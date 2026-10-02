//! Canonical bounded encoding 2 of the unchanged logical recipe VM.
//!
//! Scalar and recipe framing is fully checked before allocating expanded bytes.
//! The expanded program then passes the existing complete logical validator.
use crate::recipe::{
    EDGE_MAX, NODE_MAX, PACKAGE_MAX, RECIPE_MAX, RecipeOutcome, RecipePackage, RecipeValue,
    SCRATCH_MAX, STEP_MAX, TABLE_MAX, decode_recipe_package_admitted,
    evaluate_serialized_validated_recipe, evaluate_validated_recipe,
};
use crate::recipe_wire_v1::RecipePackageV1;
use crate::{BootstrapError, RejectCode, Result};

fn reject() -> BootstrapError {
    BootstrapError {
        code: RejectCode::Recipe,
        offset: None,
    }
}

fn take(raw: &[u8], start: usize, length: usize) -> Result<&[u8]> {
    raw.get(start..start.checked_add(length).ok_or_else(reject)?)
        .ok_or_else(reject)
}

fn u16_at(raw: &[u8], at: usize) -> Result<u16> {
    Ok(u16::from_be_bytes(
        take(raw, at, 2)?.try_into().map_err(|_| reject())?,
    ))
}

fn u32_at(raw: &[u8], at: usize) -> Result<u32> {
    Ok(u32::from_be_bytes(
        take(raw, at, 4)?.try_into().map_err(|_| reject())?,
    ))
}

fn u64_at(raw: &[u8], at: usize) -> Result<u64> {
    Ok(u64::from_be_bytes(
        take(raw, at, 8)?.try_into().map_err(|_| reject())?,
    ))
}

fn length_at(raw: &[u8], at: usize) -> Result<usize> {
    usize::try_from(u32_at(raw, at)?).map_err(|_| reject())
}

fn put_length(raw: &mut [u8], at: usize, length: usize) -> Result<()> {
    let value = u32::try_from(length).map_err(|_| reject())?;
    raw.get_mut(at..at.checked_add(4).ok_or_else(reject)?)
        .ok_or_else(reject)?
        .copy_from_slice(&value.to_be_bytes());
    Ok(())
}

fn read_scalar(raw: &[u8], cursor: &mut usize, bits: u32) -> Result<u64> {
    let limit = u64::MAX >> (64 - bits);
    let mut value = 0u64;
    for index in 0..bits.div_ceil(7) {
        let byte = *raw.get(*cursor).ok_or_else(reject)?;
        *cursor = cursor.checked_add(1).ok_or_else(reject)?;
        let digit = u64::from(byte & 127);
        let shift = 7 * index;
        if digit > limit >> shift {
            return Err(reject());
        }
        value |= digit << shift;
        if byte & 128 == 0 {
            if index != 0 && digit == 0 {
                return Err(reject());
            }
            return Ok(value);
        }
    }
    Err(reject())
}

fn scalar_size(value: u64) -> usize {
    ((64 - value.leading_zeros()).max(1).div_ceil(7)) as usize
}

fn write_scalar(output: &mut Vec<u8>, mut value: u64) {
    loop {
        let digit = (value & 127) as u8;
        value >>= 7;
        output.push(digit | if value == 0 { 0 } else { 128 });
        if value == 0 {
            return;
        }
    }
}

fn node_fields(op: u8) -> Result<(usize, bool, bool)> {
    let arguments = match op {
        1 | 2 | 24 | 25 => 0,
        5 | 14 | 22 => 1,
        3 | 20 | 23 => 3,
        4 | 6..=13 | 15..=19 | 21 => 2,
        _ => return Err(reject()),
    };
    Ok((
        arguments,
        matches!(op, 2 | 5 | 22),
        matches!(op, 1 | 5 | 14 | 22 | 25),
    ))
}

