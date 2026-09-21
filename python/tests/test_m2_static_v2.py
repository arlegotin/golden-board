"""Static facts come from actual current bytes and preserve losing evidence."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import unittest

from golden_board import canonical_manifest, curriculum, identity, m2_policy
from golden_board.m2_carrier_v2 import build_development_carrier
from golden_board.m2_policy_v2 import load_decoder_policy_v2
from golden_board.m2_route_v2 import build_route_images_v2
from golden_board.m2_slice import compile_slice_v0
from golden_board.m2_slice_v1 import compile_slice_v1
from golden_board.m2_static_v2 import build_static_projection_v2, StaticProjectionError

ROOT = Path(__file__).resolve().parents[2]


class StaticProjection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources = tuple((ROOT/p).read_bytes() for p in (
            'studies/m2/slice-v0.json','conformance/content-v0.json',
            'conformance/chess-v0.json','reports/game-set-v0.bin',
            'spec/content-v0.md','spec/constants-v0.toml','spec/curriculum-v0.toml'))
        cls.prototype = compile_slice_v0(*sources)
        cls.compiled = compile_slice_v1((ROOT/'studies/m2/slice-v1.json').read_bytes(),*sources)
        cls.blueprint = curriculum.load_blueprint(sources[-1])
        cls.neutral = (ROOT/'spec/profile-policy-v0.toml').read_bytes()
        cls.policy = load_decoder_policy_v2(*((ROOT/'spec'/p).read_bytes() for p in (
            'profile-policy-v2.toml','profile-limits-v2.toml','damage-policy-v2.toml')))
        cls.image = build_development_carrier(cls.compiled,cls.prototype,cls.blueprint,
                                             m2_policy.load_profile_policy(cls.neutral).capacity_policy)
        cls.routes = build_route_images_v2(cls.compiled,cls.image.capacity_plan.side,cls.image.capacity_plan.width)
        cls.result = cls.build()

    @classmethod
    def build(cls, image=None, routes=None):
        return build_static_projection_v2(cls.compiled,cls.prototype,cls.blueprint,cls.neutral,
            cls.image if image is None else image, cls.routes if routes is None else routes,
            policy_v2=cls.policy)

    def doc(self, name):
        return canonical_manifest.validate_canonical_manifest(getattr(self.result,name))

    def test_byte_cell_and_logical_reserve_reconcile(self):
        capacity = self.doc('capacity_ledger')
        ledger = capacity['ledger']
        physical = sum(ledger[key] for key in ('replicated_payload_bytes','envelope_header_bytes',
            'section_check_bytes','fragment_header_bytes','fragment_zero_pad_bytes',
            'local_check_bytes','transport_pad_bytes','parity_bytes'))
        self.assertEqual(physical,216*self.image.capacity_plan.units)
        self.assertEqual(ledger['encoded_transport_bytes'],physical)
        self.assertEqual(ledger['unused_cells'],0)
        self.assertEqual(ledger['total_cells'],self.image.capacity_plan.side**2)
        semantic = self.doc('semantic_envelope')['totals']
        before = semantic['content_capacity_before_reserve_bytes']
        self.assertEqual(semantic['reserve_payload_bytes'],max(382,(before+18)//19))
        self.assertGreater(semantic['real_decoded_body_payload_bytes'],semantic['real_stored_body_payload_bytes'])
        self.assertEqual(semantic['authoring_payload_bytes'],105277)

    def test_cross_hashes_self_exclusion_and_static_scope(self):
        candidate = self.doc('candidate_manifest')
        expected = dict(candidate)
        digest = expected.pop('manifest_identity')
        self.assertEqual(digest,identity.identity_hex(b'golden-board:manifest:v0\0',
            (canonical_manifest.serialize_manifest(expected),)))
        self.assertNotIn('candidate-manifest.json',[row['path'] for row in candidate['files']])
        for row in candidate['files']:
            path = row['path']
            raw = self.image.carrier if path == 'carrier.bin' else self.image.route_prefixes[int(path[6])] if path.startswith('route-') else getattr(self.result,path[:-5].replace('-','_'))
            self.assertEqual((row['bytes'],row['sha256']),(len(raw),sha256(raw).hexdigest()))
        limits = self.doc('static_limits')
        self.assertEqual(limits['scope'],'static-construction-only')
        self.assertEqual(limits['declared_transport']['scope'],'one-pass-complete-inventory-groups')
        self.assertNotIn('damage',limits)
        self.assertEqual(limits['selected_manifestation']['carrier_file_bytes'],4+limits['selected_manifestation']['carrier_bytes'])

    def test_complete_search_ownership_and_density(self):
        search = self.doc('geometry_search')
        self.assertEqual(search['rows'],[list(row) for row in self.image.capacity_plan.search_rows])
        self.assertEqual(sum(row[2] == 'fit' for row in search['rows']),1)
        ownership = self.doc('ownership_ledger')
        self.assertEqual(ownership['cell_table']['row_count'],self.image.capacity_plan.side**2)
        self.assertEqual(ownership['interior_fixed_pad']['fill_order'],'affine-images-of-ascending-logical-tail')
        density = self.doc('density_ledger')
        interior = density['scope_rows'][-1]
        self.assertEqual(interior['one_count']+interior['zero_count'],(self.image.capacity_plan.side-2*self.image.capacity_plan.width)**2)
        self.assertIn(self.doc('static_limits')['realism']['result'],('pass','fail'))

    def test_actual_corrupt_matrix_and_forged_plan_reject(self):
        raw = bytearray(self.image.carrier)
        raw[4] ^= 128
        with self.assertRaises(StaticProjectionError):
            self.build(image=replace(self.image,carrier=bytes(raw)))
        plan = replace(self.image.capacity_plan,reserve_bytes=self.image.capacity_plan.reserve_bytes-1)
        with self.assertRaises(StaticProjectionError):
            self.build(image=replace(self.image,capacity_plan=plan))
        with self.assertRaises(StaticProjectionError):
            self.build(image=replace(self.image,carrier=self.image.carrier+b'\0'))


if __name__ == '__main__':
    unittest.main()
