from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import cast

from golden_board import checks, clean, source_doctor
from golden_board.manifest import decode_canonical_manifest, encode_canonical_value
from golden_board.reports import (
    MAX_REPORT_BYTES,
    ReportError,
    _read_below,
    build_release_summary,
    check_tracked_reports,
    native_evidence_from_summary,
)
from golden_board.source_lock import (
    SourceLock,
    held_mount_identity,
    load_source_lock,
    read_regular_below,
    same_held_mount,
)
from golden_board.registry import RegistryError, _run_bounded_process


SOURCE_REPORT = Path("reports/source-doctor.json")
RELEASE_SUMMARY = Path("reports/release-summary.json")
NATIVE_EVIDENCE = Path("artifacts/native-verification.json")
_REPORT = PurePosixPath(SOURCE_REPORT.as_posix())
_SOURCE_USAGE = "usage: generate source-doctor | check source-report"
_READ_CHUNK = 64 * 1024
_MAX_ERROR_DETAIL = 512
_TOOL_VERSION = {
    "cargo": re.compile(
        rb"cargo 1\.94\.0 \((?:Homebrew|[0-9a-f]{7,40} [0-9]{4}-[0-9]{2}-[0-9]{2})\)\n\Z"
    ),
    "cargo-fmt": re.compile(
        rb"(?:rustfmt 1\.8\.0|rustfmt 1\.8\.0-(?:stable|nightly) \([0-9a-f]{7,40} [0-9]{4}-[0-9]{2}-[0-9]{2}\))\n\Z"
    ),
    "rustc": re.compile(
        rb"rustc 1\.94\.0 \([0-9a-f]{7,40} [0-9]{4}-[0-9]{2}-[0-9]{2}\)(?: \(Homebrew\))?\n\Z"
    ),
    "rustdoc": re.compile(
        rb"rustdoc 1\.94\.0 \([0-9a-f]{7,40} [0-9]{4}-[0-9]{2}-[0-9]{2}\)(?: \(Homebrew\))?\n\Z"
    ),
    "rustfmt": re.compile(
        rb"(?:rustfmt 1\.8\.0|rustfmt 1\.8\.0-(?:stable|nightly) \([0-9a-f]{7,40} [0-9]{4}-[0-9]{2}-[0-9]{2}\))\n\Z"
    ),
}
_DOCKER_VERSION = re.compile(
    rb"Docker version 25\.0\.3, build [0-9A-Za-z._+-]{1,64}\n\Z"
)
_IMAGE_GIT_VERSION = re.compile(rb"git version 2\.[0-9]{1,3}\.[0-9]{1,3}\n\Z")
_LINUX_AVAILABLE = re.compile(
    r"available: Docker Engine [A-Za-z0-9._+-]{1,64} "
    r"[A-Za-z0-9._+-]{1,64}/[A-Za-z0-9._+-]{1,64} "
    r"kernel [A-Za-z0-9._+-]{1,64}\Z"
)
_LINUX_UNAVAILABLE = {
    "unavailable: fixed_socket_inaccessible",
    "unavailable: daemon_unreachable",
    "unavailable: network_acquisition_unavailable",
    "unavailable: immutable_image_unavailable",
}


def build_source_report(root: Path, lock: SourceLock) -> dict[str, object]:
    return source_doctor.build_source_report(root, lock)


def _validated_linux_observation(value: object) -> dict[str, object]:
    keys = {
        "schema_version",
        "protocol",
        "state",
        "observed_daemon_state",
        "blocker",
        "deadline",
    }
    if type(value) is not dict or set(value) != keys:
        raise ValueError("invalid clean-Linux observation")
    result = cast(dict[str, object], value)
    state = result["state"]
    observed = result["observed_daemon_state"]
    blocker = result["blocker"]
    if (
        type(result["schema_version"]) is not int
        or result["schema_version"] != 0
        or result["protocol"] != "docker-clean-linux-v0"
        or state not in {"planned", "verified"}
        or type(observed) is not str
        or not (_LINUX_AVAILABLE.fullmatch(observed) or observed in _LINUX_UNAVAILABLE)
        or type(blocker) is not str
        or len(blocker) > _MAX_ERROR_DETAIL
        or any(ord(character) < 0x20 or ord(character) > 0x7E for character in blocker)
        or result["deadline"] != "M2"
        or (
            state == "planned"
            and (
                blocker
                not in {
                    "fixed_socket_inaccessible",
                    "daemon_unreachable",
                    "network_acquisition_unavailable",
                    "immutable_image_unavailable",
                }
                or (
                    observed in _LINUX_UNAVAILABLE
                    and observed != f"unavailable: {blocker}"
                )
                or (
                    _LINUX_AVAILABLE.fullmatch(observed) is not None
                    and blocker
                    not in {
                        "network_acquisition_unavailable",
                        "immutable_image_unavailable",
                    }
                )
            )
        )
        or (
            state == "verified"
            and (blocker or _LINUX_AVAILABLE.fullmatch(observed) is None)
        )
    ):
        raise ValueError("invalid clean-Linux observation")
    return dict(result)


