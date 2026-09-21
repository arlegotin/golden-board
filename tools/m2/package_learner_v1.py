#!/usr/bin/env python3
"""Build an offline learner kit from exact checked required-stream bytes.

This packaging operation proves byte binding, not carrier recovery or a human
gate. Gate-8 integration must supply the recovered stream and its evidence.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

from golden_board.m2_runner_v1 import CONTENT_SHA256, m2_runner_v1

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / 'studies/m2/templates/learner/instructions-v1.txt').read_text()


def build_files(raw, root=ROOT):
    runner = m2_runner_v1(raw,label_suppressed=True)
    metadata = dict(schema='golden-board.learner-prototype-data/v0',
        content_base64=base64.b64encode(raw).decode(), content_bytes=len(raw),
        content_sha256=CONTENT_SHA256,
        root_id=runner.projection_view.root_record_id)
    files = {name:(root / 'tools/m2/learner_web' / name).read_bytes()
             for name in ('index.html', 'layout.js', 'ui.js', 'viewer.js')}
    files.update({'READ-ME.txt':(root / 'studies/m2/templates/learner/instructions-v1.txt').read_bytes(), 'lesson.content-v0.bin':raw,
        'lesson-data.js':('globalThis.LESSON_DATA = ' +
            json.dumps(metadata, sort_keys=True, separators=(',', ':')) + ';\n').encode()})
    files.update({name:(root/'tools/m2'/name).read_bytes()
                  for name in ('learner_runner.py','learner_runner_v1.py')})
    return dict(sorted(files.items()))


def archive_bytes(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo('golden-board-learner/' + name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--content', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    with args.content.open('rb') as source:
        raw = source.read(1048577)
    files = build_files(raw)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if any(args.output_dir.iterdir()):
        raise ValueError('output directory must be empty')
    for name, data in files.items():
        (args.output_dir / name).write_bytes(data)
    archive = archive_bytes(files)
    (args.output_dir / 'learner.zip').write_bytes(archive)
    print(json.dumps(dict(files=len(files), zip_bytes=len(archive),
                          zip_sha256=hashlib.sha256(archive).hexdigest()), sort_keys=True))


if __name__ == '__main__':
    main()
