from __future__ import annotations

import os
import errno
import io
import json
from dataclasses import dataclass
import hashlib
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
import socket
import stat
import tarfile
import tempfile
from types import SimpleNamespace

from golden_board.manifest import decode_canonical_manifest, encode_canonical_value
from golden_board.acquisition import build_inventory, load_inventory, write_inventory
from golden_board.registry import RegistryError, _run_bounded_process
from golden_board.reports import (
    EXPECTED_NATIVE_COMMANDS,
    EXPECTED_NATIVE_ISOLATION,
    MAX_REPORT_BYTES,
    ReportError,
    _native_inventory,
    _native_shape,
    git_control_preflight,
    validate_native_evidence,
)
from golden_board.source_lock import (
    SourceLock,
    held_mount_identity,
    load_source_lock,
    read_regular_below,
    same_held_mount,
)


class CleanError(ValueError):
    pass


TOOL_TIMEOUT = 10.0
COMMAND_TIMEOUT = 900.0
OUTPUT_LIMIT = 1024 * 1024
OID = re.compile(rb"[0-9a-f]{40}\n\Z")
SDKROOT = Path(
    "/Applications/Xcode.app/Contents/Developer/Platforms/"
    "MacOSX.platform/Developer/SDKs/MacOSX.sdk"
)


def _run(
    argv: list[str],
    raw: bytes,
    environment: dict[str, str],
    *,
    timeout: float,
    output_limit: int,
    cwd: Path | None = None,
) -> tuple[bytes, bytes]:
    return _run_bounded_process(
        argv,
        raw,
        environment,
        timeout=timeout,
        output_limit=output_limit,
        cwd=cwd,
    )


def _probe_runner(argv: list[str], **kwargs: object) -> object:
    environment = kwargs.pop("env", None)
    cwd = kwargs.pop("cwd", None)
    if (
        kwargs
        or type(environment) is not dict
        or (cwd is not None and not isinstance(cwd, Path))
    ):
        raise CleanError("invalid tool probe")
    try:
        stdout, stderr = _run(
            argv,
            b"",
            environment,
            timeout=TOOL_TIMEOUT,
            output_limit=512,
            cwd=cwd,
        )
    except (OSError, RegistryError, ValueError) as error:
        raise CleanError("tool probe failed") from error
    return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)


def _probe_exact_tool(
    path: Path,
    version_argv: tuple[str, ...],
    expected: bytes,
) -> Path:
    from golden_board.bootstrap import validate_tool

    try:
        return validate_tool(
            path,
            version_argv,
            expected,
            runner=_probe_runner,
        )
    except ValueError as error:
        raise CleanError("invalid pinned tool") from error


def _explicit_git(path: Path) -> Path:
    _safe_executable(path)
    return _probe_exact_tool(path, ("--version",), b"git version 2.49.0\n")


def _probe_semantic_tool(path: Path, name: str, version: str) -> Path:
    from golden_board.bootstrap import validate_semantic_tool

    try:
        return validate_semantic_tool(
            path,
            name,
            version,
            runner=_probe_runner,
        )
    except ValueError as error:
        raise CleanError("invalid pinned tool") from error


@dataclass(frozen=True)
class _NativeTools:
    python: Path
    uv: Path
    cargo: Path
    cargo_fmt: Path
    rustc: Path
    rustdoc: Path
    rustfmt: Path
    git: Path


def _validate_sealed_path(value: str) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > 8192
        or any(ord(character) < 0x20 or ord(character) > 0x7E for character in value)
    ):
        raise CleanError("invalid sealed tool path")
    entries = value.split(os.pathsep)
    if any(
        not entry
        or not Path(entry).is_absolute()
        or ".." in Path(entry).parts
        or os.fspath(Path(entry)) != entry
        for entry in entries
    ) or len(entries) != len(set(entries)):
        raise CleanError("invalid sealed tool path")
    return value


def _resolve_native_tools(
    git_executable: Path,
    *,
    sealed_path: str,
) -> _NativeTools:
    search = _validate_sealed_path(sealed_path)
    candidates: dict[str, Path] = {}
    for name in ("python3.14", "uv", "cargo"):
        found = shutil.which(name, path=search)
        if found is None:
            raise CleanError(f"missing pinned native tool: {name}")
        candidates[name] = Path(found)
    cargo = _probe_semantic_tool(candidates["cargo"], "cargo", "1.94.0")
    cargo_fmt = _probe_semantic_tool(cargo.parent / "cargo-fmt", "rustfmt", "1.8.0")
    rustc = _probe_semantic_tool(cargo.parent / "rustc", "rustc", "1.94.0")
    rustdoc = _probe_semantic_tool(cargo.parent / "rustdoc", "rustdoc", "1.94.0")
    rustfmt = _probe_semantic_tool(cargo.parent / "rustfmt", "rustfmt", "1.8.0")
    if (
        cargo_fmt != cargo.parent / "cargo-fmt"
        or rustc != cargo.parent / "rustc"
        or rustdoc != cargo.parent / "rustdoc"
        or rustfmt != cargo.parent / "rustfmt"
    ):
        raise CleanError("invalid pinned native Cargo toolchain")
    return _NativeTools(
        python=_probe_exact_tool(
            candidates["python3.14"], ("--version",), b"Python 3.14.6\n"
        ),
        uv=_probe_semantic_tool(candidates["uv"], "uv", "0.11.29"),
        cargo=cargo,
        cargo_fmt=cargo_fmt,
        rustc=rustc,
        rustdoc=rustdoc,
        rustfmt=rustfmt,
        git=_explicit_git(git_executable),
    )


def _safe_executable(path: Path) -> Path:
    if not isinstance(path, Path) or not path.is_absolute() or "\0" in os.fspath(path):
        raise CleanError("unsafe executable capability")
    try:
        resolved = path.resolve(strict=True)
        mode = path.lstat().st_mode
    except OSError as error:
        raise CleanError("unsafe executable capability") from error
    if (
        resolved != path
        or not stat.S_ISREG(mode)
        or mode & 0o022
        or not os.access(path, os.X_OK)
    ):
        raise CleanError("unsafe executable capability")
    return path


def _invoke(
    tool: Path,
    argv: list[str],
    environment: dict[str, str],
    *,
    cwd: Path,
    raw: bytes = b"",
    timeout: float = COMMAND_TIMEOUT,
    output_limit: int = OUTPUT_LIMIT,
) -> tuple[bytes, bytes]:
    executable = _safe_executable(tool)
    if not argv or argv[0] != str(executable) or type(environment) is not dict:
        raise CleanError("invalid fixed process invocation")
    try:
        result = _run(
            list(argv),
            raw,
            dict(environment),
            timeout=timeout,
            output_limit=output_limit,
            cwd=cwd,
        )
    except (OSError, RegistryError, ValueError) as error:
        raise CleanError("isolated process failed") from error
    _safe_executable(executable)
    if (
        type(result) is not tuple
        or len(result) != 2
        or type(result[0]) is not bytes
        or type(result[1]) is not bytes
    ):
        raise CleanError("isolated process returned invalid output")
    return result


def _git_environment(temporary: Path, git: Path) -> dict[str, str]:
    return {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(temporary / "bootstrap-home"),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": str(git.parent),
        "TMPDIR": str(temporary / "bootstrap-tmp"),
        "TZ": "UTC",
    }


def _checkout_git_environment(checkout: Path, git: Path) -> dict[str, str]:
    environment = _git_environment(checkout, git)
    environment["HOME"] = str(checkout / "artifacts/check-home")
    environment["TMPDIR"] = str(checkout / "artifacts/check-tmp")
    return environment


def _prepare_checkout_directories(checkout: Path) -> None:
    from golden_board.bootstrap import prepare_directories

    try:
        prepare_directories(checkout, acquisition=True)
    except ValueError as error:
        raise CleanError("unsafe checkout-local runtime directory") from error


def _prove_venv_ignore(
    repository: Path,
    git: Path,
    environment: dict[str, str],
) -> None:
    try:
        ignore = read_regular_below(repository, Path(".gitignore"), 64 * 1024)
    except (OSError, ValueError) as error:
        raise CleanError("tracked .venv ignore proof failed") from error
    if not ignore.startswith(b".venv/\n"):
        raise CleanError("tracked .venv ignore proof failed")
    tracked, tracked_error = _git_operation(
        repository,
        git,
        environment,
        ["ls-files", "--error-unmatch", "--", ".gitignore"],
    )
    ignored, ignored_error = _git_operation(
        repository,
        git,
        environment,
        ["check-ignore", "-v", "--", ".venv/"],
    )
    venv_tracked, venv_tracked_error = _git_operation(
        repository,
        git,
        environment,
        ["ls-files", "-z", "--", ".venv"],
    )
    if (
        tracked != b".gitignore\n"
        or tracked_error
        or ignored != b".gitignore:1:.venv/\t.venv/\n"
        or ignored_error
        or venv_tracked
        or venv_tracked_error
    ):
        raise CleanError("tracked .venv ignore proof failed")


def _git_runner(git: Path):
    def run(
        argv: list[str],
        raw: bytes,
        environment: dict[str, str],
        *,
        timeout: float,
        output_limit: int,
        cwd: Path | None = None,
    ) -> tuple[bytes, bytes]:
        if cwd is None:
            raise CleanError("Git operation requires a checkout")
        return _invoke(
            git,
            argv,
            environment,
            cwd=cwd,
            raw=raw,
            timeout=timeout,
            output_limit=output_limit,
        )

    return run


def _git_operation(
    root: Path,
    git: Path,
    environment: dict[str, str],
    suffix: list[str],
) -> tuple[bytes, bytes]:
    try:
        prefix = git_control_preflight(
            root,
            git_executable=git,
            git_environment=environment,
            runner=_git_runner(git),
        )
    except (OSError, ReportError, ValueError) as error:
        raise CleanError("Git control preflight failed") from error
    return _invoke(git, [*prefix, *suffix], environment, cwd=root)


def _clone_exact_head(source: Path, temporary: Path, git: Path) -> tuple[Path, str]:
    repository = _repository(source)
    temporary = _repository(temporary)
    checkout = temporary / "checkout"
    if checkout.exists() or checkout.is_symlink():
        raise CleanError("fresh checkout destination already exists")
    for name in ("bootstrap-home", "bootstrap-tmp", "git-template"):
        path = temporary / name
        path.mkdir(mode=0o700)
        if path.resolve(strict=True) != path or not path.is_dir() or path.is_symlink():
            raise CleanError("unsafe native bootstrap directory")
    environment = _git_environment(temporary, git)
    _prove_venv_ignore(repository, git, environment)
    status, status_error = _git_operation(
        repository,
        git,
        environment,
        ["status", "--porcelain=v1", "--untracked-files=all"],
    )
    if status or status_error:
        raise CleanError("source checkout is not clean")
    oid_raw, oid_error = _git_operation(
        repository,
        git,
        environment,
        ["rev-parse", "--verify", "HEAD^{commit}"],
    )
    if oid_error or OID.fullmatch(oid_raw) is None:
        raise CleanError("source HEAD is not an exact commit")
    oid = oid_raw[:-1].decode("ascii")

    try:
        git_control_preflight(
            repository,
            git_executable=git,
            git_environment=environment,
            runner=_git_runner(git),
        )
    except (OSError, ReportError, ValueError) as error:
        raise CleanError("Git control preflight failed") from error
    clone_prefix = [
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
    ]
    clone_out, clone_error = _invoke(
        git,
        [
            *clone_prefix,
            "clone",
            "--quiet",
            "--no-local",
            "--no-hardlinks",
            "--no-checkout",
            f"--template={temporary / 'git-template'}",
            "--",
            str(repository),
            str(checkout),
        ],
        environment,
        cwd=temporary,
    )
    if clone_out or clone_error:
        raise CleanError("exact HEAD clone failed")
    source_oid, source_oid_error = _git_operation(
        repository,
        git,
        environment,
        ["rev-parse", "--verify", "HEAD^{commit}"],
    )
    if source_oid_error or source_oid != oid_raw:
        raise CleanError("source HEAD moved during clone")
    checkout = _repository(checkout)
    _prepare_checkout_directories(checkout)
    checkout_environment = _checkout_git_environment(checkout, git)
    checkout_out, checkout_error = _git_operation(
        checkout,
        git,
        checkout_environment,
        ["checkout", "--quiet", "--detach", "--force", oid],
    )
    if checkout_out or checkout_error:
        raise CleanError("exact commit checkout failed")
    _prove_venv_ignore(checkout, git, checkout_environment)
    cloned_oid, cloned_error = _git_operation(
        checkout,
        git,
        checkout_environment,
        ["rev-parse", "--verify", "HEAD^{commit}"],
    )
    if cloned_error or cloned_oid != oid_raw:
        raise CleanError("fresh checkout HEAD differs")
    cloned_status, cloned_status_error = _git_operation(
        checkout,
        git,
        checkout_environment,
        ["status", "--porcelain=v1", "--untracked-files=all"],
    )
    if cloned_status or cloned_status_error:
        raise CleanError("fresh checkout is not clean")
    return checkout, oid


