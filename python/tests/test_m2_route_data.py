"""Result-free tests for the frozen M2 route-data owner and sector ledger."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import unittest
from unittest import mock

from golden_board import (
    bootstrap,
    canonical_manifest,
    m2_common_recipe,
    m2_recipe,
    m2_route_data,
)


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_RAW = (ROOT / "spec/route-data-v0.json").read_bytes()
R3_OWNER_FIXTURE_RAW = (ROOT / "conformance/m2-r3-owner-v1.json").read_bytes()


class RouteDataFreezeTests(unittest.TestCase):
    def test_r3_template_route_and_logical_example_charge_are_exact(self) -> None:
        template = m2_route_data.render_r3_route_data_template(
            R3_OWNER_FIXTURE_RAW
        )
        self.assertEqual(len(template), 8_011)
        self.assertEqual(
            sha256(template).hexdigest(),
            "2d6e83c1a396a0c4fc83caada7bd1b04e6ca60a4275eae630690fdde4c58c8c1",
        )
        package = m2_recipe.build_r3_recipe_package()
        candidate = m2_route_data.CandidateRouteData(
            "eh72-hier-r5-r2-r1-crc32c-v0",
            7,
            "eh72-hier-repetition-v0",
            "crc32c-v0",
            (package,),
        )
        images = m2_route_data.build_r3_route_images(candidate, 2_040, 128)
        prefixes = tuple(
            sector.data[: sector.route_prefix_cells // 8]
            for sector in images.sectors
        )
        self.assertEqual(tuple(map(len, prefixes)), (29_091,) * 4)
        self.assertEqual(
            tuple(sha256(prefix).hexdigest() for prefix in prefixes),
            (
                "a3a9ac59b857af3904d2bff998bd96c36ccba4d8a97180ad8e0e9d4434b92395",
                "4da3722a786890647ece291a3fbcb14ba9f2c6a847c13088f2c47792a52c861a",
                "7c55f1be66239d4c48a0760217a31d0cd36b30a8d04ac91c17a67315a04c4fbb",
                "5daca7964260360c62877969618e5756a946ee2d5f2b2d78756e29f5c63d44a1",
            ),
        )
        self.assertEqual(
            sha256(b"".join(prefixes)).hexdigest(),
            "a3a6c9fc8a67d5cc36d0d75f74464fbeac2819d7b6bd8048206aa19d6cbd7922",
        )
        self.assertEqual(
            m2_route_data.r3_route_resource_metrics(candidate),
            m2_route_data.R3RouteResourceMetrics(15_134, 6_163),
        )

    def test_tracked_manifest_is_exact_canonical_owner(self) -> None:
        self.assertEqual(MANIFEST_RAW, m2_route_data.render_route_data_manifest())
        self.assertEqual(
            sha256(MANIFEST_RAW).hexdigest(),
            "965a3e35ceb4b5a92a7715b3fcde20cc3019f8c9d9efa533abd93b051bb86641",
        )
        profiles = m2_route_data.load_route_data_manifest(MANIFEST_RAW)
        self.assertEqual(len(profiles), 6)
        for facts in profiles:
            self.assertEqual(tuple(item.fact_id for item in facts), tuple(range(1, 13)))
            self.assertEqual(
                tuple(item.recipe_id for item in facts),
                (101, 102, 103, 104, 105, 106, 107, 30, 109, 110, 111, 112),
            )
            self.assertTrue(all(item.definition.value_type == bootstrap.BYTES for item in facts))
            self.assertTrue(all(item.mask_input_slots for item in facts))

    def test_candidate_rows_freeze_family_check_and_profile_variants(self) -> None:
        profiles = m2_route_data.load_route_data_manifest(MANIFEST_RAW)
        eh = profiles[0][7]
        rs = profiles[4][7]
        self.assertEqual(tuple(item.width for item in eh.source_inputs), (8,))
        self.assertEqual(tuple(item.width for item in eh.inputs), (9, 1, 3))
        self.assertEqual(tuple(item.width for item in eh.outputs), (8,))
        self.assertEqual(tuple(item.width for item in rs.source_inputs), (191,))
        self.assertEqual(tuple(item.width for item in rs.inputs), (255, 1, 64))
        self.assertEqual(tuple(item.width for item in rs.outputs), (191,))
        self.assertEqual(eh.encoder_recipe_id, 108)
        self.assertEqual(rs.encoder_recipe_id, 108)
        self.assertEqual(profiles[0][10].outputs[0].width, 32)
        self.assertEqual(profiles[1][10].outputs[0].width, 64)
        self.assertEqual(
            tuple((item.value_type, item.width) for item in profiles[0][8].inputs),
            ((bootstrap.UINT, 32), (bootstrap.UINT, 16), (bootstrap.UINT, 16)),
        )
        self.assertEqual(
            tuple((item.value_type, item.width) for item in profiles[0][8].outputs),
            ((bootstrap.UINT, 32),),
        )
        self.assertEqual(profiles[0][8].mask_input_slots, (1,))
        self.assertEqual(len(eh.worked_input), 13)
        self.assertEqual(len(eh.worked_output), 2 + 8)
        self.assertEqual(len(rs.worked_input), 320)
        self.assertEqual(len(rs.worked_output), 2 + 191)
        self.assertEqual(eh.source_mask_mode, "whole-value-xor-v0")
        self.assertEqual(rs.source_mask_mode, "common-block-payload-xor-recrc32c-v0")
        self.assertEqual(len(rs.worked_sector_sources), 4)
        self.assertEqual(len(rs.held_sector_sources), 4)
        self.assertNotEqual(profiles[4][7].worked_source, profiles[5][7].worked_source)
        self.assertEqual(
            bootstrap.decode_common_block(rs.worked_source, 5).profile_version, 5
        )

    def test_transport_examples_freeze_encoder_damage_decoder_chain(self) -> None:
        profiles = m2_route_data.load_route_data_manifest(MANIFEST_RAW)
        eh = profiles[0][7]
        rs = profiles[4][7]
        self.assertEqual(eh.recipe_id, 30)
        self.assertEqual((eh.worked_damage_offset, eh.worked_damage_xor), (0, 0x80))
        self.assertEqual((eh.held_damage_offset, eh.held_damage_xor), (8, 0x01))
        self.assertEqual(eh.worked_input, b"\x80" + bytes(12))
        self.assertEqual(eh.held_input[:9].hex(), "11121a2a9e26af36df")
        self.assertEqual(eh.held_input[9:], bytes(4))
        self.assertEqual(eh.worked_output, b"\0\0" + eh.worked_source)
        self.assertEqual(eh.held_output, b"\0\0" + eh.held_source)
        self.assertEqual((rs.worked_damage_offset, rs.worked_damage_xor), (0, 0x53))
        self.assertEqual((rs.held_damage_offset, rs.held_damage_xor), (254, 0x53))
        expected_worked = bytearray(m2_route_data._rs255_191_encode(rs.worked_source))
        expected_worked[0] ^= 0x53
        expected_held = bytearray(m2_route_data._rs255_191_encode(rs.held_source))
        expected_held[254] ^= 0x53
        self.assertEqual(rs.worked_input, bytes(expected_worked) + bytes(65))
        self.assertEqual(rs.held_input, bytes(expected_held) + bytes(65))
        self.assertEqual(rs.held_input[255:], bytes(65))
        self.assertEqual(rs.worked_output, b"\0\0" + rs.worked_source)
        self.assertEqual(rs.held_output, b"\0\0" + rs.held_source)

    def test_selective_masks_preserve_structural_slots_and_disjoint_examples(self) -> None:
        facts = m2_route_data.load_route_data_manifest(MANIFEST_RAW)[0]
        transform = facts[1]
        original = m2_route_data._split_values(transform.worked_input, transform.inputs, "test")
        for mask in m2_route_data.SECTOR_MASKS:
            masked_raw = m2_route_data._mask_input(
                transform.worked_input,
                transform.inputs,
                transform.mask_input_slots,
                mask,
            )
            masked = m2_route_data._split_values(masked_raw, transform.inputs, "test")
            self.assertEqual(masked[:5], original[:5])
            expected_bit = int.from_bytes(original[5], "big") ^ (mask & 1)
            self.assertEqual(int.from_bytes(masked[5], "big"), expected_bit)
        for fact in facts:
            for sector, mask in enumerate(m2_route_data.SECTOR_MASKS):
                if fact.encoder_recipe_id is None:
                    worked = m2_route_data._mask_input(
                        fact.worked_source,
                        fact.source_inputs,
                        fact.mask_input_slots,
                        mask,
                    )
                    held = m2_route_data._mask_input(
                        fact.held_source,
                        fact.source_inputs,
                        fact.mask_input_slots,
                        mask,
                    )
                else:
                    worked = fact.worked_sector_sources[sector]
                    held = fact.held_sector_sources[sector]
                self.assertNotEqual(worked, held)

    def test_nonzero_mask_wrong_recipe_output_is_rejected_by_owner_oracle(self) -> None:
        fact = m2_route_data.load_route_data_manifest(MANIFEST_RAW)[0][0]
        package = bootstrap.decode_recipe_package(
            m2_common_recipe.common_recipe_package(1), 1
        )
        recipe = next(item for item in package.recipes if item.recipe_id == 101)
        recipes = {101: (package, recipe)}
        mutant = bootstrap.RecipeResult(0, (b"\0",))
        with mock.patch.object(
            m2_route_data.bootstrap, "evaluate_recipe", return_value=mutant
        ):
            with self.assertRaisesRegex(
                m2_route_data.RouteDataError,
                "independent-example:1:worked:3c",
            ):
                m2_route_data._check_examples((fact,), recipes, 0x3C)

    def test_mapping_oracle_rejects_geometry_outside_the_frozen_domain(self) -> None:
        fact = m2_route_data.load_route_data_manifest(MANIFEST_RAW)[0][8]
        for side, width in ((0, 0), (17, 17), (17, 18), (2_049, 1)):
            with self.subTest(side=side, width=width):
                recipe_input = b"".join(
                    (
                        (1).to_bytes(4, "big"),
                        side.to_bytes(2, "big"),
                        width.to_bytes(2, "big"),
                    )
                )
                with self.assertRaisesRegex(
                    m2_route_data.RouteDataError, "expected-mapping-domain"
                ):
                    m2_route_data._expected_nontransport_output(
                        1, fact, recipe_input
                    )

    def test_nontransport_masked_outputs_have_one_exact_owner_digest(self) -> None:
        frozen = bytearray()
        for profile_version, facts in enumerate(
            m2_route_data.load_route_data_manifest(MANIFEST_RAW), 1
        ):
            for fact in facts:
                if fact.fact_id == 8:
                    continue
                for mask in m2_route_data.SECTOR_MASKS:
                    for label, source in (
                        (0, fact.worked_source),
                        (1, fact.held_source),
                    ):
                        recipe_input = m2_route_data._mask_input(
                            source,
                            fact.source_inputs,
                            fact.mask_input_slots,
                            mask,
                        )
                        output = m2_route_data._expected_nontransport_output(
                            profile_version, fact, recipe_input
                        )
                        frozen.extend(
                            bytes((profile_version, fact.fact_id, mask, label))
                        )
                        frozen.extend(len(recipe_input).to_bytes(2, "big"))
                        frozen.extend(recipe_input)
                        frozen.extend(len(output).to_bytes(2, "big"))
                        frozen.extend(output)
        self.assertEqual(len(frozen), 10_032)
        self.assertEqual(
            sha256(frozen).hexdigest(),
            "96e371d452f31ca80a296a4fea793d86b369c7f018262f9f0ab1bb9f9badd59c",
        )

    def test_rs_sector_sources_mask_only_payload_and_recompute_local_crc(self) -> None:
        profiles = m2_route_data.load_route_data_manifest(MANIFEST_RAW)
        for profile_version in (5, 6):
            fact = profiles[profile_version - 1][7]
            for canonical, sources in (
                (fact.worked_source, fact.worked_sector_sources),
                (fact.held_source, fact.held_sector_sources),
            ):
                base = bootstrap.decode_common_block(canonical, profile_version)
                self.assertEqual(len(base.payload), 157)
                for mask, source in zip(
                    m2_route_data.SECTOR_MASKS, sources, strict=True
                ):
                    decoded = bootstrap.decode_common_block(source, profile_version)
                    self.assertEqual(source[:30], canonical[:30])
                    self.assertEqual(
                        decoded.payload,
                        bytes(value ^ mask for value in base.payload),
                    )
                    self.assertEqual(
                        decoded,
                        bootstrap.CommonBlock(
                            base.profile_version,
                            base.section_id,
                            base.semantic_copy_id,
                            base.section_type,
                            base.section_version,
                            base.fragment_index,
                            base.fragment_count,
                            base.section_envelope_length,
                            decoded.payload,
                        ),
                    )

    def test_dependency_linter_rejects_every_definition_ablation(self) -> None:
        for fact_id in range(1, 13):
            with self.subTest(fact_id=fact_id):
                ablated = m2_route_data.ablated_manifest(MANIFEST_RAW, fact_id)
                with self.assertRaises(m2_route_data.RouteDataError):
                    m2_route_data.lint_route_data_manifest(ablated)

    def test_dependency_linter_rejects_first_use_before_definition(self) -> None:
        manifest = canonical_manifest.validate_canonical_manifest(MANIFEST_RAW)
        manifest["facts"][4]["consumes"] = [3, 12]
        changed = canonical_manifest.serialize_manifest(manifest)
        with self.assertRaisesRegex(m2_route_data.RouteDataError, "knowledge-use:5"):
            m2_route_data.lint_route_data_manifest(changed)

    def test_dependency_linter_rejects_unused_definition(self) -> None:
        manifest = canonical_manifest.validate_canonical_manifest(MANIFEST_RAW)
        manifest["facts"][2]["consumes"] = []
        manifest["facts"][3]["consumes"] = [2]
        manifest["facts"][4]["consumes"] = [4]
        changed = canonical_manifest.serialize_manifest(manifest)
        with self.assertRaisesRegex(m2_route_data.RouteDataError, "unused-definition"):
            m2_route_data.lint_route_data_manifest(changed)

    def test_table_and_package_records_are_literal_complete_duplicates(self) -> None:
        fixture = canonical_manifest.validate_canonical_manifest(
            (ROOT / "conformance/recipe-v0.json").read_bytes()
        )
        package = bootstrap.decode_recipe_package(bytes.fromhex(fixture["package_hex"]), 1)
        facts = m2_route_data.load_route_data_manifest(MANIFEST_RAW)[0]
        examples = tuple(
            (
                (fact.worked_input, fact.worked_output),
                (fact.held_input, fact.held_output),
            )
            for fact in facts
        )
        records, owners = m2_route_data._build_records(0, facts, (package,), examples)
        self.assertEqual(len(owners), 40)
        table_wire = m2_route_data._table_wire(package.tables[0])
        self.assertIn(table_wire, records)
        self.assertIn(package.encoded, records)
        self.assertEqual(sum(name.startswith("worked:") for name, _ in owners), 12)
        self.assertEqual(sum(name.startswith("held-out:") for name, _ in owners), 12)

    def test_full_sector_ledger_is_exact_contiguous_and_deterministic(self) -> None:
        candidate = m2_route_data.CandidateRouteData(
            "eh72-r2-crc32c-v0", 1, "eh72-replicated-v0", "crc32c-v0", (b"x",)
        )
        route_parts = tuple(bytes((sector,)) * 128 for sector in range(4))
        owners = tuple((("synthetic-record", (128 - 64) * 8),) for _ in range(4))
        image = m2_route_data._assemble_route_images(candidate, route_parts, owners, 2_048, 128)
        self.assertEqual(image.instruction_cells, 4 * 128 * 8)
        self.assertEqual(image.headroom_cells, 1_024)
        self.assertEqual(len(image.sectors), 4)
        for sector in image.sectors:
            self.assertEqual(len(sector.data), 30_720)
            self.assertEqual(sector.route_prefix_cells, 1_024)
            self.assertEqual(sector.headroom_cells, 256)
            self.assertEqual(sector.spans[0].start_cell, 0)
            self.assertEqual(
                sector.spans[-1].start_cell + sector.spans[-1].cell_count,
                m2_route_data.SECTOR_CAPACITY_CELLS,
            )
            for left, right in zip(sector.spans, sector.spans[1:]):
                self.assertEqual(left.start_cell + left.cell_count, right.start_cell)
        again = m2_route_data._assemble_route_images(candidate, route_parts, owners, 2_048, 128)
        self.assertEqual(image, again)
        self.assertNotEqual(image.sectors[0].data, image.sectors[1].data)

    def test_sector_fit_charges_headroom_beyond_the_prefix(self) -> None:
        candidate = m2_route_data.CandidateRouteData(
            "eh72-r2-crc32c-v0", 1, "eh72-replicated-v0", "crc32c-v0", (b"x",)
        )
        route_parts = tuple(bytes(30_720) for _ in range(4))
        owners = tuple((("synthetic-record", (30_720 - 64) * 8),) for _ in range(4))
        with self.assertRaisesRegex(m2_route_data.RouteDataError, "sector-fit"):
            m2_route_data._assemble_route_images(candidate, route_parts, owners, 2_048, 128)

    def test_sector_geometry_is_explicit_bounded_and_changes_capacity(self) -> None:
        candidate = m2_route_data.CandidateRouteData(
            "eh72-r2-crc32c-v0", 1, "eh72-replicated-v0", "crc32c-v0", (b"x",)
        )
        route_parts = tuple(bytes((sector,)) * 64 for sector in range(4))
        owners = tuple((('synthetic-record', 0),) for _ in range(4))
        image = m2_route_data._assemble_route_images(
            candidate, route_parts, owners, 128, 8
        )
        self.assertEqual(len(image.sectors[0].data), 120)
        for side, width in ((56, 8), (65, 8), (128, 7), (128, 64)):
            with self.subTest(side=side, width=width):
                with self.assertRaisesRegex(
                    m2_route_data.RouteDataError, "sector-geometry"
                ):
                    m2_route_data._assemble_route_images(
                        candidate, route_parts, owners, side, width
                    )

    def test_builder_fails_closed_without_all_exported_recipes(self) -> None:
        fixture = canonical_manifest.validate_canonical_manifest(
            (ROOT / "conformance/recipe-v0.json").read_bytes()
        )
        candidate = m2_route_data.CandidateRouteData(
            "eh72-r2-crc32c-v0",
            1,
            "eh72-replicated-v0",
            "crc32c-v0",
            (bytes.fromhex(fixture["package_hex"]),),
        )
        with self.assertRaisesRegex(m2_route_data.RouteDataError, "missing-exported-recipe"):
            m2_route_data.build_route_images(MANIFEST_RAW, candidate, 2_048, 128)

    def test_exact_owner_rejects_canonical_but_mutated_data(self) -> None:
        manifest = canonical_manifest.validate_canonical_manifest(MANIFEST_RAW)
        manifest["sector_capacity_bytes"] += 1
        changed = canonical_manifest.serialize_manifest(manifest)
        with self.assertRaisesRegex(m2_route_data.RouteDataError, "manifest-drift"):
            m2_route_data.load_route_data_manifest(changed)


if __name__ == "__main__":
    unittest.main()
