#!/usr/bin/env python3
"""Regenerate and atomically retain the exact P6 gate-5 evidence."""

from __future__ import annotations

import argparse
from hashlib import sha256
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import NoReturn


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from golden_board import (  # noqa: E402
    canonical_manifest,
    capacity,
    curriculum,
    m2_carrier,
    m2_codec,
    m2_policy,
    m2_recipe,
    m2_slice,
)


P1 = "eh72-r2-crc32c-v0"
P3 = "eh72-r3-crc32c-v0"
P7 = "eh72-hier-r5-r2-r1-crc32c-v0"
ALLOWLIST = (
    f"{P1}/semantic-envelope.json",
    f"{P1}/carrier.obs-bits",
    f"{P1}/candidate-manifest.json",
    f"{P1}/ownership-ledger.json",
    f"{P1}/capacity-ledger.json",
    f"{P1}/density-ledger.json",
    f"{P3}/semantic-envelope.json",
    f"{P3}/carrier.obs-bits",
    f"{P3}/candidate-manifest.json",
    f"{P3}/ownership-ledger.json",
    f"{P3}/capacity-ledger.json",
    f"{P3}/density-ledger.json",
)
MAX_ARTIFACT_BYTES = 1_048_576
R3_ALLOWLIST = (
    "semantic-envelope.json",
    "carrier.obs-bits",
    "candidate-manifest.json",
    "ownership-ledger.json",
    "capacity-ledger.json",
    "density-ledger.json",
)
R3_ARTIFACT_SPECS = {
    "semantic-envelope.json": (
        376_036,
        "f81e29b04b307b147aec1c2602933c778e1c9198084e5d5c8e4e29cad1bdb0fd",
    ),
    "carrier.obs-bits": (
        520_204,
        "c6309da5f199a237b8fc79292a5135581ad0f9b517fbe9516770ebaf084d49b0",
    ),
    "candidate-manifest.json": (
        675_827,
        "38839aa28561ff2bec0997a80d8dc938e876526c25f40e23b6a78844f8fc1d86",
    ),
    "ownership-ledger.json": (
        478_010,
        "fe82dc8119d77a855e7227dea95a673e3fb2ffb5a9c513cf31a169ea53ee5d12",
    ),
    "capacity-ledger.json": (
        673_935,
        "a6e4a9b5e6a78a3ecf7d42ebbe75b0fa84258b6931183e37109dc927d0f9d2c6",
    ),
    "density-ledger.json": (
        1_157,
        "6e931df836f063e1de96ee73514ca91b4ddd59071bc8338bdd5a79244fcbee61",
    ),
}
R3_RUST_CANONICAL_NAMES = {
    "semantic-envelope-v0.json": "semantic-envelope.json",
    "carrier-v7.obs-bits": "carrier.obs-bits",
    "candidate-manifest-v1.json": "candidate-manifest.json",
    "ownership-ledger-v1.json": "ownership-ledger.json",
    "capacity-ledger-v1.json": "capacity-ledger.json",
    "density-ledger-v0.json": "density-ledger.json",
}
R3_RUST_EMISSION_SPECS = {
    "ARTIFACT-SHA256": (
        1_191,
        "0fb0a9b81a051effa79a2978012ebb3e769f661a434dbd5308b133f9ca47c164",
    ),
    "METRICS": (
        1_891,
        "83761a4b1e2ee617207b51e0d4522d614ce76994c86565a702037320b1f7b990",
    ),
    "candidate-manifest-v1.json": R3_ARTIFACT_SPECS[
        "candidate-manifest.json"
    ],
    "capacity-ledger-v1.json": R3_ARTIFACT_SPECS["capacity-ledger.json"],
    "carrier-v7.obs-bits": R3_ARTIFACT_SPECS["carrier.obs-bits"],
    "cell-ownership-v1.bin": (
        37_454_400,
        "693cea7fe092903ffde3ea292667baf3043a06c8a36c26fa2142088eb2c190ad",
    ),
    "density-ledger-v0.json": R3_ARTIFACT_SPECS["density-ledger.json"],
    "ownership-ledger-v1.json": R3_ARTIFACT_SPECS[
        "ownership-ledger.json"
    ],
    "recipient-package-v7.bin": (
        25_930,
        "4bd8e0d485ae6e6a65f4edc4ef2aaac9585a2bcd8c4623e44d69f1dad3b0ec8e",
    ),
    "route-prefix-v1-sector-0.bin": (
        29_091,
        "a3a9ac59b857af3904d2bff998bd96c36ccba4d8a97180ad8e0e9d4434b92395",
    ),
    "route-prefix-v1-sector-1.bin": (
        29_091,
        "4da3722a786890647ece291a3fbcb14ba9f2c6a847c13088f2c47792a52c861a",
    ),
    "route-prefix-v1-sector-2.bin": (
        29_091,
        "7c55f1be66239d4c48a0760217a31d0cd36b30a8d04ac91c17a67315a04c4fbb",
    ),
    "route-prefix-v1-sector-3.bin": (
        29_091,
        "5daca7964260360c62877969618e5756a946ee2d5f2b2d78756e29f5c63d44a1",
    ),
    "semantic-envelope-v0.json": R3_ARTIFACT_SPECS[
        "semantic-envelope.json"
    ],
}


