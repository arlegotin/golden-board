"""Observed framing and executable examples, independently of source equality."""
from pathlib import Path
import unittest
from unittest.mock import patch

from golden_board import recipe_wire_v2, m2_program_refinement_v2, m2_recovery_recipe_v2
from golden_board.m2_revision_recipe import build_revision_recipe_package
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
            result = decode_observed_route_v2(prefix, 2040, 112, sector)
            self.assertEqual(result.sector, sector)
            self.assertEqual(result.prefix_bytes, 25424)
            self.assertEqual(result.package.profile_version, 8)
            self.assertEqual(result.example_count, 33)
            self.assertEqual(result.inventory_section_id, 1)
            self.assertEqual(result.mapping['unit_population'], 1908)
            self.assertEqual(result.mapping['offset'], (8*40503+112*257) % 1816**2)
            self.assertGreater(result.primitive_steps, 0)
            self.assertEqual(decode_observed_route_v2(prefix+b'\xff'*128,2040,112,sector),result)

    def test_shape_versions_order_and_example_truth_fail_closed(self):
        prefix = self.prefixes[0]
        for offset, value in ((40,1),(45,7),(47,46),(63,1),(65,4),(71,255),
                              (74,3),(79,2)):
            raw = bytearray(prefix)
            raw[offset] = value
            with self.subTest(offset=offset), self.assertRaises(DecoderError):
                decode_observed_route_v2(bytes(raw),2040,112,0)
        # Change a carried result byte, leaving every outer frame intact.
        offset = 64
        while prefix[offset+1] != 2:
            offset += 8+int.from_bytes(prefix[offset+4:offset+8],'big')
        length = int.from_bytes(prefix[offset+4:offset+8],'big')
        raw = bytearray(prefix)
        raw[offset+8+length-1] ^= 1
        with self.assertRaises(DecoderError) as rejected:
            decode_observed_route_v2(bytes(raw),2040,112,0)
        self.assertGreater(rejected.exception.primitive_steps,0)
        self.assertGreater(rejected.exception.peak_scratch_bytes,0)
        for data, side, width, sector in ((prefix[:-1],2040,112,0),
             (bytearray(prefix),2040,112,0),(prefix,True,112,0),
             (prefix,2040,104,0),(prefix,2040,112,1),(prefix,2056,112,0)):
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
                            decode_observed_route_v2(bytes(corrupted),2040,112,sector)
                        removed=bytearray(prefix[:offset]+prefix[end:])
                        removed[46:48]=(int.from_bytes(prefix[46:48],'big')-1).to_bytes(2,'big')
                        removed[48:52]=(len(removed)-64).to_bytes(4,'big')
                        removed[56:60]=(len(removed)*8).to_bytes(4,'big')
                        with self.subTest(sector=sector,fact=fact,operator='remove'),self.assertRaises(DecoderError):
                            decode_observed_route_v2(bytes(removed),2040,112,sector)
                    offset=end
                self.assertEqual(seen,list(range(1,13)))


    def records(self, prefix):
        rows = []
        at = 64
        while at < len(prefix):
            end = at+8+int.from_bytes(prefix[at+4:at+8], 'big')
            rows.append((int.from_bytes(prefix[at+2:at+4], 'big'), prefix[at+1], at, end))
            at = end
        self.assertEqual(at, len(prefix))
        return rows

    def test_complete_closure_rejects_changed_raw_data_template_or_program_before_calls(self):
        original = self.prefixes[0]
        package = decode_observed_route_v2(original,2040,112,0).package
        source = recipe_wire_v2.expand_recipe_package_v2(package.encoded,8)
        locations = {}
        at = 64
        for table in package.logical.tables:
            locations[('table',table.table_id)] = at+16
            at += 16+len(table.payload)
        for recipe in package.logical.recipes:
            locations[('recipe',recipe.recipe_id)] = at+32+12*(len(recipe.inputs)+len(recipe.outputs))
            at += recipe.recipe_bytes
        for name, offset in (('encoded-observation',locations[('table',24)]),
                             ('erasure-template',locations[('table',27)]+4*9+1),
                             ('raw-repetition-program',locations[('recipe',114)]+31)):
            expanded = bytearray(source)
            expanded[offset] ^= 1
            changed_package = recipe_wire_v2.encode_recipe_package_v2(bytes(expanded),8)
            recipe_wire_v2.decode_recipe_package_v2(changed_package,8)
            self.assertEqual(len(changed_package),len(package.encoded))
            changed = bytearray(original)
            _, _, start, end = next(row for row in self.records(original) if row[1] == 5)
            changed[start+8:end] = changed_package
            calls = []
            with self.subTest(mutation=name), self.assertRaisesRegex(DecoderError,'complete-recovery-program') as rejected:
                decode_observed_route_v2(bytes(changed),2040,112,0,
                    charge=lambda steps,scratch:calls.append((steps,scratch)))
            self.assertEqual(calls,[])
            self.assertEqual((rejected.exception.primitive_steps,rejected.exception.peak_scratch_bytes),(0,0))

    def test_every_context_witness_executes_and_is_charged(self):
        prefix = self.prefixes[0]
        calls = []
        route = decode_observed_route_v2(prefix,2040,112,0,
            charge=lambda steps,scratch:calls.append((steps,scratch)))
        framed = [int.from_bytes(prefix[start+10:start+12],'big')
                  for _,kind,start,_ in self.records(prefix) if kind in (2,3)]
        ids = (*framed,109,109,109,*((126,)*8))
        recipes = {r.recipe_id:r for r in route.package.logical.recipes}
        expected = [(recipes[rid].primitive_steps,recipes[rid].peak_live_scratch_bytes) for rid in ids]
        self.assertEqual(len(framed),33)
        self.assertEqual(len(calls),44)
        self.assertEqual(calls,expected)
        self.assertEqual(sum(row[0] for row in calls),route.primitive_steps)
        self.assertEqual(route.primitive_steps,152936421)
        fact10 = next(start+22 for rid,_,start,_ in self.records(prefix) if rid == 1001)
        # Nonprimary case results are executed after all33 framed examples and
        # three mapping checks. A bad reference stops before any context call.
        for offset,label,count in ((0,'group-composition-reference',36),
                (22+57*0+32,'group-complete-trace',37),
                (22+57*3+32,'group-complete-trace',40),
                (22+57*5+33,'group-complete-trace',42)):
            changed = bytearray(prefix)
            changed[fact10+offset] ^= 1
            observed = []
            with self.subTest(offset=offset), self.assertRaisesRegex(DecoderError,label) as rejected:
                decode_observed_route_v2(bytes(changed),2040,112,0,
                    charge=lambda steps,scratch:observed.append((steps,scratch)))
            self.assertEqual(observed,calls[:count])
            self.assertEqual(rejected.exception.primitive_steps,sum(row[0] for row in calls[:count]))

    def test_bad_target_and_case_charge_the_failed_complete_call(self):
        prefix = self.prefixes[0]
        expected = []
        decode_observed_route_v2(prefix,2040,112,0,
            charge=lambda steps,scratch:expected.append((steps,scratch)))
        fact10 = next(start+22 for rid,_,start,_ in self.records(prefix) if rid == 1001)
        for case, offset, replacement in ((0,0,bytes(4)),(5,4,bytes((255,)))):
            changed = bytearray(prefix)
            start = fact10+22+57*case+offset
            changed[start:start+len(replacement)] = replacement
            calls = []
            with self.subTest(case=case), self.assertRaisesRegex(DecoderError,'group-complete-trace') as rejected:
                decode_observed_route_v2(bytes(changed),2040,112,0,
                    charge=lambda steps,scratch:calls.append((steps,scratch)))
            self.assertEqual(calls,expected[:37+case])
            self.assertEqual(rejected.exception.primitive_steps,sum(row[0] for row in calls))

    def test_primary_examples_bind_exact_cases_four_six_and_seven_before_execution(self):
        prefix = self.prefixes[0]
        records = self.records(prefix)
        fact10 = next(start+22 for rid,_,start,_ in records if rid == 1001)
        calls = []
        decode_observed_route_v2(prefix,2040,112,0,
            charge=lambda steps,scratch:calls.append((steps,scratch)))
        for rid, case in ((1002,4),(1003,6),(1004,7)):
            _, _, start, end = next(row for row in records if row[0] == rid)
            primary = start+20
            self.assertEqual(prefix[primary:end],prefix[fact10+22+57*case:fact10+22+57*(case+1)])
            # Substitute another independently valid complete126 example. Its
            # VM answer is correct, but it is not this primary's carried case.
            changed = bytearray(prefix)
            changed[primary:end] = prefix[fact10+22+57*2:fact10+22+57*3]
            before = sum(kind in (2,3) for _,kind,at,_ in records if at < start)
            observed = []
            with self.subTest(record=rid), self.assertRaisesRegex(DecoderError,'group-primary') as rejected:
                decode_observed_route_v2(bytes(changed),2040,112,0,
                    charge=lambda steps,scratch:observed.append((steps,scratch)))
            self.assertEqual(observed,calls[:before])
            self.assertEqual(rejected.exception.primitive_steps,sum(row[0] for row in observed))

    def test_equal_vm_result_cannot_replace_the_declared_physical_query(self):
        prefix = self.prefixes[0]
        records = self.records(prefix)
        fact10 = next(start+22 for rid,_,start,_ in records if rid == 1001)
        primary = next(start+20 for rid,_,start,_ in records if rid == 1002)
        changed = bytearray(prefix)
        # Units6 and7 belong to the same group: both126 calls produce the same
        # result. Bind the primary and DEFINE together; the stated case still
        # requires query6, so semantic validation must reject after44 calls.
        for start in (fact10+22+57*4,primary):
            changed[start:start+4] = (7).to_bytes(4,'big')
        expected, calls = [], []
        decode_observed_route_v2(prefix,2040,112,0,
            charge=lambda steps,scratch:expected.append((steps,scratch)))
        with self.assertRaisesRegex(DecoderError,'fact10.example-order') as rejected:
            decode_observed_route_v2(bytes(changed),2040,112,0,
                charge=lambda steps,scratch:calls.append((steps,scratch)))
        self.assertEqual(calls,expected)
        self.assertEqual(len(calls),44)
        self.assertEqual(rejected.exception.primitive_steps,sum(row[0] for row in calls))

    def test_complete_route_runs_with_cold_neutral_closures_and_no_files(self):
        m2_recovery_recipe_v2._neutral_baseline.cache_clear()
        m2_program_refinement_v2._expected.cache_clear()
        build_revision_recipe_package.cache_clear()
        with (patch('builtins.open',side_effect=AssertionError('source access')),
              patch('io.open',side_effect=AssertionError('path access')),
              patch('os.open',side_effect=AssertionError('descriptor access')),
              patch('golden_board.m2_route_v2.build_route_prefixes_v2',
                    side_effect=AssertionError('route reconstruction'))):
            route = decode_observed_route_v2(self.prefixes[0],2040,112,0)
        self.assertEqual(route.primitive_steps,152936421)


if __name__ == '__main__':
    unittest.main()