def _directory_flags() -> int:
    required = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW")
    if any(type(getattr(os, name, None)) is not int for name in required):
        raise ValueError("source report capability")
    return os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW


def _file_flags() -> int:
    required = ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK")
    if any(type(getattr(os, name, None)) is not int for name in required):
        raise ValueError("source report capability")
    return os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK


def _same_file(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )


def _same_identity(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev,
        before.st_ino,
        stat.S_IFMT(before.st_mode),
    ) == (
        after.st_dev,
        after.st_ino,
        stat.S_IFMT(after.st_mode),
    )


def _held_named_directory(
    parent: int,
    name: str,
    descriptor: int,
    path: Path,
    mount: tuple[int, bytes | None],
) -> None:
    held = os.fstat(descriptor)
    named = os.stat(name, dir_fd=parent, follow_symlinks=False)
    path_facts = os.stat(path, follow_symlinks=False)
    if (
        not stat.S_ISDIR(held.st_mode)
        or not _same_identity(held, named)
        or not _same_identity(held, path_facts)
        or not same_held_mount(mount, descriptor, path)
    ):
        raise ValueError("unsafe held directory")


def _safe_unlink_owned(
    directory: int,
    name: str,
    identity: tuple[int, int] | None,
    mount: tuple[int, bytes | None],
    path: Path,
) -> None:
    if identity is None:
        return
    descriptor: int | None = None
    try:
        facts = os.stat(name, dir_fd=directory, follow_symlinks=False)
        descriptor = os.open(name, _file_flags(), dir_fd=directory)
        held = os.fstat(descriptor)
    except FileNotFoundError:
        return
    try:
        if (
            (held.st_dev, held.st_ino) == identity
            and _same_identity(held, facts)
            and _same_identity(
                held,
                os.stat(name, dir_fd=directory, follow_symlinks=False),
            )
            and same_held_mount(mount, descriptor, path)
        ):
            os.unlink(name, dir_fd=directory)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_regular_at(directory: int, leaf: str, max_bytes: int) -> bytes:
    descriptor: int | None = None
    failure: BaseException | None = None
    data = bytearray()
    try:
        descriptor = os.open(leaf, _file_flags(), dir_fd=directory)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            raise ValueError("source report file")
        while True:
            chunk = os.read(
                descriptor,
                min(_READ_CHUNK, max_bytes + 1 - len(data)),
            )
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > max_bytes:
                raise ValueError("source report file")
        after = os.fstat(descriptor)
        if not _same_file(before, after) or len(data) != after.st_size:
            raise ValueError("source report file")
    except (OSError, TypeError, ValueError) as error:
        failure = ValueError("source report file")
        failure.__cause__ = error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as error:
                if failure is None:
                    failure = ValueError("source report file")
                    failure.__cause__ = error
    if failure is not None:
        raise failure
    return bytes(data)


def _read_bounded(root: Path, relative: Path) -> bytes:
    return _read_below(root, PurePosixPath(relative.as_posix()), MAX_REPORT_BYTES)


def _canonical_bytes(value: object) -> bytes:
    raw = encode_canonical_value(value)
    if len(raw) > MAX_REPORT_BYTES:
        raise ReportError("canonical report exceeds the M0 report byte cap")
    return raw


def _canonical_object(root: Path, relative: Path) -> dict[str, object]:
    raw = _read_bounded(root, relative)
    value = decode_canonical_manifest(raw)
    if type(value) is not dict:
        raise ReportError(f"canonical input must be an object: {relative}")
    if encode_canonical_value(value) != raw:
        raise ReportError(f"canonical input bytes are noncanonical: {relative}")
    return cast(dict[str, object], value)


