#!/usr/bin/env python3
"""Decode one bounded development observation without candidate/source inputs."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

from golden_board import canonical_manifest
from golden_board.m2_decoder import OBS_BITS, OBS_MATRIX, OBS_UNITS
from golden_board.m2_decoder_v2 import ObservationDecoderV2

ROOT = Path(__file__).resolve().parents[2]


def _read_regular(path, maximum):
    fd = os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise ValueError('observation must be a bounded regular file')
        raw = source.read(maximum+1)
    if len(raw) > maximum:
        raise ValueError('observation grew past its bound')
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel',choices=(OBS_BITS,OBS_MATRIX,OBS_UNITS),required=True)
    parser.add_argument('--observation',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args = parser.parse_args()
    raw = _read_regular(args.observation,4194306)
    owners = tuple((ROOT/'spec'/name).read_bytes() for name in
                   ('profile-policy-v2.toml','profile-limits-v2.toml','damage-policy-v2.toml'))
    decoder = ObservationDecoderV2(*owners)
    result = decoder.decode(args.channel,raw)
    rejection = decoder.last_rejection
    output = {'decoder-result.json':decoder.render_result(args.channel,result),
              'decoder-resources.json':decoder.render_resources()}
    for name,value in (('required.content-v0.bin',result.m2_required_stream),
                       ('all.content-v0.bin',result.m2_all_stream)):
        if value is not None:
            output[name] = value
    execution = dict(schema='golden-board.m2-observation-development/v2',status='development-only',
        channel=args.channel,observation_sha256=sha256(raw).hexdigest(),decoder_rejection=rejection,
        owner_sha256=[sha256(value).hexdigest() for value in owners],
        files=[dict(path=name,bytes=len(value),sha256=sha256(value).hexdigest())
               for name,value in sorted(output.items())])
    output['execution.json'] = canonical_manifest.serialize_manifest(execution)
    destination = args.output_dir.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('output directory already exists')
    destination.parent.mkdir(parents=True,exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.receiver-v2-',dir=destination.parent))
    try:
        for name,value in sorted(output.items()):
            path = stage/name
            path.write_bytes(value)
            path.chmod(0o600)
        if destination.exists() or destination.is_symlink():
            raise ValueError('output directory appeared during decoding')
        stage.rename(destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print(json.dumps(dict(status='development-only',artifact_state=result.artifact_state,
                          channel=args.channel,files=len(output)),sort_keys=True))


if __name__ == '__main__':
    main()
