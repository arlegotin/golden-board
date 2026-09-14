#!/usr/bin/env python3
"""Phase-aware, fail-closed M2 Gate-8 producer and assembly entrypoint."""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
import errno
import hashlib
import os
from pathlib import Path
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Callable, Mapping, NoReturn, Sequence


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "python"))

from golden_board import (  # noqa: E402
    bootstrap,
    canonical_manifest,
    m2_codec,
    m2_damage,
    m2_decoder,
    m2_gate8,
    m2_independence,
    m2_recipe,
    m2_route_data,
    m2_runner,
)
from tools.m2 import generate_candidates  # noqa: E402


PROFILE_ID = "eh72-hier-r5-r2-r1-crc32c-v0"
POLICY_PATH = ROOT / "spec" / "gate8-policy-v0.toml"
REFRESH_POLICY_PATH = ROOT / "spec" / "gate8-verifier-refresh-v0.toml"
_REFRESH_ARCHIVE = ROOT / "artifacts/linux/verifier-refresh-c1ef7213-v0"
_RELEASE_REPAIR_ARCHIVE = (
    ROOT / "artifacts/linux/gate8-clean-linux-test-refresh-v0"
)
_POST_ASSEMBLY_TEST_ARCHIVE = (
    ROOT / "artifacts/linux/gate8-candidate-ready-test-refresh-v0"
)
_RUNTIME_TEST_REPAIR_ARCHIVE = (
    ROOT / "artifacts/linux/gate8-candidate-ready-runtime-test-refresh-v0"
)
_CLEAN_SNAPSHOT_TEST_REPAIR_ARCHIVE = (
    ROOT / "artifacts/linux/gate8-candidate-ready-clean-snapshot-refresh-v0"
)
_PROVENANCE_INPUT_REPAIR_ARCHIVE = (
    ROOT
    / "artifacts/linux/gate8-candidate-ready-provenance-input-refresh-v0"
)
_PROVENANCE_FIXTURE_REPAIR_ARCHIVE = (
    ROOT
    / "artifacts/linux/gate8-provenance-fixture-refresh-v0"
)
_GATE8_ROOT = ROOT / "artifacts/gate8"
_REPORT_PATH = ROOT / "reports/m2-feasibility-v0.json"
_ROADMAP_PATH = ROOT / "docs/roadmap.md"
_ACQUISITION_PATH = ROOT / "artifacts/linux/verifier-v0.env"
_PRIOR_ROADMAP_SHA256 = (
    "2914de9b4a7556258f4b1d69c24076270628656379dfbe8fa73d25301cacf7d8"
)
_PENDING_ROADMAP_SHA256 = (
    "153f66d0713c04d357c3bf980b3fde1feae328d7751099e5c9bb019c6f98b1f1"
)
_REFRESH_MANIFEST_SHA256 = (
    "b462ef1a05384bb4803b9fe6e1bd4a8b3ce479cc70f0fd8f0083cbe2f59c5d21"
)
_REFRESH_PAYLOAD_SHA256 = (
    "a741dff22f080aa01f790570cf02626e489c669c5ea26c102571a51a0ab1487b"
)
_REFRESH_DOMAIN = b"golden-board:m2-gate8-verifier-refresh-archive:v0\0"
_RELEASE_REPAIR_DOMAIN = (
    b"golden-board:m2-gate8-clean-linux-test-refresh-archive:v0\0"
)
_RELEASE_REPAIR_SCHEMA = (
    "golden-board.m2-gate8-clean-linux-test-refresh-archive/v0"
)
_RELEASE_REPAIR_MANIFEST_SHA256 = (
    "5a1188fd65d9734bc3cb10f912af98dedd2282cd9d57a0d4edb41d8b0ed5d482"
)
_RELEASE_REPAIR_PAYLOAD_SHA256 = (
    "d76245a7b0d8cfc8071b6a4a68c3da1bb60000e1dfdbccaae62dfcdd35560d9a"
)
_RELEASE_REPAIR_REPORT_SHA256 = (
    "f6da8e64635fcbca8f65baac2b14dedcaed45bef2479eff2e1acb56f4e760809"
)
_RELEASE_REPAIR_ROADMAP_SHA256 = (
    "16116145b7db913cec1b322a6dccc1adefacdd52c9153aa4bd7913f14de8b418"
)
_POST_ASSEMBLY_TEST_DOMAIN = (
    b"golden-board:m2-gate8-candidate-ready-test-refresh-archive:v0\0"
)
_POST_ASSEMBLY_TEST_SCHEMA = (
    "golden-board.m2-gate8-candidate-ready-test-refresh-archive/v0"
)
_POST_ASSEMBLY_TEST_MANIFEST_SHA256 = (
    "13bf603c0bac6ff5f44a5d115b8954a214f777d505a49ddc12c445f7fd5a760f"
)
_POST_ASSEMBLY_TEST_PAYLOAD_SHA256 = (
    "f378a44cdea3c65acf2275346b9b939c4467e9f7b330a873c1cda2339906b3b0"
)
_POST_ASSEMBLY_TEST_REPORT_SHA256 = (
    "1589678984f75c7d7c27fab3e06c39d23b99d7d80a0a1a8a3b9d2461e632ddcb"
)
_POST_ASSEMBLY_TEST_ROADMAP_SHA256 = (
    "be9f9634cb9ec475240df1df592568cbe9ab74c7c052ec9a701e59f259c22281"
)
_RUNTIME_TEST_REPAIR_DOMAIN = (
    b"golden-board:m2-gate8-candidate-ready-runtime-test-refresh-archive:v0\0"
)
_RUNTIME_TEST_REPAIR_SCHEMA = (
    "golden-board.m2-gate8-candidate-ready-runtime-test-refresh-archive/v0"
)
_RUNTIME_TEST_REPAIR_MANIFEST_SHA256 = (
    "5f6932d350d2f418ad23290b92b983489e8fab077524209e9f1375e1738607f5"
)
_RUNTIME_TEST_REPAIR_PAYLOAD_SHA256 = (
    "e00576ade3267b94cb0b25b5f313eb1d8a25cc50f639bf264cfef1c07ae3d290"
)
_RUNTIME_TEST_REPAIR_REPORT_SHA256 = (
    "0bf75dac0bb3b1d71376885be946cb591d4e8970fd3686b1784c2165b3a3ede1"
)
_RUNTIME_TEST_REPAIR_ROADMAP_SHA256 = (
    "cf121dfa99390ba0b73b88c8eb1aff20667d6e47569ecfc138763600929f27e0"
)
_CLEAN_SNAPSHOT_TEST_REPAIR_DOMAIN = (
    b"golden-board:m2-gate8-candidate-ready-clean-snapshot-refresh-archive:v0\0"
)
_CLEAN_SNAPSHOT_TEST_REPAIR_SCHEMA = (
    "golden-board.m2-gate8-candidate-ready-clean-snapshot-refresh-archive/v0"
)
_CLEAN_SNAPSHOT_TEST_REPAIR_MANIFEST_SHA256 = (
    "fadd7a64769bc944c7416280d3bfb7c5cbd61a1f7c4211bc173abe6a752f0762"
)
_CLEAN_SNAPSHOT_TEST_REPAIR_PAYLOAD_SHA256 = (
    "a0fea678870075dca724c66f776d0c0eea0a180edcea1b8035fba413392efa38"
)
_CLEAN_SNAPSHOT_TEST_REPAIR_REPORT_SHA256 = (
    "4e039eb356a2153d86cf1a5d4db5af2aa7d15f64bce97902cd11d0e6bcb135a8"
)
_CLEAN_SNAPSHOT_TEST_REPAIR_ROADMAP_SHA256 = (
    "b1f884836b76b08b505a33fc66549a4b0ea3462820401ed1661834717599044e"
)
_PROVENANCE_INPUT_REPAIR_DOMAIN = (
    b"golden-board:m2-gate8-candidate-ready-provenance-input-refresh-archive:v0\0"
)
_PROVENANCE_INPUT_REPAIR_SCHEMA = (
    "golden-board.m2-gate8-candidate-ready-provenance-input-refresh-archive/v0"
)
_PROVENANCE_INPUT_REPAIR_MANIFEST_SHA256 = (
    "07aed69df68caae925ec29c75433db214fb47f8a1d8b8b1ea524806fde656803"
)
_PROVENANCE_INPUT_REPAIR_PAYLOAD_SHA256 = (
    "62e0b1b8bd1cfcfc2733ae207a5be882f991de0080c0c63c9988b71e0eacd2d5"
)
_PROVENANCE_INPUT_REPAIR_REPORT_SHA256 = (
    "9d23768ab807954a627aa5a83ddefd2522eddedc05dd103c173442c2f6b945db"
)
_PROVENANCE_INPUT_REPAIR_ROADMAP_SHA256 = (
    "818c8f653edcdb4269db391980c6609b8d7424bcbed8bf4ff4b01e66c7c82be9"
)
_PROVENANCE_FIXTURE_REPAIR_DOMAIN = (
    b"golden-board:m2-gate8-provenance-fixture-refresh-archive:v0\0"
)
_PROVENANCE_FIXTURE_REPAIR_SCHEMA = (
    "golden-board.m2-gate8-provenance-fixture-refresh-archive/v0"
)
_PROVENANCE_FIXTURE_REPAIR_MANIFEST_SHA256 = (
    "16c9692dcb32802e77f4c3e56ce34807e05227d4f4a0164ccb2f5726a563c418"
)
_PROVENANCE_FIXTURE_REPAIR_PAYLOAD_SHA256 = (
    "af4d10df67057564200a3c1efaac7ca9f619f246cffefe11f8e8296add0c3ee0"
)
_PROVENANCE_FIXTURE_REPAIR_REPORT_SHA256 = (
    "d4f3170059a605541029a8ae69288e2a1f718fea9881e67ca12456f0b9d76f0f"
)
_PROVENANCE_FIXTURE_REPAIR_ROADMAP_SHA256 = (
    "9d375aff96dbc7ae029468dfc687f2c0d33c9b9c3c446daf4cbf7641bdbd6f66"
)
_MAX_FILE_BYTES = 1_048_576
_MAX_ERROR_BYTES = 16_384
_PRODUCER_IDS = ("native-python", "native-rust", "linux-python", "linux-rust")
_PYTHON_PRODUCER_IDS = ("native-python", "linux-python")
_NATIVE_IDS = ("native-python", "native-rust")


class Gate8CliError(ValueError):
    __slots__ = ("reason", "exit_code")

    def __init__(self, reason: str, exit_code: int = 3) -> None:
        self.reason = reason
        self.exit_code = exit_code
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class GeneratedGateSeven:
    manifestation: object
    damage_files: dict[str, bytes]
    proof_raw: bytes
    artifacts: dict[str, bytes]
    bundle_case_preimages: tuple[tuple[str, str, bytes, bytes], ...] = ()
    clean_result_raw: bytes = b""
    content_stream: bytes = b""


@dataclass(frozen=True, slots=True)
class Gate8Assembly:
    tree_files: dict[str, tuple[bytes, int]]
    report_raw: bytes


def _fail(reason: str, exit_code: int = 3) -> NoReturn:
    raise Gate8CliError(reason, exit_code)


def _source_root() -> Path:
    try:
        current = Path.cwd()
        current_metadata = current.stat()
        root_metadata = ROOT.stat()
    except OSError as error:
        raise Gate8CliError("source-root", 2) from error
    if (
        current_metadata.st_dev != root_metadata.st_dev
        or current_metadata.st_ino != root_metadata.st_ino
        or current.is_symlink()
    ):
        _fail("source-root", 2)
    return ROOT


def _absolute_path(value: str, reason: str) -> Path:
    if type(value) is not str or not value or "\0" in value:
        _fail(reason, 2)
    path = Path(value)
    if not path.is_absolute() or path.name in ("", ".", ".."):
        _fail(reason, 2)
    return path


def _disjoint_paths(reason: str, *paths: Path) -> None:
    """Reject equal or nested filesystem roles before any generation/write."""

    absolute = tuple(Path(os.path.abspath(path)) for path in paths)
    for index, left in enumerate(absolute):
        for right in absolute[index + 1 :]:
            if left == right or left in right.parents or right in left.parents:
                _fail(reason, 2)


def _lstat(path: Path, reason: str) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as error:
        raise Gate8CliError(reason, 2) from error


def _no_symlink_ancestors(path: Path, reason: str) -> None:
    absolute = Path(os.path.abspath(path))
    cursor = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        cursor /= component
        if cursor.exists() or cursor.is_symlink():
            metadata = _lstat(cursor, reason)
            if stat.S_ISLNK(metadata.st_mode):
                _fail(reason, 2)


def _private_directory(path: Path, reason: str, *, empty: bool) -> None:
    _no_symlink_ancestors(path, reason)
    metadata = _lstat(path, reason)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        _fail(reason, 2)
    try:
        entries = tuple(path.iterdir())
    except OSError as error:
        raise Gate8CliError(reason, 2) from error
    if empty and entries:
        _fail(reason, 2)


def _regular_file(path: Path, reason: str, maximum: int = _MAX_FILE_BYTES) -> bytes:
    _no_symlink_ancestors(path, reason)
    metadata = _lstat(path, reason)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_nlink != 1
        or not 1 <= metadata.st_size <= maximum
    ):
        _fail(reason, 2)
    try:
        raw = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise Gate8CliError(reason, 2) from error
    if (
        len(raw) != metadata.st_size
        or after.st_dev != metadata.st_dev
        or after.st_ino != metadata.st_ino
        or after.st_size != metadata.st_size
        or after.st_mtime_ns != metadata.st_mtime_ns
        or after.st_nlink != 1
    ):
        _fail(reason, 2)
    return raw


def _write_fsynced(path: Path, raw: bytes, mode: int = 0o600) -> None:
    if type(raw) is not bytes or not raw:
        _fail("output-bytes")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise Gate8CliError("output-write") from error


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise Gate8CliError("directory-fsync") from error


def _rename_noreplace(source: Path, destination: Path) -> None:
    """Atomically rename one same-filesystem path without replacement."""

    library = ctypes.CDLL(None, use_errno=True)
    source_raw = os.fsencode(source)
    destination_raw = os.fsencode(destination)
    if sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        status_code = library.renameat2(
            -100, source_raw, -100, destination_raw, 1
        )
    elif sys.platform == "darwin" and hasattr(library, "renamex_np"):
        status_code = library.renamex_np(
            source_raw, destination_raw, 0x00000004
        )
    else:
        _fail("rename-noreplace-unsupported")
    if status_code != 0:
        observed_errno = ctypes.get_errno()
        if observed_errno in {errno.EEXIST, errno.ENOTEMPTY}:
            _fail("assembly-publish-race", 2)
        raise Gate8CliError("assembly-publish") from OSError(
            observed_errno, os.strerror(observed_errno)
        )


def _cleanup_tree(root: Path) -> None:
    """Link-safe cleanup of one caller-owned private work root."""

    try:
        entries = tuple(root.iterdir())
    except OSError as error:
        raise Gate8CliError("work-root-cleanup") from error
    if len(entries) > 10_100:
        _fail("work-root-cleanup")
    for entry in entries:
        metadata = _lstat(entry, "work-root-cleanup")
        try:
            if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
                shutil.rmtree(entry)
            else:
                entry.unlink()
        except OSError as error:
            raise Gate8CliError("work-root-cleanup") from error
    _fsync_directory(root)
    _private_directory(root, "work-root-cleanup", empty=True)


def _owner(relative: str, maximum: int = 16 * _MAX_FILE_BYTES) -> bytes:
    path = ROOT / relative
    raw = _regular_file(path, "owner-read", maximum)
    return raw


def _refresh_owner() -> tuple[bytes, dict[str, object], bytes]:
    policy_raw = _owner("spec/gate8-policy-v0.toml")
    refresh_raw = _owner("spec/gate8-verifier-refresh-v0.toml")
    try:
        m2_gate8.load_gate8_policy(policy_raw)
        refresh = m2_gate8.load_gate8_verifier_refresh(refresh_raw)
    except m2_gate8.Gate8Error as error:
        raise Gate8CliError("refresh-owner", 2) from error
    return policy_raw, refresh, refresh_raw


def _refresh_payload_sequence(values: Mapping[str, tuple[bytes, int]]) -> str:
    if not isinstance(values, Mapping) or len(values) != 71:
        _fail("refresh-prior-file-set", 2)
    rows = sorted(values, key=lambda path: path.encode("utf-8"))
    preimage = bytearray(_REFRESH_DOMAIN)
    preimage.extend(len(rows).to_bytes(8, "big"))
    for path in rows:
        raw, mode = values[path]
        try:
            path_raw = path.encode("utf-8")
        except UnicodeError as error:
            raise Gate8CliError("refresh-prior-path", 2) from error
        if (
            not path
            or path.startswith("/")
            or "\\" in path
            or any(part in ("", ".", "..") for part in path.split("/"))
            or type(raw) is not bytes
            or not raw
            or mode not in (0o644, 0o755)
        ):
            _fail("refresh-prior-file-set", 2)
        preimage.extend(len(path_raw).to_bytes(8, "big"))
        preimage.extend(path_raw)
        preimage.extend(len(raw).to_bytes(8, "big"))
        preimage.extend(hashlib.sha256(raw).digest())
    return hashlib.sha256(preimage).hexdigest()


def _refresh_manifest(values: Mapping[str, tuple[bytes, int]]) -> bytes:
    rows = [
        {
            "byte_length": len(values[path][0]),
            "path": path,
            "sha256": hashlib.sha256(values[path][0]).hexdigest(),
        }
        for path in sorted(values, key=lambda item: item.encode("utf-8"))
    ]
    raw = canonical_manifest.serialize_manifest(
        {
            "files": rows,
            "schema": "golden-board.m2-linux-verifier-refresh-archive/v0",
        }
    )
    if (
        len(raw) != 11_816
        or hashlib.sha256(raw).hexdigest() != _REFRESH_MANIFEST_SHA256
        or _refresh_payload_sequence(values) != _REFRESH_PAYLOAD_SHA256
    ):
        _fail("refresh-prior-identity", 2)
    return raw


def _prior_tree_expected_paths(
    policy_raw: bytes,
    observed: Mapping[str, tuple[bytes, int]],
) -> dict[str, int]:
    policy = m2_gate8.load_gate8_policy(policy_raw)
    phase = policy.get("phase_paths")
    if type(phase) is not dict or type(phase.get("gate8_exact_files")) is not list:
        _fail("refresh-prior-policy", 2)
    prefix = "artifacts/gate8/"
    expected: dict[str, int] = {}
    for path in phase["gate8_exact_files"]:
        if type(path) is not str or not path.startswith(prefix):
            _fail("refresh-prior-policy", 2)
        relative = path[len(prefix) :]
        if relative in expected:
            _fail("refresh-prior-policy", 2)
        expected[relative] = 0o644
    for bundle_kind in ("technical", "learner"):
        manifest_name = f"bundles/{bundle_kind}-v0.json"
        manifest_item = observed.get(manifest_name)
        if manifest_item is None:
            _fail("refresh-prior-bundle", 2)
        try:
            manifest = canonical_manifest.validate_canonical_manifest(
                manifest_item[0]
            )
        except (ValueError, canonical_manifest.ManifestError) as error:
            raise Gate8CliError("refresh-prior-bundle", 2) from error
        participant = manifest.get("participant_files")
        evaluator = manifest.get("evaluator_files")
        if (
            type(participant) is not list
            or type(evaluator) is not list
            or any(type(row) is not dict for row in participant + evaluator)
        ):
            _fail("refresh-prior-bundle", 2)
        files: dict[str, bytes] = {}
        for row in participant + evaluator:
            role = row.get("role_id")
            relative = row.get("path")
            mode_text = row.get("mode")
            if (
                type(role) is not str
                or role in files
                or type(relative) is not str
                or mode_text not in ("100644", "100755")
            ):
                _fail("refresh-prior-bundle", 2)
            tree_path = f"bundles/{bundle_kind}/{relative}"
            item = observed.get(tree_path)
            if item is None or tree_path in expected:
                _fail("refresh-prior-bundle", 2)
            files[role] = item[0]
            expected[tree_path] = 0o755 if mode_text == "100755" else 0o644
        try:
            m2_gate8.validate_bundle_manifest(
                manifest_item[0], policy_raw, bundle_kind, files
            )
        except m2_gate8.Gate8Error as error:
            raise Gate8CliError("refresh-prior-bundle", 2) from error
    if len(expected) != 69:
        _fail("refresh-prior-file-set", 2)
    return expected


