"""Closed, result-free tests for the M2 pre-result policy barrier."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from hashlib import sha256
import os
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest
from unittest import mock

from golden_board import (
    canonical_manifest,
    capacity,
    curriculum,
    m2_carrier,
    m2_codec,
    m2_policy,
    m2_recipe,
    m2_route_data,
    m2_slice,
)


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> bytes:
    return (ROOT / path).read_bytes()


def _gf_mul(left: int, right: int) -> int:
    product = 0
    for _ in range(8):
        if right & 1:
            product ^= left
        high = left & 0x80
        left = (left << 1) & 0xFF
        if high:
            left ^= 0x1D
        right >>= 1
    return product


def _gf_pow(value: int, exponent: int) -> int:
    product = 1
    while exponent:
        if exponent & 1:
            product = _gf_mul(product, value)
        value = _gf_mul(value, value)
        exponent >>= 1
    return product


def _alpha_pow(exponent: int) -> int:
    return _gf_pow(2, exponent % 255)


def _gf_inverse(value: int) -> int:
    if not value:
        raise ValueError("zero inverse")
    return _gf_pow(value, 254)


def _poly_mul(left: list[int], right: list[int]) -> list[int]:
    product = [0] * (len(left) + len(right) - 1)
    for left_index, left_value in enumerate(left):
        for right_index, right_value in enumerate(right):
            product[left_index + right_index] ^= _gf_mul(left_value, right_value)
    return product


def _poly_eval_ascending(polynomial: list[int], value: int) -> int:
    result = 0
    for coefficient in reversed(polynomial):
        result = _gf_mul(result, value) ^ coefficient
    return result


def _rs_generator() -> bytes:
    polynomial = [1]
    for exponent in range(64):
        polynomial = _poly_mul(polynomial, [1, _alpha_pow(exponent)])
    return bytes(polynomial)


def _rs_encode(data: bytes, generator: bytes) -> bytes:
    if len(data) != 191 or len(generator) != 65:
        raise ValueError("RS shape")
    work = bytearray(data + bytes(64))
    for index in range(191):
        coefficient = work[index]
        for generator_index in range(1, 65):
            work[index + generator_index] ^= _gf_mul(
                coefficient, generator[generator_index]
            )
    return data + bytes(work[191:])


def _rs_syndromes(word: bytes) -> list[int]:
    if len(word) != 255:
        raise ValueError("RS word")
    result = []
    for exponent in range(64):
        point = _alpha_pow(exponent)
        value = 0
        for coefficient in word:
            value = _gf_mul(value, point) ^ coefficient
        result.append(value)
    return result


def _berlekamp_massey(sequence: list[int]) -> tuple[list[int], int]:
    connection = [1]
    prior_connection = [1]
    degree = 0
    shift = 1
    prior_discrepancy = 1
    for index, item in enumerate(sequence):
        discrepancy = item
        for subindex in range(1, degree + 1):
            if subindex < len(connection):
                discrepancy ^= _gf_mul(connection[subindex], sequence[index - subindex])
        if discrepancy == 0:
            shift += 1
            continue
        old_connection = connection.copy()
        scale = _gf_mul(discrepancy, _gf_inverse(prior_discrepancy))
        required = len(prior_connection) + shift
        connection.extend([0] * max(0, required - len(connection)))
        for subindex, coefficient in enumerate(prior_connection):
            connection[subindex + shift] ^= _gf_mul(scale, coefficient)
        if 2 * degree <= index:
            degree = index + 1 - degree
            prior_connection = old_connection
            prior_discrepancy = discrepancy
            shift = 1
        else:
            shift += 1
    while len(connection) > 1 and connection[-1] == 0:
        connection.pop()
    return connection, degree


def _rs_decode_reference(
    observation: bytes, erasures: list[int]
) -> tuple[int, bytes | None, dict[str, bytes | list[int]]]:
    if (
        len(observation) != 255
        or any(type(position) is not int for position in erasures)
        or any(not 0 <= position <= 254 for position in erasures)
        or any(left >= right for left, right in zip(erasures, erasures[1:]))
    ):
        return 3, None, {}
    if len(erasures) > 64:
        return 4, None, {}
    working = bytearray(observation)
    for position in erasures:
        working[position] = 0
    syndromes = _rs_syndromes(bytes(working))
    if not erasures and not any(syndromes):
        return (
            0,
            bytes(working),
            {
                "syndromes": bytes(syndromes),
                "positions": [],
                "magnitudes": [],
            },
        )
    erasure_locator = [1]
    for position in erasures:
        erasure_locator = _poly_mul(erasure_locator, [1, _alpha_pow(254 - position)])
    transformed = []
    for index in range(64):
        value = 0
        for subindex in range(min(index, len(erasures)) + 1):
            value ^= _gf_mul(erasure_locator[subindex], syndromes[index - subindex])
        transformed.append(value)
    bm_input = transformed[len(erasures) :]
    unknown_locator, unknown_degree = _berlekamp_massey(bm_input)
    if (
        len(unknown_locator) != unknown_degree + 1
        or len(unknown_locator) > 33
        or 2 * unknown_degree + len(erasures) > 64
    ):
        return 4, None, {}
    locator = _poly_mul(erasure_locator, unknown_locator)
    if len(locator) > 65 or len(locator) - 1 != len(erasures) + unknown_degree:
        return 4, None, {}
    roots = [
        position
        for position in range(255)
        if _poly_eval_ascending(locator, _alpha_pow(position + 1)) == 0
    ]
    erasure_set = set(erasures)
    if (
        len(roots) != len(locator) - 1
        or not erasure_set.issubset(roots)
        or sum(position not in erasure_set for position in roots) != unknown_degree
    ):
        return 5, None, {}
    evaluator = _poly_mul(syndromes, locator)[:64]
    evaluator.extend([0] * (64 - len(evaluator)))
    derivative = [
        locator[index] if index % 2 else 0 for index in range(1, len(locator))
    ]
    corrections: list[tuple[int, int]] = []
    for position in roots:
        location = _alpha_pow(254 - position)
        argument = _alpha_pow(position + 1)
        denominator = _poly_eval_ascending(derivative, argument)
        if denominator == 0:
            return 5, None, {}
        magnitude = _gf_mul(
            location,
            _gf_mul(
                _poly_eval_ascending(evaluator, argument),
                _gf_inverse(denominator),
            ),
        )
        if magnitude == 0 and position not in erasure_set:
            return 5, None, {}
        corrections.append((position, magnitude))
    error_count = sum(
        position not in erasure_set and magnitude != 0
        for position, magnitude in corrections
    )
    if error_count != unknown_degree or 2 * error_count + len(erasures) > 64:
        return 5, None, {}
    for position, magnitude in corrections:
        working[position] ^= magnitude
    if any(_rs_syndromes(bytes(working))):
        return 5, None, {}
    return (
        0,
        bytes(working),
        {
            "syndromes": bytes(syndromes),
            "erasure_locator": bytes(erasure_locator),
            "transformed": bytes(transformed),
            "bm_input": bytes(bm_input),
            "unknown_locator": bytes(unknown_locator),
            "locator": bytes(locator),
            "evaluator": bytes(evaluator),
            "positions": [position for position, _ in corrections],
            "magnitudes": [magnitude for _, magnitude in corrections],
        },
    )


class M2PolicyFreeze(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile_raw = _read("spec/profile-policy-v0.toml")
        cls.damage_raw = _read("spec/damage-policy-v0.toml")
        cls.limits_raw = _read("spec/profile-limits-v0.toml")
        cls.profile = m2_policy.load_profile_policy(cls.profile_raw)
        cls.damage = m2_policy.load_damage_policy(cls.damage_raw)
        cls.rs_fixture_raw = _read("conformance/rs255-191-v0.json")
        cls.rs_fixture = canonical_manifest.validate_canonical_manifest(
            cls.rs_fixture_raw
        )
        compiled = m2_slice.compile_slice_v0(
            _read("studies/m2/slice-v0.json"),
            _read("conformance/content-v0.json"),
            _read("conformance/chess-v0.json"),
            _read("reports/game-set-v0.bin"),
            _read("spec/content-v0.md"),
            _read("spec/constants-v0.toml"),
            _read("spec/curriculum-v0.toml"),
        )
        blueprint = curriculum.load_blueprint(_read("spec/curriculum-v0.toml"))
        cls.inputs = capacity.derive_capacity_inputs(compiled, blueprint)
        cls.r3_bootstrap_raw = _read("spec/bootstrap-v1.md")
        tracked_profile_raw = _read("spec/profile-policy-v1.toml")
        tracked_damage_raw = _read("spec/damage-policy-v1.toml")
        tracked_promotion_raw = _read(
            "spec/m2-r3-owner-promotion-v1.toml"
        )
        archive_owner_root = ROOT / (
            "artifacts/history/m2-r3-pre-d7-mapping-clarification/owners"
        )
        archived_damage_raw = (
            archive_owner_root / "damage-policy-v1.toml"
        ).read_bytes()
        archived_limits_raw = (
            archive_owner_root / "profile-limits-v1.toml"
        ).read_bytes()
        archived_promotion_raw = (
            archive_owner_root / "m2-r3-owner-promotion-v1.toml"
        ).read_bytes()
        schema_archive_owner_root = ROOT / (
            "artifacts/history/m2-r3-pre-damage-artifact-schema-"
            "clarification/owners"
        )
        schema_archived_damage_raw = (
            schema_archive_owner_root / "damage-policy-v1.toml"
        ).read_bytes()
        schema_archived_limits_raw = (
            schema_archive_owner_root / "profile-limits-v1.toml"
        ).read_bytes()
        schema_archived_promotion_raw = (
            schema_archive_owner_root / "m2-r3-owner-promotion-v1.toml"
        ).read_bytes()
        witness_archive_owner_root = ROOT / (
            "artifacts/history/m2-r3-pre-independence-witness-"
            "clarification/owners"
        )
        witness_archived_damage_raw = (
            witness_archive_owner_root / "damage-policy-v1.toml"
        ).read_bytes()
        witness_archived_limits_raw = (
            witness_archive_owner_root / "profile-limits-v1.toml"
        ).read_bytes()
        witness_archived_promotion_raw = (
            witness_archive_owner_root / "m2-r3-owner-promotion-v1.toml"
        ).read_bytes()
        convergence_archive_owner_root = ROOT / (
            "artifacts/history/m2-r3-pre-gate6-convergence-"
            "clarification/owners"
        )
        convergence_archived_damage_raw = (
            convergence_archive_owner_root / "damage-policy-v1.toml"
        ).read_bytes()
        convergence_archived_limits_raw = (
            convergence_archive_owner_root / "profile-limits-v1.toml"
        ).read_bytes()
        convergence_archived_promotion_raw = (
            convergence_archive_owner_root
            / "m2-r3-owner-promotion-v1.toml"
        ).read_bytes()
        cls.r3_owner_fixture_raw = _read("conformance/m2-r3-owner-v1.json")
        cls.r3_package = m2_recipe.build_r3_recipe_package()
        r3_profile = m2_codec.r3_candidate_profile(
            protected_units=1_841,
            encoded_transport_bytes=397_656,
        )
        envelope = capacity.derive_capacity_envelope(
            cls.inputs, cls.profile.capacity_policy
        )
        semantic = canonical_manifest.validate_canonical_manifest(
            m2_carrier.render_semantic_envelope(compiled, cls.inputs, envelope)
        )
        capacity_projection = m2_carrier.derive_r3_capacity_projection(
            r3_profile, 2_040, 128, cls.inputs, semantic
        )
        candidate = m2_route_data.CandidateRouteData(
            r3_profile.profile_id,
            r3_profile.profile_version,
            r3_profile.transport_id,
            r3_profile.section_check_id,
            (cls.r3_package,),
        )
        cls.r3_projection = m2_route_data.build_r3_route_owner_projection(
            cls.r3_owner_fixture_raw, candidate, capacity_projection
        )
        projection_value = canonical_manifest.validate_canonical_manifest(
            cls.r3_projection.reproduction_projection
        )
        cls.r3_rust_route_receipt = canonical_manifest.serialize_manifest(
            {
                "implementation_id": "rust",
                "recipient_package_sha256": projection_value[
                    "recipient_package_sha256"
                ],
                "reproduction_projection_sha256": sha256(
                    cls.r3_projection.reproduction_projection
                ).hexdigest(),
                "route_data_template_sha256": projection_value[
                    "route_data_template_sha256"
                ],
                "route_sha256": projection_value["route_sha256"],
                "schema": "golden-board.m2-r3-route-reproduction/v1",
            }
        )
        cls.r3_route_raw = m2_route_data.render_r3_route_data_owner(
            cls.r3_projection,
            cls.r3_projection.python_reproduction_receipt,
            cls.r3_rust_route_receipt,
        )
        (
            cls.r3_profile_draft_raw,
            cls.r3_damage_draft_raw,
            cls.r3_promotion_draft_raw,
        ) = m2_policy._r3_blocked_owner_precursors(
            tracked_profile_raw,
            archived_damage_raw,
            archived_promotion_raw,
        )
        cls.r3_profile_raw = m2_policy.render_r3_promoted_profile_policy(
            cls.r3_profile_draft_raw,
            cls.r3_bootstrap_raw,
            cls.r3_route_raw,
        )
        cls.r3_damage_raw = m2_policy.render_r3_promoted_damage_policy(
            cls.r3_damage_draft_raw,
            cls.r3_bootstrap_raw,
            cls.r3_profile_raw,
            cls.r3_route_raw,
        )
        cls.r3_limits_raw = m2_policy.render_r3_profile_limits(
            cls.r3_profile_raw,
            cls.r3_damage_raw,
            cls.r3_bootstrap_raw,
            cls.r3_route_raw,
            cls.r3_package,
            _read("python/golden_board/capacity.py"),
            cls.profile_raw,
            cls.limits_raw,
            cls.inputs,
        )
        cls.r3_python_limits_receipt = (
            m2_policy.render_r3_limits_reproduction_receipt(
                "python", cls.r3_limits_raw, cls.r3_route_raw
            )
        )
        cls.r3_rust_limits_receipt = (
            m2_policy.render_r3_limits_reproduction_receipt(
                "rust", cls.r3_limits_raw, cls.r3_route_raw
            )
        )
        cls.r3_promotion_raw = m2_policy.render_r3_promotion_manifest(
            cls.r3_promotion_draft_raw,
            cls.r3_bootstrap_raw,
            cls.r3_profile_raw,
            cls.r3_damage_raw,
            cls.r3_owner_fixture_raw,
            cls.r3_route_raw,
            cls.r3_limits_raw,
            cls.r3_projection.python_reproduction_receipt,
            cls.r3_rust_route_receipt,
            cls.r3_python_limits_receipt,
            cls.r3_rust_limits_receipt,
        )
        if archived_limits_raw != cls.r3_limits_raw:
            raise RuntimeError("archived R3 limits drift")
        cls.r3_bundle = m2_policy.R3PromotionWriteBundle(
            cls.r3_profile_raw,
            cls.r3_damage_raw,
            cls.r3_route_raw,
            cls.r3_limits_raw,
            cls.r3_promotion_raw,
        )
        cls.r3_stage_files = {
            "damage-policy-v1.projected.toml": cls.r3_damage_raw,
            "m2-r3-owner-promotion-v1.projected.toml": cls.r3_promotion_raw,
            "profile-limits-v1.toml": cls.r3_limits_raw,
            "profile-policy-v1.projected.toml": cls.r3_profile_raw,
            "recipient-package-v7.bin": cls.r3_package,
            "route-data-v1.json": cls.r3_route_raw,
            "route-data-v1.template.json": (
                cls.r3_projection.route_data_template
            ),
            "route-malformed-corpus.json": cls.r3_projection.malformed_corpus,
            "route-prefix-sector-0.bin": cls.r3_projection.route_prefixes[0],
            "route-prefix-sector-1.bin": cls.r3_projection.route_prefixes[1],
            "route-prefix-sector-2.bin": cls.r3_projection.route_prefixes[2],
            "route-prefix-sector-3.bin": cls.r3_projection.route_prefixes[3],
            "route-prefixes.bin": b"".join(cls.r3_projection.route_prefixes),
            "route-reproduction-projection.json": (
                cls.r3_projection.reproduction_projection
            ),
        }
        cls.r3_clarified_damage_raw = schema_archived_damage_raw
        cls.r3_clarified_limits_raw = m2_policy.render_r3_profile_limits(
            cls.r3_profile_raw,
            cls.r3_clarified_damage_raw,
            cls.r3_bootstrap_raw,
            cls.r3_route_raw,
            cls.r3_package,
            _read("python/golden_board/capacity.py"),
            cls.profile_raw,
            cls.limits_raw,
            cls.inputs,
        )
        cls.r3_clarified_python_limits_receipt = (
            m2_policy.render_r3_limits_reproduction_receipt(
                "python", cls.r3_clarified_limits_raw, cls.r3_route_raw
            )
        )
        cls.r3_clarified_rust_limits_receipt = (
            m2_policy.render_r3_limits_reproduction_receipt(
                "rust", cls.r3_clarified_limits_raw, cls.r3_route_raw
            )
        )
        cls.r3_clarified_promotion_raw = (
            m2_policy.render_r3_mapping_clarification_manifest(
                archived_promotion_raw,
                cls.r3_bootstrap_raw,
                cls.r3_profile_raw,
                cls.r3_clarified_damage_raw,
                cls.r3_owner_fixture_raw,
                cls.r3_route_raw,
                cls.r3_clarified_limits_raw,
                cls.r3_projection.python_reproduction_receipt,
                cls.r3_rust_route_receipt,
                cls.r3_clarified_python_limits_receipt,
                cls.r3_clarified_rust_limits_receipt,
            )
        )
        cls.r3_clarified_bundle = m2_policy.R3PromotionWriteBundle(
            cls.r3_profile_raw,
            cls.r3_clarified_damage_raw,
            cls.r3_route_raw,
            cls.r3_clarified_limits_raw,
            cls.r3_clarified_promotion_raw,
        )
        cls.r3_clarified_stage_files = dict(cls.r3_stage_files)
        cls.r3_clarified_stage_files.update(
            {
                "damage-policy-v1.projected.toml": (
                    cls.r3_clarified_damage_raw
                ),
                "m2-r3-owner-promotion-v1.projected.toml": (
                    cls.r3_clarified_promotion_raw
                ),
                "profile-limits-v1.toml": cls.r3_clarified_limits_raw,
            }
        )
        if schema_archived_limits_raw != cls.r3_clarified_limits_raw:
            raise RuntimeError("schema-archived R3 limits drift")
        if schema_archived_promotion_raw != cls.r3_clarified_promotion_raw:
            raise RuntimeError("schema-archived R3 promotion drift")
        cls.r3_schema_damage_raw = witness_archived_damage_raw
        cls.r3_schema_limits_raw = m2_policy.render_r3_profile_limits(
            cls.r3_profile_raw,
            cls.r3_schema_damage_raw,
            cls.r3_bootstrap_raw,
            cls.r3_route_raw,
            cls.r3_package,
            _read("python/golden_board/capacity.py"),
            cls.profile_raw,
            cls.limits_raw,
            cls.inputs,
        )
        cls.r3_schema_python_limits_receipt = (
            m2_policy.render_r3_limits_reproduction_receipt(
                "python", cls.r3_schema_limits_raw, cls.r3_route_raw
            )
        )
        cls.r3_schema_rust_limits_receipt = (
            m2_policy.render_r3_limits_reproduction_receipt(
                "rust", cls.r3_schema_limits_raw, cls.r3_route_raw
            )
        )
        cls.r3_schema_promotion_raw = (
            m2_policy.render_r3_damage_schema_clarification_manifest(
                schema_archived_promotion_raw,
                cls.r3_bootstrap_raw,
                cls.r3_profile_raw,
                cls.r3_schema_damage_raw,
                cls.r3_owner_fixture_raw,
                cls.r3_route_raw,
                cls.r3_schema_limits_raw,
                cls.r3_projection.python_reproduction_receipt,
                cls.r3_rust_route_receipt,
                cls.r3_schema_python_limits_receipt,
                cls.r3_schema_rust_limits_receipt,
            )
        )
        cls.r3_schema_bundle = m2_policy.R3PromotionWriteBundle(
            cls.r3_profile_raw,
            cls.r3_schema_damage_raw,
            cls.r3_route_raw,
            cls.r3_schema_limits_raw,
            cls.r3_schema_promotion_raw,
        )
        cls.r3_schema_stage_files = dict(cls.r3_stage_files)
        cls.r3_schema_stage_files.update(
            {
                "damage-policy-v1.projected.toml": cls.r3_schema_damage_raw,
                "m2-r3-owner-promotion-v1.projected.toml": (
                    cls.r3_schema_promotion_raw
                ),
                "profile-limits-v1.toml": cls.r3_schema_limits_raw,
            }
        )
        if witness_archived_limits_raw != cls.r3_schema_limits_raw:
            raise RuntimeError("witness-archived R3 limits drift")
        if witness_archived_promotion_raw != cls.r3_schema_promotion_raw:
            raise RuntimeError("witness-archived R3 promotion drift")
        cls.r3_witness_damage_raw = convergence_archived_damage_raw
        cls.r3_witness_limits_raw = m2_policy.render_r3_profile_limits(
            cls.r3_profile_raw,
            cls.r3_witness_damage_raw,
            cls.r3_bootstrap_raw,
            cls.r3_route_raw,
            cls.r3_package,
            _read("python/golden_board/capacity.py"),
            cls.profile_raw,
            cls.limits_raw,
            cls.inputs,
        )
        cls.r3_witness_python_limits_receipt = (
            m2_policy.render_r3_limits_reproduction_receipt(
                "python", cls.r3_witness_limits_raw, cls.r3_route_raw
            )
        )
        cls.r3_witness_rust_limits_receipt = (
            m2_policy.render_r3_limits_reproduction_receipt(
                "rust", cls.r3_witness_limits_raw, cls.r3_route_raw
            )
        )
        cls.r3_witness_promotion_raw = (
            m2_policy.render_r3_independence_witness_clarification_manifest(
                witness_archived_promotion_raw,
                cls.r3_bootstrap_raw,
                cls.r3_profile_raw,
                cls.r3_witness_damage_raw,
                cls.r3_owner_fixture_raw,
                cls.r3_route_raw,
                cls.r3_witness_limits_raw,
                cls.r3_projection.python_reproduction_receipt,
                cls.r3_rust_route_receipt,
                cls.r3_witness_python_limits_receipt,
                cls.r3_witness_rust_limits_receipt,
            )
        )
        cls.r3_witness_bundle = m2_policy.R3PromotionWriteBundle(
            cls.r3_profile_raw,
            cls.r3_witness_damage_raw,
            cls.r3_route_raw,
            cls.r3_witness_limits_raw,
            cls.r3_witness_promotion_raw,
        )
        cls.r3_witness_stage_files = dict(cls.r3_stage_files)
        cls.r3_witness_stage_files.update(
            {
                "damage-policy-v1.projected.toml": (
                    cls.r3_witness_damage_raw
                ),
                "m2-r3-owner-promotion-v1.projected.toml": (
                    cls.r3_witness_promotion_raw
                ),
                "profile-limits-v1.toml": cls.r3_witness_limits_raw,
            }
        )
        if convergence_archived_limits_raw != cls.r3_witness_limits_raw:
            raise RuntimeError("convergence-archived R3 limits drift")
        if convergence_archived_promotion_raw != cls.r3_witness_promotion_raw:
            raise RuntimeError("convergence-archived R3 promotion drift")
        cls.r3_convergence_damage_raw = tracked_damage_raw
        cls.r3_convergence_limits_raw = m2_policy.render_r3_profile_limits(
            cls.r3_profile_raw,
            cls.r3_convergence_damage_raw,
            cls.r3_bootstrap_raw,
            cls.r3_route_raw,
            cls.r3_package,
            _read("python/golden_board/capacity.py"),
            cls.profile_raw,
            cls.limits_raw,
            cls.inputs,
        )
        cls.r3_convergence_python_limits_receipt = (
            m2_policy.render_r3_limits_reproduction_receipt(
                "python", cls.r3_convergence_limits_raw, cls.r3_route_raw
            )
        )
        cls.r3_convergence_rust_limits_receipt = (
            m2_policy.render_r3_limits_reproduction_receipt(
                "rust", cls.r3_convergence_limits_raw, cls.r3_route_raw
            )
        )
        cls.r3_convergence_promotion_raw = (
            m2_policy.render_r3_gate6_convergence_clarification_manifest(
                convergence_archived_promotion_raw,
                cls.r3_bootstrap_raw,
                cls.r3_profile_raw,
                cls.r3_convergence_damage_raw,
                cls.r3_owner_fixture_raw,
                cls.r3_route_raw,
                cls.r3_convergence_limits_raw,
                cls.r3_projection.python_reproduction_receipt,
                cls.r3_rust_route_receipt,
                cls.r3_convergence_python_limits_receipt,
                cls.r3_convergence_rust_limits_receipt,
            )
        )
        cls.r3_convergence_bundle = m2_policy.R3PromotionWriteBundle(
            cls.r3_profile_raw,
            cls.r3_convergence_damage_raw,
            cls.r3_route_raw,
            cls.r3_convergence_limits_raw,
            cls.r3_convergence_promotion_raw,
        )
        cls.r3_convergence_stage_files = dict(cls.r3_stage_files)
        cls.r3_convergence_stage_files.update(
            {
                "damage-policy-v1.projected.toml": (
                    cls.r3_convergence_damage_raw
                ),
                "m2-r3-owner-promotion-v1.projected.toml": (
                    cls.r3_convergence_promotion_raw
                ),
                "profile-limits-v1.toml": cls.r3_convergence_limits_raw,
            }
        )
        tracked_tuple = (
            tracked_profile_raw,
            tracked_damage_raw,
            _read("spec/route-data-v1.json"),
            _read("spec/profile-limits-v1.toml"),
            tracked_promotion_raw,
        )
        staged_tuple = (
            cls.r3_profile_raw,
            cls.r3_clarified_damage_raw,
            cls.r3_route_raw,
            cls.r3_limits_raw,
            cls.r3_promotion_raw,
        )
        final_tuple = (
            cls.r3_profile_raw,
            cls.r3_clarified_damage_raw,
            cls.r3_route_raw,
            cls.r3_clarified_limits_raw,
            cls.r3_clarified_promotion_raw,
        )
        schema_staged_tuple = (
            cls.r3_profile_raw,
            cls.r3_schema_damage_raw,
            cls.r3_route_raw,
            cls.r3_clarified_limits_raw,
            cls.r3_clarified_promotion_raw,
        )
        schema_final_tuple = (
            cls.r3_profile_raw,
            cls.r3_schema_damage_raw,
            cls.r3_route_raw,
            cls.r3_schema_limits_raw,
            cls.r3_schema_promotion_raw,
        )
        witness_staged_tuple = (
            cls.r3_profile_raw,
            cls.r3_witness_damage_raw,
            cls.r3_route_raw,
            cls.r3_schema_limits_raw,
            cls.r3_schema_promotion_raw,
        )
        witness_final_tuple = (
            cls.r3_profile_raw,
            cls.r3_witness_damage_raw,
            cls.r3_route_raw,
            cls.r3_witness_limits_raw,
            cls.r3_witness_promotion_raw,
        )
        convergence_staged_tuple = (
            cls.r3_profile_raw,
            cls.r3_convergence_damage_raw,
            cls.r3_route_raw,
            cls.r3_witness_limits_raw,
            cls.r3_witness_promotion_raw,
        )
        convergence_final_tuple = (
            cls.r3_profile_raw,
            cls.r3_convergence_damage_raw,
            cls.r3_route_raw,
            cls.r3_convergence_limits_raw,
            cls.r3_convergence_promotion_raw,
        )
        if tracked_tuple == staged_tuple:
            cls.r3_tracked_status = "clarification-staged"
        elif tracked_tuple == final_tuple:
            cls.r3_tracked_status = "clarified-final"
        elif tracked_tuple == schema_staged_tuple:
            cls.r3_tracked_status = "damage-schema-staged"
        elif tracked_tuple == schema_final_tuple:
            cls.r3_tracked_status = "damage-schema-final"
        elif tracked_tuple == witness_staged_tuple:
            cls.r3_tracked_status = "witness-staged"
        elif tracked_tuple == witness_final_tuple:
            cls.r3_tracked_status = "witness-final"
        elif tracked_tuple == convergence_staged_tuple:
            cls.r3_tracked_status = "gate6-convergence-staged"
        elif tracked_tuple == convergence_final_tuple:
            cls.r3_tracked_status = "gate6-convergence-final"
        else:
            raise RuntimeError("tracked R3 clarification owner drift")

    def _write_r3_workspace(self, root: Path) -> None:
        for relative in ("spec", "conformance", "artifacts", "reports"):
            (root / relative).mkdir(parents=True, exist_ok=True)
        for relative, raw in (
            ("spec/bootstrap-v1.md", self.r3_bootstrap_raw),
            ("spec/profile-policy-v1.toml", self.r3_profile_draft_raw),
            ("spec/damage-policy-v1.toml", self.r3_damage_draft_raw),
            (
                "spec/m2-r3-owner-promotion-v1.toml",
                self.r3_promotion_draft_raw,
            ),
            ("conformance/m2-r3-owner-v1.json", self.r3_owner_fixture_raw),
        ):
            (root / relative).write_bytes(raw)

    def _apply_r3(
        self,
        root: Path,
        *,
        bundle: m2_policy.R3PromotionWriteBundle | None = None,
        blocked_profile: bytes | None = None,
        rust_stage: Path | None = None,
        dry_run: bool,
    ) -> str:
        if rust_stage is None:
            rust_stage = root / ".rust-stage"
            if not rust_stage.exists():
                self.assertEqual(
                    self._write_r3_stage(rust_stage),
                    "e4af2341e63dfccd87ae879468b76a854b209807dc060c833d71c04f195ec29b",
                )
        return m2_policy.apply_r3_promotion_bundle(
            root,
            self.r3_bundle if bundle is None else bundle,
            (
                self.r3_profile_draft_raw
                if blocked_profile is None
                else blocked_profile
            ),
            self.r3_damage_draft_raw,
            self.r3_promotion_draft_raw,
            self.r3_bootstrap_raw,
            self.r3_owner_fixture_raw,
            self.r3_projection.python_reproduction_receipt,
            self.r3_rust_route_receipt,
            self.r3_python_limits_receipt,
            self.r3_rust_limits_receipt,
            rust_stage,
            self.r3_stage_files,
            dry_run=dry_run,
        )

    def _write_r3_stage(self, stage: Path) -> str:
        files = dict(self.r3_stage_files)
        files["route-rust-reproduction.json"] = self.r3_rust_route_receipt
        files["limits-rust-reproduction.json"] = self.r3_rust_limits_receipt
        stage.mkdir()
        for name, raw in files.items():
            (stage / name).write_bytes(raw)
        manifest = canonical_manifest.serialize_manifest(
            {
                "files": [
                    {
                        "bytes": len(raw),
                        "path": name,
                        "sha256": sha256(raw).hexdigest(),
                    }
                    for name, raw in sorted(files.items())
                ],
                "schema": "golden-board.m2-r3-rust-stage/v1",
            }
        )
        (stage / "manifest.json").write_bytes(manifest)
        return sha256(manifest).hexdigest()

    def _write_r3_clarification_workspace(self, root: Path) -> None:
        for relative in ("spec", "conformance", "artifacts/candidates"):
            (root / relative).mkdir(parents=True, exist_ok=True)
        for relative, raw in (
            ("spec/bootstrap-v1.md", self.r3_bootstrap_raw),
            ("spec/profile-policy-v1.toml", self.r3_profile_raw),
            (
                "spec/damage-policy-v1.toml",
                self.r3_clarified_damage_raw,
            ),
            ("spec/route-data-v1.json", self.r3_route_raw),
            ("spec/profile-limits-v1.toml", self.r3_limits_raw),
            (
                "spec/m2-r3-owner-promotion-v1.toml",
                self.r3_promotion_raw,
            ),
            ("conformance/m2-r3-owner-v1.json", self.r3_owner_fixture_raw),
        ):
            (root / relative).write_bytes(raw)
        source = ROOT / (
            "artifacts/history/m2-r3-pre-d7-mapping-clarification"
        )
        destination = root / (
            "artifacts/history/m2-r3-pre-d7-mapping-clarification"
        )
        shutil.copytree(source, destination)

    def _write_r3_clarification_stage(self, stage: Path) -> str:
        files = dict(self.r3_clarified_stage_files)
        files["route-rust-reproduction.json"] = self.r3_rust_route_receipt
        files["limits-rust-reproduction.json"] = (
            self.r3_clarified_rust_limits_receipt
        )
        stage.mkdir()
        for name, raw in files.items():
            (stage / name).write_bytes(raw)
        manifest = canonical_manifest.serialize_manifest(
            {
                "files": [
                    {
                        "bytes": len(raw),
                        "path": name,
                        "sha256": sha256(raw).hexdigest(),
                    }
                    for name, raw in sorted(files.items())
                ],
                "schema": "golden-board.m2-r3-rust-stage/v1",
            }
        )
        (stage / "manifest.json").write_bytes(manifest)
        return sha256(manifest).hexdigest()

    def _apply_r3_clarification(
        self,
        root: Path,
        *,
        bundle: m2_policy.R3PromotionWriteBundle | None = None,
        rust_stage: Path | None = None,
        comparison_files: dict[str, bytes] | None = None,
        dry_run: bool,
    ) -> str:
        if rust_stage is None:
            rust_stage = root / ".rust-clarification-stage"
            if not rust_stage.exists():
                self.assertEqual(
                    self._write_r3_clarification_stage(rust_stage),
                    "9ab2d2928738c4bc8a3384e1a8181b7b23c00ef5e36e203a97a946f30b6603c4",
                )
        return m2_policy.apply_r3_mapping_clarification_bundle(
            root,
            self.r3_clarified_bundle if bundle is None else bundle,
            self.r3_bootstrap_raw,
            self.r3_owner_fixture_raw,
            self.r3_projection.python_reproduction_receipt,
            self.r3_rust_route_receipt,
            self.r3_clarified_python_limits_receipt,
            self.r3_clarified_rust_limits_receipt,
            rust_stage,
            (
                self.r3_clarified_stage_files
                if comparison_files is None
                else comparison_files
            ),
            dry_run=dry_run,
        )

    def _write_r3_damage_schema_workspace(self, root: Path) -> None:
        for relative in ("spec", "conformance", "artifacts/candidates"):
            (root / relative).mkdir(parents=True, exist_ok=True)
        for relative, raw in (
            ("spec/bootstrap-v1.md", self.r3_bootstrap_raw),
            ("spec/profile-policy-v1.toml", self.r3_profile_raw),
            ("spec/damage-policy-v1.toml", self.r3_schema_damage_raw),
            ("spec/route-data-v1.json", self.r3_route_raw),
            ("spec/profile-limits-v1.toml", self.r3_clarified_limits_raw),
            (
                "spec/m2-r3-owner-promotion-v1.toml",
                self.r3_clarified_promotion_raw,
            ),
            ("conformance/m2-r3-owner-v1.json", self.r3_owner_fixture_raw),
        ):
            (root / relative).write_bytes(raw)
        for name in (
            "m2-r3-pre-d7-mapping-clarification",
            "m2-r3-pre-damage-artifact-schema-clarification",
        ):
            shutil.copytree(
                ROOT / "artifacts/history" / name,
                root / "artifacts/history" / name,
            )

    def _write_r3_damage_schema_stage(self, stage: Path) -> str:
        files = dict(self.r3_schema_stage_files)
        files["route-rust-reproduction.json"] = self.r3_rust_route_receipt
        files["limits-rust-reproduction.json"] = (
            self.r3_schema_rust_limits_receipt
        )
        stage.mkdir()
        for name, raw in files.items():
            (stage / name).write_bytes(raw)
        manifest = canonical_manifest.serialize_manifest(
            {
                "files": [
                    {
                        "bytes": len(raw),
                        "path": name,
                        "sha256": sha256(raw).hexdigest(),
                    }
                    for name, raw in sorted(files.items())
                ],
                "schema": "golden-board.m2-r3-rust-stage/v1",
            }
        )
        (stage / "manifest.json").write_bytes(manifest)
        return sha256(manifest).hexdigest()

    def _apply_r3_damage_schema(
        self,
        root: Path,
        *,
        bundle: m2_policy.R3PromotionWriteBundle | None = None,
        rust_stage: Path | None = None,
        comparison_files: dict[str, bytes] | None = None,
        dry_run: bool,
    ) -> str:
        if rust_stage is None:
            rust_stage = root / ".rust-damage-schema-stage"
            if not rust_stage.exists():
                self.assertEqual(
                    self._write_r3_damage_schema_stage(rust_stage),
                    "5f0b62d9f39fbcbfecd13ccd4fb7dc830e0619db6de5d34bec5de5040430e225",
                )
        return m2_policy.apply_r3_damage_schema_clarification_bundle(
            root,
            self.r3_schema_bundle if bundle is None else bundle,
            self.r3_bootstrap_raw,
            self.r3_owner_fixture_raw,
            self.r3_projection.python_reproduction_receipt,
            self.r3_rust_route_receipt,
            self.r3_schema_python_limits_receipt,
            self.r3_schema_rust_limits_receipt,
            rust_stage,
            (
                self.r3_schema_stage_files
                if comparison_files is None
                else comparison_files
            ),
            dry_run=dry_run,
        )

    def _write_r3_witness_workspace(self, root: Path) -> None:
        for relative in ("spec", "conformance", "artifacts/candidates"):
            (root / relative).mkdir(parents=True, exist_ok=True)
        for relative, raw in (
            ("spec/bootstrap-v1.md", self.r3_bootstrap_raw),
            ("spec/profile-policy-v1.toml", self.r3_profile_raw),
            ("spec/damage-policy-v1.toml", self.r3_witness_damage_raw),
            ("spec/route-data-v1.json", self.r3_route_raw),
            ("spec/profile-limits-v1.toml", self.r3_schema_limits_raw),
            (
                "spec/m2-r3-owner-promotion-v1.toml",
                self.r3_schema_promotion_raw,
            ),
            ("conformance/m2-r3-owner-v1.json", self.r3_owner_fixture_raw),
        ):
            (root / relative).write_bytes(raw)
        for name in (
            "m2-r3-pre-d7-mapping-clarification",
            "m2-r3-pre-damage-artifact-schema-clarification",
            "m2-r3-pre-independence-witness-clarification",
        ):
            shutil.copytree(
                ROOT / "artifacts/history" / name,
                root / "artifacts/history" / name,
            )

    def _write_r3_witness_stage(self, stage: Path) -> str:
        files = dict(self.r3_witness_stage_files)
        files["route-rust-reproduction.json"] = self.r3_rust_route_receipt
        files["limits-rust-reproduction.json"] = (
            self.r3_witness_rust_limits_receipt
        )
        stage.mkdir()
        for name, raw in files.items():
            (stage / name).write_bytes(raw)
        manifest = canonical_manifest.serialize_manifest(
            {
                "files": [
                    {
                        "bytes": len(raw),
                        "path": name,
                        "sha256": sha256(raw).hexdigest(),
                    }
                    for name, raw in sorted(files.items())
                ],
                "schema": "golden-board.m2-r3-rust-stage/v1",
            }
        )
        (stage / "manifest.json").write_bytes(manifest)
        return sha256(manifest).hexdigest()

    def _apply_r3_witness(
        self,
        root: Path,
        *,
        bundle: m2_policy.R3PromotionWriteBundle | None = None,
        rust_stage: Path | None = None,
        comparison_files: dict[str, bytes] | None = None,
        dry_run: bool,
    ) -> str:
        if rust_stage is None:
            rust_stage = root / ".rust-witness-stage"
            if not rust_stage.exists():
                self.assertEqual(
                    self._write_r3_witness_stage(rust_stage),
                    "708bcff8f3df0126016dc4bf83801542055bd2861040c8beb678d7f0ea33a411",
                )
        return m2_policy.apply_r3_independence_witness_clarification_bundle(
            root,
            self.r3_witness_bundle if bundle is None else bundle,
            self.r3_bootstrap_raw,
            self.r3_owner_fixture_raw,
            self.r3_projection.python_reproduction_receipt,
            self.r3_rust_route_receipt,
            self.r3_witness_python_limits_receipt,
            self.r3_witness_rust_limits_receipt,
            rust_stage,
            (
                self.r3_witness_stage_files
                if comparison_files is None
                else comparison_files
            ),
            dry_run=dry_run,
        )

    def _write_r3_convergence_workspace(self, root: Path) -> None:
        for relative in ("spec", "conformance", "artifacts/candidates"):
            (root / relative).mkdir(parents=True, exist_ok=True)
        for relative, raw in (
            ("spec/bootstrap-v1.md", self.r3_bootstrap_raw),
            ("spec/profile-policy-v1.toml", self.r3_profile_raw),
            (
                "spec/damage-policy-v1.toml",
                self.r3_convergence_damage_raw,
            ),
            ("spec/route-data-v1.json", self.r3_route_raw),
            ("spec/profile-limits-v1.toml", self.r3_witness_limits_raw),
            (
                "spec/m2-r3-owner-promotion-v1.toml",
                self.r3_witness_promotion_raw,
            ),
            ("conformance/m2-r3-owner-v1.json", self.r3_owner_fixture_raw),
        ):
            (root / relative).write_bytes(raw)
        for name in (
            "m2-r3-pre-d7-mapping-clarification",
            "m2-r3-pre-damage-artifact-schema-clarification",
            "m2-r3-pre-independence-witness-clarification",
            "m2-r3-pre-gate6-convergence-clarification",
        ):
            shutil.copytree(
                ROOT / "artifacts/history" / name,
                root / "artifacts/history" / name,
            )

    def _write_r3_convergence_stage(self, stage: Path) -> str:
        files = dict(self.r3_convergence_stage_files)
        files["route-rust-reproduction.json"] = self.r3_rust_route_receipt
        files["limits-rust-reproduction.json"] = (
            self.r3_convergence_rust_limits_receipt
        )
        stage.mkdir()
        for name, raw in files.items():
            (stage / name).write_bytes(raw)
        manifest = canonical_manifest.serialize_manifest(
            {
                "files": [
                    {
                        "bytes": len(raw),
                        "path": name,
                        "sha256": sha256(raw).hexdigest(),
                    }
                    for name, raw in sorted(files.items())
                ],
                "schema": "golden-board.m2-r3-rust-stage/v1",
            }
        )
        (stage / "manifest.json").write_bytes(manifest)
        return sha256(manifest).hexdigest()

    def _apply_r3_convergence(
        self,
        root: Path,
        *,
        bundle: m2_policy.R3PromotionWriteBundle | None = None,
        rust_stage: Path | None = None,
        comparison_files: dict[str, bytes] | None = None,
        dry_run: bool,
    ) -> str:
        if rust_stage is None:
            rust_stage = root / ".rust-convergence-stage"
            if not rust_stage.exists():
                self.assertEqual(
                    self._write_r3_convergence_stage(rust_stage),
                    "9fda506c34382a1420ad94ef7b04641e835f9a9641852e3471546d83e40a505c",
                )
        return m2_policy.apply_r3_gate6_convergence_clarification_bundle(
            root,
            self.r3_convergence_bundle if bundle is None else bundle,
            self.r3_bootstrap_raw,
            self.r3_owner_fixture_raw,
            self.r3_projection.python_reproduction_receipt,
            self.r3_rust_route_receipt,
            self.r3_convergence_python_limits_receipt,
            self.r3_convergence_rust_limits_receipt,
            rust_stage,
            (
                self.r3_convergence_stage_files
                if comparison_files is None
                else comparison_files
            ),
            dry_run=dry_run,
        )

    def test_r3_exact_owner_dag_and_corrected_obs_units_are_strict(self) -> None:
        self.assertEqual(
            tuple(
                sha256(raw).hexdigest()
                for raw in (
                    self.r3_profile_draft_raw,
                    self.r3_damage_draft_raw,
                    self.r3_promotion_draft_raw,
                )
            ),
            (
                "f9b3a24c09fceb345bcf9644c75cd6b86f44d6d428d83a5267eab6167825f7d6",
                "a1cbf2644d26b3e0ba284dbc093a26f77d9fe9baeb461f69707de4f8abe8042e",
                "57b6fa75507d5406e82a5dd26d8f8542300052a6c330e6cffe33a3865c5be9a3",
            ),
        )
        self.assertEqual(
            m2_policy._r3_blocked_owner_precursors(
                self.r3_profile_raw,
                self.r3_damage_raw,
                self.r3_promotion_raw,
            ),
            (
                self.r3_profile_draft_raw,
                self.r3_damage_draft_raw,
                self.r3_promotion_draft_raw,
            ),
        )
        self.assertEqual(
            tuple(
                (len(raw), sha256(raw).hexdigest())
                for raw in (
                    self.r3_bootstrap_raw,
                    self.r3_profile_raw,
                    self.r3_damage_raw,
                    self.r3_route_raw,
                    self.r3_limits_raw,
                    self.r3_promotion_raw,
                )
            ),
            (
                (27_457, "e4d0a5667758a753d35603632dee550db7ecb66cf64ee675ce7485531da27dde"),
                (28_660, "44215d993e3fdfdd1630c404f1ee969e8abc6e4928fda83365fc6940e5cfd412"),
                (24_552, "e5fb1eb7ffbe82ac9a422d84542c9c8dc2cfbcaf7bbd105471d986435bfe104c"),
                (11_015, "94df79d9a3fb01b69014417683a0f48f2222fea9fe991361bc99aa0c30dc663e"),
                (5_434, "4be5f03700b924195b14cf3e832ae0ffc477c7b74fe10450ec6a7eae28210ebf"),
                (7_701, "37c81359e172afcf61efd359cd9abace8fe61607ebff8d4d9cb4859c9a3fd1e3"),
            ),
        )
        damage = tomllib.loads(self.r3_damage_raw.decode("utf-8"))
        limits = tomllib.loads(self.r3_limits_raw.decode("utf-8"))
        self.assertEqual(damage["generated"]["obs_units_bytes"], 408_901)
        self.assertEqual(limits["damage"]["obs_units_bytes"], 408_901)
        self.assertEqual(limits["profile"][0]["obs_units_bytes"], 408_901)
        self.assertEqual(limits["damage"]["cases"], 10_038)
        admitted = m2_policy._load_r3_promoted_owner_set(
            self.r3_bundle,
            self.r3_bootstrap_raw,
            self.r3_owner_fixture_raw,
            self.r3_projection.python_reproduction_receipt,
            self.r3_rust_route_receipt,
            self.r3_python_limits_receipt,
            self.r3_rust_limits_receipt,
            "37c81359e172afcf61efd359cd9abace8fe61607ebff8d4d9cb4859c9a3fd1e3",
        )
        self.assertEqual(
            admitted.promotion_sha256,
            "37c81359e172afcf61efd359cd9abace8fe61607ebff8d4d9cb4859c9a3fd1e3",
        )
        with self.assertRaises(m2_policy.PolicyError) as caught:
            m2_policy.load_r3_promoted_owner_set(
                self.r3_bundle,
                self.r3_bootstrap_raw,
                self.r3_owner_fixture_raw,
                self.r3_projection.python_reproduction_receipt,
                self.r3_rust_route_receipt,
                self.r3_python_limits_receipt,
                self.r3_rust_limits_receipt,
            )
        self.assertEqual(caught.exception.reason, "r3-promotion-identity")

    def test_r3_loader_and_apply_reject_mutants_and_forged_inputs(self) -> None:
        unknown = self.r3_profile_raw.replace(
            b'policy_version = 1\n',
            b'policy_version = 1\nunknown_key = 1\n',
            1,
        )
        duplicate = self.r3_profile_raw.replace(
            b'policy_version = 1\n',
            b'policy_version = 1\npolicy_version = 1\n',
            1,
        )
        for mutant in (unknown, duplicate):
            bundle = m2_policy.R3PromotionWriteBundle(
                mutant,
                self.r3_damage_raw,
                self.r3_route_raw,
                self.r3_limits_raw,
                self.r3_promotion_raw,
            )
            with self.subTest(kind="profile-owner-mutant"):
                with self.assertRaises(m2_policy.PolicyError):
                    m2_policy.load_r3_promoted_owner_set(
                        bundle,
                        self.r3_bootstrap_raw,
                        self.r3_owner_fixture_raw,
                        self.r3_projection.python_reproduction_receipt,
                        self.r3_rust_route_receipt,
                        self.r3_python_limits_receipt,
                        self.r3_rust_limits_receipt,
                    )

        forged_profile = self.r3_profile_raw.replace(
            b"policy_version = 1", b"policy_version = 2", 1
        )
        forged = m2_policy.R3PromotionWriteBundle(
            forged_profile,
            self.r3_damage_raw,
            self.r3_route_raw,
            self.r3_limits_raw,
            self.r3_promotion_raw,
        )
        with tempfile.TemporaryDirectory(prefix="gb-r3-forged-") as directory:
            root = Path(directory)
            self._write_r3_workspace(root)
            before = {
                path.name: path.read_bytes()
                for path in (root / "spec").iterdir()
            }
            with self.assertRaises(m2_policy.PolicyError):
                self._apply_r3(root, bundle=forged, dry_run=True)
            self.assertEqual(
                before,
                {
                    path.name: path.read_bytes()
                    for path in (root / "spec").iterdir()
                },
            )

        with tempfile.TemporaryDirectory(prefix="gb-r3-current-") as directory:
            root = Path(directory)
            self._write_r3_workspace(root)
            mutant = self.r3_profile_draft_raw.replace(
                b"policy_version = 1", b"policy_version = 2", 1
            )
            profile_path = root / "spec/profile-policy-v1.toml"
            profile_path.write_bytes(mutant)
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3(
                    root,
                    blocked_profile=mutant,
                    dry_run=True,
                )
            self.assertEqual(caught.exception.reason, "r3-apply-blocked-input")
            self.assertEqual(profile_path.read_bytes(), mutant)
            self.assertFalse((root / "spec/route-data-v1.json").exists())
            self.assertFalse((root / "spec/profile-limits-v1.toml").exists())

    def test_r3_mapping_clarification_cascade_and_archive_are_exact(self) -> None:
        self.assertEqual(
            tuple(
                (len(raw), sha256(raw).hexdigest())
                for raw in (
                    self.r3_clarified_damage_raw,
                    self.r3_clarified_limits_raw,
                    self.r3_clarified_python_limits_receipt,
                    self.r3_clarified_rust_limits_receipt,
                    self.r3_clarified_promotion_raw,
                )
            ),
            (
                (26_533, "cbe82b203c6c735c70d30eebcf8005dcabf46c60332d1726d7ef1d00c12dcb3f"),
                (5_434, "54c62adfbee30bb84d9b4029059134db81c8e5794cd11c7c716b9b15ae1749e7"),
                (262, "5397497da30d61acf3e13b1d185dac93a37aef68ad81ee1ff8d0b2370af8498d"),
                (260, "db573ed9df5d7405704e2abf54e6c09460543c65513c97846cc346cb6ad01722"),
                (7_701, "82f4e9feedb95c5f5554e3bb219587d726996985276bdc51def099495901a57b"),
            ),
        )
        archive = m2_policy.validate_r3_pre_clarification_archive(
            ROOT, self.r3_clarified_damage_raw
        )
        self.assertEqual(len(archive), 11)
        self.assertEqual(
            sha256(archive["owners/damage-policy-v1.toml"]).hexdigest(),
            "e5fb1eb7ffbe82ac9a422d84542c9c8dc2cfbcaf7bbd105471d986435bfe104c",
        )
        admitted = m2_policy._load_r3_mapping_clarified_owner_set(
            self.r3_clarified_bundle,
            self.r3_bootstrap_raw,
            self.r3_owner_fixture_raw,
            self.r3_projection.python_reproduction_receipt,
            self.r3_rust_route_receipt,
            self.r3_clarified_python_limits_receipt,
            self.r3_clarified_rust_limits_receipt,
        )
        self.assertEqual(
            admitted,
            m2_policy.R3PromotedOwnerSet(
                "e4d0a5667758a753d35603632dee550db7ecb66cf64ee675ce7485531da27dde",
                "44215d993e3fdfdd1630c404f1ee969e8abc6e4928fda83365fc6940e5cfd412",
                "cbe82b203c6c735c70d30eebcf8005dcabf46c60332d1726d7ef1d00c12dcb3f",
                "94df79d9a3fb01b69014417683a0f48f2222fea9fe991361bc99aa0c30dc663e",
                "54c62adfbee30bb84d9b4029059134db81c8e5794cd11c7c716b9b15ae1749e7",
                "82f4e9feedb95c5f5554e3bb219587d726996985276bdc51def099495901a57b",
            ),
        )
        with self.assertRaises(m2_policy.PolicyError):
            m2_policy.render_r3_mapping_clarification_manifest(
                archive["owners/m2-r3-owner-promotion-v1.toml"] + b" ",
                self.r3_bootstrap_raw,
                self.r3_profile_raw,
                self.r3_clarified_damage_raw,
                self.r3_owner_fixture_raw,
                self.r3_route_raw,
                self.r3_clarified_limits_raw,
                self.r3_projection.python_reproduction_receipt,
                self.r3_rust_route_receipt,
                self.r3_clarified_python_limits_receipt,
                self.r3_clarified_rust_limits_receipt,
            )

    def test_r3_rust_stage_validation_rejects_drift_and_symlinks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gb-r3-stage-") as directory:
            parent = Path(directory)
            stage = parent / "stage"
            manifest_sha256 = self._write_r3_stage(stage)
            self.assertEqual(
                m2_policy.validate_r3_rust_stage(
                    stage, manifest_sha256, self.r3_stage_files
                ),
                (self.r3_rust_route_receipt, self.r3_rust_limits_receipt),
            )
            alias = parent / "stage-alias"
            os.symlink(stage, alias, target_is_directory=True)
            with self.assertRaises(m2_policy.PolicyError) as caught:
                m2_policy.validate_r3_rust_stage(
                    alias, manifest_sha256, self.r3_stage_files
                )
            self.assertEqual(caught.exception.reason, "r3-rust-stage-path")
            route_path = stage / "route-data-v1.json"
            route_path.write_bytes(route_path.read_bytes() + b" ")
            with self.assertRaises(m2_policy.PolicyError) as caught:
                m2_policy.validate_r3_rust_stage(
                    stage, manifest_sha256, self.r3_stage_files
                )
            self.assertEqual(caught.exception.reason, "r3-rust-stage-file")

    def test_r3_apply_dry_run_is_bounded_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gb-r3-dry-") as directory:
            root = Path(directory)
            self._write_r3_workspace(root)
            (root / "spec/route-data-v1.json").write_bytes(self.r3_route_raw)
            (root / "spec/profile-limits-v1.toml").write_bytes(
                self.r3_limits_raw
            )
            before = {
                path.name: path.read_bytes()
                for path in (root / "spec").iterdir()
            }
            self.assertEqual(self._apply_r3(root, dry_run=True), "dry-run-clean")
            self.assertEqual(
                before,
                {
                    path.name: path.read_bytes()
                    for path in (root / "spec").iterdir()
                },
            )

        with tempfile.TemporaryDirectory(prefix="gb-r3-stale-") as directory:
            root = Path(directory)
            self._write_r3_workspace(root)
            (root / "spec/route-data-v1.json").write_bytes(b"stale")
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3(root, dry_run=True)
            self.assertEqual(caught.exception.reason, "r3-apply-precondition")

    def test_r3_apply_requires_the_pinned_full_rust_stage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gb-r3-stage-gate-") as directory:
            root = Path(directory)
            self._write_r3_workspace(root)
            arguments = (
                root,
                self.r3_bundle,
                self.r3_profile_draft_raw,
                self.r3_damage_draft_raw,
                self.r3_promotion_draft_raw,
                self.r3_bootstrap_raw,
                self.r3_owner_fixture_raw,
                self.r3_projection.python_reproduction_receipt,
                self.r3_rust_route_receipt,
                self.r3_python_limits_receipt,
                self.r3_rust_limits_receipt,
            )
            with self.assertRaises(m2_policy.PolicyError) as caught:
                m2_policy.apply_r3_promotion_bundle(
                    *arguments, None, None, dry_run=True
                )
            self.assertEqual(caught.exception.reason, "r3-apply-rust-stage")

            stage = root / ".independent-rust-stage"
            self.assertEqual(
                self._write_r3_stage(stage),
                "e4af2341e63dfccd87ae879468b76a854b209807dc060c833d71c04f195ec29b",
            )
            mutant_files = dict(self.r3_stage_files)
            mutant_files["route-data-v1.json"] += b" "
            with self.assertRaises(m2_policy.PolicyError) as caught:
                m2_policy.apply_r3_promotion_bundle(
                    *arguments, stage, mutant_files, dry_run=True
                )
            self.assertEqual(
                caught.exception.reason,
                "r3-rust-stage-drift:route-data-v1.json",
            )
            self.assertFalse((root / "spec/route-data-v1.json").exists())
            self.assertFalse((root / "spec/profile-limits-v1.toml").exists())

        with tempfile.TemporaryDirectory(prefix="gb-r3-links-") as directory:
            parent = Path(directory)
            root = parent / "workspace"
            self._write_r3_workspace(root)
            alias = parent / "workspace-alias"
            os.symlink(root, alias, target_is_directory=True)
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3(alias, dry_run=True)
            self.assertEqual(caught.exception.reason, "r3-apply-workspace")
            target = parent / "target"
            target.write_bytes(b"outside")
            os.symlink(target, root / "spec/route-data-v1.json")
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3(root, dry_run=True)
            self.assertEqual(caught.exception.reason, "r3-apply-destination")
            self.assertEqual(target.read_bytes(), b"outside")

        with tempfile.TemporaryDirectory(prefix="gb-r3-spec-link-") as directory:
            parent = Path(directory)
            root = parent / "workspace"
            self._write_r3_workspace(root)
            (root / "spec").rename(root / "spec-real")
            os.symlink(root / "spec-real", root / "spec", target_is_directory=True)
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3(root, dry_run=True)
            self.assertEqual(caught.exception.reason, "r3-apply-workspace")

        with tempfile.TemporaryDirectory(prefix="gb-r3-artifact-") as directory:
            parent = Path(directory)
            root = parent / "workspace"
            self._write_r3_workspace(root)
            target = parent / "artifact-target"
            target.write_bytes(b"unrelated")
            os.symlink(target, root / "artifacts/link")
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3(root, dry_run=True)
            self.assertEqual(caught.exception.reason, "r3-apply-precondition")

    def test_r3_apply_write_set_and_idempotence_are_exact(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gb-r3-apply-") as directory:
            root = Path(directory)
            self._write_r3_workspace(root)
            (root / "docs").mkdir()
            (root / "python/tests").mkdir(parents=True)
            sentinels = {
                root / "docs/roadmap.md": b"roadmap-sentinel",
                root / "python/tests/test_foundation.py": b"foundation-sentinel",
                root / "conformance/registry.toml": b"registry-sentinel",
            }
            for path, raw in sentinels.items():
                path.write_bytes(raw)
            bootstrap_before = (root / "spec/bootstrap-v1.md").read_bytes()
            fixture_before = (
                root / "conformance/m2-r3-owner-v1.json"
            ).read_bytes()
            self.assertEqual(self._apply_r3(root, dry_run=False), "applied")
            expected = {
                "profile-policy-v1.toml": self.r3_profile_raw,
                "damage-policy-v1.toml": self.r3_damage_raw,
                "route-data-v1.json": self.r3_route_raw,
                "profile-limits-v1.toml": self.r3_limits_raw,
                "m2-r3-owner-promotion-v1.toml": self.r3_promotion_raw,
            }
            for name, raw in expected.items():
                self.assertEqual((root / "spec" / name).read_bytes(), raw)
            self.assertEqual(
                (root / "spec/bootstrap-v1.md").read_bytes(), bootstrap_before
            )
            self.assertEqual(
                (root / "conformance/m2-r3-owner-v1.json").read_bytes(),
                fixture_before,
            )
            for path, raw in sentinels.items():
                self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(
                m2_policy.apply_r3_promotion_bundle(
                    root,
                    self.r3_bundle,
                    None,
                    None,
                    None,
                    self.r3_bootstrap_raw,
                    self.r3_owner_fixture_raw,
                    self.r3_projection.python_reproduction_receipt,
                    self.r3_rust_route_receipt,
                    self.r3_python_limits_receipt,
                    self.r3_rust_limits_receipt,
                    None,
                    None,
                    dry_run=False,
                ),
                "already-applied",
            )
            self.assertFalse(
                any(path.name.startswith(".r3-") for path in (root / "spec").iterdir())
            )

    def test_r3_repository_clarification_dry_run_is_clean(self) -> None:
        if self.r3_tracked_status.startswith(
            ("witness-", "gate6-convergence-")
        ):
            self.assertEqual(
                len(
                    m2_policy.validate_r3_pre_clarification_archive(
                        ROOT, self.r3_witness_damage_raw
                    )
                ),
                11,
            )
            self.assertEqual(
                len(
                    m2_policy.validate_r3_pre_damage_schema_archive(
                        ROOT, self.r3_witness_damage_raw
                    )
                ),
                11,
            )
            self.assertEqual(
                len(
                    m2_policy.validate_r3_pre_independence_witness_archive(
                        ROOT,
                        (
                            self.r3_convergence_damage_raw
                            if self.r3_tracked_status.startswith(
                                "gate6-convergence-"
                            )
                            else self.r3_witness_damage_raw
                        ),
                    )
                ),
                11,
            )
            if self.r3_tracked_status.startswith("gate6-convergence-"):
                self.assertEqual(
                    len(
                        m2_policy.validate_r3_pre_gate6_convergence_archive(
                            ROOT, self.r3_convergence_damage_raw
                        )
                    ),
                    11,
                )
            return
        if self.r3_tracked_status.startswith("damage-schema-"):
            self.assertEqual(
                len(
                    m2_policy.validate_r3_pre_clarification_archive(
                        ROOT, self.r3_schema_damage_raw
                    )
                ),
                11,
            )
            self.assertEqual(
                len(
                    m2_policy.validate_r3_pre_damage_schema_archive(
                        ROOT, self.r3_schema_damage_raw
                    )
                ),
                11,
            )
            return
        staged = self.r3_tracked_status == "clarification-staged"
        self.assertEqual(
            m2_policy.apply_r3_mapping_clarification_bundle(
                ROOT,
                self.r3_clarified_bundle,
                self.r3_bootstrap_raw,
                self.r3_owner_fixture_raw,
                self.r3_projection.python_reproduction_receipt,
                self.r3_rust_route_receipt,
                self.r3_clarified_python_limits_receipt,
                self.r3_clarified_rust_limits_receipt,
                (
                    Path("/tmp/golden-board-r3-clarification-rust.XC66YD")
                    if staged
                    else None
                ),
                (
                    self.r3_clarified_stage_files
                    if staged
                    else None
                ),
                dry_run=True,
            ),
            "dry-run-clean" if staged else "already-applied",
        )

    def test_r3_damage_schema_refreeze_bytes_and_archives_are_exact(self) -> None:
        self.assertEqual(
            (
                len(self.r3_schema_damage_raw),
                sha256(self.r3_schema_damage_raw).hexdigest(),
            ),
            (
                51_345,
                "337810fe852443d43d06f6563bd25d00498d2bce727fb9558069c9a1ab1e8f6f",
            ),
        )
        self.assertEqual(
            sha256(self.r3_schema_limits_raw).hexdigest(),
            "6d9ce190fd510dc95c2a49fb371d7b22174771d798f14788d270e3d42b041691",
        )
        self.assertEqual(
            sha256(self.r3_schema_python_limits_receipt).hexdigest(),
            "275f35adb5b62bd799f23ddbbaec3f36e0c6f6cb39c18662012ffe155ca2e0c8",
        )
        self.assertEqual(
            sha256(self.r3_schema_rust_limits_receipt).hexdigest(),
            "7dfe55fe169e1f176eff726602678c1596b4822357dfa1c470306b9c223b81c1",
        )
        self.assertEqual(
            sha256(self.r3_schema_promotion_raw).hexdigest(),
            "3e0893b8376c2fae2140c9349e7b5b302ee87de443cd4e497dbfba19b2b6adc9",
        )
        self.assertEqual(
            len(
                m2_policy.validate_r3_pre_clarification_archive(
                    ROOT, self.r3_schema_damage_raw
                )
            ),
            11,
        )
        self.assertEqual(
            len(
                m2_policy.validate_r3_pre_damage_schema_archive(
                    ROOT, self.r3_schema_damage_raw
                )
            ),
            11,
        )
        admitted = m2_policy._load_r3_damage_schema_clarified_owner_set(
            self.r3_schema_bundle,
            self.r3_bootstrap_raw,
            self.r3_owner_fixture_raw,
            self.r3_projection.python_reproduction_receipt,
            self.r3_rust_route_receipt,
            self.r3_schema_python_limits_receipt,
            self.r3_schema_rust_limits_receipt,
        )
        self.assertEqual(
            (
                admitted.damage_policy_sha256,
                admitted.profile_limits_sha256,
                admitted.promotion_sha256,
            ),
            (
                "337810fe852443d43d06f6563bd25d00498d2bce727fb9558069c9a1ab1e8f6f",
                "6d9ce190fd510dc95c2a49fb371d7b22174771d798f14788d270e3d42b041691",
                "3e0893b8376c2fae2140c9349e7b5b302ee87de443cd4e497dbfba19b2b6adc9",
            ),
        )

    def test_r3_damage_schema_apply_is_atomic_status_last_and_idempotent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="gb-r3-damage-schema-apply-"
        ) as directory:
            root = Path(directory)
            self._write_r3_damage_schema_workspace(root)
            before = {
                path.name: path.read_bytes() for path in (root / "spec").iterdir()
            }
            self.assertEqual(
                self._apply_r3_damage_schema(root, dry_run=True),
                "dry-run-clean",
            )
            self.assertEqual(
                {
                    path.name: path.read_bytes()
                    for path in (root / "spec").iterdir()
                    if not path.name.startswith(".rust-")
                },
                before,
            )
            real_replace = m2_policy.os.replace
            writes: list[str] = []

            def observed_replace(source: object, destination: object) -> None:
                destination_path = Path(destination)  # type: ignore[arg-type]
                if destination_path.name in {
                    "damage-policy-v1.toml",
                    "profile-limits-v1.toml",
                    "m2-r3-owner-promotion-v1.toml",
                }:
                    writes.append(destination_path.name)
                real_replace(source, destination)

            with mock.patch.object(
                m2_policy.os, "replace", side_effect=observed_replace
            ):
                self.assertEqual(
                    self._apply_r3_damage_schema(root, dry_run=False),
                    "applied",
                )
            self.assertEqual(
                writes,
                [
                    "damage-policy-v1.toml",
                    "profile-limits-v1.toml",
                    "m2-r3-owner-promotion-v1.toml",
                ],
            )
            self.assertEqual(
                (root / "spec/damage-policy-v1.toml").read_bytes(),
                self.r3_schema_damage_raw,
            )
            self.assertEqual(
                (root / "spec/profile-limits-v1.toml").read_bytes(),
                self.r3_schema_limits_raw,
            )
            self.assertEqual(
                (root / "spec/m2-r3-owner-promotion-v1.toml").read_bytes(),
                self.r3_schema_promotion_raw,
            )
            self.assertEqual(
                m2_policy.apply_r3_damage_schema_clarification_bundle(
                    root,
                    self.r3_schema_bundle,
                    self.r3_bootstrap_raw,
                    self.r3_owner_fixture_raw,
                    self.r3_projection.python_reproduction_receipt,
                    self.r3_rust_route_receipt,
                    self.r3_schema_python_limits_receipt,
                    self.r3_schema_rust_limits_receipt,
                    None,
                    None,
                    dry_run=False,
                ),
                "already-applied",
            )

    def test_r3_damage_schema_apply_rejects_stale_links_and_candidate(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="gb-r3-damage-schema-stale-"
        ) as directory:
            root = Path(directory)
            self._write_r3_damage_schema_workspace(root)
            limits = root / "spec/profile-limits-v1.toml"
            limits.write_bytes(limits.read_bytes() + b" ")
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3_damage_schema(root, dry_run=True)
            self.assertEqual(
                caught.exception.reason, "r3-damage-schema-precondition"
            )

        with tempfile.TemporaryDirectory(
            prefix="gb-r3-damage-schema-link-"
        ) as directory:
            root = Path(directory)
            self._write_r3_damage_schema_workspace(root)
            target = root / "outside"
            target.write_bytes(b"outside")
            destination = root / "spec/profile-limits-v1.toml"
            destination.unlink()
            os.symlink(target, destination)
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3_damage_schema(root, dry_run=True)
            self.assertEqual(
                caught.exception.reason, "r3-damage-schema-destination"
            )
            self.assertEqual(target.read_bytes(), b"outside")

        with tempfile.TemporaryDirectory(
            prefix="gb-r3-damage-schema-candidate-"
        ) as directory:
            root = Path(directory)
            self._write_r3_damage_schema_workspace(root)
            candidate = root / (
                "artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0"
            )
            candidate.mkdir()
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3_damage_schema(root, dry_run=True)
            self.assertEqual(
                caught.exception.reason, "r3-damage-schema-candidate-present"
            )

    def test_r3_damage_schema_apply_rolls_back_before_authority(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="gb-r3-damage-schema-rollback-"
        ) as directory:
            root = Path(directory)
            self._write_r3_damage_schema_workspace(root)
            expected = {
                name: (root / "spec" / name).read_bytes()
                for name in (
                    "damage-policy-v1.toml",
                    "profile-limits-v1.toml",
                    "m2-r3-owner-promotion-v1.toml",
                )
            }
            real_replace = m2_policy.os.replace
            injected = False

            def failing_replace(source: object, destination: object) -> None:
                nonlocal injected
                source_path = Path(source)  # type: ignore[arg-type]
                destination_path = Path(destination)  # type: ignore[arg-type]
                if (
                    not injected
                    and destination_path.name
                    == "m2-r3-owner-promotion-v1.toml"
                    and source_path.parent.name.startswith(
                        ".r3-damage-schema-stage-"
                    )
                ):
                    injected = True
                    raise OSError("injected schema authority failure")
                real_replace(source, destination)

            with mock.patch.object(
                m2_policy.os, "replace", side_effect=failing_replace
            ):
                with self.assertRaisesRegex(
                    OSError, "injected schema authority failure"
                ):
                    self._apply_r3_damage_schema(root, dry_run=False)
            self.assertTrue(injected)
            self.assertEqual(
                {
                    name: (root / "spec" / name).read_bytes()
                    for name in expected
                },
                expected,
            )

    def test_r3_damage_schema_apply_rejects_stale_stage_and_archive_link(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="gb-r3-damage-schema-stage-"
        ) as directory:
            root = Path(directory)
            self._write_r3_damage_schema_workspace(root)
            stage = root / ".rust-damage-schema-stage"
            self._write_r3_damage_schema_stage(stage)
            prefix = stage / "route-prefix-sector-0.bin"
            changed = bytearray(prefix.read_bytes())
            changed[-1] ^= 1
            prefix.write_bytes(bytes(changed))
            before = {
                name: (root / "spec" / name).read_bytes()
                for name in (
                    "damage-policy-v1.toml",
                    "profile-limits-v1.toml",
                    "m2-r3-owner-promotion-v1.toml",
                )
            }
            with self.assertRaises(m2_policy.PolicyError):
                self._apply_r3_damage_schema(
                    root, rust_stage=stage, dry_run=False
                )
            self.assertEqual(
                {
                    name: (root / "spec" / name).read_bytes()
                    for name in before
                },
                before,
            )

        with tempfile.TemporaryDirectory(
            prefix="gb-r3-damage-schema-archive-link-"
        ) as directory:
            root = Path(directory)
            self._write_r3_damage_schema_workspace(root)
            archived = root / (
                "artifacts/history/m2-r3-pre-damage-artifact-schema-"
                "clarification/owners/profile-limits-v1.toml"
            )
            outside = root / "outside-limits"
            outside.write_bytes(archived.read_bytes())
            archived.unlink()
            os.symlink(outside, archived)
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3_damage_schema(root, dry_run=True)
            self.assertEqual(
                caught.exception.reason, "r3-schema-archive-file"
            )
            self.assertEqual(
                sha256(outside.read_bytes()).hexdigest(),
                "54c62adfbee30bb84d9b4029059134db81c8e5794cd11c7c716b9b15ae1749e7",
            )

    def test_r3_witness_refreeze_bytes_archive_and_mutations_are_exact(
        self,
    ) -> None:
        self.assertEqual(
            (
                len(self.r3_witness_damage_raw),
                sha256(self.r3_witness_damage_raw).hexdigest(),
                len(self.r3_witness_limits_raw),
                sha256(self.r3_witness_limits_raw).hexdigest(),
                len(self.r3_witness_python_limits_receipt),
                sha256(self.r3_witness_python_limits_receipt).hexdigest(),
                len(self.r3_witness_rust_limits_receipt),
                sha256(self.r3_witness_rust_limits_receipt).hexdigest(),
                len(self.r3_witness_promotion_raw),
                sha256(self.r3_witness_promotion_raw).hexdigest(),
            ),
            (
                62_627,
                "ccd494ff608b68ad7bce09a4fb79e4f49846de595364de8ca209ff558fbc81ed",
                5_434,
                "6320464174b2f411d41e125cff4a875a1f337a31157dac6e2f429f1aa57b2a0d",
                262,
                "1e71b339bbe1658f3bba6259f71f4dbdeb0023c4ab723bc16ac4d16063125b6f",
                260,
                "1e2f2f45b9042e5bb36186bbd0c3ba2e8f3b21b4619d64527fe5464be6b4649d",
                7_701,
                "ec24331ed85ff92589c00f3bdadfa6368bd6461da067b64d38c297525c2f3ca1",
            ),
        )
        archived = m2_policy.validate_r3_pre_independence_witness_archive(
            ROOT, self.r3_witness_damage_raw
        )
        self.assertEqual(len(archived), 11)
        precursor_lines = archived[
            "owners/m2-r3-owner-promotion-v1.toml"
        ].splitlines(keepends=True)
        final_lines = self.r3_witness_promotion_raw.splitlines(keepends=True)
        self.assertEqual(len(precursor_lines), len(final_lines))
        changed = [
            (before, after)
            for before, after in zip(precursor_lines, final_lines, strict=True)
            if before != after
        ]
        self.assertEqual(len(changed), 4)
        self.assertTrue(all(before.startswith(b"sha256 = ") for before, _ in changed[:1]))
        self.assertEqual(
            sorted(after.split(b" = ", 1)[0] for _, after in changed),
            [
                b"python_reproduction_sha256",
                b"rust_reproduction_sha256",
                b"sha256",
                b"sha256",
            ],
        )
        admitted = m2_policy._load_r3_pre_gate6_convergence_owner_set(
            self.r3_witness_bundle,
            self.r3_bootstrap_raw,
            self.r3_owner_fixture_raw,
            self.r3_projection.python_reproduction_receipt,
            self.r3_rust_route_receipt,
            self.r3_witness_python_limits_receipt,
            self.r3_witness_rust_limits_receipt,
        )
        self.assertEqual(
            (
                admitted.damage_policy_sha256,
                admitted.profile_limits_sha256,
                admitted.promotion_sha256,
            ),
            (
                "ccd494ff608b68ad7bce09a4fb79e4f49846de595364de8ca209ff558fbc81ed",
                "6320464174b2f411d41e125cff4a875a1f337a31157dac6e2f429f1aa57b2a0d",
                "ec24331ed85ff92589c00f3bdadfa6368bd6461da067b64d38c297525c2f3ca1",
            ),
        )

    def test_r3_witness_apply_is_atomic_status_last_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gb-r3-witness-apply-") as directory:
            root = Path(directory)
            self._write_r3_witness_workspace(root)
            before = {
                path.name: path.read_bytes() for path in (root / "spec").iterdir()
            }
            self.assertEqual(
                self._apply_r3_witness(root, dry_run=True), "dry-run-clean"
            )
            self.assertEqual(
                {
                    path.name: path.read_bytes()
                    for path in (root / "spec").iterdir()
                    if not path.name.startswith(".rust-")
                },
                before,
            )
            real_replace = m2_policy.os.replace
            writes: list[str] = []

            def observed_replace(source: object, destination: object) -> None:
                destination_path = Path(destination)  # type: ignore[arg-type]
                if destination_path.name in {
                    "damage-policy-v1.toml",
                    "profile-limits-v1.toml",
                    "m2-r3-owner-promotion-v1.toml",
                }:
                    writes.append(destination_path.name)
                real_replace(source, destination)

            with mock.patch.object(
                m2_policy.os, "replace", side_effect=observed_replace
            ):
                self.assertEqual(
                    self._apply_r3_witness(root, dry_run=False), "applied"
                )
            self.assertEqual(
                writes,
                [
                    "damage-policy-v1.toml",
                    "profile-limits-v1.toml",
                    "m2-r3-owner-promotion-v1.toml",
                ],
            )
            self.assertEqual(
                m2_policy.apply_r3_independence_witness_clarification_bundle(
                    root,
                    self.r3_witness_bundle,
                    self.r3_bootstrap_raw,
                    self.r3_owner_fixture_raw,
                    self.r3_projection.python_reproduction_receipt,
                    self.r3_rust_route_receipt,
                    self.r3_witness_python_limits_receipt,
                    self.r3_witness_rust_limits_receipt,
                    None,
                    None,
                    dry_run=False,
                ),
                "already-applied",
            )
            self.assertFalse(
                any(
                    path.name.startswith(".r3-witness-")
                    for path in (root / "spec").iterdir()
                )
            )

    def test_r3_witness_apply_rejects_stale_links_stage_and_candidate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gb-r3-witness-stale-") as directory:
            root = Path(directory)
            self._write_r3_witness_workspace(root)
            limits = root / "spec/profile-limits-v1.toml"
            limits.write_bytes(limits.read_bytes() + b" ")
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3_witness(root, dry_run=True)
            self.assertEqual(caught.exception.reason, "r3-witness-precondition")

        with tempfile.TemporaryDirectory(prefix="gb-r3-witness-link-") as directory:
            root = Path(directory)
            self._write_r3_witness_workspace(root)
            target = root / "outside"
            target.write_bytes(b"outside")
            destination = root / "spec/profile-limits-v1.toml"
            destination.unlink()
            os.symlink(target, destination)
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3_witness(root, dry_run=True)
            self.assertEqual(caught.exception.reason, "r3-witness-destination")
            self.assertEqual(target.read_bytes(), b"outside")

        with tempfile.TemporaryDirectory(prefix="gb-r3-witness-hardlink-") as directory:
            root = Path(directory)
            self._write_r3_witness_workspace(root)
            archived = root / (
                "artifacts/history/m2-r3-pre-independence-witness-"
                "clarification/owners/profile-limits-v1.toml"
            )
            outside = root / "outside-limits"
            os.link(archived, outside)
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3_witness(root, dry_run=True)
            self.assertEqual(caught.exception.reason, "r3-witness-archive-file")

        with tempfile.TemporaryDirectory(prefix="gb-r3-witness-stage-") as directory:
            root = Path(directory)
            self._write_r3_witness_workspace(root)
            stage = root / ".rust-witness-stage"
            self._write_r3_witness_stage(stage)
            prefix = stage / "route-prefix-sector-0.bin"
            changed = bytearray(prefix.read_bytes())
            changed[-1] ^= 1
            prefix.write_bytes(bytes(changed))
            with self.assertRaises(m2_policy.PolicyError):
                self._apply_r3_witness(root, rust_stage=stage, dry_run=True)

        with tempfile.TemporaryDirectory(prefix="gb-r3-witness-candidate-") as directory:
            root = Path(directory)
            self._write_r3_witness_workspace(root)
            (root / "artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0").mkdir()
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3_witness(root, dry_run=True)
            self.assertEqual(caught.exception.reason, "r3-witness-candidate-present")

    def test_r3_witness_apply_revalidates_and_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gb-r3-witness-race-") as directory:
            root = Path(directory)
            self._write_r3_witness_workspace(root)
            original = (root / "spec/profile-limits-v1.toml").read_bytes()
            real_validate = m2_policy.validate_r3_pre_independence_witness_archive
            calls = 0

            def mutate_then_validate(*args: object, **kwargs: object) -> object:
                nonlocal calls
                calls += 1
                if calls == 2:
                    (root / "spec/profile-limits-v1.toml").write_bytes(
                        original + b" "
                    )
                return real_validate(*args, **kwargs)

            with mock.patch.object(
                m2_policy,
                "validate_r3_pre_independence_witness_archive",
                side_effect=mutate_then_validate,
            ):
                with self.assertRaises(m2_policy.PolicyError) as caught:
                    self._apply_r3_witness(root, dry_run=False)
            self.assertEqual(caught.exception.reason, "r3-witness-prewrite")

        with tempfile.TemporaryDirectory(prefix="gb-r3-witness-rollback-") as directory:
            root = Path(directory)
            self._write_r3_witness_workspace(root)
            expected = {
                name: (root / "spec" / name).read_bytes()
                for name in (
                    "damage-policy-v1.toml",
                    "profile-limits-v1.toml",
                    "m2-r3-owner-promotion-v1.toml",
                )
            }
            real_replace = m2_policy.os.replace
            injected = False

            def failing_replace(source: object, destination: object) -> None:
                nonlocal injected
                source_path = Path(source)  # type: ignore[arg-type]
                destination_path = Path(destination)  # type: ignore[arg-type]
                if (
                    not injected
                    and destination_path.name
                    == "m2-r3-owner-promotion-v1.toml"
                    and source_path.parent.name.startswith(".r3-witness-stage-")
                ):
                    injected = True
                    raise OSError("injected witness authority failure")
                real_replace(source, destination)

            with mock.patch.object(
                m2_policy.os, "replace", side_effect=failing_replace
            ):
                with self.assertRaisesRegex(
                    OSError, "injected witness authority failure"
                ):
                    self._apply_r3_witness(root, dry_run=False)
            self.assertTrue(injected)
            self.assertEqual(
                {
                    name: (root / "spec" / name).read_bytes()
                    for name in expected
                },
                expected,
            )

    def test_r3_repository_witness_refreeze_dry_run_is_clean(self) -> None:
        self.assertIn(
            self.r3_tracked_status,
            {
                "witness-staged",
                "witness-final",
                "gate6-convergence-staged",
                "gate6-convergence-final",
            },
        )
        if self.r3_tracked_status.startswith("gate6-convergence-"):
            self.assertEqual(
                len(
                    m2_policy.validate_r3_pre_gate6_convergence_archive(
                        ROOT, self.r3_convergence_damage_raw
                    )
                ),
                11,
            )
            return
        staged = self.r3_tracked_status == "witness-staged"
        self.assertEqual(
            m2_policy.apply_r3_independence_witness_clarification_bundle(
                ROOT,
                self.r3_witness_bundle,
                self.r3_bootstrap_raw,
                self.r3_owner_fixture_raw,
                self.r3_projection.python_reproduction_receipt,
                self.r3_rust_route_receipt,
                self.r3_witness_python_limits_receipt,
                self.r3_witness_rust_limits_receipt,
                (
                    Path("/tmp/golden-board-r3-proof-owner-rust.jVUby4")
                    if staged
                    else None
                ),
                self.r3_witness_stage_files if staged else None,
                dry_run=True,
            ),
            "dry-run-clean" if staged else "already-applied",
        )

    def test_r3_gate6_convergence_bytes_archive_and_dag_are_exact(self) -> None:
        self.assertEqual(
            tuple(
                (len(raw), sha256(raw).hexdigest())
                for raw in (
                    self.r3_convergence_damage_raw,
                    self.r3_convergence_limits_raw,
                    self.r3_convergence_python_limits_receipt,
                    self.r3_convergence_rust_limits_receipt,
                    self.r3_convergence_promotion_raw,
                )
            ),
            (
                (
                    65_343,
                    "b3b28f00d3ba04addbed4517eb1abb4ecd02796176eaaecdbc1d47f1f39509df",
                ),
                (
                    5_434,
                    "32c2bd0cb978eb800bed7f8ac1c7db223b593b4cf3bad951a9ce4cdc3a568902",
                ),
                (
                    262,
                    "08c030afabe1291b3fa0b20a27666e480a242801fc1978f27992a161cf50b883",
                ),
                (
                    260,
                    "d52a1e9770438e53354599ca899ec0aad328c46739b42d27dec048ec9977750b",
                ),
                (
                    7_701,
                    "8c30ae216f5a3fd8ee13f2821d38412afa6c50303c9140cbe54da8610df9cd8d",
                ),
            ),
        )
        archived = m2_policy.validate_r3_pre_gate6_convergence_archive(
            ROOT, self.r3_convergence_damage_raw
        )
        self.assertEqual(len(archived), 11)
        self.assertEqual(
            sha256(
                ROOT.joinpath(
                    "artifacts/history/m2-r3-pre-gate6-convergence-"
                    "clarification/archive-files.sha256"
                ).read_bytes()
            ).hexdigest(),
            "d1ece9d02628a624d58837b9a1c1994dfb521e96303df66758c95880b2d378e4",
        )
        before_lines = archived[
            "owners/m2-r3-owner-promotion-v1.toml"
        ].splitlines(keepends=True)
        after_lines = self.r3_convergence_promotion_raw.splitlines(
            keepends=True
        )
        self.assertEqual(len(before_lines), len(after_lines))
        changed = [
            (before, after)
            for before, after in zip(before_lines, after_lines, strict=True)
            if before != after
        ]
        self.assertEqual(len(changed), 4)
        self.assertEqual(
            sorted(after.split(b" = ", 1)[0] for _, after in changed),
            [
                b"python_reproduction_sha256",
                b"rust_reproduction_sha256",
                b"sha256",
                b"sha256",
            ],
        )
        admitted = m2_policy.load_r3_promoted_owner_set(
            self.r3_convergence_bundle,
            self.r3_bootstrap_raw,
            self.r3_owner_fixture_raw,
            self.r3_projection.python_reproduction_receipt,
            self.r3_rust_route_receipt,
            self.r3_convergence_python_limits_receipt,
            self.r3_convergence_rust_limits_receipt,
        )
        self.assertEqual(
            (
                admitted.damage_policy_sha256,
                admitted.profile_limits_sha256,
                admitted.promotion_sha256,
            ),
            (
                "b3b28f00d3ba04addbed4517eb1abb4ecd02796176eaaecdbc1d47f1f39509df",
                "32c2bd0cb978eb800bed7f8ac1c7db223b593b4cf3bad951a9ce4cdc3a568902",
                "8c30ae216f5a3fd8ee13f2821d38412afa6c50303c9140cbe54da8610df9cd8d",
            ),
        )

    def test_r3_gate6_convergence_apply_is_atomic_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="gb-r3-convergence-apply-"
        ) as directory:
            root = Path(directory)
            self._write_r3_convergence_workspace(root)
            before = {
                path.name: path.read_bytes()
                for path in (root / "spec").iterdir()
            }
            self.assertEqual(
                self._apply_r3_convergence(root, dry_run=True),
                "dry-run-clean",
            )
            self.assertEqual(
                {
                    path.name: path.read_bytes()
                    for path in (root / "spec").iterdir()
                    if not path.name.startswith(".rust-")
                },
                before,
            )
            real_replace = m2_policy.os.replace
            writes: list[str] = []

            def observed_replace(source: object, destination: object) -> None:
                destination_path = Path(destination)  # type: ignore[arg-type]
                if destination_path.name in {
                    "damage-policy-v1.toml",
                    "profile-limits-v1.toml",
                    "m2-r3-owner-promotion-v1.toml",
                }:
                    writes.append(destination_path.name)
                real_replace(source, destination)

            with mock.patch.object(
                m2_policy.os, "replace", side_effect=observed_replace
            ):
                self.assertEqual(
                    self._apply_r3_convergence(root, dry_run=False),
                    "applied",
                )
            self.assertEqual(
                writes,
                [
                    "damage-policy-v1.toml",
                    "profile-limits-v1.toml",
                    "m2-r3-owner-promotion-v1.toml",
                ],
            )
            self.assertEqual(
                m2_policy.apply_r3_gate6_convergence_clarification_bundle(
                    root,
                    self.r3_convergence_bundle,
                    self.r3_bootstrap_raw,
                    self.r3_owner_fixture_raw,
                    self.r3_projection.python_reproduction_receipt,
                    self.r3_rust_route_receipt,
                    self.r3_convergence_python_limits_receipt,
                    self.r3_convergence_rust_limits_receipt,
                    None,
                    None,
                    dry_run=False,
                ),
                "already-applied",
            )
            self.assertFalse(
                any(
                    path.name.startswith(".r3-convergence-")
                    for path in (root / "spec").iterdir()
                )
            )

    def test_r3_gate6_convergence_rejects_stale_links_stage_and_candidate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="gb-r3-convergence-stale-"
        ) as directory:
            root = Path(directory)
            self._write_r3_convergence_workspace(root)
            limits = root / "spec/profile-limits-v1.toml"
            limits.write_bytes(limits.read_bytes() + b" ")
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3_convergence(root, dry_run=True)
            self.assertEqual(
                caught.exception.reason, "r3-convergence-precondition"
            )

        with tempfile.TemporaryDirectory(
            prefix="gb-r3-convergence-link-"
        ) as directory:
            root = Path(directory)
            self._write_r3_convergence_workspace(root)
            target = root / "outside"
            target.write_bytes(b"outside")
            destination = root / "spec/profile-limits-v1.toml"
            destination.unlink()
            os.symlink(target, destination)
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3_convergence(root, dry_run=True)
            self.assertEqual(
                caught.exception.reason, "r3-convergence-destination"
            )
            self.assertEqual(target.read_bytes(), b"outside")

        with tempfile.TemporaryDirectory(
            prefix="gb-r3-convergence-hardlink-"
        ) as directory:
            root = Path(directory)
            self._write_r3_convergence_workspace(root)
            archived = root / (
                "artifacts/history/m2-r3-pre-gate6-convergence-"
                "clarification/owners/profile-limits-v1.toml"
            )
            os.link(archived, root / "outside-limits")
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3_convergence(root, dry_run=True)
            self.assertEqual(
                caught.exception.reason, "r3-convergence-archive-file"
            )

        with tempfile.TemporaryDirectory(
            prefix="gb-r3-convergence-stage-"
        ) as directory:
            root = Path(directory)
            self._write_r3_convergence_workspace(root)
            stage = root / ".rust-convergence-stage"
            self._write_r3_convergence_stage(stage)
            prefix = stage / "route-prefix-sector-0.bin"
            changed = bytearray(prefix.read_bytes())
            changed[-1] ^= 1
            prefix.write_bytes(bytes(changed))
            with self.assertRaises(m2_policy.PolicyError):
                self._apply_r3_convergence(
                    root, rust_stage=stage, dry_run=True
                )

        with tempfile.TemporaryDirectory(
            prefix="gb-r3-convergence-candidate-"
        ) as directory:
            root = Path(directory)
            self._write_r3_convergence_workspace(root)
            root.joinpath(
                "artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0"
            ).mkdir()
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3_convergence(root, dry_run=True)
            self.assertEqual(
                caught.exception.reason, "r3-convergence-candidate-present"
            )

    def test_r3_gate6_convergence_revalidates_and_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="gb-r3-convergence-race-"
        ) as directory:
            root = Path(directory)
            self._write_r3_convergence_workspace(root)
            limits_path = root / "spec/profile-limits-v1.toml"
            original = limits_path.read_bytes()
            real_validate = (
                m2_policy.validate_r3_pre_gate6_convergence_archive
            )
            calls = 0

            def mutate_then_validate(
                *args: object, **kwargs: object
            ) -> object:
                nonlocal calls
                calls += 1
                if calls == 2:
                    limits_path.write_bytes(original + b" ")
                return real_validate(*args, **kwargs)

            with mock.patch.object(
                m2_policy,
                "validate_r3_pre_gate6_convergence_archive",
                side_effect=mutate_then_validate,
            ):
                with self.assertRaises(m2_policy.PolicyError) as caught:
                    self._apply_r3_convergence(root, dry_run=False)
            self.assertEqual(
                caught.exception.reason, "r3-convergence-prewrite"
            )

        with tempfile.TemporaryDirectory(
            prefix="gb-r3-convergence-rollback-"
        ) as directory:
            root = Path(directory)
            self._write_r3_convergence_workspace(root)
            expected = {
                name: (root / "spec" / name).read_bytes()
                for name in (
                    "damage-policy-v1.toml",
                    "profile-limits-v1.toml",
                    "m2-r3-owner-promotion-v1.toml",
                )
            }
            real_replace = m2_policy.os.replace
            injected = False

            def failing_replace(source: object, destination: object) -> None:
                nonlocal injected
                source_path = Path(source)  # type: ignore[arg-type]
                destination_path = Path(destination)  # type: ignore[arg-type]
                if (
                    not injected
                    and destination_path.name
                    == "m2-r3-owner-promotion-v1.toml"
                    and source_path.parent.name.startswith(
                        ".r3-convergence-stage-"
                    )
                ):
                    injected = True
                    raise OSError("injected convergence authority failure")
                real_replace(source, destination)

            with mock.patch.object(
                m2_policy.os, "replace", side_effect=failing_replace
            ):
                with self.assertRaisesRegex(
                    OSError, "injected convergence authority failure"
                ):
                    self._apply_r3_convergence(root, dry_run=False)
            self.assertTrue(injected)
            self.assertEqual(
                {
                    name: (root / "spec" / name).read_bytes()
                    for name in expected
                },
                expected,
            )

    def test_r3_clarification_apply_write_set_and_idempotence_are_exact(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="gb-r3-clarification-apply-"
        ) as directory:
            root = Path(directory)
            self._write_r3_clarification_workspace(root)
            (root / "docs").mkdir()
            sentinel = root / "docs/roadmap.md"
            sentinel.write_bytes(b"roadmap-sentinel")
            profile_before = (root / "spec/profile-policy-v1.toml").read_bytes()
            route_before = (root / "spec/route-data-v1.json").read_bytes()
            self.assertEqual(
                self._apply_r3_clarification(root, dry_run=False), "applied"
            )
            self.assertEqual(
                (root / "spec/profile-policy-v1.toml").read_bytes(),
                profile_before,
            )
            self.assertEqual(
                (root / "spec/route-data-v1.json").read_bytes(), route_before
            )
            self.assertEqual(
                (root / "spec/damage-policy-v1.toml").read_bytes(),
                self.r3_clarified_damage_raw,
            )
            self.assertEqual(
                (root / "spec/profile-limits-v1.toml").read_bytes(),
                self.r3_clarified_limits_raw,
            )
            self.assertEqual(
                (
                    root / "spec/m2-r3-owner-promotion-v1.toml"
                ).read_bytes(),
                self.r3_clarified_promotion_raw,
            )
            self.assertEqual(sentinel.read_bytes(), b"roadmap-sentinel")
            self.assertEqual(
                m2_policy.apply_r3_mapping_clarification_bundle(
                    root,
                    self.r3_clarified_bundle,
                    self.r3_bootstrap_raw,
                    self.r3_owner_fixture_raw,
                    self.r3_projection.python_reproduction_receipt,
                    self.r3_rust_route_receipt,
                    self.r3_clarified_python_limits_receipt,
                    self.r3_clarified_rust_limits_receipt,
                    None,
                    None,
                    dry_run=False,
                ),
                "already-applied",
            )
            self.assertFalse(
                any(
                    path.name.startswith(".r3-clarification-")
                    for path in (root / "spec").iterdir()
                )
            )

    def test_r3_clarification_apply_rejects_stale_links_archive_and_rolls_back(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="gb-r3-clarification-stale-"
        ) as directory:
            root = Path(directory)
            self._write_r3_clarification_workspace(root)
            limits_path = root / "spec/profile-limits-v1.toml"
            limits_path.write_bytes(limits_path.read_bytes() + b" ")
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3_clarification(root, dry_run=True)
            self.assertEqual(
                caught.exception.reason, "r3-clarification-precondition"
            )

        with tempfile.TemporaryDirectory(
            prefix="gb-r3-clarification-candidate-"
        ) as directory:
            root = Path(directory)
            self._write_r3_clarification_workspace(root)
            (root / "artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0").mkdir()
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3_clarification(root, dry_run=True)
            self.assertEqual(
                caught.exception.reason,
                "r3-clarification-candidate-present",
            )

        with tempfile.TemporaryDirectory(
            prefix="gb-r3-clarification-archive-"
        ) as directory:
            root = Path(directory)
            self._write_r3_clarification_workspace(root)
            archive_file = root / (
                "artifacts/history/m2-r3-pre-d7-mapping-clarification/"
                "owners/limits-rust-reproduction.json"
            )
            outside = root / "outside"
            outside.write_bytes(archive_file.read_bytes())
            archive_file.unlink()
            archive_file.symlink_to(outside)
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3_clarification(root, dry_run=True)
            self.assertEqual(caught.exception.reason, "r3-archive-file")

        with tempfile.TemporaryDirectory(
            prefix="gb-r3-clarification-link-"
        ) as directory:
            root = Path(directory)
            self._write_r3_clarification_workspace(root)
            promotion_path = root / "spec/m2-r3-owner-promotion-v1.toml"
            outside = root / "outside-promotion"
            outside.write_bytes(promotion_path.read_bytes())
            promotion_path.unlink()
            promotion_path.symlink_to(outside)
            with self.assertRaises(m2_policy.PolicyError) as caught:
                self._apply_r3_clarification(root, dry_run=True)
            self.assertEqual(
                caught.exception.reason, "r3-clarification-destination"
            )
            self.assertEqual(outside.read_bytes(), self.r3_promotion_raw)

        with tempfile.TemporaryDirectory(
            prefix="gb-r3-clarification-rollback-"
        ) as directory:
            root = Path(directory)
            self._write_r3_clarification_workspace(root)
            initial = {
                path.name: path.read_bytes()
                for path in (root / "spec").iterdir()
            }
            real_replace = os.replace
            destinations: list[str] = []

            def fail_authority(source: object, destination: object) -> None:
                source_path = Path(source)  # type: ignore[arg-type]
                destination_path = Path(destination)  # type: ignore[arg-type]
                destinations.append(destination_path.name)
                if (
                    source_path.parent.name.startswith(
                        ".r3-clarification-stage-"
                    )
                    and destination_path.name
                    == "m2-r3-owner-promotion-v1.toml"
                ):
                    raise OSError("injected clarification write failure")
                real_replace(source, destination)

            with mock.patch.object(
                m2_policy.os, "replace", side_effect=fail_authority
            ):
                with self.assertRaisesRegex(
                    OSError, "injected clarification write failure"
                ):
                    self._apply_r3_clarification(root, dry_run=False)
            self.assertEqual(
                destinations[:3],
                [
                    "damage-policy-v1.toml",
                    "profile-limits-v1.toml",
                    "m2-r3-owner-promotion-v1.toml",
                ],
            )
            self.assertEqual(
                initial,
                {
                    path.name: path.read_bytes()
                    for path in (root / "spec").iterdir()
                },
            )

    def test_r3_apply_rolls_back_before_status_authority_on_write_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="gb-r3-rollback-") as directory:
            root = Path(directory)
            self._write_r3_workspace(root)
            initial = {
                path.name: path.read_bytes()
                for path in (root / "spec").iterdir()
            }
            real_replace = os.replace
            destinations = []

            def fail_authority(source: object, destination: object) -> None:
                destination_path = Path(destination)  # type: ignore[arg-type]
                destinations.append(destination_path.name)
                source_path = Path(source)  # type: ignore[arg-type]
                if (
                    destination_path.name
                    == "m2-r3-owner-promotion-v1.toml"
                    and source_path.parent.name.startswith(
                        ".r3-promotion-stage-"
                    )
                ):
                    raise OSError("injected promotion write failure")
                real_replace(source, destination)

            with mock.patch.object(
                m2_policy.os, "replace", side_effect=fail_authority
            ):
                with self.assertRaisesRegex(
                    OSError, "injected promotion write failure"
                ):
                    self._apply_r3(root, dry_run=False)
            self.assertEqual(
                destinations[:5],
                [
                    "route-data-v1.json",
                    "profile-limits-v1.toml",
                    "profile-policy-v1.toml",
                    "damage-policy-v1.toml",
                    "m2-r3-owner-promotion-v1.toml",
                ],
            )
            self.assertEqual(
                initial,
                {
                    path.name: path.read_bytes()
                    for path in (root / "spec").iterdir()
                },
            )
            promotion = tomllib.loads(
                (root / "spec/m2-r3-owner-promotion-v1.toml").read_text()
            )
            self.assertEqual(promotion["status"], "blocked")
            self.assertFalse(promotion["damage_observation_authorized"])

    def test_rs_owner_corpus_schema_generator_and_field_are_exact(self) -> None:
        fixture = self.rs_fixture
        self.assertEqual(
            set(fixture),
            {
                "decode_kats",
                "encode_kats",
                "field_inverse_kats",
                "field_multiplication_kats",
                "generator_coefficients_hex",
                "generator_sha256",
                "intermediate_kat",
                "mutant_ids",
                "profile_id",
                "schema",
            },
        )
        self.assertEqual(
            (fixture["schema"], fixture["profile_id"]),
            ("golden-board.rs255-191-v0-fixtures/v0", "rs255-191-v0"),
        )
        self.assertEqual(
            sha256(self.rs_fixture_raw).hexdigest(),
            "d4dcc0cc441f42c66dc19d6db636733fc577751baf073dc7f951cd3c3dd23f72",
        )
        generator = _rs_generator()
        self.assertEqual(len(generator), 65)
        self.assertEqual(
            generator, bytes.fromhex(fixture["generator_coefficients_hex"])
        )
        self.assertEqual(sha256(generator).hexdigest(), fixture["generator_sha256"])
        profile_document = tomllib.loads(self.profile_raw.decode("utf-8"))
        self.assertEqual(
            profile_document["transport"]["rs255_191"]["generator_coefficients_hex"],
            generator.hex(),
        )
        for row in fixture["field_multiplication_kats"]:
            self.assertEqual(set(row), {"a", "b", "product"})
            self.assertEqual(_gf_mul(row["a"], row["b"]), row["product"])
        for row in fixture["field_inverse_kats"]:
            self.assertEqual(set(row), {"a", "inverse"})
            self.assertEqual(_gf_inverse(row["a"]), row["inverse"])
            self.assertEqual(_gf_mul(row["a"], row["inverse"]), 1)

    def test_rs_owner_encode_kats_are_independently_rederived(self) -> None:
        generator = _rs_generator()
        self.assertEqual(len(self.rs_fixture["encode_kats"]), 4)
        self.assertEqual(
            [row["id"] for row in self.rs_fixture["encode_kats"]],
            [
                "all-zero",
                "last-byte-one",
                "ascending-00-through-be",
                "nonpalindromic-affine-73-41",
            ],
        )
        for row in self.rs_fixture["encode_kats"]:
            self.assertEqual(
                set(row), {"codeword_hex", "codeword_sha256", "data_hex", "id"}
            )
            data = bytes.fromhex(row["data_hex"])
            expected = bytes.fromhex(row["codeword_hex"])
            self.assertEqual((len(data), len(expected)), (191, 255))
            self.assertEqual(_rs_encode(data, generator), expected, row["id"])
            self.assertEqual(sha256(expected).hexdigest(), row["codeword_sha256"])
            self.assertEqual(_rs_syndromes(expected), [0] * 64)

    def test_rs_owner_decoder_statuses_hashes_and_boundaries_are_exact(self) -> None:
        codewords = {
            row["id"]: bytes.fromhex(row["codeword_hex"])
            for row in self.rs_fixture["encode_kats"]
        }
        expected_ids = [
            "single-data-first",
            "single-data-last",
            "single-parity-first",
            "single-parity-last",
            "e0-s64",
            "e1-s62",
            "e16-s32",
            "e31-s2",
            "e32-s0",
            "e1-s63",
            "e16-s33",
            "e32-s1",
            "e33-s0",
            "e0-s65",
        ]
        self.assertEqual(
            [row["id"] for row in self.rs_fixture["decode_kats"]], expected_ids
        )
        for row in self.rs_fixture["decode_kats"]:
            self.assertEqual(
                set(row),
                {
                    "erasure_positions",
                    "expected_codeword_id",
                    "expected_correction_magnitudes",
                    "expected_correction_positions",
                    "expected_status",
                    "id",
                    "observation_hex",
                    "observation_sha256",
                },
            )
            observation = bytes.fromhex(row["observation_hex"])
            self.assertEqual(len(observation), 255)
            self.assertEqual(sha256(observation).hexdigest(), row["observation_sha256"])
            status, corrected, trace = _rs_decode_reference(
                observation, row["erasure_positions"]
            )
            self.assertEqual(status, row["expected_status"], row["id"])
            if status == 0:
                self.assertEqual(
                    corrected, codewords[row["expected_codeword_id"]], row["id"]
                )
                self.assertEqual(
                    trace["positions"], row["expected_correction_positions"]
                )
                self.assertEqual(
                    trace["magnitudes"], row["expected_correction_magnitudes"]
                )
            else:
                self.assertIsNone(corrected)
        ascending = codewords["ascending-00-through-be"]
        self.assertEqual(_rs_decode_reference(ascending, [1, 1])[0], 3)
        self.assertEqual(_rs_decode_reference(ascending, [2, 1])[0], 3)
        self.assertEqual(_rs_decode_reference(ascending, [-1])[0], 3)
        self.assertEqual(_rs_decode_reference(ascending, [255])[0], 3)

    def test_rs_owner_intermediate_trace_and_mutant_names_are_exact(self) -> None:
        row = self.rs_fixture["intermediate_kat"]
        self.assertEqual(
            set(row),
            {
                "bm_input_hex",
                "codeword_id",
                "correction_magnitudes",
                "correction_positions",
                "erasure_locator_ascending_hex",
                "erasure_positions",
                "evaluator_ascending_padded_hex",
                "expected_status",
                "full_locator_ascending_hex",
                "id",
                "observation_hex",
                "syndromes_hex",
                "transformed_syndromes_hex",
                "unknown_error_locator_ascending_hex",
            },
        )
        status, corrected, trace = _rs_decode_reference(
            bytes.fromhex(row["observation_hex"]), row["erasure_positions"]
        )
        self.assertEqual(status, row["expected_status"])
        expected = next(
            bytes.fromhex(item["codeword_hex"])
            for item in self.rs_fixture["encode_kats"]
            if item["id"] == row["codeword_id"]
        )
        self.assertEqual(corrected, expected)
        for trace_name, row_name in (
            ("syndromes", "syndromes_hex"),
            ("erasure_locator", "erasure_locator_ascending_hex"),
            ("transformed", "transformed_syndromes_hex"),
            ("bm_input", "bm_input_hex"),
            ("unknown_locator", "unknown_error_locator_ascending_hex"),
            ("locator", "full_locator_ascending_hex"),
            ("evaluator", "evaluator_ascending_padded_hex"),
        ):
            self.assertEqual(trace[trace_name], bytes.fromhex(row[row_name]))
        self.assertEqual(trace["positions"], row["correction_positions"])
        self.assertEqual(trace["magnitudes"], row["correction_magnitudes"])
        self.assertEqual(
            self.rs_fixture["mutant_ids"],
            [
                "field-modulus-0x11b",
                "generator-roots-1-through-64",
                "coefficient-order-ascending-on-wire",
                "parity-before-data",
                "symbol-bits-lsb-first",
                "position-power-alpha-to-p",
                "erasure-transform-not-multiplied",
                "transformed-syndrome-prefix-not-dropped",
                "chien-alpha-to-p",
                "forney-location-factor-omitted",
                "ordinary-derivative",
                "erased-observation-byte-not-zero-filled",
                "correction-applied-before-all-magnitudes",
                "root-count-degree-not-checked",
                "post-syndrome-not-checked",
            ],
        )

    def test_exact_six_profile_set_and_immutable_projection(self) -> None:
        self.assertEqual(
            tuple(item.profile_id for item in self.profile.profiles),
            (
                "eh72-r2-crc32c-v0",
                "eh72-r2-crc64-ecma-v0",
                "eh72-r3-crc32c-v0",
                "eh72-r3-crc64-ecma-v0",
                "rs255-191-crc32c-v0",
                "rs255-191-crc64-ecma-v0",
            ),
        )
        self.assertEqual(
            tuple(item.profile_version for item in self.profile.profiles),
            tuple(range(1, 7)),
        )
        with self.assertRaises(FrozenInstanceError):
            self.profile.side_max = 4096  # type: ignore[misc]
        error = m2_policy.PolicyError("x")
        with self.assertRaises(AttributeError):
            error._reason = "changed"

    def test_capacity_projection_reproduces_frozen_candidate_neutral_envelope(
        self,
    ) -> None:
        policy_document = tomllib.loads(self.profile_raw.decode("utf-8"))
        capacity_path = policy_document["bindings"]["capacity_module_path"]
        self.assertEqual(capacity_path, "python/golden_board/capacity.py")
        self.assertEqual(
            sha256(_read(capacity_path)).hexdigest(),
            policy_document["bindings"]["capacity_module_sha256"],
        )
        envelope = capacity.derive_capacity_envelope(
            self.inputs, self.profile.capacity_policy
        )
        observed = (
            envelope.concept_minima_bytes,
            envelope.assessment_bytes,
            envelope.integrated_bytes,
            envelope.generic_shared_support_bytes,
            envelope.authoring_payload_bytes,
            len(envelope.buckets),
            sum(len(bucket.slots) for bucket in envelope.buckets),
            sum(len(bucket.sections) for bucket in envelope.buckets),
            sum(item.payload_length for item in self.inputs.real_content_sections),
            self.inputs.tier_frames[0].logical_payload_length,
            self.inputs.tier_frames[1].logical_payload_length,
            sum(item.payload_length for item in self.inputs.real_content_sections)
            + sum(item.logical_payload_length for item in self.inputs.tier_frames),
        )
        self.assertEqual(observed, self.profile.expected_capacity)
        self.assertEqual(
            envelope.slot_count_by_kind,
            (408, 31, 475, 404, 31, 404, 404, 408, 11, 475, 495, 131, 495, 2),
        )

    def test_damage_seed_set_is_exact_partitioned_and_not_outcome_derived(self) -> None:
        seeds = self.damage.d3_seeds
        self.assertEqual(len(seeds), 128)
        self.assertEqual(seeds[0], 0x47424D3200000000)
        self.assertEqual(seeds[-1], 0x47424D320000007F)
        self.assertEqual(
            tuple(seeds[index * 32] for index in range(4)),
            (
                0x47424D3200000000,
                0x47424D3200000020,
                0x47424D3200000040,
                0x47424D3200000060,
            ),
        )

    def test_damage_transform_ids_are_exactly_the_bootstrap_coordinate_views(
        self,
    ) -> None:
        expected_formulas = (
            ("r", "c"),
            ("side_minus_1_minus_c", "r"),
            ("side_minus_1_minus_r", "side_minus_1_minus_c"),
            ("c", "side_minus_1_minus_r"),
            ("r", "side_minus_1_minus_c"),
            ("side_minus_1_minus_c", "side_minus_1_minus_r"),
            ("side_minus_1_minus_r", "c"),
            ("c", "r"),
        )
        self.assertEqual(self.damage.transform_formulas, expected_formulas)

    def test_obs_units_resource_metrics_bind_recipient_manifestations(self) -> None:
        self.assertEqual(
            self.damage.obs_units_resource_profiles,
            (
                (
                    1,
                    "eh72-r2-crc32c-v0",
                    "f030732cd966fd9570149f6fd2d1befb5eed66319eb248b609693e868f977941",
                    80_435,
                    4_613,
                ),
                (
                    2,
                    "eh72-r2-crc64-ecma-v0",
                    "cce1758613d7f10278533409e07103ae15162972fcf30030e17c233e39664011",
                    80_435,
                    4_613,
                ),
                (
                    3,
                    "eh72-r3-crc32c-v0",
                    "8c91ba74f9bbed97aed89191e8d8d30a9a0c4d32bd5ac98b63a4c19ed71fb0e7",
                    80_435,
                    4_613,
                ),
                (
                    4,
                    "eh72-r3-crc64-ecma-v0",
                    "de237fcd9d53581710404bd8b00152cb68f50adef48e715fdd4572e786bae4b8",
                    80_435,
                    4_613,
                ),
                (
                    5,
                    "rs255-191-crc32c-v0",
                    "2dd94f23f63bd4fbeb8d56565a9cc9a7e0a2054d3483e364cfb60e7751058e91",
                    1_698_049,
                    7_688,
                ),
                (
                    6,
                    "rs255-191-crc64-ecma-v0",
                    "1c05a1f57394d292487f46561492619358fe2d12e42e3a20194d5917f351e555",
                    1_698_049,
                    7_688,
                ),
            ),
        )

    def test_full_set_limit_union_is_exactly_regenerated(self) -> None:
        rendered = m2_policy.render_profile_limits(
            self.profile, self.damage, self.inputs
        )
        self.assertEqual(rendered, self.limits_raw)
        parsed = m2_policy.load_profile_limits(
            self.limits_raw, self.profile, self.damage, self.inputs
        )
        self.assertEqual(
            parsed["profile_ids"], [item.profile_id for item in self.profile.profiles]
        )
        self.assertEqual(parsed["damage"]["cases"], 12_968)
        self.assertEqual(parsed["profile"][-1]["damage_cases"], 11_145)
        self.assertEqual(parsed["bootstrap"]["inventory_entries"], 818)
        self.assertEqual(parsed["semantic_capacity"]["reserve_payload_bytes"], 7_141)

    def test_exact_owner_identity_caps_and_limits_drift_fail_closed(self) -> None:
        for loader, raw in (
            (m2_policy.load_profile_policy, self.profile_raw),
            (m2_policy.load_damage_policy, self.damage_raw),
        ):
            mutation = bytearray(raw)
            mutation[len(mutation) // 2] ^= 1
            with self.assertRaises(m2_policy.PolicyError) as caught:
                loader(bytes(mutation))
            self.assertEqual(caught.exception.reason, "owner-identity")
            with self.assertRaises(m2_policy.PolicyError) as caught:
                loader(raw + b"#" * (65_537 - len(raw)))
            self.assertEqual(caught.exception.reason, "byte-limit")
        mutation = self.limits_raw.replace(b"cases = 12968", b"cases = 12969", 1)
        with self.assertRaises(m2_policy.PolicyError) as caught:
            m2_policy.load_profile_limits(
                mutation, self.profile, self.damage, self.inputs
            )
        self.assertEqual(caught.exception.reason, "limits-drift")


if __name__ == "__main__":
    unittest.main()
