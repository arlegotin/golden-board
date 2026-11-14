"""Finite remaining-course inputs/results. Editorial names never enter the artifact."""
from copy import deepcopy
import json
import chess
from . import advanced_state as native
from .advanced_fixtures import fixtures
from .anthology_input import load_anthology
from .authoring import occupancy
from .document import decode_document
from .practical_state import evaluate as practical,history,REASONS
from .practical_cases import move,claim,PROMO,CYCLE,EP,SCHOLAR
from .source_game import cell_index

MODES={'relation':1,'files':2,'discovered':3,'escape':4,'schedule':5,'proof':6,'facts':7,'routine':8,'anthology':9,'effect':10}
KINDS={'attacked':1,'defended':2,'pin':3,'fork':4,'inventory':5,'scale':6,'development':7,
 'center':8,'king':9,'activity':10,'lines':11,'restriction':12,'pawns':13,'alternatives':14,'comparison':15}

def cell(text):return cell_index(chess.parse_square(text))
def local(fen,kind,source='c3'):return {'op':'relation','fen':fen,'kind':kind,'source':cell(source)}
def files(fen,side=0,file=3,pawn='d5'):
    return {'op':'files','fen':fen,'side':side,'file':file,'pawn':None if pawn is None else cell(pawn)}
def coherent(op,prefix,**values):return {'op':op,'prefix':' '.join(prefix.split()),**values}
def schedule(prefix,moves):return coherent('schedule',prefix,moves=moves)
def mating_tree(first='h4g3'):
    return {'children':{first:{'children':{
        'g1f1':{'children':{'g3f2':{}}},'g1h1':{'children':{'g3g2':{}}}}}}}
def certificate(prefix,tree=None,winner=0):return coherent('proof',prefix,winner=winner,tree=mating_tree() if tree is None else tree)
def facts(prefix,kind,**values):return coherent('facts',prefix,kind=kind,**values)
def routine(spec):return {**spec,'op':'routine','request_op':spec['op']}
def anthology(ordinal,ply,seeks=()):return {'op':'anthology','ordinal':ordinal,'ply':ply,'seeks':list(seeks)}

def signature(spec):return json.dumps({k:v for k,v in spec.items() if k not in ('history_id','other_history_id','context_id')},sort_keys=True,separators=(',',':'))

def _result(before,values,detail,after=None,marks=()):
    return {'before':before,'after':after,'values':values,'marks':sorted(set(marks)),'detail':detail}

