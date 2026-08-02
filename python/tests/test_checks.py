from __future__ import annotations

import ast
import copy
import hashlib
import io
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from types import SimpleNamespace
from unittest.mock import patch

from golden_board import acquisition, bootstrap, checks, cli, registry
from golden_board.acquisition import (
    AcquisitionError,
    INVENTORY_PATH,
    build_inventory,
    validate_inventory,
    write_inventory,
)
from golden_board.bootstrap import BootstrapError
from golden_board.checks import FOCUS_AREAS, run_area, run_mode


ROOT = Path(__file__).resolve().parents[2]
GIT_ENVIRONMENT = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_TERMINAL_PROMPT": "0",
    "HOME": str(ROOT / "artifacts/check-home"),
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/opt/homebrew/bin",
    "TMPDIR": str(ROOT / "artifacts/check-tmp"),
    "TZ": "UTC",
}


def _copy_repository() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name) / "checkout"
    shutil.copytree(
        ROOT,
        root,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", "artifacts", "target", "__pycache__", ".superpowers"
        ),
    )
    return temporary, root


def _snapshot(root: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    ignored = {".git", ".superpowers", ".venv", "artifacts", "target", "__pycache__"}
    pending = [root]
    while pending:
        directory = pending.pop()
        for entry in os.scandir(directory):
            path = Path(entry.path)
            if entry.name in ignored:
                continue
            if entry.is_dir(follow_symlinks=False):
                pending.append(path)
            elif entry.is_file(follow_symlinks=False):
                result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def _fake_inventory_root(root: Path) -> None:
    for relative in (
        "artifacts/uv-cache",
        "artifacts/uv-python",
        "artifacts/cargo-home",
    ):
        path = root / relative
        path.mkdir(parents=True, exist_ok=True)
        (path / "payload").write_bytes(relative.encode())
    lock = root / "Cargo.lock"
    lock.write_text("version = 4\n", encoding="utf-8")


class CommandContractTests(unittest.TestCase):
    def test_focus_areas_are_exact_and_ordered(self) -> None:
        self.assertEqual(
            ("foundation", "dependencies", "identity", "manifest", "source"),
            FOCUS_AREAS,
        )

    def test_cli_dispatches_fast_full_and_every_focus(self) -> None:
        with patch.object(checks, "run_mode", return_value=[]) as mode:
            self.assertEqual(0, cli.main(("check", "fast"), ROOT))
            self.assertEqual(0, cli.main(("check", "full"), ROOT))
        self.assertEqual(["fast", "full"], [call.args[1] for call in mode.call_args_list])
        with patch.object(checks, "run_area", return_value=[]) as area:
            for name in FOCUS_AREAS:
                self.assertEqual(0, cli.main(("check", "focused", name), ROOT))
        self.assertEqual(list(FOCUS_AREAS), [call.args[1] for call in area.call_args_list])

    def test_cli_forwards_the_explicit_git_capability(self) -> None:
        executable = Path("/opt/homebrew/bin/git")
        with patch.object(checks, "run_mode", return_value=[]) as run:
            self.assertEqual(
                0,
                cli.main(
                    ("check", "fast"),
                    ROOT,
                    git_executable=executable,
                    git_environment=GIT_ENVIRONMENT,
                ),
            )
        self.assertEqual(executable, run.call_args.kwargs["git_executable"])
        self.assertEqual(GIT_ENVIRONMENT, run.call_args.kwargs["git_environment"])

    def test_callable_cli_never_reads_the_ambient_git_capability(self) -> None:
        with (
            patch.dict(os.environ, {"GB_BOOTSTRAP_GIT": "/attacker"}, clear=False),
            patch.object(cli, "_module_git_context", side_effect=AssertionError("ambient Git")),
            patch.object(checks, "run_mode", return_value=[]),
        ):
            self.assertEqual(0, cli.main(("check", "fast"), ROOT))

    def test_cli_maps_check_failure_usage_and_release_statuses(self) -> None:
        error = io.StringIO()
        with patch.object(checks, "run_mode", return_value=["broken"]), redirect_stderr(error):
            self.assertEqual(1, cli.main(("check", "fast"), ROOT))
        self.assertIn("broken", error.getvalue())
        for arguments in (
            (),
            ("fast",),
            ("check",),
            ("check", "focused"),
            ("check", "focused", "unknown"),
            ("check", "fast", "extra"),
            ("generate", "release-summary", "--native-evidence", "elsewhere.json"),
            ("module", "golden_board.identity"),
        ):
            with self.subTest(arguments=arguments), redirect_stderr(io.StringIO()):
                self.assertEqual(2, cli.main(arguments, ROOT))
        with redirect_stderr(error := io.StringIO()):
            self.assertEqual(2, cli.main(("check", "release"), ROOT))
        self.assertIn("M2 architecture freeze", error.getvalue())

    def test_bootstrap_argument_grammar_is_closed(self) -> None:
        accepted = (
            (),
            ("fast",),
            ("full",),
            ("release",),
            *(("focused", area) for area in FOCUS_AREAS),
            ("generate", "source-doctor"),
            ("generate", "release-summary"),
            (
                "generate",
                "release-summary",
                "--native-evidence",
                "artifacts/native-verification.json",
            ),
        )
        for arguments in accepted:
            with self.subTest(arguments=arguments):
                self.assertIsInstance(bootstrap.check_command(arguments), tuple)
        for arguments in (
            ("focused",),
            ("focused", "other"),
            ("generate", "source-doctor", "elsewhere"),
            ("generate", "release-summary", "--native-evidence", "../native.json"),
            ("environment", "verify-native"),
            ("python", "-m", "golden_board.identity"),
        ):
            with self.subTest(arguments=arguments), self.assertRaises(BootstrapError):
                bootstrap.check_command(arguments)

    def test_wrappers_are_privileged_isolated_and_do_not_expose_raw_package_commands(self) -> None:
        for name, mode in (("setup", "acquire"), ("check", "check")):
            raw = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            self.assertTrue(raw.startswith("#!/bin/sh -p\ncase $- in\n"), name)
            self.assertIn('python3.14', raw)
            self.assertIn('-I -S -B', raw)
            self.assertIn(f'"{mode}"', raw)
            self.assertNotIn("/usr/bin/env", raw)
            self.assertNotIn("eval", raw)
            self.assertNotIn("pip ", raw)
            self.assertNotIn("cargo install", raw)
            self.assertTrue((ROOT / "scripts" / name).stat().st_mode & stat.S_IXUSR)

    def test_wrapper_privileged_startup_ignores_hostile_shell_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            marker = directory / "executed"
            startup = directory / "startup"
            startup.write_text(f": > {marker}\n", encoding="utf-8")
            function = f"() {{ : > {marker}; }}"
            environment = {
                "BASH_ENV": str(startup),
                "BASH_FUNC_command%%": function,
                "ENV": str(startup),
                "GB_CLEAN_LINUX_DIGEST": "",
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": "",
                "TZ": "UTC",
            }
            result = subprocess.run(
                [str(ROOT / "scripts/check")],
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                close_fds=True,
                timeout=10,
                check=False,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(marker.exists())


class CheckBehaviorTests(unittest.TestCase):
    def mutate(self, relative: str, transform) -> Path:
        temporary, root = _copy_repository()
        self.addCleanup(temporary.cleanup)
        path = root / relative
        path.write_text(transform(path.read_text(encoding="utf-8")), encoding="utf-8")
        return root

    def test_repository_passes_each_static_focus_without_mutation(self) -> None:
        before = _snapshot(ROOT)
        for area in ("foundation", "dependencies", "source"):
            with self.subTest(area=area):
                self.assertEqual([], run_area(ROOT, area))
        self.assertEqual(before, _snapshot(ROOT))

    def test_full_dispatch_preserves_every_product_byte(self) -> None:
        before = _snapshot(ROOT)
        with (
            patch.object(checks, "_cargo_and_vectors", return_value=[]),
            patch.object(checks, "_python_tests", return_value=[]),
        ):
            self.assertEqual([], run_mode(ROOT, "full"))
        self.assertEqual(before, _snapshot(ROOT))

    def test_unknown_area_and_mode_fail_closed(self) -> None:
        self.assertTrue(run_area(ROOT, "unknown"))
        self.assertTrue(run_mode(ROOT, "unknown"))

    def test_foundation_detects_agent_and_status_header_mutations(self) -> None:
        root = self.mutate("AGENTS.md", lambda text: text.replace("deterministic", "random"))
        self.assertTrue(run_area(root, "foundation"))
        root = self.mutate(
            "docs/roadmap.md",
            lambda text: text.replace(
                "| Project state | In progress |", "| Project state | Complete |", 1
            ),
        )
        self.assertTrue(run_area(root, "foundation"))

    def test_foundation_detects_readme_authority_and_copied_source_facts(self) -> None:
        for addition in (
            "\nCurrent milestone: M0\n",
            "\nlexical_ply_total: 1\n",
            "\nfence_count: 64\n",
        ):
            with self.subTest(addition=addition):
                root = self.mutate("README.md", lambda text, addition=addition: text + addition)
                self.assertTrue(run_area(root, "foundation"))

    def test_foundation_rejects_unexpected_report_and_nonfinal_lf(self) -> None:
        temporary, root = _copy_repository()
        self.addCleanup(temporary.cleanup)
        (root / "reports/extra.json").write_text("{}\n", encoding="utf-8")
        self.assertTrue(run_area(root, "foundation"))
        (root / "reports/extra.json").unlink()
        agents = (root / "AGENTS.md").read_bytes()
        (root / "AGENTS.md").write_bytes(agents.rstrip(b"\n"))
        self.assertTrue(run_area(root, "foundation"))
        (root / "AGENTS.md").write_bytes(agents)
        (root / "reports/extra-directory").mkdir()
        self.assertTrue(run_area(root, "foundation"))

    def test_foundation_rejects_unreviewed_spec_and_writable_wrapper(self) -> None:
        temporary, root = _copy_repository()
        self.addCleanup(temporary.cleanup)
        (root / "spec/transport-v0.json").write_text("{}\n", encoding="utf-8")
        self.assertTrue(run_area(root, "foundation"))
        (root / "spec/transport-v0.json").unlink()
        (root / "scripts/check").chmod(0o775)
        self.assertTrue(run_area(root, "foundation"))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks required")
    def test_public_checks_reject_a_symlinked_repository_root(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        link = Path(temporary.name) / "checkout"
        link.symlink_to(ROOT, target_is_directory=True)
        self.assertTrue(run_area(link, "foundation"))
        self.assertTrue(run_mode(link, "fast"))

    def test_dependencies_detect_python_and_rust_manifest_mutations(self) -> None:
        mutations = (
            (
                "pyproject.toml",
                lambda text: text.replace("dependencies = []", 'dependencies = ["chess"]'),
            ),
            (
                "crates/golden-board-core/Cargo.toml",
                lambda text: text + '\nserde = "1"\n',
            ),
            ("Cargo.lock", lambda text: text.replace("registry+", "git+", 1)),
            ("Cargo.toml", lambda text: text + '\n[patch.crates-io]\nsha2 = { path = "vendor" }\n'),
        )
        for relative, transform in mutations:
            with self.subTest(relative=relative):
                self.assertTrue(run_area(self.mutate(relative, transform), "dependencies"))

    def test_dependencies_detect_global_install_and_unlocked_commands(self) -> None:
        for addition in (
            "\npip install chess\n",
            "\ncargo install cargo-audit\n",
            "\nuv run python -m unittest\n",
            "\ncargo test\n",
            "\ncurl https://example.invalid\n",
        ):
            with self.subTest(addition=addition):
                root = self.mutate("scripts/check", lambda text, addition=addition: text + addition)
                (root / "scripts/check").chmod(0o755)
                self.assertTrue(run_area(root, "dependencies"))
        root = self.mutate(
            "scripts/check",
            lambda text: text.replace(
                "gb_uv=$(command -v uv)", "gb_uv=$(command -v unreviewed-uv)"
            ),
        )
        (root / "scripts/check").chmod(0o755)
        self.assertTrue(run_area(root, "dependencies"))

    def test_dependencies_detect_undeclared_import_and_process_execution(self) -> None:
        for addition in (
            "\nimport chess\n",
            "\nimport subprocess\nsubprocess.run(['curl'])\n",
            "\nimport os\nos.system('true')\n",
        ):
            with self.subTest(addition=addition):
                root = self.mutate(
                    "python/golden_board/identity.py",
                    lambda text, addition=addition: text + addition,
                )
                self.assertTrue(run_area(root, "dependencies"))
        root = self.mutate(
            "python/golden_board/cli.py",
            lambda text: text + "\nsubprocess.run(['/attacker'])\n",
        )
        self.assertTrue(run_area(root, "dependencies"))

    def test_process_audit_detects_unreviewed_bounded_runner_calls(self) -> None:
        root = self.mutate(
            "python/golden_board/identity.py",
            lambda text: text
            + "\nfrom golden_board.registry import _run_bounded_process\n"
            + "_run_bounded_process(['/attacker'], b'', {}, timeout=1, output_limit=1)\n",
        )
        self.assertTrue(checks._imports_and_processes(root))

    def test_dependencies_detect_rust_process_execution(self) -> None:
        root = self.mutate(
            "crates/golden-board-core/src/lib.rs",
            lambda text: text + '\nfn bad() { std::process::Command::new("curl"); }\n',
        )
        self.assertTrue(run_area(root, "dependencies"))

    def test_source_detects_stale_report_lock_and_copied_doctor_fields(self) -> None:
        root = self.mutate(
            "reports/source-doctor.json",
            lambda text: text.replace('"fence_count":64', '"fence_count":63'),
        )
        self.assertTrue(run_area(root, "source"))
        root = self.mutate(
            "spec/identity-v0.md", lambda text: text + "\ntag_inventory: copied\n"
        )
        self.assertTrue(run_area(root, "source"))

    def test_pending_report_check_does_not_invoke_git_inventory(self) -> None:
        with patch("golden_board.reports.subprocess.Popen", side_effect=AssertionError("git")):
            self.assertEqual([], run_area(ROOT, "foundation"))

    def test_foundation_does_not_regenerate_the_anthology_report(self) -> None:
        with patch(
            "golden_board.reports.build_source_report",
            side_effect=AssertionError("source regeneration"),
        ):
            self.assertEqual([], run_area(ROOT, "foundation"))

    def test_native_report_check_requires_and_forwards_git_context(self) -> None:
        native_summary = copy.deepcopy(
            __import__("golden_board.manifest", fromlist=["decode_canonical_manifest"])
            .decode_canonical_manifest((ROOT / "reports/release-summary.json").read_bytes())
        )
        native_summary["gates"][0]["result"] = "pass"
        native_summary["gates"][0]["native_verification"] = {}
        temporary, root = _copy_repository()
        self.addCleanup(temporary.cleanup)
        (root / "reports/release-summary.json").write_bytes(
            __import__("golden_board.manifest", fromlist=["encode_canonical_value"])
            .encode_canonical_value(native_summary)
        )
        self.assertTrue(run_area(root, "foundation"))

    def test_completed_malformed_release_is_an_error_not_a_traceback(self) -> None:
        from golden_board.manifest import encode_canonical_value
        from golden_board.status import render_m0_completion

        temporary, root = _copy_repository()
        self.addCleanup(temporary.cleanup)
        digest = hashlib.sha256((root / "reports/source-doctor.json").read_bytes()).hexdigest()
        roadmap = render_m0_completion(
            (root / "docs/roadmap.md").read_text(encoding="utf-8"),
            completed_on="2026-08-02",
            source_report_sha256=digest,
        )
        (root / "docs/roadmap.md").write_text(roadmap, encoding="utf-8")
        (root / "reports/release-summary.json").write_bytes(
            encode_canonical_value(
                {
                    "schema_version": 0,
                    "roadmap_revision": 1,
                    "generation_inputs": [],
                    "gates": [],
                }
            )
        )
        self.assertTrue(run_area(root, "foundation"))

    def test_focus_areas_run_their_own_units_and_registered_family(self) -> None:
        for area, module in (
            ("identity", "tests.test_identity"),
            ("manifest", "tests.test_manifest"),
            ("source", "tests.test_source_doctor"),
        ):
            with (
                self.subTest(area=area),
                patch.object(checks, "_python_tests", return_value=[]) as python_tests,
                patch.object(checks, "_cargo_and_vectors", return_value=[]) as cargo,
                patch.object(checks, "_source_errors", return_value=[]),
                patch.object(checks, "_generated_errors", return_value=[]),
                patch.object(checks, "run_registered_vectors", return_value=[]) as vectors,
            ):
                self.assertEqual([], run_area(ROOT, area))
            self.assertIn(module, python_tests.call_args.args[1])
            if area == "source":
                self.assertEqual({"source-doctor"}, vectors.call_args.kwargs["families"])
            else:
                self.assertEqual({area}, cargo.call_args.kwargs["families"])

    def test_completed_status_requires_exact_report_identity_path_and_passing_g1(self) -> None:
        from golden_board.status import render_m0_completion

        temporary, root = _copy_repository()
        self.addCleanup(temporary.cleanup)
        digest = hashlib.sha256((root / "reports/source-doctor.json").read_bytes()).hexdigest()
        roadmap = (root / "docs/roadmap.md").read_text(encoding="utf-8")
        completed = render_m0_completion(
            roadmap,
            completed_on="2026-08-02",
            source_report_sha256=digest,
        )
        (root / "docs/roadmap.md").write_text(completed, encoding="utf-8")
        self.assertTrue(run_area(root, "foundation"))
        (root / "docs/roadmap.md").write_text(
            completed.replace("reports/source-doctor.json", "reports/release-summary.json", 1),
            encoding="utf-8",
        )
        self.assertTrue(run_area(root, "foundation"))

    def test_dependencies_require_project_local_environment_and_exact_tool_pins(self) -> None:
        for relative, transform in (
            (".gitignore", lambda text: text.replace(".venv/\n", "")),
            (".python-version", lambda _: "3.14.5\n"),
            ("rust-toolchain.toml", lambda text: text.replace("1.94.0", "stable")),
            ("uv.lock", lambda text: text.replace("version = 1", "version = 2")),
        ):
            with self.subTest(relative=relative):
                self.assertTrue(run_area(self.mutate(relative, transform), "dependencies"))


class AcquisitionInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        _fake_inventory_root(self.root)

    def test_inventory_is_bounded_sorted_and_self_validating(self) -> None:
        value = build_inventory(self.root)
        paths = [item["path"] for item in value["files"]]
        self.assertEqual(sorted(paths), paths)
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(value, validate_inventory(self.root, value))

    def test_inventory_records_length_and_sha256(self) -> None:
        value = build_inventory(self.root)
        for item in value["files"]:
            raw = (self.root / item["path"]).read_bytes()
            self.assertEqual(len(raw), item["byte_length"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item["sha256"])

    def test_inventory_excludes_only_cargo_global_cache_bookkeeping(self) -> None:
        cargo_bookkeeping = self.root / "artifacts/cargo-home/.global-cache"
        included_namesake = self.root / "artifacts/uv-cache/.global-cache"
        cargo_bookkeeping.write_bytes(b"mutable timestamps")
        included_namesake.write_bytes(b"hashed payload")
        value = build_inventory(self.root)
        paths = {item["path"] for item in value["files"]}
        self.assertNotIn("artifacts/cargo-home/.global-cache", paths)
        self.assertIn("artifacts/uv-cache/.global-cache", paths)
        write_inventory(self.root, value)
        cargo_bookkeeping.write_bytes(b"new timestamps")
        self.assertEqual(value, acquisition.load_inventory(self.root))
        included_namesake.write_bytes(b"changed payload")
        with self.assertRaises(AcquisitionError):
            acquisition.load_inventory(self.root)

    def test_inventory_caps_and_repeated_validation_are_fail_closed(self) -> None:
        value = build_inventory(self.root)
        write_inventory(self.root, value)
        first = (self.root / INVENTORY_PATH).read_bytes()
        self.assertEqual(value, acquisition.load_inventory(self.root))
        write_inventory(self.root, build_inventory(self.root))
        self.assertEqual(first, (self.root / INVENTORY_PATH).read_bytes())
        with (
            patch.object(acquisition, "MAX_FILES", 1),
            self.assertRaises(AcquisitionError),
        ):
            build_inventory(self.root)
        with (
            patch.object(acquisition, "MAX_ENTRIES", 1),
            self.assertRaises(AcquisitionError),
        ):
            build_inventory(self.root)
        with (
            patch.object(acquisition, "MAX_TOTAL_BYTES", 1),
            self.assertRaises(AcquisitionError),
        ):
            build_inventory(self.root)
        (self.root / "artifacts/uv-cache/payload").write_bytes(b"changed")
        with self.assertRaises(AcquisitionError):
            acquisition.load_inventory(self.root)

    def test_inventory_rejects_missing_extra_changed_and_noncanonical_records(self) -> None:
        value = build_inventory(self.root)
        cases = []
        missing = copy.deepcopy(value)
        missing["files"].pop()
        cases.append(missing)
        extra = copy.deepcopy(value)
        extra["files"].append(copy.deepcopy(extra["files"][-1]))
        cases.append(extra)
        changed = copy.deepcopy(value)
        changed["files"][0]["sha256"] = "0" * 64
        cases.append(changed)
        for candidate in cases:
            with self.subTest(candidate=candidate), self.assertRaises(AcquisitionError):
                validate_inventory(self.root, candidate)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks required")
    def test_inventory_rejects_parent_leaf_and_outside_symlinks(self) -> None:
        target = self.root / "outside"
        target.mkdir()
        (target / "payload").write_bytes(b"outside")
        leaf = self.root / "artifacts/uv-cache/link"
        leaf.symlink_to(target / "payload")
        with self.assertRaises(AcquisitionError):
            build_inventory(self.root)
        leaf.unlink()
        cache = self.root / "artifacts/uv-cache"
        shutil.rmtree(cache)
        cache.symlink_to(target, target_is_directory=True)
        with self.assertRaises(AcquisitionError):
            build_inventory(self.root)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks required")
    def test_inventory_rejects_a_symlinked_repository_root(self) -> None:
        link = self.root.parent / f"{self.root.name}-link"
        link.symlink_to(self.root, target_is_directory=True)
        self.addCleanup(link.unlink)
        with self.assertRaises(AcquisitionError):
            build_inventory(link)

    def test_inventory_publication_is_atomic_and_refuses_unsafe_destination(self) -> None:
        value = build_inventory(self.root)
        write_inventory(self.root, value)
        self.assertEqual(value, acquisition.load_inventory(self.root))
        destination = self.root / INVENTORY_PATH
        destination.unlink()
        destination.mkdir()
        with self.assertRaises(AcquisitionError):
            write_inventory(self.root, value)

    def test_failed_inventory_publication_preserves_the_previous_bytes(self) -> None:
        value = build_inventory(self.root)
        write_inventory(self.root, value)
        before = (self.root / INVENTORY_PATH).read_bytes()
        with (
            patch("golden_board.acquisition.os.replace", side_effect=OSError("injected")),
            self.assertRaises(AcquisitionError),
        ):
            write_inventory(self.root, value)
        self.assertEqual(before, (self.root / INVENTORY_PATH).read_bytes())

    def test_contained_uv_python_links_are_recorded_not_silently_omitted(self) -> None:
        target = self.root / "artifacts/uv-python/payload"
        link = self.root / "artifacts/uv-python/python3"
        link.symlink_to("payload")
        value = build_inventory(self.root)
        self.assertEqual(
            [{"path": "artifacts/uv-python/python3", "target": "payload"}],
            value["links"],
        )
        self.assertEqual(value, validate_inventory(self.root, value))

    def test_cargo_archives_must_match_every_locked_registry_checksum(self) -> None:
        cache = self.root / "artifacts/cargo-home/registry/cache/index"
        cache.mkdir(parents=True)
        raw = b"crate"
        (cache / "demo-1.2.3.crate").write_bytes(raw)
        (self.root / "Cargo.lock").write_text(
            "version = 4\n\n[[package]]\n"
            'name = "demo"\nversion = "1.2.3"\n'
            'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
            f'checksum = "{hashlib.sha256(raw).hexdigest()}"\n',
            encoding="utf-8",
        )
        self.assertIsInstance(build_inventory(self.root), dict)
        (cache / "demo-1.2.3.crate").write_bytes(b"wrong")
        with self.assertRaises(AcquisitionError):
            build_inventory(self.root)


class BootstrapSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def _venv_removal_context(self):
        bootstrap.prepare_directories(self.root, acquisition=True)
        git = self.root / "git"
        git.write_bytes(b"git")
        git.chmod(0o700)
        (self.root / ".git").mkdir(exist_ok=True)
        (self.root / ".git/HEAD").write_text(
            "ref: refs/heads/m0\n", encoding="ascii"
        )
        (self.root / ".git/config").write_text(
            "[core]\n\trepositoryformatversion = 0\n", encoding="ascii"
        )
        (self.root / ".gitignore").write_text(".venv/\n", encoding="ascii")

        def runner(argv, raw, environment, **kwargs):
            del environment, kwargs
            if argv[1:3] == ["--no-pager", "config"]:
                return b"core.repositoryformatversion\0", b""
            if "check-ignore" in argv:
                return b".gitignore\x001\x00.venv/\x00" + raw, b""
            return b"", b""

        return {
            "git_executable": git,
            "git_environment": bootstrap.git_environment(self.root, git),
            "runner": runner,
        }

    def test_runtime_directories_are_created_only_at_declared_paths(self) -> None:
        bootstrap.prepare_directories(self.root, acquisition=False)
        for relative in bootstrap.RUNTIME_DIRECTORIES:
            self.assertTrue((self.root / relative).is_dir(), relative)
        self.assertEqual(
            {"artifacts", ".venv"} & {item.name for item in self.root.iterdir()},
            {item.name for item in self.root.iterdir()},
        )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks required")
    def test_runtime_directories_reject_symlink_and_nondirectory_components(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "artifacts").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(BootstrapError):
            bootstrap.prepare_directories(self.root, acquisition=False)
        (self.root / "artifacts").unlink()
        (self.root / "artifacts").write_bytes(b"file")
        with self.assertRaises(BootstrapError):
            bootstrap.prepare_directories(self.root, acquisition=False)

    def test_tool_validation_requires_absolute_regular_executable_and_exact_version(self) -> None:
        tool = self.root / "tool"
        tool.write_bytes(b"tool")
        tool.chmod(0o700)
        runner = lambda argv, **kwargs: SimpleNamespace(returncode=0, stdout=b"tool 1.2.3\n", stderr=b"")
        self.assertEqual(tool, bootstrap.validate_tool(tool, ("--version",), b"tool 1.2.3\n", runner=runner))
        with self.assertRaises(BootstrapError):
            bootstrap.validate_tool(Path("tool"), ("--version",), b"tool 1.2.3\n", runner=runner)
        with self.assertRaises(BootstrapError):
            bootstrap.validate_tool(tool, ("--version",), b"tool 9\n", runner=runner)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks required")
    def test_tool_validation_resolves_bootstrap_symlink_but_rejects_unsafe_target(self) -> None:
        real = self.root / "real"
        real.write_bytes(b"tool")
        real.chmod(0o700)
        link = self.root / "tool"
        link.symlink_to(real)
        runner = lambda argv, **kwargs: SimpleNamespace(returncode=0, stdout=b"tool\n", stderr=b"")
        self.assertEqual(real, bootstrap.validate_tool(link, (), b"tool\n", runner=runner))
        real.chmod(0o722)
        with self.assertRaises(BootstrapError):
            bootstrap.validate_tool(link, (), b"tool\n", runner=runner)

    def test_fresh_environment_drops_hostile_inherited_overrides(self) -> None:
        hostile = {
            "PYTHONPATH": "attacker",
            "UV_CONFIG_FILE": "attacker",
            "CARGO_HOME": "attacker",
            "RUSTC_WRAPPER": "attacker",
            "GIT_DIR": "attacker",
            "DYLD_INSERT_LIBRARIES": "attacker",
            "LD_PRELOAD": "attacker",
            "SSH_ASKPASS": "attacker",
        }
        (self.root / "python").mkdir()
        bootstrap.prepare_directories(self.root, acquisition=False)
        with patch.dict(os.environ, hostile, clear=False):
            environment = bootstrap.project_environment(
                self.root,
                python_path=self.root / "python",
                tool_directories=(Path("/tools"),),
                offline=True,
            )
        self.assertNotIn("attacker", environment.values())
        self.assertEqual(str(self.root / "python"), environment["PYTHONPATH"])
        self.assertEqual("1", environment["UV_OFFLINE"])
        self.assertEqual("true", environment["CARGO_NET_OFFLINE"])

    def test_project_python_directory_is_fixed_real_and_contained(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "python").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(BootstrapError):
            bootstrap.project_environment(
                self.root,
                python_path=self.root / "python",
                tool_directories=(Path("/tools"),),
                offline=True,
            )
        (self.root / "python").unlink()
        (self.root / "python").mkdir()
        with self.assertRaises(BootstrapError):
            bootstrap.project_environment(
                self.root,
                python_path=outside,
                tool_directories=(Path("/tools"),),
                offline=True,
            )

    def test_platform_marker_is_rejected_on_darwin_and_exact_on_linux(self) -> None:
        digest = "sha256:" + "a" * 64
        with self.assertRaises(BootstrapError):
            bootstrap.validate_platform_marker("Darwin", digest, digest)
        with self.assertRaises(BootstrapError):
            bootstrap.validate_platform_marker("Linux", "", digest)
        with self.assertRaises(BootstrapError):
            bootstrap.validate_platform_marker("Linux", digest.upper(), digest)
        self.assertEqual(digest, bootstrap.validate_platform_marker("Linux", digest, digest))

    def test_venv_requires_three_aliases_to_one_contained_managed_python(self) -> None:
        managed = self.root / "artifacts/uv-python/cpython/bin/python3.14"
        managed.parent.mkdir(parents=True)
        managed.write_bytes(b"python")
        managed.chmod(0o700)
        binary = self.root / ".venv/bin"
        binary.mkdir(parents=True)
        config = self.root / ".venv/pyvenv.cfg"
        config_text = (
            f"home = {managed.parent}\nimplementation = CPython\nuv = 0.11.29\n"
            "version_info = 3.14\ninclude-system-site-packages = false\n"
            "prompt = golden-board\n"
        )
        config.write_text(config_text, encoding="utf-8")
        (binary / "python").symlink_to(managed)
        (binary / "python3").symlink_to("python")
        (binary / "python3.14").symlink_to("python")
        runner = lambda argv, **kwargs: SimpleNamespace(returncode=0, stdout=b"Python 3.14.6\n", stderr=b"")
        self.assertEqual(managed, bootstrap.validate_venv(self.root, runner=runner))
        drifted_runner = lambda argv, **kwargs: SimpleNamespace(returncode=0, stdout=b"Python 3.14.7\n", stderr=b"")
        with self.assertRaises(BootstrapError):
            bootstrap.validate_venv(self.root, runner=drifted_runner)
        config.write_text(config_text.replace("version_info = 3.14\n", "version_info = 3.14.6\n"), encoding="utf-8")
        with self.assertRaises(BootstrapError):
            bootstrap.validate_venv(self.root, runner=runner)
        config.write_text(config_text, encoding="utf-8")
        (binary / "python3.14").unlink()
        (binary / "python3.14").symlink_to(Path("/usr/bin/python3"))
        with self.assertRaises(BootstrapError):
            bootstrap.validate_venv(self.root, runner=runner)

    def test_venv_resolves_real_uv_alias_chain_without_path_resolve(self) -> None:
        python_root = self.root / "artifacts/uv-python"
        managed = python_root / "cpython-3.14.6-macos-aarch64-none/bin/python3.14"
        managed.parent.mkdir(parents=True)
        managed.write_bytes(b"python")
        managed.chmod(0o700)
        current = python_root / "cpython-3.14-macos-aarch64-none"
        current.symlink_to(managed.parents[1])
        binary = self.root / ".venv/bin"
        binary.mkdir(parents=True)
        (self.root / ".venv/pyvenv.cfg").write_text(
            f"home = {current / 'bin'}\nimplementation = CPython\nuv = 0.11.29\n"
            "version_info = 3.14\ninclude-system-site-packages = false\n"
            "prompt = golden-board\n",
            encoding="utf-8",
        )
        (binary / "python").symlink_to(current / "bin/python3.14")
        (binary / "python3").symlink_to("python")
        (binary / "python3.14").symlink_to("python")
        real_resolve = Path.resolve

        def reject_data_path_resolve(path: Path, strict: bool = False) -> Path:
            if ".venv" in path.parts or path.is_relative_to(python_root):
                raise AssertionError("venv data path used Path.resolve")
            return real_resolve(path, strict=strict)

        runner = lambda argv, **kwargs: SimpleNamespace(
            returncode=0, stdout=b"Python 3.14.6\n", stderr=b""
        )
        with patch.object(Path, "resolve", new=reject_data_path_resolve):
            self.assertEqual(
                managed,
                bootstrap.validate_venv(self.root, runner=runner),
            )

    def test_venv_rejects_regular_bin_aliases_before_python_probe(self) -> None:
        managed_home = self.root / "artifacts/uv-python/cpython/bin"
        managed_home.mkdir(parents=True)
        binary = self.root / ".venv/bin"
        binary.mkdir(parents=True)
        (self.root / ".venv/pyvenv.cfg").write_text(
            f"home = {managed_home}\nimplementation = CPython\nuv = 0.11.29\n"
            "version_info = 3.14\ninclude-system-site-packages = false\n"
            "prompt = golden-board\n",
            encoding="utf-8",
        )
        for name in ("python", "python3", "python3.14"):
            (binary / name).write_bytes(b"regular alias")
            (binary / name).chmod(0o700)
        probed = False

        def runner(argv, **kwargs):
            nonlocal probed
            del argv, kwargs
            probed = True
            return SimpleNamespace(
                returncode=0, stdout=b"Python 3.14.6\n", stderr=b""
            )

        with self.assertRaises(BootstrapError):
            bootstrap.validate_venv(self.root, runner=runner)
        self.assertFalse(probed)

    def test_venv_rejects_linux_mount_identity_before_python_probe(self) -> None:
        managed = self.root / "artifacts/uv-python/cpython/bin/python3.14"
        managed.parent.mkdir(parents=True)
        managed.write_bytes(b"python")
        managed.chmod(0o700)
        binary = self.root / ".venv/bin"
        binary.mkdir(parents=True)
        (self.root / ".venv/pyvenv.cfg").write_text(
            f"home = {managed.parent}\nimplementation = CPython\nuv = 0.11.29\n"
            "version_info = 3.14\ninclude-system-site-packages = false\n"
            "prompt = golden-board\n",
            encoding="utf-8",
        )
        (binary / "python").symlink_to(managed)
        (binary / "python3").symlink_to("python")
        (binary / "python3.14").symlink_to("python")
        probed = False

        def runner(argv, **kwargs):
            nonlocal probed
            del argv, kwargs
            probed = True
            return SimpleNamespace(
                returncode=0, stdout=b"Python 3.14.6\n", stderr=b""
            )

        def mount_check(_repository, _descriptor, path: Path) -> bool:
            return path != managed

        with (
            patch.object(
                bootstrap,
                "same_held_mount",
                side_effect=mount_check,
            ) as checked,
            self.assertRaises(BootstrapError),
        ):
            bootstrap.validate_venv(self.root, runner=runner)
        checked.assert_called()
        self.assertFalse(probed)

    def test_acquisition_removes_only_real_venv_without_following_child_links(self) -> None:
        context = self._venv_removal_context()
        outside = self.root / "outside"
        outside.mkdir()
        marker = outside / "marker"
        marker.write_bytes(b"safe")
        venv = self.root / ".venv"
        venv.mkdir()
        (venv / "outside").symlink_to(outside, target_is_directory=True)
        bootstrap.remove_venv(self.root, **context)
        self.assertFalse(venv.exists())
        self.assertEqual(b"safe", marker.read_bytes())
        venv.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(BootstrapError):
            bootstrap.remove_venv(self.root, **context)

    def test_acquisition_refuses_a_venv_mount_point(self) -> None:
        context = self._venv_removal_context()
        (self.root / ".venv").mkdir()
        with (
            patch("golden_board.bootstrap.os.path.ismount", return_value=True),
            self.assertRaises(BootstrapError),
        ):
            bootstrap.remove_venv(self.root, **context)
        self.assertTrue((self.root / ".venv").is_dir())

    def test_exec_argv_uses_absolute_uv_and_verified_python_twice(self) -> None:
        uv = Path("/tools/uv")
        python = Path("/checkout/artifacts/uv-python/cpython/bin/python3.14")
        argv = bootstrap.project_argv(
            Path("/checkout"), uv, python, ("check", "fast")
        )
        self.assertEqual(str(uv), argv[0])
        self.assertIn("--offline", argv)
        self.assertIn("--frozen", argv)
        self.assertIn("--no-cache", argv)
        self.assertIn("-P", argv)
        self.assertIn("-B", argv)
        self.assertIn("-S", argv)
        self.assertEqual(2, argv.count(str(python)))
        self.assertEqual(("check", "fast"), tuple(argv[-2:]))

    def test_isolated_bootstrap_reaches_the_package_without_pythonpath(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                str(ROOT / "python/golden_board/bootstrap.py"),
            ],
            cwd=ROOT,
            env={"LANG": "C", "LC_ALL": "C", "PATH": str(Path(sys.executable).parent), "TZ": "UTC"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            close_fds=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(1, result.returncode)
        self.assertNotIn(b"ModuleNotFoundError", result.stderr)
        self.assertIn(b"invalid bootstrap invocation", result.stderr)

    def test_cargo_configuration_is_rejected_below_or_above_the_checkout(self) -> None:
        checkout = self.root / "checkout"
        checkout.mkdir()
        (checkout / ".cargo").mkdir()
        (checkout / ".cargo/config.toml").write_text("[build]\n", encoding="utf-8")
        with self.assertRaises(BootstrapError):
            bootstrap.validate_cargo_configuration(checkout)
        shutil.rmtree(checkout / ".cargo")
        (self.root / ".cargo").mkdir()
        (self.root / ".cargo/config").write_text("[build]\n", encoding="utf-8")
        with self.assertRaises(BootstrapError):
            bootstrap.validate_cargo_configuration(checkout)

    def test_cli_git_projection_is_exact_and_drops_the_bootstrap_key(self) -> None:
        git = self.root / "git"
        git.write_bytes(b"git")
        git.chmod(0o700)
        environment = {"GB_BOOTSTRAP_GIT": str(git), "GIT_DIR": "attacker"}
        runner = lambda argv, **kwargs: SimpleNamespace(
            returncode=0, stdout=b"git version 2.49.0\n", stderr=b""
        )
        executable, projected = cli._module_git_context(
            self.root, environment, runner=runner
        )
        self.assertEqual(git, executable)
        self.assertEqual(
            {
                "GIT_CONFIG_GLOBAL",
                "GIT_CONFIG_NOSYSTEM",
                "GIT_OPTIONAL_LOCKS",
                "GIT_TERMINAL_PROMPT",
                "HOME",
                "LANG",
                "LC_ALL",
                "PATH",
                "TMPDIR",
                "TZ",
            },
            set(projected),
        )
        self.assertNotIn("GB_BOOTSTRAP_GIT", projected)
        self.assertNotIn("GIT_DIR", projected)

    def test_cli_git_runtime_directories_reject_symlinks(self) -> None:
        git = self.root / "git"
        git.write_bytes(b"git")
        git.chmod(0o700)
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "artifacts").symlink_to(outside, target_is_directory=True)
        runner = lambda argv, **kwargs: SimpleNamespace(
            returncode=0, stdout=b"git version 2.49.0\n", stderr=b""
        )
        with self.assertRaises(ValueError):
            cli._module_git_context(
                self.root,
                {"GB_BOOTSTRAP_GIT": str(git)},
                runner=runner,
            )

    def test_cli_git_runtime_directories_reject_mounts_before_tool_probe(self) -> None:
        git = self.root / "git"
        git.write_bytes(b"git")
        git.chmod(0o700)
        runner = unittest.mock.Mock(side_effect=AssertionError("probe"))
        artifacts = self.root / "artifacts"

        def same_mount(_baseline, _descriptor, path: Path) -> bool:
            return path != artifacts

        with (
            patch.object(cli, "same_held_mount", side_effect=same_mount),
            self.assertRaises(ValueError),
        ):
            cli._module_git_context(
                self.root,
                {"GB_BOOTSTRAP_GIT": str(git)},
                runner=runner,
            )
        runner.assert_not_called()


class RegistryBoundaryTests(unittest.TestCase):
    def test_rust_child_is_absolute_fixed_argv_with_new_minimal_environment(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        binary = root / "artifacts/cargo-target/debug/gb-vector"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"binary")
        binary.chmod(0o700)
        captured: list[object] = []

        def fake(argv, raw, environment, **kwargs):
            captured.extend((argv, raw, environment, kwargs))
            return b"ok\t" + b"0" * 64 + b"\n", b""

        with patch.object(registry, "_run_bounded_process", side_effect=fake):
            registry._rust_result(root, binary, "identity-a-scalar", b"payload")
        self.assertEqual([str(binary), "identity-a-scalar"], captured[0])
        self.assertEqual({"LANG": "C", "LC_ALL": "C", "TZ": "UTC"}, captured[2])
        self.assertTrue(Path(captured[0][0]).is_absolute())


class StaticTestQualityTests(unittest.TestCase):
    def test_full_python_suite_includes_task12_mutation_tests(self) -> None:
        self.assertIn("tests.test_checks", checks._PYTHON_TESTS)

    def test_fast_rust_check_runs_units_instead_of_only_building(self) -> None:
        calls: list[list[str]] = []

        def command(argv, root, environment):
            del root, environment
            calls.append(argv)
            return []

        tools = {
            "cargo": Path("/tools/cargo"),
            "rustc": Path("/tools/rustc"),
            "rustfmt": Path("/tools/rustfmt"),
        }
        with (
            patch.object(checks, "_tool", side_effect=lambda name, prefix: tools[name]),
            patch.object(checks, "_child_environment", return_value={}),
            patch.object(checks, "_command", side_effect=command),
            patch.object(checks, "run_registered_vectors", return_value=[]),
        ):
            self.assertEqual(
                [],
                checks._cargo_and_vectors(
                    ROOT,
                    full=False,
                    families={"identity"},
                ),
            )
        cargo = next(argv for argv in calls if "--manifest-path" in argv)
        self.assertIn("test", cargo)
        self.assertIn("--lib", cargo)

    def test_task12_python_child_receives_the_validated_cargo_directory(self) -> None:
        captured: list[tuple[Path, ...]] = []

        def environment(root, tools):
            del root
            captured.append(tools)
            return {}

        with (
            patch.object(checks, "_tool", return_value=Path("/tools/cargo")),
            patch.object(checks, "_child_environment", side_effect=environment),
            patch.object(checks, "_command", return_value=[]),
        ):
            self.assertEqual(
                [],
                checks._python_tests(ROOT, ("tests.test_checks",)),
            )
        self.assertIn(Path("/tools/cargo"), captured[0])

    def test_cli_maps_unexpected_check_errors_to_status_one(self) -> None:
        with (
            patch.object(checks, "run_mode", side_effect=ValueError("injected")),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(1, cli.main(("check", "fast"), ROOT))


if __name__ == "__main__":
    unittest.main()
