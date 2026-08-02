from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from golden_board import checks, cli


ROOT = Path(__file__).resolve().parents[2]


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


class StaticDependencyPolicyTests(unittest.TestCase):
    def mutate(self, relative: str, addition: str) -> Path:
        temporary, root = _copy_repository()
        self.addCleanup(temporary.cleanup)
        path = root / relative
        path.write_text(path.read_text(encoding="utf-8") + addition, encoding="utf-8")
        return root

    def test_static_policy_is_process_free_and_short_circuits_metadata(self) -> None:
        root = self.mutate("Cargo.toml", '\n[patch.crates-io]\nsha2 = { git = "x" }\n')
        with patch.object(
            checks, "_cargo_metadata_errors", side_effect=AssertionError("metadata")
        ):
            self.assertTrue(
                checks._dependency_errors(root, cargo_executable=Path("/cargo"))
            )

    def test_constants_source_uses_the_shared_mount_safe_reader(self) -> None:
        with patch.object(
            checks,
            "read_regular_below",
            wraps=checks.read_regular_below,
        ) as reader:
            checks._load_source(ROOT)
        reader.assert_called_once_with(ROOT, checks._SOURCE, checks._MAX_SOURCE_BYTES)

    def test_text_tree_rejects_mount_identity_before_scandir(self) -> None:
        temporary, root = _copy_repository()
        self.addCleanup(temporary.cleanup)
        root = root.resolve(strict=True)
        target = root / "docs"
        target_identity = (target.stat().st_dev, target.stat().st_ino)
        scandir = os.scandir

        def reject_target_scan(path):
            if isinstance(path, int):
                facts = os.fstat(path)
                if (facts.st_dev, facts.st_ino) == target_identity:
                    raise AssertionError("mounted text tree was scanned")
            elif Path(path) == target:
                raise AssertionError("mounted text tree was scanned by path")
            return scandir(path)

        def mount_check(_repository, _descriptor, path: Path) -> bool:
            return path != target

        with (
            patch.object(
                checks,
                "same_held_mount",
                side_effect=mount_check,
            ) as checked,
            patch.object(checks.os, "scandir", side_effect=reject_target_scan),
            self.assertRaises(ValueError),
        ):
            checks._text_paths(root)
        checked.assert_called()

    def test_text_tree_entry_cap_is_enforced_while_scanning(self) -> None:
        temporary, root = _copy_repository()
        self.addCleanup(temporary.cleanup)
        root = root.resolve(strict=True)

        class Entries:
            def __init__(self) -> None:
                self.index = 0

            def __enter__(self):
                return self

            def __exit__(self, *_arguments):
                return False

            def __iter__(self):
                return self

            def __next__(self):
                self.index += 1
                if self.index <= 2:
                    return SimpleNamespace(name=f"entry-{self.index}")
                raise AssertionError("text scan consumed past its entry cap")

        entries = Entries()
        with (
            patch.object(checks, "_TEXT_TREES", ("docs",)),
            patch.object(checks, "_MAX_TEXT_ENTRIES", 1),
            patch.object(checks.os, "scandir", return_value=entries),
            self.assertRaisesRegex(ValueError, "text-entry limit"),
        ):
            checks._text_paths(root)
        self.assertEqual(2, entries.index)

    def test_directory_entry_cap_is_enforced_while_scanning(self) -> None:
        temporary, root = _copy_repository()
        self.addCleanup(temporary.cleanup)
        root = root.resolve(strict=True)

        class Entries:
            def __init__(self) -> None:
                self.index = 0

            def __enter__(self):
                return self

            def __exit__(self, *_arguments):
                return False

            def __iter__(self):
                return self

            def __next__(self):
                self.index += 1
                if self.index <= 2:
                    return SimpleNamespace(name=f"entry-{self.index}")
                raise AssertionError("directory scan consumed past its entry cap")

        entries = Entries()
        with (
            patch.object(checks, "_MAX_TEXT_ENTRIES", 1),
            patch.object(checks.os, "scandir", return_value=entries),
            self.assertRaisesRegex(ValueError, "text-entry limit"),
        ):
            checks._directory_entries(root, checks.PurePosixPath("docs"))
        self.assertEqual(2, entries.index)

    def test_static_policy_rejects_every_unreviewed_rust_target_surface(self) -> None:
        for relative in (
            "crates/golden-board-core/build.rs",
            "crates/golden-board-core/src/main.rs",
            "crates/golden-board-core/src/bin/other.rs",
            "crates/golden-board-core/examples/example.rs",
            "crates/golden-board-core/benches/bench.rs",
            "crates/golden-board-core/tests/other.rs",
        ):
            with self.subTest(relative=relative):
                temporary, root = _copy_repository()
                self.addCleanup(temporary.cleanup)
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fn main() {}\n", encoding="utf-8")
                self.assertTrue(checks.static_dependency_errors(root))

    def test_static_policy_rejects_aliased_and_dynamic_python_process_routes(
        self,
    ) -> None:
        mutations = (
            "\nimport subprocess as sp\nrunner = sp.run\nrunner(['/attacker'])\n",
            "\nimport asyncio as aio\naio.create_subprocess_shell('attacker')\n",
            "\nimport os as operating_system\noperating_system.posix_spawn('/x', ['/x'], {})\n",
            "\nimport pty as terminal\nterminal.spawn(['/attacker'])\n",
            "\nimport multiprocessing as mp\nmp.Process(target=lambda: None).start()\n",
            "\nimport subprocess\ngetattr(subprocess, 'run')(['/attacker'])\n",
            "\nimport subprocess\nsubprocess.__dict__['run'](['/attacker'])\n",
            "\nimport functools, subprocess\nrunner = functools.partial(subprocess.run, ['/attacker'])\nrunner()\n",
            "\nimport subprocess\nsubprocess.run.__call__(['/attacker'])\n",
            "\nimport sys\nsys.modules['subprocess'].run(['/attacker'])\n",
            "\nimport sys\nsys.modules.get('os').system('/attacker')\n",
            "\nimport subprocess\ngetattr(subprocess.run, '__call__')(['/attacker'])\n",
        )
        for addition in mutations:
            with self.subTest(addition=addition):
                root = self.mutate("python/golden_board/identity.py", addition)
                self.assertTrue(checks.static_dependency_errors(root))

    def test_static_policy_binds_reviewed_process_argv_environment_and_limits(
        self,
    ) -> None:
        mutations = (
            (
                "python/golden_board/registry.py",
                "start_new_session=True",
                "start_new_session=False",
            ),
            (
                "python/golden_board/reports.py",
                '"ls-files",',
                '"status",',
            ),
            (
                "python/golden_board/bootstrap.py",
                "output_limit=OUTPUT_LIMIT,",
                "output_limit=1,",
            ),
        )
        for relative, before, after in mutations:
            with self.subTest(relative=relative, before=before):
                temporary, root = _copy_repository()
                self.addCleanup(temporary.cleanup)
                path = root / relative
                text = path.read_text(encoding="utf-8")
                self.assertIn(before, text)
                path.write_text(text.replace(before, after, 1), encoding="utf-8")
                self.assertTrue(checks.static_dependency_errors(root))

    def test_static_policy_binds_complete_acquisition_and_check_grammar(self) -> None:
        mutations = (
            (
                "python/golden_board/bootstrap.py",
                '        "--no-config",\n        "run",',
                '        "run",',
            ),
            (
                "python/golden_board/bootstrap.py",
                '        "--offline",\n        "--frozen",',
                '        "--frozen",',
            ),
            (
                "python/golden_board/bootstrap.py",
                '        "--frozen",\n        "--no-cache",',
                '        "--no-cache",',
            ),
            (
                "python/golden_board/bootstrap.py",
                '        "--no-cache",\n        "--python",',
                '        "--python",',
            ),
            (
                "python/golden_board/bootstrap.py",
                '[str(uv), "--no-config", "sync", "--project", str(root), "--locked"]',
                '[str(uv), "--no-config", "sync", "--project", str(root)]',
            ),
            (
                "python/golden_board/bootstrap.py",
                '"UV_CACHE_DIR": str(repository / "artifacts/uv-cache")',
                '"UV_CACHE_DIR": "/tmp/global-uv-cache"',
            ),
            (
                "python/golden_board/checks.py",
                'cargo_arguments.extend(("--offline", "--locked"))',
                'cargo_arguments.extend(("--offline",))',
            ),
            (
                "python/golden_board/checks.py",
                '[str(python), "-P", "-B", "-S", "-m", "unittest", "-q", *modules]',
                '[str(python), "-P", "-B", "-m", "unittest", "-q", *modules]',
            ),
            (
                "python/golden_board/checks.py",
                '"PYTHONDONTWRITEBYTECODE": "1",',
                '"PYTHONDONTWRITEBYTECODE": "0",',
            ),
            (
                "python/golden_board/checks.py",
                'repository / "artifacts/check-pycache"',
                'repository / "artifacts/global-pycache"',
            ),
            (
                "python/golden_board/cli.py",
                'NATIVE_EVIDENCE = Path("artifacts/native-verification.json")',
                'NATIVE_EVIDENCE = Path("elsewhere.json")',
            ),
        )
        for relative, before, after in mutations:
            with self.subTest(relative=relative, before=before):
                temporary, root = _copy_repository()
                self.addCleanup(temporary.cleanup)
                path = root / relative
                text = path.read_text(encoding="utf-8")
                self.assertIn(before, text)
                path.write_text(text.replace(before, after, 1), encoding="utf-8")
                self.assertTrue(checks.static_dependency_errors(root))

    def test_static_policy_covers_every_full_test_module(self) -> None:
        expected = {
            path.relative_to(ROOT / "python")
            .with_suffix("")
            .as_posix()
            .replace("/", ".")
            for path in (ROOT / "python/tests").glob("test_*.py")
        }
        self.assertEqual(expected, set(checks._PYTHON_TESTS))
        self.assertIn("tests.test_bootstrap_hardening", checks._PYTHON_TESTS)
        self.assertIn("tests.test_acquisition_hardening", checks._PYTHON_TESTS)
        self.assertIn("tests.test_check_hardening", checks._PYTHON_TESTS)


class SealedCapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "artifacts/check-pycache").mkdir(parents=True)
        self.tools: dict[str, Path] = {}
        for name in ("git", "cargo", "cargo-fmt", "rustc", "rustdoc", "rustfmt"):
            path = self.root / name
            path.write_bytes(name.encode("ascii"))
            path.chmod(0o700)
            self.tools[name] = path

    def runner(self, argv: list[str], **kwargs: object) -> object:
        del kwargs
        outputs = {
            "git": b"git version 2.49.0\n",
            "cargo": b"cargo 1.94.0 (Homebrew)\n",
            "cargo-fmt": b"rustfmt 1.8.0\n",
            "rustc": b"rustc 1.94.0 (4a4ef493e 2026-03-02) (Homebrew)\n",
            "rustdoc": b"rustdoc 1.94.0 (4a4ef493e 2026-03-02) (Homebrew)\n",
            "rustfmt": b"rustfmt 1.8.0\n",
        }
        return SimpleNamespace(
            returncode=0, stdout=outputs[Path(argv[0]).name], stderr=b""
        )

    def environment(self) -> dict[str, str]:
        environment = {
            f"GB_BOOTSTRAP_{name.upper().replace('-', '_')}": str(path)
            for name, path in self.tools.items()
        }
        environment.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPYCACHEPREFIX": str(self.root / "artifacts/check-pycache"),
            }
        )
        return environment

    def test_module_context_consumes_all_absolute_capabilities(self) -> None:
        (
            git,
            git_environment,
            cargo,
            cargo_fmt,
            rustc,
            rustdoc,
            rustfmt,
            pycache_prefix,
        ) = cli._module_capability_context(
            self.root, self.environment(), runner=self.runner
        )
        self.assertEqual(self.tools["git"], git)
        self.assertEqual(self.tools["cargo"], cargo)
        self.assertEqual(self.tools["cargo-fmt"], cargo_fmt)
        self.assertEqual(self.tools["rustc"], rustc)
        self.assertEqual(self.tools["rustdoc"], rustdoc)
        self.assertEqual(self.tools["rustfmt"], rustfmt)
        self.assertEqual(self.root / "artifacts/check-pycache", pycache_prefix)
        self.assertEqual("0", git_environment["GIT_OPTIONAL_LOCKS"])
        self.assertEqual("1", git_environment["GIT_NO_LAZY_FETCH"])
        self.assertFalse(set(self.environment()) & set(git_environment))

    def test_module_context_rejects_missing_and_semantically_wrong_versions(
        self,
    ) -> None:
        environment = self.environment()
        del environment["GB_BOOTSTRAP_RUSTC"]
        with self.assertRaises(ValueError):
            cli._module_capability_context(self.root, environment, runner=self.runner)

        for key, value in (
            ("PYTHONDONTWRITEBYTECODE", "0"),
            ("PYTHONPYCACHEPREFIX", "/tmp/global-pycache"),
        ):
            with self.subTest(key=key):
                environment = self.environment()
                environment[key] = value
                with self.assertRaises(ValueError):
                    cli._module_capability_context(
                        self.root, environment, runner=self.runner
                    )

        def wrong(argv: list[str], **kwargs: object) -> object:
            result = self.runner(argv, **kwargs)
            if Path(argv[0]).name == "cargo":
                result.stdout = b"cargo 1.94.00 (Homebrew)\n"
            return result

        with self.assertRaises(ValueError):
            cli._module_capability_context(self.root, self.environment(), runner=wrong)

    def test_cli_forwards_explicit_rust_capabilities(self) -> None:
        pycache_prefix = self.root / "artifacts/check-pycache"
        with patch.object(checks, "run_mode", return_value=[]) as run:
            self.assertEqual(
                0,
                cli.main(
                    ("check", "fast"),
                    self.root,
                    cargo_executable=self.tools["cargo"],
                    cargo_fmt_executable=self.tools["cargo-fmt"],
                    rustc_executable=self.tools["rustc"],
                    rustdoc_executable=self.tools["rustdoc"],
                    rustfmt_executable=self.tools["rustfmt"],
                    pycache_prefix=pycache_prefix,
                ),
            )
        self.assertEqual(self.tools["cargo"], run.call_args.kwargs["cargo_executable"])
        self.assertEqual(
            self.tools["cargo-fmt"], run.call_args.kwargs["cargo_fmt_executable"]
        )
        self.assertEqual(self.tools["rustc"], run.call_args.kwargs["rustc_executable"])
        self.assertEqual(
            self.tools["rustdoc"], run.call_args.kwargs["rustdoc_executable"]
        )
        self.assertEqual(
            self.tools["rustfmt"], run.call_args.kwargs["rustfmt_executable"]
        )
        self.assertEqual(pycache_prefix, run.call_args.kwargs["pycache_prefix"])

    def test_child_environment_contains_exact_git_lock_suppression(self) -> None:
        environment = checks._child_environment(
            self.root,
            tuple(
                self.tools[name]
                for name in ("cargo", "cargo-fmt", "rustc", "rustdoc", "rustfmt")
            ),
        )
        self.assertEqual("0", environment["GIT_OPTIONAL_LOCKS"])
        self.assertEqual("1", environment["GIT_NO_LAZY_FETCH"])
        self.assertEqual("1", environment["PYTHONDONTWRITEBYTECODE"])
        self.assertEqual(
            str(self.root / "artifacts/check-pycache"),
            environment["PYTHONPYCACHEPREFIX"],
        )
        self.assertNotIn("GB_BOOTSTRAP_CARGO", environment)
        self.assertNotIn("RUSTC_WRAPPER", environment)

    def test_pycache_projection_rejects_symlink_mount_and_content(self) -> None:
        prefix = self.root / "artifacts/check-pycache"
        (prefix / "poison.pyc").write_bytes(b"poison")
        with self.assertRaises(ValueError):
            checks._validated_pycache_prefix(self.root)
        (prefix / "poison.pyc").unlink()
        real_fstat = os.fstat
        calls = 0

        def other_device(descriptor: int) -> os.stat_result:
            nonlocal calls
            calls += 1
            facts = real_fstat(descriptor)
            if calls > 1:
                values = list(facts)
                values[2] += 1
                return os.stat_result(values)
            return facts

        with patch.object(checks.os, "fstat", side_effect=other_device):
            with self.assertRaises(ValueError):
                checks._validated_pycache_prefix(self.root)
        with patch.object(checks.os.path, "ismount", return_value=True):
            with self.assertRaises(ValueError):
                checks._validated_pycache_prefix(self.root)
        prefix.rmdir()
        outside = self.root / "outside"
        outside.mkdir()
        prefix.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            checks._validated_pycache_prefix(self.root)

    def test_pycache_projection_rejects_same_device_linux_mount_identity(self) -> None:
        with (
            patch.object(
                checks,
                "same_held_mount",
                return_value=False,
                create=True,
            ) as mount_check,
            self.assertRaises(ValueError),
        ):
            checks._validated_pycache_prefix(self.root)
        mount_check.assert_called()

    def test_nested_python_ignores_a_poisoned_source_tree_cache_by_exact_env(
        self,
    ) -> None:
        poison = self.root / "python/golden_board/__pycache__"
        poison.mkdir(parents=True)
        (poison / "identity.cpython-314.pyc").write_bytes(b"valid-looking poison")
        captured: dict[str, object] = {}

        def command(argv, root, environment):
            del root
            captured.update(argv=argv, environment=environment)
            return []

        with patch.object(checks, "_command", side_effect=command):
            self.assertEqual(
                [],
                checks._python_tests(
                    self.root,
                    ("tests.test_identity",),
                    pycache_prefix=self.root / "artifacts/check-pycache",
                ),
            )
        self.assertEqual(
            [
                str(Path(checks.sys.executable).resolve()),
                "-P",
                "-B",
                "-S",
                "-m",
                "unittest",
                "-q",
                "tests.test_identity",
            ],
            captured["argv"],
        )
        environment = captured["environment"]
        self.assertIsInstance(environment, dict)
        self.assertEqual("1", environment["PYTHONDONTWRITEBYTECODE"])
        self.assertEqual(
            str(self.root / "artifacts/check-pycache"),
            environment["PYTHONPYCACHEPREFIX"],
        )
        self.assertNotEqual(str(poison), environment["PYTHONPYCACHEPREFIX"])

    def test_nested_python_disables_site_and_cwd_shadowing_but_uses_pythonpath(
        self,
    ) -> None:
        temporary, root = _copy_repository()
        self.addCleanup(temporary.cleanup)
        root = root.resolve(strict=True)
        (root / "artifacts/check-pycache").mkdir(parents=True)
        site_marker = root / "sitecustomize-ran"
        shadow_marker = root / "cwd-unittest-ran"
        suite_marker = root / "pythonpath-suite-ran"
        (root / "python/sitecustomize.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(site_marker)!r}).write_text('ran', encoding='utf-8')\n",
            encoding="utf-8",
        )
        (root / "unittest.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(shadow_marker)!r}).write_text('ran', encoding='utf-8')\n",
            encoding="utf-8",
        )
        (root / "python/tests/test_site_isolation_probe.py").write_text(
            "from pathlib import Path\n"
            "import unittest\n"
            "from golden_board.constants import MANIFEST\n"
            f"Path({str(suite_marker)!r}).write_text('ran', encoding='utf-8')\n"
            "class SiteIsolationProbe(unittest.TestCase):\n"
            "    def test_project_package_import(self):\n"
            "        self.assertEqual(b'GB-MANIFEST-v0\\x00', MANIFEST)\n",
            encoding="utf-8",
        )

        self.assertEqual(
            [],
            checks._python_tests(
                root,
                ("tests.test_site_isolation_probe",),
                pycache_prefix=root / "artifacts/check-pycache",
            ),
        )
        self.assertTrue(suite_marker.is_file())
        self.assertFalse(site_marker.exists())
        self.assertFalse(shadow_marker.exists())

    def test_git_probe_uses_the_bounded_process_primitive(self) -> None:
        captured: dict[str, object] = {}

        def bounded(argv, raw, environment, **kwargs):
            captured.update(argv=argv, raw=raw, environment=environment, kwargs=kwargs)
            return b"git version 2.49.0\n", b""

        with patch.object(cli, "_run_bounded_process", side_effect=bounded):
            result = cli._git_version_runner(
                [str(self.tools["git"]), "--version"],
                cwd=self.root,
                env={"LANG": "C"},
            )
        self.assertEqual(0, result.returncode)
        self.assertEqual(False, captured["kwargs"].get("shell", False))
        self.assertEqual(10, captured["kwargs"]["timeout"])
        self.assertEqual(4096, captured["kwargs"]["output_limit"])


class FocusCompositionTests(unittest.TestCase):
    def test_foundation_and_dependencies_run_owned_nonrecursive_suites(self) -> None:
        with (
            patch.object(checks, "_foundation_errors", return_value=[]),
            patch.object(checks, "_dependency_errors", return_value=[]),
            patch.object(checks, "_python_tests", return_value=[]) as tests,
        ):
            self.assertEqual(
                [],
                checks.run_area(
                    ROOT, "foundation", cargo_executable=Path("/sealed/cargo")
                ),
            )
            foundation = tests.call_args.args[1]
            self.assertEqual(
                [],
                checks.run_area(
                    ROOT, "dependencies", cargo_executable=Path("/sealed/cargo")
                ),
            )
            dependencies = tests.call_args.args[1]
        self.assertIn("tests.test_foundation", foundation)
        self.assertIn("tests.test_status", foundation)
        self.assertIn("tests.test_check_hardening", dependencies)
        self.assertNotIn("tests.test_checks", foundation + dependencies)


if __name__ == "__main__":
    unittest.main()
