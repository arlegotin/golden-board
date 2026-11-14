"""Strict first-record development import; full anthology qualification is S4."""
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

import chess

from .environment import verify_dependencies
from .rules import board_ending
from .source import verify_source


def cell_index(square: int) -> int:
    return (7 - chess.square_rank(square)) * 8 + chess.square_file(square)


def board_end(board):
    return board_ending(board)


def parse_mainline(span: bytes) -> dict:
    try:
        header, movetext = re.split(r'\r?\n[ \t]*\r?\n', span.decode('utf-8'), maxsplit=1)
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError('Source record lacks a valid UTF-8 header boundary.') from error
    tags = {}
    for line in header.splitlines():
        match = re.fullmatch(r'\[([A-Za-z0-9_]+) "((?:[^"\\]|\\["\\])*)"\]', line)
        if not match or match[1] in tags:
            raise ValueError('Malformed/duplicate source tag.')
        tags[match[1]] = match[2]
    if ('FEN' in tags or 'Variant' in tags or tags.get('SetUp', '0') != '0'
            or tags.get('Result') not in ('1-0', '0-1', '1/2-1/2')):
        raise ValueError('Only concluded standard-start main lines are supported.')
    tokens = list(re.finditer(r'\S+', movetext))
    board = chess.Board()
    positions = []

    def observe():
        positions.append({'board': board.board_fen(), 'turn': 0 if board.turn else 1,
                          'fen': board.fen(en_passant='fen')})

    observe()
    moves, san = [], []
    numbered = False
    marker = None
    promotion = {None: 0, chess.QUEEN: 1, chess.ROOK: 2, chess.BISHOP: 3, chess.KNIGHT: 4}
    for index, match in enumerate(tokens):
        token = match[0]
        number = re.fullmatch(r'([1-9][0-9]*)(\.|\.\.\.)', token)
        if number:
            expected_dots = '.' if board.turn else '...'
            if numbered or int(number[1]) != board.fullmove_number or number[2] != expected_dots:
                raise ValueError(f'Incorrect move number at movetext byte {match.start()}.')
            numbered = True
            continue
        if token in ('1-0', '0-1', '1/2-1/2', '*'):
            if index != len(tokens) - 1 or numbered or token != tags['Result'] or token == '*':
                raise ValueError('Unfinished, mismatched or trailing result tokens.')
            marker = token
            break
        if board.turn and not numbered:
            raise ValueError(f'Missing move number before ply {len(moves) + 1}.')
        if board_end(board) != 'active':
            raise ValueError(f'Continuation after board ending at ply {len(moves) + 1}.')
        try:
            move = board.parse_san(token)
        except ValueError as error:
            raise ValueError(f'Invalid SAN at ply {len(moves) + 1}: {token!r}.') from error
        if move not in board.legal_moves or board.san(move) != token:
            raise ValueError(f'Noncanonical/incorrect SAN at ply {len(moves) + 1}: {token!r}.')
        moves.append([cell_index(move.from_square), cell_index(move.to_square), promotion[move.promotion]])
        san.append(token)
        board.push(move)
        observe()
        numbered = False
    if marker is None or not moves:
        raise ValueError('Missing concluded main line/result.')
    score = {'1-0': 0, '0-1': 1, '1/2-1/2': 2}[marker]
    ending = board_end(board)
    if ending == 'checkmate' and score != (1 if board.turn else 0):
        raise ValueError('Recorded score contradicts checkmate.')
    if ending in ('stalemate', 'common-dead') and score != 2:
        raise ValueError('Recorded score contradicts board draw.')
    return {'moves': moves, 'san': san, 'positions': positions, 'score': score, 'board_end': ending}


def first_game(root: Path) -> dict:
    inventory = verify_source(root)
    first = inventory['records'][0]
    data = (root / inventory['path']).read_bytes()[first['start']:first['end']]
    return parse_mainline(data)


def independent_first_game(root: Path) -> dict:
    verify_source(root)
    verify_dependencies(root)
    with tempfile.TemporaryDirectory() as directory:
        module = Path(directory) / 'chess.cjs'
        with tarfile.open(root / 'inputs/dependencies/chess.js-1.4.0.tgz') as archive:
            module.write_bytes(archive.extractfile('package/dist/cjs/chess.js').read())
        result = subprocess.run(['node', str(root / 'tests/reference-game.mjs'),
                                 str(root / 'inputs/anthology.pgn'), str(module)],
                                capture_output=True, text=True, check=True)
    return json.loads(result.stdout)