def _recheck_exact_head(
    source: Path,
    checkout: Path,
    temporary: Path,
    git: Path,
    oid: str,
) -> None:
    expected = oid.encode("ascii") + b"\n"
    for root, environment in (
        (source, _git_environment(temporary, git)),
        (checkout, _checkout_git_environment(checkout, git)),
    ):
        _prove_venv_ignore(root, git, environment)
        current, current_error = _git_operation(
            root,
            git,
            environment,
            ["rev-parse", "--verify", "HEAD^{commit}"],
        )
        status, status_error = _git_operation(
            root,
            git,
            environment,
            ["status", "--porcelain=v1", "--untracked-files=all"],
        )
        final, final_error = _git_operation(
            root,
            git,
            environment,
            ["rev-parse", "--verify", "HEAD^{commit}"],
        )
        if (
            current != expected
            or current_error
            or status
            or status_error
            or final != expected
            or final_error
        ):
            raise CleanError("exact HEAD changed during native verification")


def _build_native_evidence(
    root: Path,
    lock: SourceLock,
    git: Path,
) -> dict[str, object]:
    environment = _checkout_git_environment(root, git)
    try:
        source_raw = read_regular_below(
            root,
            PurePosixPath("reports/source-doctor.json"),
            MAX_REPORT_BYTES,
        )
        inventory = _native_inventory(
            root,
            git_executable=git,
            git_environment=environment,
        )
        value: dict[str, object] = {
            "schema_version": 0,
            "protocol": "native-isolated-v0",
            "result": "pass",
            "roadmap_revision": 1,
            "tool_versions": {
                "cargo": lock.toolchains.cargo,
                "cc": lock.toolchains.cc,
                "git": lock.toolchains.git,
                "ld": lock.toolchains.ld,
                "python": lock.toolchains.python,
                "rust": lock.toolchains.rust,
                "sdk": lock.toolchains.sdk,
                "uv": lock.toolchains.uv,
            },
            "isolation": EXPECTED_NATIVE_ISOLATION,
            "commands": EXPECTED_NATIVE_COMMANDS,
            "source_report_sha256": hashlib.sha256(source_raw).hexdigest(),
            "inputs": inventory,
        }
        return validate_native_evidence(
            root,
            value,
            git_executable=git,
            git_environment=environment,
        )
    except (OSError, ReportError, ValueError) as error:
        if isinstance(error, CleanError):
            raise
        raise CleanError("native evidence validation failed") from error


def _new_temporary_root() -> Path:
    try:
        root = Path(tempfile.mkdtemp(prefix="golden-board-native-")).resolve(
            strict=True
        )
        mode = root.lstat().st_mode
    except OSError as error:
        raise CleanError("cannot create isolated native workspace") from error
    if not stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
        raise CleanError("isolated native workspace is unsafe")
    return root


def _remove_temporary_root(root: Path) -> None:
    temporary = _repository(root)
    parent = _repository(temporary.parent)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    parent_descriptor: int | None = None
    descriptor: int | None = None
    try:
        parent_descriptor = os.open(parent, flags)
        before = os.stat(
            temporary.name, dir_fd=parent_descriptor, follow_symlinks=False
        )
        descriptor = os.open(temporary.name, flags, dir_fd=parent_descriptor)
        held = os.fstat(descriptor)
        parent_mount = held_mount_identity(parent_descriptor)
        mount = held_mount_identity(descriptor)
        if (
            _facts(before) != _facts(held)
            or not same_held_mount(parent_mount, descriptor, temporary)
            or mount != parent_mount
        ):
            raise CleanError("isolated workspace cleanup is unsafe")
        _delete_directory_contents(descriptor, temporary, mount)
        current = os.stat(
            temporary.name, dir_fd=parent_descriptor, follow_symlinks=False
        )
        if _identity(current) != _identity(held):
            raise CleanError("isolated workspace changed during cleanup")
        os.rmdir(temporary.name, dir_fd=parent_descriptor)
    except (OSError, ValueError) as error:
        if isinstance(error, CleanError):
            raise
        raise CleanError("isolated workspace cleanup failed") from error
    finally:
        for opened in (descriptor, parent_descriptor):
            if opened is not None:
                os.close(opened)


def _native_sdk() -> Path:
    from golden_board.bootstrap import _validate_sdk

    try:
        return _validate_sdk()
    except ValueError as error:
        raise CleanError("native SDK validation failed") from error


