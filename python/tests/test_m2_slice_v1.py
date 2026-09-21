"""New required teaching, historical anthology, and independent compilation."""
from dataclasses import replace
from pathlib import Path
import unittest

from golden_board import canonical_manifest as manifest, content, curriculum, m2_runner
from golden_board.m2_capacity_v1 import derive_capacity_inputs_v1
from golden_board.m2_slice import compile_slice_v0
from golden_board.m2_slice_v1 import compile_slice_v1
from tools.m2.learner_compile import compile_pages, slice_declaration, _compose
from tools.m2.learner_content import build_cases

ROOT = Path(__file__).resolve().parents[2]


def inputs():
    return tuple((ROOT / path).read_bytes() for path in (
        'studies/m2/slice-v0.json', 'conformance/content-v0.json',
        'conformance/chess-v0.json', 'reports/game-set-v0.bin',
        'spec/content-v0.md', 'spec/constants-v0.toml', 'spec/curriculum-v0.toml'))


class ParticipantSlice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = build_cases(ROOT)
        cls.raw, cls.owner = compile_pages(cls.pages)
        cls.sources = inputs()
        cls.declaration = slice_declaration(cls.raw, cls.sources[0])
        cls.compiled = compile_slice_v1(cls.declaration, *cls.sources)

    def test_required_teaching_is_complete_and_anthology_is_retained(self):
        self.assertEqual((ROOT / 'studies/m2/slice-v1.json').read_bytes(), self.declaration)
        self.assertEqual(self.compiled.required_content_bytes, self.raw)
        self.assertEqual(len(self.compiled.game_payloads), 64)
        self.assertEqual(len(self.compiled.fixture_payloads), 10)
        self.assertEqual(len(self.owner['pages']), len(self.pages))
        by_id = {r.record_id: r for r in self.compiled.projection.records}
        for record in self.compiled.required_projection.records[:-1]:
            self.assertEqual(by_id[record.record_id], record)
        assigned = [i for a in self.compiled.atomic_assignments for i in a.record_ids]
        self.assertEqual(assigned, list(range(1, len(by_id))))
        required = [a for a in self.compiled.atomic_assignments if a.closure == 'm2_required']
        self.assertEqual([i for a in required for i in a.record_ids],
                         list(range(1, self.owner['root_id'])))

    def test_mechanics_example_and_external_final_are_in_the_bytes(self):
        records = {r.record_id: r.payload for r in self.compiled.required_projection.records}
        first = records[self.owner['pages'][0]['node_id']]
        self.assertEqual([a.hex() for a in records[first.passive_trace_ref].actions],
                         ['01000001','02000000','01000002','03000000'])
        for page in self.owner['pages']:
            if page['phase'] == 'heldout':
                node = records[page['node_id']]
                self.assertEqual((node.answer_mode, node.predicate_result_ref,
                                  node.passive_trace_ref, node.cases), (2, 0, 0, ()))

    def test_library_inspection_is_neutral_and_reveals_the_same_payloads_as_its_example(self):
        runner = m2_runner.GenericRunner(self.compiled.content_bytes, label_suppressed=True)
        initial = runner.frame()
        for action in (bytes.fromhex('01000001'), bytes.fromhex('03000000')):
            runner.perform(action)
        result = runner.frame()
        self.assertEqual(result.outcome, 3)
        self.assertEqual(result.feedback, initial.passive.resulting_presentation)
        self.assertEqual(sum(record.kind == 9 for record in result.feedback.records), 74)
        runner.advance()
        self.assertEqual(runner.frame().current_node_id, self.owner['pages'][0]['node_id'])

    def test_compact_layout_preserves_every_selectable_cell(self):
        for page in self.pages:
            rows, columns, cells, regions, crops = _compose(page)
            self.assertLessEqual(columns, 36, page['id'])
            for region in regions:
                visible = tuple(cells[row*columns+column]
                    for row in range(region.row_start, region.row_end)
                    for column in range(region.column_start, region.column_end))
                self.assertEqual(visible, crops[region.region_id][2], page['id'])

    def test_closed_declaration_and_source_binding_fail_closed(self):
        original = manifest.validate_canonical_manifest(self.declaration)
        changed = dict(original, extra=0)
        with self.assertRaises(ValueError):
            compile_slice_v1(manifest.serialize_manifest(changed), *self.sources)
        changed = dict(original, legacy_declaration_sha256='0'*64)
        with self.assertRaises(ValueError):
            compile_slice_v1(manifest.serialize_manifest(changed), *self.sources)
        changed = manifest.validate_canonical_manifest(self.declaration)
        changed['lesson_records'][0]['payload']['atom_width'] = True
        with self.assertRaises(ValueError):
            compile_slice_v1(manifest.serialize_manifest(changed), *self.sources)

    def test_capacity_charges_real_teaching_and_preserves_separate_prototypes(self):
        old = compile_slice_v0(*self.sources)
        blueprint = curriculum.load_blueprint(self.sources[-1])
        value = derive_capacity_inputs_v1(self.compiled, old, blueprint)
        self.assertEqual(value.slice_semantic_sha256, self.compiled.content_sha256)
        self.assertEqual(sum(item.payload_length for item in value.real_content_sections),
                         len(self.compiled.content_bytes) - 4 - 12)
        self.assertGreater(sum(item.payload_length for item in value.real_content_sections
                               if item.closure == 'm2_required'), 40000)
        bad = replace(self.compiled, capacity_prototypes=self.compiled.capacity_prototypes[1:])
        with self.assertRaises(ValueError):
            derive_capacity_inputs_v1(bad, old, blueprint)


if __name__ == '__main__':
    unittest.main()
