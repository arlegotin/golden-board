from dataclasses import dataclass
from hashlib import sha256
from http.client import HTTPException
import json
import os
from pathlib import Path, PurePosixPath
import signal
import stat
from urllib.request import ProxyHandler, Request, build_opener

from golden_board.source_lock import DIGEST, held_mount_identity, same_held_mount


ROOT = Path(__file__).resolve().parents[2]
DESTINATION = ROOT / "artifacts/reference-acquisition"
FIPS_SNAPSHOT = ROOT / "inputs/references/fips-180-4.pdf"
USER_AGENT = "Golden-Board-M0/0 urllib"
CSL_JSON = "application/vnd.citationstyles.csl+json"
OCI_INDEX = "application/vnd.oci.image.index.v1+json"
DOCKER_INDEX = "application/vnd.docker.distribution.manifest.list.v2+json"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
DOCKER_MANIFEST = "application/vnd.docker.distribution.manifest.v2+json"
OCI_CONFIG = "application/vnd.oci.image.config.v1+json"
IMAGE_ENV = (
    "PATH=/usr/local/cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "RUSTUP_HOME=/usr/local/rustup",
    "CARGO_HOME=/usr/local/cargo",
    "RUST_VERSION=1.94.0",
)
NETWORK_DEADLINE_SECONDS = 120.0


def _direct_opener():
    return build_opener(ProxyHandler({}))


_OPENER = _direct_opener()


class AcquisitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Artifact:
    id: str
    filename: str
    url: str
    sha256: str
    byte_length: int
    accept: str = "*/*"


