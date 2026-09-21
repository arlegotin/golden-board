from pathlib import Path
import unittest

from golden_board import bootstrap, curriculum, m2_policy
from golden_board.m2_slice import compile_slice_v0
from golden_board.m2_slice_v1 import compile_slice_v1
from golden_board.m2_carrier_v2 import build_development_carrier, recover_clean_matrix
from golden_board.m2_mapping_v2 import map_unit_bit

ROOT = Path(__file__).resolve().parents[2]


class RevisedCarrier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths = ('studies/m2/slice-v0.json', 'conformance/content-v0.json',
                 'conformance/chess-v0.json', 'reports/game-set-v0.bin',
                 'spec/content-v0.md', 'spec/constants-v0.toml', 'spec/curriculum-v0.toml')
        raws = tuple(ROOT.joinpath(p).read_bytes() for p in paths)
        legacy = compile_slice_v0(*raws)
        cls.compiled = compile_slice_v1(ROOT.joinpath('studies/m2/slice-v1.json').read_bytes(), *raws)
        blueprint = curriculum.load_blueprint(raws[-1])
        policy = m2_policy.load_profile_policy(ROOT.joinpath('spec/profile-policy-v0.toml').read_bytes()).capacity_policy
        cls.image = build_development_carrier(cls.compiled, legacy, blueprint, policy)

    def test_actual_matrix_recovers_exact_required_and_all_streams(self):
        plan = self.image.capacity_plan
        result = recover_clean_matrix(self.image.carrier, plan.width)
        self.assertEqual(result.required_bytes, self.compiled.required_content_bytes)
        self.assertEqual(result.all_bytes, self.compiled.content_bytes)
        self.assertEqual(len(result.checked_section_ids), len(plan.sections))
        self.assertEqual(len(self.image.carrier), 4+plan.side**2//8)
        self.assertLessEqual(len(self.image.carrier)-4, 524288)

    def test_every_oriented_shell_contains_its_complete_route_and_cells_have_owners(self):
        plan = self.image.capacity_plan
        packed = self.image.carrier[4:]
        for sector, prefix in enumerate(self.image.route_prefixes):
            recovered = bytearray(len(prefix))
            for bit in range(len(prefix)*8):
                row, column = bootstrap.sector_cell(plan.side, plan.width, sector, bit)
                index = row*plan.side+column
                recovered[bit//8] |= ((packed[index//8] >> (7-index%8)) & 1) << (7-bit%8)
            self.assertEqual(bytes(recovered), prefix)
        self.assertEqual(sum(self.image.owner_cell_counts), plan.side**2)
        self.assertEqual(self.image.owner_cell_counts[-1], plan.pad_cells)

    def test_clean_checker_rejects_damage_instead_of_reporting_a_clean_pass(self):
        plan = self.image.capacity_plan
        # Flip the same physical encoded bit in each inventory lane. The
        # ordinary codec may correct it, but it no longer passes a clean check.
        raw = bytearray(self.image.carrier)
        for unit_id in range(1, 6):
            physical = map_unit_bit(plan.side, plan.width, unit_id, 0)
            row, column = divmod(physical, plan.side-2*plan.width)
            bit = (row+plan.width)*plan.side+column+plan.width
            raw[4+bit//8] ^= 1 << (7-bit%8)
        with self.assertRaisesRegex(ValueError, 'clean-group-not-verified'):
            recover_clean_matrix(bytes(raw), plan.width)
        for bad in (self.image.carrier[:-1], self.image.carrier+b'\0', b'\0'*4):
            with self.assertRaises(ValueError):
                recover_clean_matrix(bad, plan.width)


if __name__ == '__main__':
    unittest.main()
