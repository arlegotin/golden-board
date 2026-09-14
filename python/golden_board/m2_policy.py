"""Closed pre-result M2 policy loaders and union-limit renderer.

This module has no codec or damage-outcome implementation.  It accepts only the
reviewed v0 owner bytes, projects capacity policy into the candidate-neutral P3
engine, and independently derives the tracked full-candidate-set limit union.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import tempfile
import tomllib

from . import bootstrap, canonical_manifest, capacity


__all__ = (
    "DamagePolicy",
    "PolicyError",
    "ProfilePolicy",
    "ProfileTuple",
    "R3DecoderPolicy",
    "R3PromotedOwnerSet",
    "R3PromotionWriteBundle",
    "apply_r3_mapping_clarification_bundle",
    "apply_r3_damage_schema_clarification_bundle",
    "apply_r3_gate6_convergence_clarification_bundle",
    "apply_r3_independence_witness_clarification_bundle",
    "apply_r3_promotion_bundle",
    "load_damage_policy",
    "load_profile_limits",
    "load_profile_policy",
    "load_r3_decoder_policy",
    "load_r3_promoted_owner_set",
    "render_r3_promoted_damage_policy",
    "render_r3_promoted_profile_policy",
    "render_r3_limits_reproduction_receipt",
    "render_r3_mapping_clarification_manifest",
    "render_r3_damage_schema_clarification_manifest",
    "render_r3_gate6_convergence_clarification_manifest",
    "render_r3_independence_witness_clarification_manifest",
    "render_r3_promotion_manifest",
    "render_r3_profile_limits",
    "validate_r3_rust_stage",
    "validate_r3_pre_clarification_archive",
    "validate_r3_pre_damage_schema_archive",
    "validate_r3_pre_gate6_convergence_archive",
    "validate_r3_pre_independence_witness_archive",
    "render_profile_limits",
)


_POLICY_BYTE_MAX = 65_536
_PROFILE_SHA256 = "c180c2ad312c21e7559a33d9d6aee7ae5ecdc287e94197061242985c57b02265"
_DAMAGE_SHA256 = "9cbb185dd5d7d3fec1d4ce4aa978fa77d92e7a4ef272c2f038f0ada769c376e4"
_BOOTSTRAP_SHA256 = "82c25776871ac48184d5a7f15663bcc1d192618d66df72ff5fbf3a252aa564c2"
_CAPACITY_SHA256 = "9c70306eaed963c682652b5b61b4cf8136e5652bbaf995cc49a4e1edd12a407d"
_SLICE_SEMANTIC_SHA256 = "de7e22f0aa4316d9f32d9435287dd19bd6c04519aae1dc9bd816613f26929671"
_RECIPE_FIXTURE_SHA256 = "50862edb1d0c9654e5c903735f86b41c7ca2958a1e36cffb70a7622ee9a20845"
_RS_FIXTURE_SHA256 = "d4dcc0cc441f42c66dc19d6db636733fc577751baf073dc7f951cd3c3dd23f72"
_PROFILE_LIMITS_V0_SHA256 = (
    "2047141ec25acc71ba45d39e803203b627d4b1c1823c147b4da361da1b189693"
)
_R3_PROMOTION_V1_SHA256 = (
    "8c30ae216f5a3fd8ee13f2821d38412afa6c50303c9140cbe54da8610df9cd8d"
)
_R3_RUST_STAGE_MANIFEST_SHA256 = (
    "e4af2341e63dfccd87ae879468b76a854b209807dc060c833d71c04f195ec29b"
)
_R3_CLARIFICATION_RUST_STAGE_MANIFEST_SHA256 = (
    "9ab2d2928738c4bc8a3384e1a8181b7b23c00ef5e36e203a97a946f30b6603c4"
)
_R3_DAMAGE_SCHEMA_RUST_STAGE_MANIFEST_SHA256 = (
    "5f0b62d9f39fbcbfecd13ccd4fb7dc830e0619db6de5d34bec5de5040430e225"
)
_R3_INDEPENDENCE_WITNESS_RUST_STAGE_MANIFEST_SHA256 = (
    "708bcff8f3df0126016dc4bf83801542055bd2861040c8beb678d7f0ea33a411"
)
_R3_GATE6_CONVERGENCE_RUST_STAGE_MANIFEST_SHA256 = (
    "9fda506c34382a1420ad94ef7b04641e835f9a9641852e3471546d83e40a505c"
)
_R3_PROFILE_V1_SHA256 = (
    "44215d993e3fdfdd1630c404f1ee969e8abc6e4928fda83365fc6940e5cfd412"
)
_R3_DAMAGE_V1_SHA256 = (
    "b3b28f00d3ba04addbed4517eb1abb4ecd02796176eaaecdbc1d47f1f39509df"
)
_R3_PROFILE_LIMITS_V1_SHA256 = (
    "32c2bd0cb978eb800bed7f8ac1c7db223b593b4cf3bad951a9ce4cdc3a568902"
)
_R3_ROUTE_V1_SHA256 = (
    "94df79d9a3fb01b69014417683a0f48f2222fea9fe991361bc99aa0c30dc663e"
)
_R3_PRE_CLARIFICATION_DAMAGE_V1_SHA256 = (
    "e5fb1eb7ffbe82ac9a422d84542c9c8dc2cfbcaf7bbd105471d986435bfe104c"
)
_R3_PRE_CLARIFICATION_LIMITS_V1_SHA256 = (
    "4be5f03700b924195b14cf3e832ae0ffc477c7b74fe10450ec6a7eae28210ebf"
)
_R3_PRE_CLARIFICATION_PROMOTION_V1_SHA256 = (
    "37c81359e172afcf61efd359cd9abace8fe61607ebff8d4d9cb4859c9a3fd1e3"
)
_R3_PRE_CLARIFICATION_PYTHON_LIMITS_RECEIPT_SHA256 = (
    "1928b469e0636e308ede38735ffcf1dbd229cca0940efb4246c1b3ffeb1fe4ca"
)
_R3_PRE_CLARIFICATION_RUST_LIMITS_RECEIPT_SHA256 = (
    "6555165e9136d217c4bc8624309977605fe8c43686261c490f543a0bb5c3e1c6"
)
_R3_PRE_CLARIFICATION_ARCHIVE_MANIFEST_SHA256 = (
    "dd447e4d45cd1fec06261af604d40e5c2d4aeb92e6af04334f5f57ecc74b8f6d"
)
_R3_MAPPING_CLARIFIED_DAMAGE_V1_SHA256 = (
    "cbe82b203c6c735c70d30eebcf8005dcabf46c60332d1726d7ef1d00c12dcb3f"
)
_R3_MAPPING_CLARIFIED_LIMITS_V1_SHA256 = (
    "54c62adfbee30bb84d9b4029059134db81c8e5794cd11c7c716b9b15ae1749e7"
)
_R3_MAPPING_CLARIFIED_PROMOTION_V1_SHA256 = (
    "82f4e9feedb95c5f5554e3bb219587d726996985276bdc51def099495901a57b"
)
_R3_MAPPING_CLARIFIED_PYTHON_LIMITS_RECEIPT_SHA256 = (
    "5397497da30d61acf3e13b1d185dac93a37aef68ad81ee1ff8d0b2370af8498d"
)
_R3_MAPPING_CLARIFIED_RUST_LIMITS_RECEIPT_SHA256 = (
    "db573ed9df5d7405704e2abf54e6c09460543c65513c97846cc346cb6ad01722"
)
_R3_PRE_DAMAGE_SCHEMA_ARCHIVE_MANIFEST_SHA256 = (
    "b55263aac1caa5534ff1276ffe8c5a0ca483a63f8f3f3bf1c573f03622c906d7"
)
_R3_DAMAGE_SCHEMA_CLARIFIED_DAMAGE_V1_SHA256 = (
    "337810fe852443d43d06f6563bd25d00498d2bce727fb9558069c9a1ab1e8f6f"
)
_R3_DAMAGE_SCHEMA_CLARIFIED_LIMITS_V1_SHA256 = (
    "6d9ce190fd510dc95c2a49fb371d7b22174771d798f14788d270e3d42b041691"
)
_R3_DAMAGE_SCHEMA_CLARIFIED_PROMOTION_V1_SHA256 = (
    "3e0893b8376c2fae2140c9349e7b5b302ee87de443cd4e497dbfba19b2b6adc9"
)
_R3_DAMAGE_SCHEMA_CLARIFIED_PYTHON_LIMITS_RECEIPT_SHA256 = (
    "275f35adb5b62bd799f23ddbbaec3f36e0c6f6cb39c18662012ffe155ca2e0c8"
)
_R3_DAMAGE_SCHEMA_CLARIFIED_RUST_LIMITS_RECEIPT_SHA256 = (
    "7dfe55fe169e1f176eff726602678c1596b4822357dfa1c470306b9c223b81c1"
)
_R3_PRE_INDEPENDENCE_WITNESS_ARCHIVE_MANIFEST_SHA256 = (
    "661141dfe15be4597aee24edbbb01b080383aabcfe75646b4a97454758915203"
)
_R3_PRE_GATE6_CONVERGENCE_ARCHIVE_MANIFEST_SHA256 = (
    "d1ece9d02628a624d58837b9a1c1994dfb521e96303df66758c95880b2d378e4"
)
_R3_PRE_GATE6_CONVERGENCE_DAMAGE_V1_SHA256 = (
    "ccd494ff608b68ad7bce09a4fb79e4f49846de595364de8ca209ff558fbc81ed"
)
_R3_PRE_GATE6_CONVERGENCE_LIMITS_V1_SHA256 = (
    "6320464174b2f411d41e125cff4a875a1f337a31157dac6e2f429f1aa57b2a0d"
)
_R3_PRE_GATE6_CONVERGENCE_PROMOTION_V1_SHA256 = (
    "ec24331ed85ff92589c00f3bdadfa6368bd6461da067b64d38c297525c2f3ca1"
)
_R3_PRE_GATE6_CONVERGENCE_PYTHON_LIMITS_RECEIPT_SHA256 = (
    "1e71b339bbe1658f3bba6259f71f4dbdeb0023c4ab723bc16ac4d16063125b6f"
)
_R3_PRE_GATE6_CONVERGENCE_RUST_LIMITS_RECEIPT_SHA256 = (
    "1e2f2f45b9042e5bb36186bbd0c3ba2e8f3b21b4619d64527fe5464be6b4649d"
)
_R3_PYTHON_LIMITS_RECEIPT_SHA256 = (
    "08c030afabe1291b3fa0b20a27666e480a242801fc1978f27992a161cf50b883"
)
_R3_RUST_LIMITS_RECEIPT_SHA256 = (
    "d52a1e9770438e53354599ca899ec0aad328c46739b42d27dec048ec9977750b"
)
_R3_BLOCKED_PROFILE_V1_SHA256 = (
    "f9b3a24c09fceb345bcf9644c75cd6b86f44d6d428d83a5267eab6167825f7d6"
)
_R3_BLOCKED_DAMAGE_V1_SHA256 = (
    "a1cbf2644d26b3e0ba284dbc093a26f77d9fe9baeb461f69707de4f8abe8042e"
)
_R3_BLOCKED_PROMOTION_V1_SHA256 = (
    "57b6fa75507d5406e82a5dd26d8f8542300052a6c330e6cffe33a3865c5be9a3"
)
_R3_BLOCKED_BOOTSTRAP_BINDING_SHA256 = (
    "e4d0a5667758a753d35603632dee550db7ecb66cf64ee675ce7485531da27dde"
)
_R3_BLOCKED_PROFILE_BINDING_SHA256 = (
    "f9b3a24c09fceb345bcf9644c75cd6b86f44d6d428d83a5267eab6167825f7d6"
)
_R3_BLOCKED_DAMAGE_BINDING_SHA256 = (
    "a1cbf2644d26b3e0ba284dbc093a26f77d9fe9baeb461f69707de4f8abe8042e"
)
_ROLE_IDS = (
    "grounded_rule",
    "contrasting_worked",
    "active_prediction_feedback",
    "distinct_held_out",
    "passive_trace",
    "heuristic",
    "assessment_item",
    "integrated_item",
)
_OBS_UNITS_RESOURCE_PROFILES = (
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
)
_OBS_UNITS_RESOURCE_SOURCE = (
    "exact-recipe-30-derived-metrics-of-the-pre-damage-canonical-recipient-"
    "manifestation-package-bound-by-recipient-package-sha256-not-an-independent-"
    "standalone-helper-package"
)
_OBS_UNITS_RESOURCE_CHARGE = (
    "for-each-logically-tried-profile-and-observed-input-id-pair-charge-the-"
    "matching-row-even-when-package-construction-or-transport-evaluation-is-cached"
)


class PolicyError(ValueError):
    __slots__ = ("_reason",)

    def __init__(self, reason: str) -> None:
        self._reason = reason
        super().__init__(reason)

    @property
    def reason(self) -> str:
        return self._reason

    def __setattr__(self, name: str, value: object) -> None:
        if name == "_reason" and hasattr(self, name):
            raise AttributeError("reason is read-only")
        super().__setattr__(name, value)


@dataclass(frozen=True, slots=True)
class ProfileTuple:
    profile_id: str
    profile_version: int
    transport_id: str
    check_bytes: int
    required_copy_count: int
    protected_unit_bytes: int
    complexity_class: int


@dataclass(frozen=True, slots=True)
class ProfilePolicy:
    sha256: str
    profiles: tuple[ProfileTuple, ...]
    capacity_policy: capacity.CapacityPolicyInput
    raw_bits_max: int
    side_max: int
    shell_width_min: int
    shell_width_max: int
    section_payload_max: int
    dependency_max: int
    inventory_entry_max: int
    section_attempt_max: int
    common_block_bytes: int
    fragment_payload_bytes: int
    content_stream_max: int
    recipe_package_max: int
    recipe_count_max: int
    recipe_table_max: int
    recipe_table_bytes_max: int
    recipe_node_max: int
    recipe_edge_max: int
    recipe_iteration_max: int
    recipe_steps_max: int
    recipe_scratch_max: int
    expected_capacity: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class DamagePolicy:
    sha256: str
    transform_formulas: tuple[tuple[str, str], ...]
    d2_placements: int
    d3_seed_first: int
    d3_seed_count: int
    d3_seed_step: int
    d5_permutations: int
    d5_seed_count: int
    d7_common_excluding_code_algebra: int
    d7_eh_code: int
    d7_eh_algebra: int
    d7_rs_code: int
    d7_rs_algebra: int
    obs_units_resource_profiles: tuple[tuple[int, str, str, int, int], ...]

    @property
    def d3_seeds(self) -> tuple[int, ...]:
        return tuple(
            self.d3_seed_first + index * self.d3_seed_step
            for index in range(self.d3_seed_count)
        )


@dataclass(frozen=True, slots=True)
class R3DecoderPolicy:
    """Exact candidate-neutral projection admitted by the v1 decoder."""

    profile_policy_sha256: str
    damage_policy_sha256: str
    profile_limits_sha256: str
    registry_profiles: tuple[ProfileTuple, ...]
    protected_units: int
    encoded_transport_bytes: int
    obs_units_resource_profiles: tuple[
        tuple[int, str, str, int, int], ...
    ]
    repetition_primitive_steps: int
    repetition_peak_scratch_bytes: int


@dataclass(frozen=True, slots=True)
class R3PromotedOwnerSet:
    bootstrap_sha256: str
    profile_policy_sha256: str
    damage_policy_sha256: str
    route_data_sha256: str
    profile_limits_sha256: str
    promotion_sha256: str


@dataclass(frozen=True, slots=True)
class R3PromotionWriteBundle:
    profile_policy: bytes
    damage_policy: bytes
    route_data: bytes
    profile_limits: bytes
    promotion_manifest: bytes


def _document(raw: bytes, expected_sha256: str, schema: str) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= _POLICY_BYTE_MAX:
        raise PolicyError("byte-limit")
    if sha256(raw).hexdigest() != expected_sha256:
        raise PolicyError("owner-identity")
    try:
        value = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise PolicyError("toml") from error
    if type(value) is not dict or value.get("schema") != schema:
        raise PolicyError("schema")
    return value


def _integer(table: dict, key: str, minimum: int = 0) -> int:
    value = table.get(key)
    if type(value) is not int or value < minimum:
        raise PolicyError(f"field:{key}")
    return value


def load_profile_policy(raw: bytes) -> ProfilePolicy:
    data = _document(raw, _PROFILE_SHA256, "golden-board.profile-policy/v0")
    candidate_set = data["candidate_set"]
    profile_rows = data["profile"]
    profile_ids = tuple(candidate_set["profile_ids"])
    if (
        candidate_set["transport_family_ids"]
        != ["eh72-replicated-v0", "rs255-191-v0"]
        or candidate_set["section_check_ids"]
        != ["crc32c-v0", "crc64-ecma-v0"]
        or type(profile_rows) is not list
        or len(profile_rows) != 6
        or tuple(row["id"] for row in profile_rows) != profile_ids
        or tuple(row["profile_version"] for row in profile_rows) != tuple(range(1, 7))
    ):
        raise PolicyError("candidate-set")
    check_width = {"crc32c-v0": 4, "crc64-ecma-v0": 8}
    unit_width = {"eh72-replicated-v0": 216, "rs255-191-v0": 255}
    profiles = tuple(
        ProfileTuple(
            row["id"],
            row["profile_version"],
            row["transport_id"],
            check_width[row["section_check_id"]],
            row["required_copy_count"],
            unit_width[row["transport_id"]],
            row["complexity_class"],
        )
        for row in profile_rows
    )
    role_rows = data["capacity"]["role_bundle"]
    if tuple(row["id"] for row in role_rows) != _ROLE_IDS:
        raise PolicyError("role-order")
    role_bundles = []
    for row in role_rows:
        values = row["kind_multiplicity"]
        if (
            type(values) is not list
            or len(values) != 14
            or any(type(item) is not int or not 0 <= item <= 4096 for item in values)
            or sum(values) == 0
        ):
            raise PolicyError("role-shape")
        role_bundles.append(capacity.RoleBundlePolicy(row["id"], tuple(values)))
    capacity_table = data["capacity"]
    capacity_policy = capacity.CapacityPolicyInput(
        tuple(role_bundles),
        _integer(capacity_table, "maximum_content_body_payload", 1),
        _integer(capacity_table, "maximum_probe_payload", 1),
        _integer(capacity_table, "generic_support_fraction_numerator", 1),
        _integer(capacity_table, "generic_support_fraction_denominator", 1),
        _integer(capacity_table, "generic_support_minimum_cycles", 1),
    )
    expected = capacity_table["expected_envelope"]
    expected_capacity = (
        _integer(expected, "concept_minima_bytes"),
        _integer(expected, "assessment_bytes"),
        _integer(expected, "integrated_bytes"),
        _integer(expected, "generic_shared_support_bytes"),
        _integer(expected, "authoring_payload_bytes"),
        _integer(expected, "bucket_count"),
        _integer(expected, "slot_count"),
        _integer(expected, "section_count"),
        _integer(expected, "real_content_body_payload_bytes"),
        _integer(expected, "required_tier_frame_payload_bytes"),
        _integer(expected, "all_tier_frame_payload_bytes"),
        _integer(expected, "real_slice_payload_excluding_inventory"),
    )
    resource = data["resource_policy"]
    geometry = data["geometry"]
    recipe = resource
    result = ProfilePolicy(
        _PROFILE_SHA256,
        profiles,
        capacity_policy,
        _integer(geometry, "raw_bits_max", 1),
        _integer(geometry, "side_max", 1),
        _integer(geometry, "shell_width_min", 1),
        _integer(geometry, "shell_width_max", 1),
        _integer(resource, "section_payload_bytes_max", 1),
        _integer(resource, "dependency_count_max"),
        _integer(resource, "inventory_entry_count_max", 1),
        _integer(resource, "section_attempt_ceiling", 1),
        _integer(resource, "common_block_bytes", 1),
        _integer(resource, "fragment_payload_bytes", 1),
        _integer(resource, "content_stream_bytes_max", 1),
        _integer(recipe, "recipe_encoded_bytes_max", 1),
        256,
        _integer(recipe, "recipe_tables_max"),
        _integer(recipe, "recipe_table_bytes_max"),
        _integer(recipe, "recipe_nodes_max", 1),
        _integer(recipe, "recipe_edges_max"),
        1_048_576,
        _integer(recipe, "recipe_primitive_steps_max", 1),
        _integer(recipe, "recipe_scratch_bytes_max", 1),
        expected_capacity,
    )
    if (
        data["bindings"]["capacity_module_sha256"] != _CAPACITY_SHA256
        or data["bindings"]["slice_semantic_sha256"] != _SLICE_SEMANTIC_SHA256
        or data["bindings"]["recipe_fixture_sha256"] != _RECIPE_FIXTURE_SHA256
        or data["bindings"]["rs_fixture_sha256"] != _RS_FIXTURE_SHA256
        or result.raw_bits_max != result.side_max * result.side_max
        or result.common_block_bytes != 191
        or result.fragment_payload_bytes != 157
    ):
        raise PolicyError("binding")
    return result


def load_damage_policy(raw: bytes) -> DamagePolicy:
    data = _document(raw, _DAMAGE_SHA256, "golden-board.damage-policy/v0")
    if (
        tuple(row["id"] for row in data["channel"])
        != ("OBS_BITS", "OBS_MATRIX", "OBS_UNITS")
        or tuple(row["id"] for row in data["transform"]) != tuple(range(8))
        or data["polarity"]["ids"] != [0, 1]
        or tuple(data[f"d{index}"]["id"] for index in range(8))
        != tuple(f"D{index}" for index in range(8))
    ):
        raise PolicyError("damage-set")
    d3 = data["d3"]
    strata = d3["stratum"]
    if (
        tuple(row["id"] for row in strata) != (0, 1, 2, 3)
        or _integer(d3, "seed_count", 1) != 128
        or _integer(d3, "stratum_size", 1) != 32
        or data["sampling"]["domain_hex"] != "47422d44414d4147452d763000"
    ):
        raise PolicyError("damage-sampling")
    d5 = data["d5"]
    d7_counts = data["d7"]["case_count"]
    decoder = data["decoder"]
    resource_rows = decoder.get("obs_units_resource_profile")
    expected_resource_rows = _OBS_UNITS_RESOURCE_PROFILES
    row_keys = (
        "profile_version",
        "profile_id",
        "recipient_package_sha256",
        "decoder_30_primitive_steps",
        "decoder_30_peak_scratch_bytes",
    )
    if (
        decoder.get("obs_units_resource_profile_row_keys")
        != list(row_keys)
        or decoder.get("obs_units_resource_profile_order")
        != "profile-version-ascending-exactly-1-through-6"
        or decoder.get("obs_units_resource_metric_source")
        != _OBS_UNITS_RESOURCE_SOURCE
        or decoder.get("obs_units_resource_charge")
        != _OBS_UNITS_RESOURCE_CHARGE
        or type(resource_rows) is not list
        or any(type(row) is not dict or tuple(row) != row_keys for row in resource_rows)
    ):
        raise PolicyError("obs-units-resource-owner")
    observed_resource_rows = tuple(
        (
            _integer(row, "profile_version", 1),
            row.get("profile_id"),
            row.get("recipient_package_sha256"),
            _integer(row, "decoder_30_primitive_steps", 1),
            _integer(row, "decoder_30_peak_scratch_bytes", 1),
        )
        for row in resource_rows
    )
    if observed_resource_rows != expected_resource_rows:
        raise PolicyError("obs-units-resource-rows")
    return DamagePolicy(
        _DAMAGE_SHA256,
        tuple(
            (row["row_formula"], row["column_formula"])
            for row in data["transform"]
        ),
        _integer(data["d2"], "placement_target", 1),
        _integer(d3, "seed_first"),
        _integer(d3, "seed_count", 1),
        _integer(d3, "seed_step", 1),
        len(d5["fixed_permutations"]),
        _integer(d5, "fisher_yates_seed_count"),
        _integer(d7_counts, "common_excluding_code_and_algebra", 1),
        _integer(d7_counts, "eh_code_cases", 1),
        _integer(d7_counts, "eh_algebra_cases", 1),
        _integer(d7_counts, "rs_code_cases", 1),
        _integer(d7_counts, "rs_algebra_cases", 1),
        expected_resource_rows,
    )


def _capacity_projection(
    policy: ProfilePolicy, inputs: capacity.CapacityInputs
) -> tuple[capacity.CapacityEnvelope, tuple[int, ...]]:
    if type(inputs) is not capacity.CapacityInputs:
        raise TypeError("expected CapacityInputs")
    envelope = capacity.derive_capacity_envelope(inputs, policy.capacity_policy)
    observed = (
        envelope.concept_minima_bytes,
        envelope.assessment_bytes,
        envelope.integrated_bytes,
        envelope.generic_shared_support_bytes,
        envelope.authoring_payload_bytes,
        len(envelope.buckets),
        sum(len(bucket.slots) for bucket in envelope.buckets),
        sum(len(bucket.sections) for bucket in envelope.buckets),
        sum(item.payload_length for item in inputs.real_content_sections),
        inputs.tier_frames[0].logical_payload_length,
        inputs.tier_frames[1].logical_payload_length,
        sum(item.payload_length for item in inputs.real_content_sections)
        + sum(item.logical_payload_length for item in inputs.tier_frames),
    )
    if (
        observed != policy.expected_capacity
        or inputs.slice_semantic_sha256 != _SLICE_SEMANTIC_SHA256
        or envelope.slot_count_by_kind
        != (408, 31, 475, 404, 31, 404, 404, 408, 11, 475, 495, 131, 495, 2)
    ):
        raise PolicyError("capacity-drift")
    return envelope, observed


def _limits_values(
    policy: ProfilePolicy,
    damage: DamagePolicy,
    inputs: capacity.CapacityInputs,
) -> tuple[dict, tuple[dict, ...], tuple[int, ...]]:
    envelope, capacity_values = _capacity_projection(policy, inputs)
    raw_bits = policy.raw_bits_max
    inventory_entries = min(
        policy.inventory_entry_max,
        (policy.section_payload_max - 8) // 20,
    )
    envelope_max = (
        18 + 4 * policy.dependency_max + policy.section_payload_max + 8
    )
    fragments = (envelope_max + policy.fragment_payload_bytes - 1) // policy.fragment_payload_bytes
    authoring = envelope.authoring_payload_bytes
    real = capacity_values[11]
    content_before_reserve = real + authoring + policy.section_payload_max
    reserve = max((content_before_reserve + 18) // 19, 2 * policy.common_block_bytes)
    rows = []
    max_units = 0
    max_encoded = 0
    max_damage = 0
    max_obs_units = 0
    for item in policy.profiles:
        unit_bits = item.protected_unit_bytes * 8
        units = raw_bits // unit_bits
        d7 = damage.d7_common_excluding_code_algebra
        if item.transport_id == "eh72-replicated-v0":
            d7 += damage.d7_eh_code + damage.d7_eh_algebra
        else:
            d7 += damage.d7_rs_code + damage.d7_rs_algebra
        cases = 16 + 4 + damage.d2_placements + damage.d3_seed_count + units + (
            damage.d5_permutations + damage.d5_seed_count
        ) + 4 * units + d7
        encoded = units * item.protected_unit_bytes
        obs_units = 4 + units * (6 + item.protected_unit_bytes)
        row = {
            "id": item.profile_id,
            "profile_version": item.profile_version,
            "check_bytes": item.check_bytes,
            "required_copy_count": item.required_copy_count,
            "protected_unit_bytes": item.protected_unit_bytes,
            "protected_units": units,
            "encoded_transport_bytes": encoded,
            "section_envelope_bytes": envelope_max - (8 - item.check_bytes),
            "fragments_per_semantic_copy": fragments,
            "damage_cases": cases,
            "obs_units_bytes": obs_units,
        }
        rows.append(row)
        max_units = max(max_units, units)
        max_encoded = max(max_encoded, encoded)
        max_damage = max(max_damage, cases)
        max_obs_units = max(max_obs_units, obs_units)
    values = {
        "inventory_entries": inventory_entries,
        "envelope_max": envelope_max,
        "fragments": fragments,
        "content_before_reserve": content_before_reserve,
        "reserve": reserve,
        "max_units": max_units,
        "max_encoded": max_encoded,
        "max_damage": max_damage,
        "max_obs_units": max_obs_units,
        "d3_weight": max(64, ((policy.side_max - 2 * policy.shell_width_min) ** 2 + 1999) // 2000),
    }
    return values, tuple(rows), capacity_values


def _toml_value(value: object) -> str:
    if type(value) is str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    if type(value) in (list, tuple):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError("unsupported TOML value")


def _emit_table(lines: list[str], name: str, values: tuple[tuple[str, object], ...]) -> None:
    lines.extend(("", f"[{name}]"))
    lines.extend(f"{key} = {_toml_value(value)}" for key, value in values)


def render_profile_limits(
    profile: ProfilePolicy,
    damage: DamagePolicy,
    inputs: capacity.CapacityInputs,
) -> bytes:
    if type(profile) is not ProfilePolicy or type(damage) is not DamagePolicy:
        raise TypeError("expected loaded M2 policies")
    value, rows, capacity_values = _limits_values(profile, damage, inputs)
    lines = [
        'schema = "golden-board.profile-limits/v0"',
        'generation = "componentwise-union-of-all-six-pre-result-profile-ledgers"',
        f'profile_policy_sha256 = "{profile.sha256}"',
        f'damage_policy_sha256 = "{damage.sha256}"',
        f'bootstrap_spec_sha256 = "{_BOOTSTRAP_SHA256}"',
        f'capacity_module_sha256 = "{_CAPACITY_SHA256}"',
        f'slice_semantic_sha256 = "{_SLICE_SEMANTIC_SHA256}"',
        f"profile_ids = {_toml_value(tuple(item.profile_id for item in profile.profiles))}",
    ]
    _emit_table(lines, "raw", (("bits", profile.raw_bits_max), ("side", profile.side_max), ("cells", profile.raw_bits_max), ("entry_hypotheses", 16), ("shell_sectors", 4), ("shell_width", profile.shell_width_max)))
    _emit_table(lines, "semantic_capacity", (
        ("prototype_kinds", 14), ("curriculum_concepts", 29), ("curriculum_families", 20), ("integrated_tasks", 3),
        ("buckets", capacity_values[5]), ("slots", capacity_values[6]), ("simulated_sections", capacity_values[7]),
        ("authoring_payload_bytes", capacity_values[4]), ("real_content_body_sections", 77),
        ("real_content_body_payload_bytes", capacity_values[8]), ("tier_frame_sections", 2),
        ("tier_frame_payload_bytes", capacity_values[9] + capacity_values[10]),
        ("real_slice_payload_excluding_inventory", capacity_values[11]),
        ("inventory_payload_bytes", profile.section_payload_max),
        ("content_capacity_before_reserve_bytes", value["content_before_reserve"]),
        ("reserve_payload_bytes", value["reserve"]), ("reserve_probe_sections", (value["reserve"] + profile.capacity_policy.maximum_probe_payload - 1) // profile.capacity_policy.maximum_probe_payload),
        ("protected_logical_capacity_bytes", value["content_before_reserve"] + value["reserve"]),
    ))
    _emit_table(lines, "bootstrap", (
        ("common_block_bytes", profile.common_block_bytes), ("common_payload_bytes", profile.fragment_payload_bytes),
        ("common_blocks", value["max_units"]), ("common_plain_bytes", value["max_units"] * profile.common_block_bytes),
        ("section_payload_bytes", profile.section_payload_max), ("section_envelope_bytes", value["envelope_max"]),
        ("fragments_per_semantic_copy", value["fragments"]), ("fragment_observations", value["max_units"]),
        ("semantic_copies_per_section", 3), ("sections", value["inventory_entries"]), ("inventory_entries", value["inventory_entries"]),
        ("dependencies_per_section", profile.dependency_max), ("dependency_edges", value["inventory_entries"] * profile.dependency_max),
        ("section_attempts", profile.section_attempt_max), ("assembled_content_bytes", profile.content_stream_max), ("output_bytes", profile.content_stream_max),
    ))
    _emit_table(lines, "transport", (("profile_tuples", len(profile.profiles)), ("protected_units", value["max_units"]), ("protected_unit_bytes", max(item.protected_unit_bytes for item in profile.profiles)), ("encoded_transport_bytes", value["max_encoded"]), ("eh_codewords_per_unit", 24), ("eh_codeword_candidate_constructions", 144), ("rs_symbols_per_unit", 255), ("rs_erasures_per_unit", 64), ("rs_unknown_errors_per_unit", 32)))
    _emit_table(lines, "recipe", (("package_bytes", profile.recipe_package_max), ("recipes", profile.recipe_count_max), ("tables", profile.recipe_table_max), ("table_payload_bytes", profile.recipe_table_bytes_max), ("nodes", profile.recipe_node_max), ("edges", profile.recipe_edge_max), ("iteration_count", profile.recipe_iteration_max), ("primitive_steps", profile.recipe_steps_max), ("scratch_bytes", profile.recipe_scratch_max), ("route_records", 256), ("route_sector_capacity_formula", "shell_width_times_side_minus_shell_width_div_8"), ("route_sector_capacity_bytes", 30720)))
    _emit_table(lines, "damage", (("cases", value["max_damage"]), ("d2_placements", damage.d2_placements), ("d3_seeds", damage.d3_seed_count), ("d3_substitutions", value["d3_weight"]), ("changed_or_erased_coordinates", profile.raw_bits_max), ("sample_attempts", profile.raw_bits_max * 64 + 1024), ("obs_bits_bytes", 4 + (profile.raw_bits_max + 7) // 8), ("obs_matrix_bytes", 2 + profile.raw_bits_max), ("obs_units_bytes", value["max_obs_units"]), ("wrong_accepts", 0)))
    _emit_table(lines, "content", (("stream_bytes", 1048576), ("records", 65535), ("records_per_non_root_kind", 4096), ("payload_bytes", 1048576), ("text_bytes", 4096), ("enum_entries", 4096), ("vector_atoms", 65535), ("matrix_cells", 65535), ("field_schema_fields", 256), ("tuple_slots", 4096), ("opaque_atoms", 4096), ("regions", 4096), ("lesson_nodes", 4096), ("cases_per_node", 4096), ("control_edges", 16384), ("selections", 4096), ("event_budget", 65535), ("run_state_bytes", 466958)))
    for row in rows:
        lines.extend(("", "[[profile]]"))
        lines.extend(f"{key} = {_toml_value(item)}" for key, item in row.items())
    return ("\n".join(lines) + "\n").encode("utf-8")


def load_profile_limits(
    raw: bytes,
    profile: ProfilePolicy,
    damage: DamagePolicy,
    inputs: capacity.CapacityInputs,
) -> dict:
    expected = render_profile_limits(profile, damage, inputs)
    if type(raw) is not bytes or len(raw) > _POLICY_BYTE_MAX or raw != expected:
        raise PolicyError("limits-drift")
    try:
        parsed = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise PolicyError("limits-toml") from error
    if parsed.get("schema") != "golden-board.profile-limits/v0":
        raise PolicyError("limits-schema")
    return parsed


def _r3_toml_document(raw: bytes, schema: str) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= _POLICY_BYTE_MAX:
        raise PolicyError("r3-byte-limit")
    try:
        value = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise PolicyError("r3-toml") from error
    if type(value) is not dict or value.get("schema") != schema:
        raise PolicyError("r3-schema")
    return value


def _replace_toml_field(
    raw: bytes, section: str | None, key: str, value: object
) -> bytes:
    try:
        text = raw.decode("utf-8")
    except UnicodeError as error:
        raise PolicyError("r3-toml-encoding") from error
    lines = text.splitlines()
    in_section = section is None
    matches = []
    for index, line in enumerate(lines):
        if line.startswith("["):
            in_section = line == f"[{section}]"
            continue
        if in_section and line.startswith(f"{key} = "):
            matches.append(index)
    if len(matches) != 1:
        raise PolicyError(f"r3-field:{section}:{key}")
    lines[matches[0]] = f"{key} = {_toml_value(value)}"
    return ("\n".join(lines) + "\n").encode("utf-8")


def _insert_toml_table_before(
    raw: bytes,
    before_section: str,
    table_name: str,
    values: dict[str, object],
) -> bytes:
    try:
        text = raw.decode("utf-8")
    except UnicodeError as error:
        raise PolicyError("r3-toml-encoding") from error
    marker = f"\n[{before_section}]\n"
    if text.count(marker) != 1 or f"\n[{table_name}]\n" in text:
        raise PolicyError(f"r3-table-insertion:{table_name}")
    return text.replace(marker, f"\n[{table_name}]\n" + "\n".join(
        f"{key} = {_toml_value(value)}" for key, value in values.items()
    ) + f"\n\n[{before_section}]\n").encode("utf-8")


def _r3_complete_route_document(route_data_raw: bytes) -> dict:
    try:
        route = canonical_manifest.validate_canonical_manifest(route_data_raw)
    except canonical_manifest.ManifestError as error:
        raise PolicyError("r3-route-canonical") from error
    generated = route.get("generated")
    if (
        route.get("schema") != "golden-board.route-data/v1"
        or type(generated) is not dict
        or set(generated) != _R3_ROUTE_GENERATED_KEYS
    ):
        raise PolicyError("r3-route-generated")
    return route


def render_r3_promoted_profile_policy(
    draft_raw: bytes,
    bootstrap_spec_raw: bytes,
    route_data_raw: bytes,
) -> bytes:
    """Bind bootstrap/route/package values and insert the exact v1 table."""

    draft = _r3_toml_document(draft_raw, "golden-board.profile-policy/v1")
    if "generated" in draft:
        raise PolicyError("r3-profile-generated-present")
    route = _r3_complete_route_document(route_data_raw)
    generated = route["generated"]
    capacity_projection = generated["capacity_projection"]
    values = {
        "encoded_transport_bytes": capacity_projection["encoded_transport_bytes"],
        "physical_unit_count": capacity_projection["physical_unit_count"],
        "recipient_package_bytes": generated["recipient_package_bytes"],
        "recipient_package_edge_count": generated["recipient_package_edge_count"],
        "recipient_package_node_count": generated["recipient_package_node_count"],
        "recipient_package_peak_scratch_bytes": generated["recipient_package_peak_scratch_bytes"],
        "recipient_package_primitive_steps": generated["recipient_package_primitive_steps"],
        "recipient_package_sha256": generated["recipient_package_sha256"],
        "route_data_path": "spec/route-data-v1.json",
        "route_data_sha256": sha256(route_data_raw).hexdigest(),
        "shell_width": route["shell_width"],
        "side": route["side"],
    }
    owner = draft.get("promotion_generated_schema")
    if type(owner) is not dict or tuple(values) != tuple(owner.get("key_order", ())):
        raise PolicyError("r3-profile-generated-schema")
    bound = _replace_toml_field(
        draft_raw,
        "bindings",
        "bootstrap_sha256",
        sha256(bootstrap_spec_raw).hexdigest(),
    )
    rendered = _insert_toml_table_before(
        bound, "candidate_set", "generated", values
    )
    parsed = _r3_toml_document(rendered, "golden-board.profile-policy/v1")
    if parsed.get("generated") != values:
        raise PolicyError("r3-profile-generated-render")
    return rendered


def render_r3_promoted_damage_policy(
    draft_raw: bytes,
    bootstrap_spec_raw: bytes,
    promoted_profile_policy_raw: bytes,
    route_data_raw: bytes,
) -> bytes:
    """Bind the upstream owners and insert exact pre-result damage values."""

    draft = _r3_toml_document(draft_raw, "golden-board.damage-policy/v1")
    if "generated" in draft:
        raise PolicyError("r3-damage-generated-present")
    _r3_toml_document(
        promoted_profile_policy_raw, "golden-board.profile-policy/v1"
    )
    route = _r3_complete_route_document(route_data_raw)
    generated = route["generated"]
    capacity_projection = generated["capacity_projection"]
    resources = {
        row["recipe_id"]: row for row in generated["recipe_resource_rows"]
    }
    if set(resources) != {30, 109, 110, 113}:
        raise PolicyError("r3-damage-resource")
    physical_units = capacity_projection["physical_unit_count"]
    d0 = len(draft["inherited_exact"]["transform_ids"]) * len(
        draft["inherited_exact"]["polarity_ids"]
    )
    d1 = len(draft["inherited_exact"]["d1_sector_ids"])
    d2 = draft["inherited_exact"]["d2_placement_target"]
    d3 = draft["inherited_exact"]["d3_seed_count"]
    d5 = len(draft["inherited_exact"]["d5_fixed_permutations"]) + draft[
        "inherited_exact"
    ]["d5_fisher_yates_seed_count"]
    d7 = draft["d7"]["case_count"]
    population = capacity_projection["population"]
    interior = capacity_projection["interior_side"]
    side = route["side"]
    damage_cases = d0 + d1 + d2 + d3 + physical_units + d5 + 4 * physical_units + d7
    values = {
        "d2_square_side": max(32, interior // 32),
        "d3_sample_retry_max": 64 * population + 1_024,
        "d3_weight": max(64, (population + 1_999) // 2_000),
        "d3_window_side": max(32, interior // 8),
        "d4_case_count": physical_units,
        "d6_case_count": 4 * physical_units,
        "damage_case_count": damage_cases,
        "obs_units_bytes": 4
        + (physical_units - 5) * (6 + 216)
        + 5 * (6 + 255),
        "physical_unit_count": physical_units,
        "profile_limits_path": "spec/profile-limits-v1.toml",
        "recipient_package_sha256": generated["recipient_package_sha256"],
        "repetition_113_peak_scratch_bytes": resources[113]["peak_scratch_bytes"],
        "repetition_113_primitive_steps": resources[113]["primitive_steps"],
        "route_data_path": "spec/route-data-v1.json",
        "route_data_sha256": sha256(route_data_raw).hexdigest(),
        "route_example_peak_scratch_bytes_by_sector": generated["route_example_peak_scratch_bytes_by_sector"],
        "route_example_primitive_steps_by_sector": generated["route_example_primitive_steps_by_sector"],
        "route_static_reject_primitive_steps": 0,
        "shell_width": route["shell_width"],
        "side": side,
        "v7_decoder_30_peak_scratch_bytes": resources[30]["peak_scratch_bytes"],
        "v7_decoder_30_primitive_steps": resources[30]["primitive_steps"],
    }
    owner = draft.get("promotion_generated_schema")
    if type(owner) is not dict or tuple(values) != tuple(owner.get("key_order", ())):
        raise PolicyError("r3-damage-generated-schema")
    bound = _replace_toml_field(
        draft_raw,
        None,
        "profile_policy_sha256",
        sha256(promoted_profile_policy_raw).hexdigest(),
    )
    bound = _replace_toml_field(
        bound,
        None,
        "bootstrap_sha256",
        sha256(bootstrap_spec_raw).hexdigest(),
    )
    rendered = _insert_toml_table_before(bound, "common", "generated", values)
    parsed = _r3_toml_document(rendered, "golden-board.damage-policy/v1")
    if parsed.get("generated") != values:
        raise PolicyError("r3-damage-generated-render")
    return rendered


_R3_ROUTE_GENERATED_KEYS = frozenset(
    {
        "capacity_projection",
        "first_fit",
        "held_out_record_bytes_by_sector",
        "malformed_corpus_case_count",
        "malformed_corpus_sha256",
        "python_reproduction_sha256",
        "recipe_resource_rows",
        "recipient_package_bytes",
        "recipient_package_edge_count",
        "recipient_package_node_count",
        "recipient_package_peak_scratch_bytes",
        "recipient_package_primitive_steps",
        "recipient_package_sha256",
        "recipient_package_table_payload_bytes",
        "reproduction_projection_sha256",
        "route_data_template_sha256",
        "route_example_peak_scratch_bytes_by_sector",
        "route_example_primitive_steps_by_sector",
        "route_headroom_cells_by_sector",
        "route_prefix_cells_by_sector",
        "route_prefix_sha256_by_sector",
        "route_sha256",
        "rust_reproduction_sha256",
        "slot_multiplier_table_sha256",
        "worked_record_bytes_by_sector",
    }
)


def render_r3_profile_limits(
    profile_policy_raw: bytes,
    damage_policy_raw: bytes,
    bootstrap_spec_raw: bytes,
    route_data_raw: bytes,
    recipient_package_raw: bytes,
    capacity_module_raw: bytes,
    base_profile_policy_raw: bytes,
    base_profile_limits_raw: bytes,
    inputs: capacity.CapacityInputs,
) -> bytes:
    """Independently derive the complete selected-v7 limits owner."""

    profile_document = _r3_toml_document(
        profile_policy_raw, "golden-board.profile-policy/v1"
    )
    damage_document = _r3_toml_document(
        damage_policy_raw, "golden-board.damage-policy/v1"
    )
    try:
        route_document = canonical_manifest.validate_canonical_manifest(
            route_data_raw
        )
    except canonical_manifest.ManifestError as error:
        raise PolicyError("r3-route-canonical") from error
    if route_document.get("schema") != "golden-board.route-data/v1":
        raise PolicyError("r3-route-schema")
    generated = route_document.get("generated")
    if type(generated) is not dict or set(generated) != _R3_ROUTE_GENERATED_KEYS:
        raise PolicyError("r3-route-generated")
    capacity_projection = generated.get("capacity_projection")
    if type(capacity_projection) is not dict:
        raise PolicyError("r3-capacity-projection")
    profile_rows = profile_document.get("profile")
    if (
        type(profile_rows) is not list
        or len(profile_rows) != 1
        or profile_rows[0].get("id")
        != "eh72-hier-r5-r2-r1-crc32c-v0"
        or profile_rows[0].get("profile_version") != 7
        or profile_document.get("candidate_set", {}).get("active_profile_ids")
        != ["eh72-hier-r5-r2-r1-crc32c-v0"]
        or damage_document.get("d7", {}).get("case_count") != 408
    ):
        raise PolicyError("r3-owner-shape")
    bootstrap_sha256 = sha256(bootstrap_spec_raw).hexdigest()
    profile_sha256 = sha256(profile_policy_raw).hexdigest()
    damage_sha256 = sha256(damage_policy_raw).hexdigest()
    route_sha256 = sha256(route_data_raw).hexdigest()
    capacity_sha256 = sha256(capacity_module_raw).hexdigest()
    bindings = profile_document.get("bindings")
    if (
        type(bindings) is not dict
        or bindings.get("bootstrap_sha256") != bootstrap_sha256
        or bindings.get("capacity_module_sha256") != capacity_sha256
        or bindings.get("slice_semantic_sha256") != inputs.slice_semantic_sha256
        or damage_document.get("profile_policy_sha256") != profile_sha256
        or damage_document.get("bootstrap_sha256") != bootstrap_sha256
    ):
        raise PolicyError("r3-owner-binding")
    if (
        sha256(base_profile_limits_raw).hexdigest()
        != _PROFILE_LIMITS_V0_SHA256
    ):
        raise PolicyError("r3-base-limits")
    base_limits = _r3_toml_document(
        base_profile_limits_raw, "golden-board.profile-limits/v0"
    )
    base_policy = load_profile_policy(base_profile_policy_raw)
    envelope, capacity_values = _capacity_projection(base_policy, inputs)
    try:
        package = bootstrap.decode_recipe_package(recipient_package_raw, 7)
    except bootstrap.BootstrapError as error:
        raise PolicyError("r3-recipient-package") from error
    if (
        sha256(recipient_package_raw).hexdigest()
        != generated.get("recipient_package_sha256")
        or len(recipient_package_raw) != generated.get("recipient_package_bytes")
    ):
        raise PolicyError("r3-recipient-binding")

    side = route_document.get("side")
    shell_width = route_document.get("shell_width")
    if type(side) is not int or type(shell_width) is not int:
        raise PolicyError("r3-geometry")
    load_payloads = capacity_projection.get("load_payload_bytes")
    load_fragments = capacity_projection.get("load_fragment_counts")
    if type(load_payloads) is not list or type(load_fragments) is not list:
        raise PolicyError("r3-load")
    reserve_payloads = capacity.partition_probe_payload(
        7_141, base_policy.capacity_policy.maximum_probe_payload
    )
    selected_sections: list[tuple[int, int]] = [
        (capacity_projection["inventory_payload_bytes"], 0)
    ]
    selected_sections.extend(
        (item.logical_payload_length, len(item.body_section_ids))
        for item in inputs.tier_frames
    )
    selected_sections.extend(
        (item.payload_length, 0) for item in inputs.real_content_sections
    )
    selected_sections.extend(
        (item.payload_length, 0)
        for bucket in envelope.buckets
        for item in bucket.sections
    )
    selected_sections.extend((item, 0) for item in reserve_payloads)
    selected_sections.extend((item, 0) for item in load_payloads)
    if (
        len(selected_sections) != capacity_projection["inventory_entry_count"]
        or sum(dependencies for _, dependencies in selected_sections)
        != capacity_projection["inventory_dependency_count"]
    ):
        raise PolicyError("r3-section-ledger")
    envelope_lengths = tuple(
        18 + 4 * dependencies + payload + 4
        for payload, dependencies in selected_sections
    )
    maximum_envelope = max(envelope_lengths)
    maximum_fragments = max((length + 156) // 157 for length in envelope_lengths)
    if any(
        type(value) is not int or value < 0
        for value in capacity_projection.values()
        if type(value) is not list
    ):
        raise PolicyError("r3-capacity-value")

    profile_limits_owner = profile_document.get("profile_limits")
    if type(profile_limits_owner) is not dict:
        raise PolicyError("r3-limits-owner")
    generation = profile_limits_owner.get("generation")
    if type(generation) is not str:
        raise PolicyError("r3-limits-owner")
    raw = base_limits["raw"]
    base_bootstrap = base_limits["bootstrap"]
    base_recipe = base_limits["recipe"]
    resource = profile_document["resource_policy"]
    geometry = profile_document["geometry"]
    policy_ceiling = {
        "assembled_content_bytes": base_bootstrap["assembled_content_bytes"],
        "carrier_bytes": profile_document["capacity"]["carrier_bytes_max"],
        "dependency_count_per_section": resource["dependency_count_max"],
        "entry_hypotheses": raw["entry_hypotheses"],
        "inventory_entries": resource["inventory_entry_count_max"],
        "output_bytes": base_bootstrap["output_bytes"],
        "raw_bits": geometry["raw_bits_max"],
        "recipe_edges": resource["recipe_edges_max"],
        "recipe_iteration_count": base_recipe["iteration_count"],
        "recipe_nodes": resource["recipe_nodes_max"],
        "recipe_package_bytes": resource["recipe_encoded_bytes_max"],
        "recipe_primitive_steps": resource["recipe_primitive_steps_max"],
        "recipe_scratch_bytes": resource["recipe_scratch_bytes_max"],
        "recipe_table_payload_bytes": resource["recipe_table_bytes_max"],
        "recipe_tables": resource["recipe_tables_max"],
        "recipes": base_recipe["recipes"],
        "route_records": base_recipe["route_records"],
        "section_attempts": resource["section_attempt_ceiling"],
        "section_payload_bytes": resource["section_payload_bytes_max"],
        "shell_sectors": raw["shell_sectors"],
        "side": geometry["side_max"],
        "shell_width": geometry["shell_width_max"],
    }
    content_before_reserve = capacity_values[11] + capacity_values[4] + 16_384
    semantic_capacity = {
        "authoring_payload_bytes": capacity_values[4],
        "buckets": capacity_values[5],
        "content_capacity_before_reserve_bytes": content_before_reserve,
        "curriculum_concepts": len(inputs.concepts),
        "curriculum_families": len(inputs.families),
        "integrated_tasks": len(inputs.integrated_tasks),
        "inventory_payload_ceiling_bytes": resource["section_payload_bytes_max"],
        "protected_logical_capacity_bytes": content_before_reserve + 7_141,
        "prototype_kinds": len(inputs.prototypes),
        "real_content_body_payload_bytes": capacity_values[8],
        "real_content_body_sections": len(inputs.real_content_sections),
        "real_slice_payload_excluding_inventory": capacity_values[11],
        "reserve_payload_bytes": 7_141,
        "reserve_probe_sections": len(reserve_payloads),
        "simulated_sections": capacity_values[7],
        "slots": capacity_values[6],
        "tier_frame_payload_bytes": capacity_values[9] + capacity_values[10],
        "tier_frame_sections": len(inputs.tier_frames),
    }
    selected_manifestation = {
        "carrier_bytes": side * side // 8,
        "cell_inverse_multiplier": capacity_projection["cell_inverse_multiplier"],
        "cell_multiplier": capacity_projection["cell_multiplier"],
        "cell_offset": capacity_projection["cell_offset"],
        "cells": side * side,
        "dependency_edges": capacity_projection["inventory_dependency_count"],
        "encoded_transport_bytes": capacity_projection["encoded_transport_bytes"],
        "factor_1_group_count": capacity_projection["factor_1_group_count"],
        "factor_2_group_count": capacity_projection["factor_2_group_count"],
        "factor_5_group_count": capacity_projection["factor_5_group_count"],
        "fixed_pad_cells": capacity_projection["fixed_pad_cells"],
        "interior_side": capacity_projection["interior_side"],
        "inventory_dependency_count": capacity_projection["inventory_dependency_count"],
        "inventory_entry_count": capacity_projection["inventory_entry_count"],
        "inventory_fragment_count": capacity_projection["inventory_fragment_count"],
        "inventory_payload_bytes": capacity_projection["inventory_payload_bytes"],
        "load_fragment_counts": load_fragments,
        "load_payload_bytes": load_payloads,
        "logical_group_count": capacity_projection["logical_group_count"],
        "mandatory_physical_unit_count": capacity_projection["mandatory_physical_unit_count"],
        "maximum_fragments_per_section": maximum_fragments,
        "maximum_section_envelope_bytes": maximum_envelope,
        "physical_unit_count": capacity_projection["physical_unit_count"],
        "population": capacity_projection["population"],
        "protected_cells": capacity_projection["protected_cells"],
        "sector_capacity_bytes": route_document["sector_capacity_bytes"],
        "semantic_copy_count": 1,
        "separation_window": capacity_projection["separation_window"],
        "shell_width": shell_width,
        "side": side,
        "slot_inverse_multiplier": capacity_projection["slot_inverse_multiplier"],
        "slot_multiplier": capacity_projection["slot_multiplier"],
    }
    physical_units = capacity_projection["physical_unit_count"]
    repetition_groups = (
        capacity_projection["factor_2_group_count"]
        + capacity_projection["factor_5_group_count"]
    )
    transport = {
        "clean_path_eh_decoder_invocations": 24
        * (physical_units + repetition_groups),
        "clean_path_repetition_candidate_groups": repetition_groups,
        "clean_path_repetition_symbol_invocations": 1_728
        * repetition_groups,
        "encoded_transport_bytes": capacity_projection["encoded_transport_bytes"],
        "eh_codewords_per_physical_unit": 24,
        "maximum_group_candidates": 6,
        "physical_replica_counts": [1, 2, 5],
        "physical_unit_bytes": 216,
        "physical_units": physical_units,
        "profile_tuples": 1,
    }
    route_package = {
        "held_out_record_bytes_by_sector": generated["held_out_record_bytes_by_sector"],
        "recipe_count": len(package.recipes),
        "recipient_package_bytes": generated["recipient_package_bytes"],
        "recipient_package_edge_count": generated["recipient_package_edge_count"],
        "recipient_package_node_count": generated["recipient_package_node_count"],
        "recipient_package_peak_scratch_bytes": generated["recipient_package_peak_scratch_bytes"],
        "recipient_package_primitive_steps": generated["recipient_package_primitive_steps"],
        "recipient_package_sha256": generated["recipient_package_sha256"],
        "recipient_package_table_count": len(package.tables),
        "recipient_package_table_payload_bytes": generated["recipient_package_table_payload_bytes"],
        "route_example_peak_scratch_bytes_by_sector": generated["route_example_peak_scratch_bytes_by_sector"],
        "route_example_primitive_steps_by_sector": generated["route_example_primitive_steps_by_sector"],
        "route_headroom_cells_by_sector": generated["route_headroom_cells_by_sector"],
        "route_prefix_cells_by_sector": generated["route_prefix_cells_by_sector"],
        "route_prefix_sha256_by_sector": generated["route_prefix_sha256_by_sector"],
        "route_records_per_sector": 3 * 12 + len(package.tables) + 1 + 2,
        "route_sha256": generated["route_sha256"],
        "worked_record_bytes_by_sector": generated["worked_record_bytes_by_sector"],
    }
    d0 = len(damage_document["inherited_exact"]["transform_ids"]) * len(
        damage_document["inherited_exact"]["polarity_ids"]
    )
    d1 = len(damage_document["inherited_exact"]["d1_sector_ids"])
    d2 = damage_document["inherited_exact"]["d2_placement_target"]
    d3 = damage_document["inherited_exact"]["d3_seed_count"]
    d4 = physical_units
    d5 = len(damage_document["inherited_exact"]["d5_fixed_permutations"]) + damage_document["inherited_exact"]["d5_fisher_yates_seed_count"]
    d6 = 4 * physical_units
    d7 = damage_document["d7"]["case_count"]
    damage = {
        "cases": d0 + d1 + d2 + d3 + d4 + d5 + d6 + d7,
        "changed_or_erased_coordinates": side * side,
        "d0_cases": d0,
        "d1_cases": d1,
        "d2_cases": d2,
        "d2_square_side": max(32, capacity_projection["interior_side"] // 32),
        "d3_cases": d3,
        "d3_sample_retry_max": 64 * capacity_projection["population"] + 1_024,
        "d3_weight": max(
            64, (capacity_projection["population"] + 1_999) // 2_000
        ),
        "d3_window_side": max(
            32, capacity_projection["interior_side"] // 8
        ),
        "d4_cases": d4,
        "d5_cases": d5,
        "d6_cases": d6,
        "d7_cases": d7,
        "obs_bits_bytes": 4 + (side * side + 7) // 8,
        "obs_matrix_bytes": 2 + side * side,
        "obs_units_bytes": 4
        + (physical_units - 5) * (6 + 216)
        + 5 * (6 + 255),
        "wrong_accepts": 0,
    }
    content_keys = profile_document["profile_limits"]["content"]["key_order"]
    content = {key: base_limits["content"][key] for key in content_keys}
    profile_row = {
        "check_bytes": 4,
        "damage_cases": damage["cases"],
        "encoded_transport_bytes": capacity_projection["encoded_transport_bytes"],
        "fragments_per_semantic_copy": maximum_fragments,
        "id": "eh72-hier-r5-r2-r1-crc32c-v0",
        "obs_units_bytes": damage["obs_units_bytes"],
        "physical_replica_counts": [1, 2, 5],
        "profile_version": 7,
        "protected_unit_bytes": 216,
        "protected_units": physical_units,
        "section_envelope_bytes": maximum_envelope,
        "semantic_copy_count": 1,
    }

    sections = (
        ("policy_ceiling", policy_ceiling),
        ("semantic_capacity", semantic_capacity),
        ("selected_manifestation", selected_manifestation),
        ("transport", transport),
        ("route_package", route_package),
        ("damage", damage),
        ("content", content),
    )
    for name, values in sections:
        owner = profile_document["profile_limits"][name]
        if tuple(values) != tuple(owner["key_order"]):
            raise PolicyError(f"r3-limit-order:{name}")
    profile_owner = profile_document["profile_limits"]["profile_row"]
    if tuple(profile_row) != tuple(profile_owner["key_order"]):
        raise PolicyError("r3-limit-order:profile")
    lines = [
        'schema = "golden-board.profile-limits/v1"',
        f"generation = {_toml_value(generation)}",
        f'profile_policy_sha256 = "{profile_sha256}"',
        f'damage_policy_sha256 = "{damage_sha256}"',
        f'bootstrap_spec_sha256 = "{bootstrap_sha256}"',
        f'route_data_sha256 = "{route_sha256}"',
        f'capacity_module_sha256 = "{capacity_sha256}"',
        f'slice_semantic_sha256 = "{inputs.slice_semantic_sha256}"',
        'profile_ids = ["eh72-hier-r5-r2-r1-crc32c-v0"]',
    ]
    for name, values in sections:
        _emit_table(lines, name, tuple(values.items()))
    lines.extend(("", "[[profile]]"))
    lines.extend(
        f"{key} = {_toml_value(value)}" for key, value in profile_row.items()
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def render_r3_limits_reproduction_receipt(
    implementation_id: str,
    profile_limits_raw: bytes,
    route_data_raw: bytes,
) -> bytes:
    """Render one exact noncircular limits-reproduction receipt."""

    if implementation_id not in {"python", "rust"}:
        raise PolicyError("r3-limits-implementation")
    if type(profile_limits_raw) is not bytes or type(route_data_raw) is not bytes:
        raise PolicyError("r3-limits-receipt-type")
    _r3_toml_document(profile_limits_raw, "golden-board.profile-limits/v1")
    try:
        route = canonical_manifest.validate_canonical_manifest(route_data_raw)
    except canonical_manifest.ManifestError as error:
        raise PolicyError("r3-limits-route") from error
    if route.get("schema") != "golden-board.route-data/v1":
        raise PolicyError("r3-limits-route")
    return canonical_manifest.serialize_manifest(
        {
            "implementation_id": implementation_id,
            "profile_limits_sha256": sha256(profile_limits_raw).hexdigest(),
            "route_data_sha256": sha256(route_data_raw).hexdigest(),
            "schema": "golden-board.m2-r3-limits-reproduction/v1",
        }
    )


def _replace_array_table_hashes(
    raw: bytes,
    table_name: str,
    hashes_by_path: dict[str, str],
) -> bytes:
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise PolicyError("r3-promotion-encoding") from error
    starts = [
        index for index, line in enumerate(lines) if line == f"[[{table_name}]]"
    ]
    observed: set[str] = set()
    for ordinal, start in enumerate(starts):
        end = starts[ordinal + 1] if ordinal + 1 < len(starts) else len(lines)
        for index in range(start + 1, len(lines)):
            if index >= end or (lines[index].startswith("[") and index != start):
                end = index
                break
        path_rows = [
            index
            for index in range(start + 1, end)
            if lines[index].startswith("path = ")
        ]
        hash_rows = [
            index
            for index in range(start + 1, end)
            if lines[index].startswith("sha256 = ")
        ]
        if len(path_rows) != 1 or len(hash_rows) != 1:
            raise PolicyError(f"r3-promotion-{table_name}")
        try:
            path = tomllib.loads(lines[path_rows[0]])["path"]
        except tomllib.TOMLDecodeError as error:
            raise PolicyError(f"r3-promotion-{table_name}") from error
        if path not in hashes_by_path or path in observed:
            raise PolicyError(f"r3-promotion-{table_name}")
        observed.add(path)
        lines[hash_rows[0]] = f'sha256 = "{hashes_by_path[path]}"'
    if observed != set(hashes_by_path):
        raise PolicyError(f"r3-promotion-{table_name}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _replace_generated_owner_blocks(
    raw: bytes,
    rows: tuple[dict[str, object], dict[str, object]],
) -> bytes:
    try:
        text = raw.decode("utf-8")
    except UnicodeError as error:
        raise PolicyError("r3-promotion-encoding") from error
    marker = "[[generated_owner]]"
    first = text.find(marker)
    if first < 0:
        raise PolicyError("r3-promotion-generated-owner")
    cursor = first
    count = 0
    while text.startswith(marker, cursor):
        count += 1
        next_marker = text.find("\n[[generated_owner]]", cursor + len(marker))
        if next_marker < 0:
            break
        cursor = next_marker + 1
    second = text.find("\n[[generated_owner]]", first + len(marker))
    if second < 0 or text.find("\n[[generated_owner]]", second + 1) >= 0:
        raise PolicyError("r3-promotion-generated-owner")
    end = text.find("\n[", second + 2)
    if end < 0:
        raise PolicyError("r3-promotion-generated-owner")
    blocks = []
    for row in rows:
        blocks.append(
            "\n".join(
                (marker,)
                + tuple(
                    f"{key} = {_toml_value(value)}" for key, value in row.items()
                )
            )
        )
    replacement = "\n\n".join(blocks)
    return (text[:first] + replacement + text[end:]).encode("utf-8")


def render_r3_promotion_manifest(
    draft_raw: bytes,
    bootstrap_spec_raw: bytes,
    promoted_profile_policy_raw: bytes,
    promoted_damage_policy_raw: bytes,
    owner_fixture_raw: bytes,
    route_data_raw: bytes,
    profile_limits_raw: bytes,
    python_route_receipt_raw: bytes,
    rust_route_receipt_raw: bytes,
    python_limits_receipt_raw: bytes,
    rust_limits_receipt_raw: bytes,
) -> bytes:
    """Render the exact all-or-nothing pre-result promotion manifest."""

    draft = _r3_toml_document(
        draft_raw, "golden-board.m2-r3-owner-promotion/v1"
    )
    profile = _r3_toml_document(
        promoted_profile_policy_raw, "golden-board.profile-policy/v1"
    )
    damage = _r3_toml_document(
        promoted_damage_policy_raw, "golden-board.damage-policy/v1"
    )
    limits = _r3_toml_document(
        profile_limits_raw, "golden-board.profile-limits/v1"
    )
    route = _r3_complete_route_document(route_data_raw)
    generated = route["generated"]
    if (
        draft.get("status") != "blocked"
        or draft.get("damage_observation_authorized") is not False
        or profile.get("bindings", {}).get("bootstrap_sha256")
        != sha256(bootstrap_spec_raw).hexdigest()
        or damage.get("bootstrap_sha256")
        != sha256(bootstrap_spec_raw).hexdigest()
        or damage.get("profile_policy_sha256")
        != sha256(promoted_profile_policy_raw).hexdigest()
        or limits.get("bootstrap_spec_sha256")
        != sha256(bootstrap_spec_raw).hexdigest()
        or limits.get("profile_policy_sha256")
        != sha256(promoted_profile_policy_raw).hexdigest()
        or limits.get("damage_policy_sha256")
        != sha256(promoted_damage_policy_raw).hexdigest()
        or limits.get("route_data_sha256") != sha256(route_data_raw).hexdigest()
    ):
        raise PolicyError("r3-promotion-binding")
    for implementation_id, raw, expected_sha in (
        (
            "python",
            python_route_receipt_raw,
            generated["python_reproduction_sha256"],
        ),
        ("rust", rust_route_receipt_raw, generated["rust_reproduction_sha256"]),
    ):
        try:
            receipt = canonical_manifest.validate_canonical_manifest(raw)
        except canonical_manifest.ManifestError as error:
            raise PolicyError("r3-route-receipt") from error
        if (
            sha256(raw).hexdigest() != expected_sha
            or receipt.get("schema")
            != "golden-board.m2-r3-route-reproduction/v1"
            or receipt.get("implementation_id") != implementation_id
            or receipt.get("recipient_package_sha256")
            != generated["recipient_package_sha256"]
            or receipt.get("route_data_template_sha256")
            != generated["route_data_template_sha256"]
            or receipt.get("route_sha256") != generated["route_sha256"]
            or receipt.get("reproduction_projection_sha256")
            != generated["reproduction_projection_sha256"]
        ):
            raise PolicyError("r3-route-receipt")
    expected_python_limits = render_r3_limits_reproduction_receipt(
        "python", profile_limits_raw, route_data_raw
    )
    expected_rust_limits = render_r3_limits_reproduction_receipt(
        "rust", profile_limits_raw, route_data_raw
    )
    if (
        python_limits_receipt_raw != expected_python_limits
        or rust_limits_receipt_raw != expected_rust_limits
        or python_limits_receipt_raw == rust_limits_receipt_raw
    ):
        raise PolicyError("r3-limits-receipt")

    draft_rows = draft.get("draft_owner")
    generated_rows = draft.get("generated_owner")
    if (
        type(draft_rows) is not list
        or tuple(row.get("path") for row in draft_rows)
        != (
            "spec/bootstrap-v1.md",
            "spec/profile-policy-v1.toml",
            "spec/damage-policy-v1.toml",
            "conformance/m2-r3-owner-v1.json",
        )
        or type(generated_rows) is not list
        or tuple(row.get("path") for row in generated_rows)
        != ("spec/route-data-v1.json", "spec/profile-limits-v1.toml")
    ):
        raise PolicyError("r3-promotion-owner-order")
    route_row = {
        "path": "spec/route-data-v1.json",
        "python_reproduction_sha256": sha256(
            python_route_receipt_raw
        ).hexdigest(),
        "required_fields": generated_rows[0]["required_fields"],
        "rust_reproduction_sha256": sha256(rust_route_receipt_raw).hexdigest(),
        "schema": "golden-board.route-data/v1",
        "sha256": sha256(route_data_raw).hexdigest(),
        "state": "independently-reproduced",
    }
    limits_row = {
        "path": "spec/profile-limits-v1.toml",
        "python_reproduction_sha256": sha256(
            python_limits_receipt_raw
        ).hexdigest(),
        "required_fields": generated_rows[1]["required_fields"],
        "rust_reproduction_sha256": sha256(rust_limits_receipt_raw).hexdigest(),
        "schema": "golden-board.profile-limits/v1",
        "sha256": sha256(profile_limits_raw).hexdigest(),
        "state": "independently-reproduced",
    }
    key_order = tuple(draft["promotion_render"]["generated_owner_final_key_order"])
    if tuple(route_row) != key_order or tuple(limits_row) != key_order:
        raise PolicyError("r3-promotion-generated-order")
    rendered = _replace_toml_field(
        draft_raw, None, "status", "pre-result-frozen"
    )
    rendered = _replace_toml_field(
        rendered, None, "damage_observation_authorized", True
    )
    rendered = _replace_array_table_hashes(
        rendered,
        "draft_owner",
        {
            "spec/bootstrap-v1.md": sha256(bootstrap_spec_raw).hexdigest(),
            "spec/profile-policy-v1.toml": sha256(
                promoted_profile_policy_raw
            ).hexdigest(),
            "spec/damage-policy-v1.toml": sha256(
                promoted_damage_policy_raw
            ).hexdigest(),
            "conformance/m2-r3-owner-v1.json": sha256(
                owner_fixture_raw
            ).hexdigest(),
        },
    )
    rendered = _replace_generated_owner_blocks(
        rendered, (route_row, limits_row)
    )
    rendered = _replace_toml_field(
        rendered,
        "freeze_barrier",
        "draft_hashes_may_change_before_freeze",
        False,
    )
    final = _r3_toml_document(
        rendered, "golden-board.m2-r3-owner-promotion/v1"
    )
    if (
        final.get("status") != "pre-result-frozen"
        or final.get("damage_observation_authorized") is not True
        or final.get("freeze_barrier", {}).get(
            "draft_hashes_may_change_before_freeze"
        )
        is not False
        or final.get("generated_owner") != [route_row, limits_row]
    ):
        raise PolicyError("r3-promotion-render")
    return rendered


def render_r3_mapping_clarification_manifest(
    pre_clarification_promotion_raw: bytes,
    bootstrap_spec_raw: bytes,
    profile_policy_raw: bytes,
    clarified_damage_policy_raw: bytes,
    owner_fixture_raw: bytes,
    route_data_raw: bytes,
    clarified_profile_limits_raw: bytes,
    python_route_receipt_raw: bytes,
    rust_route_receipt_raw: bytes,
    python_limits_receipt_raw: bytes,
    rust_limits_receipt_raw: bytes,
) -> bytes:
    """Render only the exact final-to-clarified-final promotion mutation."""

    raws = (
        pre_clarification_promotion_raw,
        bootstrap_spec_raw,
        profile_policy_raw,
        clarified_damage_policy_raw,
        owner_fixture_raw,
        route_data_raw,
        clarified_profile_limits_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
    )
    if any(type(raw) is not bytes for raw in raws):
        raise PolicyError("r3-clarification-render-arguments")
    if (
        sha256(pre_clarification_promotion_raw).hexdigest()
        != _R3_PRE_CLARIFICATION_PROMOTION_V1_SHA256
        or sha256(bootstrap_spec_raw).hexdigest()
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or sha256(profile_policy_raw).hexdigest() != _R3_PROFILE_V1_SHA256
        or sha256(clarified_damage_policy_raw).hexdigest()
        != _R3_MAPPING_CLARIFIED_DAMAGE_V1_SHA256
        or sha256(route_data_raw).hexdigest() != _R3_ROUTE_V1_SHA256
        or sha256(clarified_profile_limits_raw).hexdigest()
        != _R3_MAPPING_CLARIFIED_LIMITS_V1_SHA256
        or sha256(owner_fixture_raw).hexdigest()
        != "d0a0da9fa62511fc7914ec214b6ba934c470ac669ed765ace29b42da22896ce3"
    ):
        raise PolicyError("r3-clarification-render-identity")
    old_promotion = _r3_toml_document(
        pre_clarification_promotion_raw,
        "golden-board.m2-r3-owner-promotion/v1",
    )
    profile = _r3_toml_document(
        profile_policy_raw, "golden-board.profile-policy/v1"
    )
    damage = _r3_toml_document(
        clarified_damage_policy_raw, "golden-board.damage-policy/v1"
    )
    limits = _r3_toml_document(
        clarified_profile_limits_raw, "golden-board.profile-limits/v1"
    )
    route = _r3_complete_route_document(route_data_raw)
    route_generated = route["generated"]
    draft_rows = old_promotion.get("draft_owner")
    generated_rows = old_promotion.get("generated_owner")
    if (
        tuple(old_promotion) != _R3_PROMOTION_TOP_KEYS
        or old_promotion.get("status") != "pre-result-frozen"
        or old_promotion.get("damage_observation_authorized") is not True
        or type(draft_rows) is not list
        or tuple((row.get("path"), row.get("sha256")) for row in draft_rows)
        != (
            (
                "spec/bootstrap-v1.md",
                _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256,
            ),
            ("spec/profile-policy-v1.toml", _R3_PROFILE_V1_SHA256),
            (
                "spec/damage-policy-v1.toml",
                _R3_PRE_CLARIFICATION_DAMAGE_V1_SHA256,
            ),
            (
                "conformance/m2-r3-owner-v1.json",
                "d0a0da9fa62511fc7914ec214b6ba934c470ac669ed765ace29b42da22896ce3",
            ),
        )
        or type(generated_rows) is not list
        or len(generated_rows) != 2
        or (
            generated_rows[0].get("path"),
            generated_rows[0].get("sha256"),
        )
        != ("spec/route-data-v1.json", _R3_ROUTE_V1_SHA256)
        or (
            generated_rows[1].get("path"),
            generated_rows[1].get("sha256"),
            generated_rows[1].get("python_reproduction_sha256"),
            generated_rows[1].get("rust_reproduction_sha256"),
        )
        != (
            "spec/profile-limits-v1.toml",
            _R3_PRE_CLARIFICATION_LIMITS_V1_SHA256,
            _R3_PRE_CLARIFICATION_PYTHON_LIMITS_RECEIPT_SHA256,
            _R3_PRE_CLARIFICATION_RUST_LIMITS_RECEIPT_SHA256,
        )
    ):
        raise PolicyError("r3-clarification-precursor")
    if (
        tuple(profile) != _R3_PROFILE_TOP_KEYS
        or tuple(damage) != _R3_PRE_SCHEMA_DAMAGE_TOP_KEYS
        or profile.get("bindings", {}).get("bootstrap_sha256")
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or damage.get("bootstrap_sha256")
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or damage.get("profile_policy_sha256") != _R3_PROFILE_V1_SHA256
        or limits.get("bootstrap_spec_sha256")
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or limits.get("profile_policy_sha256") != _R3_PROFILE_V1_SHA256
        or limits.get("damage_policy_sha256")
        != _R3_MAPPING_CLARIFIED_DAMAGE_V1_SHA256
        or limits.get("route_data_sha256") != _R3_ROUTE_V1_SHA256
    ):
        raise PolicyError("r3-clarification-binding")
    for implementation_id, raw, expected_sha256 in (
        (
            "python",
            python_route_receipt_raw,
            route_generated["python_reproduction_sha256"],
        ),
        (
            "rust",
            rust_route_receipt_raw,
            route_generated["rust_reproduction_sha256"],
        ),
    ):
        try:
            receipt = canonical_manifest.validate_canonical_manifest(raw)
        except canonical_manifest.ManifestError as error:
            raise PolicyError("r3-clarification-route-receipt") from error
        if (
            sha256(raw).hexdigest() != expected_sha256
            or receipt.get("schema")
            != "golden-board.m2-r3-route-reproduction/v1"
            or receipt.get("implementation_id") != implementation_id
            or receipt.get("recipient_package_sha256")
            != route_generated["recipient_package_sha256"]
            or receipt.get("route_data_template_sha256")
            != route_generated["route_data_template_sha256"]
            or receipt.get("route_sha256") != route_generated["route_sha256"]
            or receipt.get("reproduction_projection_sha256")
            != route_generated["reproduction_projection_sha256"]
        ):
            raise PolicyError("r3-clarification-route-receipt")
    if (
        python_limits_receipt_raw
        != render_r3_limits_reproduction_receipt(
            "python", clarified_profile_limits_raw, route_data_raw
        )
        or rust_limits_receipt_raw
        != render_r3_limits_reproduction_receipt(
            "rust", clarified_profile_limits_raw, route_data_raw
        )
        or sha256(python_limits_receipt_raw).hexdigest()
        != "5397497da30d61acf3e13b1d185dac93a37aef68ad81ee1ff8d0b2370af8498d"
        or sha256(rust_limits_receipt_raw).hexdigest()
        != "db573ed9df5d7405704e2abf54e6c09460543c65513c97846cc346cb6ad01722"
    ):
        raise PolicyError("r3-clarification-limits-receipt")
    route_row = dict(generated_rows[0])
    limits_row = {
        "path": "spec/profile-limits-v1.toml",
        "python_reproduction_sha256": sha256(
            python_limits_receipt_raw
        ).hexdigest(),
        "required_fields": generated_rows[1]["required_fields"],
        "rust_reproduction_sha256": sha256(
            rust_limits_receipt_raw
        ).hexdigest(),
        "schema": "golden-board.profile-limits/v1",
        "sha256": _R3_MAPPING_CLARIFIED_LIMITS_V1_SHA256,
        "state": "independently-reproduced",
    }
    key_order = tuple(
        old_promotion["promotion_render"]["generated_owner_final_key_order"]
    )
    if tuple(route_row) != key_order or tuple(limits_row) != key_order:
        raise PolicyError("r3-clarification-generated-order")
    rendered = _replace_array_table_hashes(
        pre_clarification_promotion_raw,
        "draft_owner",
        {
            "spec/bootstrap-v1.md": _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256,
            "spec/profile-policy-v1.toml": _R3_PROFILE_V1_SHA256,
            "spec/damage-policy-v1.toml": (
                _R3_MAPPING_CLARIFIED_DAMAGE_V1_SHA256
            ),
            "conformance/m2-r3-owner-v1.json": (
                "d0a0da9fa62511fc7914ec214b6ba934c470ac669ed765ace29b42da22896ce3"
            ),
        },
    )
    rendered = _replace_generated_owner_blocks(
        rendered, (route_row, limits_row)
    )
    if (
        sha256(rendered).hexdigest()
        != _R3_MAPPING_CLARIFIED_PROMOTION_V1_SHA256
    ):
        raise PolicyError("r3-clarification-render")
    final = _r3_toml_document(
        rendered, "golden-board.m2-r3-owner-promotion/v1"
    )
    if (
        final.get("draft_owner", ())[2].get("sha256")
        != _R3_MAPPING_CLARIFIED_DAMAGE_V1_SHA256
        or final.get("generated_owner") != [route_row, limits_row]
    ):
        raise PolicyError("r3-clarification-render")
    return rendered


def render_r3_damage_schema_clarification_manifest(
    precursor_promotion_raw: bytes,
    bootstrap_spec_raw: bytes,
    profile_policy_raw: bytes,
    damage_policy_raw: bytes,
    owner_fixture_raw: bytes,
    route_data_raw: bytes,
    profile_limits_raw: bytes,
    python_route_receipt_raw: bytes,
    rust_route_receipt_raw: bytes,
    python_limits_receipt_raw: bytes,
    rust_limits_receipt_raw: bytes,
) -> bytes:
    """Render the exact self-owned damage-artifact schema refreeze."""

    raws = (
        precursor_promotion_raw,
        bootstrap_spec_raw,
        profile_policy_raw,
        damage_policy_raw,
        owner_fixture_raw,
        route_data_raw,
        profile_limits_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
    )
    if any(type(raw) is not bytes for raw in raws):
        raise PolicyError("r3-damage-schema-render-arguments")
    fixture_sha256 = (
        "d0a0da9fa62511fc7914ec214b6ba934c470ac669ed765ace29b42da22896ce3"
    )
    if (
        sha256(precursor_promotion_raw).hexdigest()
        != _R3_MAPPING_CLARIFIED_PROMOTION_V1_SHA256
        or sha256(bootstrap_spec_raw).hexdigest()
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or sha256(profile_policy_raw).hexdigest() != _R3_PROFILE_V1_SHA256
        or sha256(damage_policy_raw).hexdigest()
        != _R3_DAMAGE_SCHEMA_CLARIFIED_DAMAGE_V1_SHA256
        or sha256(owner_fixture_raw).hexdigest() != fixture_sha256
        or sha256(route_data_raw).hexdigest() != _R3_ROUTE_V1_SHA256
        or sha256(profile_limits_raw).hexdigest()
        != _R3_DAMAGE_SCHEMA_CLARIFIED_LIMITS_V1_SHA256
    ):
        raise PolicyError("r3-damage-schema-render-identity")
    precursor = _r3_toml_document(
        precursor_promotion_raw,
        "golden-board.m2-r3-owner-promotion/v1",
    )
    profile = _r3_toml_document(
        profile_policy_raw, "golden-board.profile-policy/v1"
    )
    damage = _r3_toml_document(
        damage_policy_raw, "golden-board.damage-policy/v1"
    )
    limits = _r3_toml_document(
        profile_limits_raw, "golden-board.profile-limits/v1"
    )
    route = _r3_complete_route_document(route_data_raw)
    route_generated = route["generated"]
    refreeze = damage.get("artifact_schema_refreeze")
    if (
        tuple(precursor) != _R3_PROMOTION_TOP_KEYS
        or tuple(profile) != _R3_PROFILE_TOP_KEYS
        or tuple(damage) != _R3_DAMAGE_SCHEMA_CLARIFIED_TOP_KEYS
        or tuple(limits) != _R3_LIMITS_TOP_KEYS
        or type(refreeze) is not dict
        or refreeze.get("mode")
        != "bounded-final-to-final-pre-damage-owner-refreeze"
        or refreeze.get("precursor_bootstrap_sha256")
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or refreeze.get("precursor_profile_policy_sha256")
        != _R3_PROFILE_V1_SHA256
        or refreeze.get("archived_precursor_damage_policy_sha256")
        != _R3_MAPPING_CLARIFIED_DAMAGE_V1_SHA256
        or refreeze.get("damage_policy_source")
        != "exact-current-tracked-damage-policy-v1-bytes-containing-this-table"
        or refreeze.get("current_partial_tuple")
        != (
            "profile-bootstrap-and-route-equal-the-pinned-precursors-current-"
            "damage-equals-the-exact-damage-policy-source-current-limits-and-"
            "promotion-equal-the-pinned-precursors-and-the-canonical-v7-"
            "candidate-path-is-absent"
        )
        or refreeze.get("precursor_route_data_sha256")
        != _R3_ROUTE_V1_SHA256
        or refreeze.get("precursor_profile_limits_sha256")
        != _R3_MAPPING_CLARIFIED_LIMITS_V1_SHA256
        or refreeze.get("precursor_python_limits_receipt_sha256")
        != _R3_MAPPING_CLARIFIED_PYTHON_LIMITS_RECEIPT_SHA256
        or refreeze.get("precursor_rust_limits_receipt_sha256")
        != _R3_MAPPING_CLARIFIED_RUST_LIMITS_RECEIPT_SHA256
        or refreeze.get("precursor_promotion_sha256")
        != _R3_MAPPING_CLARIFIED_PROMOTION_V1_SHA256
        or refreeze.get("precursor_archive_manifest_sha256")
        != _R3_PRE_DAMAGE_SCHEMA_ARCHIVE_MANIFEST_SHA256
        or refreeze.get("write_set")
        != [
            "spec/damage-policy-v1.toml",
            "spec/profile-limits-v1.toml",
            "spec/m2-r3-owner-promotion-v1.toml",
        ]
        or refreeze.get("write_order")
        != [
            "spec/damage-policy-v1.toml",
            "spec/profile-limits-v1.toml",
            "spec/m2-r3-owner-promotion-v1.toml",
        ]
        or refreeze.get("status_last") is not True
        or profile.get("bindings", {}).get("bootstrap_sha256")
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or damage.get("bootstrap_sha256")
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or damage.get("profile_policy_sha256") != _R3_PROFILE_V1_SHA256
        or limits.get("bootstrap_spec_sha256")
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or limits.get("profile_policy_sha256") != _R3_PROFILE_V1_SHA256
        or limits.get("damage_policy_sha256")
        != _R3_DAMAGE_SCHEMA_CLARIFIED_DAMAGE_V1_SHA256
        or limits.get("route_data_sha256") != _R3_ROUTE_V1_SHA256
    ):
        raise PolicyError("r3-damage-schema-render-binding")

    draft_rows = precursor.get("draft_owner")
    generated_rows = precursor.get("generated_owner")
    if (
        precursor.get("status") != "pre-result-frozen"
        or precursor.get("damage_observation_authorized") is not True
        or type(draft_rows) is not list
        or tuple((row.get("path"), row.get("sha256")) for row in draft_rows)
        != (
            (
                "spec/bootstrap-v1.md",
                _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256,
            ),
            ("spec/profile-policy-v1.toml", _R3_PROFILE_V1_SHA256),
            (
                "spec/damage-policy-v1.toml",
                _R3_MAPPING_CLARIFIED_DAMAGE_V1_SHA256,
            ),
            ("conformance/m2-r3-owner-v1.json", fixture_sha256),
        )
        or type(generated_rows) is not list
        or len(generated_rows) != 2
        or (
            generated_rows[0].get("path"),
            generated_rows[0].get("sha256"),
        )
        != ("spec/route-data-v1.json", _R3_ROUTE_V1_SHA256)
        or (
            generated_rows[1].get("path"),
            generated_rows[1].get("sha256"),
            generated_rows[1].get("python_reproduction_sha256"),
            generated_rows[1].get("rust_reproduction_sha256"),
        )
        != (
            "spec/profile-limits-v1.toml",
            _R3_MAPPING_CLARIFIED_LIMITS_V1_SHA256,
            _R3_MAPPING_CLARIFIED_PYTHON_LIMITS_RECEIPT_SHA256,
            _R3_MAPPING_CLARIFIED_RUST_LIMITS_RECEIPT_SHA256,
        )
    ):
        raise PolicyError("r3-damage-schema-render-precursor")

    for implementation_id, raw, expected_sha256 in (
        (
            "python",
            python_route_receipt_raw,
            route_generated["python_reproduction_sha256"],
        ),
        (
            "rust",
            rust_route_receipt_raw,
            route_generated["rust_reproduction_sha256"],
        ),
    ):
        try:
            receipt = canonical_manifest.validate_canonical_manifest(raw)
        except canonical_manifest.ManifestError as error:
            raise PolicyError("r3-damage-schema-route-receipt") from error
        if (
            sha256(raw).hexdigest() != expected_sha256
            or receipt.get("schema")
            != "golden-board.m2-r3-route-reproduction/v1"
            or receipt.get("implementation_id") != implementation_id
            or receipt.get("recipient_package_sha256")
            != route_generated["recipient_package_sha256"]
            or receipt.get("route_data_template_sha256")
            != route_generated["route_data_template_sha256"]
            or receipt.get("route_sha256") != route_generated["route_sha256"]
            or receipt.get("reproduction_projection_sha256")
            != route_generated["reproduction_projection_sha256"]
        ):
            raise PolicyError("r3-damage-schema-route-receipt")
    if (
        python_limits_receipt_raw
        != render_r3_limits_reproduction_receipt(
            "python", profile_limits_raw, route_data_raw
        )
        or rust_limits_receipt_raw
        != render_r3_limits_reproduction_receipt(
            "rust", profile_limits_raw, route_data_raw
        )
        or sha256(python_limits_receipt_raw).hexdigest()
        != _R3_DAMAGE_SCHEMA_CLARIFIED_PYTHON_LIMITS_RECEIPT_SHA256
        or sha256(rust_limits_receipt_raw).hexdigest()
        != _R3_DAMAGE_SCHEMA_CLARIFIED_RUST_LIMITS_RECEIPT_SHA256
    ):
        raise PolicyError("r3-damage-schema-limits-receipt")

    route_row = dict(generated_rows[0])
    limits_row = {
        "path": "spec/profile-limits-v1.toml",
        "python_reproduction_sha256": (
            _R3_DAMAGE_SCHEMA_CLARIFIED_PYTHON_LIMITS_RECEIPT_SHA256
        ),
        "required_fields": generated_rows[1]["required_fields"],
        "rust_reproduction_sha256": (
            _R3_DAMAGE_SCHEMA_CLARIFIED_RUST_LIMITS_RECEIPT_SHA256
        ),
        "schema": "golden-board.profile-limits/v1",
        "sha256": _R3_DAMAGE_SCHEMA_CLARIFIED_LIMITS_V1_SHA256,
        "state": "independently-reproduced",
    }
    key_order = tuple(
        precursor["promotion_render"]["generated_owner_final_key_order"]
    )
    if tuple(route_row) != key_order or tuple(limits_row) != key_order:
        raise PolicyError("r3-damage-schema-generated-order")
    rendered = _replace_array_table_hashes(
        precursor_promotion_raw,
        "draft_owner",
        {
            "spec/bootstrap-v1.md": _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256,
            "spec/profile-policy-v1.toml": _R3_PROFILE_V1_SHA256,
            "spec/damage-policy-v1.toml": (
                _R3_DAMAGE_SCHEMA_CLARIFIED_DAMAGE_V1_SHA256
            ),
            "conformance/m2-r3-owner-v1.json": fixture_sha256,
        },
    )
    rendered = _replace_generated_owner_blocks(
        rendered, (route_row, limits_row)
    )
    if (
        sha256(rendered).hexdigest()
        != _R3_DAMAGE_SCHEMA_CLARIFIED_PROMOTION_V1_SHA256
    ):
        raise PolicyError("r3-damage-schema-render")
    final = _r3_toml_document(
        rendered, "golden-board.m2-r3-owner-promotion/v1"
    )
    if (
        final.get("draft_owner", ())[2].get("sha256")
        != _R3_DAMAGE_SCHEMA_CLARIFIED_DAMAGE_V1_SHA256
        or final.get("generated_owner") != [route_row, limits_row]
    ):
        raise PolicyError("r3-damage-schema-render")
    return rendered


def render_r3_independence_witness_clarification_manifest(
    precursor_promotion_raw: bytes,
    bootstrap_spec_raw: bytes,
    profile_policy_raw: bytes,
    damage_policy_raw: bytes,
    owner_fixture_raw: bytes,
    route_data_raw: bytes,
    profile_limits_raw: bytes,
    python_route_receipt_raw: bytes,
    rust_route_receipt_raw: bytes,
    python_limits_receipt_raw: bytes,
    rust_limits_receipt_raw: bytes,
) -> bytes:
    """Render the exact self-owned independence-witness refreeze."""

    raws = (
        precursor_promotion_raw,
        bootstrap_spec_raw,
        profile_policy_raw,
        damage_policy_raw,
        owner_fixture_raw,
        route_data_raw,
        profile_limits_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
    )
    if any(type(raw) is not bytes for raw in raws):
        raise PolicyError("r3-witness-render-arguments")
    fixture_sha256 = (
        "d0a0da9fa62511fc7914ec214b6ba934c470ac669ed765ace29b42da22896ce3"
    )
    if (
        sha256(precursor_promotion_raw).hexdigest()
        != _R3_DAMAGE_SCHEMA_CLARIFIED_PROMOTION_V1_SHA256
        or sha256(bootstrap_spec_raw).hexdigest()
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or sha256(profile_policy_raw).hexdigest() != _R3_PROFILE_V1_SHA256
        or sha256(damage_policy_raw).hexdigest()
        != _R3_PRE_GATE6_CONVERGENCE_DAMAGE_V1_SHA256
        or sha256(owner_fixture_raw).hexdigest() != fixture_sha256
        or sha256(route_data_raw).hexdigest() != _R3_ROUTE_V1_SHA256
        or sha256(profile_limits_raw).hexdigest()
        != _R3_PRE_GATE6_CONVERGENCE_LIMITS_V1_SHA256
    ):
        raise PolicyError("r3-witness-render-identity")
    precursor = _r3_toml_document(
        precursor_promotion_raw,
        "golden-board.m2-r3-owner-promotion/v1",
    )
    profile = _r3_toml_document(
        profile_policy_raw, "golden-board.profile-policy/v1"
    )
    damage = _r3_toml_document(
        damage_policy_raw, "golden-board.damage-policy/v1"
    )
    limits = _r3_toml_document(
        profile_limits_raw, "golden-board.profile-limits/v1"
    )
    refreeze = damage.get("independence_witness_refreeze")
    if (
        tuple(precursor) != _R3_PROMOTION_TOP_KEYS
        or tuple(profile) != _R3_PROFILE_TOP_KEYS
        or tuple(damage) != _R3_PRE_GATE6_CONVERGENCE_DAMAGE_TOP_KEYS
        or tuple(limits) != _R3_LIMITS_TOP_KEYS
        or type(refreeze) is not dict
        or refreeze.get("mode")
        != "bounded-final-to-final-pre-damage-independence-witness-refreeze"
        or refreeze.get("precursor_bootstrap_sha256")
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or refreeze.get("precursor_profile_policy_sha256")
        != _R3_PROFILE_V1_SHA256
        or refreeze.get("archived_precursor_damage_policy_sha256")
        != _R3_DAMAGE_SCHEMA_CLARIFIED_DAMAGE_V1_SHA256
        or refreeze.get("precursor_route_data_sha256")
        != _R3_ROUTE_V1_SHA256
        or refreeze.get("precursor_profile_limits_sha256")
        != _R3_DAMAGE_SCHEMA_CLARIFIED_LIMITS_V1_SHA256
        or refreeze.get("precursor_python_limits_receipt_sha256")
        != _R3_DAMAGE_SCHEMA_CLARIFIED_PYTHON_LIMITS_RECEIPT_SHA256
        or refreeze.get("precursor_rust_limits_receipt_sha256")
        != _R3_DAMAGE_SCHEMA_CLARIFIED_RUST_LIMITS_RECEIPT_SHA256
        or refreeze.get("precursor_promotion_sha256")
        != _R3_DAMAGE_SCHEMA_CLARIFIED_PROMOTION_V1_SHA256
        or refreeze.get("precursor_candidate_manifest_sha256")
        != "54e7f72bd1d3e045fe699c070f5378d696413c28ad786535e9c7ae7fdc1a1d8f"
        or refreeze.get("precursor_candidate_manifest_identity")
        != "bd72b98d59065bf5ef8f4cfd3917d76a3aeb135c969315626c8729a068f66d97"
        or refreeze.get("precursor_archive_manifest_sha256")
        != _R3_PRE_INDEPENDENCE_WITNESS_ARCHIVE_MANIFEST_SHA256
        or refreeze.get("damage_policy_source")
        != "exact-current-tracked-damage-policy-v1-bytes-containing-this-table"
        or refreeze.get("current_partial_tuple")
        != (
            "profile-bootstrap-and-route-equal-the-pinned-precursors-current-"
            "damage-equals-the-exact-damage-policy-source-current-limits-and-"
            "promotion-equal-the-pinned-precursors-and-the-canonical-v7-"
            "candidate-path-is-absent"
        )
        or refreeze.get("write_set")
        != [
            "spec/damage-policy-v1.toml",
            "spec/profile-limits-v1.toml",
            "spec/m2-r3-owner-promotion-v1.toml",
        ]
        or refreeze.get("write_order")
        != [
            "spec/damage-policy-v1.toml",
            "spec/profile-limits-v1.toml",
            "spec/m2-r3-owner-promotion-v1.toml",
        ]
        or refreeze.get("status_last") is not True
        or refreeze.get("final_status") != "pre-result-frozen"
        or refreeze.get("final_damage_observation_authorized") is not True
        or profile.get("bindings", {}).get("bootstrap_sha256")
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or damage.get("bootstrap_sha256")
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or damage.get("profile_policy_sha256") != _R3_PROFILE_V1_SHA256
        or limits.get("bootstrap_spec_sha256")
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or limits.get("profile_policy_sha256") != _R3_PROFILE_V1_SHA256
        or limits.get("damage_policy_sha256")
        != _R3_PRE_GATE6_CONVERGENCE_DAMAGE_V1_SHA256
        or limits.get("route_data_sha256") != _R3_ROUTE_V1_SHA256
    ):
        raise PolicyError("r3-witness-render-binding")

    draft_rows = precursor.get("draft_owner")
    generated_rows = precursor.get("generated_owner")
    if (
        precursor.get("status") != "pre-result-frozen"
        or precursor.get("damage_observation_authorized") is not True
        or type(draft_rows) is not list
        or tuple((row.get("path"), row.get("sha256")) for row in draft_rows)
        != (
            ("spec/bootstrap-v1.md", _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256),
            ("spec/profile-policy-v1.toml", _R3_PROFILE_V1_SHA256),
            (
                "spec/damage-policy-v1.toml",
                _R3_DAMAGE_SCHEMA_CLARIFIED_DAMAGE_V1_SHA256,
            ),
            ("conformance/m2-r3-owner-v1.json", fixture_sha256),
        )
        or type(generated_rows) is not list
        or len(generated_rows) != 2
        or (generated_rows[0].get("path"), generated_rows[0].get("sha256"))
        != ("spec/route-data-v1.json", _R3_ROUTE_V1_SHA256)
        or (
            generated_rows[1].get("path"),
            generated_rows[1].get("sha256"),
            generated_rows[1].get("python_reproduction_sha256"),
            generated_rows[1].get("rust_reproduction_sha256"),
        )
        != (
            "spec/profile-limits-v1.toml",
            _R3_DAMAGE_SCHEMA_CLARIFIED_LIMITS_V1_SHA256,
            _R3_DAMAGE_SCHEMA_CLARIFIED_PYTHON_LIMITS_RECEIPT_SHA256,
            _R3_DAMAGE_SCHEMA_CLARIFIED_RUST_LIMITS_RECEIPT_SHA256,
        )
    ):
        raise PolicyError("r3-witness-render-precursor")
    if (
        python_limits_receipt_raw
        != render_r3_limits_reproduction_receipt(
            "python", profile_limits_raw, route_data_raw
        )
        or rust_limits_receipt_raw
        != render_r3_limits_reproduction_receipt(
            "rust", profile_limits_raw, route_data_raw
        )
        or sha256(python_limits_receipt_raw).hexdigest()
        != _R3_PRE_GATE6_CONVERGENCE_PYTHON_LIMITS_RECEIPT_SHA256
        or sha256(rust_limits_receipt_raw).hexdigest()
        != _R3_PRE_GATE6_CONVERGENCE_RUST_LIMITS_RECEIPT_SHA256
    ):
        raise PolicyError("r3-witness-limits-receipt")

    route_row = dict(generated_rows[0])
    limits_row = {
        "path": "spec/profile-limits-v1.toml",
        "python_reproduction_sha256": (
            _R3_PRE_GATE6_CONVERGENCE_PYTHON_LIMITS_RECEIPT_SHA256
        ),
        "required_fields": generated_rows[1]["required_fields"],
        "rust_reproduction_sha256": (
            _R3_PRE_GATE6_CONVERGENCE_RUST_LIMITS_RECEIPT_SHA256
        ),
        "schema": "golden-board.profile-limits/v1",
        "sha256": _R3_PRE_GATE6_CONVERGENCE_LIMITS_V1_SHA256,
        "state": "independently-reproduced",
    }
    key_order = tuple(
        precursor["promotion_render"]["generated_owner_final_key_order"]
    )
    if tuple(route_row) != key_order or tuple(limits_row) != key_order:
        raise PolicyError("r3-witness-generated-order")
    rendered = _replace_array_table_hashes(
        precursor_promotion_raw,
        "draft_owner",
        {
            "spec/bootstrap-v1.md": _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256,
            "spec/profile-policy-v1.toml": _R3_PROFILE_V1_SHA256,
            "spec/damage-policy-v1.toml": (
                _R3_PRE_GATE6_CONVERGENCE_DAMAGE_V1_SHA256
            ),
            "conformance/m2-r3-owner-v1.json": fixture_sha256,
        },
    )
    rendered = _replace_generated_owner_blocks(rendered, (route_row, limits_row))
    if (
        sha256(rendered).hexdigest()
        != _R3_PRE_GATE6_CONVERGENCE_PROMOTION_V1_SHA256
    ):
        raise PolicyError("r3-witness-render")
    final_bundle = R3PromotionWriteBundle(
        profile_policy_raw,
        damage_policy_raw,
        route_data_raw,
        profile_limits_raw,
        rendered,
    )
    _load_r3_promoted_owner_set(
        final_bundle,
        bootstrap_spec_raw,
        owner_fixture_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
        _R3_PRE_GATE6_CONVERGENCE_PROMOTION_V1_SHA256,
    )
    return rendered


def render_r3_gate6_convergence_clarification_manifest(
    precursor_promotion_raw: bytes,
    bootstrap_spec_raw: bytes,
    profile_policy_raw: bytes,
    damage_policy_raw: bytes,
    owner_fixture_raw: bytes,
    route_data_raw: bytes,
    profile_limits_raw: bytes,
    python_route_receipt_raw: bytes,
    rust_route_receipt_raw: bytes,
    python_limits_receipt_raw: bytes,
    rust_limits_receipt_raw: bytes,
) -> bytes:
    """Render the exact self-owned pre-render convergence refreeze."""

    raws = (
        precursor_promotion_raw,
        bootstrap_spec_raw,
        profile_policy_raw,
        damage_policy_raw,
        owner_fixture_raw,
        route_data_raw,
        profile_limits_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
    )
    if any(type(raw) is not bytes for raw in raws):
        raise PolicyError("r3-convergence-render-arguments")
    fixture_sha256 = (
        "d0a0da9fa62511fc7914ec214b6ba934c470ac669ed765ace29b42da22896ce3"
    )
    if (
        sha256(precursor_promotion_raw).hexdigest()
        != _R3_PRE_GATE6_CONVERGENCE_PROMOTION_V1_SHA256
        or sha256(bootstrap_spec_raw).hexdigest()
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or sha256(profile_policy_raw).hexdigest() != _R3_PROFILE_V1_SHA256
        or sha256(damage_policy_raw).hexdigest() != _R3_DAMAGE_V1_SHA256
        or sha256(owner_fixture_raw).hexdigest() != fixture_sha256
        or sha256(route_data_raw).hexdigest() != _R3_ROUTE_V1_SHA256
        or sha256(profile_limits_raw).hexdigest()
        != _R3_PROFILE_LIMITS_V1_SHA256
    ):
        raise PolicyError("r3-convergence-render-identity")
    precursor = _r3_toml_document(
        precursor_promotion_raw,
        "golden-board.m2-r3-owner-promotion/v1",
    )
    profile = _r3_toml_document(
        profile_policy_raw, "golden-board.profile-policy/v1"
    )
    damage = _r3_toml_document(
        damage_policy_raw, "golden-board.damage-policy/v1"
    )
    limits = _r3_toml_document(
        profile_limits_raw, "golden-board.profile-limits/v1"
    )
    expected_refreeze = {
        "mode": "bounded-final-to-final-pre-damage-gate6-convergence-refreeze",
        "precursor_archive_manifest_sha256": (
            _R3_PRE_GATE6_CONVERGENCE_ARCHIVE_MANIFEST_SHA256
        ),
        "damage_policy_source": (
            "exact-current-tracked-damage-policy-v1-bytes-containing-this-table"
        ),
        "transition": (
            "from-the-exact-archive-preimage-replace-only-family-case-rows-"
            "binding-case-acceptance-and-gate6-publish-with-their-values-in-"
            "this-owner-and-append-this-table-and-fourth-admission-binding-"
            "including-the-all-four-regeneration-precondition"
        ),
        "owner_dag_regeneration": (
            "rerender-exact-limits-and-both-receipts-from-the-new-damage-"
            "owner-then-change-only-the-promotion-damage-row-and-limits-row-"
            "hashes"
        ),
        "preconditions": (
            "all-four-archives-verify-canonical-v7-is-absent-two-gate6-create-"
            "attempts-ended-in-independent-tooling-disagreement-and-wrote-no-"
            "damage-evidence-and-no-canonical-gate6-outcome-exists"
        ),
        "write_set": [
            "spec/damage-policy-v1.toml",
            "spec/profile-limits-v1.toml",
            "spec/m2-r3-owner-promotion-v1.toml",
        ],
    }
    admission = damage.get("admission")
    if (
        tuple(precursor) != _R3_PROMOTION_TOP_KEYS
        or tuple(profile) != _R3_PROFILE_TOP_KEYS
        or tuple(damage) != _R3_DAMAGE_TOP_KEYS
        or tuple(limits) != _R3_LIMITS_TOP_KEYS
        or damage.get("gate6_convergence_refreeze") != expected_refreeze
        or type(admission) is not dict
        or admission.get("pre_gate6_convergence_archive_root")
        != "artifacts/history/m2-r3-pre-gate6-convergence-clarification"
        or admission.get("pre_gate6_convergence_archive_manifest")
        != (
            "artifacts/history/m2-r3-pre-gate6-convergence-clarification/"
            "archive-files.sha256"
        )
        or admission.get(
            "pre_gate6_convergence_archive_manifest_sha256"
        )
        != _R3_PRE_GATE6_CONVERGENCE_ARCHIVE_MANIFEST_SHA256
        or admission.get("pre_gate6_convergence_candidate_manifest_sha256")
        != "4439abb20aeb4943d9f3dddd4b2b914c08f3a411b791d2ced797533351168019"
        or admission.get("pre_gate6_convergence_candidate_manifest_identity")
        != "69b4052299e43a675683361e6a7fa83798b7b3646c873233cfbdd18432ac4cf4"
        or admission.get("pre_gate6_convergence_damage_policy_sha256")
        != _R3_PRE_GATE6_CONVERGENCE_DAMAGE_V1_SHA256
        or admission.get("pre_gate6_convergence_profile_limits_sha256")
        != _R3_PRE_GATE6_CONVERGENCE_LIMITS_V1_SHA256
        or admission.get("pre_gate6_convergence_promotion_sha256")
        != _R3_PRE_GATE6_CONVERGENCE_PROMOTION_V1_SHA256
        or admission.get(
            "pre_gate6_convergence_python_limits_receipt_sha256"
        )
        != _R3_PRE_GATE6_CONVERGENCE_PYTHON_LIMITS_RECEIPT_SHA256
        or admission.get(
            "pre_gate6_convergence_rust_limits_receipt_sha256"
        )
        != _R3_PRE_GATE6_CONVERGENCE_RUST_LIMITS_RECEIPT_SHA256
        or admission.get("canonical_regeneration_precondition")
        != (
            "all-four-owned-eleven-file-archive-manifests-exist-match-and-"
            "verify-and-the-canonical-v7-candidate-path-is-absent"
        )
        or profile.get("bindings", {}).get("bootstrap_sha256")
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or damage.get("bootstrap_sha256")
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or damage.get("profile_policy_sha256") != _R3_PROFILE_V1_SHA256
        or limits.get("bootstrap_spec_sha256")
        != _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256
        or limits.get("profile_policy_sha256") != _R3_PROFILE_V1_SHA256
        or limits.get("damage_policy_sha256") != _R3_DAMAGE_V1_SHA256
        or limits.get("route_data_sha256") != _R3_ROUTE_V1_SHA256
    ):
        raise PolicyError("r3-convergence-render-binding")
    draft_rows = precursor.get("draft_owner")
    generated_rows = precursor.get("generated_owner")
    if (
        precursor.get("status") != "pre-result-frozen"
        or precursor.get("damage_observation_authorized") is not True
        or type(draft_rows) is not list
        or tuple((row.get("path"), row.get("sha256")) for row in draft_rows)
        != (
            ("spec/bootstrap-v1.md", _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256),
            ("spec/profile-policy-v1.toml", _R3_PROFILE_V1_SHA256),
            (
                "spec/damage-policy-v1.toml",
                _R3_PRE_GATE6_CONVERGENCE_DAMAGE_V1_SHA256,
            ),
            ("conformance/m2-r3-owner-v1.json", fixture_sha256),
        )
        or type(generated_rows) is not list
        or len(generated_rows) != 2
        or (generated_rows[0].get("path"), generated_rows[0].get("sha256"))
        != ("spec/route-data-v1.json", _R3_ROUTE_V1_SHA256)
        or (
            generated_rows[1].get("path"),
            generated_rows[1].get("sha256"),
            generated_rows[1].get("python_reproduction_sha256"),
            generated_rows[1].get("rust_reproduction_sha256"),
        )
        != (
            "spec/profile-limits-v1.toml",
            _R3_PRE_GATE6_CONVERGENCE_LIMITS_V1_SHA256,
            _R3_PRE_GATE6_CONVERGENCE_PYTHON_LIMITS_RECEIPT_SHA256,
            _R3_PRE_GATE6_CONVERGENCE_RUST_LIMITS_RECEIPT_SHA256,
        )
    ):
        raise PolicyError("r3-convergence-render-precursor")
    if (
        python_limits_receipt_raw
        != render_r3_limits_reproduction_receipt(
            "python", profile_limits_raw, route_data_raw
        )
        or rust_limits_receipt_raw
        != render_r3_limits_reproduction_receipt(
            "rust", profile_limits_raw, route_data_raw
        )
        or sha256(python_limits_receipt_raw).hexdigest()
        != _R3_PYTHON_LIMITS_RECEIPT_SHA256
        or sha256(rust_limits_receipt_raw).hexdigest()
        != _R3_RUST_LIMITS_RECEIPT_SHA256
    ):
        raise PolicyError("r3-convergence-limits-receipt")
    route_row = dict(generated_rows[0])
    limits_row = dict(generated_rows[1])
    limits_row["python_reproduction_sha256"] = (
        _R3_PYTHON_LIMITS_RECEIPT_SHA256
    )
    limits_row["rust_reproduction_sha256"] = _R3_RUST_LIMITS_RECEIPT_SHA256
    limits_row["sha256"] = _R3_PROFILE_LIMITS_V1_SHA256
    key_order = tuple(
        precursor["promotion_render"]["generated_owner_final_key_order"]
    )
    if tuple(route_row) != key_order or tuple(limits_row) != key_order:
        raise PolicyError("r3-convergence-generated-order")
    rendered = _replace_array_table_hashes(
        precursor_promotion_raw,
        "draft_owner",
        {
            "spec/bootstrap-v1.md": _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256,
            "spec/profile-policy-v1.toml": _R3_PROFILE_V1_SHA256,
            "spec/damage-policy-v1.toml": _R3_DAMAGE_V1_SHA256,
            "conformance/m2-r3-owner-v1.json": fixture_sha256,
        },
    )
    rendered = _replace_generated_owner_blocks(rendered, (route_row, limits_row))
    if sha256(rendered).hexdigest() != _R3_PROMOTION_V1_SHA256:
        raise PolicyError("r3-convergence-render")
    final_bundle = R3PromotionWriteBundle(
        profile_policy_raw,
        damage_policy_raw,
        route_data_raw,
        profile_limits_raw,
        rendered,
    )
    _load_r3_promoted_owner_set(
        final_bundle,
        bootstrap_spec_raw,
        owner_fixture_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
        _R3_PROMOTION_V1_SHA256,
    )
    return rendered


def _remove_r3_generated_table(raw: bytes, before_section: str) -> bytes:
    try:
        text = raw.decode("utf-8")
    except UnicodeError as error:
        raise PolicyError("r3-precursor-encoding") from error
    start_marker = "\n[generated]\n"
    end_marker = f"\n[{before_section}]\n"
    start = text.find(start_marker)
    end = text.find(end_marker, start + len(start_marker))
    if start < 0 or end < 0 or text.find(start_marker, start + 1) >= 0:
        raise PolicyError("r3-precursor-generated")
    return (text[:start] + text[end:]).encode("utf-8")


def _r3_blocked_owner_precursors(
    profile_raw: bytes,
    damage_raw: bytes,
    promotion_raw: bytes,
) -> tuple[bytes, bytes, bytes]:
    """Recover the exact reviewed regression precursors from either state."""

    if any(type(raw) is not bytes for raw in (profile_raw, damage_raw, promotion_raw)):
        raise PolicyError("r3-precursor-type")
    observed = tuple(
        sha256(raw).hexdigest() for raw in (profile_raw, damage_raw, promotion_raw)
    )
    blocked = (
        _R3_BLOCKED_PROFILE_V1_SHA256,
        _R3_BLOCKED_DAMAGE_V1_SHA256,
        _R3_BLOCKED_PROMOTION_V1_SHA256,
    )
    if observed == blocked:
        return profile_raw, damage_raw, promotion_raw
    if observed != (
        _R3_PROFILE_V1_SHA256,
        _R3_PRE_CLARIFICATION_DAMAGE_V1_SHA256,
        _R3_PRE_CLARIFICATION_PROMOTION_V1_SHA256,
    ):
        raise PolicyError("r3-precursor-identity")

    profile = _remove_r3_generated_table(profile_raw, "candidate_set")
    profile = _replace_toml_field(
        profile,
        "bindings",
        "bootstrap_sha256",
        _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256,
    )
    damage = _remove_r3_generated_table(damage_raw, "common")
    damage = _replace_toml_field(
        damage,
        None,
        "profile_policy_sha256",
        _R3_BLOCKED_PROFILE_BINDING_SHA256,
    )
    damage = _replace_toml_field(
        damage,
        None,
        "bootstrap_sha256",
        _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256,
    )

    promoted = _r3_toml_document(
        promotion_raw, "golden-board.m2-r3-owner-promotion/v1"
    )
    generated = promoted.get("generated_owner")
    if type(generated) is not list or len(generated) != 2:
        raise PolicyError("r3-precursor-promotion")
    promotion = _replace_toml_field(
        promotion_raw, None, "status", "blocked"
    )
    promotion = _replace_toml_field(
        promotion, None, "damage_observation_authorized", False
    )
    promotion = _replace_array_table_hashes(
        promotion,
        "draft_owner",
        {
            "spec/bootstrap-v1.md": _R3_BLOCKED_BOOTSTRAP_BINDING_SHA256,
            "spec/profile-policy-v1.toml": _R3_BLOCKED_PROFILE_BINDING_SHA256,
            "spec/damage-policy-v1.toml": _R3_BLOCKED_DAMAGE_BINDING_SHA256,
            "conformance/m2-r3-owner-v1.json": (
                "d0a0da9fa62511fc7914ec214b6ba934c470ac669ed765ace29b42da22896ce3"
            ),
        },
    )
    promotion = _replace_generated_owner_blocks(
        promotion,
        (
            {
                "path": "spec/route-data-v1.json",
                "schema": "golden-board.route-data/v1",
                "state": "absent-or-not-yet-independently-reproduced",
                "required_fields": generated[0]["required_fields"],
            },
            {
                "path": "spec/profile-limits-v1.toml",
                "schema": "golden-board.profile-limits/v1",
                "state": "absent-or-not-yet-independently-reproduced",
                "required_fields": generated[1]["required_fields"],
            },
        ),
    )
    algebraic_marker = b"\n[algebraic_binding]\n"
    if promotion.count(algebraic_marker) != 1:
        raise PolicyError("r3-precursor-promotion")
    promotion = promotion.replace(
        algebraic_marker, b"\n\n[algebraic_binding]\n", 1
    )
    promotion = _replace_toml_field(
        promotion,
        "freeze_barrier",
        "draft_hashes_may_change_before_freeze",
        True,
    )
    recovered = (profile, damage, promotion)
    if tuple(sha256(raw).hexdigest() for raw in recovered) != blocked:
        raise PolicyError("r3-precursor-reconstruction")
    return recovered


_R3_RUST_STAGE_COMPARISON_FILES = frozenset(
    {
        "damage-policy-v1.projected.toml",
        "m2-r3-owner-promotion-v1.projected.toml",
        "profile-limits-v1.toml",
        "profile-policy-v1.projected.toml",
        "recipient-package-v7.bin",
        "route-data-v1.json",
        "route-data-v1.template.json",
        "route-malformed-corpus.json",
        "route-prefix-sector-0.bin",
        "route-prefix-sector-1.bin",
        "route-prefix-sector-2.bin",
        "route-prefix-sector-3.bin",
        "route-prefixes.bin",
        "route-reproduction-projection.json",
    }
)


def validate_r3_rust_stage(
    stage_directory: Path,
    expected_manifest_sha256: str,
    expected_files: dict[str, bytes],
) -> tuple[bytes, bytes]:
    """Byte-compare one explicit independently emitted Rust staging bundle."""

    if (
        not isinstance(stage_directory, Path)
        or type(expected_manifest_sha256) is not str
        or len(expected_manifest_sha256) != 64
        or type(expected_files) is not dict
        or set(expected_files) != _R3_RUST_STAGE_COMPARISON_FILES
        or any(type(value) is not bytes for value in expected_files.values())
    ):
        raise PolicyError("r3-rust-stage-arguments")
    try:
        resolved = stage_directory.resolve(strict=True)
    except OSError as error:
        raise PolicyError("r3-rust-stage-path") from error
    if not resolved.is_dir() or stage_directory.is_symlink():
        raise PolicyError("r3-rust-stage-path")
    manifest_path = resolved / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PolicyError("r3-rust-stage-manifest")
    manifest_stat = manifest_path.stat()
    manifest_raw = manifest_path.read_bytes()
    if (
        manifest_stat.st_nlink != 1
        or not 1 <= len(manifest_raw) <= 65_536
        or len(manifest_raw) != manifest_stat.st_size
        or sha256(manifest_raw).hexdigest() != expected_manifest_sha256
    ):
        raise PolicyError("r3-rust-stage-manifest")
    try:
        manifest = canonical_manifest.validate_canonical_manifest(manifest_raw)
    except canonical_manifest.ManifestError as error:
        raise PolicyError("r3-rust-stage-manifest") from error
    rows = manifest.get("files")
    if (
        set(manifest) != {"files", "schema"}
        or manifest.get("schema") != "golden-board.m2-r3-rust-stage/v1"
        or type(rows) is not list
        or any(
            type(row) is not dict
            or tuple(row) != ("bytes", "path", "sha256")
            for row in rows
        )
    ):
        raise PolicyError("r3-rust-stage-manifest")
    expected_names = _R3_RUST_STAGE_COMPARISON_FILES | {
        "limits-rust-reproduction.json",
        "route-rust-reproduction.json",
    }
    names = tuple(row["path"] for row in rows)
    if (
        names != tuple(sorted(expected_names))
        or set(path.name for path in resolved.iterdir())
        != expected_names | {"manifest.json"}
    ):
        raise PolicyError("r3-rust-stage-files")
    loaded: dict[str, bytes] = {}
    identities = {(manifest_stat.st_dev, manifest_stat.st_ino)}
    total_bytes = 0
    for row in rows:
        name = row["path"]
        path = resolved / name
        if (
            type(name) is not str
            or Path(name).name != name
            or path.is_symlink()
            or not path.is_file()
            or type(row["bytes"]) is not int
            or not 1 <= row["bytes"] <= 1_048_576
            or type(row["sha256"]) is not str
            or len(row["sha256"]) != 64
        ):
            raise PolicyError("r3-rust-stage-file")
        stat = path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if stat.st_nlink != 1 or identity in identities:
            raise PolicyError("r3-rust-stage-file")
        identities.add(identity)
        raw = path.read_bytes()
        total_bytes += len(raw)
        if (
            len(raw) != stat.st_size
            or len(raw) != row["bytes"]
            or sha256(raw).hexdigest() != row["sha256"]
        ):
            raise PolicyError("r3-rust-stage-file")
        loaded[name] = raw
    if total_bytes > 4_194_304:
        raise PolicyError("r3-rust-stage-size")
    for name, expected in expected_files.items():
        if loaded[name] != expected:
            raise PolicyError(f"r3-rust-stage-drift:{name}")
    route = _r3_complete_route_document(expected_files["route-data-v1.json"])
    generated = route["generated"]
    expected_route_receipt = canonical_manifest.serialize_manifest(
        {
            "implementation_id": "rust",
            "recipient_package_sha256": generated["recipient_package_sha256"],
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
    expected_limits_receipt = render_r3_limits_reproduction_receipt(
        "rust",
        expected_files["profile-limits-v1.toml"],
        expected_files["route-data-v1.json"],
    )
    if (
        loaded["route-rust-reproduction.json"] != expected_route_receipt
        or loaded["limits-rust-reproduction.json"] != expected_limits_receipt
    ):
        raise PolicyError("r3-rust-stage-receipt")
    return expected_route_receipt, expected_limits_receipt


_R3_PRE_CLARIFICATION_ARCHIVE_PATHS = frozenset(
    {
        "eh72-hier-r5-r2-r1-crc32c-v0/candidate-manifest.json",
        "eh72-hier-r5-r2-r1-crc32c-v0/capacity-ledger.json",
        "eh72-hier-r5-r2-r1-crc32c-v0/carrier.obs-bits",
        "eh72-hier-r5-r2-r1-crc32c-v0/density-ledger.json",
        "eh72-hier-r5-r2-r1-crc32c-v0/ownership-ledger.json",
        "eh72-hier-r5-r2-r1-crc32c-v0/semantic-envelope.json",
        "owners/damage-policy-v1.toml",
        "owners/limits-python-reproduction.json",
        "owners/limits-rust-reproduction.json",
        "owners/m2-r3-owner-promotion-v1.toml",
        "owners/profile-limits-v1.toml",
    }
)


def validate_r3_pre_clarification_archive(
    workspace: Path,
    damage_policy_raw: bytes,
) -> dict[str, bytes]:
    """Admit the exact immutable eleven-file pre-clarification archive."""

    if not isinstance(workspace, Path) or type(damage_policy_raw) is not bytes:
        raise PolicyError("r3-archive-arguments")
    try:
        root = workspace.resolve(strict=True)
    except OSError as error:
        raise PolicyError("r3-archive-workspace") from error
    if workspace.is_symlink() or not root.is_dir():
        raise PolicyError("r3-archive-workspace")
    damage_sha256 = sha256(damage_policy_raw).hexdigest()
    if damage_sha256 not in {
        _R3_MAPPING_CLARIFIED_DAMAGE_V1_SHA256,
        _R3_DAMAGE_SCHEMA_CLARIFIED_DAMAGE_V1_SHA256,
        _R3_PRE_GATE6_CONVERGENCE_DAMAGE_V1_SHA256,
        _R3_DAMAGE_V1_SHA256,
    }:
        raise PolicyError("r3-archive-damage-owner")
    damage = _r3_toml_document(
        damage_policy_raw, "golden-board.damage-policy/v1"
    )
    admission = damage.get("admission")
    archive_relative = (
        "artifacts/history/m2-r3-pre-d7-mapping-clarification"
    )
    manifest_relative = f"{archive_relative}/archive-files.sha256"
    if (
        type(admission) is not dict
        or admission.get("pre_clarification_archive_root") != archive_relative
        or admission.get("pre_clarification_archive_manifest")
        != manifest_relative
        or admission.get("pre_clarification_archive_manifest_sha256")
        != _R3_PRE_CLARIFICATION_ARCHIVE_MANIFEST_SHA256
        or admission.get("pre_clarification_archive_scope")
        != (
            "exact-six-file-v7-tree-plus-old-damage-limits-promotion-and-"
            "both-limits-receipts"
        )
        or admission.get("pre_clarification_candidate_manifest_identity")
        != "2cfd677dab41e882b045077d888784814c269b072272125282edfbca3638d793"
        or admission.get("pre_clarification_profile_limits_sha256")
        != _R3_PRE_CLARIFICATION_LIMITS_V1_SHA256
        or admission.get("pre_clarification_reuse")
        != "history-only-never-canonical-r3-gate-or-damage-input"
        or admission.get("canonical_regeneration_precondition")
        != (
            (
                "all-four-owned-eleven-file-archive-manifests-exist-match-"
                "and-verify-and-the-canonical-v7-candidate-path-is-absent"
            )
            if damage_sha256 == _R3_DAMAGE_V1_SHA256
            else (
                "all-three-owned-eleven-file-archive-manifests-exist-match-"
                "and-verify-and-the-canonical-v7-candidate-path-is-absent"
            )
            if damage_sha256
            == _R3_PRE_GATE6_CONVERGENCE_DAMAGE_V1_SHA256
            else (
                "both-owned-eleven-file-archive-manifests-exist-match-and-"
                "verify-and-the-canonical-v7-candidate-path-is-absent"
            )
            if damage_sha256 == _R3_DAMAGE_SCHEMA_CLARIFIED_DAMAGE_V1_SHA256
            else (
                "archive-manifest-exists-matches-and-verifies-all-eleven-"
                "files-and-canonical-candidate-path-is-absent"
            )
        )
    ):
        raise PolicyError("r3-archive-owner")
    artifacts = root / "artifacts"
    history = artifacts / "history"
    archive = history / "m2-r3-pre-d7-mapping-clarification"
    candidate = archive / "eh72-hier-r5-r2-r1-crc32c-v0"
    owners = archive / "owners"
    if any(
        path.is_symlink() or not path.is_dir()
        for path in (artifacts, history, archive, candidate, owners)
    ):
        raise PolicyError("r3-archive-path")
    manifest_path = archive / "archive-files.sha256"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PolicyError("r3-archive-manifest")
    manifest_stat = manifest_path.stat()
    manifest_raw = manifest_path.read_bytes()
    if (
        manifest_stat.st_nlink != 1
        or not 1 <= len(manifest_raw) <= 16_384
        or len(manifest_raw) != manifest_stat.st_size
        or not manifest_raw.endswith(b"\n")
        or sha256(manifest_raw).hexdigest()
        != _R3_PRE_CLARIFICATION_ARCHIVE_MANIFEST_SHA256
    ):
        raise PolicyError("r3-archive-manifest")
    try:
        lines = manifest_raw.decode("ascii").splitlines()
    except UnicodeError as error:
        raise PolicyError("r3-archive-manifest") from error
    rows: dict[str, str] = {}
    for line in lines:
        digest, separator, relative = line.partition("  ")
        parts = relative.split("/")
        if (
            separator != "  "
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or relative not in _R3_PRE_CLARIFICATION_ARCHIVE_PATHS
            or relative in rows
            or any(part in ("", ".", "..") for part in parts)
            or "\\" in relative
        ):
            raise PolicyError("r3-archive-manifest")
        rows[relative] = digest
    if set(rows) != _R3_PRE_CLARIFICATION_ARCHIVE_PATHS:
        raise PolicyError("r3-archive-manifest")
    try:
        root_entries = {path.name: path for path in archive.iterdir()}
        candidate_entries = {path.name: path for path in candidate.iterdir()}
        owner_entries = {path.name: path for path in owners.iterdir()}
    except OSError as error:
        raise PolicyError("r3-archive-files") from error
    if (
        set(root_entries)
        != {
            "archive-files.sha256",
            "eh72-hier-r5-r2-r1-crc32c-v0",
            "owners",
        }
        or set(candidate_entries)
        != {Path(path).name for path in _R3_PRE_CLARIFICATION_ARCHIVE_PATHS if path.startswith("eh72-")}
        or set(owner_entries)
        != {Path(path).name for path in _R3_PRE_CLARIFICATION_ARCHIVE_PATHS if path.startswith("owners/")}
    ):
        raise PolicyError("r3-archive-files")
    loaded: dict[str, bytes] = {}
    identities: set[tuple[int, int]] = {
        (manifest_stat.st_dev, manifest_stat.st_ino)
    }
    total = 0
    for relative, digest in rows.items():
        path = archive / relative
        if path.is_symlink() or not path.is_file():
            raise PolicyError("r3-archive-file")
        stat = path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if (
            stat.st_nlink != 1
            or identity in identities
            or not 1 <= stat.st_size <= 1_048_576
        ):
            raise PolicyError("r3-archive-file")
        identities.add(identity)
        raw = path.read_bytes()
        total += len(raw)
        if len(raw) != stat.st_size or sha256(raw).hexdigest() != digest:
            raise PolicyError("r3-archive-file")
        loaded[relative] = raw
    if total > 4_194_304:
        raise PolicyError("r3-archive-file")
    try:
        archived_candidate = canonical_manifest.validate_canonical_manifest(
            loaded[
                "eh72-hier-r5-r2-r1-crc32c-v0/candidate-manifest.json"
            ]
        )
    except canonical_manifest.ManifestError as error:
        raise PolicyError("r3-archive-candidate") from error
    if (
        archived_candidate.get("manifest_identity")
        != admission["pre_clarification_candidate_manifest_identity"]
        or archived_candidate.get("profile_limits_sha256")
        != admission["pre_clarification_profile_limits_sha256"]
        or sha256(loaded["owners/damage-policy-v1.toml"]).hexdigest()
        != _R3_PRE_CLARIFICATION_DAMAGE_V1_SHA256
        or sha256(loaded["owners/profile-limits-v1.toml"]).hexdigest()
        != _R3_PRE_CLARIFICATION_LIMITS_V1_SHA256
        or sha256(
            loaded["owners/m2-r3-owner-promotion-v1.toml"]
        ).hexdigest()
        != _R3_PRE_CLARIFICATION_PROMOTION_V1_SHA256
        or sha256(
            loaded["owners/limits-python-reproduction.json"]
        ).hexdigest()
        != _R3_PRE_CLARIFICATION_PYTHON_LIMITS_RECEIPT_SHA256
        or sha256(
            loaded["owners/limits-rust-reproduction.json"]
        ).hexdigest()
        != _R3_PRE_CLARIFICATION_RUST_LIMITS_RECEIPT_SHA256
    ):
        raise PolicyError("r3-archive-identity")
    return loaded


def validate_r3_pre_damage_schema_archive(
    workspace: Path,
    damage_policy_raw: bytes,
) -> dict[str, bytes]:
    """Admit the exact immutable pre-damage-schema eleven-file archive."""

    if not isinstance(workspace, Path) or type(damage_policy_raw) is not bytes:
        raise PolicyError("r3-schema-archive-arguments")
    try:
        root = workspace.resolve(strict=True)
    except OSError as error:
        raise PolicyError("r3-schema-archive-workspace") from error
    if workspace.is_symlink() or not root.is_dir():
        raise PolicyError("r3-schema-archive-workspace")
    damage_sha256 = sha256(damage_policy_raw).hexdigest()
    if damage_sha256 not in {
        _R3_DAMAGE_SCHEMA_CLARIFIED_DAMAGE_V1_SHA256,
        _R3_PRE_GATE6_CONVERGENCE_DAMAGE_V1_SHA256,
        _R3_DAMAGE_V1_SHA256,
    }:
        raise PolicyError("r3-schema-archive-damage-owner")
    damage = _r3_toml_document(
        damage_policy_raw, "golden-board.damage-policy/v1"
    )
    expected_top_keys = (
        _R3_DAMAGE_TOP_KEYS
        if damage_sha256 == _R3_DAMAGE_V1_SHA256
        else _R3_PRE_GATE6_CONVERGENCE_DAMAGE_TOP_KEYS
        if damage_sha256
        == _R3_PRE_GATE6_CONVERGENCE_DAMAGE_V1_SHA256
        else _R3_DAMAGE_SCHEMA_CLARIFIED_TOP_KEYS
    )
    if tuple(damage) != expected_top_keys:
        raise PolicyError("r3-schema-archive-damage-owner")
    admission = damage.get("admission")
    archive_relative = (
        "artifacts/history/m2-r3-pre-damage-artifact-schema-clarification"
    )
    manifest_relative = f"{archive_relative}/archive-files.sha256"
    if (
        type(admission) is not dict
        or admission.get("pre_damage_artifact_schema_archive_root")
        != archive_relative
        or admission.get("pre_damage_artifact_schema_archive_manifest")
        != manifest_relative
        or admission.get(
            "pre_damage_artifact_schema_archive_manifest_sha256"
        )
        != _R3_PRE_DAMAGE_SCHEMA_ARCHIVE_MANIFEST_SHA256
        or admission.get("pre_damage_artifact_schema_archive_scope")
        != (
            "exact-six-file-v7-tree-plus-pre-schema-clarification-damage-"
            "limits-promotion-and-both-limits-receipts"
        )
        or admission.get(
            "pre_damage_artifact_schema_candidate_manifest_sha256"
        )
        != "ae6d98ce6c52c0b849f479491d2fe86679b2d9cca9401c4860ae037621021f9f"
        or admission.get(
            "pre_damage_artifact_schema_candidate_manifest_identity"
        )
        != "5f105061d05ae22bc00755f6dca040818e75b6e99d52573ed0e16ebfb66dcaa3"
        or admission.get("pre_damage_artifact_schema_damage_policy_sha256")
        != _R3_MAPPING_CLARIFIED_DAMAGE_V1_SHA256
        or admission.get("pre_damage_artifact_schema_profile_limits_sha256")
        != _R3_MAPPING_CLARIFIED_LIMITS_V1_SHA256
        or admission.get("pre_damage_artifact_schema_promotion_sha256")
        != _R3_MAPPING_CLARIFIED_PROMOTION_V1_SHA256
        or admission.get(
            "pre_damage_artifact_schema_python_limits_receipt_sha256"
        )
        != _R3_MAPPING_CLARIFIED_PYTHON_LIMITS_RECEIPT_SHA256
        or admission.get(
            "pre_damage_artifact_schema_rust_limits_receipt_sha256"
        )
        != _R3_MAPPING_CLARIFIED_RUST_LIMITS_RECEIPT_SHA256
        or admission.get("pre_damage_artifact_schema_reuse")
        != "history-only-never-current-r3-gate-damage-or-proof-input"
        or admission.get("canonical_regeneration_precondition")
        != (
            (
                "all-four-owned-eleven-file-archive-manifests-exist-match-"
                "and-verify-and-the-canonical-v7-candidate-path-is-absent"
            )
            if damage_sha256 == _R3_DAMAGE_V1_SHA256
            else (
                "all-three-owned-eleven-file-archive-manifests-exist-match-"
                "and-verify-and-the-canonical-v7-candidate-path-is-absent"
            )
            if damage_sha256
            == _R3_PRE_GATE6_CONVERGENCE_DAMAGE_V1_SHA256
            else (
                "both-owned-eleven-file-archive-manifests-exist-match-and-"
                "verify-and-the-canonical-v7-candidate-path-is-absent"
            )
        )
    ):
        raise PolicyError("r3-schema-archive-owner")

    artifacts = root / "artifacts"
    history = artifacts / "history"
    archive = history / "m2-r3-pre-damage-artifact-schema-clarification"
    candidate = archive / "eh72-hier-r5-r2-r1-crc32c-v0"
    owners = archive / "owners"
    if any(
        path.is_symlink() or not path.is_dir()
        for path in (artifacts, history, archive, candidate, owners)
    ):
        raise PolicyError("r3-schema-archive-path")
    manifest_path = archive / "archive-files.sha256"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PolicyError("r3-schema-archive-manifest")
    manifest_stat = manifest_path.stat()
    manifest_raw = manifest_path.read_bytes()
    if (
        manifest_stat.st_nlink != 1
        or not 1 <= len(manifest_raw) <= 16_384
        or len(manifest_raw) != manifest_stat.st_size
        or not manifest_raw.endswith(b"\n")
        or sha256(manifest_raw).hexdigest()
        != _R3_PRE_DAMAGE_SCHEMA_ARCHIVE_MANIFEST_SHA256
    ):
        raise PolicyError("r3-schema-archive-manifest")
    try:
        lines = manifest_raw.decode("ascii").splitlines()
    except UnicodeError as error:
        raise PolicyError("r3-schema-archive-manifest") from error
    rows: dict[str, str] = {}
    for line in lines:
        digest, separator, relative = line.partition("  ")
        parts = relative.split("/")
        if (
            separator != "  "
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or relative not in _R3_PRE_CLARIFICATION_ARCHIVE_PATHS
            or relative in rows
            or any(part in ("", ".", "..") for part in parts)
            or "\\" in relative
        ):
            raise PolicyError("r3-schema-archive-manifest")
        rows[relative] = digest
    if set(rows) != _R3_PRE_CLARIFICATION_ARCHIVE_PATHS:
        raise PolicyError("r3-schema-archive-manifest")
    try:
        root_entries = {path.name: path for path in archive.iterdir()}
        candidate_entries = {path.name: path for path in candidate.iterdir()}
        owner_entries = {path.name: path for path in owners.iterdir()}
    except OSError as error:
        raise PolicyError("r3-schema-archive-files") from error
    if (
        set(root_entries)
        != {
            "archive-files.sha256",
            "eh72-hier-r5-r2-r1-crc32c-v0",
            "owners",
        }
        or set(candidate_entries)
        != {
            Path(path).name
            for path in _R3_PRE_CLARIFICATION_ARCHIVE_PATHS
            if path.startswith("eh72-")
        }
        or set(owner_entries)
        != {
            Path(path).name
            for path in _R3_PRE_CLARIFICATION_ARCHIVE_PATHS
            if path.startswith("owners/")
        }
    ):
        raise PolicyError("r3-schema-archive-files")

    loaded: dict[str, bytes] = {}
    identities: set[tuple[int, int]] = {
        (manifest_stat.st_dev, manifest_stat.st_ino)
    }
    total = 0
    for relative, digest in rows.items():
        path = archive / relative
        if path.is_symlink() or not path.is_file():
            raise PolicyError("r3-schema-archive-file")
        stat = path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if (
            stat.st_nlink != 1
            or identity in identities
            or not 1 <= stat.st_size <= 1_048_576
        ):
            raise PolicyError("r3-schema-archive-file")
        identities.add(identity)
        raw = path.read_bytes()
        total += len(raw)
        if len(raw) != stat.st_size or sha256(raw).hexdigest() != digest:
            raise PolicyError("r3-schema-archive-file")
        loaded[relative] = raw
    if total > 4_194_304:
        raise PolicyError("r3-schema-archive-file")
    try:
        archived_candidate = canonical_manifest.validate_canonical_manifest(
            loaded[
                "eh72-hier-r5-r2-r1-crc32c-v0/candidate-manifest.json"
            ]
        )
    except canonical_manifest.ManifestError as error:
        raise PolicyError("r3-schema-archive-candidate") from error
    if (
        sha256(
            loaded[
                "eh72-hier-r5-r2-r1-crc32c-v0/candidate-manifest.json"
            ]
        ).hexdigest()
        != admission["pre_damage_artifact_schema_candidate_manifest_sha256"]
        or archived_candidate.get("manifest_identity")
        != admission["pre_damage_artifact_schema_candidate_manifest_identity"]
        or archived_candidate.get("profile_limits_sha256")
        != admission["pre_damage_artifact_schema_profile_limits_sha256"]
        or sha256(loaded["owners/damage-policy-v1.toml"]).hexdigest()
        != _R3_MAPPING_CLARIFIED_DAMAGE_V1_SHA256
        or sha256(loaded["owners/profile-limits-v1.toml"]).hexdigest()
        != _R3_MAPPING_CLARIFIED_LIMITS_V1_SHA256
        or sha256(
            loaded["owners/m2-r3-owner-promotion-v1.toml"]
        ).hexdigest()
        != _R3_MAPPING_CLARIFIED_PROMOTION_V1_SHA256
        or sha256(
            loaded["owners/limits-python-reproduction.json"]
        ).hexdigest()
        != _R3_MAPPING_CLARIFIED_PYTHON_LIMITS_RECEIPT_SHA256
        or sha256(
            loaded["owners/limits-rust-reproduction.json"]
        ).hexdigest()
        != _R3_MAPPING_CLARIFIED_RUST_LIMITS_RECEIPT_SHA256
    ):
        raise PolicyError("r3-schema-archive-identity")
    return loaded


def validate_r3_pre_independence_witness_archive(
    workspace: Path,
    damage_policy_raw: bytes,
) -> dict[str, bytes]:
    """Admit the exact immutable pre-witness eleven-file archive."""

    if not isinstance(workspace, Path) or type(damage_policy_raw) is not bytes:
        raise PolicyError("r3-witness-archive-arguments")
    try:
        root = workspace.resolve(strict=True)
    except OSError as error:
        raise PolicyError("r3-witness-archive-workspace") from error
    if workspace.is_symlink() or not root.is_dir():
        raise PolicyError("r3-witness-archive-workspace")
    damage_sha256 = sha256(damage_policy_raw).hexdigest()
    if damage_sha256 not in {
        _R3_PRE_GATE6_CONVERGENCE_DAMAGE_V1_SHA256,
        _R3_DAMAGE_V1_SHA256,
    }:
        raise PolicyError("r3-witness-archive-damage-owner")
    damage = _r3_toml_document(
        damage_policy_raw, "golden-board.damage-policy/v1"
    )
    if tuple(damage) != (
        _R3_DAMAGE_TOP_KEYS
        if damage_sha256 == _R3_DAMAGE_V1_SHA256
        else _R3_PRE_GATE6_CONVERGENCE_DAMAGE_TOP_KEYS
    ):
        raise PolicyError("r3-witness-archive-damage-owner")
    admission = damage.get("admission")
    archive_relative = (
        "artifacts/history/m2-r3-pre-independence-witness-clarification"
    )
    manifest_relative = f"{archive_relative}/archive-files.sha256"
    if (
        type(admission) is not dict
        or admission.get("pre_independence_witness_archive_root")
        != archive_relative
        or admission.get("pre_independence_witness_archive_manifest")
        != manifest_relative
        or admission.get(
            "pre_independence_witness_archive_manifest_sha256"
        )
        != _R3_PRE_INDEPENDENCE_WITNESS_ARCHIVE_MANIFEST_SHA256
        or admission.get("pre_independence_witness_archive_scope")
        != (
            "exact-six-file-v7-tree-plus-pre-witness-clarification-damage-"
            "limits-promotion-and-both-limits-receipts"
        )
        or admission.get(
            "pre_independence_witness_candidate_manifest_sha256"
        )
        != "54e7f72bd1d3e045fe699c070f5378d696413c28ad786535e9c7ae7fdc1a1d8f"
        or admission.get(
            "pre_independence_witness_candidate_manifest_identity"
        )
        != "bd72b98d59065bf5ef8f4cfd3917d76a3aeb135c969315626c8729a068f66d97"
        or admission.get("pre_independence_witness_damage_policy_sha256")
        != _R3_DAMAGE_SCHEMA_CLARIFIED_DAMAGE_V1_SHA256
        or admission.get("pre_independence_witness_profile_limits_sha256")
        != _R3_DAMAGE_SCHEMA_CLARIFIED_LIMITS_V1_SHA256
        or admission.get("pre_independence_witness_promotion_sha256")
        != _R3_DAMAGE_SCHEMA_CLARIFIED_PROMOTION_V1_SHA256
        or admission.get(
            "pre_independence_witness_python_limits_receipt_sha256"
        )
        != _R3_DAMAGE_SCHEMA_CLARIFIED_PYTHON_LIMITS_RECEIPT_SHA256
        or admission.get(
            "pre_independence_witness_rust_limits_receipt_sha256"
        )
        != _R3_DAMAGE_SCHEMA_CLARIFIED_RUST_LIMITS_RECEIPT_SHA256
        or admission.get("pre_independence_witness_reuse")
        != "history-only-never-current-r3-gate-damage-or-proof-input"
        or admission.get("canonical_regeneration_precondition")
        != (
            (
                "all-four-owned-eleven-file-archive-manifests-exist-match-"
                "and-verify-and-the-canonical-v7-candidate-path-is-absent"
            )
            if damage_sha256 == _R3_DAMAGE_V1_SHA256
            else (
                "all-three-owned-eleven-file-archive-manifests-exist-match-"
                "and-verify-and-the-canonical-v7-candidate-path-is-absent"
            )
        )
    ):
        raise PolicyError("r3-witness-archive-owner")

    artifacts = root / "artifacts"
    history = artifacts / "history"
    archive = history / "m2-r3-pre-independence-witness-clarification"
    candidate = archive / "eh72-hier-r5-r2-r1-crc32c-v0"
    owners = archive / "owners"
    if any(
        path.is_symlink() or not path.is_dir()
        for path in (artifacts, history, archive, candidate, owners)
    ):
        raise PolicyError("r3-witness-archive-path")
    manifest_path = archive / "archive-files.sha256"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PolicyError("r3-witness-archive-manifest")
    manifest_stat = manifest_path.stat()
    manifest_raw = manifest_path.read_bytes()
    if (
        manifest_stat.st_nlink != 1
        or not 1 <= len(manifest_raw) <= 16_384
        or len(manifest_raw) != manifest_stat.st_size
        or not manifest_raw.endswith(b"\n")
        or sha256(manifest_raw).hexdigest()
        != _R3_PRE_INDEPENDENCE_WITNESS_ARCHIVE_MANIFEST_SHA256
    ):
        raise PolicyError("r3-witness-archive-manifest")
    try:
        lines = manifest_raw.decode("ascii").splitlines()
    except UnicodeError as error:
        raise PolicyError("r3-witness-archive-manifest") from error
    rows: dict[str, str] = {}
    for line in lines:
        digest, separator, relative = line.partition("  ")
        parts = relative.split("/")
        if (
            separator != "  "
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or relative not in _R3_PRE_CLARIFICATION_ARCHIVE_PATHS
            or relative in rows
            or any(part in ("", ".", "..") for part in parts)
            or "\\" in relative
        ):
            raise PolicyError("r3-witness-archive-manifest")
        rows[relative] = digest
    if set(rows) != _R3_PRE_CLARIFICATION_ARCHIVE_PATHS:
        raise PolicyError("r3-witness-archive-manifest")
    try:
        root_entries = {path.name: path for path in archive.iterdir()}
        candidate_entries = {path.name: path for path in candidate.iterdir()}
        owner_entries = {path.name: path for path in owners.iterdir()}
    except OSError as error:
        raise PolicyError("r3-witness-archive-files") from error
    if (
        set(root_entries)
        != {
            "archive-files.sha256",
            "eh72-hier-r5-r2-r1-crc32c-v0",
            "owners",
        }
        or set(candidate_entries)
        != {
            Path(path).name
            for path in _R3_PRE_CLARIFICATION_ARCHIVE_PATHS
            if path.startswith("eh72-")
        }
        or set(owner_entries)
        != {
            Path(path).name
            for path in _R3_PRE_CLARIFICATION_ARCHIVE_PATHS
            if path.startswith("owners/")
        }
    ):
        raise PolicyError("r3-witness-archive-files")

    loaded: dict[str, bytes] = {}
    identities: set[tuple[int, int]] = {
        (manifest_stat.st_dev, manifest_stat.st_ino)
    }
    total = 0
    for relative, digest in rows.items():
        path = archive / relative
        if path.is_symlink() or not path.is_file():
            raise PolicyError("r3-witness-archive-file")
        stat = path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if (
            stat.st_nlink != 1
            or identity in identities
            or not 1 <= stat.st_size <= 1_048_576
        ):
            raise PolicyError("r3-witness-archive-file")
        identities.add(identity)
        raw = path.read_bytes()
        total += len(raw)
        if len(raw) != stat.st_size or sha256(raw).hexdigest() != digest:
            raise PolicyError("r3-witness-archive-file")
        loaded[relative] = raw
    if total > 4_194_304:
        raise PolicyError("r3-witness-archive-file")
    try:
        archived_candidate = canonical_manifest.validate_canonical_manifest(
            loaded[
                "eh72-hier-r5-r2-r1-crc32c-v0/candidate-manifest.json"
            ]
        )
    except canonical_manifest.ManifestError as error:
        raise PolicyError("r3-witness-archive-candidate") from error
    if (
        sha256(
            loaded[
                "eh72-hier-r5-r2-r1-crc32c-v0/candidate-manifest.json"
            ]
        ).hexdigest()
        != admission["pre_independence_witness_candidate_manifest_sha256"]
        or archived_candidate.get("manifest_identity")
        != admission["pre_independence_witness_candidate_manifest_identity"]
        or archived_candidate.get("profile_limits_sha256")
        != admission["pre_independence_witness_profile_limits_sha256"]
        or sha256(loaded["owners/damage-policy-v1.toml"]).hexdigest()
        != _R3_DAMAGE_SCHEMA_CLARIFIED_DAMAGE_V1_SHA256
        or sha256(loaded["owners/profile-limits-v1.toml"]).hexdigest()
        != _R3_DAMAGE_SCHEMA_CLARIFIED_LIMITS_V1_SHA256
        or sha256(
            loaded["owners/m2-r3-owner-promotion-v1.toml"]
        ).hexdigest()
        != _R3_DAMAGE_SCHEMA_CLARIFIED_PROMOTION_V1_SHA256
        or sha256(
            loaded["owners/limits-python-reproduction.json"]
        ).hexdigest()
        != _R3_DAMAGE_SCHEMA_CLARIFIED_PYTHON_LIMITS_RECEIPT_SHA256
        or sha256(
            loaded["owners/limits-rust-reproduction.json"]
        ).hexdigest()
        != _R3_DAMAGE_SCHEMA_CLARIFIED_RUST_LIMITS_RECEIPT_SHA256
    ):
        raise PolicyError("r3-witness-archive-identity")
    return loaded


def validate_r3_pre_gate6_convergence_archive(
    workspace: Path,
    damage_policy_raw: bytes,
) -> dict[str, bytes]:
    """Admit the exact immutable pre-gate6-convergence archive."""

    if not isinstance(workspace, Path) or type(damage_policy_raw) is not bytes:
        raise PolicyError("r3-convergence-archive-arguments")
    try:
        root = workspace.resolve(strict=True)
    except OSError as error:
        raise PolicyError("r3-convergence-archive-workspace") from error
    if workspace.is_symlink() or not root.is_dir():
        raise PolicyError("r3-convergence-archive-workspace")
    if sha256(damage_policy_raw).hexdigest() != _R3_DAMAGE_V1_SHA256:
        raise PolicyError("r3-convergence-archive-damage-owner")
    damage = _r3_toml_document(
        damage_policy_raw, "golden-board.damage-policy/v1"
    )
    admission = damage.get("admission")
    archive_relative = (
        "artifacts/history/m2-r3-pre-gate6-convergence-clarification"
    )
    manifest_relative = f"{archive_relative}/archive-files.sha256"
    if (
        tuple(damage) != _R3_DAMAGE_TOP_KEYS
        or type(admission) is not dict
        or admission.get("pre_gate6_convergence_archive_root")
        != archive_relative
        or admission.get("pre_gate6_convergence_archive_manifest")
        != manifest_relative
        or admission.get(
            "pre_gate6_convergence_archive_manifest_sha256"
        )
        != _R3_PRE_GATE6_CONVERGENCE_ARCHIVE_MANIFEST_SHA256
        or admission.get("pre_gate6_convergence_archive_scope")
        != (
            "exact-six-file-v7-tree-plus-pre-convergence-clarification-"
            "damage-limits-promotion-and-both-limits-receipts"
        )
        or admission.get("pre_gate6_convergence_candidate_manifest_sha256")
        != "4439abb20aeb4943d9f3dddd4b2b914c08f3a411b791d2ced797533351168019"
        or admission.get("pre_gate6_convergence_candidate_manifest_identity")
        != "69b4052299e43a675683361e6a7fa83798b7b3646c873233cfbdd18432ac4cf4"
        or admission.get("pre_gate6_convergence_damage_policy_sha256")
        != _R3_PRE_GATE6_CONVERGENCE_DAMAGE_V1_SHA256
        or admission.get("pre_gate6_convergence_profile_limits_sha256")
        != _R3_PRE_GATE6_CONVERGENCE_LIMITS_V1_SHA256
        or admission.get("pre_gate6_convergence_promotion_sha256")
        != _R3_PRE_GATE6_CONVERGENCE_PROMOTION_V1_SHA256
        or admission.get(
            "pre_gate6_convergence_python_limits_receipt_sha256"
        )
        != _R3_PRE_GATE6_CONVERGENCE_PYTHON_LIMITS_RECEIPT_SHA256
        or admission.get(
            "pre_gate6_convergence_rust_limits_receipt_sha256"
        )
        != _R3_PRE_GATE6_CONVERGENCE_RUST_LIMITS_RECEIPT_SHA256
        or admission.get("pre_gate6_convergence_reuse")
        != "history-only-never-current-r3-gate-damage-or-proof-input"
        or admission.get("canonical_regeneration_precondition")
        != (
            "all-four-owned-eleven-file-archive-manifests-exist-match-and-"
            "verify-and-the-canonical-v7-candidate-path-is-absent"
        )
    ):
        raise PolicyError("r3-convergence-archive-owner")
    artifacts = root / "artifacts"
    history = artifacts / "history"
    archive = history / "m2-r3-pre-gate6-convergence-clarification"
    candidate = archive / "eh72-hier-r5-r2-r1-crc32c-v0"
    owners = archive / "owners"
    if any(
        path.is_symlink() or not path.is_dir()
        for path in (artifacts, history, archive, candidate, owners)
    ):
        raise PolicyError("r3-convergence-archive-path")
    manifest_path = archive / "archive-files.sha256"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PolicyError("r3-convergence-archive-manifest")
    manifest_stat = manifest_path.stat()
    manifest_raw = manifest_path.read_bytes()
    if (
        manifest_stat.st_nlink != 1
        or not 1 <= len(manifest_raw) <= 16_384
        or len(manifest_raw) != manifest_stat.st_size
        or not manifest_raw.endswith(b"\n")
        or sha256(manifest_raw).hexdigest()
        != _R3_PRE_GATE6_CONVERGENCE_ARCHIVE_MANIFEST_SHA256
    ):
        raise PolicyError("r3-convergence-archive-manifest")
    try:
        lines = manifest_raw.decode("ascii").splitlines()
    except UnicodeError as error:
        raise PolicyError("r3-convergence-archive-manifest") from error
    rows: dict[str, str] = {}
    for line in lines:
        digest, separator, relative = line.partition("  ")
        parts = relative.split("/")
        if (
            separator != "  "
            or len(digest) != 64
            or any(
                character not in "0123456789abcdef" for character in digest
            )
            or relative not in _R3_PRE_CLARIFICATION_ARCHIVE_PATHS
            or relative in rows
            or any(part in ("", ".", "..") for part in parts)
            or "\\" in relative
        ):
            raise PolicyError("r3-convergence-archive-manifest")
        rows[relative] = digest
    if set(rows) != _R3_PRE_CLARIFICATION_ARCHIVE_PATHS:
        raise PolicyError("r3-convergence-archive-manifest")
    try:
        root_entries = {path.name: path for path in archive.iterdir()}
        candidate_entries = {path.name: path for path in candidate.iterdir()}
        owner_entries = {path.name: path for path in owners.iterdir()}
    except OSError as error:
        raise PolicyError("r3-convergence-archive-files") from error
    if (
        set(root_entries)
        != {
            "archive-files.sha256",
            "eh72-hier-r5-r2-r1-crc32c-v0",
            "owners",
        }
        or set(candidate_entries)
        != {
            Path(path).name
            for path in _R3_PRE_CLARIFICATION_ARCHIVE_PATHS
            if path.startswith("eh72-")
        }
        or set(owner_entries)
        != {
            Path(path).name
            for path in _R3_PRE_CLARIFICATION_ARCHIVE_PATHS
            if path.startswith("owners/")
        }
    ):
        raise PolicyError("r3-convergence-archive-files")
    loaded: dict[str, bytes] = {}
    identities: set[tuple[int, int]] = {
        (manifest_stat.st_dev, manifest_stat.st_ino)
    }
    total = 0
    for relative, digest in rows.items():
        path = archive / relative
        if path.is_symlink() or not path.is_file():
            raise PolicyError("r3-convergence-archive-file")
        stat = path.stat()
        file_identity = (stat.st_dev, stat.st_ino)
        if (
            stat.st_nlink != 1
            or file_identity in identities
            or not 1 <= stat.st_size <= 1_048_576
        ):
            raise PolicyError("r3-convergence-archive-file")
        identities.add(file_identity)
        raw = path.read_bytes()
        total += len(raw)
        if len(raw) != stat.st_size or sha256(raw).hexdigest() != digest:
            raise PolicyError("r3-convergence-archive-file")
        loaded[relative] = raw
    if total > 4_194_304:
        raise PolicyError("r3-convergence-archive-file")
    candidate_name = (
        "eh72-hier-r5-r2-r1-crc32c-v0/candidate-manifest.json"
    )
    try:
        archived_candidate = canonical_manifest.validate_canonical_manifest(
            loaded[candidate_name]
        )
    except canonical_manifest.ManifestError as error:
        raise PolicyError("r3-convergence-archive-candidate") from error
    if (
        sha256(loaded[candidate_name]).hexdigest()
        != admission["pre_gate6_convergence_candidate_manifest_sha256"]
        or archived_candidate.get("manifest_identity")
        != admission["pre_gate6_convergence_candidate_manifest_identity"]
        or archived_candidate.get("profile_limits_sha256")
        != admission["pre_gate6_convergence_profile_limits_sha256"]
        or sha256(loaded["owners/damage-policy-v1.toml"]).hexdigest()
        != _R3_PRE_GATE6_CONVERGENCE_DAMAGE_V1_SHA256
        or sha256(loaded["owners/profile-limits-v1.toml"]).hexdigest()
        != _R3_PRE_GATE6_CONVERGENCE_LIMITS_V1_SHA256
        or sha256(
            loaded["owners/m2-r3-owner-promotion-v1.toml"]
        ).hexdigest()
        != _R3_PRE_GATE6_CONVERGENCE_PROMOTION_V1_SHA256
        or sha256(
            loaded["owners/limits-python-reproduction.json"]
        ).hexdigest()
        != _R3_PRE_GATE6_CONVERGENCE_PYTHON_LIMITS_RECEIPT_SHA256
        or sha256(
            loaded["owners/limits-rust-reproduction.json"]
        ).hexdigest()
        != _R3_PRE_GATE6_CONVERGENCE_RUST_LIMITS_RECEIPT_SHA256
    ):
        raise PolicyError("r3-convergence-archive-identity")
    return loaded


_R3_PROFILE_TOP_KEYS = (
    "schema",
    "policy_version",
    "status_authority",
    "base",
    "bindings",
    "promotion_barrier",
    "promotion_generated_schema",
    "generated",
    "candidate_set",
    "registry_profile",
    "registry",
    "transport",
    "check",
    "profile",
    "protection_class",
    "capacity",
    "geometry",
    "mapping",
    "resource_policy",
    "selection",
    "lower_bound",
    "manifestation",
    "candidate_manifest",
    "ownership_ledger",
    "capacity_ledger",
    "profile_limits",
    "metric_row",
    "selection_row",
    "admission",
)
_R3_PRE_GATE6_CONVERGENCE_DAMAGE_TOP_KEYS = (
    "schema",
    "policy_version",
    "status_authority",
    "profile_policy_path",
    "profile_policy_sha256",
    "bootstrap_path",
    "bootstrap_sha256",
    "owner_kat_path",
    "owner_kat_sha256",
    "base",
    "promotion_barrier",
    "promotion_generated_schema",
    "generated",
    "common",
    "inherited_exact",
    "d3",
    "d4",
    "d5",
    "d6",
    "d7",
    "d7_count_reconciliation",
    "boundary_kat",
    "state",
    "reject",
    "decoder",
    "decoder_result",
    "damage_manifest",
    "case_identity",
    "independence_manifest",
    "family_manifest",
    "case_shard_manifest",
    "artifact_bundle",
    "artifact_schema_refreeze",
    "independence_witness_refreeze",
    "admission",
)
_R3_DAMAGE_TOP_KEYS = (
    _R3_PRE_GATE6_CONVERGENCE_DAMAGE_TOP_KEYS[:-1]
    + ("gate6_convergence_refreeze", "admission")
)
_R3_DAMAGE_SCHEMA_CLARIFIED_TOP_KEYS = (
    "schema",
    "policy_version",
    "status_authority",
    "profile_policy_path",
    "profile_policy_sha256",
    "bootstrap_path",
    "bootstrap_sha256",
    "owner_kat_path",
    "owner_kat_sha256",
    "base",
    "promotion_barrier",
    "promotion_generated_schema",
    "generated",
    "common",
    "inherited_exact",
    "d3",
    "d4",
    "d5",
    "d6",
    "d7",
    "d7_count_reconciliation",
    "boundary_kat",
    "state",
    "reject",
    "decoder",
    "decoder_result",
    "damage_manifest",
    "case_identity",
    "independence_manifest",
    "family_manifest",
    "case_shard_manifest",
    "artifact_bundle",
    "artifact_schema_refreeze",
    "admission",
)
_R3_PRE_SCHEMA_DAMAGE_TOP_KEYS = (
    "schema",
    "policy_version",
    "status_authority",
    "profile_policy_path",
    "profile_policy_sha256",
    "bootstrap_path",
    "bootstrap_sha256",
    "owner_kat_path",
    "owner_kat_sha256",
    "base",
    "promotion_barrier",
    "promotion_generated_schema",
    "generated",
    "common",
    "inherited_exact",
    "d3",
    "d4",
    "d5",
    "d6",
    "d7",
    "d7_count_reconciliation",
    "boundary_kat",
    "state",
    "decoder",
    "decoder_result",
    "damage_manifest",
    "case_identity",
    "independence_manifest",
    "admission",
)
_R3_PROMOTION_TOP_KEYS = (
    "schema",
    "status",
    "active_candidate_id",
    "active_profile_version",
    "damage_observation_authorized",
    "r2_evidence",
    "draft_owner",
    "generated_owner",
    "algebraic_binding",
    "freeze_barrier",
    "promotion_render",
    "admission",
)

_R3_LIMITS_TOP_KEYS = (
    "schema",
    "generation",
    "profile_policy_sha256",
    "damage_policy_sha256",
    "bootstrap_spec_sha256",
    "route_data_sha256",
    "capacity_module_sha256",
    "slice_semantic_sha256",
    "profile_ids",
    "policy_ceiling",
    "semantic_capacity",
    "selected_manifestation",
    "transport",
    "route_package",
    "damage",
    "content",
    "profile",
)


def load_r3_decoder_policy(
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    damage_policy_raw: bytes,
) -> R3DecoderPolicy:
    """Admit the exact promoted v1 registry and logical resource projection.

    The observation-only decoder deliberately receives neither a candidate
    manifestation nor route bytes.  This loader therefore exposes only the
    hash-bound registry, generated transport limits, and resource rows needed
    to enumerate an observation.  Archived v0 owners continue through their
    existing loaders and cannot be mixed with this projection.
    """

    if (
        type(profile_policy_raw) is not bytes
        or type(profile_limits_raw) is not bytes
        or type(damage_policy_raw) is not bytes
        or sha256(profile_policy_raw).hexdigest() != _R3_PROFILE_V1_SHA256
        or sha256(profile_limits_raw).hexdigest()
        != _R3_PROFILE_LIMITS_V1_SHA256
        or sha256(damage_policy_raw).hexdigest() != _R3_DAMAGE_V1_SHA256
    ):
        raise PolicyError("r3-decoder-owner-identity")
    profile = _r3_toml_document(
        profile_policy_raw, "golden-board.profile-policy/v1"
    )
    limits = _r3_toml_document(
        profile_limits_raw, "golden-board.profile-limits/v1"
    )
    damage = _r3_toml_document(
        damage_policy_raw, "golden-board.damage-policy/v1"
    )
    if (
        tuple(profile) != _R3_PROFILE_TOP_KEYS
        or tuple(limits) != _R3_LIMITS_TOP_KEYS
        or tuple(damage) != _R3_DAMAGE_TOP_KEYS
        or limits.get("profile_policy_sha256") != _R3_PROFILE_V1_SHA256
        or limits.get("damage_policy_sha256") != _R3_DAMAGE_V1_SHA256
        or profile.get("generated", {}).get("route_data_sha256")
        != _R3_ROUTE_V1_SHA256
        or damage.get("generated", {}).get("route_data_sha256")
        != _R3_ROUTE_V1_SHA256
        or limits.get("route_data_sha256") != _R3_ROUTE_V1_SHA256
    ):
        raise PolicyError("r3-decoder-owner-binding")

    registry_rows = profile.get("registry_profile")
    expected_registry = (
        (
            "eh72-hier-r5-r2-r1-crc32c-v0",
            7,
            "eh72-hier-repetition-v0",
            "crc32c-v0",
            True,
            False,
            True,
        ),
        (
            "eh72-r2-crc64-ecma-v0",
            2,
            "eh72-replicated-v0",
            "crc64-ecma-v0",
            False,
            True,
            False,
        ),
        (
            "eh72-r3-crc32c-v0",
            3,
            "eh72-replicated-v0",
            "crc32c-v0",
            False,
            True,
            False,
        ),
        (
            "eh72-r3-crc64-ecma-v0",
            4,
            "eh72-replicated-v0",
            "crc64-ecma-v0",
            False,
            True,
            False,
        ),
        (
            "rs255-191-crc32c-v0",
            5,
            "rs255-191-v0",
            "crc32c-v0",
            False,
            True,
            False,
        ),
        (
            "rs255-191-crc64-ecma-v0",
            6,
            "rs255-191-v0",
            "crc64-ecma-v0",
            False,
            True,
            False,
        ),
    )
    registry_keys = (
        "id",
        "profile_version",
        "transport_id",
        "section_check_id",
        "candidate",
        "fixture",
        "may_establish_r3_artifact",
    )
    if (
        type(registry_rows) is not list
        or any(
            type(row) is not dict or tuple(row) != registry_keys
            for row in registry_rows
        )
        or tuple(tuple(row[key] for key in registry_keys) for row in registry_rows)
        != expected_registry
        or profile.get("registry", {}).get("order") != [7, 2, 3, 4, 5, 6]
    ):
        raise PolicyError("r3-decoder-registry")

    active_rows = profile.get("profile")
    limit_rows = limits.get("profile")
    if (
        type(active_rows) is not list
        or len(active_rows) != 1
        or active_rows[0]
        != {
            "id": "eh72-hier-r5-r2-r1-crc32c-v0",
            "profile_version": 7,
            "transport_id": "eh72-hier-repetition-v0",
            "section_check_id": "crc32c-v0",
            "semantic_copy_count": 1,
            "complexity_class": 1,
            "map_id": "affine-slot-then-interior-v1",
        }
        or type(limit_rows) is not list
        or len(limit_rows) != 1
        or type(limit_rows[0]) is not dict
    ):
        raise PolicyError("r3-decoder-profile")
    limit = limit_rows[0]
    protected_units = _integer(limit, "protected_units", 1)
    encoded_transport_bytes = _integer(
        limit, "encoded_transport_bytes", 1
    )
    if (
        limit.get("id") != expected_registry[0][0]
        or limit.get("profile_version") != 7
        or limit.get("check_bytes") != 4
        or limit.get("semantic_copy_count") != 1
        or limit.get("physical_replica_counts") != [1, 2, 5]
        or limit.get("protected_unit_bytes") != 216
        or encoded_transport_bytes != protected_units * 216
        or limits.get("profile_ids") != [expected_registry[0][0]]
        or profile.get("generated", {}).get("physical_unit_count")
        != protected_units
        or profile.get("generated", {}).get("encoded_transport_bytes")
        != encoded_transport_bytes
        or limits.get("selected_manifestation", {}).get("physical_unit_count")
        != protected_units
        or limits.get("selected_manifestation", {}).get(
            "encoded_transport_bytes"
        )
        != encoded_transport_bytes
    ):
        raise PolicyError("r3-decoder-profile")

    fixture_rows = damage.get("decoder", {}).get(
        "fixture_resource_profile"
    )
    resource_keys = (
        "profile_version",
        "profile_id",
        "recipient_package_sha256",
        "decoder_30_primitive_steps",
        "decoder_30_peak_scratch_bytes",
    )
    if (
        type(fixture_rows) is not list
        or any(
            type(row) is not dict or tuple(row) != resource_keys
            for row in fixture_rows
        )
    ):
        raise PolicyError("r3-decoder-resource")
    fixture_resources = tuple(
        (
            _integer(row, "profile_version", 1),
            row.get("profile_id"),
            row.get("recipient_package_sha256"),
            _integer(row, "decoder_30_primitive_steps", 1),
            _integer(row, "decoder_30_peak_scratch_bytes", 1),
        )
        for row in fixture_rows
    )
    if fixture_resources != _OBS_UNITS_RESOURCE_PROFILES[1:]:
        raise PolicyError("r3-decoder-resource")
    generated = damage.get("generated")
    if type(generated) is not dict:
        raise PolicyError("r3-decoder-resource")
    v7_resource = (
        7,
        expected_registry[0][0],
        generated.get("recipient_package_sha256"),
        _integer(generated, "v7_decoder_30_primitive_steps", 1),
        _integer(generated, "v7_decoder_30_peak_scratch_bytes", 1),
    )
    repetition_steps = _integer(
        generated, "repetition_113_primitive_steps", 1
    )
    repetition_scratch = _integer(
        generated, "repetition_113_peak_scratch_bytes", 1
    )
    if (
        v7_resource[2]
        != profile.get("generated", {}).get("recipient_package_sha256")
        or v7_resource[2]
        != limits.get("route_package", {}).get("recipient_package_sha256")
        or v7_resource[3] != limits.get("route_package", {}).get(
            "recipient_package_primitive_steps"
        )
        or damage.get("decoder", {}).get("registry_profile_order")
        != [7, 2, 3, 4, 5, 6]
    ):
        raise PolicyError("r3-decoder-resource")

    profile_shapes = (
        (expected_registry[0], 4, 1, 1, 216),
        (expected_registry[1], 8, 2, 1, 216),
        (expected_registry[2], 4, 3, 1, 216),
        (expected_registry[3], 8, 3, 1, 216),
        (expected_registry[4], 4, 2, 2, 255),
        (expected_registry[5], 8, 2, 2, 255),
    )
    projected_profiles = tuple(
        ProfileTuple(
            registry[0],
            registry[1],
            registry[2],
            check_bytes,
            copies,
            unit_bytes,
            complexity,
        )
        for registry, check_bytes, copies, complexity, unit_bytes in profile_shapes
    )
    return R3DecoderPolicy(
        _R3_PROFILE_V1_SHA256,
        _R3_DAMAGE_V1_SHA256,
        _R3_PROFILE_LIMITS_V1_SHA256,
        projected_profiles,
        protected_units,
        encoded_transport_bytes,
        (v7_resource,) + fixture_resources,
        repetition_steps,
        repetition_scratch,
    )


def _load_r3_promoted_owner_set(
    bundle: R3PromotionWriteBundle,
    bootstrap_spec_raw: bytes,
    owner_fixture_raw: bytes,
    python_route_receipt_raw: bytes,
    rust_route_receipt_raw: bytes,
    python_limits_receipt_raw: bytes,
    rust_limits_receipt_raw: bytes,
    expected_promotion_sha256: str,
) -> R3PromotedOwnerSet:
    """Strictly admit one explicitly pinned complete cross-hashed owner set."""

    if (
        type(bundle) is not R3PromotionWriteBundle
        or type(expected_promotion_sha256) is not str
        or len(expected_promotion_sha256) != 64
    ):
        raise PolicyError("r3-owner-bundle")
    hashes = {
        "spec/bootstrap-v1.md": sha256(bootstrap_spec_raw).hexdigest(),
        "spec/profile-policy-v1.toml": sha256(bundle.profile_policy).hexdigest(),
        "spec/damage-policy-v1.toml": sha256(bundle.damage_policy).hexdigest(),
        "conformance/m2-r3-owner-v1.json": sha256(owner_fixture_raw).hexdigest(),
        "spec/route-data-v1.json": sha256(bundle.route_data).hexdigest(),
        "spec/profile-limits-v1.toml": sha256(bundle.profile_limits).hexdigest(),
    }
    if (
        sha256(bundle.promotion_manifest).hexdigest()
        != expected_promotion_sha256
    ):
        raise PolicyError("r3-promotion-identity")
    profile = _r3_toml_document(
        bundle.profile_policy, "golden-board.profile-policy/v1"
    )
    damage = _r3_toml_document(
        bundle.damage_policy, "golden-board.damage-policy/v1"
    )
    limits = _r3_toml_document(
        bundle.profile_limits, "golden-board.profile-limits/v1"
    )
    promotion = _r3_toml_document(
        bundle.promotion_manifest,
        "golden-board.m2-r3-owner-promotion/v1",
    )
    route = _r3_complete_route_document(bundle.route_data)
    damage_sha256 = hashes["spec/damage-policy-v1.toml"]
    damage_top_keys = (
        _R3_DAMAGE_TOP_KEYS
        if damage_sha256 == _R3_DAMAGE_V1_SHA256
        else _R3_PRE_GATE6_CONVERGENCE_DAMAGE_TOP_KEYS
        if damage_sha256 == _R3_PRE_GATE6_CONVERGENCE_DAMAGE_V1_SHA256
        else _R3_DAMAGE_SCHEMA_CLARIFIED_TOP_KEYS
        if damage_sha256 == _R3_DAMAGE_SCHEMA_CLARIFIED_DAMAGE_V1_SHA256
        else _R3_PRE_SCHEMA_DAMAGE_TOP_KEYS
        if damage_sha256
        in {
            _R3_MAPPING_CLARIFIED_DAMAGE_V1_SHA256,
            _R3_PRE_CLARIFICATION_DAMAGE_V1_SHA256,
        }
        else ()
    )
    if (
        tuple(profile) != _R3_PROFILE_TOP_KEYS
        or tuple(damage) != damage_top_keys
        or tuple(promotion) != _R3_PROMOTION_TOP_KEYS
        or promotion.get("status") != "pre-result-frozen"
        or promotion.get("damage_observation_authorized") is not True
        or promotion.get("active_candidate_id")
        != "eh72-hier-r5-r2-r1-crc32c-v0"
        or promotion.get("active_profile_version") != 7
    ):
        raise PolicyError("r3-owner-shape")
    profile_generated = profile.get("generated")
    damage_generated = damage.get("generated")
    if (
        type(profile_generated) is not dict
        or tuple(profile_generated)
        != tuple(profile["promotion_generated_schema"]["key_order"])
        or type(damage_generated) is not dict
        or tuple(damage_generated)
        != tuple(damage["promotion_generated_schema"]["key_order"])
        or tuple(row["profile_version"] for row in profile["registry_profile"])
        != (7, 2, 3, 4, 5, 6)
        or tuple(row["candidate"] for row in profile["registry_profile"])
        != (True, False, False, False, False, False)
        or tuple(row["fixture"] for row in profile["registry_profile"])
        != (False, True, True, True, True, True)
    ):
        raise PolicyError("r3-owner-registry")
    route_generated = route["generated"]
    if (
        profile["bindings"]["bootstrap_sha256"]
        != hashes["spec/bootstrap-v1.md"]
        or damage["bootstrap_sha256"] != hashes["spec/bootstrap-v1.md"]
        or damage["profile_policy_sha256"]
        != hashes["spec/profile-policy-v1.toml"]
        or profile_generated["route_data_sha256"]
        != hashes["spec/route-data-v1.json"]
        or damage_generated["route_data_sha256"]
        != hashes["spec/route-data-v1.json"]
        or profile_generated["recipient_package_sha256"]
        != route_generated["recipient_package_sha256"]
        or damage_generated["recipient_package_sha256"]
        != route_generated["recipient_package_sha256"]
        or limits["bootstrap_spec_sha256"] != hashes["spec/bootstrap-v1.md"]
        or limits["profile_policy_sha256"]
        != hashes["spec/profile-policy-v1.toml"]
        or limits["damage_policy_sha256"]
        != hashes["spec/damage-policy-v1.toml"]
        or limits["route_data_sha256"] != hashes["spec/route-data-v1.json"]
    ):
        raise PolicyError("r3-owner-binding")
    draft_rows = promotion.get("draft_owner")
    generated_rows = promotion.get("generated_owner")
    if (
        type(draft_rows) is not list
        or tuple((row.get("path"), row.get("sha256")) for row in draft_rows)
        != tuple(
            (path, hashes[path])
            for path in (
                "spec/bootstrap-v1.md",
                "spec/profile-policy-v1.toml",
                "spec/damage-policy-v1.toml",
                "conformance/m2-r3-owner-v1.json",
            )
        )
        or type(generated_rows) is not list
        or tuple((row.get("path"), row.get("sha256"), row.get("state")) for row in generated_rows)
        != (
            (
                "spec/route-data-v1.json",
                hashes["spec/route-data-v1.json"],
                "independently-reproduced",
            ),
            (
                "spec/profile-limits-v1.toml",
                hashes["spec/profile-limits-v1.toml"],
                "independently-reproduced",
            ),
        )
    ):
        raise PolicyError("r3-promotion-owner")
    if (
        generated_rows[0].get("python_reproduction_sha256")
        != sha256(python_route_receipt_raw).hexdigest()
        or generated_rows[0].get("rust_reproduction_sha256")
        != sha256(rust_route_receipt_raw).hexdigest()
        or route_generated["python_reproduction_sha256"]
        != sha256(python_route_receipt_raw).hexdigest()
        or route_generated["rust_reproduction_sha256"]
        != sha256(rust_route_receipt_raw).hexdigest()
        or generated_rows[1].get("python_reproduction_sha256")
        != sha256(python_limits_receipt_raw).hexdigest()
        or generated_rows[1].get("rust_reproduction_sha256")
        != sha256(rust_limits_receipt_raw).hexdigest()
        or python_limits_receipt_raw
        != render_r3_limits_reproduction_receipt(
            "python", bundle.profile_limits, bundle.route_data
        )
        or rust_limits_receipt_raw
        != render_r3_limits_reproduction_receipt(
            "rust", bundle.profile_limits, bundle.route_data
        )
    ):
        raise PolicyError("r3-owner-receipt")
    return R3PromotedOwnerSet(
        hashes["spec/bootstrap-v1.md"],
        hashes["spec/profile-policy-v1.toml"],
        hashes["spec/damage-policy-v1.toml"],
        hashes["spec/route-data-v1.json"],
        hashes["spec/profile-limits-v1.toml"],
        expected_promotion_sha256,
    )


def load_r3_promoted_owner_set(
    bundle: R3PromotionWriteBundle,
    bootstrap_spec_raw: bytes,
    owner_fixture_raw: bytes,
    python_route_receipt_raw: bytes,
    rust_route_receipt_raw: bytes,
    python_limits_receipt_raw: bytes,
    rust_limits_receipt_raw: bytes,
) -> R3PromotedOwnerSet:
    """Strictly admit only the current clarified v1 owner set."""

    admitted = _load_r3_promoted_owner_set(
        bundle,
        bootstrap_spec_raw,
        owner_fixture_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
        _R3_PROMOTION_V1_SHA256,
    )
    if (
        admitted.profile_policy_sha256 != _R3_PROFILE_V1_SHA256
        or admitted.damage_policy_sha256 != _R3_DAMAGE_V1_SHA256
        or admitted.route_data_sha256 != _R3_ROUTE_V1_SHA256
        or admitted.profile_limits_sha256 != _R3_PROFILE_LIMITS_V1_SHA256
    ):
        raise PolicyError("r3-owner-identity")
    return admitted


def _load_r3_mapping_clarified_owner_set(
    bundle: R3PromotionWriteBundle,
    bootstrap_spec_raw: bytes,
    owner_fixture_raw: bytes,
    python_route_receipt_raw: bytes,
    rust_route_receipt_raw: bytes,
    python_limits_receipt_raw: bytes,
    rust_limits_receipt_raw: bytes,
) -> R3PromotedOwnerSet:
    """Admit the exact historical post-mapping/pre-schema owner tuple."""

    admitted = _load_r3_promoted_owner_set(
        bundle,
        bootstrap_spec_raw,
        owner_fixture_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
        _R3_MAPPING_CLARIFIED_PROMOTION_V1_SHA256,
    )
    if (
        admitted.profile_policy_sha256 != _R3_PROFILE_V1_SHA256
        or admitted.damage_policy_sha256
        != _R3_MAPPING_CLARIFIED_DAMAGE_V1_SHA256
        or admitted.route_data_sha256 != _R3_ROUTE_V1_SHA256
        or admitted.profile_limits_sha256
        != _R3_MAPPING_CLARIFIED_LIMITS_V1_SHA256
    ):
        raise PolicyError("r3-mapping-owner-identity")
    return admitted


def _load_r3_damage_schema_clarified_owner_set(
    bundle: R3PromotionWriteBundle,
    bootstrap_spec_raw: bytes,
    owner_fixture_raw: bytes,
    python_route_receipt_raw: bytes,
    rust_route_receipt_raw: bytes,
    python_limits_receipt_raw: bytes,
    rust_limits_receipt_raw: bytes,
) -> R3PromotedOwnerSet:
    """Admit the exact historical post-schema/pre-witness owner tuple."""

    admitted = _load_r3_promoted_owner_set(
        bundle,
        bootstrap_spec_raw,
        owner_fixture_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
        _R3_DAMAGE_SCHEMA_CLARIFIED_PROMOTION_V1_SHA256,
    )
    if (
        admitted.profile_policy_sha256 != _R3_PROFILE_V1_SHA256
        or admitted.damage_policy_sha256
        != _R3_DAMAGE_SCHEMA_CLARIFIED_DAMAGE_V1_SHA256
        or admitted.route_data_sha256 != _R3_ROUTE_V1_SHA256
        or admitted.profile_limits_sha256
        != _R3_DAMAGE_SCHEMA_CLARIFIED_LIMITS_V1_SHA256
    ):
        raise PolicyError("r3-damage-schema-owner-identity")
    return admitted


def _load_r3_pre_gate6_convergence_owner_set(
    bundle: R3PromotionWriteBundle,
    bootstrap_spec_raw: bytes,
    owner_fixture_raw: bytes,
    python_route_receipt_raw: bytes,
    rust_route_receipt_raw: bytes,
    python_limits_receipt_raw: bytes,
    rust_limits_receipt_raw: bytes,
) -> R3PromotedOwnerSet:
    """Admit the exact historical post-witness/pre-convergence owner tuple."""

    admitted = _load_r3_promoted_owner_set(
        bundle,
        bootstrap_spec_raw,
        owner_fixture_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
        _R3_PRE_GATE6_CONVERGENCE_PROMOTION_V1_SHA256,
    )
    if (
        admitted.profile_policy_sha256 != _R3_PROFILE_V1_SHA256
        or admitted.damage_policy_sha256
        != _R3_PRE_GATE6_CONVERGENCE_DAMAGE_V1_SHA256
        or admitted.route_data_sha256 != _R3_ROUTE_V1_SHA256
        or admitted.profile_limits_sha256
        != _R3_PRE_GATE6_CONVERGENCE_LIMITS_V1_SHA256
    ):
        raise PolicyError("r3-convergence-owner-identity")
    return admitted


def _r3_artifacts_absent(workspace: Path) -> bool:
    candidate = (
        workspace
        / "artifacts/candidates/eh72-hier-r5-r2-r1-crc32c-v0"
    )
    if candidate.exists() or candidate.is_symlink():
        return False
    markers = (
        b"eh72-hier-r5-r2-r1-crc32c-v0",
        b'"profile_version":7',
        b"profile_version = 7",
    )
    count = 0
    total = 0
    for root_name in ("artifacts", "reports"):
        root = workspace / root_name
        if not root.exists():
            continue
        if root.is_symlink() or not root.is_dir():
            return False
        for path in root.rglob("*"):
            count += 1
            if count > 100_000:
                raise PolicyError("r3-artifact-scan-limit")
            if path.is_symlink():
                return False
            if path.is_dir():
                continue
            if not path.is_file():
                return False
            size = path.stat().st_size
            total += size
            if total > 2_147_483_648:
                raise PolicyError("r3-artifact-scan-limit")
            if size <= 16_777_216:
                raw = path.read_bytes()
                if any(marker in raw for marker in markers):
                    return False
    return True


def apply_r3_promotion_bundle(
    workspace: Path,
    bundle: R3PromotionWriteBundle,
    blocked_profile_policy_raw: bytes | None,
    blocked_damage_policy_raw: bytes | None,
    blocked_promotion_raw: bytes | None,
    bootstrap_spec_raw: bytes,
    owner_fixture_raw: bytes,
    python_route_receipt_raw: bytes,
    rust_route_receipt_raw: bytes,
    python_limits_receipt_raw: bytes,
    rust_limits_receipt_raw: bytes,
    rust_stage_directory: Path | None,
    python_comparison_files: dict[str, bytes] | None,
    *,
    dry_run: bool,
) -> str:
    """Stage, validate, and optionally install only the frozen five-file set."""

    if (
        not isinstance(workspace, Path)
        or type(bundle) is not R3PromotionWriteBundle
        or type(dry_run) is not bool
        or any(
            type(raw) is not bytes
            for raw in (
                bootstrap_spec_raw,
                owner_fixture_raw,
                python_route_receipt_raw,
                rust_route_receipt_raw,
                python_limits_receipt_raw,
                rust_limits_receipt_raw,
            )
        )
        or any(
            raw is not None and type(raw) is not bytes
            for raw in (
                blocked_profile_policy_raw,
                blocked_damage_policy_raw,
                blocked_promotion_raw,
            )
        )
        or (
            rust_stage_directory is not None
            and not isinstance(rust_stage_directory, Path)
        )
        or (
            python_comparison_files is not None
            and type(python_comparison_files) is not dict
        )
    ):
        raise PolicyError("r3-apply-arguments")
    try:
        root = workspace.resolve(strict=True)
    except OSError as error:
        raise PolicyError("r3-apply-workspace") from error
    destinations = {
        "profile-policy-v1.toml": root / "spec/profile-policy-v1.toml",
        "damage-policy-v1.toml": root / "spec/damage-policy-v1.toml",
        "route-data-v1.json": root / "spec/route-data-v1.json",
        "profile-limits-v1.toml": root / "spec/profile-limits-v1.toml",
        "m2-r3-owner-promotion-v1.toml": root
        / "spec/m2-r3-owner-promotion-v1.toml",
    }
    outputs = {
        "profile-policy-v1.toml": bundle.profile_policy,
        "damage-policy-v1.toml": bundle.damage_policy,
        "route-data-v1.json": bundle.route_data,
        "profile-limits-v1.toml": bundle.profile_limits,
        "m2-r3-owner-promotion-v1.toml": bundle.promotion_manifest,
    }
    spec_directory = root / "spec"
    conformance_directory = root / "conformance"
    if (
        workspace.is_symlink()
        or spec_directory.is_symlink()
        or not spec_directory.is_dir()
        or conformance_directory.is_symlink()
        or not conformance_directory.is_dir()
    ):
        raise PolicyError("r3-apply-workspace")
    bootstrap_path = spec_directory / "bootstrap-v1.md"
    fixture_path = root / "conformance/m2-r3-owner-v1.json"
    if (
        bootstrap_path.is_symlink()
        or fixture_path.is_symlink()
        or not bootstrap_path.is_file()
        or not fixture_path.is_file()
        or bootstrap_path.read_bytes() != bootstrap_spec_raw
        or fixture_path.read_bytes() != owner_fixture_raw
    ):
        raise PolicyError("r3-apply-input")
    admitted = _load_r3_promoted_owner_set(
        bundle,
        bootstrap_spec_raw,
        owner_fixture_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
        _R3_PRE_CLARIFICATION_PROMOTION_V1_SHA256,
    )
    current = {}
    destination_identities: set[tuple[int, int]] = set()
    for name, path in destinations.items():
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise PolicyError("r3-apply-destination")
        if path.is_file():
            stat = path.stat()
            identity = (stat.st_dev, stat.st_ino)
            if identity in destination_identities:
                raise PolicyError("r3-apply-destination-alias")
            destination_identities.add(identity)
        current[name] = path.read_bytes() if path.is_file() else None
    if all(current[name] == outputs[name] for name in outputs):
        _r3_toml_document(
            bundle.profile_policy, "golden-board.profile-policy/v1"
        )
        _r3_toml_document(
            bundle.damage_policy, "golden-board.damage-policy/v1"
        )
        _r3_complete_route_document(bundle.route_data)
        _r3_toml_document(
            bundle.profile_limits, "golden-board.profile-limits/v1"
        )
        if sha256(bundle.promotion_manifest).hexdigest() != admitted.promotion_sha256:
            raise PolicyError("r3-apply-postcondition")
        return "already-applied"
    if rust_stage_directory is None or python_comparison_files is None:
        raise PolicyError("r3-apply-rust-stage")
    stage_route_receipt, stage_limits_receipt = validate_r3_rust_stage(
        rust_stage_directory,
        _R3_RUST_STAGE_MANIFEST_SHA256,
        python_comparison_files,
    )
    if (
        stage_route_receipt != rust_route_receipt_raw
        or stage_limits_receipt != rust_limits_receipt_raw
    ):
        raise PolicyError("r3-apply-rust-stage")
    if any(
        type(raw) is not bytes
        for raw in (
            blocked_profile_policy_raw,
            blocked_damage_policy_raw,
            blocked_promotion_raw,
        )
    ):
        raise PolicyError("r3-apply-blocked-input")
    blocked_documents = (
        (
            blocked_profile_policy_raw,
            _R3_BLOCKED_PROFILE_V1_SHA256,
            "golden-board.profile-policy/v1",
        ),
        (
            blocked_damage_policy_raw,
            _R3_BLOCKED_DAMAGE_V1_SHA256,
            "golden-board.damage-policy/v1",
        ),
        (
            blocked_promotion_raw,
            _R3_BLOCKED_PROMOTION_V1_SHA256,
            "golden-board.m2-r3-owner-promotion/v1",
        ),
    )
    parsed_blocked = []
    for raw, expected_sha256, schema in blocked_documents:
        if sha256(raw).hexdigest() != expected_sha256:
            raise PolicyError("r3-apply-blocked-input")
        parsed_blocked.append(_r3_toml_document(raw, schema))
    if (
        "generated" in parsed_blocked[0]
        or "generated" in parsed_blocked[1]
        or parsed_blocked[2].get("status") != "blocked"
        or parsed_blocked[2].get("damage_observation_authorized") is not False
    ):
        raise PolicyError("r3-apply-blocked-input")
    expected_profile = render_r3_promoted_profile_policy(
        blocked_profile_policy_raw, bootstrap_spec_raw, bundle.route_data
    )
    expected_damage = render_r3_promoted_damage_policy(
        blocked_damage_policy_raw,
        bootstrap_spec_raw,
        expected_profile,
        bundle.route_data,
    )
    expected_promotion = render_r3_promotion_manifest(
        blocked_promotion_raw,
        bootstrap_spec_raw,
        expected_profile,
        expected_damage,
        owner_fixture_raw,
        bundle.route_data,
        bundle.profile_limits,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
    )
    if (
        expected_profile != bundle.profile_policy
        or expected_damage != bundle.damage_policy
        or expected_promotion != bundle.promotion_manifest
    ):
        raise PolicyError("r3-apply-render")
    if (
        current["profile-policy-v1.toml"] != blocked_profile_policy_raw
        or current["damage-policy-v1.toml"] != blocked_damage_policy_raw
        or current["m2-r3-owner-promotion-v1.toml"] != blocked_promotion_raw
        or current["route-data-v1.json"] not in (None, outputs["route-data-v1.json"])
        or current["profile-limits-v1.toml"]
        not in (None, outputs["profile-limits-v1.toml"])
        or not _r3_artifacts_absent(root)
    ):
        raise PolicyError("r3-apply-precondition")
    with tempfile.TemporaryDirectory(
        prefix=".r3-promotion-stage-", dir=spec_directory
    ) as temporary:
        stage = Path(temporary)
        for name, raw in outputs.items():
            path = stage / name
            with path.open("wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        directory_fd = os.open(stage, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        staged = R3PromotionWriteBundle(
            (stage / "profile-policy-v1.toml").read_bytes(),
            (stage / "damage-policy-v1.toml").read_bytes(),
            (stage / "route-data-v1.json").read_bytes(),
            (stage / "profile-limits-v1.toml").read_bytes(),
            (stage / "m2-r3-owner-promotion-v1.toml").read_bytes(),
        )
        if staged != bundle:
            raise PolicyError("r3-apply-stage")
        _r3_toml_document(
            staged.profile_policy, "golden-board.profile-policy/v1"
        )
        _r3_toml_document(
            staged.damage_policy, "golden-board.damage-policy/v1"
        )
        _r3_complete_route_document(staged.route_data)
        _r3_toml_document(
            staged.profile_limits, "golden-board.profile-limits/v1"
        )
        if sha256(staged.promotion_manifest).hexdigest() != admitted.promotion_sha256:
            raise PolicyError("r3-apply-stage")
        if dry_run:
            return "dry-run-clean"
        backups = dict(current)
        backup_directory = stage / "backups"
        backup_directory.mkdir(mode=0o700)
        for name, raw in backups.items():
            if raw is None:
                continue
            with (backup_directory / name).open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        directory_fd = os.open(backup_directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        written: list[str] = []
        try:
            # Status authority is replaced last, so any interrupted write stays
            # fail-closed as blocked. Exact partial generated files are accepted
            # on a retry but never authorize a carrier or damage observation.
            non_authority_order = (
                "route-data-v1.json",
                "profile-limits-v1.toml",
                "profile-policy-v1.toml",
                "damage-policy-v1.toml",
            )
            for name in non_authority_order:
                os.replace(stage / name, destinations[name])
                written.append(name)
            directory_fd = os.open(spec_directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            authority = "m2-r3-owner-promotion-v1.toml"
            os.replace(stage / authority, destinations[authority])
            written.append(authority)
            directory_fd = os.open(spec_directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            observed = {
                name: path.read_bytes() for name, path in destinations.items()
            }
            if any(observed[name] != outputs[name] for name in outputs):
                raise PolicyError("r3-apply-postcondition")
            observed_bundle = R3PromotionWriteBundle(
                observed["profile-policy-v1.toml"],
                observed["damage-policy-v1.toml"],
                observed["route-data-v1.json"],
                observed["profile-limits-v1.toml"],
                observed["m2-r3-owner-promotion-v1.toml"],
            )
            _load_r3_promoted_owner_set(
                observed_bundle,
                bootstrap_spec_raw,
                owner_fixture_raw,
                python_route_receipt_raw,
                rust_route_receipt_raw,
                python_limits_receipt_raw,
                rust_limits_receipt_raw,
                _R3_PRE_CLARIFICATION_PROMOTION_V1_SHA256,
            )
        except Exception:
            for name in reversed(written):
                previous = backups[name]
                if previous is None:
                    try:
                        destinations[name].unlink()
                    except FileNotFoundError:
                        pass
                else:
                    os.replace(backup_directory / name, destinations[name])
            directory_fd = os.open(spec_directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            raise
    return "applied"


def apply_r3_mapping_clarification_bundle(
    workspace: Path,
    bundle: R3PromotionWriteBundle,
    bootstrap_spec_raw: bytes,
    owner_fixture_raw: bytes,
    python_route_receipt_raw: bytes,
    rust_route_receipt_raw: bytes,
    python_limits_receipt_raw: bytes,
    rust_limits_receipt_raw: bytes,
    rust_stage_directory: Path | None,
    python_comparison_files: dict[str, bytes] | None,
    *,
    dry_run: bool,
) -> str:
    """Atomically re-freeze only the archived mapping clarification cascade."""

    if (
        not isinstance(workspace, Path)
        or type(bundle) is not R3PromotionWriteBundle
        or type(dry_run) is not bool
        or any(
            type(raw) is not bytes
            for raw in (
                bootstrap_spec_raw,
                owner_fixture_raw,
                python_route_receipt_raw,
                rust_route_receipt_raw,
                python_limits_receipt_raw,
                rust_limits_receipt_raw,
            )
        )
        or (
            rust_stage_directory is not None
            and not isinstance(rust_stage_directory, Path)
        )
        or (
            python_comparison_files is not None
            and type(python_comparison_files) is not dict
        )
    ):
        raise PolicyError("r3-clarification-apply-arguments")
    try:
        root = workspace.resolve(strict=True)
    except OSError as error:
        raise PolicyError("r3-clarification-workspace") from error
    spec_directory = root / "spec"
    conformance_directory = root / "conformance"
    artifacts_directory = root / "artifacts"
    candidates_directory = artifacts_directory / "candidates"
    if (
        workspace.is_symlink()
        or not root.is_dir()
        or spec_directory.is_symlink()
        or not spec_directory.is_dir()
        or conformance_directory.is_symlink()
        or not conformance_directory.is_dir()
        or artifacts_directory.is_symlink()
        or not artifacts_directory.is_dir()
        or candidates_directory.is_symlink()
        or (
            candidates_directory.exists()
            and not candidates_directory.is_dir()
        )
    ):
        raise PolicyError("r3-clarification-workspace")
    bootstrap_path = spec_directory / "bootstrap-v1.md"
    fixture_path = conformance_directory / "m2-r3-owner-v1.json"
    if (
        bootstrap_path.is_symlink()
        or not bootstrap_path.is_file()
        or fixture_path.is_symlink()
        or not fixture_path.is_file()
        or bootstrap_path.read_bytes() != bootstrap_spec_raw
        or fixture_path.read_bytes() != owner_fixture_raw
    ):
        raise PolicyError("r3-clarification-input")
    admitted = _load_r3_mapping_clarified_owner_set(
        bundle,
        bootstrap_spec_raw,
        owner_fixture_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
    )
    destinations = {
        "profile-policy-v1.toml": spec_directory / "profile-policy-v1.toml",
        "damage-policy-v1.toml": spec_directory / "damage-policy-v1.toml",
        "route-data-v1.json": spec_directory / "route-data-v1.json",
        "profile-limits-v1.toml": spec_directory / "profile-limits-v1.toml",
        "m2-r3-owner-promotion-v1.toml": (
            spec_directory / "m2-r3-owner-promotion-v1.toml"
        ),
    }
    final = {
        "profile-policy-v1.toml": bundle.profile_policy,
        "damage-policy-v1.toml": bundle.damage_policy,
        "route-data-v1.json": bundle.route_data,
        "profile-limits-v1.toml": bundle.profile_limits,
        "m2-r3-owner-promotion-v1.toml": bundle.promotion_manifest,
    }
    current: dict[str, bytes] = {}
    identities: set[tuple[int, int]] = set()
    for name, path in destinations.items():
        if path.is_symlink() or not path.is_file():
            raise PolicyError("r3-clarification-destination")
        stat = path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if identity in identities:
            raise PolicyError("r3-clarification-destination-alias")
        identities.add(identity)
        current[name] = path.read_bytes()
    archived = validate_r3_pre_clarification_archive(
        root, bundle.damage_policy
    )
    archived_bundle = R3PromotionWriteBundle(
        bundle.profile_policy,
        archived["owners/damage-policy-v1.toml"],
        bundle.route_data,
        archived["owners/profile-limits-v1.toml"],
        archived["owners/m2-r3-owner-promotion-v1.toml"],
    )
    _load_r3_promoted_owner_set(
        archived_bundle,
        bootstrap_spec_raw,
        owner_fixture_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        archived["owners/limits-python-reproduction.json"],
        archived["owners/limits-rust-reproduction.json"],
        _R3_PRE_CLARIFICATION_PROMOTION_V1_SHA256,
    )
    if all(current[name] == final[name] for name in final):
        return "already-applied"
    if rust_stage_directory is None or python_comparison_files is None:
        raise PolicyError("r3-clarification-rust-stage")
    stage_route_receipt, stage_limits_receipt = validate_r3_rust_stage(
        rust_stage_directory,
        _R3_CLARIFICATION_RUST_STAGE_MANIFEST_SHA256,
        python_comparison_files,
    )
    if (
        stage_route_receipt != rust_route_receipt_raw
        or stage_limits_receipt != rust_limits_receipt_raw
    ):
        raise PolicyError("r3-clarification-rust-stage")
    precursor = {
        "profile-policy-v1.toml": bundle.profile_policy,
        "damage-policy-v1.toml": bundle.damage_policy,
        "route-data-v1.json": bundle.route_data,
        "profile-limits-v1.toml": archived[
            "owners/profile-limits-v1.toml"
        ],
        "m2-r3-owner-promotion-v1.toml": archived[
            "owners/m2-r3-owner-promotion-v1.toml"
        ],
    }
    if any(current[name] != precursor[name] for name in precursor):
        raise PolicyError("r3-clarification-precondition")
    canonical_candidate = candidates_directory / (
        "eh72-hier-r5-r2-r1-crc32c-v0"
    )
    if canonical_candidate.exists() or canonical_candidate.is_symlink():
        raise PolicyError("r3-clarification-candidate-present")
    expected_promotion = render_r3_mapping_clarification_manifest(
        archived["owners/m2-r3-owner-promotion-v1.toml"],
        bootstrap_spec_raw,
        bundle.profile_policy,
        bundle.damage_policy,
        owner_fixture_raw,
        bundle.route_data,
        bundle.profile_limits,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
    )
    if expected_promotion != bundle.promotion_manifest:
        raise PolicyError("r3-clarification-render")
    outputs = {
        "damage-policy-v1.toml": bundle.damage_policy,
        "profile-limits-v1.toml": bundle.profile_limits,
        "m2-r3-owner-promotion-v1.toml": bundle.promotion_manifest,
    }
    with tempfile.TemporaryDirectory(
        prefix=".r3-clarification-stage-", dir=spec_directory
    ) as temporary:
        stage = Path(temporary)
        for name, raw in outputs.items():
            path = stage / name
            with path.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        directory_fd = os.open(stage, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        if any((stage / name).read_bytes() != raw for name, raw in outputs.items()):
            raise PolicyError("r3-clarification-stage")
        if dry_run:
            return "dry-run-clean"
        backup_directory = stage / "backups"
        backup_directory.mkdir(mode=0o700)
        for name in outputs:
            with (backup_directory / name).open("xb") as handle:
                handle.write(current[name])
                handle.flush()
                os.fsync(handle.fileno())
        directory_fd = os.open(backup_directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        written: list[str] = []
        try:
            # The stale promotion remains fail-closed until the last replace.
            for name in (
                "damage-policy-v1.toml",
                "profile-limits-v1.toml",
            ):
                os.replace(stage / name, destinations[name])
                written.append(name)
            directory_fd = os.open(spec_directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            authority = "m2-r3-owner-promotion-v1.toml"
            os.replace(stage / authority, destinations[authority])
            written.append(authority)
            directory_fd = os.open(spec_directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            observed = {
                name: path.read_bytes() for name, path in destinations.items()
            }
            if any(observed[name] != final[name] for name in final):
                raise PolicyError("r3-clarification-postcondition")
            observed_bundle = R3PromotionWriteBundle(
                observed["profile-policy-v1.toml"],
                observed["damage-policy-v1.toml"],
                observed["route-data-v1.json"],
                observed["profile-limits-v1.toml"],
                observed["m2-r3-owner-promotion-v1.toml"],
            )
            if _load_r3_mapping_clarified_owner_set(
                observed_bundle,
                bootstrap_spec_raw,
                owner_fixture_raw,
                python_route_receipt_raw,
                rust_route_receipt_raw,
                python_limits_receipt_raw,
                rust_limits_receipt_raw,
            ) != admitted:
                raise PolicyError("r3-clarification-postcondition")
        except Exception:
            for name in reversed(written):
                os.replace(backup_directory / name, destinations[name])
            directory_fd = os.open(spec_directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            raise
    return "applied"


def apply_r3_damage_schema_clarification_bundle(
    workspace: Path,
    bundle: R3PromotionWriteBundle,
    bootstrap_spec_raw: bytes,
    owner_fixture_raw: bytes,
    python_route_receipt_raw: bytes,
    rust_route_receipt_raw: bytes,
    python_limits_receipt_raw: bytes,
    rust_limits_receipt_raw: bytes,
    rust_stage_directory: Path | None,
    python_comparison_files: dict[str, bytes] | None,
    *,
    dry_run: bool,
) -> str:
    """Atomically install only the self-owned damage-schema refreeze."""

    if (
        not isinstance(workspace, Path)
        or type(bundle) is not R3PromotionWriteBundle
        or type(dry_run) is not bool
        or any(
            type(raw) is not bytes
            for raw in (
                bootstrap_spec_raw,
                owner_fixture_raw,
                python_route_receipt_raw,
                rust_route_receipt_raw,
                python_limits_receipt_raw,
                rust_limits_receipt_raw,
            )
        )
        or (
            rust_stage_directory is not None
            and not isinstance(rust_stage_directory, Path)
        )
        or (
            python_comparison_files is not None
            and type(python_comparison_files) is not dict
        )
    ):
        raise PolicyError("r3-damage-schema-apply-arguments")
    try:
        root = workspace.resolve(strict=True)
    except OSError as error:
        raise PolicyError("r3-damage-schema-workspace") from error
    spec_directory = root / "spec"
    conformance_directory = root / "conformance"
    artifacts_directory = root / "artifacts"
    candidates_directory = artifacts_directory / "candidates"
    if (
        workspace.is_symlink()
        or not root.is_dir()
        or spec_directory.is_symlink()
        or not spec_directory.is_dir()
        or conformance_directory.is_symlink()
        or not conformance_directory.is_dir()
        or artifacts_directory.is_symlink()
        or not artifacts_directory.is_dir()
        or candidates_directory.is_symlink()
        or (
            candidates_directory.exists()
            and not candidates_directory.is_dir()
        )
    ):
        raise PolicyError("r3-damage-schema-workspace")
    bootstrap_path = spec_directory / "bootstrap-v1.md"
    fixture_path = conformance_directory / "m2-r3-owner-v1.json"
    if (
        bootstrap_path.is_symlink()
        or not bootstrap_path.is_file()
        or fixture_path.is_symlink()
        or not fixture_path.is_file()
        or bootstrap_path.read_bytes() != bootstrap_spec_raw
        or fixture_path.read_bytes() != owner_fixture_raw
    ):
        raise PolicyError("r3-damage-schema-input")

    admitted = _load_r3_damage_schema_clarified_owner_set(
        bundle,
        bootstrap_spec_raw,
        owner_fixture_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
    )
    destinations = {
        "profile-policy-v1.toml": spec_directory / "profile-policy-v1.toml",
        "damage-policy-v1.toml": spec_directory / "damage-policy-v1.toml",
        "route-data-v1.json": spec_directory / "route-data-v1.json",
        "profile-limits-v1.toml": spec_directory / "profile-limits-v1.toml",
        "m2-r3-owner-promotion-v1.toml": (
            spec_directory / "m2-r3-owner-promotion-v1.toml"
        ),
    }
    final = {
        "profile-policy-v1.toml": bundle.profile_policy,
        "damage-policy-v1.toml": bundle.damage_policy,
        "route-data-v1.json": bundle.route_data,
        "profile-limits-v1.toml": bundle.profile_limits,
        "m2-r3-owner-promotion-v1.toml": bundle.promotion_manifest,
    }
    current: dict[str, bytes] = {}
    identities: set[tuple[int, int]] = set()
    for name, path in destinations.items():
        if path.is_symlink() or not path.is_file():
            raise PolicyError("r3-damage-schema-destination")
        stat = path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if identity in identities:
            raise PolicyError("r3-damage-schema-destination-alias")
        identities.add(identity)
        current[name] = path.read_bytes()

    validate_r3_pre_clarification_archive(root, bundle.damage_policy)
    archived = validate_r3_pre_damage_schema_archive(
        root, bundle.damage_policy
    )
    archived_bundle = R3PromotionWriteBundle(
        bundle.profile_policy,
        archived["owners/damage-policy-v1.toml"],
        bundle.route_data,
        archived["owners/profile-limits-v1.toml"],
        archived["owners/m2-r3-owner-promotion-v1.toml"],
    )
    _load_r3_mapping_clarified_owner_set(
        archived_bundle,
        bootstrap_spec_raw,
        owner_fixture_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        archived["owners/limits-python-reproduction.json"],
        archived["owners/limits-rust-reproduction.json"],
    )
    canonical_candidate = candidates_directory / (
        "eh72-hier-r5-r2-r1-crc32c-v0"
    )
    if canonical_candidate.exists() or canonical_candidate.is_symlink():
        raise PolicyError("r3-damage-schema-candidate-present")
    expected_promotion = render_r3_damage_schema_clarification_manifest(
        archived["owners/m2-r3-owner-promotion-v1.toml"],
        bootstrap_spec_raw,
        bundle.profile_policy,
        bundle.damage_policy,
        owner_fixture_raw,
        bundle.route_data,
        bundle.profile_limits,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
    )
    if expected_promotion != bundle.promotion_manifest:
        raise PolicyError("r3-damage-schema-render")
    if all(current[name] == final[name] for name in final):
        return "already-applied"

    precursor = {
        "profile-policy-v1.toml": bundle.profile_policy,
        "damage-policy-v1.toml": bundle.damage_policy,
        "route-data-v1.json": bundle.route_data,
        "profile-limits-v1.toml": archived[
            "owners/profile-limits-v1.toml"
        ],
        "m2-r3-owner-promotion-v1.toml": archived[
            "owners/m2-r3-owner-promotion-v1.toml"
        ],
    }
    if any(current[name] != precursor[name] for name in precursor):
        raise PolicyError("r3-damage-schema-precondition")
    if rust_stage_directory is None or python_comparison_files is None:
        raise PolicyError("r3-damage-schema-rust-stage")
    stage_route_receipt, stage_limits_receipt = validate_r3_rust_stage(
        rust_stage_directory,
        _R3_DAMAGE_SCHEMA_RUST_STAGE_MANIFEST_SHA256,
        python_comparison_files,
    )
    if (
        stage_route_receipt != rust_route_receipt_raw
        or stage_limits_receipt != rust_limits_receipt_raw
    ):
        raise PolicyError("r3-damage-schema-rust-stage")

    outputs = {
        "damage-policy-v1.toml": bundle.damage_policy,
        "profile-limits-v1.toml": bundle.profile_limits,
        "m2-r3-owner-promotion-v1.toml": bundle.promotion_manifest,
    }
    with tempfile.TemporaryDirectory(
        prefix=".r3-damage-schema-stage-", dir=spec_directory
    ) as temporary:
        stage = Path(temporary)
        for name, raw in outputs.items():
            path = stage / name
            with path.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        directory_fd = os.open(stage, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        if any((stage / name).read_bytes() != raw for name, raw in outputs.items()):
            raise PolicyError("r3-damage-schema-stage")
        if dry_run:
            return "dry-run-clean"

        backup_directory = stage / "backups"
        backup_directory.mkdir(mode=0o700)
        for name in outputs:
            with (backup_directory / name).open("xb") as handle:
                handle.write(current[name])
                handle.flush()
                os.fsync(handle.fileno())
        directory_fd = os.open(backup_directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        written: list[str] = []
        try:
            for name in (
                "damage-policy-v1.toml",
                "profile-limits-v1.toml",
            ):
                os.replace(stage / name, destinations[name])
                written.append(name)
            directory_fd = os.open(spec_directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            authority = "m2-r3-owner-promotion-v1.toml"
            os.replace(stage / authority, destinations[authority])
            written.append(authority)
            directory_fd = os.open(spec_directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            observed = {
                name: path.read_bytes() for name, path in destinations.items()
            }
            if any(observed[name] != final[name] for name in final):
                raise PolicyError("r3-damage-schema-postcondition")
            observed_bundle = R3PromotionWriteBundle(
                observed["profile-policy-v1.toml"],
                observed["damage-policy-v1.toml"],
                observed["route-data-v1.json"],
                observed["profile-limits-v1.toml"],
                observed["m2-r3-owner-promotion-v1.toml"],
            )
            if _load_r3_damage_schema_clarified_owner_set(
                observed_bundle,
                bootstrap_spec_raw,
                owner_fixture_raw,
                python_route_receipt_raw,
                rust_route_receipt_raw,
                python_limits_receipt_raw,
                rust_limits_receipt_raw,
            ) != admitted:
                raise PolicyError("r3-damage-schema-postcondition")
            if canonical_candidate.exists() or canonical_candidate.is_symlink():
                raise PolicyError("r3-damage-schema-postcondition")
        except Exception:
            for name in reversed(written):
                os.replace(backup_directory / name, destinations[name])
            directory_fd = os.open(spec_directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            raise
    return "applied"


def apply_r3_independence_witness_clarification_bundle(
    workspace: Path,
    bundle: R3PromotionWriteBundle,
    bootstrap_spec_raw: bytes,
    owner_fixture_raw: bytes,
    python_route_receipt_raw: bytes,
    rust_route_receipt_raw: bytes,
    python_limits_receipt_raw: bytes,
    rust_limits_receipt_raw: bytes,
    rust_stage_directory: Path | None,
    python_comparison_files: dict[str, bytes] | None,
    *,
    dry_run: bool,
) -> str:
    """Atomically install only the self-owned witness-count refreeze."""

    if (
        not isinstance(workspace, Path)
        or type(bundle) is not R3PromotionWriteBundle
        or type(dry_run) is not bool
        or any(
            type(raw) is not bytes
            for raw in (
                bootstrap_spec_raw,
                owner_fixture_raw,
                python_route_receipt_raw,
                rust_route_receipt_raw,
                python_limits_receipt_raw,
                rust_limits_receipt_raw,
            )
        )
        or (
            rust_stage_directory is not None
            and not isinstance(rust_stage_directory, Path)
        )
        or (
            python_comparison_files is not None
            and type(python_comparison_files) is not dict
        )
    ):
        raise PolicyError("r3-witness-apply-arguments")
    try:
        root = workspace.resolve(strict=True)
    except OSError as error:
        raise PolicyError("r3-witness-workspace") from error
    spec_directory = root / "spec"
    conformance_directory = root / "conformance"
    artifacts_directory = root / "artifacts"
    candidates_directory = artifacts_directory / "candidates"
    if (
        workspace.is_symlink()
        or not root.is_dir()
        or spec_directory.is_symlink()
        or not spec_directory.is_dir()
        or conformance_directory.is_symlink()
        or not conformance_directory.is_dir()
        or artifacts_directory.is_symlink()
        or not artifacts_directory.is_dir()
        or candidates_directory.is_symlink()
        or (
            candidates_directory.exists()
            and not candidates_directory.is_dir()
        )
    ):
        raise PolicyError("r3-witness-workspace")
    bootstrap_path = spec_directory / "bootstrap-v1.md"
    fixture_path = conformance_directory / "m2-r3-owner-v1.json"
    if (
        bootstrap_path.is_symlink()
        or not bootstrap_path.is_file()
        or bootstrap_path.stat().st_nlink != 1
        or fixture_path.is_symlink()
        or not fixture_path.is_file()
        or fixture_path.stat().st_nlink != 1
        or bootstrap_path.read_bytes() != bootstrap_spec_raw
        or fixture_path.read_bytes() != owner_fixture_raw
    ):
        raise PolicyError("r3-witness-input")

    admitted = _load_r3_pre_gate6_convergence_owner_set(
        bundle,
        bootstrap_spec_raw,
        owner_fixture_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
    )
    destinations = {
        "profile-policy-v1.toml": spec_directory / "profile-policy-v1.toml",
        "damage-policy-v1.toml": spec_directory / "damage-policy-v1.toml",
        "route-data-v1.json": spec_directory / "route-data-v1.json",
        "profile-limits-v1.toml": spec_directory / "profile-limits-v1.toml",
        "m2-r3-owner-promotion-v1.toml": (
            spec_directory / "m2-r3-owner-promotion-v1.toml"
        ),
    }
    final = {
        "profile-policy-v1.toml": bundle.profile_policy,
        "damage-policy-v1.toml": bundle.damage_policy,
        "route-data-v1.json": bundle.route_data,
        "profile-limits-v1.toml": bundle.profile_limits,
        "m2-r3-owner-promotion-v1.toml": bundle.promotion_manifest,
    }

    def read_current(reason: str) -> dict[str, bytes]:
        current_files: dict[str, bytes] = {}
        identities: set[tuple[int, int]] = set()
        for name, path in destinations.items():
            if path.is_symlink() or not path.is_file():
                raise PolicyError(reason)
            stat = path.stat()
            identity = (stat.st_dev, stat.st_ino)
            if stat.st_nlink != 1 or identity in identities:
                raise PolicyError(reason)
            identities.add(identity)
            raw = path.read_bytes()
            if len(raw) != stat.st_size:
                raise PolicyError(reason)
            current_files[name] = raw
        return current_files

    current = read_current("r3-witness-destination")
    validate_r3_pre_clarification_archive(root, bundle.damage_policy)
    validate_r3_pre_damage_schema_archive(root, bundle.damage_policy)
    archived = validate_r3_pre_independence_witness_archive(
        root, bundle.damage_policy
    )
    archived_bundle = R3PromotionWriteBundle(
        bundle.profile_policy,
        archived["owners/damage-policy-v1.toml"],
        bundle.route_data,
        archived["owners/profile-limits-v1.toml"],
        archived["owners/m2-r3-owner-promotion-v1.toml"],
    )
    _load_r3_damage_schema_clarified_owner_set(
        archived_bundle,
        bootstrap_spec_raw,
        owner_fixture_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        archived["owners/limits-python-reproduction.json"],
        archived["owners/limits-rust-reproduction.json"],
    )
    canonical_candidate = candidates_directory / (
        "eh72-hier-r5-r2-r1-crc32c-v0"
    )
    if canonical_candidate.exists() or canonical_candidate.is_symlink():
        raise PolicyError("r3-witness-candidate-present")
    expected_promotion = (
        render_r3_independence_witness_clarification_manifest(
            archived["owners/m2-r3-owner-promotion-v1.toml"],
            bootstrap_spec_raw,
            bundle.profile_policy,
            bundle.damage_policy,
            owner_fixture_raw,
            bundle.route_data,
            bundle.profile_limits,
            python_route_receipt_raw,
            rust_route_receipt_raw,
            python_limits_receipt_raw,
            rust_limits_receipt_raw,
        )
    )
    if expected_promotion != bundle.promotion_manifest:
        raise PolicyError("r3-witness-render")
    if all(current[name] == final[name] for name in final):
        return "already-applied"

    precursor = {
        "profile-policy-v1.toml": bundle.profile_policy,
        "damage-policy-v1.toml": bundle.damage_policy,
        "route-data-v1.json": bundle.route_data,
        "profile-limits-v1.toml": archived[
            "owners/profile-limits-v1.toml"
        ],
        "m2-r3-owner-promotion-v1.toml": archived[
            "owners/m2-r3-owner-promotion-v1.toml"
        ],
    }
    if any(current[name] != precursor[name] for name in precursor):
        raise PolicyError("r3-witness-precondition")
    if rust_stage_directory is None or python_comparison_files is None:
        raise PolicyError("r3-witness-rust-stage")
    stage_route_receipt, stage_limits_receipt = validate_r3_rust_stage(
        rust_stage_directory,
        _R3_INDEPENDENCE_WITNESS_RUST_STAGE_MANIFEST_SHA256,
        python_comparison_files,
    )
    if (
        stage_route_receipt != rust_route_receipt_raw
        or stage_limits_receipt != rust_limits_receipt_raw
    ):
        raise PolicyError("r3-witness-rust-stage")

    outputs = {
        "damage-policy-v1.toml": bundle.damage_policy,
        "profile-limits-v1.toml": bundle.profile_limits,
        "m2-r3-owner-promotion-v1.toml": bundle.promotion_manifest,
    }
    with tempfile.TemporaryDirectory(
        prefix=".r3-witness-stage-", dir=spec_directory
    ) as temporary:
        stage = Path(temporary)
        for name, raw in outputs.items():
            path = stage / name
            with path.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        directory_fd = os.open(stage, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        if any((stage / name).read_bytes() != raw for name, raw in outputs.items()):
            raise PolicyError("r3-witness-stage")

        # Re-read every current input after the independently compared output
        # has been staged.  This closes the check/write window before the first
        # replace and prevents a caller from overwriting concurrent owner drift.
        staged_current = read_current("r3-witness-prewrite")
        if (
            any(staged_current[name] != precursor[name] for name in precursor)
            or bootstrap_path.read_bytes() != bootstrap_spec_raw
            or fixture_path.read_bytes() != owner_fixture_raw
            or canonical_candidate.exists()
            or canonical_candidate.is_symlink()
        ):
            raise PolicyError("r3-witness-prewrite")
        validate_r3_pre_clarification_archive(root, bundle.damage_policy)
        validate_r3_pre_damage_schema_archive(root, bundle.damage_policy)
        validate_r3_pre_independence_witness_archive(root, bundle.damage_policy)
        staged_current = read_current("r3-witness-prewrite")
        if (
            any(staged_current[name] != precursor[name] for name in precursor)
            or bootstrap_path.read_bytes() != bootstrap_spec_raw
            or fixture_path.read_bytes() != owner_fixture_raw
            or canonical_candidate.exists()
            or canonical_candidate.is_symlink()
        ):
            raise PolicyError("r3-witness-prewrite")
        if dry_run:
            return "dry-run-clean"

        backup_directory = stage / "backups"
        backup_directory.mkdir(mode=0o700)
        for name in outputs:
            with (backup_directory / name).open("xb") as handle:
                handle.write(staged_current[name])
                handle.flush()
                os.fsync(handle.fileno())
        directory_fd = os.open(backup_directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        staged_current = read_current("r3-witness-prewrite")
        if (
            any(staged_current[name] != precursor[name] for name in precursor)
            or bootstrap_path.read_bytes() != bootstrap_spec_raw
            or fixture_path.read_bytes() != owner_fixture_raw
            or canonical_candidate.exists()
            or canonical_candidate.is_symlink()
        ):
            raise PolicyError("r3-witness-prewrite")
        written: list[str] = []
        try:
            for name in (
                "damage-policy-v1.toml",
                "profile-limits-v1.toml",
            ):
                os.replace(stage / name, destinations[name])
                written.append(name)
            directory_fd = os.open(spec_directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            authority = "m2-r3-owner-promotion-v1.toml"
            os.replace(stage / authority, destinations[authority])
            written.append(authority)
            directory_fd = os.open(spec_directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            observed = read_current("r3-witness-postcondition")
            if any(observed[name] != final[name] for name in final):
                raise PolicyError("r3-witness-postcondition")
            observed_bundle = R3PromotionWriteBundle(
                observed["profile-policy-v1.toml"],
                observed["damage-policy-v1.toml"],
                observed["route-data-v1.json"],
                observed["profile-limits-v1.toml"],
                observed["m2-r3-owner-promotion-v1.toml"],
            )
            if _load_r3_pre_gate6_convergence_owner_set(
                observed_bundle,
                bootstrap_spec_raw,
                owner_fixture_raw,
                python_route_receipt_raw,
                rust_route_receipt_raw,
                python_limits_receipt_raw,
                rust_limits_receipt_raw,
            ) != admitted:
                raise PolicyError("r3-witness-postcondition")
            if canonical_candidate.exists() or canonical_candidate.is_symlink():
                raise PolicyError("r3-witness-postcondition")
        except Exception:
            for name in reversed(written):
                os.replace(backup_directory / name, destinations[name])
            directory_fd = os.open(spec_directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            raise
    return "applied"


def apply_r3_gate6_convergence_clarification_bundle(
    workspace: Path,
    bundle: R3PromotionWriteBundle,
    bootstrap_spec_raw: bytes,
    owner_fixture_raw: bytes,
    python_route_receipt_raw: bytes,
    rust_route_receipt_raw: bytes,
    python_limits_receipt_raw: bytes,
    rust_limits_receipt_raw: bytes,
    rust_stage_directory: Path | None,
    python_comparison_files: dict[str, bytes] | None,
    *,
    dry_run: bool,
) -> str:
    """Atomically install only the self-owned gate-6 convergence refreeze."""

    if (
        not isinstance(workspace, Path)
        or type(bundle) is not R3PromotionWriteBundle
        or type(dry_run) is not bool
        or any(
            type(raw) is not bytes
            for raw in (
                bootstrap_spec_raw,
                owner_fixture_raw,
                python_route_receipt_raw,
                rust_route_receipt_raw,
                python_limits_receipt_raw,
                rust_limits_receipt_raw,
            )
        )
        or (
            rust_stage_directory is not None
            and not isinstance(rust_stage_directory, Path)
        )
        or (
            python_comparison_files is not None
            and type(python_comparison_files) is not dict
        )
    ):
        raise PolicyError("r3-convergence-apply-arguments")
    try:
        root = workspace.resolve(strict=True)
    except OSError as error:
        raise PolicyError("r3-convergence-workspace") from error
    spec_directory = root / "spec"
    conformance_directory = root / "conformance"
    artifacts_directory = root / "artifacts"
    candidates_directory = artifacts_directory / "candidates"
    if (
        workspace.is_symlink()
        or not root.is_dir()
        or spec_directory.is_symlink()
        or not spec_directory.is_dir()
        or conformance_directory.is_symlink()
        or not conformance_directory.is_dir()
        or artifacts_directory.is_symlink()
        or not artifacts_directory.is_dir()
        or candidates_directory.is_symlink()
        or (
            candidates_directory.exists()
            and not candidates_directory.is_dir()
        )
    ):
        raise PolicyError("r3-convergence-workspace")
    bootstrap_path = spec_directory / "bootstrap-v1.md"
    fixture_path = conformance_directory / "m2-r3-owner-v1.json"
    if (
        bootstrap_path.is_symlink()
        or not bootstrap_path.is_file()
        or bootstrap_path.stat().st_nlink != 1
        or fixture_path.is_symlink()
        or not fixture_path.is_file()
        or fixture_path.stat().st_nlink != 1
        or bootstrap_path.read_bytes() != bootstrap_spec_raw
        or fixture_path.read_bytes() != owner_fixture_raw
    ):
        raise PolicyError("r3-convergence-input")
    admitted = load_r3_promoted_owner_set(
        bundle,
        bootstrap_spec_raw,
        owner_fixture_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
    )
    destinations = {
        "profile-policy-v1.toml": spec_directory / "profile-policy-v1.toml",
        "damage-policy-v1.toml": spec_directory / "damage-policy-v1.toml",
        "route-data-v1.json": spec_directory / "route-data-v1.json",
        "profile-limits-v1.toml": spec_directory / "profile-limits-v1.toml",
        "m2-r3-owner-promotion-v1.toml": (
            spec_directory / "m2-r3-owner-promotion-v1.toml"
        ),
    }
    final = {
        "profile-policy-v1.toml": bundle.profile_policy,
        "damage-policy-v1.toml": bundle.damage_policy,
        "route-data-v1.json": bundle.route_data,
        "profile-limits-v1.toml": bundle.profile_limits,
        "m2-r3-owner-promotion-v1.toml": bundle.promotion_manifest,
    }

    def read_current(reason: str) -> dict[str, bytes]:
        current_files: dict[str, bytes] = {}
        identities: set[tuple[int, int]] = set()
        for name, path in destinations.items():
            if path.is_symlink() or not path.is_file():
                raise PolicyError(reason)
            stat = path.stat()
            file_identity = (stat.st_dev, stat.st_ino)
            if stat.st_nlink != 1 or file_identity in identities:
                raise PolicyError(reason)
            identities.add(file_identity)
            raw = path.read_bytes()
            if len(raw) != stat.st_size:
                raise PolicyError(reason)
            current_files[name] = raw
        return current_files

    current = read_current("r3-convergence-destination")
    validate_r3_pre_clarification_archive(root, bundle.damage_policy)
    validate_r3_pre_damage_schema_archive(root, bundle.damage_policy)
    validate_r3_pre_independence_witness_archive(root, bundle.damage_policy)
    archived = validate_r3_pre_gate6_convergence_archive(
        root, bundle.damage_policy
    )
    archived_bundle = R3PromotionWriteBundle(
        bundle.profile_policy,
        archived["owners/damage-policy-v1.toml"],
        bundle.route_data,
        archived["owners/profile-limits-v1.toml"],
        archived["owners/m2-r3-owner-promotion-v1.toml"],
    )
    _load_r3_pre_gate6_convergence_owner_set(
        archived_bundle,
        bootstrap_spec_raw,
        owner_fixture_raw,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        archived["owners/limits-python-reproduction.json"],
        archived["owners/limits-rust-reproduction.json"],
    )
    canonical_candidate = candidates_directory / (
        "eh72-hier-r5-r2-r1-crc32c-v0"
    )
    if canonical_candidate.exists() or canonical_candidate.is_symlink():
        raise PolicyError("r3-convergence-candidate-present")
    expected_promotion = render_r3_gate6_convergence_clarification_manifest(
        archived["owners/m2-r3-owner-promotion-v1.toml"],
        bootstrap_spec_raw,
        bundle.profile_policy,
        bundle.damage_policy,
        owner_fixture_raw,
        bundle.route_data,
        bundle.profile_limits,
        python_route_receipt_raw,
        rust_route_receipt_raw,
        python_limits_receipt_raw,
        rust_limits_receipt_raw,
    )
    if expected_promotion != bundle.promotion_manifest:
        raise PolicyError("r3-convergence-render")
    if all(current[name] == final[name] for name in final):
        return "already-applied"
    precursor = {
        "profile-policy-v1.toml": bundle.profile_policy,
        "damage-policy-v1.toml": bundle.damage_policy,
        "route-data-v1.json": bundle.route_data,
        "profile-limits-v1.toml": archived[
            "owners/profile-limits-v1.toml"
        ],
        "m2-r3-owner-promotion-v1.toml": archived[
            "owners/m2-r3-owner-promotion-v1.toml"
        ],
    }
    if any(current[name] != precursor[name] for name in precursor):
        raise PolicyError("r3-convergence-precondition")
    if rust_stage_directory is None or python_comparison_files is None:
        raise PolicyError("r3-convergence-rust-stage")
    stage_route_receipt, stage_limits_receipt = validate_r3_rust_stage(
        rust_stage_directory,
        _R3_GATE6_CONVERGENCE_RUST_STAGE_MANIFEST_SHA256,
        python_comparison_files,
    )
    if (
        stage_route_receipt != rust_route_receipt_raw
        or stage_limits_receipt != rust_limits_receipt_raw
    ):
        raise PolicyError("r3-convergence-rust-stage")
    outputs = {
        "damage-policy-v1.toml": bundle.damage_policy,
        "profile-limits-v1.toml": bundle.profile_limits,
        "m2-r3-owner-promotion-v1.toml": bundle.promotion_manifest,
    }
    with tempfile.TemporaryDirectory(
        prefix=".r3-convergence-stage-", dir=spec_directory
    ) as temporary:
        stage = Path(temporary)
        for name, raw in outputs.items():
            path = stage / name
            with path.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        directory_fd = os.open(stage, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        if any(
            (stage / name).read_bytes() != raw
            for name, raw in outputs.items()
        ):
            raise PolicyError("r3-convergence-stage")

        def revalidate(reason: str) -> dict[str, bytes]:
            observed = read_current(reason)
            if (
                any(observed[name] != precursor[name] for name in precursor)
                or bootstrap_path.read_bytes() != bootstrap_spec_raw
                or fixture_path.read_bytes() != owner_fixture_raw
                or canonical_candidate.exists()
                or canonical_candidate.is_symlink()
            ):
                raise PolicyError(reason)
            validate_r3_pre_clarification_archive(root, bundle.damage_policy)
            validate_r3_pre_damage_schema_archive(root, bundle.damage_policy)
            validate_r3_pre_independence_witness_archive(
                root, bundle.damage_policy
            )
            validate_r3_pre_gate6_convergence_archive(
                root, bundle.damage_policy
            )
            observed = read_current(reason)
            if (
                any(observed[name] != precursor[name] for name in precursor)
                or bootstrap_path.read_bytes() != bootstrap_spec_raw
                or fixture_path.read_bytes() != owner_fixture_raw
                or canonical_candidate.exists()
                or canonical_candidate.is_symlink()
            ):
                raise PolicyError(reason)
            return observed

        staged_current = revalidate("r3-convergence-prewrite")
        if dry_run:
            return "dry-run-clean"
        backup_directory = stage / "backups"
        backup_directory.mkdir(mode=0o700)
        for name in outputs:
            with (backup_directory / name).open("xb") as handle:
                handle.write(staged_current[name])
                handle.flush()
                os.fsync(handle.fileno())
        directory_fd = os.open(backup_directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        revalidate("r3-convergence-prewrite")
        written: list[str] = []
        try:
            for name in (
                "damage-policy-v1.toml",
                "profile-limits-v1.toml",
            ):
                os.replace(stage / name, destinations[name])
                written.append(name)
            directory_fd = os.open(spec_directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            authority = "m2-r3-owner-promotion-v1.toml"
            os.replace(stage / authority, destinations[authority])
            written.append(authority)
            directory_fd = os.open(spec_directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            observed = read_current("r3-convergence-postcondition")
            if any(observed[name] != final[name] for name in final):
                raise PolicyError("r3-convergence-postcondition")
            observed_bundle = R3PromotionWriteBundle(
                observed["profile-policy-v1.toml"],
                observed["damage-policy-v1.toml"],
                observed["route-data-v1.json"],
                observed["profile-limits-v1.toml"],
                observed["m2-r3-owner-promotion-v1.toml"],
            )
            if load_r3_promoted_owner_set(
                observed_bundle,
                bootstrap_spec_raw,
                owner_fixture_raw,
                python_route_receipt_raw,
                rust_route_receipt_raw,
                python_limits_receipt_raw,
                rust_limits_receipt_raw,
            ) != admitted:
                raise PolicyError("r3-convergence-postcondition")
            if canonical_candidate.exists() or canonical_candidate.is_symlink():
                raise PolicyError("r3-convergence-postcondition")
        except Exception:
            for name in reversed(written):
                os.replace(backup_directory / name, destinations[name])
            directory_fd = os.open(spec_directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            raise
    return "applied"
