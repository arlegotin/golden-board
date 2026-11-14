"""Hand-derived advanced relations and finite witness boundaries, author-time only."""
from pathlib import Path
from copy import deepcopy
import importlib.util,unittest
import chess

ROOT=Path(__file__).resolve().parents[1]
def cell(text):
    from golden_board.source_game import cell_index
    return cell_index(chess.parse_square(text))

class AdvancedStateTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('golden_board.advanced_state'),
                             'Exact advanced relation/schedule/proof authoring is absent.')
        from golden_board import advanced_state
        return advanced_state

    def test_pin_fork_targets_and_along_ray_legality(self):
        p=self.api();b=chess.Board('7k/6b1/8/1r6/4q3/2N5/8/K7 w - - 0 1')
        r=p.relations(b,cell('c3'))
        self.assertEqual(r['pins'],[[cell('a1'),cell('c3'),cell('g7')]])
        self.assertEqual(r['attacked'],[cell('b5'),cell('e4')]);self.assertTrue(r['fork'])
        b.set_piece_at(chess.B2,chess.Piece(chess.PAWN,True));self.assertEqual(p.relations(b,cell('c3'))['pins'],[])
        from golden_board.practical_state import coherent
        replay,_=coherent('e2e4 d7d6 f1b5 c7c6 b1c3')
        self.assertIn('c6b5',replay.legal_moves);self.assertNotIn('c6c5',replay.legal_moves)

    def test_discovered_stationary_slider_and_vacated_king_capture(self):
        p=self.api();r=p.discovered('b2b3 d7d5 c1b2 e7e6 b1c3 g8f6','c3b5')
        self.assertEqual(r['pairs'],[[cell('b2'),cell('f6')]])
        self.assertEqual(r['checks'],[])
        r=p.discovered('e2e4 e7e5 f1c4 b8c6 d1h5 g8f6','h5f7')
        self.assertEqual(r['pairs'],[]);self.assertTrue(r['effect']['after']['check'])
        prefix=('e2e4 g8f6 a2a3 f6g4 a3a4 g4f2 a4a5 f2d1 b2b3 d7d6 '
                'b3b4 c8g4 b4b5 g4h3 c2c3 h3g2 e1e2 g2f3')
        r=p.escape(prefix,'e2d1')
        self.assertFalse(r['premove_attacked']);self.assertTrue(r['effect']['move_probe']['king_attacked'])
        self.assertFalse(r['effect']['accepted'])
        self.assertTrue(p.escape(prefix,'e2f3')['effect']['accepted'])

    def test_passed_and_file_directions_and_nonpawn_neutrality(self):
        p=self.api();b=chess.Board('7k/8/8/2pP4/8/8/8/K7 w - - 0 1')
        r=p.file_facts(b,0,0,cell('d5'))
        self.assertTrue(r['passed']);self.assertTrue(r['open']);self.assertFalse(r['semiopen'])
        self.assertEqual(r['opposing_exclusions'],[])
        b.remove_piece_at(chess.C5);b.set_piece_at(chess.C6,chess.Piece(chess.PAWN,False))
        self.assertFalse(p.file_facts(b,0,0,cell('d5'))['passed'])
        b.set_piece_at(chess.A4,chess.Piece(chess.ROOK,True))
        self.assertTrue(p.file_facts(b,0,0,cell('d5'))['open'])
        self.assertTrue(p.file_facts(b,0,2,cell('d5'))['semiopen'])
        self.assertFalse(p.file_facts(b,1,2,cell('c6'))['semiopen'])

    def fixtures(self):
        self.api()
        from golden_board.advanced_fixtures import fixtures
        return fixtures(ROOT)

    def test_coherent_mating_routes_and_promotion_interference(self):
        p=self.api();f=self.fixtures()
        q=p.scheduled(f['queen'],'h4g3 g1f1 g3f2')
        self.assertEqual((q['states'][-1]['reason'],q['states'][-1]['score']),('checkmate',0))
        r=p.scheduled(f['rook'],'c3b3 b1a1 h2h1')
        self.assertEqual((r['states'][-1]['reason'],r['states'][-1]['score']),('checkmate',1))
        r=p.scheduled(f['rook'],'c3b3 b1c1 h2h1 c1d2');self.assertFalse(r['states'][-1]['closed'])
        a=p.scheduled(f['pawn'],'e7f6 h4h3 g6g7 h3h2 g7g8q')
        self.assertEqual(a['first_promotion'],{'side':0,'ply':5,'choice':1});self.assertFalse(a['states'][-1]['closed'])
        b=p.scheduled(f['pawn'],'e7d7 h4g5 d7c7 g5f6 g6g7 f6f7 g7g8q f7g8')
        self.assertEqual(b['states'][-1]['reason'],'common-dead');self.assertEqual(b['states'][-1]['score'],2)

    def test_full_defender_reply_tree_and_missing_active_draw_limits(self):
        p=self.api();f=self.fixtures();tree={'children':{'h4g3':{'children':{
            'g1f1':{'children':{'g3f2':{}}},'g1h1':{'children':{'g3g2':{}}}}}}}
        r=p.proof(f['queen'],0,tree);self.assertTrue(r['available']);self.assertTrue(r['winning'])
        defense=next(n for n in r['nodes'] if n['role']=='defender')
        self.assertEqual(defense['domain'],['g1f1','g1h1']);self.assertEqual(defense['claims'],[])
        broken=deepcopy(tree);del broken['children']['h4g3']['children']['g1h1']
        r=p.proof(f['queen'],0,broken);self.assertFalse(r['available']);self.assertIsNone(r['winning'])
        self.assertIn('missing-defender-reply',r['errors'])
        for negative in ({},{'children':{'h4h3':{}}}):
            self.assertFalse(p.proof(f['queen'],0,negative)['available'])
        cycle='g1f3 g8f6 f3g1 f6g8 '*2
        r=p.proof(cycle,1,{});self.assertFalse(r['available'])
        self.assertIn('claim:threefold',r['nodes'][0]['domain'])
        cyclic={};cyclic['children']={'h4g3':cyclic}
        with self.assertRaises(ValueError):p.proof(f['queen'],0,cyclic)

    def test_original_minor_departure_survives_return_and_facts_do_not_rank(self):
        p=self.api();r=p.guidance('g1f3 g8f6 f3g1 f6g8')
        self.assertEqual(r['departed'],[cell('g8'),cell('g1')])
        self.assertEqual(r['minor_locations'][cell('g1')],cell('g1'))
        self.assertEqual(r['material']['totals'],[39,39]);self.assertIsNone(r['advantage'])
        self.assertEqual(len(r['legal']),20);self.assertIsNone(r['best_move'])

if __name__=='__main__':unittest.main()
