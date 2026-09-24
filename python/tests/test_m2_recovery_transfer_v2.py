"""Finite source-generated transfer checks, not acquisition or qualification.

The fixture builds today's source carrier. Expected common blocks are encoded
from its source sections before recovery; no participant packet, saved decoder
answer, damage corpus or checked-in carrier is an input. Canonical orientation
and geometry are given here; route acquisition is a separate test obligation.
"""
from dataclasses import replace
from pathlib import Path
import os
import unittest
from unittest.mock import patch

from golden_board import bootstrap, bootstrap_v2, curriculum, m2_codec, m2_policy
from golden_board import recipe_wire_v2
from golden_board import m2_decoder as old_decoder
from golden_board import m2_program_refinement_v2, m2_recovery_recipe_v2
from golden_board.m2_decoder_v2 import ObservationDecoderV2
from golden_board.m2_carrier_v2 import build_development_carrier
from golden_board.m2_mapping_v2 import mapping_parameters
from golden_board.m2_recovery_recipe_v2 import evaluate_recovery_native, recovery_program_refined
from golden_board.m2_revision_recipe import build_revision_recipe_package
from golden_board.m2_route_receiver_v2 import decode_observed_route_v2
from golden_board.m2_slice import compile_slice_v0
from golden_board.m2_slice_v1 import compile_slice_v1


ROOT = Path(__file__).resolve().parents[2]


def identity(block):
    return block[:2] + block[4:14] + block[16:20] + block[22:26]