class CandidateWriterError(ValueError):
    pass


def _fail(reason: str) -> NoReturn:
    raise CandidateWriterError(reason)


def _read(relative: str) -> bytes:
    return (ROOT / relative).read_bytes()


def _artifact_map(
    profile_one: m2_carrier.Manifestation,
    profile_three: m2_carrier.Manifestation,
) -> dict[str, bytes]:
    if (
        type(profile_one) is not m2_carrier.Manifestation
        or type(profile_three) is not m2_carrier.Manifestation
        or profile_one.profile_id != P1
        or profile_three.profile_id != P3
    ):
        _fail("artifact-type")
    for profile_id, manifestation in ((P1, profile_one), (P3, profile_three)):
        try:
            candidate = canonical_manifest.validate_canonical_manifest(
                manifestation.candidate_manifest
            )
            ownership = canonical_manifest.validate_canonical_manifest(
                manifestation.ownership_ledger
            )
            capacity_ledger = canonical_manifest.validate_canonical_manifest(
                manifestation.capacity_ledger
            )
            density = canonical_manifest.validate_canonical_manifest(
                manifestation.density_ledger
            )
        except (TypeError, ValueError) as error:
            raise CandidateWriterError("artifact-manifest") from error
        if (
            candidate.get("profile_id") != profile_id
            or candidate.get("semantic_envelope_sha256")
            != sha256(manifestation.semantic_envelope).hexdigest()
            or candidate.get("carrier_sha256")
            != sha256(manifestation.carrier).hexdigest()
            or candidate.get("ownership_sha256")
            != sha256(manifestation.ownership_ledger).hexdigest()
            or candidate.get("capacity_ledger_sha256")
            != sha256(manifestation.capacity_ledger).hexdigest()
            or candidate.get("density_ledger_sha256")
            != sha256(manifestation.density_ledger).hexdigest()
            or ownership.get("profile_id") != profile_id
            or capacity_ledger.get("profile_id") != profile_id
            or density.get("profile_id") != profile_id
        ):
            _fail("artifact-binding")
    values = dict(
        zip(
            ALLOWLIST,
            (
                profile_one.semantic_envelope,
                profile_one.carrier,
                profile_one.candidate_manifest,
                profile_one.ownership_ledger,
                profile_one.capacity_ledger,
                profile_one.density_ledger,
                profile_three.semantic_envelope,
                profile_three.carrier,
                profile_three.candidate_manifest,
                profile_three.ownership_ledger,
                profile_three.capacity_ledger,
                profile_three.density_ledger,
            ),
            strict=True,
        )
    )
    if any(not 1 <= len(value) <= MAX_ARTIFACT_BYTES for value in values.values()):
        _fail("artifact-size")
    return values


