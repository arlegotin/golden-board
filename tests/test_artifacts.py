"""The release forms must preserve every original bit, not merely look plausible."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ArtifactTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('golden_board.artifacts'),
                             'Canonical artifact verification is missing')
        from golden_board import artifacts
        return artifacts

    def test_original_forms_and_all_document_identities(self):
        report = self.api().verify_artifacts(ROOT)
        self.assertTrue(report['exact'])
        self.assertEqual(report['cells'], 4194304)
        self.assertEqual(report['documents'], json.loads((ROOT/'artifacts/manifest.json').read_text())['documents'])

    def test_each_inconsistent_form_is_refused(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT/'artifacts', root/'artifacts')
            for suffix in ('bin', 'txt', 'png'):
                path = root/f'artifacts/GOLDEN-BOARD.{suffix}'
                original = path.read_bytes()
                path.write_bytes(original[:-1])
                with self.subTest(form=suffix), self.assertRaises(ValueError):
                    api.verify_artifacts(root)
                path.write_bytes(original)

    def test_png_pixels_are_checked_independently_of_file_hash(self):
        api = self.api()
        from golden_board.clean_carrier import unpack_bits
        from golden_board.raster import write_binary_png
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'wrong.png'
            bits = bytearray(unpack_bits((ROOT/'artifacts/GOLDEN-BOARD.bin').read_bytes()))
            bits[123456] ^= 1
            write_binary_png(path, 2048, 2048, bits)
            self.assertNotEqual(api.png_packed(path.read_bytes()), (ROOT/'artifacts/GOLDEN-BOARD.bin').read_bytes())
            broken = bytearray(path.read_bytes()); broken[-1] ^= 1
            with self.assertRaises(ValueError): api.png_packed(bytes(broken))

    def test_documented_verify_entrypoint(self):
        run = subprocess.run([str(ROOT/'gb'), 'verify'], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(json.loads(run.stdout)['exact'])


if __name__ == '__main__':
    unittest.main()
