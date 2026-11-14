"""Finite authored T1–T3 data, with coherent histories and exact typed truth."""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import tomllib

import chess

from .authoring import occupancy,token
from .course_author import CourseAuthor,compile_group,passive_reachable
from .course_generic import add_numeric_glyphs,number_glyph
from .document import decode_document
from .rules import Replay
from .source_game import cell_index

ROWS,COLS=20,10
PIN_BLACK='e2e4 e7e5 g1f3 b8c6 f1b5 d7d6 a2a3'
PIN_WHITE='e2e4 e7e5 b1c3 g8f6 d2d3 f8b4'
KING_LINE_WHITE='e2e4 f7f5 a2a3 f5e4 a3a4 h7h5 a4a5 h8h6 a5a6 h6f6 b2b3 d7d5 b3b4 c8g4 b4b5 g4f3 b5b6 f3e2 a6b7 e2d1 b6c7 f6f2 h2h3 f2f1'
KING_LINE_BLACK='b1c3 e7e5 f2f4 a7a6 f4e5 a6a5 h2h4 a5a4 h1h3 a4a3 h3f3 b7b6 d2d4 b6b5 c1g5 b5b4 g5f6 b4b3 f6e7 a3b2 e7d8 b3c2 f3f7 h7h6 f7f8'
OPS={name:i for i,name in enumerate(('address','identity','occupied','setup','turn','legal','control','capture','candidate','evasions','termination','move'),1)}


@lru_cache(maxsize=128)
def coherent(prefix):
    state=Replay();fens=[state.fen]
    for move in prefix.split():state.play(move);fens.append(state.fen)
    return state,tuple(fens)


def squares(names):return sorted(cell_index(chess.parse_square(name)) for name in names.split())


