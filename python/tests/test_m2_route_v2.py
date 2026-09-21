from pathlib import Path
import unittest

from golden_board import recipe_wire_v1, m2_route_data
from golden_board.m2_slice_v1 import compile_slice_v1
from golden_board.m2_route_v2 import build_route_prefixes_v2, build_route_images_v2, validate_route_prefix_v2

ROOT = Path(__file__).resolve().parents[2]


class RevisedRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources = ('studies/m2/slice-v1.json', 'studies/m2/slice-v0.json',
                   'conformance/content-v0.json', 'conformance/chess-v0.json',
                   'reports/game-set-v0.bin', 'spec/content-v0.md',
                   'spec/constants-v0.toml', 'spec/curriculum-v0.toml')
        cls.compiled = compile_slice_v1(*(ROOT.joinpath(p).read_bytes() for p in sources))
        cls.prefixes = build_route_prefixes_v2(cls.compiled)

    def test_four_complete_routes_have_all_tables_and_failures(self):
        self.assertEqual(len(set(self.prefixes)), 4)
        for sector, raw in enumerate(self.prefixes):
            records = validate_route_prefix_v2(raw, self.compiled, sector)
            self.assertEqual(len(records), 47)
            self.assertFalse(any(row.kind == 4 for row in records))
            package_record, = (r for r in records if r.kind == 5)
            package = recipe_wire_v1.decode_recipe_package_v1(package_record.payload, 8)
            self.assertEqual(len(package.logical.tables), 14)
            self.assertTrue({17, 21}.issubset({t.table_id for t in package.logical.tables}))
            cases = [r for r in records if r.kind in (2, 3)]
            statuses = set()
            for row in cases:
                payload = row.payload
                rid = int.from_bytes(payload[2:4], 'big')
                length = int.from_bytes(payload[4:8], 'big')
                statuses.add(int.from_bytes(payload[12+length:14+length], 'big'))
                self.assertIn(rid, {r.recipe_id for r in package.logical.recipes})
            self.assertEqual(statuses, {0, 4, 11})

    def test_shell_accounting_fits_with_unchanged_headroom(self):
        images = build_route_images_v2(self.compiled, 2048, 112)
        self.assertEqual(images.instruction_cells, sum(len(p)*8 for p in self.prefixes))
        self.assertEqual(images.headroom_cells, max((images.instruction_cells+19)//20, 1024))
        for sector, prefix in zip(images.sectors, self.prefixes):
            self.assertEqual(len(sector.data)*8, 112*(2048-112))
            self.assertEqual(sector.data[:len(prefix)], prefix)
            self.assertEqual(sum(s.cell_count for s in sector.spans), len(sector.data)*8)
            self.assertGreaterEqual(sector.headroom_cells, 256)

    def test_prefix_extraction_ignores_tail_but_rejects_carried_mutations(self):
        for sector, raw in enumerate(self.prefixes):
            expected = validate_route_prefix_v2(raw, self.compiled, sector)
            self.assertEqual(validate_route_prefix_v2(raw+b'\xff'*300, self.compiled, sector), expected)
            for offset in (0, 40, 44, 46, 48, 52, 56, 62, 64, len(raw)-1):
                damaged = bytearray(raw)
                damaged[offset] ^= 1
                with self.subTest(sector=sector, offset=offset), self.assertRaises(m2_route_data.RouteDataError):
                    validate_route_prefix_v2(bytes(damaged), self.compiled, sector)
            with self.assertRaises(m2_route_data.RouteDataError):
                validate_route_prefix_v2(raw[:-1], self.compiled, sector)


if __name__ == '__main__':
    unittest.main()
