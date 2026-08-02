from pathlib import Path, PurePosixPath

from golden_board.source_lock import AnthologyLock, SafeFileError, read_regular_below


DIAGNOSTIC_PRECEDENCE = (
    "source.path",
    "source.type",
    "source.size_limit",
    "source.changed",
    "source.lock_size",
    "source.lock_hash",
    "source.utf8",
    "source.bom",
    "source.control",
    "source.newline",
    "source.final_lf",
    "source.fence_structure",
    "source.fence_count",
)


class SourceDoctorError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def snapshot_regular_file(
    root: Path,
    lock: AnthologyLock,
    max_bytes: int = 16_777_216,
) -> bytes:
    path = lock.path
    if (
        type(path) is not PurePosixPath
        or any(character in path.as_posix() for character in ("\0", "\\"))
        or path.is_absolute()
        or not path.parts
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise SourceDoctorError("source.path")
    try:
        return read_regular_below(root, path, max_bytes)
    except SafeFileError as error:
        code = {
            "safe_file.type": "source.type",
            "safe_file.limit": "source.size_limit",
            "safe_file.changed": "source.changed",
        }.get(str(error), "source.path")
        raise SourceDoctorError(code) from error
