"""Numeric route teaching carries checked relationships, not labels."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import unittest

from golden_board import bootstrap, m2_codec, recipe_wire_v1
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
                         (16,64,96,296,226,210,636,544,464,430,314,2421))
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

    def test_group_conflict_and_rep_only_are_separate_and_unambiguous(self):
        value = self.rows[9].value
        self.assertEqual(value[206:215], bytes((2,1,1,1,1,3,2,4,3)))
        self.assertEqual(value[245:254], bytes((1,1,1,1,1,3,1,3,2)))
        rows = [value[104+i*8:112+i*8] for i in range(9)]
        self.assertEqual(rows[4][-2:], b'\0\1')
        self.assertEqual(rows[5][-2:], b'\1\0')
        self.assertEqual(rows[8][-3:], b'\0\0\0')

    def test_group_trace_connects_physical_allocation_raw_unknowns_and_decision(self):
        from golden_board.m2_teaching_recipe_v2 import build_teaching_recipe_package
        from golden_board.m2_transport_v2 import aggregate_replica_group
        value = self.rows[9].value
        self.assertEqual(len(value),430,'Missing runnable recovery traces')
        self.assertEqual(tuple(int.from_bytes(value[i:i+4],'big') for i in range(48,72,4)),
                         (400,0,1,5,11,15))
        a = self.rows[6].value[134:325]
        encoded = self.rows[7].value[112:328]
        lanes = []
        for first,count in zip(value[402:412:2],value[403:412:2],strict=True):
            unknown = tuple(range(first,first+count))
            lane = bytearray(encoded)
            for bit in unknown:
                lane[bit//8] &= ~(1 << (7-bit%8))
            lanes.append(m2_codec.CopyObservation(bytes(lane),unknown))
        recovered = aggregate_replica_group(lanes)
        self.assertEqual(recovered.lane_states,(1,)*5)
        self.assertEqual(recovered.repetition_block,a)
        self.assertEqual(recovered.group_state,3)
        guessed = aggregate_replica_group(tuple(m2_codec.CopyObservation(lane.encoded,()) for lane in lanes))
        self.assertEqual(guessed.lane_states,(1,)*5)
        self.assertEqual((guessed.repetition_state,guessed.group_state),(1,1))
        self.assertNotEqual(guessed.repetition_block,a)
        self.assertEqual(value[412:],bytes((0,0,0,0,0,1,1,0,1,1,3,1,1,1,1,1,1,3)))
        package = recipe_wire_v1.decode_recipe_package_v1(build_teaching_recipe_package(),8)
        for start in (*range(294,402,12),412):
            trace = value[start:start+12]
            result = recipe_wire_v1.evaluate_recipe_v1(package,110,
                tuple(bytes((v,)) for v in trace[:9]))
            self.assertEqual((result.status,b''.join(result.outputs)),(0,trace[9:]))
        self.assertEqual(value[351:354],bytes((3,4,0)))
        self.assertEqual(value[363:366],bytes((2,3,1)))

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
        bridges = value[1989:2013]
        self.assertEqual(bridges.hex(),'00000064024c024d00020001000000c802cc02cd00030001')
        from golden_board.position_teaching_v2 import build_position_teaching_v2
        self.assertEqual(value[2013:],build_position_teaching_v2(self.compiled).value)

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
