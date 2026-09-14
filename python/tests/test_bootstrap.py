from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from golden_board import bootstrap, canonical_manifest, constants as C, content


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_RAW = (ROOT / "conformance/bootstrap-v0.json").read_bytes()
FIXTURE = canonical_manifest.validate_canonical_manifest(FIXTURE_RAW)
REJECTIONS_RAW = (ROOT / "conformance/bootstrap-invalid-v0.json").read_bytes()
REJECTIONS = canonical_manifest.validate_canonical_manifest(REJECTIONS_RAW)
RECIPE_FIXTURE_RAW = (ROOT / "conformance/recipe-v0.json").read_bytes()
RECIPE_FIXTURE = canonical_manifest.validate_canonical_manifest(RECIPE_FIXTURE_RAW)


def _inventory() -> bootstrap.Inventory:
    entries = [
        bootstrap.InventoryEntry(1, 1, 0, 128, 1, 2, (), 1_376),
        bootstrap.InventoryEntry(2, 2, 0, 128, 1, 2, (4,), 38),
        bootstrap.InventoryEntry(3, 2, 0, 128, 1, 2, (4,), 38),
        bootstrap.InventoryEntry(4, 3, 0, 128, 1, 2, (), 12),
    ]
    entries.extend(
        bootstrap.InventoryEntry(5 + ordinal, 3, 0, 129, 1, 1, (), 2, ordinal)
        for ordinal in range(64)
    )
    return bootstrap.Inventory(tuple(entries))


def _inventory_v1() -> bootstrap.Inventory:
    entries = [
        bootstrap.InventoryEntry(1, 1, 1, 128, 1, 1, (), 1_376, None, 5),
        bootstrap.InventoryEntry(2, 2, 0, 128, 1, 1, (16,), 38, None, 5),
        bootstrap.InventoryEntry(3, 2, 0, 128, 1, 1, (16,), 38, None, 5),
        bootstrap.InventoryEntry(16, 3, 0, 128, 1, 1, (), 2, None, 5),
    ]
    entries.extend(
        bootstrap.InventoryEntry(
            100 + ordinal,
            3,
            0,
            129,
            1,
            1,
            (),
            2,
            ordinal,
            1,
        )
        for ordinal in range(64)
    )
    return bootstrap.Inventory(tuple(entries), 1)


def _be(value: int, width: int) -> bytes:
    return value.to_bytes(width, "big")


def _recipe_descriptor(value_id: int, value_type: int, width: int) -> bytes:
    return b"".join(
        (_be(value_id, 2), bytes((value_type, 0)), _be(width, 4), _be(1, 4))
    )


def _recipe_node(
    node_id: int,
    opcode: int,
    output_type: int,
    output_width: int,
    arguments: tuple[int, ...] = (),
    auxiliary_u16: int = 0,
    immediate_u64: int = 0,
) -> bytes:
    padded = arguments + (0,) * (4 - len(arguments))
    return b"".join(
        (
            _be(node_id, 2),
            bytes((opcode, output_type)),
            _be(output_width, 4),
            _be(len(arguments), 2),
            b"".join(_be(value, 2) for value in padded),
            _be(auxiliary_u16, 2),
            b"\0\0\0\0",
            _be(immediate_u64, 8),
        )
    )


def _recipe_record(
    recipe_id: int,
    inputs: list[tuple[int, int]],
    outputs: list[tuple[int, int]],
    nodes: list[tuple[int, int, tuple[int, ...], int, int, int]],
    prior_resources: dict[int, tuple[int, int]],
) -> tuple[bytes, tuple[int, int]]:
    """Independent literal-fixture assembler for the closed resource formulas."""

    input_count = len(inputs)
    edge_count = sum(len(row[2]) + (row[0] == 22) for row in nodes)
    steps = len(nodes) + sum(
        row[4] * prior_resources[row[3]][0] for row in nodes if row[0] == 22
    )
    last_use = {index: index for index in range(1, len(nodes) + 1)}
    for consumer, row in enumerate(nodes, 1):
        for value_id in row[2]:
            if value_id > input_count:
                last_use[value_id - input_count] = consumer

    def storage(value_type: int, width: int) -> int:
        if value_type == bootstrap.TABLE:
            return 0
        return width if value_type == bootstrap.BYTES else (width + 7) // 8

    live: dict[int, int] = {}
    peak = 0
    for node_id, row in enumerate(nodes, 1):
        opcode, output_width, _, auxiliary, _, output_type = row
        live_bytes = sum(live.values())
        if opcode == 22:
            peak = max(peak, live_bytes + prior_resources[auxiliary][1])
        result_bytes = storage(output_type, output_width)
        peak = max(peak, live_bytes + result_bytes)
        live[node_id] = result_bytes
        for prior in tuple(live):
            if last_use[prior] == node_id:
                del live[prior]

    descriptors = b"".join(
        _recipe_descriptor(index, value_type, width)
        for index, (value_type, width) in enumerate(inputs, 1)
    ) + b"".join(
        _recipe_descriptor(index, value_type, width)
        for index, (value_type, width) in enumerate(outputs, 1)
    )
    node_bytes = b"".join(
        _recipe_node(
            index,
            opcode,
            output_type,
            output_width,
            arguments,
            auxiliary,
            immediate,
        )
        for index, (
            opcode,
            output_width,
            arguments,
            auxiliary,
            immediate,
            output_type,
        ) in enumerate(nodes, 1)
    )
    recipe_bytes = 32 + len(descriptors) + len(node_bytes)
    header = b"".join(
        (
            _be(recipe_id, 2),
            b"\0\0",
            _be(len(inputs), 2),
            _be(len(outputs), 2),
            _be(len(nodes), 4),
            _be(edge_count, 4),
            _be(steps, 8),
            _be(peak, 4),
            _be(recipe_bytes, 4),
        )
    )
    return header + descriptors + node_bytes, (steps, peak)


