"""Carried relationships execute through the real content validator/runtime."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import json
import struct
import unittest

from golden_board import canonical_manifest, content
from golden_board.content_teaching_v2 import ContentTeachingError, build_content_teaching_v2


SOURCE = Path(__file__).resolve().parents[2] / "conformance/content-v0.json"


class ContentTeachingTests(unittest.TestCase):
    def test_independent_semantic_construction_and_exact_framed_charge(self):
        source = SOURCE.read_bytes()
        result = build_content_teaching_v2(source)
        fixture = json.loads(source)
        self.assertEqual(result.base_stream.hex(), fixture["bases"][0]["stream_hex"])
        self.assertEqual(len(result.base_stream), 575)
        self.assertEqual(len(result.value), 1639)
        self.assertEqual(result.value[:4], (575).to_bytes(4, "big"))
        self.assertEqual(result.value[579:583], (1056).to_bytes(4, "big"))
        cursor = 583
        for count, width in ((48, 14), (6, 12), (4, 12), (8, 32)):
            self.assertEqual(int.from_bytes(result.value[cursor:cursor + 2], "big"), count)
            cursor += 2 + count * width
        self.assertEqual(cursor, len(result.value))
        with self.assertRaises(FrozenInstanceError):
            result.base_stream = b""

    def test_source_types_shapes_counts_and_comparison_bytes_fail_closed(self):
        source = SOURCE.read_bytes()
        mutations = [
            lambda s: s["bases"][0]["projection"]["records"][5].update(atom_width=True),
            lambda s: s["bases"][0]["projection"]["records"][5].update(extra=1),
            lambda s: s["bases"][0]["projection"]["records"][8].update(atom_count=3),
            lambda s: s["bases"][0]["projection"].update(root_record_id=28),
            lambda s: s["bases"][0].update(stream_hex="00" * 575),
            lambda s: s["bases"][0].update(stream_length=576),
            lambda s: s["bases"][0]["projection"]["records"][0].update(text="Changed"),
        ]
        for mutate in mutations:
            candidate = json.loads(source)
            mutate(candidate)
            with self.subTest(mutation=mutate):
                with self.assertRaises(ContentTeachingError):
                    build_content_teaching_v2(canonical_manifest.serialize_manifest(candidate))
        for raw in (b"{}", b" " + source, b"x" * (1048576 + 1)):
            with self.assertRaises(ContentTeachingError):
                build_content_teaching_v2(raw)

    def test_every_carried_scalar_consequence_is_whole_stream_acceptance(self):
        result = build_content_teaching_v2(SOURCE.read_bytes())
        rows = result.value[585:585 + 48 * 14]
        accepted = 0
        for offset, width, old, new, expected in struct.iter_unpack(">HHIIH", rows):
            self.assertEqual(int.from_bytes(result.base_stream[offset:offset + width], "big"), old)
            candidate = bytearray(result.base_stream)
            candidate[offset:offset + width] = new.to_bytes(width, "big")
            try:
                content.stream_validation(bytes(candidate))
                actual = 1
            except content.ContentReject:
                actual = 0
            self.assertEqual(actual, expected, (offset, new))
            accepted += actual
        self.assertEqual(accepted, 7)

    def test_carried_actions_replay_from_the_real_root_with_exact_budgets(self):
        result = build_content_teaching_v2(SOURCE.read_bytes())
        projection = content.stream_validation(result.base_stream)
        cursor = 583 + 2 + 48 * 14 + 2 + 6 * 12 + 2 + 4 * 12 + 2
        for row in (result.value[i:i + 32] for i in range(cursor, len(result.value), 32)):
            node, count, actions, phase, last, shape, selected, a, b, outcome, feedback, nxt, global_left, local_left = struct.unpack(">HB12sBBBBHHBHHHH", row)
            state = content.new_run(projection)
            for _ in range(2):
                if content.run_state_view(state).current_node_id == node:
                    break
                state, _ = content.step(projection, state, bytes.fromhex("03000000"))
                state = content.advance_committed(projection, state)
            self.assertEqual(content.run_state_view(state).current_node_id, node)
            for index in range(count):
                state, actual_last = content.step(projection, state, actions[4 * index:4 * index + 4])
            view = content.run_state_view(state)
            self.assertEqual((view.phase, actual_last, view.outcome, view.feedback_ref, view.next_node_ref, view.global_remaining, view.local_remaining),
                             (phase, last, outcome, feedback, nxt, global_left, local_left))
            ids = (a, b)[:selected]
            if view.committed_response:
                self.assertEqual(view.committed_response, bytes((shape,)) + selected.to_bytes(2, "big") + b"".join(x.to_bytes(2, "big") for x in ids))
            else:
                self.assertEqual(view.selection_buffer, ids)
            self.assertEqual(actions[4 * count:], bytes(12 - 4 * count))


if __name__ == "__main__":
    unittest.main()
