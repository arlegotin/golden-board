"""Source-side semantic oracle remains separate from production acquisition."""
from dataclasses import replace
from unittest.mock import patch
import os
import unittest

from python.tests import test_m2_damage_v2 as fixtures
from golden_board.m2_damage_oracle_v2 import DamageOracleV2


class RevisedDamageOracle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.RevisedDamageObservations.setUpClass()
        cls.corpus = fixtures.RevisedDamageObservations.corpus
        cls.oracle = DamageOracleV2(cls.corpus)

    def test_clean_and_missing_replica_are_derived_without_production_decoder(self):
        with patch('golden_board.m2_decoder.ObservationDecoder.decode',side_effect=AssertionError('oracle called decoder')):
            clean = self.oracle.evaluate(self.corpus.case('D5',0))
            missing = self.oracle.evaluate(self.corpus.case('D4',0))
        self.assertEqual(clean.artifact_state,'exact')
        self.assertEqual(missing.artifact_state,'exact')
        self.assertEqual(clean.required_stream,missing.required_stream)
        self.assertEqual(clean.all_stream,missing.all_stream)
        self.assertEqual(clean.wrong_accepts,0)
        self.assertEqual(missing.wrong_accepts,0)
        self.assertEqual(missing.section_states[0],(1,'verified'))

    def test_checked_malformed_content_cannot_be_returned_as_a_stream(self):
        clean = self.oracle.evaluate(self.corpus.case('D5',0))
        for ordinal in (0,6,7,13,14,15,16,17,18,19):
            expected = self.oracle.evaluate(self.corpus.boundary_case(ordinal))
            required_valid = 7 <= ordinal <= 13 or 17 <= ordinal <= 19
            with self.subTest(ordinal=ordinal):
                self.assertEqual(expected.artifact_state,'degraded' if required_valid else 'failure')
                self.assertEqual(expected.required_stream,clean.required_stream if required_valid else None)
                self.assertIsNone(expected.all_stream)
                self.assertTrue(expected.reauthored_boundary)

    def test_compact_and_foreign_bootstrap_never_establish_content(self):
        for ordinal in (408,413,414):
            value = self.oracle.evaluate(self.corpus.case('D7',ordinal))
            self.assertEqual(value.artifact_state,'failure')
            self.assertIsNone(value.required_stream)
            self.assertIsNone(value.all_stream)
            self.assertEqual(value.wrong_accepts,0)

    def test_reauthenticated_different_section_is_a_wrong_accept_even_with_both_streams(self):
        section = next(s for s in self.corpus.sections.values() if s.section_type==6)
        payload = bytes((section.payload[0]^1,))+section.payload[1:]
        replacements = self.corpus._changed_payload(section.section_id,payload)
        case = replace(self.corpus.case('D5',0),observation=self.corpus._units(replacements))
        # This deliberately reauthored diagnostic is not an owned corpus case.
        with self.assertRaises(ValueError):
            self.oracle.evaluate(case)
        value = self.oracle._evaluate_observation(case)
        self.assertEqual(value.artifact_state,'exact')
        self.assertIsNotNone(value.required_stream)
        self.assertIsNotNone(value.all_stream)
        self.assertEqual(value.wrong_accepts,1)
        self.assertFalse(value.reauthored_boundary)

    def test_forced_rejection_requires_exact_owned_observation_bytes(self):
        case = self.corpus.case('D7',408)
        forged = replace(case,observation=self.corpus.case('D0',0).observation)
        with self.assertRaises(ValueError):
            self.oracle.evaluate(forged)

    @unittest.skipUnless(os.environ.get('GB_M2_DAMAGE_V2_PREFLIGHT')=='1',
                         'explicit bounded revised observation/semantic preflight')
    def test_source_oracle_and_observation_receiver_agree(self):
        from golden_board.m2_decoder_v2 import ObservationDecoderV2
        owners = tuple((fixtures.ROOT/'spec'/name).read_bytes() for name in (
            'profile-policy-v2.toml','profile-limits-v2.toml','damage-policy-v2.toml'))
        decoder = ObservationDecoderV2(*owners)
        cases = [('D0',0),('D0',7),('D1',0),('D2',0),('D3',0),('D3',96),
            ('D4',0),('D6',0),('D7',0),('D7',10),('D7',16),('D7',401),('D7',402),
            ('D7',405),('D7',408),('D7',413),('D7',414)]
        cases.extend(('B0',i) for i in range(21))
        for family,ordinal in cases:
            case = self.corpus.boundary_case(ordinal) if family=='B0' else self.corpus.case(family,ordinal)
            expected = self.oracle.evaluate(case)
            actual = decoder.decode(case.channel,case.observation)
            with self.subTest(case=case.case_id):
                self.assertEqual(actual.artifact_state,expected.artifact_state)
                self.assertEqual(actual.m2_required_stream,expected.required_stream)
                self.assertEqual(actual.m2_all_stream,expected.all_stream)
                self.assertEqual(actual.section_results,expected.semantic_result.section_results)
                self.assertEqual(actual.fragment_diagnostics,expected.semantic_result.fragment_diagnostics)
                if family!='B0':
                    self.assertEqual(expected.wrong_accepts,0)
            print('semantic preflight',case.case_id,actual.artifact_state,flush=True)


if __name__ == '__main__':
    unittest.main()
