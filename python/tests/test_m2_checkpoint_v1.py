"""Historical admission must preserve evidence without running producers."""
from contextlib import ExitStack
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.m2 import verify_gate8_v2 as coordinator

ROOT = Path(__file__).resolve().parents[2]


class CompletedCheckpointV1Tests(unittest.TestCase):
    def test_live_linux_requires_frozen_restoration_before_runtime_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            fake = Path(temp) / 'docker'
            fake.write_text('#!/bin/sh\nprintf "unexpected docker invocation\\n" >&2\nexit 1\n')
            fake.chmod(0o755)
            result = subprocess.run([str(ROOT / 'tools/linux/verify.sh')],
                env={**os.environ, 'PATH': temp + os.pathsep + os.environ['PATH']},
                capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('restore-checkpoint', result.stderr)
            self.assertNotIn('unexpected docker invocation', result.stderr)

    def test_live_source_cannot_reuse_completed_release(self):
        with patch.object(coordinator, 'run_checked_v2', side_effect=AssertionError('producer prerequisite invoked')):
            with self.assertRaisesRegex(ValueError, 'restore-checkpoint'):
                coordinator.workflow_v2('full')

    def test_completed_checkpoint_has_read_only_admission(self):
        self.assertTrue(callable(getattr(coordinator, 'admit_completed_m2_checkpoint_v1', None)),
                        'completed M2 needs explicit historical evidence admission')
        with ExitStack() as stack:
            for name in ('workflow_v2', 'execute_pair_v2', 'assemble_v2'):
                stack.enter_context(patch.object(coordinator, name, side_effect=AssertionError('producer invoked')))
            for name in ('produce', 'finish_candidate_v2', 'build_preflight_v2'):
                stack.enter_context(patch.object(coordinator.producer, name, side_effect=AssertionError('generation invoked')))
            value = coordinator.admit_completed_m2_checkpoint_v1(ROOT)
        self.assertEqual(value['source_commit'], '5d9254d2f6b755013d7d0b86ea7e935e8ee08257')

    def test_materialized_checkpoint_is_exact_and_missing_or_changed_evidence_rejects(self):
        self.assertTrue(callable(getattr(coordinator, 'materialize_completed_m2_checkpoint_v1', None)),
                        'completed M2 needs offline restoration')
        with tempfile.TemporaryDirectory(prefix='gb-checkpoint-test-') as temp:
            restored = coordinator.materialize_completed_m2_checkpoint_v1(ROOT, Path(temp).resolve() / 'checkpoint')
            self.assertTrue((restored / '.git').is_dir())
            # Original component tests consume ignored legacy Linux snapshots
            # and R1/R2 policy owners, as well as the final v2 evidence.
            import json
            archive_path = 'artifacts/history/m2-pre-participant-revision-v1'
            archive = json.loads((ROOT / archive_path / 'archive-manifest.json').read_bytes())
            prefixes = ('artifacts/linux/', 'artifacts/history/m2-r1-candidates/owners/',
                        'artifacts/history/m2-r2-candidates/owners/')
            for row in archive['files']:
                if row['path'].startswith(prefixes):
                    target = restored / row['path']
                    self.assertTrue(target.is_file(), row['path'])
                    self.assertEqual(target.read_bytes(), (ROOT / archive_path / row['archive_path']).read_bytes())
                    self.assertEqual(target.stat().st_mode & 0o777, int(row['mode'], 8))
            self.assertEqual((restored / 'docs/roadmap.md').read_bytes(),
                             __import__('subprocess').check_output(['git', '-C', str(ROOT), 'show',
                                 '5d9254d2f6b755013d7d0b86ea7e935e8ee08257:docs/roadmap.md']))
            # The descriptor is outside the original Git source inventory.
            descriptor = restored / 'studies/m2/checkpoint-v1.json'
            self.assertFalse(descriptor.exists())
            descriptor.write_bytes((ROOT / 'studies/m2/checkpoint-v1.json').read_bytes())
            (restored / 'docs/new-development-note.md').write_text('M3 authoring note\n')
            roadmap = restored / 'docs/roadmap.md'
            roadmap.write_bytes(roadmap.read_bytes().replace(b'| Roadmap revision | 11 |',
                                                           b'| Roadmap revision | 99 |')
                                .replace(b'| Current milestone | M3 ', b'| Current milestone | M4 '))
            self.assertEqual(coordinator.admit_completed_m2_checkpoint_v1(restored)['source_commit'],
                             '5d9254d2f6b755013d7d0b86ea7e935e8ee08257')
            report = restored / 'reports/m2-feasibility-v2.json'
            report.chmod(0o755)
            with self.assertRaises(ValueError):
                coordinator.admit_completed_m2_checkpoint_v1(restored)
            report.chmod(0o644)
            evidence = restored / 'artifacts/gate8/bundles/technical/recipient/01-clean/observation.bits'
            raw = evidence.read_bytes()
            evidence.write_bytes(raw + b'corrupt')
            with self.assertRaises(ValueError):
                coordinator.admit_completed_m2_checkpoint_v1(restored)
            evidence.write_bytes(raw)
            evidence.unlink()
            with self.assertRaises(ValueError):
                coordinator.admit_completed_m2_checkpoint_v1(restored)


if __name__ == '__main__':
    unittest.main()
