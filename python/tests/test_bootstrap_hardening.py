from __future__ import annotations

import importlib.util
import marshal
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from golden_board import bootstrap
from golden_board.bootstrap import BootstrapError
from golden_board.registry import RegistryError


ROOT = Path(__file__).resolve().parents[2]


class BootstrapHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def _git_context(self) -> tuple[Path, dict[str, str]]:
        (self.root / "python").mkdir(exist_ok=True)
        bootstrap.prepare_directories(self.root, acquisition=True)
        git = self.root / "git"
        git.write_bytes(b"git")
        git.chmod(0o700)
        (self.root / ".git").mkdir(exist_ok=True)
        (self.root / ".git/HEAD").write_text("ref: refs/heads/m0\n", encoding="ascii")
        (self.root / ".git/config").write_text(
            "[core]\n\trepositoryformatversion = 0\n", encoding="ascii"
        )
        (self.root / ".gitignore").write_text(".venv/\n", encoding="ascii")
        return git, bootstrap.git_environment(self.root, git)

    @staticmethod
    def _clean_git_runner(argv, raw, environment, **kwargs):
        del environment, kwargs
        if argv[1:3] == ["--no-pager", "config"]:
            return b"core.repositoryformatversion\0", b""
        if "ls-files" in argv:
            return b"", b""
        if "check-ignore" in argv:
            return b".gitignore\x001\x00.venv/\x00" + raw, b""
        raise AssertionError(argv)

    def test_static_dependency_failure_precedes_tools_directories_and_removal(
        self,
    ) -> None:
        arguments = (
            "acquire",
            str(ROOT),
            *("/unused",) * 6,
        )
        with (
            patch.object(bootstrap.sys, "version_info", (3, 14, 6)),
            patch.object(
                bootstrap,
                "_static_dependency_preflight",
                side_effect=BootstrapError("dependency policy rejected"),
            ),
            patch.object(bootstrap, "_tools") as tools,
            patch.object(bootstrap, "prepare_directories") as prepare,
            patch.object(bootstrap, "remove_venv") as remove,
        ):
            self.assertEqual(1, bootstrap.main(arguments))
        tools.assert_not_called()
        prepare.assert_not_called()
        remove.assert_not_called()

    def test_acquisition_overwrites_hostile_rustfmt_with_the_validated_sibling(
        self,
    ) -> None:
        tools = tuple(
            Path("/tools") / name
            for name in (
                "python3.14",
                "uv",
                "cargo",
                "cargo-fmt",
                "rustc",
                "rustdoc",
                "rustfmt",
                "git",
            )
        )
        children: list[tuple[list[str], dict[str, str]]] = []

        def project_environment(*_args, **_kwargs):
            return {"RUSTFMT": os.environ["RUSTFMT"]}

        def run_command(argv, environment, _root):
            children.append((argv, dict(environment)))
            return b"", b""

        lock = SimpleNamespace(
            clean_linux=SimpleNamespace(platform_digest="sha256:" + "0" * 64)
        )
        arguments = ("acquire", str(ROOT), *("/unused",) * 6)
        with (
            patch.dict(os.environ, {"RUSTFMT": "/attacker/rustfmt"}, clear=False),
            patch.object(bootstrap.sys, "version_info", (3, 14, 6)),
            patch.object(bootstrap, "_static_dependency_preflight"),
            patch.object(bootstrap, "validate_cargo_configuration"),
            patch.object(bootstrap, "load_source_lock", return_value=lock),
            patch.object(bootstrap, "validate_platform_marker", return_value=None),
            patch.object(bootstrap, "_tools", return_value=tools),
            patch.object(bootstrap, "prepare_directories"),
            patch.object(bootstrap, "_validate_sdk", return_value=None),
            patch.object(
                bootstrap, "project_environment", side_effect=project_environment
            ),
            patch.object(bootstrap, "remove_venv"),
            patch.object(bootstrap, "git_environment", return_value={}),
            patch.object(bootstrap, "_run_command", side_effect=run_command),
            patch.object(bootstrap, "validate_venv"),
            patch.object(bootstrap, "build_inventory", return_value=object()),
            patch.object(bootstrap, "write_inventory"),
        ):
            self.assertEqual(0, bootstrap.main(arguments))
        cargo_fetch = next(child for child in children if child[0][0] == "/tools/cargo")
        self.assertEqual("/tools/rustfmt", cargo_fetch[1]["RUSTFMT"])
        self.assertNotIn("/attacker/rustfmt", cargo_fetch[1].values())

    def test_unignored_or_tracked_venv_is_preserved(self) -> None:
        git, environment = self._git_context()
        venv = self.root / ".venv"
        venv.mkdir()
        marker = venv / "marker"
        marker.write_bytes(b"keep")

        def unignored(*args, **kwargs):
            del args, kwargs
            raise RegistryError("injected")

        with self.assertRaises(BootstrapError):
            bootstrap.remove_venv(
                self.root,
                git_executable=git,
                git_environment=environment,
                runner=unignored,
            )
        self.assertEqual(b"keep", marker.read_bytes())

        calls = 0

        def tracked(argv, raw, child_environment, **kwargs):
            nonlocal calls
            del argv, child_environment, kwargs
            calls += 1
            return (raw, b"") if calls == 1 else (b".venv/marker\0", b"")

        with self.assertRaises(BootstrapError):
            bootstrap.remove_venv(
                self.root,
                git_executable=git,
                git_environment=environment,
                runner=tracked,
            )
        self.assertEqual(b"keep", marker.read_bytes())

    def test_git_disposable_proof_rejects_git_tree_before_runner(self) -> None:
        git, environment = self._git_context()
        venv = self.root / ".venv"
        venv.mkdir()
        marker = venv / "marker"
        marker.write_bytes(b"keep")
        called = False

        def runner(*args, **kwargs):
            nonlocal called
            del args, kwargs
            called = True
            return b"", b""

        with (
            patch.object(
                bootstrap,
                "git_control_preflight",
                side_effect=bootstrap.ReportError("Git metadata tree is unsafe"),
                create=True,
            ) as validate,
            self.assertRaises(BootstrapError),
        ):
            bootstrap.remove_venv(
                self.root,
                git_executable=git,
                git_environment=environment,
                runner=runner,
            )
        validate.assert_called_once()
        self.assertFalse(called)
        self.assertEqual(b"keep", marker.read_bytes())

    def test_local_git_exclude_cannot_prove_venv_disposable(self) -> None:
        git, environment = self._git_context()
        venv = self.root / ".venv"
        venv.mkdir()
        marker = venv / "marker"
        marker.write_bytes(b"keep")

        def runner(argv, raw, child_environment, **kwargs):
            del child_environment, kwargs
            if argv[1:3] == ["--no-pager", "config"]:
                return b"core.repositoryformatversion\0", b""
            if "check-ignore" in argv:
                return b".git/info/exclude\x001\x00.venv/\x00" + raw, b""
            return b"", b""

        with self.assertRaisesRegex(BootstrapError, "ignore proof"):
            bootstrap.remove_venv(
                self.root,
                git_executable=git,
                git_environment=environment,
                runner=runner,
            )
        self.assertEqual(b"keep", marker.read_bytes())

    def test_real_repository_git_proves_tracked_venv_ignore_attribution(self) -> None:
        candidate = Path(
            "/opt/homebrew/bin/git" if sys.platform == "darwin" else "/usr/bin/git"
        )
        if not candidate.exists() or not (ROOT / ".git").is_dir():
            self.skipTest("fixed local Git checkout capability unavailable")
        git = candidate.resolve(strict=True)
        bootstrap._prove_venv_disposable(
            ROOT,
            git,
            bootstrap.git_environment(ROOT, git),
            bootstrap._run_bounded_process,
        )

    def test_absent_but_tracked_venv_is_rejected(self) -> None:
        git, environment = self._git_context()
        calls = 0

        def tracked(argv, raw, child_environment, **kwargs):
            nonlocal calls
            del argv, child_environment, kwargs
            calls += 1
            return (raw, b"") if calls == 1 else (b".venv/owned\0", b"")

        with self.assertRaises(BootstrapError):
            bootstrap.remove_venv(
                self.root,
                git_executable=git,
                git_environment=environment,
                runner=tracked,
            )
        self.assertFalse((self.root / ".venv").exists())

    def test_nested_mount_or_unsupported_entry_is_preserved(self) -> None:
        git, environment = self._git_context()
        venv = self.root / ".venv"
        nested = venv / "nested"
        nested.mkdir(parents=True)
        marker = nested / "marker"
        marker.write_bytes(b"keep")
        with (
            patch.object(
                bootstrap,
                "same_held_mount",
                side_effect=lambda _root, _descriptor, path: path != nested,
            ),
            self.assertRaises(BootstrapError),
        ):
            bootstrap.remove_venv(
                self.root,
                git_executable=git,
                git_environment=environment,
                runner=self._clean_git_runner,
            )
        self.assertEqual(b"keep", marker.read_bytes())

        if hasattr(os, "mkfifo"):
            fifo = nested / "fifo"
            os.mkfifo(fifo)
            with self.assertRaises(BootstrapError):
                bootstrap.remove_venv(
                    self.root,
                    git_executable=git,
                    git_environment=environment,
                    runner=self._clean_git_runner,
                )
            self.assertTrue(stat.S_ISFIFO(fifo.lstat().st_mode))

    def test_venv_entry_cap_fails_before_removal(self) -> None:
        git, environment = self._git_context()
        venv = self.root / ".venv"
        venv.mkdir()
        (venv / "one").write_bytes(b"1")
        (venv / "two").write_bytes(b"2")
        with (
            patch.object(bootstrap, "MAX_VENV_ENTRIES", 1),
            self.assertRaises(BootstrapError),
        ):
            bootstrap.remove_venv(
                self.root,
                git_executable=git,
                git_environment=environment,
                runner=self._clean_git_runner,
            )
        self.assertEqual({"one", "two"}, {path.name for path in venv.iterdir()})

    def test_default_tool_probe_is_bounded_and_semantic_versions_are_closed(
        self,
    ) -> None:
        tool = self.root / "tool"
        tool.write_text(
            '#!/bin/sh\ni=0; while [ "$i" -lt 5000 ]; do printf x; i=$((i + 1)); done\n',
            encoding="utf-8",
        )
        tool.chmod(0o700)
        with self.assertRaises(BootstrapError):
            bootstrap.validate_tool(
                tool, (), b"never", runner=bootstrap._default_runner
            )

        def valid(_argv, **_kwargs):
            return SimpleNamespace(
                returncode=0, stdout=b"cargo 1.94.0 (Homebrew)\n", stderr=b""
            )

        def junk(_argv, **_kwargs):
            return SimpleNamespace(
                returncode=0, stdout=b"cargo 1.94.0 attacker-junk\n", stderr=b""
            )

        self.assertEqual(
            tool,
            bootstrap.validate_semantic_tool(tool, "cargo", "1.94.0", runner=valid),
        )
        with self.assertRaises(BootstrapError):
            bootstrap.validate_semantic_tool(tool, "cargo", "1.94.0", runner=junk)
        with self.assertRaises(BootstrapError):
            bootstrap.validate_semantic_tool(
                self.root / "missing-rustdoc", "rustdoc", "1.94.0", runner=valid
            )

        if hasattr(os, "symlink"):
            tool_directory = self.root / "tools"
            tool_directory.mkdir()
            cargo_fmt = tool_directory / "cargo-fmt"
            cargo_fmt.symlink_to(tool)

            def rustfmt(argv, **kwargs):
                del argv, kwargs
                return SimpleNamespace(
                    returncode=0, stdout=b"rustfmt 1.8.0\n", stderr=b""
                )

            self.assertEqual(
                tool,
                bootstrap.validate_semantic_tool(
                    cargo_fmt, "rustfmt", "1.8.0", runner=rustfmt
                ),
            )

    def test_clean_linux_semantic_probe_uses_only_fixed_rustup_home(self) -> None:
        tool = self.root / "cargo"
        tool.write_bytes(b"cargo")
        tool.chmod(0o700)
        environments: list[dict[str, str]] = []

        def runner(_argv, **kwargs):
            environments.append(dict(kwargs["env"]))
            return SimpleNamespace(
                returncode=0, stdout=b"cargo 1.94.0\n", stderr=b""
            )

        with patch.dict(
            os.environ,
            {
                "CARGO_HOME": "/attacker/cargo",
                "HOME": "/attacker/home",
                "RUSTUP_HOME": "/attacker/rustup",
            },
            clear=False,
        ):
            self.assertEqual(
                tool,
                bootstrap._validate_clean_linux_semantic_tool(
                    tool, "cargo", "1.94.0", runner=runner
                ),
            )
        self.assertEqual(
            [
                {
                    "CARGO_HOME": "/workspace/artifacts/cargo-home",
                    "HOME": "/workspace/artifacts/check-home",
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PATH": str(tool.parent),
                    "RUSTUP_HOME": "/workspace/artifacts/cargo-home/rustup",
                    "TZ": "UTC",
                }
            ],
            environments,
        )

    def test_image_git_probe_accepts_only_the_closed_git_2_grammar(self) -> None:
        tool = self.root / "git"
        tool.write_bytes(b"git")
        tool.chmod(0o700)
        projected: list[dict[str, str]] = []

        def result(stdout: bytes):
            def runner(_argv, **kwargs):
                projected.append(dict(kwargs["env"]))
                return SimpleNamespace(returncode=0, stdout=stdout, stderr=b"")

            return runner

        for stdout in (b"git version 2.0.0\n", b"git version 2.39.5\n"):
            with self.subTest(stdout=stdout):
                self.assertEqual(
                    tool,
                    bootstrap.validate_image_git(tool, runner=result(stdout)),
                )
        for stdout in (
            b"git version 1.99.9\n",
            b"git version 3.0.0\n",
            b"git version 2.39\n",
            b"git version 2.39.5 attacker\n",
            b"git version 2.39.5\r\n",
            b"git version 2.1000.0\n",
            b"x" * (bootstrap.TOOL_OUTPUT_LIMIT + 1),
        ):
            with self.subTest(stdout=stdout), self.assertRaises(BootstrapError):
                bootstrap.validate_image_git(tool, runner=result(stdout))
        self.assertTrue(projected)
        self.assertTrue(
            all(environment["GIT_NO_LAZY_FETCH"] == "1" for environment in projected)
        )

    def test_tool_bundle_uses_image_git_only_for_validated_clean_linux(self) -> None:
        arguments = tuple(
            f"/tools/{name}"
            for name in ("python3.14", "uv", "cargo", "rustc", "rustfmt", "git")
        )
        with (
            patch.object(
                bootstrap, "validate_tool", side_effect=lambda path, *_args: path
            ) as exact,
            patch.object(
                bootstrap,
                "validate_semantic_tool",
                side_effect=lambda path, *_args, **_kwargs: path,
            ) as semantic,
            patch.object(
                bootstrap, "validate_image_git", side_effect=lambda path, **_kwargs: path
            ) as image_git,
            patch.object(
                bootstrap,
                "validate_host_git",
                side_effect=lambda path, **_kwargs: path,
            ) as host_git,
        ):
            tools = bootstrap._tools(arguments, clean_linux=True)
            self.assertEqual(Path("/tools/cargo-fmt"), tools[3])
            image_git.assert_called_once_with(Path("/tools/git"))
            self.assertFalse(
                any(call.args[0] == Path("/tools/git") for call in exact.call_args_list)
            )
            self.assertIn(
                (Path("/tools/cargo-fmt"), "rustfmt", "1.8.0"),
                tuple(call.args for call in semantic.call_args_list),
            )
            self.assertIn(
                (Path("/tools/rustdoc"), "rustdoc", "1.94.0"),
                tuple(call.args for call in semantic.call_args_list),
            )
            self.assertEqual(Path("/tools/rustdoc"), tools[5])

            exact.reset_mock()
            image_git.reset_mock()
            host_git.reset_mock()
            bootstrap._tools(arguments, clean_linux=False)
            image_git.assert_not_called()
            host_git.assert_called_once_with(Path("/tools/git"))

    def test_tool_bundle_rejects_sibling_tool_resolving_outside_cargo_directory(
        self,
    ) -> None:
        arguments = tuple(
            f"/tools/{name}"
            for name in ("python3.14", "uv", "cargo", "rustc", "rustfmt", "git")
        )

        for sibling in ("cargo-fmt", "rustc", "rustdoc", "rustfmt"):

            def semantic(path: Path, *_args: str, sibling: str = sibling) -> Path:
                if path == Path("/tools") / sibling:
                    return Path("/attacker") / sibling
                return path

            with (
                self.subTest(sibling=sibling),
                patch.object(
                    bootstrap, "validate_tool", side_effect=lambda path, *_args: path
                ),
                patch.object(bootstrap, "validate_semantic_tool", side_effect=semantic),
                self.assertRaisesRegex(
                    BootstrapError,
                    rf"{sibling} must be the validated cargo sibling",
                ),
            ):
                bootstrap._tools(arguments)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks required")
    def test_import_source_validation_rejects_a_python_leaf_symlink(self) -> None:
        python = self.root / "python"
        package = python / "golden_board"
        package.mkdir(parents=True)
        (package / "__init__.py").write_bytes(b"")
        outside = self.root / "outside.py"
        outside.write_bytes(b"VALUE = 1\n")
        (package / "module.py").symlink_to(outside)
        with self.assertRaises(RuntimeError):
            bootstrap._validate_import_sources(python)

    def test_import_source_validation_rejects_linux_mount_identity(self) -> None:
        with (
            patch.object(
                bootstrap,
                "_bootstrap_same_held_mount",
                return_value=False,
                create=True,
            ) as mount_check,
            self.assertRaises(RuntimeError),
        ):
            bootstrap._validate_import_sources(ROOT / "python")
        mount_check.assert_called()

    def test_import_cache_prefix_is_unique_empty_and_not_project_pycache(self) -> None:
        prefix = bootstrap._prepare_import_cache()
        try:
            self.assertTrue(prefix.is_absolute())
            self.assertEqual([], list(prefix.iterdir()))
            self.assertNotEqual(
                (ROOT / "python/golden_board/__pycache__").resolve(),
                prefix,
            )
        finally:
            bootstrap._discard_import_cache(prefix)
        self.assertFalse(prefix.exists())

    def test_untrusted_project_module_cannot_execute_before_source_seal(self) -> None:
        checkout = self.root / "checkout"
        package = checkout / "python/golden_board"
        shutil.copytree(
            ROOT / "python/golden_board",
            package,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        marker = self.root / "untrusted-module-executed"
        acquisition = package / "acquisition.py"
        raw = acquisition.read_text(encoding="utf-8")
        acquisition.write_text(
            raw.replace(
                "from __future__ import annotations\n",
                "from __future__ import annotations\nimport os\nos.system("
                + repr("/usr/bin/touch " + shlex.quote(str(marker)))
                + ")\n",
                1,
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-B", str(package / "bootstrap.py")],
            cwd=checkout,
            env={
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": str(Path(sys.executable).parent),
                "TZ": "UTC",
            },
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

    def test_shadow_package_cannot_execute_before_exact_entry_check(self) -> None:
        checkout = self.root / "shadow-checkout"
        package = checkout / "python/golden_board"
        shutil.copytree(
            ROOT / "python/golden_board",
            package,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        marker = self.root / "shadow-package-executed"
        shadow = package / "acquisition"
        shadow.mkdir()
        (shadow / "__init__.py").write_text(
            "import os\nos.system("
            + repr("/usr/bin/touch " + shlex.quote(str(marker)))
            + ")\n",
            encoding="utf-8",
        )
        with self.assertRaises(BootstrapError):
            bootstrap._default_runner(
                [sys.executable, "-I", "-S", "-B", str(package / "bootstrap.py")],
                cwd=checkout,
                env={
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PATH": str(Path(sys.executable).parent),
                    "TZ": "UTC",
                },
            )
        self.assertFalse(marker.exists())

    def test_python_root_shadow_modules_reject_before_project_import(self) -> None:
        checkout = self.root / "root-shadow-checkout"
        python_root = checkout / "python"
        shutil.copytree(
            ROOT / "python",
            python_root,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        hashlib_marker = self.root / "hashlib-shadow-executed"
        site_marker = self.root / "site-shadow-executed"
        for name, marker in (
            ("hashlib.py", hashlib_marker),
            ("sitecustomize.py", site_marker),
        ):
            (python_root / name).write_text(
                "import os\nos.system("
                + repr("/usr/bin/touch " + shlex.quote(str(marker)))
                + ")\n",
                encoding="utf-8",
            )
        with self.assertRaises(RuntimeError):
            bootstrap._validate_import_sources(python_root)
        with self.assertRaises(BootstrapError):
            bootstrap._default_runner(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-B",
                    str(python_root / "golden_board/bootstrap.py"),
                ],
                cwd=checkout,
                env={
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PATH": str(Path(sys.executable).parent),
                    "TZ": "UTC",
                },
            )
        self.assertFalse(hashlib_marker.exists())
        self.assertFalse(site_marker.exists())

    def test_venv_removal_never_calls_path_reopening_rmtree(self) -> None:
        git, environment = self._git_context()
        venv = self.root / ".venv"
        venv.mkdir()
        (venv / "leaf").write_bytes(b"remove")
        with patch.object(
            shutil, "rmtree", side_effect=AssertionError("rmtree reopen")
        ):
            bootstrap.remove_venv(
                self.root,
                git_executable=git,
                git_environment=environment,
                runner=self._clean_git_runner,
            )
        self.assertFalse(venv.exists())

    def test_descriptor_removal_preserves_a_swapped_in_victim(self) -> None:
        git, environment = self._git_context()
        venv = self.root / ".venv"
        venv.mkdir()
        (venv / "leaf").write_bytes(b"remove")
        victim = self.root / "victim"
        victim.mkdir()
        marker = victim / "marker"
        marker.write_bytes(b"preserve")
        displaced = self.root / "displaced"
        real_unlink = os.unlink
        swapped = False

        def swap_then_unlink(path, *, dir_fd=None):
            nonlocal swapped
            if not swapped:
                venv.rename(displaced)
                victim.rename(venv)
                swapped = True
            return real_unlink(path, dir_fd=dir_fd)

        with (
            patch.object(bootstrap.os, "unlink", side_effect=swap_then_unlink),
            self.assertRaises(BootstrapError),
        ):
            bootstrap.remove_venv(
                self.root,
                git_executable=git,
                git_environment=environment,
                runner=self._clean_git_runner,
            )
        self.assertTrue(swapped)
        self.assertEqual(b"preserve", (venv / "marker").read_bytes())

    def test_project_and_git_environments_are_exactly_closed(self) -> None:
        (self.root / "python").mkdir()
        bootstrap.prepare_directories(self.root, acquisition=False)
        environment = bootstrap.project_environment(
            self.root,
            python_path=self.root / "python",
            tool_directories=(Path("/tools"), Path("/usr/bin")),
            offline=True,
        )
        self.assertEqual("0", environment["GIT_OPTIONAL_LOCKS"])
        self.assertEqual("1", environment["GIT_NO_LAZY_FETCH"])
        self.assertEqual("/tools:/usr/bin", environment["PATH"])
        self.assertEqual("1", environment["PYTHONDONTWRITEBYTECODE"])
        self.assertEqual(
            str(self.root / "artifacts/check-pycache"),
            environment["PYTHONPYCACHEPREFIX"],
        )

        git = self.root / "git"
        expected = bootstrap.git_environment(self.root, git)
        self.assertEqual(
            {
                "GIT_CONFIG_GLOBAL",
                "GIT_CONFIG_NOSYSTEM",
                "GIT_OPTIONAL_LOCKS",
                "GIT_NO_LAZY_FETCH",
                "GIT_TERMINAL_PROMPT",
                "HOME",
                "LANG",
                "LC_ALL",
                "PATH",
                "TMPDIR",
                "TZ",
            },
            set(expected),
        )
        self.assertIn("/usr/bin", expected["PATH"].split(os.pathsep))

    def test_project_python_directory_rejects_linux_mount_identity(self) -> None:
        (self.root / "python").mkdir()
        bootstrap.prepare_directories(self.root, acquisition=False)
        with (
            patch.object(
                bootstrap,
                "same_held_mount",
                return_value=False,
                create=True,
            ) as mount_check,
            self.assertRaises(BootstrapError),
        ):
            bootstrap.project_environment(
                self.root,
                python_path=self.root / "python",
                tool_directories=(Path("/usr/bin"),),
                offline=True,
            )
        mount_check.assert_called()

    def test_project_child_ignores_poisoned_source_pycache_without_writes(self) -> None:
        checkout = self.root / "pycache-checkout"
        shutil.copytree(
            ROOT / "python",
            checkout / "python",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        bootstrap.prepare_directories(checkout, acquisition=False)
        source = checkout / "python/golden_board/cli.py"
        marker = self.root / "source-pyc-executed"
        code = compile(
            "import os\nos.system("
            + repr("/usr/bin/touch " + shlex.quote(str(marker)))
            + ")\n",
            str(source),
            "exec",
        )
        source_stat = source.stat()
        poisoned = (
            importlib.util.MAGIC_NUMBER
            + struct.pack("<III", 0, int(source_stat.st_mtime), source_stat.st_size)
            + marshal.dumps(code)
        )
        pyc = source.parent / "__pycache__" / f"cli.{sys.implementation.cache_tag}.pyc"
        pyc.parent.mkdir()
        pyc.write_bytes(poisoned)
        environment = bootstrap.project_environment(
            checkout,
            python_path=checkout / "python",
            tool_directories=(Path(sys.executable).parent, Path("/usr/bin")),
            offline=True,
        )
        try:
            bootstrap._default_runner(
                [sys.executable, "-B", "-m", "golden_board.cli"],
                cwd=checkout,
                env=environment,
            )
        except BootstrapError:
            pass
        self.assertFalse(marker.exists())
        self.assertEqual(poisoned, pyc.read_bytes())
        self.assertEqual([], list((checkout / "artifacts/check-pycache").iterdir()))

    def test_exact_project_child_argv_disables_sitecustomize_and_cwd_shadow(
        self,
    ) -> None:
        checkout = self.root / "site-checkout"
        shutil.copytree(
            ROOT / "python",
            checkout / "python",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        bootstrap.prepare_directories(checkout, acquisition=False)
        marker = self.root / "sitecustomize-executed"
        shadow_marker = self.root / "cwd-shadow-executed"
        hook = checkout / "python/sitecustomize.py"
        hook.write_text(
            "import os\nos.system("
            + repr("/usr/bin/touch " + shlex.quote(str(marker)))
            + ")\n",
            encoding="utf-8",
        )
        shadow = checkout / "golden_board"
        shadow.mkdir()
        (shadow / "__init__.py").write_text(
            "import os\nos.system("
            + repr("/usr/bin/touch " + shlex.quote(str(shadow_marker)))
            + ")\n",
            encoding="utf-8",
        )
        python = Path(sys.executable).resolve(strict=True)
        complete = bootstrap.project_argv(
            checkout,
            Path("/unused/uv"),
            python,
            ("check", "fast"),
        )
        start = max(
            index for index, value in enumerate(complete) if value == str(python)
        )
        child = complete[start:]
        self.assertEqual(
            [str(python), "-P", "-B", "-S", "-m"],
            child[:5],
        )
        environment = bootstrap.project_environment(
            checkout,
            python_path=checkout / "python",
            tool_directories=(python.parent, Path("/usr/bin")),
            offline=True,
        )
        try:
            bootstrap._default_runner(child, cwd=checkout, env=environment)
        except BootstrapError:
            pass
        self.assertFalse(marker.exists())
        self.assertFalse(shadow_marker.exists())
        self.assertEqual([], list((checkout / "artifacts/check-pycache").iterdir()))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks required")
    def test_project_child_rejects_a_symlinked_pycache_prefix(self) -> None:
        (self.root / "python").mkdir()
        bootstrap.prepare_directories(self.root, acquisition=False)
        prefix = self.root / "artifacts/check-pycache"
        prefix.mkdir(parents=True, exist_ok=True)
        prefix.rmdir()
        outside = self.root / "outside-pycache"
        outside.mkdir()
        prefix.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(BootstrapError):
            bootstrap.project_environment(
                self.root,
                python_path=self.root / "python",
                tool_directories=(Path("/usr/bin"),),
                offline=True,
            )

    def test_runtime_directories_reject_mounts_and_cross_device_descriptors(
        self,
    ) -> None:
        artifacts = self.root / "artifacts"
        with (
            patch.object(
                bootstrap,
                "same_held_mount",
                side_effect=lambda _root, _descriptor, path: path != artifacts,
            ),
            self.assertRaises(BootstrapError),
        ):
            bootstrap.prepare_directories(self.root, acquisition=False)

        if artifacts.exists():
            artifacts.rmdir()
        real_fstat = os.fstat
        calls = 0

        def cross_device(descriptor):
            nonlocal calls
            value = real_fstat(descriptor)
            calls += 1
            if calls == 2:
                return SimpleNamespace(
                    st_ctime_ns=value.st_ctime_ns,
                    st_dev=value.st_dev + 1,
                    st_ino=value.st_ino,
                    st_mode=value.st_mode,
                    st_mtime_ns=value.st_mtime_ns,
                    st_size=value.st_size,
                )
            return value

        with (
            patch.object(bootstrap.os, "fstat", side_effect=cross_device),
            self.assertRaises(BootstrapError),
        ):
            bootstrap.prepare_directories(self.root, acquisition=False)

    def test_runtime_directories_reject_linux_mount_identity(self) -> None:
        with (
            patch.object(
                bootstrap,
                "same_held_mount",
                return_value=False,
                create=True,
            ) as mount_check,
            self.assertRaises(BootstrapError),
        ):
            bootstrap.prepare_directories(self.root, acquisition=False)
        mount_check.assert_called()

    def test_venv_regular_leaf_mount_identity_is_preserved(self) -> None:
        git, environment = self._git_context()
        venv = self.root / ".venv"
        venv.mkdir()
        leaf = venv / "leaf"
        leaf.write_bytes(b"preserve")

        def mount_check(_repository, _descriptor, path: Path) -> bool:
            return path != leaf

        with (
            patch.object(
                bootstrap,
                "same_held_mount",
                side_effect=mount_check,
                create=True,
            ) as checked,
            self.assertRaises(BootstrapError),
        ):
            bootstrap.remove_venv(
                self.root,
                git_executable=git,
                git_environment=environment,
                runner=self._clean_git_runner,
            )
        checked.assert_called()
        self.assertEqual(b"preserve", leaf.read_bytes())

    def test_venv_regular_leaf_is_reopened_at_final_unlink_boundary(self) -> None:
        git, environment = self._git_context()
        venv = self.root / ".venv"
        venv.mkdir()
        leaf = venv / "leaf"
        leaf.write_bytes(b"preserve")
        leaf_checks = 0

        def mount_check(_repository, _descriptor, path: Path) -> bool:
            nonlocal leaf_checks
            if path == leaf:
                leaf_checks += 1
                return leaf_checks < 3
            return True

        real_unlink = os.unlink

        def reject_leaf_unlink(path, *, dir_fd=None):
            if path == "leaf":
                raise AssertionError("leaf was not reopened before unlink")
            return real_unlink(path, dir_fd=dir_fd)

        with (
            patch.object(bootstrap, "same_held_mount", side_effect=mount_check),
            patch.object(bootstrap.os, "unlink", side_effect=reject_leaf_unlink),
            self.assertRaises(BootstrapError),
        ):
            bootstrap.remove_venv(
                self.root,
                git_executable=git,
                git_environment=environment,
                runner=self._clean_git_runner,
            )
        self.assertGreaterEqual(leaf_checks, 3)
        self.assertEqual(b"preserve", leaf.read_bytes())


if __name__ == "__main__":
    unittest.main()
