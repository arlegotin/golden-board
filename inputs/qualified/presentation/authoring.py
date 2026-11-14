"""Authored developmental lessons and game data; subject knowledge stays here."""
import json
from pathlib import Path
import subprocess

import chess

from .document import NONE, decode_document, encode_document
from .source_game import cell_index, first_game


def _mask(rows):
    bits = ''.join(rows)
    return [int((bits + '0' * (-len(bits) % 8))[i:i + 8], 2)
            for i in range(0, len(bits), 8)]


def glyphs():
    result = [{'kind': 1, 'id': ident, 'rows': 2, 'cols': 2, 'mask': [mask]}
              for ident, mask in ((0, 0), (1, 0x90), (2, 0x60))]
    patterns = {
        3: ['110', '100', '000'], 4: ['000', '001', '011'],
        5: ['010', '111', '010'], 6: ['10', '01'], 7: ['01', '10'],
        8: ['111', '010', '000'], 9: ['000', '010', '111'],
        10: ['110', '110', '000'], 11: ['000', '011', '011'], 12: ['101', '000', '101']}
    for ident, rows in patterns.items():
        result.append({'kind': 1, 'id': ident, 'rows': len(rows), 'cols': len(rows[0]), 'mask': _mask(rows)})
    for count in range(1, 10):
        bits = '1' * count + '0' * (9 - count)
        result.append({'kind': 1, 'id': 12 + count, 'rows': 3, 'cols': 3,
                       'mask': _mask([bits[:3], bits[3:6], bits[6:]])})
    for side in range(2):
        for kind in range(1, 7):
            rows = [['0'] * 5 for _ in range(5)]
            rows[0 if side == 0 else 4][0 if side == 0 else 4] = '1'
            rows[1][1] = rows[3][3] = '1'
            for bit in range(3):
                rows[2][bit + 1] = str((kind >> (2 - bit)) & 1)
            result.append({'kind': 1, 'id': 31 + kind + side * 6, 'rows': 5, 'cols': 5,
                           'mask': _mask([''.join(row) for row in rows])})
    return result


def token(piece):
    return 0 if piece is None else 31 + piece.piece_type + (0 if piece.color else 6)


def occupancy(board):
    cells = [0] * 64
    for square, piece in board.piece_map().items():
        cells[cell_index(square)] = token(piece)
    return cells


def board_cells(board, source=None, mask=None, role=0, feedback=0, history=0, score=None):
    footer = [3 if board.turn else 4, token(board.piece_at(source)) if source is not None else 0,
              feedback, 12 + history if history else 0, 0, 0, 0, 0]
    if score is not None:
        footer[1] = 10 + score
    cells = occupancy(board) + footer
    if mask is not None:
        layer = [0] * 64
        for square in mask:
            layer[cell_index(square)] = 5
        cells += layer + [role, 0, 0, 0, 0, 0, 0, 0]
    return cells


def replay(text):
    board = chess.Board()
    boards = [board.copy()]
    for uci in text.split():
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError(f'Illegal authored witness at ply {len(boards)}: {uci}.')
        board.push(move)
        boards.append(board.copy())
    return boards


def legal_destinations(board, source):
    return {move.to_square for move in board.legal_moves if move.from_square == source}


