"""Finite body grammar, deterministic generation, and atomic rejection."""
from hashlib import sha256
import unittest

from golden_board import body_codec_v1


def literals(raw):
    """An independently specified legal all-literal tokenization."""
    return b"\x03" + len(raw).to_bytes(2, "big") + b"".join(
        b"\0" + raw[start:start + 8] for start in range(0, len(raw), 8)
    )


class BodyCodecV1(unittest.TestCase):
    codec = body_codec_v1

    def test_literal_groups_empty_and_exact_wire_examples(self):
        for raw in (b"", b"A", b"ABCDEFGH", b"ABCDEFGHI", bytes(range(31))):
            with self.subTest(raw=raw):
                self.assertEqual(self.codec.encode_lzss(raw), literals(raw))
                self.assertEqual(self.codec.decode_lzss(literals(raw)), raw)
        self.assertEqual(self.codec.encode_lzss(b"A"), bytes.fromhex("0300010041"))

    def test_overlap_maximum_match_and_short_suffix_are_exact(self):
        cases = (
            (b"AAAA", "03000440410000"),
            (b"A" * 19, "0300134041000f"),
            (b"A" * 20, "0300144041000f41"),
            (b"AB" * 4, "0300082041420013"),
            (b"AB" * 10, "030014204142001f"),
        )
        for raw, encoded_hex in cases:
            with self.subTest(raw=raw):
                encoded = bytes.fromhex(encoded_hex)
                self.assertEqual(self.codec.encode_lzss(raw), encoded)
                self.assertEqual(self.codec.decode_lzss(encoded), raw)

    def test_longest_match_wins_and_equal_matches_choose_nearest(self):
        cases = (
            (b"abcXabcYabc", b"\x03\x00\x0b\x0aabcX\x00\x30Y\x00\x30"),
            (b"abcQZabcRabcQZ", b"\x03\x00\x0e\x05abcQZ\x00\x40R\x00\x82"),
        )
        for raw, encoded in cases:
            with self.subTest(raw=raw):
                self.assertEqual(self.codec.encode_lzss(raw), encoded)
                self.assertEqual(self.codec.encode_lzss(raw), self.codec.encode_lzss(raw))
                self.assertEqual(self.codec.decode_lzss(encoded), raw)

    def test_distance_4096_is_admitted_and_encoder_window_excludes_4097(self):
        at_limit = b"abc" + b"x" * 4093 + b"abc"
        encoded = self.codec.encode_lzss(at_limit)
        self.assertEqual(encoded[-2:], b"\xff\xf0")
        self.assertEqual(self.codec.decode_lzss(encoded), at_limit)
        beyond = b"abc" + b"x" * 4094 + b"abc"
        encoded = self.codec.encode_lzss(beyond)
        self.assertEqual(self.codec.decode_lzss(encoded), beyond)
        # Inspect only the last three generated tokens, without an encoder oracle.
        cursor, decoded, tokens = 3, 0, []
        while decoded < len(beyond):
            flags = encoded[cursor]
            cursor += 1
            for bit in range(7, -1, -1):
                if decoded == len(beyond):
                    break
                start = decoded
                if flags & (1 << bit):
                    token = int.from_bytes(encoded[cursor:cursor + 2], "big")
                    cursor += 2
                    decoded += (token & 15) + 3
                    tokens.append((start, "copy", (token >> 4) + 1))
                else:
                    tokens.append((start, "literal", encoded[cursor]))
                    cursor += 1
                    decoded += 1
        self.assertEqual(tokens[-3:], [(4097, "literal", 97), (4098, "literal", 98),
                                      (4099, "literal", 99)])
        # Literal construction independently reaches the largest copy distance.
        prefix = at_limit[:4096]
        manual = b"\x03" + len(at_limit).to_bytes(2, "big") + literals(prefix)[3:] + b"\x80\xff\xf0"
        self.assertEqual(self.codec.decode_lzss(manual), at_limit)

    def test_body_selection_is_strict_and_dispatch_never_sniffs_payload(self):
        for raw in (b"", b"abc", b"A" * 7, b"\x03\x00\x01\x00A"):
            with self.subTest(raw=raw):
                self.assertGreaterEqual(len(self.codec.encode_lzss(raw)), len(raw))
                self.assertEqual(self.codec.encode_body(raw), (0, raw))
                self.assertEqual(self.codec.decode_body(0, raw), raw)
        raw = b"A" * 8
        expected = self.codec.encode_lzss(raw)
        self.assertEqual(self.codec.encode_body(raw), (1, expected))
        self.assertEqual(self.codec.decode_body(1, expected), raw)
        self.assertEqual(self.codec.decode_body(1, b"\x03\0\0"), b"")

    def test_decoder_accepts_well_formed_noncanonical_tokenization(self):
        raw = b"A" * 60
        encoded = literals(raw)
        self.assertNotEqual(encoded, self.codec.encode_lzss(raw))
        self.assertEqual(self.codec.decode_lzss(encoded), raw)
        self.assertEqual(self.codec.decode_body(1, encoded), raw)

    def test_maximum_raw_size_and_incompressible_candidate_bound(self):
        raw = b"".join(sha256(index.to_bytes(2, "big")).digest() for index in range(512))
        self.assertEqual(len(raw), 16384)
        candidate = self.codec.encode_lzss(raw)
        self.assertGreater(len(candidate), 16384)
        self.assertLessEqual(len(candidate), 18435)
        self.assertEqual(self.codec.encode_body(raw), (0, raw))
        self.assertEqual(self.codec.decode_body(0, raw), raw)
        with self.assertRaises(ValueError):
            self.codec.decode_lzss(candidate)
        compressible = b"\0" * 16384
        version, encoded = self.codec.encode_body(compressible)
        self.assertEqual(version, 1)
        self.assertLessEqual(len(encoded), 16384)
        self.assertEqual(self.codec.decode_body(version, encoded), compressible)

    def test_truncations_references_overruns_unused_flags_and_trailing_reject(self):
        malformed = (
            b"", b"\x03", b"\x03\0", b"\x00\0\0", b"\x04\0\0",
            b"\x03\x40\x01", b"\x03\0\0\0", b"\x03\0\1",
            b"\x03\0\1\0", b"\x03\0\1\x01A", b"\x03\0\1\0A\0",
            b"\x03\0\3\x80\0\0", b"\x03\0\4\x40A\0",
            b"\x03\0\4\x40A\0\x10", b"\x03\0\3\x40A\0\0",
            literals(b"ABCDEFGH") + b"\0", bytes(16385),
        )
        for encoded in malformed:
            with self.subTest(encoded=encoded[:20], size=len(encoded)):
                with self.assertRaises(ValueError):
                    self.codec.decode_lzss(encoded)
                with self.assertRaises(ValueError):
                    self.codec.decode_body(1, encoded)
        complete = self.codec.encode_lzss(b"ABC" * 10)
        for end in range(len(complete)):
            with self.subTest(truncation=end):
                with self.assertRaises(ValueError):
                    self.codec.decode_lzss(complete[:end])

    def test_public_interfaces_reject_invalid_types_versions_and_raw_bounds(self):
        for raw in (None, "abc", bytearray(b"abc"), memoryview(b"abc"), [1, 2, 3], 3):
            for operation in (self.codec.encode_lzss, self.codec.decode_lzss,
                              self.codec.encode_body):
                with self.subTest(operation=operation.__name__, value=type(raw).__name__):
                    with self.assertRaises(ValueError):
                        operation(raw)
            for version in (0, 1):
                with self.assertRaises(ValueError):
                    self.codec.decode_body(version, raw)
        for version in (False, True, -1, 2, 3, 65535, None, "1", 1.0):
            with self.subTest(version=version):
                with self.assertRaises(ValueError):
                    self.codec.decode_body(version, b"\x03\0\0")
        for operation in (self.codec.encode_lzss, self.codec.encode_body):
            with self.assertRaises(ValueError):
                operation(bytes(16385))
        with self.assertRaises(ValueError):
            self.codec.decode_body(0, bytes(16385))


if __name__ == "__main__":
    unittest.main()
