"""Direct checks for the reviewed M2 slice-v0 compiler."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from golden_board import canonical_manifest
from golden_board import constants as C
from golden_board import content
from golden_board import m2_slice


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> bytes:
    return (ROOT / relative).read_bytes()


INPUTS = (
    _read("studies/m2/slice-v0.json"),
    _read("conformance/content-v0.json"),
    _read("conformance/chess-v0.json"),
    _read("reports/game-set-v0.bin"),
    _read("spec/content-v0.md"),
    _read("spec/constants-v0.toml"),
    _read("spec/curriculum-v0.toml"),
)


def _compile(*, manifest: bytes | None = None, game_set: bytes | None = None):
    values = list(INPUTS)
    if manifest is not None:
        values[0] = manifest
    if game_set is not None:
        values[3] = game_set
    return m2_slice.compile_slice_v0(*values)


def _mutated_manifest(mutator) -> bytes:
    value = canonical_manifest.validate_canonical_manifest(INPUTS[0])
    mutator(value)
    return canonical_manifest.serialize_manifest(value)


def _independent_game_frames(data: bytes) -> tuple[bytes, ...]:
    count = int.from_bytes(data[:2], "big")
    offset = 2
    values = []
    for _ in range(count):
        start = offset
        plies = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2 + 2 * plies + 1
        values.append(data[start:offset])
    if offset != len(data):
        raise AssertionError("test-side game framing did not consume input")
    return tuple(values)


class M2SliceCompilation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compiled = _compile()

    def test_exact_stream_and_public_round_trip(self) -> None:
        compiled = self.compiled
        self.assertEqual(len(compiled.required_projection.records), 29)
        self.assertEqual(compiled.required_projection.root_record_id, 29)
        self.assertEqual(len(compiled.required_content_bytes), 575)
        self.assertEqual(
            compiled.required_content_sha256,
            "99c783060adb543ef1621b4e17f57772bd88c9d37cb249981aed5f9a4962d7dc",
        )
        self.assertEqual(
            content.projection_view(
                content.stream_validation(compiled.required_content_bytes)
            ),
            compiled.required_projection,
        )
        self.assertEqual(len(compiled.projection.records), 182)
        self.assertEqual(compiled.projection.root_record_id, 182)
        self.assertEqual(
            tuple(record.record_id for record in compiled.projection.records),
            tuple(range(1, 183)),
        )
        self.assertEqual(len(compiled.content_bytes), 13_644)
        self.assertEqual(
            compiled.content_sha256,
            "de7e22f0aa4316d9f32d9435287dd19bd6c04519aae1dc9bd816613f26929671",
        )
        self.assertEqual(
            content.encode_content_v0(
                content.authoring_from_validated(compiled.projection)
            ),
            compiled.content_bytes,
        )
        reparsed = content.projection_view(
            content.stream_validation(compiled.content_bytes)
        )
        self.assertEqual(reparsed, compiled.projection)

    def test_all_games_are_exact_distinct_atomic_assignments(self) -> None:
        compiled = self.compiled
        independent = _independent_game_frames(INPUTS[3])
        self.assertEqual(compiled.game_payloads, independent)
        self.assertEqual(len(independent), 64)
        self.assertEqual(sum(map(len, independent)), len(INPUTS[3]) - 2)
        self.assertEqual(len(set(independent)), 64)

        game_assignments = tuple(
            assignment
            for assignment in compiled.atomic_assignments
            if assignment.game_ordinal is not None
        )
        self.assertEqual(len(game_assignments), 64)
        self.assertEqual(
            tuple(item.section_id for item in game_assignments),
            tuple(range(100, 164)),
        )
        self.assertEqual(
            tuple(item.game_ordinal for item in game_assignments), tuple(range(64))
        )
        self.assertEqual(
            len({item.section_id for item in compiled.atomic_assignments}), 77
        )
        self.assertEqual(
            tuple(item.section_id for item in compiled.atomic_assignments),
            (16, 17, *range(100, 164), *range(200, 211)),
        )
        self.assertEqual(
            tuple(
                record_id
                for assignment in compiled.atomic_assignments
                for record_id in assignment.record_ids
            ),
            tuple(range(1, 182)),
        )
        self.assertEqual(
            tuple(
                (root.section_id, root.closure, root.record_id)
                for root in compiled.tier_roots
            ),
            ((2, "m2_required", 29), (3, "m2_all", 182)),
        )

        records = {
            record.record_id: record.payload for record in compiled.projection.records
        }
        opaque_ids = []
        for ordinal, game in enumerate(independent):
            binding_id = 30 + 2 * ordinal
            opaque_id = binding_id + 1
            binding = records[binding_id]
            opaque = records[opaque_id]
            self.assertIs(type(binding), content.ContentSemanticBinding)
            self.assertEqual(
                (
                    binding.binding_class,
                    binding.namespace_id,
                    binding.semantic_code,
                    binding.argument,
                    binding.auxiliary,
                ),
                (C.BINDING_DATA, 2, ordinal + 1, 29, len(game)),
            )
            self.assertIs(type(opaque), content.ContentOpaqueData)
            self.assertEqual(opaque.data_binding_ref, binding_id)
            self.assertEqual(bytes(opaque.data), game)
            opaque_ids.append(opaque_id)
        aggregate = records[179]
        self.assertIs(type(aggregate), content.ContentTuple)
        self.assertEqual(aggregate.field_values[0].record_refs[:64], tuple(opaque_ids))
        self.assertEqual(
            aggregate.field_values[0].record_refs[64:], tuple(range(159, 178, 2))
        )

    def test_external_answer_is_neutral_and_leads_to_original_entry(self) -> None:
        projection = content.stream_validation(self.compiled.content_bytes)
        state = content.new_run(projection)
        self.assertEqual(content.run_state_view(state).current_node_id, 181)
        state, result = content.step(projection, state, bytes.fromhex("01000002"))
        self.assertEqual(result, C.INTERACTION_SELECTED)
        state, result = content.step(projection, state, bytes.fromhex("03000000"))
        view = content.run_state_view(state)
        self.assertEqual(result, C.INTERACTION_COMMITTED)
        self.assertEqual(view.committed_response.hex(), "0100010002")
        self.assertEqual(view.outcome, C.OUTCOME_NEUTRAL)
        self.assertEqual(view.feedback_ref, 180)
        self.assertEqual(view.next_node_ref, 26)
        state = content.advance_committed(projection, state)
        self.assertEqual(content.run_state_view(state).current_node_id, 26)

    def test_selected_chess_fixtures_are_serialized_as_wire_bytes(self) -> None:
        compiled = self.compiled
        self.assertEqual(
            tuple(map(len, compiled.fixture_payloads)),
            (90, 94, 90, 96, 96, 96, 96, 29, 23, 31),
        )
        fixture = canonical_manifest.validate_canonical_manifest(INPUTS[2])
        cases = {row["name"]: row for row in fixture["cases"]}
        first = compiled.fixture_payloads[0]
        self.assertEqual(first[:2], b"\x00\x01")
        prior_length = int.from_bytes(first[2:4], "big")
        prior = first[4 : 4 + prior_length]
        offset = 4 + prior_length
        subject_length = int.from_bytes(first[offset : offset + 2], "big")
        subject = first[offset + 2 : offset + 2 + subject_length]
        expected_length_at = offset + 2 + subject_length
        expected_length = int.from_bytes(
            first[expected_length_at : expected_length_at + 2], "big"
        )
        expected = first[expected_length_at + 2 :]
        case = cases["castling-positive-first-kingside"]
        self.assertEqual(prior, bytes.fromhex(case["input"]["moves_hex"]))
        self.assertEqual(subject, bytes.fromhex(case["input"]["move_hex"]))
        self.assertEqual(expected_length, len(expected))
        self.assertEqual(expected[0], 1)
        self.assertEqual(
            expected[1:], bytes.fromhex(case["expected"]["success"]["position_hex"])
        )
        self.assertEqual(compiled.fixture_payloads[7][-3:], b"\x04\x007")
        self.assertEqual(compiled.fixture_payloads[8][-13], 5)
        for case_name, payload in zip(
            compiled.chess_fixture_cases, compiled.fixture_payloads, strict=True
        ):
            self.assertNotIn(case_name.encode("ascii"), payload)

        records = {
            record.record_id: record.payload for record in compiled.projection.records
        }
        for ordinal, payload in enumerate(compiled.fixture_payloads):
            binding_id = 158 + 2 * ordinal
            binding = records[binding_id]
            opaque = records[binding_id + 1]
            self.assertEqual(
                (
                    binding.binding_class,
                    binding.namespace_id,
                    binding.semantic_code,
                    binding.argument,
                    binding.auxiliary,
                ),
                (C.BINDING_DATA, 3, ordinal + 1, 29, len(payload)),
            )
            self.assertEqual(bytes(opaque.data), payload)

    def test_asymmetry_and_special_fixture_bindings_are_concrete(self) -> None:
        values = canonical_manifest.validate_canonical_manifest(INPUTS[0])
        probe = values["asymmetry_probe"]
        cells = tuple(probe["cells"])
        transpose = tuple(
            cells[row * probe["columns"] + column]
            for column in range(probe["columns"])
            for row in range(probe["rows"])
        )
        reflection = tuple(
            cells[row * probe["columns"] + probe["columns"] - 1 - column]
            for row in range(probe["rows"])
            for column in range(probe["columns"])
        )
        self.assertNotEqual(transpose, cells)
        self.assertNotEqual(reflection, cells)
        self.assertTrue(any(value ^ 0xFF > 5 for value in cells))
        self.assertTrue(any(int(f"{value:08b}"[::-1], 2) > 5 for value in cells))

        self.assertEqual(
            self.compiled.chess_fixture_cases,
            (
                "castling-positive-first-kingside",
                "castling-positive-first-queenside",
                "en-passant-legal-capture",
                "promotion-quiet-queen",
                "promotion-quiet-rook",
                "promotion-quiet-bishop",
                "promotion-quiet-knight",
                "geometry-illegal-self-check",
                "en-passant-nominal-without-capturer",
                "en-passant-effective-key-retained",
            ),
        )

    def test_capacity_prototypes_cover_all_fourteen_kinds(self) -> None:
        values = canonical_manifest.validate_canonical_manifest(INPUTS[0])
        rows = values["capacity_prototypes"]
        self.assertEqual([row["kind"] for row in rows], list(range(1, 15)))
        self.assertEqual({row["role"] for row in rows}, {"nonsemantic-capacity-only"})
        self.assertEqual(len({row["prototype_id"] for row in rows}), 14)
        self.assertEqual(
            tuple(
                (
                    item.kind,
                    item.prototype_id,
                    item.source_record_id,
                    item.frame_length,
                )
                for item in self.compiled.capacity_prototypes
            ),
            tuple(
                (
                    row["kind"],
                    row["prototype_id"],
                    row["source_record_id"],
                    length,
                )
                for row, length in zip(
                    rows,
                    (15, 14, 14, 20, 34, 19, 54, 18, 11, 14, 14, 28, 58, 12),
                    strict=True,
                )
            ),
        )

    def test_result_and_errors_are_immutable(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            self.compiled.content_bytes = b""  # type: ignore[misc]
        error = m2_slice.SliceError("bad_value", "manifest")
        with self.assertRaises(AttributeError):
            error._reason = "changed"


class M2SliceRejections(unittest.TestCase):
    def assert_slice_error(self, manifest: bytes, reason: str, path: str) -> None:
        with self.assertRaises(m2_slice.SliceError) as caught:
            _compile(manifest=manifest)
        self.assertEqual(
            (caught.exception.reason, caught.exception.path), (reason, path)
        )

    def test_unknown_root_field_is_closed(self) -> None:
        self.assert_slice_error(
            _mutated_manifest(lambda value: value.__setitem__("extra", 0)),
            "closed_shape",
            "manifest",
        )

    def test_game_assignment_cannot_alias_a_section(self) -> None:
        def mutate(value) -> None:
            value["game_record_plan"]["assignments"][1]["section_id"] = 100

        self.assert_slice_error(
            _mutated_manifest(mutate),
            "bad_value",
            "game_record_plan.assignments[1]",
        )

    def test_game_record_ids_and_ordinals_are_not_inferred(self) -> None:
        def mutate(value) -> None:
            value["game_record_plan"]["assignments"][7]["opaque_record_id"] = 99

        self.assert_slice_error(
            _mutated_manifest(mutate),
            "bad_value",
            "game_record_plan.assignments[7]",
        )

    def test_game_set_identity_is_recomputed(self) -> None:
        def mutate(value) -> None:
            value["inputs"]["game_set"]["identity"] = "0" * 64

        self.assert_slice_error(
            _mutated_manifest(mutate), "identity_mismatch", "inputs.game_set"
        )

    def test_mutated_game_bytes_fail_before_content_authoring(self) -> None:
        changed = bytearray(INPUTS[3])
        changed[-1] ^= 1
        with self.assertRaises(m2_slice.SliceError) as caught:
            _compile(game_set=bytes(changed))
        self.assertEqual(
            (caught.exception.reason, caught.exception.path),
            ("hash_mismatch", "inputs.game_set"),
        )

    def test_required_chess_case_cannot_be_renamed(self) -> None:
        def mutate(value) -> None:
            value["chess_fixture_cases"]["assignments"][2]["case_name"] = "not-a-case"

        self.assert_slice_error(
            _mutated_manifest(mutate),
            "bad_reference",
            "chess_fixture_cases.assignments[2]",
        )

    def test_support_assignment_cannot_hide_or_duplicate_a_record(self) -> None:
        def mutate(value) -> None:
            value["section_plan"]["support_assignments"][0]["record_ids"][-1] = 27

        self.assert_slice_error(
            _mutated_manifest(mutate),
            "bad_value",
            "section_plan.support_assignments[0]",
        )

    def test_noncanonical_manifest_rejects(self) -> None:
        self.assert_slice_error(INPUTS[0][:-1] + b" \n", "invalid_manifest", "inputs")


if __name__ == "__main__":
    unittest.main()