def _open_reports_directory(root: Path, *, create: bool = False) -> int:
    try:
        flags = _directory_flags()
    except ValueError as error:
        raise ReportError(
            "report writes require descriptor-relative no-follow opens"
        ) from error
    directory: int | None = None
    try:
        repository = os.open(root, flags)
    except OSError as error:
        raise ReportError("cannot open repository root descriptor") from error
    try:
        repository_facts = os.fstat(repository)
        root_facts = os.stat(root, follow_symlinks=False)
        try:
            mount = held_mount_identity(repository)
        except OSError as error:
            raise ReportError("repository mount identity is unavailable") from error
        if not stat.S_ISDIR(repository_facts.st_mode) or not _same_identity(
            repository_facts, root_facts
        ):
            raise ReportError("repository root identity changed")
        try:
            directory = os.open("reports", flags, dir_fd=repository)
        except FileNotFoundError:
            if not create:
                raise ReportError("reports directory is missing")
            try:
                os.mkdir("reports", 0o755, dir_fd=repository)
                directory = os.open("reports", flags, dir_fd=repository)
            except OSError as error:
                raise ReportError("cannot create direct reports directory") from error
        except OSError as error:
            raise ReportError("cannot open direct reports directory") from error
        try:
            _held_named_directory(
                repository, "reports", directory, root / "reports", mount
            )
        except (OSError, TypeError, ValueError) as error:
            raise ReportError("reports directory identity changed") from error
        if not _same_identity(
            os.fstat(repository), os.stat(root, follow_symlinks=False)
        ):
            raise ReportError("repository root identity changed")
    except BaseException:
        if directory is not None:
            try:
                os.close(directory)
            except OSError:
                pass
        try:
            os.close(repository)
        except OSError:
            pass
        raise
    try:
        os.close(repository)
    except BaseException:
        try:
            os.close(directory)
        except OSError:
            pass
        raise
    if directory is None:
        raise ReportError("reports directory is unavailable")
    return directory


def _existing_leaf_is_regular(
    directory: int,
    name: str,
    path: Path,
    mount: tuple[int, bytes | None],
) -> None:
    descriptor: int | None = None
    try:
        named = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return
    try:
        descriptor = os.open(name, _file_flags(), dir_fd=directory)
        held = os.fstat(descriptor)
        if (
            not stat.S_ISREG(held.st_mode)
            or not _same_identity(held, named)
            or not same_held_mount(mount, descriptor, path)
            or not _same_identity(
                held,
                os.stat(name, dir_fd=directory, follow_symlinks=False),
            )
        ):
            raise ReportError(
                f"report destination is not a safe regular file: reports/{name}"
            )
    except (OSError, TypeError, ValueError) as error:
        if isinstance(error, ReportError):
            raise
        raise ReportError(
            f"report destination is not a safe regular file: reports/{name}"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _report_directory_is_current(
    root: Path,
    directory: int,
    mount: tuple[int, bytes | None],
) -> None:
    current = _open_reports_directory(root)
    try:
        if not same_held_mount(mount, current, root / "reports") or not _same_identity(
            os.fstat(directory), os.fstat(current)
        ):
            raise ReportError("reports directory identity changed")
    finally:
        os.close(current)


def _open_verified_report(
    directory: int,
    directory_path: Path,
    name: str,
    expected: bytes,
    mount: tuple[int, bytes | None],
) -> int:
    descriptor: int | None = None
    try:
        descriptor = os.open(name, _file_flags(), dir_fd=directory)
        before = os.fstat(descriptor)
        named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size != len(expected)
            or not _same_file(before, named)
            or not same_held_mount(mount, descriptor, directory_path / name)
        ):
            raise ReportError("temporary report identity changed")
        verified = bytearray()
        while True:
            chunk = os.read(
                descriptor,
                min(_READ_CHUNK, MAX_REPORT_BYTES + 1 - len(verified)),
            )
            if not chunk:
                break
            verified.extend(chunk)
            if len(verified) > MAX_REPORT_BYTES:
                raise ReportError("temporary report exceeds the M0 byte cap")
        after = os.fstat(descriptor)
        final_named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (
            bytes(verified) != expected
            or not _same_file(before, after)
            or not _same_file(after, final_named)
            or not same_held_mount(mount, descriptor, directory_path / name)
        ):
            raise ReportError("temporary report verification failed")
        return descriptor
    except BaseException:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


def _write_all(descriptor: int, raw: bytes) -> None:
    view = memoryview(raw)
    offset = 0
    while offset < len(raw):
        written = os.write(descriptor, view[offset:])
        if written <= 0:
            raise ReportError("short write while rendering canonical report")
        offset += written


