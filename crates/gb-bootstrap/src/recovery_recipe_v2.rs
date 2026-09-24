//! Source-owned recovery programs and exact native refinements.
//!
//! Callers charge the entire observed generic declaration before dispatch,
//! including failures and cache reuse. Native execution never discounts it.
use crate::body_recipe_v1::{build_revision_recipe_package, revision_recipe_builders};
use crate::candidate::{
    CodecError, DecodeQuality, EhErasure, EhObservation, aggregate_repetition_observation,
    decode_eh_unit_fast,
};
use crate::candidate_recipe::{
    EncodedTable, RecipeBuilder, encode_package_with_tables, finalize, r3_eh_tables,
};
use crate::recipe::{RecipeOutcome, RecipeValue};
use crate::recipe_wire_v1::{RecipePackageV1, decode_recipe_package_v1, expand_recipe_package_v1};
use crate::recipe_wire_v2::{encode_recipe_package_v2, expand_recipe_package_v2};
use crate::teaching_recipe_v2::{
    arity, bounded_array, descriptors, exact_table, hex, number, shape,
};
use crate::{BootstrapError, RejectCode, Result};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::sync::OnceLock;
use toml::Value;

const SOURCE: &[u8] = include_bytes!("../../../spec/recovery-program-v2.toml");
const LAST_SOURCE_ID: u16 = 127;
const NATIVE_IDS: &[u16] = &[119, 120, 122, 123, 124, 126, 127];
const TABLE_SHAPES: [(u16, u8, u32, u32); 5] = [
    (23, 3, 8, 1),
    (24, 3, 216, 2),
    (25, 3, 68, 1),
    (26, 3, 5, 8),
    (27, 3, 4, 14),
];
const TABLE_DIGESTS: [&str; 4] = [
    "852a7ac722c3d320e634ed8617e04f3105e18f683746c4e03578074945a19b9e",
    "64285c0bea30c06f2e16507c0a5f2c3a751082abc840429fa3a4bfda53d5c6c6",
    "3445e37879b2a7aa5e885fba817e974fa3234f352ffc82a301fbfdfd509f5b72",
    "fb6d348c685a7537d1ea70572feece31bdfcf1d743c62597c0e333f7aa4deaaa",
];
fn invalid() -> BootstrapError {
    BootstrapError {
        code: RejectCode::Recipe,
        offset: None,
    }
}
fn u16_at(raw: &[u8], at: usize) -> u16 {
    u16::from_be_bytes(raw[at..at + 2].try_into().expect("admitted frame"))
}
fn u32_at(raw: &[u8], at: usize) -> u32 {
    u32::from_be_bytes(raw[at..at + 4].try_into().expect("admitted frame"))
}

