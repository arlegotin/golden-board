from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import patch

from golden_board.manifest import decode_canonical_manifest, encode_canonical_value
from golden_board import reports


ACCEPTANCE = tuple(f"Requirement {index}" for index in range(1, 19))
OWNERS = (
    "M0",
    "M1", "M1", "M1",
    "M2", "M2", "M2", "M2",
    "M3", "M3",
    "M4", "M4", "M4", "M4",
    "M5", "M5",
    "M6", "M6",
)
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


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for directory in (
            "docs",
            "docs/superpowers/plans",
            "inputs",
            "python/golden_board",
            "reports",
        ):
            (self.root / directory).mkdir(parents=True, exist_ok=True)

        (self.root / "docs/roadmap.md").write_text(roadmap(), encoding="utf-8")
        anthology_bytes = b"anthology\n"
        anthology_path = self.root / "docs/64_games.md"
        anthology_path.write_bytes(anthology_bytes)
        anthology_sha256 = sha256(anthology_path)
        (self.root / "docs/superpowers/plans/ignored.md").write_text(
            "plan\n", encoding="utf-8"
        )
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
                "byte_length": len(anthology_bytes),
                "sha256": anthology_sha256,
            },
        }
        (self.root / "reports/source-doctor.json").write_bytes(
            encode_canonical_value(self.source_report)
        )

        self.tool_versions = {
            "python": "3.14.6",
            "uv": "0.11.29",
            "rust": "1.94.0",
            "cargo": "1.94.0",
            "git": "2.49.0",
            "cc": "Apple clang 17.0.0 (clang-1700.0.13.5) at /usr/bin/cc",
            "ld": "ld-1167.5 selected by /usr/bin/cc",
            "sdk": "macOS SDK 15.5 selected by /usr/bin/cc",
        }
        self.lock = SimpleNamespace(
            anthology=SimpleNamespace(
                path=PurePosixPath("docs/64_games.md"),
                byte_length=len(anthology_bytes),
                sha256=anthology_sha256,
            ),
            toolchains=SimpleNamespace(**self.tool_versions),
        )
        self.git_executable = Path("/owner/bin/git")
        self.git_environment = {
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "HOME": str(self.root / "check-home"),
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": os.pathsep.join(("/owner/bin", "/usr/bin")),
            "TMPDIR": str(self.root / "check-tmp"),
            "TZ": "UTC",
        }
        self.git_context = {
            "git_executable": self.git_executable,
            "git_environment": self.git_environment,
        }
        self.tracked = (
            PurePosixPath("docs/64_games.md"),
            PurePosixPath("docs/roadmap.md"),
            PurePosixPath("docs/superpowers/plans/ignored.md"),
            PurePosixPath("inputs/source-lock.toml"),
            PurePosixPath("python/golden_board/source_doctor.py"),
            PurePosixPath("reports/source-doctor.json"),
            PurePosixPath("reports/release-summary.json"),
        )
        lock_patch = patch.object(reports, "load_source_lock", return_value=self.lock)
        self.real_tracked_paths = reports._tracked_paths
        tracked_patch = patch.object(reports, "_tracked_paths", return_value=self.tracked)
        lock_patch.start()
        tracked_patch.start()
        self.addCleanup(lock_patch.stop)
        self.addCleanup(tracked_patch.stop)

    def inventory(self) -> list[dict[str, str]]:
        included = (
            "docs/64_games.md",
            "inputs/source-lock.toml",
            "python/golden_board/source_doctor.py",
            "reports/source-doctor.json",
        )
        return [
            {"path": relative, "sha256": sha256(self.root / relative)}
            for relative in included
        ]

    def native_evidence(self) -> dict[str, object]:
        return {
            "schema_version": 0,
            "protocol": "native-isolated-v0",
            "result": "pass",
            "roadmap_revision": 1,
            "tool_versions": self.tool_versions.copy(),
            "isolation": {
                "project_environment": ".venv",
                "cache_roots": {
                    "cargo_home": "artifacts/cargo-home",
                    "cargo_target": "artifacts/cargo-target",
                    "uv_cache": "artifacts/uv-cache",
                    "uv_python": "artifacts/uv-python",
                },
                "environment": {
                    "acquisition": {
                        "CARGO_HOME": "artifacts/cargo-home",
                        "CARGO_TARGET_DIR": "artifacts/cargo-target",
                        "UV_CACHE_DIR": "artifacts/uv-cache",
                        "UV_MANAGED_PYTHON": "true",
                        "UV_NO_CONFIG": "1",
                        "UV_PYTHON_INSTALL_DIR": "artifacts/uv-python",
                        "UV_PROJECT_ENVIRONMENT": ".venv",
                    },
                    "offline": {
                        "CARGO_HOME": "artifacts/cargo-home",
                        "CARGO_NET_OFFLINE": "true",
                        "CARGO_TARGET_DIR": "artifacts/cargo-target",
                        "UV_CACHE_DIR": "artifacts/uv-cache",
                        "UV_MANAGED_PYTHON": "true",
                        "UV_NO_CONFIG": "1",
                        "UV_OFFLINE": "1",
                        "UV_PYTHON_DOWNLOADS": "never",
                        "UV_PYTHON_INSTALL_DIR": "artifacts/uv-python",
                        "UV_PROJECT_ENVIRONMENT": ".venv",
                    },
                },
                "network": {
                    "acquisition": "enabled",
                    "offline": "package_manager_offline",
                    "os_enforcement": "not_claimed_at_m0",
                },
            },
            "commands": [
                {
                    "phase": "acquisition",
                    "argv": ["uv", "--no-config", "sync", "--project", ".", "--locked"],
                    "exit_code": 0,
                },
                {
                    "phase": "acquisition",
                    "argv": ["cargo", "fetch", "--manifest-path", "Cargo.toml", "--locked"],
                    "exit_code": 0,
                },
                {
                    "phase": "acquisition",
                    "argv": ["cargo", "build", "--manifest-path", "Cargo.toml", "--workspace", "--locked"],
                    "exit_code": 0,
                },
                {
                    "phase": "offline",
                    "argv": ["uv", "--no-config", "sync", "--project", ".", "--offline", "--locked"],
                    "exit_code": 0,
                },
                {
                    "phase": "offline",
                    "argv": [
                        "cargo", "build", "--manifest-path", "Cargo.toml",
                        "--workspace", "--offline", "--locked"
                    ],
                    "exit_code": 0,
                },
                {
                    "phase": "offline",
                    "argv": ["scripts/check", "full"],
                    "exit_code": 0,
                },
            ],
            "source_report_sha256": sha256(
                self.root / "reports/source-doctor.json"
            ),
            "inputs": self.inventory(),
        }

    def test_acceptance_matrix_is_exactly_g1_through_g18(self) -> None:
        text = roadmap()
        rows = reports.parse_acceptance_matrix(text)
        self.assertEqual(18, len(rows))
        self.assertEqual(("G1", "Requirement 1", "M0"), rows[0])
        self.assertEqual(("G18", "Requirement 18", "M6"), rows[-1])

        duplicate = text.replace("| G2 |", "| G1 |", 1)
        reordered = text.replace(
            "| G1 | Requirement 1 | M0 | Evidence 1 |\n"
            "| G2 | Requirement 2 | M1 | Evidence 2 |",
            "| G2 | Requirement 2 | M1 | Evidence 2 |\n"
            "| G1 | Requirement 1 | M0 | Evidence 1 |",
        )
        oversized = text + "x" * (4 * 1024 * 1024 + 1 - len(text))
        duplicated_matrix = text.replace(
            "## 13. Project status — sole mutable authority\n",
            text[text.index(reports.ACCEPTANCE_HEADING) :],
        )
        prefixed_terminator = text.replace(
            "\n---\n\n## 13. Project status — sole mutable authority",
            "\n---not-a-terminator\n"
            "| G1 | Conflicting requirement | M0 | Conflicting evidence |\n"
            "---\n\n## 13. Project status — sole mutable authority",
        )
        for case, malformed in (
            ("duplicate gate", duplicate),
            ("reordered gates", reordered),
            ("wrong final gate", text.replace("| G18 |", "| G19 |")),
            ("oversized roadmap", oversized),
            ("duplicated matrix", duplicated_matrix),
            ("prefixed terminator", prefixed_terminator),
        ):
            with self.subTest(case=case):
                with self.assertRaises(reports.ReportError):
                    reports.parse_acceptance_matrix(malformed)
        with self.assertRaises(reports.ReportError):
            reports._roadmap_revision(oversized)

    def test_without_native_evidence_only_g1_is_pending_m0(self) -> None:
        value = reports.build_release_summary(self.root, self.source_report)
        self.assertEqual("pending_m0_verification", value["gates"][0]["result"])
        self.assertNotIn("native_verification", value["gates"][0])
        for gate in value["gates"][1:]:
            self.assertEqual("pending_owner_milestone", gate["result"])
            self.assertNotIn("evidence", gate)
            self.assertNotIn("command", gate)
            self.assertNotIn("candidate_identity", gate)
        self.assertEqual([], reports.validate_release_summary(value, roadmap()))

    def test_validated_native_projection_closes_g1_and_is_embedded(self) -> None:
        native = self.native_evidence()
        validated = reports.validate_native_evidence(
            self.root, native, **self.git_context
        )
        self.assertEqual(native, validated)
        self.assertIsNot(native, validated)

        value = reports.build_release_summary(
            self.root, self.source_report, native, **self.git_context
        )
        g1 = value["gates"][0]
        self.assertEqual("pass", g1["result"])
        self.assertEqual(native, g1["native_verification"])
        self.assertEqual(native, reports.native_evidence_from_summary(value))
        self.assertEqual([], reports.validate_release_summary(value, roadmap()))

        claimed_bytes = b"different anthology\n"
        claimed_sha256 = hashlib.sha256(claimed_bytes).hexdigest()
        inconsistent_report = dict(self.source_report)
        inconsistent_report["source"] = {
            "path": "docs/64_games.md",
            "byte_length": len(claimed_bytes),
            "sha256": claimed_sha256,
        }
        (self.root / "reports/source-doctor.json").write_bytes(
            encode_canonical_value(inconsistent_report)
        )
        inconsistent_lock = SimpleNamespace(
            anthology=SimpleNamespace(
                path=PurePosixPath("docs/64_games.md"),
                byte_length=len(claimed_bytes),
                sha256=claimed_sha256,
            ),
            toolchains=self.lock.toolchains,
        )
        inconsistent_native = self.native_evidence()
        operations = {
            "standalone validation": lambda: reports.validate_native_evidence(
                self.root, inconsistent_native, **self.git_context
            ),
            "release build": lambda: reports.build_release_summary(
                self.root,
                inconsistent_report,
                inconsistent_native,
                **self.git_context,
            ),
        }
        with patch.object(
            reports, "load_source_lock", return_value=inconsistent_lock
        ):
            for operation_name, operation in operations.items():
                with self.subTest(operation=operation_name):
                    with self.assertRaises(reports.ReportError):
                        operation()

    def test_native_evidence_rejects_tampering_and_self_cycles(self) -> None:
        mutations: list[dict[str, object]] = []

        wrong_tool = self.native_evidence()
        wrong_tool["tool_versions"] = self.tool_versions | {"python": "3.14.5"}
        mutations.append(wrong_tool)

        wrong_hash = self.native_evidence()
        wrong_hash["inputs"] = [dict(item) for item in self.inventory()]
        wrong_hash["inputs"][0]["sha256"] = "0" * 64
        mutations.append(wrong_hash)

        unmanaged_python = self.native_evidence()
        isolation = unmanaged_python["isolation"]
        self.assertIsInstance(isolation, dict)
        environment = isolation["environment"]
        self.assertIsInstance(environment, dict)
        acquisition = environment["acquisition"]
        self.assertIsInstance(acquisition, dict)
        acquisition["UV_MANAGED_PYTHON"] = "false"
        mutations.append(unmanaged_python)

        online_offline_phase = self.native_evidence()
        isolation = online_offline_phase["isolation"]
        self.assertIsInstance(isolation, dict)
        network = isolation["network"]
        self.assertIsInstance(network, dict)
        network["offline"] = "enabled"
        mutations.append(online_offline_phase)

        boolean_exit = self.native_evidence()
        boolean_exit["commands"] = [
            dict(command) for command in boolean_exit["commands"]
        ]
        boolean_exit["commands"][0]["exit_code"] = False
        mutations.append(boolean_exit)

        self_cycle = self.native_evidence()
        self_cycle["inputs"] = self.inventory() + [
            {"path": "reports/release-summary.json", "sha256": "1" * 64}
        ]
        mutations.append(self_cycle)

        timestamp = self.native_evidence()
        timestamp["timestamp"] = "2026-08-02T00:00:00Z"
        mutations.append(timestamp)

        fake_pass = {"result": "pass"}
        mutations.append(fake_pass)

        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(reports.ReportError):
                    reports.validate_native_evidence(
                        self.root, mutation, **self.git_context
                    )

    def test_native_evidence_cannot_override_failed_source_preflight(self) -> None:
        failed = dict(self.source_report)
        failed["g1_preflight"] = False
        (self.root / "reports/source-doctor.json").write_bytes(
            encode_canonical_value(failed)
        )
        native = self.native_evidence()
        operations = {
            "standalone validation": lambda: reports.validate_native_evidence(
                self.root, native, **self.git_context
            ),
            "release build": lambda: reports.build_release_summary(
                self.root, failed, native, **self.git_context
            ),
        }
        for operation_name, operation in operations.items():
            with self.subTest(operation=operation_name):
                with self.assertRaises(reports.ReportError):
                    operation()

    def test_identity_hashing_rejects_a_regular_file_over_the_m0_cap(self) -> None:
        oversized = self.root / "oversized.bin"
        with oversized.open("wb") as stream:
            stream.truncate(reports.MAX_IDENTITY_FILE_BYTES + 1)
        with self.assertRaises(reports.ReportError):
            reports._sha256_below(self.root, PurePosixPath("oversized.bin"))

    def test_native_inventory_rejects_a_symlinked_parent_component(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "payload").write_bytes(b"outside\n")
        (self.root / "linked").symlink_to(outside, target_is_directory=True)
        with patch.object(
            reports,
            "_tracked_paths",
            return_value=(PurePosixPath("linked/payload"),),
        ):
            with self.assertRaises(reports.ReportError):
                reports._native_inventory(self.root, **self.git_context)

    def test_report_read_rejects_a_symlinked_parent_component(self) -> None:
        reports_directory = self.root / "reports"
        actual_directory = self.root / "actual-reports"
        reports_directory.rename(actual_directory)
        reports_directory.symlink_to(actual_directory, target_is_directory=True)
        with self.assertRaises(reports.ReportError):
            reports.build_release_summary(self.root, self.source_report)

    def test_report_read_rejects_a_symlinked_leaf(self) -> None:
        report = self.root / "reports/source-doctor.json"
        outside = self.root / "outside-source-report.json"
        outside.write_bytes(report.read_bytes())
        report.unlink()
        report.symlink_to(outside)
        with self.assertRaises(reports.ReportError):
            reports.build_release_summary(self.root, self.source_report)

    def test_later_gate_evidence_and_unknown_fields_are_rejected(self) -> None:
        value = reports.build_release_summary(self.root, self.source_report)
        value["gates"][1]["evidence"] = [{"sha256": "0" * 64}]
        errors = reports.validate_release_summary(value, roadmap())
        self.assertTrue(any("G2" in error for error in errors), errors)

        value = reports.build_release_summary(self.root, self.source_report)
        value["generated_at"] = "2026-08-02T00:00:00Z"
        errors = reports.validate_release_summary(value, roadmap())
        self.assertTrue(any("top-level keys" in error for error in errors), errors)

        value = reports.build_release_summary(self.root, self.source_report)
        self.assertTrue(reports.validate_release_summary(value, None))

    def test_release_summary_has_no_output_identity_in_generation_inputs(self) -> None:
        value = reports.build_release_summary(
            self.root,
            self.source_report,
            self.native_evidence(),
            **self.git_context,
        )
        paths = {item["path"] for item in value["generation_inputs"]}
        self.assertNotIn("reports/release-summary.json", paths)
        native_paths = {
            item["path"] for item in value["gates"][0]["native_verification"]["inputs"]
        }
        self.assertNotIn("docs/roadmap.md", native_paths)
        self.assertNotIn("reports/release-summary.json", native_paths)
        self.assertFalse(any(path.startswith("docs/superpowers/") for path in native_paths))

    def test_check_tracked_reports_regenerates_both_approved_reports(self) -> None:
        value = reports.build_release_summary(
            self.root,
            self.source_report,
            self.native_evidence(),
            **self.git_context,
        )
        (self.root / "reports/release-summary.json").write_bytes(
            encode_canonical_value(value)
        )
        with patch.object(
            reports, "build_source_report", return_value=self.source_report
        ):
            self.assertEqual(
                [], reports.check_tracked_reports(self.root, **self.git_context)
            )

        (self.root / "reports/release-summary.json").write_bytes(b"{}\n")
        with patch.object(
            reports, "build_source_report", return_value=self.source_report
        ):
            errors = reports.check_tracked_reports(self.root, **self.git_context)
        self.assertTrue(errors)

    def test_report_encoding_is_canonical_and_final_lf_terminated(self) -> None:
        value = reports.build_release_summary(self.root, self.source_report)
        raw = encode_canonical_value(value)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertFalse(raw.endswith(b"\n\n"))
        self.assertEqual(value, decode_canonical_manifest(raw))

    def test_identity_paths_require_canonical_posix_syntax(self) -> None:
        for value in (
            "\0payload",
            "nested\\payload",
            "nested//payload",
            "nested/",
            "./nested",
            "nested/./payload",
            "nested/../payload",
            "../payload",
            "/payload",
        ):
            with self.subTest(value=value), self.assertRaises(reports.ReportError):
                reports._safe_relative_path(value, "test path")

    def test_source_report_schema_version_rejects_boolean(self) -> None:
        malformed = dict(self.source_report)
        malformed["schema_version"] = False
        (self.root / "reports/source-doctor.json").write_bytes(
            encode_canonical_value(malformed)
        )
        with self.assertRaisesRegex(reports.ReportError, "integer 0"):
            reports.build_release_summary(self.root, malformed)

    def test_release_summary_requires_exact_static_identity_graph(self) -> None:
        original = reports.build_release_summary(self.root, self.source_report)
        mutations = []

        missing_input = decode_canonical_manifest(encode_canonical_value(original))
        missing_input["generation_inputs"].pop()
        mutations.append(missing_input)

        substituted_input = decode_canonical_manifest(encode_canonical_value(original))
        substituted_input["generation_inputs"][0]["path"] = "docs/other.md"
        mutations.append(substituted_input)

        wrong_kind = decode_canonical_manifest(encode_canonical_value(original))
        wrong_kind["gates"][0]["evidence"][0]["kind"] = "other"
        mutations.append(wrong_kind)

        wrong_path = decode_canonical_manifest(encode_canonical_value(original))
        wrong_path["gates"][0]["evidence"][1]["path"] = "reports/other.json"
        mutations.append(wrong_path)

        reversed_evidence = decode_canonical_manifest(encode_canonical_value(original))
        reversed_evidence["gates"][0]["evidence"].reverse()
        mutations.append(reversed_evidence)

        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assertTrue(
                    reports.validate_release_summary(mutation, roadmap())
                )

    def test_git_inventory_uses_only_absolute_injected_git_and_closed_env(self) -> None:
        with patch.object(
            reports.subprocess,
            "Popen",
            side_effect=AssertionError("must not spawn"),
        ):
            with self.assertRaises(reports.ReportError):
                reports._bounded_git_output(
                    self.root,
                    git_executable=Path("git"),
                    git_environment=self.git_environment,
                )
            with self.assertRaises(reports.ReportError):
                reports._bounded_git_output(
                    self.root,
                    git_executable=self.git_executable,
                    git_environment=self.git_environment | {"GIT_DIR": "/outside"},
                )

        captured: dict[str, object] = {}

        class StopSpawn(RuntimeError):
            pass

        def capture(argv: list[str], **kwargs: object) -> object:
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            raise StopSpawn

        with (
            patch.dict(
                os.environ,
                {
                    "GIT_DIR": "/outside",
                    "GIT_WORK_TREE": "/outside",
                    "GIT_CONFIG_COUNT": "1",
                },
                clear=False,
            ),
            patch.object(reports.subprocess, "Popen", side_effect=capture),
            self.assertRaises(StopSpawn),
        ):
            reports._bounded_git_output(self.root, **self.git_context)

        argv = captured["argv"]
        kwargs = captured["kwargs"]
        self.assertEqual(str(self.git_executable), argv[0])
        self.assertEqual(self.git_environment, kwargs["env"])
        self.assertNotIn("GIT_DIR", kwargs["env"])
        self.assertNotIn("GIT_WORK_TREE", kwargs["env"])
        self.assertIs(False, kwargs["shell"])
        self.assertIs(True, kwargs["close_fds"])

        for raw in (b"tracked", b"tracked\0\0other\0", b"\0"):
            with (
                self.subTest(raw=raw),
                patch.object(reports, "_bounded_git_output", return_value=raw),
                self.assertRaises(reports.ReportError),
            ):
                self.real_tracked_paths(self.root, **self.git_context)
        with patch.object(
            reports, "_bounded_git_output", return_value=b"tracked\0"
        ):
            self.assertEqual(
                (PurePosixPath("tracked"),),
                self.real_tracked_paths(self.root, **self.git_context),
            )


if __name__ == "__main__":
    unittest.main()