def _write_source_report(root: Path, raw: bytes) -> None:
    if type(raw) is not bytes or len(raw) > MAX_REPORT_BYTES:
        raise ValueError("source report bytes")

    reports_descriptor: int | None = None
    temporary_descriptor: int | None = None
    temporary_name: str | None = None
    temporary_identity: tuple[int, int] | None = None
    reports_mount: tuple[int, bytes | None] | None = None
    failure: BaseException | None = None
    committed = False
    try:
        reports_descriptor = _open_reports_directory(root, create=True)
        reports_mount = held_mount_identity(reports_descriptor)
        reports_path = root / "reports"
        _existing_leaf_is_regular(
            reports_descriptor,
            _REPORT.name,
            reports_path / _REPORT.name,
            reports_mount,
        )

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        for index in range(64):
            candidate = f".{_REPORT.name}.{index}.tmp"
            try:
                temporary_descriptor = os.open(
                    candidate,
                    flags,
                    0o600,
                    dir_fd=reports_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            temporary_facts = os.fstat(temporary_descriptor)
            temporary_identity = (temporary_facts.st_dev, temporary_facts.st_ino)
            if not same_held_mount(
                reports_mount,
                temporary_descriptor,
                reports_path / candidate,
            ):
                raise ValueError("source report temporary mount")
            break
        if temporary_descriptor is None or temporary_name is None:
            raise ValueError("source report temporary names")

        _write_all(temporary_descriptor, raw)
        os.fsync(temporary_descriptor)
        closing = temporary_descriptor
        temporary_descriptor = None
        os.close(closing)

        temporary_descriptor = _open_verified_report(
            reports_descriptor,
            reports_path,
            temporary_name,
            raw,
            reports_mount,
        )
        decode_canonical_manifest(raw)

        _existing_leaf_is_regular(
            reports_descriptor,
            _REPORT.name,
            reports_path / _REPORT.name,
            reports_mount,
        )
        temporary_facts = os.fstat(temporary_descriptor)
        named_temporary = os.stat(
            temporary_name,
            dir_fd=reports_descriptor,
            follow_symlinks=False,
        )
        if not _same_file(temporary_facts, named_temporary) or not same_held_mount(
            reports_mount,
            temporary_descriptor,
            reports_path / temporary_name,
        ):
            raise ValueError("source report temporary identity")
        _report_directory_is_current(root, reports_descriptor, reports_mount)

        os.replace(
            temporary_name,
            _REPORT.name,
            src_dir_fd=reports_descriptor,
            dst_dir_fd=reports_descriptor,
        )
        temporary_name = None
        published = _open_verified_report(
            reports_descriptor,
            reports_path,
            _REPORT.name,
            raw,
            reports_mount,
        )
        try:
            if not _same_identity(
                os.fstat(temporary_descriptor),
                os.fstat(published),
            ):
                raise ValueError("source report published identity")
        finally:
            try:
                os.close(published)
            except OSError:
                pass
        committed = True
    except (OSError, TypeError, ValueError) as error:
        failure = error
    finally:
        if temporary_descriptor is not None:
            try:
                os.close(temporary_descriptor)
            except OSError as error:
                if failure is None:
                    failure = error
        if (
            temporary_name is not None
            and reports_descriptor is not None
            and reports_mount is not None
        ):
            try:
                _safe_unlink_owned(
                    reports_descriptor,
                    temporary_name,
                    temporary_identity,
                    reports_mount,
                    root / "reports" / temporary_name,
                )
            except OSError as error:
                if failure is None:
                    failure = error
        for descriptor in (reports_descriptor,):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError as error:
                    if failure is None:
                        failure = error
    if committed:
        return
    if failure is not None:
        raise failure
    raise ValueError("source report publication")


def _render_temporary(
    root: Path,
    destination: Path,
    value: object,
) -> tuple[int, str, int, tuple[int, bytes | None], tuple[int, int], bytes]:
    if destination != RELEASE_SUMMARY:
        raise ReportError(f"undeclared report destination: {destination}")
    raw = _canonical_bytes(value)
    directory = _open_reports_directory(root, create=True)
    directory_path = root / "reports"
    mount = held_mount_identity(directory)
    temporary_name: str | None = None
    temporary_identity: tuple[int, int] | None = None
    descriptor: int | None = None
    try:
        _existing_leaf_is_regular(
            directory,
            destination.name,
            directory_path / destination.name,
            mount,
        )
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        for index in range(64):
            candidate = f".{destination.name}.{index}.tmp"
            try:
                descriptor = os.open(candidate, flags, 0o600, dir_fd=directory)
            except FileExistsError:
                continue
            temporary_name = candidate
            temporary_facts = os.fstat(descriptor)
            temporary_identity = (temporary_facts.st_dev, temporary_facts.st_ino)
            if not same_held_mount(mount, descriptor, directory_path / candidate):
                raise ReportError("temporary report mount changed")
            break
        if temporary_name is None or descriptor is None or temporary_identity is None:
            raise ReportError("no bounded temporary report name is available")
        try:
            _write_all(descriptor, raw)
            os.fsync(descriptor)
            closing = descriptor
            descriptor = None
            os.close(closing)
            descriptor = _open_verified_report(
                directory,
                directory_path,
                temporary_name,
                raw,
                mount,
            )
            parsed = decode_canonical_manifest(raw)
            if encode_canonical_value(parsed) != raw:
                raise ReportError("temporary report is not canonical")
        except BaseException:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            raise
        return directory, temporary_name, descriptor, mount, temporary_identity, raw
    except BaseException:
        if temporary_name is not None:
            try:
                _safe_unlink_owned(
                    directory,
                    temporary_name,
                    temporary_identity,
                    mount,
                    directory_path / temporary_name,
                )
            except OSError:
                pass
        try:
            os.close(directory)
        except OSError:
            pass
        raise


def _replace_canonical(root: Path, destination: Path, value: object) -> None:
    directory, temporary_name, descriptor, mount, temporary_identity, raw = (
        _render_temporary(root, destination, value)
    )
    try:
        directory_path = root / "reports"
        _existing_leaf_is_regular(
            directory,
            destination.name,
            directory_path / destination.name,
            mount,
        )
        held = os.fstat(descriptor)
        named = os.stat(
            temporary_name,
            dir_fd=directory,
            follow_symlinks=False,
        )
        if not _same_file(held, named) or not same_held_mount(
            mount,
            descriptor,
            directory_path / temporary_name,
        ):
            raise ReportError("temporary report identity changed")
        _report_directory_is_current(root, directory, mount)
        os.replace(
            temporary_name,
            destination.name,
            src_dir_fd=directory,
            dst_dir_fd=directory,
        )
        published = _open_verified_report(
            directory,
            directory_path,
            destination.name,
            raw,
            mount,
        )
        try:
            if not _same_identity(os.fstat(descriptor), os.fstat(published)):
                raise ReportError("published report identity changed")
        finally:
            try:
                os.close(published)
            except OSError:
                pass
    except BaseException:
        try:
            _safe_unlink_owned(
                directory,
                temporary_name,
                temporary_identity,
                mount,
                directory_path / temporary_name,
            )
        except OSError:
            pass
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.close(directory)
        except OSError:
            pass
        raise
    # Successful replacement is the commit point. Descriptor-close failure
    # after publication cannot truthfully be reported as preservation failure.
    try:
        os.close(descriptor)
    except OSError:
        pass
    try:
        os.close(directory)
    except OSError:
        pass


def _source_value(root: Path) -> dict[str, object]:
    lock = load_source_lock(root)
    return build_source_report(root, lock)


def _current_report(root: Path) -> bytes:
    return encode_canonical_value(_source_value(root))


def _release_value(
    root: Path,
    native_evidence: dict[str, object] | None = None,
    *,
    git_executable: Path | None = None,
    git_environment: dict[str, str] | None = None,
) -> dict[str, object]:
    return build_release_summary(
        root,
        _source_value(root),
        native_evidence,
        git_executable=git_executable,
        git_environment=git_environment,
    )


def _error_detail(value: object) -> str:
    escaped = ascii(str(value))[1:-1]
    if len(escaped) <= _MAX_ERROR_DETAIL:
        return escaped
    return f"{escaped[: _MAX_ERROR_DETAIL - 3]}..."


def _git_runtime_directory(root: Path, name: str) -> Path:
    repository = root.resolve(strict=True)
    if repository != root or not stat.S_ISDIR(repository.lstat().st_mode):
        raise ValueError("repository root")
    if name not in {"check-home", "check-tmp"}:
        raise ValueError("Git runtime directory")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        root_descriptor = os.open(repository, flags)
        descriptors.append(root_descriptor)
        root_facts = os.fstat(root_descriptor)
        mount = held_mount_identity(root_descriptor)
        if not _same_identity(root_facts, repository.lstat()):
            raise ValueError("repository root")
        try:
            os.mkdir("artifacts", 0o700, dir_fd=root_descriptor)
        except FileExistsError:
            pass
        artifacts_descriptor = os.open("artifacts", flags, dir_fd=root_descriptor)
        descriptors.append(artifacts_descriptor)
        _held_named_directory(
            root_descriptor,
            "artifacts",
            artifacts_descriptor,
            repository / "artifacts",
            mount,
        )
        try:
            os.mkdir(name, 0o700, dir_fd=artifacts_descriptor)
        except FileExistsError:
            pass
        target_descriptor = os.open(name, flags, dir_fd=artifacts_descriptor)
        descriptors.append(target_descriptor)
        _held_named_directory(
            artifacts_descriptor,
            name,
            target_descriptor,
            repository / "artifacts" / name,
            mount,
        )
        _held_named_directory(
            root_descriptor,
            "artifacts",
            artifacts_descriptor,
            repository / "artifacts",
            mount,
        )
        if not _same_identity(os.fstat(root_descriptor), repository.lstat()):
            raise ValueError("repository root")
    except (OSError, TypeError, ValueError) as error:
        raise ValueError("Git runtime directory") from error
    finally:
        while descriptors:
            try:
                os.close(descriptors.pop())
            except OSError:
                pass
    return repository / "artifacts" / name


def _git_version_runner(argv: list[str], **kwargs: object) -> object:
    cwd = kwargs.get("cwd")
    environment = kwargs.get("env")
    if not isinstance(cwd, Path) or type(environment) is not dict:
        raise ValueError("sealed tool version probe")
    stdout, stderr = _run_bounded_process(
        argv,
        b"",
        environment,
        cwd=cwd,
        timeout=10,
        output_limit=4096,
    )
    return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)


