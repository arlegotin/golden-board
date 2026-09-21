"""Real command output is capped and failed parents cannot strand the reader."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, call, patch

from tools.m2 import verify_gate8_v2 as coordinator


ROOT = Path(__file__).resolve().parents[2]


class CommandExecutionV2(unittest.TestCase):
    def test_exited_unreaped_direct_child_is_reaped_before_group_cleanup(self):
        child = subprocess.Popen([sys.executable, '-c', 'import os;os._exit(0)'],
                                 start_new_session=True)
        try:
            deadline = time.monotonic() + 3
            while True:
                if all(hasattr(os, name) for name in ('waitid', 'P_PID', 'WEXITED', 'WNOWAIT')):
                    status = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
                    exited = status is not None
                else:
                    # Darwin lacks waitid on some Python builds. Inspect kernel
                    # state without Popen.poll/wait, which would reap the child.
                    status = subprocess.run(['ps', '-o', 'stat=', '-p', str(child.pid)],
                        capture_output=True, text=True, timeout=1, check=False)
                    exited = status.returncode == 0 and status.stdout.strip().startswith('Z')
                if exited:
                    break
                self.assertLess(time.monotonic(), deadline, 'child did not reach unreaped exit state')
                time.sleep(.01)
            self.assertIsNone(child.returncode)
            coordinator._stop({'exited': child})
            self.assertEqual(child.returncode, 0)
            with self.assertRaises(ChildProcessError):
                os.waitpid(child.pid, os.WNOHANG)
            with self.assertRaises(ProcessLookupError):
                os.killpg(child.pid, 0)
        finally:
            if child.poll() is None:
                child.kill()
            child.wait()

    def test_persistent_permission_denial_for_live_group_rejects(self):
        child = Mock(pid=12345, stdin=None)
        child.poll.return_value = None
        denied = PermissionError(1, 'fixture denied live process group')
        with patch.object(coordinator.os, 'killpg', side_effect=denied) as killpg, \
             patch.object(coordinator.time, 'monotonic', side_effect=(0, 3, 4, 6)):
            with self.assertRaises(PermissionError) as caught:
                coordinator._stop({'live': child})
        self.assertIs(caught.exception, denied)
        self.assertEqual(killpg.call_args_list, [call(child.pid, signal.SIGTERM),
                                               call(child.pid, signal.SIGKILL)])
        child.wait.assert_not_called()

    def test_diagnostic_overflow_never_retains_more_than_the_storage_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory).resolve()
            command = [sys.executable,'-c',
                'import os\nfor _ in range(257):os.write(1,b"x"*65536)']
            with self.assertRaisesRegex(ValueError,'command-log-bound'):
                coordinator.run_checked_v2(command,work,'overflow')
            path = work/'overflow.log'
            self.assertEqual(path.stat().st_size,16777216)
            with path.open('rb') as stream:
                self.assertEqual(stream.read(8),b'xxxxxxxx')
                stream.seek(-8,2)
                self.assertEqual(stream.read(8),b'xxxxxxxx')

    def test_failed_command_reaps_descendant_that_retains_stdout(self):
        harness = r'''
import sys
from pathlib import Path
from tools.m2.verify_gate8_v2 import run_checked_v2
child = r"""
import os,subprocess,sys
from pathlib import Path
Path(sys.argv[1]).write_text(str(os.getpid()))
subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])
sys.exit(2)
"""
work=Path(sys.argv[1])
try:
    run_checked_v2([sys.executable,'-c',child,str(work/'producer.pid')],work,'failed')
except ValueError as error:
    print(str(error))
else:
    raise AssertionError('failed command returned success')
'''
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory).resolve()
            environment = dict(os.environ,PYTHONPATH=str(ROOT/'python')+os.pathsep+str(ROOT))
            process = subprocess.Popen([sys.executable,'-B','-c',harness,str(work)],cwd=ROOT,
                env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            timed_out = False
            try:
                try:stdout,stderr = process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    process.send_signal(signal.SIGTERM)
                    stdout,stderr = process.communicate(timeout=4)
                self.assertFalse(timed_out,'failed parent waited for a descendant stdout EOF')
                self.assertEqual(process.returncode,0,stderr.decode(errors='replace'))
                self.assertEqual(stdout,b'gate8-coordinator-v2:command-exit:failed:2\n')
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
                marker = work/'producer.pid'
                if marker.exists():
                    try:os.killpg(int(marker.read_text()),signal.SIGKILL)
                    except ProcessLookupError:pass
                process.stdout.close();process.stderr.close()


if __name__ == '__main__':unittest.main()
