from pathlib import Path
import unittest

from golden_board.registry import (
    RegistryError,
    _python_result,
    _rust_result,
    _rust_binary,
    load_registry,
    run_registered_vectors,
)


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "artifacts/cargo-target"


class DifferentialVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.binary = _rust_binary(ROOT, TARGET)

    def test_every_registered_result_matches_both_implementations(self) -> None:
        self.assertEqual([], run_registered_vectors(ROOT, TARGET))

    def test_bounded_mutations_do_not_retain_the_original_result(self) -> None:
        def outcome(function, *arguments):
            try:
                return function(*arguments)
            except RegistryError as error:
                return f"error:{error}"

        cases = (
            ("identity-a-scalar", b"", b"\x00"),
            ("identity-a-scalar", b"\x00", b"\x01"),
            ("identity-a-list", b"\0\0", b"\0\0\0"),
            ("identity-a-list", b"\0\1\0\0\0\0", b"\0\1\0\0\0"),
            ("manifest", b"{}\n", b"{} \n"),
            ("manifest", b'{"a":0}\n', b'{"a":0,"a":0}\n'),
            ("manifest", b'{"a":0,"b":1}\n', b'{"b":1,"a":0}\n'),
            ("manifest", b'"a"\n', b'"\xff"\n'),
        )
        for operation, original, mutated in cases:
            with self.subTest(operation=operation, mutated=mutated):
                expected = _python_result(operation, original)
                self.assertNotEqual(expected, outcome(_python_result, operation, mutated))
                self.assertNotEqual(expected, outcome(_rust_result, self.binary, operation, mutated))

    def test_registry_contains_no_fake_source_or_later_profile_case(self) -> None:
        registry = load_registry(ROOT / "conformance/registry.toml")
        families = {case["family"] for case in registry["case"]}
        self.assertNotIn("source-doctor", families)
        self.assertEqual({"identity", "manifest"}, families)


if __name__ == "__main__":
    unittest.main()
