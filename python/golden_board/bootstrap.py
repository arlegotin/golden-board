from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
from collections.abc import Callable, Sequence
from types import SimpleNamespace


_BOOTSTRAP_FILE = Path(__file__)
_PACKAGE_DIRECTORY = _BOOTSTRAP_FILE.parent
_PYTHON_DIRECTORY = _PACKAGE_DIRECTORY.parent
_IMPORT_SOURCE_LIMIT = 4 * 1024 * 1024
_IMPORT_SOURCE_COUNT = 64
_BOOTSTRAP_FDINFO_MAX_BYTES = 4096
_TRUSTED_SOURCE_SHA256 = {
    "__init__.py": "cc4532ec9eca51ea23edb9b88fa332448cef1a6908a07f940bf52c22c123ad02",
    "acquisition.py": "779931e37c44fb41d95003e6b96b01ce76c37c79ef7feab36951b5303bcd9697",
    "checks.py": "85b21122426e057c17b6b8e13fd457ed2ede4cc52e9549823e0661bd9398bd72",
    "clean.py": "4490ab13e596b869b5a34c4488c44981f3f910394a10994616f9e125d52fbd92",
    "cli.py": "18dacad30886be0621b8b4ab13a1d838006035e69ab178b89b0551897db65e05",
    "constants.py": "be8d252b08478d6d72604c2b8048a68b0648f186a74dd363dceabd955a0b06c3",
    "identity.py": "93af1f118c1a339d77ed63c30d46eef70422fb6d17822f3c561e3f27b355050d",
    "manifest.py": "a433d8357ef3b5ce65866509e5dab328de786dfc5abd0a7a8aeb9052469efb07",
    "reference_acquisition.py": "690b253982beea96533b1983204ef07f398d4f418e1e1151a1af509b8597eea9",
    "registry.py": "4fabae6eca56e9193d4cfb517566ed773275932bfdf0c733be0b31c8421b27c5",
    "reports.py": "a2ec2f0cc564133bbdd8512772ed24a2dccf313c1f60e1fe1107750d86845095",
    "source_doctor.py": "d3c61565fe8dfd3909eb17fa46abadebac2165e60234d4c020e7a1d8d7df4f0f",
    "source_lock.py": "b360e9c3a3ab7bdc409232c48be78b75ac647a21f16ee2aa7385adc2a0d1c950",
    "status.py": "629360012eff93807dc599843132fb8e6b68f9f94223562b5293c4679198b66b",
}


def _file_facts(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _identity_facts(value: os.stat_result) -> tuple[int, int, int]:
    return (value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode))


def _bootstrap_linux_mount_id(descriptor: int) -> bytes:
    required = ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK")
    if any(type(getattr(os, name, None)) is not int for name in required):
        raise OSError("mount identity capability")
    before = os.fstat(descriptor)
    fdinfo: int | None = None
    raw = bytearray()
    try:
        fdinfo = os.open(
            f"/proc/self/fdinfo/{descriptor}",
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
        )
        while len(raw) <= _BOOTSTRAP_FDINFO_MAX_BYTES:
            chunk = os.read(
                fdinfo,
                min(1024, _BOOTSTRAP_FDINFO_MAX_BYTES + 1 - len(raw)),
            )
            if not chunk:
                break
            raw.extend(chunk)
    finally:
        if fdinfo is not None:
            os.close(fdinfo)
    after = os.fstat(descriptor)
    data = bytes(raw)
    matches = [
        line.removeprefix(b"mnt_id:\t")
        for line in data.splitlines()
        if line.startswith(b"mnt_id:")
    ]
    if (
        len(data) > _BOOTSTRAP_FDINFO_MAX_BYTES
        or not data.endswith(b"\n")
        or _identity_facts(before) != _identity_facts(after)
        or len(matches) != 1
        or re.fullmatch(rb"[1-9][0-9]{0,19}", matches[0]) is None
    ):
        raise OSError("mount identity syntax")
    return matches[0]


def _bootstrap_mount_identity(descriptor: int) -> tuple[int, bytes | None]:
    before = os.fstat(descriptor)
    if sys.platform == "linux":
        mount_id: bytes | None = _bootstrap_linux_mount_id(descriptor)
    elif sys.platform == "darwin":
        mount_id = None
    else:
        raise OSError("unsupported mount identity platform")
    after = os.fstat(descriptor)
    if _identity_facts(before) != _identity_facts(after):
        raise OSError("mount identity changed")
    return before.st_dev, mount_id


def _bootstrap_same_held_mount(
    repository_mount: tuple[int, bytes | None],
    descendant_descriptor: int,
    descendant_path: Path,
) -> bool:
    try:
        before = os.fstat(descendant_descriptor)
        if repository_mount[0] != before.st_dev:
            return False
        if sys.platform == "linux":
            same = repository_mount[1] == _bootstrap_linux_mount_id(
                descendant_descriptor
            )
        elif sys.platform == "darwin":
            same = repository_mount[1] is None and not os.path.ismount(descendant_path)
        else:
            return False
        return bool(
            same
            and _identity_facts(before)
            == _identity_facts(os.fstat(descendant_descriptor))
        )
    except OSError, TypeError, ValueError:
        return False


def _prepare_import_cache() -> Path:
    try:
        path = Path(
            tempfile.mkdtemp(prefix="golden-board-bootstrap-", dir="/tmp")
        ).resolve(strict=True)
        mode = path.lstat().st_mode
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        try:
            if (
                not stat.S_ISDIR(mode)
                or mode & 0o077
                or os.fstat(descriptor).st_uid != os.geteuid()
                or os.listdir(descriptor)
            ):
                raise OSError("unsafe import cache")
        finally:
            os.close(descriptor)
    except OSError as error:
        raise RuntimeError("unsafe bootstrap import cache") from error
    sys.dont_write_bytecode = True
    sys.pycache_prefix = str(path)
    return path


def _discard_import_cache(path: Path) -> None:
    try:
        facts = path.lstat()
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        try:
            if (
                not stat.S_ISDIR(facts.st_mode)
                or facts.st_mode & 0o077
                or os.fstat(descriptor).st_uid != os.geteuid()
                or os.listdir(descriptor)
            ):
                raise OSError("unsafe import cache")
        finally:
            os.close(descriptor)
        os.rmdir(path)
    except OSError as error:
        raise RuntimeError("cannot close bootstrap import cache") from error


