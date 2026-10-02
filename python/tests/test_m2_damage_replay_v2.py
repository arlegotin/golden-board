"""Replay evidence cannot omit coverage or detach a result from its input."""
from dataclasses import replace
from pathlib import Path
import unittest

from golden_board import canonical_manifest as manifest
from golden_board.m2_damage_v2 import DamageObservationV2
from golden_board.m2_decoder_v2 import ObservationDecoderV2
from golden_board import m2_damage_replay_v2 as replay

ROOT=Path(__file__).resolve().parents[2]


class DamageReplayV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        decoder=ObservationDecoderV2(*((ROOT/'spec'/name).read_bytes() for name in (
            'profile-policy-v2.toml','profile-limits-v2.toml','damage-policy-v2.toml')))
        # A real closed decoder result, with a small synthetic evaluator catalog.
        # This serializer test does not label this input a source-owned corpus run.
        cls.case=DamageObservationV2('D7',0,'OBS_UNITS','serializer-test',(),bytes(4))
        result=decoder.decode(cls.case.channel,cls.case.observation)
        cls.result=decoder.render_result(cls.case.channel,result)
        cls.resources=decoder.render_resources()
        cls.sections=(1,2,3,16,17,18)
        cls.states=((1,'incomplete'),)+tuple((i,'unknown') for i in cls.sections[1:])

    def row(self,**changes):
        args=dict(case=self.case,result_raw=self.result,resources_raw=self.resources,
                  section_states=self.states,wrong_accept_count=0,
                  section_ids=self.sections,required_section_ids=self.sections)
        args.update(changes)
        return replay.render_replay_row(**args)

    def test_accidental_promises_and_boundary_differences_stay_separate(self):
        clean=manifest.validate_canonical_manifest(self.row())
        self.assertEqual(clean['promise_result'],'pass')
        self.assertFalse(clean['reauthored_boundary'])
        self.assertEqual(clean['observation'],self.case.identity())
        self.assertEqual(manifest.serialize_manifest(clean['decoder_result']),self.result)
        self.assertEqual(manifest.serialize_manifest(clean['resource_projection']),self.resources)
        self.assertEqual(manifest.validate_canonical_manifest(self.row(wrong_accept_count=1))['promise_result'],'fail')
        for family in ('D0','D1','D2','D3','D4','D5','D6'):
            row=manifest.validate_canonical_manifest(self.row(case=replace(self.case,family=family)))
            self.assertEqual(row['promise_result'],'fail')
        boundary=manifest.validate_canonical_manifest(self.row(
            case=replace(self.case,family='B0'),wrong_accept_count=1))
        self.assertTrue(boundary['reauthored_boundary'])
        self.assertEqual(boundary['wrong_accept_count'],1)
        self.assertEqual(boundary['promise_result'],'pass')

    def test_coverage_and_source_types_cannot_shrink_or_forge_a_promise(self):
        for changes in (
            dict(section_states=self.states[:-1]),
            dict(section_states=self.states[::-1]),
            dict(section_states=self.states+(self.states[-1],)),
            dict(section_states=((True,'unknown'),)+self.states[1:]),
            dict(section_states=((1,'invented'),)+self.states[1:]),
            dict(required_section_ids=(999,)),dict(required_section_ids=()),
            dict(required_section_ids=(1,)),
            dict(wrong_accept_count=True),dict(wrong_accept_count=-1),
            dict(wrong_accept_count=1<<64),dict(case=replace(self.case,family='D8')),
            dict(case=replace(self.case,ordinal=True)),
        ):
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.row(**changes)

    def test_stale_or_rebound_result_sidecar_rejects(self):
        for key,value in (('observation_sha256','0'*64),('result_sha256','0'*64),
                          ('channel','OBS_BITS')):
            side=manifest.validate_canonical_manifest(self.resources);side[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.row(resources_raw=manifest.serialize_manifest(side))
        changed=replace(self.case,observation=bytes(5))
        with self.assertRaises(ValueError):self.row(case=changed)
        side=manifest.validate_canonical_manifest(self.resources)
        side['resource']['primitive_steps']+=1
        with self.assertRaises(ValueError):self.row(resources_raw=manifest.serialize_manifest(side))

    def test_serialized_rows_are_revalidated_against_exact_case_and_catalog(self):
        raw=self.row()
        admitted=replay.validate_replay_row(raw,self.case,self.sections,self.sections)
        self.assertEqual(admitted,manifest.validate_canonical_manifest(raw))
        for key,value in (('promise_result','fail'),('reauthored_boundary',True),
                          ('unknown','ignored'),('expected_section_states',[])):
            row=manifest.validate_canonical_manifest(raw);row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                replay.validate_replay_row(manifest.serialize_manifest(row),self.case,self.sections,self.sections)
        with self.assertRaises(ValueError):
            replay.validate_replay_row(raw,replace(self.case,ordinal=1),self.sections,self.sections)

    def test_source_unknown_cannot_be_relabelled_as_a_visible_section(self):
        from hashlib import sha256
        result=manifest.validate_canonical_manifest(self.result)
        result['section_rows'][0]['state']='unknown'
        raw=manifest.serialize_manifest(result)
        side=manifest.validate_canonical_manifest(self.resources)
        side['result_sha256']=sha256(raw).hexdigest()
        with self.assertRaises(ValueError):
            self.row(result_raw=raw,resources_raw=manifest.serialize_manifest(side),
                section_states=tuple((sid,'unknown') for sid in self.sections))


if __name__=='__main__':unittest.main()
