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


def render(output: Path, *, source: Path | None = None, bootstrap='canonical'):
    canonical = (ROOT / 'artifacts/GOLDEN-BOARD.bin').read_bytes()
    identity = json.loads((ROOT / 'artifacts/manifest.json').read_bytes())['forms']['bin']
    if len(canonical) != identity['bytes'] or hashlib.sha256(canonical).hexdigest() != identity['sha256']:
        raise ValueError('Canonical artifact identity mismatch.')
    artifact = source.read_bytes() if source is not None else canonical
    if bootstrap == 'canonical':
        if artifact != canonical:
            raise ValueError('Canonical artifact identity mismatch.')
    elif bootstrap == 'field-boundaries':
        from golden_board import bootstrap_boundaries as candidate
        from golden_board.clean_carrier import decode_symbols, unpack_bits
        if source is None:
            raise ValueError('A candidate requires an explicit --source packed artifact.')
        decode_symbols(unpack_bits(artifact), bootstrap=candidate)
        if artifact[16384:] != canonical[16384:]:
            raise ValueError('The field-boundary candidate must preserve the frozen payload.')
    else:
        raise ValueError('Unknown bootstrap profile.')
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
    if bootstrap == 'field-boundaries':
        from golden_board.raw_draw import panel
        before = bytes((byte >> bit) & 1 for byte in canonical[:16384] for bit in range(7,-1,-1))
        for ordinal in candidate.CHANGED_PANELS:
            old = panel(before,ordinal-1,columns=32)
            new = panel(strip,ordinal-1,columns=32)
            canvas = bytearray(140*72)
            for left, cells in ((4,old),(72,new)):
                for row in range(64):
                    start = (4+row)*140+left
                    canvas[start:start+64] = cells[row*64:(row+1)*64]
            write_binary_png(output/f'bootstrap-{ordinal:02d}-comparison.png',140,72,canvas,scale=8)
        (output/'source.json').write_text(json.dumps({
            'bootstrap_layout':candidate.LAYOUT_REVISION,
            'sha256':hashlib.sha256(artifact).hexdigest(),
            'canonical_sha256':identity['sha256'],
            'canonical_payload_exact':True,
            'changed_panels':list(candidate.CHANGED_PANELS),
            'comparison_order':['canonical','candidate'],
            'scope':'Exact candidate cells; native conformance, no recipient trial.'
        },indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='A new output directory')
    parser.add_argument('--source', type=Path, help='Packed BIN/bitplane to render')
    parser.add_argument('--bootstrap', choices=('canonical','field-boundaries'), default='canonical')
    args = parser.parse_args()
    try:
        render(args.output, source=args.source, bootstrap=args.bootstrap)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
