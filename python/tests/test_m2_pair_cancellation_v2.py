"""Cancellation reaps real producer groups, including the Popen return window."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
HARNESS = r'''
import json, os, signal, sys
from pathlib import Path
from golden_board.m2_gate8_policy_v2 import load_gate8_policy_v2
from tools.m2 import verify_gate8_v2 as coordinator

root, mode = Path(sys.argv[1]), sys.argv[2]
policy = load_gate8_policy_v2(Path('spec/gate8-policy-v2.toml').read_bytes())
previous = {s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
spawn = coordinator.subprocess.Popen
pids = []
def observed_spawn(*args, **kwargs):
    child = spawn(*args, **kwargs)
    pids.append(child.pid)
    (root/('pid-'+str(len(pids)))).write_text(str(child.pid))
    if mode == 'ownership-window' and len(pids) == 1:
        # The real child exists, but execute_pair has not yet recorded it.
        os.kill(os.getpid(), signal.SIGTERM)
    return child
coordinator.subprocess.Popen = observed_spawn
commands = {name:[sys.executable,'-c','import time;time.sleep(30)']
            for name in ('native-python','native-rust')}
try:
    coordinator.execute_pair_v2(commands,Path.cwd(),policy,'a'*64,dict(os.environ),
        lambda _:None,root/'logs',preflight_timeout=15)
except ValueError as error:
    if str(error) != 'gate8-coordinator-v2:pair-cancelled':
        raise
    assert all(signal.getsignal(s) == handler for s,handler in previous.items())
    print(json.dumps({'cancelled':True,'children':pids}))
else:
    raise AssertionError('cancelled pair returned success')
'''


class PairCancellationV2(unittest.TestCase):
    def check_cancellation(self, mode):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            environment = dict(os.environ, PYTHONPATH=str(ROOT/'python')+os.pathsep+str(ROOT))
            child = subprocess.Popen([sys.executable,'-B','-c',HARNESS,str(root),mode],
                cwd=ROOT,env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                start_new_session=True)
            try:
                if mode == 'waiting':
                    deadline = time.monotonic()+5
                    while not (root/'pid-2').exists() and child.poll() is None and time.monotonic()<deadline:
                        time.sleep(.01)
                    self.assertTrue((root/'pid-2').exists(), 'both real producers must start')
                    child.send_signal(signal.SIGTERM)
                stdout,stderr = child.communicate(timeout=6)
                self.assertEqual(child.returncode,0,stderr.decode(errors='replace'))
                value = json.loads(stdout)
                self.assertIs(value['cancelled'],True)
                self.assertTrue(value['children'])
                for pid in value['children']:
                    with self.assertRaises(ProcessLookupError):
                        os.kill(pid,0)
            finally:
                if child.poll() is None:
                    os.killpg(child.pid,signal.SIGKILL)
                    child.wait()
                for marker in root.glob('pid-*'):
                    try:os.killpg(int(marker.read_text()),signal.SIGKILL)
                    except ProcessLookupError:pass
                child.stdout.close();child.stderr.close()

    def test_sigterm_while_waiting_reaps_every_owned_producer(self):
        self.check_cancellation('waiting')

    def test_sigterm_between_spawn_and_registration_reaps_new_child(self):
        self.check_cancellation('ownership-window')


if __name__ == '__main__':unittest.main()
