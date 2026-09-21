"""Shell orchestration only: external Docker/build/component jobs are simulated."""
from __future__ import annotations

import json
from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
H = 'a' * 64
S = 'b' * 64


class LinuxExecutionV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gb-linux-v2-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.repo = self.base / 'repo'
        (self.repo / 'tools/linux').mkdir(parents=True)
        (self.repo / 'artifacts/linux').mkdir(parents=True)
        (self.repo / '.git').mkdir()
        (self.repo / 'artifacts/linux/verifier-v0.env').write_bytes(b'image_id=sha256:' + b'c'*64 + b'\n')
        for name in ('verify-v2.sh', 'container-verify-v2.sh', 'image.env'):
            shutil.copyfile(ROOT / 'tools/linux' / name, self.repo / 'tools/linux' / name)
        self.output = self.base / 'output'
        self.native = self.base / 'native'
        for directory in (self.output, self.native):
            directory.mkdir(mode=0o700)
        for producer in ('native-python', 'native-rust'):
            receipt = self.native / (producer + '.json')
            receipt.write_bytes(b'{}\n')
            receipt.chmod(0o644)
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        self.log = self.base / 'calls.jsonl'
        self.write_tool('docker', '''import json,os,pathlib,sys
args=sys.argv[1:]
with open(os.environ['TEST_LOG'],'a') as f:f.write(json.dumps(args)+'\\n')
if os.environ.get('TEST_FAIL','') and os.environ['TEST_FAIL'] in ' '.join(args):sys.exit(17)
if 'linux-input' in args:print('b'*64)
elif 'digest' in args:print(('c' if os.environ.get('TEST_DRIFT') else 'a')*64)
elif any(x.endswith('/container-verify-v2.sh') for x in args):
 out=pathlib.Path(os.environ['GB_M2_GATE8_V2_OUTPUT'])
 for n in ('linux-python.json','linux-rust.json','verification.json'):(out/n).write_bytes(b'{}\\n')
''')
        self.env = dict(os.environ, PATH=str(self.bin)+os.pathsep+os.environ['PATH'],
            GB_M2_GATE8_V2_OUTPUT=str(self.output), GB_M2_GATE8_V2_NATIVE_RECEIPTS=str(self.native),
            TEST_LOG=str(self.log), PYTHONDONTWRITEBYTECODE='1')

    def write_tool(self, name, body):
        path = self.bin / name
        path.write_text('#!' + sys.executable + '\n' + body)
        path.chmod(0o755)

    def host(self, *arguments, **changes):
        return subprocess.run(['sh', str(self.repo/'tools/linux/verify-v2.sh'),
            *(arguments or (str(self.repo), H, 'sha256:'+'c'*64))], env={**self.env, **changes},
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_posix_syntax_and_strict_arguments(self):
        for name in ('verify-v2.sh', 'container-verify-v2.sh'):
            path = ROOT / 'tools/linux' / name
            subprocess.run(['sh', '-n', str(path)], check=True)
            result = subprocess.run(['sh', str(path)], capture_output=True)
            self.assertEqual(result.returncode, 2)
        self.assertNotEqual(self.host(str(self.repo), 'G'*64, 'sha256:'+'c'*64).returncode, 0)
        self.assertNotEqual(self.host(str(self.repo), H, 'sha256:'+'d'*64).returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_host_rejects_unsafe_paths_before_docker(self):
        for changes in ({'GB_M2_GATE8_V2_OUTPUT':'relative'},
                        {'GB_M2_GATE8_V2_NATIVE_RECEIPTS':''},
                        {'GB_M2_GATE8_V2_OUTPUT':str(self.native)},
                        {'GB_M2_GATE8_V2_OUTPUT':str(self.repo)}):
            with self.subTest(changes=changes):
                self.assertNotEqual(self.host(**changes).returncode, 0)
        self.output.chmod(0o755)
        self.assertNotEqual(self.host().returncode, 0)
        self.output.chmod(0o700)
        linked = self.base / 'linked'
        linked.symlink_to(self.output, target_is_directory=True)
        self.assertNotEqual(self.host(GB_M2_GATE8_V2_OUTPUT=str(linked)).returncode, 0)
        for producer in ('native-python', 'native-rust'):
            receipt = self.native / (producer + '.json')
            receipt.chmod(0o600)
            with self.subTest(producer=producer):
                self.assertNotEqual(self.host().returncode, 0)
            receipt.chmod(0o644)
        (self.native / 'extra').write_bytes(b'x')
        self.assertNotEqual(self.host().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_host_orders_admission_container_freeze_and_output_check(self):
        result = self.host()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        kinds = ['input' if 'linux-input' in a else 'container' if any(x.endswith('/container-verify-v2.sh') for x in a)
                 else 'snapshot' if 'digest' in a else 'output' for a in calls]
        self.assertEqual(kinds, ['input','container','snapshot','input','output'])
        for args in calls:
            self.assertIn('none', args)
            self.assertEqual(args[args.index('--network')+1], 'none')
        call = calls[1]
        mounts = [call[i+1] for i,x in enumerate(call[:-1]) if x == '--mount']
        self.assertIn(f'type=bind,source={self.repo},target=/input,readonly', mounts)
        self.assertIn(f'type=bind,source={self.native},target=/native-receipts,readonly', mounts)
        self.assertIn(f'type=bind,source={self.output},target=/gate8-output', mounts)
        self.assertFalse(any('candidate' in mount for mount in mounts))

    def test_host_short_circuits_failure_and_source_drift(self):
        self.assertNotEqual(self.host(TEST_FAIL='linux-input').returncode, 0)
        self.assertEqual(len(self.calls()), 1)
        self.log.unlink()
        self.assertNotEqual(self.host(TEST_FAIL='container-verify-v2.sh').returncode, 0)
        self.assertEqual(len(self.calls()), 2)
        self.log.unlink()
        self.assertNotEqual(self.host(TEST_DRIFT='1').returncode, 0)
        self.assertEqual(len(self.calls()), 3)


    def test_actual_transient_parser_rejects_tampering(self):
        # Execute the exact production here-document with fixture paths. This
        # tests retained byte admission, not fresh execution or producer gates.
        shell=(ROOT/'tools/linux/verify-v2.sh').read_text()
        code=shell.split("<<'PY'\n",1)[1].rsplit('\nPY\n',1)[0]
        def canonical(value):
            return json.dumps(value,sort_keys=True,separators=(',',':')).encode()+b'\n'
        receipts={p:canonical(dict(producer_id=p,source_projection_sha256=S))
                  for p in ('linux-python','linux-rust')}
        acquisition=self.repo/'artifacts/linux/verifier-v0.env'
        record=dict(schema='golden-board.m2-linux-verification/v2',source_projection_sha256=S,
            acquisition_sha256=sha256(acquisition.read_bytes()).hexdigest(),
            host_snapshot_sha256=H,container_snapshot_sha256=H,components='pass',pair='pass',
            linux_receipt_sha256={p:sha256(v).hexdigest() for p,v in receipts.items()})
        original={**{p+'.json':v for p,v in receipts.items()},'verification.json':canonical(record)}
        def reset():
            for p in self.output.iterdir():p.unlink()
            for name,raw in original.items():
                path=self.output/name;path.write_bytes(raw);path.chmod(0o644)
                # Reading may update atime; this is not a content mutation.
                os.utime(path,ns=(0,path.stat().st_mtime_ns))
        def check():
            return subprocess.run([sys.executable,'-c',code,S,H,str(self.output),str(acquisition)],
                capture_output=True,timeout=10).returncode
        reset();self.assertEqual(check(),0)
        for mutation in ('hash','extra-field','boolean','receipt','extra-file','mode','oversized'):
            with self.subTest(mutation=mutation):
                reset()
                changed=dict(record)
                if mutation=='hash':changed['container_snapshot_sha256']='f'*64
                elif mutation=='extra-field':changed['attestation']=True
                elif mutation=='boolean':changed['components']=True
                elif mutation=='receipt':
                    (self.output/'linux-rust.json').write_bytes(canonical(dict(
                        producer_id='linux-rust',source_projection_sha256='f'*64)))
                elif mutation=='extra-file':(self.output/'extra').write_bytes(b'x')
                elif mutation=='mode':(self.output/'linux-rust.json').chmod(0o600)
                elif mutation=='oversized':(self.output/'linux-rust.json').write_bytes(b'x'*1048577)
                if changed!=record:(self.output/'verification.json').write_bytes(canonical(changed))
                self.assertNotEqual(check(),0)

    def container_fixture(self):
        subprocess.run(['git', 'init', '--quiet', str(self.repo)],
                       check=True, capture_output=True)
        self.write_tool('uname', "import sys; print('Linux' if sys.argv[1]=='-s' else 'aarch64')\n")
        self.write_tool('python', r'''import json,os,pathlib,shutil,sys
args=sys.argv[1:]
def event(kind):
 with open(os.environ['TEST_LOG'],'a') as f:f.write(json.dumps([kind,*args])+'\n')
if args[0]=='-':
 code=sys.stdin.read()
 if len(args)==2:event('acquisition-check')
 else:
  event('export')
  out=pathlib.Path(args[2])
  for name in ('linux-python.json','linux-rust.json','verification.json'):(out/name).write_bytes(b'{}\n')
elif args[0].endswith('snapshot.py'):
 if args[1]=='materialize':
  event('materialize');shutil.copytree(args[2],args[3]);print('a'*64)
 else:
  event('snapshot')
  changed=os.environ.get('TEST_CONTAINER_DRIFT') and pathlib.Path(os.environ['TEST_MARKER']).exists()
  print(('c' if changed else 'a')*64)
elif args[0].endswith('verify_gate8_v2.py'):
 if args[1]=='linux-input':event('input');print('b'*64)
 elif args[1]=='pair':
  event('pair')
  assert args[2:7]==['--kind','linux','--workers','8','--rust-binary']
  binary=pathlib.Path(args[7]);assert binary.stat().st_mode&0o777==0o500
  assert args[8]=='--work-root' and args[10]=='--native-receipts'
  work=pathlib.Path(args[9]);assert not list(work.iterdir())
  pathlib.Path(os.environ['TEST_MARKER']).write_bytes(b'pair reached')
  if os.environ.get('TEST_CONTAINER_FAIL')=='pair':sys.exit(19)
 else:sys.exit(2)
else:sys.exit(2)
''')
        self.write_tool('uv', "import os,sys; args=sys.argv[1:]; i=args.index('python'); os.execvp('python',args[i:])\n")
        self.write_tool('rustup', r'''import json,os,pathlib,sys
with open(os.environ['TEST_LOG'],'a') as f:f.write(json.dumps(['build',*sys.argv[1:]])+'\n')
if os.environ.get('TEST_CONTAINER_FAIL')=='build':sys.exit(18)
p=pathlib.Path('target/release/gb-m2-gate8-v2');p.parent.mkdir(parents=True);p.write_bytes(b'fixture executable')
''')
        scripts=self.repo/'scripts';scripts.mkdir()
        check=scripts/'check'
        check.write_text('#!' + sys.executable + r'''
import json,os,pathlib,sys
assert sys.argv[1:]==['components']
assert pathlib.Path('artifacts/linux/verifier-v0.env').read_bytes()==b'image_id=sha256:'+b'c'*64+b'\n'
with open(os.environ['TEST_LOG'],'a') as f:f.write(json.dumps(['components'])+'\n')
if os.environ.get('TEST_CONTAINER_FAIL')=='components':sys.exit(16)
''')
        check.chmod(0o755)
        # Materialization excludes ignored provenance, just as the real snapshot
        # does. This fixture's copier strips that one file before copying.
        tool=self.bin/'python'
        tool.write_text(tool.read_text().replace("shutil.copytree(args[2],args[3]);print",
            "shutil.copytree(args[2],args[3]);(pathlib.Path(args[3])/'artifacts/linux/verifier-v0.env').unlink();print"))
        self.env.update(TMPDIR=str(self.base),TEST_MARKER=str(self.base/'pair-reached'))

    def container(self, **changes):
        return subprocess.run(['sh',str(self.repo/'tools/linux/container-verify-v2.sh'),
            str(self.repo),H,str(self.native),str(self.output),
            str(self.repo/'artifacts/linux/verifier-v0.env')],env={**self.env,**changes},
            text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)

    def test_container_orders_actual_commands_before_export(self):
        self.container_fixture()
        result=self.container()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual([a[0] for a in self.calls()],['input','materialize','snapshot',
            'acquisition-check','snapshot','components','build','pair','snapshot','snapshot','export'])
        self.assertEqual(sorted(p.name for p in self.output.iterdir()),
            ['linux-python.json','linux-rust.json','verification.json'])

    def test_container_components_preserve_exact_git_index_bytes(self):
        self.container_fixture()
        check = self.repo / 'scripts/check'
        check.write_text(check.read_text() + r'''
import subprocess
index = pathlib.Path('.git/index')
before = index.read_bytes()
for command in (['git', 'diff', '--check'], ['git', 'status', '--porcelain=v1']):
    subprocess.run(command, check=True, capture_output=True)
    assert index.read_bytes() == before, 'read-only Git command changed frozen index'
''')
        for command in (
            ['git', 'add', '.'],
            ['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
             'commit', '--quiet', '-m', 'fixture'],
        ):
            subprocess.run(command, cwd=self.repo, check=True, capture_output=True)
        original = (self.repo / '.git/index').read_bytes()
        result = self.container(GIT_OPTIONAL_LOCKS='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('components', [row[0] for row in self.calls()])
        self.assertEqual((self.repo / '.git/index').read_bytes(), original)

    def test_container_failure_or_drift_cannot_export(self):
        self.container_fixture()
        for failure in ('components','build','pair'):
            with self.subTest(failure=failure):
                result=self.container(TEST_CONTAINER_FAIL=failure)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(list(self.output.iterdir()),[])
                self.assertNotIn('export',[a[0] for a in self.calls()])
                self.log.unlink()
        result=self.container(TEST_CONTAINER_DRIFT='1')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(list(self.output.iterdir()),[])
        self.assertNotIn('export',[a[0] for a in self.calls()])


if __name__ == '__main__':
    unittest.main()