def persist_candidates(
    output: Path,
    profile_one: m2_carrier.Manifestation,
    profile_three: m2_carrier.Manifestation,
) -> str:
    """Create the exact allowlisted tree atomically, or verify an exact rerun."""

    if not isinstance(output, Path) or output.name in ("", ".", ".."):
        _fail("output")
    values = _artifact_map(profile_one, profile_three)
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        _fail("existing-target")
    if output.exists():
        observed: set[str] = set()
        observed_directories: set[str] = set()
        for path in output.rglob("*"):
            if path.is_symlink() or (not path.is_file() and not path.is_dir()):
                _fail("existing-type")
            if path.is_file():
                relative = path.relative_to(output).as_posix()
                if not any(
                    relative.startswith(f"{profile_id}/damage/")
                    for profile_id in (P1, P3)
                ):
                    observed.add(relative)
            else:
                relative = path.relative_to(output).as_posix()
                if not any(
                    relative == f"{profile_id}/damage"
                    or relative.startswith(f"{profile_id}/damage/")
                    for profile_id in (P1, P3)
                ):
                    observed_directories.add(relative)
        if (
            observed != set(ALLOWLIST)
            or observed_directories != {P1, P3}
        ):
            _fail("existing-allowlist")
        if any((output / relative).read_bytes() != value for relative, value in values.items()):
            _fail("existing-mismatch")
        return "unchanged"

    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".m2-candidates-stage-", dir=output.parent))
    try:
        for relative, value in values.items():
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(value)
        observed = {
            path.relative_to(stage).as_posix()
            for path in stage.rglob("*")
            if path.is_file()
        }
        if observed != set(ALLOWLIST):
            _fail("stage-allowlist")
        os.replace(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return "created"


def _r3_artifact_map(
    manifestation: m2_carrier.Manifestation,
) -> dict[str, bytes]:
    if (
        type(manifestation) is not m2_carrier.Manifestation
        or manifestation.profile_id != P7
    ):
        _fail("r3-artifact-type")
    values = dict(
        zip(
            R3_ALLOWLIST,
            (
                manifestation.semantic_envelope,
                manifestation.carrier,
                manifestation.candidate_manifest,
                manifestation.ownership_ledger,
                manifestation.capacity_ledger,
                manifestation.density_ledger,
            ),
            strict=True,
        )
    )
    if any(type(raw) is not bytes for raw in values.values()):
        _fail("r3-artifact-type")
    for name, raw in values.items():
        expected_size, expected_sha256 = R3_ARTIFACT_SPECS[name]
        if (
            len(raw) != expected_size
            or sha256(raw).hexdigest() != expected_sha256
        ):
            _fail("r3-artifact-identity")
    try:
        semantic = canonical_manifest.validate_canonical_manifest(
            manifestation.semantic_envelope
        )
        candidate = canonical_manifest.validate_canonical_manifest(
            manifestation.candidate_manifest
        )
        ownership = canonical_manifest.validate_canonical_manifest(
            manifestation.ownership_ledger
        )
        capacity_ledger = canonical_manifest.validate_canonical_manifest(
            manifestation.capacity_ledger
        )
        density = canonical_manifest.validate_canonical_manifest(
            manifestation.density_ledger
        )
    except (TypeError, ValueError) as error:
        raise CandidateWriterError("r3-artifact-manifest") from error
    if (
        semantic.get("schema") != "golden-board.m2-semantic-envelope/v0"
        or candidate.get("schema") != "golden-board.m2-candidate-manifest/v1"
        or candidate.get("profile_id") != P7
        or candidate.get("semantic_envelope_sha256")
        != R3_ARTIFACT_SPECS["semantic-envelope.json"][1]
        or candidate.get("carrier_sha256")
        != R3_ARTIFACT_SPECS["carrier.obs-bits"][1]
        or candidate.get("ownership_sha256")
        != R3_ARTIFACT_SPECS["ownership-ledger.json"][1]
        or candidate.get("capacity_ledger_sha256")
        != R3_ARTIFACT_SPECS["capacity-ledger.json"][1]
        or candidate.get("density_ledger_sha256")
        != R3_ARTIFACT_SPECS["density-ledger.json"][1]
        or ownership.get("schema") != "golden-board.m2-ownership-ledger/v1"
        or ownership.get("profile_id") != P7
        or capacity_ledger.get("schema")
        != "golden-board.m2-capacity-ledger/v1"
        or capacity_ledger.get("profile_id") != P7
        or density.get("schema") != "golden-board.m2-density-ledger/v0"
        or density.get("profile_id") != P7
        or int.from_bytes(manifestation.carrier[:4], "big") != 4_161_600
        or len(manifestation.carrier) != 4 + (4_161_600 + 7) // 8
    ):
        _fail("r3-artifact-binding")
    return values


def _validate_output_root(output: Path) -> None:
    if not isinstance(output, Path) or output.name in ("", ".", ".."):
        _fail("output")
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        _fail("output-type")


def _read_exact_regular(
    path: Path,
    expected_size: int,
    expected_sha256: str,
    reason: str,
) -> bytes:
    try:
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size != expected_size
        ):
            _fail(reason)
        raw = path.read_bytes()
    except OSError as error:
        raise CandidateWriterError(reason) from error
    if len(raw) != expected_size or sha256(raw).hexdigest() != expected_sha256:
        _fail(reason)
    return raw


