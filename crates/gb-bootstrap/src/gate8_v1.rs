//! Independent, bounded M2 R3 gate-8 fact regeneration.
//!
//! This module owns the Rust computation beneath the tracked gate-8 manifest.
//! It deliberately exposes typed facts separately from their canonical owner
//! serialization: candidate construction and every damage observation/result
//! are recomputed from promoted owners, never copied from retained Python
//! aggregate rows.

use std::collections::BTreeMap;

use gb_foundation::{ManifestValue, serialize_manifest, validate_canonical_manifest};
use sha2::{Digest, Sha256};

use crate::EntryHypothesis;
use crate::candidate::{EhObservation, TransportFamily, decode_eh_unit, profile_by_version};
use crate::candidate_recipe::{
    build_eh_recipe_package, build_r3_recipe_package, build_rs_decoder_recipe_package,
    r3_recipe_package_metrics,
};
use crate::carrier::{
    HierarchicalManifestationCore, R3GateOneThroughFive, build_r3_gate_one_through_five,
    build_route_images, generate_r3_route_owner,
};
use crate::damage::{
    ArtifactState, Coordinate, SectionState, d2_square_side, d5_permutations,
    sample_without_replacement, serialize_obs_bits, transformed_clean_bits,
};
use crate::damage_v1::{
    RecoveryResultV1, algebraic_one_beyond_v1, boundary_kat_results_v1, code_mutant_v1,
    cross_profile_splice_v1, d3_coordinates_v1, decode_observation_v1, erase_shell_sector_v1,
    erase_square_v1, geometry_one_beyond_v1, local_check_mutant_v1, mapping_mutant_v1,
    missing_unit_one_beyond_v1, omitted_unit_observation_v1, permuted_unit_observation_v1,
    render_decoder_result_v1, resource_route_one_beyond_v1, route_conflict_v1,
    section_check_mutant_v1, substitute_coordinates_v1, valid_replica_conflict_v1,
};
use crate::independence_v1::{
    IndependenceProofV1, RenderedDamageEvidenceBundleV1, build_independence_proof_from_bundle_v1,
    render_damage_evidence_bundle_v1,
};
use gb_slice::{SliceInputs, compile_slice_v0};

use crate::recipe::decode_recipe_package;
use crate::{
    FragmentWitness, MAX_RAW_BITS, RecoveryQuality, assemble_content_stream,
    assemble_semantic_copy, decode_common_block, decode_tier_frame,
};

pub const R3_PROFILE_ID: &str = "eh72-hier-r5-r2-r1-crc32c-v0";
pub const R3_GATE8_CASE_COUNTS: [usize; 8] = [16, 4, 256, 128, 1_841, 21, 7_364, 408];
pub const R3_GATE8_TOTAL_CASES: usize = 10_038;
pub const GATE8_ARTIFACT_IDS: [&str; 8] = [
    "semantic-content-projection",
    "candidate-manifest",
    "carrier",
    "ownership-ledger",
    "capacity-ledger",
    "density-ledger",
    "damage-bundle-inventory",
    "independence-proof",
];
pub const GATE8_PRODUCER_IDS: [&str; 4] =
    ["native-python", "native-rust", "linux-python", "linux-rust"];
const GATE8_DAMAGE_FILE_COUNT: usize = 72;
const GATE8_DAMAGE_AGGREGATE_BYTES_MAX: usize = 67_108_864;
const GATE8_MANIFEST_BYTES_MAX: usize = 1_048_576;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Gate8Error {
    Candidate,
    Observation,
    Result,
    ResourceLimit,
}

