from dataclasses import FrozenInstanceError, replace
from copy import deepcopy
from pathlib import Path
import os
import tomllib
import unittest
from unittest.mock import patch

from golden_board import bootstrap, m2_codec, m2_recipe, recipe_wire_v1, recipe_wire_v2
from golden_board.m2_body_recipe_v1 import BodyRecipeProgramV1
from golden_board.m2_revision_recipe import build_revision_recipe_package, _encode_profile8_package
from golden_board import m2_recovery_recipe_v2 as recovery


def source_package():
    old = recipe_wire_v1.decode_recipe_package_v1(build_revision_recipe_package(), 8).logical
    bodies = tuple(BodyRecipeProgramV1(r.recipe_id,
        tuple((d.value_type, d.width) for d in r.inputs),
        tuple((d.value_type, d.width) for d in r.outputs),
        tuple((n.opcode, n.output_type, n.output_width, n.arguments,
               n.auxiliary_u16, n.immediate_u64) for n in r.nodes)) for r in old.recipes)
    tables = tuple(m2_recipe._table_record(t.table_id, t.element_type,
        t.element_width, t.element_count, t.payload) for t in old.tables)
    raw = _encode_profile8_package(tuple(sorted(bodies + recovery.recovery_programs(),
        key=lambda p: p.recipe_id)), tables + recovery.recovery_tables())
    return recipe_wire_v1.decode_recipe_package_v1(raw, 8)


def inventory():
    # A small raw traversal fixture; full inventory admission is a separate
    # precondition and is deliberately not asserted by these cursor tests.
    rows = []
    for sid, kind, factor, size in ((1, 1, 5, 68), (2, 2, 2, 157), (3, 3, 1, 1)):
        rows.append(sid.to_bytes(4, 'big') + kind.to_bytes(2, 'big') + b'\0\2'
                    + bytes((0, 1, 1, 2*factor)) + bytes(2)
                    + size.to_bytes(4, 'big') + bytes(2))
    return b'\0\2\0\3\0\0\0\x40' + b''.join(rows)


def common(value=b'A', copy=0, version=0):
    return bootstrap.encode_common_block(bootstrap.CommonBlock(8, 400, copy, 3,
        version, 0, 1, 24, value * 24))


def identity(block):
    return block[:2] + block[4:14] + block[16:20] + block[22:26]


