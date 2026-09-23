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
                         (16,64,96,296,226,210,636,544,464,443,314,2421))
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

    def test_physical_context_and_lane_states_are_carried_before_decision(self):
        from golden_board.m2_teaching_recipe_v2 import build_teaching_recipe_package
        from golden_board.m2_transport_v2 import aggregate_replica_group
        value = self.rows[9].value
        self.assertEqual(len(value),443)
        self.assertEqual(value[:4],b'\0\4\0\6','missing finite physical roster')
        roster = [tuple(int.from_bytes(value[j:j+2],'big') for j in range(i,i+12,2))
                  for i in range(4,52,12)]
        self.assertEqual(roster[2:],[(400,0,1,5,11,15),(401,0,1,2,16,17)])
        offsets = value[52:60]
        widths = (2,4,2,2,2,2,2,4)
        self.assertEqual(value[60],2)
        keys=[]
        for base in (61,81):
            cursor=base; key=[]
            for width in widths:
                key.append(int.from_bytes(value[cursor:cursor+width],'big'));cursor+=width
            keys.append(tuple(key))
        self.assertEqual(keys,[(8,400,0,4,0,0,1,23),(8,401,0,4,0,0,1,23)])
        self.assertEqual(value[104:106],bytes((13,4)))
        templates=[value[i:i+4] for i in range(106,158,4)]
        self.assertEqual(value[160:162],bytes((8,24)))
        encoded=(self.rows[7].value[112:328],self.rows[7].value[328:544])
        common=(self.rows[6].value[134:325],self.rows[6].value[325:516])
        package=recipe_wire_v1.decode_recipe_package_v1(build_teaching_recipe_package(),8)
        groups=[]
        for case,at in enumerate(range(162,354,24)):
            row=value[at:at+24]
            owner=next(r for r in roster if r[4]==row[0])
            expected=next(k for k in keys if (k[1],k[5],k[6])==owner[:3])
            factor=owner[3]; lanes=[]
            self.assertEqual(row[1+factor:6],bytes(5-factor))
            for token in row[1:1+factor]:
                if token==0:lanes.append(None);continue
                source,unknown,first,count=templates[token-1]
                raw=bytearray(encoded[source]); erased=[]
                for bit in range(first,first+count):
                    if unknown: raw[bit//8]&=~(1<<(7-bit%8));erased.append(bit)
                    else:raw[bit//8]^=1<<(7-bit%8)
                lanes.append(m2_codec.CopyObservation(bytes(raw),tuple(erased)))
            group=aggregate_replica_group(lanes); groups.append(group)
            self.assertEqual(row[6:11],bytes(group.lane_states)+bytes(5-factor))
            self.assertEqual(row[11],group.repetition_state)
            checked={raw for state,raw in zip(group.lane_states,group.lane_blocks,strict=True) if state in (2,3)}
            if group.repetition_state==3:checked.add(group.repetition_block)
            def key(raw):return tuple(int.from_bytes(raw[o:o+w],'big') for o,w in zip(offsets,widths,strict=True))
            identity=bool(checked) and all(key(raw)==expected for raw in checked)
            self.assertEqual(row[20],int(identity))
            result=recipe_wire_v1.evaluate_recipe_v1(package,110,tuple(bytes((v,)) for v in row[12:21]))
            self.assertEqual((result.status,b''.join(result.outputs)),(0,row[21:24]))
            if case==6:
                guessed=aggregate_replica_group(tuple(m2_codec.CopyObservation(l.encoded,()) for l in lanes))
                self.assertEqual(group.repetition_block,common[0])
                self.assertEqual(group.lane_states,(1,)*5)
                self.assertEqual((guessed.repetition_state,guessed.group_state),(1,1))
        self.assertEqual(groups[0].repetition_state,0)
        self.assertEqual(value[174+2*24+10],2)  # clean A remains verified
        self.assertEqual(value[174+3*24+10],3)  # corrected A is not verified
        self.assertEqual(value[174+4*24+9:174+4*24+12],bytes((3,4,0)))
        self.assertEqual(value[174+5*24+9:174+5*24+12],bytes((2,3,1)))
        self.assertEqual(value[174+7*24+8:174+7*24+12],bytes((0,1,2,0)))

    def test_erasure_coordinates_and_raw_symbol_counts_feed_existing_recipes(self):
        from golden_board.m2_teaching_recipe_v2 import build_teaching_recipe_package
        package=recipe_wire_v1.decode_recipe_package_v1(build_teaching_recipe_package(),8)
        value=self.rows[9].value
        self.assertEqual(value[354:356],bytes((3,4)))
        anchors=[(int.from_bytes(value[i:i+2],'big'),value[i+2],value[i+3]) for i in range(356,368,4)]
        self.assertEqual(anchors,[(0,0,1),(63,0,64),(72,1,1)])
        for bit,word,position in anchors:self.assertEqual((word,position),(bit//72,bit%72+1))
        self.assertEqual(value[368:373],bytes((7,0,0,0,30)))
        incoming=value[373:386]
        self.assertEqual(incoming.hex(),'00014000000000062001400000')
        expected=self.rows[6].value[134:142]
        for stored in (incoming[:9],incoming[:7]+bytes((incoming[7]|1,))+incoming[8:9]):
            result=recipe_wire_v1.evaluate_recipe_v1(package,30,(stored,incoming[9:10],incoming[10:]))
            self.assertEqual((result.status,result.outputs),(0,(expected,)))
        self.assertEqual(value[386:390],bytes((0,113,4,8)))
        derived=[]
        for i in range(390,422,8):
            row=value[i:i+8];factor=row[0];symbols=row[1:6]
            self.assertEqual(symbols[factor:],bytes((2,))*(5-factor))
            args=bytes((factor,symbols[:factor].count(0),symbols[:factor].count(1)));derived.append(args)
            result=recipe_wire_v1.evaluate_recipe_v1(package,113,tuple(bytes((v,)) for v in args))
            self.assertEqual((result.status,b''.join(result.outputs)),(0,row[6:]))
        self.assertEqual(derived,[bytes((2,1,1)),bytes((5,1,4)),bytes((5,0,1)),bytes((5,0,0))])
        self.assertEqual(value[422],5)
        for i in range(423,443,4):
            length=int.from_bytes(value[i:i+2],'big');count,last=value[i+2:i+4]
            self.assertEqual((count,last),((length+156)//157,length-157*(count-1)))

    def test_typed_constructor_rejects_the_prior_packed_descriptor_reading(self):
        from golden_board.m2_teaching_recipe_v2 import build_teaching_recipe_package
        package=recipe_wire_v1.decode_recipe_package_v1(build_teaching_recipe_package(),8)
        value=self.rows[9].value
        self.assertEqual(value[101:106],bytes((0,111,0,13,4)))
        self.assertEqual(value[158:160],bytes((0,110)))
        words=(self.rows[7].value[112:121],self.rows[7].value[328:337])
        for i in range(13):
            descriptor=value[106+4*i:110+4*i]
            source,unknown,first,count=descriptor
            result=recipe_wire_v1.evaluate_recipe_v1(package,111,
                words+tuple(bytes((v,)) for v in descriptor))
            mask=((1<<count)-1)<<(72-first-count)
            original=int.from_bytes(words[source],'big')
            expected=original & ~mask if unknown else original ^ mask
            self.assertEqual(result.outputs,(expected.to_bytes(9,'big'),
                (mask if unknown else 0).to_bytes(9,'big')))
            if unknown:
                self.assertGreater(int.from_bytes(descriptor[1:3],'big'),72)
        self.assertEqual(value[110:114],bytes((0,0,59,5)))
        self.assertEqual(value[138:142],bytes((0,1,59,5)))

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
