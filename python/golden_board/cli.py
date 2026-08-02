import os
from pathlib import Path, PurePosixPath
import stat
import sys

from golden_board import source_doctor
from golden_board.manifest import decode_canonical_manifest, encode_canonical_value
from golden_board.source_lock import load_source_lock, read_regular_below


MAX_REPORT_BYTES = 1 << 24
_REPORT = PurePosixPath("reports/source-doctor.json")
_USAGE = "usage: generate source-doctor | check source-report"
_READ_CHUNK = 64 * 1024


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


def _write_all(descriptor: int, raw: bytes) -> None:
    view = memoryview(raw)
    offset = 0
    while offset < len(view):
        written = os.write(descriptor, view[offset:])
        if written <= 0:
            raise ValueError("source report short write")
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


def _current_report(root: Path) -> bytes:
    lock = load_source_lock(root)
    report = source_doctor.build_source_report(root, lock)
    return encode_canonical_value(report)


def main(argv: list[str] | None = None, root: Path = Path.cwd()) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if arguments not in (
        ("generate", "source-doctor"),
        ("check", "source-report"),
    ):
        print(_USAGE, file=sys.stderr)
        return 2

    try:
        expected = _current_report(root)
    except (OSError, TypeError, ValueError):
        print("source report failed", file=sys.stderr)
        return 1

    if arguments == ("generate", "source-doctor"):
        try:
            _write_source_report(root, expected)
        except (OSError, TypeError, ValueError):
            print("source report failed", file=sys.stderr)
            return 1
        return 0

    try:
        actual = read_regular_below(root, _REPORT, MAX_REPORT_BYTES)
    except (OSError, TypeError, ValueError):
        print("source report unavailable", file=sys.stderr)
        return 1
    if actual != expected:
        print("source report differs", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
