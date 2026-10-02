from dataclasses import replace
import os
import unittest

from golden_board import body_codec_v1, recipe_wire_v2
from golden_board.m2_teaching_recipe_v2 import build_teaching_recipe_package
from golden_board.m2_program_refinement_v2 import mapping_program_refined,body_program_refined,transport_programs_refined


class ProgramRefinement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = recipe_wire_v2.decode_recipe_package_v2(build_teaching_recipe_package(),8)

    def test_closure_checks_every_instruction_and_referenced_table(self):
        self.assertTrue(mapping_program_refined(self.package))
        self.assertTrue(body_program_refined(self.package))
        self.assertTrue(transport_programs_refined(self.package))
        for rid in (30,109,113,201,202):
            recipes = tuple(replace(r,nodes=(replace(r.nodes[0],immediate_u64=r.nodes[0].immediate_u64+1),*r.nodes[1:]))
                            if r.recipe_id == rid else r for r in self.package.logical.recipes)
            mutant = replace(self.package,logical=replace(self.package.logical,recipes=recipes))
            self.assertFalse((mapping_program_refined if rid == 109 else transport_programs_refined if rid in (30,113) else body_program_refined)(mutant))
        for tid in (3,4,5):
            tables = tuple(replace(t,payload=bytes((t.payload[0]^1,))+t.payload[1:])
                           if t.table_id == tid else t for t in self.package.logical.tables)
            self.assertFalse(body_program_refined(replace(self.package,logical=replace(self.package.logical,tables=tables))))
        # An unrelated teaching program does not affect this transitive closure.
        recipes = tuple(r for r in self.package.logical.recipes if r.recipe_id != 214)
        self.assertTrue(body_program_refined(replace(self.package,logical=replace(self.package.logical,recipes=recipes))))

    @unittest.skipUnless(os.environ.get('GB_M2_PROGRAM_REFINEMENT_FULL') == '1','explicit full generic202 refinement corpus')
    def test_native_and_actual_generic_program_agree(self):
        valid = [body_codec_v1.encode_lzss(raw) for raw in
                 (b'',b'12345678',b'AAAAAAAA',b'ABABABAB',bytes(range(32)),bytes(16384))]
        malformed = [b'',b'\3',b'\3\0',b'\2\0\x08',b'\3\x40\1',
                     b'\3\0\x08\x80\0\5',b'\3\0\x08\x40A\0\x14',
                     b'\3\0\x08\x41A\0\4',valid[2]+b'\0',valid[2][:-1]]
        for raw in (*valid,*malformed):
            with self.subTest(raw_length=len(raw),prefix=raw[:10].hex()):
                try:
                    decoded = body_codec_v1.decode_lzss(raw)
                    expected = (0,(len(decoded).to_bytes(2,'big'),decoded+bytes(16384-len(decoded))))
                except ValueError:
                    expected = (3,())
                result = recipe_wire_v2.evaluate_recipe_v2(self.package,202,
                    (raw+b'\xff'*(16384-len(raw)),len(raw).to_bytes(2,'big')))
                self.assertEqual((result.status,result.outputs),expected)


if __name__ == '__main__':
    unittest.main()
