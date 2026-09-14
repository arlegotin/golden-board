"""Compact generic-opcode M2 decoder recipe construction.

The production codecs live in :mod:`golden_board.m2_codec`.  This module emits
independent, self-declaring programs for the frozen bootstrap recipe VM; it
does not call those production decoders while evaluating a recipe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from hashlib import sha256
import json
from typing import Callable

from . import bootstrap
from .m2_codec import (
    _be,
    _bits_to_bytes,
    _gf_mul,
    _recipe_record,
    eh72_decode,
    eh72_encode,
    rs_generator_coefficients,
    rs255_191_decode,
    rs255_191_encode,
)


_WORD = 0
_WORD_BYTES = 256
_COUNT = 256
_ERASURES = 257
_MASK = 321
_SYNDROMES = 577
_GAMMA = 641
_TRANSFORMED = 706
_C = 834
_B = 963
_OLD_C = 1092
_L = 1221
_M = 1222
_BM_B = 1223
_LOCATOR = 1224
_OMEGA = 1289
_DERIVATIVE = 1353
_ROOT_COUNT = 1417
_ERROR_COUNT = 1418
_ERASURE_ROOT_COUNT = 1419
_ROOTS = 1420
_MAGNITUDES = 1486
_POINT = 1552
_ACCUMULATOR = 1553
_X = 1554
_OUTER = 1555
_FLAG = 1556
_QUOTIENT = 1557
_DISCREPANCY = 1558
_DEGREE = 1559
_CRC = 1560
_STATE_BYTES = 1564

_LOG_TABLE = 1
_EXP_TABLE = 2
_IDENTITY_TABLE = 3
_INVERSE_TABLE = 4
_CRC_TABLE = 5
_DOMAIN_TABLE = 6
_INPUT_PADDING_TABLE = 7
_GENERATOR_TABLE = 8


@dataclass(frozen=True, slots=True)
class DecoderRecipeContract:
    profile_version: int
    transport_id: str
    section_check_id: str
    package: bytes
    package_sha256: str
    package_bytes: int
    recipe_id: int
    inputs: tuple[tuple[int, int], ...]
    outputs: tuple[tuple[int, int], ...]
    table_records: tuple[bytes, ...]
    worked_input: tuple[bytes, ...]
    worked_output: bytes
    held_input: tuple[bytes, ...]
    held_output: bytes


@dataclass(frozen=True, slots=True)
class TransportRecipeContract:
    profile_version: int
    transport_id: str
    section_check_id: str
    package: bytes
    package_sha256: str
    package_bytes: int
    exported_recipe_ids: tuple[int, ...]
    encoder_recipe_id: int
    encoder_inputs: tuple[tuple[int, int], ...]
    encoder_outputs: tuple[tuple[int, int], ...]
    decoder_recipe_id: int
    decoder_inputs: tuple[tuple[int, int], ...]
    decoder_outputs: tuple[tuple[int, int], ...]
    worked_source: bytes
    worked_observation: bytes
    worked_decoder_inputs: tuple[bytes, ...]
    worked_decoded_output: bytes
    held_source: bytes
    held_observation: bytes
    held_decoder_inputs: tuple[bytes, ...]
    held_decoded_output: bytes


@dataclass(frozen=True, slots=True)
class RsManifestationAdmission:
    profile_version: int
    package_sha256: str
    package_bytes: int
    node_count: int
    edge_count: int
    table_payload_bytes: int
    primitive_steps: int
    scratch_bytes: int
    corpus_sha256: str
    checked_case_ids: tuple[str, ...]
    mismatched_case_ids: tuple[str, ...]
    recipe_closure_pass: bool
    failure_reason: str
    later_resource_gates_evaluated: bool


@dataclass
class _Body:
    inputs: tuple[tuple[int, int], ...]
    nodes: list[tuple[int, int, int, tuple[int, ...], int, int]]
    state_bytes: int = _STATE_BYTES
    _constants: dict[tuple[int, int], int] = field(default_factory=dict)
    _tables: dict[tuple[int, int], int] = field(default_factory=dict)

    def add(
        self,
        opcode: int,
        value_type: int,
        width: int,
        arguments: tuple[int, ...] = (),
        auxiliary: int = 0,
        immediate: int = 0,
    ) -> int:
        self.nodes.append((opcode, value_type, width, arguments, auxiliary, immediate))
        return len(self.inputs) + len(self.nodes)

    def constant(self, width: int, value: int) -> int:
        key = (width, value)
        if key not in self._constants:
            self._constants[key] = self.add(1, bootstrap.UINT, width, immediate=value)
        return self._constants[key]

    def table(self, table_id: int, width: int) -> int:
        key = (table_id, width)
        if key not in self._tables:
            self._tables[key] = self.add(2, bootstrap.TABLE, width, auxiliary=table_id)
        return self._tables[key]

    def load(self, state: int, index: int) -> int:
        return self.add(19, bootstrap.UINT, 8, (state, index))

    def store(self, state: int, index: int, value: int) -> int:
        return self.add(20, bootstrap.BYTES, self.state_bytes, (state, index, value))

    def index(self, base: int, offset: int) -> int:
        return self.add(6, bootstrap.UINT, 64, (self.constant(64, base), offset))

    def widen(self, value: int) -> int:
        return self.add(4, bootstrap.UINT, 64, (self.constant(56, 0), value))

    def narrow(self, value: int) -> int:
        return self.add(21, bootstrap.UINT, 8, (self.table(_IDENTITY_TABLE, 8), value))

    def equal(self, left: int, right: int) -> int:
        return self.add(17, bootstrap.BOOL, 1, (left, right))

    def less(self, left: int, right: int) -> int:
        return self.add(18, bootstrap.BOOL, 1, (left, right))

    def select(
        self, condition: int, yes: int, no: int, value_type: int, width: int
    ) -> int:
        return self.add(23, value_type, width, (condition, yes, no))

    def bool_and(self, left: int, right: int) -> int:
        return self.select(
            left,
            right,
            self.add(1, bootstrap.BOOL, 1, immediate=0),
            bootstrap.BOOL,
            1,
        )

    def bool_or(self, left: int, right: int) -> int:
        return self.select(
            left,
            self.add(1, bootstrap.BOOL, 1, immediate=1),
            right,
            bootstrap.BOOL,
            1,
        )

    def bool_not(self, value: int) -> int:
        return self.equal(value, self.add(1, bootstrap.BOOL, 1, immediate=0))

    def gf_multiply(self, left: int, right: int) -> int:
        log = self.table(_LOG_TABLE, 16)
        left_log = self.add(21, bootstrap.UINT, 16, (log, left))
        right_log = self.add(21, bootstrap.UINT, 16, (log, right))
        exponent = self.add(6, bootstrap.UINT, 16, (left_log, right_log))
        return self.add(
            21,
            bootstrap.UINT,
            8,
            (self.table(_EXP_TABLE, 8), exponent),
        )

    def inverse(self, value: int) -> int:
        return self.add(
            21,
            bootstrap.UINT,
            8,
            (self.table(_INVERSE_TABLE, 8), value),
        )

    def alpha(self, exponent: int) -> int:
        return self.add(
            21,
            bootstrap.UINT,
            8,
            (self.table(_EXP_TABLE, 8), exponent),
        )

    def finish(self, state: int, status: int | None = None) -> None:
        result_status = self.add(24, bootstrap.STATUS, 16) if status is None else status
        self.add(5, bootstrap.STATUS, 16, (result_status,), auxiliary=1)
        self.add(5, bootstrap.STATUS, 16, (state,), auxiliary=2)


class _Package:
    def __init__(self, profile_version: int) -> None:
        self.profile_version = profile_version
        self.resources: dict[int, tuple[int, int]] = {}
        self.records: list[bytes] = []
        self.node_counts: list[int] = []
        self.edge_counts: list[int] = []

    def recipe(
        self,
        inputs: tuple[tuple[int, int], ...],
        outputs: tuple[tuple[int, int], ...],
        build: Callable[[_Body], None],
        state_bytes: int = _STATE_BYTES,
        recipe_id: int | None = None,
    ) -> int:
        recipe_id = len(self.records) + 1 if recipe_id is None else recipe_id
        body = _Body(inputs, [], state_bytes)
        build(body)
        raw, edges, steps, peak = _recipe_record(
            recipe_id, inputs, outputs, body.nodes, self.resources
        )
        self.records.append(raw)
        self.resources[recipe_id] = (steps, peak)
        self.node_counts.append(len(body.nodes))
        self.edge_counts.append(edges)
        return recipe_id


def _tables() -> tuple[bytes, ...]:
    exponents = [1]
    for _ in range(1, 511):
        exponents.append(_gf_mul(exponents[-1], 2))
    logarithms = [0] * 256
    for exponent, value in enumerate(exponents[:255]):
        logarithms[value] = exponent
    # A zero sentinel beyond every nonzero log sum lets the same eager lookup
    # implement the complete zero/nonzero product without SELECT branches.
    logarithms[0] = 512
    safe_exponents = exponents[:509] + [0] * 516
    inverses = [0] + [exponents[255 - logarithms[value]] for value in range(1, 256)]
    crc_rows = []
    for value in range(256):
        register = value
        for _ in range(8):
            register = (register >> 1) ^ 0x82F63B78 if register & 1 else register >> 1
        crc_rows.append(register.to_bytes(4, "big"))
    payloads = (
        b"".join(value.to_bytes(2, "big") for value in logarithms),
        bytes(safe_exponents),
        bytes(range(256)),
        bytes(inverses),
        b"".join(crc_rows),
        bytes.fromhex("d3916ac47208be5f"),
        bytes(_STATE_BYTES - _MASK + 1),
        rs_generator_coefficients()[1:],
    )
    types = (
        (bootstrap.UINT, 16),
        (bootstrap.UINT, 8),
        (bootstrap.UINT, 8),
        (bootstrap.UINT, 8),
        (bootstrap.BYTES, 4),
        (bootstrap.UINT, 8),
        (bootstrap.BYTES, _STATE_BYTES - _MASK + 1),
        (bootstrap.UINT, 8),
    )
    counts = (256, 1025, 256, 256, 256, 8, 1, 64)
    return tuple(
        b"".join(
            (
                _be(index + 1, 2),
                bytes((value_type, 0)),
                _be(width, 4),
                _be(counts[index], 4),
                _be(len(payload), 4),
                payload,
            )
        )
        for index, ((value_type, width), payload) in enumerate(
            zip(types, payloads, strict=True)
        )
    )


def _state_interfaces() -> tuple[
    tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]
]:
    return (
        ((bootstrap.BYTES, _STATE_BYTES), (bootstrap.UINT, 64)),
        ((bootstrap.STATUS, 16), (bootstrap.BYTES, _STATE_BYTES)),
    )


def prepare_rs_decoder_input(
    observed: bytes, erasures: tuple[int, ...]
) -> tuple[bytes, bytes, bytes]:
    if type(observed) is not bytes or len(observed) != 255:
        raise ValueError("observation")
    if (
        type(erasures) is not tuple
        or len(erasures) > 255
        or any(type(value) is not int or not 0 <= value <= 255 for value in erasures)
    ):
        raise ValueError("erasures")
    positions = bytearray(64)
    retained = erasures[:64]
    positions[: len(retained)] = bytes(retained)
    return observed, bytes((len(erasures),)), bytes(positions)


@lru_cache(maxsize=2)
def build_rs_decoder_recipe(profile_version: int) -> bytes:
    if profile_version not in (5, 6):
        raise ValueError("profile_version")
    package = _Package(profile_version)
    state_inputs, state_outputs = _state_interfaces()

    def workspace_zero(body: _Body) -> None:
        position = body.index(_MASK, 2)
        value = body.load(1, position)
        valid = body.equal(value, body.constant(8, 0))
        status = body.select(
            valid,
            body.add(24, bootstrap.STATUS, 16),
            body.add(25, bootstrap.STATUS, 16, immediate=3),
            bootstrap.STATUS,
            16,
        )
        body.finish(1, status)

    workspace_zero_id = package.recipe(state_inputs, state_outputs, workspace_zero)

    def count_precheck(body: _Body) -> None:
        count = body.load(1, body.constant(64, _COUNT))
        within_bound = body.less(count, body.constant(8, 65))
        sentinel = body.load(1, body.constant(64, 255))
        sentinel_valid = body.equal(sentinel, body.constant(8, 0))
        valid = body.bool_and(within_bound, sentinel_valid)
        parameter_status = body.select(
            sentinel_valid,
            body.add(25, bootstrap.STATUS, 16, immediate=4),
            body.add(25, bootstrap.STATUS, 16, immediate=3),
            bootstrap.STATUS,
            16,
        )
        status = body.select(
            valid,
            body.add(24, bootstrap.STATUS, 16),
            parameter_status,
            bootstrap.STATUS,
            16,
        )
        body.finish(1, status)

    count_precheck_id = package.recipe(state_inputs, state_outputs, count_precheck)

    def normalize_erasure(body: _Body) -> None:
        count = body.load(1, body.constant(64, _COUNT))
        count_wide = body.widen(count)
        active = body.less(2, count_wide)
        list_index = body.index(_ERASURES, 2)
        position = body.load(1, list_index)
        position_wide = body.widen(position)
        in_range = body.less(position, body.constant(8, 255))
        first = body.equal(2, body.constant(64, 0))
        previous = body.load(1, body.constant(64, _OUTER))
        increasing = body.less(previous, position)
        ordered = body.select(
            first,
            body.add(1, bootstrap.BOOL, 1, immediate=1),
            increasing,
            bootstrap.BOOL,
            1,
        )
        active_valid = body.bool_and(in_range, ordered)
        padding_valid = body.equal(position, body.constant(8, 0))
        valid = body.select(active, active_valid, padding_valid, bootstrap.BOOL, 1)
        mask_index = body.index(_MASK, position_wide)
        old_mask = body.load(1, mask_index)
        new_mask = body.select(active, body.constant(8, 1), old_mask, bootstrap.UINT, 8)
        state = body.store(1, mask_index, new_mask)
        old_word = body.load(state, position_wide)
        new_word = body.select(active, body.constant(8, 0), old_word, bootstrap.UINT, 8)
        state = body.store(state, position_wide, new_word)
        retained = body.select(active, position, previous, bootstrap.UINT, 8)
        state = body.store(state, body.constant(64, _OUTER), retained)
        status = body.select(
            valid,
            body.add(24, bootstrap.STATUS, 16),
            body.add(25, bootstrap.STATUS, 16, immediate=3),
            bootstrap.STATUS,
            16,
        )
        body.finish(state, status)

    normalize_erasure_id = package.recipe(
        state_inputs, state_outputs, normalize_erasure
    )

    def syndrome_symbol(body: _Body) -> None:
        accumulator = body.load(1, body.constant(64, _ACCUMULATOR))
        point = body.load(1, body.constant(64, _POINT))
        coefficient = body.load(1, body.index(_WORD, 2))
        product = body.gf_multiply(accumulator, point)
        value = body.add(13, bootstrap.UINT, 8, (product, coefficient))
        state = body.store(1, body.constant(64, _ACCUMULATOR), value)
        body.finish(state)

    syndrome_symbol_id = package.recipe(state_inputs, state_outputs, syndrome_symbol)

    def syndrome_root(body: _Body) -> None:
        point = body.alpha(2)
        state = body.store(1, body.constant(64, _POINT), point)
        state = body.store(state, body.constant(64, _ACCUMULATOR), body.constant(8, 0))
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=syndrome_symbol_id,
            immediate=255,
        )
        value = body.load(state, body.constant(64, _ACCUMULATOR))
        state = body.store(state, body.index(_SYNDROMES, 2), value)
        post_flag = body.load(state, body.constant(64, _FLAG))
        post = body.equal(post_flag, body.constant(8, 1))
        nonzero = body.bool_not(body.equal(value, body.constant(8, 0)))
        invalid = body.bool_and(post, nonzero)
        status = body.select(
            invalid,
            body.add(25, bootstrap.STATUS, 16, immediate=5),
            body.add(24, bootstrap.STATUS, 16),
            bootstrap.STATUS,
            16,
        )
        body.finish(state, status)

    syndrome_root_id = package.recipe(state_inputs, state_outputs, syndrome_root)

    def gamma_degree(body: _Body) -> None:
        outer = body.load(1, body.constant(64, _OUTER))
        outer_wide = body.widen(outer)
        count = body.load(1, body.constant(64, _COUNT))
        active_outer = body.less(outer, count)
        degree = body.add(7, bootstrap.UINT, 64, (body.constant(64, 64), 2))
        nonzero = body.less(body.constant(64, 0), degree)
        outer_plus_two = body.add(
            6, bootstrap.UINT, 64, (outer_wide, body.constant(64, 2))
        )
        within_degree = body.less(degree, outer_plus_two)
        active = body.bool_and(active_outer, body.bool_and(nonzero, within_degree))
        current_index = body.index(_GAMMA, degree)
        current = body.load(1, current_index)
        safe_degree = body.select(
            nonzero, degree, body.constant(64, 1), bootstrap.UINT, 64
        )
        previous_degree = body.add(
            7, bootstrap.UINT, 64, (safe_degree, body.constant(64, 1))
        )
        previous = body.load(1, body.index(_GAMMA, previous_degree))
        x_value = body.load(1, body.constant(64, _X))
        product = body.gf_multiply(previous, x_value)
        updated = body.add(13, bootstrap.UINT, 8, (current, product))
        selected = body.select(active, updated, current, bootstrap.UINT, 8)
        state = body.store(1, current_index, selected)
        body.finish(state)

    gamma_degree_id = package.recipe(state_inputs, state_outputs, gamma_degree)

    def gamma_outer(body: _Body) -> None:
        ordinal = body.narrow(2)
        position = body.load(1, body.index(_ERASURES, 2))
        exponent = body.add(
            7,
            bootstrap.UINT,
            64,
            (body.constant(64, 254), body.widen(position)),
        )
        x_value = body.alpha(exponent)
        state = body.store(1, body.constant(64, _OUTER), ordinal)
        state = body.store(state, body.constant(64, _X), x_value)
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=gamma_degree_id,
            immediate=65,
        )
        body.finish(state)

    gamma_outer_id = package.recipe(state_inputs, state_outputs, gamma_outer)

    def transformed_convolution(body: _Body) -> None:
        outer = body.load(1, body.constant(64, _OUTER))
        inner = body.load(1, body.constant(64, _X))
        outer_wide = body.widen(outer)
        inner_wide = body.widen(inner)
        reverse = body.add(7, bootstrap.UINT, 64, (outer_wide, inner_wide))
        count = body.load(1, body.constant(64, _COUNT))
        active = body.less(
            inner, body.add(6, bootstrap.UINT, 8, (count, body.constant(8, 1)))
        )
        gamma_value = body.load(1, body.index(_GAMMA, inner_wide))
        syndrome = body.load(1, body.index(_SYNDROMES, reverse))
        product = body.gf_multiply(gamma_value, syndrome)
        selected = body.select(active, product, body.constant(8, 0), bootstrap.UINT, 8)
        target = body.index(_TRANSFORMED, outer_wide)
        current = body.load(1, target)
        accumulated = body.add(13, bootstrap.UINT, 8, (current, selected))
        state = body.store(1, target, accumulated)
        at_end = body.equal(inner, outer)
        next_inner = body.select(
            at_end,
            body.constant(8, 0),
            body.add(6, bootstrap.UINT, 8, (inner, body.constant(8, 1))),
            bootstrap.UINT,
            8,
        )
        next_outer = body.select(
            at_end,
            body.add(6, bootstrap.UINT, 8, (outer, body.constant(8, 1))),
            outer,
            bootstrap.UINT,
            8,
        )
        state = body.store(state, body.constant(64, _X), next_inner)
        state = body.store(state, body.constant(64, _OUTER), next_outer)
        body.finish(state)

    transformed_convolution_id = package.recipe(
        state_inputs, state_outputs, transformed_convolution
    )

    def copy_c(body: _Body) -> None:
        value = body.load(1, body.index(_C, 2))
        state = body.store(1, body.index(_OLD_C, 2), value)
        body.finish(state)

    copy_c_id = package.recipe(state_inputs, state_outputs, copy_c)

    def bm_discrepancy(body: _Body) -> None:
        n_value = body.load(1, body.constant(64, _OUTER))
        n_wide = body.widen(n_value)
        locator_degree = body.load(1, body.constant(64, _L))
        locator_wide = body.widen(locator_degree)
        index = body.add(6, bootstrap.UINT, 64, (2, body.constant(64, 1)))
        index_limit = body.add(
            6, bootstrap.UINT, 64, (locator_wide, body.constant(64, 1))
        )
        within_degree = body.less(index, index_limit)
        n_limit = body.add(6, bootstrap.UINT, 64, (n_wide, body.constant(64, 1)))
        within_n = body.less(index, n_limit)
        active = body.bool_and(within_degree, within_n)
        safe_index = body.select(within_n, index, n_wide, bootstrap.UINT, 64)
        u_degree = body.add(7, bootstrap.UINT, 64, (n_wide, safe_index))
        count = body.load(1, body.constant(64, _COUNT))
        transformed_index = body.add(
            6,
            bootstrap.UINT,
            64,
            (body.widen(count), u_degree),
        )
        c_value = body.load(1, body.index(_C, index))
        u_value = body.load(1, body.index(_TRANSFORMED, transformed_index))
        product = body.gf_multiply(c_value, u_value)
        selected = body.select(active, product, body.constant(8, 0), bootstrap.UINT, 8)
        accumulator = body.load(1, body.constant(64, _ACCUMULATOR))
        value = body.add(13, bootstrap.UINT, 8, (accumulator, selected))
        state = body.store(1, body.constant(64, _ACCUMULATOR), value)
        body.finish(state)

    bm_discrepancy_id = package.recipe(state_inputs, state_outputs, bm_discrepancy)

    def c_update(body: _Body) -> None:
        discrepancy = body.load(1, body.constant(64, _DISCREPANCY))
        nonzero = body.bool_not(body.equal(discrepancy, body.constant(8, 0)))
        active_flag = body.load(1, body.constant(64, _FLAG))
        active = body.bool_and(nonzero, body.equal(active_flag, body.constant(8, 1)))
        shift = body.load(1, body.constant(64, _M))
        target = body.add(6, bootstrap.UINT, 64, (2, body.widen(shift)))
        target_valid = body.less(target, body.constant(64, 65))
        enabled = body.bool_and(active, target_valid)
        b_value = body.load(1, body.index(_B, 2))
        quotient = body.load(1, body.constant(64, _QUOTIENT))
        product = body.gf_multiply(quotient, b_value)
        current = body.load(1, body.index(_C, target))
        updated = body.add(13, bootstrap.UINT, 8, (current, product))
        selected = body.select(enabled, updated, current, bootstrap.UINT, 8)
        state = body.store(1, body.index(_C, target), selected)
        body.finish(state)

    c_update_id = package.recipe(state_inputs, state_outputs, c_update)

    def b_update(body: _Body) -> None:
        flag = body.load(1, body.constant(64, _DEGREE))
        update = body.equal(flag, body.constant(8, 1))
        old_c = body.load(1, body.index(_OLD_C, 2))
        current = body.load(1, body.index(_B, 2))
        selected = body.select(update, old_c, current, bootstrap.UINT, 8)
        state = body.store(1, body.index(_B, 2), selected)
        body.finish(state)

    b_update_id = package.recipe(state_inputs, state_outputs, b_update)

    def bm_outer(body: _Body) -> None:
        n_byte = body.narrow(2)
        n_wide = body.widen(n_byte)
        count = body.load(1, body.constant(64, _COUNT))
        transformed_index = body.add(
            6,
            bootstrap.UINT,
            64,
            (body.widen(count), n_wide),
        )
        active = body.less(transformed_index, body.constant(64, 64))
        u_value = body.load(1, body.index(_TRANSFORMED, transformed_index))
        initial = body.select(active, u_value, body.constant(8, 0), bootstrap.UINT, 8)
        state = body.store(1, body.constant(64, _OUTER), n_byte)
        state = body.store(state, body.constant(64, _ACCUMULATOR), initial)
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=bm_discrepancy_id,
            immediate=32,
        )
        discrepancy = body.load(state, body.constant(64, _ACCUMULATOR))
        state = body.store(state, body.constant(64, _DISCREPANCY), discrepancy)
        discrepancy_zero = body.equal(discrepancy, body.constant(8, 0))
        active_nonzero = body.bool_and(active, body.bool_not(discrepancy_zero))
        prior_b = body.load(state, body.constant(64, _BM_B))
        quotient = body.gf_multiply(discrepancy, body.inverse(prior_b))
        quotient = body.select(
            active_nonzero,
            quotient,
            body.constant(8, 0),
            bootstrap.UINT,
            8,
        )
        state = body.store(state, body.constant(64, _QUOTIENT), quotient)
        state = body.store(
            state,
            body.constant(64, _FLAG),
            body.select(
                active_nonzero,
                body.constant(8, 1),
                body.constant(8, 0),
                bootstrap.UINT,
                8,
            ),
        )
        locator_degree = body.load(state, body.constant(64, _L))
        twice_l = body.add(
            6,
            bootstrap.UINT,
            64,
            (body.widen(locator_degree), body.widen(locator_degree)),
        )
        update_condition = body.bool_not(body.less(n_wide, twice_l))
        update_b = body.bool_and(active_nonzero, update_condition)
        state = body.store(
            state,
            body.constant(64, _DEGREE),
            body.select(
                update_b,
                body.constant(8, 1),
                body.constant(8, 0),
                bootstrap.UINT,
                8,
            ),
        )
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=copy_c_id,
            immediate=33,
        )
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=c_update_id,
            immediate=33,
        )
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=b_update_id,
            immediate=33,
        )
        old_l = body.load(state, body.constant(64, _L))
        n_plus_one = body.add(6, bootstrap.UINT, 64, (n_wide, body.constant(64, 1)))
        safe_l = body.select(
            update_b,
            body.widen(old_l),
            body.constant(64, 0),
            bootstrap.UINT,
            64,
        )
        new_l_wide = body.add(7, bootstrap.UINT, 64, (n_plus_one, safe_l))
        new_l = body.narrow(new_l_wide)
        selected_l = body.select(update_b, new_l, old_l, bootstrap.UINT, 8)
        state = body.store(state, body.constant(64, _L), selected_l)
        old_m = body.load(state, body.constant(64, _M))
        incremented_m = body.add(6, bootstrap.UINT, 8, (old_m, body.constant(8, 1)))
        changed_m = body.select(
            update_b,
            body.constant(8, 1),
            incremented_m,
            bootstrap.UINT,
            8,
        )
        selected_m = body.select(active, changed_m, old_m, bootstrap.UINT, 8)
        state = body.store(state, body.constant(64, _M), selected_m)
        old_b = body.load(state, body.constant(64, _BM_B))
        selected_b = body.select(update_b, discrepancy, old_b, bootstrap.UINT, 8)
        state = body.store(state, body.constant(64, _BM_B), selected_b)
        body.finish(state)

    bm_outer_id = package.recipe(state_inputs, state_outputs, bm_outer)

    def c_degree_scan(body: _Body) -> None:
        c_coefficient = body.load(1, body.index(_C, 2))
        locator_coefficient = body.load(1, body.index(_LOCATOR, 2))
        mode = body.load(1, body.constant(64, _FLAG))
        coefficient = body.select(
            body.equal(mode, body.constant(8, 1)),
            locator_coefficient,
            c_coefficient,
            bootstrap.UINT,
            8,
        )
        nonzero = body.bool_not(body.equal(coefficient, body.constant(8, 0)))
        current = body.load(1, body.constant(64, _DEGREE))
        ordinal = body.narrow(2)
        selected = body.select(nonzero, ordinal, current, bootstrap.UINT, 8)
        state = body.store(1, body.constant(64, _DEGREE), selected)
        body.finish(state)

    c_degree_scan_id = package.recipe(state_inputs, state_outputs, c_degree_scan)

    def bm_boundary(body: _Body) -> None:
        degree = body.load(1, body.constant(64, _DEGREE))
        locator_degree = body.load(1, body.constant(64, _L))
        degree_valid = body.equal(degree, locator_degree)
        count = body.load(1, body.constant(64, _COUNT))
        twice_l = body.add(
            6,
            bootstrap.UINT,
            8,
            (locator_degree, locator_degree),
        )
        total = body.add(6, bootstrap.UINT, 8, (twice_l, count))
        bound_valid = body.less(total, body.constant(8, 65))
        valid = body.bool_and(degree_valid, bound_valid)
        status = body.select(
            valid,
            body.add(24, bootstrap.STATUS, 16),
            body.add(25, bootstrap.STATUS, 16, immediate=4),
            bootstrap.STATUS,
            16,
        )
        body.finish(1, status)

    bm_boundary_id = package.recipe(state_inputs, state_outputs, bm_boundary)

    def locator_convolution(body: _Body) -> None:
        outer = body.load(1, body.constant(64, _OUTER))
        inner = body.load(1, body.constant(64, _X))
        outer_wide = body.widen(outer)
        inner_wide = body.widen(inner)
        count = body.load(1, body.constant(64, _COUNT))
        locator_degree = body.load(1, body.constant(64, _L))
        c_degree = body.add(7, bootstrap.UINT, 64, (outer_wide, inner_wide))
        within_gamma = body.less(
            inner,
            body.add(6, bootstrap.UINT, 8, (count, body.constant(8, 1))),
        )
        within_c = body.less(
            body.narrow(c_degree),
            body.add(
                6,
                bootstrap.UINT,
                8,
                (locator_degree, body.constant(8, 1)),
            ),
        )
        active = body.bool_and(within_gamma, within_c)
        gamma_value = body.load(1, body.index(_GAMMA, inner_wide))
        c_value = body.load(1, body.index(_C, c_degree))
        product = body.gf_multiply(gamma_value, c_value)
        selected = body.select(active, product, body.constant(8, 0), bootstrap.UINT, 8)
        target = body.index(_LOCATOR, outer_wide)
        current = body.load(1, target)
        value = body.add(13, bootstrap.UINT, 8, (current, selected))
        state = body.store(1, target, value)
        at_end = body.equal(inner, outer)
        next_inner = body.select(
            at_end,
            body.constant(8, 0),
            body.add(6, bootstrap.UINT, 8, (inner, body.constant(8, 1))),
            bootstrap.UINT,
            8,
        )
        next_outer = body.select(
            at_end,
            body.add(6, bootstrap.UINT, 8, (outer, body.constant(8, 1))),
            outer,
            bootstrap.UINT,
            8,
        )
        state = body.store(state, body.constant(64, _X), next_inner)
        state = body.store(state, body.constant(64, _OUTER), next_outer)
        body.finish(state)

    locator_convolution_id = package.recipe(
        state_inputs, state_outputs, locator_convolution
    )

    def locator_boundary(body: _Body) -> None:
        degree = body.load(1, body.constant(64, _DEGREE))
        count = body.load(1, body.constant(64, _COUNT))
        locator_degree = body.load(1, body.constant(64, _L))
        expected = body.add(6, bootstrap.UINT, 8, (count, locator_degree))
        valid = body.equal(degree, expected)
        status = body.select(
            valid,
            body.add(24, bootstrap.STATUS, 16),
            body.add(25, bootstrap.STATUS, 16, immediate=4),
            bootstrap.STATUS,
            16,
        )
        body.finish(1, status)

    locator_boundary_id = package.recipe(state_inputs, state_outputs, locator_boundary)

    def omega_convolution(body: _Body) -> None:
        outer = body.load(1, body.constant(64, _OUTER))
        inner = body.load(1, body.constant(64, _X))
        outer_wide = body.widen(outer)
        inner_wide = body.widen(inner)
        syndrome_degree = body.add(7, bootstrap.UINT, 64, (outer_wide, inner_wide))
        syndrome = body.load(1, body.index(_SYNDROMES, syndrome_degree))
        locator = body.load(1, body.index(_LOCATOR, inner_wide))
        product = body.gf_multiply(syndrome, locator)
        target = body.index(_OMEGA, outer_wide)
        current = body.load(1, target)
        value = body.add(13, bootstrap.UINT, 8, (current, product))
        state = body.store(1, target, value)
        at_end = body.equal(inner, outer)
        next_inner = body.select(
            at_end,
            body.constant(8, 0),
            body.add(6, bootstrap.UINT, 8, (inner, body.constant(8, 1))),
            bootstrap.UINT,
            8,
        )
        next_outer = body.select(
            at_end,
            body.add(6, bootstrap.UINT, 8, (outer, body.constant(8, 1))),
            outer,
            bootstrap.UINT,
            8,
        )
        state = body.store(state, body.constant(64, _X), next_inner)
        state = body.store(state, body.constant(64, _OUTER), next_outer)
        body.finish(state)

    omega_convolution_id = package.recipe(
        state_inputs, state_outputs, omega_convolution
    )

    def polynomial_evaluator(base: int, length: int) -> Callable[[_Body], None]:
        def build(body: _Body) -> None:
            reverse_index = body.add(
                7,
                bootstrap.UINT,
                64,
                (body.constant(64, length - 1), 2),
            )
            coefficient = body.load(1, body.index(base, reverse_index))
            accumulator = body.load(1, body.constant(64, _ACCUMULATOR))
            point = body.load(1, body.constant(64, _POINT))
            product = body.gf_multiply(accumulator, point)
            value = body.add(13, bootstrap.UINT, 8, (product, coefficient))
            state = body.store(1, body.constant(64, _ACCUMULATOR), value)
            body.finish(state)

        return build

    locator_eval_id = package.recipe(
        state_inputs, state_outputs, polynomial_evaluator(_LOCATOR, 65)
    )
    omega_eval_id = package.recipe(
        state_inputs, state_outputs, polynomial_evaluator(_OMEGA, 64)
    )

    def derivative_evaluator(body: _Body) -> None:
        reverse_index = body.add(
            7,
            bootstrap.UINT,
            64,
            (body.constant(64, 63), 2),
        )
        source_degree = body.add(
            6,
            bootstrap.UINT,
            64,
            (reverse_index, body.constant(64, 1)),
        )
        source = body.load(1, body.index(_LOCATOR, source_degree))
        remainder = body.add(
            10,
            bootstrap.UINT,
            64,
            (source_degree, body.constant(64, 2)),
        )
        odd_source = body.equal(remainder, body.constant(64, 1))
        coefficient = body.select(
            odd_source, source, body.constant(8, 0), bootstrap.UINT, 8
        )
        accumulator = body.load(1, body.constant(64, _ACCUMULATOR))
        point = body.load(1, body.constant(64, _POINT))
        product = body.gf_multiply(accumulator, point)
        value = body.add(13, bootstrap.UINT, 8, (product, coefficient))
        state = body.store(1, body.constant(64, _ACCUMULATOR), value)
        body.finish(state)

    derivative_eval_id = package.recipe(
        state_inputs, state_outputs, derivative_evaluator
    )

    def chien(body: _Body) -> None:
        position_byte = body.narrow(2)
        exponent = body.add(6, bootstrap.UINT, 64, (2, body.constant(64, 1)))
        point = body.alpha(exponent)
        state = body.store(1, body.constant(64, _POINT), point)
        state = body.store(state, body.constant(64, _ACCUMULATOR), body.constant(8, 0))
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=locator_eval_id,
            immediate=65,
        )
        locator_value = body.load(state, body.constant(64, _ACCUMULATOR))
        root = body.equal(locator_value, body.constant(8, 0))
        erased_value = body.load(1, body.index(_MASK, 2))
        erased = body.equal(erased_value, body.constant(8, 1))
        unknown_root = body.bool_and(root, body.bool_not(erased))
        root_count = body.load(state, body.constant(64, _ROOT_COUNT))
        root_capacity = body.less(root_count, body.constant(8, 65))
        bad_capacity = body.bool_and(root, body.bool_not(root_capacity))
        root_target = body.index(_ROOTS, body.widen(root_count))
        old_root = body.load(state, root_target)
        selected_root = body.select(root, position_byte, old_root, bootstrap.UINT, 8)
        state = body.store(state, root_target, selected_root)
        root_increment = body.add(
            6, bootstrap.UINT, 8, (root_count, body.constant(8, 1))
        )
        new_root_count = body.select(
            root, root_increment, root_count, bootstrap.UINT, 8
        )
        state = body.store(state, body.constant(64, _ROOT_COUNT), new_root_count)
        error_count = body.load(state, body.constant(64, _ERROR_COUNT))
        error_increment = body.add(
            6, bootstrap.UINT, 8, (error_count, body.constant(8, 1))
        )
        new_error_count = body.select(
            unknown_root, error_increment, error_count, bootstrap.UINT, 8
        )
        state = body.store(state, body.constant(64, _ERROR_COUNT), new_error_count)
        erased_root = body.bool_and(root, erased)
        erased_count = body.load(state, body.constant(64, _ERASURE_ROOT_COUNT))
        erased_increment = body.add(
            6, bootstrap.UINT, 8, (erased_count, body.constant(8, 1))
        )
        new_erased_count = body.select(
            erased_root, erased_increment, erased_count, bootstrap.UINT, 8
        )
        state = body.store(
            state, body.constant(64, _ERASURE_ROOT_COUNT), new_erased_count
        )
        status = body.select(
            bad_capacity,
            body.add(25, bootstrap.STATUS, 16, immediate=5),
            body.add(24, bootstrap.STATUS, 16),
            bootstrap.STATUS,
            16,
        )
        body.finish(state, status)

    chien_id = package.recipe(state_inputs, state_outputs, chien)

    def root_boundary(body: _Body) -> None:
        count = body.load(1, body.constant(64, _COUNT))
        locator_degree = body.load(1, body.constant(64, _L))
        expected_roots = body.add(6, bootstrap.UINT, 8, (count, locator_degree))
        root_count = body.load(1, body.constant(64, _ROOT_COUNT))
        roots_valid = body.equal(root_count, expected_roots)
        error_count = body.load(1, body.constant(64, _ERROR_COUNT))
        errors_valid = body.equal(error_count, locator_degree)
        erasure_roots = body.load(1, body.constant(64, _ERASURE_ROOT_COUNT))
        erasures_valid = body.equal(erasure_roots, count)
        valid = body.bool_and(roots_valid, body.bool_and(errors_valid, erasures_valid))
        status = body.select(
            valid,
            body.add(24, bootstrap.STATUS, 16),
            body.add(25, bootstrap.STATUS, 16, immediate=5),
            bootstrap.STATUS,
            16,
        )
        body.finish(1, status)

    root_boundary_id = package.recipe(state_inputs, state_outputs, root_boundary)

    def magnitude(body: _Body) -> None:
        root_count = body.load(1, body.constant(64, _ROOT_COUNT))
        active = body.less(2, body.widen(root_count))
        position = body.load(1, body.index(_ROOTS, 2))
        position_wide = body.widen(position)
        point_exponent = body.add(
            6,
            bootstrap.UINT,
            64,
            (position_wide, body.constant(64, 1)),
        )
        point = body.alpha(point_exponent)
        state = body.store(1, body.constant(64, _POINT), point)
        state = body.store(state, body.constant(64, _ACCUMULATOR), body.constant(8, 0))
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=omega_eval_id,
            immediate=64,
        )
        omega_value = body.load(state, body.constant(64, _ACCUMULATOR))
        state = body.store(state, body.constant(64, _ACCUMULATOR), body.constant(8, 0))
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=derivative_eval_id,
            immediate=64,
        )
        derivative_value = body.load(state, body.constant(64, _ACCUMULATOR))
        denominator_zero = body.equal(derivative_value, body.constant(8, 0))
        x_exponent = body.add(
            7,
            bootstrap.UINT,
            64,
            (body.constant(64, 254), position_wide),
        )
        x_value = body.alpha(x_exponent)
        numerator = body.gf_multiply(x_value, omega_value)
        value = body.gf_multiply(numerator, body.inverse(derivative_value))
        value_zero = body.equal(value, body.constant(8, 0))
        erased_value = body.load(1, body.index(_MASK, position_wide))
        erased = body.equal(erased_value, body.constant(8, 1))
        invalid_derivative = body.bool_and(active, denominator_zero)
        unknown = body.bool_and(active, body.bool_not(erased))
        invalid_zero = body.bool_and(unknown, value_zero)
        invalid = body.bool_or(invalid_derivative, invalid_zero)
        target = body.index(_MAGNITUDES, 2)
        old = body.load(state, target)
        selected = body.select(active, value, old, bootstrap.UINT, 8)
        state = body.store(state, target, selected)
        status = body.select(
            invalid,
            body.add(25, bootstrap.STATUS, 16, immediate=5),
            body.add(24, bootstrap.STATUS, 16),
            bootstrap.STATUS,
            16,
        )
        body.finish(state, status)

    magnitude_id = package.recipe(state_inputs, state_outputs, magnitude)

    def correction(body: _Body) -> None:
        root_count = body.load(1, body.constant(64, _ROOT_COUNT))
        active = body.less(2, body.widen(root_count))
        root = body.load(1, body.index(_ROOTS, 2))
        magnitude = body.load(1, body.index(_MAGNITUDES, 2))
        root_wide = body.widen(root)
        current = body.load(1, root_wide)
        corrected = body.add(13, bootstrap.UINT, 8, (current, magnitude))
        selected = body.select(active, corrected, current, bootstrap.UINT, 8)
        state = body.store(1, root_wide, selected)
        body.finish(state)

    correction_id = package.recipe(state_inputs, state_outputs, correction)

    def crc_step(body: _Body) -> None:
        domain_limit = body.constant(64, 8)
        in_domain = body.less(2, domain_limit)
        domain_index = body.select(
            in_domain, 2, body.constant(64, 0), bootstrap.UINT, 64
        )
        domain_value = body.add(
            21,
            bootstrap.UINT,
            8,
            (body.table(_DOMAIN_TABLE, 8), domain_index),
        )
        safe_preimage = body.select(in_domain, domain_limit, 2, bootstrap.UINT, 64)
        word_index = body.add(7, bootstrap.UINT, 64, (safe_preimage, domain_limit))
        word_value = body.load(1, word_index)
        input_value = body.select(
            in_domain, domain_value, word_value, bootstrap.UINT, 8
        )
        old = tuple(body.load(1, body.constant(64, _CRC + index)) for index in range(4))
        table_index = body.add(13, bootstrap.UINT, 8, (old[3], input_value))
        row = body.add(
            21,
            bootstrap.BYTES,
            4,
            (body.table(_CRC_TABLE, 4), table_index),
        )
        row_bytes = tuple(
            body.add(
                19,
                bootstrap.UINT,
                8,
                (row, body.constant(64, index)),
            )
            for index in range(4)
        )
        values = (
            row_bytes[0],
            body.add(13, bootstrap.UINT, 8, (old[0], row_bytes[1])),
            body.add(13, bootstrap.UINT, 8, (old[1], row_bytes[2])),
            body.add(13, bootstrap.UINT, 8, (old[2], row_bytes[3])),
        )
        state = 1
        for index, value in enumerate(values):
            state = body.store(state, body.constant(64, _CRC + index), value)
        body.finish(state)

    crc_step_id = package.recipe(state_inputs, state_outputs, crc_step)

    main_inputs = (
        (bootstrap.BYTES, 255),
        (bootstrap.BYTES, 1),
        (bootstrap.BYTES, 64),
    )
    main_outputs = ((bootstrap.STATUS, 16), (bootstrap.BYTES, 191))

    def main(body: _Body) -> None:
        padding_table = body.table(_INPUT_PADDING_TABLE, _STATE_BYTES - _MASK + 1)
        padding = body.add(
            21,
            bootstrap.BYTES,
            _STATE_BYTES - _MASK + 1,
            (padding_table, body.constant(64, 0)),
        )
        sentinel = body.add(
            3,
            bootstrap.BYTES,
            1,
            (
                padding,
                body.constant(64, 0),
                body.constant(64, 1),
            ),
        )
        tail = body.add(
            3,
            bootstrap.BYTES,
            _STATE_BYTES - _MASK,
            (
                padding,
                body.constant(64, 1),
                body.constant(64, _STATE_BYTES - _MASK),
            ),
        )
        state = body.add(4, bootstrap.BYTES, 256, (1, sentinel))
        state = body.add(4, bootstrap.BYTES, 257, (state, 2))
        state = body.add(4, bootstrap.BYTES, _MASK, (state, 3))
        state = body.add(4, bootstrap.BYTES, _STATE_BYTES, (state, tail))
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=workspace_zero_id,
            immediate=_STATE_BYTES - _MASK,
        )
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=count_precheck_id,
            immediate=1,
        )
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=normalize_erasure_id,
            immediate=64,
        )
        one = body.constant(8, 1)
        state = body.store(state, body.constant(64, _GAMMA), one)
        state = body.store(state, body.constant(64, _C), one)
        state = body.store(state, body.constant(64, _B), one)
        state = body.store(state, body.constant(64, _M), one)
        state = body.store(state, body.constant(64, _BM_B), one)
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=syndrome_root_id,
            immediate=64,
        )
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=gamma_outer_id,
            immediate=64,
        )
        state = body.store(state, body.constant(64, _OUTER), body.constant(8, 0))
        state = body.store(state, body.constant(64, _X), body.constant(8, 0))
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=transformed_convolution_id,
            immediate=2080,
        )
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=bm_outer_id,
            immediate=64,
        )
        state = body.store(state, body.constant(64, _DEGREE), body.constant(8, 0))
        state = body.store(state, body.constant(64, _FLAG), body.constant(8, 0))
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=c_degree_scan_id,
            immediate=65,
        )
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=bm_boundary_id,
            immediate=1,
        )
        state = body.store(state, body.constant(64, _OUTER), body.constant(8, 0))
        state = body.store(state, body.constant(64, _X), body.constant(8, 0))
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=locator_convolution_id,
            immediate=2145,
        )
        state = body.store(state, body.constant(64, _DEGREE), body.constant(8, 0))
        state = body.store(state, body.constant(64, _FLAG), body.constant(8, 1))
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=c_degree_scan_id,
            immediate=65,
        )
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=locator_boundary_id,
            immediate=1,
        )
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=chien_id,
            immediate=255,
        )
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=root_boundary_id,
            immediate=1,
        )
        state = body.store(state, body.constant(64, _OUTER), body.constant(8, 0))
        state = body.store(state, body.constant(64, _X), body.constant(8, 0))
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=omega_convolution_id,
            immediate=2080,
        )
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=magnitude_id,
            immediate=64,
        )
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=correction_id,
            immediate=64,
        )
        state = body.store(state, body.constant(64, _FLAG), body.constant(8, 1))
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=syndrome_root_id,
            immediate=64,
        )
        for index in range(4):
            state = body.store(
                state,
                body.constant(64, _CRC + index),
                body.constant(8, 0xFF),
            )
        state = body.add(
            22,
            bootstrap.BYTES,
            _STATE_BYTES,
            (state,),
            auxiliary=crc_step_id,
            immediate=195,
        )
        valid = body.add(1, bootstrap.BOOL, 1, immediate=1)
        for index in range(4):
            register = body.load(state, body.constant(64, _CRC + index))
            final = body.add(13, bootstrap.UINT, 8, (register, body.constant(8, 0xFF)))
            expected = body.load(state, body.constant(64, 187 + index))
            equal = body.equal(final, expected)
            valid = body.bool_and(valid, equal)
        start = body.constant(64, 0)
        length = body.constant(64, 191)
        decoded = body.add(3, bootstrap.BYTES, 191, (state, start, length))
        status = body.select(
            valid,
            body.add(24, bootstrap.STATUS, 16),
            body.add(25, bootstrap.STATUS, 16, immediate=6),
            bootstrap.STATUS,
            16,
        )
        body.add(5, bootstrap.STATUS, 16, (status,), auxiliary=1)
        body.add(5, bootstrap.STATUS, 16, (decoded,), auxiliary=2)

    final_recipe_id = package.recipe(main_inputs, main_outputs, main, recipe_id=30)
    if final_recipe_id != 30:
        raise AssertionError("decoder recipe identity")

    encoder_state_inputs = (
        (bootstrap.BYTES, 256),
        (bootstrap.UINT, 64),
    )
    encoder_state_outputs = (
        (bootstrap.STATUS, 16),
        (bootstrap.BYTES, 256),
    )

    def encoder_zero(body: _Body) -> None:
        position = body.add(
            6,
            bootstrap.UINT,
            64,
            (body.constant(64, 191), 2),
        )
        value = body.load(1, position)
        valid = body.equal(value, body.constant(8, 0))
        status = body.select(
            valid,
            body.add(24, bootstrap.STATUS, 16),
            body.add(25, bootstrap.STATUS, 16, immediate=3),
            bootstrap.STATUS,
            16,
        )
        body.finish(1, status)

    encoder_zero_id = package.recipe(
        encoder_state_inputs,
        encoder_state_outputs,
        encoder_zero,
        256,
        31,
    )

    def encoder_parity(body: _Body) -> None:
        feedback = body.load(1, body.constant(64, 255))
        factor = body.add(
            21,
            bootstrap.UINT,
            8,
            (body.table(_GENERATOR_TABLE, 8), 2),
        )
        product = body.gf_multiply(feedback, factor)
        following = body.load(
            1,
            body.add(
                6,
                bootstrap.UINT,
                64,
                (body.constant(64, 192), 2),
            ),
        )
        is_last = body.equal(2, body.constant(64, 63))
        combined = body.add(13, bootstrap.UINT, 8, (product, following))
        selected = body.select(is_last, product, combined, bootstrap.UINT, 8)
        target = body.add(
            6,
            bootstrap.UINT,
            64,
            (body.constant(64, 191), 2),
        )
        state = body.store(1, target, selected)
        body.finish(state)

    encoder_parity_id = package.recipe(
        encoder_state_inputs,
        encoder_state_outputs,
        encoder_parity,
        256,
        32,
    )

    def encoder_data(body: _Body) -> None:
        data_value = body.load(1, 2)
        parity_first = body.load(1, body.constant(64, 191))
        feedback = body.add(13, bootstrap.UINT, 8, (data_value, parity_first))
        staged = body.store(1, body.constant(64, 255), feedback)
        state = body.add(
            22,
            bootstrap.BYTES,
            256,
            (staged,),
            auxiliary=encoder_parity_id,
            immediate=64,
        )
        body.finish(state)

    encoder_data_id = package.recipe(
        encoder_state_inputs,
        encoder_state_outputs,
        encoder_data,
        256,
        33,
    )

    encoder_inputs = ((bootstrap.BYTES, 191),)
    encoder_outputs = (
        (bootstrap.STATUS, 16),
        (bootstrap.BYTES, 255),
    )

    def encoder_main(body: _Body) -> None:
        padding = body.add(
            21,
            bootstrap.BYTES,
            _STATE_BYTES - _MASK + 1,
            (
                body.table(_INPUT_PADDING_TABLE, _STATE_BYTES - _MASK + 1),
                body.constant(64, 0),
            ),
        )
        zero_tail = body.add(
            3,
            bootstrap.BYTES,
            65,
            (
                padding,
                body.constant(64, 0),
                body.constant(64, 65),
            ),
        )
        state = body.add(4, bootstrap.BYTES, 256, (1, zero_tail))
        state = body.add(
            22,
            bootstrap.BYTES,
            256,
            (state,),
            auxiliary=encoder_zero_id,
            immediate=65,
        )
        state = body.add(
            22,
            bootstrap.BYTES,
            256,
            (state,),
            auxiliary=encoder_data_id,
            immediate=191,
        )
        encoded = body.add(
            3,
            bootstrap.BYTES,
            255,
            (
                state,
                body.constant(64, 0),
                body.constant(64, 255),
            ),
        )
        success = body.add(24, bootstrap.STATUS, 16)
        body.add(5, bootstrap.STATUS, 16, (success,), auxiliary=1)
        body.add(5, bootstrap.STATUS, 16, (encoded,), auxiliary=2)

    generated_encoder_id = package.recipe(
        encoder_inputs, encoder_outputs, encoder_main, 256, 108
    )
    if generated_encoder_id != 108:
        raise AssertionError("encoder helper identity")
    table_records = _tables()
    tables = b"".join(table_records)
    records = b"".join(package.records)
    package_bytes = 64 + len(tables) + len(records)
    total_nodes = sum(package.node_counts)
    total_edges = sum(package.edge_counts)
    table_payload_bytes = sum(
        int.from_bytes(record[12:16], "big") for record in table_records
    )
    maximum_steps = max(value[0] for value in package.resources.values())
    maximum_peak = max(value[1] for value in package.resources.values())
    header = b"".join(
        (
            b"GBRECP0\0",
            bytes(4),
            _be(profile_version, 2),
            bytes(2),
            _be(len(package.records), 2),
            _be(len(table_records), 2),
            _be(total_nodes, 4),
            _be(total_edges, 4),
            _be(table_payload_bytes, 4),
            _be(package_bytes, 4),
            _be(maximum_steps, 8),
            _be(maximum_peak, 4),
            bytes(16),
        )
    )
    raw = header + tables + records
    parsed = bootstrap.decode_recipe_package(raw, profile_version)
    if not any(recipe.recipe_id == final_recipe_id for recipe in parsed.recipes):
        raise AssertionError("final recipe identity")
    return raw


def execute_rs_decoder_recipe(
    profile_version: int, observed: bytes, erasures: tuple[int, ...]
) -> bootstrap.RecipeResult:
    raw = build_rs_decoder_recipe(profile_version)
    package = bootstrap.decode_recipe_package(raw, profile_version)
    inputs = prepare_rs_decoder_input(observed, erasures)
    return bootstrap.evaluate_recipe(package, 30, inputs)


@lru_cache(maxsize=2)
def rs_decoder_recipe_contract(profile_version: int) -> DecoderRecipeContract:
    raw = build_rs_decoder_recipe(profile_version)
    common = bootstrap.encode_common_block(
        bootstrap.CommonBlock(
            profile_version,
            9,
            0,
            3,
            0,
            0,
            1,
            157,
            bytes(range(157)),
        )
    )
    encoded = rs255_191_encode(common)
    damaged = bytearray(encoded)
    damaged[254] ^= 0x53
    worked_input = prepare_rs_decoder_input(encoded, ())
    held_input = prepare_rs_decoder_input(bytes(damaged), ())
    expected = bytes(2) + common
    return DecoderRecipeContract(
        profile_version,
        "rs255-191-v0",
        "crc32c-v0" if profile_version == 5 else "crc64-ecma-v0",
        raw,
        sha256(raw).hexdigest(),
        len(raw),
        30,
        (
            (bootstrap.BYTES, 255),
            (bootstrap.BYTES, 1),
            (bootstrap.BYTES, 64),
        ),
        ((bootstrap.STATUS, 16), (bootstrap.BYTES, 191)),
        _tables(),
        worked_input,
        expected,
        held_input,
        expected,
    )


@lru_cache(maxsize=2)
def rs_transport_recipe_contract(
    profile_version: int,
) -> TransportRecipeContract:
    if profile_version not in (5, 6):
        raise ValueError("profile_version")
    raw = build_rs_decoder_recipe(profile_version)
    worked = bootstrap.encode_common_block(
        bootstrap.CommonBlock(
            profile_version,
            8,
            0,
            3,
            0,
            0,
            1,
            157,
            bytes(157),
        )
    )
    held = bootstrap.encode_common_block(
        bootstrap.CommonBlock(
            profile_version,
            8,
            0,
            3,
            0,
            0,
            1,
            157,
            bytes((73 * index + 41) & 0xFF for index in range(157)),
        )
    )
    worked_observation = bytearray(rs255_191_encode(worked))
    worked_observation[0] ^= 0x53
    held_observation = bytearray(rs255_191_encode(held))
    held_observation[254] ^= 0x53
    return TransportRecipeContract(
        profile_version,
        "rs255-191-v0",
        "crc32c-v0" if profile_version == 5 else "crc64-ecma-v0",
        raw,
        sha256(raw).hexdigest(),
        len(raw),
        (30, 108),
        108,
        ((bootstrap.BYTES, 191),),
        ((bootstrap.BYTES, 255),),
        30,
        (
            (bootstrap.BYTES, 255),
            (bootstrap.BYTES, 1),
            (bootstrap.BYTES, 64),
        ),
        ((bootstrap.BYTES, 191),),
        worked,
        bytes(worked_observation),
        prepare_rs_decoder_input(bytes(worked_observation), ()),
        b"\0\0" + worked,
        held,
        bytes(held_observation),
        prepare_rs_decoder_input(bytes(held_observation), ()),
        b"\0\0" + held,
    )


_RS_RECIPIENT_PACKAGES = {
    5: "2dd94f23f63bd4fbeb8d56565a9cc9a7e0a2054d3483e364cfb60e7751058e91",
    6: "1c05a1f57394d292487f46561492619358fe2d12e42e3a20194d5917f351e555",
}
_RS_RECIPIENT_RECIPE_IDS = (
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
)
_RS_CORPUS_SHA256 = "d4dcc0cc441f42c66dc19d6db636733fc577751baf073dc7f951cd3c3dd23f72"


def smoke_rs_decoder_manifestation(
    profile_version: int, raw: bytes
) -> RsManifestationAdmission:
    """Cheap parser/identity smoke preserving the known closure-first failure."""

    expected_sha256 = _RS_RECIPIENT_PACKAGES.get(profile_version)
    if expected_sha256 is None or type(raw) is not bytes:
        raise ValueError("rs-manifestation-profile")
    if len(raw) != 32_302 or sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("rs-manifestation-identity")
    package = bootstrap.decode_recipe_package(raw, profile_version)
    if tuple(
        recipe.recipe_id for recipe in package.recipes
    ) != _RS_RECIPIENT_RECIPE_IDS or (
        package.total_node_count,
        package.total_edge_count,
        package.table_payload_bytes,
        package.maximum_primitive_steps,
        package.peak_live_scratch_bytes,
    ) != (865, 1_231, 2_306, 1_698_049, 7_688):
        raise ValueError("rs-manifestation-shape")
    invalid_common = rs255_191_encode(bytes(range(191)))
    direct = rs255_191_decode(invalid_common, (), profile_version)
    recipe = bootstrap.evaluate_recipe(package, 30, (invalid_common, b"\0", bytes(64)))
    if direct.status != 6 or direct.decoded is not None:
        raise ValueError("rs-manifestation-smoke-oracle")
    if recipe.status == 6 and not recipe.outputs:
        raise ValueError("rs-manifestation-identity-stale")
    return RsManifestationAdmission(
        profile_version,
        expected_sha256,
        len(raw),
        package.total_node_count,
        package.total_edge_count,
        package.table_payload_bytes,
        package.maximum_primitive_steps,
        package.peak_live_scratch_bytes,
        _RS_CORPUS_SHA256,
        ("invalid-common-local-check",),
        ("invalid-common-local-check",),
        False,
        "incomplete_rs_recovery_recipe",
        False,
    )


def audit_rs_decoder_manifestation(
    profile_version: int, raw: bytes, corpus_raw: bytes
) -> RsManifestationAdmission:
    """Cross-check the exact Rust RS decoder manifestation in the Python VM.

    This returns a result when the hash-bound manifestation fails recipe
    closure.  Later size/step measurements remain diagnostics and the one
    failed DAG is never promoted into a lower bound over other recipe DAGs.
    """

    expected_sha256 = _RS_RECIPIENT_PACKAGES.get(profile_version)
    if expected_sha256 is None or type(raw) is not bytes:
        raise ValueError("rs-manifestation-profile")
    if len(raw) != 32_302 or sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("rs-manifestation-identity")
    if (
        type(corpus_raw) is not bytes
        or sha256(corpus_raw).hexdigest() != _RS_CORPUS_SHA256
    ):
        raise ValueError("rs-manifestation-corpus-identity")
    package = bootstrap.decode_recipe_package(raw, profile_version)
    if tuple(
        recipe.recipe_id for recipe in package.recipes
    ) != _RS_RECIPIENT_RECIPE_IDS or (
        package.total_node_count,
        package.total_edge_count,
        package.table_payload_bytes,
        package.maximum_primitive_steps,
        package.peak_live_scratch_bytes,
    ) != (865, 1_231, 2_306, 1_698_049, 7_688):
        raise ValueError("rs-manifestation-shape")
    corpus = json.loads(corpus_raw)
    if corpus.get("schema") != "golden-board.rs255-191-v0-fixtures/v0":
        raise ValueError("rs-manifestation-corpus-schema")
    encoded = {
        row["id"]: bytes.fromhex(row["codeword_hex"]) for row in corpus["encode_kats"]
    }
    ascending = bytes(range(191))
    ascending_codeword = rs255_191_encode(ascending)
    probes: list[tuple[str, bytes, tuple[int, ...], int, bytes | None, bool]] = [
        ("clean-algebra", ascending_codeword, (), 0, ascending, False),
        (
            "invalid-common-local-check",
            ascending_codeword,
            (),
            6,
            None,
            True,
        ),
    ]
    erased = bytearray(ascending_codeword)
    erased[190] = 0xA5
    probes.append(("single-erasure", bytes(erased), (190,), 0, ascending, False))
    erased[0] ^= 0x53
    probes.append(("mixed-one-one", bytes(erased), (190,), 0, ascending, False))
    for row in corpus["decode_kats"]:
        status = row["expected_status"]
        expected = encoded[row["expected_codeword_id"]][:191] if status == 0 else None
        probes.append(
            (
                row["id"],
                bytes.fromhex(row["observation_hex"]),
                tuple(row["erasure_positions"]),
                status,
                expected,
                False,
            )
        )

    checked: list[str] = []
    mismatched: list[str] = []
    for (
        case_id,
        observation,
        erasures,
        expected_status,
        expected_data,
        require_local_check,
    ) in probes:
        direct = rs255_191_decode(
            observation,
            erasures,
            profile_version if require_local_check else None,
        )
        if direct.status != expected_status or direct.decoded != expected_data:
            raise ValueError(f"rs-manifestation-oracle:{case_id}")
        if len(erasures) <= 64:
            count = len(erasures)
            positions = bytes(erasures) + bytes(64 - len(erasures))
        else:
            count = 65
            positions = b"\xff" + bytes(63)
        result = bootstrap.evaluate_recipe(
            package, 30, (observation, bytes((count,)), positions)
        )
        expected_outputs = (expected_data,) if expected_data is not None else ()
        if result.status != expected_status or result.outputs != expected_outputs:
            mismatched.append(case_id)
        checked.append(case_id)

    return RsManifestationAdmission(
        profile_version,
        expected_sha256,
        len(raw),
        package.total_node_count,
        package.total_edge_count,
        package.table_payload_bytes,
        package.maximum_primitive_steps,
        package.peak_live_scratch_bytes,
        _RS_CORPUS_SHA256,
        tuple(checked),
        tuple(mismatched),
        not mismatched,
        "" if not mismatched else "incomplete_rs_recovery_recipe",
        False,
    )


_EH_STATE_BYTES = 31
_EH_COUNT = 9
_EH_POSITIONS = 10
_EH_SYNDROME = 13
_EH_FOUND_COUNT = 14
_EH_FOUND_FILL = 15
_EH_FOUND_CHANGE = 16
_EH_PREVIOUS = 17
_EH_SYNDROME_TABLE = 10
_EH_COLUMN_TABLE = 11
_EH_CLEAR_MASK_TABLE = 12
_EH_BIT_MASK_TABLE = 13
_EH_DECODE_TABLE = 14
_EH_IDENTITY_TABLE = 15
_EH_ZERO_TABLE = 16


def _table_record(
    table_id: int,
    value_type: int,
    width: int,
    count: int,
    payload: bytes,
) -> bytes:
    return b"".join(
        (
            _be(table_id, 2),
            bytes((value_type, 0)),
            _be(width, 4),
            _be(count, 4),
            _be(len(payload), 4),
            payload,
        )
    )


@lru_cache(maxsize=1)
def _eh_decoder_tables() -> tuple[bytes, ...]:
    syndrome_rows = []
    for byte_ordinal in range(9):
        for value in range(256):
            syndrome = 0
            for bit in range(8):
                if value & (1 << (7 - bit)):
                    position = byte_ordinal * 8 + bit + 1
                    syndrome ^= 0x80 | (position if position <= 71 else 0)
            syndrome_rows.append(syndrome)
    columns = bytes(
        0x80 | (position if position <= 71 else 0) for position in range(1, 73)
    )
    clear_masks = bytes(0xFF ^ (1 << (7 - bit)) for bit in range(8))
    bit_masks = bytes(1 << (7 - bit) for bit in range(8))
    decoded_rows = []
    parity_positions = {1, 2, 4, 8, 16, 32, 64, 72}
    for nibble_ordinal in range(18):
        for nibble_value in range(16):
            bits = [0] * 72
            for offset in range(4):
                bits[nibble_ordinal * 4 + offset] = (nibble_value >> (3 - offset)) & 1
            data_bits = tuple(
                bits[position - 1]
                for position in range(1, 73)
                if position not in parity_positions
            )
            decoded_rows.append(_bits_to_bytes(data_bits))
    return (
        _table_record(
            _EH_SYNDROME_TABLE,
            bootstrap.UINT,
            8,
            len(syndrome_rows),
            bytes(syndrome_rows),
        ),
        _table_record(_EH_COLUMN_TABLE, bootstrap.UINT, 8, 72, columns),
        _table_record(_EH_CLEAR_MASK_TABLE, bootstrap.UINT, 8, 8, clear_masks),
        _table_record(_EH_BIT_MASK_TABLE, bootstrap.UINT, 8, 8, bit_masks),
        _table_record(
            _EH_DECODE_TABLE,
            bootstrap.UINT,
            64,
            len(decoded_rows),
            b"".join(decoded_rows),
        ),
        _table_record(
            _EH_IDENTITY_TABLE,
            bootstrap.UINT,
            8,
            256,
            bytes(range(256)),
        ),
        _table_record(_EH_ZERO_TABLE, bootstrap.BYTES, 18, 1, bytes(18)),
    )


def _finish_package(
    profile_version: int, package: _Package, table_records: tuple[bytes, ...]
) -> bytes:
    tables = b"".join(table_records)
    records = b"".join(package.records)
    package_bytes = 64 + len(tables) + len(records)
    header = b"".join(
        (
            b"GBRECP0\0",
            bytes(4),
            _be(profile_version, 2),
            bytes(2),
            _be(len(package.records), 2),
            _be(len(table_records), 2),
            _be(sum(package.node_counts), 4),
            _be(sum(package.edge_counts), 4),
            _be(
                sum(int.from_bytes(record[12:16], "big") for record in table_records),
                4,
            ),
            _be(package_bytes, 4),
            _be(max(value[0] for value in package.resources.values()), 8),
            _be(max(value[1] for value in package.resources.values()), 4),
            bytes(16),
        )
    )
    raw = header + tables + records
    bootstrap.decode_recipe_package(raw, profile_version)
    return raw


@lru_cache(maxsize=4)
def build_eh72_decoder_recipe(profile_version: int) -> bytes:
    if profile_version not in (1, 2, 3, 4):
        raise ValueError("profile_version")
    package = _Package(profile_version)
    state_inputs = (
        (bootstrap.BYTES, _EH_STATE_BYTES),
        (bootstrap.UINT, 64),
    )
    state_outputs = (
        (bootstrap.STATUS, 16),
        (bootstrap.BYTES, _EH_STATE_BYTES),
    )

    def narrow(body: _Body, value: int) -> int:
        return body.add(
            21,
            bootstrap.UINT,
            8,
            (body.table(_EH_IDENTITY_TABLE, 8), value),
        )

    def precheck(body: _Body) -> None:
        count = body.load(1, body.constant(64, _EH_COUNT))
        valid = body.less(count, body.constant(8, 4))
        state = body.store(
            1,
            body.constant(64, _EH_FOUND_CHANGE),
            body.constant(8, 255),
        )
        status = body.select(
            valid,
            body.add(24, bootstrap.STATUS, 16),
            body.add(25, bootstrap.STATUS, 16, immediate=4),
            bootstrap.STATUS,
            16,
        )
        body.finish(state, status)

    precheck_id = package.recipe(
        state_inputs, state_outputs, precheck, _EH_STATE_BYTES, 1
    )

    def normalize(body: _Body) -> None:
        count = body.load(1, body.constant(64, _EH_COUNT))
        ordinal = narrow(body, 2)
        active = body.less(ordinal, count)
        position = body.load(1, body.index(_EH_POSITIONS, 2))
        positive = body.less(body.constant(8, 0), position)
        in_range = body.bool_and(positive, body.less(position, body.constant(8, 73)))
        first = body.equal(ordinal, body.constant(8, 0))
        previous = body.load(1, body.constant(64, _EH_PREVIOUS))
        increasing = body.less(previous, position)
        ordered = body.select(
            first,
            body.add(1, bootstrap.BOOL, 1, immediate=1),
            increasing,
            bootstrap.BOOL,
            1,
        )
        active_valid = body.bool_and(in_range, ordered)
        padding_valid = body.equal(position, body.constant(8, 0))
        valid = body.select(active, active_valid, padding_valid, bootstrap.BOOL, 1)
        safe_position = body.select(
            in_range, position, body.constant(8, 1), bootstrap.UINT, 8
        )
        bit_position = body.add(
            7, bootstrap.UINT, 8, (safe_position, body.constant(8, 1))
        )
        byte_index = body.add(
            9,
            bootstrap.UINT,
            8,
            (bit_position, body.constant(8, 8)),
        )
        bit_index = body.add(
            10,
            bootstrap.UINT,
            8,
            (bit_position, body.constant(8, 8)),
        )
        current = body.load(1, byte_index)
        clear_mask = body.add(
            21,
            bootstrap.UINT,
            8,
            (body.table(_EH_CLEAR_MASK_TABLE, 8), bit_index),
        )
        cleared = body.add(11, bootstrap.UINT, 8, (current, clear_mask))
        selected = body.select(active, cleared, current, bootstrap.UINT, 8)
        state = body.store(1, byte_index, selected)
        retained = body.select(active, position, previous, bootstrap.UINT, 8)
        state = body.store(state, body.constant(64, _EH_PREVIOUS), retained)
        status = body.select(
            valid,
            body.add(24, bootstrap.STATUS, 16),
            body.add(25, bootstrap.STATUS, 16, immediate=3),
            bootstrap.STATUS,
            16,
        )
        body.finish(state, status)

    normalize_id = package.recipe(
        state_inputs, state_outputs, normalize, _EH_STATE_BYTES, 2
    )

    def syndrome_step(body: _Body) -> None:
        byte_value = body.load(1, 2)
        base = body.add(
            8,
            bootstrap.UINT,
            64,
            (2, body.constant(64, 256)),
        )
        index = body.add(
            6,
            bootstrap.UINT,
            64,
            (base, body.widen(byte_value)),
        )
        contribution = body.add(
            21,
            bootstrap.UINT,
            8,
            (body.table(_EH_SYNDROME_TABLE, 8), index),
        )
        current = body.load(1, body.constant(64, _EH_SYNDROME))
        updated = body.add(13, bootstrap.UINT, 8, (current, contribution))
        state = body.store(1, body.constant(64, _EH_SYNDROME), updated)
        body.finish(state)

    syndrome_id = package.recipe(
        state_inputs, state_outputs, syndrome_step, _EH_STATE_BYTES, 3
    )

    def construction(body: _Body) -> None:
        count = body.load(1, body.constant(64, _EH_COUNT))
        is_zero = body.equal(count, body.constant(8, 0))
        is_one = body.equal(count, body.constant(8, 1))
        is_two = body.equal(count, body.constant(8, 2))
        is_three = body.equal(count, body.constant(8, 3))
        active_zero = body.bool_and(is_zero, body.less(2, body.constant(64, 73)))
        active_two = body.bool_and(is_two, body.less(2, body.constant(64, 4)))
        active_three = body.bool_and(is_three, body.less(2, body.constant(64, 8)))
        active = body.bool_or(
            active_zero,
            body.bool_or(is_one, body.bool_or(active_two, active_three)),
        )
        rank = body.add(
            10,
            bootstrap.UINT,
            64,
            (2, body.constant(64, 72)),
        )
        nonzero_ordinal = body.less(body.constant(64, 0), 2)
        safe_ordinal = body.select(
            nonzero_ordinal, 2, body.constant(64, 1), bootstrap.UINT, 64
        )
        zero_change = body.add(
            7,
            bootstrap.UINT,
            64,
            (safe_ordinal, body.constant(64, 1)),
        )
        nonzero_rank = body.less(body.constant(64, 0), rank)
        safe_rank = body.select(
            nonzero_rank, rank, body.constant(64, 1), bootstrap.UINT, 64
        )
        one_raw = body.add(7, bootstrap.UINT, 64, (safe_rank, body.constant(64, 1)))
        first_erasure = body.load(1, body.constant(64, _EH_POSITIONS))
        safe_first_erasure = body.select(
            is_one,
            first_erasure,
            body.constant(8, 1),
            bootstrap.UINT,
            8,
        )
        first_erasure_index = body.add(
            7,
            bootstrap.UINT,
            8,
            (safe_first_erasure, body.constant(8, 1)),
        )
        before_erasure = body.less(one_raw, body.widen(first_erasure_index))
        one_change = body.select(
            before_erasure,
            one_raw,
            body.add(6, bootstrap.UINT, 64, (one_raw, body.constant(64, 1))),
            bootstrap.UINT,
            64,
        )
        change_position = body.select(
            is_one, one_change, zero_change, bootstrap.UINT, 64
        )
        safe_change_position = body.select(
            active,
            change_position,
            body.constant(64, 0),
            bootstrap.UINT,
            64,
        )
        has_change = body.bool_or(
            body.bool_and(is_zero, nonzero_ordinal),
            body.bool_and(is_one, nonzero_rank),
        )
        one_fill = body.add(
            9,
            bootstrap.UINT,
            64,
            (2, body.constant(64, 72)),
        )
        fill = body.select(
            is_one,
            one_fill,
            body.select(
                body.bool_or(is_two, is_three),
                2,
                body.constant(64, 0),
                bootstrap.UINT,
                64,
            ),
            bootstrap.UINT,
            64,
        )
        candidate = body.load(1, body.constant(64, _EH_SYNDROME))
        for slot in range(3):
            position = body.load(1, body.constant(64, _EH_POSITIONS + slot))
            slot_active = body.less(body.constant(8, slot), count)
            safe_position = body.select(
                slot_active,
                position,
                body.constant(8, 1),
                bootstrap.UINT,
                8,
            )
            position_index = body.add(
                7,
                bootstrap.UINT,
                8,
                (safe_position, body.constant(8, 1)),
            )
            column = body.add(
                21,
                bootstrap.UINT,
                8,
                (body.table(_EH_COLUMN_TABLE, 8), position_index),
            )
            shifted = (
                fill
                if slot == 0
                else body.add(
                    16,
                    bootstrap.UINT,
                    64,
                    (fill, body.constant(64, slot)),
                )
            )
            bit = body.add(14, bootstrap.UINT, 64, (shifted,), immediate=1)
            filled = body.equal(bit, body.constant(64, 1))
            include = body.bool_and(slot_active, filled)
            contribution = body.select(
                include, column, body.constant(8, 0), bootstrap.UINT, 8
            )
            candidate = body.add(13, bootstrap.UINT, 8, (candidate, contribution))
        change_column = body.add(
            21,
            bootstrap.UINT,
            8,
            (body.table(_EH_COLUMN_TABLE, 8), safe_change_position),
        )
        candidate = body.add(
            13,
            bootstrap.UINT,
            8,
            (
                candidate,
                body.select(
                    has_change,
                    change_column,
                    body.constant(8, 0),
                    bootstrap.UINT,
                    8,
                ),
            ),
        )
        valid = body.bool_and(active, body.equal(candidate, body.constant(8, 0)))
        found = body.load(1, body.constant(64, _EH_FOUND_COUNT))
        updated_count = body.add(6, bootstrap.UINT, 8, (found, body.constant(8, 1)))
        state = body.store(
            1,
            body.constant(64, _EH_FOUND_COUNT),
            body.select(valid, updated_count, found, bootstrap.UINT, 8),
        )
        fill_byte = narrow(body, fill)
        old_fill = body.load(state, body.constant(64, _EH_FOUND_FILL))
        state = body.store(
            state,
            body.constant(64, _EH_FOUND_FILL),
            body.select(valid, fill_byte, old_fill, bootstrap.UINT, 8),
        )
        change_byte = narrow(body, change_position)
        selected_change = body.select(
            has_change,
            change_byte,
            body.constant(8, 255),
            bootstrap.UINT,
            8,
        )
        old_change = body.load(state, body.constant(64, _EH_FOUND_CHANGE))
        state = body.store(
            state,
            body.constant(64, _EH_FOUND_CHANGE),
            body.select(valid, selected_change, old_change, bootstrap.UINT, 8),
        )
        body.finish(state)

    construction_id = package.recipe(
        state_inputs, state_outputs, construction, _EH_STATE_BYTES, 4
    )

    def candidate_check(body: _Body) -> None:
        count = body.load(1, body.constant(64, _EH_FOUND_COUNT))
        unique = body.equal(count, body.constant(8, 1))
        invariant = body.less(count, body.constant(8, 2))
        failure = body.select(
            invariant,
            body.add(25, bootstrap.STATUS, 16, immediate=5),
            body.add(25, bootstrap.STATUS, 16, immediate=11),
            bootstrap.STATUS,
            16,
        )
        status = body.select(
            unique,
            body.add(24, bootstrap.STATUS, 16),
            failure,
            bootstrap.STATUS,
            16,
        )
        body.finish(1, status)

    check_id = package.recipe(
        state_inputs, state_outputs, candidate_check, _EH_STATE_BYTES, 5
    )

    def apply_erasure(body: _Body) -> None:
        count = body.load(1, body.constant(64, _EH_COUNT))
        ordinal = narrow(body, 2)
        active = body.less(ordinal, count)
        position = body.load(1, body.index(_EH_POSITIONS, 2))
        safe_position = body.select(
            active,
            position,
            body.constant(8, 1),
            bootstrap.UINT,
            8,
        )
        bit_position = body.add(
            7,
            bootstrap.UINT,
            8,
            (safe_position, body.constant(8, 1)),
        )
        byte_index = body.add(9, bootstrap.UINT, 8, (bit_position, body.constant(8, 8)))
        bit_index = body.add(10, bootstrap.UINT, 8, (bit_position, body.constant(8, 8)))
        mask = body.add(
            21,
            bootstrap.UINT,
            8,
            (body.table(_EH_BIT_MASK_TABLE, 8), bit_index),
        )
        fill = body.load(1, body.constant(64, _EH_FOUND_FILL))
        shifted = body.add(16, bootstrap.UINT, 8, (fill, ordinal))
        bit = body.add(14, bootstrap.UINT, 8, (shifted,), immediate=1)
        set_bit = body.equal(bit, body.constant(8, 1))
        include = body.bool_and(active, set_bit)
        current = body.load(1, byte_index)
        filled = body.add(12, bootstrap.UINT, 8, (current, mask))
        state = body.store(
            1,
            byte_index,
            body.select(include, filled, current, bootstrap.UINT, 8),
        )
        body.finish(state)

    apply_id = package.recipe(
        state_inputs, state_outputs, apply_erasure, _EH_STATE_BYTES, 6
    )

    main_inputs = (
        (bootstrap.BYTES, 9),
        (bootstrap.BYTES, 1),
        (bootstrap.BYTES, 3),
    )
    main_outputs = (
        (bootstrap.STATUS, 16),
        (bootstrap.BYTES, 8),
    )

    def main(body: _Body) -> None:
        zero = body.add(
            21,
            bootstrap.BYTES,
            18,
            (body.table(_EH_ZERO_TABLE, 18), body.constant(64, 0)),
        )
        state = body.add(4, bootstrap.BYTES, 10, (1, 2))
        state = body.add(4, bootstrap.BYTES, 13, (state, 3))
        state = body.add(4, bootstrap.BYTES, _EH_STATE_BYTES, (state, zero))
        for recipe_id, count in (
            (precheck_id, 1),
            (normalize_id, 3),
            (syndrome_id, 9),
            (construction_id, 144),
            (check_id, 1),
            (apply_id, 3),
        ):
            state = body.add(
                22,
                bootstrap.BYTES,
                _EH_STATE_BYTES,
                (state,),
                auxiliary=recipe_id,
                immediate=count,
            )
        change = body.load(state, body.constant(64, _EH_FOUND_CHANGE))
        has_change = body.less(change, body.constant(8, 72))
        safe_change = body.select(
            has_change, change, body.constant(8, 0), bootstrap.UINT, 8
        )
        byte_index = body.add(9, bootstrap.UINT, 8, (safe_change, body.constant(8, 8)))
        bit_index = body.add(10, bootstrap.UINT, 8, (safe_change, body.constant(8, 8)))
        mask = body.add(
            21,
            bootstrap.UINT,
            8,
            (body.table(_EH_BIT_MASK_TABLE, 8), bit_index),
        )
        current = body.load(state, byte_index)
        changed = body.add(13, bootstrap.UINT, 8, (current, mask))
        state = body.store(
            state,
            byte_index,
            body.select(has_change, changed, current, bootstrap.UINT, 8),
        )
        decoded = body.constant(64, 0)
        for ordinal in range(18):
            byte_value = body.load(state, body.constant(64, ordinal // 2))
            nibble = (
                body.add(
                    16,
                    bootstrap.UINT,
                    8,
                    (byte_value, body.constant(8, 4)),
                )
                if ordinal % 2 == 0
                else body.add(14, bootstrap.UINT, 8, (byte_value,), immediate=0x0F)
            )
            index = body.add(
                6,
                bootstrap.UINT,
                64,
                (
                    body.constant(64, ordinal * 16),
                    body.widen(nibble),
                ),
            )
            contribution = body.add(
                21,
                bootstrap.UINT,
                64,
                (body.table(_EH_DECODE_TABLE, 64), index),
            )
            decoded = body.add(13, bootstrap.UINT, 64, (decoded, contribution))
        output = body.add(
            3,
            bootstrap.BYTES,
            8,
            (zero, body.constant(64, 0), body.constant(64, 8)),
        )
        for index in range(8):
            shift = (7 - index) * 8
            shifted = (
                decoded
                if shift == 0
                else body.add(
                    16,
                    bootstrap.UINT,
                    64,
                    (decoded, body.constant(64, shift)),
                )
            )
            masked = body.add(14, bootstrap.UINT, 64, (shifted,), immediate=0xFF)
            value = body.add(
                21,
                bootstrap.UINT,
                8,
                (body.table(_EH_IDENTITY_TABLE, 8), masked),
            )
            output = body.add(
                20,
                bootstrap.BYTES,
                8,
                (output, body.constant(64, index), value),
            )
        success = body.add(24, bootstrap.STATUS, 16)
        body.add(5, bootstrap.STATUS, 16, (success,), auxiliary=1)
        body.add(5, bootstrap.STATUS, 16, (output,), auxiliary=2)

    package.recipe(
        main_inputs,
        main_outputs,
        main,
        _EH_STATE_BYTES,
        30,
    )
    return _finish_package(profile_version, package, _eh_decoder_tables())


_EH_RECIPIENT_PACKAGES = {
    1: (
        24_786,
        "f030732cd966fd9570149f6fd2d1befb5eed66319eb248b609693e868f977941",
        "crc32c-v0",
    ),
    2: (
        26_738,
        "cce1758613d7f10278533409e07103ae15162972fcf30030e17c233e39664011",
        "crc64-ecma-v0",
    ),
    3: (
        24_786,
        "8c91ba74f9bbed97aed89191e8d8d30a9a0c4d32bd5ac98b63a4c19ed71fb0e7",
        "crc32c-v0",
    ),
    4: (
        26_738,
        "de237fcd9d53581710404bd8b00152cb68f50adef48e715fdd4572e786bae4b8",
        "crc64-ecma-v0",
    ),
}
_EH_RECIPIENT_RECIPE_IDS = (
    1,
    2,
    3,
    4,
    30,
    90,
    92,
    99,
    100,
    101,
    102,
    103,
    104,
    105,
    106,
    107,
    108,
    109,
    110,
    111,
    112,
)
_ROUTE_EXPORTS = (30, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112)


def _eh_decoder_inputs(
    observed: bytes, erasures: tuple[int, ...]
) -> tuple[bytes, bytes, bytes]:
    if (
        type(observed) is not bytes
        or len(observed) != 9
        or type(erasures) is not tuple
        or len(erasures) > 3
        or any(
            type(position) is not int or not 1 <= position <= 72
            for position in erasures
        )
        or any(left >= right for left, right in zip(erasures, erasures[1:]))
    ):
        raise ValueError("eh-recipient-input")
    return (
        observed,
        bytes((len(erasures),)),
        bytes(erasures) + bytes(3 - len(erasures)),
    )


def smoke_eh72_transport_recipe(profile_version: int, raw: bytes) -> str:
    """Cheap identity/parser/route-entry smoke for one canonical EH package."""

    expected = _EH_RECIPIENT_PACKAGES.get(profile_version)
    if expected is None or type(raw) is not bytes:
        raise ValueError("eh-recipient-profile")
    expected_bytes, expected_sha256, _ = expected
    if len(raw) != expected_bytes or sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("eh-recipient-identity")
    package = bootstrap.decode_recipe_package(raw, profile_version)
    if (
        tuple(recipe.recipe_id for recipe in package.recipes)
        != _EH_RECIPIENT_RECIPE_IDS
    ):
        raise ValueError("eh-recipient-recipes")
    source = bytes.fromhex("0123456789abcdef")
    codeword = eh72_encode(source)
    encoded = bootstrap.evaluate_recipe(package, 108, (source,))
    observation = bytearray(codeword)
    observation[8] ^= 1
    decoded = bootstrap.evaluate_recipe(
        package, 30, _eh_decoder_inputs(bytes(observation), ())
    )
    if (
        encoded.status != 0
        or encoded.outputs != (codeword,)
        or decoded.status != 0
        or decoded.outputs != (source,)
    ):
        raise ValueError("eh-recipient-smoke")
    return expected_sha256


def _require_common_export_behavior(
    package: bootstrap.RecipePackage, profile_version: int
) -> None:
    def evaluate(
        recipe_id: int,
        inputs: tuple[bytes, ...],
        outputs: tuple[bytes, ...],
        status: int = 0,
    ) -> None:
        result = bootstrap.evaluate_recipe(package, recipe_id, inputs)
        if result.status != status or result.outputs != outputs:
            raise ValueError(f"eh-recipient-export:{recipe_id}")

    for value in (0, 0xA5, 0xFF):
        evaluate(101, (bytes((value,)),), (bytes((value ^ 0xFF,)),))

    side, row, column = 11, 2, 7
    last = side - 1
    coordinates = (
        (row, column),
        (last - column, row),
        (last - row, last - column),
        (column, last - row),
        (row, last - column),
        (last - column, last - row),
        (last - row, column),
        (column, row),
    )
    for transform, (mapped_row, mapped_column) in enumerate(coordinates):
        for polarity in (0, 1):
            for observed in (0, 1):
                evaluate(
                    102,
                    (
                        bytes((transform,)),
                        bytes((polarity,)),
                        row.to_bytes(2, "big"),
                        column.to_bytes(2, "big"),
                        side.to_bytes(2, "big"),
                        bytes((observed,)),
                    ),
                    (
                        (mapped_row * side + mapped_column).to_bytes(4, "big"),
                        bytes((polarity ^ observed,)),
                    ),
                )
    evaluate(
        102,
        (b"\0", b"\0", b"\0\x0b", b"\0\0", b"\0\x0b", b"\0"),
        (),
        3,
    )

    for left, right in ((0, 1), (1, 1), (0xFFFF, 0)):
        evaluate(
            103,
            (left.to_bytes(2, "big"), right.to_bytes(2, "big")),
            (bytes((left < right,)),),
        )
    evaluate(
        104,
        (b"\0\x11", b"\0\x05", b"\0\x80"),
        ((17 * 128 + 5).to_bytes(4, "big"),),
    )
    evaluate(105, ((0x123456).to_bytes(4, "big"),), ((0x123457).to_bytes(4, "big"),))
    for status in range(12):
        evaluate(106, (bytes((status,)),), (bytes((status == 0,)),))

    check_input = bytes.fromhex("a55a00ffc33c96690f")
    evaluate(
        107,
        (check_input,),
        (bootstrap.crc32c_v0(check_input).to_bytes(4, "big"),),
    )

    for logical, side, shell_width in (
        (987_654_321, 100, 10),
        (0xF2345678, 17, 3),
    ):
        interior = side - 2 * shell_width
        population = interior * interior
        reduced = logical % population
        scaled = (
            population + 2 * (reduced % interior) * interior - reduced
        ) % population
        offset = (40_503 * profile_version + shell_width * 257) % population
        expected = (scaled + offset) % population
        evaluate(
            109,
            (
                logical.to_bytes(4, "big"),
                side.to_bytes(2, "big"),
                shell_width.to_bytes(2, "big"),
            ),
            (expected.to_bytes(4, "big"),),
        )
    for side, shell_width in ((0, 0), (17, 17), (17, 18), (2049, 1)):
        evaluate(
            109,
            (
                b"\0\0\0\1",
                side.to_bytes(2, "big"),
                shell_width.to_bytes(2, "big"),
            ),
            (),
            3,
        )

    evaluate(
        110,
        (b"\x12\x34\x56\x78", b"\x9a\xbc"),
        (b"\x12\x34\x56\x78\x9a\xbc",),
    )
    check_width = 64 if profile_version in (2, 4, 6) else 32
    check = (
        bootstrap.crc64_ecma_v0(check_input)
        if check_width == 64
        else bootstrap.crc32c_v0(check_input)
    )
    evaluate(111, (check_input,), (check.to_bytes(check_width // 8, "big"),))
    for expected_count, available_count, valid, expected in (
        (1, 0, 1, 1),
        (0xFFFF, 0xFFFE, 1, 1),
        (0, 0xFFFF, 1, 0),
        (2, 1, 0, 0),
    ):
        evaluate(
            112,
            (
                expected_count.to_bytes(2, "big"),
                available_count.to_bytes(2, "big"),
                bytes((valid,)),
            ),
            (bytes((expected,)),),
        )


def admit_eh72_transport_recipe(
    profile_version: int, raw: bytes
) -> TransportRecipeContract:
    """Admit one hash-bound shared EH recipient package.

    The bytes are emitted by the independent Rust package compiler and passed
    in explicitly (normally through its bounded temporary-file example).  This
    lane independently parses and executes both route-bound transport entries;
    no generated package blob is tracked in the repository.
    """

    expected = _EH_RECIPIENT_PACKAGES.get(profile_version)
    if expected is None or type(raw) is not bytes:
        raise ValueError("eh-recipient-profile")
    expected_bytes, expected_sha256, check_id = expected
    if len(raw) != expected_bytes or sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("eh-recipient-identity")
    package = bootstrap.decode_recipe_package(raw, profile_version)
    if (
        tuple(recipe.recipe_id for recipe in package.recipes)
        != _EH_RECIPIENT_RECIPE_IDS
    ):
        raise ValueError("eh-recipient-recipes")
    _require_common_export_behavior(package, profile_version)

    worked_source = bytes(8)
    held_source = bytes.fromhex("0123456789abcdef")
    worked_observation = bytearray(eh72_encode(worked_source))
    worked_observation[0] ^= 0x80
    held_observation = bytearray(eh72_encode(held_source))
    held_observation[8] ^= 0x01
    encoder_kats = (
        (bytes(8), bytes(9)),
        (
            bytes.fromhex("8000000000000000"),
            bytes.fromhex("e00000000000000001"),
        ),
        (
            bytes.fromhex("0123456789abcdef"),
            bytes.fromhex("11121a2a9e26af36de"),
        ),
        (bytes((0xFF,)) * 8, bytes((0xFF,)) * 9),
    )
    for source, expected_codeword in encoder_kats:
        direct_codeword = eh72_encode(source)
        encoded = bootstrap.evaluate_recipe(package, 108, (source,))
        if (
            direct_codeword != expected_codeword
            or encoded.status != 0
            or encoded.outputs != (expected_codeword,)
        ):
            raise ValueError("eh-recipient-encoder")
    for source, observation in (
        (worked_source, bytes(worked_observation)),
        (held_source, bytes(held_observation)),
    ):
        decoded = bootstrap.evaluate_recipe(
            package, 30, _eh_decoder_inputs(observation, ())
        )
        direct = eh72_decode(observation)
        if (
            decoded.status != 0
            or decoded.outputs != (source,)
            or direct.decoded != decoded.outputs[0]
        ):
            raise ValueError("eh-recipient-decoder")

    held_codeword = eh72_encode(held_source)

    def flip_bits(*positions: int) -> bytes:
        observation = bytearray(held_codeword)
        for position in positions:
            observation[position // 8] ^= 1 << (7 - position % 8)
        return bytes(observation)

    def require_recovery(
        observation: bytes, erasures: tuple[int, ...], label: str
    ) -> None:
        decoded = bootstrap.evaluate_recipe(
            package, 30, _eh_decoder_inputs(observation, erasures)
        )
        direct = eh72_decode(observation, erasures)
        if (
            decoded.status != 0
            or decoded.outputs != (held_source,)
            or direct.decoded != decoded.outputs[0]
        ):
            raise ValueError(f"eh-recipient-recovery:{label}")

    for position in range(72):
        require_recovery(flip_bits(position), (), f"error:{position + 1}")
        require_recovery(
            flip_bits(position), (position + 1,), f"erasure:{position + 1}"
        )
        require_recovery(
            flip_bits(position, (position + 1) % 72),
            (position + 1,),
            f"mixed:{position + 1}",
        )
    require_recovery(flip_bits(0, 1), (1, 2), "two-erasures")
    require_recovery(flip_bits(0, 1, 2), (1, 2, 3), "three-erasures")

    for label, count, positions in (
        ("too-many", 4, bytes(3)),
        ("duplicate", 2, b"\x01\x01\x00"),
        ("zero", 1, bytes(3)),
        ("past-end", 1, b"\x49\x00\x00"),
    ):
        rejected = bootstrap.evaluate_recipe(
            package, 30, (held_codeword, bytes((count,)), positions)
        )
        if rejected.status != 3 or rejected.outputs:
            raise ValueError(f"eh-recipient-parameter:{label}")

    for label, erased_bits, error_bits, erasures in (
        ("s0", (), (0, 1), ()),
        ("s1", (0,), (7, 63), (1,)),
        ("s2", (0, 1), (2,), (1, 2)),
        ("s3", (0, 1, 2), (3,), (1, 2, 3)),
    ):
        observation = flip_bits(*(erased_bits + error_bits))
        direct = eh72_decode(observation, erasures)
        rejected = bootstrap.evaluate_recipe(
            package, 30, _eh_decoder_inputs(observation, erasures)
        )
        if direct.decoded is not None or rejected.status != 5 or rejected.outputs:
            raise ValueError(f"eh-recipient-one-beyond:{label}")

    return TransportRecipeContract(
        profile_version,
        "eh72-replicated-v0",
        check_id,
        raw,
        expected_sha256,
        expected_bytes,
        _ROUTE_EXPORTS,
        108,
        ((bootstrap.BYTES, 8),),
        ((bootstrap.BYTES, 9),),
        30,
        (
            (bootstrap.BYTES, 9),
            (bootstrap.BYTES, 1),
            (bootstrap.BYTES, 3),
        ),
        ((bootstrap.BYTES, 8),),
        worked_source,
        bytes(worked_observation),
        _eh_decoder_inputs(bytes(worked_observation), ()),
        b"\0\0" + worked_source,
        held_source,
        bytes(held_observation),
        _eh_decoder_inputs(bytes(held_observation), ()),
        b"\0\0" + held_source,
    )


# The canonical EH recipient packages are generated here independently from
# the frozen generic-VM grammar.  They deliberately do not splice records or
# tables out of a Rust artifact: every descriptor, node, resource total, and
# table byte is rendered by the Python implementation below.  Profiles 1--4
# use the legacy table set, while profile 7 adds the slot-multiplier table and
# repetition recipe.
_R3_STATE_BYTES = 1_536
_R3_TABLE_WIDEN = 3
_R3_TABLE_ZERO_BYTE = 4
_R3_TABLE_BYTE_IDENTITY = 5
_R3_TABLE_EH_CODE_BYTE = 10
_R3_TABLE_EH_CODE_SHIFT = 11
_R3_TABLE_EH_POSITION = 12
_R3_TABLE_EH_DATA_ACTIVE = 13
_R3_TABLE_EH_DATA_BYTE = 14
_R3_TABLE_EH_DATA_SHIFT = 15
_R3_TABLE_SLOT_MULTIPLIER = 17
_R3_TABLE_EH_FILL_LIMIT = 18
_R3_TABLE_BITS_NOT_MASK = 19
_R3_TABLE_D4_FLAGS = 20

_R3_EH_POSITIONS = 9
_R3_EH_SYNDROME = 12
_R3_EH_PARITY = 13
_R3_EH_COUNT = 14
_R3_EH_FOUND_COUNT = 15
_R3_EH_CHOSEN_FILL = 16
_R3_EH_CHOSEN_FLIP = 17
_R3_EH_OUTPUT = 18
_R3_CRC_VALUE = 32
_R3_CRC_BYTE = 40
_R3_CRC_MODE = 41


class _R3Body:
    """One deterministic recipe builder for a frozen EH package."""

    def __init__(
        self,
        recipe_id: int,
        inputs: tuple[tuple[int, int], ...],
        outputs: tuple[tuple[int, int], ...],
    ) -> None:
        self.recipe_id = recipe_id
        self.inputs = inputs
        self.outputs = outputs
        self.nodes: list[tuple[int, int, int, tuple[int, ...], int, int]] = []
        self._tables: dict[int, int] = {}
        self._constants: dict[tuple[int, int, int], int] = {}
        self._statuses: dict[int, int] = {}

    @classmethod
    def state_body(cls, recipe_id: int) -> _R3Body:
        return cls(
            recipe_id,
            ((bootstrap.BYTES, _R3_STATE_BYTES), (bootstrap.UINT, 64)),
            ((bootstrap.STATUS, 16), (bootstrap.BYTES, _R3_STATE_BYTES)),
        )

    def add(
        self,
        opcode: int,
        value_type: int,
        width: int,
        arguments: tuple[int, ...] = (),
        auxiliary: int = 0,
        immediate: int = 0,
    ) -> int:
        self.nodes.append((opcode, value_type, width, arguments, auxiliary, immediate))
        return len(self.inputs) + len(self.nodes)

    def constant(self, value_type: int, width: int, value: int) -> int:
        key = (value_type, width, value)
        if key not in self._constants:
            self._constants[key] = self.add(1, value_type, width, immediate=value)
        return self._constants[key]

    def uint(self, width: int, value: int) -> int:
        return self.constant(bootstrap.UINT, width, value)

    def boolean(self, value: bool) -> int:
        return self.constant(bootstrap.BOOL, 1, int(value))

    def status(self, value: int) -> int:
        if value not in self._statuses:
            self._statuses[value] = self.add(
                24 if value == 0 else 25,
                bootstrap.STATUS,
                16,
                immediate=value,
            )
        return self._statuses[value]

    def binary(
        self, opcode: int, value_type: int, width: int, left: int, right: int
    ) -> int:
        return self.add(opcode, value_type, width, (left, right))

    def select(
        self,
        value_type: int,
        width: int,
        condition: int,
        yes: int,
        no: int,
    ) -> int:
        return self.add(23, value_type, width, (condition, yes, no))

    def equal(self, left: int, right: int) -> int:
        return self.add(17, bootstrap.BOOL, 1, (left, right))

    def less(self, left: int, right: int) -> int:
        return self.add(18, bootstrap.BOOL, 1, (left, right))

    def bool_and(self, left: int, right: int) -> int:
        return self.select(bootstrap.BOOL, 1, left, right, self.boolean(False))

    def bool_or(self, left: int, right: int) -> int:
        return self.select(bootstrap.BOOL, 1, left, self.boolean(True), right)

    def bool_not(self, value: int) -> int:
        return self.equal(value, self.boolean(False))

    def less_or_equal(self, left: int, right: int) -> int:
        return self.bool_not(self.less(right, left))

    def table(self, table_id: int, width: int) -> int:
        if table_id not in self._tables:
            self._tables[table_id] = self.add(
                2, bootstrap.TABLE, width, auxiliary=table_id
            )
        return self._tables[table_id]

    def widen(self, value: int) -> int:
        return self.add(
            21,
            bootstrap.UINT,
            16,
            (self.table(_R3_TABLE_WIDEN, 16), value),
        )

    def iteration_byte(self) -> int:
        return self.add(
            21,
            bootstrap.UINT,
            8,
            (self.table(_R3_TABLE_BYTE_IDENTITY, 8), 2),
        )

    def fixed_index(self, offset: int) -> int:
        return self.uint(16, offset)

    def offset_index(self, offset: int, value: int) -> int:
        widened = self.widen(value)
        base = self.uint(16, offset)
        return self.binary(6, bootstrap.UINT, 16, base, widened)

    def iteration_index(self, offset: int) -> int:
        if offset == 0:
            return 2
        return self.binary(6, bootstrap.UINT, 64, self.uint(64, offset), 2)

    def read(self, state: int, index: int) -> int:
        return self.add(19, bootstrap.UINT, 8, (state, index))

    def read_fixed(self, state: int, offset: int) -> int:
        return self.read(state, self.fixed_index(offset))

    def read_offset(self, state: int, offset: int, value: int) -> int:
        return self.read(state, self.offset_index(offset, value))

    def read_iteration(self, state: int, offset: int) -> int:
        return self.read(state, self.iteration_index(offset))

    def write(self, state: int, index: int, value: int) -> int:
        return self.add(
            20,
            bootstrap.BYTES,
            _R3_STATE_BYTES,
            (state, index, value),
        )

    def write_fixed(self, state: int, offset: int, value: int) -> int:
        return self.write(state, self.fixed_index(offset), value)

    def write_offset(self, state: int, offset: int, index: int, value: int) -> int:
        return self.write(state, self.offset_index(offset, index), value)

    def read_uint(self, state: int, offset: int, byte_count: int) -> int:
        value = self.read_fixed(state, offset)
        width = 8
        for index in range(1, byte_count):
            following = self.read_fixed(state, offset + index)
            width += 8
            value = self.add(4, bootstrap.UINT, width, (value, following))
        return value

    def write_uint(self, state: int, offset: int, byte_count: int, value: int) -> int:
        width = byte_count * 8
        identity = self.table(_R3_TABLE_BYTE_IDENTITY, 8)
        for index in range(byte_count):
            shift_amount = (byte_count - index - 1) * 8
            shifted = value
            if shift_amount:
                shifted = self.binary(
                    16,
                    bootstrap.UINT,
                    width,
                    value,
                    self.uint(width, shift_amount),
                )
            masked = self.add(14, bootstrap.UINT, width, (shifted,), immediate=0xFF)
            byte = self.add(21, bootstrap.UINT, 8, (identity, masked))
            state = self.write_fixed(state, offset + index, byte)
        return state

    def iterate(self, state: int, body: int, count: int) -> int:
        return self.add(
            22,
            bootstrap.BYTES,
            _R3_STATE_BYTES,
            (state,),
            auxiliary=body,
            immediate=count,
        )

    def zero_bytes(self, length: int) -> int:
        table = self.table(_R3_TABLE_ZERO_BYTE, 1)
        zero = self.uint(8, 0)
        first = self.add(21, bootstrap.BYTES, 1, (table, zero))
        powers = [(1, first)]
        while powers[-1][0] <= length // 2:
            width, value = powers[-1]
            powers.append(
                (
                    width * 2,
                    self.add(4, bootstrap.BYTES, width * 2, (value, value)),
                )
            )
        remaining = length
        output: int | None = None
        for width, value in reversed(powers):
            if width <= remaining:
                output = (
                    value
                    if output is None
                    else self.add(
                        4,
                        bootstrap.BYTES,
                        length - remaining + width,
                        (output, value),
                    )
                )
                remaining -= width
        if remaining or output is None:
            raise AssertionError("r3-zero-bytes")
        return output

    def finish_body(self, status: int, state: int) -> None:
        self.add(5, bootstrap.STATUS, 16, (status,), auxiliary=1)
        self.add(5, bootstrap.STATUS, 16, (state,), auxiliary=2)

    def finish_outputs(self, status: int, outputs: tuple[int, ...]) -> None:
        self.add(5, bootstrap.STATUS, 16, (status,), auxiliary=1)
        for slot, output in enumerate(outputs, 2):
            self.add(5, bootstrap.STATUS, 16, (output,), auxiliary=slot)


def _r3_gcd(left: int, right: int) -> int:
    while right:
        left, right = right, left % right
    return left


def _r3_toroidal_separation(delta: int, side: int) -> int:
    return min(delta, side - delta)


def _r3_slot_multiplier_valid(candidate: int, interior: int) -> bool:
    population = interior * interior
    slots = population // 1_728
    if slots < 2 or _r3_gcd(candidate, slots) != 1:
        return False
    window = max(32, interior // 8)
    cell_multiplier = 2 * interior - 1
    for lane_delta in range(1, 5):
        wrapped = candidate * lane_delta % slots
        for delta in (wrapped, wrapped - slots):
            flat = cell_multiplier * 1_728 * delta % population
            row, column = divmod(flat, interior)
            column_separation = _r3_toroidal_separation(column, interior)
            row_cases = (row,) if column == 0 else (row, (row + 1) % interior)
            for row_delta in row_cases:
                if (
                    max(
                        _r3_toroidal_separation(row_delta, interior),
                        column_separation,
                    )
                    < window
                ):
                    return False
    return True


@lru_cache(maxsize=1)
def r3_slot_multiplier_table() -> bytes:
    """Return independently generated TABLE17 payload bytes."""

    result = bytearray(256)
    for index in range(1, 255):
        interior = index * 8
        slots = interior * interior // 1_728
        if slots < 2:
            continue
        for candidate in range(1, slots):
            if _r3_slot_multiplier_valid(candidate, interior):
                if candidate > 255:
                    raise AssertionError("r3-slot-multiplier-width")
                result[index] = candidate
                break
    return bytes(result)


def _r3_eh_tables(*, include_slot_multiplier: bool = True) -> tuple[bytes, ...]:
    data_active = []
    data_bytes = []
    data_shifts = []
    data_bit = 0
    for position in range(1, 73):
        is_data = position <= 71 and position & (position - 1) != 0
        data_active.append(int(is_data))
        data_bytes.append(data_bit // 8 if is_data else 0)
        data_shifts.append(7 - data_bit % 8 if is_data else 0)
        if is_data:
            data_bit += 1
    if data_bit != 64:
        raise AssertionError("r3-eh-data-bits")
    tables = [
        (
            _R3_TABLE_WIDEN,
            bootstrap.UINT,
            16,
            256,
            b"".join(_be(value, 2) for value in range(256)),
        ),
        (_R3_TABLE_ZERO_BYTE, bootstrap.BYTES, 1, 1, b"\0"),
        (_R3_TABLE_BYTE_IDENTITY, bootstrap.UINT, 8, 256, bytes(range(256))),
        (
            _R3_TABLE_EH_CODE_BYTE,
            bootstrap.UINT,
            8,
            72,
            bytes(index // 8 for index in range(72)),
        ),
        (
            _R3_TABLE_EH_CODE_SHIFT,
            bootstrap.UINT,
            8,
            72,
            bytes(7 - index % 8 for index in range(72)),
        ),
        (
            _R3_TABLE_EH_POSITION,
            bootstrap.UINT,
            8,
            72,
            bytes(0 if position == 72 else position for position in range(1, 73)),
        ),
        (_R3_TABLE_EH_DATA_ACTIVE, bootstrap.UINT, 8, 72, bytes(data_active)),
        (_R3_TABLE_EH_DATA_BYTE, bootstrap.UINT, 8, 72, bytes(data_bytes)),
        (_R3_TABLE_EH_DATA_SHIFT, bootstrap.UINT, 8, 72, bytes(data_shifts)),
        (_R3_TABLE_EH_FILL_LIMIT, bootstrap.UINT, 8, 4, bytes((1, 2, 4, 8))),
        (_R3_TABLE_BITS_NOT_MASK, bootstrap.BITS, 8, 1, b"\xff"),
        (_R3_TABLE_D4_FLAGS, bootstrap.UINT, 8, 8, bytes((0, 3, 6, 5, 4, 7, 2, 1))),
    ]
    if include_slot_multiplier:
        tables.append(
            (
                _R3_TABLE_SLOT_MULTIPLIER,
                bootstrap.UINT,
                8,
                256,
                r3_slot_multiplier_table(),
            )
        )
        tables.sort(key=lambda row: row[0])
    return tuple(
        b"".join(
            (
                _be(table_id, 2),
                bytes((value_type, 0)),
                _be(width, 4),
                _be(count, 4),
                _be(len(payload), 4),
                payload,
            )
        )
        for table_id, value_type, width, count, payload in tables
    )


def _r3_eh_scan() -> _R3Body:
    body = _R3Body.state_body(1)
    state = 1
    byte_table = body.table(_R3_TABLE_EH_CODE_BYTE, 8)
    byte_index = body.add(21, bootstrap.UINT, 8, (byte_table, 2))
    byte = body.read(state, byte_index)
    shift_table = body.table(_R3_TABLE_EH_CODE_SHIFT, 8)
    shift = body.add(21, bootstrap.UINT, 8, (shift_table, 2))
    shifted = body.binary(16, bootstrap.UINT, 8, byte, shift)
    bit = body.add(14, bootstrap.UINT, 8, (shifted,), immediate=1)
    position_table = body.table(_R3_TABLE_EH_POSITION, 8)
    position = body.add(21, bootstrap.UINT, 8, (position_table, 2))
    zero = body.uint(8, 0)
    one = body.uint(8, 1)
    set_bit = body.equal(bit, one)
    contribution = body.select(bootstrap.UINT, 8, set_bit, position, zero)
    syndrome = body.read_fixed(state, _R3_EH_SYNDROME)
    syndrome = body.binary(13, bootstrap.UINT, 8, syndrome, contribution)
    state = body.write_fixed(state, _R3_EH_SYNDROME, syndrome)
    parity = body.read_fixed(state, _R3_EH_PARITY)
    parity = body.binary(13, bootstrap.UINT, 8, parity, bit)
    state = body.write_fixed(state, _R3_EH_PARITY, parity)
    body.finish_body(body.status(0), state)
    return body


def _r3_eh_validate() -> _R3Body:
    body = _R3Body.state_body(2)
    state = 1
    index = body.iteration_byte()
    count = body.read_fixed(state, _R3_EH_COUNT)
    count_valid = body.less(count, body.uint(8, 4))
    active = body.less(index, count)
    position = body.read_iteration(state, _R3_EH_POSITIONS)
    zero = body.uint(8, 0)
    seventy_three = body.uint(8, 73)
    above_zero = body.less(zero, position)
    below_limit = body.less(position, seventy_three)
    in_range = body.bool_and(above_zero, below_limit)
    padding = body.equal(position, zero)
    position_valid = body.select(bootstrap.BOOL, 1, active, in_range, padding)
    index_zero = body.equal(index, zero)
    one = body.uint(8, 1)
    safe_index = body.select(bootstrap.UINT, 8, index_zero, one, index)
    previous_index = body.binary(7, bootstrap.UINT, 8, safe_index, one)
    previous = body.read_offset(state, _R3_EH_POSITIONS, previous_index)
    ordered = body.less(previous, position)
    truth = body.boolean(True)
    ordered = body.select(bootstrap.BOOL, 1, index_zero, truth, ordered)
    ordered = body.select(bootstrap.BOOL, 1, active, ordered, truth)
    valid = body.bool_and(count_valid, position_valid)
    valid = body.bool_and(valid, ordered)
    status = body.select(
        bootstrap.STATUS,
        16,
        valid,
        body.status(0),
        body.status(3),
    )
    body.finish_body(status, state)
    return body


def _r3_eh_candidate() -> _R3Body:
    body = _R3Body.state_body(3)
    state = 1
    divisor = body.uint(64, 73)
    fill_index = body.binary(9, bootstrap.UINT, 64, 2, divisor)
    flip_index = body.binary(10, bootstrap.UINT, 64, 2, divisor)
    identity = body.table(_R3_TABLE_BYTE_IDENTITY, 8)
    fill = body.add(21, bootstrap.UINT, 8, (identity, fill_index))
    flip = body.add(21, bootstrap.UINT, 8, (identity, flip_index))
    count = body.read_fixed(state, _R3_EH_COUNT)
    limit_table = body.table(_R3_TABLE_EH_FILL_LIMIT, 8)
    fill_limit = body.add(21, bootstrap.UINT, 8, (limit_table, count))
    fill_valid = body.less(fill, fill_limit)
    zero = body.uint(8, 0)
    one = body.uint(8, 1)
    two = body.uint(8, 2)
    may_flip = body.less(count, two)
    flip_zero = body.equal(flip, zero)
    flip_valid = body.bool_or(may_flip, flip_zero)

    syndrome = body.read_fixed(state, _R3_EH_SYNDROME)
    parity = body.read_fixed(state, _R3_EH_PARITY)
    flip_is_erasure = body.boolean(False)
    for ordinal in range(3):
        ordinal_value = body.uint(8, ordinal)
        active = body.less(ordinal_value, count)
        position = body.read_fixed(state, _R3_EH_POSITIONS + ordinal)
        shifted = (
            fill
            if ordinal == 0
            else body.binary(16, bootstrap.UINT, 8, fill, body.uint(8, ordinal))
        )
        bit = body.add(14, bootstrap.UINT, 8, (shifted,), immediate=1)
        safe_position = body.select(bootstrap.UINT, 8, active, position, one)
        zero_based = body.binary(7, bootstrap.UINT, 8, safe_position, one)
        code_byte_table = body.table(_R3_TABLE_EH_CODE_BYTE, 8)
        code_byte = body.add(21, bootstrap.UINT, 8, (code_byte_table, zero_based))
        observed_byte = body.read(state, code_byte)
        code_shift_table = body.table(_R3_TABLE_EH_CODE_SHIFT, 8)
        code_shift = body.add(21, bootstrap.UINT, 8, (code_shift_table, zero_based))
        observed = body.binary(16, bootstrap.UINT, 8, observed_byte, code_shift)
        observed = body.add(14, bootstrap.UINT, 8, (observed,), immediate=1)
        delta = body.binary(13, bootstrap.UINT, 8, observed, bit)
        delta_set = body.equal(delta, one)
        contributes = body.bool_and(active, delta_set)
        position_table = body.table(_R3_TABLE_EH_POSITION, 8)
        syndrome_position = body.add(
            21, bootstrap.UINT, 8, (position_table, zero_based)
        )
        contribution = body.select(
            bootstrap.UINT, 8, contributes, syndrome_position, zero
        )
        syndrome = body.binary(13, bootstrap.UINT, 8, syndrome, contribution)
        parity_bit = body.select(bootstrap.UINT, 8, active, delta, zero)
        parity = body.binary(13, bootstrap.UINT, 8, parity, parity_bit)
        matches = body.equal(flip, position)
        matches = body.bool_and(active, matches)
        flip_is_erasure = body.bool_or(flip_is_erasure, matches)

    flip_nonzero = body.bool_not(flip_zero)
    flip_overall = body.equal(flip, body.uint(8, 72))
    not_overall = body.bool_not(flip_overall)
    flip_has_syndrome = body.bool_and(flip_nonzero, not_overall)
    flip_contribution = body.select(bootstrap.UINT, 8, flip_has_syndrome, flip, zero)
    syndrome = body.binary(13, bootstrap.UINT, 8, syndrome, flip_contribution)
    flip_parity = body.select(bootstrap.UINT, 8, flip_nonzero, one, zero)
    parity = body.binary(13, bootstrap.UINT, 8, parity, flip_parity)

    syndrome_zero = body.equal(syndrome, zero)
    parity_zero = body.equal(parity, zero)
    parity_valid = body.bool_and(syndrome_zero, parity_zero)
    no_erasure_flip = body.bool_not(flip_is_erasure)
    valid = body.bool_and(fill_valid, flip_valid)
    valid = body.bool_and(valid, no_erasure_flip)
    valid = body.bool_and(valid, parity_valid)
    found = body.read_fixed(state, _R3_EH_FOUND_COUNT)
    increment = body.select(bootstrap.UINT, 8, valid, one, zero)
    found = body.binary(6, bootstrap.UINT, 8, found, increment)
    state = body.write_fixed(state, _R3_EH_FOUND_COUNT, found)
    old_fill = body.read_fixed(state, _R3_EH_CHOSEN_FILL)
    chosen_fill = body.select(bootstrap.UINT, 8, valid, fill, old_fill)
    state = body.write_fixed(state, _R3_EH_CHOSEN_FILL, chosen_fill)
    old_flip = body.read_fixed(state, _R3_EH_CHOSEN_FLIP)
    chosen_flip = body.select(bootstrap.UINT, 8, valid, flip, old_flip)
    state = body.write_fixed(state, _R3_EH_CHOSEN_FLIP, chosen_flip)
    body.finish_body(body.status(0), state)
    return body


def _r3_eh_output() -> _R3Body:
    body = _R3Body.state_body(4)
    state = 1
    position_table = body.table(_R3_TABLE_EH_POSITION, 8)
    syndrome_position = body.add(21, bootstrap.UINT, 8, (position_table, 2))
    seventy_two = body.uint(8, 72)
    zero = body.uint(8, 0)
    is_overall = body.equal(syndrome_position, zero)
    position = body.select(
        bootstrap.UINT,
        8,
        is_overall,
        seventy_two,
        syndrome_position,
    )
    byte_table = body.table(_R3_TABLE_EH_CODE_BYTE, 8)
    byte_index = body.add(21, bootstrap.UINT, 8, (byte_table, 2))
    byte = body.read(state, byte_index)
    shift_table = body.table(_R3_TABLE_EH_CODE_SHIFT, 8)
    shift = body.add(21, bootstrap.UINT, 8, (shift_table, 2))
    shifted = body.binary(16, bootstrap.UINT, 8, byte, shift)
    bit = body.add(14, bootstrap.UINT, 8, (shifted,), immediate=1)
    count = body.read_fixed(state, _R3_EH_COUNT)
    fill = body.read_fixed(state, _R3_EH_CHOSEN_FILL)
    one = body.uint(8, 1)
    for ordinal in range(3):
        ordinal_value = body.uint(8, ordinal)
        active = body.less(ordinal_value, count)
        erased_position = body.read_fixed(state, _R3_EH_POSITIONS + ordinal)
        matches = body.equal(position, erased_position)
        matches = body.bool_and(active, matches)
        shifted_fill = (
            fill
            if ordinal == 0
            else body.binary(16, bootstrap.UINT, 8, fill, ordinal_value)
        )
        fill_bit = body.add(14, bootstrap.UINT, 8, (shifted_fill,), immediate=1)
        bit = body.select(bootstrap.UINT, 8, matches, fill_bit, bit)
    flip = body.read_fixed(state, _R3_EH_CHOSEN_FLIP)
    flip_here = body.equal(position, flip)
    flipped = body.binary(13, bootstrap.UINT, 8, bit, one)
    bit = body.select(bootstrap.UINT, 8, flip_here, flipped, bit)

    active_table = body.table(_R3_TABLE_EH_DATA_ACTIVE, 8)
    data_active = body.add(21, bootstrap.UINT, 8, (active_table, 2))
    data_active = body.equal(data_active, one)
    data_byte_table = body.table(_R3_TABLE_EH_DATA_BYTE, 8)
    data_byte = body.add(21, bootstrap.UINT, 8, (data_byte_table, 2))
    current = body.read_offset(state, _R3_EH_OUTPUT, data_byte)
    data_shift_table = body.table(_R3_TABLE_EH_DATA_SHIFT, 8)
    data_shift = body.add(21, bootstrap.UINT, 8, (data_shift_table, 2))
    placed = body.binary(15, bootstrap.UINT, 8, bit, data_shift)
    updated = body.binary(13, bootstrap.UINT, 8, current, placed)
    written = body.write_offset(state, _R3_EH_OUTPUT, data_byte, updated)
    state = body.select(bootstrap.BYTES, _R3_STATE_BYTES, data_active, written, state)
    body.finish_body(body.status(0), state)
    return body


def _r3_eh_decode() -> _R3Body:
    body = _R3Body(
        30,
        (
            (bootstrap.BYTES, 9),
            (bootstrap.BYTES, 1),
            (bootstrap.BYTES, 3),
        ),
        ((bootstrap.STATUS, 16), (bootstrap.BYTES, 8)),
    )
    prefix = body.add(4, bootstrap.BYTES, 12, (1, 3))
    zeros = body.zero_bytes(_R3_STATE_BYTES - 12)
    state = body.add(4, bootstrap.BYTES, _R3_STATE_BYTES, (prefix, zeros))
    zero16 = body.uint(16, 0)
    count = body.read(2, zero16)
    state = body.write_fixed(state, _R3_EH_COUNT, count)
    state = body.iterate(state, 2, 3)
    state = body.iterate(state, 1, 72)
    state = body.iterate(state, 3, 584)
    state = body.iterate(state, 4, 72)
    found = body.read_fixed(state, _R3_EH_FOUND_COUNT)
    unique = body.equal(found, body.uint(8, 1))
    start = body.uint(16, _R3_EH_OUTPUT)
    length = body.uint(16, 8)
    output = body.add(3, bootstrap.BYTES, 8, (state, start, length))
    status = body.select(
        bootstrap.STATUS,
        16,
        unique,
        body.status(0),
        body.status(5),
    )
    body.finish_outputs(status, (output,))
    return body


def _r3_eh_encode_step() -> _R3Body:
    body = _R3Body.state_body(100)
    state = 1
    one = body.uint(8, 1)
    active_table = body.table(_R3_TABLE_EH_DATA_ACTIVE, 8)
    active = body.add(21, bootstrap.UINT, 8, (active_table, 2))
    active = body.equal(active, one)
    data_byte_table = body.table(_R3_TABLE_EH_DATA_BYTE, 8)
    data_byte = body.add(21, bootstrap.UINT, 8, (data_byte_table, 2))
    byte = body.read(state, data_byte)
    data_shift_table = body.table(_R3_TABLE_EH_DATA_SHIFT, 8)
    data_shift = body.add(21, bootstrap.UINT, 8, (data_shift_table, 2))
    shifted = body.binary(16, bootstrap.UINT, 8, byte, data_shift)
    bit = body.add(14, bootstrap.UINT, 8, (shifted,), immediate=1)
    code_byte_table = body.table(_R3_TABLE_EH_CODE_BYTE, 8)
    code_byte = body.add(21, bootstrap.UINT, 8, (code_byte_table, 2))
    current = body.read_offset(state, _R3_EH_OUTPUT, code_byte)
    code_shift_table = body.table(_R3_TABLE_EH_CODE_SHIFT, 8)
    code_shift = body.add(21, bootstrap.UINT, 8, (code_shift_table, 2))
    placed = body.binary(15, bootstrap.UINT, 8, bit, code_shift)
    updated = body.binary(13, bootstrap.UINT, 8, current, placed)
    written = body.write_offset(state, _R3_EH_OUTPUT, code_byte, updated)
    state = body.select(bootstrap.BYTES, _R3_STATE_BYTES, active, written, state)
    position_table = body.table(_R3_TABLE_EH_POSITION, 8)
    position = body.add(21, bootstrap.UINT, 8, (position_table, 2))
    zero = body.uint(8, 0)
    bit_set = body.equal(bit, one)
    contributes = body.bool_and(active, bit_set)
    contribution = body.select(bootstrap.UINT, 8, contributes, position, zero)
    syndrome = body.read_fixed(state, _R3_EH_SYNDROME)
    syndrome = body.binary(13, bootstrap.UINT, 8, syndrome, contribution)
    state = body.write_fixed(state, _R3_EH_SYNDROME, syndrome)
    parity = body.read_fixed(state, _R3_EH_PARITY)
    selected_bit = body.select(bootstrap.UINT, 8, active, bit, zero)
    parity = body.binary(13, bootstrap.UINT, 8, parity, selected_bit)
    state = body.write_fixed(state, _R3_EH_PARITY, parity)
    body.finish_body(body.status(0), state)
    return body


def _r3_eh_parity_step() -> _R3Body:
    body = _R3Body.state_body(99)
    state = 1
    syndrome = body.read_fixed(state, _R3_EH_SYNDROME)
    shifted = body.binary(16, bootstrap.UINT, 8, syndrome, 2)
    bit = body.add(14, bootstrap.UINT, 8, (shifted,), immediate=1)
    one = body.uint(8, 1)
    position = body.binary(15, bootstrap.UINT, 8, one, 2)
    zero_based = body.binary(7, bootstrap.UINT, 8, position, one)
    byte_table = body.table(_R3_TABLE_EH_CODE_BYTE, 8)
    code_byte = body.add(21, bootstrap.UINT, 8, (byte_table, zero_based))
    output_base = body.uint(8, _R3_EH_OUTPUT)
    byte_index = body.binary(6, bootstrap.UINT, 8, output_base, code_byte)
    current = body.read(state, byte_index)
    shift_table = body.table(_R3_TABLE_EH_CODE_SHIFT, 8)
    code_shift = body.add(21, bootstrap.UINT, 8, (shift_table, zero_based))
    placed = body.binary(15, bootstrap.UINT, 8, bit, code_shift)
    updated = body.binary(13, bootstrap.UINT, 8, current, placed)
    state = body.write(state, byte_index, updated)
    parity_index = body.fixed_index(_R3_EH_PARITY)
    parity = body.read(state, parity_index)
    parity = body.binary(13, bootstrap.UINT, 8, parity, bit)
    state = body.write(state, parity_index, parity)
    body.finish_body(body.status(0), state)
    return body


def _r3_eh_encode() -> _R3Body:
    body = _R3Body(
        108,
        ((bootstrap.BYTES, 8),),
        ((bootstrap.STATUS, 16), (bootstrap.BYTES, 9)),
    )
    zeros = body.zero_bytes(_R3_STATE_BYTES - 8)
    state = body.add(4, bootstrap.BYTES, _R3_STATE_BYTES, (1, zeros))
    state = body.iterate(state, 100, 72)
    state = body.iterate(state, 99, 7)
    parity = body.read_fixed(state, _R3_EH_PARITY)
    overall_index = body.fixed_index(_R3_EH_OUTPUT + 8)
    overall = body.read(state, overall_index)
    overall = body.binary(13, bootstrap.UINT, 8, overall, parity)
    state = body.write(state, overall_index, overall)
    start = body.uint(16, _R3_EH_OUTPUT)
    length = body.uint(16, 9)
    output = body.add(3, bootstrap.BYTES, 9, (state, start, length))
    body.finish_outputs(body.status(0), (output,))
    return body


def _r3_crc32c_bit() -> _R3Body:
    body = _R3Body.state_body(90)
    state = 1
    crc = body.read_uint(state, _R3_CRC_VALUE, 4)
    byte = body.read_fixed(state, _R3_CRC_BYTE)
    iteration = body.iteration_byte()
    shifted = body.binary(16, bootstrap.UINT, 8, byte, iteration)
    bit = body.add(14, bootstrap.UINT, 8, (shifted,), immediate=1)
    bit_set = body.equal(bit, body.uint(8, 1))
    zero32 = body.uint(32, 0)
    one32 = body.uint(32, 1)
    bit = body.select(bootstrap.UINT, 32, bit_set, one32, zero32)
    low = body.add(14, bootstrap.UINT, 32, (crc,), immediate=1)
    mix = body.binary(13, bootstrap.UINT, 32, low, bit)
    mix = body.equal(mix, one32)
    shifted_crc = body.binary(16, bootstrap.UINT, 32, crc, one32)
    polynomial = body.uint(32, 0x82F63B78)
    reduction = body.select(bootstrap.UINT, 32, mix, polynomial, zero32)
    crc = body.binary(13, bootstrap.UINT, 32, shifted_crc, reduction)
    state = body.write_uint(state, _R3_CRC_VALUE, 4, crc)
    body.finish_body(body.status(0), state)
    return body


def _eh_combined_crc_bit() -> _R3Body:
    """Build the shared even-profile CRC-32C/CRC-64 bit procedure."""

    body = _R3Body.state_body(90)
    state = 1
    crc = body.read_uint(state, _R3_CRC_VALUE, 8)
    byte = body.read_fixed(state, _R3_CRC_BYTE)
    iteration = body.iteration_byte()
    one8 = body.uint(8, 1)
    zero64 = body.uint(64, 0)
    one64 = body.uint(64, 1)

    reflected = body.binary(16, bootstrap.UINT, 8, byte, iteration)
    reflected = body.add(14, bootstrap.UINT, 8, (reflected,), immediate=1)
    reflected_set = body.equal(reflected, one8)
    reflected = body.select(bootstrap.UINT, 64, reflected_set, one64, zero64)
    low = body.add(14, bootstrap.UINT, 64, (crc,), immediate=1)
    reflected_mix = body.binary(13, bootstrap.UINT, 64, low, reflected)
    reflected_mix = body.equal(reflected_mix, one64)
    reflected_shift = body.binary(16, bootstrap.UINT, 64, crc, one64)
    crc32_polynomial = body.uint(64, 0x82F63B78)
    crc32_reduction = body.select(
        bootstrap.UINT,
        64,
        reflected_mix,
        crc32_polynomial,
        zero64,
    )
    crc32 = body.binary(13, bootstrap.UINT, 64, reflected_shift, crc32_reduction)

    seven = body.uint(8, 7)
    bit_shift = body.binary(7, bootstrap.UINT, 8, seven, iteration)
    forward = body.binary(16, bootstrap.UINT, 8, byte, bit_shift)
    forward = body.add(14, bootstrap.UINT, 8, (forward,), immediate=1)
    forward_set = body.equal(forward, one8)
    forward = body.select(bootstrap.UINT, 64, forward_set, one64, zero64)
    top_shift = body.uint(64, 63)
    top = body.binary(16, bootstrap.UINT, 64, crc, top_shift)
    forward_mix = body.binary(13, bootstrap.UINT, 64, top, forward)
    forward_mix = body.equal(forward_mix, one64)
    masked = body.add(
        14,
        bootstrap.UINT,
        64,
        (crc,),
        immediate=0x7FFFFFFFFFFFFFFF,
    )
    forward_shift = body.binary(15, bootstrap.UINT, 64, masked, one64)
    crc64_polynomial = body.uint(64, 0x42F0E1EBA9EA3693)
    crc64_reduction = body.select(
        bootstrap.UINT,
        64,
        forward_mix,
        crc64_polynomial,
        zero64,
    )
    crc64 = body.binary(13, bootstrap.UINT, 64, forward_shift, crc64_reduction)

    mode = body.read_fixed(state, _R3_CRC_MODE)
    crc64_mode = body.equal(mode, one8)
    crc = body.select(bootstrap.UINT, 64, crc64_mode, crc64, crc32)
    state = body.write_uint(state, _R3_CRC_VALUE, 8, crc)
    body.finish_body(body.status(0), state)
    return body


def _r3_crc_byte() -> _R3Body:
    body = _R3Body.state_body(92)
    state = 1
    byte = body.read(state, 2)
    state = body.write_fixed(state, _R3_CRC_BYTE, byte)
    state = body.iterate(state, 90, 8)
    body.finish_body(body.status(0), state)
    return body


def _r3_crc_fact(recipe_id: int, width: int = 32, *, combined: bool = False) -> _R3Body:
    body = _R3Body(
        recipe_id,
        ((bootstrap.BYTES, 9),),
        ((bootstrap.STATUS, 16), (bootstrap.UINT, width)),
    )
    zeros = body.zero_bytes(_R3_STATE_BYTES - 9)
    state = body.add(4, bootstrap.BYTES, _R3_STATE_BYTES, (1, zeros))
    byte_count = 8 if combined else width // 8
    if width == 32:
        initial = body.uint(8, 0xFF)
        initial_start = 4 if combined else 0
        for index in range(initial_start, byte_count):
            state = body.write_fixed(state, _R3_CRC_VALUE + index, initial)
    if combined:
        state = body.write_fixed(state, _R3_CRC_MODE, body.uint(8, int(width == 64)))
    state = body.iterate(state, 92, 9)
    result_offset = _R3_CRC_VALUE + 4 if combined and width == 32 else _R3_CRC_VALUE
    crc = body.read_uint(state, result_offset, width // 8)
    if width == 32:
        crc = body.binary(
            13,
            bootstrap.UINT,
            32,
            crc,
            body.uint(32, 0xFFFFFFFF),
        )
    body.finish_outputs(body.status(0), (crc,))
    return body


def _r3_fact(recipe_id: int, profile_version: int = 7) -> _R3Body:
    if recipe_id == 101:
        body = _R3Body(
            recipe_id,
            ((bootstrap.BITS, 8),),
            ((bootstrap.STATUS, 16), (bootstrap.BITS, 8)),
        )
        table = body.table(_R3_TABLE_BITS_NOT_MASK, 8)
        zero = body.uint(8, 0)
        mask = body.add(21, bootstrap.BITS, 8, (table, zero))
        output = body.binary(13, bootstrap.BITS, 8, 1, mask)
        body.finish_outputs(body.status(0), (output,))
        return body
    if recipe_id == 102:
        body = _R3Body(
            recipe_id,
            (
                (bootstrap.UINT, 3),
                (bootstrap.BOOL, 1),
                (bootstrap.UINT, 16),
                (bootstrap.UINT, 16),
                (bootstrap.UINT, 16),
                (bootstrap.BOOL, 1),
            ),
            (
                (bootstrap.STATUS, 16),
                (bootstrap.UINT, 32),
                (bootstrap.BOOL, 1),
            ),
        )
        transform, polarity, row, column, side, observed = range(1, 7)
        zero16 = body.uint(16, 0)
        one16 = body.uint(16, 1)
        side_nonzero = body.less(zero16, side)
        safe_side = body.select(bootstrap.UINT, 16, side_nonzero, side, one16)
        last = body.binary(7, bootstrap.UINT, 16, safe_side, one16)
        row_valid = body.less(row, safe_side)
        column_valid = body.less(column, safe_side)
        safe_row = body.select(bootstrap.UINT, 16, row_valid, row, zero16)
        safe_column = body.select(bootstrap.UINT, 16, column_valid, column, zero16)
        flags_table = body.table(_R3_TABLE_D4_FLAGS, 8)
        flags = body.add(21, bootstrap.UINT, 8, (flags_table, transform))
        zero8 = body.uint(8, 0)
        swap_mask = body.add(14, bootstrap.UINT, 8, (flags,), immediate=1)
        swap = body.less(zero8, swap_mask)
        reverse_row_mask = body.add(14, bootstrap.UINT, 8, (flags,), immediate=2)
        reverse_row = body.less(zero8, reverse_row_mask)
        reverse_column_mask = body.add(14, bootstrap.UINT, 8, (flags,), immediate=4)
        reverse_column = body.less(zero8, reverse_column_mask)
        base_row = body.select(bootstrap.UINT, 16, swap, safe_column, safe_row)
        base_column = body.select(bootstrap.UINT, 16, swap, safe_row, safe_column)
        flipped_row = body.binary(7, bootstrap.UINT, 16, last, base_row)
        flipped_column = body.binary(7, bootstrap.UINT, 16, last, base_column)
        selected_row = body.select(
            bootstrap.UINT, 16, reverse_row, flipped_row, base_row
        )
        selected_column = body.select(
            bootstrap.UINT,
            16,
            reverse_column,
            flipped_column,
            base_column,
        )
        row32 = body.add(4, bootstrap.UINT, 32, (zero16, selected_row))
        column32 = body.add(4, bootstrap.UINT, 32, (zero16, selected_column))
        side32 = body.add(4, bootstrap.UINT, 32, (zero16, safe_side))
        product = body.binary(8, bootstrap.UINT, 32, row32, side32)
        flat = body.binary(6, bootstrap.UINT, 32, product, column32)
        same = body.equal(polarity, observed)
        false_value = body.boolean(False)
        normalized = body.equal(same, false_value)
        valid = body.select(bootstrap.BOOL, 1, side_nonzero, row_valid, false_value)
        valid = body.select(bootstrap.BOOL, 1, valid, column_valid, false_value)
        status = body.select(
            bootstrap.STATUS,
            16,
            valid,
            body.status(0),
            body.status(3),
        )
        body.finish_outputs(status, (flat, normalized))
        return body
    if recipe_id == 103:
        body = _R3Body(
            recipe_id,
            ((bootstrap.UINT, 16), (bootstrap.UINT, 16)),
            ((bootstrap.STATUS, 16), (bootstrap.BOOL, 1)),
        )
        output = body.less(1, 2)
        status = body.status(0)
        body.finish_outputs(status, (output,))
        return body
    if recipe_id == 104:
        body = _R3Body(
            recipe_id,
            ((bootstrap.UINT, 16),) * 3,
            ((bootstrap.STATUS, 16), (bootstrap.UINT, 32)),
        )
        zero = body.uint(16, 0)
        row = body.add(4, bootstrap.UINT, 32, (zero, 1))
        column = body.add(4, bootstrap.UINT, 32, (zero, 2))
        stride = body.add(4, bootstrap.UINT, 32, (zero, 3))
        product = body.binary(8, bootstrap.UINT, 32, row, stride)
        output = body.binary(6, bootstrap.UINT, 32, product, column)
        body.finish_outputs(body.status(0), (output,))
        return body
    if recipe_id == 105:
        body = _R3Body(
            recipe_id,
            ((bootstrap.UINT, 32),),
            ((bootstrap.STATUS, 16), (bootstrap.UINT, 32)),
        )
        output = body.binary(6, bootstrap.UINT, 32, 1, body.uint(32, 1))
        body.finish_outputs(body.status(0), (output,))
        return body
    if recipe_id == 106:
        body = _R3Body(
            recipe_id,
            ((bootstrap.UINT, 8),),
            ((bootstrap.STATUS, 16), (bootstrap.BOOL, 1)),
        )
        zero = body.uint(8, 0)
        output = body.equal(1, zero)
        status = body.status(0)
        body.finish_outputs(status, (output,))
        return body
    if recipe_id == 107:
        return _r3_crc_fact(107, 32, combined=profile_version % 2 == 0)
    if recipe_id == 109:
        body = _R3Body(
            recipe_id,
            (
                (bootstrap.UINT, 32),
                (bootstrap.UINT, 16),
                (bootstrap.UINT, 16),
            ),
            ((bootstrap.STATUS, 16), (bootstrap.UINT, 32)),
        )
        logical, side, shell_width = 1, 2, 3
        shell_below_side = body.less(shell_width, side)
        side_in_range = body.less(side, body.uint(16, 2_049))
        preliminary = body.bool_and(shell_below_side, side_in_range)
        safe_side = body.select(bootstrap.UINT, 16, preliminary, side, shell_width)
        after_first_shell = body.binary(7, bootstrap.UINT, 16, safe_side, shell_width)
        second_shell_below_side = body.less(shell_width, after_first_shell)
        valid = body.bool_and(preliminary, second_shell_below_side)
        safe_after_first_shell = body.select(
            bootstrap.UINT,
            16,
            valid,
            after_first_shell,
            shell_width,
        )
        interior16 = body.binary(
            7, bootstrap.UINT, 16, safe_after_first_shell, shell_width
        )
        zero16 = body.uint(16, 0)
        interior = body.add(4, bootstrap.UINT, 32, (zero16, interior16))
        population = body.binary(8, bootstrap.UINT, 32, interior, interior)
        zero32 = body.uint(32, 0)
        one32 = body.uint(32, 1)
        nonzero_population = body.less(zero32, population)
        safe_population = body.select(
            bootstrap.UINT,
            32,
            nonzero_population,
            population,
            one32,
        )
        safe_interior = body.select(
            bootstrap.UINT, 32, nonzero_population, interior, one32
        )
        reduced = body.binary(10, bootstrap.UINT, 32, logical, safe_population)
        remainder = body.binary(10, bootstrap.UINT, 32, reduced, safe_interior)
        scaled_once = body.binary(8, bootstrap.UINT, 32, safe_interior, remainder)
        scaled_twice = body.binary(8, bootstrap.UINT, 32, scaled_once, body.uint(32, 2))
        scaled = body.binary(10, bootstrap.UINT, 32, scaled_twice, safe_population)
        shifted = body.binary(6, bootstrap.UINT, 32, safe_population, scaled)
        difference = body.binary(7, bootstrap.UINT, 32, shifted, reduced)
        multiplied = body.binary(10, bootstrap.UINT, 32, difference, safe_population)
        width32 = body.add(4, bootstrap.UINT, 32, (zero16, shell_width))
        width_term = body.binary(8, bootstrap.UINT, 32, width32, body.uint(32, 257))
        profile_term = body.uint(32, 40_503 * profile_version)
        offset_sum = body.binary(6, bootstrap.UINT, 32, width_term, profile_term)
        offset = body.binary(10, bootstrap.UINT, 32, offset_sum, safe_population)
        added = body.binary(6, bootstrap.UINT, 32, multiplied, offset)
        output = body.binary(10, bootstrap.UINT, 32, added, safe_population)
        valid = body.select(bootstrap.BOOL, 1, valid, nonzero_population, valid)
        status = body.select(
            bootstrap.STATUS,
            16,
            valid,
            body.status(0),
            body.status(3),
        )
        body.finish_outputs(status, (output,))
        return body
    if recipe_id == 110:
        body = _R3Body(
            recipe_id,
            ((bootstrap.UINT, 32), (bootstrap.UINT, 16)),
            ((bootstrap.STATUS, 16), (bootstrap.UINT, 48)),
        )
        output = body.add(4, bootstrap.UINT, 48, (1, 2))
        body.finish_outputs(body.status(0), (output,))
        return body
    if recipe_id == 111:
        return _r3_crc_fact(
            111,
            32 if profile_version % 2 else 64,
            combined=profile_version % 2 == 0,
        )
    if recipe_id == 112:
        body = _R3Body(
            recipe_id,
            (
                (bootstrap.UINT, 16),
                (bootstrap.UINT, 16),
                (bootstrap.BOOL, 1),
            ),
            ((bootstrap.STATUS, 16), (bootstrap.BOOL, 1)),
        )
        maximum = body.uint(16, 0xFFFF)
        can_increment = body.less(2, maximum)
        zero = body.uint(16, 0)
        safe_value = body.select(bootstrap.UINT, 16, can_increment, 2, zero)
        one = body.uint(16, 1)
        following = body.binary(6, bootstrap.UINT, 16, safe_value, one)
        adjacent = body.equal(1, following)
        false_value = body.boolean(False)
        output = body.select(bootstrap.BOOL, 1, adjacent, 3, false_value)
        output = body.select(bootstrap.BOOL, 1, can_increment, output, false_value)
        body.finish_outputs(body.status(0), (output,))
        return body
    raise AssertionError("r3-fact-id")


def _r3_repetition_symbol() -> _R3Body:
    body = _R3Body(
        113,
        ((bootstrap.UINT, 8),) * 3,
        (
            (bootstrap.STATUS, 16),
            (bootstrap.BOOL, 1),
            (bootstrap.BOOL, 1),
        ),
    )
    factor, zero_count, one_count = 1, 2, 3
    two = body.uint(8, 2)
    five = body.uint(8, 5)
    factor_two = body.equal(factor, two)
    factor_five = body.equal(factor, five)
    factor_valid = body.bool_or(factor_two, factor_five)
    zero8 = body.uint(8, 0)
    factor16 = body.add(4, bootstrap.UINT, 16, (zero8, factor))
    zero16 = body.add(4, bootstrap.UINT, 16, (zero8, zero_count))
    one16 = body.add(4, bootstrap.UINT, 16, (zero8, one_count))
    total = body.binary(6, bootstrap.UINT, 16, zero16, one16)
    total_valid = body.less_or_equal(total, factor16)
    valid = body.bool_and(factor_valid, total_valid)
    output_zero = body.less(one_count, zero_count)
    output_one = body.less(zero_count, one_count)
    output_known = body.bool_or(output_zero, output_one)
    status = body.select(
        bootstrap.STATUS,
        16,
        valid,
        body.status(0),
        body.status(3),
    )
    body.finish_outputs(status, (output_known, output_one))
    return body


@dataclass(frozen=True, slots=True)
class R3RecipePackageMetrics:
    package_bytes: int
    package_sha256: str
    node_count: int
    edge_count: int
    table_payload_bytes: int
    maximum_primitive_steps: int
    peak_scratch_bytes: int
    repetition_recipe_bytes: int
    repetition_recipe_nodes: int


def _eh_recipient_recipe_bodies(
    profile_version: int,
) -> tuple[_R3Body, ...]:
    return (
        _r3_eh_scan(),
        _r3_eh_validate(),
        _r3_eh_candidate(),
        _r3_eh_output(),
        _r3_eh_decode(),
        _eh_combined_crc_bit() if profile_version % 2 == 0 else _r3_crc32c_bit(),
        _r3_crc_byte(),
        _r3_eh_parity_step(),
        _r3_eh_encode_step(),
        *(_r3_fact(recipe_id, profile_version) for recipe_id in range(101, 108)),
        _r3_eh_encode(),
        *(_r3_fact(recipe_id, profile_version) for recipe_id in range(109, 113)),
    )


def _r3_recipe_bodies() -> tuple[_R3Body, ...]:
    return (
        *_eh_recipient_recipe_bodies(7),
        _r3_repetition_symbol(),
    )


def _render_eh_recipe_package(
    profile_version: int,
    bodies: tuple[_R3Body, ...],
    tables: tuple[bytes, ...],
) -> bytes:
    resources: dict[int, tuple[int, int]] = {}
    records = []
    node_count = 0
    edge_count = 0
    for body in bodies:
        raw, edges, steps, peak = _recipe_record(
            body.recipe_id,
            body.inputs,
            body.outputs,
            body.nodes,
            resources,
        )
        records.append(raw)
        resources[body.recipe_id] = (steps, peak)
        node_count += len(body.nodes)
        edge_count += edges
    table_payload_bytes = sum(int.from_bytes(table[12:16], "big") for table in tables)
    package_bytes = 64 + sum(map(len, tables)) + sum(map(len, records))
    header = b"".join(
        (
            b"GBRECP0\0",
            bytes(4),
            _be(profile_version, 2),
            bytes(2),
            _be(len(records), 2),
            _be(len(tables), 2),
            _be(node_count, 4),
            _be(edge_count, 4),
            _be(table_payload_bytes, 4),
            _be(package_bytes, 4),
            _be(max(value[0] for value in resources.values()), 8),
            _be(max(value[1] for value in resources.values()), 4),
            bytes(16),
        )
    )
    raw = header + b"".join(tables) + b"".join(records)
    bootstrap.decode_recipe_package(raw, profile_version)
    return raw


@lru_cache(maxsize=4)
def build_eh_recipient_package(profile_version: int) -> bytes:
    """Render the exact canonical EH package for legacy profiles 1--4.

    The construction is bounded, uses only local Python recipe primitives,
    and admits its result through the frozen parser before returning it.
    """

    if profile_version not in (1, 2, 3, 4):
        raise ValueError("profile_version")
    return _render_eh_recipe_package(
        profile_version,
        _eh_recipient_recipe_bodies(profile_version),
        _r3_eh_tables(include_slot_multiplier=False),
    )


@lru_cache(maxsize=1)
def build_r3_recipe_package() -> bytes:
    """Render the complete compact v7 recipient package independently."""

    return _render_eh_recipe_package(7, _r3_recipe_bodies(), _r3_eh_tables())


def r3_recipe_package_metrics() -> R3RecipePackageMetrics:
    raw = build_r3_recipe_package()
    package = bootstrap.decode_recipe_package(raw, 7)
    repetition = next(recipe for recipe in package.recipes if recipe.recipe_id == 113)
    repetition_bytes = (
        32
        + 12 * (len(repetition.inputs) + len(repetition.outputs))
        + 32 * len(repetition.nodes)
    )
    return R3RecipePackageMetrics(
        len(raw),
        sha256(raw).hexdigest(),
        int.from_bytes(raw[20:24], "big"),
        int.from_bytes(raw[24:28], "big"),
        int.from_bytes(raw[28:32], "big"),
        int.from_bytes(raw[36:44], "big"),
        int.from_bytes(raw[44:48], "big"),
        repetition_bytes,
        len(repetition.nodes),
    )
