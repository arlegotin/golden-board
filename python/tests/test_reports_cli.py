from __future__ import annotations

import hashlib
import io
import inspect
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import patch

from golden_board import cli, reports
from golden_board.manifest import decode_canonical_manifest, encode_canonical_value


ACCEPTANCE = tuple(f"Requirement {index}" for index in range(1, 19))
OWNERS = (
    "M0",
    "M1",
    "M1",
    "M1",
    "M2",
    "M2",
    "M2",
    "M2",
    "M3",
    "M3",
    "M4",
    "M4",
    "M4",
    "M4",
    "M5",
    "M5",
    "M6",
    "M6",
)
SOURCE_SHA256 = "33d44f7167ab190cc793e3fdfd8190d89ed13c1dc507c20854cf64751c7be7da"


def roadmap() -> str:
    rows = "\n".join(
        f"| G{index} | {ACCEPTANCE[index - 1]} | {OWNERS[index - 1]} | Evidence {index} |"
        for index in range(1, 19)
    )
    return (
        "# Roadmap\n\n"
        "| Field | Value |\n"
        "|---|---|\n"
        "| Roadmap revision | 1 |\n\n"
        "## 12. Final acceptance matrix\n\n"
        "| ID | Acceptance requirement | Owning milestone | Required evidence |\n"
        "|---|---|---|---|\n"
        f"{rows}\n\n---\n\n"
        "## 13. Project status — sole mutable authority\n"
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReportCliTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for directory in (
            "artifacts",
            "docs",
            "inputs",
            "python/golden_board",
            "reports",
        ):
            (self.root / directory).mkdir(parents=True, exist_ok=True)

        (self.root / "docs/roadmap.md").write_text(roadmap(), encoding="utf-8")
        (self.root / "docs/64_games.md").write_bytes(b"anthology\n")
        (self.root / "inputs/source-lock.toml").write_text(
            "schema_version = 0\n", encoding="utf-8"
        )
        (self.root / "python/golden_board/source_doctor.py").write_text(
            "# source doctor\n", encoding="utf-8"
        )
        self.source_report = {
            "schema_version": 0,
            "g1_preflight": True,
            "fence_count": 64,
            "raw_module_sha256": sha256(
                self.root / "python/golden_board/source_doctor.py"
            ),
            "source": {
                "path": "docs/64_games.md",
                "byte_length": 165145,
                "sha256": SOURCE_SHA256,
            },
        }
        (self.root / "reports/source-doctor.json").write_bytes(
            encode_canonical_value(self.source_report)
        )
        self.lock = SimpleNamespace(
            anthology=SimpleNamespace(
                path=PurePosixPath("docs/64_games.md"),
                byte_length=165145,
                sha256=SOURCE_SHA256,
            ),
            toolchains=SimpleNamespace(
                python="3.14.6",
                uv="0.11.29",
                rust="1.94.0",
                cargo="1.94.0",
                git="2.49.0",
                cc="Apple clang 17.0.0 (clang-1700.0.13.5) at /usr/bin/cc",
                ld="ld-1167.5 selected by /usr/bin/cc",
                sdk="macOS SDK 15.5 selected by /usr/bin/cc",
            ),
        )
        self.git_executable = Path("/owner/bin/git")
        self.git_environment = {
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "HOME": str(self.root / "check-home"),
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": os.pathsep.join(("/owner/bin", "/usr/bin")),
            "TMPDIR": str(self.root / "check-tmp"),
            "TZ": "UTC",
        }

        patches = (
            patch.object(cli, "load_source_lock", return_value=self.lock),
            patch.object(cli, "build_source_report", return_value=self.source_report),
            patch.object(reports, "load_source_lock", return_value=self.lock),
            patch.object(
                reports, "build_source_report", return_value=self.source_report
            ),
        )
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)

    def generate_release(self) -> bytes:
        self.assertEqual(0, cli.main(["generate", "release-summary"], root=self.root))
        return (self.root / "reports/release-summary.json").read_bytes()

    def test_initial_release_summary_is_canonical_pending_and_deterministic(
        self,
    ) -> None:
        source_before = (self.root / "reports/source-doctor.json").read_bytes()
        first = self.generate_release()
        value = decode_canonical_manifest(first)

        self.assertEqual(first, encode_canonical_value(value))
        self.assertTrue(first.endswith(b"\n"))
        self.assertEqual([], reports.validate_release_summary(value, roadmap()))
        self.assertEqual("pending_m0_verification", value["gates"][0]["result"])
        self.assertNotIn("native_verification", value["gates"][0])
        for gate in value["gates"][1:]:
            self.assertEqual("pending_owner_milestone", gate["result"])
            self.assertNotIn("command", gate)
            self.assertNotIn("evidence", gate)
            self.assertNotIn("candidate_identity", gate)

        report_names = sorted(path.name for path in (self.root / "reports").iterdir())
        self.assertEqual(["release-summary.json", "source-doctor.json"], report_names)
        self.assertEqual(first, self.generate_release())
        self.assertEqual(
            source_before, (self.root / "reports/source-doctor.json").read_bytes()
        )

    def test_task9_source_commands_are_retained_and_check_never_repairs(self) -> None:
        source_path = self.root / "reports/source-doctor.json"
        source_path.write_bytes(b"stale\n")
        self.assertEqual(0, cli.main(["generate", "source-doctor"], root=self.root))
        expected = encode_canonical_value(self.source_report)
        self.assertEqual(expected, source_path.read_bytes())
        self.assertEqual(0, cli.main(["check", "source-report"], root=self.root))
        self.assertEqual(
            Path.cwd(), inspect.signature(cli.main).parameters["root"].default
        )
        self.assertEqual(0, cli.main(["check", "source-report"], self.root))

        source_path.write_bytes(b"stale\n")
        with redirect_stderr(io.StringIO()):
            self.assertEqual(1, cli.main(["check", "source-report"], root=self.root))
        self.assertEqual(b"stale\n", source_path.read_bytes())

    def test_check_commands_are_offline_and_do_not_rewrite_reports(self) -> None:
        release_before = self.generate_release()
        source_before = (self.root / "reports/source-doctor.json").read_bytes()
        with (
            patch(
                "socket.create_connection",
                side_effect=AssertionError("network access attempted"),
            ),
            patch(
                "urllib.request.urlopen",
                side_effect=AssertionError("network access attempted"),
            ),
        ):
            self.assertEqual(0, cli.main(["check", "source-report"], root=self.root))
            self.assertEqual(0, cli.main(["check", "release-summary"], root=self.root))

        with patch.object(cli, "check_tracked_reports", return_value=[]) as checker:
            self.assertEqual(
                0,
                cli.main(
                    ["check", "release-summary"],
                    root=self.root,
                    git_executable=self.git_executable,
                    git_environment=self.git_environment,
                ),
            )
        checker.assert_called_once_with(
            self.root,
            git_executable=self.git_executable,
            git_environment=self.git_environment,
        )

        self.assertEqual(
            source_before, (self.root / "reports/source-doctor.json").read_bytes()
        )
        self.assertEqual(
            release_before,
            (self.root / "reports/release-summary.json").read_bytes(),
        )
        self.assertEqual([], list((self.root / "reports").glob(".*.tmp")))

    def test_native_input_is_canonical_and_only_the_fixed_path_is_accepted(
        self,
    ) -> None:
        with patch.object(
            reports.subprocess,
            "Popen",
            side_effect=AssertionError("pending report path started Git"),
        ):
            before = self.generate_release()
            self.assertEqual(0, cli.main(["check", "release-summary"], root=self.root))
        native = {"schema_version": 0, "probe": "fixed ignored handoff"}
        native_path = self.root / "artifacts/native-verification.json"
        native_path.write_bytes(encode_canonical_value(native))
        sentinel = {"schema_version": 0, "native_was_forwarded": True}

        stderr = io.StringIO()
        with (
            patch.object(
                reports.subprocess,
                "Popen",
                side_effect=AssertionError("missing-context path started Git"),
            ),
            redirect_stderr(stderr),
        ):
            self.assertEqual(
                1,
                cli.main(
                    [
                        "generate",
                        "release-summary",
                        "--native-evidence",
                        "artifacts/native-verification.json",
                    ],
                    root=self.root,
                ),
            )
        self.assertIn("sealed Git context", stderr.getvalue())
        self.assertEqual(
            before,
            (self.root / "reports/release-summary.json").read_bytes(),
        )

        with patch.object(
            cli, "build_release_summary", return_value=sentinel
        ) as builder:
            self.assertEqual(
                0,
                cli.main(
                    [
                        "generate",
                        "release-summary",
                        "--native-evidence",
                        "artifacts/native-verification.json",
                    ],
                    root=self.root,
                    git_executable=self.git_executable,
                    git_environment=self.git_environment,
                ),
            )
        self.assertEqual(native, builder.call_args.args[2])
        self.assertEqual(
            self.git_executable, builder.call_args.kwargs["git_executable"]
        )
        self.assertEqual(
            self.git_environment, builder.call_args.kwargs["git_environment"]
        )
        self.assertEqual(
            encode_canonical_value(sentinel),
            (self.root / "reports/release-summary.json").read_bytes(),
        )

        before = (self.root / "reports/release-summary.json").read_bytes()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(
                2,
                cli.main(
                    [
                        "generate",
                        "release-summary",
                        "--native-evidence",
                        "../native-verification.json",
                    ],
                    root=self.root,
                ),
            )
        self.assertEqual(
            before, (self.root / "reports/release-summary.json").read_bytes()
        )

        before = (self.root / "reports/release-summary.json").read_bytes()
        invalid_native = (
            encode_canonical_value([]),
            b'{"schema_version": 0}\n',
            b"x" * (reports.MAX_REPORT_BYTES + 1),
        )
        for raw in invalid_native:
            native_path.write_bytes(raw)
            with self.subTest(native_length=len(raw)), redirect_stderr(io.StringIO()):
                self.assertEqual(
                    1,
                    cli.main(
                        [
                            "generate",
                            "release-summary",
                            "--native-evidence",
                            "artifacts/native-verification.json",
                        ],
                        root=self.root,
                        git_executable=self.git_executable,
                        git_environment=self.git_environment,
                    ),
                )
            self.assertEqual(
                before,
                (self.root / "reports/release-summary.json").read_bytes(),
            )
            self.assertEqual([], list((self.root / "reports").glob(".*.tmp")))

    def test_failed_atomic_replace_preserves_the_previous_report(self) -> None:
        release_path = self.root / "reports/release-summary.json"
        previous = self.generate_release()
        with (
            patch.object(cli.os, "fsync", side_effect=OSError("fsync failed")),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(
                1, cli.main(["generate", "release-summary"], root=self.root)
            )
        self.assertEqual(previous, release_path.read_bytes())
        self.assertEqual([], list((self.root / "reports").glob(".*.tmp")))

        with (
            patch.object(cli.os, "replace", side_effect=OSError("replace failed")),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(
                1, cli.main(["generate", "release-summary"], root=self.root)
            )
        self.assertEqual(previous, release_path.read_bytes())
        self.assertEqual([], list((self.root / "reports").glob(".*.tmp")))

        real_open = os.open
        real_close = os.close
        opened: list[int] = []

        def tracking_open(*args: object, **kwargs: object) -> int:
            descriptor = real_open(*args, **kwargs)  # type: ignore[arg-type]
            opened.append(descriptor)
            return descriptor

        def fail_root_close(descriptor: int) -> None:
            real_close(descriptor)
            if descriptor == opened[0]:
                raise OSError("root close failed")

        with (
            patch.object(
                cli,
                "held_mount_identity",
                return_value=(self.root.stat().st_dev, None),
            ),
            patch.object(cli, "same_held_mount", return_value=True),
            patch.object(cli.os, "open", side_effect=tracking_open),
            patch.object(cli.os, "close", side_effect=fail_root_close),
            self.assertRaisesRegex(OSError, "root close failed"),
        ):
            cli._open_reports_directory(self.root)
        self.assertEqual(2, len(opened))
        for descriptor in opened:
            with self.assertRaises(OSError):
                os.fstat(descriptor)

        real_open_reports = cli._open_reports_directory
        directories: list[int] = []

        def capture_directory(root: Path, *, create: bool = False) -> int:
            descriptor = real_open_reports(root, create=create)
            directories.append(descriptor)
            return descriptor

        stderr = io.StringIO()
        with (
            patch.object(cli, "_open_reports_directory", side_effect=capture_directory),
            patch.object(cli.os, "fsync", side_effect=OSError("fsync primary")),
            patch.object(cli.os, "unlink", side_effect=OSError("unlink cleanup")),
            redirect_stderr(stderr),
        ):
            self.assertEqual(
                1, cli.main(["generate", "release-summary"], root=self.root)
            )
        self.assertIn("fsync primary", stderr.getvalue())
        self.assertNotIn("unlink cleanup", stderr.getvalue())
        with self.assertRaises(OSError):
            os.fstat(directories.pop())
        temporary = list((self.root / "reports").glob(".*.tmp"))
        self.assertEqual(1, len(temporary))
        temporary[0].unlink()
        self.assertEqual(previous, release_path.read_bytes())

        stderr = io.StringIO()
        with (
            patch.object(cli, "_open_reports_directory", side_effect=capture_directory),
            patch.object(cli.os, "replace", side_effect=OSError("replace primary")),
            patch.object(cli.os, "unlink", side_effect=OSError("unlink cleanup")),
            redirect_stderr(stderr),
        ):
            self.assertEqual(
                1, cli.main(["generate", "release-summary"], root=self.root)
            )
        self.assertIn("replace primary", stderr.getvalue())
        self.assertNotIn("unlink cleanup", stderr.getvalue())
        with self.assertRaises(OSError):
            os.fstat(directories.pop())
        temporary = list((self.root / "reports").glob(".*.tmp"))
        self.assertEqual(1, len(temporary))
        temporary[0].unlink()
        self.assertEqual(previous, release_path.read_bytes())

        published_directory: list[int] = []

        def capture_published_directory(root: Path, *, create: bool = False) -> int:
            descriptor = real_open_reports(root, create=create)
            published_directory.append(descriptor)
            return descriptor

        def fail_published_close(descriptor: int) -> None:
            real_close(descriptor)
            if published_directory and descriptor == published_directory[0]:
                raise OSError("post-commit close")

        with (
            patch.object(
                cli,
                "held_mount_identity",
                return_value=(self.root.stat().st_dev, None),
            ),
            patch.object(cli, "same_held_mount", return_value=True),
            patch.object(
                cli,
                "_open_reports_directory",
                side_effect=capture_published_directory,
            ),
            patch.object(cli.os, "close", side_effect=fail_published_close),
        ):
            self.assertEqual(
                0, cli.main(["generate", "release-summary"], root=self.root)
            )
        self.assertEqual(previous, release_path.read_bytes())

    def test_generate_and_check_reject_symlinked_report_leaves(self) -> None:
        outside = self.root / "outside-report.json"
        outside.write_bytes(b"outside\n")
        source = self.root / "reports/source-doctor.json"
        source.unlink()
        source.symlink_to(outside)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(1, cli.main(["check", "source-report"], root=self.root))

        release = self.root / "reports/release-summary.json"
        release.symlink_to(outside)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(
                1, cli.main(["generate", "release-summary"], root=self.root)
            )
        self.assertEqual(b"outside\n", outside.read_bytes())

    def test_generate_and_check_reject_a_symlinked_reports_parent(self) -> None:
        reports_directory = self.root / "reports"
        actual_directory = self.root / "actual-reports"
        reports_directory.rename(actual_directory)
        reports_directory.symlink_to(actual_directory, target_is_directory=True)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(1, cli.main(["check", "source-report"], root=self.root))
            self.assertEqual(
                1, cli.main(["generate", "release-summary"], root=self.root)
            )

    def test_subprocess_timeout_is_a_stable_cli_failure(self) -> None:
        with (
            patch.object(
                cli,
                "check_tracked_reports",
                side_effect=subprocess.TimeoutExpired(["git", "ls-files"], 30),
            ),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(1, cli.main(["check", "release-summary"], root=self.root))

        hostile = "hostile\x1b[31m\nforged\n" + "x" * 5000
        for returned in (False, True):
            stderr = io.StringIO()
            with (
                patch.object(cli, "check_tracked_reports") as checker,
                redirect_stderr(stderr),
            ):
                if returned:
                    checker.return_value = [hostile]
                else:
                    checker.side_effect = ValueError(hostile)
                self.assertEqual(
                    1, cli.main(["check", "release-summary"], root=self.root)
                )
            rendered = stderr.getvalue()
            self.assertEqual(1, rendered.count("\n"))
            self.assertTrue(
                all(
                    character == "\n" or 0x20 <= ord(character) <= 0x7E
                    for character in rendered
                )
            )
            self.assertIn(r"\x1b", rendered)
            self.assertIn(r"\nforged\n", rendered)
            self.assertLessEqual(len(rendered), 520)

    def test_unknown_or_extra_arguments_fail_with_usage_status(self) -> None:
        invalid = (
            [],
            ["generate"],
            ["generate", "source-report"],
            ["check", "source-doctor"],
            ["check", "release-summary", "extra"],
            ["release", "summary"],
        )
        for argv in invalid:
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()):
                self.assertEqual(2, cli.main(argv, root=self.root))


if __name__ == "__main__":
    unittest.main()