ARTIFACTS = (
    Artifact(
        "fide-laws-2023",
        "fide-laws-2023.html",
        "https://handbook.fide.com/chapter/E012023",
        "e0c8bee28c2dee07b724357b9802fee8591e9d11efd2a910b38e9bd21d3c7643",
        186226,
    ),
    Artifact(
        "fide-handbook-index",
        "fide-handbook-index.html",
        "https://handbook.fide.com/",
        "ad9367f4bbf2c225eeabbc301a0f016710c69fd24c3cd4aac7db34c747ee8eab",
        75659,
    ),
    Artifact(
        "pgn-guide-1994",
        "pgn-complete-1994.html",
        "https://www.saremba.de/chessgml/standards/pgn/pgn-complete.htm",
        "2c2445a8c2118a5603610364f8055b31db388e2f4cbc6bb70815bf38ee45de3f",
        239689,
    ),
    Artifact(
        "fips-180-4",
        "NIST.FIPS.180-4.pdf",
        "https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.180-4.pdf",
        "0455b406d89648d20cbde375561e19c245b9815e894164c2670772e3d54deb82",
        833315,
    ),
    Artifact(
        "nist-sha-byte-kat",
        "shabytetestvectors.zip",
        "https://csrc.nist.gov/CSRC/media/Projects/Cryptographic-Algorithm-Validation-Program/documents/shs/shabytetestvectors.zip",
        "929ef80b7b3418aca026643f6f248815913b60e01741a44bba9e118067f4c9b8",
        4909729,
    ),
    Artifact(
        "rfc-9260",
        "rfc9260.txt",
        "https://www.rfc-editor.org/rfc/rfc9260.txt",
        "04bdd3255e9e5ddf1e401e9d5d726ec2750e5269cb52485db3f7f4fe77500354",
        345864,
    ),
    Artifact(
        "ecma-182",
        "ECMA-182_1st_edition_december_1992.pdf",
        "https://ecma-international.org/wp-content/uploads/ECMA-182_1st_edition_december_1992.pdf",
        "95e5a266a0d96697a05be9b55a141180330dfe94a450b39ffb8b002fbb085366",
        3987114,
    ),
    Artifact(
        "hamming-1950",
        "hamming-1950.csl.json",
        "https://doi.org/10.1002/j.1538-7305.1950.tb00463.x",
        "9c7456e29f9550e7e8eb52855632fecadb56506b06e59d9088d988ef75a75cb3",
        1440,
        CSL_JSON,
    ),
    Artifact(
        "reed-solomon-1960",
        "reed-solomon-1960.csl.json",
        "https://doi.org/10.1137/0108018",
        "86cc4d5ca423a8fe0087446235df29e9a2b273f8488471262a0578a7b999b8c6",
        2093,
        CSL_JSON,
    ),
    Artifact(
        "voyager-cover",
        "voyager-record-cover-446eb9.jpg",
        "https://science.nasa.gov/wp-content/uploads/2024/03/voyager-record-cover-446eb9.jpg",
        "eac79258cc229db4de1234afa4c8d64a158d287f8c6ee59e175535f0e86b5502",
        1427637,
    ),
    Artifact(
        "lincos-1960",
        "lincos-62053679.marcxml",
        "https://lccn.loc.gov/62053679/marcxml",
        "a023757ecf16cf41691959243201903c3a7648401896148436b4e1afd827d56d",
        3208,
    ),
    Artifact(
        "cosmicos-67e80da",
        "cosmicos-67e80da32383bd77ad4427455c9ae982e9c649cf.tar.gz",
        "https://github.com/paulfitz/cosmicos/archive/67e80da32383bd77ad4427455c9ae982e9c649cf.tar.gz",
        "bd1b07ccb09630202e28ba99311b63befee48cfb96390f727e0eb5ae60070b43",
        310352,
    ),
    Artifact(
        "seti-busch-reddick",
        "seti-busch-reddick-0911.3976v3.pdf",
        "https://arxiv.org/pdf/0911.3976v3",
        "0c462605022ee8d9246a42c74046b4760f08d69bdd16189ac85aee57f5f73a5f",
        385791,
    ),
    Artifact(
        "seti-heller",
        "seti-heller-1706.00653v3.pdf",
        "https://arxiv.org/pdf/1706.00653v3",
        "d86d9f4c63e36b70e1992789b58ff57a11e9132238f96fb8c94dc6ecec82b54e",
        2273277,
    ),
    Artifact(
        "reproducible-builds-definition",
        "reproducible-builds-definition-1d7e9a.md",
        "https://salsa.debian.org/reproducible-builds/reproducible-website/-/raw/1d7e9a6138117a37f207aa514b4ef396095ba7ce/_docs/definition.md",
        "f063776583fae80f7b285b8b3a40829ab25f602c25c07e28e914853f10993a66",
        1442,
    ),
    Artifact(
        "uv-linux-arm64-archive",
        "uv-aarch64-unknown-linux-gnu.tar.gz",
        "https://github.com/astral-sh/uv/releases/download/0.11.29/uv-aarch64-unknown-linux-gnu.tar.gz",
        "94500fb064ae3c971a873cba64d94694c50677e0a4dbf78735c80509e7429919",
        24438519,
    ),
    Artifact(
        "uv-linux-arm64-checksum",
        "uv-aarch64-unknown-linux-gnu.tar.gz.sha256",
        "https://github.com/astral-sh/uv/releases/download/0.11.29/uv-aarch64-unknown-linux-gnu.tar.gz.sha256",
        "ea4b3b400502856fae8d8504649e32f9a2faba2f871a235b99c4935cfb2a51cf",
        102,
    ),
)

