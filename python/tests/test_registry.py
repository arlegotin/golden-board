import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
import time
import threading
import unittest
from unittest.mock import patch

from golden_board import source_lock
import golden_board.registry as registry_module
from golden_board.registry import (
    MAX_FIXTURE_BYTES,
    MAX_REGISTRY_BYTES,
    RegistryError,
    _materialize_fixture,
    _run_bounded_process,
    _rust_binary,
    _rust_result,
    _validated_target,
    load_registry,
    run_registered_vectors,
    validate_registry,
)


EMPTY_SCALAR = "d884e5911a8a923feb85ae9c2b8066eb982234dfe6c6e7f34900988e6dc27a14"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _case(**changes: object) -> dict[str, object]:
    fixture = b"\n"
    case: dict[str, object] = {
        "id": "identity-a-empty-scalar",
        "family": "identity",
        "operation": "identity-a-scalar",
        "input_path": "conformance/identity/a-empty-scalar.hex",
        "input_kind": "hex",
        "fixture_sha256": _sha(fixture),
        "input_sha256": _sha(b""),
        "expected_kind": "sha256",
        "expected": EMPTY_SCALAR,
        "implementations": ["python", "rust"],
        "owner": "spec/identity-v0.md#6",
    }
    case.update(changes)
    return case


def _registry(*cases: dict[str, object]) -> dict[str, object]:
    return {"schema_version": 0, "case": list(cases or (_case(),))}


def _toml(registry: dict[str, object]) -> str:
    lines = [f"schema_version = {registry['schema_version']}"]
    for key, value in registry.items():
        if key not in {"schema_version", "case"}:
            lines.append(f"{key} = {json.dumps(value)}")
    for case in registry["case"]:
        lines.append("\n[[case]]")
        for key, value in case.items():
            if isinstance(value, str):
                rendered = json.dumps(value)
            elif isinstance(value, list):
                rendered = "[" + ", ".join(json.dumps(item) for item in value) + "]"
            else:
                rendered = str(value).lower()
            lines.append(f"{key} = {rendered}")
    return "\n".join(lines) + "\n"


