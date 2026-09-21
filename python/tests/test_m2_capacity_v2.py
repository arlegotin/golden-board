from pathlib import Path
import unittest

from golden_board import bootstrap_v2, capacity, curriculum, m2_policy
from golden_board.m2_slice import compile_slice_v0
from golden_board.m2_slice_v1 import compile_slice_v1
from golden_board.m2_capacity_v2 import build_capacity_plan

ROOT = Path(__file__).resolve().parents[2]


class CompressedCapacity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths = ('studies/m2/slice-v0.json', 'conformance/content-v0.json',
                 'conformance/chess-v0.json', 'reports/game-set-v0.bin',
                 'spec/content-v0.md', 'spec/constants-v0.toml', 'spec/curriculum-v0.toml')
        raws = tuple(ROOT.joinpath(p).read_bytes() for p in paths)
        cls.legacy = compile_slice_v0(*raws)
        cls.compiled = compile_slice_v1(ROOT.joinpath('studies/m2/slice-v1.json').read_bytes(), *raws)
        cls.blueprint = curriculum.load_blueprint(raws[-1])
        cls.policy = m2_policy.load_profile_policy(ROOT.joinpath('spec/profile-policy-v0.toml').read_bytes()).capacity_policy

    def plan(self, lengths=(25000,)*4):
        return build_capacity_plan(self.compiled, self.legacy, self.blueprint, self.policy, lengths)

    def test_complete_costs_keep_future_allowance_and_uncompressed_reserve(self):
        plan = self.plan()
        self.assertEqual(plan.authoring_bytes, 105277)
        self.assertEqual(plan.reserve_bytes, 9353)
        self.assertEqual(sum(len(s.payload) for s in plan.sections if s.section_type == 3), 25929)
        self.assertEqual(sum(len(s.payload) for s in plan.sections if s.section_type == 3 and s.factor == 5), 12804)
        self.assertEqual({s.section_id for s in plan.sections if s.factor == 5}, bootstrap_v2.SPINE)
        self.assertEqual(sum(s.factor*s.fragments for s in plan.sections), plan.units)
        self.assertEqual(plan.units*1728 + plan.pad_cells, (plan.side-2*plan.width)**2)
        self.assertLessEqual(plan.side, 2048)
        self.assertTrue(all(0 < len(s.payload) <= 16384 for s in plan.sections))
        self.assertEqual(len(plan.inventory.entries), len(plan.sections))
        inv_section, = (s for s in plan.sections if s.section_id == 1)
        self.assertEqual(bootstrap_v2.decode_inventory(inv_section.payload), plan.inventory)

    def test_smaller_route_selects_first_geometry_and_oversize_rejects(self):
        plan = self.plan((23000,)*4)
        self.assertEqual(plan.search_rows[-1][2], 'fit')
        self.assertTrue(all(r[2] != 'fit' for r in plan.search_rows[:-1]))
        self.assertEqual((plan.side, plan.width), plan.search_rows[-1][:2])
        for lengths in ((30000,)*4, (25000,)*3, (True,)*4, (1.5,)*4):
            with self.subTest(lengths=lengths), self.assertRaises(ValueError):
                self.plan(lengths)

    def test_real_sections_roundtrip_and_probes_are_not_discounted(self):
        from golden_board import bootstrap
        plan = self.plan()
        raw = {s.section_id: bootstrap.encode_section_envelope(bootstrap.SectionEnvelope(
            s.section_id, s.section_type, s.version, s.closure, 1, s.dependencies, s.payload))
            for s in plan.sections}
        recovered = bootstrap_v2.recover_content(raw)
        self.assertEqual(recovered.required_bytes, self.compiled.required_content_bytes)
        self.assertEqual(recovered.all_bytes, self.compiled.content_bytes)
        self.assertEqual(sum(len(s.payload) for s in plan.sections if s.section_type == 4), 105277)
        self.assertEqual(sum(len(s.payload) for s in plan.sections if s.section_type == 5), 9353)
        self.assertTrue(all(s.version == 0 for s in plan.sections if s.section_type in (4, 5, 6)))
        total = sum(len(s.payload) for s in plan.sections if s.section_type in (4, 5, 6))
        fill = capacity.probe_fill_bytes(self.compiled.content_sha256, total+(plan.pad_cells+7)//8)
        self.assertEqual(b''.join(s.payload for s in plan.sections if s.section_type in (4,5,6)), fill[:total])
        self.assertEqual(plan.pad_bytes, fill[total:])


if __name__ == '__main__':
    unittest.main()