def _admit_prior_tree(policy_raw: bytes) -> dict[str, tuple[bytes, int]]:
    observed, _directories = _tree_files(_GATE8_ROOT)
    expected = _prior_tree_expected_paths(policy_raw, observed)
    if set(observed) != set(expected):
        _fail("refresh-prior-file-set", 2)
    for path, mode in expected.items():
        if observed[path][1] != mode:
            _fail("refresh-prior-file-mode", 2)
        if path.endswith(".json"):
            try:
                canonical_manifest.validate_canonical_manifest(observed[path][0])
            except (ValueError, canonical_manifest.ManifestError) as error:
                raise Gate8CliError("refresh-prior-canonical", 2) from error
    if (
        hashlib.sha256(observed["linux-attestation-v0.json"][0]).hexdigest()
        != "797f6fe868b56d59bb46323665f4c658759b93b3a6adc4dd904785c4db7bf44f"
        or hashlib.sha256(observed["generated-evidence-v0.json"][0]).hexdigest()
        != "87c2f1548ac789ed4ab533c5ba8ba56606735e3a355514c54620e2a6a2d320c5"
        or hashlib.sha256(observed["evidence-source-v0.json"][0]).hexdigest()
        != "89bf45c209d9a0d1c41039690d8b309f8e54d8a0f68ae651a6b18e8f3ee652c5"
    ):
        _fail("refresh-prior-direct-hash", 2)
    receipts = {
        producer_id: observed[f"receipts/{producer_id}.json"][0]
        for producer_id in _PRODUCER_IDS
    }
    candidate_raw = _regular_file(
        ROOT
        / "artifacts/candidates"
        / PROFILE_ID
        / "candidate-manifest.json",
        "refresh-prior-candidate",
    )
    cross_raw = observed[
        f"{PROFILE_ID}/cross-language-manifest.json"
    ][0]
    selection_raw = observed["selection-v0.json"][0]
    profile_raw = _owner("spec/profile-policy-v1.toml")
    try:
        for producer_id, raw in receipts.items():
            m2_gate8.parse_producer_receipt(raw, producer_id)
        m2_gate8.validate_cross_language_manifest(
            cross_raw, receipts, candidate_raw
        )
        selection = canonical_manifest.validate_canonical_manifest(selection_raw)
        candidate_rows = selection.get("candidate_rows")
        if type(candidate_rows) is not list or len(candidate_rows) != 1:
            _fail("refresh-prior-selection", 2)
        expected_row = m2_gate8.build_candidate_row(
            m2_gate8._CANDIDATE_METRICS,  # noqa: SLF001
            profile_raw,
            cross_raw,
        )
        if candidate_rows[0] != expected_row:
            _fail("refresh-prior-selection", 2)
        m2_gate8.validate_selection(
            selection_raw, expected_row, cross_raw, profile_raw
        )
    except (m2_gate8.Gate8Error, canonical_manifest.ManifestError) as error:
        raise Gate8CliError("refresh-prior-cross-binding", 2) from error
    return observed


def _admit_prior_live(policy_raw: bytes) -> dict[str, tuple[bytes, int]]:
    tree = _admit_prior_tree(policy_raw)
    report = _regular_file(_REPORT_PATH, "refresh-prior-report")
    roadmap = _regular_file(
        _ROADMAP_PATH, "refresh-prior-roadmap", 16 * _MAX_FILE_BYTES
    )
    try:
        canonical_manifest.validate_canonical_manifest(report)
    except (ValueError, canonical_manifest.ManifestError) as error:
        raise Gate8CliError("refresh-prior-report", 2) from error
    if (
        hashlib.sha256(report).hexdigest()
        != "98e9c71997604ec3f57ad0dba09e24ecbf32016575973bb73a1bc28b57f417e3"
        or hashlib.sha256(roadmap).hexdigest() != _PRIOR_ROADMAP_SHA256
    ):
        _fail("refresh-prior-direct-hash", 2)
    values = {
        f"artifacts/gate8/{path}": item for path, item in tree.items()
    }
    values["reports/m2-feasibility-v0.json"] = (report, 0o644)
    values["docs/roadmap.md"] = (roadmap, 0o644)
    if (
        len(values) != 71
        or sum(len(raw) for raw, _mode in values.values()) != 11_435_789
    ):
        _fail("refresh-prior-file-set", 2)
    _refresh_manifest(values)
    return values


def _archive_values(
    root: Path | None = None,
) -> dict[str, tuple[bytes, int]]:
    archive_root = _REFRESH_ARCHIVE if root is None else root
    try:
        observed, directories = _tree_files(archive_root)
    except Gate8CliError as error:
        if error.reason in {
            "gate8-file",
            "gate8-hardlink",
            "gate8-directory",
        }:
            raise Gate8CliError("refresh-archive-alias", 2) from error
        raise
    manifest_item = observed.get("archive-manifest-v0.json")
    if manifest_item is None or manifest_item[1] != 0o600:
        _fail("refresh-archive")
    try:
        manifest = canonical_manifest.validate_canonical_manifest(manifest_item[0])
    except (ValueError, canonical_manifest.ManifestError) as error:
        raise Gate8CliError("refresh-archive") from error
    rows = manifest.get("files")
    if (
        set(manifest) != {"files", "schema"}
        or manifest.get("schema")
        != "golden-board.m2-linux-verifier-refresh-archive/v0"
        or type(rows) is not list
        or len(rows) != 71
        or hashlib.sha256(manifest_item[0]).hexdigest()
        != _REFRESH_MANIFEST_SHA256
    ):
        _fail("refresh-archive")
    values: dict[str, tuple[bytes, int]] = {}
    paths: list[str] = []
    for row in rows:
        if (
            type(row) is not dict
            or set(row) != {"byte_length", "path", "sha256"}
            or type(row.get("path")) is not str
            or type(row.get("byte_length")) is not int
            or type(row.get("sha256")) is not str
        ):
            _fail("refresh-archive")
        original = row["path"]
        stored = f"prior/{original}"
        item = observed.get(stored)
        if (
            item is None
            or item[1] != 0o600
            or len(item[0]) != row["byte_length"]
            or hashlib.sha256(item[0]).hexdigest() != row["sha256"]
            or original in values
        ):
            _fail("refresh-archive")
        values[original] = (item[0], 0o755 if original.endswith("m2-learner-runner.py") else 0o644)
        paths.append(original)
    expected_files = {"archive-manifest-v0.json"} | {
        f"prior/{path}" for path in values
    }
    expected_directories = {
        parent.as_posix()
        for name in expected_files
        for parent in Path(name).parents
        if parent.as_posix() != "."
    }
    try:
        expected_manifest = _refresh_manifest(values)
    except Gate8CliError as error:
        raise Gate8CliError("refresh-archive") from error
    if (
        set(observed) != expected_files
        or directories != expected_directories
        or paths != sorted(paths, key=lambda path: path.encode("utf-8"))
        or expected_manifest != manifest_item[0]
    ):
        _fail("refresh-archive")
    return values


