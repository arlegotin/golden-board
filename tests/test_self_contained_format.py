"""Current message carries structure, not development revision labels."""
import hashlib
from pathlib import Path
import unittest
from golden_board.document import decode_document, encode_document
from golden_board.clean_carrier import encode_section, decode_section, inventory_for

ROOT = Path(__file__).resolve().parents[1]
MINI = bytes.fromhex((ROOT/'spec/vectors/current-mini.hex').read_text())


class SelfContainedTests(unittest.TestCase):
    def test_literal_document_and_section(self):
        document = decode_document(MINI)
        self.assertEqual(len(MINI), 326)
        self.assertEqual(MINI[:6].hex(), 'd6390002000f')
        self.assertEqual(encode_document(document['entries'], list(document['records'].values())), MINI)
        literal = bytes.fromhex('000100000002aabbbec1ff10')
        self.assertEqual(encode_section(1, 1, b'\xaa\xbb'), literal)
        self.assertEqual(decode_section(literal)['payload'], b'\xaa\xbb')
        self.assertEqual(inventory_for({1:MINI})[:2], b'\0\1')

    def test_only_pinned_legacy_inputs_convert(self):
        from golden_board.qualified_inputs import current_document
        legacy = (ROOT/'evidence/S03-shared-anthology/actual-document.bin').read_bytes()
        converted = current_document(legacy, 'anthology')
        self.assertEqual(converted, legacy[:2]+legacy[3:])
        decode_document(converted)
        for changed in (legacy+b'\0', b'\0'+legacy[1:]):
            with self.assertRaisesRegex(ValueError, 'identity'):
                current_document(changed, 'anthology')
        with self.assertRaises(ValueError):
            current_document(legacy, 'foundation')

    def test_pruning_preserves_all_actual_glyph_uses(self):
        from golden_board.message_cleanup import clean_document
        document = decode_document(MINI)
        unused = dict(document['records'][0], id=99)
        body = encode_document(document['entries'], [*document['records'].values(), unused])
        actual, report = clean_document(body)
        self.assertEqual(actual, MINI)
        self.assertEqual(report['unused_glyph_ids'], [99])
        self.assertEqual(report['removed_sha_tables'], [])

    def test_old_header_and_corruption_are_rejected(self):
        legacy = bytes.fromhex((ROOT/'spec/vectors/S02-mini.hex').read_text())
        with self.assertRaises(ValueError): decode_document(legacy)
        literal = bytes.fromhex('000100000002aabbbec1ff10')
        for value in (literal[:5], literal[:-1], literal+b'\0', literal[:6]+b'\0'+literal[7:]):
            with self.assertRaises(ValueError): decode_section(value)
