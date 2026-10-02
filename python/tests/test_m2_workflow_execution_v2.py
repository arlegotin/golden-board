"""Coordinator scheduling with explicit fixtures, never full gate evidence.

The expensive source builder, producers, Linux job and assembler are stand-ins.
The workflow, private staging, retained-file reads and failure ordering are real.
"""
from contextlib import ExitStack, contextmanager
from io import StringIO
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from golden_board.m2_gate8_policy_v2 import load_gate8_policy_v2
from tools.m2 import verify_gate8_v2 as coordinator

ROOT = Path(__file__).resolve().parents[2]


class WorkflowExecutionV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gb-workflow-v2-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.policy_raw = (ROOT / 'spec/gate8-policy-v2.toml').read_bytes()
        self.policy = load_gate8_policy_v2(self.policy_raw)
        self.owner = self.policy.document
        self.source = b'explicit fixture source snapshot\n'
        self.report = b'explicit fixture report\n'
        self.receipts = {name: ('fixture receipt ' + name + '\n').encode()
                         for name in self.owner['producer_receipt']['producer_order']}
        self.attestation = b'explicit fixture Linux attestation\n'
        self.events = []
        self.published = False
        self.state = 'pending'
        self.component_failure = False
        self.change_during = None
        self.build_failure = False
        self.pair_failure = False
        self.linux_failure = False
        self.assembly_failure = False
        self.qualification_failure = False
        self.assembly_report = self.report
        self.write('spec/gate8-policy-v2.toml', self.policy_raw)
        self.write('source-marker', self.source)
        self.write(self.owner['authority']['report_path'], self.report)
        for name, raw in self.receipts.items():
            self.write(self.owner['producer_receipt']['path'].format(producer_id=name), raw)
        self.write(self.owner['linux']['attestation_path'], self.attestation)

    def write(self, path, raw):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)

    def test_release_build_overrides_ambient_rustc_with_pinned_compiler(self):
        expected=subprocess.check_output(['rustup','which','--toolchain','1.97.1','rustc'],
            text=True).strip()
        with patch.dict(os.environ,{'RUSTC':'/untrusted/ambient/rustc'}):
            environment=coordinator.rust_build_environment_v2()
        self.assertEqual(environment['RUSTC'],expected)
        self.assertEqual(environment['CARGO_INCREMENTAL'],'0')
        self.assertEqual(subprocess.check_output([environment['RUSTC'],'--version'],
            text=True).split()[1],'1.97.1')

    def mutate(self, phase):
        if self.change_during == phase:
            self.write('source-marker', b'changed fixture source\n')

    @contextmanager
    def fixture(self):
        real_mkdtemp = tempfile.mkdtemp
        real_run_checked = coordinator.run_checked_v2

        def initial(*_):
            self.events.append('source-snapshot')
            return (self.repo / 'source-marker').read_bytes()

        def freeze(raw, repository, policy):
            self.assertEqual(repository, self.repo)
            self.assertEqual(policy.document, self.owner)
            if raw != (self.repo / 'source-marker').read_bytes():
                raise ValueError('fixture-source-changed')

        def components(command, work, label):
            self.assertEqual(command, ['scripts/check', 'components'])
            self.assertEqual(label, 'components')
            self.events.append('components')
            if self.component_failure:
                # Actual nonzero child exit; no component checks are claimed.
                real_run_checked([sys.executable, '-c', 'raise SystemExit(7)'], work, label)
            self.mutate('components')

        def build(work):
            self.events.append('build')
            if self.build_failure:
                raise ValueError('fixture-build-failed')
            self.mutate('build')
            return work / 'fixture-rust-executable'

        def pair(kind, workers, binary, work):
            self.assertEqual((kind, workers), ('native', 8))
            self.assertEqual(binary, work.parent / 'fixture-rust-executable')
            self.events.append('native')
            if self.pair_failure:
                raise ValueError('fixture-native-failed')
            self.mutate('native')
            (work / 'source.json').write_bytes((self.repo / 'source-marker').read_bytes())
            return {name: self.receipts[name] for name in ('native-python', 'native-rust')}

        def linux(work, policy, source, native):
            self.assertEqual(source, self.source)
            self.assertEqual(native, {name: self.receipts[name] for name in ('native-python', 'native-rust')})
            self.events.append('linux')
            if self.linux_failure:
                raise ValueError('fixture-linux-failed')
            self.mutate('linux')
            return self.receipts, self.attestation

        def assemble(work, policy, source, receipts, attestation, before, mode):
            self.assertEqual((source, receipts, attestation), (self.source, self.receipts, self.attestation))
            self.assertEqual(before, b'fixture initial roadmap\n')
            self.assertEqual(list(work.iterdir()), [])
            self.events.append('assembly-' + mode)
            # This is the stand-in for the real assembler's own entry freeze.
            freeze(source, self.repo, policy)
            if self.assembly_failure:
                raise ValueError('fixture-assembly-failed')
            self.published = mode == 'generate'
            self.mutate('assembly')
            return self.assembly_report

        def state(*_):
            return ('ready' if self.published else self.state), b'fixture initial roadmap\n'

        def complete(root,policy,before,report,source):
            self.assertEqual((root,policy,before,report,source),
                (self.repo,self.policy,b'fixture initial roadmap\n',self.report,self.source))
            self.events.append('completion')
            self.state='complete'

        def qualify(*_):
            if self.qualification_failure:
                raise ValueError('fixture-qualification-failed')

        with ExitStack() as stack:
            replacements = {
                'ROOT': self.repo, 'admit_transition_v2': state,
                'build_source_projection_v2': initial, 'validate_source_projection_v2': freeze,
                'run_checked_v2': components, '_build_native_binary': build,
                'pair_v2': pair, '_linux_execution': linux, 'assemble_v2': assemble,
                'admit_release_qualification_v2': qualify,
                'publish_completion_v2': complete,
            }
            for name, value in replacements.items():
                stack.enter_context(patch.object(coordinator, name, value))
            stack.enter_context(patch.object(Path, 'cwd', return_value=self.repo))
            stack.enter_context(patch.object(tempfile, 'mkdtemp',
                side_effect=lambda **kwargs: real_mkdtemp(dir=self.base, **kwargs)))
            stack.enter_context(patch.object(sys, 'stderr', StringIO()))
            yield

    def test_actual_component_failure_prevents_build_native_linux_and_assembly(self):
        self.component_failure = True
        with self.fixture(), self.assertRaisesRegex(ValueError, 'command-exit:components:7'):
            coordinator.workflow_v2('bootstrap')
        self.assertEqual(self.events, ['source-snapshot', 'components'])
        self.assertFalse(self.published)

    def test_source_change_during_components_rejects_before_build(self):
        self.change_during = 'components'
        with self.fixture(), self.assertRaisesRegex(ValueError, 'fixture-source-changed'):
            coordinator.workflow_v2('bootstrap')
        self.assertEqual(self.events, ['source-snapshot', 'components'])
        self.assertFalse(self.published)

    def test_source_change_during_build_rejects_before_full_native_pair(self):
        self.change_during = 'build'
        with self.fixture(), self.assertRaises(ValueError):
            coordinator.workflow_v2('bootstrap')
        self.assertEqual(self.events, ['source-snapshot', 'components', 'build'])
        self.assertFalse(self.published)

    def test_stage_failures_do_not_enter_later_stage_or_publish(self):
        for flag, tail in (('build_failure', ['build']),
                           ('pair_failure', ['build', 'native']),
                           ('linux_failure', ['build', 'native', 'linux']),
                           ('assembly_failure', ['build', 'native', 'linux', 'assembly-generate'])):
            with self.subTest(flag=flag):
                self.events.clear()
                setattr(self, flag, True)
                with self.fixture(), self.assertRaisesRegex(ValueError, 'fixture-.*-failed'):
                    coordinator.workflow_v2('bootstrap')
                setattr(self, flag, False)
                self.assertEqual(self.events, ['source-snapshot', 'components', *tail])
                self.assertFalse(self.published)

    def test_bootstrap_full_and_release_have_exact_distinct_routing(self):
        for mode in ('bootstrap', 'full', 'release'):
            with self.subTest(mode=mode):
                self.events.clear()
                self.published = False
                self.state = 'pending' if mode == 'bootstrap' else 'ready'
                with self.fixture():
                    coordinator.workflow_v2(mode)
                expected = ['source-snapshot', 'components', 'build', 'native']
                if mode != 'full':
                    expected.append('linux')
                expected.append('assembly-generate' if mode == 'bootstrap' else 'assembly-check')
                if mode == 'release':expected.append('completion')
                self.assertEqual(self.events, expected)
                self.assertEqual(self.published, mode == 'bootstrap')

    def test_incorrect_authority_state_stops_before_any_stage(self):
        for mode, state in (('bootstrap', 'ready'), ('full', 'pending'), ('release', 'pending')):
            with self.subTest(mode=mode):
                self.state = state
                with self.fixture(), self.assertRaisesRegex(ValueError, 'workflow-state'):
                    coordinator.workflow_v2(mode)
                self.assertEqual(self.events, [])

    def test_release_rejects_unqualified_review_before_expensive_work(self):
        self.state='ready'
        self.qualification_failure=True
        with self.fixture(), self.assertRaisesRegex(ValueError,'fixture-qualification-failed'):
            coordinator.workflow_v2('release')
        self.assertEqual(self.events,[])

    def test_completed_release_is_read_only_and_repeatable(self):
        self.state='complete'
        with self.fixture():coordinator.workflow_v2('release')
        self.assertEqual(self.events,['source-snapshot','components','build','native',
            'linux','assembly-check'])
        self.assertEqual(self.state,'complete')

    def test_native_source_disagreement_prevents_linux_and_assembly(self):
        self.change_during = 'native'
        with self.fixture(), self.assertRaisesRegex(ValueError, 'workflow-source'):
            coordinator.workflow_v2('bootstrap')
        self.assertEqual(self.events, ['source-snapshot', 'components', 'build', 'native'])
        self.assertFalse(self.published)

    def test_ready_report_and_final_source_must_remain_exact(self):
        self.state = 'ready'
        self.assembly_report = b'changed fixture report\n'
        with self.fixture(), self.assertRaisesRegex(ValueError, 'release-report-changed'):
            coordinator.workflow_v2('full')
        self.assembly_report = self.report
        self.change_during = 'assembly'
        with self.fixture(), self.assertRaisesRegex(ValueError, 'fixture-source-changed'):
            coordinator.workflow_v2('full')
        self.assertFalse(self.published)

    def test_later_source_owned_pending_roadmap_is_not_mistaken_for_ready(self):
        from tools.m2 import reopen_participant_revision as transition
        tail = self.owner['lifecycle']['pre_ready_tail'].encode()
        archive = (b'| Roadmap revision | 11 |\n| Project state | In progress |\n'
            b'| Current milestone | M2 \xe2\x80\x94 Full-carrier bootstrap and transport feasibility |\n'
            b'Old normative text.\n## 13. Project status\n'
            b'| M2 \xe2\x80\x94 Full-carrier bootstrap and transport feasibility | In progress | '
            + tail + b' |\n## 14. Adversarial stress matrix\n')
        current = archive.replace(b'Old normative text.', b'Current frozen normative text.')
        archive_path = self.repo/'archive/pending/docs/roadmap.md'
        archive_path.parent.mkdir(parents=True)
        archive_path.write_bytes(archive)
        self.write('docs/roadmap.md', current)
        self.repo.joinpath(self.owner['authority']['report_path']).unlink()
        shutil.rmtree(self.repo/self.owner['authority']['gate8_root'])
        with patch.object(transition, 'ARCHIVE', 'archive'), patch.object(
                transition, '_load_package', return_value=None):
            self.assertEqual(coordinator.admit_transition_v2(self.repo,self.policy),('pending',current))


if __name__ == '__main__':
    unittest.main()
