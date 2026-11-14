"""The public CLI exposes reproducible tools and preserves existing output."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def run_gb(self, *args):
        return subprocess.run([str(ROOT/'gb'), *map(str,args)], cwd=ROOT, capture_output=True, text=True)

    def test_help_has_no_retired_trial_or_explorer_commands(self):
        run = self.run_gb('--help')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn('explorer', run.stdout)
        self.assertNotIn('trial', run.stdout)
        self.assertIn('inspect', run.stdout)
        for command in ('trial', 'explorer'):
            self.assertNotEqual(self.run_gb(command).returncode, 0)

    def test_inspect_extracts_exact_bodies_and_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'documents'
            run = self.run_gb('inspect', '--output', output)
            self.assertEqual(run.returncode, 0, run.stderr)
            report = json.loads(run.stdout)
            self.assertEqual(report['documents']['2']['entries'], list(range(324,388)))
            from golden_board.artifacts import sha
            expected = json.loads((ROOT/'artifacts/manifest.json').read_text())['documents']
            for ident, row in expected.items():
                self.assertEqual(sha((output/f'{ident}.bin').read_bytes()), row['sha256'])
            marker = output/'owner-file'; marker.write_text('preserve')
            self.assertNotEqual(self.run_gb('inspect','--output',output).returncode,0)
            self.assertEqual(marker.read_text(),'preserve')

    def test_unsupported_check_area_fails(self):
        self.assertNotEqual(self.run_gb('check','focused','protocol').returncode,0)
        self.assertNotEqual(self.run_gb('check','fast','source').returncode,0)


if __name__ == '__main__':
    unittest.main()