class Author:
    def __init__(self):
        self.records = glyphs()
        self.next_frame = 1000
        self.next_trace = 2000
        self.next_page = 3000
        self.labels = {}

    def frame(self, cells, rows=9, cols=8, regions=()):
        ident = self.next_frame
        self.next_frame += 1
        self.records.append({'kind': 2, 'id': ident, 'rows': rows, 'cols': cols,
                             'cells': list(cells), 'regions': [list(region) for region in regions]})
        return ident

    def trace(self, frames, rows=9, cols=8, regions=(), data=()):
        initial = self.frame(frames[0], rows, cols, regions)
        steps = []
        previous = frames[0]
        for frame in frames[1:]:
            if len(frame) != len(previous):
                raise ValueError('Authored trace dimension change.')
            steps.append([[index, value] for index, value in enumerate(frame) if value != previous[index]])
            previous = frame
        ident = self.next_trace
        self.next_trace += 1
        self.records.append({'kind': 3, 'id': ident, 'initial': initial, 'data': list(data), 'steps': steps})
        return ident

    def page(self, label, display, trace=False, shape=0, choices=(), accepted=(),
             success=NONE, failure=NONE, passive=NONE, links=()):
        ident = self.next_page
        self.next_page += 1
        self.records.append({'kind': 4, 'id': ident, 'display_kind': int(trace), 'display': display,
                             'shape': shape, 'choices': list(choices),
                             'accepted': [list(value) for value in accepted],
                             'success': success, 'failure': failure, 'passive': passive, 'links': list(links)})
        self.labels[label] = ident
        return ident

    def record(self, ident):
        return next(record for record in self.records if record['id'] == ident)

    def encode(self, entries):
        return encode_document(entries, self.records)


