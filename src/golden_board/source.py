"""Exact-byte acquisition inventory. Strict game import belongs to S4."""
import hashlib
import json
from pathlib import Path
import re


def source_spans(root: Path) -> dict:
    lock_path = root / 'inputs/lock.json'
    if not lock_path.is_file():
        raise ValueError('Missing inputs/lock.json; restore the retained source lock.')
    lock = json.loads(lock_path.read_text())
    path = root / lock['path']
    if not path.is_file():
        raise ValueError('Missing inputs/anthology.pgn; restore the exact owner-supplied PGN.')
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != lock['sha256'] or len(data) != lock['bytes']:
        raise ValueError(f'{lock["path"]}: identity mismatch; expected '
                         f'{lock["sha256"]} ({lock["bytes"]} bytes), observed '
                         f'{digest} ({len(data)} bytes). Restore the source; do not relock silently.')
    try:
        data.decode('utf-8')
    except UnicodeDecodeError as error:
        raise ValueError(f'{path}: invalid UTF-8 at byte {error.start}') from error
    starts = [match.start() for match in re.finditer(br'(?m)^\[Event ', data)]
    if not starts or starts[0] != 0:
        raise ValueError(f'{path}: expected the owner source to start with an Event tag.')
    records = [{'ordinal': ordinal, 'start': start, 'end': end,
                'sha256': hashlib.sha256(data[start:end]).hexdigest()}
               for ordinal, (start, end) in enumerate(zip(starts, starts[1:] + [len(data)]), 1)]
    if len(records) != lock['expected_records']:
        raise ValueError(f'Expected {lock["expected_records"]} source records; found {len(records)}.')
    return {'scope': 'identity and boundary inventory; contents unqualified',
            'path': lock['path'], 'sha256': digest, 'bytes': len(data),
            'record_count': len(records), 'records': records}


def verify_source(root: Path) -> dict:
    inventory = source_spans(root)
    data = (root / inventory['path']).read_bytes()
    for record in inventory['records']:
        ordinal, start, end = record['ordinal'], record['start'], record['end']
        span = data[start:end]
        parts = re.split(br'\r?\n[ \t]*\r?\n', span, maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f'Source record {ordinal}, byte {start}: missing header boundary.')
        tags = {}
        for line in parts[0].splitlines():
            match = re.fullmatch(br'\[([A-Za-z0-9_]+) "((?:[^"\\]|\\["\\])*)"\]', line)
            if not match or match[1] in tags:
                raise ValueError(f'Source record {ordinal}, byte {start}: malformed/duplicate tag.')
            tags[match[1]] = match[2]
        marker = re.search(br'(1-0|0-1|1/2-1/2|\*)\s*\Z', parts[1])
        if not marker or marker[1] == b'*' or tags.get(b'Result') != marker[1]:
            raise ValueError(f'Source record {ordinal}, byte {start}: mismatched/unfinished result.')
        record.update(tags=[name.decode('ascii') for name in tags], result=marker[1].decode('ascii'))
    inventory['scope'] = 'acquisition inventory; legality unqualified'
    return inventory