def _validate_import_sources(
    python_directory: Path,
) -> dict[str, tuple[int, int, int, int, int, int]]:
    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptors: list[int] = []
    source_facts: dict[str, tuple[int, int, int, int, int, int]] = {}
    try:
        if (
            not python_directory.is_absolute()
            or python_directory.resolve(strict=True) != python_directory
            or stat.S_ISLNK(python_directory.lstat().st_mode)
        ):
            raise OSError("unsafe Python source root")
        repository_descriptor = os.open(python_directory.parent, directory_flags)
        descriptors.append(repository_descriptor)
        repository_mount = _bootstrap_mount_identity(repository_descriptor)
        python_descriptor = os.open(
            python_directory.name,
            directory_flags,
            dir_fd=repository_descriptor,
        )
        descriptors.append(python_descriptor)
        if not _bootstrap_same_held_mount(
            repository_mount, python_descriptor, python_directory
        ):
            raise OSError("unsafe Python source root mount")
        with os.scandir(python_descriptor) as iterator:
            root_names: list[str] = []
            for entry in iterator:
                if len(root_names) >= 3:
                    raise OSError("too many Python root entries")
                root_names.append(entry.name)
        if set(root_names) != {"golden_board", "tests"}:
            raise OSError("unexpected Python root entry")
        for name in ("golden_board", "tests"):
            linked = os.stat(name, dir_fd=python_descriptor, follow_symlinks=False)
            child = os.open(name, directory_flags, dir_fd=python_descriptor)
            try:
                opened = os.fstat(child)
                if (
                    not stat.S_ISDIR(opened.st_mode)
                    or not _bootstrap_same_held_mount(
                        repository_mount, child, python_directory / name
                    )
                    or _identity_facts(opened) != _identity_facts(linked)
                ):
                    raise OSError("unsafe Python root directory")
            finally:
                os.close(child)
        package_descriptor = os.open(
            "golden_board", directory_flags, dir_fd=python_descriptor
        )
        descriptors.append(package_descriptor)
        if (
            not _bootstrap_same_held_mount(
                repository_mount,
                package_descriptor,
                python_directory / "golden_board",
            )
            or os.fstat(python_descriptor).st_mode & 0o022
            or os.fstat(package_descriptor).st_mode & 0o022
        ):
            raise OSError("writable Python source directory")
        with os.scandir(package_descriptor) as iterator:
            names: list[str] = []
            for entry in iterator:
                if len(names) >= _IMPORT_SOURCE_COUNT:
                    raise OSError("too many Python source entries")
                names.append(entry.name)
        allowed_sources = set(_TRUSTED_SOURCE_SHA256) | {"bootstrap.py"}
        if set(names) - allowed_sources - {"__pycache__"}:
            raise OSError("unexpected Python package entry")
        if "__pycache__" in names:
            cache = os.stat(
                "__pycache__", dir_fd=package_descriptor, follow_symlinks=False
            )
            if not stat.S_ISDIR(cache.st_mode):
                raise OSError("unsafe local Python cache")
            cache_descriptor = os.open(
                "__pycache__",
                directory_flags,
                dir_fd=package_descriptor,
            )
            try:
                if not _bootstrap_same_held_mount(
                    repository_mount,
                    cache_descriptor,
                    python_directory / "golden_board/__pycache__",
                ) or _identity_facts(os.fstat(cache_descriptor)) != _identity_facts(
                    cache
                ):
                    raise OSError("changed local Python cache")
            finally:
                os.close(cache_descriptor)
        sources: set[str] = set()
        for name in names:
            if not name.endswith(".py"):
                continue
            if re.fullmatch(r"[a-z_][a-z0-9_]*\.py", name) is None:
                raise OSError("unsafe Python source name")
            descriptor = os.open(name, file_flags, dir_fd=package_descriptor)
            descriptors.append(descriptor)
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or not _bootstrap_same_held_mount(
                    repository_mount,
                    descriptor,
                    python_directory / "golden_board" / name,
                )
                or before.st_mode & 0o022
                or before.st_size > _IMPORT_SOURCE_LIMIT
            ):
                raise OSError("unsafe Python source")
            remaining = before.st_size
            digest = hashlib.sha256()
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    raise OSError("short Python source")
                digest.update(chunk)
                remaining -= len(chunk)
            after = os.fstat(descriptor)
            current = os.stat(name, dir_fd=package_descriptor, follow_symlinks=False)
            if _file_facts(before) != _file_facts(after) or _file_facts(
                after
            ) != _file_facts(current):
                raise OSError("changed Python source")
            if (
                name != "bootstrap.py"
                and digest.hexdigest() != _TRUSTED_SOURCE_SHA256.get(name)
            ):
                raise OSError("untrusted Python source")
            sources.add(name)
            source_facts[name] = _file_facts(after)
        if sources != allowed_sources:
            raise OSError("unexpected Python source set")
    except OSError as error:
        raise RuntimeError("unsafe bootstrap source tree") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    return source_facts


try:
    if not _BOOTSTRAP_FILE.is_absolute():
        raise OSError("bootstrap path is not absolute")
    file_mode = _BOOTSTRAP_FILE.lstat().st_mode
    package_mode = _PACKAGE_DIRECTORY.lstat().st_mode
    python_mode = _PYTHON_DIRECTORY.lstat().st_mode
    if (
        stat.S_ISLNK(file_mode)
        or not stat.S_ISREG(file_mode)
        or file_mode & 0o022
        or stat.S_ISLNK(package_mode)
        or not stat.S_ISDIR(package_mode)
        or package_mode & 0o022
        or stat.S_ISLNK(python_mode)
        or not stat.S_ISDIR(python_mode)
        or python_mode & 0o022
        or _BOOTSTRAP_FILE.resolve(strict=True) != _BOOTSTRAP_FILE
        or _PACKAGE_DIRECTORY.resolve(strict=True) != _PACKAGE_DIRECTORY
        or _PYTHON_DIRECTORY.resolve(strict=True) != _PYTHON_DIRECTORY
    ):
        raise OSError("unsafe bootstrap module path")
except OSError as error:
    raise RuntimeError("unsafe bootstrap import root") from error

_IMPORT_CACHE = _prepare_import_cache()
try:
    _IMPORT_SOURCE_FACTS = _validate_import_sources(_PYTHON_DIRECTORY)
    sys.path.insert(0, str(_PYTHON_DIRECTORY))

    from golden_board.acquisition import (
        build_inventory,
        load_inventory,
        write_inventory,
    )
    from golden_board.reports import ReportError, git_control_preflight
    from golden_board.registry import RegistryError, _run_bounded_process
    from golden_board.source_lock import (
        SafeFileError,
        held_mount_identity,
        load_source_lock,
        read_regular_below,
        resolve_same_mount_path,
        same_held_mount,
    )

    if _validate_import_sources(_PYTHON_DIRECTORY) != _IMPORT_SOURCE_FACTS:
        raise RuntimeError("bootstrap source tree changed during import")
finally:
    _discard_import_cache(_IMPORT_CACHE)


class BootstrapError(ValueError):
    pass


RUNTIME_DIRECTORIES = (
    PurePosixPath("artifacts"),
    PurePosixPath("artifacts/cargo-home"),
    PurePosixPath("artifacts/cargo-target"),
    PurePosixPath("artifacts/check-home"),
    PurePosixPath("artifacts/check-pycache"),
    PurePosixPath("artifacts/check-tmp"),
    PurePosixPath("artifacts/tmp"),
    PurePosixPath("artifacts/uv-cache"),
    PurePosixPath("artifacts/uv-python"),
)
SDKROOT = Path(
    "/Applications/Xcode.app/Contents/Developer/Platforms/"
    "MacOSX.platform/Developer/SDKs/MacOSX.sdk"
)
OUTPUT_LIMIT = 64 * 1024
TOOL_OUTPUT_LIMIT = 512
TOOL_TIMEOUT = 10.0
COMMAND_TIMEOUT = 300.0
MAX_VENV_ENTRIES = 100_000
MAX_VENV_DEPTH = 128
_DIR_FD_REMOVAL = os.unlink in os.supports_dir_fd and os.rmdir in os.supports_dir_fd
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _fail(message: str) -> BootstrapError:
    return BootstrapError(message)


