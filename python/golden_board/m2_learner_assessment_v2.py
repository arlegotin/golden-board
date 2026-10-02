"""Independent final assessment from authored intent and recovered pictures.

This module neither imports the lesson author nor consumes its owner output.
"""
from hashlib import sha256
import re
import tomllib

from . import canonical_manifest as manifest, chess, content as c

CONTENT_SHA = '141168a051b44f978667f7c562070300d79368ace3fee47f5d19082de7642c17'
FIXTURE_SHA = '9a63aa74a32761bf1f8919278e895f532e4d4f305a30f74ddd1d0c4acec6a639'
GAMES_SHA = 'e883055cd0417061cf04d596cbca75d039948a987180d26a80bd6d6888f4764e'
IDENTITIES = (
    ('final-grid', 'grid', 'occupancy'), ('final-turn', 'turn', 'transition'),
    ('final-sliding', 'sliding', 'transition'), ('final-knight', 'knight', 'transition'),
    ('final-capture', 'capture', 'transition'), ('final-control', 'attack', 'control'),
    ('final-castling', 'castling', 'transition'), ('final-en-passant', 'en_passant', 'transition'),
    ('final-self-check', 'self_check', 'transition'), ('final-promotion', 'promotion', 'transition'),
    ('final-history', 'history', 'history'), ('final-game', 'game', 'record_transition'))
KEYS = {'id', 'family', 'kind', 'page_ordinal', 'prefix_kind', 'prefix_value',
        'prefix_plies', 'suffix', 'option_moves', 'reverse'}


def _require(ok, reason):
    if not ok:
        raise ValueError('learner-assessment-v2:' + reason)


def _hash(raw):
    return sha256(raw).hexdigest()


def _line(value):
    tokens = value.split()
    _require(len(tokens) <= 64, 'prefix-bound')
    out = bytearray()
    for token in tokens:
        _require(re.fullmatch(r'[a-h][1-8][a-h][1-8][qrbn]?', token) is not None, 'uci')
        a = ord(token[0])-97 + 8*(int(token[1])-1)
        b = ord(token[2])-97 + 8*(int(token[3])-1)
        p = {'': 0, 'q': 1, 'r': 2, 'b': 3, 'n': 4}[token[4:]]
        raw = ((a << 10) | (b << 4) | (p << 1)).to_bytes(2, 'big')
        chess.decode_move(raw)
        out.extend(raw)
    return bytes(out)


def _moves(raw):
    _require(len(raw) % 2 == 0, 'move-framing')
    return tuple(chess.decode_move(raw[i:i+2]) for i in range(0, len(raw), 2))


def _game(raw):
    _require(raw[:2] == b'\0@', 'game-count')
    offset, total, games = 2, 0, []
    for _ in range(64):
        _require(offset+2 <= len(raw), 'game-truncated')
        count = int.from_bytes(raw[offset:offset+2], 'big')
        total += count
        end = offset+3+2*count
        _require(1 <= count <= 4096 and total <= 65535 and end <= len(raw), 'game-bound')
        game = raw[offset:end]
        _require(game[-1] <= 2 and (not games or games[-1] < game), 'game-order-score')
        games.append(game)
        offset = end
    _require(offset == len(raw), 'game-eof')
    chess.validate_source_record(_moves(games[0][2:-1]), games[0][-1])
    return games[0]


def _matrix(rows, columns, cells):
    cells = list(cells)
    _require(len(cells) == rows*columns, 'matrix-size')
    return rows, columns, cells


def _board(raw):
    return _matrix(10, 8, [raw[r*8+f] for r in range(7, -1, -1) for f in range(8)]
                   + [255]*8 + list(raw[64:]) + [255]*5)


def _mask(values):
    return _matrix(8, 8, [values[r*8+f] for r in range(7, -1, -1) for f in range(8)])


