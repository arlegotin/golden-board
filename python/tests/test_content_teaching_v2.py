"""Carried relationships execute through the real content validator/runtime."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import json
import struct
import unittest
from unittest.mock import patch

from golden_board import canonical_manifest, content
from golden_board.content_teaching_v2 import ContentTeachingError, build_content_teaching_v2


SOURCE = Path(__file__).resolve().parents[2] / "conformance/content-v0.json"


class ContentTeachingTests(unittest.TestCase):
    def test_always_allowing_sequence_repetitions_changes_carried_evidence(self):
        from golden_board import m2_route_semantics_v2 as semantics
        from golden_board.m2_teaching_recipe_v2 import build_teaching_recipe_package
        from golden_board.recipe_wire_v2 import decode_recipe_package_v2
        source = SOURCE.read_bytes()
        correct = build_content_teaching_v2(source).value
        transition = content._transition

        def allow_all_sequence_repetitions(projection, state, action):
            # Inject only the rival runtime rule. Keep the declared flag and
            # every other transition rule unchanged outside this call.
            node = projection._by_id[state.current_node_id]
            flags = node.flags
            if node.response_shape == 3:
                object.__setattr__(node, 'flags', flags | 1)
            try:
                return transition(projection, state, action)
            finally:
                object.__setattr__(node, 'flags', flags)

        with patch.object(content, '_transition', allow_all_sequence_repetitions):
            mutant = build_content_teaching_v2(source).value
        self.assertNotEqual(mutant, correct, 'the repeated-selection flag needs a carried counterexample')
        package = decode_recipe_package_v2(build_teaching_recipe_package(), 8)
        with self.assertRaises(semantics.DecoderError):
            semantics._miniature(mutant, package)

    def test_assertion_bridge_rejects_byte_equivalent_uint_recipe_ports(self):
        from golden_board import recipe_wire_v2
        from golden_board.m2_teaching_recipe_v2 import build_teaching_recipe_package
        original = recipe_wire_v2.decode_recipe_package_v2(build_teaching_recipe_package(),8)
        expanded = bytearray(original.logical.encoded)
        cursor = 64
        for table in original.logical.tables:
            if table.table_id == 19:
                expanded[cursor+2] = 0  # Retag the complement mask as UINT8.
            cursor += 16+len(table.payload)
        for recipe in original.logical.recipes:
            if recipe.recipe_id == 101:
                descriptors = cursor+32
                expanded[descriptors+2] = 0
                expanded[descriptors+2*12+2] = 0
                nodes = descriptors+3*12
                for index in (2,3):
                    expanded[nodes+index*32+3] = 0
            cursor += recipe.recipe_bytes
        changed = recipe_wire_v2.encode_recipe_package_v2(bytes(expanded),8)
        package = recipe_wire_v2.decode_recipe_package_v2(changed,8)
        for value, expected in ((254,1),(253,2)):
            result = recipe_wire_v2.evaluate_recipe_v2(package,101,(bytes((value,)),))
            self.assertEqual((result.status,result.outputs),(0,(bytes((expected,)),)))
        # Equal one-byte answers cannot establish the bridge's BITS8 ports.
        with patch('golden_board.m2_teaching_recipe_v2.build_teaching_recipe_package',return_value=changed):
            with self.assertRaises(ContentTeachingError):
                build_content_teaching_v2(SOURCE.read_bytes())

    def _connected(self):
        raw = build_content_teaching_v2(SOURCE.read_bytes()).value
        at = 1703  # All four historical blocks are retained before this extension.
        self.assertGreater(len(raw), at, "missing connected control teaching")
        for width, count in ((4, 15), (4, 5)):
            self.assertEqual(int.from_bytes(raw[at:at+2], "big"), count)
            at += 2 + width * count
        count = int.from_bytes(raw[at:at+2], "big"); at += 2
        self.assertEqual(count, 7)
        variants = []
        for _ in range(count):
            n = int.from_bytes(raw[at:at+2], "big"); at += 2
            patches = tuple(struct.iter_unpack(">HHII", raw[at:at+12*n])); at += 12*n
            n = int.from_bytes(raw[at:at+2], "big"); at += 2
            rows = tuple(struct.iter_unpack(">B4sH6BHHB4H", raw[at:at+26*n])); at += 26*n
            variants.append((patches, rows))
        return raw, at, variants

    def test_connected_states_separate_controls_results_and_budget_meanings(self):
        _, _, variants = self._connected()
        # Row: operation, action, node, phase, last, shape, mode, flags,
        # count, ids[2], outcome, feedback, next, global, local.
        base = variants[0][1]
        self.assertEqual(base[0][2:], (26,1,0,1,1,0,0,0,0,0,0,0,8,2))
        self.assertEqual(base[1][3:5], (1,1))  # successful selection stays active
        self.assertEqual(base[2][3:5], (3,6))  # duplicate exhausts, preserves result
        self.assertEqual(base[3][3:5], (3,9))  # later reset cannot replenish
        self.assertEqual(base[-1][3:5], (2,8))  # committed is independently terminal
        sequence = variants[1][1][5]
        self.assertEqual(sequence[5:11], (3,2,0,2,2,1))  # mode2 does not force sorting
        repetition = variants[2][1][-1]
        self.assertEqual(repetition[5:11], (3,2,1,2,1,1))
        no_repetition = variants[1][1][6:]
        allows_repetition = variants[2][1]
        self.assertEqual(len(no_repetition), 6)
        for before, after in zip(no_repetition, allows_repetition):
            self.assertEqual(before[:4], after[:4])  # same input, node, phase
            self.assertEqual(before[-2:], after[-2:])  # same budget history
        self.assertEqual(no_repetition[4][4:11], (6,3,2,0,1,1,0))
        self.assertEqual(allows_repetition[4][4:11], (1,3,2,1,2,1,1))
        self.assertEqual(no_repetition[-1][8:11], (1,1,0))
        self.assertEqual(allows_repetition[-1][8:11], (2,1,1))
        ordered_set = variants[3][1][-1]
        self.assertEqual(ordered_set[5:11], (2,3,0,2,1,2))
        active = variants[4][1]
        self.assertEqual(active[2][3:5], (1,6))
        self.assertEqual(active[2][-2:], (20,14))
        self.assertEqual(active[3][3:5], (1,2))  # duplicate did not stop processing
        self.assertEqual(active[6][3:5], (1,7))
        self.assertEqual(active[7][3:5], (1,2))  # over-limit did not stop processing
        # COMMIT matches the authored trace in both; its remaining counts differ.
        self.assertEqual(variants[5][1][1][-2:], (8,1))
        self.assertEqual(variants[5][1][4][-2:], (7,0))
        self.assertEqual(variants[6][1][-2][2:5], (27,1,0))
        self.assertEqual(variants[6][1][-2][-2:], (1,1))  # clamp at advancement
        self.assertEqual(variants[6][1][-1][3:5], (3,1))
        self.assertEqual(variants[6][1][-1][-2:], (0,0))

    def test_all_connected_snapshots_replay_with_complete_state_and_exact_inputs(self):
        raw, _, variants = self._connected()
        compared = 0
        for patches, rows in variants:
            changed = bytearray(raw[4:579])
            for offset,width,old,new in patches:
                self.assertEqual(int.from_bytes(changed[offset:offset+width],'big'),old)
                changed[offset:offset+width] = new.to_bytes(width,'big')
            projection = content.stream_validation(bytes(changed))
            records = {r.record_id:r.payload for r in content.projection_view(projection).records}
            state = None
            for operation,action,*expected in rows:
                last = 0
                if operation == 0:
                    self.assertEqual(action,bytes(4))
                    state = content.new_run(projection)
                elif operation == 1:
                    state,last = content.step(projection,state,action)
                else:
                    self.assertEqual(operation,2)
                    self.assertEqual(action,bytes(4))
                    state = content.advance_committed(projection,state)
                view = content.run_state_view(state)
                node = records[view.current_node_id]
                ids = view.selection_buffer
                if view.committed_response:
                    self.assertEqual(view.committed_response[0],node.response_shape)
                    ids = tuple(value[0] for value in struct.iter_unpack('>H',view.committed_response[3:]))
                actual = (view.current_node_id,view.phase,last,node.response_shape,node.answer_mode,
                          node.flags,len(ids),*(ids+(0,)*(2-len(ids))),view.outcome,
                          view.feedback_ref,view.next_node_ref,view.global_remaining,view.local_remaining)
                self.assertEqual(actual,tuple(expected))
                compared += 1
        self.assertEqual(compared,75)

    def test_asserted_output_is_distinct_from_structural_acceptance(self):
        raw, at, _ = self._connected()
        at += 101  # Grounded presence and case-count relationships.
        self.assertEqual(int.from_bytes(raw[at:at+2], "big"), 1); at += 2
        bridge = struct.unpack(">4HBHHBBHHB", raw[at:at+20]); at += 20
        self.assertEqual(bridge, (2,19,18,101,0,17,2,1,1,10,4,1))
        self.assertEqual(int.from_bytes(raw[at:at+2], "big"), 4); at += 2
        descriptors = tuple(struct.iter_unpack(">HHI", raw[at:at+32])); at += 32
        self.assertEqual(int.from_bytes(raw[at:at+2], "big"), 4); at += 2
        cases = tuple(struct.iter_unpack(">4IBHBB", raw[at:]))
        self.assertEqual(cases, ((255,1,1,254,1,0,1,1), (255,2,2,253,1,0,2,1),
                                 (255,2,2,254,1,0,1,0), (255,1,1,253,1,0,2,0)))
        base = raw[4:579]
        for case in cases:
            changed = bytearray(base)
            for (offset,width,old), new in zip(descriptors, case[:4]):
                self.assertEqual(int.from_bytes(changed[offset:offset+width], "big"), old)
                changed[offset:offset+width] = new.to_bytes(width, "big")
            projection = content.stream_validation(bytes(changed))
            state, result = content.step(projection, content.new_run(projection), b"\3\0\0\0")
            view = content.run_state_view(state)
            self.assertEqual((result,view.outcome,view.feedback_ref,view.next_node_ref), (3,1,21,27))

    def test_carried_witnesses_distinguish_replacement_reset_and_exhaustion(self):
        result = build_content_teaching_v2(SOURCE.read_bytes())
        cursor = 583 + 2 + 48 * 14 + 2 + 6 * 12 + 2 + 4 * 12
        count = int.from_bytes(result.value[cursor:cursor + 2], "big")
        rows = {}
        for index in range(count):
            start = cursor + 2 + index * 32
            row = struct.unpack(">HB12sBBBBHHBHHHH", result.value[start:start + 32])
            node, n, actions, *outcome = row
            rows[node, actions[:4 * n]] = tuple(outcome)
        # Identical exhausted phase and budgets, three distinct last-action
        # results. A last-choice-wins rival must disagree with a carried row.
        expected = {
            "0100000101000001": (3, 6, 1, 1, 1, 0, 0, 0, 0, 6, 0),
            "0100000101000002": (3, 7, 1, 1, 1, 0, 0, 0, 0, 6, 0),
            "0100000102000000": (3, 2, 1, 0, 0, 0, 0, 0, 0, 6, 0),
        }
        for actions, consequence in expected.items():
            with self.subTest(actions=actions):
                key = (26, bytes.fromhex(actions))
                self.assertIn(key, rows, "missing discriminating carried witness")
                self.assertEqual(rows[key], consequence)

    def test_independent_semantic_construction_and_exact_framed_charge(self):
        source = SOURCE.read_bytes()
        result = build_content_teaching_v2(source)
        fixture = json.loads(source)
        self.assertEqual(result.base_stream.hex(), fixture["bases"][0]["stream_hex"])
        self.assertEqual(len(result.base_stream), 575)
        self.assertEqual(len(result.value), 4106)
        self.assertEqual(result.value[:4], (575).to_bytes(4, "big"))
        self.assertEqual(result.value[579:583], (3523).to_bytes(4, "big"))
        cursor = 583
        for count, width in ((48, 14), (6, 12), (4, 12), (10, 32)):
            self.assertEqual(int.from_bytes(result.value[cursor:cursor + 2], "big"), count)
            cursor += 2 + count * width
        self.assertEqual(cursor, 1703)
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
        for row in (result.value[i:i + 32] for i in range(cursor, cursor + 10 * 32, 32)):
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
