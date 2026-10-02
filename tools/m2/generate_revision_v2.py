#!/usr/bin/env python3
"""Build a private development carrier and verify its physical content bridge.

This produces no Gate-8 receipt, Candidate-ready report, roadmap promotion or
qualifying participant bundle. Full revision lifecycle integration is separate.
"""

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile

from golden_board import curriculum, m2_policy
from golden_board.m2_carrier_v2 import build_development_carrier, recover_clean_matrix
from golden_board.m2_slice import compile_slice_v0
from golden_board.m2_slice_v1 import compile_slice_v1
from golden_board.m2_teaching_recipe_v2 import build_teaching_recipe_package
from tools.m2.package_learner_v1 import archive_bytes, build_files

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATHS = ('studies/m2/slice-v0.json', 'conformance/content-v0.json',
                'conformance/chess-v0.json', 'reports/game-set-v0.bin',
                'spec/content-v0.md', 'spec/constants-v0.toml', 'spec/curriculum-v0.toml')


def _read(root, path):
    with (root/path).open('rb') as stream:
        raw = stream.read(2097153)
    if len(raw) > 2097152:
        raise ValueError('source-size:' + path)
    return raw


def generate(root=ROOT):
    sources = tuple(_read(root, path) for path in SOURCE_PATHS)
    declaration = _read(root, 'studies/m2/slice-v1.json')
    legacy = compile_slice_v0(*sources)
    compiled = compile_slice_v1(declaration, *sources)
    blueprint = curriculum.load_blueprint(sources[-1])
    policy = m2_policy.load_profile_policy(_read(root, 'spec/profile-policy-v0.toml')).capacity_policy
    image = build_development_carrier(compiled, legacy, blueprint, policy)
    plan = image.capacity_plan
    recovered = recover_clean_matrix(image.carrier, plan.width)
    if (recovered.required_bytes, recovered.all_bytes) != (
            compiled.required_content_bytes, compiled.content_bytes):
        raise ValueError('physical-content-bridge-mismatch')
    # Bind the development viewer preview to recovered bytes, not a direct
    # compiler handoff. The package helper independently checks its source.
    learner = archive_bytes(build_files(recovered.required_bytes, root))
    files = {'carrier.bin': image.carrier,
             'required.content-v0.bin': recovered.required_bytes,
             'all.content-v0.bin': recovered.all_bytes,
             'recipe-package.bin': build_teaching_recipe_package(),
             'learner-preview.zip': learner}
    files.update((f'route-{i}.bin', raw) for i, raw in enumerate(image.route_prefixes))
    report = {
        'schema': 'golden-board.m2-revision-development/v2',
        'status': 'development-only',
        'claims': ['source-built-carrier', 'clean-matrix-content-roundtrip',
                   'viewer-preview-bound-to-recovered-required-stream'],
        'pending': ['independent-full-carrier-reproduction', 'knowledge-use-and-ablation',
                    'complete-limits-and-damage-gates', 'archive-first-lifecycle-transition',
                    'fresh-native-and-linux-gate8', 'release', 'fresh-human-bridges'],
        'profile': 'eh72-hier-r5-r2-r1-lzss-crc32c-v1',
        'side': plan.side, 'shell_width': plan.width,
        'physical_units': plan.units, 'fixed_pad_cells': plan.pad_cells,
        'owner_cell_counts': list(image.owner_cell_counts),
        'route_prefix_bytes': [len(raw) for raw in image.route_prefixes],
        'headroom_cells': list(plan.headroom_cells),
        'future_authoring_payload_bytes': plan.authoring_bytes,
        'uncompressed_reserve_payload_bytes': plan.reserve_bytes,
        'sections': [{k:v for k,v in asdict(s).items() if k != 'payload'} |
                     {'payload_bytes': len(s.payload), 'payload_sha256': sha256(s.payload).hexdigest(),
                      'fragments': s.fragments} for s in plan.sections],
        'checked_section_ids': list(recovered.checked_section_ids),
        'geometry_search': [list(row) for row in plan.search_rows],
        'slice_source_sha256': sha256(declaration).hexdigest(),
        # The report is deliberately excluded from its own preimage.
        'files': [{'path': name, 'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}
                  for name, raw in sorted(files.items())],
    }
    files['development-report.json'] = (json.dumps(report, sort_keys=True, separators=(',', ':'))+'\n').encode()
    return files, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('output path must be new')
    files, report = generate()
    stage = Path(tempfile.mkdtemp(prefix='.revision-v2-', dir=output.parent))
    try:
        for name, raw in sorted(files.items()):
            with (stage/name).open('xb') as stream:
                stream.write(raw)
        # Rename only into a still-absent destination; this is development
        # output, never a canonical report/tree replacement.
        if output.exists() or output.is_symlink():
            raise ValueError('output appeared during generation')
        os.rename(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print(json.dumps({key: report[key] for key in (
        'status', 'side', 'shell_width', 'physical_units', 'route_prefix_bytes')}, sort_keys=True))


if __name__ == '__main__':
    main()