def _lessons():
    author = Author()
    main = []
    witnesses = {}

    def worked(label, frames, rows=9, cols=8, witness=''):
        ident = author.page(label, author.trace(frames, rows, cols), trace=True)
        main.append(ident)
        witnesses[label] = witness
        return ident

    worked('representation', [[0, 1, 1, 1, 0, 1], [1, 1, 1, 1, 0, 1], [1, 1, 1, 1, 0, 0]], 2, 3)
    setup = replay('e2e4 e7e5')
    worked('setup_turn', [board_cells(board) for board in setup], witness='e2e4 e7e5')
    # A separate atlas is reachable from the setup page and carries all identities.
    atlas = author.frame(list(range(32, 44)), 2, 6)
    atlas_page = author.page('atlas', atlas)
    author.record(main[-1])['links'].append(atlas_page)
    slider = replay('e2e4 a7a6 f1b5')
    worked('slider', [board_cells(board) for board in slider], witness='e2e4 a7a6 f1b5')
    knight = replay('b1a3 g8h6 a3b5')
    worked('knight', [board_cells(board) for board in knight], witness='b1a3 g8h6 a3b5')
    capture = replay('e2e4 d7d5 e4d5')
    worked('capture', [board_cells(board) for board in capture], witness='e2e4 d7d5 e4d5')
    pin_text = 'e2e4 e7e5 g1f3 b8c6 f1b5 d7d6 a2a3'
    pinned = replay(pin_text)[-1]
    source = chess.C6
    geometric = set(pinned.attacks(source))
    legal = legal_destinations(pinned, source)
    if legal or {chess.square_name(square) for square in geometric} != {'a5', 'a7', 'b4', 'b8', 'd4', 'd8', 'e5', 'e7'}:
        raise ValueError('Pinned-control witness contradicts hand-derived set.')
    worked('control_legality', [board_cells(pinned, source, geometric, 8),
                                board_cells(pinned, source, legal, 9)], rows=18, witness=pin_text)
    hypothetical = pinned.copy()
    piece = hypothetical.remove_piece_at(chess.C6)
    hypothetical.set_piece_at(chess.D4, piece)
    if chess.Move.from_uci('c6d4') in pinned.legal_moves or not hypothetical.is_attacked_by(chess.WHITE, chess.E8):
        raise ValueError('Self-check contrast failed.')
    worked('self_check', [board_cells(pinned), board_cells(hypothetical, feedback=7)],
           witness=pin_text + ' ; rejected local occupancy c6→d4, not a legal continuation')
    ep_text = 'e2e4 a7a6 e4e5 d7d5'
    ep = replay(ep_text)[-1]
    if chess.Move.from_uci('e5d6') not in ep.legal_moves:
        raise ValueError('Immediate en-passant witness failed.')
    after = replay(ep_text + ' e5d6')[-1]
    delayed = replay(ep_text + ' g1f3 a6a5')[-1]
    if chess.Move.from_uci('e5d6') in delayed.legal_moves or after.piece_at(chess.D5) is not None:
        raise ValueError('En-passant removal/timing contrast failed.')
    ep_page = worked('en_passant', [board_cells(board) for board in replay(ep_text)]
                     + [board_cells(after, feedback=6)],
                     witness=ep_text + ' e5d6 ; compare linked delayed branch')
    delayed_attempt = delayed.copy()
    pawn = delayed_attempt.remove_piece_at(chess.E5)
    delayed_attempt.remove_piece_at(chess.D5)
    delayed_attempt.set_piece_at(chess.D6, pawn)
    delayed_frames = [board_cells(board) for board in replay(ep_text + ' g1f3 a6a5')]
    delayed_frames += [board_cells(delayed_attempt, feedback=7)]
    delayed_page = author.page('en_passant_delay', author.trace(delayed_frames), trace=True)
    author.record(ep_page)['links'].append(delayed_page)
    history_text = 'g1f3 g8f6 f3g1 f6g8 g1f3 g8f6 f3g1 f6g8'
    history_boards = replay(history_text)
    counts = {}
    history_frames = []
    for board in history_boards:
        # This knight-only witness has constant rights and no en-passant square.
        # This is not the general repetition-key implementation owned by S4.
        key = (board.board_fen(), board.turn)
        counts[key] = counts.get(key, 0) + 1
        history_frames.append(board_cells(board, history=counts[key]))
    if occupancy(history_boards[0]) != occupancy(history_boards[4]) or history_frames[0] == history_frames[4]:
        raise ValueError('Same-board/history contrast failed.')
    worked('history', history_frames, witness=history_text)

    practices = []
    for label, source, literal in [('practice_knight', chess.B1, {chess.A3, chess.C3}),
                                   ('practice_empty', chess.F1, set())]:
        board = chess.Board()
        destinations = legal_destinations(board, source)
        if destinations != literal:
            raise ValueError(f'Practice {label} differs from hand-derived set.')
        prompt = board_cells(board, source, {source}, 5)
        result = board_cells(board, source, destinations, 9)
        correct = board_cells(board, source, destinations, 9, feedback=6)
        wrong = board_cells(board, source, destinations, 9, feedback=7)
        regions = [[index + 1, index] for index in range(64)]
        correct_page = author.page(label + '_correct', author.frame(correct, 18))
        wrong_page = author.page(label + '_wrong', author.frame(wrong, 18))
        passive = author.page(label + '_passive', author.trace([prompt, result, correct], 18),
                              trace=True, links=[correct_page])
        page = author.page(label, author.frame(prompt, 18, regions=regions), shape=2,
                           choices=list(range(1, 65)),
                           accepted=[sorted(cell_index(square) + 1 for square in destinations)],
                           success=correct_page, failure=wrong_page, passive=passive, links=[passive])
        practices.append((page, correct_page, wrong_page, passive))
        main.append(page)
        witnesses[label] = 'standard initial position; target source carried by separate mask'
    for index, ident in enumerate(main):
        following = main[index + 1] if index + 1 < len(main) else main[0]
        author.record(ident)['links'].append(following)
    author.record(atlas_page)['links'] = [main[1], main[2]]
    author.record(delayed_page)['links'] = [ep_page, author.labels['history']]
    for page, correct, wrong, passive in practices:
        following = author.record(page)['links'][-1]
        author.record(correct)['links'] = [page, following]
        author.record(wrong)['links'] = [page, passive, following]
    coverage = {label: author.labels[label] for label in witnesses}
    return author.encode([main[0]]), coverage, witnesses


def game_document(game):
    author = Author()
    author.records.extend([
        {'kind': 5, 'id': 4000, 'rows': len(game['moves']), 'cols': 3,
         'values': [value for move in game['moves'] for value in move]},
        {'kind': 5, 'id': 4001, 'rows': 1, 'cols': 1, 'values': [game['score']]}])
    frames = [board_cells(chess.Board(position['fen']), score=game['score'] if index == len(game['moves']) else None)
              for index, position in enumerate(game['positions'])]
    trace = author.trace(frames, data=[4000, 4001])
    return author.encode([trace])


def build_content(root: Path) -> dict:
    lesson, coverage, witnesses = _lessons()
    game = first_game(root)
    return {'documents': {1: lesson, 2: game_document(game)}, 'coverage': coverage,
            'witnesses': witnesses, 'game_plies': len(game['moves']),
            'source_ordinal': 1, 'scope': 'development representative, not anthology selection'}