def evaluate(spec,root):
    op=spec['op']
    if op in ('relation','files'):
        board=chess.Board(spec['fen']);before=occupancy(board)
        if op=='relation':
            r=native.relations(board,spec['source']);kind=spec['kind']
            if kind in ('attacked','defended'):
                targets=r[kind];values=[len(targets),*targets];marks=targets
            elif kind=='pin':
                values=[len(r['pins']),*(v for row in r['pins'] for v in row)];marks=[v for row in r['pins'] for v in row]
            else:
                values=[int(r['fork']),len(r['attacked']),*r['attacked'],None,None];marks=r['attacked']
            return _result(before,values,r,marks=marks)
        r=native.file_facts(board,spec['side'],spec['file'],spec['pawn'])
        values=[None if r['passed'] is None else int(r['passed']),int(r['open']),int(r['semiopen']),
            len(r['own_file_pawns']),len(r['enemy_file_pawns']),len(r['opposing_exclusions']),*r['opposing_exclusions']]
        return _result(before,values,r,marks=r['opposing_exclusions'])
    if op=='anthology':
        truth,body=load_anthology(root);d=decode_document(body);ordinal=spec['ordinal']
        if type(ordinal) is not int or not 1<=ordinal<=len(d['entries']):raise ValueError('Unknown anthology ordinal.')
        row=truth['canonical_games'][ordinal-1];g=truth['games'][str(row['source_ordinal'])]
        entry=d['entries'][ordinal-1];n=len(g['moves']);ply=spec['ply'];ok=type(ply) is int and 0<=ply<=n
        seeks=spec['seeks'];valid=all(type(i) is int and 0<=i<=n for i in seeks)
        r={'document':2,'ordinal':ordinal,'entry':entry,'trace':entry,'plies':n,'score':g['score'],
            'accepted':ok,'seeks_valid':valid,'seeks':seeks,'score_cause':None,'historical_metadata':None,
            'move_table':d['records'][entry]['data'][0],'score_table':d['records'][entry]['data'][1],
            'schema_table':d['records'][entry]['data'][2],
            'positions':[occupancy(chess.Board(p['fen'])) for p in g['positions']],
            'sides':[p['turn'] for p in g['positions']]}
        return _result(r['positions'][0],[int(ok),2,ordinal,entry,n,ply,g['score'],int(valid),None,None],r,
            r['positions'][ply] if ok else None)
    prefix=spec['prefix'];before=history(prefix)[-1]['occupancy']
    if op in ('discovered','escape','effect','routine'):
        if op=='discovered':r=native.discovered(prefix,spec['move']);effect=r['effect'];values=[int(effect['accepted']),len(r['pairs']),len(r['checks']),*(v for p in r['pairs'] for v in p)];marks=[v for p in r['pairs'] for v in p]
        elif op=='escape':
            r=native.escape(prefix,spec['move']);effect=r['effect']
            values=[int(effect['accepted'])];marks=effect.get('move_probe',{}).get('attackers',[])
        else:
            request={**spec,'op':spec.get('request_op','attempt')}
            effect=practical(request);r={'effect':effect};marks=[]
            if op=='effect':values=[int(effect['accepted']),int(effect['after']['closed']),REASONS.index(effect['after']['reason']),effect['after']['score']]
            else:
                a,b=effect['before'],effect['after'];board=chess.Board(native.coherent(prefix)[0].fen)
                m=chess.Move.from_uci(spec['move']) if spec['kind']=='move' else None
                values=[int(not a['closed']),a['side'],int(a['check']),*map(int,a['eligible']),len(a['legal']),
                    int(effect['accepted']),int(board.is_capture(m)) if m and board.is_pseudo_legal(m) else 0,
                    int(b['check']),int(b['closed']),REASONS.index(b['reason']),b['score'],None]
                r['ordered_stages']=[1,2,3,4,5,6,7,8]
                r['legal']=a['legal'];r['claims']=a['eligible']
        return _result(before,values,r,effect['after']['occupancy'],marks)
    if op=='schedule':
        r=native.scheduled(prefix,spec['moves']);first=r['first_promotion'];last=r['states'][-1]
        values=[len(r['moves']),None if first is None else first['side'],None if first is None else first['ply'],
            None if first is None else first['choice'],int(last['closed']),REASONS.index(last['reason']),last['score'],None]
        return _result(before,values,r,last['occupancy'])
    if op=='proof':
        r=native.proof(prefix,spec['winner'],spec['tree']);nodes=r['nodes']
        values=[int(r['available']),None if r['winning'] is None else 1,r['winner'],len(nodes),
            sum(n['role']=='defender' for n in nodes),sum(len(n['claims']) for n in nodes),
            sum(n['state']['closed'] and n['state']['score']==r['winner'] for n in nodes),
            sum(not n['children'] and not n['state']['closed'] for n in nodes)]
        return _result(before,values,r,nodes[-1]['state']['occupancy'])
    if op!='facts':raise ValueError('Unknown advanced operation.')
    r=native.guidance(prefix);kind=spec['kind'];marks=[];after=None
    if kind=='inventory':values=[*r['material']['counts'][0],*r['material']['counts'][1],*r['material']['totals']]
    elif kind=='scale':values=[*r['material']['scale'],*r['material']['totals'],r['state']['score'],None,None]
    elif kind=='development':values=[len(r['departed']),*r['departed'],None];marks=r['departed']
    elif kind=='center':
        side=spec.get('side',0);marks=r['center_control'][side]
        values=[side,len(marks),*marks,*[v for pair in r['center_occupancy'] for v in pair],None]
    elif kind=='king':values=[int(r['state']['closed']),int(r['check']),len(r['king_routes']),*[cell(m[2:4]) for m in r['king_routes']],None];marks=[cell(m[2:4]) for m in r['king_routes']]
    elif kind in ('activity','restriction','comparison'):
        other=native.guidance(spec['other']);side=r['state']['side']
        if other['state']['side']!=side:raise ValueError('Mobility comparison requires the same side to move.')
        r['comparison']=other;after=other['state']['occupancy'];marks=other['control'][side]
        values=[side,len(r['control'][side]),len(other['control'][side]),len(r['legal']),len(other['legal']),None,None]
    elif kind=='lines':
        board=chess.Board(native.coherent(prefix)[0].fen);side=r['state']['side']
        ff=[native.file_facts(board,side,f) for f in range(8)];opened=[i for i,f in enumerate(ff) if f['open']];semi=[i for i,f in enumerate(ff) if f['semiopen']]
        values=[side,len(opened),*opened,len(semi),*semi,None];marks=[i for i in range(64) if i%8 in opened]
        r['files']=ff
    elif kind=='pawns':
        board=chess.Board(native.coherent(prefix)[0].fen);ff=native.file_facts(board,spec['side'],spec['pawn']%8,spec['pawn']);r['pawn']=ff
        values=[spec['side'],spec['pawn'],int(ff['passed']),len(ff['opposing_exclusions']),*ff['opposing_exclusions'],None]
        marks=ff['opposing_exclusions']
    elif kind=='alternatives':
        alternatives=spec['alternatives'];legal=[m for m in alternatives if m in r['legal']]
        r['alternatives']=[{'move':m,**practical(move(prefix,m))} for m in alternatives]
        values=[len(alternatives),len(legal),*[int(m in legal) for m in alternatives],None];marks=[cell(m[2:4]) for m in legal]
    else:raise ValueError('Unknown exact guidance fact.')
    return _result(before,values,r,after,marks)

