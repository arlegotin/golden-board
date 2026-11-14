"""Complete remaining-course claims require real carried material, not labels."""
from pathlib import Path
from copy import deepcopy
import importlib.util,hashlib,json,subprocess,tomllib,unittest

ROOT=Path(__file__).resolve().parents[1]

class AdvancedCourseTests(unittest.TestCase):
    def product(self):
        self.assertIsNotNone(importlib.util.find_spec('golden_board.course_advanced'),
                             'The remaining48strata have no serialized teaching.')
        from golden_board.course_advanced import build_advanced
        if not hasattr(type(self),'_product'):type(self)._product=build_advanced(ROOT)
        return type(self)._product

    def test_king_attempts_share_general_results_and_full_both_side_probes(self):
        import chess
        from golden_board.advanced_cases import evaluate
        from golden_board.course_practical import digits, bit, _decoded_frames
        from golden_board.document import decode_document
        p=self.product(); doc=decode_document(p['document'])
        q=next(q for g in p['groups'] for q in g['queries']
               if q['id']=='escape_square_safety_with_capture_occupancy')
        specs=[q['worked_input'],*q['worked_variants'],q['input']]
        self.assertEqual(len(specs),9)
        colored_accept=set(); black_requests=set()
        token=lambda piece:0 if piece is None else 31+piece.piece_type+(0 if piece.color else 6)
        cell=lambda square:(7-chess.square_rank(square))*8+chess.square_file(square)
        for index,spec in enumerate(specs):
            self.assertEqual((spec['op'],spec['kind']),('effect','move'),
                             'King safety still introduces a separate result language.')
            b=chess.Board()
            for text in spec['prefix'].split():
                m=chess.Move.from_uci(text);self.assertIn(m,b.legal_moves);b.push(m)
            m=chess.Move.from_uci(spec['move']);side=b.turn
            self.assertEqual(b.piece_at(m.from_square),chess.Piece(chess.KING,side))
            self.assertFalse(b.is_game_over());self.assertIn(m,b.pseudo_legal_moves)
            self.assertFalse(b.is_castling(m));accepted=m in b.legal_moves
            h=b.copy();h.push(m);actual=h if accepted else b
            attackers=sorted(cell(x)for x in h.attackers(not side,h.king(side)))
            colored_accept.add((side,accepted))
            if not side:
                black_requests.add((spec['move'],accepted))
                if spec['move']=='g1h2':
                    self.assertTrue(attackers)
                    self.assertFalse(h.attackers(chess.BLACK,h.king(chess.WHITE)),
                                     'Black danger must differ from fixed White focus.')
            result=evaluate(spec,ROOT)
            self.assertEqual(result['values'],[int(accepted),0,0,None])
            self.assertEqual(result['marks'],[])
            frame=q['worked'][index]if index<len(q['worked'])else q['options'][q['correct']]
            self.assertEqual(frame[208:210],digits(10,2))
            for i,value in enumerate([int(accepted),0,0,None]):
                base=(10+i)*26
                self.assertEqual(frame[base:base+2],digits(i+1,2))
                self.assertEqual(frame[base+3],bit(value is not None))
                self.assertEqual(frame[base+5:base+9],digits(value)if value is not None else [0]*4)
            for i in range(4,24):
                base=(10+i%12)*26+(13 if i>=12 else 0)
                self.assertEqual(frame[base:base+12],[0]*12)
            self.assertEqual([frame[(i//8)*26+9+i%8]for i in range(64)],
                             [token(actual.piece_at(chess.square(i%8,7-i//8)))for i in range(64)])
            self.assertFalse(any(frame[(i//8)*26+18+i%8]for i in range(64)))
            probe=_decoded_frames(doc,p['probes'][str(spec['context_id'])])[p['probe_steps'][str(spec['context_id'])]]
            self.assertEqual([probe[(i//8)*26+9+i%8]for i in range(64)],
                             [token(h.piece_at(chess.square(i%8,7-i//8)))for i in range(64)])
            self.assertEqual([i for i in range(64)if probe[(i//8)*26+18+i%8]],attackers)
            self.assertEqual(probe[22*26+2],bit(bool(attackers)))
        self.assertEqual(colored_accept,{(True,True),(True,False),(False,True),(False,False)})
        self.assertEqual(black_requests,{('g1h1',True),('g1h2',False)})
        # The current document must not retain the independently taught op4.
        for node,r in doc['records'].items():
            if r['kind']!=4:continue
            for frame in _decoded_frames(doc,node):
                if len(frame)>=23*26:self.assertNotEqual(frame[208:210],digits(4,2))

    def test_escape_source_separates_domain_capture_and_occupancy_rivals(self):
        # Removing a quiet-origin or unsafe-checker positive must fail this test.
        import chess
        from golden_board.advanced_cases import evaluate
        from golden_board.course_practical import digits, bit, _decoded_frames
        from golden_board.document import decode_document
        p = self.product(); doc = decode_document(p['document'])
        q = next(q for g in p['groups'] for q in g['queries']
                 if q['id'] == 'escape_square_safety_with_capture_occupancy')
        specs = [q['worked_input'], *q['worked_variants'], q['input']]
        old = q['worked_input']['prefix']; safe = ' '.join(old.split()[:16])
        defended = 'e2e4 e7e5 f1c4 d8h4 d2d3 f8c5 a2a3 c5f2'
        required = {(safe, 'e1e2'), (safe, 'e1f2'), (old, 'e2d3'), (defended, 'e1f2')}
        self.assertTrue(required <= {(s['prefix'], s['move']) for s in specs},
                        'The source still lacks the four discriminating positive observations.')
        check_accept = set(); refuted = set(); capture_accept = set()
        for index, spec in enumerate(specs):
            b = chess.Board()
            for text in spec['prefix'].split():
                m = chess.Move.from_uci(text); self.assertIn(m, b.legal_moves); b.push(m)
            m = chess.Move.from_uci(spec['move']); side = b.turn
            self.assertFalse(b.is_game_over()); self.assertIn(m, b.pseudo_legal_moves)
            self.assertEqual(b.piece_at(m.from_square), chess.Piece(chess.KING, side))
            self.assertFalse(b.is_castling(m))
            accepted = m in b.legal_moves; before = set(b.attackers(not side, b.king(side)))
            h = b.copy(); h.push(m); after = set(h.attackers(not side, h.king(side)))
            actual = h if accepted else b; actual_attackers = set(actual.attackers(not side, actual.king(side)))
            r = evaluate(spec, ROOT); self.assertEqual(r['values'], [int(accepted),0,0,None])
            expected_marks=sorted((7-chess.square_rank(x))*8+chess.square_file(x) for x in after)
            self.assertEqual(r['marks'], [])
            check_accept.add((bool(before), accepted)); capture_accept.add((b.is_capture(m), accepted))
            scalar_rivals = {'actual_safety': int(not actual_attackers),
                'check_evasion_only': int(bool(before) and not after),
                'safe_checker_capture': int(accepted and m.to_square in before),
                'checker_capture': int(m.to_square in before)}
            refuted.update(k for k,v in scalar_rivals.items() if v != int(accepted))
            if not before and accepted: refuted.add('check_gated_result_board')
            if not before and after: refuted.add('check_gated_hypothetical_mask')
            token = lambda piece: 0 if piece is None else 31+piece.piece_type+(0 if piece.color else 6)
            cells = [chess.square(i%8, 7-i//8) for i in range(64)]
            frame = q['worked'][index] if index < len(q['worked']) else q['options'][q['correct']]
            self.assertEqual(frame[10*26+5:10*26+9], digits(int(accepted)))
            self.assertEqual([frame[(i//8)*26+9+i%8] for i in range(64)], [token(actual.piece_at(x)) for x in cells])
            self.assertEqual([i for i in range(64) if frame[(i//8)*26+18+i%8]], r['marks'])
            if index < len(q['worked']):self.assertEqual(frame[22*26+3], 6)
            probe = _decoded_frames(doc, p['probes'][str(spec['context_id'])])[p['probe_steps'][str(spec['context_id'])]]
            self.assertEqual([probe[(i//8)*26+9+i%8] for i in range(64)], [token(h.piece_at(x)) for x in cells])
            self.assertEqual([i for i in range(64) if probe[(i//8)*26+18+i%8]], expected_marks)
            self.assertEqual(probe[22*26+2], bit(bool(after)))
            self.assertEqual(probe[8*26+4:8*26+9], [22 if v==0 else 12+v for v in
                [7-chess.square_rank(m.from_square), chess.square_file(m.from_square),
                 7-chess.square_rank(m.to_square), chess.square_file(m.to_square), 0]])
        self.assertEqual(check_accept, {(False, False), (False, True), (True, False), (True, True)})
        self.assertEqual(capture_accept, {(False, False), (False, True), (True, False), (True, True)})
        self.assertEqual(refuted, {'actual_safety','check_evasion_only','safe_checker_capture','checker_capture',
                                  'check_gated_result_board','check_gated_hypothetical_mask'})

    def test_escape_probes_share_literal_trace_with_exact_request_steps(self):
        # Sharing must not make every context accidentally return the last probe.
        from golden_board.course_practical import _decoded_frames
        from golden_board.document import decode_document
        p = self.product(); doc = decode_document(p['document'])
        q = next(q for g in p['groups'] for q in g['queries']
                 if q['id'] == 'escape_square_safety_with_capture_occupancy')
        specs = [q['worked_input'], *q['worked_variants'], q['input']]
        nodes = {p['probes'][str(s['context_id'])] for s in specs}
        self.assertEqual(len(nodes), 1, 'Probe diagrams still duplicate full initial records.')
        node = next(iter(nodes)); frames = _decoded_frames(doc, node)
        steps = [p['probe_steps'][str(s['context_id'])] for s in specs]
        self.assertEqual(sorted(steps), list(range(9))); self.assertEqual(len(frames), 9)
        case = next(c for c in p['cases'] if any(a['id']==q['id'] for a in c['queries']))
        script = """
import {readFileSync} from 'node:fs';import {decodeDocument,Player} from './mechanism/player.mjs';
const x=JSON.parse(readFileSync(0,'utf8')),p=new Player(decodeDocument(Buffer.from(x.body,'hex')),x.entry);
if(!p.action({link:x.probe}).ok)throw Error('probe unreachable by ordinary link');
const out=x.steps.map(step=>{if(!p.action({seek:step}).ok)throw Error('seek failed');return p.packet().frame.cells;});
process.stdout.write(JSON.stringify(out));
"""
        order = steps + list(reversed(steps))
        run = subprocess.run(['node','--input-type=module','-e',script], cwd=ROOT,
            input=json.dumps({'body':p['document'].hex(),'entry':case['worked'],'probe':node,'steps':order}),
            capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(run.stdout), [frames[i] for i in order])

    def test_escape_attacker_table_binds_each_probe_step_including_empty_masks(self):
        import chess
        from golden_board.document import decode_document
        p = self.product(); doc = decode_document(p['document'])
        q = next(q for g in p['groups'] for q in g['queries']
                 if q['id'] == 'escape_square_safety_with_capture_occupancy')
        specs = [q['worked_input'], *q['worked_variants'], q['input']]
        node = p['probes'][str(specs[0]['context_id'])]
        trace = doc['records'][doc['records'][node]['display']]
        self.assertEqual(len(trace['data']),2, 'Every step needs explicit focal identity, including safe steps.')
        focal=doc['records'][trace['data'][0]]
        self.assertEqual(focal['cols'],3)
        actual_focal=[focal['values'][i:i+3]for i in range(0,len(focal['values']),3)]
        table = doc['records'][trace['data'][1]]
        self.assertEqual(table['cols'],4)
        actual = [table['values'][i:i+4] for i in range(0,len(table['values']),4)]
        expected = [];expected_focal=[]
        for spec in sorted(specs, key=lambda s:p['probe_steps'][str(s['context_id'])]):
            b = chess.Board()
            for text in spec['prefix'].split():b.push_uci(text)
            side = b.turn; b.push(chess.Move.from_uci(spec['move'])); step = p['probe_steps'][str(spec['context_id'])]
            cell = lambda x:(7-chess.square_rank(x))*8+chess.square_file(x)
            attackers = sorted(cell(x) for x in b.attackers(not side,b.king(side)))
            expected_focal.append([step,3,cell(b.king(side))])
            rows = [[step,3,cell(b.king(side)),a] for a in attackers]
            self.assertEqual([r for r in actual if r[0]==step],rows)
            expected.extend(rows)
        self.assertEqual(actual,expected)
        self.assertEqual(actual_focal,expected_focal)

    def test_general_attempt_calibration_uses_complete_worked_route(self):
        from golden_board.course_practical import _decoded_frames,digits
        from golden_board.document import decode_document
        p=self.product();doc=decode_document(p['document'])
        calibration=doc['records'][p['calibration']]
        # The independent request-only/result pair is removed; its existing
        # ordinary route carries requests and every general result together.
        self.assertFalse(any(f[208:210]==digits(10,2)
                             for f in _decoded_frames(doc,p['calibration'])))
        first=p['cases'][0]['worked']
        self.assertIn(first,calibration['links'])
        frames=_decoded_frames(doc,first)
        intro=[f for f in frames if f[208:210]==digits(10,2)and f[575]==6]
        self.assertTrue(intro)
        for f in intro:
            self.assertTrue(any(f[248:253]),'General request operands omitted.')
            for i in range(4):self.assertEqual(f[(10+i)*26:(10+i)*26+2],digits(i+1,2))
        q=next(q for q in p['groups'][0]['queries']
               if q['id']=='escape_square_safety_with_capture_occupancy')
        self.assertTrue(all(f in [shown[:23*26]for shown in frames]for f in q['worked']))

    def test_full_family_groups_preserve_all_observations_and_finite_practice(self):
        from golden_board.document import decode_document
        from golden_board.course_practical import _decoded_frames
        p = self.product(); doc = decode_document(p['document'])
        family_groups = {}
        for group in p['groups']:family_groups.setdefault(group['id'].split('-')[0],[]).append(group)
        self.assertEqual({f:len(gs) for f,gs in family_groups.items()},
                         {'T11':1,'T12':2,'T13':1,'T14':2,'T15':1,'T16':1})
        self.assertEqual(sum(len(g['queries']) for g in p['groups']),48)
        for group, case in zip(p['groups'],p['cases']):
            self.assertLessEqual(len(group['queries']),8)
            self.assertEqual(len(case['expected']),len(group['queries']))
            practice = doc['records'][case['practice']]
            self.assertEqual(practice['accepted'],[case['expected']])
            work = _decoded_frames(doc,case['worked']); passive = _decoded_frames(doc,case['passive'])
            shown_practice = _decoded_frames(doc,case['practice'])
            for source,binding in zip(group['queries'],case['queries']):
                for role in ('worked','contrast'):
                    start,end = binding[role+'_steps']
                    self.assertEqual([f[:23*26] for f in work[start:end+1]],source[role])
                start,end = binding['practice_steps']
                self.assertEqual([f[:23*26] for f in shown_practice[start:end+1]],source['options'])
                start,end = binding['passive_steps']; shown = passive[start:end+1]
                self.assertEqual([f[:23*26] for f in shown[:-1]], [f for option in source['options'] for f in (option,option)])
                self.assertEqual(shown[-1][:23*26],source['options'][source['correct']])

    def test_repaired_worked_observations_separate_the_actual_p31_rivals(self):
        from golden_board.advanced_cases import evaluate
        from golden_board.course_practical import digits
        p = self.product()
        variants = [(s, evaluate(s, ROOT), q['worked'][i+1])
                    for g in p['groups'] for q in g['queries']
                    for i, s in enumerate(q['worked_variants'])]
        proofs = [(s, r, frame) for s, r, frame in variants if s['op'] == 'proof']
        counts = [(sum(len(n['claims']) for n in r['detail']['nodes']),
                   sum(bool(n['claims']) for n in r['detail']['nodes']),
                   sum(len(n['claims']) for n in r['detail']['nodes'] if n['role'] == 'defender'))
                  for s, r, frame in proofs]
        self.assertIn((5, 4, 1), counts,
                      'Carried proof examples still alias claim actions/nodes/defenders.')
        _, count_result, frame = proofs[counts.index((5, 4, 1))]
        self.assertFalse(count_result['detail']['available'])
        self.assertEqual(frame[15*26+5:15*26+9], digits(5))
        self.assertTrue(any(r['values'][6] == 0 and
                            sum(n['state']['reason'] == 'checkmate' for n in r['detail']['nodes']) == 2
                            for s, r, frame in proofs), 'Winning-goal leaves still alias any mate.')
        effects = [r['values'] for s, r, frame in variants if s['op'] == 'effect']
        self.assertTrue(all(v in effects for v in ([1, 0, 0, None], [1, 1, 1, 0], [1, 1, 2, 2])),
                        'Effect displays must separate check, closure, reason and result.')
        self.assertTrue(any(s['op'] == 'effect' and r['detail']['effect']['after']['check']
                            and r['values'][1] == 0 for s, r, frame in variants),
                        'An ongoing check must actually distinguish check from closure.')
        self.assertTrue(any(s['op'] == 'facts' and s['kind'] == 'lines' and
                            r['values'] == [1, 1, 0, 1, 1, None]
                            for s, r, frame in variants), 'Open-file count remains observed-zero only.')

    def test_all48_strata_have_carried_truth_practice_and_passive_routes(self):
        p=self.product()
        required={s for f in tomllib.loads((ROOT/'content/coverage.toml').read_text())['family'][11:] for s in f['critical_strata']}
        self.assertEqual(len(required),48);self.assertEqual(set(p['bindings']),required)
        self.assertEqual(p['truth']['strata'],48)
        request={'documents':{'5':p['document'].hex()},'cases':p['cases']}
        run=subprocess.run(['node',str(ROOT/'tools/audit-course.mjs')],input=json.dumps(request),capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        report=json.loads(run.stdout)
        self.assertTrue(report['all_frames_exact'] and report['all_actions_exact'] and report['passive_without_response'])

    def test_proof_has_all_defenses_and_explicit_unavailable_contrasts(self):
        p=self.product();qs={q['id']:q for g in p['groups'] for q in g['queries']}
        q=qs['at_least_one_assessed_complete_reply_family']
        self.assertTrue(q['worked_expected']['detail']['available']);self.assertTrue(q['expected']['detail']['available'])
        types={e for q in qs.values() for s in q['worked_variants'] if s['op']=='proof'
               for e in __import__('golden_board.advanced_cases',fromlist=['evaluate']).evaluate(s,ROOT)['detail']['errors']}
        self.assertTrue({'missing-defender-reply','active-leaf','nonwinning-leaf'}<=types)
        self.assertTrue(p['proofs']);self.assertTrue(p['contexts'])

    def test_unavailable_is_not_false_or_a_ranked_move(self):
        p=self.product();qs={q['id']:q for g in p['groups'] for q in g['queries']}
        for name in ('rough_scale1_3_3_5_9_not_advantage','legal_alternative_not_automatically_bad','shown_finite_comparison_only'):
            self.assertIn(None,qs[name]['expected']['values'])
        self.assertEqual(qs['legal_alternative_not_automatically_bad']['expected']['values'][:2],[2,2])
        q=qs['first_promotion_not_forced_win'];self.assertIn(None,q['expected']['values'])

    def test_anthology_references_bind_all64_exact_complete_records(self):
        p=self.product();rows=p['anthology_inventory']
        self.assertEqual(len(rows),64);self.assertEqual([r[1] for r in rows],list(range(1,65)))
        self.assertEqual(sum(r[4] for r in rows),6890)
        self.assertTrue(all(r[0]==2 and r[2]==r[3] for r in rows))
        self.assertTrue(all(len(r)==9 for r in rows));self.assertEqual(len({r[8] for r in rows}),1)

    def test_actual_frame_or_proof_domain_mutation_is_rejected(self):
        from golden_board.document import decode_document,encode_document
        from golden_board.course_advanced import validate_advanced
        p=deepcopy(self.product());d=decode_document(p['document'])
        node=next(iter(p['proofs'].values()));trace=d['records'][d['records'][node]['display']]
        table=d['records'][trace['data'][0]];table['values'][-1]^=1
        p['document']=encode_document(d['entries'],list(d['records'].values()))
        digest=hashlib.sha256(p['document']).hexdigest()
        for rows in p['bindings'].values():
            for row in rows:row['document_sha256']=digest
        with self.assertRaises(ValueError):validate_advanced(p,ROOT)

    def test_routine_carries_actor_reason_and_reveals_ordered_checks(self):
        from golden_board.course_practical import _decoded_frames,COLS
        from golden_board.document import decode_document
        p=self.product();qs={q['id']:q for g in p['groups'] for q in g['queries']}
        q=qs['king_safety_and_current_claims']
        self.assertEqual(q['worked'][0][9*COLS+14],3)
        self.assertTrue(all(f[9*COLS+14]==4 for f in q['options']))
        self.assertNotEqual(q['worked'][0][9*COLS+16],0)
        spec=q['worked_input'];node=p['details'][str(spec['context_id'])]
        frames=_decoded_frames(decode_document(p['document']),node)
        self.assertEqual(len(frames),8)
        for row in range(8):self.assertEqual(frames[0][row*COLS+9:row*COLS+17],[0]*8)
        self.assertEqual(frames[0][10*COLS+11],5,'First check must highlight the active field.')
        self.assertEqual(frames[0][16*COLS:16*COLS+12],[0]*12,'Future acceptance is not revealed before its stage.')

    def test_worked_relations_break_pin_and_immediate_pawn_rivals(self):
        from golden_board.advanced_cases import queries,evaluate
        qs={q['id']:q for q in queries(ROOT)}
        q=qs['one_piece_geometric_fork_distinct_targets']
        results=[evaluate(s,ROOT)['detail'] for s in [q['worked_input'],*q['worked_variants']]]
        self.assertTrue(any(r['fork'] and not r['pins'] for r in results),'Fork must be demonstrated independently of pin.')
        q=qs['passed_no_enemy_same_or_adjacent_file_ahead']
        specs=[q['worked_input'],*q['worked_variants']]
        own=distant=False
        for s in specs:
            for target in evaluate(s,ROOT)['detail']['opposing_exclusions']:
                own |= target%8==s['pawn']%8
                distant |= abs(target//8-s['pawn']//8)>1
        self.assertTrue(own,'Same-file opposing pawn must refute passedness.')
        self.assertTrue(distant,'A distant forward opposing pawn must also refute passedness.')

    def test_worked_file_pin_and_active_black_routine_are_present(self):
        from golden_board.advanced_cases import queries,evaluate
        qs={q['id']:q for q in queries(ROOT)}
        q=qs['absolute_pin_vs_relative_line'];pins=[]
        for s in [q['worked_input'],*q['worked_variants']]:pins.extend(evaluate(s,ROOT)['detail']['pins'])
        self.assertTrue(any(a%8==b%8==c%8 for a,b,c in pins),'File pins need a positive source observation.')
        q=qs['active_state_and_side'];states=[evaluate(s,ROOT)['detail']['effect']['before'] for s in [q['worked_input'],*q['worked_variants']]]
        self.assertTrue(any(not s['closed'] and s['side']==1 for s in states),'Active must not mean White-to-move.')

    def test_proof_claim_event_does_not_increment_displayed_ply(self):
        from golden_board.course_practical import _decoded_frames,COLS,digits
        from golden_board.document import decode_document
        p=self.product();spec=next(s for g in p['groups'] for q in g['queries'] for s in q['worked_variants']
            if s['op']=='proof' and 'claim:threefold' in s['tree'].get('children',{}))
        frames=_decoded_frames(decode_document(p['document']),p['proofs'][str(spec['context_id'])])
        self.assertEqual(len(frames),2)
        self.assertEqual(frames[0][9*COLS+2:9*COLS+6],digits(8))
        self.assertEqual(frames[1][9*COLS+2:9*COLS+6],digits(8))

if __name__=='__main__':unittest.main()
