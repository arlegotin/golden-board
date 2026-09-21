from __future__ import annotations

from dataclasses import FrozenInstanceError
import os
import unittest

from golden_board import bootstrap, body_codec_v1
from golden_board.m2_body_recipe_v1 import (
    BodyRecipeProgramV1,
    body_recipe_programs_v1,
    build_body_recipe_diagnostic_package_v1,
)


class BodyRecipeV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = build_body_recipe_diagnostic_package_v1()
        cls.package = bootstrap.decode_recipe_package(cls.raw, 7)

    def example(self, tokens, length):
        return bootstrap.evaluate_recipe(self.package, 203, (tokens, length.to_bytes(2, "big")))

    def test_programs_are_fresh_and_deeply_immutable(self):
        first, second = body_recipe_programs_v1(), body_recipe_programs_v1()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertTrue(all(isinstance(p, BodyRecipeProgramV1) for p in first))
        self.assertEqual(tuple(p.recipe_id for p in first), (201, 202, 203))
        self.assertTrue(all(a is not b for a, b in zip(first, second, strict=True)))
        self.assertIsInstance(first[0].nodes, tuple)
        self.assertIsInstance(first[0].nodes[0][3], tuple)
        with self.assertRaises(FrozenInstanceError):
            first[0].recipe_id = 999

    def test_small_vm_outputs_match_independent_host_codec(self):
        for source in (b"12345678", b"AAAAAAAA", b"ABABABAB", b"ABCDEFGH"):
            encoded = body_codec_v1.encode_lzss(source)
            tokens = encoded[3:]
            self.assertLessEqual(len(tokens), 9)
            result = self.example(tokens + bytes(9-len(tokens)), len(tokens))
            self.assertEqual(result.status, 0)
            self.assertEqual(result.outputs, (body_codec_v1.decode_lzss(encoded),))
            self.assertEqual(result.outputs, (source,))

    def test_malformed_token_boundaries_are_atomic_status3(self):
        for raw, length in (
            (bytes(9), 0), (b"\x80\0\x05"+bytes(6), 3),
            (b"\x40A\0"+bytes(6), 3), (b"\x40A\0\x05"+bytes(5), 4),
            (b"\x40A\0\x14"+bytes(5), 4), (b"\x41A\0\x04"+bytes(5), 4),
            (b"\x40A\0\x04"+bytes(5), 5), (b"\0"+b"12345678", 8),
            (b"\0"+b"12345678", 10), (b"\0"+b"12345678", 65535),
        ):
            with self.subTest(raw=raw.hex(), length=length):
                self.assertEqual(self.example(raw, length), bootstrap.RecipeResult(3, ()))

    def test_header_bounds_and_unknown_codec_are_atomic_status3(self):
        for prefix, length in ((bytes(3), 0), (bytes(3), 1), (bytes(3), 2),
                               (b"\x02\0\x08", 12), (b"\x03\x40\x01", 3),
                               (b"\x03\xff\xff", 3), (b"\x03\0\0", 16385),
                               (b"\x03\0\0", 65535)):
            result = bootstrap.evaluate_recipe(self.package, 202,
                (prefix+bytes(16384-len(prefix)), length.to_bytes(2, "big")))
            self.assertEqual(result, bootstrap.RecipeResult(3, ()))

    def test_unused_input_padding_is_ignored(self):
        self.assertEqual(self.example(b"\x40A\0\x04"+b"\xff"*5, 4),
                         bootstrap.RecipeResult(0, (b"AAAAAAAA",)))

    def test_upper_distance_4096_on_reachable_partial_state(self):
        # The prefix is 512 complete groups of eight literals. The next group
        # starts a length-three copy at the maximum admitted backward distance.
        prefix = (b"\0" + b"\xa9"*8)*512
        encoded = b"\x03\x10\x03" + prefix + b"\x80\xff\xf0"
        state = bytearray(32782)
        state[:len(encoded)] = encoded
        state[16384:16384+4096] = b"\xa9"*4096
        for offset, value in ((32768, len(encoded)), (32770, 4099),
                              (32772, 3+len(prefix)), (32774, 4096),
                              (32776, 0x0A99)):
            state[offset:offset+2] = value.to_bytes(2, "big")
        state[32781] = 1
        result = bootstrap.evaluate_recipe(self.package, 201, (bytes(state), bytes(8)))
        self.assertEqual(result.status, 0)
        output = result.outputs[0]
        self.assertEqual(output[16384+4096], 0xA9)
        self.assertEqual(output[32774:32779], b"\x10\x01\x10\0\x02")

    def test_no_byte_input_coercion(self):
        for value in (bytearray(9), memoryview(bytes(9)), "123456789", [0]*9):
            with self.assertRaises(TypeError):
                bootstrap.evaluate_recipe(self.package, 203, (value, b"\0\x09"))

    def test_exact_interfaces_resources_and_old_limits(self):
        self.assertEqual(self.package.total_node_count, 374)
        self.assertEqual(self.package.maximum_primitive_steps, 2375776)
        self.assertEqual(self.package.peak_live_scratch_bytes, 98398)
        self.assertEqual(len(self.raw), 13101)
        self.assertEqual(self.package.recipes[0].inputs[0].width, 32782)
        self.assertEqual(self.package.recipes[1].inputs[0].width, 16384)
        self.assertEqual(self.package.recipes[1].outputs[-1].width, 16384)
        self.assertEqual(bootstrap.RECIPE_PACKAGE_MAX, 1048576)
        self.assertEqual(bootstrap.RECIPE_STEP_MAX, 268435456)
        self.assertEqual(bootstrap.RECIPE_SCRATCH_MAX, 16777216)
        self.assertTrue(all(1 <= n.opcode <= 25 for r in self.package.recipes for n in r.nodes))

    def test_checked_arithmetic_failure_retains_status11(self):
        state = bytearray(32782)
        state[32781] = 1
        state[32770:32772] = b"\xff\xff"
        state[32774:32776] = b"\xff\xff"
        result = bootstrap.evaluate_recipe(self.package, 201, (bytes(state), bytes(8)))
        self.assertEqual(result, bootstrap.RecipeResult(11, ()))

    @unittest.skipUnless(os.environ.get("GB_M2_BODY_RECIPE_FULL") == "1", "opt-in full fixed-iteration stress")
    def test_full_section_limit(self):
        expected = bytes(16384)
        encoded = body_codec_v1.encode_lzss(expected)
        result = bootstrap.evaluate_recipe(self.package, 202,
            (encoded+bytes(16384-len(encoded)), len(encoded).to_bytes(2, "big")))
        self.assertEqual(result, bootstrap.RecipeResult(0, (b"\x40\0", expected)))


if __name__ == "__main__":
    unittest.main()
