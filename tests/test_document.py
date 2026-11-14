"""Risk: ambiguous framing, unchecked lengths/references, or mirrored codec bugs."""
import copy
import json
from pathlib import Path
import subprocess
import unittest

from golden_board.document import decode_document, encode_document

ROOT = Path(__file__).resolve().parents[1]
MINI = bytes.fromhex((ROOT / 'spec/vectors/current-mini.hex').read_text())


class DocumentTests(unittest.TestCase):
    def test_literal_mini_roundtrip_and_partial_update_data(self):
        doc = decode_document(MINI)
        self.assertEqual(doc['entries'], [512, 257])
        self.assertEqual(len(doc['records']), 15)
        self.assertEqual(doc['records'][256]['cells'], [0, 1, 1, 1, 0, 1])
        self.assertEqual(doc['records'][257]['steps'], [[[0, 1]], [[5, 0]]])
        self.assertEqual(doc['records'][512]['accepted'], [[10]])
        self.assertEqual(encode_document(doc['entries'], list(doc['records'].values())), MINI)

    def test_trailing_truncated_and_huge_lengths_rejected(self):
        for data in (MINI + b'\0', MINI[:2], MINI[:7], MINI[:23], MINI[:-1]):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                decode_document(data)
        huge = bytearray(MINI)
        huge[13:17] = b'\xff' * 4
        with self.assertRaisesRegex(ValueError, 'length|truncated'):
            decode_document(bytes(huge))

    def test_duplicate_id_and_unknown_kind_rejected(self):
        duplicate = bytearray(MINI)
        duplicate[21:23] = b'\0\0'
        with self.assertRaises(ValueError):
            decode_document(bytes(duplicate))
        unknown = bytearray(MINI)
        unknown[10] = 99
        with self.assertRaises(ValueError):
            decode_document(bytes(unknown))

    def test_mask_padding_is_not_silent_data(self):
        broken = bytearray(MINI)
        index = MINI.index(bytes.fromhex('02 03 d4')) + 2
        broken[index] |= 1
        with self.assertRaisesRegex(ValueError, 'padding'):
            decode_document(bytes(broken))

    def test_dangling_reference_and_out_of_range_updates_rejected(self):
        doc = decode_document(MINI)
        for ident, key, value in ((256, 'cells', [0, 1, 1, 1, 0, 90]),
                                  (257, 'steps', [[[6, 1]]]),
                                  (512, 'success', 333),
                                  (512, 'accepted', [[99]])):
            with self.subTest(key=key):
                records = copy.deepcopy(doc['records'])
                records[ident][key] = value
                with self.assertRaises(ValueError):
                    encode_document(doc['entries'], list(records.values()))

    def test_noncanonical_set_and_nonnumeric_values_rejected(self):
        doc = decode_document(MINI)
        for response in ([20, 10], [10, 10], [True]):
            with self.subTest(response=response):
                records = copy.deepcopy(doc['records'])
                records[512]['accepted'] = [response]
                with self.assertRaises(ValueError):
                    encode_document(doc['entries'], list(records.values()))

    def test_python_js_decoded_parity(self):
        result = subprocess.run(['node', '--input-type=module', '-e',
            "import {readFileSync} from 'node:fs'; import {decodeDocument} from './mechanism/player.mjs'; "
            "const h=readFileSync('spec/vectors/current-mini.hex','utf8').replace(/\\s/g,''); "
            "console.log(JSON.stringify(decodeDocument(Buffer.from(h,'hex'))));"],
            cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), json.loads(json.dumps(decode_document(MINI))))


if __name__ == '__main__':
    unittest.main()
