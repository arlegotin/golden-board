from dataclasses import replace
from pathlib import Path
import unittest

from golden_board import bootstrap as base
from golden_board import bootstrap_v2 as revised


def inventory_fixture():
    bodies = (16, 17, 18, *range(100, 164), *range(200, 211))
    entries = [
        base.InventoryEntry(1, 1, 2, 128, 1, 1, (), 8 + 20 * 81 + 4 * 81,
                            physical_replica_count=5),
        base.InventoryEntry(2, 2, 0, 128, 1, 1, (16, 17, 18), 46,
                            physical_replica_count=5),
        base.InventoryEntry(3, 2, 0, 128, 1, 1, bodies, 346,
                            physical_replica_count=5),
    ]
    entries.extend(base.InventoryEntry(
        sid, 3, int(sid in (16, 17, 18)), 128 if sid < 100 else 129,
        1, 1, (), 100, sid - 100 if 100 <= sid < 164 else None,
        5 if sid < 100 else 1,
    ) for sid in bodies)
    return base.Inventory(tuple(entries), 2)


class RevisedInventory(unittest.TestCase):
    def test_exact_required_closure_and_old_admission_are_separate(self):
        source = inventory_fixture()
        encoded = revised.encode_inventory(source)
        self.assertEqual(revised.decode_inventory(encoded), source)
        self.assertEqual(encoded[:8], b'\0\2\0Q\0\0\0@')
        with self.assertRaises(base.BootstrapReject):
            base.decode_inventory(encoded)
        with self.assertRaises(base.BootstrapReject):
            base.encode_inventory(source)
        for version in (0, 1, True):
            with self.assertRaises(base.BootstrapReject):
                revised.encode_inventory(replace(source, version=version))

    def test_downgraded_spine_and_mixed_roles_reject(self):
        source = inventory_fixture()
        for index, changes in (
            (4, {'physical_replica_count': 2}),
            (4, {'closure_class': 129}),
            (4, {'section_version': 2}),
            (4, {'section_id': 19}),
            (6, {'physical_replica_count': 5}),
            (6, {'game_ordinal': 1}),
            (6, {'check_id': 2}),
            (6, {'copy_count': 2}),
            (6, {'copy_count': True}),
            (6, {'logical_payload_length': 16385}),
            (1, {'dependencies': (16, 17)}),
            (2, {'dependencies': source.entries[2].dependencies[:-1]}),
        ):
            rows = list(source.entries)
            rows[index] = replace(rows[index], **changes)
            with self.subTest(index=index, changes=changes):
                with self.assertRaises(base.BootstrapReject):
                    revised.encode_inventory(replace(source, entries=tuple(rows)))

    def test_wire_bounds_flags_widths_and_trailing_reject(self):
        raw = revised.encode_inventory(inventory_fixture())
        for cut in (0, 1, 7, 8, 27, len(raw) - 1):
            with self.assertRaises(base.BootstrapReject):
                revised.decode_inventory(raw[:cut])
        for offset, value in ((0, 1), (8, 1), (19, 0x8a), (18, 2), (24, 255)):
            mutated = bytearray(raw)
            mutated[offset] = value
            with self.subTest(offset=offset):
                with self.assertRaises(base.BootstrapReject):
                    revised.decode_inventory(bytes(mutated))
        for malformed in (raw + b'\0', raw + bytes(16385), bytearray(raw)):
            with self.assertRaises(base.BootstrapReject):
                revised.decode_inventory(malformed)

    def test_untrusted_logical_input_rejects_before_processing(self):
        source = inventory_fixture()
        for rows in ((), (None,) * 3, (source.entries[0],) * 4097,
                     (replace(source.entries[0], section_id=[]), *source.entries[1:])):
            with self.assertRaises(base.BootstrapReject):
                revised.encode_inventory(replace(source, entries=rows))


