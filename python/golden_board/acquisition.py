from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import tomllib
from typing import cast

from golden_board.manifest import decode_canonical_manifest, encode_canonical_value
from golden_board.source_lock import (
    SafeFileError,
    held_mount_identity,
    read_regular_below,
    resolve_same_mount_path,
    same_held_mount,
)


class AcquisitionError(ValueError):
    pass


INVENTORY_PATH = PurePosixPath("artifacts/acquisition-inventory.json")
INVENTORY_ROOTS = (
    PurePosixPath("artifacts/cargo-home"),
    PurePosixPath("artifacts/uv-cache"),
    PurePosixPath("artifacts/uv-python"),
)
MAX_FILES = 50_000
MAX_ENTRIES = 100_000
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
MAX_INVENTORY_BYTES = 16 * 1024 * 1024
MAX_RELATIVE_PATH_BYTES = 4096
MAX_RELATIVE_PATH_DEPTH = 64


def _error(message: str = "invalid acquisition inventory") -> AcquisitionError:
    return AcquisitionError(message)


def _stat_identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _stat_facts(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _require_bounded_relative_path(relative: PurePosixPath) -> None:
    if (
        len(relative.parts) > MAX_RELATIVE_PATH_DEPTH
        or len(os.fsencode(relative.as_posix())) > MAX_RELATIVE_PATH_BYTES
    ):
        raise _error("acquisition path cap exceeded")


def _valid_link_target(target: str) -> bool:
    return bool(target) and "\0" not in target and len(os.fsencode(target)) <= 4096


def _contained_python_link(root: Path, link: PurePosixPath) -> bool:
    try:
        resolve_same_mount_path(
            root,
            link,
            boundary=PurePosixPath("artifacts/uv-python"),
            max_symlinks=32,
        )
    except SafeFileError:
        return False
    return True


def _open_directory_below(
    root: Path,
    relative: PurePosixPath,
    repository: int,
    repository_stat: os.stat_result,
    repository_mount: tuple[int, bytes | None],
) -> int:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.dup(repository)
    try:
        root_path = os.stat(root, follow_symlinks=False)
        if (
            not stat.S_ISDIR(root_path.st_mode)
            or _stat_identity(root_path) != _stat_identity(repository_stat)
        ):
            raise _error("acquisition repository identity changed")
        current = PurePosixPath()
        for part in relative.parts:
            current /= part
            child: int | None = None
            try:
                entry = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
                child = os.open(part, flags, dir_fd=descriptor)
                held = os.fstat(child)
                path = root / current.as_posix()
                path_stat = os.stat(path, follow_symlinks=False)
                entry_after = os.stat(
                    part, dir_fd=descriptor, follow_symlinks=False
                )
                if (
                    not same_held_mount(repository_mount, child, path)
                    or not all(
                        stat.S_ISDIR(value.st_mode)
                        for value in (entry, held, path_stat, entry_after)
                    )
                    or any(
                        value.st_dev != repository_stat.st_dev
                        for value in (entry, held, path_stat, entry_after)
                    )
                    or any(
                        _stat_identity(value) != _stat_identity(held)
                        for value in (entry, path_stat, entry_after)
                    )
                ):
                    raise _error(f"unsafe acquisition directory: {current}")
            except BaseException:
                if child is not None:
                    os.close(child)
                raise
            os.close(descriptor)
            descriptor = cast(int, child)
    except AcquisitionError:
        os.close(descriptor)
        raise
    except OSError as error:
        os.close(descriptor)
        raise _error(f"unsafe acquisition directory: {relative}") from error
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _inventory_paths(
    root: Path,
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    records: list[dict[str, object]] = []
    links: list[dict[str, str]] = []
    entry_count = 0
    total = 0
    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    repository = os.open(root, directory_flags)
    try:
        repository_stat = os.fstat(repository)
        repository_mount = held_mount_identity(repository)
        root_path = os.stat(root, follow_symlinks=False)
        if (
            not stat.S_ISDIR(repository_stat.st_mode)
            or repository_stat.st_dev != root_path.st_dev
            or _stat_identity(repository_stat) != _stat_identity(root_path)
        ):
            raise _error("acquisition repository identity changed")
        for relative_root in INVENTORY_ROOTS:
            pending = [relative_root]
            while pending:
                current = pending.pop()
                descriptor = _open_directory_below(
                    root,
                    current,
                    repository,
                    repository_stat,
                    repository_mount,
                )
                try:
                    children: list[str] = []
                    with os.scandir(descriptor) as iterator:
                        for child in iterator:
                            entry_count += 1
                            if entry_count > MAX_ENTRIES:
                                raise _error("acquisition entry-count cap exceeded")
                            children.append(child.name)
                    children.sort(key=os.fsencode)
                    for name in children:
                        relative = current / name
                        _require_bounded_relative_path(relative)
                        try:
                            before = os.stat(
                                name, dir_fd=descriptor, follow_symlinks=False
                            )
                            path_before = os.stat(
                                root / relative.as_posix(), follow_symlinks=False
                            )
                        except OSError as error:
                            raise _error("acquisition entry changed") from error
                        if (
                            before.st_dev != repository_stat.st_dev
                            or _stat_identity(path_before) != _stat_identity(before)
                        ):
                            raise _error(f"unsafe acquisition entry: {relative}")
                        mode = before.st_mode
                        if stat.S_ISLNK(mode):
                            if relative_root != PurePosixPath("artifacts/uv-python"):
                                raise _error(f"unsafe acquisition symlink: {relative}")
                            try:
                                target = os.readlink(name, dir_fd=descriptor)
                            except OSError as error:
                                raise _error("acquisition link changed") from error
                            link_path = root / relative.as_posix()
                            if (
                                not _valid_link_target(target)
                                or not _contained_python_link(root, relative)
                            ):
                                raise _error(f"unsafe acquisition symlink: {relative}")
                            try:
                                after = os.stat(
                                    name,
                                    dir_fd=descriptor,
                                    follow_symlinks=False,
                                )
                                path_after = os.stat(
                                    link_path, follow_symlinks=False
                                )
                                after_target = os.readlink(name, dir_fd=descriptor)
                            except OSError as error:
                                raise _error("acquisition link changed") from error
                            if (
                                after.st_dev != repository_stat.st_dev
                                or _stat_facts(before) != _stat_facts(after)
                                or _stat_identity(path_after) != _stat_identity(after)
                                or target != after_target
                            ):
                                raise _error("acquisition link changed")
                            links.append(
                                {"path": relative.as_posix(), "target": target}
                            )
                            continue
                        if stat.S_ISDIR(mode):
                            pending.append(relative)
                            continue
                        if not stat.S_ISREG(mode):
                            raise _error(f"unsupported acquisition entry: {relative}")
                        entry_path = root / relative.as_posix()
                        entry_mount = os.stat(
                            name, dir_fd=descriptor, follow_symlinks=False
                        )
                        path_mount = os.stat(entry_path, follow_symlinks=False)
                        if (
                            entry_mount.st_dev != repository_stat.st_dev
                            or _stat_facts(before) != _stat_facts(entry_mount)
                            or _stat_identity(path_before)
                            != _stat_identity(entry_mount)
                            or _stat_identity(path_mount)
                            != _stat_identity(entry_mount)
                        ):
                            raise _error(f"unsafe acquisition file: {relative}")
                        file_descriptor = os.open(
                            name,
                            os.O_RDONLY
                            | os.O_CLOEXEC
                            | os.O_NOFOLLOW
                            | os.O_NONBLOCK,
                            dir_fd=descriptor,
                        )
                        try:
                            held = os.fstat(file_descriptor)
                            if (
                                not same_held_mount(
                                    repository_mount,
                                    file_descriptor,
                                    entry_path,
                                )
                                or _stat_identity(held) != _stat_identity(before)
                            ):
                                raise _error(f"unsafe acquisition file: {relative}")
                            raw, after = _read_regular_descriptor(
                                file_descriptor, MAX_FILE_BYTES
                            )
                        finally:
                            os.close(file_descriptor)
                        entry_after = os.stat(
                            name, dir_fd=descriptor, follow_symlinks=False
                        )
                        path_after = os.stat(entry_path, follow_symlinks=False)
                        if (
                            after.st_dev != repository_stat.st_dev
                            or _stat_facts(before) != _stat_facts(after)
                            or _stat_facts(entry_after) != _stat_facts(after)
                            or _stat_identity(path_after) != _stat_identity(after)
                        ):
                            raise _error("acquisition file changed")
                        current_descriptor = os.open(
                            name,
                            os.O_RDONLY
                            | os.O_CLOEXEC
                            | os.O_NOFOLLOW
                            | os.O_NONBLOCK,
                            dir_fd=descriptor,
                        )
                        try:
                            current_held = os.fstat(current_descriptor)
                            if (
                                not same_held_mount(
                                    repository_mount,
                                    current_descriptor,
                                    entry_path,
                                )
                                or _stat_facts(current_held) != _stat_facts(after)
                            ):
                                raise _error("acquisition file changed")
                        finally:
                            os.close(current_descriptor)
                        total += len(raw)
                        if total > MAX_TOTAL_BYTES:
                            raise _error("acquisition byte cap exceeded")
                        if relative == PurePosixPath(
                            "artifacts/cargo-home/.global-cache"
                        ):
                            continue
                        records.append(
                            {
                                "byte_length": len(raw),
                                "path": relative.as_posix(),
                                "sha256": hashlib.sha256(raw).hexdigest(),
                            }
                        )
                        if len(records) > MAX_FILES:
                            raise _error("acquisition file-count cap exceeded")
                finally:
                    os.close(descriptor)
    finally:
        os.close(repository)
    records.sort(key=lambda item: os.fsencode(cast(str, item["path"])))
    links.sort(key=lambda item: os.fsencode(item["path"]))
    paths = [cast(str, item["path"]) for item in records]
    if len(paths) != len(set(paths)):
        raise _error("duplicate acquisition path")
    if len(links) != len({item["path"] for item in links}):
        raise _error("duplicate acquisition link")
    return records, links


def _cargo_checksums(root: Path, records: list[dict[str, object]]) -> None:
    try:
        raw = read_regular_below(root, PurePosixPath("Cargo.lock"), 1 << 20)
        lock = tomllib.loads(raw.decode("utf-8", "strict"))
    except (SafeFileError, UnicodeError, tomllib.TOMLDecodeError, ValueError) as error:
        raise _error("invalid Cargo.lock") from error
    packages = lock.get("package", [])
    if type(packages) is not list:
        raise _error("invalid Cargo.lock packages")
    by_name = {
        cast(str, item["path"]): item
        for item in records
        if cast(str, item["path"]).startswith(
            "artifacts/cargo-home/registry/cache/"
        )
    }
    for package in packages:
        if type(package) is not dict:
            raise _error("invalid Cargo.lock package")
        source = package.get("source")
        if source is None:
            continue
        if type(source) is not str or not source.startswith("registry+"):
            raise _error("Cargo.lock contains a non-registry dependency")
        name = package.get("name")
        version = package.get("version")
        checksum = package.get("checksum")
        if not all(type(value) is str for value in (name, version, checksum)):
            raise _error("Cargo.lock registry package is incomplete")
        suffix = f"/{name}-{version}.crate"
        matches = [record for path, record in by_name.items() if path.endswith(suffix)]
        if not matches or any(record["sha256"] != checksum for record in matches):
            raise _error(f"Cargo archive does not match Cargo.lock: {name} {version}")


def build_inventory(root: Path) -> dict[str, object]:
    if not isinstance(root, Path) or not root.is_absolute():
        raise _error("unsafe repository root")
    try:
        repository = root.resolve(strict=True)
        mode = root.lstat().st_mode
    except OSError as error:
        raise _error("unsafe repository root") from error
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode) or repository != root:
        raise _error("unsafe repository root")
    records, links = _inventory_paths(repository)
    _cargo_checksums(repository, records)
    return {
        "schema_version": 0,
        "roots": [path.as_posix() for path in INVENTORY_ROOTS],
        "files": records,
        "links": links,
    }


def validate_inventory(root: Path, value: object) -> dict[str, object]:
    if type(value) is not dict or set(value) != {
        "files",
        "links",
        "roots",
        "schema_version",
    }:
        raise _error()
    document = cast(dict[str, object], value)
    if type(document["schema_version"]) is not int or document["schema_version"] != 0:
        raise _error()
    expected_roots = [path.as_posix() for path in INVENTORY_ROOTS]
    if (
        document["roots"] != expected_roots
        or type(document["files"]) is not list
        or type(document["links"]) is not list
    ):
        raise _error()
    files = cast(list[object], document["files"])
    links_value = cast(list[object], document["links"])
    if (
        len(files) > MAX_FILES
        or len(links_value) > MAX_ENTRIES
        or len(files) + len(links_value) > MAX_ENTRIES
    ):
        raise _error()
    paths: list[str] = []
    total = 0
    for record in files:
        if type(record) is not dict or set(record) != {"byte_length", "path", "sha256"}:
            raise _error()
        item = cast(dict[str, object], record)
        path = item["path"]
        size = item["byte_length"]
        digest = item["sha256"]
        if (
            type(path) is not str
            or not path
            or "\\" in path
            or "\0" in path
            or PurePosixPath(path).as_posix() != path
            or PurePosixPath(path).is_absolute()
            or any(part in ("", ".", "..") for part in PurePosixPath(path).parts)
            or len(os.fsencode(path)) > MAX_RELATIVE_PATH_BYTES
            or len(PurePosixPath(path).parts) > MAX_RELATIVE_PATH_DEPTH
            or type(size) is not int
            or not 0 <= size <= MAX_FILE_BYTES
            or type(digest) is not str
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise _error()
        if not any(PurePosixPath(path).is_relative_to(root_path) for root_path in INVENTORY_ROOTS):
            raise _error()
        total += size
        if total > MAX_TOTAL_BYTES:
            raise _error()
        paths.append(path)
    if paths != sorted(paths, key=os.fsencode) or len(paths) != len(set(paths)):
        raise _error()
    link_paths: list[str] = []
    for record in links_value:
        if type(record) is not dict or set(record) != {"path", "target"}:
            raise _error()
        item = cast(dict[str, object], record)
        path = item["path"]
        target = item["target"]
        if (
            type(path) is not str
            or not path.startswith("artifacts/uv-python/")
            or PurePosixPath(path).as_posix() != path
            or any(part in ("", ".", "..") for part in PurePosixPath(path).parts)
            or len(os.fsencode(path)) > MAX_RELATIVE_PATH_BYTES
            or len(PurePosixPath(path).parts) > MAX_RELATIVE_PATH_DEPTH
            or type(target) is not str
            or not _valid_link_target(target)
        ):
            raise _error()
        link_paths.append(path)
    if link_paths != sorted(link_paths, key=os.fsencode) or len(link_paths) != len(
        set(link_paths)
    ):
        raise _error()
    expected = build_inventory(root)
    if document != expected:
        raise _error("acquisition inventory is stale")
    return cast(dict[str, object], decode_canonical_manifest(encode_canonical_value(document)))


def _write_all(descriptor: int, raw: bytes) -> None:
    view = memoryview(raw)
    offset = 0
    while offset < len(raw):
        written = os.write(descriptor, view[offset:])
        if written <= 0:
            raise _error("short inventory write")
        offset += written


def _read_regular_descriptor(
    descriptor: int, maximum: int
) -> tuple[bytes, os.stat_result]:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
        raise _error("unsafe inventory file")
    os.lseek(descriptor, 0, os.SEEK_SET)
    data = bytearray()
    while True:
        chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > maximum:
            raise _error("inventory byte cap exceeded")
    after = os.fstat(descriptor)
    if _stat_facts(before) != _stat_facts(after) or len(data) != after.st_size:
        raise _error("inventory file changed")
    return bytes(data), after


def _require_directory_identity(
    root: Path,
    repository: int,
    artifacts: int,
    repository_mount: tuple[int, bytes | None],
) -> None:
    try:
        root_path = os.stat(root, follow_symlinks=False)
        root_descriptor = os.fstat(repository)
        artifacts_path = os.stat(
            "artifacts", dir_fd=repository, follow_symlinks=False
        )
        artifacts_descriptor = os.fstat(artifacts)
    except OSError as error:
        raise _error("acquisition directory identity changed") from error
    if (
        not all(
            stat.S_ISDIR(value.st_mode)
            for value in (
                root_path,
                root_descriptor,
                artifacts_path,
                artifacts_descriptor,
            )
        )
        or _stat_identity(root_path) != _stat_identity(root_descriptor)
        or _stat_identity(artifacts_path) != _stat_identity(artifacts_descriptor)
        or not same_held_mount(
            repository_mount, artifacts, root / "artifacts"
        )
    ):
        raise _error("acquisition directory identity changed")


def _open_inventory_leaf(
    root: Path,
    artifacts: int,
    name: str,
    repository_mount: tuple[int, bytes | None],
    *,
    expected_identity: tuple[int, int] | None = None,
    expected_facts: tuple[int, int, int, int, int, int] | None = None,
    message: str,
) -> tuple[int, os.stat_result]:
    if (
        type(name) is not str
        or not name
        or "/" in name
        or "\0" in name
        or "\\" in name
    ):
        raise _error(message)
    descriptor: int | None = None
    try:
        before = os.stat(name, dir_fd=artifacts, follow_symlinks=False)
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=artifacts,
        )
        held = os.fstat(descriptor)
        after = os.stat(name, dir_fd=artifacts, follow_symlinks=False)
        if (
            not stat.S_ISREG(held.st_mode)
            or _stat_identity(before) != _stat_identity(held)
            or _stat_identity(after) != _stat_identity(held)
            or not same_held_mount(
                repository_mount,
                descriptor,
                root / "artifacts" / name,
            )
            or (
                expected_identity is not None
                and _stat_identity(held) != expected_identity
            )
            or (expected_facts is not None and _stat_facts(held) != expected_facts)
        ):
            raise _error(message)
        return descriptor, held
    except FileNotFoundError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except AcquisitionError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as error:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise _error(message) from error


def write_inventory(root: Path, value: object) -> None:
    document = validate_inventory(root, value)
    raw = encode_canonical_value(document)
    if len(raw) > MAX_INVENTORY_BYTES:
        raise _error("inventory byte cap exceeded")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    repository: int | None = None
    artifacts: int | None = None
    temporary: str | None = None
    descriptor: int | None = None
    backup: str | None = None
    prior_identity: tuple[int, int] | None = None
    prior_facts: tuple[int, int, int, int, int, int] | None = None
    prior_raw: bytes | None = None
    linked_prior_facts: tuple[int, int, int, int, int, int] | None = None
    temporary_identity: tuple[int, int] | None = None
    temporary_facts: tuple[int, int, int, int, int, int] | None = None
    published_identity: tuple[int, int] | None = None
    repository_mount: tuple[int, bytes | None] | None = None
    replaced = False
    try:
        repository = os.open(root, flags)
        repository_mount = held_mount_identity(repository)
        artifacts = os.open("artifacts", flags, dir_fd=repository)
        _require_directory_identity(root, repository, artifacts, repository_mount)
        try:
            prior_descriptor, prior_stat = _open_inventory_leaf(
                root,
                artifacts,
                INVENTORY_PATH.name,
                repository_mount,
                message="unsafe inventory destination",
            )
        except FileNotFoundError:
            prior_descriptor = None
            prior_stat = None
        if prior_descriptor is not None:
            try:
                prior_raw, prior_stable = _read_regular_descriptor(
                    prior_descriptor, MAX_INVENTORY_BYTES
                )
                if _stat_facts(prior_stable) != _stat_facts(prior_stat):
                    raise _error("inventory destination changed")
                prior_identity = _stat_identity(prior_stable)
                prior_facts = _stat_facts(prior_stable)
            finally:
                os.close(prior_descriptor)
        for index in range(64):
            candidate = f".{INVENTORY_PATH.name}.{index}.tmp"
            try:
                descriptor = os.open(
                    candidate,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=artifacts,
                )
            except FileExistsError:
                continue
            temporary = candidate
            break
        if descriptor is None or temporary is None:
            raise _error("no inventory temporary name")
        created = os.fstat(descriptor)
        temporary_identity = _stat_identity(created)
        created_path = os.stat(
            temporary, dir_fd=artifacts, follow_symlinks=False
        )
        if (
            not stat.S_ISREG(created.st_mode)
            or _stat_identity(created_path) != _stat_identity(created)
            or not same_held_mount(
                repository_mount,
                descriptor,
                root / "artifacts" / temporary,
            )
        ):
            raise _error("unsafe inventory temporary")
        _write_all(descriptor, raw)
        os.fsync(descriptor)
        _require_directory_identity(root, repository, artifacts, repository_mount)
        temporary_raw, temporary_stat = _read_regular_descriptor(
            descriptor, MAX_INVENTORY_BYTES
        )
        temporary_facts = _stat_facts(temporary_stat)
        if temporary_raw != raw:
            raise _error("inventory verification failed")
        validate_inventory(root, document)
        _require_directory_identity(root, repository, artifacts, repository_mount)
        temporary_check, _ = _open_inventory_leaf(
            root,
            artifacts,
            temporary,
            repository_mount,
            expected_facts=temporary_facts,
            message="inventory temporary changed",
        )
        os.close(temporary_check)
        if prior_identity is not None:
            previous_descriptor, previous = _open_inventory_leaf(
                root,
                artifacts,
                INVENTORY_PATH.name,
                repository_mount,
                expected_facts=prior_facts,
                message="inventory destination changed",
            )
            os.close(previous_descriptor)
            for index in range(64):
                candidate = f".{INVENTORY_PATH.name}.{index}.bak"
                try:
                    os.link(
                        INVENTORY_PATH.name,
                        candidate,
                        src_dir_fd=artifacts,
                        dst_dir_fd=artifacts,
                        follow_symlinks=False,
                    )
                except FileExistsError:
                    continue
                backup = candidate
                break
            if backup is None:
                raise _error("no inventory backup name")
            backup_descriptor, backup_stat = _open_inventory_leaf(
                root,
                artifacts,
                backup,
                repository_mount,
                expected_identity=prior_identity,
                message="inventory destination changed",
            )
            os.close(backup_descriptor)
            current_descriptor, current = _open_inventory_leaf(
                root,
                artifacts,
                INVENTORY_PATH.name,
                repository_mount,
                expected_identity=prior_identity,
                message="inventory destination changed",
            )
            os.close(current_descriptor)
            if _stat_facts(backup_stat) != _stat_facts(current):
                raise _error("inventory destination changed")
            linked_prior_facts = _stat_facts(current)
        else:
            try:
                unexpected_descriptor, _ = _open_inventory_leaf(
                    root,
                    artifacts,
                    INVENTORY_PATH.name,
                    repository_mount,
                    message="inventory destination changed",
                )
            except FileNotFoundError:
                pass
            else:
                os.close(unexpected_descriptor)
                raise _error("inventory destination changed")
        _require_directory_identity(root, repository, artifacts, repository_mount)
        temporary_check, _ = _open_inventory_leaf(
            root,
            artifacts,
            temporary,
            repository_mount,
            expected_facts=temporary_facts,
            message="inventory temporary changed",
        )
        os.close(temporary_check)
        if prior_identity is not None:
            current_descriptor, _ = _open_inventory_leaf(
                root,
                artifacts,
                INVENTORY_PATH.name,
                repository_mount,
                expected_facts=linked_prior_facts,
                message="inventory destination changed",
            )
            os.close(current_descriptor)
        else:
            try:
                unexpected_descriptor, _ = _open_inventory_leaf(
                    root,
                    artifacts,
                    INVENTORY_PATH.name,
                    repository_mount,
                    message="inventory destination changed",
                )
            except FileNotFoundError:
                pass
            else:
                os.close(unexpected_descriptor)
                raise _error("inventory destination changed")
        os.replace(
            temporary,
            INVENTORY_PATH.name,
            src_dir_fd=artifacts,
            dst_dir_fd=artifacts,
        )
        replaced = True
        temporary = None
        published_identity = _stat_identity(temporary_stat)
        _require_directory_identity(root, repository, artifacts, repository_mount)
        published_descriptor, _ = _open_inventory_leaf(
            root,
            artifacts,
            INVENTORY_PATH.name,
            repository_mount,
            expected_identity=published_identity,
            message="published inventory changed",
        )
        try:
            published_raw, published_stat = _read_regular_descriptor(
                published_descriptor, MAX_INVENTORY_BYTES
            )
        finally:
            os.close(published_descriptor)
        if (
            published_raw != raw
            or _stat_identity(published_stat) != published_identity
        ):
            raise _error("published inventory changed")
        try:
            published_value = decode_canonical_manifest(published_raw)
        except ValueError as error:
            raise _error("published inventory is invalid") from error
        if validate_inventory(root, published_value) != document:
            raise _error("inventory changed during publication")
        _require_directory_identity(root, repository, artifacts, repository_mount)
        os.fsync(artifacts)
        _require_directory_identity(root, repository, artifacts, repository_mount)
        if backup is not None:
            backup_descriptor, _ = _open_inventory_leaf(
                root,
                artifacts,
                backup,
                repository_mount,
                expected_identity=prior_identity,
                message="inventory backup changed",
            )
            os.close(backup_descriptor)
            os.unlink(backup, dir_fd=artifacts)
            backup = None
            # Publication is already durable. This sync only makes removal of the
            # non-authoritative recovery link durable; it cannot invalidate evidence.
            try:
                os.fsync(artifacts)
            except OSError:
                pass
        replaced = False
    except BaseException as error:
        rollback_error: BaseException | None = None
        if (
            replaced
            and repository is not None
            and artifacts is not None
            and repository_mount is not None
            and published_identity is not None
        ):
            try:
                _require_directory_identity(
                    root, repository, artifacts, repository_mount
                )
                if prior_identity is not None:
                    if backup is None:
                        raise _error("inventory backup unavailable")
                    backup_descriptor, _ = _open_inventory_leaf(
                        root,
                        artifacts,
                        backup,
                        repository_mount,
                        expected_identity=prior_identity,
                        message="inventory backup changed",
                    )
                    try:
                        backup_raw, _ = _read_regular_descriptor(
                            backup_descriptor, MAX_INVENTORY_BYTES
                        )
                    finally:
                        os.close(backup_descriptor)
                    if prior_raw is None or backup_raw != prior_raw:
                        raise _error("inventory backup changed")
                    try:
                        current_descriptor, _ = _open_inventory_leaf(
                            root,
                            artifacts,
                            INVENTORY_PATH.name,
                            repository_mount,
                            expected_identity=published_identity,
                            message="inventory rollback target changed",
                        )
                    except FileNotFoundError as missing:
                        raise _error("inventory rollback target changed") from missing
                    os.close(current_descriptor)
                    os.replace(
                        backup,
                        INVENTORY_PATH.name,
                        src_dir_fd=artifacts,
                        dst_dir_fd=artifacts,
                    )
                    backup = None
                    restored_descriptor, _ = _open_inventory_leaf(
                        root,
                        artifacts,
                        INVENTORY_PATH.name,
                        repository_mount,
                        expected_identity=prior_identity,
                        message="inventory rollback changed",
                    )
                    try:
                        restored_raw, _ = _read_regular_descriptor(
                            restored_descriptor, MAX_INVENTORY_BYTES
                        )
                    finally:
                        os.close(restored_descriptor)
                    if restored_raw != prior_raw:
                        raise _error("inventory rollback changed")
                else:
                    try:
                        current_descriptor, _ = _open_inventory_leaf(
                            root,
                            artifacts,
                            INVENTORY_PATH.name,
                            repository_mount,
                            expected_identity=published_identity,
                            message="inventory rollback target changed",
                        )
                    except FileNotFoundError:
                        current_descriptor = None
                    if current_descriptor is not None:
                        os.close(current_descriptor)
                        os.unlink(INVENTORY_PATH.name, dir_fd=artifacts)
                os.fsync(artifacts)
                replaced = False
            except BaseException as rollback:
                rollback_error = rollback
        if rollback_error is not None:
            raise _error("inventory rollback failed") from rollback_error
        if isinstance(error, AcquisitionError):
            raise
        if isinstance(error, (OSError, SafeFileError, ValueError)):
            raise _error("inventory publication failed") from error
        raise
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary is not None and artifacts is not None:
            try:
                if repository_mount is None or temporary_identity is None:
                    raise _error("inventory temporary cleanup is unsafe")
                cleanup_descriptor, _ = _open_inventory_leaf(
                    root,
                    artifacts,
                    temporary,
                    repository_mount,
                    expected_identity=temporary_identity,
                    message="inventory temporary cleanup is unsafe",
                )
                os.close(cleanup_descriptor)
                os.unlink(temporary, dir_fd=artifacts)
            except (OSError, AcquisitionError):
                pass
        if backup is not None and artifacts is not None and not replaced:
            try:
                if repository_mount is None or prior_identity is None:
                    raise _error("inventory backup cleanup is unsafe")
                cleanup_descriptor, _ = _open_inventory_leaf(
                    root,
                    artifacts,
                    backup,
                    repository_mount,
                    expected_identity=prior_identity,
                    message="inventory backup cleanup is unsafe",
                )
                os.close(cleanup_descriptor)
                os.unlink(backup, dir_fd=artifacts)
            except (OSError, AcquisitionError):
                pass
        for opened in (artifacts, repository):
            if opened is not None:
                try:
                    os.close(opened)
                except OSError:
                    pass


def load_inventory(root: Path) -> dict[str, object]:
    try:
        raw = read_regular_below(root, INVENTORY_PATH, MAX_INVENTORY_BYTES)
        value = decode_canonical_manifest(raw)
    except (SafeFileError, ValueError) as error:
        raise _error("inventory unavailable") from error
    return validate_inventory(root, value)