def _square(index):return chess.square(index%8,7-index//8)


def foundation_result(spec):
    """Typed authoring predicates; legal claims always use the full Replay witness."""
    state,_=coherent(spec['prefix']);board=chess.Board(state.fen);op=spec['op']
    if op=='address':
        row,col=spec['row'],spec['col']
        if type(row) is not int or type(col) is not int or not 0<=row<8 or not 0<=col<8:raise ValueError('Outside complete8x8matrix.')
        return [row*8+col]
    if op=='identity':return [i for i,v in enumerate(occupancy(board)) if v==spec['selector']]
    if op=='occupied':return [i for i,v in enumerate(occupancy(board)) if bool(v)==spec['occupied']]
    if op=='setup':
        if spec['prefix']:raise ValueError('Standard setup is the actual initial state.')
        return occupancy(board)
    if op=='turn':return state.side_to_move
    if op=='termination':
        chess.Move.from_uci(spec['move'])
        verified=Replay()
        for item in spec['prefix'].split():verified.play(item)
        try:verified.play(spec['move']);accepted=True
        except ValueError:
            accepted=False
        if accepted and not verified.closed:raise ValueError('An accepted closure example requires an actual terminal state.')
        return {'after':occupancy(chess.Board(verified.fen)),'accepted':accepted,'closed_before':state.closed,
            'closed_after':verified.closed,'after_side':verified.side_to_move}
    if op in ('legal','control'):
        source=chess.parse_square(spec['source']);piece=board.piece_at(source)
        if piece is None:raise ValueError('An explicit existing controller is required.')
        if op=='control':return sorted(cell_index(s) for s in board.attacks(source))
        if int(not piece.color)!=state.side_to_move:raise ValueError('Legal query must use the active side.')
        moves=[chess.Move.from_uci(m) for m in state.legal_moves if m.startswith(spec['source'])]
        if any(m.promotion for m in moves):raise ValueError('Promotion requires its later explicit choice lesson.')
        return sorted({cell_index(m.to_square) for m in moves})
    if op=='evasions':
        if not board.is_check() or state.closed:raise ValueError('Active check is required for an evasion lesson.')
        if any(chess.Move.from_uci(m).promotion for m in state.legal_moves):raise ValueError('This ordinary reply table precedes explicit promotion notation.')
        return sorted([[cell_index(m.from_square)//8,cell_index(m.from_square)%8,
                        cell_index(m.to_square)//8,cell_index(m.to_square)%8]
                       for m in map(chess.Move.from_uci,state.legal_moves)])
    if op in ('candidate','capture','move'):
        move=chess.Move.from_uci(spec['move']);piece=board.piece_at(move.from_square)
        if piece is None or int(not piece.color)!=state.side_to_move or move.promotion or not board.is_pseudo_legal(move):
            raise ValueError('Ordinary geometrical candidate for the active side required.')
        target=board.piece_at(move.to_square)
        if op!='move' and (target is None or target.color==piece.color or target.piece_type==chess.KING):
            raise ValueError('This explicitly scoped example is an ordinary nonking capture.')
        if board.is_castling(move) or board.is_en_passant(move):raise ValueError('Special updates require their later dedicated lessons.')
        accepted=spec['move'] in state.legal_moves
        if op in ('capture','move') and not accepted:raise ValueError('An update requires an actual legal continuation.')
        after=board.copy();after.remove_piece_at(move.from_square);after.set_piece_at(move.to_square,piece)
        if accepted:
            verified=Replay()
            for item in spec['prefix'].split()+[spec['move']]:verified.play(item)
            if occupancy(chess.Board(verified.fen))!=occupancy(after):raise ValueError('Ordinary update differs from actual replay.')
        return {'after':occupancy(after),'accepted':accepted,'captured':token(target),
            'target_attacked_before':board.is_attacked_by(not piece.color,move.to_square),
            'king_attacked_after':after.is_attacked_by(not piece.color,after.king(piece.color)),
            'after_side':1-state.side_to_move if accepted else state.side_to_move}
    raise ValueError('Unknown authored foundation predicate: '+str(op))


def _grid(cells,values,y):
    if len(values)!=64:raise ValueError('Full64cell matrix required.')
    for i in range(8):cells[y*COLS+i+1]=number_glyph(i);cells[(y+1+i)*COLS]=number_glyph(i)
    for i,v in enumerate(values):cells[(y+1+i//8)*COLS+1+i%8]=v


def render_foundation(spec,result,*,verdict=None):
    state,_=coherent(spec['prefix']);board=chess.Board(state.fen);cells=[0]*(ROWS*COLS);op=spec['op']
    _grid(cells,occupancy(board),0)
    cells[9*COLS]=3+state.side_to_move
    cells[9*COLS+1]=spec.get('selector',0)
    if 'source' in spec:
        i=cell_index(chess.parse_square(spec['source']));cells[9*COLS+1]=token(board.piece_at(chess.parse_square(spec['source'])))
        cells[9*COLS+2:9*COLS+4]=[number_glyph(i//8),number_glyph(i%8)]
    if 'row' in spec:cells[9*COLS+2:9*COLS+4]=[number_glyph(spec['row']),number_glyph(spec['col'])]
    if 'occupied' in spec:cells[9*COLS+1]=5 if spec['occupied'] else 0
    if 'move' in spec:
        m=chess.Move.from_uci(spec['move']);a,b=cell_index(m.from_square),cell_index(m.to_square)
        cells[9*COLS+1]=token(board.piece_at(m.from_square))
        cells[9*COLS+2:9*COLS+6]=[number_glyph(v) for v in (a//8,a%8,b//8,b%8)]
    cells[9*COLS+6]=spec.get('mode',8 if op=='control' else 9 if op=='legal' else 0)
    code=OPS[op];cells[19*COLS+2:19*COLS+6]=[1 if code&(1<<bit) else 2 for bit in range(3,-1,-1)]
    if result is not None:
        if op in ('capture','candidate','move','termination'):
            _grid(cells,result['after'],10);cells[19*COLS]=3+result['after_side']
            cells[19*COLS+7]=number_glyph(int(result['accepted']))
            if op=='termination':cells[19*COLS+8:19*COLS+10]=[number_glyph(int(result[k])) for k in ('closed_before','closed_after')]
            else:cells[19*COLS+8]=number_glyph(int(result['king_attacked_after']))
        elif op=='setup':_grid(cells,result,10)
        elif op=='turn':cells[14*COLS+4]=3+result
        elif op=='evasions':
            if len(result)>8:raise ValueError('Full reply list exceeds this fixed rendered table.')
            cells[10*COLS]=number_glyph(len(result))
            for r,row in enumerate(result):
                for c,v in enumerate(row):cells[(11+r)*COLS+2+c]=number_glyph(v)
        else:_grid(cells,[5 if i in result else 0 for i in range(64)],10)
    if verdict is not None:cells[9*COLS+9]=6 if verdict else 7
    return cells


def _query(ident,strata,work,practice,work_rival,options,*,variants=()):
    expected=foundation_result(practice);worked_expected=foundation_result(work)
    if worked_expected==work_rival or options.count(expected)!=1 or len(options) not in (2,3):raise ValueError('Discriminating complete alternatives required: '+ident)
    q={'id':ident,'strata':list(strata),'worked_input':work,'input':practice,'worked_expected':worked_expected,
       'worked_rival':work_rival,'expected':expected,'options_data':options,'correct':options.index(expected),'worked_variants':list(variants)}
    q['worked']=[render_foundation(work,None),render_foundation(work,worked_expected,verdict=True)]
    for v in variants:q['worked']+=[render_foundation(v,None),render_foundation(v,foundation_result(v),verdict=True)]
    q['contrast']=[render_foundation(work,work_rival,verdict=False),render_foundation(work,worked_expected,verdict=True)]
    q['options']=[render_foundation(practice,o) for o in options]
    return q


def _mask_alternatives(spec,expected):
    if spec['op'] in ('legal','control'):
        other={**spec,'op':'control' if spec['op']=='legal' else 'legal'}
        rival=foundation_result(other)
    else:rival=[]
    candidates=[expected,rival,expected[1:] if expected else [0]];out=[]
    for value in candidates:
        if value not in out:out.append(value)
    if len(out)<3:
        changed=sorted(set(expected)^{next(i for i in range(64) if i not in expected) if len(expected)<64 else 0})
        if changed not in out:out.append(changed)
    return out


def _movement(ident,strata,wp,ws,work_hand,pp,ps,practice_hand,*,op='legal',captures=()):
    work={'op':op,'prefix':wp,'source':ws};practice={'op':op,'prefix':pp,'source':ps}
    expected,worked=foundation_result(practice),foundation_result(work)
    if expected!=squares(practice_hand) or worked!=squares(work_hand):raise ValueError('Hand-derived movement witness disagrees: '+ident)
    rival=foundation_result({**work,'op':'control' if op=='legal' else 'legal'})
    if rival==worked:rival=worked[1:]
    options=_mask_alternatives(practice,expected)
    # Deliberately vary correct-option position independently of mode/turn.
    shift=sum(map(ord,ident))%len(options);options=options[shift:]+options[:shift]
    return _query(ident,strata,work,practice,rival,options,variants=captures)


def foundation_groups():
    q=[]
    orientation='eight_by_eight_orientation';identity='stable_unfamiliar_piece_and_side_glyphs';setup='standard_setup_all_six_types_both_sides'
    w={'op':'address','prefix':'','row':0,'col':7};p={'op':'address','prefix':'e2e4','row':7,'col':0}
    q.append(_query('board-address',[orientation],w,p,[56],[[0],[56],[63]]))
    # Every initial type and side is individually queried and bound, not inferred
    # from an atlas label. Worked/play states vary without changing glyph identity.
    for side in range(2):
        for kind in range(1,7):
            glyph=31+kind+side*6;w={'op':'identity','prefix':'','selector':glyph}
            p={'op':'identity','prefix':'e2e4 e7e5','selector':glyph}
            expected=foundation_result(p);rival=foundation_result({**w,'selector':glyph+6 if side==0 else glyph-6})
            options=[expected,foundation_result({**p,'selector':glyph+6 if side==0 else glyph-6}),[]]
            if not expected:raise ValueError('Every side/type must remain present in the chosen identity context.')
            if kind%2:options=options[1:]+options[:1]
            q.append(_query(f'identity-{side}-{kind}',[identity,setup],w,p,rival,options))
    w={'op':'occupied','prefix':'','occupied':True};p={'op':'occupied','prefix':'e2e4 d7d5 e4d5','occupied':False}
    q.append(_query('empty-and-occupied',['empty_vs_occupied'],w,p,foundation_result({**w,'occupied':False}),
        _mask_alternatives(p,foundation_result(p)),variants=({**w,'occupied':False},)))
    for mode in (8,9):
        w={'op':'turn','prefix':'','mode':mode};p={'op':'turn','prefix':'e2e4','mode':mode}
        q.append(_query(f'turn-mode-{mode}',['first_side_and_alternation','turn_not_query_mode'],w,p,1,[1,0],
            variants=({**w,'prefix':'e2e4'},{**w,'prefix':'e2e4 e7e5'})))
    groups=[{'id':f'board-identity-{i//8+1}','rows':ROWS,'cols':COLS,'queries':q[i:i+8]} for i in range(0,len(q),8)]

    king_captures=(
        {'op':'capture','prefix':'e2e4 d7d5 e1e2 d5e4 e2e3 a7a6','move':'e3e4'},
        {'op':'capture','prefix':'b1c3 e7e5 d2d4 e8e7 d4e5 e7e6 a2a3','move':'e6e5'})
    q=[
        _movement('king',['king_step_and_boundary'],'e2e4 a7a6 e1e2 a6a5','e2','d3 e3 f3 e1','b1c3 e7e5 d2d4 e8e7 d4e5 e7e6 a2a3','e6','e7 e5 f5',captures=king_captures),
        _movement('queen',['queen_ray_and_block'],'e2e4 e7e5','d1','e2 f3 g4 h5','e2e4 e7e5 f2f3 d8h4 g2g3','h4','d8 e7 f6 h6 g5 h5 e4 f4 g4 g3 h3 h2',captures=(
            {'op':'capture','prefix':'e2e4 e7e5 d1h5 b8c6','move':'h5e5'},
            {'op':'capture','prefix':'e2e4 e7e5 f2f3 d8h4 g2g3','move':'h4g3'})),
        _movement('rook',['rook_ray_and_block'],'a2a4 a7a5','a1','a2 a3','a2a4 h7h5 a4a5 h5h4 b2b3 h8h5 b3b4','h5','h8 h7 h6 a5 b5 c5 d5 e5 f5 g5',captures=(
            {'op':'capture','prefix':'a2a4 h7h5 a4a5 h5h4 a1a4 a7a6','move':'a4h4'},
            {'op':'capture','prefix':'a2a4 h7h5 a4a5 h5h4 b2b3 h8h5 b3b4','move':'h5a5'})),
        _movement('bishop',['bishop_ray_and_block'],'e2e4 e7e5','f1','e2 d3 c4 b5 a6','e2e4 e7e5 b1c3 f8b4 a2a3','b4','f8 e7 d6 a5 c5 a3 c3',captures=(
            {'op':'capture','prefix':'e2e4 d7d5 f1b5 c7c6','move':'b5c6'},
            {'op':'capture','prefix':'e2e4 e7e5 b1c3 f8b4 a2a3','move':'b4c3'})),
        _movement('knight',['knight_jump_and_boundary','friendly_occupancy_vs_defense'],'','b1','a3 c3','e2e4 g8f6 a2a3','f6','g8 d5 h5 e4 g4',captures=(
            {'op':'capture','prefix':'g1f3 e7e5','move':'f3e5'},
            {'op':'capture','prefix':'e2e4 g8f6 a2a3','move':'f6e4'})),
        _movement('pawn-forward',['pawn_forward_not_capture','pawn_initial_double_clear_path','both_sides_pawn_directions'],'','e2','e3 e4','e2e4','d7','d6 d5'),
        _movement('pawn-capture',['pawn_diagonal_capture_not_forward','both_sides_pawn_directions'],'e2e4 d7d5','e4','d5 e5','e2e4 d7d5 a2a3','d5','d4 e4'),
        _movement('pawn-double-blocked',['pawn_double_blocked_or_moved'],'g1f3 a7a6 f3e5 a6a5 e5d3 a5a4','d2','','b1c3 a7a6 c3d5','d7','d6'),
        _movement('pawn-moved',['pawn_double_blocked_or_moved'],'e2e3 a7a6 e3e4 a6a5','e4','e5','a2a3 d7d6 a3a4 d6d5 a4a5','d5','d4'),
    ]
    work={'op':'capture','prefix':'e2e4 d7d5','move':'e4d5'};practice={'op':'capture','prefix':'e2e4 d7d5 a2a3','move':'d5e4'}
    wr=foundation_result(work);bad=deepcopy(wr);bad['after'][36]=32 # Source pawn incorrectly retained.
    answer=foundation_result(practice);extra=deepcopy(answer);extra['after'][27]=38
    missing=deepcopy(answer);missing['after'][36]=32 # Captured piece incorrectly remains.
    q.append(_query('capture-removal',['ordinary_capture_removal'],work,practice,bad,[extra,answer,missing]))
    groups += [{'id':f'movement-{i//8+1}','rows':ROWS,'cols':COLS,'queries':q[i:i+8]} for i in range(0,len(q),8)]

    q=[_movement('pinned-control',['pinned_controller_still_controls','geometric_move_exposes_own_king'],PIN_BLACK,'c6','a5 a7 b4 b8 d4 d8 e5 e7',PIN_WHITE,'c3','a2 a4 b1 b5 d1 d5 e2 e4',op='control'),
       _movement('pinned-legality',['geometric_move_exposes_own_king'],PIN_WHITE,'c3','',PIN_BLACK,'c6',''),
       _movement('pawn-control',['pawn_king_friendly_defense_control'],'','d2','c3 e3','e2e4','d7','c6 e6',op='control'),
       _movement('king-control',['pawn_king_friendly_defense_control','king_step_and_boundary'],'','e1','d1 f1 d2 e2 f2','e2e4','e8','d8 f8 d7 e7 f7',op='control')]
    work={**king_captures[0],'op':'candidate'};practice={**king_captures[1],'op':'candidate'}
    wr=foundation_result(work);wrong=deepcopy(wr);wrong['after_side']=coherent(work['prefix'])[0].side_to_move
    answer=foundation_result(practice);bad=deepcopy(answer);bad['accepted']=False;bad['king_attacked_after']=True;bad['after_side']=coherent(practice['prefix'])[0].side_to_move
    retained=deepcopy(answer);retained['after_side']=bad['after_side']
    q.append(_query('capture-opens-line',['king_capture_opens_slider_line'],work,practice,wrong,[bad,answer,retained],variants=(
        {'op':'candidate','prefix':KING_LINE_WHITE,'move':'e1d1'},
        {'op':'candidate','prefix':KING_LINE_BLACK,'move':'e8d8'})))
    work={'op':'evasions','prefix':'e2e4 e7e5 d1h5 b8c6 h5e5'}
    practice={'op':'evasions','prefix':'e2e4 e7e5 h2h3 f7f6 d1h5'}
    wr=foundation_result(work);answer=foundation_result(practice)
    q.append(_query('all-evasions',['complete_check_evasions_king_capture_block'],work,practice,wr[:1],[answer[:1],[],answer]))
    work={'op':'termination','prefix':'f2f3 e7e5 g2g4','move':'d8h4'}
    practice={'op':'termination','prefix':'e2e4 e7e5 f1c4 b8c6 d1h5 g8f6 h5f7','move':'f7e8'}
    wrong=deepcopy(foundation_result(work));wrong['after'][60]=0
    answer=foundation_result(practice);removed=deepcopy(answer);removed['after'][4]=0;removed['accepted']=True
    active=deepcopy(answer);active['closed_after']=False
    q.append(_query('king-retention',['no_king_capture_as_game_end'],work,practice,wrong,[answer,removed,active],
        variants=({'op':'termination','prefix':'f2f3 e7e5 g2g4 d8h4','move':'h4e1'},
                  {'op':'termination','prefix':'f2f3 e7e5 g2g4','move':'d8g4'})))
    work={'op':'termination','prefix':'e2e4 e7e5 f2f3 d8h4','move':'a2a3'}
    practice={'op':'termination','prefix':'e2e4 e7e5 d1h5 b8c6 h5e5','move':'a7a6'}
    wrong=deepcopy(foundation_result(work));wrong['closed_before']=True
    answer=foundation_result(practice);check_alias=deepcopy(answer);check_alias['closed_before']=True
    false_ending=deepcopy(answer);false_ending['closed_after']=True
    q.append(_query('prior-closure',['no_king_capture_as_game_end'],work,practice,wrong,
                    [check_alias,answer,false_ending],variants=(
                        {'op':'termination','prefix':'f2f3 e7e5 g2g4 d8h4','move':'a2a3'},
                        {'op':'termination','prefix':'e2e4 e7e5 f2f3 d8h4','move':'h4e1'})))
    groups.append({'id':'control-and-check','rows':ROWS,'cols':COLS,'queries':q})
    return groups


def validate_foundation(product):
    canonical={g['id']:g for g in foundation_groups()}
    if len(product['groups'])!=len(canonical) or {g['id'] for g in product['groups']}!=set(canonical):raise ValueError('Missing/unknown foundation group.')
    document=decode_document(product['document']);digest=hashlib.sha256(product['document']).hexdigest()
    reached=passive_reachable(product['document']);expected_bindings={};checked=[]
    def frames(node):
        page=document['records'].get(node)
        if page is None or page['kind']!=4:raise ValueError('Binding is not an actual page.')
        record=document['records'][page['display']]
        if page['display_kind']==0:return [record['cells']]
        current=list(document['records'][record['initial']]['cells']);result=[list(current)]
        for step in record['steps']:
            for i,v in step:current[i]=v
            result.append(list(current))
        return result
    cases={c['id']:c for c in product['cases']}
    if len(cases)!=len(product['cases']) or set(cases)!=set(canonical):raise ValueError('Missing/unknown serialized case.')
    for group in product['groups']:
        reference=canonical[group['id']]
        if [q['id'] for q in group['queries']]!=[q['id'] for q in reference['queries']]:raise ValueError('Missing/unknown stratum query.')
        a=CourseAuthor();add_numeric_glyphs(a);compiled=compile_group(a,reference);case=cases[group['id']]
        if case['queries']!=compiled['queries'] or case['expected']!=compiled['expected']:raise ValueError('Wrong actual query/response/range binding.')
        for role in ('worked','practice','passive','success','failure'):
            node=case[role]
            if node not in reached or frames(node)!=compiled['frames'][str(compiled[role])]:raise ValueError('Wrong/missing serialized '+role+' evidence.')
            page=document['records'][node];expected_page=a.record(compiled[role])
            if any(page[k]!=expected_page[k] for k in ('shape','choices','accepted')):raise ValueError('Wrong serialized response relation.')
        for r in ('worked','practice','passive'):
            required=[case[v] for v in ('worked','practice','passive') if v!=r]
            if any(v not in document['records'][case[r]]['links'] for v in required):raise ValueError('Mandatory passive relation requires a response.')
        for q,binding,known in zip(group['queries'],case['queries'],reference['queries']):
            if q['strata']!=known['strata'] or q['input']!=known['input'] or q['worked_input']!=known['worked_input'] or q['worked_variants']!=known['worked_variants']:
                raise ValueError('Predicate/input/stratum role differs from its declared authoring obligation.')
            for s in known['strata']:expected_bindings.setdefault(s,[]).append(_binding(case,binding,digest))
        for q in group['queries']:
            if foundation_result(q['input'])!=q['expected'] or foundation_result(q['worked_input'])!=q['worked_expected']:
                raise ValueError('Wrong foundation predicate: '+q['id'])
            if q['worked_expected']==q['worked_rival'] or q['options_data'].count(q['expected'])!=1 or q['options_data'][q['correct']]!=q['expected']:
                raise ValueError('Wrong/incomplete foundation alternatives: '+q['id'])
            work=[render_foundation(q['worked_input'],None),render_foundation(q['worked_input'],q['worked_expected'],verdict=True)]
            for v in q['worked_variants']:work += [render_foundation(v,None),render_foundation(v,foundation_result(v),verdict=True)]
            if q['worked']!=work or q['contrast']!=[render_foundation(q['worked_input'],q['worked_rival'],verdict=False),render_foundation(q['worked_input'],q['worked_expected'],verdict=True)] or q['options']!=[render_foundation(q['input'],v) for v in q['options_data']]:
                raise ValueError('Wrong displayed foundation state/intermediate: '+q['id'])
            checked.append({'query':q['id'],'strata':q['strata'],'input':q['input'],'expected':q['expected'],'worked_input':q['worked_input'],'worked_expected':q['worked_expected'],'rival':q['worked_rival'],
                'worked_variants':[{'input':v,'expected':foundation_result(v)} for v in q['worked_variants']],
                'complete_domain':64 if q['input']['op'] not in ('evasions','turn') else 'all actual legal replies' if q['input']['op']=='evasions' else [0,1]})
    expected={s for f in product['coverage_families'] for s in f['critical_strata']}
    if set(product['bindings'])!=expected or product['bindings']!=expected_bindings:raise ValueError('False/missing actual foundation stratum binding.')
    if any(c[k] not in reached for c in product['cases'] for k in ('worked','practice','passive','success','failure')):raise ValueError('Response required for passive content.')
    if any(node not in reached for node in product['contexts'].values()):raise ValueError('Missing carried history prerequisite.')
    prefixes={spec['prefix'] for group in product['groups'] for q in group['queries'] for spec in [q['worked_input'],q['input'],*q['worked_variants']]}
    if set(product['contexts'])!=prefixes:raise ValueError('Missing coherent history prerequisite.')
    prerequisite=product.get('prerequisites',{}).get('coordinate_quad')
    if prerequisite!={'node':product['roots'][0],'steps':[12,15]} or frames(prerequisite['node'])!=_atlas_frames():raise ValueError('Missing/wrong coordinate-quad calibration.')
    return {'strata':len(expected),'queries':checked,'passive_without_response':True,'scope':'Finite authoredT1–T3 truth only; not recipient understanding or complete course'}


def _binding(case,query,digest):
    return {'case':case['id'],'query':query['id'],'document_sha256':digest,'state':'authored',
        'worked':case['worked'],'worked_steps':query['worked_steps'],'contrast':case['contrast'],'contrast_steps':query['contrast_steps'],
        'practice':case['practice'],'prediction':case['practice'],'practice_steps':query['practice_steps'],
        'passive':case['passive'],'passive_steps':query['passive_steps'],'success':case['success'],'failure':case['failure']}


def _atlas_frames():
    result=[]
    for glyph in range(32,44):
        spec={'op':'identity','prefix':'','selector':glyph};result.append(render_foundation(spec,foundation_result(spec)))
    for prefix,move in (('','e2e4'),('e2e4','e7e5')):
        spec={'op':'move','prefix':prefix,'move':move}
        result += [render_foundation(spec,None),render_foundation(spec,foundation_result(spec),verdict=True)]
    return result


def build_foundation(root):
    author=CourseAuthor()
    retained=(root/'evidence/S03-selective-carrier/actual-rehearsal/documents/3.bin').read_bytes()
    if hashlib.sha256(retained).hexdigest()!='a8c4da928c2ff570d69897c148a7c9c95c7537dcd4fedee222f714e58ecf8bcd':raise ValueError('Historical T4representative changed.')
    from .qualified_inputs import current_document
    retained=current_document(retained,'foundation')
    old=decode_document(retained);t4=old['entries'][-1];imported=author.import_subgraph(retained,[t4])
    add_numeric_glyphs(author);groups=foundation_groups();cases=[];contexts={};context_frames={}
    # First ordinary coordinate quads are spatially aligned with later reply rows.
    # Both sides: before board, tuple, and complete resulting occupancy/turn.
    atlas_frames=_atlas_frames()
    atlas=author.page('board-and-identity-atlas',author.trace(atlas_frames,ROWS,COLS),trace=True)
    for group in groups:
        c=compile_group(author,group);c['section']=3;cases.append(c)
        prefixes={spec['prefix'] for q in group['queries'] for spec in [q['worked_input'],q['input'],*q['worked_variants']]}
        for prefix in sorted(prefixes):
            if prefix not in contexts:
                _,fens=coherent(prefix);frames=[]
                for i,fen in enumerate(fens):
                    b=chess.Board(fen);frame=[0]*100;_grid(frame,occupancy(b),0);frame[90]=3 if b.turn else 4
                    if i:
                        m=chess.Move.from_uci(prefix.split()[i-1]);a,before_target=cell_index(m.from_square),cell_index(m.to_square)
                        frame[92:96]=[number_glyph(v) for v in (a//8,a%8,before_target//8,before_target%8)]
                    frames.append(frame)
                node=author.page('history-'+str(len(contexts)),author.trace(frames,10,COLS),trace=True)
                contexts[prefix]=node;context_frames[str(node)]=frames
            node=contexts[prefix]
            author.record(c['worked'])['links'].append(node)
            author.record(c['passive'])['links'].append(node)
            if c['worked'] not in author.record(node)['links']:author.record(node)['links'].append(c['worked'])
    roots=[atlas]+[c['worked'] for c in cases]+[t4]
    for a,b in zip(roots[:-2],roots[1:-1]):author.record(a)['links'].append(b);author.record(b)['links'].append(a)
    # The retained T4graph stays byte-for-byte identical; a new entry links to it.
    author.record(cases[-1]['worked'])['links'].append(t4)
    cases[0]['frames'][str(atlas)]=atlas_frames
    # Every history is checked once through a group that actually links to it.
    for node,frames in context_frames.items():
        c=next(c for c in cases if int(node) in author.record(c['worked'])['links']);c['frames'][node]=frames
    body=author.encode(roots);digest=hashlib.sha256(body).hexdigest();bindings={}
    for c in cases:
        for q in c['queries']:
            for s in q['strata']:
                bindings.setdefault(s,[]).append(_binding(c,q,digest))
    families=tomllib.loads((root/'content/coverage.toml').read_text())['family'][1:4]
    product={'document':body,'groups':groups,'cases':cases,'bindings':bindings,'roots':roots,'contexts':contexts,
        'prerequisites':{'coordinate_quad':{'node':atlas,'steps':[12,15]}},
        'coverage_families':families,'full_course':False,'retained_t4':{'root':t4,'records':list(imported),'state':'representative only; T4uncompleted'},
        'scope':'Actual24T1–T3logical strata plus exact retainedT4representative; no carried/recipient claim'}
    product['truth']=validate_foundation(product)
    return product
