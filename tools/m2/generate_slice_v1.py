#!/usr/bin/env python3
"""Reproduce the revised logical slice and private review evidence offline."""
import argparse
import base64
import json
from pathlib import Path

from golden_board.m2_slice_v1 import compile_slice_v1
from tools.m2.learner_compile import compile_pages, reference_transcript, slice_declaration
from tools.m2.learner_content import build_cases

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-declaration', action='store_true')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    sources = tuple((ROOT / path).read_bytes() for path in (
        'studies/m2/slice-v0.json', 'conformance/content-v0.json',
        'conformance/chess-v0.json', 'reports/game-set-v0.bin',
        'spec/content-v0.md', 'spec/constants-v0.toml', 'spec/curriculum-v0.toml'))
    pages = build_cases(ROOT)
    raw, owner = compile_pages(pages)
    declaration = slice_declaration(raw, sources[0])
    compiled = compile_slice_v1(declaration, *sources)
    path = ROOT / 'studies/m2/slice-v1.json'
    if args.write_declaration:
        path.write_bytes(declaration)
    elif path.read_bytes() != declaration:
        raise ValueError('tracked declaration differs from reviewed source authoring')
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    (output / 'required.content-v0.bin').write_bytes(compiled.required_content_bytes)
    (output / 'all.content-v0.bin').write_bytes(compiled.content_bytes)
    for name, value in (('owner.json', owner), ('pages.json', pages),
                        ('reference-transcript.json', reference_transcript(raw, owner))):
        (output / name).write_text(json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n')
    metadata = dict(schema='golden-board.learner-prototype-data/v0',
        content_base64=base64.b64encode(raw).decode(), content_bytes=len(raw),
        content_sha256=owner['content_sha256'], root_id=owner['root_id'])
    (output / 'lesson-data.js').write_text('globalThis.LESSON_DATA = ' +
        json.dumps(metadata, sort_keys=True, separators=(',', ':')) + ';\n')
    print(json.dumps(dict(pages=len(pages), required_bytes=len(raw),
        required_sha256=compiled.required_content_sha256, all_bytes=len(compiled.content_bytes),
        all_sha256=compiled.content_sha256, sections=len(compiled.atomic_assignments)), sort_keys=True))


if __name__ == '__main__':
    main()