def _create_archive(values: Mapping[str, tuple[bytes, int]]) -> None:
    if _REFRESH_ARCHIVE.exists() or _REFRESH_ARCHIVE.is_symlink():
        _fail("refresh-archive-precondition", 2)
    parent = _REFRESH_ARCHIVE.parent
    _no_symlink_ancestors(parent, "refresh-archive-parent")
    metadata = _lstat(parent, "refresh-archive-parent")
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        _fail("refresh-archive-parent", 2)
    manifest = _refresh_manifest(values)
    stage = Path(tempfile.mkdtemp(prefix=".verifier-refresh-", dir=parent))
    try:
        os.chmod(stage, 0o700)
        for original, (raw, _mode) in values.items():
            destination = stage / "prior" / original
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _write_fsynced(destination, raw, 0o600)
        _write_fsynced(stage / "archive-manifest-v0.json", manifest, 0o600)
        for directory in sorted(
            (path for path in stage.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            os.chmod(directory, 0o700)
            _fsync_directory(directory)
        _fsync_directory(stage)
        if _archive_values(stage) != dict(values):
            _fail("refresh-archive-stage")
        _rename_noreplace(stage, _REFRESH_ARCHIVE)
        _fsync_directory(parent)
    finally:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
    archived = _archive_values()
    if archived != dict(values):
        _fail("refresh-archive-postcondition")


def _release_repair_payload_sequence(
    values: Mapping[str, tuple[bytes, int]],
) -> str:
    if not isinstance(values, Mapping) or len(values) != 71:
        _fail("release-repair-file-set", 2)
    paths = sorted(values, key=lambda path: path.encode("utf-8"))
    preimage = bytearray(_RELEASE_REPAIR_DOMAIN)
    preimage.extend(len(paths).to_bytes(8, "big"))
    for path in paths:
        raw, mode = values[path]
        try:
            path_raw = path.encode("utf-8")
        except UnicodeError as error:
            raise Gate8CliError("release-repair-path", 2) from error
        if (
            not path
            or path.startswith("/")
            or "\\" in path
            or any(part in ("", ".", "..") for part in path.split("/"))
            or type(raw) is not bytes
            or not raw
            or mode not in (0o644, 0o755)
        ):
            _fail("release-repair-file-set", 2)
        preimage.extend(len(path_raw).to_bytes(8, "big"))
        preimage.extend(path_raw)
        preimage.extend(len(raw).to_bytes(8, "big"))
        preimage.extend(hashlib.sha256(raw).digest())
    return hashlib.sha256(preimage).hexdigest()


def _release_repair_manifest(
    values: Mapping[str, tuple[bytes, int]],
) -> bytes:
    rows = [
        {
            "byte_length": len(values[path][0]),
            "path": path,
            "sha256": hashlib.sha256(values[path][0]).hexdigest(),
        }
        for path in sorted(values, key=lambda item: item.encode("utf-8"))
    ]
    raw = canonical_manifest.serialize_manifest(
        {"files": rows, "schema": _RELEASE_REPAIR_SCHEMA}
    )
    if (
        len(raw) != 11_824
        or hashlib.sha256(raw).hexdigest()
        != _RELEASE_REPAIR_MANIFEST_SHA256
        or _release_repair_payload_sequence(values)
        != _RELEASE_REPAIR_PAYLOAD_SHA256
    ):
        _fail("release-repair-identity", 2)
    return raw


def _release_repair_expected_mode(path: str) -> int:
    return 0o755 if path.endswith("m2-learner-runner.py") else 0o644


def _release_repair_live_values() -> dict[str, tuple[bytes, int]]:
    tree, directories = _tree_files(_GATE8_ROOT)
    expected_directories = {
        parent.as_posix()
        for path in tree
        for parent in Path(path).parents
        if parent.as_posix() != "."
    }
    if len(tree) != 69 or directories != expected_directories:
        _fail("release-repair-file-set", 2)
    values = {
        f"artifacts/gate8/{path}": item for path, item in tree.items()
    }
    values["reports/m2-feasibility-v0.json"] = (
        _regular_file(_REPORT_PATH, "release-repair-report"),
        0o644,
    )
    values["docs/roadmap.md"] = (
        _regular_file(
            _ROADMAP_PATH, "release-repair-roadmap", 16 * _MAX_FILE_BYTES
        ),
        0o644,
    )
    if (
        any(mode != _release_repair_expected_mode(path) for path, (_raw, mode) in values.items())
        or sum(len(raw) for raw, _mode in values.values()) != 11_436_098
        or hashlib.sha256(values["reports/m2-feasibility-v0.json"][0]).hexdigest()
        != _RELEASE_REPAIR_REPORT_SHA256
        or hashlib.sha256(values["docs/roadmap.md"][0]).hexdigest()
        != _RELEASE_REPAIR_ROADMAP_SHA256
        or hashlib.sha256(values["artifacts/gate8/evidence-source-v0.json"][0]).hexdigest()
        != "75adb99ea2a6d4ddc696be9a579d15563fd7c09f9be25c363cc866920d6608f2"
        or hashlib.sha256(values["artifacts/gate8/generated-evidence-v0.json"][0]).hexdigest()
        != "22dab47b8bb769c88ef49b1489abe3fb592288f2714c8dd2834719c14567e3cf"
        or hashlib.sha256(values["artifacts/gate8/linux-attestation-v0.json"][0]).hexdigest()
        != "eaf07de3598253bd657f92928d79af28ec4b7e637ffa621665b71cb44b1515e6"
        or hashlib.sha256(values["artifacts/gate8/selection-v0.json"][0]).hexdigest()
        != "af3cdaaa194e5a07aa81e1918fb7a394dfe6dfaff46a07defb0ffead61ef7baf"
    ):
        _fail("release-repair-prior", 2)
    _release_repair_manifest(values)
    return values


def _release_repair_archive_values(
    root: Path | None = None,
) -> dict[str, tuple[bytes, int]]:
    archive_root = _RELEASE_REPAIR_ARCHIVE if root is None else root
    observed, directories = _tree_files(archive_root)
    manifest_item = observed.get("archive-manifest-v0.json")
    if manifest_item is None or manifest_item[1] != 0o600:
        _fail("release-repair-archive")
    try:
        manifest = canonical_manifest.validate_canonical_manifest(manifest_item[0])
    except (ValueError, canonical_manifest.ManifestError) as error:
        raise Gate8CliError("release-repair-archive") from error
    rows = manifest.get("files")
    if (
        set(manifest) != {"files", "schema"}
        or manifest.get("schema") != _RELEASE_REPAIR_SCHEMA
        or type(rows) is not list
        or len(rows) != 71
        or hashlib.sha256(manifest_item[0]).hexdigest()
        != _RELEASE_REPAIR_MANIFEST_SHA256
    ):
        _fail("release-repair-archive")
    values: dict[str, tuple[bytes, int]] = {}
    paths: list[str] = []
    for row in rows:
        if (
            type(row) is not dict
            or set(row) != {"byte_length", "path", "sha256"}
            or type(row.get("path")) is not str
            or type(row.get("byte_length")) is not int
            or type(row.get("sha256")) is not str
        ):
            _fail("release-repair-archive")
        original = row["path"]
        stored = f"prior/{original}"
        item = observed.get(stored)
        if (
            item is None
            or item[1] != 0o600
            or len(item[0]) != row["byte_length"]
            or hashlib.sha256(item[0]).hexdigest() != row["sha256"]
            or original in values
        ):
            _fail("release-repair-archive")
        values[original] = (
            item[0],
            _release_repair_expected_mode(original),
        )
        paths.append(original)
    expected_files = {"archive-manifest-v0.json"} | {
        f"prior/{path}" for path in values
    }
    expected_directories = {
        parent.as_posix()
        for name in expected_files
        for parent in Path(name).parents
        if parent.as_posix() != "."
    }
    if (
        set(observed) != expected_files
        or directories != expected_directories
        or paths != sorted(paths, key=lambda path: path.encode("utf-8"))
        or _release_repair_manifest(values) != manifest_item[0]
    ):
        _fail("release-repair-archive")
    return values


def _create_release_repair_archive(
    values: Mapping[str, tuple[bytes, int]],
) -> None:
    if _RELEASE_REPAIR_ARCHIVE.exists() or _RELEASE_REPAIR_ARCHIVE.is_symlink():
        _fail("release-repair-archive-precondition", 2)
    parent = _RELEASE_REPAIR_ARCHIVE.parent
    _no_symlink_ancestors(parent, "release-repair-archive-parent")
    metadata = _lstat(parent, "release-repair-archive-parent")
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        _fail("release-repair-archive-parent", 2)
    manifest = _release_repair_manifest(values)
    stage = Path(tempfile.mkdtemp(prefix=".gate8-release-repair-", dir=parent))
    try:
        os.chmod(stage, 0o700)
        for original, (raw, _mode) in values.items():
            destination = stage / "prior" / original
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _write_fsynced(destination, raw, 0o600)
        _write_fsynced(stage / "archive-manifest-v0.json", manifest, 0o600)
        for directory in sorted(
            (path for path in stage.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            os.chmod(directory, 0o700)
            _fsync_directory(directory)
        _fsync_directory(stage)
        if _release_repair_archive_values(stage) != dict(values):
            _fail("release-repair-archive-stage")
        _rename_noreplace(stage, _RELEASE_REPAIR_ARCHIVE)
        _fsync_directory(parent)
    finally:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
    if _release_repair_archive_values() != dict(values):
        _fail("release-repair-archive-postcondition")


def _post_assembly_test_payload_sequence(
    values: Mapping[str, tuple[bytes, int]],
) -> str:
    if not isinstance(values, Mapping) or len(values) != 71:
        _fail("post-assembly-test-file-set", 2)
    paths = sorted(values, key=lambda path: path.encode("utf-8"))
    preimage = bytearray(_POST_ASSEMBLY_TEST_DOMAIN)
    preimage.extend(len(paths).to_bytes(8, "big"))
    for path in paths:
        raw, mode = values[path]
        try:
            path_raw = path.encode("utf-8")
        except UnicodeError as error:
            raise Gate8CliError("post-assembly-test-path", 2) from error
        if (
            not path
            or path.startswith("/")
            or "\\" in path
            or any(part in ("", ".", "..") for part in path.split("/"))
            or type(raw) is not bytes
            or not raw
            or mode not in (0o644, 0o755)
        ):
            _fail("post-assembly-test-file-set", 2)
        preimage.extend(len(path_raw).to_bytes(8, "big"))
        preimage.extend(path_raw)
        preimage.extend(len(raw).to_bytes(8, "big"))
        preimage.extend(hashlib.sha256(raw).digest())
    return hashlib.sha256(preimage).hexdigest()


def _post_assembly_test_manifest(
    values: Mapping[str, tuple[bytes, int]],
) -> bytes:
    rows = [
        {
            "byte_length": len(values[path][0]),
            "path": path,
            "sha256": hashlib.sha256(values[path][0]).hexdigest(),
        }
        for path in sorted(values, key=lambda item: item.encode("utf-8"))
    ]
    raw = canonical_manifest.serialize_manifest(
        {"files": rows, "schema": _POST_ASSEMBLY_TEST_SCHEMA}
    )
    if (
        len(raw) != 11_828
        or hashlib.sha256(raw).hexdigest()
        != _POST_ASSEMBLY_TEST_MANIFEST_SHA256
        or _post_assembly_test_payload_sequence(values)
        != _POST_ASSEMBLY_TEST_PAYLOAD_SHA256
    ):
        _fail("post-assembly-test-identity", 2)
    return raw


def _post_assembly_test_live_values() -> dict[str, tuple[bytes, int]]:
    tree, directories = _tree_files(_GATE8_ROOT)
    expected_directories = {
        parent.as_posix()
        for path in tree
        for parent in Path(path).parents
        if parent.as_posix() != "."
    }
    if len(tree) != 69 or directories != expected_directories:
        _fail("post-assembly-test-file-set", 2)
    values = {
        f"artifacts/gate8/{path}": item for path, item in tree.items()
    }
    values["reports/m2-feasibility-v0.json"] = (
        _regular_file(_REPORT_PATH, "post-assembly-test-report"),
        0o644,
    )
    values["docs/roadmap.md"] = (
        _regular_file(
            _ROADMAP_PATH, "post-assembly-test-roadmap", 16 * _MAX_FILE_BYTES
        ),
        0o644,
    )
    if (
        any(
            mode != _release_repair_expected_mode(path)
            for path, (_raw, mode) in values.items()
        )
        or sum(len(raw) for raw, _mode in values.values()) != 11_436_098
        or hashlib.sha256(values["reports/m2-feasibility-v0.json"][0]).hexdigest()
        != _POST_ASSEMBLY_TEST_REPORT_SHA256
        or hashlib.sha256(values["docs/roadmap.md"][0]).hexdigest()
        != _POST_ASSEMBLY_TEST_ROADMAP_SHA256
        or hashlib.sha256(
            values["artifacts/gate8/evidence-source-v0.json"][0]
        ).hexdigest()
        != "189734ba320682feccb88b34ae8d1a35fb36a295d253d599db385009b84186a6"
        or hashlib.sha256(
            values["artifacts/gate8/generated-evidence-v0.json"][0]
        ).hexdigest()
        != "16049609ac3465f138ad7c91e7eb69f2c3c190b67b83b3dcd233168c3b8225a1"
        or hashlib.sha256(
            values["artifacts/gate8/linux-attestation-v0.json"][0]
        ).hexdigest()
        != "1f3275d2bec434a38f94f4929e995c83e98780c5298f3a56198eae25f875191f"
        or hashlib.sha256(
            values["artifacts/gate8/selection-v0.json"][0]
        ).hexdigest()
        != "af3cdaaa194e5a07aa81e1918fb7a394dfe6dfaff46a07defb0ffead61ef7baf"
    ):
        _fail("post-assembly-test-prior", 2)
    _post_assembly_test_manifest(values)
    return values


def _post_assembly_test_archive_values(
    root: Path | None = None,
) -> dict[str, tuple[bytes, int]]:
    archive_root = _POST_ASSEMBLY_TEST_ARCHIVE if root is None else root
    observed, directories = _tree_files(archive_root)
    manifest_item = observed.get("archive-manifest-v0.json")
    if manifest_item is None or manifest_item[1] != 0o600:
        _fail("post-assembly-test-archive")
    try:
        manifest = canonical_manifest.validate_canonical_manifest(manifest_item[0])
    except (ValueError, canonical_manifest.ManifestError) as error:
        raise Gate8CliError("post-assembly-test-archive") from error
    rows = manifest.get("files")
    if (
        set(manifest) != {"files", "schema"}
        or manifest.get("schema") != _POST_ASSEMBLY_TEST_SCHEMA
        or type(rows) is not list
        or len(rows) != 71
        or hashlib.sha256(manifest_item[0]).hexdigest()
        != _POST_ASSEMBLY_TEST_MANIFEST_SHA256
    ):
        _fail("post-assembly-test-archive")
    values: dict[str, tuple[bytes, int]] = {}
    paths: list[str] = []
    for row in rows:
        if (
            type(row) is not dict
            or set(row) != {"byte_length", "path", "sha256"}
            or type(row.get("path")) is not str
            or type(row.get("byte_length")) is not int
            or type(row.get("sha256")) is not str
        ):
            _fail("post-assembly-test-archive")
        original = row["path"]
        stored = f"prior/{original}"
        item = observed.get(stored)
        if (
            item is None
            or item[1] != 0o600
            or len(item[0]) != row["byte_length"]
            or hashlib.sha256(item[0]).hexdigest() != row["sha256"]
            or original in values
        ):
            _fail("post-assembly-test-archive")
        values[original] = (
            item[0],
            _release_repair_expected_mode(original),
        )
        paths.append(original)
    expected_files = {"archive-manifest-v0.json"} | {
        f"prior/{path}" for path in values
    }
    expected_directories = {
        parent.as_posix()
        for name in expected_files
        for parent in Path(name).parents
        if parent.as_posix() != "."
    }
    if (
        set(observed) != expected_files
        or directories != expected_directories
        or paths != sorted(paths, key=lambda path: path.encode("utf-8"))
        or _post_assembly_test_manifest(values) != manifest_item[0]
    ):
        _fail("post-assembly-test-archive")
    return values


def _create_post_assembly_test_archive(
    values: Mapping[str, tuple[bytes, int]],
) -> None:
    if _POST_ASSEMBLY_TEST_ARCHIVE.exists() or _POST_ASSEMBLY_TEST_ARCHIVE.is_symlink():
        _fail("post-assembly-test-archive-precondition", 2)
    parent = _POST_ASSEMBLY_TEST_ARCHIVE.parent
    _no_symlink_ancestors(parent, "post-assembly-test-archive-parent")
    metadata = _lstat(parent, "post-assembly-test-archive-parent")
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        _fail("post-assembly-test-archive-parent", 2)
    manifest = _post_assembly_test_manifest(values)
    stage = Path(tempfile.mkdtemp(prefix=".gate8-post-assembly-test-", dir=parent))
    try:
        os.chmod(stage, 0o700)
        for original, (raw, _mode) in values.items():
            destination = stage / "prior" / original
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _write_fsynced(destination, raw, 0o600)
        _write_fsynced(stage / "archive-manifest-v0.json", manifest, 0o600)
        for directory in sorted(
            (path for path in stage.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            os.chmod(directory, 0o700)
            _fsync_directory(directory)
        _fsync_directory(stage)
        if _post_assembly_test_archive_values(stage) != dict(values):
            _fail("post-assembly-test-archive-stage")
        _rename_noreplace(stage, _POST_ASSEMBLY_TEST_ARCHIVE)
        _fsync_directory(parent)
    finally:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
    if _post_assembly_test_archive_values() != dict(values):
        _fail("post-assembly-test-archive-postcondition")


def _runtime_test_repair_payload_sequence(
    values: Mapping[str, tuple[bytes, int]],
) -> str:
    if not isinstance(values, Mapping) or len(values) != 71:
        _fail("runtime-test-repair-file-set", 2)
    paths = sorted(values, key=lambda path: path.encode("utf-8"))
    preimage = bytearray(_RUNTIME_TEST_REPAIR_DOMAIN)
    preimage.extend(len(paths).to_bytes(8, "big"))
    for path in paths:
        raw, mode = values[path]
        try:
            path_raw = path.encode("utf-8")
        except UnicodeError as error:
            raise Gate8CliError("runtime-test-repair-path", 2) from error
        if (
            not path
            or path.startswith("/")
            or "\\" in path
            or any(part in ("", ".", "..") for part in path.split("/"))
            or type(raw) is not bytes
            or not raw
            or mode not in (0o644, 0o755)
        ):
            _fail("runtime-test-repair-file-set", 2)
        preimage.extend(len(path_raw).to_bytes(8, "big"))
        preimage.extend(path_raw)
        preimage.extend(len(raw).to_bytes(8, "big"))
        preimage.extend(hashlib.sha256(raw).digest())
    return hashlib.sha256(preimage).hexdigest()


def _runtime_test_repair_manifest(
    values: Mapping[str, tuple[bytes, int]],
) -> bytes:
    rows = [
        {
            "byte_length": len(values[path][0]),
            "path": path,
            "sha256": hashlib.sha256(values[path][0]).hexdigest(),
        }
        for path in sorted(values, key=lambda item: item.encode("utf-8"))
    ]
    raw = canonical_manifest.serialize_manifest(
        {"files": rows, "schema": _RUNTIME_TEST_REPAIR_SCHEMA}
    )
    if (
        len(raw) != 11_836
        or hashlib.sha256(raw).hexdigest()
        != _RUNTIME_TEST_REPAIR_MANIFEST_SHA256
        or _runtime_test_repair_payload_sequence(values)
        != _RUNTIME_TEST_REPAIR_PAYLOAD_SHA256
    ):
        _fail("runtime-test-repair-identity", 2)
    return raw


def _runtime_test_repair_live_values() -> dict[str, tuple[bytes, int]]:
    tree, directories = _tree_files(_GATE8_ROOT)
    expected_directories = {
        parent.as_posix()
        for path in tree
        for parent in Path(path).parents
        if parent.as_posix() != "."
    }
    if len(tree) != 69 or directories != expected_directories:
        _fail("runtime-test-repair-file-set", 2)
    values = {
        f"artifacts/gate8/{path}": item for path, item in tree.items()
    }
    values["reports/m2-feasibility-v0.json"] = (
        _regular_file(_REPORT_PATH, "runtime-test-repair-report"),
        0o644,
    )
    values["docs/roadmap.md"] = (
        _regular_file(
            _ROADMAP_PATH, "runtime-test-repair-roadmap", 16 * _MAX_FILE_BYTES
        ),
        0o644,
    )
    exact_hashes = {
        "reports/m2-feasibility-v0.json": _RUNTIME_TEST_REPAIR_REPORT_SHA256,
        "docs/roadmap.md": _RUNTIME_TEST_REPAIR_ROADMAP_SHA256,
        "artifacts/gate8/evidence-source-v0.json": "0d743b09c0a180e92b0f12fe9cfeb213b59ce30d4748256ef40b2420aaf8dc3b",
        "artifacts/gate8/generated-evidence-v0.json": "ac5a52d302665c603298c8821c28d35b0fca9d461d0e1ed80e081d3d785795c5",
        "artifacts/gate8/linux-attestation-v0.json": "d3ca34196d8235aade12e7fe0d140b966cb4fa773e2d0d0a1ff1fa730b93baca",
        "artifacts/gate8/selection-v0.json": "af3cdaaa194e5a07aa81e1918fb7a394dfe6dfaff46a07defb0ffead61ef7baf",
    }
    if (
        any(
            mode != _release_repair_expected_mode(path)
            for path, (_raw, mode) in values.items()
        )
        or sum(len(raw) for raw, _mode in values.values()) != 11_436_099
        or any(
            hashlib.sha256(values[path][0]).hexdigest() != expected
            for path, expected in exact_hashes.items()
        )
    ):
        _fail("runtime-test-repair-prior", 2)
    _runtime_test_repair_manifest(values)
    return values


def _runtime_test_repair_archive_values(
    root: Path | None = None,
) -> dict[str, tuple[bytes, int]]:
    archive_root = _RUNTIME_TEST_REPAIR_ARCHIVE if root is None else root
    observed, directories = _tree_files(archive_root)
    manifest_item = observed.get("archive-manifest-v0.json")
    if manifest_item is None or manifest_item[1] != 0o600:
        _fail("runtime-test-repair-archive")
    try:
        manifest = canonical_manifest.validate_canonical_manifest(manifest_item[0])
    except (ValueError, canonical_manifest.ManifestError) as error:
        raise Gate8CliError("runtime-test-repair-archive") from error
    rows = manifest.get("files")
    if (
        set(manifest) != {"files", "schema"}
        or manifest.get("schema") != _RUNTIME_TEST_REPAIR_SCHEMA
        or type(rows) is not list
        or len(rows) != 71
        or hashlib.sha256(manifest_item[0]).hexdigest()
        != _RUNTIME_TEST_REPAIR_MANIFEST_SHA256
    ):
        _fail("runtime-test-repair-archive")
    values: dict[str, tuple[bytes, int]] = {}
    paths: list[str] = []
    for row in rows:
        if (
            type(row) is not dict
            or set(row) != {"byte_length", "path", "sha256"}
            or type(row.get("path")) is not str
            or type(row.get("byte_length")) is not int
            or type(row.get("sha256")) is not str
        ):
            _fail("runtime-test-repair-archive")
        original = row["path"]
        stored = f"prior/{original}"
        item = observed.get(stored)
        if (
            item is None
            or item[1] != 0o600
            or len(item[0]) != row["byte_length"]
            or hashlib.sha256(item[0]).hexdigest() != row["sha256"]
            or original in values
        ):
            _fail("runtime-test-repair-archive")
        values[original] = (
            item[0],
            _release_repair_expected_mode(original),
        )
        paths.append(original)
    expected_files = {"archive-manifest-v0.json"} | {
        f"prior/{path}" for path in values
    }
    expected_directories = {
        parent.as_posix()
        for name in expected_files
        for parent in Path(name).parents
        if parent.as_posix() != "."
    }
    if (
        set(observed) != expected_files
        or directories != expected_directories
        or paths != sorted(paths, key=lambda path: path.encode("utf-8"))
        or _runtime_test_repair_manifest(values) != manifest_item[0]
    ):
        _fail("runtime-test-repair-archive")
    return values


def _create_runtime_test_repair_archive(
    values: Mapping[str, tuple[bytes, int]],
) -> None:
    if (
        _RUNTIME_TEST_REPAIR_ARCHIVE.exists()
        or _RUNTIME_TEST_REPAIR_ARCHIVE.is_symlink()
    ):
        _fail("runtime-test-repair-archive-precondition", 2)
    parent = _RUNTIME_TEST_REPAIR_ARCHIVE.parent
    _no_symlink_ancestors(parent, "runtime-test-repair-archive-parent")
    metadata = _lstat(parent, "runtime-test-repair-archive-parent")
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        _fail("runtime-test-repair-archive-parent", 2)
    manifest = _runtime_test_repair_manifest(values)
    stage = Path(
        tempfile.mkdtemp(prefix=".gate8-runtime-test-repair-", dir=parent)
    )
    try:
        os.chmod(stage, 0o700)
        for original, (raw, _mode) in values.items():
            destination = stage / "prior" / original
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _write_fsynced(destination, raw, 0o600)
        _write_fsynced(stage / "archive-manifest-v0.json", manifest, 0o600)
        for directory in sorted(
            (path for path in stage.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            os.chmod(directory, 0o700)
            _fsync_directory(directory)
        _fsync_directory(stage)
        if _runtime_test_repair_archive_values(stage) != dict(values):
            _fail("runtime-test-repair-archive-stage")
        _rename_noreplace(stage, _RUNTIME_TEST_REPAIR_ARCHIVE)
        _fsync_directory(parent)
    finally:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
    if _runtime_test_repair_archive_values() != dict(values):
        _fail("runtime-test-repair-archive-postcondition")


def _clean_snapshot_test_repair_payload_sequence(
    values: Mapping[str, tuple[bytes, int]],
) -> str:
    if not isinstance(values, Mapping) or len(values) != 71:
        _fail("clean-snapshot-test-repair-file-set", 2)
    paths = sorted(values, key=lambda path: path.encode("utf-8"))
    preimage = bytearray(_CLEAN_SNAPSHOT_TEST_REPAIR_DOMAIN)
    preimage.extend(len(paths).to_bytes(8, "big"))
    for path in paths:
        raw, mode = values[path]
        try:
            path_raw = path.encode("utf-8")
        except UnicodeError as error:
            raise Gate8CliError(
                "clean-snapshot-test-repair-path", 2
            ) from error
        if (
            not path
            or path.startswith("/")
            or "\\" in path
            or any(part in ("", ".", "..") for part in path.split("/"))
            or type(raw) is not bytes
            or not raw
            or mode not in (0o644, 0o755)
        ):
            _fail("clean-snapshot-test-repair-file-set", 2)
        preimage.extend(len(path_raw).to_bytes(8, "big"))
        preimage.extend(path_raw)
        preimage.extend(len(raw).to_bytes(8, "big"))
        preimage.extend(hashlib.sha256(raw).digest())
    return hashlib.sha256(preimage).hexdigest()


def _clean_snapshot_test_repair_manifest(
    values: Mapping[str, tuple[bytes, int]],
) -> bytes:
    rows = [
        {
            "byte_length": len(values[path][0]),
            "path": path,
            "sha256": hashlib.sha256(values[path][0]).hexdigest(),
        }
        for path in sorted(values, key=lambda item: item.encode("utf-8"))
    ]
    raw = canonical_manifest.serialize_manifest(
        {"files": rows, "schema": _CLEAN_SNAPSHOT_TEST_REPAIR_SCHEMA}
    )
    if (
        len(raw) != 11_838
        or hashlib.sha256(raw).hexdigest()
        != _CLEAN_SNAPSHOT_TEST_REPAIR_MANIFEST_SHA256
        or _clean_snapshot_test_repair_payload_sequence(values)
        != _CLEAN_SNAPSHOT_TEST_REPAIR_PAYLOAD_SHA256
    ):
        _fail("clean-snapshot-test-repair-identity", 2)
    return raw


def _clean_snapshot_test_repair_live_values() -> dict[str, tuple[bytes, int]]:
    tree, directories = _tree_files(_GATE8_ROOT)
    expected_directories = {
        parent.as_posix()
        for path in tree
        for parent in Path(path).parents
        if parent.as_posix() != "."
    }
    if len(tree) != 69 or directories != expected_directories:
        _fail("clean-snapshot-test-repair-file-set", 2)
    values = {
        f"artifacts/gate8/{path}": item for path, item in tree.items()
    }
    values["reports/m2-feasibility-v0.json"] = (
        _regular_file(_REPORT_PATH, "clean-snapshot-test-repair-report"),
        0o644,
    )
    values["docs/roadmap.md"] = (
        _regular_file(
            _ROADMAP_PATH,
            "clean-snapshot-test-repair-roadmap",
            16 * _MAX_FILE_BYTES,
        ),
        0o644,
    )
    exact_hashes = {
        "reports/m2-feasibility-v0.json": _CLEAN_SNAPSHOT_TEST_REPAIR_REPORT_SHA256,
        "docs/roadmap.md": _CLEAN_SNAPSHOT_TEST_REPAIR_ROADMAP_SHA256,
        "artifacts/gate8/evidence-source-v0.json": "1a54cd22226e56587f200741b74e344e71ba0baceec778da86f8da7e503195b0",
        "artifacts/gate8/generated-evidence-v0.json": "c2ffcb91e465be35461fdcb9f20b3ee86528ed2bb4fc0218895435131142152b",
        "artifacts/gate8/linux-attestation-v0.json": "d4893a6830a7e16566189e44f54575fc302cf30b400659af9ce313c9c1aa1074",
        "artifacts/gate8/selection-v0.json": "af3cdaaa194e5a07aa81e1918fb7a394dfe6dfaff46a07defb0ffead61ef7baf",
    }
    if (
        any(
            mode != _release_repair_expected_mode(path)
            for path, (_raw, mode) in values.items()
        )
        or sum(len(raw) for raw, _mode in values.values()) != 11_436_099
        or any(
            hashlib.sha256(values[path][0]).hexdigest() != expected
            for path, expected in exact_hashes.items()
        )
    ):
        _fail("clean-snapshot-test-repair-prior", 2)
    _clean_snapshot_test_repair_manifest(values)
    return values


def _clean_snapshot_test_repair_archive_values(
    root: Path | None = None,
) -> dict[str, tuple[bytes, int]]:
    archive_root = (
        _CLEAN_SNAPSHOT_TEST_REPAIR_ARCHIVE if root is None else root
    )
    observed, directories = _tree_files(archive_root)
    manifest_item = observed.get("archive-manifest-v0.json")
    if manifest_item is None or manifest_item[1] != 0o600:
        _fail("clean-snapshot-test-repair-archive")
    try:
        manifest = canonical_manifest.validate_canonical_manifest(manifest_item[0])
    except (ValueError, canonical_manifest.ManifestError) as error:
        raise Gate8CliError("clean-snapshot-test-repair-archive") from error
    rows = manifest.get("files")
    if (
        set(manifest) != {"files", "schema"}
        or manifest.get("schema") != _CLEAN_SNAPSHOT_TEST_REPAIR_SCHEMA
        or type(rows) is not list
        or len(rows) != 71
        or hashlib.sha256(manifest_item[0]).hexdigest()
        != _CLEAN_SNAPSHOT_TEST_REPAIR_MANIFEST_SHA256
    ):
        _fail("clean-snapshot-test-repair-archive")
    values: dict[str, tuple[bytes, int]] = {}
    paths: list[str] = []
    for row in rows:
        if (
            type(row) is not dict
            or set(row) != {"byte_length", "path", "sha256"}
            or type(row.get("path")) is not str
            or type(row.get("byte_length")) is not int
            or type(row.get("sha256")) is not str
        ):
            _fail("clean-snapshot-test-repair-archive")
        original = row["path"]
        stored = f"prior/{original}"
        item = observed.get(stored)
        if (
            item is None
            or item[1] != 0o600
            or len(item[0]) != row["byte_length"]
            or hashlib.sha256(item[0]).hexdigest() != row["sha256"]
            or original in values
        ):
            _fail("clean-snapshot-test-repair-archive")
        values[original] = (
            item[0],
            _release_repair_expected_mode(original),
        )
        paths.append(original)
    expected_files = {"archive-manifest-v0.json"} | {
        f"prior/{path}" for path in values
    }
    expected_directories = {
        parent.as_posix()
        for name in expected_files
        for parent in Path(name).parents
        if parent.as_posix() != "."
    }
    if (
        set(observed) != expected_files
        or directories != expected_directories
        or paths != sorted(paths, key=lambda path: path.encode("utf-8"))
        or _clean_snapshot_test_repair_manifest(values) != manifest_item[0]
    ):
        _fail("clean-snapshot-test-repair-archive")
    return values


def _create_clean_snapshot_test_repair_archive(
    values: Mapping[str, tuple[bytes, int]],
) -> None:
    if (
        _CLEAN_SNAPSHOT_TEST_REPAIR_ARCHIVE.exists()
        or _CLEAN_SNAPSHOT_TEST_REPAIR_ARCHIVE.is_symlink()
    ):
        _fail("clean-snapshot-test-repair-archive-precondition", 2)
    parent = _CLEAN_SNAPSHOT_TEST_REPAIR_ARCHIVE.parent
    _no_symlink_ancestors(parent, "clean-snapshot-test-repair-archive-parent")
    metadata = _lstat(parent, "clean-snapshot-test-repair-archive-parent")
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        _fail("clean-snapshot-test-repair-archive-parent", 2)
    manifest = _clean_snapshot_test_repair_manifest(values)
    stage = Path(
        tempfile.mkdtemp(
            prefix=".gate8-clean-snapshot-test-repair-", dir=parent
        )
    )
    try:
        os.chmod(stage, 0o700)
        for original, (raw, _mode) in values.items():
            destination = stage / "prior" / original
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _write_fsynced(destination, raw, 0o600)
        _write_fsynced(stage / "archive-manifest-v0.json", manifest, 0o600)
        for directory in sorted(
            (path for path in stage.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            os.chmod(directory, 0o700)
            _fsync_directory(directory)
        _fsync_directory(stage)
        if _clean_snapshot_test_repair_archive_values(stage) != dict(values):
            _fail("clean-snapshot-test-repair-archive-stage")
        _rename_noreplace(stage, _CLEAN_SNAPSHOT_TEST_REPAIR_ARCHIVE)
        _fsync_directory(parent)
    finally:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
    if _clean_snapshot_test_repair_archive_values() != dict(values):
        _fail("clean-snapshot-test-repair-archive-postcondition")


def _provenance_input_repair_payload_sequence(
    values: Mapping[str, tuple[bytes, int]],
) -> str:
    if not isinstance(values, Mapping) or len(values) != 71:
        _fail("provenance-input-repair-file-set", 2)
    paths = sorted(values, key=lambda path: path.encode("utf-8"))
    preimage = bytearray(_PROVENANCE_INPUT_REPAIR_DOMAIN)
    preimage.extend(len(paths).to_bytes(8, "big"))
    for path in paths:
        raw, mode = values[path]
        try:
            path_raw = path.encode("utf-8")
        except UnicodeError as error:
            raise Gate8CliError("provenance-input-repair-path", 2) from error
        if (
            not path
            or path.startswith("/")
            or "\\" in path
            or any(part in ("", ".", "..") for part in path.split("/"))
            or type(raw) is not bytes
            or not raw
            or mode not in (0o644, 0o755)
        ):
            _fail("provenance-input-repair-file-set", 2)
        preimage.extend(len(path_raw).to_bytes(8, "big"))
        preimage.extend(path_raw)
        preimage.extend(len(raw).to_bytes(8, "big"))
        preimage.extend(hashlib.sha256(raw).digest())
    return hashlib.sha256(preimage).hexdigest()


def _provenance_input_repair_manifest(
    values: Mapping[str, tuple[bytes, int]],
) -> bytes:
    rows = [
        {
            "byte_length": len(values[path][0]),
            "path": path,
            "sha256": hashlib.sha256(values[path][0]).hexdigest(),
        }
        for path in sorted(values, key=lambda item: item.encode("utf-8"))
    ]
    raw = canonical_manifest.serialize_manifest(
        {"files": rows, "schema": _PROVENANCE_INPUT_REPAIR_SCHEMA}
    )
    if (
        len(raw) != 11_840
        or hashlib.sha256(raw).hexdigest()
        != _PROVENANCE_INPUT_REPAIR_MANIFEST_SHA256
        or _provenance_input_repair_payload_sequence(values)
        != _PROVENANCE_INPUT_REPAIR_PAYLOAD_SHA256
    ):
        _fail("provenance-input-repair-identity", 2)
    return raw


def _provenance_input_repair_live_values() -> dict[str, tuple[bytes, int]]:
    tree, directories = _tree_files(_GATE8_ROOT)
    expected_directories = {
        parent.as_posix()
        for path in tree
        for parent in Path(path).parents
        if parent.as_posix() != "."
    }
    if len(tree) != 69 or directories != expected_directories:
        _fail("provenance-input-repair-file-set", 2)
    values = {
        f"artifacts/gate8/{path}": item for path, item in tree.items()
    }
    values["reports/m2-feasibility-v0.json"] = (
        _regular_file(_REPORT_PATH, "provenance-input-repair-report"),
        0o644,
    )
    values["docs/roadmap.md"] = (
        _regular_file(
            _ROADMAP_PATH,
            "provenance-input-repair-roadmap",
            16 * _MAX_FILE_BYTES,
        ),
        0o644,
    )
    exact_hashes = {
        "reports/m2-feasibility-v0.json": _PROVENANCE_INPUT_REPAIR_REPORT_SHA256,
        "docs/roadmap.md": _PROVENANCE_INPUT_REPAIR_ROADMAP_SHA256,
        "artifacts/gate8/evidence-source-v0.json": "19a81497c591b107eafd4db86445803c908a517d4a925880d44a8686b5f044a4",
        "artifacts/gate8/generated-evidence-v0.json": "ac4a24da19e0bedf462c2481865e30ffb4af47b7d5226b44e6973d518ccd9f94",
        "artifacts/gate8/linux-attestation-v0.json": "ea046fbca0ab10718c65f6e0d3614375589965e5523f4ec180d4eb48c2a4717f",
        "artifacts/gate8/selection-v0.json": "af3cdaaa194e5a07aa81e1918fb7a394dfe6dfaff46a07defb0ffead61ef7baf",
    }
    if (
        any(
            mode != _release_repair_expected_mode(path)
            for path, (_raw, mode) in values.items()
        )
        or sum(len(raw) for raw, _mode in values.values()) != 11_436_099
        or any(
            hashlib.sha256(values[path][0]).hexdigest() != expected
            for path, expected in exact_hashes.items()
        )
    ):
        _fail("provenance-input-repair-prior", 2)
    _provenance_input_repair_manifest(values)
    return values


def _provenance_input_repair_archive_values(
    root: Path | None = None,
) -> dict[str, tuple[bytes, int]]:
    archive_root = _PROVENANCE_INPUT_REPAIR_ARCHIVE if root is None else root
    observed, directories = _tree_files(archive_root)
    manifest_item = observed.get("archive-manifest-v0.json")
    if manifest_item is None or manifest_item[1] != 0o600:
        _fail("provenance-input-repair-archive")
    try:
        manifest = canonical_manifest.validate_canonical_manifest(manifest_item[0])
    except (ValueError, canonical_manifest.ManifestError) as error:
        raise Gate8CliError("provenance-input-repair-archive") from error
    rows = manifest.get("files")
    if (
        set(manifest) != {"files", "schema"}
        or manifest.get("schema") != _PROVENANCE_INPUT_REPAIR_SCHEMA
        or type(rows) is not list
        or len(rows) != 71
        or hashlib.sha256(manifest_item[0]).hexdigest()
        != _PROVENANCE_INPUT_REPAIR_MANIFEST_SHA256
    ):
        _fail("provenance-input-repair-archive")
    values: dict[str, tuple[bytes, int]] = {}
    paths: list[str] = []
    for row in rows:
        if (
            type(row) is not dict
            or set(row) != {"byte_length", "path", "sha256"}
            or type(row.get("path")) is not str
            or type(row.get("byte_length")) is not int
            or type(row.get("sha256")) is not str
        ):
            _fail("provenance-input-repair-archive")
        original = row["path"]
        stored = f"prior/{original}"
        item = observed.get(stored)
        if (
            item is None
            or item[1] != 0o600
            or len(item[0]) != row["byte_length"]
            or hashlib.sha256(item[0]).hexdigest() != row["sha256"]
            or original in values
        ):
            _fail("provenance-input-repair-archive")
        values[original] = (
            item[0],
            _release_repair_expected_mode(original),
        )
        paths.append(original)
    expected_files = {"archive-manifest-v0.json"} | {
        f"prior/{path}" for path in values
    }
    expected_directories = {
        parent.as_posix()
        for name in expected_files
        for parent in Path(name).parents
        if parent.as_posix() != "."
    }
    if (
        set(observed) != expected_files
        or directories != expected_directories
        or paths != sorted(paths, key=lambda path: path.encode("utf-8"))
        or _provenance_input_repair_manifest(values) != manifest_item[0]
    ):
        _fail("provenance-input-repair-archive")
    return values


def _create_provenance_input_repair_archive(
    values: Mapping[str, tuple[bytes, int]],
) -> None:
    if (
        _PROVENANCE_INPUT_REPAIR_ARCHIVE.exists()
        or _PROVENANCE_INPUT_REPAIR_ARCHIVE.is_symlink()
    ):
        _fail("provenance-input-repair-archive-precondition", 2)
    parent = _PROVENANCE_INPUT_REPAIR_ARCHIVE.parent
    _no_symlink_ancestors(parent, "provenance-input-repair-archive-parent")
    metadata = _lstat(parent, "provenance-input-repair-archive-parent")
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        _fail("provenance-input-repair-archive-parent", 2)
    manifest = _provenance_input_repair_manifest(values)
    stage = Path(
        tempfile.mkdtemp(prefix=".gate8-provenance-input-repair-", dir=parent)
    )
    try:
        os.chmod(stage, 0o700)
        for original, (raw, _mode) in values.items():
            destination = stage / "prior" / original
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _write_fsynced(destination, raw, 0o600)
        _write_fsynced(stage / "archive-manifest-v0.json", manifest, 0o600)
        for directory in sorted(
            (path for path in stage.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            os.chmod(directory, 0o700)
            _fsync_directory(directory)
        _fsync_directory(stage)
        if _provenance_input_repair_archive_values(stage) != dict(values):
            _fail("provenance-input-repair-archive-stage")
        _rename_noreplace(stage, _PROVENANCE_INPUT_REPAIR_ARCHIVE)
        _fsync_directory(parent)
    finally:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
    if _provenance_input_repair_archive_values() != dict(values):
        _fail("provenance-input-repair-archive-postcondition")


def _provenance_fixture_repair_payload_sequence(
    values: Mapping[str, tuple[bytes, int]],
) -> str:
    if not isinstance(values, Mapping) or len(values) != 71:
        _fail("provenance-fixture-repair-file-set", 2)
    paths = sorted(values, key=lambda path: path.encode("utf-8"))
    preimage = bytearray(_PROVENANCE_FIXTURE_REPAIR_DOMAIN)
    preimage.extend(len(paths).to_bytes(8, "big"))
    for path in paths:
        raw, mode = values[path]
        try:
            path_raw = path.encode("utf-8")
        except UnicodeError as error:
            raise Gate8CliError("provenance-fixture-repair-path", 2) from error
        if (
            not path
            or path.startswith("/")
            or "\\" in path
            or any(part in ("", ".", "..") for part in path.split("/"))
            or type(raw) is not bytes
            or not raw
            or mode not in (0o644, 0o755)
        ):
            _fail("provenance-fixture-repair-file-set", 2)
        preimage.extend(len(path_raw).to_bytes(8, "big"))
        preimage.extend(path_raw)
        preimage.extend(len(raw).to_bytes(8, "big"))
        preimage.extend(hashlib.sha256(raw).digest())
    return hashlib.sha256(preimage).hexdigest()


def _provenance_fixture_repair_manifest(
    values: Mapping[str, tuple[bytes, int]],
) -> bytes:
    rows = [
        {
            "byte_length": len(values[path][0]),
            "path": path,
            "sha256": hashlib.sha256(values[path][0]).hexdigest(),
        }
        for path in sorted(values, key=lambda item: item.encode("utf-8"))
    ]
    raw = canonical_manifest.serialize_manifest(
        {"files": rows, "schema": _PROVENANCE_FIXTURE_REPAIR_SCHEMA}
    )
    if (
        len(raw) != 11_826
        or hashlib.sha256(raw).hexdigest()
        != _PROVENANCE_FIXTURE_REPAIR_MANIFEST_SHA256
        or _provenance_fixture_repair_payload_sequence(values)
        != _PROVENANCE_FIXTURE_REPAIR_PAYLOAD_SHA256
    ):
        _fail("provenance-fixture-repair-identity", 2)
    return raw


def _provenance_fixture_repair_live_values() -> dict[str, tuple[bytes, int]]:
    tree, directories = _tree_files(_GATE8_ROOT)
    expected_directories = {
        parent.as_posix()
        for path in tree
        for parent in Path(path).parents
        if parent.as_posix() != "."
    }
    if len(tree) != 69 or directories != expected_directories:
        _fail("provenance-fixture-repair-file-set", 2)
    values = {
        f"artifacts/gate8/{path}": item for path, item in tree.items()
    }
    values["reports/m2-feasibility-v0.json"] = (
        _regular_file(_REPORT_PATH, "provenance-fixture-repair-report"),
        0o644,
    )
    values["docs/roadmap.md"] = (
        _regular_file(
            _ROADMAP_PATH,
            "provenance-fixture-repair-roadmap",
            16 * _MAX_FILE_BYTES,
        ),
        0o644,
    )
    exact_hashes = {
        "reports/m2-feasibility-v0.json": _PROVENANCE_FIXTURE_REPAIR_REPORT_SHA256,
        "docs/roadmap.md": _PROVENANCE_FIXTURE_REPAIR_ROADMAP_SHA256,
        "artifacts/gate8/evidence-source-v0.json": "32d5464337eee49a3944a9e846d72268f5006f034a8de408b7f2247974551746",
        "artifacts/gate8/generated-evidence-v0.json": "0f314946d8ccb104513bea6cfc7356bd240f2c3f530f7db7c6e6e8121f1d3659",
        "artifacts/gate8/linux-attestation-v0.json": "dea3ad41b42ca8c5562eba73b0755cce67824edd7b5b54a6ef08048f5212e431",
        "artifacts/gate8/selection-v0.json": "af3cdaaa194e5a07aa81e1918fb7a394dfe6dfaff46a07defb0ffead61ef7baf",
    }
    if (
        any(
            mode != _release_repair_expected_mode(path)
            for path, (_raw, mode) in values.items()
        )
        or sum(len(raw) for raw, _mode in values.values()) != 11_436_100
        or any(
            hashlib.sha256(values[path][0]).hexdigest() != expected
            for path, expected in exact_hashes.items()
        )
    ):
        _fail("provenance-fixture-repair-prior", 2)
    _provenance_fixture_repair_manifest(values)
    return values


def _provenance_fixture_repair_archive_values(
    root: Path | None = None,
) -> dict[str, tuple[bytes, int]]:
    archive_root = _PROVENANCE_FIXTURE_REPAIR_ARCHIVE if root is None else root
    observed, directories = _tree_files(archive_root)
    manifest_item = observed.get("archive-manifest-v0.json")
    if manifest_item is None or manifest_item[1] != 0o600:
        _fail("provenance-fixture-repair-archive")
    try:
        manifest = canonical_manifest.validate_canonical_manifest(manifest_item[0])
    except (ValueError, canonical_manifest.ManifestError) as error:
        raise Gate8CliError("provenance-fixture-repair-archive") from error
    rows = manifest.get("files")
    if (
        set(manifest) != {"files", "schema"}
        or manifest.get("schema") != _PROVENANCE_FIXTURE_REPAIR_SCHEMA
        or type(rows) is not list
        or len(rows) != 71
        or hashlib.sha256(manifest_item[0]).hexdigest()
        != _PROVENANCE_FIXTURE_REPAIR_MANIFEST_SHA256
    ):
        _fail("provenance-fixture-repair-archive")
    values: dict[str, tuple[bytes, int]] = {}
    paths: list[str] = []
    for row in rows:
        if (
            type(row) is not dict
            or set(row) != {"byte_length", "path", "sha256"}
            or type(row.get("path")) is not str
            or type(row.get("byte_length")) is not int
            or type(row.get("sha256")) is not str
        ):
            _fail("provenance-fixture-repair-archive")
        original = row["path"]
        stored = f"prior/{original}"
        item = observed.get(stored)
        if (
            item is None
            or item[1] != 0o600
            or len(item[0]) != row["byte_length"]
            or hashlib.sha256(item[0]).hexdigest() != row["sha256"]
            or original in values
        ):
            _fail("provenance-fixture-repair-archive")
        values[original] = (
            item[0],
            _release_repair_expected_mode(original),
        )
        paths.append(original)
    expected_files = {"archive-manifest-v0.json"} | {
        f"prior/{path}" for path in values
    }
    expected_directories = {
        parent.as_posix()
        for name in expected_files
        for parent in Path(name).parents
        if parent.as_posix() != "."
    }
    if (
        set(observed) != expected_files
        or directories != expected_directories
        or paths != sorted(paths, key=lambda path: path.encode("utf-8"))
        or _provenance_fixture_repair_manifest(values) != manifest_item[0]
    ):
        _fail("provenance-fixture-repair-archive")
    return values


def _create_provenance_fixture_repair_archive(
    values: Mapping[str, tuple[bytes, int]],
) -> None:
    if (
        _PROVENANCE_FIXTURE_REPAIR_ARCHIVE.exists()
        or _PROVENANCE_FIXTURE_REPAIR_ARCHIVE.is_symlink()
    ):
        _fail("provenance-fixture-repair-archive-precondition", 2)
    parent = _PROVENANCE_FIXTURE_REPAIR_ARCHIVE.parent
    _no_symlink_ancestors(parent, "provenance-fixture-repair-archive-parent")
    metadata = _lstat(parent, "provenance-fixture-repair-archive-parent")
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        _fail("provenance-fixture-repair-archive-parent", 2)
    manifest = _provenance_fixture_repair_manifest(values)
    stage = Path(
        tempfile.mkdtemp(prefix=".gate8-provenance-fixture-repair-", dir=parent)
    )
    try:
        os.chmod(stage, 0o700)
        for original, (raw, _mode) in values.items():
            destination = stage / "prior" / original
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _write_fsynced(destination, raw, 0o600)
        _write_fsynced(stage / "archive-manifest-v0.json", manifest, 0o600)
        for directory in sorted(
            (path for path in stage.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            os.chmod(directory, 0o700)
            _fsync_directory(directory)
        _fsync_directory(stage)
        if _provenance_fixture_repair_archive_values(stage) != dict(values):
            _fail("provenance-fixture-repair-archive-stage")
        _rename_noreplace(stage, _PROVENANCE_FIXTURE_REPAIR_ARCHIVE)
        _fsync_directory(parent)
    finally:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
    if _provenance_fixture_repair_archive_values() != dict(values):
        _fail("provenance-fixture-repair-archive-postcondition")


def _render_reopened_roadmap(prior: bytes) -> bytes:
    replacements = (
        (b"| Roadmap revision | 9 |\n", b"| Roadmap revision | 10 |\n"),
        (b"| Last updated | 2026-08-22 |\n", b"| Last updated | 2026-08-30 |\n"),
        (b"| Project state | Candidate ready |\n", b"| Project state | In progress |\n"),
        (
            b"| M2 \xe2\x80\x94 Full-carrier bootstrap and transport feasibility | "
            b"Candidate ready \xe2\x80\x94 independent validation pending | ",
            b"| M2 \xe2\x80\x94 Full-carrier bootstrap and transport feasibility | "
            b"In progress | ",
        ),
        (
            b"The candidate passes gates 1\xe2\x80\x938 with provisional preferred "
            b"candidate `eh72-hier-r5-r2-r1-crc32c-v0` and tracked report "
            b"SHA-256 `98e9c71997604ec3f57ad0dba09e24ecbf32016575973bb73a1bc28b57f417e3`; "
            b"automated native and clean-Linux evidence passes, while technical "
            b"and learner validation remains pending.",
            b"Revision 10 preserves the R3 candidate and Gates 1\xe2\x80\x937 while "
            b"reopening only Gate 8 for the acquired Linux verifier provenance "
            b"refresh; no current Candidate-ready claim is admitted.",
        ),
    )
    result = prior
    for old, new in replacements:
        if result.count(old) != 1 or new in result:
            _fail("refresh-roadmap-precondition", 2)
        result = result.replace(old, new, 1)
    if (
        len(result) != 189_838
        or hashlib.sha256(result).hexdigest() != _PENDING_ROADMAP_SHA256
    ):
        _fail("refresh-roadmap-projection", 2)
    return result


def _admit_observed_verifier(
    policy_raw: bytes, receipt_raw: bytes
) -> dict[str, str]:
    try:
        values = m2_gate8.parse_linux_acquisition_receipt(
            receipt_raw, policy_raw
        )
    except m2_gate8.Gate8Error as error:
        raise Gate8CliError("refresh-acquisition", 2) from error
    dockerfile = _regular_file(
        ROOT / "tools/linux/Dockerfile", "refresh-dockerfile"
    )
    if hashlib.sha256(dockerfile).hexdigest() != values["dockerfile_sha256"]:
        _fail("refresh-observed-image", 2)
    template = "\n".join(
        (
            "{{.Id}}",
            "{{.Os}}/{{.Architecture}}",
            '{{index .Config.Labels "org.golden-board.contract"}}',
            '{{index .Config.Labels "org.golden-board.base"}}',
        )
    )
    try:
        process = subprocess.Popen(
            (
                "docker",
                "image",
                "inspect",
                "--format",
                template,
                values["image"],
            ),
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if process.stdout is None:
            _fail("refresh-observed-image", 2)
        descriptor = process.stdout.fileno()
        selector = selectors.DefaultSelector()
        selector.register(descriptor, selectors.EVENT_READ)
        deadline = time.monotonic() + 30
        output = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(process.args, 30)
            if not selector.select(remaining):
                raise subprocess.TimeoutExpired(process.args, 30)
            chunk = os.read(descriptor, min(4_097 - len(output), 4_097))
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > 4_096:
                _fail("refresh-observed-image", 2)
        selector.close()
        return_code = process.wait(max(0.001, deadline - time.monotonic()))
    except Gate8CliError:
        try:
            process.kill()
            process.wait(timeout=5)
        except (NameError, OSError, subprocess.SubprocessError):
            pass
        raise
    except (OSError, subprocess.SubprocessError) as error:
        try:
            process.kill()
            process.wait(timeout=5)
        except (NameError, OSError, subprocess.SubprocessError):
            pass
        raise Gate8CliError("refresh-observed-image", 2) from error
    finally:
        try:
            selector.close()
        except (NameError, OSError):
            pass
        try:
            process.stdout.close()
        except (AttributeError, NameError, OSError):
            pass
    observed_raw = bytes(output)
    if (
        return_code != 0
        or b"\r" in observed_raw
        or not observed_raw.endswith(b"\n")
        or observed_raw.count(b"\n") != 4
    ):
        _fail("refresh-observed-image", 2)
    try:
        observed = observed_raw.decode("ascii").splitlines()
    except UnicodeError as error:
        raise Gate8CliError("refresh-observed-image", 2) from error
    if observed != [
        values["image_id"],
        values["platform"],
        values["contract"],
        values["base"],
    ]:
        _fail("refresh-observed-image", 2)
    return values


def _admit_refresh_candidate() -> None:
    try:
        generate_candidates._admit_r3_canonical_context(  # noqa: SLF001
            ROOT / "artifacts/candidates", regeneration=False
        )
    except generate_candidates.CandidateWriterError as error:
        raise Gate8CliError("refresh-candidate", 2) from error


def _pending_roadmap() -> bytes:
    raw = _regular_file(
        _ROADMAP_PATH, "refresh-pending-roadmap", 16 * _MAX_FILE_BYTES
    )
    if (
        len(raw) != 189_838
        or hashlib.sha256(raw).hexdigest() != _PENDING_ROADMAP_SHA256
    ):
        _fail("refresh-pending-roadmap", 2)
    return raw


def _remaining_tree_expected(
    archive: Mapping[str, tuple[bytes, int]],
) -> dict[str, tuple[bytes, int]]:
    prefix = "artifacts/gate8/"
    expected = {
        path[len(prefix) :]: item
        for path, item in archive.items()
        if path.startswith(prefix)
    }
    if len(expected) != 69:
        _fail("refresh-archive")
    return expected


def _admit_remaining_prior(
    archive: Mapping[str, tuple[bytes, int]],
) -> tuple[bool, bool]:
    report_present = _REPORT_PATH.exists() or _REPORT_PATH.is_symlink()
    tree_present = _GATE8_ROOT.exists() or _GATE8_ROOT.is_symlink()
    if report_present:
        expected_report = archive.get("reports/m2-feasibility-v0.json")
        if (
            expected_report is None
            or _regular_file(_REPORT_PATH, "refresh-prior-report")
            != expected_report[0]
        ):
            _fail("refresh-prior-report", 2)
    if tree_present:
        _validate_tree(_GATE8_ROOT, _remaining_tree_expected(archive))
    return report_present, tree_present


def _admit_removal_tomb(
    tomb: Path, archive: Mapping[str, tuple[bytes, int]]
) -> None:
    expected = _remaining_tree_expected(archive)
    observed, directories = _tree_files(tomb)
    expected_directories = {
        parent.as_posix()
        for name in expected
        for parent in Path(name).parents
        if parent.as_posix() != "."
    }
    if (
        not set(observed) <= set(expected)
        or any(observed[path] != expected[path] for path in observed)
        or not directories <= expected_directories
    ):
        _fail("refresh-removal-residue")


def _install_pending_roadmap(
    prior: bytes,
    pending: bytes,
    prewrite: Callable[[], None] | None = None,
) -> None:
    descriptor, name = tempfile.mkstemp(
        prefix=".roadmap-verifier-refresh-", dir=_ROADMAP_PATH.parent
    )
    os.close(descriptor)
    stage = Path(name)
    try:
        stage.unlink()
        _write_fsynced(stage, pending, 0o644)
        _fsync_directory(_ROADMAP_PATH.parent)
        if prewrite is not None:
            prewrite()
        if (
            _regular_file(
                _ROADMAP_PATH, "refresh-roadmap-stale", 16 * _MAX_FILE_BYTES
            )
            != prior
        ):
            _fail("refresh-roadmap-stale", 2)
        os.replace(stage, _ROADMAP_PATH)
        _fsync_directory(_ROADMAP_PATH.parent)
        _pending_roadmap()
    except OSError as error:
        raise Gate8CliError("refresh-roadmap-install") from error
    finally:
        if stage.exists() and not stage.is_symlink():
            stage.unlink()


def _remove_prior_outputs(
    archive: Mapping[str, tuple[bytes, int]],
) -> None:
    _pending_roadmap()
    report_present, tree_present = _admit_remaining_prior(archive)
    tomb = _GATE8_ROOT.parent / ".gate8-verifier-refresh-remove-v0"
    if tomb.exists() or tomb.is_symlink():
        if tree_present:
            _fail("refresh-removal-residue")
        _admit_removal_tomb(tomb, archive)
        try:
            shutil.rmtree(tomb)
            _fsync_directory(tomb.parent)
        except OSError as error:
            raise Gate8CliError("refresh-removal") from error
    if report_present:
        try:
            _REPORT_PATH.unlink()
            _fsync_directory(_REPORT_PATH.parent)
        except OSError as error:
            raise Gate8CliError("refresh-removal") from error
    if tree_present:
        try:
            _rename_noreplace(_GATE8_ROOT, tomb)
            _fsync_directory(_GATE8_ROOT.parent)
            _validate_tree(tomb, _remaining_tree_expected(archive))
            shutil.rmtree(tomb)
            _fsync_directory(tomb.parent)
        except OSError as error:
            raise Gate8CliError("refresh-removal") from error
    if (
        _REPORT_PATH.exists()
        or _REPORT_PATH.is_symlink()
        or _GATE8_ROOT.exists()
        or _GATE8_ROOT.is_symlink()
        or tomb.exists()
        or tomb.is_symlink()
    ):
        _fail("refresh-removal-postcondition")


def reopen_verifier() -> None:
    """Apply the exact one-way Candidate-ready-to-In-progress reopen."""

    policy_raw, _refresh, refresh_raw = _refresh_owner()
    receipt_raw = _regular_file(_ACQUISITION_PATH, "refresh-acquisition", 379)
    _admit_observed_verifier(policy_raw, receipt_raw)
    _admit_refresh_candidate()
    roadmap_raw = _regular_file(
        _ROADMAP_PATH, "refresh-roadmap", 16 * _MAX_FILE_BYTES
    )
    roadmap_hash = hashlib.sha256(roadmap_raw).hexdigest()
    archive_present = _REFRESH_ARCHIVE.exists() or _REFRESH_ARCHIVE.is_symlink()
    if roadmap_hash == _PRIOR_ROADMAP_SHA256:
        prior = _admit_prior_live(policy_raw)
        if archive_present:
            archived = _archive_values()
            if archived != prior:
                _fail("refresh-archive-prior-mismatch")
        else:
            _create_archive(prior)
            archived = _archive_values()
        pending = _render_reopened_roadmap(roadmap_raw)

        def prewrite() -> None:
            current_policy, _current_refresh, current_refresh_raw = _refresh_owner()
            if (
                current_policy != policy_raw
                or current_refresh_raw != refresh_raw
                or _admit_prior_live(policy_raw) != archived
                or _archive_values() != archived
                or _regular_file(_ACQUISITION_PATH, "refresh-acquisition", 379)
                != receipt_raw
            ):
                _fail("refresh-stale-precondition", 2)
            _admit_observed_verifier(policy_raw, receipt_raw)
            _admit_refresh_candidate()

        _install_pending_roadmap(roadmap_raw, pending, prewrite)
    elif roadmap_hash == _PENDING_ROADMAP_SHA256:
        if not archive_present:
            _fail("refresh-archive-precondition")
        archived = _archive_values()
    else:
        _fail("refresh-roadmap-state", 2)
    _remove_prior_outputs(archived)
    _pending_roadmap()
    _archive_values()


def _render_release_repair_roadmap(current: bytes, report: bytes) -> bytes:
    prior = _archive_values().get("docs/roadmap.md")
    if prior is None:
        _fail("release-repair-prior-archive", 2)
    pending = _render_reopened_roadmap(prior[0])
    if (
        hashlib.sha256(current).hexdigest() != _RELEASE_REPAIR_ROADMAP_SHA256
        or hashlib.sha256(report).hexdigest() != _RELEASE_REPAIR_REPORT_SHA256
        or m2_gate8.render_candidate_ready_roadmap(pending, report) != current
    ):
        _fail("release-repair-roadmap-precondition", 2)
    return pending


def reopen_clean_linux_tests() -> None:
    """Reopen Gate 8 after the clean-snapshot lifecycle-test repair."""

    policy_raw, refresh, refresh_raw = _refresh_owner()
    repair = refresh.get("release_repair")
    if type(repair) is not dict:
        _fail("release-repair-owner", 2)
    receipt_raw = _regular_file(_ACQUISITION_PATH, "refresh-acquisition", 379)
    _admit_observed_verifier(policy_raw, receipt_raw)
    _admit_refresh_candidate()
    roadmap_raw = _regular_file(
        _ROADMAP_PATH, "release-repair-roadmap", 16 * _MAX_FILE_BYTES
    )
    roadmap_hash = hashlib.sha256(roadmap_raw).hexdigest()
    archive_present = (
        _RELEASE_REPAIR_ARCHIVE.exists()
        or _RELEASE_REPAIR_ARCHIVE.is_symlink()
    )
    if roadmap_hash == _RELEASE_REPAIR_ROADMAP_SHA256:
        live = _release_repair_live_values()
        if archive_present:
            archived = _release_repair_archive_values()
            if archived != live:
                _fail("release-repair-archive-prior-mismatch")
        else:
            _create_release_repair_archive(live)
            archived = _release_repair_archive_values()
        pending = _render_release_repair_roadmap(
            roadmap_raw, live["reports/m2-feasibility-v0.json"][0]
        )

        def prewrite() -> None:
            current_policy, current_refresh, current_refresh_raw = _refresh_owner()
            if (
                current_policy != policy_raw
                or current_refresh != refresh
                or current_refresh_raw != refresh_raw
                or _release_repair_live_values() != archived
                or _release_repair_archive_values() != archived
                or _regular_file(_ACQUISITION_PATH, "refresh-acquisition", 379)
                != receipt_raw
            ):
                _fail("release-repair-stale-precondition", 2)
            _admit_observed_verifier(policy_raw, receipt_raw)
            _admit_refresh_candidate()

        _install_pending_roadmap(roadmap_raw, pending, prewrite)
    elif roadmap_hash == _PENDING_ROADMAP_SHA256:
        if not archive_present:
            _fail("release-repair-archive-precondition")
        archived = _release_repair_archive_values()
    else:
        _fail("release-repair-roadmap-state", 2)
    _remove_prior_outputs(archived)
    _pending_roadmap()
    _release_repair_archive_values()


def _render_post_assembly_test_roadmap(current: bytes, report: bytes) -> bytes:
    prior = _archive_values().get("docs/roadmap.md")
    if prior is None:
        _fail("post-assembly-test-prior-archive", 2)
    pending = _render_reopened_roadmap(prior[0])
    if (
        hashlib.sha256(current).hexdigest()
        != _POST_ASSEMBLY_TEST_ROADMAP_SHA256
        or hashlib.sha256(report).hexdigest()
        != _POST_ASSEMBLY_TEST_REPORT_SHA256
        or m2_gate8.render_candidate_ready_roadmap(pending, report) != current
    ):
        _fail("post-assembly-test-roadmap-precondition", 2)
    return pending


def reopen_candidate_ready_tests() -> None:
    """Reopen Gate 8 after the Candidate-ready lifecycle-test repair."""

    policy_raw, refresh, refresh_raw = _refresh_owner()
    repair = refresh.get("candidate_ready_test_repair")
    if type(repair) is not dict:
        _fail("post-assembly-test-owner", 2)
    receipt_raw = _regular_file(_ACQUISITION_PATH, "refresh-acquisition", 379)
    _admit_observed_verifier(policy_raw, receipt_raw)
    _admit_refresh_candidate()
    roadmap_raw = _regular_file(
        _ROADMAP_PATH, "post-assembly-test-roadmap", 16 * _MAX_FILE_BYTES
    )
    roadmap_hash = hashlib.sha256(roadmap_raw).hexdigest()
    archive_present = (
        _POST_ASSEMBLY_TEST_ARCHIVE.exists()
        or _POST_ASSEMBLY_TEST_ARCHIVE.is_symlink()
    )
    if roadmap_hash == _POST_ASSEMBLY_TEST_ROADMAP_SHA256:
        live = _post_assembly_test_live_values()
        if archive_present:
            archived = _post_assembly_test_archive_values()
            if archived != live:
                _fail("post-assembly-test-archive-prior-mismatch")
        else:
            _create_post_assembly_test_archive(live)
            archived = _post_assembly_test_archive_values()
        pending = _render_post_assembly_test_roadmap(
            roadmap_raw, live["reports/m2-feasibility-v0.json"][0]
        )

        def prewrite() -> None:
            current_policy, current_refresh, current_refresh_raw = _refresh_owner()
            if (
                current_policy != policy_raw
                or current_refresh != refresh
                or current_refresh_raw != refresh_raw
                or _post_assembly_test_live_values() != archived
                or _post_assembly_test_archive_values() != archived
                or _regular_file(_ACQUISITION_PATH, "refresh-acquisition", 379)
                != receipt_raw
            ):
                _fail("post-assembly-test-stale-precondition", 2)
            _admit_observed_verifier(policy_raw, receipt_raw)
            _admit_refresh_candidate()

        _install_pending_roadmap(roadmap_raw, pending, prewrite)
    elif roadmap_hash == _PENDING_ROADMAP_SHA256:
        if not archive_present:
            _fail("post-assembly-test-archive-precondition")
        archived = _post_assembly_test_archive_values()
    else:
        _fail("post-assembly-test-roadmap-state", 2)
    _remove_prior_outputs(archived)
    _pending_roadmap()
    _post_assembly_test_archive_values()


def _render_runtime_test_repair_roadmap(current: bytes, report: bytes) -> bytes:
    prior = _archive_values().get("docs/roadmap.md")
    if prior is None:
        _fail("runtime-test-repair-prior-archive", 2)
    pending = _render_reopened_roadmap(prior[0])
    if (
        hashlib.sha256(current).hexdigest()
        != _RUNTIME_TEST_REPAIR_ROADMAP_SHA256
        or hashlib.sha256(report).hexdigest()
        != _RUNTIME_TEST_REPAIR_REPORT_SHA256
        or m2_gate8.render_candidate_ready_roadmap(pending, report) != current
    ):
        _fail("runtime-test-repair-roadmap-precondition", 2)
    return pending


def reopen_candidate_ready_runtime_tests() -> None:
    """Reopen Gate 8 for the owned real-host lifecycle-test repair."""

    policy_raw, refresh, refresh_raw = _refresh_owner()
    repair = refresh.get("candidate_ready_runtime_test_repair")
    if type(repair) is not dict:
        _fail("runtime-test-repair-owner", 2)
    receipt_raw = _regular_file(_ACQUISITION_PATH, "refresh-acquisition", 379)
    _admit_observed_verifier(policy_raw, receipt_raw)
    _admit_refresh_candidate()
    roadmap_raw = _regular_file(
        _ROADMAP_PATH, "runtime-test-repair-roadmap", 16 * _MAX_FILE_BYTES
    )
    roadmap_hash = hashlib.sha256(roadmap_raw).hexdigest()
    archive_present = (
        _RUNTIME_TEST_REPAIR_ARCHIVE.exists()
        or _RUNTIME_TEST_REPAIR_ARCHIVE.is_symlink()
    )
    if roadmap_hash == _RUNTIME_TEST_REPAIR_ROADMAP_SHA256:
        live = _runtime_test_repair_live_values()
        if archive_present:
            archived = _runtime_test_repair_archive_values()
            if archived != live:
                _fail("runtime-test-repair-archive-prior-mismatch")
        else:
            _create_runtime_test_repair_archive(live)
            archived = _runtime_test_repair_archive_values()
        pending = _render_runtime_test_repair_roadmap(
            roadmap_raw, live["reports/m2-feasibility-v0.json"][0]
        )

        def prewrite() -> None:
            current_policy, current_refresh, current_refresh_raw = _refresh_owner()
            if (
                current_policy != policy_raw
                or current_refresh != refresh
                or current_refresh_raw != refresh_raw
                or _runtime_test_repair_live_values() != archived
                or _runtime_test_repair_archive_values() != archived
                or _regular_file(_ACQUISITION_PATH, "refresh-acquisition", 379)
                != receipt_raw
            ):
                _fail("runtime-test-repair-stale-precondition", 2)
            _admit_observed_verifier(policy_raw, receipt_raw)
            _admit_refresh_candidate()

        _install_pending_roadmap(roadmap_raw, pending, prewrite)
    elif roadmap_hash == _PENDING_ROADMAP_SHA256:
        if not archive_present:
            _fail("runtime-test-repair-archive-precondition")
        archived = _runtime_test_repair_archive_values()
    else:
        _fail("runtime-test-repair-roadmap-state", 2)
    _remove_prior_outputs(archived)
    _pending_roadmap()
    _runtime_test_repair_archive_values()


def _render_clean_snapshot_test_repair_roadmap(
    current: bytes, report: bytes
) -> bytes:
    prior = _archive_values().get("docs/roadmap.md")
    if prior is None:
        _fail("clean-snapshot-test-repair-prior-archive", 2)
    pending = _render_reopened_roadmap(prior[0])
    if (
        hashlib.sha256(current).hexdigest()
        != _CLEAN_SNAPSHOT_TEST_REPAIR_ROADMAP_SHA256
        or hashlib.sha256(report).hexdigest()
        != _CLEAN_SNAPSHOT_TEST_REPAIR_REPORT_SHA256
        or m2_gate8.render_candidate_ready_roadmap(pending, report) != current
    ):
        _fail("clean-snapshot-test-repair-roadmap-precondition", 2)
    return pending


def reopen_candidate_ready_clean_snapshot_tests() -> None:
    """Reopen Gate 8 for the owned clean-snapshot lifecycle-test repair."""

    policy_raw, refresh, refresh_raw = _refresh_owner()
    repair = refresh.get("candidate_ready_clean_snapshot_test_repair")
    if type(repair) is not dict:
        _fail("clean-snapshot-test-repair-owner", 2)
    receipt_raw = _regular_file(_ACQUISITION_PATH, "refresh-acquisition", 379)
    _admit_observed_verifier(policy_raw, receipt_raw)
    _admit_refresh_candidate()
    roadmap_raw = _regular_file(
        _ROADMAP_PATH,
        "clean-snapshot-test-repair-roadmap",
        16 * _MAX_FILE_BYTES,
    )
    roadmap_hash = hashlib.sha256(roadmap_raw).hexdigest()
    archive_present = (
        _CLEAN_SNAPSHOT_TEST_REPAIR_ARCHIVE.exists()
        or _CLEAN_SNAPSHOT_TEST_REPAIR_ARCHIVE.is_symlink()
    )
    if roadmap_hash == _CLEAN_SNAPSHOT_TEST_REPAIR_ROADMAP_SHA256:
        live = _clean_snapshot_test_repair_live_values()
        if archive_present:
            archived = _clean_snapshot_test_repair_archive_values()
            if archived != live:
                _fail("clean-snapshot-test-repair-archive-prior-mismatch")
        else:
            _create_clean_snapshot_test_repair_archive(live)
            archived = _clean_snapshot_test_repair_archive_values()
        pending = _render_clean_snapshot_test_repair_roadmap(
            roadmap_raw, live["reports/m2-feasibility-v0.json"][0]
        )

        def prewrite() -> None:
            current_policy, current_refresh, current_refresh_raw = _refresh_owner()
            if (
                current_policy != policy_raw
                or current_refresh != refresh
                or current_refresh_raw != refresh_raw
                or _clean_snapshot_test_repair_live_values() != archived
                or _clean_snapshot_test_repair_archive_values() != archived
                or _regular_file(_ACQUISITION_PATH, "refresh-acquisition", 379)
                != receipt_raw
            ):
                _fail("clean-snapshot-test-repair-stale-precondition", 2)
            _admit_observed_verifier(policy_raw, receipt_raw)
            _admit_refresh_candidate()

        _install_pending_roadmap(roadmap_raw, pending, prewrite)
    elif roadmap_hash == _PENDING_ROADMAP_SHA256:
        if not archive_present:
            _fail("clean-snapshot-test-repair-archive-precondition")
        archived = _clean_snapshot_test_repair_archive_values()
    else:
        _fail("clean-snapshot-test-repair-roadmap-state", 2)
    _remove_prior_outputs(archived)
    _pending_roadmap()
    _clean_snapshot_test_repair_archive_values()


def _render_provenance_input_repair_roadmap(
    current: bytes, report: bytes
) -> bytes:
    prior = _archive_values().get("docs/roadmap.md")
    if prior is None:
        _fail("provenance-input-repair-prior-archive", 2)
    pending = _render_reopened_roadmap(prior[0])
    if (
        hashlib.sha256(current).hexdigest()
        != _PROVENANCE_INPUT_REPAIR_ROADMAP_SHA256
        or hashlib.sha256(report).hexdigest()
        != _PROVENANCE_INPUT_REPAIR_REPORT_SHA256
        or m2_gate8.render_candidate_ready_roadmap(pending, report) != current
    ):
        _fail("provenance-input-repair-roadmap-precondition", 2)
    return pending


def reopen_candidate_ready_provenance_input() -> None:
    """Reopen Gate 8 for the owned clean-Linux provenance-input repair."""

    policy_raw, refresh, refresh_raw = _refresh_owner()
    repair = refresh.get("candidate_ready_provenance_input_repair")
    if type(repair) is not dict:
        _fail("provenance-input-repair-owner", 2)
    receipt_raw = _regular_file(_ACQUISITION_PATH, "refresh-acquisition", 379)
    _admit_observed_verifier(policy_raw, receipt_raw)
    _admit_refresh_candidate()
    roadmap_raw = _regular_file(
        _ROADMAP_PATH,
        "provenance-input-repair-roadmap",
        16 * _MAX_FILE_BYTES,
    )
    roadmap_hash = hashlib.sha256(roadmap_raw).hexdigest()
    archive_present = (
        _PROVENANCE_INPUT_REPAIR_ARCHIVE.exists()
        or _PROVENANCE_INPUT_REPAIR_ARCHIVE.is_symlink()
    )
    if roadmap_hash == _PROVENANCE_INPUT_REPAIR_ROADMAP_SHA256:
        live = _provenance_input_repair_live_values()
        if archive_present:
            archived = _provenance_input_repair_archive_values()
            if archived != live:
                _fail("provenance-input-repair-archive-prior-mismatch")
        else:
            _create_provenance_input_repair_archive(live)
            archived = _provenance_input_repair_archive_values()
        pending = _render_provenance_input_repair_roadmap(
            roadmap_raw, live["reports/m2-feasibility-v0.json"][0]
        )

        def prewrite() -> None:
            current_policy, current_refresh, current_refresh_raw = _refresh_owner()
            if (
                current_policy != policy_raw
                or current_refresh != refresh
                or current_refresh_raw != refresh_raw
                or _provenance_input_repair_live_values() != archived
                or _provenance_input_repair_archive_values() != archived
                or _regular_file(_ACQUISITION_PATH, "refresh-acquisition", 379)
                != receipt_raw
            ):
                _fail("provenance-input-repair-stale-precondition", 2)
            _admit_observed_verifier(policy_raw, receipt_raw)
            _admit_refresh_candidate()

        _install_pending_roadmap(roadmap_raw, pending, prewrite)
    elif roadmap_hash == _PENDING_ROADMAP_SHA256:
        if not archive_present:
            _fail("provenance-input-repair-archive-precondition")
        archived = _provenance_input_repair_archive_values()
    else:
        _fail("provenance-input-repair-roadmap-state", 2)
    _remove_prior_outputs(archived)
    _pending_roadmap()
    _provenance_input_repair_archive_values()


def _render_provenance_fixture_repair_roadmap(
    current: bytes, report: bytes
) -> bytes:
    prior = _archive_values().get("docs/roadmap.md")
    if prior is None:
        _fail("provenance-fixture-repair-prior-archive", 2)
    pending = _render_reopened_roadmap(prior[0])
    if (
        hashlib.sha256(current).hexdigest()
        != _PROVENANCE_FIXTURE_REPAIR_ROADMAP_SHA256
        or hashlib.sha256(report).hexdigest()
        != _PROVENANCE_FIXTURE_REPAIR_REPORT_SHA256
        or m2_gate8.render_candidate_ready_roadmap(pending, report) != current
    ):
        _fail("provenance-fixture-repair-roadmap-precondition", 2)
    return pending


def reopen_provenance_fixtures() -> None:
    """Reopen Gate 8 for the owned clean-Linux provenance-input repair."""

    policy_raw, refresh, refresh_raw = _refresh_owner()
    repair = refresh.get("candidate_ready_provenance_fixture_repair")
    if type(repair) is not dict:
        _fail("provenance-fixture-repair-owner", 2)
    receipt_raw = _regular_file(_ACQUISITION_PATH, "refresh-acquisition", 379)
    _admit_observed_verifier(policy_raw, receipt_raw)
    _admit_refresh_candidate()
    roadmap_raw = _regular_file(
        _ROADMAP_PATH,
        "provenance-fixture-repair-roadmap",
        16 * _MAX_FILE_BYTES,
    )
    roadmap_hash = hashlib.sha256(roadmap_raw).hexdigest()
    archive_present = (
        _PROVENANCE_FIXTURE_REPAIR_ARCHIVE.exists()
        or _PROVENANCE_FIXTURE_REPAIR_ARCHIVE.is_symlink()
    )
    if roadmap_hash == _PROVENANCE_FIXTURE_REPAIR_ROADMAP_SHA256:
        live = _provenance_fixture_repair_live_values()
        if archive_present:
            archived = _provenance_fixture_repair_archive_values()
            if archived != live:
                _fail("provenance-fixture-repair-archive-prior-mismatch")
        else:
            _create_provenance_fixture_repair_archive(live)
            archived = _provenance_fixture_repair_archive_values()
        pending = _render_provenance_fixture_repair_roadmap(
            roadmap_raw, live["reports/m2-feasibility-v0.json"][0]
        )

        def prewrite() -> None:
            current_policy, current_refresh, current_refresh_raw = _refresh_owner()
            if (
                current_policy != policy_raw
                or current_refresh != refresh
                or current_refresh_raw != refresh_raw
                or _provenance_fixture_repair_live_values() != archived
                or _provenance_fixture_repair_archive_values() != archived
                or _regular_file(_ACQUISITION_PATH, "refresh-acquisition", 379)
                != receipt_raw
            ):
                _fail("provenance-fixture-repair-stale-precondition", 2)
            _admit_observed_verifier(policy_raw, receipt_raw)
            _admit_refresh_candidate()

        _install_pending_roadmap(roadmap_raw, pending, prewrite)
    elif roadmap_hash == _PENDING_ROADMAP_SHA256:
        if not archive_present:
            _fail("provenance-fixture-repair-archive-precondition")
        archived = _provenance_fixture_repair_archive_values()
    else:
        _fail("provenance-fixture-repair-roadmap-state", 2)
    _remove_prior_outputs(archived)
    _pending_roadmap()
    _provenance_fixture_repair_archive_values()


def _legacy_fixtures() -> tuple[bytes, bytes]:
    """Independently rebuild all owned legacy packages and the sole v3 route."""

    packages = {
        version: m2_recipe.build_eh_recipient_package(version)
        for version in (2, 3, 4)
    }
    for version in (5, 6):
        contract = m2_recipe.rs_transport_recipe_contract(version)
        package = m2_recipe.build_rs_decoder_recipe(version)
        if (
            contract.package != package
            or contract.package_bytes != len(package)
            or contract.package_sha256 != hashlib.sha256(package).hexdigest()
        ):
            _fail("legacy-package")
        packages[version] = package
    for version, package in packages.items():
        try:
            decoded = bootstrap.decode_recipe_package(package, version)
        except bootstrap.BootstrapError as error:
            raise Gate8CliError("legacy-package") from error
        if decoded.profile_version != version:
            _fail("legacy-package")

    profile = m2_codec.r3_candidate_profile(
        protected_units=1_841,
        encoded_transport_bytes=397_656,
    )
    alternate = next(
        item
        for item in m2_codec.r3_registry_profiles(profile)
        if item.profile_version == 3
    )
    try:
        routes = m2_route_data.build_route_images(
            _owner("spec/route-data-v0.json"),
            m2_route_data.CandidateRouteData(
                alternate.profile_id,
                alternate.profile_version,
                alternate.transport_id,
                alternate.section_check_id,
                (packages[3],),
            ),
            2_040,
            128,
        )
    except m2_route_data.RouteDataError as error:
        raise Gate8CliError("legacy-route") from error
    if (
        len(routes.sectors) != 4
        or routes.sectors[0].sector_id != 0
        or routes.sectors[0].route_prefix_cells % 8
    ):
        _fail("legacy-route")
    prefix_bytes = routes.sectors[0].route_prefix_cells // 8
    return packages[3], routes.sectors[0].data[:prefix_bytes]


def _damage_values(
    run: m2_damage.DamageRun,
    manifestation: object,
    profile: m2_codec.CandidateProfile,
    profile_raw: bytes,
    limits_raw: bytes,
    damage_raw: bytes,
    bootstrap_raw: bytes,
    route_raw: bytes,
) -> tuple[dict[str, bytes], object]:
    if (
        type(run) is not m2_damage.DamageRun
        or run.profile_id != PROFILE_ID
        or len(run.family_manifests) != 8
        or run.case_count != 10_038
        or run.gate6_result != "pass"
        or run.gate7_result != "not_evaluated"
        or run.wrong_accept_count != 0
    ):
        _fail("python-gate6")
    values = {
        "damage-manifest.json": run.manifest,
        **{
            f"damage-D{ordinal}.json": raw
            for ordinal, raw in enumerate(run.family_manifests)
        },
    }
    for name, raw in run.case_shards:
        if name in values or "/" in name or "\\" in name:
            _fail("python-gate6")
        values[name] = raw
    try:
        admitted = m2_damage.validate_damage_bundle_v1(
            run.manifest,
            run.family_manifests,
            run.case_shards,
            damage_raw,
            profile_raw,
            limits_raw,
            bootstrap_raw,
            route_raw,
            m2_recipe.build_r3_recipe_package(),
            manifestation.candidate_manifest,  # type: ignore[attr-defined]
            manifestation.carrier,  # type: ignore[attr-defined]
        )
    except (AttributeError, m2_damage.DamageError) as error:
        raise Gate8CliError("python-gate6") from error
    if admitted.result != "pass":
        _fail("python-gate6")
    return values, admitted


def _generate_python_gate_seven(work_root: Path) -> GeneratedGateSeven:
    """Generate, materialize, and re-admit exact Gates 1--7 in Python."""

    _private_directory(work_root, "candidate-root", empty=True)
    manifestation = generate_candidates.build_r3_candidate()
    candidate_values = generate_candidates._r3_artifact_map(manifestation)
    for name in generate_candidates.R3_ALLOWLIST:
        _write_fsynced(work_root / name, candidate_values[name])
    _fsync_directory(work_root)

    profile_raw = _owner("spec/profile-policy-v1.toml")
    limits_raw = _owner("spec/profile-limits-v1.toml")
    damage_raw = _owner("spec/damage-policy-v1.toml")
    bootstrap_raw = _owner("spec/bootstrap-v1.md")
    route_raw = _owner("spec/route-data-v1.json")
    alternate_package, _alternate_prefix = _legacy_fixtures()
    profile = m2_codec.r3_candidate_profile(
        protected_units=1_841,
        encoded_transport_bytes=397_656,
    )
    run = m2_damage.run_damage_python(
        manifestation,
        profile,
        profile_raw,
        limits_raw,
        damage_raw,
        route_raw,
        alternate_package,
        min(8, os.cpu_count() or 1),
        _owner("spec/route-data-v0.json"),
    )
    damage_values, _admitted = _damage_values(
        run,
        manifestation,
        profile,
        profile_raw,
        limits_raw,
        damage_raw,
        bootstrap_raw,
        route_raw,
    )
    try:
        proof = m2_independence.build_independence_proof_v1(
            manifestation.candidate_manifest,
            manifestation.ownership_ledger,
            run.manifest,
            run.family_manifests,
            tuple(raw for _name, raw in run.case_shards),
        )
        admitted_proof = m2_independence.validate_independence_proof_v1(
            proof.raw,
            manifestation.candidate_manifest,
            manifestation.ownership_ledger,
            run.manifest,
            run.family_manifests,
            tuple(raw for _name, raw in run.case_shards),
        )
    except m2_independence.IndependenceError as error:
        raise Gate8CliError("python-gate7") from error
    if admitted_proof.result != "pass":
        _fail("python-gate7")
    damage_root = work_root / "damage"
    try:
        damage_root.mkdir(mode=0o700)
    except OSError as error:
        raise Gate8CliError("python-gate7") from error
    for name in sorted(damage_values):
        _write_fsynced(damage_root / name, damage_values[name])
    _write_fsynced(damage_root / "independence-proof.json", proof.raw)
    _fsync_directory(damage_root)
    _fsync_directory(work_root)

    all_damage = {**damage_values, "independence-proof.json": proof.raw}
    semantic = m2_gate8.build_semantic_content_projection_from_carrier(
        manifestation.candidate_manifest,
        manifestation.carrier,
        manifestation.semantic_envelope,
    )
    decoder = m2_decoder.ObservationDecoder(profile_raw, limits_raw, damage_raw)
    clean_result = decoder.render_result(
        m2_decoder.OBS_BITS,
        decoder.decode(m2_decoder.OBS_BITS, manifestation.carrier),
    )
    artifacts = {
        "semantic-content-projection": semantic.canonical_bytes,
        "candidate-manifest": manifestation.candidate_manifest,
        "carrier": manifestation.carrier,
        "ownership-ledger": manifestation.ownership_ledger,
        "capacity-ledger": manifestation.capacity_ledger,
        "density-ledger": manifestation.density_ledger,
        "damage-bundle-inventory": m2_gate8.render_damage_inventory(all_damage),
        "independence-proof": proof.raw,
    }
    m2_gate8.render_producer_receipt("native-python", artifacts)
    return GeneratedGateSeven(
        manifestation,
        damage_values,
        proof.raw,
        artifacts,
        run.bundle_case_preimages,
        clean_result,
        semantic.content_stream,
    )


def _case_rows(damage_files: Mapping[str, bytes]) -> dict[str, dict[str, object]]:
    wanted = {"D2-000000", "D3-000000", "D4-000000", "D7-000011"}
    output: dict[str, dict[str, object]] = {}
    for name in sorted(damage_files):
        if "-cases-" not in name:
            continue
        try:
            value = canonical_manifest.validate_canonical_manifest(
                damage_files[name]
            )
        except (TypeError, ValueError) as error:
            raise Gate8CliError("damage-case") from error
        rows = value.get("case_rows") if type(value) is dict else None
        if type(rows) is not list:
            _fail("damage-case")
        for row in rows:
            if type(row) is not dict:
                _fail("damage-case")
            case_id = row.get("case_id")
            if case_id in wanted:
                if case_id in output:
                    _fail("damage-case")
                output[str(case_id)] = row
    if set(output) != wanted:
        _fail("damage-case")
    return output


def _owner_projection_inputs(
    generated: GeneratedGateSeven,
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    candidate_path = f"artifacts/candidates/{PROFILE_ID}"
    candidate_values = {
        f"{candidate_path}/candidate-manifest.json": generated.manifestation.candidate_manifest,  # type: ignore[attr-defined]
        f"{candidate_path}/semantic-envelope.json": generated.manifestation.semantic_envelope,  # type: ignore[attr-defined]
        f"{candidate_path}/capacity-ledger.json": generated.manifestation.capacity_ledger,  # type: ignore[attr-defined]
    }
    paths = {
        path
        for role in (
            "parameter_manifest",
            "known_answer_manifest",
            "shell_manifest",
            "recipe_manifest",
            "grammar_state_manifest",
            "work_scratch_ledger",
            "profile_limits_derivation",
            "side_search_policy",
        )
        for path in m2_gate8.owner_projection_paths(role)
    }
    source_preimages = {
        path: candidate_values[path]
        if path in candidate_values
        else _owner(path)
        for path in paths
    }
    projections = {
        role: m2_gate8.render_owner_projection(
            role,
            {
                path: source_preimages[path]
                for path in m2_gate8.owner_projection_paths(role)
            },
        )
        for role in (
            "parameter_manifest",
            "known_answer_manifest",
            "shell_manifest",
            "recipe_manifest",
            "grammar_state_manifest",
            "work_scratch_ledger",
            "profile_limits_derivation",
            "side_search_policy",
        )
    }
    return source_preimages, projections


def _bundle_files(
    generated: GeneratedGateSeven,
    policy_raw: bytes,
    projections: Mapping[str, bytes],
) -> tuple[dict[str, bytes], dict[str, bytes], bytes, bytes, bytes, bytes]:
    cases = _case_rows(generated.damage_files)
    captured = {
        case_id: (channel, observation, result)
        for case_id, channel, observation, result in generated.bundle_case_preimages
    }
    if set(captured) != set(cases):
        _fail("damage-case-preimage")
    for case_id, (channel, observation, result) in captured.items():
        if (
            cases[case_id].get("channel") != channel
            or cases[case_id].get("observation_sha256")
            != hashlib.sha256(observation).hexdigest()
            or cases[case_id].get("decoder_result_sha256")
            != hashlib.sha256(result).hexdigest()
        ):
            _fail("damage-case-preimage")
    content_query, content_result = m2_gate8.render_technical_content_query(
        policy_raw, generated.content_stream
    )
    heldout_classes = m2_gate8.render_technical_heldout_classes(cases)
    heldout_expected = m2_gate8.render_technical_heldout_expected(cases)
    semantic_path = m2_runner.semantic_path_bytes(
        m2_runner.run_m2_semantic_path(
            generated.content_stream, label_suppressed=True
        )
    )
    learner_expected = m2_gate8.render_learner_expected(
        policy_raw, generated.content_stream, semantic_path
    )
    learner_slice = m2_gate8.render_learner_slice_binding(
        policy_raw, generated.content_stream
    )
    heldout_request = m2_gate8.render_learner_heldout_request(policy_raw)
    technical_values = {
        "clean-observation": generated.manifestation.carrier,  # type: ignore[attr-defined]
        "content-query": content_query,
        "unknown-error-observation": captured["D3-000000"][1],
        "known-erasure-observation": captured["D2-000000"][1],
        "missing-unit-observation": captured["D4-000000"][1],
        "negative-observation": captured["D7-000011"][1],
        "candidate-bindings": generated.manifestation.candidate_manifest,  # type: ignore[attr-defined]
        "clean-expected": generated.clean_result_raw,
        "content-query-expected": content_result,
        "heldout-expected": heldout_expected,
        "resource-limits": _owner("spec/profile-limits-v1.toml"),
    }
    learner_values = {
        "content-stream": generated.content_stream,
        "runner": _owner("tools/m2/learner_runner.py"),
        "slice-binding": learner_slice,
        "heldout-cases": heldout_request,
        "candidate-bindings": generated.manifestation.candidate_manifest,  # type: ignore[attr-defined]
        "semantic-path-expected": semantic_path,
        "heldout-expected": learner_expected,
    }
    technical = m2_gate8.build_bundle_files(
        policy_raw, ROOT, "technical", technical_values
    )
    learner = m2_gate8.build_bundle_files(
        policy_raw, ROOT, "learner", learner_values
    )
    if projections.get("parameter_manifest") is None:
        _fail("bundle-owner-projection")
    return (
        technical,
        learner,
        m2_gate8.render_bundle_manifest(policy_raw, "technical", technical),
        m2_gate8.render_bundle_manifest(policy_raw, "learner", learner),
        heldout_classes,
        semantic_path,
    )


def _bundle_tree_rows(
    policy_raw: bytes,
    kind: str,
    files: Mapping[str, bytes],
) -> dict[str, tuple[bytes, int]]:
    policy = m2_gate8.load_gate8_policy(policy_raw)
    bundle = policy.get(f"{kind}_bundle")
    if type(bundle) is not dict:
        _fail("bundle-policy")
    roles = bundle.get("participant_roles", []) + bundle.get("evaluator_roles", [])
    paths = bundle.get("role_paths")
    modes = bundle.get("role_modes", {})
    root = bundle.get("file_root")
    if (
        type(roles) is not list
        or type(paths) is not dict
        or type(modes) is not dict
        or type(root) is not str
        or not root.startswith("artifacts/gate8/")
    ):
        _fail("bundle-policy")
    prefix = root.removeprefix("artifacts/gate8/")
    output = {}
    for role in roles:
        path = paths.get(role)
        if type(role) is not str or type(path) is not str or role not in files:
            _fail("bundle-policy")
        mode = 0o755 if modes.get(role) == "100755" else 0o644
        output[f"{prefix}/{path}"] = (files[role], mode)
    return output


def _assemble_gate8(
    generated: GeneratedGateSeven,
    receipts: Mapping[str, bytes],
) -> Gate8Assembly:
    policy_raw = _owner("spec/gate8-policy-v0.toml")
    if tuple(receipts) != _PRODUCER_IDS:
        _fail("assembly-receipts")
    for producer_id in _PRODUCER_IDS:
        m2_gate8.validate_producer_receipt(
            receipts[producer_id], producer_id, generated.artifacts
        )
    source_raw = m2_gate8.build_evidence_source_projection(ROOT)
    m2_gate8.validate_gate8_source_surface(source_raw, ROOT, policy_raw)
    cross_raw = m2_gate8.render_cross_language_manifest(
        receipts, generated.manifestation.candidate_manifest  # type: ignore[attr-defined]
    )
    cross = m2_gate8.validate_cross_language_manifest(
        cross_raw,
        receipts,
        generated.manifestation.candidate_manifest,  # type: ignore[attr-defined]
    )
    if not isinstance(cross.get("summary"), dict) or cross["summary"].get(  # type: ignore[index]
        "result"
    ) != "pass":
        _fail("assembly-cross-language")
    owner_sources, projections = _owner_projection_inputs(generated)
    (
        technical_files,
        learner_files,
        technical_bundle,
        learner_bundle,
        heldout_classes,
        semantic_path,
    ) = _bundle_files(generated, policy_raw, projections)
    metrics = m2_gate8.derive_candidate_metrics(
        m2_recipe.build_r3_recipe_package(),
        _owner("spec/profile-limits-v1.toml"),
        _owner("spec/route-data-v1.json"),
        generated.manifestation.capacity_ledger,  # type: ignore[attr-defined]
    )
    candidate_row = m2_gate8.build_candidate_row(
        metrics, _owner("spec/profile-policy-v1.toml"), cross_raw
    )
    selection = m2_gate8.render_selection(
        candidate_row, cross_raw, _owner("spec/profile-policy-v1.toml")
    )
    verifier_environment = _owner("artifacts/linux/verifier-v0.env")
    linux = m2_gate8.render_linux_attestation(
        source_raw, cross_raw, verifier_environment
    )
    geometry = m2_gate8.render_geometry_equivalence(
        generated.manifestation.candidate_manifest  # type: ignore[attr-defined]
    )
    generated_shared = {
        "content_stream": ("m2_all", generated.content_stream),
        "vertical_slice": ("slice-v0", _owner("studies/m2/slice-v0.json")),
        "semantic_envelope": (
            "capacity-envelope-v1",
            generated.manifestation.semantic_envelope,  # type: ignore[attr-defined]
        ),
        "profile_limits_derivation": (
            "profile-limits-v7",
            projections["profile_limits_derivation"],
        ),
        "side_search_policy": ("side-search-v7", projections["side_search_policy"]),
        "evidence_source_projection": ("m2-evidence-source-v0", source_raw),
        "selection_recomputation": ("selection-v0", selection),
        "linux_attestation": ("linux-v0", linux),
        "technical_bundle": ("technical-v0", technical_bundle),
        "learner_bundle": ("learner-v0", learner_bundle),
    }
    generated_candidate = {
        "parameter_manifest": projections["parameter_manifest"],
        "known_answer_manifest": projections["known_answer_manifest"],
        "shell_manifest": projections["shell_manifest"],
        "recipe_manifest": projections["recipe_manifest"],
        "grammar_state_manifest": projections["grammar_state_manifest"],
        "work_scratch_ledger": projections["work_scratch_ledger"],
        "carrier": generated.manifestation.carrier,  # type: ignore[attr-defined]
        "ownership_ledger": generated.manifestation.ownership_ledger,  # type: ignore[attr-defined]
        "capacity_ledger": generated.manifestation.capacity_ledger,  # type: ignore[attr-defined]
        "density_ledger": generated.manifestation.density_ledger,  # type: ignore[attr-defined]
        "damage_manifest": generated.damage_files["damage-manifest.json"],
        **{
            f"damage_D{ordinal}": generated.damage_files[
                f"damage-D{ordinal}.json"
            ]
            for ordinal in range(8)
        },
        "independence_proof": generated.proof_raw,
        "cross_language_manifest": cross_raw,
    }
    generated_evidence = m2_gate8.render_generated_evidence(
        generated_shared, generated_candidate
    )
    pilot_preimages = {
        "bootstrap_spec_raw": _owner("spec/bootstrap-v1.md"),
        "route_data_raw": _owner("spec/route-data-v1.json"),
        "damage_policy_raw": _owner("spec/damage-policy-v1.toml"),
        "geometry_equivalence_raw": geometry,
        "technical_heldout_classes_raw": heldout_classes,
        "content_stream_raw": generated.content_stream,
        "vertical_slice_raw": _owner("studies/m2/slice-v0.json"),
        "runner_raw": _owner("tools/m2/learner_runner.py"),
        "semantic_path_raw": semantic_path,
    }
    report = m2_gate8.render_candidate_ready_report(
        source_root=ROOT,
        gate8_policy_raw=policy_raw,
        roadmap_raw=_owner("docs/roadmap.md"),
        evidence_source_raw=source_raw,
        candidate_metrics=metrics,
        selection_raw=selection,
        profile_policy_raw=_owner("spec/profile-policy-v1.toml"),
        profile_limits_raw=_owner("spec/profile-limits-v1.toml"),
        semantic_envelope_raw=generated.manifestation.semantic_envelope,  # type: ignore[attr-defined]
        side_search_projection_raw=projections["side_search_policy"],
        candidate_manifest_raw=generated.manifestation.candidate_manifest,  # type: ignore[attr-defined]
        carrier_raw=generated.manifestation.carrier,  # type: ignore[attr-defined]
        ownership_ledger_raw=generated.manifestation.ownership_ledger,  # type: ignore[attr-defined]
        capacity_ledger_raw=generated.manifestation.capacity_ledger,  # type: ignore[attr-defined]
        density_ledger_raw=generated.manifestation.density_ledger,  # type: ignore[attr-defined]
        work_scratch_projection_raw=projections["work_scratch_ledger"],
        damage_manifest_raw=generated.damage_files["damage-manifest.json"],
        family_manifest_raws={
            f"D{ordinal}": generated.damage_files[f"damage-D{ordinal}.json"]
            for ordinal in range(8)
        },
        damage_bundle_files={
            **generated.damage_files,
            "independence-proof.json": generated.proof_raw,
        },
        producer_receipts=receipts,
        producer_artifacts=generated.artifacts,
        cross_language_raw=cross_raw,
        linux_attestation_raw=linux,
        verifier_environment_raw=verifier_environment,
        technical_bundle_raw=technical_bundle,
        technical_files=technical_files,
        learner_bundle_raw=learner_bundle,
        learner_files=learner_files,
        generated_evidence_raw=generated_evidence,
        generated_shared_preimages=generated_shared,
        generated_candidate_preimages=generated_candidate,
        owner_source_preimages=owner_sources,
        pilot_preimages=pilot_preimages,
    )
    fixed = {
        "evidence-source-v0.json": source_raw,
        "generated-evidence-v0.json": generated_evidence,
        "linux-attestation-v0.json": linux,
        "selection-v0.json": selection,
        f"{PROFILE_ID}/cross-language-manifest.json": cross_raw,
        "projections/damage-inventory-v7.json": generated.artifacts[
            "damage-bundle-inventory"
        ],
        "projections/geometry-equivalence-v7.json": geometry,
        "projections/grammar-state-manifest-v7.json": projections[
            "grammar_state_manifest"
        ],
        "projections/known-answer-manifest-v7.json": projections[
            "known_answer_manifest"
        ],
        "projections/m2-all.content-v0.bin": generated.content_stream,
        "projections/parameter-manifest-v7.json": projections[
            "parameter_manifest"
        ],
        "projections/profile-limits-v7.json": projections[
            "profile_limits_derivation"
        ],
        "projections/recipe-manifest-v7.json": projections["recipe_manifest"],
        "projections/semantic-content-v7.json": generated.artifacts[
            "semantic-content-projection"
        ],
        "projections/shell-manifest-v7.json": projections["shell_manifest"],
        "projections/side-search-v7.json": projections["side_search_policy"],
        "projections/technical-heldout-classes-v0.json": heldout_classes,
        "projections/runner-semantic-path-v0.json": semantic_path,
        "projections/work-scratch-ledger-v7.json": projections[
            "work_scratch_ledger"
        ],
        "bundles/learner-v0.json": learner_bundle,
        "bundles/technical-v0.json": technical_bundle,
        **{
            f"receipts/{producer_id}.json": receipts[producer_id]
            for producer_id in _PRODUCER_IDS
        },
    }
    tree = {path: (raw, 0o644) for path, raw in fixed.items()}
    tree.update(_bundle_tree_rows(policy_raw, "technical", technical_files))
    tree.update(_bundle_tree_rows(policy_raw, "learner", learner_files))
    if len(tree) != 69:
        _fail("assembly-tree-count")
    return Gate8Assembly(tree, report)


def _read_receipt_directory(directory: Path, allowed: tuple[str, ...]) -> dict[str, bytes]:
    _private_directory(directory, "receipt-directory", empty=False)
    try:
        entries = tuple(directory.iterdir())
    except OSError as error:
        raise Gate8CliError("receipt-directory", 2) from error
    names = {entry.name for entry in entries}
    if not names <= {f"{producer}.json" for producer in allowed}:
        _fail("receipt-directory", 2)
    output: dict[str, bytes] = {}
    inodes: set[tuple[int, int]] = set()
    for entry in entries:
        metadata = _lstat(entry, "receipt-directory")
        inode = (metadata.st_dev, metadata.st_ino)
        if inode in inodes:
            _fail("receipt-directory", 2)
        inodes.add(inode)
        producer_id = entry.stem
        raw = _regular_file(entry, "receipt-directory")
        m2_gate8.parse_producer_receipt(raw, producer_id)
        output[producer_id] = raw
    return output


def _tree_files(
    root: Path,
) -> tuple[dict[str, tuple[bytes, int]], set[str]]:
    """Read one bounded exact regular-file tree without following links."""

    _private_directory(root, "gate8-directory", empty=False)
    try:
        paths = tuple(root.rglob("*"))
    except OSError as error:
        raise Gate8CliError("gate8-directory") from error
    if len(paths) > 128:
        _fail("gate8-file-count")
    output: dict[str, tuple[bytes, int]] = {}
    directories: set[str] = set()
    inodes: set[tuple[int, int]] = set()
    aggregate = 0
    for path in paths:
        metadata = _lstat(path, "gate8-file")
        if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
            if stat.S_IMODE(metadata.st_mode) != 0o700:
                _fail("gate8-directory-mode")
            directories.add(path.relative_to(root).as_posix())
            continue
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_nlink != 1
        ):
            _fail("gate8-file")
        inode = (metadata.st_dev, metadata.st_ino)
        if inode in inodes:
            _fail("gate8-hardlink")
        inodes.add(inode)
        raw = _regular_file(path, "gate8-file", 16 * _MAX_FILE_BYTES)
        aggregate += len(raw)
        if aggregate > 83_886_080:
            _fail("gate8-aggregate")
        relative = path.relative_to(root).as_posix()
        if relative in output:
            _fail("gate8-file")
        output[relative] = (raw, stat.S_IMODE(metadata.st_mode))
    return output, directories


def _validate_tree(root: Path, expected: Mapping[str, tuple[bytes, int]]) -> None:
    if (
        not isinstance(expected, Mapping)
        or len(expected) != 69
        or any(
            type(path) is not str
            or type(value) is not tuple
            or len(value) != 2
            or type(value[0]) is not bytes
            or value[1] not in (0o644, 0o755)
            for path, value in expected.items()
        )
    ):
        _fail("gate8-expected-tree")
    observed, directories = _tree_files(root)
    expected_directories = {
        parent.as_posix()
        for name in expected
        for parent in Path(name).parents
        if parent.as_posix() != "."
    }
    if observed != dict(expected) or directories != expected_directories:
        _fail("gate8-tree-mismatch")


def _write_tree(root: Path, expected: Mapping[str, tuple[bytes, int]]) -> None:
    _private_directory(root, "gate8-stage", empty=True)
    for relative, (raw, mode) in expected.items():
        path = root / relative
        current = root
        for component in Path(relative).parts[:-1]:
            current /= component
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                metadata = _lstat(current, "gate8-stage")
                if (
                    stat.S_ISLNK(metadata.st_mode)
                    or not stat.S_ISDIR(metadata.st_mode)
                    or stat.S_IMODE(metadata.st_mode) != 0o700
                ):
                    _fail("gate8-stage")
            except OSError as error:
                raise Gate8CliError("gate8-stage") from error
        _write_fsynced(path, raw, mode)
        try:
            path.chmod(mode)
        except OSError as error:
            raise Gate8CliError("gate8-stage") from error
    for path in sorted(
        (item for item in root.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        _fsync_directory(path)
    _fsync_directory(root)
    _validate_tree(root, expected)


def _install_assembly(
    mode: str,
    output: Path,
    report_path: Path,
    roadmap_path: Path,
    assembly: Gate8Assembly,
) -> None:
    _no_symlink_ancestors(output.parent, "gate8-output")
    _no_symlink_ancestors(report_path.parent, "report-output")
    _no_symlink_ancestors(roadmap_path.parent, "roadmap-output")
    output_parent = _lstat(output.parent, "gate8-output")
    report_parent = _lstat(report_path.parent, "report-output")
    roadmap_parent = _lstat(roadmap_path.parent, "roadmap-output")
    if (
        not stat.S_ISDIR(output_parent.st_mode)
        or stat.S_ISLNK(output_parent.st_mode)
        or not stat.S_ISDIR(report_parent.st_mode)
        or stat.S_ISLNK(report_parent.st_mode)
        or not stat.S_ISDIR(roadmap_parent.st_mode)
        or stat.S_ISLNK(roadmap_parent.st_mode)
    ):
        _fail("report-output", 2)
    roadmap_raw = _regular_file(roadmap_path, "roadmap-output", 16 * _MAX_FILE_BYTES)
    if mode == "check":
        _private_directory(output, "gate8-output", empty=False)
        _validate_tree(output, assembly.tree_files)
        if _regular_file(report_path, "report-output") != assembly.report_raw:
            _fail("assembly-check-mismatch")
        m2_gate8.validate_candidate_ready_roadmap(roadmap_raw, assembly.report_raw)
        return
    if mode != "generate":
        _fail("assembly-mode", 2)
    if (
        output.exists()
        or output.is_symlink()
        or report_path.exists()
        or report_path.is_symlink()
    ):
        _fail("assembly-generate-precondition", 2)
    final_roadmap = m2_gate8.render_candidate_ready_roadmap(
        roadmap_raw, assembly.report_raw
    )
    stage = Path(tempfile.mkdtemp(prefix=".gate8-tree-", dir=output.parent))
    report_descriptor, report_name = tempfile.mkstemp(
        prefix=".m2-feasibility-", dir=report_path.parent
    )
    os.close(report_descriptor)
    report_stage = Path(report_name)
    roadmap_descriptor, roadmap_name = tempfile.mkstemp(
        prefix=".roadmap-candidate-ready-", dir=roadmap_path.parent
    )
    os.close(roadmap_descriptor)
    roadmap_stage = Path(roadmap_name)
    backup_descriptor, backup_name = tempfile.mkstemp(
        prefix=".roadmap-pre-gate8-", dir=roadmap_path.parent
    )
    os.close(backup_descriptor)
    roadmap_backup = Path(backup_name)
    tree_installed = False
    report_installed = False
    roadmap_installed = False
    try:
        os.chmod(stage, 0o700)
        report_stage.unlink()
        roadmap_stage.unlink()
        roadmap_backup.unlink()
        _write_tree(stage, assembly.tree_files)
        _write_fsynced(report_stage, assembly.report_raw, 0o644)
        _write_fsynced(roadmap_stage, final_roadmap, 0o644)
        _write_fsynced(roadmap_backup, roadmap_raw, 0o644)
        _fsync_directory(report_path.parent)
        _fsync_directory(roadmap_path.parent)
        if (
            output.exists()
            or output.is_symlink()
            or report_path.exists()
            or report_path.is_symlink()
            or _regular_file(
                roadmap_path, "roadmap-output", 16 * _MAX_FILE_BYTES
            )
            != roadmap_raw
        ):
            _fail("assembly-stale-precondition", 2)
        _rename_noreplace(stage, output)
        tree_installed = True
        _fsync_directory(output.parent)
        _validate_tree(output, assembly.tree_files)
        _rename_noreplace(report_stage, report_path)
        report_installed = True
        _fsync_directory(report_path.parent)
        if _regular_file(report_path, "report-output") != assembly.report_raw:
            _fail("assembly-postcondition")
        _validate_tree(output, assembly.tree_files)
        if (
            _regular_file(report_path, "report-output") != assembly.report_raw
            or _regular_file(
                roadmap_path, "roadmap-output", 16 * _MAX_FILE_BYTES
            )
            != roadmap_raw
        ):
            _fail("assembly-stale-precondition", 2)
        os.replace(roadmap_stage, roadmap_path)
        roadmap_installed = True
        _fsync_directory(roadmap_path.parent)
        if (
            _regular_file(roadmap_path, "roadmap-output", 16 * _MAX_FILE_BYTES)
            != final_roadmap
        ):
            _fail("assembly-postcondition")
        m2_gate8.validate_candidate_ready_roadmap(final_roadmap, assembly.report_raw)
        roadmap_backup.unlink()
        _fsync_directory(roadmap_path.parent)
    except BaseException as error:
        try:
            if roadmap_installed:
                if roadmap_backup.is_symlink():
                    _fail("assembly-rollback")
                if not roadmap_backup.exists():
                    _write_fsynced(roadmap_backup, roadmap_raw, 0o644)
                if (
                    _regular_file(
                        roadmap_backup,
                        "assembly-rollback",
                        16 * _MAX_FILE_BYTES,
                    )
                    != roadmap_raw
                ):
                    _fail("assembly-rollback")
                os.replace(roadmap_backup, roadmap_path)
                _fsync_directory(roadmap_path.parent)
                roadmap_installed = False
            if report_installed:
                if _regular_file(report_path, "assembly-rollback") != assembly.report_raw:
                    _fail("assembly-rollback")
                report_path.unlink()
                _fsync_directory(report_path.parent)
                report_installed = False
            if tree_installed:
                _validate_tree(output, assembly.tree_files)
                shutil.rmtree(output)
                _fsync_directory(output.parent)
                if output.exists() or output.is_symlink():
                    _fail("assembly-rollback")
                tree_installed = False
        except BaseException as rollback_error:
            raise Gate8CliError("assembly-rollback") from rollback_error
        if isinstance(error, OSError):
            raise Gate8CliError("assembly-write") from error
        raise
    finally:
        if report_stage.exists() and not report_stage.is_symlink():
            report_stage.unlink()
        if roadmap_stage.exists() and not roadmap_stage.is_symlink():
            roadmap_stage.unlink()
        if roadmap_backup.exists() and not roadmap_backup.is_symlink():
            roadmap_backup.unlink()
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)


def assemble(
    mode: str,
    candidate_root: Path,
    receipt_directory: Path,
    output: Path,
    report_path: Path,
) -> None:
    canonical_output = ROOT / "artifacts" / "gate8"
    canonical_report = ROOT / "reports" / "m2-feasibility-v0.json"
    if output != canonical_output or report_path != canonical_report:
        _fail("assembly-target", 2)
    _no_symlink_ancestors(output.parent, "assembly-target")
    _no_symlink_ancestors(report_path.parent, "assembly-target")
    output_parent = _lstat(output.parent, "assembly-target")
    report_parent = _lstat(report_path.parent, "assembly-target")
    if (
        not stat.S_ISDIR(output_parent.st_mode)
        or stat.S_ISLNK(output_parent.st_mode)
        or not stat.S_ISDIR(report_parent.st_mode)
        or stat.S_ISLNK(report_parent.st_mode)
    ):
        _fail("assembly-target", 2)
    if mode == "generate":
        if (
            output.exists()
            or output.is_symlink()
            or report_path.exists()
            or report_path.is_symlink()
        ):
            _fail("assembly-generate-precondition", 2)
    elif mode == "check":
        _private_directory(output, "gate8-output", empty=False)
        _regular_file(report_path, "report-output")
    else:
        _fail("assembly-mode", 2)
    _disjoint_paths(
        "assembly-root-alias",
        candidate_root,
        receipt_directory,
        output,
        report_path,
    )
    _disjoint_paths("assembly-source-alias", candidate_root, ROOT)
    _private_directory(candidate_root, "candidate-root", empty=True)
    receipts = _read_receipt_directory(receipt_directory, _PRODUCER_IDS)
    if set(receipts) != set(_PRODUCER_IDS):
        _fail("assembly-receipts", 2)
    ordered_receipts = {
        producer_id: receipts[producer_id] for producer_id in _PRODUCER_IDS
    }
    try:
        generated = _generate_python_gate_seven(candidate_root)
        assembly = _assemble_gate8(generated, ordered_receipts)
    finally:
        _cleanup_tree(candidate_root)
    _install_assembly(
        mode, output, report_path, ROOT / "docs" / "roadmap.md", assembly
    )


def _install_receipt(output: Path, producer_id: str, raw: bytes, mode: str) -> None:
    allowed = _PRODUCER_IDS if producer_id.startswith("native-") else (
        "linux-python",
        "linux-rust",
    )
    existing = _read_receipt_directory(output, allowed)
    path = output / f"{producer_id}.json"
    if mode == "generate":
        if producer_id in existing or path.exists() or path.is_symlink():
            _fail("producer-output", 2)
        descriptor, stage_name = tempfile.mkstemp(
            prefix=f".{producer_id}-", dir=output
        )
        os.close(descriptor)
        stage = Path(stage_name)
        try:
            stage.unlink()
            _write_fsynced(stage, raw)
            if _regular_file(stage, "producer-stage") != raw:
                _fail("producer-stage")
            _rename_noreplace(stage, path)
            _fsync_directory(output)
        except OSError as error:
            raise Gate8CliError("producer-output") from error
        finally:
            if stage.exists() and not stage.is_symlink():
                stage.unlink()
    elif mode == "check":
        if existing.get(producer_id) != raw:
            _fail("producer-check-mismatch")
    else:
        _fail("producer-mode", 2)


def producer(mode: str, producer_id: str, candidate_root: Path, output: Path) -> None:
    if producer_id not in _PYTHON_PRODUCER_IDS:
        _fail("producer-id", 2)
    allowed = _PRODUCER_IDS if producer_id == "native-python" else (
        "linux-python",
        "linux-rust",
    )
    _disjoint_paths("producer-root-alias", candidate_root, output)
    _disjoint_paths("producer-source-alias", candidate_root, ROOT)
    _private_directory(candidate_root, "candidate-root", empty=True)
    _private_directory(output, "output-directory", empty=False)
    _read_receipt_directory(output, allowed)
    try:
        generated = _generate_python_gate_seven(candidate_root)
        receipt = m2_gate8.render_producer_receipt(producer_id, generated.artifacts)
    finally:
        _cleanup_tree(candidate_root)
    _install_receipt(output, producer_id, receipt, mode)


def _phase_outputs_absent() -> None:
    policy = m2_gate8.load_gate8_policy(_owner("spec/gate8-policy-v0.toml"))
    phase = policy.get("phase_paths")
    if type(phase) is not dict or type(phase.get("gate8_exact_files")) is not list:
        _fail("phase-policy")
    paths = ["reports/m2-feasibility-v0.json", *phase["gate8_exact_files"]]
    for relative in paths:
        if type(relative) is not str:
            _fail("phase-policy")
        path = ROOT / relative
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise Gate8CliError("phase-presence", 2) from error
        _fail("phase-presence", 2)


def phase_check(phase: str, candidate_root: Path) -> None:
    if phase != "pre-gate8-clean":
        _fail("phase", 2)
    _disjoint_paths("phase-root-alias", candidate_root, ROOT)
    _phase_outputs_absent()
    _private_directory(candidate_root, "candidate-root", empty=True)
    try:
        _generate_python_gate_seven(candidate_root)
    finally:
        _cleanup_tree(candidate_root)


def prepare_linux_input(
    mode: str,
    native_python_path: Path,
    native_rust_path: Path,
    output: Path,
) -> None:
    if mode not in ("release-fresh", "standalone-retained"):
        _fail("linux-input-mode", 2)
    if native_python_path == native_rust_path:
        _fail("linux-input-receipts", 2)
    _disjoint_paths(
        "linux-input-alias",
        native_python_path,
        native_rust_path,
        output,
    )
    retained = ROOT / "artifacts" / "gate8" / "receipts"
    expected_retained = (
        retained / "native-python.json",
        retained / "native-rust.json",
    )
    supplied = (native_python_path, native_rust_path)
    if mode == "standalone-retained":
        if supplied != expected_retained:
            _fail("linux-input-mode", 2)
    elif supplied == expected_retained or any(
        path.parent == retained for path in supplied
    ):
        _fail("linux-input-mode", 2)
    _private_directory(output, "linux-input-output", empty=True)
    receipts = {
        producer_id: _regular_file(path, "linux-input-receipt")
        for producer_id, path in zip(_NATIVE_IDS, supplied, strict=True)
    }
    for producer_id in _NATIVE_IDS:
        m2_gate8.parse_producer_receipt(receipts[producer_id], producer_id)
    source_raw = m2_gate8.build_evidence_source_projection(ROOT)
    m2_gate8.validate_gate8_source_surface(
        source_raw, ROOT, _owner("spec/gate8-policy-v0.toml")
    )
    manifest = m2_gate8.render_linux_verification_input(source_raw, receipts)
    staged = Path(tempfile.mkdtemp(prefix=".gate8-linux-input-", dir=output))
    installed: list[Path] = []
    try:
        os.chmod(staged, 0o700)
        _write_fsynced(staged / "input-manifest.json", manifest)
        for producer_id in _NATIVE_IDS:
            _write_fsynced(staged / f"{producer_id}.json", receipts[producer_id])
        _fsync_directory(staged)
        m2_gate8.validate_linux_verification_input(
            _regular_file(staged / "input-manifest.json", "linux-input-stage"),
            source_raw,
            receipts,
        )
        for name in ("native-python.json", "native-rust.json", "input-manifest.json"):
            destination = output / name
            _rename_noreplace(staged / name, destination)
            installed.append(destination)
        _fsync_directory(output)
    except BaseException as error:
        for path in reversed(installed):
            try:
                metadata = path.lstat()
                if stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(
                    metadata.st_mode
                ):
                    path.unlink()
            except FileNotFoundError:
                pass
            except OSError as cleanup_error:
                raise Gate8CliError("linux-input-rollback") from cleanup_error
        if isinstance(error, OSError):
            raise Gate8CliError("linux-input-write") from error
        raise
    finally:
        if staged.exists() and not staged.is_symlink():
            shutil.rmtree(staged)
        _fsync_directory(output)


def _linux_native_input(directory: Path) -> tuple[dict[str, bytes], bytes]:
    _no_symlink_ancestors(directory, "linux-native-input")
    metadata = _lstat(directory, "linux-native-input")
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        _fail("linux-native-input", 2)
    try:
        entries = tuple(directory.iterdir())
    except OSError as error:
        raise Gate8CliError("linux-native-input", 2) from error
    if {path.name for path in entries} != {
        "input-manifest.json",
        "native-python.json",
        "native-rust.json",
    }:
        _fail("linux-native-input", 2)
    inodes: set[tuple[int, int]] = set()
    values = {}
    for path in entries:
        item = _lstat(path, "linux-native-input")
        inode = (item.st_dev, item.st_ino)
        if inode in inodes:
            _fail("linux-native-input", 2)
        inodes.add(inode)
        values[path.name] = _regular_file(path, "linux-native-input")
    receipts = {
        producer_id: values[f"{producer_id}.json"]
        for producer_id in _NATIVE_IDS
    }
    source_raw = m2_gate8.build_evidence_source_projection(ROOT)
    m2_gate8.validate_gate8_source_surface(
        source_raw, ROOT, _owner("spec/gate8-policy-v0.toml")
    )
    m2_gate8.validate_linux_verification_input(
        values["input-manifest.json"], source_raw, receipts
    )
    return receipts, source_raw


def verify_linux(
    candidate_root: Path,
    native_input_directory: Path,
    linux_output_directory: Path,
    gate8_work_root: Path,
) -> None:
    _disjoint_paths(
        "linux-work-root",
        candidate_root,
        native_input_directory,
        linux_output_directory,
        gate8_work_root,
    )
    _disjoint_paths("linux-candidate-source", candidate_root, ROOT)
    _disjoint_paths("linux-gate8-source", gate8_work_root, ROOT)
    _private_directory(candidate_root, "candidate-root", empty=True)
    _private_directory(gate8_work_root, "gate8-work-root", empty=True)
    native_receipts, source_raw = _linux_native_input(native_input_directory)
    linux_receipts = _read_receipt_directory(
        linux_output_directory, ("linux-python", "linux-rust")
    )
    if set(linux_receipts) != {"linux-python", "linux-rust"}:
        _fail("linux-output-receipts", 2)
    receipts = {
        "native-python": native_receipts["native-python"],
        "native-rust": native_receipts["native-rust"],
        "linux-python": linux_receipts["linux-python"],
        "linux-rust": linux_receipts["linux-rust"],
    }
    try:
        generated = _generate_python_gate_seven(candidate_root)
        assembly = _assemble_gate8(generated, receipts)
        staged_tree = gate8_work_root / "gate8"
        staged_tree.mkdir(mode=0o700)
        _write_tree(staged_tree, assembly.tree_files)
        staged_report = gate8_work_root / "m2-feasibility-v0.json"
        _write_fsynced(staged_report, assembly.report_raw, 0o644)
        _fsync_directory(gate8_work_root)
        _validate_tree(staged_tree, assembly.tree_files)
        if m2_gate8.build_evidence_source_projection(ROOT) != source_raw:
            _fail("linux-source-drift")
        tracked_report = _regular_file(
            ROOT / "reports/m2-feasibility-v0.json", "linux-report"
        )
        if tracked_report != assembly.report_raw:
            _fail("linux-report-mismatch")
    finally:
        _cleanup_tree(candidate_root)
        _cleanup_tree(gate8_work_root)


def _arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("reopen-provenance-fixtures", add_help=False)
    subcommands.add_parser("reopen-verifier", add_help=False)
    subcommands.add_parser("reopen-clean-linux-tests", add_help=False)
    subcommands.add_parser("reopen-candidate-ready-tests", add_help=False)
    subcommands.add_parser("reopen-candidate-ready-runtime-tests", add_help=False)
    subcommands.add_parser(
        "reopen-candidate-ready-clean-snapshot-tests", add_help=False
    )
    subcommands.add_parser(
        "reopen-candidate-ready-provenance-input", add_help=False
    )

    producer_parser = subcommands.add_parser("producer")
    producer_parser.add_argument("--mode", choices=("generate", "check"), required=True)
    producer_parser.add_argument("--producer-id", required=True)
    producer_parser.add_argument("--candidate-root", required=True)
    producer_parser.add_argument("--output-dir", required=True)

    phase_parser = subcommands.add_parser("phase-check")
    phase_parser.add_argument("--phase", required=True)
    phase_parser.add_argument("--candidate-root", required=True)

    linux_input = subcommands.add_parser("prepare-linux-input")
    linux_input.add_argument(
        "--mode", choices=("release-fresh", "standalone-retained"), required=True
    )
    linux_input.add_argument("--native-python-receipt", required=True)
    linux_input.add_argument("--native-rust-receipt", required=True)
    linux_input.add_argument("--output-dir", required=True)

    assembly = subcommands.add_parser("assemble")
    assembly.add_argument("--mode", choices=("generate", "check"), required=True)
    assembly.add_argument("--candidate-root", required=True)
    assembly.add_argument("--receipt-dir", required=True)
    assembly.add_argument("--output-dir", required=True)
    assembly.add_argument("--report-out", required=True)

    linux = subcommands.add_parser("verify-linux")
    linux.add_argument("--candidate-root", required=True)
    linux.add_argument("--native-input-dir", required=True)
    linux.add_argument("--linux-output-dir", required=True)
    linux.add_argument("--gate8-work-root", required=True)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    try:
        _source_root()
        parsed = _arguments(arguments)
        if parsed.command == "reopen-provenance-fixtures":
            reopen_provenance_fixtures()
        elif parsed.command == "reopen-verifier":
            reopen_verifier()
        elif parsed.command == "reopen-clean-linux-tests":
            reopen_clean_linux_tests()
        elif parsed.command == "reopen-candidate-ready-tests":
            reopen_candidate_ready_tests()
        elif parsed.command == "reopen-candidate-ready-runtime-tests":
            reopen_candidate_ready_runtime_tests()
        elif parsed.command == "reopen-candidate-ready-clean-snapshot-tests":
            reopen_candidate_ready_clean_snapshot_tests()
        elif parsed.command == "reopen-candidate-ready-provenance-input":
            reopen_candidate_ready_provenance_input()
        elif parsed.command == "producer":
            producer(
                parsed.mode,
                parsed.producer_id,
                _absolute_path(parsed.candidate_root, "candidate-root"),
                _absolute_path(parsed.output_dir, "output-directory"),
            )
        elif parsed.command == "phase-check":
            phase_check(
                parsed.phase,
                _absolute_path(parsed.candidate_root, "candidate-root"),
            )
        elif parsed.command == "prepare-linux-input":
            prepare_linux_input(
                parsed.mode,
                _absolute_path(
                    parsed.native_python_receipt, "linux-input-receipt"
                ),
                _absolute_path(parsed.native_rust_receipt, "linux-input-receipt"),
                _absolute_path(parsed.output_dir, "linux-input-output"),
            )
        elif parsed.command == "assemble":
            assemble(
                parsed.mode,
                _absolute_path(parsed.candidate_root, "candidate-root"),
                _absolute_path(parsed.receipt_dir, "receipt-directory"),
                _absolute_path(parsed.output_dir, "gate8-output"),
                _absolute_path(parsed.report_out, "report-output"),
            )
        elif parsed.command == "verify-linux":
            verify_linux(
                _absolute_path(parsed.candidate_root, "candidate-root"),
                _absolute_path(parsed.native_input_dir, "linux-native-input"),
                _absolute_path(parsed.linux_output_dir, "linux-output"),
                _absolute_path(parsed.gate8_work_root, "gate8-work-root"),
            )
        else:
            _fail("subcommand", 2)
    except Gate8CliError as error:
        diagnostic = f"M2 Gate-8 rejected: {error.reason}\n".encode("ascii")
        sys.stderr.buffer.write(diagnostic[:_MAX_ERROR_BYTES])
        return error.exit_code
    except (m2_gate8.Gate8Error, ValueError) as error:
        reason = getattr(error, "reason", "gate8")
        diagnostic = f"M2 Gate-8 rejected: {reason}\n".encode(
            "ascii", errors="replace"
        )
        sys.stderr.buffer.write(diagnostic[:_MAX_ERROR_BYTES])
        return 3
    except OSError:
        sys.stderr.buffer.write(b"M2 Gate-8 rejected: io-failure\n")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
