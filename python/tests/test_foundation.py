from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

try:
    from golden_board import canonical_manifest, identity
except ImportError:
    canonical_manifest = None
    identity = None

try:
    from golden_board import source_doctor
except ImportError:
    source_doctor = None


ROOT = Path(__file__).resolve().parents[2]
IDENTITY_FIXTURE = ROOT / "conformance" / "identity-v0.json"
MANIFEST_FIXTURE = ROOT / "conformance" / "manifest-v0.json"
CHESS_FIXTURE = ROOT / "conformance" / "chess-v0.json"
SOURCE_FIXTURE = ROOT / "conformance" / "source-v0.json"
MAX_REPO_TEXT_BYTES = 1_048_576
M0_IDENTITY_VECTORS_SHA256 = (
    "19b90c4ab863ca3853a1b8229b8ae84a886e4a8cf0c3bee496157e592bf000ae"
)
M1_IDENTITY_VECTORS = [
    {
        "domain_hex": "676f6c64656e2d626f6172643a706f736974696f6e3a763000",
        "fields_hex": [
            "0402030506030204010101010101010100000000000000000000000000000000"
            "0000000000000000000000000000000007070707070707070a08090b0c09080a"
            "000f00"
        ],
        "identity": "7d578698cdb2095a1b818234f12b3e6d4f19bbadb414887f26e6a8d52417a186",
        "name": "initial-position",
        "preimage_hex": (
            "676f6c64656e2d626f6172643a706f736974696f6e3a763000000100000043"
            "0402030506030204010101010101010100000000000000000000000000000000"
            "0000000000000000000000000000000007070707070707070a08090b0c09080a"
            "000f00"
        ),
    },
    {
        "domain_hex": (
            "676f6c64656e2d626f6172643a72657065746974696f6e2d6b65793a763000"
        ),
        "fields_hex": [
            "0402030506030204010101010101010100000000000000000000000000000000"
            "0000000000000000000000000000000007070707070707070a08090b0c09080a"
            "000f00"
        ],
        "identity": "b12da42c15cc340394688be5d771ad8936241e9dcb03592b2791e06b9dbe33e3",
        "name": "initial-repetition-key",
        "preimage_hex": (
            "676f6c64656e2d626f6172643a72657065746974696f6e2d6b65793a763000"
            "000100000043"
            "0402030506030204010101010101010100000000000000000000000000000000"
            "0000000000000000000000000000000007070707070707070a08090b0c09080a"
            "000f00"
        ),
    },
    {
        "domain_hex": "676f6c64656e2d626f6172643a67616d653a763000",
        "fields_hex": ["00043550d24039e0edf001"],
        "identity": "c49a921d652aa82b69a320073ca7ca0f5f3adf3d4ccc80d5aea162a52925b3bb",
        "name": "fools-mate-game",
        "preimage_hex": (
            "676f6c64656e2d626f6172643a67616d653a76300000010000000b"
            "00043550d24039e0edf001"
        ),
    },
    {
        "domain_hex": "676f6c64656e2d626f6172643a67616d652d7365743a763000",
        "fields_hex": ["000100043550d24039e0edf001"],
        "identity": "4070001b03556dcf41043adcf7a261c4b20aa7874a8033546520a48107fbc2f8",
        "name": "fools-mate-game-set",
        "preimage_hex": (
            "676f6c64656e2d626f6172643a67616d652d7365743a76300000010000000d"
            "000100043550d24039e0edf001"
        ),
    },
]


