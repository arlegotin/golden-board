#!/usr/bin/env python3
"""Strict check/create/gate7 lifecycle for the sole promoted M2 R3 candidate."""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
import errno
from hashlib import sha256
import os
from pathlib import Path
import select
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import NoReturn, Sequence


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "python"))

from golden_board import (  # noqa: E402
    canonical_manifest,
    m2_carrier,
    m2_codec,
    m2_damage,
    m2_independence,
    m2_policy,
    m2_recipe,
)
from tools.m2 import generate_candidates  # noqa: E402


PROFILE_ID = m2_damage.R3_PROFILE_ID
PROFILE_IDS = (PROFILE_ID,)
CANDIDATE_ROOT = ROOT / "artifacts" / "candidates" / PROFILE_ID
DAMAGE_DIRECTORY = CANDIDATE_ROOT / "damage"
ROOT_FILES = ("damage-manifest.json",) + tuple(
    f"damage-D{index}.json" for index in range(8)
)
INDEPENDENCE_FILE = "independence-proof.json"
MAX_ARTIFACT_BYTES = 1_048_576
MAX_GATE6_FILES = 10_047
MAX_POST_GATE7_FILES = 10_048
MAX_AGGREGATE_BYTES = 536_870_912
RUST_DECODER = ROOT / "target" / "release" / "gb-r3-damage-decoder"
RUST_PROOF = ROOT / "target" / "release" / "gb-r3-independence-proof"


class DamageWriterError(ValueError):
    __slots__ = ("reason",)

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class R3DamageInputs:
    workspace: Path
    candidate_root: Path
    manifestation: m2_carrier.Manifestation
    profile: m2_codec.CandidateProfile
    profile_policy_raw: bytes
    profile_limits_raw: bytes
    damage_policy_raw: bytes
    bootstrap_spec_raw: bytes
    route_data_raw: bytes
    recipient_package_raw: bytes
    alternate_route_data_raw: bytes


@dataclass(frozen=True, slots=True)
class ExistingDamageBundle:
    values: dict[str, bytes]
    admitted: m2_damage.DamageBundleV1
    proof_raw: bytes | None


def _fail(reason: str) -> NoReturn:
    raise DamageWriterError(reason)


def _read_owner(workspace: Path, relative: str) -> bytes:
    path = workspace / relative
    raw, _ = _real_regular(path, "owner-read")
    return raw


def _lstat(path: Path, reason: str) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as error:
        raise DamageWriterError(reason) from error


def _real_directory(path: Path, reason: str) -> os.stat_result:
    metadata = _lstat(path, reason)
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        _fail(reason)
    return metadata


def _real_regular(
    path: Path,
    reason: str,
    *,
    maximum_bytes: int = MAX_ARTIFACT_BYTES,
) -> tuple[bytes, tuple[int, int]]:
    metadata = _lstat(path, reason)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_nlink != 1
        or not 1 <= metadata.st_size <= maximum_bytes
    ):
        _fail(reason)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise DamageWriterError(reason) from error
    if len(raw) != metadata.st_size:
        _fail(reason)
    return raw, (metadata.st_dev, metadata.st_ino)


def _within_workspace(workspace: Path, path: Path, reason: str) -> None:
    if not isinstance(workspace, Path) or not isinstance(path, Path):
        _fail(reason)
    workspace_absolute = Path(os.path.abspath(workspace))
    path_absolute = Path(os.path.abspath(path))
    _real_directory(workspace_absolute, reason)
    try:
        relative = path_absolute.relative_to(workspace_absolute)
    except ValueError:
        _fail(reason)
    cursor = workspace_absolute
    for component in relative.parts:
        cursor /= component
        if cursor.exists() or cursor.is_symlink():
            _real_directory(cursor, reason)