def _compose(panels, options):
    rows, cols = max(p[0] for p in options), sum(p[1] for p in options)+1
    cells, regions, left = [255]*(rows*cols), [], 0
    for rid, (height, width, data) in enumerate(options, 1):
        for r in range(height):
            cells[r*cols+left:r*cols+left+width] = data[r*width:(r+1)*width]
        regions.append((rid, 0, height, left, left+width))
        left += width+1
    panels = panels + [_matrix(rows, cols, cells)]
    positions, top, left, height, width = [], 0, 0, 0, 0
    for r, col, _ in panels:
        if left and left+col > 36:
            top, left, height = top+height+2, 0, 0
        positions.append((top, left))
        width, height = max(width, left+col), max(height, r)
        left += col+2
    rows = top+height
    cells = [255]*(rows*width)
    for (r, col, data), (top, left) in zip(panels, positions, strict=True):
        for y in range(r):
            at = (top+y)*width+left
            cells[at:at+col] = data[y*col:(y+1)*col]
    top, left = positions[-1]
    regions = tuple(c.ContentRegion(rid, 0, r0+top, r1+top, c0+left, c1+left, 1)
                    for rid, r0, r1, c0, c1 in regions)
    return c.ContentMatrix(1, rows, width, tuple(cells)), regions


def _proposed(before, move):
    raw = bytearray(before)
    origin, dest = move.origin, move.destination
    code = before[origin]
    kind = (code-1) % 6+1 if code else 0
    side = (code-1)//6 if code else before[64]
    raw[origin], raw[dest], raw[64], raw[66] = 0, code, raw[64]^1, 0
    if kind == 1:
        if before[dest] == 0 and before[66] == dest+1 and abs(origin % 8-dest % 8) == 1:
            raw[(origin//8)*8+dest % 8] = 0
        if origin % 8 == dest % 8 and abs(origin//8-dest//8) == 2:
            raw[66] = (origin+dest)//2+1
        if move.promotion:
            raw[dest] = 6*side+{1: 5, 2: 4, 3: 3, 4: 2}[move.promotion]
    if kind == 6:
        raw[65] &= 12 if side == 0 else 3
        pair = {(4, 6): (7, 5), (4, 2): (0, 3), (60, 62): (63, 61), (60, 58): (56, 59)}.get((origin, dest))
        if pair:
            a, b = pair
            raw[a], raw[b] = 0, before[a]
    for square, bit, rook in ((7, 1, 4), (0, 2, 4), (63, 4, 10), (56, 8, 10)):
        if (origin == square and code == rook) or (dest == square and before[square] == rook):
            raw[65] &= 15^bit
    return bytes(raw)


def _derive(q, fixtures, game, game_set):
    pk, pv = q['prefix_kind'], q['prefix_value']
    if pk == 'literal':
        _require(q['prefix_plies'] == 0, 'literal-plies')
        prefix = _line(pv)
    elif pk == 'fixture':
        _require(q['prefix_plies'] == 0, 'fixture-plies')
        selected = [case for case in fixtures['cases'] if case['name'] == pv]
        _require(len(selected) == 1, 'fixture-name')
        prefix = bytes.fromhex(selected[0]['input']['moves_hex'])
    else:
        _require(pk == 'game' and pv == '' and q['prefix_plies'] <= (len(game)-3)//2, 'game-prefix')
        prefix = game[2:2+2*q['prefix_plies']]
    prefix += _line(q['suffix'])
    _require(len(prefix) <= 128, 'prefix-bound')
    state = chess.replay_from_start(_moves(prefix))
    before = chess.encode_position(state.position)
    kind = q['kind']
    evidence = dict(kind=kind, prefix_hex=prefix.hex(), before_hex=before.hex())
    panels = [_board(before)]
    if kind in ('transition', 'record_transition'):
        option_moves = [_line(v) for v in q['option_moves']]
        _require(all(len(v) == 2 for v in option_moves), 'one-option-move')
        if kind == 'record_transition':
            _require(pk == 'game' and not q['suffix'] and len(option_moves) == 1
                     and q['prefix_plies'] < (len(game)-3)//2, 'record-question')
            encoded = game[2+len(prefix):4+len(prefix)]
            option_moves.insert(0, encoded)
            if q['reverse']:
                option_moves.reverse()
        else:
            _require(len(option_moves) == 2 and not q['reverse'], 'transition-question')
        _require(option_moves[0] != option_moves[1], 'option-distinct')
        options, facts, accepted = [], [], []
        for i, raw in enumerate(option_moves, 1):
            move = chess.decode_move(raw)
            fact = dict(region_id=i, move_hex=raw.hex())
            try:
                after = chess.encode_position(chess.apply_move(state, move).position)
                fact.update(legal=True, after_hex=after.hex())
                accepted.append(True)
            except chess.ChessReject as error:
                after = _proposed(before, move)
                fact.update(legal=False, rejection=error.code, proposed_hex=after.hex())
                accepted.append(False)
            options.append(_board(after))
            facts.append(fact)
        evidence['options'] = facts
        if kind == 'record_transition':
            _require(all(accepted) and len({bytes.fromhex(f['after_hex'])[64:] for f in facts}) == 1,
                     'record-legal-footer')
            accepted = [raw == encoded for raw in option_moves]
            move = chess.decode_move(encoded)
            diagram = dict(wire_bytes=list(encoded), origin=move.origin,
                           destination=move.destination, promotion=move.promotion)
            panels[:0] = [_matrix(1, 1, [245]), _matrix(2, 3,
                list(encoded)+[255, move.origin, move.destination, move.promotion])]
            evidence.update(game_path='reports/game-set-v0.bin', game_set_sha256=_hash(game_set),
                game_sha256=_hash(game), game_ordinal=0, ply_index=q['prefix_plies'],
                record_move_hex=encoded.hex(), record_diagram=diagram)
    else:
        _require(not q['option_moves'], 'nonmove-options')
        if kind == 'occupancy':
            mask = [int(chess.evaluate_predicate(b'chess.occupancy', chess.OccupancyInput(
                state.position, sq, chess.OccupancyMatch('occupied')))) for sq in range(64)]
            evidence['mask'] = mask
            panels.insert(0, _matrix(1, 1, [253]))
            options, accepted = [_mask(mask), _mask([1-v for v in mask])], [True, False]
        elif kind == 'control':
            mask = [int(bool(chess.controls_square(state.position, 0, sq))) for sq in range(64)]
            destinations = {move.destination for move in chess.legal_moves(state)}
            legal = [int(sq in destinations) for sq in range(64)]
            _require(mask != legal, 'control-discriminator')
            evidence.update(side=0, control_mask=mask, legal_destination_mask=legal)
            panels[:0] = [_matrix(1, 1, [254]), _matrix(1, 6, range(1, 7))]
            options, accepted = [_mask(mask), _mask(legal)], [True, False]
        else:
            _require(kind == 'history', 'question-kind')
            positions = [chess.encode_position(chess.replay_from_start(_moves(prefix[:n])).position)
                         for n in range(0, len(prefix)+1, 2)]
            rows = ((len(positions)+2)//3)*12-1
            cells = [255]*(rows*26)
            for i, raw in enumerate(positions):
                top, left = (i//3)*12, (i % 3)*9
                cells[top*26+left] = i
                board = _board(raw)[2]
                for y in range(10):
                    at = (top+1+y)*26+left
                    cells[at:at+8] = board[y*8:(y+1)*8]
            fact = chess.evaluate_predicate(b'chess.history_claim', chess.HistoryClaimInput(state))
            evidence.update(positions_hex=[p.hex() for p in positions],
                occurrences=fact.current_key_occurrences, threefold_available=fact.threefold_available)
            panels = [_matrix(1, 1, [247]), _matrix(rows, 26, cells), _board(before)]
            options = [_matrix(1, 1, [0]), _matrix(1, 1, [1])]
            accepted = [not fact.threefold_available, fact.threefold_available]
        if q['reverse']:
            options.reverse()
            accepted.reverse()
    correct = [i+1 for i, valid in enumerate(accepted) if valid]
    _require(correct and options[0] != options[1], 'question-discriminator')
    matrix, regions = _compose(panels, options)
    return matrix, regions, correct, evidence


def build_learner_assessment_v2(required_raw, intent_raw, chess_fixture_raw, game_set_raw):
    for raw, limit in ((required_raw, 42432), (intent_raw, 16384),
                       (chess_fixture_raw, 2097152), (game_set_raw, 327677)):
        _require(type(raw) is bytes and 0 < len(raw) <= limit, 'input-type-size')
    _require(len(required_raw) == 42432 and _hash(required_raw) == CONTENT_SHA, 'required-identity')
    _require(_hash(chess_fixture_raw) == FIXTURE_SHA and _hash(game_set_raw) == GAMES_SHA, 'source-identity')
    source = tomllib.loads(intent_raw.decode('utf-8'))
    _require(set(source) == {'schema', 'questions'} and source['schema'] ==
             'golden-board.m2-learner-assessment-source/v2', 'intent-root')
    questions = source['questions']
    _require(type(questions) is list and len(questions) == 12, 'question-count')
    for i, (q, identity) in enumerate(zip(questions, IDENTITIES, strict=True), 53):
        _require(type(q) is dict and set(q) == KEYS, 'question-keys')
        for key in KEYS-{'page_ordinal', 'prefix_plies', 'reverse', 'option_moves'}:
            _require(type(q[key]) is str and q[key].isascii() and len(q[key]) <= 256, 'question-string')
        _require(type(q['page_ordinal']) is int and q['page_ordinal'] == i
                 and type(q['prefix_plies']) is int and 0 <= q['prefix_plies'] <= 64
                 and type(q['reverse']) is bool, 'question-scalars')
        _require((q['id'], q['family'], q['kind']) == identity, 'question-identity')
        _require(type(q['option_moves']) is list and len(q['option_moves']) <= 2
                 and all(type(v) is str and v.isascii() and len(v) <= 5 for v in q['option_moves']), 'option-domain')
    fixtures = manifest.validate_canonical_manifest(chess_fixture_raw)
    game = _game(game_set_raw)
    view = c.projection_view(c.stream_validation(required_raw))
    _require(c.encode_content_v0(c.authoring_from_validated(view)) == required_raw, 'typed-roundtrip')
    records = {r.record_id: r.payload for r in view.records}
    nodes = [(r.record_id, r.payload) for r in view.records if isinstance(r.payload, c.ContentLessonNode)]
    _require(view.root_record_id == 588 and records[588] == c.ContentRoot(nodes[0][0], 4160)
             and len(nodes) == 65, 'lesson-root-count')
    _require([sum(n.answer_mode == mode for _, n in nodes) for mode in (3, 1, 2)] == [46, 7, 12], 'lesson-roles')
    for _, node in nodes:
        _require(node.role == (3 if node.answer_mode == 3 else 5) and node.response_shape == 1
            and node.flags == 0 and node.max_selections == 1 and node.item_event_budget == 16, 'node-contract')
    pages = []
    for q in questions:
        index = q['page_ordinal']
        node_id, node = nodes[index]
        expected_next = nodes[index+1][0] if index+1 < len(nodes) else 0
        _require(node.answer_mode == 2 and node.predicate_result_ref == 0 and node.passive_trace_ref == 0
            and not node.cases and node.default_next_node_ref == expected_next, 'heldout-contract')
        _require(records[node.default_feedback_ref] == c.ContentFeedback(1, node.presentation_ref, 0), 'heldout-feedback')
        matrix, regions, correct, evidence = _derive(q, fixtures, game, game_set_raw)
        _require(records[node.presentation_ref] == matrix and records[node.region_set_ref] ==
                 c.ContentRegionSet(node.presentation_ref, regions), 'recovered-question-picture')
        pages.append(dict(id=q['id'], family=q['family'], phase='heldout', node_id=node_id,
            surface_matrix_id=node.presentation_ref, region_set_id=node.region_set_ref,
            correct=correct, evidence=evidence))
    return manifest.serialize_manifest(dict(schema='golden-board.m2-lesson-owner/v2',
        assessment_source_sha256=_hash(intent_raw), content_sha256=_hash(required_raw),
        content_bytes=len(required_raw), root_id=view.root_record_id, pages=pages,
        local_budget=16, global_budget=4160))


def validate_learner_assessment_v2(raw, required_raw, intent_raw, chess_fixture_raw, game_set_raw):
    manifest.validate_canonical_manifest(raw)
    _require(raw == build_learner_assessment_v2(required_raw, intent_raw, chess_fixture_raw, game_set_raw),
             'evaluation-binding')
