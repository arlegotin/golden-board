"""Observed numeric relationships cannot be replaced by framing or a digest."""
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import struct
import unittest

from golden_board import content
from golden_board.m2_decoder import DecoderError
from golden_board.m2_route_receiver_v2 import decode_observed_route_v2
from golden_board.m2_route_semantics_v2 import (
    validate_local_definitions, validate_recovered_context,
)
from golden_board.m2_route_v2 import build_route_prefixes_v2
from golden_board.m2_slice_v1 import compile_slice_v1

ROOT = Path(__file__).resolve().parents[2]


class NumericRouteSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiled = compile_slice_v1(*((ROOT / p).read_bytes() for p in (
            'studies/m2/slice-v1.json', 'studies/m2/slice-v0.json',
            'conformance/content-v0.json', 'conformance/chess-v0.json',
            'reports/game-set-v0.bin', 'spec/content-v0.md',
            'spec/constants-v0.toml', 'spec/curriculum-v0.toml')))
        cls.route = decode_observed_route_v2(
            build_route_prefixes_v2(cls.compiled)[0], 2040, 128, 0)

    def validate(self, definitions=None, package=None):
        return validate_local_definitions(
            self.route.definitions if definitions is None else definitions,
            self.route.package if package is None else package,
            side=2040, width=128, sector=0)

    def connected_spans(self):
        raw = self.route.definitions[11]
        cursor = 206+1703
        layouts = []
        for count in (15,5):
            self.assertEqual(int.from_bytes(raw[cursor:cursor+2],'big'),count)
            layouts.extend(range(cursor+2,cursor+2+4*count,4))
            cursor += 2+4*count
        self.assertEqual(int.from_bytes(raw[cursor:cursor+2],'big'),7)
        cursor += 2
        variants = []
        for _ in range(7):
            count = int.from_bytes(raw[cursor:cursor+2],'big'); cursor += 2
            patches = tuple(range(cursor,cursor+12*count,12)); cursor += 12*count
            count = int.from_bytes(raw[cursor:cursor+2],'big'); cursor += 2
            states = tuple(range(cursor,cursor+26*count,26)); cursor += 26*count
            variants.append((patches,states))
        self.assertEqual(sum(len(rows) for _,rows in variants),75)
        return tuple(layouts),tuple(variants),cursor

    def altered_fact12(self, offset, replacement=None):
        definitions = list(self.route.definitions)
        raw = bytearray(definitions[11])
        raw[offset] = raw[offset]^1 if replacement is None else replacement
        definitions[11] = bytes(raw)
        return tuple(definitions)

    def test_every_intermediate_state_is_checked_without_changing_framing(self):
        _,variants,_ = self.connected_spans()
        for variant,(_,rows) in enumerate(variants):
            for ordinal,start in enumerate(rows):
                # Remaining local events must be checked even before COMMIT.
                with self.subTest(variant=variant,state=ordinal), self.assertRaises(DecoderError):
                    self.validate(self.altered_fact12(start+25))
        # Exercise the other state fields on an active state, not just its tail.
        for field in (6,7,8,9,10,11,12,14,16,17,19,21,23):
            with self.subTest(field=field), self.assertRaises(DecoderError):
                self.validate(self.altered_fact12(variants[0][1][1]+field))

    def test_sequence_repeat_permission_requires_the_carried_flag(self):
        _,variants,_ = self.connected_spans()
        definitions = list(self.route.definitions)
        raw = bytearray(definitions[11])
        no_repeats = variants[1][1][6:]
        repeats = variants[2][1]
        self.assertEqual(len(no_repeats),len(repeats))
        # Reuse the complete, valid flag-on history but retain each actual
        # flag-off declaration. This is the always-allow-repeats rival.
        for to,source in zip(no_repeats,repeats):
            self.assertEqual(raw[to:to+5],raw[source:source+5])
            flag = raw[to+11]
            raw[to:to+26] = raw[source:source+26]
            raw[to+11] = flag
        self.assertNotEqual(bytes(raw),definitions[11])
        definitions[11] = bytes(raw)
        with self.assertRaises(DecoderError):
            self.validate(tuple(definitions))

    def test_connected_input_sequence_cannot_be_replaced_by_another_valid_trajectory(self):
        _,variants,_ = self.connected_spans()
        definitions = list(self.route.definitions)
        raw = bytearray(definitions[11])
        patches,rows = variants[1]
        # Keep mode2 and replace the owned shape3 experiment with valid shape2.
        # Recompute every consequence, so a validator trusting supplied inputs
        # would accept this substitute and silently lose the discriminator.
        patch_at, = patches
        offset,width,old,_ = struct.unpack('>HHII',raw[patch_at:patch_at+12])
        raw[patch_at+8:patch_at+12] = (2).to_bytes(4,'big')
        base = bytearray(raw[206+4:206+579])
        self.assertEqual(int.from_bytes(base[offset:offset+width],'big'),old)
        base[offset:offset+width] = (2).to_bytes(width,'big')
        projection = content.stream_validation(bytes(base))
        records = {r.record_id:r.payload for r in content.projection_view(projection).records}
        state = None
        for start in rows:
            op,action = raw[start],bytes(raw[start+1:start+5])
            last = 0
            if op == 0:
                state = content.new_run(projection)
            elif op == 2:
                state = content.advance_committed(projection,state)
            else:
                state,last = content.step(projection,state,action)
            view = content.run_state_view(state); node = records[view.current_node_id]
            ids = view.selection_buffer
            if view.committed_response:
                ids = tuple(v[0] for v in struct.iter_unpack('>H',view.committed_response[3:]))
            raw[start:start+26] = struct.pack('>B4sH6BHHB4H',op,action,view.current_node_id,
                view.phase,last,node.response_shape,node.answer_mode,node.flags,len(ids),
                *(ids+(0,)*(2-len(ids))),view.outcome,view.feedback_ref,view.next_node_ref,
                view.global_remaining,view.local_remaining)
        definitions[11] = bytes(raw)
        with self.assertRaises(DecoderError):
            self.validate(tuple(definitions))

    def test_connected_layouts_and_exact_actions_cannot_drift(self):
        layouts,variants,_ = self.connected_spans()
        offsets = [start+3 for start in layouts]
        offsets.extend(start for _,rows in variants for start in rows)
        offsets.extend(start+4 for _,rows in variants for start in rows)
        for offset in offsets:
            with self.subTest(offset=offset), self.assertRaises(DecoderError):
                self.validate(self.altered_fact12(offset))

    def test_role_bounds_counts_and_assertion_direction_are_semantically_checked(self):
        _,_,roles = self.connected_spans()
        # Typed field links, presence bits, every interval verdict, accepted and
        # total case counts (distinct quantities), and the asserted-output ports.
        offsets = [roles+2+6*i+j for i in range(2) for j in (1,2,3,5)]
        offsets += [roles+16+3*i+2 for i in range(3)]
        offsets += [roles+27+4*i+3 for i in range(6)]
        offsets += [roles+53+16*i+j for i in range(3) for j in (7,9,11,13,15)]
        assertion = roles+101
        offsets += [assertion+2+i for i in (1,3,5,7,8,10,12,13,14,16,18,19)]
        offsets += [assertion+58+21*i+j for i in range(4) for j in (3,7,11,15,16,18,19,20)]
        for offset in offsets:
            with self.subTest(offset=offset), self.assertRaises(DecoderError):
                self.validate(self.altered_fact12(offset))

    def test_assertion_bridge_rejects_a_well_typed_changed_complement_closure(self):
        from golden_board import recipe_wire_v2
        package = self.route.package
        table_offsets,recipe_offsets = {},{}
        cursor = 64
        for table in package.logical.tables:
            table_offsets[table.table_id] = cursor
            cursor += 16+len(table.payload)
        for recipe in package.logical.recipes:
            recipe_offsets[recipe.recipe_id] = cursor
            cursor += recipe.recipe_bytes
        # Both mutants remain legal recipe packages. One changes the mask,
        # the other changes XOR to OR; descriptor or parser rejection is not
        # the reason the observed finite bridge must refuse them.
        node = recipe_offsets[101]+32+3*12+3*32
        for offset,value in ((table_offsets[19]+16,254),(node+2,12)):
            expanded = bytearray(package.logical.encoded)
            expanded[offset] = value
            encoded = recipe_wire_v2.encode_recipe_package_v2(bytes(expanded),8)
            changed = recipe_wire_v2.decode_recipe_package_v2(encoded,8)
            with self.subTest(offset=offset), self.assertRaisesRegex(DecoderError,'fact12.assertion'):
                self.validate(package=changed)

    def test_observed_facts_then_recovered_context_without_source_access(self):
        with patch('builtins.open', side_effect=AssertionError('source access')):
            commitments = self.validate()
            validate_recovered_context(commitments,
                required_bytes=self.compiled.required_content_bytes,
                all_bytes=self.compiled.content_bytes)
            validate_recovered_context(commitments,
                required_bytes=self.compiled.required_content_bytes, all_bytes=None)
            skipped = validate_recovered_context(commitments, required_bytes=None, all_bytes=None)
            self.assertEqual((skipped.required_context_checked, skipped.all_context_checked,
                              skipped.section_membership_checked), (False, False, False))

    def test_each_fact_has_semantic_checks_after_valid_outer_framing(self):
        for index in range(12):
            definitions = list(self.route.definitions)
            raw = bytearray(definitions[index])
            raw[-1] ^= 1
            definitions[index] = bytes(raw)
            with self.subTest(fact=index+1), self.assertRaises(DecoderError):
                self.validate(tuple(definitions))

    def test_complete_group_traces_bind_queries_identity_and_all_result_fields(self):
        offsets = list(range(0,22,2)) + [21]
        for case in (0,3,4,6,7):
            offsets.extend(22+57*case+field for field in (0,4,5,7,11,32,33,56))
        offsets.extend(22+57*7+field for field in (12,14,18,20,22,24,26,28))
        for offset in offsets:
            definitions = list(self.route.definitions)
            raw = bytearray(definitions[9])
            raw[offset] ^= 1
            definitions[9] = bytes(raw)
            with self.subTest(offset=offset), self.assertRaises(DecoderError):
                self.validate(tuple(definitions))

    def test_verified_and_identity_claims_cannot_override_constructed_observations(self):
        for case, field, claimed in ((3,32,2),(7,33,1)):
            definitions = list(self.route.definitions)
            raw = bytearray(definitions[9])
            raw[22+57*case+field] = claimed
            definitions[9] = bytes(raw)
            with self.subTest(case=case), self.assertRaisesRegex(DecoderError,'fact10.complete-result'):
                self.validate(tuple(definitions))

    def test_context_claim_is_deferred_then_bound_to_actual_stream(self):
        definitions = list(self.route.definitions)
        raw = bytearray(definitions[11])
        raw[2:4] = (587).to_bytes(2, 'big')
        definitions[11] = bytes(raw)
        commitments = self.validate(tuple(definitions))
        validate_recovered_context(commitments, required_bytes=None, all_bytes=None)
        with self.assertRaises(DecoderError):
            validate_recovered_context(commitments,
                required_bytes=self.compiled.required_content_bytes, all_bytes=None)

    def test_full_miniature_outcomes_and_action_costs_are_replayed(self):
        # Fact12: three contexts18 + layouts/kinds188 + length4 + miniature575
        # + supplement length4. The first scalar row's acceptance is at +14.
        start = 18+188+4+575+4
        for offset in (start+2+13, start+1120-1):
            definitions = list(self.route.definitions)
            raw = bytearray(definitions[11])
            raw[offset] ^= 1
            definitions[11] = bytes(raw)
            with self.subTest(offset=offset), self.assertRaises(DecoderError):
                self.validate(tuple(definitions))

    def test_selection_discriminants_cannot_be_forged_or_replaced_by_valid_rows(self):
        start = 206 + 583 + 2 + 48 * 14 + 2 + 6 * 12 + 2 + 4 * 12 + 2
        for index in (8, 9):
            for mutation in ('replace-valid', 'last-result', 'buffer'):
                definitions = list(self.route.definitions)
                raw = bytearray(definitions[11])
                at = start + 32 * index
                if mutation == 'replace-valid':
                    raw[at:at + 32] = raw[start + 32 * 6:start + 32 * 7]
                elif mutation == 'last-result':
                    raw[at + 16] = 6
                else:
                    raw[at + 20] = 2
                definitions[11] = bytes(raw)
                with self.subTest(index=index, mutation=mutation), self.assertRaises(DecoderError):
                    self.validate(tuple(definitions))

    def test_forged_logical_package_cannot_bypass_wire_validation(self):
        # The public package wrapper is constructible; semantic validation must
        # reparse bytes rather than trust the supplied logical table projection.
        forged = replace(self.route.package, encoded=b'bad')
        with self.assertRaises(DecoderError):
            self.validate(package=forged)

    def test_body_membership_and_typed_but_false_position_reject(self):
        commitments = self.validate()
        records = self.compiled.projection.records
        raw = self.compiled.content_bytes
        cursor, frames = 4, {}
        for record in records:
            end = cursor+8+int.from_bytes(raw[cursor+4:cursor+8], 'big')
            frames[record.record_id] = raw[cursor:end]
            cursor = end
        bodies = {row.section_id:b''.join(frames[rid] for rid in row.record_ids)
                  for row in self.compiled.atomic_assignments}
        validate_recovered_context(commitments,
            required_bytes=self.compiled.required_content_bytes,
            all_bytes=raw, body_payloads=bodies)
        changed_bodies = dict(bodies)
        changed_bodies[100] = changed_bodies[101]
        with self.assertRaises(DecoderError):
            validate_recovered_context(commitments,
                required_bytes=self.compiled.required_content_bytes,
                all_bytes=raw, body_payloads=changed_bodies)
        authored = content.authoring_from_validated(self.compiled.required_projection)
        changed = []
        for record in authored.records:
            if record.record_id == 43:
                cells = list(record.payload.cells)
                cells[260] = 0  # Valid byte atom; false nominal-target consequence.
                record = replace(record, payload=replace(record.payload, cells=tuple(cells)))
            changed.append(record)
        typed = content.encode_content_v0(replace(authored, records=tuple(changed)))
        with self.assertRaises(DecoderError):
            validate_recovered_context(commitments, required_bytes=typed, all_bytes=None)

    def test_forged_commitment_rechecks_its_observed_bytes(self):
        commitments = self.validate()
        raw = bytearray(commitments.fact12)
        raw[18+188+4+575+4+2+13] ^= 1
        with self.assertRaises(DecoderError):
            validate_recovered_context(replace(commitments, fact12=bytes(raw)),
                                       required_bytes=None, all_bytes=None)

    def test_strict_input_bounds_and_present_stream_failures(self):
        for definitions in (list(self.route.definitions), (),
                            (*self.route.definitions[:-1], bytearray(self.route.definitions[-1]))):
            with self.assertRaises(DecoderError):
                self.validate(definitions)
        commitments = self.validate()
        for stream in (b'', b'\0'*1_048_577, bytearray(self.compiled.required_content_bytes)):
            with self.assertRaises(DecoderError):
                validate_recovered_context(commitments, required_bytes=stream, all_bytes=None)
        with self.assertRaises(DecoderError):
            validate_recovered_context(object(), required_bytes=None, all_bytes=None)


if __name__ == '__main__':
    unittest.main()
