"""Practical teaching: hand boundaries, coherent histories and carried evidence."""
from pathlib import Path
import importlib.util
import unittest

ROOT=Path(__file__).resolve().parents[1]
CYCLE='g1f3 g8f6 f3g1 f6g8 '

class PracticalStateTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('golden_board.practical_state'),
                             'The practical truth/witness layer is not implemented.')
        from golden_board import practical_state
        return practical_state

    def test_current_key_witnesses_distinguish_clock_and_ep(self):
        p=self.api()
        r=p.evaluate({'op':'observe','prefix':CYCLE*2})
        self.assertEqual(r['after']['occurrences'],[0,4,8])
        self.assertEqual((r['after']['repeat'],r['after']['clock']), (3,8))
        self.assertEqual(r['after']['eligible'],[True,False])
        r=p.evaluate({'op':'compare','prefix':'e2e4','other':'e2e4 g8f6 g1f3 f6g8 f3g1'})
        self.assertTrue(r['equal_key']);self.assertNotEqual(r['before']['ep'],r['after']['ep'])
        self.assertIsNone(r['before']['key_ep'])
        r=p.evaluate({'op':'compare','prefix':'e2e4 a7a6 e4e5 d7d5',
                      'other':'e2e4 a7a6 e4e5 d7d5 '+CYCLE})
        self.assertFalse(r['equal_key']);self.assertEqual(r['before']['key_ep'],19)

    def test_rejected_event_is_atomic_and_claim_does_not_replay_a_move(self):
        p=self.api()
        r=p.evaluate({'op':'attempt','prefix':CYCLE*2,'kind':'claim','actor':1,'reason':'threefold'})
        self.assertFalse(r['accepted']);self.assertEqual(r['after'],r['before'])
        r=p.evaluate({'op':'attempt','prefix':CYCLE*2,'kind':'claim','actor':0,'reason':'threefold'})
        self.assertTrue(r['accepted']);self.assertTrue(r['after']['closed'])
        self.assertEqual(r['after']['reason'],'threefold');self.assertEqual(r['after']['score'],2)
        self.assertEqual(r['before']['occupancy'],r['after']['occupancy'])
        self.assertEqual(r['before']['occurrences'],r['after']['occurrences'])

    def test_castle_probes_move_king_then_both_pieces(self):
        p=self.api()
        prefix='e2e4 e7e5 g1h3 b8c6 f1c4 f8c5 f2f3 g8f6'
        r=p.evaluate({'op':'attempt','prefix':prefix,'kind':'move','move':'e1g1'})
        self.assertFalse(r['accepted'])
        probes=r['castle_probes'];self.assertEqual([v['king'] for v in probes],[60,61,62])
        self.assertEqual([v['attackers'] for v in probes],[[],[],[26]])
        self.assertEqual(probes[1]['occupancy'][63],35)
        self.assertEqual(probes[1]['occupancy'][61],37)
        self.assertEqual(probes[2]['occupancy'][63],0)
        self.assertEqual(probes[2]['occupancy'][61],35)
        self.assertEqual(probes[2]['occupancy'][62],37)

    def test_local_material_has_no_replay_and_incomplete_record_guesses_nothing(self):
        p=self.api()
        r=p.evaluate({'op':'material','fen':'7k/8/8/8/8/8/8/KN6 w - - 0 1'})
        self.assertEqual(r['classification'],'common-dead');self.assertNotIn('before',r)
        r=p.evaluate({'op':'material','fen':'7k/8/8/8/8/8/8/KNN5 w - - 0 1'})
        self.assertEqual(r['classification'],'outside-profile')
        r=p.evaluate({'op':'record','prefix':'e2e4 e7e5','length':3,'ply':2,'score':2})
        self.assertFalse(r['complete']);self.assertFalse(r['accepted']);self.assertIsNone(r['after'])
        r=p.evaluate({'op':'record','prefix':'e2e4 e7e5','length':2,'ply':1,'score':2})
        self.assertTrue(r['complete']);self.assertEqual(r['record_cause'],'unspecified')
        self.assertEqual(r['after']['side'],1);self.assertIsNone(r['after']['score'])

    def test_rejected_ep_still_carries_full_trial_removal_and_open_king_line(self):
        p=self.api();prefix=('e2e4 e7e6 f2f4 g8f6 f4f5 e6f5 e4e5 f6g4 '
            'g1f3 f8e7 d2d4 e8g8 b1c3 f8e8 f1d3 e7f8 d1d2 d7d5')
        r=p.evaluate({'op':'attempt','prefix':prefix,'kind':'move','move':'e5d6'})
        self.assertFalse(r['accepted']);self.assertIn('move_probe',r)
        self.assertEqual(r['move_probe']['occupancy'][27],0) # d5 captured off destination
        self.assertEqual(r['move_probe']['occupancy'][19],32)
        self.assertTrue(r['move_probe']['king_attacked'])

    def test_invalid_promotion_choice_has_no_valid_move_tuple(self):
        p=self.api()
        for text in ('b7a8k','b7a8p'):
            with self.assertRaises(ValueError):p.move_row(text)