pub type Result<T> = std::result::Result<T, Gate8Error>;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Gate8CaseFactV1 {
    pub family_id: String,
    pub case_id: String,
    pub channel: String,
    pub observation_sha256: String,
    pub decoder_result_sha256: String,
    pub common_case_row: ManifestValue,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Gate8CandidateFactsV1 {
    pub gates_one_through_five: R3GateOneThroughFive,
    pub case_facts: Vec<Gate8CaseFactV1>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Gate8LegacyFixtureFactV0 {
    pub profile_version: u16,
    pub recipient_package_sha256: String,
    pub route_prefix_sha256: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct RegeneratedLegacyFixturesV0 {
    facts: Vec<Gate8LegacyFixtureFactV0>,
    v3_route_prefix: Vec<u8>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Gate8GateSixSevenFactsV1 {
    pub damage_bundle: RenderedDamageEvidenceBundleV1,
    pub independence_proof: IndependenceProofV1,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Gate8SemanticContentV0 {
    pub canonical_bytes: Vec<u8>,
    pub content_stream: Vec<u8>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Gate8ArtifactFactV0 {
    pub artifact_id: &'static str,
    pub sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Gate8ProducerReceiptV0 {
    pub producer_id: &'static str,
    pub artifact_rows: Vec<Gate8ArtifactFactV0>,
    pub canonical_bytes: Vec<u8>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AdmittedGate8ProducerReceiptV0 {
    pub producer_id: String,
    pub artifact_rows: Vec<(String, String)>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Gate8CrossLanguageManifestV0 {
    pub canonical_bytes: Vec<u8>,
    pub passed: bool,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Gate8CandidateMetricsV0 {
    pub operation_kind_count: u64,
    pub table_count: u64,
    pub table_bytes: u64,
    pub graph_nodes: u64,
    pub graph_edges: u64,
    pub dependency_depth: u64,
    pub recipe_cells: u64,
    pub worked_example_cells: u64,
    pub held_out_example_cells: u64,
    pub shell_cells: u64,
    pub convention_count: u64,
    pub plain_bits: u64,
    pub protected_bits: u64,
    pub reserve_bits: u64,
    pub total_bits: u64,
    pub robustness_ppm: u64,
    pub worst_case_work_units: u64,
    pub scratch_bytes: u64,
    pub remaining_reserve_bytes: u64,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn string(value: &str) -> ManifestValue {
    ManifestValue::String(value.to_owned())
}

fn object(rows: impl IntoIterator<Item = (&'static str, ManifestValue)>) -> ManifestValue {
    ManifestValue::Object(
        rows.into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}

fn parameter(id: &str, value_type: &str, value: ManifestValue) -> ManifestValue {
    object([
        ("id", string(id)),
        ("value_type", string(value_type)),
        ("value", value),
    ])
}

fn coordinate_list(coordinates: impl IntoIterator<Item = Coordinate>) -> ManifestValue {
    ManifestValue::Array(
        coordinates
            .into_iter()
            .map(|coordinate| {
                ManifestValue::Array(vec![
                    ManifestValue::U64(u64::from(coordinate.row)),
                    ManifestValue::U64(u64::from(coordinate.column)),
                ])
            })
            .collect(),
    )
}

fn u64_list(values: impl IntoIterator<Item = u64>) -> ManifestValue {
    ManifestValue::Array(values.into_iter().map(ManifestValue::U64).collect())
}

fn artifact_state_name(state: ArtifactState) -> &'static str {
    match state {
        ArtifactState::Exact => "exact",
        ArtifactState::Degraded => "degraded",
        ArtifactState::Failure => "failure",
        ArtifactState::Ambiguous => "ambiguous",
        ArtifactState::ResourceLimit => "resource-limit",
    }
}

fn section_state_name(state: SectionState) -> &'static str {
    match state {
        SectionState::Verified => "verified",
        SectionState::Recovered => "recovered",
        SectionState::Incomplete => "incomplete",
        SectionState::Corrupt => "corrupt",
        SectionState::Ambiguous => "ambiguous",
        SectionState::Unknown => "unknown",
    }
}

fn case_shape_v1(
    core: &HierarchicalManifestationCore,
    family: usize,
    ordinal: usize,
) -> Result<(&'static str, Vec<ManifestValue>)> {
    let target_ids = || u64_list(1_u64..=5);
    let u64_parameter = |id: &str, value: u64| parameter(id, "u64", ManifestValue::U64(value));
    let ordinal_u64 = u64::try_from(ordinal).map_err(|_| Gate8Error::ResourceLimit)?;
    Ok(match family {
        0 => (
            "clean-transform-polarity",
            vec![
                u64_parameter("polarity_id", ordinal_u64 % 2),
                u64_parameter("transform_id", ordinal_u64 / 2),
            ],
        ),
        1 => (
            "erase-one-complete-shell-sector",
            vec![u64_parameter("sector_id", ordinal_u64)],
        ),
        2 => {
            let local = *exact_d2_placements(usize::from(core.mapping.interior_side))?
                .get(ordinal)
                .ok_or(Gate8Error::Observation)?;
            let width = u32::from(core.shell_width);
            let absolute = Coordinate {
                row: local
                    .row
                    .checked_add(width)
                    .ok_or(Gate8Error::ResourceLimit)?,
                column: local
                    .column
                    .checked_add(width)
                    .ok_or(Gate8Error::ResourceLimit)?,
            };
            (
                "erase-square-in-protected-interior",
                vec![
                    u64_parameter(
                        "side",
                        u64::try_from(d2_square_side(usize::from(core.mapping.interior_side)))
                            .map_err(|_| Gate8Error::ResourceLimit)?,
                    ),
                    parameter("top_left", "coordinate-list", coordinate_list([absolute])),
                ],
            )
        }
        3 => {
            let seed = 5_134_751_402_299_490_304_u64
                .checked_add(ordinal_u64)
                .ok_or(Gate8Error::ResourceLimit)?;
            let coordinates =
                d3_coordinates_v1(core, seed, 0).map_err(|_| Gate8Error::Observation)?;
            (
                "fixed-weight-unknown-bit-substitution",
                vec![
                    parameter(
                        "coordinates",
                        "coordinate-list",
                        coordinate_list(coordinates),
                    ),
                    u64_parameter("seed", seed),
                    u64_parameter("stratum_id", ordinal_u64 / 32),
                ],
            )
        }
        4 => (
            "omit-one-physical-unit-observation",
            vec![u64_parameter(
                "omitted_unit_id",
                ordinal_u64
                    .checked_add(1)
                    .ok_or(Gate8Error::ResourceLimit)?,
            )],
        ),
        5 => (
            "permute-intact-physical-unit-observations",
            vec![u64_parameter("permutation_ordinal", ordinal_u64)],
        ),
        6 => (
            "erase-shell-sector-union-one-physical-unit-cell-set",
            vec![
                u64_parameter("sector_id", ordinal_u64 / 1_841),
                u64_parameter("unit_id", ordinal_u64 % 1_841 + 1),
            ],
        ),
        7 => match ordinal {
            0..=2 => (
                "mapping-mutants",
                vec![u64_parameter("mutant_ordinal", ordinal_u64)],
            ),
            3..=4 => (
                "check-mutants",
                vec![
                    u64_parameter("case_ordinal", ordinal_u64 - 3),
                    parameter("target_unit_ids", "u64-list", target_ids()),
                ],
            ),
            5..=6 => (
                "check-mutants",
                vec![
                    u64_parameter("case_ordinal", ordinal_u64 - 3),
                    u64_parameter("section_id", 2),
                ],
            ),
            7..=9 => (
                "code-mutants",
                vec![
                    u64_parameter("case_ordinal", ordinal_u64 - 7),
                    parameter("target_unit_ids", "u64-list", target_ids()),
                ],
            ),
            10 => (
                "route-conflicts",
                vec![u64_parameter("alternate_profile_version", 3)],
            ),
            11..=15 => (
                "cross-profile-splices",
                vec![
                    u64_parameter("source_profile_version", ordinal_u64 - 9),
                    parameter("target_unit_ids", "u64-list", target_ids()),
                ],
            ),
            16 => (
                "valid-copy-conflicts",
                vec![
                    u64_parameter("section_id", 1),
                    u64_parameter("target_unit_id", 1),
                ],
            ),
            17..=272 => (
                "d2-one-beyond",
                vec![
                    u64_parameter("d2_ordinal", ordinal_u64 - 17),
                    u64_parameter("side", 56),
                ],
            ),
            273..=400 => (
                "d3-one-beyond",
                vec![u64_parameter(
                    "seed",
                    5_134_751_402_299_490_304_u64
                        .checked_add(ordinal_u64 - 273)
                        .ok_or(Gate8Error::ResourceLimit)?,
                )],
            ),
            401 => (
                "missing-unit-one-beyond",
                vec![parameter("omitted_unit_ids", "u64-list", target_ids())],
            ),
            402..=404 => {
                let (errors, erasures) = [(2_u64, 0_u64), (1, 2), (0, 4)][ordinal - 402];
                (
                    "algebraic-one-beyond",
                    vec![
                        u64_parameter("erasures", erasures),
                        u64_parameter("errors", errors),
                        parameter("target_unit_ids", "u64-list", target_ids()),
                    ],
                )
            }
            405 => (
                "resource-route-one-beyond",
                vec![u64_parameter("declared_value", 268_435_457)],
            ),
            406 => (
                "resource-route-one-beyond",
                vec![u64_parameter("declared_value", 16_777_217)],
            ),
            407 => ("geometry-one-beyond", vec![u64_parameter("side", 2_056)]),
            _ => return Err(Gate8Error::Result),
        },
        _ => return Err(Gate8Error::Result),
    })
}

fn common_case_row_v1(
    core: &HierarchicalManifestationCore,
    family: usize,
    ordinal: usize,
    channel: &str,
    observation_sha256: &str,
    decoder_result_sha256: &str,
    result: &RecoveryResultV1,
) -> Result<ManifestValue> {
    let (operator, parameters) = case_shape_v1(core, family, ordinal)?;
    let states = result
        .sections
        .iter()
        .map(|section| (section.section_id, section.state))
        .collect::<BTreeMap<_, _>>();
    let expected_section_states = core
        .sections
        .iter()
        .map(|section| {
            object([
                (
                    "section_id",
                    ManifestValue::U64(u64::from(section.section_id)),
                ),
                (
                    "state",
                    string(section_state_name(
                        states
                            .get(&section.section_id)
                            .copied()
                            .unwrap_or(SectionState::Unknown),
                    )),
                ),
            ])
        })
        .collect();
    let expected_envelopes = core
        .sections
        .iter()
        .map(|section| {
            section
                .envelope()
                .map(|raw| (section.section_id, raw))
                .map_err(|_| Gate8Error::Candidate)
        })
        .collect::<Result<BTreeMap<_, _>>>()?;
    let wrong_accept_count = result
        .sections
        .iter()
        .filter(|section| {
            section.envelope.as_ref().is_some_and(|actual| {
                expected_envelopes
                    .get(&section.section_id)
                    .is_none_or(|expected| expected != actual)
            })
        })
        .count() as u64;
    Ok(object([
        ("case_id", string(&format!("D{family}-{ordinal:06}"))),
        ("family_id", string(&format!("D{family}"))),
        ("channel", string(channel)),
        ("operator", string(operator)),
        ("parameter_projection", ManifestValue::Array(parameters)),
        ("observation_sha256", string(observation_sha256)),
        ("decoder_result_sha256", string(decoder_result_sha256)),
        (
            "expected_artifact_state",
            string(artifact_state_name(result.artifact_state)),
        ),
        (
            "expected_section_states",
            ManifestValue::Array(expected_section_states),
        ),
        ("wrong_accept_count", ManifestValue::U64(wrong_accept_count)),
    ]))
}

/// Independently reconstruct the promoted v7 candidate from repository-owned
/// semantic inputs. No retained candidate artifact is accepted as input.
pub fn regenerate_current_r3_gates_one_through_five() -> Result<R3GateOneThroughFive> {
    let curriculum = include_bytes!("../../../spec/curriculum-v0.toml");
    let compiled = compile_slice_v0(SliceInputs {
        declaration: include_bytes!("../../../studies/m2/slice-v0.json"),
        content_fixture: include_bytes!("../../../conformance/content-v0.json"),
        chess_fixture: include_bytes!("../../../conformance/chess-v0.json"),
        game_set: include_bytes!("../../../reports/game-set-v0.bin"),
        content_spec: include_bytes!("../../../spec/content-v0.md"),
        constants: include_bytes!("../../../spec/constants-v0.toml"),
        curriculum,
    })
    .map_err(|_| Gate8Error::Candidate)?;
    build_r3_gate_one_through_five(
        include_bytes!("../../../spec/bootstrap-v1.md"),
        include_bytes!("../../../spec/profile-policy-v1.toml"),
        include_bytes!("../../../spec/damage-policy-v1.toml"),
        include_bytes!("../../../spec/route-data-v1.json"),
        include_bytes!("../../../spec/profile-limits-v1.toml"),
        include_bytes!("../../../spec/m2-r3-owner-promotion-v1.toml"),
        include_bytes!("../../../conformance/m2-r3-owner-v1.json"),
        &compiled,
        curriculum,
    )
    .map_err(|_| Gate8Error::Candidate)
}

fn route_prefix(
    core: &HierarchicalManifestationCore,
    profile_version: u16,
    package: &[u8],
) -> Result<Vec<u8>> {
    let routes = build_route_images(
        include_bytes!("../../../spec/route-data-v0.json"),
        profile_version,
        package,
        core.side,
        core.shell_width,
    )
    .map_err(|_| Gate8Error::Candidate)?;
    let sector = routes.sectors.first().ok_or(Gate8Error::Candidate)?;
    let bit_count =
        usize::try_from(sector.route_prefix_cells).map_err(|_| Gate8Error::ResourceLimit)?;
    if bit_count % 8 != 0 || bit_count > sector.bits.len() {
        return Err(Gate8Error::Candidate);
    }
    let mut raw = vec![0_u8; bit_count / 8];
    for (bit, value) in sector.bits[..bit_count].iter().copied().enumerate() {
        raw[bit / 8] |= value << (7 - bit % 8);
    }
    Ok(raw)
}

fn legacy_owner_u64(row: &toml::Value, key: &str) -> Result<u64> {
    row.get(key)
        .and_then(toml::Value::as_integer)
        .and_then(|value| u64::try_from(value).ok())
        .ok_or(Gate8Error::Candidate)
}

fn regenerate_legacy_v0_fixtures(
    core: &HierarchicalManifestationCore,
) -> Result<RegeneratedLegacyFixturesV0> {
    let owner: toml::Value = toml::from_str(
        std::str::from_utf8(include_bytes!("../../../spec/damage-policy-v0.toml"))
            .map_err(|_| Gate8Error::Candidate)?,
    )
    .map_err(|_| Gate8Error::Candidate)?;
    let rows = owner
        .get("decoder")
        .and_then(|value| value.get("obs_units_resource_profile"))
        .and_then(toml::Value::as_array)
        .ok_or(Gate8Error::Candidate)?;
    if owner.get("schema").and_then(toml::Value::as_str) != Some("golden-board.damage-policy/v0")
        || rows.len() != 6
    {
        return Err(Gate8Error::Candidate);
    }
    let mut facts = Vec::with_capacity(5);
    let mut v3_route_prefix = None;
    for profile_version in 2_u16..=6 {
        let profile = profile_by_version(profile_version).ok_or(Gate8Error::Candidate)?;
        let row = rows
            .get(usize::from(profile_version - 1))
            .ok_or(Gate8Error::Candidate)?;
        let row_table = row.as_table().ok_or(Gate8Error::Candidate)?;
        if row_table.len() != 5
            || legacy_owner_u64(row, "profile_version")? != u64::from(profile_version)
            || row.get("profile_id").and_then(toml::Value::as_str) != Some(profile.id)
        {
            return Err(Gate8Error::Candidate);
        }
        let expected_sha = row
            .get("recipient_package_sha256")
            .and_then(toml::Value::as_str)
            .filter(|value| lowercase_sha256(value))
            .ok_or(Gate8Error::Candidate)?;
        let package = match profile.transport {
            TransportFamily::Eh72Replicated => build_eh_recipe_package(profile_version),
            TransportFamily::Rs255_191 => build_rs_decoder_recipe_package(profile_version),
            TransportFamily::Eh72HierarchicalRepetition => return Err(Gate8Error::Candidate),
        }
        .map_err(|_| Gate8Error::Candidate)?;
        let decoded =
            decode_recipe_package(&package, profile_version).map_err(|_| Gate8Error::Candidate)?;
        if sha256(&package) != expected_sha
            || decoded.recipe_primitive_steps(30)
                != Some(legacy_owner_u64(row, "decoder_30_primitive_steps")?)
            || decoded.recipe_peak_scratch_bytes(30)
                != Some(legacy_owner_u64(row, "decoder_30_peak_scratch_bytes")?)
        {
            return Err(Gate8Error::Candidate);
        }
        let route_prefix = if profile_version == 3 {
            let prefix = route_prefix(core, profile_version, &package)?;
            v3_route_prefix = Some(prefix.clone());
            Some(sha256(&prefix))
        } else {
            None
        };
        facts.push(Gate8LegacyFixtureFactV0 {
            profile_version,
            recipient_package_sha256: expected_sha.to_owned(),
            route_prefix_sha256: route_prefix,
        });
    }
    Ok(RegeneratedLegacyFixturesV0 {
        facts,
        v3_route_prefix: v3_route_prefix.ok_or(Gate8Error::Candidate)?,
    })
}

/// Rebuild every legacy v2--v6 recipient package required by the v7 decoder
/// directly from frozen v0 owners. The sole route fixture consumed by the
/// owned D7 corpus is the independently rebuilt v3 prefix.
pub fn regenerate_r3_legacy_fixture_facts(
    core: &HierarchicalManifestationCore,
) -> Result<Vec<Gate8LegacyFixtureFactV0>> {
    Ok(regenerate_legacy_v0_fixtures(core)?.facts)
}

fn append_case(
    rows: &mut Vec<Gate8CaseFactV1>,
    core: &HierarchicalManifestationCore,
    family: usize,
    ordinal: usize,
    channel: &str,
    observation: Vec<u8>,
) -> Result<()> {
    if family > 7
        || !matches!(channel, "OBS_BITS" | "OBS_MATRIX" | "OBS_UNITS")
        || observation.len() > MAX_RAW_BITS + 8
    {
        return Err(Gate8Error::Observation);
    }
    if ordinal >= R3_GATE8_CASE_COUNTS[family] {
        return Err(Gate8Error::ResourceLimit);
    }
    let result = decode_observation_v1(channel, &observation);
    let (_, decoder_result_sha256) =
        render_decoder_result_v1(channel, &result).map_err(|_| Gate8Error::Result)?;
    let observation_sha256 = sha256(&observation);
    let common_case_row = common_case_row_v1(
        core,
        family,
        ordinal,
        channel,
        &observation_sha256,
        &decoder_result_sha256,
        &result,
    )?;
    rows.push(Gate8CaseFactV1 {
        family_id: format!("D{family}"),
        case_id: format!("D{family}-{ordinal:06}"),
        channel: channel.to_owned(),
        observation_sha256,
        decoder_result_sha256,
        common_case_row,
    });
    Ok(())
}

fn append_d0(rows: &mut Vec<Gate8CaseFactV1>, core: &HierarchicalManifestationCore) -> Result<()> {
    let side = usize::from(core.side);
    for transform in 0_u8..8 {
        for polarity in 0_u8..2 {
            let bits = transformed_clean_bits(
                &core.carrier_bits,
                side,
                EntryHypothesis {
                    transform,
                    polarity,
                },
            )
            .map_err(|_| Gate8Error::Observation)?;
            append_case(
                rows,
                core,
                0,
                usize::from(transform) * 2 + usize::from(polarity),
                "OBS_BITS",
                serialize_obs_bits(&bits).map_err(|_| Gate8Error::Observation)?,
            )?;
        }
    }
    Ok(())
}

fn exact_d2_placements(interior: usize) -> Result<Vec<Coordinate>> {
    let square = d2_square_side(interior);
    let domain = interior
        .checked_sub(square)
        .and_then(|value| value.checked_add(1))
        .ok_or(Gate8Error::ResourceLimit)?;
    let choices = [0_usize, domain / 2, domain - 1];
    let mut placements = Vec::with_capacity(256);
    let mut excluded = Vec::with_capacity(9);
    for row in choices {
        for column in choices {
            placements.push(Coordinate {
                row: row as u32,
                column: column as u32,
            });
            excluded.push(
                row.checked_mul(domain)
                    .and_then(|value| value.checked_add(column))
                    .ok_or(Gate8Error::ResourceLimit)?,
            );
        }
    }
    excluded.sort_unstable();
    let population = domain
        .checked_mul(domain)
        .and_then(|value| value.checked_sub(excluded.len()))
        .ok_or(Gate8Error::ResourceLimit)?;
    let sampled = sample_without_replacement(
        population,
        256_usize
            .checked_sub(placements.len())
            .ok_or(Gate8Error::ResourceLimit)?,
        5_134_751_402_299_490_304,
    )
    .map_err(|_| Gate8Error::Observation)?;
    for sampled in sampled {
        let mut flat = sampled;
        for excluded in &excluded {
            if *excluded <= flat {
                flat = flat.checked_add(1).ok_or(Gate8Error::ResourceLimit)?;
            }
        }
        placements.push(Coordinate {
            row: (flat / domain) as u32,
            column: (flat % domain) as u32,
        });
    }
    if placements.len() != 256 {
        return Err(Gate8Error::Observation);
    }
    Ok(placements)
}

fn append_d1_through_d6(
    rows: &mut Vec<Gate8CaseFactV1>,
    core: &HierarchicalManifestationCore,
) -> Result<()> {
    for sector in 0_u8..4 {
        append_case(
            rows,
            core,
            1,
            usize::from(sector),
            "OBS_MATRIX",
            erase_shell_sector_v1(core, sector, None).map_err(|_| Gate8Error::Observation)?,
        )?;
    }

    let square = d2_square_side(usize::from(core.mapping.interior_side));
    let placements = exact_d2_placements(usize::from(core.mapping.interior_side))?;
    for (ordinal, placement) in placements.iter().enumerate() {
        append_case(
            rows,
            core,
            2,
            ordinal,
            "OBS_MATRIX",
            erase_square_v1(core, *placement, square).map_err(|_| Gate8Error::Observation)?,
        )?;
    }

    for ordinal in 0_u64..128 {
        let coordinates = d3_coordinates_v1(core, 5_134_751_402_299_490_304 + ordinal, 0)
            .map_err(|_| Gate8Error::Observation)?;
        append_case(
            rows,
            core,
            3,
            ordinal as usize,
            "OBS_MATRIX",
            substitute_coordinates_v1(core, &coordinates).map_err(|_| Gate8Error::Observation)?,
        )?;
    }

    for unit_id in 1_u32..=1_841 {
        append_case(
            rows,
            core,
            4,
            unit_id as usize - 1,
            "OBS_UNITS",
            omitted_unit_observation_v1(core, &[unit_id]).map_err(|_| Gate8Error::Observation)?,
        )?;
    }

    for (ordinal, permutation) in d5_permutations(core.units.len())
        .map_err(|_| Gate8Error::Observation)?
        .into_iter()
        .enumerate()
    {
        append_case(
            rows,
            core,
            5,
            ordinal,
            "OBS_UNITS",
            permuted_unit_observation_v1(core, &permutation)
                .map_err(|_| Gate8Error::Observation)?,
        )?;
    }

    for sector in 0_u8..4 {
        for unit_id in 1_u32..=1_841 {
            append_case(
                rows,
                core,
                6,
                usize::from(sector) * 1_841 + unit_id as usize - 1,
                "OBS_MATRIX",
                erase_shell_sector_v1(core, sector, Some(unit_id))
                    .map_err(|_| Gate8Error::Observation)?,
            )?;
        }
    }
    Ok(())
}

fn append_d7(
    rows: &mut Vec<Gate8CaseFactV1>,
    core: &HierarchicalManifestationCore,
    legacy_v3_route_prefix: &[u8],
) -> Result<()> {
    let mut case_ordinal = 0_usize;
    macro_rules! append {
        ($channel:literal, $observation:expr $(,)?) => {{
            let ordinal = case_ordinal;
            case_ordinal = case_ordinal
                .checked_add(1)
                .ok_or(Gate8Error::ResourceLimit)?;
            append_case(rows, core, 7, ordinal, $channel, $observation)?;
        }};
    }
    for ordinal in 0_u8..3 {
        append!(
            "OBS_BITS",
            mapping_mutant_v1(core, ordinal).map_err(|_| Gate8Error::Observation)?,
        );
    }
    for normal_reflection in [false, true] {
        append!(
            "OBS_UNITS",
            local_check_mutant_v1(core, normal_reflection).map_err(|_| Gate8Error::Observation)?,
        );
    }
    for wrong_check_id in [true, false] {
        append!(
            "OBS_UNITS",
            section_check_mutant_v1(core, wrong_check_id).map_err(|_| Gate8Error::Observation)?,
        );
    }
    for ordinal in 0_u8..3 {
        append!(
            "OBS_UNITS",
            code_mutant_v1(core, ordinal).map_err(|_| Gate8Error::Observation)?,
        );
    }
    append!(
        "OBS_BITS",
        route_conflict_v1(core, legacy_v3_route_prefix).map_err(|_| Gate8Error::Observation)?,
    );
    for profile_version in 2_u16..=6 {
        append!(
            "OBS_UNITS",
            cross_profile_splice_v1(core, profile_version).map_err(|_| Gate8Error::Observation)?,
        );
    }
    append!(
        "OBS_UNITS",
        valid_replica_conflict_v1(core).map_err(|_| Gate8Error::Observation)?,
    );

    let interior = usize::from(core.mapping.interior_side);
    let square = d2_square_side(interior) + 1;
    for placement in exact_d2_placements(interior)? {
        let maximum = interior
            .checked_sub(square)
            .ok_or(Gate8Error::Observation)? as u32;
        append!(
            "OBS_MATRIX",
            erase_square_v1(
                core,
                Coordinate {
                    row: placement.row.min(maximum),
                    column: placement.column.min(maximum),
                },
                square,
            )
            .map_err(|_| Gate8Error::Observation)?,
        );
    }
    for ordinal in 0_u64..128 {
        let coordinates = d3_coordinates_v1(core, 5_134_751_402_299_490_304 + ordinal, 1)
            .map_err(|_| Gate8Error::Observation)?;
        append!(
            "OBS_MATRIX",
            substitute_coordinates_v1(core, &coordinates).map_err(|_| Gate8Error::Observation)?,
        );
    }
    append!(
        "OBS_UNITS",
        missing_unit_one_beyond_v1(core)
            .map_err(|_| Gate8Error::Observation)?
            .1,
    );
    for (errors, erasures) in [(2, 0), (1, 2), (0, 4)] {
        append!(
            "OBS_MATRIX",
            algebraic_one_beyond_v1(core, errors, erasures).map_err(|_| Gate8Error::Observation)?,
        );
    }
    for scratch in [false, true] {
        append!(
            "OBS_BITS",
            resource_route_one_beyond_v1(core, scratch).map_err(|_| Gate8Error::Observation)?,
        );
    }
    append!("OBS_BITS", geometry_one_beyond_v1());
    if case_ordinal != R3_GATE8_CASE_COUNTS[7] {
        return Err(Gate8Error::Result);
    }
    Ok(())
}

/// Regenerate and decode the exact 10,038-case promoted v7 corpus in frozen
/// family/case order. The output contains only hashes and case identity; raw
/// observations/results are bounded to one case at a time.
pub fn regenerate_r3_gate8_case_facts(
    core: &HierarchicalManifestationCore,
) -> Result<Vec<Gate8CaseFactV1>> {
    if core.profile.id != R3_PROFILE_ID || core.units.len() != 1_841 {
        return Err(Gate8Error::Candidate);
    }
    let legacy = regenerate_legacy_v0_fixtures(core)?;
    let mut rows = Vec::with_capacity(R3_GATE8_TOTAL_CASES);
    append_d0(&mut rows, core)?;
    append_d1_through_d6(&mut rows, core)?;
    append_d7(&mut rows, core, &legacy.v3_route_prefix)?;
    if rows.len() != R3_GATE8_TOTAL_CASES
        || R3_GATE8_CASE_COUNTS.iter().sum::<usize>() != rows.len()
        || rows.iter().enumerate().any(|(index, row)| {
            let mut first = 0;
            for (family, count) in R3_GATE8_CASE_COUNTS.iter().copied().enumerate() {
                let end = first + count;
                if (first..end).contains(&index) {
                    return row.family_id != format!("D{family}")
                        || row.case_id != format!("D{family}-{:06}", index - first);
                }
                first = end;
            }
            true
        })
    {
        return Err(Gate8Error::Result);
    }
    Ok(rows)
}

pub fn regenerate_current_r3_gate8_facts() -> Result<Gate8CandidateFactsV1> {
    let gates_one_through_five = regenerate_current_r3_gates_one_through_five()?;
    if gates_one_through_five.gate_passes != [true; 5] {
        return Err(Gate8Error::Candidate);
    }
    let case_facts = regenerate_r3_gate8_case_facts(&gates_one_through_five.core)?;
    Ok(Gate8CandidateFactsV1 {
        gates_one_through_five,
        case_facts,
    })
}

/// Render and strictly re-admit the complete transient Gate 6 bundle, then
/// independently recompute the Gate 7 proof from those exact bytes.
pub fn render_r3_gate_six_seven_facts(
    gates_one_through_five: &R3GateOneThroughFive,
    case_facts: &[Gate8CaseFactV1],
) -> Result<Gate8GateSixSevenFactsV1> {
    if case_facts.len() != R3_GATE8_TOTAL_CASES {
        return Err(Gate8Error::Result);
    }
    let mut cases: [Vec<ManifestValue>; 8] =
        std::array::from_fn(|family| Vec::with_capacity(R3_GATE8_CASE_COUNTS[family]));
    for row in case_facts {
        let family = row
            .family_id
            .strip_prefix('D')
            .and_then(|value| value.parse::<usize>().ok())
            .filter(|family| *family < 8)
            .ok_or(Gate8Error::Result)?;
        if row.case_id != format!("D{family}-{:06}", cases[family].len()) {
            return Err(Gate8Error::Result);
        }
        cases[family].push(row.common_case_row.clone());
    }
    if cases
        .iter()
        .zip(R3_GATE8_CASE_COUNTS)
        .any(|(rows, count)| rows.len() != count)
    {
        return Err(Gate8Error::Result);
    }
    let boundary_rows = boundary_kat_results_v1()
        .map_err(|_| Gate8Error::Result)?
        .into_iter()
        .map(|row| {
            object([
                ("kat_id", string(row.kat_id)),
                ("result_sha256", string(&row.sha256)),
                ("result", string(if row.passed { "pass" } else { "fail" })),
            ])
        })
        .collect::<Vec<_>>();
    let damage_bundle = render_damage_evidence_bundle_v1(
        &gates_one_through_five.artifacts.candidate_manifest,
        &gates_one_through_five.artifacts.ownership_ledger,
        &sha256(&gates_one_through_five.core.carrier_bytes),
        &cases,
        &boundary_rows,
    )
    .map_err(|_| Gate8Error::Result)?;
    let expected_shards = [1_usize, 1, 2, 3, 11, 1, 41, 3];
    let actual_shards = std::array::from_fn::<_, 8, _>(|family| {
        let prefix = format!("damage-D{family}-cases-");
        damage_bundle
            .case_shards
            .iter()
            .filter(|(name, _)| name.starts_with(&prefix))
            .count()
    });
    let aggregate_bytes = damage_bundle
        .family_manifests
        .iter()
        .chain(damage_bundle.case_shards.iter().map(|(_, raw)| raw))
        .try_fold(damage_bundle.damage_manifest.len(), |sum, raw| {
            sum.checked_add(raw.len()).ok_or(Gate8Error::ResourceLimit)
        })?;
    if actual_shards != expected_shards
        || damage_bundle.family_manifests.len() != 8
        || damage_bundle.case_shards.len() != 63
        || aggregate_bytes > 67_108_864
    {
        return Err(Gate8Error::Result);
    }
    let family_refs = damage_bundle
        .family_manifests
        .iter()
        .map(Vec::as_slice)
        .collect::<Vec<_>>();
    let shard_refs = damage_bundle
        .case_shards
        .iter()
        .map(|(_, raw)| raw.as_slice())
        .collect::<Vec<_>>();
    let independence_proof = build_independence_proof_from_bundle_v1(
        &gates_one_through_five.artifacts.candidate_manifest,
        &gates_one_through_five.artifacts.ownership_ledger,
        &damage_bundle.damage_manifest,
        &family_refs,
        &shard_refs,
    )
    .map_err(|_| Gate8Error::Result)?;
    if !independence_proof.passed {
        return Err(Gate8Error::Result);
    }
    Ok(Gate8GateSixSevenFactsV1 {
        damage_bundle,
        independence_proof,
    })
}

fn checked_extend_u32(raw: &mut Vec<u8>, value: u32) {
    raw.extend_from_slice(&value.to_be_bytes());
}

fn checked_extend_u64(raw: &mut Vec<u8>, value: usize) -> Result<()> {
    raw.extend_from_slice(
        &u64::try_from(value)
            .map_err(|_| Gate8Error::ResourceLimit)?
            .to_be_bytes(),
    );
    Ok(())
}

/// Independently extract each logical group once from the regenerated clean
/// carrier and render the exact owned semantic-content projection.
pub fn render_r3_semantic_content_projection(
    gates_one_through_five: &R3GateOneThroughFive,
) -> Result<Gate8SemanticContentV0> {
    let core = &gates_one_through_five.core;
    if core.sections.len() != 138 || core.units.len() != 1_841 {
        return Err(Gate8Error::Candidate);
    }
    let section_envelopes = core
        .sections
        .iter()
        .map(|section| {
            section
                .envelope()
                .map(|raw| (section.section_id, raw))
                .map_err(|_| Gate8Error::Candidate)
        })
        .collect::<Result<Vec<_>>>()?;
    if section_envelopes
        .windows(2)
        .any(|rows| rows[0].0 >= rows[1].0)
    {
        return Err(Gate8Error::Candidate);
    }

    let mut grouped = BTreeMap::<(u32, u16), Vec<(u8, u8, [u8; 191])>>::new();
    for (ordinal, unit) in core.units.iter().enumerate() {
        if unit.physical_unit_id as usize != ordinal + 1 {
            return Err(Gate8Error::Candidate);
        }
        let decoded = decode_eh_unit(
            &EhObservation {
                encoded: unit.encoded,
                erasures: Vec::new(),
            },
            7,
        )
        .map_err(|_| Gate8Error::Candidate)?;
        if decoded.quality != crate::candidate::DecodeQuality::Verified {
            return Err(Gate8Error::Candidate);
        }
        let common = decode_common_block(&decoded.common, 7).map_err(|_| Gate8Error::Candidate)?;
        if common.section_id != unit.section_id
            || common.semantic_copy_id != 0
            || common.fragment_index != unit.fragment_index
            || unit.replica_index >= unit.physical_replica_count
            || !matches!(unit.physical_replica_count, 1 | 2 | 5)
        {
            return Err(Gate8Error::Candidate);
        }
        grouped
            .entry((unit.section_id, unit.fragment_index))
            .or_default()
            .push((
                unit.replica_index,
                unit.physical_replica_count,
                decoded.common,
            ));
    }
    if grouped.len() != 1_279 {
        return Err(Gate8Error::Candidate);
    }

    let mut common_rows = Vec::<(u32, u16, [u8; 191])>::with_capacity(grouped.len());
    for ((section_id, fragment_index), mut lanes) in grouped {
        lanes.sort_by_key(|(replica, _, _)| *replica);
        let factor = lanes
            .first()
            .map(|(_, factor, _)| *factor)
            .ok_or(Gate8Error::Candidate)?;
        if lanes.len() != usize::from(factor)
            || lanes.iter().enumerate().any(|(replica, row)| {
                row.0 as usize != replica || row.1 != factor || row.2 != lanes[0].2
            })
        {
            return Err(Gate8Error::Candidate);
        }
        common_rows.push((section_id, fragment_index, lanes[0].2));
    }

    let mut section_preimage = b"golden-board:m2:gate8:section-envelopes:v0\0".to_vec();
    checked_extend_u64(&mut section_preimage, section_envelopes.len())?;
    for (section_id, envelope) in &section_envelopes {
        checked_extend_u32(&mut section_preimage, *section_id);
        checked_extend_u64(&mut section_preimage, envelope.len())?;
        section_preimage.extend_from_slice(envelope);
    }
    let mut common_preimage = b"golden-board:m2:gate8:common-plain-blocks:v0\0".to_vec();
    checked_extend_u64(&mut common_preimage, common_rows.len())?;
    let mut fragments_by_section = BTreeMap::<u32, Vec<FragmentWitness>>::new();
    for (section_id, fragment_index, common) in &common_rows {
        checked_extend_u32(&mut common_preimage, *section_id);
        checked_extend_u32(&mut common_preimage, u32::from(*fragment_index));
        checked_extend_u64(&mut common_preimage, common.len())?;
        common_preimage.extend_from_slice(common);
        fragments_by_section
            .entry(*section_id)
            .or_default()
            .push(FragmentWitness {
                raw_block: *common,
                quality: RecoveryQuality::Verified,
            });
    }
    for (section_id, envelope) in &section_envelopes {
        let assembled = assemble_semantic_copy(
            fragments_by_section
                .get(section_id)
                .ok_or(Gate8Error::Candidate)?,
            7,
        )
        .map_err(|_| Gate8Error::Candidate)?;
        if assembled.envelope != *envelope {
            return Err(Gate8Error::Candidate);
        }
    }

    let section_by_id = core
        .sections
        .iter()
        .map(|section| (section.section_id, section))
        .collect::<BTreeMap<_, _>>();
    let tier_section = section_by_id.get(&3).ok_or(Gate8Error::Candidate)?;
    let tier = decode_tier_frame(&tier_section.payload, 3).map_err(|_| Gate8Error::Candidate)?;
    let bodies = tier
        .body_section_ids
        .iter()
        .map(|section_id| {
            section_by_id
                .get(section_id)
                .map(|section| (*section_id, section.payload.clone()))
                .ok_or(Gate8Error::Candidate)
        })
        .collect::<Result<BTreeMap<_, _>>>()?;
    let content_stream =
        assemble_content_stream(&tier, &bodies).map_err(|_| Gate8Error::Candidate)?;
    let value = object([
        ("candidate_id", string(R3_PROFILE_ID)),
        (
            "common_plain_blocks_sha256",
            string(&sha256(&common_preimage)),
        ),
        ("content_stream_sha256", string(&sha256(&content_stream))),
        (
            "schema",
            string("golden-board.m2-gate8-semantic-content/v0"),
        ),
        (
            "section_envelopes_sha256",
            string(&sha256(&section_preimage)),
        ),
        (
            "semantic_envelope_sha256",
            string(&sha256(gates_one_through_five.semantic.canonical_bytes())),
        ),
    ]);
    let canonical_bytes = serialize_manifest(&value).map_err(|_| Gate8Error::Result)?;
    if canonical_bytes.len() > GATE8_MANIFEST_BYTES_MAX {
        return Err(Gate8Error::ResourceLimit);
    }
    Ok(Gate8SemanticContentV0 {
        canonical_bytes,
        content_stream,
    })
}

pub fn render_r3_damage_inventory(bundle: &RenderedDamageEvidenceBundleV1) -> Result<Vec<u8>> {
    let mut files = Vec::<(String, &[u8])>::with_capacity(GATE8_DAMAGE_FILE_COUNT);
    files.push(("damage-manifest.json".to_owned(), &bundle.damage_manifest));
    if bundle.family_manifests.len() != 8 || bundle.case_shards.len() != 63 {
        return Err(Gate8Error::Result);
    }
    for (family, raw) in bundle.family_manifests.iter().enumerate() {
        files.push((format!("damage-D{family}.json"), raw));
    }
    for (path, raw) in &bundle.case_shards {
        files.push((path.clone(), raw));
    }
    files.sort_by(|left, right| left.0.as_bytes().cmp(right.0.as_bytes()));
    let aggregate = files.iter().try_fold(0_usize, |sum, (path, raw)| {
        if path.is_empty()
            || path.len() > 255
            || !path.is_ascii()
            || raw.is_empty()
            || raw.len() > GATE8_MANIFEST_BYTES_MAX
        {
            return Err(Gate8Error::Result);
        }
        sum.checked_add(raw.len()).ok_or(Gate8Error::ResourceLimit)
    })?;
    if files.len() != GATE8_DAMAGE_FILE_COUNT
        || aggregate > GATE8_DAMAGE_AGGREGATE_BYTES_MAX
        || files.windows(2).any(|rows| rows[0].0 >= rows[1].0)
    {
        return Err(Gate8Error::Result);
    }
    let value = object([
        ("candidate_id", string(R3_PROFILE_ID)),
        (
            "file_rows",
            ManifestValue::Array(
                files
                    .into_iter()
                    .map(|(path, raw)| {
                        object([
                            ("byte_length", ManifestValue::U64(raw.len() as u64)),
                            ("path", string(&path)),
                            ("sha256", string(&sha256(raw))),
                        ])
                    })
                    .collect(),
            ),
        ),
        (
            "schema",
            string("golden-board.m2-gate8-damage-inventory/v0"),
        ),
    ]);
    let raw = serialize_manifest(&value).map_err(|_| Gate8Error::Result)?;
    if raw.len() > GATE8_MANIFEST_BYTES_MAX {
        return Err(Gate8Error::ResourceLimit);
    }
    Ok(raw)
}

pub fn render_rust_gate8_receipt(
    gates_one_through_five: &R3GateOneThroughFive,
    gates_six_seven: &Gate8GateSixSevenFactsV1,
    producer_id: &'static str,
) -> Result<Gate8ProducerReceiptV0> {
    if !matches!(producer_id, "native-rust" | "linux-rust") {
        return Err(Gate8Error::Result);
    }
    let semantic = render_r3_semantic_content_projection(gates_one_through_five)?;
    let damage_inventory = render_r3_damage_inventory(&gates_six_seven.damage_bundle)?;
    let rows = vec![
        Gate8ArtifactFactV0 {
            artifact_id: "semantic-content-projection",
            sha256: sha256(&semantic.canonical_bytes),
        },
        Gate8ArtifactFactV0 {
            artifact_id: "candidate-manifest",
            sha256: sha256(&gates_one_through_five.artifacts.candidate_manifest),
        },
        Gate8ArtifactFactV0 {
            artifact_id: "carrier",
            sha256: sha256(&gates_one_through_five.core.carrier_bytes),
        },
        Gate8ArtifactFactV0 {
            artifact_id: "ownership-ledger",
            sha256: sha256(&gates_one_through_five.artifacts.ownership_ledger),
        },
        Gate8ArtifactFactV0 {
            artifact_id: "capacity-ledger",
            sha256: sha256(&gates_one_through_five.artifacts.capacity_ledger),
        },
        Gate8ArtifactFactV0 {
            artifact_id: "density-ledger",
            sha256: sha256(&gates_one_through_five.artifacts.density_ledger),
        },
        Gate8ArtifactFactV0 {
            artifact_id: "damage-bundle-inventory",
            sha256: sha256(&damage_inventory),
        },
        Gate8ArtifactFactV0 {
            artifact_id: "independence-proof",
            sha256: sha256(&gates_six_seven.independence_proof.canonical_bytes),
        },
    ];
    let value = object([
        (
            "artifact_rows",
            ManifestValue::Array(
                rows.iter()
                    .map(|row| {
                        object([
                            ("artifact_id", string(row.artifact_id)),
                            ("sha256", string(&row.sha256)),
                        ])
                    })
                    .collect(),
            ),
        ),
        ("candidate_id", string(R3_PROFILE_ID)),
        ("producer_id", string(producer_id)),
        (
            "schema",
            string("golden-board.m2-gate8-producer-receipt/v0"),
        ),
    ]);
    let canonical_bytes = serialize_manifest(&value).map_err(|_| Gate8Error::Result)?;
    validate_rust_gate8_receipt(&canonical_bytes, producer_id, &rows)?;
    Ok(Gate8ProducerReceiptV0 {
        producer_id,
        artifact_rows: rows,
        canonical_bytes,
    })
}

pub fn render_native_rust_gate8_receipt(
    gates_one_through_five: &R3GateOneThroughFive,
    gates_six_seven: &Gate8GateSixSevenFactsV1,
) -> Result<Gate8ProducerReceiptV0> {
    render_rust_gate8_receipt(gates_one_through_five, gates_six_seven, "native-rust")
}

pub fn validate_rust_gate8_receipt(
    raw: &[u8],
    producer_id: &str,
    expected_rows: &[Gate8ArtifactFactV0],
) -> Result<()> {
    if raw.is_empty()
        || raw.len() > GATE8_MANIFEST_BYTES_MAX
        || expected_rows.len() != 8
        || !matches!(producer_id, "native-rust" | "linux-rust")
    {
        return Err(Gate8Error::Result);
    }
    let expected = serialize_manifest(&object([
        (
            "artifact_rows",
            ManifestValue::Array(
                expected_rows
                    .iter()
                    .map(|row| {
                        object([
                            ("artifact_id", string(row.artifact_id)),
                            ("sha256", string(&row.sha256)),
                        ])
                    })
                    .collect(),
            ),
        ),
        ("candidate_id", string(R3_PROFILE_ID)),
        ("producer_id", string(producer_id)),
        (
            "schema",
            string("golden-board.m2-gate8-producer-receipt/v0"),
        ),
    ]))
    .map_err(|_| Gate8Error::Result)?;
    validate_canonical_manifest(raw).map_err(|_| Gate8Error::Result)?;
    if raw != expected {
        return Err(Gate8Error::Result);
    }
    Ok(())
}

pub fn validate_native_rust_gate8_receipt(
    raw: &[u8],
    expected_rows: &[Gate8ArtifactFactV0],
) -> Result<()> {
    validate_rust_gate8_receipt(raw, "native-rust", expected_rows)
}

pub fn admit_gate8_producer_receipt(
    raw: &[u8],
    expected_producer_id: &str,
) -> Result<AdmittedGate8ProducerReceiptV0> {
    if raw.is_empty()
        || raw.len() > GATE8_MANIFEST_BYTES_MAX
        || !GATE8_PRODUCER_IDS.contains(&expected_producer_id)
    {
        return Err(Gate8Error::Result);
    }
    let value = validate_canonical_manifest(raw).map_err(|_| Gate8Error::Result)?;
    let root = manifest_object_ref(&value)?;
    if !exact_manifest_keys(
        root,
        &["artifact_rows", "candidate_id", "producer_id", "schema"],
    ) || manifest_string_field(root, "schema")? != "golden-board.m2-gate8-producer-receipt/v0"
        || manifest_string_field(root, "candidate_id")? != R3_PROFILE_ID
        || manifest_string_field(root, "producer_id")? != expected_producer_id
    {
        return Err(Gate8Error::Result);
    }
    let Some(ManifestValue::Array(rows)) = root.get("artifact_rows") else {
        return Err(Gate8Error::Result);
    };
    if rows.len() != GATE8_ARTIFACT_IDS.len() {
        return Err(Gate8Error::Result);
    }
    let artifact_rows = rows
        .iter()
        .enumerate()
        .map(|(ordinal, row)| {
            let row = manifest_object_ref(row)?;
            let artifact_id = manifest_string_field(row, "artifact_id")?;
            let sha = manifest_string_field(row, "sha256")?;
            if !exact_manifest_keys(row, &["artifact_id", "sha256"])
                || artifact_id != GATE8_ARTIFACT_IDS[ordinal]
                || !lowercase_sha256(sha)
            {
                return Err(Gate8Error::Result);
            }
            Ok((artifact_id.to_owned(), sha.to_owned()))
        })
        .collect::<Result<Vec<_>>>()?;
    Ok(AdmittedGate8ProducerReceiptV0 {
        producer_id: expected_producer_id.to_owned(),
        artifact_rows,
    })
}

pub fn render_gate8_cross_language_manifest(
    retained_candidate_manifest_sha256: &str,
    producer_receipts: [&[u8]; 4],
) -> Result<Gate8CrossLanguageManifestV0> {
    if !lowercase_sha256(retained_candidate_manifest_sha256) {
        return Err(Gate8Error::Result);
    }
    let admitted = producer_receipts
        .into_iter()
        .zip(GATE8_PRODUCER_IDS)
        .map(|(raw, producer_id)| admit_gate8_producer_receipt(raw, producer_id))
        .collect::<Result<Vec<_>>>()?;
    let mut passed = true;
    let rows = GATE8_ARTIFACT_IDS
        .iter()
        .enumerate()
        .map(|(ordinal, artifact_id)| {
            let hashes = admitted
                .iter()
                .map(|receipt| receipt.artifact_rows[ordinal].1.as_str())
                .collect::<Vec<_>>();
            let row_passed = hashes.iter().all(|value| *value == hashes[0]);
            passed &= row_passed;
            object([
                ("artifact_id", string(artifact_id)),
                ("native_python_sha256", string(hashes[0])),
                ("native_rust_sha256", string(hashes[1])),
                ("linux_python_sha256", string(hashes[2])),
                ("linux_rust_sha256", string(hashes[3])),
                ("result", string(if row_passed { "pass" } else { "fail" })),
            ])
        })
        .collect::<Vec<_>>();
    let value = object([
        ("artifact_rows", ManifestValue::Array(rows)),
        ("candidate_id", string(R3_PROFILE_ID)),
        (
            "candidate_manifest_sha256",
            string(retained_candidate_manifest_sha256),
        ),
        ("schema", string("golden-board.m2-cross-language/v0")),
        (
            "summary",
            object([
                ("artifact_count", ManifestValue::U64(8)),
                ("result", string(if passed { "pass" } else { "fail" })),
            ]),
        ),
    ]);
    let canonical_bytes = serialize_manifest(&value).map_err(|_| Gate8Error::Result)?;
    if canonical_bytes.len() > GATE8_MANIFEST_BYTES_MAX {
        return Err(Gate8Error::ResourceLimit);
    }
    Ok(Gate8CrossLanguageManifestV0 {
        canonical_bytes,
        passed,
    })
}

pub fn validate_gate8_cross_language_manifest(
    raw: &[u8],
    retained_candidate_manifest_sha256: &str,
    producer_receipts: [&[u8]; 4],
) -> Result<bool> {
    validate_canonical_manifest(raw).map_err(|_| Gate8Error::Result)?;
    let expected = render_gate8_cross_language_manifest(
        retained_candidate_manifest_sha256,
        producer_receipts,
    )?;
    if raw != expected.canonical_bytes {
        return Err(Gate8Error::Result);
    }
    Ok(expected.passed)
}

fn manifest_object_ref(value: &ManifestValue) -> Result<&BTreeMap<String, ManifestValue>> {
    let ManifestValue::Object(value) = value else {
        return Err(Gate8Error::Result);
    };
    Ok(value)
}

fn manifest_u64_field(value: &BTreeMap<String, ManifestValue>, key: &str) -> Result<u64> {
    let Some(ManifestValue::U64(value)) = value.get(key) else {
        return Err(Gate8Error::Result);
    };
    Ok(*value)
}

fn exact_manifest_keys(value: &BTreeMap<String, ManifestValue>, keys: &[&str]) -> bool {
    value.len() == keys.len() && keys.iter().all(|key| value.contains_key(*key))
}

fn manifest_string_field<'a>(
    value: &'a BTreeMap<String, ManifestValue>,
    key: &str,
) -> Result<&'a str> {
    let Some(ManifestValue::String(value)) = value.get(key) else {
        return Err(Gate8Error::Result);
    };
    Ok(value)
}

fn lowercase_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

/// Independently derive the exact 19-field active-candidate metric row from
/// the validated recipe graph, route owner, regenerated carrier, and capacity
/// ledger.
pub fn derive_r3_candidate_metrics(
    gates_one_through_five: &R3GateOneThroughFive,
) -> Result<Gate8CandidateMetricsV0> {
    let package_raw = build_r3_recipe_package().map_err(|_| Gate8Error::Candidate)?;
    let package = decode_recipe_package(&package_raw, 7).map_err(|_| Gate8Error::Candidate)?;
    let package_metrics = r3_recipe_package_metrics().map_err(|_| Gate8Error::Candidate)?;
    let operation_kind_count = u64::try_from(
        package
            .opcode_ids()
            .collect::<std::collections::BTreeSet<_>>()
            .len(),
    )
    .map_err(|_| Gate8Error::ResourceLimit)?;
    let dependency_depth = package.dependency_depth().ok_or(Gate8Error::Candidate)?;
    let route = generate_r3_route_owner().map_err(|_| Gate8Error::Candidate)?;
    if route.draft.recipient_package != package_raw
        || route.draft.recipient_package_sha256 != sha256(&package_raw)
    {
        return Err(Gate8Error::Candidate);
    }
    let capacity = validate_canonical_manifest(&gates_one_through_five.artifacts.capacity_ledger)
        .map_err(|_| Gate8Error::Result)?;
    let capacity = manifest_object_ref(&capacity)?;
    let ledger = capacity
        .get("ledger")
        .ok_or(Gate8Error::Result)
        .and_then(manifest_object_ref)?;
    let route_data =
        validate_canonical_manifest(include_bytes!("../../../spec/route-data-v1.json"))
            .map_err(|_| Gate8Error::Candidate)?;
    let route_data = manifest_object_ref(&route_data)?;
    let convention_count = match route_data.get("facts") {
        Some(ManifestValue::Array(rows)) => rows.len() as u64,
        _ => return Err(Gate8Error::Candidate),
    };
    let side = u64::from(gates_one_through_five.core.side);
    let width = u64::from(gates_one_through_five.core.shell_width);
    let total_bits = side.checked_mul(side).ok_or(Gate8Error::ResourceLimit)?;
    let shell_cells = 4_u64
        .checked_mul(width)
        .and_then(|value| value.checked_mul(side.checked_sub(width)?))
        .ok_or(Gate8Error::ResourceLimit)?;
    let worked_example_cells = route
        .draft
        .worked_record_bytes_by_sector
        .iter()
        .try_fold(0_u64, |sum, value| sum.checked_add(*value))
        .and_then(|value| value.checked_mul(8))
        .ok_or(Gate8Error::ResourceLimit)?;
    let held_out_example_cells = route
        .draft
        .held_out_record_bytes_by_sector
        .iter()
        .try_fold(0_u64, |sum, value| sum.checked_add(*value))
        .and_then(|value| value.checked_mul(8))
        .ok_or(Gate8Error::ResourceLimit)?;
    let protected_bits = u64::try_from(gates_one_through_five.core.units.len())
        .ok()
        .and_then(|units| units.checked_mul(1_728))
        .ok_or(Gate8Error::ResourceLimit)?;
    let plain_bits = 1_279_u64
        .checked_mul(191)
        .and_then(|value| value.checked_mul(8))
        .ok_or(Gate8Error::ResourceLimit)?;
    let carrier_bytes = total_bits / 8;
    Ok(Gate8CandidateMetricsV0 {
        operation_kind_count,
        table_count: u64::from(u16::from_be_bytes(
            package_raw[18..20]
                .try_into()
                .map_err(|_| Gate8Error::Candidate)?,
        )),
        table_bytes: u64::from(package_metrics.table_payload_bytes),
        graph_nodes: u64::from(package_metrics.node_count),
        graph_edges: u64::from(package_metrics.edge_count),
        dependency_depth,
        recipe_cells: manifest_u64_field(ledger, "shell_recipe_cells")?,
        worked_example_cells,
        held_out_example_cells,
        shell_cells,
        convention_count,
        plain_bits,
        protected_bits,
        reserve_bits: 7_141 * 8,
        total_bits,
        robustness_ppm: 0,
        worst_case_work_units: manifest_u64_field(ledger, "worst_case_work_units")?,
        scratch_bytes: manifest_u64_field(ledger, "scratch_bytes")?,
        remaining_reserve_bytes: 524_288_u64
            .checked_sub(carrier_bytes)
            .ok_or(Gate8Error::Candidate)?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn promoted_candidate_fact_identities_are_independent_and_exact() {
        let result = regenerate_current_r3_gates_one_through_five().unwrap();
        assert_eq!(result.gate_passes, [true; 5]);
        assert_eq!(result.core.profile.id, R3_PROFILE_ID);
        assert_eq!(result.core.units.len(), 1_841);
        assert_eq!(result.core.carrier_bytes.len(), 520_204);
        assert_eq!(
            sha256(&result.core.carrier_bytes),
            "c6309da5f199a237b8fc79292a5135581ad0f9b517fbe9516770ebaf084d49b0"
        );
        assert_eq!(
            sha256(&result.artifacts.candidate_manifest),
            "38839aa28561ff2bec0997a80d8dc938e876526c25f40e23b6a78844f8fc1d86"
        );
    }

    #[test]
    fn one_exact_case_from_each_family_is_recomputed() {
        let result = regenerate_current_r3_gates_one_through_five().unwrap();
        let core = &result.core;
        let mut rows = Vec::new();
        append_case(
            &mut rows,
            core,
            0,
            0,
            "OBS_BITS",
            core.carrier_bytes.clone(),
        )
        .unwrap();
        append_case(
            &mut rows,
            core,
            1,
            0,
            "OBS_MATRIX",
            erase_shell_sector_v1(core, 0, None).unwrap(),
        )
        .unwrap();
        let placement = exact_d2_placements(usize::from(core.mapping.interior_side)).unwrap()[0];
        append_case(
            &mut rows,
            core,
            2,
            0,
            "OBS_MATRIX",
            erase_square_v1(
                core,
                placement,
                d2_square_side(usize::from(core.mapping.interior_side)),
            )
            .unwrap(),
        )
        .unwrap();
        let coordinates = d3_coordinates_v1(core, 5_134_751_402_299_490_304, 0).unwrap();
        append_case(
            &mut rows,
            core,
            3,
            0,
            "OBS_MATRIX",
            substitute_coordinates_v1(core, &coordinates).unwrap(),
        )
        .unwrap();
        append_case(
            &mut rows,
            core,
            4,
            0,
            "OBS_UNITS",
            omitted_unit_observation_v1(core, &[1]).unwrap(),
        )
        .unwrap();
        append_case(
            &mut rows,
            core,
            5,
            0,
            "OBS_UNITS",
            permuted_unit_observation_v1(core, &d5_permutations(core.units.len()).unwrap()[0])
                .unwrap(),
        )
        .unwrap();
        append_case(
            &mut rows,
            core,
            6,
            0,
            "OBS_MATRIX",
            erase_shell_sector_v1(core, 0, Some(1)).unwrap(),
        )
        .unwrap();
        append_case(
            &mut rows,
            core,
            7,
            405,
            "OBS_BITS",
            resource_route_one_beyond_v1(core, false).unwrap(),
        )
        .unwrap();
        assert_eq!(rows.len(), 8);
        assert_eq!(
            rows.iter()
                .map(|row| (
                    row.observation_sha256.as_str(),
                    row.decoder_result_sha256.as_str()
                ))
                .collect::<Vec<_>>(),
            vec![
                (
                    "c6309da5f199a237b8fc79292a5135581ad0f9b517fbe9516770ebaf084d49b0",
                    "19b0672e7e05e3740439eab0f2055a618fb909f59ab65421d8213aa1ae16252c",
                ),
                (
                    "7e3db65a92d1fb4e22dbecee4dd43fbf29d9cf1427ef92a3c9eae3aa8f3063f8",
                    "da6d653a2c25a57c75bcbd9caa45b433fc92b6e39f0dde9d55def75ae1e0f3a4",
                ),
                (
                    "f131b068ab22ba6178d6db660cb89025132b1535cede2fbfe0699de95b6c26d6",
                    "5a16f1aed3b8089820f28d4fa610f77c0df9a2124cf3ebfc845decba0a91358b",
                ),
                (
                    "9cba9e3a83064ba6799ba8949304289d0c033b41457cc65b0f256a9f91f91249",
                    "2410d00e3712ce755e9b074deab4e0fe1801548909e494cdcd43d1f2f54abbc8",
                ),
                (
                    "40bf1c82170bfee99f31857663abb335681fade56af164f5df423ed2221d1a3f",
                    "f941d696d5015e127d4e2bd64b29c276b641af93f750ed6ca1b89029488f50fd",
                ),
                (
                    "6731afd616ed31cedce6223fc56e553d0d006c792c317c6d58af588a8efb8b1a",
                    "594c98172e44db5531c019ffe2d479b6812df0a39c9022ede4770f74a9c0cebc",
                ),
                (
                    "251bb3fcb8812dddbf0b0ade902cb8ff67044d174f7def9277fc86d786dd7f55",
                    "bf6c571bb92c9b7126d567ef747f540271eccab29f7774c6b8a558eb0e2ca871",
                ),
                (
                    "70194108203dda92e57380a706f7d7dbae70f60fec2fe41c908604f3fd597427",
                    "78253f50589a2cb22fe53f38d4959c58ec3483db3e0f74574a1b06634322e71d",
                ),
            ]
        );
    }

    #[test]
    fn d2_rejection_sample_excludes_anchors_before_sampling() {
        let placements = exact_d2_placements(1_784).unwrap();
        assert_eq!(placements.len(), 256);
        assert_eq!(
            placements[8],
            Coordinate {
                row: 1_729,
                column: 1_729
            }
        );
        assert_eq!(
            placements[9],
            Coordinate {
                row: 47,
                column: 628
            }
        );
        assert_eq!(
            placements[10],
            Coordinate {
                row: 1_313,
                column: 1_428
            }
        );
    }

    #[test]
    fn exact_gate8_candidate_metrics_are_graph_derived() {
        let gates = regenerate_current_r3_gates_one_through_five().unwrap();
        assert_eq!(
            derive_r3_candidate_metrics(&gates).unwrap(),
            Gate8CandidateMetricsV0 {
                operation_kind_count: 23,
                table_count: 13,
                table_bytes: 1_470,
                graph_nodes: 699,
                graph_edges: 1_087,
                dependency_depth: 36,
                recipe_cells: 830_016,
                worked_example_cells: 11_712,
                held_out_example_cells: 11_712,
                shell_cells: 978_944,
                convention_count: 12,
                plain_bits: 1_954_312,
                protected_bits: 3_181_248,
                reserve_bits: 57_128,
                total_bits: 4_161_600,
                robustness_ppm: 0,
                worst_case_work_units: 4_484_682_504,
                scratch_bytes: 6_163,
                remaining_reserve_bytes: 4_088,
            }
        );
    }

    #[test]
    fn semantic_projection_decodes_every_clean_lane_and_section() {
        let gates = regenerate_current_r3_gates_one_through_five().unwrap();
        let semantic = render_r3_semantic_content_projection(&gates).unwrap();
        assert_eq!(semantic.content_stream.len(), 13_644);
        assert_eq!(
            sha256(&semantic.content_stream),
            "de7e22f0aa4316d9f32d9435287dd19bd6c04519aae1dc9bd816613f26929671"
        );
        assert_eq!(semantic.canonical_bytes.len(), 476);
        assert_eq!(
            sha256(&semantic.canonical_bytes),
            "1e9ada4562dc31dc40e703a76d5159b534a247b221546957f9110bf21e47a645"
        );
        let value = validate_canonical_manifest(&semantic.canonical_bytes).unwrap();
        let value = manifest_object_ref(&value).unwrap();
        assert_eq!(
            value.get("schema"),
            Some(&string("golden-board.m2-gate8-semantic-content/v0"))
        );
        assert_eq!(
            value.get("content_stream_sha256"),
            Some(&string(&sha256(&semantic.content_stream)))
        );
        assert_eq!(
            value.get("semantic_envelope_sha256"),
            Some(&string(gates.semantic.sha256()))
        );
        assert_eq!(
            value.get("common_plain_blocks_sha256"),
            Some(&string(
                "f3605dc34f8af3694c21a323e9a212c67b06e1e03be065f60db174abf26dff1b"
            ))
        );
        assert_eq!(
            value.get("section_envelopes_sha256"),
            Some(&string(
                "614cd587e1061cd1f780cd7972f4d9ce92d49307eba173dcfd9c83619605b103"
            ))
        );
    }

    #[test]
    fn legacy_gate8_fixtures_are_rebuilt_only_from_v0_owners() {
        let gates = regenerate_current_r3_gates_one_through_five().unwrap();
        let facts = regenerate_r3_legacy_fixture_facts(&gates.core).unwrap();
        assert_eq!(
            facts
                .iter()
                .map(|row| (row.profile_version, row.recipient_package_sha256.as_str()))
                .collect::<Vec<_>>(),
            vec![
                (
                    2,
                    "cce1758613d7f10278533409e07103ae15162972fcf30030e17c233e39664011"
                ),
                (
                    3,
                    "8c91ba74f9bbed97aed89191e8d8d30a9a0c4d32bd5ac98b63a4c19ed71fb0e7"
                ),
                (
                    4,
                    "de237fcd9d53581710404bd8b00152cb68f50adef48e715fdd4572e786bae4b8"
                ),
                (
                    5,
                    "2dd94f23f63bd4fbeb8d56565a9cc9a7e0a2054d3483e364cfb60e7751058e91"
                ),
                (
                    6,
                    "1c05a1f57394d292487f46561492619358fe2d12e42e3a20194d5917f351e555"
                ),
            ]
        );
        assert_eq!(
            facts
                .iter()
                .map(|row| row.route_prefix_sha256.as_deref())
                .collect::<Vec<_>>(),
            vec![
                None,
                Some("d343c6e86d06e669c8d287bb928373bca9a03471efeae910231f268eb677af4d"),
                None,
                None,
                None
            ]
        );
    }

    #[test]
    fn producer_receipt_parser_rejects_unknown_reordered_and_wrong_producer() {
        const IDS: [&str; 8] = [
            "semantic-content-projection",
            "candidate-manifest",
            "carrier",
            "ownership-ledger",
            "capacity-ledger",
            "density-ledger",
            "damage-bundle-inventory",
            "independence-proof",
        ];
        let rows = IDS
            .iter()
            .enumerate()
            .map(|(ordinal, artifact_id)| Gate8ArtifactFactV0 {
                artifact_id,
                sha256: format!("{ordinal:064x}"),
            })
            .collect::<Vec<_>>();
        let valid = serialize_manifest(&object([
            (
                "artifact_rows",
                ManifestValue::Array(
                    rows.iter()
                        .map(|row| {
                            object([
                                ("artifact_id", string(row.artifact_id)),
                                ("sha256", string(&row.sha256)),
                            ])
                        })
                        .collect(),
                ),
            ),
            ("candidate_id", string(R3_PROFILE_ID)),
            ("producer_id", string("native-rust")),
            (
                "schema",
                string("golden-board.m2-gate8-producer-receipt/v0"),
            ),
        ]))
        .unwrap();
        validate_native_rust_gate8_receipt(&valid, &rows).unwrap();

        let mut wrong_producer = validate_canonical_manifest(&valid).unwrap();
        let ManifestValue::Object(root) = &mut wrong_producer else {
            unreachable!()
        };
        root.insert("producer_id".to_owned(), string("linux-rust"));
        let wrong_producer = serialize_manifest(&wrong_producer).unwrap();
        validate_rust_gate8_receipt(&wrong_producer, "linux-rust", &rows).unwrap();
        assert_eq!(
            validate_native_rust_gate8_receipt(&wrong_producer, &rows),
            Err(Gate8Error::Result)
        );
        assert_eq!(
            validate_rust_gate8_receipt(&wrong_producer, "linux-python", &rows),
            Err(Gate8Error::Result)
        );

        let mut unknown = validate_canonical_manifest(&valid).unwrap();
        let ManifestValue::Object(root) = &mut unknown else {
            unreachable!()
        };
        root.insert("extra".to_owned(), ManifestValue::Bool(false));
        let unknown = serialize_manifest(&unknown).unwrap();
        assert_eq!(
            validate_native_rust_gate8_receipt(&unknown, &rows),
            Err(Gate8Error::Result)
        );

        let mut reordered = rows.clone();
        reordered.swap(0, 1);
        assert_eq!(
            validate_native_rust_gate8_receipt(&valid, &reordered),
            Err(Gate8Error::Result)
        );

        let render_receipt = |producer_id: &str, rows: &[Gate8ArtifactFactV0]| {
            serialize_manifest(&object([
                (
                    "artifact_rows",
                    ManifestValue::Array(
                        rows.iter()
                            .map(|row| {
                                object([
                                    ("artifact_id", string(row.artifact_id)),
                                    ("sha256", string(&row.sha256)),
                                ])
                            })
                            .collect(),
                    ),
                ),
                ("candidate_id", string(R3_PROFILE_ID)),
                ("producer_id", string(producer_id)),
                (
                    "schema",
                    string("golden-board.m2-gate8-producer-receipt/v0"),
                ),
            ]))
            .unwrap()
        };
        let receipts = GATE8_PRODUCER_IDS
            .iter()
            .map(|producer| render_receipt(producer, &rows))
            .collect::<Vec<_>>();
        let receipt_refs: [&[u8]; 4] = std::array::from_fn(|index| receipts[index].as_slice());
        let cross = render_gate8_cross_language_manifest(&"f".repeat(64), receipt_refs).unwrap();
        assert!(cross.passed);
        assert!(
            validate_gate8_cross_language_manifest(
                &cross.canonical_bytes,
                &"f".repeat(64),
                receipt_refs,
            )
            .unwrap()
        );

        let mut mismatched_rows = rows.clone();
        mismatched_rows[7].sha256 = "e".repeat(64);
        let mut mismatched_receipts = receipts.clone();
        mismatched_receipts[3] = render_receipt("linux-rust", &mismatched_rows);
        let mismatched_refs: [&[u8]; 4] =
            std::array::from_fn(|index| mismatched_receipts[index].as_slice());
        let failed =
            render_gate8_cross_language_manifest(&"f".repeat(64), mismatched_refs).unwrap();
        assert!(!failed.passed);
        assert!(
            !validate_gate8_cross_language_manifest(
                &failed.canonical_bytes,
                &"f".repeat(64),
                mismatched_refs,
            )
            .unwrap()
        );

        let mut extra = validate_canonical_manifest(&cross.canonical_bytes).unwrap();
        let ManifestValue::Object(root) = &mut extra else {
            unreachable!()
        };
        root.insert("extra".to_owned(), ManifestValue::Bool(false));
        let extra = serialize_manifest(&extra).unwrap();
        assert_eq!(
            validate_gate8_cross_language_manifest(&extra, &"f".repeat(64), receipt_refs),
            Err(Gate8Error::Result)
        );
    }
}
