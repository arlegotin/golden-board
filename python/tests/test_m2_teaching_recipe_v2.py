import unittest

from golden_board import bootstrap, recipe_wire_v1, recipe_wire_v2
from golden_board.m2_recovery_recipe_v2 import _neutral_baseline, recovery_program_refined
from golden_board.m2_revision_recipe import build_revision_recipe_package
from golden_board.m2_teaching_recipe_v2 import build_teaching_recipe_package, teaching_examples


class TeachingRecipes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = build_teaching_recipe_package()
        cls.package = recipe_wire_v2.decode_recipe_package_v2(cls.raw, 8)

    def test_complete_constructor_preserves_observed_and_unknown_bits(self):
        tables = {t.table_id: t.payload for t in self.package.logical.tables}
        for case in (5, 6):
            for lane in range(5):
                token = tables[26][5*case+lane]
                source, unknown, first, count = tables[27][4*token:4*token+4]
                encoded = tables[24][216*source:216*(source+1)]
                for bit in (0, 58, 59, 63, 67, 72, 1727):
                    state = bytearray(4096)
                    state[0], state[3200] = 5, case
                    result = bootstrap._evaluate_validated_recipe(self.package.logical, 125,
                        (bytes(state), (1728*lane+bit).to_bytes(8, 'big')))
                    changed = first <= bit < first+count
                    erased = changed and unknown == 1
                    value = (encoded[bit//8] >> (7-bit%8)) & 1
                    value = 0 if erased else value ^ int(changed and unknown == 0)
                    state[1] = 1 << lane
                    state[22+432*lane+bit//8] = value << (7-bit%8)
                    state[22+432*lane+216+bit//8] = int(erased) << (7-bit%8)
                    self.assertEqual(result, bootstrap.RecipeResult(0, (bytes(state),)))
        for factor, case, iteration in ((5, 8, 0), (5, 255, 0), (2, 5, 2*1728)):
            state = bytearray(4096)
            state[0], state[3200] = factor, case
            result = bootstrap._evaluate_validated_recipe(self.package.logical, 125,
                (bytes(state), iteration.to_bytes(8, 'big')))
            self.assertEqual(result, bootstrap.RecipeResult(3, ()))

    def test_complete_entry_derives_context_and_invokes_shared_kernels(self):
        recipes = {r.recipe_id: r for r in self.package.logical.recipes}
        entry = recipes[126]
        self.assertEqual(tuple((d.value_type,d.width) for d in entry.inputs),
                         ((bootstrap.UINT,32), (bootstrap.UINT,8)))
        self.assertEqual(tuple(n.auxiliary_u16 for n in entry.nodes if n.opcode == 22),
                         (122, 125, 119))
        for rid in (120, 123, 124, 126, 127):
            self.assertTrue(recovery_program_refined(self.package, rid))
        self.assertFalse({106,110,111} & recipes.keys())

    def test_existing_programs_are_unchanged_and_new_resources_are_derived(self):
        old = recipe_wire_v1.decode_recipe_package_v1(build_revision_recipe_package(), 8).logical
        current = self.package.logical
        retained = tuple(r for r in old.recipes if r.recipe_id not in (106,110,111))
        old_ids = {r.recipe_id for r in retained}
        self.assertEqual(tuple(r for r in current.recipes if r.recipe_id in old_ids), retained)
        self.assertTrue({106,110,111}.issubset({r.recipe_id for r in old.recipes}))
        baseline = {r.recipe_id:r for r in _neutral_baseline().recipes}
        for recipe in current.recipes:
            if 114 <= recipe.recipe_id <= 127:
                self.assertEqual(recipe, baseline[recipe.recipe_id])
        inherited_tables = {t.table_id for t in old.tables}
        self.assertEqual(tuple(t for t in current.tables if t.table_id in inherited_tables), old.tables)
        self.assertEqual(tuple(t.table_id for t in current.tables if t.table_id not in inherited_tables),
                         (21,23,24,25,26,27))
        self.assertEqual(next(t.payload for t in current.tables if t.table_id == 21), bytes((7,8,9)))
        self.assertEqual(tuple(r.recipe_id for r in current.recipes if r.recipe_id >= 210),
                         (210,211,212,213,214))
        self.assertEqual(current.maximum_primitive_steps, max(r.primitive_steps for r in current.recipes))
        self.assertEqual(current.peak_live_scratch_bytes, max(r.peak_live_scratch_bytes for r in current.recipes))
        self.assertEqual(self.raw[8:10], bytes((0,2)))
        self.assertEqual(len(self.raw),17719)

    def test_carried_examples_discriminate_failures_and_output_suppression(self):
        rows = teaching_examples()
        self.assertEqual(len(rows), 8)
        for row in rows:
            actual = recipe_wire_v2.evaluate_recipe_v2(self.package, row.recipe_id, row.inputs)
            self.assertEqual(actual.status.to_bytes(2, 'big') + b''.join(actual.outputs),
                             row.output, row)
            if actual.status:
                self.assertEqual(actual.outputs, ())
        self.assertEqual({int.from_bytes(r.output[:2], 'big') for r in rows}, {0, 4, 11})
        self.assertEqual({n.opcode for r in self.package.logical.recipes if r.recipe_id in (210, 211, 212)
                          for n in r.nodes}, set(range(1, 26)))

    def test_iteration_index_advances_and_original_bytes_remain_immutable(self):
        for value, expected in ((0, 3), (10, 13), (252, 255)):
            self.assertEqual(recipe_wire_v2.evaluate_recipe_v2(self.package, 214, (bytes([value]),)),
                             bootstrap.RecipeResult(0, (bytes([expected]),)))
        for value in (253, 254, 255):
            self.assertEqual(recipe_wire_v2.evaluate_recipe_v2(self.package, 214, (bytes([value]),)),
                             bootstrap.RecipeResult(11, ()))
        worked = teaching_examples()[0]
        outputs = recipe_wire_v2.evaluate_recipe_v2(self.package, 211, worked.inputs).outputs
        self.assertEqual(outputs[18:20], (b'b', b'a\x02c'))
        self.assertEqual(outputs[26], b'abcabc')


if __name__ == '__main__':
    unittest.main()
