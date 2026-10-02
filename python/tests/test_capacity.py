"""Direct checks for the candidate-neutral M2 capacity envelope."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import unittest

from golden_board import capacity, curriculum, m2_slice


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> bytes:
    return (ROOT / relative).read_bytes()


def _inputs() -> capacity.CapacityInputs:
    compiled = m2_slice.compile_slice_v0(
        _read("studies/m2/slice-v0.json"),
        _read("conformance/content-v0.json"),
        _read("conformance/chess-v0.json"),
        _read("reports/game-set-v0.bin"),
        _read("spec/content-v0.md"),
        _read("spec/constants-v0.toml"),
        _read("spec/curriculum-v0.toml"),
    )
    blueprint = curriculum.load_blueprint(_read("spec/curriculum-v0.toml"))
    return capacity.derive_capacity_inputs(compiled, blueprint)


# These sparse multiplicities exercise the P3 engine; profile-policy-v0 owns
# the later reviewed production multiplicities and its loader projection.
_TEST_BUNDLES = (
    ("grounded_rule", (1, 1, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 1, 0)),
    ("contrasting_worked", (1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 1, 1, 1, 0)),
    (
        "active_prediction_feedback",
        (1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 1, 1, 1, 0),
    ),
    ("distinct_held_out", (1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 1, 0, 1, 0)),
    ("passive_trace", (1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0)),
    ("heuristic", (2, 1, 1, 1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 0)),
    ("assessment_item", (1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 1, 0, 1, 0)),
    ("integrated_item", (1, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1, 0)),
)


def _policy(maximum: int = 191, probe: int = 191) -> capacity.CapacityPolicyInput:
    return capacity.CapacityPolicyInput(
        tuple(capacity.RoleBundlePolicy(*row) for row in _TEST_BUNDLES),
        maximum,
        probe,
        1,
        4,
        1,
    )


class CapacityFacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = _inputs()

    def test_exact_prototype_maxima_and_real_slice_charge(self) -> None:
        self.assertEqual(
            tuple(
                (item.kind, item.source_record_id, item.frame_length)
                for item in self.inputs.prototypes
            ),
            (
                (1, 1, 15),
                (2, 6, 14),
                (3, 9, 14),
                (4, 12, 20),
                (5, 13, 34),
                (6, 14, 19),
                (7, 15, 54),
                (8, 16, 18),
                (9, 17, 11),
                (10, 19, 14),
                (11, 20, 14),
                (12, 25, 28),
                (13, 26, 58),
                (14, 29, 12),
            ),
        )
        self.assertEqual(len(self.inputs.real_content_sections), 77)
        self.assertEqual(
            sum(item.payload_length for item in self.inputs.real_content_sections),
            13_628,
        )
        self.assertEqual(
            tuple(
                (
                    item.section_id,
                    item.logical_payload_length,
                    item.assembled_stream_length,
                    item.assembled_record_count,
                    len(item.body_section_ids),
                    item.root_record_frame_length,
                )
                for item in self.inputs.tier_frames
            ),
            ((2, 38, 575, 29, 1, 12), (3, 342, 13_644, 182, 77, 12)),
        )

    def test_curriculum_order_heuristics_and_core4_are_derived(self) -> None:
        self.assertEqual(len(self.inputs.concepts), 29)
        self.assertEqual(
            tuple(
                item.concept_id
                for item in self.inputs.concepts
                if item.heuristic_required
            ),
            ("c3.material_heuristic", "c3.practical_heuristic_set"),
        )
        self.assertEqual(
            (self.inputs.concepts[-1].concept_id, self.inputs.concepts[-1].tier),
            ("c4.record_literacy", "core4"),
        )
        self.assertEqual(len(self.inputs.families), 20)
        self.assertEqual(
            sum(item.delayed_required for item in self.inputs.families), 11
        )
        self.assertEqual(
            tuple((item.task_id, item.minimum_per_form) for item in self.inputs.integrated_tasks),
            (
                ("integrated_legal_sequence_pre", 1),
                ("integrated_legal_sequence_post", 1),
                ("integrated_record_reading_post", 1),
            ),
        )

    def test_fact_views_are_immutable(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            self.inputs.slice_semantic_sha256 = "0" * 64  # type: ignore[misc]
        error = capacity.CapacityError("bad", "path")
        with self.assertRaises(AttributeError):
            error._reason = "changed"


class CapacityDerivation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = _inputs()
        cls.envelope = capacity.derive_capacity_envelope(cls.inputs, _policy())

    def test_exact_bucket_order_subtotals_and_whole_generic_cycles(self) -> None:
        envelope = self.envelope
        self.assertEqual(len(envelope.buckets), 53)
        self.assertEqual(
            tuple(item.bucket_id for item in envelope.buckets[:3]),
            (
                "concept_minima/c0.scalar_equality",
                "concept_minima/c0.order_sequence",
                "concept_minima/c0.matrix_position",
            ),
        )
        self.assertEqual(
            envelope.buckets[-1].bucket_id, "generic_shared_support"
        )
        self.assertEqual(
            (
                envelope.concept_minima_bytes,
                envelope.assessment_bytes,
                envelope.integrated_bytes,
                envelope.generic_shared_support_bytes,
                envelope.authoring_payload_bytes,
            ),
            (26_921, 60_333, 2_412, 22_534, 112_200),
        )
        generic = envelope.buckets[-1]
        self.assertEqual(len(generic.slots), 950)
        self.assertEqual(max(item.role_ordinal for item in generic.slots) + 1, 38)
        self.assertEqual(len(generic.sections), 133)
        self.assertEqual(
            sum(item.payload_length for item in generic.sections),
            generic.payload_length,
        )

    def test_slots_are_atomic_next_fit_and_never_cross_bucket_sections(self) -> None:
        total_slots = 0
        for bucket in self.envelope.buckets:
            self.assertEqual(
                tuple(item.slot_ordinal for item in bucket.slots),
                tuple(range(len(bucket.slots))),
            )
            covered = []
            for section in bucket.sections:
                slots = bucket.slots[
                    section.first_slot_ordinal : section.first_slot_ordinal
                    + section.slot_count
                ]
                self.assertTrue(slots)
                self.assertEqual(
                    section.payload_length,
                    sum(item.frame_length for item in slots),
                )
                self.assertLessEqual(
                    section.payload_length,
                    self.envelope.maximum_content_body_payload,
                )
                covered.extend(item.slot_ordinal for item in slots)
            self.assertEqual(covered, list(range(len(bucket.slots))))
            total_slots += len(bucket.slots)
        self.assertEqual(total_slots, 4_626)
        self.assertEqual(
            self.envelope.slot_count_by_kind,
            (507, 505, 447, 447, 38, 85, 447, 505, 38, 474, 447, 172, 476, 38),
        )
        core4 = next(
            item
            for item in self.envelope.buckets
            if item.bucket_id == "concept_minima/c4.record_literacy"
        )
        self.assertEqual(core4.protection_class, "nonreplicated-core3-4")

    def test_reserve_probe_section_and_copy_charges_are_exact(self) -> None:
        real_content = sum(
            item.payload_length for item in self.inputs.real_content_sections
        ) + sum(item.logical_payload_length for item in self.inputs.tier_frames)
        reserve = capacity.reserve_requirement(
            real_content, self.envelope.authoring_payload_bytes
        )
        self.assertEqual(reserve, 6_643)
        parts = capacity.partition_probe_payload(reserve, 191)
        self.assertEqual((len(parts), parts[-1], sum(parts)), (35, 149, reserve))
        self.assertEqual(capacity.reserve_requirement(0, 0), 382)
        self.assertEqual(capacity.reserve_requirement(7_258, 0), 382)
        self.assertEqual(capacity.reserve_requirement(7_259, 0), 383)
        fixed = capacity.solve_reserve_fixed_point(
            real_content,
            self.envelope.authoring_payload_bytes,
            2_000,
            20,
            191,
        )
        self.assertEqual(
            (
                fixed.content_capacity_before_reserve,
                fixed.reserve_payload_length,
                len(fixed.reserve_section_payloads),
                fixed.reserve_section_payloads[-1],
                fixed.inventory_payload_length,
            ),
            (128_928, 6_786, 36, 101, 2_720),
        )
        self.assertGreaterEqual(
            fixed.reserve_payload_length,
            (
                fixed.content_capacity_before_reserve
                + fixed.reserve_payload_length
                + 19
            )
            // 20,
        )
        crc32 = capacity.section_charge(191, 2, 1, 2)
        self.assertEqual(
            (
                crc32.envelope_length,
                crc32.fragments_per_copy,
                crc32.common_blocks,
                crc32.common_block_bytes,
            ),
            (221, 2, 4, 764),
        )
        crc64 = capacity.section_charge(191, 2, 2, 3)
        self.assertEqual(
            (
                crc64.envelope_length,
                crc64.fragments_per_copy,
                crc64.common_blocks,
                crc64.common_block_bytes,
            ),
            (225, 2, 6, 1_146),
        )

    def test_load_partition_and_fill_stream_cover_every_residual_cell(self) -> None:
        fill = capacity.partition_residual_cells(1_000, 216 * 8)
        self.assertEqual(fill, capacity.LoadProbeFill(0, 0, 1_000))
        fill = capacity.partition_residual_cells(4_000, 216 * 8)
        self.assertEqual(fill, capacity.LoadProbeFill(2, 3_456, 544))
        self.assertEqual(
            capacity.probe_fill_bytes(self.inputs.slice_semantic_sha256, 40).hex(),
            "62aa2a4ed38b3ad8243e13ffe042273124c3970b892096c5fb05c251bea1775eb"
            "ef7a515d8d10c04",
        )

    def test_future_record_assignment_is_first_compatible_and_single_use(self) -> None:
        bucket = self.envelope.buckets[0]
        first = bucket.slots[0]
        second_same_kind = next(
            item
            for item in bucket.slots[1:]
            if item.kind == first.kind
        )
        assigned = capacity.assign_authored_records(
            self.envelope,
            (
                capacity.AuthoredRecordDemand(
                    1_000, bucket.bucket_id, first.kind, first.frame_length
                ),
                capacity.AuthoredRecordDemand(
                    1_001, bucket.bucket_id, first.kind, first.frame_length - 1
                ),
            ),
        )
        self.assertEqual(
            tuple(item.slot_ordinal for item in assigned),
            (first.slot_ordinal, second_same_kind.slot_ordinal),
        )

    def assert_capacity_error(self, function, reason: str, path: str) -> None:
        with self.assertRaises(capacity.CapacityError) as caught:
            function()
        self.assertEqual(
            (caught.exception.reason, caught.exception.path), (reason, path)
        )

    def test_policy_and_boundaries_fail_closed(self) -> None:
        reversed_policy = replace(
            _policy(), role_bundles=tuple(reversed(_policy().role_bundles))
        )
        self.assert_capacity_error(
            lambda: capacity.derive_capacity_envelope(self.inputs, reversed_policy),
            "role_bundle_order",
            "policy.role_bundles",
        )
        empty = replace(
            _policy().role_bundles[0], record_kind_multiplicities=(0,) * 14
        )
        empty_policy = replace(
            _policy(), role_bundles=(empty, *_policy().role_bundles[1:])
        )
        self.assert_capacity_error(
            lambda: capacity.derive_capacity_envelope(self.inputs, empty_policy),
            "empty_required_role",
            "policy.role_bundles[0]",
        )
        self.assert_capacity_error(
            lambda: capacity.derive_capacity_envelope(self.inputs, _policy(57)),
            "prototype_length",
            "inputs.prototypes",
        )
        for changed, path in (
            (
                replace(_policy(), generic_support_fraction_numerator=0),
                "policy.generic_support_fraction_numerator",
            ),
            (
                replace(_policy(), generic_support_fraction_denominator=0),
                "policy.generic_support_fraction_denominator",
            ),
            (
                replace(
                    _policy(),
                    generic_support_fraction_numerator=2,
                    generic_support_fraction_denominator=1,
                ),
                "policy.generic_support_fraction",
            ),
            (
                replace(_policy(), generic_support_minimum_cycles=0),
                "policy.generic_support_minimum_cycles",
            ),
        ):
            self.assert_capacity_error(
                lambda changed=changed: capacity.derive_capacity_envelope(
                    self.inputs, changed
                ),
                "bad_value",
                path,
            )
        self.assert_capacity_error(
            lambda: capacity.section_charge(1_048_576, 0, 1, 1),
            "section_envelope_limit",
            "section.envelope",
        )
        self.assert_capacity_error(
            lambda: capacity.partition_residual_cells(10, 0),
            "bad_value",
            "load_probe.protected_unit_cells",
        )

    def test_slot_exhaustion_oversize_and_duplicate_demands_reject(self) -> None:
        bucket = self.envelope.buckets[0]
        kind = bucket.slots[0].kind
        matching = [item for item in bucket.slots if item.kind == kind]
        demands = tuple(
            capacity.AuthoredRecordDemand(
                2_000 + index, bucket.bucket_id, kind, matching[0].frame_length
            )
            for index in range(len(matching) + 1)
        )
        self.assert_capacity_error(
            lambda: capacity.assign_authored_records(self.envelope, demands),
            "slot_exhausted",
            f"demands[{len(matching)}]",
        )
        self.assert_capacity_error(
            lambda: capacity.assign_authored_records(
                self.envelope,
                (
                    capacity.AuthoredRecordDemand(
                        3_000,
                        bucket.bucket_id,
                        kind,
                        matching[0].frame_length + 1,
                    ),
                ),
            ),
            "slot_exhausted",
            "demands[0]",
        )
        self.assert_capacity_error(
            lambda: capacity.assign_authored_records(
                self.envelope,
                (
                    capacity.AuthoredRecordDemand(
                        4_000, bucket.bucket_id, kind, matching[0].frame_length
                    ),
                    capacity.AuthoredRecordDemand(
                        4_000, bucket.bucket_id, kind, matching[0].frame_length
                    ),
                ),
            ),
            "duplicate_record",
            "demands[1].record_id",
        )


if __name__ == "__main__":
    unittest.main()