def _recipe_fixture() -> tuple[bytes, tuple[bytes, ...]]:
    # Node tuple: opcode, output width, argument IDs, aux-u16, immediate, type.
    resources: dict[int, tuple[int, int]] = {}
    body_nodes = [
        (1, 1, (), 0, 1, bootstrap.BOOL),
        (23, 8, (3, 1, 1), 0, 0, bootstrap.UINT),
        (24, 16, (), 0, 0, bootstrap.STATUS),
        (5, 16, (5,), 1, 0, bootstrap.STATUS),
        (5, 16, (4,), 2, 0, bootstrap.STATUS),
    ]
    body, resources[1] = _recipe_record(
        1,
        [(bootstrap.UINT, 8), (bootstrap.UINT, 64)],
        [(bootstrap.STATUS, 16), (bootstrap.UINT, 8)],
        body_nodes,
        resources,
    )

    inputs = [
        (bootstrap.UINT, 8),
        (bootstrap.UINT, 8),
        (bootstrap.BITS, 8),
        (bootstrap.BYTES, 3),
        (bootstrap.BOOL, 1),
    ]
    nodes: list[tuple[int, int, tuple[int, ...], int, int, int]] = []

    def add(
        opcode: int,
        value_type: int,
        width: int,
        arguments: tuple[int, ...] = (),
        auxiliary: int = 0,
        immediate: int = 0,
    ) -> int:
        nodes.append((opcode, width, arguments, auxiliary, immediate, value_type))
        return len(inputs) + len(nodes)

    one = add(1, bootstrap.UINT, 8, immediate=1)
    three = add(1, bootstrap.UINT, 8, immediate=3)
    table = add(2, bootstrap.TABLE, 8, auxiliary=1)
    desired: list[tuple[int, int, int, bytes]] = []

    def keep(value_id: int, value_type: int, width: int, expected: bytes) -> None:
        desired.append((value_id, value_type, width, expected))

    keep(add(3, bootstrap.BITS, 3, (3, one, three)), bootstrap.BITS, 3, b"`")
    keep(add(4, bootstrap.UINT, 16, (1, 2)), bootstrap.UINT, 16, b"\x06\x02")
    keep(add(6, bootstrap.UINT, 8, (1, 2)), bootstrap.UINT, 8, b"\x08")
    keep(add(7, bootstrap.UINT, 8, (1, 2)), bootstrap.UINT, 8, b"\x04")
    keep(add(8, bootstrap.UINT, 8, (1, 2)), bootstrap.UINT, 8, b"\x0c")
    keep(add(9, bootstrap.UINT, 8, (1, 2)), bootstrap.UINT, 8, b"\x03")
    keep(add(10, bootstrap.UINT, 8, (1, 2)), bootstrap.UINT, 8, b"\x00")
    keep(add(11, bootstrap.UINT, 8, (1, 2)), bootstrap.UINT, 8, b"\x02")
    keep(add(12, bootstrap.UINT, 8, (1, 2)), bootstrap.UINT, 8, b"\x06")
    keep(add(13, bootstrap.UINT, 8, (1, 2)), bootstrap.UINT, 8, b"\x04")
    keep(add(14, bootstrap.UINT, 8, (1,), immediate=15), bootstrap.UINT, 8, b"\x06")
    keep(add(15, bootstrap.UINT, 8, (1, one)), bootstrap.UINT, 8, b"\x0c")
    keep(add(16, bootstrap.UINT, 8, (1, one)), bootstrap.UINT, 8, b"\x03")
    keep(add(17, bootstrap.BOOL, 1, (1, 2)), bootstrap.BOOL, 1, b"\x00")
    keep(add(18, bootstrap.BOOL, 1, (1, 2)), bootstrap.BOOL, 1, b"\x00")
    keep(add(19, bootstrap.BOOL, 1, (3, one)), bootstrap.BOOL, 1, b"\x00")
    keep(add(20, bootstrap.BITS, 8, (3, one, 5)), bootstrap.BITS, 8, b"\xf6")
    keep(add(21, bootstrap.UINT, 8, (table, one)), bootstrap.UINT, 8, b"\x08")
    keep(add(19, bootstrap.UINT, 8, (4, one)), bootstrap.UINT, 8, b"b")
    keep(add(20, bootstrap.BYTES, 3, (4, one, 2)), bootstrap.BYTES, 3, b"a\x02c")
    keep(
        add(22, bootstrap.UINT, 8, (1,), auxiliary=1, immediate=2),
        bootstrap.UINT,
        8,
        b"\x06",
    )
    keep(add(23, bootstrap.UINT, 8, (5, 1, 2)), bootstrap.UINT, 8, b"\x06")
    failure = add(25, bootstrap.STATUS, 16, immediate=5)
    failure_copy = add(1, bootstrap.STATUS, 16, immediate=5)
    keep(
        add(17, bootstrap.BOOL, 1, (failure, failure_copy)), bootstrap.BOOL, 1, b"\x01"
    )
    keep(add(3, bootstrap.UINT, 3, (3, one, three)), bootstrap.UINT, 3, b"\x03")
    keep(add(3, bootstrap.BYTES, 1, (4, one, one)), bootstrap.BYTES, 1, b"b")
    keep(add(4, bootstrap.BITS, 16, (3, 3)), bootstrap.BITS, 16, b"\xb6\xb6")
    keep(add(4, bootstrap.BYTES, 6, (4, 4)), bootstrap.BYTES, 6, b"abcabc")
    keep(add(11, bootstrap.BITS, 8, (3, 3)), bootstrap.BITS, 8, b"\xb6")
    keep(add(12, bootstrap.BITS, 8, (3, 3)), bootstrap.BITS, 8, b"\xb6")
    keep(add(13, bootstrap.BITS, 8, (3, 3)), bootstrap.BITS, 8, b"\x00")
    keep(add(19, bootstrap.UINT, 8, (table, one)), bootstrap.UINT, 8, b"\x08")
    success = add(24, bootstrap.STATUS, 16)
    extra_outputs = [
        (bootstrap.BITS, 16, b"\x06\x02"),
        (bootstrap.BYTES, 6, b"abcabc"),
        (bootstrap.BITS, 6, b"l"),
    ]
    outputs = (
        [(bootstrap.STATUS, 16)]
        + [(value_type, width) for _, value_type, width, _ in desired]
        + [(value_type, width) for value_type, width, _ in extra_outputs]
    )
    add(5, bootstrap.STATUS, 16, (success,), auxiliary=1)
    for slot, (value_id, _, _, _) in enumerate(desired, 2):
        add(5, bootstrap.STATUS, 16, (value_id,), auxiliary=slot)
    extra_slot = len(desired) + 2
    add(5, bootstrap.STATUS, 16, (1,), auxiliary=extra_slot)
    add(5, bootstrap.STATUS, 16, (2,), auxiliary=extra_slot, immediate=8)
    add(5, bootstrap.STATUS, 16, (4,), auxiliary=extra_slot + 1)
    add(5, bootstrap.STATUS, 16, (4,), auxiliary=extra_slot + 1, immediate=3)
    add(5, bootstrap.STATUS, 16, (desired[0][0],), auxiliary=extra_slot + 2)
    add(
        5,
        bootstrap.STATUS,
        16,
        (desired[0][0],),
        auxiliary=extra_slot + 2,
        immediate=3,
    )
    kitchen, resources[2] = _recipe_record(2, inputs, outputs, nodes, resources)

    failure_nodes = [
        (1, 8, (), 0, 7, bootstrap.UINT),
        (5, 16, (1,), 2, 0, bootstrap.STATUS),
        (25, 16, (), 0, 4, bootstrap.STATUS),
        (5, 16, (3,), 1, 0, bootstrap.STATUS),
    ]
    failure_recipe, resources[3] = _recipe_record(
        3,
        [],
        [(bootstrap.STATUS, 16), (bootstrap.UINT, 8)],
        failure_nodes,
        resources,
    )

    table_payload = b"\x07\x08\x09"
    table_record = b"".join(
        (
            b"\0\1",
            bytes((bootstrap.UINT, 0)),
            _be(8, 4),
            _be(3, 4),
            _be(3, 4),
            table_payload,
        )
    )
    recipes = (body, kitchen, failure_recipe)
    package_bytes = 64 + len(table_record) + sum(map(len, recipes))
    total_nodes = sum(int.from_bytes(recipe[8:12], "big") for recipe in recipes)
    total_edges = sum(int.from_bytes(recipe[12:16], "big") for recipe in recipes)
    header = b"".join(
        (
            b"GBRECP0\0",
            b"\0\0\0\0",
            b"\0\x01",
            b"\0\0",
            _be(len(recipes), 2),
            b"\0\x01",
            _be(total_nodes, 4),
            _be(total_edges, 4),
            _be(len(table_payload), 4),
            _be(package_bytes, 4),
            _be(max(value[0] for value in resources.values()), 8),
            _be(max(value[1] for value in resources.values()), 4),
            bytes(16),
        )
    )
    return header + table_record + b"".join(recipes), tuple(
        row[3] for row in desired
    ) + tuple(row[2] for row in extra_outputs)