def _projected_executable(environment: dict[str, str], key: str, label: str) -> Path:
    value = environment.get(key)
    if type(value) is not str or not value or "\0" in value:
        raise ValueError(f"sealed {label} projection")
    supplied = Path(value)
    if not supplied.is_absolute() or ".." in supplied.parts:
        raise ValueError(f"sealed {label} projection")
    try:
        executable = supplied.resolve(strict=True)
        mode = executable.lstat().st_mode
    except OSError as error:
        raise ValueError(f"sealed {label} projection") from error
    if (
        executable != supplied
        or not stat.S_ISREG(mode)
        or mode & 0o022
        or not os.access(executable, os.X_OK)
    ):
        raise ValueError(f"sealed {label} projection")
    return executable


def _module_git_context(
    root: Path,
    environment: dict[str, str],
    *,
    clean_linux: bool = False,
    runner=_git_version_runner,
) -> tuple[Path, dict[str, str]]:
    if type(environment) is not dict or type(clean_linux) is not bool:
        raise ValueError("sealed Git projection")
    executable = _projected_executable(environment, "GB_BOOTSTRAP_GIT", "Git")
    home = _git_runtime_directory(root, "check-home")
    temporary = _git_runtime_directory(root, "check-tmp")
    projected = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(home),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": str(executable.parent),
        "TMPDIR": str(temporary),
        "TZ": "UTC",
    }
    try:
        result = runner(
            [str(executable), "--version"],
            cwd=root,
            env=projected,
        )
    except (OSError, RegistryError) as error:
        raise ValueError("sealed Git version probe") from error
    stdout = getattr(result, "stdout", None)
    if (
        getattr(result, "returncode", None) != 0
        or type(stdout) is not bytes
        or len(stdout) > 4096
        or _IMAGE_GIT_VERSION.fullmatch(stdout) is None
        or getattr(result, "stderr", None) != b""
    ):
        raise ValueError("sealed Git version probe")
    return executable, projected


