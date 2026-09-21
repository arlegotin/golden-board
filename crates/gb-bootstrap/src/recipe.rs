//! Bounded interpreter for the promoted candidate-neutral recipe language.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

use crate::{BootstrapError, RejectCode, Result};

pub(super) const PACKAGE_MAX: usize = 1_048_576;
pub(super) const RECIPE_MAX: usize = 256;
pub(super) const TABLE_MAX: usize = 4_096;
pub(super) const NODE_MAX: usize = 65_535;
pub(super) const EDGE_MAX: u64 = 262_140;
const VALUE_WIDTH_MAX: u32 = 1_048_576;
const ITERATION_MAX: u64 = 1_048_576;
pub(super) const STEP_MAX: u64 = 268_435_456;
pub(super) const SCRATCH_MAX: u64 = 16_777_216;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum RecipeType {
    Uint = 0,
    Bool = 1,
    Bits = 2,
    Bytes = 3,
    Table = 4,
    Status = 5,
}

impl RecipeType {
    fn parse(value: u8) -> Result<Self> {
        match value {
            0 => Ok(Self::Uint),
            1 => Ok(Self::Bool),
            2 => Ok(Self::Bits),
            3 => Ok(Self::Bytes),
            4 => Ok(Self::Table),
            5 => Ok(Self::Status),
            _ => Err(recipe_error()),
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RecipeValue {
    Uint {
        width: u32,
        value: u64,
    },
    Bool(bool),
    Bits {
        width: u32,
        packed: Vec<u8>,
    },
    Bytes(Vec<u8>),
    Status(u16),
    Table {
        element_type: RecipeType,
        element_width: u32,
        element_count: u32,
        payload: Arc<[u8]>,
    },
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RecipeOutcome {
    pub status: u16,
    /// Successful non-status outputs in slot order. Empty for nonzero status.
    pub outputs: Vec<RecipeValue>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Descriptor {
    value_id: u16,
    kind: RecipeType,
    width: u32,
    count: u32,
    element_type: Option<RecipeType>,
}

impl Descriptor {
    fn plain(value_id: u16, kind: RecipeType, width: u32) -> Result<Self> {
        validate_width(kind, width)?;
        Ok(Self {
            value_id,
            kind,
            width,
            count: 1,
            element_type: None,
        })
    }

    fn storage(&self) -> Result<u64> {
        match self.kind {
            RecipeType::Bytes => Ok(u64::from(self.width)),
            RecipeType::Table => Ok(0),
            _ => Ok(u64::from(self.width).div_ceil(8)),
        }
    }

    fn units(&self) -> Result<u64> {
        match self.kind {
            RecipeType::Bytes => Ok(u64::from(self.width)),
            RecipeType::Table => Err(recipe_error()),
            _ => Ok(u64::from(self.width)),
        }
    }

    fn same_shape(&self, other: &Self) -> bool {
        self.kind == other.kind
            && self.width == other.width
            && self.count == other.count
            && self.element_type == other.element_type
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct TableRecord {
    descriptor: Descriptor,
    payload: Arc<[u8]>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Node {
    id: u16,
    opcode: u8,
    output: Descriptor,
    arguments: Vec<u16>,
    auxiliary_u16: u16,
    auxiliary_u32: u32,
    immediate: u64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Recipe {
    pub id: u16,
    inputs: Vec<Descriptor>,
    outputs: Vec<Descriptor>,
    nodes: Vec<Node>,
    pub primitive_steps: u64,
    pub peak_scratch_bytes: u64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RecipePackage {
    pub profile_version: u16,
    tables: BTreeMap<u16, TableRecord>,
    recipes: BTreeMap<u16, Recipe>,
    pub maximum_primitive_steps: u64,
    pub peak_scratch_bytes: u64,
}

impl RecipePackage {
    pub(crate) fn adapter_shape(&self, recipe_id: u16) -> Option<(u64, u64)> {
        let r = self.recipes.get(&recipe_id)?;
        let bytes = r
            .outputs
            .iter()
            .try_fold(0u64, |a, d| a.checked_add(d.storage().ok()?))?;
        Some((bytes, (r.inputs.len() + r.outputs.len()) as u64))
    }
    pub fn recipe_ids(&self) -> impl Iterator<Item = u16> + '_ {
        self.recipes.keys().copied()
    }

    pub fn opcode_ids(&self) -> impl Iterator<Item = u8> + '_ {
        self.recipes
            .values()
            .flat_map(|recipe| recipe.nodes.iter().map(|node| node.opcode))
    }

    /// Longest validated dependency path measured in recipe nodes, counting
    /// both endpoints. Recipe inputs are not nodes. An ITERATE node has the
    /// ordinary value dependencies plus the owned control dependency on its
    /// already-validated body recipe.
    pub fn dependency_depth(&self) -> Option<u64> {
        let mut recipe_depths = BTreeMap::<u16, u64>::new();
        for recipe in self.recipes.values() {
            let mut node_depths = Vec::<u64>::with_capacity(recipe.nodes.len());
            for node in &recipe.nodes {
                let mut prior = 0_u64;
                for argument in &node.arguments {
                    let argument = usize::from(*argument);
                    if argument > recipe.inputs.len() {
                        prior = prior.max(*node_depths.get(argument - recipe.inputs.len() - 1)?);
                    }
                }
                if node.opcode == 22 {
                    prior = prior.max(*recipe_depths.get(&node.auxiliary_u16)?);
                }
                node_depths.push(prior.checked_add(1)?);
            }
            recipe_depths.insert(recipe.id, node_depths.into_iter().max().unwrap_or(0));
        }
        recipe_depths.values().copied().max()
    }

    /// Exact statically-derived primitive steps for one named recipe entry.
    pub fn recipe_primitive_steps(&self, recipe_id: u16) -> Option<u64> {
        self.recipes
            .get(&recipe_id)
            .map(|recipe| recipe.primitive_steps)
    }

    pub fn recipe_peak_scratch_bytes(&self, recipe_id: u16) -> Option<u64> {
        self.recipes
            .get(&recipe_id)
            .map(|recipe| recipe.peak_scratch_bytes)
    }
}

fn recipe_error() -> BootstrapError {
    BootstrapError {
        code: RejectCode::Recipe,
        offset: None,
    }
}

fn read_u16(raw: &[u8], offset: usize) -> Result<u16> {
    let bytes = raw
        .get(offset..offset.checked_add(2).ok_or_else(recipe_error)?)
        .ok_or_else(recipe_error)?;
    Ok(u16::from_be_bytes([bytes[0], bytes[1]]))
}

fn read_u32(raw: &[u8], offset: usize) -> Result<u32> {
    let bytes = raw
        .get(offset..offset.checked_add(4).ok_or_else(recipe_error)?)
        .ok_or_else(recipe_error)?;
    Ok(u32::from_be_bytes(bytes.try_into().unwrap()))
}

fn read_u64(raw: &[u8], offset: usize) -> Result<u64> {
    let bytes = raw
        .get(offset..offset.checked_add(8).ok_or_else(recipe_error)?)
        .ok_or_else(recipe_error)?;
    Ok(u64::from_be_bytes(bytes.try_into().unwrap()))
}

fn validate_width(kind: RecipeType, width: u32) -> Result<()> {
    match kind {
        RecipeType::Uint if (1..=64).contains(&width) => Ok(()),
        RecipeType::Bool if width == 1 => Ok(()),
        RecipeType::Bits if (1..=VALUE_WIDTH_MAX).contains(&width) => Ok(()),
        RecipeType::Bytes if width <= VALUE_WIDTH_MAX => Ok(()),
        RecipeType::Status if width == 16 => Ok(()),
        RecipeType::Table if width <= VALUE_WIDTH_MAX => Ok(()),
        _ => Err(recipe_error()),
    }
}

fn fits_width(value: u64, width: u32) -> bool {
    width == 64 || value < (1_u64 << width)
}

fn element_bytes(kind: RecipeType, width: u32) -> Result<usize> {
    validate_width(kind, width)?;
    usize::try_from(match kind {
        RecipeType::Bytes => u64::from(width),
        RecipeType::Table => return Err(recipe_error()),
        _ => u64::from(width).div_ceil(8),
    })
    .map_err(|_| recipe_error())
}

fn decode_scalar(kind: RecipeType, width: u32, bytes: &[u8]) -> Result<RecipeValue> {
    let expected = element_bytes(kind, width)?;
    if bytes.len() != expected {
        return Err(recipe_error());
    }
    match kind {
        RecipeType::Uint | RecipeType::Bool | RecipeType::Status => {
            let unused = expected * 8 - width as usize;
            if unused != 0 && bytes[0] >> (8 - unused) != 0 {
                return Err(recipe_error());
            }
            let mut value = 0_u64;
            for byte in bytes {
                value = value.checked_shl(8).ok_or_else(recipe_error)? | u64::from(*byte);
            }
            match kind {
                RecipeType::Uint => Ok(RecipeValue::Uint { width, value }),
                RecipeType::Bool if value <= 1 => Ok(RecipeValue::Bool(value == 1)),
                RecipeType::Status if value <= 14 => Ok(RecipeValue::Status(value as u16)),
                _ => Err(recipe_error()),
            }
        }
        RecipeType::Bits => {
            let unused = expected * 8 - width as usize;
            if unused != 0 && bytes[expected - 1] & ((1_u8 << unused) - 1) != 0 {
                return Err(recipe_error());
            }
            Ok(RecipeValue::Bits {
                width,
                packed: bytes.to_vec(),
            })
        }
        RecipeType::Bytes => Ok(RecipeValue::Bytes(bytes.to_vec())),
        RecipeType::Table => Err(recipe_error()),
    }
}

fn value_descriptor(value: &RecipeValue, value_id: u16) -> Result<Descriptor> {
    match value {
        RecipeValue::Uint { width, value } if fits_width(*value, *width) => {
            Descriptor::plain(value_id, RecipeType::Uint, *width)
        }
        RecipeValue::Bool(_) => Descriptor::plain(value_id, RecipeType::Bool, 1),
        RecipeValue::Bits { width, packed } => {
            decode_scalar(RecipeType::Bits, *width, packed)?;
            Descriptor::plain(value_id, RecipeType::Bits, *width)
        }
        RecipeValue::Bytes(value) if value.len() <= VALUE_WIDTH_MAX as usize => {
            Descriptor::plain(value_id, RecipeType::Bytes, value.len() as u32)
        }
        RecipeValue::Status(value) if *value <= 14 => {
            Descriptor::plain(value_id, RecipeType::Status, 16)
        }
        RecipeValue::Table { .. } => Err(recipe_error()),
        _ => Err(recipe_error()),
    }
}

fn parse_descriptor(raw: &[u8], offset: usize, expected_id: u16) -> Result<Descriptor> {
    let value_id = read_u16(raw, offset)?;
    let kind = RecipeType::parse(*raw.get(offset + 2).ok_or_else(recipe_error)?)?;
    let flags = *raw.get(offset + 3).ok_or_else(recipe_error)?;
    let width = read_u32(raw, offset + 4)?;
    let count = read_u32(raw, offset + 8)?;
    if value_id != expected_id || flags != 0 || kind == RecipeType::Table || count != 1 {
        return Err(recipe_error());
    }
    Descriptor::plain(value_id, kind, width)
}

fn parse_table(raw: &[u8], offset: &mut usize, previous_id: &mut u16) -> Result<TableRecord> {
    let header = raw
        .get(*offset..offset.checked_add(16).ok_or_else(recipe_error)?)
        .ok_or_else(recipe_error)?;
    let id = read_u16(header, 0)?;
    let kind = RecipeType::parse(header[2])?;
    let flags = header[3];
    let width = read_u32(header, 4)?;
    let count = read_u32(header, 8)?;
    let payload_bytes = read_u32(header, 12)?;
    if id == 0
        || id <= *previous_id
        || kind == RecipeType::Table
        || flags != 0
        || count == 0
        || count > VALUE_WIDTH_MAX
    {
        return Err(recipe_error());
    }
    let each = element_bytes(kind, width)?;
    let exact = each
        .checked_mul(usize::try_from(count).map_err(|_| recipe_error())?)
        .ok_or_else(recipe_error)?;
    if usize::try_from(payload_bytes).map_err(|_| recipe_error())? != exact {
        return Err(recipe_error());
    }
    let payload_start = offset.checked_add(16).ok_or_else(recipe_error)?;
    let payload_end = payload_start.checked_add(exact).ok_or_else(recipe_error)?;
    let payload = raw
        .get(payload_start..payload_end)
        .ok_or_else(recipe_error)?;
    if each == 0 {
        for _ in 0..count {
            decode_scalar(kind, width, &[])?;
        }
    } else {
        for item in payload.chunks_exact(each) {
            decode_scalar(kind, width, item)?;
        }
    }
    *offset = payload_end;
    *previous_id = id;
    Ok(TableRecord {
        descriptor: Descriptor {
            value_id: id,
            kind: RecipeType::Table,
            width,
            count,
            element_type: Some(kind),
        },
        payload: Arc::from(payload),
    })
}

fn node_value<'a>(values: &'a [Descriptor], id: u16) -> Result<&'a Descriptor> {
    if id == 0 {
        return Err(recipe_error());
    }
    values.get(usize::from(id - 1)).ok_or_else(recipe_error)
}

fn all_zero_fields(node: &Node, allow_aux16: bool, allow_immediate: bool) -> Result<()> {
    if node.auxiliary_u32 != 0
        || !allow_aux16 && node.auxiliary_u16 != 0
        || !allow_immediate && node.immediate != 0
    {
        return Err(recipe_error());
    }
    Ok(())
}

fn static_node(
    node: &mut Node,
    current_recipe_id: u16,
    values: &[Descriptor],
    outputs: &[Descriptor],
    tables: &BTreeMap<u16, TableRecord>,
    recipes: &BTreeMap<u16, Recipe>,
    writes: &mut [Vec<(u64, u64)>],
) -> Result<()> {
    let args = node
        .arguments
        .iter()
        .map(|id| node_value(values, *id))
        .collect::<Result<Vec<_>>>()?;
    let output = &node.output;
    let same = |left: &Descriptor, right: &Descriptor| left.same_shape(right);
    match node.opcode {
        1 => {
            all_zero_fields(node, false, true)?;
            if !args.is_empty()
                || !matches!(
                    output.kind,
                    RecipeType::Uint | RecipeType::Bool | RecipeType::Status
                )
                || !fits_width(node.immediate, output.width)
                || output.kind == RecipeType::Bool && node.immediate > 1
                || output.kind == RecipeType::Status && node.immediate > 14
            {
                return Err(recipe_error());
            }
        }
        2 => {
            all_zero_fields(node, true, false)?;
            let table = tables.get(&node.auxiliary_u16).ok_or_else(recipe_error)?;
            if !args.is_empty()
                || output.kind != RecipeType::Table
                || output.width != table.descriptor.width
            {
                return Err(recipe_error());
            }
            node.output.element_type = table.descriptor.element_type;
            node.output.count = table.descriptor.count;
        }
        3 => {
            all_zero_fields(node, false, false)?;
            if args.len() != 3
                || !matches!(args[0].kind, RecipeType::Bits | RecipeType::Bytes)
                || args[1].kind != RecipeType::Uint
                || args[2].kind != RecipeType::Uint
                || !(output.kind == args[0].kind
                    || args[0].kind == RecipeType::Bits
                        && output.kind == RecipeType::Uint
                        && output.width <= 64)
                || output.width > args[0].width
            {
                return Err(recipe_error());
            }
        }
        4 => {
            all_zero_fields(node, false, false)?;
            if args.len() != 2
                || args[0].kind != args[1].kind
                || !matches!(
                    args[0].kind,
                    RecipeType::Uint | RecipeType::Bits | RecipeType::Bytes
                )
                || output.kind != args[0].kind
                || output.width
                    != args[0]
                        .width
                        .checked_add(args[1].width)
                        .ok_or_else(recipe_error)?
            {
                return Err(recipe_error());
            }
        }
        5 => {
            all_zero_fields(node, true, true)?;
            if args.len() != 1
                || output.kind != RecipeType::Status
                || output.width != 16
                || node.auxiliary_u16 == 0
            {
                return Err(recipe_error());
            }
            let slot_index = usize::from(node.auxiliary_u16 - 1);
            let slot = outputs.get(slot_index).ok_or_else(recipe_error)?;
            let source = args[0];
            let compatible = match source.kind {
                RecipeType::Uint => matches!(slot.kind, RecipeType::Uint | RecipeType::Bits),
                RecipeType::Bool => slot.kind == RecipeType::Bool,
                RecipeType::Bits => slot.kind == RecipeType::Bits,
                RecipeType::Bytes => slot.kind == RecipeType::Bytes,
                RecipeType::Status => slot.kind == RecipeType::Status,
                RecipeType::Table => false,
            };
            if !compatible {
                return Err(recipe_error());
            }
            let length = source.units()?;
            let end = node
                .immediate
                .checked_add(length)
                .ok_or_else(recipe_error)?;
            if end > slot.units()? {
                return Err(recipe_error());
            }
            writes[slot_index].push((node.immediate, end));
        }
        6..=10 => {
            all_zero_fields(node, false, false)?;
            if args.len() != 2
                || args[0].kind != RecipeType::Uint
                || !same(args[0], args[1])
                || !same(output, args[0])
            {
                return Err(recipe_error());
            }
        }
        11..=13 => {
            all_zero_fields(node, false, false)?;
            if args.len() != 2
                || !matches!(args[0].kind, RecipeType::Uint | RecipeType::Bits)
                || !same(args[0], args[1])
                || !same(output, args[0])
            {
                return Err(recipe_error());
            }
        }
        14 => {
            all_zero_fields(node, false, true)?;
            if args.len() != 1
                || args[0].kind != RecipeType::Uint
                || !same(output, args[0])
                || !fits_width(node.immediate, output.width)
            {
                return Err(recipe_error());
            }
        }
        15 | 16 => {
            all_zero_fields(node, false, false)?;
            if args.len() != 2
                || args.iter().any(|arg| arg.kind != RecipeType::Uint)
                || !same(output, args[0])
            {
                return Err(recipe_error());
            }
        }
        17 => {
            all_zero_fields(node, false, false)?;
            if args.len() != 2
                || !same(args[0], args[1])
                || output.kind != RecipeType::Bool
                || output.width != 1
            {
                return Err(recipe_error());
            }
        }
        18 => {
            all_zero_fields(node, false, false)?;
            if args.len() != 2
                || args[0].kind != RecipeType::Uint
                || !same(args[0], args[1])
                || output.kind != RecipeType::Bool
                || output.width != 1
            {
                return Err(recipe_error());
            }
        }
        19 => {
            all_zero_fields(node, false, false)?;
            if args.len() != 2 || args[1].kind != RecipeType::Uint {
                return Err(recipe_error());
            }
            let expected = match args[0].kind {
                RecipeType::Bits => Descriptor::plain(0, RecipeType::Bool, 1)?,
                RecipeType::Bytes => Descriptor::plain(0, RecipeType::Uint, 8)?,
                RecipeType::Table => Descriptor {
                    value_id: 0,
                    kind: args[0].element_type.ok_or_else(recipe_error)?,
                    width: args[0].width,
                    count: 1,
                    element_type: None,
                },
                _ => return Err(recipe_error()),
            };
            if !same(output, &expected) {
                return Err(recipe_error());
            }
        }
        20 => {
            all_zero_fields(node, false, false)?;
            if args.len() != 3 || args[1].kind != RecipeType::Uint || !same(output, args[0]) {
                return Err(recipe_error());
            }
            let element = match args[0].kind {
                RecipeType::Bits => Descriptor::plain(0, RecipeType::Bool, 1)?,
                RecipeType::Bytes => Descriptor::plain(0, RecipeType::Uint, 8)?,
                _ => return Err(recipe_error()),
            };
            if !same(args[2], &element) {
                return Err(recipe_error());
            }
        }
        21 => {
            all_zero_fields(node, false, false)?;
            if args.len() != 2
                || args[0].kind != RecipeType::Table
                || args[1].kind != RecipeType::Uint
            {
                return Err(recipe_error());
            }
            let expected = Descriptor {
                value_id: 0,
                kind: args[0].element_type.ok_or_else(recipe_error)?,
                width: args[0].width,
                count: 1,
                element_type: None,
            };
            if !same(output, &expected) {
                return Err(recipe_error());
            }
        }
        22 => {
            all_zero_fields(node, true, true)?;
            let body = recipes.get(&node.auxiliary_u16).ok_or_else(recipe_error)?;
            if args.len() != 1
                || node.auxiliary_u16 >= current_recipe_id
                || node.immediate > ITERATION_MAX
                || !same(output, args[0])
                || body.inputs.len() != 2
                || body.outputs.len() != 2
                || !same(&body.inputs[0], args[0])
                || body.inputs[1].kind != RecipeType::Uint
                || body.inputs[1].width != 64
                || body.outputs[0].kind != RecipeType::Status
                || !same(&body.outputs[1], args[0])
            {
                return Err(recipe_error());
            }
        }
        23 => {
            all_zero_fields(node, false, false)?;
            if args.len() != 3 || args[0].kind != RecipeType::Bool || !same(args[1], args[2]) {
                return Err(recipe_error());
            }
            if args[1].kind == RecipeType::Table {
                if output.kind != RecipeType::Table || output.width != args[1].width {
                    return Err(recipe_error());
                }
                node.output.count = args[1].count;
                node.output.element_type = args[1].element_type;
            } else if !same(output, args[1]) {
                return Err(recipe_error());
            }
        }
        24 => {
            all_zero_fields(node, false, false)?;
            if !args.is_empty() || output.kind != RecipeType::Status || output.width != 16 {
                return Err(recipe_error());
            }
        }
        25 => {
            all_zero_fields(node, false, true)?;
            if !args.is_empty()
                || output.kind != RecipeType::Status
                || output.width != 16
                || !(1..=14).contains(&node.immediate)
            {
                return Err(recipe_error());
            }
        }
        _ => return Err(recipe_error()),
    }
    Ok(())
}

fn validate_output_coverage(outputs: &[Descriptor], writes: &mut [Vec<(u64, u64)>]) -> Result<()> {
    for (slot, intervals) in outputs.iter().zip(writes) {
        intervals.sort_unstable();
        let mut next = 0_u64;
        for (start, end) in intervals.iter().copied() {
            if start != next || end <= start {
                return Err(recipe_error());
            }
            next = end;
        }
        if next != slot.units()? {
            return Err(recipe_error());
        }
    }
    Ok(())
}

fn validate_reachability(recipe: &Recipe) -> Result<()> {
    let input_count = recipe.inputs.len() as u16;
    let mut reachable = BTreeSet::new();
    let mut pending = recipe
        .nodes
        .iter()
        .filter(|node| node.opcode == 5)
        .map(|node| node.id)
        .collect::<Vec<_>>();
    while let Some(id) = pending.pop() {
        if !reachable.insert(id) {
            continue;
        }
        let node = recipe
            .nodes
            .get(usize::from(id - 1))
            .ok_or_else(recipe_error)?;
        for argument in &node.arguments {
            if *argument > input_count {
                pending.push(argument - input_count);
            }
        }
    }
    if reachable.len() != recipe.nodes.len() {
        return Err(recipe_error());
    }
    Ok(())
}

fn derive_scratch(recipe: &Recipe, recipes: &BTreeMap<u16, Recipe>) -> Result<u64> {
    let input_count = recipe.inputs.len() as u16;
    let mut last_use = vec![None; recipe.nodes.len()];
    for (index, node) in recipe.nodes.iter().enumerate() {
        for argument in &node.arguments {
            if *argument > input_count {
                last_use[usize::from(*argument - input_count - 1)] = Some(index);
            }
        }
    }
    let mut live = 0_u64;
    let mut peak = 0_u64;
    for (index, node) in recipe.nodes.iter().enumerate() {
        let storage = node.output.storage()?;
        peak = peak.max(live.checked_add(storage).ok_or_else(recipe_error)?);
        if node.opcode == 22 {
            let body = recipes.get(&node.auxiliary_u16).ok_or_else(recipe_error)?;
            peak = peak.max(
                live.checked_add(body.peak_scratch_bytes)
                    .ok_or_else(recipe_error)?,
            );
        }
        live = live.checked_add(storage).ok_or_else(recipe_error)?;
        for argument in node.arguments.iter().copied().collect::<BTreeSet<_>>() {
            if argument > input_count {
                let argument_index = usize::from(argument - input_count - 1);
                if last_use[argument_index] == Some(index) {
                    live = live
                        .checked_sub(recipe.nodes[argument_index].output.storage()?)
                        .ok_or_else(recipe_error)?;
                }
            }
        }
        if last_use[index].is_none() {
            live = live.checked_sub(storage).ok_or_else(recipe_error)?;
        }
    }
    Ok(peak)
}

fn parse_recipe(
    raw: &[u8],
    offset: &mut usize,
    previous_id: &mut u16,
    tables: &BTreeMap<u16, TableRecord>,
    earlier_recipes: &BTreeMap<u16, Recipe>,
) -> Result<Recipe> {
    let start = *offset;
    let header = raw
        .get(start..start.checked_add(32).ok_or_else(recipe_error)?)
        .ok_or_else(recipe_error)?;
    let id = read_u16(header, 0)?;
    let flags = read_u16(header, 2)?;
    let input_count = usize::from(read_u16(header, 4)?);
    let output_count = usize::from(read_u16(header, 6)?);
    let node_count = usize::try_from(read_u32(header, 8)?).map_err(|_| recipe_error())?;
    let edge_count = u64::from(read_u32(header, 12)?);
    let primitive_steps = read_u64(header, 16)?;
    let peak_scratch = u64::from(read_u32(header, 24)?);
    let recipe_bytes = usize::try_from(read_u32(header, 28)?).map_err(|_| recipe_error())?;
    if id == 0
        || id <= *previous_id
        || flags != 0
        || input_count > 64
        || !(1..=64).contains(&output_count)
        || !(1..=NODE_MAX).contains(&node_count)
        || input_count
            .checked_add(node_count)
            .ok_or_else(recipe_error)?
            > u16::MAX as usize
        || edge_count > EDGE_MAX
        || primitive_steps > STEP_MAX
        || peak_scratch > SCRATCH_MAX
    {
        return Err(recipe_error());
    }
    let exact_bytes = 32_usize
        .checked_add(
            12_usize
                .checked_mul(
                    input_count
                        .checked_add(output_count)
                        .ok_or_else(recipe_error)?,
                )
                .ok_or_else(recipe_error)?,
        )
        .and_then(|value| value.checked_add(32_usize.checked_mul(node_count)?))
        .ok_or_else(recipe_error)?;
    if recipe_bytes != exact_bytes
        || start.checked_add(recipe_bytes).ok_or_else(recipe_error)? > raw.len()
    {
        return Err(recipe_error());
    }
    let mut cursor = start + 32;
    let mut inputs = Vec::with_capacity(input_count);
    for index in 0..input_count {
        inputs.push(parse_descriptor(
            raw,
            cursor,
            u16::try_from(index + 1).unwrap(),
        )?);
        cursor += 12;
    }
    let mut outputs = Vec::with_capacity(output_count);
    for index in 0..output_count {
        outputs.push(parse_descriptor(
            raw,
            cursor,
            u16::try_from(index + 1).unwrap(),
        )?);
        cursor += 12;
    }
    if outputs[0].kind != RecipeType::Status
        || outputs[0].width != 16
        || outputs
            .iter()
            .skip(1)
            .any(|slot| matches!(slot.kind, RecipeType::Status | RecipeType::Table))
    {
        return Err(recipe_error());
    }
    let mut values = inputs.clone();
    let mut nodes = Vec::with_capacity(node_count);
    let mut writes = vec![Vec::new(); output_count];
    let mut derived_edges = 0_u64;
    let mut derived_steps = 0_u64;
    for index in 0..node_count {
        let node_raw = raw.get(cursor..cursor + 32).ok_or_else(recipe_error)?;
        let node_id = read_u16(node_raw, 0)?;
        let opcode = node_raw[2];
        let output_type = RecipeType::parse(node_raw[3])?;
        let output_width = read_u32(node_raw, 4)?;
        let argument_count = usize::from(read_u16(node_raw, 8)?);
        if node_id as usize != index + 1 || !(1..=25).contains(&opcode) || argument_count > 4 {
            return Err(recipe_error());
        }
        let all_arguments = [
            read_u16(node_raw, 10)?,
            read_u16(node_raw, 12)?,
            read_u16(node_raw, 14)?,
            read_u16(node_raw, 16)?,
        ];
        if all_arguments[argument_count..]
            .iter()
            .any(|value| *value != 0)
            || all_arguments[..argument_count]
                .iter()
                .any(|value| *value == 0 || usize::from(*value) > input_count + index)
        {
            return Err(recipe_error());
        }
        let mut node = Node {
            id: node_id,
            opcode,
            output: Descriptor::plain(
                u16::try_from(input_count + index + 1).map_err(|_| recipe_error())?,
                output_type,
                output_width,
            )?,
            arguments: all_arguments[..argument_count].to_vec(),
            auxiliary_u16: read_u16(node_raw, 18)?,
            auxiliary_u32: read_u32(node_raw, 20)?,
            immediate: read_u64(node_raw, 24)?,
        };
        static_node(
            &mut node,
            id,
            &values,
            &outputs,
            tables,
            earlier_recipes,
            &mut writes,
        )?;
        derived_edges = derived_edges
            .checked_add(argument_count as u64 + u64::from(opcode == 22))
            .ok_or_else(recipe_error)?;
        let node_steps = if opcode == 22 {
            let body = earlier_recipes
                .get(&node.auxiliary_u16)
                .ok_or_else(recipe_error)?;
            1_u64
                .checked_add(
                    node.immediate
                        .checked_mul(body.primitive_steps)
                        .ok_or_else(recipe_error)?,
                )
                .ok_or_else(recipe_error)?
        } else {
            1
        };
        derived_steps = derived_steps
            .checked_add(node_steps)
            .ok_or_else(recipe_error)?;
        values.push(node.output.clone());
        nodes.push(node);
        cursor += 32;
    }
    if cursor != start + recipe_bytes
        || derived_edges != edge_count
        || derived_steps != primitive_steps
    {
        return Err(recipe_error());
    }
    validate_output_coverage(&outputs, &mut writes)?;
    let mut recipe = Recipe {
        id,
        inputs,
        outputs,
        nodes,
        primitive_steps,
        peak_scratch_bytes: peak_scratch,
    };
    validate_reachability(&recipe)?;
    if derive_scratch(&recipe, earlier_recipes)? != peak_scratch {
        return Err(recipe_error());
    }
    // Keep this assignment explicit so all checked fields above precede publication.
    recipe.peak_scratch_bytes = peak_scratch;
    *offset = cursor;
    *previous_id = id;
    Ok(recipe)
}

/// Parse and completely statically validate one recipe package.
pub fn decode_recipe_package(raw: &[u8], expected_profile_version: u16) -> Result<RecipePackage> {
    decode_recipe_package_admitted(raw, expected_profile_version, 7)
}

/// The compact-wire adapter alone additionally admits the new logical profile.
/// This still parses fully expanded version-zero node framing and all semantics.
pub(super) fn decode_recipe_package_admitted(
    raw: &[u8],
    expected_profile_version: u16,
    maximum_profile_version: u16,
) -> Result<RecipePackage> {
    if raw.len() > PACKAGE_MAX || raw.len() < 64 {
        return Err(recipe_error());
    }
    if &raw[..8] != b"GBRECP0\0"
        || read_u16(raw, 8)? != 0
        || read_u16(raw, 10)? != 0
        || read_u16(raw, 12)? != expected_profile_version
        || !(1..=maximum_profile_version).contains(&expected_profile_version)
        || read_u16(raw, 14)? != 0
        || raw[48..64].iter().any(|value| *value != 0)
    {
        return Err(recipe_error());
    }
    let recipe_count = usize::from(read_u16(raw, 16)?);
    let table_count = usize::from(read_u16(raw, 18)?);
    let total_nodes = usize::try_from(read_u32(raw, 20)?).map_err(|_| recipe_error())?;
    let total_edges = u64::from(read_u32(raw, 24)?);
    let table_payload = u64::from(read_u32(raw, 28)?);
    let package_bytes = usize::try_from(read_u32(raw, 32)?).map_err(|_| recipe_error())?;
    let maximum_steps = read_u64(raw, 36)?;
    let peak_scratch = u64::from(read_u32(raw, 44)?);
    if !(1..=RECIPE_MAX).contains(&recipe_count)
        || table_count > TABLE_MAX
        || !(1..=NODE_MAX).contains(&total_nodes)
        || total_edges > EDGE_MAX
        || table_payload > PACKAGE_MAX as u64
        || package_bytes != raw.len()
        || maximum_steps > STEP_MAX
        || peak_scratch > SCRATCH_MAX
    {
        return Err(recipe_error());
    }
    let mut cursor = 64_usize;
    let mut previous_table = 0_u16;
    let mut tables = BTreeMap::new();
    let mut observed_table_payload = 0_u64;
    for _ in 0..table_count {
        let before = cursor;
        let table = parse_table(raw, &mut cursor, &mut previous_table)?;
        observed_table_payload = observed_table_payload
            .checked_add(u64::try_from(cursor - before - 16).map_err(|_| recipe_error())?)
            .ok_or_else(recipe_error)?;
        tables.insert(table.descriptor.value_id, table);
    }
    if observed_table_payload != table_payload {
        return Err(recipe_error());
    }
    let mut previous_recipe = 0_u16;
    let mut recipes = BTreeMap::new();
    for _ in 0..recipe_count {
        let recipe = parse_recipe(raw, &mut cursor, &mut previous_recipe, &tables, &recipes)?;
        recipes.insert(recipe.id, recipe);
    }
    let observed_nodes = recipes
        .values()
        .map(|recipe| recipe.nodes.len())
        .sum::<usize>();
    let observed_edges = recipes
        .values()
        .flat_map(|recipe| recipe.nodes.iter())
        .map(|node| node.arguments.len() as u64 + u64::from(node.opcode == 22))
        .sum::<u64>();
    let observed_steps = recipes.values().map(|recipe| recipe.primitive_steps).max();
    let observed_scratch = recipes
        .values()
        .map(|recipe| recipe.peak_scratch_bytes)
        .max();
    if cursor != raw.len()
        || observed_nodes != total_nodes
        || observed_edges != total_edges
        || observed_steps != Some(maximum_steps)
        || observed_scratch != Some(peak_scratch)
    {
        return Err(recipe_error());
    }
    Ok(RecipePackage {
        profile_version: expected_profile_version,
        tables,
        recipes,
        maximum_primitive_steps: maximum_steps,
        peak_scratch_bytes: peak_scratch,
    })
}

fn uint(value: &RecipeValue) -> Option<(u32, u64)> {
    match value {
        RecipeValue::Uint { width, value } => Some((*width, *value)),
        _ => None,
    }
}

fn unpack_bits(width: u32, packed: &[u8]) -> Option<Vec<u8>> {
    if packed.len() != usize::try_from(u64::from(width).div_ceil(8)).ok()? {
        return None;
    }
    let mut result = Vec::with_capacity(width as usize);
    for index in 0..width as usize {
        result.push((packed[index / 8] >> (7 - index % 8)) & 1);
    }
    if width % 8 != 0 && packed.last()? & ((1_u8 << (8 - width % 8)) - 1) != 0 {
        return None;
    }
    Some(result)
}

fn pack_bits(bits: &[u8]) -> Option<Vec<u8>> {
    if bits.iter().any(|bit| *bit > 1) {
        return None;
    }
    let mut packed = vec![0_u8; bits.len().div_ceil(8)];
    for (index, bit) in bits.iter().copied().enumerate() {
        packed[index / 8] |= bit << (7 - index % 8);
    }
    Some(packed)
}

fn value_units(value: &RecipeValue) -> Option<Vec<u8>> {
    match value {
        RecipeValue::Uint { width, value } => {
            if !fits_width(*value, *width) {
                return None;
            }
            Some(
                (0..*width)
                    .map(|index| ((value >> (*width - index - 1)) & 1) as u8)
                    .collect(),
            )
        }
        RecipeValue::Bool(value) => Some(vec![u8::from(*value)]),
        RecipeValue::Bits { width, packed } => unpack_bits(*width, packed),
        RecipeValue::Bytes(value) => Some(value.clone()),
        RecipeValue::Status(value) if *value <= 14 => Some(
            (0..16)
                .map(|index| ((value >> (15 - index)) & 1) as u8)
                .collect(),
        ),
        _ => None,
    }
}

fn units_value(descriptor: &Descriptor, units: &[u8]) -> Option<RecipeValue> {
    if units.len() != usize::try_from(descriptor.units().ok()?).ok()? {
        return None;
    }
    match descriptor.kind {
        RecipeType::Uint => {
            let mut value = 0_u64;
            for bit in units {
                if *bit > 1 {
                    return None;
                }
                value = value.checked_shl(1)? | u64::from(*bit);
            }
            Some(RecipeValue::Uint {
                width: descriptor.width,
                value,
            })
        }
        RecipeType::Bool if units.len() == 1 && units[0] <= 1 => {
            Some(RecipeValue::Bool(units[0] == 1))
        }
        RecipeType::Bool => None,
        RecipeType::Bits => Some(RecipeValue::Bits {
            width: descriptor.width,
            packed: pack_bits(units)?,
        }),
        RecipeType::Bytes => Some(RecipeValue::Bytes(units.to_vec())),
        RecipeType::Status => {
            let mut value = 0_u16;
            for bit in units {
                if *bit > 1 {
                    return None;
                }
                value = value.checked_shl(1)? | u16::from(*bit);
            }
            (value <= 14).then_some(RecipeValue::Status(value))
        }
        RecipeType::Table => None,
    }
}

fn bits_binary(left: &RecipeValue, right: &RecipeValue, opcode: u8) -> Option<RecipeValue> {
    let RecipeValue::Bits {
        width,
        packed: left,
    } = left
    else {
        return None;
    };
    let RecipeValue::Bits {
        width: right_width,
        packed: right,
    } = right
    else {
        return None;
    };
    if width != right_width || left.len() != right.len() {
        return None;
    }
    let packed = left
        .iter()
        .zip(right)
        .map(|(left, right)| match opcode {
            11 => left & right,
            12 => left | right,
            13 => left ^ right,
            _ => unreachable!(),
        })
        .collect::<Vec<_>>();
    decode_scalar(RecipeType::Bits, *width, &packed).ok()
}

fn runtime_failure(status: u16) -> RecipeOutcome {
    RecipeOutcome {
        status,
        outputs: Vec::new(),
    }
}

fn evaluate_inner(
    package: &RecipePackage,
    recipe: &Recipe,
    inputs: &[RecipeValue],
) -> RecipeOutcome {
    if inputs.len() != recipe.inputs.len()
        || inputs.iter().zip(&recipe.inputs).any(|(value, expected)| {
            value_descriptor(value, expected.value_id)
                .map(|observed| !observed.same_shape(expected))
                .unwrap_or(true)
        })
    {
        return runtime_failure(3);
    }
    let mut values = inputs.to_vec();
    let mut outputs = recipe
        .outputs
        .iter()
        .map(|descriptor| {
            descriptor
                .units()
                .ok()
                .and_then(|length| usize::try_from(length).ok())
                .map(|length| vec![None; length])
        })
        .collect::<Option<Vec<_>>>();
    let Some(ref mut outputs) = outputs else {
        return runtime_failure(11);
    };
    for node in &recipe.nodes {
        let arguments = node
            .arguments
            .iter()
            .map(|id| values.get(usize::from(*id - 1)).cloned())
            .collect::<Option<Vec<_>>>();
        let Some(arguments) = arguments else {
            return runtime_failure(11);
        };
        if node.opcode == 22 {
            let Some(body) = package.recipes.get(&node.auxiliary_u16) else {
                return runtime_failure(11);
            };
            let mut accumulator = arguments[0].clone();
            for index in 0..node.immediate {
                let result = evaluate_inner(
                    package,
                    body,
                    &[
                        accumulator,
                        RecipeValue::Uint {
                            width: 64,
                            value: index,
                        },
                    ],
                );
                if result.status != 0 {
                    return result;
                }
                let Some(next) = result.outputs.into_iter().next() else {
                    return runtime_failure(11);
                };
                accumulator = next;
            }
            values.push(accumulator);
            continue;
        }
        let produced = (|| -> Option<RecipeValue> {
            match node.opcode {
                1 => match node.output.kind {
                    RecipeType::Uint => Some(RecipeValue::Uint {
                        width: node.output.width,
                        value: node.immediate,
                    }),
                    RecipeType::Bool => Some(RecipeValue::Bool(node.immediate == 1)),
                    RecipeType::Status => Some(RecipeValue::Status(node.immediate as u16)),
                    _ => None,
                },
                2 => package
                    .tables
                    .get(&node.auxiliary_u16)
                    .map(|table| RecipeValue::Table {
                        element_type: table.descriptor.element_type.unwrap(),
                        element_width: table.descriptor.width,
                        element_count: table.descriptor.count,
                        payload: Arc::clone(&table.payload),
                    }),
                3 => {
                    let (_, start) = uint(&arguments[1])?;
                    let (_, length) = uint(&arguments[2])?;
                    if length != u64::from(node.output.width) {
                        return None;
                    }
                    let start = usize::try_from(start).ok()?;
                    let length = usize::try_from(length).ok()?;
                    match &arguments[0] {
                        RecipeValue::Bits { width, packed } => {
                            let source = unpack_bits(*width, packed)?;
                            let selected = source.get(start..start.checked_add(length)?)?;
                            if node.output.kind == RecipeType::Uint {
                                units_value(&node.output, selected)
                            } else {
                                Some(RecipeValue::Bits {
                                    width: node.output.width,
                                    packed: pack_bits(selected)?,
                                })
                            }
                        }
                        RecipeValue::Bytes(source) => Some(RecipeValue::Bytes(
                            source.get(start..start.checked_add(length)?)?.to_vec(),
                        )),
                        _ => None,
                    }
                }
                4 => match (&arguments[0], &arguments[1]) {
                    (
                        RecipeValue::Uint {
                            width: left_width,
                            value: left,
                        },
                        RecipeValue::Uint {
                            width: right_width,
                            value: right,
                        },
                    ) => right
                        .checked_shl(*right_width)
                        .and_then(|_| left.checked_shl(*right_width))
                        .map(|value| RecipeValue::Uint {
                            width: left_width + right_width,
                            value: value | right,
                        }),
                    (
                        RecipeValue::Bits {
                            width: left_width,
                            packed: left,
                        },
                        RecipeValue::Bits {
                            width: right_width,
                            packed: right,
                        },
                    ) => {
                        let mut bits = unpack_bits(*left_width, left)?;
                        bits.extend(unpack_bits(*right_width, right)?);
                        Some(RecipeValue::Bits {
                            width: left_width + right_width,
                            packed: pack_bits(&bits)?,
                        })
                    }
                    (RecipeValue::Bytes(left), RecipeValue::Bytes(right)) => {
                        let mut value = left.clone();
                        value.extend_from_slice(right);
                        Some(RecipeValue::Bytes(value))
                    }
                    _ => None,
                },
                5 => {
                    let cells = value_units(&arguments[0])?;
                    let slot = outputs.get_mut(usize::from(node.auxiliary_u16 - 1))?;
                    let start = usize::try_from(node.immediate).ok()?;
                    let target = slot.get_mut(start..start.checked_add(cells.len())?)?;
                    if target.iter().any(Option::is_some) {
                        None
                    } else {
                        for (target, cell) in target.iter_mut().zip(cells) {
                            *target = Some(cell);
                        }
                        Some(RecipeValue::Status(0))
                    }
                }
                6..=10 => {
                    let (width, left) = uint(&arguments[0])?;
                    let (_, right) = uint(&arguments[1])?;
                    let value = match node.opcode {
                        6 => left.checked_add(right),
                        7 => left.checked_sub(right),
                        8 => left.checked_mul(right),
                        9 => left.checked_div(right),
                        10 => left.checked_rem(right),
                        _ => unreachable!(),
                    }?;
                    fits_width(value, width).then_some(RecipeValue::Uint { width, value })
                }
                11..=13 => match (&arguments[0], &arguments[1]) {
                    (
                        RecipeValue::Uint { width, value: left },
                        RecipeValue::Uint { value: right, .. },
                    ) => Some(RecipeValue::Uint {
                        width: *width,
                        value: match node.opcode {
                            11 => left & right,
                            12 => left | right,
                            13 => left ^ right,
                            _ => unreachable!(),
                        },
                    }),
                    (left, right) => bits_binary(left, right, node.opcode),
                },
                14 => {
                    let (width, value) = uint(&arguments[0])?;
                    Some(RecipeValue::Uint {
                        width,
                        value: value & node.immediate,
                    })
                }
                15 | 16 => {
                    let (width, value) = uint(&arguments[0])?;
                    let (_, shift) = uint(&arguments[1])?;
                    let shift = u32::try_from(shift).ok()?;
                    if shift >= width {
                        None
                    } else if node.opcode == 15 {
                        value.checked_shl(shift).and_then(|value| {
                            fits_width(value, width).then_some(RecipeValue::Uint { width, value })
                        })
                    } else {
                        Some(RecipeValue::Uint {
                            width,
                            value: value >> shift,
                        })
                    }
                }
                17 => Some(RecipeValue::Bool(arguments[0] == arguments[1])),
                18 => {
                    let (_, left) = uint(&arguments[0])?;
                    let (_, right) = uint(&arguments[1])?;
                    Some(RecipeValue::Bool(left < right))
                }
                19 | 21 => {
                    let (_, index) = uint(&arguments[1])?;
                    let index = usize::try_from(index).ok()?;
                    match &arguments[0] {
                        RecipeValue::Bits { width, packed } if node.opcode == 19 => {
                            unpack_bits(*width, packed).and_then(|bits| {
                                bits.get(index).map(|bit| RecipeValue::Bool(*bit == 1))
                            })
                        }
                        RecipeValue::Bytes(value) if node.opcode == 19 => {
                            value.get(index).map(|byte| RecipeValue::Uint {
                                width: 8,
                                value: u64::from(*byte),
                            })
                        }
                        RecipeValue::Table {
                            element_type,
                            element_width,
                            element_count,
                            payload,
                        } => {
                            if index >= *element_count as usize {
                                None
                            } else {
                                let each = element_bytes(*element_type, *element_width).ok()?;
                                let start = index.checked_mul(each)?;
                                decode_scalar(
                                    *element_type,
                                    *element_width,
                                    payload.get(start..start.checked_add(each)?)?,
                                )
                                .ok()
                            }
                        }
                        _ => None,
                    }
                }
                20 => {
                    let (_, index) = uint(&arguments[1])?;
                    let index = usize::try_from(index).ok()?;
                    match (&arguments[0], &arguments[2]) {
                        (RecipeValue::Bits { width, packed }, RecipeValue::Bool(value)) => {
                            let mut bits = unpack_bits(*width, packed)?;
                            *bits.get_mut(index)? = u8::from(*value);
                            Some(RecipeValue::Bits {
                                width: *width,
                                packed: pack_bits(&bits)?,
                            })
                        }
                        (RecipeValue::Bytes(source), RecipeValue::Uint { value, .. }) => {
                            let mut result = source.clone();
                            *result.get_mut(index)? = u8::try_from(*value).ok()?;
                            Some(RecipeValue::Bytes(result))
                        }
                        _ => None,
                    }
                }
                22 => unreachable!(),
                23 => match arguments[0] {
                    RecipeValue::Bool(true) => Some(arguments[1].clone()),
                    RecipeValue::Bool(false) => Some(arguments[2].clone()),
                    _ => None,
                },
                24 => Some(RecipeValue::Status(0)),
                25 => Some(RecipeValue::Status(node.immediate as u16)),
                _ => None,
            }
        })();
        let Some(produced) = produced else {
            return runtime_failure(11);
        };
        values.push(produced);
    }
    let completed = outputs
        .iter()
        .zip(&recipe.outputs)
        .map(|(cells, descriptor)| {
            let cells = cells.iter().copied().collect::<Option<Vec<_>>>()?;
            units_value(descriptor, &cells)
        })
        .collect::<Option<Vec<_>>>();
    let Some(mut completed) = completed else {
        return runtime_failure(11);
    };
    let RecipeValue::Status(status) = completed.remove(0) else {
        return runtime_failure(11);
    };
    if status == 0 {
        RecipeOutcome {
            status,
            outputs: completed,
        }
    } else {
        runtime_failure(status)
    }
}

/// Evaluate one fully validated recipe atomically.
pub fn evaluate_recipe(
    package: &RecipePackage,
    recipe_id: u16,
    inputs: &[RecipeValue],
) -> Result<RecipeOutcome> {
    if !(1..=7).contains(&package.profile_version) {
        return Err(recipe_error());
    }
    evaluate_validated_recipe(package, recipe_id, inputs)
}

pub(super) fn evaluate_validated_recipe(
    package: &RecipePackage,
    recipe_id: u16,
    inputs: &[RecipeValue],
) -> Result<RecipeOutcome> {
    let recipe = package.recipes.get(&recipe_id).ok_or_else(recipe_error)?;
    if inputs.len() != recipe.inputs.len()
        || inputs.iter().zip(&recipe.inputs).any(|(value, expected)| {
            value_descriptor(value, expected.value_id)
                .map(|observed| !observed.same_shape(expected))
                .unwrap_or(true)
        })
    {
        return Err(recipe_error());
    }
    Ok(evaluate_inner(package, recipe, inputs))
}

fn encode_serialized_value(value: &RecipeValue) -> Result<Vec<u8>> {
    Ok(match value {
        RecipeValue::Uint { width, value } => {
            let length = usize::try_from(width.div_ceil(8)).map_err(|_| recipe_error())?;
            value.to_be_bytes()[8 - length..].to_vec()
        }
        RecipeValue::Bool(value) => vec![u8::from(*value)],
        RecipeValue::Bits { width, packed } => {
            if packed.len() != usize::try_from(width.div_ceil(8)).map_err(|_| recipe_error())? {
                return Err(recipe_error());
            }
            packed.clone()
        }
        RecipeValue::Bytes(value) => value.clone(),
        RecipeValue::Status(value) => value.to_be_bytes().to_vec(),
        RecipeValue::Table { .. } => return Err(recipe_error()),
    })
}

/// Decode a recipe's exact serialized interface input, evaluate the promoted
/// interpreter, and return `STATUS[16]` followed by successful output slots.
/// This is the candidate-neutral route WORKED/HELD validation entry point.
pub fn evaluate_serialized_recipe(
    package: &RecipePackage,
    recipe_id: u16,
    input: &[u8],
) -> Result<Vec<u8>> {
    if !(1..=7).contains(&package.profile_version) {
        return Err(recipe_error());
    }
    evaluate_serialized_validated_recipe(package, recipe_id, input)
}

pub(super) fn evaluate_serialized_validated_recipe(
    package: &RecipePackage,
    recipe_id: u16,
    input: &[u8],
) -> Result<Vec<u8>> {
    let recipe = package.recipes.get(&recipe_id).ok_or_else(recipe_error)?;
    let mut offset = 0_usize;
    let mut values = Vec::with_capacity(recipe.inputs.len());
    for descriptor in &recipe.inputs {
        if descriptor.count != 1 || descriptor.kind == RecipeType::Table {
            return Err(recipe_error());
        }
        let length = element_bytes(descriptor.kind, descriptor.width)?;
        let end = offset.checked_add(length).ok_or_else(recipe_error)?;
        let raw = input.get(offset..end).ok_or_else(recipe_error)?;
        values.push(decode_scalar(descriptor.kind, descriptor.width, raw)?);
        offset = end;
    }
    if offset != input.len() {
        return Err(recipe_error());
    }
    let outcome = evaluate_validated_recipe(package, recipe_id, &values)?;
    let mut output = outcome.status.to_be_bytes().to_vec();
    if outcome.status == 0 {
        for value in &outcome.outputs {
            output.extend(encode_serialized_value(value)?);
        }
    }
    Ok(output)
}
