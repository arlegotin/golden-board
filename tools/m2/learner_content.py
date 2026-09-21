"""Bounded, owner-only authoring for the revised M2 representation slice.

The presenter receives numeric matrices and generic response regions only.
English identifiers and evidence stay in owner tooling. Every true position
comes from the public chess oracle. Rejected diagrams are mechanically complete
hypotheticals, and are never passed off as legally reachable positions.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

SEPARATOR = 255
OCCUPANCY_RELATION = 253
CONTROL_RELATION = 254
LOCATION_RELATION = 252
TARGET_RELATION = 251
RIGHTS_RELATION = 250
REPEAT_RELATION = 249
COUNT_RELATION = 248
CLAIM_RELATION = 247
CONTINUE_RELATION = 246
RECORD_RELATION = 245
MAX_GAME_SET_BYTES = 327677
MAX_PAGES = 96


def _matrix(rows, columns, cells):
    cells = list(cells)
    if len(cells) != rows * columns or not all(type(c) is int and 0 <= c <= 255 for c in cells):
        raise ValueError('invalid authored matrix')
    return {'rows': rows, 'columns': columns, 'cells': cells}


def _board(raw):
    if len(raw) != 67:
        raise ValueError('position length')
    cells = [raw[rank*8+file] for rank in range(7,-1,-1) for file in range(8)]
    return _matrix(10,8,cells+[SEPARATOR]*8+list(raw[64:])+[SEPARATOR]*5)


def _mask(values):
    if len(values) != 64:
        raise ValueError('mask length')
    return _matrix(8,8,[values[rank*8+file] for rank in range(7,-1,-1) for file in range(8)])


def _choices(panels):
    height=max(p['rows'] for p in panels)
    width=sum(p['columns'] for p in panels)+len(panels)-1
    cells=[SEPARATOR]*(height*width)
    regions=[]
    offset=0
    for i,panel in enumerate(panels,1):
        for row in range(panel['rows']):
            start=row*width+offset
            cells[start:start+panel['columns']]=panel['cells'][row*panel['columns']:(row+1)*panel['columns']]
        regions.append({'id':i,'row_start':0,'row_end':panel['rows'],
                        'column_start':offset,'column_end':offset+panel['columns']})
        offset+=panel['columns']+1
    return _matrix(height,width,cells),regions


def _uci(value):
    """Pack an owner-readable coordinate, without implementing chess movement."""
    a=ord(value[0])-97+8*(int(value[1])-1)
    b=ord(value[2])-97+8*(int(value[3])-1)
    promotion={'q':1,'r':2,'b':3,'n':4}.get(value[4:],0)
    return ((a<<10)|(b<<4)|(promotion<<1)).to_bytes(2,'big').hex()


def _line(text):
    return ''.join(_uci(token) for token in text.split())


def _canonical_games(raw):
    """Bounded source-v0 framing of the exactly-64 anthology, not a PGN parser.

    The source owner validates anthology identity and complete record semantics.
    Here every slice/count/score/order bound is checked before selecting ordinal
    zero; that selected record is additionally replayed through the chess API.
    """
    if type(raw) is not bytes or not 2 <= len(raw) <= MAX_GAME_SET_BYTES or raw[:2] != b'\0@':
        raise ValueError('expected bounded 64-game anthology')
    offset=2
    total=0
    games=[]
    for _ in range(64):
        if offset+2 > len(raw):
            raise ValueError('truncated game count')
        count=int.from_bytes(raw[offset:offset+2],'big')
        total+=count
        if not 1 <= count <= 4096 or total > 65535:
            raise ValueError('game-set ply bound')
        end=offset+3+2*count
        if end > len(raw):
            raise ValueError('truncated game')
        game=raw[offset:end]
        if game[-1] not in (0,1,2):
            raise ValueError('game score code')
        if games and games[-1] >= game:
            raise ValueError('game-set order or duplicate')
        games.append(game)
        offset=end
    if offset != len(raw):
        raise ValueError('game-set trailing bytes')
    return tuple(games)


def _proposed(before, move):
    """Draw a rejected request, including its requested special displacement.

    This is a diagram operation, never a legality or reachability decision.
    Its output is explicitly marked proposed_hex rather than after_hex.
    """
    raw=bytearray(before)
    origin,destination=move.origin,move.destination
    code=before[origin]
    kind=(code-1)%6+1 if code else 0
    side=(code-1)//6 if code else before[64]
    raw[origin]=0
    raw[destination]=code
    raw[64]^=1
    raw[66]=0
    if kind == 1:
        if (before[destination] == 0 and before[66] == destination+1
                and abs(origin%8-destination%8) == 1):
            raw[(origin//8)*8+destination%8]=0
        if origin%8 == destination%8 and abs(origin//8-destination//8) == 2:
            raw[66]=(origin+destination)//2+1
        if move.promotion:
            raw[destination]=6*side+{1:5,2:4,3:3,4:2}[move.promotion]
    if kind == 6:
        raw[65]&=12 if side == 0 else 3
        castle={(4,6):(7,5),(4,2):(0,3),(60,62):(63,61),(60,58):(56,59)}.get((origin,destination))
        if castle:
            rook_origin,rook_destination=castle
            raw[rook_origin]=0
            raw[rook_destination]=before[rook_origin]
    for square,bit,rook in ((7,1,4),(0,2,4),(63,4,10),(56,8,10)):
        if (origin == square and code == rook) or (destination == square and before[square] == rook):
            raw[65]&=15^bit
    return bytes(raw)


def build_cases(root: Path) -> list[dict]:
    from golden_board import chess

    root=Path(root).resolve()
    fixture_path=root/'conformance/chess-v0.json'
    with fixture_path.open('rb') as stream:
        fixture_bytes=stream.read(2_097_153)
    if len(fixture_bytes) > 2_097_152:
        raise ValueError('fixture byte bound')
    fixtures={c['name']:c for c in json.loads(fixture_bytes)['cases']}
    game_path='reports/game-set-v0.bin'
    with (root/game_path).open('rb') as stream:
        game_set=stream.read(MAX_GAME_SET_BYTES+1)
    game=_canonical_games(game_set)[0]
    game_moves=game[2:-1].hex()

    def moves(encoded):
        if len(encoded)%4 or len(encoded)>4096*4:
            raise ValueError('history bound')
        raw=bytes.fromhex(encoded)
        return tuple(chess.decode_move(raw[i:i+2]) for i in range(0,len(raw),2))

    chess.validate_source_record(moves(game_moves),game[-1])

    @lru_cache(maxsize=256)
    def state(prefix):
        return chess.replay_from_start(moves(prefix))

    def position(prefix):
        return chess.encode_position(state(prefix).position)

    def claim(prefix):
        return chess.evaluate_predicate(b'chess.history_claim',chess.HistoryClaimInput(state(prefix)))

    pages=[]

    def page(identifier,family,phase,panels,options,accepted,evidence):
        last,regions=_choices(options)
        answer=tuple(i+1 for i,valid in enumerate(accepted) if valid)
        if not answer or len(pages) >= MAX_PAGES:
            raise ValueError('page answer or bound')
        result={'id':identifier,'family':family,'phase':phase,'panels':panels+[last],
                'regions':regions,'correct':answer,'evidence':evidence}
        pages.append(result)
        return result

    def transition(identifier,family,phase,prefix,option_moves,source='authored reachable history',expected=None):
        replay=state(prefix)
        before=position(prefix)
        options,facts,valid=[],[],[]
        for i,encoded in enumerate(option_moves,1):
            move=chess.decode_move(bytes.fromhex(encoded))
            fact={'region_id':i,'move_hex':encoded}
            try:
                after=chess.apply_move(replay,move)
            except chess.ChessReject as error:
                proposed=_proposed(before,move)
                fact.update(legal=False,rejection=error.code,proposed_hex=proposed.hex())
                options.append(_board(proposed))
                valid.append(False)
            else:
                raw=chess.encode_position(after.position)
                fact.update(legal=True,after_hex=raw.hex())
                options.append(_board(raw))
                valid.append(True)
            facts.append(fact)
        if expected is not None and valid != expected:
            raise ValueError((identifier,valid,expected))
        if len({tuple(p['cells']) for p in options}) != len(options):
            raise ValueError('indistinguishable options: '+identifier)
        return page(identifier,family,phase,[_board(before)],options,valid,
                    {'kind':'transition','source':source,'prefix_hex':prefix,
                     'before_hex':before.hex(),'options':facts})

    def fixture(identifier,family,phase,name,alternate,reverse=False):
        f=fixtures[name]
        prefix=f['input']['moves_hex']
        target=f['input']['move_hex']
        target_valid='success' in f['expected']
        sequence=[target,_uci(alternate)]
        expected=[target_valid,not target_valid]
        if reverse:
            sequence.reverse();expected.reverse()
        p=transition(identifier,family,phase,prefix,sequence,'conformance/chess-v0.json#'+name,expected)
        fact=next(o for o in p['evidence']['options'] if o['move_hex'] == target)
        if target_valid:
            if fact['after_hex'] != f['expected']['success']['position_hex']:
                raise ValueError('fixture result disagreement: '+name)
        else:
            if fact['rejection'] != f['expected']['rejection']:
                raise ValueError('fixture rejection disagreement: '+name)
        return p

    def storyboard(prefix,start=0):
        """Carry every consecutive ply in the declared, explicitly numbered span."""
        if start%4 or not 0 <= start <= len(prefix) <= 256:
            raise ValueError('storyboard span bound')
        prefixes=[prefix[:n] for n in range(start,len(prefix)+1,4)]
        width=26
        height=((len(prefixes)+2)//3)*12-1
        cells=[SEPARATOR]*(height*width)
        frames=[]
        for i,p in enumerate(prefixes):
            raw=position(p)
            row=(i//3)*12
            column=(i%3)*9
            cells[row*width+column]=len(p)//4
            board=_board(raw)
            for local in range(10):
                at=(row+1+local)*width+column
                cells[at:at+8]=board['cells'][local*8:(local+1)*8]
            frames.append({'prefix_hex':p,'position_hex':raw.hex(),
                           'ordinal_row':row,'row_start':row+1,'column_start':column})
        return _matrix(height,width,cells),frames

    def occupancy(identifier,phase,prefix,side=None,reverse=False):
        replay=state(prefix)
        if side is None:
            values=[int(chess.evaluate_predicate(b'chess.occupancy',chess.OccupancyInput(
                replay.position,sq,chess.OccupancyMatch('occupied')))) for sq in range(64)]
        else:
            values=[int(any(chess.evaluate_predicate(b'chess.occupancy',chess.OccupancyInput(
                replay.position,sq,chess.OccupancyMatch('exact',side,piece))) for piece in range(1,7))) for sq in range(64)]
        options=[_mask(values),_mask([1-v for v in values])]
        accepted=[True,False]
        if reverse:options.reverse();accepted.reverse()
        panels=[_matrix(1,1,[OCCUPANCY_RELATION])]
        if side is not None:panels.append(_matrix(1,6,range(1+6*side,7+6*side)))
        panels.append(_board(position(prefix)))
        return page(identifier,'grid',phase,panels,options,accepted,
                    {'kind':'occupancy','relation_badge':OCCUPANCY_RELATION,'prefix_hex':prefix,'side':side,'mask':values})

    def control(identifier,phase,prefix,side,reverse=False):
        replay=state(prefix)
        mask=[int(bool(chess.controls_square(replay.position,side,sq))) for sq in range(64)]
        legal={m.destination for m in chess.legal_moves(replay)}
        legal_mask=[int(sq in legal) for sq in range(64)]
        if mask == legal_mask:
            raise ValueError('control alternatives do not discriminate')
        options=[_mask(mask),_mask(legal_mask)];accepted=[True,False]
        if reverse:options.reverse();accepted.reverse()
        return page(identifier,'attack',phase,[_matrix(1,1,[CONTROL_RELATION]),
                    _matrix(1,6,range(1+6*side,7+6*side)),_board(position(prefix))],options,accepted,
                    {'kind':'control','relation_badge':CONTROL_RELATION,'prefix_hex':prefix,'side':side,
                     'control_mask':mask,'legal_destination_mask':legal_mask})

    # Generic mechanics precede every chess-shaped panel. Selection 1 is
    # explicitly cleared, then the matching region 2 is selected and committed.
    mechanic=page('mechanics-reset-reselect','mechanics','teach',[_matrix(2,3,[1,0,0,0,1,1])],
                 [_matrix(2,3,[0,1,1,1,0,0]),_matrix(2,3,[1,0,0,0,1,1])],[False,True],
                 {'kind':'mechanics','relation':'exact numeric-matrix match'})
    mechanic['passive_actions']=['01000001','02000000','01000002','03000000']

    # Addresses are established before any Position footer or state-field use.
    page('locations-oriented-grid','locations','teach',[_matrix(1,1,[LOCATION_RELATION]),_mask(list(range(64))),
         _matrix(1,4,[0,7,56,63])],[_mask([int(s in (0,7,56,63)) for s in range(64)]),
         _mask([int(s in (8,15,48,55)) for s in range(64)])],[True,False],
         {'kind':'locations','squares':[0,7,56,63]})
    page('locations-single-square','locations','teach',[_matrix(1,1,[LOCATION_RELATION]),_mask(list(range(64))),
         _matrix(1,1,[20])],[_mask([int(s == 21) for s in range(64)]),
         _mask([int(s == 20) for s in range(64)])],[False,True],{'kind':'locations','squares':[20]})

    def target(identifier,prefix,before_prefix=None,reverse=False):
        raw=position(prefix)
        code=raw[66]
        values=[int(code != 0 and sq == code-1) for sq in range(64)]
        wrong=[int(sq == code) for sq in range(64)]
        panels=[_matrix(1,3,[SEPARATOR,SEPARATOR,TARGET_RELATION])]
        if before_prefix is not None:panels.append(_board(position(before_prefix)))
        panels.extend([_board(raw),_matrix(1,2,[code,code-1 if code else SEPARATOR])])
        options=[_mask(values),_mask(wrong)];accepted=[True,False]
        if reverse:options.reverse();accepted.reverse()
        ev={'kind':'state_target','prefix_hex':prefix,'position_hex':raw.hex(),
            'nominal_code':code,'target_mask':values,'field_offset':66}
        if before_prefix is not None:ev['before_hex']=position(before_prefix).hex()
        return page(identifier,'state_target','teach',panels,options,accepted,ev)

    target('target-none','')
    target('target-21-means-20',_line('e2e4'),'')
    target('target-43-means-42',_line('a2a3 c7c5'),_line('a2a3'),reverse=True)
    target('target-45-means-44',_line('a2a3 e7e5'),_line('a2a3'))
    target('target-expires',_line('e2e4 g8f6'),_line('e2e4'),reverse=True)

    bindings=[[1,0,4,7,6,5],[2,0,4,0,2,3],[4,1,60,63,62,61],[8,1,60,56,58,59]]
    bit_cells=[SEPARATOR,1,2,4,8]+[value for mask in range(16)
        for value in [mask]+[int(bool(mask&bit)) for bit in (1,2,4,8)]]
    page('rights-four-bits','state_rights','teach',[_matrix(1,3,[SEPARATOR,RIGHTS_RELATION,SEPARATOR]),
         _matrix(17,5,bit_cells),_matrix(4,6,[v for row in bindings for v in row]),_board(position(''))],
         [_matrix(1,4,[1,1,1,1]),_matrix(1,4,[0,0,0,0])],[True,False],
         {'kind':'state_rights','field_offset':65,'bit_bindings':bindings,'mask':15})

    def rights_return(identifier,prefix,start,origin,expected):
        story,frames=storyboard(prefix,start)
        current=position(prefix)
        if current[65] != expected:
            raise ValueError('permission demonstration disagrees with oracle')
        bits=[int(bool(expected&b)) for b in (1,2,4,8)]
        return page(identifier,'state_rights','teach',[_matrix(1,3,[SEPARATOR,RIGHTS_RELATION,SEPARATOR]),story],
                    [_matrix(1,5,[15,1,1,1,1]),_matrix(1,5,[expected]+bits)],[False,True],
                    {'kind':'state_rights','field_offset':65,'returned_origin':origin,
                     'storyboard':{'panel_index':1,'frames':frames}})

    rights_return('rights-rook-return',_line('h2h3 a7a6 h1h2 a6a5 h2h1'),8,7,14)
    rights_return('rights-king-return',_line('e2e3 a7a6 e1e2 a6a5 e2e1'),8,4,12)

    occupancy('grid-occupied','teach','')
    occupancy('grid-first-side','teach','',side=0)
    occupancy('grid-second-side','teach','',side=1,reverse=True)
    occupancy('grid-practice','practice',game_moves[:12],reverse=True)
    transition('turn-first','turn','teach','',[_uci('e2e4'),_uci('e7e5')],expected=[True,False])
    transition('turn-second','turn','teach',_line('e2e4'),[_uci('d2d4'),_uci('e7e5')],expected=[False,True])
    transition('turn-practice','turn','practice',_line('d2d4 d7d5'),[_uci('g1f3'),_uci('g8f6')],expected=[True,False])
    transition('bishop-open-ray','sliding','teach',_line('e2e4 e7e5'),[_uci('f1c4'),_uci('f1c5')],expected=[True,False])
    transition('rook-open-ray','sliding','teach',_line('a2a4 a7a5'),[_uci('a1a6'),_uci('a1a3')],expected=[False,True])
    transition('bishop-practice','sliding','practice',_line('d2d4 d7d5'),[_uci('c1f4'),_uci('c1f5')],expected=[True,False])
    transition('queen-diagonal','queen','teach',_line('e2e4 a7a6'),[_uci('d1h5'),_uci('d1g5')],expected=[True,False])
    transition('queen-file','queen','teach',_line('d2d4 a7a6'),[_uci('d1d5'),_uci('d1d3')],expected=[False,True])
    transition('king-one-step','king','teach',_line('e2e4 a7a6'),[_uci('e1e2'),_uci('e1e3')],expected=[True,False])
    transition('knight-jumps','knight','teach','',[_uci('g1g3'),_uci('g1f3')],expected=[False,True])
    transition('knight-other-side','knight','teach',_line('e2e4'),[_uci('b8c6'),_uci('b8c5')],expected=[True,False])
    transition('knight-practice','knight','practice',_line('g1f3 g8f6'),[_uci('f3f5'),_uci('f3e5')],expected=[False,True])
    transition('pawn-capture','capture','teach',_line('e2e4 d7d5'),[_uci('e4d5'),_uci('e4f5')],expected=[True,False])
    transition('capture-or-empty-step','capture','teach',_line('d2d4 e7e5'),[_uci('d4c5'),_uci('d4d5')],expected=[False,True])
    transition('capture-practice','capture','practice',_line('c2c4 d7d5'),[_uci('c4d5'),_uci('c4b5')],expected=[True,False])
    control('attack-is-not-move','teach','',0)
    control('attack-pawn-diagonals','teach',_line('e2e4 d7d5'),0,reverse=True)
    fixture('self-check-capture','self_check','teach','geometry-illegal-self-check','e2d3',reverse=True)
    for identifier,name,alternate,bit,reverse in (
        ('castle-two-pieces','first-kingside','e1e3',1,False),
        ('castle-other-direction','first-queenside','e1a1',2,True),
        ('castle-second-kingside','second-kingside','e8e6',4,True),
        ('castle-second-queenside','second-queenside','e8b8',8,False),
    ):
        demonstration=fixture(identifier,'castling','teach','castling-positive-'+name,alternate,reverse)
        binding=next(row for row in bindings if row[0] == bit)
        demonstration['panels'].insert(0,_matrix(1,6,binding))
        demonstration['evidence']['permission_bit']=bit
    denied=fixture('rights-return-forbids-castling','state_rights','teach',
                   'castling-right-loss-after-king-return','h1f1',reverse=True)
    denied['panels'].insert(0,_matrix(1,3,[RIGHTS_RELATION,1,0]))
    fixture('castle-through-control','castling','teach','castling-failure-through-check','h1f1',reverse=True)
    fixture('en-passant-removes-other-square','en_passant','teach','en-passant-legal-capture','d4e2')
    fixture('self-check-en-passant','self_check','teach','en-passant-pinned-self-exposing-capture','e1e2',reverse=True)
    fixture('en-passant-practice','en_passant','practice','en-passant-two-capturers-right','f4g3',reverse=True)
    for name in ('queen','rook','bishop','knight'):
        fixture('promotion-'+name,'promotion','teach','promotion-quiet-'+name,'b7b8',reverse=name in ('rook','knight'))

    cycle=_line('g1f3 g8f6 f3g1 f6g8')
    prefix=cycle*2
    story,frames=storyboard(prefix)
    key=chess.repetition_key(state(prefix))
    matches=[int(chess.repetition_key(state(f['prefix_hex'])) == key) for f in frames]
    page('history-repeat-relation','history','teach',[_matrix(1,1,[REPEAT_RELATION]),_board(position(prefix)),story],
         [_matrix(1,len(matches),matches),_matrix(1,len(matches),[1]*len(matches))],[True,False],
         {'kind':'history_relation','query_badge':REPEAT_RELATION,'match_flags':matches,
          'storyboard':{'panel_index':2,'frames':frames}})
    # The comparative rows name the chronological checkpoint, number of equal
    # current keys, and the availability bit before asking for that bit alone.
    checkpoints=[0,4,8]
    comparison=[value for ply in checkpoints for value in
                (ply,claim(prefix[:ply*4]).current_key_occurrences,int(claim(prefix[:ply*4]).threefold_available))]
    page('history-claim-comparison','history','teach',[_matrix(1,3,[SEPARATOR,COUNT_RELATION,CLAIM_RELATION]),
         story,_matrix(3,3,comparison)],[_matrix(1,3,[0,1,1]),_matrix(1,3,[0,0,1])],[False,True],
         {'kind':'history_comparison','query_badge':CLAIM_RELATION,'comparison':comparison,
          'storyboard':{'panel_index':1,'frames':frames}})

    def history(identifier,phase,prefix,count_shown=False,reverse=False):
        story,frames=storyboard(prefix)
        fact=claim(prefix)
        panels=[_matrix(1,1,[CLAIM_RELATION]),story,_board(position(prefix))]
        if count_shown:panels.append(_matrix(1,2,[COUNT_RELATION,fact.current_key_occurrences]))
        options=[_matrix(1,1,[0]),_matrix(1,1,[1])]
        accepted=[not fact.threefold_available,fact.threefold_available]
        if reverse:options.reverse();accepted.reverse()
        return page(identifier,'history',phase,panels,options,accepted,
                    {'kind':'history','query_badge':CLAIM_RELATION,'prefix_hex':prefix,
                     'storyboard':{'panel_index':1,'frames':frames},'count_shown':count_shown,
                     'occurrences':fact.current_key_occurrences,'threefold_available':fact.threefold_available})

    history('history-second-practice','practice',cycle)

    ep_base=fixtures['en-passant-legal-capture']['input']['moves_hex']
    no_ep_base=_line('e2e4')
    ep_cycle=_line('g8f6 g1f3 f6g8 f3g1')
    pairs=[[no_ep_base,no_ep_base+ep_cycle],[ep_base,ep_base+ep_cycle]]
    equal=[];panels=[_matrix(1,1,[REPEAT_RELATION])]
    for pair in pairs:
        equal.append(chess.repetition_key(state(pair[0])) == chess.repetition_key(state(pair[1])))
        joined,_=_choices([_board(position(p)) for p in pair])
        panels.append(joined)
        panels.append(_matrix(1,2,[0 if claim(p).effective_ep.square is None
                                  else claim(p).effective_ep.square+1 for p in pair]))
    if equal != [True,False]:
        raise ValueError('effective-target boundary disagrees with oracle')
    page('history-effective-target-boundary','history','teach',panels,
         [_matrix(1,2,[1,0]),_matrix(1,2,[0,0])],[True,False],
         {'kind':'history_equivalence','query_badge':REPEAT_RELATION,'prefix_pairs':pairs,
          'same_keys':equal,'comparison_scope':'paired current positions; no omitted-history count claim'})
    continuing=transition('history-claim-allows-next-move','history','teach',prefix,
                          [_uci('e2e5'),_uci('e2e4')],expected=[False,True])
    continuing['panels'].insert(0,_matrix(2,2,[CLAIM_RELATION,1,CONTINUE_RELATION,1]))
    continuing['evidence']['threefold_available']=claim(prefix).threefold_available
    if not continuing['evidence']['threefold_available']:
        raise ValueError('claim-availability demonstration disagrees with oracle')

    def record(identifier,phase,index,alternate,reverse=False):
        prefix=game_moves[:4*index]
        encoded=game_moves[4*index:4*index+4]
        sequence=[encoded,_uci(alternate)]
        if reverse:sequence.reverse()
        p=transition(identifier,'game',phase,prefix,sequence,game_path,expected=[True,True])
        p['correct']=tuple(o['region_id'] for o in p['evidence']['options'] if o['move_hex'] == encoded)
        if len(p['correct']) != 1:
            raise ValueError('record alternatives must differ')
        footers={bytes.fromhex(o['after_hex'])[64:] for o in p['evidence']['options']}
        if len(footers) != 1:
            raise ValueError('record footer would reveal the answer')
        move=chess.decode_move(bytes.fromhex(encoded))
        wire=bytes.fromhex(encoded)
        diagram=_matrix(2,3,list(wire)+[SEPARATOR]+[move.origin,move.destination,move.promotion])
        p['panels'][:0]=[_matrix(1,1,[RECORD_RELATION]),diagram]
        p['evidence'].update(kind='record_transition',game_path=game_path,
            game_set_sha256=hashlib.sha256(game_set).hexdigest(),game_sha256=hashlib.sha256(game).hexdigest(),
            game_ordinal=0,ply_index=index,record_move_hex=encoded,
            record_diagram={'wire_bytes':list(wire),'origin':move.origin,'destination':move.destination,'promotion':move.promotion})
        return p

    record('game-first','teach',2,'b1c3')
    record('game-second','teach',3,'g8f6',reverse=True)

    # New final boards/options, never the old trial's third-ply record question
    # or its confounded en-passant illustration. The self-check is a reachable
    # bishop pin with mechanically ordinary displacement.
    occupancy('final-grid','heldout',game_moves[:28])
    transition('final-turn','turn','heldout',_line('b2b3'),[_uci('b1c3'),_uci('b8c6')],expected=[False,True])
    transition('final-sliding','sliding','heldout',_line('g2g3 d7d5'),[_uci('f1h3'),_uci('f1h4')],expected=[True,False])
    transition('final-knight','knight','heldout',_line('g1h3 e7e5'),[_uci('h3h5'),_uci('h3g5')],expected=[False,True])
    transition('final-capture','capture','heldout',_line('g2g4 h7h5'),[_uci('g4h5'),_uci('g4f5')],expected=[True,False])
    control('final-control','heldout',_line('b2b3 e7e6'),0,reverse=True)
    transition('final-castling','castling','heldout',
               fixtures['castling-positive-second-kingside']['input']['moves_hex']+_line('a7a6 a2a3'),
               [_uci('e8e6'),_uci('e8g8')],expected=[False,True])
    transition('final-en-passant','en_passant','heldout',_line('e2e4 a7a6 e4e5 d7d5'),
               [_uci('e5d6'),_uci('e5f6')],expected=[True,False])
    transition('final-self-check','self_check','heldout',_line('d2d4 e7e6 b1c3 f8b4'),
               [_uci('c3b5'),_uci('a2a3')],expected=[False,True])
    transition('final-promotion','promotion','heldout',fixtures['promotion-quiet-queen']['input']['moves_hex']+_line('g1f3 g8f6'),
               [_uci('b7a8n'),_uci('b7a8')],expected=[True,False])
    history('final-history','heldout',_line('b1a3 b8a6 a3b1 a6b8'),reverse=True)
    record('final-game','heldout',5,'g8f6',reverse=True)
    return pages
