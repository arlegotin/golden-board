"""Only the local exact R1/R5/R6 operations consumed by real rehearsal cases.

Authoring-time subject logic. No runtime Player or carrier dependency.
"""
import chess


def _board(board):
    if not isinstance(board,chess.Board) or board.chess960 or not board.is_valid():
        raise ValueError('A structurally valid orthodox local board is required; no history is asserted.')


def occupied_relations(board,source):
    _board(board)
    if type(source) is not int or not 0<=source<64 or board.piece_at(source) is None:
        raise ValueError('An occupied source square is required.')
    side=board.color_at(source)
    targets={square for square in board.attacks(source) if board.piece_at(square)}
    return {'attacked':{s for s in targets if board.color_at(s)!=side},
            'defended':{s for s in targets if board.color_at(s)==side}}


def passed_pawns(board,side):
    _board(board)
    if type(side) is not bool:raise ValueError('A chess side is required.')
    enemies=board.pieces(chess.PAWN,not side)
    direction=1 if side else -1
    return {p for p in board.pieces(chess.PAWN,side) if not any(
        abs(chess.square_file(q)-chess.square_file(p))<=1 and
        direction*(chess.square_rank(q)-chess.square_rank(p))>0 for q in enemies)}


def material_inventory(board):
    _board(board)
    counts=[[len(board.pieces(kind,side)) for kind in range(1,7)] for side in (True,False)]
    scale=[1,3,3,5,9,None]
    totals=[sum(count*value for count,value in zip(row,scale) if value is not None) for row in counts]
    return {'counts':counts,'scale':scale,'totals':totals}