def repo_text_bytes(root: Path, relative: bytes) -> bytes:
    components = relative.split(b"/")
    if (
        not relative
        or b"\0" in relative
        or relative.startswith(b"/")
        or any(component in {b"", b".", b".."} for component in components)
        or not hasattr(os, "O_NOFOLLOW")
    ):
        raise AssertionError(f"unsafe repository text path: {relative!r}")

    directory_fd = None
    file_fd = None
    try:
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        for component in components[:-1]:
            metadata = os.stat(component, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise AssertionError(f"unsafe repository text path: {relative!r}")
            next_fd = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd

        metadata = os.stat(components[-1], dir_fd=directory_fd, follow_symlinks=False)
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > MAX_REPO_TEXT_BYTES
        ):
            raise AssertionError(f"unsafe repository text path: {relative!r}")
        file_fd = os.open(
            components[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd
        )
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_REPO_TEXT_BYTES:
            raise AssertionError(f"unsafe repository text path: {relative!r}")

        data = bytearray()
        while len(data) <= MAX_REPO_TEXT_BYTES:
            chunk = os.read(file_fd, min(65_536, MAX_REPO_TEXT_BYTES + 1 - len(data)))
            if not chunk:
                return bytes(data)
            data.extend(chunk)
        raise AssertionError(f"unsafe repository text path: {relative!r}")
    except OSError as error:
        raise AssertionError(f"unsafe repository text path: {relative!r}") from error
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def validate_conformance_registry(root: Path) -> None:
    try:
        registry = tomllib.loads(
            repo_text_bytes(root, b"conformance/registry.toml").decode("utf-8")
        )
    except (AssertionError, OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise AssertionError("invalid conformance registry") from error
    if set(registry) != {"schema", "suite"} or registry["schema"] != (
        "golden-board.conformance-registry/v0"
    ):
        raise AssertionError("invalid conformance registry")
    suites = registry["suite"]
    if not isinstance(suites, list):
        raise AssertionError("invalid conformance registry")

    row_keys = {
        "id",
        "path",
        "specification",
        "version",
        "sha256",
        "consumers",
        "provenance",
    }
    identifiers = set()
    paths = set()
    for suite in suites:
        if not isinstance(suite, dict) or set(suite) != row_keys:
            raise AssertionError("invalid conformance registry")
        identifier = suite["id"]
        specification = suite["specification"]
        if any(
            not isinstance(value, str)
            or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) is None
            for value in (identifier, specification)
        ):
            raise AssertionError("invalid conformance registry")
        path = suite["path"]
        if (
            not isinstance(path, str)
            or path != f"conformance/{identifier}.json"
            or identifier in identifiers
            or path in paths
            or suite["version"] != "v0"
            or not isinstance(suite["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", suite["sha256"]) is None
            or suite["consumers"] != ["python", "rust"]
            or suite["provenance"] != "hand-authored"
        ):
            raise AssertionError("invalid conformance registry")
        identifiers.add(identifier)
        paths.add(path)
        payload = repo_text_bytes(root, path.encode("ascii"))
        if hashlib.sha256(payload).hexdigest() != suite["sha256"]:
            raise AssertionError("invalid conformance registry")

    try:
        inventory = set()
        with os.scandir(root / "conformance") as entries:
            for entry in entries:
                if entry.name == "registry.toml":
                    continue
                metadata = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                    raise AssertionError("invalid conformance registry")
                inventory.add(f"conformance/{entry.name}")
                if len(inventory) > len(paths):
                    raise AssertionError("invalid conformance registry")
    except OSError as error:
        raise AssertionError("invalid conformance registry") from error
    if inventory != paths:
        raise AssertionError("invalid conformance registry")


class FoundationModulesPresent(unittest.TestCase):
    def test_identity_and_manifest_modules_exist(self) -> None:
        self.assertIsNotNone(identity)
        self.assertIsNotNone(canonical_manifest)

    def test_source_doctor_module_exists(self) -> None:
        self.assertIsNotNone(source_doctor)


@unittest.skipIf(identity is None, "implementation not present")
class IdentityConformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.before = IDENTITY_FIXTURE.read_bytes()
        cls.fixture = json.loads(cls.before)

    @classmethod
    def tearDownClass(cls) -> None:
        if IDENTITY_FIXTURE.read_bytes() != cls.before:
            raise AssertionError("identity fixture was modified")

    def test_hand_authored_vectors(self) -> None:
        for case in self.fixture["vectors"]:
            with self.subTest(case=case["name"]):
                domain = bytes.fromhex(case["domain_hex"])
                fields = [bytes.fromhex(value) for value in case["fields_hex"]]
                self.assertEqual(
                    identity.frame_preimage(domain, fields).hex(),
                    case["preimage_hex"],
                )
                self.assertEqual(
                    identity.identity_hex(domain, fields), case["identity"]
                )

    def test_registered_m1_vectors_are_exact(self) -> None:
        vectors = self.fixture["vectors"]
        self.assertEqual(len(vectors), 12)
        m0_bytes = json.dumps(
            vectors[:8], ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        self.assertEqual(hashlib.sha256(m0_bytes).hexdigest(), M0_IDENTITY_VECTORS_SHA256)
        self.assertEqual(vectors[8:], M1_IDENTITY_VECTORS)

    def test_nist_sha256_known_answers(self) -> None:
        for case in self.fixture["sha256"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(
                    hashlib.sha256(bytes.fromhex(case["message_hex"])).hexdigest(),
                    case["digest"],
                )

    def test_integer_boundaries(self) -> None:
        self.assertEqual(identity.u16_be(0), b"\x00\x00")
        self.assertEqual(identity.u16_be(65_535), b"\xff\xff")
        self.assertEqual(identity.u32_be(0), b"\x00\x00\x00\x00")
        self.assertEqual(identity.u32_be(4_294_967_295), b"\xff\xff\xff\xff")
        for value in (-1, 65_536):
            with self.subTest(kind="u16", value=value):
                with self.assertRaises(identity.IdentityError):
                    identity.u16_be(value)
        for value in (-1, 4_294_967_296):
            with self.subTest(kind="u32", value=value):
                with self.assertRaises(identity.IdentityError):
                    identity.u32_be(value)

    def test_field_count_and_domain_rejections(self) -> None:
        with self.assertRaises(identity.IdentityError):
            identity.frame_preimage(b"test:a\0", [b""] * 65_536)
        for domain in (b"test:a", b"test\0a\0", b"t\xff\0", "test:a\0"):
            with self.subTest(domain=domain):
                with self.assertRaises(identity.IdentityError):
                    identity.frame_preimage(domain, [])
        with self.assertRaises(identity.IdentityError):
            identity.frame_preimage(b"test:a\0", ["not-bytes"])


@unittest.skipIf(canonical_manifest is None, "implementation not present")
class ManifestConformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.before = MANIFEST_FIXTURE.read_bytes()
        cls.fixture = json.loads(cls.before)

    @classmethod
    def tearDownClass(cls) -> None:
        if MANIFEST_FIXTURE.read_bytes() != cls.before:
            raise AssertionError("manifest fixture was modified")

    def test_payload_cases(self) -> None:
        for case in self.fixture["cases"]:
            source = bytes.fromhex(case["source_hex"])
            expected = bytes.fromhex(case["canonical_hex"])
            with self.subTest(case=case["name"]):
                if case["outcome"] == "reject":
                    with self.assertRaises(canonical_manifest.ManifestError):
                        canonical_manifest.canonicalize_manifest(source)
                    continue
                self.assertEqual(
                    canonical_manifest.canonicalize_manifest(source), expected
                )
                if case["outcome"] == "canonical":
                    canonical_manifest.validate_canonical_manifest(source)
                else:
                    with self.assertRaises(canonical_manifest.ManifestError):
                        canonical_manifest.validate_canonical_manifest(source)

    def test_fixture_files_are_canonical(self) -> None:
        canonical_manifest.validate_canonical_manifest(IDENTITY_FIXTURE.read_bytes())
        canonical_manifest.validate_canonical_manifest(MANIFEST_FIXTURE.read_bytes())
        canonical_manifest.validate_canonical_manifest(CHESS_FIXTURE.read_bytes())
        canonical_manifest.validate_canonical_manifest(SOURCE_FIXTURE.read_bytes())

    def test_depth_boundaries(self) -> None:
        depth_32 = b'{"a":' * 31 + b"{}" + b"}" * 31 + b"\n"
        depth_33 = b'{"a":' * 32 + b"{}" + b"}" * 32 + b"\n"
        canonical_manifest.validate_canonical_manifest(depth_32)
        with self.assertRaises(canonical_manifest.ManifestError):
            canonical_manifest.canonicalize_manifest(depth_33)
        nested = {}
        for _ in range(32):
            nested = {"a": nested}
        with self.assertRaises(canonical_manifest.ManifestError):
            canonical_manifest.serialize_manifest(nested)

    def test_input_and_output_boundaries(self) -> None:
        content = "a" * (canonical_manifest.MAX_BYTES - 9)
        exact = ('{"s":"' + content + '"}\n').encode()
        self.assertEqual(len(exact), canonical_manifest.MAX_BYTES)
        canonical_manifest.validate_canonical_manifest(exact)
        with self.assertRaises(canonical_manifest.ManifestError):
            canonical_manifest.canonicalize_manifest(exact + b"\n")
        self.assertEqual(
            len(canonical_manifest.serialize_manifest({"s": content})),
            canonical_manifest.MAX_BYTES,
        )
        with self.assertRaises(canonical_manifest.ManifestError):
            canonical_manifest.serialize_manifest({"s": content + "a"})

    def test_round_trip_and_insertion_order(self) -> None:
        source = b'{"a":[true,0,"x"],"b":{}}\n'
        value = canonical_manifest.validate_canonical_manifest(source)
        self.assertEqual(canonical_manifest.serialize_manifest(value), source)
        self.assertEqual(
            canonical_manifest.serialize_manifest({"b": 1, "a": 2}),
            canonical_manifest.serialize_manifest({"a": 2, "b": 1}),
        )

    def test_serializer_rejects_values_outside_subset(self) -> None:
        values = [None, -1, 1.0, {"": 1}, {"é": 1}, {"a": "\ud800"}, [1]]
        for value in values:
            with self.subTest(value=repr(value)):
                with self.assertRaises(canonical_manifest.ManifestError):
                    canonical_manifest.serialize_manifest(value)


@unittest.skipIf(source_doctor is None, "source doctor not present")
class SourceDoctorTrustBoundary(unittest.TestCase):
    def test_lock_accepts_only_the_closed_m0_document(self) -> None:
        lock = (ROOT / "inputs/source-lock.toml").read_bytes()
        parsed = source_doctor.parse_source_lock(lock, ROOT)
        self.assertEqual(parsed.path, "docs/64_games.md")
        self.assertEqual(parsed.expected_bytes, 165_145)

        mutations = [
            lock.replace(b'id = "pgn-guide-1994"', b'id = "fide-laws-2023"'),
            lock.replace(b"33d44f7167ab190c", b"X3d44f7167ab190c", 1),
            lock.replace(b'newline = "lf"\n', b"", 1),
            lock.replace(b'newline = "lf"\n', b'newline = "lf"\nextra = 1\n', 1),
            lock.replace(b'path = "docs/64_games.md"', b'path = "/tmp/x"', 1),
            lock.replace(b'path = "docs/64_games.md"', b'path = "../x"', 1),
            lock.replace(b'role = "historical_background"', b'role = "future_profile"', 1),
            lock.replace(b'newline = "lf"\n', b'newline = "lf"\nprofile = "v0"\n', 1),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                with self.assertRaises(source_doctor.LockError):
                    source_doctor.parse_source_lock(mutation, ROOT)

    def test_regular_source_bounds_and_lock_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            path = root / "docs/source.md"
            for size in (source_doctor.MAX_SOURCE_BYTES - 1, source_doctor.MAX_SOURCE_BYTES):
                data = b"a" * size
                path.write_bytes(data)
                locked = source_doctor.LockedSource(
                    "docs/source.md", len(data), hashlib.sha256(data).hexdigest()
                )
                opened = source_doctor.read_locked_source(root, locked)
                self.assertTrue(opened.lock_match)
                self.assertEqual(opened.data, data)

            path.write_bytes(b"a" * (source_doctor.MAX_SOURCE_BYTES + 1))
            with self.assertRaises(source_doctor.InputError):
                source_doctor.read_locked_source(
                    root,
                    source_doctor.LockedSource("docs/source.md", 0, "0" * 64),
                )

            path.write_bytes(b"same")
            expected = source_doctor.LockedSource(
                "docs/source.md", 4, hashlib.sha256(b"same").hexdigest()
            )
            for replacement in (b"diff", b"same-more", b"sam"):
                path.write_bytes(replacement)
                opened = source_doctor.read_locked_source(root, expected)
                self.assertFalse(opened.lock_match)
            path.write_bytes(b"same")
            wrong_size = source_doctor.LockedSource(
                "docs/source.md", 5, hashlib.sha256(b"same").hexdigest()
            )
            wrong_hash = source_doctor.LockedSource("docs/source.md", 4, "0" * 64)
            self.assertFalse(source_doctor.read_locked_source(root, wrong_size).lock_match)
            self.assertFalse(source_doctor.read_locked_source(root, wrong_hash).lock_match)

            path.chmod(0)
            try:
                if not os.access(path, os.R_OK):
                    with self.assertRaises(source_doctor.InputError):
                        source_doctor.read_locked_source(root, expected)
            finally:
                path.chmod(0o600)

    def test_unsafe_source_objects_reject_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            target = root / "docs/target"
            target.write_bytes(b"x")
            locked = source_doctor.LockedSource("docs/input", 1, hashlib.sha256(b"x").hexdigest())
            input_path = root / locked.path

            cases = []
            input_path.symlink_to(target)
            cases.append("symlink")
            for kind in cases:
                with self.subTest(kind=kind):
                    with self.assertRaises(source_doctor.InputError):
                        source_doctor.read_locked_source(root, locked)
            input_path.unlink()

            input_path.mkdir()
            with self.assertRaises(source_doctor.InputError):
                source_doctor.read_locked_source(root, locked)
            input_path.rmdir()

            if hasattr(os, "mkfifo"):
                os.mkfifo(input_path)
                try:
                    with self.assertRaises(source_doctor.InputError):
                        source_doctor.read_locked_source(root, locked)
                finally:
                    input_path.unlink()

            if hasattr(socket, "AF_UNIX"):
                listener = socket.socket(socket.AF_UNIX)
                try:
                    listener.bind(str(input_path))
                    with self.assertRaises(source_doctor.InputError):
                        source_doctor.read_locked_source(root, locked)
                finally:
                    listener.close()
                    input_path.unlink(missing_ok=True)

            with self.assertRaises(source_doctor.InputError):
                source_doctor.read_locked_source(root, locked)
            with self.assertRaises(source_doctor.InputError):
                source_doctor.read_locked_source(
                    root,
                    source_doctor.LockedSource("../outside", 0, "0" * 64),
                )


@unittest.skipIf(source_doctor is None, "source doctor not present")
class SourceDoctorScanner(unittest.TestCase):
    def scan(self, data: bytes) -> dict:
        locked = source_doctor.LockedSource(
            "docs/source.md", len(data), hashlib.sha256(data).hexdigest()
        )
        return source_doctor.scan_source(data, locked)

    def test_source_fences_tags_spans_and_regions(self) -> None:
        data = (
            b"outer  \n"
            b"```pgn\n"
            b'[Event "x...?!"]\n'
            b'[Result "1-0"]\n'
            b'[Event "escaped\\\"quote"]\n'
            b"malformed\n"
            b"\n"
            b"1. e4 e5 1-0\n"
            b"```\n"
        )
        report = self.scan(data)
        self.assertEqual(report["fences"]["candidate_count"], 1)
        block = report["blocks"][0]
        for key in ("fence_span", "content_span", "tag_span", "separator_span", "movetext_span"):
            start, end = block[key]
            self.assertEqual(len(data[start:end]), end - start)
        self.assertEqual(data[slice(*block["movetext_span"])], b"1. e4 e5 1-0\n")
        self.assertEqual(report["tags"]["recognized_lines"], 3)
        self.assertEqual(report["tags"]["duplicate_blocks"]["count"], 1)
        self.assertEqual(report["tags"]["malformed_lines"]["count"], 1)
        self.assertEqual(report["tags"]["escape_counts"]["quote"], 1)
        event = next(item for item in report["tags"]["punctuation"] if item["name"] == "Event")
        self.assertEqual(event["ellipsis_value_count"], 1)
        self.assertEqual(event["question_value_count"], 1)
        trailing = report["source"]["trailing_horizontal_whitespace"]
        self.assertEqual([item["region"] for item in trailing], [
            "outer_markdown", "fence", "tags", "separator", "movetext"
        ])
        self.assertEqual(trailing[0]["count"], 1)
        self.assertEqual(report["movetext"]["constructs"][0]["count"], 0)
        canonical_manifest.validate_canonical_manifest(
            canonical_manifest.serialize_manifest(report)
        )

    def test_encoding_newlines_controls_and_fence_anomalies(self) -> None:
        data = (
            b"\xef\xbb\xbftext\n"
            b"```PGN\r\n"
            b"```\n"
            b"```pgn\n"
            b"```pgn\n"
            b"\x7f\n"
            b"```\n"
            b"```pgn\n"
        )
        report = self.scan(data)
        self.assertTrue(report["source"]["bom"])
        self.assertEqual(report["source"]["line_endings"]["crlf"], 1)
        self.assertEqual(report["source"]["unexpected_controls"]["count"], 1)
        self.assertEqual(report["fences"]["near_misses"]["count"], 1)
        self.assertEqual(report["fences"]["orphan_closers"]["count"], 1)
        self.assertEqual(report["fences"]["nested_openers"]["count"], 1)
        self.assertEqual(report["fences"]["unclosed_openers"]["count"], 1)
        self.assertEqual(report["fences"]["candidate_count"], 1)

        invalid = self.scan(b"\xff\n")
        self.assertFalse(invalid["source"]["utf8_valid"])
        self.assertEqual(invalid["source"]["nfc_state"], "unavailable")
        non_nfc = self.scan("e\u0301\n".encode())
        self.assertEqual(non_nfc["source"]["nfc_state"], "valid_non_nfc")

        candidate = b"```pgn\n\n```\n"
        for count in (0, 1, 63, 64, 65):
            source = candidate * count
            locked = source_doctor.LockedSource(
                "docs/source.md", len(source), hashlib.sha256(source).hexdigest()
            )
            counted = source_doctor.scan_source(source, locked)
            self.assertEqual(counted["fences"]["candidate_count"], count)
            self.assertEqual(source_doctor._gate_passes(counted), count == 64)

    def test_movetext_classes_constructs_results_and_duplicates(self) -> None:
        first = (
            b"```pgn\n[Result \"1-0\"]\n\n"
            b"1. e4 Nf3 N1f3 Nb1d2 O-O exd5 e8=Q+ Raxd1# 2. O-O-O 1-0\n```\n"
        )
        second = b"```pgn\n[Result \"0-1\"]\n\n1. e4  e5 1-0\n```\n"
        third = b"```pgn\n[Result \"1-0\"]\n\n1. e4 e5 1-0\n```\n"
        fourth = b"```pgn\n[Result \"1-0\"]\n\n1. e4 e5 1-0\n```\n"
        constructs = (
            b"```pgn\n\n%escape\n"
            b"1... { } ( ) ; 0-0 e.p. ++ e2-e4 e2e4 $12 foo!? *\n```\n"
        )
        empty = b"```pgn\n\n\n```\n"
        report = self.scan(first + second + third + fourth + constructs + empty)
        primary = report["movetext"]["primary_counts"]
        self.assertGreater(primary["move_number"], 0)
        self.assertGreater(primary["castle"], 0)
        self.assertGreater(primary["piece"], 0)
        self.assertGreater(primary["pawn_capture"], 0)
        self.assertGreater(primary["pawn_quiet"], 0)
        self.assertGreater(primary["unknown"], 0)
        features = report["movetext"]["feature_counts"]
        for key in features:
            self.assertGreater(features[key], 0, key)
        construct_counts = {item["key"]: item["count"] for item in report["movetext"]["constructs"]}
        for key in construct_counts:
            self.assertGreater(construct_counts[key], 0, key)
        self.assertEqual(report["movetext"]["result_agreement_counts"], {
            "indeterminate": 2, "match": 3, "mismatch": 1
        })
        token_groups = report["duplicate_candidates"]["token_sequence"]
        self.assertEqual(token_groups[0]["ordinals"], [2, 3, 4])
        self.assertEqual(report["duplicate_candidates"]["raw_movetext"][0]["ordinals"], [3, 4])
        self.assertGreater(report["movetext"]["line_wrap"]["empty_lines"], 0)
        self.assertGreater(report["movetext"]["line_wrap"]["repeated_space_lines"], 0)

    def test_samples_and_report_limit_are_bounded(self) -> None:
        unknowns = b" ".join([b"x" * 300] + [f"?{index}".encode() for index in range(40)])
        data = b"```pgn\n\n" + unknowns + b"\n```\n"
        sampled = self.scan(data)["movetext"]["unknown_tokens"]
        self.assertEqual(sampled["count"], 41)
        self.assertEqual(len(sampled["examples"]), 32)
        self.assertEqual(sampled["omitted_count"], 9)
        self.assertTrue(sampled["examples"][0]["truncated"])
        self.assertEqual(len(sampled["examples"][0]["bytes_hex"]), 512)

        dense = b"```pgn\n\n```\n" * 60_000
        self.assertLessEqual(len(dense), source_doctor.MAX_SOURCE_BYTES)
        locked = source_doctor.LockedSource(
            "docs/source.md", len(dense), hashlib.sha256(dense).hexdigest()
        )
        self.assertEqual(source_doctor.generate_report_bytes(dense, locked), source_doctor.REPORT_LIMIT_BYTES)

        unique_tags = b"".join(
            f'[A{index} "x"]\n'.encode() for index in range(2_000)
        )
        tag_dense = b"```pgn\n" + unique_tags + b"\n```\n"
        first = self.scan(tag_dense)
        self.assertEqual(first["tags"]["recognized_lines"], 2_000)
        self.assertEqual(first, self.scan(tag_dense))


@unittest.skipIf(source_doctor is None, "source doctor not present")
class SourceDoctorEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (ROOT / "docs/64_games.md").read_bytes()
        cls.locked = source_doctor.load_source_lock(ROOT)
        cls.report_bytes = (ROOT / "reports/source-doctor.json").read_bytes()
        cls.report = json.loads(cls.report_bytes)

    def test_checked_report_is_exact_deterministic_and_lexical_only(self) -> None:
        self.assertEqual(source_doctor.generate_report_bytes(self.source, self.locked), self.report_bytes)
        canonical_manifest.validate_canonical_manifest(self.report_bytes)
        self.assertEqual(set(self.report), {
            "blocks", "duplicate_candidates", "fences", "movetext", "schema",
            "scope", "source", "tags"
        })
        self.assertEqual(set(self.report["source"]), {
            "bom", "expected_bytes", "expected_sha256", "file_kind", "final_lf",
            "line_endings", "lock_match", "nfc_state", "observed_bytes",
            "observed_sha256", "path", "symlink", "tab_count",
            "trailing_horizontal_whitespace", "unexpected_controls", "utf8_valid"
        })
        self.assertEqual(set(self.report["fences"]), {
            "candidate_count", "near_misses", "nested_openers", "orphan_closers",
            "recognized_closers", "recognized_openers", "unclosed_openers"
        })
        self.assertEqual(set(self.report["tags"]), {
            "duplicate_blocks", "escape_counts", "malformed_lines", "name_stats",
            "orders", "punctuation", "recognized_lines", "separator_states",
            "special_name_counts"
        })
        self.assertEqual(set(self.report["movetext"]), {
            "constructs", "feature_counts", "final_slot_counts", "line_wrap",
            "move_numbers", "primary_counts", "ranges", "result_agreement_counts",
            "result_counts", "token_bytes", "total_tokens", "unknown_tokens"
        })
        block_keys = {
            "closer_line", "content_span", "fence_span", "lexical_final_slot",
            "lexical_ply_count", "movetext_lines", "movetext_span", "opener_line",
            "ordinal", "raw_movetext_sha256", "result_agreement", "separator_span",
            "separator_state", "tag_count", "tag_span", "token_count",
            "token_projection_sha256"
        }
        for ordinal, block in enumerate(self.report["blocks"], 1):
            self.assertEqual(set(block), block_keys)
            self.assertEqual(block["ordinal"], ordinal)
            fence_start, fence_end = block["fence_span"]
            content_start, content_end = block["content_span"]
            self.assertLessEqual(fence_start, content_start)
            self.assertLessEqual(content_end, fence_end)
            self.assertEqual(len(self.source[fence_start:fence_end]), fence_end - fence_start)
            for name in ("tag_span", "separator_span", "movetext_span"):
                span = block[name]
                self.assertIn(len(span), (0, 2))
                if span:
                    self.assertLessEqual(content_start, span[0])
                    self.assertLessEqual(span[1], content_end)
        report_text = self.report_bytes.decode("utf-8")
        for forbidden in ("canonical_game", "chess_legal", "resolved_move", "position_fen", "semantic_identity"):
            self.assertNotIn(forbidden, report_text)

    def test_current_facts_match_the_reviewed_reconnaissance(self) -> None:
        self.assertEqual(self.report["source"]["observed_bytes"], 165_145)
        self.assertEqual(self.report["source"]["line_endings"], {"bare_cr": 0, "crlf": 0, "lf": 4_376})
        self.assertTrue(self.report["source"]["lock_match"])
        self.assertEqual(self.report["fences"]["candidate_count"], 64)
        self.assertEqual(self.report["tags"]["recognized_lines"], 895)
        self.assertEqual(len(self.report["tags"]["orders"]), 7)
        self.assertEqual(self.report["movetext"]["total_tokens"], 7_456)
        primary = self.report["movetext"]["primary_counts"]
        self.assertEqual(sum(primary[name] for name in ("castle", "piece", "pawn_capture", "pawn_quiet")), 4_915)
        self.assertEqual(self.report["duplicate_candidates"], {"raw_movetext": [], "token_sequence": []})
        self.assertEqual(
            [(item["region"], item["count"]) for item in self.report["source"]["trailing_horizontal_whitespace"]],
            [("outer_markdown", 192), ("fence", 0), ("tags", 0), ("separator", 0), ("movetext", 0)],
        )

    def run_doctor(self, cwd: Path) -> subprocess.CompletedProcess[bytes]:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "python")
        return subprocess.run(
            [sys.executable, "-m", "golden_board.source_doctor"],
            cwd=cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def make_checkout(self, root: Path, data: bytes, lock_matches: bool) -> None:
        (root / "docs").mkdir()
        (root / "inputs").mkdir()
        (root / "docs/64_games.md").write_bytes(data)
        lock = (ROOT / "inputs/source-lock.toml").read_bytes()
        if lock_matches:
            lock = lock.replace(b"bytes = 165145", f"bytes = {len(data)}".encode(), 1)
            lock = lock.replace(
                b"33d44f7167ab190cc793e3fdfd8190d89ed13c1dc507c20854cf64751c7be7da",
                hashlib.sha256(data).hexdigest().encode(),
                1,
            )
        (root / "inputs/source-lock.toml").write_bytes(lock)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)

    def test_command_from_root_nested_and_failure_modes(self) -> None:
        before = hashlib.sha256(self.source).digest()
        for cwd in (ROOT, ROOT / "docs"):
            result = self.run_doctor(cwd)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, self.report_bytes)
        self.assertEqual(hashlib.sha256((ROOT / "docs/64_games.md").read_bytes()).digest(), before)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changed = b"X" + self.source[1:]
            self.make_checkout(root, changed, lock_matches=False)
            mismatch = self.run_doctor(root)
            self.assertEqual(mismatch.returncode, 1)
            self.assertFalse(json.loads(mismatch.stdout)["source"]["lock_match"])
            (root / "docs/64_games.md").unlink()
            unsafe = self.run_doctor(root)
            self.assertEqual(unsafe.returncode, 1)
            self.assertEqual(unsafe.stdout, b"")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            near_miss = b"```PGN\n" + self.source
            self.make_checkout(root, near_miss, lock_matches=True)
            result = self.run_doctor(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["fences"]["near_misses"]["count"], 1)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dense = b"```pgn\n\n```\n" * 60_000
            self.make_checkout(root, dense, lock_matches=True)
            result = self.run_doctor(root)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, source_doctor.REPORT_LIMIT_BYTES)


@unittest.skipIf(source_doctor is None, "source doctor not present")
class SourceDoctorFast(unittest.TestCase):
    def test_locked_current_source_is_gate_clean(self) -> None:
        locked = source_doctor.load_source_lock(ROOT)
        opened = source_doctor.read_locked_source(ROOT, locked)
        self.assertTrue(opened.lock_match)
        self.assertTrue(source_doctor._gate_passes(source_doctor.scan_source(opened.data, locked)))


class RepoContract(unittest.TestCase):
    REQUIRED = [
        ".gitignore", ".python-version", "AGENTS.md", "Cargo.lock", "Cargo.toml",
        "README.md", "conformance/chess-v0.json", "conformance/identity-v0.json",
        "conformance/manifest-v0.json", "conformance/source-v0.json",
        "conformance/registry.toml", "crates/gb-foundation/Cargo.toml",
        "crates/gb-foundation/src/constants.rs", "crates/gb-foundation/src/lib.rs",
        "crates/gb-foundation/tests/conformance.rs",
        "docs/64_games.md", "docs/m0-plan.md", "docs/m0-spec.md", "docs/roadmap.md",
        "docs/m1-plan.md", "docs/m1-spec.md", "docs/sources.md", "inputs/source-lock.toml", "pyproject.toml",
        "python/golden_board/__init__.py", "python/golden_board/canonical_manifest.py",
        "python/golden_board/constants.py", "python/golden_board/constants_codegen.py",
        "python/golden_board/identity.py", "python/golden_board/source_doctor.py",
        "python/tests/test_constants.py", "python/tests/test_curriculum_contract.py",
        "python/tests/test_foundation.py",
        "reports/source-doctor.json",
        "rust-toolchain.toml", "scripts/check", "spec/chess-v0.md",
        "spec/constants-v0.toml", "spec/content-v0.md", "spec/curriculum-v0.toml", "spec/identity-v0.md",
        "spec/source-v0.md", "uv.lock",
    ]

    def tracked(self) -> dict[str, str]:
        output = subprocess.run(
            ["git", "ls-files", "--stage", "--", *self.REQUIRED],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout
        return {line.split("\t", 1)[1]: line.split()[0] for line in output.splitlines()}

    def test_required_surface_is_nonempty_tracked_and_not_premature(self) -> None:
        tracked = self.tracked()
        self.assertEqual(set(tracked), set(self.REQUIRED))
        for relative in self.REQUIRED:
            self.assertGreater((ROOT / relative).stat().st_size, 0, relative)
        self.assertEqual(tracked["scripts/check"], "100755")
        self.assertTrue(os.access(ROOT / "scripts/check", os.X_OK))

        all_tracked = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, check=True, stdout=subprocess.PIPE, text=True
        ).stdout.splitlines()
        forbidden_exact = {".dockerignore", "Dockerfile", "docs/decisions.md", "flake.nix"}
        forbidden_prefixes = (".github/workflows/", "release/", "schemas/", "tools/linux/")
        self.assertFalse(forbidden_exact.intersection(all_tracked))
        self.assertFalse([path for path in all_tracked if path.startswith(forbidden_prefixes)])

    def test_text_registry_links_and_status_are_consistent(self) -> None:
        output = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        for relative in [
            *(os.fsencode(path) for path in self.REQUIRED),
            *(path for path in output.split(b"\0") if path),
        ]:
            if relative in {b"docs/64_games.md", b"reports/game-set-v0.bin"}:
                continue
            data = repo_text_bytes(ROOT, relative)
            self.assertNotIn(b"\r", data, relative)
            self.assertTrue(data.endswith(b"\n"), relative)
            for line in data.splitlines():
                self.assertFalse(line.endswith((b" ", b"\t")), relative)
                self.assertFalse(line.startswith((b"<<<<<<<", b"=======", b">>>>>>>")), relative)

        validate_conformance_registry(ROOT)

        readme = (ROOT / "README.md").read_text()
        agents = (ROOT / "AGENTS.md").read_text()
        for command in (
            "scripts/check fast", "scripts/check focused source",
            "scripts/check focused identity", "scripts/check focused repo",
            "scripts/check full",
        ):
            self.assertIn(command, readme)
            self.assertIn(command, agents)
        self.assertLessEqual(len(agents.splitlines()), 80)

        roadmap = (ROOT / "docs/roadmap.md").read_text()
        header_state = re.search(r"^\| Project state \| (.+) \|$", roadmap, re.MULTILINE).group(1)
        header_milestone = re.search(r"^\| Current milestone \| (.+) \|$", roadmap, re.MULTILINE).group(1)
        rows = re.findall(r"^\| (M[0-6] — [^|]+) \| ([^|]+) \|", roadmap, re.MULTILINE)
        current = next(((name, status.strip()) for name, status in rows if not status.strip().startswith("Complete")), None)
        if current is None:
            expected_state, expected_milestone = "Complete", "Completed project"
        else:
            expected_milestone = current[0]
            leading = current[1].split(" — ", 1)[0]
            if all(status.strip() == "Not started" for _, status in rows):
                expected_state = "Not started"
            elif leading == "Not started":
                expected_state = "In progress"
            else:
                expected_state = leading
        self.assertEqual(header_state, expected_state)
        self.assertEqual(header_milestone, expected_milestone)

    def test_chess_fixture_is_registered(self) -> None:
        registry = tomllib.loads((ROOT / "conformance/registry.toml").read_text())
        rows = [row for row in registry["suite"] if row["id"] == "chess-v0"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0],
            {
                "consumers": ["python", "rust"],
                "id": "chess-v0",
                "path": "conformance/chess-v0.json",
                "provenance": "hand-authored",
                "sha256": "9a63aa74a32761bf1f8919278e895f532e4d4f305a30f74ddd1d0c4acec6a639",
                "specification": "chess-v0",
                "version": "v0",
            },
        )

    def test_source_fixture_is_registered(self) -> None:
        registry = tomllib.loads((ROOT / "conformance/registry.toml").read_text())
        rows = [row for row in registry["suite"] if row["id"] == "source-v0"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0],
            {
                "consumers": ["python", "rust"],
                "id": "source-v0",
                "path": "conformance/source-v0.json",
                "provenance": "hand-authored",
                "sha256": "669e5550d225d3c4669e1c0902d6b05d83855b3a941a9b4c1ff1e8fbe11cfbec",
                "specification": "source-v0",
                "version": "v0",
            },
        )

    def test_source_fixture_shape_and_coverage_are_closed(self) -> None:
        payload = canonical_manifest.validate_canonical_manifest(
            repo_text_bytes(ROOT, b"conformance/source-v0.json")
        )
        self.assertEqual(set(payload), {"bases", "cases", "recipes", "schema"})
        self.assertEqual(payload["schema"], "golden-board.source-v0-fixtures/v0")
        self.assertEqual(
            payload["bases"],
            [{"id": "locked-anthology", "source_lock_id": "anthology"}],
        )
        self.assertEqual(len(payload["cases"]), 71)
        self.assertEqual(len(payload["recipes"]), 115)
        names = [row["name"] for key in ("cases", "recipes") for row in payload[key]]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(
            all(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) for name in names)
        )
        self.assertEqual(
            {
                prefix: sum(name.startswith(prefix + "-") for name in names)
                for prefix in (
                    "raw", "fence", "tag", "framing", "resource", "structure",
                    "terminal", "san", "duplicate", "binary", "evidence", "accept",
                )
            },
            {
                "raw": 44, "fence": 11, "tag": 20, "framing": 8,
                "resource": 6, "structure": 13, "terminal": 7, "san": 21,
                "duplicate": 2, "binary": 29, "evidence": 6, "accept": 19,
            },
        )
        self.assertEqual(
            {row["operation"] for key in ("cases", "recipes") for row in payload[key]},
            {
                "compile_source", "decode_game", "decode_game_set", "encode_game",
                "encode_game_set", "validate_anthology", "validate_candidate_trace",
            },
        )

        source_lock = tomllib.loads((ROOT / "inputs/source-lock.toml").read_text())
        receipts = [row for row in source_lock["source"] if row["id"] == "anthology"]
        self.assertEqual(len(receipts), 1)
        receipt = receipts[0]
        base = repo_text_bytes(ROOT, receipt["path"].encode("ascii"))
        self.assertEqual(len(base), receipt["bytes"])
        self.assertEqual(hashlib.sha256(base).hexdigest(), receipt["sha256"])

        lowercase_hex = re.compile(r"(?:[0-9a-f]{2})*")
        expected_codes = set()

        def checked_hex(value: object) -> bytes:
            self.assertIs(type(value), str)
            self.assertIsNotNone(lowercase_hex.fullmatch(value))
            self.assertLessEqual(len(value), 2 * (MAX_REPO_TEXT_BYTES + 1))
            return bytes.fromhex(value)

        def check_expected(expected: object, input_length: int) -> None:
            self.assertIs(type(expected), dict)
            self.assertIn(set(expected), ({"accept"}, {"rejection"}))
            if "accept" in expected:
                self.assertEqual(expected["accept"], {})
                return
            rejection = expected["rejection"]
            self.assertIs(type(rejection), dict)
            self.assertEqual(set(rejection), {"code", "raw_end", "raw_start"})
            self.assertIs(type(rejection["code"]), int)
            self.assertIn(rejection["code"], range(1, 69))
            expected_codes.add(rejection["code"])
            for key in ("raw_start", "raw_end"):
                self.assertIs(type(rejection[key]), int)
            self.assertLessEqual(0, rejection["raw_start"])
            self.assertLessEqual(rejection["raw_start"], rejection["raw_end"])
            self.assertLessEqual(rejection["raw_end"], input_length)

        for case in payload["cases"]:
            self.assertIs(type(case), dict)
            self.assertEqual(
                set(case), {"expected", "input_hex", "name", "operation"}
            )
            self.assertIs(type(case["name"]), str)
            self.assertIs(type(case["operation"]), str)
            raw = checked_hex(case["input_hex"])
            check_expected(case["expected"], len(raw))

        recipe_keys = {
            "literal-repeat": {
                "count_cap", "expected", "input", "input_bytes", "input_sha256",
                "name", "operation", "recipe",
            },
            "locked-base-patch": {
                "expected", "input", "input_bytes", "input_sha256", "name",
                "operation", "patch_cap", "recipe",
            },
            "knight-cycle-corpus": {
                "count_cap", "expected", "input", "input_bytes", "input_sha256",
                "name", "operation", "recipe",
            },
            "typed-game-plies": {
                "count_cap", "expected", "input", "input_bytes", "input_sha256",
                "name", "operation", "recipe",
            },
            "typed-game-set-games": {
                "count_cap", "expected", "input", "input_bytes", "input_sha256",
                "name", "operation", "recipe",
            },
            "typed-game-set-total-plies": {
                "count_cap", "expected", "input", "input_bytes", "input_sha256",
                "name", "operation", "recipe",
            },
            "typed-anthology": {
                "count_cap", "expected", "input", "input_bytes", "input_sha256",
                "name", "operation", "recipe",
            },
        }
        recipe_counts = {key: 0 for key in recipe_keys}
        for recipe in payload["recipes"]:
            self.assertIs(type(recipe), dict)
            kind = recipe["recipe"]
            self.assertIn(kind, recipe_keys)
            self.assertEqual(set(recipe), recipe_keys[kind])
            self.assertIs(type(recipe["name"]), str)
            self.assertIs(type(recipe["operation"]), str)
            recipe_counts[kind] += 1
            inputs = recipe["input"]
            self.assertIs(type(inputs), dict)
            if kind == "literal-repeat":
                self.assertEqual(
                    set(inputs), {"prefix_hex", "repeat_count", "repeat_hex", "suffix_hex"}
                )
                self.assertIs(type(recipe["count_cap"]), int)
                self.assertIs(type(inputs["repeat_count"]), int)
                self.assertLessEqual(0, inputs["repeat_count"])
                self.assertLessEqual(inputs["repeat_count"], recipe["count_cap"])
                prefix = checked_hex(inputs["prefix_hex"])
                repeated = checked_hex(inputs["repeat_hex"])
                suffix = checked_hex(inputs["suffix_hex"])
                expanded_length = (
                    len(prefix) + len(repeated) * inputs["repeat_count"] + len(suffix)
                )
                self.assertLessEqual(expanded_length, MAX_REPO_TEXT_BYTES + 1)
                raw = (
                    prefix + repeated * inputs["repeat_count"] + suffix
                )
            elif kind == "locked-base-patch":
                self.assertEqual(set(inputs), {"base", "patches"})
                self.assertEqual(inputs["base"], "locked-anthology")
                self.assertIs(type(inputs["patches"]), list)
                self.assertIs(type(recipe["patch_cap"]), int)
                self.assertLessEqual(len(inputs["patches"]), recipe["patch_cap"])
                raw_buffer = bytearray(base)
                prior_start = len(base) + 1
                expanded_length = len(base)
                for patch in inputs["patches"]:
                    self.assertIs(type(patch), dict)
                    self.assertEqual(
                        set(patch), {"old_hex", "replacement_hex", "start"}
                    )
                    self.assertIs(type(patch["start"]), int)
                    old = checked_hex(patch["old_hex"])
                    replacement = checked_hex(patch["replacement_hex"])
                    start = patch["start"]
                    self.assertLessEqual(0, start)
                    self.assertLessEqual(start + len(old), len(base))
                    self.assertLess(start, prior_start)
                    self.assertLessEqual(start + len(old), prior_start)
                    self.assertEqual(base[start:start + len(old)], old)
                    self.assertEqual(raw_buffer[start:start + len(old)], old)
                    expanded_length += len(replacement) - len(old)
                    self.assertLessEqual(expanded_length, MAX_REPO_TEXT_BYTES + 1)
                    raw_buffer[start:start + len(old)] = replacement
                    prior_start = start
                raw = bytes(raw_buffer)
            elif kind == "knight-cycle-corpus":
                self.assertIn(
                    set(inputs),
                    (
                        {"cycle", "ply_counts", "result"},
                        {"cycle", "newline_hex", "ply_counts", "result"},
                    ),
                )
                self.assertEqual(inputs["cycle"], ["Nf3", "Nf6", "Ng1", "Ng8"])
                self.assertEqual(inputs["result"], "1/2-1/2")
                self.assertIs(type(inputs["ply_counts"]), list)
                self.assertLessEqual(len(inputs["ply_counts"]), recipe["count_cap"])
                self.assertTrue(all(type(count) is int for count in inputs["ply_counts"]))
                self.assertLessEqual(sum(inputs["ply_counts"]), 65_536)
                newline = checked_hex(inputs.get("newline_hex", "0a"))
                self.assertIn(newline, (b"\n", b"\r\n"))
                blocks = []
                cycle = [token.encode("ascii") for token in inputs["cycle"]]
                for count in inputs["ply_counts"]:
                    self.assertIn(count, range(1, 4097))
                    tokens = []
                    for ply in range(count):
                        if ply % 2 == 0:
                            tokens.append(f"{ply // 2 + 1}.".encode("ascii"))
                        tokens.append(cycle[ply % 4])
                    tokens.append(b"1/2-1/2")
                    blocks.append(
                        newline.join(
                            (b"```pgn", b'[Result "1/2-1/2"]', b"",
                             b" ".join(tokens), b"```", b"")
                        )
                    )
                raw = b"".join(blocks)
            elif kind in {"typed-game-plies", "typed-game-set-games"}:
                self.assertEqual(set(inputs), {"count", "unit_hex"})
                self.assertIs(type(inputs["count"]), int)
                self.assertLessEqual(0, inputs["count"])
                self.assertLessEqual(inputs["count"], recipe["count_cap"])
                unit = checked_hex(inputs["unit_hex"])
                self.assertLessEqual(
                    len(unit) * inputs["count"], MAX_REPO_TEXT_BYTES + 1
                )
                raw = unit * inputs["count"]
            elif kind == "typed-game-set-total-plies":
                self.assertEqual(set(inputs), {"move_hex", "ply_counts", "score"})
                move = checked_hex(inputs["move_hex"])
                self.assertEqual(len(move), 2)
                self.assertIs(type(inputs["ply_counts"]), list)
                self.assertLessEqual(len(inputs["ply_counts"]), recipe["count_cap"])
                self.assertTrue(all(type(count) is int for count in inputs["ply_counts"]))
                self.assertLessEqual(sum(inputs["ply_counts"]), 65_536)
                self.assertIs(type(inputs["score"]), int)
                self.assertIn(inputs["score"], (0, 1, 2))
                pieces = []
                for count in inputs["ply_counts"]:
                    self.assertIn(count, range(1, 4097))
                    pieces.append(count.to_bytes(2, "big") + move * count + bytes([inputs["score"]]))
                raw = b"".join(pieces)
            else:
                self.assertEqual(
                    set(inputs), {"cycle_moves_hex", "ply_counts", "score"}
                )
                cycle = checked_hex(inputs["cycle_moves_hex"])
                self.assertEqual(len(cycle), 8)
                self.assertIs(type(inputs["ply_counts"]), list)
                self.assertLessEqual(len(inputs["ply_counts"]), recipe["count_cap"])
                self.assertTrue(all(type(count) is int for count in inputs["ply_counts"]))
                self.assertLessEqual(sum(inputs["ply_counts"]), 65_536)
                self.assertIs(type(inputs["score"]), int)
                self.assertIn(inputs["score"], (0, 1, 2))
                pieces = []
                for count in inputs["ply_counts"]:
                    self.assertIn(count, range(1, 4097))
                    moves = (cycle * ((count + 3) // 4))[:count * 2]
                    pieces.append(count.to_bytes(2, "big") + moves + bytes([inputs["score"]]))
                raw = b"".join(pieces)

            self.assertLessEqual(len(raw), MAX_REPO_TEXT_BYTES + 1)
            self.assertIs(type(recipe["input_bytes"]), int)
            self.assertEqual(len(raw), recipe["input_bytes"])
            self.assertIs(type(recipe["input_sha256"]), str)
            self.assertIsNotNone(re.fullmatch(r"[0-9a-f]{64}", recipe["input_sha256"]))
            self.assertEqual(hashlib.sha256(raw).hexdigest(), recipe["input_sha256"])
            check_expected(recipe["expected"], len(raw))

        self.assertEqual(
            recipe_counts,
            {
                "literal-repeat": 14, "locked-base-patch": 88,
                "knight-cycle-corpus": 4, "typed-game-plies": 1,
                "typed-game-set-games": 2, "typed-game-set-total-plies": 2,
                "typed-anthology": 4,
            },
        )
        self.assertEqual(expected_codes, set(range(1, 69)))
        self.assertNotIn(69, expected_codes)
        self.assertNotIn(70, expected_codes)

    def test_chess_fixture_shape_and_coverage_are_closed(self) -> None:
        payload = canonical_manifest.validate_canonical_manifest(
            repo_text_bytes(ROOT, b"conformance/chess-v0.json")
        )
        self.assertEqual(set(payload), {"cases", "recipes", "schema"})
        self.assertEqual(payload["schema"], "golden-board.chess-v0-fixtures/v0")

        cases = payload["cases"]
        self.assertEqual(len(cases), 224)
        names = [case["name"] for case in cases]
        self.assertEqual(len(set(names)), len(names))
        self.assertTrue(all(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) for name in names))
        self.assertEqual(
            {case["operation"] for case in cases},
            {
                "apply_event", "apply_move", "controls_square", "decode_event",
                "decode_move", "decode_position", "evaluate_predicate", "legal_moves",
                "pseudo_legal_moves", "repetition_key", "replay_from_start",
                "validate_local", "validate_source_record",
            },
        )
        self.assertEqual(
            {
                prefix: sum(name.startswith(prefix + "-") for name in names)
                for prefix in (
                    "wire", "structural", "local", "geometry", "castling",
                    "en-passant", "promotion", "terminal", "history", "event",
                    "record", "predicate", "precedence",
                )
            },
            {
                "wire": 14, "structural": 17, "local": 20, "geometry": 19,
                "castling": 15, "en-passant": 11, "promotion": 11, "terminal": 7,
                "history": 8, "event": 21, "record": 13, "predicate": 60,
                "precedence": 8,
            },
        )
        required = {
            "wire-position-initial", "wire-initial-legal-moves",
            "local-lowest-square-tie", "geometry-king-capture-removes-blocker-self-check",
            "castling-failure-origin-safe-transit-attack",
            "en-passant-pinned-effective-key-omitted", "promotion-immediate-checkmate",
            "en-passant-geometry-after-nominal-target",
            "terminal-stalemate-precedes-common-dead",
            "terminal-king-two-knights-versus-king-not-common-dead",
            "history-pawn-move-resets-halfmove", "event-after-claimed-fifty-move-closure",
            "record-common-dead-second-win-contradiction",
            "predicate-correct-discovered-attack-check",
            "predicate-correct-finite-mating-geometry", "predicate-tree-defect-depth",
            "predicate-closed-fork-seventeen-before-resource",
            "predicate-resource-node-count-4097", "predicate-resource-edges-per-node-257",
            "predicate-resource-total-edges-4096",
            *(f"precedence-layer-{letter}-{suffix}" for letter, suffix in (
                ("a", "structure"), ("b", "local"), ("c", "closure"),
                ("d", "resource"), ("e", "illegal-move"), ("f", "invalid-event"),
                ("g", "finite-proof"), ("h", "source-record"),
            )),
        }
        self.assertTrue(required.issubset(names))
        input_shapes = {
            "apply_event": {"event_hex": str, "events_hex": list},
            "apply_move": {"move_hex": str, "moves_hex": str},
            "controls_square": {"position_hex": str, "side": int, "target": int},
            "decode_event": {"event_hex": str},
            "decode_move": {"move_hex": str},
            "decode_position": {"position_hex": str},
            "evaluate_predicate": {"input": dict, "predicate_id": str},
            "legal_moves": {"moves_hex": str},
            "pseudo_legal_moves": {"position_hex": str},
            "repetition_key": {"moves_hex": str},
            "replay_from_start": {"moves_hex": str},
            "validate_local": {"position_hex": str},
            "validate_source_record": {"moves_hex": str, "score": int},
        }
        success_shapes = {
            "apply_event": ({"cause": dict, "score": int, "status": int},),
            "apply_move": (
                {"position_hex": str},
                {"halfmove_clock": int, "position_hex": str},
                {"king_in_check": bool, "position_hex": str, "terminal": int},
            ),
            "controls_square": ({"squares": list},),
            "decode_event": ({"event_hex": str},),
            "decode_move": ({"move_hex": str},),
            "decode_position": ({"position_hex": str},),
            "evaluate_predicate": ({"result": dict},),
            "legal_moves": ({"moves_hex": str},),
            "pseudo_legal_moves": ({"moves_hex": str},),
            "repetition_key": ({"repetition_key_hex": str},),
            "replay_from_start": (
                {"common_dead": bool, "terminal": int},
                {"common_dead": bool, "terminal": int, "winning_side": int},
            ),
            "validate_source_record": (
                {"score": int, "terminal": int},
                {
                    "fifty_move_available": bool,
                    "score": int,
                    "terminal": int,
                    "threefold_available": bool,
                },
            ),
        }
        predicate_input_shapes = {
            "chess.absolute_pin": {"origin": int, "position_hex": str, "variant": str},
            "chess.control": {"position_hex": str, "side": int, "target": int, "variant": str},
            "chess.declaration_event": {"event_hex": str, "events_hex": list, "variant": str},
            "chess.defended": {"defender": dict, "position_hex": str, "target": int, "variant": str},
            "chess.discovered_attack_check": {"move_hex": str, "moves_hex": str, "slider_origin": int, "target": int, "variant": str},
            "chess.escape_square_control": {"candidate": int, "position_hex": str, "side": int, "variant": str},
            "chess.finite_mating_geometry": {"mating_side": int, "moves_hex": str, "nodes": list, "variant": str},
            "chess.finite_promotion_race": {"moves_hex": str, "nodes": list, "variant": str},
            "chess.fork_double_attack": {"move_hex": str, "moves_hex": str, "targets": list, "variant": str},
            "chess.history_claim": {"moves_hex": str, "variant": str},
            "chess.king_check": {"position_hex": str, "side": int, "variant": str},
            "chess.move_legality": {"move_hex": str, "moves_hex": str, "variant": str},
            "chess.move_record_replay": {"move_hex": str, "variant": str},
            "chess.occupancy": {"match": dict, "position_hex": str, "square": int, "variant": str},
            "chess.open_file": {"file": int, "position_hex": str, "variant": str},
            "chess.passed_pawn": {"pawn_square": int, "position_hex": str, "variant": str},
            "chess.semi_open_file": {"file": int, "position_hex": str, "side": int, "variant": str},
            "chess.setup_turn": {"position_hex": str, "variant": str},
            "chess.source_score_relation": {"moves_hex": str, "score": int, "variant": str},
            "chess.terminal_transition": {"move_hex": str, "moves_hex": str, "variant": str},
            "chess.unknown": {"position_hex": str, "variant": str},
        }
        predicate_result_shapes = {
            **{
                predicate_id: {"value": bool}
                for predicate_id in (
                    "chess.absolute_pin", "chess.defended", "chess.discovered_attack_check",
                    "chess.escape_square_control", "chess.fork_double_attack",
                    "chess.king_check", "chess.occupancy", "chess.open_file",
                    "chess.passed_pawn", "chess.semi_open_file", "chess.setup_turn",
                )
            },
            "chess.control": {"squares": list},
            "chess.declaration_event": {"cause": dict, "kind": str, "score": int, "status": int},
            "chess.finite_mating_geometry": {"all_branches_mate": bool, "mating_side": int, "max_plies": int},
            "chess.finite_promotion_race": {"outcomes": list},
            "chess.history_claim": {
                "current_key_occurrences": int,
                "effective_ep": dict,
                "fifty_move_available": bool,
                "halfmove_clock": int,
                "nominal_ep": dict,
                "played_plies": int,
                "threefold_available": bool,
            },
            "chess.move_legality": {"kind": str},
            "chess.move_record_replay": {"kind": str, "move_hex": str},
            "chess.source_score_relation": {"kind": str, "terminal": int},
            "chess.terminal_transition": {"terminal": int, "winning_side": int},
        }
        cause_shapes = (
            {"kind": str},
            {"kind": str, "side": int},
            {"kind": str, "terminal": int},
            {"kind": str, "terminal": int, "winning_side": int},
        )
        for case in cases:
            self.assertEqual(set(case), {"expected", "input", "name", "operation"})
            self.assertIsInstance(case["input"], dict)
            input_shape = input_shapes[case["operation"]]
            self.assertEqual(set(case["input"]), set(input_shape))
            for key, expected_type in input_shape.items():
                self.assertIs(type(case["input"][key]), expected_type)
            self.assertEqual(len(case["expected"]), 1)
            self.assertIn(next(iter(case["expected"])), {"rejection", "success"})
            if "rejection" in case["expected"]:
                self.assertIs(type(case["expected"]["rejection"]), int)
                self.assertIn(case["expected"]["rejection"], range(1, 63))
            else:
                success = case["expected"]["success"]
                self.assertIsInstance(success, dict)
                matching = [
                    shape
                    for shape in success_shapes[case["operation"]]
                    if set(success) == set(shape)
                ]
                self.assertEqual(len(matching), 1)
                for key, expected_type in matching[0].items():
                    self.assertIs(type(success[key]), expected_type)

            if case["operation"] == "apply_event":
                self.assertTrue(all(type(item) is str for item in case["input"]["events_hex"]))
                if "success" in case["expected"]:
                    cause = case["expected"]["success"]["cause"]
                    matching_causes = [shape for shape in cause_shapes if set(cause) == set(shape)]
                    self.assertEqual(len(matching_causes), 1)
                    for key, expected_type in matching_causes[0].items():
                        self.assertIs(type(cause[key]), expected_type)
            if case["operation"] == "controls_square" and "success" in case["expected"]:
                self.assertTrue(
                    all(type(square) is int for square in case["expected"]["success"]["squares"])
                )
            if case["operation"] == "evaluate_predicate":
                predicate_id = case["input"]["predicate_id"]
                predicate_input = case["input"]["input"]
                predicate_shape = predicate_input_shapes[predicate_id]
                if set(predicate_input) == {"variant"}:
                    self.assertEqual(case["expected"], {"rejection": 15})
                    self.assertIs(type(predicate_input["variant"]), str)
                else:
                    self.assertEqual(set(predicate_input), set(predicate_shape))
                    for key, expected_type in predicate_shape.items():
                        self.assertIs(type(predicate_input[key]), expected_type)
                    if "match" in predicate_input:
                        self.assertEqual(set(predicate_input["match"]), {"kind", "piece", "side"})
                        self.assertIs(type(predicate_input["match"]["kind"]), str)
                        self.assertIs(type(predicate_input["match"]["piece"]), int)
                        self.assertIs(type(predicate_input["match"]["side"]), int)
                    if "defender" in predicate_input:
                        self.assertEqual(set(predicate_input["defender"]), {"kind", "square"})
                        self.assertIs(type(predicate_input["defender"]["kind"]), str)
                        self.assertIs(type(predicate_input["defender"]["square"]), int)
                    if "targets" in predicate_input:
                        self.assertTrue(all(type(target) is int for target in predicate_input["targets"]))
                    if "events_hex" in predicate_input:
                        self.assertTrue(all(type(event) is str for event in predicate_input["events_hex"]))
                    if "nodes" in predicate_input:
                        for node in predicate_input["nodes"]:
                            self.assertIs(type(node), dict)
                            self.assertEqual(set(node), {"edges"})
                            self.assertIs(type(node["edges"]), list)
                            for edge in node["edges"]:
                                self.assertIs(type(edge), dict)
                                self.assertEqual(set(edge), {"child", "move_hex"})
                                self.assertIs(type(edge["child"]), int)
                                self.assertIs(type(edge["move_hex"]), str)
                if "success" in case["expected"]:
                    result = case["expected"]["success"]["result"]
                    result_shape = predicate_result_shapes[predicate_id]
                    self.assertEqual(set(result), set(result_shape))
                    for key, expected_type in result_shape.items():
                        self.assertIs(type(result[key]), expected_type)
                    if "squares" in result:
                        self.assertTrue(all(type(square) is int for square in result["squares"]))
                    if "outcomes" in result:
                        self.assertTrue(all(type(outcome) is str for outcome in result["outcomes"]))
                    if "cause" in result:
                        self.assertEqual(set(result["cause"]), {"kind", "side"})
                        self.assertIs(type(result["cause"]["kind"]), str)
                        self.assertIs(type(result["cause"]["side"]), int)
                    for key in ("effective_ep", "nominal_ep"):
                        if key in result:
                            ep = result[key]
                            self.assertIn(set(ep), ({"kind"}, {"kind", "square"}))
                            self.assertIs(type(ep["kind"]), str)
                            if "square" in ep:
                                self.assertIs(type(ep["square"]), int)

        def check_hex(value: object) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key.endswith("_hex"):
                        values = item if isinstance(item, list) else [item]
                        self.assertTrue(all(isinstance(part, str) for part in values))
                        self.assertTrue(all(re.fullmatch(r"(?:[0-9a-f]{2})*", part) for part in values))
                        if key == "moves_hex":
                            self.assertTrue(all(len(part) % 4 == 0 for part in values))
                    check_hex(item)
            elif isinstance(value, list):
                for item in value:
                    check_hex(item)

        check_hex(payload)
        recipes = payload["recipes"]
        self.assertEqual([recipe["name"] for recipe in recipes], [
            "history-boundary-4095", "history-boundary-4096", "history-excess-4097",
        ])
        expected_recipe_facts = (
            (4095, "", 8190, "fe083157aff7dddf8ef1d7c55d14d74836351de95367107f2382c465ba670735", {"success": {"played_plies": 4095}}),
            (4096, "", 8192, "39b9ad3d90be853994abbf8fba476816fcc15865f9fdf99f26a33673e0972616", {"success": {"played_plies": 4096}}),
            (4097, "4180", 8194, "b2b5803f901288658064cbd1c05ff36db5b6fe73f99d68941e85178b968c5abc", {"rejection": 35}),
        )
        for recipe, (plies, final_move, byte_count, digest, expected) in zip(recipes, expected_recipe_facts):
            self.assertEqual(set(recipe), {
                "count_cap", "expected", "input", "input_bytes", "input_sha256", "name", "recipe",
            })
            self.assertEqual(recipe["recipe"], "knight-cycle-history")
            self.assertIs(type(recipe["count_cap"]), int)
            self.assertEqual(recipe["count_cap"], 4097)
            self.assertIs(type(recipe["input"]), dict)
            self.assertEqual(set(recipe["input"]), {"cycle_moves_hex", "final_move_hex", "ply_count"})
            self.assertEqual(recipe["expected"], expected)
            if "success" in expected:
                self.assertIs(type(recipe["expected"]["success"]["played_plies"]), int)
            else:
                self.assertIs(type(recipe["expected"]["rejection"]), int)
            self.assertIs(type(recipe["input"]["ply_count"]), int)
            self.assertEqual(recipe["input"]["ply_count"], plies)
            self.assertIs(type(recipe["input"]["final_move_hex"]), str)
            self.assertEqual(recipe["input"]["final_move_hex"], final_move)
            prefix_plies = plies - bool(final_move)
            cycle = recipe["input"]["cycle_moves_hex"]
            self.assertIs(type(cycle), str)
            self.assertEqual(cycle, "1950fad05460b7e0")
            constructed = (cycle * ((prefix_plies + 3) // 4))[: prefix_plies * 4] + final_move
            raw = bytes.fromhex(constructed)
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (byte_count, digest))
            self.assertIs(type(recipe["input_bytes"]), int)
            self.assertIs(type(recipe["input_sha256"]), str)
            self.assertEqual((recipe["input_bytes"], recipe["input_sha256"]), (byte_count, digest))

    def test_chess_fixture_shape_mutations_fail_closed(self) -> None:
        payload = canonical_manifest.validate_canonical_manifest(CHESS_FIXTURE.read_bytes())

        def extra_input(value: dict[str, object]) -> None:
            value["cases"][0]["input"]["extra"] = 1

        def extra_success(value: dict[str, object]) -> None:
            value["cases"][0]["expected"]["success"]["extra"] = 1

        def wrong_recipe_branch(value: dict[str, object]) -> None:
            value["recipes"][0]["expected"] = {"rejection": 1}

        def wrong_recipe_type(value: dict[str, object]) -> None:
            value["recipes"][0]["expected"]["success"]["played_plies"] = "4095"

        def predicate_input_extra(value: dict[str, object]) -> None:
            case = next(
                case for case in value["cases"]
                if case["name"] == "predicate-correct-setup-turn"
            )
            case["input"]["input"]["extra"] = 1

        def predicate_result_type(value: dict[str, object]) -> None:
            case = next(
                case for case in value["cases"]
                if case["name"] == "predicate-correct-fork-double-attack"
            )
            case["expected"]["success"]["result"]["value"] = 1

        for name, mutate in {
            "extra operation input": extra_input,
            "extra operation success": extra_success,
            "wrong recipe branch": wrong_recipe_branch,
            "wrong recipe result type": wrong_recipe_type,
            "extra predicate input": predicate_input_extra,
            "wrong predicate result type": predicate_result_type,
        }.items():
            with self.subTest(name=name):
                mutated = copy.deepcopy(payload)
                mutate(mutated)
                data = canonical_manifest.serialize_manifest(mutated)
                with mock.patch.object(
                    sys.modules[__name__], "repo_text_bytes", return_value=data
                ):
                    with self.assertRaises(AssertionError):
                        self.test_chess_fixture_shape_and_coverage_are_closed()

        oversized = copy.deepcopy(payload)
        oversized["recipes"][0]["input"]["cycle_moves_hex"] += "00"
        data = canonical_manifest.serialize_manifest(oversized)
        with mock.patch.object(sys.modules[__name__], "repo_text_bytes", return_value=data):
            with mock.patch.object(hashlib, "sha256", side_effect=RuntimeError("expanded")):
                with self.assertRaises(AssertionError):
                    self.test_chess_fixture_shape_and_coverage_are_closed()

    def test_conformance_registry_mutations_fail_closed(self) -> None:
        payload = b"fixture\n"
        digest = hashlib.sha256(payload).hexdigest().encode()
        registry = (
            b'schema = "golden-board.conformance-registry/v0"\n\n'
            b"[[suite]]\n"
            b'id = "identity-v0"\n'
            b'path = "conformance/identity-v0.json"\n'
            b'specification = "identity-v0"\n'
            b'version = "v0"\n'
            + b'sha256 = "' + digest + b'"\n'
            b'consumers = ["python", "rust"]\n'
            b'provenance = "hand-authored"\n'
        )
        mutations = {
            "missing_top_key": registry.replace(
                b'schema = "golden-board.conformance-registry/v0"\n\n', b""
            ),
            "missing_suite": b'schema = "golden-board.conformance-registry/v0"\n',
            "extra_top_key": registry.replace(
                b"\n\n[[suite]]", b"\nextra = true\n\n[[suite]]"
            ),
            "bad_schema": registry.replace(b"registry/v0", b"registry/v1"),
            "missing_row_key": registry.replace(b'version = "v0"\n', b""),
            "extra_row_key": registry + b'extra = "x"\n',
            "bad_id_empty": registry.replace(b'id = "identity-v0"', b'id = ""'),
            "bad_id_uppercase": registry.replace(b"identity-v0", b"Identity-v0", 1),
            "bad_id_hyphens": registry.replace(b"identity-v0", b"identity--v0", 1),
            "bad_specification": registry.replace(
                b'specification = "identity-v0"', b'specification = "identity_v0"'
            ),
            "empty_path": registry.replace(
                b'path = "conformance/identity-v0.json"', b'path = ""'
            ),
            "parent_path": registry.replace(
                b'path = "conformance/identity-v0.json"', b'path = "../identity-v0.json"'
            ),
            "absolute_path": registry.replace(
                b'path = "conformance/identity-v0.json"', b'path = "/identity-v0.json"'
            ),
            "nested_path": registry.replace(
                b'path = "conformance/identity-v0.json"',
                b'path = "conformance/nested/identity-v0.json"',
            ),
            "backslash_alias": registry.replace(
                b'path = "conformance/identity-v0.json"',
                br"path = 'conformance\identity-v0.json'",
            ),
            "nul_path": registry.replace(
                b'path = "conformance/identity-v0.json"',
                br'path = "conformance/identity-v0\u0000.json"',
            ),
            "dot_path": registry.replace(
                b'path = "conformance/identity-v0.json"', b'path = "."'
            ),
            "dot_dot_path": registry.replace(
                b'path = "conformance/identity-v0.json"', b'path = ".."'
            ),
            "alternate_path": registry.replace(
                b'path = "conformance/identity-v0.json"',
                b'path = "conformance/./identity-v0.json"',
            ),
            "registry_self_path": registry.replace(
                b'path = "conformance/identity-v0.json"',
                b'path = "conformance/registry.toml"',
            ),
            "bad_version": registry.replace(b'version = "v0"', b'version = "v1"'),
            "bad_hash": registry.replace(digest, b"A" * 64),
            "bad_consumers": registry.replace(
                b'["python", "rust"]', b'["rust", "python"]'
            ),
            "bad_provenance": registry.replace(b"hand-authored", b"generated"),
            "duplicate_id": registry + b"[[suite]]\n" + registry.split(b"[[suite]]\n", 1)[1],
            "duplicate_path": registry
            + b"[[suite]]\n"
            + registry.split(b"[[suite]]\n", 1)[1].replace(
                b'id = "identity-v0"', b'id = "manifest-v0"'
            ),
            "oversized_registry": registry
            + b" " * (MAX_REPO_TEXT_BYTES + 1 - len(registry)),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix="registry-contract-"
            ) as directory:
                root = Path(directory)
                (root / "conformance").mkdir()
                (root / "conformance/registry.toml").write_bytes(mutation)
                (root / "conformance/identity-v0.json").write_bytes(payload)
                with self.assertRaises(AssertionError):
                    validate_conformance_registry(root)

    def test_conformance_registry_tree_and_payload_bounds(self) -> None:
        def write_valid(root: Path, payload: bytes = b"fixture\n") -> Path:
            conformance = root / "conformance"
            conformance.mkdir()
            digest = hashlib.sha256(payload).hexdigest()
            (conformance / "registry.toml").write_text(
                'schema = "golden-board.conformance-registry/v0"\n\n'
                "[[suite]]\n"
                'id = "identity-v0"\n'
                'path = "conformance/identity-v0.json"\n'
                'specification = "identity-v0"\n'
                'version = "v0"\n'
                f'sha256 = "{digest}"\n'
                'consumers = ["python", "rust"]\n'
                'provenance = "hand-authored"\n'
            )
            path = conformance / "identity-v0.json"
            path.write_bytes(payload)
            return path

        for name in (
            "missing_target",
            "unregistered_payload",
            "direct_symlink",
            "non_regular_target",
            "hash_mismatch",
            "inventory_mismatch",
            "unexpected_symlink",
            "registry_symlink",
            "registry_non_regular",
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix="registry-contract-"
            ) as directory:
                root = Path(directory)
                path = write_valid(root)
                if name == "missing_target":
                    path.unlink()
                elif name == "unregistered_payload":
                    (root / "conformance/manifest-v0.json").write_bytes(b"extra\n")
                elif name == "direct_symlink":
                    path.unlink()
                    target = root / "target.json"
                    target.write_bytes(b"fixture\n")
                    path.symlink_to(target)
                elif name == "non_regular_target":
                    path.unlink()
                    path.mkdir()
                elif name == "hash_mismatch":
                    path.write_bytes(b"changed\n")
                elif name == "inventory_mismatch":
                    path.unlink()
                    (root / "conformance/manifest-v0.json").write_bytes(b"fixture\n")
                elif name == "unexpected_symlink":
                    target = root / "target.json"
                    target.write_bytes(b"extra\n")
                    (root / "conformance/extra.json").symlink_to(target)
                else:
                    registry_path = root / "conformance/registry.toml"
                    registry = registry_path.read_bytes()
                    registry_path.unlink()
                    if name == "registry_symlink":
                        target = root / "registry.toml"
                        target.write_bytes(registry)
                        registry_path.symlink_to(target)
                    else:
                        registry_path.mkdir()
                with self.assertRaises(AssertionError):
                    validate_conformance_registry(root)

        for size, accepted in (
            (MAX_REPO_TEXT_BYTES, True),
            (MAX_REPO_TEXT_BYTES + 1, False),
        ):
            with self.subTest(size=size), tempfile.TemporaryDirectory(
                prefix="registry-contract-"
            ) as directory:
                root = Path(directory)
                write_valid(root, b"x" * size)
                if accepted:
                    validate_conformance_registry(root)
                else:
                    with self.assertRaises(AssertionError):
                        validate_conformance_registry(root)

    def test_untracked_text_scan_rejects_unsafe_files(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT, prefix="repo-contract-") as directory:
            root = Path(directory)
            (root / "regular.txt").write_bytes(b"regular\n")
            (root / "newline\nname.txt").write_bytes(b"newline\n")
            self.test_text_registry_links_and_status_are_consistent()
            self.assertEqual(repo_text_bytes(root, b"regular.txt"), b"regular\n")
            for relative in (b"/absolute", b"../outside", b"regular.txt/../outside"):
                with self.subTest(relative=relative), self.assertRaises(AssertionError):
                    repo_text_bytes(root, relative)

            safe_directory = root / "safe-directory"
            safe_directory.mkdir()
            (safe_directory / "inside.txt").write_bytes(b"inside\n")
            (root / "directory-link").symlink_to(safe_directory, target_is_directory=True)
            with self.assertRaises(AssertionError):
                repo_text_bytes(root, b"directory-link/inside.txt")
            (root / "directory-link").unlink()

            target = root / "target.txt"
            target.write_bytes(b"target\n")
            (root / "link.txt").symlink_to(target)
            with self.assertRaises(AssertionError):
                self.test_text_registry_links_and_status_are_consistent()
            (root / "link.txt").unlink()

            (root / "oversize.txt").write_bytes(b"x" * (1_048_576 + 1))
            with self.assertRaises(AssertionError):
                self.test_text_registry_links_and_status_are_consistent()
            (root / "oversize.txt").unlink()

            if hasattr(os, "mkfifo"):
                fifo = root / "pipe"
                os.mkfifo(fifo)
                try:
                    with self.assertRaises(AssertionError):
                        repo_text_bytes(root, b"pipe")
                finally:
                    fifo.unlink()

    def test_m1_admission_policy(self) -> None:
        check = (ROOT / "scripts/check").read_text()
        self.assertIn("cargo test -p gb-foundation", check)
        self.assertIn("git diff --check || return 1", check)
        self.assertIn("git diff --cached --check || return 1", check)
        identity_block = check.split("identity() {", 1)[1].split("\n}\n", 1)[0]
        repo_block = check.split("repo() {", 1)[1].split("\n}\n", 1)[0]
        self.assertNotIn("--workspace", identity_block)
        self.assertNotIn("git diff --check -- ", repo_block)
        self.assertNotIn("git diff --cached --check -- ", repo_block)

        roadmap = (ROOT / "docs/roadmap.md").read_text()
        self.assertIn(
            "| M1 — Chess truth, source grammar, and assessment blueprint | In progress | — |",
            roadmap,
        )

    def test_m1_portable_evidence_and_run_state_owners_are_explicit(self) -> None:
        source = " ".join((ROOT / "spec/source-v0.md").read_text().split())
        content = " ".join((ROOT / "spec/content-v0.md").read_text().split())
        m1_spec = " ".join((ROOT / "docs/m1-spec.md").read_text().split())
        m1_plan = " ".join((ROOT / "docs/m1-plan.md").read_text().split())

        self.assertIn(
            "`conformance/source-v0.json` is the portable shared fixture. It owns "
            "exact raw-byte and typed-operation cases through "
            "`SOURCE_EVIDENCE_CROSS_FIELD`.",
            source,
        )
        self.assertIn(
            "`SOURCE_CANDIDATE_MISMATCH` is P5 coordinator evidence constructed "
            "only after two individually valid candidates.",
            source,
        )
        self.assertIn(
            "`SOURCE_EVIDENCE_INSTALL` is language-local host-adapter failure and "
            "interruption evidence.",
            source,
        )
        self.assertIn(
            "Neither latter case is a portable shared-fixture input; both retain "
            "the owner-defined canonical span `[0,0)`.",
            source,
        )
        self.assertIn(
            "`global_remaining <= root.global_event_budget`; failure spans "
            "`global_remaining` `[6,8)`; "
            "`local_remaining <= current_node.item_event_budget`; failure spans "
            "`local_remaining` `[8,10)`; "
            "`local_remaining <= global_remaining`; failure spans "
            "`local_remaining` `[8,10)`. "
            "Active requires both remaining values nonzero; exhausted requires at "
            "least one zero; committed permits either. A phase/budget mismatch "
            "spans `phase` `[10,11)`.",
            content,
        )
        self.assertIn(
            "Hand-authored portable fixtures cover exact raw-byte or "
            "typed-operation inputs and expected code/span for every rejection "
            "through `SOURCE_EVIDENCE_CROSS_FIELD`, including:",
            source,
        )
        self.assertNotIn(
            "fixtures cover exact raw bytes and expected code/span for every "
            "rejection above",
            source,
        )
        self.assertIn(
            "Literal boundary-plus-one evidence is required whenever representable.",
            content,
        )
        full_width = (
            "When a wire maximum fills its field (for example `u16` 65,535), "
            "commit the literal maximum encoding and test one additional "
            "host/runtime element or operation without encoding wrap; rejection "
            "or exhaustion is atomic with no output/state mutation."
        )
        self.assertIn(full_width, content)
        for overview in (m1_spec, m1_plan):
            self.assertIn(
                "Shared source fixtures are portable raw/typed inputs; P5 owns "
                "candidate mismatch, and adapter-local tests own install/interruption.",
                overview,
            )
            self.assertIn(full_width, overview)

    def test_m1_chess_and_source_owners_are_closed(self) -> None:
        chess = (ROOT / "spec/chess-v0.md").read_text()
        source = (ROOT / "spec/source-v0.md").read_text()
        design = (ROOT / "docs/m1-spec.md").read_text()
        design_words = " ".join(design.split())

        self.assertIn("sole owner of Golden Board v0 chess types", chess)
        self.assertIn("sole owner of Golden Board v0 raw Markdown", source)
        self.assertIn("sole normative owner of chess bytes", design_words)
        self.assertIn("sole normative owner of raw grammar", design_words)
        self.assertIsNone(re.search(r"\b(?:TODO|TBD|FIXME|XXX)\b", chess + source))

        operations = {
            "decode_position", "encode_position", "decode_move", "encode_move",
            "decode_event", "encode_event", "validate_local",
            "controls_square", "king_in_check", "pseudo_legal_moves",
            "replay_from_start", "legal_moves", "apply_move",
            "repetition_key", "board_terminal", "common_dead", "new_game",
            "apply_event", "validate_source_record", "evaluate_predicate",
        }
        api = chess.split("## 5. Public logical API", 1)[1].split(
            "## 6. Board semantics", 1
        )[0]
        api_block = api.split("```text", 1)[1].split("```", 1)[0]
        self.assertEqual(
            set(re.findall(r"^([a-z_]+)\(", api_block, re.MULTILINE)),
            operations,
        )

        source_operations = {
            "compile_source", "encode_game", "decode_game",
            "validate_anthology", "encode_game_set", "decode_game_set",
            "encode_candidate_trace", "validate_candidate_trace",
            "coordinate_candidates", "validate_retained_evidence",
        }
        source_api = source.split("### 1.2 Logical API", 1)[1].split(
            "## 2. Input profile and spans", 1
        )[0]
        source_api_block = source_api.split("```text", 1)[1].split("```", 1)[0]
        self.assertEqual(
            set(re.findall(r"^([a-z_]+)\(", source_api_block, re.MULTILINE)),
            source_operations,
        )

        predicates = set(
            re.findall(r"^\| `(chess\.[a-z0-9_]+)` \|", chess, re.MULTILINE)
        )
        self.assertEqual(
            predicates,
            {
                "chess.setup_turn", "chess.occupancy", "chess.move_legality",
                "chess.control", "chess.defended", "chess.king_check",
                "chess.absolute_pin", "chess.fork_double_attack",
                "chess.discovered_attack_check", "chess.escape_square_control",
                "chess.passed_pawn", "chess.open_file", "chess.semi_open_file",
                "chess.finite_promotion_race", "chess.finite_mating_geometry",
                "chess.terminal_transition", "chess.history_claim",
                "chess.declaration_event", "chess.source_score_relation",
                "chess.move_record_replay",
            },
        )
        self.assertEqual(
            re.findall(r"^\*\*Stage ([0-9]+) ", source, re.MULTILINE),
            [str(stage) for stage in range(1, 12)],
        )

    def test_m1_content_owner_is_closed(self) -> None:
        content = (ROOT / "spec/content-v0.md").read_text()
        design = " ".join((ROOT / "docs/m1-spec.md").read_text().split())

        self.assertIn("sole owner of Golden Board content-v0", content)
        self.assertIn("sole normative owner of generic content bytes", design)
        self.assertIsNone(re.search(r"\b(?:TODO|TBD|FIXME|XXX)\b", content))
        self.assertIn("content.stream_validation", content)
        self.assertIn("466,958", content)
        self.assertIn("466,955", content)

        self.assertEqual(
            set(re.findall(r"\bCONTENT_KIND_[A-Z_]+\b", content)),
            {
                "CONTENT_KIND_TEXT", "CONTENT_KIND_ATOM_SCHEMA",
                "CONTENT_KIND_ATOM_VECTOR", "CONTENT_KIND_MATRIX",
                "CONTENT_KIND_FIELD_SCHEMA", "CONTENT_KIND_TUPLE",
                "CONTENT_KIND_REGION_SET", "CONTENT_KIND_SEMANTIC_BINDING",
                "CONTENT_KIND_OPAQUE_DATA", "CONTENT_KIND_PREDICATE_RESULT",
                "CONTENT_KIND_FEEDBACK", "CONTENT_KIND_PASSIVE_TRACE",
                "CONTENT_KIND_LESSON_NODE", "CONTENT_KIND_ROOT",
            },
        )
        code_section = content.split("### 13.2 Primary code order", 1)[1].split(
            "### 13.3 Validation stages", 1
        )[0]
        self.assertEqual(
            re.findall(r"^\d+\. `(CONTENT_[A-Z0-9_]+)`$", code_section, re.MULTILINE),
            [
                "CONTENT_LIMIT_EXCEEDED", "CONTENT_TRUNCATED",
                "CONTENT_BAD_VERSION", "CONTENT_BAD_RECORD_COUNT",
                "CONTENT_BAD_RECORD_ID", "CONTENT_RECORD_ORDER",
                "CONTENT_BAD_RECORD_KIND", "CONTENT_BAD_PAYLOAD_LENGTH",
                "CONTENT_TRAILING_DATA", "CONTENT_BAD_TAG",
                "CONTENT_RESERVED_NONZERO", "CONTENT_BAD_UTF8",
                "CONTENT_BAD_COUNT", "CONTENT_BAD_VALUE",
                "CONTENT_NONCANONICAL_ORDER", "CONTENT_DUPLICATE",
                "CONTENT_ZERO_REFERENCE", "CONTENT_FORWARD_REFERENCE",
                "CONTENT_MISSING_REFERENCE", "CONTENT_WRONG_REFERENCE_KIND",
                "CONTENT_SCHEMA_MISMATCH", "CONTENT_ROOT_COUNT",
                "CONTENT_ROOT_NOT_FINAL", "CONTENT_BAD_CONTROL_EDGE",
                "CONTENT_ORPHAN_RECORD", "CONTENT_BAD_RESPONSE_SCHEMA",
                "CONTENT_FORBIDDEN_ANSWER_DATA", "CONTENT_BAD_FEEDBACK",
                "CONTENT_BAD_PASSIVE_TRACE", "CONTENT_BUDGET_PROOF",
                "CONTENT_BAD_RUN_STATE",
            ],
        )

    def test_m1_owner_and_plan_alignment(self) -> None:
        chess = " ".join((ROOT / "spec/chess-v0.md").read_text().split())
        content = " ".join((ROOT / "spec/content-v0.md").read_text().split())
        plan = " ".join((ROOT / "docs/m1-plan.md").read_text().split())
        design = " ".join((ROOT / "docs/m1-spec.md").read_text().split())
        roadmap = " ".join((ROOT / "docs/roadmap.md").read_text().split())

        self.assertIn("`EN_PASSANT_NONE` is numeric zero", chess)
        self.assertIn("exactly `square_index + 1`", chess)
        self.assertIn("`ContentRejectCode` is a constants-owned `u16`", content)
        self.assertIn("P4-Python source -> P6 curriculum", plan)
        self.assertIn("P6-Python content -> P6 curriculum", plan)
        self.assertIn("Python source owner API from P4", plan)
        self.assertIn("Python generic-content validation from P6.1", plan)
        self.assertNotIn("P2 -> P6 curriculum", plan)
        self.assertIn(
            "each referenced stratum's typed owner call independently recomputes and passes",
            design,
        )
        self.assertIn(
            "each referenced stratum's typed owner call independently recomputes and passes",
            roadmap,
        )
        same_as_prior = (
            "an absent prior item selects first; a present empty prior response commits "
            "empty; a mechanically valid mapped response replays; and an incompatible "
            "mapping selects first"
        )
        self.assertIn(same_as_prior, design)
        self.assertIn(same_as_prior, roadmap)
        self.assertIn(
            "Before the first screened candidate or reserve starts result-bearing pretest, "
            "publish a tracked salted commitment",
            design,
        )
        self.assertIn(
            "Before the first screened candidate or reserve starts result-bearing pretest, "
            "publish a tracked salted commitment",
            roadmap,
        )
        self.assertNotIn("owns the numeric value of every symbolic code named here", chess)
        for owner in (chess, design):
            self.assertIn("records and mirrors them for generation", owner)
            self.assertIn("second normative assignment", owner)
        self.assertIn("canonical `a1..h8` order", chess)
        self.assertIn("`square_index` is `0..63`", chess)
        self.assertIn(
            "square order is `a1,b1,...,h1,a2,...,h8` and square index is `0..63`",
            design,
        )
        self.assertIn(
            "Nominal en-passant is `0` for none, otherwise `square_index + 1`",
            design,
        )
        self.assertIn(
            "The Python and Rust generic-content lanes remain independent and no-chess",
            plan,
        )
        self.assertIn("one presentation-identical neutral acknowledgement", design)
        self.assertIn("one presentation-identical neutral acknowledgement", roadmap)
        self.assertIn(
            "Result-bearing feedback for every screened slot, including unused reserves, "
            "is withheld until every selected learner's normal or fallback feedback "
            "window resolves",
            design,
        )
        self.assertIn(
            "result-bearing feedback for every screened slot, including unused reserves, "
            "remain withheld until every selected participant's normal or fallback "
            "feedback window has resolved",
            roadmap,
        )
        for protocol in (design, roadmap):
            self.assertIn("later private assessment manifest", protocol)
            self.assertIn("commitment byte framing", protocol)
            self.assertIn("first delayed attempt is the only attempt", protocol)
            self.assertIn(
                "closed interval from 36 through 60 hours after that learner's complete "
                "valid posttest",
                protocol,
            )
            self.assertIn(
                "posttest itself finishes by the slot's frozen posttest deadline",
                protocol,
            )
            self.assertIn("early, late, invalid, or missed first attempt", protocol)
            self.assertIn("without retry", protocol)
            self.assertIn(
                "valid in-window completion or at the +60-hour fallback deadline",
                protocol,
            )
        self.assertIn("reveal and verify both only after all selected windows resolve", design)
        self.assertIn(
            "reveal follows resolution of all selected normal or fallback windows",
            roadmap,
        )
        self.assertIn(
            "feedback embargo for that slot resolves 60 hours after that deadline",
            design,
        )
        self.assertIn(
            "that slot's feedback embargo resolves 60 hours after the deadline",
            roadmap,
        )


class RootCheckCLI(unittest.TestCase):
    SCRIPT = ROOT / "scripts/check"

    def run_check(self, *arguments: str, **kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.SCRIPT), *arguments],
            cwd=kwargs.get("cwd", ROOT),
            env=kwargs.get("env"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def test_usage_errors(self) -> None:
        for arguments in ((), ("unknown",), ("focused",), ("focused", "unknown"), ("full", "extra"), ("focused", "repo", "extra")):
            with self.subTest(arguments=arguments):
                result = self.run_check(*arguments)
                self.assertEqual(result.returncode, 2)
                self.assertIn("usage:", result.stderr)

    def fake_environment(self, root: Path, fail_child: bool) -> dict[str, str]:
        binary = root / "bin"
        binary.mkdir(parents=True)
        fake_rustc = binary / "rustc"
        fake_rustc.write_text("#!/bin/sh\necho 'rustc 1.97.1 (test)'\n")
        fake_rustc.chmod(0o755)
        git = binary / "git"
        git.write_text("#!/bin/sh\necho 'git version test'\n")
        git.chmod(0o755)
        uv = binary / "uv"
        uv.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = --version ]; then echo 'uv 0.11.29 (test)'; exit 0; fi\n"
            + (
                "case \" $* \" in *\" -c \"*) exit 0;; *) exit 1;; esac\n"
                if fail_child
                else "exit 0\n"
            )
        )
        uv.chmod(0o755)
        rustup = binary / "rustup"
        rustup.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = which ]; then echo \"${0%/*}/rustc\"; exit 0; fi\n"
            "if [ \"$4\" = --version ]; then echo 'cargo 1.97.1 (test)'; exit 0; fi\n"
            "exit 0\n"
        )
        rustup.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = str(binary)
        return environment

    def test_success_and_failed_child_are_classified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copied = root / "scripts/check"
            copied.parent.mkdir()
            copied.write_bytes(self.SCRIPT.read_bytes())
            copied.chmod(0o755)
            environment = self.fake_environment(root, fail_child=False)
            success = subprocess.run(
                [str(copied), "focused", "identity"], cwd=root, env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
            )
            self.assertEqual(success.returncode, 0, success.stderr)
            failed_environment = self.fake_environment(root / "failed", fail_child=True)
            failure = subprocess.run(
                [str(copied), "focused", "identity"], cwd=root, env=failed_environment,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
            )
            self.assertEqual(failure.returncode, 1)
            self.assertIn("identity", failure.stderr)

    def test_missing_dependency_cache_fails_actionably(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment["CARGO_HOME"] = directory
            result = self.run_check("focused", "identity", env=environment)
            self.assertEqual(result.returncode, 1)
            self.assertIn("identity-rust failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