class RegistrySchemaTests(unittest.TestCase):
    def load(self, registry: dict[str, object]) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "conformance/registry.toml"
            path.parent.mkdir()
            path.write_text(_toml(registry), encoding="utf-8")
            return load_registry(path)

    def assert_rejected(self, registry: dict[str, object]) -> None:
        with self.assertRaises(RegistryError):
            self.load(registry)

    def test_closed_top_level_and_case_schema(self) -> None:
        top = _registry()
        top["unknown"] = 1
        self.assert_rejected(top)
        case = _case(unknown="x")
        self.assert_rejected(_registry(case))

    def test_duplicate_and_noncanonical_ids_reject(self) -> None:
        self.assert_rejected(_registry(_case(), _case()))
        for identifier in ("Upper", "has_underscore", "-leading", "trailing-", "two--hyphens"):
            with self.subTest(identifier=identifier):
                self.assert_rejected(_registry(_case(id=identifier)))

    def test_toml_escaped_nul_path_rejects(self) -> None:
        self.assert_rejected(
            _registry(_case(input_path="conformance/identity/nul\0fixture.hex"))
        )

    def test_unknown_enums_reject_but_source_inspect_is_admitted(self) -> None:
        changes = (
            {"family": "chess"},
            {"family": []},
            {"operation": "shell-text"},
            {"input_kind": "path"},
            {"input_kind": []},
            {"expected_kind": "bytes"},
            {"expected_kind": []},
            {"implementations": ["python", "browser"]},
        )
        for change in changes:
            with self.subTest(change=change):
                self.assert_rejected(_registry(_case(**change)))
        source = _case(
            id="source-doctor-example",
            family="source-doctor",
            operation="source-inspect",
            input_path="conformance/source-doctor/example.hex",
            expected_kind="diagnostic",
            expected="source.syntax",
            implementations=["python"],
            owner="docs/superpowers/specs/2026-08-02-m0-foundation-design.md#11",
        )
        self.load(_registry(source))

    def test_cases_have_stable_id_order(self) -> None:
        second = _case(id="identity-b-zero-scalar", operation="identity-b-scalar")
        loaded = self.load(_registry(second, _case()))
        self.assertEqual(
            ["identity-a-empty-scalar", "identity-b-zero-scalar"],
            [case["id"] for case in loaded["case"]],
        )

    def test_registry_read_delegates_once_to_shared_reader(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "conformance/registry.toml"
            path.parent.mkdir()
            path.write_text(_toml(_registry()), encoding="utf-8")
            with patch.object(
                registry_module,
                "read_regular_below",
                wraps=registry_module.read_regular_below,
            ) as reader:
                load_registry(path)
        reader.assert_called_once_with(
            path.parent.parent.resolve(),
            PurePosixPath("conformance/registry.toml"),
            MAX_REGISTRY_BYTES,
        )

    def test_registry_path_is_not_resolved_before_descriptor_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "conformance/registry.toml"
            path.parent.mkdir()
            path.write_text(_toml(_registry()), encoding="utf-8")
            real_resolve = type(path).resolve

            def reject_descendant_resolve(value: Path, *args: object, **kwargs: object):
                if value == path:
                    raise AssertionError("descendant resolve")
                return real_resolve(value, *args, **kwargs)

            with patch.object(type(path), "resolve", new=reject_descendant_resolve):
                self.assertEqual(0, load_registry(path)["schema_version"])

    def test_toml_integer_digit_limit_is_a_registry_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "conformance/registry.toml"
            path.parent.mkdir()
            path.write_text(
                "schema_version = " + "9" * 5_000 + "\ncase = []\n",
                encoding="utf-8",
            )
            with self.assertRaises(RegistryError):
                load_registry(path)

    def test_deep_toml_is_a_registry_error(self) -> None:
        nested = "[" * 2_000 + "0" + "]" * 2_000
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "conformance/registry.toml"
            path.parent.mkdir()
            path.write_text(
                f"schema_version = {nested}\ncase = []\n",
                encoding="utf-8",
            )
            with self.assertRaises(RegistryError):
                load_registry(path)

        with self.assertRaises(RegistryError):
            registry_module._materialize_recipe(f"kind = {nested}\n".encode())

    def test_reader_errors_are_not_misreported_as_toml_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "conformance/registry.toml"
            path.parent.mkdir()
            with self.assertRaisesRegex(RegistryError, r"^registry\.path$"):
                load_registry(path)
            path.write_bytes(b"\xef\xbb\xbfschema_version = 0\ncase = []\n")
            with self.assertRaisesRegex(RegistryError, r"^registry\.utf8$"):
                load_registry(path)

            with patch.object(registry_module.os, "O_NOFOLLOW", None):
                with self.assertRaisesRegex(RegistryError, r"^registry\.platform$"):
                    load_registry(path)

            with (
                patch.object(
                    source_lock,
                    "held_mount_identity",
                    return_value=(path.parent.parent.stat().st_dev, None),
                ),
                patch.object(source_lock, "same_held_mount", return_value=True),
                patch("golden_board.registry.os.read", side_effect=OSError("injected")),
            ):
                with self.assertRaisesRegex(RegistryError, r"^registry\.changed$"):
                    load_registry(path)


class RegistryFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        fixture = self.root / "conformance/identity/a-empty-scalar.hex"
        fixture.parent.mkdir(parents=True)
        fixture.write_bytes(b"\n")

    def errors(self, case: dict[str, object] | None = None) -> list[str]:
        return validate_registry(self.root, _registry(case or _case()))

    def test_valid_hex_fixture_passes(self) -> None:
        self.assertEqual([], self.errors())

    def test_fixture_read_delegates_once_to_shared_reader(self) -> None:
        with patch.object(
            registry_module,
            "read_regular_below",
            wraps=registry_module.read_regular_below,
        ) as reader:
            self.assertEqual([], self.errors())
        reader.assert_called_once_with(
            self.root.resolve(),
            PurePosixPath("conformance/identity/a-empty-scalar.hex"),
            MAX_FIXTURE_BYTES,
        )

    def test_missing_extra_and_hash_mismatch_reject(self) -> None:
        fixture = self.root / "conformance/identity/a-empty-scalar.hex"
        fixture.unlink()
        self.assertTrue(self.errors())
        fixture.write_bytes(b"00\n")
        self.assertTrue(self.errors())
        fixture.write_bytes(b"\n")
        extra = self.root / "conformance/identity/extra.hex"
        extra.write_bytes(b"00\n")
        self.assertTrue(self.errors())

    def test_absolute_parent_and_backslash_paths_reject(self) -> None:
        for value in (
            str((self.root / "outside.hex").resolve()),
            "conformance/../outside.hex",
            "conformance\\identity\\a-empty-scalar.hex",
            "conformance/identity/nul\0fixture.hex",
        ):
            with self.subTest(value=value):
                self.assertTrue(self.errors(_case(input_path=value)))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks required")
    def test_leaf_and_parent_symlinks_reject(self) -> None:
        fixture = self.root / "conformance/identity/a-empty-scalar.hex"
        real = self.root / "real.hex"
        real.write_bytes(b"\n")
        fixture.unlink()
        fixture.symlink_to(real)
        self.assertTrue(self.errors())

        fixture.unlink()
        identity = fixture.parent
        identity.rmdir()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "a-empty-scalar.hex").write_bytes(b"\n")
        identity.symlink_to(outside, target_is_directory=True)
        self.assertTrue(self.errors())

    def test_nonregular_oversized_and_nonlowercase_hex_reject(self) -> None:
        fixture = self.root / "conformance/identity/a-empty-scalar.hex"
        fixture.unlink()
        fixture.mkdir()
        self.assertTrue(self.errors())
        fixture.rmdir()
        fixture.write_bytes(b"0" * (MAX_FIXTURE_BYTES + 1))
        self.assertTrue(self.errors())
        fixture.write_bytes(b"AA\n")
        case = _case(fixture_sha256=_sha(b"AA\n"), input_sha256=_sha(b"\xaa"))
        self.assertTrue(self.errors(case))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO support required")
    def test_fifo_fixture_rejects_without_waiting_for_a_writer(self) -> None:
        fixture = self.root / "conformance/identity/a-empty-scalar.hex"
        fixture.unlink()
        os.mkfifo(fixture)
        outcome: list[list[str]] = []
        worker = threading.Thread(target=lambda: outcome.append(self.errors()), daemon=True)
        worker.start()
        worker.join(0.5)
        self.assertFalse(worker.is_alive(), "fixture open blocked on FIFO")
        self.assertTrue(outcome[0])

    def test_fixture_reader_requires_descriptor_safety_flags(self) -> None:
        with patch.object(registry_module.os, "O_DIRECTORY", None):
            self.assertTrue(any("registry.platform" in error for error in self.errors()))

    def test_stale_materialized_hash_rejects(self) -> None:
        self.assertTrue(self.errors(_case(input_sha256="0" * 64)))

    def test_fixture_inventory_is_bounded_and_fails_on_scan_error(self) -> None:
        with patch.object(registry_module, "MAX_CONFORMANCE_ENTRIES", 1):
            self.assertTrue(self.errors())

        hidden = self.root / "conformance/hidden"
        hidden.mkdir()
        hidden = hidden.resolve()
        real_scandir = os.scandir

        def fail_hidden(path):
            if Path(path) == hidden:
                raise OSError("injected scan failure")
            return real_scandir(path)

        with patch("golden_board.registry.os.scandir", side_effect=fail_hidden):
            errors = self.errors()
        self.assertTrue(any("registry.conformance" in value for value in errors))

    def test_fixture_inventory_rejects_a_mounted_directory_before_scandir(self) -> None:
        conformance = self.root / "conformance"

        def same_mount(_baseline, _descriptor, path: Path) -> bool:
            return path.name != conformance.name

        with (
            patch.object(registry_module, "same_held_mount", side_effect=same_mount),
            patch.object(registry_module.os, "scandir", side_effect=AssertionError("scan")),
        ):
            errors = self.errors()
        self.assertIn("registry.conformance", errors)

    def test_fixture_inventory_rechecks_directory_identity_after_scandir(self) -> None:
        original = registry_module._open_relative_directory
        calls = 0

        def exchange_before_reopen(*args: object, **kwargs: object) -> int:
            nonlocal calls
            parts = args[3]
            if parts == ("conformance",):
                calls += 1
                if calls == 2:
                    conformance = self.root / "conformance"
                    conformance.rename(self.root / "displaced-conformance")
                    conformance.mkdir()
            return original(*args, **kwargs)  # type: ignore[arg-type]

        with patch.object(
            registry_module,
            "_open_relative_directory",
            side_effect=exchange_before_reopen,
        ):
            errors = self.errors()
        self.assertIn("registry.conformance", errors)

    def test_fixture_mount_is_rejected_before_hashing(self) -> None:
        fixture = (self.root / "conformance/identity/a-empty-scalar.hex").resolve()
        case = _case()

        def same_mount(_baseline, _descriptor, path: Path) -> bool:
            return path.resolve() != fixture

        with (
            patch(
                "golden_board.source_lock.same_held_mount",
                side_effect=same_mount,
            ),
            patch.object(
                registry_module.hashlib,
                "sha256",
                side_effect=AssertionError("hash"),
            ),
        ):
            errors = self.errors(case)
        self.assertTrue(any("registry.path" in error for error in errors))

    def test_recipe_schema_is_closed_and_materialization_is_bounded(self) -> None:
        fixture = self.root / "conformance/identity/a-empty-scalar.hex"
        fixture.unlink()
        recipe = self.root / "conformance/manifest/depth.toml"
        recipe.parent.mkdir()
        recipe.write_text('kind = "nested_array"\nlevels = 2\n', encoding="utf-8")
        raw = b"[[0]]\n"
        case = _case(
            id="manifest-depth-two",
            family="manifest",
            operation="manifest",
            input_path="conformance/manifest/depth.toml",
            input_kind="recipe",
            fixture_sha256=_sha(recipe.read_bytes()),
            input_sha256=_sha(raw),
            expected="8327e6ef1e4d52f90f69da8c767d851da34685fd014debe879b84767e03589fc",
            owner="spec/identity-v0.md#7",
        )
        self.assertEqual(raw, _materialize_fixture(self.root, case))
        recipe.write_text('kind = "unknown"\nlevels = 2\n', encoding="utf-8")
        case["fixture_sha256"] = _sha(recipe.read_bytes())
        self.assertTrue(self.errors(case))

    def test_recipe_rejects_huge_repetition_before_multiplication(self) -> None:
        fixture = self.root / "conformance/identity/a-empty-scalar.hex"
        fixture.unlink()
        recipe = self.root / "conformance/manifest/nodes.toml"
        recipe.parent.mkdir()
        recipe.write_text(
            'kind = "repeated_object_member"\n'
            'groups = 1\nitems_per_group = 100000000000000000000\nextra_last = 0\n',
            encoding="utf-8",
        )
        case = _case(
            id="manifest-nodes-huge",
            family="manifest",
            operation="manifest",
            input_path="conformance/manifest/nodes.toml",
            input_kind="recipe",
            fixture_sha256=_sha(recipe.read_bytes()),
            input_sha256="0" * 64,
            expected_kind="diagnostic",
            expected="manifest.limit",
            owner="spec/identity-v0.md#7",
        )
        self.assertTrue(self.errors(case))

        recipe.write_text(
            'kind = "nested_array"\nlevels = ' + "9" * 5_000 + "\n",
            encoding="utf-8",
        )
        case["fixture_sha256"] = _sha(recipe.read_bytes())
        self.assertTrue(self.errors(case))

    def test_recipe_checks_encoded_width_before_repetition(self) -> None:
        raw = (
            b'kind = "repeated_object_member"\n'
            b'groups = 1\nitems_per_group = 18\nextra_last = 0\n'
        )
        original = registry_module._checked_extend

        def bounded_extend(output: bytearray, chunk: bytes) -> None:
            self.assertLessEqual(len(chunk), registry_module.MAX_MATERIALIZED_BYTES - len(output))
            original(output, chunk)

        with (
            patch.object(registry_module, "MAX_MATERIALIZED_BYTES", 32),
            patch.object(registry_module, "_checked_extend", side_effect=bounded_extend),
            self.assertRaises(RegistryError),
        ):
            registry_module._materialize_recipe(raw)


