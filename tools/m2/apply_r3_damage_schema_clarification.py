#!/usr/bin/env python3
"""Dry-run or atomically apply the R3 damage-artifact schema refreeze."""

from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import sys


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
    m2_route_data,
    m2_slice,
)


class DamageSchemaToolError(ValueError):
    pass


def _read(relative: str, maximum: int = 1_048_576) -> bytes:
    path = ROOT / relative
    if path.is_symlink() or not path.is_file():
        raise DamageSchemaToolError(f"input:{relative}")
    raw = path.read_bytes()
    if not 1 <= len(raw) <= maximum:
        raise DamageSchemaToolError(f"input-size:{relative}")
    return raw


def _route_receipt(
    implementation_id: str,
    projection: m2_route_data.R3RouteOwnerProjection,
) -> bytes:
    value = canonical_manifest.validate_canonical_manifest(
        projection.reproduction_projection
    )
    return canonical_manifest.serialize_manifest(
        {
            "implementation_id": implementation_id,
            "recipient_package_sha256": value["recipient_package_sha256"],
            "reproduction_projection_sha256": sha256(
                projection.reproduction_projection
            ).hexdigest(),
            "route_data_template_sha256": value[
                "route_data_template_sha256"
            ],
            "route_sha256": value["route_sha256"],
            "schema": "golden-board.m2-r3-route-reproduction/v1",
        }
    )


def build_damage_schema_projection() -> tuple[
    m2_policy.R3PromotionWriteBundle,
    bytes,
    bytes,
    bytes,
    bytes,
    bytes,
    bytes,
    dict[str, bytes],
]:
    """Independently derive every Python byte consumed by the atomic gate."""

    base_profile_raw = _read("spec/profile-policy-v0.toml")
    base_limits_raw = _read("spec/profile-limits-v0.toml")
    profile_raw = _read("spec/profile-policy-v1.toml")
    damage_raw = _read("spec/damage-policy-v1.toml")
    bootstrap_raw = _read("spec/bootstrap-v1.md")
    tracked_route_raw = _read("spec/route-data-v1.json")
    owner_fixture_raw = _read("conformance/m2-r3-owner-v1.json")
    capacity_module_raw = _read("python/golden_board/capacity.py")
    compiled = m2_slice.compile_slice_v0(
        _read("studies/m2/slice-v0.json"),
        _read("conformance/content-v0.json"),
        _read("conformance/chess-v0.json"),
        _read("reports/game-set-v0.bin", 16_777_216),
        _read("spec/content-v0.md"),
        _read("spec/constants-v0.toml"),
        _read("spec/curriculum-v0.toml"),
    )
    blueprint = curriculum.load_blueprint(_read("spec/curriculum-v0.toml"))
    inputs = capacity.derive_capacity_inputs(compiled, blueprint)
    base_policy = m2_policy.load_profile_policy(base_profile_raw)
    envelope = capacity.derive_capacity_envelope(
        inputs, base_policy.capacity_policy
    )
    package = m2_recipe.build_r3_recipe_package()
    candidate_profile = m2_codec.r3_candidate_profile(
        protected_units=1_841,
        encoded_transport_bytes=397_656,
    )
    semantic = canonical_manifest.validate_canonical_manifest(
        m2_carrier.render_semantic_envelope(compiled, inputs, envelope)
    )
    capacity_projection = m2_carrier.derive_r3_capacity_projection(
        candidate_profile, 2_040, 128, inputs, semantic
    )
    route_candidate = m2_route_data.CandidateRouteData(
        candidate_profile.profile_id,
        candidate_profile.profile_version,
        candidate_profile.transport_id,
        candidate_profile.section_check_id,
        (package,),
    )
    projection = m2_route_data.build_r3_route_owner_projection(
        owner_fixture_raw, route_candidate, capacity_projection
    )
    python_route_receipt = _route_receipt("python", projection)
    rust_route_receipt = _route_receipt("rust", projection)
    route_raw = m2_route_data.render_r3_route_data_owner(
        projection, python_route_receipt, rust_route_receipt
    )
    if route_raw != tracked_route_raw:
        raise DamageSchemaToolError("route-drift")
    limits_raw = m2_policy.render_r3_profile_limits(
        profile_raw,
        damage_raw,
        bootstrap_raw,
        route_raw,
        package,
        capacity_module_raw,
        base_profile_raw,
        base_limits_raw,
        inputs,
    )
    python_limits_receipt = m2_policy.render_r3_limits_reproduction_receipt(
        "python", limits_raw, route_raw
    )
    rust_limits_receipt = m2_policy.render_r3_limits_reproduction_receipt(
        "rust", limits_raw, route_raw
    )
    m2_policy.validate_r3_pre_clarification_archive(ROOT, damage_raw)
    archived = m2_policy.validate_r3_pre_damage_schema_archive(
        ROOT, damage_raw
    )
    promotion_raw = m2_policy.render_r3_damage_schema_clarification_manifest(
        archived["owners/m2-r3-owner-promotion-v1.toml"],
        bootstrap_raw,
        profile_raw,
        damage_raw,
        owner_fixture_raw,
        route_raw,
        limits_raw,
        python_route_receipt,
        rust_route_receipt,
        python_limits_receipt,
        rust_limits_receipt,
    )
    bundle = m2_policy.R3PromotionWriteBundle(
        profile_raw,
        damage_raw,
        route_raw,
        limits_raw,
        promotion_raw,
    )
    comparison_files = {
        "damage-policy-v1.projected.toml": damage_raw,
        "m2-r3-owner-promotion-v1.projected.toml": promotion_raw,
        "profile-limits-v1.toml": limits_raw,
        "profile-policy-v1.projected.toml": profile_raw,
        "recipient-package-v7.bin": package,
        "route-data-v1.json": route_raw,
        "route-data-v1.template.json": projection.route_data_template,
        "route-malformed-corpus.json": projection.malformed_corpus,
        "route-prefix-sector-0.bin": projection.route_prefixes[0],
        "route-prefix-sector-1.bin": projection.route_prefixes[1],
        "route-prefix-sector-2.bin": projection.route_prefixes[2],
        "route-prefix-sector-3.bin": projection.route_prefixes[3],
        "route-prefixes.bin": b"".join(projection.route_prefixes),
        "route-reproduction-projection.json": (
            projection.reproduction_projection
        ),
    }
    return (
        bundle,
        bootstrap_raw,
        owner_fixture_raw,
        python_route_receipt,
        rust_route_receipt,
        python_limits_receipt,
        rust_limits_receipt,
        comparison_files,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rust-stage",
        required=True,
        type=Path,
        help="exact independently emitted Rust damage-schema stage",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="atomically write the three refrozen owners; default is dry-run",
    )
    arguments = parser.parse_args()
    (
        bundle,
        bootstrap_raw,
        fixture_raw,
        python_route_receipt,
        rust_route_receipt,
        python_limits_receipt,
        rust_limits_receipt,
        comparison_files,
    ) = build_damage_schema_projection()
    result = m2_policy.apply_r3_damage_schema_clarification_bundle(
        ROOT,
        bundle,
        bootstrap_raw,
        fixture_raw,
        python_route_receipt,
        rust_route_receipt,
        python_limits_receipt,
        rust_limits_receipt,
        arguments.rust_stage,
        comparison_files,
        dry_run=not arguments.apply,
    )
    print(f"m2 R3 damage-schema clarification: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