def _consume_native_link_probe(root: Path, output: Path) -> None:
    if output != root / "artifacts/check-tmp/native-link-probe":
        raise CleanError("native compiler link path drifted")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    leaf: int | None = None
    try:
        descriptors.append(os.open(root, flags))
        mount = held_mount_identity(descriptors[0])
        current = root
        for name in ("artifacts", "check-tmp"):
            child = os.open(name, flags, dir_fd=descriptors[-1])
            descriptors.append(child)
            current /= name
            if not same_held_mount(mount, child, current):
                raise CleanError("native compiler output directory is unsafe")
        leaf, held = _held_leaf(descriptors[-1], output.name, output, mount)
        if held.st_size <= 0 or held.st_mode & 0o111 == 0:
            raise CleanError("native compiler link result is invalid")
        current_leaf = os.stat(
            output.name, dir_fd=descriptors[-1], follow_symlinks=False
        )
        if _facts(held) != _facts(current_leaf):
            raise CleanError("native compiler link result changed")
        os.unlink(output.name, dir_fd=descriptors[-1])
        try:
            os.stat(output.name, dir_fd=descriptors[-1], follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise CleanError("native compiler link result survived cleanup")
    except OSError as error:
        raise CleanError("native compiler link result is invalid") from error
    finally:
        if leaf is not None:
            os.close(leaf)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _probe_native_platform(root: Path, tools: _NativeTools, lock: SourceLock) -> None:
    facts = os.uname()
    if (
        facts.sysname != "Darwin"
        or lock.toolchains.host != f"Darwin {facts.release} {facts.machine}"
        or lock.toolchains.cc != "Apple clang 17.0.0 (clang-1700.0.13.5) at /usr/bin/cc"
        or lock.toolchains.ld != "ld-1167.5 selected by /usr/bin/cc"
        or lock.toolchains.sdk != "macOS SDK 15.5 selected by /usr/bin/cc"
    ):
        raise CleanError("native platform differs from the source lock")
    if _native_sdk() != SDKROOT:
        raise CleanError("native SDK differs from the source lock")
    cc = _safe_executable(Path("/usr/bin/cc"))
    environment = _native_environment(root, tools, offline=False)
    version, version_error = _invoke(
        cc,
        [str(cc), "--version"],
        environment,
        cwd=root,
        timeout=TOOL_TIMEOUT,
    )
    if version_error or not version.startswith(
        b"Apple clang version 17.0.0 (clang-1700.0.13.5)\n"
    ):
        raise CleanError("native compiler differs from the source lock")
    output = root / "artifacts/check-tmp/native-link-probe"
    if output.exists() or output.is_symlink():
        raise CleanError("native compiler probe output already exists")
    trace_out, trace_error = _invoke(
        cc,
        [str(cc), "-###", "-x", "c", "-", "-o", str(output)],
        environment,
        cwd=root,
        timeout=TOOL_TIMEOUT,
    )
    trace = trace_error.decode("utf-8", "strict")
    required = (
        '"-target-sdk-version=15.5"',
        '"-target-linker-version" "1167.5"',
        f'"-isysroot" "{SDKROOT}"',
        f'"-syslibroot" "{SDKROOT}"',
        '"-lSystem"',
    )
    linker = (
        '\n "/Applications/Xcode.app/Contents/Developer/Toolchains/'
        'XcodeDefault.xctoolchain/usr/bin/ld" '
    )
    if (
        trace_out
        or not all(item in trace for item in required)
        or trace.count(linker) != 1
        or output.exists()
        or output.is_symlink()
    ):
        raise CleanError("native compiler trace differs from the source lock")
    link_out, link_error = _invoke(
        cc,
        [str(cc), "-x", "c", "-", "-o", str(output)],
        environment,
        cwd=root,
        raw=b"int main(void) { return 0; }\n",
        timeout=TOOL_TIMEOUT,
    )
    if link_out or link_error:
        raise CleanError("native compiler link probe failed")
    _consume_native_link_probe(root, output)


def verify_isolated_native(
    root: Path,
    *,
    git_executable: Path,
) -> dict[str, object]:
    repository = _repository(root)
    sealed_path = os.environ.get("PATH")
    if sealed_path is None:
        raise CleanError("sealed tool path is unavailable")
    tools = _resolve_native_tools(git_executable, sealed_path=sealed_path)
    temporary = _new_temporary_root()
    try:
        checkout, oid = _clone_exact_head(repository, temporary, tools.git)
        lock = load_source_lock(checkout)
        _static_dependency_preflight(checkout)
        _probe_native_platform(checkout, tools, lock)
        _run_native_phases(checkout, tools)
        evidence = _build_native_evidence(checkout, lock, tools.git)
        _recheck_exact_head(repository, checkout, temporary, tools.git, oid)
        return evidence
    except (OSError, UnicodeError, ValueError) as error:
        if isinstance(error, CleanError):
            raise
        raise CleanError("isolated native verification failed") from error
    finally:
        _remove_temporary_root(temporary)


DOCKER_SOCKET = Path("/var/run/docker.sock")
DOCKER_HOST = "unix:///var/run/docker.sock"
LINUX_PLATFORM = "linux/arm64/v8"
LINUX_IMAGE = "docker.io/library/rust:1.94.0-bookworm"
LINUX_PROTOCOL = "docker-clean-linux-v0"
LINUX_RUSTUP = "/usr/local/cargo/bin/rustup"
LINUX_RUSTUP_VERSION = "rustup 1.29.0 (28d1352db 2026-03-05)"
LINUX_RUSTUP_HOME = "/workspace/artifacts/cargo-home/rustup"
LINUX_RUST_SYSROOT = f"{LINUX_RUSTUP_HOME}/toolchains/1.94.0-aarch64-unknown-linux-gnu"
LINUX_RUST_BIN = f"{LINUX_RUST_SYSROOT}/bin"
LINUX_CC_VERSION = "12.2.0"
LINUX_LD_VERSION = "GNU ld (GNU Binutils for Debian) 2.40"
LINUX_LIBC_VERSION = "ldd (Debian GLIBC 2.36-9+deb12u13) 2.36"
_LINUX_TOKEN = re.compile(r"[A-Za-z0-9._+-]{1,64}\Z")


class _LinuxPrerequisite(CleanError):
    def __init__(self, blocker: str, observed: str | None = None) -> None:
        if blocker not in {
            "fixed_socket_inaccessible",
            "daemon_unreachable",
            "network_acquisition_unavailable",
            "immutable_image_unavailable",
        }:
            raise CleanError("invalid clean-Linux blocker")
        super().__init__(blocker)
        self.blocker = blocker
        self.observed = observed


@dataclass(frozen=True)
class _DockerClient:
    executable: Path
    temporary: Path
    prefix: tuple[str, ...]
    environment: dict[str, str]


@dataclass(frozen=True)
class _LinuxAcquisition:
    index: bytes
    manifest: bytes
    config: bytes
    uv_archive: bytes


@dataclass(frozen=True)
class _LinuxUvTool:
    path: Path
    byte_length: int
    sha256: str
    facts: tuple[int, int, int, int, int, int]


def _validate_linux_lock(lock: SourceLock) -> object:
    from golden_board import reference_acquisition as reference

    try:
        value = lock.clean_linux
        archive = next(
            artifact
            for artifact in reference.ARTIFACTS
            if artifact.id == "uv-linux-arm64-archive"
        )
        expected = {
            "mechanism": "docker",
            "image": LINUX_IMAGE,
            "digest": f"sha256:{reference.RUST_INDEX.sha256}",
            "platform_digest": f"sha256:{reference.RUST_PLATFORM.sha256}",
            "config_digest": f"sha256:{reference.RUST_CONFIG.sha256}",
            "platform": LINUX_PLATFORM,
            "uv_archive": archive.url,
            "uv_archive_sha256": archive.sha256,
            "docker_client": "25.0.3",
            "acquisition_protocol": "docker-acquire-v0",
            "offline_protocol": "docker-offline-v0",
            "deadline": "M2",
        }
        if any(
            getattr(value, name) != expected_value
            for name, expected_value in expected.items()
        ):
            raise CleanError("invalid clean-Linux lock")
        if tuple(value.mounts) != ("checkout", "uv-tool"):
            raise CleanError("invalid clean-Linux lock")
        daemon_tokens = (
            _available_daemon_tokens(value.observed_daemon_state)
            if type(value.observed_daemon_state) is str
            else ()
        )
        available = len(daemon_tokens) == 4 and all(
            _LINUX_TOKEN.fullmatch(token) is not None for token in daemon_tokens
        )
        unavailable = {
            "fixed_socket_inaccessible",
            "daemon_unreachable",
            "network_acquisition_unavailable",
            "immutable_image_unavailable",
        }
        canonical = (
            value.state == "planned"
            and value.blocker in unavailable
            and (
                value.observed_daemon_state == f"unavailable: {value.blocker}"
                or (
                    available
                    and value.blocker
                    in {
                        "network_acquisition_unavailable",
                        "immutable_image_unavailable",
                    }
                )
            )
        ) or (value.state == "verified" and not value.blocker and available)
        legacy = (
            value.state == "planned"
            and value.observed_daemon_state
            == "unavailable: permission denied for fixed unix:///var/run/docker.sock"
            and value.blocker
            == "Fixed Docker daemon socket unix:///var/run/docker.sock is not accessible on the primary host"
        )
        if not canonical and not legacy:
            raise CleanError("invalid clean-Linux lock")
    except (AttributeError, StopIteration, TypeError, ValueError) as error:
        if isinstance(error, CleanError):
            raise
        raise CleanError("invalid clean-Linux lock") from error
    return value


def _available_daemon_tokens(value: str) -> tuple[str, ...]:
    match = re.fullmatch(
        r"available: Docker Engine ([A-Za-z0-9._+-]{1,64}) "
        r"([A-Za-z0-9._+-]{1,64})/([A-Za-z0-9._+-]{1,64}) "
        r"kernel ([A-Za-z0-9._+-]{1,64})",
        value,
    )
    return match.groups() if match is not None else ()


def _probe_docker_tool(path: Path) -> Path:
    from golden_board.bootstrap import validate_docker_tool

    try:
        return validate_docker_tool(path, runner=_probe_runner)
    except ValueError as error:
        raise CleanError("invalid pinned Docker tool") from error


def _explicit_docker(path: Path) -> Path:
    _safe_executable(path)
    return _probe_docker_tool(path)


def _prepare_docker_client(temporary: Path, docker: Path) -> _DockerClient:
    root = _repository(temporary)
    for name in ("docker-config", "docker-home", "docker-tmp"):
        path = root / name
        try:
            path.mkdir(mode=0o700)
            if name == "docker-config":
                path.chmod(0o500)
            held = path.lstat()
        except OSError as error:
            raise CleanError("cannot create isolated Docker directory") from error
        expected_mode = 0o500 if name == "docker-config" else 0o700
        if (
            not stat.S_ISDIR(held.st_mode)
            or stat.S_IMODE(held.st_mode) != expected_mode
            or path.resolve(strict=True) != path
        ):
            raise CleanError("unsafe isolated Docker directory")
    environment = {
        "HOME": str(root / "docker-home"),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": str(docker.parent),
        "TMPDIR": str(root / "docker-tmp"),
        "TZ": "UTC",
    }
    return _DockerClient(
        executable=docker,
        temporary=root,
        prefix=(
            str(docker),
            "--config",
            str(root / "docker-config"),
            "--host",
            DOCKER_HOST,
        ),
        environment=environment,
    )


def _empty_docker_config(client: _DockerClient) -> None:
    root = _repository(client.temporary)
    expected = {
        "docker-config": 0o500,
        "docker-home": 0o700,
        "docker-tmp": 0o700,
    }
    for name, expected_mode in expected.items():
        path = root / name
        try:
            mode = path.lstat().st_mode
            entries = list(path.iterdir())
        except OSError as error:
            raise CleanError("unsafe Docker client configuration") from error
        if (
            not stat.S_ISDIR(mode)
            or stat.S_IMODE(mode) != expected_mode
            or path.is_symlink()
            or path.resolve(strict=True) != path
            or entries
        ):
            raise CleanError("unsafe Docker client configuration")


def _docker_call(
    client: _DockerClient,
    suffix: list[str],
    *,
    timeout: float = COMMAND_TIMEOUT,
    output_limit: int = OUTPUT_LIMIT,
) -> tuple[bytes, bytes]:
    if (
        type(suffix) is not list
        or not suffix
        or any(type(item) is not str or not item or "\0" in item for item in suffix)
    ):
        raise CleanError("invalid fixed Docker invocation")
    executable = _safe_executable(client.executable)
    if client.prefix[:1] != (str(executable),):
        raise CleanError("invalid fixed Docker invocation")
    _empty_docker_config(client)
    result = _run(
        [*client.prefix, *suffix],
        b"",
        dict(client.environment),
        timeout=timeout,
        output_limit=output_limit,
        cwd=client.temporary,
    )
    _safe_executable(executable)
    _empty_docker_config(client)
    return result


def _fixed_socket_available() -> bool:
    try:
        value = DOCKER_SOCKET.stat()
    except OSError as error:
        if error.errno == errno.EPERM:
            raise CleanError("Docker socket check is controller-confined") from error
        if error.errno in {errno.ENOENT, errno.ENOTDIR, errno.EACCES}:
            return False
        raise CleanError("Docker socket check failed") from error
    if not stat.S_ISSOCK(value.st_mode):
        return False
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.settimeout(1.0)
        probe.connect(os.fspath(DOCKER_SOCKET))
    except OSError as error:
        if error.errno == errno.EPERM:
            raise CleanError("Docker socket check is controller-confined") from error
        if error.errno in {errno.ENOENT, errno.ENOTDIR, errno.EACCES}:
            return False
        if error.errno == errno.ECONNREFUSED:
            return True
        raise CleanError("Docker socket connectivity check failed") from error
    finally:
        probe.close()
    return True


def _probe_docker_daemon(client: _DockerClient) -> str:
    if not _fixed_socket_available():
        raise _LinuxPrerequisite("fixed_socket_inaccessible")
    try:
        stdout, stderr = _docker_call(
            client,
            [
                "info",
                "--format",
                "{{.ServerVersion}}\t{{.OSType}}\t{{.Architecture}}\t{{.KernelVersion}}",
            ],
            timeout=TOOL_TIMEOUT,
            output_limit=512,
        )
    except RegistryError as error:
        if str(error).startswith("registry.process_exit:"):
            raise _LinuxPrerequisite("daemon_unreachable") from error
        raise CleanError("Docker daemon probe failed closed") from error
    try:
        fields = stdout[:-1].decode("ascii").split("\t")
    except UnicodeError as error:
        raise CleanError("invalid Docker daemon observation") from error
    if (
        stderr
        or not stdout.endswith(b"\n")
        or len(fields) != 4
        or any(_LINUX_TOKEN.fullmatch(field) is None for field in fields)
    ):
        raise CleanError("invalid Docker daemon observation")
    version, operating_system, architecture, kernel = fields
    return (
        f"available: Docker Engine {version} "
        f"{operating_system}/{architecture} kernel {kernel}"
    )


def _linux_network_get(
    url: str,
    accept: str,
    maximum: int,
    authorization: str | None = None,
) -> bytes:
    from golden_board import reference_acquisition as reference

    try:
        return reference._get(url, accept, maximum, authorization)
    except reference.AcquisitionError as error:
        detail = str(error)
        if detail in {f"network: {url}", f"network returned no bytes: {url}"}:
            raise _LinuxPrerequisite("network_acquisition_unavailable") from error
        raise CleanError("clean-Linux network adapter failed closed") from error


def _verified_linux_download(artifact: object, authorization: str | None) -> bytes:
    from golden_board import reference_acquisition as reference

    raw = _linux_network_get(
        artifact.url,
        artifact.accept,
        artifact.byte_length,
        authorization,
    )
    try:
        reference.verify_bytes(artifact, raw)
    except reference.AcquisitionError as error:
        raise CleanError("clean-Linux immutable acquisition bytes differ") from error
    return raw


def _acquire_linux_inputs(clean_lock: object) -> _LinuxAcquisition:
    from golden_board import reference_acquisition as reference

    token_raw = _linux_network_get(
        reference.TOKEN_URL,
        "application/json",
        65_536,
    )
    try:
        token = json.loads(token_raw)["token"]
    except (
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise CleanError("invalid immutable-registry token response") from error
    if (
        type(token) is not str
        or re.fullmatch(r"[A-Za-z0-9._~+/=-]{1,8192}", token) is None
    ):
        raise CleanError("invalid immutable-registry token response")
    authorization = f"Bearer {token}"
    index = _verified_linux_download(reference.RUST_INDEX, authorization)
    try:
        platform = reference.select_linux_arm64_manifest(index)
    except reference.AcquisitionError as error:
        raise CleanError("invalid immutable OCI index") from error
    if platform != (
        clean_lock.platform_digest,
        reference.RUST_PLATFORM.byte_length,
    ):
        raise CleanError("immutable OCI platform descriptor differs")

    manifest = _verified_linux_download(reference.RUST_PLATFORM, authorization)
    try:
        config_descriptor = reference.select_image_config(manifest)
    except reference.AcquisitionError as error:
        raise CleanError("invalid immutable OCI manifest") from error
    if config_descriptor != (
        clean_lock.config_digest,
        reference.RUST_CONFIG.byte_length,
    ):
        raise CleanError("immutable OCI config descriptor differs")

    config = _verified_linux_download(reference.RUST_CONFIG, authorization)
    try:
        reference.validate_image_config(config)
    except reference.AcquisitionError as error:
        raise CleanError("immutable OCI config differs") from error
    archive = next(
        artifact
        for artifact in reference.ARTIFACTS
        if artifact.id == "uv-linux-arm64-archive"
    )
    if (
        archive.url != clean_lock.uv_archive
        or archive.sha256 != clean_lock.uv_archive_sha256
    ):
        raise CleanError("immutable uv declaration differs")
    uv_archive = _verified_linux_download(archive, None)
    return _LinuxAcquisition(index, manifest, config, uv_archive)


def _extract_linux_uv(raw: bytes) -> bytes:
    if type(raw) is not bytes or not 0 < len(raw) <= 32 * 1024 * 1024:
        raise CleanError("invalid uv archive")
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r|gz") as archive:
            expected = (
                ("uv-aarch64-unknown-linux-gnu", "directory", 0),
                ("uv-aarch64-unknown-linux-gnu/uvx", "file", 1024 * 1024),
                ("uv-aarch64-unknown-linux-gnu/uv", "file", 64 * 1024 * 1024),
            )
            payload: bytes | None = None
            for name, kind, maximum in expected:
                member = archive.next()
                if (
                    member is None
                    or member.name != name
                    or member.mode & 0o777 != 0o755
                    or (
                        kind == "directory" and (not member.isdir() or member.size != 0)
                    )
                    or (
                        kind == "file"
                        and (not member.isreg() or not 0 < member.size <= maximum)
                    )
                ):
                    raise CleanError("invalid uv archive members")
                if name.endswith("/uv"):
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise CleanError("invalid uv archive member")
                    payload = stream.read(member.size + 1)
                    if len(payload) != member.size:
                        raise CleanError("invalid uv archive member")
            if archive.next() is not None or payload is None:
                raise CleanError("invalid uv archive members")
            return payload
    except (EOFError, OSError, tarfile.TarError) as error:
        raise CleanError("invalid uv archive") from error


def _materialize_linux_uv(temporary: Path, archive: bytes) -> _LinuxUvTool:
    root = _repository(temporary)
    payload = _extract_linux_uv(archive)
    directory = root / "uv-tool"
    root_descriptor: int | None = None
    descriptor: int | None = None
    leaf: int | None = None
    try:
        root_descriptor = os.open(
            root,
            os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        mount = held_mount_identity(root_descriptor)
        directory.mkdir(mode=0o700)
        descriptor = os.open(
            "uv-tool",
            os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=root_descriptor,
        )
        directory_facts = os.fstat(descriptor)
        if _facts(directory_facts) != _facts(directory.lstat()) or not same_held_mount(
            mount, descriptor, directory
        ):
            raise CleanError("unsafe uv tool directory")
        leaf = os.open(
            "uv",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o555,
            dir_fd=descriptor,
        )
        _write_all(leaf, payload)
        os.fchmod(leaf, 0o555)
        os.fsync(leaf)
        held = os.fstat(leaf)
        named = os.stat("uv", dir_fd=descriptor, follow_symlinks=False)
        path = directory / "uv"
        if (
            not stat.S_ISREG(held.st_mode)
            or held.st_size != len(payload)
            or held.st_mode & 0o777 != 0o555
            or _facts(held) != _facts(named)
            or not same_held_mount(mount, leaf, path)
        ):
            raise CleanError("unsafe uv tool capability")
        closing = leaf
        leaf = None
        os.close(closing)
        leaf = os.open(
            "uv",
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=descriptor,
        )
        _read_exact(leaf, payload)
        if _facts(os.fstat(leaf)) != _facts(held):
            raise CleanError("uv tool capability changed")
        tool = _LinuxUvTool(
            path,
            len(payload),
            hashlib.sha256(payload).hexdigest(),
            _facts(held),
        )
        _validate_linux_uv_tool(root, tool)
        return tool
    except (OSError, ValueError) as error:
        if isinstance(error, CleanError):
            raise
        raise CleanError("cannot materialize uv tool capability") from error
    finally:
        for opened in (leaf, descriptor, root_descriptor):
            if opened is not None:
                os.close(opened)


def _validate_linux_uv_tool(temporary: Path, tool: _LinuxUvTool) -> Path:
    root = _repository(temporary)
    expected = root / "uv-tool/uv"
    if (
        not isinstance(tool, _LinuxUvTool)
        or tool.path != expected
        or type(tool.byte_length) is not int
        or not 0 < tool.byte_length <= 64 * 1024 * 1024
        or re.fullmatch(r"[0-9a-f]{64}", tool.sha256) is None
        or type(tool.facts) is not tuple
        or len(tool.facts) != 6
        or any(type(value) is not int for value in tool.facts)
    ):
        raise CleanError("invalid uv tool capability")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    leaf: int | None = None
    try:
        descriptors.append(os.open(root, flags))
        mount = held_mount_identity(descriptors[0])
        before = os.stat("uv-tool", dir_fd=descriptors[0], follow_symlinks=False)
        descriptors.append(os.open("uv-tool", flags, dir_fd=descriptors[0]))
        held_directory = os.fstat(descriptors[1])
        if _facts(before) != _facts(held_directory) or not same_held_mount(
            mount, descriptors[1], root / "uv-tool"
        ):
            raise CleanError("uv tool directory changed")
        with os.scandir(descriptors[1]) as iterator:
            if sorted(entry.name for entry in iterator) != ["uv"]:
                raise CleanError("uv tool directory changed")
        leaf = os.open(
            "uv",
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=descriptors[1],
        )
        held = os.fstat(leaf)
        named = os.stat("uv", dir_fd=descriptors[1], follow_symlinks=False)
        if (
            not stat.S_ISREG(held.st_mode)
            or held.st_mode & 0o777 != 0o555
            or held.st_size != tool.byte_length
            or _facts(held) != tool.facts
            or _facts(held) != _facts(named)
            or not same_held_mount(mount, leaf, expected)
        ):
            raise CleanError("uv tool capability changed")
        digest = hashlib.sha256()
        total = 0
        while total <= tool.byte_length:
            chunk = os.read(leaf, min(64 * 1024, tool.byte_length + 1 - total))
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
        after = os.fstat(leaf)
        current = os.stat("uv", dir_fd=descriptors[1], follow_symlinks=False)
        if (
            total != tool.byte_length
            or digest.hexdigest() != tool.sha256
            or _facts(after) != _facts(held)
            or _facts(current) != _facts(held)
        ):
            raise CleanError("uv tool capability changed")
        return expected
    except (OSError, ValueError) as error:
        if isinstance(error, CleanError):
            raise
        raise CleanError("uv tool capability changed") from error
    finally:
        if leaf is not None:
            os.close(leaf)
        for opened in reversed(descriptors):
            os.close(opened)


def _linux_image_reference(clean_lock: object) -> str:
    value = f"docker.io/library/rust@{clean_lock.platform_digest}"
    if re.fullmatch(r"docker\.io/library/rust@sha256:[0-9a-f]{64}", value) is None:
        raise CleanError("invalid immutable Linux image reference")
    return value


def _pull_linux_image(client: _DockerClient, clean_lock: object) -> str:
    image = _linux_image_reference(clean_lock)
    try:
        _docker_call(
            client,
            ["pull", "--platform", LINUX_PLATFORM, image],
            timeout=COMMAND_TIMEOUT,
            output_limit=4 * 1024 * 1024,
        )
    except RegistryError as error:
        raise CleanError("immutable image pull failed closed") from error
    return image


def _validate_local_linux_image(
    client: _DockerClient,
    clean_lock: object,
    image: str,
) -> None:
    from golden_board import reference_acquisition as reference

    if image != _linux_image_reference(clean_lock):
        raise CleanError("invalid local immutable image reference")
    try:
        stdout, stderr = _docker_call(
            client,
            ["image", "inspect", image],
            timeout=TOOL_TIMEOUT,
            output_limit=1024 * 1024,
        )
        document = json.loads(stdout)
        value = document[0]
        config = value["Config"]
    except (
        IndexError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise CleanError("invalid local immutable image") from error
    if (
        stderr
        or type(document) is not list
        or len(document) != 1
        or type(value) is not dict
        or value.get("Id") != clean_lock.config_digest
        or value.get("Architecture") != "arm64"
        or value.get("Os") != "linux"
        or type(config) is not dict
        or config.get("Env") != list(reference.IMAGE_ENV)
        or config.get("Entrypoint") is not None
        or config.get("Cmd") != ["bash"]
    ):
        raise CleanError("invalid local immutable image")


def _probe_linux_cargo_fmt(
    root: Path,
    cargo: Path,
    cargo_fmt: Path,
    rustc: Path,
    rustdoc: Path,
    rustfmt: Path,
) -> None:
    if (
        cargo_fmt != cargo.parent / "cargo-fmt"
        or rustc != cargo.parent / "rustc"
        or rustdoc != cargo.parent / "rustdoc"
        or rustfmt != cargo.parent / "rustfmt"
    ):
        raise CleanError("invalid cargo-fmt dispatch")
    stdout, stderr = _invoke(
        cargo,
        [str(cargo), "fmt", "--version"],
        {
            "CARGO_CACHE_AUTO_CLEAN_FREQUENCY": "never",
            "CARGO_HOME": str(root / "artifacts/cargo-home"),
            "CARGO_REGISTRIES_CRATES_IO_PROTOCOL": "sparse",
            "HOME": str(root / "artifacts/check-home"),
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": str(cargo.parent),
            "RUSTC": str(rustc),
            "RUSTDOC": str(rustdoc),
            "RUSTFMT": str(rustfmt),
            "TMPDIR": str(root / "artifacts/check-tmp"),
            "TZ": "UTC",
        },
        cwd=root,
        timeout=TOOL_TIMEOUT,
        output_limit=512,
    )
    if (
        stderr
        or re.fullmatch(
            rb"rustfmt 1\.8\.0(?:-stable)?"
            rb"(?: \([A-Za-z0-9][A-Za-z0-9._+:/ -]{0,127}\)){0,2}\n\Z",
            stdout,
        )
        is None
    ):
        raise CleanError("invalid project-local cargo-fmt dispatch")


def _validate_linux_rust_toolchain(root: Path) -> None:
    repository = _repository(root)
    parts = (
        "artifacts",
        "cargo-home",
        "rustup",
        "toolchains",
        "1.94.0-aarch64-unknown-linux-gnu",
        "bin",
    )
    versions = (
        ("cargo", "cargo", "1.94.0"),
        ("rustc", "rustc", "1.94.0"),
        ("rustdoc", "rustdoc", "1.94.0"),
        ("rustfmt", "rustfmt", "1.8.0"),
        ("cargo-fmt", "rustfmt", "1.8.0"),
    )
    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    directories: list[int] = []
    files: list[tuple[str, Path, int, os.stat_result]] = []
    try:
        directories.append(os.open(repository, directory_flags))
        mount = held_mount_identity(directories[0])
        current = repository
        for name in parts:
            before = os.stat(
                name,
                dir_fd=directories[-1],
                follow_symlinks=False,
            )
            child = os.open(name, directory_flags, dir_fd=directories[-1])
            directories.append(child)
            current /= name
            held = os.fstat(child)
            after = os.stat(
                name,
                dir_fd=directories[-2],
                follow_symlinks=False,
            )
            if (
                not stat.S_ISDIR(held.st_mode)
                or held.st_mode & 0o022
                or _facts(before) != _facts(held)
                or _facts(after) != _facts(held)
                or not same_held_mount(mount, child, current)
            ):
                raise CleanError("unsafe project-local Rust toolchain")

        def validate_namespace() -> None:
            named_path = repository
            for index, name in enumerate(parts):
                named_path /= name
                held = os.fstat(directories[index + 1])
                named = os.stat(
                    name,
                    dir_fd=directories[index],
                    follow_symlinks=False,
                )
                path_stat = named_path.lstat()
                if (
                    _facts(named) != _facts(held)
                    or _facts(path_stat) != _facts(held)
                    or not same_held_mount(
                        mount,
                        directories[index + 1],
                        named_path,
                    )
                ):
                    raise CleanError("unsafe project-local Rust toolchain")

        for name, semantic_name, version in versions:
            before = os.stat(
                name,
                dir_fd=directories[-1],
                follow_symlinks=False,
            )
            descriptor = os.open(name, file_flags, dir_fd=directories[-1])
            path = current / name
            held = os.fstat(descriptor)
            after = os.stat(
                name,
                dir_fd=directories[-1],
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(held.st_mode)
                or held.st_mode & 0o022
                or held.st_mode & 0o111 == 0
                or _facts(before) != _facts(held)
                or _facts(after) != _facts(held)
                or not same_held_mount(mount, descriptor, path)
            ):
                os.close(descriptor)
                raise CleanError("unsafe project-local Rust toolchain")
            files.append((semantic_name, path, descriptor, held))
            validate_namespace()
            if _probe_semantic_tool(path, semantic_name, version) != path:
                raise CleanError("unsafe project-local Rust toolchain")
            validate_namespace()

        _probe_linux_cargo_fmt(
            repository,
            current / "cargo",
            current / "cargo-fmt",
            current / "rustc",
            current / "rustdoc",
            current / "rustfmt",
        )
        validate_namespace()

        for (_name, path, descriptor, held), (leaf, _semantic, _version) in zip(
            files,
            versions,
            strict=True,
        ):
            named = os.stat(
                leaf,
                dir_fd=directories[-1],
                follow_symlinks=False,
            )
            if (
                _facts(os.fstat(descriptor)) != _facts(held)
                or _facts(named) != _facts(held)
                or not same_held_mount(mount, descriptor, path)
            ):
                raise CleanError("unsafe project-local Rust toolchain")
    except (OSError, ValueError) as error:
        if isinstance(error, CleanError):
            raise
        raise CleanError("unsafe project-local Rust toolchain") from error
    finally:
        for _name, _path, descriptor, _held in reversed(files):
            os.close(descriptor)
        for descriptor in reversed(directories):
            os.close(descriptor)


_LINUX_PROBE_SCRIPT = """set -eu
probe=/workspace/artifacts/check-tmp/linux-link-probe
test ! -e "$probe"
trap '/usr/bin/rm -f "$probe"' EXIT HUP INT TERM
uv=$(/opt/golden-board/uv --version)
rustup=$(cd / && RUSTUP_HOME=/usr/local/rustup CARGO_HOME=/usr/local/cargo /usr/local/cargo/bin/rustup --version 2>/dev/null)
git=$(/usr/bin/git --version)
cc=$(/usr/bin/cc -dumpfullversion)
ld=$(/usr/bin/ld --version | /usr/bin/head -n 1)
libc=$(/usr/bin/ldd --version | /usr/bin/head -n 1)
arch=$(/usr/bin/uname -m)
shell=$(/bin/sh -p -c 'printf shell-ok')
driver=$(/usr/bin/cc -print-prog-name=ld)
test "$driver" = /usr/bin/aarch64-linux-gnu-ld
trace=$(/usr/bin/cc -### -x c - -o "$probe" </dev/null 2>&1)
case "$trace" in *collect2*ld-linux-aarch64.so.1*) ;; *) exit 32 ;; esac
link_trace=$(printf 'int main(void) { return 0; }\n' | /usr/bin/cc -Wl,-t -x c - -o "$probe" 2>&1)
case "$link_trace" in *libc.so*) ;; *) exit 33 ;; esac
interpreter=$(/usr/bin/readelf -l "$probe")
case "$interpreter" in *'/lib/ld-linux-aarch64.so.1'*) ;; *) exit 34 ;; esac
"$probe"
/usr/bin/rm -f "$probe"
trap - EXIT HUP INT TERM
printf 'linux-image-probe-v0\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n' "$uv" "$rustup" "$git" "$cc" "$ld" "$libc" "$arch" "$shell"
"""


_LINUX_ACQUIRE_SCRIPT = """set -eu
cd /workspace
/usr/local/cargo/bin/rustup toolchain install 1.94.0-aarch64-unknown-linux-gnu --profile minimal --component rustfmt --no-self-update >/dev/null 2>&1
local=/workspace/artifacts/cargo-home/rustup/toolchains/1.94.0-aarch64-unknown-linux-gnu
/opt/golden-board/uv python install 3.14.6 >/dev/null 2>&1
managed_python=$(/opt/golden-board/uv python find 3.14.6)
test "$managed_python" = /workspace/artifacts/uv-python/cpython-3.14.6-linux-aarch64-gnu/bin/python3.14
"$managed_python" -I -S -B -c 'import sys; from pathlib import Path; prefix=Path("/workspace/artifacts/uv-python/cpython-3.14.6-linux-aarch64-gnu"); executable=prefix/"bin/python3.14"; assert sys.version_info[:3] == (3, 14, 6); assert Path(sys.executable) == executable; assert Path(sys.prefix) == prefix == Path(sys.base_prefix); assert prefix.resolve(strict=True) == prefix; assert executable.resolve(strict=True).is_relative_to(prefix); sys.path.insert(0,"/workspace/python"); from golden_board.clean import _validate_linux_rust_toolchain; _validate_linux_rust_toolchain(Path("/workspace"))'
/opt/golden-board/uv --no-config sync --project . --locked >/dev/null 2>&1
test "$(command -v python)" = /workspace/.venv/bin/python
test "$(command -v python3)" = /workspace/.venv/bin/python3
test "$(command -v python3.14)" = /workspace/.venv/bin/python3.14
"$local/bin/cargo" fetch --manifest-path Cargo.toml --locked >/dev/null 2>&1
"$local/bin/cargo" build --manifest-path Cargo.toml --workspace --locked >/dev/null 2>&1
PYTHONPATH=/workspace/python /workspace/.venv/bin/python -P -B -S -c 'from pathlib import Path; from golden_board.bootstrap import validate_venv; from golden_board.acquisition import build_inventory, load_inventory, write_inventory; root=Path("/workspace"); validate_venv(root); value=build_inventory(root); write_inventory(root,value); assert load_inventory(root)==value'
printf 'docker-acquire-v0\n'
"""


_LINUX_OFFLINE_SCRIPT = """set -eu
cd /workspace
managed_python=$(/opt/golden-board/uv python find 3.14.6)
test "$managed_python" = /workspace/artifacts/uv-python/cpython-3.14.6-linux-aarch64-gnu/bin/python3.14
rust_tools() {
  "$managed_python" -I -S -B -c 'import sys; from pathlib import Path; prefix=Path("/workspace/artifacts/uv-python/cpython-3.14.6-linux-aarch64-gnu"); executable=prefix/"bin/python3.14"; assert sys.version_info[:3] == (3, 14, 6); assert Path(sys.executable) == executable; assert Path(sys.prefix) == prefix == Path(sys.base_prefix); assert prefix.resolve(strict=True) == prefix; assert executable.resolve(strict=True).is_relative_to(prefix); sys.path.insert(0,"/workspace/python"); from golden_board.clean import _validate_linux_rust_toolchain; _validate_linux_rust_toolchain(Path("/workspace"))'
}
rust_tools
/opt/golden-board/uv --no-config sync --project . --offline --locked >/dev/null 2>&1
test "$(command -v python)" = /workspace/.venv/bin/python
test "$(command -v python3)" = /workspace/.venv/bin/python3
test "$(command -v python3.14)" = /workspace/.venv/bin/python3.14
rust_tools
"/workspace/artifacts/cargo-home/rustup/toolchains/1.94.0-aarch64-unknown-linux-gnu/bin/cargo" build --manifest-path Cargo.toml --workspace --offline --locked >/dev/null 2>&1
inventory() {
  PYTHONPATH=/workspace/python /workspace/.venv/bin/python -P -B -S -c 'from pathlib import Path; from golden_board.bootstrap import validate_venv; from golden_board.acquisition import build_inventory, load_inventory; root=Path("/workspace"); validate_venv(root); assert build_inventory(root)==load_inventory(root)'
}
full() {
  /usr/bin/env -i LANG=C LC_ALL=C PATH=/workspace/.venv/bin:/opt/golden-board:/workspace/artifacts/cargo-home/rustup/toolchains/1.94.0-aarch64-unknown-linux-gnu/bin:/usr/bin:/bin TZ=UTC GB_CLEAN_LINUX_DIGEST="$GB_CLEAN_LINUX_DIGEST" CC=/usr/bin/cc COMPILER_PATH=/usr/bin CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=/usr/bin/cc RUSTC=/workspace/artifacts/cargo-home/rustup/toolchains/1.94.0-aarch64-unknown-linux-gnu/bin/rustc RUSTDOC=/workspace/artifacts/cargo-home/rustup/toolchains/1.94.0-aarch64-unknown-linux-gnu/bin/rustdoc RUSTFMT=/workspace/artifacts/cargo-home/rustup/toolchains/1.94.0-aarch64-unknown-linux-gnu/bin/rustfmt RUSTUP_HOME=/workspace/artifacts/cargo-home/rustup /workspace/scripts/check full
}
inventory
rust_tools
full
inventory
rust_tools
full
inventory
printf 'docker-offline-v0\n'
"""


def _linux_phase_environment(clean_lock: object, phase: str) -> tuple[str, ...]:
    if phase not in {"probe", "acquire", "offline"}:
        raise CleanError("invalid clean-Linux phase")
    values = {
        "CARGO_CACHE_AUTO_CLEAN_FREQUENCY": "never",
        "CARGO_HOME": "/workspace/artifacts/cargo-home",
        "CARGO_REGISTRIES_CRATES_IO_PROTOCOL": "sparse",
        "CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER": "/usr/bin/cc",
        "CARGO_TARGET_DIR": "/workspace/artifacts/cargo-target",
        "CC": "/usr/bin/cc",
        "COMPILER_PATH": "/usr/bin",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": "/workspace/artifacts/check-home",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": f"/workspace/.venv/bin:/opt/golden-board:{LINUX_RUST_BIN}",
        "RUSTC": f"{LINUX_RUST_BIN}/rustc",
        "RUSTDOC": f"{LINUX_RUST_BIN}/rustdoc",
        "RUSTFMT": f"{LINUX_RUST_BIN}/rustfmt",
        "RUSTUP_HOME": LINUX_RUSTUP_HOME,
        "TMPDIR": "/workspace/artifacts/check-tmp",
        "TZ": "UTC",
        "UV_CACHE_DIR": "/workspace/artifacts/uv-cache",
        "UV_MANAGED_PYTHON": "true",
        "UV_NO_CONFIG": "1",
        "UV_PYTHON_INSTALL_DIR": "/workspace/artifacts/uv-python",
        "UV_PROJECT_ENVIRONMENT": ".venv",
    }
    if phase == "offline":
        values.update(
            {
                "CARGO_NET_OFFLINE": "true",
                "GB_CLEAN_LINUX_DIGEST": clean_lock.platform_digest,
                "UV_OFFLINE": "1",
                "UV_PYTHON_DOWNLOADS": "never",
            }
        )
    return tuple(f"{name}={values[name]}" for name in sorted(values))


def _validate_linux_checkout_mount(temporary: Path, checkout: Path) -> Path:
    root = _repository(temporary)
    repository = _repository(checkout)
    if repository != root / "checkout" or "," in os.fspath(repository):
        raise CleanError("invalid clean-Linux checkout mount")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    parent: int | None = None
    child: int | None = None
    try:
        parent = os.open(root, flags)
        mount = held_mount_identity(parent)
        before = os.stat("checkout", dir_fd=parent, follow_symlinks=False)
        child = os.open("checkout", flags, dir_fd=parent)
        held = os.fstat(child)
        if (
            _facts(before) != _facts(held)
            or _facts(repository.lstat()) != _facts(held)
            or not same_held_mount(mount, child, repository)
        ):
            raise CleanError("invalid clean-Linux checkout mount")
        return repository
    except OSError as error:
        raise CleanError("invalid clean-Linux checkout mount") from error
    finally:
        for opened in (child, parent):
            if opened is not None:
                os.close(opened)


def _linux_container_argv(
    temporary: Path,
    checkout: Path,
    uv: _LinuxUvTool,
    clean_lock: object,
    image: str,
    *,
    phase: str,
    name: str,
    cidfile: Path,
) -> list[str]:
    root = _repository(temporary)
    repository = _validate_linux_checkout_mount(root, checkout)
    uv_path = _validate_linux_uv_tool(root, uv)
    if (
        image != _linux_image_reference(clean_lock)
        or re.fullmatch(
            rf"golden-board-m0-{phase}-[0-9a-f]{{16}}",
            name,
        )
        is None
        or cidfile != root / f"container-{phase}.cid"
        or cidfile.exists()
        or cidfile.is_symlink()
        or any(
            character in ",\0\r\n" for character in f"{repository}{uv_path}{cidfile}"
        )
    ):
        raise CleanError("invalid fixed clean-Linux container")
    scripts = {
        "probe": _LINUX_PROBE_SCRIPT,
        "acquire": _LINUX_ACQUIRE_SCRIPT,
        "offline": _LINUX_OFFLINE_SCRIPT,
    }
    try:
        script = scripts[phase]
    except KeyError as error:
        raise CleanError("invalid clean-Linux phase") from error
    user = os.getuid()
    group = os.getgid()
    if (
        type(user) is not int
        or type(group) is not int
        or not 0 <= user <= 2_147_483_647
        or not 0 <= group <= 2_147_483_647
    ):
        raise CleanError("invalid clean-Linux container user")
    argv = [
        "run",
        "--name",
        name,
        "--user",
        f"{user}:{group}",
        "--cidfile",
        str(cidfile),
        "--platform",
        LINUX_PLATFORM,
        "--pull=never",
    ]
    if phase != "acquire":
        argv.extend(("--network", "none"))
    argv.extend(
        (
            "--workdir",
            "/workspace",
            "--mount",
            f"type=bind,src={repository},dst=/workspace",
            "--mount",
            f"type=bind,src={uv_path},dst=/opt/golden-board/uv,readonly",
            image,
            "/usr/bin/env",
            "-i",
            *_linux_phase_environment(clean_lock, phase),
            "/bin/sh",
            "-p",
            "-c",
            script,
        )
    )
    return argv


def _validate_linux_probe_output(stdout: bytes, stderr: bytes) -> None:
    try:
        if not stdout.endswith(b"\n") or b"\r" in stdout or b"\0" in stdout:
            raise CleanError("invalid clean-Linux image probe")
        lines = stdout[:-1].decode("ascii").split("\n")
    except UnicodeError as error:
        raise CleanError("invalid clean-Linux image probe") from error
    semantic = ((3, r"git version 2\.[0-9]{1,3}\.[0-9]{1,3}"),)
    if (
        stderr
        or len(stdout) > 4096
        or len(lines) != 9
        or lines[0] != "linux-image-probe-v0"
        or lines[1] != "uv 0.11.29 (aarch64-unknown-linux-gnu)"
        or lines[2] != LINUX_RUSTUP_VERSION
        or any(
            re.fullmatch(pattern, lines[index]) is None for index, pattern in semantic
        )
        or lines[4] != LINUX_CC_VERSION
        or lines[5] != LINUX_LD_VERSION
        or lines[6] != LINUX_LIBC_VERSION
        or lines[7:] != ["aarch64", "shell-ok"]
    ):
        raise CleanError("invalid clean-Linux image probe")


def _linux_container_identity(
    client: _DockerClient,
    phase: str,
) -> tuple[str, Path]:
    if phase not in {"probe", "acquire", "offline"}:
        raise CleanError("invalid clean-Linux phase")
    root = _repository(client.temporary)
    token = hashlib.sha256(os.fsencode(root)).hexdigest()[:16]
    return (
        f"golden-board-m0-{phase}-{token}",
        root / f"container-{phase}.cid",
    )


def _prove_linux_container_name_absent(
    client: _DockerClient,
    name: str,
) -> None:
    if (
        re.fullmatch(
            r"golden-board-m0-(?:probe|acquire|offline)-[0-9a-f]{16}",
            name,
        )
        is None
    ):
        raise CleanError("invalid clean-Linux container name")
    stdout, stderr = _docker_call(
        client,
        [
            "container",
            "ls",
            "--all",
            "--no-trunc",
            "--quiet",
            "--filter",
            f"name=^/{name}$",
        ],
        timeout=TOOL_TIMEOUT,
        output_limit=512,
    )
    if stdout or stderr:
        raise CleanError("Docker container name is not absent")


def _cleanup_linux_container(
    client: _DockerClient,
    name: str,
    cidfile: Path,
    *,
    required: bool,
) -> None:
    root = _repository(client.temporary)
    match = re.fullmatch(
        r"golden-board-m0-(probe|acquire|offline)-[0-9a-f]{16}",
        name,
    )
    if (
        match is None
        or cidfile.parent != root
        or cidfile.name != f"container-{match.group(1)}.cid"
    ):
        raise CleanError("invalid clean-Linux container cleanup")
    directory: int | None = None
    leaf: int | None = None
    try:
        directory = os.open(
            root,
            os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        mount = held_mount_identity(directory)
        try:
            before = os.stat(cidfile.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            _prove_linux_container_name_absent(client, name)
            if required:
                raise CleanError("successful Docker run omitted its cidfile")
            return
        leaf = os.open(
            cidfile.name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory,
        )
        held = os.fstat(leaf)
        if (
            not stat.S_ISREG(held.st_mode)
            or held.st_size != 64
            or _facts(before) != _facts(held)
            or not same_held_mount(mount, leaf, cidfile)
        ):
            raise CleanError("unsafe Docker cidfile")
        raw = os.read(leaf, 65)
        if re.fullmatch(rb"[0-9a-f]{64}", raw) is None:
            raise CleanError("invalid Docker cidfile")
        container_id = raw.decode("ascii")
        inspect_stdout, inspect_stderr = _docker_call(
            client,
            [
                "container",
                "inspect",
                "--format",
                "{{.Id}}\t{{.Name}}",
                container_id,
            ],
            timeout=TOOL_TIMEOUT,
            output_limit=512,
        )
        if (
            inspect_stdout != f"{container_id}\t/{name}\n".encode("ascii")
            or inspect_stderr
        ):
            raise CleanError("Docker cidfile/name correlation failed")
        stdout, stderr = _docker_call(
            client,
            ["container", "rm", "--force", "--volumes", container_id],
            timeout=TOOL_TIMEOUT,
            output_limit=512,
        )
        current = os.stat(cidfile.name, dir_fd=directory, follow_symlinks=False)
        if stdout != raw + b"\n" or stderr or _facts(current) != _facts(held):
            raise CleanError("named Docker container cleanup failed")
        _prove_linux_container_name_absent(client, name)
        os.unlink(cidfile.name, dir_fd=directory)
    except (OSError, RegistryError, ValueError) as error:
        if isinstance(error, CleanError):
            raise
        raise CleanError("named Docker container cleanup failed") from error
    finally:
        for opened in (leaf, directory):
            if opened is not None:
                os.close(opened)


def _run_linux_container(
    client: _DockerClient,
    checkout: Path,
    uv: _LinuxUvTool,
    clean_lock: object,
    image: str,
    phase: str,
) -> None:
    name, cidfile = _linux_container_identity(client, phase)
    argv = _linux_container_argv(
        client.temporary,
        checkout,
        uv,
        clean_lock,
        image,
        phase=phase,
        name=name,
        cidfile=cidfile,
    )
    result: tuple[bytes, bytes] | None = None
    failure: BaseException | None = None
    try:
        result = _docker_call(
            client,
            argv,
            timeout=COMMAND_TIMEOUT,
            output_limit=4 * 1024 * 1024,
        )
    except BaseException as error:
        failure = error
    try:
        _cleanup_linux_container(
            client,
            name,
            cidfile,
            required=result is not None,
        )
    except BaseException as error:
        raise CleanError("clean-Linux container cleanup failed") from error
    if failure is not None:
        raise failure
    if result is None:
        raise CleanError("clean-Linux container returned no result")
    stdout, stderr = result
    if phase == "probe":
        _validate_linux_probe_output(stdout, stderr)
    else:
        protocol = (
            clean_lock.acquisition_protocol
            if phase == "acquire"
            else clean_lock.offline_protocol
        )
        if stderr or stdout != protocol.encode("ascii") + b"\n":
            raise CleanError(f"invalid clean-Linux {phase} result")


def _recreate_cargo_target_root(root: Path) -> None:
    repository = _repository(root)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(repository, flags))
        mount = held_mount_identity(descriptors[0])
        descriptors.append(os.open("artifacts", flags, dir_fd=descriptors[0]))
        if not same_held_mount(mount, descriptors[1], repository / "artifacts"):
            raise CleanError("unsafe Cargo target parent")
        try:
            os.stat(
                "cargo-target",
                dir_fd=descriptors[1],
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise CleanError("Cargo target unexpectedly exists")
        os.mkdir("cargo-target", 0o755, dir_fd=descriptors[1])
        descriptors.append(os.open("cargo-target", flags, dir_fd=descriptors[1]))
        held = os.fstat(descriptors[2])
        named = os.stat("cargo-target", dir_fd=descriptors[1], follow_symlinks=False)
        with os.scandir(descriptors[2]) as iterator:
            empty = next(iterator, None) is None
        if (
            _facts(held) != _facts(named)
            or not same_held_mount(
                mount, descriptors[2], repository / "artifacts/cargo-target"
            )
            or not empty
        ):
            raise CleanError("unsafe recreated Cargo target")
    except (OSError, ValueError) as error:
        if isinstance(error, CleanError):
            raise
        raise CleanError("unsafe recreated Cargo target") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _validate_offline_disposable_state(root: Path) -> None:
    repository = _repository(root)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(repository, flags))
        mount = held_mount_identity(descriptors[0])
        try:
            os.stat(".venv", dir_fd=descriptors[0], follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise CleanError("invalid offline disposable state")

        current = repository
        for name in ("artifacts", "cargo-target"):
            before = os.stat(
                name,
                dir_fd=descriptors[-1],
                follow_symlinks=False,
            )
            child = os.open(name, flags, dir_fd=descriptors[-1])
            descriptors.append(child)
            current /= name
            held = os.fstat(child)
            after = os.stat(
                name,
                dir_fd=descriptors[-2],
                follow_symlinks=False,
            )
            if (
                not stat.S_ISDIR(held.st_mode)
                or _facts(before) != _facts(held)
                or _facts(after) != _facts(held)
                or not same_held_mount(mount, child, current)
            ):
                raise CleanError("invalid offline disposable state")
        target = os.fstat(descriptors[-1])
        with os.scandir(descriptors[-1]) as iterator:
            if next(iterator, None) is not None:
                raise CleanError("invalid offline disposable state")
        target_after = os.stat(
            "cargo-target",
            dir_fd=descriptors[-2],
            follow_symlinks=False,
        )
        try:
            os.stat(".venv", dir_fd=descriptors[0], follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise CleanError("invalid offline disposable state")
        if _facts(target_after) != _facts(target):
            raise CleanError("invalid offline disposable state")
    except (OSError, ValueError) as error:
        if isinstance(error, CleanError):
            raise
        raise CleanError("invalid offline disposable state") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _run_linux_phases(
    client: _DockerClient,
    root: Path,
    uv: _LinuxUvTool,
    clean_lock: object,
    image: str,
    git: Path,
) -> None:
    _validate_runtime_roots(root)
    _run_linux_container(client, root, uv, clean_lock, image, "probe")
    _run_linux_container(client, root, uv, clean_lock, image, "acquire")
    inventory = load_inventory(root)
    if build_inventory(root) != inventory:
        raise CleanError("clean-Linux acquisition inventory differs")
    _remove_disposable_outputs(root, git)
    _recreate_cargo_target_root(root)
    _validate_offline_disposable_state(root)
    _run_linux_container(client, root, uv, clean_lock, image, "offline")
    _validate_cargo_target_root(root)
    if load_inventory(root) != inventory or build_inventory(root) != inventory:
        raise CleanError("clean-Linux offline inventory differs")


def _linux_observation(
    *,
    blocker: str | None,
    daemon: str | None,
) -> dict[str, object]:
    if blocker is None:
        if daemon is None or not daemon.startswith("available: Docker Engine "):
            raise CleanError("invalid verified clean-Linux observation")
        state = "verified"
        observed = daemon
        detail = ""
    else:
        if blocker not in {
            "fixed_socket_inaccessible",
            "daemon_unreachable",
            "network_acquisition_unavailable",
            "immutable_image_unavailable",
        }:
            raise CleanError("invalid planned clean-Linux observation")
        state = "planned"
        observed = daemon or f"unavailable: {blocker}"
        detail = blocker
    return {
        "schema_version": 0,
        "protocol": LINUX_PROTOCOL,
        "state": state,
        "observed_daemon_state": observed,
        "blocker": detail,
        "deadline": "M2",
    }


def verify_linux(
    root: Path,
    lock: SourceLock,
    *,
    git_executable: Path,
    docker_executable: Path,
) -> dict[str, object]:
    repository = _repository(root)
    clean_lock = _validate_linux_lock(lock)
    git = _explicit_git(git_executable)
    docker = _explicit_docker(docker_executable)
    temporary = _new_temporary_root()
    daemon: str | None = None
    try:
        client = _prepare_docker_client(temporary, docker)
        try:
            daemon = _probe_docker_daemon(client)
        except _LinuxPrerequisite as error:
            return _linux_observation(blocker=error.blocker, daemon=error.observed)
        try:
            checkout, oid = _clone_exact_head(repository, temporary, git)
            checkout_lock = load_source_lock(checkout)
            if checkout_lock != lock:
                raise CleanError("fresh clean-Linux lock differs")
            _validate_linux_lock(checkout_lock)
            _static_dependency_preflight(checkout)
            acquired = _acquire_linux_inputs(clean_lock)
            uv = _materialize_linux_uv(temporary, acquired.uv_archive)
            image = _pull_linux_image(client, clean_lock)
            _validate_local_linux_image(client, clean_lock, image)
            _run_linux_phases(client, checkout, uv, clean_lock, image, git)
            _recheck_exact_head(repository, checkout, temporary, git, oid)
        except _LinuxPrerequisite as error:
            _recheck_exact_head(
                repository,
                checkout,
                temporary,
                git,
                oid,
            )
            return _linux_observation(
                blocker=error.blocker,
                daemon=error.observed or daemon,
            )
        return _linux_observation(blocker=None, daemon=daemon)
    except (OSError, UnicodeError, ValueError) as error:
        if isinstance(error, CleanError):
            raise
        raise CleanError("clean-Linux verification failed") from error
    finally:
        _remove_temporary_root(temporary)


def _native_environment(
    root: Path,
    tools: object,
    *,
    offline: bool,
) -> dict[str, str]:
    paths = tuple(
        getattr(tools, name)
        for name in (
            "cargo",
            "cargo_fmt",
            "rustc",
            "rustdoc",
            "rustfmt",
            "python",
            "uv",
            "git",
        )
    ) + (Path("/usr/bin/cc"),)
    environment = {
        "CARGO_CACHE_AUTO_CLEAN_FREQUENCY": "never",
        "CARGO_HOME": str(root / "artifacts/cargo-home"),
        "CARGO_REGISTRIES_CRATES_IO_PROTOCOL": "sparse",
        "CARGO_TARGET_AARCH64_APPLE_DARWIN_LINKER": "/usr/bin/cc",
        "CARGO_TARGET_DIR": str(root / "artifacts/cargo-target"),
        "CC": "/usr/bin/cc",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(root / "artifacts/check-home"),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.pathsep.join(dict.fromkeys(str(path.parent) for path in paths)),
        "SDKROOT": str(SDKROOT),
        "RUSTC": str(getattr(tools, "rustc")),
        "RUSTDOC": str(getattr(tools, "rustdoc")),
        "RUSTFMT": str(getattr(tools, "rustfmt")),
        "TMPDIR": str(root / "artifacts/check-tmp"),
        "TZ": "UTC",
        "UV_CACHE_DIR": str(root / "artifacts/uv-cache"),
        "UV_MANAGED_PYTHON": "true",
        "UV_NO_CONFIG": "1",
        "UV_PYTHON_INSTALL_DIR": str(root / "artifacts/uv-python"),
        "UV_PROJECT_ENVIRONMENT": ".venv",
    }
    if offline:
        environment.update(
            {
                "CARGO_NET_OFFLINE": "true",
                "UV_OFFLINE": "1",
                "UV_PYTHON_DOWNLOADS": "never",
            }
        )
    return environment


def _validate_fresh_venv(root: Path) -> Path:
    from golden_board.bootstrap import validate_venv

    try:
        return validate_venv(root, runner=_probe_runner)
    except ValueError as error:
        raise CleanError("fresh managed Python is invalid") from error


def _static_dependency_preflight(root: Path) -> None:
    from golden_board.bootstrap import validate_cargo_configuration
    from golden_board.checks import static_dependency_errors

    try:
        validate_cargo_configuration(root)
        errors = static_dependency_errors(root)
    except (OSError, UnicodeError, ValueError) as error:
        raise CleanError("dependency policy audit failed") from error
    if (
        type(errors) is not list
        or any(type(error) is not str for error in errors)
        or errors
    ):
        raise CleanError("dependency policy rejected")


def _validate_runtime_roots(root: Path) -> None:
    repository = _repository(root)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(repository, flags))
        mount = held_mount_identity(descriptors[0])
        artifacts = os.open("artifacts", flags, dir_fd=descriptors[0])
        descriptors.append(artifacts)
        if not same_held_mount(mount, artifacts, repository / "artifacts"):
            raise CleanError("unsafe runtime root: artifacts")
        for name in ("cargo-home", "cargo-target", "uv-cache", "uv-python"):
            child = os.open(name, flags, dir_fd=artifacts)
            descriptors.append(child)
            held = os.fstat(child)
            named = os.stat(name, dir_fd=artifacts, follow_symlinks=False)
            if (
                not stat.S_ISDIR(held.st_mode)
                or _facts(held) != _facts(named)
                or not same_held_mount(mount, child, repository / "artifacts" / name)
            ):
                raise CleanError(f"unsafe runtime root: {name}")
            with os.scandir(child) as iterator:
                if next(iterator, None) is not None:
                    raise CleanError(f"unsafe runtime root: {name} is not empty")
    except (OSError, ValueError) as error:
        if isinstance(error, CleanError):
            raise
        raise CleanError("unsafe runtime root") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _validate_cargo_target_root(root: Path) -> None:
    repository = _repository(root)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(repository, flags))
        mount = held_mount_identity(descriptors[0])
        current = repository
        for name in ("artifacts", "cargo-target"):
            before = os.stat(name, dir_fd=descriptors[-1], follow_symlinks=False)
            child = os.open(name, flags, dir_fd=descriptors[-1])
            descriptors.append(child)
            current /= name
            held = os.fstat(child)
            after = os.stat(name, dir_fd=descriptors[-2], follow_symlinks=False)
            if (
                not stat.S_ISDIR(held.st_mode)
                or _facts(before) != _facts(held)
                or _facts(after) != _facts(held)
                or not same_held_mount(mount, child, current)
            ):
                raise CleanError("unsafe recreated Cargo target")
    except (OSError, ValueError) as error:
        if isinstance(error, CleanError):
            raise
        raise CleanError("unsafe recreated Cargo target") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _delete_directory_contents(
    descriptor: int,
    path: Path,
    mount: tuple[int, bytes | None],
    *,
    depth: int = 0,
    entries: list[int] | None = None,
) -> None:
    if depth > 128:
        raise CleanError("disposable tree depth cap exceeded")
    if entries is None:
        entries = [0]
    with os.scandir(descriptor) as iterator:
        names = sorted((entry.name for entry in iterator), key=os.fsencode)
    for name in names:
        entries[0] += 1
        if entries[0] > 200_000:
            raise CleanError("disposable tree entry cap exceeded")
        before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        child_path = path / name
        mode = before.st_mode
        if stat.S_ISLNK(mode):
            current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if _facts(before) != _facts(current):
                raise CleanError("disposable symlink changed")
            os.unlink(name, dir_fd=descriptor)
            continue
        if stat.S_ISREG(mode):
            child = os.open(
                name,
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=descriptor,
            )
            try:
                held = os.fstat(child)
                current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if (
                    _facts(before) != _facts(held)
                    or _facts(held) != _facts(current)
                    or not same_held_mount(mount, child, child_path)
                ):
                    raise CleanError("disposable file changed")
                os.unlink(name, dir_fd=descriptor)
            finally:
                os.close(child)
            continue
        if not stat.S_ISDIR(mode):
            raise CleanError("disposable tree contains a special entry")
        child = os.open(
            name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=descriptor,
        )
        try:
            held = os.fstat(child)
            if _facts(before) != _facts(held) or not same_held_mount(
                mount, child, child_path
            ):
                raise CleanError("disposable directory changed")
            _delete_directory_contents(
                child,
                child_path,
                mount,
                depth=depth + 1,
                entries=entries,
            )
            held_after = os.fstat(child)
            current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if _facts(current) != _facts(held_after) or not same_held_mount(
                mount, child, child_path
            ):
                raise CleanError("disposable directory changed")
            os.rmdir(name, dir_fd=descriptor)
        finally:
            os.close(child)


def _remove_cargo_target(root: Path) -> None:
    repository = _repository(root)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(repository, flags))
        mount = held_mount_identity(descriptors[0])
        current = repository
        for name in ("artifacts", "cargo-target"):
            parent = descriptors[-1]
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
            child = os.open(name, flags, dir_fd=parent)
            descriptors.append(child)
            current /= name
            held = os.fstat(child)
            if _facts(before) != _facts(held) or not same_held_mount(
                mount, child, current
            ):
                raise CleanError("unsafe Cargo target")
        _delete_directory_contents(descriptors[-1], current, mount)
        held_after = os.fstat(descriptors[-1])
        current_after = os.stat(
            "cargo-target", dir_fd=descriptors[-2], follow_symlinks=False
        )
        if _facts(held_after) != _facts(current_after) or not same_held_mount(
            mount, descriptors[-1], current
        ):
            raise CleanError("Cargo target changed")
        os.rmdir("cargo-target", dir_fd=descriptors[-2])
    except (OSError, ValueError) as error:
        if isinstance(error, CleanError):
            raise
        raise CleanError("cannot remove exact Cargo target") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _remove_disposable_outputs(root: Path, git: Path) -> None:
    from golden_board.bootstrap import remove_venv

    environment = _checkout_git_environment(root, git)
    try:
        remove_venv(
            root,
            git_executable=git,
            git_environment=environment,
            runner=_git_runner(git),
        )
        _remove_cargo_target(root)
    except ValueError as error:
        if isinstance(error, CleanError):
            raise
        raise CleanError("cannot remove exact disposable outputs") from error


def _repository_executable(root: Path, relative: tuple[str, str]) -> Path:
    repository = _repository(root)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    leaf: int | None = None
    path = repository
    try:
        descriptors.append(os.open(repository, flags))
        mount = held_mount_identity(descriptors[0])
        parent = descriptors[0]
        for name in relative[:-1]:
            path /= name
            child = os.open(name, flags, dir_fd=parent)
            descriptors.append(child)
            if not same_held_mount(mount, child, path):
                raise CleanError("repository executable parent is unsafe")
            parent = child
        path /= relative[-1]
        leaf = os.open(
            relative[-1],
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent,
        )
        held = os.fstat(leaf)
        named = os.stat(relative[-1], dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISREG(held.st_mode)
            or held.st_mode & 0o022
            or held.st_mode & 0o111 == 0
            or _facts(held) != _facts(named)
            or not same_held_mount(mount, leaf, path)
        ):
            raise CleanError("repository executable is unsafe")
        return path
    except OSError as error:
        raise CleanError("repository executable is unsafe") from error
    finally:
        if leaf is not None:
            os.close(leaf)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _full_environment(tools: object, managed_python: Path) -> dict[str, str]:
    entries = tuple(
        dict.fromkeys(
            str(path.parent)
            for path in (
                getattr(tools, "cargo"),
                getattr(tools, "cargo_fmt"),
                getattr(tools, "rustc"),
                getattr(tools, "rustdoc"),
                getattr(tools, "rustfmt"),
                managed_python,
                getattr(tools, "uv"),
                getattr(tools, "git"),
                Path("/usr/bin/cc"),
            )
        )
    )
    return {
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.pathsep.join(entries),
        "TZ": "UTC",
    }


def _run_native_phases(root: Path, tools: object) -> Path:
    _validate_runtime_roots(root)
    _probe_linux_cargo_fmt(
        root,
        getattr(tools, "cargo"),
        getattr(tools, "cargo_fmt"),
        getattr(tools, "rustc"),
        getattr(tools, "rustdoc"),
        getattr(tools, "rustfmt"),
    )
    acquisition_environment = _native_environment(root, tools, offline=False)
    commands = (
        (
            getattr(tools, "uv"),
            [
                str(getattr(tools, "uv")),
                "--no-config",
                "sync",
                "--project",
                ".",
                "--locked",
            ],
        ),
        (
            getattr(tools, "cargo"),
            [
                str(getattr(tools, "cargo")),
                "fetch",
                "--manifest-path",
                "Cargo.toml",
                "--locked",
            ],
        ),
        (
            getattr(tools, "cargo"),
            [
                str(getattr(tools, "cargo")),
                "build",
                "--manifest-path",
                "Cargo.toml",
                "--workspace",
                "--locked",
            ],
        ),
    )
    for tool, argv in commands:
        _invoke(tool, argv, acquisition_environment, cwd=root)
    _validate_fresh_venv(root)
    inventory = build_inventory(root)
    write_inventory(root, inventory)
    if load_inventory(root) != inventory:
        raise CleanError("published acquisition inventory differs")

    _remove_disposable_outputs(root, getattr(tools, "git"))
    offline_environment = _native_environment(root, tools, offline=True)
    _invoke(
        getattr(tools, "uv"),
        [
            str(getattr(tools, "uv")),
            "--no-config",
            "sync",
            "--project",
            ".",
            "--offline",
            "--locked",
        ],
        offline_environment,
        cwd=root,
    )
    managed_python = _validate_fresh_venv(root)
    _invoke(
        getattr(tools, "cargo"),
        [
            str(getattr(tools, "cargo")),
            "build",
            "--manifest-path",
            "Cargo.toml",
            "--workspace",
            "--offline",
            "--locked",
        ],
        offline_environment,
        cwd=root,
    )
    _validate_cargo_target_root(root)
    if build_inventory(root) != inventory or load_inventory(root) != inventory:
        raise CleanError("offline acquisition inventory drifted")

    check = _repository_executable(root, ("scripts", "check"))
    full_environment = _full_environment(tools, managed_python)
    for _ in range(2):
        _invoke(check, [str(check), "full"], full_environment, cwd=root)
        _validate_cargo_target_root(root)
        if build_inventory(root) != inventory or load_inventory(root) != inventory:
            raise CleanError("full-check acquisition inventory drifted")
    return managed_python


def _repository(root: Path) -> Path:
    if not isinstance(root, Path) or not root.is_absolute():
        raise CleanError("invalid repository root")
    try:
        if root.resolve(strict=True) != root or not root.is_dir() or root.is_symlink():
            raise CleanError("invalid repository root")
    except OSError as error:
        raise CleanError("invalid repository root") from error
    return root


def _identity(value: os.stat_result) -> tuple[int, int, int]:
    return value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode)


def _facts(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _write_all(descriptor: int, raw: bytes) -> None:
    view = memoryview(raw)
    offset = 0
    while offset < len(view):
        written = os.write(descriptor, view[offset:])
        if written <= 0:
            raise CleanError("native evidence short write")
        offset += written


def _read_exact(descriptor: int, expected: bytes) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    value = bytearray()
    while len(value) <= len(expected):
        chunk = os.read(descriptor, min(64 * 1024, len(expected) + 1 - len(value)))
        if not chunk:
            break
        value.extend(chunk)
    if bytes(value) != expected:
        raise CleanError("native evidence verification failed")


def _held_leaf(
    directory: int,
    name: str,
    path: Path,
    mount: tuple[int, bytes | None],
) -> tuple[int, os.stat_result]:
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=directory,
    )
    try:
        held = os.fstat(descriptor)
        named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (
            not stat.S_ISREG(held.st_mode)
            or _facts(held) != _facts(named)
            or not same_held_mount(mount, descriptor, path)
        ):
            raise CleanError("unsafe native evidence leaf")
        return descriptor, held
    except BaseException:
        os.close(descriptor)
        raise


def _unlink_owned(
    directory: int,
    name: str | None,
    identity: tuple[int, int] | None,
    path: Path,
    mount: tuple[int, bytes | None] | None,
) -> None:
    if name is None or identity is None or mount is None:
        return
    descriptor: int | None = None
    try:
        descriptor, held = _held_leaf(directory, name, path, mount)
        if (held.st_dev, held.st_ino) != identity:
            raise CleanError("native evidence cleanup identity changed")
        os.unlink(name, dir_fd=directory)
    except FileNotFoundError:
        return
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _directory_current(
    repository: Path,
    root_descriptor: int,
    artifacts: int,
    mount: tuple[int, bytes | None],
) -> None:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    current_root: int | None = None
    current_artifacts: int | None = None
    try:
        current_root = os.open(repository, flags)
        current_artifacts = os.open("artifacts", flags, dir_fd=current_root)
        if (
            _identity(os.fstat(root_descriptor)) != _identity(os.fstat(current_root))
            or _identity(os.fstat(root_descriptor)) != _identity(repository.lstat())
            or _identity(os.fstat(artifacts)) != _identity(os.fstat(current_artifacts))
            or _identity(os.fstat(artifacts))
            != _identity(
                os.stat("artifacts", dir_fd=current_root, follow_symlinks=False)
            )
            or not same_held_mount(mount, current_artifacts, repository / "artifacts")
        ):
            raise CleanError("native evidence directory changed")
    except OSError as error:
        raise CleanError("native evidence directory changed") from error
    finally:
        for descriptor in (current_artifacts, current_root):
            if descriptor is not None:
                os.close(descriptor)


def write_native_evidence(root: Path, evidence: dict[str, object]) -> None:
    repository = _repository(root)
    try:
        value = _native_shape(evidence)
        raw = encode_canonical_value(value)
        if len(raw) > MAX_REPORT_BYTES:
            raise CleanError("native evidence exceeds its byte cap")
        if encode_canonical_value(decode_canonical_manifest(raw)) != raw:
            raise CleanError("native evidence is not canonical")
    except (ReportError, ValueError) as error:
        if isinstance(error, CleanError):
            raise
        raise CleanError("invalid native evidence") from error

    required = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW")
    if any(type(getattr(os, name, None)) is not int for name in required):
        raise CleanError("safe native evidence publication is unavailable")
    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    root_descriptor: int | None = None
    artifacts: int | None = None
    temporary: int | None = None
    temporary_name: str | None = None
    temporary_identity: tuple[int, int] | None = None
    backup_name: str | None = None
    backup_identity: tuple[int, int] | None = None
    published_identity: tuple[int, int] | None = None
    prior_facts: os.stat_result | None = None
    mount: tuple[int, bytes | None] | None = None
    failure: BaseException | None = None
    committed = False
    try:
        root_descriptor = os.open(repository, directory_flags)
        root_facts = os.fstat(root_descriptor)
        if _identity(root_facts) != _identity(repository.lstat()):
            raise CleanError("repository root identity changed")
        mount = held_mount_identity(root_descriptor)
        try:
            artifacts = os.open("artifacts", directory_flags, dir_fd=root_descriptor)
        except FileNotFoundError:
            os.mkdir("artifacts", 0o755, dir_fd=root_descriptor)
            artifacts = os.open("artifacts", directory_flags, dir_fd=root_descriptor)
        artifacts_path = repository / "artifacts"
        artifacts_facts = os.fstat(artifacts)
        if (
            _identity(artifacts_facts)
            != _identity(
                os.stat("artifacts", dir_fd=root_descriptor, follow_symlinks=False)
            )
            or _identity(artifacts_facts) != _identity(artifacts_path.lstat())
            or not same_held_mount(mount, artifacts, artifacts_path)
        ):
            raise CleanError("unsafe native evidence directory")

        destination = "native-verification.json"
        try:
            existing, existing_facts = _held_leaf(
                artifacts,
                destination,
                artifacts_path / destination,
                mount,
            )
        except FileNotFoundError:
            pass
        else:
            prior_facts = existing_facts
            os.close(existing)

        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        for index in range(64):
            candidate = f".{destination}.{index}.tmp"
            try:
                temporary = os.open(candidate, flags, 0o600, dir_fd=artifacts)
            except FileExistsError:
                continue
            temporary_name = candidate
            held = os.fstat(temporary)
            temporary_identity = (held.st_dev, held.st_ino)
            if not same_held_mount(mount, temporary, artifacts_path / candidate):
                raise CleanError("native evidence temporary mount changed")
            break
        if temporary is None or temporary_name is None:
            raise CleanError("no bounded native evidence temporary name")
        _write_all(temporary, raw)
        os.fsync(temporary)
        written_facts = os.fstat(temporary)
        _read_exact(temporary, raw)
        if _facts(os.fstat(temporary)) != _facts(written_facts):
            raise CleanError("native evidence temporary changed")

        reopened, reopened_facts = _held_leaf(
            artifacts,
            temporary_name,
            artifacts_path / temporary_name,
            mount,
        )
        try:
            if _facts(reopened_facts) != _facts(written_facts):
                raise CleanError("native evidence temporary identity changed")
            _read_exact(reopened, raw)
        finally:
            os.close(reopened)
        _directory_current(repository, root_descriptor, artifacts, mount)
        try:
            existing, current_facts = _held_leaf(
                artifacts,
                destination,
                artifacts_path / destination,
                mount,
            )
        except FileNotFoundError:
            if prior_facts is not None:
                raise CleanError("native evidence destination changed")
        else:
            try:
                if prior_facts is None or _facts(current_facts) != _facts(prior_facts):
                    raise CleanError("native evidence destination changed")
                for index in range(64):
                    candidate = f".{destination}.{index}.backup"
                    try:
                        os.link(
                            destination,
                            candidate,
                            src_dir_fd=artifacts,
                            dst_dir_fd=artifacts,
                            follow_symlinks=False,
                        )
                    except FileExistsError:
                        continue
                    backup_name = candidate
                    break
                if backup_name is None:
                    raise CleanError("no bounded native evidence backup name")
            finally:
                os.close(existing)

        if prior_facts is None:
            try:
                os.stat(destination, dir_fd=artifacts, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise CleanError("native evidence destination changed")
        else:
            current, current_facts = _held_leaf(
                artifacts,
                destination,
                artifacts_path / destination,
                mount,
            )
            backup, backup_facts = _held_leaf(
                artifacts,
                backup_name or "",
                artifacts_path / (backup_name or ".missing"),
                mount,
            )
            try:
                if _identity(current_facts) != _identity(prior_facts) or _facts(
                    current_facts
                ) != _facts(backup_facts):
                    raise CleanError("native evidence backup identity changed")
                backup_identity = (backup_facts.st_dev, backup_facts.st_ino)
            finally:
                os.close(backup)
                os.close(current)
        final_temporary, final_temporary_facts = _held_leaf(
            artifacts,
            temporary_name,
            artifacts_path / temporary_name,
            mount,
        )
        try:
            if _facts(final_temporary_facts) != _facts(written_facts):
                raise CleanError("native evidence temporary changed")
            _read_exact(final_temporary, raw)
        finally:
            os.close(final_temporary)
        _directory_current(repository, root_descriptor, artifacts, mount)
        os.replace(
            temporary_name,
            destination,
            src_dir_fd=artifacts,
            dst_dir_fd=artifacts,
        )
        temporary_name = None
        published_identity = temporary_identity
        _directory_current(repository, root_descriptor, artifacts, mount)
        published, published_facts = _held_leaf(
            artifacts,
            destination,
            artifacts_path / destination,
            mount,
        )
        try:
            if (
                _identity(published_facts) != _identity(written_facts)
                or published_facts.st_size != written_facts.st_size
                or published_facts.st_mtime_ns != written_facts.st_mtime_ns
            ):
                raise CleanError("published native evidence identity changed")
            _read_exact(published, raw)
        finally:
            os.close(published)
        os.fsync(artifacts)
        _directory_current(repository, root_descriptor, artifacts, mount)
        committed = True
    except (OSError, TypeError, ValueError) as error:
        failure = error
    finally:
        if (
            not committed
            and published_identity is not None
            and artifacts is not None
            and mount is not None
        ):
            try:
                if backup_name is None or backup_identity is None:
                    _unlink_owned(
                        artifacts,
                        destination,
                        published_identity,
                        repository / "artifacts" / destination,
                        mount,
                    )
                else:
                    backup, backup_facts = _held_leaf(
                        artifacts,
                        backup_name,
                        repository / "artifacts" / backup_name,
                        mount,
                    )
                    try:
                        if (
                            backup_facts.st_dev,
                            backup_facts.st_ino,
                        ) != backup_identity:
                            raise CleanError("native evidence rollback is unsafe")
                    finally:
                        os.close(backup)
                    os.replace(
                        backup_name,
                        destination,
                        src_dir_fd=artifacts,
                        dst_dir_fd=artifacts,
                    )
                    backup_name = None
                    restored, restored_facts = _held_leaf(
                        artifacts,
                        destination,
                        repository / "artifacts" / destination,
                        mount,
                    )
                    try:
                        if (
                            restored_facts.st_dev,
                            restored_facts.st_ino,
                        ) != backup_identity:
                            raise CleanError("native evidence rollback failed")
                    finally:
                        os.close(restored)
                os.fsync(artifacts)
            except (OSError, CleanError) as error:
                failure = CleanError("native evidence rollback failed")
                failure.__cause__ = error
        if temporary is not None:
            try:
                os.close(temporary)
            except OSError as error:
                if failure is None:
                    failure = error
        if artifacts is not None:
            try:
                _unlink_owned(
                    artifacts,
                    temporary_name,
                    temporary_identity,
                    repository / "artifacts" / (temporary_name or ".unused"),
                    mount,
                )
            except (OSError, CleanError) as error:
                if failure is None:
                    failure = error
            try:
                _unlink_owned(
                    artifacts,
                    backup_name,
                    backup_identity,
                    repository / "artifacts" / (backup_name or ".unused"),
                    mount,
                )
            except (OSError, CleanError) as error:
                if failure is None:
                    failure = error
        for descriptor in (artifacts, root_descriptor):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError as error:
                    if failure is None:
                        failure = error
    if committed and failure is None:
        return
    if isinstance(failure, CleanError):
        raise failure
    raise CleanError("native evidence publication failed") from failure
