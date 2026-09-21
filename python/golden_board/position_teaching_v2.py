"""Source-extracted finite Position/Move16 teaching; no carrier admission.

The exact 408-byte suffix is owned by spec/position-teaching-v2.md.
"""
from dataclasses import dataclass
from hashlib import sha256

from . import chess, constants, content
from .m2_slice import SliceCompilation


@dataclass(frozen=True, slots=True)
class PositionTeachingV2:
    value: bytes


def _require(condition, reason):
    if not condition:
        raise ValueError('position_teaching_v2.' + reason)


def _u16(values):
    return b''.join(value.to_bytes(2,'big') for value in values)


def _layout(rows):
    return _u16((len(rows),)) + _u16(value for row in rows for value in row)


def _project(raw, digest, expected):
    _require(type(raw) is bytes and 4 <= len(raw) <= 524288, 'stream.bound')
    _require(type(digest) is str and sha256(raw).hexdigest() == digest, 'stream.digest')
    actual = content.projection_view(content.stream_validation(raw))
    _require(actual == expected, 'stream.projection')
    return {record.record_id:record.payload for record in actual.records}


def _subject(compiled, records, sid, namespace, code, raw, expected_ids):
    _require(type(raw) is bytes and 1 <= len(raw) <= 16384, 'subject.bound')
    selected = tuple(row for row in compiled.atomic_assignments if row.section_id == sid)
    _require(len(selected) == 1 and selected[0].record_ids == expected_ids, 'subject.assignment')
    binding_id,opaque_id = expected_ids
    binding,opaque = records.get(binding_id),records.get(opaque_id)
    _require(type(binding) is content.ContentSemanticBinding and
             (binding.binding_class,binding.namespace_id,binding.semantic_code,
              binding.argument,binding.auxiliary) == (1,namespace,code,1,len(raw)), 'subject.binding')
    _require(type(opaque) is content.ContentOpaqueData and opaque.data_binding_ref == binding_id
             and bytes(opaque.data) == raw, 'subject.opaque')
    return raw


def _fixture_parts(raw, expected_kind):
    _require(type(raw) is bytes and 8 <= len(raw) <= 16384 and raw[:2] == bytes((0,expected_kind)), 'fixture.header')
    prior_length = int.from_bytes(raw[2:4],'big')
    _require(prior_length <= 8192 and prior_length % 2 == 0 and 4+prior_length+2 <= len(raw), 'fixture.prior')
    prior = raw[4:4+prior_length]
    subject_at = 4+prior_length
    subject_length = int.from_bytes(raw[subject_at:subject_at+2],'big')
    _require(subject_length == 2 and subject_at+2+subject_length+2 <= len(raw), 'fixture.subject')
    subject = raw[subject_at+2:subject_at+2+subject_length]
    expected_at = subject_at+2+subject_length
    expected_length = int.from_bytes(raw[expected_at:expected_at+2],'big')
    _require(expected_length >= 1 and expected_at+2+expected_length == len(raw), 'fixture.eof')
    return prior,subject,expected_at+2,raw[expected_at+2:]


def _moves(raw):
    _require(type(raw) is bytes and len(raw) <= 8192 and len(raw) % 2 == 0, 'moves.bound')
    return tuple(chess.decode_move(raw[i:i+2]) for i in range(0,len(raw),2))


def _position(raw):
    _require(chess.encode_position(chess.decode_position(raw)) == raw, 'position.roundtrip')
    return raw