def _candidate_manifestation(
    workspace: Path,
    candidate_root: Path,
    *,
    allowed_stage: Path | None = None,
) -> m2_carrier.Manifestation:
    _within_workspace(workspace, candidate_root, "candidate-path")
    _real_directory(candidate_root, "candidate-path")
    allowed_names = set(generate_candidates.R3_ALLOWLIST)
    damage_path = candidate_root / "damage"
    if damage_path.exists() or damage_path.is_symlink():
        _real_directory(damage_path, "candidate-damage-path")
        allowed_names.add("damage")
    if allowed_stage is not None:
        if allowed_stage.parent != candidate_root:
            _fail("candidate-stage")
        _real_directory(allowed_stage, "candidate-stage")
        allowed_names.add(allowed_stage.name)
    try:
        entries = tuple(candidate_root.iterdir())
    except OSError as error:
        raise DamageWriterError("candidate-path") from error
    if {entry.name for entry in entries} != allowed_names:
        _fail("candidate-allowlist")
    values: dict[str, bytes] = {}
    inodes: set[tuple[int, int]] = set()
    for name in generate_candidates.R3_ALLOWLIST:
        expected_size, expected_sha256 = generate_candidates.R3_ARTIFACT_SPECS[
            name
        ]
        raw, inode = _real_regular(
            candidate_root / name,
            "candidate-artifact",
            maximum_bytes=max(MAX_ARTIFACT_BYTES, expected_size),
        )
        if (
            len(raw) != expected_size
            or sha256(raw).hexdigest() != expected_sha256
            or inode in inodes
        ):
            _fail("candidate-artifact")
        inodes.add(inode)
        values[name] = raw
    manifestation = m2_carrier.Manifestation(
        PROFILE_ID,
        *(values[name] for name in generate_candidates.R3_ALLOWLIST),
    )
    try:
        generated = generate_candidates._r3_artifact_map(manifestation)
    except generate_candidates.CandidateWriterError as error:
        raise DamageWriterError("candidate-artifact") from error
    if generated != values:
        _fail("candidate-artifact")
    return manifestation


def _owner_inputs(
    workspace: Path = ROOT,
    candidate_root: Path = CANDIDATE_ROOT,
    *,
    allowed_stage: Path | None = None,
) -> R3DamageInputs:
    manifestation = _candidate_manifestation(
        workspace, candidate_root, allowed_stage=allowed_stage
    )
    profile_raw = _read_owner(workspace, "spec/profile-policy-v1.toml")
    limits_raw = _read_owner(workspace, "spec/profile-limits-v1.toml")
    damage_raw = _read_owner(workspace, "spec/damage-policy-v1.toml")
    bootstrap_raw = _read_owner(workspace, "spec/bootstrap-v1.md")
    route_raw = _read_owner(workspace, "spec/route-data-v1.json")
    package_raw = m2_recipe.build_r3_recipe_package()
    try:
        decoder_policy = m2_policy.load_r3_decoder_policy(
            profile_raw, limits_raw, damage_raw
        )
    except m2_policy.PolicyError as error:
        raise DamageWriterError("owner-admission") from error
    if (
        decoder_policy.protected_units != 1_841
        or decoder_policy.encoded_transport_bytes != 397_656
        or decoder_policy.registry_profiles[0].profile_id != PROFILE_ID
    ):
        _fail("owner-admission")
    return R3DamageInputs(
        workspace,
        candidate_root,
        manifestation,
        m2_codec.r3_candidate_profile(
            protected_units=decoder_policy.protected_units,
            encoded_transport_bytes=decoder_policy.encoded_transport_bytes,
        ),
        profile_raw,
        limits_raw,
        damage_raw,
        bootstrap_raw,
        route_raw,
        package_raw,
        _read_owner(workspace, "spec/route-data-v0.json"),
    )


def _shard_names(family_raws: Sequence[bytes]) -> tuple[str, ...]:
    names: list[str] = []
    for family_index, raw in enumerate(family_raws):
        try:
            value = canonical_manifest.validate_canonical_manifest(raw)
        except (TypeError, ValueError) as error:
            raise DamageWriterError("family-manifest") from error
        refs = value.get("shard_rows") if type(value) is dict else None
        if (
            type(value) is not dict
            or value.get("schema") != m2_damage.R3_FAMILY_SCHEMA
            or value.get("family_id") != f"D{family_index}"
            or type(refs) is not list
            or not refs
        ):
            _fail("family-manifest")
        for ordinal, row in enumerate(refs):
            if type(row) is not dict or row.get("shard_ordinal") != ordinal:
                _fail("family-manifest")
            names.append(f"damage-D{family_index}-cases-{ordinal:04d}.json")
    if len(set(names)) != len(names):
        _fail("shard-name")
    return tuple(names)


