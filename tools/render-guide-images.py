#!/usr/bin/env python3
"""Render exact bootstrap documentation views without added labels."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from golden_board.raster import write_binary_png


def render(output: Path):
    artifact = (ROOT / 'artifacts/GOLDEN-BOARD.bin').read_bytes()
    identity = json.loads((ROOT / 'artifacts/manifest.json').read_bytes())['forms']['bin']
    if len(artifact) != identity['bytes'] or hashlib.sha256(artifact).hexdigest() != identity['sha256']:
        raise ValueError('Canonical artifact identity mismatch.')
    # Only the carried 2048-by-64 bootstrap strip is needed. Black means one.
    strip = bytes((byte >> bit) & 1 for byte in artifact[:16384] for bit in range(7, -1, -1))
    output.mkdir(parents=True, exist_ok=False)
    write_binary_png(output / 'bootstrap-strip.png', 2048, 64, strip, scale=8)
    width, height = 276, 140
    for group in range(4):
        canvas = bytearray(width * height)
        for local in range(8):
            panel = group * 8 + local
            left, top = 4 + (local % 4) * 68, 4 + (local // 4) * 68
            for row in range(64):
                source = row * 2048 + panel * 64
                target = (top + row) * width + left
                canvas[target:target + 64] = strip[source:source + 64]
        name = f'bootstrap-{group * 8 + 1:02d}-{group * 8 + 8:02d}.png'
        write_binary_png(output / name, width, height, canvas, scale=4)

    # README crops show the same exact cells, without guide margins.
    full = bytes((byte >> bit) & 1 for byte in artifact[:32768] for bit in range(7,-1,-1))
    first = b''.join(full[row*2048:row*2048+256] for row in range(64))
    fragment = b''.join(full[row*2048:row*2048+512] for row in range(128))
    write_binary_png(output/'bootstrap-first-frames.png',256,64,first,scale=2)
    write_binary_png(output/'golden-board-fragment.png',512,128,fragment)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='A new output directory')
    args = parser.parse_args()
    try:
        render(args.output)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