def pair(block, flips=(), erasures=()):
    encoded, mask = bytearray(m2_codec.eh72_encode_unit(block)), bytearray(216)
    for bit in flips:
        encoded[bit//8] ^= 128 >> (bit % 8)
    for bit in erasures:
        mask[bit//8] |= 128 >> (bit % 8)
        encoded[bit//8] &= 255 ^ (128 >> (bit % 8))
    return bytes(encoded + mask)


def group_inputs(factor, lanes, key):
    return (bytes((factor,)), bytes((sum(1 << i for i, lane in enumerate(lanes)
                                      if lane is not None),)), key,
            *(lane or bytes(432) for lane in lanes), *(bytes(432),) * (5-len(lanes)))


class RecoverySource(unittest.TestCase):
    def test_runtime_logical_reference_matches_every_source_program_and_table(self):
        self.assertEqual(recovery.recovery_programs(), recovery._reference_programs())
        self.assertEqual(recovery.recovery_tables(), recovery._reference_tables())
        source = deepcopy(recovery._source())
        source['recipes'][0]['nodes'][0][-1] ^= 1
        with patch.object(recovery, '_source', return_value=source):
            with self.assertRaisesRegex(ValueError, 'reference-drift'):
                recovery.recovery_programs()

    def test_closed_source_shape_and_bounds(self):
        self.assertEqual(tuple(p.recipe_id for p in recovery.recovery_programs()), tuple(range(114, 128)))
        self.assertEqual(len(recovery.recovery_tables()), 5)
        path = Path(recovery.__file__).resolve().parents[2] / 'spec/recovery-program-v2.toml'
        raw = path.read_bytes()
        fixture_payload = tomllib.loads(raw.decode('utf-8'))['tables'][1]['payload'].encode('ascii')
        for changed in (raw.replace(b'version = 1', b'version = true', 1),
                        raw + b'\n[unowned]\nvalue = 1\n',
                        raw.replace(b'id = 114', b'id = 113', 1),
                        raw.replace(b'd3916ac47208be5f', b'd3916ac47208be5e', 1),
                        raw.replace(fixture_payload, b'1'+fixture_payload[1:], 1),
                        b' ' * 262145):
            with self.subTest(prefix=changed[:35]), patch.object(Path, 'open',
                    return_value=__import__('io').BytesIO(changed)):
                with self.assertRaises(ValueError):
                    recovery.recovery_programs()


class ScopedRecoveryExecution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logical = source_package().logical
        cls.package = recipe_wire_v2.decode_recipe_package_v2(
            recipe_wire_v2.encode_recipe_package_v2(logical.encoded, 8), 8)

    def test_admission_reparses_bytes_and_checks_roots_only_once(self):
        forged = replace(self.package, logical=replace(self.package.logical, recipes=()))
        with patch.object(recovery, 'recovery_program_refined', wraps=recovery.recovery_program_refined) as check:
            execution = recovery.admit_recovery_programs(forged, (120, 123, 127))
            self.assertEqual(check.call_count, 3)
            block = common()
            inputs = group_inputs(1, (pair(block),), identity(block))
            expected = bootstrap.RecipeResult(0, (b'\2', b'\1', block))
            with patch.object(recipe_wire_v2, 'decode_recipe_package_v2', side_effect=AssertionError('repeat parse')):
                self.assertEqual(execution.evaluate(120, inputs), expected)
                self.assertEqual(execution.evaluate(120, inputs), expected)
            self.assertEqual(check.call_count, 3)
        with self.assertRaises(FrozenInstanceError):
            execution._roots = (126,)

    def test_admitted_roots_and_typed_input_behavior_remain_closed(self):
        for roots in ((), (120,120), (125,), (999,), (True,), (120.0,), tuple(range(119,127))):
            with self.subTest(roots=roots), self.assertRaises(ValueError):
                recovery.admit_recovery_programs(self.package, roots)
        execution = recovery.admit_recovery_programs(self.package, (120,))
        for rid in (119,123,126,127,120.0):
            with self.subTest(rid=rid), self.assertRaises(ValueError):
                execution.evaluate(rid, ())
        with self.assertRaises(bootstrap.BootstrapReject):
            execution.evaluate(120, ())
        with self.assertRaises(TypeError):
            execution.evaluate(120, b'')
        block = common()
        valid = group_inputs(1, (pair(block),), identity(block))
        malformed = (b'\3', *valid[1:])
        self.assertEqual(execution.evaluate(120, malformed), bootstrap.RecipeResult(3, ()))

    def test_root_materialization_stops_at_one_excess(self):
        visited = []
        def roots():
            for index in range(100):
                visited.append(index)
                yield 120
        with self.assertRaisesRegex(ValueError, 'recovery-native-roots'):
            recovery.admit_recovery_programs(self.package, roots())
        self.assertEqual(visited, list(range(8)))

    def test_cold_scoped_admission_needs_no_runtime_files(self):
        recovery._neutral_baseline.cache_clear()
        build_revision_recipe_package.cache_clear()
        block = common()
        inputs = group_inputs(1, (pair(block),), identity(block))
        with (patch('builtins.open', side_effect=AssertionError('runtime source read')),
              patch('io.open', side_effect=AssertionError('runtime path read')),
              patch('os.open', side_effect=AssertionError('runtime descriptor read'))):
            execution = recovery.admit_recovery_programs(
                self.package, (119, 120, 122, 123, 124, 126, 127))
            self.assertEqual(execution.evaluate(120, inputs),
                             bootstrap.RecipeResult(0, (b'\2', b'\1', block)))

    def test_mutated_retained_closure_rejects_and_unrelated_table_does_not(self):
        for tid, roots, accepted in ((23, (120,), False), (27, (126,), False), (27, (120,), True)):
            raw = bytearray(self.package.logical.encoded)
            at = 64
            for table in self.package.logical.tables:
                if table.table_id == tid:
                    raw[at+16] ^= 1
                at += 16+len(table.payload)
            wire = recipe_wire_v2.encode_recipe_package_v2(bytes(raw), 8)
            forged = replace(self.package, encoded=wire)
            with self.subTest(table=tid, roots=roots):
                if accepted:
                    recovery.admit_recovery_programs(forged, roots)
                else:
                    with self.assertRaisesRegex(ValueError, 'unrefined-closure'):
                        recovery.admit_recovery_programs(forged, roots)
        for encoded in (b'bad', bytearray(self.package.encoded), build_revision_recipe_package()):
            with self.subTest(prefix=encoded[:10]), self.assertRaises(ValueError):
                recovery.admit_recovery_programs(replace(self.package, encoded=encoded), (120,))

    def test_strict_per_call_api_still_checks_structural_admission(self):
        block = common()
        inputs = group_inputs(1, (pair(block),), identity(block))
        execution = recovery.admit_recovery_programs(self.package, (120,))
        with patch.object(recovery, 'recovery_program_refined', return_value=False):
            self.assertEqual(execution.evaluate(120, inputs).outputs, (b'\2', b'\1', block))
            with self.assertRaisesRegex(ValueError, 'unrefined-closure'):
                recovery.evaluate_recovery_native(self.package, 120, inputs)


class RecoveryNative(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = source_package()

    def parity(self, rid, inputs):
        native = recovery.evaluate_recovery_native(self.package, rid, inputs)
        generic = bootstrap._evaluate_validated_recipe(self.package.logical, rid, inputs)
        self.assertEqual(native, generic)
        return native

    def test_cold_reference_and_native_dispatch_need_no_runtime_files(self):
        recovery._neutral_baseline.cache_clear()
        build_revision_recipe_package.cache_clear()
        with (patch('builtins.open', side_effect=AssertionError('runtime source read')),
              patch('io.open', side_effect=AssertionError('runtime path read')),
              patch('os.open', side_effect=AssertionError('runtime descriptor read'))):
            for rid in (119, 120, 122, 123, 124, 126, 127):
                self.assertTrue(recovery.recovery_program_refined(self.package, rid))
            inputs, expected = self.construction_expected(5)
            self.assertEqual(recovery.evaluate_recovery_native(self.package, 126, inputs), expected)

    def test_closure_checks_transitive_nodes_tables_resources_and_duplicates(self):
        for rid in (119, 120, 122, 123, 124):
            self.assertTrue(recovery.recovery_program_refined(self.package, rid))
        for changed in (1, 3, 4, 90, 92, 114, 115, 116, 117, 118, 119, 120):
            recipes = tuple(replace(r, nodes=(replace(r.nodes[0], immediate_u64=
                r.nodes[0].immediate_u64 ^ 1), *r.nodes[1:])) if r.recipe_id == changed else r
                for r in self.package.logical.recipes)
            mutant = replace(self.package, logical=replace(self.package.logical, recipes=recipes))
            self.assertFalse(recovery.recovery_program_refined(mutant, 120), changed)
        for tid in (3, 4, 5, 10, 11, 12, 13, 14, 15, 18, 23):
            tables = tuple(replace(t, payload=bytes((t.payload[0] ^ 1,)) + t.payload[1:])
                           if t.table_id == tid else t for t in self.package.logical.tables)
            mutant = replace(self.package, logical=replace(self.package.logical, tables=tables))
            self.assertFalse(recovery.recovery_program_refined(mutant, 120), tid)
        recipes = tuple(replace(r, primitive_steps=r.primitive_steps-1)
                        if r.recipe_id == 119 else r for r in self.package.logical.recipes)
        mutant = replace(self.package, logical=replace(self.package.logical, recipes=recipes))
        self.assertFalse(recovery.recovery_program_refined(mutant, 120))
        with self.assertRaises(ValueError):
            recovery.evaluate_recovery_native(mutant, 120, ())
        duplicate = replace(self.package, logical=replace(self.package.logical,
            recipes=self.package.logical.recipes + (self.package.logical.recipes[-1],)))
        self.assertFalse(recovery.recovery_program_refined(duplicate, 120))
        for changed, root in ((121, 123), (122, 123), (123, 123), (124, 124)):
            recipes = tuple(replace(r, peak_live_scratch_bytes=r.peak_live_scratch_bytes+1)
                            if r.recipe_id == changed else r for r in self.package.logical.recipes)
            mutant = replace(self.package, logical=replace(self.package.logical, recipes=recipes))
            self.assertFalse(recovery.recovery_program_refined(mutant, root))
        missing = tuple(t for t in self.package.logical.tables if t.table_id != 17)
        mutant = replace(self.package, logical=replace(self.package.logical, tables=missing))
        self.assertFalse(recovery.recovery_program_refined(mutant, 124))
        # Unrelated valid programs need not match this particular closure.
        recipes = tuple(r for r in self.package.logical.recipes if r.recipe_id != 202)
        self.assertTrue(recovery.recovery_program_refined(
            replace(self.package, logical=replace(self.package.logical, recipes=recipes)), 120))

    def test_mapping_valid_and_invalid_domains(self):
        for row in ((2048, 112, 1, 0), (2048, 128, 100, 1727), (512, 32, 90, 72),
                    (0, 0, 1, 0), (64, 8, 1, 0), (65535, 65535, 1, 65535),
                    (2048, 112, 0xffffffff, 0), (2048, 112, 1, 1728)):
            with self.subTest(row=row):
                self.parity(124, tuple(v.to_bytes(n, 'big') for v, n in zip(row, (2, 2, 4, 2))))

    def test_roster_complete_state_and_rejections(self):
        raw = inventory()
        for target in (1, 5, 6, 9, 10, 11, 0, 0xffffffff):
            with self.subTest(target=target):
                self.parity(123, (raw.ljust(16384, b'\0'), len(raw).to_bytes(2, 'big'),
                                  target.to_bytes(4, 'big')))
        state = bytearray(b'\xff' * 16431)
        state[:16384] = raw.ljust(16384, b'\0')
        state[16384:16386] = len(raw).to_bytes(2, 'big')
        state[16396:16400] = (9).to_bytes(4, 'big')
        result = self.parity(122, (bytes(state), b'\xff' * 8))
        self.assertEqual(result.status, 0)
        self.assertEqual(result.outputs[0][:16384], state[:16384])
        for at, bad in ((0, b'\0\1'), (2, b'\xff\xff'), (19, b'\x06'),
                        (20, b'\xff\xff'), (28, bytes(4)), (42, b'\xff'*4)):
            changed = bytearray(raw)
            changed[at:at+len(bad)] = bad
            with self.subTest(at=at):
                self.assertEqual(self.parity(123, (bytes(changed).ljust(16384, b'\0'),
                    len(raw).to_bytes(2, 'big'), (1).to_bytes(4, 'big'))).status, 3)

    def test_native_input_types_are_vm_input_errors(self):
        for rid, inputs in ((120, ()), (124, (bytes(2), bytes(2), bytes(3), bytes(2)))):
            with self.assertRaises(bootstrap.BootstrapReject):
                recovery.evaluate_recovery_native(self.package, rid, inputs)
        for inputs in (b'', None, (bytearray(2), bytes(2), bytes(4), bytes(2))):
            with self.assertRaises(TypeError):
                recovery.evaluate_recovery_native(self.package, 124, inputs)

    def test_group_local_result_identity_and_full_kernel_state(self):
        block = common(copy=1, version=9)
        inputs = group_inputs(1, (pair(block),), identity(common()))
        result = recovery.evaluate_recovery_native(self.package, 120, inputs)
        self.assertEqual(result, bootstrap.RecipeResult(0, (b'\2', b'\0', block)))
        state = b''.join(inputs) + b'\xff' * (4096-2182)
        result = recovery.evaluate_recovery_native(self.package, 119, (state, b'\xff'*8))
        expected = bytearray(4096)
        expected[2806:2997] = block
        expected[3010] = 2
        self.assertEqual(result, bootstrap.RecipeResult(0, (bytes(expected),)))

    def test_group_repetition_conflict_erasure_and_canonicality(self):
        a, b = common(), common(b'B')
        cases = [
            (group_inputs(5, (None,)*5, identity(a)), 0, 0, bytes(191)),
            (group_inputs(1, (pair(a, flips=(0,)),), identity(a)), 3, 1, a),
            (group_inputs(1, (pair(a, erasures=(0, 1, 2)),), identity(a)), 3, 1, a),
            (group_inputs(1, (pair(a, erasures=(0, 1, 2, 3)),), identity(a)), 1, 0, bytes(191)),
            (group_inputs(5, tuple(pair(b, flips=(2*i, 2*i+1)) for i in range(5)), identity(b)), 3, 1, b),
            (group_inputs(5, (pair(a), pair(b), None, None, None), identity(a)), 4, 0, bytes(191)),
            (group_inputs(2, (pair(a), None), identity(a)), 2, 1, a),
        ]
        for inputs, state, accepted, block in cases:
            result = recovery.evaluate_recovery_native(self.package, 120, inputs)
            self.assertEqual(result, bootstrap.RecipeResult(0, (bytes((state,)), bytes((accepted,)), block)))
        valid = group_inputs(1, (pair(a),), identity(a))
        hidden = bytearray(pair(a, erasures=(0,)))
        hidden[0] |= 128
        malformed = [
            (b'\3', *valid[1:]), (valid[0], b'\x80', *valid[2:]),
            (valid[0], b'\0', *valid[2:]),
            (*valid[:3], bytes(hidden), *valid[4:]),
        ]
        for inputs in malformed:
            self.assertEqual(recovery.evaluate_recovery_native(self.package, 120, inputs),
                             bootstrap.RecipeResult(3, ()))

    def construction_expected(self, case):
        physical = 11 if case == 7 else 6
        sid, factor = (401, 2) if case == 7 else (400, 5)
        key = (b'\0\10' + sid.to_bytes(4, 'big') + b'\0\0\0\4\0\0\0\0\0\1'
               + (23).to_bytes(4, 'big'))
        local = (0, 1, 2, 3, 4, 3, 3, 2)[case]
        accepted = (0, 0, 1, 1, 0, 1, 1, 0)[case]
        envelope = bytes(23) if case in (0, 1, 4) else bootstrap.encode_section_envelope(
            bootstrap.SectionEnvelope(400, 4, 0, 129, 1, (), bytes((int(case == 5),))))
        inputs = (physical.to_bytes(4, 'big'), bytes((case,)))
        expected = bootstrap.RecipeResult(0, (physical.to_bytes(4, 'big'), bytes((factor,)),
            key, bytes((local,)), bytes((accepted,)), envelope))
        return inputs, expected

    def test_construction_all_eight_and_rejections(self):
        for case in range(8):
            inputs, expected = self.construction_expected(case)
            with self.subTest(case=case):
                self.assertEqual(recovery.evaluate_recovery_native(self.package, 126, inputs), expected)
        for target, case in ((10, 2), (12, 7)):
            _, expected = self.construction_expected(case)
            # Querying any member returns the derived first group member.
            self.assertEqual(recovery.evaluate_recovery_native(self.package, 126,
                (target.to_bytes(4, 'big'), bytes((case,)))), expected)
        # Lookup failure, constructor-domain failure, and populated lane outside
        # the inventory-derived factor all suppress every staged output.
        for target, case in ((0, 0), (13, 0), (0xffffffff, 0), (6, 8), (6, 255),
                             (11, 4), (12, 5), (11, 6)):
            inputs = (target.to_bytes(4, 'big'), bytes((case,)))
            self.assertEqual(self.parity(126, inputs), bootstrap.RecipeResult(3, ()))

    def test_construction_requires_every_table_template_and_constructor(self):
        self.assertTrue(recovery.recovery_program_refined(self.package, 126))
        for tid in (24, 25, 26, 27):
            tables = tuple(replace(t, payload=bytes((t.payload[0] ^ 1,)) + t.payload[1:])
                           if t.table_id == tid else t for t in self.package.logical.tables)
            mutant = replace(self.package, logical=replace(self.package.logical, tables=tables))
            self.assertFalse(recovery.recovery_program_refined(mutant, 126))
        for rid in (119, 121, 122, 125, 126):
            recipes = tuple(replace(r, nodes=(replace(r.nodes[0], immediate_u64=
                r.nodes[0].immediate_u64 ^ 1), *r.nodes[1:])) if r.recipe_id == rid else r
                for r in self.package.logical.recipes)
            mutant = replace(self.package, logical=replace(self.package.logical, recipes=recipes))
            self.assertFalse(recovery.recovery_program_refined(mutant, 126))

    def bootstrap_inputs(self, length=90, limit=2389, section=1, copy=0, version=2, index=0):
        count = (length+156)//157
        size = length-157*(count-1) if index+1 == count else 157
        block = bootstrap.encode_common_block(bootstrap.CommonBlock(8, section, copy, 1,
            version, index, count, length, bytes(size)))
        return (limit.to_bytes(4, 'big'), b'\1', pair(block), *(bytes(432),)*4), block

    def test_first_inventory_bootstrap_local_boundary_and_shape(self):
        self.assertTrue(recovery.recovery_program_refined(self.package, 127))
        for length in (22, 90, 16406):
            inputs, block = self.bootstrap_inputs(length=length)
            self.assertEqual(recovery.evaluate_recovery_native(self.package, 127, inputs),
                             bootstrap.RecipeResult(0, (b'\2', b'\1', block)))
        for fields in ({'length': 21}, {'length': 16407}, {'section': 2}, {'copy': 1},
                       {'version': 1}, {'length': 300, 'limit': 5}, {'length': 300, 'index': 1}):
            inputs, _ = self.bootstrap_inputs(**fields)
            self.assertEqual(recovery.evaluate_recovery_native(self.package, 127, inputs),
                             bootstrap.RecipeResult(0, (b'\2', b'\0', bytes(191))))
        for limit in (0, 4, 2390, 0xffffffff):
            inputs, _ = self.bootstrap_inputs(limit=limit)
            self.assertEqual(recovery.evaluate_recovery_native(self.package, 127, inputs),
                             bootstrap.RecipeResult(3, ()))
        inputs, _ = self.bootstrap_inputs()
        malformed = (inputs[0], b'\0', *inputs[2:])
        self.assertEqual(recovery.evaluate_recovery_native(self.package, 127, malformed),
                         bootstrap.RecipeResult(3, ()))
        missing = (inputs[0], b'\0', *(bytes(432),)*5)
        self.assertEqual(recovery.evaluate_recovery_native(self.package, 127, missing),
                         bootstrap.RecipeResult(0, (b'\0', b'\0', bytes(191))))
        for rid in (119, 127):
            recipes = tuple(replace(r, primitive_steps=r.primitive_steps+1)
                            if r.recipe_id == rid else r for r in self.package.logical.recipes)
            self.assertFalse(recovery.recovery_program_refined(
                replace(self.package, logical=replace(self.package.logical, recipes=recipes)), 127))

    @unittest.skipUnless(os.environ.get('GB_M2_RECOVERY_BOOTSTRAP_FULL') == '1',
                         'explicit generic first-inventory bootstrap differential corpus')
    def test_actual_generic_first_inventory_bootstrap(self):
        for fields in ({'length': 22}, {'length': 16406}, {'section': 2},
                       {'length': 300, 'limit': 5}, {'limit': 2390}):
            inputs, _ = self.bootstrap_inputs(**fields)
            self.parity(127, inputs)

    @unittest.skipUnless(os.environ.get('GB_M2_RECOVERY_CONSTRUCTION_FULL') == '1',
                         'explicit generic complete construction differential corpus')
    def test_actual_generic_construction_all_eight(self):
        for case in range(8):
            inputs, expected = self.construction_expected(case)
            with self.subTest(case=case):
                self.assertEqual(self.parity(126, inputs), expected)

    @unittest.skipUnless(os.environ.get('GB_M2_RECOVERY_REFINEMENT_FULL') == '1',
                         'explicit generic whole-group differential corpus')
    def test_actual_generic_whole_group_and_kernel(self):
        a, b = common(), common(b'B', copy=1, version=9)
        cases = (
            group_inputs(1, (pair(b),), identity(a)),
            group_inputs(5, tuple(pair(a, flips=(2*i, 2*i+1)) for i in range(5)), identity(a)),
            group_inputs(2, (pair(a), pair(b)), identity(a)),
            group_inputs(1, (pair(a, erasures=(0, 1, 2)),), identity(a)),
            group_inputs(1, (pair(a, erasures=(0, 1, 2, 3)),), identity(a)),
            group_inputs(5, (None,)*5, identity(a)),
        )
        for inputs in cases:
            self.parity(120, inputs)
        inputs = cases[0]
        state = b''.join(inputs) + b'\xff'*(4096-2182)
        self.parity(119, (state, b'\xff'*8))


if __name__ == '__main__':
    unittest.main()
