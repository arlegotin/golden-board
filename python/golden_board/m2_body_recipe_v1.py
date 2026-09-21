"""Immutable programs for spec/body-recipe-v1.md, using the existing VM only.

Production profile-8 composition consumes the logical definitions. The optional
standalone diagnostic serializer deliberately remains logical profile 7; it
cannot accidentally send profile 8 through the historical public parser.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import bootstrap
from .m2_recipe import _R3Body, _render_eh_recipe_package, _table_record

__all__ = (
    "BodyRecipeProgramV1",
    "body_recipe_programs_v1",
    "build_body_recipe_diagnostic_package_v1",
)

LIMIT = 16384
STATE_BYTES = 32782
N, L, P, O, D, R, F, K, E = (32768, 32770, 32772, 32774, 32776, 32778, 32779, 32780, 32781)
BODY, ENTRY, EXAMPLE = 201, 202, 203
_Node = tuple[int, int, int, tuple[int, ...], int, int]


@dataclass(frozen=True, slots=True)
class BodyRecipeProgramV1:
    """One immutable logical recipe, compatible with the common serializer."""

    recipe_id: int
    inputs: tuple[tuple[int, int], ...]
    outputs: tuple[tuple[int, int], ...]
    nodes: tuple[_Node, ...]


class _Body(_R3Body):
    def write(self, state, index, value):
        return self.add(20, bootstrap.BYTES, STATE_BYTES, (state, index, value))

    def iterate(self, state, body, count):
        return self.add(22, bootstrap.BYTES, STATE_BYTES, (state,), auxiliary=body, immediate=count)

    def u16(self, value):
        return self.uint(16, value)

    def u8(self, value):
        return self.uint(8, value)

    def add16(self, left, right):
        return self.binary(6, bootstrap.UINT, 16, left, right)

    def sub16(self, left, right):
        return self.binary(7, bootstrap.UINT, 16, left, right)

    def safe_input(self, index):
        # SELECT is eager: every speculative read must itself be bounded.
        safe = self.select(bootstrap.UINT, 16, self.less(index, self.u16(LIMIT)), index, self.u16(0))
        return self.read(1, safe)

    def all(self, *values):
        result = values[0]
        for value in values[1:]:
            result = self.bool_and(result, value)
        return result


def _decoder_body():
    b = _Body(BODY, ((bootstrap.BYTES, STATE_BYTES), (bootstrap.UINT, 64)),
             ((bootstrap.STATUS, 16), (bootstrap.BYTES, STATE_BYTES)))
    n, target, cursor, produced, distance = (b.read_uint(1, offset, 2) for offset in (N, L, P, O, D))
    remaining, flags, tokens, admitted = (b.read_fixed(1, offset) for offset in (R, F, K, E))
    active = b.less(produced, target)
    new_token = b.equal(remaining, b.u8(0))
    new_group = b.equal(tokens, b.u8(0))
    next_flags = b.select(bootstrap.UINT, 8, new_group, b.safe_input(cursor), flags)
    token_cursor = b.add16(cursor, b.select(bootstrap.UINT, 16, new_group, b.u16(1), b.u16(0)))
    first = b.safe_input(token_cursor)
    second = b.safe_input(b.add16(token_cursor, b.u16(1)))
    word = b.add(4, bootstrap.UINT, 16, (first, second))
    high_bit = b.add(14, bootstrap.UINT, 8, (next_flags,), immediate=128)
    copy = b.equal(high_bit, b.u8(128))
    new_distance = b.add16(b.binary(16, bootstrap.UINT, 16, word, b.u16(4)), b.u16(1))
    copy_length = b.binary(6, bootstrap.UINT, 8,
                           b.add(14, bootstrap.UINT, 8, (second,), immediate=15), b.u8(3))
    token_length = b.select(bootstrap.UINT, 8, copy, copy_length, b.u8(1))
    token_end = b.add16(token_cursor, b.select(bootstrap.UINT, 16, copy, b.u16(2), b.u16(1)))
    end_output = b.add16(produced, b.widen(token_length))
    good_token = b.all(b.less_or_equal(token_end, n), b.less_or_equal(end_output, target),
                       b.bool_or(b.bool_not(copy), b.less_or_equal(new_distance, produced)))
    good = b.all(b.equal(admitted, b.u8(1)),
                 b.bool_or(b.bool_not(active), b.bool_or(b.bool_not(new_token), good_token)))
    status = b.select(bootstrap.STATUS, 16, good, b.status(0), b.status(3))

    distance_used = b.select(bootstrap.UINT, 16, new_token, new_distance, distance)
    # The clamped subtraction also covers the eagerly evaluated literal branch.
    safe_produced = b.select(bootstrap.UINT, 16, b.less(produced, distance_used), distance_used, produced)
    source = b.add16(b.u16(LIMIT), b.sub16(safe_produced, distance_used))
    copy_byte = b.read(1, source)
    output_byte = b.select(bootstrap.UINT, 8, b.bool_or(b.bool_not(new_token), copy), copy_byte, first)
    updated = b.write(1, b.add16(b.u16(LIMIT), produced), output_byte)
    selected_cursor = b.select(bootstrap.UINT, 16, new_token, token_end, cursor)
    updated = b.write_uint(updated, P, 2, selected_cursor)
    updated = b.write_uint(updated, O, 2, b.add16(produced, b.u16(1)))
    updated = b.write_uint(updated, D, 2, distance_used)
    old_remaining_safe = b.select(bootstrap.UINT, 8, new_token, b.u8(1), remaining)
    old_remaining_next = b.binary(7, bootstrap.UINT, 8, old_remaining_safe, b.u8(1))
    new_remaining = b.binary(7, bootstrap.UINT, 8, token_length, b.u8(1))
    updated = b.write_fixed(updated, R, b.select(bootstrap.UINT, 8, new_token, new_remaining, old_remaining_next))
    shifted = b.binary(15, bootstrap.UINT, 8,
                       b.add(14, bootstrap.UINT, 8, (next_flags,), immediate=127), b.u8(1))
    updated = b.write_fixed(updated, F, b.select(bootstrap.UINT, 8, new_token, shifted, flags))
    available = b.select(bootstrap.UINT, 8, new_group, b.u8(8), tokens)
    next_tokens = b.binary(7, bootstrap.UINT, 8, available, b.u8(1))
    updated = b.write_fixed(updated, K, b.select(bootstrap.UINT, 8, new_token, next_tokens, tokens))
    updated = b.select(bootstrap.BYTES, STATE_BYTES, active, updated, 1)
    b.finish_body(status, updated)
    return b


def _initialize(b, encoded, encoded_length, extra_admission=None):
    target = b.read_uint(encoded, 1, 2)
    good = b.all(b.less_or_equal(b.u16(3), encoded_length),
                 b.less_or_equal(encoded_length, b.u16(LIMIT)),
                 b.less_or_equal(target, b.u16(LIMIT)),
                 b.equal(b.read_fixed(encoded, 0), b.u8(3)))
    if extra_admission is not None:
        good = b.bool_and(good, extra_admission)
    state = b.add(4, bootstrap.BYTES, STATE_BYTES, (encoded, b.zero_bytes(LIMIT + 14)))
    state = b.write_uint(state, N, 2, encoded_length)
    state = b.write_uint(state, L, 2, target)
    state = b.write_fixed(state, P + 1, b.u8(3))
    state = b.write_fixed(state, E, b.select(bootstrap.UINT, 8, good, b.u8(1), b.u8(0)))
    return state, target


def _finalize(b, state, encoded_length, target, output_length, include_length):
    good = b.all(b.equal(b.read_uint(state, P, 2), encoded_length),
                 b.equal(b.read_uint(state, O, 2), target),
                 b.equal(b.read_fixed(state, R), b.u8(0)),
                 b.equal(b.read_fixed(state, F), b.u8(0)))
    status = b.select(bootstrap.STATUS, 16, good, b.status(0), b.status(3))
    decoded = b.add(3, bootstrap.BYTES, output_length,
                    (state, b.u16(LIMIT), b.u16(output_length)))
    b.finish_outputs(status, (target, decoded) if include_length else (decoded,))


def _decoder_entry():
    b = _Body(ENTRY, ((bootstrap.BYTES, LIMIT), (bootstrap.UINT, 16)),
             ((bootstrap.STATUS, 16), (bootstrap.UINT, 16), (bootstrap.BYTES, LIMIT)))
    state, target = _initialize(b, 1, 2)
    state = b.iterate(state, BODY, LIMIT)
    _finalize(b, state, 2, target, LIMIT, True)
    return b


def _example_entry():
    # An existing-opcode construction: header + tiny body + zero padding.
    # No host decoder or host token iteration is involved.
    b = _Body(EXAMPLE, ((bootstrap.BYTES, 9), (bootstrap.UINT, 16)),
             ((bootstrap.STATUS, 16), (bootstrap.BYTES, 8)))
    header = b.zero_bytes(3)
    header = b.add(20, bootstrap.BYTES, 3, (header, b.u16(0), b.u8(3)))
    header = b.add(20, bootstrap.BYTES, 3, (header, b.u16(2), b.u8(8)))
    prefix = b.add(4, bootstrap.BYTES, 12, (header, 1))
    encoded = b.add(4, bootstrap.BYTES, LIMIT, (prefix, b.zero_bytes(LIMIT - 12)))
    length_good = b.less_or_equal(2, b.u16(9))
    safe_length = b.select(bootstrap.UINT, 16, length_good, 2, b.u16(0))
    encoded_length = b.add16(safe_length, b.u16(3))
    state, target = _initialize(b, encoded, encoded_length, length_good)
    state = b.iterate(state, BODY, 8)
    _finalize(b, state, encoded_length, target, 8, False)
    return b


def body_recipe_programs_v1() -> tuple[BodyRecipeProgramV1, ...]:
    """Construct fresh immutable programs in increasing recipe-ID order."""

    builders = (_decoder_body(), _decoder_entry(), _example_entry())
    return tuple(
        BodyRecipeProgramV1(builder.recipe_id, builder.inputs, builder.outputs, tuple(builder.nodes))
        for builder in builders
    )


def build_body_recipe_diagnostic_package_v1() -> bytes:
    """Build standalone profile-7 diagnostic bytes, never a profile-8 carrier.

    The new carrier owner must combine the immutable programs with its own base
    bodies and admit profile 8 explicitly through the new parser. Existing
    tables may be shared only after their exact identities are checked.
    """

    tables = (
        _table_record(3, bootstrap.UINT, 16, 256, b"".join(n.to_bytes(2, "big") for n in range(256))),
        _table_record(4, bootstrap.BYTES, 1, 1, b"\0"),
        _table_record(5, bootstrap.UINT, 8, 256, bytes(range(256))),
    )
    return _render_eh_recipe_package(7, body_recipe_programs_v1(), tables)
