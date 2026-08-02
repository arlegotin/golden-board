from dataclasses import replace
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from golden_board.source_doctor import (
    DIAGNOSTIC_PRECEDENCE,
    SourceDoctorError,
    snapshot_regular_file,
)
from golden_board.source_lock import AnthologyLock, SafeFileError


def anthology(path: object = PurePosixPath("source.pgn")) -> AnthologyLock:
    return AnthologyLock(
        path=path,  # type: ignore[arg-type]
        file_type="regular",
        byte_length=999,
        sha256="0" * 64,
        encoding="UTF-8",
        bom="absent",
        newlines="LF",
        final_lf="present",
    )


class SourceSnapshotTests(unittest.TestCase):
    def test_diagnostic_contract_is_closed_and_ordered(self) -> None:
        self.assertEqual(
            (
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
            ),
            DIAGNOSTIC_PRECEDENCE,
        )
        error = SourceDoctorError("source.path")
        self.assertEqual("source.path", error.code)
        self.assertEqual("source.path", str(error))

    def test_returns_direct_regular_file_bytes_unchanged(self) -> None:
        raw = b"[Event \"stale\"]\r\n\xff"
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.pgn").write_bytes(raw)
            self.assertEqual(raw, snapshot_regular_file(root, anthology()))

    def test_zero_exact_and_limit_plus_one(self) -> None:
        for raw, limit, expected_code in (
            (b"", 0, None),
            (b"abc", 3, None),
            (b"abc", 2, "source.size_limit"),
        ):
            with self.subTest(raw=raw, limit=limit), TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "source.pgn").write_bytes(raw)
                if expected_code is None:
                    self.assertEqual(
                        raw, snapshot_regular_file(root, anthology(), limit)
                    )
                else:
                    with self.assertRaises(SourceDoctorError) as caught:
                        snapshot_regular_file(root, anthology(), limit)
                    self.assertEqual(expected_code, caught.exception.code)

    def test_maps_shared_reader_failures_and_preserves_cause(self) -> None:
        mappings = (
            ("safe_file.path", "source.path"),
            ("safe_file.root", "source.path"),
            ("safe_file.capability", "source.path"),
            ("safe_file.type", "source.type"),
            ("safe_file.limit", "source.size_limit"),
            ("safe_file.changed", "source.changed"),
            ("safe_file.unknown", "source.path"),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            lock = anthology()
            for safe_code, source_code in mappings:
                with self.subTest(safe_code=safe_code):
                    cause = SafeFileError(safe_code)
                    with patch(
                        "golden_board.source_doctor.read_regular_below",
                        side_effect=cause,
                    ) as reader, self.assertRaises(SourceDoctorError) as caught:
                        snapshot_regular_file(root, lock)
                    self.assertEqual(source_code, caught.exception.code)
                    self.assertIs(cause, caught.exception.__cause__)
                    reader.assert_called_once_with(root, lock.path, 16_777_216)

    def test_rejects_invalid_lock_paths_without_delegating(self) -> None:
        invalid = (
            "source.pgn",
            PurePosixPath(),
            PurePosixPath("/source.pgn"),
            PurePosixPath("../source.pgn"),
            PurePosixPath("nested/../source.pgn"),
            PurePosixPath("nested\\source.pgn"),
            PurePosixPath("nested/\0source.pgn"),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for path in invalid:
                with self.subTest(path=path), patch(
                    "golden_board.source_doctor.read_regular_below"
                ) as reader, self.assertRaises(SourceDoctorError) as caught:
                    snapshot_regular_file(root, replace(anthology(), path=path))
                self.assertEqual("source.path", caught.exception.code)
                reader.assert_not_called()

    def test_delegates_once_and_does_not_validate_snapshot_profile(self) -> None:
        raw = b"\xef\xbb\xbf\xff\rno-final-lf"
        with TemporaryDirectory() as directory:
            root = Path(directory)
            lock = anthology(PurePosixPath("nested/source.pgn"))
            with patch(
                "golden_board.source_doctor.read_regular_below", return_value=raw
            ) as reader:
                self.assertIs(raw, snapshot_regular_file(root, lock, 123))
            reader.assert_called_once_with(root, lock.path, 123)


if __name__ == "__main__":
    unittest.main()
