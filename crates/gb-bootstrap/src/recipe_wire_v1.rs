//! Explicit compact recipe wire admission; the existing VM semantics are shared.
//!
//! Historical public parsers retain version-zero/profile-1..7 admission. This
//! module expands only bounded version-one packages and independently validates
//! their complete logical program before publishing or evaluating it.

use crate::recipe::{
    EDGE_MAX, NODE_MAX, PACKAGE_MAX, RECIPE_MAX, RecipeOutcome, RecipePackage, RecipeValue,
    SCRATCH_MAX, STEP_MAX, TABLE_MAX, decode_recipe_package_admitted,
    evaluate_serialized_validated_recipe, evaluate_validated_recipe,
};
use crate::{BootstrapError, RejectCode, Result};

/// Parsed diagnostic view. Execution always reparses `encoded`; mutable cached
/// logical fields cannot bypass admission or alter the executed program.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RecipePackageV1 {
    pub encoded: Vec<u8>,
    pub logical: RecipePackage,
}

fn reject() -> BootstrapError {
    BootstrapError {
        code: RejectCode::Recipe,
        offset: None,
    }
}

fn take(raw: &[u8], first: usize, length: usize) -> Result<&[u8]> {
    let end = first.checked_add(length).ok_or_else(reject)?;
    raw.get(first..end).ok_or_else(reject)
}

fn u16_at(raw: &[u8], offset: usize) -> Result<u16> {
    Ok(u16::from_be_bytes(
        take(raw, offset, 2)?.try_into().map_err(|_| reject())?,
    ))
}

fn u32_at(raw: &[u8], offset: usize) -> Result<u32> {
    Ok(u32::from_be_bytes(
        take(raw, offset, 4)?.try_into().map_err(|_| reject())?,
    ))
}

fn u64_at(raw: &[u8], offset: usize) -> Result<u64> {
    Ok(u64::from_be_bytes(
        take(raw, offset, 8)?.try_into().map_err(|_| reject())?,
    ))
}

fn length_at(raw: &[u8], offset: usize) -> Result<usize> {
    usize::try_from(u32_at(raw, offset)?).map_err(|_| reject())
}

fn put_length(raw: &mut [u8], offset: usize, value: usize) -> Result<()> {
    let value = u32::try_from(value).map_err(|_| reject())?;
    raw.get_mut(offset..offset.checked_add(4).ok_or_else(reject)?)
        .ok_or_else(reject)?
        .copy_from_slice(&value.to_be_bytes());
    Ok(())
}

fn arity(opcode: u8) -> Result<u16> {
    match opcode {
        1 | 2 | 24 | 25 => Ok(0),
        5 | 14 | 22 => Ok(1),
        3 | 20 | 23 => Ok(3),
        4 | 6..=13 | 15..=19 | 21 => Ok(2),
        _ => Err(reject()),
    }
}

#[derive(Clone, Copy)]
struct NodeFields {
    arguments: usize,
    auxiliary: bool,
    immediate: bool,
    bytes: usize,
}

fn node_fields(opcode: u8) -> Result<NodeFields> {
    let arguments = usize::from(arity(opcode)?);
    let auxiliary = matches!(opcode, 2 | 5 | 22);
    let immediate = matches!(opcode, 1 | 5 | 14 | 22 | 25);
    Ok(NodeFields {
        arguments,
        auxiliary,
        immediate,
        bytes: 6 + arguments * 2 + usize::from(auxiliary) * 2 + usize::from(immediate) * 8,
    })
}

struct RecipeFrame {
    first: usize,
    input_bytes: usize,
    front_bytes: usize,
    node_count: usize,
    output_bytes: usize,
}

struct WirePlan {
    tables_end: usize,
    output_bytes: usize,
    recipes: Vec<RecipeFrame>,
}

