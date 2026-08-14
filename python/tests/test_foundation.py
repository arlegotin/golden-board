from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import tomllib
import unittest

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
        "README.md", "conformance/identity-v0.json", "conformance/manifest-v0.json",
        "conformance/registry.toml", "crates/gb-foundation/Cargo.toml",
        "crates/gb-foundation/src/lib.rs", "crates/gb-foundation/tests/conformance.rs",
        "docs/64_games.md", "docs/m0-plan.md", "docs/m0-spec.md", "docs/roadmap.md",
        "docs/m1-plan.md", "docs/m1-spec.md", "docs/sources.md", "inputs/source-lock.toml", "pyproject.toml",
        "python/golden_board/__init__.py", "python/golden_board/canonical_manifest.py",
        "python/golden_board/identity.py", "python/golden_board/source_doctor.py",
        "python/tests/test_foundation.py", "reports/source-doctor.json",
        "rust-toolchain.toml", "scripts/check", "spec/identity-v0.md", "uv.lock",
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
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout
        for relative in [*self.REQUIRED, *output.splitlines()]:
            if relative in {"docs/64_games.md", "reports/game-set-v0.bin"}:
                continue
            data = (ROOT / relative).read_bytes()
            self.assertNotIn(b"\r", data, relative)
            self.assertTrue(data.endswith(b"\n"), relative)
            for line in data.splitlines():
                self.assertFalse(line.endswith((b" ", b"\t")), relative)
                self.assertFalse(line.startswith((b"<<<<<<<", b"=======", b">>>>>>>")), relative)

        registry = tomllib.loads((ROOT / "conformance/registry.toml").read_text())
        payloads = sorted(path.name for path in (ROOT / "conformance").iterdir() if path.name != "registry.toml")
        self.assertEqual(payloads, sorted(Path(item["path"]).name for item in registry["suite"]))
        for item in registry["suite"]:
            payload = ROOT / item["path"]
            self.assertEqual(hashlib.sha256(payload.read_bytes()).hexdigest(), item["sha256"])

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

    def test_m1_admission_policy(self) -> None:
        check = (ROOT / "scripts/check").read_text()
        self.assertIn("cargo test -p gb-foundation", check)
        self.assertIn("git diff --check || return 1", check)
        self.assertIn("git diff --cached --check || return 1", check)

        roadmap = (ROOT / "docs/roadmap.md").read_text()
        self.assertIn(
            "| M1 — Chess truth, source grammar, and assessment blueprint | In progress | — |",
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
