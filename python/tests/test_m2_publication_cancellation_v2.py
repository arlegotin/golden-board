"""A signal after a successful rename must not outrun transaction ownership."""
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

from python.tests import test_m2_publication_v2 as fixtures
from tools.m2 import verify_gate8_v2 as coordinator


class PublicationCancellationV2(unittest.TestCase):
    def check_interrupt(self, point):
        with tempfile.TemporaryDirectory() as directory:
            fixture = fixtures.PublicationV2()
            root,stage,policy = fixture.fixture(Path(directory).resolve())
            target,name = ((coordinator.producer,'_rename_noreplace') if point == 'candidate'
                else (coordinator.os,'replace'))
            original = getattr(target,name)
            destination = (root/policy.document['authority']['candidate_root'] if point == 'candidate'
                else root/'docs/roadmap.md')
            previous = {number:signal.getsignal(number) for number in (signal.SIGINT,signal.SIGTERM)}
            signalled = False
            def interrupt_after_rename(source, actual_destination):
                nonlocal signalled
                original(source,actual_destination)
                if actual_destination == destination and not signalled:
                    signalled = True
                    os.kill(os.getpid(),signal.SIGINT)
            with patch.object(target,name,side_effect=interrupt_after_rename):
                with self.assertRaises((ValueError,KeyboardInterrupt)):
                    fixture.publish(root,stage,policy)
            self.assertTrue(signalled)
            self.assertEqual((root/'docs/roadmap.md').read_bytes(),b'pending\n')
            for key in ('candidate_root','gate8_root','report_path'):
                self.assertFalse((root/policy.document['authority'][key]).exists(),key)
            for number,handler in previous.items():
                self.assertEqual(signal.getsignal(number),handler)

    def test_candidate_rename_records_ownership_before_cancellation(self):
        self.check_interrupt('candidate')

    def test_status_replace_records_ownership_before_cancellation(self):
        self.check_interrupt('roadmap')


if __name__ == '__main__':unittest.main()
