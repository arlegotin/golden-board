import unittest

from golden_board import bootstrap, recipe_wire_v1
from golden_board.m2_revision_recipe import build_revision_recipe_package
from golden_board.m2_teaching_recipe_v2 import build_teaching_recipe_package, teaching_examples


class TeachingRecipes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = build_teaching_recipe_package()
        cls.package = recipe_wire_v1.decode_recipe_package_v1(cls.raw, 8)

    def test_group_decision_includes_raw_repetition_and_preserves_conflicts(self):
        recipe = next(r for r in self.package.logical.recipes if r.recipe_id == 110)
        self.assertEqual(tuple((d.value_type,d.width) for d in recipe.inputs),
                         ((bootstrap.UINT,2),)*6+((bootstrap.BOOL,1),)*3,
                         'Fact10 still executes concatenation instead of the candidate decision')
        cases = (
            ((0,0,0,0,0,0,0,0,0), (0,0,0)),
            ((0,0,0,0,0,0,1,0,0), (0,1,0)),
            ((1,0,0,0,0,0,1,1,1), (1,2,1)),
            ((1,1,1,1,1,1,1,1,1), (1,2,1)),
            ((1,0,0,0,0,2,1,1,1), (3,4,0)),
            ((0,0,0,0,0,2,1,0,1), (2,3,1)),
            ((1,0,0,0,0,1,1,1,1), (1,2,1)),
            ((1,2,0,0,0,0,1,1,1), (3,4,0)),
            ((1,0,0,0,0,0,1,1,0), (1,2,0)),
        )
        for values, expected in cases:
            with self.subTest(values=values):
                actual = recipe_wire_v1.evaluate_recipe_v1(self.package,110,
                    tuple(bytes((v,)) for v in values))
                self.assertEqual(actual,bootstrap.RecipeResult(0,tuple(bytes((v,)) for v in expected)))

    def test_existing_programs_are_unchanged_and_new_resources_are_derived(self):
        old = recipe_wire_v1.decode_recipe_package_v1(build_revision_recipe_package(), 8).logical
        current = self.package.logical
        retained=tuple(r for r in old.recipes if r.recipe_id not in (106,110))
        self.assertNotIn(106,tuple(r.recipe_id for r in current.recipes))
        self.assertIn(106,tuple(r.recipe_id for r in old.recipes))
        self.assertEqual(tuple(r for r in current.recipes if r.recipe_id < 210 and r.recipe_id != 110), retained)
        self.assertNotEqual(next(r for r in current.recipes if r.recipe_id == 110),
                            next(r for r in old.recipes if r.recipe_id == 110))
        self.assertEqual(current.tables[:-1], old.tables)
        self.assertEqual(tuple(r.recipe_id for r in current.recipes if r.recipe_id >= 210),
                         (210, 211, 212, 213, 214))
        self.assertEqual(current.tables[-1].table_id, 21)
        self.assertEqual(current.tables[-1].payload, b'\x07\x08\x09')
        self.assertEqual(current.maximum_primitive_steps, old.maximum_primitive_steps)
        self.assertEqual(current.peak_live_scratch_bytes, old.peak_live_scratch_bytes)
        self.assertEqual(len(self.raw) - len(build_revision_recipe_package()), 2421)

    def test_carried_examples_discriminate_failures_and_output_suppression(self):
        rows = teaching_examples()
        self.assertEqual(len(rows), 8)
        for row in rows:
            actual = recipe_wire_v1.evaluate_recipe_v1(self.package, row.recipe_id, row.inputs)
            self.assertEqual(actual.status.to_bytes(2, 'big') + b''.join(actual.outputs),
                             row.output, row)
            if actual.status:
                self.assertEqual(actual.outputs, ())
        self.assertEqual({int.from_bytes(r.output[:2], 'big') for r in rows}, {0, 4, 11})
        self.assertEqual({n.opcode for r in self.package.logical.recipes if r.recipe_id in (210, 211, 212)
                          for n in r.nodes}, set(range(1, 26)))

    def test_iteration_index_advances_and_original_bytes_remain_immutable(self):
        for value, expected in ((0, 3), (10, 13), (252, 255)):
            self.assertEqual(recipe_wire_v1.evaluate_recipe_v1(self.package, 214, (bytes([value]),)),
                             bootstrap.RecipeResult(0, (bytes([expected]),)))
        for value in (253, 254, 255):
            self.assertEqual(recipe_wire_v1.evaluate_recipe_v1(self.package, 214, (bytes([value]),)),
                             bootstrap.RecipeResult(11, ()))
        worked = teaching_examples()[0]
        outputs = recipe_wire_v1.evaluate_recipe_v1(self.package, 211, worked.inputs).outputs
        self.assertEqual(outputs[18:20], (b'b', b'a\x02c'))
        self.assertEqual(outputs[26], b'abcabc')


if __name__ == '__main__':
    unittest.main()
