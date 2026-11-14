"""Piece masks preserve identities, content and canonical unused bits."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from golden_board.course_author import CourseAuthor
from golden_board.document import decode_document, encode_document
from golden_board.piece_glyphs import apply_piece_glyphs


# Independent literal masks in piece-ID order:
# pawn, knight, bishop, rook, queen, king.
EXPECTED = (
    ('00000','00100','00100','00100','00000'),
    ('00000','00110','00100','01100','00000'),
    ('00000','00100','00100','01110','00000'),
    ('00000','01010','01010','01110','00000'),
    ('00000','01010','00100','01110','00000'),
    ('00000','00100','01010','01110','00000'),
)


def fixture(use_pieces=True):
    author=CourseAuthor()
    cells=list(range(32,44)) if use_pieces else [0]
    trace=author.trace([cells,cells[::-1]],rows=1,cols=len(cells))
    return author.encode([trace])


class PieceGlyphTests(unittest.TestCase):
    def test_exact_masks_role_order_and_complement_padding(self):
        doc=decode_document(apply_piece_glyphs(fixture()))
        masks=[]
        for kind,rows in enumerate(EXPECTED):
            expected=[int(v) for v in ''.join(rows)]
            for side in range(2):
                record=doc['records'][32+kind+6*side]
                self.assertEqual((record['kind'],record['rows'],record['cols']),(1,5,5))
                bits=[(v>>s)&1 for v in record['mask'] for s in range(7,-1,-1)]
                self.assertEqual(bits[:25],[b^side for b in expected])
                self.assertEqual(bits[25:],[0]*7)
                masks.append(tuple(record['mask']))
        self.assertEqual(len(set(masks)),12)
        self.assertNotEqual(doc['records'][33]['mask'],doc['records'][34]['mask'])

    def test_only_piece_masks_change_same_size_and_idempotent(self):
        before=fixture();after=apply_piece_glyphs(before)
        old,new=decode_document(before),decode_document(after)
        self.assertEqual(len(before),len(after))
        self.assertEqual(old['entries'],new['entries'])
        self.assertEqual(set(old['records']),set(new['records']))
        for ident,record in old['records'].items():
            expected=deepcopy(new['records'][ident])
            if 32<=ident<=43:
                self.assertNotEqual(record['mask'],expected['mask'])
                expected['mask']=record['mask']
            self.assertEqual(record,expected)
        self.assertEqual(apply_piece_glyphs(after),after)

    def test_incomplete_wrong_kind_or_wrong_dimensions_refused(self):
        for change in ('missing','kind','dimensions'):
            doc=decode_document(fixture(False))
            if change=='missing':del doc['records'][32]
            elif change=='kind':doc['records'][32]={'kind':5,'id':32,'rows':1,'cols':1,'values':[1]}
            else:doc['records'][32].update(rows=1,cols=1,mask=[128])
            raw=encode_document(doc['entries'],list(doc['records'].values()))
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'piece glyph'):
                apply_piece_glyphs(raw)

    def test_palette_metadata_identifies_public_masks(self):
        import hashlib
        from golden_board import piece_glyphs
        document = decode_document(apply_piece_glyphs(fixture()))
        masks = b''.join(bytes(document['records'][ident]['mask']) for ident in range(32, 44))
        self.assertIsNotNone(getattr(piece_glyphs, 'PALETTE_SHA256', None))
        self.assertEqual(piece_glyphs.PALETTE_SHA256, hashlib.sha256(masks).hexdigest())
        self.assertEqual(piece_glyphs.REVISION, 'inverted-5x5-v1')

    def test_unknown_build_style_refused_before_creating_output(self):
        from golden_board.clean_build import build_clean
        with tempfile.TemporaryDirectory() as tmp:
            destination=Path(tmp)/'new'
            with self.assertRaisesRegex(ValueError,'glyph style'):
                build_clean(Path(__file__).resolve().parents[1],destination,piece_glyph_style='unknown')
            self.assertFalse(destination.exists())


if __name__=='__main__':unittest.main()
