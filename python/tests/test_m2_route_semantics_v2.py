"""Observed numeric relationships cannot be replaced by framing or a digest."""
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
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
            build_route_prefixes_v2(cls.compiled)[0], 2048, 112, 0)

    def validate(self, definitions=None, package=None):
        return validate_local_definitions(
            self.route.definitions if definitions is None else definitions,
            self.route.package if package is None else package,
            side=2048, width=112, sector=0)

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

    def test_group_traces_bind_raw_candidates_identity_and_unknown_symbols(self):
        # Keep all outer framing valid; every context/derivation is checked
        # independently of the generic VM's successful execution.
        offsets = (330,140,174+4*24+5,174+7*24+8,360,363,368,369,370,
                   373+7,373+10,391,400,410,442)
        offsets += tuple(base+offset for base in (61,81) for offset in (0,2,6,8,10,12,14,16))
        for offset in offsets:
            definitions = list(self.route.definitions)
            raw = bytearray(definitions[9]);raw[offset] ^= 1
            definitions[9] = bytes(raw)
            with self.subTest(offset=offset), self.assertRaises(DecoderError):
                self.validate(tuple(definitions))

    def test_vm_consistent_verified_and_identity_lies_do_not_override_observations(self):
        for at,flag in ((246,7),(342,8)):
            definitions=list(self.route.definitions)
            raw=bytearray(definitions[9])
            raw[at+flag]=1
            if flag==7:raw[at+10]=2  # corrected candidate falsely called verified
            else:raw[at+11]=1  # same A moved into foreign physical ownership
            definitions[9]=bytes(raw)
            with self.subTest(flag=flag),self.assertRaises(DecoderError):
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
        for offset in (start+2+13, start+1056-1):
            definitions = list(self.route.definitions)
            raw = bytearray(definitions[11])
            raw[offset] ^= 1
            definitions[11] = bytes(raw)
            with self.subTest(offset=offset), self.assertRaises(DecoderError):
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
