"""Finite carried use and honest ablation scope, without source access."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import unittest

from golden_board import canonical_manifest, content
from golden_board.m2_knowledge_v2 import (
    KnowledgeUseError, build_knowledge_use_v2, validate_knowledge_use_v2,
)
from golden_board.m2_route_v2 import build_route_prefixes_v2
from golden_board.m2_slice_v1 import compile_slice_v1

ROOT = Path(__file__).resolve().parents[2]


class CarriedKnowledge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiled = compile_slice_v1(*((ROOT/p).read_bytes() for p in (
            'studies/m2/slice-v1.json','studies/m2/slice-v0.json',
            'conformance/content-v0.json','conformance/chess-v0.json',
            'reports/game-set-v0.bin','spec/content-v0.md',
            'spec/constants-v0.toml','spec/curriculum-v0.toml')))
        cls.prefixes = build_route_prefixes_v2(cls.compiled)
        raw=cls.compiled.content_bytes
        cursor,frames=4,{}
        while cursor<len(raw):
            end=cursor+8+int.from_bytes(raw[cursor+4:cursor+8],'big')
            frames[int.from_bytes(raw[cursor:cursor+2],'big')]=raw[cursor:end]
            cursor=end
        cls.bodies={row.section_id:b''.join(frames[rid] for rid in row.record_ids)
                    for row in cls.compiled.atomic_assignments if row.section_id in (100,200)}
        cls.arguments=dict(side=2048,width=112,
            required_stream=cls.compiled.required_content_bytes,
            all_stream=raw,body_payloads=cls.bodies)
        with (patch('builtins.open',side_effect=AssertionError('source access')),
              patch('io.open',side_effect=AssertionError('path source access')),
              patch('os.open',side_effect=AssertionError('descriptor source access')),
              patch('golden_board.m2_route_v2.build_route_prefixes_v2',
                    side_effect=AssertionError('source reconstruction'))):
            cls.evidence=build_knowledge_use_v2(cls.prefixes,**cls.arguments)
        cls.document=canonical_manifest.validate_canonical_manifest(cls.evidence)

    def test_exact_actual_records_and_distinct_rejection_coverage(self):
        value=self.document
        self.assertEqual(value['scope'],'carried-finite-use-and-ablation-development')
        self.assertEqual(value['topological_order'],list(range(1,13)))
        self.assertEqual(value['summary'],dict(route_count=4,definition_count=48,
            example_count=128,structural_presence_rejections=48,
            relationship_contradiction_rejections=48,recovered_context_count=4,result='pass'))
        self.assertEqual(len(value['ablation_rows']),96)
        for sector,row in enumerate(value['route_rows']):
            self.assertEqual(row['sector_id'],sector)
            self.assertEqual(len(row['record_rows']),47)
            self.assertEqual(len(row['fact_rows']),12)
            self.assertEqual(len(row['example_rows']),32)
            self.assertEqual(row['context'],{'required':'checked','all':'checked','section-membership':'checked'})
            self.assertTrue(all(r['success'] for r in row['example_rows']))
            self.assertTrue(any(r['status']!=0 for r in row['example_rows']))
            cursor=64
            for record in row['record_rows']:
                self.assertEqual(record['byte_offset'],cursor)
                cursor+=record['bytes']
            self.assertEqual(cursor,len(self.prefixes[sector]))
        expected=[(s,f,op,kind) for s in range(4) for f in range(1,13)
                  for op,kind in (('remove','record-structure'),('contradict','definition-relationship'))]
        self.assertEqual([(r['sector_id'],r['fact_id'],r['operator'],r['classification'])
                          for r in value['ablation_rows']],expected)
        self.assertTrue(all(r['success'] is False for r in value['ablation_rows']))
        self.assertEqual([r['repair_id'] for r in value['repair_coverage']],
                         [f'C{i:02}' for i in range(1,12)])

    def test_missing_or_typed_but_false_context_is_not_complete_evidence(self):
        for updates in ({'required_stream':None},{'all_stream':None},
                        {'body_payloads':{100:self.bodies[100]}},
                        {'body_payloads':{100:self.bodies[200],200:self.bodies[200]}}):
            with self.subTest(updates=tuple(updates)),self.assertRaises(KnowledgeUseError):
                build_knowledge_use_v2(self.prefixes,**(self.arguments|updates))
        authored=content.authoring_from_validated(self.compiled.required_projection)
        records=[]
        for record in authored.records:
            if record.record_id==43:
                cells=list(record.payload.cells);cells[260]=0
                record=replace(record,payload=replace(record.payload,cells=tuple(cells)))
            records.append(record)
        false_stream=content.encode_content_v0(replace(authored,records=tuple(records)))
        with self.assertRaises(KnowledgeUseError):
            build_knowledge_use_v2(self.prefixes,**(self.arguments|{'required_stream':false_stream}))

    def test_strict_inputs_do_not_coerce_or_ignore_extra_prefix_bytes(self):
        cases=((list(self.prefixes),{}),(self.prefixes[:3],{}),
               ((self.prefixes[0]+b'\0',*self.prefixes[1:]),{}),
               (self.prefixes,{'side':True}),(self.prefixes,{'width':129}),
               (self.prefixes,{'all_stream':bytearray(self.arguments['all_stream'])}),
               (self.prefixes,{'body_payloads':{True:b'x',**self.bodies}}),
               (self.prefixes,{'body_payloads':{**self.bodies,500:b'x'*16385}}))
        for prefixes,updates in cases:
            with self.subTest(updates=tuple(updates)),self.assertRaises(KnowledgeUseError):
                build_knowledge_use_v2(prefixes,**(self.arguments|updates))

    def test_evidence_validation_recomputes_and_rejects_missing_failed_extra_rows(self):
        self.assertIsNone(validate_knowledge_use_v2(self.evidence,self.prefixes,**self.arguments))
        mutations=[]
        missing=deepcopy(self.document);missing['ablation_rows'].pop();mutations.append(missing)
        failed=deepcopy(self.document);failed['ablation_rows'][1]['success']=True;mutations.append(failed)
        changed=deepcopy(self.document);changed['route_rows'][0]['fact_rows'][0]['value_sha256']='0'*64;mutations.append(changed)
        extra=deepcopy(self.document);extra['human_pass']=True;mutations.append(extra)
        for value in mutations:
            with self.subTest(keys=tuple(value)),self.assertRaises(KnowledgeUseError):
                validate_knowledge_use_v2(canonical_manifest.serialize_manifest(value),self.prefixes,**self.arguments)
        for raw in (b'',bytearray(self.evidence),self.evidence+b' ',b'x'*1048577):
            with self.assertRaises(KnowledgeUseError):
                validate_knowledge_use_v2(raw,self.prefixes,**self.arguments)


if __name__=='__main__':
    unittest.main()