TOKEN_URL = (
    "https://auth.docker.io/token?service=registry.docker.io"
    "&scope=repository%3Alibrary%2Frust%3Apull"
)
RUST_INDEX = Artifact(
    "rust-1.94.0-bookworm-index",
    "rust-1.94.0-bookworm.index.json",
    "https://registry-1.docker.io/v2/library/rust/manifests/"
    "sha256:365468470075493dc4583f47387001854321c5a8583ea9604b297e67f01c5a4f",
    "365468470075493dc4583f47387001854321c5a8583ea9604b297e67f01c5a4f",
    7752,
    f"{OCI_INDEX}, {DOCKER_INDEX}",
)
RUST_PLATFORM = Artifact(
    "rust-1.94.0-bookworm-linux-arm64",
    "rust-1.94.0-bookworm-linux-arm64.manifest.json",
    "https://registry-1.docker.io/v2/library/rust/manifests/"
    "sha256:94aaa0b45f4d185294474343d9034f829969f6c9ff8101f348b526d105860818",
    "94aaa0b45f4d185294474343d9034f829969f6c9ff8101f348b526d105860818",
    1942,
    f"{OCI_MANIFEST}, {DOCKER_MANIFEST}",
)
RUST_CONFIG = Artifact(
    "rust-1.94.0-bookworm-linux-arm64-config",
    "rust-1.94.0-bookworm-linux-arm64.config.json",
    "https://registry-1.docker.io/v2/library/rust/blobs/"
    "sha256:4019a0c031b04dec0649a4e4af542125d94d2c9467e19ea6fd4d9e53510fd5e9",
    "4019a0c031b04dec0649a4e4af542125d94d2c9467e19ea6fd4d9e53510fd5e9",
    4734,
    OCI_CONFIG,
)


def _get(
    url: str,
    accept: str,
    max_bytes: int,
    authorization: str | None = None,
) -> bytes:
    headers = {"Accept": accept, "User-Agent": USER_AGENT}
    if authorization is not None:
        headers["Authorization"] = authorization
    try:
        active_timer = signal.getitimer(signal.ITIMER_REAL)
    except (AttributeError, OSError, ValueError) as error:
        raise AcquisitionError("network deadline capability is unavailable") from error
    if active_timer != (0.0, 0.0):
        raise AcquisitionError("network deadline is already active")

    def deadline_expired(_signum, _frame):
        raise TimeoutError("network deadline expired")

    previous_handler = None
    failure: AcquisitionError | None = None
    raw: bytes | None = None
    try:
        previous_handler = signal.signal(signal.SIGALRM, deadline_expired)
        signal.setitimer(
            signal.ITIMER_REAL,
            NETWORK_DEADLINE_SECONDS,
        )
        with _OPENER.open(
            Request(url, headers=headers), timeout=NETWORK_DEADLINE_SECONDS
        ) as response:
            raw = response.read(max_bytes + 1)
    except (HTTPException, OSError, ValueError) as error:
        failure = AcquisitionError(f"network: {url}")
        failure.__cause__ = error
    finally:
        if previous_handler is not None:
            cleanup_error: OSError | ValueError | None = None
            try:
                signal.setitimer(signal.ITIMER_REAL, 0.0)
            except (OSError, ValueError) as error:
                cleanup_error = error
            try:
                signal.signal(signal.SIGALRM, previous_handler)
            except (OSError, ValueError) as error:
                if cleanup_error is None:
                    cleanup_error = error
            if failure is None and cleanup_error is not None:
                failure = AcquisitionError("network deadline cleanup failed")
                failure.__cause__ = cleanup_error
    if failure is not None:
        raise failure
    if raw is None:
        raise AcquisitionError(f"network returned no bytes: {url}")
    if len(raw) > max_bytes:
        raise AcquisitionError(f"network response exceeds {max_bytes} bytes: {url}")
    return raw


def verify_bytes(artifact: Artifact, raw: bytes) -> None:
    if len(raw) != artifact.byte_length:
        raise AcquisitionError(
            f"{artifact.id}: byte_length {len(raw)} != {artifact.byte_length}"
        )
    actual = sha256(raw).hexdigest()
    if actual != artifact.sha256:
        raise AcquisitionError(f"{artifact.id}: sha256 {actual} != {artifact.sha256}")


