"""Compact wire preserves the complete validated recipe program and admission."""
from dataclasses import replace
import json
from pathlib import Path
import unittest

from golden_board import bootstrap, m2_recipe, recipe_wire_v1


ROOT = Path(__file__).resolve().parents[2]


def changed(raw, offset, width, value):
    result = bytearray(raw)
    result[offset:offset + width] = value.to_bytes(width, "big")
    return bytes(result)


def layout(raw):
    """Locate fields in valid fixture bytes without using the codec under test."""
    read = lambda offset, width: int.from_bytes(raw[offset:offset + width], "big")
    cursor = 64
    tables = []
    for _ in range(read(18, 2)):
        tables.append(cursor)
        cursor += 16 + read(cursor + 12, 4)
    recipes = {}
    for _ in range(read(16, 2)):
        count = read(cursor + 8, 4)
        nodes = cursor + 32 + 12 * (read(cursor + 4, 2) + read(cursor + 6, 2))
        recipes[read(cursor, 2)] = (cursor, nodes, count)
        cursor += read(cursor + 28, 4)
    assert cursor == len(raw)
    return tables, recipes


def node_size(node):
    return (6 + 2 * len(node.arguments) + 2 * (node.opcode in (2, 5, 22))
            + 8 * (node.opcode in (1, 5, 14, 22, 25)))


def node_positions(recipe, start):
    result = {}
    for node in recipe.nodes:
        result[node.node_id] = start
        start += node_size(node)
    return result