def _root(root: Path) -> Path:
    if not isinstance(root, Path) or not root.is_absolute():
        raise _fail("repository root must be absolute")
    try:
        mode = root.lstat().st_mode
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise _fail("repository root is unavailable") from error
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode) or resolved != root:
        raise _fail("repository root must be a canonical real directory")
    return root


def _open_runtime_below(
    root: Path,
    root_descriptor: int,
    root_mount: tuple[int, bytes | None],
    relative: PurePosixPath,
    *,
    create: bool,
) -> int:
    descriptor = os.dup(root_descriptor)
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
        current = root
        for part in relative.parts:
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise _fail(f"missing runtime directory: {relative}")
                try:
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                    child = os.open(part, flags, dir_fd=descriptor)
                except OSError as error:
                    raise _fail(
                        f"cannot create safe runtime directory: {relative}"
                    ) from error
            except OSError as error:
                raise _fail(f"unsafe runtime directory: {relative}") from error
            current = current / part
            try:
                opened = os.fstat(child)
                linked = current.lstat()
                if (
                    not stat.S_ISDIR(opened.st_mode)
                    or not same_held_mount(root_mount, child, current)
                    or _identity_facts(opened) != _identity_facts(linked)
                ):
                    raise _fail(f"unsafe runtime directory: {relative}")
            except BaseException:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _mkdir_below(
    root: Path,
    root_descriptor: int,
    root_mount: tuple[int, bytes | None],
    relative: PurePosixPath,
) -> None:
    descriptor = _open_runtime_below(
        root,
        root_descriptor,
        root_mount,
        relative,
        create=True,
    )
    os.close(descriptor)


def prepare_directories(root: Path, *, acquisition: bool) -> None:
    del acquisition
    repository = _root(root)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        descriptor = os.open(repository, flags)
    except OSError as error:
        raise _fail("cannot open repository root") from error
    try:
        opened = os.fstat(descriptor)
        if _identity_facts(opened) != _identity_facts(repository.lstat()):
            raise _fail("repository root changed")
        try:
            root_mount = held_mount_identity(descriptor)
        except OSError as error:
            raise _fail("repository mount identity is unavailable") from error
        for relative in RUNTIME_DIRECTORIES:
            _mkdir_below(repository, descriptor, root_mount, relative)
    finally:
        os.close(descriptor)


def _validate_empty_project_pycache(root: Path) -> Path:
    repository = _root(root)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        root_descriptor = os.open(repository, flags)
    except OSError as error:
        raise _fail("cannot open repository root") from error
    descriptor: int | None = None
    try:
        opened = os.fstat(root_descriptor)
        if _identity_facts(opened) != _identity_facts(repository.lstat()):
            raise _fail("repository root changed")
        try:
            root_mount = held_mount_identity(root_descriptor)
        except OSError as error:
            raise _fail("repository mount identity is unavailable") from error
        descriptor = _open_runtime_below(
            repository,
            root_descriptor,
            root_mount,
            PurePosixPath("artifacts/check-pycache"),
            create=False,
        )
        with os.scandir(descriptor) as iterator:
            if next(iterator, None) is not None:
                raise _fail("project Python cache must be empty")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(root_descriptor)
    return repository / "artifacts/check-pycache"


def validate_cargo_configuration(root: Path) -> None:
    repository = _root(root)
    candidates: list[Path] = []
    current = repository
    while True:
        candidates.append(current / ".cargo")
        if current.parent == current:
            break
        current = current.parent
    candidates.append(repository / "artifacts/cargo-home")
    for directory in candidates:
        for name in ("config", "config.toml", "credentials", "credentials.toml"):
            path = directory / name
            try:
                path.lstat()
            except FileNotFoundError:
                continue
            except OSError as error:
                raise _fail("cannot inspect Cargo configuration") from error
            raise _fail("ambient Cargo configuration is forbidden")


def git_environment(root: Path, git_executable: Path) -> dict[str, str]:
    repository = _root(root)
    if not isinstance(git_executable, Path) or not git_executable.is_absolute():
        raise _fail("Git capability must be absolute")
    path = os.pathsep.join(dict.fromkeys((str(git_executable.parent), "/usr/bin")))
    return {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(repository / "artifacts/check-home"),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": path,
        "TMPDIR": str(repository / "artifacts/check-tmp"),
        "TZ": "UTC",
    }


def _prove_venv_disposable(
    root: Path,
    git_executable: Path,
    environment: dict[str, str],
    runner: Callable[..., object],
) -> None:
    try:
        resolved = git_executable.resolve(strict=True)
        mode = resolved.lstat().st_mode
    except OSError as error:
        raise _fail("Git capability is unavailable") from error
    if (
        resolved != git_executable
        or not stat.S_ISREG(mode)
        or mode & 0o022
        or not os.access(resolved, os.X_OK)
        or environment != git_environment(root, resolved)
    ):
        raise _fail("Git capability or environment is unsafe")
    probes = (
        (
            ("check-ignore", "-v", "-z", "--stdin", "--no-index"),
            b".venv/\0",
            b".gitignore\x001\x00.venv/\x00.venv/\x00",
        ),
        (("ls-files", "-z", "--", ".venv"), b"", b""),
    )
    ignore_bytes: bytes | None = None
    for index, (suffix, raw, expected) in enumerate(probes):
        try:
            if index == 0:
                ignore_bytes = read_regular_below(
                    root, PurePosixPath(".gitignore"), 64 * 1024
                )
            prefix = git_control_preflight(
                root,
                git_executable=resolved,
                git_environment=environment,
                runner=runner,
            )
            if (
                index == 0
                and read_regular_below(root, PurePosixPath(".gitignore"), 64 * 1024)
                != ignore_bytes
            ):
                raise _fail("tracked root .gitignore changed")
            result = runner(
                [*prefix, *suffix],
                raw,
                dict(environment),
                timeout=TOOL_TIMEOUT,
                output_limit=TOOL_OUTPUT_LIMIT,
                cwd=root,
            )
            if (
                index == 0
                and read_regular_below(root, PurePosixPath(".gitignore"), 64 * 1024)
                != ignore_bytes
            ):
                raise _fail("tracked root .gitignore changed")
        except (
            OSError,
            RegistryError,
            ReportError,
            SafeFileError,
            ValueError,
        ) as error:
            raise _fail(".venv is not proven disposable") from error
        if (
            type(result) is not tuple
            or len(result) != 2
            or type(result[0]) is not bytes
            or type(result[1]) is not bytes
            or result[1]
            or result[0] != expected
        ):
            detail = "ignore proof" if index == 0 else "tracked-file proof"
            raise _fail(f".venv failed {detail}")


