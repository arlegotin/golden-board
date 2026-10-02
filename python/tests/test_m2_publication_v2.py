"""Publication is authority-last and rolls back only newly installed evidence."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from golden_board.m2_gate8_policy_v2 import load_gate8_policy_v2
from tools.m2 import generate_gate8_v2 as producer
from tools.m2 import verify_gate8_v2 as coordinator

ROOT=Path(__file__).resolve().parents[2]


class PublicationV2(unittest.TestCase):
    def fixture(self,base):
        root=base/'repository';stage=base/'stage';root.mkdir(mode=0o700);stage.mkdir(mode=0o700)
        for path in ('artifacts/candidates','docs','reports'):(root/path).mkdir(parents=True,mode=0o700)
        producer.write_file(root,'docs/roadmap.md',b'pending\n')
        producer.write_file(stage,'candidate/value.json',b'candidate\n')
        producer.write_file(stage,'gate8/value.json',b'evidence\n')
        producer.write_file(stage,'report.json',b'report\n')
        producer.write_file(stage,'roadmap.md',b'ready\n')
        policy=load_gate8_policy_v2((ROOT/'spec/gate8-policy-v2.toml').read_bytes())
        return root,stage,policy

    def publish(self,root,stage,policy,mode='generate',freeze=lambda:None):
        return coordinator.publish_stage_v2(root,policy,stage,b'pending\n',b'ready\n',mode,freeze)

    def test_candidate_gate8_report_precede_roadmap_and_check_is_write_free(self):
        with tempfile.TemporaryDirectory() as directory:
            root,stage,policy=self.fixture(Path(directory).resolve());observed=[]
            original=coordinator.producer._rename_noreplace
            def rename(source,destination):
                self.assertEqual((root/'docs/roadmap.md').read_bytes(),b'pending\n')
                observed.append(destination.relative_to(root).as_posix());original(source,destination)
            with patch.object(coordinator.producer,'_rename_noreplace',side_effect=rename):
                self.publish(root,stage,policy)
            self.assertEqual(observed,[policy.document['authority'][key] for key in
                ('candidate_root','gate8_root','report_path')])
            before={p.relative_to(root):(p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
            self.publish(root,stage,policy,'check')
            self.assertEqual(before,{p.relative_to(root):(p.read_bytes(),p.stat().st_mtime_ns)
                for p in root.rglob('*') if p.is_file()})

    def test_status_fsync_failure_restores_before_and_preserves_identical_old_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root,stage,policy=self.fixture(Path(directory).resolve())
            candidate=root/policy.document['authority']['candidate_root'];candidate.mkdir(mode=0o700)
            producer.write_file(candidate,'value.json',b'candidate\n')
            inode=candidate.stat().st_ino;original=coordinator.producer.fsync_directory;failed=False
            def sync(path):
                nonlocal failed
                if path==root/'docs' and (root/'docs/roadmap.md').read_bytes()==b'ready\n' and not failed:
                    failed=True;raise OSError('status fsync')
                original(path)
            with patch.object(coordinator.producer,'fsync_directory',side_effect=sync):
                with self.assertRaisesRegex(OSError,'status fsync'):self.publish(root,stage,policy)
            self.assertEqual((root/'docs/roadmap.md').read_bytes(),b'pending\n')
            self.assertEqual(candidate.stat().st_ino,inode)
            self.assertFalse((root/policy.document['authority']['gate8_root']).exists())
            self.assertFalse((root/policy.document['authority']['report_path']).exists())

    def test_changed_candidate_or_source_prevents_any_publication(self):
        for changed in ('candidate','source'):
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as directory:
                root,stage,policy=self.fixture(Path(directory).resolve())
                if changed=='candidate':
                    candidate=root/policy.document['authority']['candidate_root'];candidate.mkdir(mode=0o700)
                    producer.write_file(candidate,'value.json',b'other\n')
                def freeze():
                    if changed=='source':raise ValueError('source changed')
                with self.assertRaises(ValueError):self.publish(root,stage,policy,freeze=freeze)
                self.assertEqual((root/'docs/roadmap.md').read_bytes(),b'pending\n')
                self.assertFalse((root/policy.document['authority']['gate8_root']).exists())
                self.assertFalse((root/policy.document['authority']['report_path']).exists())


if __name__=='__main__':unittest.main()