class CompactRecipeWire(unittest.TestCase):
    codec = recipe_wire_v1

    @classmethod
    def setUpClass(cls):
        cls.raw = m2_recipe.build_r3_recipe_package()
        cls.fixture = json.loads((ROOT / "conformance/recipe-v0.json").read_bytes())
        cls.fixture_raw = bytes.fromhex(cls.fixture["package_hex"])

    def rejected(self, operation, *args):
        with self.assertRaises(bootstrap.BootstrapReject) as caught:
            operation(*args)
        self.assertEqual(caught.exception.code, bootstrap.RECIPE)

    def test_current_package_exact_round_trip_and_undiscounted_resources(self):
        encoded = self.codec.encode_recipe_package_v1(self.raw, 7)
        package = self.codec.decode_recipe_package_v1(encoded, 7)
        logical = bootstrap.decode_recipe_package(self.raw, 7)
        self.assertEqual((len(self.raw), len(encoded)), (25_930, 11_664))
        self.assertEqual(encoded[8:12], b"\0\1\0\0")
        self.assertEqual(int.from_bytes(encoded[32:36], "big"), len(encoded))
        self.assertEqual(package.encoded, encoded)
        self.assertEqual(package.profile_version, 7)
        self.assertEqual(package.logical, logical)
        self.assertEqual(self.codec.expand_recipe_package_v1(encoded, 7), self.raw)
        self.assertEqual(self.codec.encode_recipe_package_v1(self.raw, 7), encoded)
        self.assertEqual((logical.total_node_count, logical.total_edge_count,
                          logical.maximum_primitive_steps, logical.peak_live_scratch_bytes),
                         (699, 1087, 80435, 6163))
        tables, recipes = layout(encoded)
        self.assertEqual(len(tables), 13)
        self.assertEqual(len(recipes), 22)
        for recipe in logical.recipes:
            start, _, _ = recipes[recipe.recipe_id]
            self.assertEqual(int.from_bytes(encoded[start + 28:start + 32], "big"),
                             32 + 12 * (len(recipe.inputs) + len(recipe.outputs))
                             + sum(node_size(node) for node in recipe.nodes))

    def test_all_opcodes_and_nonzero_emit_offsets_preserve_literal_results(self):
        encoded = self.codec.encode_recipe_package_v1(self.fixture_raw, 1)
        package = self.codec.decode_recipe_package_v1(encoded, 1)
        self.assertEqual(self.codec.expand_recipe_package_v1(encoded, 1), self.fixture_raw)
        self.assertEqual({node.opcode for recipe in package.logical.recipes
                          for node in recipe.nodes}, set(range(1, 26)))
        self.assertTrue(any(node.opcode == 5 and node.immediate_u64
                            for recipe in package.logical.recipes for node in recipe.nodes))
        inputs = tuple(bytes.fromhex(value) for value in self.fixture["inputs_hex"])
        expected = tuple(bytes.fromhex(value) for value in self.fixture["expected_outputs_hex"])
        self.assertEqual(self.codec.evaluate_recipe_v1(package, 2, inputs),
                         bootstrap.RecipeResult(0, expected))

    def test_diagnostic_profiles_one_through_eight_do_not_widen_old_admission(self):
        for profile in range(1, 9):
            with self.subTest(profile=profile):
                raw = changed(self.fixture_raw, 12, 2, profile)
                encoded = self.codec.encode_recipe_package_v1(raw, profile)
                package = self.codec.decode_recipe_package_v1(encoded, profile)
                self.assertEqual(self.codec.expand_recipe_package_v1(encoded, profile), raw)
                self.assertEqual(self.codec.evaluate_recipe_v1(package, 3, ()),
                                 bootstrap.RecipeResult(4, ()))
                self.rejected(bootstrap.decode_recipe_package, encoded, profile)
                if profile == 8:
                    self.rejected(bootstrap.decode_recipe_package, raw, profile)
                    self.rejected(bootstrap.evaluate_recipe, package.logical, 3, ())
                else:
                    self.assertEqual(bootstrap.decode_recipe_package(raw, profile).encoded, raw)
        for profile in (False, True, 0, 9, 65535):
            self.rejected(self.codec.encode_recipe_package_v1, self.fixture_raw, profile)
            self.rejected(self.codec.decode_recipe_package_v1, encoded, profile)
        self.rejected(self.codec.decode_recipe_package_v1, encoded, 7)

    def test_header_counts_lengths_versions_and_expansion_are_bounded(self):
        raw = self.codec.encode_recipe_package_v1(self.raw, 7)
        mutations = [(8, 2, 0), (8, 2, 2), (10, 2, 1), (14, 2, 1),
                     (16, 2, 0), (16, 2, 257), (18, 2, 4097),
                     (20, 4, 0), (20, 4, 65536), (24, 4, 262141),
                     (28, 4, bootstrap.RECIPE_PACKAGE_MAX + 1),
                     (32, 4, len(raw) - 1), (36, 8, bootstrap.RECIPE_STEP_MAX + 1),
                     (44, 4, bootstrap.RECIPE_SCRATCH_MAX + 1), (48, 1, 1)]
        for offset, width, value in mutations:
            with self.subTest(offset=offset, value=value):
                self.rejected(self.codec.decode_recipe_package_v1,
                              changed(raw, offset, width, value), 7)
        for malformed in (b"", raw[:63], raw[:-1], raw + b"\0", bytearray(raw),
                          b"X" + raw[1:], bytes(bootstrap.RECIPE_PACKAGE_MAX + 1)):
            self.rejected(self.codec.decode_recipe_package_v1, malformed, 7)
        trailing = changed(raw + b"\0", 32, 4, len(raw) + 1)
        self.rejected(self.codec.decode_recipe_package_v1, trailing, 7)
        too_large = raw + bytes(600_000)
        too_large = changed(changed(too_large, 32, 4, len(too_large)), 20, 4, 65535)
        self.rejected(self.codec.decode_recipe_package_v1, too_large, 7)

    def test_recipe_counts_tables_and_descriptor_fields_reject_atomically(self):
        raw = self.codec.encode_recipe_package_v1(self.fixture_raw, 1)
        tables, recipes = layout(raw)
        start, nodes, count = recipes[1]
        mutations = [(start + 2, 2, 1), (start + 4, 2, 65), (start + 6, 2, 0),
                     (start + 8, 4, 0), (start + 8, 4, 65536),
                     (start + 12, 4, bootstrap.RECIPE_EDGE_MAX + 1),
                     (start + 16, 8, bootstrap.RECIPE_STEP_MAX + 1),
                     (start + 24, 4, bootstrap.RECIPE_SCRATCH_MAX + 1),
                     (start + 28, 4, 32),
                     (start + 32 + 3, 1, 1), (tables[0] + 3, 1, 1),
                     (tables[0] + 8, 4, 0xffffffff), (tables[0] + 12, 4, 0xffffffff)]
        for offset, width, value in mutations:
            with self.subTest(offset=offset, value=value):
                self.rejected(self.codec.decode_recipe_package_v1,
                              changed(raw, offset, width, value), 1)
        bad_bits = changed(changed(raw, tables[0] + 2, 1, bootstrap.BITS),
                           tables[0] + 4, 4, 3)
        self.rejected(self.codec.decode_recipe_package_v1, bad_bits, 1)

    def test_unknown_opcodes_forward_refs_types_and_output_coverage_reject(self):
        raw = self.codec.encode_recipe_package_v1(self.fixture_raw, 1)
        package = bootstrap.decode_recipe_package(self.fixture_raw, 1)
        _, recipes = layout(raw)
        kitchen = package.recipes[1]
        node_start = recipes[kitchen.recipe_id][1]
        positions = node_positions(kitchen, node_start)
        position = lambda node: positions[node.node_id]
        constant = next(node for node in kitchen.nodes if node.opcode == 1)
        binary = next(node for node in kitchen.nodes if node.opcode == 6)
        emit = next(node for node in kitchen.nodes if node.opcode == 5 and node.immediate_u64 == 8)
        failure = next(node for node in kitchen.nodes if node.opcode == 25)
        mutations = [(position(constant), 1, 0), (position(constant), 1, 26),
                     (position(binary) + 6, 2, len(kitchen.inputs) + binary.node_id),
                     (position(binary) + 1, 1, 255),
                     (position(emit) + 10, 8, 7), (position(failure) + 6, 8, 15)]
        for offset, width, value in mutations:
            with self.subTest(offset=offset, value=value):
                malformed = changed(raw, offset, width, value)
                self.rejected(self.codec.decode_recipe_package_v1, malformed, 1)
                self.rejected(self.codec.expand_recipe_package_v1, malformed, 1)

    def test_derived_resource_declarations_are_exact_not_discounted(self):
        raw = self.codec.encode_recipe_package_v1(self.raw, 7)
        _, recipes = layout(raw)
        first = recipes[1][0]
        for offset, width in ((20, 4), (24, 4), (28, 4), (36, 8), (44, 4),
                              (first + 12, 4), (first + 16, 8), (first + 24, 4)):
            value = int.from_bytes(raw[offset:offset + width], "big")
            with self.subTest(offset=offset):
                self.rejected(self.codec.decode_recipe_package_v1,
                              changed(raw, offset, width, value + 1), 7)

    def test_encoder_validates_omitted_fields_and_original_wire(self):
        _, recipes = layout(self.fixture_raw)
        node = recipes[1][1]
        for offset, width, value in ((node, 2, 2), (node + 8, 2, 4),
                                      (node + 16, 2, 1), (node + 20, 4, 1)):
            self.rejected(self.codec.encode_recipe_package_v1,
                          changed(self.fixture_raw, offset, width, value), 1)
        compact = self.codec.encode_recipe_package_v1(self.fixture_raw, 1)
        self.rejected(self.codec.encode_recipe_package_v1, compact, 1)
        self.rejected(self.codec.encode_recipe_package_v1, bytearray(self.fixture_raw), 1)

    def test_every_opcode_requires_all_assigned_fields_within_its_recipe(self):
        raw = self.codec.encode_recipe_package_v1(self.fixture_raw, 1)
        logical = bootstrap.decode_recipe_package(self.fixture_raw, 1)
        _, recipes = layout(raw)
        seen, earlier_nodes = set(), 0
        for ordinal, recipe in enumerate(logical.recipes, 1):
            start, node_start, _ = recipes[recipe.recipe_id]
            positions = node_positions(recipe, node_start)
            for node in recipe.nodes:
                if node.opcode in seen:
                    continue
                seen.add(node.opcode)
                # Cut inside the prefix and each assigned argument/aux/immediate.
                field_ends = [1, 2, 6] + [8 + 2 * index for index in range(len(node.arguments))]
                end = 6 + 2 * len(node.arguments)
                if node.opcode in (2, 5, 22):
                    end += 2
                    field_ends.append(end)
                if node.opcode in (1, 5, 14, 22, 25):
                    end += 8
                    field_ends.append(end)
                for field_end in field_ends:
                    boundary = positions[node.node_id] + field_end - 1
                    malformed = raw[:boundary]
                    for offset, width, value in (
                        (16, 2, ordinal), (20, 4, earlier_nodes + node.node_id),
                        (32, 4, boundary), (start + 8, 4, node.node_id),
                        (start + 28, 4, boundary - start),
                    ):
                        malformed = changed(malformed, offset, width, value)
                    with self.subTest(opcode=node.opcode, field_end=field_end):
                        self.rejected(self.codec.decode_recipe_package_v1, malformed, 1)
            earlier_nodes += len(recipe.nodes)
        self.assertEqual(seen, set(range(1, 26)))

    def test_recipe_trailing_field_and_fixed24_experiment_have_no_fallback(self):
        raw = self.codec.encode_recipe_package_v1(self.fixture_raw, 1)
        _, recipes = layout(raw)
        start = recipes[1][0]
        length = int.from_bytes(raw[start + 28:start + 32], "big")
        boundary = start + length
        extra_field = raw[:boundary] + b"\0" + raw[boundary:]
        extra_field = changed(changed(extra_field, 32, 4, len(extra_field)),
                              start + 28, 4, length + 1)
        self.rejected(self.codec.decode_recipe_package_v1, extra_field, 1)
        logical = bootstrap.decode_recipe_package(self.fixture_raw, 1)
        table_end = 64 + sum(16 + len(table.payload) for table in logical.tables)
        fixed = bytearray(self.fixture_raw[:table_end])
        fixed[8:10] = b"\0\1"
        _, expanded_layout = layout(self.fixture_raw)
        for recipe in logical.recipes:
            start, nodes, _ = expanded_layout[recipe.recipe_id]
            header = bytearray(self.fixture_raw[start:nodes])
            header[28:32] = (recipe.recipe_bytes - 8 * len(recipe.nodes)).to_bytes(4, "big")
            fixed.extend(header)
            for index in range(len(recipe.nodes)):
                node = self.fixture_raw[nodes + index * 32:nodes + (index + 1) * 32]
                fixed.extend(node[2:8] + node[10:20] + node[24:32])
        fixed[32:36] = len(fixed).to_bytes(4, "big")
        self.rejected(self.codec.decode_recipe_package_v1, bytes(fixed), 1)

    def test_expanded_package_limit_is_checked_before_allocation(self):
        nodes = 65535
        recipe_bytes = 32 + 12 + 6 * nodes
        header = bytearray(self.fixture_raw[:64])
        for offset, width, value in ((8, 2, 1), (16, 2, 1), (18, 2, 0),
                                     (20, 4, nodes), (24, 4, 0), (28, 4, 0),
                                     (32, 4, 64 + recipe_bytes), (36, 8, nodes), (44, 4, 2)):
            header[offset:offset + width] = value.to_bytes(width, "big")
        recipe = bytearray(32)
        for offset, width, value in ((0, 2, 1), (6, 2, 1), (8, 4, nodes),
                                     (16, 8, nodes), (24, 4, 2), (28, 4, recipe_bytes)):
            recipe[offset:offset + width] = value.to_bytes(width, "big")
        descriptor = bytes.fromhex("000105000000001000000001")
        raw = bytes(header + recipe) + descriptor + bytes.fromhex("180500000010") * nodes
        self.assertLess(len(raw), bootstrap.RECIPE_PACKAGE_MAX)
        self.assertGreater(64 + 32 + 12 + 32 * nodes, bootstrap.RECIPE_PACKAGE_MAX)
        self.rejected(self.codec.decode_recipe_package_v1, raw, 1)

    def test_evaluation_reparses_compact_bytes_and_ignores_forged_cached_logical_state(self):
        compact = self.codec.encode_recipe_package_v1(self.raw, 7)
        package = self.codec.decode_recipe_package_v1(compact, 7)
        corrupt_cache = replace(package.logical, profile_version=8, recipes=(),
                                tables=(), total_node_count=0, encoded=b"invalid")
        forged = replace(package, logical=corrupt_cache)
        self.assertEqual(self.codec.evaluate_recipe_v1(forged, 107, (b"123456789",)),
                         bootstrap.RecipeResult(0, (bytes.fromhex("e3069283"),)))
        invalid_wire = replace(package, encoded=changed(compact, 8, 2, 0))
        self.rejected(self.codec.evaluate_recipe_v1, invalid_wire, 107, (b"123456789",))
        self.rejected(self.codec.evaluate_recipe_v1, replace(package, profile_version=8), 107,
                      (b"123456789",))
        with self.assertRaises(TypeError):
            self.codec.evaluate_recipe_v1(package.logical, 107, (b"123456789",))
        with self.assertRaises(AttributeError):
            package.encoded = b"bad"

    def test_crc_checked_overflow_and_explicit_failure_release_no_partial_output(self):
        compact = self.codec.encode_recipe_package_v1(self.raw, 7)
        package = self.codec.decode_recipe_package_v1(compact, 7)
        for recipe, inputs, expected in (
            (107, (b"123456789",), bootstrap.RecipeResult(0, (bytes.fromhex("e3069283"),))),
            (107, (bytes(range(9)),), bootstrap.RecipeResult(0, (bytes.fromhex("7144c5a8"),))),
            (105, (bytes.fromhex("ffffffff"),), bootstrap.RecipeResult(11, ())),
            (105, (bytes.fromhex("00123456"),), bootstrap.RecipeResult(0, (bytes.fromhex("00123457"),))),
        ):
            with self.subTest(recipe=recipe, inputs=inputs):
                self.assertEqual(self.codec.evaluate_recipe_v1(package, recipe, inputs), expected)
        fixture = self.codec.decode_recipe_package_v1(
            self.codec.encode_recipe_package_v1(self.fixture_raw, 1), 1)
        self.assertEqual(self.codec.evaluate_recipe_v1(fixture, 3, ()), bootstrap.RecipeResult(4, ()))
        self.assertEqual(self.codec.evaluate_recipe_v1(fixture, 2,
                         (b"\x06", b"\0", b"\xb6", b"abc", b"\1")),
                         bootstrap.RecipeResult(11, ()))


if __name__ == "__main__":
    unittest.main()