def _validate_gate6_values(
    values: dict[str, bytes], inputs: R3DamageInputs
) -> m2_damage.DamageBundleV1:
    if type(values) is not dict or any(
        type(name) is not str or type(raw) is not bytes
        for name, raw in values.items()
    ):
        _fail("gate6-values")
    try:
        family_raws = tuple(values[name] for name in ROOT_FILES[1:])
        shard_names = _shard_names(family_raws)
        expected = {*ROOT_FILES, *shard_names}
        if set(values) != expected:
            _fail("gate6-allowlist")
        admitted = m2_damage.validate_damage_bundle_v1(
            values[ROOT_FILES[0]],
            family_raws,
            tuple((name, values[name]) for name in shard_names),
            inputs.damage_policy_raw,
            inputs.profile_policy_raw,
            inputs.profile_limits_raw,
            inputs.bootstrap_spec_raw,
            inputs.route_data_raw,
            inputs.recipient_package_raw,
            inputs.manifestation.candidate_manifest,
            inputs.manifestation.carrier,
        )
    except KeyError as error:
        raise DamageWriterError("gate6-allowlist") from error
    except m2_damage.DamageError as error:
        raise DamageWriterError("gate6-admission") from error
    return admitted


def _artifact_map(
    run: m2_damage.DamageRun, inputs: R3DamageInputs
) -> dict[str, bytes]:
    if (
        type(run) is not m2_damage.DamageRun
        or run.profile_id != PROFILE_ID
        or type(run.manifest) is not bytes
        or type(run.manifest_identity) is not str
        or type(run.family_manifests) is not tuple
        or len(run.family_manifests) != 8
        or type(run.case_shards) is not tuple
        or run.case_count != 10_038
        or run.family_case_counts
        != tuple(zip(m2_damage.R3_FAMILY_IDS, m2_damage.R3_FAMILY_CASE_COUNTS))
        or not isinstance(run.wrong_accept_count, int)
        or run.gate6_result not in {"pass", "fail"}
        or run.gate7_result != "not_evaluated"
    ):
        _fail("damage-result")
    values = dict(
        zip(ROOT_FILES, (run.manifest, *run.family_manifests), strict=True)
    )
    for name, raw in run.case_shards:
        if (
            type(name) is not str
            or type(raw) is not bytes
            or name in values
            or "/" in name
            or "\\" in name
            or name == INDEPENDENCE_FILE
        ):
            _fail("artifact-name")
        values[name] = raw
    admitted = _validate_gate6_values(values, inputs)
    root_summary = admitted.root["summary"]
    if (
        run.manifest_identity != root_summary["manifest_identity"]
        or run.wrong_accept_count != root_summary["wrong_accept_count"]
        or run.gate6_result != admitted.result
    ):
        _fail("damage-result-binding")
    return values


def _read_damage_directory(
    inputs: R3DamageInputs,
    directory: Path | None = None,
    *,
    allow_proof: bool = True,
) -> ExistingDamageBundle:
    damage = inputs.candidate_root / "damage" if directory is None else directory
    _real_directory(damage, "damage-directory")
    try:
        entries = tuple(damage.iterdir())
    except OSError as error:
        raise DamageWriterError("damage-directory") from error
    maximum_files = MAX_POST_GATE7_FILES if allow_proof else MAX_GATE6_FILES
    if not 9 <= len(entries) <= maximum_files:
        _fail("damage-file-count")
    values: dict[str, bytes] = {}
    inodes: set[tuple[int, int]] = set()
    aggregate = 0
    for path in entries:
        if path.name in values:
            _fail("damage-allowlist")
        raw, inode = _real_regular(path, "damage-file")
        if inode in inodes:
            _fail("damage-hardlink")
        inodes.add(inode)
        aggregate += len(raw)
        if aggregate > MAX_AGGREGATE_BYTES:
            _fail("damage-aggregate")
        values[path.name] = raw
    proof_raw = values.pop(INDEPENDENCE_FILE, None)
    if proof_raw is not None and not allow_proof:
        _fail("damage-proof-unexpected")
    admitted = _validate_gate6_values(values, inputs)
    return ExistingDamageBundle(values, admitted, proof_raw)


