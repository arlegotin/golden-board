"""Finite practical lesson inputs. English editorial names never enter the message."""
from .source import source_spans
from .source_game import parse_mainline

CYCLE='g1f3 g8f6 f3g1 f6g8 '
FOOL='f2f3 e7e5 g2g4 d8h4'
SCHOLAR='e2e4 e7e5 f1c4 b8c6 d1h5 g8f6 h5f7'
STALE='e2e3 a7a5 d1h5 a8a6 h5a5 h7h5 a5c7 a6h6 h2h4 f7f6 c7d7 e8f7 d7b7 d8d3 b7b8 d3h7 b8c8 f7g6 c8e6'
SHORT='e2e4 e7e5 g1f3 b8c6 f1c4 g8f6'
LONG='d2d3 g7g6 c1f4 f8g7 b1a3 a7a6 d1d2 b7b6 b2b4 c7c6'
BLACK_SHORT=SHORT+' d2d3 f8c5 c2c3'
BLACK_LONG='e2e4 d7d5 e4d5 d8d5 b1c3 d5d6 g1f3 b8c6 d2d4 c8f5 c1f4'
RIGHTS_OK=SHORT+' b1c3 f8c5 c3b1 a7a6'
KING_BACK=SHORT+' e1e2 f8c5 e2e1 a7a6'
ROOK_BACK=SHORT+' h1g1 f8c5 g1h1 a7a6'
REPLACEMENT=('a2a4 h7h5 a4a5 h5h4 a5a6 h4h3 a6b7 h3g2 b7a8r g8f6 '
    'a1a3 b8c6 a8a7 d7d6 a3h3 d6d5 a7a1 e7e6 d2d3 f8e7 c1f4 e8g8 b1c3 g7g6 d1d2 g6g5')
EP='e2e4 a7a6 e4e5 d7d5'
BLACK_EP='a2a3 e7e5 a3a4 e5e4 d2d4'
PINNED_EP=('e2e4 e7e6 f2f4 g8f6 f4f5 e6f5 e4e5 f6g4 '
    'g1f3 f8e7 d2d4 e8g8 b1c3 f8e8 f1d3 e7f8 d1d2 d7d5')
PROMO='a2a4 h7h5 a4a5 h5h4 a5a6 h4h3 a6b7 h3g2'

def observe(prefix):return {'op':'observe','prefix':prefix}
def move(prefix,text):return {'op':'attempt','prefix':prefix,'kind':'move','move':text}
def claim(prefix,actor,reason='threefold'):return {'op':'attempt','prefix':prefix,'kind':'claim','actor':actor,'reason':reason}
def compare(prefix,other):return {'op':'compare','prefix':prefix,'other':other}
def material(board):return {'op':'material','fen':board+' w - - 0 1'}
def record(prefix,score,ply=None,length=None):
    n=len(prefix.split());return {'op':'record','prefix':prefix,'length':n if length is None else length,'ply':n if ply is None else ply,'score':score}