def _verify_r3_directory(
    output: Path,
    values: dict[str, bytes] | None = None,
) -> None:
    target = output / P7
    if target.is_symlink() or not target.is_dir():
        _fail("r3-existing-target")
    try:
        entries = list(target.iterdir())
    except OSError as error:
        raise CandidateWriterError("r3-existing-target") from error
    damage_entries = [path for path in entries if path.name == "damage"]
    if damage_entries:
        damage = damage_entries[0]
        try:
            metadata = damage.lstat()
        except OSError as error:
            raise CandidateWriterError("r3-existing-allowlist") from error
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            _fail("r3-existing-allowlist")
    if len(entries) != len(R3_ALLOWLIST) + len(damage_entries):
        _fail("r3-existing-allowlist")
    observed: dict[str, bytes] = {}
    for path in entries:
        if path.name == "damage":
            continue
        if path.name not in R3_ARTIFACT_SPECS:
            _fail("r3-existing-allowlist")
        expected_size, expected_sha256 = R3_ARTIFACT_SPECS[path.name]
        observed[path.name] = _read_exact_regular(
            path,
            expected_size,
            expected_sha256,
            "r3-existing-mismatch",
        )
    if set(observed) != set(R3_ALLOWLIST):
        _fail("r3-existing-allowlist")
    if values is not None and any(
        observed[name] != values[name] for name in R3_ALLOWLIST
    ):
        _fail("r3-existing-mismatch")


def verify_r3_candidate(
    output: Path,
    manifestation: m2_carrier.Manifestation,
) -> str:
    """Verify only the canonical v7 directory without traversing R2 history."""

    _validate_output_root(output)
    if not output.is_dir():
        _fail("r3-existing-target")
    _verify_r3_directory(output, _r3_artifact_map(manifestation))
    return "verified"


