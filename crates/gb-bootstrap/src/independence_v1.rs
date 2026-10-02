//! Strict canonical M2 R3 independence-proof rows and bundle bindings.
//!
//! The witness calculations are deliberately supplied by a separate typed
//! projection. This module owns the closed v1 proof schema, exact owner/root
//! admission, manifest identity, and byte-for-byte validation only. It never
//! reads a carrier or executes a damage case.

use std::collections::{BTreeMap, BTreeSet};

use gb_foundation::{ManifestValue, identity_hex, serialize_manifest, validate_canonical_manifest};
use sha2::{Digest, Sha256};

use crate::damage::{CounterWords, WINDOW_DOMAIN, sample_without_replacement};

pub const PROFILE_ID_V1: &str = "eh72-hier-r5-r2-r1-crc32c-v0";
pub const PROOF_PREDICATE_IDS_V1: [&str; 9] = [
    "two-stage-map-bijection",
    "matrix-owner-total-partition",
    "shell-sector-total-partition",
    "physical-group-total-partition",
    "owner-factor-ledger-reconciliation",
    "final-cell-lane-separation",
    "d2-d4-d6-required-closure-survival",
    "section-dependency-inventory-closure",
    "damage-promise-binding",
];
pub const PROOF_WITNESS_COUNTS_V1: [u64; 9] = [
    3_182_656, 4_161_600, 978_944, 3_181_248, 4_161_600, 1_282_176, 37_844, 1_362, 10_038,
];
const FAMILY_IDS: [&str; 8] = ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7"];
const FAMILY_COUNTS: [u64; 8] = [16, 4, 256, 128, 1_841, 21, 7_364, 408];
const BOUNDARY_IDS: [&str; 4] = [
    "rep2-correction-boundary",
    "rep5-correction-boundary",
    "complete-section-conflict",
    "section-attempt-ceiling-plus-one",
];
const BOUNDARY_RESULT_SHA256: [&str; 4] = [
    "452d38bd592174b0fb022cee41e4f261768957811893ae471934bf3e4e8e6622",
    "5158867ec6d4c740afec018f5695a51779ca54758113303d3b656c4b6ee1f01e",
    "9508a43cc54c7f6dc06fcee677a18db1ed57bfdb87e1c5f692d332642a3c5b56",
    "966307a69ded9f055704443e6c6c46b4d0226a4a4bced398e0573fe5afe03187",
];
const IDENTITY_DOMAIN: &[u8] = b"golden-board:manifest:v0\0";
const RECIPIENT_PACKAGE_SHA256: &str =
    "4bd8e0d485ae6e6a65f4edc4ef2aaac9585a2bcd8c4623e44d69f1dad3b0ec8e";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum IndependenceV1Error {
    Manifest,
    Binding,
    Arithmetic,
}

pub type Result<T> = std::result::Result<T, IndependenceV1Error>;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ProofPredicateRowV1 {
    pub predicate_id: &'static str,
    pub witness_count: u64,
    pub minimum_surviving_count: u64,
    pub violation_count: u64,
    pub passed: bool,
}

impl ProofPredicateRowV1 {
    pub fn new(
        predicate_id: &'static str,
        witness_count: u64,
        violation_count: u64,
    ) -> Result<Self> {
        let ordinal = PROOF_PREDICATE_IDS_V1
            .iter()
            .position(|owned| *owned == predicate_id)
            .ok_or(IndependenceV1Error::Manifest)?;
        if witness_count != PROOF_WITNESS_COUNTS_V1[ordinal] {
            return Err(IndependenceV1Error::Manifest);
        }
        Ok(Self {
            predicate_id,
            witness_count,
            minimum_surviving_count: 1,
            violation_count,
            passed: violation_count == 0,
        })
    }
}

/// Materialize the exact frozen proof rows from independently enumerated
/// violation counts. Witness counts and the literal floor are owner constants,
/// never caller-selected or outcome-dependent.
pub fn proof_rows_from_violation_counts_v1(
    violation_counts: [u64; 9],
) -> Result<Vec<ProofPredicateRowV1>> {
    PROOF_PREDICATE_IDS_V1
        .iter()
        .zip(PROOF_WITNESS_COUNTS_V1)
        .zip(violation_counts)
        .map(|((&predicate_id, witness_count), violation_count)| {
            ProofPredicateRowV1::new(predicate_id, witness_count, violation_count)
        })
        .collect()
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct IndependenceProofV1 {
    pub canonical_bytes: Vec<u8>,
    pub manifest_identity: String,
    pub passed: bool,
    pub predicate_rows: Vec<ProofPredicateRowV1>,
}

/// Complete transient v1 gate-6 evidence rendered from independently
/// regenerated case rows.  Gate 8 hashes these byte strings in memory; this
/// type deliberately has no filesystem writer.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RenderedDamageEvidenceBundleV1 {
    pub damage_manifest: Vec<u8>,
    pub family_manifests: Vec<Vec<u8>>,
    pub case_shards: Vec<(String, Vec<u8>)>,
}

#[derive(Clone, Debug)]
struct SectionEvidenceV1 {
    section_id: u64,
    section_type: u64,
    closure_class: u64,
    copy_class: String,
    factor: u64,
    fragment_count: u64,
    dependencies: Vec<u64>,
}

#[derive(Clone, Debug)]
struct UnitEvidenceV1 {
    physical_unit_id: u64,
    section_id: u64,
    fragment_index: u64,
    replica_index: u64,
    factor: u64,
    slot: u64,
    logical_bit_first: u64,
    mapped_cell_sha256: String,
}

#[derive(Clone, Debug)]
struct ShellEvidenceV1 {
    route_prefix_cells: u64,
    headroom_cells: u64,
    fixed_pad_cells: u64,
}

#[derive(Clone, Debug)]
struct CandidateEvidenceV1 {
    side: u64,
    width: u64,
    interior_side: u64,
    population: u64,
    unit_population: u64,
    unit_multiplier: u64,
    unit_inverse_multiplier: u64,
    cell_multiplier: u64,
    cell_inverse_multiplier: u64,
    cell_offset: u64,
    sections: Vec<SectionEvidenceV1>,
    units: Vec<UnitEvidenceV1>,
    shell: Vec<ShellEvidenceV1>,
    ledger: BTreeMap<String, ManifestValue>,
    ownership_cell_table_sha256: String,
}

#[derive(Clone, Debug)]
struct DamageEvidenceV1 {
    cases: [Vec<ManifestValue>; 8],
    family_pass: [bool; 8],
    boundary_pass: bool,
}

fn digest(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn lower_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn object(value: &ManifestValue) -> Result<&BTreeMap<String, ManifestValue>> {
    let ManifestValue::Object(value) = value else {
        return Err(IndependenceV1Error::Manifest);
    };
    Ok(value)
}

fn array(value: &ManifestValue) -> Result<&[ManifestValue]> {
    let ManifestValue::Array(value) = value else {
        return Err(IndependenceV1Error::Manifest);
    };
    Ok(value)
}

fn text(value: &ManifestValue) -> Result<&str> {
    let ManifestValue::String(value) = value else {
        return Err(IndependenceV1Error::Manifest);
    };
    Ok(value)
}

fn unsigned(value: &ManifestValue) -> Result<u64> {
    let ManifestValue::U64(value) = value else {
        return Err(IndependenceV1Error::Manifest);
    };
    Ok(*value)
}

fn exact_keys(value: &BTreeMap<String, ManifestValue>, keys: &[&str]) -> bool {
    value.len() == keys.len() && keys.iter().all(|key| value.contains_key(*key))
}

fn field<'a>(value: &'a BTreeMap<String, ManifestValue>, key: &str) -> Result<&'a ManifestValue> {
    value.get(key).ok_or(IndependenceV1Error::Manifest)
}

fn manifest_string(value: &str) -> ManifestValue {
    ManifestValue::String(value.to_owned())
}

