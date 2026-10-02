"""Real subprocess protocol failures cannot release or strand a peer."""
from pathlib import Path
import os
import sys
import tempfile
import unittest

from golden_board.m2_gate8_policy_v2 import load_gate8_policy_v2
from tools.m2 import generate_gate8_v2 as producer
from tools.m2 import verify_gate8_v2 as coordinator

ROOT=Path(__file__).resolve().parents[2]


class PairExecutionV2(unittest.TestCase):
    def setUp(self):
        self.policy=load_gate8_policy_v2((ROOT/'spec/gate8-policy-v2.toml').read_bytes())
        self.ready={identifier:producer.render_ready_v2(self.policy,identifier,'a'*64,
            tuple((path,b'x') for path in producer.core_paths(self.policy)))
            for identifier in ('native-python','native-rust')}

    def run_children(self,root,scripts,check,timeout=5):
        commands={name:[sys.executable,'-B','-c',script] for name,script in scripts.items()}
        return coordinator.execute_pair_v2(commands,root,self.policy,'a'*64,
            dict(os.environ),check,root/'logs',preflight_timeout=timeout)

    def script(self,name,marker,tail=''):
        return ('import pathlib,sys,time\n'
            +f'sys.stdout.buffer.write({self.ready[name]!r});sys.stdout.buffer.flush()\n'
            +'release=sys.stdin.buffer.read()\n'
            +'assert release\n'
            +f'pathlib.Path({str(marker)!r}).write_bytes(release)\n'+tail)

    def test_both_actual_readiness_records_are_checked_before_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();markers={k:root/k for k in self.ready}
            def check(values):
                self.assertEqual(set(values),set(self.ready))
                self.assertFalse(any(p.exists() for p in markers.values()))
            values=self.run_children(root,{k:self.script(k,markers[k]) for k in self.ready},check)
            for k,path in markers.items():
                producer.admit_release_v2(path.read_bytes(),values[k])

    def test_failed_preimage_comparison_releases_neither_producer(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();markers={k:root/k for k in self.ready}
            def reject(_):raise ValueError('different actual cores')
            with self.assertRaisesRegex(ValueError,'different actual cores'):
                self.run_children(root,{k:self.script(k,markers[k]) for k in self.ready},reject)
            self.assertFalse(any(p.exists() for p in markers.values()))

    def test_extra_stdout_and_failure_exit_reject_and_reap_peer(self):
        for tail in ('sys.stdout.write("extra");sys.stdout.flush()\n','sys.exit(2)\n'):
            with self.subTest(tail=tail),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve()
                scripts={'native-python':self.script('native-python',root/'one',tail),
                    'native-rust':self.script('native-rust',root/'two','time.sleep(30)\n')}
                with self.assertRaises(ValueError):self.run_children(root,scripts,lambda _:None)

    def test_readiness_bound_and_preflight_deadline_reject(self):
        for script in ('import sys;sys.stdout.write("x"*16385);sys.stdout.flush()',
                       'import time;time.sleep(30)'):
            with self.subTest(script=script),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve()
                scripts={'native-python':script,
                    'native-rust':self.script('native-rust',root/'peer','time.sleep(30)\n')}
                with self.assertRaises(ValueError):self.run_children(root,scripts,lambda _:None,timeout=.2)


if __name__=='__main__':unittest.main()