def _admit_r3_canonical_context(output: Path, *, regeneration: bool) -> None:
    if type(regeneration) is not bool:
        _fail("r3-regeneration-mode")
    _validate_output_root(output)
    canonical_output = ROOT / "artifacts/candidates"
    try:
        if (
            not output.exists()
            or output.resolve(strict=True) != canonical_output.resolve(strict=True)
        ):
            _fail("r3-canonical-output")
    except OSError as error:
        raise CandidateWriterError("r3-canonical-output") from error
    damage_path = ROOT / "spec/damage-policy-v1.toml"
    if damage_path.is_symlink() or not damage_path.is_file():
        _fail("r3-archive-owner")
    try:
        damage_raw = damage_path.read_bytes()
        m2_policy.validate_r3_pre_clarification_archive(ROOT, damage_raw)
        m2_policy.validate_r3_pre_damage_schema_archive(ROOT, damage_raw)
        m2_policy.validate_r3_pre_independence_witness_archive(
            ROOT, damage_raw
        )
        m2_policy.validate_r3_pre_gate6_convergence_archive(
            ROOT, damage_raw
        )
    except m2_policy.PolicyError as error:
        raise CandidateWriterError(f"r3-archive:{error.reason}") from error
    target = output / P7
    if regeneration:
        if target.exists() or target.is_symlink():
            _fail("r3-regeneration-precondition")
    else:
        _verify_r3_directory(output)


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def persist_r3_candidate(
    output: Path,
    manifestation: m2_carrier.Manifestation,
) -> str:
    """Atomically create or exactly verify the sole active v7 directory."""

    _validate_output_root(output)
    values = _r3_artifact_map(manifestation)
    target = output / P7
    if target.is_symlink():
        _fail("r3-existing-target")
    if target.exists():
        _verify_r3_directory(output, values)
        return "unchanged"
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise CandidateWriterError("output-create") from error
    _validate_output_root(output)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{P7}.stage-", dir=output)
    )
    try:
        for name in R3_ALLOWLIST:
            destination = stage / name
            with destination.open("xb") as stream:
                stream.write(values[name])
                stream.flush()
                os.fsync(stream.fileno())
        _fsync_directory(stage)
        stage_entries = list(stage.iterdir())
        if (
            len(stage_entries) != len(R3_ALLOWLIST)
            or any(path.name not in R3_ARTIFACT_SPECS for path in stage_entries)
        ):
            _fail("r3-stage-allowlist")
        staged = {
            path.name: _read_exact_regular(
                path,
                *R3_ARTIFACT_SPECS[path.name],
                "r3-stage-mismatch",
            )
            for path in stage_entries
        }
        if set(staged) != set(R3_ALLOWLIST) or any(
            staged[name] != values[name] for name in R3_ALLOWLIST
        ):
            _fail("r3-stage-allowlist")
        if target.is_symlink() or target.exists():
            _fail("r3-existing-target")
        os.replace(stage, target)
        _fsync_directory(output)
    except OSError as error:
        raise CandidateWriterError("r3-atomic-write") from error
    finally:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
    _verify_r3_directory(output, values)
    return "created"


def _validate_r3_rust_emission(directory: Path) -> dict[str, bytes]:
    if directory.is_symlink() or not directory.is_dir():
        _fail("r3-rust-emission")
    try:
        entries = list(directory.iterdir())
    except OSError as error:
        raise CandidateWriterError("r3-rust-emission") from error
    if len(entries) != len(R3_RUST_EMISSION_SPECS):
        _fail("r3-rust-allowlist")
    loaded: dict[str, bytes] = {}
    for path in entries:
        spec = R3_RUST_EMISSION_SPECS.get(path.name)
        if spec is None:
            _fail("r3-rust-allowlist")
        loaded[path.name] = _read_exact_regular(
            path, *spec, "r3-rust-identity"
        )
    if set(loaded) != set(R3_RUST_EMISSION_SPECS):
        _fail("r3-rust-allowlist")
    hashed_names = set(R3_RUST_EMISSION_SPECS) - {"ARTIFACT-SHA256", "METRICS"}
    expected_inventory = "".join(
        f"{R3_RUST_EMISSION_SPECS[name][1]}  "
        f"{R3_RUST_EMISSION_SPECS[name][0]}  {name}\n"
        for name in sorted(hashed_names)
    ).encode("ascii")
    if loaded["ARTIFACT-SHA256"] != expected_inventory:
        _fail("r3-rust-inventory")
    return {
        canonical_name: loaded[rust_name]
        for rust_name, canonical_name in R3_RUST_CANONICAL_NAMES.items()
    }


