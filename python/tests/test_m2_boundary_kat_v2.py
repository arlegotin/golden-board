"""Boundary receipts require fresh current receiver execution."""
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from golden_board import canonical_manifest,bootstrap
from golden_board import m2_boundary_kat_v2 as kat

ROOT=Path(__file__).resolve().parents[2]

class BoundaryKatsV2(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owners=tuple((ROOT/'spec'/name).read_bytes() for name in (
            'profile-policy-v2.toml','profile-limits-v2.toml','damage-policy-v2.toml'))

    def test_all_four_receipts_execute_owned_semantics_in_order(self):
        rows=kat.boundary_kat_results_v2(*self.owners)
        self.assertEqual(len(rows),4)
        for i,raw in enumerate(rows):
            self.assertEqual(canonical_manifest.validate_canonical_manifest(raw),dict(
                schema='golden-board.m2-boundary-kat-result/v2',kat_id=kat.KAT_IDS[i],result='pass'))
            self.assertEqual(raw,kat.boundary_kat_result_v2(i,*self.owners))

    def test_invalid_ordinals_and_stale_owners_reject(self):
        for ordinal in (True,False,-1,4,1<<64,'0',None):
            with self.subTest(ordinal=ordinal),self.assertRaises(ValueError):
                kat.boundary_kat_result_v2(ordinal,*self.owners)
        with self.assertRaises(ValueError):kat.boundary_kat_result_v2(0,b'',*self.owners[1:])

    def test_ceiling_observes4096_actual_checks_for_one_sorted_section_identity(self):
        observed=[]
        decode=bootstrap.decode_section_envelope
        def compared(raw):
            observed.append(raw)
            return decode(raw)
        with patch.object(bootstrap,'decode_section_envelope',side_effect=compared):
            raw=kat.boundary_kat_result_v2(3,*self.owners)
        self.assertEqual(canonical_manifest.validate_canonical_manifest(raw)['result'],'pass')
        self.assertEqual(len(observed),4096)
        self.assertEqual(observed,sorted(set(observed)))
        self.assertEqual({decode(raw).section_id for raw in observed},{4004})

    def test_actual_product_failure_is_not_replaced_by_saved_pass(self):
        from golden_board.m2_decoder_v2 import ObservationDecoderV2
        from golden_board.m2_decoder import DecoderError
        with patch.object(ObservationDecoderV2,'_aggregate_v7_group',side_effect=DecoderError('physical-group')):
            raw=kat.boundary_kat_result_v2(0,*self.owners)
        self.assertEqual(canonical_manifest.validate_canonical_manifest(raw)['result'],'fail')

    def test_missing_attempt_ceiling_is_losing_evidence(self):
        from golden_board.m2_resources_v2 import ResourceMeterV2
        with patch.object(ResourceMeterV2,'section',return_value=None):
            raw=kat.boundary_kat_result_v2(3,*self.owners)
        self.assertEqual(canonical_manifest.validate_canonical_manifest(raw)['result'],'fail')

    def test_conflict_cannot_be_resolved_by_first_candidate(self):
        recover=bootstrap.recover_logical_section
        def first_candidate(witnesses):
            rows=tuple(witnesses)
            return recover(rows[:1])
        with patch.object(bootstrap,'recover_logical_section',side_effect=first_candidate):
            raw=kat.boundary_kat_result_v2(2,*self.owners)
        self.assertEqual(canonical_manifest.validate_canonical_manifest(raw)['result'],'fail')
