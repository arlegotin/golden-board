"""Two bounded source cases, independently checked against actual physical cells."""
from dataclasses import replace
import unittest

from golden_board import canonical_manifest
from golden_board.m2_formative_transfer_v2 import build_formative_transfer_v2
from golden_board.m2_recovery_recipe_v2 import evaluate_recovery_native
from . import test_m2_recovery_transfer_v2 as transfer_fixture


class FormativeTransfer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        transfer_fixture.RecoveryTransfer.setUpClass()
        cls.source = transfer_fixture.RecoveryTransfer
        cls.image = cls.source.image
        cls.cases = build_formative_transfer_v2(cls.image)

    def test_full_observations_preserve_all_other_cells_and_shell(self):
        clean = self.source.packed
        for case, factor, state in zip(self.cases, (2, 5), ('recovered', 'conflict'), strict=True):
            with self.subTest(case=case.name):
                self.assertEqual(case.factor, factor)
                self.assertEqual(case.expected_group_state, state)
                self.assertEqual(case.fragment_index, 2)
                self.assertNotEqual(case.section_id, 1)
                self.assertEqual(case.observation[:2], self.image.capacity_plan.side.to_bytes(2, 'big'))
                self.assertEqual(len(case.observation), 2+self.image.capacity_plan.side**2)
                actual = tuple((flat, value) for flat, value in enumerate(case.observation[2:])
                    if value != (clean[flat//8] >> (7-flat%8)) & 1)
                self.assertEqual(actual, case.edited_cells)
                for flat, _ in actual:
                    row, column = divmod(flat, self.image.capacity_plan.side)
                    width = self.image.capacity_plan.width
                    self.assertTrue(width <= row < self.image.capacity_plan.side-width)
                    self.assertTrue(width <= column < self.image.capacity_plan.side-width)
        self.assertEqual(tuple(case.name for case in self.cases), ('a', 'b'))
        self.assertEqual(len(self.cases[0].edited_cells), 10)
        self.assertNotEqual(self.cases[0].section_id, self.cases[1].section_id)

    def test_complete_carried_program_independently_agrees_with_case_properties(self):
        harness = self.source()
        harness.setUp()
        for case in self.cases:
            overrides = {flat: None if value == 2 else value for flat, value in case.edited_cells}
            pairs = harness.pairs(case.physical_first, case.factor, overrides)
            key = transfer_fixture.identity(case.expected_common)
            local = [evaluate_recovery_native(self.source.package, 120,
                (b'\1', b'\1', key, pair, *(bytes(432),)*4)) for pair in pairs[:case.factor]]
            self.assertEqual(tuple(row.outputs[0][0] for row in local),
                             (1, 1) if case.name == 'a' else (2, 1, 1, 1, 1))
            result = harness.recover(case.physical_first, overrides)
            self.assertEqual(result.status, 0)
            self.assertEqual(result.outputs, (b'\3', b'\1', case.expected_common)
                             if case.name == 'a' else (b'\4', b'\0', bytes(191)))
            self.assertEqual(case.expected_repetition_common, case.expected_common)
        self.assertEqual(self.cases[1].foreign_common, self.cases[0].expected_common)

    def test_deterministic_and_rejects_source_binding_or_selection_drift(self):
        self.assertEqual(build_formative_transfer_v2(self.image), self.cases)
        case = self.cases[0]
        flat = case.edited_cells[0][0]
        raw = bytearray(self.image.carrier)
        raw[4+flat//8] ^= 128 >> (flat%8)
        with self.assertRaisesRegex(ValueError, 'source-lane-binding'):
            build_formative_transfer_v2(replace(self.image, carrier=bytes(raw)))
        plan = replace(self.image.capacity_plan, sections=tuple(
            row for row in self.image.capacity_plan.sections if row.factor != 2))
        with self.assertRaises(ValueError):
            build_formative_transfer_v2(replace(self.image, capacity_plan=plan))

    def test_owner_metadata_is_canonical_manifest_data(self):
        for case in self.cases:
            owner = case.owner_manifest()
            raw = canonical_manifest.serialize_manifest(owner)
            self.assertEqual(canonical_manifest.validate_canonical_manifest(raw), owner)
        self.assertEqual(self.cases[0].owner_manifest()['foreign_common_sha256'], '0'*64)


if __name__ == '__main__':
    unittest.main()
