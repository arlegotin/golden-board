from __future__ import annotations

from pathlib import Path
import os
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import io
import json
import sys
import tarfile
import unittest
from unittest.mock import Mock, patch

import golden_board.clean as clean
from golden_board.manifest import decode_canonical_manifest, encode_canonical_value
from golden_board.clean import (
    CleanError,
    write_native_evidence,
)
from golden_board.reports import (
    EXPECTED_NATIVE_COMMANDS,
    EXPECTED_NATIVE_ISOLATION,
    NATIVE_TOOL_KEYS,
)


def native_evidence(*, suffix: str = "") -> dict[str, object]:
    digest = "a" * 64
    return {
        "schema_version": 0,
        "protocol": "native-isolated-v0",
        "result": "pass",
        "roadmap_revision": 1,
        "tool_versions": {name: f"locked-{name}" for name in NATIVE_TOOL_KEYS},
        "isolation": EXPECTED_NATIVE_ISOLATION,
        "commands": EXPECTED_NATIVE_COMMANDS,
        "source_report_sha256": digest,
        "inputs": [{"path": f"AGENTS{suffix}.md", "sha256": digest}],
    }


class CleanInterfaceTests(unittest.TestCase):
    def test_writer_rejects_a_relative_repository(self) -> None:
        with self.assertRaisesRegex(CleanError, "repository root"):
            write_native_evidence(Path("."), {})

    def test_writer_rejects_non_native_evidence_before_creating_artifacts(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with self.assertRaises(CleanError):
                write_native_evidence(root, {})
            self.assertFalse((root / "artifacts").exists())

    def test_writer_atomically_replaces_only_the_fixed_canonical_handoff(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            first = native_evidence()
            second = native_evidence(suffix="-new")
            write_native_evidence(root, first)
            destination = root / "artifacts/native-verification.json"
            self.assertEqual(first, decode_canonical_manifest(destination.read_bytes()))
            self.assertEqual(encode_canonical_value(first), destination.read_bytes())

            write_native_evidence(root, second)

            self.assertEqual(
                second, decode_canonical_manifest(destination.read_bytes())
            )
            self.assertEqual([], list((root / "artifacts").glob(".*.tmp")))

    def test_writer_rejects_symlinked_artifacts_or_destination(self) -> None:
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            root = Path(directory).resolve()
            (root / "artifacts").symlink_to(Path(outside), target_is_directory=True)
            with self.assertRaises(CleanError):
                write_native_evidence(root, native_evidence())
            self.assertEqual([], list(Path(outside).iterdir()))

        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            root = Path(directory).resolve()
            (root / "artifacts").mkdir()
            external = Path(outside) / "evidence"
            external.write_text("untouched", encoding="ascii")
            (root / "artifacts/native-verification.json").symlink_to(external)
            with self.assertRaises(CleanError):
                write_native_evidence(root, native_evidence())
            self.assertEqual("untouched", external.read_text(encoding="ascii"))

    def test_writer_rejects_an_artifacts_mount_before_creating_a_temporary(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "artifacts").mkdir()
            with (
                patch("golden_board.clean.same_held_mount", return_value=False),
                self.assertRaises(CleanError),
            ):
                write_native_evidence(root, native_evidence())
            self.assertEqual([], list((root / "artifacts").iterdir()))

    def test_writer_restores_prior_bytes_when_post_replace_verification_fails(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            prior = native_evidence()
            replacement = native_evidence(suffix="-new")
            write_native_evidence(root, prior)
            read_exact = clean._read_exact
            calls = 0

            def fail_published(descriptor: int, expected: bytes) -> None:
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise CleanError("post-replace verification failed")
                read_exact(descriptor, expected)

            with (
                patch.object(clean, "_read_exact", side_effect=fail_published),
                self.assertRaises(CleanError),
            ):
                write_native_evidence(root, replacement)

            destination = root / "artifacts/native-verification.json"
            self.assertEqual(encode_canonical_value(prior), destination.read_bytes())
            self.assertEqual([], list((root / "artifacts").glob(".*.tmp")))
            self.assertEqual([], list((root / "artifacts").glob(".*.backup")))

    def test_writer_rejects_an_artifacts_directory_exchange_at_replace(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            real_replace = clean.os.replace

            def exchange_then_replace(*args: object, **kwargs: object) -> None:
                real_replace(*args, **kwargs)
                (root / "artifacts").rename(root / "moved-artifacts")
                (root / "artifacts").mkdir()

            with (
                patch.object(clean.os, "replace", side_effect=exchange_then_replace),
                self.assertRaises(CleanError),
            ):
                write_native_evidence(root, native_evidence())

            self.assertEqual([], list((root / "artifacts").iterdir()))
            self.assertFalse(
                (root / "moved-artifacts/native-verification.json").exists()
            )


class NativeProtocolTests(unittest.TestCase):
    def tools(self, root: Path):
        return SimpleNamespace(
            python=root / "tools/python3.14",
            uv=root / "tools/uv",
            cargo=root / "tools/cargo",
            cargo_fmt=root / "tools/cargo-fmt",
            rustdoc=root / "tools/rustdoc",
            rustc=root / "tools/rustc",
            rustfmt=root / "tools/rustfmt",
            git=root / "tools/git",
        )

    def test_semantic_tool_probe_adds_only_the_explicit_local_home(self) -> None:
        tool = Path("/tools/cargo")
        home = Path("/checkout/artifacts/check-home")
        observed: dict[str, object] = {}

        def probe_runner(argv, **kwargs):
            observed["argv"] = argv
            observed.update(kwargs)
            return SimpleNamespace(
                returncode=0,
                stdout=b"cargo 1.94.0 (Homebrew)\n",
                stderr=b"",
            )

        def validate(path, name, version, *, runner):
            runner(
                [str(path), "--version"],
                cwd=None,
                env={
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PATH": str(path.parent),
                    "TZ": "UTC",
                },
            )
            return path

        with (
            patch.object(clean, "_probe_runner", side_effect=probe_runner),
            patch(
                "golden_board.bootstrap.validate_semantic_tool",
                side_effect=validate,
            ),
        ):
            self.assertEqual(
                tool,
                clean._probe_semantic_tool(tool, "cargo", "1.94.0", home=home),
            )

        self.assertEqual([str(tool), "--version"], observed["argv"])
        self.assertIsNone(observed["cwd"])
        self.assertEqual(
            {
                "HOME": str(home),
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": str(tool.parent),
                "TZ": "UTC",
            },
            observed["env"],
        )

    def test_native_phase_environments_are_closed_and_checkout_local(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "checkout"
            tools = self.tools(root.parent)
            with patch.dict(
                clean.os.environ,
                {"CARGO_CACHE_AUTO_CLEAN_FREQUENCY": "always"},
                clear=True,
            ):
                acquisition = clean._native_environment(root, tools, offline=False)
                offline = clean._native_environment(root, tools, offline=True)

        common = {
            "CARGO_CACHE_AUTO_CLEAN_FREQUENCY": "never",
            "CARGO_HOME": str(root / "artifacts/cargo-home"),
            "CARGO_REGISTRIES_CRATES_IO_PROTOCOL": "sparse",
            "CARGO_TARGET_DIR": str(root / "artifacts/cargo-target"),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "HOME": str(root / "artifacts/check-home"),
            "LANG": "C",
            "LC_ALL": "C",
            "RUSTC": str(tools.rustc),
            "RUSTDOC": str(tools.rustdoc),
            "RUSTFMT": str(tools.rustfmt),
            "TMPDIR": str(root / "artifacts/check-tmp"),
            "TZ": "UTC",
            "UV_CACHE_DIR": str(root / "artifacts/uv-cache"),
            "UV_MANAGED_PYTHON": "true",
            "UV_NO_CONFIG": "1",
            "UV_PYTHON_INSTALL_DIR": str(root / "artifacts/uv-python"),
            "UV_PROJECT_ENVIRONMENT": ".venv",
            "CARGO_TARGET_AARCH64_APPLE_DARWIN_LINKER": "/usr/bin/cc",
            "CC": "/usr/bin/cc",
            "SDKROOT": str(clean.SDKROOT),
        }
        expected_path = ":".join(
            dict.fromkeys(
                str(path.parent)
                for path in (
                    tools.cargo,
                    tools.cargo_fmt,
                    tools.rustdoc,
                    tools.rustc,
                    tools.rustfmt,
                    tools.python,
                    tools.uv,
                    tools.git,
                    Path("/usr/bin/cc"),
                )
            )
        )
        self.assertEqual({**common, "PATH": expected_path}, acquisition)
        self.assertEqual(
            {
                **common,
                "PATH": expected_path,
                "CARGO_NET_OFFLINE": "true",
                "UV_OFFLINE": "1",
                "UV_PYTHON_DOWNLOADS": "never",
            },
            offline,
        )
        for hostile in (
            "PYTHONPATH",
            "RUSTC_WRAPPER",
            "CARGO_HOME_OVERRIDE",
            "HTTP_PROXY",
            "DYLD_INSERT_LIBRARIES",
        ):
            self.assertNotIn(hostile, acquisition)
            self.assertNotIn(hostile, offline)

    def test_explicit_git_is_never_resolved_from_path(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            git = root / "git"
            git.write_bytes(b"git")
            git.chmod(0o755)
            with (
                patch.object(
                    clean.shutil, "which", side_effect=AssertionError("PATH lookup")
                ),
                patch.object(clean, "_probe_exact_tool", return_value=git),
            ):
                self.assertEqual(git, clean._explicit_git(git))

    def test_explicit_git_allows_a_caller_supplied_symlink(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            real = root / "real-git"
            real.write_bytes(b"git")
            real.chmod(0o755)
            link = root / "git"
            link.symlink_to(real)
            with (
                patch.object(
                    clean,
                    "_probe_exact_tool",
                    return_value=link,
                ) as probe,
            ):
                self.assertEqual(link, clean._explicit_git(link))
        probe.assert_called_once()

    def test_native_tools_resolve_only_non_capabilities_from_the_sealed_path(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            names = ("python3.14", "uv", "cargo")
            candidates = {name: str(root / name) for name in names}
            calls: list[tuple[str, str | None]] = []
            semantic_calls: list[tuple[Path, str, str]] = []

            def which(name: str, *, path: str | None = None) -> str | None:
                calls.append((name, path))
                return candidates.get(name)

            def exact(path: Path, _argv: tuple[str, ...], _raw: bytes) -> Path:
                return path

            def semantic(path: Path, _name: str, _version: str) -> Path:
                semantic_calls.append((path, _name, _version))
                return path

            git = root / "explicit-git"
            git.write_bytes(b"git")
            git.chmod(0o755)
            with (
                patch.object(clean.shutil, "which", side_effect=which),
                patch.object(clean, "_probe_exact_tool", side_effect=exact),
                patch.object(clean, "_probe_semantic_tool", side_effect=semantic),
            ):
                tools = clean._resolve_native_tools(git, sealed_path="/sealed/bin")

        self.assertEqual([(name, "/sealed/bin") for name in names], calls)
        self.assertEqual(git, tools.git)
        self.assertEqual(Path(candidates["python3.14"]), tools.python)
        self.assertEqual(root / "cargo-fmt", tools.cargo_fmt)
        self.assertIn(
            (root / "cargo-fmt", "rustfmt", "1.8.0"),
            semantic_calls,
        )
        self.assertEqual(root / "rustdoc", tools.rustdoc)
        self.assertIn(
            (root / "rustdoc", "rustdoc", "1.94.0"),
            semantic_calls,
        )
        self.assertIn(
            (root / "rustc", "rustc", "1.94.0"),
            semantic_calls,
        )
        self.assertIn(
            (root / "rustfmt", "rustfmt", "1.8.0"),
            semantic_calls,
        )

    def test_sealed_path_rejects_relative_empty_or_control_entries(self) -> None:
        for value in ("relative", "/ok::/also", "/ok:\n/bad"):
            with self.subTest(value=value), self.assertRaises(CleanError):
                clean._validate_sealed_path(value)

    def test_sealed_path_normalizes_duplicate_entries(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            first = root / "first"
            second = root / "second"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            self.assertEqual(
                os.pathsep.join([str(first), str(second)]),
                clean._validate_sealed_path(
                    os.pathsep.join(
                        [str(first), str(first), str(second), str(second)]
                    )
                ),
            )

    def test_exact_head_clone_uses_closed_git_and_rechecks_both_trees(self) -> None:
        with TemporaryDirectory() as directory:
            temporary = Path(directory).resolve()
            source = temporary / "source"
            source.mkdir()
            (source / ".gitignore").write_text(".venv/\n", encoding="ascii")
            git = temporary / "git"
            git.write_bytes(b"git")
            git.chmod(0o755)
            checkout = temporary / "checkout"
            oid = b"1" * 40 + b"\n"
            calls: list[tuple[list[str], dict[str, str], Path]] = []

            def invoke(
                _tool: Path,
                argv: list[str],
                environment: dict[str, str],
                *,
                cwd: Path,
                **_kwargs: object,
            ) -> tuple[bytes, bytes]:
                calls.append((list(argv), dict(environment), cwd))
                if "clone" in argv:
                    checkout.mkdir()
                    return b"", b"" if "--quiet" in argv else b"clone progress\n"
                if "checkout" in argv:
                    (checkout / ".gitignore").write_text(".venv/\n", encoding="ascii")
                    return b"", b"" if "--quiet" in argv else b"checkout progress\n"
                if argv[-4:] == ["ls-files", "--error-unmatch", "--", ".gitignore"]:
                    return b".gitignore\n", b""
                if argv[-4:] == ["check-ignore", "-v", "--", ".venv/"]:
                    return b".gitignore:1:.venv/\t.venv/\n", b""
                if argv[-2:] == ["--verify", "HEAD^{commit}"]:
                    return oid, b""
                return b"", b""

            def prepare_checkout(root: Path) -> None:
                (root / "artifacts/check-home").mkdir(parents=True)
                (root / "artifacts/check-tmp").mkdir()

            with (
                patch.object(
                    clean,
                    "git_control_preflight",
                    side_effect=lambda root, **_kwargs: (str(git), f"ROOT={root.name}"),
                ) as preflight,
                patch.object(clean, "_invoke", side_effect=invoke),
                patch.object(
                    clean, "_prepare_checkout_directories", side_effect=prepare_checkout
                ),
            ):
                actual, captured_oid = clean._clone_exact_head(source, temporary, git)

        self.assertEqual(checkout, actual)
        self.assertEqual("1" * 40, captured_oid)
        self.assertEqual(13, preflight.call_count)
        clone = next(argv for argv, _, _ in calls if "clone" in argv)
        self.assertEqual(
            [
                str(git),
                "--no-pager",
                "--no-replace-objects",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.untrackedCache=false",
                "-c",
                "core.excludesFile=/dev/null",
                "-c",
                "core.attributesFile=/dev/null",
                "-c",
                "core.hooksPath=/dev/null",
                "clone",
                "--quiet",
                "--no-local",
                "--no-hardlinks",
                "--no-checkout",
                f"--template={temporary / 'git-template'}",
                "--",
                str(source),
                str(checkout),
            ],
            clone,
        )
        checkout_call = next(argv for argv, _, _ in calls if "checkout" in argv)
        self.assertEqual(
            ["checkout", "--quiet", "--detach", "--force", "1" * 40],
            checkout_call[-5:],
        )
        fixed = {
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": str(git.parent),
            "TZ": "UTC",
        }
        for _, environment, cwd in calls:
            local = cwd == checkout
            self.assertEqual(
                {
                    **fixed,
                    "HOME": str(
                        checkout / "artifacts/check-home"
                        if local
                        else temporary / "bootstrap-home"
                    ),
                    "TMPDIR": str(
                        checkout / "artifacts/check-tmp"
                        if local
                        else temporary / "bootstrap-tmp"
                    ),
                },
                environment,
            )

    def test_native_phases_publish_once_then_require_stable_offline_inventory(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "checkout"
            (root / "scripts").mkdir(parents=True)
            check = root / "scripts/check"
            check.write_text("#!/bin/sh\n", encoding="ascii")
            check.chmod(0o755)
            tools = self.tools(root.parent)
            managed_python = root / "artifacts/uv-python/cpython/bin/python3.14"
            inventory = {
                "schema_version": 0,
                "roots": [
                    "artifacts/cargo-home",
                    "artifacts/uv-cache",
                    "artifacts/uv-python",
                ],
                "files": [],
                "links": [],
            }
            calls: list[tuple[list[str], dict[str, str], Path]] = []

            def invoke(
                _tool: Path,
                argv: list[str],
                environment: dict[str, str],
                *,
                cwd: Path,
                **_kwargs: object,
            ) -> tuple[bytes, bytes]:
                calls.append((list(argv), dict(environment), cwd))
                if argv == [str(tools.cargo), "fmt", "--version"]:
                    return b"rustfmt 1.8.0\n", b""
                return b"", b""

            with (
                patch.object(clean, "_validate_runtime_roots") as validate_roots,
                patch.object(
                    clean, "_validate_cargo_target_root", create=True
                ) as validate_target,
                patch.object(clean, "_invoke", side_effect=invoke),
                patch.object(
                    clean, "_validate_fresh_venv", return_value=managed_python
                ) as venv,
                patch.object(clean, "_remove_disposable_outputs") as remove,
                patch.object(
                    clean, "build_inventory", side_effect=[inventory] * 4
                ) as build,
                patch.object(clean, "write_inventory") as write,
                patch.object(clean, "load_inventory", return_value=inventory) as load,
            ):
                actual = clean._run_native_phases(root, tools)

        self.assertEqual(managed_python, actual)
        self.assertEqual(2, venv.call_count)
        remove.assert_called_once_with(root, tools.git)
        self.assertEqual(4, build.call_count)
        write.assert_called_once_with(root, inventory)
        self.assertEqual(4, load.call_count)
        self.assertEqual(1, validate_roots.call_count)
        self.assertEqual(3, validate_target.call_count)
        self.assertEqual(
            [
                [str(tools.cargo), "fmt", "--version"],
                [str(tools.uv), "--no-config", "sync", "--project", ".", "--locked"],
                [
                    str(tools.cargo),
                    "fetch",
                    "--manifest-path",
                    "Cargo.toml",
                    "--locked",
                ],
                [
                    str(tools.cargo),
                    "build",
                    "--manifest-path",
                    "Cargo.toml",
                    "--workspace",
                    "--locked",
                ],
                [
                    str(tools.uv),
                    "--no-config",
                    "sync",
                    "--project",
                    ".",
                    "--offline",
                    "--locked",
                ],
                [
                    str(tools.cargo),
                    "build",
                    "--manifest-path",
                    "Cargo.toml",
                    "--workspace",
                    "--offline",
                    "--locked",
                ],
                [str(check), "full"],
                [str(check), "full"],
            ],
            [argv for argv, _, _ in calls],
        )
        acquisition = calls[1][1]
        offline = calls[4][1]
        self.assertNotIn("UV_OFFLINE", acquisition)
        self.assertEqual("1", offline["UV_OFFLINE"])
        self.assertEqual("never", offline["UV_PYTHON_DOWNLOADS"])
        self.assertEqual("true", offline["CARGO_NET_OFFLINE"])
        full_environments = [environment for _, environment, _ in calls[-2:]]
        self.assertEqual(full_environments[0], full_environments[1])
        self.assertEqual({"LANG", "LC_ALL", "PATH", "TZ"}, set(full_environments[0]))

    def test_native_inventory_drift_stops_before_full_check(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "checkout"
            (root / "scripts").mkdir(parents=True)
            check = root / "scripts/check"
            check.write_text("#!/bin/sh\n", encoding="ascii")
            check.chmod(0o755)
            tools = self.tools(root.parent)
            first = {"schema_version": 0, "roots": [], "files": [], "links": []}
            drifted = {
                "schema_version": 0,
                "roots": [],
                "files": [{"x": 1}],
                "links": [],
            }
            calls: list[list[str]] = []
            with (
                patch.object(clean, "_validate_runtime_roots"),
                patch.object(clean, "_probe_linux_cargo_fmt"),
                patch.object(clean, "_validate_cargo_target_root"),
                patch.object(
                    clean,
                    "_invoke",
                    side_effect=lambda _tool, argv, *_args, **_kwargs: (
                        calls.append(list(argv)) or b"",
                        b"",
                    ),
                ),
                patch.object(
                    clean, "_validate_fresh_venv", return_value=root / "python"
                ),
                patch.object(clean, "_remove_disposable_outputs"),
                patch.object(clean, "build_inventory", side_effect=[first, drifted]),
                patch.object(clean, "write_inventory"),
                patch.object(clean, "load_inventory", return_value=first),
                self.assertRaisesRegex(CleanError, "inventory"),
            ):
                clean._run_native_phases(root, tools)

        self.assertNotIn([str(check), "full"], calls)

    def test_published_inventory_tamper_stops_before_full_check(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "checkout"
            (root / "scripts").mkdir(parents=True)
            check = root / "scripts/check"
            check.write_text("#!/bin/sh\n", encoding="ascii")
            check.chmod(0o755)
            tools = self.tools(root.parent)
            inventory = {"schema_version": 0, "roots": [], "files": [], "links": []}
            calls: list[list[str]] = []
            with (
                patch.object(clean, "_validate_runtime_roots"),
                patch.object(clean, "_probe_linux_cargo_fmt"),
                patch.object(clean, "_validate_cargo_target_root", create=True),
                patch.object(
                    clean,
                    "_invoke",
                    side_effect=lambda _tool, argv, *_args, **_kwargs: (
                        calls.append(list(argv)) or b"",
                        b"",
                    ),
                ),
                patch.object(
                    clean, "_validate_fresh_venv", return_value=root / "python"
                ),
                patch.object(clean, "_remove_disposable_outputs"),
                patch.object(clean, "build_inventory", return_value=inventory),
                patch.object(clean, "write_inventory"),
                patch.object(clean, "load_inventory", side_effect=[inventory, {}]),
                self.assertRaisesRegex(CleanError, "inventory"),
            ):
                clean._run_native_phases(root, tools)

        self.assertNotIn([str(check), "full"], calls)

    def test_venv_ignore_proof_rejects_a_force_tracked_entry(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / ".gitignore").write_bytes(b".venv/\n")
            git = root / "git"
            environment = {"LANG": "C"}
            outputs = iter(
                (
                    (b".gitignore\n", b""),
                    (b".gitignore:1:.venv/\t.venv/\n", b""),
                    (b".venv/forced\0", b""),
                )
            )
            suffixes: list[list[str]] = []

            def operation(
                _root: Path,
                _git: Path,
                _environment: dict[str, str],
                suffix: list[str],
            ) -> tuple[bytes, bytes]:
                suffixes.append(list(suffix))
                return next(outputs)

            with (
                patch.object(clean, "_git_operation", side_effect=operation),
                self.assertRaisesRegex(CleanError, "ignore proof"),
            ):
                clean._prove_venv_ignore(root, git, environment)

        self.assertEqual(["ls-files", "-z", "--", ".venv"], suffixes[-1])

    def test_native_evidence_is_built_only_through_the_report_validator(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "reports").mkdir()
            source_raw = b'{"source":"report"}\n'
            (root / "reports/source-doctor.json").write_bytes(source_raw)
            tools = self.tools(root)
            toolchains = SimpleNamespace(
                cargo="1.94.0",
                cc="Apple clang 17",
                git="2.49.0",
                ld="ld-1167.5",
                python="3.14.6",
                rust="1.94.0",
                sdk="macOS SDK 15.5",
                uv="0.11.29",
            )
            lock = SimpleNamespace(toolchains=toolchains)
            inventory = [{"path": "AGENTS.md", "sha256": "b" * 64}]
            validated: list[dict[str, object]] = []

            def validate(
                _root: Path,
                value: dict[str, object],
                **_kwargs: object,
            ) -> dict[str, object]:
                validated.append(value)
                return value

            with (
                patch.object(clean, "_native_inventory", return_value=inventory),
                patch.object(clean, "validate_native_evidence", side_effect=validate),
            ):
                value = clean._build_native_evidence(root, lock, tools.git)

        self.assertEqual([value], validated)
        self.assertEqual("native-isolated-v0", value["protocol"])
        self.assertEqual(clean.EXPECTED_NATIVE_COMMANDS, value["commands"])
        self.assertEqual(clean.EXPECTED_NATIVE_ISOLATION, value["isolation"])
        self.assertEqual(inventory, value["inputs"])
        self.assertNotIn("commit", value)
        self.assertNotIn(str(root), repr(value))

    def test_native_public_verifier_rechecks_source_after_all_phases_and_cleans(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            temporary = root / "owned-temp"
            temporary.mkdir()
            checkout = temporary / "checkout"
            checkout.mkdir()
            tools = self.tools(root)
            git = tools.git
            evidence = native_evidence()
            events: list[str] = []
            with (
                patch.dict(clean.os.environ, {"PATH": "/sealed/bin"}, clear=True),
                patch.object(clean, "_resolve_native_tools", return_value=tools),
                patch.object(clean, "_new_temporary_root", return_value=temporary),
                patch.object(
                    clean,
                    "_clone_exact_head",
                    side_effect=lambda *_args: (checkout, "1" * 40),
                ),
                patch.object(clean, "load_source_lock", return_value=SimpleNamespace()),
                patch.object(
                    clean,
                    "_static_dependency_preflight",
                    side_effect=lambda *_args: events.append("dependencies"),
                ),
                patch.object(
                    clean,
                    "_probe_native_platform",
                    side_effect=lambda *_args: events.append("probe"),
                ),
                patch.object(
                    clean,
                    "_run_native_phases",
                    side_effect=lambda *_args: (
                        events.append("phases") or checkout / "python"
                    ),
                ),
                patch.object(
                    clean,
                    "_build_native_evidence",
                    side_effect=lambda *_args: events.append("evidence") or evidence,
                ),
                patch.object(
                    clean,
                    "_recheck_exact_head",
                    side_effect=lambda *_args: events.append("recheck"),
                ) as recheck,
                patch.object(
                    clean,
                    "_remove_temporary_root",
                    side_effect=lambda *_args: events.append("cleanup"),
                ) as cleanup,
            ):
                value = clean.verify_isolated_native(root, git_executable=git)

        self.assertEqual(evidence, value)
        self.assertEqual(
            ["dependencies", "probe", "phases", "evidence", "recheck", "cleanup"],
            events,
        )
        recheck.assert_called_once_with(root, checkout, temporary, tools.git, "1" * 40)
        cleanup.assert_called_once_with(temporary)

    def test_dependency_policy_stops_before_platform_or_acquisition(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            temporary = root / "owned-temp"
            temporary.mkdir()
            checkout = temporary / "checkout"
            checkout.mkdir()
            tools = self.tools(root)
            with (
                patch.dict(clean.os.environ, {"PATH": "/sealed/bin"}, clear=True),
                patch.object(clean, "_resolve_native_tools", return_value=tools),
                patch.object(clean, "_new_temporary_root", return_value=temporary),
                patch.object(
                    clean,
                    "_clone_exact_head",
                    return_value=(checkout, "1" * 40),
                ),
                patch.object(clean, "load_source_lock", return_value=SimpleNamespace()),
                patch.object(
                    clean,
                    "_static_dependency_preflight",
                    side_effect=CleanError("dependency policy rejected"),
                ),
                patch.object(clean, "_probe_native_platform") as probe,
                patch.object(clean, "_run_native_phases") as phases,
                patch.object(clean, "_remove_temporary_root"),
                self.assertRaisesRegex(CleanError, "dependency policy"),
            ):
                clean.verify_isolated_native(root, git_executable=tools.git)

        probe.assert_not_called()
        phases.assert_not_called()

    def test_dependency_preflight_checks_fresh_checkout_cargo_ancestors(self) -> None:
        with TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            checkout = parent / "nested/checkout"
            checkout.mkdir(parents=True)
            cargo = parent / ".cargo"
            cargo.mkdir()
            hostile = cargo / "config.toml"
            hostile.write_text("[build]\nrustc = '/hostile'\n", encoding="ascii")

            def validate(root: Path) -> None:
                self.assertEqual(checkout, root)
                if hostile.exists():
                    raise ValueError("ambient Cargo configuration is forbidden")

            fake_bootstrap = SimpleNamespace(validate_cargo_configuration=validate)
            fake_checks = SimpleNamespace(static_dependency_errors=lambda _root: [])
            with (
                patch.dict(
                    sys.modules,
                    {
                        "golden_board.bootstrap": fake_bootstrap,
                        "golden_board.checks": fake_checks,
                    },
                ),
                self.assertRaisesRegex(CleanError, "dependency policy audit"),
            ):
                clean._static_dependency_preflight(checkout)

    def test_runtime_cache_roots_reject_symlink_type_or_mount(self) -> None:
        for kind in ("symlink", "file", "special", "mount"):
            with self.subTest(kind=kind), TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                artifacts = root / "artifacts"
                artifacts.mkdir()
                for name in ("cargo-home", "cargo-target", "uv-cache", "uv-python"):
                    (artifacts / name).mkdir()
                target = artifacts / "uv-cache"
                target.rmdir()
                if kind == "symlink":
                    target.symlink_to(artifacts / "uv-python", target_is_directory=True)
                elif kind == "file":
                    target.write_bytes(b"not a directory")
                elif kind == "special":
                    target.mkdir()
                    clean.os.mkfifo(target / "hostile")
                else:
                    target.mkdir()
                context = (
                    patch.object(clean, "same_held_mount", return_value=False)
                    if kind == "mount"
                    else patch.object(
                        clean, "same_held_mount", wraps=clean.same_held_mount
                    )
                )
                with context, self.assertRaisesRegex(CleanError, "runtime root"):
                    clean._validate_runtime_roots(root)

    def test_final_recheck_brackets_status_with_the_same_source_oid(self) -> None:
        with TemporaryDirectory() as directory:
            temporary = Path(directory).resolve()
            source = temporary / "source"
            checkout = temporary / "checkout"
            source.mkdir()
            checkout.mkdir()
            git = temporary / "git"
            expected = b"1" * 40 + b"\n"
            roots: list[Path] = []
            outputs = iter(
                [
                    (expected, b""),
                    (b"", b""),
                    (b"2" * 40 + b"\n", b""),
                    (b"", b""),
                ]
            )

            def operation(root: Path, *_args: object, **_kwargs: object):
                roots.append(root)
                return next(outputs)

            with (
                patch.object(clean, "_prove_venv_ignore"),
                patch.object(clean, "_git_operation", side_effect=operation),
                self.assertRaisesRegex(CleanError, "exact HEAD"),
            ):
                clean._recheck_exact_head(source, checkout, temporary, git, "1" * 40)

        self.assertEqual([source, source, source], roots)

    def test_native_compiler_rejects_a_mutated_selected_linker_before_real_link(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "artifacts/check-home").mkdir(parents=True)
            (root / "artifacts/check-tmp").mkdir()
            tools = self.tools(root)
            lock = SimpleNamespace(
                toolchains=SimpleNamespace(
                    host="Darwin 25.5.0 arm64",
                    cc="Apple clang 17.0.0 (clang-1700.0.13.5) at /usr/bin/cc",
                    ld="ld-1167.5 selected by /usr/bin/cc",
                    sdk="macOS SDK 15.5 selected by /usr/bin/cc",
                )
            )
            trace = (
                '\n "/wrong/toolchain/usr/bin/ld" '
                '"-target-sdk-version=15.5" '
                '"-target-linker-version" "1167.5" '
                f'"-isysroot" "{clean.SDKROOT}" '
                f'"-syslibroot" "{clean.SDKROOT}" '
                '"-lSystem"'
            ).encode()
            outputs = iter(
                [
                    (
                        b"Apple clang version 17.0.0 (clang-1700.0.13.5)\n",
                        b"",
                    ),
                    (b"", trace),
                    (b"", b""),
                ]
            )
            calls: list[list[str]] = []

            def invoke(_tool: Path, argv: list[str], *_args: object, **_kwargs: object):
                calls.append(list(argv))
                return next(outputs)

            with (
                patch.object(
                    clean.os,
                    "uname",
                    return_value=SimpleNamespace(
                        sysname="Darwin", release="25.5.0", machine="arm64"
                    ),
                ),
                patch.object(clean, "_native_sdk", return_value=clean.SDKROOT),
                patch.object(clean, "_safe_executable", side_effect=lambda path: path),
                patch.object(clean, "_invoke", side_effect=invoke),
                self.assertRaisesRegex(CleanError, "compiler trace"),
            ):
                clean._probe_native_platform(root, tools, lock)

        self.assertEqual(2, len(calls))

    def test_native_compiler_accepts_valid_version_with_noisy_stderr(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "artifacts/check-home").mkdir(parents=True)
            (root / "artifacts/check-tmp").mkdir()
            tools = self.tools(root)
            lock = SimpleNamespace(
                toolchains=SimpleNamespace(
                    host="Darwin 25.5.0 arm64",
                    cc="Apple clang 17.0.0 (clang-1700.0.13.5) at /usr/bin/cc",
                    ld="ld-1167.5 selected by /usr/bin/cc",
                    sdk="macOS SDK 15.5 selected by /usr/bin/cc",
                )
            )
            linker = (
                '\n "/Applications/Xcode.app/Contents/Developer/Toolchains/'
                'XcodeDefault.xctoolchain/usr/bin/ld" '
                '"-target-sdk-version=15.5" '
                '"-target-linker-version" "1167.5" '
                f'"-isysroot" "{clean.SDKROOT}" '
                f'"-syslibroot" "{clean.SDKROOT}" '
                '"-lSystem"'
            )
            trace = (
                '\n "/Applications/Xcode.app/Contents/Developer/Toolchains/'
                'XcodeDefault.xctoolchain/usr/bin/clang" '
                '"-x" "c" "-" "-o" "/dev/null" '
                '"-fcolor-diagnostics" '
                f'"-isysroot" "{clean.SDKROOT}" '
                "-Xclang -fmessage-length=0 -fdiagnostics-show-note-include-stack "
                f'{linker}\n'
            ).encode()
            outputs = iter(
                [
                    (
                        b"Apple clang version 17.0.0 (clang-1700.0.13.5)\n",
                        b"some clang-warning: noisy but non-fatal\n",
                    ),
                    (b"", trace),
                    (b"", b""),
                ]
            )
            calls: list[list[str]] = []
            output_path = str(root / "artifacts/check-tmp/native-link-probe")

            def invoke(_tool: Path, argv: list[str], *_args: object, **_kwargs: object):
                calls.append(list(argv))
                if "-###" not in argv and argv[-1] == output_path:
                    artifact = Path(argv[-1])
                    artifact.write_bytes(b"\x7fELF")
                    artifact.chmod(0o755)
                return next(outputs)

            with (
                patch.object(
                    clean.os,
                    "uname",
                    return_value=SimpleNamespace(
                        sysname="Darwin", release="25.5.0", machine="arm64"
                    ),
                ),
                patch.object(clean, "_native_sdk", return_value=clean.SDKROOT),
                patch.object(clean, "_safe_executable", side_effect=lambda path: path),
                patch.object(clean, "_invoke", side_effect=invoke),
            ):
                clean._probe_native_platform(root, tools, lock)

        self.assertEqual(3, len(calls))

    def test_cargo_target_removal_rejects_symlink_file_or_mount_without_outside_damage(
        self,
    ) -> None:
        for kind in ("symlink", "file", "special", "mount"):
            with (
                self.subTest(kind=kind),
                TemporaryDirectory() as directory,
                TemporaryDirectory() as outside_directory,
            ):
                root = Path(directory).resolve()
                outside = Path(outside_directory).resolve()
                artifacts = root / "artifacts"
                artifacts.mkdir()
                target = artifacts / "cargo-target"
                sentinel = outside / "sentinel"
                sentinel.write_text("untouched", encoding="ascii")
                if kind == "symlink":
                    target.symlink_to(outside, target_is_directory=True)
                elif kind == "file":
                    target.write_bytes(b"not a target directory")
                elif kind == "special":
                    clean.os.mkfifo(target)
                else:
                    target.mkdir()
                context = (
                    patch.object(clean, "same_held_mount", return_value=False)
                    if kind == "mount"
                    else patch.object(
                        clean, "same_held_mount", wraps=clean.same_held_mount
                    )
                )
                with context, self.assertRaisesRegex(CleanError, "Cargo target"):
                    clean._remove_cargo_target(root)

                self.assertEqual("untouched", sentinel.read_text(encoding="ascii"))

    def test_acquisition_failure_stops_before_inventory_publication(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            tools = self.tools(root)
            with (
                patch.object(clean, "_validate_runtime_roots"),
                patch.object(
                    clean,
                    "_invoke",
                    side_effect=CleanError("isolated process failed"),
                ),
                patch.object(clean, "build_inventory") as build,
                patch.object(clean, "write_inventory") as write,
                self.assertRaisesRegex(CleanError, "process"),
            ):
                clean._run_native_phases(root, tools)
        build.assert_not_called()
        write.assert_not_called()

    def test_bounded_runner_timeout_or_output_failure_is_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            tool = root / "tool"
            tool.write_bytes(b"tool")
            tool.chmod(0o755)
            for code in ("registry.process_timeout", "registry.process_output"):
                with (
                    self.subTest(code=code),
                    patch.object(clean, "_run", side_effect=clean.RegistryError(code)),
                    self.assertRaisesRegex(CleanError, "process"),
                ):
                    clean._invoke(
                        tool,
                        [str(tool), "fixed"],
                        {"LANG": "C"},
                        cwd=root,
                    )

    def test_temporary_cleanup_rejects_special_entries_without_traversal(self) -> None:
        with TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            root = parent / "owned"
            root.mkdir()
            fifo = root / "hostile"
            clean.os.mkfifo(fifo)
            with self.assertRaisesRegex(CleanError, "special"):
                clean._remove_temporary_root(root)
            self.assertTrue(fifo.exists())


def linux_source_lock() -> SimpleNamespace:
    return SimpleNamespace(
        clean_linux=SimpleNamespace(
            mechanism="docker",
            image="docker.io/library/rust:1.94.0-bookworm",
            digest="sha256:365468470075493dc4583f47387001854321c5a8583ea9604b297e67f01c5a4f",
            platform_digest="sha256:94aaa0b45f4d185294474343d9034f829969f6c9ff8101f348b526d105860818",
            config_digest="sha256:4019a0c031b04dec0649a4e4af542125d94d2c9467e19ea6fd4d9e53510fd5e9",
            platform="linux/arm64/v8",
            uv_archive="https://github.com/astral-sh/uv/releases/download/0.11.29/uv-aarch64-unknown-linux-gnu.tar.gz",
            uv_archive_sha256="94500fb064ae3c971a873cba64d94694c50677e0a4dbf78735c80509e7429919",
            docker_client="25.0.3",
            observed_daemon_state="unavailable: fixed_socket_inaccessible",
            acquisition_protocol="docker-acquire-v0",
            offline_protocol="docker-offline-v0",
            mounts=("checkout", "uv-tool"),
            state="planned",
            blocker="fixed_socket_inaccessible",
            deadline="M2",
        )
    )


class LinuxProtocolTests(unittest.TestCase):
    _PYTHON_ALIAS = "cpython-3.14-linux-aarch64-gnu"
    _PYTHON_VERSION = "cpython-3.14.6-linux-aarch64-gnu"
    _PYTHON_CONTAINER_TARGET = (
        "/workspace/artifacts/uv-python/cpython-3.14.6-linux-aarch64-gnu"
    )
    _PYTHON_NORMALIZE_TEMPORARY = ".cpython-3.14-linux-aarch64-gnu.normalize.tmp"

    @classmethod
    def _python_alias_checkout(cls, root: Path) -> tuple[Path, Path]:
        (root / "Cargo.lock").write_text("version = 4\n", encoding="ascii")
        for relative in (
            "artifacts/cargo-home",
            "artifacts/uv-cache",
            "artifacts/uv-python",
        ):
            (root / relative).mkdir(parents=True, exist_ok=True)
        python_root = root / "artifacts/uv-python"
        (python_root / cls._PYTHON_VERSION).mkdir()
        alias = python_root / cls._PYTHON_ALIAS
        alias.symlink_to(cls._PYTHON_CONTAINER_TARGET)
        return python_root, alias

    @staticmethod
    def uv_tar(
        *,
        extra: tarfile.TarInfo | None = None,
        directory_size: int = 0,
    ) -> bytes:
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            directory = tarfile.TarInfo("uv-aarch64-unknown-linux-gnu/")
            directory.type = tarfile.DIRTYPE
            directory.mode = 0o755
            directory.size = directory_size
            archive.addfile(directory)
            for name, raw in (
                ("uv-aarch64-unknown-linux-gnu/uvx", b"uvx"),
                ("uv-aarch64-unknown-linux-gnu/uv", b"uv-binary"),
            ):
                member = tarfile.TarInfo(name)
                member.size = len(raw)
                member.mode = 0o755
                archive.addfile(member, io.BytesIO(raw))
            if extra is not None:
                archive.addfile(extra)
        return stream.getvalue()

    def test_linux_lock_protocol_is_exact_before_any_daemon_action(self) -> None:
        lock = linux_source_lock()
        for field, bad in (
            ("mechanism", "podman"),
            ("platform", "linux/amd64"),
            ("mounts", ("checkout", "uv-tool", "extra")),
            ("acquisition_protocol", "docker-acquire-v1"),
            ("offline_protocol", "docker-offline-v1"),
            ("docker_client", "latest"),
            ("state", "verified"),
            ("observed_daemon_state", "unavailable: anything"),
            ("blocker", "anything"),
        ):
            with self.subTest(field=field):
                changed = linux_source_lock()
                setattr(changed.clean_linux, field, bad)
                with self.assertRaisesRegex(CleanError, "clean-Linux lock"):
                    clean._validate_linux_lock(changed)
        self.assertIs(lock.clean_linux, clean._validate_linux_lock(lock))

        legacy = linux_source_lock()
        legacy.clean_linux.observed_daemon_state = (
            "unavailable: permission denied for fixed unix:///var/run/docker.sock"
        )
        legacy.clean_linux.blocker = "Fixed Docker daemon socket unix:///var/run/docker.sock is not accessible on the primary host"
        self.assertIs(legacy.clean_linux, clean._validate_linux_lock(legacy))

    def test_explicit_docker_allows_a_caller_supplied_symlink(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            real = root / "real-docker"
            real.write_bytes(b"docker")
            real.chmod(0o755)
            link = root / "docker"
            link.symlink_to(real)
            with (
                patch.object(
                    clean,
                    "_probe_docker_tool",
                    return_value=link,
                ) as probe,
            ):
                self.assertEqual(link, clean._explicit_docker(link))
        probe.assert_called_once()

    def test_docker_client_uses_only_fixed_endpoint_empty_config_and_closed_env(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            temporary = Path(directory).resolve()
            docker = temporary / "docker"
            docker.write_bytes(b"docker")
            docker.chmod(0o755)
            client = clean._prepare_docker_client(temporary, docker)
            config_entries = list((temporary / "docker-config").iterdir())
            modes = {
                name: clean.stat.S_IMODE((temporary / name).stat().st_mode)
                for name in ("docker-config", "docker-home", "docker-tmp")
            }

        self.assertEqual(
            (
                str(docker),
                "--config",
                str(temporary / "docker-config"),
                "--host",
                "unix:///var/run/docker.sock",
            ),
            client.prefix,
        )
        self.assertEqual(
            {
                "HOME": str(temporary / "docker-home"),
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": str(docker.parent),
                "TMPDIR": str(temporary / "docker-tmp"),
                "TZ": "UTC",
            },
            client.environment,
        )
        for hostile in (
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_CONFIG",
            "DOCKER_TLS_VERIFY",
            "HTTP_PROXY",
            "HOME_FROM_CALLER",
        ):
            self.assertNotIn(hostile, client.environment)
        self.assertEqual([], config_entries)
        self.assertEqual(
            {"docker-config": 0o500, "docker-home": 0o700, "docker-tmp": 0o700},
            modes,
        )

        with TemporaryDirectory() as directory:
            temporary = Path(directory).resolve()
            docker = temporary / "docker"
            docker.write_bytes(b"docker")
            docker.chmod(0o755)
            client = clean._prepare_docker_client(temporary, docker)
            (temporary / "docker-home/hostile").write_bytes(b"x")
            with self.assertRaisesRegex(CleanError, "client configuration"):
                clean._empty_docker_config(client)

    def test_daemon_probe_has_closed_planned_states_and_available_fact(self) -> None:
        client = SimpleNamespace(
            executable=Path("/tools/docker"),
            prefix=(
                "/tools/docker",
                "--config",
                "/tmp/config",
                "--host",
                "unix:///var/run/docker.sock",
            ),
            environment={"LANG": "C"},
            temporary=Path("/tmp"),
        )
        with (
            patch.object(clean, "_fixed_socket_available", return_value=False),
            patch.object(clean, "_docker_call") as call,
            self.assertRaises(clean._LinuxPrerequisite) as caught,
        ):
            clean._probe_docker_daemon(client)
        self.assertEqual("fixed_socket_inaccessible", caught.exception.blocker)
        call.assert_not_called()

        with (
            patch.object(clean, "_fixed_socket_available", return_value=True),
            patch.object(
                clean,
                "_docker_call",
                side_effect=clean.RegistryError("registry.process_exit:1"),
            ),
            self.assertRaises(clean._LinuxPrerequisite) as caught,
        ):
            clean._probe_docker_daemon(client)
        self.assertEqual("daemon_unreachable", caught.exception.blocker)

        for code in (
            "registry.process_timeout",
            "registry.process_output",
            "registry.process_start",
        ):
            with (
                self.subTest(code=code),
                patch.object(clean, "_fixed_socket_available", return_value=True),
                patch.object(
                    clean,
                    "_docker_call",
                    side_effect=clean.RegistryError(code),
                ),
                self.assertRaisesRegex(CleanError, "failed closed"),
            ):
                clean._probe_docker_daemon(client)

        with (
            patch.object(clean, "_fixed_socket_available", return_value=True),
            patch.object(
                clean,
                "_docker_call",
                return_value=(b"25.0.3\tlinux\taarch64\t6.10.14-linuxkit\n", b""),
            ) as call,
        ):
            observed = clean._probe_docker_daemon(client)
        self.assertEqual(
            "available: Docker Engine 25.0.3 linux/aarch64 kernel 6.10.14-linuxkit",
            observed,
        )
        self.assertEqual(
            [
                "info",
                "--format",
                "{{.ServerVersion}}\t{{.OSType}}\t{{.Architecture}}\t{{.KernelVersion}}",
            ],
            call.call_args.args[1],
        )

    def test_controller_permission_error_cannot_become_a_host_observation(self) -> None:
        with (
            patch.object(
                clean.Path,
                "stat",
                side_effect=PermissionError(clean.errno.EPERM, "sandbox"),
            ),
            self.assertRaisesRegex(CleanError, "controller-confined"),
        ):
            clean._fixed_socket_available()

        closed: list[bool] = []

        def denied(_path: str) -> None:
            raise PermissionError(clean.errno.EPERM, "controller")

        probe = SimpleNamespace(
            settimeout=lambda _seconds: None,
            connect=denied,
            close=lambda: closed.append(True),
        )
        with (
            patch.object(
                clean.Path,
                "stat",
                return_value=SimpleNamespace(st_mode=clean.stat.S_IFSOCK),
            ),
            patch.object(clean.socket, "socket", return_value=probe),
            self.assertRaisesRegex(CleanError, "controller-confined"),
        ):
            clean._fixed_socket_available()
        self.assertEqual([True], closed)

    def test_linux_public_verifier_stops_before_clone_on_daemon_prerequisite(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            temporary = root / "owned"
            temporary.mkdir()
            git = root / "git"
            docker = root / "docker"
            client = SimpleNamespace()
            events: list[str] = []
            with (
                patch.object(
                    clean,
                    "_validate_linux_lock",
                    side_effect=lambda lock: events.append("lock") or lock.clean_linux,
                ),
                patch.object(
                    clean,
                    "_explicit_git",
                    side_effect=lambda path: events.append("git") or path,
                ),
                patch.object(
                    clean,
                    "_explicit_docker",
                    side_effect=lambda path: events.append("docker") or path,
                ),
                patch.object(
                    clean,
                    "_new_temporary_root",
                    side_effect=lambda: events.append("temporary") or temporary,
                ),
                patch.object(clean, "_prepare_docker_client", return_value=client),
                patch.object(
                    clean,
                    "_probe_docker_daemon",
                    side_effect=lambda _client: (
                        events.append("daemon")
                        or (_ for _ in ()).throw(
                            clean._LinuxPrerequisite("daemon_unreachable")
                        )
                    ),
                ),
                patch.object(clean, "_clone_exact_head") as clone,
                patch.object(
                    clean,
                    "_remove_temporary_root",
                    side_effect=lambda _root: events.append("cleanup"),
                ),
            ):
                result = clean.verify_linux(
                    root,
                    linux_source_lock(),
                    git_executable=git,
                    docker_executable=docker,
                )

        self.assertEqual(
            {
                "schema_version": 0,
                "protocol": "docker-clean-linux-v0",
                "state": "planned",
                "observed_daemon_state": "unavailable: daemon_unreachable",
                "blocker": "daemon_unreachable",
                "deadline": "M2",
            },
            result,
        )
        self.assertEqual(
            ["lock", "git", "docker", "temporary", "daemon", "cleanup"], events
        )
        clone.assert_not_called()

    def test_linux_workspace_cleanup_failure_remains_hard(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            temporary = root / "owned"
            temporary.mkdir()
            git = root / "git"
            docker = root / "docker"
            with (
                patch.object(
                    clean,
                    "_validate_linux_lock",
                    side_effect=lambda value: value.clean_linux,
                ),
                patch.object(clean, "_explicit_git", return_value=git),
                patch.object(clean, "_explicit_docker", return_value=docker),
                patch.object(clean, "_new_temporary_root", return_value=temporary),
                patch.object(
                    clean, "_prepare_docker_client", return_value=SimpleNamespace()
                ),
                patch.object(
                    clean,
                    "_probe_docker_daemon",
                    side_effect=clean._LinuxPrerequisite("daemon_unreachable"),
                ),
                patch.object(
                    clean,
                    "_remove_temporary_root",
                    side_effect=CleanError("injected workspace cleanup failure"),
                ),
                self.assertRaisesRegex(CleanError, "workspace cleanup failure"),
            ):
                clean.verify_linux(
                    root,
                    linux_source_lock(),
                    git_executable=git,
                    docker_executable=docker,
                )

    def test_linux_public_verifier_runs_the_exact_checkout_protocol_and_rechecks_head(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            temporary = root / "owned"
            checkout = temporary / "checkout"
            checkout.mkdir(parents=True)
            git = root / "git"
            docker = root / "docker"
            source_lock = linux_source_lock()
            clean_lock = source_lock.clean_linux
            client = SimpleNamespace()
            acquisition = SimpleNamespace(uv_archive=b"archive")
            uv = SimpleNamespace()
            image = f"docker.io/library/rust@{clean_lock.platform_digest}"
            daemon = (
                "available: Docker Engine 25.0.3 linux/arm64 kernel 6.10.14-linuxkit"
            )
            events: list[str] = []
            with (
                patch.object(
                    clean,
                    "_validate_linux_lock",
                    side_effect=lambda value: (
                        events.append("lock"),
                        value.clean_linux,
                    )[1],
                ),
                patch.object(clean, "_explicit_git", return_value=git),
                patch.object(clean, "_explicit_docker", return_value=docker),
                patch.object(clean, "_new_temporary_root", return_value=temporary),
                patch.object(clean, "_prepare_docker_client", return_value=client),
                patch.object(clean, "_probe_docker_daemon", return_value=daemon),
                patch.object(
                    clean,
                    "_clone_exact_head",
                    side_effect=lambda *_args: (
                        events.append("clone"),
                        (checkout, "e" * 40),
                    )[1],
                ),
                patch.object(clean, "load_source_lock", return_value=source_lock),
                patch.object(
                    clean,
                    "_static_dependency_preflight",
                    side_effect=lambda *_args: events.append("static"),
                ),
                patch.object(
                    clean,
                    "_acquire_linux_inputs",
                    side_effect=lambda *_args: (
                        events.append("acquire"),
                        acquisition,
                    )[1],
                ),
                patch.object(
                    clean,
                    "_materialize_linux_uv",
                    side_effect=lambda *_args: (
                        events.append("uv"),
                        uv,
                    )[1],
                ),
                patch.object(clean, "_pull_linux_image", return_value=image),
                patch.object(clean, "_validate_local_linux_image"),
                patch.object(
                    clean,
                    "_run_linux_phases",
                    side_effect=lambda *_args: events.append("phases"),
                ) as phases,
                patch.object(
                    clean,
                    "_recheck_exact_head",
                    side_effect=lambda *_args: events.append("recheck"),
                ) as recheck,
                patch.object(clean, "_remove_temporary_root"),
            ):
                result = clean.verify_linux(
                    root,
                    source_lock,
                    git_executable=git,
                    docker_executable=docker,
                )

        self.assertEqual("verified", result["state"])
        self.assertEqual(daemon, result["observed_daemon_state"])
        self.assertEqual(
            ["lock", "clone", "lock", "static", "acquire", "uv", "phases", "recheck"],
            events,
        )
        phases.assert_called_once_with(client, checkout, uv, clean_lock, image, git)
        recheck.assert_called_once_with(root, checkout, temporary, git, "e" * 40)

    def test_linux_protocol_failure_discards_workspace_without_rechecking(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            temporary = root / "owned"
            checkout = temporary / "checkout"
            checkout.mkdir(parents=True)
            (checkout / "normalizer-residue").symlink_to("discarded")
            source_lock = linux_source_lock()
            clean_lock = source_lock.clean_linux
            git = root / "git"
            docker = root / "docker"
            client = SimpleNamespace()
            acquired = SimpleNamespace(uv_archive=b"archive")
            uv = SimpleNamespace()
            image = f"docker.io/library/rust@{clean_lock.platform_digest}"
            with (
                patch.object(
                    clean, "_validate_linux_lock", return_value=clean_lock
                ),
                patch.object(clean, "_explicit_git", return_value=git),
                patch.object(clean, "_explicit_docker", return_value=docker),
                patch.object(clean, "_new_temporary_root", return_value=temporary),
                patch.object(clean, "_prepare_docker_client", return_value=client),
                patch.object(
                    clean,
                    "_probe_docker_daemon",
                    return_value=(
                        "available: Docker Engine 25.0.3 linux/arm64 "
                        "kernel 6.10.14-linuxkit"
                    ),
                ),
                patch.object(
                    clean,
                    "_clone_exact_head",
                    return_value=(checkout, "e" * 40),
                ),
                patch.object(clean, "load_source_lock", return_value=source_lock),
                patch.object(clean, "_static_dependency_preflight"),
                patch.object(
                    clean, "_acquire_linux_inputs", return_value=acquired
                ),
                patch.object(clean, "_materialize_linux_uv", return_value=uv),
                patch.object(clean, "_pull_linux_image", return_value=image),
                patch.object(clean, "_validate_local_linux_image"),
                patch.object(
                    clean,
                    "_run_linux_phases",
                    side_effect=CleanError("alias normalization failed"),
                ),
                patch.object(clean, "_recheck_exact_head") as recheck,
                self.assertRaisesRegex(CleanError, "alias normalization failed"),
            ):
                clean.verify_linux(
                    root,
                    source_lock,
                    git_executable=git,
                    docker_executable=docker,
                )

        self.assertFalse(temporary.exists() or temporary.is_symlink())
        recheck.assert_not_called()

    def test_linux_post_clone_planned_result_rechecks_head_before_returning(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            temporary = root / "owned"
            checkout = temporary / "checkout"
            checkout.mkdir(parents=True)
            source_lock = linux_source_lock()
            git = root / "git"
            docker = root / "docker"
            daemon = (
                "available: Docker Engine 25.0.3 linux/arm64 kernel 6.10.14-linuxkit"
            )
            events: list[str] = []
            with (
                patch.object(
                    clean,
                    "_validate_linux_lock",
                    side_effect=lambda value: value.clean_linux,
                ),
                patch.object(clean, "_explicit_git", return_value=git),
                patch.object(clean, "_explicit_docker", return_value=docker),
                patch.object(clean, "_new_temporary_root", return_value=temporary),
                patch.object(
                    clean, "_prepare_docker_client", return_value=SimpleNamespace()
                ),
                patch.object(clean, "_probe_docker_daemon", return_value=daemon),
                patch.object(
                    clean, "_clone_exact_head", return_value=(checkout, "f" * 40)
                ),
                patch.object(clean, "load_source_lock", return_value=source_lock),
                patch.object(clean, "_static_dependency_preflight"),
                patch.object(
                    clean,
                    "_acquire_linux_inputs",
                    side_effect=clean._LinuxPrerequisite(
                        "network_acquisition_unavailable"
                    ),
                ),
                patch.object(
                    clean,
                    "_recheck_exact_head",
                    side_effect=lambda *_args: events.append("recheck"),
                ) as recheck,
                patch.object(
                    clean,
                    "_remove_temporary_root",
                    side_effect=lambda *_args: events.append("cleanup"),
                ),
            ):
                result = clean.verify_linux(
                    root,
                    source_lock,
                    git_executable=git,
                    docker_executable=docker,
                )

        self.assertEqual("planned", result["state"])
        self.assertEqual("network_acquisition_unavailable", result["blocker"])
        self.assertEqual(["recheck", "cleanup"], events)
        recheck.assert_called_once_with(root, checkout, temporary, git, "f" * 40)

    def test_oci_chain_selects_exact_platform_config_and_uv_archive(self) -> None:
        from golden_board import reference_acquisition as reference

        clean_lock = clean._validate_linux_lock(linux_source_lock())
        index = json.dumps(
            {
                "manifests": [
                    {
                        "mediaType": reference.OCI_MANIFEST,
                        "digest": clean_lock.platform_digest,
                        "size": reference.RUST_PLATFORM.byte_length,
                        "platform": {
                            "os": "linux",
                            "architecture": "arm64",
                            "variant": "v8",
                        },
                    }
                ]
            },
            separators=(",", ":"),
        ).encode()
        manifest = json.dumps(
            {
                "config": {
                    "mediaType": reference.OCI_CONFIG,
                    "digest": clean_lock.config_digest,
                    "size": reference.RUST_CONFIG.byte_length,
                }
            },
            separators=(",", ":"),
        ).encode()
        config = json.dumps(
            {
                "architecture": "arm64",
                "os": "linux",
                "config": {
                    "Env": list(reference.IMAGE_ENV),
                    "Entrypoint": None,
                    "Cmd": ["bash"],
                },
            },
            separators=(",", ":"),
        ).encode()
        uv = b"validated-uv-archive"
        responses = iter((b'{"token":"abc.DEF_123"}', index, manifest, config, uv))
        calls: list[tuple[str, str, int, str | None]] = []

        def get(
            url: str,
            accept: str,
            maximum: int,
            authorization: str | None = None,
        ) -> bytes:
            calls.append((url, accept, maximum, authorization))
            return next(responses)

        with (
            patch.object(reference, "_get", side_effect=get),
            patch.object(reference, "verify_bytes") as verify,
        ):
            acquired = clean._acquire_linux_inputs(clean_lock)

        self.assertEqual(
            (index, manifest, config, uv),
            (
                acquired.index,
                acquired.manifest,
                acquired.config,
                acquired.uv_archive,
            ),
        )
        self.assertEqual(4, verify.call_count)
        self.assertIsNone(calls[0][3])
        self.assertTrue(all(call[3] == "Bearer abc.DEF_123" for call in calls[1:4]))
        self.assertIsNone(calls[4][3])

    def test_oci_network_unavailability_is_planned_but_byte_or_chain_mismatch_is_hard(
        self,
    ) -> None:
        from golden_board import reference_acquisition as reference

        clean_lock = clean._validate_linux_lock(linux_source_lock())
        with (
            patch.object(
                reference,
                "_get",
                side_effect=reference.AcquisitionError(
                    f"network: {reference.TOKEN_URL}"
                ),
            ),
            self.assertRaises(clean._LinuxPrerequisite) as caught,
        ):
            clean._acquire_linux_inputs(clean_lock)
        self.assertEqual("network_acquisition_unavailable", caught.exception.blocker)

        for detail in (
            "network response exceeds 1 bytes: https://invalid",
            "network deadline capability is unavailable",
            "network deadline cleanup failed",
        ):
            with (
                self.subTest(detail=detail),
                patch.object(
                    reference,
                    "_get",
                    side_effect=reference.AcquisitionError(detail),
                ),
                self.assertRaisesRegex(CleanError, "adapter failed closed"),
            ):
                clean._acquire_linux_inputs(clean_lock)

        with (
            patch.object(
                reference,
                "_get",
                side_effect=[b'{"token":"abc"}', b"mutated-index"],
            ),
            self.assertRaisesRegex(CleanError, "immutable acquisition bytes"),
        ):
            clean._acquire_linux_inputs(clean_lock)

    def test_uv_archive_extracts_only_the_exact_regular_uv_member(self) -> None:
        self.assertEqual(b"uv-binary", clean._extract_linux_uv(self.uv_tar()))

        traversal = tarfile.TarInfo("../outside")
        traversal.size = 0
        symlink = tarfile.TarInfo("extra-link")
        symlink.type = tarfile.SYMTYPE
        symlink.linkname = "/outside"
        for member in (traversal, symlink):
            with (
                self.subTest(member=member.name),
                self.assertRaisesRegex(CleanError, "uv archive"),
            ):
                clean._extract_linux_uv(self.uv_tar(extra=member))
        with self.assertRaisesRegex(CleanError, "uv archive"):
            clean._extract_linux_uv(self.uv_tar(directory_size=64 * 1024 * 1024))

    def test_uv_tool_materialization_is_one_real_read_only_executable(self) -> None:
        with TemporaryDirectory() as directory:
            temporary = Path(directory).resolve()
            with patch.object(clean, "_extract_linux_uv", return_value=b"uv-binary"):
                tool = clean._materialize_linux_uv(temporary, b"archive")
            self.assertEqual(temporary / "uv-tool/uv", tool.path)
            self.assertEqual(b"uv-binary", tool.path.read_bytes())
            self.assertEqual(0o555, tool.path.stat().st_mode & 0o777)
            self.assertEqual([tool.path], list((temporary / "uv-tool").iterdir()))
            self.assertEqual(tool.path, clean._validate_linux_uv_tool(temporary, tool))

            replacement = temporary / "uv-tool/replacement"
            replacement.write_bytes(b"uv-binary")
            replacement.chmod(0o555)
            replacement.replace(tool.path)
            with self.assertRaisesRegex(CleanError, "capability changed"):
                clean._validate_linux_uv_tool(temporary, tool)

    def test_image_pull_uses_only_platform_digest_and_closed_failure_classification(
        self,
    ) -> None:
        clean_lock = clean._validate_linux_lock(linux_source_lock())
        image = f"docker.io/library/rust@{clean_lock.platform_digest}"
        client = SimpleNamespace()
        with patch.object(
            clean, "_docker_call", return_value=(b"pull progress\n", b"")
        ) as call:
            self.assertEqual(image, clean._pull_linux_image(client, clean_lock))
        self.assertEqual(
            ["pull", "--platform", "linux/arm64/v8", image],
            call.call_args.args[1],
        )
        self.assertNotIn(clean_lock.image, call.call_args.args[1])
        self.assertNotIn(clean_lock.digest, call.call_args.args[1])

        for code in (
            "registry.process_exit:1",
            "registry.process_timeout",
            "registry.process_output",
        ):
            with (
                self.subTest(code=code),
                patch.object(
                    clean,
                    "_docker_call",
                    side_effect=clean.RegistryError(code),
                ),
                self.assertRaisesRegex(CleanError, "pull failed closed"),
            ):
                clean._pull_linux_image(client, clean_lock)

    def test_local_image_inspect_requires_config_digest_platform_and_closed_env(
        self,
    ) -> None:
        from golden_board import reference_acquisition as reference

        clean_lock = clean._validate_linux_lock(linux_source_lock())
        image = f"docker.io/library/rust@{clean_lock.platform_digest}"
        document = [
            {
                "Id": clean_lock.config_digest,
                "Architecture": "arm64",
                "Os": "linux",
                "Config": {
                    "Env": list(reference.IMAGE_ENV),
                    "Entrypoint": None,
                    "Cmd": ["bash"],
                },
            }
        ]
        client = SimpleNamespace()
        with patch.object(
            clean,
            "_docker_call",
            return_value=(json.dumps(document).encode() + b"\n", b""),
        ) as call:
            clean._validate_local_linux_image(client, clean_lock, image)
        self.assertEqual(["image", "inspect", image], call.call_args.args[1])

        document[0]["Config"]["Env"].append("HOSTILE=1")
        with (
            patch.object(
                clean,
                "_docker_call",
                return_value=(json.dumps(document).encode() + b"\n", b""),
            ),
            self.assertRaisesRegex(CleanError, "local immutable image"),
        ):
            clean._validate_local_linux_image(client, clean_lock, image)

    def test_every_container_argv_has_exactly_two_mounts_digest_env_i_and_pull_never(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            temporary = Path(directory).resolve()
            checkout = temporary / "checkout"
            checkout.mkdir()
            with patch.object(clean, "_extract_linux_uv", return_value=b"uv-binary"):
                tool = clean._materialize_linux_uv(temporary, b"archive")
            clean_lock = clean._validate_linux_lock(linux_source_lock())
            image = f"docker.io/library/rust@{clean_lock.platform_digest}"
            by_phase: dict[str, list[str]] = {}
            for phase in ("probe", "acquire", "offline"):
                name = f"golden-board-m0-{phase}-0123456789abcdef"
                cidfile = temporary / f"container-{phase}.cid"
                by_phase[phase] = clean._linux_container_argv(
                    temporary,
                    checkout,
                    tool,
                    clean_lock,
                    image,
                    phase=phase,
                    name=name,
                    cidfile=cidfile,
                )

        for phase, argv in by_phase.items():
            self.assertEqual("run", argv[0])
            self.assertEqual(2, argv.count("--mount"))
            mounts = [
                argv[index + 1] for index, item in enumerate(argv) if item == "--mount"
            ]
            self.assertEqual(
                [
                    f"type=bind,src={checkout},dst=/workspace",
                    f"type=bind,src={tool.path},dst=/opt/golden-board/uv,readonly",
                ],
                mounts,
            )
            self.assertIn("--pull=never", argv)
            self.assertEqual("linux/arm64/v8", argv[argv.index("--platform") + 1])
            image_index = argv.index(image)
            self.assertEqual(
                ["/usr/bin/env", "-i"], argv[image_index + 1 : image_index + 3]
            )
            self.assertEqual(["/bin/sh", "-p", "-c"], argv[-4:-1])
            assignments = argv[image_index + 3 : -4]
            self.assertIn("GIT_NO_LAZY_FETCH=1", assignments)
            self.assertIn(
                "CARGO_REGISTRIES_CRATES_IO_PROTOCOL=sparse",
                assignments,
            )
            self.assertIn("CC=/usr/bin/cc", assignments)
            self.assertIn("COMPILER_PATH=/usr/bin", assignments)
            self.assertIn(
                "CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=/usr/bin/cc",
                assignments,
            )
            local_rust = (
                "/workspace/artifacts/cargo-home/rustup/toolchains/"
                "1.94.0-aarch64-unknown-linux-gnu/bin"
            )
            self.assertIn(
                f"PATH=/workspace/.venv/bin:/opt/golden-board:{local_rust}",
                assignments,
            )
            self.assertIn(f"RUSTC={local_rust}/rustc", assignments)
            self.assertIn(f"RUSTDOC={local_rust}/rustdoc", assignments)
            self.assertIn(f"RUSTFMT={local_rust}/rustfmt", assignments)
            self.assertIn(
                "RUSTUP_HOME=/workspace/artifacts/cargo-home/rustup",
                assignments,
            )
            self.assertNotIn("/usr/local/cargo/bin", "\n".join(assignments))
            self.assertNotIn("/usr/local/rustup", "\n".join(assignments))
            self.assertNotIn("HTTP_PROXY", "\n".join(assignments))
            marker = f"GB_CLEAN_LINUX_DIGEST={clean_lock.platform_digest}"
            self.assertEqual(phase == "offline", marker in assignments)
            self.assertEqual(phase != "acquire", "--network" in argv)
            self.assertIn("--user", argv)
            self.assertRegex(argv[argv.index("--user") + 1], r"[0-9]+:[0-9]+\Z")
            if "--network" in argv:
                self.assertEqual("none", argv[argv.index("--network") + 1])

    def test_container_builder_revalidates_uv_identity_before_each_mount(self) -> None:
        with TemporaryDirectory() as directory:
            temporary = Path(directory).resolve()
            checkout = temporary / "checkout"
            checkout.mkdir()
            with patch.object(clean, "_extract_linux_uv", return_value=b"uv-binary"):
                tool = clean._materialize_linux_uv(temporary, b"archive")
            replacement = temporary / "uv-tool/replacement"
            replacement.write_bytes(b"uv-binary")
            replacement.chmod(0o555)
            replacement.replace(tool.path)
            clean_lock = clean._validate_linux_lock(linux_source_lock())
            with self.assertRaisesRegex(CleanError, "capability changed"):
                clean._linux_container_argv(
                    temporary,
                    checkout,
                    tool,
                    clean_lock,
                    f"docker.io/library/rust@{clean_lock.platform_digest}",
                    phase="probe",
                    name="golden-board-m0-probe-0123456789abcdef",
                    cidfile=temporary / "probe.cid",
                )

    def test_linux_probe_output_and_script_close_image_owned_facts_and_real_link(
        self,
    ) -> None:
        probe = (
            b"linux-image-probe-v0\n"
            b"uv 0.11.29 (aarch64-unknown-linux-gnu)\n"
            b"rustup 1.29.0 (28d1352db 2026-03-05)\n"
            b"git version 2.39.5\n"
            b"12.2.0\n"
            b"GNU ld (GNU Binutils for Debian) 2.40\n"
            b"ldd (Debian GLIBC 2.36-9+deb12u13) 2.36\n"
            b"aarch64\n"
            b"shell-ok\n"
        )
        clean._validate_linux_probe_output(probe, b"")
        for mutation in (
            probe.replace(b"rustup 1.29.0", b"rustup 1.28.2"),
            probe.replace(b"28d1352db", b"28d1352d"),
            probe.replace(b"2026-03-05", b"2026/03/05"),
            probe.replace(b"git version 2.39.5", b"git hostile"),
            probe.replace(b"git version 2.39.5", b"git version 1.39.5"),
            probe.replace(b"git version 2.39.5", b"git version 3.0.0"),
            probe.replace(b"git version 2.39.5", b"git version 2.1234.5"),
            probe.replace(b"12.2.0", b"13.2.0"),
            probe.replace(
                b"GNU Binutils for Debian) 2.40", b"GNU Binutils for Debian) 2.41"
            ),
            probe.replace(b"GLIBC 2.36-9+deb12u13", b"GLIBC 2.37-9+deb12u13"),
            probe.replace(b"aarch64", b"x86_64"),
            probe.replace(b"uv 0.11.29", b"uv 0.11.30"),
            probe.replace(b"aarch64-unknown-linux-gnu", b"x86_64-unknown-linux-gnu"),
            probe + b"extra\n",
            probe[:-1],
            probe.replace(b"\n", b"\r\n", 1),
        ):
            with (
                self.subTest(mutation=mutation[-40:]),
                self.assertRaisesRegex(CleanError, "image probe"),
            ):
                clean._validate_linux_probe_output(mutation, b"")
        for required in (
            "rustup=$(cd / &&",
            "RUSTUP_HOME=/usr/local/rustup",
            "/usr/local/cargo/bin/rustup --version 2>/dev/null",
            "/usr/bin/cc -###",
            'test "$driver" = /usr/bin/aarch64-linux-gnu-ld',
            "collect2",
            "ld-linux-aarch64.so.1",
            "/usr/bin/cc -Wl,-t",
            "libc.so",
            "/usr/bin/readelf -l",
            '"$probe"',
            "/usr/bin/rm -f",
        ):
            self.assertIn(required, clean._LINUX_PROBE_SCRIPT)
        for forbidden in (
            "/usr/local/cargo/bin/cargo",
            "/usr/local/cargo/bin/rustc",
            "/usr/local/cargo/bin/rustfmt",
            "/usr/local/rustup/toolchains",
        ):
            self.assertNotIn(forbidden, clean._LINUX_PROBE_SCRIPT)

    def test_linux_acquisition_installs_and_seals_project_local_rust_before_resolution(
        self,
    ) -> None:
        script = clean._LINUX_ACQUIRE_SCRIPT
        local_root = (
            "/workspace/artifacts/cargo-home/rustup/toolchains/"
            "1.94.0-aarch64-unknown-linux-gnu"
        )
        install = (
            "/usr/local/cargo/bin/rustup toolchain install "
            "1.94.0-aarch64-unknown-linux-gnu --profile minimal "
            "--component rustfmt --no-self-update"
        )
        self.assertEqual(1, script.count("/usr/local/cargo/bin/rustup"))
        self.assertIn(install, script)
        validator = "_validate_linux_rust_toolchain"
        self.assertIn(validator, script)
        for proof in (
            "sys.version_info[:3] == (3, 14, 6)",
            "Path(sys.executable) == executable",
            "Path(sys.prefix) == prefix == Path(sys.base_prefix)",
            "prefix.resolve(strict=True) == prefix",
            "executable.resolve(strict=True).is_relative_to(prefix)",
        ):
            self.assertIn(proof, script)
            self.assertLess(script.index(proof), script.index(validator))
        self.assertLess(script.index(install), script.index("uv python install"))
        self.assertLess(script.index("uv python install"), script.index(validator))
        self.assertLess(script.index(validator), script.index("uv --no-config sync"))
        self.assertLess(
            script.index(validator), script.index('"$local/bin/cargo" fetch')
        )
        self.assertIn('"$local/bin/cargo" fetch', script)
        self.assertIn('"$local/bin/cargo" build', script)
        self.assertIn("validate_venv", script)
        self.assertNotIn("build_inventory", script)
        self.assertNotIn("write_inventory", script)
        self.assertNotIn("load_inventory", script)
        for command in ("ln", "mv", "readlink"):
            self.assertNotIn(f"\n{command} ", script)
            self.assertNotIn(f"/usr/bin/{command}", script)
        self.assertNotIn("cargo_version=", script)
        self.assertNotIn('case "$cargo_version"', script)
        self.assertNotIn("/usr/local/rustup", script)

        offline = clean._LINUX_OFFLINE_SCRIPT
        self.assertIn("_validate_linux_rust_toolchain", offline)
        self.assertIn("sys.version_info[:3] == (3, 14, 6)", offline)
        self.assertLess(
            offline.index("rust_tools\n/opt/golden-board/uv"),
            offline.index("uv --no-config sync"),
        )
        self.assertIn("python3.14\nrust_tools\n", offline)
        self.assertIn("rust_tools\nfull\ninventory\nrust_tools\nfull", offline)
        self.assertIn(f'"{local_root}/bin/cargo" build', offline)
        self.assertIn(f"/opt/golden-board:{local_root}/bin:/usr/bin:/bin", offline)
        self.assertIn(f"RUSTC={local_root}/bin/rustc", offline)
        self.assertIn(f"RUSTDOC={local_root}/bin/rustdoc", offline)
        self.assertNotIn("/usr/local/cargo/bin", offline)
        self.assertNotIn("/usr/local/rustup", offline)

    def test_project_local_rust_tools_are_descriptor_contained_before_version_probes(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            binary = (
                root / "artifacts/cargo-home/rustup/toolchains/"
                "1.94.0-aarch64-unknown-linux-gnu/bin"
            )
            binary.mkdir(parents=True)
            for name in ("cargo", "rustc", "rustdoc", "rustfmt", "cargo-fmt"):
                path = binary / name
                path.write_bytes(b"tool")
                path.chmod(0o555)
            with (
                patch.object(
                    clean,
                    "_probe_semantic_tool",
                    side_effect=lambda path, _name, _version, **_kwargs: path,
                ) as probe,
                patch.object(clean, "_probe_linux_cargo_fmt") as cargo_fmt,
            ):
                clean._validate_linux_rust_toolchain(root)

            self.assertEqual(
                [
                    (binary / "cargo", "cargo", "1.94.0"),
                    (binary / "rustc", "rustc", "1.94.0"),
                    (binary / "rustdoc", "rustdoc", "1.94.0"),
                    (binary / "rustfmt", "rustfmt", "1.8.0"),
                    (binary / "cargo-fmt", "rustfmt", "1.8.0"),
                ],
                [call.args for call in probe.call_args_list],
            )
            self.assertTrue(
                all(
                    call.kwargs == {"home": root / "artifacts/check-home"}
                    for call in probe.call_args_list
                )
            )
            cargo_fmt.assert_called_once_with(
                root,
                binary / "cargo",
                binary / "cargo-fmt",
                binary / "rustc",
                binary / "rustdoc",
                binary / "rustfmt",
            )

            outside = root / "outside"
            (root / "artifacts/cargo-home/rustup").rename(outside)
            (root / "artifacts/cargo-home/rustup").symlink_to(
                outside, target_is_directory=True
            )
            with (
                patch.object(clean, "_probe_semantic_tool") as hostile_probe,
                self.assertRaisesRegex(CleanError, "project-local Rust toolchain"),
            ):
                clean._validate_linux_rust_toolchain(root)
            hostile_probe.assert_not_called()

        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            rustup = root / "artifacts/cargo-home/rustup"
            binary = rustup / "toolchains/1.94.0-aarch64-unknown-linux-gnu/bin"
            binary.mkdir(parents=True)
            for name in ("cargo", "rustc", "rustdoc", "rustfmt", "cargo-fmt"):
                path = binary / name
                path.write_bytes(b"tool")
                path.chmod(0o555)
            calls = 0

            def exchange(
                path: Path, _name: str, _version: str, **_kwargs: object
            ) -> Path:
                nonlocal calls
                calls += 1
                if calls == 1:
                    rustup.rename(root / "detached-rustup")
                    replacement = (
                        rustup / "toolchains/1.94.0-aarch64-unknown-linux-gnu/bin"
                    )
                    replacement.mkdir(parents=True)
                    for name in ("cargo", "rustc", "rustdoc", "rustfmt", "cargo-fmt"):
                        leaf = replacement / name
                        leaf.write_bytes(b"replacement")
                        leaf.chmod(0o555)
                return path

            with (
                patch.object(clean, "_probe_semantic_tool", side_effect=exchange),
                patch.object(clean, "_probe_linux_cargo_fmt") as cargo_fmt,
                self.assertRaisesRegex(CleanError, "project-local Rust toolchain"),
            ):
                clean._validate_linux_rust_toolchain(root)
            cargo_fmt.assert_not_called()

    def test_cargo_fmt_dispatch_has_closed_local_tool_and_version_contract(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            binary = root / "rust/bin"
            cargo = binary / "cargo"
            cargo_fmt = binary / "cargo-fmt"
            rustc = binary / "rustc"
            rustdoc = binary / "rustdoc"
            rustfmt = binary / "rustfmt"
            with patch.object(
                clean,
                "_invoke",
                return_value=(b"rustfmt 1.8.0-stable (abc123 2026-03-01)\n", b""),
            ) as invoke:
                clean._probe_linux_cargo_fmt(
                    root, cargo, cargo_fmt, rustc, rustdoc, rustfmt
                )

            self.assertEqual(
                (cargo, [str(cargo), "fmt", "--version"]),
                invoke.call_args.args[:2],
            )
            environment = invoke.call_args.args[2]
            self.assertEqual("never", environment["CARGO_CACHE_AUTO_CLEAN_FREQUENCY"])
            self.assertEqual(
                "sparse", environment["CARGO_REGISTRIES_CRATES_IO_PROTOCOL"]
            )
            self.assertEqual(str(binary), environment["PATH"])
            self.assertEqual(str(rustc), environment["RUSTC"])
            self.assertEqual(str(rustdoc), environment["RUSTDOC"])
            self.assertEqual(str(rustfmt), environment["RUSTFMT"])

            with (
                patch.object(clean, "_invoke") as wrong_invoke,
                self.assertRaisesRegex(CleanError, "cargo-fmt dispatch"),
            ):
                clean._probe_linux_cargo_fmt(
                    root,
                    cargo,
                    root / "outside/cargo-fmt",
                    rustc,
                    rustdoc,
                    rustfmt,
                )
            wrong_invoke.assert_not_called()

            for stdout, stderr in (
                (b"rustfmt 1.8.1\n", b""),
                (b"rustfmt 1.8.0 (ok\x01bad)\n", b""),
                (b"rustfmt 1.8.0\nextra\n", b""),
                (b"rustfmt 1.8.0\n", b"warning\n"),
            ):
                with (
                    self.subTest(stdout=stdout, stderr=stderr),
                    patch.object(clean, "_invoke", return_value=(stdout, stderr)),
                    self.assertRaisesRegex(CleanError, "cargo-fmt dispatch"),
                ):
                    clean._probe_linux_cargo_fmt(
                        root, cargo, cargo_fmt, rustc, rustdoc, rustfmt
                    )

    def test_named_container_cleanup_runs_after_success_and_failure(self) -> None:
        with TemporaryDirectory() as directory:
            temporary = Path(directory).resolve()
            checkout = temporary / "checkout"
            checkout.mkdir()
            with patch.object(clean, "_extract_linux_uv", return_value=b"uv-binary"):
                tool = clean._materialize_linux_uv(temporary, b"archive")
            clean_lock = clean._validate_linux_lock(linux_source_lock())
            image = f"docker.io/library/rust@{clean_lock.platform_digest}"
            client = SimpleNamespace(temporary=temporary)
            calls: list[list[str]] = []

            def invoke(_client: object, suffix: list[str], **_kwargs: object):
                calls.append(list(suffix))
                if suffix[0] == "run":
                    cidfile = Path(suffix[suffix.index("--cidfile") + 1])
                    cidfile.write_text("a" * 64, encoding="ascii")
                    return b"docker-acquire-v0\n", b""
                name = calls[0][calls[0].index("--name") + 1]
                if suffix[1] == "inspect":
                    container_id = suffix[-1]
                    self.assertEqual(
                        [
                            "container",
                            "inspect",
                            "--format",
                            "{{.Id}}\t{{.Name}}",
                            container_id,
                        ],
                        suffix,
                    )
                    return f"{container_id}\t/{name}\n".encode(), b""
                if suffix[1] == "rm":
                    container_id = suffix[-1]
                    return (container_id + "\n").encode(), b""
                return b"", b""

            with patch.object(clean, "_docker_call", side_effect=invoke):
                clean._run_linux_container(
                    client,
                    checkout,
                    tool,
                    clean_lock,
                    image,
                    "acquire",
                )
            self.assertEqual(
                ["run", "container", "container", "container"],
                [call[0] for call in calls],
            )
            self.assertEqual(["rm", "--force", "--volumes"], calls[2][1:4])
            self.assertEqual("a" * 64, calls[2][-1])
            self.assertEqual("ls", calls[3][1])
            self.assertIn("--quiet", calls[3])
            self.assertEqual([], list(temporary.glob("*.cid")))

            calls.clear()

            def fail_then_cleanup(
                _client: object, suffix: list[str], **_kwargs: object
            ):
                calls.append(list(suffix))
                if suffix[0] == "run":
                    Path(suffix[suffix.index("--cidfile") + 1]).write_text(
                        "b" * 64, encoding="ascii"
                    )
                    raise clean.RegistryError("registry.process_exit:9")
                container_id = suffix[-1]
                name = calls[0][calls[0].index("--name") + 1]
                if suffix[1] == "inspect":
                    return f"{container_id}\t/{name}\n".encode(), b""
                if suffix[1] == "rm":
                    return (container_id + "\n").encode(), b""
                return b"", b""

            with (
                patch.object(clean, "_docker_call", side_effect=fail_then_cleanup),
                self.assertRaises(clean.RegistryError),
            ):
                clean._run_linux_container(
                    client,
                    checkout,
                    tool,
                    clean_lock,
                    image,
                    "acquire",
                )
            self.assertEqual(
                ["run", "container", "container", "container"],
                [call[0] for call in calls],
            )
            self.assertEqual([], list(temporary.glob("*.cid")))

            calls.clear()

            def diverged(_client: object, suffix: list[str], **_kwargs: object):
                calls.append(list(suffix))
                if suffix[0] == "run":
                    Path(suffix[suffix.index("--cidfile") + 1]).write_text(
                        "c" * 64, encoding="ascii"
                    )
                    return b"docker-acquire-v0\n", b""
                return f"{'c' * 64}\t/unrelated\n".encode(), b""

            with (
                patch.object(clean, "_docker_call", side_effect=diverged),
                self.assertRaisesRegex(CleanError, "cleanup"),
            ):
                clean._run_linux_container(
                    client,
                    checkout,
                    tool,
                    clean_lock,
                    image,
                    "acquire",
                )
            self.assertEqual(["run", "container"], [call[0] for call in calls])

    def test_failed_run_without_cidfile_proves_name_absent_and_never_deletes_by_name(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            temporary = Path(directory).resolve()
            checkout = temporary / "checkout"
            checkout.mkdir()
            with patch.object(clean, "_extract_linux_uv", return_value=b"uv-binary"):
                tool = clean._materialize_linux_uv(temporary, b"archive")
            clean_lock = clean._validate_linux_lock(linux_source_lock())
            image = f"docker.io/library/rust@{clean_lock.platform_digest}"
            client = SimpleNamespace(temporary=temporary)
            calls: list[list[str]] = []

            def absent(_client: object, suffix: list[str], **_kwargs: object):
                calls.append(list(suffix))
                if suffix[0] == "run":
                    raise clean.RegistryError("registry.process_exit:125")
                return b"", b""

            with (
                patch.object(clean, "_docker_call", side_effect=absent),
                self.assertRaises(clean.RegistryError),
            ):
                clean._run_linux_container(
                    client, checkout, tool, clean_lock, image, "acquire"
                )
            self.assertEqual(["run", "container"], [call[0] for call in calls])
            self.assertEqual("ls", calls[1][1])
            self.assertNotIn("rm", calls[1])

            calls.clear()

            def rebound(_client: object, suffix: list[str], **_kwargs: object):
                calls.append(list(suffix))
                if suffix[0] == "run":
                    raise clean.RegistryError("registry.process_exit:125")
                return b"d" * 64 + b"\n", b""

            with (
                patch.object(clean, "_docker_call", side_effect=rebound),
                self.assertRaisesRegex(CleanError, "cleanup"),
            ):
                clean._run_linux_container(
                    client, checkout, tool, clean_lock, image, "acquire"
                )
            self.assertEqual(["run", "container"], [call[0] for call in calls])

    def test_linux_absolute_python_alias_fails_inventory_before_normalization(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _python_root, alias = self._python_alias_checkout(root)

            with self.assertRaisesRegex(ValueError, "unsafe acquisition symlink"):
                clean.build_inventory(root)

            self.assertEqual(self._PYTHON_CONTAINER_TARGET, alias.readlink().as_posix())

    def test_linux_python_alias_normalizes_to_exact_inventoried_relative_link(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _python_root, alias = self._python_alias_checkout(root)
            real_replace = clean.os.replace
            replacements = 0

            def replace_once(*args: object, **kwargs: object) -> None:
                nonlocal replacements
                replacements += 1
                real_replace(*args, **kwargs)

            with (
                patch.object(clean.os, "replace", side_effect=replace_once),
                patch.object(
                    clean.os,
                    "link",
                    side_effect=AssertionError("normalizer must not hard-link"),
                ),
                patch.object(
                    clean.os,
                    "unlink",
                    side_effect=AssertionError("normalizer must not unlink"),
                ),
                patch.object(
                    clean,
                    "_invoke",
                    side_effect=AssertionError("normalizer must not launch a process"),
                ),
            ):
                clean._normalize_linux_python_alias(root)

            self.assertEqual(1, replacements)
            self.assertEqual(self._PYTHON_VERSION, alias.readlink().as_posix())
            self.assertEqual(
                [
                    {
                        "path": f"artifacts/uv-python/{self._PYTHON_ALIAS}",
                        "target": self._PYTHON_VERSION,
                    }
                ],
                clean.build_inventory(root)["links"],
            )

    def test_linux_python_alias_rejects_noncanonical_inputs_and_collisions(
        self,
    ) -> None:
        for mutation in (
            "wrong-target",
            "already-relative",
            "regular-file",
            "directory",
            "temporary-collision",
        ):
            with self.subTest(mutation=mutation), TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                python_root, alias = self._python_alias_checkout(root)
                collision: Path | None = None
                if mutation == "wrong-target":
                    alias.unlink()
                    alias.symlink_to(
                        "/workspace/artifacts/uv-python/"
                        "cpython-3.14.5-linux-aarch64-gnu"
                    )
                elif mutation == "already-relative":
                    alias.unlink()
                    alias.symlink_to(self._PYTHON_VERSION)
                elif mutation == "regular-file":
                    alias.unlink()
                    alias.write_bytes(b"not a link")
                elif mutation == "directory":
                    alias.unlink()
                    alias.mkdir()
                else:
                    collision = python_root / self._PYTHON_NORMALIZE_TEMPORARY
                    collision.write_bytes(b"unowned temporary")
                alias_before = alias.lstat()
                collision_before = collision.lstat() if collision is not None else None

                replace = Mock()
                with (
                    patch.object(clean.os, "replace", replace),
                    self.assertRaises(CleanError),
                ):
                    clean._normalize_linux_python_alias(root)

                replace.assert_not_called()
                alias_after = alias.lstat()
                self.assertEqual(
                    (alias_before.st_dev, alias_before.st_ino, alias_before.st_mode),
                    (alias_after.st_dev, alias_after.st_ino, alias_after.st_mode),
                )
                if mutation == "wrong-target":
                    self.assertEqual(
                        "/workspace/artifacts/uv-python/"
                        "cpython-3.14.5-linux-aarch64-gnu",
                        alias.readlink().as_posix(),
                    )
                elif mutation == "already-relative":
                    self.assertEqual(self._PYTHON_VERSION, alias.readlink().as_posix())
                elif mutation == "regular-file":
                    self.assertEqual(b"not a link", alias.read_bytes())
                elif mutation == "directory":
                    self.assertTrue(alias.is_dir())
                else:
                    assert collision is not None
                    assert collision_before is not None
                    collision_after = collision.lstat()
                    self.assertEqual(
                        (
                            collision_before.st_dev,
                            collision_before.st_ino,
                            collision_before.st_mode,
                        ),
                        (
                            collision_after.st_dev,
                            collision_after.st_ino,
                            collision_after.st_mode,
                        ),
                    )
                    self.assertEqual(b"unowned temporary", collision.read_bytes())

    def test_linux_python_alias_rejects_non_directory_version_target(self) -> None:
        for target_type in ("symlink", "regular-file"):
            with (
                self.subTest(target_type=target_type),
                TemporaryDirectory() as directory,
            ):
                root = Path(directory).resolve()
                python_root, alias = self._python_alias_checkout(root)
                target = python_root / self._PYTHON_VERSION
                target.rmdir()
                if target_type == "symlink":
                    (python_root / "other-version").mkdir()
                    target.symlink_to("other-version", target_is_directory=True)
                else:
                    target.write_bytes(b"not a directory")
                alias_before = alias.lstat()
                target_before = target.lstat()

                replace = Mock()
                with (
                    patch.object(clean.os, "replace", replace),
                    self.assertRaises(CleanError),
                ):
                    clean._normalize_linux_python_alias(root)

                replace.assert_not_called()
                alias_after = alias.lstat()
                target_after = target.lstat()
                self.assertEqual(
                    (alias_before.st_dev, alias_before.st_ino, alias_before.st_mode),
                    (alias_after.st_dev, alias_after.st_ino, alias_after.st_mode),
                )
                self.assertEqual(
                    (target_before.st_dev, target_before.st_ino, target_before.st_mode),
                    (target_after.st_dev, target_after.st_ino, target_after.st_mode),
                )
                self.assertEqual(
                    self._PYTHON_CONTAINER_TARGET, alias.readlink().as_posix()
                )
                if target_type == "symlink":
                    self.assertEqual("other-version", target.readlink().as_posix())
                else:
                    self.assertEqual(b"not a directory", target.read_bytes())

    def test_linux_python_alias_postpublication_failure_leaves_published_state(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            python_root, alias = self._python_alias_checkout(root)
            real_replace = clean.os.replace
            replacements = 0

            def replace_once(*args: object, **kwargs: object) -> None:
                nonlocal replacements
                replacements += 1
                real_replace(*args, **kwargs)

            with (
                patch.object(clean.os, "replace", side_effect=replace_once),
                patch.object(clean.os, "fsync", side_effect=OSError("injected fsync")),
                self.assertRaises(CleanError),
            ):
                clean._normalize_linux_python_alias(root)

            self.assertEqual(1, replacements)
            self.assertEqual(self._PYTHON_VERSION, alias.readlink().as_posix())
            self.assertEqual(
                self._PYTHON_VERSION,
                clean.build_inventory(root)["links"][0]["target"],
            )
            temporary = python_root / self._PYTHON_NORMALIZE_TEMPORARY
            self.assertFalse(temporary.exists() or temporary.is_symlink())

    def test_linux_python_alias_replace_failure_leaves_scratch_for_outer_discard(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            python_root, alias = self._python_alias_checkout(root)
            temporary = python_root / self._PYTHON_NORMALIZE_TEMPORARY
            replace = Mock(side_effect=OSError("injected replace"))

            with (
                patch.object(clean.os, "replace", replace),
                patch.object(
                    clean.os,
                    "unlink",
                    side_effect=AssertionError("normalizer must not clean pathnames"),
                ),
                self.assertRaises(CleanError),
            ):
                clean._normalize_linux_python_alias(root)

            self.assertEqual(1, replace.call_count)
            self.assertEqual(self._PYTHON_CONTAINER_TARGET, alias.readlink().as_posix())
            self.assertEqual(self._PYTHON_VERSION, temporary.readlink().as_posix())

    def test_linux_python_alias_descriptor_close_failure_remains_hard(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _python_root, alias = self._python_alias_checkout(root)
            real_close = clean.os.close
            real_fsync = clean.os.fsync
            python_descriptor: int | None = None
            injected = False

            def remember_python_descriptor(descriptor: int) -> None:
                nonlocal python_descriptor
                python_descriptor = descriptor
                real_fsync(descriptor)

            def fail_python_close(descriptor: int) -> None:
                nonlocal injected
                if descriptor == python_descriptor and not injected:
                    injected = True
                    raise OSError("injected descriptor close")
                real_close(descriptor)

            try:
                with (
                    patch.object(
                        clean.os, "fsync", side_effect=remember_python_descriptor
                    ),
                    patch.object(clean.os, "close", side_effect=fail_python_close),
                    self.assertRaises(CleanError),
                ):
                    clean._normalize_linux_python_alias(root)
            finally:
                if python_descriptor is not None and injected:
                    real_close(python_descriptor)

            self.assertTrue(injected)
            self.assertEqual(self._PYTHON_VERSION, alias.readlink().as_posix())

    def test_linux_python_alias_rechecks_source_immediately_before_replace(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _python_root, alias = self._python_alias_checkout(root)
            original = alias.lstat()
            real_open = clean.os.open
            real_replace = clean.os.replace
            replace = Mock(wraps=real_replace)
            temporary_opens = 0

            def substitute_during_second_temporary_resolution(
                path: object,
                flags: int,
                mode: int = 0o777,
                *,
                dir_fd: int | None = None,
            ) -> int:
                nonlocal temporary_opens
                if path == self._PYTHON_NORMALIZE_TEMPORARY:
                    temporary_opens += 1
                    if temporary_opens == 2:
                        alias.unlink()
                        alias.symlink_to(self._PYTHON_CONTAINER_TARGET)
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with (
                patch.object(
                    clean.os,
                    "open",
                    side_effect=substitute_during_second_temporary_resolution,
                ),
                patch.object(clean.os, "replace", replace),
                self.assertRaises(CleanError),
            ):
                clean._normalize_linux_python_alias(root)

            self.assertEqual(2, temporary_opens)
            replace.assert_not_called()
            changed = alias.lstat()
            self.assertNotEqual(
                (original.st_dev, original.st_ino),
                (changed.st_dev, changed.st_ino),
            )
            self.assertEqual(
                self._PYTHON_CONTAINER_TARGET, alias.readlink().as_posix()
            )

    def test_linux_python_alias_detects_substituted_temporary_at_publication(
        self,
    ) -> None:
        for substituted_target in ("adversarial", self._PYTHON_VERSION):
            with (
                self.subTest(substituted_target=substituted_target),
                TemporaryDirectory() as directory,
            ):
                root = Path(directory).resolve()
                _python_root, alias = self._python_alias_checkout(root)
                real_replace = clean.os.replace
                real_symlink = clean.os.symlink
                real_unlink = clean.os.unlink
                calls = 0

                def substitute_then_replace(
                    source: str,
                    destination: str,
                    *,
                    src_dir_fd: int,
                    dst_dir_fd: int,
                ) -> None:
                    nonlocal calls
                    calls += 1
                    real_unlink(source, dir_fd=src_dir_fd)
                    real_symlink(substituted_target, source, dir_fd=src_dir_fd)
                    real_replace(
                        source,
                        destination,
                        src_dir_fd=src_dir_fd,
                        dst_dir_fd=dst_dir_fd,
                    )

                with (
                    patch.object(
                        clean.os, "replace", side_effect=substitute_then_replace
                    ),
                    self.assertRaises(CleanError),
                ):
                    clean._normalize_linux_python_alias(root)

                self.assertEqual(1, calls)
                self.assertEqual(substituted_target, alias.readlink().as_posix())

    def test_linux_postpublication_substitutions_stop_before_inventory(self) -> None:
        for mutation in ("alias", "parent", "target"):
            with self.subTest(mutation=mutation), TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                python_root, alias = self._python_alias_checkout(root)
                version = python_root / self._PYTHON_VERSION
                real_fsync = clean.os.fsync
                real_replace = clean.os.replace
                replacements = 0

                def replace_once(*args: object, **kwargs: object) -> None:
                    nonlocal replacements
                    replacements += 1
                    real_replace(*args, **kwargs)

                def substitute_after_fsync(descriptor: int) -> None:
                    real_fsync(descriptor)
                    if mutation == "alias":
                        alias.unlink()
                        alias.symlink_to("adversarial")
                    elif mutation == "parent":
                        python_root.rename(root / "artifacts/uv-python-held")
                        python_root.mkdir()
                    else:
                        version.rename(python_root / f"{self._PYTHON_VERSION}.held")
                        version.mkdir()

                phases: list[str] = []
                with (
                    patch.object(clean, "_validate_runtime_roots"),
                    patch.object(
                        clean,
                        "_run_linux_container",
                        side_effect=lambda *_args: phases.append(_args[-1]),
                    ),
                    patch.object(clean.os, "replace", side_effect=replace_once),
                    patch.object(clean.os, "fsync", side_effect=substitute_after_fsync),
                    patch.object(
                        clean,
                        "build_inventory",
                        side_effect=AssertionError("inventory must not start"),
                    ) as build,
                    self.assertRaises(CleanError),
                ):
                    clean._run_linux_phases(
                        SimpleNamespace(),
                        root,
                        SimpleNamespace(),
                        SimpleNamespace(),
                        "image",
                        root / "git",
                    )

                self.assertEqual(1, replacements)
                self.assertEqual(["probe", "acquire"], phases)
                build.assert_not_called()

    def test_linux_phases_publish_once_then_compare_offline_and_full_inventory(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            temporary = Path(directory).resolve()
            checkout = temporary / "checkout"
            checkout.mkdir()
            tool = SimpleNamespace()
            client = SimpleNamespace()
            git = temporary / "git"
            clean_lock = clean._validate_linux_lock(linux_source_lock())
            image = f"docker.io/library/rust@{clean_lock.platform_digest}"
            inventory = {"schema_version": 0, "roots": [], "files": [], "links": []}
            phases: list[str] = []
            events: list[str] = []
            with (
                patch.object(clean, "_validate_runtime_roots") as roots,
                patch.object(
                    clean,
                    "_run_linux_container",
                    side_effect=lambda *_args: (
                        phases.append(_args[-1]),
                        events.append(_args[-1]),
                    ),
                ),
                patch.object(
                    clean,
                    "load_inventory",
                    side_effect=lambda *_args: (
                        events.append("reload"),
                        inventory,
                    )[1],
                ) as load,
                patch.object(
                    clean,
                    "build_inventory",
                    side_effect=lambda *_args: (
                        events.append("build"),
                        inventory,
                    )[1],
                ) as build,
                patch.object(
                    clean,
                    "_normalize_linux_python_alias",
                    side_effect=lambda *_args: events.append("normalize"),
                    create=True,
                ) as normalize,
                patch.object(
                    clean,
                    "write_inventory",
                    side_effect=lambda *_args: events.append("publish"),
                ) as write,
                patch.object(
                    clean,
                    "_remove_disposable_outputs",
                    side_effect=lambda *_args: events.append("remove"),
                ) as remove,
                patch.object(
                    clean,
                    "_recreate_cargo_target_root",
                    side_effect=lambda *_args: events.append("recreate"),
                ) as recreate,
                patch.object(
                    clean,
                    "_validate_offline_disposable_state",
                    side_effect=lambda *_args: events.append("state"),
                    create=True,
                ) as state,
                patch.object(clean, "_validate_cargo_target_root") as target,
            ):
                clean._run_linux_phases(
                    client,
                    checkout,
                    tool,
                    clean_lock,
                    image,
                    git,
                )

        self.assertEqual(["probe", "acquire", "offline"], phases)
        roots.assert_called_once_with(checkout)
        normalize.assert_called_once_with(checkout)
        remove.assert_called_once_with(checkout, git)
        recreate.assert_called_once_with(checkout)
        state.assert_called_once_with(checkout)
        target.assert_called_once_with(checkout)
        self.assertEqual(
            [
                "probe",
                "acquire",
                "normalize",
                "build",
                "publish",
                "reload",
                "remove",
                "recreate",
                "state",
                "offline",
                "reload",
                "build",
            ],
            events,
        )
        write.assert_called_once_with(checkout, inventory)
        self.assertEqual(2, load.call_count)
        self.assertEqual(2, build.call_count)
        self.assertIn(
            "rust_tools\nfull\ninventory\nrust_tools\nfull\ninventory",
            clean._LINUX_OFFLINE_SCRIPT,
        )

    def test_linux_host_inventory_failure_starts_neither_deletion_nor_offline(
        self,
    ) -> None:
        inventory = {"schema_version": 0, "roots": [], "files": [], "links": []}
        for failure in (
            "acquire",
            "normalize",
            "build",
            "write",
            "reload",
            "reload_error",
        ):
            events: list[str] = []

            def run(*_args):
                phase = _args[-1]
                events.append(phase)
                if failure == "acquire" and phase == "acquire":
                    raise CleanError("acquisition or cleanup failed")

            def normalize(_root):
                events.append("normalize")
                if failure == "normalize":
                    raise CleanError("alias normalization failed")

            def build(_root):
                events.append("build")
                if failure == "build":
                    raise CleanError("inventory build failed")
                return inventory

            def write(_root, _inventory):
                events.append("write")
                if failure == "write":
                    raise CleanError("inventory write failed")

            def load(_root):
                events.append("reload")
                if failure == "reload_error":
                    raise CleanError("inventory reload failed")
                return {} if failure == "reload" else inventory

            with (
                self.subTest(failure=failure),
                patch.object(clean, "_validate_runtime_roots"),
                patch.object(clean, "_run_linux_container", side_effect=run),
                patch.object(
                    clean,
                    "_normalize_linux_python_alias",
                    side_effect=normalize,
                    create=True,
                ),
                patch.object(clean, "build_inventory", side_effect=build),
                patch.object(clean, "write_inventory", side_effect=write),
                patch.object(clean, "load_inventory", side_effect=load),
                patch.object(
                    clean,
                    "_remove_disposable_outputs",
                    side_effect=lambda *_args: events.append("remove"),
                ),
                patch.object(
                    clean,
                    "_recreate_cargo_target_root",
                    side_effect=lambda *_args: events.append("recreate"),
                ),
                patch.object(
                    clean,
                    "_validate_offline_disposable_state",
                    side_effect=lambda *_args: events.append("state"),
                ),
                patch.object(
                    clean,
                    "_validate_cargo_target_root",
                    side_effect=lambda *_args: events.append("target"),
                ),
                self.assertRaises(CleanError),
            ):
                clean._run_linux_phases(
                    SimpleNamespace(),
                    Path("/checkout"),
                    SimpleNamespace(),
                    clean._validate_linux_lock(linux_source_lock()),
                    "docker.io/library/rust@sha256:" + "a" * 64,
                    Path("/git"),
                )

            self.assertNotIn("remove", events)
            self.assertNotIn("offline", events)
            if failure == "acquire":
                self.assertNotIn("normalize", events)
            else:
                self.assertIn("normalize", events)
                if failure != "normalize":
                    failed_event = "reload" if failure == "reload_error" else failure
                    self.assertLess(
                        events.index("normalize"), events.index(failed_event)
                    )
            if failure == "normalize":
                self.assertNotIn("build", events)
                self.assertNotIn("write", events)
                self.assertNotIn("reload", events)
                self.assertNotIn("recreate", events)
                self.assertNotIn("state", events)
                self.assertNotIn("target", events)

    def test_offline_phase_requires_absent_venv_and_exact_empty_target(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / "artifacts/cargo-target"
            target.mkdir(parents=True)
            clean._validate_offline_disposable_state(root)

            (root / ".venv").mkdir()
            with self.assertRaisesRegex(CleanError, "offline disposable state"):
                clean._validate_offline_disposable_state(root)
            (root / ".venv").rmdir()

            (target / "hostile").write_bytes(b"x")
            with self.assertRaisesRegex(CleanError, "offline disposable state"):
                clean._validate_offline_disposable_state(root)

        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            root = Path(directory).resolve()
            artifacts = root / "artifacts"
            artifacts.mkdir()
            (artifacts / "cargo-target").symlink_to(
                Path(outside), target_is_directory=True
            )
            with self.assertRaisesRegex(CleanError, "offline disposable state"):
                clean._validate_offline_disposable_state(root)


if __name__ == "__main__":
    unittest.main()