pub(crate) fn recovery_source(source: &[u8]) -> Result<(Vec<RecipeBuilder>, Vec<EncodedTable>)> {
    if source.len() > 262_144 {
        return Err(invalid());
    }
    let value: Value = toml::from_str(std::str::from_utf8(source).map_err(|_| invalid())?)
        .map_err(|_| invalid())?;
    let root = exact_table(&value, &["version", "tables", "recipes"])?;
    if number(&root["version"])? != 1 {
        return Err(invalid());
    }
    let mut tables = Vec::new();
    for (index, row) in bounded_array(&root["tables"], 5, 5)?.iter().enumerate() {
        let table = exact_table(row, &["id", "type", "width", "count", "payload"])?;
        let values = [
            number(&table["id"])?,
            number(&table["type"])?,
            number(&table["width"])?,
            number(&table["count"])?,
        ];
        let (id, kind, width, count) = TABLE_SHAPES[index];
        let payload = hex(&table["payload"])?;
        if values
            != [
                u64::from(id),
                u64::from(kind),
                u64::from(width),
                u64::from(count),
            ]
            || payload.len() != (width * count) as usize
            || (index == 0 && payload != crate::LOCAL_CHECK_DOMAIN)
            || (index != 0 && format!("{:x}", Sha256::digest(&payload)) != TABLE_DIGESTS[index - 1])
        {
            return Err(invalid());
        }
        tables.push((id, kind, width, count, payload));
    }
    let predecessor = decode_recipe_package_v1(&build_revision_recipe_package()?, 8)?;
    let mut steps: BTreeMap<_, _> = predecessor
        .logical
        .recipe_ids()
        .map(|id| {
            (
                id,
                predecessor
                    .logical
                    .recipe_primitive_steps(id)
                    .expect("admitted recipe"),
            )
        })
        .collect();
    let mut builders = Vec::new();
    let count = usize::from(LAST_SOURCE_ID - 113);
    for (index, row) in bounded_array(&root["recipes"], count, count)?
        .iter()
        .enumerate()
    {
        let row = exact_table(row, &["id", "inputs", "outputs", "nodes"])?;
        let id = 114 + index as u16;
        if number(&row["id"])? != u64::from(id) {
            return Err(invalid());
        }
        let inputs = descriptors(&row["inputs"], 1)?;
        let outputs = descriptors(&row["outputs"], 1)?;
        let input_count = inputs.len();
        let mut builder = RecipeBuilder::custom(id, inputs, outputs);
        let mut total = 0u64;
        for (ordinal, node) in bounded_array(&row["nodes"], 1, 4096)?.iter().enumerate() {
            let values = bounded_array(node, 9, 9)?;
            let n: Vec<_> = values.iter().map(number).collect::<Result<_>>()?;
            let op = n[0];
            let result = shape(n[1], n[2], true)?;
            let count = arity(op)?;
            if n[3] != count as u64 || n[4 + count..7].iter().any(|x| *x != 0) {
                return Err(invalid());
            }
            let mut args = Vec::new();
            for arg in &n[4..4 + count] {
                if *arg == 0 || *arg > (input_count + ordinal) as u64 {
                    return Err(invalid());
                }
                args.push(u16::try_from(*arg).map_err(|_| invalid())?);
            }
            let aux = u16::try_from(n[7]).map_err(|_| invalid())?;
            let imm = n[8];
            if (!matches!(op, 2 | 5 | 22) && aux != 0)
                || (!matches!(op, 1 | 5 | 14 | 22 | 25) && imm != 0)
            {
                return Err(invalid());
            }
            let cost = if op == 22 {
                if aux >= id || imm > 1_048_576 {
                    return Err(invalid());
                }
                imm.checked_mul(*steps.get(&aux).ok_or_else(invalid)?)
                    .and_then(|x| x.checked_add(1))
                    .ok_or_else(invalid)?
            } else {
                1
            };
            total = total.checked_add(cost).ok_or_else(invalid)?;
            if total > 268_435_456 {
                return Err(invalid());
            }
            builder.push(op as u8, result, &args, aux, imm);
        }
        steps.insert(id, total);
        builders.push(builder);
    }
    Ok((builders, tables))
}
pub(crate) fn recovery_builders_and_tables() -> Result<(Vec<RecipeBuilder>, Vec<EncodedTable>)> {
    recovery_source(SOURCE)
}

/// Compose neutral source without constructing a route or carrier.
pub fn build_recovery_recipe_package_from_source(source: &[u8]) -> Result<Vec<u8>> {
    let (owned, tables) = recovery_source(source)?;
    let mut builders = revision_recipe_builders();
    builders.extend(owned);
    builders.sort_by_key(|b| b.id);
    let mut recipes = Vec::new();
    for builder in builders {
        recipes.push(finalize(builder, &recipes));
    }
    let mut all_tables = r3_eh_tables();
    all_tables.extend(tables);
    encode_recipe_package_v2(&encode_package_with_tables(8, &recipes, all_tables), 8)
}
pub fn build_recovery_recipe_package() -> Result<Vec<u8>> {
    build_recovery_recipe_package_from_source(SOURCE)
}

