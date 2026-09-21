"""Arbitrary observation boundaries outside the enumerated damage corpus."""
from pathlib import Path
import unittest
from golden_board import bootstrap, canonical_manifest, m2_codec, m2_damage, m2_decoder
from golden_board.m2_decoder_v2 import ObservationDecoderV2

ROOT = Path(__file__).resolve().parents[2]


class ObservationBoundariesV2(unittest.TestCase):
    def setUp(self):
        self.decoder = ObservationDecoderV2(*(ROOT.joinpath('spec', name).read_bytes() for name in (
            'profile-policy-v2.toml', 'profile-limits-v2.toml', 'damage-policy-v2.toml')))

    def test_checked_complete_conflict_preserves_section_and_artifact_ambiguity(self):
        lanes = {}
        for index, payload in enumerate((b'first', b'other')):
            raw = bootstrap.encode_section_envelope(bootstrap.SectionEnvelope(4003, 6, 0, 129, 1, (), payload))
            common = bootstrap.fragment_section(raw, 8-index, 0)[0]
            lanes[100+index] = m2_codec.eh72_encode_unit(common)
        for order in ((100,101), (101,100)):
            result = self.decoder.decode(m2_decoder.OBS_UNITS,m2_damage._obs_units(order,lanes))
            self.assertEqual(result.artifact_state,'ambiguous')
            self.assertEqual(result.section_results,(
                m2_decoder.SectionResult(1,'incomplete',None),
                m2_decoder.SectionResult(4003,'ambiguous',None)))
            self.assertEqual(result.resource.section_attempts,2)
            self.assertIsNone(result.profile_id)
            self.assertIsNone(result.m2_required_stream)
            self.assertIsNone(result.m2_all_stream)
            self.decoder.render_result(m2_decoder.OBS_UNITS,result)

    def test_width_outside_owned_domain_rejects_before_pool_and_lane_work(self):
        for length in (0,256,65535):
            raw=b'\0\0\0\1\0\0\0\1'+length.to_bytes(2,'big')+bytes(length)
            result=self.decoder.decode(m2_decoder.OBS_UNITS,raw)
            self.assertEqual(result.artifact_state,'failure')
            self.assertEqual(result.resource,m2_decoder.ResourceUsage(0,0,1048576+256))
            self.assertEqual(result.fragment_diagnostics,())
            side=canonical_manifest.validate_canonical_manifest(self.decoder.render_resources())
            active={row['kernel']:row for row in side['adapter_rows'] if row['calls']}
            self.assertEqual(set(active),{'observation','result-render'})
            self.assertEqual(active['observation']['reference_input_units'],len(raw))
            self.assertEqual(active['observation']['peak_workspace_bytes'],0)

    def test_incomplete_copy_reserves_no_unconstructed_envelope_bytes(self):
        raw=bootstrap.encode_section_envelope(bootstrap.SectionEnvelope(4005,6,0,129,1,(),bytes([7])*200))
        blocks=bootstrap.fragment_section(raw,8,0)
        self.assertEqual(len(blocks),2)
        wire=m2_damage._obs_units((100,),{100:m2_codec.eh72_encode_unit(blocks[0])})
        result=self.decoder.decode(m2_decoder.OBS_UNITS,wire)
        self.assertEqual(result.artifact_state,'failure')
        self.assertEqual(result.resource.section_attempts,0)
        side=canonical_manifest.validate_canonical_manifest(self.decoder.render_resources())
        row=next(row for row in side['adapter_rows'] if row['kernel']=='section-assembly')
        self.assertEqual((row['calls'],row['reference_input_units'],row['peak_workspace_bytes']),(2,382,24))
