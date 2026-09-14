"""Direct checks for the candidate-neutral M2 generic runner."""

from __future__ import annotations

import ast
from dataclasses import fields, replace
from pathlib import Path
import unittest

from golden_board import constants as C
from golden_board import content
from golden_board import m2_runner
from golden_board import m2_slice


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> bytes:
    return (ROOT / relative).read_bytes()


SLICE_INPUTS = (
    _read("studies/m2/slice-v0.json"),
    _read("conformance/content-v0.json"),
    _read("conformance/chess-v0.json"),
    _read("reports/game-set-v0.bin"),
    _read("spec/content-v0.md"),
    _read("spec/constants-v0.toml"),
    _read("spec/curriculum-v0.toml"),
)


def _all_stream() -> bytes:
    return m2_slice.compile_slice_v0(*SLICE_INPUTS).content_bytes


def _labels(value: object):
    if isinstance(value, tuple):
        for item in value:
            yield from _labels(item)
        return
    if hasattr(value, "__dataclass_fields__"):
        for field in fields(value):
            if field.name in {"text", "label", "name", "limitation"}:
                yield getattr(value, field.name)
            yield from _labels(getattr(value, field.name))


def _generic_base() -> content.ContentAuthoringProjection:
    import json

    fixture = json.loads(_read("conformance/content-v0.json"))
    raw = bytes.fromhex(fixture["bases"][0]["stream_hex"])
    accepted = content.stream_validation(raw)
    return content.authoring_from_validated(content.projection_view(accepted))


def _replace_records(
    authoring: content.ContentAuthoringProjection, replacements: dict[int, object]
) -> bytes:
    records = tuple(
        content.ContentRecordView(
            record.record_id,
            replacements.get(record.record_id, record.payload),
        )
        for record in authoring.records
    )
    return content.encode_content_v0(
        content.ContentAuthoringProjection(authoring.version, records)
    )


