"""Source accounting, independent convention and membership failures."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from golden_board.source_game import parse_mainline

ROOT=Path(__file__).resolve().parents[1]


def pgn(moves='1. e4 e5',result='1-0',name='fixture'):
    return f'[Event "{name}"]\n[Result "{result}"]\n\n{moves} {result}\n\n'


def locked(root,text,count):
    path=root/'inputs/anthology.pgn';path.parent.mkdir(parents=True);data=text.encode('utf8');path.write_bytes(data)
    (root/'inputs/lock.json').write_text(json.dumps({'path':'inputs/anthology.pgn','sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'expected_records':count}))


class AnthologyTests(unittest.TestCase):
    def test_invalid_record_is_accounted_without_losing_other_entries(self):
        from golden_board.anthology import import_anthology
        bad=pgn().replace('[Result "1-0"]','[Result "1-0"]\n[Result "1-0"]')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);locked(root,bad+pgn('1. d4 d5'),2)
            r=import_anthology(root)
            self.assertFalse(r['qualified']);self.assertEqual(r['record_count'],2)
            self.assertEqual([v['classification'] for v in r['records']],['invalid','eligible'])
            self.assertEqual(r['selection']['selected_source_ordinals'],[2])
            self.assertIn('duplicate',r['records'][0]['reason'])
            self.assertEqual(r['records'][0]['start'],0)
            self.assertEqual(r['records'][0]['end'],r['records'][1]['start'])

    def test_strict_source_mutations_are_rejected_without_silent_repair(self):
        from golden_board.anthology import import_anthology
        mate=pgn('1. f3 e5 2. g4 Qh4#','0-1')
        mutations=[pgn('1. e5 e5'),pgn('2. e4 e5'),pgn('1. e4 {note} e5'),
            pgn().replace('1-0\n\n','1-0 junk\n\n'),mate.replace('Qh4#','Qh4+'),
            mate.replace('0-1','1-0'),pgn().replace('[Result','[FEN "not a start"]\n[Result'),
            pgn().replace('[Result','[Variant "Chess960"]\n[Result'),
            pgn().replace('[Result','[SetUp "1"]\n[Result'),
            pgn().replace('1-0\n\n','0-1\n\n'),pgn('1. f3 e5 2. g4 Qh4# 3. a3','0-1')]
        for changed in mutations:
            with self.subTest(record=changed),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);locked(root,changed+pgn('1. d4 d5'),2)
                r=import_anthology(root)
                self.assertEqual(r['records'][0]['classification'],'invalid')
                self.assertEqual(r['selection']['selected_source_ordinals'],[2])
                self.assertEqual((root/'inputs/anthology.pgn').read_text(),changed+pgn('1. d4 d5'))

    def test_duplicates_retain_earliest_and_score_conflicts_never_choose_rank(self):
        from golden_board.anthology import import_anthology
        text=pgn(name='first')+pgn(name='duplicate')+pgn('1. d4 d5','1/2-1/2')+pgn('1. d4 d5','1-0')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);locked(root,text,4);r=import_anthology(root)
            self.assertEqual([v['classification'] for v in r['records']],['eligible','duplicate','conflict','conflict'])
            self.assertEqual(r['records'][1]['duplicate_of'],1)
            self.assertEqual(r['selection']['selected_source_ordinals'],[1])
            self.assertIsNone(r['selection']['editorial_tail_cut'])
            self.assertEqual([v['source_ordinal'] for v in r['records']],[1,2,3,4])

    def test_prefix_is_checked_before_canonical_sorting(self):
        from golden_board.anthology import import_anthology,validate_prefix
        with self.assertRaisesRegex(ValueError,'prefix'):validate_prefix([1,2,4],[1,4])
        with self.assertRaises(ValueError):validate_prefix([1,2],[])
        validate_prefix([1,2,4],[1,2]) # Mathematical check, not an editorial-cut authorization.
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);locked(root,pgn()+pgn('1. d4 d5'),2);r=import_anthology(root)
            self.assertEqual(r['selection']['selected_source_ordinals'],[1,2])
            self.assertEqual([v['source_ordinal'] for v in r['canonical_games']],[2,1])
            self.assertEqual([v['artifact_ordinal'] for v in r['canonical_games']],[1,2])

    def test_metadata_and_order_do_not_change_selected_game_truth(self):
        from golden_board.anthology import import_anthology,canonical_game_bytes
        one=pgn(name='one');two=pgn('1. d4 d5',name='two')
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            left,right=Path(a),Path(b);locked(left,one+two,2)
            locked(right,two.replace('two','new metadata')+one.replace('one','different'),2)
            x,y=import_anthology(left),import_anthology(right)
            xb=[canonical_game_bytes(x['games'][str(g['source_ordinal'])]) for g in x['canonical_games']]
            yb=[canonical_game_bytes(y['games'][str(g['source_ordinal'])]) for g in y['canonical_games']]
            self.assertEqual(xb,yb)
            self.assertEqual(canonical_game_bytes({'moves':[[52,36,0]],'score':0}),b'\0\0\0\1\x34\x24\0\0')

    def test_reference_distinguishes_native_and_immediate_ep_without_changing_moves(self):
        from golden_board.anthology import independent_anthology
        legal='1. e4 a6 2. e5 d5 3. exd6'
        pinned='1. e4 e6 2. f4 Nf6 3. f5 exf5 4. e5 Ng4 5. Nf3 Be7 6. d4 O-O 7. Nc3 Re8 8. Bd3 Bf8 9. Qd2 d5'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'original.pgn';path.write_text(pgn('1. e4')+pgn(legal)+pgn(pinned)+pgn(pinned+' 10. exd6'))
            rows=independent_anthology(ROOT,path)['records']
        self.assertEqual([r['status'] for r in rows],['accepted','accepted','accepted','rejected'])
        e4=rows[0]['game']['positions'][1]
        self.assertEqual(e4['native_fen'].split()[3],'-')
        self.assertEqual(e4['fen'],'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1')
        self.assertEqual(e4['ep_derivation']['target'],'e3')
        self.assertEqual(rows[1]['game']['positions'][4]['fen'].split()[3],'d6')
        self.assertEqual(rows[2]['game']['positions'][18]['fen'].split()[3],'d6')

    def test_independent_strict_flag_does_not_substitute_for_canonical_san(self):
        from golden_board.anthology import independent_anthology
        correct=pgn('1. f3 e5 2. g4 Qh4#','0-1')
        invalid=[correct.replace('Qh4#','Qh4+'),correct.replace('Qh4#','Qh4'),
            correct.replace('1. f3','2. f3'),correct.replace('1. f3','1. f5'),
            correct.replace('[Result "0-1"]','[Result "0-1"]\n[Result "0-1"]'),
            correct.rstrip()+' junk\n\n',correct.replace('1. f3','1. f3 {note}'),
            correct.replace('[Result','[FEN "unsupported"]\n[Result')]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'original.pgn';path.write_text(correct+''.join(invalid))
            rows=independent_anthology(ROOT,path)['records']
        self.assertEqual([r['status'] for r in rows],['accepted']+['rejected']*len(invalid))
        self.assertIn('canonical SAN',rows[1]['error'])

    def test_first_wrong_intermediate_field_fails_reference_comparison(self):
        from golden_board.anthology import compare_game
        game=parse_mainline(pgn().encode())
        reference={'moves':[[52,36,0],[12,28,0]],'score':0,'board_end':'active','positions':[{'fen':fen} for fen in [
            'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
            'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
            'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2']]}
        self.assertTrue(compare_game(game,reference)['matches'])
        reference['positions'][1]['fen']=reference['positions'][1]['fen'].replace('e3','-')
        result=compare_game(game,reference)
        self.assertFalse(result['matches']);self.assertEqual(result['ply'],1);self.assertEqual(result['field'],'fen')

    def test_boundary_compares_ending_and_adapter_closure_without_inferring_score_cause(self):
        from copy import deepcopy
        from golden_board.anthology import compare_game, _adapter_replay
        mate = parse_mainline(pgn('1. f3 e5 2. g4 Qh4#', '0-1').encode())
        incorrect = deepcopy(mate)
        incorrect['board_end'] = 'active'
        result = compare_game(mate, incorrect)
        self.assertFalse(result['matches'])
        self.assertEqual(result['field'], 'board_end')
        with patch('golden_board.rules.board_ending', return_value='active'):
            result = _adapter_replay(mate)
        self.assertFalse(result['matches'])
        self.assertEqual(result['field'], 'adapter_outcome')
        self.assertEqual(result['ply'], 4)
        active = _adapter_replay(parse_mainline(pgn().encode()))
        self.assertTrue(active['matches'])
        self.assertEqual(active['ending'], 'active')
        self.assertIsNone(active['outcome'])

    def test_actual_source_import_smoke_does_not_claim_qualification(self):
        from golden_board.anthology import import_anthology
        r=import_anthology(ROOT)
        self.assertFalse(r['qualified']);self.assertEqual(r['record_count'],64)
        self.assertEqual(sum(len(g['moves']) for g in r['games'].values()),6890)
        self.assertEqual(max(len(g['moves']) for g in r['games'].values()),271)
        self.assertEqual(r['selection']['eligible_source_ordinals'],r['selection']['selected_source_ordinals'])

    def test_missing_independent_tool_preserves_import_diagnostics_without_qualification(self):
        from golden_board.anthology import qualify_anthology
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);locked(root,pgn(),1)
            # Tool-boundary failure injection; no mock behavior is the assertion.
            with patch('golden_board.anthology.independent_anthology',side_effect=ValueError('fixture reference unavailable')):
                report=qualify_anthology(root)
            self.assertFalse(report['qualified'])
            self.assertEqual(report['records'][0]['classification'],'eligible')
            self.assertIn('reference unavailable',report['qualification_error'])

    def test_explicit_game_compiler_and_player_batch_retain_all_frames_and_scores(self):
        from golden_board.authoring import game_document,audit_game,player_frames_batch
        games=[parse_mainline(pgn().encode()),parse_mainline(pgn('1. d4 d5','1/2-1/2').encode())]
        documents=[game_document(g) for g in games]
        frames=player_frames_batch(ROOT,documents)
        self.assertEqual([len(f) for f in frames],[3,3])
        for game,data,actual in zip(games,documents,frames):self.assertEqual(actual,audit_game(game,data))
        self.assertEqual(frames[0][1][36],32)
        self.assertEqual(frames[0][1][52],0)
        self.assertEqual(frames[0][-1][65],10)
        self.assertEqual(frames[1][-1][65],12)

    def test_missing_early_patch_fails_before_later_frames(self):
        from golden_board.authoring import game_document,audit_game
        from golden_board.document import decode_document,encode_document
        game=parse_mainline(pgn('1. e4 e5 2. Nf3').encode());doc=decode_document(game_document(game))
        trace=doc['records'][doc['entries'][0]]
        trace['steps'][0]=[v for v in trace['steps'][0] if v[0]!=52]
        bad=encode_document(doc['entries'],list(doc['records'].values()))
        with self.assertRaisesRegex(ValueError,'ply 1'):audit_game(game,bad)

    def test_complete_playback_includes_castling_en_passant_and_promotion_effects(self):
        from golden_board.authoring import game_document,audit_game,player_frames_batch
        lines=['1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. O-O',
               '1. e4 a6 2. e5 d5 3. exd6',
               '1. a4 h5 2. a5 h4 3. a6 h3 4. axb7 hxg2 5. bxa8=N']
        games=[parse_mainline(pgn(line).encode()) for line in lines]
        documents=[game_document(g) for g in games];actual=player_frames_batch(ROOT,documents)
        for game,doc,frames in zip(games,documents,actual):self.assertEqual(frames,audit_game(game,doc))
        self.assertEqual([actual[0][-1][i] for i in (60,61,62,63)],[0,35,37,0])
        self.assertEqual(actual[1][-1][27],0) # d5 captured pawn removed.
        self.assertEqual(actual[1][-1][19],32) # d6 capturing pawn.
        self.assertEqual(actual[2][-1][0],33) # white knight, explicitly chosen promotion.

    def test_unqualified_import_cannot_be_measured_as_qualified_playback(self):
        from golden_board.anthology_playback import measure_anthology
        from golden_board.anthology import import_anthology
        with self.assertRaisesRegex(ValueError,'qualified'):measure_anthology(ROOT,import_anthology(ROOT))


if __name__=='__main__':unittest.main()