/// Bound the complete expansion from headers before allocating its buffer.
/// Recipe ranges also bound every subsequent variable-width node read.
fn plan(raw: &[u8], expected_profile: u16, expanding: bool) -> Result<WirePlan> {
    if !(64..=PACKAGE_MAX).contains(&raw.len())
        || !(1..=8).contains(&expected_profile)
        || take(raw, 0, 8)? != b"GBRECP0\0"
        || u16_at(raw, 8)? != u16::from(expanding)
        || u16_at(raw, 10)? != 0
        || u16_at(raw, 12)? != expected_profile
        || u16_at(raw, 14)? != 0
        || take(raw, 48, 16)?.iter().any(|byte| *byte != 0)
        || length_at(raw, 32)? != raw.len()
    {
        return Err(reject());
    }
    let recipe_count = usize::from(u16_at(raw, 16)?);
    let table_count = usize::from(u16_at(raw, 18)?);
    let node_count = length_at(raw, 20)?;
    if !(1..=RECIPE_MAX).contains(&recipe_count)
        || table_count > TABLE_MAX
        || !(1..=NODE_MAX).contains(&node_count)
        || u64::from(u32_at(raw, 24)?) > EDGE_MAX
        || length_at(raw, 28)? > PACKAGE_MAX
        || u64_at(raw, 36)? > STEP_MAX
        || u64::from(u32_at(raw, 44)?) > SCRATCH_MAX
    {
        return Err(reject());
    }
    let mut cursor = 64usize;
    let mut table_payload = 0usize;
    for _ in 0..table_count {
        let header = take(raw, cursor, 16)?;
        let count = length_at(header, 8)?;
        let payload = length_at(header, 12)?;
        if !(1..=PACKAGE_MAX).contains(&count) || payload > PACKAGE_MAX {
            return Err(reject());
        }
        let record_length = 16usize.checked_add(payload).ok_or_else(reject)?;
        take(raw, cursor, record_length)?;
        cursor = cursor.checked_add(record_length).ok_or_else(reject)?;
        table_payload = table_payload.checked_add(payload).ok_or_else(reject)?;
        if table_payload > PACKAGE_MAX {
            return Err(reject());
        }
    }
    if table_payload != length_at(raw, 28)? {
        return Err(reject());
    }
    let tables_end = cursor;
    let mut expanded_bytes = tables_end;
    let mut output_bytes = tables_end;
    let mut observed_nodes = 0usize;
    let mut recipes = Vec::with_capacity(recipe_count);
    for _ in 0..recipe_count {
        let header = take(raw, cursor, 32)?;
        let inputs = usize::from(u16_at(header, 4)?);
        let outputs = usize::from(u16_at(header, 6)?);
        let nodes = length_at(header, 8)?;
        if inputs > 64
            || !(1..=64).contains(&outputs)
            || !(1..=NODE_MAX).contains(&nodes)
            || inputs.checked_add(nodes).ok_or_else(reject)? > NODE_MAX
        {
            return Err(reject());
        }
        let descriptors = inputs
            .checked_add(outputs)
            .and_then(|count| count.checked_mul(12))
            .ok_or_else(reject)?;
        let front = 32usize.checked_add(descriptors).ok_or_else(reject)?;
        let input_length = length_at(header, 28)?;
        let expanded_length = nodes
            .checked_mul(32)
            .and_then(|bytes| bytes.checked_add(front))
            .ok_or_else(reject)?;
        expanded_bytes = expanded_bytes
            .checked_add(expanded_length)
            .ok_or_else(reject)?;
        observed_nodes = observed_nodes.checked_add(nodes).ok_or_else(reject)?;
        if expanded_bytes > PACKAGE_MAX || observed_nodes > node_count || input_length > PACKAGE_MAX
        {
            return Err(reject());
        }
        let record = take(raw, cursor, input_length)?;
        let encoded_nodes = input_length.checked_sub(front).ok_or_else(reject)?;
        let result_length = if expanding {
            if encoded_nodes < nodes.checked_mul(6).ok_or_else(reject)?
                || encoded_nodes > nodes.checked_mul(18).ok_or_else(reject)?
            {
                return Err(reject());
            }
            expanded_length
        } else {
            if input_length != expanded_length {
                return Err(reject());
            }
            let mut length = front;
            for node in record[front..].chunks_exact(32) {
                length = length
                    .checked_add(node_fields(node[2])?.bytes)
                    .ok_or_else(reject)?;
            }
            length
        };
        output_bytes = output_bytes.checked_add(result_length).ok_or_else(reject)?;
        if output_bytes > PACKAGE_MAX {
            return Err(reject());
        }
        recipes.push(RecipeFrame {
            first: cursor,
            input_bytes: input_length,
            front_bytes: front,
            node_count: nodes,
            output_bytes: result_length,
        });
        cursor = cursor.checked_add(input_length).ok_or_else(reject)?;
    }
    if cursor != raw.len() || observed_nodes != node_count {
        return Err(reject());
    }
    Ok(WirePlan {
        tables_end,
        output_bytes,
        recipes,
    })
}