fn decode_node(record: &[u8], cursor: &mut usize, ordinal: usize) -> Result<[u8; 32]> {
    let tag = *record.get(*cursor).ok_or_else(reject)?;
    *cursor = cursor.checked_add(1).ok_or_else(reject)?;
    let opcode = tag & 31;
    let output_type = tag >> 5;
    if output_type > 5 {
        return Err(reject());
    }
    let (arguments, auxiliary, immediate) = node_fields(opcode)?;
    let mut node = [0u8; 32];
    node[..2].copy_from_slice(&u16::try_from(ordinal).map_err(|_| reject())?.to_be_bytes());
    node[2] = opcode;
    node[3] = output_type;
    node[4..8].copy_from_slice(&(read_scalar(record, cursor, 32)? as u32).to_be_bytes());
    node[8..10].copy_from_slice(&(arguments as u16).to_be_bytes());
    for index in 0..arguments {
        node[10 + 2 * index..12 + 2 * index]
            .copy_from_slice(&(read_scalar(record, cursor, 16)? as u16).to_be_bytes());
    }
    if auxiliary {
        node[18..20].copy_from_slice(&(read_scalar(record, cursor, 16)? as u16).to_be_bytes());
    }
    if immediate {
        node[24..32].copy_from_slice(&read_scalar(record, cursor, 64)?.to_be_bytes());
    }
    Ok(node)
}

fn encoded_node_size(node: &[u8]) -> Result<usize> {
    let (arguments, auxiliary, immediate) = node_fields(node[2])?;
    let mut length = 1 + scalar_size(u64::from(u32_at(node, 4)?));
    for index in 0..arguments {
        length += scalar_size(u64::from(u16_at(node, 10 + 2 * index)?));
    }
    if auxiliary {
        length += scalar_size(u64::from(u16_at(node, 18)?));
    }
    if immediate {
        length += scalar_size(u64_at(node, 24)?);
    }
    Ok(length)
}

fn encode_node(node: &[u8], output: &mut Vec<u8>) -> Result<()> {
    let (arguments, auxiliary, immediate) = node_fields(node[2])?;
    output.push((node[3] << 5) | node[2]);
    write_scalar(output, u64::from(u32_at(node, 4)?));
    for index in 0..arguments {
        write_scalar(output, u64::from(u16_at(node, 10 + 2 * index)?));
    }
    if auxiliary {
        write_scalar(output, u64::from(u16_at(node, 18)?));
    }
    if immediate {
        write_scalar(output, u64_at(node, 24)?);
    }
    Ok(())
}

fn decode_descriptor(record: &[u8], cursor: &mut usize, ordinal: usize) -> Result<[u8; 12]> {
    let kind = *record.get(*cursor).ok_or_else(reject)?;
    if !matches!(kind, 0..=3 | 5) {
        return Err(reject());
    }
    *cursor = cursor.checked_add(1).ok_or_else(reject)?;
    let width = read_scalar(record, cursor, 32)? as u32;
    let mut descriptor = [0u8; 12];
    descriptor[..2].copy_from_slice(&u16::try_from(ordinal).map_err(|_| reject())?.to_be_bytes());
    descriptor[2] = kind;
    descriptor[4..8].copy_from_slice(&width.to_be_bytes());
    descriptor[11] = 1;
    Ok(descriptor)
}

struct Frame {
    first: usize,
    input_bytes: usize,
    inputs: usize,
    outputs: usize,
    nodes: usize,
    output_bytes: usize,
}

struct Plan {
    tables_end: usize,
    output_bytes: usize,
    frames: Vec<Frame>,
}

