"""Exact fixed-width move data, unchanged literal playback and explicit teaching."""
from pathlib import Path
import importlib.util,json,subprocess,unittest
from copy import deepcopy
from golden_board.document import decode_document

ROOT=Path(__file__).resolve().parents[1]

class MovePackingTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('golden_board.move_packing'),
                             'Fixed6/6/3move records are not implemented.')
        from golden_board import move_packing
        return move_packing

    def test_hand_bit_boundaries_and_invalid_values_never_mask(self):
        p=self.api()
        self.assertEqual(p.pack_move([63,0,4]),0x7e04)
        self.assertEqual(p.unpack_move(0x01fa),[0,63,2])
        for row in ([64,0,0],[0,64,0],[0,0,5],[True,0,0],[-1,0,0]):
            with self.assertRaises(ValueError):p.pack_move(row)
        for value in (0x8000,5,6,7,-1,65536,True):
            with self.assertRaises(ValueError):p.unpack_move(value)

    def test_all64_actual_moves_and_playback_dependencies_preserved(self):
        p=self.api();original=(ROOT/'evidence/S03-shared-anthology/actual-document.bin').read_bytes()
        from golden_board.qualified_inputs import current_document
        original=current_document(original,'anthology')
        body=p.pack_anthology(original);a,b=decode_document(original),decode_document(body)
        self.assertEqual(a['entries'],b['entries']);count=0
        from golden_board.advanced_fixtures import qualified
        truth=qualified(ROOT)
        for ordinal,entry in enumerate(a['entries'],1):
            x,y=a['records'][entry],b['records'][entry]
            for key in ('initial','steps'):self.assertEqual(x[key],y[key])
            self.assertEqual(b['records'][y['data'][2]]['values'],[16,1,6,6,3])
            old=a['records'][x['data'][0]];new=b['records'][y['data'][0]]
            moves=[p.unpack_move(v) for v in new['values']]
            source=truth['games'][str(truth['canonical_games'][ordinal-1]['source_ordinal'])]['moves']
            self.assertEqual(moves,source);self.assertEqual(new['cols'],1)
            self.assertEqual([n for row in moves for n in row],old['values']);count+=len(moves)
            self.assertEqual(a['records'][x['data'][1]],b['records'][y['data'][1]])
        self.assertEqual(count,6890)
        for ident,r in a['records'].items():
            if r['kind'] in (1,2):self.assertEqual(r,b['records'][ident])
        request={'original':original.hex(),'packed':body.hex()}
        run=subprocess.run(['node',str(ROOT/'tools/audit-move-packing.mjs')],input=json.dumps(request),capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr);self.assertEqual(json.loads(run.stdout)['moves'],6890)

    def test_actual_field_teaching_separates_boundaries_choices_and_unavailable(self):
        self.assertIsNotNone(importlib.util.find_spec('golden_board.course_move_packing'),
                             'Packed fields have no ostensive teaching/practice/passive source.')
        from golden_board.course_move_packing import packing_groups,solve,render
        gs=packing_groups(ROOT);self.assertEqual(len(gs),1)
        specs=[s for q in gs[0]['queries'] for s in [q['worked_input'],*q['worked_variants']]]
        rows=[s['row'] for s in specs if s['op']=='pack']
        self.assertEqual({r[2] for r in rows},{0,1,2,3,4})
        self.assertTrue(any(r[0]==0 for r in rows));self.assertTrue(any(r[0]==63 for r in rows))
        self.assertTrue(any(r[1]==0 for r in rows));self.assertTrue(any(r[1]==63 for r in rows))
        s={'op':'pack','row':[63,0,4]};f=render(s,solve(s))
        self.assertEqual(f[11*26:11*26+16],[1 if (0x7e04>>i)&1 else 2 for i in range(15,-1,-1)])
        for code in (32768,5):
            s={'op':'unpack','value':code};self.assertIsNone(solve(s));f=render(s,solve(s),complete=True)
            self.assertEqual(f[14*26],2)
            self.assertEqual(f[9*26:9*26+2],[0,0])

    def test_field_roles_bind_actual_moves_and_every_promotion_choice(self):
        from golden_board.course_move_packing import packing_groups,solve,render
        from golden_board.practical_state import evaluate,move_row
        from golden_board.practical_cases import move
        gs=packing_groups(ROOT);specs=[s for q in gs[0]['queries'] for s in [q['worked_input'],*q['worked_variants']] if 'prefix' in s]
        self.assertTrue(specs,'Generic bit fields must be bound to actual record steps.')
        choices=set()
        for s in specs:
            effect=evaluate(move(s['prefix'],s['move']));self.assertTrue(effect['accepted'])
            row=move_row(s['move']);fields=[row[0]*8+row[1],row[2]*8+row[3],row[4]]
            if row[4]:choices.add(row[4])
            expected=fields if s['op']=='unpack' else self.api().pack_move(fields)
            self.assertEqual(solve(s),expected);f=render(s,expected)
            for y in range(8):
                self.assertEqual(f[y*26:y*26+8],effect['before']['occupancy'][y*8:y*8+8])
                self.assertEqual(f[y*26+9:y*26+17],effect['after']['occupancy'][y*8:y*8+8])
            self.assertGreater(s['history_id'],0)
        self.assertEqual(choices,{1,2,3,4})

if __name__=='__main__':unittest.main()
