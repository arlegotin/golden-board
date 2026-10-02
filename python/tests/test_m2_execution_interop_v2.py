"""Execution admission binds actual files and environment before receipts."""
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from golden_board import canonical_manifest as manifest
from golden_board.m2_gate8_policy_v2 import load_gate8_policy_v2, result_file_paths_v2
from golden_board import m2_gate8_receipts_v2 as receipts
from tools.m2 import generate_gate8_v2 as producer
from tools.m2 import verify_gate8_v2 as coordinator

ROOT = Path(__file__).resolve().parents[2]


class ExecutionInteropV2(unittest.TestCase):
    def test_tree_rejects_mode_and_inode_switch_at_actual_read_boundary(self):
        for mutation in ('mode', 'inode'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                path = root / 'result.json'
                path.write_bytes(b'unchanged')
                path.chmod(0o644)
                original = producer.read_source_file_v2
                before_inode = path.stat().st_ino

                def switched(*args, **kwargs):
                    if mutation == 'mode':
                        path.chmod(0o755)
                    else:
                        replacement = root / 'replacement'
                        replacement.write_bytes(b'unchanged')
                        replacement.chmod(0o644)
                        os.replace(replacement, path)
                        self.assertNotEqual(path.stat().st_ino, before_inode)
                    return original(*args, **kwargs)

                with patch.object(producer, 'read_source_file_v2', side_effect=switched):
                    with self.assertRaises(ValueError):
                        producer.tree_rows(root, 1, 100, 100)

    def test_case_alias_of_work_inside_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            repository = base / 'SourceRepository'
            repository.mkdir(mode=0o700)
            work = repository / 'work'
            work.mkdir(mode=0o700)
            alias = base / 'sOURCErEPOSITORY' / 'work'
            if not alias.exists():
                self.skipTest('filesystem is case-sensitive')
            self.assertTrue(alias.samefile(work))
            self.assertFalse(alias.is_relative_to(repository))
            with self.assertRaises(ValueError):
                producer.admit_work_root(alias, repository, Path('/usr/bin/python3'))

    def test_postpublication_freeze_failure_removes_only_owned_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            observed = []

            def failed_freeze():
                observed.append((root / 'receipt.json').read_bytes())
                raise ValueError('source changed after installation')

            with self.assertRaisesRegex(ValueError, 'source changed after installation'):
                producer.atomic_last_file(root, 'receipt.json', b'owned\n', postcondition=failed_freeze)
            self.assertEqual(observed, [b'owned\n'])
            self.assertEqual(list(root.iterdir()), [])

            def replaced_during_freeze():
                replacement = root / 'replacement'
                replacement.write_bytes(b'foreign\n')
                replacement.chmod(0o644)
                os.replace(replacement, root / 'receipt.json')
                raise ValueError('receipt replaced during final freeze')

            with self.assertRaisesRegex(ValueError, 'receipt replaced during final freeze'):
                producer.atomic_last_file(root, 'receipt.json', b'owned\n',
                                          postcondition=replaced_during_freeze)
            self.assertEqual((root / 'receipt.json').read_bytes(), b'foreign\n')
            self.assertEqual([path.name for path in root.iterdir()], ['receipt.json'])

    def test_pair_binds_native_receipt_to_observed_platform(self):
        policy = load_gate8_policy_v2((ROOT / 'spec/gate8-policy-v2.toml').read_bytes())
        owner_raw = (ROOT / 'spec/gate8-policy-v2.toml').read_bytes()
        source = manifest.serialize_manifest(dict(schema='m2-evidence-source-v2',
            roadmap_normative_sha256='0' * 64, entries=[dict(path='spec/gate8-policy-v2.toml',
                mode='100644', byte_length=len(owner_raw), sha256=sha256(owner_raw).hexdigest())]))
        damage_paths = tuple(sorted(('resource-limits.json', 'damage/manifest.json',
            'damage/boundary-kats.json', *(f'damage/{family}/{name}.json'
                for family in ('D0', 'D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7', 'B0')
                for name in ('000000', 'manifest')))))
        # These are structural receipt fixtures. No synthetic file or result is
        # allowed to enter a real candidate producer in this admission test.
        rows = tuple(producer.file_row(path, b'x')
                     for path in result_file_paths_v2(policy, damage_paths))
        core_files = tuple((path, b'x') for path in producer.core_paths(policy))
        ready = {name: producer.admit_ready_v2(producer.render_ready_v2(policy, name,
                    sha256(source).hexdigest(), core_files), policy, name, sha256(source).hexdigest())
                 for name in ('native-python', 'native-rust')}
        identities = {language: dict(implementation=language, bytes=10,
                      sha256=sha256(language.encode()).hexdigest()) for language in ('python', 'rust')}
        observed = dict(kind='native', platform='darwin/arm64', image_id='none', acquisition_sha256='none')
        receipt_raw = {name: receipts.render_producer_receipt_v2(policy, source, name,
            identities[name.split('-')[1]], observed, rows, damage_paths) for name in ready}
        for wrong in (False, True):
            with self.subTest(wrong_platform=wrong), tempfile.TemporaryDirectory() as directory:
                base = Path(directory).resolve()
                work = base / 'work'
                work.mkdir(mode=0o700)
                executable = base / 'rust'
                executable.write_bytes(b'fixture')
                values = dict(receipt_raw)
                if wrong:
                    value = manifest.validate_canonical_manifest(values['native-python'])
                    value['environment_identity']['platform'] = 'unobserved-platform'
                    values['native-python'] = manifest.serialize_manifest(value)
                    # Shape admission deliberately accepts a native platform;
                    # the actual coordinator must bind it to this environment.
                    receipts.admit_producer_receipt_v2(values['native-python'], policy, source, damage_paths)

                def read(root, path, *args, **kwargs):
                    if path == 'spec/gate8-policy-v2.toml':
                        return owner_raw, {}
                    if path == 'source.json':
                        return source, {}
                    if path == 'receipt.json':
                        return values[root.name], {}
                    raise AssertionError('unexpected coordinator read: ' + path)

                def completed_pair(commands, cwd, actual_policy, source_hash, environment, check, logs):
                    self.assertEqual(set(commands), set(ready))
                    self.assertEqual(source_hash, sha256(source).hexdigest())
                    check(ready)
                    return ready

                def staged_rows(root, *bounds):
                    if root.name == 'preflight':
                        return tuple(ready[root.parent.name]['core_rows'])
                    self.assertEqual(root.name, 'candidate')
                    return rows

                with ExitStack() as stack:
                    stack.enter_context(patch.object(coordinator, 'ROOT', Path.cwd()))
                    stack.enter_context(patch.object(coordinator, 'build_source_projection_v2', return_value=source))
                    stack.enter_context(patch.object(coordinator, 'validate_source_projection_v2'))
                    stack.enter_context(patch.object(coordinator, 'read_source_file_v2', side_effect=read))
                    stack.enter_context(patch.object(coordinator, '_private_executable',
                                                    return_value=(executable, identities['rust'])))
                    stack.enter_context(patch.object(producer, 'executable_identity',
                                                    side_effect=lambda _, language: identities[language]))
                    stack.enter_context(patch.object(producer, 'tree_rows', side_effect=staged_rows))
                    stack.enter_context(patch.object(coordinator, '_bundle_preimages'))
                    stack.enter_context(patch.object(coordinator, 'execute_pair_v2', side_effect=completed_pair))
                    stack.enter_context(patch.object(producer.platform, 'system', return_value='Darwin'))
                    stack.enter_context(patch.object(producer.platform, 'machine', return_value='aarch64'))
                    self.assertEqual(producer.observed_environment_v2('native-python'), observed)
                    if wrong:
                        with self.assertRaisesRegex(ValueError, 'child-environment'):
                            coordinator.pair_v2('native', 1, executable, work)
                        self.assertFalse((work / 'receipts').exists())
                    else:
                        self.assertEqual(coordinator.pair_v2('native', 1, executable, work), values)
                        self.assertEqual((work / 'receipts/native-python.json').read_bytes(), values['native-python'])


if __name__ == '__main__':
    unittest.main()
