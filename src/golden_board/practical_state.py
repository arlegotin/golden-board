"""Author-time C1–C7 witnesses. Nothing here is shipped as a recipient evaluator."""
from functools import lru_cache
from copy import deepcopy
import chess

from .authoring import occupancy
from .rules import Replay, local_deadness
from .source_game import cell_index

PROMOTION={'':0,'q':1,'r':2,'b':3,'n':4}
REASONS=(None,'checkmate','stalemate','common-dead','threefold','fifty-move','resignation','agreement')

def move_row(text):
    """Explicit zero-based row/column quadruple and separate promotion choice."""
    if text[4:] not in PROMOTION:raise ValueError('Invalid explicit promotion choice.')
    move=chess.Move.from_uci(text)
    a,b=cell_index(move.from_square),cell_index(move.to_square)
    return [a//8,a%8,b//8,b%8,PROMOTION[text[4:]]]

def _key(board):
    rights=[bool(board.castling_rights & chess.BB_SQUARES[s]) for s in (chess.H1,chess.A1,chess.H8,chess.A8)]
    return {'occupancy':occupancy(board),'side':0 if board.turn else 1,'rights':rights,
            'ep':cell_index(board.ep_square) if board.has_legal_en_passant() else None}

def observe(replay,keys):
    board=chess.Board(replay.fen);key=_key(board)
    matches=[i for i,k in enumerate(keys) if k==key]
    if len(matches)!=replay.repetition_count:raise ValueError('History/key count disagreement.')
    return {'occupancy':occupancy(board),'side':replay.side_to_move,'rights':key['rights'],
        'ep':cell_index(board.ep_square) if board.ep_square is not None else None,
        'key_ep':key['ep'],'clock':replay.halfmove_clock,'repeat':replay.repetition_count,
        'check':board.is_check(),'legal':list(replay.legal_moves),
        'eligible':[v in replay.available_claims for v in ('threefold','fifty-move')],
        'closed':replay.closed,'reason':replay.outcome.reason if replay.outcome else None,
        'score':replay.outcome.score if replay.outcome else None,'key':key,'occurrences':matches}

def coherent(prefix):
    """Fresh Replay plus every state; source always starts at the standard setup."""
    replay=Replay();keys=[_key(chess.Board(replay.fen))];states=[observe(replay,keys)]
    for text in prefix.split():
        replay.play(text);keys.append(_key(chess.Board(replay.fen)));states.append(observe(replay,keys))
    return replay,states

def castle_probes(replay,text):
    """Explicit hypothetical origin, king-only transit, both-moved destination."""
    try:move=chess.Move.from_uci(text)
    except ValueError:return []
    board=chess.Board(replay.fen);origin=move.from_square;target=move.to_square
    if origin not in (chess.E1,chess.E8) or target-origin not in (-2,2):return []
    king=board.piece_at(origin)
    if king is None or king.piece_type!=chess.KING:return []
    direction=1 if target>origin else -1
    rook_origin=origin+(3 if direction==1 else -4);rook_target=origin+direction
    rook=board.piece_at(rook_origin)
    if rook!=chess.Piece(chess.ROOK,king.color):return []
    stages=[board.copy(stack=False)]
    transit=board.copy(stack=False);transit.remove_piece_at(origin);transit.set_piece_at(origin+direction,king);stages.append(transit)
    final=board.copy(stack=False);final.remove_piece_at(origin);final.remove_piece_at(rook_origin)
    final.set_piece_at(target,king);final.set_piece_at(rook_target,rook);stages.append(final)
    result=[]
    for stage,(position,square) in enumerate(zip(stages,(origin,origin+direction,target))):
        controls=set()
        for source,piece in position.piece_map().items():
            if piece.color!=king.color:controls.update(position.attacks(source))
        result.append({'stage':stage,'occupancy':occupancy(position),'king':cell_index(square),
            'attackers':sorted(cell_index(s) for s in position.attackers(not king.color,square)),
            'enemy_control':sorted(cell_index(s) for s in controls),
            'type':'hypothetical_castle_occupancy'})
    return result

@lru_cache(maxsize=512)
def _history(prefix):
    # Immutable-by-custody cache: caller receives copies, never the cached Replay.
    return coherent(prefix)[1]

def history(prefix):return deepcopy(_history(prefix))

def evaluate(spec):
    op=spec['op']
    if op=='material':
        return {'type':'local_material','occupancy':occupancy(chess.Board(spec['fen'])),
                'classification':local_deadness(spec['fen'])}
    prefix=spec.get('prefix','');replay,states=coherent(prefix);before=states[-1]
    result={'type':'coherent_replay','before':before,'after':before,'accepted':True}
    if op=='observe':return result
    if op=='compare':
        other=history(spec['other'])[-1];result.update(after=other,equal_key=before['key']==other['key'])
        return result
    if op=='record':
        length,ply,score=spec['length'],spec['ply'],spec['score']
        if type(length) is not int or length<0 or type(ply) is not int or ply<0 or type(score) is not int or score not in (0,1,2):
            raise ValueError('Invalid finite record domain.')
        complete=length==len(replay.moves)
        if replay.outcome and replay.outcome.score!=score:raise ValueError('Record score conflicts with board ending.')
        result.update(type='authored_record',before=states[0],complete=complete,accepted=complete and ply<=length,
            after=states[ply] if complete and ply<=length else None,
            record_score=score,record_cause='unspecified',length=length,available=len(replay.moves),ply=ply)
        return result
    if op!='attempt':raise ValueError('Unknown practical operation.')
    kind=spec['kind'];keys=[s['key'] for s in states]
    if kind=='move':
        result['castle_probes']=castle_probes(replay,spec['move'])
        board=chess.Board(replay.fen)
        try:move=chess.Move.from_uci(spec['move'])
        except ValueError:move=None
        if move is not None and board.is_pseudo_legal(move) and not replay.closed:
            mover=board.turn;board.push(move);king=board.king(mover)
            result['move_probe']={'type':'hypothetical_move_occupancy','occupancy':occupancy(board),
                'king':cell_index(king),'king_attacked':board.is_attacked_by(not mover,king),
                'attackers':sorted(cell_index(s) for s in board.attackers(not mover,king)),
                'new_piece_control':sorted(cell_index(s) for s in board.attacks(move.to_square))}
    try:
        if kind=='move':replay.play(spec['move']);keys.append(_key(chess.Board(replay.fen)))
        elif kind=='claim':replay.claim_draw(spec['actor'],spec['reason'])
        elif kind=='resign':replay.resign(spec['actor'])
        elif kind=='agree':replay.agree_draw(spec['consents'])
        else:raise ValueError('Unknown event kind.')
    except ValueError:
        result['accepted']=False
        if observe(replay,keys)!=before:raise ValueError('Rejected practical event mutated state.')
    result['after']=observe(replay,keys)
    return result
