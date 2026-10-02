"""Producer handshake and private filesystem checks precede expensive work."""
from hashlib import sha256
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from golden_board import canonical_manifest as manifest
from golden_board.m2_gate8_policy_v2 import load_gate8_policy_v2
from tools.m2 import generate_gate8_v2 as execution

ROOT=Path(__file__).resolve().parents[2]


class ExecutionV2(unittest.TestCase):
    def setUp(self):
        self.policy=load_gate8_policy_v2((ROOT/'spec/gate8-policy-v2.toml').read_bytes())
        self.files=tuple((p,b'x') for p in self.policy.document['candidate_files']['fixed']
                         if p not in ('independence-proof.json','bundle-preimages.json'))
        self.ready_raw=execution.render_ready_v2(self.policy,'native-python','a'*64,self.files)
        self.ready=execution.admit_ready_v2(self.ready_raw,self.policy,'native-python','a'*64)

    def test_only_exact_own_source_and_core_release_is_accepted(self):
        release=execution.render_release_v2(self.ready)
        execution.admit_release_v2(release,self.ready)
        for mutate in (lambda v:v.update(source_projection_sha256='b'*64),
            lambda v:v.update(core_rows_sha256='c'*64),lambda v:v.update(extra=0)):
            value=manifest.validate_canonical_manifest(release);mutate(value)
            with self.assertRaises(ValueError):execution.admit_release_v2(manifest.serialize_manifest(value),self.ready)
        for invalid in (b'',release+b'\n',release+release,release.replace(b':',b': ',1)):
            with self.assertRaises(ValueError):execution.admit_release_v2(invalid,self.ready)

    def test_readiness_binds_every_core_file_and_exact_types(self):
        for mutate in (lambda v:v['core_rows'].pop(),lambda v:v['core_rows'].reverse(),
            lambda v:v['core_rows'][0].update(bytes=True),lambda v:v['core_rows'][0].update(mode='100755'),
            lambda v:v.update(producer_id='native-rust'),lambda v:v.update(extra=0)):
            value=manifest.validate_canonical_manifest(self.ready_raw);mutate(value)
            with self.assertRaises(ValueError):execution.admit_ready_v2(
                manifest.serialize_manifest(value),self.policy,'native-python','a'*64)

    def test_private_writer_has_closed_modes_and_no_overwrite_or_link_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();work=root/'work';work.mkdir(mode=0o700)
            execution.admit_work_root(work,ROOT,Path('/bin/sh'))
            execution.write_file(work,'a/b/value',b'first')
            rows=execution.tree_rows(work,10,1000,1000)
            self.assertEqual(rows,(dict(path='a/b/value',mode='100644',bytes=5,sha256=sha256(b'first').hexdigest()),))
            self.assertEqual((work/'a/b').stat().st_mode&0o777,0o700)
            with self.assertRaises(ValueError):execution.write_file(work,'a/b/value',b'other')
            self.assertEqual((work/'a/b/value').read_bytes(),b'first')
            (work/'alias').symlink_to('a',target_is_directory=True)
            with self.assertRaises(ValueError):execution.write_file(work,'alias/new',b'bad')
            with self.assertRaises(ValueError):execution.tree_rows(work,10,1000,1000)
            (work/'alias').unlink();os.link(work/'a/b/value',work/'hardlink')
            with self.assertRaises(ValueError):execution.tree_rows(work,10,1000,1000)

    def test_arguments_and_work_alias_reject_before_generation(self):
        for args in ([],['producer','--producer-id','native-rust','--workers','1','--work-root','/tmp/x'],
            ['producer','--producer-id','native-python','--workers','01','--work-root','/tmp/x']):
            with self.assertRaises(ValueError):execution.parse_arguments(args)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();repository=root/'repo';repository.mkdir()
            work=repository/'work';work.mkdir(mode=0o700)
            with self.assertRaises(ValueError):execution.admit_work_root(work,repository,Path('/bin/sh'))

    def test_nested_root_with_link_ancestor_cannot_be_read_or_written(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory).resolve();work=base/'work';external=base/'external'
            work.mkdir(mode=0o700);external.mkdir(mode=0o700)
            execution.write_file(external,'technical-v2/value',b'bound')
            (work/'bundles').symlink_to(external,target_is_directory=True)
            root=work/'bundles/technical-v2'
            with self.assertRaises(ValueError):execution.tree_rows(root,10,1000,1000)
            with self.assertRaises(ValueError):execution.write_file(root,'extra',b'bad')
            self.assertFalse((external/'technical-v2/extra').exists())

    def test_last_receipt_publication_rolls_back_only_its_own_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            with patch.object(execution,'fsync_directory',side_effect=OSError('fsync')):
                with self.assertRaises(OSError):execution.atomic_last_file(root,'receipt.json',b'new')
            self.assertEqual(list(root.iterdir()),[])
            execution.atomic_last_file(root,'receipt.json',b'old')
            with self.assertRaises(ValueError):execution.atomic_last_file(root,'receipt.json',b'new')
            self.assertEqual((root/'receipt.json').read_bytes(),b'old')
            self.assertEqual([p.name for p in root.iterdir()],['receipt.json'])


if __name__=='__main__':unittest.main()
