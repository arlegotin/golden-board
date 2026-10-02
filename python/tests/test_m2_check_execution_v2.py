"""Root command dispatch uses simulated child commands, never real gate work."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]


class CheckExecutionV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='gb-check-v2-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        (self.root/'scripts').mkdir()
        shutil.copyfile(ROOT/'scripts/check',self.root/'scripts/check')
        (self.root/'docs').mkdir()
        self.roadmap=self.root/'docs/roadmap.md'
        self.roadmap.write_text('| Roadmap revision | 11 |\n')
        (self.root/'artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0/damage').mkdir(parents=True)
        self.bin=self.root/'bin';self.bin.mkdir()
        (self.root/'.venv/bin').mkdir(parents=True)
        self.log=self.root/'calls.jsonl'
        common='''import json,os,pathlib,sys
with open(os.environ['TEST_LOG'],'a') as f:f.write(json.dumps([pathlib.Path(sys.argv[0]).name,*sys.argv[1:]])+'\\n')
if os.environ.get('TEST_FAIL') and os.environ['TEST_FAIL'] in ' '.join(sys.argv[1:]):sys.exit(7)
'''
        bodies={
            'uv':"if sys.argv[1:]==['--version']:print('uv 0.11.29 (fixture)')\n",
            'rustc':"print('rustc 1.97.1 (fixture)')\n",
            'rustup':"if sys.argv[1]=='which':print(pathlib.Path(sys.argv[0]).parent/'rustc')\nelif sys.argv[-1]=='--version':print('cargo 1.97.1 (fixture)')\n",
            'git':"if sys.argv[1:]==['--version']:print('git version fixture')\n",
            'sh':'',
        }
        for name,body in bodies.items():
            path=self.bin/name;path.write_text('#!'+sys.executable+'\n'+common+body);path.chmod(0o755)
        path=self.root/'.venv/bin/python';path.write_text('#!'+sys.executable+'\n'+common);path.chmod(0o755)
        self.env={**os.environ,'PATH':str(self.bin)+os.pathsep+os.environ['PATH'],
                  'TEST_LOG':str(self.log),'PYTHONDONTWRITEBYTECODE':'1'}

    def run_check(self,*args,**env):
        return subprocess.run(['/bin/sh',str(self.root/'scripts/check'),*args],cwd=self.root,
            env={**self.env,**env},capture_output=True,text=True,timeout=20)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_components_are_non_gate8_checks_in_existing_order(self):
        result=self.run_check('components')
        self.assertEqual(result.returncode,0,result.stderr)
        stdout=result.stdout
        labels=['repo-shell','identity-python','chess-python','chess-oracle','source-python',
                'curriculum-python','content-python','transport-python','damage-python']
        self.assertEqual(sorted(labels,key=stdout.index),labels)
        joined='\n'.join(' '.join(c) for c in self.calls())
        self.assertNotIn('generate_candidates.py',joined)
        self.assertNotIn('generate_damage.py',joined)
        self.assertNotIn('generate_gate8.py',joined)
        self.assertNotIn('verify_gate8_v2.py',joined)
        self.assertNotIn('docker',joined)

    def test_v2_full_and_release_delegate_once_without_asserted_pass_flags(self):
        for mode in ('full','release'):
            with self.subTest(mode=mode):
                result=self.run_check(mode)
                self.assertEqual(result.returncode,0,result.stderr)
                coordinator=[c for c in self.calls() if 'tools/m2/verify_gate8_v2.py' in c]
                self.assertEqual(coordinator,[['python','tools/m2/verify_gate8_v2.py',mode]])
                self.assertNotIn('check: repo-shell',result.stdout)
                self.log.unlink()

    def test_partial_archive_dispatch_and_coordinator_failure_reject(self):
        self.roadmap.write_text('| Roadmap revision | 10 |\n')
        archive=self.root/'artifacts/history/m2-pre-participant-revision-v1'
        archive.parent.mkdir();archive.symlink_to(self.root/'missing')
        result=self.run_check('full',TEST_FAIL='verify_gate8_v2.py')
        self.assertNotEqual(result.returncode,0)
        self.assertIn(['python','tools/m2/verify_gate8_v2.py','full'],self.calls())
        self.assertFalse(any('tools/m2/generate_gate8.py' in c for c in self.calls()))

    def test_historical_focused_checks_stay_on_original_generators(self):
        self.roadmap.write_text('| Roadmap revision | 10 |\n')
        for area,old in (('transport','tools/m2/generate_candidates.py'),
                         ('damage','tools/m2/generate_damage.py')):
            with self.subTest(area=area):
                result=self.run_check('focused',area)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertTrue(any(old in c and '--check' in c for c in self.calls()))
                self.log.unlink()

    def test_historical_full_keeps_original_gate8_phase(self):
        self.roadmap.write_text('| Roadmap revision | 10 |\n')
        result=self.run_check('full')
        self.assertEqual(result.returncode,0,result.stderr)
        gate8=[c for c in self.calls() if 'tools/m2/generate_gate8.py' in c]
        self.assertEqual(len(gate8),1)
        self.assertEqual(gate8[0][1:6],['tools/m2/generate_gate8.py','phase-check',
            '--phase','pre-gate8-clean','--candidate-root'])
        self.assertFalse(any('tools/m2/verify_gate8_v2.py' in c for c in self.calls()))

    def test_components_stop_on_child_failure(self):
        result=self.run_check('components',TEST_FAIL='python.tests.test_chess_oracle')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('check: chess-oracle',result.stdout)
        self.assertNotIn('check: source-python',result.stdout)
        self.assertNotIn('check: transport-python',result.stdout)


if __name__=='__main__':unittest.main()