def author_slice(root: Path) -> dict[int, bytes]:
    return build_content(root)['documents']


def audit_game(game: dict, data: bytes, entry: int | None = None) -> list[list[int]]:
    document = decode_document(data)
    entry = document['entries'][0] if entry is None else entry
    if type(entry) is not int or entry not in document['entries']:
        raise ValueError('Unknown game entry.')
    for glyph in glyphs():
        if document['records'].get(glyph['id']) != glyph:
            raise ValueError(f'Game glyph definition mismatch: {glyph["id"]}.')
    trace = document['records'][entry]
    if trace['kind'] != 3 or len(trace['steps']) != len(game['moves']):
        raise ValueError('Incomplete game presentation.')
    move_table, score_table = [document['records'][ident] for ident in trace['data']]
    if (move_table['rows'] != len(game['moves']) or move_table['cols'] != 3 or
            move_table['values'] != [value for move in game['moves'] for value in move] or
            score_table['values'] != [game['score']]):
        raise ValueError('Canonical move/score data mismatch.')
    initial = document['records'][trace['initial']]
    if (initial['rows'], initial['cols'], initial['regions']) != (9, 8, []):
        raise ValueError('Game frame dimensions/regions mismatch.')
    current = list(initial['cells'])
    frames = []
    for ply, position in enumerate(game['positions']):
        if ply:
            for index, token_id in trace['steps'][ply - 1]:
                current[index] = token_id
        expected = board_cells(chess.Board(position['fen']), score=game['score'] if ply == len(game['moves']) else None)
        if current != expected:
            mismatch = next((index for index, (left, right) in enumerate(zip(current, expected)) if left != right), None)
            raise ValueError(f'Game presentation mismatch at ply {ply}, cell {mismatch}.')
        frames.append(list(current))
    return frames


def audit_game_document(root: Path, data: bytes) -> list[list[int]]:
    return audit_game(first_game(root), data)


def player_frames_batch(root: Path, documents: list[bytes]) -> list[list[list[int]]]:
    result = subprocess.run(['node', '--input-type=module', '-e',
        "import {readFileSync} from 'node:fs'; import {decodeDocument,Player} from './viewer/player.mjs'; "
        "const all=JSON.parse(readFileSync(0,'utf8')).map(hex=>{const d=decodeDocument(Buffer.from(hex,'hex')); "
        "const p=new Player(d); const frames=[p.packet().frame.cells]; "
        "for(let k=1;k<=p.packet().step_count;k++){const a=p.action({seek:k});if(!a.ok)throw Error(a.error);frames.push(p.packet().frame.cells)} "
        "return frames;});console.log(JSON.stringify(all));"], cwd=root,
        input=json.dumps([data.hex() for data in documents]).encode(), capture_output=True, check=True)
    return json.loads(result.stdout)


def player_frames(root: Path, data: bytes) -> list[list[int]]:
    return player_frames_batch(root, [data])[0]


def player_entry_packets(root: Path, data: bytes) -> dict:
    """All carried roots through the same generic Player, retaining render metadata."""
    result = subprocess.run(['node', '--input-type=module', '-e',
        "import {readFileSync} from 'node:fs'; import {decodeDocument,Player} from './viewer/player.mjs'; "
        "const d=decodeDocument(Buffer.from(readFileSync(0,'utf8').trim(),'hex')); "
        "const glyphs=new Player(d).packet().glyphs; "
        "const entries=d.entries.map(id=>{const p=new Player(d,id);const initial=p.packet(); "
        "const frames=[initial.frame];for(let k=1;k<=initial.step_count;k++){"
        "const a=p.action({seek:k});if(!a.ok)throw Error(a.error);frames.push(a.packet.frame)} "
        "return {id,data:initial.data,frames};});console.log(JSON.stringify({glyphs,entries}));"],
        cwd=root, input=data.hex().encode(), capture_output=True, check=True)
    return json.loads(result.stdout)
