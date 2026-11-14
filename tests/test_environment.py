"""Risk: offline setup secretly downloads or trusts corrupt archives."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from golden_board.environment import setup, verify_dependencies
from golden_board import environment

ROOT = Path(__file__).resolve().parents[1]


class EnvironmentTests(unittest.TestCase):
    def test_independent_reference_reads_retained_source_package(self):
        report = environment.reference_smoke(ROOT)
        self.assertEqual(report['e4_fen'],
                         'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1')

    def test_absent_dependency_fails_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'inputs/dependencies').mkdir(parents=True)
            shutil.copy2(ROOT / 'inputs/dependencies/lock.json',
                         root / 'inputs/dependencies/lock.json')
            with self.assertRaisesRegex(ValueError, 'Restore the locked archive'):
                verify_dependencies(root, acquire=False)

    def test_corrupt_dependency_is_not_replaced_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'inputs/dependencies', root / 'inputs/dependencies')
            package = root / 'inputs/dependencies/chess-1.11.2.tar.gz'
            package.write_bytes(b'broken')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                verify_dependencies(root, acquire=False)
            self.assertEqual(package.read_bytes(), b'broken')

    def test_fresh_environment_installs_from_retained_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'env'
            report = setup(ROOT, acquire=False, destination=destination)
            self.assertEqual(report['chess'], '1.11.2')
            result = subprocess.run([str(destination / 'bin/python'), '-c',
                                     'import chess; print(len(list(chess.Board().legal_moves)))'],
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), '20')


if __name__ == '__main__':
    unittest.main()
