//! Independent construction of the complete M2 provisional carrier.
//!
//! This module consumes only promoted owners, the independently compiled slice,
//! and the final hash-bound recipient recipe package.  It does not consume a
//! carrier, ledger, section, or placement emitted by another implementation.

use std::collections::{BTreeMap, BTreeSet};

use gb_foundation::{ManifestValue, identity_hex, serialize_manifest, validate_canonical_manifest};
use gb_slice::{Closure, SliceCompilation};
use sha2::{Digest, Sha256};

use crate::candidate::{
    CandidateProfile, EH_UNIT_BYTES, EhObservation, TransportFamily, decode_eh_unit,
    encode_eh_unit, profile_by_version, recover_hierarchical_eh_group,
};
use crate::candidate_recipe::{
    build_eh_recipe_package, r3_recipe_package_metrics, r3_recipe_resource_rows,
    r3_slot_multiplier_table,
};
use crate::policy::{
    ProfilePolicy, admit_r3_promoted_owner_bundle, load_damage_policy, load_profile_limits,
    load_profile_policy,
};
use crate::recipe::{RecipePackage, RecipeValue, decode_recipe_package, evaluate_recipe};
use crate::{
    CHECK_CRC32C, CLOSURE_M2_ALL_ONLY, CLOSURE_M2_REQUIRED, FragmentWitness, Inventory,
    InventoryEntry, RecoveryQuality, SECTION_CAPACITY_PROBE, SECTION_CONTENT_BODY,
    SECTION_INVENTORY, SECTION_LOAD_PROBE, SECTION_RESERVE_PROBE, SECTION_TIER_FRAME,
    SectionEnvelope, aggregate_section_witnesses, assemble_content_stream, assemble_semantic_copy,
    decode_common_block, decode_inventory, decode_section, decode_tier_frame, encode_inventory,
    encode_section, fragment_envelope, sector_cell_at, validate_envelope_against_inventory,
};

const ROUTE_DATA_SHA256: &str = "965a3e35ceb4b5a92a7715b3fcde20cc3019f8c9d9efa533abd93b051bb86641";
const ROUTE_MAGIC: &[u8; 8] = b"GBROUTE\0";
const ROUTE_VERSION: u16 = 0;
const MAX_ROUTE_CAPACITY_BYTES: usize = 30_720;
const DISCRIMINATOR_CELLS: usize = 256;
const SECTOR_MASKS: [u8; 4] = [0x00, 0x3c, 0xa5, 0xc9];
const SHELL_PAD_DOMAIN: &[u8] = b"GB-M2-SHELL-PAD-v0\0";
const FILL_DOMAIN: &[u8] = b"GB-M2-FILL-v0\0";
const RAW_BITS_MAX: usize = 4_194_304;
const RESERVE_PAYLOAD_BYTES: u64 = 7_141;
const MAXIMUM_PROBE_PAYLOAD: u64 = 16_384;
const OWNER_DOCUMENT_BYTES_MAX: usize = 1_048_576;

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

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CarrierError {
    OwnerIdentity,
    ManifestShape,
    Recipe,
    RouteFit,
    Arithmetic,
    Parameter,
    Section,
    Geometry,
    Ownership,
    Reconstruction,
}

type Result<T> = std::result::Result<T, CarrierError>;

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn object(value: &ManifestValue) -> Result<&BTreeMap<String, ManifestValue>> {
    match value {
        ManifestValue::Object(value) => Ok(value),
        _ => Err(CarrierError::ManifestShape),
    }
}

fn object_mut(value: &mut ManifestValue) -> Result<&mut BTreeMap<String, ManifestValue>> {
    match value {
        ManifestValue::Object(value) => Ok(value),
        _ => Err(CarrierError::ManifestShape),
    }
}

fn array(value: &ManifestValue) -> Result<&[ManifestValue]> {
    match value {
        ManifestValue::Array(value) => Ok(value),
        _ => Err(CarrierError::ManifestShape),
    }
}

fn array_mut(value: &mut ManifestValue) -> Result<&mut Vec<ManifestValue>> {
    match value {
        ManifestValue::Array(value) => Ok(value),
        _ => Err(CarrierError::ManifestShape),
    }
}

fn text(value: &ManifestValue) -> Result<&str> {
    match value {
        ManifestValue::String(value) => Ok(value),
        _ => Err(CarrierError::ManifestShape),
    }
}

fn unsigned(value: &ManifestValue) -> Result<u64> {
    match value {
        ManifestValue::U64(value) => Ok(*value),
        _ => Err(CarrierError::ManifestShape),
    }
}

fn field<'a>(value: &'a ManifestValue, key: &str) -> Result<&'a ManifestValue> {
    object(value)?.get(key).ok_or(CarrierError::ManifestShape)
}

fn decode_hex(value: &str) -> Result<Vec<u8>> {
    if value.len() % 2 != 0 || !value.is_ascii() {
        return Err(CarrierError::ManifestShape);
    }
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let text = std::str::from_utf8(pair).map_err(|_| CarrierError::ManifestShape)?;
            u8::from_str_radix(text, 16).map_err(|_| CarrierError::ManifestShape)
        })
        .collect()
}

fn encode_hex(raw: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(raw.len() * 2);
    for byte in raw {
        output.push(char::from(DIGITS[usize::from(byte >> 4)]));
        output.push(char::from(DIGITS[usize::from(byte & 0x0f)]));
    }
    output
}

fn be_u16(output: &mut Vec<u8>, value: usize) -> Result<()> {
    output.extend_from_slice(
        &u16::try_from(value)
            .map_err(|_| CarrierError::Arithmetic)?
            .to_be_bytes(),
    );
    Ok(())
}

fn be_u32(output: &mut Vec<u8>, value: usize) -> Result<()> {
    output.extend_from_slice(
        &u32::try_from(value)
            .map_err(|_| CarrierError::Arithmetic)?
            .to_be_bytes(),
    );
    Ok(())
}

fn bytes_to_bits(raw: &[u8]) -> Vec<u8> {
    raw.iter()
        .flat_map(|byte| (0..8).rev().map(move |shift| (byte >> shift) & 1))
        .collect()
}

fn counter_bits(domain: &[u8], suffix: &[u8], count: usize) -> Result<Vec<u8>> {
    let mut output = Vec::with_capacity(count);
    let mut counter = 0_u64;
    while output.len() < count {
        let mut hash = Sha256::new();
        hash.update(domain);
        hash.update(suffix);
        hash.update(counter.to_be_bytes());
        let digest = hash.finalize();
        output.extend(bytes_to_bits(&digest));
        counter = counter.checked_add(1).ok_or(CarrierError::Arithmetic)?;
    }
    output.truncate(count);
    Ok(output)
}

/// Canonical probe/pad stream from Section 10.5.
pub fn fill_bits(slice_semantic_sha256: &[u8; 32], count: usize) -> Result<Vec<u8>> {
    if count > RAW_BITS_MAX {
        return Err(CarrierError::Parameter);
    }
    counter_bits(FILL_DOMAIN, slice_semantic_sha256, count)
}