class PracticalCourseTests(unittest.TestCase):
    def product(self):
        self.assertIsNotNone(importlib.util.find_spec('golden_board.course_practical'),
                             'The actual practical teaching document is absent.')
        from golden_board.course_practical import build_practical
        if not hasattr(type(self),'_product'):type(self)._product=build_practical(ROOT)
        return type(self)._product

    def test_all66_strata_have_actual_source_truth_and_passive_practice(self):
        import tomllib,json,subprocess
        from golden_board.document import decode_document
        p=self.product();families=tomllib.loads((ROOT/'content/coverage.toml').read_text())['family'][4:11]
        expected={s for f in families for s in f['critical_strata']}
        self.assertEqual(len(expected),66);self.assertEqual(set(p['bindings']),expected)
        self.assertEqual(p['truth']['strata'],66)
        d=decode_document(p['document'])
        for c in p['cases']:
            page=d['records'][c['practice']]
            self.assertEqual(page['accepted'],[c['expected']])
            self.assertIn(c['passive'],d['records'][c['worked']]['links'])
        req={'documents':{'4':p['document'].hex()},'cases':p['cases']}
        run=subprocess.run(['node',str(ROOT/'tools/audit-course.mjs')],input=json.dumps(req).encode(),capture_output=True)
        self.assertEqual(run.returncode,0,run.stderr.decode())
        r=json.loads(run.stdout);self.assertTrue(r['all_frames_exact'] and r['all_actions_exact'] and r['passive_without_response'])

    def test_mutated_truth_and_carried_frame_cannot_qualify(self):
        from copy import deepcopy
        p=self.product()
        from golden_board.course_practical import validate_practical
        broken=deepcopy(p);broken['groups'][0]['queries'][0]['expected']['after']['clock']+=1
        with self.assertRaises(ValueError):validate_practical(broken,ROOT)
        from golden_board.document import decode_document,encode_document
        broken=deepcopy(p);d=decode_document(broken['document'])
        node=next(iter(p['records'].values()));trace=d['records'][d['records'][node]['display']]
        d['records'][trace['data'][0]]['values'][0]^=1
        broken['document']=encode_document(d['entries'],list(d['records'].values()))
        import hashlib
        for rows in broken['bindings'].values():
            for row in rows:row['document_sha256']=hashlib.sha256(broken['document']).hexdigest()
        with self.assertRaises(ValueError):validate_practical(broken,ROOT)
        broken=deepcopy(p);broken['bindings'].pop(next(iter(broken['bindings'])))
        with self.assertRaises(ValueError):validate_practical(broken,ROOT)

    def test_all_required_state_boundaries_are_not_only_family_labels(self):
        p=self.product();queries=[q for g in p['groups'] for q in g['queries']]
        rows={q['id']:q for q in queries}
        self.assertEqual({rows[x]['worked_expected']['after']['occupancy'].count(37) for x in ('first_short','first_long')},{1})
        self.assertFalse(rows['promoted_replacement_no_right_restore']['expected']['accepted'])
        self.assertEqual(rows['halfmoves99_100']['worked_expected']['before']['clock'],99)
        self.assertEqual(rows['halfmoves99_100']['expected']['before']['clock'],100)
        self.assertEqual(rows['mate_stalemate_dead_closure_priority']['expected']['after']['reason'],'common-dead')
        self.assertTrue(p['calibration']);self.assertEqual(p['roots'][0],p['calibration'])

    def test_requests_identify_both_comparison_operands_and_record_stream(self):
        self.product()
        from golden_board.course_practical import render
        from golden_board.practical_cases import compare,RIGHTS_OK,KING_BACK,ROOK_BACK
        a=render(compare(RIGHTS_OK,KING_BACK));b=render(compare(RIGHTS_OK,ROOK_BACK))
        self.assertNotEqual(a,b,'Second operand must be visible before the answer.')
        from golden_board.course_practical import groups
        specs=[s for g in groups(ROOT) for q in g['queries'] for s in [q['input'],q['worked_input'],*q['worked_variants']] if s['op']=='record']
        for i,s in enumerate(specs):
            for t in specs[i+1:]:
                if s['prefix']!=t['prefix']:self.assertNotEqual(render(s),render(t))

    def test_observation_is_completion_and_outside_profile_is_unavailable(self):
        self.product()
        from golden_board.course_practical import render,COLS
        from golden_board.practical_cases import observe,material
        from golden_board.practical_state import evaluate
        s=observe(CYCLE*2);f=render(s);option=render(s,evaluate(s))
        for field in (6,7,8,9,10,11,12):
            self.assertEqual(f[(9+field)*COLS+3:(9+field)*COLS+8],[0]*5)
            self.assertEqual(option[(9+field)*COLS+3:(9+field)*COLS+8],[0]*5)
        s=material('7k/8/8/8/8/8/8/KNN5');f=render(s,evaluate(s))
        self.assertEqual(f[9*COLS:9*COLS+2],[2,0])
        from golden_board.practical_cases import record
        s=record('e2e4 e7e5',0);f=render(s,evaluate(s))
        self.assertEqual(f[9*COLS+4:9*COLS+6],[2,0])

    def test_same_values_with_wrong_record_columns_are_rejected(self):
        from copy import deepcopy
        import hashlib
        from golden_board.document import decode_document,encode_document
        from golden_board.course_practical import validate_practical
        p=deepcopy(self.product());d=decode_document(p['document']);node=next(iter(p['records'].values()))
        trace=d['records'][d['records'][node]['display']];table=d['records'][trace['data'][0]]
        table['rows']*=3;table['cols']=1
        p['document']=encode_document(d['entries'],list(d['records'].values()))
        digest=hashlib.sha256(p['document']).hexdigest()
        for rows in p['bindings'].values():
            for row in rows:row['document_sha256']=digest
        with self.assertRaises(ValueError):validate_practical(p,ROOT)

    def test_equal_clock_different_recurrence_requests_identify_the_history(self):
        p=self.product()
        from golden_board.course_practical import render
        from golden_board.practical_state import evaluate
        q=next(q for g in p['groups'] for q in g['queries'] if q['id']=='current_key_count_not_elapsed_plies')
        rival_prefix='g1f3 g8f6 b1c3 b8c6 c3b1 c6b8 f3g1 f6g8'
        v=next((v for v in q['worked_variants'] if v['prefix']==rival_prefix),None)
        self.assertIsNotNone(v,'Equal clock needs a different recurrence pattern.')
        a,b=evaluate(q['worked_input'])['after'],evaluate(v)['after']
        self.assertEqual(a['clock'],b['clock']);self.assertEqual(a['occupancy'],b['occupancy'])
        self.assertEqual((a['occurrences'],b['occurrences']),([0,4,8],[0,8]))
        self.assertNotEqual(render(q['worked_input']),render(v))
        self.assertTrue(p['history_directory'])

    def test_explicit_boundary_segments_preserve_request_identity(self):
        from golden_board.document import decode_document
        p=self.product();d=decode_document(p['document'])
        traces=[d['records'][d['records'][n]['display']] for n in p['contexts'].values()]
        self.assertGreater(len({t['initial'] for t in traces}),1)
        self.assertEqual(len(set(p['history_ids'].values())),len(p['contexts']))
        directory=d['records'][d['records'][p['history_directory']]['display']]
        self.assertEqual([d['records'][i]['cols'] for i in directory['data']],[6,11])
        self.assertGreaterEqual(len(p['history_segments']),len(p['contexts']))

    def test_promotion_is_not_correlated_with_capture(self):
        import chess
        from golden_board.practical_state import evaluate
        p=self.product();specs=[s for g in p['groups'] for q in g['queries'] if q['family']=='T7'
                              for s in [q['worked_input'],*q['worked_variants']]]
        quiet=[]
        for s in specs:
            if len(s['move'])==5 and s['move'][4] in 'qrbn':
                r=evaluate(s);b=chess.Board()
                for text in s['prefix'].split():b.push_uci(text)
                if r['accepted'] and not b.is_capture(chess.Move.from_uci(s['move'])):quiet.append(r['before']['side'])
        self.assertEqual(set(quiet),{0,1})

    def test_complete_record_with_out_of_range_ply_separates_flags(self):
        from golden_board.course_practical import render,COLS,_decoded_frames,digits
        from golden_board.document import decode_document
        from golden_board.practical_state import evaluate
        p=self.product()
        q=next(q for g in p['groups'] for q in g['queries'] if q['id']=='record_order_and_length_boundary')
        variants=[s for s in q['worked_variants'] if s['ply']>s['length'] and s['length']==len(s['prefix'].split())]
        self.assertTrue(variants,'Worked source must separate complete data from valid navigation.')
        s=variants[0];result=evaluate(s);f=render(s,result)
        self.assertEqual((result['accepted'],result['complete'],result['after']),(False,True,None))
        self.assertEqual((f[9*COLS],f[9*COLS+2]),(2,1))
        self.assertEqual(result['available'],7)
        self.assertEqual(s['record_id'],q['worked_input']['record_id'])
        for row in range(8):self.assertEqual(f[row*COLS+9:row*COLS+17],[0]*8)
        case=next(c for c in p['cases'] if any(v['id']==q['id'] for v in c['queries']))
        frames=_decoded_frames(decode_document(p['document']),case['worked'])
        actual=next(v for v in frames if v[8*COLS+8:8*COLS+12]==digits(8)
                    and (v[9*COLS],v[9*COLS+2])==(2,1))
        self.assertEqual(actual[8*COLS+3:8*COLS+7],digits(7))
        for row in range(8):self.assertEqual(actual[row*COLS+9:row*COLS+17],[0]*8)

    def test_auxiliary_reply_frames_identify_their_carried_history(self):
        from golden_board.course_practical import _decoded_frames,COLS,digits
        from golden_board.document import decode_document
        p=self.product();d=decode_document(p['document'])
        self.assertTrue(p['replies'])
        for prefix,node in p['replies'].items():
            for frame in _decoded_frames(d,node):
                self.assertEqual(frame[8*COLS+14:8*COLS+18],digits(p['history_ids'][prefix]),prefix)

    def test_wrong_auxiliary_history_id_is_rejected(self):
        from copy import deepcopy
        import hashlib
        from golden_board.course_practical import validate_practical,COLS
        from golden_board.document import decode_document,encode_document
        p=deepcopy(self.product());d=decode_document(p['document'])
        node=next(iter(p['replies'].values()));trace=d['records'][d['records'][node]['display']]
        d['records'][trace['initial']]['cells'][8*COLS+17]=22
        p['document']=encode_document(d['entries'],list(d['records'].values()))
        digest=hashlib.sha256(p['document']).hexdigest()
        for rows in p['bindings'].values():
            for row in rows:row['document_sha256']=digest
        with self.assertRaises(ValueError):validate_practical(p,ROOT)

if __name__=='__main__':unittest.main()
