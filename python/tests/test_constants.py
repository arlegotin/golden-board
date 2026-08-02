import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

from golden_board import constants, manifest
from golden_board.checks import render_constants


ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path("spec/constants-v0.json")
OUTPUTS = {
    Path("python/golden_board/constants.py"),
    Path("crates/golden-board-core/src/constants.rs"),
}


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()


class ConstantsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads((ROOT / SOURCE).read_bytes())

    def render_document(self, document: object, *, raw: bytes | None = None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / SOURCE.parent).mkdir(parents=True)
        (root / SOURCE).write_bytes(_canonical(document) if raw is None else raw)
        return render_constants(root)

    def assert_rejected(self, document: object, *, raw: bytes | None = None) -> None:
        with self.assertRaises(ValueError):
            self.render_document(document, raw=raw)

    def test_canonical_source_generates_exact_tracked_files(self) -> None:
        outputs = render_constants(ROOT)
        self.assertEqual(OUTPUTS, set(outputs))
        self.assertEqual(outputs, render_constants(ROOT))
        for relative, generated in outputs.items():
            self.assertEqual((ROOT / relative).read_bytes(), generated)

        source_hash = hashlib.sha256((ROOT / SOURCE).read_bytes()).hexdigest().encode()
        for generated in outputs.values():
            self.assertIn(source_hash, generated)
            self.assertTrue(generated.endswith(b"\n"))

    def test_python_consumers_use_the_generated_values(self) -> None:
        for domain in self.document["domains"]:
            self.assertEqual(
                bytes.fromhex(domain["hex"]),
                getattr(constants, domain["name"].upper()),
            )
        self.assertEqual(tuple(self.document["diagnostics"]), constants.MANIFEST_DIAGNOSTICS)
        self.assertIs(constants.MANIFEST, manifest.MANIFEST_PREFIX)
        self.assertIs(constants.MANIFEST_DIAGNOSTICS, manifest.DIAGNOSTICS)

    def test_schema_is_closed_and_versioned(self) -> None:
        unknown_top = copy.deepcopy(self.document)
        unknown_top["extra"] = 0
        self.assert_rejected(unknown_top)

        unknown_domain = copy.deepcopy(self.document)
        unknown_domain["domains"][0]["extra"] = 0
        self.assert_rejected(unknown_domain)

        wrong_version = copy.deepcopy(self.document)
        wrong_version["schema_version"] = 1
        self.assert_rejected(wrong_version)

    def test_domain_names_are_unique_and_canonical(self) -> None:
        duplicate = copy.deepcopy(self.document)
        duplicate["domains"][1]["name"] = duplicate["domains"][0]["name"]
        self.assert_rejected(duplicate)

        invalid = copy.deepcopy(self.document)
        invalid["domains"][0]["name"] = "not-valid"
        self.assert_rejected(invalid)

        out_of_order = copy.deepcopy(self.document)
        out_of_order["domains"].reverse()
        self.assert_rejected(out_of_order)

    def test_diagnostics_are_unique_canonical_identifiers(self) -> None:
        duplicate = copy.deepcopy(self.document)
        duplicate["diagnostics"][1] = duplicate["diagnostics"][0]
        self.assert_rejected(duplicate)

        invalid = copy.deepcopy(self.document)
        invalid["diagnostics"][0] = "Manifest Limit"
        self.assert_rejected(invalid)

    def test_source_bytes_must_be_canonical(self) -> None:
        canonical = _canonical(self.document)
        self.assert_rejected(self.document, raw=b" " + canonical)
        self.assert_rejected(self.document, raw=canonical.removesuffix(b"\n"))
        huge_integer = (
            b'{"diagnostics":[],"domains":[],"schema_version":'
            + b"9" * 5_000
            + b"}\n"
        )
        self.assert_rejected(self.document, raw=huge_integer)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO support required")
    def test_source_reader_rejects_symlinks_and_fifo_without_blocking(self) -> None:
        for kind in ("parent-symlink", "leaf-symlink", "fifo"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                actual = root / "actual"
                actual.mkdir()
                source = actual / SOURCE.name
                source.write_bytes(_canonical(self.document))
                if kind == "parent-symlink":
                    (root / "spec").symlink_to(actual, target_is_directory=True)
                else:
                    (root / "spec").mkdir()
                    leaf = root / SOURCE
                    if kind == "leaf-symlink":
                        leaf.symlink_to(source)
                    else:
                        os.mkfifo(leaf)
                outcome: list[Exception] = []

                def render() -> None:
                    try:
                        render_constants(root)
                    except Exception as error:
                        outcome.append(error)

                worker = threading.Thread(target=render, daemon=True)
                worker.start()
                worker.join(0.5)
                self.assertFalse(worker.is_alive(), f"constants reader blocked on {kind}")
                self.assertEqual(1, len(outcome))
                self.assertIsInstance(outcome[0], ValueError)

    def test_domains_are_printable_ascii_with_one_terminal_nul(self) -> None:
        embedded_nul = copy.deepcopy(self.document)
        embedded_nul["domains"][0]["ascii"] = "GB\0BAD"
        embedded_nul["domains"][0]["hex"] = b"GB\0BAD\0".hex()
        self.assert_rejected(embedded_nul)

        missing_nul = copy.deepcopy(self.document)
        missing_nul["domains"][0]["hex"] = b"GB-IDENTITY-TEST-A-v0".hex()
        self.assert_rejected(missing_nul)

        extra_nul = copy.deepcopy(self.document)
        extra_nul["domains"][0]["hex"] += "00"
        self.assert_rejected(extra_nul)

    def test_domain_hex_is_lowercase_and_matches_ascii(self) -> None:
        uppercase = copy.deepcopy(self.document)
        uppercase["domains"][0]["hex"] = uppercase["domains"][0]["hex"].upper()
        self.assert_rejected(uppercase)

        mismatch = copy.deepcopy(self.document)
        mismatch["domains"][0]["ascii"] = "GB-IDENTITY-TEST-X-v0"
        self.assert_rejected(mismatch)

        spaced = copy.deepcopy(self.document)
        spaced["domains"][0]["ascii"] = "GB"
        spaced["domains"][0]["hex"] = "47  42  00"
        self.assert_rejected(spaced)


if __name__ == "__main__":
    unittest.main()