class BootstrapV0(unittest.TestCase):
    def test_registered_literal_fixture_is_closed_and_exact(self) -> None:
        self.assertEqual(
            set(FIXTURE),
            {
                "common_block_hex",
                "crc32c_kats",
                "crc64_ecma_kats",
                "inventory_entry_count",
                "inventory_hex",
                "schema",
                "section_crc32c_hex",
                "section_crc64_ecma_hex",
                "tier_frame_hex",
            },
        )
        self.assertEqual(FIXTURE["schema"], "golden-board.bootstrap-v0-fixtures/v0")
        for row in FIXTURE["crc32c_kats"]:
            self.assertEqual(set(row), {"input_hex", "result_hex"})
            self.assertEqual(
                bootstrap.crc32c_v0(bytes.fromhex(row["input_hex"])).to_bytes(4, "big"),
                bytes.fromhex(row["result_hex"]),
            )
        for row in FIXTURE["crc64_ecma_kats"]:
            self.assertEqual(set(row), {"input_hex", "result_hex"})
            self.assertEqual(
                bootstrap.crc64_ecma_v0(bytes.fromhex(row["input_hex"])).to_bytes(
                    8, "big"
                ),
                bytes.fromhex(row["result_hex"]),
            )

        block_raw = bytes.fromhex(FIXTURE["common_block_hex"])
        block = bootstrap.decode_common_block(block_raw, 1)
        self.assertEqual(bootstrap.encode_common_block(block), block_raw)
        for name in ("section_crc32c_hex", "section_crc64_ecma_hex"):
            section_raw = bytes.fromhex(FIXTURE[name])
            section = bootstrap.decode_section_envelope(section_raw)
            self.assertEqual(bootstrap.encode_section_envelope(section), section_raw)
        inventory_raw = bytes.fromhex(FIXTURE["inventory_hex"])
        inventory = bootstrap.decode_inventory(inventory_raw)
        self.assertEqual(len(inventory.entries), FIXTURE["inventory_entry_count"])
        self.assertEqual(bootstrap.encode_inventory(inventory), inventory_raw)
        tier_raw = bytes.fromhex(FIXTURE["tier_frame_hex"])
        tier = bootstrap.decode_tier_frame(tier_raw, 2)
        self.assertEqual(bootstrap.encode_tier_frame(tier), tier_raw)

    def test_shared_inventory_rejections_are_exact(self) -> None:
        self.assertEqual(set(REJECTIONS), {"inventory_mutations", "schema"})
        self.assertEqual(
            REJECTIONS["schema"], "golden-board.bootstrap-v0-rejections/v0"
        )
        original = bytes.fromhex(FIXTURE["inventory_hex"])
        for row in REJECTIONS["inventory_mutations"]:
            self.assertEqual(set(row), {"offset", "replacement_hex", "result_code"})
            replacement = bytes.fromhex(row["replacement_hex"])
            offset = row["offset"]
            mutated = (
                original[:offset] + replacement + original[offset + len(replacement) :]
            )
            with self.assertRaises(bootstrap.BootstrapReject) as caught:
                bootstrap.decode_inventory(mutated)
            self.assertEqual(caught.exception.code, row["result_code"])

    def test_crc_known_answers(self) -> None:
        self.assertEqual(bootstrap.crc32c_v0(b""), 0)
        self.assertEqual(bootstrap.crc32c_v0(b"123456789"), 0xE3069283)
        self.assertEqual(bootstrap.crc32c_v0(b"\0\1\2\3"), 0xD9331AA3)
        self.assertEqual(bootstrap.crc64_ecma_v0(b""), 0)
        self.assertEqual(bootstrap.crc64_ecma_v0(b"123456789"), 0x6C40DF5F0B497347)
        self.assertEqual(bootstrap.crc64_ecma_v0(b"\0\1\2\3"), 0xF805609ECE1ECBF3)

    def test_exact_entry_hypothesis_order_and_bounds(self) -> None:
        bits = (0, 1, 1, 1)
        hypotheses = bootstrap.entry_hypotheses(bits, 4)
        self.assertEqual(len(hypotheses), 16)
        self.assertEqual(hypotheses[0], bits)
        self.assertEqual(hypotheses[1], tuple(bit ^ 1 for bit in bits))
        self.assertEqual(hypotheses[2], (1, 0, 1, 1))
        observation = bootstrap.RawObservation.parse(bits, 4)
        self.assertEqual(
            observation.normalized_bit(bootstrap.EntryHypothesis(1, 0), 0, 0),
            1,
        )
        with self.assertRaises(AttributeError):
            observation._side = 3
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.entry_hypotheses(bits, 3)
        self.assertEqual(caught.exception.code, bootstrap.RAW_LENGTH)
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.entry_hypotheses((0, 1, 0), 3)
        self.assertEqual(caught.exception.code, bootstrap.RAW_GEOMETRY)
        with self.assertRaises(AttributeError):
            caught.exception._code = bootstrap.RAW_LENGTH
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.entry_hypotheses((0, True, 0, 1), 4)
        self.assertEqual(caught.exception.code, bootstrap.RAW_VALUE)

    def test_entry_hypotheses_are_lazy_and_bounded(self) -> None:
        side = 512
        hypotheses = bootstrap.entry_hypotheses(bytes(side * side), side * side)
        self.assertEqual(len(hypotheses), 16)
        self.assertNotIsInstance(hypotheses[0], tuple)
        self.assertEqual(len(hypotheses[0]), side * side)
        self.assertEqual(hypotheses[15][-1], 1)

    def test_sector_partition_is_exact(self) -> None:
        side, width = 32, 8
        sectors = [
            {
                bootstrap.sector_cell(side, width, sector, offset)
                for offset in range(width * (side - width))
            }
            for sector in range(4)
        ]
        self.assertEqual(sum(map(len, sectors)), side * side - (side - 2 * width) ** 2)
        self.assertEqual(len(set().union(*sectors)), sum(map(len, sectors)))
        self.assertEqual(
            set().union(*sectors),
            {
                (row, column)
                for row in range(side)
                for column in range(side)
                if row < width
                or row >= side - width
                or column < width
                or column >= side - width
            },
        )

    def test_common_block_round_trip_and_fail_closed_check(self) -> None:
        payload = bytes(range(157))
        block = bootstrap.CommonBlock(1, 9, 0, 3, 0, 0, 1, 157, payload)
        encoded = bootstrap.encode_common_block(block)
        self.assertEqual(len(encoded), 191)
        self.assertEqual(bootstrap.decode_common_block(encoded, 1), block)
        damaged = bytearray(encoded)
        damaged[60] ^= 1
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.decode_common_block(bytes(damaged), 1)
        self.assertEqual(caught.exception.code, bootstrap.LOCAL_CHECK)

    def test_final_fragment_padding_and_length_are_canonical(self) -> None:
        block = bootstrap.CommonBlock(7, 9, 1, 3, 0, 1, 2, 160, b"abc")
        encoded = bootstrap.encode_common_block(block)
        self.assertEqual(bootstrap.decode_common_block(encoded, 7), block)
        damaged = bytearray(encoded)
        damaged[33] = 1
        damaged[-4:] = bootstrap.crc32c_v0(
            bootstrap.LOCAL_DOMAIN + bytes(damaged[:187])
        ).to_bytes(4, "big")
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.decode_common_block(bytes(damaged), 7)
        self.assertEqual(caught.exception.code, bootstrap.FRAGMENT_SHAPE)

    def test_section_round_trip_both_checks(self) -> None:
        for check_id in (1, 2):
            section = bootstrap.SectionEnvelope(9, 3, 0, 128, check_id, (2, 4), b"data")
            encoded = bootstrap.encode_section_envelope(section)
            self.assertTrue(bootstrap.section_envelope_attempt_eligible(encoded))
            self.assertEqual(bootstrap.decode_section_envelope(encoded), section)
            wrong_stored = encoded[:-1] + bytes((encoded[-1] ^ 1,))
            self.assertTrue(
                bootstrap.section_envelope_attempt_eligible(wrong_stored)
            )
            with self.assertRaises(bootstrap.BootstrapReject) as caught:
                bootstrap.decode_section_envelope(wrong_stored)
            self.assertEqual(caught.exception.code, bootstrap.SECTION_CHECK)
        wrong_width = bytearray(
            bootstrap.encode_section_envelope(
                bootstrap.SectionEnvelope(9, 3, 0, 128, 1, (), b"data")
            )
        )
        wrong_width[11] = 2
        self.assertFalse(
            bootstrap.section_envelope_attempt_eligible(bytes(wrong_width))
        )

    def test_fragment_assembly_deduplicates_but_never_votes(self) -> None:
        section = bootstrap.SectionEnvelope(9, 3, 0, 128, 1, (), bytes(range(256)))
        envelope = bootstrap.encode_section_envelope(section)
        blocks = bootstrap.fragment_section(envelope, 4, 1)
        copy_id, assembled = bootstrap.assemble_semantic_copy(
            (blocks[1], blocks[0], blocks[0]), 4
        )
        self.assertEqual((copy_id, assembled), (1, envelope))
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.assemble_semantic_copy(blocks[:-1], 4)
        self.assertEqual(caught.exception.code, bootstrap.SECTION_INCOMPLETE)

    def test_witness_quality_is_order_independent_and_conflict_is_ambiguous(
        self,
    ) -> None:
        first = bootstrap.encode_section_envelope(
            bootstrap.SectionEnvelope(9, 3, 0, 128, 1, (), b"same")
        )
        witnesses = (
            bootstrap.SectionWitness(first, False),
            bootstrap.SectionWitness(first, True),
        )
        self.assertEqual(
            bootstrap.recover_logical_section(witnesses), ("verified", first)
        )
        second = bootstrap.encode_section_envelope(
            bootstrap.SectionEnvelope(9, 3, 0, 128, 1, (), b"other")
        )
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.recover_logical_section(
                (
                    bootstrap.SectionWitness(first, True),
                    bootstrap.SectionWitness(second, False),
                )
            )
        self.assertEqual(caught.exception.code, bootstrap.AMBIGUOUS)

    def test_inventory_round_trip_and_trailing_rejection(self) -> None:
        inventory = _inventory()
        encoded = bootstrap.encode_inventory(inventory)
        self.assertEqual(bootstrap.decode_inventory(encoded), inventory)
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.decode_inventory(encoded + b"\0")
        self.assertEqual(caught.exception.code, bootstrap.TRAILING_DATA)
        invalid = list(inventory.entries)
        invalid[1] = replace(invalid[1], closure_class=129)
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.encode_inventory(bootstrap.Inventory(tuple(invalid)))
        self.assertEqual(caught.exception.code, bootstrap.INVENTORY)
        invalid = list(inventory.entries)
        invalid[3] = replace(invalid[3], logical_payload_length=0)
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.encode_inventory(bootstrap.Inventory(tuple(invalid)))
        self.assertEqual(caught.exception.code, bootstrap.INVENTORY)

    def test_inventory_v1_flags_spine_and_copy_count_are_exact(self) -> None:
        inventory = _inventory_v1()
        encoded = bootstrap.encode_inventory(inventory)
        self.assertEqual(len(encoded), 1_376)
        self.assertEqual(encoded[:2], b"\0\1")
        self.assertEqual(bootstrap.decode_inventory(encoded), inventory)
        # The checked section-1 and section-16 spine entries use the sentinel.
        self.assertEqual(encoded[19], 5 << 1)
        entry_16_offset = 8 + 20 * 3 + 8
        self.assertEqual(encoded[entry_16_offset + 11], 5 << 1)
        self.assertEqual(
            bootstrap.decode_inventory_entry_v1_header(encoded[8:28]),
            (5, False),
        )
        self.assertEqual(
            bootstrap.decode_inventory_entry_v1_header(
                encoded[entry_16_offset : entry_16_offset + 20]
            ),
            (5, False),
        )

        for index, changed in (
            (0, replace(inventory.entries[0], copy_count=2)),
            (0, replace(inventory.entries[0], check_id=2)),
            (0, replace(inventory.entries[0], physical_replica_count=3)),
            (3, replace(inventory.entries[3], physical_replica_count=2)),
            (4, replace(inventory.entries[4], physical_replica_count=5)),
            (3, replace(inventory.entries[3], closure_class=129)),
            (3, replace(inventory.entries[3], game_ordinal=0)),
        ):
            with self.subTest(index=index, changed=changed):
                entries = list(inventory.entries)
                entries[index] = changed
                with self.assertRaises(bootstrap.BootstrapReject) as caught:
                    bootstrap.encode_inventory(bootstrap.Inventory(tuple(entries), 1))
                self.assertEqual(caught.exception.code, bootstrap.INVENTORY)

        reserved = bytearray(encoded)
        reserved[19] |= 0x10
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.decode_inventory(bytes(reserved))
        self.assertEqual(caught.exception.code, bootstrap.INVENTORY)

    def test_inventory_agreement_and_dependency_closure_are_exact(self) -> None:
        inventory = _inventory()
        section = bootstrap.SectionEnvelope(4, 3, 0, 128, 1, (), bytes(12))
        bootstrap.validate_envelope_against_inventory(section, inventory)
        block = bootstrap.CommonBlock(1, 4, 0, 3, 0, 0, 1, 12, bytes(12))
        bootstrap.validate_common_against_inventory(block, inventory)
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.validate_common_against_inventory(
                replace(block, semantic_copy_id=2), inventory
            )
        self.assertEqual(caught.exception.code, bootstrap.INVENTORY)
        self.assertEqual(bootstrap.dependency_closure(inventory, (2,), {2, 4}), (2, 4))
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.dependency_closure(inventory, (2,), {2})
        self.assertEqual(caught.exception.code, bootstrap.DEPENDENCY)

        cyclic_entries = list(inventory.entries)
        cyclic_entries[3] = replace(cyclic_entries[3], dependencies=(2,))
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.validate_inventory_closure(
                bootstrap.Inventory(tuple(cyclic_entries))
            )
        self.assertEqual(caught.exception.code, bootstrap.DEPENDENCY)

        root = bytes.fromhex("0005000e0000000400010001")
        frame = bootstrap.TierFrame(0, (4,), 16, 1, root)
        payload = bootstrap.encode_tier_frame(frame)
        self.assertEqual(len(payload), 38)
        envelope = bootstrap.SectionEnvelope(2, 2, 0, 128, 1, (4,), payload)
        bootstrap.validate_tier_against_inventory(frame, envelope, inventory)

    def test_tier_frame_assembles_one_exact_stream(self) -> None:
        projection = content.ContentAuthoringProjection(
            C.CONTENT_VERSION,
            (
                content.ContentRecordView(
                    1,
                    content.ContentAtomSchema(
                        C.ATOM_UNSIGNED, 1, (), min_value=0, max_value=1
                    ),
                ),
                content.ContentRecordView(2, content.ContentMatrix(1, 1, 1, (0,))),
                content.ContentRecordView(
                    3,
                    content.ContentRegionSet(
                        2,
                        (content.ContentRegion(1, 0, 0, 1, 0, 1, C.REGION_SELECTABLE),),
                    ),
                ),
                content.ContentRecordView(
                    4, content.ContentFeedback(C.FEEDBACK_NEUTRAL, 2, 0)
                ),
                content.ContentRecordView(
                    5,
                    content.ContentLessonNode(
                        C.ROLE_PRACTICE,
                        C.RESPONSE_SINGLE,
                        C.ANSWER_EXTERNAL,
                        0,
                        2,
                        3,
                        0,
                        0,
                        1,
                        2,
                        (),
                        4,
                        0,
                    ),
                ),
                content.ContentRecordView(6, content.ContentRoot(5, 2)),
            ),
        )
        expected = content.encode_content_v0(projection)
        root = expected[-12:]
        body = {4: expected[4:-12]}
        count = 6
        frame = bootstrap.TierFrame(0, (4,), len(expected), count, root)
        encoded = bootstrap.encode_tier_frame(frame)
        self.assertEqual(bootstrap.decode_tier_frame(encoded, 2), frame)
        self.assertEqual(bootstrap.assemble_content_stream(frame, body), expected)
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.encode_tier_frame(replace(frame, root_record_bytes=b"root"))
        self.assertEqual(caught.exception.code, bootstrap.TIER_FRAME)
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.assemble_content_stream(
                replace(frame, assembled_record_count=count + 1), body
            )
        self.assertEqual(caught.exception.code, bootstrap.TIER_FRAME)
        malformed_body = {4: body[4][:-1]}
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.assemble_content_stream(
                replace(frame, assembled_stream_byte_length=len(expected) - 1),
                malformed_body,
            )
        self.assertEqual(caught.exception.code, bootstrap.TIER_FRAME)
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.assemble_content_stream(frame, {})
        self.assertEqual(caught.exception.code, bootstrap.DEPENDENCY)

    def test_recipe_package_all_opcodes_and_exact_iterator_convention(self) -> None:
        self.assertEqual(
            set(RECIPE_FIXTURE),
            {
                "expected_outputs_hex",
                "inputs_hex",
                "package_hex",
                "profile_version",
                "recipe_id",
                "schema",
                "status",
            },
        )
        self.assertEqual(RECIPE_FIXTURE["schema"], "golden-board.recipe-v0-fixtures/v0")
        self.assertEqual(
            (
                RECIPE_FIXTURE["profile_version"],
                RECIPE_FIXTURE["recipe_id"],
                RECIPE_FIXTURE["status"],
            ),
            (1, 2, 0),
        )
        self.assertIs(type(RECIPE_FIXTURE["package_hex"]), str)
        self.assertTrue(
            all(type(value) is str for value in RECIPE_FIXTURE["inputs_hex"])
        )
        self.assertTrue(
            all(type(value) is str for value in RECIPE_FIXTURE["expected_outputs_hex"])
        )
        independently_built, independently_expected = _recipe_fixture()
        raw = bytes.fromhex(RECIPE_FIXTURE["package_hex"])
        inputs = tuple(bytes.fromhex(value) for value in RECIPE_FIXTURE["inputs_hex"])
        expected_outputs = tuple(
            bytes.fromhex(value) for value in RECIPE_FIXTURE["expected_outputs_hex"]
        )
        self.assertEqual(independently_built, raw)
        self.assertEqual(independently_expected, expected_outputs)
        package = bootstrap.decode_recipe_package(
            raw, RECIPE_FIXTURE["profile_version"]
        )
        self.assertEqual(package.encoded, raw)
        self.assertEqual(
            tuple(recipe.recipe_id for recipe in package.recipes), (1, 2, 3)
        )
        self.assertEqual(package.tables[0].payload, b"\x07\x08\x09")
        seen = {node.opcode for recipe in package.recipes for node in recipe.nodes}
        self.assertEqual(seen, set(range(1, 26)))
        result = bootstrap.evaluate_recipe(
            package,
            RECIPE_FIXTURE["recipe_id"],
            inputs,
        )
        self.assertEqual(
            result,
            bootstrap.RecipeResult(RECIPE_FIXTURE["status"], expected_outputs),
        )
        with self.assertRaises(AttributeError):
            package.profile_version = 2

    def test_recipe_runtime_failures_never_release_partial_outputs(self) -> None:
        raw, _ = _recipe_fixture()
        package = bootstrap.decode_recipe_package(raw, 1)
        # QUOT sees a zero divisor after earlier nodes have completed.
        limited = bootstrap.evaluate_recipe(
            package,
            2,
            (b"\x06", b"\x00", b"\xb6", b"abc", b"\x01"),
        )
        self.assertEqual(limited, bootstrap.RecipeResult(11, ()))
        # Recipe 3 writes its data output before emitting an explicit failure.
        explicit = bootstrap.evaluate_recipe(package, 3, ())
        self.assertEqual(explicit, bootstrap.RecipeResult(4, ()))
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            bootstrap.evaluate_recipe(
                package,
                2,
                (b"\x06", b"\x02", b"\xb6", b"abc", b"\x02"),
            )
        self.assertEqual(caught.exception.code, bootstrap.RECIPE)

    def test_recipe_duplicate_argument_releases_one_live_value_once(self) -> None:
        recipe, resources = _recipe_record(
            1,
            [],
            [(bootstrap.STATUS, 16), (bootstrap.UINT, 8)],
            [
                (1, 8, (), 0, 0xAA, bootstrap.UINT),
                (13, 8, (1, 1), 0, 0, bootstrap.UINT),
                (24, 16, (), 0, 0, bootstrap.STATUS),
                (5, 16, (3,), 1, 0, bootstrap.STATUS),
                (5, 16, (2,), 2, 0, bootstrap.STATUS),
            ],
            {},
        )
        package_bytes = 64 + len(recipe)
        raw = b"".join(
            (
                b"GBRECP0\0",
                b"\0\0\0\0",
                _be(1, 2),
                b"\0\0",
                _be(1, 2),
                b"\0\0",
                _be(5, 4),
                _be(4, 4),
                b"\0\0\0\0",
                _be(package_bytes, 4),
                _be(resources[0], 8),
                _be(resources[1], 4),
                bytes(16),
                recipe,
            )
        )
        package = bootstrap.decode_recipe_package(raw, 1)
        self.assertEqual(package.peak_live_scratch_bytes, 5)
        self.assertEqual(
            bootstrap.evaluate_recipe(package, 1, ()),
            bootstrap.RecipeResult(0, (b"\0",)),
        )

    def test_recipe_static_mutations_are_closed_and_atomic(self) -> None:
        raw, _ = _recipe_fixture()
        parsed = bootstrap.decode_recipe_package(raw, 1)

        def rejected(mutated: bytes, profile: int = 1) -> None:
            with self.assertRaises(bootstrap.BootstrapReject) as caught:
                bootstrap.decode_recipe_package(mutated, profile)
            self.assertEqual(caught.exception.code, bootstrap.RECIPE)

        rejected(raw, 2)
        unknown_profile = bytearray(raw)
        unknown_profile[12:14] = _be(8, 2)
        rejected(bytes(unknown_profile), 8)
        # Exact outer length can include the byte, but complete consumption cannot.
        trailing = bytearray(raw + b"\0")
        trailing[32:36] = _be(len(trailing), 4)
        rejected(bytes(trailing))
        # A BITS width-three table with nonzero final low bits fails table stage.
        unused_bits = bytearray(raw)
        unused_bits[66] = bootstrap.BITS
        unused_bits[68:72] = _be(3, 4)
        rejected(bytes(unused_bits))
        # Declared package peak is exact, not a permissive ceiling.
        scratch = bytearray(raw)
        scratch[44:48] = _be(int.from_bytes(raw[44:48], "big") + 1, 4)
        rejected(bytes(scratch))
        # Unknown opcode in the first recipe is rejected before evaluation.
        first_node = 64 + 19 + 32 + 4 * 12
        unknown = bytearray(raw)
        unknown[first_node + 2] = 26
        rejected(bytes(unknown))
        table_bytes = sum(16 + len(table.payload) for table in parsed.tables)
        kitchen = parsed.recipes[1]
        kitchen_start = 64 + table_bytes + parsed.recipes[0].recipe_bytes
        kitchen_nodes = (
            kitchen_start + 32 + 12 * (len(kitchen.inputs) + len(kitchen.outputs))
        )

        def kitchen_node_offset(node: bootstrap.RecipeNode) -> int:
            return kitchen_nodes + 32 * (node.node_id - 1)

        # Reserved status 15 cannot be introduced through FAILURE.
        failure = next(node for node in kitchen.nodes if node.opcode == 25)
        reserved = bytearray(raw)
        reserved[
            kitchen_node_offset(failure) + 24 : kitchen_node_offset(failure) + 32
        ] = _be(15, 8)
        rejected(bytes(reserved))
        # Moving the second UINT chunk left creates both overlap and a gap while
        # staying in-range, so this reaches the exact output-coverage stage.
        partial_slot = len(kitchen.outputs) - 2
        second_chunk = next(
            node
            for node in kitchen.nodes
            if node.opcode == 5
            and node.auxiliary_u16 == partial_slot
            and node.immediate_u64 == 8
        )
        overlap = bytearray(raw)
        overlap[
            kitchen_node_offset(second_chunk)
            + 24 : kitchen_node_offset(second_chunk)
            + 32
        ] = _be(7, 8)
        rejected(bytes(overlap))


if __name__ == "__main__":
    unittest.main()
