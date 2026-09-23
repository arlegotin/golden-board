"""Exact finite first-use coverage, distinct from human acquisition."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import unittest

from golden_board import canonical_manifest
from golden_board.m2_first_use_v2 import (
    FirstUseError, build_first_use_v2, validate_first_use_v2, _opcode_order,
)
from golden_board import m2_first_use_v2 as first_use
from golden_board.m2_route_v2 import build_route_prefixes_v2
from golden_board.m2_slice_v1 import compile_slice_v1

ROOT = Path(__file__).resolve().parents[2]


class FirstUse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiled = compile_slice_v1(*((ROOT/p).read_bytes() for p in (
            'studies/m2/slice-v1.json','studies/m2/slice-v0.json',
            'conformance/content-v0.json','conformance/chess-v0.json',
            'reports/game-set-v0.bin','spec/content-v0.md',
            'spec/constants-v0.toml','spec/curriculum-v0.toml')))
        cls.prefixes = build_route_prefixes_v2(compiled)
        with (patch('builtins.open', side_effect=AssertionError('source access')),
              patch('io.open', side_effect=AssertionError('source access')),
              patch('golden_board.m2_route_v2.build_route_prefixes_v2',
                    side_effect=AssertionError('source reconstruction'))):
            cls.raw = build_first_use_v2(cls.prefixes, side=2048, width=112)
        cls.value = canonical_manifest.validate_canonical_manifest(cls.raw)

    def test_complete_package_and_literal_prerequisite_coverage(self):
        v=self.value
        self.assertEqual(v['summary']['result'],'pass')
        self.assertEqual((len(v['route_rows']),len(v['node_rows']),len(v['recipe_rows']),
                          len(v['table_rows']),len(v['opcode_rows'])),(4,1162,29,15,25))
        self.assertEqual(v['inputs']['package']['bytes'],18531)
        t=next(t for t in v['table_rows'] if t[0]==17)
        self.assertEqual(v['mapping_use'][:4],[9,17,228,t[3]+228])
        self.assertEqual(len(v['literal_rows']),37)
        self.assertEqual(v['copy_rows'],[[70,1,33,0],[71,2,33,8],[72,4,34,0],[73,4,34,3]])
        positions={op:i for i,op in enumerate(v['opcode_order'])}
        for op,offset,deps,nodes in v['opcode_rows']:
            self.assertEqual(offset,6*(op-1))
            self.assertTrue(nodes)
            self.assertTrue(all(positions[d]<positions[op] for d in deps))
        self.assertTrue({1,2,5,6,21,23,24}<set(v['opcode_order'][:positions[22]]))
        validate_first_use_v2(self.raw,self.prefixes,side=2048,width=112)

    def test_missing_late_and_circular_opcode_definitions_reject(self):
        good={1:(),2:(1,),3:(2,)}
        self.assertEqual(_opcode_order(good),[1,2,3])
        for bad in ({1:(2,)},{1:(2,),2:(1,)},{1:(1,)}):
            with self.assertRaises(FirstUseError):
                _opcode_order(bad)

    def test_literal_anchors_do_not_invent_unobserved_intermediate_values(self):
        value=deepcopy(self.value)
        # Recipe211 ADD result value11 is observed only through output4.
        value['node_rows']=[n for n in value['node_rows']
                           if not (n[0]==211 and n[5]==5 and n[8][0][0]==11)]
        nodes={(n[0],n[1]):n for n in value['node_rows']}
        ins={(d[0],d[2]):d for d in value['descriptor_rows'] if d[1]==0}
        outs={(d[0],d[2]):d for d in value['descriptor_rows'] if d[1]==1}
        with self.assertRaisesRegex(FirstUseError,'unobserved-intermediate'):
            first_use._grounding(value,nodes,ins,outs)

    def test_literal_copy_anchor_is_checked_without_vm_evaluation(self):
        value=deepcopy(self.value)
        prefix=bytearray(self.prefixes[0])
        example=next(e for e in value['route_rows'][0]['example_spans'] if e[2]==602)
        # Output33 is a literal copy of the two first input bytes.
        descriptors=[d for d in value['descriptor_rows'] if d[0]==211 and d[1]==1]
        offset=example[5]+sum(d[6] if d[5]==3 else (d[6]+7)//8 for d in descriptors[:32])
        prefix[offset]^=1
        with self.assertRaisesRegex(FirstUseError,'literal-copy'):
            first_use._literal_constraints(bytes(prefix),value)

    def test_omitted_or_remapped_use_is_not_valid_coverage(self):
        for key in ('node_rows','field_rows','literal_rows','use_rows','table_rows'):
            value=deepcopy(self.value);value[key].pop()
            with self.subTest(key=key),self.assertRaises(FirstUseError):
                validate_first_use_v2(canonical_manifest.serialize_manifest(value),self.prefixes,side=2048,width=112)
        value=deepcopy(self.value);value['opcode_rows'][0][1]=6
        with self.assertRaises(FirstUseError):
            validate_first_use_v2(canonical_manifest.serialize_manifest(value),self.prefixes,side=2048,width=112)

    def test_malformed_geometry_bytes_and_missing_grounding_reject(self):
        for prefixes,side,width in ((list(self.prefixes),2048,112),(self.prefixes,True,112),
                                   (self.prefixes[:3],2048,112),(self.prefixes,2048,113),
                                   ((self.prefixes[0]+b'\0',*self.prefixes[1:]),2048,112)):
            with self.assertRaises(FirstUseError):
                build_first_use_v2(prefixes,side=side,width=width)
        raw=bytearray(self.prefixes[0])
        fact6=next(r for r in self.value['route_rows'][0]['definition_spans'] if r[0]==6)
        raw[fact6[1]+24*6+5]^=1
        with self.assertRaises(FirstUseError):
            build_first_use_v2((bytes(raw),*self.prefixes[1:]),side=2048,width=112)


if __name__ == '__main__':
    unittest.main()