fn plan(raw: &[u8], profile: u16, expanding: bool) -> Result<Plan> {
    if !(64..=PACKAGE_MAX).contains(&raw.len())
        || profile != 8
        || take(raw, 0, 8)? != b"GBRECP0\0"
        || u16_at(raw, 8)? != if expanding { 2 } else { 0 }
        || u16_at(raw, 10)? != 0
        || u16_at(raw, 12)? != profile
        || u16_at(raw, 14)? != 0
        || take(raw, 48, 16)?.iter().any(|v| *v != 0)
        || length_at(raw, 32)? != raw.len()
    {
        return Err(reject());
    }
    let recipes = usize::from(u16_at(raw, 16)?);
    let tables = usize::from(u16_at(raw, 18)?);
    let nodes = length_at(raw, 20)?;
    if !(1..=RECIPE_MAX).contains(&recipes)
        || tables > TABLE_MAX
        || !(1..=NODE_MAX).contains(&nodes)
        || u64::from(u32_at(raw, 24)?) > EDGE_MAX
        || length_at(raw, 28)? > PACKAGE_MAX
        || u64_at(raw, 36)? > STEP_MAX
        || u64::from(u32_at(raw, 44)?) > SCRATCH_MAX
    {
        return Err(reject());
    }
    let mut cursor = 64usize;
    let mut table_payload = 0usize;
    for _ in 0..tables {
        let header = take(raw, cursor, 16)?;
        let count = length_at(header, 8)?;
        let payload = length_at(header, 12)?;
        if !(1..=PACKAGE_MAX).contains(&count) || payload > PACKAGE_MAX {
            return Err(reject());
        }
        let bytes = 16usize.checked_add(payload).ok_or_else(reject)?;
        take(raw, cursor, bytes)?;
        cursor = cursor.checked_add(bytes).ok_or_else(reject)?;
        table_payload = table_payload.checked_add(payload).ok_or_else(reject)?;
        if table_payload > PACKAGE_MAX {
            return Err(reject());
        }
    }
    if table_payload != length_at(raw, 28)? {
        return Err(reject());
    }
    let tables_end = cursor;
    let mut output_bytes = cursor;
    let mut expanded_bytes = cursor;
    let mut observed_nodes = 0usize;
    let mut frames = Vec::with_capacity(recipes);
    for _ in 0..recipes {
        let header = take(raw, cursor, 32)?;
        let inputs = usize::from(u16_at(header, 4)?);
        let outputs = usize::from(u16_at(header, 6)?);
        let count = length_at(header, 8)?;
        if inputs > 64
            || !(1..=64).contains(&outputs)
            || !(1..=NODE_MAX).contains(&count)
            || inputs.checked_add(count).ok_or_else(reject)? > NODE_MAX
            || u64::from(u32_at(header, 12)?) > EDGE_MAX
            || u64_at(header, 16)? > STEP_MAX
            || u64::from(u32_at(header, 24)?) > SCRATCH_MAX
        {
            return Err(reject());
        }
        let descriptors = inputs.checked_add(outputs).ok_or_else(reject)?;
        let front = descriptors
            .checked_mul(12)
            .and_then(|n| n.checked_add(32))
            .ok_or_else(reject)?;
        let expanded = count
            .checked_mul(32)
            .and_then(|n| n.checked_add(front))
            .ok_or_else(reject)?;
        expanded_bytes = expanded_bytes.checked_add(expanded).ok_or_else(reject)?;
        observed_nodes = observed_nodes.checked_add(count).ok_or_else(reject)?;
        let input_bytes = length_at(header, 28)?;
        if expanded_bytes > PACKAGE_MAX || observed_nodes > nodes || input_bytes > PACKAGE_MAX {
            return Err(reject());
        }
        let record = take(raw, cursor, input_bytes)?;
        let output = if expanding {
            let minimum = count
                .checked_mul(2)
                .and_then(|n| n.checked_add(32 + 2 * descriptors))
                .ok_or_else(reject)?;
            let maximum = count
                .checked_mul(22)
                .and_then(|n| n.checked_add(32 + 6 * descriptors))
                .ok_or_else(reject)?;
            if !(minimum..=maximum).contains(&input_bytes) {
                return Err(reject());
            }
            let mut position = 32;
            for count in [inputs, outputs] {
                for ordinal in 1..=count {
                    decode_descriptor(record, &mut position, ordinal)?;
                }
            }
            for ordinal in 1..=count {
                decode_node(record, &mut position, ordinal)?;
            }
            if position != record.len() {
                return Err(reject());
            }
            expanded
        } else {
            if input_bytes != expanded {
                return Err(reject());
            }
            let mut length = 32;
            for descriptor in take(record, 32, front - 32)?.chunks_exact(12) {
                length += 1 + scalar_size(u64::from(u32_at(descriptor, 4)?));
            }
            for node in record[front..].chunks_exact(32) {
                length = length
                    .checked_add(encoded_node_size(node)?)
                    .ok_or_else(reject)?;
            }
            length
        };
        output_bytes = output_bytes.checked_add(output).ok_or_else(reject)?;
        if output_bytes > PACKAGE_MAX {
            return Err(reject());
        }
        frames.push(Frame {
            first: cursor,
            input_bytes,
            inputs,
            outputs,
            nodes: count,
            output_bytes: output,
        });
        cursor = cursor.checked_add(input_bytes).ok_or_else(reject)?;
    }
    if cursor != raw.len() || observed_nodes != nodes {
        return Err(reject());
    }
    Ok(Plan {
        tables_end,
        output_bytes,
        frames,
    })
}

