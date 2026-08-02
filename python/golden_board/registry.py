from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import signal
import stat
import subprocess
import time
import tomllib

from golden_board.source_lock import (
    SafeFileError,
    held_mount_identity,
    read_regular_below,
    same_held_mount,
)


MAX_REGISTRY_BYTES = 1 << 20
MAX_FIXTURE_BYTES = 1 << 20
MAX_MATERIALIZED_BYTES = (1 << 24) + 1
MAX_CHILD_OUTPUT = 1 << 10
MAX_CONFORMANCE_ENTRIES = 4_096
CHILD_TIMEOUT = 10.0

_CASE_KEYS = {
    "id",
    "family",
    "operation",
    "input_path",
    "input_kind",
    "fixture_sha256",
    "input_sha256",
    "expected_kind",
    "expected",
    "implementations",
    "owner",
}
_OPERATIONS = {
    "identity": {"identity-a-scalar", "identity-b-scalar", "identity-a-list"},
    "manifest": {"manifest"},
    "source-doctor": {"source-inspect"},
}
_INPUT_KINDS = {"hex", "recipe"}
_EXPECTED_KINDS = {"sha256", "diagnostic"}
_IMPLEMENTATIONS = {"python", "rust"}
_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_DIAGNOSTIC = re.compile(r"[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9_-]*)+\Z")
_OWNER = re.compile(r"[A-Za-z0-9._/-]+#[A-Za-z0-9._-]+\Z")


class RegistryError(ValueError):
    pass


def _identity(value: os.stat_result) -> tuple[int, int, int]:
    return value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode)


def _directory_flags() -> int:
    required = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW")
    if any(type(getattr(os, name, None)) is not int for name in required):
        raise RegistryError("registry.platform")
    return os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW


def _file_flags() -> int:
    required = ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK")
    if any(type(getattr(os, name, None)) is not int for name in required):
        raise RegistryError("registry.platform")
    return os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK


def _open_repository(root: Path, code: str) -> tuple[int, tuple[int, bytes | None]]:
    descriptor: int | None = None
    try:
        descriptor = os.open(root, _directory_flags())
        held = os.fstat(descriptor)
        named = root.lstat()
        mount = held_mount_identity(descriptor)
        if not stat.S_ISDIR(held.st_mode) or _identity(held) != _identity(named):
            raise RegistryError(code)
        return descriptor, mount
    except RegistryError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except (OSError, TypeError, ValueError) as error:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise RegistryError(code) from error


def _open_named_directory(
    parent: int,
    name: str,
    path: Path,
    mount: tuple[int, bytes | None],
    code: str,
) -> int:
    descriptor: int | None = None
    try:
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        descriptor = os.open(name, _directory_flags(), dir_fd=parent)
        held = os.fstat(descriptor)
        after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        path_facts = path.lstat()
        if (
            not stat.S_ISDIR(held.st_mode)
            or _identity(before) != _identity(held)
            or _identity(after) != _identity(held)
            or _identity(path_facts) != _identity(held)
            or not same_held_mount(mount, descriptor, path)
        ):
            raise RegistryError(code)
        return descriptor
    except RegistryError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except (OSError, TypeError, ValueError) as error:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise RegistryError(code) from error


def _open_relative_directory(
    repository: int,
    root: Path,
    mount: tuple[int, bytes | None],
    parts: tuple[str, ...],
    code: str,
) -> int:
    parent = repository
    owned: int | None = None
    current = root
    try:
        for part in parts:
            current /= part
            child = _open_named_directory(parent, part, current, mount, code)
            if owned is not None:
                os.close(owned)
            owned = child
            parent = child
        if owned is None:
            raise RegistryError(code)
        return owned
    except BaseException:
        if owned is not None:
            try:
                os.close(owned)
            except OSError:
                pass
        raise