type Frames = BTreeMap<(u8, u16), Vec<u8>>;
fn frames(raw: &[u8]) -> Frames {
    let mut result = BTreeMap::new();
    let mut cursor = 64;
    for _ in 0..u16_at(raw, 18) {
        let end = cursor + 16 + u32_at(raw, cursor + 12) as usize;
        result.insert((0, u16_at(raw, cursor)), raw[cursor..end].to_vec());
        cursor = end;
    }
    for _ in 0..u16_at(raw, 16) {
        let end = cursor + u32_at(raw, cursor + 28) as usize;
        result.insert((1, u16_at(raw, cursor)), raw[cursor..end].to_vec());
        cursor = end;
    }
    result
}
fn closure(rows: &Frames, root: u16) -> Option<Frames> {
    let mut result = BTreeMap::new();
    let mut pending = vec![root];
    let mut seen = BTreeSet::new();
    while let Some(id) = pending.pop() {
        if !seen.insert(id) {
            continue;
        }
        let row = rows.get(&(1, id))?;
        result.insert((1, id), row.clone());
        let start = 32 + 12 * (usize::from(u16_at(row, 4)) + usize::from(u16_at(row, 6)));
        for node in row[start..].chunks_exact(32) {
            let target = u16_at(node, 18);
            match node[2] {
                2 => {
                    result.insert((0, target), rows.get(&(0, target))?.clone());
                }
                22 => pending.push(target),
                _ => (),
            }
        }
    }
    Some(result)
}
fn admitted_frames(package: &RecipePackageV1) -> Result<Frames> {
    let expanded = match package.encoded.get(8..10).ok_or_else(invalid)? {
        [0, 1] => expand_recipe_package_v1(&package.encoded, 8)?,
        [0, 2] => expand_recipe_package_v2(&package.encoded, 8)?,
        _ => return Err(invalid()),
    };
    Ok(frames(&expanded))
}
fn neutral_frames() -> Result<&'static Frames> {
    static EXPECTED: OnceLock<Option<Frames>> = OnceLock::new();
    EXPECTED
        .get_or_init(|| {
            let raw = build_recovery_recipe_package().ok()?;
            Some(frames(&expand_recipe_package_v2(&raw, 8).ok()?))
        })
        .as_ref()
        .ok_or_else(invalid)
}

fn refined_frames(package: &RecipePackageV1, id: u16) -> Result<Frames> {
    if !NATIVE_IDS.contains(&id) {
        return Err(invalid());
    }
    let expected = neutral_frames()?;
    let observed = admitted_frames(package)?;
    let want = closure(expected, id).ok_or_else(invalid)?;
    if closure(&observed, id).as_ref() != Some(&want) {
        return Err(invalid());
    }
    Ok(want)
}

/// Scoped authority for repeatedly executing exact observed recovery closures.
/// The immutable borrow prevents retained-byte mutation for this handle's life.
/// Every call still requires its full generic resource charge by the caller.
pub struct RecoveryExecution<'a> {
    _package: &'a RecipePackageV1,
    rows: Frames,
    roots: BTreeSet<u16>,
}

impl RecoveryExecution<'_> {
    pub fn evaluate_serialized(&self, id: u16, input: &[u8]) -> Result<Vec<u8>> {
        if !self.roots.contains(&id) {
            return Err(invalid());
        }
        dispatch(&self.rows, id, input)
    }
}

