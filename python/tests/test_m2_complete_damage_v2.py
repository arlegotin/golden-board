"""Retained damage evidence keeps coverage, failures and resource bindings."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from golden_board import canonical_manifest as manifest
from golden_board import m2_complete_damage_v2 as complete
from golden_board.m2_resources_v2 import build_resource_limits_v2, ResourceAggregateV2
from golden_board.m2_decoder_bridge_v2 import _result_frame_value
from python.tests import test_m2_damage_replay_v2 as fixtures


class CompleteDamageV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.DamageReplayV2.setUpClass()
        cls.fixture=fixtures.DamageReplayV2()
        cls.case=cls.fixture.case
        cls.ids=cls.fixture.sections
        cls.raw=cls.fixture.row()
        cls.sidecar=manifest.validate_canonical_manifest(cls.fixture.resources)

    def test_compact_reconstructs_exact_accounting_and_binds_complete_result(self):
        raw=complete.compact_replay_row(self.raw,self.case,self.ids)
        compact=manifest.validate_canonical_manifest(raw)
        side=complete.validate_compact_case(raw,self.case,self.ids,self.sidecar['source_owners'])
        self.assertEqual(side,self.fixture.resources)
        self.assertEqual(compact['decoder_result_sha256'],sha256(self.fixture.result).hexdigest())
        self.assertEqual(compact['resource_projection_sha256'],sha256(side).hexdigest())
        self.assertEqual(compact['section_states'],[[sid,state] for sid,state in self.fixture.states])
        self.assertEqual(compact['promise_result'],'pass')

    def test_compact_mutations_cannot_change_coverage_promise_or_accounting(self):
        original=manifest.validate_canonical_manifest(complete.compact_replay_row(
            self.raw,self.case,self.ids))
        changes=[('section_states',original['section_states'][:-1]),
                 ('section_states',original['section_states'][::-1]),
                 ('wrong_accept_count',True),('wrong_accept_count',1),
                 ('promise_result','fail'),('resource_projection_sha256','0'*64),
                 ('decoder_result_sha256','0'*64),('extra',0),
                 ('stream_rows',[[2,False,'1'*64],[3,False,'0'*64]])]
        for key,value in changes:
            row=deepcopy(original);row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                complete.validate_compact_case(manifest.serialize_manifest(row),self.case,
                                               self.ids,self.sidecar['source_owners'])
        row=deepcopy(original);row['resource']['primitive_steps']+=1
        with self.assertRaises(ValueError):
            complete.validate_compact_case(manifest.serialize_manifest(row),self.case,
                                           self.ids,self.sidecar['source_owners'])

    def test_incremental_aggregation_is_exact_and_requires_complete_order(self):
        ids=(self.case.case_id,)
        expected=build_resource_limits_v2('1'*64,ids,((ids[0],self.fixture.resources),))
        aggregate=ResourceAggregateV2(ids)
        aggregate.push(ids[0],self.fixture.resources)
        self.assertEqual(aggregate.finish('1'*64),expected)
        with self.assertRaises(ValueError):aggregate.push(ids[0],self.fixture.resources)
        with self.assertRaises(ValueError):ResourceAggregateV2(ids).finish('1'*64)
        with self.assertRaises(ValueError):ResourceAggregateV2(ids).push('D7-000001',self.fixture.resources)

    def test_source_identity_types_cannot_be_rebound_by_boolean_integer_equality(self):
        case=replace(self.case,parameters=(('polarity_id','u64',0),('coordinates','rows',((1,0),))))
        raw=complete.compact_replay_row(self.fixture.row(case=case),case,self.ids)
        for nested in (False,True):
            value=manifest.validate_canonical_manifest(raw)
            rows=value['observation']['parameter_projection']
            if nested:rows[1]['value'][0][0]=True
            else:rows[0]['value']=False
            with self.subTest(nested=nested),self.assertRaises(ValueError):
                complete.validate_compact_case(manifest.serialize_manifest(value),case,
                    self.ids,self.sidecar['source_owners'])

    def test_failure_cannot_expose_stream_and_available_hash_cannot_be_absent(self):
        compact=complete.compact_replay_row(self.raw,self.case,self.ids)
        for available_hash in ('0'*64,'1'*64):
            value=manifest.validate_canonical_manifest(compact)
            value['stream_rows'][0]=[2,True,available_hash]
            with self.subTest(compact_hash=available_hash),self.assertRaises(ValueError):
                complete.validate_compact_case(manifest.serialize_manifest(value),self.case,
                    self.ids,self.sidecar['source_owners'])
            result=manifest.validate_canonical_manifest(self.fixture.result)
            result['m2_required_available']=True
            result['m2_required_stream_sha256']=available_hash
            with self.subTest(full_hash=available_hash),self.assertRaises(ValueError):
                _result_frame_value(manifest.serialize_manifest(result))

    def test_shards_greedily_preserve_order_and_reject_oversized_case(self):
        output={}
        writer=complete.FamilyWriter('D7','1'*64,lambda path,raw:output.setdefault(path,raw))
        raw=complete.compact_replay_row(self.raw,self.case,self.ids)
        # This unit test tests the bounded serializer only, not complete admission.
        for ordinal in range(33):
            row=manifest.validate_canonical_manifest(raw)
            row['observation']['case_ordinal']=ordinal
            row['observation']['case_id']=f'D7-{ordinal:06d}'
            writer.push(manifest.serialize_manifest(row))
        doc=manifest.validate_canonical_manifest(writer.finish(True))
        self.assertEqual([r['case_count'] for r in doc['shards']],[32,1])
        self.assertEqual([r['first_ordinal'] for r in doc['shards']],[0,32])
        self.assertEqual(doc['cases_sha256'],sha256(b''.join(
            manifest.serialize_manifest(row) for path in sorted(output)
            for row in manifest.validate_canonical_manifest(output[path])['cases'])).hexdigest())
        with self.assertRaises(ValueError):
            complete.FamilyWriter('D7','1'*64,lambda *_:None).push(b'x'*262145)

    def context(self):
        # Small source-context double for projection serialization only. Actual
        # static/corpus admission stays mandatory in the public constructor.
        # Reduced family sizes exercise the serializer's sequence rules; this
        # double cannot pass the unmocked source/static admission boundary.
        counts=(16,1,1,1,2,1,8,3,2)
        ids=tuple(f'{family}-{i:06d}' for family,count in zip(complete.FAMILIES,counts,strict=True)
                  for i in range(count))
        return SimpleNamespace(count=2,capacity={'carrier_sha256':'1'*64}),self.ids,counts,ids

    def fake_case(self,_corpus,family,ordinal):
        return replace(self.case,family=family,ordinal=ordinal)

    def complete_fixture(self):
        output={}
        def records():
            for family,count in zip(complete.FAMILIES,self.context()[2],strict=True):
                for ordinal in range(count):
                    yield self.fixture.row(case=self.fake_case(None,family,ordinal),
                        wrong_accept_count=int(family=='B0'))
        kats=tuple(manifest.serialize_manifest(dict(schema='golden-board.m2-boundary-kat-result/v2',
            kat_id=kat_id,result='pass')) for kat_id in complete.KAT_IDS)
        with patch.object(complete,'_context',return_value=self.context()),patch.object(
                complete,'_case',side_effect=self.fake_case):
            complete.build_complete_damage_v2(b'candidate',b'',b'',b'',None,records(),kats,
                                              lambda path,raw:output.__setitem__(path,raw))
        return output,records,kats

    def admit_fixture(self,output):
        with patch.object(complete,'_context',return_value=self.context()),patch.object(
                complete,'_case',side_effect=self.fake_case):
            return complete.admit_complete_damage_v2(b'candidate',b'',b'',b'',None,
                output.__getitem__,tuple(sorted(output)))

    def test_complete_projection_preserves_failures_and_separate_boundary_wrong_accepts(self):
        output,_,_=self.complete_fixture()
        root,limits=self.admit_fixture(output)
        value=manifest.validate_canonical_manifest(root)
        self.assertEqual(root,output['damage/manifest.json'])
        self.assertEqual(limits,output['resource-limits.json'])
        self.assertEqual(value['result'],'fail')
        self.assertEqual(value['wrong_accept_count'],0)
        self.assertEqual(value['reauthored_boundary']['wrong_accept_count'],2)
        self.assertEqual(value['reauthored_boundary']['result'],'pass')
        self.assertEqual(value['family_rows'][-1]['result'],'pass')
        self.assertEqual(value['accidental_case_count'],33)

    def test_retained_tree_rejects_extra_missing_mutated_and_non_greedy_shards(self):
        original,_,_=self.complete_fixture()
        changes=[]
        extra=dict(original);extra['damage/extra.json']=b'{}\n';changes.append(extra)
        missing=dict(original);del missing['damage/D0/000000.json'];changes.append(missing)
        mutated=dict(original);value=manifest.validate_canonical_manifest(mutated['damage/manifest.json'])
        value['result']='pass';mutated['damage/manifest.json']=manifest.serialize_manifest(value);changes.append(mutated)
        reordered=dict(original);value=manifest.validate_canonical_manifest(reordered['damage/D0/000000.json'])
        value['cases']=value['cases'][::-1]
        reordered['damage/D0/000000.json']=manifest.serialize_manifest(value);changes.append(reordered)
        divided=dict(original);value=manifest.validate_canonical_manifest(divided['damage/D0/000000.json'])
        halves=[]
        for i in range(2):
            shard=dict(value,first_ordinal=i*8,case_count=8,cases=value['cases'][i*8:(i+1)*8])
            raw=manifest.serialize_manifest(shard);path=f'damage/D0/{i:06d}.json';divided[path]=raw
            halves.append(dict(**complete.file_row(path,raw),first_ordinal=i*8,case_count=8))
        family=manifest.validate_canonical_manifest(divided['damage/D0/manifest.json']);family['shards']=halves
        divided['damage/D0/manifest.json']=manifest.serialize_manifest(family);changes.append(divided)
        for index,output in enumerate(changes):
            with self.subTest(index=index),self.assertRaises(ValueError):self.admit_fixture(output)

    def test_incomplete_or_extra_execution_never_emits_root_success(self):
        _,records,kats=self.complete_fixture()
        for rows in (iter(()),iter((*records(),self.raw))):
            output={}
            with patch.object(complete,'_context',return_value=self.context()),patch.object(
                    complete,'_case',side_effect=self.fake_case),self.assertRaises(ValueError):
                complete.build_complete_damage_v2(b'candidate',b'',b'',b'',None,rows,kats,
                    lambda path,raw:output.__setitem__(path,raw))
            self.assertNotIn('damage/manifest.json',output)
            self.assertNotIn('resource-limits.json',output)

    def test_retained_names_are_bounded_before_source_or_file_work(self):
        for name in ('x'*10000,'damage/D9/000000.json','damage/D0/../manifest.json',
                     '/damage/manifest.json','damage/D0/0000000.json','damage/é.json'):
            with (self.subTest(name=name[:80]),
                  patch.object(complete,'_context',side_effect=AssertionError('source reached')),
                  self.assertRaises(ValueError)):
                complete.admit_complete_damage_v2(b'',b'',b'',b'',None,
                    lambda _name: self.fail('read reached'),(name,))


if __name__=='__main__':unittest.main()
