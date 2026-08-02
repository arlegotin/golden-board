import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

import golden_board.manifest as manifest_module
from golden_board.manifest import (
    DIAGNOSTICS,
    MAX_COLLECTION,
    MAX_DEPTH,
    MAX_INPUT,
    MAX_NODES,
    ManifestError,
    canonical_manifest_hash,
    decode_canonical_manifest,
    encode_canonical_value,
)


ROOT = Path(__file__).resolve().parents[2]


def _node_document(extra: int = 0, first: bytes = b"0") -> bytes:
    members: list[bytes] = []
    for group in range(27):
        width = 37036 + (extra if group == 26 else 0)
        values = [b"0"] * width
        if group == 0:
            values[0] = first
        members.append(f'"g{group:02d}":'.encode() + b"[" + b",".join(values) + b"]")
    return b"{" + b",".join(members) + b"}\n"


class ManifestTests(unittest.TestCase):
    def assert_code(self, expected: str, raw: bytes) -> None:
        with self.assertRaises(ManifestError) as caught:
            decode_canonical_manifest(raw)
        self.assertEqual(expected, caught.exception.code)

    def test_canonical_documents_round_trip(self) -> None:
        cases = (
            b"{}\n",
            b'{"a":2,"b":1}\n',
            b'{"a":"\\n","u":"\xc3\xa9"}\n',
            b'{"x":[true,false,0,18446744073709551615]}\n',
            b'{"a":"\\b\\t\\n\\f\\r\\u0000\\\"\\\\/"}\n',
        )
        for raw in cases:
            with self.subTest(raw=raw):
                value = decode_canonical_manifest(raw)
                self.assertEqual(raw, encode_canonical_value(value))

    def test_value_encoder_has_one_authoritative_spelling(self) -> None:
        self.assertEqual(
            b'{"a":"\\b\\t\\n\\f\\r\\u0000\\\"\\\\/","u":"\xc3\xa9"}\n',
            encode_canonical_value({"u": "é", "a": "\b\t\n\f\r\x00\"\\/"}),
        )
        self.assertEqual(b'{"\\u0000":true}\n', encode_canonical_value({"\x00": True}))
        self.assertEqual(b'"\xf0\x9f\x98\x80"\n', encode_canonical_value("😀"))

    def test_noncanonical_spellings_reject(self) -> None:
        for raw in (
            b'{"b":1,"a":2}\n',
            b'{ "a":1}\n',
            b'{"a":"\\u0061"}\n',
            b'{"a":"\\/"}\n',
            b'{"a":"\\u000A"}\n',
            b"{}",
            b"\n{}\n",
            b"{} \n",
            b'{"u":"\\ud83d\\ude00"}\n',
        ):
            with self.subTest(raw=raw):
                self.assert_code("manifest.noncanonical", raw)

    def test_trailing_data_rejects_before_semantics(self) -> None:
        for raw in (b"{}\n\n", b"{}\nX", b'{"a":0,"a":1}\nX'):
            with self.subTest(raw=raw):
                self.assert_code("manifest.trailing_data", raw)

    def test_each_stable_diagnostic(self) -> None:
        cases = (
            ("manifest.utf8", b"\xff"),
            ("manifest.utf8", b"\xef\xbb\xbf{}\n"),
            ("manifest.syntax", b"{]\n"),
            ("manifest.syntax", b"[1,]\n"),
            ("manifest.duplicate_key", b'{"a":0,"a":1}\n'),
            ("manifest.duplicate_key", b'{"a":{"x":0,"x":1}}\n'),
            ("manifest.unsupported_type", b"null\n"),
            ("manifest.unsupported_type", b"1.0\n"),
            ("manifest.unsupported_type", b"1e0\n"),
            ("manifest.integer_range", b"-0\n"),
            ("manifest.integer_range", b"-1\n"),
            ("manifest.integer_range", b"18446744073709551616\n"),
            ("manifest.invalid_key", '{"é":0}\n'.encode()),
            ("manifest.invalid_unicode", b'{"a":"\\ud800"}\n'),
            ("manifest.invalid_unicode", b'{"a":"\\udc00"}\n'),
        )
        for expected, raw in cases:
            with self.subTest(expected=expected, raw=raw):
                self.assert_code(expected, raw)

    def test_diagnostic_precedence(self) -> None:
        self.assert_code("manifest.limit", b"\xff" + b" " * MAX_INPUT)
        self.assert_code("manifest.limit", b"{]" + b"[" * (MAX_DEPTH + 1))
        self.assert_code("manifest.limit", b"[" + b"," * MAX_COLLECTION + b"null]\n")
        self.assert_code("manifest.limit", _node_document(1, first=b"null"))
        self.assert_code("manifest.trailing_data", b'{"a":null,"a":1}\nX')
        self.assert_code("manifest.duplicate_key", b'{"a":null,"a":18446744073709551616}\n')
        self.assert_code("manifest.unsupported_type", b"[null,18446744073709551616]\n")
        self.assert_code("manifest.invalid_key", '{"é":"\\ud800"}\n'.encode())
        self.assert_code("manifest.integer_range", b"9" * 5000 + b"\n")
        self.assert_code("manifest.syntax", "[1١]\n".encode("utf-8"))
        with self.assertRaises(ManifestError) as caught:
            encode_canonical_value("\ud800" + "a" * MAX_INPUT)
        self.assertEqual("manifest.limit", caught.exception.code)
        with patch.object(manifest_module, "MAX_STRING_BYTES", 3):
            with self.assertRaises(ManifestError) as caught:
                encode_canonical_value({"aaaaé": 0})
        self.assertEqual("manifest.limit", caught.exception.code)

    def test_diagnostics_are_unique_and_in_precedence_order(self) -> None:
        self.assertEqual(10, len(DIAGNOSTICS))
        self.assertEqual(len(DIAGNOSTICS), len(set(DIAGNOSTICS)))
        self.assertEqual("manifest.limit", DIAGNOSTICS[0])
        self.assertEqual("manifest.noncanonical", DIAGNOSTICS[-1])

    def test_depth_boundary_and_boundary_plus_one(self) -> None:
        at = b"[" * MAX_DEPTH + b"0" + b"]" * MAX_DEPTH + b"\n"
        over = b"[" * (MAX_DEPTH + 1) + b"0" + b"]" * (MAX_DEPTH + 1) + b"\n"
        self.assertEqual(at, encode_canonical_value(decode_canonical_manifest(at)))
        self.assert_code("manifest.limit", over)

    def test_collection_boundary_and_boundary_plus_one(self) -> None:
        at = b"[" + b",".join([b"0"] * MAX_COLLECTION) + b"]\n"
        over = b"[" + b",".join([b"0"] * (MAX_COLLECTION + 1)) + b"]\n"
        self.assertEqual(MAX_COLLECTION, len(decode_canonical_manifest(at)))
        self.assert_code("manifest.limit", over)

    def test_node_boundary_and_boundary_plus_one(self) -> None:
        value = {f"g{group:02d}": [0] * 37036 for group in range(27)}
        at = encode_canonical_value(value)
        self.assertEqual(MAX_NODES, 1 + 27 + 27 * 37036)
        self.assertEqual(at, encode_canonical_value(decode_canonical_manifest(at)))
        value["g26"].append(0)
        with self.assertRaises(ManifestError) as caught:
            encode_canonical_value(value)
        self.assertEqual("manifest.limit", caught.exception.code)

    def test_input_and_string_boundary_plus_one(self) -> None:
        at = encode_canonical_value("a" * (MAX_INPUT - 3))
        self.assertEqual(MAX_INPUT, len(at))
        self.assertEqual(at, encode_canonical_value(decode_canonical_manifest(at)))
        with self.assertRaises(ManifestError) as caught:
            encode_canonical_value("a" * (MAX_INPUT - 2))
        self.assertEqual("manifest.limit", caught.exception.code)
        self.assert_code("manifest.limit", b'"' + b"a" * (MAX_INPUT - 2) + b'"\n')

    def test_string_size_scan_stops_at_the_first_over_limit_scalar(self) -> None:
        class Probe(str):
            def __iter__(self):
                yield from "aaaa"
                raise AssertionError("scanned beyond the first over-limit scalar")

        with patch.object(manifest_module, "MAX_STRING_BYTES", 3):
            with self.assertRaises(ManifestError) as caught:
                manifest_module._escaped_string(Probe())
        self.assertEqual("manifest.limit", caught.exception.code)

    def test_value_type_rejections(self) -> None:
        IntSubclass = type("IntSubclass", (int,), {})
        StringSubclass = type("StringSubclass", (str,), {})
        ListSubclass = type("ListSubclass", (list,), {})
        DictSubclass = type("DictSubclass", (dict,), {})
        cases = (
            (None, "manifest.unsupported_type"),
            (1.0, "manifest.unsupported_type"),
            (-1, "manifest.integer_range"),
            (2**64, "manifest.integer_range"),
            ({"é": 0}, "manifest.invalid_key"),
            ("\ud800", "manifest.invalid_unicode"),
            ((1, 2), "manifest.unsupported_type"),
            (IntSubclass(1), "manifest.unsupported_type"),
            (StringSubclass("a"), "manifest.unsupported_type"),
            (ListSubclass(), "manifest.unsupported_type"),
            (DictSubclass(), "manifest.unsupported_type"),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                with self.assertRaises(ManifestError) as caught:
                    encode_canonical_value(value)
                self.assertEqual(expected, caught.exception.code)
        with self.assertRaises(ManifestError) as caught:
            encode_canonical_value({StringSubclass("a"): 0})
        self.assertEqual("manifest.invalid_key", caught.exception.code)

    def test_empty_manifest_known_answer(self) -> None:
        self.assertEqual(
            "836b1e2073681781d86862b6135f26e66db2c15cc73080d01815930aefbc4a4a",
            canonical_manifest_hash(b"{}\n"),
        )

    def test_constants_source_is_exact_and_canonical(self) -> None:
        raw = (ROOT / "spec/constants-v0.json").read_bytes()
        self.assertEqual(
            "76e6ffd2478e569a7bd00210d27d4cbf958ad034b21346746282dd7aa2395d3b",
            hashlib.sha256(raw).hexdigest(),
        )
        self.assertEqual(raw, encode_canonical_value(decode_canonical_manifest(raw)))


if __name__ == "__main__":
    unittest.main()