class M2RunnerPath(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stream = _all_stream()
        cls.ordinary = m2_runner.run_m2_semantic_path(
            cls.stream, label_suppressed=False
        )
        cls.suppressed = m2_runner.run_m2_semantic_path(
            cls.stream, label_suppressed=True
        )

    def test_exact_stream_and_full_path_are_bound(self) -> None:
        self.assertEqual(len(self.stream), 13_644)
        self.assertEqual(
            self.ordinary.content_stream_sha256,
            "de7e22f0aa4316d9f32d9435287dd19bd6c04519aae1dc9bd816613f26929671",
        )
        self.assertEqual(
            tuple((event.node_id, event.action.hex(), event.result) for event in self.ordinary.events),
            (
                (181, "01000002", C.INTERACTION_SELECTED),
                (181, "03000000", C.INTERACTION_COMMITTED),
                (26, "01000001", C.INTERACTION_SELECTED),
                (26, "03000000", C.INTERACTION_COMMITTED),
                (27, "01000003", C.INTERACTION_SELECTED),
                (27, "01000001", C.INTERACTION_SELECTED),
                (27, "03000000", C.INTERACTION_COMMITTED),
                (28, "01000003", C.INTERACTION_SELECTED),
                (28, "01000001", C.INTERACTION_SELECTED),
                (28, "03000000", C.INTERACTION_COMMITTED),
            ),
        )
        self.assertEqual(
            tuple(
                (
                    item.node_id,
                    item.committed_response.hex(),
                    item.outcome,
                    item.feedback_ref,
                    item.next_node_ref,
                )
                for item in self.ordinary.commitments
            ),
            (
                (181, "0100010002", C.OUTCOME_NEUTRAL, 180, 26),
                (26, "0100010001", C.OUTCOME_ACCEPTED, 21, 27),
                (27, "02000200010003", C.OUTCOME_NEUTRAL, 20, 28),
                (28, "03000200030001", C.OUTCOME_NEUTRAL, 24, 0),
            ),
        )
        self.assertEqual(len(self.ordinary.checkpoints), 14)
        final = self.ordinary.checkpoints[-1]
        self.assertEqual((final.global_remaining, final.local_remaining), (0, 0))
        self.assertEqual(final.available_actions, ())
        self.assertFalse(final.can_advance)

    def test_evaluator_predicates_and_committed_responses_are_exact(self) -> None:
        absent = m2_runner.EvaluatorPredicate(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        bound = m2_runner.EvaluatorPredicate(19, 18, 2, 1, 2, 16, 7, 17, 16, 10)
        self.assertEqual(self.ordinary.commitments[0].node_predicate, absent)
        self.assertEqual(self.ordinary.commitments[0].feedback_predicate, absent)
        self.assertEqual(self.ordinary.commitments[1].node_predicate, bound)
        self.assertEqual(self.ordinary.commitments[1].feedback_predicate, bound)
        self.assertEqual(self.ordinary.commitments[2].node_predicate, absent)
        self.assertEqual(self.ordinary.commitments[3].node_predicate, absent)
        self.assertTrue(
            all(item.committed_response for item in self.ordinary.commitments)
        )

    def test_label_suppression_is_semantically_byte_identical(self) -> None:
        self.assertEqual(self.ordinary, self.suppressed)
        ordinary_bytes = m2_runner.semantic_path_bytes(self.ordinary)
        suppressed_bytes = m2_runner.semantic_path_bytes(self.suppressed)
        self.assertEqual(ordinary_bytes, suppressed_bytes)
        self.assertEqual(
            m2_runner.semantic_path_sha256(self.ordinary),
            m2_runner.semantic_path_sha256(self.suppressed),
        )
        self.assertEqual(
            m2_runner.semantic_path_sha256(self.ordinary),
            m2_runner.M2_SEMANTIC_PATH_SHA256,
        )
        self.assertEqual(len(ordinary_bytes), 9_883)
        self.assertIn(self.ordinary.content_stream_sha256.encode("ascii"), ordinary_bytes)

    def test_frames_remove_text_without_substitute_identifiers(self) -> None:
        ordinary_runner = m2_runner.m2_runner(self.stream, label_suppressed=False)
        suppressed_runner = m2_runner.m2_runner(self.stream, label_suppressed=True)
        ordinary = ordinary_runner.frame()
        suppressed = suppressed_runner.frame()
        ordinary_labels = tuple(value for value in _labels(ordinary) if value is not None)
        suppressed_labels = tuple(value for value in _labels(suppressed) if value is not None)
        self.assertIn(b"Surface", ordinary_labels)
        self.assertEqual(suppressed_labels, ())
        self.assertEqual(ordinary.available_actions, suppressed.available_actions)
        self.assertEqual(ordinary.current_node_id, suppressed.current_node_id)
        self.assertEqual(ordinary.events, suppressed.events)

        for runner in (ordinary_runner, suppressed_runner):
            runner.perform(bytes.fromhex("01000002"))
            runner.perform(bytes.fromhex("03000000"))
        ordinary_feedback = ordinary_runner.frame().feedback
        suppressed_feedback = suppressed_runner.frame().feedback
        self.assertIsNotNone(ordinary_feedback)
        self.assertIsNotNone(suppressed_feedback)
        aggregate = next(
            record for record in suppressed_feedback.records if record.record_id == 179
        )
        first_opaque = next(
            record for record in suppressed_feedback.records if record.record_id == 31
        )
        self.assertEqual(len(aggregate.fields[0].record_refs), 74)
        self.assertEqual(
            bytes(first_opaque.opaque_data),
            m2_slice.compile_slice_v0(*SLICE_INPUTS).game_payloads[0],
        )
        self.assertEqual(
            tuple(value for value in _labels(suppressed_feedback) if value is not None),
            (),
        )

    def test_m2_identity_and_host_action_boundaries_fail_closed(self) -> None:
        with self.assertRaises(m2_runner.RunnerError) as wrong:
            m2_runner.m2_runner(self.stream[:-1], label_suppressed=True)
        self.assertEqual(wrong.exception.reason, "m2_content_stream_identity")
        with self.assertRaises(TypeError):
            m2_runner.m2_runner(bytearray(self.stream), label_suppressed=True)
        runner = m2_runner.m2_runner(self.stream, label_suppressed=True)
        before = runner.frame()
        with self.assertRaises(m2_runner.RunnerError) as unavailable:
            runner.perform(bytes.fromhex("01000004"))
        self.assertEqual(unavailable.exception.reason, "action_not_available")
        self.assertEqual(runner.frame(), before)
        with self.assertRaises(m2_runner.RunnerError):
            runner.advance()


class GenericRunnerCanaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = _generic_base()

    def test_unequal_rectangles_enum_mask_passive_reset_and_exhaustion(self) -> None:
        for rows, columns in ((5, 7), (7, 5)):
            cells = tuple(index % 6 for index in range(rows * columns))
            raw = _replace_records(
                self.base,
                {12: content.ContentMatrix(6, rows, columns, cells)},
            )
            runner = m2_runner.GenericRunner(raw, label_suppressed=True)
            frame = runner.frame()
            matrix = next(
                record
                for record in frame.presentation.records
                if record.record_id == 12
            )
            self.assertEqual((matrix.rows, matrix.columns, matrix.atoms), (rows, columns, cells))
            self.assertEqual(matrix.atom_schema.atom_class, C.ATOM_UNSIGNED)
            self.assertIsNotNone(frame.passive)
            self.assertEqual(frame.passive.actions, (bytes.fromhex("03000000"),))
            runner.perform(bytes.fromhex("02000000"))
            self.assertEqual(runner.frame().events[-1].result, C.INTERACTION_RESET)
            runner.perform(bytes.fromhex("02000000"))
            exhausted = runner.frame()
            self.assertEqual(exhausted.phase, C.PHASE_EXHAUSTED)
            self.assertEqual(exhausted.available_actions, ())

        initial = m2_runner.GenericRunner(
            _replace_records(
                self.base,
                {
                    1: content.ContentText("not a domain label"),
                    2: content.ContentText("field alpha"),
                    3: content.ContentText("field beta"),
                    4: content.ContentText("field gamma"),
                    5: content.ContentText("limit"),
                    6: content.ContentAtomSchema(
                        C.ATOM_UNSIGNED, 1, (), 0, 255, None
                    ),
                    17: content.ContentOpaqueData(16, (251,)),
                },
            ),
            label_suppressed=True,
        ).frame()
        tuple_record = next(
            record for record in initial.presentation.records if record.record_id == 14
        )
        enum_record = next(
            record for record in initial.presentation.records if record.record_id == 10
        )
        mask_record = next(
            record for record in initial.presentation.records if record.record_id == 11
        )
        self.assertEqual(enum_record.atom_schema.atom_class, C.ATOM_ENUM)
        self.assertEqual(mask_record.atom_schema.atom_class, C.ATOM_MASK)
        self.assertEqual(len(tuple_record.fields), 3)
        self.assertEqual(tuple(_labels(initial)), (None,) * len(tuple(_labels(initial))))

    def test_suppressed_frames_ignore_utf8_identity_and_font_rendering(self) -> None:
        first = _replace_records(
            self.base,
            {
                1: content.ContentText("alpha"),
                2: content.ContentText("beta"),
                3: content.ContentText("gamma"),
                4: content.ContentText("delta"),
                5: content.ContentText("epsilon"),
            },
        )
        second = _replace_records(
            self.base,
            {
                1: content.ContentText("λ"),
                2: content.ContentText("漢"),
                3: content.ContentText("e\u0301"),
                4: content.ContentText("🙂"),
                5: content.ContentText("Ж"),
            },
        )
        left = m2_runner.GenericRunner(first, label_suppressed=True)
        right = m2_runner.GenericRunner(second, label_suppressed=True)
        self.assertEqual(left.frame(), right.frame())
        for action in (bytes.fromhex("01000001"), bytes.fromhex("03000000")):
            self.assertEqual(left.perform(action), right.perform(action))
            self.assertEqual(left.frame(), right.frame())

    def test_module_dependency_firewall(self) -> None:
        path = ROOT / "python/golden_board/m2_runner.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        relative_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
                if node.level:
                    relative_names.update(alias.name for alias in node.names)
        self.assertEqual(imported, {"", "__future__", "dataclasses", "hashlib"})
        self.assertEqual(relative_names, {"canonical_manifest", "constants", "content"})
        lowered = source.lower()
        for forbidden in (
            "golden_board.chess",
            "gb_chess",
            "m2_slice",
            "bootstrap",
            "transport",
            "legal_move",
            "answer_map",
        ):
            self.assertNotIn(forbidden, lowered)
        rust_manifest = _read("crates/gb-slice/Cargo.toml").decode("ascii")
        self.assertNotIn("gb-chess", rust_manifest)


if __name__ == "__main__":
    unittest.main()
