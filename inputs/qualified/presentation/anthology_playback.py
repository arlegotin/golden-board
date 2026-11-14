"""Complete current-format game/playback measurement; no carrier-fit inference."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

import chess

from .anthology import REPO, canonical_game_bytes, validate_prefix
from .authoring import audit_game, game_document, player_frames_batch
from .document import decode_document
from .source import source_spans


def validated_game_truth(root: Path, qualified: dict) -> tuple[dict, list]:
    """Reuse complete code-bound source truth without rerunning unchanged legality."""
    if (not qualified.get('qualified') or not qualified.get('comparisons') or
            not all(row['matches'] for row in qualified['comparisons'])):
        raise ValueError('Complete independently qualified source is required before playback measurement')
    current = source_spans(root)
    if current['sha256'] != qualified['source']['sha256']:
        raise ValueError('Qualified source identity changed')
    for relative, digest in qualified['input_files'].items():
        if hashlib.sha256((REPO / relative).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Qualified source dependency changed: {relative}')
    selected = qualified['selection']['selected_source_ordinals']
    eligible = qualified['selection']['eligible_source_ordinals']
    validate_prefix(eligible, selected)
    if selected != eligible:
        raise ValueError('This stage does not apply an editorial reduction')
    games = qualified['games']
    order = sorted(selected, key=lambda ordinal: canonical_game_bytes(games[str(ordinal)]))
    if order != [row['source_ordinal'] for row in qualified['canonical_games']]:
        raise ValueError('Canonical ordering changed selected membership')
    if [row['artifact_ordinal'] for row in qualified['canonical_games']] != list(range(1, len(order) + 1)):
        raise ValueError('Canonical game ordinals are not dense')
    checked = []
    for row in qualified['canonical_games']:
        ordinal = row['source_ordinal']; game = games[str(ordinal)]
        truth = canonical_game_bytes(game)
        if hashlib.sha256(truth).hexdigest() != row['truth_sha256']:
            raise ValueError(f'Qualified game truth changed at source ordinal {ordinal}')
        checked.append((row, game, truth))
    return current, checked


def measure_anthology(root: Path, qualified: dict) -> dict:
    current, checked = validated_game_truth(root, qualified)
    report = {'scope': 'Complete standalone game documents and generic playback; NOT full carrier/curriculum fit',
              'passed': False, 'source_sha256': current['sha256'], 'records': [], 'eligible_games': len(checked),
              'editorial_reduction': None, 'source_qualification_scope': qualified['scope']}
    documents = []
    expected_frames = []
    for row, game, truth in checked:
        ordinal = row['source_ordinal']
        data = game_document(game)
        entry = {'artifact_ordinal': row['artifact_ordinal'], 'source_ordinal': ordinal,
                 'plies': len(game['moves']), 'score': game['score'], 'truth_bytes': len(truth),
                 'truth_sha256': row['truth_sha256'], 'document_bytes': len(data),
                 'document_sha256': hashlib.sha256(data).hexdigest()}
        report['records'].append(entry)
        try:
            frames = audit_game(game, data)
        except ValueError as error:
            report.update(error=str(error), failed_source_ordinal=ordinal, failed_document_hex=data.hex())
            return report
        documents.append(data); expected_frames.append(frames)
        document = decode_document(data); trace = document['records'][document['entries'][0]]
        entry['assignments_per_ply'] = dict(sorted(Counter(len(step) for step in trace['steps']).items()))
        entry['special_moves'] = {'castling': [], 'en_passant': [], 'promotions': []}
        for ply, (origin, target, promotion) in enumerate(game['moves'], 1):
            before = chess.Board(game['positions'][ply - 1]['fen'])
            square = lambda cell: chess.square(cell % 8, 7 - cell // 8)
            move = chess.Move(square(origin), square(target),
                              promotion=(None, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)[promotion])
            if before.is_castling(move): entry['special_moves']['castling'].append(ply)
            if before.is_en_passant(move): entry['special_moves']['en_passant'].append(ply)
            if promotion: entry['special_moves']['promotions'].append({'ply': ply, 'choice': promotion})
    try:
        actual = player_frames_batch(root, documents)
    except (subprocess.CalledProcessError, ValueError) as error:
        report['error'] = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            report['player_stdout'] = error.stdout.decode(errors='replace')
            report['player_stderr'] = error.stderr.decode(errors='replace')
        return report
    if len(actual) != len(expected_frames):
        report['error'] = 'Player returned wrong game count'
        return report
    for entry, expected, frames in zip(report['records'], expected_frames, actual):
        if expected != frames:
            first = next((ply for ply, (a, b) in enumerate(zip(expected, frames)) if a != b),
                         min(len(expected), len(frames)))
            report.update(error=f'Player frame mismatch at ply {first}', failed_source_ordinal=entry['source_ordinal'],
                          expected_frames=expected, actual_frames=frames)
            return report
        entry.update(frames=len(frames), all_frames_exact=True,
                     frame_sha256=[hashlib.sha256(bytes(frame)).hexdigest() for frame in frames])
    report.update(passed=True, game_count=len(documents), total_plies=sum(row['plies'] for row in report['records']),
                  total_frames=sum(row['frames'] for row in report['records']),
                  total_truth_bytes=sum(row['truth_bytes'] for row in report['records']),
                  total_document_bytes=sum(map(len, documents)),
                  max_document_bytes=max(map(len, documents)), maximum_plies=max(row['plies'] for row in report['records']),
                  document_collection_sha256=hashlib.sha256(b''.join(len(data).to_bytes(4, 'big') + data for data in documents)).hexdigest(),
                  limits='Standalone documents repeat glyphs/headers; no full anthology carrier, complete curriculum, curation breadth, rights, full practical-profile or release claim')
    report['input_files'] = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                            (Path(__file__), REPO / 'src/golden_board/authoring.py', REPO / 'viewer/player.mjs',
                             REPO / 'src/golden_board/document.py')}
    return report
