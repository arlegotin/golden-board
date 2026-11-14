"""Preview's encoded miniature, pictures and discovery prerequisites agree."""
import importlib.util
from pathlib import Path
import unittest

from golden_board import clean_carrier as carrier, direct_bootstrap as baseline
from golden_board import raw_draw as draw
from golden_board.checksum import crc32c
from golden_board.document import decode_document, encode_document


class BootstrapClarityTests(unittest.TestCase):
    def preview(self):
        self.assertIsNotNone(importlib.util.find_spec('golden_board.bootstrap_clarity'),
                             'The separate authored clarity preview is missing')
        from golden_board import bootstrap_clarity
        return bootstrap_clarity

    def test_rectangular_glyphs_roundtrip_without_changing_other_records(self):
        p = self.preview()
        model = decode_document(p.miniature())
        old = decode_document(bytes.fromhex((Path(__file__).resolve().parents[1]/'spec/vectors/pre-clarity-mini.hex').read_text()))
        self.assertEqual(len(p.miniature()), 326)
        self.assertEqual(model['entries'], old['entries'])
        for ident, mask in ((0, 0), (1, 0xd4), (2, 0x28)):
            self.assertEqual(model['records'][ident],
                             dict(kind=1, id=ident, rows=2, cols=3, mask=[mask]))
        self.assertEqual({k: v for k, v in model['records'].items() if k > 2},
                         {k: v for k, v in old['records'].items() if k > 2})
        self.assertEqual(encode_document(model['entries'], list(model['records'].values())),
                         p.miniature())
        for ident in model['records']:
            fields = p.record_fields(ident)
            kind, rid, length = fields[:3]
            self.assertEqual(int.from_bytes(rid, 'big'), ident)
            self.assertEqual(kind, bytes([model['records'][ident]['kind']]))
            self.assertEqual(int.from_bytes(length, 'big'), len(b''.join(fields[3:])))
            self.assertIn(b''.join(fields), p.miniature())

    def test_headers_anchor_parameters_and_complete_example_stay_consistent(self):
        p = self.preview()
        example = p.example()
        self.assertEqual(list(map(len, example)), [336, 28, 18])
        section, inventory, body = example
        self.assertEqual(carrier.decode_section(section)['payload'], p.miniature())
        self.assertEqual(carrier.decode_inventory(body)[1]['crc'], crc32c(section[:-4]))
        route = p.make_route(506509, *example)
        self.assertEqual(len(route), 2048*64)
        self.assertEqual(route, p.make_route(506509, *example))
        old = baseline.extract(carrier.unpack_bits((Path(__file__).resolve().parents[1]/'artifacts/GOLDEN-BOARD.bin').read_bytes()))
        self.assertEqual(draw.panel(route, 0, columns=32), draw.panel(old, 0, columns=32))
        self.assertEqual(p.parameters(route), 506509)
        bad = bytearray(route)
        bad[12*2048+6*64+14] ^= 1
        with self.assertRaisesRegex(ValueError, 'parameters'):
            p.parameters(bytes(bad))
        for ordinal in range(1, 33):
            panel = draw.panel(route, ordinal-1, columns=32)
            self.assertEqual(draw._read_number(panel, 56, 0, 8), ordinal)
            self.assertEqual(panel[63*64:], b'\1'*64)
        self.assertEqual(p.glyph_bits(1), (2, 3, bytes([1, 1, 0, 1, 0, 1])))

    def test_narrow_trace_rasters_preserve_full_blank_and_changed_tiles(self):
        p = self.preview()
        # Independently expand six tile IDs into a11×5 raster, including blanks.
        patterns = {0: ('000', '000'), 1: ('110', '101'), 2: ('001', '010')}
        for cells in ([0,1,1,1,0,1], [1,1,1,1,0,1], [1,1,1,1,0,0], [2]*6):
            expected = bytearray(11*5)
            for index, ident in enumerate(cells):
                for row, bits in enumerate(patterns[ident]):
                    for col, bit in enumerate(bits):
                        expected[(index//3*3+row)*11+index%3*4+col] = int(bit)
            width, height, pixels = p.frame_raster(cells)
            self.assertEqual((width, height, pixels), (11, 5, bytes(expected)))
        canvas = bytearray(4096)
        p.draw_frame(canvas, [2]*6, 51, 54)
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            p.draw_frame(canvas, [2]*6, 54, 54)

    def test_reference_groups_have_exact_ids_counts_and_lists(self):
        p = self.preview()
        panel = draw.panel(p.make_route(506509, *p.example()), 17, columns=32)
        for top, ident, refs in ((7,6,()), (21,7,()), (35,8,(6,7)), (49,9,(8,))):
            self.assertEqual(draw._read_number(panel, 5, top+4, 8), ident)
            self.assertEqual(draw._read_number(panel, 19, top+4, 8), len(refs))
            self.assertEqual([draw._read_number(panel, x, top+4, 8)
                              for x in (36,49)[:len(refs)]], list(refs))
            if not refs:
                self.assertFalse(any(panel[y*64+x] for y in range(top+1,top+8)
                                     for x in range(33,60)))

    def test_all_page_fields_keep_separate_widths_and_exact_data(self):
        p = self.preview()
        panel = draw.panel(p.make_route(506509, *p.example()), 24, columns=32)
        ys = (5,8,11,17,20,26,29,32,37,40,43,48,51,54,57,60)
        for y, field in zip(ys, p.record_fields(512)):
            self.assertEqual(draw._read_number(panel, 11, y, 4), len(field))
            self.assertEqual(panel[y*64+21:y*64+21+len(field)*8],
                             b''.join(draw._bits(value, 8) for value in field))

    def test_checksum_computation_follows_covered_range_not_stored_range(self):
        p = self.preview()
        section, *rest = p.example()
        panel = draw.panel(p.make_route(506509, section, *rest), 18, columns=32)
        self.assertEqual([draw._read_number(panel,x,33,16) for x in (8,24,40)],
                         [0,332,332])
        self.assertEqual(draw._read_number(panel,16,45,32),crc32c(section[:-4]))
        self.assertEqual([draw._read_number(panel,x,56,16) for x in (8,24,40)],
                         [332,4,336])

    def test_envelope_partitions_the_complete_section_without_false_sample_alignment(self):
        p = self.preview()
        panel = draw.panel(p.make_route(506509, *p.example()), 14, columns=32)
        expected = ((0,2,2),(2,4,6),(6,326,332),(332,4,336))
        for y, triple in zip((12,24,36,48), expected):
            self.assertEqual([draw._read_number(panel,x,y,16) for x in (8,24,40)],
                             list(triple))

    def test_parameter_block_has_equal_visible_margins_without_changing_values(self):
        p = self.preview()
        panel = draw.panel(p.make_route(506509, *p.example()), 6, columns=32)
        xs = [x for y in range(4,63) for x in range(64) if panel[y*64+x]]
        self.assertEqual(min(xs), 63-max(xs))
        self.assertEqual([draw._read_number(panel,14,12+row*12,width)
                          for row,width in enumerate((16,16,16,32))], [2048,64,8,506509])

    def test_page_has_blank_row_before_footer(self):
        p = self.preview()
        panel = draw.panel(p.make_route(506509, *p.example()), 24, columns=32)
        self.assertFalse(any(panel[62*64:63*64]))
        self.assertEqual(panel[63*64:], b'\1'*64)

    def test_outcome_pictures_have_blank_row_above_box_bottom(self):
        p = self.preview()
        panel = draw.panel(p.make_route(506509, *p.example()), 25, columns=32)
        model = decode_document(p.miniature())
        for top, ident in ((27,259),(46,260)):
            self.assertFalse(any(panel[(top+14)*64+34:(top+14)*64+62]))
            self.assertEqual(panel[(top+15)*64+33:(top+15)*64+63],b'\1'*30)
            width, height, expected = p.frame_raster(model['records'][ident]['cells'])
            actual = b''.join(panel[(top+9+row)*64+42:(top+9+row)*64+42+width]
                              for row in range(height))
            self.assertEqual(actual, expected)

    def test_both_glyph_definitions_precede_composition_and_match_their_pictures(self):
        p = self.preview()
        panel = draw.panel(p.make_route(506509, *p.example()), 21, columns=32)
        data = p.miniature()
        header = [data[:2],data[2:4],data[4:6],data[6:8],data[8:10]]
        groups = [(6,header),(24,p.record_fields(0)),(45,p.record_fields(1))]
        for top, fields in groups:
            for row, field in enumerate(fields):
                y = top+row*3
                self.assertEqual(draw._read_number(panel,3,y,4),len(field))
                self.assertEqual(panel[y*64+13:y*64+13+len(field)*8],
                                 b''.join(draw._bits(value,8) for value in field))
        for top, bits in ((30,'000000'),(51,'110101')):
            for index, bit in enumerate(bits):
                for dy in range(2):
                    for dx in range(2):
                        self.assertEqual(panel[(top+index//3*2+dy)*64+52+index%3*2+dx],int(bit))
        self.assertFalse(any(panel[62*64:63*64]))

    def test_composition_record_and_enlarged_picture_agree_with_cell_indices(self):
        p = self.preview()
        panel = draw.panel(p.make_route(506509, *p.example()), 22, columns=32)
        for row, field in enumerate(p.record_fields(256)):
            y = 8+row*4
            self.assertEqual(draw._read_number(panel,3,y,4),len(field))
            self.assertEqual(panel[y*64+13:y*64+13+len(field)*8],
                             b''.join(draw._bits(value,8) for value in field))
        rows = ('00001100110','00001010101','00000000000','11000000110','10100000101')
        for row, bits in enumerate(rows):
            for col, bit in enumerate(bits):
                for dy in range(2):
                    for dx in range(2):
                        self.assertEqual(panel[(48+row*2+dy)*64+4+col*2+dx],int(bit))
        for index in range(6):
            self.assertEqual(draw._read_number(panel,36+index%3*10,48+index//3*9,3),index)
        self.assertFalse(any(panel[62*64:63*64]))


if __name__ == '__main__':
    unittest.main()
