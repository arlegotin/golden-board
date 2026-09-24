"""Numeric route teaching carries checked relationships, not labels."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import unittest

from golden_board import bootstrap, bootstrap_v2, m2_codec, recipe_wire_v1, recipe_wire_v2
from golden_board.m2_recovery_recipe_v2 import evaluate_recovery_native
from golden_board.m2_teaching_recipe_v2 import build_teaching_recipe_package
from golden_board.m2_revision_recipe import build_revision_recipe_package
from golden_board.m2_slice_v1 import compile_slice_v1
from golden_board.m2_route_definitions_v2 import build_route_definitions_v2

ROOT = Path(__file__).resolve().parents[2]


class RouteDefinitions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'conformance/content-v0.json').read_bytes()
        cls.compiled = compile_slice_v1(*( (ROOT / p).read_bytes() for p in (
            'studies/m2/slice-v1.json', 'studies/m2/slice-v0.json',
            'conformance/content-v0.json', 'conformance/chess-v0.json',
            'reports/game-set-v0.bin', 'spec/content-v0.md',
            'spec/constants-v0.toml', 'spec/curriculum-v0.toml')))
        cls.rows = build_route_definitions_v2(cls.compiled, cls.source)

    def test_exact_finite_shape_and_fresh_immutable_records(self):
        self.assertEqual(tuple(r.fact_id for r in self.rows), tuple(range(1, 13)))
        self.assertEqual(tuple(len(r.value) for r in self.rows),
                         (16,64,306,296,236,228,636,544,464,478,314,2485))
        again = build_route_definitions_v2(self.compiled, self.source)
        self.assertEqual(again, self.rows)
        self.assertIsNot(again[0], self.rows[0])
        with self.assertRaises(FrozenInstanceError):
            self.rows[0].fact_id = 9
        self.assertEqual(self.rows[0].value.hex(), '00ff807faa55f00fcc3301fe817e18e7')

    def test_source_digest_and_projection_are_not_unchecked_inputs(self):
        with self.assertRaises(ValueError):
            build_route_definitions_v2(replace(self.compiled, required_content_sha256='0'*64), self.source)
        with self.assertRaises(ValueError):
            build_route_definitions_v2(replace(self.compiled, required_content_bytes=b'\0'*4), self.source)
        with self.assertRaises(ValueError):
            build_route_definitions_v2(replace(self.compiled, required_projection=self.compiled.projection), self.source)
        with self.assertRaises(ValueError):
            build_route_definitions_v2(self.compiled, bytearray(self.source))

    def test_profile_eh_words_and_repetition_use_real_generic_recipes(self):
        package = recipe_wire_v1.decode_recipe_package_v1(build_revision_recipe_package(), 8)
        block_a, block_b = self.rows[6].value[134:325], self.rows[6].value[325:516]
        for block, encoded in zip((block_a, block_b), (self.rows[7].value[112:328], self.rows[7].value[328:544])):
            self.assertEqual(bootstrap.decode_common_block(block, 8).section_id, 400)
            with self.assertRaises(bootstrap.BootstrapReject):
                bootstrap.decode_common_block(block, 7)
            self.assertEqual(m2_codec.eh72_encode_unit(block), encoded)
            decoded = bytearray()
            for i in range(24):
                plain = (block+b'\0')[8*i:8*i+8]
                word = encoded[9*i:9*i+9]
                self.assertEqual(recipe_wire_v1.evaluate_recipe_v1(package, 108, (plain,)).outputs, (word,))
                result = recipe_wire_v1.evaluate_recipe_v1(package, 30, (word,b'\0',bytes(3)))
                self.assertEqual(result.status, 0)
                decoded.extend(result.outputs[0])
            self.assertEqual(bytes(decoded), block+b'\0')
        word = self.rows[7].value[328:337]
        for first in range(0,10,2):
            damaged = bytearray(word)
            for bit in (first,first+1):
                damaged[bit//8] ^= 1 << (7-bit%8)
            actual = recipe_wire_v1.evaluate_recipe_v1(package, 30, (bytes(damaged),b'\0',bytes(3)))
            self.assertIsNone(m2_codec.eh72_decode(bytes(damaged),()).decoded)
            self.assertNotEqual(actual.status,0)
            self.assertEqual(actual.outputs,())
        for factor in (2, 5):
            for zeros in range(factor+1):
                for ones in range(factor-zeros+1):
                    result = recipe_wire_v1.evaluate_recipe_v1(package, 113, tuple(bytes([x]) for x in (factor,zeros,ones)))
                    known, bit = m2_codec.repetition_symbol_counts(factor,zeros,ones)
                    self.assertEqual((result.status,result.outputs), (0,(bytes([known]),bytes([bit]))))

    def test_complete_physical_context_and_observation_results_are_carried(self):
        package = recipe_wire_v2.decode_recipe_package_v2(build_teaching_recipe_package(),8)
        tables = {t.table_id:t.payload for t in package.logical.tables}
        value = self.rows[9].value
        self.assertEqual(len(value),478)
        self.assertEqual(tuple(int.from_bytes(value[i:i+2],'big') for i in range(0,20,2)),
                         (123,124,120,125,126,127,24,25,26,27))
        self.assertEqual(value[20:22],bytes((8,57)))
        self.assertEqual(tables[24],self.rows[7].value[112:544])
        # The miniature is a traversal illustration, never a production
        # inventory that passed all mandatory roles and semantic admission.
        with self.assertRaises(bootstrap.BootstrapReject):
            bootstrap_v2.decode_inventory(tables[25])
        first, roster = 1, {}
        for at in range(8,68,20):
            header = tables[25][at:at+20]
            sid = int.from_bytes(header[:4],'big')
            factor = (header[11] >> 1) & 7
            envelope = 22+int.from_bytes(header[14:18],'big')
            count = (envelope+156)//157
            roster[sid] = (factor,first,first+factor*count-1,header[4:8],envelope,count)
            first += factor*count
        self.assertEqual(tuple((sid,*row[:3]) for sid,row in roster.items()),
                         ((1,5,1,5),(400,5,6,10),(401,2,11,12)))
        common = (self.rows[6].value[134:325],self.rows[6].value[325:516])
        for case in range(8):
            row = value[22+57*case:22+57*(case+1)]
            target = 11 if case == 7 else 6
            sid = 401 if case == 7 else 400
            factor,first,_,kind_version,envelope,count = roster[sid]
            key = (bytes((0,8))+sid.to_bytes(4,'big')+bytes(2)+kind_version+bytes(2)
                   +count.to_bytes(2,'big')+envelope.to_bytes(4,'big'))
            state = (0,1,2,3,4,3,3,2)[case]
            accepted = (0,0,1,1,0,1,1,0)[case]
            payload = bytes(23) if case in (0,1,4) else common[int(case==5)][30:53]
            expected = (bytes(2)+first.to_bytes(4,'big')+bytes((factor,))+key
                        +bytes((state,accepted))+payload)
            self.assertEqual(row[:5],target.to_bytes(4,'big')+bytes((case,)))
            self.assertEqual(row[5:],expected)
            result = evaluate_recovery_native(package,126,(row[:4],row[4:5]))
            self.assertEqual(result.status.to_bytes(2,'big')+b''.join(result.outputs),expected)

    def test_unknown_observations_are_not_guessed_zero_during_repetition(self):
        from golden_board.m2_transport_v2 import aggregate_replica_group
        package = recipe_wire_v2.decode_recipe_package_v2(build_teaching_recipe_package(),8)
        tables = {t.table_id:t.payload for t in package.logical.tables}
        lanes = []
        for token in tables[26][5*6:5*7]:
            source,unknown,first,count = tables[27][4*token:4*(token+1)]
            self.assertEqual(unknown,1)
            raw = bytearray(tables[24][216*source:216*(source+1)])
            erased = tuple(range(first,first+count))
            for bit in erased:
                raw[bit//8] &= 255 ^ (128 >> (bit%8))
            lanes.append(m2_codec.CopyObservation(bytes(raw),erased))
        result = aggregate_replica_group(tuple(lanes))
        self.assertEqual(result.lane_states,(1,)*5)
        self.assertEqual((result.repetition_state,result.group_state),(3,3))
        self.assertEqual(result.chosen_block,self.rows[6].value[134:325])
        guessed = aggregate_replica_group(tuple(m2_codec.CopyObservation(lane.encoded,()) for lane in lanes))
        self.assertEqual((guessed.repetition_state,guessed.group_state),(1,1))
        self.assertEqual(self.rows[9].value[22+57*6+32:22+57*6+34],bytes((3,1)))

    def test_complete_constructor_takes_query_and_case_without_host_decision_flags(self):
        package = recipe_wire_v2.decode_recipe_package_v2(build_teaching_recipe_package(),8)
        recipes = {r.recipe_id:r for r in package.logical.recipes}
        self.assertNotIn(110,recipes)
        self.assertNotIn(111,recipes)
        self.assertEqual(tuple((d.value_type,d.width) for d in recipes[126].inputs),
                         ((bootstrap.UINT,32),(bootstrap.UINT,8)))
        self.assertEqual(tuple(n.auxiliary_u16 for n in recipes[126].nodes if n.opcode == 22),
                         (122,125,119))
        self.assertEqual({n.auxiliary_u16 for n in recipes[125].nodes if n.opcode == 2},
                         {24,26,27})
        self.assertTrue(any(n.opcode == 22 and n.auxiliary_u16 == 121 for n in recipes[122].nodes))
        self.assertTrue(any(n.opcode == 22 and n.auxiliary_u16 == 114 for n in recipes[119].nodes))

    def test_mutations_separate_local_crc_from_envelope_identity(self):
        value = self.rows[6].value
        block = value[134:325]
        self.assertEqual(bootstrap.decode_section_envelope(
            bootstrap.decode_common_block(block,8).payload).payload, b'\0')
        for index in range(10):
            row = value[516+12*index:528+12*index]
            offset,width,replacement,recheck,local,agreement = (
                int.from_bytes(row[i:i+2],'big') for i in range(0,12,2))
            mutant = bytearray(block)
            mutant[offset:offset+width] = replacement.to_bytes(width,'big')
            if recheck:
                mutant[187:] = bootstrap.crc32c_v0(bootstrap.LOCAL_DOMAIN+mutant[:187]).to_bytes(4,'big')
            if local:
                accepted = bootstrap.decode_common_block(bytes(mutant),8)
                envelope = bootstrap.decode_section_envelope(accepted.payload)
                self.assertEqual(index,5)
                self.assertEqual(accepted.section_id,65936)
                self.assertEqual(envelope.section_id,400)
                self.assertEqual(agreement,0)
            else:
                with self.assertRaises(bootstrap.BootstrapReject):
                    bootstrap.decode_common_block(bytes(mutant),8)

    def test_content_contexts_and_real_namespace_bridges_remain_distinct(self):
        value = self.rows[11].value
        context = tuple(int.from_bytes(value[i:i+2],'big') for i in range(0,18,2))
        self.assertEqual(context,(0,588,588,1,746,746,2,29,29))
        mini_length = int.from_bytes(value[206:210],'big')
        self.assertEqual(mini_length,575)
        from golden_board import content
        mini = content.projection_view(content.stream_validation(value[210:785]))
        self.assertEqual(len(mini.records),29)
        self.assertEqual({record.kind for record in mini.records},set(range(1,15)))
        bridges = value[2053:2077]
        self.assertEqual(bridges.hex(),'00000064024c024d00020001000000c802cc02cd00030001')
        from golden_board.position_teaching_v2 import build_position_teaching_v2
        self.assertEqual(value[2077:],build_position_teaching_v2(self.compiled).value)

    def test_mapping_examples_include_slot_wrap_and_both_pad_boundaries(self):
        value = self.rows[8].value
        parameters = [tuple(int.from_bytes(value[j:j+4],'big') for j in range(i,i+40,4)) for i in (0,40)]
        self.assertEqual(parameters,[(2040,128,1784,3182656,1841,2,921,3567,3179087,356920),
                                     (1952,128,1696,2876416,1664,15,111,3391,2873023,356920)])
        for geometry,p in enumerate(parameters):
            side,width,interior,population,units,multiplier,inverse,affine,affine_inverse,offset = p
            start = 80+geometry*192
            rows = [tuple(int.from_bytes(value[j:j+4],'big') for j in range(i,i+24,4))
                    for i in range(start,start+192,24)]
            self.assertLess(rows[4][2],multiplier)
            self.assertEqual(rows[-2][3:],(1728*units,(affine*1728*units+offset)%population,1))
            self.assertEqual(rows[-1][3],population-1)
            self.assertEqual(rows[-3][1],1727)
            self.assertNotEqual(rows[-3][0],units)
            for unit,bit,slot,logical,physical,kind in rows:
                self.assertEqual(affine_inverse*((physical-offset)%population)%population,logical)
                if kind == 0:
                    self.assertEqual((inverse*slot)%units+1,unit)
                    self.assertEqual(logical,1728*slot+bit)


if __name__ == '__main__':
    unittest.main()