def _module_tool_context(
    root: Path,
    environment: dict[str, str],
    name: str,
    *,
    runner=_git_version_runner,
) -> Path:
    if name not in _TOOL_VERSION or type(environment) is not dict:
        raise ValueError("sealed tool projection")
    executable = _projected_executable(
        environment,
        f"GB_BOOTSTRAP_{name.upper().replace('-', '_')}",
        name,
    )
    projected = {
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": str(executable.parent),
        "TZ": "UTC",
    }
    try:
        result = runner([str(executable), "--version"], cwd=root, env=projected)
    except (OSError, RegistryError) as error:
        raise ValueError("sealed tool version probe") from error
    stdout = getattr(result, "stdout", None)
    if (
        getattr(result, "returncode", None) != 0
        or type(stdout) is not bytes
        or _TOOL_VERSION[name].fullmatch(stdout) is None
        or getattr(result, "stderr", None) != b""
    ):
        raise ValueError("sealed tool version probe")
    return executable


def _module_docker_context(
    root: Path,
    environment: dict[str, str],
    *,
    runner=_git_version_runner,
) -> Path:
    if type(environment) is not dict:
        raise ValueError("sealed Docker projection")
    executable = _projected_executable(environment, "GB_BOOTSTRAP_DOCKER", "Docker")
    projected = {
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": str(executable.parent),
        "TZ": "UTC",
    }
    try:
        result = runner([str(executable), "--version"], cwd=root, env=projected)
    except (OSError, RegistryError) as error:
        raise ValueError("sealed Docker version probe") from error
    stdout = getattr(result, "stdout", None)
    if (
        getattr(result, "returncode", None) != 0
        or type(stdout) is not bytes
        or _DOCKER_VERSION.fullmatch(stdout) is None
        or getattr(result, "stderr", None) != b""
    ):
        raise ValueError("sealed Docker version probe")
    return executable


def _module_python_context(root: Path, environment: dict[str, str]) -> Path:
    if (
        type(environment) is not dict
        or environment.get("PYTHONDONTWRITEBYTECODE") != "1"
    ):
        raise ValueError("sealed Python bytecode projection")
    value = environment.get("PYTHONPYCACHEPREFIX")
    if type(value) is not str or not value or "\0" in value:
        raise ValueError("sealed Python bytecode projection")
    return checks._validated_pycache_prefix(root, Path(value))


