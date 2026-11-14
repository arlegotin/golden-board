"""Serialized witnesses for three actual source-compatible recipient rivals."""
from pathlib import Path
import json
import subprocess
import unittest

from golden_board.course_advanced import build_advanced
from golden_board.course_author import passive_reachable
from golden_board.course_practical import _decoded_frames
from golden_board.document import decode_document

ROOT=Path(__file__).resolve().parents[1]


class TeachingBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.product=build_advanced(ROOT)
        cls.document=decode_document(cls.product['document'])
        cls.queries={q['id']:q for g in cls.product['groups'] for q in g['queries']}

    def detail(self,spec):
        node=self.product['details'][str(spec['context_id'])]
        self.assertIn(node,passive_reachable(self.product['document']))
        page=self.document['records'][node]
        trace=self.document['records'][page['display']]
        return _decoded_frames(self.document,node),[self.document['records'][i] for i in trace['data']]

    def number(self,tokens):
        self.assertTrue(all(t in range(13,23) for t in tokens),'Numeric zero must be visible, not glyph blank0.')
        value=0
        for token in tokens:value=10*value+(0 if token==22 else token-12)
        return value

    def field(self,frame,index):
        offset=(10+index%12)*26+(13 if index>=12 else 0)
        self.assertEqual(frame[offset+3],1,'The literal numeric field must be available.')
        return self.number(frame[offset+5:offset+9])

    def test_captured_originals_teach_presence_and_literal_zero_location(self):
        # Reverting to only surviving-original examples must fail this witness.
        q=self.queries['minor_development_observable_departures']
        frames,tables=self.detail(q['input'])
        table=next(t for t in tables if t['cols']==4 and t['rows']==8)
        rows=[table['values'][i:i+4] for i in range(0,32,4)]
        self.assertEqual({row[0] for row in rows},{1,2,5,6,57,58,61,62})
        absent=[r for r in rows if r[1]==0]
        self.assertTrue(absent,'The source still has no numeric captured-original row.')
        self.assertTrue(all(row[2]==0 for row in absent))
        shown=[[self.field(frame,i) for i in range(4)] for frame in frames]
        self.assertEqual(shown,rows,'Visible fourfields must explain the literal table, including absent location0.')
        # Returned originals are still present, at origin, and have departed.
        _,worked=self.detail(q['worked_input'])
        returned=next(t for t in worked if t['cols']==4 and t['rows']==8)
        returned=[returned['values'][i:i+4] for i in range(0,32,4)]
        self.assertIn([62,1,62,1],returned)
        self.assertIn([6,1,6,1],returned)
        initial=next(s for s in q['worked_variants'] if s['prefix']=='')
        _,tables=self.detail(initial)
        pristine=next(t for t in tables if t['cols']==4 and t['rows']==8)
        self.assertTrue(all(pristine['values'][i:i+4]==[pristine['values'][i],1,pristine['values'][i],0]
                            for i in range(0,32,4)))

    def test_mixed_independent_proposals_discriminate_legal_destination_mask(self):
        # An all-legal source cannot distinguish all-proposal marking.
        q=self.queries['compare_only_shown_finite_continuations']
        self.assertEqual(q['expected']['values'],[2,1,1,0,None],
                         'A legal and an illegal independent proposal must be carried.')
        frame=q['options'][q['correct']]
        mask={i for i in range(64) if frame[(i//8)*26+18+i%8]}
        self.assertEqual(mask,{34})       # f1c4 legal; d2d5 illegal.
        self.assertNotEqual(mask,{34,27}) # The actual source-compatible rival.
        _,tables=self.detail(q['input'])
        offered=next(t for t in tables if t['cols']==3 and t['rows']==2)
        self.assertEqual(offered['values'],[61,34,0,51,27,0])
        # Keep the established independent-versus-sequential all-legal witness.
        other=self.queries['legal_alternative_not_automatically_bad']
        self.assertEqual(other['expected']['values'],[2,2,1,1,None])

    def test_every_seek_event_is_carried_and_invalid_request_retains_actual_view(self):
        q=self.queries['seek_backward_forward_equivalence'];spec=q['worked_input']
        n=q['worked_expected']['detail']['plies'];requests=spec['seeks']
        invalid=[i for i,value in enumerate(requests) if not 0<=value<=n]
        self.assertTrue(invalid,'There is no source contrast for aggregate invalid-route0.')
        self.assertTrue(all(0<i<len(requests)-1 for i in invalid))
        self.assertTrue(0<=spec['ply']<=n)
        frames,tables=self.detail(spec)
        self.assertEqual(len(frames),len(requests),'Do not skip the decisive refusal event.')
        self.assertTrue(any(t['cols']==1 and t['values']==requests for t in tables))
        # Actual generic mechanism on doc2; doc5detail has a different trace bound.
        from golden_board.anthology_input import load_anthology
        _,body=load_anthology(ROOT);doc=decode_document(body);entry=doc['entries'][spec['ordinal']-1]
        script="""
import {readFileSync} from 'node:fs';
import {decodeDocument,Player} from './mechanism/player.mjs';
const x=JSON.parse(readFileSync(0,'utf8')),p=new Player(decodeDocument(Buffer.from(x.body,'hex')),x.entry);
const events=x.requests.map(seek=>{const before=p.packet(),r=p.action({seek}),after=p.packet();
return {ok:r.ok,unchanged:JSON.stringify(before)===JSON.stringify(after),step:after.step,cells:after.frame.cells};});
process.stdout.write(JSON.stringify(events));
"""
        run=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,
            input=json.dumps({'body':body.hex(),'entry':entry,'requests':requests}),capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr);events=json.loads(run.stdout)
        for request,frame,event in zip(requests,frames,events,strict=True):
            self.assertEqual(self.field(frame,0),int(event['ok']))
            self.assertEqual(self.field(frame,5),request)
            self.assertEqual(self.field(frame,7),0)
            self.assertEqual([frame[(i//8)*26+9+i%8] for i in range(64)],event['cells'][:64])
            if not event['ok']:self.assertTrue(event['unchanged'])
        self.assertEqual(events[-1]['step'],spec['ply'])
        self.assertEqual(q['worked_expected']['values'][0],1)
        self.assertEqual(q['worked_expected']['values'][7],0)
        self.assertEqual(q['expected']['values'][7],1) # all-valid practice
        bad_final=next(v for v in q['worked_variants'] if v['ply']>n)
        from golden_board.advanced_cases import evaluate
        result=evaluate(bad_final,ROOT)
        self.assertEqual((result['values'][0],result['values'][7]),(0,1))


if __name__=='__main__':unittest.main()