def _emit_r3_rust(directory: Path) -> dict[str, bytes]:
    try:
        temporary_root = Path("/tmp").resolve(strict=True)
        resolved_parent = directory.parent.resolve(strict=True)
    except (AttributeError, OSError) as error:
        raise CandidateWriterError("r3-rust-output") from error
    if (
        not isinstance(directory, Path)
        or not directory.is_absolute()
        or not resolved_parent.is_relative_to(temporary_root)
        or directory.is_symlink()
        or directory.exists()
    ):
        _fail("r3-rust-output")
    try:
        rustc = subprocess.run(
            ["rustup", "which", "--toolchain", "1.97.1", "rustc"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        ).stdout.strip()
        if subprocess.run(
            [rustc, "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        ).stdout.split(maxsplit=2)[:2] != ["rustc", "1.97.1"]:
            _fail("r3-rust-toolchain")
        environment = dict(os.environ)
        environment["RUSTC"] = rustc
        completed = subprocess.run(
            [
                "rustup",
                "run",
                "1.97.1",
                "cargo",
                "run",
                "-q",
                "--locked",
                "--offline",
                "-p",
                "gb-bootstrap",
                "--example",
                "r3_carrier",
                "--",
                str(directory),
            ],
            cwd=ROOT,
            env=environment,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise CandidateWriterError("r3-rust-emitter") from error
    if completed.stdout != f"{directory}\n":
        _fail("r3-rust-emitter-output")
    return _validate_r3_rust_emission(directory)


def compare_r3_rust_emission(
    rust_values: dict[str, bytes],
    manifestation: m2_carrier.Manifestation,
) -> None:
    python_values = _r3_artifact_map(manifestation)
    if (
        type(rust_values) is not dict
        or set(rust_values) != set(R3_ALLOWLIST)
        or any(type(raw) is not bytes for raw in rust_values.values())
        or rust_values != python_values
    ):
        _fail("r3-cross-language-mismatch")


def _emit_package(profile_version: int, directory: Path) -> bytes:
    environment = dict(os.environ)
    if "RUSTC" not in environment:
        environment["RUSTC"] = subprocess.run(
            ["rustup", "which", "--toolchain", "1.97.1", "rustc"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
            timeout=30,
        ).stdout.strip()
    output = directory / f"eh-{profile_version}.bin"
    subprocess.run(
        [
            "rustup", "run", "1.97.1", "cargo", "run", "-q", "--locked",
            "--offline", "-p", "gb-bootstrap", "--example", "dump_eh_package",
            "--", str(profile_version), str(output),
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
    )
    return output.read_bytes()


def generate_r2(output: Path) -> str:
    """Historical R2 regeneration entry point; never called by R3 admission."""

    profile_raw = _read("spec/profile-policy-v0.toml")
    limits_raw = _read("spec/profile-limits-v0.toml")
    damage_raw = _read("spec/damage-policy-v0.toml")
    bootstrap_raw = _read("spec/bootstrap-v0.md")
    route_raw = _read("spec/route-data-v0.json")
    compiled = m2_slice.compile_slice_v0(
        _read("studies/m2/slice-v0.json"),
        _read("conformance/content-v0.json"),
        _read("conformance/chess-v0.json"),
        _read("reports/game-set-v0.bin"),
        _read("spec/content-v0.md"),
        _read("spec/constants-v0.toml"),
        _read("spec/curriculum-v0.toml"),
    )
    inputs = capacity.derive_capacity_inputs(
        compiled, curriculum.load_blueprint(_read("spec/curriculum-v0.toml"))
    )
    policy = m2_policy.load_profile_policy(profile_raw)
    envelope = capacity.derive_capacity_envelope(inputs, policy.capacity_policy)
    profiles = m2_codec.load_candidate_profiles(profile_raw, limits_raw)
    common = (
        profile_raw, limits_raw, damage_raw, bootstrap_raw, compiled, inputs,
        envelope, route_raw,
    )
    with tempfile.TemporaryDirectory(prefix="golden-board-p6-packages-") as directory:
        package_directory = Path(directory)
        p1 = m2_carrier.build_p6_outcome(
            profiles[0], *common, _emit_package(1, package_directory)
        )
        p3 = m2_carrier.build_p6_outcome(
            profiles[2], *common, _emit_package(3, package_directory)
        )
    if (
        p1.gate5_result != "pass"
        or p1.failure_reason is not None
        or p1.manifestation is None
        or p1.elimination_bound is not None
        or p3.gate5_result != "pass"
        or p3.failure_reason is not None
        or p3.manifestation is None
        or p3.elimination_bound is not None
    ):
        _fail("p6-outcome")
    return persist_candidates(output, p1.manifestation, p3.manifestation)


def _r3_route_receipt(
    implementation_id: str,
    route_manifest_raw: bytes,
) -> bytes:
    try:
        route = canonical_manifest.validate_canonical_manifest(
            route_manifest_raw
        )
        generated = route["generated"]
        if type(generated) is not dict:
            _fail("r3-route-owner")
        return canonical_manifest.serialize_manifest(
            {
                "implementation_id": implementation_id,
                "recipient_package_sha256": generated[
                    "recipient_package_sha256"
                ],
                "reproduction_projection_sha256": generated[
                    "reproduction_projection_sha256"
                ],
                "route_data_template_sha256": generated[
                    "route_data_template_sha256"
                ],
                "route_sha256": generated["route_sha256"],
                "schema": "golden-board.m2-r3-route-reproduction/v1",
            }
        )
    except (KeyError, TypeError, ValueError) as error:
        raise CandidateWriterError("r3-route-owner") from error


def build_r3_candidate() -> m2_carrier.Manifestation:
    """Strictly rebuild the sole promoted v7 candidate in Python."""

    base_profile_raw = _read("spec/profile-policy-v0.toml")
    profile_raw = _read("spec/profile-policy-v1.toml")
    limits_raw = _read("spec/profile-limits-v1.toml")
    damage_raw = _read("spec/damage-policy-v1.toml")
    bootstrap_raw = _read("spec/bootstrap-v1.md")
    route_raw = _read("spec/route-data-v1.json")
    compiled = m2_slice.compile_slice_v0(
        _read("studies/m2/slice-v0.json"),
        _read("conformance/content-v0.json"),
        _read("conformance/chess-v0.json"),
        _read("reports/game-set-v0.bin"),
        _read("spec/content-v0.md"),
        _read("spec/constants-v0.toml"),
        _read("spec/curriculum-v0.toml"),
    )
    inputs = capacity.derive_capacity_inputs(
        compiled, curriculum.load_blueprint(_read("spec/curriculum-v0.toml"))
    )
    base_policy = m2_policy.load_profile_policy(base_profile_raw)
    envelope = capacity.derive_capacity_envelope(
        inputs, base_policy.capacity_policy
    )
    package = m2_recipe.build_r3_recipe_package()
    proof = m2_carrier.R3CarrierOwnerProof(
        _read("spec/m2-r3-owner-promotion-v1.toml"),
        _read("conformance/m2-r3-owner-v1.json"),
        base_profile_raw,
        _r3_route_receipt("python", route_raw),
        _r3_route_receipt("rust", route_raw),
        m2_policy.render_r3_limits_reproduction_receipt(
            "python", limits_raw, route_raw
        ),
        m2_policy.render_r3_limits_reproduction_receipt(
            "rust", limits_raw, route_raw
        ),
    )
    profile = m2_codec.r3_candidate_profile(
        protected_units=1_841,
        encoded_transport_bytes=397_656,
    )
    outcome = m2_carrier.build_p6_outcome(
        profile,
        profile_raw,
        limits_raw,
        damage_raw,
        bootstrap_raw,
        compiled,
        inputs,
        envelope,
        route_raw,
        package,
        r3_owner_proof=proof,
    )
    if (
        outcome.profile_id != P7
        or outcome.gate5_result != "pass"
        or outcome.failure_reason is not None
        or outcome.elimination_bound is not None
        or outcome.manifestation is None
    ):
        _fail("r3-p6-outcome")
    _r3_artifact_map(outcome.manifestation)
    return outcome.manifestation


def generate(output: Path, *, write: bool = True) -> str:
    """Regenerate only when absent, or verify the exact tracked six files."""

    if type(write) is not bool:
        _fail("mode")
    _admit_r3_canonical_context(output, regeneration=write)
    if not write:
        return "verified"
    manifestation = build_r3_candidate()
    with tempfile.TemporaryDirectory(
        prefix="golden-board-r3-rust-candidate-", dir="/tmp"
    ) as parent:
        rust_values = _emit_r3_rust(Path(parent) / "emission")
        compare_r3_rust_emission(rust_values, manifestation)
    return persist_r3_candidate(output, manifestation)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "candidates",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify archive admission and the existing v7 directory without writing",
    )
    arguments = parser.parse_args()
    status = generate(arguments.output, write=not arguments.check)
    print(f"m2 candidate evidence: {status}: {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
