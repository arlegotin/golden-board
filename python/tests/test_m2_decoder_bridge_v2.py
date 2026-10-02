"""Protocol failure cannot become evidence or contaminate a later observation."""
import sys
import unittest

from golden_board.m2_decoder_bridge_v2 import RevisionBatchDecoder, BridgeV2Error


CHILD = r'''
from pathlib import Path
from hashlib import sha256
import sys
from golden_board import canonical_manifest as m
from golden_board.m2_decoder_v2 import ObservationDecoderV2
decoder=ObservationDecoderV2(*((Path('spec')/name).read_bytes() for name in (
    'profile-policy-v2.toml','profile-limits-v2.toml','damage-policy-v2.toml')))
mode=sys.argv[1]
while True:
    header=sys.stdin.buffer.read(5)
    if not header:break
    if len(header)!=5:sys.exit(2)
    size=int.from_bytes(header[1:],'big')
    wire=sys.stdin.buffer.read(size)
    if len(wire)!=size:sys.exit(2)
    channel={1:'OBS_BITS',2:'OBS_MATRIX',3:'OBS_UNITS'}[header[0]]
    result=decoder.decode(channel,wire)
    raw=decoder.render_result(channel,result)
    side=m.validate_canonical_manifest(decoder.render_resources())
    if mode=='observation':side['observation_sha256']='0'*64
    if mode=='result':side['result_sha256']='0'*64
    if mode=='owner':side['source_owners']['spec/resource-accounting-v2.md']='0'*64
    if mode=='resource':side['resource']['primitive_steps']+=1
    if mode=='channel':side['channel']='OBS_MATRIX' if channel!='OBS_MATRIX' else 'OBS_UNITS'
    if mode=='schema':
        value=m.validate_canonical_manifest(raw)
        value['schema']='golden-board.m2-damage-decoder-result/v1'
        raw=m.serialize_manifest(value)
        side['result_sha256']=sha256(raw).hexdigest()
    if mode=='incomplete':
        value=m.validate_canonical_manifest(raw)
        raw=m.serialize_manifest({key:value[key] for key in ('schema','channel','resource')})
        side['result_sha256']=sha256(raw).hexdigest()
    if mode=='noncanonical':raw=b' '+raw
    if mode=='stall':
        import time
        time.sleep(60)
    if mode=='empty':
        sys.stdout.buffer.write(bytes(4));sys.stdout.buffer.flush();continue
    sys.stdout.buffer.write(len(raw).to_bytes(4,'big')+raw)
    if mode=='oversized':
        sys.stdout.buffer.write((1048577).to_bytes(4,'big'));sys.stdout.buffer.flush();continue
    side=m.serialize_manifest(side)
    if mode=='truncated':
        sys.stdout.buffer.write(len(side).to_bytes(4,'big')+side[:3]);sys.stdout.buffer.flush();sys.exit(0)
    sys.stdout.buffer.write(len(side).to_bytes(4,'big')+side);sys.stdout.buffer.flush()
'''


class DecoderBridgeV2(unittest.TestCase):
    def child(self, mode='ok',timeout=5):
        return RevisionBatchDecoder((sys.executable,'-c',CHILD,mode),timeout_seconds=timeout)

    def test_persistent_frames_preserve_exact_pairs_and_observation_identity(self):
        from hashlib import sha256
        from golden_board import canonical_manifest
        with self.child() as client:
            for channel,wire in (('OBS_UNITS',bytes(4)),('OBS_BITS',b''),('OBS_MATRIX',bytes(2))):
                pair=client.decode(channel,wire)
                result=canonical_manifest.validate_canonical_manifest(pair.result_raw)
                side=canonical_manifest.validate_canonical_manifest(pair.resources_raw)
                self.assertEqual(result['channel'],channel)
                self.assertEqual(result['schema'],'golden-board.m2-damage-decoder-result/v2')
                self.assertEqual(side['observation_sha256'],sha256(wire).hexdigest())
                self.assertEqual(side['result_sha256'],sha256(pair.result_raw).hexdigest())
                self.assertEqual(result['resource'],side['resource'])

    def test_bad_request_writes_nothing_and_process_can_still_serve_a_valid_frame(self):
        with self.child() as client:
            for channel,wire in (([],b''),('BITS',b''),('OBS_BITS',bytearray()),
                                 ('OBS_BITS',bytes(4194307))):
                with self.subTest(channel=channel),self.assertRaises(BridgeV2Error):
                    client.decode(channel,wire)
            client.decode('OBS_UNITS',bytes(4))

    def test_invalid_response_aborts_without_reusing_desynchronized_stream(self):
        for mode in ('empty','oversized','truncated','noncanonical','schema',
                     'channel','observation','result','owner','resource','incomplete'):
            with self.subTest(mode=mode),self.child(mode) as client:
                with self.assertRaises(BridgeV2Error):client.decode('OBS_UNITS',bytes(4))
                self.assertIsNotNone(client._process.poll())
                with self.assertRaises(BridgeV2Error):client.decode('OBS_UNITS',bytes(4))

    def test_timeout_aborts_the_child(self):
        with self.child('stall',timeout=1) as client:
            with self.assertRaises(BridgeV2Error):client.decode('OBS_UNITS',bytes(4))
            self.assertIsNotNone(client._process.poll())

    def test_write_deadline_bounds_a_child_that_never_reads_a_large_frame(self):
        from time import monotonic
        # The finite sleeper makes the regression itself bounded even before
        # the fix; a blocking pipe writer incorrectly waits its full lifetime.
        with RevisionBatchDecoder((sys.executable,'-c','import time; time.sleep(3)'),
                                  timeout_seconds=1) as client:
            start=monotonic()
            with self.assertRaises(BridgeV2Error):client.decode('OBS_BITS',bytes(4194306))
            self.assertLess(monotonic()-start,2.5)
            self.assertIsNotNone(client._process.poll())


if __name__=='__main__':unittest.main()
