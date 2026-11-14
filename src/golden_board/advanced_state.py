"""Exact R1–R7/F1/F2 author-time witnesses; never a Player dependency."""
from copy import deepcopy
import chess
from .authoring import occupancy
from .practical_state import coherent,history,evaluate,observe,_key
from .practical_cases import move as request_move
from .rehearsal_predicates import occupied_relations,material_inventory,_board
from .source_game import cell_index

def square(cell):
    if type(cell) is not int or not 0<=cell<64:raise ValueError('A binary-board cell is required.')
    return chess.square(cell%8,7-cell//8)

def _ray(a,b):
    """Strictly intervening squares, or None for a non-slider direction."""
    ax,ay=chess.square_file(a),chess.square_rank(a);bx,by=chess.square_file(b),chess.square_rank(b)
    dx,dy=bx-ax,by-ay
    if (not dx and not dy) or (dx and dy and abs(dx)!=abs(dy)):return None
    sx=(dx>0)-(dx<0);sy=(dy>0)-(dy<0);distance=max(abs(dx),abs(dy))
    return [chess.square(ax+i*sx,ay+i*sy) for i in range(1,distance)]

def relations(board,source):
    _board(board);s=square(source);piece=board.piece_at(s)
    if piece is None:raise ValueError('The selected relation source must be occupied.')
    r=occupied_relations(board,s);pins=[];king=board.king(piece.color)
    for target,pinner in board.piece_map().items():
        if pinner.color==piece.color or pinner.piece_type not in (chess.BISHOP,chess.ROOK,chess.QUEEN):continue
        ray=_ray(king,target)
        if ray is None or s not in ray:continue
        diagonal=chess.square_file(king)!=chess.square_file(target) and chess.square_rank(king)!=chess.square_rank(target)
        if pinner.piece_type!=(chess.BISHOP if diagonal else chess.ROOK) and pinner.piece_type!=chess.QUEEN:continue
        if [v for v in ray if board.piece_at(v)]==[s]:pins.append([cell_index(king),source,cell_index(target)])
    attacked=sorted(map(cell_index,r['attacked']));defended=sorted(map(cell_index,r['defended']))
    return {'attacked':attacked,'defended':defended,'pins':sorted(pins),'fork':len(attacked)>=2,
        'pairs':[[source,target] for target in attacked],
        'scope':'Local geometric relation; no history, legal-capture or profit assertion.'}

def file_facts(board,side,file,pawn=None):
    _board(board)
    if type(side) is not int or side not in (0,1) or type(file) is not int or not 0<=file<8:raise ValueError('Side/file outside finite domain.')
    color=side==0;own=sorted(cell_index(s) for s in board.pieces(chess.PAWN,color) if chess.square_file(s)==file)
    enemy=sorted(cell_index(s) for s in board.pieces(chess.PAWN,not color) if chess.square_file(s)==file)
    exclusions=[]
    if pawn is not None:
        s=square(pawn)
        if board.piece_at(s)!=chess.Piece(chess.PAWN,color):raise ValueError('Select a pawn of the declared side.')
        direction=1 if color else -1
        exclusions=sorted(cell_index(t) for t in board.pieces(chess.PAWN,not color)
            if abs(chess.square_file(t)-chess.square_file(s))<=1 and direction*(chess.square_rank(t)-chess.square_rank(s))>0)
    return {'own_file_pawns':own,'enemy_file_pawns':enemy,'open':not own and not enemy,
        'semiopen':not own and bool(enemy),'opposing_exclusions':exclusions,
        'passed':None if pawn is None else not exclusions}

def discovered(prefix,text):
    replay,_=coherent(prefix);before=chess.Board(replay.fen);effect=evaluate(request_move(prefix,text))
    pairs=[];checks=[]
    if effect['accepted']:
        m=chess.Move.from_uci(text);after=before.copy();after.push(m);side=before.turn
        for s,p in before.piece_map().items():
            if p.color!=side or s==m.from_square or p.piece_type not in (chess.BISHOP,chess.ROOK,chess.QUEEN) or after.piece_at(s)!=p:continue
            for target,t in before.piece_map().items():
                if t.color==side or after.piece_at(target)!=t:continue
                ray=_ray(s,target)
                if ray is None or m.from_square not in ray:continue
                if target not in before.attacks(s) and target in after.attacks(s):
                    pair=[cell_index(s),cell_index(target)];pairs.append(pair)
                    if t.piece_type==chess.KING:checks.append(pair)
    return {'effect':effect,'pairs':sorted(pairs),'checks':sorted(checks)}

def escape(prefix,text):
    replay,_=coherent(prefix);board=chess.Board(replay.fen);m=chess.Move.from_uci(text)
    if board.piece_at(m.from_square)!=chess.Piece(chess.KING,board.turn):raise ValueError('Select the active king.')
    return {'effect':evaluate(request_move(prefix,text)),
            'premove_attacked':board.is_attacked_by(not board.turn,m.to_square)}

def scheduled(prefix,moves):
    replay,states=coherent(prefix);keys=[s['key'] for s in states];frames=[states[-1]];first=None
    texts=moves.split() if isinstance(moves,str) else list(moves)
    for i,text in enumerate(texts,1):
        side=replay.side_to_move;replay.play(text);keys.append(_key(chess.Board(replay.fen)))
        frames.append(observe(replay,keys))
        if len(text)==5 and first is None:first={'side':side,'ply':i,'choice':'qrbn'.index(text[4])+1}
    return {'moves':texts,'states':frames,'first_promotion':first,'forced':None,
            'scope':'Only this complete shown legal schedule; no forced outcome assertion.'}

def proof(prefix,winner,tree):
    if type(winner) is not int or winner not in (0,1):raise ValueError('Winning side must be0/1.')
    replay,states=coherent(prefix);nodes=[];errors=[];active=set()
    def visit(state,keys,node,parent=None,via=None):
        if not isinstance(node,dict) or set(node)-{'children'}:raise ValueError('A finite node has only an explicit children mapping.')
        if id(node) in active:raise ValueError('Cyclic proof is not finite.')
        children=node.get('children',{})
        if not isinstance(children,dict):raise ValueError('Children must name explicit actions.')
        active.add(id(node));ident=len(nodes);closed=state.closed
        role='leaf' if closed else 'attacker' if state.side_to_move==winner else 'defender'
        domain=list(state.legal_moves)+['claim:'+c for c in state.available_claims]
        row={'id':ident,'parent':parent,'via':via,'role':role,'state':observe(state,keys),
            'domain':domain,'claims':list(state.available_claims),'children':[],
            'resignation_dominated':role=='defender','agreement_compellable':False}
        nodes.append(row)
        if closed:
            if state.outcome.score!=winner:errors.append('nonwinning-leaf')
            if children:errors.append('postgame-child')
        elif not children:
            errors.append('active-leaf')
            if role=='defender':errors.append('missing-defender-reply')
        if role=='defender' and set(children)!=set(domain):errors.append('missing-defender-reply' if set(domain)-set(children) else 'invalid-reply')
        for action,child in children.items():
            if action not in domain:
                errors.append('invalid-action');continue
            target=deepcopy(state)
            if action.startswith('claim:'):target.claim_draw(target.side_to_move,action[6:])
            else:target.play(action)
            targetkeys=keys+([_key(chess.Board(target.fen))] if not action.startswith('claim:') else [])
            child_id=visit(target,targetkeys,child,ident,action);row['children'].append(child_id)
        active.remove(id(node));return ident
    visit(replay,[s['key'] for s in states],tree)
    return {'available':not errors,'winning':True if not errors else None,'winner':winner,
        'nodes':nodes,'errors':sorted(set(errors)),
        'scope':'This finite authored certificate only; unavailable is not a losing-position verdict.'}

def guidance(prefix):
    replay,states=coherent(prefix);board=chess.Board(replay.fen)
    original={s:s for s in (chess.B1,chess.C1,chess.F1,chess.G1,chess.B8,chess.C8,chess.F8,chess.G8)};departed=set()
    for text in prefix.split():
        m=chess.Move.from_uci(text)
        for identity,location in list(original.items()):
            if location==m.to_square:original[identity]=None
            elif location==m.from_square:original[identity]=m.to_square;departed.add(identity)
    center=[chess.D4,chess.E4,chess.D5,chess.E5];control=[]
    for side in (True,False):
        control.append(sorted(cell_index(s) for s in set().union(*(set(board.attacks(o)) for o,p in board.piece_map().items() if p.color==side))))
    return {'material':material_inventory(board),'minor_locations':{cell_index(k):None if v is None else cell_index(v) for k,v in original.items()},
        'departed':sorted(map(cell_index,departed)),'center_occupancy':[[cell_index(s),occupancy(board)[cell_index(s)]] for s in center],
        'center_control':[[cell_index(s) for s in center if cell_index(s) in cells] for cells in control],
        'control':control,'legal':list(replay.legal_moves),'check':board.is_check(),
        'king_routes':[m for m in replay.legal_moves if board.piece_type_at(chess.Move.from_uci(m).from_square)==chess.KING],
        'advantage':None,'best_move':None,'state':states[-1]}