def _write_fsynced(path: Path, raw: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise DamageWriterError("stage-write") from error


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise DamageWriterError("directory-fsync") from error


def _cleanup_private_stage(path: Path) -> None:
    if path.is_symlink():
        _fail("stage-cleanup")
    if path.exists():
        _real_directory(path, "stage-cleanup")
        try:
            shutil.rmtree(path)
        except OSError as error:
            raise DamageWriterError("stage-cleanup") from error
    if path.exists() or path.is_symlink():
        _fail("stage-cleanup")
    _fsync_directory(path.parent)


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
            _fail("publish-race")
        raise DamageWriterError("publish-rename") from OSError(
            observed_errno, os.strerror(observed_errno)
        )


def persist_gate6(
    inputs: R3DamageInputs, values: dict[str, bytes]
) -> str:
    """Validate and atomically publish only the complete gate-6 directory."""

    _validate_gate6_values(values, inputs)
    destination = inputs.candidate_root / "damage"
    if destination.exists() or destination.is_symlink():
        existing = _read_damage_directory(inputs)
        if existing.proof_raw is not None or existing.values != values:
            _fail("existing-mismatch")
        return "unchanged"
    stage = Path(
        tempfile.mkdtemp(prefix=".m2-damage-stage-", dir=inputs.candidate_root)
    )
    try:
        for name in sorted(values):
            _write_fsynced(stage / name, values[name])
        _fsync_directory(stage)
        staged_inputs = _owner_inputs(
            inputs.workspace, inputs.candidate_root, allowed_stage=stage
        )
        staged = _read_damage_directory(
            staged_inputs, stage, allow_proof=False
        )
        if staged.values != values:
            _fail("stage-mismatch")
        current_inputs = _owner_inputs(
            inputs.workspace, inputs.candidate_root, allowed_stage=stage
        )
        if current_inputs.manifestation != inputs.manifestation:
            _fail("candidate-drift")
        if destination.exists() or destination.is_symlink():
            _fail("publish-race")
        _rename_noreplace(stage, destination)
        _fsync_directory(inputs.candidate_root)
        observed_inputs = _owner_inputs(inputs.workspace, inputs.candidate_root)
        observed = _read_damage_directory(observed_inputs)
        if observed.values != values or observed.proof_raw is not None:
            _fail("publish-postcondition")
    finally:
        _cleanup_private_stage(stage)
    return "created"


def check_existing(
    workspace: Path = ROOT,
    candidate_root: Path = CANDIDATE_ROOT,
    rust_proof_binary: Path | None = None,
) -> str:
    """Validate existing evidence only; never start damage generation."""

    inputs = _owner_inputs(workspace, candidate_root)
    existing = _read_damage_directory(inputs)
    if existing.proof_raw is None:
        return (
            "gate6-pass-awaiting-gate7"
            if existing.admitted.result == "pass"
            else "gate6-fail"
        )
    if existing.admitted.result != "pass":
        _fail("proof-after-failed-gate6")
    binary = (
        _build_rust_binary("gb-r3-independence-proof")
        if rust_proof_binary is None
        else rust_proof_binary
    )
    proof = _crosscheck_retained_proof(inputs, existing, binary)
    return f"gate7-{proof.result}"


def _toolchain() -> tuple[Path, Path]:
    resolved: list[Path] = []
    for name in ("cargo", "rustc"):
        try:
            result = subprocess.run(
                ("rustup", "which", "--toolchain", "1.97.1", name),
                cwd=ROOT,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise DamageWriterError("rust-toolchain") from error
        path = Path(result.stdout.strip())
        if (
            "\n" in result.stdout.strip()
            or not path.is_absolute()
            or path.is_symlink()
            or not path.is_file()
            or not os.access(path, os.X_OK)
        ):
            _fail("rust-toolchain")
        resolved.append(path)
    return resolved[0], resolved[1]


def _build_rust_binary(name: str) -> Path:
    if name not in {"gb-r3-damage-decoder", "gb-r3-independence-proof"}:
        _fail("rust-binary-name")
    cargo, rustc = _toolchain()
    environment = os.environ.copy()
    environment["RUSTC"] = str(rustc)
    try:
        subprocess.run(
            (
                str(cargo),
                "build",
                "--release",
                "--locked",
                "--offline",
                "-p",
                "gb-bootstrap",
                "--bin",
                name,
            ),
            cwd=ROOT,
            env=environment,
            check=True,
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise DamageWriterError("rust-build") from error
    path = ROOT / "target" / "release" / name
    metadata = _lstat(path, "rust-binary")
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or not os.access(path, os.X_OK)
    ):
        _fail("rust-binary")
    return path


def create_gate6(
    rust_decoder_command: Sequence[str],
    worker_count: int,
) -> str:
    """Explicitly run the first v7 damage corpus and publish gate 6 only."""

    inputs = _owner_inputs()
    destination = inputs.candidate_root / "damage"
    if destination.exists() or destination.is_symlink():
        return check_existing()
    rebuilt = generate_candidates.build_r3_candidate()
    if rebuilt != inputs.manifestation:
        _fail("candidate-python-mismatch")
    with tempfile.TemporaryDirectory(
        prefix="golden-board-r3-gate6-preflight-", dir="/tmp"
    ) as directory:
        rust_values = generate_candidates._emit_r3_rust(
            Path(directory) / "candidate"
        )
        generate_candidates.compare_r3_rust_emission(rust_values, rebuilt)
        alternate_package = generate_candidates._emit_package(3, Path(directory))
        run = m2_damage.run_damage(
            inputs.manifestation,
            inputs.profile,
            inputs.profile_policy_raw,
            inputs.profile_limits_raw,
            inputs.damage_policy_raw,
            inputs.route_data_raw,
            alternate_package,
            rust_decoder_command,
            worker_count,
            inputs.alternate_route_data_raw,
        )
    return persist_gate6(inputs, _artifact_map(run, inputs))


def _gate7_input_raws(
    existing: ExistingDamageBundle,
) -> tuple[bytes, tuple[bytes, ...], tuple[bytes, ...]]:
    family_raws = tuple(existing.values[name] for name in ROOT_FILES[1:])
    shard_names = _shard_names(family_raws)
    try:
        return (
            existing.values[ROOT_FILES[0]],
            family_raws,
            tuple(existing.values[name] for name in shard_names),
        )
    except KeyError as error:
        raise DamageWriterError("gate7-inputs") from error


def _build_python_proof(
    inputs: R3DamageInputs, existing: ExistingDamageBundle
) -> m2_independence.IndependenceProof:
    damage_raw, family_raws, shard_raws = _gate7_input_raws(existing)
    try:
        return m2_independence.build_independence_proof_v1(
            inputs.manifestation.candidate_manifest,
            inputs.manifestation.ownership_ledger,
            damage_raw,
            family_raws,
            shard_raws,
        )
    except m2_independence.IndependenceError as error:
        raise DamageWriterError("proof-python") from error


def _validate_proof_bytes(
    raw: bytes,
    inputs: R3DamageInputs,
    existing: ExistingDamageBundle,
) -> m2_independence.IndependenceProof:
    damage_raw, family_raws, shard_raws = _gate7_input_raws(existing)
    try:
        return m2_independence.validate_independence_proof_v1(
            raw,
            inputs.manifestation.candidate_manifest,
            inputs.manifestation.ownership_ledger,
            damage_raw,
            family_raws,
            shard_raws,
        )
    except m2_independence.IndependenceError as error:
        raise DamageWriterError("proof-admission") from error


def _snapshot_gate7_inputs(
    stage: Path,
    inputs: R3DamageInputs,
    existing: ExistingDamageBundle,
) -> tuple[Path, Path, Path, ExistingDamageBundle]:
    """Write and re-admit an inode-distinct, fsynced proof input snapshot."""

    _real_directory(stage, "proof-stage")
    candidate_path = stage / "candidate-manifest.json"
    ownership_path = stage / "ownership-ledger.json"
    damage_path = stage / "damage"
    try:
        damage_path.mkdir(mode=0o700)
    except OSError as error:
        raise DamageWriterError("proof-stage") from error
    _write_fsynced(candidate_path, inputs.manifestation.candidate_manifest)
    _write_fsynced(ownership_path, inputs.manifestation.ownership_ledger)
    for name in sorted(existing.values):
        _write_fsynced(damage_path / name, existing.values[name])
    _fsync_directory(damage_path)
    _fsync_directory(stage)

    try:
        stage_entries = tuple(stage.iterdir())
    except OSError as error:
        raise DamageWriterError("proof-stage") from error
    if {path.name for path in stage_entries} != {
        candidate_path.name,
        ownership_path.name,
        damage_path.name,
    }:
        _fail("proof-stage-allowlist")
    _real_directory(damage_path, "proof-stage")
    inodes: set[tuple[int, int]] = set()
    for path, expected in (
        (candidate_path, inputs.manifestation.candidate_manifest),
        (ownership_path, inputs.manifestation.ownership_ledger),
    ):
        raw, inode = _real_regular(path, "proof-stage-file")
        if raw != expected or inode in inodes:
            _fail("proof-stage-file")
        inodes.add(inode)
    try:
        damage_entries = tuple(damage_path.iterdir())
    except OSError as error:
        raise DamageWriterError("proof-stage-file") from error
    for path in damage_entries:
        raw, inode = _real_regular(path, "proof-stage-file")
        if existing.values.get(path.name) != raw or inode in inodes:
            _fail("proof-stage-file")
        inodes.add(inode)
    staged = _read_damage_directory(inputs, damage_path, allow_proof=False)
    if staged.values != existing.values or staged.proof_raw is not None:
        _fail("proof-stage-mismatch")
    return candidate_path, ownership_path, damage_path, staged


def _run_rust_proof(
    binary: Path,
    candidate_path: Path,
    ownership_path: Path,
    damage_path: Path,
) -> bytes:
    """Run the pinned Rust proof CLI with a bounded stdout artifact channel."""

    metadata = _lstat(binary, "rust-proof-binary")
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or not os.access(binary, os.X_OK)
    ):
        _fail("rust-proof-binary")
    binary_identity = (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
    )
    try:
        process = subprocess.Popen(
            (
                str(binary),
                str(candidate_path),
                str(ownership_path),
                str(damage_path),
            ),
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise DamageWriterError("rust-proof-run") from error
    if process.stdout is None:
        process.kill()
        process.wait()
        _fail("rust-proof-run")
    output = bytearray()
    deadline = time.monotonic() + 600.0
    descriptor = process.stdout.fileno()
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.wait()
                _fail("rust-proof-timeout")
            readable, _, _ = select.select((descriptor,), (), (), remaining)
            if not readable:
                process.kill()
                process.wait()
                _fail("rust-proof-timeout")
            chunk = os.read(descriptor, 65_536)
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > MAX_ARTIFACT_BYTES:
                process.kill()
                process.wait()
                _fail("rust-proof-output")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            process.kill()
            process.wait()
            _fail("rust-proof-timeout")
        return_code = process.wait(timeout=remaining)
    except DamageWriterError:
        raise
    except (OSError, subprocess.SubprocessError) as error:
        if process.poll() is None:
            process.kill()
            process.wait()
        raise DamageWriterError("rust-proof-run") from error
    finally:
        process.stdout.close()
    observed = _lstat(binary, "rust-proof-binary")
    if (
        return_code != 0
        or not output
        or (
            observed.st_dev,
            observed.st_ino,
            observed.st_size,
            observed.st_mtime_ns,
        )
        != binary_identity
    ):
        _fail("rust-proof-result")
    return bytes(output)


def _revalidate_gate7_current(
    inputs: R3DamageInputs,
    existing: ExistingDamageBundle,
    stage: Path,
) -> tuple[R3DamageInputs, ExistingDamageBundle]:
    current_inputs = _owner_inputs(
        inputs.workspace, inputs.candidate_root, allowed_stage=stage
    )
    if current_inputs != inputs:
        _fail("gate7-owner-drift")
    current = _read_damage_directory(current_inputs)
    if (
        current.values != existing.values
        or current.proof_raw != existing.proof_raw
        or current.admitted.result != existing.admitted.result
    ):
        _fail("gate7-input-drift")
    return current_inputs, current


def _crosscheck_retained_proof(
    inputs: R3DamageInputs,
    existing: ExistingDamageBundle,
    binary: Path,
) -> m2_independence.IndependenceProof:
    if existing.proof_raw is None or existing.admitted.result != "pass":
        _fail("proof-crosscheck-state")
    stage = Path(
        tempfile.mkdtemp(prefix=".m2-proof-check-", dir=inputs.candidate_root)
    )
    try:
        candidate_path, ownership_path, damage_path, staged = (
            _snapshot_gate7_inputs(stage, inputs, existing)
        )
        python_proof = _build_python_proof(inputs, staged)
        rust_raw = _run_rust_proof(
            binary, candidate_path, ownership_path, damage_path
        )
        if (
            rust_raw != python_proof.raw
            or existing.proof_raw != python_proof.raw
        ):
            _fail("proof-independent-disagreement")
        admitted = _validate_proof_bytes(rust_raw, inputs, staged)
        if admitted != python_proof:
            _fail("proof-independent-disagreement")
        _revalidate_gate7_current(inputs, existing, stage)
        return admitted
    finally:
        _cleanup_private_stage(stage)


def _create_gate7_with_binary(
    binary: Path,
    workspace: Path = ROOT,
    candidate_root: Path = CANDIDATE_ROOT,
) -> str:
    inputs = _owner_inputs(workspace, candidate_root)
    existing = _read_damage_directory(inputs)
    if existing.admitted.result != "pass":
        _fail("gate7-after-failed-gate6")

    stage = Path(
        tempfile.mkdtemp(prefix=".m2-proof-stage-", dir=inputs.candidate_root)
    )
    try:
        candidate_path, ownership_path, damage_path, staged = (
            _snapshot_gate7_inputs(stage, inputs, existing)
        )
        python_proof = _build_python_proof(inputs, staged)
        rust_raw = _run_rust_proof(
            binary, candidate_path, ownership_path, damage_path
        )
        if rust_raw != python_proof.raw:
            _fail("proof-independent-disagreement")
        admitted_proof = _validate_proof_bytes(rust_raw, inputs, staged)
        if admitted_proof != python_proof:
            _fail("proof-independent-disagreement")

        _, current = _revalidate_gate7_current(inputs, existing, stage)
        if current.proof_raw is not None:
            if current.proof_raw != python_proof.raw:
                _fail("existing-proof-mismatch")
            return "unchanged"

        staged_proof = stage / INDEPENDENCE_FILE
        _write_fsynced(staged_proof, python_proof.raw)
        _fsync_directory(stage)
        raw, inode = _real_regular(staged_proof, "proof-stage-file")
        if raw != python_proof.raw:
            _fail("proof-stage-file")
        for path in (
            candidate_path,
            ownership_path,
            *(damage_path / name for name in sorted(existing.values)),
        ):
            _, other_inode = _real_regular(path, "proof-stage-file")
            if inode == other_inode:
                _fail("proof-stage-file")

        _, current = _revalidate_gate7_current(inputs, existing, stage)
        if current.proof_raw is not None:
            _fail("proof-publish-race")
        destination = inputs.candidate_root / "damage" / INDEPENDENCE_FILE
        if destination.exists() or destination.is_symlink():
            _fail("proof-publish-race")
        _rename_noreplace(staged_proof, destination)
        _fsync_directory(destination.parent)
        observed_inputs = _owner_inputs(
            inputs.workspace, inputs.candidate_root, allowed_stage=stage
        )
        observed = _read_damage_directory(observed_inputs)
        if (
            observed.values != existing.values
            or observed.proof_raw != python_proof.raw
        ):
            _fail("proof-publish-postcondition")
        _validate_proof_bytes(observed.proof_raw, observed_inputs, observed)
        return f"created-{python_proof.result}"
    finally:
        _cleanup_private_stage(stage)


def create_gate7() -> str:
    """Render, compare, and atomically add only the gate-7 proof."""

    return _create_gate7_with_binary(
        _build_rust_binary("gb-r3-independence-proof")
    )


def _parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    maximum_workers = min(8, os.cpu_count() or 1)
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--check",
        action="store_true",
        help="validate existing evidence only (also the default mode)",
    )
    modes.add_argument(
        "--create",
        action="store_true",
        help="explicitly run and atomically publish the first gate-6 corpus",
    )
    modes.add_argument(
        "--gate7",
        action="store_true",
        help="add only the independently reproduced gate-7 proof",
    )
    parser.add_argument(
        "--workers",
        type=int,
        choices=range(1, maximum_workers + 1),
        default=maximum_workers,
    )
    return parser.parse_args(arguments)


def main() -> int:
    arguments = _parse_arguments()
    if arguments.create:
        rust_decoder = _build_rust_binary("gb-r3-damage-decoder")
        status = create_gate6((str(rust_decoder),), arguments.workers)
    elif arguments.gate7:
        status = create_gate7()
    else:
        status = check_existing()
    print(f"m2 damage evidence: {status}: {DAMAGE_DIRECTORY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
