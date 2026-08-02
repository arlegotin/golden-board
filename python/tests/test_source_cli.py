from contextlib import redirect_stderr
from io import StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from golden_board import cli
from golden_board.manifest import encode_canonical_value


REPORT = {
    "schema_version": 0,
    "source": {"path": "docs/64_games.md"},
    "diagnostics": [],
    "g1_preflight": True,
}
REPORT_BYTES = encode_canonical_value(REPORT)


class SourceCliTests(unittest.TestCase):
    def call_main(self, argv: list[str], root: Path, report: object = REPORT) -> tuple[int, str]:
        errors = StringIO()
        with (
            patch.object(cli, "load_source_lock", return_value=object()) as load,
            patch.object(
                cli.source_doctor,
                "build_source_report",
                return_value=report,
                create=True,
            ) as build,
            redirect_stderr(errors),
        ):
            status = cli.main(argv, root=root)
        if argv in (["generate", "source-doctor"], ["check", "source-report"]):
            load.assert_called_once_with(root)
            build.assert_called_once_with(root, load.return_value)
        else:
            load.assert_not_called()
            build.assert_not_called()
        return status, errors.getvalue()

    def test_dispatcher_accepts_only_two_exact_commands(self) -> None:
        invalid = (
            [],
            ["generate"],
            ["source-doctor", "generate"],
            ["generate", "source-report"],
            ["check", "source-doctor"],
            ["generate", "source-doctor", "extra"],
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for argv in invalid:
                with self.subTest(argv=argv):
                    status, error = self.call_main(list(argv), root)
                    self.assertEqual(2, status)
                    self.assertEqual("usage: generate source-doctor | check source-report\n", error)
            self.assertFalse((root / "reports").exists())

    def test_generate_creates_only_the_fixed_canonical_report(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            status, error = self.call_main(["generate", "source-doctor"], root)
            self.assertEqual((0, ""), (status, error))
            report = root / "reports/source-doctor.json"
            self.assertEqual(REPORT_BYTES, report.read_bytes())
            self.assertEqual(["source-doctor.json"], sorted(path.name for path in report.parent.iterdir()))

    def test_check_is_in_memory_nonmutating_and_detects_drift_or_absence(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            target = reports / "source-doctor.json"
            target.write_bytes(REPORT_BYTES)
            before = target.stat()
            status, error = self.call_main(["check", "source-report"], root)
            self.assertEqual((0, ""), (status, error))
            self.assertEqual(REPORT_BYTES, target.read_bytes())
            self.assertEqual((before.st_ino, before.st_mtime_ns), (target.stat().st_ino, target.stat().st_mtime_ns))

            target.write_bytes(b"stale\n")
            stale = target.read_bytes()
            status, error = self.call_main(["check", "source-report"], root)
            self.assertEqual(1, status)
            self.assertEqual("source report differs\n", error)
            self.assertEqual(stale, target.read_bytes())

            target.unlink()
            reports.rmdir()
            status, error = self.call_main(["check", "source-report"], root)
            self.assertEqual(1, status)
            self.assertEqual("source report unavailable\n", error)
            self.assertFalse(reports.exists())

    def test_report_build_and_encoding_fail_closed_without_writing(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(cli, "load_source_lock", side_effect=ValueError("untrusted detail")), redirect_stderr(StringIO()) as errors:
                self.assertEqual(1, cli.main(["generate", "source-doctor"], root=root))
                self.assertEqual("source report failed\n", errors.getvalue())
            self.assertFalse((root / "reports").exists())

            status, error = self.call_main(["generate", "source-doctor"], root, None)
            self.assertEqual(1, status)
            self.assertEqual("source report failed\n", error)
            self.assertFalse((root / "reports").exists())

    def test_writer_rejects_symlinked_parent_and_nonregular_destination(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            outside.mkdir()
            (root / "reports").symlink_to(outside, target_is_directory=True)
            with self.assertRaises((OSError, ValueError)):
                cli._write_source_report(root, REPORT_BYTES)
            self.assertEqual([], list(outside.iterdir()))

        with TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            outside = root / "outside.json"
            outside.write_bytes(b"safe")
            (reports / "source-doctor.json").symlink_to(outside)
            with self.assertRaises((OSError, ValueError)):
                cli._write_source_report(root, REPORT_BYTES)
            self.assertEqual(b"safe", outside.read_bytes())

            (reports / "source-doctor.json").unlink()
            (reports / "source-doctor.json").mkdir()
            with self.assertRaises((OSError, ValueError)):
                cli._write_source_report(root, REPORT_BYTES)

    def test_writer_uses_bounded_exclusive_temporary_names(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            target = reports / "source-doctor.json"
            target.write_bytes(b"old\n")
            for index in range(64):
                (reports / f".source-doctor.json.{index}.tmp").write_bytes(b"occupied")
            with self.assertRaises(ValueError):
                cli._write_source_report(root, REPORT_BYTES)
            self.assertEqual(b"old\n", target.read_bytes())
            self.assertEqual(65, len(list(reports.iterdir())))

    def test_writer_handles_memoryview_short_writes(self) -> None:
        real_write = os.write
        argument_types: list[type[object]] = []

        def short_write(descriptor: int, data: object) -> int:
            argument_types.append(type(data))
            view = memoryview(data)  # type: ignore[arg-type]
            return real_write(descriptor, view[: max(1, len(view) // 3)])

        with TemporaryDirectory() as directory, patch.object(cli.os, "write", side_effect=short_write):
            root = Path(directory)
            cli._write_source_report(root, REPORT_BYTES)
            self.assertEqual(REPORT_BYTES, (root / "reports/source-doctor.json").read_bytes())
        self.assertGreater(len(argument_types), 1)
        self.assertEqual({memoryview}, set(argument_types))

    def test_pre_replace_fsync_close_verify_and_reparse_failures_preserve_old(self) -> None:
        failures = ("fsync", "close", "verify", "reparse")
        for failure in failures:
            with self.subTest(failure=failure), TemporaryDirectory() as directory:
                root = Path(directory)
                reports = root / "reports"
                reports.mkdir()
                target = reports / "source-doctor.json"
                target.write_bytes(b"old\n")
                stack = []
                if failure == "fsync":
                    stack.append(patch.object(cli.os, "fsync", side_effect=OSError("fail")))
                elif failure == "close":
                    real_close = os.close
                    calls = 0

                    def first_close_fails(descriptor: int) -> None:
                        nonlocal calls
                        calls += 1
                        real_close(descriptor)
                        if calls == 1:
                            raise OSError("fail")

                    stack.append(patch.object(cli.os, "close", side_effect=first_close_fails))
                elif failure == "verify":
                    stack.append(patch.object(cli, "_read_regular_at", return_value=b"different\n"))
                else:
                    stack.append(patch.object(cli, "decode_canonical_manifest", side_effect=ValueError("fail")))

                with stack[0], self.assertRaises((OSError, ValueError)):
                    cli._write_source_report(root, REPORT_BYTES)
                self.assertEqual(b"old\n", target.read_bytes())
                self.assertEqual(["source-doctor.json"], sorted(path.name for path in reports.iterdir()))

    def test_replace_failure_preserves_old_and_cleans_temporary(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            target = reports / "source-doctor.json"
            target.write_bytes(b"old\n")
            with patch.object(cli.os, "replace", side_effect=OSError("fail")), self.assertRaises(OSError):
                cli._write_source_report(root, REPORT_BYTES)
            self.assertEqual(b"old\n", target.read_bytes())
            self.assertEqual(["source-doctor.json"], sorted(path.name for path in reports.iterdir()))

    def test_successful_replace_is_the_final_commit_point(self) -> None:
        real_close = os.close
        calls = 0

        def later_close_fails(descriptor: int) -> None:
            nonlocal calls
            calls += 1
            real_close(descriptor)
            if calls > 2:
                raise OSError("post-commit close")

        with TemporaryDirectory() as directory, patch.object(cli.os, "close", side_effect=later_close_fails):
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            (reports / "source-doctor.json").write_bytes(b"old\n")
            cli._write_source_report(root, REPORT_BYTES)
            self.assertEqual(REPORT_BYTES, (reports / "source-doctor.json").read_bytes())

    def test_descriptor_reader_rejects_symlink_nonregular_oversize_and_change(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            (reports / "regular").write_bytes(b"abc")
            (reports / "link").symlink_to("regular")
            (reports / "directory").mkdir()
            descriptor = os.open(reports, os.O_RDONLY | os.O_DIRECTORY)
            try:
                self.assertEqual(b"abc", cli._read_regular_at(descriptor, "regular", 3))
                for leaf, limit in (("link", 3), ("directory", 3), ("regular", 2)):
                    with self.subTest(leaf=leaf, limit=limit), self.assertRaises(ValueError):
                        cli._read_regular_at(descriptor, leaf, limit)
                regular = os.open(reports / "regular", os.O_RDONLY)
                try:
                    before = os.fstat(regular)
                finally:
                    os.close(regular)
                changed_values = list(before)
                changed_values[6] += 1
                changed = os.stat_result(changed_values)
                with patch.object(cli.os, "fstat", side_effect=(before, changed)):
                    with self.assertRaises(ValueError):
                        cli._read_regular_at(descriptor, "regular", 3)
            finally:
                os.close(descriptor)


if __name__ == "__main__":
    unittest.main()