def dead_prefix(root):
    """Exact qualified source witness, plus explicit non-source test continuation."""
    span=source_spans(root)['records'][44]
    game=parse_mainline((root/'inputs/anthology.pgn').read_bytes()[span['start']:span['end']])
    def square(i):return chr(97+i%8)+str(8-i//8)
    return ' '.join(square(a)+square(b)+('', 'q','r','b','n')[p] for a,b,p in game['moves'])

def practical_queries(root):
    rows=[]
    def add(family,name,work,practice=None,*,also=(),variants=(),rival='accepted'):
        if practice is None:
            practice={**work}
            if 'prefix' in work:practice['prefix']=CYCLE+work['prefix']
            if 'other' in work:practice['other']=CYCLE+work['other']
        rows.append({'family':family,'id':name,'strata':[name,*also],
            'worked_input':work,'input':practice,'worked_variants':list(variants),'rival_kind':rival})

    add('T4','no_moves_with_check_mate',observe(FOOL),observe(SCHOLAR),rival='reason',
        variants=[observe(STALE),observe('e2e4 e7e5 f2f3 d8h4')])
    add('T4','no_moves_without_check_stalemate',observe(STALE),also=['matched_check_status_contrast'],
        variants=[observe(FOOL)],rival='reason')
    add('T4','check_with_evasion_not_mate',observe('e2e4 e7e5 f2f3 d8h4'),
        observe('e2e4 e7e5 f1c4 b8c6 d1h5 g8f6 h5e5'),also=['all_relevant_replies'],rival='closed')
    add('T4','post_terminal_rejection',move(FOOL,'a2a3'),move(STALE,'a7a6'),
        variants=[move('e2e4 e7e5 f2f3 d8h4','a2a3')])

    for name,prefix,text in [('first_short',SHORT,'e1g1'),('first_long',LONG,'e1c1'),
                            ('second_short',BLACK_SHORT,'e8g8'),('second_long',BLACK_LONG,'e8c8')]:
        add('T5',name,move(prefix,text),also=['correct_rook_update'] if name=='first_short' else (),rival='rook')
    add('T5','king_moved_then_returned',move(KING_BACK,'e1g1'),variants=[move(RIGHTS_OK,'e1g1')])
    add('T5','rook_moved_then_returned',move(ROOK_BACK,'e1g1'),variants=[move(RIGHTS_OK,'e1g1')])
    add('T5','rook_captured_right_lost',move(PROMO+' b7a8q','e8c8'),rival='rights',
        variants=[move(PROMO,'b7a8q')])
    add('T5','promoted_replacement_no_right_restore',move(REPLACEMENT,'e1c1'))
    blocked=LONG.replace('b1a3','h2h3')
    add('T5','king_rook_path_empty_including_b_file',move(blocked,'e1c1'),variants=[move(LONG,'e1c1')])
    for name,prefix in [
        ('origin_attacked','e2e4 e7e5 g1h3 b8c6 f1c4 a7a6 d2d3 f8b4'),
        ('transit_attacked_after_king_vacates','e2e4 b7b6 g1f3 e7e6 f1c4 c8a6 c4b3 g8f6'),
        ('destination_attacked_after_both_move','e2e4 e7e5 g1h3 f8c5 f1c4 b8c6 f2f3 a7a6')]:
        add('T5',name,move(prefix,'e1g1'),variants=[move(SHORT,'e1g1')])
    battack='d2d3 b8c6 c1f4 c6a5 b1c3 a5c4 d1d2 c4a3 e2e3 a7a6'
    add('T5','attacked_rook_or_b_file_allowed',move(LONG,'e1c1'),move(battack,'e1c1'),
        variants=[move(battack,'e1c1')])

    add('T6','immediate_double_move_opportunity',move(EP,'e5d6'),move(BLACK_EP,'e4d3'),
        also=['captured_pawn_removed_off_destination','both_sides_direction'],rival='ep',
        variants=[move(BLACK_EP,'e4d3')])
    add('T6','declined_opportunity_expires',move(EP+' '+CYCLE,'e5d6'),
        move(BLACK_EP+' g8f6 g1f3 f6g8 f3g1','e4d3'),also=['same_occupancy_different_timing'],
        variants=[move(EP,'e5d6'),move(BLACK_EP,'e4d3')])
    add('T6','self_check_discovered_line_reject',move(PINNED_EP,'e5d6'),
        variants=[move(EP,'e5d6')])

    for side,prefix,origin in [('first',PROMO,'b7a8'),('second',PROMO+' b7a8q','g2h1')]:
        for name,suffix in [('queen','q'),('rook','r'),('bishop','b'),('knight','n')]:
            add('T7',side+'_'+name,move(prefix,origin+suffix),rival='promotion')
    add('T7','explicit_mandatory_choice',move(PROMO,'b7a8'),move(PROMO+' b7a8q','g2h1'),
        also=['missing_or_invalid_choice_reject'],variants=[move(PROMO,'b7a8q'),move(PROMO,'b7a8k'),move(PROMO,'b7a8p'),
            move('a2a4 h7h5 a4a5 h5h4 a5a6 b8c6 a6b7 h4h3','b7b8q'),
            move('g1f3 g8f6 '+PROMO+' b7a8q','g2g1n')])
    add('T7','capture_promotion',move(PROMO,'b7a8n'),move(PROMO+' b7a8q','g2h1b'),rival='promotion')
    add('T7','immediate_new_piece_control',move(PROMO,'b7a8r'),move(PROMO+' b7a8q','g2h1n'),
        variants=[move(PROMO,'b7a8'+s) for s in 'qrbn'],rival='promotion')

    base='e2e3 e7e6 d2d3 a7a6'
    add('T8','same_board_different_side',compare(base,base+' d1d2 g8f6 d2e2 f6g8 e2d1'),rival='equal_key')
    add('T8','same_board_lost_rights',compare(RIGHTS_OK,KING_BACK),rival='equal_key',
        variants=[compare(RIGHTS_OK,ROOK_BACK)])
    add('T8','legal_ep_key_difference',compare(EP,EP+' '+CYCLE),rival='equal_key')
    add('T8','unusable_ep_ignored',compare('e2e4','e2e4 g8f6 g1f3 f6g8 f3g1'),rival='equal_key')
    add('T8','pinned_ep_ignored',compare(PINNED_EP,PINNED_EP+' c3b1 g4f6 b1c3 f6g4'),rival='equal_key')
    add('T8','initial_occurrence_one',observe(''),observe(CYCLE),rival='repeat')
    add('T8','current_key_count_not_elapsed_plies',observe(CYCLE*2),observe(CYCLE*2+' e2e4'),
        also=['coherent_occupancy_clock_and_history'],
        variants=[observe(CYCLE*2+' g1f3'),observe('g1f3 g8f6 b1c3 b8c6 c3b1 c6b8 f3g1 f6g8')],rival='repeat')

    add('T9','current_third_occurrence_not_prospective',claim(' '.join((CYCLE*2).split()[:-1]),1),
        claim(CYCLE*2,0),variants=[claim(CYCLE*2,0)])
    add('T9','halfmoves99_100',claim(' '.join((CYCLE*25).split()[:-1]),1,'fifty-move'),
        claim(CYCLE*25,0,'fifty-move'),variants=[claim(CYCLE*25,0,'fifty-move')])
    capture='e2e4 e7e5 g1f3 b8c6 f1b5 g8f6'
    add('T9','pawn_and_capture_reset',move(CYCLE*25,'e2e4'),move(capture,'b5c6'),
        variants=[move(capture,'b5c6')],rival='clock')
    add('T9','eligibility_not_automatic_closure',observe(CYCLE*2),observe(CYCLE*40),
        also=['excluded_fivefold_75move'],variants=[observe(CYCLE*40)],rival='closed')
    add('T9','claimant_side_and_active_state',claim(CYCLE*2,1),claim(FOOL,0),
        variants=[claim(CYCLE*2,0),claim(FOOL,0),
            claim('f2f3 e7e5 '+('b1c3 b8c6 c3b1 c6b8 '*25)+'b1c3 d8h4',0,'fifty-move')])
    add('T9','resignation_either_side',{'op':'attempt','prefix':'e2e4','kind':'resign','actor':0},
        {'op':'attempt','prefix':'e2e4','kind':'resign','actor':1},
        variants=[{'op':'attempt','prefix':'','kind':'resign','actor':1}],rival='score')
    add('T9','agreement_two_consents_after_both_move',{'op':'attempt','prefix':'e2e4 e7e5','kind':'agree','consents':[0,1]},
        {'op':'attempt','prefix':'d2d4 d7d5','kind':'agree','consents':[1,0]},
        variants=[{'op':'attempt','prefix':p,'kind':'agree','consents':c} for p,c in [('',[0,1]),('e2e4',[0,1]),('e2e4 e7e5',[0]),('e2e4 e7e5',[0,0])]])
    add('T9','invalid_declarations_atomic',{'op':'attempt','prefix':'e2e4 e7e5','kind':'agree','consents':[1,1]},
        {'op':'attempt','prefix':'d2d4 d7d5','kind':'resign','actor':2},
        variants=[{'op':'attempt','prefix':FOOL,'kind':k,**args} for k,args in [('resign',{'actor':0}),('agree',{'consents':[0,1]})]])
    common=['7k/8/8/8/8/8/8/K7','7k/8/8/8/8/8/8/KB6','7k/8/8/8/8/8/8/KN6',
            '1b5k/8/8/8/8/8/8/K7','1n5k/8/8/8/8/8/8/K7']
    add('T9','KK_KBK_KNK_both_colors',material(common[0]),material(common[-1]),
        variants=[material(b) for b in common[1:]],rival='material')
    outside=['7k/8/8/8/8/8/8/KNN5','5b1k/8/8/8/8/8/8/K1B5','7k/8/8/8/8/8/8/KR6','7k/8/8/8/8/8/P7/K7']
    add('T9','other_material_outside_profile',material(outside[0]),material(outside[1]),
        variants=[material(b) for b in outside[2:]],rival='material')
    dead=dead_prefix(root)+' b3b4 h3b3'
    priority='f2f3 e7e5 g2g4 '+('b8c6 b1c3 c6b8 c3b1 '*25)
    add('T9','mate_stalemate_dead_closure_priority',move(priority,'d8h4'),move(dead,'b4b3'),
        variants=[move(' '.join(STALE.split()[:-1]),STALE.split()[-1]),move(dead,'b4b3')],rival='reason')
    add('T9','recorded_score_unspecified_cause',record('e2e4 e7e5',0),record('d2d4 d7d5',2),rival='record_cause')
    add('T9','scope_exclusions',claim(CYCLE*2,0,'prospective-threefold'),claim(CYCLE*40,0,'fivefold'),
        variants=[claim(CYCLE*40,0,'seventy-five'),claim(CYCLE*40,0,'fifty-move')])

    add('T10','origin_destination_and_explicit_promotion',record(PROMO+' b7a8n',0),
        record(PROMO+' b7a8q g2h1b',1),rival='promotion')
    add('T10','record_order_and_length_boundary',record(SHORT+' e1g1',2,3),
        record(BLACK_LONG+' e8c8',1,5),also=['standard_start_full_replay','every_intermediate_turn_and_board'],
        variants=[record(SHORT+' e1g1',2,8)],rival='side')
    add('T10','minimal_score_no_cause',record(SHORT,1),record(BLACK_SHORT,0),rival='record_cause')
    add('T10','partial_prefix_not_complete_game',record('e2e4 e7e5 g1f3',0,2,4),
        record('d2d4 d7d5 c1f4',2,2,5),variants=[record('e2e4 e7e5 g1f3',0,2)],rival='complete')
    specs=[s for q in rows for s in [q['worked_input'],q['input'],*q['worked_variants']]]
    for s in specs:
        for key in ('prefix','other'):
            if key in s:s[key]=' '.join(s[key].split())
    prefixes=sorted({s[k] for s in specs for k in ('prefix','other') if k in s})
    for s in specs:
        if 'prefix' in s:s['history_id']=prefixes.index(s['prefix'])+1
        if 'other' in s:s['other_history_id']=prefixes.index(s['other'])+1
    records=[s for s in specs if s['op']=='record']
    identities=sorted({(s['prefix'],s['length'],s['score']) for s in records})
    for s in records:s['record_id']=identities.index((s['prefix'],s['length'],s['score']))+1
    return rows