def _module_linux_linker_context(
    root: Path,
    environment: dict[str, str],
) -> Path | None:
    if type(environment) is not dict:
        raise ValueError("sealed clean-Linux projection")
    system = os.uname().sysname
    if system == "Darwin":
        if (
            environment.get("GB_CLEAN_LINUX_DIGEST")
            or "COMPILER_PATH" in environment
            or "CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER" in environment
        ):
            raise ValueError("sealed clean-Linux projection")
        return None
    if system != "Linux":
        raise ValueError("sealed clean-Linux projection")
    lock = load_source_lock(root)
    if (
        environment.get("GB_CLEAN_LINUX_DIGEST") != lock.clean_linux.platform_digest
        or environment.get("CC") != "/usr/bin/cc"
        or environment.get("COMPILER_PATH") != "/usr/bin"
        or environment.get("CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER")
        != "/usr/bin/cc"
    ):
        raise ValueError("sealed clean-Linux projection")
    return Path("/usr/bin/cc")


def _module_capability_context(
    root: Path,
    environment: dict[str, str],
    *,
    clean_linux: bool = False,
    runner=_git_version_runner,
) -> tuple[Path, dict[str, str], Path, Path, Path, Path, Path, Path]:
    pycache_prefix = _module_python_context(root, environment)
    git, git_environment = _module_git_context(
        root,
        environment,
        clean_linux=clean_linux,
        runner=runner,
    )
    cargo = _module_tool_context(root, environment, "cargo", runner=runner)
    cargo_fmt = _module_tool_context(root, environment, "cargo-fmt", runner=runner)
    rustc = _module_tool_context(root, environment, "rustc", runner=runner)
    rustdoc = _module_tool_context(root, environment, "rustdoc", runner=runner)
    rustfmt = _module_tool_context(root, environment, "rustfmt", runner=runner)
    if (
        cargo_fmt != cargo.parent / "cargo-fmt"
        or rustc != cargo.parent / "rustc"
        or rustdoc != cargo.parent / "rustdoc"
        or rustfmt != cargo.parent / "rustfmt"
    ):
        raise ValueError("sealed Cargo toolchain projection")
    return (
        git,
        git_environment,
        cargo,
        cargo_fmt,
        rustc,
        rustdoc,
        rustfmt,
        pycache_prefix,
    )


