from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tomllib


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_SOURCE_LOCK_BYTES = 4 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024


class SafeFileError(ValueError):
    pass


class SourceLockError(ValueError):
    pass


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
        for component in relative.parts[:-1]:
            try:
                directory = os.open(component, directory_flags, dir_fd=directory)
            except OSError as error:
                raise SafeFileError("safe_file.path") from error
            descriptors.append(directory)
        try:
            descriptor = os.open(relative.name, file_flags, dir_fd=directory)
        except OSError as error:
            raise SafeFileError("safe_file.path") from error
        descriptors.append(descriptor)
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
    anthology_value = AnthologyLock(
        path=_relative(anthology["path"]),
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
        or not mounts
        or not all(isinstance(item, str) and item for item in mounts)
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
        or len(set(clean_value.mounts)) != len(clean_value.mounts)
    ):
        raise SourceLockError("source_lock.clean_linux")

    return SourceLock(
        schema_version=0,
        anthology=anthology_value,
        toolchains=toolchain_value,
        references=references,
        clean_linux=clean_value,
    )