class RegistryProcessTests(unittest.TestCase):
    def test_rust_binary_requires_a_prebuilt_checkout_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            target = root / "artifacts/cargo-target"
            binary = target / "debug/gb-vector"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"binary")
            binary.chmod(0o700)
            self.assertEqual(binary, _rust_binary(root, target))
            binary.unlink()
            with self.assertRaises(RegistryError):
                _rust_binary(root, target)

    def test_default_and_explicit_targets_are_checkout_local_and_nonsymlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            default = root / "target"
            explicit = root / "artifacts/cargo-target"
            default.mkdir()
            explicit.mkdir(parents=True)
            self.assertEqual(default, _validated_target(root, None))
            self.assertEqual(explicit, _validated_target(root, explicit))
            regular = root / "regular-target"
            regular.write_bytes(b"")
            with self.assertRaises(RegistryError):
                _validated_target(root, regular)
            link = root / "linked-target"
            link.symlink_to(explicit, target_is_directory=True)
            with self.assertRaises(RegistryError):
                _validated_target(root, link)

    def test_rust_binary_rejects_a_symlinked_debug_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            target = root / "artifacts/cargo-target"
            outside = root.parent / f"{root.name}-outside-debug"
            outside.mkdir()
            self.addCleanup(outside.rmdir)
            binary = outside / "gb-vector"
            binary.write_bytes(b"binary")
            binary.chmod(0o700)
            self.addCleanup(binary.unlink)
            (target / "debug").parent.mkdir(parents=True)
            (target / "debug").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(RegistryError):
                _rust_binary(root, target)

    def test_bounded_process_reports_timeout_nonzero_and_oversized_streams(self) -> None:
        with self.assertRaisesRegex(RegistryError, "timeout"):
            _run_bounded_process(
                [sys.executable, "-c", "import time; time.sleep(1)"],
                b"",
                {},
                timeout=0.01,
                output_limit=128,
            )
        with self.assertRaisesRegex(RegistryError, "exit"):
            _run_bounded_process(
                [sys.executable, "-c", "raise SystemExit(7)"],
                b"",
                {},
                timeout=1,
                output_limit=128,
            )
        for stream in ("stdout", "stderr"):
            target = "sys.stdout.buffer" if stream == "stdout" else "sys.stderr.buffer"
            with self.subTest(stream=stream), self.assertRaisesRegex(RegistryError, "output"):
                _run_bounded_process(
                    [sys.executable, "-c", f"import sys; {target}.write(b'x'*129)"],
                    b"",
                    {},
                    timeout=1,
                    output_limit=128,
                )

    def test_bounded_process_retries_nonblocking_stdin(self) -> None:
        real_write = os.write
        blocked = False

        def block_once(descriptor, raw):
            nonlocal blocked
            if not blocked:
                blocked = True
                raise BlockingIOError
            return real_write(descriptor, raw)

        with patch("golden_board.registry.os.write", side_effect=block_once):
            stdout, stderr = _run_bounded_process(
                [sys.executable, "-c", "import sys; assert sys.stdin.buffer.read() == b'x'"],
                b"x",
                {},
                timeout=1,
                output_limit=128,
            )
        self.assertTrue(blocked)
        self.assertEqual((b"", b""), (stdout, stderr))

    @unittest.skipUnless(hasattr(os, "killpg"), "process groups required")
    def test_timeout_kills_descendants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pid_path = Path(temporary) / "descendant.pid"
            script = (
                "import pathlib,subprocess,sys,time; "
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
                "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(30)"
            )
            with self.assertRaisesRegex(RegistryError, "timeout"):
                _run_bounded_process(
                    [sys.executable, "-c", script, str(pid_path)],
                    b"",
                    {},
                    timeout=1,
                    output_limit=128,
                )
            descendant = int(pid_path.read_text())
            for _ in range(100):
                try:
                    os.kill(descendant, 0)
                except ProcessLookupError:
                    break
                if sys.platform == "linux":
                    try:
                        state = (
                            Path(f"/proc/{descendant}/stat")
                            .read_text(encoding="ascii")
                            .rsplit(")", 1)[1]
                            .lstrip()[:1]
                        )
                    except FileNotFoundError:
                        break
                    if state == "Z":
                        break
                time.sleep(0.01)
            else:
                self.fail(f"descendant process survived timeout: {descendant}")

    def test_rust_runner_uses_binary_and_operation_only(self) -> None:
        seen: list[object] = []

        def fake(argv, raw, environment, *, timeout, output_limit):
            seen.extend((argv, raw, environment, timeout, output_limit))
            return b"ok\t" + EMPTY_SCALAR.encode() + b"\n", b""

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        binary = root / "artifacts/cargo-target/debug/gb-vector"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"binary")
        binary.chmod(0o700)
        with patch("golden_board.registry._run_bounded_process", side_effect=fake):
            result = _rust_result(root, binary, "identity-a-scalar", b"payload")
        self.assertEqual([str(binary), "identity-a-scalar"], seen[0])
        self.assertEqual(b"payload", seen[1])
        self.assertEqual(f"ok\t{EMPTY_SCALAR}\n", result)

    def test_rust_runner_drops_hostile_environment_and_requires_absolute_binary(self) -> None:
        captured: list[object] = []

        def fake(argv, raw, environment, *, timeout, output_limit):
            captured.extend((argv, raw, environment, timeout, output_limit))
            return b"ok\t" + EMPTY_SCALAR.encode() + b"\n", b""

        hostile = {
            "PATH": "/attacker",
            "LD_PRELOAD": "/attacker/library",
            "RUSTC_WRAPPER": "/attacker/wrapper",
        }
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        binary = root / "artifacts/cargo-target/debug/gb-vector"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"binary")
        binary.chmod(0o700)
        with (
            patch.dict(os.environ, hostile, clear=False),
            patch("golden_board.registry._run_bounded_process", side_effect=fake),
        ):
            _rust_result(root, binary, "identity-a-scalar", b"payload")
        self.assertEqual([str(binary), "identity-a-scalar"], captured[0])
        self.assertEqual(
            {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"}, captured[2]
        )
        with self.assertRaisesRegex(RegistryError, "registry.binary"):
            _rust_result(root, Path("relative/gb-vector"), "identity-a-scalar", b"")

    def test_target_directory_must_be_a_real_checkout_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "conformance").mkdir()
            (root / "conformance/registry.toml").write_text(
                _toml(_registry()), encoding="utf-8"
            )
            outside = root.parent / f"{root.name}-outside"
            outside.mkdir()
            self.addCleanup(outside.rmdir)
            errors = run_registered_vectors(root, outside)
            self.assertTrue(errors)

    def test_target_mount_is_rejected_and_binary_mount_never_executes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            target = root / "artifacts/cargo-target"
            binary = target / "debug/gb-vector"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"binary")
            binary.chmod(0o700)

            def reject_target(_baseline, _descriptor, path: Path) -> bool:
                return path != target

            with (
                patch.object(registry_module, "same_held_mount", side_effect=reject_target),
                self.assertRaisesRegex(RegistryError, "registry.target"),
            ):
                _validated_target(root, target)

            def reject_binary(_baseline, _descriptor, path: Path) -> bool:
                return path != binary

            with (
                patch.object(registry_module, "same_held_mount", side_effect=reject_binary),
                patch.object(
                    registry_module,
                    "_run_bounded_process",
                    side_effect=AssertionError("process"),
                ),
                self.assertRaisesRegex(RegistryError, "registry.binary"),
            ):
                _rust_result(root, binary, "identity-a-scalar", b"payload")


if __name__ == "__main__":
    unittest.main()
