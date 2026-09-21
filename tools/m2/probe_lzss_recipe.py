#!/usr/bin/env python3
"""Private existing-opcode LZSS feasibility probe; never emits a carrier."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
import unittest

from golden_board import bootstrap
from golden_board.m2_recipe import _R3Body, _render_eh_recipe_package, _table_record

LIMIT = 16384
STATE_BYTES = 2 * LIMIT + 14
N, L, P, O, D, R, F, K, E = (2 * LIMIT + n for n in (0, 2, 4, 6, 8, 10, 11, 12, 13))
BODY, ENTRY, EXAMPLE = 201, 202, 203
ROOT = Path(__file__).resolve().parents[2]


class Body(_R3Body):
    def write(self, state, index, value):
        return self.add(20, bootstrap.BYTES, STATE_BYTES, (state, index, value))

    def iterate(self, state, body, count):
        return self.add(22, bootstrap.BYTES, STATE_BYTES, (state,), auxiliary=body, immediate=count)

    def u16(self, value):
        return self.uint(16, value)

    def u8(self, value):
        return self.uint(8, value)

    def add16(self, left, right):
        return self.binary(6, bootstrap.UINT, 16, left, right)

    def sub16(self, left, right):
        return self.binary(7, bootstrap.UINT, 16, left, right)

    def safe_input(self, index):
        # SELECT is eager: every speculative read must itself be bounded.
        safe = self.select(bootstrap.UINT, 16, self.less(index, self.u16(LIMIT)), index, self.u16(0))
        return self.read(1, safe)

    def all(self, *values):
        result = values[0]
        for value in values[1:]:
            result = self.bool_and(result, value)
        return result


def decoder_body():
    b = Body(BODY, ((bootstrap.BYTES, STATE_BYTES), (bootstrap.UINT, 64)),
             ((bootstrap.STATUS, 16), (bootstrap.BYTES, STATE_BYTES)))
    n, target, cursor, produced, distance = (b.read_uint(1, offset, 2) for offset in (N, L, P, O, D))
    remaining, flags, tokens, admitted = (b.read_fixed(1, offset) for offset in (R, F, K, E))
    active = b.less(produced, target)
    new_token = b.equal(remaining, b.u8(0))
    new_group = b.equal(tokens, b.u8(0))
    next_flags = b.select(bootstrap.UINT, 8, new_group, b.safe_input(cursor), flags)
    token_cursor = b.add16(cursor, b.select(bootstrap.UINT, 16, new_group, b.u16(1), b.u16(0)))
    first = b.safe_input(token_cursor)
    second = b.safe_input(b.add16(token_cursor, b.u16(1)))
    word = b.add(4, bootstrap.UINT, 16, (first, second))
    high_bit = b.add(14, bootstrap.UINT, 8, (next_flags,), immediate=128)
    copy = b.equal(high_bit, b.u8(128))
    new_distance = b.add16(b.binary(16, bootstrap.UINT, 16, word, b.u16(4)), b.u16(1))
    copy_length = b.binary(6, bootstrap.UINT, 8,
                           b.add(14, bootstrap.UINT, 8, (second,), immediate=15), b.u8(3))
    token_length = b.select(bootstrap.UINT, 8, copy, copy_length, b.u8(1))
    token_end = b.add16(token_cursor, b.select(bootstrap.UINT, 16, copy, b.u16(2), b.u16(1)))
    end_output = b.add16(produced, b.widen(token_length))
    good_token = b.all(b.less_or_equal(token_end, n), b.less_or_equal(end_output, target),
                       b.bool_or(b.bool_not(copy), b.less_or_equal(new_distance, produced)))
    good = b.all(b.equal(admitted, b.u8(1)),
                 b.bool_or(b.bool_not(active), b.bool_or(b.bool_not(new_token), good_token)))
    status = b.select(bootstrap.STATUS, 16, good, b.status(0), b.status(3))

    distance_used = b.select(bootstrap.UINT, 16, new_token, new_distance, distance)
    # The clamped subtraction also covers the eagerly evaluated literal branch.
    safe_produced = b.select(bootstrap.UINT, 16, b.less(produced, distance_used), distance_used, produced)
    source = b.add16(b.u16(LIMIT), b.sub16(safe_produced, distance_used))
    copy_byte = b.read(1, source)
    output_byte = b.select(bootstrap.UINT, 8, b.bool_or(b.bool_not(new_token), copy), copy_byte, first)
    updated = b.write(1, b.add16(b.u16(LIMIT), produced), output_byte)
    selected_cursor = b.select(bootstrap.UINT, 16, new_token, token_end, cursor)
    updated = b.write_uint(updated, P, 2, selected_cursor)
    updated = b.write_uint(updated, O, 2, b.add16(produced, b.u16(1)))
    updated = b.write_uint(updated, D, 2, distance_used)
    old_remaining_safe = b.select(bootstrap.UINT, 8, new_token, b.u8(1), remaining)
    old_remaining_next = b.binary(7, bootstrap.UINT, 8, old_remaining_safe, b.u8(1))
    new_remaining = b.binary(7, bootstrap.UINT, 8, token_length, b.u8(1))
    updated = b.write_fixed(updated, R, b.select(bootstrap.UINT, 8, new_token, new_remaining, old_remaining_next))
    shifted = b.binary(15, bootstrap.UINT, 8,
                       b.add(14, bootstrap.UINT, 8, (next_flags,), immediate=127), b.u8(1))
    updated = b.write_fixed(updated, F, b.select(bootstrap.UINT, 8, new_token, shifted, flags))
    available = b.select(bootstrap.UINT, 8, new_group, b.u8(8), tokens)
    next_tokens = b.binary(7, bootstrap.UINT, 8, available, b.u8(1))
    updated = b.write_fixed(updated, K, b.select(bootstrap.UINT, 8, new_token, next_tokens, tokens))
    updated = b.select(bootstrap.BYTES, STATE_BYTES, active, updated, 1)
    b.finish_body(status, updated)
    return b


def initialize(b, encoded, encoded_length, extra_admission=None):
    target = b.read_uint(encoded, 1, 2)
    good = b.all(b.less_or_equal(b.u16(3), encoded_length),
                 b.less_or_equal(encoded_length, b.u16(LIMIT)),
                 b.less_or_equal(target, b.u16(LIMIT)),
                 b.equal(b.read_fixed(encoded, 0), b.u8(3)))
    if extra_admission is not None:
        good = b.bool_and(good, extra_admission)
    state = b.add(4, bootstrap.BYTES, STATE_BYTES, (encoded, b.zero_bytes(LIMIT + 14)))
    state = b.write_uint(state, N, 2, encoded_length)
    state = b.write_uint(state, L, 2, target)
    state = b.write_fixed(state, P + 1, b.u8(3))
    state = b.write_fixed(state, E, b.select(bootstrap.UINT, 8, good, b.u8(1), b.u8(0)))
    return state, target


def finalize(b, state, encoded_length, target, output_length, include_length):
    good = b.all(b.equal(b.read_uint(state, P, 2), encoded_length),
                 b.equal(b.read_uint(state, O, 2), target),
                 b.equal(b.read_fixed(state, R), b.u8(0)),
                 b.equal(b.read_fixed(state, F), b.u8(0)))
    status = b.select(bootstrap.STATUS, 16, good, b.status(0), b.status(3))
    decoded = b.add(3, bootstrap.BYTES, output_length,
                    (state, b.u16(LIMIT), b.u16(output_length)))
    b.finish_outputs(status, (target, decoded) if include_length else (decoded,))


def decoder_entry():
    b = Body(ENTRY, ((bootstrap.BYTES, LIMIT), (bootstrap.UINT, 16)),
             ((bootstrap.STATUS, 16), (bootstrap.UINT, 16), (bootstrap.BYTES, LIMIT)))
    state, target = initialize(b, 1, 2)
    state = b.iterate(state, BODY, LIMIT)
    finalize(b, state, 2, target, LIMIT, True)
    return b


def example_entry():
    # An existing-opcode construction: header + tiny body + zero padding.
    # No host decoder or host token iteration is involved.
    b = Body(EXAMPLE, ((bootstrap.BYTES, 9), (bootstrap.UINT, 16)),
             ((bootstrap.STATUS, 16), (bootstrap.BYTES, 8)))
    header = b.zero_bytes(3)
    header = b.add(20, bootstrap.BYTES, 3, (header, b.u16(0), b.u8(3)))
    header = b.add(20, bootstrap.BYTES, 3, (header, b.u16(2), b.u8(8)))
    prefix = b.add(4, bootstrap.BYTES, 12, (header, 1))
    encoded = b.add(4, bootstrap.BYTES, LIMIT, (prefix, b.zero_bytes(LIMIT - 12)))
    length_good = b.less_or_equal(2, b.u16(9))
    safe_length = b.select(bootstrap.UINT, 16, length_good, 2, b.u16(0))
    encoded_length = b.add16(safe_length, b.u16(3))
    state, target = initialize(b, encoded, encoded_length, length_good)
    state = b.iterate(state, BODY, 8)
    finalize(b, state, encoded_length, target, 8, False)
    return b


def build_package():
    tables = (
        _table_record(3, bootstrap.UINT, 16, 256, b"".join(n.to_bytes(2, "big") for n in range(256))),
        _table_record(4, bootstrap.BYTES, 1, 1, b"\0"),
        _table_record(5, bootstrap.UINT, 8, 256, bytes(range(256))),
    )
    return _render_eh_recipe_package(7, (decoder_body(), decoder_entry(), example_entry()), tables)


class RecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = bootstrap.decode_recipe_package(build_package(), 7)

    def test_tiny_literal_and_overlap(self):
        for encoded, length, expected in (
            (b"\0" + b"12345678", 9, b"12345678"),
            (b"\x40A\0\x04" + bytes(5), 4, b"AAAAAAAA"),
        ):
            result = bootstrap.evaluate_recipe(self.package, 203, (encoded, length.to_bytes(2, "big")))
            self.assertEqual((result.status, result.outputs), (0, (expected,)))

    def test_tiny_malformed_is_atomic(self):
        for encoded, length in (
            (bytes(9), 0),
            (b"\x80\0\x05" + bytes(6), 3),
            (b"\x40A\0" + bytes(6), 3),
            (b"\x40A\0\x05" + bytes(5), 4),
            (b"\x40A\0\x14" + bytes(5), 4),
            (b"\x41A\0\x04" + bytes(5), 4),
            (b"\x40A\0\x04" + bytes(5), 5),
            (b"\0" + b"12345678", 8),
            (b"\0" + b"12345678", 10),
            (b"\0" + b"12345678", 65535),
        ):
            result = bootstrap.evaluate_recipe(self.package, 203, (encoded, length.to_bytes(2, "big")))
            self.assertEqual(result.status, 3)
            self.assertEqual(result.outputs, ())

    def test_header_bounds_are_atomic(self):
        for prefix, length in (
            (bytes(3), 0), (bytes(3), 1), (bytes(3), 2),
            (b"\x02\0\x08", 12), (b"\x03\x40\x01", 3),
            (b"\x03\xff\xff", 3), (b"\x03\0\0", 16385),
            (b"\x03\0\0", 65535),
        ):
            result = bootstrap.evaluate_recipe(self.package, ENTRY,
                (prefix + bytes(LIMIT - len(prefix)), length.to_bytes(2, "big")))
            self.assertEqual((result.status, result.outputs), (3, ()))

    def test_vm_arithmetic_failure_remains_status11(self):
        state = bytearray(STATE_BYTES)
        state[E] = 1
        state[L:L+2] = b"\xff\xff"
        state[O:O+2] = b"\xff\xff"
        result = bootstrap.evaluate_recipe(self.package, BODY, (bytes(state), bytes(8)))
        self.assertEqual((result.status, result.outputs), (11, ()))

    def test_padding_is_outside_declared_input(self):
        raw = b"\x40A\0\x04" + b"\xff" * 5
        result = bootstrap.evaluate_recipe(self.package, EXAMPLE, (raw, b"\0\x04"))
        self.assertEqual((result.status, result.outputs), (0, (b"AAAAAAAA",)))

    def test_distance_4096_and_overlap_in_actual_body(self):
        # Direct body probes isolate extreme-distance and second-byte overlap.
        # The complete entrypoint is independently exercised by --measure.
        for produced, distance, remaining, expected in ((4096, 4096, 0, 0xA9), (2, 1, 6, 0xA9)):
            state = bytearray(STATE_BYTES)
            state[:6] = b"\x03\x10\x03\x80\xff\xf0"
            state[LIMIT] = 0xA9
            for offset, value in ((N, 6), (L, produced + 3), (P, 3), (O, produced), (D, distance)):
                state[offset:offset+2] = value.to_bytes(2, "big")
            if remaining:
                state[:7] = b"\x03\0\x08\x40\xa9\0\x04"
                state[LIMIT:LIMIT+2] = b"\xa9\xa9"
                state[N:N+2] = b"\0\x07"
                state[L:L+2] = b"\0\x08"
                state[P:P+2] = b"\0\x07"
                state[K] = 6
            state[R] = remaining
            state[E] = 1
            result = bootstrap.evaluate_recipe(self.package, BODY, (bytes(state), bytes(8)))
            self.assertEqual(result.status, 0)
            self.assertEqual(result.outputs[0][LIMIT + produced], expected)
            self.assertEqual(int.from_bytes(result.outputs[0][O:O+2], "big"), produced + 1)

    def test_bounded_existing_operations_and_exact_projection(self):
        self.assertTrue(all(1 <= n.opcode <= 25 for r in self.package.recipes for n in r.nodes))
        self.assertEqual(self.package.total_node_count, 374)
        self.assertEqual(self.package.maximum_primitive_steps, 2375776)
        self.assertEqual(self.package.peak_live_scratch_bytes, 98398)
        self.assertEqual(sum(compact_recipe_size(r) for r in self.package.recipes), 4576)

    def test_actual_compact_wire_roundtrip_and_execution(self):
        compact, metadata = compact_check(self.package)
        self.assertEqual(len(compact), 5457)
        self.assertTrue(metadata["exact_logical_roundtrip"])
        self.assertEqual(metadata["example_status"], 0)


def compact_recipe_size(recipe):
    """Exact opcode-specific development wire size, without creating v1 bytes."""
    node_bytes = sum(6 + 2 * len(n.arguments)
                     + 2 * (n.opcode in (2, 5, 22))
                     + 8 * (n.opcode in (1, 5, 14, 22, 25)) for n in recipe.nodes)
    return 32 + 12 * (len(recipe.inputs) + len(recipe.outputs)) + node_bytes


def compact_check(package):
    from golden_board.recipe_wire_v1 import (
        decode_recipe_package_v1, encode_recipe_package_v1,
        evaluate_recipe_v1, expand_recipe_package_v1,
    )
    compact = encode_recipe_package_v1(package.encoded, 7)
    if expand_recipe_package_v1(compact, 7) != package.encoded:
        raise AssertionError("compact logical roundtrip")
    projected = 64 + sum(16 + len(t.payload) for t in package.tables)
    projected += sum(compact_recipe_size(r) for r in package.recipes)
    if len(compact) != projected:
        raise AssertionError("compact measured size differs from independent projection")
    decoded = decode_recipe_package_v1(compact, 7)
    result = evaluate_recipe_v1(decoded, EXAMPLE, (b"\x40A\0\x04"+bytes(5), b"\0\x04"))
    if result.status != 0 or result.outputs != (b"AAAAAAAA",):
        raise AssertionError("compact public execution")
    return compact, {"bytes": len(compact), "sha256": hashlib.sha256(compact).hexdigest(),
                     "exact_logical_roundtrip": True, "example_status": result.status}


def _tokens(tokens, expected):
    """Construct diagnostic encodings; expected bytes are supplied independently."""
    output = bytearray(b"\x03" + len(expected).to_bytes(2, "big"))
    for start in range(0, len(tokens), 8):
        group = tokens[start:start+8]
        flags = sum(1 << (7 - i) for i, token in enumerate(group) if len(token) == 2)
        output.append(flags)
        output.extend(b"".join(group))
    return bytes(output)


def _copy(distance, length):
    assert 1 <= distance <= 4096 and 3 <= length <= 18
    return (((distance - 1) << 4) | (length - 3)).to_bytes(2, "big")


def _maximum_vectors():
    prefix = bytes((17 * i + i // 256) % 256 for i in range(4096))
    expected = prefix + prefix[:18] + b"\0"
    tokens = [bytes((value,)) for value in prefix] + [_copy(4096, 18), b"\0"]
    remaining = LIMIT - len(expected)
    while remaining:
        amount = min(18, remaining)
        tokens.append(_copy(1, amount) if amount >= 3 else b"\0")
        remaining -= amount if amount >= 3 else 1
    full_output = expected + bytes(LIMIT - len(expected))
    maximum_decoded = _tokens(tokens, full_output)
    full_input_output = b"A" * 14562
    maximum_encoded = _tokens([b"A"] * 14559 + [_copy(1, 3)], full_input_output)
    assert len(maximum_encoded) == LIMIT
    return (
        ("maximum-decoded-with-distance4096-and-overlap", maximum_decoded, full_output),
        ("maximum-encoded-with-final-full-flag-group", maximum_encoded, full_input_output),
        ("empty-exact-header", b"\x03\0\0", b""),
    )


def _metrics(package):
    table_bytes = sum(16 + len(t.payload) for t in package.tables)
    recipes = [{"recipe_id": r.recipe_id, "nodes": len(r.nodes), "edges": r.edge_count,
                "v0_bytes": r.recipe_bytes, "compact_v1_bytes": compact_recipe_size(r),
                "primitive_steps": r.primitive_steps, "peak_scratch_bytes": r.peak_live_scratch_bytes,
                "inputs": [[d.value_type, d.width] for d in r.inputs],
                "outputs": [[d.value_type, d.width] for d in r.outputs]} for r in package.recipes]
    growth = sum(r["compact_v1_bytes"] for r in recipes)
    return {"status": "private feasibility only; no carrier or passing receipt",
            "state_bytes": STATE_BYTES, "recipes": recipes,
            "v0_package_bytes": len(package.encoded),
            "v0_sha256": hashlib.sha256(package.encoded).hexdigest(),
            "compact_v1_standalone_bytes": 64 + table_bytes + growth,
            "compact_v1_merged_increment_bytes": growth,
            "shared_table_ids": [t.table_id for t in package.tables],
            "table_bytes_with_headers": table_bytes,
            "node_count": package.total_node_count, "edge_count": package.total_edge_count,
            "max_primitive_steps": package.maximum_primitive_steps,
            "peak_scratch_bytes": package.peak_live_scratch_bytes,
            "all_recipe_ops": sorted({n.opcode for r in package.recipes for n in r.nodes}),
            "maximum_iterations": LIMIT,
            "full_entry_array_write_bytes_in_body": LIMIT * STATE_BYTES * 10,
            "limits": {"encoded_section": LIMIT, "decoded_section": LIMIT,
                       "package_bytes": bootstrap.RECIPE_PACKAGE_MAX,
                       "primitive_steps": bootstrap.RECIPE_STEP_MAX,
                       "scratch_bytes": bootstrap.RECIPE_SCRATCH_MAX},
            "route_accounting": {"compact_old_prefix_per_sector": 14825,
                                 "max_prefix_2048_w112": 25813,
                                 "recipe_growth_per_sector": growth,
                                 "positive_example_records_per_sector": 82,
                                 "subtotal_per_sector": 14825 + growth + 82,
                                 "remaining_per_sector_before_new_definitions_and_composition_grounding": 25813 - 14825 - growth - 82}}


def measure():
    package = bootstrap.decode_recipe_package(build_package(), 7)
    result = _metrics(package)
    compact, result["actual_compact_wire"] = compact_check(package)
    results = []
    for name, encoded, expected in _maximum_vectors():
        assert len(encoded) <= LIMIT and len(expected) <= LIMIT
        print(f"running {name}: encoded={len(encoded)}, decoded={len(expected)}", flush=True)
        started = time.monotonic()
        evaluated = bootstrap.evaluate_recipe(package, ENTRY,
            (encoded + bytes(LIMIT - len(encoded)), len(encoded).to_bytes(2, "big")))
        actual = (len(expected).to_bytes(2, "big"), expected + bytes(LIMIT-len(expected)))
        if evaluated.status != 0 or evaluated.outputs != actual:
            raise AssertionError((name, evaluated.status, "exact full padded output differs"))
        print(f"verified {name} in {time.monotonic()-started:.3f}s", flush=True)
        results.append({"name": name, "encoded_bytes": len(encoded), "decoded_bytes": len(expected),
                        "encoded_sha256": hashlib.sha256(encoded).hexdigest(),
                        "decoded_sha256": hashlib.sha256(expected).hexdigest(),
                        "status": evaluated.status, "exact_full_output_matches": True})
    result["full_entry_executions"] = results
    examples = []
    for sector in range(4):
        literal = bytes(range(ord("1")+sector, ord("1")+sector+8))
        repeated = bytes((ord("A")+sector,))
        for name, raw, length, expected in (
            ("worked", b"\0" + literal, 9, literal),
            ("held", b"\x40" + repeated + b"\0\x04" + bytes(5), 4, repeated * 8),
        ):
            args = (raw, length.to_bytes(2, "big"))
            evaluated = bootstrap.evaluate_recipe(package, EXAMPLE, args)
            assert evaluated.status == 0 and evaluated.outputs == (expected,)
            examples.append({"sector": sector, "label": name, "recipe_id": EXAMPLE,
                             "inputs_hex": [a.hex() for a in args],
                             "status_and_output_hex": (bytes(2)+expected).hex(),
                             "existing_route_record_bytes": 8 + 12 + len(raw) + 2 + 2 + len(expected)})
    result["positive_examples"] = examples
    result["small_adversarial_suite"] = "eight unittest cases, including ten malformed token streams and eight malformed headers returning status3, automatic arithmetic failure retaining status11, and actual compact-wire roundtrip/execution; all public evaluator"
    output = ROOT / "artifacts/work/participant-revision"
    output.mkdir(parents=True, exist_ok=True)
    (output / "lzss-recipe-package-v0.bin").write_bytes(package.encoded)
    (output / "lzss-recipe-package-v1.bin").write_bytes(compact)
    (output / "lzss-recipe-measurement.json").write_text(json.dumps(result, sort_keys=True, indent=2)+"\n")
    print(json.dumps({key: result[key] for key in ("v0_package_bytes", "compact_v1_standalone_bytes", "compact_v1_merged_increment_bytes", "node_count", "max_primitive_steps", "peak_scratch_bytes")}, sort_keys=True), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--measure", action="store_true")
    arguments = parser.parse_args()
    if arguments.self_test or arguments.measure:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(RecipeTests)
        if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
            raise SystemExit(1)
    if arguments.measure:
        measure()
    if not arguments.self_test and not arguments.measure:
        parser.error("choose --self-test and/or --measure")
