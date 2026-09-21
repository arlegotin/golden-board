import unittest

from golden_board import bootstrap, m2_recipe, recipe_wire_v1
from golden_board.m2_revision_recipe import build_revision_recipe_package


class RevisionRecipe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = build_revision_recipe_package()
        cls.package = recipe_wire_v1.decode_recipe_package_v1(cls.raw, 8)

    def test_new_identity_preserves_base_programs_and_adds_complete_codec(self):
        old = bootstrap.decode_recipe_package(m2_recipe.build_r3_recipe_package(), 7)
        new = self.package.logical
        self.assertEqual(new.tables, old.tables)
        self.assertEqual(tuple(r.recipe_id for r in new.recipes),
                         tuple(r.recipe_id for r in old.recipes) + (201, 202, 203))
        self.assertEqual(new.total_node_count, 699 + 374)
        self.assertEqual(new.maximum_primitive_steps, 2375776)
        self.assertEqual(new.peak_live_scratch_bytes, 98398)
        self.assertEqual(len(self.raw), 16240)
        for original, revised in zip(old.recipes, new.recipes):
            if original.recipe_id != 109:
                self.assertEqual(original, revised)
        with self.assertRaises(bootstrap.BootstrapReject):
            bootstrap.decode_recipe_package(self.raw, 8)
        with self.assertRaises(bootstrap.BootstrapReject):
            recipe_wire_v1.decode_recipe_package_v1(self.raw, 7)

    def test_profile8_keeps_crc32_and_uses_its_own_affine_offset(self):
        result = recipe_wire_v1.evaluate_recipe_v1(self.package, 107, (b'123456789',))
        self.assertEqual(result, bootstrap.RecipeResult(0, (bytes.fromhex('e3069283'),)))
        for logical, side, width in ((0, 2048, 112), (1727, 2048, 112), (123456, 1952, 128)):
            actual = recipe_wire_v1.evaluate_recipe_v1(self.package, 109,
                (logical.to_bytes(4, 'big'), side.to_bytes(2, 'big'), width.to_bytes(2, 'big')))
            interior = side - 2 * width
            expected = ((2 * interior - 1) * logical + 8 * 40503 + width * 257) % (interior * interior)
            self.assertEqual(actual, bootstrap.RecipeResult(0, (expected.to_bytes(4, 'big'),)))

    def test_small_codec_wrapper_executes_from_compact_bytes(self):
        result = recipe_wire_v1.evaluate_recipe_v1(self.package, 203,
            (b'\x40A\0\4' + bytes(5), b'\0\4'))
        self.assertEqual(result, bootstrap.RecipeResult(0, (b'AAAAAAAA',)))


if __name__ == '__main__':
    unittest.main()