fn shell_pad_bits(profile_version: u16, sector: u8, count: usize) -> Result<Vec<u8>> {
    let mut suffix = Vec::with_capacity(3);
    suffix.extend_from_slice(&profile_version.to_be_bytes());
    suffix.push(sector);
    counter_bits(SHELL_PAD_DOMAIN, &suffix, count)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ShellOwner {
    Instruction,
    Example,
    Recipe,
    Headroom,
    FixedPad,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ShellSpan {
    pub first_cell: u64,
    pub cell_count: u64,
    pub owner: ShellOwner,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SectorImage {
    pub sector_id: u8,
    pub bits: Vec<u8>,
    pub route_prefix_cells: u64,
    pub headroom_cells: u64,
    pub spans: Vec<ShellSpan>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RouteImages {
    pub instruction_cells: u64,
    pub headroom_cells: u64,
    pub sectors: [SectorImage; 4],
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ValueShape {
    kind: u8,
    width: u32,
}

fn value_size(shape: ValueShape) -> Result<usize> {
    match shape.kind {
        0 | 1 | 2 | 5 => {
            usize::try_from(shape.width.div_ceil(8)).map_err(|_| CarrierError::Arithmetic)
        }
        3 => usize::try_from(shape.width).map_err(|_| CarrierError::Arithmetic),
        _ => Err(CarrierError::ManifestShape),
    }
}

fn shapes(value: &ManifestValue, key: &str) -> Result<Vec<ValueShape>> {
    array(field(value, key)?)?
        .iter()
        .map(|row| {
            let kind = u8::try_from(unsigned(field(row, "type")?)?)
                .map_err(|_| CarrierError::ManifestShape)?;
            let width = u32::try_from(unsigned(field(row, "width")?)?)
                .map_err(|_| CarrierError::ManifestShape)?;
            let shape = ValueShape { kind, width };
            value_size(shape)?;
            Ok(shape)
        })
        .collect()
}

fn decode_values(raw: &[u8], shapes: &[ValueShape]) -> Result<Vec<RecipeValue>> {
    let mut offset = 0_usize;
    let mut output = Vec::with_capacity(shapes.len());
    for shape in shapes {
        let size = value_size(*shape)?;
        let end = offset.checked_add(size).ok_or(CarrierError::Arithmetic)?;
        let bytes = raw.get(offset..end).ok_or(CarrierError::ManifestShape)?;
        let value = match shape.kind {
            0 => {
                if shape.width == 0 || shape.width > 64 {
                    return Err(CarrierError::ManifestShape);
                }
                let mut value = 0_u64;
                for byte in bytes {
                    value = (value << 8) | u64::from(*byte);
                }
                if shape.width < 64 && value >= (1_u64 << shape.width) {
                    return Err(CarrierError::ManifestShape);
                }
                RecipeValue::Uint {
                    width: shape.width,
                    value,
                }
            }
            1 if shape.width == 1 && bytes.len() == 1 && bytes[0] <= 1 => {
                RecipeValue::Bool(bytes[0] == 1)
            }
            2 => {
                if shape.width == 0
                    || shape.width as usize > bytes.len() * 8
                    || shape.width % 8 != 0
                        && bytes.last().copied().unwrap_or(0) & ((1 << (8 - shape.width % 8)) - 1)
                            != 0
                {
                    return Err(CarrierError::ManifestShape);
                }
                RecipeValue::Bits {
                    width: shape.width,
                    packed: bytes.to_vec(),
                }
            }
            3 => RecipeValue::Bytes(bytes.to_vec()),
            _ => return Err(CarrierError::ManifestShape),
        };
        output.push(value);
        offset = end;
    }
    if offset != raw.len() {
        return Err(CarrierError::ManifestShape);
    }
    Ok(output)
}

fn encode_value(value: &RecipeValue) -> Result<Vec<u8>> {
    Ok(match value {
        RecipeValue::Uint { width, value } => {
            let size = usize::try_from(width.div_ceil(8)).map_err(|_| CarrierError::Arithmetic)?;
            value.to_be_bytes()[8 - size..].to_vec()
        }
        RecipeValue::Bool(value) => vec![u8::from(*value)],
        RecipeValue::Bits { width, packed } => {
            if packed.len()
                != usize::try_from(width.div_ceil(8)).map_err(|_| CarrierError::Arithmetic)?
            {
                return Err(CarrierError::Recipe);
            }
            packed.clone()
        }
        RecipeValue::Bytes(value) => value.clone(),
        RecipeValue::Status(value) => value.to_be_bytes().to_vec(),
        RecipeValue::Table { .. } => return Err(CarrierError::Recipe),
    })
}

fn encode_outcome(status: u16, values: &[RecipeValue]) -> Result<Vec<u8>> {
    let mut output = status.to_be_bytes().to_vec();
    if status == 0 {
        for value in values {
            output.extend(encode_value(value)?);
        }
    }
    Ok(output)
}

fn apply_mask(values: &mut [RecipeValue], slots: &BTreeSet<usize>, mask: u8) -> Result<()> {
    for (index, value) in values.iter_mut().enumerate() {
        if !slots.contains(&(index + 1)) {
            continue;
        }
        match value {
            RecipeValue::Uint { width, value } => {
                let bytes =
                    usize::try_from(width.div_ceil(8)).map_err(|_| CarrierError::Arithmetic)?;
                let mut repeated = 0_u64;
                for _ in 0..bytes {
                    repeated = (repeated << 8) | u64::from(mask);
                }
                let width_mask = if *width == 64 {
                    u64::MAX
                } else {
                    (1_u64 << *width) - 1
                };
                *value ^= repeated & width_mask;
            }
            RecipeValue::Bool(value) => *value ^= mask & 1 == 1,
            RecipeValue::Bits { width, packed } => {
                for byte in packed.iter_mut() {
                    *byte ^= mask;
                }
                if *width % 8 != 0 {
                    let keep = 0xff << (8 - *width % 8);
                    *packed.last_mut().ok_or(CarrierError::ManifestShape)? &= keep as u8;
                }
            }
            RecipeValue::Bytes(value) => {
                for byte in value {
                    *byte ^= mask;
                }
            }
            _ => return Err(CarrierError::ManifestShape),
        }
    }
    Ok(())
}

fn encode_values(values: &[RecipeValue]) -> Result<Vec<u8>> {
    let mut output = Vec::new();
    for value in values {
        output.extend(encode_value(value)?);
    }
    Ok(output)
}

fn route_record(stage: u8, kind: u8, record_id: u16, payload: &[u8]) -> Result<Vec<u8>> {
    let mut raw = Vec::with_capacity(8 + payload.len());
    raw.push(stage);
    raw.push(kind);
    raw.extend_from_slice(&record_id.to_be_bytes());
    be_u32(&mut raw, payload.len())?;
    raw.extend_from_slice(payload);
    Ok(raw)
}

fn example_for_profile<'a>(
    root: &'a ManifestValue,
    fact_id: u64,
    profile: CandidateProfile,
) -> Result<&'a ManifestValue> {
    let examples = field(root, "examples")?;
    let key = match fact_id {
        8 => "transport",
        9 => "mapping",
        11 => "section_check",
        _ => "common",
    };
    for row in array(field(examples, key)?)? {
        let candidate = object(row)?.get("value").unwrap_or(row);
        if unsigned(field(candidate, "fact_id")?)? != fact_id {
            continue;
        }
        let selected = match key {
            "transport" | "mapping" => {
                unsigned(field(row, "profile_version")?)? == u64::from(profile.version)
            }
            "section_check" => {
                text(field(row, "section_check_id")?)?
                    == if profile.section_check_id == 1 {
                        "crc32c-v0"
                    } else {
                        "crc64-ecma-v0"
                    }
            }
            _ => true,
        };
        if selected {
            return Ok(candidate);
        }
    }
    Err(CarrierError::ManifestShape)
}

fn evaluated_example(
    example: &ManifestValue,
    package: &RecipePackage,
    which: &str,
    mask: u8,
    sector: usize,
) -> Result<(Vec<u8>, Vec<u8>)> {
    let input_shapes = shapes(example, "inputs")?;
    let sector_key = format!("{which}_sector_inputs_hex");
    let input_hex = if let Some(rows) = object(example)?.get(&sector_key) {
        text(
            array(rows)?
                .get(sector)
                .ok_or(CarrierError::ManifestShape)?,
        )?
    } else {
        text(field(example, &format!("{which}_input_hex"))?)?
    };
    let mut values = decode_values(&decode_hex(input_hex)?, &input_shapes)?;
    let mask_slots = array(field(example, "mask_input_slots")?)?
        .iter()
        .map(|value| usize::try_from(unsigned(value)?).map_err(|_| CarrierError::ManifestShape))
        .collect::<Result<BTreeSet<_>>>()?;
    apply_mask(&mut values, &mask_slots, mask)?;
    let input = encode_values(&values)?;
    let recipe_id = u16::try_from(unsigned(field(example, "recipe_id")?)?)
        .map_err(|_| CarrierError::ManifestShape)?;
    let outcome = evaluate_recipe(package, recipe_id, &values).map_err(|_| CarrierError::Recipe)?;
    if outcome.status != 0 {
        return Err(CarrierError::Recipe);
    }
    let output = encode_outcome(outcome.status, &outcome.outputs)?;
    let sector_output_key = format!("{which}_sector_outputs_hex");
    if let Some(rows) = object(example)?.get(&sector_output_key) {
        let expected = decode_hex(text(
            array(rows)?
                .get(sector)
                .ok_or(CarrierError::ManifestShape)?,
        )?)?;
        if output != expected {
            return Err(CarrierError::Recipe);
        }
    }
    Ok((input, output))
}

fn transport_example(
    example: &ManifestValue,
    package: &RecipePackage,
    sector: usize,
    which: &str,
) -> Result<(Vec<u8>, Vec<u8>)> {
    let source_key = format!("{which}_sector_sources_hex");
    let sources = array(field(example, &source_key)?)?;
    let source = decode_hex(text(
        sources.get(sector).ok_or(CarrierError::ManifestShape)?,
    )?)?;
    let encoded = evaluate_recipe(package, 108, &[RecipeValue::Bytes(source.clone())])
        .map_err(|_| CarrierError::Recipe)?;
    if encoded.status != 0 || encoded.outputs.len() != 1 {
        return Err(CarrierError::Recipe);
    }
    let RecipeValue::Bytes(mut observed) = encoded.outputs[0].clone() else {
        return Err(CarrierError::Recipe);
    };
    let offset = usize::try_from(unsigned(field(
        example,
        &format!("{which}_damage_offset"),
    )?)?)
    .map_err(|_| CarrierError::ManifestShape)?;
    let xor = u8::try_from(unsigned(field(example, &format!("{which}_damage_xor"))?)?)
        .map_err(|_| CarrierError::ManifestShape)?;
    *observed
        .get_mut(offset)
        .ok_or(CarrierError::ManifestShape)? ^= xor;
    let erasure_capacity = usize::try_from(unsigned(field(example, "erasure_capacity")?)?)
        .map_err(|_| CarrierError::ManifestShape)?;
    let mut input = observed.clone();
    input.push(0);
    input.resize(input.len() + erasure_capacity, 0);
    let outcome = evaluate_recipe(
        package,
        30,
        &[
            RecipeValue::Bytes(observed),
            RecipeValue::Bytes(vec![0]),
            RecipeValue::Bytes(vec![0; erasure_capacity]),
        ],
    )
    .map_err(|_| CarrierError::Recipe)?;
    if outcome.status != 0 || outcome.outputs != [RecipeValue::Bytes(source.clone())] {
        return Err(CarrierError::Recipe);
    }
    Ok((input, encode_outcome(outcome.status, &outcome.outputs)?))
}

fn package_table_records(package_raw: &[u8]) -> Result<Vec<Vec<u8>>> {
    if package_raw.len() < 64 {
        return Err(CarrierError::Recipe);
    }
    let count = usize::from(u16::from_be_bytes([package_raw[18], package_raw[19]]));
    let mut offset = 64_usize;
    let mut output = Vec::with_capacity(count);
    for _ in 0..count {
        let header = package_raw
            .get(offset..offset + 16)
            .ok_or(CarrierError::Recipe)?;
        let payload = usize::try_from(u32::from_be_bytes(header[12..16].try_into().unwrap()))
            .map_err(|_| CarrierError::Arithmetic)?;
        let end = offset
            .checked_add(16)
            .and_then(|value| value.checked_add(payload))
            .ok_or(CarrierError::Arithmetic)?;
        output.push(
            package_raw
                .get(offset..end)
                .ok_or(CarrierError::Recipe)?
                .to_vec(),
        );
        offset = end;
    }
    Ok(output)
}

fn record_owner(kind: u8) -> ShellOwner {
    match kind {
        2 | 3 => ShellOwner::Example,
        5 => ShellOwner::Recipe,
        _ => ShellOwner::Instruction,
    }
}

fn route_prefix(
    root: &ManifestValue,
    profile: CandidateProfile,
    package: &RecipePackage,
    package_raw: &[u8],
    sector: usize,
    route_version: u16,
    legacy_transport_examples: bool,
) -> Result<(Vec<u8>, Vec<(ShellOwner, usize)>)> {
    let mut records = Vec::new();
    let mut spans = Vec::new();
    let base = u16::try_from(sector * 10_000).map_err(|_| CarrierError::Arithmetic)?;
    let facts = array(field(root, "facts")?)?;
    if facts.len() != 12 {
        return Err(CarrierError::ManifestShape);
    }
    for fact in facts {
        let fact_id = u16::try_from(unsigned(field(fact, "fact_id")?)?)
            .map_err(|_| CarrierError::ManifestShape)?;
        let stage = u8::try_from(unsigned(field(fact, "stage")?)?)
            .map_err(|_| CarrierError::ManifestShape)?;
        let definition = field(fact, "definition")?;
        if u16::try_from(unsigned(field(definition, "value_id")?)?).ok() != Some(fact_id) {
            return Err(CarrierError::ManifestShape);
        }
        let mut define = fact_id.to_be_bytes().to_vec();
        define.extend_from_slice(&fact_id.to_be_bytes());
        define.push(
            u8::try_from(unsigned(field(definition, "type")?)?)
                .map_err(|_| CarrierError::ManifestShape)?,
        );
        define.push(0);
        define.extend_from_slice(
            &u32::try_from(unsigned(field(definition, "width")?)?)
                .map_err(|_| CarrierError::ManifestShape)?
                .to_be_bytes(),
        );
        define.extend_from_slice(
            &u32::try_from(unsigned(field(definition, "count")?)?)
                .map_err(|_| CarrierError::ManifestShape)?
                .to_be_bytes(),
        );
        define.extend(decode_hex(text(field(definition, "value_hex")?)?)?);
        let define_id = base
            .checked_add(fact_id * 100 + 1)
            .ok_or(CarrierError::Arithmetic)?;
        let raw = route_record(stage, 1, define_id, &define)?;
        spans.push((record_owner(1), raw.len() * 8));
        records.extend(raw);

        let example = example_for_profile(root, u64::from(fact_id), profile)?;
        for (ordinal, (which, kind)) in [("worked", 2_u8), ("held", 3_u8)].into_iter().enumerate() {
            let (input, output) = if fact_id == 8 && legacy_transport_examples {
                transport_example(example, package, sector, which)?
            } else {
                evaluated_example(example, package, which, SECTOR_MASKS[sector], sector)?
            };
            let recipe_id = u16::try_from(unsigned(field(example, "recipe_id")?)?)
                .map_err(|_| CarrierError::ManifestShape)?;
            let mut payload = Vec::new();
            payload.extend_from_slice(&fact_id.to_be_bytes());
            payload.extend_from_slice(&recipe_id.to_be_bytes());
            be_u32(&mut payload, input.len())?;
            be_u32(&mut payload, output.len())?;
            payload.extend(input);
            payload.extend(output);
            let record_id = base
                .checked_add(fact_id * 100 + 2 + ordinal as u16)
                .ok_or(CarrierError::Arithmetic)?;
            let raw = route_record(stage, kind, record_id, &payload)?;
            spans.push((record_owner(kind), raw.len() * 8));
            records.extend(raw);
        }
    }
    for (index, table) in package_table_records(package_raw)?.iter().enumerate() {
        let id = base
            .checked_add(5_001 + u16::try_from(index).map_err(|_| CarrierError::Arithmetic)?)
            .ok_or(CarrierError::Arithmetic)?;
        let raw = route_record(5, 4, id, table)?;
        spans.push((ShellOwner::Instruction, raw.len() * 8));
        records.extend(raw);
    }
    let raw = route_record(
        5,
        5,
        base.checked_add(6_001).ok_or(CarrierError::Arithmetic)?,
        package_raw,
    )?;
    spans.push((ShellOwner::Recipe, raw.len() * 8));
    records.extend(raw);
    let raw = route_record(
        5,
        6,
        base.checked_add(7_001).ok_or(CarrierError::Arithmetic)?,
        &1_u32.to_be_bytes(),
    )?;
    spans.push((ShellOwner::Instruction, raw.len() * 8));
    records.extend(raw);
    let raw = route_record(
        5,
        7,
        base.checked_add(7_002).ok_or(CarrierError::Arithmetic)?,
        &[],
    )?;
    spans.push((ShellOwner::Instruction, raw.len() * 8));
    records.extend(raw);

    let table_count = package_table_records(package_raw)?.len();
    let record_count = 36_usize
        .checked_add(table_count)
        .and_then(|value| value.checked_add(3))
        .ok_or(CarrierError::Arithmetic)?;
    let prefix_cells = (64_usize)
        .checked_add(records.len())
        .and_then(|value| value.checked_mul(8))
        .ok_or(CarrierError::Arithmetic)?;
    let mut envelope = Vec::with_capacity(32);
    envelope.extend_from_slice(ROUTE_MAGIC);
    envelope.extend_from_slice(&route_version.to_be_bytes());
    envelope.push(sector as u8);
    envelope.push(sector as u8);
    envelope.extend_from_slice(&profile.version.to_be_bytes());
    be_u16(&mut envelope, record_count)?;
    be_u32(&mut envelope, records.len())?;
    be_u32(&mut envelope, package_raw.len())?;
    be_u32(&mut envelope, prefix_cells)?;
    envelope.extend_from_slice(&(DISCRIMINATOR_CELLS as u16).to_be_bytes());
    envelope.extend_from_slice(&0_u16.to_be_bytes());
    if envelope.len() != 32 {
        return Err(CarrierError::Arithmetic);
    }
    let mut prefix = CALIBRATIONS[sector].to_vec();
    prefix.extend_from_slice(&envelope);
    prefix.extend(records);
    let mut owners = vec![
        (ShellOwner::Instruction, 256),
        (ShellOwner::Instruction, 256),
    ];
    owners.extend(spans);
    if prefix.len() * 8 != prefix_cells
        || owners.iter().map(|row| row.1).sum::<usize>() != prefix_cells
    {
        return Err(CarrierError::Ownership);
    }
    Ok((prefix, owners))
}

/// Independently build the four complete route sectors for a P6-surviving profile.
pub fn build_route_images(
    route_manifest_raw: &[u8],
    profile_version: u16,
    recipe_package_raw: &[u8],
    side: u16,
    shell_width: u16,
) -> Result<RouteImages> {
    if route_manifest_raw.len() > OWNER_DOCUMENT_BYTES_MAX
        || recipe_package_raw.len() > OWNER_DOCUMENT_BYTES_MAX
    {
        return Err(CarrierError::Parameter);
    }
    if digest(route_manifest_raw) != ROUTE_DATA_SHA256 {
        return Err(CarrierError::OwnerIdentity);
    }
    let root =
        validate_canonical_manifest(route_manifest_raw).map_err(|_| CarrierError::ManifestShape)?;
    if text(field(&root, "schema")?)? != "golden-board.route-data/v0"
        || unsigned(field(&root, "side")?)? != 2_048
        || unsigned(field(&root, "shell_width")?)? != 128
        || unsigned(field(&root, "sector_capacity_bytes")?)? != MAX_ROUTE_CAPACITY_BYTES as u64
        || unsigned(field(&root, "discriminator_cells")?)? != DISCRIMINATOR_CELLS as u64
    {
        return Err(CarrierError::ManifestShape);
    }
    let profile = profile_by_version(profile_version).ok_or(CarrierError::Parameter)?;
    if !matches!(profile.version, 1 | 3) || profile.transport != TransportFamily::Eh72Replicated {
        return Err(CarrierError::Parameter);
    }
    let promoted_package =
        build_eh_recipe_package(profile_version).map_err(|_| CarrierError::Recipe)?;
    if recipe_package_raw != promoted_package {
        return Err(CarrierError::OwnerIdentity);
    }
    let _map = AffineMap::derive(side, shell_width, profile_version)?;
    build_route_images_from_value(
        &root,
        profile,
        recipe_package_raw,
        side,
        shell_width,
        ROUTE_VERSION,
        true,
    )
}

fn build_route_images_from_value(
    root: &ManifestValue,
    profile: CandidateProfile,
    recipe_package_raw: &[u8],
    side: u16,
    shell_width: u16,
    route_version: u16,
    legacy_transport_examples: bool,
) -> Result<RouteImages> {
    let sector_cells = usize::from(shell_width)
        .checked_mul(
            usize::from(side)
                .checked_sub(usize::from(shell_width))
                .ok_or(CarrierError::Geometry)?,
        )
        .ok_or(CarrierError::Arithmetic)?;
    let package = decode_recipe_package(recipe_package_raw, profile.version)
        .map_err(|_| CarrierError::Recipe)?;
    let mut prefixes = Vec::with_capacity(4);
    let mut instruction_cells = 0_usize;
    for sector in 0..4 {
        let prefix = route_prefix(
            root,
            profile,
            &package,
            recipe_package_raw,
            sector,
            route_version,
            legacy_transport_examples,
        )?;
        instruction_cells = instruction_cells
            .checked_add(prefix.0.len() * 8)
            .ok_or(CarrierError::Arithmetic)?;
        prefixes.push(prefix);
    }
    let headroom_cells = ((instruction_cells + 19) / 20).max(4 * DISCRIMINATOR_CELLS);
    let remaining = headroom_cells - 4 * DISCRIMINATOR_CELLS;
    let quotient = remaining / 4;
    let remainder = remaining % 4;
    let mut sectors = Vec::with_capacity(4);
    for (sector, (prefix, mut owners)) in prefixes.into_iter().enumerate() {
        let prefix_cells = prefix.len() * 8;
        let assigned_headroom = DISCRIMINATOR_CELLS + quotient + usize::from(sector < remainder);
        if prefix_cells
            .checked_add(assigned_headroom)
            .ok_or(CarrierError::Arithmetic)?
            > sector_cells
        {
            return Err(CarrierError::RouteFit);
        }
        let mut bits = bytes_to_bits(&prefix);
        bits.extend(bytes_to_bits(&CALIBRATIONS[sector]));
        let generated = sector_cells - prefix_cells - DISCRIMINATOR_CELLS;
        bits.extend(shell_pad_bits(profile.version, sector as u8, generated)?);
        owners.push((ShellOwner::Headroom, assigned_headroom));
        owners.push((
            ShellOwner::FixedPad,
            sector_cells - prefix_cells - assigned_headroom,
        ));
        let mut first = 0_u64;
        let spans = owners
            .into_iter()
            .map(|(owner, count)| {
                let span = ShellSpan {
                    first_cell: first,
                    cell_count: count as u64,
                    owner,
                };
                first += count as u64;
                span
            })
            .collect::<Vec<_>>();
        if bits.len() != sector_cells || first != bits.len() as u64 {
            return Err(CarrierError::Ownership);
        }
        sectors.push(SectorImage {
            sector_id: sector as u8,
            bits,
            route_prefix_cells: prefix_cells as u64,
            headroom_cells: assigned_headroom as u64,
            spans,
        });
    }
    Ok(RouteImages {
        instruction_cells: instruction_cells as u64,
        headroom_cells: headroom_cells as u64,
        sectors: sectors.try_into().map_err(|_| CarrierError::Arithmetic)?,
    })
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct R3RouteGeneration {
    /// Canonical v1 route-data template. Its `generated` object is deliberately
    /// empty until the independent reproduction and malformed-corpus owners
    /// provide their exact bindings, so these bytes are never promotable.
    pub route_data_template: Vec<u8>,
    pub route_data_template_sha256: String,
    pub recipient_package: Vec<u8>,
    pub recipient_package_sha256: String,
    pub route_sha256: String,
    pub route_prefixes: [Vec<u8>; 4],
    pub route_prefix_sha256_by_sector: [String; 4],
    pub worked_record_bytes_by_sector: [u64; 4],
    pub held_out_record_bytes_by_sector: [u64; 4],
    pub side: u16,
    pub shell_width: u16,
    pub sector_capacity_bytes: u64,
    pub mapping: HierarchicalMap,
    pub route_images: RouteImages,
    pub logical_group_count: u64,
    pub factor_1_group_count: u64,
    pub factor_2_group_count: u64,
    pub factor_5_group_count: u64,
    pub load_fragment_counts: Vec<u64>,
    pub load_payload_bytes: Vec<u64>,
    pub inventory_entry_count: u64,
    pub inventory_dependency_count: u64,
    pub inventory_payload_bytes: u64,
    pub inventory_fragment_count: u64,
    pub receipt: Vec<u8>,
    pub receipt_sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct R3MalformedRouteCase {
    pub case_id: String,
    pub mutant: Vec<u8>,
    pub mutant_sha256: String,
}

/// Complete, independently reproducible v7 route owner inputs.  Construction
/// is result-free: it emits route/package bytes and owner receipts, but never
/// constructs an interior carrier or evaluates a damage case.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct R3RouteOwnerGeneration {
    pub draft: R3RouteGeneration,
    pub route_data: Vec<u8>,
    pub route_data_sha256: String,
    pub reproduction_projection: Vec<u8>,
    pub reproduction_projection_sha256: String,
    pub python_reproduction_receipt: Vec<u8>,
    pub python_reproduction_sha256: String,
    pub rust_reproduction_receipt: Vec<u8>,
    pub rust_reproduction_sha256: String,
    pub malformed_corpus: Vec<u8>,
    pub malformed_corpus_sha256: String,
    pub malformed_cases: Vec<R3MalformedRouteCase>,
    pub examined_pair_count: u64,
    pub total_pair_count: u64,
    pub predecessor_side: u16,
    pub predecessor_shell_width: u16,
    pub predecessor_reason: String,
}

fn value_shape(kind: u64, width: u64) -> ManifestValue {
    manifest_object([
        ("type", ManifestValue::U64(kind)),
        ("width", ManifestValue::U64(width)),
    ])
}

fn manifest_strings(values: &[&str]) -> ManifestValue {
    manifest_array(values.iter().map(|value| manifest_string(*value)))
}

fn r3_profile_row(
    profile_id: &str,
    profile_version: u64,
    section_check_id: &str,
    transport_id: &str,
    candidate: bool,
    fixture: bool,
) -> ManifestValue {
    manifest_object([
        ("candidate", ManifestValue::Bool(candidate)),
        ("fixture", ManifestValue::Bool(fixture)),
        ("profile_id", manifest_string(profile_id)),
        ("profile_version", ManifestValue::U64(profile_version)),
        ("section_check_id", manifest_string(section_check_id)),
        ("transport_id", manifest_string(transport_id)),
    ])
}

fn set_r3_fact(
    facts: &mut [ManifestValue],
    fact_id: u64,
    name: &str,
    consumes: &[u64],
    recipe_id: u64,
) -> Result<()> {
    let fact = facts
        .iter_mut()
        .find(|row| field(row, "fact_id").and_then(unsigned).ok() == Some(fact_id))
        .ok_or(CarrierError::ManifestShape)?;
    let row = object_mut(fact)?;
    row.insert("name".to_owned(), manifest_string(name));
    row.insert(
        "consumes".to_owned(),
        manifest_array(consumes.iter().copied().map(ManifestValue::U64)),
    );
    row.insert("recipe_id".to_owned(), ManifestValue::U64(recipe_id));
    let definition = object_mut(
        row.get_mut("definition")
            .ok_or(CarrierError::ManifestShape)?,
    )?;
    definition.insert("width".to_owned(), ManifestValue::U64(name.len() as u64));
    definition.insert(
        "value_hex".to_owned(),
        manifest_string(encode_hex(name.as_bytes())),
    );
    Ok(())
}

fn r3_route_data_template_value() -> Result<ManifestValue> {
    let base = include_bytes!("../../../spec/route-data-v0.json");
    if digest(base) != ROUTE_DATA_SHA256 {
        return Err(CarrierError::OwnerIdentity);
    }
    let mut root = validate_canonical_manifest(base).map_err(|_| CarrierError::ManifestShape)?;
    let root = object_mut(&mut root)?;
    root.insert(
        "schema".to_owned(),
        manifest_string("golden-board.route-data/v1"),
    );
    root.insert("route_version".to_owned(), ManifestValue::U64(1));
    root.insert(
        "recipe_export_ids".to_owned(),
        manifest_array(
            std::iter::once(30_u64)
                .chain(101_u64..=113)
                .map(ManifestValue::U64),
        ),
    );
    root.insert(
        "profiles".to_owned(),
        manifest_array([
            r3_profile_row(
                "eh72-hier-r5-r2-r1-crc32c-v0",
                7,
                "crc32c-v0",
                "eh72-hier-repetition-v0",
                true,
                false,
            ),
            r3_profile_row(
                "eh72-r2-crc64-ecma-v0",
                2,
                "crc64-ecma-v0",
                "eh72-replicated-v0",
                false,
                true,
            ),
            r3_profile_row(
                "eh72-r3-crc32c-v0",
                3,
                "crc32c-v0",
                "eh72-replicated-v0",
                false,
                true,
            ),
            r3_profile_row(
                "eh72-r3-crc64-ecma-v0",
                4,
                "crc64-ecma-v0",
                "eh72-replicated-v0",
                false,
                true,
            ),
            r3_profile_row(
                "rs255-191-crc32c-v0",
                5,
                "crc32c-v0",
                "rs255-191-v0",
                false,
                true,
            ),
            r3_profile_row(
                "rs255-191-crc64-ecma-v0",
                6,
                "crc64-ecma-v0",
                "rs255-191-v0",
                false,
                true,
            ),
        ]),
    );
    let facts = array_mut(root.get_mut("facts").ok_or(CarrierError::ManifestShape)?)?;
    set_r3_fact(facts, 8, "eh72-hier-repetition-v1", &[6, 7], 113)?;
    set_r3_fact(facts, 9, "slot-affine-adapter-v1", &[6, 8], 109)?;
    set_r3_fact(facts, 10, "group-fragment-adapter-v1", &[7, 8, 9], 110)?;

    let old_examples = root
        .get("examples")
        .ok_or(CarrierError::ManifestShape)?
        .clone();
    let common = field(&old_examples, "common")?.clone();
    let section_check = array(field(&old_examples, "section_check")?)?
        .iter()
        .find(|row| field(row, "section_check_id").and_then(text).ok() == Some("crc32c-v0"))
        .cloned()
        .ok_or(CarrierError::ManifestShape)?;
    let mut mapping = array(field(&old_examples, "mapping")?)?
        .iter()
        .find(|row| field(row, "profile_version").and_then(unsigned).ok() == Some(1))
        .cloned()
        .ok_or(CarrierError::ManifestShape)?;
    let mapping_row = object_mut(&mut mapping)?;
    mapping_row.insert("profile_version".to_owned(), ManifestValue::U64(7));
    let mapping_value = object_mut(
        mapping_row
            .get_mut("value")
            .ok_or(CarrierError::ManifestShape)?,
    )?;
    mapping_value.insert(
        "worked_output_hex".to_owned(),
        manifest_string("00000004d401"),
    );
    mapping_value.insert(
        "held_output_hex".to_owned(),
        manifest_string("0000002971c1"),
    );
    let transport = manifest_object([
        ("fact_id", ManifestValue::U64(8)),
        (
            "held_sector_inputs_hex",
            manifest_strings(&["050203", "020001", "050001", "050202"]),
        ),
        (
            "held_sector_outputs_hex",
            manifest_strings(&["00000101", "00000101", "00000101", "00000000"]),
        ),
        (
            "inputs",
            manifest_array([value_shape(0, 8), value_shape(0, 8), value_shape(0, 8)]),
        ),
        ("mask_input_slots", manifest_array([])),
        (
            "outputs",
            manifest_array([value_shape(1, 1), value_shape(1, 1)]),
        ),
        ("profile_version", ManifestValue::U64(7)),
        ("recipe_id", ManifestValue::U64(113)),
        (
            "support_recipe_ids",
            manifest_array([ManifestValue::U64(30), ManifestValue::U64(108)]),
        ),
        ("transport_id", manifest_string("eh72-hier-repetition-v0")),
        (
            "worked_sector_inputs_hex",
            manifest_strings(&["050302", "020100", "050100", "020101"]),
        ),
        (
            "worked_sector_outputs_hex",
            manifest_strings(&["00000100", "00000100", "00000100", "00000000"]),
        ),
    ]);
    let owner_fixture_raw = include_bytes!("../../../conformance/m2-r3-owner-v1.json");
    let examples = manifest_object([
        ("common", common),
        ("mapping", manifest_array([mapping])),
        (
            "owner_fixture",
            manifest_object([
                ("path", manifest_string("conformance/m2-r3-owner-v1.json")),
                (
                    "schema",
                    manifest_string("golden-board.m2-r3-owner-fixtures/v1"),
                ),
                ("sha256", manifest_string(digest(owner_fixture_raw))),
            ]),
        ),
        ("section_check", manifest_array([section_check])),
        ("transport", manifest_array([transport])),
    ]);
    root.insert("examples".to_owned(), examples);
    // This exact absence is the explicit pre-promotion barrier. The separate
    // receipt names every Rust-derived value without pretending the missing
    // Python/malformed-corpus bindings exist.
    root.insert(
        "generated".to_owned(),
        ManifestValue::Object(BTreeMap::new()),
    );
    Ok(ManifestValue::Object(std::mem::take(root)))
}

fn r3_route_prefix_bytes(routes: &RouteImages) -> Result<[Vec<u8>; 4]> {
    routes
        .sectors
        .iter()
        .map(|sector| {
            let cells =
                usize::try_from(sector.route_prefix_cells).map_err(|_| CarrierError::Arithmetic)?;
            packed_bits(sector.bits.get(..cells).ok_or(CarrierError::Ownership)?)
        })
        .collect::<Result<Vec<_>>>()?
        .try_into()
        .map_err(|_| CarrierError::Arithmetic)
}

fn route_example_record_bytes(prefix: &[u8]) -> Result<(u64, u64)> {
    if prefix.len() < 64 {
        return Err(CarrierError::RouteFit);
    }
    let mut worked = 0_u64;
    let mut held = 0_u64;
    let mut offset = 64_usize;
    while offset < prefix.len() {
        let header = prefix
            .get(offset..offset + 8)
            .ok_or(CarrierError::RouteFit)?;
        let payload = usize::try_from(u32::from_be_bytes(header[4..8].try_into().unwrap()))
            .map_err(|_| CarrierError::Arithmetic)?;
        let record = 8_usize
            .checked_add(payload)
            .ok_or(CarrierError::Arithmetic)?;
        let end = offset.checked_add(record).ok_or(CarrierError::Arithmetic)?;
        if end > prefix.len() {
            return Err(CarrierError::RouteFit);
        }
        match header[1] {
            2 => {
                worked = worked
                    .checked_add(u64::try_from(record).map_err(|_| CarrierError::Arithmetic)?)
                    .ok_or(CarrierError::Arithmetic)?;
            }
            3 => {
                held = held
                    .checked_add(u64::try_from(record).map_err(|_| CarrierError::Arithmetic)?)
                    .ok_or(CarrierError::Arithmetic)?;
            }
            _ => {}
        }
        offset = end;
    }
    Ok((worked, held))
}

/// Independently render the non-promotable v7 route-data template, exact
/// route prefixes, first-fit shell/placement projection, and a canonical Rust
/// receipt. This is pre-result route work and never constructs a carrier.
pub fn generate_r3_route_draft() -> Result<R3RouteGeneration> {
    let mut template = r3_route_data_template_value()?;
    let profile = profile_by_version(7).ok_or(CarrierError::Parameter)?;
    let recipient_package = build_eh_recipe_package(7).map_err(|_| CarrierError::Recipe)?;
    let maximum_routes = build_route_images_from_value(
        &template,
        profile,
        &recipient_package,
        2_048,
        128,
        1,
        false,
    )?;
    let prefix_cells = maximum_routes
        .sectors
        .iter()
        .map(|sector| sector.route_prefix_cells)
        .collect::<Vec<_>>();
    if prefix_cells.iter().any(|cells| *cells != prefix_cells[0]) {
        return Err(CarrierError::Ownership);
    }
    let mut selected = None;
    for (side, shell_width) in pair_order() {
        let Ok(mapping) = HierarchicalMap::derive(side, shell_width) else {
            continue;
        };
        if mapping.unit_slot_count < 1_465 {
            continue;
        }
        let sector_cells = u64::from(shell_width)
            .checked_mul(u64::from(side - shell_width))
            .ok_or(CarrierError::Arithmetic)?;
        if maximum_routes
            .sectors
            .iter()
            .any(|sector| sector.route_prefix_cells + sector.headroom_cells > sector_cells)
        {
            continue;
        }
        selected = Some((side, shell_width, mapping));
        break;
    }
    let (side, shell_width, mapping) = selected.ok_or(CarrierError::Geometry)?;
    let slots = mapping.unit_slot_count;
    let load_fragments = slots.checked_sub(1_465).ok_or(CarrierError::Geometry)?;
    let mut remaining = load_fragments;
    let mut load_fragment_counts = Vec::new();
    while remaining != 0 {
        let count = remaining.min(105);
        load_fragment_counts.push(count);
        remaining -= count;
    }
    let load_payload_bytes = load_fragment_counts
        .iter()
        .map(|fragments| load_payload_for_fragments(*fragments, MAXIMUM_PROBE_PAYLOAD, 4))
        .collect::<Result<Vec<_>>>()?
        .into_iter()
        .map(|value| u64::try_from(value).map_err(|_| CarrierError::Arithmetic))
        .collect::<Result<Vec<_>>>()?;
    // Exact v1 entry ledger before load: inventory 1 + tiers 2 + real 77 +
    // capacity 53 + reserve 1 = 134. Only the two tier frames carry
    // dependencies: 1 + 77 = 78. Every load section adds one dependency-free
    // 20-byte entry, so this derives (rather than extrapolates) the payload.
    let inventory_dependency_count = 78_u64;
    let inventory_entry_count = 134_u64
        .checked_add(
            u64::try_from(load_fragment_counts.len()).map_err(|_| CarrierError::Arithmetic)?,
        )
        .ok_or(CarrierError::Arithmetic)?;
    let inventory_payload_bytes = 8_u64
        .checked_add(
            inventory_entry_count
                .checked_mul(20)
                .ok_or(CarrierError::Arithmetic)?,
        )
        .and_then(|value| value.checked_add(inventory_dependency_count * 4))
        .ok_or(CarrierError::Arithmetic)?;
    let inventory_fragment_count = section_fragment_count(&LogicalSection {
        section_id: 1,
        section_type: SECTION_INVENTORY,
        section_version: 1,
        closure_class: CLOSURE_M2_REQUIRED,
        check_id: CHECK_CRC32C,
        copy_count: 1,
        dependencies: Vec::new(),
        game_ordinal: None,
        payload: vec![
            0;
            usize::try_from(inventory_payload_bytes)
                .map_err(|_| CarrierError::Arithmetic)?
        ],
    })?;
    if inventory_fragment_count != 20 {
        return Err(CarrierError::Geometry);
    }
    let root = object_mut(&mut template)?;
    root.insert("side".to_owned(), ManifestValue::U64(u64::from(side)));
    root.insert(
        "shell_width".to_owned(),
        ManifestValue::U64(u64::from(shell_width)),
    );
    let sector_capacity_bytes = u64::from(shell_width)
        .checked_mul(u64::from(side - shell_width))
        .ok_or(CarrierError::Arithmetic)?
        / 8;
    root.insert(
        "sector_capacity_bytes".to_owned(),
        ManifestValue::U64(sector_capacity_bytes),
    );
    let route_data_template =
        serialize_manifest(&template).map_err(|_| CarrierError::ManifestShape)?;
    validate_canonical_manifest(&route_data_template).map_err(|_| CarrierError::ManifestShape)?;
    let route_images = build_route_images_from_value(
        &template,
        profile,
        &recipient_package,
        side,
        shell_width,
        1,
        false,
    )?;
    let route_prefixes = r3_route_prefix_bytes(&route_images)?;
    let route_prefix_sha256_by_sector = route_prefixes.each_ref().map(|raw| digest(raw));
    let example_record_bytes = route_prefixes
        .each_ref()
        .map(|prefix| route_example_record_bytes(prefix))
        .into_iter()
        .collect::<Result<Vec<_>>>()?;
    let worked_record_bytes_by_sector: [u64; 4] = example_record_bytes
        .iter()
        .map(|row| row.0)
        .collect::<Vec<_>>()
        .try_into()
        .map_err(|_| CarrierError::Arithmetic)?;
    let held_out_record_bytes_by_sector: [u64; 4] = example_record_bytes
        .iter()
        .map(|row| row.1)
        .collect::<Vec<_>>()
        .try_into()
        .map_err(|_| CarrierError::Arithmetic)?;
    let route_concat = route_prefixes.concat();
    let route_sha256 = digest(&route_concat);
    let package = decode_recipe_package(&recipient_package, 7).map_err(|_| CarrierError::Recipe)?;
    let route_prefix_cells_by_sector = route_images
        .sectors
        .iter()
        .map(|sector| ManifestValue::U64(sector.route_prefix_cells))
        .collect::<Vec<_>>();
    let route_headroom_cells_by_sector = route_images
        .sectors
        .iter()
        .map(|sector| ManifestValue::U64(sector.headroom_cells))
        .collect::<Vec<_>>();
    let receipt_value = manifest_object([
        (
            "schema",
            manifest_string("golden-board.r3-route-rust-receipt/v1"),
        ),
        ("route_data_complete", ManifestValue::Bool(false)),
        (
            "missing_generated_bindings",
            manifest_strings(&[
                "malformed_corpus_sha256",
                "python_reproduction_sha256",
                "worked_held_out_bytes",
            ]),
        ),
        ("side", ManifestValue::U64(u64::from(side))),
        ("shell_width", ManifestValue::U64(u64::from(shell_width))),
        (
            "sector_capacity_bytes",
            ManifestValue::U64(sector_capacity_bytes),
        ),
        ("route_sha256", manifest_string(&route_sha256)),
        (
            "route_prefix_sha256_by_sector",
            manifest_array(route_prefix_sha256_by_sector.iter().map(manifest_string)),
        ),
        (
            "route_prefix_cells_by_sector",
            manifest_array(route_prefix_cells_by_sector),
        ),
        (
            "route_headroom_cells_by_sector",
            manifest_array(route_headroom_cells_by_sector),
        ),
        (
            "worked_record_bytes_by_sector",
            manifest_array(
                worked_record_bytes_by_sector
                    .iter()
                    .copied()
                    .map(ManifestValue::U64),
            ),
        ),
        (
            "held_out_record_bytes_by_sector",
            manifest_array(
                held_out_record_bytes_by_sector
                    .iter()
                    .copied()
                    .map(ManifestValue::U64),
            ),
        ),
        (
            "recipient_package_sha256",
            manifest_string(digest(&recipient_package)),
        ),
        (
            "recipient_package_bytes",
            ManifestValue::U64(recipient_package.len() as u64),
        ),
        (
            "node_count",
            ManifestValue::U64(u64::from_be_bytes([
                0,
                0,
                0,
                0,
                recipient_package[20],
                recipient_package[21],
                recipient_package[22],
                recipient_package[23],
            ])),
        ),
        (
            "edge_count",
            ManifestValue::U64(u64::from_be_bytes([
                0,
                0,
                0,
                0,
                recipient_package[24],
                recipient_package[25],
                recipient_package[26],
                recipient_package[27],
            ])),
        ),
        (
            "table_payload_bytes",
            ManifestValue::U64(u64::from_be_bytes([
                0,
                0,
                0,
                0,
                recipient_package[28],
                recipient_package[29],
                recipient_package[30],
                recipient_package[31],
            ])),
        ),
        (
            "primitive_steps",
            ManifestValue::U64(u64::from_be_bytes(
                recipient_package[36..44].try_into().unwrap(),
            )),
        ),
        (
            "peak_scratch_bytes",
            ManifestValue::U64(u64::from(u32::from_be_bytes(
                recipient_package[44..48].try_into().unwrap(),
            ))),
        ),
        (
            "recipe_113_primitive_steps",
            ManifestValue::U64(
                package
                    .recipe_primitive_steps(113)
                    .ok_or(CarrierError::Recipe)?,
            ),
        ),
        (
            "recipe_113_peak_scratch_bytes",
            ManifestValue::U64(
                package
                    .recipe_peak_scratch_bytes(113)
                    .ok_or(CarrierError::Recipe)?,
            ),
        ),
        (
            "slot_multiplier_table_sha256",
            manifest_string("835717bf400c597a3a9e1b59747f23d93047b6cfab462756fa07d96c5f3eba3f"),
        ),
        (
            "route_data_template_sha256",
            manifest_string(digest(&route_data_template)),
        ),
        ("unit_slot_count", ManifestValue::U64(slots)),
        (
            "logical_group_count",
            ManifestValue::U64(903 + load_fragments),
        ),
        (
            "factor_1_group_count",
            ManifestValue::U64(431 + load_fragments),
        ),
        ("factor_2_group_count", ManifestValue::U64(442)),
        ("factor_5_group_count", ManifestValue::U64(30)),
        (
            "load_fragment_counts",
            manifest_array(load_fragment_counts.iter().copied().map(ManifestValue::U64)),
        ),
        (
            "load_payload_bytes",
            manifest_array(load_payload_bytes.iter().copied().map(ManifestValue::U64)),
        ),
        (
            "inventory_entry_count",
            ManifestValue::U64(inventory_entry_count),
        ),
        (
            "inventory_dependency_count",
            ManifestValue::U64(inventory_dependency_count),
        ),
        (
            "inventory_payload_bytes",
            ManifestValue::U64(inventory_payload_bytes),
        ),
        (
            "inventory_fragment_count",
            ManifestValue::U64(inventory_fragment_count),
        ),
        (
            "slot_multiplier",
            ManifestValue::U64(mapping.slot_multiplier),
        ),
        (
            "inverse_slot_multiplier",
            ManifestValue::U64(mapping.inverse_slot_multiplier),
        ),
        (
            "cell_multiplier",
            ManifestValue::U64(mapping.cell_multiplier),
        ),
        (
            "inverse_cell_multiplier",
            ManifestValue::U64(mapping.inverse_cell_multiplier),
        ),
        ("cell_offset", ManifestValue::U64(mapping.cell_offset)),
        (
            "fixed_pad_cells",
            ManifestValue::U64(mapping.fixed_pad_cells),
        ),
    ]);
    let receipt = serialize_manifest(&receipt_value).map_err(|_| CarrierError::ManifestShape)?;
    validate_canonical_manifest(&receipt).map_err(|_| CarrierError::ManifestShape)?;
    Ok(R3RouteGeneration {
        route_data_template_sha256: digest(&route_data_template),
        route_data_template,
        recipient_package_sha256: digest(&recipient_package),
        recipient_package,
        route_sha256,
        route_prefixes,
        route_prefix_sha256_by_sector,
        worked_record_bytes_by_sector,
        held_out_record_bytes_by_sector,
        side,
        shell_width,
        sector_capacity_bytes,
        mapping,
        route_images,
        logical_group_count: 903 + load_fragments,
        factor_1_group_count: 431 + load_fragments,
        factor_2_group_count: 442,
        factor_5_group_count: 30,
        load_fragment_counts,
        load_payload_bytes,
        inventory_entry_count,
        inventory_dependency_count,
        inventory_payload_bytes,
        inventory_fragment_count,
        receipt_sha256: digest(&receipt),
        receipt,
    })
}

fn route_payload_range(prefix: &[u8], record_id: u16) -> Result<(usize, usize, u8, u8)> {
    if prefix.len() < 64 {
        return Err(CarrierError::RouteFit);
    }
    let record_count = usize::from(u16::from_be_bytes(prefix[46..48].try_into().unwrap()));
    let record_bytes = usize::try_from(u32::from_be_bytes(prefix[48..52].try_into().unwrap()))
        .map_err(|_| CarrierError::Arithmetic)?;
    if prefix.len()
        != 64_usize
            .checked_add(record_bytes)
            .ok_or(CarrierError::Arithmetic)?
    {
        return Err(CarrierError::RouteFit);
    }
    let mut offset = 64_usize;
    let mut found = None;
    for _ in 0..record_count {
        let header = prefix
            .get(offset..offset + 8)
            .ok_or(CarrierError::RouteFit)?;
        let payload_bytes = usize::try_from(u32::from_be_bytes(header[4..8].try_into().unwrap()))
            .map_err(|_| CarrierError::Arithmetic)?;
        let first = offset.checked_add(8).ok_or(CarrierError::Arithmetic)?;
        let end = first
            .checked_add(payload_bytes)
            .ok_or(CarrierError::Arithmetic)?;
        prefix.get(first..end).ok_or(CarrierError::RouteFit)?;
        if u16::from_be_bytes(header[2..4].try_into().unwrap()) == record_id {
            if found.is_some() {
                return Err(CarrierError::RouteFit);
            }
            found = Some((first, end, header[0], header[1]));
        }
        offset = end;
    }
    if offset != prefix.len() {
        return Err(CarrierError::RouteFit);
    }
    found.ok_or(CarrierError::RouteFit)
}

fn package_table_payload_range(package: &[u8], table_id: u16) -> Result<(usize, usize)> {
    if package.len() < 64 {
        return Err(CarrierError::Recipe);
    }
    let table_count = usize::from(u16::from_be_bytes(package[18..20].try_into().unwrap()));
    let mut offset = 64_usize;
    let mut found = None;
    for _ in 0..table_count {
        let header = package
            .get(offset..offset + 16)
            .ok_or(CarrierError::Recipe)?;
        let payload_bytes = usize::try_from(u32::from_be_bytes(header[12..16].try_into().unwrap()))
            .map_err(|_| CarrierError::Arithmetic)?;
        let first = offset.checked_add(16).ok_or(CarrierError::Arithmetic)?;
        let end = first
            .checked_add(payload_bytes)
            .ok_or(CarrierError::Arithmetic)?;
        package.get(first..end).ok_or(CarrierError::Recipe)?;
        if u16::from_be_bytes(header[..2].try_into().unwrap()) == table_id {
            if found.is_some() {
                return Err(CarrierError::Recipe);
            }
            found = Some((first, end));
        }
        offset = end;
    }
    found.ok_or(CarrierError::Recipe)
}

fn package_recipe_range(package: &[u8], recipe_id: u16) -> Result<(usize, usize)> {
    if package.len() < 64 {
        return Err(CarrierError::Recipe);
    }
    let recipe_count = usize::from(u16::from_be_bytes(package[16..18].try_into().unwrap()));
    let table_count = usize::from(u16::from_be_bytes(package[18..20].try_into().unwrap()));
    let mut offset = 64_usize;
    for _ in 0..table_count {
        let header = package
            .get(offset..offset + 16)
            .ok_or(CarrierError::Recipe)?;
        let payload_bytes = usize::try_from(u32::from_be_bytes(header[12..16].try_into().unwrap()))
            .map_err(|_| CarrierError::Arithmetic)?;
        offset = offset
            .checked_add(16)
            .and_then(|value| value.checked_add(payload_bytes))
            .ok_or(CarrierError::Arithmetic)?;
        package.get(..offset).ok_or(CarrierError::Recipe)?;
    }
    let mut found = None;
    for _ in 0..recipe_count {
        let header = package
            .get(offset..offset + 32)
            .ok_or(CarrierError::Recipe)?;
        let recipe_bytes = usize::try_from(u32::from_be_bytes(header[28..32].try_into().unwrap()))
            .map_err(|_| CarrierError::Arithmetic)?;
        let end = offset
            .checked_add(recipe_bytes)
            .ok_or(CarrierError::Arithmetic)?;
        package.get(offset..end).ok_or(CarrierError::Recipe)?;
        if u16::from_be_bytes(header[..2].try_into().unwrap()) == recipe_id {
            if found.is_some() {
                return Err(CarrierError::Recipe);
            }
            found = Some((offset, end));
        }
        offset = end;
    }
    if offset != package.len() {
        return Err(CarrierError::Recipe);
    }
    found.ok_or(CarrierError::Recipe)
}

fn malformed_r3_route_cases(clean: &[u8]) -> Result<Vec<R3MalformedRouteCase>> {
    if clean.len() < 64 {
        return Err(CarrierError::RouteFit);
    }
    let mut rows = Vec::with_capacity(8);
    let mut push = |case_id: &str, mutant: Vec<u8>| {
        rows.push(R3MalformedRouteCase {
            case_id: case_id.to_owned(),
            mutant_sha256: digest(&mutant),
            mutant,
        });
    };

    let mut mutant = clean.to_vec();
    mutant[40..42].copy_from_slice(&0_u16.to_be_bytes());
    push("route-version-zero", mutant);

    let mut mutant = clean.to_vec();
    mutant[44..46].copy_from_slice(&3_u16.to_be_bytes());
    push("profile-version-three", mutant);

    let (_first, end, stage, kind) = route_payload_range(clean, 801)?;
    if stage != 3 || kind != 1 || clean.get(end - 1) != Some(&0x31) {
        return Err(CarrierError::RouteFit);
    }
    let mut mutant = clean.to_vec();
    mutant[end - 1] = 0x30;
    push("fact8-definition-v0", mutant);

    let (first, end, stage, kind) = route_payload_range(clean, 802)?;
    if stage != 3 || kind != 2 || end - first < 4 {
        return Err(CarrierError::RouteFit);
    }
    let mut mutant = clean.to_vec();
    mutant[first + 2..first + 4].copy_from_slice(&30_u16.to_be_bytes());
    push("fact8-worked-recipe30", mutant);

    let (table_first, table_end, stage, kind) = route_payload_range(clean, 5_010)?;
    if stage != 5 || kind != 4 || table_end - table_first != 272 {
        return Err(CarrierError::RouteFit);
    }
    let route_table_payload = table_first + 16;
    if u16::from_be_bytes(clean[table_first..table_first + 2].try_into().unwrap()) != 17 {
        return Err(CarrierError::RouteFit);
    }
    let mut mutant = clean.to_vec();
    mutant[route_table_payload + 223] ^= 0x01;
    push("route-table17-index223-xor01", mutant);

    let (package_first, package_end, stage, kind) = route_payload_range(clean, 6_001)?;
    if stage != 5 || kind != 5 {
        return Err(CarrierError::RouteFit);
    }
    let package = &clean[package_first..package_end];
    let (package_table_first, package_table_end) = package_table_payload_range(package, 17)?;
    if package_table_end - package_table_first != 256 {
        return Err(CarrierError::Recipe);
    }
    let mut mutant = clean.to_vec();
    mutant[route_table_payload + 255] = 0x01;
    mutant[package_first + package_table_first + 255] = 0x01;
    push("both-table17-index255-one", mutant);

    let (recipe_first, _) = package_recipe_range(package, 113)?;
    let mut mutant = clean.to_vec();
    mutant[package_first + recipe_first..package_first + recipe_first + 2]
        .copy_from_slice(&114_u16.to_be_bytes());
    push("package-recipe113-id114", mutant);

    let mut mutant = clean.to_vec();
    mutant[package_first + recipe_first + 36..package_first + recipe_first + 40]
        .copy_from_slice(&7_u32.to_be_bytes());
    push("package-recipe113-input0-width7", mutant);
    Ok(rows)
}

fn r3_load_fixed_point_fits(unit_slots: u64) -> Result<bool> {
    let Some(mut remaining) = unit_slots.checked_sub(1_465) else {
        return Ok(false);
    };
    let mut load_fragments = Vec::new();
    while remaining != 0 {
        let fragments = remaining.min(105);
        if load_payload_for_fragments(fragments, MAXIMUM_PROBE_PAYLOAD, 4).is_err() {
            return Ok(false);
        }
        load_fragments.push(fragments);
        remaining -= fragments;
    }
    let entry_count = 134_u64
        .checked_add(u64::try_from(load_fragments.len()).map_err(|_| CarrierError::Arithmetic)?)
        .ok_or(CarrierError::Arithmetic)?;
    let inventory_payload = 8_u64
        .checked_add(
            entry_count
                .checked_mul(20)
                .ok_or(CarrierError::Arithmetic)?,
        )
        .and_then(|value| value.checked_add(78 * 4))
        .ok_or(CarrierError::Arithmetic)?;
    if inventory_payload > MAXIMUM_PROBE_PAYLOAD {
        return Ok(false);
    }
    let envelope_bytes = 18_u64
        .checked_add(inventory_payload)
        .and_then(|value| value.checked_add(4))
        .ok_or(CarrierError::Arithmetic)?;
    Ok(envelope_bytes.div_ceil(157) == 20)
}

fn r3_first_fit_value(
    draft: &R3RouteGeneration,
) -> Result<(ManifestValue, u64, u64, u16, u16, String)> {
    let total_pair_count =
        u64::try_from(pair_order().count()).map_err(|_| CarrierError::Arithmetic)?;
    let mut examined = 0_u64;
    let mut predecessor: Option<(u16, u16, &'static str)> = None;
    for (side, shell_width) in pair_order() {
        examined = examined.checked_add(1).ok_or(CarrierError::Arithmetic)?;
        let reason = match HierarchicalMap::derive(side, shell_width) {
            Err(_) => Some("no-admissible-map"),
            Ok(mapping) if mapping.unit_slot_count < 1_465 => Some("mandatory-units-do-not-fit"),
            Ok(_)
                if draft.route_images.sectors.iter().any(|sector| {
                    let sector_cells = u64::from(shell_width) * u64::from(side - shell_width);
                    sector.route_prefix_cells + sector.headroom_cells > sector_cells
                }) =>
            {
                Some("route-shell-capacity")
            }
            Ok(mapping) if !r3_load_fixed_point_fits(mapping.unit_slot_count)? => {
                Some("load-fixed-point")
            }
            Ok(mapping) => {
                if side != draft.side
                    || shell_width != draft.shell_width
                    || mapping != draft.mapping
                {
                    return Err(CarrierError::Geometry);
                }
                let (predecessor_side, predecessor_shell_width, predecessor_reason) =
                    predecessor.ok_or(CarrierError::Geometry)?;
                let value = manifest_object([
                    ("examined_pair_count", ManifestValue::U64(examined)),
                    ("predecessor_reason", manifest_string(predecessor_reason)),
                    (
                        "predecessor_shell_width",
                        ManifestValue::U64(u64::from(predecessor_shell_width)),
                    ),
                    (
                        "predecessor_side",
                        ManifestValue::U64(u64::from(predecessor_side)),
                    ),
                    ("selected_pair_ordinal", ManifestValue::U64(examined)),
                    ("total_pair_count", ManifestValue::U64(total_pair_count)),
                ]);
                return Ok((
                    value,
                    examined,
                    total_pair_count,
                    predecessor_side,
                    predecessor_shell_width,
                    predecessor_reason.to_owned(),
                ));
            }
        };
        predecessor = reason.map(|reason| (side, shell_width, reason));
    }
    Err(CarrierError::Geometry)
}

fn r3_capacity_projection_value(draft: &R3RouteGeneration) -> Result<ManifestValue> {
    let physical_unit_count = draft.mapping.unit_slot_count;
    let encoded_transport_bytes = physical_unit_count
        .checked_mul(EH_UNIT_BYTES as u64)
        .ok_or(CarrierError::Arithmetic)?;
    let protected_cells = physical_unit_count
        .checked_mul(R3_UNIT_BITS)
        .ok_or(CarrierError::Arithmetic)?;
    Ok(manifest_object([
        (
            "cell_inverse_multiplier",
            ManifestValue::U64(draft.mapping.inverse_cell_multiplier),
        ),
        (
            "cell_multiplier",
            ManifestValue::U64(draft.mapping.cell_multiplier),
        ),
        ("cell_offset", ManifestValue::U64(draft.mapping.cell_offset)),
        (
            "encoded_transport_bytes",
            ManifestValue::U64(encoded_transport_bytes),
        ),
        (
            "factor_1_group_count",
            ManifestValue::U64(draft.factor_1_group_count),
        ),
        (
            "factor_2_group_count",
            ManifestValue::U64(draft.factor_2_group_count),
        ),
        (
            "factor_5_group_count",
            ManifestValue::U64(draft.factor_5_group_count),
        ),
        ("fixed_logical_group_count", ManifestValue::U64(903)),
        (
            "fixed_pad_cells",
            ManifestValue::U64(draft.mapping.fixed_pad_cells),
        ),
        (
            "interior_side",
            ManifestValue::U64(u64::from(draft.mapping.interior_side)),
        ),
        (
            "inventory_dependency_count",
            ManifestValue::U64(draft.inventory_dependency_count),
        ),
        (
            "inventory_entry_count",
            ManifestValue::U64(draft.inventory_entry_count),
        ),
        (
            "inventory_fragment_count",
            ManifestValue::U64(draft.inventory_fragment_count),
        ),
        (
            "inventory_payload_bytes",
            ManifestValue::U64(draft.inventory_payload_bytes),
        ),
        (
            "load_fragment_counts",
            manifest_array(
                draft
                    .load_fragment_counts
                    .iter()
                    .copied()
                    .map(ManifestValue::U64),
            ),
        ),
        (
            "load_payload_bytes",
            manifest_array(
                draft
                    .load_payload_bytes
                    .iter()
                    .copied()
                    .map(ManifestValue::U64),
            ),
        ),
        (
            "logical_group_count",
            ManifestValue::U64(draft.logical_group_count),
        ),
        ("mandatory_physical_unit_count", ManifestValue::U64(1_465)),
        (
            "physical_unit_count",
            ManifestValue::U64(physical_unit_count),
        ),
        ("population", ManifestValue::U64(draft.mapping.population)),
        ("protected_cells", ManifestValue::U64(protected_cells)),
        (
            "separation_window",
            ManifestValue::U64(u64::from(draft.mapping.window_side)),
        ),
        (
            "slot_inverse_multiplier",
            ManifestValue::U64(draft.mapping.inverse_slot_multiplier),
        ),
        (
            "slot_multiplier",
            ManifestValue::U64(draft.mapping.slot_multiplier),
        ),
    ]))
}

fn r3_reproduction_receipt(
    implementation_id: &str,
    route_sha256: &str,
    package_sha256: &str,
    template_sha256: &str,
    projection_sha256: &str,
) -> Result<Vec<u8>> {
    let value = manifest_object([
        ("implementation_id", manifest_string(implementation_id)),
        ("recipient_package_sha256", manifest_string(package_sha256)),
        (
            "reproduction_projection_sha256",
            manifest_string(projection_sha256),
        ),
        (
            "route_data_template_sha256",
            manifest_string(template_sha256),
        ),
        ("route_sha256", manifest_string(route_sha256)),
        (
            "schema",
            manifest_string("golden-board.m2-r3-route-reproduction/v1"),
        ),
    ]);
    serialize_manifest(&value).map_err(|_| CarrierError::ManifestShape)
}

fn r3_route_prefix_admits_against(
    raw: &[u8],
    sector: usize,
    expected: &[u8],
    expected_package: &[u8],
) -> Result<()> {
    if sector >= 4 || raw.len() < 64 || raw[..32] != CALIBRATIONS[sector] {
        return Err(CarrierError::RouteFit);
    }
    let envelope = &raw[32..64];
    let record_count = usize::from(u16::from_be_bytes(envelope[14..16].try_into().unwrap()));
    let record_bytes = usize::try_from(u32::from_be_bytes(envelope[16..20].try_into().unwrap()))
        .map_err(|_| CarrierError::Arithmetic)?;
    let package_bytes = usize::try_from(u32::from_be_bytes(envelope[20..24].try_into().unwrap()))
        .map_err(|_| CarrierError::Arithmetic)?;
    let prefix_cells = usize::try_from(u32::from_be_bytes(envelope[24..28].try_into().unwrap()))
        .map_err(|_| CarrierError::Arithmetic)?;
    if &envelope[..8] != ROUTE_MAGIC
        || u16::from_be_bytes(envelope[8..10].try_into().unwrap()) != 1
        || envelope[10] != sector as u8
        || envelope[11] != sector as u8
        || u16::from_be_bytes(envelope[12..14].try_into().unwrap()) != 7
        || !(39..=256).contains(&record_count)
        || raw.len()
            != 64_usize
                .checked_add(record_bytes)
                .ok_or(CarrierError::Arithmetic)?
        || prefix_cells != raw.len().checked_mul(8).ok_or(CarrierError::Arithmetic)?
        || u16::from_be_bytes(envelope[28..30].try_into().unwrap()) != 256
        || u16::from_be_bytes(envelope[30..32].try_into().unwrap()) != 0
    {
        return Err(CarrierError::RouteFit);
    }
    let base = u16::try_from(sector * 10_000).map_err(|_| CarrierError::Arithmetic)?;
    let (package_first, package_end, stage, kind) = route_payload_range(raw, base + 6_001)?;
    if stage != 5
        || kind != 5
        || package_end - package_first != package_bytes
        || &raw[package_first..package_end] != expected_package
        || decode_recipe_package(&raw[package_first..package_end], 7).is_err()
    {
        return Err(CarrierError::RouteFit);
    }
    let tables = package_table_records(expected_package)?;
    for (index, table) in tables.iter().enumerate() {
        let record_id = base
            .checked_add(5_001)
            .and_then(|value| value.checked_add(u16::try_from(index).ok()?))
            .ok_or(CarrierError::Arithmetic)?;
        let (first, end, table_stage, table_kind) = route_payload_range(raw, record_id)?;
        if table_stage != 5 || table_kind != 4 || &raw[first..end] != table {
            return Err(CarrierError::RouteFit);
        }
    }
    // Owner admission is intentionally stricter than damage-time discovery:
    // every DEFINE/example byte is bound by the independently regenerated
    // canonical prefix, not merely by locally parseable framing.
    if raw != expected {
        return Err(CarrierError::OwnerIdentity);
    }
    Ok(())
}

/// Admit one route prefix against a complete independently generated v7
/// owner.  This is an owner/KAT check, not a damage decoder entry point.
pub fn admit_r3_route_prefix(
    raw: &[u8],
    sector: usize,
    owner: &R3RouteOwnerGeneration,
) -> Result<()> {
    let expected = owner
        .draft
        .route_prefixes
        .get(sector)
        .ok_or(CarrierError::Parameter)?;
    r3_route_prefix_admits_against(raw, sector, expected, &owner.draft.recipient_package)
}

/// Generate the complete route-data-v1 owner, malformed corpus, and the two
/// deterministic reproduction receipt preimages.  The `python` receipt is the
/// byte string the independent Python generator must reproduce; its digest is
/// not copied from Python output.
pub fn generate_r3_route_owner() -> Result<R3RouteOwnerGeneration> {
    let draft = generate_r3_route_draft()?;
    let metrics = r3_recipe_package_metrics().map_err(|_| CarrierError::Recipe)?;
    if metrics.package_bytes as usize != draft.recipient_package.len()
        || metrics.package_sha256 != draft.recipient_package_sha256
    {
        return Err(CarrierError::Recipe);
    }
    let malformed_cases = malformed_r3_route_cases(&draft.route_prefixes[0])?;
    if malformed_cases.len() != 8 {
        return Err(CarrierError::RouteFit);
    }
    for row in &malformed_cases {
        if r3_route_prefix_admits_against(
            &row.mutant,
            0,
            &draft.route_prefixes[0],
            &draft.recipient_package,
        )
        .is_ok()
        {
            return Err(CarrierError::RouteFit);
        }
    }
    let malformed_corpus_value = manifest_object([
        (
            "clean_sector_sha256",
            manifest_string(&draft.route_prefix_sha256_by_sector[0]),
        ),
        (
            "rows",
            manifest_array(malformed_cases.iter().map(|row| {
                manifest_object([
                    ("case_id", manifest_string(&row.case_id)),
                    ("expected_result", manifest_string("reject")),
                    ("mutant_bytes", ManifestValue::U64(row.mutant.len() as u64)),
                    ("mutant_sha256", manifest_string(&row.mutant_sha256)),
                    ("sector_id", ManifestValue::U64(0)),
                ])
            })),
        ),
        (
            "schema",
            manifest_string("golden-board.m2-r3-route-malformed-corpus/v1"),
        ),
    ]);
    let malformed_corpus =
        serialize_manifest(&malformed_corpus_value).map_err(|_| CarrierError::ManifestShape)?;
    let malformed_corpus_sha256 = digest(&malformed_corpus);
    let (
        first_fit,
        examined_pair_count,
        total_pair_count,
        predecessor_side,
        predecessor_shell_width,
        predecessor_reason,
    ) = r3_first_fit_value(&draft)?;
    let capacity_projection = r3_capacity_projection_value(&draft)?;
    let recipe_resource_rows = r3_recipe_resource_rows().map_err(|_| CarrierError::Recipe)?;
    let slot_multiplier_table_sha256 = digest(&r3_slot_multiplier_table());

    let mut projection = BTreeMap::new();
    projection.insert("capacity_projection".to_owned(), capacity_projection);
    projection.insert("first_fit".to_owned(), first_fit);
    projection.insert(
        "held_out_record_bytes_by_sector".to_owned(),
        manifest_array(
            draft
                .held_out_record_bytes_by_sector
                .iter()
                .copied()
                .map(ManifestValue::U64),
        ),
    );
    projection.insert(
        "malformed_corpus_case_count".to_owned(),
        ManifestValue::U64(malformed_cases.len() as u64),
    );
    projection.insert(
        "malformed_corpus_sha256".to_owned(),
        manifest_string(&malformed_corpus_sha256),
    );
    projection.insert(
        "recipe_resource_rows".to_owned(),
        manifest_array(recipe_resource_rows.iter().map(|row| {
            manifest_object([
                (
                    "encoded_bytes",
                    ManifestValue::U64(u64::from(row.encoded_bytes)),
                ),
                ("node_count", ManifestValue::U64(u64::from(row.node_count))),
                (
                    "peak_scratch_bytes",
                    ManifestValue::U64(row.peak_scratch_bytes),
                ),
                ("primitive_steps", ManifestValue::U64(row.primitive_steps)),
                ("recipe_id", ManifestValue::U64(u64::from(row.recipe_id))),
            ])
        })),
    );
    for (key, value) in [
        ("recipient_package_bytes", u64::from(metrics.package_bytes)),
        (
            "recipient_package_edge_count",
            u64::from(metrics.edge_count),
        ),
        (
            "recipient_package_node_count",
            u64::from(metrics.node_count),
        ),
        (
            "recipient_package_peak_scratch_bytes",
            u64::from(metrics.peak_scratch_bytes),
        ),
        (
            "recipient_package_primitive_steps",
            metrics.maximum_primitive_steps,
        ),
        (
            "recipient_package_table_payload_bytes",
            u64::from(metrics.table_payload_bytes),
        ),
    ] {
        projection.insert(key.to_owned(), ManifestValue::U64(value));
    }
    projection.insert(
        "recipient_package_sha256".to_owned(),
        manifest_string(&draft.recipient_package_sha256),
    );
    projection.insert(
        "route_data_template_sha256".to_owned(),
        manifest_string(&draft.route_data_template_sha256),
    );
    projection.insert(
        "route_example_peak_scratch_bytes_by_sector".to_owned(),
        manifest_array((0..4).map(|_| ManifestValue::U64(metrics.route_peak_scratch_bytes))),
    );
    projection.insert(
        "route_example_primitive_steps_by_sector".to_owned(),
        manifest_array(
            (0..4)
                .map(|_| ManifestValue::U64(metrics.route_worked_held_primitive_steps_per_sector)),
        ),
    );
    projection.insert(
        "route_headroom_cells_by_sector".to_owned(),
        manifest_array(
            draft
                .route_images
                .sectors
                .iter()
                .map(|row| ManifestValue::U64(row.headroom_cells)),
        ),
    );
    projection.insert(
        "route_prefix_cells_by_sector".to_owned(),
        manifest_array(
            draft
                .route_images
                .sectors
                .iter()
                .map(|row| ManifestValue::U64(row.route_prefix_cells)),
        ),
    );
    projection.insert(
        "route_prefix_sha256_by_sector".to_owned(),
        manifest_array(
            draft
                .route_prefix_sha256_by_sector
                .iter()
                .map(manifest_string),
        ),
    );
    projection.insert(
        "route_sha256".to_owned(),
        manifest_string(&draft.route_sha256),
    );
    projection.insert(
        "slot_multiplier_table_sha256".to_owned(),
        manifest_string(&slot_multiplier_table_sha256),
    );
    projection.insert(
        "worked_record_bytes_by_sector".to_owned(),
        manifest_array(
            draft
                .worked_record_bytes_by_sector
                .iter()
                .copied()
                .map(ManifestValue::U64),
        ),
    );
    let reproduction_projection = serialize_manifest(&ManifestValue::Object(projection.clone()))
        .map_err(|_| CarrierError::ManifestShape)?;
    let reproduction_projection_sha256 = digest(&reproduction_projection);
    let python_reproduction_receipt = r3_reproduction_receipt(
        "python",
        &draft.route_sha256,
        &draft.recipient_package_sha256,
        &draft.route_data_template_sha256,
        &reproduction_projection_sha256,
    )?;
    let rust_reproduction_receipt = r3_reproduction_receipt(
        "rust",
        &draft.route_sha256,
        &draft.recipient_package_sha256,
        &draft.route_data_template_sha256,
        &reproduction_projection_sha256,
    )?;
    let python_reproduction_sha256 = digest(&python_reproduction_receipt);
    let rust_reproduction_sha256 = digest(&rust_reproduction_receipt);
    if python_reproduction_sha256 == rust_reproduction_sha256 {
        return Err(CarrierError::ManifestShape);
    }
    projection.insert(
        "python_reproduction_sha256".to_owned(),
        manifest_string(&python_reproduction_sha256),
    );
    projection.insert(
        "reproduction_projection_sha256".to_owned(),
        manifest_string(&reproduction_projection_sha256),
    );
    projection.insert(
        "rust_reproduction_sha256".to_owned(),
        manifest_string(&rust_reproduction_sha256),
    );
    let mut route_data_value = validate_canonical_manifest(&draft.route_data_template)
        .map_err(|_| CarrierError::ManifestShape)?;
    object_mut(&mut route_data_value)?
        .insert("generated".to_owned(), ManifestValue::Object(projection));
    let route_data =
        serialize_manifest(&route_data_value).map_err(|_| CarrierError::ManifestShape)?;
    validate_canonical_manifest(&route_data).map_err(|_| CarrierError::ManifestShape)?;
    let route_data_sha256 = digest(&route_data);
    Ok(R3RouteOwnerGeneration {
        draft,
        route_data_sha256,
        route_data,
        reproduction_projection,
        reproduction_projection_sha256,
        python_reproduction_receipt,
        python_reproduction_sha256,
        rust_reproduction_receipt,
        rust_reproduction_sha256,
        malformed_corpus,
        malformed_corpus_sha256,
        malformed_cases,
        examined_pair_count,
        total_pair_count,
        predecessor_side,
        predecessor_shell_width,
        predecessor_reason,
    })
}

/// Strict route-data-v1 admission against the independently regenerated Rust
/// owner. Canonical JSON, every closed key/value, all nested projections, and
/// all cross-hashes must therefore match before admission succeeds.
pub fn admit_r3_route_data(raw: &[u8]) -> Result<R3RouteOwnerGeneration> {
    if raw.len() > OWNER_DOCUMENT_BYTES_MAX {
        return Err(CarrierError::Parameter);
    }
    let owner = generate_r3_route_owner()?;
    validate_canonical_manifest(raw).map_err(|_| CarrierError::ManifestShape)?;
    if raw != owner.route_data {
        return Err(CarrierError::OwnerIdentity);
    }
    for sector in 0..4 {
        admit_r3_route_prefix(&owner.draft.route_prefixes[sector], sector, &owner)?;
    }
    Ok(owner)
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LogicalSection {
    pub section_id: u32,
    pub section_type: u16,
    pub section_version: u16,
    pub closure_class: u8,
    pub check_id: u8,
    pub copy_count: u8,
    pub dependencies: Vec<u32>,
    pub game_ordinal: Option<u8>,
    pub payload: Vec<u8>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticPrototype {
    pub kind: u16,
    pub prototype_id: String,
    pub source_record_id: u16,
    pub frame_length: u16,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticRealSection {
    pub section_id: u32,
    pub closure_class: u8,
    pub copy_class: String,
    pub record_ids: Vec<u16>,
    pub game_ordinal: Option<u8>,
    pub payload: Vec<u8>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticTierFrame {
    pub section_id: u32,
    pub closure_class: u8,
    pub copy_class: String,
    pub dependencies: Vec<u32>,
    pub payload: Vec<u8>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticSlot {
    pub bucket_id: String,
    pub slot_ordinal: u64,
    pub role_ordinal: u64,
    pub role_id: String,
    pub kind: u16,
    pub prototype_id: String,
    pub frame_length: u16,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticBucket {
    pub bucket_id: String,
    pub tier: String,
    pub copy_class: String,
    pub logical_payload_bytes: u64,
    pub slot_count: u64,
    pub section_count: u64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticCapacitySection {
    pub section_id: u32,
    pub bucket_id: String,
    pub section_ordinal: u64,
    pub tier: String,
    pub copy_class: String,
    pub first_slot_ordinal: u64,
    pub slot_count: u64,
    pub logical_payload_bytes: u64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticEnvelopeManifest {
    canonical_bytes: Vec<u8>,
    sha256: String,
    slice_semantic_sha256: String,
    prototypes: Vec<SemanticPrototype>,
    real_sections: Vec<SemanticRealSection>,
    tier_frames: Vec<SemanticTierFrame>,
    buckets: Vec<SemanticBucket>,
    capacity_sections: Vec<SemanticCapacitySection>,
    slots: Vec<SemanticSlot>,
}

impl SemanticEnvelopeManifest {
    pub fn canonical_bytes(&self) -> &[u8] {
        &self.canonical_bytes
    }

    pub fn sha256(&self) -> &str {
        &self.sha256
    }

    pub fn slice_semantic_sha256(&self) -> &str {
        &self.slice_semantic_sha256
    }
}

fn validate_semantic_manifest_integrity(semantic: &SemanticEnvelopeManifest) -> Result<()> {
    if semantic.canonical_bytes.len() > OWNER_DOCUMENT_BYTES_MAX
        || digest(&semantic.canonical_bytes) != semantic.sha256
    {
        return Err(CarrierError::OwnerIdentity);
    }
    let root = validate_canonical_manifest(&semantic.canonical_bytes)
        .map_err(|_| CarrierError::ManifestShape)?;
    if text(field(&root, "schema")?)? != "golden-board.m2-semantic-envelope/v0"
        || text(field(&root, "slice_semantic_sha256")?)? != semantic.slice_semantic_sha256
    {
        return Err(CarrierError::OwnerIdentity);
    }
    Ok(())
}

fn manifest_string(value: impl Into<String>) -> ManifestValue {
    ManifestValue::String(value.into())
}

fn manifest_array(values: impl IntoIterator<Item = ManifestValue>) -> ManifestValue {
    ManifestValue::Array(values.into_iter().collect())
}

fn frame_map(stream: &[u8]) -> Result<BTreeMap<u16, Vec<u8>>> {
    if stream.len() < 4 {
        return Err(CarrierError::Section);
    }
    let count = usize::from(u16::from_be_bytes([stream[2], stream[3]]));
    let mut at = 4_usize;
    let mut output = BTreeMap::new();
    for _ in 0..count {
        let header = stream.get(at..at + 8).ok_or(CarrierError::Section)?;
        let id = u16::from_be_bytes([header[0], header[1]]);
        let payload = usize::try_from(u32::from_be_bytes(header[4..8].try_into().unwrap()))
            .map_err(|_| CarrierError::Arithmetic)?;
        let end = at
            .checked_add(8)
            .and_then(|value| value.checked_add(payload))
            .ok_or(CarrierError::Arithmetic)?;
        let frame = stream.get(at..end).ok_or(CarrierError::Section)?;
        if output.insert(id, frame.to_vec()).is_some() {
            return Err(CarrierError::Section);
        }
        at = end;
    }
    if at != stream.len() || output.len() != count {
        return Err(CarrierError::Section);
    }
    Ok(output)
}

fn tier_payload(
    tier_id: u8,
    stream: &[u8],
    body_ids: &[u32],
    root_frame: &[u8],
) -> Result<Vec<u8>> {
    if stream.len() < 4 || body_ids.is_empty() || body_ids.windows(2).any(|pair| pair[0] >= pair[1])
    {
        return Err(CarrierError::Section);
    }
    let mut output = Vec::new();
    output.extend_from_slice(&0_u16.to_be_bytes());
    output.push(tier_id);
    output.push(0);
    be_u16(&mut output, body_ids.len())?;
    output.extend_from_slice(&0_u16.to_be_bytes());
    be_u32(&mut output, stream.len())?;
    output.extend_from_slice(&stream[2..4]);
    be_u32(&mut output, root_frame.len())?;
    output.extend_from_slice(&stream[..4]);
    for id in body_ids {
        output.extend_from_slice(&id.to_be_bytes());
    }
    output.extend_from_slice(root_frame);
    Ok(output)
}

fn curriculum_table<'a>(value: &'a toml::Value, key: &str) -> Result<&'a toml::Table> {
    value
        .get(key)
        .and_then(toml::Value::as_table)
        .ok_or(CarrierError::ManifestShape)
}

fn curriculum_rows<'a>(value: &'a toml::Value, key: &str) -> Result<&'a [toml::Value]> {
    value
        .get(key)
        .and_then(toml::Value::as_array)
        .map(Vec::as_slice)
        .ok_or(CarrierError::ManifestShape)
}

fn toml_text<'a>(value: &'a toml::Value, key: &str) -> Result<&'a str> {
    value
        .get(key)
        .and_then(toml::Value::as_str)
        .ok_or(CarrierError::ManifestShape)
}

fn toml_u64(value: &toml::Value, key: &str) -> Result<u64> {
    value
        .get(key)
        .and_then(toml::Value::as_integer)
        .and_then(|value| u64::try_from(value).ok())
        .ok_or(CarrierError::ManifestShape)
}

fn copy_class(tier: &str) -> Result<String> {
    match tier {
        "core0" | "core1" | "core2" => Ok("replicated-m2".to_owned()),
        "core3" | "core4" => Ok("nonreplicated-m2".to_owned()),
        _ => Err(CarrierError::ManifestShape),
    }
}

fn append_role_slots(
    target: &mut Vec<SemanticSlot>,
    bucket_id: &str,
    role_ordinal: u64,
    role_id: &str,
    counts: &[u64; 14],
    prototypes: &[SemanticPrototype],
) -> Result<()> {
    for (index, count) in counts.iter().copied().enumerate() {
        for _ in 0..count {
            let prototype = prototypes.get(index).ok_or(CarrierError::ManifestShape)?;
            target.push(SemanticSlot {
                bucket_id: bucket_id.to_owned(),
                slot_ordinal: u64::try_from(target.len()).map_err(|_| CarrierError::Arithmetic)?,
                role_ordinal,
                role_id: role_id.to_owned(),
                kind: prototype.kind,
                prototype_id: prototype.prototype_id.clone(),
                frame_length: prototype.frame_length,
            });
        }
    }
    Ok(())
}

fn finalize_bucket(
    bucket_id: String,
    tier: String,
    mut slots: Vec<SemanticSlot>,
    maximum: u64,
    next_section_id: &mut u32,
    all_slots: &mut Vec<SemanticSlot>,
    sections: &mut Vec<SemanticCapacitySection>,
) -> Result<SemanticBucket> {
    if slots.is_empty() {
        return Err(CarrierError::ManifestShape);
    }
    for (ordinal, slot) in slots.iter_mut().enumerate() {
        slot.slot_ordinal = u64::try_from(ordinal).map_err(|_| CarrierError::Arithmetic)?;
        if u64::from(slot.frame_length) > maximum {
            return Err(CarrierError::ManifestShape);
        }
    }
    let class = copy_class(&tier)?;
    let mut first = 0_usize;
    let mut section_ordinal = 0_u64;
    while first < slots.len() {
        let mut end = first;
        let mut bytes = 0_u64;
        while end < slots.len() && bytes + u64::from(slots[end].frame_length) <= maximum {
            bytes += u64::from(slots[end].frame_length);
            end += 1;
        }
        if end == first {
            return Err(CarrierError::ManifestShape);
        }
        sections.push(SemanticCapacitySection {
            section_id: *next_section_id,
            bucket_id: bucket_id.clone(),
            section_ordinal,
            tier: tier.clone(),
            copy_class: class.clone(),
            first_slot_ordinal: first as u64,
            slot_count: (end - first) as u64,
            logical_payload_bytes: bytes,
        });
        *next_section_id = next_section_id
            .checked_add(1)
            .ok_or(CarrierError::Arithmetic)?;
        section_ordinal += 1;
        first = end;
    }
    let logical_payload_bytes = slots.iter().map(|slot| u64::from(slot.frame_length)).sum();
    let slot_count = slots.len() as u64;
    all_slots.extend(slots);
    Ok(SemanticBucket {
        bucket_id,
        tier,
        copy_class: class,
        logical_payload_bytes,
        slot_count,
        section_count: section_ordinal,
    })
}

fn string_set(value: &toml::Value, table_key: &str, key: &str) -> Result<BTreeSet<String>> {
    curriculum_table(value, table_key)?
        .get(key)
        .and_then(toml::Value::as_array)
        .ok_or(CarrierError::ManifestShape)?
        .iter()
        .map(|value| {
            value
                .as_str()
                .map(str::to_owned)
                .ok_or(CarrierError::ManifestShape)
        })
        .collect()
}

fn fields(names: &[&str]) -> ManifestValue {
    manifest_array(names.iter().map(|value| manifest_string(*value)))
}

/// Independently derive and canonically serialize the P3 semantic envelope.
pub fn render_semantic_envelope(
    policy: &ProfilePolicy,
    policy_raw: &[u8],
    compiled: &SliceCompilation,
    curriculum_raw: &[u8],
) -> Result<SemanticEnvelopeManifest> {
    if policy_raw.len() > 65_536
        || curriculum_raw.len() > OWNER_DOCUMENT_BYTES_MAX
        || digest(policy_raw) != policy.sha256
    {
        return Err(CarrierError::OwnerIdentity);
    }
    let policy_document: toml::Value =
        toml::from_str(std::str::from_utf8(policy_raw).map_err(|_| CarrierError::ManifestShape)?)
            .map_err(|_| CarrierError::ManifestShape)?;
    let slice_semantic_sha256 = policy_document
        .get("bindings")
        .and_then(toml::Value::as_table)
        .and_then(|table| table.get("slice_semantic_sha256"))
        .and_then(toml::Value::as_str)
        .ok_or(CarrierError::ManifestShape)?;
    let curriculum_sha256 = policy_document
        .get("bindings")
        .and_then(toml::Value::as_table)
        .and_then(|table| table.get("curriculum_sha256"))
        .and_then(toml::Value::as_str)
        .ok_or(CarrierError::ManifestShape)?;
    let expected_envelope_sha256 = policy_document
        .get("semantic_envelope_manifest")
        .and_then(toml::Value::as_table)
        .and_then(|table| table.get("expected_sha256"))
        .and_then(toml::Value::as_str)
        .ok_or(CarrierError::ManifestShape)?;
    let derived_slice_semantic_sha256 = digest(compiled.all_stream());
    if slice_semantic_sha256 != derived_slice_semantic_sha256
        || digest(curriculum_raw) != curriculum_sha256
    {
        return Err(CarrierError::OwnerIdentity);
    }
    let curriculum_text =
        std::str::from_utf8(curriculum_raw).map_err(|_| CarrierError::ManifestShape)?;
    let curriculum: toml::Value =
        toml::from_str(curriculum_text).map_err(|_| CarrierError::ManifestShape)?;
    let frames = frame_map(compiled.all_stream())?;
    let mut prototypes = Vec::new();
    for row in compiled.capacity_prototypes() {
        prototypes.push(SemanticPrototype {
            kind: row.kind(),
            prototype_id: row.prototype_id().to_owned(),
            source_record_id: row.source_record_id(),
            frame_length: row.frame_length(),
        });
    }
    if prototypes.len() != 14
        || prototypes
            .iter()
            .enumerate()
            .any(|(index, row)| usize::from(row.kind) != index + 1)
    {
        return Err(CarrierError::ManifestShape);
    }

    let mut real_sections = Vec::new();
    for assignment in compiled.assignments() {
        let mut payload = Vec::new();
        for id in assignment.record_ids() {
            payload.extend(frames.get(id).ok_or(CarrierError::Section)?);
        }
        let closure_class = match assignment.closure() {
            Closure::Required => CLOSURE_M2_REQUIRED,
            Closure::AllOnly => CLOSURE_M2_ALL_ONLY,
            Closure::All => return Err(CarrierError::Section),
        };
        let section_id = u32::from(assignment.section_id());
        real_sections.push(SemanticRealSection {
            section_id,
            closure_class,
            copy_class: if closure_class == CLOSURE_M2_REQUIRED {
                "replicated-m2".to_owned()
            } else {
                "nonreplicated-m2".to_owned()
            },
            record_ids: assignment.record_ids().to_vec(),
            game_ordinal: (100..164)
                .contains(&section_id)
                .then(|| (section_id - 100) as u8),
            payload,
        });
    }
    if real_sections.len() != 77
        || real_sections
            .windows(2)
            .any(|pair| pair[0].section_id >= pair[1].section_id)
    {
        return Err(CarrierError::Section);
    }
    let required_ids = real_sections
        .iter()
        .filter(|row| row.closure_class == CLOSURE_M2_REQUIRED)
        .map(|row| row.section_id)
        .collect::<Vec<_>>();
    let all_ids = real_sections
        .iter()
        .map(|row| row.section_id)
        .collect::<Vec<_>>();
    let required_root = compiled
        .tier_roots()
        .iter()
        .find(|row| row.closure() == Closure::Required)
        .ok_or(CarrierError::Section)?;
    let all_root = compiled
        .tier_roots()
        .iter()
        .find(|row| row.closure() == Closure::All)
        .ok_or(CarrierError::Section)?;
    let tier_frames = vec![
        SemanticTierFrame {
            section_id: 2,
            closure_class: CLOSURE_M2_REQUIRED,
            copy_class: "fixed-two-m2".to_owned(),
            dependencies: required_ids.clone(),
            payload: tier_payload(
                0,
                compiled.required_stream(),
                &required_ids,
                required_root.frame(),
            )?,
        },
        SemanticTierFrame {
            section_id: 3,
            closure_class: CLOSURE_M2_REQUIRED,
            copy_class: "fixed-two-m2".to_owned(),
            dependencies: all_ids.clone(),
            payload: tier_payload(1, compiled.all_stream(), &all_ids, all_root.frame())?,
        },
    ];

    let heuristic = string_set(
        &curriculum,
        "authoring_minimums",
        "heuristic_role_required_concept_ids",
    )?;
    let essential = string_set(&curriculum, "sets", "E")?;
    if policy.role_bundles.len() != 8 {
        return Err(CarrierError::ManifestShape);
    }
    let mut buckets = Vec::new();
    let mut capacity_sections = Vec::new();
    let mut all_slots = Vec::new();
    let mut next_section_id = 211_u32;
    for concept in curriculum_rows(&curriculum, "concept")? {
        let id = toml_text(concept, "id")?;
        let tier = toml_text(concept, "tier")?;
        let bucket_id = format!("concept_minima/{id}");
        let mut slots = Vec::new();
        let role_count = 5 + usize::from(heuristic.contains(id));
        for (ordinal, (role_id, counts)) in policy.role_bundles[..role_count].iter().enumerate() {
            append_role_slots(
                &mut slots,
                &bucket_id,
                ordinal as u64,
                role_id,
                counts,
                &prototypes,
            )?;
        }
        buckets.push(finalize_bucket(
            bucket_id,
            tier.to_owned(),
            slots,
            policy.maximum_content_body_payload,
            &mut next_section_id,
            &mut all_slots,
            &mut capacity_sections,
        )?);
    }
    for family in curriculum_rows(&curriculum, "family")? {
        let id = toml_text(family, "id")?;
        let tier = toml_text(family, "tier")?;
        let bucket_id = format!("assessment/{id}");
        let occurrences = if essential.contains(id) { 15 } else { 12 };
        let mut slots = Vec::new();
        for ordinal in 0..occurrences {
            let (role_id, counts) = &policy.role_bundles[6];
            append_role_slots(
                &mut slots,
                &bucket_id,
                ordinal,
                role_id,
                counts,
                &prototypes,
            )?;
        }
        buckets.push(finalize_bucket(
            bucket_id,
            tier.to_owned(),
            slots,
            policy.maximum_content_body_payload,
            &mut next_section_id,
            &mut all_slots,
            &mut capacity_sections,
        )?);
    }
    for task in curriculum_rows(&curriculum, "integrated_task")? {
        let id = toml_text(task, "id")?;
        let bucket_id = format!("integrated/{id}");
        let occurrences = toml_u64(task, "minimum_per_form")?
            .checked_mul(3)
            .ok_or(CarrierError::Arithmetic)?;
        let mut slots = Vec::new();
        for ordinal in 0..occurrences {
            let (role_id, counts) = &policy.role_bundles[7];
            append_role_slots(
                &mut slots,
                &bucket_id,
                ordinal,
                role_id,
                counts,
                &prototypes,
            )?;
        }
        buckets.push(finalize_bucket(
            bucket_id,
            "core3".to_owned(),
            slots,
            policy.maximum_content_body_payload,
            &mut next_section_id,
            &mut all_slots,
            &mut capacity_sections,
        )?);
    }
    let nongeneric_bytes = buckets
        .iter()
        .map(|row| row.logical_payload_bytes)
        .sum::<u64>();
    let largest_index = policy
        .role_bundles
        .iter()
        .enumerate()
        .max_by(|left, right| {
            let size = |row: &(usize, &(String, [u64; 14]))| {
                row.1
                    .1
                    .iter()
                    .zip(&prototypes)
                    .map(|(count, prototype)| count * u64::from(prototype.frame_length))
                    .sum::<u64>()
            };
            size(left)
                .cmp(&size(right))
                .then_with(|| right.1.0.cmp(&left.1.0))
        })
        .map(|row| row.0)
        .ok_or(CarrierError::ManifestShape)?;
    let (largest_id, largest_counts) = &policy.role_bundles[largest_index];
    let cycle_bytes = prototypes
        .iter()
        .map(|row| u64::from(row.frame_length))
        .sum::<u64>()
        + largest_counts
            .iter()
            .zip(&prototypes)
            .map(|(count, row)| count * u64::from(row.frame_length))
            .sum::<u64>();
    if policy.generic_support_fraction_denominator == 0 || cycle_bytes == 0 {
        return Err(CarrierError::ManifestShape);
    }
    let target = nongeneric_bytes
        .checked_mul(policy.generic_support_fraction_numerator)
        .ok_or(CarrierError::Arithmetic)?
        .div_ceil(policy.generic_support_fraction_denominator);
    let cycles = policy
        .generic_support_minimum_cycles
        .max(target.div_ceil(cycle_bytes));
    let generic_id = "generic_shared_support";
    let mut generic_slots = Vec::new();
    for cycle in 0..cycles {
        for prototype in &prototypes {
            generic_slots.push(SemanticSlot {
                bucket_id: generic_id.to_owned(),
                slot_ordinal: 0,
                role_ordinal: cycle,
                role_id: "all_content_kinds".to_owned(),
                kind: prototype.kind,
                prototype_id: prototype.prototype_id.clone(),
                frame_length: prototype.frame_length,
            });
        }
        append_role_slots(
            &mut generic_slots,
            generic_id,
            cycle,
            largest_id,
            largest_counts,
            &prototypes,
        )?;
    }
    if cycles != policy.expected_generic_cycle_count
        || generic_slots.len() as u64 != policy.expected_generic_slot_count
    {
        return Err(CarrierError::ManifestShape);
    }
    let generic_bucket = finalize_bucket(
        generic_id.to_owned(),
        "core0".to_owned(),
        generic_slots,
        policy.maximum_content_body_payload,
        &mut next_section_id,
        &mut all_slots,
        &mut capacity_sections,
    )?;
    if generic_bucket.section_count != policy.expected_generic_section_count {
        return Err(CarrierError::ManifestShape);
    }
    buckets.push(generic_bucket);
    let authoring_payload_bytes = buckets
        .iter()
        .map(|row| row.logical_payload_bytes)
        .sum::<u64>();
    let expected_next_section_id = 211_u32
        .checked_add(
            u32::try_from(policy.expected_capacity[7]).map_err(|_| CarrierError::Arithmetic)?,
        )
        .ok_or(CarrierError::Arithmetic)?;
    let mut slots_by_kind = [0_u64; 14];
    for slot in &all_slots {
        let index = usize::from(slot.kind)
            .checked_sub(1)
            .filter(|index| *index < slots_by_kind.len())
            .ok_or(CarrierError::ManifestShape)?;
        slots_by_kind[index] += 1;
    }
    if next_section_id != expected_next_section_id
        || buckets.len() as u64 != policy.expected_capacity[5]
        || capacity_sections.len() as u64 != policy.expected_capacity[7]
        || all_slots.len() as u64 != policy.expected_capacity[6]
        || authoring_payload_bytes != policy.expected_capacity[4]
        || slots_by_kind != policy.expected_slots_by_kind
    {
        return Err(CarrierError::ManifestShape);
    }

    let prototype_rows = prototypes.iter().map(|row| {
        manifest_array([
            ManifestValue::U64(u64::from(row.kind)),
            manifest_string(&row.prototype_id),
            ManifestValue::U64(u64::from(row.source_record_id)),
            ManifestValue::U64(u64::from(row.frame_length)),
        ])
    });
    let real_rows = real_sections.iter().map(|row| {
        manifest_array([
            ManifestValue::U64(u64::from(row.section_id)),
            ManifestValue::U64(u64::from(row.closure_class)),
            manifest_string(&row.copy_class),
            ManifestValue::U64(row.payload.len() as u64),
            manifest_array(
                row.record_ids
                    .iter()
                    .map(|id| ManifestValue::U64(u64::from(*id))),
            ),
            ManifestValue::Bool(row.game_ordinal.is_some()),
            ManifestValue::U64(row.game_ordinal.map_or(u64::from(u16::MAX), u64::from)),
        ])
    });
    let tier_rows = tier_frames.iter().map(|row| {
        manifest_array([
            ManifestValue::U64(u64::from(row.section_id)),
            ManifestValue::U64(u64::from(row.closure_class)),
            manifest_string(&row.copy_class),
            ManifestValue::U64(row.payload.len() as u64),
            manifest_array(
                row.dependencies
                    .iter()
                    .map(|id| ManifestValue::U64(u64::from(*id))),
            ),
        ])
    });
    let bucket_rows = buckets.iter().map(|row| {
        manifest_array([
            manifest_string(&row.bucket_id),
            manifest_string(&row.tier),
            manifest_string(&row.copy_class),
            ManifestValue::U64(row.logical_payload_bytes),
            ManifestValue::U64(row.slot_count),
            ManifestValue::U64(row.section_count),
        ])
    });
    let capacity_rows = capacity_sections.iter().map(|row| {
        manifest_array([
            ManifestValue::U64(u64::from(row.section_id)),
            manifest_string(&row.bucket_id),
            ManifestValue::U64(row.section_ordinal),
            manifest_string(&row.tier),
            manifest_string(&row.copy_class),
            ManifestValue::U64(row.first_slot_ordinal),
            ManifestValue::U64(row.slot_count),
            ManifestValue::U64(row.logical_payload_bytes),
        ])
    });
    let slot_rows = all_slots.iter().map(|row| {
        manifest_array([
            manifest_string(&row.bucket_id),
            ManifestValue::U64(row.slot_ordinal),
            ManifestValue::U64(row.role_ordinal),
            manifest_string(&row.role_id),
            ManifestValue::U64(u64::from(row.kind)),
            manifest_string(&row.prototype_id),
            ManifestValue::U64(u64::from(row.frame_length)),
        ])
    });
    let mut totals = BTreeMap::new();
    for (key, value) in [
        ("prototype_count", prototypes.len() as u64),
        ("real_section_count", real_sections.len() as u64),
        ("tier_frame_count", tier_frames.len() as u64),
        ("bucket_count", buckets.len() as u64),
        ("capacity_section_count", capacity_sections.len() as u64),
        ("slot_count", all_slots.len() as u64),
        ("authoring_payload_bytes", authoring_payload_bytes),
    ] {
        totals.insert(key.to_owned(), ManifestValue::U64(value));
    }
    let mut root = BTreeMap::new();
    root.insert(
        "schema".to_owned(),
        manifest_string("golden-board.m2-semantic-envelope/v0"),
    );
    root.insert(
        "slice_semantic_sha256".to_owned(),
        manifest_string(&derived_slice_semantic_sha256),
    );
    root.insert(
        "prototype_row_fields".to_owned(),
        fields(&["kind", "prototype_id", "source_record_id", "frame_length"]),
    );
    root.insert("prototype_rows".to_owned(), manifest_array(prototype_rows));
    root.insert(
        "real_section_row_fields".to_owned(),
        fields(&[
            "section_id",
            "closure_class",
            "copy_class",
            "logical_payload_bytes",
            "record_ids",
            "has_game_ordinal",
            "game_ordinal",
        ]),
    );
    root.insert("real_section_rows".to_owned(), manifest_array(real_rows));
    root.insert(
        "tier_frame_row_fields".to_owned(),
        fields(&[
            "section_id",
            "closure_class",
            "copy_class",
            "logical_payload_bytes",
            "dependency_ids",
        ]),
    );
    root.insert("tier_frame_rows".to_owned(), manifest_array(tier_rows));
    root.insert(
        "bucket_row_fields".to_owned(),
        fields(&[
            "bucket_id",
            "tier",
            "copy_class",
            "logical_payload_bytes",
            "slot_count",
            "section_count",
        ]),
    );
    root.insert("bucket_rows".to_owned(), manifest_array(bucket_rows));
    root.insert(
        "capacity_section_row_fields".to_owned(),
        fields(&[
            "section_id",
            "bucket_id",
            "section_ordinal",
            "tier",
            "copy_class",
            "first_slot_ordinal",
            "slot_count",
            "logical_payload_bytes",
        ]),
    );
    root.insert(
        "capacity_section_rows".to_owned(),
        manifest_array(capacity_rows),
    );
    root.insert(
        "slot_row_fields".to_owned(),
        fields(&[
            "bucket_id",
            "slot_ordinal",
            "role_ordinal",
            "role_id",
            "kind",
            "prototype_id",
            "frame_length",
        ]),
    );
    root.insert("slot_rows".to_owned(), manifest_array(slot_rows));
    root.insert("totals".to_owned(), ManifestValue::Object(totals));
    let canonical_bytes = serialize_manifest(&ManifestValue::Object(root))
        .map_err(|_| CarrierError::ManifestShape)?;
    if canonical_bytes.len() > 1_048_576 {
        return Err(CarrierError::ManifestShape);
    }
    let sha256 = digest(&canonical_bytes);
    if sha256 != expected_envelope_sha256 {
        return Err(CarrierError::OwnerIdentity);
    }
    Ok(SemanticEnvelopeManifest {
        canonical_bytes,
        sha256,
        slice_semantic_sha256: derived_slice_semantic_sha256,
        prototypes,
        real_sections,
        tier_frames,
        buckets,
        capacity_sections,
        slots: all_slots,
    })
}

impl LogicalSection {
    pub(crate) fn envelope(&self) -> Result<Vec<u8>> {
        encode_section(&SectionEnvelope {
            section_id: self.section_id,
            section_type: self.section_type,
            section_version: self.section_version,
            closure_class: self.closure_class,
            check_id: self.check_id,
            dependencies: self.dependencies.clone(),
            payload: self.payload.clone(),
        })
        .map_err(|_| CarrierError::Section)
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ProtectedUnit {
    pub physical_unit_id: u32,
    pub section_id: u32,
    pub semantic_copy_id: u16,
    pub fragment_index: u16,
    pub replica_index: u8,
    pub physical_replica_count: u8,
    pub encoded: [u8; EH_UNIT_BYTES],
    pub slot: u64,
    pub logical_bit_first: u64,
}

/// Encode every section/copy/fragment in canonical unit order.
pub fn protect_sections(
    profile_version: u16,
    sections: &[LogicalSection],
) -> Result<Vec<ProtectedUnit>> {
    let profile = profile_by_version(profile_version).ok_or(CarrierError::Parameter)?;
    if !matches!(profile.version, 1 | 3) {
        return Err(CarrierError::Parameter);
    }
    if sections.is_empty()
        || sections
            .windows(2)
            .any(|pair| pair[0].section_id >= pair[1].section_id)
        || sections
            .iter()
            .any(|row| row.copy_count == 0 || row.copy_count > 3)
    {
        return Err(CarrierError::Section);
    }
    let mut output = Vec::new();
    let maximum_copy_count = sections
        .iter()
        .map(|section| section.copy_count)
        .max()
        .ok_or(CarrierError::Section)?;
    for copy in 0..maximum_copy_count {
        for section in sections.iter().filter(|section| copy < section.copy_count) {
            let envelope = section.envelope()?;
            let blocks = fragment_envelope(
                profile_version,
                section.section_id,
                u16::from(copy),
                section.section_type,
                section.section_version,
                &envelope,
            )
            .map_err(|_| CarrierError::Section)?;
            for (fragment_index, block) in blocks.into_iter().enumerate() {
                let physical_unit_id =
                    u32::try_from(output.len() + 1).map_err(|_| CarrierError::Arithmetic)?;
                let logical_bit_first = u64::try_from(output.len())
                    .map_err(|_| CarrierError::Arithmetic)?
                    .checked_mul((EH_UNIT_BYTES * 8) as u64)
                    .ok_or(CarrierError::Arithmetic)?;
                output.push(ProtectedUnit {
                    physical_unit_id,
                    section_id: section.section_id,
                    semantic_copy_id: u16::from(copy),
                    fragment_index: u16::try_from(fragment_index)
                        .map_err(|_| CarrierError::Arithmetic)?,
                    replica_index: copy,
                    physical_replica_count: section.copy_count,
                    encoded: encode_eh_unit(&block),
                    slot: u64::try_from(output.len()).map_err(|_| CarrierError::Arithmetic)?,
                    logical_bit_first,
                });
            }
        }
    }
    Ok(output)
}

/// Encode v7 sections in `(section_id, fragment_index, replica_index)` order.
/// Every lane in a group carries the same semantic-copy-zero common block.
pub fn protect_sections_hierarchical(
    sections: &[LogicalSection],
    mapping: HierarchicalMap,
) -> Result<Vec<ProtectedUnit>> {
    if sections.is_empty()
        || sections
            .windows(2)
            .any(|pair| pair[0].section_id >= pair[1].section_id)
        || sections.iter().any(|section| {
            !matches!(section.copy_count, 1 | 2 | 5)
                || ([1, 2, 3, 16].contains(&section.section_id) != (section.copy_count == 5))
        })
    {
        return Err(CarrierError::Section);
    }
    let mut output = Vec::new();
    for section in sections {
        let envelope = section.envelope()?;
        let blocks = fragment_envelope(
            7,
            section.section_id,
            0,
            section.section_type,
            section.section_version,
            &envelope,
        )
        .map_err(|_| CarrierError::Section)?;
        for (fragment_index, block) in blocks.into_iter().enumerate() {
            let encoded = encode_eh_unit(&block);
            for replica_index in 0..section.copy_count {
                let physical_ordinal =
                    u64::try_from(output.len()).map_err(|_| CarrierError::Arithmetic)?;
                if physical_ordinal >= mapping.unit_slot_count {
                    return Err(CarrierError::Geometry);
                }
                let slot = mapping.slot(physical_ordinal)?;
                output.push(ProtectedUnit {
                    physical_unit_id: u32::try_from(physical_ordinal + 1)
                        .map_err(|_| CarrierError::Arithmetic)?,
                    section_id: section.section_id,
                    semantic_copy_id: 0,
                    fragment_index: u16::try_from(fragment_index)
                        .map_err(|_| CarrierError::Arithmetic)?,
                    replica_index,
                    physical_replica_count: section.copy_count,
                    encoded,
                    slot,
                    logical_bit_first: slot
                        .checked_mul(R3_UNIT_BITS)
                        .ok_or(CarrierError::Arithmetic)?,
                });
            }
        }
    }
    Ok(output)
}

fn resolved_copy_count(profile: CandidateProfile, class: &str) -> Result<u8> {
    match class {
        "replicated-m2" if profile.version == 7 => Ok(2),
        "replicated-m2" => Ok(profile.required_copy_count),
        "nonreplicated-m2" => Ok(1),
        "fixed-two-m2" if profile.version == 7 => Ok(5),
        "fixed-two-m2" => Ok(2),
        _ => Err(CarrierError::ManifestShape),
    }
}

fn inventory_payload(profile: CandidateProfile, sections: &[LogicalSection]) -> Result<Vec<u8>> {
    if sections.is_empty() || sections[0].section_id == 1 {
        return Err(CarrierError::Section);
    }
    let entry_count = sections
        .len()
        .checked_add(1)
        .ok_or(CarrierError::Arithmetic)?;
    let dependency_count = sections.iter().try_fold(0_usize, |sum, row| {
        sum.checked_add(row.dependencies.len())
            .ok_or(CarrierError::Arithmetic)
    })?;
    let payload_length = 8_usize
        .checked_add(
            entry_count
                .checked_mul(20)
                .ok_or(CarrierError::Arithmetic)?,
        )
        .and_then(|value| value.checked_add(dependency_count * 4))
        .ok_or(CarrierError::Arithmetic)?;
    let mut entries = Vec::with_capacity(entry_count);
    entries.push(InventoryEntry {
        section_id: 1,
        section_type: SECTION_INVENTORY,
        section_version: if profile.version == 7 { 1 } else { 0 },
        closure_class: CLOSURE_M2_REQUIRED,
        check_id: profile.section_check_id,
        copy_count: if profile.version == 7 { 1 } else { 2 },
        physical_replica_count: if profile.version == 7 { 5 } else { 1 },
        dependencies: Vec::new(),
        logical_payload_length: u32::try_from(payload_length)
            .map_err(|_| CarrierError::Arithmetic)?,
        game_ordinal: None,
    });
    for section in sections {
        entries.push(InventoryEntry {
            section_id: section.section_id,
            section_type: section.section_type,
            section_version: section.section_version,
            closure_class: section.closure_class,
            check_id: section.check_id,
            copy_count: if profile.version == 7 {
                1
            } else {
                section.copy_count
            },
            physical_replica_count: if profile.version == 7 {
                section.copy_count
            } else {
                1
            },
            dependencies: section.dependencies.clone(),
            logical_payload_length: u32::try_from(section.payload.len())
                .map_err(|_| CarrierError::Arithmetic)?,
            game_ordinal: section.game_ordinal.map(u16::from),
        });
    }
    encode_inventory(&Inventory {
        inventory_version: u16::from(profile.version == 7),
        entries,
    })
    .map_err(|_| CarrierError::Section)
}

fn insert_inventory(
    profile: CandidateProfile,
    mut sections: Vec<LogicalSection>,
) -> Result<Vec<LogicalSection>> {
    sections.sort_by_key(|row| row.section_id);
    let payload = inventory_payload(profile, &sections)?;
    sections.insert(
        0,
        LogicalSection {
            section_id: 1,
            section_type: SECTION_INVENTORY,
            section_version: if profile.version == 7 { 1 } else { 0 },
            closure_class: CLOSURE_M2_REQUIRED,
            check_id: profile.section_check_id,
            copy_count: if profile.version == 7 { 5 } else { 2 },
            dependencies: Vec::new(),
            game_ordinal: None,
            payload,
        },
    );
    Ok(sections)
}

fn reserve_lengths(total: u64, maximum: u64) -> Result<Vec<usize>> {
    if total == 0 || maximum == 0 {
        return Err(CarrierError::ManifestShape);
    }
    let mut remaining = total;
    let mut output = Vec::new();
    while remaining != 0 {
        let take = remaining.min(maximum);
        output.push(usize::try_from(take).map_err(|_| CarrierError::Arithmetic)?);
        remaining -= take;
    }
    Ok(output)
}

fn base_sections(
    profile: CandidateProfile,
    semantic: &SemanticEnvelopeManifest,
    reserve_payload_bytes: u64,
    maximum_probe_payload: u64,
) -> Result<Vec<LogicalSection>> {
    let mut sections = Vec::new();
    for tier in &semantic.tier_frames {
        sections.push(LogicalSection {
            section_id: tier.section_id,
            section_type: SECTION_TIER_FRAME,
            section_version: 0,
            closure_class: tier.closure_class,
            check_id: profile.section_check_id,
            copy_count: resolved_copy_count(profile, &tier.copy_class)?,
            dependencies: tier.dependencies.clone(),
            game_ordinal: None,
            payload: tier.payload.clone(),
        });
    }
    for real in &semantic.real_sections {
        sections.push(LogicalSection {
            section_id: real.section_id,
            section_type: SECTION_CONTENT_BODY,
            section_version: 0,
            closure_class: real.closure_class,
            check_id: profile.section_check_id,
            copy_count: if profile.version == 7 && real.section_id == 16 {
                5
            } else {
                resolved_copy_count(profile, &real.copy_class)?
            },
            dependencies: Vec::new(),
            game_ordinal: real.game_ordinal,
            payload: real.payload.clone(),
        });
    }
    for row in &semantic.capacity_sections {
        sections.push(LogicalSection {
            section_id: row.section_id,
            section_type: SECTION_CAPACITY_PROBE,
            section_version: 0,
            closure_class: CLOSURE_M2_ALL_ONLY,
            check_id: profile.section_check_id,
            copy_count: resolved_copy_count(profile, &row.copy_class)?,
            dependencies: Vec::new(),
            game_ordinal: None,
            payload: vec![
                0;
                usize::try_from(row.logical_payload_bytes)
                    .map_err(|_| CarrierError::Arithmetic)?
            ],
        });
    }
    let first_reserve = semantic
        .capacity_sections
        .last()
        .ok_or(CarrierError::ManifestShape)?
        .section_id
        .checked_add(1)
        .ok_or(CarrierError::Arithmetic)?;
    for (ordinal, length) in reserve_lengths(reserve_payload_bytes, maximum_probe_payload)?
        .into_iter()
        .enumerate()
    {
        sections.push(LogicalSection {
            section_id: first_reserve
                .checked_add(u32::try_from(ordinal).map_err(|_| CarrierError::Arithmetic)?)
                .ok_or(CarrierError::Arithmetic)?,
            section_type: SECTION_RESERVE_PROBE,
            section_version: 0,
            closure_class: CLOSURE_M2_ALL_ONLY,
            check_id: profile.section_check_id,
            copy_count: if profile.version == 7 {
                2
            } else {
                profile.required_copy_count
            },
            dependencies: Vec::new(),
            game_ordinal: None,
            payload: vec![0; length],
        });
    }
    sections.sort_by_key(|row| row.section_id);
    if sections
        .windows(2)
        .any(|pair| pair[0].section_id >= pair[1].section_id)
    {
        return Err(CarrierError::Section);
    }
    Ok(sections)
}

fn section_fragment_count(section: &LogicalSection) -> Result<u64> {
    let check = match section.check_id {
        1 => 4_u64,
        2 => 8_u64,
        _ => return Err(CarrierError::Section),
    };
    let envelope = 18_u64
        .checked_add(4 * section.dependencies.len() as u64)
        .and_then(|value| value.checked_add(section.payload.len() as u64))
        .and_then(|value| value.checked_add(check))
        .ok_or(CarrierError::Arithmetic)?;
    Ok(envelope.div_ceil(157))
}

fn protected_unit_count(sections: &[LogicalSection]) -> Result<u64> {
    sections.iter().try_fold(0_u64, |sum, row| {
        section_fragment_count(row)?
            .checked_mul(u64::from(row.copy_count))
            .and_then(|count| sum.checked_add(count))
            .ok_or(CarrierError::Arithmetic)
    })
}

fn load_payload_for_fragments(fragments: u64, maximum: u64, check_bytes: u64) -> Result<usize> {
    if fragments == 0 {
        return Err(CarrierError::Geometry);
    }
    let upper = fragments
        .checked_mul(157)
        .and_then(|value| value.checked_sub(18 + check_bytes))
        .ok_or(CarrierError::Arithmetic)?
        .min(maximum);
    if upper == 0 || (18 + upper + check_bytes).div_ceil(157) != fragments {
        return Err(CarrierError::Geometry);
    }
    usize::try_from(upper).map_err(|_| CarrierError::Arithmetic)
}

fn load_fragment_partition(total: u64, count: u64, maximum: u64) -> Result<Vec<u64>> {
    if count == 0
        || total < count
        || total > count.checked_mul(maximum).ok_or(CarrierError::Arithmetic)?
    {
        return Err(CarrierError::Geometry);
    }
    let mut remaining = total;
    let mut output = Vec::new();
    for ordinal in 0..count {
        let after = count - ordinal - 1;
        let take = maximum.min(remaining - after);
        output.push(take);
        remaining -= take;
    }
    if remaining != 0 {
        return Err(CarrierError::Geometry);
    }
    Ok(output)
}

fn solve_load(
    profile: CandidateProfile,
    base: &[LogicalSection],
    interior_cells: u64,
    maximum_probe_payload: u64,
) -> Result<(u64, Vec<u64>)> {
    let slots = interior_cells / (EH_UNIT_BYTES as u64 * 8);
    let base_units = protected_unit_count(base)?;
    let check_bytes = if profile.section_check_id == CHECK_CRC32C {
        4
    } else {
        8
    };
    let max_fragments = (18 + maximum_probe_payload + check_bytes).div_ceil(157);
    let first_id = base
        .last()
        .ok_or(CarrierError::Section)?
        .section_id
        .checked_add(1)
        .ok_or(CarrierError::Arithmetic)?;
    let zero_inventory = insert_inventory(profile, base.to_vec())?;
    let zero_nonload = base_units
        .checked_add(
            section_fragment_count(&zero_inventory[0])? * u64::from(zero_inventory[0].copy_count),
        )
        .ok_or(CarrierError::Arithmetic)?;
    match slots.checked_sub(zero_nonload) {
        Some(0) => return Ok((0, Vec::new())),
        None => return Err(CarrierError::Geometry),
        Some(_) => {}
    }
    for load_count in 1_u64..=4_096_u64.saturating_sub(base.len() as u64 + 1) {
        let mut placeholders = base.to_vec();
        for ordinal in 0..load_count {
            placeholders.push(LogicalSection {
                section_id: first_id
                    .checked_add(u32::try_from(ordinal).map_err(|_| CarrierError::Arithmetic)?)
                    .ok_or(CarrierError::Arithmetic)?,
                section_type: SECTION_LOAD_PROBE,
                section_version: 0,
                closure_class: CLOSURE_M2_ALL_ONLY,
                check_id: profile.section_check_id,
                copy_count: 1,
                dependencies: Vec::new(),
                game_ordinal: None,
                payload: vec![0],
            });
        }
        let with_inventory = insert_inventory(profile, placeholders)?;
        let inventory_units =
            section_fragment_count(&with_inventory[0])? * u64::from(with_inventory[0].copy_count);
        let nonload = base_units
            .checked_add(inventory_units)
            .ok_or(CarrierError::Arithmetic)?;
        let remaining = slots.checked_sub(nonload).ok_or(CarrierError::Geometry)?;
        if remaining >= load_count && load_count >= remaining.div_ceil(max_fragments) {
            return Ok((
                remaining,
                load_fragment_partition(remaining, load_count, max_fragments)?,
            ));
        }
    }
    Err(CarrierError::Geometry)
}

fn filled_sections(
    profile: CandidateProfile,
    semantic: &SemanticEnvelopeManifest,
    reserve_payload_bytes: u64,
    maximum_probe_payload: u64,
    interior_cells: u64,
    slice_digest: &[u8; 32],
) -> Result<(Vec<LogicalSection>, Vec<u8>)> {
    let mut sections = base_sections(
        profile,
        semantic,
        reserve_payload_bytes,
        maximum_probe_payload,
    )?;
    let (load_units, partition) =
        solve_load(profile, &sections, interior_cells, maximum_probe_payload)?;
    let check_bytes = if profile.section_check_id == CHECK_CRC32C {
        4
    } else {
        8
    };
    let first_load = sections
        .last()
        .ok_or(CarrierError::Section)?
        .section_id
        .checked_add(1)
        .ok_or(CarrierError::Arithmetic)?;
    for (ordinal, fragments) in partition.into_iter().enumerate() {
        sections.push(LogicalSection {
            section_id: first_load
                .checked_add(u32::try_from(ordinal).map_err(|_| CarrierError::Arithmetic)?)
                .ok_or(CarrierError::Arithmetic)?,
            section_type: SECTION_LOAD_PROBE,
            section_version: 0,
            closure_class: CLOSURE_M2_ALL_ONLY,
            check_id: profile.section_check_id,
            copy_count: 1,
            dependencies: Vec::new(),
            game_ordinal: None,
            payload: vec![
                0;
                load_payload_for_fragments(fragments, maximum_probe_payload, check_bytes)?
            ],
        });
    }
    let probe_bytes = sections
        .iter()
        .filter(|row| {
            matches!(
                row.section_type,
                SECTION_CAPACITY_PROBE | SECTION_RESERVE_PROBE | SECTION_LOAD_PROBE
            )
        })
        .map(|row| row.payload.len())
        .sum::<usize>();
    let pad_cells = usize::try_from(interior_cells % (EH_UNIT_BYTES as u64 * 8))
        .map_err(|_| CarrierError::Arithmetic)?;
    let stream = fill_bits(
        slice_digest,
        probe_bytes
            .checked_mul(8)
            .and_then(|value| value.checked_add(pad_cells))
            .ok_or(CarrierError::Arithmetic)?,
    )?;
    let mut byte_offset = 0_usize;
    for section in sections.iter_mut().filter(|row| {
        matches!(
            row.section_type,
            SECTION_CAPACITY_PROBE | SECTION_RESERVE_PROBE | SECTION_LOAD_PROBE
        )
    }) {
        for byte in &mut section.payload {
            let at = byte_offset.checked_mul(8).ok_or(CarrierError::Arithmetic)?;
            *byte = stream[at..at + 8]
                .iter()
                .fold(0_u8, |value, bit| (value << 1) | bit);
            byte_offset += 1;
        }
    }
    let pad_start = byte_offset.checked_mul(8).ok_or(CarrierError::Arithmetic)?;
    let pad = stream[pad_start..].to_vec();
    let sections = insert_inventory(profile, sections)?;
    let units = protected_unit_count(&sections)?;
    if units != load_units + (interior_cells / (EH_UNIT_BYTES as u64 * 8) - load_units)
        || units * (EH_UNIT_BYTES as u64 * 8) + pad.len() as u64 != interior_cells
    {
        return Err(CarrierError::Ownership);
    }
    Ok((sections, pad))
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct CellOwner {
    pub kind: u8,
    pub owner_id: u32,
    pub bit_offset: u32,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ManifestationCore {
    pub profile: CandidateProfile,
    pub semantic_envelope_sha256: String,
    pub side: u16,
    pub shell_width: u16,
    pub mapping: AffineMap,
    pub routes: RouteImages,
    pub sections: Vec<LogicalSection>,
    pub units: Vec<ProtectedUnit>,
    pub carrier_bits: Vec<u8>,
    pub carrier_bytes: Vec<u8>,
    pub cell_owners: Vec<CellOwner>,
    pub interior_fixed_pad_bits: Vec<u8>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HierarchicalManifestationCore {
    pub profile: CandidateProfile,
    pub semantic_envelope_sha256: String,
    pub side: u16,
    pub shell_width: u16,
    pub mapping: HierarchicalMap,
    pub routes: RouteImages,
    pub sections: Vec<LogicalSection>,
    pub units: Vec<ProtectedUnit>,
    pub carrier_bits: Vec<u8>,
    pub carrier_bytes: Vec<u8>,
    pub cell_owners: Vec<CellOwner>,
    pub interior_fixed_pad_bits: Vec<u8>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HierarchicalCapacityProjection {
    pub side: u16,
    pub shell_width: u16,
    pub unit_slot_count: u64,
    pub logical_group_count: u64,
    pub factor_1_group_count: u64,
    pub factor_2_group_count: u64,
    pub factor_5_group_count: u64,
    pub protected_unit_count: u64,
    pub protected_cells: u64,
    pub fixed_pad_cells: u64,
    pub inventory_payload_bytes: u64,
    pub inventory_fragment_count: u64,
    pub load_fragment_counts: Vec<u64>,
    pub load_payload_bytes: Vec<u64>,
}

/// Compute the frozen v7 capacity/load fixed point without constructing route
/// bytes, a carrier, or any damage observation.
pub fn hierarchical_capacity_projection(
    side: u16,
    shell_width: u16,
    semantic: &SemanticEnvelopeManifest,
    reserve_payload_bytes: u64,
    maximum_probe_payload: u64,
) -> Result<HierarchicalCapacityProjection> {
    if reserve_payload_bytes != RESERVE_PAYLOAD_BYTES
        || maximum_probe_payload != MAXIMUM_PROBE_PAYLOAD
    {
        return Err(CarrierError::OwnerIdentity);
    }
    validate_semantic_manifest_integrity(semantic)?;
    let profile = profile_by_version(7).ok_or(CarrierError::Parameter)?;
    let mapping = HierarchicalMap::derive(side, shell_width)?;
    let slice_digest: [u8; 32] = decode_hex(&semantic.slice_semantic_sha256)?
        .try_into()
        .map_err(|_| CarrierError::OwnerIdentity)?;
    let (sections, fixed_pad) = filled_sections(
        profile,
        semantic,
        reserve_payload_bytes,
        maximum_probe_payload,
        mapping.population,
        &slice_digest,
    )?;
    let mut factor_groups = BTreeMap::<u8, u64>::new();
    for section in &sections {
        let fragments = section_fragment_count(section)?;
        let count = factor_groups.entry(section.copy_count).or_default();
        *count = count
            .checked_add(fragments)
            .ok_or(CarrierError::Arithmetic)?;
    }
    if factor_groups
        .keys()
        .any(|factor| !matches!(*factor, 1 | 2 | 5))
    {
        return Err(CarrierError::Section);
    }
    let factor_1_group_count = factor_groups.get(&1).copied().unwrap_or(0);
    let factor_2_group_count = factor_groups.get(&2).copied().unwrap_or(0);
    let factor_5_group_count = factor_groups.get(&5).copied().unwrap_or(0);
    let logical_group_count = factor_1_group_count
        .checked_add(factor_2_group_count)
        .and_then(|value| value.checked_add(factor_5_group_count))
        .ok_or(CarrierError::Arithmetic)?;
    let protected_unit_count = factor_1_group_count
        .checked_add(factor_2_group_count * 2)
        .and_then(|value| value.checked_add(factor_5_group_count * 5))
        .ok_or(CarrierError::Arithmetic)?;
    let inventory = sections.first().ok_or(CarrierError::Section)?;
    let load = sections
        .iter()
        .filter(|section| section.section_type == SECTION_LOAD_PROBE)
        .collect::<Vec<_>>();
    Ok(HierarchicalCapacityProjection {
        side,
        shell_width,
        unit_slot_count: mapping.unit_slot_count,
        logical_group_count,
        factor_1_group_count,
        factor_2_group_count,
        factor_5_group_count,
        protected_unit_count,
        protected_cells: protected_unit_count
            .checked_mul(R3_UNIT_BITS)
            .ok_or(CarrierError::Arithmetic)?,
        fixed_pad_cells: fixed_pad.len() as u64,
        inventory_payload_bytes: inventory.payload.len() as u64,
        inventory_fragment_count: section_fragment_count(inventory)?,
        load_fragment_counts: load
            .iter()
            .map(|section| section_fragment_count(section))
            .collect::<Result<Vec<_>>>()?,
        load_payload_bytes: load
            .iter()
            .map(|section| section.payload.len() as u64)
            .collect(),
    })
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EliminationCategory {
    pub category_id: &'static str,
    pub semantic_section_count: u64,
    pub logical_payload_bytes: u64,
    pub protected_unit_count: u64,
    pub protected_cells: u64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CapacityEliminationBound {
    pub profile_id: String,
    pub categories: Vec<EliminationCategory>,
    pub inventory_units: u64,
    pub tier_frame_units: u64,
    pub real_content_units: u64,
    pub capacity_probe_units: u64,
    pub reserve_probe_units: u64,
    pub protected_unit_count: u64,
    pub protected_cells: u64,
    pub route_prefix_cells: u64,
    pub lower_bound_cells: u64,
    pub carrier_ceiling_cells: u64,
}

/// Recompute the exact policy-compliant gate-5 lower bound without constructing
/// forbidden later-gate evidence.
pub fn capacity_elimination_bound(
    profile_version: u16,
    route_manifest_raw: &[u8],
    recipe_package_raw: &[u8],
    semantic: &SemanticEnvelopeManifest,
    reserve_payload_bytes: u64,
    maximum_probe_payload: u64,
) -> Result<CapacityEliminationBound> {
    if reserve_payload_bytes != RESERVE_PAYLOAD_BYTES
        || maximum_probe_payload != MAXIMUM_PROBE_PAYLOAD
    {
        return Err(CarrierError::OwnerIdentity);
    }
    validate_semantic_manifest_integrity(semantic)?;
    let profile = profile_by_version(profile_version).ok_or(CarrierError::Parameter)?;
    if !matches!(profile.version, 1 | 3) || profile.section_check_id != CHECK_CRC32C {
        return Err(CarrierError::Parameter);
    }
    let base = base_sections(
        profile,
        semantic,
        reserve_payload_bytes,
        maximum_probe_payload,
    )?;
    let with_inventory = insert_inventory(profile, base)?;
    let units_for = |section_type: u16| -> Result<u64> {
        with_inventory
            .iter()
            .filter(|row| row.section_type == section_type)
            .try_fold(0_u64, |sum, row| {
                section_fragment_count(row)?
                    .checked_mul(u64::from(row.copy_count))
                    .and_then(|count| sum.checked_add(count))
                    .ok_or(CarrierError::Arithmetic)
            })
    };
    let inventory_units = units_for(SECTION_INVENTORY)?;
    let tier_frame_units = units_for(SECTION_TIER_FRAME)?;
    let real_content_units = units_for(SECTION_CONTENT_BODY)?;
    let capacity_probe_units = units_for(SECTION_CAPACITY_PROBE)?;
    let reserve_probe_units = units_for(SECTION_RESERVE_PROBE)?;
    let category = |category_id: &'static str, section_type: u16, units: u64| {
        let rows = with_inventory
            .iter()
            .filter(|row| row.section_type == section_type)
            .collect::<Vec<_>>();
        EliminationCategory {
            category_id,
            semantic_section_count: rows.len() as u64,
            logical_payload_bytes: rows.iter().map(|row| row.payload.len() as u64).sum(),
            protected_unit_count: units,
            protected_cells: units * (EH_UNIT_BYTES * 8) as u64,
        }
    };
    let categories = vec![
        category("inventory", SECTION_INVENTORY, inventory_units),
        category("tier-frame", SECTION_TIER_FRAME, tier_frame_units),
        category("real-content", SECTION_CONTENT_BODY, real_content_units),
        category(
            "capacity-probe",
            SECTION_CAPACITY_PROBE,
            capacity_probe_units,
        ),
        category("reserve-probe", SECTION_RESERVE_PROBE, reserve_probe_units),
    ];
    let protected_unit_count = inventory_units
        .checked_add(tier_frame_units)
        .and_then(|value| value.checked_add(real_content_units))
        .and_then(|value| value.checked_add(capacity_probe_units))
        .and_then(|value| value.checked_add(reserve_probe_units))
        .ok_or(CarrierError::Arithmetic)?;
    let protected_cells = protected_unit_count
        .checked_mul((EH_UNIT_BYTES * 8) as u64)
        .ok_or(CarrierError::Arithmetic)?;
    let routes = build_route_images(
        route_manifest_raw,
        profile_version,
        recipe_package_raw,
        2_048,
        128,
    )?;
    let route_prefix_cells = routes
        .sectors
        .iter()
        .map(|row| row.route_prefix_cells)
        .sum::<u64>();
    let lower_bound_cells = protected_cells
        .checked_add(route_prefix_cells)
        .ok_or(CarrierError::Arithmetic)?;
    Ok(CapacityEliminationBound {
        profile_id: profile.id.to_owned(),
        categories,
        inventory_units,
        tier_frame_units,
        real_content_units,
        capacity_probe_units,
        reserve_probe_units,
        protected_unit_count,
        protected_cells,
        route_prefix_cells,
        lower_bound_cells,
        carrier_ceiling_cells: 4_194_304,
    })
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EliminationBoundArtifact {
    pub bound: CapacityEliminationBound,
    pub canonical_bytes: Vec<u8>,
    pub sha256: String,
}

/// Strictly load every owner needed by gate 5 and render its closed canonical
/// favorable-omission proof. This function never constructs a carrier.
pub fn render_capacity_elimination_artifact(
    profile_version: u16,
    route_manifest_raw: &[u8],
    recipe_package_raw: &[u8],
    semantic: &SemanticEnvelopeManifest,
    compiled: &SliceCompilation,
    profile_policy_raw: &[u8],
    damage_policy_raw: &[u8],
    profile_limits_raw: &[u8],
    curriculum_raw: &[u8],
) -> Result<EliminationBoundArtifact> {
    if profile_version != 3 || curriculum_raw.len() > OWNER_DOCUMENT_BYTES_MAX {
        return Err(CarrierError::Parameter);
    }
    let policy =
        load_profile_policy(profile_policy_raw).map_err(|_| CarrierError::OwnerIdentity)?;
    let damage = load_damage_policy(damage_policy_raw).map_err(|_| CarrierError::OwnerIdentity)?;
    let limits = load_profile_limits(
        profile_limits_raw,
        &policy,
        &damage,
        compiled,
        curriculum_raw,
    )
    .map_err(|_| CarrierError::OwnerIdentity)?;
    let owner_semantic =
        render_semantic_envelope(&policy, profile_policy_raw, compiled, curriculum_raw)?;
    if &owner_semantic != semantic {
        return Err(CarrierError::OwnerIdentity);
    }
    let reserve_payload_bytes = limits
        .get("semantic_capacity")
        .and_then(toml::Value::as_table)
        .and_then(|table| table.get("reserve_payload_bytes"))
        .and_then(toml::Value::as_integer)
        .and_then(|value| u64::try_from(value).ok())
        .ok_or(CarrierError::ManifestShape)?;
    let bound = capacity_elimination_bound(
        profile_version,
        route_manifest_raw,
        recipe_package_raw,
        semantic,
        reserve_payload_bytes,
        policy.maximum_probe_payload,
    )?;
    if bound.lower_bound_cells <= bound.carrier_ceiling_cells {
        return Err(CarrierError::Geometry);
    }
    let category_rows = bound.categories.iter().map(|row| {
        manifest_array([
            manifest_string(row.category_id),
            ManifestValue::U64(row.semantic_section_count),
            ManifestValue::U64(row.logical_payload_bytes),
            ManifestValue::U64(row.protected_unit_count),
            ManifestValue::U64(row.protected_cells),
        ])
    });
    let result = "lower-bound-exceeds-hard-ceiling";
    let value = manifest_object([
        (
            "schema",
            manifest_string("golden-board.m2-elimination-bound/v0"),
        ),
        ("profile_policy_sha256", manifest_string(&policy.sha256)),
        (
            "profile_limits_sha256",
            manifest_string(digest(profile_limits_raw)),
        ),
        (
            "semantic_envelope_sha256",
            manifest_string(&semantic.sha256),
        ),
        ("profile_id", manifest_string(&bound.profile_id)),
        ("side_max", ManifestValue::U64(policy.side_max)),
        (
            "protected_unit_bits",
            ManifestValue::U64((EH_UNIT_BYTES * 8) as u64),
        ),
        (
            "route_prefix_cells",
            ManifestValue::U64(bound.route_prefix_cells),
        ),
        (
            "category_row_fields",
            fields(&[
                "category_id",
                "semantic_section_count",
                "logical_payload_bytes",
                "protected_unit_count",
                "protected_cells",
            ]),
        ),
        ("category_rows", manifest_array(category_rows)),
        (
            "protected_unit_count",
            ManifestValue::U64(bound.protected_unit_count),
        ),
        ("protected_cells", ManifestValue::U64(bound.protected_cells)),
        (
            "lower_bound_cells",
            ManifestValue::U64(bound.lower_bound_cells),
        ),
        (
            "hard_ceiling_cells",
            ManifestValue::U64(bound.carrier_ceiling_cells),
        ),
        (
            "candidate_favorable_omissions",
            manifest_array([
                manifest_string("shell-headroom"),
                manifest_string("alignment-pad"),
                manifest_string("load-probe"),
            ]),
        ),
        ("result", manifest_string(result)),
    ]);
    let canonical_bytes = serialize_manifest(&value).map_err(|_| CarrierError::ManifestShape)?;
    validate_canonical_manifest(&canonical_bytes).map_err(|_| CarrierError::ManifestShape)?;
    let sha256 = digest(&canonical_bytes);
    Ok(EliminationBoundArtifact {
        bound,
        canonical_bytes,
        sha256,
    })
}

fn pair_order() -> impl Iterator<Item = (u16, u16)> {
    (64_u16..=2_048).step_by(8).flat_map(|side| {
        let maximum = 128.min((side - 8) / 2);
        (8_u16..=maximum).step_by(8).map(move |width| (side, width))
    })
}

/// Build the first complete fitting P6 manifestation in frozen pair order.
pub fn build_manifestation_core(
    profile_version: u16,
    route_manifest_raw: &[u8],
    recipe_package_raw: &[u8],
    semantic: &SemanticEnvelopeManifest,
    reserve_payload_bytes: u64,
    maximum_probe_payload: u64,
) -> Result<ManifestationCore> {
    if reserve_payload_bytes != RESERVE_PAYLOAD_BYTES
        || maximum_probe_payload != MAXIMUM_PROBE_PAYLOAD
    {
        return Err(CarrierError::OwnerIdentity);
    }
    let profile = profile_by_version(profile_version).ok_or(CarrierError::Parameter)?;
    if !matches!(profile.version, 1 | 3) || profile.section_check_id != CHECK_CRC32C {
        return Err(CarrierError::Parameter);
    }
    validate_semantic_manifest_integrity(semantic)?;
    let slice_digest: [u8; 32] = decode_hex(&semantic.slice_semantic_sha256)?
        .try_into()
        .map_err(|_| CarrierError::OwnerIdentity)?;
    let maximum_routes = build_route_images(
        route_manifest_raw,
        profile_version,
        recipe_package_raw,
        2_048,
        128,
    )?;
    let prefix = usize::try_from(maximum_routes.sectors[0].route_prefix_cells)
        .map_err(|_| CarrierError::Arithmetic)?;
    if maximum_routes
        .sectors
        .iter()
        .any(|row| row.route_prefix_cells as usize != prefix)
    {
        return Err(CarrierError::Ownership);
    }
    let mut selected = None;
    for (side, width) in pair_order() {
        let sector_cells = usize::from(width) * (usize::from(side) - usize::from(width));
        if maximum_routes.sectors.iter().any(|row| {
            prefix + usize::try_from(row.headroom_cells).unwrap_or(usize::MAX) > sector_cells
        }) {
            continue;
        }
        let mapping = AffineMap::derive(side, width, profile_version)?;
        let base = base_sections(
            profile,
            semantic,
            reserve_payload_bytes,
            maximum_probe_payload,
        )?;
        if solve_load(profile, &base, mapping.population, maximum_probe_payload).is_ok() {
            selected = Some((side, width, mapping));
            break;
        }
    }
    let (side, shell_width, mapping) = selected.ok_or(CarrierError::Geometry)?;
    let routes = build_route_images(
        route_manifest_raw,
        profile_version,
        recipe_package_raw,
        side,
        shell_width,
    )?;
    let (sections, interior_fixed_pad_bits) = filled_sections(
        profile,
        semantic,
        reserve_payload_bytes,
        maximum_probe_payload,
        mapping.population,
        &slice_digest,
    )?;
    let units = protect_sections(profile_version, &sections)?;
    let cell_count = usize::from(side)
        .checked_mul(usize::from(side))
        .ok_or(CarrierError::Arithmetic)?;
    let mut carrier_bits = vec![2_u8; cell_count];
    let mut owners = vec![None; cell_count];
    for sector in &routes.sectors {
        let prefix =
            usize::try_from(sector.route_prefix_cells).map_err(|_| CarrierError::Arithmetic)?;
        let headroom =
            usize::try_from(sector.headroom_cells).map_err(|_| CarrierError::Arithmetic)?;
        for (offset, bit) in sector.bits.iter().copied().enumerate() {
            let (row, column) = sector_cell_at(
                usize::from(side),
                usize::from(shell_width),
                sector.sector_id,
                offset,
            )
            .map_err(|_| CarrierError::Geometry)?;
            let flat = row * usize::from(side) + column;
            let (kind, bit_offset) = if offset < prefix {
                (1, offset)
            } else if offset < prefix + headroom {
                (2, offset - prefix)
            } else {
                (3, offset - prefix - headroom)
            };
            if carrier_bits[flat] != 2 || owners[flat].is_some() {
                return Err(CarrierError::Ownership);
            }
            carrier_bits[flat] = bit;
            owners[flat] = Some(CellOwner {
                kind,
                owner_id: u32::from(sector.sector_id),
                bit_offset: u32::try_from(bit_offset).map_err(|_| CarrierError::Arithmetic)?,
            });
        }
    }
    for unit in &units {
        let bits = bytes_to_bits(&unit.encoded);
        for (bit_offset, bit) in bits.into_iter().enumerate() {
            let logical = unit
                .logical_bit_first
                .checked_add(bit_offset as u64)
                .ok_or(CarrierError::Arithmetic)?;
            let physical = mapping.forward(logical)?;
            let (row, column) = mapping.matrix_cell(physical)?;
            let flat = usize::from(row) * usize::from(side) + usize::from(column);
            if carrier_bits[flat] != 2 || owners[flat].is_some() {
                return Err(CarrierError::Ownership);
            }
            carrier_bits[flat] = bit;
            owners[flat] = Some(CellOwner {
                kind: 4,
                owner_id: unit.physical_unit_id,
                bit_offset: bit_offset as u32,
            });
        }
    }
    let mut pad_offset = 0_usize;
    for flat in 0..cell_count {
        if carrier_bits[flat] == 2 {
            let row = flat / usize::from(side);
            let column = flat % usize::from(side);
            if row < usize::from(shell_width)
                || row >= usize::from(side - shell_width)
                || column < usize::from(shell_width)
                || column >= usize::from(side - shell_width)
            {
                return Err(CarrierError::Ownership);
            }
            carrier_bits[flat] = *interior_fixed_pad_bits
                .get(pad_offset)
                .ok_or(CarrierError::Ownership)?;
            owners[flat] = Some(CellOwner {
                kind: 5,
                owner_id: 0,
                bit_offset: u32::try_from(pad_offset).map_err(|_| CarrierError::Arithmetic)?,
            });
            pad_offset += 1;
        }
    }
    if pad_offset != interior_fixed_pad_bits.len() || carrier_bits.iter().any(|bit| *bit > 1) {
        return Err(CarrierError::Ownership);
    }
    let cell_owners = owners
        .into_iter()
        .collect::<Option<Vec<_>>>()
        .ok_or(CarrierError::Ownership)?;
    let carrier_bytes = serialize_obs_bits(&carrier_bits)?;
    Ok(ManifestationCore {
        profile,
        semantic_envelope_sha256: semantic.sha256.clone(),
        side,
        shell_width,
        mapping,
        routes,
        sections,
        units,
        carrier_bits,
        carrier_bytes,
        cell_owners,
        interior_fixed_pad_bits,
    })
}

/// Build the v7 interior and carrier from already owner-validated route images.
///
/// Route-data v1 remains a separate promotion boundary. This constructor does
/// not accept unparsed route bytes and therefore cannot accidentally claim
/// that a provisional route/package is frozen.
pub fn build_hierarchical_manifestation_core_at(
    side: u16,
    shell_width: u16,
    routes: RouteImages,
    semantic: &SemanticEnvelopeManifest,
    reserve_payload_bytes: u64,
    maximum_probe_payload: u64,
) -> Result<HierarchicalManifestationCore> {
    if reserve_payload_bytes != RESERVE_PAYLOAD_BYTES
        || maximum_probe_payload != MAXIMUM_PROBE_PAYLOAD
    {
        return Err(CarrierError::OwnerIdentity);
    }
    validate_semantic_manifest_integrity(semantic)?;
    let profile = profile_by_version(7).ok_or(CarrierError::Parameter)?;
    if profile.transport != TransportFamily::Eh72HierarchicalRepetition
        || profile.section_check_id != CHECK_CRC32C
        || profile.required_copy_count != 1
    {
        return Err(CarrierError::Parameter);
    }
    let mapping = HierarchicalMap::derive(side, shell_width)?;
    let sector_cells = usize::from(shell_width)
        .checked_mul(
            usize::from(side)
                .checked_sub(usize::from(shell_width))
                .ok_or(CarrierError::Geometry)?,
        )
        .ok_or(CarrierError::Arithmetic)?;
    for (sector_index, sector) in routes.sectors.iter().enumerate() {
        if usize::from(sector.sector_id) != sector_index
            || sector.bits.len() != sector_cells
            || sector.bits.iter().any(|bit| *bit > 1)
            || sector.route_prefix_cells + sector.headroom_cells > sector_cells as u64
        {
            return Err(CarrierError::Ownership);
        }
    }
    let slice_digest: [u8; 32] = decode_hex(&semantic.slice_semantic_sha256)?
        .try_into()
        .map_err(|_| CarrierError::OwnerIdentity)?;
    let (sections, interior_fixed_pad_bits) = filled_sections(
        profile,
        semantic,
        reserve_payload_bytes,
        maximum_probe_payload,
        mapping.population,
        &slice_digest,
    )?;
    let units = protect_sections_hierarchical(&sections, mapping)?;
    if units.len() as u64 != mapping.unit_slot_count
        || interior_fixed_pad_bits.len() as u64 != mapping.fixed_pad_cells
    {
        return Err(CarrierError::Ownership);
    }
    let cell_count = usize::from(side)
        .checked_mul(usize::from(side))
        .ok_or(CarrierError::Arithmetic)?;
    let mut carrier_bits = vec![2_u8; cell_count];
    let mut owners = vec![None; cell_count];
    for sector in &routes.sectors {
        let prefix =
            usize::try_from(sector.route_prefix_cells).map_err(|_| CarrierError::Arithmetic)?;
        let headroom =
            usize::try_from(sector.headroom_cells).map_err(|_| CarrierError::Arithmetic)?;
        for (offset, bit) in sector.bits.iter().copied().enumerate() {
            let (row, column) = sector_cell_at(
                usize::from(side),
                usize::from(shell_width),
                sector.sector_id,
                offset,
            )
            .map_err(|_| CarrierError::Geometry)?;
            let flat = row * usize::from(side) + column;
            let (kind, owner_offset) = if offset < prefix {
                (1, offset)
            } else if offset < prefix + headroom {
                (2, offset - prefix)
            } else {
                (3, offset - prefix - headroom)
            };
            if carrier_bits[flat] != 2 || owners[flat].is_some() {
                return Err(CarrierError::Ownership);
            }
            carrier_bits[flat] = bit;
            owners[flat] = Some(CellOwner {
                kind,
                owner_id: u32::from(sector.sector_id),
                bit_offset: u32::try_from(owner_offset).map_err(|_| CarrierError::Arithmetic)?,
            });
        }
    }
    for (physical_ordinal, unit) in units.iter().enumerate() {
        if unit.physical_unit_id != physical_ordinal as u32 + 1 {
            return Err(CarrierError::Ownership);
        }
        for (bit_offset, bit) in bytes_to_bits(&unit.encoded).into_iter().enumerate() {
            let physical = mapping.forward_unit_bit(
                physical_ordinal as u64,
                u16::try_from(bit_offset).map_err(|_| CarrierError::Arithmetic)?,
            )?;
            let (row, column) = mapping.matrix_cell(physical)?;
            let flat = usize::from(row) * usize::from(side) + usize::from(column);
            if carrier_bits[flat] != 2 || owners[flat].is_some() {
                return Err(CarrierError::Ownership);
            }
            carrier_bits[flat] = bit;
            owners[flat] = Some(CellOwner {
                kind: 4,
                owner_id: unit.physical_unit_id,
                bit_offset: bit_offset as u32,
            });
        }
    }
    // The v1 map defines the fixed-pad *set* as the affine image of the
    // logical tail.  The inherited fill-stream owner separately fixes the bit
    // order as the unoccupied interior cells in physical row-major order.
    // Keeping those two rules separate is observable whenever the tail is not
    // byte-constant.
    let mut pad_offset = 0_usize;
    for interior_row in 0..usize::from(mapping.interior_side) {
        for interior_column in 0..usize::from(mapping.interior_side) {
            let row = interior_row + usize::from(shell_width);
            let column = interior_column + usize::from(shell_width);
            let flat = row * usize::from(side) + column;
            if carrier_bits[flat] != 2 {
                continue;
            }
            let physical = (interior_row as u64)
                .checked_mul(u64::from(mapping.interior_side))
                .and_then(|value| value.checked_add(interior_column as u64))
                .ok_or(CarrierError::Arithmetic)?;
            if !matches!(
                mapping.inverse(physical)?,
                HierarchicalInverse::FixedPad { .. }
            ) {
                return Err(CarrierError::Ownership);
            }
            carrier_bits[flat] = *interior_fixed_pad_bits
                .get(pad_offset)
                .ok_or(CarrierError::Ownership)?;
            owners[flat] = Some(CellOwner {
                kind: 5,
                owner_id: 0,
                bit_offset: u32::try_from(pad_offset).map_err(|_| CarrierError::Arithmetic)?,
            });
            pad_offset += 1;
        }
    }
    if pad_offset != interior_fixed_pad_bits.len() || carrier_bits.iter().any(|bit| *bit > 1) {
        return Err(CarrierError::Ownership);
    }
    let cell_owners = owners
        .into_iter()
        .collect::<Option<Vec<_>>>()
        .ok_or(CarrierError::Ownership)?;
    let carrier_bytes = serialize_obs_bits(&carrier_bits)?;
    Ok(HierarchicalManifestationCore {
        profile,
        semantic_envelope_sha256: semantic.sha256.clone(),
        side,
        shell_width,
        mapping,
        routes,
        sections,
        units,
        carrier_bits,
        carrier_bytes,
        cell_owners,
        interior_fixed_pad_bits,
    })
}

/// Reconstruct a clean v7 carrier through the same conflict-safe physical
/// grouping used by the observation decoder.
pub fn validate_clean_hierarchical_reconstruction(
    core: &HierarchicalManifestationCore,
    compiled: &SliceCompilation,
) -> Result<()> {
    if core.profile.version != 7
        || core.carrier_bytes != serialize_obs_bits(&core.carrier_bits)?
        || core.units.len() as u64 != core.mapping.unit_slot_count
    {
        return Err(CarrierError::Reconstruction);
    }
    let side = usize::from(core.side);
    let mut fragment_rows = BTreeMap::<u32, Vec<FragmentWitness>>::new();
    let mut ordinal = 0usize;
    while ordinal < core.units.len() {
        let first = &core.units[ordinal];
        let factor = usize::from(first.physical_replica_count);
        let end = ordinal
            .checked_add(factor)
            .ok_or(CarrierError::Arithmetic)?;
        let group = core
            .units
            .get(ordinal..end)
            .ok_or(CarrierError::Reconstruction)?;
        if group.iter().enumerate().any(|(replica, unit)| {
            unit.section_id != first.section_id
                || unit.fragment_index != first.fragment_index
                || usize::from(unit.replica_index) != replica
                || usize::from(unit.physical_replica_count) != factor
                || unit.semantic_copy_id != 0
        }) {
            return Err(CarrierError::Reconstruction);
        }
        let mut observations = Vec::with_capacity(factor);
        for (lane_offset, unit) in group.iter().enumerate() {
            let physical_ordinal = ordinal + lane_offset;
            let mut encoded = [0_u8; EH_UNIT_BYTES];
            for bit_offset in 0..EH_UNIT_BYTES * 8 {
                let physical = core
                    .mapping
                    .forward_unit_bit(physical_ordinal as u64, bit_offset as u16)?;
                let (row, column) = core.mapping.matrix_cell(physical)?;
                encoded[bit_offset / 8] |= core.carrier_bits
                    [usize::from(row) * side + usize::from(column)]
                    << (7 - bit_offset % 8);
            }
            if encoded != unit.encoded {
                return Err(CarrierError::Reconstruction);
            }
            observations.push(Some(EhObservation {
                encoded,
                erasures: Vec::new(),
            }));
        }
        let recovered = recover_hierarchical_eh_group(core.profile, &observations)
            .map_err(|_| CarrierError::Reconstruction)?;
        if recovered.state != crate::candidate::FragmentState::Verified {
            return Err(CarrierError::Reconstruction);
        }
        let common = recovered.common.ok_or(CarrierError::Reconstruction)?;
        let block = decode_common_block(&common, 7).map_err(|_| CarrierError::Reconstruction)?;
        if block.section_id != first.section_id
            || block.fragment_index != first.fragment_index
            || block.semantic_copy_id != 0
        {
            return Err(CarrierError::Reconstruction);
        }
        fragment_rows
            .entry(block.section_id)
            .or_default()
            .push(FragmentWitness {
                raw_block: common,
                quality: RecoveryQuality::Verified,
            });
        ordinal = end;
    }
    let mut decoded_sections = BTreeMap::new();
    for expected in &core.sections {
        let rows = fragment_rows
            .get(&expected.section_id)
            .ok_or(CarrierError::Reconstruction)?;
        let witness = assemble_semantic_copy(rows, 7).map_err(|_| CarrierError::Reconstruction)?;
        let canonical =
            aggregate_section_witnesses(&[witness]).map_err(|_| CarrierError::Reconstruction)?;
        let decoded =
            decode_section(&canonical.envelope).map_err(|_| CarrierError::Reconstruction)?;
        if decoded.section_id != expected.section_id || decoded.payload != expected.payload {
            return Err(CarrierError::Reconstruction);
        }
        decoded_sections.insert(expected.section_id, decoded);
    }
    let inventory = decode_inventory(
        &decoded_sections
            .get(&1)
            .ok_or(CarrierError::Reconstruction)?
            .payload,
    )
    .map_err(|_| CarrierError::Reconstruction)?;
    if inventory.inventory_version != 1 {
        return Err(CarrierError::Reconstruction);
    }
    for expected in &core.sections {
        let entry = inventory
            .entries
            .binary_search_by_key(&expected.section_id, |entry| entry.section_id)
            .ok()
            .map(|index| &inventory.entries[index])
            .ok_or(CarrierError::Reconstruction)?;
        if entry.copy_count != 1 || entry.physical_replica_count != expected.copy_count {
            return Err(CarrierError::Reconstruction);
        }
        validate_envelope_against_inventory(
            decoded_sections
                .get(&expected.section_id)
                .ok_or(CarrierError::Reconstruction)?,
            &inventory,
        )
        .map_err(|_| CarrierError::Reconstruction)?;
    }
    for (id, expected) in [
        (2_u32, compiled.required_stream()),
        (3_u32, compiled.all_stream()),
    ] {
        let tier = decode_tier_frame(
            &decoded_sections
                .get(&id)
                .ok_or(CarrierError::Reconstruction)?
                .payload,
            id,
        )
        .map_err(|_| CarrierError::Reconstruction)?;
        let bodies = tier
            .body_section_ids
            .iter()
            .map(|body_id| {
                decoded_sections
                    .get(body_id)
                    .map(|row| (*body_id, row.payload.clone()))
                    .ok_or(CarrierError::Reconstruction)
            })
            .collect::<Result<BTreeMap<_, _>>>()?;
        let assembled =
            assemble_content_stream(&tier, &bodies).map_err(|_| CarrierError::Reconstruction)?;
        if assembled != expected {
            return Err(CarrierError::Reconstruction);
        }
    }
    Ok(())
}

/// Reconstruct every clean semantic section and both exact content streams.
pub fn validate_clean_reconstruction(
    core: &ManifestationCore,
    compiled: &SliceCompilation,
) -> Result<()> {
    if core.carrier_bytes != serialize_obs_bits(&core.carrier_bits)? {
        return Err(CarrierError::Reconstruction);
    }
    let side = usize::from(core.side);
    for sector in &core.routes.sectors {
        for (offset, expected) in sector.bits.iter().copied().enumerate() {
            let (row, column) = sector_cell_at(
                side,
                usize::from(core.shell_width),
                sector.sector_id,
                offset,
            )
            .map_err(|_| CarrierError::Geometry)?;
            if core.carrier_bits[row * side + column] != expected {
                return Err(CarrierError::Reconstruction);
            }
        }
    }
    let mut fragments = BTreeMap::<(u32, u16), Vec<FragmentWitness>>::new();
    for unit in &core.units {
        let mut encoded = [0_u8; EH_UNIT_BYTES];
        for bit_offset in 0..EH_UNIT_BYTES * 8 {
            let logical = unit.logical_bit_first + bit_offset as u64;
            let physical = core.mapping.forward(logical)?;
            let (row, column) = core.mapping.matrix_cell(physical)?;
            encoded[bit_offset / 8] |= core.carrier_bits
                [usize::from(row) * side + usize::from(column)]
                << (7 - bit_offset % 8);
        }
        if encoded != unit.encoded {
            return Err(CarrierError::Reconstruction);
        }
        let decoded = decode_eh_unit(
            &EhObservation {
                encoded,
                erasures: Vec::new(),
            },
            core.profile.version,
        )
        .map_err(|_| CarrierError::Reconstruction)?;
        let block = decode_common_block(&decoded.common, core.profile.version)
            .map_err(|_| CarrierError::Reconstruction)?;
        fragments
            .entry((block.section_id, block.semantic_copy_id))
            .or_default()
            .push(FragmentWitness {
                raw_block: decoded.common,
                quality: RecoveryQuality::Verified,
            });
    }
    let mut section_witnesses = BTreeMap::<u32, Vec<crate::SectionWitness>>::new();
    for ((section_id, _), rows) in fragments {
        section_witnesses.entry(section_id).or_default().push(
            assemble_semantic_copy(&rows, core.profile.version)
                .map_err(|_| CarrierError::Reconstruction)?,
        );
    }
    let mut decoded_sections = BTreeMap::new();
    for expected in &core.sections {
        let witnesses = section_witnesses
            .get(&expected.section_id)
            .ok_or(CarrierError::Reconstruction)?;
        let canonical =
            aggregate_section_witnesses(witnesses).map_err(|_| CarrierError::Reconstruction)?;
        let decoded =
            decode_section(&canonical.envelope).map_err(|_| CarrierError::Reconstruction)?;
        if decoded.payload != expected.payload || decoded.section_id != expected.section_id {
            return Err(CarrierError::Reconstruction);
        }
        decoded_sections.insert(expected.section_id, decoded);
    }
    let inventory = decode_inventory(
        &decoded_sections
            .get(&1)
            .ok_or(CarrierError::Reconstruction)?
            .payload,
    )
    .map_err(|_| CarrierError::Reconstruction)?;
    for section in decoded_sections.values() {
        validate_envelope_against_inventory(section, &inventory)
            .map_err(|_| CarrierError::Reconstruction)?;
    }
    for (id, expected) in [
        (2_u32, compiled.required_stream()),
        (3_u32, compiled.all_stream()),
    ] {
        let tier = decode_tier_frame(
            &decoded_sections
                .get(&id)
                .ok_or(CarrierError::Reconstruction)?
                .payload,
            id,
        )
        .map_err(|_| CarrierError::Reconstruction)?;
        let bodies = tier
            .body_section_ids
            .iter()
            .map(|body_id| {
                decoded_sections
                    .get(body_id)
                    .map(|row| (*body_id, row.payload.clone()))
                    .ok_or(CarrierError::Reconstruction)
            })
            .collect::<Result<BTreeMap<_, _>>>()?;
        let assembled =
            assemble_content_stream(&tier, &bodies).map_err(|_| CarrierError::Reconstruction)?;
        if assembled != expected {
            return Err(CarrierError::Reconstruction);
        }
    }
    Ok(())
}

fn manifest_object(
    values: impl IntoIterator<Item = (&'static str, ManifestValue)>,
) -> ManifestValue {
    ManifestValue::Object(
        values
            .into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}

fn mapping_manifest(map: AffineMap) -> ManifestValue {
    manifest_object([
        ("id", manifest_string("affine-interior-v1")),
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
    ])
}

fn packed_bits(bits: &[u8]) -> Result<Vec<u8>> {
    if bits.len() % 8 != 0 || bits.iter().any(|bit| *bit > 1) {
        return Err(CarrierError::Parameter);
    }
    Ok(bits
        .chunks_exact(8)
        .map(|chunk| chunk.iter().fold(0_u8, |value, bit| (value << 1) | bit))
        .collect())
}

fn shell_rows(core: &ManifestationCore) -> Result<Vec<ManifestValue>> {
    core.routes
        .sectors
        .iter()
        .map(|row| {
            let fixed_pad = row.bits.len() as u64 - row.route_prefix_cells - row.headroom_cells;
            Ok(manifest_object([
                ("sector_id", ManifestValue::U64(u64::from(row.sector_id))),
                (
                    "route_prefix_cells",
                    ManifestValue::U64(row.route_prefix_cells),
                ),
                ("headroom_cells", ManifestValue::U64(row.headroom_cells)),
                ("fixed_pad_cells", ManifestValue::U64(fixed_pad)),
                (
                    "image_sha256",
                    manifest_string(digest(&packed_bits(&row.bits)?)),
                ),
            ]))
        })
        .collect()
}

fn section_rows(core: &ManifestationCore) -> Result<Vec<ManifestValue>> {
    core.sections
        .iter()
        .map(|row| {
            let envelope = row.envelope()?;
            Ok(manifest_object([
                ("section_id", ManifestValue::U64(u64::from(row.section_id))),
                (
                    "section_type",
                    ManifestValue::U64(u64::from(row.section_type)),
                ),
                (
                    "closure_class",
                    ManifestValue::U64(u64::from(row.closure_class)),
                ),
                ("check_id", ManifestValue::U64(u64::from(row.check_id))),
                ("copy_count", ManifestValue::U64(u64::from(row.copy_count))),
                (
                    "dependency_ids",
                    manifest_array(
                        row.dependencies
                            .iter()
                            .map(|id| ManifestValue::U64(u64::from(*id))),
                    ),
                ),
                (
                    "logical_payload_bytes",
                    ManifestValue::U64(row.payload.len() as u64),
                ),
                ("envelope_bytes", ManifestValue::U64(envelope.len() as u64)),
                (
                    "fragment_count",
                    ManifestValue::U64(section_fragment_count(row)?),
                ),
            ]))
        })
        .collect()
}

fn unit_rows(core: &ManifestationCore) -> Vec<ManifestValue> {
    core.units
        .iter()
        .map(|row| {
            manifest_object([
                (
                    "physical_unit_id",
                    ManifestValue::U64(u64::from(row.physical_unit_id)),
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
                ("transport_id", manifest_string("eh72-replicated-v0")),
                ("encoded_bytes", ManifestValue::U64(EH_UNIT_BYTES as u64)),
                ("encoded_sha256", manifest_string(digest(&row.encoded))),
                (
                    "logical_bit_first",
                    ManifestValue::U64(row.logical_bit_first),
                ),
                (
                    "logical_bit_count",
                    ManifestValue::U64((EH_UNIT_BYTES * 8) as u64),
                ),
            ])
        })
        .collect()
}

fn cell_table_sha256(core: &ManifestationCore) -> String {
    let mut hasher = Sha256::new();
    for owner in &core.cell_owners {
        hasher.update([owner.kind]);
        hasher.update(owner.owner_id.to_be_bytes());
        hasher.update(owner.bit_offset.to_be_bytes());
    }
    format!("{:x}", hasher.finalize())
}

fn ownership_ledger(
    core: &ManifestationCore,
    shell: &[ManifestValue],
    units: &[ManifestValue],
) -> Result<Vec<u8>> {
    let value = manifest_object([
        (
            "schema",
            manifest_string("golden-board.m2-ownership-ledger/v0"),
        ),
        ("profile_id", manifest_string(core.profile.id)),
        ("side", ManifestValue::U64(u64::from(core.side))),
        (
            "shell_width",
            ManifestValue::U64(u64::from(core.shell_width)),
        ),
        ("mapping", mapping_manifest(core.mapping)),
        ("shell_rows", ManifestValue::Array(shell.to_vec())),
        ("unit_rows", ManifestValue::Array(units.to_vec())),
        (
            "interior_fixed_pad",
            manifest_object([
                (
                    "logical_bit_first",
                    ManifestValue::U64(core.units.len() as u64 * (EH_UNIT_BYTES * 8) as u64),
                ),
                (
                    "logical_bit_count",
                    ManifestValue::U64(core.interior_fixed_pad_bits.len() as u64),
                ),
                (
                    "fill_order",
                    manifest_string("unoccupied-interior-cells-in-physical-row-major-order"),
                ),
            ]),
        ),
        (
            "cell_table",
            manifest_object([
                ("row_bytes", ManifestValue::U64(9)),
                (
                    "row_count",
                    ManifestValue::U64(core.cell_owners.len() as u64),
                ),
                ("row_order", manifest_string("canonical-matrix-row-major")),
                (
                    "owner_kind_ids",
                    manifest_array([
                        manifest_string("1-shell-route"),
                        manifest_string("2-shell-headroom"),
                        manifest_string("3-shell-fixed-pad"),
                        manifest_string("4-protected-unit"),
                        manifest_string("5-interior-fixed-pad"),
                    ]),
                ),
                (
                    "owner_id_rule",
                    manifest_string(
                        "sector-id-for-shell-kinds-physical-unit-id-for-protected-unit-zero-for-interior-fixed-pad",
                    ),
                ),
                (
                    "owner_bit_offset_rule",
                    manifest_string("zero-based-offset-within-named-owner"),
                ),
            ]),
        ),
        (
            "cell_table_sha256",
            manifest_string(cell_table_sha256(core)),
        ),
    ]);
    serialize_manifest(&value).map_err(|_| CarrierError::ManifestShape)
}

fn candidate_ledger(core: &ManifestationCore, package: &RecipePackage) -> Result<ManifestValue> {
    let mut owners = core
        .sections
        .iter()
        .map(|row| {
            manifest_object([
                (
                    "owner_id",
                    manifest_string(format!("section:{:010}", row.section_id)),
                ),
                (
                    "section_type",
                    ManifestValue::U64(u64::from(row.section_type)),
                ),
                (
                    "closure_class",
                    ManifestValue::U64(u64::from(row.closure_class)),
                ),
                ("copy_count", ManifestValue::U64(u64::from(row.copy_count))),
                (
                    "logical_bytes",
                    ManifestValue::U64(row.payload.len() as u64),
                ),
            ])
        })
        .collect::<Vec<_>>();
    owners.sort_by(|left, right| {
        text(object(left).unwrap().get("owner_id").unwrap())
            .unwrap()
            .cmp(text(object(right).unwrap().get("owner_id").unwrap()).unwrap())
    });
    let check_bytes = 4_u64;
    let protected_unit_count = core.units.len() as u64;
    let envelope_bytes = core.sections.iter().try_fold(0_u64, |sum, row| {
        let value = (18_u64 + 4 * row.dependencies.len() as u64) * u64::from(row.copy_count);
        sum.checked_add(value).ok_or(CarrierError::Arithmetic)
    })?;
    let section_check_bytes = core.sections.iter().try_fold(0_u64, |sum, row| {
        sum.checked_add(check_bytes * u64::from(row.copy_count))
            .ok_or(CarrierError::Arithmetic)
    })?;
    let physical_envelopes = core.sections.iter().try_fold(0_u64, |sum, row| {
        let envelope = row.envelope()?;
        sum.checked_add(envelope.len() as u64 * u64::from(row.copy_count))
            .ok_or(CarrierError::Arithmetic)
    })?;
    let fragment_zero_pad_bytes = protected_unit_count
        .checked_mul(157)
        .and_then(|value| value.checked_sub(physical_envelopes))
        .ok_or(CarrierError::Arithmetic)?;
    let shell_count = |owner: ShellOwner| -> u64 {
        core.routes
            .sectors
            .iter()
            .flat_map(|row| &row.spans)
            .filter(|row| row.owner == owner)
            .map(|row| row.cell_count)
            .sum()
    };
    let mut interior_counts = [0_u64; 7];
    let section_types = core
        .sections
        .iter()
        .map(|row| (row.section_id, row.section_type))
        .collect::<BTreeMap<_, _>>();
    for unit in &core.units {
        interior_counts[usize::from(section_types[&unit.section_id])] += (EH_UNIT_BYTES * 8) as u64;
    }
    let real_protected = interior_counts[usize::from(SECTION_INVENTORY)]
        + interior_counts[usize::from(SECTION_TIER_FRAME)]
        + interior_counts[usize::from(SECTION_CONTENT_BODY)];
    let recipe_steps = package
        .recipe_primitive_steps(30)
        .ok_or(CarrierError::Recipe)?;
    let values = [
        ("envelope_bytes", envelope_bytes),
        ("fragment_header_bytes", 30 * protected_unit_count),
        ("fragment_zero_pad_bytes", fragment_zero_pad_bytes),
        ("local_check_bytes", 4 * protected_unit_count),
        ("section_check_bytes", section_check_bytes),
        ("transport_pad_bytes", protected_unit_count),
        ("parity_bytes", 24 * protected_unit_count),
        (
            "shell_instruction_cells",
            shell_count(ShellOwner::Instruction),
        ),
        ("shell_example_cells", shell_count(ShellOwner::Example)),
        ("shell_recipe_cells", shell_count(ShellOwner::Recipe)),
        ("shell_headroom_cells", shell_count(ShellOwner::Headroom)),
        ("shell_fixed_pad_cells", shell_count(ShellOwner::FixedPad)),
        ("real_protected_cells", real_protected),
        (
            "capacity_probe_cells",
            interior_counts[usize::from(SECTION_CAPACITY_PROBE)],
        ),
        (
            "reserve_probe_cells",
            interior_counts[usize::from(SECTION_RESERVE_PROBE)],
        ),
        (
            "load_probe_cells",
            interior_counts[usize::from(SECTION_LOAD_PROBE)],
        ),
        (
            "interior_fixed_pad_cells",
            core.interior_fixed_pad_bits.len() as u64,
        ),
        ("protected_unit_count", protected_unit_count),
        ("codeword_count", protected_unit_count * 24),
        (
            "worst_case_section_attempts",
            core.sections
                .iter()
                .map(|row| u64::from(row.copy_count))
                .max()
                .unwrap_or(0),
        ),
        (
            "worst_case_work_units",
            protected_unit_count
                .checked_mul(24)
                .and_then(|value| value.checked_mul(recipe_steps))
                .ok_or(CarrierError::Arithmetic)?,
        ),
        ("scratch_bytes", package.peak_scratch_bytes),
        ("unused_cells", 0),
        ("total_cells", core.carrier_bits.len() as u64),
    ];
    let mut object = BTreeMap::new();
    object.insert(
        "logical_bytes_by_owner".to_owned(),
        ManifestValue::Array(owners),
    );
    for (key, value) in values {
        object.insert(key.to_owned(), ManifestValue::U64(value));
    }
    let shell = shell_count(ShellOwner::Instruction)
        + shell_count(ShellOwner::Example)
        + shell_count(ShellOwner::Recipe)
        + shell_count(ShellOwner::Headroom)
        + shell_count(ShellOwner::FixedPad);
    if shell
        + real_protected
        + interior_counts[usize::from(SECTION_CAPACITY_PROBE)]
        + interior_counts[usize::from(SECTION_RESERVE_PROBE)]
        + interior_counts[usize::from(SECTION_LOAD_PROBE)]
        + core.interior_fixed_pad_bits.len() as u64
        != core.carrier_bits.len() as u64
    {
        return Err(CarrierError::Ownership);
    }
    let copied_payload = core
        .sections
        .iter()
        .map(|row| row.payload.len() as u64 * u64::from(row.copy_count))
        .sum::<u64>();
    if (envelope_bytes
        + copied_payload
        + section_check_bytes
        + fragment_zero_pad_bytes
        + 30 * protected_unit_count
        + 4 * protected_unit_count
        + protected_unit_count
        + 24 * protected_unit_count)
        != protected_unit_count * EH_UNIT_BYTES as u64
    {
        return Err(CarrierError::Ownership);
    }
    Ok(ManifestValue::Object(object))
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct DensityScope {
    id: &'static str,
    cells: u64,
    ones: u64,
}

fn density_data(core: &ManifestationCore) -> Result<(Vec<DensityScope>, [u64; 6])> {
    let side = usize::from(core.side);
    let width = usize::from(core.shell_width);
    let unit_types = core
        .units
        .iter()
        .map(|unit| {
            let section_type = core
                .sections
                .iter()
                .find(|row| row.section_id == unit.section_id)
                .map(|row| row.section_type)
                .ok_or(CarrierError::Ownership)?;
            Ok((unit.physical_unit_id, section_type))
        })
        .collect::<Result<BTreeMap<_, _>>>()?;
    let ids = [
        "shell",
        "real-protected",
        "capacity-probe",
        "reserve-probe",
        "load-probe",
        "fixed-pad",
        "complete-interior",
    ];
    let mut scopes = ids.map(|id| DensityScope {
        id,
        cells: 0,
        ones: 0,
    });
    for (flat, bit) in core.carrier_bits.iter().copied().enumerate() {
        let row = flat / side;
        let column = flat % side;
        let owner = core.cell_owners[flat];
        let mut add = |index: usize| {
            scopes[index].cells += 1;
            scopes[index].ones += u64::from(bit);
        };
        if owner.kind <= 3 {
            add(0);
        }
        if owner.kind == 4 {
            match unit_types[&owner.owner_id] {
                SECTION_INVENTORY | SECTION_TIER_FRAME | SECTION_CONTENT_BODY => add(1),
                SECTION_CAPACITY_PROBE => add(2),
                SECTION_RESERVE_PROBE => add(3),
                SECTION_LOAD_PROBE => add(4),
                _ => return Err(CarrierError::Ownership),
            }
        }
        if matches!(owner.kind, 3 | 5) {
            add(5);
        }
        if row >= width && row < side - width && column >= width && column < side - width {
            add(6);
        }
    }
    if scopes.iter().any(|row| row.ones > row.cells) {
        return Err(CarrierError::Ownership);
    }
    let interior = usize::from(core.mapping.interior_side);
    let bit_at =
        |row: usize, column: usize| core.carrier_bits[(row + width) * side + column + width];
    let mut horizontal = 0_u64;
    let mut vertical = 0_u64;
    let mut seen_rows = BTreeSet::new();
    let mut repeated_rows = 0_u64;
    for row in 0..interior {
        let values = (0..interior)
            .map(|column| bit_at(row, column))
            .collect::<Vec<_>>();
        let mut run = 0_u64;
        let mut prior = 2_u8;
        for bit in &values {
            run = if *bit == prior { run + 1 } else { 1 };
            horizontal = horizontal.max(run);
            prior = *bit;
        }
        if !seen_rows.insert(values) {
            repeated_rows += 1;
        }
    }
    let mut seen_columns = BTreeSet::new();
    let mut repeated_columns = 0_u64;
    for column in 0..interior {
        let values = (0..interior)
            .map(|row| bit_at(row, column))
            .collect::<Vec<_>>();
        let mut run = 0_u64;
        let mut prior = 2_u8;
        for bit in &values {
            run = if *bit == prior { run + 1 } else { 1 };
            vertical = vertical.max(run);
            prior = *bit;
        }
        if !seen_columns.insert(values) {
            repeated_columns += 1;
        }
    }
    let mut tile_min = u64::MAX;
    let mut tile_max = 0_u64;
    for tile_row in 0..interior / 32 {
        for tile_column in 0..interior / 32 {
            let mut ones = 0_u64;
            for row in tile_row * 32..tile_row * 32 + 32 {
                for column in tile_column * 32..tile_column * 32 + 32 {
                    ones += u64::from(bit_at(row, column));
                }
            }
            tile_min = tile_min.min(ones);
            tile_max = tile_max.max(ones);
        }
    }
    if tile_min == u64::MAX {
        return Err(CarrierError::Geometry);
    }
    Ok((
        scopes.to_vec(),
        [
            horizontal,
            vertical,
            tile_min,
            tile_max,
            repeated_rows,
            repeated_columns,
        ],
    ))
}

fn density_ledger(core: &ManifestationCore, carrier_sha256: &str) -> Result<(Vec<u8>, [u64; 6])> {
    let (scopes, regularity) = density_data(core)?;
    let scope_rows = scopes.into_iter().map(|row| {
        let density = if row.cells == 0 {
            0
        } else {
            row.ones * 1_000_000 / row.cells
        };
        manifest_object([
            ("scope_id", manifest_string(row.id)),
            ("cell_count", ManifestValue::U64(row.cells)),
            ("zero_count", ManifestValue::U64(row.cells - row.ones)),
            ("one_count", ManifestValue::U64(row.ones)),
            ("one_density_ppm", ManifestValue::U64(density)),
        ])
    });
    let value = manifest_object([
        (
            "schema",
            manifest_string("golden-board.m2-density-ledger/v0"),
        ),
        ("profile_id", manifest_string(core.profile.id)),
        ("carrier_sha256", manifest_string(carrier_sha256)),
        ("scope_rows", manifest_array(scope_rows)),
        (
            "interior_regularity",
            manifest_object([
                (
                    "longest_horizontal_equal_run",
                    ManifestValue::U64(regularity[0]),
                ),
                (
                    "longest_vertical_equal_run",
                    ManifestValue::U64(regularity[1]),
                ),
                ("tile_one_count_min", ManifestValue::U64(regularity[2])),
                ("tile_one_count_max", ManifestValue::U64(regularity[3])),
                ("repeated_row_count", ManifestValue::U64(regularity[4])),
                ("repeated_column_count", ManifestValue::U64(regularity[5])),
            ]),
        ),
    ]);
    Ok((
        serialize_manifest(&value).map_err(|_| CarrierError::ManifestShape)?,
        regularity,
    ))
}

fn validate_realism(
    core: &ManifestationCore,
    profile_policy_raw: &[u8],
    profile_policy_sha256: &str,
    regularity: [u64; 6],
) -> Result<()> {
    if digest(profile_policy_raw) != profile_policy_sha256 {
        return Err(CarrierError::OwnerIdentity);
    }
    let policy: toml::Value = toml::from_str(
        std::str::from_utf8(profile_policy_raw).map_err(|_| CarrierError::ManifestShape)?,
    )
    .map_err(|_| CarrierError::ManifestShape)?;
    let realism = curriculum_table(&policy, "realism")?;
    if realism
        .get("global_one_fraction_scope")
        .and_then(toml::Value::as_str)
        != Some("complete-interior")
    {
        return Err(CarrierError::ManifestShape);
    }
    let integer = |key: &str| {
        realism
            .get(key)
            .and_then(toml::Value::as_integer)
            .and_then(|value| u64::try_from(value).ok())
            .ok_or(CarrierError::ManifestShape)
    };
    let side = usize::from(core.side);
    let width = usize::from(core.shell_width);
    let mut ones = 0_u64;
    let mut cells = 0_u64;
    for row in width..side - width {
        for column in width..side - width {
            ones += u64::from(core.carrier_bits[row * side + column]);
            cells += 1;
        }
    }
    if cells != core.mapping.population {
        return Err(CarrierError::Ownership);
    }
    if ones * integer("global_one_fraction_min_denominator")?
        < cells * integer("global_one_fraction_min_numerator")?
        || ones * integer("global_one_fraction_max_denominator")?
            > cells * integer("global_one_fraction_max_numerator")?
        || regularity[2] < integer("tile_one_count_min")?
        || regularity[3] > integer("tile_one_count_max")?
    {
        return Err(CarrierError::Geometry);
    }
    let run_limit = 128_u64.max(u64::from(core.mapping.interior_side).div_ceil(4));
    let repeat_limit = 2_u64.max(u64::from(core.mapping.interior_side) / 32);
    if regularity[0] > run_limit
        || regularity[1] > run_limit
        || regularity[4] > repeat_limit
        || regularity[5] > repeat_limit
    {
        return Err(CarrierError::Geometry);
    }
    Ok(())
}

/// Apply the frozen gate-5 realism bounds to a complete manifestation. A
/// `Geometry` rejection is the ordinary candidate failure and does not reopen
/// the canonical first-fit search.
pub fn validate_manifestation_realism(
    core: &ManifestationCore,
    profile_policy_raw: &[u8],
) -> Result<()> {
    let policy =
        load_profile_policy(profile_policy_raw).map_err(|_| CarrierError::OwnerIdentity)?;
    let (_, regularity) = density_data(core)?;
    validate_realism(core, profile_policy_raw, &policy.sha256, regularity)
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ManifestationArtifacts {
    pub candidate_manifest: Vec<u8>,
    pub candidate_manifest_identity: String,
    pub ownership_ledger: Vec<u8>,
    pub capacity_ledger: Vec<u8>,
    pub density_ledger: Vec<u8>,
    pub carrier_sha256: String,
    pub ownership_sha256: String,
    pub capacity_ledger_sha256: String,
    pub density_ledger_sha256: String,
    pub realism_passes: bool,
}

/// Canonical gate-5 artifacts for the sole active R3/v7 manifestation.
///
/// The density ledger deliberately retains the inherited v0 schema.  R3
/// versions the candidate, ownership, and capacity schemas, but does not
/// version the unchanged density/realism owner.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct R3ManifestationArtifacts {
    pub candidate_manifest: Vec<u8>,
    pub candidate_manifest_identity: String,
    pub ownership_ledger: Vec<u8>,
    pub capacity_ledger: Vec<u8>,
    pub density_ledger: Vec<u8>,
    pub carrier_sha256: String,
    pub ownership_sha256: String,
    pub capacity_ledger_sha256: String,
    pub density_ledger_sha256: String,
    pub complete_interior_cells: u64,
    pub complete_interior_ones: u64,
    pub regularity: [u64; 6],
    pub realism_passes: bool,
}

/// Complete pre-damage result of independently closing automated gates 1--5.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct R3GateOneThroughFive {
    pub semantic: SemanticEnvelopeManifest,
    pub core: HierarchicalManifestationCore,
    pub artifacts: R3ManifestationArtifacts,
    pub gate_passes: [bool; 5],
    pub mandatory_physical_units: u64,
    pub lower_bound_cells: u64,
    pub clean_path_eh_decoder_invocations: u64,
    pub clean_path_repetition_candidate_groups: u64,
    pub clean_path_repetition_symbol_invocations: u64,
}

fn hierarchical_mapping_manifest(map: HierarchicalMap) -> ManifestValue {
    manifest_object([
        ("id", manifest_string("affine-slot-then-interior-v1")),
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
    ])
}

fn hierarchical_shell_rows(core: &HierarchicalManifestationCore) -> Result<Vec<ManifestValue>> {
    core.routes
        .sectors
        .iter()
        .map(|row| {
            let fixed_pad = row
                .bits
                .len()
                .checked_sub(
                    usize::try_from(row.route_prefix_cells + row.headroom_cells)
                        .map_err(|_| CarrierError::Arithmetic)?,
                )
                .ok_or(CarrierError::Ownership)?;
            Ok(manifest_object([
                ("sector_id", ManifestValue::U64(u64::from(row.sector_id))),
                (
                    "route_prefix_cells",
                    ManifestValue::U64(row.route_prefix_cells),
                ),
                ("headroom_cells", ManifestValue::U64(row.headroom_cells)),
                ("fixed_pad_cells", ManifestValue::U64(fixed_pad as u64)),
                (
                    "image_sha256",
                    manifest_string(digest(&packed_bits(&row.bits)?)),
                ),
            ]))
        })
        .collect()
}

fn hierarchical_copy_class(section: &LogicalSection) -> Result<&'static str> {
    match section.copy_count {
        5 if [1, 2, 3, 16].contains(&section.section_id) => Ok("required-spine"),
        2 if ![1, 2, 3, 16].contains(&section.section_id) => Ok("replicated-m2"),
        1 if ![1, 2, 3, 16].contains(&section.section_id) => Ok("nonreplicated-m2"),
        _ => Err(CarrierError::Ownership),
    }
}

fn hierarchical_section_rows(core: &HierarchicalManifestationCore) -> Result<Vec<ManifestValue>> {
    core.sections
        .iter()
        .map(|row| {
            let envelope = row.envelope()?;
            Ok(manifest_object([
                ("section_id", ManifestValue::U64(u64::from(row.section_id))),
                (
                    "section_type",
                    ManifestValue::U64(u64::from(row.section_type)),
                ),
                (
                    "closure_class",
                    ManifestValue::U64(u64::from(row.closure_class)),
                ),
                ("check_id", ManifestValue::U64(u64::from(row.check_id))),
                ("semantic_copy_count", ManifestValue::U64(1)),
                (
                    "physical_replica_count",
                    ManifestValue::U64(u64::from(row.copy_count)),
                ),
                ("copy_class", manifest_string(hierarchical_copy_class(row)?)),
                (
                    "dependency_ids",
                    manifest_array(
                        row.dependencies
                            .iter()
                            .map(|id| ManifestValue::U64(u64::from(*id))),
                    ),
                ),
                (
                    "logical_payload_bytes",
                    ManifestValue::U64(row.payload.len() as u64),
                ),
                ("envelope_bytes", ManifestValue::U64(envelope.len() as u64)),
                (
                    "fragment_count",
                    ManifestValue::U64(section_fragment_count(row)?),
                ),
            ]))
        })
        .collect()
}

fn hierarchical_unit_rows(core: &HierarchicalManifestationCore) -> Result<Vec<ManifestValue>> {
    core.units
        .iter()
        .map(|row| {
            let ordinal = u64::from(row.physical_unit_id)
                .checked_sub(1)
                .ok_or(CarrierError::Ownership)?;
            if row.slot != core.mapping.slot(ordinal)?
                || row.logical_bit_first != row.slot * R3_UNIT_BITS
                || row.semantic_copy_id != 0
            {
                return Err(CarrierError::Ownership);
            }
            Ok(manifest_object([
                (
                    "physical_unit_id",
                    ManifestValue::U64(u64::from(row.physical_unit_id)),
                ),
                ("section_id", ManifestValue::U64(u64::from(row.section_id))),
                ("semantic_copy_id", ManifestValue::U64(0)),
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
                ("slot", ManifestValue::U64(row.slot)),
                ("transport_id", manifest_string("eh72-hier-repetition-v0")),
                ("encoded_bytes", ManifestValue::U64(EH_UNIT_BYTES as u64)),
                ("encoded_sha256", manifest_string(digest(&row.encoded))),
                (
                    "logical_bit_first",
                    ManifestValue::U64(row.logical_bit_first),
                ),
                ("logical_bit_count", ManifestValue::U64(R3_UNIT_BITS)),
            ]))
        })
        .collect()
}

fn hierarchical_ownership_unit_rows(
    core: &HierarchicalManifestationCore,
) -> Result<Vec<ManifestValue>> {
    core.units
        .iter()
        .map(|row| {
            let ordinal = u64::from(row.physical_unit_id)
                .checked_sub(1)
                .ok_or(CarrierError::Ownership)?;
            let mut mapped = Vec::with_capacity(R3_UNIT_BITS as usize * 4);
            let mut distinct = BTreeSet::new();
            for encoded_bit in 0..R3_UNIT_BITS {
                let physical = core.mapping.forward_unit_bit(
                    ordinal,
                    u16::try_from(encoded_bit).map_err(|_| CarrierError::Arithmetic)?,
                )?;
                if !distinct.insert(physical) {
                    return Err(CarrierError::Ownership);
                }
                mapped.extend_from_slice(
                    &u32::try_from(physical)
                        .map_err(|_| CarrierError::Arithmetic)?
                        .to_be_bytes(),
                );
            }
            if distinct.len() != R3_UNIT_BITS as usize {
                return Err(CarrierError::Ownership);
            }
            Ok(manifest_object([
                (
                    "physical_unit_id",
                    ManifestValue::U64(u64::from(row.physical_unit_id)),
                ),
                ("section_id", ManifestValue::U64(u64::from(row.section_id))),
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
                ("slot", ManifestValue::U64(row.slot)),
                (
                    "logical_bit_first",
                    ManifestValue::U64(row.logical_bit_first),
                ),
                ("logical_bit_count", ManifestValue::U64(R3_UNIT_BITS)),
                ("mapped_cell_sha256", manifest_string(digest(&mapped))),
            ]))
        })
        .collect()
}

fn hierarchical_cell_table_sha256(core: &HierarchicalManifestationCore) -> String {
    let mut hasher = Sha256::new();
    for owner in &core.cell_owners {
        hasher.update([owner.kind]);
        hasher.update(owner.owner_id.to_be_bytes());
        hasher.update(owner.bit_offset.to_be_bytes());
    }
    format!("{:x}", hasher.finalize())
}

fn hierarchical_ownership_ledger(
    core: &HierarchicalManifestationCore,
    shell: &[ManifestValue],
) -> Result<Vec<u8>> {
    let value = manifest_object([
        (
            "schema",
            manifest_string("golden-board.m2-ownership-ledger/v1"),
        ),
        ("profile_id", manifest_string(core.profile.id)),
        ("side", ManifestValue::U64(u64::from(core.side))),
        (
            "shell_width",
            ManifestValue::U64(u64::from(core.shell_width)),
        ),
        ("mapping", hierarchical_mapping_manifest(core.mapping)),
        ("shell_rows", ManifestValue::Array(shell.to_vec())),
        (
            "unit_rows",
            ManifestValue::Array(hierarchical_ownership_unit_rows(core)?),
        ),
        (
            "interior_fixed_pad",
            manifest_object([
                (
                    "logical_bit_first",
                    ManifestValue::U64(core.mapping.unit_slot_count * R3_UNIT_BITS),
                ),
                (
                    "logical_bit_count",
                    ManifestValue::U64(core.interior_fixed_pad_bits.len() as u64),
                ),
                (
                    "fill_order",
                    manifest_string("unoccupied-interior-cells-in-physical-row-major-order"),
                ),
            ]),
        ),
        (
            "cell_table",
            manifest_object([
                ("row_bytes", ManifestValue::U64(9)),
                (
                    "row_count",
                    ManifestValue::U64(core.cell_owners.len() as u64),
                ),
                ("row_order", manifest_string("canonical-matrix-row-major")),
                (
                    "owner_kind_ids",
                    manifest_array([
                        manifest_string("1-shell-route"),
                        manifest_string("2-shell-headroom"),
                        manifest_string("3-shell-fixed-pad"),
                        manifest_string("4-protected-unit"),
                        manifest_string("5-interior-fixed-pad"),
                    ]),
                ),
                (
                    "owner_id_rule",
                    manifest_string(
                        "sector-id-for-shell-kinds-physical-unit-id-for-protected-unit-zero-for-interior-fixed-pad",
                    ),
                ),
                (
                    "owner_bit_offset_rule",
                    manifest_string("zero-based-offset-within-named-owner"),
                ),
            ]),
        ),
        (
            "cell_table_sha256",
            manifest_string(hierarchical_cell_table_sha256(core)),
        ),
    ]);
    serialize_manifest(&value).map_err(|_| CarrierError::ManifestShape)
}

fn hierarchical_candidate_ledger(
    core: &HierarchicalManifestationCore,
    package: &RecipePackage,
) -> Result<ManifestValue> {
    let mut owners = core
        .sections
        .iter()
        .map(|row| {
            Ok(manifest_object([
                (
                    "owner_id",
                    manifest_string(format!("section:{:010}", row.section_id)),
                ),
                (
                    "section_type",
                    ManifestValue::U64(u64::from(row.section_type)),
                ),
                (
                    "closure_class",
                    ManifestValue::U64(u64::from(row.closure_class)),
                ),
                ("semantic_copy_count", ManifestValue::U64(1)),
                (
                    "physical_replica_count",
                    ManifestValue::U64(u64::from(row.copy_count)),
                ),
                (
                    "logical_bytes",
                    ManifestValue::U64(row.payload.len() as u64),
                ),
            ]))
        })
        .collect::<Result<Vec<_>>>()?;
    owners.sort_by(|left, right| {
        text(object(left).unwrap().get("owner_id").unwrap())
            .unwrap()
            .cmp(text(object(right).unwrap().get("owner_id").unwrap()).unwrap())
    });
    let protected_unit_count = core.units.len() as u64;
    let envelope_bytes = core.sections.iter().try_fold(0_u64, |sum, row| {
        let header = 18_u64
            .checked_add(4 * row.dependencies.len() as u64)
            .ok_or(CarrierError::Arithmetic)?;
        sum.checked_add(header * u64::from(row.copy_count))
            .ok_or(CarrierError::Arithmetic)
    })?;
    let section_check_bytes = core.sections.iter().try_fold(0_u64, |sum, row| {
        sum.checked_add(4 * u64::from(row.copy_count))
            .ok_or(CarrierError::Arithmetic)
    })?;
    let physical_envelopes = core.sections.iter().try_fold(0_u64, |sum, row| {
        sum.checked_add(row.envelope()?.len() as u64 * u64::from(row.copy_count))
            .ok_or(CarrierError::Arithmetic)
    })?;
    let fragment_zero_pad_bytes = protected_unit_count
        .checked_mul(157)
        .and_then(|value| value.checked_sub(physical_envelopes))
        .ok_or(CarrierError::Arithmetic)?;
    let shell_count = |owner: ShellOwner| -> u64 {
        core.routes
            .sectors
            .iter()
            .flat_map(|row| &row.spans)
            .filter(|row| row.owner == owner)
            .map(|row| row.cell_count)
            .sum()
    };
    let section_types = core
        .sections
        .iter()
        .map(|row| (row.section_id, row.section_type))
        .collect::<BTreeMap<_, _>>();
    let mut interior_counts = [0_u64; 7];
    for unit in &core.units {
        interior_counts[usize::from(section_types[&unit.section_id])] += R3_UNIT_BITS;
    }
    let real_protected = interior_counts[usize::from(SECTION_INVENTORY)]
        + interior_counts[usize::from(SECTION_TIER_FRAME)]
        + interior_counts[usize::from(SECTION_CONTENT_BODY)];
    let decoder_steps = package
        .recipe_primitive_steps(30)
        .ok_or(CarrierError::Recipe)?;
    let repetition_steps = package
        .recipe_primitive_steps(113)
        .ok_or(CarrierError::Recipe)?;
    let repeated_group_count = core.sections.iter().try_fold(0_u64, |sum, row| {
        if row.copy_count > 1 {
            sum.checked_add(section_fragment_count(row)?)
                .ok_or(CarrierError::Arithmetic)
        } else {
            Ok(sum)
        }
    })?;
    let lane_work = protected_unit_count
        .checked_mul(24)
        .and_then(|value| value.checked_mul(decoder_steps))
        .ok_or(CarrierError::Arithmetic)?;
    let repetition_work_per_group = 24_u64
        .checked_mul(decoder_steps)
        .and_then(|value| value.checked_add(R3_UNIT_BITS * repetition_steps))
        .ok_or(CarrierError::Arithmetic)?;
    let worst_case_work_units = lane_work
        .checked_add(
            repeated_group_count
                .checked_mul(repetition_work_per_group)
                .ok_or(CarrierError::Arithmetic)?,
        )
        .ok_or(CarrierError::Arithmetic)?;
    let values = [
        ("envelope_bytes", envelope_bytes),
        ("fragment_header_bytes", 30 * protected_unit_count),
        ("fragment_zero_pad_bytes", fragment_zero_pad_bytes),
        ("local_check_bytes", 4 * protected_unit_count),
        ("section_check_bytes", section_check_bytes),
        ("transport_pad_bytes", protected_unit_count),
        ("parity_bytes", 24 * protected_unit_count),
        (
            "shell_instruction_cells",
            shell_count(ShellOwner::Instruction),
        ),
        ("shell_example_cells", shell_count(ShellOwner::Example)),
        ("shell_recipe_cells", shell_count(ShellOwner::Recipe)),
        ("shell_headroom_cells", shell_count(ShellOwner::Headroom)),
        ("shell_fixed_pad_cells", shell_count(ShellOwner::FixedPad)),
        ("real_protected_cells", real_protected),
        (
            "capacity_probe_cells",
            interior_counts[usize::from(SECTION_CAPACITY_PROBE)],
        ),
        (
            "reserve_probe_cells",
            interior_counts[usize::from(SECTION_RESERVE_PROBE)],
        ),
        (
            "load_probe_cells",
            interior_counts[usize::from(SECTION_LOAD_PROBE)],
        ),
        (
            "interior_fixed_pad_cells",
            core.interior_fixed_pad_bits.len() as u64,
        ),
        ("protected_unit_count", protected_unit_count),
        ("codeword_count", protected_unit_count * 24),
        ("worst_case_section_attempts", 1),
        ("worst_case_work_units", worst_case_work_units),
        ("scratch_bytes", package.peak_scratch_bytes),
        ("unused_cells", 0),
        ("total_cells", core.carrier_bits.len() as u64),
    ];
    let mut object = BTreeMap::new();
    object.insert(
        "logical_bytes_by_owner".to_owned(),
        ManifestValue::Array(owners),
    );
    for (key, value) in values {
        object.insert(key.to_owned(), ManifestValue::U64(value));
    }
    let shell_cells = shell_count(ShellOwner::Instruction)
        + shell_count(ShellOwner::Example)
        + shell_count(ShellOwner::Recipe)
        + shell_count(ShellOwner::Headroom)
        + shell_count(ShellOwner::FixedPad);
    if shell_cells
        + real_protected
        + interior_counts[usize::from(SECTION_CAPACITY_PROBE)]
        + interior_counts[usize::from(SECTION_RESERVE_PROBE)]
        + interior_counts[usize::from(SECTION_LOAD_PROBE)]
        + core.interior_fixed_pad_bits.len() as u64
        != core.carrier_bits.len() as u64
    {
        return Err(CarrierError::Ownership);
    }
    let physical_payload = core.sections.iter().try_fold(0_u64, |sum, row| {
        sum.checked_add(row.payload.len() as u64 * u64::from(row.copy_count))
            .ok_or(CarrierError::Arithmetic)
    })?;
    if envelope_bytes
        + physical_payload
        + section_check_bytes
        + fragment_zero_pad_bytes
        + 30 * protected_unit_count
        + 4 * protected_unit_count
        + protected_unit_count
        + 24 * protected_unit_count
        != protected_unit_count * EH_UNIT_BYTES as u64
    {
        return Err(CarrierError::Ownership);
    }
    Ok(ManifestValue::Object(object))
}

fn hierarchical_density_data(
    core: &HierarchicalManifestationCore,
) -> Result<(Vec<DensityScope>, [u64; 6])> {
    let side = usize::from(core.side);
    let width = usize::from(core.shell_width);
    let unit_types = core
        .units
        .iter()
        .map(|unit| {
            let section_type = core
                .sections
                .iter()
                .find(|row| row.section_id == unit.section_id)
                .map(|row| row.section_type)
                .ok_or(CarrierError::Ownership)?;
            Ok((unit.physical_unit_id, section_type))
        })
        .collect::<Result<BTreeMap<_, _>>>()?;
    let ids = [
        "shell",
        "real-protected",
        "capacity-probe",
        "reserve-probe",
        "load-probe",
        "fixed-pad",
        "complete-interior",
    ];
    let mut scopes = ids.map(|id| DensityScope {
        id,
        cells: 0,
        ones: 0,
    });
    for (flat, bit) in core.carrier_bits.iter().copied().enumerate() {
        let row = flat / side;
        let column = flat % side;
        let owner = core.cell_owners[flat];
        let mut add = |index: usize| {
            scopes[index].cells += 1;
            scopes[index].ones += u64::from(bit);
        };
        if owner.kind <= 3 {
            add(0);
        }
        if owner.kind == 4 {
            match unit_types[&owner.owner_id] {
                SECTION_INVENTORY | SECTION_TIER_FRAME | SECTION_CONTENT_BODY => add(1),
                SECTION_CAPACITY_PROBE => add(2),
                SECTION_RESERVE_PROBE => add(3),
                SECTION_LOAD_PROBE => add(4),
                _ => return Err(CarrierError::Ownership),
            }
        }
        if matches!(owner.kind, 3 | 5) {
            add(5);
        }
        if row >= width && row < side - width && column >= width && column < side - width {
            add(6);
        }
    }
    if scopes.iter().any(|row| row.ones > row.cells) {
        return Err(CarrierError::Ownership);
    }
    let interior = usize::from(core.mapping.interior_side);
    let bit_at =
        |row: usize, column: usize| core.carrier_bits[(row + width) * side + column + width];
    let mut horizontal = 0_u64;
    let mut vertical = 0_u64;
    let mut seen_rows = BTreeSet::new();
    let mut repeated_rows = 0_u64;
    for row in 0..interior {
        let values = (0..interior)
            .map(|column| bit_at(row, column))
            .collect::<Vec<_>>();
        let mut run = 0_u64;
        let mut prior = 2_u8;
        for bit in &values {
            run = if *bit == prior { run + 1 } else { 1 };
            horizontal = horizontal.max(run);
            prior = *bit;
        }
        if !seen_rows.insert(values) {
            repeated_rows += 1;
        }
    }
    let mut seen_columns = BTreeSet::new();
    let mut repeated_columns = 0_u64;
    for column in 0..interior {
        let values = (0..interior)
            .map(|row| bit_at(row, column))
            .collect::<Vec<_>>();
        let mut run = 0_u64;
        let mut prior = 2_u8;
        for bit in &values {
            run = if *bit == prior { run + 1 } else { 1 };
            vertical = vertical.max(run);
            prior = *bit;
        }
        if !seen_columns.insert(values) {
            repeated_columns += 1;
        }
    }
    let mut tile_min = u64::MAX;
    let mut tile_max = 0_u64;
    for tile_row in 0..interior / 32 {
        for tile_column in 0..interior / 32 {
            let mut ones = 0_u64;
            for row in tile_row * 32..tile_row * 32 + 32 {
                for column in tile_column * 32..tile_column * 32 + 32 {
                    ones += u64::from(bit_at(row, column));
                }
            }
            tile_min = tile_min.min(ones);
            tile_max = tile_max.max(ones);
        }
    }
    if tile_min == u64::MAX {
        return Err(CarrierError::Geometry);
    }
    Ok((
        scopes.to_vec(),
        [
            horizontal,
            vertical,
            tile_min,
            tile_max,
            repeated_rows,
            repeated_columns,
        ],
    ))
}

fn hierarchical_density_ledger(
    core: &HierarchicalManifestationCore,
    carrier_sha256: &str,
) -> Result<(Vec<u8>, Vec<DensityScope>, [u64; 6])> {
    let (scopes, regularity) = hierarchical_density_data(core)?;
    let scope_rows = scopes.iter().map(|row| {
        let density = if row.cells == 0 {
            0
        } else {
            row.ones * 1_000_000 / row.cells
        };
        manifest_object([
            ("scope_id", manifest_string(row.id)),
            ("cell_count", ManifestValue::U64(row.cells)),
            ("zero_count", ManifestValue::U64(row.cells - row.ones)),
            ("one_count", ManifestValue::U64(row.ones)),
            ("one_density_ppm", ManifestValue::U64(density)),
        ])
    });
    let value = manifest_object([
        (
            "schema",
            // profile-policy-v1 inherits this unchanged owner from v0.
            manifest_string("golden-board.m2-density-ledger/v0"),
        ),
        ("profile_id", manifest_string(core.profile.id)),
        ("carrier_sha256", manifest_string(carrier_sha256)),
        ("scope_rows", manifest_array(scope_rows)),
        (
            "interior_regularity",
            manifest_object([
                (
                    "longest_horizontal_equal_run",
                    ManifestValue::U64(regularity[0]),
                ),
                (
                    "longest_vertical_equal_run",
                    ManifestValue::U64(regularity[1]),
                ),
                ("tile_one_count_min", ManifestValue::U64(regularity[2])),
                ("tile_one_count_max", ManifestValue::U64(regularity[3])),
                ("repeated_row_count", ManifestValue::U64(regularity[4])),
                ("repeated_column_count", ManifestValue::U64(regularity[5])),
            ]),
        ),
    ]);
    Ok((
        serialize_manifest(&value).map_err(|_| CarrierError::ManifestShape)?,
        scopes,
        regularity,
    ))
}

fn validate_hierarchical_realism(
    core: &HierarchicalManifestationCore,
    inherited_policy_raw: &[u8],
    regularity: [u64; 6],
) -> Result<()> {
    let policy =
        load_profile_policy(inherited_policy_raw).map_err(|_| CarrierError::OwnerIdentity)?;
    if digest(inherited_policy_raw) != policy.sha256 {
        return Err(CarrierError::OwnerIdentity);
    }
    let document: toml::Value = toml::from_str(
        std::str::from_utf8(inherited_policy_raw).map_err(|_| CarrierError::ManifestShape)?,
    )
    .map_err(|_| CarrierError::ManifestShape)?;
    let realism = curriculum_table(&document, "realism")?;
    if realism
        .get("global_one_fraction_scope")
        .and_then(toml::Value::as_str)
        != Some("complete-interior")
    {
        return Err(CarrierError::ManifestShape);
    }
    let integer = |key: &str| {
        realism
            .get(key)
            .and_then(toml::Value::as_integer)
            .and_then(|value| u64::try_from(value).ok())
            .ok_or(CarrierError::ManifestShape)
    };
    let side = usize::from(core.side);
    let width = usize::from(core.shell_width);
    let mut ones = 0_u64;
    let mut cells = 0_u64;
    for row in width..side - width {
        for column in width..side - width {
            ones += u64::from(core.carrier_bits[row * side + column]);
            cells += 1;
        }
    }
    if cells != core.mapping.population
        || ones * integer("global_one_fraction_min_denominator")?
            < cells * integer("global_one_fraction_min_numerator")?
        || ones * integer("global_one_fraction_max_denominator")?
            > cells * integer("global_one_fraction_max_numerator")?
        || regularity[2] < integer("tile_one_count_min")?
        || regularity[3] > integer("tile_one_count_max")?
    {
        return Err(CarrierError::Geometry);
    }
    let run_limit = 128_u64.max(u64::from(core.mapping.interior_side).div_ceil(4));
    let repeat_limit = 2_u64.max(u64::from(core.mapping.interior_side) / 32);
    if regularity[0] > run_limit
        || regularity[1] > run_limit
        || regularity[4] > repeat_limit
        || regularity[5] > repeat_limit
    {
        return Err(CarrierError::Geometry);
    }
    Ok(())
}

fn r3_limit_u64(document: &toml::Value, table: &str, key: &str) -> Result<u64> {
    document
        .get(table)
        .and_then(toml::Value::as_table)
        .and_then(|row| row.get(key))
        .and_then(toml::Value::as_integer)
        .and_then(|value| u64::try_from(value).ok())
        .ok_or(CarrierError::ManifestShape)
}

fn r3_limit_u64_array(document: &toml::Value, table: &str, key: &str) -> Result<Vec<u64>> {
    document
        .get(table)
        .and_then(toml::Value::as_table)
        .and_then(|row| row.get(key))
        .and_then(toml::Value::as_array)
        .ok_or(CarrierError::ManifestShape)?
        .iter()
        .map(|value| {
            value
                .as_integer()
                .and_then(|value| u64::try_from(value).ok())
                .ok_or(CarrierError::ManifestShape)
        })
        .collect()
}

fn validate_r3_core_against_limits(
    core: &HierarchicalManifestationCore,
    semantic: &SemanticEnvelopeManifest,
    route_owner: &R3RouteOwnerGeneration,
    profile_limits_raw: &[u8],
) -> Result<(u64, u64, u64, u64)> {
    let limits: toml::Value = toml::from_str(
        std::str::from_utf8(profile_limits_raw).map_err(|_| CarrierError::ManifestShape)?,
    )
    .map_err(|_| CarrierError::ManifestShape)?;
    let projection = hierarchical_capacity_projection(
        core.side,
        core.shell_width,
        semantic,
        r3_limit_u64(&limits, "semantic_capacity", "reserve_payload_bytes")?,
        MAXIMUM_PROBE_PAYLOAD,
    )?;
    let section_envelopes = core
        .sections
        .iter()
        .map(LogicalSection::envelope)
        .collect::<Result<Vec<_>>>()?;
    let maximum_envelope = section_envelopes
        .iter()
        .map(|raw| raw.len() as u64)
        .max()
        .ok_or(CarrierError::Section)?;
    let maximum_fragments = core
        .sections
        .iter()
        .map(section_fragment_count)
        .collect::<Result<Vec<_>>>()?
        .into_iter()
        .max()
        .ok_or(CarrierError::Section)?;
    let dependency_edges = core
        .sections
        .iter()
        .map(|row| row.dependencies.len() as u64)
        .sum::<u64>();
    let mandatory_physical_units = core
        .sections
        .iter()
        .filter(|row| row.section_type != SECTION_LOAD_PROBE)
        .try_fold(0_u64, |sum, row| {
            sum.checked_add(section_fragment_count(row)? * u64::from(row.copy_count))
                .ok_or(CarrierError::Arithmetic)
        })?;
    let repeated_groups = projection
        .factor_2_group_count
        .checked_add(projection.factor_5_group_count)
        .ok_or(CarrierError::Arithmetic)?;
    let clean_eh_invocations = projection
        .protected_unit_count
        .checked_add(repeated_groups)
        .and_then(|value| value.checked_mul(24))
        .ok_or(CarrierError::Arithmetic)?;
    let repetition_symbols = repeated_groups
        .checked_mul(R3_UNIT_BITS)
        .ok_or(CarrierError::Arithmetic)?;
    let lower_bound_cells = mandatory_physical_units
        .checked_mul(R3_UNIT_BITS)
        .and_then(|value| {
            value.checked_add(
                core.routes
                    .sectors
                    .iter()
                    .map(|row| row.route_prefix_cells)
                    .sum(),
            )
        })
        .ok_or(CarrierError::Arithmetic)?;
    let selected_checks = [
        ("carrier_bytes", core.carrier_bits.len() as u64 / 8),
        (
            "cell_inverse_multiplier",
            core.mapping.inverse_cell_multiplier,
        ),
        ("cell_multiplier", core.mapping.cell_multiplier),
        ("cell_offset", core.mapping.cell_offset),
        ("cells", core.carrier_bits.len() as u64),
        ("dependency_edges", dependency_edges),
        (
            "encoded_transport_bytes",
            projection.protected_unit_count * EH_UNIT_BYTES as u64,
        ),
        ("factor_1_group_count", projection.factor_1_group_count),
        ("factor_2_group_count", projection.factor_2_group_count),
        ("factor_5_group_count", projection.factor_5_group_count),
        ("fixed_pad_cells", projection.fixed_pad_cells),
        ("interior_side", u64::from(core.mapping.interior_side)),
        ("inventory_dependency_count", dependency_edges),
        ("inventory_entry_count", core.sections.len() as u64),
        (
            "inventory_fragment_count",
            projection.inventory_fragment_count,
        ),
        (
            "inventory_payload_bytes",
            projection.inventory_payload_bytes,
        ),
        ("logical_group_count", projection.logical_group_count),
        ("mandatory_physical_unit_count", mandatory_physical_units),
        ("maximum_fragments_per_section", maximum_fragments),
        ("maximum_section_envelope_bytes", maximum_envelope),
        ("physical_unit_count", projection.protected_unit_count),
        ("population", core.mapping.population),
        ("protected_cells", projection.protected_cells),
        (
            "sector_capacity_bytes",
            u64::from(core.shell_width) * u64::from(core.side - core.shell_width) / 8,
        ),
        ("semantic_copy_count", 1),
        ("separation_window", u64::from(core.mapping.window_side)),
        ("shell_width", u64::from(core.shell_width)),
        ("side", u64::from(core.side)),
        (
            "slot_inverse_multiplier",
            core.mapping.inverse_slot_multiplier,
        ),
        ("slot_multiplier", core.mapping.slot_multiplier),
    ];
    if selected_checks
        .iter()
        .any(|(key, value)| r3_limit_u64(&limits, "selected_manifestation", key) != Ok(*value))
        || r3_limit_u64_array(&limits, "selected_manifestation", "load_fragment_counts")?
            != projection.load_fragment_counts
        || r3_limit_u64_array(&limits, "selected_manifestation", "load_payload_bytes")?
            != projection.load_payload_bytes
        || r3_limit_u64(&limits, "transport", "clean_path_eh_decoder_invocations")?
            != clean_eh_invocations
        || r3_limit_u64(
            &limits,
            "transport",
            "clean_path_repetition_candidate_groups",
        )? != repeated_groups
        || r3_limit_u64(
            &limits,
            "transport",
            "clean_path_repetition_symbol_invocations",
        )? != repetition_symbols
        || route_owner.draft.side != core.side
        || route_owner.draft.shell_width != core.shell_width
        || route_owner.draft.route_images != core.routes
        || route_owner.draft.mapping != core.mapping
        || route_owner.draft.logical_group_count != projection.logical_group_count
        || route_owner.draft.factor_1_group_count != projection.factor_1_group_count
        || route_owner.draft.factor_2_group_count != projection.factor_2_group_count
        || route_owner.draft.factor_5_group_count != projection.factor_5_group_count
        || route_owner.draft.load_fragment_counts != projection.load_fragment_counts
        || route_owner.draft.load_payload_bytes != projection.load_payload_bytes
    {
        return Err(CarrierError::OwnerIdentity);
    }
    Ok((
        mandatory_physical_units,
        lower_bound_cells,
        clean_eh_invocations,
        repetition_symbols,
    ))
}

fn render_r3_manifestation_artifacts(
    core: &HierarchicalManifestationCore,
    semantic: &SemanticEnvelopeManifest,
    profile_policy_raw: &[u8],
    profile_limits_raw: &[u8],
    bootstrap_spec_raw: &[u8],
    route_data_raw: &[u8],
    recipient_package_raw: &[u8],
) -> Result<R3ManifestationArtifacts> {
    let package =
        decode_recipe_package(recipient_package_raw, 7).map_err(|_| CarrierError::Recipe)?;
    let profile_policy_sha256 = digest(profile_policy_raw);
    let profile_limits_sha256 = digest(profile_limits_raw);
    let bootstrap_spec_sha256 = digest(bootstrap_spec_raw);
    let route_data_sha256 = digest(route_data_raw);
    let recipient_package_sha256 = digest(recipient_package_raw);
    let carrier_sha256 = digest(&core.carrier_bytes);
    let shell = hierarchical_shell_rows(core)?;
    let sections = hierarchical_section_rows(core)?;
    let units = hierarchical_unit_rows(core)?;
    let ledger = hierarchical_candidate_ledger(core, &package)?;
    let ownership_ledger = hierarchical_ownership_ledger(core, &shell)?;
    let ownership_sha256 = digest(&ownership_ledger);
    let capacity_value = manifest_object([
        (
            "schema",
            manifest_string("golden-board.m2-capacity-ledger/v1"),
        ),
        ("profile_id", manifest_string(core.profile.id)),
        ("carrier_sha256", manifest_string(&carrier_sha256)),
        ("section_rows", ManifestValue::Array(sections.clone())),
        ("unit_rows", ManifestValue::Array(units.clone())),
        ("ledger", ledger.clone()),
    ]);
    let capacity_ledger =
        serialize_manifest(&capacity_value).map_err(|_| CarrierError::ManifestShape)?;
    let capacity_ledger_sha256 = digest(&capacity_ledger);
    let (density_ledger, scopes, regularity) = hierarchical_density_ledger(core, &carrier_sha256)?;
    let density_ledger_sha256 = digest(&density_ledger);
    let inherited_policy_raw = include_bytes!("../../../spec/profile-policy-v0.toml");
    let realism_passes = match validate_hierarchical_realism(core, inherited_policy_raw, regularity)
    {
        Ok(()) => true,
        Err(CarrierError::Geometry) => false,
        Err(error) => return Err(error),
    };
    let complete = scopes
        .iter()
        .find(|row| row.id == "complete-interior")
        .ok_or(CarrierError::Ownership)?;
    let base_fields = [
        (
            "schema",
            manifest_string("golden-board.m2-candidate-manifest/v1"),
        ),
        (
            "profile_policy_sha256",
            manifest_string(&profile_policy_sha256),
        ),
        (
            "profile_limits_sha256",
            manifest_string(&profile_limits_sha256),
        ),
        (
            "bootstrap_spec_sha256",
            manifest_string(&bootstrap_spec_sha256),
        ),
        ("route_data_sha256", manifest_string(&route_data_sha256)),
        (
            "recipient_package_sha256",
            manifest_string(&recipient_package_sha256),
        ),
        ("profile_id", manifest_string(core.profile.id)),
        ("profile_version", ManifestValue::U64(7)),
        (
            "semantic_envelope_sha256",
            manifest_string(semantic.sha256()),
        ),
        ("side", ManifestValue::U64(u64::from(core.side))),
        (
            "shell_width",
            ManifestValue::U64(u64::from(core.shell_width)),
        ),
        ("mapping", hierarchical_mapping_manifest(core.mapping)),
        ("shell_rows", ManifestValue::Array(shell)),
        ("section_rows", ManifestValue::Array(sections)),
        ("unit_rows", ManifestValue::Array(units)),
        ("ownership_sha256", manifest_string(&ownership_sha256)),
        (
            "capacity_ledger_sha256",
            manifest_string(&capacity_ledger_sha256),
        ),
        (
            "density_ledger_sha256",
            manifest_string(&density_ledger_sha256),
        ),
        ("carrier_sha256", manifest_string(&carrier_sha256)),
        ("ledger", ledger),
    ];
    let without_identity = manifest_object(base_fields);
    let without_identity_bytes =
        serialize_manifest(&without_identity).map_err(|_| CarrierError::ManifestShape)?;
    let candidate_manifest_identity =
        identity_hex(b"golden-board:manifest:v0\0", &[&without_identity_bytes])
            .map_err(|_| CarrierError::ManifestShape)?;
    let mut with_identity = object(&without_identity)?.clone();
    with_identity.insert(
        "manifest_identity".to_owned(),
        manifest_string(&candidate_manifest_identity),
    );
    let candidate_manifest = serialize_manifest(&ManifestValue::Object(with_identity))
        .map_err(|_| CarrierError::ManifestShape)?;
    for raw in [
        candidate_manifest.as_slice(),
        ownership_ledger.as_slice(),
        capacity_ledger.as_slice(),
        density_ledger.as_slice(),
    ] {
        validate_canonical_manifest(raw).map_err(|_| CarrierError::ManifestShape)?;
    }
    Ok(R3ManifestationArtifacts {
        candidate_manifest,
        candidate_manifest_identity,
        ownership_ledger,
        capacity_ledger,
        density_ledger,
        carrier_sha256,
        ownership_sha256,
        capacity_ledger_sha256,
        density_ledger_sha256,
        complete_interior_cells: complete.cells,
        complete_interior_ones: complete.ones,
        regularity,
        realism_passes,
    })
}

/// Strictly admit all promoted v1 owners, then and only then construct the
/// complete v7 carrier and its gate-5 artifacts.  This path never realizes a
/// D0--D7 operator or invokes the observation decoder.
#[allow(clippy::too_many_arguments)]
pub fn build_r3_gate_one_through_five(
    bootstrap_spec_raw: &[u8],
    profile_policy_raw: &[u8],
    damage_policy_raw: &[u8],
    route_data_raw: &[u8],
    profile_limits_raw: &[u8],
    promotion_manifest_raw: &[u8],
    owner_fixture_raw: &[u8],
    compiled: &SliceCompilation,
    curriculum_raw: &[u8],
) -> Result<R3GateOneThroughFive> {
    let owners = admit_r3_promoted_owner_bundle(
        bootstrap_spec_raw,
        profile_policy_raw,
        damage_policy_raw,
        route_data_raw,
        profile_limits_raw,
        promotion_manifest_raw,
        owner_fixture_raw,
        compiled,
        curriculum_raw,
    )
    .map_err(|_| CarrierError::OwnerIdentity)?;
    let inherited_policy_raw = include_bytes!("../../../spec/profile-policy-v0.toml");
    let inherited_policy =
        load_profile_policy(inherited_policy_raw).map_err(|_| CarrierError::OwnerIdentity)?;
    let semantic = render_semantic_envelope(
        &inherited_policy,
        inherited_policy_raw,
        compiled,
        curriculum_raw,
    )?;
    let profile_document: toml::Value = toml::from_str(
        std::str::from_utf8(profile_policy_raw).map_err(|_| CarrierError::ManifestShape)?,
    )
    .map_err(|_| CarrierError::ManifestShape)?;
    if profile_document
        .get("bindings")
        .and_then(toml::Value::as_table)
        .and_then(|row| row.get("semantic_envelope_sha256"))
        .and_then(toml::Value::as_str)
        != Some(semantic.sha256())
    {
        return Err(CarrierError::OwnerIdentity);
    }
    let package = decode_recipe_package(&owners.route.draft.recipient_package, 7)
        .map_err(|_| CarrierError::Recipe)?;
    let package_metrics = r3_recipe_package_metrics().map_err(|_| CarrierError::Recipe)?;
    let resource_rows = r3_recipe_resource_rows().map_err(|_| CarrierError::Recipe)?;
    if package.profile_version != 7
        || package.recipe_ids().count() != 22
        || resource_rows
            .iter()
            .map(|row| row.recipe_id)
            .collect::<Vec<_>>()
            != [30_u16, 109, 110, 113]
        || package_metrics.package_bytes as usize != owners.route.draft.recipient_package.len()
        || package_metrics.package_sha256 != owners.route.draft.recipient_package_sha256
    {
        return Err(CarrierError::Recipe);
    }
    for sector in 0..4 {
        admit_r3_route_prefix(
            &owners.route.draft.route_prefixes[sector],
            sector,
            &owners.route,
        )?;
    }
    let core = build_hierarchical_manifestation_core_at(
        owners.route.draft.side,
        owners.route.draft.shell_width,
        owners.route.draft.route_images.clone(),
        &semantic,
        RESERVE_PAYLOAD_BYTES,
        MAXIMUM_PROBE_PAYLOAD,
    )?;
    validate_clean_hierarchical_reconstruction(&core, compiled)?;
    let (
        mandatory_physical_units,
        lower_bound_cells,
        clean_path_eh_decoder_invocations,
        clean_path_repetition_symbol_invocations,
    ) = validate_r3_core_against_limits(&core, &semantic, &owners.route, profile_limits_raw)?;
    let clean_path_repetition_candidate_groups = core
        .sections
        .iter()
        .filter(|row| row.copy_count > 1)
        .try_fold(0_u64, |sum, row| {
            sum.checked_add(section_fragment_count(row)?)
                .ok_or(CarrierError::Arithmetic)
        })?;
    if mandatory_physical_units != 1_465
        || lower_bound_cells > RAW_BITS_MAX as u64
        || core.carrier_bits.len() > RAW_BITS_MAX
        || core.carrier_bytes.len() != core.carrier_bits.len().div_ceil(8) + 4
    {
        return Err(CarrierError::Geometry);
    }
    let artifacts = render_r3_manifestation_artifacts(
        &core,
        &semantic,
        profile_policy_raw,
        profile_limits_raw,
        bootstrap_spec_raw,
        route_data_raw,
        &owners.route.draft.recipient_package,
    )?;
    Ok(R3GateOneThroughFive {
        semantic,
        core,
        gate_passes: [true, true, true, true, artifacts.realism_passes],
        artifacts,
        mandatory_physical_units,
        lower_bound_cells,
        clean_path_eh_decoder_invocations,
        clean_path_repetition_candidate_groups,
        clean_path_repetition_symbol_invocations,
    })
}

/// Rebuild and byte-compare the complete v7 gates-1--5 output.  No field in a
/// supplied candidate artifact is trusted as an input to regeneration.
#[allow(clippy::too_many_arguments)]
pub fn validate_r3_gate_one_through_five(
    expected: &R3GateOneThroughFive,
    bootstrap_spec_raw: &[u8],
    profile_policy_raw: &[u8],
    damage_policy_raw: &[u8],
    route_data_raw: &[u8],
    profile_limits_raw: &[u8],
    promotion_manifest_raw: &[u8],
    owner_fixture_raw: &[u8],
    compiled: &SliceCompilation,
    curriculum_raw: &[u8],
) -> Result<()> {
    let rebuilt = build_r3_gate_one_through_five(
        bootstrap_spec_raw,
        profile_policy_raw,
        damage_policy_raw,
        route_data_raw,
        profile_limits_raw,
        promotion_manifest_raw,
        owner_fixture_raw,
        compiled,
        curriculum_raw,
    )?;
    if &rebuilt != expected {
        return Err(CarrierError::OwnerIdentity);
    }
    Ok(())
}

/// Strictly admit the six retained manifestation byte strings plus their
/// semantic preimage by regenerating them from the promoted raw owner bundle.
/// This is the file-oriented counterpart to
/// [`validate_r3_gate_one_through_five`].
#[allow(clippy::too_many_arguments)]
pub fn admit_r3_gate_one_through_five_artifacts(
    semantic_envelope_raw: &[u8],
    carrier_raw: &[u8],
    candidate_manifest_raw: &[u8],
    ownership_ledger_raw: &[u8],
    capacity_ledger_raw: &[u8],
    density_ledger_raw: &[u8],
    bootstrap_spec_raw: &[u8],
    profile_policy_raw: &[u8],
    damage_policy_raw: &[u8],
    route_data_raw: &[u8],
    profile_limits_raw: &[u8],
    promotion_manifest_raw: &[u8],
    owner_fixture_raw: &[u8],
    compiled: &SliceCompilation,
    curriculum_raw: &[u8],
) -> Result<R3GateOneThroughFive> {
    let rebuilt = build_r3_gate_one_through_five(
        bootstrap_spec_raw,
        profile_policy_raw,
        damage_policy_raw,
        route_data_raw,
        profile_limits_raw,
        promotion_manifest_raw,
        owner_fixture_raw,
        compiled,
        curriculum_raw,
    )?;
    compare_r3_gate_artifact_bytes(
        &rebuilt,
        semantic_envelope_raw,
        carrier_raw,
        candidate_manifest_raw,
        ownership_ledger_raw,
        capacity_ledger_raw,
        density_ledger_raw,
    )?;
    Ok(rebuilt)
}

#[allow(clippy::too_many_arguments)]
fn compare_r3_gate_artifact_bytes(
    rebuilt: &R3GateOneThroughFive,
    semantic_envelope_raw: &[u8],
    carrier_raw: &[u8],
    candidate_manifest_raw: &[u8],
    ownership_ledger_raw: &[u8],
    capacity_ledger_raw: &[u8],
    density_ledger_raw: &[u8],
) -> Result<()> {
    if semantic_envelope_raw != rebuilt.semantic.canonical_bytes()
        || carrier_raw != rebuilt.core.carrier_bytes
        || candidate_manifest_raw != rebuilt.artifacts.candidate_manifest
        || ownership_ledger_raw != rebuilt.artifacts.ownership_ledger
        || capacity_ledger_raw != rebuilt.artifacts.capacity_ledger
        || density_ledger_raw != rebuilt.artifacts.density_ledger
    {
        return Err(CarrierError::OwnerIdentity);
    }
    Ok(())
}

/// Render every canonical P6 artifact for a complete CRC32C/EH manifestation.
pub fn render_manifestation_artifacts(
    core: &ManifestationCore,
    semantic: &SemanticEnvelopeManifest,
    compiled: &SliceCompilation,
    profile_policy_raw: &[u8],
    damage_policy_raw: &[u8],
    profile_limits_raw: &[u8],
    bootstrap_spec_raw: &[u8],
    curriculum_raw: &[u8],
    route_manifest_raw: &[u8],
    recipe_package_raw: &[u8],
) -> Result<ManifestationArtifacts> {
    if !matches!(core.profile.version, 1 | 3)
        || bootstrap_spec_raw.len() > OWNER_DOCUMENT_BYTES_MAX
        || curriculum_raw.len() > OWNER_DOCUMENT_BYTES_MAX
    {
        return Err(CarrierError::Parameter);
    }
    let policy =
        load_profile_policy(profile_policy_raw).map_err(|_| CarrierError::OwnerIdentity)?;
    let damage = load_damage_policy(damage_policy_raw).map_err(|_| CarrierError::OwnerIdentity)?;
    let limits = load_profile_limits(
        profile_limits_raw,
        &policy,
        &damage,
        compiled,
        curriculum_raw,
    )
    .map_err(|_| CarrierError::OwnerIdentity)?;
    let bootstrap_binding = limits
        .get("bootstrap_spec_sha256")
        .and_then(toml::Value::as_str)
        .ok_or(CarrierError::ManifestShape)?;
    if digest(bootstrap_spec_raw) != bootstrap_binding {
        return Err(CarrierError::OwnerIdentity);
    }
    let owner_semantic =
        render_semantic_envelope(&policy, profile_policy_raw, compiled, curriculum_raw)?;
    if &owner_semantic != semantic || core.semantic_envelope_sha256 != semantic.sha256 {
        return Err(CarrierError::OwnerIdentity);
    }
    let reserve_payload_bytes = limits
        .get("semantic_capacity")
        .and_then(toml::Value::as_table)
        .and_then(|table| table.get("reserve_payload_bytes"))
        .and_then(toml::Value::as_integer)
        .and_then(|value| u64::try_from(value).ok())
        .ok_or(CarrierError::ManifestShape)?;
    if reserve_payload_bytes != RESERVE_PAYLOAD_BYTES
        || policy.maximum_probe_payload != MAXIMUM_PROBE_PAYLOAD
    {
        return Err(CarrierError::OwnerIdentity);
    }
    let owner_core = build_manifestation_core(
        core.profile.version,
        route_manifest_raw,
        recipe_package_raw,
        semantic,
        reserve_payload_bytes,
        policy.maximum_probe_payload,
    )?;
    if &owner_core != core {
        return Err(CarrierError::OwnerIdentity);
    }
    validate_clean_reconstruction(core, compiled)?;
    let package = decode_recipe_package(recipe_package_raw, core.profile.version)
        .map_err(|_| CarrierError::Recipe)?;
    let profile_policy_sha256 = digest(profile_policy_raw);
    let profile_limits_sha256 = digest(profile_limits_raw);
    let bootstrap_spec_sha256 = digest(bootstrap_spec_raw);
    let carrier_sha256 = digest(&core.carrier_bytes);
    let shell = shell_rows(core)?;
    let sections = section_rows(core)?;
    let units = unit_rows(core);
    let ledger = candidate_ledger(core, &package)?;
    let ownership_ledger = ownership_ledger(core, &shell, &units)?;
    let ownership_sha256 = digest(&ownership_ledger);
    let capacity_value = manifest_object([
        (
            "schema",
            manifest_string("golden-board.m2-capacity-ledger/v0"),
        ),
        ("profile_id", manifest_string(core.profile.id)),
        ("carrier_sha256", manifest_string(&carrier_sha256)),
        ("section_rows", ManifestValue::Array(sections.clone())),
        ("unit_rows", ManifestValue::Array(units.clone())),
        ("ledger", ledger.clone()),
    ]);
    let capacity_ledger =
        serialize_manifest(&capacity_value).map_err(|_| CarrierError::ManifestShape)?;
    let capacity_ledger_sha256 = digest(&capacity_ledger);
    let (density_ledger, regularity) = density_ledger(core, &carrier_sha256)?;
    let realism_passes =
        match validate_realism(core, profile_policy_raw, &profile_policy_sha256, regularity) {
            Ok(()) => true,
            Err(CarrierError::Geometry) => false,
            Err(error) => return Err(error),
        };
    let density_ledger_sha256 = digest(&density_ledger);
    let base_fields = [
        (
            "schema",
            manifest_string("golden-board.m2-candidate-manifest/v0"),
        ),
        (
            "profile_policy_sha256",
            manifest_string(&profile_policy_sha256),
        ),
        (
            "profile_limits_sha256",
            manifest_string(&profile_limits_sha256),
        ),
        (
            "bootstrap_spec_sha256",
            manifest_string(&bootstrap_spec_sha256),
        ),
        ("profile_id", manifest_string(core.profile.id)),
        (
            "profile_version",
            ManifestValue::U64(u64::from(core.profile.version)),
        ),
        (
            "semantic_envelope_sha256",
            manifest_string(&core.semantic_envelope_sha256),
        ),
        ("side", ManifestValue::U64(u64::from(core.side))),
        (
            "shell_width",
            ManifestValue::U64(u64::from(core.shell_width)),
        ),
        ("mapping", mapping_manifest(core.mapping)),
        ("shell_rows", ManifestValue::Array(shell)),
        ("section_rows", ManifestValue::Array(sections)),
        ("unit_rows", ManifestValue::Array(units)),
        ("ownership_sha256", manifest_string(&ownership_sha256)),
        (
            "capacity_ledger_sha256",
            manifest_string(&capacity_ledger_sha256),
        ),
        (
            "density_ledger_sha256",
            manifest_string(&density_ledger_sha256),
        ),
        ("carrier_sha256", manifest_string(&carrier_sha256)),
        ("ledger", ledger),
    ];
    let without_identity = manifest_object(base_fields.clone());
    let without_identity_bytes =
        serialize_manifest(&without_identity).map_err(|_| CarrierError::ManifestShape)?;
    let candidate_manifest_identity =
        identity_hex(b"golden-board:manifest:v0\0", &[&without_identity_bytes])
            .map_err(|_| CarrierError::ManifestShape)?;
    let mut with_identity = object(&without_identity)?.clone();
    with_identity.insert(
        "manifest_identity".to_owned(),
        manifest_string(&candidate_manifest_identity),
    );
    let candidate_manifest = serialize_manifest(&ManifestValue::Object(with_identity))
        .map_err(|_| CarrierError::ManifestShape)?;
    Ok(ManifestationArtifacts {
        candidate_manifest,
        candidate_manifest_identity,
        ownership_ledger,
        capacity_ledger,
        density_ledger,
        carrier_sha256,
        ownership_sha256,
        capacity_ledger_sha256,
        density_ledger_sha256,
        realism_passes,
    })
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct AffineMap {
    pub side: u16,
    pub shell_width: u16,
    pub interior_side: u16,
    pub population: u64,
    pub multiplier: u64,
    pub offset: u64,
    pub inverse_multiplier: u64,
}

impl AffineMap {
    pub fn derive(side: u16, shell_width: u16, profile_version: u16) -> Result<Self> {
        if !(64..=2048).contains(&side)
            || side % 8 != 0
            || !(8..=128).contains(&shell_width)
            || shell_width % 8 != 0
            || u32::from(shell_width) * 2 + 8 > u32::from(side)
        {
            return Err(CarrierError::Geometry);
        }
        let interior_side = side
            .checked_sub(shell_width * 2)
            .ok_or(CarrierError::Geometry)?;
        let population = u64::from(interior_side)
            .checked_mul(u64::from(interior_side))
            .ok_or(CarrierError::Arithmetic)?;
        let multiplier = u64::from(interior_side)
            .checked_mul(2)
            .and_then(|value| value.checked_sub(1))
            .ok_or(CarrierError::Arithmetic)?;
        let offset =
            (u64::from(profile_version) * 40_503 + u64::from(shell_width) * 257) % population;
        let inverse_multiplier = population
            .checked_sub(u64::from(interior_side) * 2)
            .and_then(|value| value.checked_sub(1))
            .ok_or(CarrierError::Arithmetic)?;
        let map = Self {
            side,
            shell_width,
            interior_side,
            population,
            multiplier,
            offset,
            inverse_multiplier,
        };
        for logical in [0, 1, population / 2, population - 1] {
            if map.inverse(map.forward(logical)?)? != logical {
                return Err(CarrierError::Geometry);
            }
        }
        Ok(map)
    }

    pub fn forward(&self, logical: u64) -> Result<u64> {
        if logical >= self.population {
            return Err(CarrierError::Geometry);
        }
        Ok((self
            .multiplier
            .checked_mul(logical)
            .ok_or(CarrierError::Arithmetic)?
            + self.offset)
            % self.population)
    }

    pub fn inverse(&self, physical: u64) -> Result<u64> {
        if physical >= self.population {
            return Err(CarrierError::Geometry);
        }
        let shifted = (physical + self.population - self.offset) % self.population;
        Ok(self
            .inverse_multiplier
            .checked_mul(shifted)
            .ok_or(CarrierError::Arithmetic)?
            % self.population)
    }

    pub fn matrix_cell(&self, physical: u64) -> Result<(u16, u16)> {
        if physical >= self.population {
            return Err(CarrierError::Geometry);
        }
        let row = physical / u64::from(self.interior_side) + u64::from(self.shell_width);
        let column = physical % u64::from(self.interior_side) + u64::from(self.shell_width);
        Ok((u16::try_from(row).unwrap(), u16::try_from(column).unwrap()))
    }
}

pub const R3_UNIT_BITS: u64 = (EH_UNIT_BYTES * 8) as u64;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum HierarchicalInverse {
    Unit {
        physical_ordinal: u64,
        replica_bit: u16,
        slot: u64,
    },
    FixedPad {
        logical_flat: u64,
    },
}

/// Frozen v7 `affine-slot-then-interior-v1` placement.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct HierarchicalMap {
    pub side: u16,
    pub shell_width: u16,
    pub interior_side: u16,
    pub population: u64,
    pub unit_slot_count: u64,
    pub window_side: u16,
    pub cell_multiplier: u64,
    pub cell_offset: u64,
    pub inverse_cell_multiplier: u64,
    pub slot_multiplier: u64,
    pub inverse_slot_multiplier: u64,
    pub fixed_pad_cells: u64,
}

fn gcd(mut left: u64, mut right: u64) -> u64 {
    while right != 0 {
        let remainder = left % right;
        left = right;
        right = remainder;
    }
    left
}

fn modular_inverse(value: u64, modulus: u64) -> Result<u64> {
    if value == 0 || modulus < 2 || gcd(value, modulus) != 1 {
        return Err(CarrierError::Geometry);
    }
    let (mut old_r, mut r) = (i128::from(value), i128::from(modulus));
    let (mut old_s, mut s) = (1_i128, 0_i128);
    while r != 0 {
        let quotient = old_r / r;
        (old_r, r) = (r, old_r - quotient * r);
        (old_s, s) = (s, old_s - quotient * s);
    }
    u64::try_from(old_s.rem_euclid(i128::from(modulus))).map_err(|_| CarrierError::Arithmetic)
}

fn toroidal_separation(delta: u64, side: u64) -> u64 {
    delta.min(side - delta)
}

fn slot_multiplier_separates(
    candidate: u64,
    slot_count: u64,
    interior_side: u64,
    population: u64,
    cell_multiplier: u64,
    window_side: u64,
) -> bool {
    if gcd(candidate, slot_count) != 1 {
        return false;
    }
    for lane_delta in 1..=4_u64 {
        let wrapped = (candidate * lane_delta) % slot_count;
        for slot_delta in [
            i128::from(wrapped),
            i128::from(wrapped) - i128::from(slot_count),
        ] {
            let flat = (i128::from(cell_multiplier) * i128::from(R3_UNIT_BITS) * slot_delta)
                .rem_euclid(i128::from(population)) as u64;
            let row = flat / interior_side;
            let column = flat % interior_side;
            let column_separation = toroidal_separation(column, interior_side);
            let row_cases = if column == 0 {
                [row, row]
            } else {
                [row, (row + 1) % interior_side]
            };
            let case_count = if column == 0 { 1 } else { 2 };
            for row_delta in row_cases.into_iter().take(case_count) {
                let row_separation = toroidal_separation(row_delta, interior_side);
                if row_separation.max(column_separation) < window_side {
                    return false;
                }
            }
        }
    }
    true
}

impl HierarchicalMap {
    pub fn derive(side: u16, shell_width: u16) -> Result<Self> {
        if !(64..=2048).contains(&side)
            || side % 8 != 0
            || !(8..=128).contains(&shell_width)
            || shell_width % 8 != 0
            || u32::from(shell_width) * 2 + 8 > u32::from(side)
        {
            return Err(CarrierError::Geometry);
        }
        let interior_side = side
            .checked_sub(shell_width * 2)
            .ok_or(CarrierError::Geometry)?;
        let interior = u64::from(interior_side);
        let population = interior
            .checked_mul(interior)
            .ok_or(CarrierError::Arithmetic)?;
        let unit_slot_count = population / R3_UNIT_BITS;
        if unit_slot_count < 2 {
            return Err(CarrierError::Geometry);
        }
        let window_side = 32_u64.max(interior / 8);
        let cell_multiplier = interior
            .checked_mul(2)
            .and_then(|value| value.checked_sub(1))
            .ok_or(CarrierError::Arithmetic)?;
        let cell_offset = (40_503_u64 * 7 + u64::from(shell_width) * 257) % population;
        let inverse_cell_multiplier = population
            .checked_sub(interior * 2)
            .and_then(|value| value.checked_sub(1))
            .ok_or(CarrierError::Arithmetic)?;
        if cell_multiplier * inverse_cell_multiplier % population != 1 {
            return Err(CarrierError::Geometry);
        }
        let slot_multiplier = (1..unit_slot_count)
            .find(|candidate| {
                slot_multiplier_separates(
                    *candidate,
                    unit_slot_count,
                    interior,
                    population,
                    cell_multiplier,
                    window_side,
                )
            })
            .ok_or(CarrierError::Geometry)?;
        let inverse_slot_multiplier = modular_inverse(slot_multiplier, unit_slot_count)?;
        let fixed_pad_cells = population - R3_UNIT_BITS * unit_slot_count;
        let map = Self {
            side,
            shell_width,
            interior_side,
            population,
            unit_slot_count,
            window_side: u16::try_from(window_side).map_err(|_| CarrierError::Arithmetic)?,
            cell_multiplier,
            cell_offset,
            inverse_cell_multiplier,
            slot_multiplier,
            inverse_slot_multiplier,
            fixed_pad_cells,
        };
        for physical_ordinal in [0, 1, unit_slot_count / 2, unit_slot_count - 1] {
            for replica_bit in [0_u16, 1, (R3_UNIT_BITS - 1) as u16] {
                let physical = map.forward_unit_bit(physical_ordinal, replica_bit)?;
                if map.inverse(physical)?
                    != (HierarchicalInverse::Unit {
                        physical_ordinal,
                        replica_bit,
                        slot: map.slot(physical_ordinal)?,
                    })
                {
                    return Err(CarrierError::Geometry);
                }
            }
        }
        Ok(map)
    }

    pub fn slot(&self, physical_ordinal: u64) -> Result<u64> {
        if physical_ordinal >= self.unit_slot_count {
            return Err(CarrierError::Geometry);
        }
        Ok(self.slot_multiplier * physical_ordinal % self.unit_slot_count)
    }

    pub fn logical_bit_first(&self, physical_ordinal: u64) -> Result<u64> {
        self.slot(physical_ordinal)?
            .checked_mul(R3_UNIT_BITS)
            .ok_or(CarrierError::Arithmetic)
    }

    pub fn forward_logical(&self, logical_flat: u64) -> Result<u64> {
        if logical_flat >= self.population {
            return Err(CarrierError::Geometry);
        }
        Ok((self
            .cell_multiplier
            .checked_mul(logical_flat)
            .ok_or(CarrierError::Arithmetic)?
            + self.cell_offset)
            % self.population)
    }

    pub fn forward_unit_bit(&self, physical_ordinal: u64, replica_bit: u16) -> Result<u64> {
        if u64::from(replica_bit) >= R3_UNIT_BITS {
            return Err(CarrierError::Geometry);
        }
        let logical = self
            .logical_bit_first(physical_ordinal)?
            .checked_add(u64::from(replica_bit))
            .ok_or(CarrierError::Arithmetic)?;
        self.forward_logical(logical)
    }

    pub fn inverse(&self, physical_flat: u64) -> Result<HierarchicalInverse> {
        if physical_flat >= self.population {
            return Err(CarrierError::Geometry);
        }
        let shifted = (physical_flat + self.population - self.cell_offset) % self.population;
        let logical_flat = self
            .inverse_cell_multiplier
            .checked_mul(shifted)
            .ok_or(CarrierError::Arithmetic)?
            % self.population;
        let protected_cells = R3_UNIT_BITS * self.unit_slot_count;
        if logical_flat >= protected_cells {
            return Ok(HierarchicalInverse::FixedPad { logical_flat });
        }
        let slot = logical_flat / R3_UNIT_BITS;
        let replica_bit =
            u16::try_from(logical_flat % R3_UNIT_BITS).map_err(|_| CarrierError::Arithmetic)?;
        let physical_ordinal = self.inverse_slot_multiplier * slot % self.unit_slot_count;
        Ok(HierarchicalInverse::Unit {
            physical_ordinal,
            replica_bit,
            slot,
        })
    }

    pub fn matrix_cell(&self, physical_flat: u64) -> Result<(u16, u16)> {
        if physical_flat >= self.population {
            return Err(CarrierError::Geometry);
        }
        let row = physical_flat / u64::from(self.interior_side) + u64::from(self.shell_width);
        let column = physical_flat % u64::from(self.interior_side) + u64::from(self.shell_width);
        Ok((
            u16::try_from(row).map_err(|_| CarrierError::Arithmetic)?,
            u16::try_from(column).map_err(|_| CarrierError::Arithmetic)?,
        ))
    }
}

/// Canonical damage-policy `OBS_BITS` serialization.
pub fn serialize_obs_bits(bits: &[u8]) -> Result<Vec<u8>> {
    if bits.is_empty() || bits.len() > 4_194_304 || bits.iter().any(|bit| *bit > 1) {
        return Err(CarrierError::Parameter);
    }
    let mut output = u32::try_from(bits.len())
        .map_err(|_| CarrierError::Arithmetic)?
        .to_be_bytes()
        .to_vec();
    let mut packed = Vec::with_capacity(bits.len().div_ceil(8));
    for chunk in bits.chunks(8) {
        let mut value = 0_u8;
        for bit in chunk {
            value = (value << 1) | bit;
        }
        value <<= 8 - chunk.len();
        packed.push(value);
    }
    output.extend(packed);
    Ok(output)
}

// Exact owner-defined semantic-envelope and candidate-manifest renderers.

#[cfg(test)]
mod tests {
    use super::*;
    use crate::candidate_recipe::build_eh_recipe_package;
    use crate::policy::load_profile_policy;
    use gb_slice::{SliceInputs, compile_slice_v0};

    fn slice() -> SliceCompilation {
        compile_slice_v0(SliceInputs {
            declaration: include_bytes!("../../../studies/m2/slice-v0.json"),
            content_fixture: include_bytes!("../../../conformance/content-v0.json"),
            chess_fixture: include_bytes!("../../../conformance/chess-v0.json"),
            game_set: include_bytes!("../../../reports/game-set-v0.bin"),
            content_spec: include_bytes!("../../../spec/content-v0.md"),
            constants: include_bytes!("../../../spec/constants-v0.toml"),
            curriculum: include_bytes!("../../../spec/curriculum-v0.toml"),
        })
        .unwrap()
    }

    #[test]
    fn semantic_envelope_is_exact_and_independently_derived() {
        let policy_raw = include_bytes!("../../../spec/profile-policy-v0.toml");
        let policy = load_profile_policy(policy_raw).unwrap();
        let semantic = render_semantic_envelope(
            &policy,
            policy_raw,
            &slice(),
            include_bytes!("../../../spec/curriculum-v0.toml"),
        )
        .unwrap();
        assert_eq!(semantic.canonical_bytes.len(), 376_036);
        assert_eq!(
            semantic.sha256,
            "f81e29b04b307b147aec1c2602933c778e1c9198084e5d5c8e4e29cad1bdb0fd"
        );
        assert_eq!(semantic.capacity_sections.first().unwrap().section_id, 211);
        assert_eq!(semantic.capacity_sections.last().unwrap().section_id, 263);
        assert_eq!(semantic.slots.len(), 4_174);
    }

    #[test]
    fn hierarchical_static_capacity_projection_is_exact_without_a_carrier() {
        let policy_raw = include_bytes!("../../../spec/profile-policy-v0.toml");
        let policy = load_profile_policy(policy_raw).unwrap();
        let compiled = slice();
        let semantic = render_semantic_envelope(
            &policy,
            policy_raw,
            &compiled,
            include_bytes!("../../../spec/curriculum-v0.toml"),
        )
        .unwrap();
        let projection = hierarchical_capacity_projection(
            1_952,
            128,
            &semantic,
            RESERVE_PAYLOAD_BYTES,
            MAXIMUM_PROBE_PAYLOAD,
        )
        .unwrap();
        assert_eq!(projection.unit_slot_count, 1_664);
        assert_eq!(projection.protected_unit_count, 1_664);
        assert_eq!(projection.factor_5_group_count, 30);
        assert_eq!(projection.factor_2_group_count, 442);
        assert_eq!(projection.factor_1_group_count, 630);
        assert_eq!(projection.logical_group_count, 1_102);
        assert_eq!(projection.inventory_payload_bytes, 3_040);
        assert_eq!(projection.inventory_fragment_count, 20);
        assert_eq!(projection.load_fragment_counts, [105, 94]);
        assert_eq!(projection.load_payload_bytes, [16_384, 14_736]);
        assert_eq!(projection.protected_cells, 2_875_392);
        assert_eq!(projection.fixed_pad_cells, 1_024);
    }

    #[test]
    fn profile_one_complete_carrier_reconstructs() {
        let policy_raw = include_bytes!("../../../spec/profile-policy-v0.toml");
        let policy = load_profile_policy(policy_raw).unwrap();
        let compiled = slice();
        let semantic = render_semantic_envelope(
            &policy,
            policy_raw,
            &compiled,
            include_bytes!("../../../spec/curriculum-v0.toml"),
        )
        .unwrap();
        let package = build_eh_recipe_package(1).unwrap();
        assert_eq!(
            build_manifestation_core(
                1,
                include_bytes!("../../../spec/route-data-v0.json"),
                &package,
                &semantic,
                RESERVE_PAYLOAD_BYTES + 1,
                MAXIMUM_PROBE_PAYLOAD,
            )
            .unwrap_err(),
            CarrierError::OwnerIdentity
        );
        assert_eq!(
            build_manifestation_core(
                1,
                include_bytes!("../../../spec/route-data-v0.json"),
                &package,
                &semantic,
                RESERVE_PAYLOAD_BYTES,
                MAXIMUM_PROBE_PAYLOAD + 1,
            )
            .unwrap_err(),
            CarrierError::OwnerIdentity
        );
        let mut alternate_package = package.clone();
        *alternate_package.last_mut().unwrap() ^= 1;
        assert_eq!(
            build_route_images(
                include_bytes!("../../../spec/route-data-v0.json"),
                1,
                &alternate_package,
                2_048,
                128,
            )
            .unwrap_err(),
            CarrierError::OwnerIdentity
        );
        let mut inconsistent_semantic = semantic.clone();
        inconsistent_semantic.slice_semantic_sha256 = "00".repeat(32);
        assert_eq!(
            build_manifestation_core(
                1,
                include_bytes!("../../../spec/route-data-v0.json"),
                &package,
                &inconsistent_semantic,
                RESERVE_PAYLOAD_BYTES,
                MAXIMUM_PROBE_PAYLOAD,
            )
            .unwrap_err(),
            CarrierError::OwnerIdentity
        );
        let core = build_manifestation_core(
            1,
            include_bytes!("../../../spec/route-data-v0.json"),
            &package,
            &semantic,
            RESERVE_PAYLOAD_BYTES,
            MAXIMUM_PROBE_PAYLOAD,
        )
        .unwrap();
        assert_eq!((core.side, core.shell_width), (1_952, 128));
        assert_eq!(core.units.len(), 1_664);
        assert_eq!(core.interior_fixed_pad_bits.len(), 1_024);
        let load = core
            .sections
            .iter()
            .filter(|row| row.section_type == SECTION_LOAD_PROBE)
            .collect::<Vec<_>>();
        assert_eq!(load.len(), 3);
        assert_eq!(
            load.iter()
                .map(|row| (section_fragment_count(row).unwrap(), row.payload.len()))
                .collect::<Vec<_>>(),
            vec![(105, 16_384), (105, 16_384), (79, 12_381)]
        );
        assert_eq!(core.carrier_bits.len(), usize::from(core.side).pow(2));
        assert_eq!(
            core.units.len() * EH_UNIT_BYTES * 8 + core.interior_fixed_pad_bits.len(),
            core.mapping.population as usize
        );
        assert_eq!(core.sections.len(), 137);
        validate_clean_reconstruction(&core, &compiled).unwrap();
    }

    #[test]
    fn profile_one_artifacts_are_canonical_and_owner_bound() {
        let policy_raw = include_bytes!("../../../spec/profile-policy-v0.toml");
        let policy = load_profile_policy(policy_raw).unwrap();
        let compiled = slice();
        let semantic = render_semantic_envelope(
            &policy,
            policy_raw,
            &compiled,
            include_bytes!("../../../spec/curriculum-v0.toml"),
        )
        .unwrap();
        let package = build_eh_recipe_package(1).unwrap();
        let core = build_manifestation_core(
            1,
            include_bytes!("../../../spec/route-data-v0.json"),
            &package,
            &semantic,
            RESERVE_PAYLOAD_BYTES,
            MAXIMUM_PROBE_PAYLOAD,
        )
        .unwrap();
        let (diagnostic_scopes, diagnostic_regularity) = density_data(&core).unwrap();
        assert_eq!(diagnostic_regularity, [45, 63, 165, 504, 0, 0]);
        assert_eq!(
            diagnostic_scopes
                .iter()
                .find(|row| row.id == "complete-interior")
                .map(|row| (row.cells, row.ones)),
            Some((2_876_416, 1_165_423))
        );
        let artifacts = render_manifestation_artifacts(
            &core,
            &semantic,
            &compiled,
            policy_raw,
            include_bytes!("../../../spec/damage-policy-v0.toml"),
            include_bytes!("../../../spec/profile-limits-v0.toml"),
            include_bytes!("../../../spec/bootstrap-v0.md"),
            include_bytes!("../../../spec/curriculum-v0.toml"),
            include_bytes!("../../../spec/route-data-v0.json"),
            &package,
        )
        .unwrap();
        assert!(artifacts.realism_passes);
        validate_manifestation_realism(&core, policy_raw).unwrap();
        assert_eq!(
            digest(&artifacts.candidate_manifest),
            "75d8b6a518315a707d6c1964001b4482c3913be8c3ba79bb43781e33816e6bbb"
        );
        assert_eq!(
            artifacts.candidate_manifest_identity,
            "0627029a418877e9331651d881da5b587e657f69f03fe08e01a641b9248c7cba"
        );
        assert_eq!(
            artifacts.carrier_sha256,
            "6e13d469877971ca30818d11084723f7b36a3560bf404de3904cb6a1f47f0513"
        );
        assert_eq!(
            artifacts.ownership_sha256,
            "bb1b1def3afa01adc47b612fae3b31d9620aa0f70484ae3e69ce75e7fed7f3bc"
        );
        assert_eq!(
            artifacts.capacity_ledger_sha256,
            "6cc17f016052bfc56265e64262f0800236e4a2bdf76ea249724eced38eb18480"
        );
        assert_eq!(
            artifacts.density_ledger_sha256,
            "c1c4c3ce92aac7f16e477158b4b826c7be13e4a9368c515bb3a94c0e99c078ab"
        );
        for raw in [
            &artifacts.candidate_manifest,
            &artifacts.ownership_ledger,
            &artifacts.capacity_ledger,
            &artifacts.density_ledger,
        ] {
            validate_canonical_manifest(raw).unwrap();
        }
        assert_eq!(artifacts.carrier_sha256, digest(&core.carrier_bytes));
        assert_eq!(
            artifacts.ownership_sha256,
            digest(&artifacts.ownership_ledger)
        );
        assert_eq!(
            artifacts.capacity_ledger_sha256,
            digest(&artifacts.capacity_ledger)
        );
        assert_eq!(
            artifacts.density_ledger_sha256,
            digest(&artifacts.density_ledger)
        );
    }

    #[test]
    fn profile_three_survives_lower_bound_and_has_complete_artifacts() {
        let policy_raw = include_bytes!("../../../spec/profile-policy-v0.toml");
        let policy = load_profile_policy(policy_raw).unwrap();
        let compiled = slice();
        let semantic = render_semantic_envelope(
            &policy,
            policy_raw,
            &compiled,
            include_bytes!("../../../spec/curriculum-v0.toml"),
        )
        .unwrap();
        let package = build_eh_recipe_package(3).unwrap();
        let bound = capacity_elimination_bound(
            3,
            include_bytes!("../../../spec/route-data-v0.json"),
            &package,
            &semantic,
            RESERVE_PAYLOAD_BYTES,
            MAXIMUM_PROBE_PAYLOAD,
        )
        .unwrap();
        assert_eq!(
            (
                bound.inventory_units,
                bound.tier_frame_units,
                bound.real_content_units,
                bound.capacity_probe_units,
                bound.reserve_probe_units,
            ),
            (40, 12, 140, 1_491, 138)
        );
        assert_eq!(bound.protected_unit_count, 1_821);
        assert_eq!(bound.protected_cells, 3_146_688);
        assert_eq!(bound.route_prefix_cells, 886_848);
        assert_eq!(bound.lower_bound_cells, 4_033_536);
        assert!(bound.lower_bound_cells <= bound.carrier_ceiling_cells);
        assert_eq!(
            render_capacity_elimination_artifact(
                3,
                include_bytes!("../../../spec/route-data-v0.json"),
                &package,
                &semantic,
                &compiled,
                policy_raw,
                include_bytes!("../../../spec/damage-policy-v0.toml"),
                include_bytes!("../../../spec/profile-limits-v0.toml"),
                include_bytes!("../../../spec/curriculum-v0.toml"),
            )
            .unwrap_err(),
            CarrierError::Geometry
        );
        let core = build_manifestation_core(
            3,
            include_bytes!("../../../spec/route-data-v0.json"),
            &package,
            &semantic,
            RESERVE_PAYLOAD_BYTES,
            MAXIMUM_PROBE_PAYLOAD,
        )
        .unwrap();
        validate_clean_reconstruction(&core, &compiled).unwrap();
        let (scopes, regularity) = density_data(&core).unwrap();
        let artifacts = render_manifestation_artifacts(
            &core,
            &semantic,
            &compiled,
            policy_raw,
            include_bytes!("../../../spec/damage-policy-v0.toml"),
            include_bytes!("../../../spec/profile-limits-v0.toml"),
            include_bytes!("../../../spec/bootstrap-v0.md"),
            include_bytes!("../../../spec/curriculum-v0.toml"),
            include_bytes!("../../../spec/route-data-v0.json"),
            &package,
        )
        .unwrap();
        assert_eq!((core.side, core.shell_width), (2_032, 128));
        assert_eq!(core.units.len(), 1_825);
        assert_eq!(core.interior_fixed_pad_bits.len(), 576);
        assert_eq!(core.sections.len(), 135);
        assert_eq!(
            core.sections
                .iter()
                .filter(|row| row.section_type == SECTION_LOAD_PROBE)
                .map(|row| (section_fragment_count(row).unwrap(), row.payload.len()))
                .collect::<Vec<_>>(),
            vec![(4, 606)]
        );
        assert_eq!(regularity, [48, 66, 158, 497, 0, 0]);
        assert_eq!(
            scopes
                .iter()
                .find(|row| row.id == "complete-interior")
                .map(|row| (row.cells, row.ones)),
            Some((3_154_176, 1_281_920))
        );
        assert_eq!(
            digest(&artifacts.candidate_manifest),
            "1e1bd5551ee357f3f4b809afba480b379c41b7365b971493db8f3bc2e415168b"
        );
        assert_eq!(
            artifacts.candidate_manifest_identity,
            "758ca1a16fdec033ee30a4ed9fef2853d41a433d9e2e2a56cd466834f7582ff9"
        );
        assert_eq!(
            artifacts.carrier_sha256,
            "40405cd5cafe41653d1bc75e082ccf3f4458403426e154d3e2aeba2f1c58c1f8"
        );
        assert_eq!(
            artifacts.ownership_sha256,
            "d72137c290c35d2fa0da6d09848fdb511ab7f3fe2db1a325a85d16292084b872"
        );
        assert_eq!(
            artifacts.capacity_ledger_sha256,
            "a92436acab9a9b80ff3a0a09c68103e18f04ccaf7467743449d1b45644ee99c7"
        );
        assert_eq!(
            artifacts.density_ledger_sha256,
            "c7d9558d241acc735f01602bec938c7c05eb6ecb963ede840ca021e3a4313016"
        );
        assert!(artifacts.realism_passes);
        validate_manifestation_realism(&core, policy_raw).unwrap();
        for raw in [
            &artifacts.candidate_manifest,
            &artifacts.ownership_ledger,
            &artifacts.capacity_ledger,
            &artifacts.density_ledger,
        ] {
            validate_canonical_manifest(raw).unwrap();
        }
        assert_eq!(artifacts.carrier_sha256, digest(&core.carrier_bytes));
        assert_eq!(
            artifacts.ownership_sha256,
            digest(&artifacts.ownership_ledger)
        );
        assert_eq!(
            artifacts.capacity_ledger_sha256,
            digest(&artifacts.capacity_ledger)
        );
        assert_eq!(
            artifacts.density_ledger_sha256,
            digest(&artifacts.density_ledger)
        );
    }

    #[test]
    fn exact_routes_are_built_without_another_implementation() {
        for profile in [1, 3] {
            let package = build_eh_recipe_package(profile).unwrap();
            let routes = build_route_images(
                include_bytes!("../../../spec/route-data-v0.json"),
                profile,
                &package,
                2_048,
                128,
            )
            .unwrap();
            assert_eq!(routes.instruction_cells, 886_848);
            assert_eq!(routes.headroom_cells, 44_343);
            for sector in &routes.sectors {
                assert_eq!(sector.route_prefix_cells, 27_714 * 8);
                assert_eq!(sector.bits.len(), 128 * (2_048 - 128));
                assert_eq!(
                    sector.spans.iter().map(|span| span.cell_count).sum::<u64>(),
                    sector.bits.len() as u64
                );
            }
            assert_eq!(
                routes
                    .sectors
                    .iter()
                    .map(|sector| sector.headroom_cells)
                    .sum::<u64>(),
                routes.headroom_cells
            );
        }
    }

    #[test]
    fn affine_formula_is_total_at_boundaries() {
        for profile in [1, 3] {
            for (side, width) in [(64, 8), (2_048, 128)] {
                let map = AffineMap::derive(side, width, profile).unwrap();
                let mut seen = BTreeSet::new();
                for logical in 0..map.population {
                    let physical = map.forward(logical).unwrap();
                    assert!(seen.insert(physical));
                    assert_eq!(map.inverse(physical).unwrap(), logical);
                }
                assert_eq!(seen.len() as u64, map.population);
            }
        }
    }

    #[test]
    fn hierarchical_map_exact_projection_search_and_inverse_are_closed() {
        let map = HierarchicalMap::derive(1_952, 128).unwrap();
        assert_eq!(map.interior_side, 1_696);
        assert_eq!(map.population, 2_876_416);
        assert_eq!(map.unit_slot_count, 1_664);
        assert_eq!(map.window_side, 212);
        assert_eq!(map.slot_multiplier, 15);
        assert_eq!(map.inverse_slot_multiplier, 111);
        assert_eq!(map.cell_multiplier, 3_391);
        assert_eq!(map.inverse_cell_multiplier, 2_873_023);
        assert_eq!(map.cell_offset, 316_417);
        assert_eq!(map.fixed_pad_cells, 1_024);
        for candidate in 1..15 {
            assert!(!slot_multiplier_separates(
                candidate,
                map.unit_slot_count,
                u64::from(map.interior_side),
                map.population,
                map.cell_multiplier,
                u64::from(map.window_side),
            ));
        }
        assert!(slot_multiplier_separates(
            15,
            map.unit_slot_count,
            u64::from(map.interior_side),
            map.population,
            map.cell_multiplier,
            u64::from(map.window_side),
        ));
        for (ordinal, bit) in [
            (0, 0),
            (0, 1_727),
            (map.unit_slot_count - 1, 0),
            (map.unit_slot_count - 1, 1_727),
        ] {
            let physical = map.forward_unit_bit(ordinal, bit).unwrap();
            assert_eq!(
                map.inverse(physical).unwrap(),
                HierarchicalInverse::Unit {
                    physical_ordinal: ordinal,
                    replica_bit: bit,
                    slot: map.slot(ordinal).unwrap(),
                }
            );
        }
        let first_pad_logical = R3_UNIT_BITS * map.unit_slot_count;
        let first_pad_physical = map.forward_logical(first_pad_logical).unwrap();
        assert_eq!(
            map.inverse(first_pad_physical).unwrap(),
            HierarchicalInverse::FixedPad {
                logical_flat: first_pad_logical,
            }
        );
    }

    #[test]
    fn protected_units_are_copy_major_then_section_then_fragment() {
        let sections = vec![
            LogicalSection {
                section_id: 1,
                section_type: SECTION_INVENTORY,
                section_version: 0,
                closure_class: CLOSURE_M2_REQUIRED,
                check_id: CHECK_CRC32C,
                copy_count: 2,
                dependencies: Vec::new(),
                game_ordinal: None,
                payload: vec![0; 200],
            },
            LogicalSection {
                section_id: 2,
                section_type: SECTION_TIER_FRAME,
                section_version: 0,
                closure_class: CLOSURE_M2_REQUIRED,
                check_id: CHECK_CRC32C,
                copy_count: 1,
                dependencies: Vec::new(),
                game_ordinal: None,
                payload: Vec::new(),
            },
        ];
        let units = protect_sections(1, &sections).unwrap();
        assert_eq!(
            units
                .iter()
                .map(|unit| (
                    unit.physical_unit_id,
                    unit.semantic_copy_id,
                    unit.section_id,
                    unit.fragment_index,
                    unit.logical_bit_first,
                ))
                .collect::<Vec<_>>(),
            vec![
                (1, 0, 1, 0, 0),
                (2, 0, 1, 1, 1_728),
                (3, 0, 2, 0, 3_456),
                (4, 1, 1, 0, 5_184),
                (5, 1, 1, 1, 6_912),
            ]
        );
    }

    #[test]
    fn hierarchical_units_are_group_contiguous_and_slot_permuted() {
        let sections = [
            (1, SECTION_INVENTORY, 1, 5),
            (2, SECTION_TIER_FRAME, 0, 5),
            (3, SECTION_TIER_FRAME, 0, 5),
            (16, SECTION_CONTENT_BODY, 0, 5),
            (17, SECTION_CONTENT_BODY, 0, 2),
            (18, SECTION_CONTENT_BODY, 0, 1),
        ]
        .into_iter()
        .map(
            |(section_id, section_type, section_version, copy_count)| LogicalSection {
                section_id,
                section_type,
                section_version,
                closure_class: if [1, 2, 3, 16].contains(&section_id) {
                    CLOSURE_M2_REQUIRED
                } else {
                    CLOSURE_M2_ALL_ONLY
                },
                check_id: CHECK_CRC32C,
                copy_count,
                dependencies: Vec::new(),
                game_ordinal: None,
                payload: vec![section_id as u8],
            },
        )
        .collect::<Vec<_>>();
        let map = HierarchicalMap::derive(1_952, 128).unwrap();
        let units = protect_sections_hierarchical(&sections, map).unwrap();
        assert_eq!(units.len(), 23);
        for (ordinal, unit) in units.iter().enumerate() {
            assert_eq!(unit.physical_unit_id, ordinal as u32 + 1);
            assert_eq!(unit.semantic_copy_id, 0);
            assert_eq!(unit.slot, map.slot(ordinal as u64).unwrap());
            assert_eq!(unit.logical_bit_first, R3_UNIT_BITS * unit.slot);
        }
        assert_eq!(
            units
                .iter()
                .map(|unit| (
                    unit.section_id,
                    unit.fragment_index,
                    unit.replica_index,
                    unit.physical_replica_count,
                ))
                .collect::<Vec<_>>(),
            [
                (1, 0, 0, 5),
                (1, 0, 1, 5),
                (1, 0, 2, 5),
                (1, 0, 3, 5),
                (1, 0, 4, 5),
                (2, 0, 0, 5),
                (2, 0, 1, 5),
                (2, 0, 2, 5),
                (2, 0, 3, 5),
                (2, 0, 4, 5),
                (3, 0, 0, 5),
                (3, 0, 1, 5),
                (3, 0, 2, 5),
                (3, 0, 3, 5),
                (3, 0, 4, 5),
                (16, 0, 0, 5),
                (16, 0, 1, 5),
                (16, 0, 2, 5),
                (16, 0, 3, 5),
                (16, 0, 4, 5),
                (17, 0, 0, 2),
                (17, 0, 1, 2),
                (18, 0, 0, 1),
            ]
        );
        for group in units.chunk_by(|left, right| {
            left.section_id == right.section_id && left.fragment_index == right.fragment_index
        }) {
            assert!(
                group
                    .windows(2)
                    .all(|pair| pair[0].encoded == pair[1].encoded)
            );
        }
    }

    #[test]
    fn r3_route_draft_is_exact_and_remains_non_promotable() {
        let generated = generate_r3_route_draft().unwrap();
        assert_eq!(generated.side, 2_040);
        assert_eq!(generated.shell_width, 128);
        assert_eq!(generated.sector_capacity_bytes, 30_592);
        assert_eq!(
            generated
                .route_images
                .sectors
                .each_ref()
                .map(|sector| sector.route_prefix_cells),
            [232_728; 4]
        );
        assert_eq!(
            generated
                .route_images
                .sectors
                .each_ref()
                .map(|sector| sector.headroom_cells),
            [11_637, 11_637, 11_636, 11_636]
        );
        assert_eq!(generated.worked_record_bytes_by_sector, [366; 4]);
        assert_eq!(generated.held_out_record_bytes_by_sector, [366; 4]);
        assert_eq!(
            generated.route_sha256,
            "a3a6c9fc8a67d5cc36d0d75f74464fbeac2819d7b6bd8048206aa19d6cbd7922"
        );
        assert_eq!(
            generated.route_prefix_sha256_by_sector,
            [
                "a3a9ac59b857af3904d2bff998bd96c36ccba4d8a97180ad8e0e9d4434b92395",
                "4da3722a786890647ece291a3fbcb14ba9f2c6a847c13088f2c47792a52c861a",
                "7c55f1be66239d4c48a0760217a31d0cd36b30a8d04ac91c17a67315a04c4fbb",
                "5daca7964260360c62877969618e5756a946ee2d5f2b2d78756e29f5c63d44a1",
            ]
        );
        assert_eq!(generated.recipient_package.len(), 25_930);
        assert_eq!(
            generated.recipient_package_sha256,
            "4bd8e0d485ae6e6a65f4edc4ef2aaac9585a2bcd8c4623e44d69f1dad3b0ec8e"
        );
        assert_eq!(generated.mapping.unit_slot_count, 1_841);
        assert_eq!(generated.mapping.slot_multiplier, 2);
        assert_eq!(generated.mapping.inverse_slot_multiplier, 921);
        assert_eq!(generated.mapping.fixed_pad_cells, 1_408);
        assert_eq!(generated.logical_group_count, 1_279);
        assert_eq!(generated.factor_1_group_count, 807);
        assert_eq!(generated.factor_2_group_count, 442);
        assert_eq!(generated.factor_5_group_count, 30);
        assert_eq!(generated.load_fragment_counts, [105, 105, 105, 61]);
        assert_eq!(
            generated.load_payload_bytes,
            [16_384, 16_384, 16_384, 9_555]
        );
        assert_eq!(generated.inventory_entry_count, 138);
        assert_eq!(generated.inventory_dependency_count, 78);
        assert_eq!(generated.inventory_payload_bytes, 3_080);
        assert_eq!(generated.inventory_fragment_count, 20);

        // Cross-check the closed static ledger against the independently
        // rendered semantic envelope and the ordinary v7 load solver.
        let policy_raw = include_bytes!("../../../spec/profile-policy-v0.toml");
        let policy = load_profile_policy(policy_raw).unwrap();
        let semantic = render_semantic_envelope(
            &policy,
            policy_raw,
            &slice(),
            include_bytes!("../../../spec/curriculum-v0.toml"),
        )
        .unwrap();
        let projection = hierarchical_capacity_projection(
            generated.side,
            generated.shell_width,
            &semantic,
            RESERVE_PAYLOAD_BYTES,
            MAXIMUM_PROBE_PAYLOAD,
        )
        .unwrap();
        assert_eq!(
            projection.unit_slot_count,
            generated.mapping.unit_slot_count
        );
        assert_eq!(
            projection.protected_unit_count,
            generated.mapping.unit_slot_count
        );
        assert_eq!(
            projection.logical_group_count,
            generated.logical_group_count
        );
        assert_eq!(
            projection.factor_1_group_count,
            generated.factor_1_group_count
        );
        assert_eq!(
            projection.factor_2_group_count,
            generated.factor_2_group_count
        );
        assert_eq!(
            projection.factor_5_group_count,
            generated.factor_5_group_count
        );
        assert_eq!(
            projection.load_fragment_counts,
            generated.load_fragment_counts
        );
        assert_eq!(projection.load_payload_bytes, generated.load_payload_bytes);
        assert_eq!(
            projection.inventory_payload_bytes,
            generated.inventory_payload_bytes
        );
        assert_eq!(
            projection.inventory_fragment_count,
            generated.inventory_fragment_count
        );

        let root = validate_canonical_manifest(&generated.route_data_template).unwrap();
        assert_eq!(
            text(field(&root, "schema").unwrap()).unwrap(),
            "golden-board.route-data/v1"
        );
        assert!(
            object(field(&root, "generated").unwrap())
                .unwrap()
                .is_empty()
        );
        let receipt = validate_canonical_manifest(&generated.receipt).unwrap();
        assert_eq!(
            field(&receipt, "route_data_complete").unwrap(),
            &ManifestValue::Bool(false)
        );
    }

    #[test]
    fn fill_and_obs_serialization_are_exact_and_bounded() {
        let digest = [0x5a; 32];
        assert!(fill_bits(&digest, 0).unwrap().is_empty());
        let bits = fill_bits(&digest, 17).unwrap();
        assert_eq!(bits.len(), 17);
        assert_eq!(fill_bits(&digest, 17).unwrap(), bits);
        assert_ne!(fill_bits(&[0x5b; 32], 17).unwrap(), bits);
        assert_eq!(
            fill_bits(&digest, RAW_BITS_MAX).unwrap().len(),
            RAW_BITS_MAX
        );
        assert_eq!(
            fill_bits(&digest, RAW_BITS_MAX + 1).unwrap_err(),
            CarrierError::Parameter
        );
        assert_eq!(serialize_obs_bits(&[1, 0, 1]).unwrap(), [0, 0, 0, 3, 0xa0]);
    }

    #[test]
    fn promoted_r3_build_closes_gates_one_through_five_without_damage() {
        let compiled = slice();
        let result = build_r3_gate_one_through_five(
            include_bytes!("../../../spec/bootstrap-v1.md"),
            include_bytes!("../../../spec/profile-policy-v1.toml"),
            include_bytes!("../../../spec/damage-policy-v1.toml"),
            include_bytes!("../../../spec/route-data-v1.json"),
            include_bytes!("../../../spec/profile-limits-v1.toml"),
            include_bytes!("../../../spec/m2-r3-owner-promotion-v1.toml"),
            include_bytes!("../../../conformance/m2-r3-owner-v1.json"),
            &compiled,
            include_bytes!("../../../spec/curriculum-v0.toml"),
        )
        .unwrap();
        assert_eq!(result.gate_passes, [true; 5]);
        assert_eq!((result.core.side, result.core.shell_width), (2_040, 128));
        assert_eq!(result.core.units.len(), 1_841);
        assert_eq!(result.mandatory_physical_units, 1_465);
        assert_eq!(result.lower_bound_cells, 3_462_432);
        assert_eq!(result.clean_path_eh_decoder_invocations, 55_512);
        assert_eq!(result.clean_path_repetition_candidate_groups, 472);
        assert_eq!(result.clean_path_repetition_symbol_invocations, 815_616);
        assert_eq!(result.core.carrier_bytes.len(), 520_204);
        assert_eq!(result.artifacts.complete_interior_cells, 3_182_656);
        assert_eq!(result.artifacts.complete_interior_ones, 1_260_060);
        assert_eq!(result.artifacts.regularity, [31, 29, 249, 499, 0, 0]);
        assert!(result.artifacts.realism_passes);
        assert_eq!(
            result.artifacts.carrier_sha256,
            "c6309da5f199a237b8fc79292a5135581ad0f9b517fbe9516770ebaf084d49b0"
        );
        assert_eq!(
            digest(&result.artifacts.candidate_manifest),
            "38839aa28561ff2bec0997a80d8dc938e876526c25f40e23b6a78844f8fc1d86"
        );
        assert_eq!(
            result.artifacts.candidate_manifest_identity,
            "d783917d34bc6fb472ea7e20c989562092707c516195019434e01f2bc6f68681"
        );
        assert_eq!(
            result.artifacts.ownership_sha256,
            "fe82dc8119d77a855e7227dea95a673e3fb2ffb5a9c513cf31a169ea53ee5d12"
        );
        assert_eq!(
            result.artifacts.capacity_ledger_sha256,
            "a6e4a9b5e6a78a3ecf7d42ebbe75b0fa84258b6931183e37109dc927d0f9d2c6"
        );
        assert_eq!(
            result.artifacts.density_ledger_sha256,
            "6e931df836f063e1de96ee73514ca91b4ddd59071bc8338bdd5a79244fcbee61"
        );
        let candidate = validate_canonical_manifest(&result.artifacts.candidate_manifest).unwrap();
        let section_rows = array(field(&candidate, "section_rows").unwrap()).unwrap();
        for section_id in [1_u64, 2, 3, 16] {
            let row = section_rows
                .iter()
                .find(|row| unsigned(field(row, "section_id").unwrap()).unwrap() == section_id)
                .unwrap();
            assert_eq!(
                text(field(row, "copy_class").unwrap()).unwrap(),
                "required-spine"
            );
        }
        assert_eq!(
            text(
                field(
                    &validate_canonical_manifest(&result.artifacts.density_ledger).unwrap(),
                    "schema",
                )
                .unwrap(),
            )
            .unwrap(),
            "golden-board.m2-density-ledger/v0"
        );
        admit_r3_gate_one_through_five_artifacts(
            result.semantic.canonical_bytes(),
            &result.core.carrier_bytes,
            &result.artifacts.candidate_manifest,
            &result.artifacts.ownership_ledger,
            &result.artifacts.capacity_ledger,
            &result.artifacts.density_ledger,
            include_bytes!("../../../spec/bootstrap-v1.md"),
            include_bytes!("../../../spec/profile-policy-v1.toml"),
            include_bytes!("../../../spec/damage-policy-v1.toml"),
            include_bytes!("../../../spec/route-data-v1.json"),
            include_bytes!("../../../spec/profile-limits-v1.toml"),
            include_bytes!("../../../spec/m2-r3-owner-promotion-v1.toml"),
            include_bytes!("../../../conformance/m2-r3-owner-v1.json"),
            &compiled,
            include_bytes!("../../../spec/curriculum-v0.toml"),
        )
        .unwrap();
        let mut candidate_mutant = result.artifacts.candidate_manifest.clone();
        let middle = candidate_mutant.len() / 2;
        candidate_mutant[middle] ^= 1;
        assert_eq!(
            compare_r3_gate_artifact_bytes(
                &result,
                result.semantic.canonical_bytes(),
                &result.core.carrier_bytes,
                &candidate_mutant,
                &result.artifacts.ownership_ledger,
                &result.artifacts.capacity_ledger,
                &result.artifacts.density_ledger,
            )
            .unwrap_err(),
            CarrierError::OwnerIdentity
        );

        let archived_candidate = include_bytes!(
            "../../../artifacts/history/m2-r3-pre-gate6-convergence-clarification/eh72-hier-r5-r2-r1-crc32c-v0/candidate-manifest.json"
        );
        assert_eq!(
            digest(archived_candidate),
            "4439abb20aeb4943d9f3dddd4b2b914c08f3a411b791d2ced797533351168019"
        );
        let archived = validate_canonical_manifest(archived_candidate).unwrap();
        assert_eq!(
            text(field(&archived, "manifest_identity").unwrap()).unwrap(),
            "69b4052299e43a675683361e6a7fa83798b7b3646c873233cfbdd18432ac4cf4"
        );
    }
}