def main(
    argv: Sequence[str] | None = None,
    root: Path = Path.cwd(),
    *,
    git_executable: Path | None = None,
    git_environment: dict[str, str] | None = None,
    docker_executable: Path | None = None,
    cargo_executable: Path | None = None,
    cargo_fmt_executable: Path | None = None,
    rustc_executable: Path | None = None,
    rustdoc_executable: Path | None = None,
    rustfmt_executable: Path | None = None,
    pycache_prefix: Path | None = None,
    linux_linker: Path | None = None,
) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    repository = root
    if arguments == ("check", "release"):
        print(
            "release verification becomes operational at the M2 architecture freeze",
            file=sys.stderr,
        )
        return 2
    if arguments in (("check", "fast"), ("check", "full")):
        try:
            errors = checks.run_mode(
                repository,
                arguments[1],
                git_executable=git_executable,
                git_environment=git_environment,
                cargo_executable=cargo_executable,
                cargo_fmt_executable=cargo_fmt_executable,
                rustc_executable=rustc_executable,
                rustdoc_executable=rustdoc_executable,
                rustfmt_executable=rustfmt_executable,
                pycache_prefix=pycache_prefix,
                linux_linker=linux_linker,
            )
        except OSError, UnicodeError, ValueError, RegistryError:
            print("check failed", file=sys.stderr)
            return 1
        if errors:
            for error in errors:
                print(f"error: {_error_detail(error)}", file=sys.stderr)
            return 1
        return 0
    if (
        len(arguments) == 3
        and arguments[:2] == ("check", "focused")
        and arguments[2] in checks.FOCUS_AREAS
    ):
        try:
            errors = checks.run_area(
                repository,
                arguments[2],
                git_executable=git_executable,
                git_environment=git_environment,
                cargo_executable=cargo_executable,
                cargo_fmt_executable=cargo_fmt_executable,
                rustc_executable=rustc_executable,
                rustdoc_executable=rustdoc_executable,
                rustfmt_executable=rustfmt_executable,
                pycache_prefix=pycache_prefix,
                linux_linker=linux_linker,
            )
        except OSError, UnicodeError, ValueError, RegistryError:
            print("check failed", file=sys.stderr)
            return 1
        if errors:
            for error in errors:
                print(f"error: {_error_detail(error)}", file=sys.stderr)
            return 1
        return 0
    if arguments in (
        ("environment", "verify-native"),
        ("environment", "verify-native", "--write-evidence"),
    ):
        try:
            if git_executable is None:
                raise ValueError("sealed Git capability required")
            native = clean.verify_isolated_native(
                repository,
                git_executable=git_executable,
            )
            if arguments[-1] == "--write-evidence":
                clean.write_native_evidence(repository, native)
            else:
                tracked = native_evidence_from_summary(
                    _canonical_object(repository, RELEASE_SUMMARY)
                )
                if tracked is not None and tracked != native:
                    raise ValueError("native verification differs from tracked G1")
            return 0
        except OSError, TypeError, ValueError, RegistryError:
            print("environment verification failed", file=sys.stderr)
            return 1
    if arguments == ("environment", "verify-linux"):
        try:
            if git_executable is None or docker_executable is None:
                raise ValueError("sealed verifier capability required")
            lock = load_source_lock(repository)
            result = _validated_linux_observation(
                clean.verify_linux(
                    repository,
                    lock,
                    git_executable=git_executable,
                    docker_executable=docker_executable,
                )
            )
            print(encode_canonical_value(result).decode("ascii"), end="")
            expected = {
                "schema_version": 0,
                "protocol": "docker-clean-linux-v0",
                "state": lock.clean_linux.state,
                "observed_daemon_state": lock.clean_linux.observed_daemon_state,
                "blocker": lock.clean_linux.blocker,
                "deadline": lock.clean_linux.deadline,
            }
            if result != expected:
                raise ValueError("clean-Linux observation differs from the source lock")
            return 0
        except OSError, TypeError, UnicodeError, ValueError, RegistryError:
            print("environment verification failed", file=sys.stderr)
            return 1
    if arguments in (
        ("generate", "source-doctor"),
        ("check", "source-report"),
    ):
        try:
            expected = _current_report(repository)
        except OSError, TypeError, ValueError:
            print("source report failed", file=sys.stderr)
            return 1

        if arguments == ("generate", "source-doctor"):
            try:
                _write_source_report(repository, expected)
            except OSError, TypeError, ValueError:
                print("source report failed", file=sys.stderr)
                return 1
            return 0

        try:
            actual = read_regular_below(repository, _REPORT, MAX_REPORT_BYTES)
        except OSError, TypeError, ValueError:
            print("source report unavailable", file=sys.stderr)
            return 1
        if actual != expected:
            print("source report differs", file=sys.stderr)
            return 1
        return 0

    try:
        if arguments == ("generate", "release-summary"):
            _replace_canonical(repository, RELEASE_SUMMARY, _release_value(repository))
            return 0
        if arguments == (
            "generate",
            "release-summary",
            "--native-evidence",
            NATIVE_EVIDENCE.as_posix(),
        ):
            native = _canonical_object(repository, NATIVE_EVIDENCE)
            _replace_canonical(
                repository,
                RELEASE_SUMMARY,
                _release_value(
                    repository,
                    native,
                    git_executable=git_executable,
                    git_environment=git_environment,
                ),
            )
            return 0
        if arguments == ("check", "release-summary"):
            errors = check_tracked_reports(
                repository,
                git_executable=git_executable,
                git_environment=git_environment,
            )
            if errors:
                for error in errors:
                    print(f"error: {_error_detail(error)}", file=sys.stderr)
                return 1
            return 0
    except (
        OSError,
        UnicodeError,
        ValueError,
        RegistryError,
        subprocess.SubprocessError,
    ) as error:
        print(f"error: {_error_detail(error)}", file=sys.stderr)
        return 1

    print(_SOURCE_USAGE, file=sys.stderr)
    return 2


def _module_main(
    environment: dict[str, str],
    arguments: tuple[str, ...],
    root: Path,
) -> int:
    if type(environment) is not dict or type(arguments) is not tuple:
        raise ValueError("sealed module invocation")
    linux_linker = _module_linux_linker_context(root, environment)
    git, git_environment, cargo, cargo_fmt, rustc, rustdoc, rustfmt, pycache_prefix = (
        _module_capability_context(
            root,
            environment,
            clean_linux=linux_linker is not None,
        )
    )
    docker = (
        _module_docker_context(root, environment)
        if arguments == ("environment", "verify-linux")
        else None
    )
    return main(
        arguments,
        root,
        git_executable=git,
        git_environment=git_environment,
        docker_executable=docker,
        cargo_executable=cargo,
        cargo_fmt_executable=cargo_fmt,
        rustc_executable=rustc,
        rustdoc_executable=rustdoc,
        rustfmt_executable=rustfmt,
        pycache_prefix=pycache_prefix,
        linux_linker=linux_linker,
    )


if __name__ == "__main__":
    try:
        _exit_status = _module_main(
            dict(os.environ),
            tuple(sys.argv[1:]),
            Path.cwd(),
        )
    except (OSError, ValueError, RegistryError) as error:
        print(f"error: {_error_detail(error)}", file=sys.stderr)
        _exit_status = 1
    raise SystemExit(_exit_status)
