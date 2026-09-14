"""Independent checks for the candidate-neutral common route recipes."""

from __future__ import annotations

from pathlib import Path
import unittest

from golden_board import bootstrap, m2_common_recipe, m2_route_data


ROOT = Path(__file__).resolve().parents[2]
ROUTE_DATA = (ROOT / "spec/route-data-v0.json").read_bytes()


def _crc32c(raw: bytes) -> int:
    value = 0xFFFFFFFF
    for byte in raw:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0x82F63B78 if value & 1 else 0)
    return value ^ 0xFFFFFFFF


def _crc64(raw: bytes) -> int:
    value = 0
    for byte in raw:
        value ^= byte << 56
        for _ in range(8):
            value = (
                ((value << 1) & 0xFFFFFFFFFFFFFFFF)
                ^ (0x42F0E1EBA9EA3693 if value >> 63 else 0)
            )
    return value


class CommonRecipeTests(unittest.TestCase):
    def test_every_profile_is_canonical_and_has_only_shared_exports(self) -> None:
        expected = tuple(range(101, 108)) + tuple(range(109, 113))
        for version in range(1, 7):
            with self.subTest(version=version):
                raw = m2_common_recipe.common_recipe_package(version)
                package = bootstrap.decode_recipe_package(raw, version)
                exports = tuple(
                    recipe.recipe_id
                    for recipe in package.recipes
                    if recipe.recipe_id >= 101
                )
                self.assertEqual(exports, expected)
                self.assertNotIn(30, exports)
                self.assertNotIn(108, exports)
                self.assertEqual(package.encoded, raw)

    def test_all_frozen_examples_and_sector_masks_execute(self) -> None:
        profiles = m2_route_data.load_route_data_manifest(ROUTE_DATA)
        for version, facts in enumerate(profiles, 1):
            package = bootstrap.decode_recipe_package(
                m2_common_recipe.common_recipe_package(version), version
            )
            recipes = {
                recipe.recipe_id: (package, recipe)
                for recipe in package.recipes
            }
            common = tuple(fact for fact in facts if fact.fact_id != 8)
            for mask in m2_route_data.SECTOR_MASKS:
                with self.subTest(version=version, mask=mask):
                    rows = m2_route_data._check_examples(common, recipes, mask)
                    self.assertEqual(len(rows), 11)

    def test_crc_entries_are_general_procedures_not_kat_selectors(self) -> None:
        vectors = (
            bytes(9),
            bytes.fromhex("ff1020304050607080"),
            bytes.fromhex("a55a00ffc33c96690f"),
        )
        crc32_package = bootstrap.decode_recipe_package(
            m2_common_recipe.common_recipe_package(1), 1
        )
        crc64_package = bootstrap.decode_recipe_package(
            m2_common_recipe.common_recipe_package(2), 2
        )
        for raw in vectors:
            with self.subTest(raw=raw.hex()):
                crc32 = bootstrap.evaluate_recipe(crc32_package, 107, (raw,))
                crc64 = bootstrap.evaluate_recipe(crc64_package, 111, (raw,))
                self.assertEqual(crc32.status, 0)
                self.assertEqual(crc64.status, 0)
                self.assertEqual(int.from_bytes(crc32.outputs[0], "big"), _crc32c(raw))
                self.assertEqual(int.from_bytes(crc64.outputs[0], "big"), _crc64(raw))

    def test_mapping_uses_dynamic_geometry_and_profile_constant(self) -> None:
        logical = 987_654_321
        side = 100
        width = 10
        interior = side - 2 * width
        population = interior * interior
        for version in range(1, 7):
            package = bootstrap.decode_recipe_package(
                m2_common_recipe.common_recipe_package(version), version
            )
            result = bootstrap.evaluate_recipe(
                package,
                109,
                (
                    logical.to_bytes(4, "big"),
                    side.to_bytes(2, "big"),
                    width.to_bytes(2, "big"),
                ),
            )
            offset = (40_503 * version + width * 257) % population
            expected = ((2 * interior - 1) * (logical % population) + offset) % population
            self.assertEqual(result.status, 0)
            self.assertEqual(int.from_bytes(result.outputs[0], "big"), expected)

    def test_mapping_rejects_invalid_frozen_geometry_without_eager_failure(self) -> None:
        package = bootstrap.decode_recipe_package(
            m2_common_recipe.common_recipe_package(1), 1
        )
        for side, width in ((0, 0), (17, 17), (17, 18), (2_049, 1)):
            with self.subTest(side=side, width=width):
                result = bootstrap.evaluate_recipe(
                    package,
                    109,
                    (
                        (1).to_bytes(4, "big"),
                        side.to_bytes(2, "big"),
                        width.to_bytes(2, "big"),
                    ),
                )
                self.assertEqual(result.status, 3)
                self.assertEqual(result.outputs, ())

    def test_transform_covers_all_eight_coordinates_and_polarities(self) -> None:
        package = bootstrap.decode_recipe_package(
            m2_common_recipe.common_recipe_package(1), 1
        )
        row, column, side = 2, 5, 8
        coordinates = (
            (row, column),
            (side - 1 - column, row),
            (side - 1 - row, side - 1 - column),
            (column, side - 1 - row),
            (row, side - 1 - column),
            (side - 1 - column, side - 1 - row),
            (side - 1 - row, column),
            (column, row),
        )
        for transform, (mapped_row, mapped_column) in enumerate(coordinates):
            for polarity in (0, 1):
                result = bootstrap.evaluate_recipe(
                    package,
                    102,
                    (
                        bytes((transform,)),
                        bytes((polarity,)),
                        row.to_bytes(2, "big"),
                        column.to_bytes(2, "big"),
                        side.to_bytes(2, "big"),
                        b"\x01",
                    ),
                )
                self.assertEqual(result.status, 0)
                self.assertEqual(
                    int.from_bytes(result.outputs[0], "big"),
                    mapped_row * side + mapped_column,
                )
                self.assertEqual(result.outputs[1], bytes((1 ^ polarity,)))


if __name__ == "__main__":
    unittest.main()
