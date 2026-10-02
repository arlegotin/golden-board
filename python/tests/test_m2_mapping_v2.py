import unittest

from golden_board import m2_mapping_v2 as mapping


class RevisionMapping(unittest.TestCase):
    def test_nontrivial_multiplier_and_profile_offset(self):
        row = mapping.mapping_parameters(1952, 128)
        self.assertEqual((row.interior, row.population, row.units, row.slot_multiplier,
                          row.slot_inverse, row.cell_multiplier, row.cell_inverse, row.offset),
                         (1696, 2876416, 1664, 15, 111, 3391, 2873023, 356920))
        self.assertEqual(mapping.map_unit_bit(1952, 128, 1, 0), 356920)
        for unit in (1, 2, 111, 112, row.units):
            for bit in (0, 1, 1727):
                physical = mapping.map_unit_bit(1952, 128, unit, bit)
                self.assertEqual(mapping.invert_interior_cell(1952, 128, physical), (0, unit, bit))

    def test_protected_pad_boundary_and_new_geometry(self):
        for side, width in ((1952, 128), (2040, 128), (2048, 112)):
            row = mapping.mapping_parameters(side, width)
            logical = 1728 * row.units - 1
            physical = (row.cell_multiplier * logical + row.offset) % row.population
            kind, unit, bit = mapping.invert_interior_cell(side, width, physical)
            self.assertEqual((kind, bit), (0, 1727))
            self.assertEqual(mapping.map_unit_bit(side, width, unit, bit), physical)
            for logical in range(1728 * row.units, row.population):
                physical = (row.cell_multiplier * logical + row.offset) % row.population
                self.assertEqual(mapping.invert_interior_cell(side, width, physical), (1, 0, 0))

    def test_adapter_rejects_domains_the_modular_primitive_does_not(self):
        mapping.mapping_parameters(2048, 112)  # Populate cache before type mutations.
        for side, width in ((63, 8), (2047, 111), (2048, 0), (2048, 129), (64, 32),
                            (2048.0, 112), (2048, 112.0), (True, 8), (64, 8)):
            with self.subTest(side=side, width=width), self.assertRaises(ValueError):
                mapping.mapping_parameters(side, width)
        row = mapping.mapping_parameters(2048, 112)
        for unit, bit in ((0, 0), (row.units + 1, 0), (1, 1728), (-1, 0),
                          (1, -1), (True, 0), (1, False), (1.0, 0)):
            with self.assertRaises(ValueError):
                mapping.map_unit_bit(2048, 112, unit, bit)
        for physical in (-1, row.population, 0xffffffff, True, 1.0):
            with self.assertRaises(ValueError):
                mapping.invert_interior_cell(2048, 112, physical)


if __name__ == '__main__':
    unittest.main()
