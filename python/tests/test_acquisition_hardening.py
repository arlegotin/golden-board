from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import unittest
from unittest.mock import patch

from golden_board import acquisition
from golden_board.manifest import encode_canonical_value


class AcquisitionPublicationHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self._new_root("checkout")
        self.payload = self.root / "artifacts/uv-cache/payload"

    def _new_root(self, name: str) -> Path:
        root = self.base / name
        for relative in acquisition.INVENTORY_ROOTS:
            directory = root / relative
            directory.mkdir(parents=True)
            (directory / "payload").write_bytes(relative.as_posix().encode())
        (root / "Cargo.lock").write_text("version = 4\n", encoding="utf-8")
        return root

    def _scratch(self, artifacts: Path | None = None) -> list[Path]:
        directory = artifacts or self.root / "artifacts"
        name = acquisition.INVENTORY_PATH.name
        return list(directory.glob(f".{name}.*.tmp")) + list(
            directory.glob(f".{name}.*.bak")
        )

    @staticmethod
    def _other_device(value: os.stat_result) -> os.stat_result:
        fields = list(value)
        fields[2] = value.st_dev + 1
        return os.stat_result(fields)

    def test_pre_replace_mutation_preserves_previous_inventory(self) -> None:
        value = acquisition.build_inventory(self.root)
        acquisition.write_inventory(self.root, value)
        destination = self.root / acquisition.INVENTORY_PATH
        before = destination.stat()
        before_bytes = destination.read_bytes()
        write_all = acquisition._write_all

        def mutate_after_write(descriptor: int, raw: bytes) -> None:
            write_all(descriptor, raw)
            self.payload.write_bytes(b"changed before replace")

        with (
            patch.object(acquisition, "_write_all", side_effect=mutate_after_write),
            self.assertRaises(acquisition.AcquisitionError),
        ):
            acquisition.write_inventory(self.root, value)

        after = destination.stat()
        self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))
        self.assertEqual(before_bytes, destination.read_bytes())
        self.assertFalse(self._scratch())

    def test_post_replace_failure_restores_previous_inode_and_bytes(self) -> None:
        value = acquisition.build_inventory(self.root)
        acquisition.write_inventory(self.root, value)
        destination = self.root / acquisition.INVENTORY_PATH
        before = destination.stat()
        before_bytes = destination.read_bytes()
        replace = os.replace
        mutated = False

        def replace_then_mutate(
            source: str,
            target: str,
            *,
            src_dir_fd: int,
            dst_dir_fd: int,
        ) -> None:
            nonlocal mutated
            replace(
                source,
                target,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
            )
            if not mutated and source.endswith(".tmp"):
                mutated = True
                self.payload.write_bytes(b"changed after replace")

        with (
            patch.object(acquisition.os, "replace", side_effect=replace_then_mutate),
            self.assertRaises(acquisition.AcquisitionError),
        ):
            acquisition.write_inventory(self.root, value)

        after = destination.stat()
        self.assertTrue(mutated)
        self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))
        self.assertEqual(before_bytes, destination.read_bytes())
        self.assertFalse(self._scratch())

    def test_post_replace_failure_without_prior_inventory_removes_destination(self) -> None:
        value = acquisition.build_inventory(self.root)
        replace = os.replace
        mutated = False

        def replace_then_mutate(
            source: str,
            target: str,
            *,
            src_dir_fd: int,
            dst_dir_fd: int,
        ) -> None:
            nonlocal mutated
            replace(
                source,
                target,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
            )
            if not mutated:
                mutated = True
                self.payload.write_bytes(b"changed after replace")

        with (
            patch.object(acquisition.os, "replace", side_effect=replace_then_mutate),
            self.assertRaises(acquisition.AcquisitionError),
        ):
            acquisition.write_inventory(self.root, value)

        self.assertTrue(mutated)
        self.assertFalse((self.root / acquisition.INVENTORY_PATH).exists())
        self.assertFalse(self._scratch())

    def test_rollback_refuses_to_clobber_an_atomically_substituted_destination(self) -> None:
        value = acquisition.build_inventory(self.root)
        acquisition.write_inventory(self.root, value)
        destination = self.root / acquisition.INVENTORY_PATH
        prior = destination.stat()
        prior_bytes = destination.read_bytes()
        foreign = destination.parent / ".foreign-inventory"
        foreign.write_bytes(b"foreign destination")
        foreign_stat = foreign.stat()
        replace = os.replace
        substituted = False

        def replace_then_substitute(
            source: str,
            target: str,
            *,
            src_dir_fd: int,
            dst_dir_fd: int,
        ) -> None:
            nonlocal substituted
            replace(
                source,
                target,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
            )
            if not substituted and source.endswith(".tmp"):
                substituted = True
                replace(
                    foreign.name,
                    target,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                )

        with (
            patch.object(acquisition.os, "replace", side_effect=replace_then_substitute),
            self.assertRaisesRegex(
                acquisition.AcquisitionError, "inventory rollback failed"
            ),
        ):
            acquisition.write_inventory(self.root, value)

        current = destination.stat()
        self.assertTrue(substituted)
        self.assertEqual(
            (foreign_stat.st_dev, foreign_stat.st_ino),
            (current.st_dev, current.st_ino),
        )
        self.assertEqual(b"foreign destination", destination.read_bytes())
        backups = list(destination.parent.glob(f".{destination.name}.*.bak"))
        self.assertEqual(1, len(backups))
        backup_stat = backups[0].stat()
        self.assertEqual(
            (prior.st_dev, prior.st_ino),
            (backup_stat.st_dev, backup_stat.st_ino),
        )
        self.assertEqual(prior_bytes, backups[0].read_bytes())

    def test_success_fsyncs_the_directory_after_backup_unlink(self) -> None:
        value = acquisition.build_inventory(self.root)
        acquisition.write_inventory(self.root, value)
        fsync = os.fsync
        unlink = os.unlink
        backup_unlinked = False
        directory_fsync_states: list[bool] = []

        def observe_unlink(path: str, *, dir_fd: int) -> None:
            nonlocal backup_unlinked
            unlink(path, dir_fd=dir_fd)
            if path.endswith(".bak"):
                backup_unlinked = True

        def observe_fsync(descriptor: int) -> None:
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                directory_fsync_states.append(backup_unlinked)
            fsync(descriptor)

        with (
            patch.object(acquisition.os, "unlink", side_effect=observe_unlink),
            patch.object(acquisition.os, "fsync", side_effect=observe_fsync),
        ):
            acquisition.write_inventory(self.root, value)

        self.assertEqual([False, True], directory_fsync_states)
        self.assertFalse(self._scratch())

    def test_directory_fsync_failure_rolls_back_with_and_without_prior(self) -> None:
        for prior in (False, True):
            root = self._new_root(f"fsync-{prior}")
            value = acquisition.build_inventory(root)
            destination = root / acquisition.INVENTORY_PATH
            if prior:
                acquisition.write_inventory(root, value)
                before = destination.stat()
                before_bytes = destination.read_bytes()
            fsync = os.fsync
            failed = False

            def fail_publication_fsync(descriptor: int) -> None:
                nonlocal failed
                if stat.S_ISDIR(os.fstat(descriptor).st_mode) and not failed:
                    failed = True
                    raise OSError("injected directory fsync failure")
                fsync(descriptor)

            with (
                self.subTest(prior=prior),
                patch.object(acquisition.os, "fsync", side_effect=fail_publication_fsync),
                self.assertRaises(acquisition.AcquisitionError),
            ):
                acquisition.write_inventory(root, value)

            self.assertTrue(failed)
            if prior:
                after = destination.stat()
                self.assertEqual(
                    (before.st_dev, before.st_ino), (after.st_dev, after.st_ino)
                )
                self.assertEqual(before_bytes, destination.read_bytes())
            else:
                self.assertFalse(destination.exists())
            self.assertFalse(self._scratch(root / "artifacts"))

    def test_post_replace_reload_must_equal_the_requested_inventory(self) -> None:
        value = acquisition.build_inventory(self.root)
        replace = os.replace
        substituted = False

        def replace_then_publish_different_valid_state(
            source: str,
            target: str,
            *,
            src_dir_fd: int,
            dst_dir_fd: int,
        ) -> None:
            nonlocal substituted
            replace(
                source,
                target,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
            )
            if not substituted:
                substituted = True
                self.payload.write_bytes(b"different valid state")
                replacement = acquisition.build_inventory(self.root)
                (self.root / acquisition.INVENTORY_PATH).write_bytes(
                    encode_canonical_value(replacement)
                )

        with (
            patch.object(
                acquisition.os,
                "replace",
                side_effect=replace_then_publish_different_valid_state,
            ),
            self.assertRaises(acquisition.AcquisitionError),
        ):
            acquisition.write_inventory(self.root, value)

        self.assertTrue(substituted)
        self.assertFalse((self.root / acquisition.INVENTORY_PATH).exists())

    def test_temporary_file_is_verified_through_the_held_directory(self) -> None:
        value = acquisition.build_inventory(self.root)
        read_regular_below = acquisition.read_regular_below

        def reject_pathname_temporary_reads(
            root: Path, relative: PurePosixPath, maximum: int
        ) -> bytes:
            if relative.name.endswith(".tmp"):
                raise AssertionError("temporary file was reopened by pathname")
            return read_regular_below(root, relative, maximum)

        with patch.object(
            acquisition,
            "read_regular_below",
            side_effect=reject_pathname_temporary_reads,
        ):
            acquisition.write_inventory(self.root, value)

        self.assertEqual(value, acquisition.load_inventory(self.root))

    def test_root_and_artifacts_identity_exchanges_fail_before_commit(self) -> None:
        for exchange in ("root", "artifacts"):
            root = self._new_root(f"identity-{exchange}")
            value = acquisition.build_inventory(root)
            acquisition.write_inventory(root, value)
            destination = root / acquisition.INVENTORY_PATH
            before = destination.stat()
            before_bytes = destination.read_bytes()
            displaced = self.base / f"identity-{exchange}-displaced"
            write_all = acquisition._write_all

            def exchange_parent(descriptor: int, raw: bytes) -> None:
                write_all(descriptor, raw)
                if exchange == "root":
                    root.rename(displaced)
                    root.mkdir()
                    (root / "artifacts").mkdir()
                else:
                    (root / "artifacts").rename(displaced)
                    (root / "artifacts").mkdir()

            with (
                self.subTest(exchange=exchange),
                patch.object(acquisition, "_write_all", side_effect=exchange_parent),
                self.assertRaisesRegex(
                    acquisition.AcquisitionError,
                    "acquisition directory identity changed",
                ),
            ):
                acquisition.write_inventory(root, value)

            old_artifacts = (
                displaced / "artifacts" if exchange == "root" else displaced
            )
            restored = old_artifacts / acquisition.INVENTORY_PATH.name
            after = restored.stat()
            self.assertEqual(
                (before.st_dev, before.st_ino), (after.st_dev, after.st_ino)
            )
            self.assertEqual(before_bytes, restored.read_bytes())
            self.assertFalse(self._scratch(old_artifacts))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks required")
    def test_enumeration_caps_file_and_link_paths_by_bytes_and_depth(self) -> None:
        cases: list[tuple[str, bool, bool]] = [
            ("file-bytes", False, False),
            ("file-depth", False, True),
            ("link-bytes", True, False),
            ("link-depth", True, True),
        ]
        for name, is_link, is_depth in cases:
            root = self._new_root(name)
            relative_root = PurePosixPath(
                "artifacts/uv-python" if is_link else "artifacts/uv-cache"
            )
            if is_depth:
                relative = relative_root / "a" / "b" / "c" / "entry"
                (root / relative.parent).mkdir(parents=True)
            else:
                relative = relative_root / ("long-inventory-entry-name" * 3)
            path = root / relative
            if is_link:
                path.symlink_to(root / "artifacts/uv-python/payload")
            else:
                path.write_bytes(b"bounded")
            limit_name = (
                "MAX_RELATIVE_PATH_DEPTH" if is_depth else "MAX_RELATIVE_PATH_BYTES"
            )
            limit = len(relative.parts) - 1 if is_depth else len(os.fsencode(str(relative))) - 1
            with (
                self.subTest(case=name),
                patch.object(acquisition, limit_name, limit),
                self.assertRaises(acquisition.AcquisitionError),
            ):
                acquisition.build_inventory(root)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks required")
    def test_python_link_containment_never_uses_path_resolve(self) -> None:
        python_root = self.root / "artifacts/uv-python"
        inside = python_root / "inside-link"
        outside = python_root / "outside-link"
        inside.symlink_to(python_root / "payload")
        escaped = self.root / "escaped"
        escaped.write_bytes(b"outside")
        outside.symlink_to(escaped)
        with patch.object(
            Path,
            "resolve",
            side_effect=AssertionError("symlink containment used Path.resolve"),
        ):
            self.assertTrue(
                acquisition._contained_python_link(
                    self.root,
                    PurePosixPath("artifacts/uv-python/inside-link"),
                )
            )
            self.assertFalse(
                acquisition._contained_python_link(
                    self.root,
                    PurePosixPath("artifacts/uv-python/outside-link"),
                )
            )

    def test_validation_caps_file_and_link_paths_by_bytes_and_depth(self) -> None:
        roots = [path.as_posix() for path in acquisition.INVENTORY_ROOTS]
        paths = {
            "file": "artifacts/uv-cache/payload",
            "link": "artifacts/uv-python/python3",
        }
        for kind, path in paths.items():
            document: dict[str, object] = {
                "schema_version": 0,
                "roots": roots,
                "files": (
                    [{"byte_length": 0, "path": path, "sha256": "0" * 64}]
                    if kind == "file"
                    else []
                ),
                "links": ([{"path": path, "target": "payload"}] if kind == "link" else []),
            }
            limits = (
                ("MAX_RELATIVE_PATH_BYTES", len(os.fsencode(path)) - 1),
                ("MAX_RELATIVE_PATH_DEPTH", len(PurePosixPath(path).parts) - 1),
            )
            for limit_name, limit in limits:
                with (
                    self.subTest(kind=kind, limit=limit_name),
                    patch.object(acquisition, limit_name, limit),
                    patch.object(
                        acquisition,
                        "build_inventory",
                        side_effect=AssertionError("validation reached live rebuild"),
                    ),
                    self.assertRaises(acquisition.AcquisitionError),
                ):
                    acquisition.validate_inventory(self.root, document)

    def test_each_acquisition_root_rejects_mount_and_device_escape(self) -> None:
        stat_call = os.stat
        ismount = os.path.ismount
        for relative in acquisition.INVENTORY_ROOTS:
            target = self.root / relative
            leaf = relative.name

            def cross_device(path: object, *args: object, **kwargs: object) -> os.stat_result:
                value = stat_call(path, *args, **kwargs)
                if path == leaf and kwargs.get("dir_fd") is not None:
                    return self._other_device(value)
                return value

            with (
                self.subTest(root=relative, rejection="device"),
                patch.object(acquisition.os, "stat", side_effect=cross_device),
                self.assertRaises(acquisition.AcquisitionError),
            ):
                acquisition.build_inventory(self.root)

            with (
                self.subTest(root=relative, rejection="mount"),
                patch.object(
                    acquisition.os.path,
                    "ismount",
                    side_effect=lambda path, target=target: Path(path) == target
                    or ismount(path),
                ),
                self.assertRaises(acquisition.AcquisitionError),
            ):
                acquisition.build_inventory(self.root)

    def test_nested_mount_or_device_escape_is_rejected_before_traversal(self) -> None:
        nested = self.root / "artifacts/uv-cache/nested"
        nested.mkdir()
        (nested / "must-not-read").write_bytes(b"outside")
        nested_identity = (nested.stat().st_dev, nested.stat().st_ino)
        stat_call = os.stat
        scandir = os.scandir
        ismount = os.path.ismount

        def cross_device(path: object, *args: object, **kwargs: object) -> os.stat_result:
            value = stat_call(path, *args, **kwargs)
            if path == "nested" and kwargs.get("dir_fd") is not None:
                return self._other_device(value)
            return value

        def reject_nested_scan(descriptor: int) -> os.ScandirIterator[str]:
            facts = os.fstat(descriptor)
            if (facts.st_dev, facts.st_ino) == nested_identity:
                raise AssertionError("escaped directory was traversed")
            return scandir(descriptor)

        with (
            patch.object(acquisition.os, "stat", side_effect=cross_device),
            patch.object(acquisition.os, "scandir", side_effect=reject_nested_scan),
            self.assertRaises(acquisition.AcquisitionError),
        ):
            acquisition.build_inventory(self.root)

        with (
            patch.object(
                acquisition.os.path,
                "ismount",
                side_effect=lambda path: Path(path) == nested or ismount(path),
            ),
            patch.object(acquisition.os, "scandir", side_effect=reject_nested_scan),
            self.assertRaises(acquisition.AcquisitionError),
        ):
            acquisition.build_inventory(self.root)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks required")
    def test_every_regular_file_and_symlink_must_share_repository_device(self) -> None:
        link = self.root / "artifacts/uv-python/python3"
        link.symlink_to("payload")
        stat_call = os.stat
        fstat = os.fstat
        for relative in (
            PurePosixPath("artifacts/uv-cache/payload"),
            PurePosixPath("artifacts/uv-python/payload"),
            PurePosixPath("artifacts/cargo-home/payload"),
            PurePosixPath("artifacts/uv-python/python3"),
        ):
            parent = (self.root / relative.parent).stat()
            parent_identity = (parent.st_dev, parent.st_ino)

            def cross_device(path: object, *args: object, **kwargs: object) -> os.stat_result:
                value = stat_call(path, *args, **kwargs)
                descriptor = kwargs.get("dir_fd")
                if (
                    path == relative.name
                    and isinstance(descriptor, int)
                    and (fstat(descriptor).st_dev, fstat(descriptor).st_ino)
                    == parent_identity
                ):
                    return self._other_device(value)
                return value

            with (
                self.subTest(path=relative),
                patch.object(acquisition.os, "stat", side_effect=cross_device),
                self.assertRaises(acquisition.AcquisitionError),
            ):
                acquisition.build_inventory(self.root)

    def test_containment_failure_cannot_publish_inventory(self) -> None:
        value = acquisition.build_inventory(self.root)
        target = self.root / acquisition.INVENTORY_ROOTS[0]
        ismount = os.path.ismount
        with (
            patch.object(
                acquisition.os.path,
                "ismount",
                side_effect=lambda path: Path(path) == target or ismount(path),
            ),
            self.assertRaises(acquisition.AcquisitionError),
        ):
            acquisition.write_inventory(self.root, value)
        self.assertFalse((self.root / acquisition.INVENTORY_PATH).exists())
        self.assertFalse(self._scratch())

    def test_regular_file_mount_is_rejected_before_hash_or_publication(self) -> None:
        target = self.root / "artifacts/uv-cache/payload"
        target.write_bytes(b"must-not-hash-mounted-file")
        value = acquisition.build_inventory(self.root)
        ismount = os.path.ismount
        sha256 = acquisition.hashlib.sha256

        def reject_target_hash(raw: bytes = b"") -> object:
            if raw == b"must-not-hash-mounted-file":
                raise AssertionError("mounted file was hashed")
            return sha256(raw)

        def mounted(path: object) -> bool:
            return Path(path) == target or ismount(path)

        with (
            patch.object(acquisition.os.path, "ismount", side_effect=mounted),
            patch.object(acquisition.hashlib, "sha256", side_effect=reject_target_hash),
            self.assertRaises(acquisition.AcquisitionError),
        ):
            acquisition.build_inventory(self.root)

        with (
            patch.object(acquisition.os.path, "ismount", side_effect=mounted),
            patch.object(acquisition.hashlib, "sha256", side_effect=reject_target_hash),
            self.assertRaises(acquisition.AcquisitionError),
        ):
            acquisition.write_inventory(self.root, value)
        self.assertFalse((self.root / acquisition.INVENTORY_PATH).exists())

    def test_linux_mount_identity_rejects_directory_before_traversal(self) -> None:
        target = self.root / "artifacts/uv-cache"
        target_identity = (target.stat().st_dev, target.stat().st_ino)
        scandir = os.scandir

        def reject_target_scan(descriptor: int):
            facts = os.fstat(descriptor)
            if (facts.st_dev, facts.st_ino) == target_identity:
                raise AssertionError("mounted directory was traversed")
            return scandir(descriptor)

        def mount_check(_repository, _descriptor, path: Path) -> bool:
            return path != target

        with (
            patch.object(
                acquisition,
                "same_held_mount",
                side_effect=mount_check,
                create=True,
            ) as checked,
            patch.object(acquisition.os, "scandir", side_effect=reject_target_scan),
            self.assertRaises(acquisition.AcquisitionError),
        ):
            acquisition.build_inventory(self.root)
        checked.assert_called()

    def test_linux_mount_identity_rejects_file_before_read_or_hash(self) -> None:
        target = self.root / "artifacts/uv-cache/payload"
        sha256 = acquisition.hashlib.sha256

        def reject_target_hash(raw: bytes = b"") -> object:
            if raw == target.read_bytes():
                raise AssertionError("mounted file was hashed")
            return sha256(raw)

        def mount_check(_repository, _descriptor, path: Path) -> bool:
            return path != target

        with (
            patch.object(
                acquisition,
                "same_held_mount",
                side_effect=mount_check,
                create=True,
            ) as checked,
            patch.object(
                acquisition.hashlib,
                "sha256",
                side_effect=reject_target_hash,
            ),
            self.assertRaises(acquisition.AcquisitionError),
        ):
            acquisition.build_inventory(self.root)
        checked.assert_called()

    def test_inventory_writer_rejects_artifacts_mount_before_temp_creation(self) -> None:
        value = acquisition.build_inventory(self.root)
        artifacts = self.root / "artifacts"

        def mount_check(_repository, _descriptor, path: Path) -> bool:
            return path != artifacts

        with (
            patch.object(acquisition, "validate_inventory", return_value=value),
            patch.object(
                acquisition,
                "same_held_mount",
                side_effect=mount_check,
                create=True,
            ) as checked,
            self.assertRaises(acquisition.AcquisitionError),
        ):
            acquisition.write_inventory(self.root, value)
        checked.assert_called()
        self.assertFalse(self._scratch())
        self.assertFalse(self._scratch())

    def test_writer_checks_existing_destination_mount_before_creating_temp(self) -> None:
        value = acquisition.build_inventory(self.root)
        acquisition.write_inventory(self.root, value)
        destination = self.root / acquisition.INVENTORY_PATH
        real_open = os.open

        def reject_temp_open(path, *args, **kwargs):
            if isinstance(path, str) and path.endswith(".tmp"):
                raise AssertionError("temporary created before destination mount check")
            return real_open(path, *args, **kwargs)

        def mount_check(_repository, _descriptor, path: Path) -> bool:
            return path != destination

        with (
            patch.object(acquisition, "same_held_mount", side_effect=mount_check),
            patch.object(acquisition.os, "open", side_effect=reject_temp_open),
            self.assertRaises(acquisition.AcquisitionError),
        ):
            acquisition.write_inventory(self.root, value)
        self.assertTrue(destination.is_file())
        self.assertFalse(self._scratch())

    def test_writer_rechecks_temporary_mount_before_replace(self) -> None:
        value = acquisition.build_inventory(self.root)
        temp_checks = 0

        def mount_check(_repository, _descriptor, path: Path) -> bool:
            nonlocal temp_checks
            if path.name.endswith(".tmp"):
                temp_checks += 1
                return temp_checks == 1
            return True

        with (
            patch.object(acquisition, "same_held_mount", side_effect=mount_check),
            patch.object(
                acquisition.os,
                "replace",
                side_effect=AssertionError("replace preceded temp mount recheck"),
            ) as replace,
            self.assertRaises(acquisition.AcquisitionError),
        ):
            acquisition.write_inventory(self.root, value)
        self.assertGreaterEqual(temp_checks, 2)
        replace.assert_not_called()
        self.assertFalse((self.root / acquisition.INVENTORY_PATH).exists())
        self.assertEqual(1, len(self._scratch()))

    def test_writer_checks_published_mount_before_read(self) -> None:
        value = acquisition.build_inventory(self.root)
        destination = self.root / acquisition.INVENTORY_PATH
        reads = 0
        read_descriptor = acquisition._read_regular_descriptor

        def observe_read(descriptor: int, maximum: int):
            nonlocal reads
            reads += 1
            if reads > 1:
                raise AssertionError("published inventory read before mount check")
            return read_descriptor(descriptor, maximum)

        def mount_check(_repository, _descriptor, path: Path) -> bool:
            return path != destination

        with (
            patch.object(acquisition, "validate_inventory", return_value=value),
            patch.object(acquisition, "same_held_mount", side_effect=mount_check),
            patch.object(
                acquisition,
                "_read_regular_descriptor",
                side_effect=observe_read,
            ),
            self.assertRaisesRegex(
                acquisition.AcquisitionError, "inventory rollback failed"
            ),
        ):
            acquisition.write_inventory(self.root, value)
        self.assertEqual(1, reads)
        self.assertTrue(destination.exists())

    def test_writer_rechecks_destination_at_final_replace_boundary(self) -> None:
        value = acquisition.build_inventory(self.root)
        acquisition.write_inventory(self.root, value)
        destination = self.root / acquisition.INVENTORY_PATH
        foreign = destination.parent / ".foreign-inventory"
        foreign.write_bytes(b"foreign")
        foreign_identity = (foreign.stat().st_dev, foreign.stat().st_ino)
        open_leaf = acquisition._open_inventory_leaf
        real_replace = os.replace
        temporary_checks = 0

        def swap_after_final_temp_check(*args, **kwargs):
            nonlocal temporary_checks
            descriptor, facts = open_leaf(*args, **kwargs)
            name = args[2]
            if name.endswith(".tmp"):
                temporary_checks += 1
                if temporary_checks == 2:
                    real_replace(foreign, destination)
            return descriptor, facts

        with (
            patch.object(
                acquisition,
                "_open_inventory_leaf",
                side_effect=swap_after_final_temp_check,
            ),
            patch.object(
                acquisition.os,
                "replace",
                side_effect=AssertionError("published after destination exchange"),
            ) as replace,
            self.assertRaisesRegex(
                acquisition.AcquisitionError, "inventory destination changed"
            ),
        ):
            acquisition.write_inventory(self.root, value)
        replace.assert_not_called()
        self.assertEqual(foreign_identity, (destination.stat().st_dev, destination.stat().st_ino))
        self.assertFalse(self._scratch())

    def test_rollback_never_restores_an_in_place_mutated_backup(self) -> None:
        prior = acquisition.build_inventory(self.root)
        acquisition.write_inventory(self.root, prior)
        self.payload.write_bytes(b"new acquisition state")
        current = acquisition.build_inventory(self.root)
        current_raw = encode_canonical_value(current)
        destination = self.root / acquisition.INVENTORY_PATH
        fsync = os.fsync
        mutated = False

        def mutate_backup_then_fail(descriptor: int) -> None:
            nonlocal mutated
            if stat.S_ISDIR(os.fstat(descriptor).st_mode) and not mutated:
                backups = list(destination.parent.glob(f".{destination.name}.*.bak"))
                self.assertEqual(1, len(backups))
                backups[0].write_bytes(b"mutated prior inventory")
                mutated = True
                raise OSError("injected publication failure")
            fsync(descriptor)

        with (
            patch.object(acquisition.os, "fsync", side_effect=mutate_backup_then_fail),
            self.assertRaisesRegex(
                acquisition.AcquisitionError, "inventory rollback failed"
            ),
        ):
            acquisition.write_inventory(self.root, current)
        self.assertTrue(mutated)
        self.assertEqual(current_raw, destination.read_bytes())
        self.assertEqual(1, len(self._scratch()))


if __name__ == "__main__":
    unittest.main()
