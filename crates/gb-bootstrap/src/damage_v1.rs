//! Observation-only M2 R3 damage decoder and result-v1 projection.
//!
//! This module is intentionally additive.  The retained `damage` module owns
//! the archived R2 decoder/result-v0 contract; this module owns only promoted
//! profile v7.  Decoder inputs are serialized observations plus tracked,
//! candidate-neutral owner/profile/recipe code.  A clean carrier, candidate
//! manifest, ownership ledger, case identity, and expected result are never
//! accepted here.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::OnceLock;

use gb_foundation::{ManifestValue, serialize_manifest};
use gb_slice::{SliceInputs, compile_slice_v0};
use sha2::{Digest, Sha256};

use crate::candidate::{
    DecodeQuality, EH_UNIT_BYTES, EhErasure, EhObservation, HierarchicalGroupState,
    HierarchicalLaneState, RS_CODEWORD_BYTES, TransportFamily, aggregate_repetition_observation,
    decode_eh_unit, decode_rs_unit, diagnose_hierarchical_eh_group, encode_eh_unit,
    profile_by_version,
};
use crate::candidate_recipe::build_eh_recipe_package;
use crate::carrier::{AffineMap, HierarchicalManifestationCore, HierarchicalMap};
use crate::damage::{
    AcceptedHypothesis, ArtifactState, Coordinate, CounterWords, FragmentState, ObsMatrix,
    ObsUnits, ResourceProjection, SectionResult, SectionState, UnitEntry, WINDOW_DOMAIN,
    d2_square_side, encode_eh_mutant_chunk, observation_sha256, sample_without_replacement,
    serialize_obs_bits, serialize_obs_matrix, serialize_obs_units,
};
use crate::recipe::{RecipePackage, decode_recipe_package, evaluate_serialized_recipe};
use crate::{
    CLOSURE_M2_REQUIRED, COMMON_PAYLOAD_BYTES, FragmentWitness, Inventory, InventoryEntry,
    LOCAL_CHECK_DOMAIN, MAX_BLOCKS_PER_COPY, MAX_ENVELOPE_BYTES, MAX_RAW_BITS,
    MAX_SECTION_CANDIDATES, MAX_SIDE, RecoveryQuality, SECTION_INVENTORY, SectionEnvelope,
    SectionWitness, aggregate_section_witnesses, assemble_content_stream, assemble_semantic_copy,
    crc32c, decode_common_block, decode_inventory, decode_section, decode_tier_frame,
    encode_common_block, encode_section, fragment_envelope, sector_cell_at,
    validate_envelope_against_inventory, validate_tier_against_inventory,
};