fn transcode(raw: &[u8], profile: u16, expanding: bool) -> Result<Vec<u8>> {
    let plan = plan(raw, profile, expanding)?;
    let mut output = Vec::with_capacity(plan.output_bytes);
    output.extend_from_slice(&raw[..plan.tables_end]);
    output[8..10].copy_from_slice(&(if expanding { 0u16 } else { 2u16 }).to_be_bytes());
    put_length(&mut output, 32, plan.output_bytes)?;
    for frame in plan.frames {
        let record = take(raw, frame.first, frame.input_bytes)?;
        let start = output.len();
        output.extend_from_slice(take(record, 0, 32)?);
        put_length(&mut output, start + 28, frame.output_bytes)?;
        let mut cursor = 32;
        for count in [frame.inputs, frame.outputs] {
            for ordinal in 1..=count {
                if expanding {
                    output.extend_from_slice(&decode_descriptor(record, &mut cursor, ordinal)?);
                } else {
                    let descriptor = take(record, cursor, 12)?;
                    output.push(descriptor[2]);
                    write_scalar(&mut output, u64::from(u32_at(descriptor, 4)?));
                    cursor = cursor.checked_add(12).ok_or_else(reject)?;
                }
            }
        }
        for ordinal in 1..=frame.nodes {
            if expanding {
                output.extend_from_slice(&decode_node(record, &mut cursor, ordinal)?);
            } else {
                encode_node(take(record, cursor, 32)?, &mut output)?;
                cursor = cursor.checked_add(32).ok_or_else(reject)?;
            }
        }
        if cursor != record.len() || output.len() - start != frame.output_bytes {
            return Err(reject());
        }
    }
    if output.len() != plan.output_bytes {
        return Err(reject());
    }
    Ok(output)
}

/// Compress a fully admitted profile-8 logical package without changing its VM.
pub fn encode_recipe_package_v2(expanded: &[u8], profile: u16) -> Result<Vec<u8>> {
    if profile != 8 {
        return Err(reject());
    }
    decode_recipe_package_admitted(expanded, profile, 8)?;
    transcode(expanded, profile, false)
}

fn expand_validated(raw: &[u8], profile: u16) -> Result<(Vec<u8>, RecipePackage)> {
    let expanded = transcode(raw, profile, true)?;
    let logical = decode_recipe_package_admitted(&expanded, profile, 8)?;
    Ok((expanded, logical))
}

/// Expand only after canonical wire framing and full logical admission succeed.
pub fn expand_recipe_package_v2(raw: &[u8], profile: u16) -> Result<Vec<u8>> {
    Ok(expand_validated(raw, profile)?.0)
}

/// Return the existing diagnostic view; retained encoded bytes remain authority.
pub fn decode_recipe_package_v2(raw: &[u8], profile: u16) -> Result<RecipePackageV1> {
    let (_, logical) = expand_validated(raw, profile)?;
    Ok(RecipePackageV1 {
        encoded: raw.to_vec(),
        logical,
    })
}

/// Reparse retained bytes even if cached logical fields were changed by callers.
pub fn evaluate_recipe_v2(
    package: &RecipePackageV1,
    id: u16,
    inputs: &[RecipeValue],
) -> Result<RecipeOutcome> {
    let (_, logical) = expand_validated(&package.encoded, 8)?;
    evaluate_validated_recipe(&logical, id, inputs)
}

/// Reparse serialized package and input, retaining status/output suppression.
pub fn evaluate_serialized_recipe_v2(
    raw: &[u8],
    profile: u16,
    id: u16,
    input: &[u8],
) -> Result<Vec<u8>> {
    let (_, logical) = expand_validated(raw, profile)?;
    evaluate_serialized_validated_recipe(&logical, id, input)
}
