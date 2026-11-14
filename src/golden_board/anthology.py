"""Strict source classification and narrow independent original-SAN qualification."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

from .environment import verify_dependencies
from .rules import Replay
from .source import source_spans
from .source_game import parse_mainline

REPO = Path(__file__).resolve().parents[2]


def canonical_game_bytes(game: dict) -> bytes:
    """Semantic identity/order key, not a new recipient document wire format."""
    if game['score'] not in (0, 1, 2):
        raise ValueError('Unknown minimal score')
    moves = game['moves']
    if any(len(move) != 3 or any(type(v) is not int for v in move) or
           not (0 <= move[0] < 64 and 0 <= move[1] < 64 and 0 <= move[2] <= 4) for move in moves):
        raise ValueError('Invalid numeric move tuple')
    return len(moves).to_bytes(4, 'big') + bytes(v for move in moves for v in move) + bytes([game['score']])


def validate_prefix(eligible: list[int], selected: list[int]) -> None:
    """Validate membership only; this does not authorize/apply an editorial cut."""
    if (len(set(eligible)) != len(eligible) or selected != eligible[:len(selected)] or
            (eligible and not selected)):
        raise ValueError('Selection must preserve a nonempty leading eligible source-order prefix')


def import_anthology(root: Path) -> dict:
    inventory = source_spans(root)
    raw = (root / inventory['path']).read_bytes()
    records, games, groups = [], {}, {}
    for source in inventory['records']:
        ordinal = source['ordinal']
        row = {'source_ordinal': ordinal, 'start': source['start'], 'end': source['end'], 'raw_sha256': source['sha256']}
        try:
            game = parse_mainline(raw[source['start']:source['end']])
            games[str(ordinal)] = game
            key = tuple(tuple(move) for move in game['moves'])
            groups.setdefault(key, []).append(row)
            truth = canonical_game_bytes(game)
            row.update(classification='eligible', plies=len(game['moves']), score=game['score'],
                       board_end=game['board_end'], truth_sha256=hashlib.sha256(truth).hexdigest(), truth_bytes=len(truth))
        except ValueError as error:
            row.update(classification='invalid', reason=str(error))
        records.append(row)
    for group in groups.values():
        if len({row['score'] for row in group}) > 1:
            for row in group:
                row.update(classification='conflict', reason='Identical validated moves have contradictory scores',
                           conflicting_source_ordinals=[r['source_ordinal'] for r in group])
        else:
            for row in group[1:]:
                row.update(classification='duplicate', duplicate_of=group[0]['source_ordinal'],
                           reason='Identical validated moves and score; earliest source occurrence retained')
    eligible = [row['source_ordinal'] for row in records if row['classification'] == 'eligible']
    selected = eligible[:]
    validate_prefix(eligible, selected)
    ordered = sorted(selected, key=lambda ordinal: canonical_game_bytes(games[str(ordinal)]))
    canonical = [{'artifact_ordinal': index, 'source_ordinal': ordinal,
                  'truth_sha256': hashlib.sha256(canonical_game_bytes(games[str(ordinal)])).hexdigest()}
                 for index, ordinal in enumerate(ordered, 1)]
    return {'scope': 'Strict all-record import; independent qualification pending', 'qualified': False,
            'source': inventory, 'record_count': len(records), 'records': records, 'games': games,
            'selection': {'eligible_source_ordinals': eligible, 'selected_source_ordinals': selected,
                          'editorial_tail_cut': None, 'mode': 'all valid nonduplicate nonconflicting source records'},
            'canonical_games': canonical}


def independent_anthology(root: Path, path: Path | None = None) -> dict:
    verify_dependencies(root)
    path = path or root / 'inputs/anthology.pgn'
    archive_path = root / 'inputs/dependencies/chess.js-1.4.0.tgz'
    with tempfile.TemporaryDirectory() as directory:
        module = Path(directory) / 'chess.cjs'
        with tarfile.open(archive_path) as archive:
            module.write_bytes(archive.extractfile('package/dist/cjs/chess.js').read())
        command = ['node', str(REPO / 'tests/reference-anthology.mjs'), str(path), str(module)]
        run = subprocess.run(command, capture_output=True, text=True)
        if run.returncode:
            raise ValueError(f'Independent original-SAN tool failed ({run.returncode}): {run.stderr}')
    result = json.loads(run.stdout)
    if result['source_sha256'] != hashlib.sha256(path.read_bytes()).hexdigest():
        raise ValueError('Independent source identity mismatch')
    result['dependency_sha256'] = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    result['stderr'] = run.stderr
    return result


def compare_game(game: dict, reference: dict) -> dict:
    for field in ('score', 'moves', 'board_end'):
        if game[field] != reference[field]:
            result = {'matches': False, 'field': field, 'production': game[field], 'reference': reference[field]}
            if field == 'moves':
                result['ply'] = next((i + 1 for i, (a, b) in enumerate(zip(game[field], reference[field])) if a != b),
                                     min(len(game[field]), len(reference[field])) + 1)
            return result
    if len(game['positions']) != len(reference['positions']):
        return {'matches': False, 'field': 'position_count', 'production': len(game['positions']),
                'reference': len(reference['positions'])}
    for ply, (left, right) in enumerate(zip(game['positions'], reference['positions'])):
        if left['fen'] != right['fen']:
            return {'matches': False, 'field': 'fen', 'ply': ply, 'production': left['fen'], 'reference': right['fen']}
    return {'matches': True, 'plies': len(game['moves']), 'positions': len(game['positions'])}


def _adapter_replay(game):
    replay = Replay()
    if replay.fen != game['positions'][0]['fen']:
        return {'matches': False, 'field': 'adapter_fen', 'ply': 0}
    for ply, (origin, destination, promotion) in enumerate(game['moves'], 1):
        square = lambda cell: chr(97 + cell % 8) + str(8 - cell // 8)
        uci = square(origin) + square(destination) + ('qrbn'[promotion - 1] if promotion else '')
        try:
            replay.play(uci)
        except ValueError as error:
            return {'matches': False, 'field': 'adapter_move', 'ply': ply, 'error': str(error)}
        if replay.fen != game['positions'][ply]['fen']:
            return {'matches': False, 'field': 'adapter_fen', 'ply': ply,
                    'production': game['positions'][ply]['fen'], 'adapter': replay.fen}
    ending = game['board_end']
    expected = None if ending == 'active' else {'score': game['score'], 'reason': ending}
    actual = None if replay.outcome is None else {'score': replay.outcome.score, 'reason': replay.outcome.reason}
    if actual != expected:
        return {'matches': False, 'field': 'adapter_outcome', 'ply': len(game['moves']),
                'production': expected, 'adapter': actual}
    return {'matches': True, 'plies': len(game['moves']), 'positions': len(game['positions']),
            'ending': ending, 'outcome': actual}


def qualify_anthology(root: Path) -> dict:
    report = import_anthology(root)
    try:
        reference = independent_anthology(root, root / report['source']['path'])
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        report['qualification_error'] = str(error)
        return report
    if reference['source_sha256'] != report['source']['sha256']:
        report['qualification_error'] = 'Independent source identity differs from the imported locked bytes'
        return report
    if len(reference['records']) != report['record_count']:
        raise ValueError('Independent source record count mismatch')
    checks = []
    for row, ref in zip(report['records'], reference['records']):
        ordinal = row['source_ordinal']
        if ref['source_ordinal'] != ordinal:
            raise ValueError('Independent source ordinal mismatch')
        accepted = str(ordinal) in report['games']
        check = {'source_ordinal': ordinal, 'reference_status': ref['status']}
        if accepted != (ref['status'] == 'accepted'):
            check.update(matches=False, field='acceptance', reference_error=ref.get('error'), production_reason=row.get('reason'))
        elif not accepted:
            check.update(matches=True, classification='both rejected; diagnostics retained', reference_error=ref['error'])
        else:
            game = report['games'][str(ordinal)]
            check.update(compare_game(game, ref['game']))
            check['adapter'] = _adapter_replay(game)
            check['matches'] = check['matches'] and check['adapter']['matches']
        checks.append(check)
    report['qualified'] = bool(report['selection']['selected_source_ordinals']) and all(c['matches'] for c in checks)
    report['scope'] = 'All-source original-SAN/practical replay comparison; hand-derived rule qualification, curation and rights are separate'
    report['reference'] = reference
    report['comparisons'] = checks
    report['total_plies_compared'] = sum(len(game['moves']) for game in report['games'].values())
    report['input_files'] = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
        (Path(__file__), REPO / 'src/golden_board/source.py', REPO / 'src/golden_board/source_game.py',
         REPO / 'src/golden_board/rules.py', REPO / 'tests/reference-anthology.mjs', REPO / 'inputs/dependencies/lock.json')}
    return report