const PROFILE_V7: u16 = 7;
const PROFILE_V7_ID: &str = "eh72-hier-r5-r2-r1-crc32c-v0";
const ABSENT_U16: u16 = u16::MAX;
const ZERO_SHA256: &str = "0000000000000000000000000000000000000000000000000000000000000000";
const MAX_PHYSICAL_UNITS: u32 = 16_384;
const SECTION_ATTEMPT_LIMIT: u64 = 4_096;
const RECIPE_STEP_LIMIT: u64 = 268_435_456;
const RECIPE_SCRATCH_LIMIT: u32 = 16_777_216;
const EH_RECIPE_STEPS: u64 = 80_435;
const EH_RECIPE_SCRATCH: u64 = 4_613;
const REPETITION_RECIPE_STEPS: u64 = 24;
const REPETITION_RECIPE_SCRATCH: u64 = 10;
const EH_CODEWORDS_PER_UNIT: u64 = 24;
const REPETITION_SYMBOLS_PER_GROUP: u64 = 1_728;
const ROUTE_MAGIC: &[u8; 8] = b"GBROUTE\0";
const CALIBRATIONS: [[u8; 32]; 4] = [
    [
        0xf0, 0x0f, 0xcc, 0x33, 0xaa, 0x55, 0x96, 0x69, 0x81, 0x7e, 0x24, 0xdb, 0x18, 0xe7, 0x42,
        0xbd, 0x01, 0xfe, 0x02, 0xfd, 0x04, 0xfb, 0x08, 0xf7, 0x10, 0xef, 0x20, 0xdf, 0x40, 0xbf,
        0x80, 0x7f,
    ],
    [
        0xcc, 0x33, 0xaa, 0x55, 0x96, 0x69, 0xf0, 0x0f, 0x02, 0xfd, 0x18, 0xe7, 0x42, 0xbd, 0x81,
        0x7e, 0x04, 0xfb, 0x08, 0xf7, 0x10, 0xef, 0x20, 0xdf, 0x40, 0xbf, 0x80, 0x7f, 0x01, 0xfe,
        0x24, 0xdb,
    ],
    [
        0xaa, 0x55, 0x96, 0x69, 0xf0, 0x0f, 0xcc, 0x33, 0x04, 0xfb, 0x42, 0xbd, 0x81, 0x7e, 0x24,
        0xdb, 0x08, 0xf7, 0x10, 0xef, 0x20, 0xdf, 0x40, 0xbf, 0x80, 0x7f, 0x01, 0xfe, 0x02, 0xfd,
        0x18, 0xe7,
    ],
    [
        0x96, 0x69, 0xf0, 0x0f, 0xcc, 0x33, 0xaa, 0x55, 0x08, 0xf7, 0x81, 0x7e, 0x24, 0xdb, 0x18,
        0xe7, 0x10, 0xef, 0x20, 0xdf, 0x40, 0xbf, 0x80, 0x7f, 0x01, 0xfe, 0x02, 0xfd, 0x04, 0xfb,
        0x42, 0xbd,
    ],
];
const FACT_STAGES: [u8; 12] = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5];
const FACT_RECIPE_IDS: [u16; 12] = [101, 102, 103, 104, 105, 106, 107, 113, 109, 110, 111, 112];
const FACT_NAMES: [&[u8]; 12] = [
    b"binary-relations-v0",
    b"entry-hypotheses-v0",
    b"unsigned-order-v0",
    b"row-major-msb-v0",
    b"route-recipe-framing-v0",
    b"recipe-language-status-bounds-v0",
    b"common-block-local-crc32c-v0",
    b"eh72-hier-repetition-v1",
    b"slot-affine-adapter-v1",
    b"group-fragment-adapter-v1",
    b"selected-section-check-inventory-v0",
    b"tier-frame-content-validation-v0",
];
const V7_TABLE_IDS: [u16; 13] = [3, 4, 5, 10, 11, 12, 13, 14, 15, 17, 18, 19, 20];
const V7_RECIPE_IDS: [u16; 22] = [
    1, 2, 3, 4, 30, 90, 92, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112,
    113,
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DamageV1Error {
    Channel,
    Owner,
    Observation,
    Profile,
    Reconstruction,
    ResourceLimit,
}

pub type Result<T> = std::result::Result<T, DamageV1Error>;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FragmentDiagnosticV1 {
    pub input_id: u32,
    pub profile_version: Option<u16>,
    pub section_id: u32,
    pub semantic_copy_id: u16,
    pub fragment_index: u16,
    pub replica_index: u16,
    pub physical_replica_count: u16,
    pub state: FragmentState,
    pub common_block_sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RecoveryResultV1 {
    pub profile_version: Option<u16>,
    pub inventory_established: bool,
    pub resource: ResourceProjection,
    pub artifact_state: ArtifactState,
    pub sections: Vec<SectionResult>,
    pub fragments: Vec<FragmentDiagnosticV1>,
    pub accepted_hypotheses: Vec<AcceptedHypothesis>,
}

impl RecoveryResultV1 {
    fn closed(state: ArtifactState, resource: ResourceProjection) -> Self {
        Self {
            profile_version: None,
            inventory_established: false,
            resource,
            artifact_state: state,
            sections: Vec::new(),
            fragments: Vec::new(),
            accepted_hypotheses: Vec::new(),
        }
    }
}

#[derive(Clone, Copy)]
struct ResourceRow {
    package_sha256: &'static str,
    primitive_steps: u64,
    peak_scratch_bytes: u64,
    invocations_per_unit: u64,
}

fn registry_resource_row(profile_version: u16) -> Result<ResourceRow> {
    let row = match profile_version {
        7 => ResourceRow {
            package_sha256: "4bd8e0d485ae6e6a65f4edc4ef2aaac9585a2bcd8c4623e44d69f1dad3b0ec8e",
            primitive_steps: EH_RECIPE_STEPS,
            peak_scratch_bytes: EH_RECIPE_SCRATCH,
            invocations_per_unit: EH_CODEWORDS_PER_UNIT,
        },
        2 => ResourceRow {
            package_sha256: "cce1758613d7f10278533409e07103ae15162972fcf30030e17c233e39664011",
            primitive_steps: 80_435,
            peak_scratch_bytes: 4_613,
            invocations_per_unit: 24,
        },
        3 => ResourceRow {
            package_sha256: "8c91ba74f9bbed97aed89191e8d8d30a9a0c4d32bd5ac98b63a4c19ed71fb0e7",
            primitive_steps: 80_435,
            peak_scratch_bytes: 4_613,
            invocations_per_unit: 24,
        },
        4 => ResourceRow {
            package_sha256: "de237fcd9d53581710404bd8b00152cb68f50adef48e715fdd4572e786bae4b8",
            primitive_steps: 80_435,
            peak_scratch_bytes: 4_613,
            invocations_per_unit: 24,
        },
        5 => ResourceRow {
            package_sha256: "2dd94f23f63bd4fbeb8d56565a9cc9a7e0a2054d3483e364cfb60e7751058e91",
            primitive_steps: 1_698_049,
            peak_scratch_bytes: 7_688,
            invocations_per_unit: 1,
        },
        6 => ResourceRow {
            package_sha256: "1c05a1f57394d292487f46561492619358fe2d12e42e3a20194d5917f351e555",
            primitive_steps: 1_698_049,
            peak_scratch_bytes: 7_688,
            invocations_per_unit: 1,
        },
        _ => return Err(DamageV1Error::Profile),
    };
    Ok(row)
}

fn checked_charge(
    resource: &mut ResourceProjection,
    primitive_steps: u64,
    invocations: u64,
    scratch: u64,
) -> Result<()> {
    resource.primitive_steps = resource
        .primitive_steps
        .checked_add(
            primitive_steps
                .checked_mul(invocations)
                .ok_or(DamageV1Error::ResourceLimit)?,
        )
        .ok_or(DamageV1Error::ResourceLimit)?;
    resource.peak_scratch_bytes = resource.peak_scratch_bytes.max(scratch);
    Ok(())
}

fn charge_registry_lane(resource: &mut ResourceProjection, profile_version: u16) -> Result<()> {
    let row = registry_resource_row(profile_version)?;
    checked_charge(
        resource,
        row.primitive_steps,
        row.invocations_per_unit,
        row.peak_scratch_bytes,
    )
}

fn charge_repetition_group(resource: &mut ResourceProjection) -> Result<()> {
    checked_charge(
        resource,
        REPETITION_RECIPE_STEPS,
        REPETITION_SYMBOLS_PER_GROUP,
        REPETITION_RECIPE_SCRATCH,
    )?;
    checked_charge(
        resource,
        EH_RECIPE_STEPS,
        EH_CODEWORDS_PER_UNIT,
        EH_RECIPE_SCRATCH,
    )
}

fn charge_section_attempt(resource: &mut ResourceProjection) -> Result<()> {
    let next = resource
        .section_attempts
        .checked_add(1)
        .ok_or(DamageV1Error::ResourceLimit)?;
    if next > SECTION_ATTEMPT_LIMIT {
        return Err(DamageV1Error::ResourceLimit);
    }
    resource.section_attempts = next;
    Ok(())
}

fn toml_u64(root: &toml::Value, table: &str, key: &str) -> Option<u64> {
    u64::try_from(root.get(table)?.get(key)?.as_integer()?).ok()
}

fn verify_promoted_decoder_owners() -> Result<()> {
    static VERIFIED: OnceLock<std::result::Result<(), DamageV1Error>> = OnceLock::new();
    *VERIFIED.get_or_init(|| {
        let promotion_raw = include_bytes!("../../../spec/m2-r3-owner-promotion-v1.toml");
        let damage_raw = include_bytes!("../../../spec/damage-policy-v1.toml");
        let profile_raw = include_bytes!("../../../spec/profile-policy-v1.toml");
        let limits_raw = include_bytes!("../../../spec/profile-limits-v1.toml");
        let route_raw = include_bytes!("../../../spec/route-data-v1.json");
        let bootstrap_raw = include_bytes!("../../../spec/bootstrap-v1.md");
        let fixture_raw = include_bytes!("../../../conformance/m2-r3-owner-v1.json");
        let curriculum_raw = include_bytes!("../../../spec/curriculum-v0.toml");
        let compiled = compile_slice_v0(SliceInputs {
            declaration: include_bytes!("../../../studies/m2/slice-v0.json"),
            content_fixture: include_bytes!("../../../conformance/content-v0.json"),
            chess_fixture: include_bytes!("../../../conformance/chess-v0.json"),
            game_set: include_bytes!("../../../reports/game-set-v0.bin"),
            content_spec: include_bytes!("../../../spec/content-v0.md"),
            constants: include_bytes!("../../../spec/constants-v0.toml"),
            curriculum: curriculum_raw,
        })
        .map_err(|_| DamageV1Error::Owner)?;
        crate::policy::admit_r3_promoted_owner_bundle(
            bootstrap_raw,
            profile_raw,
            damage_raw,
            route_raw,
            limits_raw,
            promotion_raw,
            fixture_raw,
            &compiled,
            curriculum_raw,
        )
        .map_err(|_| DamageV1Error::Owner)?;
        let promotion: toml::Value =
            toml::from_str(std::str::from_utf8(promotion_raw).map_err(|_| DamageV1Error::Owner)?)
                .map_err(|_| DamageV1Error::Owner)?;
        if promotion.get("schema").and_then(toml::Value::as_str)
            != Some("golden-board.m2-r3-owner-promotion/v1")
            || promotion.get("status").and_then(toml::Value::as_str) != Some("pre-result-frozen")
            || promotion
                .get("damage_observation_authorized")
                .and_then(toml::Value::as_bool)
                != Some(true)
            || promotion
                .get("active_profile_version")
                .and_then(toml::Value::as_integer)
                != Some(7)
            || promotion
                .get("active_candidate_id")
                .and_then(toml::Value::as_str)
                != Some(PROFILE_V7_ID)
        {
            return Err(DamageV1Error::Owner);
        }
        let digest = |raw: &[u8]| format!("{:x}", Sha256::digest(raw));
        let draft = promotion
            .get("draft_owner")
            .and_then(toml::Value::as_array)
            .ok_or(DamageV1Error::Owner)?;
        let generated = promotion
            .get("generated_owner")
            .and_then(toml::Value::as_array)
            .ok_or(DamageV1Error::Owner)?;
        let owner = |rows: &[toml::Value], path: &str, raw: &[u8]| {
            rows.iter().any(|row| {
                row.get("path").and_then(toml::Value::as_str) == Some(path)
                    && row.get("sha256").and_then(toml::Value::as_str) == Some(digest(raw).as_str())
            })
        };
        if !owner(draft, "spec/bootstrap-v1.md", bootstrap_raw)
            || !owner(draft, "spec/profile-policy-v1.toml", profile_raw)
            || !owner(draft, "spec/damage-policy-v1.toml", damage_raw)
            || !owner(draft, "conformance/m2-r3-owner-v1.json", fixture_raw)
            || !owner(generated, "spec/route-data-v1.json", route_raw)
            || !owner(generated, "spec/profile-limits-v1.toml", limits_raw)
        {
            return Err(DamageV1Error::Owner);
        }
        let damage: toml::Value =
            toml::from_str(std::str::from_utf8(damage_raw).map_err(|_| DamageV1Error::Owner)?)
                .map_err(|_| DamageV1Error::Owner)?;
        let limits: toml::Value =
            toml::from_str(std::str::from_utf8(limits_raw).map_err(|_| DamageV1Error::Owner)?)
                .map_err(|_| DamageV1Error::Owner)?;
        let limits_profile = limits
            .get("profile")
            .and_then(toml::Value::as_array)
            .and_then(|rows| rows.first());
        if damage.get("schema").and_then(toml::Value::as_str)
            != Some("golden-board.damage-policy/v1")
            || toml_u64(&damage, "generated", "physical_unit_count") != Some(1_841)
            || toml_u64(&damage, "generated", "obs_units_bytes") != Some(408_901)
            || toml_u64(&damage, "generated", "v7_decoder_30_primitive_steps")
                != Some(EH_RECIPE_STEPS)
            || toml_u64(&damage, "generated", "v7_decoder_30_peak_scratch_bytes")
                != Some(EH_RECIPE_SCRATCH)
            || toml_u64(&damage, "generated", "repetition_113_primitive_steps")
                != Some(REPETITION_RECIPE_STEPS)
            || toml_u64(&damage, "generated", "repetition_113_peak_scratch_bytes")
                != Some(REPETITION_RECIPE_SCRATCH)
            || limits.get("schema").and_then(toml::Value::as_str)
                != Some("golden-board.profile-limits/v1")
            || limits_profile
                .and_then(|row| row.get("id"))
                .and_then(toml::Value::as_str)
                != Some(PROFILE_V7_ID)
            || toml_u64(&limits, "selected_manifestation", "physical_unit_count") != Some(1_841)
        {
            return Err(DamageV1Error::Owner);
        }
        let package_raw =
            build_eh_recipe_package(PROFILE_V7).map_err(|_| DamageV1Error::Reconstruction)?;
        let expected = registry_resource_row(PROFILE_V7)?;
        let package = decode_recipe_package(&package_raw, PROFILE_V7)
            .map_err(|_| DamageV1Error::Reconstruction)?;
        if digest(&package_raw) != expected.package_sha256
            || package.recipe_primitive_steps(30) != Some(EH_RECIPE_STEPS)
            || package.recipe_peak_scratch_bytes(30) != Some(EH_RECIPE_SCRATCH)
            || package.recipe_primitive_steps(113) != Some(REPETITION_RECIPE_STEPS)
            || package.recipe_peak_scratch_bytes(113) != Some(REPETITION_RECIPE_SCRATCH)
        {
            return Err(DamageV1Error::Owner);
        }
        Ok(())
    })
}

fn read_u16(raw: &[u8], offset: usize) -> Option<u16> {
    raw.get(offset..offset.checked_add(2)?)
        .map(|bytes| u16::from_be_bytes(bytes.try_into().unwrap()))
}

fn read_u32(raw: &[u8], offset: usize) -> Option<u32> {
    raw.get(offset..offset.checked_add(4)?)
        .map(|bytes| u32::from_be_bytes(bytes.try_into().unwrap()))
}

fn gcd(mut left: u64, mut right: u64) -> u64 {
    while right != 0 {
        (left, right) = (right, left % right);
    }
    left
}

fn modular_inverse(value: u64, modulus: u64) -> Result<u64> {
    if value == 0 || modulus < 2 || gcd(value, modulus) != 1 {
        return Err(DamageV1Error::Reconstruction);
    }
    let (mut old_r, mut r) = (i128::from(value), i128::from(modulus));
    let (mut old_s, mut s) = (1_i128, 0_i128);
    while r != 0 {
        let quotient = old_r / r;
        (old_r, r) = (r, old_r - quotient * r);
        (old_s, s) = (s, old_s - quotient * s);
    }
    u64::try_from(old_s.rem_euclid(i128::from(modulus))).map_err(|_| DamageV1Error::ResourceLimit)
}

fn matrix_value(matrix: &ObsMatrix, row: usize, column: usize) -> Result<u8> {
    if row >= matrix.side || column >= matrix.side {
        return Err(DamageV1Error::Observation);
    }
    Ok(matrix.values[row * matrix.side + column])
}

fn route_bytes(
    matrix: &ObsMatrix,
    width: usize,
    sector: u8,
    byte_count: usize,
) -> Result<Option<Vec<u8>>> {
    let bit_count = byte_count
        .checked_mul(8)
        .ok_or(DamageV1Error::ResourceLimit)?;
    let sector_cells = width
        .checked_mul(
            matrix
                .side
                .checked_sub(width)
                .ok_or(DamageV1Error::Observation)?,
        )
        .ok_or(DamageV1Error::ResourceLimit)?;
    if bit_count > sector_cells {
        return Ok(None);
    }
    let mut raw = vec![0_u8; byte_count];
    for bit in 0..bit_count {
        let (row, column) = sector_cell_at(matrix.side, width, sector, bit)
            .map_err(|_| DamageV1Error::Observation)?;
        match matrix_value(matrix, row, column)? {
            0 => {}
            1 => raw[bit / 8] |= 1 << (7 - bit % 8),
            2 => return Ok(None),
            _ => return Err(DamageV1Error::Observation),
        }
    }
    Ok(Some(raw))
}

fn package_table_records(raw: &[u8]) -> Option<Vec<&[u8]>> {
    if raw.len() < 64 {
        return None;
    }
    let count = usize::from(read_u16(raw, 18)?);
    let mut offset = 64_usize;
    let mut output = Vec::with_capacity(count);
    for _ in 0..count {
        let header = raw.get(offset..offset.checked_add(16)?)?;
        let payload = usize::try_from(read_u32(header, 12)?).ok()?;
        let end = offset.checked_add(16)?.checked_add(payload)?;
        output.push(raw.get(offset..end)?);
        offset = end;
    }
    Some(output)
}

fn recipe_u32(package: &RecipePackage, recipe_id: u16, input: &[u8]) -> Result<u64> {
    let raw = evaluate_serialized_recipe(package, recipe_id, input)
        .map_err(|_| DamageV1Error::Reconstruction)?;
    if raw.len() != 6 || raw[..2] != [0, 0] {
        return Err(DamageV1Error::Reconstruction);
    }
    Ok(u64::from(u32::from_be_bytes(raw[2..].try_into().unwrap())))
}

fn table_17_multiplier(package_raw: &[u8], interior_side: u16) -> Result<u64> {
    if interior_side % 8 != 0 {
        return Err(DamageV1Error::Reconstruction);
    }
    let index = usize::from(interior_side / 8);
    let table = package_table_records(package_raw)
        .ok_or(DamageV1Error::Reconstruction)?
        .into_iter()
        .find(|row| read_u16(row, 0) == Some(17))
        .ok_or(DamageV1Error::Reconstruction)?;
    if table.get(2).copied() != Some(0)
        || table.get(3).copied() != Some(0)
        || read_u32(table, 4) != Some(8)
        || read_u32(table, 8) != Some(256)
        || read_u32(table, 12) != Some(256)
        || table.len() != 272
    {
        return Err(DamageV1Error::Reconstruction);
    }
    let value = u64::from(*table.get(16 + index).ok_or(DamageV1Error::Reconstruction)?);
    if value == 0 {
        return Err(DamageV1Error::Reconstruction);
    }
    Ok(value)
}

fn observed_hierarchical_map(
    package: &RecipePackage,
    package_raw: &[u8],
    side: u16,
    width: u16,
) -> Result<HierarchicalMap> {
    if !(64..=2_048).contains(&side)
        || side % 8 != 0
        || !(8..=128).contains(&width)
        || width % 8 != 0
        || u32::from(width) * 2 + 8 > u32::from(side)
    {
        return Err(DamageV1Error::Observation);
    }
    let interior_side = side - 2 * width;
    let population = u64::from(interior_side)
        .checked_mul(u64::from(interior_side))
        .ok_or(DamageV1Error::ResourceLimit)?;
    let input = |logical: u32| {
        let mut raw = logical.to_be_bytes().to_vec();
        raw.extend_from_slice(&side.to_be_bytes());
        raw.extend_from_slice(&width.to_be_bytes());
        raw
    };
    let cell_offset = recipe_u32(package, 109, &input(0))?;
    let next = recipe_u32(package, 109, &input(1))?;
    if cell_offset >= population || next >= population {
        return Err(DamageV1Error::Reconstruction);
    }
    let cell_multiplier = (next + population - cell_offset) % population;
    let inverse_cell_multiplier = modular_inverse(cell_multiplier, population)?;
    let unit_slot_count = population / REPETITION_SYMBOLS_PER_GROUP;
    let slot_multiplier = table_17_multiplier(package_raw, interior_side)?;
    let inverse_slot_multiplier = modular_inverse(slot_multiplier, unit_slot_count)?;
    let fixed_pad_cells = population
        .checked_sub(
            unit_slot_count
                .checked_mul(REPETITION_SYMBOLS_PER_GROUP)
                .ok_or(DamageV1Error::ResourceLimit)?,
        )
        .ok_or(DamageV1Error::Reconstruction)?;
    let map = HierarchicalMap {
        side,
        shell_width: width,
        interior_side,
        population,
        unit_slot_count,
        window_side: u16::try_from(32_u64.max(u64::from(interior_side) / 8))
            .map_err(|_| DamageV1Error::ResourceLimit)?,
        cell_multiplier,
        cell_offset,
        inverse_cell_multiplier,
        slot_multiplier,
        inverse_slot_multiplier,
        fixed_pad_cells,
    };
    for physical_ordinal in [0_u64, 1, unit_slot_count / 2, unit_slot_count - 1] {
        for bit in [0_u16, 1, 1_727] {
            let physical = map
                .forward_unit_bit(physical_ordinal, bit)
                .map_err(|_| DamageV1Error::Reconstruction)?;
            if map
                .inverse(physical)
                .map_err(|_| DamageV1Error::Reconstruction)?
                != (crate::carrier::HierarchicalInverse::Unit {
                    physical_ordinal,
                    replica_bit: bit,
                    slot: map
                        .slot(physical_ordinal)
                        .map_err(|_| DamageV1Error::Reconstruction)?,
                })
            {
                return Err(DamageV1Error::Reconstruction);
            }
        }
    }
    Ok(map)
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ParsedRouteV1 {
    width: u16,
    sector: u8,
    map: HierarchicalMap,
    package: RecipePackage,
}

fn charge_route_recipe(
    resource: &mut ResourceProjection,
    package: &RecipePackage,
    recipe_id: u16,
) -> Result<()> {
    let steps = package
        .recipe_primitive_steps(recipe_id)
        .ok_or(DamageV1Error::Reconstruction)?;
    let scratch = package
        .recipe_peak_scratch_bytes(recipe_id)
        .ok_or(DamageV1Error::Reconstruction)?;
    checked_charge(resource, steps, 1, scratch)
}

fn parse_sector_route_v1(
    matrix: &ObsMatrix,
    width: usize,
    sector: u8,
    resource: &mut ResourceProjection,
) -> Result<Option<ParsedRouteV1>> {
    let Some(head) = route_bytes(matrix, width, sector, 64)? else {
        return Ok(None);
    };
    if head[..32] != CALIBRATIONS[usize::from(sector)] || &head[32..40] != ROUTE_MAGIC {
        return Ok(None);
    }
    let envelope = &head[32..64];
    let record_count = usize::from(read_u16(envelope, 14).unwrap());
    let record_bytes = usize::try_from(read_u32(envelope, 16).unwrap())
        .map_err(|_| DamageV1Error::ResourceLimit)?;
    let package_bytes = usize::try_from(read_u32(envelope, 20).unwrap())
        .map_err(|_| DamageV1Error::ResourceLimit)?;
    let prefix_cells = usize::try_from(read_u32(envelope, 24).unwrap())
        .map_err(|_| DamageV1Error::ResourceLimit)?;
    if read_u16(envelope, 8) != Some(1)
        || envelope[10] != sector
        || envelope[11] != sector
        || read_u16(envelope, 12) != Some(PROFILE_V7)
        || !(39..=256).contains(&record_count)
        || record_bytes > 30_720
        || package_bytes > 1_048_576
        || prefix_cells
            != (64_usize
                .checked_add(record_bytes)
                .ok_or(DamageV1Error::ResourceLimit)?)
            .checked_mul(8)
            .ok_or(DamageV1Error::ResourceLimit)?
        || read_u16(envelope, 28) != Some(256)
        || read_u16(envelope, 30) != Some(0)
    {
        return Ok(None);
    }
    let Some(route) = route_bytes(matrix, width, sector, 64 + record_bytes)? else {
        return Ok(None);
    };
    let records = &route[64..];
    let base = u16::from(sector) * 10_000;
    let mut offset = 0_usize;
    let mut rows = Vec::<(u8, u8, u16, &[u8])>::with_capacity(record_count);
    let mut prior_id = 0_u16;
    let mut prior_stage = 0_u8;
    for ordinal in 0..record_count {
        let Some(header) = records.get(offset..offset + 8) else {
            return Ok(None);
        };
        let stage = header[0];
        let kind = header[1];
        let record_id = u16::from_be_bytes(header[2..4].try_into().unwrap());
        let payload_bytes = usize::try_from(u32::from_be_bytes(header[4..8].try_into().unwrap()))
            .map_err(|_| DamageV1Error::ResourceLimit)?;
        let end = offset
            .checked_add(8)
            .and_then(|value| value.checked_add(payload_bytes))
            .ok_or(DamageV1Error::ResourceLimit)?;
        let Some(payload) = records.get(offset + 8..end) else {
            return Ok(None);
        };
        if stage > 5
            || kind == 0
            || kind > 7
            || ordinal != 0 && (record_id <= prior_id || stage < prior_stage)
        {
            return Ok(None);
        }
        rows.push((stage, kind, record_id, payload));
        prior_id = record_id;
        prior_stage = stage;
        offset = end;
    }
    if offset != records.len() || record_count < 39 {
        return Ok(None);
    }
    for fact in 1_u16..=12 {
        let stage = FACT_STAGES[usize::from(fact - 1)];
        let start = usize::from(fact - 1) * 3;
        for (local, kind) in [1_u8, 2, 3].into_iter().enumerate() {
            let (actual_stage, actual_kind, id, payload) = rows[start + local];
            let fact_index = usize::from(fact - 1);
            if actual_stage != stage
                || actual_kind != kind
                || id != base + fact * 100 + 1 + local as u16
                || payload.len() < if kind == 1 { 14 } else { 12 }
                || read_u16(payload, 0) != Some(fact)
                || kind == 1
                    && (read_u16(payload, 2) != Some(fact)
                        || payload[4] != 3
                        || payload[5] != 0
                        || read_u32(payload, 6) != u32::try_from(FACT_NAMES[fact_index].len()).ok()
                        || read_u32(payload, 10) != Some(1)
                        || payload.get(14..) != Some(FACT_NAMES[fact_index]))
            {
                return Ok(None);
            }
            if kind != 1 {
                let input = usize::try_from(read_u32(payload, 4).unwrap())
                    .map_err(|_| DamageV1Error::ResourceLimit)?;
                let output = usize::try_from(read_u32(payload, 8).unwrap())
                    .map_err(|_| DamageV1Error::ResourceLimit)?;
                if 12_usize
                    .checked_add(input)
                    .and_then(|value| value.checked_add(output))
                    != Some(payload.len())
                {
                    return Ok(None);
                }
            }
        }
    }
    let table_count = record_count - 39;
    for (index, row) in rows[36..36 + table_count].iter().enumerate() {
        if row.0 != 5
            || row.1 != 4
            || row.2 != base + 5_001 + index as u16
            || read_u16(row.3, 0) != V7_TABLE_IDS.get(index).copied()
        {
            return Ok(None);
        }
    }
    let package_row = rows[36 + table_count];
    if package_row.0 != 5
        || package_row.1 != 5
        || package_row.2 != base + 6_001
        || package_row.3.len() != package_bytes
        || package_row.3.len() < 64
        || &package_row.3[..8] != b"GBRECP0\0"
    {
        return Ok(None);
    }
    // Once the route and its unique package record are structurally bound,
    // exceeding an owned recipe resource ceiling is a global resource-limit,
    // not an ordinary invalid-route result that may be hidden by another
    // redundant sector.  Keep malformed non-resource package fields on the
    // ordinary fail-closed route-rejection path.
    let declared_steps = u64::from_be_bytes(package_row.3[36..44].try_into().unwrap());
    let declared_scratch = u32::from_be_bytes(package_row.3[44..48].try_into().unwrap());
    if declared_steps > RECIPE_STEP_LIMIT || declared_scratch > RECIPE_SCRATCH_LIMIT {
        return Err(DamageV1Error::ResourceLimit);
    }
    let Ok(package) = decode_recipe_package(package_row.3, PROFILE_V7) else {
        return Ok(None);
    };
    if package.recipe_ids().ne(V7_RECIPE_IDS)
        || package.recipe_primitive_steps(30) != Some(EH_RECIPE_STEPS)
        || package.recipe_peak_scratch_bytes(30) != Some(EH_RECIPE_SCRATCH)
        || package.recipe_primitive_steps(113) != Some(REPETITION_RECIPE_STEPS)
        || package.recipe_peak_scratch_bytes(113) != Some(REPETITION_RECIPE_SCRATCH)
    {
        return Ok(None);
    }
    let Some(package_tables) = package_table_records(package_row.3) else {
        return Ok(None);
    };
    if package_tables.len() != table_count
        || rows[36..36 + table_count]
            .iter()
            .zip(package_tables)
            .any(|(route_table, package_table)| route_table.3 != package_table)
    {
        return Ok(None);
    }
    for fact in 0..12 {
        let worked = rows[fact * 3 + 1].3;
        let held = rows[fact * 3 + 2].3;
        let worked_input = usize::try_from(read_u32(worked, 4).unwrap())
            .map_err(|_| DamageV1Error::ResourceLimit)?;
        let held_input = usize::try_from(read_u32(held, 4).unwrap())
            .map_err(|_| DamageV1Error::ResourceLimit)?;
        if worked.get(12..12 + worked_input).is_none()
            || held.get(12..12 + held_input).is_none()
            || worked[12..12 + worked_input] == held[12..12 + held_input]
        {
            return Ok(None);
        }
        for example in [worked, held] {
            let recipe_id = read_u16(example, 2).unwrap();
            if recipe_id != FACT_RECIPE_IDS[fact] {
                return Ok(None);
            }
            let input_bytes = usize::try_from(read_u32(example, 4).unwrap())
                .map_err(|_| DamageV1Error::ResourceLimit)?;
            let output_bytes = usize::try_from(read_u32(example, 8).unwrap())
                .map_err(|_| DamageV1Error::ResourceLimit)?;
            let input_end = 12_usize
                .checked_add(input_bytes)
                .ok_or(DamageV1Error::ResourceLimit)?;
            let output_end = input_end
                .checked_add(output_bytes)
                .ok_or(DamageV1Error::ResourceLimit)?;
            if output_end != example.len() {
                return Ok(None);
            }
            charge_route_recipe(resource, &package, recipe_id)?;
            if evaluate_serialized_recipe(&package, recipe_id, &example[12..input_end])
                .ok()
                .as_deref()
                != Some(&example[input_end..])
            {
                return Ok(None);
            }
        }
    }
    let endpoint = rows[37 + table_count];
    let end = rows[38 + table_count];
    if endpoint.0 != 5
        || endpoint.1 != 6
        || endpoint.2 != base + 7_001
        || endpoint.3 != 1_u32.to_be_bytes()
        || end.0 != 5
        || end.1 != 7
        || end.2 != base + 7_002
        || !end.3.is_empty()
    {
        return Ok(None);
    }
    let width = u16::try_from(width).map_err(|_| DamageV1Error::Observation)?;
    let map = observed_hierarchical_map(&package, package_row.3, matrix.side as u16, width)?;
    Ok(Some(ParsedRouteV1 {
        width,
        sector,
        map,
        package,
    }))
}

fn mapping_sha256_v1(map: HierarchicalMap) -> Result<String> {
    let value = object([
        ("id", string("affine-slot-then-interior-v1")),
        (
            "interior_side",
            ManifestValue::U64(u64::from(map.interior_side)),
        ),
        ("population", ManifestValue::U64(map.population)),
        ("unit_population", ManifestValue::U64(map.unit_slot_count)),
        ("unit_multiplier", ManifestValue::U64(map.slot_multiplier)),
        (
            "unit_inverse_multiplier",
            ManifestValue::U64(map.inverse_slot_multiplier),
        ),
        ("cell_multiplier", ManifestValue::U64(map.cell_multiplier)),
        ("offset", ManifestValue::U64(map.cell_offset)),
        (
            "cell_inverse_multiplier",
            ManifestValue::U64(map.inverse_cell_multiplier),
        ),
    ]);
    let raw = serialize_manifest(&value).map_err(|_| DamageV1Error::Reconstruction)?;
    Ok(observation_sha256(&raw))
}

fn mapping_sha256_legacy(map: AffineMap) -> Result<String> {
    let value = object([
        ("id", string("affine-interior-v1")),
        (
            "interior_side",
            ManifestValue::U64(u64::from(map.interior_side)),
        ),
        ("population", ManifestValue::U64(map.population)),
        ("multiplier", ManifestValue::U64(map.multiplier)),
        ("offset", ManifestValue::U64(map.offset)),
        (
            "inverse_multiplier",
            ManifestValue::U64(map.inverse_multiplier),
        ),
    ]);
    let raw = serialize_manifest(&value).map_err(|_| DamageV1Error::Reconstruction)?;
    Ok(observation_sha256(&raw))
}

fn registry_profile_rank(profile_version: u16) -> Option<u8> {
    match profile_version {
        7 => Some(0),
        2 => Some(1),
        3 => Some(2),
        4 => Some(3),
        5 => Some(4),
        6 => Some(5),
        _ => None,
    }
}

fn sort_and_dedup_accepted(rows: &mut Vec<AcceptedHypothesis>) -> Result<()> {
    if rows
        .iter()
        .any(|row| registry_profile_rank(row.profile_version).is_none())
    {
        return Err(DamageV1Error::Profile);
    }
    rows.sort_by(|left, right| {
        (
            left.transform_id,
            left.polarity_id,
            left.sector_id,
            registry_profile_rank(left.profile_version).unwrap(),
            &left.mapping_sha256,
        )
            .cmp(&(
                right.transform_id,
                right.polarity_id,
                right.sector_id,
                registry_profile_rank(right.profile_version).unwrap(),
                &right.mapping_sha256,
            ))
    });
    rows.dedup();
    Ok(())
}

fn accepted_rows_strictly_sorted(rows: &[AcceptedHypothesis]) -> bool {
    rows.iter()
        .all(|row| registry_profile_rank(row.profile_version).is_some())
        && rows.windows(2).all(|pair| {
            let left = &pair[0];
            let right = &pair[1];
            (
                left.transform_id,
                left.polarity_id,
                left.sector_id,
                registry_profile_rank(left.profile_version).unwrap(),
                &left.mapping_sha256,
            ) < (
                right.transform_id,
                right.polarity_id,
                right.sector_id,
                registry_profile_rank(right.profile_version).unwrap(),
                &right.mapping_sha256,
            )
        })
}

fn discover_routes_v1(
    matrix: &ObsMatrix,
    resource: &mut ResourceProjection,
) -> Result<Vec<ParsedRouteV1>> {
    let maximum = 128.min(matrix.side.saturating_sub(8) / 2);
    let mut output = Vec::new();
    for width in (8..=maximum).step_by(8) {
        for sector in 0..4 {
            if let Some(route) = parse_sector_route_v1(matrix, width, sector, resource)? {
                output.push(route);
            }
        }
    }
    Ok(output)
}

#[derive(Clone, Debug)]
struct LocalCandidate {
    profile_version: u16,
    common: [u8; 191],
    quality: DecodeQuality,
}

#[derive(Clone, Debug)]
struct LaneInput {
    present: bool,
    observation: Option<EhObservation>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct GroupIdentity {
    section_id: u32,
    section_type: u16,
    section_version: u16,
    fragment_index: u16,
    fragment_count: u16,
    section_envelope_length: u32,
}

impl GroupIdentity {
    fn from_common(common: &[u8; 191]) -> Result<Self> {
        let block =
            decode_common_block(common, PROFILE_V7).map_err(|_| DamageV1Error::Reconstruction)?;
        if block.semantic_copy_id != 0 {
            return Err(DamageV1Error::Reconstruction);
        }
        Ok(Self {
            section_id: block.section_id,
            section_type: block.section_type,
            section_version: block.section_version,
            fragment_index: block.fragment_index,
            fragment_count: block.fragment_count,
            section_envelope_length: block.section_envelope_length,
        })
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ExpectedLane {
    identity: GroupIdentity,
    replica_index: u16,
    physical_replica_count: u16,
}

#[derive(Clone, Debug)]
struct GroupRecovery {
    identity: GroupIdentity,
    first_id: u32,
    factor: u8,
    state: FragmentState,
    common: Option<[u8; 191]>,
    lane_states: Vec<FragmentState>,
}

fn section_envelope_length(entry: &InventoryEntry) -> Result<usize> {
    let check = match entry.check_id {
        1 => 4_usize,
        2 => 8_usize,
        _ => return Err(DamageV1Error::Reconstruction),
    };
    18_usize
        .checked_add(
            entry
                .dependencies
                .len()
                .checked_mul(4)
                .ok_or(DamageV1Error::ResourceLimit)?,
        )
        .and_then(|value| value.checked_add(entry.logical_payload_length as usize))
        .and_then(|value| value.checked_add(check))
        .filter(|value| *value <= MAX_ENVELOPE_BYTES)
        .ok_or(DamageV1Error::ResourceLimit)
}

fn inventory_layout(inventory: &Inventory) -> Result<BTreeMap<u32, ExpectedLane>> {
    if inventory.inventory_version != 1 {
        return Err(DamageV1Error::Reconstruction);
    }
    let mut id = 1_u32;
    let mut output = BTreeMap::new();
    for entry in &inventory.entries {
        let envelope_length = section_envelope_length(entry)?;
        let fragment_count = envelope_length.div_ceil(COMMON_PAYLOAD_BYTES);
        let fragment_count_u16 =
            u16::try_from(fragment_count).map_err(|_| DamageV1Error::ResourceLimit)?;
        let factor = u16::from(entry.physical_replica_count);
        for fragment_index in 0..fragment_count_u16 {
            let identity = GroupIdentity {
                section_id: entry.section_id,
                section_type: entry.section_type,
                section_version: entry.section_version,
                fragment_index,
                fragment_count: fragment_count_u16,
                section_envelope_length: envelope_length as u32,
            };
            for replica_index in 0..factor {
                if id > MAX_PHYSICAL_UNITS {
                    return Err(DamageV1Error::ResourceLimit);
                }
                output.insert(
                    id,
                    ExpectedLane {
                        identity,
                        replica_index,
                        physical_replica_count: factor,
                    },
                );
                id = id.checked_add(1).ok_or(DamageV1Error::ResourceLimit)?;
            }
        }
    }
    Ok(output)
}

fn decode_local_candidates(
    units: &ObsUnits,
    resource: &mut ResourceProjection,
) -> Result<BTreeMap<u32, Vec<LocalCandidate>>> {
    let mut output = BTreeMap::<u32, Vec<LocalCandidate>>::new();
    let mut entries = units.entries.iter().collect::<Vec<_>>();
    entries.sort_by_key(|entry| entry.physical_unit_id);
    // This loop order is normative: input ID first, then active v7 followed by
    // archived registry fixtures v2 through v6, without short-circuiting.
    for entry in entries {
        for version in [7_u16, 2, 3, 4, 5, 6] {
            charge_registry_lane(resource, version)?;
            let profile = profile_by_version(version).ok_or(DamageV1Error::Profile)?;
            let decoded = match profile.transport {
                TransportFamily::Eh72Replicated | TransportFamily::Eh72HierarchicalRepetition
                    if entry.bytes.len() == EH_UNIT_BYTES =>
                {
                    let encoded: [u8; EH_UNIT_BYTES] = entry.bytes.as_slice().try_into().unwrap();
                    decode_eh_unit(
                        &EhObservation {
                            encoded,
                            erasures: Vec::new(),
                        },
                        version,
                    )
                    .ok()
                }
                TransportFamily::Rs255_191 if entry.bytes.len() == RS_CODEWORD_BYTES => {
                    decode_rs_unit(&entry.bytes, &[], version).ok()
                }
                _ => None,
            };
            if let Some(decoded) = decoded {
                output
                    .entry(entry.physical_unit_id)
                    .or_default()
                    .push(LocalCandidate {
                        profile_version: version,
                        common: decoded.common,
                        quality: decoded.quality,
                    });
            }
        }
    }
    Ok(output)
}

fn recover_group(
    entries: &BTreeMap<u32, LaneInput>,
    first_id: u32,
    factor: u8,
    expected: GroupIdentity,
    resource: &mut ResourceProjection,
) -> Result<GroupRecovery> {
    if !matches!(factor, 1 | 2 | 5) {
        return Err(DamageV1Error::Reconstruction);
    }
    let mut observations = Vec::with_capacity(usize::from(factor));
    let mut present_without_eh = Vec::with_capacity(usize::from(factor));
    for lane in 0..u32::from(factor) {
        let id = first_id
            .checked_add(lane)
            .ok_or(DamageV1Error::ResourceLimit)?;
        let row = entries.get(&id);
        observations.push(row.and_then(|row| row.observation.clone()));
        present_without_eh.push(row.is_some_and(|row| row.present && row.observation.is_none()));
    }
    if factor > 1
        && (0..u32::from(factor)).any(|lane| {
            entries
                .get(&(first_id + lane))
                .is_some_and(|row| row.present)
        })
    {
        charge_repetition_group(resource)?;
    }
    let profile = profile_by_version(PROFILE_V7).ok_or(DamageV1Error::Profile)?;
    let diagnostic = diagnose_hierarchical_eh_group(profile, &observations)
        .map_err(|_| DamageV1Error::Reconstruction)?;
    let mut lane_states = Vec::with_capacity(diagnostic.lanes.len());
    for (lane_index, lane) in diagnostic.lanes.into_iter().enumerate() {
        let agrees = lane
            .common
            .and_then(|common| GroupIdentity::from_common(&common).ok())
            == Some(expected);
        lane_states.push(if present_without_eh[lane_index] {
            FragmentState::Corrupt
        } else {
            match lane.state {
                HierarchicalLaneState::Absent => FragmentState::Missing,
                HierarchicalLaneState::Corrupt => FragmentState::Corrupt,
                HierarchicalLaneState::Verified if agrees => FragmentState::Verified,
                HierarchicalLaneState::Recovered if agrees => FragmentState::Recovered,
                HierarchicalLaneState::Verified | HierarchicalLaneState::Recovered => {
                    FragmentState::Corrupt
                }
            }
        });
    }
    let common_agrees = diagnostic
        .common
        .and_then(|common| GroupIdentity::from_common(&common).ok())
        == Some(expected);
    let state = match diagnostic.state {
        HierarchicalGroupState::Missing if present_without_eh.iter().any(|value| *value) => {
            FragmentState::Corrupt
        }
        HierarchicalGroupState::Missing => FragmentState::Missing,
        HierarchicalGroupState::Corrupt => FragmentState::Corrupt,
        HierarchicalGroupState::Conflict => FragmentState::Ambiguous,
        HierarchicalGroupState::Verified if common_agrees => FragmentState::Verified,
        HierarchicalGroupState::Recovered if common_agrees => FragmentState::Recovered,
        HierarchicalGroupState::Verified | HierarchicalGroupState::Recovered => {
            FragmentState::Corrupt
        }
    };
    Ok(GroupRecovery {
        identity: expected,
        first_id,
        factor,
        state,
        common: common_agrees.then_some(diagnostic.common).flatten(),
        lane_states,
    })
}

fn assemble_raw_fragment_bytes(groups: &[GroupRecovery]) -> Option<Vec<u8>> {
    let first = groups.first()?;
    let count = usize::from(first.identity.fragment_count);
    if groups.len() != count
        || groups.iter().enumerate().any(|(index, group)| {
            group.identity.fragment_index as usize != index
                || group.identity.section_id != first.identity.section_id
                || group.identity.section_type != first.identity.section_type
                || group.identity.section_version != first.identity.section_version
                || group.identity.fragment_count != first.identity.fragment_count
                || group.identity.section_envelope_length != first.identity.section_envelope_length
                || group.common.is_none()
        })
    {
        return None;
    }
    let envelope_length = usize::try_from(first.identity.section_envelope_length).ok()?;
    let mut raw = Vec::with_capacity(envelope_length);
    for group in groups {
        let block = decode_common_block(group.common.as_ref()?, PROFILE_V7).ok()?;
        raw.extend_from_slice(&block.payload);
    }
    (raw.len() == envelope_length).then_some(raw)
}

fn structurally_attemptable(raw: &[u8]) -> bool {
    if raw.len() < 22 || raw.len() > MAX_ENVELOPE_BYTES || raw[..2] != [0, 0] {
        return false;
    }
    let check_bytes = match raw[11] {
        1 => 4_usize,
        2 => 8_usize,
        _ => return false,
    };
    let dependencies = usize::from(u16::from_be_bytes([raw[12], raw[13]]));
    let payload = usize::try_from(u32::from_be_bytes(raw[14..18].try_into().unwrap())).ok();
    18_usize
        .checked_add(dependencies.checked_mul(4).unwrap_or(usize::MAX))
        .and_then(|value| value.checked_add(payload?))
        .and_then(|value| value.checked_add(check_bytes))
        == Some(raw.len())
}

fn checked_section_from_groups(
    groups: &[GroupRecovery],
    inventory: Option<&Inventory>,
    resource: &mut ResourceProjection,
) -> Result<Option<SectionResult>> {
    let Some(raw) = assemble_raw_fragment_bytes(groups) else {
        return Ok(None);
    };
    if !structurally_attemptable(&raw) {
        return Ok(None);
    }
    charge_section_attempt(resource)?;
    let Ok(envelope) = decode_section(&raw) else {
        return Ok(None);
    };
    if inventory
        .is_some_and(|inventory| validate_envelope_against_inventory(&envelope, inventory).is_err())
    {
        return Ok(None);
    }
    let recovered = groups
        .iter()
        .any(|group| group.state == FragmentState::Recovered);
    Ok(Some(SectionResult {
        section_id: envelope.section_id,
        state: if recovered {
            SectionState::Recovered
        } else {
            SectionState::Verified
        },
        envelope: Some(raw),
    }))
}

fn bootstrap_inventory_groups(
    entries: &BTreeMap<u32, LaneInput>,
    resource: &mut ResourceProjection,
) -> Result<Vec<GroupRecovery>> {
    let initial = GroupIdentity {
        section_id: 1,
        section_type: SECTION_INVENTORY,
        section_version: 1,
        fragment_index: 0,
        fragment_count: 1,
        section_envelope_length: 1,
    };
    // The first group establishes the two variable shape fields.  Identity
    // fields fixed by the route are checked before those fields are trusted.
    let mut observations = Vec::with_capacity(5);
    let mut present_without_eh = Vec::with_capacity(5);
    for id in 1_u32..=5 {
        let row = entries.get(&id);
        observations.push(row.and_then(|row| row.observation.clone()));
        present_without_eh.push(row.is_some_and(|row| row.present && row.observation.is_none()));
    }
    if (1_u32..=5).any(|id| entries.get(&id).is_some_and(|row| row.present)) {
        charge_repetition_group(resource)?;
    }
    let profile = profile_by_version(PROFILE_V7).ok_or(DamageV1Error::Profile)?;
    let diagnostic = diagnose_hierarchical_eh_group(profile, &observations)
        .map_err(|_| DamageV1Error::Reconstruction)?;
    let Some(common) = diagnostic.common else {
        let state = match diagnostic.state {
            HierarchicalGroupState::Missing if present_without_eh.iter().any(|value| *value) => {
                FragmentState::Corrupt
            }
            HierarchicalGroupState::Missing => FragmentState::Missing,
            HierarchicalGroupState::Conflict => FragmentState::Ambiguous,
            _ => FragmentState::Corrupt,
        };
        return Ok(vec![GroupRecovery {
            identity: initial,
            first_id: 1,
            factor: 5,
            state,
            common: None,
            lane_states: diagnostic
                .lanes
                .iter()
                .enumerate()
                .map(|(lane_index, lane)| {
                    if present_without_eh[lane_index] {
                        return FragmentState::Corrupt;
                    }
                    match lane.state {
                        HierarchicalLaneState::Absent => FragmentState::Missing,
                        HierarchicalLaneState::Corrupt => FragmentState::Corrupt,
                        HierarchicalLaneState::Verified => FragmentState::Verified,
                        HierarchicalLaneState::Recovered => FragmentState::Recovered,
                    }
                })
                .collect(),
        }]);
    };
    let identity = GroupIdentity::from_common(&common)?;
    if identity.section_id != 1
        || identity.section_type != SECTION_INVENTORY
        || identity.section_version != 1
        || identity.fragment_index != 0
        || identity.fragment_count == 0
        || usize::from(identity.fragment_count) > MAX_BLOCKS_PER_COPY
        || identity.section_envelope_length as usize > MAX_ENVELOPE_BYTES
    {
        return Ok(vec![GroupRecovery {
            identity,
            first_id: 1,
            factor: 5,
            state: FragmentState::Corrupt,
            common: None,
            lane_states: vec![FragmentState::Corrupt; 5],
        }]);
    }
    let mut output = Vec::with_capacity(usize::from(identity.fragment_count));
    let lane_states = diagnostic
        .lanes
        .iter()
        .map(|lane| {
            let agrees = lane
                .common
                .and_then(|common| GroupIdentity::from_common(&common).ok())
                == Some(identity);
            match lane.state {
                HierarchicalLaneState::Absent => FragmentState::Missing,
                HierarchicalLaneState::Corrupt => FragmentState::Corrupt,
                HierarchicalLaneState::Verified if agrees => FragmentState::Verified,
                HierarchicalLaneState::Recovered if agrees => FragmentState::Recovered,
                HierarchicalLaneState::Verified | HierarchicalLaneState::Recovered => {
                    FragmentState::Corrupt
                }
            }
        })
        .collect();
    output.push(GroupRecovery {
        identity,
        first_id: 1,
        factor: 5,
        state: match diagnostic.state {
            HierarchicalGroupState::Verified => FragmentState::Verified,
            HierarchicalGroupState::Recovered => FragmentState::Recovered,
            HierarchicalGroupState::Conflict => FragmentState::Ambiguous,
            HierarchicalGroupState::Missing => FragmentState::Missing,
            HierarchicalGroupState::Corrupt => FragmentState::Corrupt,
        },
        common: Some(common),
        lane_states,
    });
    for fragment_index in 1..identity.fragment_count {
        let expected = GroupIdentity {
            fragment_index,
            ..identity
        };
        output.push(recover_group(
            entries,
            1_u32
                .checked_add(u32::from(fragment_index) * 5)
                .ok_or(DamageV1Error::ResourceLimit)?,
            5,
            expected,
            resource,
        )?);
    }
    Ok(output)
}

fn groups_from_layout(
    entries: &BTreeMap<u32, LaneInput>,
    layout: &BTreeMap<u32, ExpectedLane>,
    resource: &mut ResourceProjection,
) -> Result<Vec<GroupRecovery>> {
    let mut groups = Vec::new();
    for (&id, lane) in layout {
        if lane.replica_index != 0 || lane.identity.section_id == 1 {
            continue;
        }
        groups.push(recover_group(
            entries,
            id,
            u8::try_from(lane.physical_replica_count).map_err(|_| DamageV1Error::Reconstruction)?,
            lane.identity,
            resource,
        )?);
    }
    Ok(groups)
}

fn foreign_or_local_candidate<'a>(
    candidates: &'a BTreeMap<u32, Vec<LocalCandidate>>,
    id: u32,
) -> Option<&'a LocalCandidate> {
    let rows = candidates.get(&id)?;
    (rows.len() == 1).then(|| &rows[0])
}

fn candidate_matches_expected(
    candidate: &LocalCandidate,
    block: &crate::CommonBlock,
    expected: ExpectedLane,
) -> bool {
    candidate.profile_version == PROFILE_V7
        && block.profile_version == PROFILE_V7
        && block.semantic_copy_id == 0
        && block.section_id == expected.identity.section_id
        && block.section_type == expected.identity.section_type
        && block.section_version == expected.identity.section_version
        && block.fragment_index == expected.identity.fragment_index
        && block.fragment_count == expected.identity.fragment_count
        && block.section_envelope_length == expected.identity.section_envelope_length
}

fn diagnostic_hash(
    state: FragmentState,
    source: Option<&(&LocalCandidate, crate::CommonBlock)>,
) -> String {
    if matches!(state, FragmentState::Verified | FragmentState::Recovered) {
        source.map_or_else(
            || ZERO_SHA256.to_owned(),
            |(candidate, _)| format!("{:x}", Sha256::digest(candidate.common)),
        )
    } else {
        ZERO_SHA256.to_owned()
    }
}

fn diagnostics_with_layout(
    entries: &BTreeMap<u32, LaneInput>,
    local: &BTreeMap<u32, Vec<LocalCandidate>>,
    layout: &BTreeMap<u32, ExpectedLane>,
    groups: &[GroupRecovery],
) -> Vec<FragmentDiagnosticV1> {
    let group_by_id = groups
        .iter()
        .flat_map(|group| {
            (0..u32::from(group.factor)).map(move |lane| (group.first_id + lane, (group, lane)))
        })
        .collect::<BTreeMap<_, _>>();
    let ids = layout
        .keys()
        .chain(entries.keys())
        .copied()
        .collect::<BTreeSet<_>>();
    ids.into_iter()
        .map(|id| {
            let expected = layout.get(&id).copied();
            let group_lane = group_by_id.get(&id).copied();
            let local_candidate = foreign_or_local_candidate(local, id);
            let source = local_candidate.and_then(|candidate| {
                decode_common_block(&candidate.common, candidate.profile_version)
                    .ok()
                    .map(|block| (candidate, block))
            });
            // A group-level conflict is a logical aggregation result.  It
            // must not erase the independently checked state/hash of any
            // physical lane that supplied one of the conflicting values.
            let v7_lane_state = group_lane.map_or(FragmentState::Unknown, |(group, lane)| {
                group.lane_states[lane as usize]
            });
            let source_matches_expected = expected.is_some_and(|expected| {
                source.as_ref().is_some_and(|(candidate, block)| {
                    candidate_matches_expected(candidate, block, expected)
                })
            });
            let state = match (expected, entries.contains_key(&id)) {
                (Some(_), false) => FragmentState::Missing,
                (Some(_), true) if source.is_some() && !source_matches_expected => {
                    FragmentState::Corrupt
                }
                (Some(_), true) => v7_lane_state,
                (None, true) => source
                    .as_ref()
                    .map_or(FragmentState::Corrupt, |(candidate, _)| {
                        match candidate.quality {
                            DecodeQuality::Verified => FragmentState::Verified,
                            DecodeQuality::Recovered => FragmentState::Recovered,
                        }
                    }),
                (None, false) => FragmentState::Unknown,
            };
            let (section_id, semantic_copy_id, fragment_index) = expected
                .map(|row| (row.identity.section_id, 0, row.identity.fragment_index))
                .or_else(|| {
                    source.as_ref().map(|(_, block)| {
                        (
                            block.section_id,
                            block.semantic_copy_id,
                            block.fragment_index,
                        )
                    })
                })
                .unwrap_or((0, ABSENT_U16, ABSENT_U16));
            FragmentDiagnosticV1 {
                input_id: id,
                profile_version: expected.map_or_else(
                    || {
                        source
                            .as_ref()
                            .map(|(candidate, _)| candidate.profile_version)
                    },
                    |_| Some(PROFILE_V7),
                ),
                section_id,
                semantic_copy_id,
                fragment_index,
                replica_index: expected.map_or(ABSENT_U16, |row| row.replica_index),
                physical_replica_count: expected
                    .map_or(ABSENT_U16, |row| row.physical_replica_count),
                state,
                common_block_sha256: diagnostic_hash(state, source.as_ref()),
            }
        })
        .collect()
}

fn diagnostics_without_inventory(
    entries: &BTreeMap<u32, LaneInput>,
    local: &BTreeMap<u32, Vec<LocalCandidate>>,
    bootstrap_groups: &[GroupRecovery],
) -> Vec<FragmentDiagnosticV1> {
    let ids = entries
        .keys()
        .copied()
        .chain(1_u32..=5)
        .collect::<BTreeSet<_>>();
    ids.into_iter()
        .map(|id| {
            let source = foreign_or_local_candidate(local, id).and_then(|candidate| {
                decode_common_block(&candidate.common, candidate.profile_version)
                    .ok()
                    .map(|block| (candidate, block))
            });
            let route_lane = (1..=5).contains(&id);
            let route_lane_missing = route_lane && !entries.contains_key(&id);
            let lane = usize::try_from(id.saturating_sub(1)).ok();
            let state = if !entries.contains_key(&id) {
                FragmentState::Missing
            } else if local.get(&id).is_some_and(|rows| rows.len() > 1) {
                FragmentState::Ambiguous
            } else if route_lane
                && source
                    .as_ref()
                    .is_some_and(|(candidate, _)| candidate.profile_version != PROFILE_V7)
            {
                match source.as_ref().unwrap().0.quality {
                    DecodeQuality::Verified => FragmentState::Verified,
                    DecodeQuality::Recovered => FragmentState::Recovered,
                }
            } else if route_lane {
                bootstrap_groups
                    .first()
                    .and_then(|group| lane.and_then(|lane| group.lane_states.get(lane).copied()))
                    .unwrap_or(FragmentState::Corrupt)
            } else if let Some((candidate, _)) = source.as_ref() {
                match candidate.quality {
                    DecodeQuality::Verified => FragmentState::Verified,
                    DecodeQuality::Recovered => FragmentState::Recovered,
                }
            } else {
                FragmentState::Corrupt
            };
            let (profile_version, section_id, semantic_copy_id, fragment_index) = source
                .as_ref()
                .map(|(candidate, block)| {
                    (
                        Some(candidate.profile_version),
                        block.section_id,
                        block.semantic_copy_id,
                        block.fragment_index,
                    )
                })
                .unwrap_or_else(|| {
                    if route_lane_missing {
                        // Even without an inventory, the v7 route fixes IDs
                        // 1..=5 as the five physical lanes of section 1,
                        // fragment 0.  Missing inputs therefore retain this
                        // known identity; corrupt present bytes do not acquire
                        // an identity that was never locally checked.
                        (Some(PROFILE_V7), 1, 0, 0)
                    } else {
                        (None, 0, ABSENT_U16, ABSENT_U16)
                    }
                });
            FragmentDiagnosticV1 {
                input_id: id,
                profile_version,
                section_id,
                semantic_copy_id,
                fragment_index,
                replica_index: if route_lane {
                    u16::try_from(id - 1).unwrap()
                } else {
                    ABSENT_U16
                },
                physical_replica_count: if route_lane { 5 } else { ABSENT_U16 },
                state,
                common_block_sha256: diagnostic_hash(state, source.as_ref()),
            }
        })
        .collect()
}

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
struct DiscoveredCopyKey {
    profile_version: u16,
    section_id: u32,
    semantic_copy_id: u16,
}

fn quality_witness(quality: DecodeQuality, common: [u8; 191]) -> FragmentWitness {
    FragmentWitness {
        raw_block: common,
        quality: match quality {
            DecodeQuality::Verified => RecoveryQuality::Verified,
            DecodeQuality::Recovered => RecoveryQuality::Recovered,
        },
    }
}

/// Reconstruct the exact candidate bytes before comparing the stored section
/// check.  This deliberately duplicates only the bounded structural half of
/// `assemble_semantic_copy`: it lets the resource ledger charge a complete,
/// width-consistent candidate immediately before the stored-check comparison.
fn structurally_complete_discovered_envelope(
    witnesses: &[FragmentWitness],
    profile_version: u16,
) -> Option<Vec<u8>> {
    if witnesses.is_empty() || witnesses.len() > MAX_BLOCKS_PER_COPY {
        return None;
    }
    let mut identity: Option<(u32, u16, u16, u16, u16, u32)> = None;
    let mut blocks = BTreeMap::<u16, crate::CommonBlock>::new();
    for witness in witnesses {
        let block = decode_common_block(&witness.raw_block, profile_version).ok()?;
        let current = (
            block.section_id,
            block.semantic_copy_id,
            block.section_type,
            block.section_version,
            block.fragment_count,
            block.section_envelope_length,
        );
        if identity.is_some_and(|value| value != current) {
            return None;
        }
        identity = Some(current);
        match blocks.get(&block.fragment_index) {
            Some(previous) if previous != &block => return None,
            Some(_) => {}
            None => {
                blocks.insert(block.fragment_index, block);
            }
        }
    }
    let (_, _, _, _, fragment_count, envelope_length) = identity?;
    if fragment_count == 0
        || usize::from(fragment_count) > MAX_BLOCKS_PER_COPY
        || blocks.len() != usize::from(fragment_count)
        || blocks.keys().copied().ne(0..fragment_count)
    {
        return None;
    }
    let envelope_length = usize::try_from(envelope_length).ok()?;
    let mut raw = Vec::with_capacity(envelope_length);
    for (_, block) in blocks {
        raw.extend_from_slice(&block.payload);
    }
    (raw.len() == envelope_length).then_some(raw)
}

fn discovered_sections_without_inventory(
    local: &BTreeMap<u32, Vec<LocalCandidate>>,
    bootstrap_groups: &[GroupRecovery],
    attempted_envelopes: &mut BTreeSet<Vec<u8>>,
    resource: &mut ResourceProjection,
) -> Result<Vec<SectionResult>> {
    let mut copies = BTreeMap::<DiscoveredCopyKey, Vec<FragmentWitness>>::new();
    for candidates in local.values() {
        let [candidate] = candidates.as_slice() else {
            continue;
        };
        let Ok(block) = decode_common_block(&candidate.common, candidate.profile_version) else {
            continue;
        };
        // Section 1 is recoverable only through its route-fixed REP5 groups;
        // treating physical lanes as semantic fragments would let a valid
        // conflict be hidden by duplicate selection.
        if candidate.profile_version == PROFILE_V7 && block.section_id == 1 {
            continue;
        }
        copies
            .entry(DiscoveredCopyKey {
                profile_version: candidate.profile_version,
                section_id: block.section_id,
                semantic_copy_id: block.semantic_copy_id,
            })
            .or_default()
            .push(quality_witness(candidate.quality, candidate.common));
    }
    for group in bootstrap_groups {
        let Some(common) = group.common else {
            continue;
        };
        if !matches!(
            group.state,
            FragmentState::Verified | FragmentState::Recovered
        ) {
            continue;
        }
        copies
            .entry(DiscoveredCopyKey {
                profile_version: PROFILE_V7,
                section_id: 1,
                semantic_copy_id: 0,
            })
            .or_default()
            .push(quality_witness(
                if group.state == FragmentState::Verified {
                    DecodeQuality::Verified
                } else {
                    DecodeQuality::Recovered
                },
                common,
            ));
    }

    let mut by_section = BTreeMap::<u32, Vec<SectionWitness>>::new();
    for (key, witnesses) in copies {
        let Some(raw) = structurally_complete_discovered_envelope(&witnesses, key.profile_version)
        else {
            continue;
        };
        if !structurally_attemptable(&raw) {
            continue;
        }
        if attempted_envelopes.insert(raw) {
            charge_section_attempt(resource)?;
        }
        let Ok(witness) = assemble_semantic_copy(&witnesses, key.profile_version) else {
            continue;
        };
        if by_section.values().map(Vec::len).sum::<usize>() >= MAX_SECTION_CANDIDATES {
            return Err(DamageV1Error::ResourceLimit);
        }
        by_section.entry(key.section_id).or_default().push(witness);
    }

    let mut sections = Vec::with_capacity(by_section.len());
    for (section_id, witnesses) in by_section {
        match aggregate_section_witnesses(&witnesses) {
            Ok(section) => sections.push(SectionResult {
                section_id,
                state: if section.quality == RecoveryQuality::Verified {
                    SectionState::Verified
                } else {
                    SectionState::Recovered
                },
                envelope: Some(section.envelope),
            }),
            Err(error) if error.code == crate::RejectCode::Ambiguous => {
                sections.push(SectionResult {
                    section_id,
                    state: SectionState::Ambiguous,
                    envelope: None,
                });
            }
            Err(error) if error.code == crate::RejectCode::ResourceLimit => {
                return Err(DamageV1Error::ResourceLimit);
            }
            Err(_) => return Err(DamageV1Error::Reconstruction),
        }
    }
    Ok(sections)
}

fn recover_all_sections(
    inventory: &Inventory,
    groups: &[GroupRecovery],
    inventory_result: &SectionResult,
    resource: &mut ResourceProjection,
) -> Result<Vec<SectionResult>> {
    let mut by_section = BTreeMap::<u32, Vec<GroupRecovery>>::new();
    for group in groups {
        by_section
            .entry(group.identity.section_id)
            .or_default()
            .push(group.clone());
    }
    let mut sections = Vec::with_capacity(inventory.entries.len());
    for entry in &inventory.entries {
        if entry.section_id == 1 {
            sections.push(inventory_result.clone());
            continue;
        }
        let groups = by_section.remove(&entry.section_id).unwrap_or_default();
        if groups
            .iter()
            .any(|group| group.state == FragmentState::Ambiguous)
        {
            sections.push(SectionResult {
                section_id: entry.section_id,
                state: SectionState::Corrupt,
                envelope: None,
            });
            continue;
        }
        if let Some(result) = checked_section_from_groups(&groups, Some(inventory), resource)? {
            sections.push(result);
            continue;
        }
        let state = if groups
            .iter()
            .any(|group| group.state == FragmentState::Corrupt)
        {
            SectionState::Corrupt
        } else if groups.len()
            != usize::try_from(section_envelope_length(entry)?.div_ceil(COMMON_PAYLOAD_BYTES))
                .map_err(|_| DamageV1Error::ResourceLimit)?
            || groups
                .iter()
                .any(|group| group.state == FragmentState::Missing)
        {
            SectionState::Incomplete
        } else {
            SectionState::Corrupt
        };
        sections.push(SectionResult {
            section_id: entry.section_id,
            state,
            envelope: None,
        });
    }
    Ok(sections)
}

fn recovered_stream_unchecked(result: &RecoveryResultV1, tier_id: u32) -> Option<Vec<u8>> {
    let sections = result
        .sections
        .iter()
        .filter_map(|row| row.envelope.as_ref())
        .filter_map(|raw| decode_section(raw).ok())
        .map(|row| (row.section_id, row))
        .collect::<BTreeMap<_, _>>();
    let inventory = sections
        .get(&1)
        .and_then(|section| decode_inventory(&section.payload).ok())?;
    let tier_section = sections.get(&tier_id)?;
    let tier = decode_tier_frame(&tier_section.payload, tier_id).ok()?;
    validate_tier_against_inventory(&tier, tier_section, &inventory).ok()?;
    let bodies = tier
        .body_section_ids
        .iter()
        .map(|id| {
            sections
                .get(id)
                .map(|section| (*id, section.payload.clone()))
        })
        .collect::<Option<BTreeMap<_, _>>>()?;
    assemble_content_stream(&tier, &bodies).ok()
}

fn recovered_stream(result: &RecoveryResultV1, tier_id: u32) -> Option<Vec<u8>> {
    // The all-tier stream is a refinement of the required-tier stream.  A
    // separately checked tier-3 reconstruction therefore cannot establish
    // availability when tier 2 is unavailable.
    if tier_id == 3 && recovered_stream_unchecked(result, 2).is_none() {
        return None;
    }
    recovered_stream_unchecked(result, tier_id)
}

fn artifact_state(sections: &[SectionResult], inventory: &Inventory) -> ArtifactState {
    if sections
        .iter()
        .any(|section| section.state == SectionState::Ambiguous)
    {
        return ArtifactState::Ambiguous;
    }
    let states = sections
        .iter()
        .map(|row| (row.section_id, row.state))
        .collect::<BTreeMap<_, _>>();
    let required_unavailable = inventory.entries.iter().any(|entry| {
        entry.closure_class == CLOSURE_M2_REQUIRED
            && !states.get(&entry.section_id).is_some_and(|state| {
                matches!(state, SectionState::Verified | SectionState::Recovered)
            })
    });
    if required_unavailable {
        ArtifactState::Failure
    } else if inventory.entries.iter().any(|entry| {
        !states
            .get(&entry.section_id)
            .is_some_and(|state| matches!(state, SectionState::Verified | SectionState::Recovered))
    }) {
        ArtifactState::Degraded
    } else {
        ArtifactState::Exact
    }
}

fn recover_v7_inputs(
    entries: BTreeMap<u32, LaneInput>,
    local: BTreeMap<u32, Vec<LocalCandidate>>,
    mut resource: ResourceProjection,
    accepted_hypotheses: Vec<AcceptedHypothesis>,
) -> Result<RecoveryResultV1> {
    let bootstrap_groups = bootstrap_inventory_groups(&entries, &mut resource)?;
    let bootstrap_attempt =
        assemble_raw_fragment_bytes(&bootstrap_groups).filter(|raw| structurally_attemptable(raw));
    let inventory_section = checked_section_from_groups(&bootstrap_groups, None, &mut resource)?;
    let inventory = inventory_section
        .as_ref()
        .and_then(|section| section.envelope.as_ref())
        .and_then(|raw| decode_section(raw).ok())
        .and_then(|section| decode_inventory(&section.payload).ok());
    let Some(inventory) = inventory else {
        let mut attempted_envelopes = bootstrap_attempt.into_iter().collect::<BTreeSet<_>>();
        let mut sections = discovered_sections_without_inventory(
            &local,
            &bootstrap_groups,
            &mut attempted_envelopes,
            &mut resource,
        )?;
        if !sections.iter().any(|section| section.section_id == 1) {
            let state = if bootstrap_groups.iter().any(|group| {
                matches!(
                    group.state,
                    FragmentState::Corrupt | FragmentState::Ambiguous
                )
            }) {
                SectionState::Corrupt
            } else if bootstrap_groups
                .iter()
                .any(|group| group.state == FragmentState::Missing)
            {
                SectionState::Incomplete
            } else {
                // Every fragment was locally recoverable, so failure to
                // establish a checked inventory is a semantic/check failure.
                SectionState::Corrupt
            };
            sections.push(SectionResult {
                section_id: 1,
                state,
                envelope: None,
            });
        }
        sections.sort_by_key(|section| section.section_id);
        let artifact_state = if sections
            .iter()
            .any(|section| section.state == SectionState::Ambiguous)
        {
            ArtifactState::Ambiguous
        } else {
            ArtifactState::Failure
        };
        return Ok(RecoveryResultV1 {
            profile_version: None,
            inventory_established: false,
            resource,
            artifact_state,
            sections,
            fragments: diagnostics_without_inventory(&entries, &local, &bootstrap_groups),
            accepted_hypotheses,
        });
    };
    let inventory_result = inventory_section.ok_or(DamageV1Error::Reconstruction)?;
    let layout = inventory_layout(&inventory)?;
    if layout.len() > 1_841 || layout.keys().next_back().copied().unwrap_or(0) > 1_841 {
        return Err(DamageV1Error::Reconstruction);
    }
    let mut groups = bootstrap_groups;
    groups.extend(groups_from_layout(&entries, &layout, &mut resource)?);
    let sections = recover_all_sections(&inventory, &groups, &inventory_result, &mut resource)?;
    let mut result = RecoveryResultV1 {
        profile_version: Some(PROFILE_V7),
        inventory_established: true,
        resource,
        artifact_state: artifact_state(&sections, &inventory),
        sections,
        fragments: diagnostics_with_layout(&entries, &local, &layout, &groups),
        accepted_hypotheses,
    };
    if recovered_stream(&result, 2).is_none() {
        result.artifact_state = ArtifactState::Failure;
    } else if recovered_stream(&result, 3).is_none()
        && result.artifact_state == ArtifactState::Exact
    {
        result.artifact_state = ArtifactState::Degraded;
    }
    Ok(result)
}

/// Decode a v1 OBS_UNITS frame using only its unit IDs/bytes and tracked
/// candidate-neutral registry code.  Arrival order is ignored after the
/// closed parser has rejected duplicate IDs.
pub fn decode_units_v1(raw: &[u8]) -> Result<RecoveryResultV1> {
    verify_promoted_decoder_owners()?;
    let units = ObsUnits::parse(raw).map_err(|error| match error {
        crate::damage::DamageError::ResourceLimit => DamageV1Error::ResourceLimit,
        _ => DamageV1Error::Observation,
    })?;
    let mut resource = ResourceProjection::default();
    let local = decode_local_candidates(&units, &mut resource)?;
    let entries = units
        .entries
        .iter()
        .map(|entry| {
            let observation = (entry.bytes.len() == EH_UNIT_BYTES).then(|| EhObservation {
                encoded: entry.bytes.as_slice().try_into().expect("length checked"),
                erasures: Vec::new(),
            });
            (
                entry.physical_unit_id,
                LaneInput {
                    present: true,
                    observation,
                },
            )
        })
        .collect::<BTreeMap<_, _>>();
    recover_v7_inputs(entries, local, resource, Vec::new())
}

fn observed_coordinate(
    side: usize,
    transform: u8,
    row: usize,
    column: usize,
) -> Result<(usize, usize)> {
    if side == 0 || row >= side || column >= side || transform > 7 {
        return Err(DamageV1Error::Observation);
    }
    let last = side - 1;
    Ok(match transform {
        0 => (row, column),
        1 => (last - column, row),
        2 => (last - row, last - column),
        3 => (column, last - row),
        4 => (row, last - column),
        5 => (last - column, last - row),
        6 => (last - row, column),
        7 => (column, row),
        _ => unreachable!(),
    })
}

fn matrix_view_may_have_v1_route(
    observed: &ObsMatrix,
    transform: u8,
    polarity: u8,
) -> Result<bool> {
    let maximum = 128.min(observed.side.saturating_sub(8) / 2);
    for width in (8..=maximum).step_by(8) {
        for sector in 0..4 {
            let mut matches = true;
            for bit in 0..256 {
                let (row, column) = sector_cell_at(observed.side, width, sector, bit)
                    .map_err(|_| DamageV1Error::Observation)?;
                let (observed_row, observed_column) =
                    observed_coordinate(observed.side, transform, row, column)?;
                let value = matrix_value(observed, observed_row, observed_column)?;
                let expected = (CALIBRATIONS[usize::from(sector)][bit / 8] >> (7 - bit % 8)) & 1;
                if value == 2 || value ^ polarity != expected {
                    matches = false;
                    break;
                }
            }
            if matches {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

fn extract_matrix_inputs(
    matrix: &ObsMatrix,
    map: HierarchicalMap,
) -> Result<(BTreeMap<u32, LaneInput>, BTreeMap<u32, Vec<LocalCandidate>>)> {
    let mut inputs = BTreeMap::new();
    let mut local = BTreeMap::<u32, Vec<LocalCandidate>>::new();
    for physical_ordinal in 0..map.unit_slot_count {
        let id = u32::try_from(physical_ordinal + 1).map_err(|_| DamageV1Error::ResourceLimit)?;
        let mut encoded = [0_u8; EH_UNIT_BYTES];
        let mut erasures = Vec::new();
        for bit in 0..REPETITION_SYMBOLS_PER_GROUP {
            let physical = map
                .forward_unit_bit(
                    physical_ordinal,
                    u16::try_from(bit).map_err(|_| DamageV1Error::ResourceLimit)?,
                )
                .map_err(|_| DamageV1Error::Reconstruction)?;
            let (row, column) = map
                .matrix_cell(physical)
                .map_err(|_| DamageV1Error::Reconstruction)?;
            match matrix_value(matrix, usize::from(row), usize::from(column))? {
                0 => {}
                1 => encoded[bit as usize / 8] |= 1 << (7 - bit as usize % 8),
                2 => erasures.push(EhErasure {
                    codeword: u8::try_from(bit / 72).map_err(|_| DamageV1Error::ResourceLimit)?,
                    position: u8::try_from(bit % 72 + 1)
                        .map_err(|_| DamageV1Error::ResourceLimit)?,
                }),
                _ => return Err(DamageV1Error::Observation),
            }
        }
        let observation = EhObservation { encoded, erasures };
        if let Ok(decoded) = decode_eh_unit(&observation, PROFILE_V7) {
            local.entry(id).or_default().push(LocalCandidate {
                profile_version: PROFILE_V7,
                common: decoded.common,
                quality: decoded.quality,
            });
        }
        inputs.insert(
            id,
            LaneInput {
                present: true,
                observation: Some(observation),
            },
        );
    }
    Ok((inputs, local))
}

fn decode_canonical_matrix_v1(
    matrix: &ObsMatrix,
    transform_id: u8,
    polarity_id: u8,
) -> Result<RecoveryResultV1> {
    let mut resource = ResourceProjection::default();
    let route_rows = discover_routes_v1(matrix, &mut resource)?;
    let legacy_rows = crate::damage::discover_routes(matrix, &mut resource)
        .map_err(|error| match error {
            crate::damage::DamageError::ResourceLimit => DamageV1Error::ResourceLimit,
            _ => DamageV1Error::Observation,
        })?
        .into_iter()
        .filter(|route| (2..=6).contains(&route.profile_version))
        .collect::<Vec<_>>();
    if route_rows.is_empty() && legacy_rows.is_empty() {
        return Err(DamageV1Error::Observation);
    }
    for route in &route_rows {
        for _ in 0..route.map.unit_slot_count {
            charge_registry_lane(&mut resource, PROFILE_V7)?;
        }
    }
    for route in &legacy_rows {
        let row = registry_resource_row(route.profile_version)?;
        let unit_count = route.map.population / REPETITION_SYMBOLS_PER_GROUP;
        checked_charge(
            &mut resource,
            row.primitive_steps,
            row.invocations_per_unit
                .checked_mul(unit_count)
                .ok_or(DamageV1Error::ResourceLimit)?,
            row.peak_scratch_bytes,
        )?;
    }
    let mut accepted_hypotheses = route_rows
        .iter()
        .map(|route| {
            Ok(AcceptedHypothesis {
                transform_id,
                polarity_id,
                sector_id: route.sector,
                profile_version: PROFILE_V7,
                mapping_sha256: mapping_sha256_v1(route.map)?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    accepted_hypotheses.extend(
        legacy_rows
            .iter()
            .map(|route| {
                Ok(AcceptedHypothesis {
                    transform_id,
                    polarity_id,
                    sector_id: route.sector,
                    profile_version: route.profile_version,
                    mapping_sha256: mapping_sha256_legacy(route.map)?,
                })
            })
            .collect::<Result<Vec<_>>>()?,
    );
    sort_and_dedup_accepted(&mut accepted_hypotheses)?;
    let mut claims = Vec::<(ParsedRouteV1, u64)>::new();
    for route in route_rows {
        if let Some((_, count)) = claims.iter_mut().find(|(prior, _)| {
            prior.width == route.width && prior.map == route.map && prior.package == route.package
        }) {
            *count = count.checked_add(1).ok_or(DamageV1Error::ResourceLimit)?;
        } else {
            claims.push((route, 1));
        }
    }
    let mut results = Vec::<RecoveryResultV1>::new();
    for (claim, accepted_path_count) in claims {
        let (inputs, local) = extract_matrix_inputs(matrix, claim.map)?;
        let result = recover_v7_inputs(inputs, local, ResourceProjection::default(), Vec::new())?;
        resource.primitive_steps = resource
            .primitive_steps
            .checked_add(
                result
                    .resource
                    .primitive_steps
                    .checked_mul(accepted_path_count)
                    .ok_or(DamageV1Error::ResourceLimit)?,
            )
            .ok_or(DamageV1Error::ResourceLimit)?;
        resource.peak_scratch_bytes = resource
            .peak_scratch_bytes
            .max(result.resource.peak_scratch_bytes);
        if !results.contains(&result) {
            results.push(result);
        }
    }
    let mut complete = Vec::new();
    for result in results.iter().filter(|result| result.inventory_established) {
        let mut normalized = result.clone();
        normalized.resource = ResourceProjection::default();
        normalized.accepted_hypotheses.clear();
        if !complete.contains(&normalized) {
            complete.push(normalized);
        }
    }
    match complete.len() {
        1 => {
            let mut result = complete.pop().unwrap();
            resource.section_attempts = results
                .iter()
                .find_map(|candidate| {
                    let mut normalized = candidate.clone();
                    normalized.resource = ResourceProjection::default();
                    normalized.accepted_hypotheses.clear();
                    (normalized == result).then_some(candidate.resource.section_attempts)
                })
                .ok_or(DamageV1Error::Reconstruction)?;
            result.resource = resource;
            result.accepted_hypotheses = accepted_hypotheses;
            Ok(result)
        }
        count if count > 1 => Ok(RecoveryResultV1 {
            profile_version: None,
            inventory_established: false,
            resource,
            artifact_state: ArtifactState::Ambiguous,
            sections: Vec::new(),
            fragments: Vec::new(),
            accepted_hypotheses,
        }),
        _ => match results.len() {
            0 => Ok(RecoveryResultV1 {
                profile_version: None,
                inventory_established: false,
                resource,
                artifact_state: ArtifactState::Failure,
                sections: Vec::new(),
                fragments: Vec::new(),
                accepted_hypotheses,
            }),
            1 => {
                let mut result = results.pop().unwrap();
                resource.section_attempts = result.resource.section_attempts;
                result.resource = resource;
                result.accepted_hypotheses = accepted_hypotheses;
                Ok(result)
            }
            _ => Ok(RecoveryResultV1 {
                profile_version: None,
                inventory_established: false,
                resource,
                artifact_state: ArtifactState::Ambiguous,
                sections: Vec::new(),
                fragments: Vec::new(),
                accepted_hypotheses,
            }),
        },
    }
}

pub fn decode_matrix_v1(raw: &[u8]) -> Result<RecoveryResultV1> {
    verify_promoted_decoder_owners()?;
    let observed = ObsMatrix::parse(raw).map_err(|error| match error {
        crate::damage::DamageError::ResourceLimit => DamageV1Error::ResourceLimit,
        _ => DamageV1Error::Observation,
    })?;
    let mut results = Vec::new();
    let mut resource_limit = false;
    for transform in 0..8 {
        for polarity in 0..2 {
            if !matrix_view_may_have_v1_route(&observed, transform, polarity)? {
                continue;
            }
            let mut values = vec![0_u8; observed.values.len()];
            for row in 0..observed.side {
                for column in 0..observed.side {
                    let (observed_row, observed_column) =
                        observed_coordinate(observed.side, transform, row, column)?;
                    let value = matrix_value(&observed, observed_row, observed_column)?;
                    values[row * observed.side + column] =
                        if value == 2 { 2 } else { value ^ polarity };
                }
            }
            let matrix = ObsMatrix {
                side: observed.side,
                values,
            };
            match decode_canonical_matrix_v1(&matrix, transform, polarity) {
                Ok(result) => results.push(result),
                Err(DamageV1Error::ResourceLimit) => resource_limit = true,
                Err(_) => {}
            }
        }
    }
    if resource_limit {
        return Err(DamageV1Error::ResourceLimit);
    }
    merge_view_results_v1(results)
}

fn parse_obs_bits_matrix(raw: &[u8]) -> Result<ObsMatrix> {
    if raw.len() < 5 {
        return Err(DamageV1Error::Observation);
    }
    let count = usize::try_from(u32::from_be_bytes(raw[..4].try_into().unwrap()))
        .map_err(|_| DamageV1Error::ResourceLimit)?;
    if count == 0 || count > MAX_RAW_BITS || raw.len() != 4 + count.div_ceil(8) {
        return Err(DamageV1Error::Observation);
    }
    let side = count.isqrt();
    if side == 0 || side > MAX_SIDE || side * side != count {
        return Err(DamageV1Error::Observation);
    }
    let used = count % 8;
    if used != 0
        && raw
            .last()
            .is_some_and(|byte| byte & ((1 << (8 - used)) - 1) != 0)
    {
        return Err(DamageV1Error::Observation);
    }
    let values = (0..count)
        .map(|bit| (raw[4 + bit / 8] >> (7 - bit % 8)) & 1)
        .collect();
    Ok(ObsMatrix { side, values })
}

pub fn decode_bits_v1(raw: &[u8]) -> Result<RecoveryResultV1> {
    verify_promoted_decoder_owners()?;
    let matrix = parse_obs_bits_matrix(raw)?;
    let mut serialized = u16::try_from(matrix.side)
        .map_err(|_| DamageV1Error::ResourceLimit)?
        .to_be_bytes()
        .to_vec();
    serialized.extend_from_slice(&matrix.values);
    decode_matrix_v1(&serialized)
}

fn merge_view_results_v1(mut results: Vec<RecoveryResultV1>) -> Result<RecoveryResultV1> {
    if results.is_empty() {
        return Err(DamageV1Error::Observation);
    }
    let mut resource = ResourceProjection::default();
    let mut accepted = Vec::new();
    for result in &results {
        resource.section_attempts = resource
            .section_attempts
            .checked_add(result.resource.section_attempts)
            .ok_or(DamageV1Error::ResourceLimit)?;
        resource.primitive_steps = resource
            .primitive_steps
            .checked_add(result.resource.primitive_steps)
            .ok_or(DamageV1Error::ResourceLimit)?;
        resource.peak_scratch_bytes = resource
            .peak_scratch_bytes
            .max(result.resource.peak_scratch_bytes);
        accepted.extend(result.accepted_hypotheses.iter().cloned());
    }
    sort_and_dedup_accepted(&mut accepted)?;
    let accepted_hypotheses = accepted;
    let mut complete = results
        .iter_mut()
        .filter(|result| result.inventory_established)
        .map(|result| {
            result.resource = ResourceProjection::default();
            result.accepted_hypotheses.clear();
            result.clone()
        })
        .collect::<Vec<_>>();
    complete.sort_by(|left, right| {
        let left = left
            .sections
            .iter()
            .filter_map(|row| row.envelope.as_ref())
            .flatten()
            .copied()
            .collect::<Vec<_>>();
        let right = right
            .sections
            .iter()
            .filter_map(|row| row.envelope.as_ref())
            .flatten()
            .copied()
            .collect::<Vec<_>>();
        left.cmp(&right)
    });
    complete.dedup();
    match complete.len() {
        0 => {
            let mut result = results.remove(0);
            result.profile_version = None;
            result.inventory_established = false;
            result.artifact_state = ArtifactState::Failure;
            result.resource = resource;
            result.accepted_hypotheses = accepted_hypotheses;
            Ok(result)
        }
        1 => {
            let mut result = complete.pop().unwrap();
            result.resource = resource;
            result.accepted_hypotheses = accepted_hypotheses;
            Ok(result)
        }
        _ => Ok(RecoveryResultV1 {
            profile_version: None,
            inventory_established: false,
            resource,
            artifact_state: ArtifactState::Ambiguous,
            sections: Vec::new(),
            fragments: Vec::new(),
            accepted_hypotheses,
        }),
    }
}

/// Close parser/decoder failure into the v1 artifact-state space.
pub fn decode_observation_v1(channel: &str, raw: &[u8]) -> RecoveryResultV1 {
    let decoded = match channel {
        "OBS_UNITS" => decode_units_v1(raw),
        "OBS_BITS" => decode_bits_v1(raw),
        "OBS_MATRIX" => decode_matrix_v1(raw),
        _ => Err(DamageV1Error::Channel),
    };
    decoded.unwrap_or_else(|error| {
        RecoveryResultV1::closed(
            if error == DamageV1Error::ResourceLimit {
                ArtifactState::ResourceLimit
            } else {
                ArtifactState::Failure
            },
            ResourceProjection::default(),
        )
    })
}

fn state_name(state: SectionState) -> &'static str {
    match state {
        SectionState::Verified => "verified",
        SectionState::Recovered => "recovered",
        SectionState::Incomplete => "incomplete",
        SectionState::Corrupt => "corrupt",
        SectionState::Ambiguous => "ambiguous",
        SectionState::Unknown => "unknown",
    }
}

fn fragment_state_name(state: FragmentState) -> &'static str {
    match state {
        FragmentState::Verified => "verified",
        FragmentState::Recovered => "recovered",
        FragmentState::Missing => "missing",
        FragmentState::Corrupt => "corrupt",
        FragmentState::Ambiguous => "ambiguous",
        FragmentState::Unknown => "unknown",
    }
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

fn canonical_array(rows: Vec<ManifestValue>) -> Result<Vec<u8>> {
    let wrapped = serialize_manifest(&object([("rows", ManifestValue::Array(rows))]))
        .map_err(|_| DamageV1Error::Reconstruction)?;
    const PREFIX: &[u8] = b"{\"rows\":";
    const SUFFIX: &[u8] = b"}\n";
    if !wrapped.starts_with(PREFIX) || !wrapped.ends_with(SUFFIX) {
        return Err(DamageV1Error::Reconstruction);
    }
    Ok(wrapped[PREFIX.len()..wrapped.len() - SUFFIX.len()].to_vec())
}

fn lower_hex_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn validate_result_v1_projection(result: &RecoveryResultV1) -> Result<()> {
    if result
        .profile_version
        .is_some_and(|version| version != PROFILE_V7)
        || result.inventory_established != (result.profile_version == Some(PROFILE_V7))
        || result
            .sections
            .windows(2)
            .any(|pair| pair[0].section_id >= pair[1].section_id)
        || result
            .fragments
            .windows(2)
            .any(|pair| pair[0].input_id >= pair[1].input_id)
        || !accepted_rows_strictly_sorted(&result.accepted_hypotheses)
        || result.sections.iter().any(|row| {
            row.envelope.is_some()
                != matches!(row.state, SectionState::Verified | SectionState::Recovered)
        })
        || result
            .fragments
            .iter()
            .any(|row| !lower_hex_sha256(&row.common_block_sha256))
        || result.fragments.iter().any(|row| {
            (row.common_block_sha256 != ZERO_SHA256)
                != matches!(
                    row.state,
                    FragmentState::Verified | FragmentState::Recovered
                )
        })
        || result
            .accepted_hypotheses
            .iter()
            .any(|row| !lower_hex_sha256(&row.mapping_sha256))
    {
        return Err(DamageV1Error::Reconstruction);
    }
    for row in &result.fragments {
        let replica_absent = row.replica_index == ABSENT_U16;
        let factor_absent = row.physical_replica_count == ABSENT_U16;
        if replica_absent != factor_absent
            || !factor_absent
                && (!matches!(row.physical_replica_count, 1 | 2 | 5)
                    || row.replica_index >= row.physical_replica_count)
            || !result.inventory_established
                && !factor_absent
                && (!(1..=5).contains(&row.input_id)
                    || row.physical_replica_count != 5
                    || row.replica_index != (row.input_id - 1) as u16)
        {
            return Err(DamageV1Error::Reconstruction);
        }
    }
    Ok(())
}

/// Render the exact promoted decoder-result/v1 schema.  Fragment rows include
/// physical lane metadata; the repetition candidate is intentionally absent.
pub fn render_decoder_result_v1(
    channel: &str,
    result: &RecoveryResultV1,
) -> Result<(Vec<u8>, String)> {
    if !matches!(channel, "OBS_BITS" | "OBS_MATRIX" | "OBS_UNITS") {
        return Err(DamageV1Error::Channel);
    }
    if channel == "OBS_UNITS" && !result.accepted_hypotheses.is_empty() {
        return Err(DamageV1Error::Reconstruction);
    }
    validate_result_v1_projection(result)?;
    let profile_id = result
        .profile_version
        .and_then(profile_by_version)
        .map_or("", |profile| profile.id);
    let section_rows = result.sections.iter().map(|row| {
        object([
            ("section_id", ManifestValue::U64(u64::from(row.section_id))),
            ("state", string(state_name(row.state))),
            (
                "semantic_sha256",
                string(
                    &row.envelope
                        .as_ref()
                        .map_or_else(|| ZERO_SHA256.to_owned(), |raw| observation_sha256(raw)),
                ),
            ),
        ])
    });
    let fragment_rows = result.fragments.iter().map(|row| {
        object([
            ("input_id", ManifestValue::U64(u64::from(row.input_id))),
            (
                "profile_id",
                string(
                    row.profile_version
                        .and_then(profile_by_version)
                        .map_or("", |profile| profile.id),
                ),
            ),
            ("section_id", ManifestValue::U64(u64::from(row.section_id))),
            (
                "semantic_copy_id",
                ManifestValue::U64(u64::from(row.semantic_copy_id)),
            ),
            (
                "fragment_index",
                ManifestValue::U64(u64::from(row.fragment_index)),
            ),
            (
                "replica_index",
                ManifestValue::U64(u64::from(row.replica_index)),
            ),
            (
                "physical_replica_count",
                ManifestValue::U64(u64::from(row.physical_replica_count)),
            ),
            ("state", string(fragment_state_name(row.state))),
            ("common_block_sha256", string(&row.common_block_sha256)),
        ])
    });
    let fragment_bytes = canonical_array(fragment_rows.collect())?;
    let required = recovered_stream(result, 2);
    let all = recovered_stream(result, 3);
    if all.is_some() && required.is_none() {
        return Err(DamageV1Error::Reconstruction);
    }
    let accepted = result.accepted_hypotheses.iter().map(|row| {
        object([
            (
                "transform_id",
                ManifestValue::U64(u64::from(row.transform_id)),
            ),
            (
                "polarity_id",
                ManifestValue::U64(u64::from(row.polarity_id)),
            ),
            ("sector_id", ManifestValue::U64(u64::from(row.sector_id))),
            (
                "profile_id",
                string(profile_by_version(row.profile_version).map_or("", |profile| profile.id)),
            ),
            ("mapping_sha256", string(&row.mapping_sha256)),
        ])
    });
    let value = object([
        ("schema", string("golden-board.m2-damage-decoder-result/v1")),
        ("channel", string(channel)),
        (
            "artifact_state",
            string(artifact_state_name(result.artifact_state)),
        ),
        ("established_profile_id", string(profile_id)),
        ("section_rows", ManifestValue::Array(section_rows.collect())),
        (
            "fragment_diagnostics_sha256",
            string(&observation_sha256(&fragment_bytes)),
        ),
        (
            "m2_required_available",
            ManifestValue::Bool(required.is_some()),
        ),
        ("m2_all_available", ManifestValue::Bool(all.is_some())),
        (
            "m2_required_stream_sha256",
            string(
                &required
                    .as_ref()
                    .map_or_else(|| ZERO_SHA256.to_owned(), |raw| observation_sha256(raw)),
            ),
        ),
        (
            "m2_all_stream_sha256",
            string(
                &all.as_ref()
                    .map_or_else(|| ZERO_SHA256.to_owned(), |raw| observation_sha256(raw)),
            ),
        ),
        (
            "resource",
            object([
                (
                    "section_attempts",
                    ManifestValue::U64(result.resource.section_attempts),
                ),
                (
                    "primitive_steps",
                    ManifestValue::U64(result.resource.primitive_steps),
                ),
                (
                    "peak_scratch_bytes",
                    ManifestValue::U64(result.resource.peak_scratch_bytes),
                ),
            ]),
        ),
        (
            "accepted_hypothesis_rows",
            ManifestValue::Array(accepted.collect()),
        ),
    ]);
    let raw = serialize_manifest(&value).map_err(|_| DamageV1Error::Reconstruction)?;
    if raw.len() > 1_048_576 {
        return Err(DamageV1Error::ResourceLimit);
    }
    let sha256 = observation_sha256(&raw);
    Ok((raw, sha256))
}

pub const BOUNDARY_KAT_IDS_V1: [&str; 4] = [
    "rep2-correction-boundary",
    "rep5-correction-boundary",
    "complete-section-conflict",
    "section-attempt-ceiling-plus-one",
];

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BoundaryKatResultV1 {
    pub kat_id: &'static str,
    pub passed: bool,
    pub canonical_bytes: Vec<u8>,
    pub sha256: String,
}

fn render_boundary_kat_result_v1(
    kat_id: &'static str,
    passed: bool,
) -> Result<BoundaryKatResultV1> {
    if !BOUNDARY_KAT_IDS_V1.contains(&kat_id) {
        return Err(DamageV1Error::Reconstruction);
    }
    let value = object([
        ("schema", string("golden-board.m2-boundary-kat-result/v1")),
        ("kat_id", string(kat_id)),
        ("result", string(if passed { "pass" } else { "fail" })),
    ]);
    let canonical_bytes = serialize_manifest(&value).map_err(|_| DamageV1Error::Reconstruction)?;
    let sha256 = observation_sha256(&canonical_bytes);
    Ok(BoundaryKatResultV1 {
        kat_id,
        passed,
        canonical_bytes,
        sha256,
    })
}

fn boundary_common_v1() -> Result<[u8; 191]> {
    encode_common_block(&crate::CommonBlock {
        profile_version: PROFILE_V7,
        section_id: 1,
        semantic_copy_id: 0,
        section_type: SECTION_INVENTORY,
        section_version: 1,
        fragment_index: 0,
        fragment_count: 1,
        section_envelope_length: 1,
        payload: vec![0],
    })
    .map_err(|_| DamageV1Error::Reconstruction)
}

fn repetition_boundary_kat_v1(factor: usize) -> Result<bool> {
    let common = boundary_common_v1()?;
    let clean = EhObservation {
        encoded: encode_eh_unit(&common),
        erasures: Vec::new(),
    };
    let mut changed = clean.clone();
    changed.encoded[0] ^= 0x80;
    let (correctable, one_beyond) = match factor {
        2 => (
            vec![Some(clean.clone()), None],
            vec![Some(clean.clone()), Some(changed.clone())],
        ),
        5 => (
            vec![
                Some(clean.clone()),
                Some(clean.clone()),
                Some(clean.clone()),
                Some(changed.clone()),
                Some(changed.clone()),
            ],
            vec![
                Some(clean.clone()),
                Some(clean.clone()),
                Some(changed.clone()),
                Some(changed.clone()),
                None,
            ],
        ),
        _ => return Err(DamageV1Error::Reconstruction),
    };
    let corrected = aggregate_repetition_observation(&correctable)
        .map_err(|_| DamageV1Error::Reconstruction)?
        .ok_or(DamageV1Error::Reconstruction)?;
    let erased = aggregate_repetition_observation(&one_beyond)
        .map_err(|_| DamageV1Error::Reconstruction)?
        .ok_or(DamageV1Error::Reconstruction)?;
    let expected_erasure = EhErasure {
        codeword: 0,
        position: 1,
    };
    let profile = profile_by_version(PROFILE_V7).ok_or(DamageV1Error::Profile)?;
    let corrected_group = diagnose_hierarchical_eh_group(profile, &correctable)
        .map_err(|_| DamageV1Error::Reconstruction)?;
    let erased_group = diagnose_hierarchical_eh_group(profile, &one_beyond)
        .map_err(|_| DamageV1Error::Reconstruction)?;
    Ok(corrected.encoded == clean.encoded
        && corrected.erasures.is_empty()
        && erased.erasures == [expected_erasure]
        && corrected_group.factor as usize == factor
        && erased_group.factor as usize == factor
        && corrected_group.common == Some(common)
        && erased_group.common == Some(common)
        && corrected_group.repetition_symbol_invocations == REPETITION_SYMBOLS_PER_GROUP as u32
        && erased_group.repetition_symbol_invocations == REPETITION_SYMBOLS_PER_GROUP as u32)
}

fn complete_section_conflict_boundary_kat_v1() -> Result<bool> {
    let envelopes = [b"first".as_slice(), b"second".as_slice()]
        .into_iter()
        .enumerate()
        .map(|(semantic_copy_id, payload)| {
            let envelope = encode_section(&SectionEnvelope {
                section_id: 9,
                section_type: crate::SECTION_CONTENT_BODY,
                section_version: 0,
                closure_class: crate::CLOSURE_M2_ALL_ONLY,
                check_id: crate::CHECK_CRC32C,
                dependencies: Vec::new(),
                payload: payload.to_vec(),
            })
            .map_err(|_| DamageV1Error::Reconstruction)?;
            encode_common_block(&crate::CommonBlock {
                profile_version: PROFILE_V7,
                section_id: 9,
                semantic_copy_id: semantic_copy_id as u16,
                section_type: crate::SECTION_CONTENT_BODY,
                section_version: 0,
                fragment_index: 0,
                fragment_count: 1,
                section_envelope_length: envelope.len() as u32,
                payload: envelope,
            })
            .map_err(|_| DamageV1Error::Reconstruction)
        })
        .collect::<Result<Vec<_>>>()?;
    let mut entries = BTreeMap::new();
    let mut local = BTreeMap::new();
    for (ordinal, common) in envelopes.into_iter().enumerate() {
        let id = 100 + ordinal as u32;
        entries.insert(
            id,
            LaneInput {
                present: true,
                observation: Some(EhObservation {
                    encoded: encode_eh_unit(&common),
                    erasures: Vec::new(),
                }),
            },
        );
        local.insert(
            id,
            vec![LocalCandidate {
                profile_version: PROFILE_V7,
                common,
                quality: DecodeQuality::Verified,
            }],
        );
    }
    let result = recover_v7_inputs(entries, local, ResourceProjection::default(), Vec::new())?;
    Ok(result.artifact_state == ArtifactState::Ambiguous
        && !result.inventory_established
        && result.resource.section_attempts == 2
        && result.sections.iter().any(|section| {
            section.section_id == 9
                && section.state == SectionState::Ambiguous
                && section.envelope.is_none()
        }))
}

fn section_attempt_boundary_kat_v1() -> Result<bool> {
    let mut candidates = (0_u32..4_097)
        .map(|ordinal| {
            encode_section(&SectionEnvelope {
                section_id: 4_000,
                section_type: crate::SECTION_CONTENT_BODY,
                section_version: 0,
                closure_class: crate::CLOSURE_M2_ALL_ONLY,
                check_id: crate::CHECK_CRC32C,
                dependencies: Vec::new(),
                payload: ordinal.to_be_bytes().to_vec(),
            })
            .map_err(|_| DamageV1Error::Reconstruction)
        })
        .collect::<Result<Vec<_>>>()?;
    candidates.sort();
    if candidates.windows(2).any(|pair| pair[0] == pair[1])
        || candidates.iter().any(|raw| !structurally_attemptable(raw))
    {
        return Ok(false);
    }
    let mut resource = ResourceProjection::default();
    let mut checked = 0_u64;
    let mut rejected = None;
    for (ordinal, candidate) in candidates.iter().enumerate() {
        match charge_section_attempt(&mut resource) {
            Ok(()) => {
                decode_section(candidate).map_err(|_| DamageV1Error::Reconstruction)?;
                checked += 1;
            }
            Err(DamageV1Error::ResourceLimit) => {
                rejected = Some(ordinal as u64);
                break;
            }
            Err(error) => return Err(error),
        }
    }
    Ok(checked == SECTION_ATTEMPT_LIMIT
        && resource.section_attempts == SECTION_ATTEMPT_LIMIT
        && rejected == Some(SECTION_ATTEMPT_LIMIT))
}

/// Execute one frozen synthetic boundary KAT and emit its exact canonical v1
/// result. This path never realizes a D0--D7 case or consumes candidate bytes.
pub fn boundary_kat_result_v1(ordinal: u8) -> Result<BoundaryKatResultV1> {
    verify_promoted_decoder_owners()?;
    let kat_id = *BOUNDARY_KAT_IDS_V1
        .get(usize::from(ordinal))
        .ok_or(DamageV1Error::Observation)?;
    let passed = match ordinal {
        0 => repetition_boundary_kat_v1(2)?,
        1 => repetition_boundary_kat_v1(5)?,
        2 => complete_section_conflict_boundary_kat_v1()?,
        3 => section_attempt_boundary_kat_v1()?,
        _ => unreachable!(),
    };
    render_boundary_kat_result_v1(kat_id, passed)
}

pub fn boundary_kat_results_v1() -> Result<Vec<BoundaryKatResultV1>> {
    (0_u8..4).map(boundary_kat_result_v1).collect()
}

// -------------------------------------------------------------------------
// Generator/oracle-side v7 observation operators.
//
// These functions are deliberately typed on the clean hierarchical core and
// are never called by the observation decoder above.  Keeping this boundary
// explicit prevents candidate rows, ownership coordinates, and case metadata
// from leaking into decoder inputs.

pub fn clean_unit_entries_v1(core: &HierarchicalManifestationCore) -> Vec<UnitEntry> {
    core.units
        .iter()
        .map(|unit| UnitEntry {
            physical_unit_id: unit.physical_unit_id,
            bytes: unit.encoded.to_vec(),
        })
        .collect()
}

pub fn omitted_unit_observation_v1(
    core: &HierarchicalManifestationCore,
    omitted: &[u32],
) -> crate::damage::Result<Vec<u8>> {
    if omitted.is_empty()
        || omitted.len() > core.units.len()
        || omitted
            .iter()
            .any(|id| *id == 0 || *id as usize > core.units.len())
        || omitted.iter().copied().collect::<BTreeSet<_>>().len() != omitted.len()
    {
        return Err(crate::damage::DamageError::Operator);
    }
    let omitted = omitted.iter().copied().collect::<BTreeSet<_>>();
    serialize_obs_units(
        &clean_unit_entries_v1(core)
            .into_iter()
            .filter(|entry| !omitted.contains(&entry.physical_unit_id))
            .collect::<Vec<_>>(),
    )
}

pub fn permuted_unit_observation_v1(
    core: &HierarchicalManifestationCore,
    permutation: &[usize],
) -> crate::damage::Result<Vec<u8>> {
    if permutation.len() != core.units.len()
        || permutation.iter().copied().collect::<BTreeSet<_>>().len() != core.units.len()
        || permutation.iter().any(|index| *index >= core.units.len())
    {
        return Err(crate::damage::DamageError::Operator);
    }
    let clean = clean_unit_entries_v1(core);
    serialize_obs_units(
        &permutation
            .iter()
            .map(|index| clean[*index].clone())
            .collect::<Vec<_>>(),
    )
}

fn clean_common_v1(
    core: &HierarchicalManifestationCore,
    unit_id: u32,
) -> crate::damage::Result<[u8; 191]> {
    let index = usize::try_from(unit_id)
        .map_err(|_| crate::damage::DamageError::Operator)?
        .checked_sub(1)
        .ok_or(crate::damage::DamageError::Operator)?;
    let unit = core
        .units
        .get(index)
        .ok_or(crate::damage::DamageError::Operator)?;
    decode_eh_unit(
        &EhObservation {
            encoded: unit.encoded,
            erasures: Vec::new(),
        },
        PROFILE_V7,
    )
    .map(|decoded| decoded.common)
    .map_err(|_| crate::damage::DamageError::Reconstruction)
}

fn recompute_common_local_check(common: &mut [u8; 191]) {
    let mut preimage = Vec::with_capacity(LOCAL_CHECK_DOMAIN.len() + 187);
    preimage.extend_from_slice(&LOCAL_CHECK_DOMAIN);
    preimage.extend_from_slice(&common[..187]);
    common[187..].copy_from_slice(&crc32c(&preimage).to_be_bytes());
}

/// D7 cross-profile splice.  All five lanes of the first REP5 group are
/// replaced by the same source-profile transport, including 255-byte RS rows.
pub fn cross_profile_splice_v1(
    core: &HierarchicalManifestationCore,
    source_profile_version: u16,
) -> crate::damage::Result<Vec<u8>> {
    if !matches!(source_profile_version, 2..=6) {
        return Err(crate::damage::DamageError::Operator);
    }
    let mut common = clean_common_v1(core, 1)?;
    common[..2].copy_from_slice(&source_profile_version.to_be_bytes());
    recompute_common_local_check(&mut common);
    let source =
        profile_by_version(source_profile_version).ok_or(crate::damage::DamageError::Operator)?;
    let bytes = match source.transport {
        TransportFamily::Eh72Replicated | TransportFamily::Eh72HierarchicalRepetition => {
            crate::candidate::encode_eh_unit(&common).to_vec()
        }
        TransportFamily::Rs255_191 => crate::candidate::encode_rs255_191(&common).to_vec(),
    };
    let mut entries = clean_unit_entries_v1(core);
    for id in 1_u32..=5 {
        entries[id as usize - 1].bytes = bytes.clone();
    }
    serialize_obs_units(&entries)
}

/// D7 local-check mutants target all five physical lanes in group one.
pub fn local_check_mutant_v1(
    core: &HierarchicalManifestationCore,
    normal_reflection: bool,
) -> crate::damage::Result<Vec<u8>> {
    let mut common = clean_common_v1(core, 1)?;
    if normal_reflection {
        let mut register = 0xffff_ffff_u32;
        let mut preimage = Vec::with_capacity(LOCAL_CHECK_DOMAIN.len() + 187);
        preimage.extend_from_slice(&LOCAL_CHECK_DOMAIN);
        preimage.extend_from_slice(&common[..187]);
        for byte in preimage {
            register ^= u32::from(byte) << 24;
            for _ in 0..8 {
                register = if register & 0x8000_0000 != 0 {
                    (register << 1) ^ 0x1edc_6f41
                } else {
                    register << 1
                };
            }
        }
        common[187..].copy_from_slice(&(register ^ 0xffff_ffff).to_be_bytes());
    } else {
        common[187..].reverse();
    }
    let encoded = crate::candidate::encode_eh_unit(&common).to_vec();
    let mut entries = clean_unit_entries_v1(core);
    for id in 1_u32..=5 {
        entries[id as usize - 1].bytes = encoded.clone();
    }
    serialize_obs_units(&entries)
}

/// D7 EH code mutants apply the inherited mutant to every codeword in every
/// lane of the first REP5 group.
pub fn code_mutant_v1(
    core: &HierarchicalManifestationCore,
    ordinal: u8,
) -> crate::damage::Result<Vec<u8>> {
    if ordinal > 2 {
        return Err(crate::damage::DamageError::Operator);
    }
    let common = clean_common_v1(core, 1)?;
    let mut plain = [0_u8; 192];
    plain[..191].copy_from_slice(&common);
    let mut encoded = [0_u8; EH_UNIT_BYTES];
    for chunk in 0..24 {
        let data: [u8; 8] = plain[chunk * 8..(chunk + 1) * 8].try_into().unwrap();
        encoded[chunk * 9..(chunk + 1) * 9]
            .copy_from_slice(&encode_eh_mutant_chunk(&data, ordinal));
    }
    let mut entries = clean_unit_entries_v1(core);
    for id in 1_u32..=5 {
        entries[id as usize - 1].bytes = encoded.to_vec();
    }
    serialize_obs_units(&entries)
}

fn replace_section_groups_v1(
    core: &HierarchicalManifestationCore,
    section_id: u32,
    envelope: &[u8],
    structurally_valid: bool,
) -> crate::damage::Result<Vec<u8>> {
    let section = core
        .sections
        .iter()
        .find(|section| section.section_id == section_id)
        .ok_or(crate::damage::DamageError::Operator)?;
    let blocks = if structurally_valid {
        fragment_envelope(
            PROFILE_V7,
            section.section_id,
            0,
            section.section_type,
            section.section_version,
            envelope,
        )
        .map_err(|_| crate::damage::DamageError::Operator)?
    } else {
        let count = envelope.len().div_ceil(COMMON_PAYLOAD_BYTES);
        (0..count)
            .map(|fragment| {
                let start = fragment * COMMON_PAYLOAD_BYTES;
                let end = envelope.len().min(start + COMMON_PAYLOAD_BYTES);
                encode_common_block(&crate::CommonBlock {
                    profile_version: PROFILE_V7,
                    section_id,
                    semantic_copy_id: 0,
                    section_type: section.section_type,
                    section_version: section.section_version,
                    fragment_index: fragment as u16,
                    fragment_count: count as u16,
                    section_envelope_length: envelope.len() as u32,
                    payload: envelope[start..end].to_vec(),
                })
                .map_err(|_| crate::damage::DamageError::Operator)
            })
            .collect::<crate::damage::Result<Vec<_>>>()?
    };
    let matching = core
        .units
        .iter()
        .filter(|unit| unit.section_id == section_id)
        .collect::<Vec<_>>();
    if matching.len() != blocks.len() * usize::from(section.copy_count) {
        return Err(crate::damage::DamageError::Reconstruction);
    }
    let mut entries = clean_unit_entries_v1(core);
    for unit in matching {
        let block = blocks
            .get(usize::from(unit.fragment_index))
            .ok_or(crate::damage::DamageError::Reconstruction)?;
        entries[unit.physical_unit_id as usize - 1].bytes =
            crate::candidate::encode_eh_unit(block).to_vec();
    }
    serialize_obs_units(&entries)
}

/// D7 section-check mutants rewrite every fragment and lane of section 2.
pub fn section_check_mutant_v1(
    core: &HierarchicalManifestationCore,
    wrong_check_id: bool,
) -> crate::damage::Result<Vec<u8>> {
    let section = core
        .sections
        .iter()
        .find(|section| section.section_id == 2 && section.closure_class == CLOSURE_M2_REQUIRED)
        .ok_or(crate::damage::DamageError::Operator)?;
    let mut envelope = section
        .envelope()
        .map_err(|_| crate::damage::DamageError::Reconstruction)?;
    if wrong_check_id {
        envelope[11] = 2;
    } else {
        let length = envelope.len();
        envelope[length - 4..].reverse();
    }
    replace_section_groups_v1(core, 2, &envelope, false)
}

/// D7 valid-replica conflict changes only physical lane ID 1.  The local
/// common block remains valid, so group aggregation must expose ambiguity.
pub fn valid_replica_conflict_v1(
    core: &HierarchicalManifestationCore,
) -> crate::damage::Result<Vec<u8>> {
    let mut common = clean_common_v1(core, 1)?;
    common[30] ^= 1;
    recompute_common_local_check(&mut common);
    let mut entries = clean_unit_entries_v1(core);
    entries[0].bytes = crate::candidate::encode_eh_unit(&common).to_vec();
    serialize_obs_units(&entries)
}

/// D7 mapping mutants retain the clean slot permutation and rewrite all unit
/// bits only at the selected mutant cell-affine location.
pub fn mapping_mutant_v1(
    core: &HierarchicalManifestationCore,
    ordinal: u8,
) -> crate::damage::Result<Vec<u8>> {
    if ordinal > 2 {
        return Err(crate::damage::DamageError::Operator);
    }
    let mut bits = core.carrier_bits.clone();
    let population = core.mapping.population;
    let interior = u64::from(core.mapping.interior_side);
    for unit in &core.units {
        for bit_offset in 0..EH_UNIT_BYTES * 8 {
            let logical = unit.logical_bit_first + bit_offset as u64;
            let physical = match ordinal {
                0 => logical,
                1 => {
                    (core.mapping.cell_multiplier * logical
                        + (core.mapping.cell_offset + 1) % population)
                        % population
                }
                2 => ((2 * interior + 1) * logical + core.mapping.cell_offset) % population,
                _ => unreachable!(),
            };
            let (row, column) = core
                .mapping
                .matrix_cell(physical)
                .map_err(|_| crate::damage::DamageError::Coordinate)?;
            let value = (unit.encoded[bit_offset / 8] >> (7 - bit_offset % 8)) & 1;
            bits[usize::from(row) * usize::from(core.side) + usize::from(column)] = value;
        }
    }
    serialize_obs_bits(&bits)
}

/// D7 route conflict replaces only sector zero's complete route prefix with
/// the supplied independently archived v3 prefix.  Prefix lengths may differ;
/// untouched shell cells retain their clean v7 values.
pub fn route_conflict_v1(
    core: &HierarchicalManifestationCore,
    archived_v3_prefix: &[u8],
) -> crate::damage::Result<Vec<u8>> {
    if archived_v3_prefix.len() < 64
        || archived_v3_prefix[..32] != CALIBRATIONS[0]
        || &archived_v3_prefix[32..40] != ROUTE_MAGIC
        || read_u16(&archived_v3_prefix[32..64], 8) != Some(0)
        || read_u16(&archived_v3_prefix[32..64], 12) != Some(3)
        || read_u32(&archived_v3_prefix[32..64], 24)
            != u32::try_from(archived_v3_prefix.len() * 8).ok()
    {
        return Err(crate::damage::DamageError::Operator);
    }
    let sector_capacity = usize::from(core.shell_width)
        .checked_mul(usize::from(core.side) - usize::from(core.shell_width))
        .ok_or(crate::damage::DamageError::ResourceLimit)?;
    if archived_v3_prefix.len() * 8 > sector_capacity {
        return Err(crate::damage::DamageError::Operator);
    }
    let mut bits = core.carrier_bits.clone();
    for bit in 0..archived_v3_prefix.len() * 8 {
        let (row, column) = sector_cell_at(
            usize::from(core.side),
            usize::from(core.shell_width),
            0,
            bit,
        )
        .map_err(|_| crate::damage::DamageError::Coordinate)?;
        bits[row * usize::from(core.side) + column] =
            (archived_v3_prefix[bit / 8] >> (7 - bit % 8)) & 1;
    }
    serialize_obs_bits(&bits)
}

pub fn missing_unit_one_beyond_v1(
    core: &HierarchicalManifestationCore,
) -> crate::damage::Result<(Vec<u32>, Vec<u8>)> {
    let omitted = vec![1, 2, 3, 4, 5];
    Ok((
        omitted.clone(),
        omitted_unit_observation_v1(core, &omitted)?,
    ))
}

pub fn algebraic_one_beyond_v1(
    core: &HierarchicalManifestationCore,
    errors: usize,
    erasures: usize,
) -> crate::damage::Result<Vec<u8>> {
    if 2 * errors + erasures != 4 || errors + erasures > 72 {
        return Err(crate::damage::DamageError::Operator);
    }
    let mut values = core.carrier_bits.clone();
    for physical_ordinal in 0_u64..5 {
        for position in 0..erasures + errors {
            let physical = core
                .mapping
                .forward_unit_bit(physical_ordinal, position as u16)
                .map_err(|_| crate::damage::DamageError::Coordinate)?;
            let (row, column) = core
                .mapping
                .matrix_cell(physical)
                .map_err(|_| crate::damage::DamageError::Coordinate)?;
            let flat = usize::from(row) * usize::from(core.side) + usize::from(column);
            if position < erasures {
                values[flat] = 2;
            } else {
                values[flat] ^= 1;
            }
        }
    }
    serialize_obs_matrix(usize::from(core.side), &values)
}

pub fn resource_route_one_beyond_v1(
    core: &HierarchicalManifestationCore,
    scratch: bool,
) -> crate::damage::Result<Vec<u8>> {
    let route = &core.routes.sectors[0];
    let prefix_bytes = usize::try_from(route.route_prefix_cells)
        .map_err(|_| crate::damage::DamageError::ResourceLimit)?
        / 8;
    let mut raw = vec![0_u8; prefix_bytes];
    for bit in 0..prefix_bytes * 8 {
        raw[bit / 8] |= route.bits[bit] << (7 - bit % 8);
    }
    let mut offset = 64_usize;
    let mut package_offset = None;
    while offset < raw.len() {
        let header = raw
            .get(offset..offset + 8)
            .ok_or(crate::damage::DamageError::Reconstruction)?;
        let length = usize::try_from(u32::from_be_bytes(header[4..8].try_into().unwrap()))
            .map_err(|_| crate::damage::DamageError::ResourceLimit)?;
        if header[1] == 5 {
            package_offset = Some(offset + 8);
            break;
        }
        offset = offset
            .checked_add(8 + length)
            .ok_or(crate::damage::DamageError::ResourceLimit)?;
    }
    let package = package_offset.ok_or(crate::damage::DamageError::Reconstruction)?;
    if scratch {
        raw[package + 44..package + 48].copy_from_slice(&16_777_217_u32.to_be_bytes());
    } else {
        raw[package + 36..package + 44].copy_from_slice(&268_435_457_u64.to_be_bytes());
    }
    let mut bits = core.carrier_bits.clone();
    for bit in 0..raw.len() * 8 {
        let (row, column) = sector_cell_at(
            usize::from(core.side),
            usize::from(core.shell_width),
            0,
            bit,
        )
        .map_err(|_| crate::damage::DamageError::Coordinate)?;
        bits[row * usize::from(core.side) + column] = (raw[bit / 8] >> (7 - bit % 8)) & 1;
    }
    serialize_obs_bits(&bits)
}

pub fn geometry_one_beyond_v1() -> Vec<u8> {
    let count = 2_056_u32 * 2_056;
    let mut raw = count.to_be_bytes().to_vec();
    raw.resize(4 + count as usize / 8, 0);
    raw
}

pub fn erase_square_v1(
    core: &HierarchicalManifestationCore,
    top_left: Coordinate,
    square: usize,
) -> crate::damage::Result<Vec<u8>> {
    let mut values = core.carrier_bits.clone();
    let row = usize::try_from(top_left.row).map_err(|_| crate::damage::DamageError::Coordinate)?;
    let column =
        usize::try_from(top_left.column).map_err(|_| crate::damage::DamageError::Coordinate)?;
    let width = usize::from(core.shell_width);
    let interior = usize::from(core.mapping.interior_side);
    if row > interior.saturating_sub(square) || column > interior.saturating_sub(square) {
        return Err(crate::damage::DamageError::Coordinate);
    }
    for local_row in row..row + square {
        for local_column in column..column + square {
            values[(local_row + width) * usize::from(core.side) + local_column + width] = 2;
        }
    }
    serialize_obs_matrix(usize::from(core.side), &values)
}

pub fn d2_one_beyond_v1(
    core: &HierarchicalManifestationCore,
    placement: Coordinate,
) -> crate::damage::Result<Vec<u8>> {
    let side = d2_square_side(usize::from(core.mapping.interior_side)) + 1;
    let maximum = usize::from(core.mapping.interior_side) - side;
    erase_square_v1(
        core,
        Coordinate {
            row: placement.row.min(maximum as u32),
            column: placement.column.min(maximum as u32),
        },
        side,
    )
}

fn interior_coordinate_v1(
    core: &HierarchicalManifestationCore,
    flat: usize,
) -> crate::damage::Result<Coordinate> {
    let interior = usize::from(core.mapping.interior_side);
    if flat >= interior * interior {
        return Err(crate::damage::DamageError::Coordinate);
    }
    Ok(Coordinate {
        row: u32::try_from(flat / interior + usize::from(core.shell_width))
            .map_err(|_| crate::damage::DamageError::Coordinate)?,
        column: u32::try_from(flat % interior + usize::from(core.shell_width))
            .map_err(|_| crate::damage::DamageError::Coordinate)?,
    })
}

fn d3_population_v1(
    core: &HierarchicalManifestationCore,
    stratum: usize,
    seed: u64,
) -> crate::damage::Result<Vec<Coordinate>> {
    let interior = usize::from(core.mapping.interior_side);
    match stratum {
        0 => (0..interior * interior)
            .map(|flat| interior_coordinate_v1(core, flat))
            .collect(),
        1 => {
            let window = 32.max(interior / 8);
            let origins = interior
                .checked_sub(window)
                .and_then(|value| value.checked_add(1))
                .ok_or(crate::damage::DamageError::SamplePopulation)?;
            let mut stream = CounterWords::new(WINDOW_DOMAIN, seed, origins)?;
            let row = stream.unbiased(origins)?;
            let column = stream.unbiased(origins)?;
            let mut population = Vec::with_capacity(window * window);
            for local_row in 0..window {
                for local_column in 0..window {
                    population.push(Coordinate {
                        row: (row + local_row + usize::from(core.shell_width)) as u32,
                        column: (column + local_column + usize::from(core.shell_width)) as u32,
                    });
                }
            }
            Ok(population)
        }
        2 => {
            let required = core
                .sections
                .iter()
                .filter(|section| section.closure_class == CLOSURE_M2_REQUIRED)
                .map(|section| section.section_id)
                .collect::<BTreeSet<_>>();
            let required_units = core
                .units
                .iter()
                .filter(|unit| required.contains(&unit.section_id))
                .map(|unit| unit.physical_unit_id)
                .collect::<BTreeSet<_>>();
            let side = usize::from(core.side);
            Ok(core
                .cell_owners
                .iter()
                .enumerate()
                .filter(|(_, owner)| owner.kind == 4 && required_units.contains(&owner.owner_id))
                .map(|(flat, _)| Coordinate {
                    row: (flat / side) as u32,
                    column: (flat % side) as u32,
                })
                .collect::<BTreeSet<_>>()
                .into_iter()
                .collect())
        }
        3 => {
            let side = usize::from(core.side);
            let width = usize::from(core.shell_width);
            Ok(core
                .cell_owners
                .iter()
                .enumerate()
                .filter(|(_, owner)| owner.kind == 4)
                .filter_map(|(flat, owner)| {
                    let row = flat / side;
                    let column = flat % side;
                    let offset = owner.bit_offset as usize;
                    let local_row = row - width;
                    let local_column = column - width;
                    (offset < 16
                        || offset + 16 >= EH_UNIT_BYTES * 8
                        || offset % 8 == 0
                        || offset % 8 == 7
                        || matches!(local_row % 16, 0 | 15)
                        || matches!(local_column % 16, 0 | 15))
                    .then_some(Coordinate {
                        row: row as u32,
                        column: column as u32,
                    })
                })
                .collect::<BTreeSet<_>>()
                .into_iter()
                .collect())
        }
        _ => Err(crate::damage::DamageError::Operator),
    }
}

pub fn d3_coordinates_v1(
    core: &HierarchicalManifestationCore,
    seed: u64,
    extra: usize,
) -> crate::damage::Result<Vec<Coordinate>> {
    let ordinal = seed
        .checked_sub(5_134_751_402_299_490_304)
        .ok_or(crate::damage::DamageError::Operator)?;
    if ordinal >= 128 {
        return Err(crate::damage::DamageError::Operator);
    }
    let population = d3_population_v1(core, (ordinal / 32) as usize, seed)?;
    let count = 64
        .max(
            usize::try_from(core.mapping.population)
                .map_err(|_| crate::damage::DamageError::ResourceLimit)?
                .div_ceil(2_000),
        )
        .checked_add(extra)
        .ok_or(crate::damage::DamageError::ResourceLimit)?;
    if population.len() < count {
        return Err(crate::damage::DamageError::SamplePopulation);
    }
    sample_without_replacement(population.len(), count, seed)?
        .into_iter()
        .map(|index| {
            population
                .get(index)
                .copied()
                .ok_or(crate::damage::DamageError::Coordinate)
        })
        .collect()
}

pub fn substitute_coordinates_v1(
    core: &HierarchicalManifestationCore,
    coordinates: &[Coordinate],
) -> crate::damage::Result<Vec<u8>> {
    if coordinates.len() > MAX_RAW_BITS {
        return Err(crate::damage::DamageError::ResourceLimit);
    }
    let mut values = core.carrier_bits.clone();
    let mut seen = BTreeSet::new();
    let side = usize::from(core.side);
    for coordinate in coordinates {
        if !seen.insert(*coordinate) {
            return Err(crate::damage::DamageError::Duplicate);
        }
        let row =
            usize::try_from(coordinate.row).map_err(|_| crate::damage::DamageError::Coordinate)?;
        let column = usize::try_from(coordinate.column)
            .map_err(|_| crate::damage::DamageError::Coordinate)?;
        if row >= side || column >= side {
            return Err(crate::damage::DamageError::Coordinate);
        }
        values[row * side + column] ^= 1;
    }
    serialize_obs_matrix(side, &values)
}

pub fn erase_shell_sector_v1(
    core: &HierarchicalManifestationCore,
    sector: u8,
    unit_id: Option<u32>,
) -> crate::damage::Result<Vec<u8>> {
    if sector > 3 || unit_id.is_some_and(|id| id == 0 || id as usize > core.units.len()) {
        return Err(crate::damage::DamageError::Operator);
    }
    let side = usize::from(core.side);
    let width = usize::from(core.shell_width);
    let mut values = core.carrier_bits.clone();
    let sector_cells = width
        .checked_mul(side - width)
        .ok_or(crate::damage::DamageError::ResourceLimit)?;
    for index in 0..sector_cells {
        let (row, column) = sector_cell_at(side, width, sector, index)
            .map_err(|_| crate::damage::DamageError::Coordinate)?;
        values[row * side + column] = 2;
    }
    if let Some(unit_id) = unit_id {
        for (flat, owner) in core.cell_owners.iter().enumerate() {
            if owner.kind == 4 && owner.owner_id == unit_id {
                values[flat] = 2;
            }
        }
    }
    serialize_obs_matrix(side, &values)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::candidate::{encode_eh_unit, profile_by_version};
    use crate::candidate_recipe::build_rs_decoder_recipe_package;
    use crate::carrier::{
        CellOwner, LogicalSection, ProtectedUnit, RouteImages, SectorImage,
        build_r3_gate_one_through_five, generate_r3_route_owner,
    };
    use crate::damage::{UnitEntry, serialize_obs_units};
    use crate::{
        CHECK_CRC32C, CommonBlock, SECTION_CONTENT_BODY, SectionEnvelope, encode_common_block,
        encode_section,
    };
    use gb_slice::{SliceInputs, compile_slice_v0};

    fn common(fragment: u16, count: u16, envelope_length: u32) -> [u8; 191] {
        encode_common_block(&CommonBlock {
            profile_version: 7,
            section_id: 1,
            semantic_copy_id: 0,
            section_type: SECTION_INVENTORY,
            section_version: 1,
            fragment_index: fragment,
            fragment_count: count,
            section_envelope_length: envelope_length,
            payload: vec![u8::try_from(fragment).unwrap(); 1],
        })
        .unwrap()
    }

    fn raw_common(
        profile_version: u16,
        semantic_copy_id: u16,
        section_id: u32,
        raw: &[u8],
    ) -> [u8; 191] {
        assert!(raw.len() <= COMMON_PAYLOAD_BYTES);
        encode_common_block(&CommonBlock {
            profile_version,
            section_id,
            semantic_copy_id,
            section_type: SECTION_CONTENT_BODY,
            section_version: 0,
            fragment_index: 0,
            fragment_count: 1,
            section_envelope_length: raw.len() as u32,
            payload: raw.to_vec(),
        })
        .unwrap()
    }

    fn no_inventory_input(
        rows: &[(u32, u16, u16, Vec<u8>)],
    ) -> (BTreeMap<u32, LaneInput>, BTreeMap<u32, Vec<LocalCandidate>>) {
        let mut entries = BTreeMap::new();
        let mut local = BTreeMap::new();
        for (id, profile_version, semantic_copy_id, raw) in rows {
            let common = raw_common(*profile_version, *semantic_copy_id, 9, raw);
            entries.insert(
                *id,
                LaneInput {
                    present: true,
                    observation: Some(EhObservation {
                        encoded: encode_eh_unit(&common),
                        erasures: Vec::new(),
                    }),
                },
            );
            local.insert(
                *id,
                vec![LocalCandidate {
                    profile_version: *profile_version,
                    common,
                    quality: DecodeQuality::Verified,
                }],
            );
        }
        (entries, local)
    }

    fn matrix_with_route_prefix(prefix: &[u8], side: usize, width: usize) -> ObsMatrix {
        let mut values = vec![0_u8; side * side];
        for bit in 0..prefix.len() * 8 {
            let (row, column) = sector_cell_at(side, width, 0, bit).unwrap();
            values[row * side + column] = (prefix[bit / 8] >> (7 - bit % 8)) & 1;
        }
        ObsMatrix { side, values }
    }

    fn promoted_core() -> &'static HierarchicalManifestationCore {
        static CORE: OnceLock<HierarchicalManifestationCore> = OnceLock::new();
        CORE.get_or_init(|| {
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
            .unwrap();
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
            .unwrap()
            .core
        })
    }

    fn synthetic_operator_core() -> HierarchicalManifestationCore {
        let profile = profile_by_version(7).unwrap();
        let mapping = HierarchicalMap::derive(128, 8).unwrap();
        let encoded = encode_eh_unit(&common(0, 1, 1));
        let units = (0_u64..5)
            .map(|ordinal| ProtectedUnit {
                physical_unit_id: ordinal as u32 + 1,
                section_id: 1,
                semantic_copy_id: 0,
                fragment_index: 0,
                replica_index: ordinal as u8,
                physical_replica_count: 5,
                encoded,
                slot: mapping.slot(ordinal).unwrap(),
                logical_bit_first: mapping.logical_bit_first(ordinal).unwrap(),
            })
            .collect::<Vec<_>>();
        let mut carrier_bits = vec![0_u8; 128 * 128];
        let mut cell_owners = vec![
            CellOwner {
                kind: 0,
                owner_id: 0,
                bit_offset: 0,
            };
            carrier_bits.len()
        ];
        for unit in &units {
            for bit in 0..EH_UNIT_BYTES * 8 {
                let physical = mapping
                    .forward_unit_bit(unit.physical_unit_id as u64 - 1, bit as u16)
                    .unwrap();
                let (row, column) = mapping.matrix_cell(physical).unwrap();
                let flat = usize::from(row) * 128 + usize::from(column);
                carrier_bits[flat] = (unit.encoded[bit / 8] >> (7 - bit % 8)) & 1;
                cell_owners[flat] = CellOwner {
                    kind: 4,
                    owner_id: unit.physical_unit_id,
                    bit_offset: bit as u32,
                };
            }
        }
        let sectors = std::array::from_fn(|sector| SectorImage {
            sector_id: sector as u8,
            bits: vec![0; 8 * 120],
            route_prefix_cells: 0,
            headroom_cells: 0,
            spans: Vec::new(),
        });
        HierarchicalManifestationCore {
            profile,
            semantic_envelope_sha256: ZERO_SHA256.to_owned(),
            side: 128,
            shell_width: 8,
            mapping,
            routes: RouteImages {
                instruction_cells: 0,
                headroom_cells: 0,
                sectors,
            },
            sections: vec![LogicalSection {
                section_id: 1,
                section_type: SECTION_INVENTORY,
                section_version: 1,
                closure_class: CLOSURE_M2_REQUIRED,
                check_id: CHECK_CRC32C,
                copy_count: 5,
                dependencies: Vec::new(),
                game_ordinal: None,
                payload: vec![0],
            }],
            units,
            carrier_bits,
            carrier_bytes: Vec::new(),
            cell_owners,
            interior_fixed_pad_bits: vec![0; mapping.fixed_pad_cells as usize],
        }
    }

    #[test]
    fn group_conflict_is_not_hidden_by_rep5_majority() {
        let profile = profile_by_version(7).unwrap();
        let left = encode_eh_unit(&common(0, 1, 1));
        // The local common check uses a different domain; obtain a second
        // valid block through its typed encoder instead of repairing bytes.
        let right = encode_eh_unit(
            &encode_common_block(&CommonBlock {
                payload: vec![1],
                ..decode_common_block(&common(0, 1, 1), 7).unwrap()
            })
            .unwrap(),
        );
        let observations = [left, left, left, left, right].map(|encoded| {
            Some(EhObservation {
                encoded,
                erasures: Vec::new(),
            })
        });
        let diagnostic = diagnose_hierarchical_eh_group(profile, &observations).unwrap();
        assert_eq!(diagnostic.state, HierarchicalGroupState::Conflict);
        assert_eq!(diagnostic.distinct_candidate_count, 2);
    }

    #[test]
    fn valid_rep5_conflict_preserves_each_physical_lane_diagnostic() {
        let core = synthetic_operator_core();
        let raw = valid_replica_conflict_v1(&core).unwrap();
        let observation = ObsUnits::parse(&raw).unwrap();
        let result = decode_units_v1(&raw).unwrap();
        assert!(!result.inventory_established);
        assert_eq!(result.artifact_state, ArtifactState::Failure);
        assert_eq!(result.fragments.len(), 5);
        assert!(result.fragments.iter().all(|row| {
            row.profile_version == Some(PROFILE_V7)
                && row.section_id == 1
                && row.semantic_copy_id == 0
                && row.fragment_index == 0
                && row.physical_replica_count == 5
                && row.replica_index == u16::try_from(row.input_id - 1).unwrap()
                && row.state == FragmentState::Verified
                && row.common_block_sha256 != ZERO_SHA256
        }));
        assert_ne!(
            result.fragments[0].common_block_sha256,
            result.fragments[1].common_block_sha256
        );
        assert!(
            result.fragments[1..]
                .windows(2)
                .all(|rows| rows[0].common_block_sha256 == rows[1].common_block_sha256)
        );
        for (row, input) in result.fragments.iter().zip(&observation.entries) {
            let decoded = decode_eh_unit(
                &EhObservation {
                    encoded: input.bytes.as_slice().try_into().unwrap(),
                    erasures: Vec::new(),
                },
                PROFILE_V7,
            )
            .unwrap();
            assert_eq!(
                row.common_block_sha256,
                format!("{:x}", Sha256::digest(decoded.common))
            );
        }
    }

    #[test]
    fn section_check_mutants_suppress_all_stream_without_required_stream() {
        let core = promoted_core();
        for (wrong_check_id, expected_attempts, expected_sha256) in [
            (
                true,
                137_u64,
                "abd38e7e9039647929eb95c353a0f33c79f5cdaf8ff790f839e186b662d4a020",
            ),
            (
                false,
                138,
                "73949e666f31f87326601f60ed6befe8768f8c7bbb48018c729f9a3b5017aa66",
            ),
        ] {
            let observation = section_check_mutant_v1(core, wrong_check_id).unwrap();
            let result = decode_units_v1(&observation).unwrap();
            assert_eq!(result.artifact_state, ArtifactState::Failure);
            assert_eq!(result.resource.section_attempts, expected_attempts);
            assert_eq!(
                result
                    .sections
                    .iter()
                    .find(|section| section.section_id == 2)
                    .map(|section| section.state),
                Some(SectionState::Corrupt)
            );
            assert!(recovered_stream(&result, 2).is_none());
            assert!(recovered_stream(&result, 3).is_none());
            let (raw, _) = render_decoder_result_v1("OBS_UNITS", &result).unwrap();
            assert_eq!(raw.len(), 17_600);
            assert_eq!(format!("{:x}", Sha256::digest(&raw)), expected_sha256);
            assert_eq!(result.resource.primitive_steps, 21_398_719_042);
            assert_eq!(result.resource.peak_scratch_bytes, 7_688);
        }
    }

    #[test]
    fn no_inventory_retains_checked_later_section_and_route_fixed_missing_rows() {
        let raw = encode_section(&SectionEnvelope {
            section_id: 9,
            section_type: SECTION_CONTENT_BODY,
            section_version: 0,
            closure_class: crate::CLOSURE_M2_ALL_ONLY,
            check_id: CHECK_CRC32C,
            dependencies: Vec::new(),
            payload: b"checked".to_vec(),
        })
        .unwrap();
        let (entries, local) = no_inventory_input(&[(100, PROFILE_V7, 0, raw.clone())]);
        let result =
            recover_v7_inputs(entries, local, ResourceProjection::default(), Vec::new()).unwrap();
        assert!(!result.inventory_established);
        assert_eq!(result.artifact_state, ArtifactState::Failure);
        assert_eq!(
            result.sections,
            vec![
                SectionResult {
                    section_id: 1,
                    state: SectionState::Incomplete,
                    envelope: None,
                },
                SectionResult {
                    section_id: 9,
                    state: SectionState::Verified,
                    envelope: Some(raw),
                },
            ]
        );
        assert_eq!(result.resource.section_attempts, 1);
        assert!(result.fragments.iter().take(5).all(|row| {
            row.profile_version == Some(PROFILE_V7)
                && row.section_id == 1
                && row.semantic_copy_id == 0
                && row.fragment_index == 0
        }));
        assert_eq!(
            result
                .fragments
                .iter()
                .take(5)
                .map(|row| (
                    row.input_id,
                    row.replica_index,
                    row.physical_replica_count,
                    row.state,
                ))
                .collect::<Vec<_>>(),
            (1_u32..=5)
                .map(|id| (id, (id - 1) as u16, 5, FragmentState::Missing))
                .collect::<Vec<_>>()
        );
        let later = result.fragments.last().unwrap();
        assert_eq!(later.input_id, 100);
        assert_eq!(later.replica_index, ABSENT_U16);
        assert_eq!(later.physical_replica_count, ABSENT_U16);
        assert_eq!(later.state, FragmentState::Verified);
    }

    #[test]
    fn missing_rep5_group_retains_route_fixed_diagnostic_identity() {
        let (omitted, observation) = missing_unit_one_beyond_v1(promoted_core()).unwrap();
        assert_eq!(omitted, [1, 2, 3, 4, 5]);
        assert_eq!(ObsUnits::parse(&observation).unwrap().entries.len(), 1_836);

        let result = decode_units_v1(&observation).unwrap();
        assert!(!result.inventory_established);
        assert_eq!(result.artifact_state, ArtifactState::Failure);
        assert_eq!(result.fragments.len(), 1_841);
        assert!(
            result.fragments[..5]
                .iter()
                .enumerate()
                .all(|(index, row)| {
                    row.input_id == index as u32 + 1
                        && row.profile_version == Some(PROFILE_V7)
                        && row.section_id == 1
                        && row.semantic_copy_id == 0
                        && row.fragment_index == 0
                        && row.replica_index == index as u16
                        && row.physical_replica_count == 5
                        && row.state == FragmentState::Missing
                        && row.common_block_sha256 == ZERO_SHA256
                })
        );
        assert_eq!(result.sections.len(), 138);
        assert_eq!(
            result.sections.first(),
            Some(&SectionResult {
                section_id: 1,
                state: SectionState::Incomplete,
                envelope: None,
            })
        );

        assert_eq!(result.resource.section_attempts, 137);
        assert_eq!(result.resource.primitive_steps, 20_412_387_288);
        assert_eq!(result.resource.peak_scratch_bytes, 7_688);
        let (rendered, result_sha256) = render_decoder_result_v1("OBS_UNITS", &result).unwrap();
        assert_eq!(rendered.len(), 17_575);
        assert_eq!(
            result_sha256,
            "1e897f63ed3d222a1e587f1ab1fb599d2da4e6c226396794b7091a5261b421fc"
        );
        let rendered = std::str::from_utf8(&rendered).unwrap();
        let marker = "\"fragment_diagnostics_sha256\":\"";
        let start = rendered.find(marker).unwrap() + marker.len();
        assert_eq!(
            &rendered[start..start + 64],
            "379652c89611f3ef0d503f157e9bc0d0175cc859be083a4bc600b736f4c2a2df"
        );
    }

    #[test]
    fn mapping_mutant_no_inventory_projection_uses_absent_lane_identity() {
        // D7-000000 leaves four valid observed v7 routes but scrambles every
        // lane under the clean route's map.  The route fixes the replica
        // positions of IDs 1 through 5; it does not synthesize a locally
        // checked common-block identity for their corrupt bytes.
        let entries = (1_u32..=1_841)
            .map(|id| {
                (
                    id,
                    LaneInput {
                        present: true,
                        observation: None,
                    },
                )
            })
            .collect::<BTreeMap<_, _>>();
        let bootstrap_groups = vec![GroupRecovery {
            identity: GroupIdentity {
                section_id: 1,
                section_type: SECTION_INVENTORY,
                section_version: 1,
                fragment_index: 0,
                fragment_count: 1,
                section_envelope_length: 1,
            },
            first_id: 1,
            factor: 5,
            state: FragmentState::Corrupt,
            common: None,
            lane_states: vec![FragmentState::Corrupt; 5],
        }];
        let fragments =
            diagnostics_without_inventory(&entries, &BTreeMap::new(), &bootstrap_groups);
        assert_eq!(fragments.len(), 1_841);
        assert!(fragments[..5].iter().enumerate().all(|(index, row)| {
            row.profile_version.is_none()
                && row.section_id == 0
                && row.semantic_copy_id == ABSENT_U16
                && row.fragment_index == ABSENT_U16
                && row.replica_index == index as u16
                && row.physical_replica_count == 5
                && row.state == FragmentState::Corrupt
                && row.common_block_sha256 == ZERO_SHA256
        }));

        let mapping_sha256 = "90d6fa3a3a6b28489c8c63e62df17caab7a46180614e387952a77071731da439";
        let result = RecoveryResultV1 {
            profile_version: None,
            inventory_established: false,
            resource: ResourceProjection {
                section_attempts: 0,
                primitive_steps: 14_223_708_344,
                peak_scratch_bytes: 6_163,
            },
            artifact_state: ArtifactState::Failure,
            sections: vec![SectionResult {
                section_id: 1,
                state: SectionState::Corrupt,
                envelope: None,
            }],
            fragments,
            accepted_hypotheses: (0_u8..4)
                .map(|sector| AcceptedHypothesis {
                    transform_id: 0,
                    polarity_id: 0,
                    sector_id: sector,
                    profile_version: PROFILE_V7,
                    mapping_sha256: mapping_sha256.to_owned(),
                })
                .collect(),
        };
        let (raw, sha256) = render_decoder_result_v1("OBS_BITS", &result).unwrap();
        assert_eq!(raw.len(), 1_431);
        assert_eq!(
            sha256,
            "18e4f5da2c37157d11549756a134b456e8ea328ce8dac9d6bbdfdaa8d7fdbc69"
        );
    }

    #[test]
    fn no_inventory_attempt_boundary_and_complete_conflict_are_fail_closed() {
        let clean = encode_section(&SectionEnvelope {
            section_id: 9,
            section_type: SECTION_CONTENT_BODY,
            section_version: 0,
            closure_class: crate::CLOSURE_M2_ALL_ONLY,
            check_id: CHECK_CRC32C,
            dependencies: Vec::new(),
            payload: b"checked".to_vec(),
        })
        .unwrap();
        let mut wrong_width = clean.clone();
        wrong_width[11] = crate::CHECK_CRC64_ECMA;
        let mut wrong_stored = clean.clone();
        let check_start = wrong_stored.len() - 4;
        wrong_stored[check_start..].reverse();
        for (raw, expected_attempts) in [(wrong_width, 0), (wrong_stored, 1)] {
            let (entries, local) = no_inventory_input(&[(100, PROFILE_V7, 0, raw)]);
            let result =
                recover_v7_inputs(entries, local, ResourceProjection::default(), Vec::new())
                    .unwrap();
            assert_eq!(result.resource.section_attempts, expected_attempts);
            assert_eq!(result.sections.len(), 1);
            assert_eq!(result.sections[0].section_id, 1);
        }

        let alternate = encode_section(&SectionEnvelope {
            payload: b"different".to_vec(),
            ..SectionEnvelope {
                section_id: 9,
                section_type: SECTION_CONTENT_BODY,
                section_version: 0,
                closure_class: crate::CLOSURE_M2_ALL_ONLY,
                check_id: CHECK_CRC32C,
                dependencies: Vec::new(),
                payload: Vec::new(),
            }
        })
        .unwrap();
        let (entries, local) =
            no_inventory_input(&[(100, PROFILE_V7, 0, clean), (101, 2, 0, alternate)]);
        let result =
            recover_v7_inputs(entries, local, ResourceProjection::default(), Vec::new()).unwrap();
        assert_eq!(result.resource.section_attempts, 2);
        assert_eq!(result.artifact_state, ArtifactState::Ambiguous);
        assert_eq!(
            result.sections.iter().find(|row| row.section_id == 9),
            Some(&SectionResult {
                section_id: 9,
                state: SectionState::Ambiguous,
                envelope: None,
            })
        );
    }

    #[test]
    fn result_v1_adds_replica_fields_without_touching_v0_renderer() {
        let result = RecoveryResultV1 {
            profile_version: None,
            inventory_established: false,
            resource: ResourceProjection::default(),
            artifact_state: ArtifactState::Failure,
            sections: Vec::new(),
            fragments: vec![FragmentDiagnosticV1 {
                input_id: 1,
                profile_version: None,
                section_id: 0,
                semantic_copy_id: ABSENT_U16,
                fragment_index: ABSENT_U16,
                replica_index: 0,
                physical_replica_count: 5,
                state: FragmentState::Missing,
                common_block_sha256: ZERO_SHA256.to_owned(),
            }],
            accepted_hypotheses: Vec::new(),
        };
        let (raw, _) = render_decoder_result_v1("OBS_UNITS", &result).unwrap();
        let text = std::str::from_utf8(&raw).unwrap();
        assert!(text.contains("golden-board.m2-damage-decoder-result/v1"));
        assert!(!text.contains("replica_index"));
        // Fragment rows are committed by hash, not included at top level.
        let rows = canonical_array(vec![object([
            ("input_id", ManifestValue::U64(1)),
            ("profile_id", string("")),
            ("section_id", ManifestValue::U64(0)),
            ("semantic_copy_id", ManifestValue::U64(65_535)),
            ("fragment_index", ManifestValue::U64(65_535)),
            ("replica_index", ManifestValue::U64(0)),
            ("physical_replica_count", ManifestValue::U64(5)),
            ("state", string("missing")),
            ("common_block_sha256", string(ZERO_SHA256)),
        ])])
        .unwrap();
        assert!(
            std::str::from_utf8(&rows)
                .unwrap()
                .contains("replica_index")
        );

        let mut duplicate = result.clone();
        duplicate.fragments.push(duplicate.fragments[0].clone());
        assert_eq!(
            render_decoder_result_v1("OBS_UNITS", &duplicate).unwrap_err(),
            DamageV1Error::Reconstruction
        );
        let mut bad_replica = result.clone();
        bad_replica.fragments[0].replica_index = 5;
        assert_eq!(
            render_decoder_result_v1("OBS_UNITS", &bad_replica).unwrap_err(),
            DamageV1Error::Reconstruction
        );
        let mut bad_establishment = result;
        bad_establishment.profile_version = Some(PROFILE_V7);
        assert_eq!(
            render_decoder_result_v1("OBS_UNITS", &bad_establishment).unwrap_err(),
            DamageV1Error::Reconstruction
        );
    }

    #[test]
    fn v1_diagnostics_enforce_inventory_identity_hash_and_registry_order() {
        let (entries, local) = no_inventory_input(&[
            (100, PROFILE_V7, 0, b"mismatch".to_vec()),
            (101, PROFILE_V7, 0, b"extra".to_vec()),
        ]);
        let expected = ExpectedLane {
            identity: GroupIdentity {
                section_id: 1,
                section_type: SECTION_INVENTORY,
                section_version: 1,
                fragment_index: 0,
                fragment_count: 1,
                section_envelope_length: 1,
            },
            replica_index: 0,
            physical_replica_count: 5,
        };
        let diagnostics =
            diagnostics_with_layout(&entries, &local, &BTreeMap::from([(100, expected)]), &[]);
        assert_eq!(diagnostics.len(), 2);
        assert_eq!(diagnostics[0].section_id, 1);
        assert_eq!(diagnostics[0].profile_version, Some(PROFILE_V7));
        assert_eq!(diagnostics[0].state, FragmentState::Corrupt);
        assert_eq!(diagnostics[0].common_block_sha256, ZERO_SHA256);
        assert_eq!(diagnostics[0].replica_index, 0);
        assert_eq!(diagnostics[0].physical_replica_count, 5);
        assert_eq!(diagnostics[1].section_id, 9);
        assert_eq!(diagnostics[1].state, FragmentState::Verified);
        assert_ne!(diagnostics[1].common_block_sha256, ZERO_SHA256);
        assert_eq!(diagnostics[1].replica_index, ABSENT_U16);
        assert_eq!(diagnostics[1].physical_replica_count, ABSENT_U16);

        let mut accepted = vec![
            AcceptedHypothesis {
                transform_id: 0,
                polarity_id: 0,
                sector_id: 0,
                profile_version: 2,
                mapping_sha256: "11".repeat(32),
            },
            AcceptedHypothesis {
                transform_id: 0,
                polarity_id: 0,
                sector_id: 0,
                profile_version: 7,
                mapping_sha256: "22".repeat(32),
            },
        ];
        sort_and_dedup_accepted(&mut accepted).unwrap();
        assert_eq!(
            accepted
                .iter()
                .map(|row| row.profile_version)
                .collect::<Vec<_>>(),
            [7, 2]
        );
        let result = RecoveryResultV1 {
            profile_version: None,
            inventory_established: false,
            resource: ResourceProjection::default(),
            artifact_state: ArtifactState::Failure,
            sections: Vec::new(),
            fragments: Vec::new(),
            accepted_hypotheses: accepted.clone(),
        };
        assert!(render_decoder_result_v1("OBS_BITS", &result).is_ok());
        let mut wrong_order = result;
        wrong_order.accepted_hypotheses.reverse();
        assert_eq!(
            render_decoder_result_v1("OBS_BITS", &wrong_order).unwrap_err(),
            DamageV1Error::Reconstruction
        );
    }

    #[test]
    fn obs_units_registry_charge_is_id_then_profile_and_bounded() {
        verify_promoted_decoder_owners().unwrap();
        let raw = serialize_obs_units(&[UnitEntry {
            physical_unit_id: 8,
            bytes: vec![0; EH_UNIT_BYTES],
        }])
        .unwrap();
        let result = decode_units_v1(&raw).unwrap();
        let per_entry = 80_435 * 24 * 4 + 1_698_049 * 2;
        assert_eq!(result.resource.primitive_steps, per_entry);
        assert_eq!(result.resource.peak_scratch_bytes, 7_688);
        assert_eq!(result.artifact_state, ArtifactState::Failure);
    }

    #[test]
    fn clean_obs_units_and_result_match_cross_implementation_kat() {
        let observation = serialize_obs_units(&clean_unit_entries_v1(promoted_core())).unwrap();
        assert_eq!(observation.len(), 408_706);
        assert_eq!(
            observation_sha256(&observation),
            "6731afd616ed31cedce6223fc56e553d0d006c792c317c6d58af588a8efb8b1a"
        );

        let result = decode_units_v1(&observation).unwrap();
        assert_eq!(result.profile_version, Some(PROFILE_V7));
        assert!(result.inventory_established);
        assert_eq!(result.artifact_state, ArtifactState::Exact);
        assert_eq!(result.sections.len(), 138);
        assert_eq!(result.fragments.len(), 1_841);
        assert_eq!(result.resource.section_attempts, 138);
        assert_eq!(result.resource.primitive_steps, 21_398_719_042);
        assert_eq!(result.resource.peak_scratch_bytes, 7_688);
        let (rendered, rendered_sha256) = render_decoder_result_v1("OBS_UNITS", &result).unwrap();
        assert_eq!(rendered.len(), 17_597);
        assert_eq!(
            rendered_sha256,
            "594c98172e44db5531c019ffe2d479b6812df0a39c9022ede4770f74a9c0cebc"
        );
    }

    #[test]
    fn promoted_resource_owner_matches_compiled_package() {
        verify_promoted_decoder_owners().unwrap();
        assert_eq!(registry_resource_row(7).unwrap().primitive_steps, 80_435);
        assert_eq!(registry_resource_row(7).unwrap().invocations_per_unit, 24);
        let package = build_eh_recipe_package(7).unwrap();
        assert_eq!(
            observation_sha256(&package),
            registry_resource_row(7).unwrap().package_sha256
        );
        // Keep imports for the foreign registry construction live and checked.
        assert!(build_rs_decoder_recipe_package(5).is_ok());
        assert_eq!(CHECK_CRC32C, 1);
    }

    #[test]
    fn observed_v1_route_parser_accepts_abi_rejects_drift_and_propagates_resource_limit() {
        let owner = generate_r3_route_owner().unwrap();
        let side = usize::from(owner.draft.side);
        let width = usize::from(owner.draft.shell_width);
        let clean = &owner.draft.route_prefixes[0];
        let matrix = matrix_with_route_prefix(clean, side, width);
        let mut resource = ResourceProjection::default();
        let parsed = parse_sector_route_v1(&matrix, width, 0, &mut resource)
            .unwrap()
            .unwrap();
        assert_eq!(parsed.map, owner.draft.mapping);
        assert_eq!(resource.primitive_steps, 15_134);
        assert_eq!(resource.peak_scratch_bytes, 6_163);

        let mut define_drift = clean.clone();
        // First record is DEFINE fact 1: 8-byte record framing, 14-byte
        // definition framing, then the exact candidate-neutral fact name.
        define_drift[64 + 8 + 14] ^= 1;
        let mutant = matrix_with_route_prefix(&define_drift, side, width);
        let mut resource = ResourceProjection::default();
        assert!(
            parse_sector_route_v1(&mutant, width, 0, &mut resource)
                .unwrap()
                .is_none()
        );
        assert_eq!(resource.primitive_steps, 0);

        let mut recipe_drift = clean.clone();
        // First WORKED record begins immediately after DEFINE fact 1.
        let first_define_payload = 14 + FACT_NAMES[0].len();
        let first_worked = 64 + 8 + first_define_payload;
        recipe_drift[first_worked + 8 + 2..first_worked + 8 + 4]
            .copy_from_slice(&102_u16.to_be_bytes());
        let mutant = matrix_with_route_prefix(&recipe_drift, side, width);
        let mut resource = ResourceProjection::default();
        assert!(
            parse_sector_route_v1(&mutant, width, 0, &mut resource)
                .unwrap()
                .is_none()
        );
        assert_eq!(resource.primitive_steps, 0);

        let mut resource_drift = clean.clone();
        let mut offset = 64_usize;
        let package = loop {
            let kind = resource_drift[offset + 1];
            let length =
                u32::from_be_bytes(resource_drift[offset + 4..offset + 8].try_into().unwrap())
                    as usize;
            if kind == 5 {
                break offset + 8;
            }
            offset += 8 + length;
        };
        resource_drift[package + 36..package + 44].copy_from_slice(&268_435_457_u64.to_be_bytes());
        let mutant = matrix_with_route_prefix(&resource_drift, side, width);
        let mut resource = ResourceProjection::default();
        assert_eq!(
            parse_sector_route_v1(&mutant, width, 0, &mut resource).unwrap_err(),
            DamageV1Error::ResourceLimit
        );
        assert_eq!(resource.primitive_steps, 0);

        resource_drift = clean.clone();
        resource_drift[package + 44..package + 48].copy_from_slice(&16_777_217_u32.to_be_bytes());
        let mutant = matrix_with_route_prefix(&resource_drift, side, width);
        let mut resource = ResourceProjection::default();
        assert_eq!(
            parse_sector_route_v1(&mutant, width, 0, &mut resource).unwrap_err(),
            DamageV1Error::ResourceLimit
        );
        assert_eq!(resource, ResourceProjection::default());
    }

    #[test]
    fn resource_route_one_beyond_is_global_resource_limit() {
        let observation = resource_route_one_beyond_v1(promoted_core(), false).unwrap();
        let result = decode_observation_v1("OBS_BITS", &observation);
        assert_eq!(result.artifact_state, ArtifactState::ResourceLimit);
        assert_eq!(result.profile_version, None);
        assert!(!result.inventory_established);
        assert!(result.sections.is_empty());
        assert!(result.fragments.is_empty());
        assert!(result.accepted_hypotheses.is_empty());
        assert_eq!(result.resource, ResourceProjection::default());
        let (_, sha256) = render_decoder_result_v1("OBS_BITS", &result).unwrap();
        assert_eq!(
            sha256,
            "78253f50589a2cb22fe53f38d4959c58ec3483db3e0f74574a1b06634322e71d"
        );
    }

    #[test]
    fn v1_section_attempt_counter_rejects_4097_before_comparison() {
        let mut resource = ResourceProjection::default();
        for _ in 0..SECTION_ATTEMPT_LIMIT {
            charge_section_attempt(&mut resource).unwrap();
        }
        assert_eq!(resource.section_attempts, SECTION_ATTEMPT_LIMIT);
        assert_eq!(
            charge_section_attempt(&mut resource).unwrap_err(),
            DamageV1Error::ResourceLimit
        );
        assert_eq!(resource.section_attempts, SECTION_ATTEMPT_LIMIT);
    }

    #[test]
    fn v1_boundary_kat_results_are_exact_and_ordered() {
        let rows = boundary_kat_results_v1().unwrap();
        assert_eq!(rows.len(), BOUNDARY_KAT_IDS_V1.len());
        let expected = [
            (
                104,
                "452d38bd592174b0fb022cee41e4f261768957811893ae471934bf3e4e8e6622",
            ),
            (
                104,
                "5158867ec6d4c740afec018f5695a51779ca54758113303d3b656c4b6ee1f01e",
            ),
            (
                105,
                "9508a43cc54c7f6dc06fcee677a18db1ed57bfdb87e1c5f692d332642a3c5b56",
            ),
            (
                112,
                "966307a69ded9f055704443e6c6c46b4d0226a4a4bced398e0573fe5afe03187",
            ),
        ];
        for ((row, expected_id), (expected_bytes, expected_sha256)) in
            rows.iter().zip(BOUNDARY_KAT_IDS_V1).zip(expected)
        {
            assert_eq!(row.kat_id, expected_id);
            assert!(row.passed);
            assert_eq!(row.canonical_bytes.len(), expected_bytes);
            assert_eq!(row.sha256, expected_sha256);
        }
    }

    #[test]
    fn clean_v7_observation_has_exact_four_path_resource_charge() {
        // Decoder input is only the independently regenerated observation
        // serialization. Candidate/ownership rows and the in-memory core are
        // intentionally absent from the decoder surface itself.
        let raw = &promoted_core().carrier_bytes;
        let result = decode_bits_v1(raw).unwrap();
        assert_eq!(result.profile_version, Some(PROFILE_V7));
        assert!(result.inventory_established);
        assert_eq!(result.artifact_state, ArtifactState::Exact);
        assert_eq!(result.sections.len(), 138);
        assert_eq!(result.fragments.len(), 1_841);
        assert_eq!(result.accepted_hypotheses.len(), 4);
        assert_eq!(result.resource.section_attempts, 138);
        assert_eq!(result.resource.primitive_steps, 17_938_790_552);
        assert_eq!(result.resource.peak_scratch_bytes, 6_163);
    }

    #[test]
    fn route_present_matrix_without_inventory_retains_checked_later_sections() {
        let raw = &promoted_core().carrier_bytes;
        let mut matrix = parse_obs_bits_matrix(raw).unwrap();
        let map = HierarchicalMap::derive(2_040, 128).unwrap();
        for physical_ordinal in 0_u64..5 {
            for bit in 0_u16..1_728 {
                let physical = map.forward_unit_bit(physical_ordinal, bit).unwrap();
                let (row, column) = map.matrix_cell(physical).unwrap();
                matrix.values[usize::from(row) * matrix.side + usize::from(column)] = 2;
            }
        }
        let mut observed = (matrix.side as u16).to_be_bytes().to_vec();
        observed.extend_from_slice(&matrix.values);
        let result = decode_matrix_v1(&observed).unwrap();
        assert!(!result.inventory_established);
        assert_eq!(result.profile_version, None);
        assert_eq!(result.artifact_state, ArtifactState::Failure);
        assert_eq!(result.sections.len(), 138);
        assert_eq!(result.sections[0].section_id, 1);
        assert_eq!(result.sections[0].state, SectionState::Corrupt);
        assert_eq!(result.sections[1].section_id, 2);
        assert_eq!(result.sections[1].state, SectionState::Verified);
        assert_eq!(result.fragments.len(), 1_841);
        assert!(result.fragments[..5].iter().all(|row| {
            row.state == FragmentState::Corrupt
                && row.physical_replica_count == 5
                && row.replica_index < 5
        }));
        assert_eq!(result.resource.section_attempts, 137);
        assert_eq!(result.accepted_hypotheses.len(), 4);
    }

    #[test]
    fn accepted_route_mapping_hashes_match_tagged_union_kats() {
        let hierarchical = HierarchicalMap::derive(2_040, 128).unwrap();
        assert_eq!(
            mapping_sha256_v1(hierarchical).unwrap(),
            "90d6fa3a3a6b28489c8c63e62df17caab7a46180614e387952a77071731da439"
        );
        let legacy = AffineMap::derive(2_040, 128, 3).unwrap();
        assert_eq!(
            mapping_sha256_legacy(legacy).unwrap(),
            "7f2f3f2a9bd9238668b3fefc78f31ae2ac4a0fa58acaab2793b24ca4d3c2369c"
        );
    }

    #[test]
    fn v7_d7_unit_operators_target_exact_rep5_lanes() {
        let core = synthetic_operator_core();
        let splice_raw = cross_profile_splice_v1(&core, 5).unwrap();
        let splice = ObsUnits::parse(&splice_raw).unwrap();
        assert_eq!(splice.entries.len(), 5);
        assert!(
            splice
                .entries
                .iter()
                .all(|entry| entry.bytes.len() == RS_CODEWORD_BYTES)
        );
        let decoded = decode_units_v1(&splice_raw).unwrap();
        assert_eq!(decoded.artifact_state, ArtifactState::Failure);
        assert!(!decoded.inventory_established);
        assert_eq!(
            decoded.sections,
            vec![SectionResult {
                section_id: 1,
                state: SectionState::Corrupt,
                envelope: None,
            }]
        );
        assert_eq!(decoded.fragments.len(), 5);
        assert!(decoded.fragments.iter().all(|row| {
            row.profile_version == Some(5)
                && row.state == FragmentState::Verified
                && row.physical_replica_count == 5
                && row.replica_index == u16::try_from(row.input_id - 1).unwrap()
                && row.common_block_sha256 != ZERO_SHA256
        }));
        let conflict = ObsUnits::parse(&valid_replica_conflict_v1(&core).unwrap()).unwrap();
        let first = decode_eh_unit(
            &EhObservation {
                encoded: conflict.entries[0].bytes.as_slice().try_into().unwrap(),
                erasures: Vec::new(),
            },
            7,
        )
        .unwrap();
        let second = decode_eh_unit(
            &EhObservation {
                encoded: conflict.entries[1].bytes.as_slice().try_into().unwrap(),
                erasures: Vec::new(),
            },
            7,
        )
        .unwrap();
        assert_ne!(first.common, second.common);
        let (ids, missing) = missing_unit_one_beyond_v1(&core).unwrap();
        assert_eq!(ids, [1, 2, 3, 4, 5]);
        assert!(ObsUnits::parse(&missing).unwrap().entries.is_empty());
    }

    #[test]
    fn v7_algebraic_operator_mutates_same_positions_in_all_five_lanes() {
        let core = synthetic_operator_core();
        let matrix = ObsMatrix::parse(&algebraic_one_beyond_v1(&core, 1, 2).unwrap()).unwrap();
        for ordinal in 0..5_u64 {
            for position in 0..3_u16 {
                let physical = core.mapping.forward_unit_bit(ordinal, position).unwrap();
                let (row, column) = core.mapping.matrix_cell(physical).unwrap();
                let value = matrix.values[usize::from(row) * matrix.side + usize::from(column)];
                if position < 2 {
                    assert_eq!(value, 2);
                } else {
                    let clean =
                        core.carrier_bits[usize::from(row) * matrix.side + usize::from(column)];
                    assert_eq!(value, clean ^ 1);
                }
            }
        }
    }
}