class RevisedContentAssembly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from golden_board import capacity, body_codec_v1
        from golden_board.m2_slice_v1 import compile_slice_v1
        root = Path(__file__).resolve().parents[2]
        paths = ('studies/m2/slice-v1.json', 'studies/m2/slice-v0.json',
                 'conformance/content-v0.json', 'conformance/chess-v0.json',
                 'reports/game-set-v0.bin', 'spec/content-v0.md',
                 'spec/constants-v0.toml', 'spec/curriculum-v0.toml')
        cls.compiled = compile_slice_v1(*((root / path).read_bytes() for path in paths))
        frames = capacity._frames(cls.compiled.content_bytes, 'all')
        envelopes = {}
        ordinals = {}
        for row in cls.compiled.atomic_assignments:
            raw = b''.join(frames[rid] for rid in row.record_ids)
            version, wire = body_codec_v1.encode_body(raw)
            envelopes[row.section_id] = base.SectionEnvelope(
                row.section_id, 3, version, 128 if row.closure == 'm2_required' else 129,
                1, (), wire)
            ordinals[row.section_id] = row.game_ordinal
        for row in cls.compiled.tier_roots:
            stream = cls.compiled.required_content_bytes if row.section_id == 2 else cls.compiled.content_bytes
            ids = revised.REQUIRED_BODIES if row.section_id == 2 else revised.ALL_BODIES
            wire = base.encode_tier_frame(base.TierFrame(row.section_id - 2, ids,
                len(stream), int.from_bytes(stream[2:4], 'big'),
                capacity._frames(stream, 'tier')[row.record_id]))
            envelopes[row.section_id] = base.SectionEnvelope(row.section_id, 2, 0, 128, 1, ids, wire)
        rows = [base.InventoryEntry(1, 1, 2, 128, 1, 1, (), 1952, physical_replica_count=5)]
        rows.extend(base.InventoryEntry(sid, env.section_type, env.section_version,
            env.closure_class, 1, 1, env.dependencies, len(env.payload), ordinals.get(sid),
            5 if sid in revised.SPINE else 1) for sid, env in sorted(envelopes.items()))
        inv = revised.encode_inventory(base.Inventory(tuple(rows), 2))
        envelopes[1] = base.SectionEnvelope(1, 1, 2, 128, 1, (), inv)
        cls.sections = {sid: base.encode_section_envelope(env) for sid, env in envelopes.items()}

    def test_encoded_sections_recover_exact_logical_streams(self):
        result = revised.recover_content(self.sections)
        self.assertEqual(result.required_bytes, self.compiled.required_content_bytes)
        self.assertEqual(result.all_bytes, self.compiled.content_bytes)
        self.assertEqual(result.checked_section_ids, tuple(sorted(self.sections)))
        self.assertEqual(result.rejected_section_ids, ())

    def test_required_failure_withholds_both_and_optional_failure_preserves_required(self):
        for sid in (2, 3):
            sections = dict(self.sections)
            env = base.decode_section_envelope(sections[sid])
            payload = env.payload[:-4] + b'\0\0' + env.payload[-2:]
            sections[sid] = base.encode_section_envelope(replace(env, payload=payload))
            result = revised.recover_content(sections)
            self.assertIsNone(result.all_bytes)
            if sid == 2:
                self.assertIsNone(result.required_bytes)
            else:
                self.assertEqual(result.required_bytes, self.compiled.required_content_bytes)
        sections = dict(self.sections)
        del sections[210]
        result = revised.recover_content(sections)
        self.assertEqual(result.required_bytes, self.compiled.required_content_bytes)
        self.assertIsNone(result.all_bytes)

    def test_checked_but_malformed_codec_and_stale_checks_do_not_expose_content(self):
        sections = dict(self.sections)
        env = base.decode_section_envelope(sections[16])
        sections[16] = base.encode_section_envelope(replace(env, payload=b'\2' + env.payload[1:]))
        result = revised.recover_content(sections)
        self.assertIsNone(result.required_bytes)
        self.assertIsNone(result.all_bytes)
        self.assertIn(16, result.checked_section_ids)  # Section check alone isn't content acceptance.
        sections[16] = self.sections[16][:-1] + bytes((self.sections[16][-1] ^ 1,))
        result = revised.recover_content(sections)
        self.assertIn(16, result.rejected_section_ids)
        self.assertIsNone(result.required_bytes)
        with self.assertRaises(base.BootstrapReject):
            revised.recover_content({100: self.sections[100]})


if __name__ == '__main__':
    unittest.main()
