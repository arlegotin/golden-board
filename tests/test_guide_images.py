"""Documentation views must add no black pixels outside exact canonical panels."""
import binascii
import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]


def pixels(path):
    data = path.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    width, height, depth, colour, compression, filtering, interlace = struct.unpack('>IIBBBBB', data[16:29])
    assert (depth, colour, compression, filtering, interlace) == (1, 0, 0, 0, 0)
    cursor, compressed = 8, bytearray()
    while cursor < len(data):
        size = int.from_bytes(data[cursor:cursor+4], 'big')
        kind = data[cursor+4:cursor+8]
        body = data[cursor+8:cursor+8+size]
        check = int.from_bytes(data[cursor+8+size:cursor+12+size], 'big')
        assert binascii.crc32(kind+body) & 0xffffffff == check
        if kind == b'IDAT': compressed.extend(body)
        cursor += size+12
    stride = (width+7)//8
    rows = zlib.decompress(compressed)
    assert len(rows) == height*(stride+1)
    black = bytearray()
    for row in range(height):
        assert rows[row*(stride+1)] == 0
        scanline = rows[row*(stride+1)+1:(row+1)*(stride+1)]
        black.extend(1-((scanline[i//8] >> (7-i%8)) & 1) for i in range(width))
    return width, height, black


class GuideImageTests(unittest.TestCase):
    def generate(self, output):
        return subprocess.run([sys.executable, str(ROOT/'tools/render-guide-images.py'),
                               '--output', str(output)], cwd=ROOT, capture_output=True, text=True)

    def test_all_panels_exact_and_no_extra_pixels_in_margins(self):
        artifact = (ROOT/'artifacts/GOLDEN-BOARD.bin').read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'views'
            run = self.generate(out)
            self.assertEqual(run.returncode, 0, run.stderr)
            for group in range(4):
                width, height, remainder = pixels(out/f'bootstrap-{group*8+1:02d}-{group*8+8:02d}.png')
                self.assertEqual((width, height), (1104, 560))
                for local in range(8):
                    ordinal = group*8+local
                    x, y = (4+68*(local%4))*4, (4+68*(local//4))*4
                    for row in range(64):
                        source = artifact[row*256+ordinal*8:row*256+ordinal*8+8]
                        expected = bytes((byte >> bit) & 1 for byte in source for bit in range(7,-1,-1) for _ in range(4))
                        for dy in range(4):
                            start = (y+row*4+dy)*width+x
                            self.assertEqual(remainder[start:start+256], expected)
                            remainder[start:start+256] = bytes(256)
                self.assertFalse(any(remainder), 'Guide-added ink outside the original panels')
            self.assertEqual((out/'bootstrap-strip.png').read_bytes(),
                             (ROOT/'docs/guide/images/bootstrap-clarity/bootstrap-strip.png').read_bytes())

    def test_checked_in_views_are_current_and_existing_outputs_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'views'
            run = self.generate(out)
            self.assertEqual(run.returncode, 0, run.stderr)
            before = {p.name: p.read_bytes() for p in out.iterdir()}
            self.assertEqual(len(before), 5)
            for name, data in before.items():
                self.assertEqual(data, (ROOT/'docs/guide/images/bootstrap-clarity'/name).read_bytes())
            self.assertNotEqual(self.generate(out).returncode, 0)
            self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})
        self.assertEqual(hashlib.sha256((ROOT/'artifacts/GOLDEN-BOARD.bin').read_bytes()).hexdigest(),
                         '0116be5b721d72b8aed5f67265b290a506c818354f9f297b0618768db996b479')
