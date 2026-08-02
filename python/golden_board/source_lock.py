from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tomllib


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_SOURCE_LOCK_BYTES = 4 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
FDINFO_MAX_BYTES = 4096
SAFE_LINK_PATH_BYTES = 4096
SAFE_LINK_DEPTH = 64


class SafeFileError(ValueError):
    pass


class SourceLockError(ValueError):
    pass


def _descriptor_identity(value: os.stat_result) -> tuple[int, int, int]:
    return value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode)


def _parse_mount_id(raw: bytes) -> bytes:
    if (
        type(raw) is not bytes
        or not raw.endswith(b"\n")
        or len(raw) > FDINFO_MAX_BYTES
    ):
        raise OSError("mount identity syntax")
    matches = [
        line.removeprefix(b"mnt_id:\t")
        for line in raw.splitlines()
        if line.startswith(b"mnt_id:")
    ]
    if len(matches) != 1 or re.fullmatch(rb"[1-9][0-9]{0,19}", matches[0]) is None:
        raise OSError("mount identity syntax")
    return matches[0]


def _linux_mount_id(descriptor: int) -> bytes:
    required = ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK")
    if (
        type(descriptor) is not int
        or descriptor < 0
        or any(type(getattr(os, name, None)) is not int for name in required)
    ):
        raise OSError("mount identity capability")
    before = os.fstat(descriptor)
    fdinfo: int | None = None
    failure: OSError | None = None
    raw = bytearray()
    try:
        fdinfo = os.open(
            f"/proc/self/fdinfo/{descriptor}",
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
        )
        while len(raw) <= FDINFO_MAX_BYTES:
            chunk = os.read(fdinfo, min(1024, FDINFO_MAX_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) > FDINFO_MAX_BYTES:
            raise OSError("mount identity limit")
    except OSError as error:
        failure = error
    finally:
        if fdinfo is not None:
            try:
                os.close(fdinfo)
            except OSError as error:
                if failure is None:
                    failure = error
    if failure is not None:
        raise failure
    after = os.fstat(descriptor)
    if _descriptor_identity(before) != _descriptor_identity(after):
        raise OSError("mount identity changed")
    return _parse_mount_id(bytes(raw))


def held_mount_identity(descriptor: int) -> tuple[int, bytes | None]:
    before = os.fstat(descriptor)
    if sys.platform == "linux":
        mount_id: bytes | None = _linux_mount_id(descriptor)
    elif sys.platform == "darwin":
        mount_id = None
    else:
        raise OSError("unsupported mount identity platform")
    after = os.fstat(descriptor)
    if _descriptor_identity(before) != _descriptor_identity(after):
        raise OSError("mount identity changed")
    return before.st_dev, mount_id


def same_held_mount(
    repository: int | tuple[int, bytes | None],
    descendant_descriptor: int,
    descendant_path: Path,
) -> bool:
    try:
        if not isinstance(descendant_path, Path):
            return False
        if type(repository) is int:
            repository_identity = held_mount_identity(repository)
        elif (
            type(repository) is tuple
            and len(repository) == 2
            and type(repository[0]) is int
            and (repository[1] is None or type(repository[1]) is bytes)
        ):
            repository_identity = repository
        else:
            return False
        descendant_before = os.fstat(descendant_descriptor)
        if repository_identity[0] != descendant_before.st_dev:
            return False
        if sys.platform == "linux":
            same = repository_identity[1] == _linux_mount_id(descendant_descriptor)
        elif sys.platform == "darwin":
            same = repository_identity[1] is None and not os.path.ismount(
                descendant_path
            )
        else:
            return False
        descendant_after = os.fstat(descendant_descriptor)
        return bool(
            same
            and _descriptor_identity(descendant_before)
            == _descriptor_identity(descendant_after)
        )
    except (OSError, TypeError, ValueError):
        return False


def resolve_same_mount_path(
    root: Path,
    relative: PurePosixPath,
    *,
    boundary: PurePosixPath,
    max_symlinks: int,
    source_boundary: PurePosixPath | None = None,
) -> PurePosixPath:
    def valid_relative(value: object) -> bool:
        return bool(
            isinstance(value, PurePosixPath)
            and not value.is_absolute()
            and value.parts
            and not any(part in ("", ".", "..") for part in value.parts)
            and not any(
                character in value.as_posix() for character in ("\0", "\\")
            )
            and len(value.parts) <= SAFE_LINK_DEPTH
            and len(os.fsencode(value.as_posix())) <= SAFE_LINK_PATH_BYTES
        )

    if (
        not isinstance(root, Path)
        or not root.is_absolute()
        or not valid_relative(relative)
        or not valid_relative(boundary)
        or (
            source_boundary is not None
            and not valid_relative(source_boundary)
        )
        or not (
            relative.is_relative_to(boundary)
            or (
                source_boundary is not None
                and relative.is_relative_to(source_boundary)
            )
        )
        or type(max_symlinks) is not int
        or max_symlinks < 0
    ):
        raise SafeFileError("safe_link.path")
    required = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
    if any(type(getattr(os, name, None)) is not int for name in required):
        raise SafeFileError("safe_link.capability")
    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    repository: int | None = None
    failure: BaseException | None = None

    def close_all(descriptors: list[int]) -> OSError | None:
        close_error: OSError | None = None
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError as error:
                if close_error is None:
                    close_error = error
        return close_error

    def normalize_target(parent: list[str], target: str) -> list[str]:
        if (
            type(target) is not str
            or not target
            or "\0" in target
            or "\\" in target
            or len(os.fsencode(target)) > SAFE_LINK_PATH_BYTES
        ):
            raise SafeFileError("safe_link.escape")
        target_path = PurePosixPath(target)
        parent_path = PurePosixPath(*parent)
        active_boundary = (
            boundary
            if parent_path.is_relative_to(boundary)
            else source_boundary
        )
        if active_boundary is None:
            raise SafeFileError("safe_link.escape")
        if target_path.is_absolute():
            try:
                target_parts = list(
                    target_path.relative_to(PurePosixPath(root.as_posix())).parts
                )
            except ValueError as error:
                raise SafeFileError("safe_link.escape") from error
            normalized: list[str] = []
            allow_leading_parents = False
        else:
            target_parts = list(target_path.parts)
            normalized = list(parent)
            allow_leading_parents = True
        target_component_seen = False
        for part in target_parts:
            if part in ("", "."):
                continue
            if part == "..":
                if (
                    not allow_leading_parents
                    or target_component_seen
                    or not normalized
                ):
                    raise SafeFileError("safe_link.escape")
                normalized.pop()
                continue
            if "\0" in part or "\\" in part:
                raise SafeFileError("safe_link.escape")
            normalized.append(part)
            target_component_seen = True
        result = PurePosixPath(*normalized)
        if (
            not (
                result.is_relative_to(boundary)
                or (
                    source_boundary is not None
                    and result.is_relative_to(source_boundary)
                )
            )
            or len(result.parts) > SAFE_LINK_DEPTH
            or len(os.fsencode(result.as_posix())) > SAFE_LINK_PATH_BYTES
        ):
            raise SafeFileError("safe_link.escape")
        return list(result.parts)

    try:
        repository = os.open(root, directory_flags)
        repository_stat = os.fstat(repository)
        root_stat = os.stat(root, follow_symlinks=False)
        if (
            not stat.S_ISDIR(repository_stat.st_mode)
            or _descriptor_identity(repository_stat)
            != _descriptor_identity(root_stat)
        ):
            raise SafeFileError("safe_link.root")
        repository_mount = held_mount_identity(repository)

        def open_parent(parts: list[str]) -> int:
            assert repository is not None
            opened: list[int] = []
            parent = repository
            current = root
            try:
                for part in parts:
                    before = os.stat(
                        part, dir_fd=parent, follow_symlinks=False
                    )
                    child = os.open(part, directory_flags, dir_fd=parent)
                    opened.append(child)
                    held = os.fstat(child)
                    after = os.stat(
                        part, dir_fd=parent, follow_symlinks=False
                    )
                    current /= part
                    if (
                        not stat.S_ISDIR(held.st_mode)
                        or _descriptor_identity(before)
                        != _descriptor_identity(held)
                        or _descriptor_identity(after)
                        != _descriptor_identity(held)
                        or not same_held_mount(
                            repository_mount, child, current
                        )
                    ):
                        raise SafeFileError("safe_link.mount")
                    parent = child
            except BaseException:
                close_all(opened)
                raise
            result = opened.pop() if opened else os.dup(repository)
            close_error = close_all(opened)
            if close_error is not None:
                close_all([result])
                raise SafeFileError("safe_link.changed") from close_error
            return result

        pending = list(relative.parts)
        resolved: list[str] = []
        symlinks = 0
        while pending:
            name = pending.pop(0)
            parent = open_parent(resolved)
            parent_failure: BaseException | None = None
            redirected = False
            try:
                before = os.stat(name, dir_fd=parent, follow_symlinks=False)
                path = root / PurePosixPath(*resolved, name).as_posix()
                if stat.S_ISLNK(before.st_mode):
                    if before.st_dev != repository_stat.st_dev:
                        raise SafeFileError("safe_link.mount")
                    target = os.readlink(name, dir_fd=parent)
                    after = os.stat(
                        name, dir_fd=parent, follow_symlinks=False
                    )
                    if (
                        _descriptor_identity(before)
                        != _descriptor_identity(after)
                        or target != os.readlink(name, dir_fd=parent)
                    ):
                        raise SafeFileError("safe_link.changed")
                    symlinks += 1
                    if symlinks > max_symlinks:
                        raise SafeFileError("safe_link.limit")
                    pending = [*normalize_target(resolved, target), *pending]
                    resolved = []
                    if (
                        len(pending) > SAFE_LINK_DEPTH
                        or len(
                            os.fsencode(PurePosixPath(*pending).as_posix())
                        )
                        > SAFE_LINK_PATH_BYTES
                    ):
                        raise SafeFileError("safe_link.escape")
                    redirected = True
                else:
                    flags = (
                        directory_flags if stat.S_ISDIR(before.st_mode) else file_flags
                    )
                    if not (
                        stat.S_ISDIR(before.st_mode)
                        or stat.S_ISREG(before.st_mode)
                    ):
                        raise SafeFileError("safe_link.type")
                    child = os.open(name, flags, dir_fd=parent)
                    try:
                        held = os.fstat(child)
                        after = os.stat(
                            name, dir_fd=parent, follow_symlinks=False
                        )
                        if (
                            _descriptor_identity(before)
                            != _descriptor_identity(held)
                            or _descriptor_identity(after)
                            != _descriptor_identity(held)
                            or not same_held_mount(repository_mount, child, path)
                        ):
                            raise SafeFileError("safe_link.mount")
                    finally:
                        os.close(child)
                    resolved.append(name)
                    if pending and not stat.S_ISDIR(before.st_mode):
                        raise SafeFileError("safe_link.type")
            except BaseException as error:
                parent_failure = error
            finally:
                try:
                    os.close(parent)
                except OSError as error:
                    if parent_failure is None:
                        parent_failure = SafeFileError("safe_link.changed")
                        parent_failure.__cause__ = error
            if parent_failure is not None:
                raise parent_failure
            if redirected:
                continue
        result = PurePosixPath(*resolved)
        if not result.is_relative_to(boundary):
            raise SafeFileError("safe_link.escape")
        return result
    except SafeFileError as error:
        failure = error
    except (OSError, TypeError, ValueError) as error:
        failure = SafeFileError("safe_link.changed")
        failure.__cause__ = error
    finally:
        if repository is not None:
            try:
                os.close(repository)
            except OSError as error:
                if failure is None:
                    failure = SafeFileError("safe_link.changed")
                    failure.__cause__ = error
    if failure is not None:
        raise failure
    raise SafeFileError("safe_link.changed")


def read_regular_below(
    root: Path,
    relative: PurePosixPath,
    max_bytes: int,
) -> bytes:
    if (
        not isinstance(relative, PurePosixPath)
        or any(character in relative.as_posix() for character in ("\0", "\\"))
        or relative.is_absolute()
        or not relative.parts
        or any(part in ("", ".", "..") for part in relative.parts)
        or type(max_bytes) is not int
        or max_bytes < 0
    ):
        raise SafeFileError("safe_file.path")
    required = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
    if any(type(getattr(os, name, None)) is not int for name in required):
        raise SafeFileError("safe_file.capability")
    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptors: list[int] = []
    failure: SafeFileError | None = None
    data = bytearray()
    try:
        try:
            directory = os.open(root, directory_flags)
        except OSError as error:
            raise SafeFileError("safe_file.root") from error
        descriptors.append(directory)
        repository = directory
        try:
            repository_mount = held_mount_identity(repository)
        except OSError as error:
            raise SafeFileError("safe_file.mount") from error
        current = root
        for component in relative.parts[:-1]:
            try:
                directory = os.open(component, directory_flags, dir_fd=directory)
            except OSError as error:
                raise SafeFileError("safe_file.path") from error
            descriptors.append(directory)
            current /= component
            if not same_held_mount(repository_mount, directory, current):
                raise SafeFileError("safe_file.mount")
        try:
            descriptor = os.open(relative.name, file_flags, dir_fd=directory)
        except OSError as error:
            raise SafeFileError("safe_file.path") from error
        descriptors.append(descriptor)
        if not same_held_mount(
            repository_mount, descriptor, current / relative.name
        ):
            raise SafeFileError("safe_file.mount")
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise SafeFileError("safe_file.type")
        if before.st_size > max_bytes:
            raise SafeFileError("safe_file.limit")
        while True:
            chunk = os.read(
                descriptor,
                min(READ_CHUNK_BYTES, max_bytes + 1 - len(data)),
            )
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > max_bytes:
                raise SafeFileError("safe_file.limit")
        after = os.fstat(descriptor)
        before_facts = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_facts = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if before_facts != after_facts or len(data) != after.st_size:
            raise SafeFileError("safe_file.changed")
    except SafeFileError as error:
        failure = error
    except OSError as error:
        failure = SafeFileError("safe_file.changed")
        failure.__cause__ = error
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError as error:
                if failure is None:
                    failure = SafeFileError("safe_file.changed")
                    failure.__cause__ = error
    if failure is not None:
        raise failure
    return bytes(data)


def validate_same_mount_tree(
    root: Path,
    relative: PurePosixPath,
    *,
    max_entries: int,
    max_depth: int,
) -> None:
    if (
        not isinstance(root, Path)
        or not isinstance(relative, PurePosixPath)
        or any(character in relative.as_posix() for character in ("\0", "\\"))
        or relative.is_absolute()
        or not relative.parts
        or any(part in ("", ".", "..") for part in relative.parts)
        or len(os.fsencode(relative.as_posix())) > 4096
        or type(max_entries) is not int
        or max_entries < 1
        or type(max_depth) is not int
        or max_depth < 0
    ):
        raise SafeFileError("safe_tree.path")
    required = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
    if any(type(getattr(os, name, None)) is not int for name in required):
        raise SafeFileError("safe_tree.capability")
    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    repository: int | None = None
    failure: BaseException | None = None
    try:
        repository = os.open(root, directory_flags)
        repository_mount = held_mount_identity(repository)

        def open_directory(path: PurePosixPath) -> int:
            opened: list[int] = []
            descriptor = repository
            current = root
            try:
                for part in path.parts:
                    before = os.stat(
                        part, dir_fd=descriptor, follow_symlinks=False
                    )
                    child = os.open(part, directory_flags, dir_fd=descriptor)
                    opened.append(child)
                    current /= part
                    held = os.fstat(child)
                    after = os.stat(
                        part, dir_fd=descriptor, follow_symlinks=False
                    )
                    if not stat.S_ISDIR(held.st_mode):
                        raise SafeFileError("safe_tree.type")
                    if (
                        _descriptor_identity(before) != _descriptor_identity(held)
                        or _descriptor_identity(after) != _descriptor_identity(held)
                        or not same_held_mount(repository_mount, child, current)
                    ):
                        raise SafeFileError("safe_tree.mount")
                    descriptor = child
            except BaseException:
                for owned in reversed(opened):
                    try:
                        os.close(owned)
                    except OSError:
                        pass
                raise
            result = opened.pop()
            close_error: OSError | None = None
            for owned in reversed(opened):
                try:
                    os.close(owned)
                except OSError as error:
                    if close_error is None:
                        close_error = error
            if close_error is not None:
                try:
                    os.close(result)
                except OSError:
                    pass
                raise SafeFileError("safe_tree.changed") from close_error
            return result

        pending = [relative]
        entries = 0
        while pending:
            current = pending.pop()
            if len(current.parts) - len(relative.parts) > max_depth:
                raise SafeFileError("safe_tree.depth")
            directory = open_directory(current)
            directory_failure: BaseException | None = None
            try:
                with os.scandir(directory) as iterator:
                    names: list[str] = []
                    for entry in iterator:
                        entries += 1
                        if entries > max_entries:
                            raise SafeFileError("safe_tree.limit")
                        name = entry.name
                        if (
                            type(name) is not str
                            or name in ("", ".", "..")
                            or any(character in name for character in ("\0", "\\"))
                        ):
                            raise SafeFileError("safe_tree.path")
                        names.append(name)
                for name in sorted(names, key=os.fsencode):
                    child_path = current / name
                    if (
                        len(os.fsencode(child_path.as_posix())) > 4096
                        or len(child_path.parts) - len(relative.parts) > max_depth
                    ):
                        raise SafeFileError("safe_tree.depth")
                    before = os.stat(
                        name, dir_fd=directory, follow_symlinks=False
                    )
                    if stat.S_ISDIR(before.st_mode):
                        child = os.open(
                            name, directory_flags, dir_fd=directory
                        )
                        try:
                            held = os.fstat(child)
                            after = os.stat(
                                name,
                                dir_fd=directory,
                                follow_symlinks=False,
                            )
                            if (
                                _descriptor_identity(before)
                                != _descriptor_identity(held)
                                or _descriptor_identity(after)
                                != _descriptor_identity(held)
                                or not same_held_mount(
                                    repository_mount,
                                    child,
                                    root / child_path.as_posix(),
                                )
                            ):
                                raise SafeFileError("safe_tree.mount")
                        finally:
                            os.close(child)
                        pending.append(child_path)
                    elif stat.S_ISREG(before.st_mode):
                        child = os.open(name, file_flags, dir_fd=directory)
                        try:
                            held = os.fstat(child)
                            after = os.stat(
                                name,
                                dir_fd=directory,
                                follow_symlinks=False,
                            )
                            if (
                                _descriptor_identity(before)
                                != _descriptor_identity(held)
                                or _descriptor_identity(after)
                                != _descriptor_identity(held)
                                or not same_held_mount(
                                    repository_mount,
                                    child,
                                    root / child_path.as_posix(),
                                )
                            ):
                                raise SafeFileError("safe_tree.mount")
                        finally:
                            os.close(child)
                    else:
                        raise SafeFileError("safe_tree.type")
            except BaseException as error:
                directory_failure = error
            finally:
                try:
                    os.close(directory)
                except OSError as error:
                    if directory_failure is None:
                        directory_failure = SafeFileError("safe_tree.changed")
                        directory_failure.__cause__ = error
            if directory_failure is not None:
                raise directory_failure
    except SafeFileError as error:
        failure = error
    except OSError as error:
        failure = SafeFileError("safe_tree.changed")
        failure.__cause__ = error
    except (TypeError, ValueError) as error:
        failure = SafeFileError("safe_tree.changed")
        failure.__cause__ = error
    finally:
        if repository is not None:
            try:
                os.close(repository)
            except OSError as error:
                if failure is None:
                    failure = SafeFileError("safe_tree.changed")
                    failure.__cause__ = error
    if failure is not None:
        raise failure


@dataclass(frozen=True)
class AnthologyLock:
    path: PurePosixPath
    file_type: str
    byte_length: int
    sha256: str
    encoding: str
    bom: str
    newlines: str
    final_lf: str


@dataclass(frozen=True)
class ToolchainLock:
    python: str
    uv: str
    rust: str
    cargo: str
    git: str
    shell: str
    host: str
    generic_sha256: str
    cc: str
    ld: str
    sdk: str


@dataclass(frozen=True)
class ReferenceLock:
    id: str
    title: str
    authority: str
    edition: str
    locator: str
    role: str
    required_at_m0: bool
    immutable_id: str
    acquired_sha256: str
    local_path: PurePosixPath | None


@dataclass(frozen=True)
class CleanLinuxLock:
    mechanism: str
    image: str
    digest: str
    platform_digest: str
    config_digest: str
    platform: str
    uv_archive: str
    uv_archive_sha256: str
    docker_client: str
    observed_daemon_state: str
    acquisition_protocol: str
    offline_protocol: str
    mounts: Sequence[str]
    state: str
    blocker: str
    deadline: str


@dataclass(frozen=True)
class SourceLock:
    schema_version: int
    anthology: AnthologyLock
    toolchains: ToolchainLock
    references: Sequence[ReferenceLock]
    clean_linux: CleanLinuxLock


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise SourceLockError(f"source_lock.schema: {name}")
    return value


def _keys(value: Mapping[str, object], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise SourceLockError(f"source_lock.schema: {name}")


def _text(value: object, name: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value):
        raise SourceLockError(f"source_lock.schema: {name}")
    return value


def _sha256(value: object) -> str:
    text = _text(value, "sha256")
    if SHA256.fullmatch(text) is None:
        raise SourceLockError("source_lock.sha256")
    return text


def _relative(value: object, *, optional: bool = False) -> PurePosixPath | None:
    if value is None and optional:
        return None
    text = _text(value, "path")
    path = PurePosixPath(text)
    if (
        any(character in text for character in ("\0", "\\"))
        or path.as_posix() != text
        or path.is_absolute()
        or not path.parts
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise SourceLockError("source_lock.path")
    return path


def _reference(value: object) -> ReferenceLock:
    table = _mapping(value, "reference")
    required = {
        "id",
        "title",
        "authority",
        "edition",
        "locator",
        "role",
        "required_at_m0",
        "immutable_id",
        "acquired_sha256",
    }
    if set(table) not in (required, required | {"local_path"}):
        raise SourceLockError("source_lock.schema: reference")
    required_at_m0 = table["required_at_m0"]
    if not isinstance(required_at_m0, bool):
        raise SourceLockError("source_lock.reference")
    role = _text(table["role"], "reference.role")
    if role not in {"normative", "source-format", "candidate", "design", "background"}:
        raise SourceLockError("source_lock.reference")
    immutable_id = _text(table["immutable_id"], "reference.immutable_id", empty=True)
    acquired_sha256 = _sha256(table["acquired_sha256"])
    if required_at_m0 and not immutable_id:
        raise SourceLockError("source_lock.reference")
    return ReferenceLock(
        id=_text(table["id"], "reference.id"),
        title=_text(table["title"], "reference.title"),
        authority=_text(table["authority"], "reference.authority"),
        edition=_text(table["edition"], "reference.edition"),
        locator=_text(table["locator"], "reference.locator"),
        role=role,
        required_at_m0=required_at_m0,
        immutable_id=immutable_id,
        acquired_sha256=acquired_sha256,
        local_path=_relative(table.get("local_path"), optional=True),
    )


def load_source_lock(root: Path) -> SourceLock:
    try:
        raw = read_regular_below(
            root,
            PurePosixPath("inputs/source-lock.toml"),
            MAX_SOURCE_LOCK_BYTES,
        )
        document = tomllib.loads(raw.decode("utf-8", "strict"))
    except (
        OSError,
        UnicodeError,
        SafeFileError,
        tomllib.TOMLDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise SourceLockError("source_lock.syntax") from error
    _keys(
        document,
        {"schema", "anthology", "toolchains", "references", "clean_linux"},
        "root",
    )

    schema = _mapping(document["schema"], "schema")
    _keys(schema, {"version"}, "schema")
    if type(schema["version"]) is not int or schema["version"] != 0:
        raise SourceLockError("source_lock.schema: version")

    anthology = _mapping(document["anthology"], "anthology")
    anthology_keys = {
        "path",
        "file_type",
        "byte_length",
        "sha256",
        "encoding",
        "bom",
        "newlines",
        "final_lf",
    }
    _keys(anthology, anthology_keys, "anthology")
    byte_length = anthology["byte_length"]
    if type(byte_length) is not int or not 0 < byte_length <= 16_777_216:
        raise SourceLockError("source_lock.schema: anthology.byte_length")
    anthology_path = _relative(anthology["path"])
    if anthology_path != PurePosixPath("docs/64_games.md"):
        raise SourceLockError("source_lock.schema: anthology.path")
    anthology_value = AnthologyLock(
        path=anthology_path,
        file_type=_text(anthology["file_type"], "anthology.file_type"),
        byte_length=byte_length,
        sha256=_sha256(anthology["sha256"]),
        encoding=_text(anthology["encoding"], "anthology.encoding"),
        bom=_text(anthology["bom"], "anthology.bom"),
        newlines=_text(anthology["newlines"], "anthology.newlines"),
        final_lf=_text(anthology["final_lf"], "anthology.final_lf"),
    )
    if (
        anthology_value.file_type != "regular"
        or anthology_value.encoding != "UTF-8"
        or anthology_value.bom != "absent"
        or anthology_value.newlines not in {"LF", "CRLF"}
        or anthology_value.final_lf != "present"
    ):
        raise SourceLockError("source_lock.schema: anthology.profile")

    toolchains = _mapping(document["toolchains"], "toolchains")
    toolchain_keys = {
        "python",
        "uv",
        "rust",
        "cargo",
        "git",
        "shell",
        "host",
        "generic_sha256",
        "cc",
        "ld",
        "sdk",
    }
    _keys(toolchains, toolchain_keys, "toolchains")
    toolchain_value = ToolchainLock(
        **{
            key: _text(toolchains[key], f"toolchains.{key}")
            for key in toolchain_keys
        }
    )

    references_table = _mapping(document["references"], "references")
    _keys(references_table, {"reference"}, "references")
    raw_references = references_table["reference"]
    if not isinstance(raw_references, list) or not raw_references:
        raise SourceLockError("source_lock.reference")
    references = tuple(_reference(value) for value in raw_references)
    if len({value.id for value in references}) != len(references):
        raise SourceLockError("source_lock.reference")

    clean = _mapping(document["clean_linux"], "clean_linux")
    clean_keys = {
        "mechanism",
        "image",
        "digest",
        "platform_digest",
        "config_digest",
        "platform",
        "uv_archive",
        "uv_archive_sha256",
        "docker_client",
        "observed_daemon_state",
        "acquisition_protocol",
        "offline_protocol",
        "mounts",
        "state",
        "blocker",
        "deadline",
    }
    _keys(clean, clean_keys, "clean_linux")
    digest = _text(clean["digest"], "clean_linux.digest")
    platform_digest = _text(
        clean["platform_digest"], "clean_linux.platform_digest"
    )
    config_digest = _text(clean["config_digest"], "clean_linux.config_digest")
    mounts = clean["mounts"]
    if (
        DIGEST.fullmatch(digest) is None
        or DIGEST.fullmatch(platform_digest) is None
        or DIGEST.fullmatch(config_digest) is None
        or not isinstance(mounts, list)
        or mounts != ["checkout", "uv-tool"]
    ):
        raise SourceLockError("source_lock.clean_linux")
    state = _text(clean["state"], "clean_linux.state")
    blocker = _text(clean["blocker"], "clean_linux.blocker", empty=True)
    if state not in {"planned", "verified"} or (state == "planned") != bool(blocker):
        raise SourceLockError("source_lock.clean_linux")
    clean_value = CleanLinuxLock(
        mechanism=_text(clean["mechanism"], "clean_linux.mechanism"),
        image=_text(clean["image"], "clean_linux.image"),
        digest=digest,
        platform_digest=platform_digest,
        config_digest=config_digest,
        platform=_text(clean["platform"], "clean_linux.platform"),
        uv_archive=_text(clean["uv_archive"], "clean_linux.uv_archive"),
        uv_archive_sha256=_sha256(clean["uv_archive_sha256"]),
        docker_client=_text(clean["docker_client"], "clean_linux.docker_client"),
        observed_daemon_state=_text(
            clean["observed_daemon_state"], "clean_linux.observed_daemon_state"
        ),
        acquisition_protocol=_text(
            clean["acquisition_protocol"], "clean_linux.acquisition_protocol"
        ),
        offline_protocol=_text(
            clean["offline_protocol"], "clean_linux.offline_protocol"
        ),
        mounts=tuple(mounts),
        state=state,
        blocker=blocker,
        deadline=_text(clean["deadline"], "clean_linux.deadline"),
    )
    if (
        clean_value.mechanism != "docker"
        or clean_value.platform != "linux/arm64/v8"
        or clean_value.acquisition_protocol != "docker-acquire-v0"
        or clean_value.offline_protocol != "docker-offline-v0"
        or clean_value.deadline != "M2"
    ):
        raise SourceLockError("source_lock.clean_linux")

    return SourceLock(
        schema_version=0,
        anthology=anthology_value,
        toolchains=toolchain_value,
        references=references,
        clean_linux=clean_value,
    )