/// Reparse retained bytes once and establish each requested full source closure.
pub fn admit_recovery_programs<'a>(
    package: &'a RecipePackageV1,
    ids: &[u16],
) -> Result<RecoveryExecution<'a>> {
    if ids.is_empty() || ids.len() > NATIVE_IDS.len() || package.encoded.get(8..10) != Some(&[0, 2])
    {
        return Err(invalid());
    }
    let observed = admitted_frames(package)?;
    let expected = neutral_frames()?;
    let mut roots = BTreeSet::new();
    for id in ids {
        if !NATIVE_IDS.contains(id) || !roots.insert(*id) {
            return Err(invalid());
        }
        let want = closure(expected, *id).ok_or_else(invalid)?;
        if closure(&observed, *id).as_ref() != Some(&want) {
            return Err(invalid());
        }
    }
    Ok(RecoveryExecution {
        _package: package,
        rows: observed,
        roots,
    })
}
/// Compare every retained transitive logical record/table, including resources.
pub fn recovery_program_refined(package: &RecipePackageV1, id: u16) -> bool {
    refined_frames(package, id).is_ok()
}
fn failure(status: u16) -> Vec<u8> {
    status.to_be_bytes().to_vec()
}
fn success(payload: &[u8]) -> Vec<u8> {
    [vec![0, 0], payload.to_vec()].concat()
}

fn group(input: &[u8]) -> Vec<u8> {
    let factor = usize::from(input[0]);
    let presence = input[1];
    if !matches!(factor, 1 | 2 | 5) || u16::from(presence) >> factor != 0 {
        return failure(3);
    }
    let mut lanes = Vec::with_capacity(factor);
    for lane in 0..5 {
        let pair = &input[22 + 432 * lane..22 + 432 * (lane + 1)];
        if presence & (1 << lane) == 0 {
            if pair.iter().any(|b| *b != 0) {
                return failure(3);
            }
            if lane < factor {
                lanes.push(None);
            }
        } else {
            if pair[..216]
                .iter()
                .zip(&pair[216..])
                .any(|(a, b)| a & b != 0)
            {
                return failure(3);
            }
            let erasures = (0..1728)
                .filter(|bit| pair[216 + bit / 8] & (128 >> (bit % 8)) != 0)
                .map(|bit| EhErasure {
                    codeword: (bit / 72) as u8,
                    position: (bit % 72 + 1) as u8,
                })
                .collect();
            lanes.push(Some(EhObservation {
                encoded: pair[..216].try_into().expect("typed lane"),
                erasures,
            }));
        }
    }
    let present = lanes.iter().filter(|lane| lane.is_some()).count();
    let mut candidates = BTreeMap::<[u8; 191], bool>::new();
    let mut admit = |observation: &EhObservation, original: bool| -> bool {
        match decode_eh_unit_fast(observation, 8) {
            Ok(decoded) => {
                let verified = original
                    && observation.erasures.is_empty()
                    && decoded.quality == DecodeQuality::Verified;
                candidates
                    .entry(decoded.common)
                    .and_modify(|v| *v |= verified)
                    .or_insert(verified);
                true
            }
            Err(
                CodecError::Erasure
                | CodecError::Corrupt
                | CodecError::Ambiguous
                | CodecError::LocalCheck,
            ) => true,
            Err(CodecError::Parameter | CodecError::InternalInvariant) => false,
        }
    };
    for observation in lanes.iter().flatten() {
        if !admit(observation, true) {
            return failure(11);
        }
    }
    if factor > 1 && present != 0 {
        match aggregate_repetition_observation(&lanes) {
            Ok(Some(rep)) => {
                if !admit(&rep, false) {
                    return failure(11);
                }
            }
            Ok(None) => (),
            Err(_) => return failure(11),
        }
    }
    let mut block = [0u8; 191];
    let state = match candidates.len() {
        0 if present == 0 => 0,
        0 => 1,
        1 => {
            let (bytes, verified) = candidates.first_key_value().expect("one candidate");
            block = *bytes;
            if *verified { 2 } else { 3 }
        }
        _ => 4,
    };
    let identity = [&block[..2], &block[4..14], &block[16..20], &block[22..26]].concat();
    let accepted = matches!(state, 2 | 3) && identity == input[2..22];
    let mut output = vec![0, 0, state, u8::from(accepted)];
    output.extend(block);
    output
}

