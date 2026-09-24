"""Independent physical witnesses cannot trust a retained ownership claim."""
from hashlib import sha256
import unittest
from unittest.mock import patch

from golden_board import canonical_manifest, identity, m2_physical_v2 as proof
from python.tests import test_m2_static_v2 as fixtures


class PhysicalEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.StaticProjection.setUpClass()
        cls.static = fixtures.StaticProjection.result
        cls.inputs = (cls.static.candidate_manifest, cls.static.capacity_ledger,
                      cls.static.ownership_ledger,cls.static.semantic_envelope)

    def rebound_inputs(self, ownership=None, route_length=None):
        candidate,capacity,raw,semantic = self.inputs
        raw = raw if ownership is None else canonical_manifest.serialize_manifest(ownership)
        value = canonical_manifest.validate_canonical_manifest(candidate)
        for row in value['files']:
            if row['path']=='ownership-ledger.json':
                row['bytes'],row['sha256']=len(raw),sha256(raw).hexdigest()
            if row['path']=='route-0.bin' and route_length is not None:
                row['bytes']=route_length
        del value['manifest_identity']
        value['manifest_identity']=identity.identity_hex(b'golden-board:manifest:v0\0',
            (canonical_manifest.serialize_manifest(value),))
        return canonical_manifest.serialize_manifest(value),capacity,raw,semantic

    def test_complete_new_geometry_has_exact_fresh_witnesses(self):
        raw = proof.build_physical_evidence_v2(*self.inputs)
        value = canonical_manifest.validate_canonical_manifest(raw)
        self.assertEqual(value['scope'], 'physical-predicates-only')
        self.assertNotIn('summary', value)
        self.assertEqual([r['witness_count'] for r in value['predicate_rows']],
                         [3297856,4161600,863744,3297024,4161600,2688768,58776,1098])
        self.assertTrue(all(r['result']=='pass' and r['violation_count']==0
                            for r in value['predicate_rows']),value['predicate_rows'])

    def test_changed_raw_ownership_or_noninteger_geometry_rejects(self):
        candidate, capacity, ownership, semantic = self.inputs
        value = canonical_manifest.validate_canonical_manifest(ownership)
        value['side'] = True
        changed = canonical_manifest.serialize_manifest(value)
        with self.assertRaises(proof.PhysicalEvidenceError):
            proof.admit_physical_inputs(candidate,capacity,changed,semantic)
        manifest = canonical_manifest.validate_canonical_manifest(candidate)
        for row in manifest['files']:
            if row['path']=='ownership-ledger.json':
                row['bytes'],row['sha256'] = len(changed),sha256(changed).hexdigest()
        del manifest['manifest_identity']
        manifest['manifest_identity'] = identity.identity_hex(b'golden-board:manifest:v0\0',
            (canonical_manifest.serialize_manifest(manifest),))
        with self.assertRaises(proof.PhysicalEvidenceError):
            proof.admit_physical_inputs(canonical_manifest.serialize_manifest(manifest),capacity,changed,semantic)

    def test_wrong_lane_cell_digest_is_counted_even_with_valid_input_binding(self):
        candidate = proof.admit_physical_inputs(*self.inputs)
        bad = dict(candidate.ownership)
        bad['unit_rows'] = [list(row) for row in bad['unit_rows']]
        bad['unit_rows'][0][1] = '0'*64
        from dataclasses import replace
        result = proof.group_evidence(replace(candidate,ownership=bad))
        self.assertEqual(result[0],1)
        self.assertTrue(result[1][0])

    def test_missing_group_member_cannot_shrink_lane_pair_witnesses(self):
        from dataclasses import replace
        candidate = proof.admit_physical_inputs(*self.inputs)
        units=[dict(row) for row in candidate.units]
        units[0]['fragment_index']=1
        witnesses,violations=proof.separation_evidence(replace(candidate,units=tuple(units)))
        self.assertEqual(witnesses,2688768)
        self.assertGreaterEqual(violations,4*1728)

    def test_d2_witness_uses_the_owned_damage_square_not_separation_window(self):
        candidate = proof.admit_physical_inputs(*self.inputs)
        physical_cells = set()
        inverse = type(candidate).inverse

        def first_anchor(actual, side):
            self.assertIs(actual,candidate)
            self.assertEqual(side,56)  # owned I=1816 damage square
            return ((112,112),)

        def record_inverse(actual, physical):
            physical_cells.add(physical)
            return inverse(actual,physical)

        with patch.object(proof,'_d2_placements',side_effect=first_anchor), \
                patch.object(type(candidate),'inverse',new=record_inverse):
            proof.closure_evidence(candidate)
        self.assertEqual(physical_cells,
                         {row*1816+column for row in range(56) for column in range(56)})

    def test_shell_span_class_cannot_be_relabelled_as_headroom(self):
        ownership=canonical_manifest.validate_canonical_manifest(self.inputs[2])
        spans=ownership['shell_rows'][0][-1]
        self.assertEqual(spans[0],[0,816,'instruction'])
        spans[0][2]='headroom'
        result=canonical_manifest.validate_canonical_manifest(
            proof.build_physical_evidence_v2(*self.rebound_inputs(ownership)))
        rows={row['predicate_id']:row for row in result['predicate_rows']}
        self.assertGreater(rows['shell-sector-total-partition']['violation_count'],0)
        self.assertGreater(rows['owner-factor-ledger-reconciliation']['violation_count'],0)
        self.assertEqual(rows['shell-sector-total-partition']['witness_count'],863744)

    def test_route_prefix_length_is_cross_bound_to_shell_extent(self):
        with self.assertRaises(proof.PhysicalEvidenceError):
            proof.admit_physical_inputs(*self.rebound_inputs(route_length=1))

    def test_missing_or_wrong_existing_dependency_targets_keep_exact_witnesses(self):
        from dataclasses import replace
        candidate=proof.admit_physical_inputs(*self.inputs)
        groups=(False,)*len(candidate.group_specs())
        counts={'all-cells':candidate.side**2}
        self.assertEqual(proof.inventory_evidence(candidate,groups,counts),(1098,0))
        for deps,violations in (([100,101,102],4),([17,18],2)):
            sections=tuple(dict(row,dependency_ids=deps) if row['section_id']==2 else row
                           for row in candidate.sections)
            with self.subTest(dependencies=deps):
                self.assertEqual(proof.inventory_evidence(
                    replace(candidate,sections=sections),groups,counts),(1098,violations))


if __name__=='__main__':
    unittest.main()
