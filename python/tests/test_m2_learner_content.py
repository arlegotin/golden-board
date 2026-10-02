"""Semantic regressions exposed by the first learner, before carrier packing."""
from pathlib import Path
import importlib.util
import unittest

from golden_board import chess

ROOT = Path(__file__).resolve().parents[2]


class RevisedLearnerContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'tools/m2/learner_content.py'
        spec = importlib.util.spec_from_file_location('revised_learner_content', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.module = module
        cls.pages = module.build_cases(ROOT)

    def test_required_meanings_are_demonstrated_before_final_questions(self):
        self.assertLessEqual(len(self.pages),96)
        ids=[p['id'] for p in self.pages]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(self.pages[0]['family'],'mechanics')
        required={'locations','state_target','state_rights','queen','king','history'}
        taught=set()
        for page in self.pages:
            if page['phase']=='teach': taught.add(page['family'])
            if page['phase']=='heldout': self.assertTrue(required <= taught)
        location=next(i for i,p in enumerate(self.pages) if p['family']=='locations')
        target=next(i for i,p in enumerate(self.pages) if p['family']=='state_target')
        self.assertLess(location,target)

    def test_nonchess_mechanics_has_select_reset_reselect_commit_example(self):
        page=self.pages[0]
        self.assertEqual(page['passive_actions'],['01000001','02000000','01000002','03000000'])
        self.assertEqual(page['correct'],(2,))
        self.assertTrue(all(p['rows'] != 8 and p['columns'] != 8 for p in page['panels']))

    def test_self_check_rejected_ep_picture_is_mechanically_complete(self):
        page=next(p for p in self.pages if p['id']=='self-check-en-passant')
        ev=page['evidence'];before=bytes.fromhex(ev['before_hex'])
        wrong=next(o for o in ev['options'] if not o['legal'])
        move=chess.decode_move(bytes.fromhex(wrong['move_hex']))
        proposed=bytes.fromhex(wrong['proposed_hex'])
        captured=(move.origin//8)*8+move.destination%8
        self.assertEqual(proposed[captured],0)
        self.assertNotEqual(before[captured],0)
        wire=chess.decode_position(proposed)
        king_square=proposed.index(6 if before[64]==0 else 12,0,64)
        self.assertTrue(chess.controls_square(wire,1-before[64],king_square))
        region=next(r for r in page['regions'] if r['id']==wrong['region_id'])
        panel=page['panels'][-1]
        at=(region['row_start']+7-captured//8)*panel['columns']+region['column_start']+captured%8
        self.assertEqual(panel['cells'][at],0)

    def test_record_questions_require_the_record_to_choose_between_legal_results(self):
        pages=[p for p in self.pages if p['evidence']['kind']=='record_transition']
        self.assertTrue(any(p['phase']=='teach' for p in pages))
        self.assertTrue(any(p['phase']=='heldout' for p in pages))
        for page in pages:
            ev=page['evidence'];raw=bytes.fromhex(ev['prefix_hex'])
            state=chess.replay_from_start(tuple(chess.decode_move(raw[i:i+2]) for i in range(0,len(raw),2)))
            matched=[];states=[]
            for option in ev['options']:
                after=chess.apply_move(state,chess.decode_move(bytes.fromhex(option['move_hex'])))
                exact=chess.encode_position(after.position)
                self.assertEqual(exact.hex(),option['after_hex'])
                states.append(exact[64:])
                if option['move_hex']==ev['record_move_hex']:matched.append(option['region_id'])
            self.assertEqual(tuple(matched),page['correct'])
            self.assertEqual(len(set(states)),1,'footer cannot reveal the recorded choice')
            if page['phase']=='heldout': self.assertGreaterEqual(ev['ply_index'],3)

    def test_every_board_option_retains_exact_authoritative_truth(self):
        for page in self.pages:
            ev=page['evidence']
            if ev['kind'] not in ('transition','record_transition'):continue
            raw=bytes.fromhex(ev['prefix_hex'])
            state=chess.replay_from_start(tuple(chess.decode_move(raw[i:i+2]) for i in range(0,len(raw),2)))
            for option in ev['options']:
                with self.subTest(page=page['id'],option=option['region_id']):
                    move=chess.decode_move(bytes.fromhex(option['move_hex']))
                    if option['legal']:
                        actual=chess.encode_position(chess.apply_move(state,move).position)
                        self.assertEqual(actual.hex(),option['after_hex'])
                        region=next(r for r in page['regions'] if r['id']==option['region_id'])
                        panel=page['panels'][-1]
                        recovered=[]
                        for rank in range(8):
                            start=(region['row_start']+7-rank)*panel['columns']+region['column_start']
                            recovered.extend(panel['cells'][start:start+8])
                        self.assertEqual(bytes(recovered),actual[:64])
                        footer=(region['row_start']+9)*panel['columns']+region['column_start']
                        self.assertEqual(bytes(panel['cells'][footer:footer+3]),actual[64:])
                    else:
                        with self.assertRaises(chess.ChessReject) as rejected:chess.apply_move(state,move)
                        self.assertEqual(rejected.exception.code,option['rejection'])

    def test_production_authoring_does_not_depend_on_participant_files(self):
        source=(ROOT/'tools/m2/learner_content.py').read_text()
        self.assertNotIn('artifacts/quiz',source)
        self.assertIn('reports/game-set-v0.bin',source)

    def test_target_codes_and_expiry_are_exact_before_the_chess_queries(self):
        pages=[p for p in self.pages if p['family']=='state_target']
        self.assertEqual({p['evidence']['nominal_code'] for p in pages},{0,21,43,45})
        for page in pages:
            ev=page['evidence']
            code=bytes.fromhex(ev['position_hex'])[66]
            self.assertEqual(code,ev['nominal_code'])
            expected=[int(code != 0 and square == code-1) for square in range(64)]
            self.assertEqual(ev['target_mask'],expected)
            region=next(r for r in page['regions'] if r['id']==page['correct'][0])
            panel=page['panels'][-1]
            shown=[]
            for rank in range(8):
                start=(7-rank)*panel['columns']+region['column_start']
                shown.extend(panel['cells'][start:start+8])
            self.assertEqual(shown,expected)
        expiry=next(p for p in pages if p['id']=='target-expires')
        self.assertNotEqual(bytes.fromhex(expiry['evidence']['before_hex'])[66],0)
        self.assertEqual(expiry['evidence']['nominal_code'],0)

    def test_permission_demonstration_binds_all_four_bits_and_nonrestoration(self):
        pages=[p for p in self.pages if p['family']=='state_rights']
        table=next(p for p in pages if p['id']=='rights-four-bits')
        self.assertEqual(table['evidence']['bit_bindings'],[
            [1,0,4,7,6,5],[2,0,4,0,2,3],
            [4,1,60,63,62,61],[8,1,60,56,58,59]])
        matrix=next(p for p in table['panels'] if (p['rows'],p['columns'])==(4,6))
        self.assertEqual(matrix['cells'],[v for row in table['evidence']['bit_bindings'] for v in row])
        matrix=next(p for p in table['panels'] if (p['rows'],p['columns'])==(17,5))
        self.assertEqual(matrix['cells'][5:],[v for mask in range(16)
            for v in [mask]+[int(bool(mask&bit)) for bit in (1,2,4,8)]])
        for identifier,remaining in [('rights-rook-return',14),('rights-king-return',12)]:
            ev=next(p for p in pages if p['id']==identifier)['evidence']
            frames=ev['storyboard']['frames']
            self.assertEqual(bytes.fromhex(frames[0]['position_hex'])[65],15)
            self.assertEqual(bytes.fromhex(frames[-1]['position_hex'])[65],remaining)
            square=ev['returned_origin']
            self.assertEqual(bytes.fromhex(frames[0]['position_hex'])[square],
                             bytes.fromhex(frames[-1]['position_hex'])[square])

    def test_queen_and_ordinary_king_are_taught_before_control_masks(self):
        first_control=next(i for i,p in enumerate(self.pages) if p['evidence']['kind']=='control')
        for family,piece in [('queen',5),('king',6)]:
            teaching=[p for p in self.pages[:first_control] if p['family']==family and p['phase']=='teach']
            self.assertTrue(teaching)
            for page in teaching:
                before=bytes.fromhex(page['evidence']['before_hex'])
                good=[o for o in page['evidence']['options'] if o['legal']]
                self.assertTrue(any(before[chess.decode_move(bytes.fromhex(o['move_hex'])).origin]==piece for o in good))

    def test_all_four_permission_bindings_have_actual_castling_examples(self):
        examples=[p for p in self.pages if p['phase']=='teach' and 'permission_bit' in p['evidence']]
        self.assertEqual({p['evidence']['permission_bit'] for p in examples},{1,2,4,8})
        for page in examples:
            ev=page['evidence'];before=bytes.fromhex(ev['before_hex'])
            self.assertTrue(before[65]&ev['permission_bit'])
            for option in ev['options']:
                if not option['legal']:continue
                move=chess.decode_move(bytes.fromhex(option['move_hex']))
                self.assertEqual((move.origin,move.destination),
                                 {1:(4,6),2:(4,2),4:(60,62),8:(60,58)}[ev['permission_bit']])
        denied=next(p for p in self.pages if p['id']=='rights-return-forbids-castling')
        self.assertIn(43,[o.get('rejection') for o in denied['evidence']['options']])

    def test_rejected_castle_picture_moves_the_rook_as_well(self):
        page=next(p for p in self.pages if p['id']=='castle-through-control')
        bad=next(o for o in page['evidence']['options'] if not o['legal'])
        proposed=bytes.fromhex(bad['proposed_hex'])
        self.assertEqual([proposed[i] for i in (4,5,6,7)],[0,4,6,0])

    def test_final_promotion_and_self_check_are_novel_reachable_cases(self):
        for family in ('self_check','promotion','castling','game'):
            final=next(p for p in self.pages if p['phase']=='heldout' and p['family']==family)
            taught={p['evidence'].get('prefix_hex') for p in self.pages if p['phase']!='heldout' and p['family']==family}
            self.assertNotIn(final['evidence']['prefix_hex'],taught)
        promotion=next(p for p in self.pages if p['id']=='final-promotion')
        self.assertTrue(any(chess.decode_move(bytes.fromhex(o['move_hex'])).promotion for o in promotion['evidence']['options'] if o['legal']))

    def test_history_proof_is_public_oracle_truth_and_final_has_no_given_count(self):
        final=next(p for p in self.pages if p['id']=='final-history')
        self.assertFalse(final['evidence']['count_shown'])
        self.assertEqual(final['evidence']['query_badge'],self.module.CLAIM_RELATION)
        for page in self.pages:
            ev=page['evidence']
            if 'storyboard' not in ev:continue
            story=ev['storyboard'];frames=story['frames']
            panel=page['panels'][story['panel_index']]
            for i,frame in enumerate(frames):
                raw=bytes.fromhex(frame['prefix_hex'])
                state=chess.replay_from_start(tuple(chess.decode_move(raw[j:j+2]) for j in range(0,len(raw),2)))
                actual=chess.encode_position(state.position)
                self.assertEqual(actual.hex(),frame['position_hex'])
                if i:self.assertEqual(len(frame['prefix_hex'])-len(frames[i-1]['prefix_hex']),4)
                recovered=[]
                for rank in range(8):
                    start=(frame['row_start']+7-rank)*panel['columns']+frame['column_start']
                    recovered.extend(panel['cells'][start:start+8])
                self.assertEqual(bytes(recovered),actual[:64])
                footer=(frame['row_start']+9)*panel['columns']+frame['column_start']
                self.assertEqual(bytes(panel['cells'][footer:footer+3]),actual[64:])
            if ev['kind']=='history':
                actual=chess.evaluate_predicate(b'chess.history_claim',chess.HistoryClaimInput(state))
                self.assertEqual(ev['occurrences'],actual.current_key_occurrences)
                self.assertEqual(ev['threefold_available'],actual.threefold_available)
                region=next(r for r in page['regions'] if r['id']==page['correct'][0])
                self.assertEqual(page['panels'][-1]['cells'][region['column_start']],int(actual.threefold_available))

    def test_effective_target_boundary_and_optional_claim_are_taught(self):
        page=next(p for p in self.pages if p['id']=='history-effective-target-boundary')
        self.assertEqual(page['evidence']['same_keys'],[True,False])
        for pair,expected in zip(page['evidence']['prefix_pairs'],[True,False]):
            keys=[];positions=[]
            for prefix in pair:
                raw=bytes.fromhex(prefix)
                state=chess.replay_from_start(tuple(chess.decode_move(raw[i:i+2]) for i in range(0,len(raw),2)))
                keys.append(chess.repetition_key(state));positions.append(chess.encode_position(state.position))
            self.assertEqual(keys[0]==keys[1],expected)
            self.assertEqual(positions[0][:66],positions[1][:66])
            self.assertNotEqual(positions[0][66],positions[1][66])
        continuing=next(p for p in self.pages if p['id']=='history-claim-allows-next-move')
        self.assertTrue(continuing['evidence']['threefold_available'])
        self.assertTrue(any(o['legal'] for o in continuing['evidence']['options']))

    def test_game_set_slice_parser_is_bounded_exact_and_fail_closed(self):
        raw=(ROOT/'reports/game-set-v0.bin').read_bytes()
        games=self.module._canonical_games(raw)
        self.assertEqual(len(games),64)
        self.assertEqual(b'\x00\x40'+b''.join(games),raw)
        for corrupted in [raw[:-1],raw+b'\0',b'\x00\x3f'+raw[2:],
                          b'\x00\x40\x10\x01'+raw[4:],b'\0'*327678]:
            with self.subTest(length=len(corrupted)):
                with self.assertRaises(ValueError):self.module._canonical_games(corrupted)

    def test_numeric_panels_are_bounded_and_deterministic(self):
        for page in self.pages:
            for panel in page['panels']:
                self.assertEqual(len(panel['cells']),panel['rows']*panel['columns'])
                self.assertTrue(all(type(value) is int and 0<=value<=255 for value in panel['cells']))
        self.assertEqual(self.pages,self.module.build_cases(ROOT))


if __name__=='__main__':unittest.main()
