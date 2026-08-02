import unittest

from golden_board.identity import (
    IdentityError,
    _encode_u16,
    _encode_u32,
    list_preimage,
    scalar_preimage,
    sha256_hex,
    validate_prefix,
)


A = b"GB-IDENTITY-TEST-A-v0\x00"
B = b"GB-IDENTITY-TEST-B-v0\x00"


class IdentityTests(unittest.TestCase):
    def test_known_answers(self) -> None:
        cases = (
            (scalar_preimage(A, b""), "d884e5911a8a923feb85ae9c2b8066eb982234dfe6c6e7f34900988e6dc27a14"),
            (scalar_preimage(A, b"\x00"), "788f75a4aec50bc39d44796a9c335e36343c690363de84db24972be2bad5eda1"),
            (scalar_preimage(B, b"\x00"), "bd9a12341ac48f633c769140093675496d828dfa9ed21874b725acf3b8870c0e"),
            (list_preimage(A, []), "ce8a5a8230d526db58192616683de0a728d0f6f9198b3ee5ebe55f2fa767a2da"),
            (list_preimage(A, [b""]), "c475f1fbfda9eae9b0ad3e71603bdd6d45ebf545c866bb50f79170bc8895d72c"),
            (list_preimage(A, [b"\x00", b"\x01\x02"]), "ba34053b678a144a645eb524bca6f464ee1923fe5d12f5d32dc29ab80d8a218f"),
            (list_preimage(A, [b"\x01\x02", b"\x00"]), "67b715044915a1337625e8002b7745c620fbf187c68882cef25c163b949125e9"),
        )
        for preimage, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(expected, sha256_hex(preimage))

    def test_exact_preimages(self) -> None:
        self.assertEqual(A + b"\x00\x00\x00\x01\x00", scalar_preimage(A, b"\x00"))
        self.assertEqual(
            A + b"\x00\x02\x00\x00\x00\x01\x00\x00\x00\x00\x02\x01\x02",
            list_preimage(A, [b"\x00", b"\x01\x02"]),
        )

    def test_prefix_validation(self) -> None:
        for prefix in (b"missing-nul", b"early\x00nul\x00", b"\x7f\x00", b"\xc3\xa9\x00", b"a" * 63 + b"\x00", b"\x00"):
            with self.subTest(prefix=prefix), self.assertRaises(IdentityError):
                validate_prefix(prefix)
        validate_prefix(b" \x00")
        validate_prefix(b"~\x00")

    def test_integer_helper_boundaries_without_large_allocations(self) -> None:
        self.assertEqual(b"\xff\xff", _encode_u16(2**16 - 1))
        self.assertEqual(b"\xff\xff\xff\xff", _encode_u32(2**32 - 1))
        for helper, value in ((_encode_u16, 2**16), (_encode_u32, 2**32), (_encode_u16, -1), (_encode_u32, -1)):
            with self.subTest(helper=helper.__name__, value=value), self.assertRaises(IdentityError):
                helper(value)

    def test_bytes_are_required(self) -> None:
        with self.assertRaises(IdentityError):
            scalar_preimage(A, bytearray(b"x"))  # type: ignore[arg-type]
        with self.assertRaises(IdentityError):
            list_preimage(A, [bytearray(b"x")])  # type: ignore[list-item]


if __name__ == "__main__":
    unittest.main()