fn roster(raw: &[u8], length: usize, target: u32) -> Vec<u8> {
    let count = usize::from(u16_at(raw, 2));
    if !(8..=16384).contains(&length)
        || raw[..2] != [0, 2]
        || raw[4..8] != [0, 0, 0, 64]
        || !(3..=818).contains(&count)
        || target == 0
    {
        return failure(3);
    }
    let (mut cursor, mut next, mut previous) = (8usize, 1u32, 0u32);
    let mut selected = None;
    for ordinal in 0..count {
        if cursor + 20 > length {
            return failure(3);
        }
        let entry = &raw[cursor..cursor + 20];
        let id = u32_at(entry, 0);
        let kind = u16_at(entry, 4);
        let version = u16_at(entry, 6);
        let factor = (entry[11] >> 1) & 7;
        let dependencies = u16_at(entry, 12);
        let payload = u32_at(entry, 14);
        let end = cursor + 20 + 4 * usize::from(dependencies);
        if id <= previous
            || !(1..=6).contains(&kind)
            || entry[9] != 1
            || entry[10] != 1
            || entry[11] & 240 != 0
            || !matches!(factor, 1 | 2 | 5)
            || dependencies > 4095
            || !(1..=16384).contains(&payload)
            || end > length
            || (ordinal == 0
                && (id, kind, version, factor, dependencies, payload)
                    != (1, 1, 2, 5, 0, length as u32))
        {
            return failure(3);
        }
        let envelope = 22 + 4 * u32::from(dependencies) + payload;
        let fragments = envelope.div_ceil(157);
        let after = next + fragments * u32::from(factor);
        if (next..after).contains(&target) {
            let fragment = (target - next) / u32::from(factor);
            let first = next + fragment * u32::from(factor);
            let mut row = vec![factor];
            row.extend(first.to_be_bytes());
            row.extend((first + u32::from(factor) - 1).to_be_bytes());
            row.extend([0, 8]);
            row.extend(&entry[..4]);
            row.extend([0, 0]);
            row.extend(&entry[4..8]);
            row.extend((fragment as u16).to_be_bytes());
            row.extend((fragments as u16).to_be_bytes());
            row.extend(envelope.to_be_bytes());
            selected = Some(row);
        }
        cursor = end;
        next = after;
        previous = id;
    }
    let Some(selected) = selected else {
        return failure(3);
    };
    if cursor != length {
        return failure(3);
    }
    let mut state = raw.to_vec();
    state.extend((length as u16).to_be_bytes());
    state.extend((cursor as u16).to_be_bytes());
    state.extend(next.to_be_bytes());
    state.extend(previous.to_be_bytes());
    state.extend(target.to_be_bytes());
    state.push(1);
    state.extend(selected);
    state.push(1);
    success(&state)
}

fn mapping(rows: &Frames, input: &[u8]) -> Vec<u8> {
    let side = u32::from(u16_at(input, 0));
    let width = u32::from(u16_at(input, 2));
    let unit = u32_at(input, 4);
    let bit = u32::from(u16_at(input, 8));
    if !(64..=2048).contains(&side)
        || !(8..=128).contains(&width)
        || side % 8 != 0
        || width % 8 != 0
        || 2 * width + 8 > side
    {
        return failure(3);
    }
    let interior = side - 2 * width;
    let population = interior * interior;
    let units = population / 1728;
    let multiplier = u32::from(rows[&(0, 17)][16 + (interior / 8) as usize]);
    if units < 2 || multiplier == 0 || unit == 0 || unit > units || bit >= 1728 {
        return failure(3);
    }
    let slot = multiplier * (unit - 1) % units;
    let logical = 1728 * slot + bit;
    let physical =
        ((u64::from(2 * interior - 1) * u64::from(logical) + 8 * 40503 + u64::from(width) * 257)
            % u64::from(population)) as u32;
    let row = width + physical / interior;
    let column = width + physical % interior;
    success(
        &[slot, logical, physical, row, column, row * side + column]
            .into_iter()
            .flat_map(u32::to_be_bytes)
            .collect::<Vec<_>>(),
    )
}

