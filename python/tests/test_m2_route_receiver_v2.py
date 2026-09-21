"""Observed framing and executable examples, independently of source equality."""
from pathlib import Path
import unittest
from unittest.mock import patch

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
            self.assertEqual(result.prefix_bytes, 25285)
            self.assertEqual(result.package.profile_version, 8)
            self.assertEqual(result.example_count, 32)
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
                        removed[46:48]=(46).to_bytes(2,'big')
                        removed[48:52]=(len(removed)-64).to_bytes(4,'big')
                        removed[56:60]=(len(removed)*8).to_bytes(4,'big')
                        with self.subTest(sector=sector,fact=fact,operator='remove'),self.assertRaises(DecoderError):
                            decode_observed_route_v2(bytes(removed),2040,112,sector)
                    offset=end
                self.assertEqual(seen,list(range(1,13)))


if __name__ == '__main__':
    unittest.main()
