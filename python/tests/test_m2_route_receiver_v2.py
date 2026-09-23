"""Observed framing and executable examples, independently of source equality."""
from pathlib import Path
import unittest
from unittest.mock import patch

from golden_board import recipe_wire_v1
from golden_board.m2_route_receiver_v2 import decode_observed_route_v2
from golden_board.m2_decoder import DecoderError
from golden_board.m2_route_v2 import build_route_prefixes_v2
from golden_board.m2_slice_v1 import compile_slice_v1

ROOT = Path(__file__).resolve().parents[2]


class ObservedRouteV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiled = compile_slice_v1(*((ROOT / p).read_bytes() for p in (
            'studies/m2/slice-v1.json', 'studies/m2/slice-v0.json',
            'conformance/content-v0.json', 'conformance/chess-v0.json',
            'reports/game-set-v0.bin', 'spec/content-v0.md',
            'spec/constants-v0.toml', 'spec/curriculum-v0.toml')))
        cls.prefixes = build_route_prefixes_v2(compiled)

    def test_complete_observed_package_executes_all_examples(self):
        for sector, prefix in enumerate(self.prefixes):
            result = decode_observed_route_v2(prefix, 2048, 112, sector)
            self.assertEqual(result.sector, sector)
            self.assertEqual(result.prefix_bytes, 25791)
            self.assertEqual(result.package.profile_version, 8)
            self.assertEqual(result.example_count, 33)
            self.assertEqual(result.inventory_section_id, 1)
            self.assertEqual(result.mapping['unit_population'], 1925)
            self.assertEqual(result.mapping['offset'], (8*40503+112*257) % 1824**2)
            self.assertGreater(result.primitive_steps, 0)
            self.assertEqual(decode_observed_route_v2(prefix+b'\xff'*128,2048,112,sector),result)

    def test_shape_versions_order_and_example_truth_fail_closed(self):
        prefix = self.prefixes[0]
        for offset, value in ((40,1),(45,7),(47,46),(63,1),(65,4),(71,255),
                              (74,3),(79,2)):
            raw = bytearray(prefix)
            raw[offset] = value
            with self.subTest(offset=offset), self.assertRaises(DecoderError):
                decode_observed_route_v2(bytes(raw),2048,112,0)
        # Change a carried result byte, leaving every outer frame intact.
        offset = 64
        while prefix[offset+1] != 2:
            offset += 8+int.from_bytes(prefix[offset+4:offset+8],'big')
        length = int.from_bytes(prefix[offset+4:offset+8],'big')
        raw = bytearray(prefix)
        raw[offset+8+length-1] ^= 1
        with self.assertRaises(DecoderError) as rejected:
            decode_observed_route_v2(bytes(raw),2048,112,0)
        self.assertGreater(rejected.exception.primitive_steps,0)
        self.assertGreater(rejected.exception.peak_scratch_bytes,0)
        for data, side, width, sector in ((prefix[:-1],2048,112,0),
             (bytearray(prefix),2048,112,0),(prefix,True,112,0),
             (prefix,2048,104,0),(prefix,2048,112,1),(prefix,2056,112,0)):
            with self.subTest(side=side,width=width,sector=sector), self.assertRaises(DecoderError):
                decode_observed_route_v2(data,side,width,sector)

    def test_every_carried_definition_is_required_in_all_four_observed_routes(self):
        # Keep all outer framing intact when corrupting a numeric definition.
        # The receiving path must use the carried relationship, without asking
        # the authoring compiler or filesystem for the expected source bytes.
        with (patch('builtins.open',side_effect=AssertionError('recipient source access')),
             patch('io.open',side_effect=AssertionError('recipient path source access')),
             patch('os.open',side_effect=AssertionError('recipient descriptor source access')),
             patch('golden_board.m2_route_v2.build_route_prefixes_v2',
                   side_effect=AssertionError('recipient source reconstruction'))):
            for sector,prefix in enumerate(self.prefixes):
                offset=64;seen=[]
                while offset<len(prefix):
                    length=int.from_bytes(prefix[offset+4:offset+8],'big')
                    end=offset+8+length
                    if prefix[offset+1]==1:
                        fact=int.from_bytes(prefix[offset+8:offset+10],'big')
                        seen.append(fact)
                        corrupted=bytearray(prefix)
                        corrupted[end-1]^=1
                        with self.subTest(sector=sector,fact=fact,operator='contradict'),self.assertRaises(DecoderError):
                            decode_observed_route_v2(bytes(corrupted),2048,112,sector)
                        removed=bytearray(prefix[:offset]+prefix[end:])
                        removed[46:48]=(int.from_bytes(prefix[46:48],'big')-1).to_bytes(2,'big')
                        removed[48:52]=(len(removed)-64).to_bytes(4,'big')
                        removed[56:60]=(len(removed)*8).to_bytes(4,'big')
                        with self.subTest(sector=sector,fact=fact,operator='remove'),self.assertRaises(DecoderError):
                            decode_observed_route_v2(bytes(removed),2048,112,sector)
                    offset=end
                self.assertEqual(seen,list(range(1,13)))


    def test_embedded_group_decisions_execute_even_when_primary_pair_passes(self):
        original = self.prefixes[0]
        clean = decode_observed_route_v2(original,2048,112,0)
        package = clean.package
        expanded = bytearray(recipe_wire_v1.expand_recipe_package_v1(package.encoded,8))
        at = 64+sum(16+len(t.payload) for t in package.logical.tables)
        for recipe in package.logical.recipes:
            if recipe.recipe_id == 110:
                node_start = at+32+12*(len(recipe.inputs)+len(recipe.outputs))
                # The framed constructor pair does not exercise decision110.
                # Change verified state2 to state1, still valid generic VM.
                expanded[node_start+32*9+31] = 1
                cost = recipe.primitive_steps
                break
            at += recipe.recipe_bytes
        changed_package = recipe_wire_v1.encode_recipe_package_v1(bytes(expanded),8)
        changed = bytearray(original)
        at = 64
        while at < len(original):
            size = int.from_bytes(original[at+4:at+8],'big')
            if original[at+1] == 5:
                self.assertEqual(size,len(changed_package))
                changed[at+8:at+8+size] = changed_package
            at += 8+size
        with self.assertRaisesRegex(DecoderError,'group-decision-trace') as rejected:
            decode_observed_route_v2(bytes(changed),2048,112,0)
        self.assertEqual(rejected.exception.primitive_steps+5*cost
            +next(r.primitive_steps for r in package.logical.recipes if r.recipe_id==30)
            +4*next(r.primitive_steps for r in package.logical.recipes if r.recipe_id==113),clean.primitive_steps)

    def test_every_context_witness_executes_and_is_charged(self):
        prefix=self.prefixes[0];calls=[]
        route=decode_observed_route_v2(prefix,2048,112,0,charge=lambda steps,scratch:calls.append((steps,scratch)))
        ids=[];at=64;fact10=None
        while at<len(prefix):
            kind=prefix[at+1]
            rid=int.from_bytes(prefix[at+2:at+4],'big')
            if kind in (2,3):ids.append(int.from_bytes(prefix[at+10:at+12],'big'))
            if rid==1001:fact10=at+22
            at+=8+int.from_bytes(prefix[at+4:at+8],'big')
        ids.extend((109,109,109,*((111,)*13),*((110,)*8),30,113,113,113,113))
        recipes={r.recipe_id:r for r in route.package.logical.recipes}
        self.assertEqual(len(ids),62)
        self.assertEqual(calls,[(recipes[i].primitive_steps,recipes[i].peak_live_scratch_bytes) for i in ids])
        self.assertEqual(sum(x[0] for x in calls),route.primitive_steps)
        for offset,label,charged in ((372,'group-erasure-reference',57),
                             (387,'group-repetition-reference',58),
                             (397,'group-repetition-trace',59),(393,'group-repetition-column',58),
                             (442,'fact10.relationship',62)):
            changed=bytearray(prefix);changed[fact10+offset]^=1
            with self.subTest(offset=offset),self.assertRaisesRegex(DecoderError,label) as rejected:
                decode_observed_route_v2(bytes(changed),2048,112,0)
            self.assertEqual(rejected.exception.primitive_steps,sum(x[0] for x in calls[:charged]))

    def test_invalid_template_range_rejects_before_call_but_noop_is_semantic(self):
        original=self.prefixes[0];at=64
        while int.from_bytes(original[at+2:at+4],'big')!=1001:
            at+=8+int.from_bytes(original[at+4:at+8],'big')
        for first,expected_count,label in ((73,36,'group-construction-fields'),
                                            (1,62,'fact10.template')):
            changed=bytearray(original);changed[at+22+108]=first
            calls=[]
            with self.subTest(first=first),self.assertRaisesRegex(DecoderError,label):
                decode_observed_route_v2(bytes(changed),2048,112,0,
                    charge=lambda steps,scratch:calls.append(steps))
            self.assertEqual(len(calls),expected_count)

    def test_same_decoded_value_does_not_allow_a_different_erasure_input(self):
        original=self.prefixes[0]; at=64; locations={}
        while at<len(original):
            locations[int.from_bytes(original[at+2:at+4],'big')]=at
            at+=8+int.from_bytes(original[at+4:at+8],'big')
        fact10=locations[1001]+22
        primary=locations[1004]+20
        changed=bytearray(original)
        # Merely substitute a different valid placeholder for unknown bit63.
        # The erasure decoder still returns A; the constructed input must be
        # exact canonical zero storage, not an unrelated successful call.
        changed[fact10+380]^=1
        with self.assertRaisesRegex(DecoderError,'group-erasure-primary'):
            decode_observed_route_v2(bytes(changed),2048,112,0)
        changed[primary+7]^=1
        calls=[]
        with self.assertRaisesRegex(DecoderError,'fact10.erasure-input'):
            decode_observed_route_v2(bytes(changed),2048,112,0,
                charge=lambda steps,scratch:calls.append(steps))
        self.assertEqual(len(calls),62)

    def test_unrelated_valid_primary_pair_does_not_replace_group_construction(self):
        original = self.prefixes[0]
        at = 64
        while at < len(original):
            rid = int.from_bytes(original[at+2:at+4],'big')
            if rid == 1001:
                fact10 = at+8+14
            if rid == 1002:
                primary = at+8+12
            at += 8+int.from_bytes(original[at+4:at+8],'big')
        # A valid constructor result for template2 cannot replace template9.
        # Keep the outer lengths and VM equality correct while breaking the
        # worked example's direct link to its erasure construction.
        changed = bytearray(original)
        changed[primary+18:primary+22] = bytes((0,0,59,5))
        changed[primary+24:primary+42] = bytes.fromhex('000140000000001820')+bytes(9)
        with self.assertRaisesRegex(DecoderError,'group-primary'):
            decode_observed_route_v2(bytes(changed),2048,112,0)


if __name__ == '__main__':
    unittest.main()