class RecoveryTransfer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources = tuple((ROOT/path).read_bytes() for path in (
            'studies/m2/slice-v0.json', 'conformance/content-v0.json',
            'conformance/chess-v0.json', 'reports/game-set-v0.bin',
            'spec/content-v0.md', 'spec/constants-v0.toml', 'spec/curriculum-v0.toml'))
        compiled = compile_slice_v1((ROOT/'studies/m2/slice-v1.json').read_bytes(), *sources)
        policy = m2_policy.load_profile_policy(
            (ROOT/'spec/profile-policy-v0.toml').read_bytes()).capacity_policy
        cls.image = build_development_carrier(compiled, compile_slice_v0(*sources),
            curriculum.load_blueprint(sources[-1]), policy)
        cls.plan = cls.image.capacity_plan
        cls.packed = cls.image.carrier[4:]
        cls.inventory_raw = bootstrap_v2.encode_inventory(cls.plan.inventory)
        if bootstrap_v2.decode_inventory(cls.inventory_raw) != cls.plan.inventory:
            raise AssertionError('source inventory failed complete admission')

        # Extract the actual program bytes from the freshly built matrix shell.
        # No source package reconstruction supplies the receiver's package.
        prefix = bytearray(len(cls.image.route_prefixes[0]))
        for bit in range(len(prefix)*8):
            row, column = bootstrap.sector_cell(cls.plan.side, cls.plan.width, 0, bit)
            flat = row*cls.plan.side + column
            prefix[bit//8] |= ((cls.packed[flat//8] >> (7-flat % 8)) & 1) << (7-bit % 8)
        if bytes(prefix) != cls.image.route_prefixes[0]:
            raise AssertionError('physical route extraction differs from source route')
        cls.physical_prefix = bytes(prefix)
        at, packages = 64, []
        while at < len(prefix):
            length = int.from_bytes(prefix[at+4:at+8], 'big')
            if prefix[at+1] == 5:
                packages.append(bytes(prefix[at+8:at+8+length]))
            at += 8+length
        if at != len(prefix) or len(packages) != 1:
            raise AssertionError('physical route package framing')
        cls.package = recipe_wire_v2.decode_recipe_package_v2(packages[0], 8)
        for rid in (120, 123, 124, 127):
            if not recovery_program_refined(cls.package, rid):
                raise AssertionError(f'carried recovery closure {rid}')
        cls.recipes = {r.recipe_id: r for r in cls.package.logical.recipes}
        cls.coordinate_cache = {}

        # This oracle knows source sections, never decoder results or inferred
        # headers. Physical groups are enumerated before observations are read.
        cls.source_groups, cls.sections = {}, {}
        first = 1
        for section in cls.plan.sections:
            envelope = bootstrap.encode_section_envelope(bootstrap.SectionEnvelope(
                section.section_id, section.section_type, section.version,
                section.closure, 1, section.dependencies, section.payload))
            groups = []
            for block in bootstrap.fragment_section(envelope, 8, 0):
                cls.source_groups[first] = (section.factor, block)
                groups.append(first)
                first += section.factor
            cls.sections[section.section_id] = (section, tuple(groups), envelope)
        if first != cls.plan.units+1:
            raise AssertionError('source group enumeration does not exhaust carrier')
        cls.selected = {}
        for factor in (1, 2, 5):
            section, groups, _ = next(value for value in cls.sections.values()
                if value[0].factor == factor
                and value[0].section_type == (4 if factor == 2 else 3)
                and len(value[1]) >= 4)
            cls.selected[factor] = groups[2]

    def setUp(self):
        self.charged_steps = 0
        self.peak_scratch = 0

    def call(self, rid, inputs, *, generic=False):
        # Charge the full declared call before native dispatch, including
        # rejection. These counters are test accounting, not a new gate.
        recipe = self.recipes[rid]
        self.charged_steps += recipe.primitive_steps
        self.peak_scratch = max(self.peak_scratch, recipe.peak_live_scratch_bytes)
        if generic:
            return bootstrap._evaluate_validated_recipe(self.package.logical, rid, inputs)
        return evaluate_recovery_native(self.package, rid, inputs)

    def coordinates(self, unit, *, generic=False):
        if not generic and unit in self.coordinate_cache:
            self.charged_steps += 1728*self.recipes[124].primitive_steps
            self.peak_scratch = max(self.peak_scratch, self.recipes[124].peak_live_scratch_bytes)
            return self.coordinate_cache[unit]
        prefix = (self.plan.side.to_bytes(2, 'big'), self.plan.width.to_bytes(2, 'big'),
                  unit.to_bytes(4, 'big'))
        result = []
        for bit in range(1728):
            mapped = self.call(124, (*prefix, bit.to_bytes(2, 'big')), generic=generic)
            self.assertEqual(mapped.status, 0)
            result.append(int.from_bytes(mapped.outputs[5], 'big'))
        if not generic:
            self.coordinate_cache[unit] = tuple(result)
        return tuple(result)

    def pairs(self, first, factor, overrides=None, *, generic=False):
        overrides = {} if overrides is None else overrides
        pairs = []
        for unit in range(first, first+factor):
            values, mask = bytearray(216), bytearray(216)
            for bit, flat in enumerate(self.coordinates(unit, generic=generic)):
                value = overrides.get(flat, (self.packed[flat//8] >> (7-flat % 8)) & 1)
                if value is None:
                    mask[bit//8] |= 128 >> (bit % 8)
                else:
                    values[bit//8] |= value << (7-bit % 8)
            pairs.append(bytes(values+mask))
        return (*pairs, *(bytes(432),)*(5-factor))

    def lookup(self, target, *, generic=False):
        result = self.call(123, (self.inventory_raw.ljust(16384, b'\0'),
            len(self.inventory_raw).to_bytes(2, 'big'), target.to_bytes(4, 'big')), generic=generic)
        self.assertEqual(result.status, 0)
        factor, first, last, key, total = result.outputs
        factor, first, last = factor[0], int.from_bytes(first, 'big'), int.from_bytes(last, 'big')
        self.assertEqual(last, first+factor-1)
        self.assertEqual(int.from_bytes(total, 'big'), self.plan.units)
        expected_factor, expected_block = self.source_groups[first]
        self.assertEqual((factor, key), (expected_factor, identity(expected_block)))
        return factor, first, key

    def recover(self, target, overrides=None, *, generic=False):
        factor, first, key = self.lookup(target, generic=generic)
        pairs = self.pairs(first, factor, overrides, generic=generic)
        inputs = (bytes((factor,)), bytes(((1 << factor)-1,)), key, *pairs)
        return self.call(120, inputs, generic=generic)

    def erased_headers(self, first):
        # The entire first-four-word region is partitioned across the lanes.
        # Every member loses >3 bits per word and cannot decode its own header;
        # each physical bit still has four known raw witnesses for REP5.
        erased = {}
        for lane in range(5):
            positions = self.coordinates(first+lane)
            for bit in range(lane, 4*72, 5):
                erased[positions[bit]] = None
        return erased

    def replace_lane(self, edits, unit, block):
        encoded = m2_codec.eh72_encode_unit(block)
        for bit, flat in enumerate(self.coordinates(unit)):
            edits[flat] = (encoded[bit//8] >> (7-bit % 8)) & 1

    def test_real_factor_one_two_five_groups_from_physical_cells(self):
        for factor, first in self.selected.items():
            with self.subTest(factor=factor, first=first):
                expected = self.source_groups[first][1]
                self.assertNotIn(int.from_bytes(expected[4:8], 'big'), (400, 401))
                # Query a last member: ownership must still return group-first.
                actual = self.recover(first+factor-1)
                self.assertEqual(actual, bootstrap.RecipeResult(0, (b'\2', b'\1', expected)))
                for lane in self.pairs(first, factor)[:factor]:
                    self.assertEqual(lane, m2_codec.eh72_encode_unit(expected)+bytes(216))
        self.assertGreater(self.charged_steps, 0)

    def test_observed_route_refinement_starts_cold_without_source_files(self):
        m2_recovery_recipe_v2._neutral_baseline.cache_clear()
        m2_program_refinement_v2._expected.cache_clear()
        build_revision_recipe_package.cache_clear()
        with (patch('builtins.open', side_effect=AssertionError('runtime source read')),
              patch('io.open', side_effect=AssertionError('runtime path read')),
              patch('os.open', side_effect=AssertionError('runtime descriptor read')),
              patch('golden_board.m2_route_v2.build_route_prefixes_v2',
                    side_effect=AssertionError('runtime route reconstruction'))):
            observed = decode_observed_route_v2(self.physical_prefix, self.plan.side, self.plan.width, 0)
        self.assertEqual(observed.package.encoded, self.package.encoded)
        self.assertEqual(observed.inventory_section_id, 1)

    def test_all_member_headers_fail_individually_but_raw_rep_recovers(self):
        first = self.selected[5]
        erased = self.erased_headers(first)
        _, _, key = self.lookup(first)
        for lane in self.pairs(first, 5, erased):
            individual = self.call(120, (b'\1', b'\1', key, lane, *(bytes(432),)*4))
            self.assertEqual(individual, bootstrap.RecipeResult(0, (b'\1', b'\0', bytes(191))))
        result = self.recover(first+4, erased)
        self.assertEqual(result, bootstrap.RecipeResult(0,
            (b'\3', b'\1', self.source_groups[first][1])))

    def test_new_valid_payload_conflicts_and_cannot_relabel_physical_owner(self):
        first = self.selected[5]
        source = self.source_groups[first][1]
        common = bootstrap.decode_common_block(source, 8)
        third = bootstrap.encode_common_block(replace(common,
            payload=bytes(value ^ 0xa5 for value in common.payload)))
        self.assertNotEqual(third, source)
        fixture = next(t for t in self.package.logical.tables if t.table_id == 24).payload
        self.assertNotIn(m2_codec.eh72_encode_unit(third), (fixture[:216], fixture[216:]))
        conflict = {}
        self.replace_lane(conflict, first+4, third)
        self.assertEqual(self.recover(first, conflict),
            bootstrap.RecipeResult(0, (b'\4', b'\0', bytes(191))))
        # A fresh locally valid packet is copied to another physical fragment.
        # Its original header cannot override inventory-derived membership.
        other = first+5
        self.assertEqual(self.source_groups[other][0], 5)
        wrong_group = {}
        for unit in range(other, other+5):
            self.replace_lane(wrong_group, unit, third)
        self.assertEqual(self.recover(other+4, wrong_group),
            bootstrap.RecipeResult(0, (b'\2', b'\0', third)))

    def test_inventory_bootstrap_chain_then_complete_inventory_admission(self):
        capacity = mapping_parameters(self.plan.side, self.plan.width).units
        result = self.call(127, (capacity.to_bytes(4, 'big'), b'\x1f',
            *self.pairs(1, 5, self.erased_headers(1))))
        self.assertEqual(result.status, 0)
        self.assertEqual(result.outputs[:2], (b'\3', b'\1'))
        first = bootstrap.decode_common_block(result.outputs[2], 8)
        blocks = [result.outputs[2]]
        for ordinal in range(1, first.fragment_count):
            key = (b'\0\10\0\0\0\1\0\0\0\1\0\2' + ordinal.to_bytes(2, 'big')
                   + first.fragment_count.to_bytes(2, 'big')
                   + first.section_envelope_length.to_bytes(4, 'big'))
            current = 1+5*ordinal
            recovered = self.call(120, (b'\5', b'\x1f', key, *self.pairs(current, 5)))
            self.assertEqual(recovered.status, 0)
            self.assertEqual(recovered.outputs[:2], (b'\2', b'\1'))
            blocks.append(recovered.outputs[2])
        expected = tuple(self.source_groups[group][1] for group in self.sections[1][1])
        self.assertEqual(tuple(blocks), expected)
        copy, raw = bootstrap.assemble_semantic_copy(blocks, 8)
        envelope = bootstrap.decode_section_envelope(raw)
        inventory = bootstrap_v2.decode_inventory(envelope.payload)
        bootstrap.validate_inventory_closure(inventory)
        bootstrap.validate_envelope_against_inventory(envelope, inventory)
        self.assertEqual((copy, envelope.section_id, envelope.section_type,
            envelope.section_version, envelope.closure_class, envelope.check_id,
            envelope.dependencies), (0, 1, 1, 2, 128, 1, ()))
        self.assertEqual((raw, envelope.payload, inventory),
                         (self.sections[1][2], self.inventory_raw, self.plan.inventory))

    def operational_path(self, overrides=None):
        owners = tuple((ROOT/path).read_bytes() for path in (
            'spec/profile-policy-v2.toml', 'spec/profile-limits-v2.toml',
            'spec/damage-policy-v2.toml'))
        decoder = ObservationDecoderV2(*owners)
        side, raw = old_decoder._parse_bits(self.image.carrier)
        if overrides:
            raw = bytearray(raw)
            for flat, value in overrides.items():
                raw[flat] = 2 if value is None else value
            raw = bytes(raw)
        cells = old_decoder._Cells(raw, side)
        route = decoder._parse_route(cells, self.plan.width, 0)
        self.assertIsNotNone(route)
        observations = decoder._extract_units(cells, route.profile, route.shell_width, route.mapping)
        return decoder, route, observations

    def test_operational_one_path_bootstrap_roster_and_catalog_schedule(self):
        decoder, route, observations = self.operational_path()
        events, results = [], []
        invoke = decoder._invoke_recovery
        inventory = decoder._recover_inventory_v7
        def traced_invoke(rid, inputs, **options):
            result = invoke(rid, inputs, **options)
            events.append(rid)
            results.append((rid, inputs, result))
            return result
        def admitted_inventory(*args):
            result = inventory(*args)
            self.assertEqual(result, (self.plan.inventory, self.sections[1][2]))
            events.append('inventory-admitted')
            return result
        with (patch.object(decoder, '_invoke_recovery', side_effect=traced_invoke),
              patch.object(decoder, '_recover_inventory_v7', side_effect=admitted_inventory),
              patch.object(decoder._meter, 'invoke', wraps=decoder._meter.invoke) as charged):
            result = decoder._recover_route_sections(route, observations)
        self.assertEqual(result.artifact_state, 'exact')
        self.assertTrue(result.inventory_available)
        self.assertEqual({row.section_id: row.envelope for row in result.section_results},
                         {sid: row[2] for sid, row in self.sections.items()})
        inventory_groups = self.sections[1][1]
        groups = tuple(self.source_groups)
        self.assertEqual(events, [127, *([120]*(len(inventory_groups)-1)),
            'inventory-admitted', *([123]*len(groups)), *([120]*len(groups))])
        by_key = {identity(block): (first, block) for first, (_, block) in self.source_groups.items()}
        for rid, inputs, recovered in results:
            self.assertEqual(recovered.status, 0)
            if rid in (120, 127):
                block = self.source_groups[1][1] if rid == 127 else by_key[inputs[2]][1]
                self.assertEqual(recovered.outputs, (b'\2', b'\1', block))
            else:
                first = int.from_bytes(inputs[2], 'big')
                factor, block = self.source_groups[first]
                self.assertEqual(inputs[:2], (self.inventory_raw.ljust(16384, b'\0'),
                    len(self.inventory_raw).to_bytes(2, 'big')))
                self.assertEqual(recovered.outputs, (bytes((factor,)), first.to_bytes(4, 'big'),
                    (first+factor-1).to_bytes(4, 'big'), identity(block), self.plan.units.to_bytes(4, 'big')))
        calls = [tuple(call.args[:2]) for call in charged.call_args_list]
        for rid, count in ((127, 1), (123, len(groups)), (120, len(groups))):
            recipe = self.recipes[rid]
            self.assertEqual(calls.count((recipe.primitive_steps, recipe.peak_live_scratch_bytes)), count)
        # First bootstrap127 and catalog120 differ. Later inventory120 calls
        # are reevaluated during catalog traversal but share their one charge.
        self.assertEqual(sum(rid == 120 for rid, _, _ in results),
                         len(groups)+len(inventory_groups)-1)
        self.assertIsNone(decoder._current_package)
        self.assertIsNone(decoder._recovery_handle)

    def test_operational_resource_failure_stops_before_inventory(self):
        decoder, route, observations = self.operational_path()
        def resource_failure(handle, rid, inputs):
            self.assertEqual(rid, 127)
            return bootstrap.RecipeResult(11, ())
        with (patch.object(m2_recovery_recipe_v2.RecoveryExecution, 'evaluate', resource_failure),
              patch.object(decoder, '_decode_inventory_payload', wraps=decoder._decode_inventory_payload) as inventory,
              patch.object(decoder._meter, 'invoke', wraps=decoder._meter.invoke) as charged):
            with self.assertRaises(old_decoder.DecoderError) as caught:
                decoder._recover_route_sections(route, observations)
        self.assertEqual(caught.exception.reason, 'resource-limit')
        inventory.assert_not_called()
        self.assertEqual([call.args for call in charged.call_args_list],
                         [(self.recipes[127].primitive_steps, self.recipes[127].peak_live_scratch_bytes)])
        self.assertIsNone(decoder._current_package)

    def test_operational_foreign_candidate_cannot_supply_a_section(self):
        first = self.selected[1]
        factor, source = self.source_groups[first]
        self.assertEqual(factor, 1)
        foreign = self.source_groups[first+1][1]
        self.assertNotEqual(identity(foreign), identity(source))
        edits = {}
        self.replace_lane(edits, first, foreign)
        decoder, route, observations = self.operational_path(edits)
        witnessed = []
        invoke = decoder._invoke_recovery
        def traced_invoke(rid, inputs, **options):
            result = invoke(rid, inputs, **options)
            if rid == 120 and inputs[2] == identity(source):
                witnessed.append(result)
            return result
        with patch.object(decoder, '_invoke_recovery', side_effect=traced_invoke):
            result = decoder._recover_route_sections(route, observations)
        self.assertEqual(witnessed, [bootstrap.RecipeResult(0, (b'\2', b'\0', foreign))])
        section_id = int.from_bytes(source[4:8], 'big')
        section = next(row for row in result.section_results if row.section_id == section_id)
        self.assertEqual((section.state, section.envelope), ('corrupt', None))
        diagnostic = next(row for row in result.fragment_diagnostics if row.input_id == first)
        self.assertEqual((diagnostic.section_id, diagnostic.fragment_index, diagnostic.state,
            diagnostic.common_block), (section_id, int.from_bytes(source[16:18], 'big'), 'verified', foreign))

    @unittest.skipUnless(os.environ.get('GB_M2_RECOVERY_TRANSFER_GENERIC') == '1',
                         'explicit generic source-carrier transfer chain')
    def test_actual_generic_roster_map_and_group_with_erased_member_headers(self):
        first = self.selected[5]
        actual = self.recover(first+4, self.erased_headers(first), generic=True)
        self.assertEqual(actual, bootstrap.RecipeResult(0,
            (b'\3', b'\1', self.source_groups[first][1])))


if __name__ == '__main__':
    unittest.main()