def queries(root):
    rows=[];f=fixtures(root)
    def add(family,name,work,practice,variants=(),target=0):
        rows.append({'id':name,'family':family,'strata':[name],'worked_input':work,'input':practice,
            'worked_variants':list(variants),'target':target})
    pin='7k/6b1/8/1r6/4q3/2N5/8/K7 w - - 0 1'
    extra='7k/6b1/8/1r6/4q3/2N5/1P6/K7 w - - 0 1'
    relative='7k/6b1/8/1r6/4q3/2N5/8/Q6K w - - 0 1'
    mirrored=lambda s:{**s,'fen':chess.Board(s['fen']).mirror().fen(),'source':s['source']^56}
    r=local(pin,'attacked');add('T11','attacked_enemy_vs_defended_friendly',r,mirrored(r),
        [local('7k/8/8/8/4p3/2N5/8/K7 w - - 0 1','attacked'),local('7k/8/8/8/4P3/2N5/8/K7 w - - 0 1','defended')])
    r=local(pin,'pin');add('T11','absolute_pin_vs_relative_line',r,mirrored(local(relative,'pin')),
        [local(relative,'pin'),local(extra,'pin'),
         local('4r2k/8/8/8/8/8/4N3/4K3 w - - 0 1','pin','e2'),
         local('4b2k/8/8/8/8/8/4N3/4K3 w - - 0 1','pin','e2')])
    along='e2e4 d7d6 f1b5 c7c6 b1c3'
    add('T11','pinned_piece_can_move_along_ray',{**move(along,'c6b5'),'op':'effect'},
        {**move(along,'c6c5'),'op':'effect'},[local('4k3/8/2p5/1B6/8/8/8/4K3 b - - 0 1','pin','c6'),
         {**move(f['queen'],'h4g3'),'op':'effect'},
         {**move(f['queen']+' h4g3 g1f1','g3f2'),'op':'effect'},
         {**move(f['queen'],'h4h3'),'op':'effect'}])
    r=local(pin,'fork');add('T11','one_piece_geometric_fork_distinct_targets',r,mirrored(r),
        [local(extra,'fork'),local('7k/6b1/8/8/4q3/2N5/8/K7 w - - 0 1','fork'),
         local('7k/8/3r4/8/2N1N3/8/8/K7 w - - 0 1','fork','e4')])
    pinned=('e2e4 e7e5 g1f3 b8c6 f1b5 d7d6 d2d4 h7h6 d4d5 a7a6 d1d4 g8f6 f3e5')
    add('T11','fork_not_guaranteed_profitable_or_legal_capture',local(pin,'fork'),mirrored(local(pin,'fork')),
        [{**move(pinned,'c6d4'),'op':'effect'},{**move(pinned,'c6e5'),'op':'effect'}],target=4)
    disc='b2b3 d7d5 c1b2 e7e6 b1c3 g8f6'
    add('T11','discovered_attack_stationary_slider',coherent('discovered',disc,move='c3b5'),
        coherent('discovered',disc,move='c3d5'),[coherent('discovered',disc,move='b2a3')],target=1)
    dcheck='b2b3 e7e6 c1b2 g8f6 b1c3 f8e7 e2e3 e8f8 d2d3 g7g6 g1f3 f8g7 f1e2 f6h5'
    add('T11','discovered_check_vs_direct_check',coherent('discovered',dcheck,move='c3b5'),
        coherent('discovered',' '.join(SCHOLAR.split()[:-1]),move='h5f7'),target=2)
    esc=('e2e4 g8f6 a2a3 f6g4 a3a4 g4f2 a4a5 f2d1 b2b3 d7d6 b3b4 c8g4 b4b5 g4h3 c2c3 h3g2 e1e2 g2f3')
    safe=' '.join(esc.split()[:16])
    defended='e2e4 e7e5 f1c4 d8h4 d2d3 f8c5 a2a3 c5f2'
    # Reuse the established general attempt relation. Full hypothetical safety
    # remains in the explicitly bound probes, rather than another result schema.
    king_attempt=lambda prefix,text:{**move(prefix,text),'op':'effect'}
    black_king=f['queen']+' h4g3'
    add('T11','escape_square_safety_with_capture_occupancy',king_attempt(esc,'e2d1'),king_attempt(esc,'e2f3'),
        [king_attempt(esc,'e2e3'),
         king_attempt(safe,'e1e2'),king_attempt(safe,'e1f2'),
         king_attempt(esc,'e2d3'),king_attempt(defended,'e1f2'),
         king_attempt(black_king,'g1h1'),king_attempt(black_king,'g1h2')])
    pawn='7k/8/2p5/3P4/8/8/8/K7 w - - 0 1';same='7k/8/8/2pP4/8/8/8/K7 w - - 0 1'
    add('T12','passed_no_enemy_same_or_adjacent_file_ahead',files(pawn),files(chess.Board(pawn).mirror().fen(),1,3,'d4'),
        [files(same),files('7k/8/3p4/3P4/8/8/8/K7 w - - 0 1'),
         files('7k/2p5/8/3P4/8/8/8/K7 w - - 0 1'),files('7k/8/8/3P4/2p5/8/8/K7 w - - 0 1')])
    edge='7k/8/1p6/P7/8/8/8/K7 w - - 0 1';edgeok='7k/8/2p5/P7/8/8/8/K7 w - - 0 1'
    add('T12','edge_file_passed',files(edge,0,0,'a5'),files(edgeok,0,0,'a5'),[files(edgeok,0,0,'a5')])
    add('T12','same_rank_not_ahead',files(same),files(chess.Board(same).mirror().fen(),1,3,'d4'),[files(pawn)])
    inert='7k/8/4N3/2pP4/3P4/8/8/K7 w - - 0 1'
    add('T12','own_pawn_and_nonpawn_do_not_change_predicate',files(same),files(inert),[files(inert)])
    add('T12','open_no_pawns',files(same,0,0,None),files('7k/8/8/2pP4/R7/8/8/K7 w - - 0 1',0,0,None),[files(same,0,2,None)],target=1)
    add('T12','semiopen_side_specific_excludes_open',files(same,0,2,None),files(same,1,3,None),[files(same,0,0,None),files(same,1,2,None)],target=2)
    race=PROMO+' b7a8q g2h1q'
    slow='a2a3 h7h5 a3a4 h5h4 a4a5 h4h3 a5a6 h3g2 a6b7 g2h1q b7a8q'
    add('T12','finite_scheduled_promotion_race',schedule('',race),schedule('',slow),target=1)
    kfast='e7f6 h4h3 g6g7 h3h2 g7g8q';kslow='e7d7 h4g5 d7c7 g5f6 g6g7 f6f7 g7g8q f7g8'
    add('T12','tempo_capture_king_interference_scope',schedule(f['pawn'],kfast),schedule(f['pawn'],kslow),
        [schedule('','a2a4 h7h5 a4a5 h8h6 a5a6 h6a6')],target=2)
    add('T12','first_promotion_not_forced_win',schedule(f['pawn'],kfast),schedule(f['pawn'],kslow),
        [schedule(f['historical_race'],'e6f7 b2b1q f5b1 c7d7'),schedule(f['historical_race'],'d7d8q c7d8 e6f7 b2b1q f5b1')],target=7)
    qproof=certificate(f['queen']);ppr=certificate(f['queen_practice'],mating_tree('f4g3'))
    missing=mating_tree();del missing['children']['h4g3']['children']['g1h1']
    incomplete=certificate(f['queen'],missing);active=certificate(f['queen'],{})
    stale=certificate(f['queen'],{'children':{'h4h3':{}}})
    claims=certificate(CYCLE*2,{},winner=1)
    # One coherent root with two different claim actions makes count unit and
    # side scope observable:5actions,4enabled nodes,1defender claim action.
    clockproof=certificate(f['queen']+' h4h5 g1f1 h5h4 f1g1'*25)
    add('T13','KQK_legal_worked_sequence',schedule(f['queen'],'h4g3 g1f1 g3f2'),schedule(f['queen_practice'],'f4g3 g1h1 g3g2'))
    add('T13','KRK_legal_worked_sequence',schedule(f['rook'],'c3b3 b1a1 h2h1'),schedule(f['rook'],'c3b3 b1c1 h2h1 c1d2'))
    add('T13','king_coordination_and_escape_control',facts(f['queen'],'king'),facts(f['rook'],'king'),[qproof,ppr],target=2)
    add('T13','avoid_stalemate',schedule(f['queen'],'h4h3'),schedule(f['queen'],'h4g3 g1h1 g3g2'),[stale],target=5)
    add('T13','at_least_one_assessed_complete_reply_family',qproof,ppr,[incomplete,active])
    add('T13','all_defender_moves_and_current_draw_claims',qproof,claims,
        [claims,certificate(CYCLE*2,{'children':{'claim:threefold':{}}},winner=1),ppr,clockproof])
    add('T13','terminal_mate_leaves_for_forced_claim',qproof,stale,
        [active,stale,certificate(f['queen'],winner=1)],target=1)
    rooktree={'children':{'c3b3':{'children':{'b1a1':{'children':{'h2h1':{}}}}}}}
    add('T13','cooperative_path_not_forced_proof',certificate(f['rook'],rooktree,1),ppr,[qproof])
    a='e2e4 e7e5';b=a+' g1f3 b8c6'
    add('T14','material_inventory',facts(a,'inventory'),facts(PROMO+' b7a8q g2h1n','inventory'),target=12)
    rich='a2a4 e7e5 a4a5 f8c5 a5a6 d8h4 a6b7 a7a6 b7a8q h4f2'
    add('T14','rough_scale1_3_3_5_9_not_advantage',facts(rich,'scale'),facts(f['pawn']+' '+kslow,'scale'),[facts('','scale')],target=9)
    add('T14','minor_development_observable_departures',facts(CYCLE,'development'),facts(f['queen'],'development'),[facts('','development')])
    add('T14','center_occupancy_control',facts(a,'center'),facts(b,'center',side=1),target=1)
    add('T14','king_safety_facts_and_limits',facts(esc,'king'),facts(f['queen']+' h4h3','king'),target=1)
    add('T14','activity_geometric_vs_legal_count',facts(a,'activity',other=b),facts(b,'activity',other=b+' b1c3 g8f6'),target=3)
    opened='a2a4 b7b5 a4b5 a7a6 b5a6 b8c6 a6a7 a8b8 a7a8q'
    add('T14','open_lines',facts(EP+' e5d6','lines'),facts(rich,'lines'),
        [facts(opened,'lines')],target=1)
    add('T14','restriction_observable_changes',facts(a,'restriction',other=b),facts(b,'restriction',other=b+' b1c3 g8f6'),target=4)
    add('T14','pawn_ideas',facts(f['pawn'],'pawns',side=0,pawn=cell('g6')),facts(EP,'pawns',side=0,pawn=cell('e5')),target=2)
    add('T14','legal_alternative_not_automatically_bad',facts('','alternatives',alternatives=['e2e4','d2d4']),facts(a,'alternatives',alternatives=['g1f3','b1c3']),target=1)
    add('T14','shown_finite_comparison_only',facts(a,'comparison',other=b),facts(b,'comparison',other=b+' b1c3 g8f6'),target=5)
    add('T15','active_state_and_side',routine(move(EP,'e5d6')),routine(move(EP,'a6a5')),
        [routine(move('e2e4','e7e5')),routine(move('e2e4','e4e5'))])
    add('T15','king_safety_and_current_claims',routine(claim(CYCLE*2,0)),routine(claim(CYCLE*2,1)),[routine(claim(CYCLE,0))],target=3)
    add('T15','complete_legal_choices',routine(move(a,'g1f3')),routine(move(esc,'e2f3')),target=5)
    add('T15','inspect_checks_captures_one_move_effects',routine(move(EP,'e5d6')),routine(move(' '.join(SCHOLAR.split()[:-1]),'h5f7')),target=7)
    add('T15','compare_only_shown_finite_continuations',facts(a,'alternatives',alternatives=['g1f3','b1c3']),facts(b,'alternatives',alternatives=['f1c4','d2d5']),target=4)
    add('T15','finite_authored_responses_no_opponent_engine',schedule(EP,'e5d6 e7d6'),schedule(a,'g1f3 b8c6 b1c3'),target=7)
    add('T15','closure_and_postgame_rejection',routine(move(' '.join(SCHOLAR.split()[:-1]),'h5f7')),routine(move(SCHOLAR,'a7a6')),target=6)
    truth,body=load_anthology(root);games=truth['canonical_games'];length=lambda i:len(truth['games'][str(games[i-1]['source_ordinal'])]['moves'])
    add('T16','all_selected_game_ordinals_reachable',anthology(1,0),anthology(64,0),target=2)
    add('T16','every_ply_and_minimal_score_reachable',anthology(1,length(1)),anthology(32,length(32)),target=6)
    add('T16','canonical_order_not_historical_metadata',anthology(7,3),anthology(48,5),target=9)
    add('T16','seek_backward_forward_equivalence',anthology(12,6,[0,8,length(12)+1,3,6]),anthology(55,9,[0,12,4,9]),[anthology(12,length(12)+1)],target=7)
    add('T16','no_descriptions_evaluations_or_inferred_cause',anthology(19,length(19)),anthology(63,length(63)),target=8)
    specs=[s for q in rows for s in [q['worked_input'],q['input'],*q['worked_variants']]]
    for s in specs:
        for k in ('prefix','other'):
            if k in s:s[k]=' '.join(s[k].split())
    prefixes=sorted({s[k] for s in specs for k in ('prefix','other') if k in s})
    contexts=sorted({signature(s) for s in specs})
    for s in specs:
        for key in ('prefix','other'):
            if key in s:s['history_id' if key=='prefix' else 'other_history_id']=prefixes.index(s[key])+1
        s['context_id']=contexts.index(signature(s))+1
    return rows
