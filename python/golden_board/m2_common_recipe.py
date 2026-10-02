"""Candidate-neutral generic-VM recipes for M2 route facts.

The transport lanes own recipes 30 and 108.  This module owns the small shared
fragment for facts 101--107 and 109--112 so those bytes cannot drift between
candidate implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable

from . import bootstrap


_IDENTITY = 1
_ONES = 2
_CRC32_INITIAL = 3
_CRC64_INITIAL = 4


def _be(value: int, width: int) -> bytes:
    return value.to_bytes(width, "big")


def _descriptor(value_id: int, value_type: int, width: int) -> bytes:
    return b"".join((_be(value_id, 2), bytes((value_type, 0)), _be(width, 4), _be(1, 4)))


def _node(
    node_id: int,
    opcode: int,
    value_type: int,
    width: int,
    arguments: tuple[int, ...],
    auxiliary: int,
    immediate: int,
) -> bytes:
    return b"".join(
        (
            _be(node_id, 2),
            bytes((opcode, value_type)),
            _be(width, 4),
            _be(len(arguments), 2),
            b"".join(_be(value, 2) for value in arguments + (0,) * (4 - len(arguments))),
            _be(auxiliary, 2),
            bytes(4),
            _be(immediate, 8),
        )
    )


@dataclass
class _Body:
    inputs: tuple[tuple[int, int], ...]
    nodes: list[tuple[int, int, int, tuple[int, ...], int, int]] = field(default_factory=list)
    constants: dict[tuple[int, int, int], int] = field(default_factory=dict)
    tables: dict[tuple[int, int], int] = field(default_factory=dict)

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
        if key not in self.constants:
            self.constants[key] = self.add(1, value_type, width, immediate=value)
        return self.constants[key]

    def table(self, table_id: int, width: int) -> int:
        key = (table_id, width)
        if key not in self.tables:
            self.tables[key] = self.add(2, bootstrap.TABLE, width, auxiliary=table_id)
        return self.tables[key]

    def select(self, condition: int, yes: int, no: int, value_type: int, width: int) -> int:
        return self.add(23, value_type, width, (condition, yes, no))

    def bool_and(self, left: int, right: int) -> int:
        return self.select(
            left,
            right,
            self.constant(bootstrap.BOOL, 1, 0),
            bootstrap.BOOL,
            1,
        )

    def success(self) -> int:
        return self.add(24, bootstrap.STATUS, 16)

    def failure(self, status: int) -> int:
        return self.add(25, bootstrap.STATUS, 16, immediate=status)

    def emit(self, value: int, slot: int) -> int:
        return self.add(5, bootstrap.STATUS, 16, (value,), auxiliary=slot)


def _record(
    recipe_id: int,
    inputs: tuple[tuple[int, int], ...],
    outputs: tuple[tuple[int, int], ...],
    nodes: list[tuple[int, int, int, tuple[int, ...], int, int]],
    resources: dict[int, tuple[int, int]],
) -> tuple[bytes, int, int, int]:
    input_count = len(inputs)
    edges = sum(len(item[3]) + (item[0] == 22) for item in nodes)
    steps = len(nodes) + sum(
        item[5] * resources[item[4]][0] for item in nodes if item[0] == 22
    )
    last_use = {index: index for index in range(1, len(nodes) + 1)}
    for consumer, item in enumerate(nodes, 1):
        for value_id in item[3]:
            if value_id > input_count:
                last_use[value_id - input_count] = consumer
    live: dict[int, int] = {}
    peak = 0
    for node_id, item in enumerate(nodes, 1):
        opcode, value_type, width, _, auxiliary, _ = item
        storage = 0 if value_type == bootstrap.TABLE else width if value_type == bootstrap.BYTES else (width + 7) // 8
        current = sum(live.values())
        if opcode == 22:
            peak = max(peak, current + resources[auxiliary][1])
        peak = max(peak, current + storage)
        live[node_id] = storage
        for prior in tuple(live):
            if last_use[prior] == node_id:
                del live[prior]
    descriptors = b"".join(
        _descriptor(index, value_type, width)
        for index, (value_type, width) in enumerate(inputs, 1)
    ) + b"".join(
        _descriptor(index, value_type, width)
        for index, (value_type, width) in enumerate(outputs, 1)
    )
    encoded_nodes = b"".join(
        _node(index, *item)
        for index, item in enumerate(nodes, 1)
    )
    recipe_bytes = 32 + len(descriptors) + len(encoded_nodes)
    header = b"".join(
        (
            _be(recipe_id, 2),
            bytes(2),
            _be(len(inputs), 2),
            _be(len(outputs), 2),
            _be(len(nodes), 4),
            _be(edges, 4),
            _be(steps, 8),
            _be(peak, 4),
            _be(recipe_bytes, 4),
        )
    )
    return header + descriptors + encoded_nodes, edges, steps, peak


def _table(table_id: int, value_type: int, width: int, count: int, payload: bytes) -> bytes:
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


class _Package:
    def __init__(self, profile_version: int) -> None:
        self.profile_version = profile_version
        self.records: list[bytes] = []
        self.resources: dict[int, tuple[int, int]] = {}
        self.nodes: list[int] = []
        self.edges: list[int] = []
        self.peaks: list[int] = []

    def recipe(
        self,
        recipe_id: int,
        inputs: tuple[tuple[int, int], ...],
        outputs: tuple[tuple[int, int], ...],
        build: Callable[[_Body], None],
    ) -> None:
        body = _Body(inputs)
        build(body)
        raw, edges, steps, peak = _record(
            recipe_id, inputs, outputs, body.nodes, self.resources
        )
        self.records.append(raw)
        self.resources[recipe_id] = (steps, peak)
        self.nodes.append(len(body.nodes))
        self.edges.append(edges)
        self.peaks.append(peak)

    def finish(self, tables: tuple[bytes, ...]) -> bytes:
        payload_bytes = sum(len(item) - 16 for item in tables)
        package_bytes = 64 + sum(map(len, tables)) + sum(map(len, self.records))
        header = b"".join(
            (
                b"GBRECP0\0",
                bytes(4),
                _be(self.profile_version, 2),
                bytes(2),
                _be(len(self.records), 2),
                _be(len(tables), 2),
                _be(sum(self.nodes), 4),
                _be(sum(self.edges), 4),
                _be(payload_bytes, 4),
                _be(package_bytes, 4),
                _be(max(value[0] for value in self.resources.values()), 8),
                _be(max(self.peaks), 4),
                bytes(16),
            )
        )
        return header + b"".join(tables) + b"".join(self.records)


def _crc_body(width: int, reflected: bool) -> Callable[[_Body], None]:
    state_bytes = 9 + width // 8

    def build(body: _Body) -> None:
        divisor = body.constant(bootstrap.UINT, 64, 8)
        byte_index = body.add(9, bootstrap.UINT, 64, (2, divisor))
        bit_index = body.add(10, bootstrap.UINT, 64, (2, divisor))
        source = body.add(19, bootstrap.UINT, 8, (1, byte_index))
        widened = body.add(
            4,
            bootstrap.UINT,
            width,
            (body.constant(bootstrap.UINT, width - 8, 0), source),
        )
        if reflected:
            shifted_source = body.add(16, bootstrap.UINT, width, (widened, bit_index))
        else:
            source_shift = body.add(
                7,
                bootstrap.UINT,
                64,
                (body.constant(bootstrap.UINT, 64, 7), bit_index),
            )
            shifted_source = body.add(16, bootstrap.UINT, width, (widened, source_shift))
        source_bit = body.add(14, bootstrap.UINT, width, (shifted_source,), immediate=1)
        source_bool = body.add(
            17,
            bootstrap.BOOL,
            1,
            (source_bit, body.constant(bootstrap.UINT, width, 1)),
        )
        crc_bytes = []
        for offset in range(width // 8):
            crc_bytes.append(
                body.add(
                    19,
                    bootstrap.UINT,
                    8,
                    (1, body.constant(bootstrap.UINT, 64, 9 + offset)),
                )
            )
        level = crc_bytes
        while len(level) > 1:
            level = [
                body.add(
                    4,
                    bootstrap.UINT,
                    (width // len(level)) * 2,
                    (level[index], level[index + 1]),
                )
                for index in range(0, len(level), 2)
            ]
        crc = level[0]
        if reflected:
            crc_bit = body.add(14, bootstrap.UINT, width, (crc,), immediate=1)
            shifted = body.add(
                16,
                bootstrap.UINT,
                width,
                (crc, body.constant(bootstrap.UINT, width, 1)),
            )
            polynomial = 0x82F63B78
        else:
            crc_top = body.add(
                16,
                bootstrap.UINT,
                width,
                (crc, body.constant(bootstrap.UINT, width, width - 1)),
            )
            crc_bit = body.add(14, bootstrap.UINT, width, (crc_top,), immediate=1)
            masked = body.add(
                14,
                bootstrap.UINT,
                width,
                (crc,),
                immediate=(1 << (width - 1)) - 1,
            )
            shifted = body.add(
                15,
                bootstrap.UINT,
                width,
                (masked, body.constant(bootstrap.UINT, width, 1)),
            )
            polynomial = 0x42F0E1EBA9EA3693
        crc_bool = body.add(
            17,
            bootstrap.BOOL,
            1,
            (crc_bit, body.constant(bootstrap.UINT, width, 1)),
        )
        same = body.add(17, bootstrap.BOOL, 1, (source_bool, crc_bool))
        feedback = body.add(
            17,
            bootstrap.BOOL,
            1,
            (same, body.constant(bootstrap.BOOL, 1, 0)),
        )
        with_polynomial = body.add(
            13,
            bootstrap.UINT,
            width,
            (shifted, body.constant(bootstrap.UINT, width, polynomial)),
        )
        updated = body.select(feedback, with_polynomial, shifted, bootstrap.UINT, width)
        identity = body.table(_IDENTITY, 8)
        state = 1
        for offset in range(width // 8):
            shift = width - 8 * (offset + 1)
            value = updated
            if shift:
                value = body.add(
                    16,
                    bootstrap.UINT,
                    width,
                    (value, body.constant(bootstrap.UINT, width, shift)),
                )
            value = body.add(14, bootstrap.UINT, width, (value,), immediate=0xFF)
            byte = body.add(21, bootstrap.UINT, 8, (identity, value))
            state = body.add(
                20,
                bootstrap.BYTES,
                state_bytes,
                (state, body.constant(bootstrap.UINT, 64, 9 + offset), byte),
            )
        body.emit(body.success(), 1)
        body.emit(state, 2)

    return build


def _read_integer(body: _Body, state: int, width: int) -> int:
    values = [
        body.add(
            19,
            bootstrap.UINT,
            8,
            (state, body.constant(bootstrap.UINT, 64, 9 + offset)),
        )
        for offset in range(width // 8)
    ]
    while len(values) > 1:
        new = []
        for index in range(0, len(values), 2):
            new.append(
                body.add(
                    4,
                    bootstrap.UINT,
                    width // len(values) * 2,
                    (values[index], values[index + 1]),
                )
            )
        values = new
    return values[0]


def _crc_entry(
    helper: int, width: int, initial_table: int, final_xor: int
) -> Callable[[_Body], None]:
    state_bytes = 9 + width // 8

    def build(body: _Body) -> None:
        table = body.table(initial_table, width // 8)
        zero = body.constant(bootstrap.UINT, 8, 0)
        initial = body.add(21, bootstrap.BYTES, width // 8, (table, zero))
        state = body.add(4, bootstrap.BYTES, state_bytes, (1, initial))
        state = body.add(
            22,
            bootstrap.BYTES,
            state_bytes,
            (state,),
            auxiliary=helper,
            immediate=72,
        )
        value = _read_integer(body, state, width)
        if final_xor:
            value = body.add(
                13,
                bootstrap.UINT,
                width,
                (value, body.constant(bootstrap.UINT, width, final_xor)),
            )
        body.emit(body.success(), 1)
        body.emit(value, 2)

    return build


@lru_cache(maxsize=6)
def common_recipe_package(profile_version: int) -> bytes:
    """Return the exact shared route package fragment for one frozen profile."""

    if profile_version not in range(1, 7):
        raise ValueError("profile_version")
    package = _Package(profile_version)
    state13 = ((bootstrap.BYTES, 13), (bootstrap.UINT, 64))
    state13_out = ((bootstrap.STATUS, 16), (bootstrap.BYTES, 13))
    package.recipe(1, state13, state13_out, _crc_body(32, True))
    crc64 = profile_version in (2, 4, 6)
    if crc64:
        state17 = ((bootstrap.BYTES, 17), (bootstrap.UINT, 64))
        state17_out = ((bootstrap.STATUS, 16), (bootstrap.BYTES, 17))
        package.recipe(2, state17, state17_out, _crc_body(64, False))

    status_output = (bootstrap.STATUS, 16)

    def binary(body: _Body) -> None:
        ones = body.add(
            21,
            bootstrap.BITS,
            8,
            (body.table(_ONES, 8), body.constant(bootstrap.UINT, 8, 0)),
        )
        result = body.add(13, bootstrap.BITS, 8, (1, ones))
        body.emit(body.success(), 1)
        body.emit(result, 2)

    package.recipe(101, ((bootstrap.BITS, 8),), (status_output, (bootstrap.BITS, 8)), binary)

    def transform(body: _Body) -> None:
        t, polarity, row, column, side, observed = range(1, 7)
        zero16 = body.constant(bootstrap.UINT, 16, 0)
        one16 = body.constant(bootstrap.UINT, 16, 1)
        side_nonzero = body.add(18, bootstrap.BOOL, 1, (zero16, side))
        safe_side = body.select(side_nonzero, side, one16, bootstrap.UINT, 16)
        last = body.add(7, bootstrap.UINT, 16, (safe_side, one16))
        row_valid = body.add(18, bootstrap.BOOL, 1, (row, safe_side))
        column_valid = body.add(18, bootstrap.BOOL, 1, (column, safe_side))
        safe_row = body.select(row_valid, row, zero16, bootstrap.UINT, 16)
        safe_column = body.select(column_valid, column, zero16, bootstrap.UINT, 16)
        reverse_row = body.add(7, bootstrap.UINT, 16, (last, safe_row))
        reverse_column = body.add(7, bootstrap.UINT, 16, (last, safe_column))
        coordinates = (
            (safe_row, safe_column),
            (reverse_column, safe_row),
            (reverse_row, reverse_column),
            (safe_column, reverse_row),
            (safe_row, reverse_column),
            (reverse_column, reverse_row),
            (reverse_row, safe_column),
            (safe_column, safe_row),
        )
        selected_row, selected_column = coordinates[-1]
        for value in range(6, -1, -1):
            selected = body.add(
                17,
                bootstrap.BOOL,
                1,
                (t, body.constant(bootstrap.UINT, 3, value)),
            )
            selected_row = body.select(
                selected, coordinates[value][0], selected_row, bootstrap.UINT, 16
            )
            selected_column = body.select(
                selected, coordinates[value][1], selected_column, bootstrap.UINT, 16
            )
        zero32 = body.constant(bootstrap.UINT, 16, 0)
        row32 = body.add(4, bootstrap.UINT, 32, (zero32, selected_row))
        column32 = body.add(4, bootstrap.UINT, 32, (zero32, selected_column))
        side32 = body.add(4, bootstrap.UINT, 32, (zero32, safe_side))
        product = body.add(8, bootstrap.UINT, 32, (row32, side32))
        flat = body.add(6, bootstrap.UINT, 32, (product, column32))
        same = body.add(17, bootstrap.BOOL, 1, (polarity, observed))
        normalized = body.add(
            17,
            bootstrap.BOOL,
            1,
            (same, body.constant(bootstrap.BOOL, 1, 0)),
        )
        valid = body.bool_and(side_nonzero, body.bool_and(row_valid, column_valid))
        status = body.select(valid, body.success(), body.failure(3), bootstrap.STATUS, 16)
        body.emit(status, 1)
        body.emit(flat, 2)
        body.emit(normalized, 3)

    package.recipe(
        102,
        ((bootstrap.UINT, 3), (bootstrap.BOOL, 1), (bootstrap.UINT, 16), (bootstrap.UINT, 16), (bootstrap.UINT, 16), (bootstrap.BOOL, 1)),
        (status_output, (bootstrap.UINT, 32), (bootstrap.BOOL, 1)),
        transform,
    )

    def less(body: _Body) -> None:
        result = body.add(18, bootstrap.BOOL, 1, (1, 2))
        body.emit(body.success(), 1)
        body.emit(result, 2)

    package.recipe(103, ((bootstrap.UINT, 16), (bootstrap.UINT, 16)), (status_output, (bootstrap.BOOL, 1)), less)

    def row_major(body: _Body) -> None:
        zero = body.constant(bootstrap.UINT, 16, 0)
        row = body.add(4, bootstrap.UINT, 32, (zero, 1))
        column = body.add(4, bootstrap.UINT, 32, (zero, 2))
        stride = body.add(4, bootstrap.UINT, 32, (zero, 3))
        product = body.add(8, bootstrap.UINT, 32, (row, stride))
        result = body.add(6, bootstrap.UINT, 32, (product, column))
        body.emit(body.success(), 1)
        body.emit(result, 2)

    package.recipe(104, ((bootstrap.UINT, 16),) * 3, (status_output, (bootstrap.UINT, 32)), row_major)

    def increment(body: _Body) -> None:
        result = body.add(6, bootstrap.UINT, 32, (1, body.constant(bootstrap.UINT, 32, 1)))
        body.emit(body.success(), 1)
        body.emit(result, 2)

    package.recipe(105, ((bootstrap.UINT, 32),), (status_output, (bootstrap.UINT, 32)), increment)

    def is_success(body: _Body) -> None:
        result = body.add(17, bootstrap.BOOL, 1, (1, body.constant(bootstrap.UINT, 8, 0)))
        body.emit(body.success(), 1)
        body.emit(result, 2)

    package.recipe(106, ((bootstrap.UINT, 8),), (status_output, (bootstrap.BOOL, 1)), is_success)
    package.recipe(
        107,
        ((bootstrap.BYTES, 9),),
        (status_output, (bootstrap.UINT, 32)),
        _crc_entry(1, 32, _CRC32_INITIAL, 0xFFFFFFFF),
    )

    def mapping(body: _Body) -> None:
        logical, side, shell_width = 1, 2, 3
        shell_inside = body.add(18, bootstrap.BOOL, 1, (shell_width, side))
        side_bounded = body.add(
            18,
            bootstrap.BOOL,
            1,
            (side, body.constant(bootstrap.UINT, 16, 2_049)),
        )
        preliminary = body.bool_and(shell_inside, side_bounded)
        safe_side = body.select(preliminary, side, shell_width, bootstrap.UINT, 16)
        after_first_shell = body.add(
            7, bootstrap.UINT, 16, (safe_side, shell_width)
        )
        second_shell_inside = body.add(
            18, bootstrap.BOOL, 1, (shell_width, after_first_shell)
        )
        valid = body.bool_and(preliminary, second_shell_inside)
        safe_after_first_shell = body.select(
            valid, after_first_shell, shell_width, bootstrap.UINT, 16
        )
        interior16 = body.add(
            7, bootstrap.UINT, 16, (safe_after_first_shell, shell_width)
        )
        zero16 = body.constant(bootstrap.UINT, 16, 0)
        interior = body.add(4, bootstrap.UINT, 32, (zero16, interior16))
        population = body.add(8, bootstrap.UINT, 32, (interior, interior))
        nonzero_population = body.add(
            18,
            bootstrap.BOOL,
            1,
            (body.constant(bootstrap.UINT, 32, 0), population),
        )
        safe_population = body.select(
            nonzero_population,
            population,
            body.constant(bootstrap.UINT, 32, 1),
            bootstrap.UINT,
            32,
        )
        safe_interior = body.select(
            nonzero_population,
            interior,
            body.constant(bootstrap.UINT, 32, 1),
            bootstrap.UINT,
            32,
        )
        reduced = body.add(10, bootstrap.UINT, 32, (logical, safe_population))
        remainder = body.add(10, bootstrap.UINT, 32, (reduced, safe_interior))
        scaled_once = body.add(8, bootstrap.UINT, 32, (safe_interior, remainder))
        scaled_twice = body.add(
            8,
            bootstrap.UINT,
            32,
            (scaled_once, body.constant(bootstrap.UINT, 32, 2)),
        )
        scaled = body.add(
            10, bootstrap.UINT, 32, (scaled_twice, safe_population)
        )
        scaled_less = body.add(18, bootstrap.BOOL, 1, (scaled, reduced))
        high = body.select(scaled_less, reduced, scaled, bootstrap.UINT, 32)
        low = body.select(scaled_less, scaled, reduced, bootstrap.UINT, 32)
        difference = body.add(7, bootstrap.UINT, 32, (high, low))
        wrapped = body.add(7, bootstrap.UINT, 32, (safe_population, difference))
        multiplied = body.select(scaled_less, wrapped, difference, bootstrap.UINT, 32)
        width32 = body.add(4, bootstrap.UINT, 32, (zero16, shell_width))
        width_term = body.add(
            8,
            bootstrap.UINT,
            32,
            (width32, body.constant(bootstrap.UINT, 32, 257)),
        )
        profile_term = body.constant(bootstrap.UINT, 32, 40_503 * profile_version)
        offset_sum = body.add(6, bootstrap.UINT, 32, (width_term, profile_term))
        offset = body.add(10, bootstrap.UINT, 32, (offset_sum, safe_population))
        threshold = body.add(7, bootstrap.UINT, 32, (safe_population, offset))
        can_add = body.add(18, bootstrap.BOOL, 1, (multiplied, threshold))
        safe_addend = body.select(
            can_add, offset, body.constant(bootstrap.UINT, 32, 0), bootstrap.UINT, 32
        )
        added = body.add(6, bootstrap.UINT, 32, (multiplied, safe_addend))
        safe_left = body.select(can_add, threshold, multiplied, bootstrap.UINT, 32)
        subtracted = body.add(7, bootstrap.UINT, 32, (safe_left, threshold))
        physical = body.select(can_add, added, subtracted, bootstrap.UINT, 32)
        complete_valid = body.bool_and(valid, nonzero_population)
        status = body.select(
            complete_valid, body.success(), body.failure(3), bootstrap.STATUS, 16
        )
        body.emit(status, 1)
        body.emit(physical, 2)

    package.recipe(
        109,
        ((bootstrap.UINT, 32), (bootstrap.UINT, 16), (bootstrap.UINT, 16)),
        (status_output, (bootstrap.UINT, 32)),
        mapping,
    )

    def fragment(body: _Body) -> None:
        result = body.add(4, bootstrap.UINT, 48, (1, 2))
        body.emit(body.success(), 1)
        body.emit(result, 2)

    package.recipe(110, ((bootstrap.UINT, 32), (bootstrap.UINT, 16)), (status_output, (bootstrap.UINT, 48)), fragment)
    package.recipe(
        111,
        ((bootstrap.BYTES, 9),),
        (status_output, (bootstrap.UINT, 64 if crc64 else 32)),
        _crc_entry(2 if crc64 else 1, 64 if crc64 else 32, _CRC64_INITIAL if crc64 else _CRC32_INITIAL, 0 if crc64 else 0xFFFFFFFF),
    )

    def tier(body: _Body) -> None:
        maximum = body.constant(bootstrap.UINT, 16, 0xFFFF)
        can_increment = body.add(18, bootstrap.BOOL, 1, (2, maximum))
        safe_value = body.select(
            can_increment, 2, body.constant(bootstrap.UINT, 16, 0), bootstrap.UINT, 16
        )
        incremented = body.add(
            6,
            bootstrap.UINT,
            16,
            (safe_value, body.constant(bootstrap.UINT, 16, 1)),
        )
        count_matches = body.add(17, bootstrap.BOOL, 1, (1, incremented))
        result = body.bool_and(can_increment, body.bool_and(count_matches, 3))
        body.emit(body.success(), 1)
        body.emit(result, 2)

    package.recipe(
        112,
        ((bootstrap.UINT, 16), (bootstrap.UINT, 16), (bootstrap.BOOL, 1)),
        (status_output, (bootstrap.BOOL, 1)),
        tier,
    )
    tables = [
        _table(_IDENTITY, bootstrap.UINT, 8, 256, bytes(range(256))),
        _table(_ONES, bootstrap.BITS, 8, 1, b"\xff"),
        _table(_CRC32_INITIAL, bootstrap.BYTES, 4, 1, b"\xff" * 4),
    ]
    if crc64:
        tables.append(_table(_CRC64_INITIAL, bootstrap.BYTES, 8, 1, bytes(8)))
    return package.finish(tuple(tables))


def common_recipe_table_records(profile_version: int) -> tuple[bytes, ...]:
    """Project the exact duplicate TABLE payloads required by route records."""

    package = bootstrap.decode_recipe_package(
        common_recipe_package(profile_version), profile_version
    )
    return tuple(
        b"".join(
            (
                _be(table.table_id, 2),
                bytes((table.element_type, 0)),
                _be(table.element_width, 4),
                _be(table.element_count, 4),
                _be(len(table.payload), 4),
                table.payload,
            )
        )
        for table in package.tables
    )
