"""Share inert game-document data in the existing numeric grammar."""
from copy import deepcopy
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

from .anthology import REPO
from .anthology_playback import validated_game_truth
from .authoring import audit_game, game_document, player_entry_packets
from .document import decode_document, encode_document


def _inert_key(record):
    if record['kind'] == 2:
        return (2, record['rows'], record['cols'], tuple(record['cells']),
                tuple(tuple(region) for region in record['regions']))
    return (5, record['rows'], record['cols'], tuple(record['values']))


def share_game_documents(documents: list[bytes]) -> bytes:
    """One distinct root per supplied game, with shared glyph/frame/table data.

    The caller supplies canonical content order. This does not select games or
    merge arbitrary page/graph documents; all subject truth is checked separately.
    """
    if not documents:
        raise ValueError('A shared anthology needs complete game documents.')
    decoded = [decode_document(data) for data in documents]
    glyphs = {}
    for document in decoded:
        records = document['records']
        if (len(document['entries']) != 1 or any(r['kind'] not in (1, 2, 3, 5) for r in records.values())
                or sum(r['kind'] == 3 for r in records.values()) != 1
                or sum(r['kind'] == 2 for r in records.values()) != 1):
            raise ValueError('Unsupported game-document topology.')
        trace = records[document['entries'][0]]
        if (trace['kind'] != 3 or len(trace['data']) != 2 or len(set(trace['data'])) != 2
                or set(trace['data']) != {r['id'] for r in records.values() if r['kind'] == 5}):
            raise ValueError('A game needs exactly its two complete referenced tables.')
        for record in records.values():
            if record['kind'] == 1:
                ident = record['id']
                if ident in glyphs and glyphs[ident] != record:
                    raise ValueError(f'Conflicting glyph definition {ident}.')
                glyphs[ident] = record
    result = [deepcopy(glyphs[ident]) for ident in sorted(glyphs)]
    next_id = 256  # Glyph namespace is exactly u8; other IDs have no subject meaning.
    interned, remaps = {}, []
    for document in decoded:
        remap = {}
        for ident, record in sorted(document['records'].items()):
            if record['kind'] not in (2, 5):
                continue
            key = _inert_key(record)
            if key not in interned:
                shared = deepcopy(record)
                shared['id'] = next_id
                next_id += 1
                result.append(shared)
                interned[key] = shared['id']
            remap[ident] = interned[key]
        remaps.append(remap)
    entries = []
    for document, remap in zip(decoded, remaps):
        trace = deepcopy(document['records'][document['entries'][0]])
        trace.update(id=next_id, initial=remap[trace['initial']],
                     data=[remap[ident] for ident in trace['data']])
        next_id += 1
        entries.append(trace['id'])
        result.append(trace)
    return encode_document(entries, result)


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def measure_shared_anthology(root: Path, qualified: dict) -> tuple[bytes, dict]:
    """Compile all selected truth once and audit every shared root through Player."""
    current, checked = validated_game_truth(root, qualified)
    standalone = [game_document(game) for _, game, _ in checked]
    data = share_game_documents(standalone)
    document = decode_document(data)
    report = {'scope': 'Complete shared v1 anthology presentation; NOT full curriculum/carrier/damage fit',
              'passed': False, 'source_sha256': current['sha256'],
              'qualified_truth_sha256': _digest(qualified), 'qualified_input_files': qualified['input_files'],
              'selected_source_ordinals': qualified['selection']['selected_source_ordinals'],
              'editorial_reduction': None, 'records': [],
              'document_bytes': len(data), 'document_sha256': hashlib.sha256(data).hexdigest(),
              'standalone_bytes': sum(map(len, standalone)),
              'standalone_document_collection_sha256': hashlib.sha256(b''.join(
                  len(item).to_bytes(4, 'big') + item for item in standalone)).hexdigest(),
              'saved_bytes': sum(map(len, standalone)) - len(data),
              'record_counts': dict(sorted(Counter(r['kind'] for r in document['records'].values()).items()))}
    paths = [Path(__file__), REPO / 'src/golden_board/anthology_playback.py',
             REPO / 'src/golden_board/authoring.py', REPO / 'src/golden_board/document.py',
             REPO / 'mechanism/player.mjs']
    report['input_files'] = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    expected = []
    for (row, game, _), entry in zip(checked, document['entries']):
        try:
            cells = audit_game(game, data, entry=entry)
        except ValueError as error:
            report.update(error=str(error), failed_source_ordinal=row['source_ordinal'], failed_entry=entry)
            return data, report
        trace = document['records'][entry]
        initial = document['records'][trace['initial']]
        full = [dict(initial, cells=frame) for frame in cells]
        expected.append({'id': entry, 'data': [document['records'][ident] for ident in trace['data']], 'frames': full})
        report['records'].append({**row, 'entry': entry, 'plies': len(game['moves']), 'score': game['score'],
                                  'frames': len(cells), 'shape': [initial['rows'], initial['cols']],
                                  'regions': initial['regions'], 'data_refs': trace['data'],
                                  'frame_sha256': [hashlib.sha256(bytes(frame)).hexdigest() for frame in cells],
                                  'render_sequence_sha256': _digest(full)})
    if len(document['entries']) != len(checked):
        report['error'] = 'Shared entry count differs from selected games'
        return data, report
    try:
        actual = player_entry_packets(root, data)
    except (subprocess.CalledProcessError, ValueError) as error:
        report['error'] = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            report['player_stdout'] = error.stdout.decode(errors='replace')
            report['player_stderr'] = error.stderr.decode(errors='replace')
        return data, report
    expected_glyphs = {str(r['id']): r for r in document['records'].values() if r['kind'] == 1}
    if actual['glyphs'] != expected_glyphs:
        report['error'] = 'Player glyph definitions differ'
        return data, report
    if len(actual['entries']) != len(expected):
        report['error'] = 'Player entry count differs'
        return data, report
    for index, (left, right) in enumerate(zip(expected, actual['entries'])):
        if left != right:
            report.update(error='Player entry/data/full-frame mismatch',
                          failed_source_ordinal=checked[index][0]['source_ordinal'], failed_entry=left['id'])
            for ply, (a, b) in enumerate(zip(left['frames'], right['frames'])):
                if a != b:
                    report.update(ply=ply, expected_frame=a, actual_frame=b)
                    break
            return data, report
    report.update(passed=True, game_count=len(checked), total_plies=sum(len(g['moves']) for _, g, _ in checked),
                  total_frames=sum(row['frames'] for row in report['records']),
                  maximum_plies=max(len(g['moves']) for _, g, _ in checked),
                  glyphs_sha256=_digest(expected_glyphs),
                  all_entries_tables_and_render_frames_exact=True)
    return data, report