def _validate_venv_tree(
    descriptor: int,
    path: Path,
    repository_mount: tuple[int, bytes | None],
    *,
    depth: int = 0,
    entries: list[int] | None = None,
) -> None:
    if entries is None:
        entries = [0]
    if depth > MAX_VENV_DEPTH:
        raise _fail(".venv tree is too deep")
    try:
        with os.scandir(descriptor) as iterator:
            for entry in iterator:
                entries[0] += 1
                if entries[0] > MAX_VENV_ENTRIES:
                    raise _fail(".venv tree has too many entries")
                before = entry.stat(follow_symlinks=False)
                mode = before.st_mode
                if stat.S_ISLNK(mode):
                    continue
                if stat.S_ISREG(mode):
                    leaf = os.open(
                        entry.name,
                        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=descriptor,
                    )
                    try:
                        if _file_facts(os.fstat(leaf)) != _file_facts(
                            before
                        ) or not same_held_mount(
                            repository_mount,
                            leaf,
                            path / entry.name,
                        ):
                            raise _fail(".venv contains a mount or changed file")
                    finally:
                        os.close(leaf)
                    continue
                if not stat.S_ISDIR(mode):
                    raise _fail(".venv contains an unsupported entry")
                flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
                child = os.open(entry.name, flags, dir_fd=descriptor)
                try:
                    current = os.fstat(child)
                    child_path = path / entry.name
                    if (
                        _file_facts(before) != _file_facts(current)
                        or not same_held_mount(repository_mount, child, child_path)
                        or _file_facts(child_path.lstat()) != _file_facts(current)
                    ):
                        raise _fail(".venv contains a mount or changed directory")
                    _validate_venv_tree(
                        child,
                        child_path,
                        repository_mount,
                        depth=depth + 1,
                        entries=entries,
                    )
                finally:
                    os.close(child)
    except BootstrapError:
        raise
    except OSError as error:
        raise _fail("cannot inspect .venv descendants") from error


def _verify_directory_chain(
    chain: Sequence[tuple[int, str, os.stat_result, Path]],
    repository_mount: tuple[int, bytes | None],
) -> None:
    try:
        for parent, name, expected, path in chain:
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            child = os.open(
                name,
                os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent,
            )
            try:
                if (
                    _identity_facts(current) != _identity_facts(expected)
                    or _identity_facts(os.fstat(child)) != _identity_facts(expected)
                    or not same_held_mount(repository_mount, child, path)
                ):
                    raise _fail(".venv directory link changed")
            finally:
                os.close(child)
    except BootstrapError:
        raise
    except OSError as error:
        raise _fail("cannot verify .venv directory link") from error


def _delete_venv_contents(
    descriptor: int,
    path: Path,
    repository_mount: tuple[int, bytes | None],
    chain: Sequence[tuple[int, str, os.stat_result, Path]],
    *,
    depth: int = 0,
    entries: list[int] | None = None,
) -> None:
    if entries is None:
        entries = [0]
    if depth > MAX_VENV_DEPTH:
        raise _fail(".venv tree is too deep")
    try:
        with os.scandir(descriptor) as iterator:
            names: list[str] = []
            for entry in iterator:
                entries[0] += 1
                if entries[0] > MAX_VENV_ENTRIES:
                    raise _fail(".venv tree has too many entries")
                names.append(entry.name)
        for name in names:
            _verify_directory_chain(chain, repository_mount)
            before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            mode = before.st_mode
            if stat.S_ISREG(mode):
                leaf = os.open(
                    name,
                    os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=descriptor,
                )
                try:
                    if _file_facts(os.fstat(leaf)) != _file_facts(
                        before
                    ) or not same_held_mount(repository_mount, leaf, path / name):
                        raise _fail(".venv leaf changed before removal")
                finally:
                    os.close(leaf)
                current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if _file_facts(current) != _file_facts(before):
                    raise _fail(".venv leaf changed before removal")
                _verify_directory_chain(chain, repository_mount)
                final_leaf = os.open(
                    name,
                    os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=descriptor,
                )
                try:
                    held = os.fstat(final_leaf)
                    final_named = os.stat(
                        name, dir_fd=descriptor, follow_symlinks=False
                    )
                    if (
                        _file_facts(held) != _file_facts(before)
                        or _file_facts(final_named) != _file_facts(held)
                        or not same_held_mount(
                            repository_mount, final_leaf, path / name
                        )
                    ):
                        raise _fail(".venv leaf changed before removal")
                    _verify_directory_chain(chain, repository_mount)
                    os.unlink(name, dir_fd=descriptor)
                    after_unlink = os.fstat(final_leaf)
                    if (
                        after_unlink.st_dev,
                        after_unlink.st_ino,
                        after_unlink.st_mode,
                        after_unlink.st_size,
                        after_unlink.st_mtime_ns,
                    ) != (
                        held.st_dev,
                        held.st_ino,
                        held.st_mode,
                        held.st_size,
                        held.st_mtime_ns,
                    ):
                        raise _fail("held .venv leaf changed during removal")
                finally:
                    os.close(final_leaf)
                continue
            if stat.S_ISLNK(mode):
                current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if _file_facts(current) != _file_facts(before):
                    raise _fail(".venv leaf changed before removal")
                _verify_directory_chain(chain, repository_mount)
                os.unlink(name, dir_fd=descriptor)
                continue
            if not stat.S_ISDIR(mode):
                raise _fail(".venv contains an unsupported entry")
            flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
            child = os.open(name, flags, dir_fd=descriptor)
            try:
                opened = os.fstat(child)
                child_path = path / name
                if (
                    _file_facts(opened) != _file_facts(before)
                    or not same_held_mount(repository_mount, child, child_path)
                    or _file_facts(child_path.lstat()) != _file_facts(opened)
                ):
                    raise _fail(".venv contains a mount or changed directory")
                child_chain = (*chain, (descriptor, name, opened, child_path))
                _verify_directory_chain(child_chain, repository_mount)
                _delete_venv_contents(
                    child,
                    child_path,
                    repository_mount,
                    child_chain,
                    depth=depth + 1,
                    entries=entries,
                )
                _verify_directory_chain(child_chain, repository_mount)
                os.rmdir(name, dir_fd=descriptor)
                try:
                    os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise _fail(".venv child link survived removal")
            finally:
                os.close(child)
        _verify_directory_chain(chain, repository_mount)
        with os.scandir(descriptor) as iterator:
            if next(iterator, None) is not None:
                raise _fail(".venv changed during removal")
    except BootstrapError:
        raise
    except OSError as error:
        raise _fail("cannot remove .venv descendants") from error


