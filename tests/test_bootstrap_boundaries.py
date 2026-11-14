"""Candidate boundaries preserve literal bits, zero fields and strict extraction."""
import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from golden_board import bootstrap_clarity as frozen, clean_carrier as carrier
from golden_board import raw_draw as draw


ROOT = Path(__file__).resolve().parents[1]


class BootstrapBoundaryTests(unittest.TestCase):
    def candidate(self):
        self.assertIsNotNone(importlib.util.find_spec('golden_board.bootstrap_boundaries'),
                             'The separately identified bounded candidate is missing')
        from golden_board import bootstrap_boundaries
        return bootstrap_boundaries

    def panel(self, ordinal, used=506509):
        route = self.candidate().make_route(used, *frozen.example())
        return draw.panel(route, ordinal-1, columns=32)

    def assert_box(self, panel, left, top, right, bottom):
        for y in range(top, bottom+1):
            self.assertEqual(panel[y*64+left], 1, (left, y))
            self.assertEqual(panel[y*64+right], 1, (right, y))
        for y in (top, bottom):
            self.assertEqual(panel[y*64+left:y*64+right+1], b'\1'*(right-left+1))

    def assert_field(self, panel, value, width, x, y):
        self.assert_box(panel, x-2, y-2, x+width+1, y+2)
        self.assertEqual(draw._read_number(panel, x, y, width), value)
        # A white inset separates the data from its boundary on every side.
        for row in (y-1, y+1):
            self.assertFalse(any(panel[row*64+x-1:row*64+x+width+1]))
        for col in (x-1, x+width):
            self.assertEqual(panel[y*64+col], 0)

    def word(self, panel, y):
        self.assert_box(panel, 8, y-2, 55, y+2)
        return bytes(draw._read_number(panel, x, y, 8) for x in (10,22,34,46))

    def test_bit_positions_have_fixed_bounded_columns_with_equal_margins(self):
        p = self.panel(2)
        for index in range(8):
            self.assert_field(p, 1 << index, 8, 20, 12+6*index)
            self.assert_field(p, index+1, 4, 40, 12+6*index)
        ink = [x for y in range(4,63) for x in range(64) if p[y*64+x]]
        self.assertEqual((min(ink), 63-max(ink)), (18,18))

    def test_split_bytes_include_entirely_zero_high_and_low_fields(self):
        p = self.panel(6)
        values = (0x0001,0x0100,0x0180,0x8001,0x1234,0x3412,0x00a5,0xa500)
        for index, value in enumerate(values):
            y = 12+6*index
            self.assert_field(p, value, 16, 9, y)
            self.assert_field(p, value >> 8, 8, 33, y)
            self.assert_field(p, value & 255, 8, 47, y)

    def test_parameter_fields_share_the_least_significant_bit_and_roundtrip_limits(self):
        candidate = self.candidate()
        for used in (1,364,506509,507904):
            route = candidate.make_route(used, *frozen.example())
            p = draw.panel(route, 6, columns=32)
            for y, value, width, x in ((12,2048,16,32), (24,64,16,32),
                                       (36,8,16,32), (48,used,32,16)):
                self.assert_field(p, value, width, x, y)
                self.assertEqual(x+width-1, 47)
            self.assertEqual(candidate.parameters(route), used)
        for bad in (0,507905,True):
            with self.assertRaises(ValueError):
                candidate.make_route(bad, *frozen.example())

    def test_shift_examples_keep_a_visible_zero_discarded_bit(self):
        p = self.panel(9)
        for y, before, after, bit in ((10,53,26,1), (28,2147483649,1073741824,1),
                                      (46,2197175160,1098587580,0)):
            self.assert_field(p, before, 32, 9, y)
            self.assert_field(p, after, 32, 9, y+7)
            self.assert_field(p, bit, 1, 53, y)

    def test_polynomial_representations_preserve_32_and_33_bit_extents(self):
        p = self.panel(10)
        for value, width, x, y in ((0xffffffff,32,16,14), (0x1edc6f41,32,16,32),
                                   (0x11edc6f41,33,15,50)):
            self.assert_field(p, value, width, x, y)
            self.assertEqual(x+width-1, 47)

    def test_crc_input_combines_a_bounded_byte_with_the_low_end_of_the_word(self):
        p = self.panel(11)
        self.assert_box(p, 5,5,58,25)
        self.assertEqual(self.word(p, 10), b'\xff\xff\xff\xff')
        self.assert_field(p, 53, 8, 46,20)
        self.assertEqual(self.word(p, 36), b'\xff\xff\xff\xca')

    def test_final_xor_result_and_four_output_bytes_have_the_same_ordered_bits(self):
        p = self.panel(13)
        self.assert_box(p, 5,5,58,25)
        mask, state, result = [self.word(p, y) for y in (10,20,36)]
        self.assertEqual(state, bytes.fromhex('a890f103'))
        self.assertEqual(result, bytes.fromhex('576f0efc'))
        self.assertEqual(bytes(a ^ b for a,b in zip(mask,state)), result)
        for x, value in zip((10,22,34,46), (87,111,14,252)):
            self.assert_field(p, value, 8, x,54)
        self.assertEqual(bytes(draw._read_number(p,x,54,8) for x in (10,22,34,46)), result)

    def test_matching_checksum_fields_retain_trailing_zero_bits(self):
        p = self.panel(14)
        self.assert_field(p, 53, 8,6,12)
        self.assert_field(p, 0x576f0efc,32,19,12)
        self.assert_field(p, 0x576f0efc,32,19,19)
        p = self.panel(19)
        self.assert_field(p, int.from_bytes(frozen.example()[0][-4:],'big'),32,16,45)
        self.assert_box(p,6,31,57,35)
        self.assert_box(p,6,54,57,58)

    def test_checksum_verdicts_use_the_same_bounded_bits_as_equality_examples(self):
        checks, truth = self.panel(14), self.panel(8)
        for y, value, truth_y in ((12,1,12),(30,0,24),(48,1,48)):
            with self.subTest(value=value, row=y):
                self.assert_field(checks, value,1,56,y+4)
                verdict = b''.join(checks[row*64+54:row*64+59]
                                   for row in range(y+2,y+7))
                equality = b''.join(truth[row*64+55:row*64+60]
                                    for row in range(truth_y-2,truth_y+3))
                self.assertEqual(verdict, equality)

    def test_reference_counts_increase_without_forward_references(self):
        p = self.panel(18)
        earlier = set()
        for top, ident, refs in ((7,6,()), (21,7,()), (35,8,(6,)), (49,9,(7,8))):
            self.assert_field(p, ident,8,5,top+4)
            self.assert_field(p, len(refs),8,19,top+4)
            self.assert_box(p,32,top,60,top+8)
            for x, ref in zip((36,49), refs):
                self.assert_field(p, ref,8,x,top+4)
                self.assertIn(ref, earlier)
            if not refs:
                self.assertFalse(any(p[y*64+x] for y in range(top+1,top+8)
                                     for x in range(33,60)))
            earlier.add(ident)

    def test_reserve_fields_and_width_label_include_their_invisible_zeros(self):
        p = self.panel(32)
        for y, value in ((10,0),(20,506509),(30,507904),(40,1395)):
            self.assert_field(p, value,32,9,y)
        self.assert_field(p, 0,32,16,49)
        self.assert_field(p, 32,8,28,57)
        self.assertFalse(any(p[62*64:63*64]))

    def test_other_panels_and_all_header_counters_stay_exact(self):
        route = self.candidate().make_route(506509, *frozen.example())
        canonical = frozen.make_route(506509, *frozen.example())
        changed = {2,6,7,9,10,11,13,14,18,19,32}
        for ordinal in range(1,33):
            p = draw.panel(route, ordinal-1, columns=32)
            old = draw.panel(canonical, ordinal-1, columns=32)
            self.assertEqual(p[:4*64], old[:4*64])
            self.assertEqual(p[63*64:], b'\1'*64)
            if ordinal not in changed:
                self.assertEqual(p, old)

    def test_explicit_candidate_profile_decodes_without_changing_canonical_defaults(self):
        candidate = self.candidate()
        docs = {1:frozen.miniature()}
        symbols, layout = carrier.make_carrier(docs, bootstrap=candidate)
        canonical, _ = carrier.make_carrier(docs)
        self.assertEqual(layout['bootstrap_layout'], 'bootstrap-field-boundaries-1')
        self.assertEqual(symbols[64*2048:], canonical[64*2048:])
        self.assertEqual(carrier.decode_symbols(symbols, bootstrap=candidate)['documents'], docs)
        serial = symbols.translate(bytes.maketrans(b'\0\1',b'01'))+b'\n'
        self.assertEqual(carrier.decode_serial(serial, bootstrap=candidate)['documents'], docs)
        with self.assertRaises(ValueError):
            carrier.decode_symbols(symbols)
        with self.assertRaises(ValueError):
            carrier.decode_symbols(canonical, bootstrap=candidate)
        for where in (6*64+12*2048+32, 6*64+10*2048+30, 64*2048+364*8):
            bad = bytearray(symbols)
            bad[where] ^= 1
            with self.assertRaises(ValueError):
                carrier.decode_symbols(bytes(bad), bootstrap=candidate)

    def test_candidate_build_profile_is_an_explicit_cli_option(self):
        result = subprocess.run([str(ROOT/'gb'),'build','--help'],
                                capture_output=True,text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--bootstrap', result.stdout)
        self.assertIn('field-boundaries', result.stdout)

    def test_candidate_renderer_checks_the_profile_and_preserves_existing_output(self):
        canonical = (ROOT/'artifacts/GOLDEN-BOARD.bin').read_bytes()
        route = self.candidate().make_route(506509, *frozen.example())
        packed = carrier.pack_bits(route)+canonical[16384:]
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'candidate.bin', Path(tmp)/'images'
            source.write_bytes(packed)
            command = [sys.executable,str(ROOT/'tools/render-guide-images.py'),
                       '--source',str(source),'--output',str(output)]
            # The frozen renderer must not silently treat another layout as canonical.
            rejected = subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertFalse(output.exists())
            accepted = subprocess.run(command+['--bootstrap','field-boundaries'],
                                      capture_output=True,text=True)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            identity = json.loads((output/'source.json').read_bytes())
            self.assertEqual(identity['sha256'], hashlib.sha256(packed).hexdigest())
            self.assertEqual(identity['bootstrap_layout'], 'bootstrap-field-boundaries-1')
            for ordinal in (2,7,13,18,32):
                self.assertTrue((output/f'bootstrap-{ordinal:02d}-comparison.png').is_file())
            marker = output/'owner-file'
            marker.write_bytes(b'preserve')
            repeated = subprocess.run(command+['--bootstrap','field-boundaries'],
                                      capture_output=True,text=True)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertEqual(marker.read_bytes(), b'preserve')
            source.write_bytes(canonical)
            wrong_profile = subprocess.run(command+['--bootstrap','field-boundaries',
                                                    '--output',str(Path(tmp)/'wrong')],
                                           capture_output=True,text=True)
            self.assertNotEqual(wrong_profile.returncode, 0)
            self.assertFalse((Path(tmp)/'wrong').exists())


if __name__ == '__main__':
    unittest.main()
