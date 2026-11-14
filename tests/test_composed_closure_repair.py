"""Actual serialized discriminators for the two surviving c0017 interpretations."""
from pathlib import Path
import json
import unittest
import chess
from golden_board.course_generic import build_generic
from golden_board.course_foundation import build_foundation,coherent,foundation_result
from golden_board.document import decode_document

ROOT=Path(__file__).resolve().parents[1]

def query(product,name):
    return next(q for g in product['groups']for q in g['queries']if q['id']==name)

def frames(product,name,role):
    c=next(c for c in product['cases']if any(q['id']==name for q in c.get('queries',[])))
    q=next(q for q in c['queries']if q['id']==name)
    d=decode_document(product['document']);page=d['records'][c['worked'if role=='contrast'else role]]
    trace=d['records'][page['display']];cells=list(d['records'][trace['initial']]['cells']);out=[cells[:]]
    for changes in trace['steps']:
        for i,v in changes:cells[i]=v
        out.append(cells[:])
    a,b=q[role+'_steps'];return out[a:b+1]

def output(frame):
    dec=lambda v:None if v==0 else 0 if v==22 else v-12
    return [[dec(frame[r*16+c])for c in (12,13,14)]for r in range(4,8)]

class ComposedClosureRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.generic=build_generic();cls.foundation=build_foundation(ROOT)



    def test_active_pseudo_valid_failed_evasions_separate_prior_from_diagnostic(self):
        q=query(self.foundation,'prior-closure')
        for s,evasion in ((q['worked_input'],'g2g3'),(q['input'],'c6e5')):
            state=coherent(s['prefix'])[0];b=chess.Board(state.fen);m=chess.Move.from_uci(s['move'])
            self.assertTrue(b.is_check());self.assertFalse(state.closed)
            self.assertTrue(b.is_pseudo_legal(m));self.assertNotIn(m,b.legal_moves)
            self.assertIn(chess.Move.from_uci(evasion),b.legal_moves)
            trial=b.copy();trial.push(m)
            king=trial.king(b.turn);self.assertTrue(trial.is_attacked_by(not b.turn,king))
            result=foundation_result(s)
            self.assertEqual((result['accepted'],result['closed_before'],result['closed_after']),(False,False,False))
            self.assertEqual(result['after_side'],state.side_to_move)
        fs=frames(self.foundation,'prior-closure','contrast')
        self.assertEqual([i for i,(a,b)in enumerate(zip(fs[0][:200],fs[1][:200]))if a!=b],[99,198])
        self.assertEqual(fs[1][197:200],[22,22,22])
        self.assertEqual([fs[1][r*10+c]for r in range(1,9)for c in range(1,9)],
                         [fs[1][r*10+c]for r in range(11,19)for c in range(1,9)])


if __name__=='__main__':unittest.main()