fn manifest_object(rows: impl IntoIterator<Item = (&'static str, ManifestValue)>) -> ManifestValue {
    ManifestValue::Object(
        rows.into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}

fn nested_manifest_identity(value: &ManifestValue) -> Result<String> {
    let mut without = value.clone();
    let root = object_mut(&mut without)?;
    let summary = object_mut(
        root.get_mut("summary")
            .ok_or(IndependenceV1Error::Manifest)?,
    )?;
    summary
        .remove("manifest_identity")
        .ok_or(IndependenceV1Error::Manifest)?;
    let raw = serialize_manifest(&without).map_err(|_| IndependenceV1Error::Manifest)?;
    identity_hex(IDENTITY_DOMAIN, &[&raw]).map_err(|_| IndependenceV1Error::Manifest)
}

fn top_level_manifest_identity(value: &ManifestValue) -> Result<String> {
    let mut without = value.clone();
    object_mut(&mut without)?
        .remove("manifest_identity")
        .ok_or(IndependenceV1Error::Manifest)?;
    let raw = serialize_manifest(&without).map_err(|_| IndependenceV1Error::Manifest)?;
    identity_hex(IDENTITY_DOMAIN, &[&raw]).map_err(|_| IndependenceV1Error::Manifest)
}

fn object_mut(value: &mut ManifestValue) -> Result<&mut BTreeMap<String, ManifestValue>> {
    let ManifestValue::Object(value) = value else {
        return Err(IndependenceV1Error::Manifest);
    };
    Ok(value)
}

fn owner_sha256(raw: &[u8]) -> String {
    digest(raw)
}

fn checked_add(left: u64, right: u64) -> Result<u64> {
    left.checked_add(right)
        .ok_or(IndependenceV1Error::Arithmetic)
}

fn checked_mul(left: u64, right: u64) -> Result<u64> {
    left.checked_mul(right)
        .ok_or(IndependenceV1Error::Arithmetic)
}

fn exact_mapping(value: &ManifestValue) -> Result<&BTreeMap<String, ManifestValue>> {
    let mapping = object(value)?;
    if !exact_keys(
        mapping,
        &[
            "id",
            "interior_side",
            "population",
            "unit_population",
            "unit_multiplier",
            "unit_inverse_multiplier",
            "cell_multiplier",
            "offset",
            "cell_inverse_multiplier",
        ],
    ) || text(field(mapping, "id")?)? != "affine-slot-then-interior-v1"
    {
        return Err(IndependenceV1Error::Manifest);
    }
    let interior_side = unsigned(field(mapping, "interior_side")?)?;
    let population = unsigned(field(mapping, "population")?)?;
    let unit_population = unsigned(field(mapping, "unit_population")?)?;
    let unit_multiplier = unsigned(field(mapping, "unit_multiplier")?)?;
    let unit_inverse = unsigned(field(mapping, "unit_inverse_multiplier")?)?;
    let cell_multiplier = unsigned(field(mapping, "cell_multiplier")?)?;
    let cell_inverse = unsigned(field(mapping, "cell_inverse_multiplier")?)?;
    let offset = unsigned(field(mapping, "offset")?)?;
    if interior_side == 0
        || population != checked_mul(interior_side, interior_side)?
        || unit_population == 0
        || unit_multiplier == 0
        || unit_multiplier >= unit_population
        || unit_inverse == 0
        || unit_inverse >= unit_population
        || checked_mul(unit_multiplier, unit_inverse)? % unit_population != 1
        || cell_multiplier == 0
        || cell_multiplier >= population
        || cell_inverse == 0
        || cell_inverse >= population
        || checked_mul(cell_multiplier, cell_inverse)? % population != 1
        || offset >= population
    {
        return Err(IndependenceV1Error::Binding);
    }
    Ok(mapping)
}

fn exact_shell_rows(value: &ManifestValue, side: u64, width: u64) -> Result<()> {
    let rows = array(value)?;
    let sector_cells = checked_mul(
        width,
        side.checked_sub(width)
            .ok_or(IndependenceV1Error::Arithmetic)?,
    )?;
    if rows.len() != 4 {
        return Err(IndependenceV1Error::Manifest);
    }
    for (ordinal, row) in rows.iter().enumerate() {
        let row = object(row)?;
        if !exact_keys(
            row,
            &[
                "sector_id",
                "route_prefix_cells",
                "headroom_cells",
                "fixed_pad_cells",
                "image_sha256",
            ],
        ) || unsigned(field(row, "sector_id")?)? != ordinal as u64
            || !lower_sha256(text(field(row, "image_sha256")?)?)
        {
            return Err(IndependenceV1Error::Manifest);
        }
        let used = checked_add(
            checked_add(
                unsigned(field(row, "route_prefix_cells")?)?,
                unsigned(field(row, "headroom_cells")?)?,
            )?,
            unsigned(field(row, "fixed_pad_cells")?)?,
        )?;
        if used != sector_cells {
            return Err(IndependenceV1Error::Binding);
        }
    }
    Ok(())
}

fn admit_candidate_and_ownership(candidate_raw: &[u8], ownership_raw: &[u8]) -> Result<[u64; 9]> {
    let candidate =
        validate_canonical_manifest(candidate_raw).map_err(|_| IndependenceV1Error::Manifest)?;
    let ownership =
        validate_canonical_manifest(ownership_raw).map_err(|_| IndependenceV1Error::Manifest)?;
    let candidate_row = object(&candidate)?;
    let ownership_row = object(&ownership)?;
    const CANDIDATE_KEYS: [&str; 21] = [
        "schema",
        "profile_policy_sha256",
        "profile_limits_sha256",
        "bootstrap_spec_sha256",
        "route_data_sha256",
        "recipient_package_sha256",
        "profile_id",
        "profile_version",
        "semantic_envelope_sha256",
        "side",
        "shell_width",
        "mapping",
        "shell_rows",
        "section_rows",
        "unit_rows",
        "ownership_sha256",
        "capacity_ledger_sha256",
        "density_ledger_sha256",
        "carrier_sha256",
        "ledger",
        "manifest_identity",
    ];
    const OWNERSHIP_KEYS: [&str; 10] = [
        "schema",
        "profile_id",
        "side",
        "shell_width",
        "mapping",
        "shell_rows",
        "unit_rows",
        "interior_fixed_pad",
        "cell_table",
        "cell_table_sha256",
    ];
    if !exact_keys(candidate_row, &CANDIDATE_KEYS)
        || !exact_keys(ownership_row, &OWNERSHIP_KEYS)
        || text(field(candidate_row, "schema")?)? != "golden-board.m2-candidate-manifest/v1"
        || text(field(ownership_row, "schema")?)? != "golden-board.m2-ownership-ledger/v1"
        || text(field(candidate_row, "profile_id")?)? != PROFILE_ID_V1
        || text(field(ownership_row, "profile_id")?)? != PROFILE_ID_V1
        || unsigned(field(candidate_row, "profile_version")?)? != 7
        || field(candidate_row, "side")? != field(ownership_row, "side")?
        || field(candidate_row, "shell_width")? != field(ownership_row, "shell_width")?
        || field(candidate_row, "mapping")? != field(ownership_row, "mapping")?
        || text(field(candidate_row, "ownership_sha256")?)? != digest(ownership_raw)
        || text(field(candidate_row, "profile_policy_sha256")?)?
            != owner_sha256(include_bytes!("../../../spec/profile-policy-v1.toml"))
        || text(field(candidate_row, "profile_limits_sha256")?)?
            != owner_sha256(include_bytes!("../../../spec/profile-limits-v1.toml"))
        || text(field(candidate_row, "bootstrap_spec_sha256")?)?
            != owner_sha256(include_bytes!("../../../spec/bootstrap-v1.md"))
        || text(field(candidate_row, "route_data_sha256")?)?
            != owner_sha256(include_bytes!("../../../spec/route-data-v1.json"))
        || text(field(candidate_row, "recipient_package_sha256")?)? != RECIPIENT_PACKAGE_SHA256
        || text(field(candidate_row, "manifest_identity")?)?
            != top_level_manifest_identity(&candidate)?
    {
        return Err(IndependenceV1Error::Binding);
    }
    for key in [
        "semantic_envelope_sha256",
        "ownership_sha256",
        "capacity_ledger_sha256",
        "density_ledger_sha256",
        "carrier_sha256",
        "manifest_identity",
    ] {
        if !lower_sha256(text(field(candidate_row, key)?)?) {
            return Err(IndependenceV1Error::Manifest);
        }
    }
    if !lower_sha256(text(field(ownership_row, "cell_table_sha256")?)?) {
        return Err(IndependenceV1Error::Manifest);
    }

    let side = unsigned(field(candidate_row, "side")?)?;
    let width = unsigned(field(candidate_row, "shell_width")?)?;
    if width == 0 || width >= side / 2 {
        return Err(IndependenceV1Error::Binding);
    }
    let mapping = exact_mapping(field(candidate_row, "mapping")?)?;
    let population = unsigned(field(mapping, "population")?)?;
    let unit_population = unsigned(field(mapping, "unit_population")?)?;
    let unit_multiplier = unsigned(field(mapping, "unit_multiplier")?)?;
    exact_shell_rows(field(candidate_row, "shell_rows")?, side, width)?;
    exact_shell_rows(field(ownership_row, "shell_rows")?, side, width)?;
    if field(candidate_row, "shell_rows")? != field(ownership_row, "shell_rows")? {
        return Err(IndependenceV1Error::Binding);
    }

    const SECTION_KEYS: [&str; 11] = [
        "section_id",
        "section_type",
        "closure_class",
        "check_id",
        "semantic_copy_count",
        "physical_replica_count",
        "copy_class",
        "dependency_ids",
        "logical_payload_bytes",
        "envelope_bytes",
        "fragment_count",
    ];
    let sections = array(field(candidate_row, "section_rows")?)?;
    if sections.is_empty() || sections.len() > 4_096 {
        return Err(IndependenceV1Error::Manifest);
    }
    let mut section_projection = Vec::with_capacity(sections.len());
    let mut prior_section_id = 0_u64;
    let mut logical_group_count = 0_u64;
    let mut dependency_edges = 0_u64;
    let mut factor_groups = [0_u64; 6];
    for value in sections {
        let row = object(value)?;
        if !exact_keys(row, &SECTION_KEYS) {
            return Err(IndependenceV1Error::Manifest);
        }
        let section_id = unsigned(field(row, "section_id")?)?;
        let section_type = unsigned(field(row, "section_type")?)?;
        let closure_class = unsigned(field(row, "closure_class")?)?;
        let factor = unsigned(field(row, "physical_replica_count")?)?;
        let fragments = unsigned(field(row, "fragment_count")?)?;
        let payload = unsigned(field(row, "logical_payload_bytes")?)?;
        let envelope = unsigned(field(row, "envelope_bytes")?)?;
        if section_id <= prior_section_id
            || unsigned(field(row, "semantic_copy_count")?)? != 1
            || !matches!(factor, 1 | 2 | 5)
            || fragments == 0
            || fragments > 4_096
            || envelope == 0
            || envelope > 1_048_576
        {
            return Err(IndependenceV1Error::Binding);
        }
        let expected_class = if [1, 2, 3, 16].contains(&section_id) {
            if factor != 5 {
                return Err(IndependenceV1Error::Binding);
            }
            "required-spine"
        } else if factor == 2 {
            "replicated-m2"
        } else if factor == 1 {
            "nonreplicated-m2"
        } else {
            return Err(IndependenceV1Error::Binding);
        };
        if text(field(row, "copy_class")?)? != expected_class {
            return Err(IndependenceV1Error::Binding);
        }
        let dependencies = array(field(row, "dependency_ids")?)?;
        if dependencies.len() > 4_095 {
            return Err(IndependenceV1Error::Manifest);
        }
        let mut prior_dependency = 0_u64;
        for dependency in dependencies {
            let dependency = unsigned(dependency)?;
            if dependency == 0 || dependency <= prior_dependency {
                return Err(IndependenceV1Error::Binding);
            }
            prior_dependency = dependency;
        }
        logical_group_count = checked_add(logical_group_count, fragments)?;
        dependency_edges = checked_add(dependency_edges, dependencies.len() as u64)?;
        factor_groups[factor as usize] = checked_add(factor_groups[factor as usize], fragments)?;
        section_projection.push((
            section_id,
            section_type,
            closure_class,
            factor,
            fragments,
            payload,
        ));
        prior_section_id = section_id;
    }

    const UNIT_KEYS: [&str; 12] = [
        "physical_unit_id",
        "section_id",
        "semantic_copy_id",
        "fragment_index",
        "replica_index",
        "physical_replica_count",
        "slot",
        "transport_id",
        "encoded_bytes",
        "encoded_sha256",
        "logical_bit_first",
        "logical_bit_count",
    ];
    const OWNERSHIP_UNIT_KEYS: [&str; 9] = [
        "physical_unit_id",
        "section_id",
        "fragment_index",
        "replica_index",
        "physical_replica_count",
        "slot",
        "logical_bit_first",
        "logical_bit_count",
        "mapped_cell_sha256",
    ];
    let units = array(field(candidate_row, "unit_rows")?)?;
    let ownership_units = array(field(ownership_row, "unit_rows")?)?;
    if units.len() != ownership_units.len() || units.len() as u64 != unit_population {
        return Err(IndependenceV1Error::Binding);
    }
    let mut ordinal = 0_usize;
    let mut slots = BTreeSet::new();
    for (section_id, _, _, factor, fragments, _) in &section_projection {
        for fragment in 0..*fragments {
            for replica in 0..*factor {
                let row = object(units.get(ordinal).ok_or(IndependenceV1Error::Binding)?)?;
                let ownership_unit = object(
                    ownership_units
                        .get(ordinal)
                        .ok_or(IndependenceV1Error::Binding)?,
                )?;
                if !exact_keys(row, &UNIT_KEYS) || !exact_keys(ownership_unit, &OWNERSHIP_UNIT_KEYS)
                {
                    return Err(IndependenceV1Error::Manifest);
                }
                let physical_id = ordinal as u64 + 1;
                let slot = checked_mul(unit_multiplier, physical_id - 1)? % unit_population;
                let logical_bit_first = checked_mul(slot, 1_728)?;
                for key in [
                    "physical_unit_id",
                    "section_id",
                    "fragment_index",
                    "replica_index",
                    "physical_replica_count",
                    "slot",
                    "logical_bit_first",
                    "logical_bit_count",
                ] {
                    if field(row, key)? != field(ownership_unit, key)? {
                        return Err(IndependenceV1Error::Binding);
                    }
                }
                if unsigned(field(row, "physical_unit_id")?)? != physical_id
                    || unsigned(field(row, "section_id")?)? != *section_id
                    || unsigned(field(row, "semantic_copy_id")?)? != 0
                    || unsigned(field(row, "fragment_index")?)? != fragment
                    || unsigned(field(row, "replica_index")?)? != replica
                    || unsigned(field(row, "physical_replica_count")?)? != *factor
                    || unsigned(field(row, "slot")?)? != slot
                    || unsigned(field(row, "encoded_bytes")?)? != 216
                    || unsigned(field(row, "logical_bit_first")?)? != logical_bit_first
                    || unsigned(field(row, "logical_bit_count")?)? != 1_728
                    || text(field(row, "transport_id")?)? != "eh72-hier-repetition-v0"
                    || !lower_sha256(text(field(row, "encoded_sha256")?)?)
                    || !lower_sha256(text(field(ownership_unit, "mapped_cell_sha256")?)?)
                    || !slots.insert(slot)
                {
                    return Err(IndependenceV1Error::Binding);
                }
                ordinal += 1;
            }
        }
    }
    if ordinal != units.len() {
        return Err(IndependenceV1Error::Binding);
    }

    let fixed_pad = object(field(ownership_row, "interior_fixed_pad")?)?;
    if !exact_keys(
        fixed_pad,
        &["logical_bit_first", "logical_bit_count", "fill_order"],
    ) || text(field(fixed_pad, "fill_order")?)?
        != "unoccupied-interior-cells-in-physical-row-major-order"
    {
        return Err(IndependenceV1Error::Manifest);
    }
    let protected_cells = checked_mul(unit_population, 1_728)?;
    let pad_cells = population
        .checked_sub(protected_cells)
        .ok_or(IndependenceV1Error::Arithmetic)?;
    if unsigned(field(fixed_pad, "logical_bit_first")?)? != protected_cells
        || unsigned(field(fixed_pad, "logical_bit_count")?)? != pad_cells
    {
        return Err(IndependenceV1Error::Binding);
    }

    const CELL_TABLE_KEYS: [&str; 6] = [
        "row_bytes",
        "row_count",
        "row_order",
        "owner_kind_ids",
        "owner_id_rule",
        "owner_bit_offset_rule",
    ];
    let cell_table = object(field(ownership_row, "cell_table")?)?;
    let total_cells = checked_mul(side, side)?;
    if !exact_keys(cell_table, &CELL_TABLE_KEYS)
        || unsigned(field(cell_table, "row_bytes")?)? != 9
        || unsigned(field(cell_table, "row_count")?)? != total_cells
        || text(field(cell_table, "row_order")?)? != "canonical-matrix-row-major"
        || text(field(cell_table, "owner_id_rule")?)?
            != "sector-id-for-shell-kinds-physical-unit-id-for-protected-unit-zero-for-interior-fixed-pad"
        || text(field(cell_table, "owner_bit_offset_rule")?)?
            != "zero-based-offset-within-named-owner"
    {
        return Err(IndependenceV1Error::Binding);
    }
    let owner_kinds = array(field(cell_table, "owner_kind_ids")?)?;
    let expected_kinds = [
        "1-shell-route",
        "2-shell-headroom",
        "3-shell-fixed-pad",
        "4-protected-unit",
        "5-interior-fixed-pad",
    ];
    if owner_kinds.len() != expected_kinds.len()
        || owner_kinds
            .iter()
            .zip(expected_kinds)
            .any(|(value, expected)| text(value) != Ok(expected))
    {
        return Err(IndependenceV1Error::Binding);
    }

    const LEDGER_KEYS: [&str; 25] = [
        "logical_bytes_by_owner",
        "envelope_bytes",
        "fragment_header_bytes",
        "fragment_zero_pad_bytes",
        "local_check_bytes",
        "section_check_bytes",
        "transport_pad_bytes",
        "parity_bytes",
        "shell_instruction_cells",
        "shell_example_cells",
        "shell_recipe_cells",
        "shell_headroom_cells",
        "shell_fixed_pad_cells",
        "real_protected_cells",
        "capacity_probe_cells",
        "reserve_probe_cells",
        "load_probe_cells",
        "interior_fixed_pad_cells",
        "protected_unit_count",
        "codeword_count",
        "worst_case_section_attempts",
        "worst_case_work_units",
        "scratch_bytes",
        "unused_cells",
        "total_cells",
    ];
    let ledger = object(field(candidate_row, "ledger")?)?;
    if !exact_keys(ledger, &LEDGER_KEYS)
        || unsigned(field(ledger, "protected_unit_count")?)? != unit_population
        || unsigned(field(ledger, "codeword_count")?)? != checked_mul(unit_population, 24)?
        || unsigned(field(ledger, "worst_case_section_attempts")?)? != 1
        || unsigned(field(ledger, "interior_fixed_pad_cells")?)? != pad_cells
        || unsigned(field(ledger, "unused_cells")?)? != 0
        || unsigned(field(ledger, "total_cells")?)? != total_cells
        || unsigned(field(ledger, "fragment_header_bytes")?)? != checked_mul(unit_population, 30)?
        || unsigned(field(ledger, "local_check_bytes")?)? != checked_mul(unit_population, 4)?
        || unsigned(field(ledger, "transport_pad_bytes")?)? != unit_population
        || unsigned(field(ledger, "parity_bytes")?)? != checked_mul(unit_population, 24)?
    {
        return Err(IndependenceV1Error::Binding);
    }
    let owner_rows = array(field(ledger, "logical_bytes_by_owner")?)?;
    if owner_rows.len() != section_projection.len() {
        return Err(IndependenceV1Error::Binding);
    }
    for (owner, (section_id, section_type, closure_class, factor, _, payload)) in
        owner_rows.iter().zip(&section_projection)
    {
        let owner = object(owner)?;
        if !exact_keys(
            owner,
            &[
                "owner_id",
                "section_type",
                "closure_class",
                "semantic_copy_count",
                "physical_replica_count",
                "logical_bytes",
            ],
        ) || text(field(owner, "owner_id")?)? != format!("section:{section_id:010}")
            || unsigned(field(owner, "section_type")?)? != *section_type
            || unsigned(field(owner, "closure_class")?)? != *closure_class
            || unsigned(field(owner, "semantic_copy_count")?)? != 1
            || unsigned(field(owner, "physical_replica_count")?)? != *factor
            || unsigned(field(owner, "logical_bytes")?)? != *payload
        {
            return Err(IndependenceV1Error::Binding);
        }
    }

    let shell_cells = checked_mul(4, checked_mul(width, side - width)?)?;
    let witness_counts = [
        checked_add(protected_cells, pad_cells)?,
        total_cells,
        total_cells
            .checked_sub(population)
            .ok_or(IndependenceV1Error::Arithmetic)?,
        protected_cells,
        total_cells,
        checked_mul(
            1_728,
            checked_add(factor_groups[2], checked_mul(factor_groups[5], 10)?)?,
        )?,
        checked_mul(
            4,
            checked_add(
                checked_add(FAMILY_COUNTS[2], FAMILY_COUNTS[4])?,
                FAMILY_COUNTS[6],
            )?,
        )?,
        checked_add(
            checked_add(logical_group_count, dependency_edges)?,
            checked_add(4, 1)?,
        )?,
        FAMILY_COUNTS.into_iter().try_fold(0_u64, checked_add)?,
    ];
    if shell_cells != witness_counts[2] {
        return Err(IndependenceV1Error::Binding);
    }
    Ok(witness_counts)
}

/// Strictly admit the persisted v7 candidate/ownership pair and independently
/// derive the nine frozen witness populations. This does not read a carrier
/// or damage artifact.
pub fn derive_proof_witness_counts_v1(
    candidate_manifest_raw: &[u8],
    ownership_ledger_raw: &[u8],
) -> Result<[u64; 9]> {
    let counts = admit_candidate_and_ownership(candidate_manifest_raw, ownership_ledger_raw)?;
    if counts != PROOF_WITNESS_COUNTS_V1 {
        return Err(IndependenceV1Error::Binding);
    }
    Ok(counts)
}

fn candidate_evidence_v1(
    candidate_manifest_raw: &[u8],
    ownership_ledger_raw: &[u8],
) -> Result<CandidateEvidenceV1> {
    derive_proof_witness_counts_v1(candidate_manifest_raw, ownership_ledger_raw)?;
    let candidate = validate_canonical_manifest(candidate_manifest_raw)
        .map_err(|_| IndependenceV1Error::Manifest)?;
    let ownership = validate_canonical_manifest(ownership_ledger_raw)
        .map_err(|_| IndependenceV1Error::Manifest)?;
    let candidate = object(&candidate)?;
    let ownership = object(&ownership)?;
    let mapping = object(field(candidate, "mapping")?)?;
    let sections = array(field(candidate, "section_rows")?)?
        .iter()
        .map(|value| {
            let row = object(value)?;
            Ok(SectionEvidenceV1 {
                section_id: unsigned(field(row, "section_id")?)?,
                section_type: unsigned(field(row, "section_type")?)?,
                closure_class: unsigned(field(row, "closure_class")?)?,
                copy_class: text(field(row, "copy_class")?)?.to_owned(),
                factor: unsigned(field(row, "physical_replica_count")?)?,
                fragment_count: unsigned(field(row, "fragment_count")?)?,
                dependencies: array(field(row, "dependency_ids")?)?
                    .iter()
                    .map(unsigned)
                    .collect::<Result<Vec<_>>>()?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    let ownership_units = array(field(ownership, "unit_rows")?)?;
    let units = array(field(candidate, "unit_rows")?)?
        .iter()
        .zip(ownership_units)
        .map(|(value, owner)| {
            let row = object(value)?;
            let owner = object(owner)?;
            Ok(UnitEvidenceV1 {
                physical_unit_id: unsigned(field(row, "physical_unit_id")?)?,
                section_id: unsigned(field(row, "section_id")?)?,
                fragment_index: unsigned(field(row, "fragment_index")?)?,
                replica_index: unsigned(field(row, "replica_index")?)?,
                factor: unsigned(field(row, "physical_replica_count")?)?,
                slot: unsigned(field(row, "slot")?)?,
                logical_bit_first: unsigned(field(row, "logical_bit_first")?)?,
                mapped_cell_sha256: text(field(owner, "mapped_cell_sha256")?)?.to_owned(),
            })
        })
        .collect::<Result<Vec<_>>>()?;
    let shell = array(field(candidate, "shell_rows")?)?
        .iter()
        .map(|value| {
            let row = object(value)?;
            Ok(ShellEvidenceV1 {
                route_prefix_cells: unsigned(field(row, "route_prefix_cells")?)?,
                headroom_cells: unsigned(field(row, "headroom_cells")?)?,
                fixed_pad_cells: unsigned(field(row, "fixed_pad_cells")?)?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    Ok(CandidateEvidenceV1 {
        side: unsigned(field(candidate, "side")?)?,
        width: unsigned(field(candidate, "shell_width")?)?,
        interior_side: unsigned(field(mapping, "interior_side")?)?,
        population: unsigned(field(mapping, "population")?)?,
        unit_population: unsigned(field(mapping, "unit_population")?)?,
        unit_multiplier: unsigned(field(mapping, "unit_multiplier")?)?,
        unit_inverse_multiplier: unsigned(field(mapping, "unit_inverse_multiplier")?)?,
        cell_multiplier: unsigned(field(mapping, "cell_multiplier")?)?,
        cell_inverse_multiplier: unsigned(field(mapping, "cell_inverse_multiplier")?)?,
        cell_offset: unsigned(field(mapping, "offset")?)?,
        sections,
        units,
        shell,
        ledger: object(field(candidate, "ledger")?)?.clone(),
        ownership_cell_table_sha256: text(field(ownership, "cell_table_sha256")?)?.to_owned(),
    })
}

fn admit_damage_root(damage_raw: &[u8], candidate_sha256: &str) -> Result<ManifestValue> {
    let damage =
        validate_canonical_manifest(damage_raw).map_err(|_| IndependenceV1Error::Manifest)?;
    let root = object(&damage)?;
    const DAMAGE_KEYS: [&str; 13] = [
        "schema",
        "damage_policy_sha256",
        "profile_policy_sha256",
        "profile_limits_sha256",
        "bootstrap_spec_sha256",
        "route_data_sha256",
        "recipient_package_sha256",
        "profile_id",
        "candidate_manifest_sha256",
        "clean_observation_sha256",
        "family_rows",
        "boundary_kat_rows",
        "summary",
    ];
    if !exact_keys(root, &DAMAGE_KEYS)
        || text(field(root, "schema")?)? != "golden-board.m2-damage-manifest/v1"
        || text(field(root, "profile_id")?)? != PROFILE_ID_V1
        || text(field(root, "candidate_manifest_sha256")?)? != candidate_sha256
        || text(field(root, "damage_policy_sha256")?)?
            != owner_sha256(include_bytes!("../../../spec/damage-policy-v1.toml"))
        || text(field(root, "profile_policy_sha256")?)?
            != owner_sha256(include_bytes!("../../../spec/profile-policy-v1.toml"))
        || text(field(root, "profile_limits_sha256")?)?
            != owner_sha256(include_bytes!("../../../spec/profile-limits-v1.toml"))
        || text(field(root, "bootstrap_spec_sha256")?)?
            != owner_sha256(include_bytes!("../../../spec/bootstrap-v1.md"))
        || text(field(root, "route_data_sha256")?)?
            != owner_sha256(include_bytes!("../../../spec/route-data-v1.json"))
        || text(field(root, "recipient_package_sha256")?)? != RECIPIENT_PACKAGE_SHA256
    {
        return Err(IndependenceV1Error::Binding);
    }
    for key in [
        "damage_policy_sha256",
        "profile_policy_sha256",
        "profile_limits_sha256",
        "bootstrap_spec_sha256",
        "route_data_sha256",
        "recipient_package_sha256",
        "candidate_manifest_sha256",
        "clean_observation_sha256",
    ] {
        if !lower_sha256(text(field(root, key)?)?) {
            return Err(IndependenceV1Error::Manifest);
        }
    }
    let families = array(field(root, "family_rows")?)?;
    if families.len() != FAMILY_IDS.len() {
        return Err(IndependenceV1Error::Manifest);
    }
    for (ordinal, row) in families.iter().enumerate() {
        let row = object(row)?;
        if !exact_keys(
            row,
            &[
                "family_id",
                "case_count",
                "wrong_accept_count",
                "result",
                "case_rows_sha256",
            ],
        ) || text(field(row, "family_id")?)? != FAMILY_IDS[ordinal]
            || unsigned(field(row, "case_count")?)? != FAMILY_COUNTS[ordinal]
            || unsigned(field(row, "wrong_accept_count")?)? != 0
            || text(field(row, "result")?)? != "pass"
            || !lower_sha256(text(field(row, "case_rows_sha256")?)?)
        {
            return Err(IndependenceV1Error::Binding);
        }
    }
    let boundaries = array(field(root, "boundary_kat_rows")?)?;
    if boundaries.len() != BOUNDARY_IDS.len() {
        return Err(IndependenceV1Error::Manifest);
    }
    for (ordinal, row) in boundaries.iter().enumerate() {
        let row = object(row)?;
        if !exact_keys(row, &["kat_id", "result_sha256", "result"])
            || text(field(row, "kat_id")?)? != BOUNDARY_IDS[ordinal]
            || text(field(row, "result")?)? != "pass"
            || text(field(row, "result_sha256")?)? != BOUNDARY_RESULT_SHA256[ordinal]
        {
            return Err(IndependenceV1Error::Binding);
        }
    }
    let summary = object(field(root, "summary")?)?;
    if !exact_keys(
        summary,
        &[
            "family_case_counts",
            "wrong_accept_count",
            "manifest_identity",
        ],
    ) || unsigned(field(summary, "wrong_accept_count")?)? != 0
        || !lower_sha256(text(field(summary, "manifest_identity")?)?)
        || text(field(summary, "manifest_identity")?)? != nested_manifest_identity(&damage)?
    {
        return Err(IndependenceV1Error::Binding);
    }
    let counts = array(field(summary, "family_case_counts")?)?;
    if counts.len() != FAMILY_IDS.len() {
        return Err(IndependenceV1Error::Manifest);
    }
    for (ordinal, row) in counts.iter().enumerate() {
        let row = object(row)?;
        if !exact_keys(row, &["family_id", "case_count"])
            || text(field(row, "family_id")?)? != FAMILY_IDS[ordinal]
            || unsigned(field(row, "case_count")?)? != FAMILY_COUNTS[ordinal]
        {
            return Err(IndependenceV1Error::Binding);
        }
    }
    Ok(damage)
}

fn ascii(value: &ManifestValue) -> Result<&str> {
    let value = text(value)?;
    if value.is_empty()
        || value.len() > 128
        || !value
            .as_bytes()
            .iter()
            .all(|byte| (0x20..=0x7e).contains(byte))
    {
        return Err(IndependenceV1Error::Manifest);
    }
    Ok(value)
}

fn validate_parameter_rows_v1(value: &ManifestValue) -> Result<()> {
    let rows = array(value)?;
    let mut prior = "";
    for value in rows {
        let row = object(value)?;
        if !exact_keys(row, &["id", "value_type", "value"]) {
            return Err(IndependenceV1Error::Manifest);
        }
        let id = ascii(field(row, "id")?)?;
        if id <= prior {
            return Err(IndependenceV1Error::Binding);
        }
        prior = id;
        match ascii(field(row, "value_type")?)? {
            "u64" => {
                unsigned(field(row, "value")?)?;
            }
            "ascii" => {
                ascii(field(row, "value")?)?;
            }
            "u64-list" => {
                let values = array(field(row, "value")?)?;
                if values.len() > 4_194_304 {
                    return Err(IndependenceV1Error::Manifest);
                }
                for value in values {
                    unsigned(value)?;
                }
            }
            "coordinate-list" => {
                let values = array(field(row, "value")?)?;
                if values.len() > 4_194_304 {
                    return Err(IndependenceV1Error::Manifest);
                }
                for coordinate in values {
                    let coordinate = array(coordinate)?;
                    if coordinate.len() != 2 {
                        return Err(IndependenceV1Error::Manifest);
                    }
                    unsigned(&coordinate[0])?;
                    unsigned(&coordinate[1])?;
                }
            }
            _ => return Err(IndependenceV1Error::Manifest),
        }
    }
    Ok(())
}

fn parameter_ids_v1(value: &ManifestValue) -> Result<Vec<&str>> {
    array(value)?
        .iter()
        .map(|value| {
            let row = object(value)?;
            text(field(row, "id")?)
        })
        .collect()
}

fn parameter_u64_v1(value: &ManifestValue, id: &str) -> Result<u64> {
    for value in array(value)? {
        let row = object(value)?;
        if text(field(row, "id")?)? == id {
            return unsigned(field(row, "value")?);
        }
    }
    Err(IndependenceV1Error::Binding)
}

fn parameter_u64_list_v1(value: &ManifestValue, id: &str) -> Result<Vec<u64>> {
    for value in array(value)? {
        let row = object(value)?;
        if text(field(row, "id")?)? == id {
            return array(field(row, "value")?)?.iter().map(unsigned).collect();
        }
    }
    Err(IndependenceV1Error::Binding)
}

fn parameter_coordinates_v1(value: &ManifestValue, id: &str) -> Result<Vec<[u64; 2]>> {
    for value in array(value)? {
        let row = object(value)?;
        if text(field(row, "id")?)? == id {
            return array(field(row, "value")?)?
                .iter()
                .map(|coordinate| {
                    let coordinate = array(coordinate)?;
                    if coordinate.len() != 2 {
                        return Err(IndependenceV1Error::Manifest);
                    }
                    Ok([unsigned(&coordinate[0])?, unsigned(&coordinate[1])?])
                })
                .collect();
        }
    }
    Err(IndependenceV1Error::Binding)
}

fn exact_d2_placements_v1(candidate: &CandidateEvidenceV1) -> Result<Vec<[u64; 2]>> {
    let square = 32_u64.max(candidate.interior_side / 32);
    let domain = candidate
        .interior_side
        .checked_sub(square)
        .and_then(|value| value.checked_add(1))
        .ok_or(IndependenceV1Error::Arithmetic)?;
    let choices = [0_u64, domain / 2, domain - 1];
    let mut placements = Vec::with_capacity(256);
    let mut excluded = Vec::with_capacity(9);
    for row in choices {
        for column in choices {
            placements.push([
                checked_add(row, candidate.width)?,
                checked_add(column, candidate.width)?,
            ]);
            excluded.push(checked_add(checked_mul(row, domain)?, column)?);
        }
    }
    excluded.sort_unstable();
    let population = checked_mul(domain, domain)?
        .checked_sub(excluded.len() as u64)
        .ok_or(IndependenceV1Error::Arithmetic)?;
    let sampled = sample_without_replacement(
        usize::try_from(population).map_err(|_| IndependenceV1Error::Arithmetic)?,
        256 - placements.len(),
        5_134_751_402_299_490_304,
    )
    .map_err(|_| IndependenceV1Error::Arithmetic)?;
    for sampled in sampled {
        let mut flat = sampled as u64;
        for excluded in &excluded {
            if *excluded <= flat {
                flat = checked_add(flat, 1)?;
            }
        }
        placements.push([
            checked_add(flat / domain, candidate.width)?,
            checked_add(flat % domain, candidate.width)?,
        ]);
    }
    if placements.len() != 256 {
        return Err(IndependenceV1Error::Binding);
    }
    Ok(placements)
}

fn exact_d3_population_v1(candidate: &CandidateEvidenceV1, stratum: u64) -> Result<Vec<u64>> {
    if !matches!(stratum, 2 | 3) {
        return Err(IndependenceV1Error::Binding);
    }
    let required = candidate
        .sections
        .iter()
        .filter(|section| section.closure_class == 128)
        .map(|section| section.section_id)
        .collect::<BTreeSet<_>>();
    let mut population = BTreeSet::new();
    for unit in &candidate.units {
        if stratum == 2 && !required.contains(&unit.section_id) {
            continue;
        }
        for bit in 0..1_728_u64 {
            let physical = final_cell_for_unit_bit(candidate, unit, bit)?;
            let row = physical / candidate.interior_side;
            let column = physical % candidate.interior_side;
            if stratum == 2
                || bit < 16
                || bit >= 1_712
                || bit % 8 == 0
                || bit % 8 == 7
                || matches!(row % 16, 0 | 15)
                || matches!(column % 16, 0 | 15)
            {
                population.insert(physical);
            }
        }
    }
    Ok(population.into_iter().collect())
}

fn exact_d3_coordinates_v1(
    candidate: &CandidateEvidenceV1,
    ordinal: u64,
    population_cache: &mut BTreeMap<u64, Vec<u64>>,
) -> Result<Vec<[u64; 2]>> {
    if ordinal >= 128 {
        return Err(IndependenceV1Error::Binding);
    }
    let seed = checked_add(5_134_751_402_299_490_304, ordinal)?;
    let stratum = ordinal / 32;
    let weight = 64_u64.max(candidate.population.div_ceil(2_000));
    let selected = match stratum {
        0 => sample_without_replacement(
            usize::try_from(candidate.population).map_err(|_| IndependenceV1Error::Arithmetic)?,
            usize::try_from(weight).map_err(|_| IndependenceV1Error::Arithmetic)?,
            seed,
        )
        .map_err(|_| IndependenceV1Error::Arithmetic)?
        .into_iter()
        .map(|physical| physical as u64)
        .collect::<Vec<_>>(),
        1 => {
            let window = 32_u64.max(candidate.interior_side / 8);
            let origins = candidate
                .interior_side
                .checked_sub(window)
                .and_then(|value| value.checked_add(1))
                .ok_or(IndependenceV1Error::Arithmetic)?;
            let mut stream = CounterWords::new(
                WINDOW_DOMAIN,
                seed,
                usize::try_from(origins).map_err(|_| IndependenceV1Error::Arithmetic)?,
            )
            .map_err(|_| IndependenceV1Error::Arithmetic)?;
            let top = stream
                .unbiased(usize::try_from(origins).map_err(|_| IndependenceV1Error::Arithmetic)?)
                .map_err(|_| IndependenceV1Error::Arithmetic)? as u64;
            let left = stream
                .unbiased(usize::try_from(origins).map_err(|_| IndependenceV1Error::Arithmetic)?)
                .map_err(|_| IndependenceV1Error::Arithmetic)? as u64;
            sample_without_replacement(
                usize::try_from(checked_mul(window, window)?)
                    .map_err(|_| IndependenceV1Error::Arithmetic)?,
                usize::try_from(weight).map_err(|_| IndependenceV1Error::Arithmetic)?,
                seed,
            )
            .map_err(|_| IndependenceV1Error::Arithmetic)?
            .into_iter()
            .map(|index| {
                let index = index as u64;
                checked_add(
                    checked_mul(checked_add(top, index / window)?, candidate.interior_side)?,
                    checked_add(left, index % window)?,
                )
            })
            .collect::<Result<Vec<_>>>()?
        }
        2 | 3 => {
            if !population_cache.contains_key(&stratum) {
                population_cache.insert(stratum, exact_d3_population_v1(candidate, stratum)?);
            }
            let population = population_cache
                .get(&stratum)
                .ok_or(IndependenceV1Error::Binding)?;
            sample_without_replacement(
                population.len(),
                usize::try_from(weight).map_err(|_| IndependenceV1Error::Arithmetic)?,
                seed,
            )
            .map_err(|_| IndependenceV1Error::Arithmetic)?
            .into_iter()
            .map(|index| {
                population
                    .get(index)
                    .copied()
                    .ok_or(IndependenceV1Error::Binding)
            })
            .collect::<Result<Vec<_>>>()?
        }
        _ => unreachable!(),
    };
    selected
        .into_iter()
        .map(|physical| {
            Ok([
                checked_add(physical / candidate.interior_side, candidate.width)?,
                checked_add(physical % candidate.interior_side, candidate.width)?,
            ])
        })
        .collect()
}

fn expected_case_shape_v1(
    family: usize,
    ordinal: u64,
) -> Result<(&'static str, &'static str, &'static [&'static str])> {
    const D0: &[&str] = &["polarity_id", "transform_id"];
    const D1: &[&str] = &["sector_id"];
    const D2: &[&str] = &["side", "top_left"];
    const D3: &[&str] = &["coordinates", "seed", "stratum_id"];
    const D4: &[&str] = &["omitted_unit_id"];
    const D5: &[&str] = &["permutation_ordinal"];
    const D6: &[&str] = &["sector_id", "unit_id"];
    const MAPPING: &[&str] = &["mutant_ordinal"];
    const CHECK_LOCAL: &[&str] = &["case_ordinal", "target_unit_ids"];
    const CHECK_SECTION: &[&str] = &["case_ordinal", "section_id"];
    const CODE: &[&str] = &["case_ordinal", "target_unit_ids"];
    const ROUTE: &[&str] = &["alternate_profile_version"];
    const SPLICE: &[&str] = &["source_profile_version", "target_unit_ids"];
    const VALID: &[&str] = &["section_id", "target_unit_id"];
    const D7_D2: &[&str] = &["d2_ordinal", "side"];
    const D7_D3: &[&str] = &["seed"];
    const MISSING: &[&str] = &["omitted_unit_ids"];
    const ALGEBRA: &[&str] = &["erasures", "errors", "target_unit_ids"];
    const RESOURCE: &[&str] = &["declared_value"];
    const GEOMETRY: &[&str] = &["side"];
    Ok(match family {
        0 => ("OBS_BITS", "clean-transform-polarity", D0),
        1 => ("OBS_MATRIX", "erase-one-complete-shell-sector", D1),
        2 => ("OBS_MATRIX", "erase-square-in-protected-interior", D2),
        3 => ("OBS_MATRIX", "fixed-weight-unknown-bit-substitution", D3),
        4 => ("OBS_UNITS", "omit-one-physical-unit-observation", D4),
        5 => ("OBS_UNITS", "permute-intact-physical-unit-observations", D5),
        6 => (
            "OBS_MATRIX",
            "erase-shell-sector-union-one-physical-unit-cell-set",
            D6,
        ),
        7 => match ordinal {
            0..=2 => ("OBS_BITS", "mapping-mutants", MAPPING),
            3..=4 => ("OBS_UNITS", "check-mutants", CHECK_LOCAL),
            5..=6 => ("OBS_UNITS", "check-mutants", CHECK_SECTION),
            7..=9 => ("OBS_UNITS", "code-mutants", CODE),
            10 => ("OBS_BITS", "route-conflicts", ROUTE),
            11..=15 => ("OBS_UNITS", "cross-profile-splices", SPLICE),
            16 => ("OBS_UNITS", "valid-copy-conflicts", VALID),
            17..=272 => ("OBS_MATRIX", "d2-one-beyond", D7_D2),
            273..=400 => ("OBS_MATRIX", "d3-one-beyond", D7_D3),
            401 => ("OBS_UNITS", "missing-unit-one-beyond", MISSING),
            402..=404 => ("OBS_MATRIX", "algebraic-one-beyond", ALGEBRA),
            405..=406 => ("OBS_BITS", "resource-route-one-beyond", RESOURCE),
            407 => ("OBS_BITS", "geometry-one-beyond", GEOMETRY),
            _ => return Err(IndependenceV1Error::Binding),
        },
        _ => return Err(IndependenceV1Error::Binding),
    })
}

fn validate_case_row_v1(
    value: &ManifestValue,
    family: usize,
    ordinal: u64,
    candidate: &CandidateEvidenceV1,
    d2_placements: &[[u64; 2]],
    d3_population_cache: &mut BTreeMap<u64, Vec<u64>>,
) -> Result<()> {
    let row = object(value)?;
    if !exact_keys(
        row,
        &[
            "case_id",
            "family_id",
            "channel",
            "operator",
            "parameter_projection",
            "observation_sha256",
            "decoder_result_sha256",
            "expected_artifact_state",
            "expected_section_states",
            "wrong_accept_count",
        ],
    ) || text(field(row, "case_id")?)? != format!("{}-{ordinal:06}", FAMILY_IDS[family])
        || text(field(row, "family_id")?)? != FAMILY_IDS[family]
        || !matches!(
            text(field(row, "channel")?)?,
            "OBS_BITS" | "OBS_MATRIX" | "OBS_UNITS"
        )
        || !lower_sha256(text(field(row, "observation_sha256")?)?)
        || !lower_sha256(text(field(row, "decoder_result_sha256")?)?)
        || !matches!(
            text(field(row, "expected_artifact_state")?)?,
            "exact" | "degraded" | "failure" | "ambiguous" | "resource-limit"
        )
        || unsigned(field(row, "wrong_accept_count")?)? != 0
    {
        return Err(IndependenceV1Error::Binding);
    }
    ascii(field(row, "operator")?)?;
    let parameters = field(row, "parameter_projection")?;
    validate_parameter_rows_v1(parameters)?;
    let (expected_channel, expected_operator, expected_parameters) =
        expected_case_shape_v1(family, ordinal)?;
    if text(field(row, "channel")?)? != expected_channel
        || text(field(row, "operator")?)? != expected_operator
        || parameter_ids_v1(parameters)? != expected_parameters
    {
        return Err(IndependenceV1Error::Binding);
    }
    match family {
        0 => {
            if parameter_u64_v1(parameters, "transform_id")? != ordinal / 2
                || parameter_u64_v1(parameters, "polarity_id")? != ordinal % 2
            {
                return Err(IndependenceV1Error::Binding);
            }
        }
        1 => {
            if parameter_u64_v1(parameters, "sector_id")? != ordinal {
                return Err(IndependenceV1Error::Binding);
            }
        }
        2 => {
            if parameter_u64_v1(parameters, "side")? != 55
                || parameter_coordinates_v1(parameters, "top_left")?
                    != [*d2_placements
                        .get(
                            usize::try_from(ordinal)
                                .map_err(|_| IndependenceV1Error::Arithmetic)?,
                        )
                        .ok_or(IndependenceV1Error::Binding)?]
            {
                return Err(IndependenceV1Error::Binding);
            }
        }
        3 => {
            if parameter_u64_v1(parameters, "seed")? != 5_134_751_402_299_490_304 + ordinal
                || parameter_u64_v1(parameters, "stratum_id")? != ordinal / 32
                || parameter_coordinates_v1(parameters, "coordinates")?
                    != exact_d3_coordinates_v1(candidate, ordinal, d3_population_cache)?
            {
                return Err(IndependenceV1Error::Binding);
            }
        }
        4 => {
            if parameter_u64_v1(parameters, "omitted_unit_id")? != ordinal + 1 {
                return Err(IndependenceV1Error::Binding);
            }
        }
        5 => {
            if parameter_u64_v1(parameters, "permutation_ordinal")? != ordinal {
                return Err(IndependenceV1Error::Binding);
            }
        }
        6 => {
            if parameter_u64_v1(parameters, "sector_id")? != ordinal / 1_841
                || parameter_u64_v1(parameters, "unit_id")? != ordinal % 1_841 + 1
            {
                return Err(IndependenceV1Error::Binding);
            }
        }
        7 => {
            let target_ids = [1_u64, 2, 3, 4, 5];
            let valid = match ordinal {
                0..=2 => parameter_u64_v1(parameters, "mutant_ordinal")? == ordinal,
                3..=4 => {
                    parameter_u64_v1(parameters, "case_ordinal")? == ordinal - 3
                        && parameter_u64_list_v1(parameters, "target_unit_ids")? == target_ids
                }
                5..=6 => {
                    parameter_u64_v1(parameters, "case_ordinal")? == ordinal - 3
                        && parameter_u64_v1(parameters, "section_id")? == 2
                }
                7..=9 => {
                    parameter_u64_v1(parameters, "case_ordinal")? == ordinal - 7
                        && parameter_u64_list_v1(parameters, "target_unit_ids")? == target_ids
                }
                10 => parameter_u64_v1(parameters, "alternate_profile_version")? == 3,
                11..=15 => {
                    parameter_u64_v1(parameters, "source_profile_version")? == ordinal - 9
                        && parameter_u64_list_v1(parameters, "target_unit_ids")? == target_ids
                }
                16 => {
                    parameter_u64_v1(parameters, "section_id")? == 1
                        && parameter_u64_v1(parameters, "target_unit_id")? == 1
                }
                17..=272 => {
                    parameter_u64_v1(parameters, "d2_ordinal")? == ordinal - 17
                        && parameter_u64_v1(parameters, "side")? == 56
                }
                273..=400 => {
                    parameter_u64_v1(parameters, "seed")?
                        == 5_134_751_402_299_490_304 + ordinal - 273
                }
                401 => parameter_u64_list_v1(parameters, "omitted_unit_ids")? == target_ids,
                402..=404 => {
                    let (errors, erasures) = [(2, 0), (1, 2), (0, 4)][ordinal as usize - 402];
                    parameter_u64_v1(parameters, "errors")? == errors
                        && parameter_u64_v1(parameters, "erasures")? == erasures
                        && parameter_u64_list_v1(parameters, "target_unit_ids")? == target_ids
                }
                405 => parameter_u64_v1(parameters, "declared_value")? == 268_435_457,
                406 => parameter_u64_v1(parameters, "declared_value")? == 16_777_217,
                407 => parameter_u64_v1(parameters, "side")? == 2_056,
                _ => false,
            };
            if !valid {
                return Err(IndependenceV1Error::Binding);
            }
        }
        _ => unreachable!(),
    }
    let states = array(field(row, "expected_section_states")?)?;
    if states.len() != candidate.sections.len() {
        return Err(IndependenceV1Error::Binding);
    }
    let mut prior_section = 0_u64;
    for (ordinal, state) in states.iter().enumerate() {
        let state = object(state)?;
        if !exact_keys(state, &["section_id", "state"]) {
            return Err(IndependenceV1Error::Manifest);
        }
        let section_id = unsigned(field(state, "section_id")?)?;
        if section_id
            != candidate
                .sections
                .get(ordinal)
                .ok_or(IndependenceV1Error::Binding)?
                .section_id
            || section_id <= prior_section
            || !matches!(
                text(field(state, "state")?)?,
                "verified" | "recovered" | "incomplete" | "corrupt" | "ambiguous" | "unknown"
            )
        {
            return Err(IndependenceV1Error::Binding);
        }
        prior_section = section_id;
    }
    Ok(())
}

fn canonical_case_rows_sha256(rows: &[ManifestValue]) -> Result<String> {
    // The owner hashes the complete family case-row array without a trailing
    // LF. D6 alone has 7,364 rows and may exceed the one-file manifest cap, so
    // stream exact canonical row encodings rather than allocating or relaxing
    // the shared 1 MiB serializer limit.
    let mut hasher = Sha256::new();
    hasher.update(b"[");
    for (ordinal, row) in rows.iter().enumerate() {
        if ordinal != 0 {
            hasher.update(b",");
        }
        let mut raw = serialize_manifest(row).map_err(|_| IndependenceV1Error::Manifest)?;
        if raw.pop() != Some(b'\n') {
            return Err(IndependenceV1Error::Manifest);
        }
        hasher.update(raw);
    }
    hasher.update(b"]");
    Ok(format!("{:x}", hasher.finalize()))
}

fn render_case_shard_v1(
    damage_manifest_identity: &str,
    family_id: &str,
    shard_ordinal: u64,
    case_first: u64,
    rows: &[ManifestValue],
) -> Result<Vec<u8>> {
    if rows.is_empty() || rows.len() > 256 {
        return Err(IndependenceV1Error::Manifest);
    }
    let wrong_accept_count = rows.iter().try_fold(0_u64, |sum, value| {
        checked_add(sum, unsigned(field(object(value)?, "wrong_accept_count")?)?)
    })?;
    let without_identity = manifest_object([
        ("schema", manifest_string("golden-board.m2-damage-cases/v1")),
        (
            "damage_manifest_identity",
            manifest_string(damage_manifest_identity),
        ),
        ("profile_id", manifest_string(PROFILE_ID_V1)),
        ("family_id", manifest_string(family_id)),
        ("shard_ordinal", ManifestValue::U64(shard_ordinal)),
        ("case_first", ManifestValue::U64(case_first)),
        ("case_rows", ManifestValue::Array(rows.to_vec())),
        (
            "summary",
            manifest_object([
                ("case_count", ManifestValue::U64(rows.len() as u64)),
                ("wrong_accept_count", ManifestValue::U64(wrong_accept_count)),
            ]),
        ),
    ]);
    let without_identity_raw =
        serialize_manifest(&without_identity).map_err(|_| IndependenceV1Error::Manifest)?;
    let manifest_identity = identity_hex(IDENTITY_DOMAIN, &[&without_identity_raw])
        .map_err(|_| IndependenceV1Error::Manifest)?;
    let mut value = without_identity;
    object_mut(
        object_mut(&mut value)?
            .get_mut("summary")
            .ok_or(IndependenceV1Error::Manifest)?,
    )?
    .insert(
        "manifest_identity".to_owned(),
        manifest_string(&manifest_identity),
    );
    serialize_manifest(&value).map_err(|_| IndependenceV1Error::Manifest)
}

fn render_nested_summary_identity_v1(mut value: ManifestValue) -> Result<Vec<u8>> {
    let raw = serialize_manifest(&value).map_err(|_| IndependenceV1Error::Manifest)?;
    let manifest_identity =
        identity_hex(IDENTITY_DOMAIN, &[&raw]).map_err(|_| IndependenceV1Error::Manifest)?;
    object_mut(
        object_mut(&mut value)?
            .get_mut("summary")
            .ok_or(IndependenceV1Error::Manifest)?,
    )?
    .insert(
        "manifest_identity".to_owned(),
        manifest_string(&manifest_identity),
    );
    serialize_manifest(&value).map_err(|_| IndependenceV1Error::Manifest)
}

/// Render the complete canonical v1 gate-6 root, eight family manifests, and
/// maximal case shards from independently regenerated common case rows.
///
/// The returned bundle is immediately re-admitted by the strict gate-7
/// parser.  Retained gate-6 files are neither accepted nor consulted.
pub fn render_damage_evidence_bundle_v1(
    candidate_manifest_raw: &[u8],
    ownership_ledger_raw: &[u8],
    clean_observation_sha256: &str,
    cases: &[Vec<ManifestValue>; 8],
    boundary_rows: &[ManifestValue],
) -> Result<RenderedDamageEvidenceBundleV1> {
    let candidate = candidate_evidence_v1(candidate_manifest_raw, ownership_ledger_raw)?;
    if !lower_sha256(clean_observation_sha256)
        || boundary_rows.len() != BOUNDARY_IDS.len()
        || cases
            .iter()
            .zip(FAMILY_COUNTS)
            .any(|(rows, count)| rows.len() as u64 != count)
    {
        return Err(IndependenceV1Error::Binding);
    }

    let d2_placements = exact_d2_placements_v1(&candidate)?;
    let mut d3_population_cache = BTreeMap::<u64, Vec<u64>>::new();
    for (family, rows) in cases.iter().enumerate() {
        for (ordinal, row) in rows.iter().enumerate() {
            validate_case_row_v1(
                row,
                family,
                ordinal as u64,
                &candidate,
                &d2_placements,
                &mut d3_population_cache,
            )?;
        }
    }

    for (ordinal, value) in boundary_rows.iter().enumerate() {
        let row = object(value)?;
        if !exact_keys(row, &["kat_id", "result_sha256", "result"])
            || text(field(row, "kat_id")?)? != BOUNDARY_IDS[ordinal]
            || text(field(row, "result_sha256")?)? != BOUNDARY_RESULT_SHA256[ordinal]
            || text(field(row, "result")?)? != "pass"
        {
            return Err(IndependenceV1Error::Binding);
        }
    }

    let family_rows = (0..8)
        .map(|family| {
            Ok(manifest_object([
                ("family_id", manifest_string(FAMILY_IDS[family])),
                ("case_count", ManifestValue::U64(FAMILY_COUNTS[family])),
                ("wrong_accept_count", ManifestValue::U64(0)),
                ("result", manifest_string("pass")),
                (
                    "case_rows_sha256",
                    manifest_string(&canonical_case_rows_sha256(&cases[family])?),
                ),
            ]))
        })
        .collect::<Result<Vec<_>>>()?;
    let root_without_identity = manifest_object([
        (
            "schema",
            manifest_string("golden-board.m2-damage-manifest/v1"),
        ),
        (
            "damage_policy_sha256",
            manifest_string(&owner_sha256(include_bytes!(
                "../../../spec/damage-policy-v1.toml"
            ))),
        ),
        (
            "profile_policy_sha256",
            manifest_string(&owner_sha256(include_bytes!(
                "../../../spec/profile-policy-v1.toml"
            ))),
        ),
        (
            "profile_limits_sha256",
            manifest_string(&owner_sha256(include_bytes!(
                "../../../spec/profile-limits-v1.toml"
            ))),
        ),
        (
            "bootstrap_spec_sha256",
            manifest_string(&owner_sha256(include_bytes!(
                "../../../spec/bootstrap-v1.md"
            ))),
        ),
        (
            "route_data_sha256",
            manifest_string(&owner_sha256(include_bytes!(
                "../../../spec/route-data-v1.json"
            ))),
        ),
        (
            "recipient_package_sha256",
            manifest_string(RECIPIENT_PACKAGE_SHA256),
        ),
        ("profile_id", manifest_string(PROFILE_ID_V1)),
        (
            "candidate_manifest_sha256",
            manifest_string(&digest(candidate_manifest_raw)),
        ),
        (
            "clean_observation_sha256",
            manifest_string(clean_observation_sha256),
        ),
        ("family_rows", ManifestValue::Array(family_rows)),
        (
            "boundary_kat_rows",
            ManifestValue::Array(boundary_rows.to_vec()),
        ),
        (
            "summary",
            manifest_object([
                (
                    "family_case_counts",
                    ManifestValue::Array(
                        (0..8)
                            .map(|family| {
                                manifest_object([
                                    ("family_id", manifest_string(FAMILY_IDS[family])),
                                    ("case_count", ManifestValue::U64(FAMILY_COUNTS[family])),
                                ])
                            })
                            .collect(),
                    ),
                ),
                ("wrong_accept_count", ManifestValue::U64(0)),
            ]),
        ),
    ]);
    let damage_manifest = render_nested_summary_identity_v1(root_without_identity)?;
    let root_value =
        validate_canonical_manifest(&damage_manifest).map_err(|_| IndependenceV1Error::Manifest)?;
    let root_identity = text(field(
        object(field(object(&root_value)?, "summary")?)?,
        "manifest_identity",
    )?)?
    .to_owned();

    const GUARANTEES: [&str; 8] = [
        "all_declared_m2_sections_exact",
        "all_declared_m2_sections_exact",
        "m2_required_closure",
        "m2_required_closure",
        "m2_required_closure",
        "all_declared_m2_sections_exact",
        "m2_required_closure",
        "correct_or_explicit_failure",
    ];
    let mut family_manifests = Vec::with_capacity(8);
    let mut case_shards = Vec::new();
    for family in 0..8 {
        let mut references = Vec::new();
        let mut case_first = 0_usize;
        let mut shard_ordinal = 0_u64;
        while case_first < cases[family].len() {
            let mut low = 1_usize;
            let mut high = 256.min(cases[family].len() - case_first);
            let mut best = None;
            while low <= high {
                let count = low + (high - low) / 2;
                match render_case_shard_v1(
                    &root_identity,
                    FAMILY_IDS[family],
                    shard_ordinal,
                    case_first as u64,
                    &cases[family][case_first..case_first + count],
                ) {
                    Ok(raw) if raw.len() <= 1_048_576 => {
                        best = Some((count, raw));
                        low = count + 1;
                    }
                    _ => high = count - 1,
                }
            }
            let (count, raw) = best.ok_or(IndependenceV1Error::Manifest)?;
            references.push(manifest_object([
                ("shard_ordinal", ManifestValue::U64(shard_ordinal)),
                ("case_first", ManifestValue::U64(case_first as u64)),
                ("case_count", ManifestValue::U64(count as u64)),
                ("manifest_sha256", manifest_string(&digest(&raw))),
            ]));
            case_shards.push((
                format!(
                    "damage-{}-cases-{shard_ordinal:04}.json",
                    FAMILY_IDS[family]
                ),
                raw,
            ));
            case_first = case_first
                .checked_add(count)
                .ok_or(IndependenceV1Error::Arithmetic)?;
            shard_ordinal = shard_ordinal
                .checked_add(1)
                .ok_or(IndependenceV1Error::Arithmetic)?;
        }
        family_manifests.push(render_nested_summary_identity_v1(manifest_object([
            (
                "schema",
                manifest_string("golden-board.m2-damage-family/v1"),
            ),
            ("damage_manifest_identity", manifest_string(&root_identity)),
            ("profile_id", manifest_string(PROFILE_ID_V1)),
            ("family_id", manifest_string(FAMILY_IDS[family])),
            ("guarantee_id", manifest_string(GUARANTEES[family])),
            ("shard_rows", ManifestValue::Array(references)),
            (
                "summary",
                manifest_object([
                    ("case_count", ManifestValue::U64(FAMILY_COUNTS[family])),
                    ("wrong_accept_count", ManifestValue::U64(0)),
                    ("result", manifest_string("pass")),
                ]),
            ),
        ]))?);
    }

    let family_refs = family_manifests
        .iter()
        .map(Vec::as_slice)
        .collect::<Vec<_>>();
    let shard_refs = case_shards
        .iter()
        .map(|(_, raw)| raw.as_slice())
        .collect::<Vec<_>>();
    admit_damage_evidence_bundle_v1(
        &damage_manifest,
        &family_refs,
        &shard_refs,
        candidate_manifest_raw,
        ownership_ledger_raw,
    )?;
    Ok(RenderedDamageEvidenceBundleV1 {
        damage_manifest,
        family_manifests,
        case_shards,
    })
}

pub fn admit_damage_evidence_bundle_v1(
    damage_manifest_raw: &[u8],
    family_manifest_raws: &[&[u8]],
    case_shard_raws: &[&[u8]],
    candidate_manifest_raw: &[u8],
    ownership_ledger_raw: &[u8],
) -> Result<()> {
    let candidate = candidate_evidence_v1(candidate_manifest_raw, ownership_ledger_raw)?;
    damage_evidence_v1(
        damage_manifest_raw,
        family_manifest_raws,
        case_shard_raws,
        candidate_manifest_raw,
        &candidate,
    )?;
    Ok(())
}

fn damage_evidence_v1(
    damage_manifest_raw: &[u8],
    family_manifest_raws: &[&[u8]],
    case_shard_raws: &[&[u8]],
    candidate_manifest_raw: &[u8],
    candidate: &CandidateEvidenceV1,
) -> Result<DamageEvidenceV1> {
    if family_manifest_raws.len() != 8 || !(8..=10_038).contains(&case_shard_raws.len()) {
        return Err(IndependenceV1Error::Manifest);
    }
    let root = admit_damage_root(damage_manifest_raw, &digest(candidate_manifest_raw))?;
    let root = object(&root)?;
    let root_summary = object(field(root, "summary")?)?;
    let root_identity = text(field(root_summary, "manifest_identity")?)?;
    let root_families = array(field(root, "family_rows")?)?;

    let mut shards = BTreeMap::<(usize, u64), (&[u8], ManifestValue)>::new();
    let mut prior_shard_key = None;
    for raw in case_shard_raws {
        if raw.is_empty() || raw.len() > 1_048_576 {
            return Err(IndependenceV1Error::Manifest);
        }
        let value = validate_canonical_manifest(raw).map_err(|_| IndependenceV1Error::Manifest)?;
        let row = object(&value)?;
        if !exact_keys(
            row,
            &[
                "schema",
                "damage_manifest_identity",
                "profile_id",
                "family_id",
                "shard_ordinal",
                "case_first",
                "case_rows",
                "summary",
            ],
        ) || text(field(row, "schema")?)? != "golden-board.m2-damage-cases/v1"
            || text(field(row, "damage_manifest_identity")?)? != root_identity
            || text(field(row, "profile_id")?)? != PROFILE_ID_V1
        {
            return Err(IndependenceV1Error::Binding);
        }
        let family_id = text(field(row, "family_id")?)?;
        let family = FAMILY_IDS
            .iter()
            .position(|expected| *expected == family_id)
            .ok_or(IndependenceV1Error::Manifest)?;
        let ordinal = unsigned(field(row, "shard_ordinal")?)?;
        let key = (family, ordinal);
        let case_rows = array(field(row, "case_rows")?)?;
        let summary = object(field(row, "summary")?)?;
        if case_rows.is_empty()
            || case_rows.len() > 256
            || !exact_keys(
                summary,
                &["case_count", "wrong_accept_count", "manifest_identity"],
            )
            || unsigned(field(summary, "case_count")?)? != case_rows.len() as u64
            || unsigned(field(summary, "wrong_accept_count")?)? != 0
            || text(field(summary, "manifest_identity")?)? != nested_manifest_identity(&value)?
            || prior_shard_key.is_some_and(|prior| prior >= key)
            || shards.insert(key, (*raw, value)).is_some()
        {
            return Err(IndependenceV1Error::Binding);
        }
        prior_shard_key = Some(key);
    }

    let guarantees = [
        "all_declared_m2_sections_exact",
        "all_declared_m2_sections_exact",
        "m2_required_closure",
        "m2_required_closure",
        "m2_required_closure",
        "all_declared_m2_sections_exact",
        "m2_required_closure",
        "correct_or_explicit_failure",
    ];
    let mut cases: [Vec<ManifestValue>; 8] = std::array::from_fn(|_| Vec::new());
    let mut family_pass = [false; 8];
    let d2_placements = exact_d2_placements_v1(candidate)?;
    let mut d3_population_cache = BTreeMap::<u64, Vec<u64>>::new();
    for (family, raw) in family_manifest_raws.iter().enumerate() {
        if raw.is_empty() || raw.len() > 1_048_576 {
            return Err(IndependenceV1Error::Manifest);
        }
        let value = validate_canonical_manifest(raw).map_err(|_| IndependenceV1Error::Manifest)?;
        let row = object(&value)?;
        if !exact_keys(
            row,
            &[
                "schema",
                "damage_manifest_identity",
                "profile_id",
                "family_id",
                "guarantee_id",
                "shard_rows",
                "summary",
            ],
        ) || text(field(row, "schema")?)? != "golden-board.m2-damage-family/v1"
            || text(field(row, "damage_manifest_identity")?)? != root_identity
            || text(field(row, "profile_id")?)? != PROFILE_ID_V1
            || text(field(row, "family_id")?)? != FAMILY_IDS[family]
            || text(field(row, "guarantee_id")?)? != guarantees[family]
        {
            return Err(IndependenceV1Error::Binding);
        }
        let references = array(field(row, "shard_rows")?)?;
        if references.is_empty() || references.len() > FAMILY_COUNTS[family] as usize {
            return Err(IndependenceV1Error::Manifest);
        }
        let mut case_first = 0_u64;
        let mut shard_slices = Vec::<(u64, Vec<ManifestValue>)>::new();
        for (ordinal, reference) in references.iter().enumerate() {
            let reference = object(reference)?;
            if !exact_keys(
                reference,
                &[
                    "shard_ordinal",
                    "case_first",
                    "case_count",
                    "manifest_sha256",
                ],
            ) || unsigned(field(reference, "shard_ordinal")?)? != ordinal as u64
                || unsigned(field(reference, "case_first")?)? != case_first
                || !lower_sha256(text(field(reference, "manifest_sha256")?)?)
            {
                return Err(IndependenceV1Error::Binding);
            }
            let (shard_raw, shard_value) = shards
                .remove(&(family, ordinal as u64))
                .ok_or(IndependenceV1Error::Binding)?;
            let shard = object(&shard_value)?;
            let shard_rows = array(field(shard, "case_rows")?)?;
            if unsigned(field(reference, "case_count")?)? != shard_rows.len() as u64
                || unsigned(field(shard, "case_first")?)? != case_first
                || digest(shard_raw) != text(field(reference, "manifest_sha256")?)?
            {
                return Err(IndependenceV1Error::Binding);
            }
            for value in shard_rows {
                validate_case_row_v1(
                    value,
                    family,
                    case_first,
                    candidate,
                    &d2_placements,
                    &mut d3_population_cache,
                )?;
                cases[family].push(value.clone());
                case_first = checked_add(case_first, 1)?;
            }
            shard_slices.push((unsigned(field(shard, "case_first")?)?, shard_rows.to_vec()));
        }
        if case_first != FAMILY_COUNTS[family] {
            return Err(IndependenceV1Error::Binding);
        }
        for (ordinal, (case_first, rows)) in shard_slices.iter().enumerate() {
            if rows.len() < 256 {
                let next_index = usize::try_from(checked_add(*case_first, rows.len() as u64)?)
                    .map_err(|_| IndependenceV1Error::Arithmetic)?;
                if let Some(next) = cases[family].get(next_index) {
                    let mut expanded = rows.clone();
                    expanded.push(next.clone());
                    if render_case_shard_v1(
                        root_identity,
                        FAMILY_IDS[family],
                        ordinal as u64,
                        *case_first,
                        &expanded,
                    )
                    .is_ok_and(|raw| raw.len() <= 1_048_576)
                    {
                        return Err(IndependenceV1Error::Binding);
                    }
                }
            }
        }
        let summary = object(field(row, "summary")?)?;
        let root_family = object(&root_families[family])?;
        if !exact_keys(
            summary,
            &[
                "case_count",
                "wrong_accept_count",
                "result",
                "manifest_identity",
            ],
        ) || unsigned(field(summary, "case_count")?)? != FAMILY_COUNTS[family]
            || unsigned(field(summary, "wrong_accept_count")?)? != 0
            || text(field(summary, "result")?)? != "pass"
            || text(field(summary, "manifest_identity")?)? != nested_manifest_identity(&value)?
            || text(field(root_family, "case_rows_sha256")?)?
                != canonical_case_rows_sha256(&cases[family])?
        {
            return Err(IndependenceV1Error::Binding);
        }
        family_pass[family] = true;
    }
    if !shards.is_empty() {
        return Err(IndependenceV1Error::Binding);
    }
    Ok(DamageEvidenceV1 {
        cases,
        family_pass,
        boundary_pass: array(field(root, "boundary_kat_rows")?)?
            .iter()
            .all(|value| object(value).and_then(|row| text(field(row, "result")?)) == Ok("pass")),
    })
}

fn mul_mod(left: u64, right: u64, modulus: u64) -> Result<u64> {
    if modulus == 0 {
        return Err(IndependenceV1Error::Arithmetic);
    }
    Ok(((u128::from(left) * u128::from(right)) % u128::from(modulus)) as u64)
}

fn cell_forward(candidate: &CandidateEvidenceV1, logical: u64) -> Result<u64> {
    checked_add(
        mul_mod(candidate.cell_multiplier, logical, candidate.population)?,
        candidate.cell_offset,
    )
    .map(|value| value % candidate.population)
}

fn cell_inverse(candidate: &CandidateEvidenceV1, physical: u64) -> Result<u64> {
    let shifted = checked_add(physical, candidate.population)?
        .checked_sub(candidate.cell_offset)
        .ok_or(IndependenceV1Error::Arithmetic)?
        % candidate.population;
    mul_mod(
        candidate.cell_inverse_multiplier,
        shifted,
        candidate.population,
    )
}

fn shell_owner(candidate: &CandidateEvidenceV1, row: u64, column: u64) -> Result<(usize, u64)> {
    let last = candidate.side - 1;
    let width = candidate.width;
    let side = candidate.side;
    let (sector, u, v) = if row < width && column < side - width {
        (0, row, column)
    } else if column >= side - width && row < side - width {
        (1, last - column, row)
    } else if row >= side - width && column >= width {
        (2, last - row, last - column)
    } else if column < width && row >= width {
        (3, column, last - row)
    } else {
        return Err(IndependenceV1Error::Binding);
    };
    Ok((sector, checked_add(checked_mul(u, side - width)?, v)?))
}

fn final_cell_for_unit_bit(
    candidate: &CandidateEvidenceV1,
    unit: &UnitEvidenceV1,
    bit: u64,
) -> Result<u64> {
    cell_forward(candidate, checked_add(unit.logical_bit_first, bit)?)
}

fn candidate_section_types(candidate: &CandidateEvidenceV1) -> BTreeMap<u64, u64> {
    candidate
        .sections
        .iter()
        .map(|section| (section.section_id, section.section_type))
        .collect()
}

fn ledger_u64(candidate: &CandidateEvidenceV1, key: &str) -> Result<u64> {
    unsigned(field(&candidate.ledger, key)?)
}

fn group_slices(candidate: &CandidateEvidenceV1) -> Result<Vec<&[UnitEvidenceV1]>> {
    let mut groups = Vec::with_capacity(1_279);
    let mut offset = 0_usize;
    for section in &candidate.sections {
        for fragment in 0..section.fragment_count {
            let factor =
                usize::try_from(section.factor).map_err(|_| IndependenceV1Error::Arithmetic)?;
            let end = offset
                .checked_add(factor)
                .ok_or(IndependenceV1Error::Arithmetic)?;
            let group = candidate
                .units
                .get(offset..end)
                .ok_or(IndependenceV1Error::Binding)?;
            if group.iter().any(|unit| {
                unit.section_id != section.section_id || unit.fragment_index != fragment
            }) {
                return Err(IndependenceV1Error::Binding);
            }
            groups.push(group);
            offset = end;
        }
    }
    if offset != candidate.units.len() {
        return Err(IndependenceV1Error::Binding);
    }
    Ok(groups)
}

fn structural_violation_counts_v1(candidate: &CandidateEvidenceV1) -> Result<[u64; 9]> {
    let population =
        usize::try_from(candidate.population).map_err(|_| IndependenceV1Error::Arithmetic)?;
    let protected_cells = checked_mul(candidate.unit_population, 1_728)?;
    let mut targets = vec![u64::MAX; population];
    let mut target_counts = vec![0_u8; population];
    let mut round_trip_bad = vec![false; population];
    for (ordinal, unit) in candidate.units.iter().enumerate() {
        for bit in 0..1_728_u64 {
            let identity = checked_add(checked_mul(ordinal as u64, 1_728)?, bit)?;
            let physical = final_cell_for_unit_bit(candidate, unit, bit)?;
            let logical = cell_inverse(candidate, physical)?;
            let slot = logical / 1_728;
            let inverse_ordinal = mul_mod(
                candidate.unit_inverse_multiplier,
                slot,
                candidate.unit_population,
            )?;
            let bad = logical % 1_728 != bit
                || inverse_ordinal != ordinal as u64
                || cell_forward(candidate, logical)? != physical;
            let identity_index =
                usize::try_from(identity).map_err(|_| IndependenceV1Error::Arithmetic)?;
            let physical_index =
                usize::try_from(physical).map_err(|_| IndependenceV1Error::Arithmetic)?;
            targets[identity_index] = physical;
            target_counts[physical_index] = target_counts[physical_index].saturating_add(1);
            round_trip_bad[identity_index] = bad;
        }
    }
    for logical in protected_cells..candidate.population {
        let physical = cell_forward(candidate, logical)?;
        let index = usize::try_from(logical).map_err(|_| IndependenceV1Error::Arithmetic)?;
        let physical_index =
            usize::try_from(physical).map_err(|_| IndependenceV1Error::Arithmetic)?;
        targets[index] = physical;
        target_counts[physical_index] = target_counts[physical_index].saturating_add(1);
        round_trip_bad[index] = cell_inverse(candidate, physical)? != logical;
    }
    let mut row_one = 0_u64;
    for identity in 0..population {
        let target =
            usize::try_from(targets[identity]).map_err(|_| IndependenceV1Error::Arithmetic)?;
        if round_trip_bad[identity] || target_counts[target] != 1 {
            row_one = checked_add(row_one, 1)?;
        }
    }

    let section_types = candidate_section_types(candidate);
    let mut table = Sha256::new();
    let mut shell_sector_counts = [0_u64; 4];
    let mut class_counts = BTreeMap::from([
        ("shell-route", 0_u64),
        ("shell-headroom", 0),
        ("shell-fixed-pad", 0),
        ("real-protected", 0),
        ("capacity-probe", 0),
        ("reserve-probe", 0),
        ("load-probe", 0),
        ("interior-fixed-pad", 0),
    ]);
    let mut row_two = 0_u64;
    let mut pad_offset = 0_u64;
    for row in 0..candidate.side {
        for column in 0..candidate.side {
            let shell = row < candidate.width
                || row >= candidate.side - candidate.width
                || column < candidate.width
                || column >= candidate.side - candidate.width;
            let (kind, owner_id, owner_offset, class_id) = if shell {
                let (sector, local) = shell_owner(candidate, row, column)?;
                shell_sector_counts[sector] = checked_add(shell_sector_counts[sector], 1)?;
                let shell = &candidate.shell[sector];
                if local < shell.route_prefix_cells {
                    (1_u8, sector as u64, local, "shell-route")
                } else if local < shell.route_prefix_cells + shell.headroom_cells {
                    (
                        2,
                        sector as u64,
                        local - shell.route_prefix_cells,
                        "shell-headroom",
                    )
                } else {
                    (
                        3,
                        sector as u64,
                        local - shell.route_prefix_cells - shell.headroom_cells,
                        "shell-fixed-pad",
                    )
                }
            } else {
                let interior = checked_add(
                    checked_mul(row - candidate.width, candidate.interior_side)?,
                    column - candidate.width,
                )?;
                let physical_index =
                    usize::try_from(interior).map_err(|_| IndependenceV1Error::Arithmetic)?;
                if target_counts[physical_index] != 1 {
                    row_two = checked_add(row_two, 1)?;
                }
                let logical = cell_inverse(candidate, interior)?;
                if logical < protected_cells {
                    let slot = logical / 1_728;
                    let ordinal = mul_mod(
                        candidate.unit_inverse_multiplier,
                        slot,
                        candidate.unit_population,
                    )?;
                    let unit = candidate
                        .units
                        .get(
                            usize::try_from(ordinal)
                                .map_err(|_| IndependenceV1Error::Arithmetic)?,
                        )
                        .ok_or(IndependenceV1Error::Binding)?;
                    let class = match *section_types
                        .get(&unit.section_id)
                        .ok_or(IndependenceV1Error::Binding)?
                    {
                        1..=3 => "real-protected",
                        4 => "capacity-probe",
                        5 => "reserve-probe",
                        6 => "load-probe",
                        _ => return Err(IndependenceV1Error::Binding),
                    };
                    (4, unit.physical_unit_id, logical % 1_728, class)
                } else {
                    let observed = pad_offset;
                    pad_offset = checked_add(pad_offset, 1)?;
                    (5, 0, observed, "interior-fixed-pad")
                }
            };
            *class_counts
                .get_mut(class_id)
                .ok_or(IndependenceV1Error::Binding)? = checked_add(class_counts[class_id], 1)?;
            let owner_id = u32::try_from(owner_id).map_err(|_| IndependenceV1Error::Arithmetic)?;
            let owner_offset =
                u32::try_from(owner_offset).map_err(|_| IndependenceV1Error::Arithmetic)?;
            table.update([kind]);
            table.update(owner_id.to_be_bytes());
            table.update(owner_offset.to_be_bytes());
        }
    }
    if pad_offset != candidate.population - protected_cells {
        row_two = checked_add(row_two, 1)?;
    }
    if format!("{:x}", table.finalize()) != candidate.ownership_cell_table_sha256 {
        row_two = checked_add(row_two, 1)?;
    }
    let sector_cells = checked_mul(candidate.width, candidate.side - candidate.width)?;
    let mut row_three = 0_u64;
    for (ordinal, count) in shell_sector_counts.into_iter().enumerate() {
        let shell = &candidate.shell[ordinal];
        if count != sector_cells
            || shell.route_prefix_cells + shell.headroom_cells + shell.fixed_pad_cells
                != sector_cells
        {
            row_three = checked_add(row_three, 1)?;
        }
    }
    if checked_mul(sector_cells, 4)? != candidate.side * candidate.side - candidate.population {
        row_three = checked_add(row_three, 1)?;
    }

    let mut row_four = 0_u64;
    let mut row_six = 0_u64;
    let mut malformed_groups = 0_u64;
    let mut factor_aggregates = BTreeMap::<u64, (u64, u64, u64)>::new();
    let groups = group_slices(candidate)?;
    let mut prior_physical = 0_u64;
    for group in &groups {
        let first = group.first().ok_or(IndependenceV1Error::Binding)?;
        let section = candidate
            .sections
            .iter()
            .find(|section| section.section_id == first.section_id)
            .ok_or(IndependenceV1Error::Binding)?;
        let expected_class = if [1, 2, 3, 16].contains(&section.section_id) {
            "required-spine"
        } else if section.factor == 2 {
            "replicated-m2"
        } else {
            "nonreplicated-m2"
        };
        let factor_owner_bad = section.factor as usize != group.len()
            || section.copy_class != expected_class
            || group.iter().any(|unit| unit.factor != section.factor);
        let contiguous_bad = group.iter().enumerate().any(|(index, unit)| {
            unit.physical_unit_id != prior_physical + index as u64 + 1
                || unit.replica_index != index as u64
        });
        let mut slots = BTreeSet::new();
        let distinct_slots_bad = group.iter().any(|unit| !slots.insert(unit.slot));
        let span_bad = group.iter().any(|unit| {
            unit.logical_bit_first != unit.slot.saturating_mul(1_728)
                || unit.slot >= candidate.unit_population
                || unit.slot
                    != (candidate.unit_multiplier * (unit.physical_unit_id.saturating_sub(1)))
                        % candidate.unit_population
        });
        let mut cells = BTreeSet::new();
        let mut cell_sets_bad = false;
        for unit in *group {
            let mut mapped = Vec::with_capacity(1_728 * 4);
            let mut lane_cells = BTreeSet::new();
            for bit in 0..1_728_u64 {
                let physical = final_cell_for_unit_bit(candidate, unit, bit)?;
                let physical_u32 =
                    u32::try_from(physical).map_err(|_| IndependenceV1Error::Arithmetic)?;
                mapped.extend_from_slice(&physical_u32.to_be_bytes());
                if !lane_cells.insert(physical) || !cells.insert(physical) {
                    cell_sets_bad = true;
                }
            }
            if digest(&mapped) != unit.mapped_cell_sha256 {
                cell_sets_bad = true;
            }
        }
        for bad in [
            factor_owner_bad,
            contiguous_bad,
            distinct_slots_bad,
            span_bad,
            cell_sets_bad,
        ] {
            if bad {
                row_four = checked_add(row_four, 1)?;
            }
        }
        if factor_owner_bad || contiguous_bad || distinct_slots_bad || span_bad || cell_sets_bad {
            malformed_groups = checked_add(malformed_groups, 1)?;
        }
        let aggregate = factor_aggregates.entry(section.factor).or_insert((0, 0, 0));
        aggregate.0 = checked_add(aggregate.0, 1)?;
        aggregate.1 = checked_add(aggregate.1, group.len() as u64)?;
        aggregate.2 = checked_add(aggregate.2, checked_mul(group.len() as u64, 1_728)?)?;
        if section.factor > 1 {
            let window = 32_u64.max(candidate.interior_side / 8);
            for left in 0..group.len() {
                for right in left + 1..group.len() {
                    for bit in 0..1_728_u64 {
                        let first = final_cell_for_unit_bit(candidate, &group[left], bit)?;
                        let second = final_cell_for_unit_bit(candidate, &group[right], bit)?;
                        let first_row = first / candidate.interior_side;
                        let first_column = first % candidate.interior_side;
                        let second_row = second / candidate.interior_side;
                        let second_column = second % candidate.interior_side;
                        if first_row
                            .abs_diff(second_row)
                            .max(first_column.abs_diff(second_column))
                            < window
                        {
                            row_six = checked_add(row_six, 1)?;
                        }
                    }
                }
            }
        }
        prior_physical = group.last().unwrap().physical_unit_id;
    }

    let expected_classes = BTreeMap::from([
        (
            "shell-route",
            checked_add(
                checked_add(
                    ledger_u64(candidate, "shell_instruction_cells")?,
                    ledger_u64(candidate, "shell_example_cells")?,
                )?,
                ledger_u64(candidate, "shell_recipe_cells")?,
            )?,
        ),
        (
            "shell-headroom",
            ledger_u64(candidate, "shell_headroom_cells")?,
        ),
        (
            "shell-fixed-pad",
            ledger_u64(candidate, "shell_fixed_pad_cells")?,
        ),
        (
            "real-protected",
            ledger_u64(candidate, "real_protected_cells")?,
        ),
        (
            "capacity-probe",
            ledger_u64(candidate, "capacity_probe_cells")?,
        ),
        (
            "reserve-probe",
            ledger_u64(candidate, "reserve_probe_cells")?,
        ),
        ("load-probe", ledger_u64(candidate, "load_probe_cells")?),
        (
            "interior-fixed-pad",
            ledger_u64(candidate, "interior_fixed_pad_cells")?,
        ),
    ]);
    let mut row_five = 0_u64;
    for (class, expected) in &expected_classes {
        if class_counts.get(class).copied() != Some(*expected) {
            row_five = checked_add(row_five, 1)?;
        }
    }
    let class_sum = class_counts
        .values()
        .try_fold(0_u64, |sum, value| checked_add(sum, *value))?;
    if class_sum != checked_mul(candidate.side, candidate.side)? {
        row_five = checked_add(row_five, 1)?;
    }
    for (factor, expected) in [
        (1_u64, (807, 807, 1_394_496)),
        (2, (442, 884, 1_527_552)),
        (5, (30, 150, 259_200)),
    ] {
        if factor_aggregates.get(&factor).copied().unwrap_or_default() != expected {
            row_five = checked_add(row_five, 1)?;
        }
    }

    let section_ids = candidate
        .sections
        .iter()
        .map(|section| section.section_id)
        .collect::<BTreeSet<_>>();
    let mut row_eight = malformed_groups;
    for section in &candidate.sections {
        for dependency in &section.dependencies {
            if !section_ids.contains(dependency) {
                row_eight = checked_add(row_eight, 1)?;
            }
        }
    }
    for removed in 0..4 {
        let survivors = candidate
            .shell
            .iter()
            .enumerate()
            .filter(|(ordinal, shell)| *ordinal != removed && shell.route_prefix_cells > 0)
            .count();
        if survivors != 3 {
            row_eight = checked_add(row_eight, 1)?;
        }
    }
    let group_units = factor_aggregates
        .values()
        .try_fold(0_u64, |sum, value| checked_add(sum, value.1))?;
    let ledger_closes = groups.len() as u64 == 1_279
        && group_units == candidate.unit_population
        && checked_add(protected_cells, candidate.population - protected_cells)?
            == candidate.population
        && class_sum == checked_mul(candidate.side, candidate.side)?;
    if !ledger_closes {
        row_eight = checked_add(row_eight, 1)?;
    }
    Ok([
        row_one, row_two, row_three, row_four, row_five, row_six, 0, row_eight, 0,
    ])
}

fn case_parameter<'a>(case: &'a ManifestValue, id: &str) -> Result<&'a ManifestValue> {
    let case = object(case)?;
    for value in array(field(case, "parameter_projection")?)? {
        let row = object(value)?;
        if text(field(row, "id")?)? == id {
            return field(row, "value");
        }
    }
    Err(IndependenceV1Error::Binding)
}

fn square_contains(row: u64, column: u64, top: u64, left: u64, side: u64) -> bool {
    row >= top
        && row < top.saturating_add(side)
        && column >= left
        && column < left.saturating_add(side)
}

fn group_survives_square_v1(
    candidate: &CandidateEvidenceV1,
    group: &[UnitEvidenceV1],
    top: u64,
    left: u64,
    side: u64,
) -> Result<bool> {
    let mut lane_erasures = vec![[0_u8; 24]; group.len()];
    let mut repetition_erasures = [0_u8; 24];
    for bit in 0..1_728_u64 {
        let mut erased_count = 0_usize;
        for (lane, unit) in group.iter().enumerate() {
            let physical = final_cell_for_unit_bit(candidate, unit, bit)?;
            let row = physical / candidate.interior_side + candidate.width;
            let column = physical % candidate.interior_side + candidate.width;
            if square_contains(row, column, top, left, side) {
                let codeword =
                    usize::try_from(bit / 72).map_err(|_| IndependenceV1Error::Arithmetic)?;
                lane_erasures[lane][codeword] = lane_erasures[lane][codeword].saturating_add(1);
                erased_count += 1;
            }
        }
        if erased_count == group.len() {
            let codeword =
                usize::try_from(bit / 72).map_err(|_| IndependenceV1Error::Arithmetic)?;
            repetition_erasures[codeword] = repetition_erasures[codeword].saturating_add(1);
        }
    }
    Ok(lane_erasures
        .iter()
        .any(|counts| counts.iter().all(|count| *count <= 3))
        || repetition_erasures.iter().all(|count| *count <= 3))
}

fn required_closure_violation_count_v1(
    candidate: &CandidateEvidenceV1,
    damage: &DamageEvidenceV1,
) -> Result<u64> {
    let required = candidate
        .sections
        .iter()
        .filter(|section| section.closure_class == 128)
        .map(|section| section.section_id)
        .collect::<Vec<_>>();
    if required != [1, 2, 3, 16] {
        return Err(IndependenceV1Error::Binding);
    }
    let groups = group_slices(candidate)?;
    let mut groups_by_section = BTreeMap::<u64, Vec<&[UnitEvidenceV1]>>::new();
    for group in groups {
        groups_by_section
            .entry(group[0].section_id)
            .or_default()
            .push(group);
    }
    let mut violations = 0_u64;
    for family in [2_usize, 4, 6] {
        for case in &damage.cases[family] {
            for section_id in &required {
                let survives = match family {
                    2 => {
                        let square_side = unsigned(case_parameter(case, "side")?)?;
                        let coordinates = array(case_parameter(case, "top_left")?)?;
                        if coordinates.len() != 1 {
                            return Err(IndependenceV1Error::Binding);
                        }
                        let coordinate = array(&coordinates[0])?;
                        if coordinate.len() != 2 {
                            return Err(IndependenceV1Error::Binding);
                        }
                        let top = unsigned(&coordinate[0])?;
                        let left = unsigned(&coordinate[1])?;
                        let mut section_survives = true;
                        for group in groups_by_section
                            .get(section_id)
                            .ok_or(IndependenceV1Error::Binding)?
                        {
                            if !group_survives_square_v1(candidate, group, top, left, square_side)?
                            {
                                section_survives = false;
                                break;
                            }
                        }
                        section_survives
                    }
                    4 | 6 => {
                        let omitted = unsigned(case_parameter(
                            case,
                            if family == 4 {
                                "omitted_unit_id"
                            } else {
                                "unit_id"
                            },
                        )?)?;
                        groups_by_section
                            .get(section_id)
                            .ok_or(IndependenceV1Error::Binding)?
                            .iter()
                            .all(|group| {
                                group
                                    .iter()
                                    .filter(|unit| unit.physical_unit_id != omitted)
                                    .count()
                                    >= 1
                            })
                    }
                    _ => unreachable!(),
                };
                if !survives {
                    violations = checked_add(violations, 1)?;
                }
            }
        }
    }
    Ok(violations)
}

fn expected_states(case: &ManifestValue) -> Result<BTreeMap<u64, &str>> {
    let case = object(case)?;
    array(field(case, "expected_section_states")?)?
        .iter()
        .map(|value| {
            let row = object(value)?;
            Ok((
                unsigned(field(row, "section_id")?)?,
                text(field(row, "state")?)?,
            ))
        })
        .collect()
}

fn damage_promise_violation_count_v1(
    candidate: &CandidateEvidenceV1,
    damage: &DamageEvidenceV1,
) -> Result<u64> {
    let required = candidate
        .sections
        .iter()
        .filter(|section| section.closure_class == 128)
        .map(|section| section.section_id)
        .collect::<BTreeSet<_>>();
    let declared = candidate
        .sections
        .iter()
        .map(|section| section.section_id)
        .collect::<BTreeSet<_>>();
    let exact = |state: &&str| matches!(*state, "verified" | "recovered");
    let mut violations = 0_u64;
    for family in 0..8 {
        let family_pass = damage.family_pass[family] && (family != 7 || damage.boundary_pass);
        for case in &damage.cases[family] {
            let case_row = object(case)?;
            let states = expected_states(case)?;
            let guarantee = match family {
                0 | 1 | 5 => {
                    text(field(case_row, "expected_artifact_state")?)? == "exact"
                        && states.keys().copied().collect::<BTreeSet<_>>() == declared
                        && states.values().all(exact)
                }
                2 | 3 | 4 | 6 => required
                    .iter()
                    .all(|section_id| states.get(section_id).is_some_and(exact)),
                7 => true,
                _ => unreachable!(),
            };
            if !family_pass || unsigned(field(case_row, "wrong_accept_count")?)? != 0 || !guarantee
            {
                violations = checked_add(violations, 1)?;
            }
        }
    }
    Ok(violations)
}

/// Strictly admit all raw gate-6 evidence, independently enumerate all nine
/// frozen predicates, and render the canonical v1 proof. No artifact is read
/// other than the supplied byte strings, and no file is written.
pub fn build_independence_proof_from_bundle_v1(
    candidate_manifest_raw: &[u8],
    ownership_ledger_raw: &[u8],
    damage_manifest_raw: &[u8],
    family_manifest_raws: &[&[u8]],
    case_shard_raws: &[&[u8]],
) -> Result<IndependenceProofV1> {
    let candidate = candidate_evidence_v1(candidate_manifest_raw, ownership_ledger_raw)?;
    let damage = damage_evidence_v1(
        damage_manifest_raw,
        family_manifest_raws,
        case_shard_raws,
        candidate_manifest_raw,
        &candidate,
    )?;
    let mut violations = structural_violation_counts_v1(&candidate)?;
    violations[6] = required_closure_violation_count_v1(&candidate, &damage)?;
    violations[8] = damage_promise_violation_count_v1(&candidate, &damage)?;
    let rows = proof_rows_from_violation_counts_v1(violations)?;
    render_independence_proof_v1(
        candidate_manifest_raw,
        ownership_ledger_raw,
        damage_manifest_raw,
        &rows,
    )
}

fn row_manifest(row: &ProofPredicateRowV1) -> ManifestValue {
    manifest_object([
        ("predicate_id", manifest_string(row.predicate_id)),
        ("witness_count", ManifestValue::U64(row.witness_count)),
        (
            "minimum_surviving_count",
            ManifestValue::U64(row.minimum_surviving_count),
        ),
        ("violation_count", ManifestValue::U64(row.violation_count)),
        (
            "result",
            manifest_string(if row.passed { "pass" } else { "fail" }),
        ),
    ])
}

fn validate_rows(rows: &[ProofPredicateRowV1]) -> Result<bool> {
    if rows.len() != PROOF_PREDICATE_IDS_V1.len() {
        return Err(IndependenceV1Error::Manifest);
    }
    for (ordinal, row) in rows.iter().enumerate() {
        if row.predicate_id != PROOF_PREDICATE_IDS_V1[ordinal]
            || row.witness_count != PROOF_WITNESS_COUNTS_V1[ordinal]
            || row.minimum_surviving_count != 1
            || row.passed != (row.violation_count == 0)
        {
            return Err(IndependenceV1Error::Manifest);
        }
    }
    Ok(rows.iter().all(|row| row.passed))
}

pub fn render_independence_proof_v1(
    candidate_manifest_raw: &[u8],
    ownership_ledger_raw: &[u8],
    damage_manifest_raw: &[u8],
    predicate_rows: &[ProofPredicateRowV1],
) -> Result<IndependenceProofV1> {
    derive_proof_witness_counts_v1(candidate_manifest_raw, ownership_ledger_raw)?;
    admit_damage_root(damage_manifest_raw, &digest(candidate_manifest_raw))?;
    let passed = validate_rows(predicate_rows)?;
    let candidate_sha256 = digest(candidate_manifest_raw);
    let ownership_sha256 = digest(ownership_ledger_raw);
    let damage_sha256 = digest(damage_manifest_raw);
    let rows = predicate_rows.iter().map(row_manifest).collect::<Vec<_>>();
    let without_identity = manifest_object([
        (
            "schema",
            manifest_string("golden-board.m2-independence-proof/v1"),
        ),
        ("profile_id", manifest_string(PROFILE_ID_V1)),
        (
            "candidate_manifest_sha256",
            manifest_string(&candidate_sha256),
        ),
        (
            "ownership_ledger_sha256",
            manifest_string(&ownership_sha256),
        ),
        ("damage_manifest_sha256", manifest_string(&damage_sha256)),
        ("predicate_rows", ManifestValue::Array(rows.clone())),
        (
            "summary",
            manifest_object([
                ("predicate_count", ManifestValue::U64(9)),
                (
                    "result",
                    manifest_string(if passed { "pass" } else { "fail" }),
                ),
            ]),
        ),
    ]);
    let without_identity_raw =
        serialize_manifest(&without_identity).map_err(|_| IndependenceV1Error::Manifest)?;
    let manifest_identity = identity_hex(IDENTITY_DOMAIN, &[&without_identity_raw])
        .map_err(|_| IndependenceV1Error::Manifest)?;
    let value = manifest_object([
        (
            "schema",
            manifest_string("golden-board.m2-independence-proof/v1"),
        ),
        ("profile_id", manifest_string(PROFILE_ID_V1)),
        (
            "candidate_manifest_sha256",
            manifest_string(&candidate_sha256),
        ),
        (
            "ownership_ledger_sha256",
            manifest_string(&ownership_sha256),
        ),
        ("damage_manifest_sha256", manifest_string(&damage_sha256)),
        ("predicate_rows", ManifestValue::Array(rows)),
        (
            "summary",
            manifest_object([
                ("predicate_count", ManifestValue::U64(9)),
                (
                    "result",
                    manifest_string(if passed { "pass" } else { "fail" }),
                ),
                ("manifest_identity", manifest_string(&manifest_identity)),
            ]),
        ),
    ]);
    let canonical_bytes = serialize_manifest(&value).map_err(|_| IndependenceV1Error::Manifest)?;
    Ok(IndependenceProofV1 {
        canonical_bytes,
        manifest_identity,
        passed,
        predicate_rows: predicate_rows.to_vec(),
    })
}

pub fn parse_independence_proof_v1(raw: &[u8]) -> Result<IndependenceProofV1> {
    let value = validate_canonical_manifest(raw).map_err(|_| IndependenceV1Error::Manifest)?;
    let root = object(&value)?;
    if !exact_keys(
        root,
        &[
            "schema",
            "profile_id",
            "candidate_manifest_sha256",
            "ownership_ledger_sha256",
            "damage_manifest_sha256",
            "predicate_rows",
            "summary",
        ],
    ) || text(field(root, "schema")?)? != "golden-board.m2-independence-proof/v1"
        || text(field(root, "profile_id")?)? != PROFILE_ID_V1
    {
        return Err(IndependenceV1Error::Manifest);
    }
    for key in [
        "candidate_manifest_sha256",
        "ownership_ledger_sha256",
        "damage_manifest_sha256",
    ] {
        if !lower_sha256(text(field(root, key)?)?) {
            return Err(IndependenceV1Error::Manifest);
        }
    }
    let raw_rows = array(field(root, "predicate_rows")?)?;
    let mut predicate_rows = Vec::with_capacity(raw_rows.len());
    for (ordinal, raw_row) in raw_rows.iter().enumerate() {
        let row = object(raw_row)?;
        if ordinal >= PROOF_PREDICATE_IDS_V1.len()
            || !exact_keys(
                row,
                &[
                    "predicate_id",
                    "witness_count",
                    "minimum_surviving_count",
                    "violation_count",
                    "result",
                ],
            )
        {
            return Err(IndependenceV1Error::Manifest);
        }
        let predicate_id = text(field(row, "predicate_id")?)?;
        let expected_id = PROOF_PREDICATE_IDS_V1[ordinal];
        if predicate_id != expected_id {
            return Err(IndependenceV1Error::Manifest);
        }
        let witness_count = unsigned(field(row, "witness_count")?)?;
        let minimum_surviving_count = unsigned(field(row, "minimum_surviving_count")?)?;
        let violation_count = unsigned(field(row, "violation_count")?)?;
        let passed = text(field(row, "result")?)? == "pass";
        if !matches!(text(field(row, "result")?)?, "pass" | "fail") {
            return Err(IndependenceV1Error::Manifest);
        }
        predicate_rows.push(ProofPredicateRowV1 {
            predicate_id: expected_id,
            witness_count,
            minimum_surviving_count,
            violation_count,
            passed,
        });
    }
    let passed = validate_rows(&predicate_rows)?;
    let summary = object(field(root, "summary")?)?;
    if !exact_keys(summary, &["predicate_count", "result", "manifest_identity"])
        || unsigned(field(summary, "predicate_count")?)? != 9
        || text(field(summary, "result")?)? != if passed { "pass" } else { "fail" }
        || !lower_sha256(text(field(summary, "manifest_identity")?)?)
    {
        return Err(IndependenceV1Error::Manifest);
    }
    let manifest_identity = nested_manifest_identity(&value)?;
    if text(field(summary, "manifest_identity")?)? != manifest_identity {
        return Err(IndependenceV1Error::Binding);
    }
    Ok(IndependenceProofV1 {
        canonical_bytes: raw.to_vec(),
        manifest_identity,
        passed,
        predicate_rows,
    })
}

pub fn admit_independence_proof_v1(
    proof_raw: &[u8],
    candidate_manifest_raw: &[u8],
    ownership_ledger_raw: &[u8],
    damage_manifest_raw: &[u8],
    predicate_rows: &[ProofPredicateRowV1],
) -> Result<IndependenceProofV1> {
    let parsed = parse_independence_proof_v1(proof_raw)?;
    let expected = render_independence_proof_v1(
        candidate_manifest_raw,
        ownership_ledger_raw,
        damage_manifest_raw,
        predicate_rows,
    )?;
    if parsed != expected {
        return Err(IndependenceV1Error::Binding);
    }
    Ok(parsed)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parameter(
        id: &'static str,
        value_type: &'static str,
        value: ManifestValue,
    ) -> ManifestValue {
        manifest_object([
            ("id", manifest_string(id)),
            ("value_type", manifest_string(value_type)),
            ("value", value),
        ])
    }

    fn d7_parameters(ordinal: u64) -> Vec<ManifestValue> {
        match ordinal {
            0..=2 => vec![parameter(
                "mutant_ordinal",
                "u64",
                ManifestValue::U64(ordinal),
            )],
            3..=4 => vec![
                parameter("case_ordinal", "u64", ManifestValue::U64(ordinal - 3)),
                parameter(
                    "target_unit_ids",
                    "u64-list",
                    ManifestValue::Array((1..=5).map(ManifestValue::U64).collect()),
                ),
            ],
            5..=6 => vec![
                parameter("case_ordinal", "u64", ManifestValue::U64(ordinal - 3)),
                parameter("section_id", "u64", ManifestValue::U64(2)),
            ],
            7..=9 => vec![
                parameter("case_ordinal", "u64", ManifestValue::U64(ordinal - 7)),
                parameter(
                    "target_unit_ids",
                    "u64-list",
                    ManifestValue::Array((1..=5).map(ManifestValue::U64).collect()),
                ),
            ],
            10 => vec![parameter(
                "alternate_profile_version",
                "u64",
                ManifestValue::U64(3),
            )],
            11..=15 => vec![
                parameter(
                    "source_profile_version",
                    "u64",
                    ManifestValue::U64(ordinal - 9),
                ),
                parameter(
                    "target_unit_ids",
                    "u64-list",
                    ManifestValue::Array((1..=5).map(ManifestValue::U64).collect()),
                ),
            ],
            16 => vec![
                parameter("section_id", "u64", ManifestValue::U64(1)),
                parameter("target_unit_id", "u64", ManifestValue::U64(1)),
            ],
            17..=272 => vec![
                parameter("d2_ordinal", "u64", ManifestValue::U64(ordinal - 17)),
                parameter("side", "u64", ManifestValue::U64(56)),
            ],
            273..=400 => vec![parameter(
                "seed",
                "u64",
                ManifestValue::U64(5_134_751_402_299_490_304 + ordinal - 273),
            )],
            401 => vec![parameter(
                "omitted_unit_ids",
                "u64-list",
                ManifestValue::Array((1..=5).map(ManifestValue::U64).collect()),
            )],
            402..=404 => vec![
                parameter(
                    "erasures",
                    "u64",
                    ManifestValue::U64([(0, 2), (2, 1), (4, 0)][ordinal as usize - 402].0),
                ),
                parameter(
                    "errors",
                    "u64",
                    ManifestValue::U64([(0, 2), (2, 1), (4, 0)][ordinal as usize - 402].1),
                ),
                parameter(
                    "target_unit_ids",
                    "u64-list",
                    ManifestValue::Array((1..=5).map(ManifestValue::U64).collect()),
                ),
            ],
            405..=406 => vec![parameter(
                "declared_value",
                "u64",
                ManifestValue::U64(if ordinal == 405 {
                    268_435_457
                } else {
                    16_777_217
                }),
            )],
            407 => vec![parameter("side", "u64", ManifestValue::U64(2_056))],
            _ => unreachable!(),
        }
    }

    fn coordinate_value(coordinates: Vec<[u64; 2]>) -> ManifestValue {
        ManifestValue::Array(
            coordinates
                .into_iter()
                .map(|[row, column]| {
                    ManifestValue::Array(vec![ManifestValue::U64(row), ManifestValue::U64(column)])
                })
                .collect(),
        )
    }

    fn synthetic_case(
        family: usize,
        ordinal: u64,
        candidate: &CandidateEvidenceV1,
        d2: &[[u64; 2]],
        d3_population_cache: &mut BTreeMap<u64, Vec<u64>>,
    ) -> ManifestValue {
        let (_, operator, _) = expected_case_shape_v1(family, ordinal).unwrap();
        let parameters = match family {
            0 => vec![
                parameter("polarity_id", "u64", ManifestValue::U64(ordinal % 2)),
                parameter("transform_id", "u64", ManifestValue::U64(ordinal / 2)),
            ],
            1 => vec![parameter("sector_id", "u64", ManifestValue::U64(ordinal))],
            2 => vec![
                parameter("side", "u64", ManifestValue::U64(55)),
                parameter(
                    "top_left",
                    "coordinate-list",
                    coordinate_value(vec![d2[ordinal as usize]]),
                ),
            ],
            3 => vec![
                parameter(
                    "coordinates",
                    "coordinate-list",
                    coordinate_value(
                        exact_d3_coordinates_v1(candidate, ordinal, d3_population_cache).unwrap(),
                    ),
                ),
                parameter(
                    "seed",
                    "u64",
                    ManifestValue::U64(5_134_751_402_299_490_304 + ordinal),
                ),
                parameter("stratum_id", "u64", ManifestValue::U64(ordinal / 32)),
            ],
            4 => vec![parameter(
                "omitted_unit_id",
                "u64",
                ManifestValue::U64(ordinal + 1),
            )],
            5 => vec![parameter(
                "permutation_ordinal",
                "u64",
                ManifestValue::U64(ordinal),
            )],
            6 => vec![
                parameter("sector_id", "u64", ManifestValue::U64(ordinal / 1_841)),
                parameter("unit_id", "u64", ManifestValue::U64(ordinal % 1_841 + 1)),
            ],
            7 => d7_parameters(ordinal),
            _ => unreachable!(),
        };
        manifest_object([
            (
                "case_id",
                manifest_string(&format!("{}-{ordinal:06}", FAMILY_IDS[family])),
            ),
            ("family_id", manifest_string(FAMILY_IDS[family])),
            (
                "channel",
                manifest_string(expected_case_shape_v1(family, ordinal).unwrap().0),
            ),
            ("operator", manifest_string(operator)),
            ("parameter_projection", ManifestValue::Array(parameters)),
            ("observation_sha256", manifest_string(&"0".repeat(64))),
            ("decoder_result_sha256", manifest_string(&"1".repeat(64))),
            (
                "expected_artifact_state",
                manifest_string(if family == 7 { "failure" } else { "exact" }),
            ),
            (
                "expected_section_states",
                ManifestValue::Array(
                    candidate
                        .sections
                        .iter()
                        .map(|section| section.section_id)
                        .map(|section_id| {
                            manifest_object([
                                ("section_id", ManifestValue::U64(section_id)),
                                ("state", manifest_string("verified")),
                            ])
                        })
                        .collect(),
                ),
            ),
            ("wrong_accept_count", ManifestValue::U64(0)),
        ])
    }

    fn finalize_nested(mut value: ManifestValue) -> Vec<u8> {
        let raw = serialize_manifest(&value).unwrap();
        let manifest_identity = identity_hex(IDENTITY_DOMAIN, &[&raw]).unwrap();
        let root = object_mut(&mut value).unwrap();
        let summary = object_mut(root.get_mut("summary").unwrap()).unwrap();
        summary.insert(
            "manifest_identity".to_owned(),
            manifest_string(&manifest_identity),
        );
        serialize_manifest(&value).unwrap()
    }

    fn regenerated_candidate_artifacts() -> (Vec<u8>, Vec<u8>) {
        let gates = crate::gate8_v1::regenerate_current_r3_gates_one_through_five().unwrap();
        (
            gates.artifacts.candidate_manifest,
            gates.artifacts.ownership_ledger,
        )
    }

    fn synthetic_damage_bundle(
        candidate_raw: &[u8],
        ownership_raw: &[u8],
    ) -> (Vec<u8>, Vec<Vec<u8>>, Vec<Vec<u8>>) {
        let candidate = candidate_evidence_v1(candidate_raw, ownership_raw).unwrap();
        let d2 = exact_d2_placements_v1(&candidate).unwrap();
        let mut d3_population_cache = BTreeMap::new();
        let cases: [Vec<ManifestValue>; 8] = std::array::from_fn(|family| {
            (0..FAMILY_COUNTS[family])
                .map(|ordinal| {
                    synthetic_case(family, ordinal, &candidate, &d2, &mut d3_population_cache)
                })
                .collect()
        });
        let family_rows = (0..8)
            .map(|family| {
                manifest_object([
                    ("family_id", manifest_string(FAMILY_IDS[family])),
                    ("case_count", ManifestValue::U64(FAMILY_COUNTS[family])),
                    ("wrong_accept_count", ManifestValue::U64(0)),
                    ("result", manifest_string("pass")),
                    (
                        "case_rows_sha256",
                        manifest_string(&canonical_case_rows_sha256(&cases[family]).unwrap()),
                    ),
                ])
            })
            .collect::<Vec<_>>();
        let boundary_rows = BOUNDARY_IDS
            .iter()
            .zip(BOUNDARY_RESULT_SHA256)
            .map(|(kat_id, sha256)| {
                manifest_object([
                    ("kat_id", manifest_string(kat_id)),
                    ("result_sha256", manifest_string(sha256)),
                    ("result", manifest_string("pass")),
                ])
            })
            .collect::<Vec<_>>();
        let root_without_identity = manifest_object([
            (
                "schema",
                manifest_string("golden-board.m2-damage-manifest/v1"),
            ),
            (
                "damage_policy_sha256",
                manifest_string(&owner_sha256(include_bytes!(
                    "../../../spec/damage-policy-v1.toml"
                ))),
            ),
            (
                "profile_policy_sha256",
                manifest_string(&owner_sha256(include_bytes!(
                    "../../../spec/profile-policy-v1.toml"
                ))),
            ),
            (
                "profile_limits_sha256",
                manifest_string(&owner_sha256(include_bytes!(
                    "../../../spec/profile-limits-v1.toml"
                ))),
            ),
            (
                "bootstrap_spec_sha256",
                manifest_string(&owner_sha256(include_bytes!(
                    "../../../spec/bootstrap-v1.md"
                ))),
            ),
            (
                "route_data_sha256",
                manifest_string(&owner_sha256(include_bytes!(
                    "../../../spec/route-data-v1.json"
                ))),
            ),
            (
                "recipient_package_sha256",
                manifest_string(RECIPIENT_PACKAGE_SHA256),
            ),
            ("profile_id", manifest_string(PROFILE_ID_V1)),
            (
                "candidate_manifest_sha256",
                manifest_string(&digest(candidate_raw)),
            ),
            ("clean_observation_sha256", manifest_string(&"2".repeat(64))),
            ("family_rows", ManifestValue::Array(family_rows)),
            ("boundary_kat_rows", ManifestValue::Array(boundary_rows)),
            (
                "summary",
                manifest_object([
                    (
                        "family_case_counts",
                        ManifestValue::Array(
                            (0..8)
                                .map(|family| {
                                    manifest_object([
                                        ("family_id", manifest_string(FAMILY_IDS[family])),
                                        ("case_count", ManifestValue::U64(FAMILY_COUNTS[family])),
                                    ])
                                })
                                .collect(),
                        ),
                    ),
                    ("wrong_accept_count", ManifestValue::U64(0)),
                ]),
            ),
        ]);
        let root = finalize_nested(root_without_identity);
        let root_value = validate_canonical_manifest(&root).unwrap();
        let root_identity = text(
            field(
                object(field(object(&root_value).unwrap(), "summary").unwrap()).unwrap(),
                "manifest_identity",
            )
            .unwrap(),
        )
        .unwrap()
        .to_owned();
        let guarantees = [
            "all_declared_m2_sections_exact",
            "all_declared_m2_sections_exact",
            "m2_required_closure",
            "m2_required_closure",
            "m2_required_closure",
            "all_declared_m2_sections_exact",
            "m2_required_closure",
            "correct_or_explicit_failure",
        ];
        let mut family_raws = Vec::new();
        let mut shard_raws = Vec::new();
        for family in 0..8 {
            let mut references = Vec::new();
            let mut case_first = 0_usize;
            let mut ordinal = 0_u64;
            while case_first < cases[family].len() {
                let mut low = 1_usize;
                let mut high = 256.min(cases[family].len() - case_first);
                let mut best = None;
                while low <= high {
                    let count = low + (high - low) / 2;
                    match render_case_shard_v1(
                        &root_identity,
                        FAMILY_IDS[family],
                        ordinal,
                        case_first as u64,
                        &cases[family][case_first..case_first + count],
                    ) {
                        Ok(raw) if raw.len() <= 1_048_576 => {
                            best = Some((count, raw));
                            low = count + 1;
                        }
                        _ => high = count - 1,
                    }
                }
                let (count, shard) = best.unwrap();
                references.push(manifest_object([
                    ("shard_ordinal", ManifestValue::U64(ordinal)),
                    ("case_first", ManifestValue::U64(case_first as u64)),
                    ("case_count", ManifestValue::U64(count as u64)),
                    ("manifest_sha256", manifest_string(&digest(&shard))),
                ]));
                shard_raws.push(shard);
                case_first += count;
                ordinal += 1;
            }
            family_raws.push(finalize_nested(manifest_object([
                (
                    "schema",
                    manifest_string("golden-board.m2-damage-family/v1"),
                ),
                ("damage_manifest_identity", manifest_string(&root_identity)),
                ("profile_id", manifest_string(PROFILE_ID_V1)),
                ("family_id", manifest_string(FAMILY_IDS[family])),
                ("guarantee_id", manifest_string(guarantees[family])),
                ("shard_rows", ManifestValue::Array(references)),
                (
                    "summary",
                    manifest_object([
                        ("case_count", ManifestValue::U64(FAMILY_COUNTS[family])),
                        ("wrong_accept_count", ManifestValue::U64(0)),
                        ("result", manifest_string("pass")),
                    ]),
                ),
            ])));
        }
        (root, family_raws, shard_raws)
    }

    fn standalone_proof(violation_counts: [u64; 9]) -> Vec<u8> {
        let rows = proof_rows_from_violation_counts_v1(violation_counts).unwrap();
        let passed = rows.iter().all(|row| row.passed);
        let rows = rows.iter().map(row_manifest).collect::<Vec<_>>();
        let without_identity = manifest_object([
            (
                "schema",
                manifest_string("golden-board.m2-independence-proof/v1"),
            ),
            ("profile_id", manifest_string(PROFILE_ID_V1)),
            (
                "candidate_manifest_sha256",
                manifest_string(&"0".repeat(64)),
            ),
            ("ownership_ledger_sha256", manifest_string(&"1".repeat(64))),
            ("damage_manifest_sha256", manifest_string(&"2".repeat(64))),
            ("predicate_rows", ManifestValue::Array(rows.clone())),
            (
                "summary",
                manifest_object([
                    ("predicate_count", ManifestValue::U64(9)),
                    (
                        "result",
                        manifest_string(if passed { "pass" } else { "fail" }),
                    ),
                ]),
            ),
        ]);
        let without_identity_raw = serialize_manifest(&without_identity).unwrap();
        let manifest_identity = identity_hex(IDENTITY_DOMAIN, &[&without_identity_raw]).unwrap();
        serialize_manifest(&manifest_object([
            (
                "schema",
                manifest_string("golden-board.m2-independence-proof/v1"),
            ),
            ("profile_id", manifest_string(PROFILE_ID_V1)),
            (
                "candidate_manifest_sha256",
                manifest_string(&"0".repeat(64)),
            ),
            ("ownership_ledger_sha256", manifest_string(&"1".repeat(64))),
            ("damage_manifest_sha256", manifest_string(&"2".repeat(64))),
            ("predicate_rows", ManifestValue::Array(rows)),
            (
                "summary",
                manifest_object([
                    ("predicate_count", ManifestValue::U64(9)),
                    (
                        "result",
                        manifest_string(if passed { "pass" } else { "fail" }),
                    ),
                    ("manifest_identity", manifest_string(&manifest_identity)),
                ]),
            ),
        ]))
        .unwrap()
    }

    #[test]
    fn proof_rows_use_only_owned_counts_and_literal_floor() {
        let rows = proof_rows_from_violation_counts_v1([0; 9]).unwrap();
        assert_eq!(rows.len(), 9);
        for (ordinal, row) in rows.iter().enumerate() {
            assert_eq!(row.predicate_id, PROOF_PREDICATE_IDS_V1[ordinal]);
            assert_eq!(row.witness_count, PROOF_WITNESS_COUNTS_V1[ordinal]);
            assert_eq!(row.minimum_surviving_count, 1);
            assert_eq!(row.violation_count, 0);
            assert!(row.passed);
        }
        assert_eq!(
            ProofPredicateRowV1::new(PROOF_PREDICATE_IDS_V1[0], 1, 0),
            Err(IndependenceV1Error::Manifest)
        );
    }

    #[test]
    fn persisted_candidate_derives_exact_owned_witness_populations() {
        let (candidate, ownership) = regenerated_candidate_artifacts();
        let counts = derive_proof_witness_counts_v1(&candidate, &ownership).unwrap();
        assert_eq!(counts, PROOF_WITNESS_COUNTS_V1);
        let evidence = candidate_evidence_v1(&candidate, &ownership).unwrap();
        assert_eq!(structural_violation_counts_v1(&evidence).unwrap(), [0; 9]);
    }

    #[test]
    fn complete_synthetic_gate6_bundle_renders_and_admits_exact_proof() {
        let (candidate, ownership) = regenerated_candidate_artifacts();
        let (root, families, shards) = synthetic_damage_bundle(&candidate, &ownership);
        let family_refs = families.iter().map(Vec::as_slice).collect::<Vec<_>>();
        let shard_refs = shards.iter().map(Vec::as_slice).collect::<Vec<_>>();
        let proof = build_independence_proof_from_bundle_v1(
            &candidate,
            &ownership,
            &root,
            &family_refs,
            &shard_refs,
        )
        .unwrap();
        assert!(proof.passed);
        assert_eq!(proof.predicate_rows.len(), 9);
        assert!(
            proof
                .predicate_rows
                .iter()
                .all(|row| row.violation_count == 0)
        );
        admit_independence_proof_v1(
            &proof.canonical_bytes,
            &candidate,
            &ownership,
            &root,
            &proof.predicate_rows,
        )
        .unwrap();

        let mut missing = shard_refs.clone();
        missing.pop();
        assert_eq!(
            build_independence_proof_from_bundle_v1(
                &candidate,
                &ownership,
                &root,
                &family_refs,
                &missing,
            ),
            Err(IndependenceV1Error::Binding)
        );

        let root_value = validate_canonical_manifest(&root).unwrap();
        let root_identity = text(
            field(
                object(field(object(&root_value).unwrap(), "summary").unwrap()).unwrap(),
                "manifest_identity",
            )
            .unwrap(),
        )
        .unwrap();
        let original = validate_canonical_manifest(&shards[0]).unwrap();
        let original_rows = array(field(object(&original).unwrap(), "case_rows").unwrap()).unwrap();
        assert_eq!(original_rows.len(), 16);
        let split = [
            render_case_shard_v1(root_identity, "D0", 0, 0, &original_rows[..8]).unwrap(),
            render_case_shard_v1(root_identity, "D0", 1, 8, &original_rows[8..]).unwrap(),
        ];
        let references = split
            .iter()
            .enumerate()
            .map(|(ordinal, raw)| {
                manifest_object([
                    ("shard_ordinal", ManifestValue::U64(ordinal as u64)),
                    ("case_first", ManifestValue::U64(ordinal as u64 * 8)),
                    ("case_count", ManifestValue::U64(8)),
                    ("manifest_sha256", manifest_string(&digest(raw))),
                ])
            })
            .collect();
        let mut family_value = validate_canonical_manifest(&families[0]).unwrap();
        let family_root = object_mut(&mut family_value).unwrap();
        family_root.insert("shard_rows".to_owned(), ManifestValue::Array(references));
        object_mut(family_root.get_mut("summary").unwrap())
            .unwrap()
            .remove("manifest_identity");
        let split_family = finalize_nested(family_value);
        let mut split_families = families.clone();
        split_families[0] = split_family;
        let mut split_shards = vec![split[0].clone(), split[1].clone()];
        split_shards.extend(shards.iter().skip(1).cloned());
        let split_family_refs = split_families.iter().map(Vec::as_slice).collect::<Vec<_>>();
        let split_shard_refs = split_shards.iter().map(Vec::as_slice).collect::<Vec<_>>();
        assert_eq!(
            build_independence_proof_from_bundle_v1(
                &candidate,
                &ownership,
                &root,
                &split_family_refs,
                &split_shard_refs,
            ),
            Err(IndependenceV1Error::Binding)
        );
    }

    #[test]
    fn exact_case_owner_rejects_channel_coordinate_and_section_id_mutants() {
        let (candidate_raw, ownership_raw) = regenerated_candidate_artifacts();
        let candidate = candidate_evidence_v1(&candidate_raw, &ownership_raw).unwrap();
        let d2 = exact_d2_placements_v1(&candidate).unwrap();
        let mut d3_cache = BTreeMap::new();

        let mut d1 = synthetic_case(1, 0, &candidate, &d2, &mut d3_cache);
        validate_case_row_v1(&d1, 1, 0, &candidate, &d2, &mut d3_cache).unwrap();
        object_mut(&mut d1)
            .unwrap()
            .insert("channel".to_owned(), manifest_string("OBS_BITS"));
        assert_eq!(
            validate_case_row_v1(&d1, 1, 0, &candidate, &d2, &mut d3_cache),
            Err(IndependenceV1Error::Binding)
        );

        let mut d2_case = synthetic_case(2, 1, &candidate, &d2, &mut d3_cache);
        let parameters = match object_mut(&mut d2_case)
            .unwrap()
            .get_mut("parameter_projection")
            .unwrap()
        {
            ManifestValue::Array(parameters) => parameters,
            _ => unreachable!(),
        };
        let top_left = object_mut(&mut parameters[1])
            .unwrap()
            .get_mut("value")
            .unwrap();
        let ManifestValue::Array(coordinates) = top_left else {
            unreachable!()
        };
        let ManifestValue::Array(coordinate) = &mut coordinates[0] else {
            unreachable!()
        };
        coordinate[0] = ManifestValue::U64(unsigned(&coordinate[0]).unwrap() + 1);
        assert_eq!(
            validate_case_row_v1(&d2_case, 2, 1, &candidate, &d2, &mut d3_cache),
            Err(IndependenceV1Error::Binding)
        );

        let mut d3_case = synthetic_case(3, 0, &candidate, &d2, &mut d3_cache);
        let parameters = match object_mut(&mut d3_case)
            .unwrap()
            .get_mut("parameter_projection")
            .unwrap()
        {
            ManifestValue::Array(parameters) => parameters,
            _ => unreachable!(),
        };
        let coordinates = object_mut(&mut parameters[0])
            .unwrap()
            .get_mut("value")
            .unwrap();
        let ManifestValue::Array(coordinates) = coordinates else {
            unreachable!()
        };
        let ManifestValue::Array(coordinate) = &mut coordinates[0] else {
            unreachable!()
        };
        coordinate[1] = ManifestValue::U64(unsigned(&coordinate[1]).unwrap() + 1);
        assert_eq!(
            validate_case_row_v1(&d3_case, 3, 0, &candidate, &d2, &mut d3_cache),
            Err(IndependenceV1Error::Binding)
        );

        let mut missing = synthetic_case(7, 0, &candidate, &d2, &mut d3_cache);
        let states = match object_mut(&mut missing)
            .unwrap()
            .get_mut("expected_section_states")
            .unwrap()
        {
            ManifestValue::Array(states) => states,
            _ => unreachable!(),
        };
        states.pop();
        assert_eq!(
            validate_case_row_v1(&missing, 7, 0, &candidate, &d2, &mut d3_cache),
            Err(IndependenceV1Error::Binding)
        );

        let mut substituted = synthetic_case(7, 0, &candidate, &d2, &mut d3_cache);
        let states = match object_mut(&mut substituted)
            .unwrap()
            .get_mut("expected_section_states")
            .unwrap()
        {
            ManifestValue::Array(states) => states,
            _ => unreachable!(),
        };
        object_mut(&mut states[0])
            .unwrap()
            .insert("section_id".to_owned(), ManifestValue::U64(99));
        assert_eq!(
            validate_case_row_v1(&substituted, 7, 0, &candidate, &d2, &mut d3_cache),
            Err(IndependenceV1Error::Binding)
        );
    }

    #[test]
    fn proof_parser_is_exact_for_pass_fail_order_and_identity() {
        let passing = standalone_proof([0; 9]);
        let parsed = parse_independence_proof_v1(&passing).unwrap();
        assert!(parsed.passed);
        assert_eq!(parsed.canonical_bytes, passing);

        let mut violations = [0_u64; 9];
        violations[7] = 2;
        let failing = standalone_proof(violations);
        let parsed = parse_independence_proof_v1(&failing).unwrap();
        assert!(!parsed.passed);
        assert_eq!(parsed.predicate_rows[7].violation_count, 2);

        let mut value = validate_canonical_manifest(&passing).unwrap();
        let root = object_mut(&mut value).unwrap();
        let rows = match root.get_mut("predicate_rows").unwrap() {
            ManifestValue::Array(rows) => rows,
            _ => unreachable!(),
        };
        let first = object_mut(&mut rows[0]).unwrap();
        first.insert("witness_count".to_owned(), ManifestValue::U64(1));
        let mutant = serialize_manifest(&value).unwrap();
        assert_eq!(
            parse_independence_proof_v1(&mutant),
            Err(IndependenceV1Error::Manifest)
        );
    }
}
