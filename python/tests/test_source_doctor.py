from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from golden_board import source_doctor
from golden_board.manifest import decode_canonical_manifest, encode_canonical_value
from golden_board.source_doctor import (
    DIAGNOSTIC_PRECEDENCE,
    SourceDoctorError,
    build_source_report,
    inspect_source,
)
from golden_board.source_lock import SafeFileError, load_source_lock


BLOCK = b"```pgn\n\n```\n"
TOP_LEVEL = {
    "schema_version",
    "source",
    "encoding",
    "newlines",
    "fences",
    "tags",
    "movetext",
    "constructs",
    "duplicates",
    "ranges",
    "diagnostics",
    "g1_preflight",
    "limitations",
}
REPORT_TOP_LEVEL = TOP_LEVEL | {"fence_count", "raw_module_sha256"}
ROOT = Path(__file__).resolve().parents[2]


def record(tags: bytes = b'[Event "omitted"]\n', moves: bytes = b"1. e4 e5 1-0\n") -> bytes:
    return b"```pgn\n" + tags + b"\n" + moves + b"```\n"


class SourceDoctorTests(unittest.TestCase):
    def assert_ordered_diagnostics(self, report: dict[str, object]) -> None:
        diagnostics = report["diagnostics"]
        self.assertEqual(
            [item for item in DIAGNOSTIC_PRECEDENCE if item in diagnostics],
            diagnostics,
        )

    def test_closed_schema_fixed_limits_and_deterministic_encoding(self) -> None:
        self.assertEqual(16_777_216, source_doctor.MAX_SOURCE_BYTES)
        self.assertEqual(65, source_doctor.MAX_RECORD_DETAILS)
        self.assertEqual(32, source_doctor.MAX_SAMPLES)
        self.assertEqual(4_096, source_doctor.MAX_TAG_NAMES)
        self.assertEqual(128, source_doctor.MAX_TAG_NAME_BYTES)
        self.assertEqual(64, source_doctor.MAX_DUPLICATE_GROUPS)
        raw = BLOCK * 64
        first = inspect_source(raw)
        second = inspect_source(raw)
        self.assertEqual(TOP_LEVEL, set(first))
        self.assertEqual(
            [
                "lexical-only",
                "no-san-or-chess-validation",
                "tag-values-untrusted-and-omitted",
                "no-canonical-game-bytes",
            ],
            first["limitations"],
        )
        self.assertEqual(first, second)
        self.assertEqual(encode_canonical_value(first), encode_canonical_value(second))
        self.assertTrue(first["g1_preflight"])

    def test_type_and_exact_input_limit(self) -> None:
        with self.assertRaises(TypeError):
            inspect_source(bytearray())  # type: ignore[arg-type]
        exact = inspect_source(b"x" * source_doctor.MAX_SOURCE_BYTES)
        self.assertEqual(source_doctor.MAX_SOURCE_BYTES, exact["source"]["byte_length"])
        with self.assertRaises(SourceDoctorError) as caught:
            inspect_source(b"x" * (source_doctor.MAX_SOURCE_BYTES + 1))
        self.assertEqual("source.size_limit", caught.exception.code)

    def test_profile_facts_and_diagnostic_precedence(self) -> None:
        cases = (
            (b"\xff", {"source.utf8", "source.newline", "source.final_lf", "source.fence_count"}),
            (b"\xef\xbb\xbf" + BLOCK * 64, {"source.bom"}),
            (b"\0\n" + BLOCK * 64, {"source.control"}),
            (BLOCK.replace(b"\n", b"\r\n") * 64, set()),
            (BLOCK * 63 + BLOCK.replace(b"\n", b"\r\n"), {"source.newline"}),
            (b"```pgn\r\r```\r", {"source.newline", "source.final_lf", "source.fence_count"}),
            (BLOCK * 63 + BLOCK[:-1], {"source.final_lf"}),
        )
        for raw, expected in cases:
            with self.subTest(expected=expected):
                report = inspect_source(raw)
                self.assertEqual(expected, set(report["diagnostics"]))
                self.assert_ordered_diagnostics(report)
        controls = inspect_source(b"\0\x01\x7f\n")
        self.assertEqual(3, controls["encoding"]["control_count"])
        self.assertEqual("lf", controls["newlines"]["profile"])

    def test_fence_counts_spans_and_record_detail_cap(self) -> None:
        for count in (63, 64, 65):
            with self.subTest(count=count):
                report = inspect_source(BLOCK * count)
                self.assertEqual(count, report["fences"]["recognized_count"])
                self.assertEqual(count != 64, "source.fence_count" in report["diagnostics"])
        raw = b"prefix\n```pgn \t\nbody\n``` \t\n"
        report = inspect_source(raw)
        item = report["fences"]["records"][0]
        opener_start = raw.index(b"```pgn")
        opener_end = raw.index(b"\n", opener_start) + 1
        closer_start = raw.index(b"``` \t")
        closer_end = raw.index(b"\n", closer_start) + 1
        self.assertEqual([opener_start, opener_end], item["opener_span"])
        self.assertEqual([opener_end, closer_start], item["body_span"])
        self.assertEqual([closer_start, closer_end], item["closer_span"])

        overflow = inspect_source(BLOCK * 66)
        self.assertEqual(66, overflow["fences"]["recognized_count"])
        self.assertEqual(65, len(overflow["fences"]["records"]))
        self.assertTrue(overflow["fences"]["records_truncated"])

        crlf = b"prefix\r\n```pgn \t\r\nbody\r\n``` \t\r\n"
        crlf_item = inspect_source(crlf)["fences"]["records"][0]
        crlf_opener = crlf.index(b"```pgn")
        crlf_body = crlf.index(b"body")
        crlf_closer = crlf.index(b"``` \t")
        self.assertEqual(
            [crlf_opener, crlf_body], crlf_item["opener_span"]
        )
        self.assertEqual(
            [crlf_body, crlf_closer], crlf_item["body_span"]
        )
        self.assertEqual(
            [crlf_closer, len(crlf)], crlf_item["closer_span"]
        )

    def test_physical_line_scanner_is_monotonic(self) -> None:
        class NoSuffixFind(bytes):
            def find(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                raise AssertionError("line scanner searched a remaining suffix")

        raw = NoSuffixFind(b"a\nb\r\nc\r")
        self.assertEqual(
            [(0, 2, 1), (2, 5, 3), (5, 7, 6)],
            list(source_doctor._lines(raw, 0, len(raw))),
        )

    def test_malformed_nested_and_unterminated_fences(self) -> None:
        raw = (
            b" ```pgn ```\n"
            b"```pgn\n"
            b"```pgn\n"
            b"body\n"
            b"```\n"
            b"```pgn\n"
            b"unterminated\n"
        )
        report = inspect_source(raw)
        self.assertIn("source.fence_structure", report["diagnostics"])
        first = raw.index(b"```")
        second = raw.index(b"```", first + 3)
        opener = raw.index(b"```", second + 3)
        nested = raw.index(b"```", opener + 3)
        unterminated = raw.rindex(b"```pgn")
        self.assertEqual(4, report["fences"]["malformed_count"])
        self.assertEqual(
            [
                [first, first + 3],
                [second, second + 3],
                [nested, nested + 3],
                [unterminated, unterminated + 3],
            ],
            report["fences"]["malformed_samples"],
        )

    def test_tag_inventory_duplicates_bounds_and_value_omission(self) -> None:
        tags = (
            b'[Event "TOP-SECRET-VALUE"]\n'
            b'[Event "SECOND-SECRET"]\n'
            b'[SetUp "1"]\n'
            b'[FEN "DO-NOT-COPY-FEN"]\n'
        )
        report = inspect_source(record(tags))
        by_name = {item["name"]: item for item in report["tags"]["names"]}
        self.assertEqual(4, report["tags"]["occurrence_count"])
        self.assertEqual(5, report["tags"]["max_name_bytes"])
        self.assertEqual(16, report["tags"]["max_value_bytes"])
        self.assertEqual(27, report["tags"]["max_line_bytes"])
        self.assertEqual(2, by_name["Event"]["count"])
        self.assertEqual(1, by_name["Event"]["duplicate_record_count"])
        self.assertEqual(16, by_name["Event"]["max_value_bytes"])
        self.assertEqual(27, by_name["Event"]["max_line_bytes"])
        self.assertEqual(2, report["constructs"]["alternate_start_tags"]["count"])
        rendered = repr(report)
        for secret in ("TOP-SECRET-VALUE", "SECOND-SECRET", "DO-NOT-COPY-FEN"):
            self.assertNotIn(secret, rendered)

        with (
            patch.object(source_doctor, "MAX_TAG_NAMES", 1),
            patch.object(source_doctor, "MAX_TAG_NAME_BYTES", 3),
        ):
            bounded = inspect_source(
                record(b'[A "x"]\n[BBBB "y"]\n[C "z"]\n')
            )
        self.assertEqual(1, bounded["tags"]["retained_name_count"])
        self.assertEqual(2, bounded["tags"]["omitted_occurrence_count"])
        self.assertEqual(1, bounded["tags"]["oversize_name_occurrence_count"])
        self.assertTrue(bounded["tags"]["inventory_truncated"])

        later = inspect_source(
            record(
                b'[Event "x"]\n',
                b'1. e4\n[FEN "LATER-SECRET"]\n1-0\n',
            )
        )
        later_names = {item["name"] for item in later["tags"]["names"]}
        self.assertIn("FEN", later_names)
        self.assertEqual(1, later["constructs"]["alternate_start_tags"]["count"])
        self.assertNotIn("LATER-SECRET", repr(later))

    def test_movetext_and_construct_taxonomy_without_token_disclosure(self) -> None:
        moves = (
            b"% ESCAPE-SECRET\n"
            b"1. e4 $1 e5?! (1... c5 (1... d5)) {BRACE-SECRET} "
            b"2... Nf6 ; SEMICOLON-SECRET\n"
            b"1-0 TRAILING-SECRET\n"
        )
        report = inspect_source(record(b'[SetUp "1"]\n', moves))
        constructs = report["constructs"]
        self.assertEqual(1, constructs["escape_lines"]["count"])
        self.assertEqual(1, constructs["brace_comments"]["count"])
        self.assertEqual(1, constructs["semicolon_comments"]["count"])
        self.assertEqual(2, constructs["ravs"]["count"])
        self.assertEqual(2, constructs["rav_max_depth"])
        self.assertEqual(1, constructs["nags"]["count"])
        self.assertEqual(1, constructs["annotation_suffixes"]["count"])
        movetext = report["movetext"]
        self.assertEqual(1, movetext["result_markers"]["white_win"])
        self.assertEqual(1, movetext["trailing_token_count"])
        self.assertGreater(movetext["san_like_shapes"]["pawn"], 0)
        self.assertGreater(movetext["san_like_shapes"]["piece"], 0)
        rendered = repr(report)
        for secret in (
            "ESCAPE-SECRET",
            "BRACE-SECRET",
            "SEMICOLON-SECRET",
            "TRAILING-SECRET",
        ):
            self.assertNotIn(secret, rendered)

    def test_unmatched_comment_closer_is_bounded_unknown_input(self) -> None:
        report = inspect_source(record(moves=b"} 1. e4 1-0\n"))
        self.assertEqual(1, report["constructs"]["unknown_tokens"]["count"])
        self.assertEqual(1, report["movetext"]["lexical_ply_count"])

    def test_separator_result_and_move_shape_buckets(self) -> None:
        cases = (
            (b"\n", b"1. e4 *\n", "empty", "unfinished"),
            (b" \t\n", b"1... e5 0-1\n", "horizontal_whitespace", "black_win"),
            (b"\n\n", b"1.e4 1/2-1/2\n", "multiple", "draw"),
        )
        reports = []
        for separator, moves, shape, result in cases:
            raw = b"```pgn\n" + b'[Event "x"]\n' + separator + moves + b"```\n"
            report = inspect_source(raw)
            reports.append(report)
            self.assertEqual(1, report["movetext"]["separator_shapes"][shape])
            self.assertEqual(1, report["movetext"]["result_markers"][result])
        self.assertEqual(1, reports[0]["movetext"]["move_number_shapes"]["white"])
        self.assertEqual(1, reports[1]["movetext"]["move_number_shapes"]["black"])
        self.assertEqual(1, reports[2]["movetext"]["move_number_shapes"]["attached_white"])

        shapes = inspect_source(
            record(moves=b"1...e5 2... Nf6 3. O-O 4. e8=Q ... xyz 1-0\n")
        )["movetext"]
        self.assertEqual(1, shapes["move_number_shapes"]["attached_black"])
        self.assertEqual(1, shapes["move_number_shapes"]["other"])
        for shape in ("castle", "piece", "pawn", "promotion", "other"):
            self.assertGreater(shapes["san_like_shapes"][shape], 0)

    def test_duplicate_hashes_and_manifest_compatible_ranges(self) -> None:
        same = b"1. e4 e5 1-0\n"
        spaced = b"1.  e4\te5  1-0\n"
        raw = record(moves=same) + record(moves=same) + record(moves=spaced)
        report = inspect_source(raw)
        duplicates = report["duplicates"]
        self.assertEqual(1, duplicates["raw_group_count"])
        self.assertEqual(1, duplicates["normalized_group_count"])
        kinds = [item["kind"] for item in duplicates["groups"]]
        self.assertEqual(["raw", "ascii-whitespace-normalized"], kinds)
        self.assertEqual(sha256(same).hexdigest(), duplicates["groups"][0]["sha256"])
        self.assertEqual(
            sha256(b"1. e4 e5 1-0").hexdigest(),
            duplicates["groups"][1]["sha256"],
        )
        self.assertEqual(
            [len(record(moves=same)), len(record(moves=spaced))],
            report["ranges"]["record_bytes"],
        )
        self.assertEqual([2, 2], report["ranges"]["lexical_plies"])
        empty = inspect_source(b"")
        self.assertEqual([], empty["ranges"]["record_bytes"])
        self.assertEqual([], empty["ranges"]["lexical_plies"])
        self.assertNotIn("None", repr(empty))

    def test_sample_and_duplicate_group_caps_are_explicit(self) -> None:
        hostile = b"".join(b" ```pgn\n" for _ in range(4))
        with patch.object(source_doctor, "MAX_SAMPLES", 2):
            sampled = inspect_source(hostile)
        self.assertEqual(4, sampled["fences"]["malformed_count"])
        self.assertEqual(2, len(sampled["fences"]["malformed_samples"]))

        raw = b"".join(record(moves=f"1. e{i} 1-0\n".encode()) * 2 for i in range(3))
        with patch.object(source_doctor, "MAX_DUPLICATE_GROUPS", 2):
            capped = inspect_source(raw)
        self.assertGreater(capped["duplicates"]["raw_group_count"], 1)
        self.assertEqual(2, len(capped["duplicates"]["groups"]))
        self.assertTrue(capped["duplicates"]["groups_truncated"])


class SourceReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.real_lock = load_source_lock(ROOT)

    def lock_for(
        self,
        raw: bytes,
        *,
        byte_length: int | None = None,
        digest: str | None = None,
        newlines: str = "LF",
    ):
        anthology = replace(
            self.real_lock.anthology,
            byte_length=len(raw) if byte_length is None else byte_length,
            sha256=sha256(raw).hexdigest() if digest is None else digest,
            newlines=newlines,
        )
        return replace(self.real_lock, anthology=anthology)

    def write_root(
        self,
        root: Path,
        raw: bytes,
        module: bytes = b"RAW-MODULE-SECRET\n",
    ) -> None:
        source = root / "docs/64_games.md"
        source.parent.mkdir(parents=True)
        source.write_bytes(raw)
        module_path = root / "python/golden_board/source_doctor.py"
        module_path.parent.mkdir(parents=True)
        module_path.write_bytes(module)

    def assert_report_diagnostics(
        self,
        raw: bytes,
        expected: list[str],
        **lock_overrides: object,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_root(root, raw)
            report = build_source_report(
                root,
                self.lock_for(raw, **lock_overrides),  # type: ignore[arg-type]
            )
        self.assertEqual(expected, report["diagnostics"])
        self.assertEqual(not expected, report["g1_preflight"])
        self.assertEqual(report, decode_canonical_manifest(encode_canonical_value(report)))

    def test_real_locked_source_report_is_current_and_canonical(self) -> None:
        first = build_source_report(ROOT, self.real_lock)
        second = build_source_report(ROOT, self.real_lock)
        encoded = encode_canonical_value(first)

        self.assertEqual(first, second)
        self.assertEqual(REPORT_TOP_LEVEL, set(first))
        self.assertEqual(
            {"path", "byte_length", "sha256"}, set(first["source"])
        )
        self.assertEqual("docs/64_games.md", first["source"]["path"])
        self.assertEqual(64, first["fence_count"])
        self.assertTrue(first["g1_preflight"])
        self.assertEqual([], first["diagnostics"])
        self.assertEqual(
            sha256((ROOT / "python/golden_board/source_doctor.py").read_bytes()).hexdigest(),
            first["raw_module_sha256"],
        )
        self.assertEqual(first, decode_canonical_manifest(encoded))
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertFalse(encoded.endswith(b"\n\n"))

    def test_composition_snapshots_and_inspects_once_with_fixed_module_read(self) -> None:
        raw = BLOCK * 64
        lock = self.lock_for(raw)
        facts = inspect_source(raw)
        root = Path("repository-root")
        with (
            patch.object(
                source_doctor, "snapshot_regular_file", return_value=raw
            ) as snapshot,
            patch.object(source_doctor, "inspect_source", return_value=facts) as inspect,
            patch.object(
                source_doctor,
                "read_regular_below",
                return_value=b"module bytes\n",
            ) as reader,
        ):
            report = build_source_report(root, lock)

        snapshot.assert_called_once_with(root, lock.anthology, 16_777_216)
        inspect.assert_called_once_with(raw)
        reader.assert_called_once_with(
            root,
            PurePosixPath("python/golden_board/source_doctor.py"),
            1_048_576,
        )
        self.assertEqual(sha256(b"module bytes\n").hexdigest(), report["raw_module_sha256"])

    def test_lock_and_profile_diagnostics_are_merged_once_in_precedence(self) -> None:
        self.assert_report_diagnostics(
            BLOCK * 64,
            ["source.lock_size"],
            byte_length=len(BLOCK * 64) + 1,
        )
        self.assert_report_diagnostics(
            BLOCK * 64,
            ["source.lock_hash"],
            digest="0" * 64,
        )
        self.assert_report_diagnostics(
            BLOCK * 64,
            ["source.newline"],
            newlines="CRLF",
        )
        mixed = BLOCK * 63 + BLOCK.replace(b"\n", b"\r\n")
        self.assert_report_diagnostics(mixed, ["source.newline"])
        hostile = b"\xff"
        self.assert_report_diagnostics(
            hostile,
            [
                "source.lock_size",
                "source.lock_hash",
                "source.utf8",
                "source.newline",
                "source.final_lf",
                "source.fence_count",
            ],
            byte_length=2,
            digest="0" * 64,
            newlines="CRLF",
        )

    def test_safely_readable_profile_failures_return_reports(self) -> None:
        cases = (
            (b"\xff\n" + BLOCK * 64, ["source.utf8"]),
            (b"\xef\xbb\xbf" + BLOCK * 64, ["source.bom"]),
            (b"\0\n" + BLOCK * 64, ["source.control"]),
            (BLOCK * 63 + BLOCK[:-1], ["source.final_lf"]),
            (BLOCK * 63, ["source.fence_count"]),
            (BLOCK * 65, ["source.fence_count"]),
        )
        for raw, expected in cases:
            with self.subTest(expected=expected):
                self.assert_report_diagnostics(raw, expected)

    def test_report_projects_no_other_lock_authority_or_hostile_values(self) -> None:
        raw = record(b'[Event "PGN-TAG-SECRET"]\n') + BLOCK * 63
        lock = self.lock_for(raw)
        lock = replace(
            lock,
            toolchains=replace(lock.toolchains, host="HOST-SECRET"),
            references=(replace(lock.references[0], title="REFERENCE-SECRET"),),
            clean_linux=replace(lock.clean_linux, blocker="BLOCKER-SECRET"),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_root(root, raw)
            report = build_source_report(root, lock)

        rendered = encode_canonical_value(report)
        for secret in (
            b"PGN-TAG-SECRET",
            b"RAW-MODULE-SECRET",
            b"HOST-SECRET",
            b"REFERENCE-SECRET",
            b"BLOCKER-SECRET",
        ):
            self.assertNotIn(secret, rendered)
        for forbidden in (
            "toolchains",
            "references",
            "clean_linux",
            "timestamp",
            "hostname",
            "environment",
            "self_hash",
        ):
            self.assertNotIn(forbidden, report)

    def test_fatal_snapshot_and_module_reader_failures_propagate(self) -> None:
        raw = BLOCK * 64
        lock = self.lock_for(raw)
        snapshot_error = SourceDoctorError("source.changed")
        with (
            patch.object(
                source_doctor,
                "snapshot_regular_file",
                side_effect=snapshot_error,
            ),
            patch.object(source_doctor, "inspect_source") as inspect,
        ):
            with self.assertRaises(SourceDoctorError) as caught:
                build_source_report(Path("root"), lock)
        self.assertIs(snapshot_error, caught.exception)
        inspect.assert_not_called()

        module_error = SafeFileError("safe_file.changed")
        with (
            patch.object(source_doctor, "snapshot_regular_file", return_value=raw),
            patch.object(source_doctor, "read_regular_below", side_effect=module_error),
        ):
            with self.assertRaises(SafeFileError) as caught:
                build_source_report(Path("root"), lock)
        self.assertIs(module_error, caught.exception)

    def test_module_identity_path_is_safe_and_bounded(self) -> None:
        raw = BLOCK * 64
        lock = self.lock_for(raw)
        for kind, expected in (
            ("missing", "safe_file.path"),
            ("parent-symlink", "safe_file.path"),
            ("leaf-symlink", "safe_file.path"),
            ("fifo", "safe_file.type"),
            ("oversize", "safe_file.limit"),
        ):
            with self.subTest(kind=kind), TemporaryDirectory() as directory:
                root = Path(directory)
                self.write_root(root, raw)
                module = root / "python/golden_board/source_doctor.py"
                module.unlink()
                if kind == "parent-symlink":
                    parent = module.parent
                    parent.rmdir()
                    target = root / "real-golden-board"
                    target.mkdir()
                    (target / "source_doctor.py").write_bytes(b"module\n")
                    parent.symlink_to(target, target_is_directory=True)
                elif kind == "leaf-symlink":
                    target = root / "module.py"
                    target.write_bytes(b"module\n")
                    module.symlink_to(target)
                elif kind == "fifo":
                    os.mkfifo(module)
                elif kind == "oversize":
                    module.write_bytes(b"x" * 1_048_577)
                with self.assertRaisesRegex(SafeFileError, expected):
                    build_source_report(root, lock)


if __name__ == "__main__":
    unittest.main()
