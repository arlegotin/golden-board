"""Closed current-source projection with exact exclusions and bounded reads."""
import copy
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from golden_board import canonical_manifest as manifest
from golden_board import m2_source_v2 as source
from golden_board.m2_gate8_policy_v2 import load_gate8_policy_v2

ROOT=Path(__file__).resolve().parents[2]


class SourceV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.policy=load_gate8_policy_v2((ROOT/'spec/gate8-policy-v2.toml').read_bytes())

    def repository(self,root):
        subprocess.run(('git','init','-q',str(root)),check=True)
        (root/'docs').mkdir();(root/'reports').mkdir()
        (root/'docs/roadmap.md').write_bytes(b'# Roadmap\n| Project state | In progress |\n'
            b'| Current milestone | M2 |\n## 13. Project status\nmutable\n'
            b'## 14. Adversarial stress matrix\nnormative\n')
        (root/'docs/decisions.md').write_bytes(b'notes')
        (root/'reports/m2-feasibility-v0.json').write_bytes(b'old')
        (root/'reports/m2-feasibility-v2.json').write_bytes(b'new')
        (root/'.gitignore').write_bytes(b'ignored/\n')
        (root/'plain').write_bytes(b'plain')
        (root/'empty').touch()
        (root/'run').write_bytes(b'run');(root/'run').chmod(0o755)

    def test_exact_current_files_modes_and_normative_roadmap(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.repository(root)
            first=source.build_source_projection_v2(root,self.policy)
            value=source.admit_source_projection_v2(first,self.policy)
            self.assertEqual([row['path'] for row in value['entries']],['.gitignore','empty','plain','run'])
            self.assertEqual(value['entries'][-1]['mode'],'100755')
            (root/'docs/decisions.md').write_bytes(b'new note')
            roadmap=root/'docs/roadmap.md'
            roadmap.write_bytes(roadmap.read_bytes().replace(b'mutable',b'another status'))
            self.assertEqual(first,source.build_source_projection_v2(root,self.policy))
            roadmap.write_bytes(roadmap.read_bytes().replace(b'normative',b'changed owner'))
            self.assertNotEqual(first,source.build_source_projection_v2(root,self.policy))
            (root/'visible-result.json').write_bytes(b'result')
            self.assertIn('visible-result.json',[row['path'] for row in source.admit_source_projection_v2(
                source.build_source_projection_v2(root,self.policy),self.policy)['entries']])

    def test_links_oversized_files_and_ignored_roadmap_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.repository(root)
            path=root/'unsafe';path.symlink_to('plain')
            with self.assertRaises(ValueError):source.build_source_projection_v2(root,self.policy)
            path.unlink();os.link(root/'plain',path)
            with self.assertRaises(ValueError):source.build_source_projection_v2(root,self.policy)
            path.unlink()
            with path.open('wb') as stream:stream.truncate(8388609)
            with self.assertRaises(ValueError):source.build_source_projection_v2(root,self.policy)
            path.unlink();(root/'.gitignore').write_bytes(b'docs/roadmap.md\n')
            with self.assertRaises(ValueError):source.build_source_projection_v2(root,self.policy)

    def test_rebound_wrong_shape_order_types_exclusions_and_bounds_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.repository(root)
            value=source.admit_source_projection_v2(source.build_source_projection_v2(root,self.policy),self.policy)
            for change in (lambda v:v.update(schema='m2-evidence-source-v0'),
                lambda v:v['entries'].reverse(),lambda v:v['entries'][0].update(byte_length=True),
                lambda v:v['entries'][0].update(path='../escape'),
                lambda v:v['entries'][0].update(path='docs/roadmap.md'),
                lambda v:v['entries'][0].update(byte_length=8388609),
                lambda v:v['entries'][0].update(mode='100600'),lambda v:v.update(extra=0)):
                changed=copy.deepcopy(value);change(changed)
                with self.assertRaises(ValueError):source.admit_source_projection_v2(
                    manifest.serialize_manifest(changed),self.policy)

    def test_worktree_git_file_is_not_an_ordinary_production_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'.git').write_bytes(b'gitdir: /missing\n')
            with self.assertRaises(ValueError):source.build_source_projection_v2(root,self.policy)

    def test_external_git_environment_cannot_select_another_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.repository(root)
            expected=source.build_source_projection_v2(root,self.policy)
            with patch.dict(os.environ,{'GIT_DIR':'/no-such-source-repository',
                'GIT_WORK_TREE':'/no-such-source-tree','GIT_INDEX_FILE':'/no-such-source-index',
                'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'core.fsmonitor','GIT_CONFIG_VALUE_0':'/no-hook'}):
                self.assertEqual(source.build_source_projection_v2(root,self.policy),expected)


if __name__=='__main__':unittest.main()
