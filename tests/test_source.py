"""Risk: using changed source bytes or treating inventory as legality."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from golden_board.source import verify_source

ROOT = Path(__file__).resolve().parents[1]


class SourceTests(unittest.TestCase):
    def test_owner_source_has_64_contiguous_raw_spans(self):
        report = verify_source(ROOT)
        self.assertEqual(report['record_count'], 64)
        self.assertEqual(report['bytes'], 51491)
        self.assertEqual(report['records'][0]['start'], 0)
        self.assertEqual(report['records'][-1]['end'], 51491)
        self.assertEqual(report['records'][0]['result'], '1-0')
        self.assertEqual(report['records'][-1]['result'], '0-1')
        self.assertEqual(report['scope'], 'acquisition inventory; legality unqualified')
        for left, right in zip(report['records'], report['records'][1:]):
            self.assertEqual(left['end'], right['start'])

    def test_changed_source_rejected_without_relocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'inputs', root / 'inputs',
                            ignore=shutil.ignore_patterns('dependencies'))
            lock = (root / 'inputs/lock.json').read_bytes()
            with (root / 'inputs/anthology.pgn').open('ab') as stream:
                stream.write(b'\n')
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                verify_source(root)
            self.assertEqual((root / 'inputs/lock.json').read_bytes(), lock)

    def test_missing_source_identifies_required_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'inputs').mkdir()
            shutil.copy2(ROOT / 'inputs/lock.json', root / 'inputs/lock.json')
            with self.assertRaisesRegex(ValueError, 'inputs/anthology.pgn'):
                verify_source(root)


if __name__ == '__main__':
    unittest.main()