def _open_named_regular(
    parent: int,
    name: str,
    path: Path,
    mount: tuple[int, bytes | None],
    code: str,
) -> int:
    descriptor: int | None = None
    try:
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        descriptor = os.open(name, _file_flags(), dir_fd=parent)
        held = os.fstat(descriptor)
        after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISREG(held.st_mode)
            or _identity(before) != _identity(held)
            or _identity(after) != _identity(held)
            or _identity(path.lstat()) != _identity(held)
            or not same_held_mount(mount, descriptor, path)
        ):
            raise RegistryError(code)
        return descriptor
    except RegistryError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except (OSError, TypeError, ValueError) as error:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise RegistryError(code) from error


def _registry_file_error(error: SafeFileError) -> RegistryError:
    code = {
        "safe_file.capability": "registry.platform",
        "safe_file.type": "registry.nonregular",
        "safe_file.limit": "registry.fixture_limit",
        "safe_file.changed": "registry.changed",
    }.get(str(error), "registry.path")
    return RegistryError(code)


def _path_parts(value: object) -> tuple[str, ...]:
    if type(value) is not str or not value or any(character in value for character in ("\0", "\\")):
        raise RegistryError("registry.path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        raise RegistryError("registry.path")
    return path.parts


def _schema_errors(registry: object) -> list[str]:
    if type(registry) is not dict or set(registry) != {"schema_version", "case"}:
        return ["registry.schema"]
    if type(registry["schema_version"]) is not int or registry["schema_version"] != 0:
        return ["registry.schema_version"]
    cases = registry["case"]
    if type(cases) is not list or not cases:
        return ["registry.case"]

    errors: list[str] = []
    identifiers: set[str] = set()
    for index, case in enumerate(cases):
        prefix = f"case[{index}]"
        if type(case) is not dict or set(case) != _CASE_KEYS:
            errors.append(f"{prefix}: registry.schema")
            continue
        identifier = case["id"]
        if type(identifier) is not str or _ID.fullmatch(identifier) is None:
            errors.append(f"{prefix}: registry.id")
        elif identifier in identifiers:
            errors.append(f"{prefix}: registry.duplicate_id")
        else:
            identifiers.add(identifier)

        family = case["family"]
        operation = case["operation"]
        if type(family) is not str or family not in _OPERATIONS:
            errors.append(f"{prefix}: registry.family")
        elif type(operation) is not str or operation not in _OPERATIONS[family]:
            errors.append(f"{prefix}: registry.operation")

        if type(case["input_kind"]) is not str or case["input_kind"] not in _INPUT_KINDS:
            errors.append(f"{prefix}: registry.input_kind")
        try:
            parts = _path_parts(case["input_path"])
            expected_directory = "source-doctor" if family == "source-doctor" else family
            if len(parts) < 3 or parts[:2] != ("conformance", expected_directory):
                errors.append(f"{prefix}: registry.path")
            suffix = ".hex" if case["input_kind"] == "hex" else ".toml"
            if not parts[-1].endswith(suffix):
                errors.append(f"{prefix}: registry.path")
        except RegistryError:
            errors.append(f"{prefix}: registry.path")

        for key in ("fixture_sha256", "input_sha256"):
            if type(case[key]) is not str or _SHA256.fullmatch(case[key]) is None:
                errors.append(f"{prefix}: registry.{key}")
        expected_kind = case["expected_kind"]
        expected = case["expected"]
        if type(expected_kind) is not str or expected_kind not in _EXPECTED_KINDS:
            errors.append(f"{prefix}: registry.expected_kind")
        elif expected_kind == "sha256" and (type(expected) is not str or _SHA256.fullmatch(expected) is None):
            errors.append(f"{prefix}: registry.expected")
        elif expected_kind == "diagnostic" and (
            type(expected) is not str or _DIAGNOSTIC.fullmatch(expected) is None
        ):
            errors.append(f"{prefix}: registry.expected")

        implementations = case["implementations"]
        if (
            type(implementations) is not list
            or not implementations
            or any(type(value) is not str or value not in _IMPLEMENTATIONS for value in implementations)
            or len(set(implementations)) != len(implementations)
            or implementations != sorted(implementations)
        ):
            errors.append(f"{prefix}: registry.implementations")
        elif family == "source-doctor" and implementations != ["python"]:
            errors.append(f"{prefix}: registry.implementations")
        elif (
            type(family) is str
            and family in {"identity", "manifest"}
            and implementations != ["python", "rust"]
        ):
            errors.append(f"{prefix}: registry.implementations")

        if type(case["owner"]) is not str or _OWNER.fullmatch(case["owner"]) is None:
            errors.append(f"{prefix}: registry.owner")
    return errors


def load_registry(path: Path) -> dict[str, object]:
    try:
        if (
            not isinstance(path, Path)
            or not path.is_absolute()
            or path.name != "registry.toml"
            or path.parent.name != "conformance"
            or "\0" in os.fspath(path)
            or "\\" in os.fspath(path)
            or ".." in path.parts
        ):
            raise RegistryError("registry.path")
        root = path.parent.parent.resolve(strict=True)
        try:
            raw = read_regular_below(
                root,
                PurePosixPath("conformance/registry.toml"),
                MAX_REGISTRY_BYTES,
            )
        except SafeFileError as error:
            raise _registry_file_error(error) from error
        if raw.startswith(b"\xef\xbb\xbf"):
            raise RegistryError("registry.utf8")
        parsed = tomllib.loads(raw.decode("utf-8", "strict"))
    except RegistryError:
        raise
    except (
        UnicodeDecodeError,
        tomllib.TOMLDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise RegistryError("registry.syntax") from error
    errors = _schema_errors(parsed)
    if errors:
        raise RegistryError(errors[0])
    parsed["case"] = sorted(parsed["case"], key=lambda case: case["id"])
    return parsed


def _checked_extend(output: bytearray, chunk: bytes) -> None:
    if len(chunk) > MAX_MATERIALIZED_BYTES - len(output):
        raise RegistryError("registry.materialized_limit")
    output.extend(chunk)


def _recipe_integer(recipe: dict[str, object], name: str) -> int:
    value = recipe[name]
    if type(value) is not int or value < 0:
        raise RegistryError("registry.recipe")
    return value


def _materialize_recipe(raw: bytes) -> bytes:
    try:
        if raw.startswith(b"\xef\xbb\xbf"):
            raise RegistryError("registry.recipe")
        recipe = tomllib.loads(raw.decode("utf-8", "strict"))
    except (
        UnicodeDecodeError,
        tomllib.TOMLDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise RegistryError("registry.recipe") from error
    if type(recipe) is not dict or type(recipe.get("kind")) is not str:
        raise RegistryError("registry.recipe")
    kind = recipe["kind"]
    if kind == "nested_array" and set(recipe) == {"kind", "levels"}:
        levels = _recipe_integer(recipe, "levels")
        if 2 * levels + 2 > MAX_MATERIALIZED_BYTES:
            raise RegistryError("registry.materialized_limit")
        return b"[" * levels + b"0" + b"]" * levels + b"\n"
    if kind == "repeated_array_zero" and set(recipe) == {"kind", "count"}:
        count = _recipe_integer(recipe, "count")
        length = 3 if count == 0 else 2 * count + 2
        if length > MAX_MATERIALIZED_BYTES:
            raise RegistryError("registry.materialized_limit")
        return b"[]\n" if count == 0 else b"[" + b"0," * (count - 1) + b"0]\n"
    if kind == "ascii_string_document" and set(recipe) == {"kind", "string_bytes"}:
        count = _recipe_integer(recipe, "string_bytes")
        if count + 3 > MAX_MATERIALIZED_BYTES:
            raise RegistryError("registry.materialized_limit")
        return b'"' + b"a" * count + b'"\n'
    if kind == "repeated_object_member" and set(recipe) == {
        "kind",
        "groups",
        "items_per_group",
        "extra_last",
    }:
        groups = _recipe_integer(recipe, "groups")
        items = _recipe_integer(recipe, "items_per_group")
        extra = _recipe_integer(recipe, "extra_last")
        if groups == 0 or max(groups, items, extra) > MAX_MATERIALIZED_BYTES:
            raise RegistryError("registry.recipe")
        output = bytearray(b"{")
        for group in range(groups):
            if group:
                _checked_extend(output, b",")
            _checked_extend(output, f'"g{group:02}":['.encode("ascii"))
            width = items + (extra if group == groups - 1 else 0)
            if width > MAX_MATERIALIZED_BYTES:
                raise RegistryError("registry.materialized_limit")
            if width:
                encoded_length = 2 * width - 1
                if encoded_length > MAX_MATERIALIZED_BYTES - len(output):
                    raise RegistryError("registry.materialized_limit")
                _checked_extend(output, b"0," * (width - 1))
                _checked_extend(output, b"0")
            _checked_extend(output, b"]")
        _checked_extend(output, b"}\n")
        return bytes(output)
    raise RegistryError("registry.recipe")


def _materialize_fixture(root: Path, case: dict[str, object]) -> bytes:
    try:
        fixture = read_regular_below(
            root,
            PurePosixPath(case["input_path"]),
            MAX_FIXTURE_BYTES,
        )
    except SafeFileError as error:
        raise _registry_file_error(error) from error
    if hashlib.sha256(fixture).hexdigest() != case["fixture_sha256"]:
        raise RegistryError("registry.fixture_hash")
    if case["input_kind"] == "hex":
        if not fixture.endswith(b"\n") or b"\n" in fixture[:-1]:
            raise RegistryError("registry.hex")
        body = fixture[:-1]
        if len(body) % 2 or any(byte not in b"0123456789abcdef" for byte in body):
            raise RegistryError("registry.hex")
        materialized = bytes.fromhex(body.decode("ascii"))
    else:
        materialized = _materialize_recipe(fixture)
    if len(materialized) > MAX_MATERIALIZED_BYTES:
        raise RegistryError("registry.materialized_limit")
    if hashlib.sha256(materialized).hexdigest() != case["input_sha256"]:
        raise RegistryError("registry.input_hash")
    return materialized


def _tracked_fixtures(root: Path) -> set[str]:
    root = root.resolve(strict=True)
    repository: int | None = None
    try:
        repository, mount = _open_repository(root, "registry.conformance")
        result: set[str] = set()
        pending = [("conformance",)]
        entries = 0
        while pending:
            parts = pending.pop()
            directory = _open_relative_directory(
                repository,
                root,
                mount,
                parts,
                "registry.conformance",
            )
            try:
                with os.scandir(directory) as children:
                    for child in children:
                        entries += 1
                        if entries > MAX_CONFORMANCE_ENTRIES:
                            raise RegistryError("registry.fixture_limit")
                        name = child.name
                        if (
                            type(name) is not str
                            or not name
                            or name in {".", ".."}
                            or "/" in name
                            or "\0" in name
                        ):
                            raise RegistryError("registry.conformance")
                        relative_parts = parts + (name,)
                        path = root.joinpath(*relative_parts)
                        relative = PurePosixPath(*relative_parts).as_posix()
                        facts = os.stat(
                            name,
                            dir_fd=directory,
                            follow_symlinks=False,
                        )
                        if stat.S_ISLNK(facts.st_mode):
                            result.add(relative)
                        elif stat.S_ISDIR(facts.st_mode):
                            child_descriptor = _open_named_directory(
                                directory,
                                name,
                                path,
                                mount,
                                "registry.conformance",
                            )
                            os.close(child_descriptor)
                            pending.append(relative_parts)
                        elif stat.S_ISREG(facts.st_mode):
                            child_descriptor = _open_named_regular(
                                directory,
                                name,
                                path,
                                mount,
                                "registry.conformance",
                            )
                            os.close(child_descriptor)
                            if relative != "conformance/registry.toml":
                                result.add(relative)
                        elif relative != "conformance/registry.toml":
                            result.add(relative)
                current_directory = _open_relative_directory(
                    repository,
                    root,
                    mount,
                    parts,
                    "registry.conformance",
                )
                try:
                    if _identity(os.fstat(directory)) != _identity(
                        os.fstat(current_directory)
                    ):
                        raise RegistryError("registry.conformance")
                finally:
                    os.close(current_directory)
            finally:
                os.close(directory)
        if _identity(os.fstat(repository)) != _identity(root.lstat()):
            raise RegistryError("registry.conformance")
        return result
    except RegistryError:
        raise
    except (OSError, TypeError, ValueError) as error:
        raise RegistryError("registry.conformance") from error
    finally:
        if repository is not None:
            try:
                os.close(repository)
            except OSError:
                pass


def validate_registry(root: Path, registry: dict[str, object]) -> list[str]:
    errors = _schema_errors(registry)
    if errors:
        return errors
    root = root.resolve()
    cases = sorted(registry["case"], key=lambda case: case["id"])
    expected_paths = {case["input_path"] for case in cases}
    for case in cases:
        try:
            _materialize_fixture(root, case)
        except RegistryError as error:
            errors.append(f"{case['id']}: {error}")
    try:
        actual_paths = _tracked_fixtures(root)
        for path in sorted(expected_paths - actual_paths):
            errors.append(f"missing fixture: {path}")
        for path in sorted(actual_paths - expected_paths):
            errors.append(f"unregistered fixture: {path}")
    except RegistryError as error:
        errors.append(str(error))
    return errors


def _run_bounded_process(
    argv: list[str],
    raw: bytes,
    environment: dict[str, str],
    *,
    timeout: float,
    output_limit: int,
    cwd: Path | None = None,
) -> tuple[bytes, bytes]:
    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=environment,
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as error:
        raise RegistryError("registry.process_start") from error
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    streams = {"stdout": bytearray(), "stderr": bytearray()}
    selector = selectors.DefaultSelector()
    completed = False
    try:
        input_offset = 0
        for pipe in (process.stdin, process.stdout, process.stderr):
            os.set_blocking(pipe.fileno(), False)
        if raw:
            selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
        else:
            process.stdin.close()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        deadline = time.monotonic() + timeout
        failure: RegistryError | None = None
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = RegistryError("registry.process_timeout")
                break
            events = selector.select(min(remaining, 0.1))
            for key, _ in events:
                stream = key.fileobj
                name = key.data
                if name == "stdin":
                    try:
                        written = os.write(stream.fileno(), raw[input_offset : input_offset + 65_536])
                        input_offset += written
                    except BlockingIOError:
                        continue
                    except BrokenPipeError:
                        input_offset = len(raw)
                    if input_offset == len(raw):
                        selector.unregister(stream)
                        stream.close()
                    continue
                try:
                    chunk = os.read(stream.fileno(), min(65_536, output_limit + 1 - len(streams[name])))
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue
                streams[name].extend(chunk)
                if len(streams[name]) > output_limit:
                    failure = RegistryError("registry.process_output")
                    break
            if failure is not None:
                break
        if failure is not None:
            raise failure
        remaining = max(0.0, deadline - time.monotonic())
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            raise RegistryError("registry.process_timeout") from error
        if returncode != 0:
            raise RegistryError(f"registry.process_exit:{returncode}")
        completed = True
        return bytes(streams["stdout"]), bytes(streams["stderr"])
    finally:
        selector.close()
        if not completed:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError:
                if process.poll() is None:
                    process.kill()
            process.wait()
        for pipe in (process.stdin, process.stdout, process.stderr):
            if not pipe.closed:
                pipe.close()


def _identity_list(raw: bytes) -> list[bytes]:
    if len(raw) < 2:
        raise RegistryError("adapter.framing")
    count = int.from_bytes(raw[:2], "big")
    offset = 2
    result: list[bytes] = []
    for _ in range(count):
        if offset + 4 > len(raw):
            raise RegistryError("adapter.framing")
        length = int.from_bytes(raw[offset : offset + 4], "big")
        offset += 4
        if length > len(raw) - offset:
            raise RegistryError("adapter.framing")
        result.append(raw[offset : offset + length])
        offset += length
    if offset != len(raw):
        raise RegistryError("adapter.framing")
    return result


def _python_result(operation: str, raw: bytes) -> str:
    from golden_board.constants import IDENTITY_TEST_A, IDENTITY_TEST_B
    from golden_board.identity import list_preimage, scalar_preimage, sha256_hex
    from golden_board.manifest import ManifestError, canonical_manifest_hash, encode_canonical_value

    if operation == "identity-a-scalar":
        digest = sha256_hex(scalar_preimage(IDENTITY_TEST_A, raw))
    elif operation == "identity-b-scalar":
        digest = sha256_hex(scalar_preimage(IDENTITY_TEST_B, raw))
    elif operation == "identity-a-list":
        digest = sha256_hex(list_preimage(IDENTITY_TEST_A, _identity_list(raw)))
    elif operation == "manifest":
        try:
            digest = canonical_manifest_hash(raw)
        except ManifestError as error:
            return f"err\t{error.code}\n"
    elif operation == "source-inspect":
        from golden_board.source_doctor import SourceDoctorError, inspect_source

        try:
            facts = inspect_source(raw)
        except SourceDoctorError as error:
            return f"err\t{error.code}\n"
        digest = hashlib.sha256(encode_canonical_value(facts)).hexdigest()
    else:
        raise RegistryError("registry.operation")
    return f"ok\t{digest}\n"


def _minimal_environment() -> dict[str, str]:
    return {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"}


def _held_binary(
    root: Path,
    binary: Path,
) -> tuple[int, tuple[int, bytes | None]]:
    root = root.resolve(strict=True)
    if (
        not isinstance(binary, Path)
        or not binary.is_absolute()
        or "\0" in os.fspath(binary)
        or ".." in binary.parts
    ):
        raise RegistryError("registry.binary")
    try:
        relative = binary.relative_to(root)
    except ValueError as error:
        raise RegistryError("registry.binary") from error
    if not relative.parts or relative.name != "gb-vector":
        raise RegistryError("registry.binary")
    repository: int | None = None
    parent: int | None = None
    descriptor: int | None = None
    try:
        repository, mount = _open_repository(root, "registry.binary")
        parent = _open_relative_directory(
            repository,
            root,
            mount,
            relative.parts[:-1],
            "registry.binary",
        )
        descriptor = _open_named_regular(
            parent,
            relative.name,
            binary,
            mount,
            "registry.binary",
        )
        if os.fstat(descriptor).st_mode & 0o111 == 0:
            raise RegistryError("registry.binary")
        return descriptor, mount
    except BaseException:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    finally:
        if parent is not None:
            try:
                os.close(parent)
            except OSError:
                pass
        if repository is not None:
            try:
                os.close(repository)
            except OSError:
                pass


def _rust_result(root: Path, binary: Path, operation: str, raw: bytes) -> str:
    if (
        not isinstance(root, Path)
        or not isinstance(binary, Path)
        or not binary.is_absolute()
    ):
        raise RegistryError("registry.binary")
    if operation not in _OPERATIONS["identity"] | _OPERATIONS["manifest"]:
        raise RegistryError("registry.operation")
    descriptor, mount = _held_binary(root, binary)
    try:
        held = os.fstat(descriptor)
        named = binary.lstat()
        if (
            _identity(held) != _identity(named)
            or not same_held_mount(mount, descriptor, binary)
        ):
            raise RegistryError("registry.binary")
        stdout, stderr = _run_bounded_process(
            [str(binary), operation],
            raw,
            _minimal_environment(),
            timeout=CHILD_TIMEOUT,
            output_limit=MAX_CHILD_OUTPUT,
        )
    finally:
        os.close(descriptor)
    if stderr:
        raise RegistryError("registry.rust_stderr")
    try:
        result = stdout.decode("ascii", "strict")
    except UnicodeDecodeError as error:
        raise RegistryError("registry.rust_output") from error
    if re.fullmatch(r"(?:ok\t[0-9a-f]{64}|err\t[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+)\n", result) is None:
        raise RegistryError("registry.rust_output")
    return result


def _validated_target(root: Path, target_dir: Path | None) -> Path:
    root = root.resolve(strict=True)
    candidate = root / "target" if target_dir is None else Path(target_dir)
    candidate = candidate if candidate.is_absolute() else root / candidate
    try:
        absolute = candidate.absolute()
        relative = absolute.relative_to(root)
    except ValueError as error:
        raise RegistryError("registry.target") from error
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise RegistryError("registry.target")
    repository: int | None = None
    current_descriptor: int | None = None
    try:
        repository, mount = _open_repository(root, "registry.target")
        parent = repository
        current = root
        for part in relative.parts:
            current /= part
            try:
                os.stat(part, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                break
            child = _open_named_directory(
                parent,
                part,
                current,
                mount,
                "registry.target",
            )
            if current_descriptor is not None:
                os.close(current_descriptor)
            current_descriptor = child
            parent = child
        if _identity(os.fstat(repository)) != _identity(root.lstat()):
            raise RegistryError("registry.target")
        return absolute
    finally:
        if current_descriptor is not None:
            try:
                os.close(current_descriptor)
            except OSError:
                pass
        if repository is not None:
            try:
                os.close(repository)
            except OSError:
                pass


def _rust_binary(root: Path, target_dir: Path | None = None) -> Path:
    root = root.resolve(strict=True)
    target = _validated_target(root, target_dir)
    debug = _validated_target(root, target / "debug")
    binary = debug / "gb-vector"
    descriptor, _mount = _held_binary(root, binary)
    os.close(descriptor)
    return binary


def _expected(case: dict[str, object]) -> str:
    prefix = "ok" if case["expected_kind"] == "sha256" else "err"
    return f"{prefix}\t{case['expected']}\n"


def run_registered_vectors(
    root: Path,
    target_dir: Path | None = None,
    *,
    families: set[str] | None = None,
) -> list[str]:
    root = root.resolve()
    if families is not None and (
        type(families) is not set
        or any(type(family) is not str for family in families)
        or not families <= set(_OPERATIONS)
    ):
        return ["registry.family"]
    try:
        registry = load_registry(root / "conformance/registry.toml")
    except RegistryError as error:
        return [str(error)]
    errors = validate_registry(root, registry)
    if errors:
        return errors
    cases = [
        case
        for case in registry["case"]
        if families is None or case["family"] in families
    ]
    binary: Path | None = None
    if any("rust" in case["implementations"] for case in cases):
        try:
            binary = _rust_binary(root, target_dir)
        except RegistryError as error:
            return [str(error)]
    for case in cases:
        try:
            raw = _materialize_fixture(root, case)
        except RegistryError as error:
            errors.append(f"{case['id']}: {error}")
            continue
        expected = _expected(case)
        for implementation in case["implementations"]:
            try:
                actual = (
                    _python_result(case["operation"], raw)
                    if implementation == "python"
                    else _rust_result(
                        root,
                        binary if binary is not None else Path(),
                        case["operation"],
                        raw,
                    )
                )
            except (RegistryError, OSError, ValueError) as error:
                errors.append(f"{case['id']}:{implementation}: {error}")
                continue
            if actual != expected:
                errors.append(f"{case['id']}:{implementation}: expected {expected.strip()}, got {actual.strip()}")
    return errors