def remove_venv(
    root: Path,
    *,
    git_executable: Path,
    git_environment: dict[str, str],
    runner: Callable[..., object] = _run_bounded_process,
) -> None:
    repository = _root(root)
    venv = repository / ".venv"
    if not _DIR_FD_REMOVAL:
        raise _fail("safe .venv removal is unavailable")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        descriptor = os.open(repository, flags)
    except OSError as error:
        raise _fail("cannot open repository root") from error
    try:
        _prove_venv_disposable(
            repository,
            git_executable,
            git_environment,
            runner,
        )
        try:
            before = os.stat(".venv", dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return
        except OSError as error:
            raise _fail("cannot inspect .venv") from error
        mode = before.st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise _fail(".venv is not a disposable real directory")
        try:
            venv_descriptor = os.open(".venv", flags, dir_fd=descriptor)
        except OSError as error:
            raise _fail("cannot open .venv") from error
        try:
            opened = os.fstat(venv_descriptor)
            try:
                repository_mount = held_mount_identity(descriptor)
            except OSError as error:
                raise _fail(".venv mount identity is unavailable") from error
            if _file_facts(opened) != _file_facts(before) or not same_held_mount(
                repository_mount, venv_descriptor, venv
            ):
                raise _fail(".venv changed before inspection")
            _validate_venv_tree(venv_descriptor, venv, repository_mount)
            chain = ((descriptor, ".venv", opened, venv),)
            _verify_directory_chain(chain, repository_mount)
            _delete_venv_contents(
                venv_descriptor,
                venv,
                repository_mount,
                chain,
            )
            _verify_directory_chain(chain, repository_mount)
            os.rmdir(".venv", dir_fd=descriptor)
            try:
                os.stat(".venv", dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise _fail(".venv link survived removal")
            if _identity_facts(os.fstat(venv_descriptor)) != _identity_facts(opened):
                raise _fail("held .venv directory identity changed")
        finally:
            os.close(venv_descriptor)
    finally:
        os.close(descriptor)


def _default_runner(argv: list[str], **kwargs: object) -> object:
    environment = kwargs.pop("env", None)
    cwd = kwargs.pop("cwd", None)
    if (
        kwargs
        or type(environment) is not dict
        or (cwd is not None and not isinstance(cwd, Path))
    ):
        raise _fail("invalid tool probe context")
    try:
        stdout, stderr = _run_bounded_process(
            argv,
            b"",
            environment,
            timeout=TOOL_TIMEOUT,
            output_limit=TOOL_OUTPUT_LIMIT,
            cwd=cwd,
        )
    except (OSError, RegistryError, ValueError) as error:
        raise _fail("tool probe failed") from error
    return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)


def validate_tool(
    path: Path,
    version_argv: tuple[str, ...],
    expected_stdout: bytes,
    *,
    runner: Callable[..., object] = _default_runner,
) -> Path:
    if not isinstance(path, Path) or not path.is_absolute() or "\0" in os.fspath(path):
        raise _fail("tool path must be absolute")
    try:
        resolved = path.resolve(strict=True)
        mode = resolved.lstat().st_mode
    except OSError as error:
        raise _fail("tool path is unavailable") from error
    if not stat.S_ISREG(mode) or mode & 0o022 or not os.access(resolved, os.X_OK):
        raise _fail("tool path is unsafe")
    result = runner(
        [str(resolved), *version_argv],
        cwd=None,
        env={"LANG": "C", "LC_ALL": "C", "PATH": str(resolved.parent), "TZ": "UTC"},
    )
    if (
        getattr(result, "returncode", None) != 0
        or getattr(result, "stdout", None) != expected_stdout
        or getattr(result, "stderr", None) != b""
    ):
        raise _fail("unexpected tool version")
    return resolved


def validate_semantic_tool(
    path: Path,
    name: str,
    version: str,
    *,
    runner: Callable[..., object] = _default_runner,
) -> Path:
    if (
        not isinstance(path, Path)
        or not path.is_absolute()
        or re.fullmatch(r"[a-z][a-z0-9-]*", name) is None
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None
    ):
        raise _fail("tool path must be absolute")
    try:
        resolved = path.resolve(strict=True)
        mode = resolved.lstat().st_mode
    except OSError as error:
        raise _fail("tool path is unavailable") from error
    if not stat.S_ISREG(mode) or mode & 0o022 or not os.access(resolved, os.X_OK):
        raise _fail("tool path is unsafe")
    result = runner(
        [str(resolved), "--version"],
        cwd=None,
        env={"LANG": "C", "LC_ALL": "C", "PATH": str(resolved.parent), "TZ": "UTC"},
    )
    pattern = re.compile(
        re.escape(name.encode("ascii"))
        + b" "
        + re.escape(version.encode("ascii"))
        + rb"(?:-stable)?(?: \([A-Za-z0-9][A-Za-z0-9._+:/ -]{0,127}\)){0,2}\n\Z"
    )
    if (
        getattr(result, "returncode", None) != 0
        or getattr(result, "stderr", None) != b""
        or type(getattr(result, "stdout", None)) is not bytes
        or len(result.stdout) > TOOL_OUTPUT_LIMIT
        or pattern.fullmatch(result.stdout) is None
    ):
        raise _fail("unexpected tool version")
    return resolved


def validate_image_git(
    path: Path,
    *,
    runner: Callable[..., object] = _default_runner,
) -> Path:
    if not isinstance(path, Path) or not path.is_absolute() or "\0" in os.fspath(path):
        raise _fail("image Git path must be absolute")
    try:
        resolved = path.resolve(strict=True)
        mode = resolved.lstat().st_mode
    except OSError as error:
        raise _fail("image Git path is unavailable") from error
    if not stat.S_ISREG(mode) or mode & 0o022 or not os.access(resolved, os.X_OK):
        raise _fail("image Git path is unsafe")
    result = runner(
        [str(resolved), "--version"],
        cwd=None,
        env={
            "GIT_NO_LAZY_FETCH": "1",
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": str(resolved.parent),
            "TZ": "UTC",
        },
    )
    stdout = getattr(result, "stdout", None)
    if (
        getattr(result, "returncode", None) != 0
        or type(stdout) is not bytes
        or len(stdout) > TOOL_OUTPUT_LIMIT
        or re.fullmatch(rb"git version 2\.[0-9]{1,3}\.[0-9]{1,3}\n", stdout) is None
        or getattr(result, "stderr", None) != b""
    ):
        raise _fail("unexpected image Git version")
    return resolved


def validate_docker_tool(
    path: Path,
    *,
    runner: Callable[..., object] = _default_runner,
) -> Path:
    if not isinstance(path, Path) or not path.is_absolute() or "\0" in os.fspath(path):
        raise _fail("Docker path must be absolute")
    try:
        resolved = path.resolve(strict=True)
        mode = resolved.lstat().st_mode
    except OSError as error:
        raise _fail("Docker path is unavailable") from error
    if not stat.S_ISREG(mode) or mode & 0o022 or not os.access(resolved, os.X_OK):
        raise _fail("Docker path is unsafe")
    result = runner(
        [str(resolved), "--version"],
        cwd=None,
        env={"LANG": "C", "LC_ALL": "C", "PATH": str(resolved.parent), "TZ": "UTC"},
    )
    stdout = getattr(result, "stdout", None)
    if (
        getattr(result, "returncode", None) != 0
        or type(stdout) is not bytes
        or len(stdout) > TOOL_OUTPUT_LIMIT
        or re.fullmatch(
            rb"Docker version 25\.0\.3, build [0-9A-Za-z._+-]{1,64}\n",
            stdout,
        )
        is None
        or getattr(result, "stderr", None) != b""
    ):
        raise _fail("unexpected Docker version")
    return resolved


def docker_capability(
    command: tuple[str, ...],
    environment: dict[str, str],
    *,
    runner: Callable[..., object] = _default_runner,
) -> Path | None:
    if type(command) is not tuple or type(environment) is not dict:
        raise _fail("invalid Docker projection")
    if command != ("environment", "verify-linux"):
        return None
    value = environment.get("GB_BOOTSTRAP_DOCKER")
    if type(value) is not str or not value or "\0" in value:
        raise _fail("missing Docker projection")
    return validate_docker_tool(Path(value), runner=runner)


def validate_platform_marker(system: str, marker: str, expected: str) -> str | None:
    if system == "Darwin":
        if marker:
            raise _fail("clean-Linux marker is not valid on Darwin")
        return None
    if system == "Linux":
        if _DIGEST.fullmatch(marker) is None or marker != expected:
            raise _fail("clean-Linux marker does not match the locked platform")
        return marker
    raise _fail("unsupported bootstrap platform")


def _real_file(root: Path, relative: PurePosixPath, max_bytes: int) -> bytes:
    try:
        return read_regular_below(root, relative, max_bytes)
    except SafeFileError as error:
        raise _fail(f"unsafe bootstrap input: {relative}") from error


def validate_venv(
    root: Path,
    *,
    runner: Callable[..., object] = _default_runner,
) -> Path:
    repository = _root(root)
    try:
        config = _real_file(repository, PurePosixPath(".venv/pyvenv.cfg"), 16 * 1024)
        text = config.decode("utf-8", "strict")
    except UnicodeError as error:
        raise _fail("invalid pyvenv.cfg") from error
    values: dict[str, str] = {}
    for line in text.splitlines():
        if " = " not in line:
            raise _fail("invalid pyvenv.cfg")
        key, value = line.split(" = ", 1)
        if not key or key in values:
            raise _fail("invalid pyvenv.cfg")
        values[key] = value
    if (
        set(values)
        != {
            "home",
            "implementation",
            "uv",
            "version_info",
            "include-system-site-packages",
            "prompt",
        }
        or values.get("implementation") != "CPython"
        or values.get("uv") != "0.11.29"
        or values.get("version_info") != "3.14"
        or values.get("include-system-site-packages") != "false"
        or values.get("prompt") != "golden-board"
    ):
        raise _fail("unexpected managed virtual environment")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        root_descriptor = os.open(repository, flags)
        descriptors.append(root_descriptor)
        repository_mount = held_mount_identity(root_descriptor)
        for parts in ((".venv", "bin"), ("artifacts", "uv-python")):
            descriptor = os.dup(root_descriptor)
            descriptors.append(descriptor)
            current = repository
            for part in parts:
                child = os.open(part, flags, dir_fd=descriptor)
                descriptors.append(child)
                current /= part
                if not same_held_mount(repository_mount, child, current):
                    raise _fail("virtual-environment directory is unsafe")
                descriptor = child
    except OSError as error:
        raise _fail("virtual-environment bin directory is unsafe") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    python_boundary = PurePosixPath("artifacts/uv-python")
    alias_boundary = PurePosixPath(".venv/bin")
    resolved: list[PurePosixPath] = []
    for name in ("python", "python3", "python3.14"):
        try:
            target = resolve_same_mount_path(
                repository,
                alias_boundary / name,
                boundary=python_boundary,
                source_boundary=alias_boundary,
                max_symlinks=32,
            )
            if not target.is_relative_to(python_boundary):
                raise SafeFileError("safe_link.escape")
        except SafeFileError as error:
            raise _fail(f"unsafe virtual-environment alias: {name}") from error
        resolved.append(target)
    if len(set(resolved)) != 1:
        raise _fail("virtual-environment aliases disagree")
    python_relative = resolved[0]
    python = repository / python_relative.as_posix()
    home = values.get("home")
    if type(home) is not str or not home or "\0" in home or "\\" in home:
        raise _fail("managed virtual-environment home is invalid")
    try:
        configured_home = PurePosixPath(home)
        if (
            not configured_home.is_absolute()
            or configured_home.as_posix() != home
            or any(part in ("", ".", "..") for part in configured_home.parts[1:])
        ):
            raise _fail("managed virtual-environment home is invalid")
        home_relative = configured_home.relative_to(
            PurePosixPath(repository.as_posix())
        )
        resolved_home = resolve_same_mount_path(
            repository,
            home_relative,
            boundary=python_boundary,
            max_symlinks=32,
        )
        if resolved_home != python_relative.parent:
            raise _fail("managed virtual-environment home is invalid")
    except (SafeFileError, ValueError) as error:
        if isinstance(error, BootstrapError):
            raise
        raise _fail("managed virtual-environment home is invalid") from error
    executable: int | None = None
    parent_descriptor: int | None = None
    root_descriptor: int | None = None
    try:
        root_descriptor = os.open(repository, flags)
        repository_mount = held_mount_identity(root_descriptor)
        parent_descriptor = _open_runtime_below(
            repository,
            root_descriptor,
            repository_mount,
            python_relative.parent,
            create=False,
        )
        named = os.stat(
            python_relative.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        executable = os.open(
            python_relative.name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent_descriptor,
        )
        held = os.fstat(executable)
        named_after = os.stat(
            python_relative.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(held.st_mode)
            or held.st_mode & 0o022
            or held.st_mode & 0o111 == 0
            or _file_facts(held) != _file_facts(named)
            or _file_facts(held) != _file_facts(named_after)
            or not same_held_mount(repository_mount, executable, python)
        ):
            raise _fail("managed Python executable is unsafe")
        result = runner(
            [str(python), "--version"],
            cwd=repository,
            env={
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": str(python.parent),
                "TZ": "UTC",
            },
        )
        current_descriptor = os.open(
            python_relative.name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent_descriptor,
        )
        try:
            current = os.fstat(current_descriptor)
            if (
                _file_facts(os.fstat(executable)) != _file_facts(held)
                or _file_facts(current) != _file_facts(held)
                or not same_held_mount(repository_mount, current_descriptor, python)
            ):
                raise _fail("managed Python executable changed")
        finally:
            os.close(current_descriptor)
        if _file_facts(os.fstat(executable)) != _file_facts(held):
            raise _fail("managed Python executable changed")
    except OSError as error:
        raise _fail("managed Python executable is unsafe") from error
    finally:
        if executable is not None:
            os.close(executable)
        if parent_descriptor is not None:
            os.close(parent_descriptor)
        if root_descriptor is not None:
            os.close(root_descriptor)
    if (
        getattr(result, "returncode", None) != 0
        or getattr(result, "stdout", None) != b"Python 3.14.6\n"
        or getattr(result, "stderr", None) != b""
    ):
        raise _fail("managed Python version drifted")
    return python


def project_environment(
    root: Path,
    *,
    python_path: Path,
    tool_directories: tuple[Path, ...],
    offline: bool,
    sdkroot: Path | None = None,
    clean_linux: bool = False,
) -> dict[str, str]:
    repository = _root(root)
    if not python_path.is_absolute():
        python_path = repository / python_path
    if python_path != repository / "python":
        raise _fail("project Python path must be the fixed repository directory")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    root_descriptor: int | None = None
    descriptor: int | None = None
    try:
        root_descriptor = os.open(repository, flags)
        descriptor = os.open("python", flags, dir_fd=root_descriptor)
        try:
            root_mount = held_mount_identity(root_descriptor)
        except OSError as error:
            raise _fail("project Python directory is unsafe") from error
        if not same_held_mount(root_mount, descriptor, python_path):
            raise _fail("project Python directory is unsafe")
    except OSError as error:
        raise _fail("project Python directory is unsafe") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if root_descriptor is not None:
            os.close(root_descriptor)
    if any(not directory.is_absolute() for directory in tool_directories):
        raise _fail("tool PATH entries must be absolute")
    pycache_prefix = _validate_empty_project_pycache(repository)
    path_entries = list(dict.fromkeys(str(directory) for directory in tool_directories))
    environment = {
        "CARGO_CACHE_AUTO_CLEAN_FREQUENCY": "never",
        "CARGO_HOME": str(repository / "artifacts/cargo-home"),
        "CARGO_REGISTRIES_CRATES_IO_PROTOCOL": "sparse",
        "CARGO_TARGET_DIR": str(repository / "artifacts/cargo-target"),
        "CARGO_TERM_COLOR": "never",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(repository / "artifacts/check-home"),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.pathsep.join(path_entries),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": str(pycache_prefix),
        "PYTHONPATH": str(python_path),
        "TMPDIR": str(repository / "artifacts/check-tmp"),
        "TZ": "UTC",
        "UV_CACHE_DIR": str(repository / "artifacts/uv-cache"),
        "UV_MANAGED_PYTHON": "true",
        "UV_NO_CONFIG": "1",
        "UV_PYTHON_INSTALL_DIR": str(repository / "artifacts/uv-python"),
        "UV_PROJECT_ENVIRONMENT": ".venv",
    }
    if type(clean_linux) is not bool or (sdkroot is not None and clean_linux):
        raise _fail("invalid platform environment")
    if sdkroot is not None:
        environment.update(
            {
                "CARGO_ENCODED_RUSTFLAGS": "-Clinker=/usr/bin/cc",
                "CARGO_TARGET_AARCH64_APPLE_DARWIN_LINKER": "/usr/bin/cc",
                "CC": "/usr/bin/cc",
                "SDKROOT": str(sdkroot),
            }
        )
    if clean_linux:
        environment.update(
            {
                "CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER": "/usr/bin/cc",
                "CC": "/usr/bin/cc",
                "COMPILER_PATH": "/usr/bin",
            }
        )
    if offline:
        environment.update(
            {
                "CARGO_NET_OFFLINE": "true",
                "UV_OFFLINE": "1",
                "UV_PYTHON_DOWNLOADS": "never",
            }
        )
    return environment


def check_command(arguments: Sequence[str]) -> tuple[str, ...]:
    values = tuple(arguments)
    if values == ():
        return ("check", "fast")
    if values in (("fast",), ("full",), ("release",)):
        return ("check", values[0])
    if (
        len(values) == 2
        and values[0] == "focused"
        and values[1]
        in (
            "foundation",
            "dependencies",
            "identity",
            "manifest",
            "source",
        )
    ):
        return ("check", *values)
    if values in (
        ("generate", "source-doctor"),
        ("generate", "release-summary"),
        (
            "generate",
            "release-summary",
            "--native-evidence",
            "artifacts/native-verification.json",
        ),
        ("environment", "verify-native"),
        ("environment", "verify-native", "--write-evidence"),
        ("environment", "verify-linux"),
    ):
        return values
    raise _fail("unsupported scripts/check arguments")


def project_argv(
    root: Path,
    uv: Path,
    python: Path,
    command: tuple[str, ...],
) -> list[str]:
    if not all(path.is_absolute() for path in (root, uv, python)):
        raise _fail("project argv paths must be absolute")
    return [
        str(uv),
        "--no-config",
        "run",
        "--project",
        str(root),
        "--offline",
        "--frozen",
        "--no-cache",
        "--python",
        str(python),
        str(python),
        "-P",
        "-B",
        "-S",
        "-m",
        "golden_board.cli",
        *command,
    ]


def _run_command(argv: list[str], environment: dict[str, str], root: Path) -> None:
    try:
        stdout, stderr = _run_bounded_process(
            argv,
            b"",
            environment,
            timeout=COMMAND_TIMEOUT,
            output_limit=OUTPUT_LIMIT,
            cwd=root,
        )
    except RegistryError as error:
        raise _fail("project command failed") from error
    if stdout or stderr:
        # Package managers may report ordinary progress; output remains bounded.
        return


def _validate_sdk() -> Path:
    try:
        mode = SDKROOT.lstat().st_mode
        if (
            SDKROOT.resolve(strict=True) != SDKROOT
            or not stat.S_ISDIR(mode)
            or mode & 0o022
        ):
            raise _fail("unsafe SDK root")
        settings = read_regular_below(
            SDKROOT, PurePosixPath("SDKSettings.json"), 65_536
        )
        document = json.loads(settings.decode("utf-8", "strict"))
    except (OSError, SafeFileError, UnicodeError, json.JSONDecodeError) as error:
        raise _fail("invalid SDK root") from error
    if type(document) is not dict or document.get("CanonicalName") != "macosx15.5":
        raise _fail("unexpected SDK version")
    return SDKROOT


def _probe_compiler(root: Path, environment: dict[str, str]) -> None:
    try:
        version, version_error = _run_bounded_process(
            ["/usr/bin/cc", "--version"],
            b"",
            environment,
            timeout=TOOL_TIMEOUT,
            output_limit=OUTPUT_LIMIT,
            cwd=root,
        )
        if (
            not version.startswith(b"Apple clang version 17.0.0 (clang-1700.0.13.5)\n")
            or version_error
        ):
            raise _fail("unexpected compiler")
        with tempfile.TemporaryDirectory(dir=root / "artifacts/check-tmp") as temporary:
            output = Path(temporary) / "probe"
            trace_out, trace = _run_bounded_process(
                ["/usr/bin/cc", "-###", "-x", "c", "-", "-o", str(output)],
                b"",
                environment,
                timeout=TOOL_TIMEOUT,
                output_limit=OUTPUT_LIMIT,
                cwd=root,
            )
            text = trace.decode("utf-8", "strict")
            required = (
                '"-target-sdk-version=15.5"',
                '"-target-linker-version" "1167.5"',
                f'"-isysroot" "{SDKROOT}"',
                f'"-syslibroot" "{SDKROOT}"',
            )
            if trace_out or not all(value in text for value in required):
                raise _fail("compiler trace drifted")
            linked_out, linked_error = _run_bounded_process(
                ["/usr/bin/cc", "-x", "c", "-", "-o", str(output)],
                b"int main(void) { return 0; }\n",
                environment,
                timeout=TOOL_TIMEOUT,
                output_limit=OUTPUT_LIMIT,
                cwd=root,
            )
            if (
                linked_out
                or linked_error
                or not output.is_file()
                or output.stat().st_size == 0
            ):
                raise _fail("compiler link probe failed")
    except (RegistryError, UnicodeError) as error:
        if isinstance(error, BootstrapError):
            raise
        raise _fail("compiler probe failed") from error


def _tools(
    arguments: Sequence[str],
    *,
    clean_linux: bool = False,
) -> tuple[Path, Path, Path, Path, Path, Path, Path, Path]:
    if len(arguments) != 6 or type(clean_linux) is not bool:
        raise _fail("bootstrap requires six tool paths")
    python, uv, cargo, rustc, rustfmt, git = (Path(value) for value in arguments)
    validated_cargo = validate_semantic_tool(cargo, "cargo", "1.94.0")
    validated_cargo_fmt = validate_semantic_tool(
        validated_cargo.parent / "cargo-fmt", "rustfmt", "1.8.0"
    )
    if validated_cargo_fmt != validated_cargo.parent / "cargo-fmt":
        raise _fail("cargo-fmt must be the validated cargo sibling")
    validated_rustdoc = validate_semantic_tool(
        validated_cargo.parent / "rustdoc", "rustdoc", "1.94.0"
    )
    if validated_rustdoc != validated_cargo.parent / "rustdoc":
        raise _fail("rustdoc must be the validated cargo sibling")
    validated_rustc = validate_semantic_tool(rustc, "rustc", "1.94.0")
    if validated_rustc != validated_cargo.parent / "rustc":
        raise _fail("rustc must be the validated cargo sibling")
    validated_rustfmt = validate_semantic_tool(rustfmt, "rustfmt", "1.8.0")
    if validated_rustfmt != validated_cargo.parent / "rustfmt":
        raise _fail("rustfmt must be the validated cargo sibling")
    return (
        validate_tool(python, ("--version",), b"Python 3.14.6\n"),
        validate_semantic_tool(uv, "uv", "0.11.29"),
        validated_cargo,
        validated_cargo_fmt,
        validated_rustc,
        validated_rustdoc,
        validated_rustfmt,
        (
            validate_image_git(git)
            if clean_linux
            else validate_tool(git, ("--version",), b"git version 2.49.0\n")
        ),
    )


def _static_dependency_preflight(root: Path) -> None:
    before = _validate_import_sources(_PYTHON_DIRECTORY)
    from golden_board.checks import static_dependency_errors

    if _validate_import_sources(_PYTHON_DIRECTORY) != before:
        raise _fail("bootstrap source tree changed during dependency preflight")
    errors = static_dependency_errors(root)
    if (
        type(errors) is not list
        or any(type(error) is not str for error in errors)
        or errors
    ):
        raise _fail("static dependency policy rejected")


def _safe_error_detail(error: BaseException) -> str:
    detail = str(error)
    if (
        not detail
        or len(detail) > 160
        or any(ord(character) < 0x20 or ord(character) > 0x7E for character in detail)
    ):
        return "bootstrap state rejected"
    return detail


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if sys.version_info[:3] != (3, 14, 6):
        print("bootstrap requires Python 3.14.6", file=sys.stderr)
        return 1
    try:
        if len(arguments) < 8 or arguments[0] not in {"acquire", "check"}:
            raise _fail("invalid bootstrap invocation")
        mode = arguments[0]
        user_arguments = arguments[8:]
        if mode == "acquire":
            if user_arguments:
                raise _fail("scripts/setup accepts no arguments")
            command: tuple[str, ...] | None = None
        else:
            command = check_command(user_arguments)
        root = _root(Path(arguments[1]))
        if root / "python" != _PYTHON_DIRECTORY:
            raise _fail("bootstrap module is outside the selected repository")
        _static_dependency_preflight(root)
        validate_cargo_configuration(root)
        lock = load_source_lock(root)
        marker = os.environ.get("GB_CLEAN_LINUX_DIGEST", "")
        accepted_marker = validate_platform_marker(
            os.uname().sysname, marker, lock.clean_linux.platform_digest
        )
        python, uv, cargo, cargo_fmt, rustc, rustdoc, rustfmt, git = _tools(
            arguments[2:8], clean_linux=accepted_marker is not None
        )
        docker = (
            docker_capability(command, dict(os.environ))
            if command is not None
            else None
        )
        prepare_directories(root, acquisition=mode == "acquire")
        sdkroot = _validate_sdk() if os.uname().sysname == "Darwin" else None
        tool_directories = tuple(
            dict.fromkeys(
                (
                    cargo.parent,
                    python.parent,
                    uv.parent,
                    git.parent,
                    Path("/usr/bin"),
                    Path("/bin"),
                )
            )
        )
        if docker is not None and docker.parent not in tool_directories:
            tool_directories += (docker.parent,)
        environment = project_environment(
            root,
            python_path=root / "python",
            tool_directories=tool_directories,
            offline=mode == "check",
            sdkroot=sdkroot,
            clean_linux=accepted_marker is not None,
        )
        environment.update(
            {
                "GB_BOOTSTRAP_CARGO": str(cargo),
                "GB_BOOTSTRAP_CARGO_FMT": str(cargo_fmt),
                "GB_BOOTSTRAP_GIT": str(git),
                "GB_BOOTSTRAP_RUSTC": str(rustc),
                "GB_BOOTSTRAP_RUSTDOC": str(rustdoc),
                "GB_BOOTSTRAP_RUSTFMT": str(rustfmt),
                "RUSTC": str(rustc),
                "RUSTDOC": str(rustdoc),
                "RUSTFMT": str(rustfmt),
            }
        )
        if docker is not None:
            environment["GB_BOOTSTRAP_DOCKER"] = str(docker)
        if accepted_marker is not None:
            environment["GB_CLEAN_LINUX_DIGEST"] = accepted_marker
        if sdkroot is not None:
            _probe_compiler(root, environment)
        if mode == "acquire":
            remove_venv(
                root,
                git_executable=git,
                git_environment=git_environment(root, git),
            )
            acquisition_environment = dict(environment)
            acquisition_environment.pop("CARGO_NET_OFFLINE", None)
            acquisition_environment.pop("UV_OFFLINE", None)
            acquisition_environment.pop("UV_PYTHON_DOWNLOADS", None)
            acquisition_environment.pop("PYTHONPATH", None)
            _run_command(
                [str(uv), "--no-config", "sync", "--project", str(root), "--locked"],
                acquisition_environment,
                root,
            )
            validate_venv(root)
            _run_command(
                [
                    str(cargo),
                    "fetch",
                    "--manifest-path",
                    "Cargo.toml",
                    "--locked",
                ],
                acquisition_environment,
                root,
            )
            write_inventory(root, build_inventory(root))
            return 0
        assert command is not None
        load_inventory(root)
        managed_python = validate_venv(root)
        _validate_empty_project_pycache(root)
        os.execve(
            str(uv),
            project_argv(root, uv, managed_python, command),
            environment,
        )
    except (BootstrapError, OSError, ValueError) as error:
        print(f"bootstrap failed: {_safe_error_detail(error)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
