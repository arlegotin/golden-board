from __future__ import annotations

import os
import stat
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import cast

from golden_board import source_doctor
from golden_board.manifest import decode_canonical_manifest, encode_canonical_value
from golden_board.reports import (
    MAX_REPORT_BYTES,
    ReportError,
    _read_below,
    build_release_summary,
    check_tracked_reports,
)
from golden_board.source_lock import SourceLock, load_source_lock, read_regular_below


SOURCE_REPORT = Path("reports/source-doctor.json")
RELEASE_SUMMARY = Path("reports/release-summary.json")
NATIVE_EVIDENCE = Path("artifacts/native-verification.json")
_REPORT = PurePosixPath(SOURCE_REPORT.as_posix())
_SOURCE_USAGE = "usage: generate source-doctor | check source-report"
_READ_CHUNK = 64 * 1024
_MAX_ERROR_DETAIL = 512


def build_source_report(root: Path, lock: SourceLock) -> dict[str, object]:
    return source_doctor.build_source_report(root, lock)


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
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ReportError("report writes require descriptor-relative no-follow opens")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY
    try:
        repository = os.open(root, flags)
    except OSError as error:
        raise ReportError("cannot open repository root descriptor") from error
    try:
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
    except BaseException:
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
    return directory


def _existing_leaf_is_regular(directory: int, name: str) -> None:
    try:
        facts = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(facts.st_mode):
        raise ReportError(f"report destination is not a regular file: reports/{name}")


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

    root_descriptor: int | None = None
    reports_descriptor: int | None = None
    temporary_descriptor: int | None = None
    temporary_name: str | None = None
    failure: BaseException | None = None
    committed = False
    try:
        root_descriptor = os.open(root, _directory_flags())
        try:
            reports_descriptor = os.open(
                "reports", _directory_flags(), dir_fd=root_descriptor
            )
        except FileNotFoundError:
            os.mkdir("reports", 0o755, dir_fd=root_descriptor)
            reports_descriptor = os.open(
                "reports", _directory_flags(), dir_fd=root_descriptor
            )

        try:
            destination = os.stat(
                _REPORT.name,
                dir_fd=reports_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            destination = None
        if destination is not None and not stat.S_ISREG(destination.st_mode):
            raise ValueError("source report destination")

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
            break
        if temporary_descriptor is None or temporary_name is None:
            raise ValueError("source report temporary names")

        _write_all(temporary_descriptor, raw)
        os.fsync(temporary_descriptor)
        closing = temporary_descriptor
        temporary_descriptor = None
        os.close(closing)

        verified = _read_regular_at(
            reports_descriptor,
            temporary_name,
            MAX_REPORT_BYTES,
        )
        if verified != raw:
            raise ValueError("source report verification")
        decode_canonical_manifest(verified)

        try:
            destination = os.stat(
                _REPORT.name,
                dir_fd=reports_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            destination = None
        if destination is not None and not stat.S_ISREG(destination.st_mode):
            raise ValueError("source report destination")

        os.replace(
            temporary_name,
            _REPORT.name,
            src_dir_fd=reports_descriptor,
            dst_dir_fd=reports_descriptor,
        )
        temporary_name = None
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
        if temporary_name is not None and reports_descriptor is not None:
            try:
                os.unlink(temporary_name, dir_fd=reports_descriptor)
            except FileNotFoundError:
                pass
            except OSError as error:
                if failure is None:
                    failure = error
        for descriptor in (reports_descriptor, root_descriptor):
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


def _render_temporary(root: Path, destination: Path, value: object) -> tuple[int, str]:
    if destination != RELEASE_SUMMARY:
        raise ReportError(f"undeclared report destination: {destination}")
    raw = _canonical_bytes(value)
    directory = _open_reports_directory(root, create=True)
    temporary_name: str | None = None
    try:
        _existing_leaf_is_regular(directory, destination.name)
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        for index in range(64):
            candidate = f".{destination.name}.{index}.tmp"
            try:
                descriptor = os.open(candidate, flags, 0o600, dir_fd=directory)
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if temporary_name is None:
            raise ReportError("no bounded temporary report name is available")
        descriptor_open = True
        try:
            _write_all(descriptor, raw)
            os.fsync(descriptor)
            closing = descriptor
            descriptor_open = False
            os.close(closing)
            read_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
            descriptor = os.open(temporary_name, read_flags, dir_fd=directory)
            descriptor_open = True
            facts = os.fstat(descriptor)
            if not stat.S_ISREG(facts.st_mode) or facts.st_size != len(raw):
                raise ReportError("temporary report identity changed")
            verified = bytearray()
            while True:
                chunk = os.read(
                    descriptor,
                    min(64 * 1024, MAX_REPORT_BYTES + 1 - len(verified)),
                )
                if not chunk:
                    break
                verified.extend(chunk)
                if len(verified) > MAX_REPORT_BYTES:
                    raise ReportError("temporary report exceeds the M0 byte cap")
            if bytes(verified) != raw:
                raise ReportError(
                    f"temporary report verification failed: {destination}"
                )
            parsed = decode_canonical_manifest(bytes(verified))
            if encode_canonical_value(parsed) != bytes(verified):
                raise ReportError("temporary report is not canonical")
        except BaseException:
            if descriptor_open:
                closing = descriptor
                descriptor_open = False
                try:
                    os.close(closing)
                except OSError:
                    pass
            raise
        else:
            if descriptor_open:
                closing = descriptor
                descriptor_open = False
                os.close(closing)
        return directory, temporary_name
    except BaseException:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=directory)
            except OSError:
                pass
        try:
            os.close(directory)
        except OSError:
            pass
        raise


def _replace_canonical(root: Path, destination: Path, value: object) -> None:
    directory, temporary_name = _render_temporary(root, destination, value)
    try:
        _existing_leaf_is_regular(directory, destination.name)
        os.replace(
            temporary_name,
            destination.name,
            src_dir_fd=directory,
            dst_dir_fd=directory,
        )
    except BaseException:
        try:
            os.unlink(temporary_name, dir_fd=directory)
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


def main(
    argv: Sequence[str] | None = None,
    root: Path = Path.cwd(),
    *,
    git_executable: Path | None = None,
    git_environment: dict[str, str] | None = None,
) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    repository = root
    if arguments in (
        ("generate", "source-doctor"),
        ("check", "source-report"),
    ):
        try:
            expected = _current_report(repository)
        except (OSError, TypeError, ValueError):
            print("source report failed", file=sys.stderr)
            return 1

        if arguments == ("generate", "source-doctor"):
            try:
                _write_source_report(repository, expected)
            except (OSError, TypeError, ValueError):
                print("source report failed", file=sys.stderr)
                return 1
            return 0

        try:
            actual = read_regular_below(repository, _REPORT, MAX_REPORT_BYTES)
        except (OSError, TypeError, ValueError):
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
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as error:
        print(f"error: {_error_detail(error)}", file=sys.stderr)
        return 1

    print(_SOURCE_USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
