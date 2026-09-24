"""Owned observation generation, with source data confined to the oracle side."""
from pathlib import Path
from unittest.mock import patch
import unittest

from golden_board import bootstrap, curriculum, m2_policy, m2_codec
from golden_board.m2_slice import compile_slice_v0
from golden_board.m2_slice_v1 import compile_slice_v1
from golden_board.m2_carrier_v2 import build_development_carrier
from golden_board.m2_damage_v2 import DamageCorpusV2

ROOT = Path(__file__).resolve().parents[2]


class RevisedDamageObservations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raws = tuple(ROOT.joinpath(p).read_bytes() for p in (
            'studies/m2/slice-v0.json','conformance/content-v0.json','conformance/chess-v0.json',
            'reports/game-set-v0.bin','spec/content-v0.md','spec/constants-v0.toml','spec/curriculum-v0.toml'))
        compiled = compile_slice_v1(ROOT.joinpath('studies/m2/slice-v1.json').read_bytes(),*raws)
        image = build_development_carrier(compiled,compile_slice_v0(*raws),curriculum.load_blueprint(raws[-1]),
            m2_policy.load_profile_policy(ROOT.joinpath('spec/profile-policy-v0.toml').read_bytes()).capacity_policy)
        cls.corpus = DamageCorpusV2(image,alternate_route_owner_raw=ROOT.joinpath('spec/route-data-v0.json').read_bytes())

    def test_counts_domains_and_lazy_case_identity(self):
        corpus = self.corpus
        units=corpus.mapping.units
        self.assertEqual((corpus.side,corpus.width,units),(2040,112,1908))
        self.assertEqual(corpus.family_counts,(16,4,256,128,units,21,4*units,415))
        self.assertEqual(sum(corpus.family_counts),840+5*units)
        self.assertEqual(corpus.boundary_count,21)
        for family,ordinal in (('D0',True),('D8',0),('D0',16),('D7',415),('D3',-1)):
            with self.subTest(family=family,ordinal=ordinal), self.assertRaises(ValueError):
                corpus.case(family,ordinal)
        with patch('golden_board.m2_decoder.ObservationDecoder.decode',side_effect=AssertionError('decoder input leak')):
            case = corpus.case('D0',0)
        self.assertEqual(case.observation,corpus.carrier)
        self.assertEqual(case.case_id,'D0-000000')
        self.assertEqual(case.identity()['observation_bytes'],len(corpus.carrier))
        self.assertNotIn('expected_result',case.identity())

    def test_omission_and_ordering_use_physical_ids(self):
        from golden_board.m2_decoder import _parse_units
        corpus = self.corpus
        units=corpus.mapping.units
        omitted = _parse_units(corpus.case('D4',units-1).observation,2389)
        self.assertEqual(tuple(row.unit_id for row in omitted),tuple(range(1,units)))
        expected = corpus.case('D5',0).observation
        for ordinal in (1,2,3,4,5,20):
            units = _parse_units(corpus.case('D5',ordinal).observation,2389)
            self.assertEqual({x.unit_id:x.encoded for x in units},corpus.clean_encoded)
            self.assertNotEqual(corpus.case('D5',ordinal).observation,expected)

    def test_matrix_erasure_sets_and_d3_parent_prefix_are_exact(self):
        corpus = self.corpus
        first = corpus.case('D1',0).observation[2:]
        combined = corpus.case('D6',0).observation[2:]
        self.assertEqual(first.count(2),corpus.width*(corpus.side-corpus.width))
        self.assertEqual(combined.count(2)-first.count(2),1728)
        for ordinal in (1,corpus.mapping.units-1,corpus.mapping.units,0):
            another = corpus.case('D6',ordinal).observation[2:]
            self.assertEqual(another.count(2),corpus.width*(corpus.side-corpus.width)+1728)
        self.assertEqual(corpus.case('D6',0).observation[2:],combined)
        for ordinal in (0,32,64,96):
            base = corpus.damage_coordinates(ordinal)
            extra = corpus.damage_coordinates(ordinal,1)
            self.assertEqual(extra[:-1],base)
            weight=max(64,(corpus.interior**2+1999)//2000)
            self.assertEqual(len(base),weight)
            self.assertEqual(len(set(extra)),weight+1)

    def test_new_compressed_cases_keep_integrity_but_reject_codec(self):
        from golden_board import body_codec_v1
        from golden_board.m2_decoder import _parse_units
        corpus = self.corpus
        for ordinal in range(14):
            case = corpus.boundary_case(ordinal)
            parameters = {row['id']:row['value'] for row in case.identity()['parameter_projection']}
            section_id = parameters['section_id']
            units = {x.unit_id:x.encoded for x in _parse_units(case.observation,2389)}
            rows = corpus.rows_by_section[section_id]
            blocks = []
            for row in rows:
                if row['replica_index'] == 0:
                    result = m2_codec._eh72_decode_unit(units[row['physical_unit_id']],(),8)
                    self.assertEqual(result.state,'verified')
                    blocks.append(result.decoded)
            _,raw = bootstrap.assemble_semantic_copy(blocks,8)
            envelope = bootstrap.decode_section_envelope(raw)
            self.assertEqual(len(envelope.payload),len(corpus.sections[section_id].payload))
            with self.subTest(case=case.case_id), self.assertRaises(ValueError):
                body_codec_v1.decode_body(1,envelope.payload)

    def test_compact_and_tier_targets_are_changed_without_extra_bytes(self):
        corpus = self.corpus
        for ordinal in range(408,414):
            case = corpus.case('D7',ordinal)
            self.assertEqual(len(case.observation),len(corpus.carrier))
            self.assertNotEqual(case.observation,corpus.carrier)
        for ordinal in range(14,20):
            case = corpus.boundary_case(ordinal)
            self.assertEqual(len(case.observation),len(corpus.case('D5',0).observation))
        self.assertEqual(corpus.case('D7',414).operator,'foreign-profile7-bootstrap')
        self.assertEqual(corpus.boundary_case(20).channel,'OBS_BITS')

    def test_compact_mutants_reject_observed_route_and_do_not_change_interior(self):
        from golden_board.m2_route_receiver_v2 import decode_observed_route_v2
        from golden_board.m2_decoder import DecoderError
        corpus = self.corpus
        for ordinal in range(408,414):
            raw = corpus.case('D7',ordinal).observation
            for sector in range(4):
                bits = bytearray()
                for offset in range(len(corpus.prefixes[sector])*8):
                    row,column = bootstrap.sector_cell(corpus.side,corpus.width,sector,offset)
                    index = row*corpus.side+column
                    bits.append((raw[4+index//8]>>(7-index%8))&1)
                prefix = bytes(sum(bits[i+j]<<(7-j) for j in range(8)) for i in range(0,len(bits),8))
                expected=bytearray(corpus.prefixes[sector])
                frame=64
                while expected[frame+1]!=5:
                    frame+=8+int.from_bytes(expected[frame+4:frame+8],'big')
                package=frame+8
                recipe=package+64
                for _ in range(int.from_bytes(expected[package+18:package+20],'big')):
                    recipe+=16+int.from_bytes(expected[recipe+12:recipe+16],'big')
                number=ordinal-408
                if number==0:
                    expected[package+8:package+10]=bytes(2)
                elif number==1:
                    expected[package+48]=1
                elif number==2:
                    value=int.from_bytes(expected[package+32:package+36],'big')
                    expected[package+32:package+36]=(value-1).to_bytes(4,'big')
                elif number==5:
                    value=int.from_bytes(expected[recipe+16:recipe+24],'big')
                    expected[recipe+16:recipe+24]=(value+1).to_bytes(8,'big')
                else:
                    count=int.from_bytes(expected[recipe+4:recipe+6],'big')+int.from_bytes(expected[recipe+6:recipe+8],'big')
                    node=recipe+32
                    for _ in range(count):
                        node+=1  # carried descriptor type
                        for byte in range(5):
                            value=expected[node];node+=1
                            if value<128:break
                        else:self.fail('unterminated carried descriptor width')
                    self.assertEqual((expected[node]&31,expected[node]>>5),(2,4))
                    expected[node]&=0xe0 if number==3 else 0x1f
                    self.assertEqual([i for i,(a,b) in enumerate(zip(prefix,corpus.prefixes[sector],strict=True)) if a!=b],[node])
                self.assertEqual(prefix,bytes(expected))
                with self.subTest(case=ordinal,sector=sector),self.assertRaises(DecoderError):
                    decode_observed_route_v2(prefix,corpus.side,corpus.width,sector)
            for row in range(corpus.width,corpus.side-corpus.width):
                start = (row*corpus.side+corpus.width)//8+4
                self.assertEqual(raw[start:start+corpus.interior//8],corpus.carrier[start:start+corpus.interior//8])

    def test_owned_case_boundaries_preserve_inherited_parameter_abi(self):
        from golden_board.m2_damage import _r3_case_shape
        corpus = self.corpus
        for ordinal in (0,1,2,3,4,5,6,7,8,9,10,11,15,16,17,272,273,400,401,402,403,404,405,406,407):
            case = corpus.case('D7',ordinal)
            channel,operator,projection,_ = _r3_case_shape('D7',ordinal)
            with self.subTest(ordinal=ordinal):
                self.assertEqual((case.channel,case.operator),(channel,operator))
                self.assertEqual(tuple((k,t) for k,t,_ in case.parameters),projection)
                self.assertLessEqual(len(case.observation),4194306)


if __name__ == '__main__':
    unittest.main()