/// Structurally transcode within the same frozen maximum. Semantic validation
/// is performed by each caller, never inferred from successful framing alone.
fn transcode(raw: &[u8], expected_profile: u16, expanding: bool) -> Result<Vec<u8>> {
    let plan = plan(raw, expected_profile, expanding)?;
    let mut output = Vec::with_capacity(plan.output_bytes);
    output.extend_from_slice(&raw[..plan.tables_end]);
    output[8..10].copy_from_slice(&u16::from(!expanding).to_be_bytes());
    put_length(&mut output, 32, plan.output_bytes)?;
    for frame in plan.recipes {
        let record = take(raw, frame.first, frame.input_bytes)?;
        let result_start = output.len();
        output.extend_from_slice(&record[..frame.front_bytes]);
        put_length(&mut output, result_start + 28, frame.output_bytes)?;
        let mut cursor = frame.front_bytes;
        for ordinal in 0..frame.node_count {
            if expanding {
                let opcode = *record.get(cursor).ok_or_else(reject)?;
                let fields = node_fields(opcode)?;
                let node = take(record, cursor, fields.bytes)?;
                let id = u16::try_from(ordinal + 1).map_err(|_| reject())?;
                let mut expanded = [0u8; 32];
                expanded[..2].copy_from_slice(&id.to_be_bytes());
                expanded[2..8].copy_from_slice(&node[..6]);
                expanded[8..10].copy_from_slice(&(fields.arguments as u16).to_be_bytes());
                let arguments_end = 6 + 2 * fields.arguments;
                expanded[10..10 + 2 * fields.arguments].copy_from_slice(&node[6..arguments_end]);
                let mut field_cursor = arguments_end;
                if fields.auxiliary {
                    expanded[18..20].copy_from_slice(&node[field_cursor..field_cursor + 2]);
                    field_cursor += 2;
                }
                if fields.immediate {
                    expanded[24..32].copy_from_slice(&node[field_cursor..field_cursor + 8]);
                }
                output.extend_from_slice(&expanded);
                cursor = cursor.checked_add(fields.bytes).ok_or_else(reject)?;
            } else {
                let node = take(record, cursor, 32)?;
                let fields = node_fields(node[2])?;
                output.extend_from_slice(&node[2..8]);
                output.extend_from_slice(&node[10..10 + 2 * fields.arguments]);
                if fields.auxiliary {
                    output.extend_from_slice(&node[18..20]);
                }
                if fields.immediate {
                    output.extend_from_slice(&node[24..32]);
                }
                cursor = cursor.checked_add(32).ok_or_else(reject)?;
            }
        }
        if cursor != record.len() || output.len() - result_start != frame.output_bytes {
            return Err(reject());
        }
    }
    if output.len() != plan.output_bytes {
        return Err(reject());
    }
    Ok(output)
}

/// Encode a fully validated expanded logical package; profile 8 is admitted only
/// by this explicit diagnostic entry point, never by the old public parser.
pub fn encode_recipe_package_v1(expanded: &[u8], expected_profile: u16) -> Result<Vec<u8>> {
    decode_recipe_package_admitted(expanded, expected_profile, 8)?;
    transcode(expanded, expected_profile, false)
}

fn expand_validated(raw: &[u8], expected_profile: u16) -> Result<(Vec<u8>, RecipePackage)> {
    let expanded = transcode(raw, expected_profile, true)?;
    let logical = decode_recipe_package_admitted(&expanded, expected_profile, 8)?;
    Ok((expanded, logical))
}

/// Recover exact expanded framing only after complete logical validation.
pub fn expand_recipe_package_v1(raw: &[u8], expected_profile: u16) -> Result<Vec<u8>> {
    Ok(expand_validated(raw, expected_profile)?.0)
}

/// Decode and validate both compact framing and the complete unchanged VM rules.
pub fn decode_recipe_package_v1(raw: &[u8], expected_profile: u16) -> Result<RecipePackageV1> {
    let (_, logical) = expand_validated(raw, expected_profile)?;
    Ok(RecipePackageV1 {
        encoded: raw.to_vec(),
        logical,
    })
}

/// Evaluate newly parsed bytes, not the cached diagnostic logical fields.
pub fn evaluate_recipe_v1(
    package: &RecipePackageV1,
    recipe_id: u16,
    inputs: &[RecipeValue],
) -> Result<RecipeOutcome> {
    let (_, logical) = expand_validated(&package.encoded, package.logical.profile_version)?;
    evaluate_validated_recipe(&logical, recipe_id, inputs)
}

/// Evaluate a serialized interface with exact status/output suppression.
pub fn evaluate_serialized_recipe_v1(
    package: &RecipePackageV1,
    recipe_id: u16,
    input: &[u8],
) -> Result<Vec<u8>> {
    let (_, logical) = expand_validated(&package.encoded, package.logical.profile_version)?;
    evaluate_serialized_validated_recipe(&logical, recipe_id, input)
}