def select_linux_arm64_manifest(raw: bytes) -> tuple[str, int]:
    try:
        document = json.loads(raw)
        manifests = document["manifests"]
    except (
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise AcquisitionError("rust index: invalid JSON") from error
    if not isinstance(manifests, list):
        raise AcquisitionError("rust index: manifests is not a list")
    matches: list[tuple[str, int]] = []
    for descriptor in manifests:
        if not isinstance(descriptor, dict):
            continue
        platform = descriptor.get("platform")
        if (
            isinstance(platform, dict)
            and platform.get("os") == "linux"
            and platform.get("architecture") == "arm64"
            and platform.get("variant") == "v8"
            and descriptor.get("mediaType") in {OCI_MANIFEST, DOCKER_MANIFEST}
            and isinstance(descriptor.get("digest"), str)
            and DIGEST.fullmatch(descriptor["digest"]) is not None
            and type(descriptor.get("size")) is int
            and descriptor["size"] > 0
        ):
            matches.append((descriptor["digest"], descriptor["size"]))
    if len(matches) != 1:
        raise AcquisitionError("rust index: expected unique linux/arm64/v8 manifest")
    return matches[0]


def select_image_config(raw: bytes) -> tuple[str, int]:
    try:
        descriptor = json.loads(raw)["config"]
    except (
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise AcquisitionError("rust manifest: invalid config descriptor") from error
    if (
        not isinstance(descriptor, dict)
        or descriptor.get("mediaType") != OCI_CONFIG
        or not isinstance(descriptor.get("digest"), str)
        or DIGEST.fullmatch(descriptor["digest"]) is None
        or type(descriptor.get("size")) is not int
        or descriptor["size"] <= 0
    ):
        raise AcquisitionError("rust manifest: invalid config descriptor")
    return descriptor["digest"], descriptor["size"]


def validate_image_config(raw: bytes) -> None:
    try:
        document = json.loads(raw)
        config = document["config"]
    except (
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise AcquisitionError("rust config: invalid JSON") from error
    if (
        not isinstance(config, dict)
        or document.get("architecture") != "arm64"
        or document.get("os") != "linux"
        or config.get("Env") != list(IMAGE_ENV)
        or config.get("Entrypoint") is not None
        or config.get("Cmd") != ["bash"]
    ):
        raise AcquisitionError("rust config: unexpected runtime settings")


def _token() -> str:
    raw = _get(TOKEN_URL, "application/json", 65_536)
    try:
        value = json.loads(raw)["token"]
    except (
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise AcquisitionError("docker token: invalid JSON") from error
    if not isinstance(value, str) or not value:
        raise AcquisitionError("docker token: missing token")
    return value


def acquire_all() -> tuple[list[tuple[Artifact, bytes]], bytes, bytes, bytes]:
    downloads = []
    for artifact in ARTIFACTS:
        raw = _get(artifact.url, artifact.accept, artifact.byte_length)
        verify_bytes(artifact, raw)
        downloads.append((artifact, raw))
    by_id = {artifact.id: (artifact, raw) for artifact, raw in downloads}
    archive, _ = by_id["uv-linux-arm64-archive"]
    _, checksum = by_id["uv-linux-arm64-checksum"]
    expected_checksum = f"{archive.sha256}  {archive.filename}\n".encode("ascii")
    if checksum != expected_checksum:
        raise AcquisitionError("uv checksum does not name the pinned archive")

    authorization = f"Bearer {_token()}"
    index = _get(
        RUST_INDEX.url,
        RUST_INDEX.accept,
        RUST_INDEX.byte_length,
        authorization,
    )
    verify_bytes(RUST_INDEX, index)
    digest, size = select_linux_arm64_manifest(index)
    expected_digest = f"sha256:{RUST_PLATFORM.sha256}"
    if (digest, size) != (expected_digest, RUST_PLATFORM.byte_length):
        raise AcquisitionError(
            f"rust index: selected {(digest, size)!r} != "
            f"{(expected_digest, RUST_PLATFORM.byte_length)!r}"
        )
    manifest = _get(
        RUST_PLATFORM.url,
        RUST_PLATFORM.accept,
        RUST_PLATFORM.byte_length,
        authorization,
    )
    verify_bytes(RUST_PLATFORM, manifest)
    digest, size = select_image_config(manifest)
    expected_config = f"sha256:{RUST_CONFIG.sha256}"
    if (digest, size) != (expected_config, RUST_CONFIG.byte_length):
        raise AcquisitionError(
            f"rust manifest: selected {(digest, size)!r} != "
            f"{(expected_config, RUST_CONFIG.byte_length)!r}"
        )
    config = _get(
        RUST_CONFIG.url,
        RUST_CONFIG.accept,
        RUST_CONFIG.byte_length,
        authorization,
    )
    verify_bytes(RUST_CONFIG, config)
    validate_image_config(config)
    return downloads, index, manifest, config


def _close_owned(descriptors: list[int]) -> OSError | None:
    failure: OSError | None = None
    while descriptors:
        descriptor = descriptors.pop()
        try:
            os.close(descriptor)
        except OSError as error:
            if failure is None:
                failure = error
    return failure


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


def _parents_unchanged(
    descriptors: list[int],
    relative: PurePosixPath,
    mount: tuple[int, bytes | None],
) -> None:
    if not descriptors or _identity(os.fstat(descriptors[0])) != _identity(ROOT.lstat()):
        raise AcquisitionError("materialization root identity changed")
    current = ROOT
    for index, component in enumerate(relative.parts[:-1], 1):
        current /= component
        held = os.fstat(descriptors[index])
        named = os.stat(
            component,
            dir_fd=descriptors[index - 1],
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(held.st_mode)
            or _identity(held) != _identity(named)
            or _identity(held) != _identity(current.lstat())
            or not same_held_mount(mount, descriptors[index], current)
        ):
            raise AcquisitionError("materialization parent identity changed")


def _safe_unlink(
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
        named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory,
        )
        held = os.fstat(descriptor)
        if (
            (held.st_dev, held.st_ino) == identity
            and _identity(held) == _identity(named)
            and _identity(held)
            == _identity(
                os.stat(name, dir_fd=directory, follow_symlinks=False)
            )
            and same_held_mount(mount, descriptor, path)
        ):
            os.unlink(name, dir_fd=directory)
    except FileNotFoundError:
        return
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _open_parent(
    relative: PurePosixPath,
) -> tuple[list[int], str, tuple[int, bytes | None]]:
    if relative.is_absolute() or any(
        part in ("", ".", "..") for part in relative.parts
    ):
        raise AcquisitionError(f"unsafe materialization path: {relative}")
    required = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW")
    if any(type(getattr(os, name, None)) is not int for name in required):
        raise AcquisitionError("safe materialization flags are unavailable")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(ROOT, flags))
        root_facts = os.fstat(descriptors[0])
        mount = held_mount_identity(descriptors[0])
        if (
            not stat.S_ISDIR(root_facts.st_mode)
            or _identity(root_facts) != _identity(ROOT.lstat())
        ):
            raise AcquisitionError("materialization root identity changed")
        current = ROOT
        for component in relative.parts[:-1]:
            directory = descriptors[-1]
            current /= component
            try:
                child = os.open(component, flags, dir_fd=directory)
            except FileNotFoundError:
                try:
                    os.mkdir(component, 0o755, dir_fd=directory)
                    child = os.open(component, flags, dir_fd=directory)
                except OSError as error:
                    raise AcquisitionError(
                        f"cannot create direct materialization parent: {relative}"
                    ) from error
            except OSError as error:
                raise AcquisitionError(
                    f"unsafe materialization parent: {relative}"
                ) from error
            descriptors.append(child)
            held = os.fstat(child)
            named = os.stat(component, dir_fd=directory, follow_symlinks=False)
            if (
                not stat.S_ISDIR(held.st_mode)
                or _identity(held) != _identity(named)
                or _identity(held) != _identity(current.lstat())
                or not same_held_mount(mount, child, current)
            ):
                raise AcquisitionError(
                    f"unsafe materialization parent mount: {relative}"
                )
        _parents_unchanged(descriptors, relative, mount)
        return descriptors, relative.name, mount
    except BaseException as error:
        _close_owned(descriptors)
        if isinstance(error, AcquisitionError):
            raise
        if isinstance(error, (OSError, ValueError)):
            raise AcquisitionError(
                f"cannot open materialization parent: {relative}"
            ) from error
        raise


def _write_all(descriptor: int, raw: bytes) -> None:
    offset = 0
    view = memoryview(raw)
    while offset < len(view):
        written = os.write(descriptor, view[offset:])
        if written <= 0:
            raise AcquisitionError("short write while materializing reference")
        offset += written


def _read_existing(
    directory: int,
    leaf: str,
    max_bytes: int,
    mount: tuple[int, bytes | None],
    path: Path,
) -> bytes:
    required = ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK")
    if any(type(getattr(os, name, None)) is not int for name in required):
        raise AcquisitionError("safe existing-file flags are unavailable")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptor: int | None = None
    failure: AcquisitionError | None = None
    data = bytearray()
    try:
        named = os.stat(leaf, dir_fd=directory, follow_symlinks=False)
        descriptor = os.open(leaf, flags, dir_fd=directory)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or _identity(before) != _identity(named)
            or not same_held_mount(mount, descriptor, path)
        ):
            raise AcquisitionError("existing materialization leaf is not regular")
        if before.st_size > max_bytes:
            raise AcquisitionError("existing materialization leaf exceeds expected length")
        while True:
            chunk = os.read(
                descriptor,
                min(64 * 1024, max_bytes + 1 - len(data)),
            )
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > max_bytes:
                raise AcquisitionError(
                    "existing materialization leaf exceeds expected length"
                )
        after = os.fstat(descriptor)
        final_named = os.stat(leaf, dir_fd=directory, follow_symlinks=False)
        if (
            _facts(before) != _facts(after)
            or _facts(after) != _facts(final_named)
            or len(data) != after.st_size
            or not same_held_mount(mount, descriptor, path)
        ):
            raise AcquisitionError("existing materialization leaf changed")
    except AcquisitionError as error:
        failure = error
    except (OSError, ValueError) as error:
        failure = AcquisitionError("cannot read existing materialization leaf")
        failure.__cause__ = error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as error:
                if failure is None:
                    failure = AcquisitionError(
                        "cannot close existing materialization leaf"
                    )
                    failure.__cause__ = error
    if failure is not None:
        raise failure
    return bytes(data)


def write_exact(path: Path, raw: bytes) -> None:
    try:
        relative_text = path.relative_to(ROOT).as_posix()
    except ValueError as error:
        raise AcquisitionError(f"write outside repository: {path}") from error
    relative = PurePosixPath(relative_text)
    if (
        any(character in relative_text for character in ("\0", "\\"))
        or relative.is_absolute()
        or relative.as_posix() != relative_text
        or not relative.parts
        or any(part in ("", ".", "..") for part in relative.parts)
    ):
        raise AcquisitionError(f"unsafe materialization path: {relative_text!r}")
    descriptors, leaf, mount = _open_parent(relative)
    directory = descriptors[-1]
    temporary_name: str | None = None
    temporary_identity: tuple[int, int] | None = None
    published_identity: tuple[int, int] | None = None
    failure: AcquisitionError | None = None
    committed = False
    try:
        _parents_unchanged(descriptors, relative, mount)
        try:
            facts = os.stat(leaf, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            facts = None
        if facts is not None:
            if not stat.S_ISREG(facts.st_mode):
                raise AcquisitionError(f"refusing nonregular existing file: {path}")
            existing = _read_existing(directory, leaf, len(raw), mount, path)
            _parents_unchanged(descriptors, relative, mount)
            if existing != raw:
                raise AcquisitionError(f"refusing mismatched existing file: {path}")
        else:
            flags = (
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
            )
            descriptor: int | None = None
            for index in range(64):
                candidate = f".{leaf}.{index}.tmp"
                try:
                    descriptor = os.open(candidate, flags, 0o600, dir_fd=directory)
                except FileExistsError:
                    continue
                temporary_name = candidate
                descriptors.append(descriptor)
                held = os.fstat(descriptor)
                temporary_identity = (held.st_dev, held.st_ino)
                if not same_held_mount(
                    mount,
                    descriptor,
                    path.parent / candidate,
                ):
                    raise AcquisitionError("temporary reference mount changed")
                break
            if descriptor is None or temporary_name is None:
                raise AcquisitionError(
                    "no bounded temporary reference name is available"
                )
            _write_all(descriptor, raw)
            os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            verified = bytearray()
            while True:
                chunk = os.read(
                    descriptor, min(64 * 1024, len(raw) + 1 - len(verified))
                )
                if not chunk:
                    break
                verified.extend(chunk)
                if len(verified) > len(raw):
                    raise AcquisitionError("temporary reference exceeds expected length")
            if bytes(verified) != raw:
                raise AcquisitionError("temporary reference verification failed")
            expected_facts = _facts(os.fstat(descriptor))
            _parents_unchanged(descriptors, relative, mount)
            verification = os.open(
                temporary_name,
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=directory,
            )
            descriptors.append(verification)
            named_temporary = os.stat(
                temporary_name,
                dir_fd=directory,
                follow_symlinks=False,
            )
            if (
                _facts(os.fstat(verification)) != expected_facts
                or _facts(named_temporary) != expected_facts
                or not same_held_mount(
                    mount,
                    verification,
                    path.parent / temporary_name,
                )
            ):
                raise AcquisitionError("temporary reference identity changed")
            _parents_unchanged(descriptors, relative, mount)
            try:
                os.link(
                    temporary_name,
                    leaf,
                    src_dir_fd=directory,
                    dst_dir_fd=directory,
                    follow_symlinks=False,
                )
            except FileExistsError as error:
                raise AcquisitionError(
                    f"materialization destination appeared concurrently: {path}"
                ) from error
            published = os.open(
                leaf,
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=directory,
            )
            descriptors.append(published)
            published_facts = os.fstat(published)
            named_published = os.stat(
                leaf,
                dir_fd=directory,
                follow_symlinks=False,
            )
            if (
                _identity(published_facts) != _identity(os.fstat(verification))
                or _facts(published_facts) != _facts(named_published)
                or not same_held_mount(mount, published, path)
            ):
                raise AcquisitionError("published reference identity changed")
            published_identity = (published_facts.st_dev, published_facts.st_ino)
            _parents_unchanged(descriptors, relative, mount)
            os.fsync(directory)
            owned_temporary = temporary_name
            temporary_name = None
            _safe_unlink(
                directory,
                owned_temporary,
                temporary_identity,
                mount,
                path.parent / owned_temporary,
            )
            os.fsync(directory)
            committed = True
    except AcquisitionError as error:
        failure = error
    except (OSError, ValueError) as error:
        failure = AcquisitionError(f"reference materialization failed: {path}")
        failure.__cause__ = error
    finally:
        if failure is not None and published_identity is not None:
            try:
                _safe_unlink(directory, leaf, published_identity, mount, path)
            except OSError as error:
                if failure is None:
                    failure = AcquisitionError(
                        f"reference materialization rollback failed: {path}"
                    )
                    failure.__cause__ = error
        if temporary_name is not None:
            try:
                _safe_unlink(
                    directory,
                    temporary_name,
                    temporary_identity,
                    mount,
                    path.parent / temporary_name,
                )
            except OSError as error:
                if failure is None:
                    failure = AcquisitionError(
                        f"reference materialization cleanup failed: {path}"
                    )
                    failure.__cause__ = error
        close_error = _close_owned(descriptors)
        if close_error is not None and failure is None and not committed:
            failure = AcquisitionError(
                f"reference materialization close failed: {path}"
            )
            failure.__cause__ = close_error
    if failure is not None:
        raise failure


def main() -> None:
    downloads, index, manifest, config = acquire_all()
    acquired = downloads + [
        (RUST_INDEX, index),
        (RUST_PLATFORM, manifest),
        (RUST_CONFIG, config),
    ]
    for artifact, raw in acquired:
        write_exact(DESTINATION / artifact.filename, raw)
    fips = next(raw for artifact, raw in downloads if artifact.id == "fips-180-4")
    write_exact(FIPS_SNAPSHOT, fips)

    for artifact, raw in acquired:
        print(f"verified {artifact.id} {artifact.sha256} {len(raw)}")
    print(
        "wrote inputs/references/fips-180-4.pdf "
        f"{sha256(fips).hexdigest()} {len(fips)}"
    )


if __name__ == "__main__":
    main()