fn construction(rows: &Frames, input: &[u8]) -> Vec<u8> {
    let case = usize::from(input[4]);
    if case >= 8 {
        return failure(3);
    }
    let mut inventory = rows[&(0, 25)][16..].to_vec();
    inventory.resize(16384, 0);
    let roster = roster(&inventory, 68, u32_at(input, 0));
    if roster[..2] != [0, 0] {
        return roster;
    }
    let state = &roster[2..];
    let factor = state[16401];
    let key = &state[16410..16430];
    let mut observation = vec![0; 2182];
    observation[0] = factor;
    observation[2..22].copy_from_slice(key);
    for lane in 0..5 {
        let token = usize::from(rows[&(0, 26)][16 + 5 * case + lane]);
        if token == 0 {
            continue;
        }
        if lane >= usize::from(factor) {
            return failure(3);
        }
        let template = &rows[&(0, 27)][16 + 4 * token..20 + 4 * token];
        let source = usize::from(template[0]);
        let start = usize::from(template[2]);
        let count = usize::from(template[3]);
        let pair = &mut observation[22 + 432 * lane..22 + 432 * (lane + 1)];
        pair[..216].copy_from_slice(&rows[&(0, 24)][16 + 216 * source..16 + 216 * (source + 1)]);
        for bit in start..start + count {
            let flag = 128 >> (bit % 8);
            if template[1] == 1 {
                pair[216 + bit / 8] |= flag;
                pair[bit / 8] &= !flag;
            } else {
                pair[bit / 8] ^= flag;
            }
        }
        observation[1] |= 1 << lane;
    }
    let recovered = group(&observation);
    if recovered[..2] != [0, 0] {
        return recovered;
    }
    let mut output = vec![0, 0];
    output.extend(&state[16402..16406]);
    output.push(factor);
    output.extend(key);
    output.extend(&recovered[2..4]);
    output.extend(&recovered[34..57]);
    output
}

fn bootstrap_first(input: &[u8]) -> Vec<u8> {
    let limit = u32_at(input, 0);
    let mut observed = vec![5, input[4]];
    observed.extend([0; 20]);
    observed.extend(&input[5..]);
    let mut result = group(&observed);
    if result[..2] != [0, 0] {
        return result;
    }
    if !(5..=2389).contains(&limit) {
        return failure(3);
    }
    let block = &result[4..];
    let prefix = [0, 8, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 2, 0, 0, 0, 0];
    let accepted = matches!(result[2], 2 | 3)
        && block[..18] == prefix
        && (22..=16406).contains(&u32_at(block, 22))
        && 5 * u32::from(u16_at(block, 18)) <= limit;
    result[3] = u8::from(accepted);
    if !accepted {
        result[4..].fill(0);
    }
    result
}

