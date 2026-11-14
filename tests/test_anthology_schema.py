"""Current collection explicitly carries the compact move-field schema."""
from pathlib import Path
import unittest
from golden_board.anthology_input import load_anthology
from golden_board.document import decode_document

ROOT=Path(__file__).resolve().parents[1]
class AnthologySchemaTests(unittest.TestCase):
    def test_current_loader_delivers_one_shared_schema_and_all_move_rows(self):
        _,body=load_anthology(ROOT);d=decode_document(body);schemas=set();moves=0
        for entry in d['entries']:
            trace=d['records'][entry]
            self.assertEqual(len(trace['data']),3)
            schemas.add(trace['data'][2]);table=d['records'][trace['data'][0]]
            self.assertEqual(table['cols'],1);moves+=table['rows']
        self.assertEqual(len(schemas),1);self.assertEqual(moves,6890)
        self.assertEqual(d['records'][schemas.pop()]['values'],[16,1,6,6,3])
