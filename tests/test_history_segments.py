"""Actual branch sharing, complete literal boundaries and honest references."""
import unittest
from copy import deepcopy
from golden_board.history_segments import HistorySegments
from golden_board.course_author import CourseAuthor
from golden_board.course_generic import add_numeric_glyphs
from golden_board.course_practical import _decoded_frames
from golden_board.document import decode_document
from golden_board.practical_cases import CYCLE
from golden_board.practical_state import history

class HistorySegmentTests(unittest.TestCase):
    def product(self):
        a=CourseAuthor();add_numeric_glyphs(a)
        cycle=' '.join((CYCLE*2).split())
        prefixes=['',' '.join(CYCLE.split()),cycle,cycle+' a2a3',cycle+' d2d4']
        ids={p:i+1 for i,p in enumerate(prefixes)};f=HistorySegments(a,ids,{cycle})
        return a,f,ids

    def test_shared_branch_stores_each_suffix_once_with_complete_boundaries(self):
        a,f,ids=self.product()
        self.assertEqual(sum(len(c['frames'])-1 for c in f.carriers.values()),10,
                         'Shared eight-ply prefix must not be stored independently in both branches.')
        contexts={p:f.context(p)[0] for p in ids}
        directory=a.page('directory',a.trace([[0]],1,1,data=[a.table(f.directory_rows(contexts),6),a.table(f.segment_rows(),11)]),trace=True,links=list(f.node_frames()))
        d=decode_document(a.encode([directory]));f.validate(d,contexts,directory,f.describe())
        descriptors=[f.segment_rows()[i:i+11] for i in range(0,len(f.segment_rows()),11)]
        byid={r[0]:r for r in descriptors}
        for prefix in ids:
            seg=f.segment_for[prefix];chain=[]
            while seg!=65535:chain.append(byid[seg]);seg=byid[seg][3]
            actual=[]
            for row in reversed(chain):
                frames=_decoded_frames(d,row[1])
                if actual:self.assertEqual(actual[-1],frames[0]);actual.extend(frames[1:])
                else:actual.extend(frames)
            expected=history(prefix);self.assertEqual(len(actual),len(expected))
            for frame,state in zip(actual,expected):
                self.assertEqual([v for y in range(8) for v in frame[y*9:y*9+8]],state['occupancy'])

    def test_wrong_parent_cycle_and_boundary_are_rejected(self):
        a,f,ids=self.product();contexts={p:f.context(p)[0] for p in ids}
        self.assertTrue(hasattr(f,'segment_rows'),'Explicit parent/trace directory is missing.')
        directory=a.page('directory',a.trace([[0]],1,1,data=[a.table(f.directory_rows(contexts),6),a.table(f.segment_rows(),11)]),trace=True,links=list(f.node_frames()))
        d=decode_document(a.encode([directory]));broken=deepcopy(d)
        trace=broken['records'][broken['records'][directory]['display']];table=broken['records'][trace['data'][1]]
        table['values'][14]=table['values'][11]
        with self.assertRaises(ValueError):f.validate(broken,contexts,directory,f.describe())

if __name__=='__main__':unittest.main()