fn descriptors_for(row: &[u8], outputs: bool) -> &[u8] {
    let inputs = usize::from(u16_at(row, 4));
    let count = usize::from(u16_at(row, if outputs { 6 } else { 4 }));
    let first = 32 + if outputs { 12 * inputs } else { 0 };
    &row[first..first + 12 * count]
}
fn decode_values(descriptors: &[u8], raw: &[u8]) -> Result<Vec<RecipeValue>> {
    let mut cursor = 0;
    let mut values = Vec::new();
    for descriptor in descriptors.chunks_exact(12) {
        let kind = descriptor[2];
        let width = u32_at(descriptor, 4);
        let size = if kind == 3 { width } else { width.div_ceil(8) } as usize;
        let value = raw.get(cursor..cursor + size).ok_or_else(invalid)?;
        cursor += size;
        let decoded = match kind {
            0 | 1 | 5 => {
                if size > 8 || (width % 8 != 0 && value[0] >> (width % 8) != 0) {
                    return Err(invalid());
                }
                let number = value.iter().fold(0u64, |n, b| (n << 8) | u64::from(*b));
                match kind {
                    0 => RecipeValue::Uint {
                        width,
                        value: number,
                    },
                    1 if number <= 1 => RecipeValue::Bool(number == 1),
                    5 if number <= 14 => RecipeValue::Status(number as u16),
                    _ => return Err(invalid()),
                }
            }
            2 => {
                if width % 8 != 0 && value[size - 1] & ((1 << (8 - width % 8)) - 1) != 0 {
                    return Err(invalid());
                }
                RecipeValue::Bits {
                    width,
                    packed: value.to_vec(),
                }
            }
            3 => RecipeValue::Bytes(value.to_vec()),
            _ => return Err(invalid()),
        };
        values.push(decoded);
    }
    if cursor != raw.len() {
        return Err(invalid());
    }
    Ok(values)
}
fn dispatch(rows: &Frames, id: u16, input: &[u8]) -> Result<Vec<u8>> {
    decode_values(descriptors_for(&rows[&(1, id)], false), input)?;
    Ok(match id {
        120 => group(input),
        119 => {
            let result = group(&input[..2182]);
            if result[..2] != [0, 0] {
                result
            } else {
                let mut state = vec![0; 4096];
                state[2806..2997].copy_from_slice(&result[4..]);
                state[3010..3012].copy_from_slice(&result[2..4]);
                success(&state)
            }
        }
        122 => roster(
            &input[..16384],
            usize::from(u16_at(input, 16384)),
            u32_at(input, 16396),
        ),
        123 => {
            let result = roster(
                &input[..16384],
                usize::from(u16_at(input, 16384)),
                u32_at(input, 16386),
            );
            if result[..2] != [0, 0] {
                result
            } else {
                let s = &result[2..];
                let mut value = vec![s[16401]];
                value.extend(&s[16402..16430]);
                value.extend((u32_at(s, 16388) - 1).to_be_bytes());
                success(&value)
            }
        }
        124 => mapping(rows, input),
        126 => construction(rows, input),
        127 => bootstrap_first(input),
        _ => return Err(invalid()),
    })
}

/// Retained-byte admission plus native execution; caller charges the full VM.
pub fn evaluate_serialized_recovery_native(
    package: &RecipePackageV1,
    id: u16,
    input: &[u8],
) -> Result<Vec<u8>> {
    dispatch(&refined_frames(package, id)?, id, input)
}
/// Typed equivalent, preserving the generic VM's exact input shape checks.
pub fn evaluate_recovery_native(
    package: &RecipePackageV1,
    id: u16,
    inputs: &[RecipeValue],
) -> Result<RecipeOutcome> {
    let rows = refined_frames(package, id)?;
    let descriptors = descriptors_for(&rows[&(1, id)], false);
    if inputs.len() != descriptors.len() / 12 {
        return Err(invalid());
    }
    let mut bytes = Vec::new();
    for (value, descriptor) in inputs.iter().zip(descriptors.chunks_exact(12)) {
        let kind = descriptor[2];
        let width = u32_at(descriptor, 4);
        match value {
            RecipeValue::Uint { width: w, value }
                if kind == 0 && *w == width && (width == 64 || *value < (1u64 << width)) =>
            {
                bytes.extend(&value.to_be_bytes()[8 - width.div_ceil(8) as usize..])
            }
            RecipeValue::Bool(value) if kind == 1 => bytes.push(u8::from(*value)),
            RecipeValue::Bits { width: w, packed }
                if kind == 2 && *w == width && packed.len() == width.div_ceil(8) as usize =>
            {
                bytes.extend(packed)
            }
            RecipeValue::Bytes(value) if kind == 3 && value.len() == width as usize => {
                bytes.extend(value)
            }
            RecipeValue::Status(value) if kind == 5 && *value <= 14 => {
                bytes.extend(value.to_be_bytes())
            }
            _ => return Err(invalid()),
        }
    }
    let raw = dispatch(&rows, id, &bytes)?;
    let status = u16_at(&raw, 0);
    let outputs = if status == 0 {
        decode_values(&descriptors_for(&rows[&(1, id)], true)[12..], &raw[2..])?
    } else {
        Vec::new()
    };
    Ok(RecipeOutcome { status, outputs })
}