def build_position_teaching_v2(compiled: SliceCompilation) -> PositionTeachingV2:
    """Rebuild from checked source records and public chess consequences."""
    _require(type(compiled) is SliceCompilation, 'compiled.type')
    required = _project(compiled.required_content_bytes,compiled.required_content_sha256,compiled.required_projection)
    all_records = _project(compiled.content_bytes,compiled.content_sha256,compiled.projection)
    _require(type(compiled.atomic_assignments) is tuple and len(compiled.atomic_assignments) <= 4095, 'assignments.bound')
    _require(type(compiled.game_payloads) is tuple and len(compiled.game_payloads) == 64
             and type(compiled.fixture_payloads) is tuple and len(compiled.fixture_payloads) == 10, 'subjects.count')
    game = _subject(compiled,all_records,100,2,1,compiled.game_payloads[0],(588,589))
    _require(len(game) == 69 and int.from_bytes(game[:2],'big') == 33 and game[-1] == 0, 'game.shape')
    game_moves = _moves(game[2:-1])
    _require(len(game_moves) == 33 and game[2:4] == bytes.fromhex('31c0'), 'game.example')
    chess.validate_source_record(game_moves,game[-1])

    matrix = required.get(43)
    _require(type(matrix) is content.ContentMatrix and (matrix.atom_schema_ref,matrix.rows,matrix.columns) == (1,20,27), 'matrix.shape')
    extraction = tuple(((7-rank)*matrix.columns+15,8*rank,8) for rank in range(8)) + ((9*matrix.columns+15,64,3),)
    position = bytearray(67)
    for source,target,count in extraction:
        position[target:target+count] = bytes(matrix.cells[source:source+count])
    first_position = _position(bytes(position))
    replayed = chess.encode_position(chess.replay_from_start(game_moves[:1]).position)
    _require(first_position == replayed and first_position[-3:] == bytes((1,15,21)), 'matrix.replay')
    _require(matrix.cells[25:27] == (21,20), 'matrix.target_relation')

    packet = _subject(compiled,all_records,200,3,1,compiled.fixture_payloads[0],(716,717))
    prior,subject,expected_start,tagged = _fixture_parts(packet,1)
    _require(len(packet) == 90 and len(prior) == 12 and subject == bytes.fromhex('1060')
             and expected_start == 22 and len(tagged) == 68 and tagged[0] == 1, 'fixture.example')
    fixture_position = _position(tagged[1:])
    fixture_state = chess.apply_move(chess.replay_from_start(_moves(prior)),chess.decode_move(subject))
    _require(fixture_position == chess.encode_position(fixture_state.position), 'fixture.replay')

    promotions = []
    promotion_prior = None
    for ordinal in range(3,7):
        binding = 716+2*ordinal
        packet = _subject(compiled,all_records,200+ordinal,3,ordinal+1,
            compiled.fixture_payloads[ordinal],(binding,binding+1))
        prior,subject,_,_ = _fixture_parts(packet,ordinal+1)
        _require(len(prior) == 16 and (promotion_prior is None or prior == promotion_prior), 'promotion.prior')
        promotion_prior = prior
        promotions.append(subject)
    _require(tuple(promotions) == tuple((0xc792+2*i).to_bytes(2,'big') for i in range(4)), 'promotion.subjects')
    base = int.from_bytes(promotions[0],'big') & ~14
    first_move = game_moves[0]
    wires = tuple(base | p << 1 for p in range(8)) + (
        int.from_bytes(game[6:8],'big'),int.from_bytes(game[8:10],'big'),
        int.from_bytes(game[2:4],'big') | 1, first_move.origin << 10 | first_move.origin << 4)
    _require(wires == (*range(0xc790,0xc7a0,2),0x1950,0xe6a0,0x31c1,0x30c0), 'move.examples')
    move_rows = bytearray(_u16((len(wires),)))
    for wire in wires:
        origin,destination,promotion = wire >> 10,(wire >> 4) & 63,(wire >> 1) & 7
        try:
            move = chess.decode_move(wire.to_bytes(2,'big'))
        except chess.ChessReject:
            admitted = 0
        else:
            admitted = 1
            _require((move.origin,move.destination,move.promotion) == (origin,destination,promotion)
                     and chess.encode_move(move) == wire.to_bytes(2,'big'), 'move.roundtrip')
        expected = int(promotion <= 4 and not wire & 1 and origin != destination)
        _require(admitted == expected, 'move.admission')
        move_rows.extend(_u16((wire,))+bytes((origin,destination,promotion,admitted)))
    promotion_state = chess.replay_from_start(_moves(promotion_prior))
    try:
        chess.apply_move(promotion_state,chess.decode_move(base.to_bytes(2,'big')))
    except chess.ChessReject as rejected:
        _require(rejected.code == constants.CHESS_MOVE_PROMOTION_MISSING, 'promotion.rejection')
    else:
        raise ValueError('position_teaching_v2.missing_promotion')
    chess.apply_move(promotion_state,chess.decode_move(promotions[0]))

    result = b''.join((
        _u16((2,)),_layout(((0,64),(64,1),(65,1),(66,1))),_u16((0,43,67)),
        _u16((len(extraction),))+_u16(v for row in extraction for v in row),first_position,
        _u16((1,717,22,68,23,67)),tagged,fixture_position,
        _layout(((10,6),(4,6),(1,3),(0,1))),bytes(move_rows),
        _u16((1,589,len(game))),_layout(((0,2),(2,2*len(game_moves)),(len(game)-1,1))),
    ))
    _require(len(result) == 408, 'value.length')
    return PositionTeachingV2(result)
