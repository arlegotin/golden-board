//! Candidate-specific programs expressed only in the frozen generic recipe VM.
//!
//! This module constructs bytes; the normal `recipe` parser remains the sole
//! authority that admits and executes them.  No codec operation is added to
//! the VM.

use crate::recipe::{
    RecipeOutcome, RecipePackage, RecipeValue, decode_recipe_package, evaluate_recipe,
};
use crate::{BootstrapError, Result};
use sha2::{Digest, Sha256};

const UINT: u8 = 0;
const BOOL: u8 = 1;
const BYTES: u8 = 3;
const TABLE: u8 = 4;
const STATUS: u8 = 5;

const OP_CONST: u8 = 1;
const OP_TABLE: u8 = 2;
const OP_SLICE: u8 = 3;
const OP_CONCAT: u8 = 4;
const OP_EMIT: u8 = 5;
const OP_ADD: u8 = 6;
const OP_SUB: u8 = 7;
const OP_MUL: u8 = 8;
const OP_QUOT: u8 = 9;
const OP_REM: u8 = 10;
const OP_AND: u8 = 11;
const OP_XOR: u8 = 13;
const OP_MASK: u8 = 14;
const OP_SHL: u8 = 15;
const OP_SHR: u8 = 16;
const OP_EQ: u8 = 17;
const OP_LT: u8 = 18;
const OP_READ: u8 = 19;
const OP_WRITE: u8 = 20;
const OP_LOOKUP: u8 = 21;
const OP_ITERATE: u8 = 22;
const OP_SELECT: u8 = 23;
const OP_SUCCESS: u8 = 24;
const OP_FAILURE: u8 = 25;

const STATE_BYTES: u32 = 1_536;
const POSITIONS: u16 = 255;
const SYNDROMES: u16 = 765;
const GAMMA: u16 = 829;
const TRANSFORMED: u16 = 894;
const CONNECTION: u16 = 958;
const PRIOR_CONNECTION: u16 = 991;
const LOCATOR: u16 = 1_057;
const EVALUATOR: u16 = 1_122;
const DERIVATIVE: u16 = 1_186;
const CORRECTION_POSITIONS: u16 = 1_250;
const CORRECTION_MAGNITUDES: u16 = 1_314;
const ROOT_IS_ERASURE: u16 = 1_378;

const ERASURE_COUNT: u16 = 1_442;
const POINT: u16 = 1_444;
const ACCUMULATOR: u16 = 1_445;
const LOCATION: u16 = 1_446;
const OUTER_INDEX: u16 = 1_447;
const DISCREPANCY: u16 = 1_448;
const SCALE: u16 = 1_449;
const CONNECTION_DEGREE: u16 = 1_450;
const BM_SHIFT: u16 = 1_451;
const PRIOR_DISCREPANCY: u16 = 1_452;
const OBSERVED_DEGREE: u16 = 1_453;
const ROOT_COUNT: u16 = 1_454;
const TARGET_POSITION: u16 = 1_455;
const FOUND: u16 = 1_456;
const ERROR_COUNT: u16 = 1_457;
const EVALUATOR_ACCUMULATOR: u16 = 1_458;
const DERIVATIVE_ACCUMULATOR: u16 = 1_459;
#[cfg(test)]
const LOOP_COUNTER_0: u16 = 1_460;
const GF_LEFT: u16 = 1_463;
const GF_RIGHT: u16 = 1_464;
const GF_PRODUCT: u16 = 1_465;
const INV_PRODUCT: u16 = 1_466;
const INV_BASE: u16 = 1_467;
const INV_EXPONENT: u16 = 1_468;
const CURRENT_IS_ERASURE: u16 = 1_469;

const TABLE_EXP: u16 = 1;
const TABLE_LOG: u16 = 2;
const TABLE_WIDEN: u16 = 3;
const TABLE_ZERO_BYTE: u16 = 4;
const TABLE_BYTE_IDENTITY: u16 = 5;

const TABLE_EH_CODE_BYTE: u16 = 10;
const TABLE_EH_CODE_SHIFT: u16 = 11;
const TABLE_EH_POSITION: u16 = 12;
const TABLE_EH_DATA_ACTIVE: u16 = 13;
const TABLE_EH_DATA_BYTE: u16 = 14;
const TABLE_EH_DATA_SHIFT: u16 = 15;
const TABLE_EH_FILL_LIMIT: u16 = 18;
const TABLE_BITS_NOT_MASK: u16 = 19;
const TABLE_D4_FLAGS: u16 = 20;
const TABLE_R3_SLOT_MULTIPLIER: u16 = 17;
const TABLE_R3_POPCOUNT5: u16 = 22;

const EH_POSITIONS: u16 = 9;
const EH_SYNDROME: u16 = 12;
const EH_PARITY: u16 = 13;
const EH_COUNT: u16 = 14;
const EH_FOUND_COUNT: u16 = 15;
const EH_CHOSEN_FILL: u16 = 16;
const EH_CHOSEN_FLIP: u16 = 17;
const EH_OUTPUT: u16 = 18;

const BODY_GF_ROUND: u16 = 1;
const BODY_INV_ROUND: u16 = 2;
const BODY_VALIDATE_ERASURE: u16 = 3;
const BODY_ERASURE_BOUNDARY: u16 = 4;
const BODY_SYNDROME_BYTE: u16 = 5;
const BODY_SYNDROME: u16 = 6;
const BODY_GAMMA_UPDATE: u16 = 7;
const BODY_TRANSFORM_SHIFT: u16 = 8;
const BODY_ERASURE_LOCATOR: u16 = 9;
const BODY_BM_DISCREPANCY: u16 = 10;
const BODY_BM_CONNECTION: u16 = 11;
const BODY_BM: u16 = 13;
const BODY_CONNECTION_DEGREE: u16 = 14;
const BODY_LOCATOR_CONVOLUTION: u16 = 15;
const BODY_LOCATOR: u16 = 16;
const BODY_LOCATOR_DEGREE: u16 = 17;
const BODY_CHIEN_EVALUATE: u16 = 18;
const BODY_CHIEN: u16 = 19;
const BODY_ERASURE_ROOT_SEARCH: u16 = 20;
const BODY_ERASURE_ROOT: u16 = 21;
const BODY_EVALUATOR_CONVOLUTION: u16 = 22;
const BODY_EVALUATOR: u16 = 23;
const BODY_DERIVATIVE: u16 = 24;
const BODY_MAGNITUDE_EVALUATE: u16 = 25;
const BODY_MAGNITUDE: u16 = 26;
const BODY_APPLY: u16 = 27;
const BODY_CORRECTION_SYNDROME: u16 = 28;
const BODY_CORRECTION_SYNDROMES: u16 = 29;
const RECIPE_RS_DECODE: u16 = 30;

const BODY_EH_SCAN: u16 = 1;
const BODY_EH_VALIDATE: u16 = 2;
const BODY_EH_CANDIDATE: u16 = 3;
const BODY_EH_OUTPUT: u16 = 4;
const RECIPE_EH_DECODE: u16 = 30;
const BODY_CRC32C_BIT: u16 = 90;
const BODY_CRC32C_BYTE: u16 = 92;
const BODY_CRC64_BYTE: u16 = 93;
const BODY_EH_PARITY: u16 = 99;
const BODY_EH_ENCODE: u16 = 100;
const RECIPE_TRANSPORT_ENCODE: u16 = 108;

const CRC_VALUE: u16 = 32;
const CRC_BYTE: u16 = 40;
const CRC_MODE: u16 = 41;

#[derive(Clone, Copy)]
struct Shape {
    kind: u8,
    width: u32,
}

impl Shape {
    const fn uint(width: u32) -> Self {
        Self { kind: UINT, width }
    }

    const fn bytes(width: u32) -> Self {
        Self { kind: BYTES, width }
    }

    const fn status() -> Self {
        Self {
            kind: STATUS,
            width: 16,
        }
    }

    fn storage(self) -> u64 {
        if self.kind == TABLE {
            0
        } else if self.kind == BYTES {
            u64::from(self.width)
        } else {
            u64::from(self.width).div_ceil(8)
        }
    }
}

#[derive(Clone)]
struct Node {
    opcode: u8,
    shape: Shape,
    arguments: Vec<u16>,
    auxiliary: u16,
    immediate: u64,
}

struct RecipeBuilder {
    id: u16,
    inputs: Vec<Shape>,
    outputs: Vec<Shape>,
    nodes: Vec<Node>,
    table_values: std::collections::BTreeMap<u16, u16>,
    constant_values: std::collections::BTreeMap<(u8, u32, u64), u16>,
    status_values: std::collections::BTreeMap<u16, u16>,
}

impl RecipeBuilder {
    fn custom(id: u16, inputs: Vec<Shape>, outputs: Vec<Shape>) -> Self {
        Self {
            id,
            inputs,
            outputs,
            nodes: Vec::new(),
            table_values: std::collections::BTreeMap::new(),
            constant_values: std::collections::BTreeMap::new(),
            status_values: std::collections::BTreeMap::new(),
        }
    }

    fn body(id: u16) -> Self {
        Self::custom(
            id,
            vec![Shape::bytes(STATE_BYTES), Shape::uint(64)],
            vec![Shape::status(), Shape::bytes(STATE_BYTES)],
        )
    }

    fn main(id: u16) -> Self {
        Self::custom(
            id,
            vec![Shape::bytes(255), Shape::bytes(1), Shape::bytes(64)],
            vec![Shape::status(), Shape::bytes(191)],
        )
    }

    fn push(
        &mut self,
        opcode: u8,
        shape: Shape,
        arguments: &[u16],
        auxiliary: u16,
        immediate: u64,
    ) -> u16 {
        self.nodes.push(Node {
            opcode,
            shape,
            arguments: arguments.to_vec(),
            auxiliary,
            immediate,
        });
        u16::try_from(self.inputs.len() + self.nodes.len()).expect("bounded recipe value ID")
    }

    fn constant(&mut self, width: u32, value: u64) -> u16 {
        let key = (UINT, width, value);
        if let Some(existing) = self.constant_values.get(&key) {
            return *existing;
        }
        let result = self.push(OP_CONST, Shape::uint(width), &[], 0, value);
        self.constant_values.insert(key, result);
        result
    }

    fn boolean(&mut self, value: bool) -> u16 {
        let immediate = u64::from(value);
        let key = (BOOL, 1, immediate);
        if let Some(existing) = self.constant_values.get(&key) {
            return *existing;
        }
        let result = self.push(
            OP_CONST,
            Shape {
                kind: BOOL,
                width: 1,
            },
            &[],
            0,
            immediate,
        );
        self.constant_values.insert(key, result);
        result
    }

    fn status(&mut self, status: u16) -> u16 {
        if let Some(existing) = self.status_values.get(&status) {
            return *existing;
        }
        let result = if status == 0 {
            self.push(OP_SUCCESS, Shape::status(), &[], 0, 0)
        } else {
            self.push(OP_FAILURE, Shape::status(), &[], 0, u64::from(status))
        };
        self.status_values.insert(status, result);
        result
    }

    fn binary(&mut self, opcode: u8, shape: Shape, left: u16, right: u16) -> u16 {
        self.push(opcode, shape, &[left, right], 0, 0)
    }

    fn select(&mut self, shape: Shape, condition: u16, yes: u16, no: u16) -> u16 {
        self.push(OP_SELECT, shape, &[condition, yes, no], 0, 0)
    }

    fn equal(&mut self, left: u16, right: u16) -> u16 {
        self.push(
            OP_EQ,
            Shape {
                kind: BOOL,
                width: 1,
            },
            &[left, right],
            0,
            0,
        )
    }

    fn less(&mut self, left: u16, right: u16) -> u16 {
        self.push(
            OP_LT,
            Shape {
                kind: BOOL,
                width: 1,
            },
            &[left, right],
            0,
            0,
        )
    }

    fn bool_and(&mut self, left: u16, right: u16) -> u16 {
        let no = self.boolean(false);
        self.select(
            Shape {
                kind: BOOL,
                width: 1,
            },
            left,
            right,
            no,
        )
    }

    fn bool_or(&mut self, left: u16, right: u16) -> u16 {
        let yes = self.boolean(true);
        self.select(
            Shape {
                kind: BOOL,
                width: 1,
            },
            left,
            yes,
            right,
        )
    }

    fn bool_not(&mut self, value: u16) -> u16 {
        let no = self.boolean(false);
        self.equal(value, no)
    }

    fn less_or_equal(&mut self, left: u16, right: u16) -> u16 {
        let greater = self.less(right, left);
        self.bool_not(greater)
    }

    fn fixed_index(&mut self, offset: u16) -> u16 {
        self.constant(16, u64::from(offset))
    }

    fn table(&mut self, table: u16, element_width: u32) -> u16 {
        if let Some(value) = self.table_values.get(&table) {
            return *value;
        }
        let value = self.push(
            OP_TABLE,
            Shape {
                kind: TABLE,
                width: element_width,
            },
            &[],
            table,
            0,
        );
        self.table_values.insert(table, value);
        value
    }

    fn widen(&mut self, byte: u16) -> u16 {
        let table = self.table(TABLE_WIDEN, 16);
        self.push(OP_LOOKUP, Shape::uint(16), &[table, byte], 0, 0)
    }

    fn iteration_byte(&mut self) -> u16 {
        let table = self.table(TABLE_BYTE_IDENTITY, 8);
        self.push(OP_LOOKUP, Shape::uint(8), &[table, 2], 0, 0)
    }

    fn offset_index(&mut self, offset: u16, byte: u16) -> u16 {
        let widened = self.widen(byte);
        let base = self.constant(16, u64::from(offset));
        self.binary(OP_ADD, Shape::uint(16), base, widened)
    }

    fn read(&mut self, state: u16, index: u16) -> u16 {
        self.push(OP_READ, Shape::uint(8), &[state, index], 0, 0)
    }

    fn read_fixed(&mut self, state: u16, offset: u16) -> u16 {
        let index = self.fixed_index(offset);
        self.read(state, index)
    }

    fn read_offset(&mut self, state: u16, offset: u16, byte: u16) -> u16 {
        let index = self.offset_index(offset, byte);
        self.read(state, index)
    }

    fn iteration_index(&mut self, offset: u16) -> u16 {
        if offset == 0 {
            2
        } else {
            let base = self.constant(64, u64::from(offset));
            self.binary(OP_ADD, Shape::uint(64), base, 2)
        }
    }

    fn read_iteration(&mut self, state: u16, offset: u16) -> u16 {
        let index = self.iteration_index(offset);
        self.read(state, index)
    }

    fn write(&mut self, state: u16, index: u16, value: u16) -> u16 {
        self.push(
            OP_WRITE,
            Shape::bytes(STATE_BYTES),
            &[state, index, value],
            0,
            0,
        )
    }

    fn write_fixed(&mut self, state: u16, offset: u16, value: u16) -> u16 {
        let index = self.fixed_index(offset);
        self.write(state, index, value)
    }

    fn write_offset(&mut self, state: u16, offset: u16, byte: u16, value: u16) -> u16 {
        let index = self.offset_index(offset, byte);
        self.write(state, index, value)
    }

    fn write_iteration(&mut self, state: u16, offset: u16, value: u16) -> u16 {
        let index = self.iteration_index(offset);
        self.write(state, index, value)
    }

    fn read_uint(&mut self, state: u16, offset: u16, bytes: u16) -> u16 {
        let mut value = self.read_fixed(state, offset);
        let mut width = 8_u32;
        for index in 1..bytes {
            let next = self.read_fixed(state, offset + index);
            width += 8;
            value = self.push(OP_CONCAT, Shape::uint(width), &[value, next], 0, 0);
        }
        value
    }

    fn write_uint(&mut self, mut state: u16, offset: u16, bytes: u16, value: u16) -> u16 {
        let width = u32::from(bytes) * 8;
        let identity = self.table(TABLE_BYTE_IDENTITY, 8);
        for index in 0..bytes {
            let shift_amount = u32::from(bytes - index - 1) * 8;
            let shifted = if shift_amount == 0 {
                value
            } else {
                let shift = self.constant(width, u64::from(shift_amount));
                self.binary(OP_SHR, Shape::uint(width), value, shift)
            };
            let masked = self.push(OP_MASK, Shape::uint(width), &[shifted], 0, 0xff);
            let byte = self.push(OP_LOOKUP, Shape::uint(8), &[identity, masked], 0, 0);
            state = self.write_fixed(state, offset + index, byte);
        }
        state
    }

    fn iterate(&mut self, state: u16, body: u16, count: u64) -> u16 {
        self.push(OP_ITERATE, Shape::bytes(STATE_BYTES), &[state], body, count)
    }

    fn zero_bytes(&mut self, length: u16) -> u16 {
        let table = self.table(TABLE_ZERO_BYTE, 1);
        let zero = self.constant(8, 0);
        let first = self.push(OP_LOOKUP, Shape::bytes(1), &[table, zero], 0, 0);
        let mut powers = vec![(1_u16, first)];
        while powers.last().expect("initial power").0 <= length / 2 {
            let (width, value) = *powers.last().expect("initial power");
            let doubled = self.push(
                OP_CONCAT,
                Shape::bytes(u32::from(width) * 2),
                &[value, value],
                0,
                0,
            );
            powers.push((width * 2, doubled));
        }
        let mut remaining = length;
        let mut output = None;
        for (width, value) in powers.into_iter().rev() {
            if width <= remaining {
                output = Some(match output {
                    None => value,
                    Some(prefix) => self.push(
                        OP_CONCAT,
                        Shape::bytes(u32::from(length - remaining + width)),
                        &[prefix, value],
                        0,
                        0,
                    ),
                });
                remaining -= width;
            }
        }
        assert_eq!(remaining, 0);
        output.expect("positive zero length")
    }

    fn alpha(&mut self, exponent: u16) -> u16 {
        let table = self.table(TABLE_EXP, 8);
        self.push(OP_LOOKUP, Shape::uint(8), &[table, exponent], 0, 0)
    }

    fn gf_multiply(&mut self, state: u16, left: u16, right: u16) -> (u16, u16) {
        let log_table = self.table(TABLE_LOG, 16);
        let left_log = self.push(OP_LOOKUP, Shape::uint(16), &[log_table, left], 0, 0);
        let right_log = self.push(OP_LOOKUP, Shape::uint(16), &[log_table, right], 0, 0);
        let exponent = self.binary(OP_ADD, Shape::uint(16), left_log, right_log);
        let exp_table = self.table(TABLE_EXP, 8);
        let product = self.push(OP_LOOKUP, Shape::uint(8), &[exp_table, exponent], 0, 0);
        (state, product)
    }

    fn gf_inverse(&mut self, state: u16, value: u16) -> (u16, u16) {
        let log_table = self.table(TABLE_LOG, 16);
        let logarithm = self.push(OP_LOOKUP, Shape::uint(16), &[log_table, value], 0, 0);
        let maximum = self.constant(16, 255);
        let exponent = self.binary(OP_SUB, Shape::uint(16), maximum, logarithm);
        let inverse = self.alpha(exponent);
        (state, inverse)
    }

    fn finish_body(&mut self, status: u16, state: u16) {
        self.push(OP_EMIT, Shape::status(), &[status], 1, 0);
        self.push(OP_EMIT, Shape::status(), &[state], 2, 0);
    }

    fn finish_main(&mut self, status: u16, output: u16) {
        self.push(OP_EMIT, Shape::status(), &[status], 1, 0);
        self.push(OP_EMIT, Shape::status(), &[output], 2, 0);
    }

    fn finish_outputs(&mut self, status: u16, outputs: &[u16]) {
        self.push(OP_EMIT, Shape::status(), &[status], 1, 0);
        for (index, output) in outputs.iter().copied().enumerate() {
            self.push(OP_EMIT, Shape::status(), &[output], (index + 2) as u16, 0);
        }
    }
}

struct BuiltRecipe {
    builder: RecipeBuilder,
    edges: u64,
    steps: u64,
    scratch: u64,
}

fn finalize(builder: RecipeBuilder, earlier: &[BuiltRecipe]) -> BuiltRecipe {
    let edges = builder
        .nodes
        .iter()
        .map(|node| node.arguments.len() as u64 + u64::from(node.opcode == OP_ITERATE))
        .sum();
    let steps = builder
        .nodes
        .iter()
        .map(|node| {
            if node.opcode == OP_ITERATE {
                let body = earlier
                    .iter()
                    .find(|recipe| recipe.builder.id == node.auxiliary)
                    .expect("lower recipe");
                1 + node.immediate * body.steps
            } else {
                1
            }
        })
        .sum();
    let input_count = builder.inputs.len() as u16;
    let mut last_use = vec![None; builder.nodes.len()];
    for (index, node) in builder.nodes.iter().enumerate() {
        for argument in &node.arguments {
            if *argument > input_count {
                last_use[usize::from(*argument - input_count - 1)] = Some(index);
            }
        }
    }
    let mut live = 0_u64;
    let mut scratch = 0_u64;
    for (index, node) in builder.nodes.iter().enumerate() {
        let storage = node.shape.storage();
        scratch = scratch.max(live + storage);
        if node.opcode == OP_ITERATE {
            let body = earlier
                .iter()
                .find(|recipe| recipe.builder.id == node.auxiliary)
                .expect("lower recipe");
            scratch = scratch.max(live + body.scratch);
        }
        live += storage;
        for argument in node
            .arguments
            .iter()
            .copied()
            .collect::<std::collections::BTreeSet<_>>()
        {
            if argument > input_count {
                let argument_index = usize::from(argument - input_count - 1);
                if last_use[argument_index] == Some(index) {
                    live -= builder.nodes[argument_index].shape.storage();
                }
            }
        }
        if last_use[index].is_none() {
            live -= storage;
        }
    }
    BuiltRecipe {
        builder,
        edges,
        steps,
        scratch,
    }
}

fn put_u16(target: &mut [u8], offset: usize, value: u16) {
    target[offset..offset + 2].copy_from_slice(&value.to_be_bytes());
}

fn put_u32(target: &mut [u8], offset: usize, value: u32) {
    target[offset..offset + 4].copy_from_slice(&value.to_be_bytes());
}

fn put_u64(target: &mut [u8], offset: usize, value: u64) {
    target[offset..offset + 8].copy_from_slice(&value.to_be_bytes());
}

fn descriptor(target: &mut [u8], offset: usize, value_id: u16, shape: Shape) {
    put_u16(target, offset, value_id);
    target[offset + 2] = shape.kind;
    put_u32(target, offset + 4, shape.width);
    put_u32(target, offset + 8, 1);
}

fn encode_recipe(recipe: &BuiltRecipe) -> Vec<u8> {
    let builder = &recipe.builder;
    let bytes = 32 + 12 * (builder.inputs.len() + builder.outputs.len()) + 32 * builder.nodes.len();
    let mut raw = vec![0; bytes];
    put_u16(&mut raw, 0, builder.id);
    put_u16(&mut raw, 4, builder.inputs.len() as u16);
    put_u16(&mut raw, 6, builder.outputs.len() as u16);
    put_u32(&mut raw, 8, builder.nodes.len() as u32);
    put_u32(&mut raw, 12, recipe.edges as u32);
    put_u64(&mut raw, 16, recipe.steps);
    put_u32(&mut raw, 24, recipe.scratch as u32);
    put_u32(&mut raw, 28, bytes as u32);
    let mut cursor = 32;
    for (index, shape) in builder.inputs.iter().copied().enumerate() {
        descriptor(&mut raw, cursor, (index + 1) as u16, shape);
        cursor += 12;
    }
    for (index, shape) in builder.outputs.iter().copied().enumerate() {
        descriptor(&mut raw, cursor, (index + 1) as u16, shape);
        cursor += 12;
    }
    for (index, node) in builder.nodes.iter().enumerate() {
        put_u16(&mut raw, cursor, (index + 1) as u16);
        raw[cursor + 2] = node.opcode;
        raw[cursor + 3] = node.shape.kind;
        put_u32(&mut raw, cursor + 4, node.shape.width);
        put_u16(&mut raw, cursor + 8, node.arguments.len() as u16);
        for (argument_index, argument) in node.arguments.iter().copied().enumerate() {
            put_u16(&mut raw, cursor + 10 + argument_index * 2, argument);
        }
        put_u16(&mut raw, cursor + 18, node.auxiliary);
        put_u64(&mut raw, cursor + 24, node.immediate);
        cursor += 32;
    }
    raw
}

fn exp_table() -> Vec<u8> {
    let mut table = (0..=508)
        .scan(1_u8, |value, exponent| {
            if exponent != 0 && exponent % 255 == 0 {
                *value = 1;
            }
            let current = *value;
            let carry = *value & 0x80 != 0;
            *value <<= 1;
            if carry {
                *value ^= 0x1d;
            }
            Some(current)
        })
        .collect::<Vec<_>>();
    table.resize(1_025, 0);
    table
}

fn log_table() -> Vec<u8> {
    let mut logarithms = [512_u16; 256];
    let mut value = 1_u8;
    for exponent in 0..255_u16 {
        logarithms[usize::from(value)] = exponent;
        let carry = value & 0x80 != 0;
        value <<= 1;
        if carry {
            value ^= 0x1d;
        }
    }
    logarithms.into_iter().flat_map(u16::to_be_bytes).collect()
}

fn widen_table() -> Vec<u8> {
    (0_u16..=255).flat_map(u16::to_be_bytes).collect()
}

fn byte_identity_table() -> Vec<u8> {
    (0_u8..=255).collect()
}

fn eh_code_byte_table() -> Vec<u8> {
    (0_u8..72).map(|index| index / 8).collect()
}

fn eh_code_shift_table() -> Vec<u8> {
    (0_u8..72).map(|index| 7 - index % 8).collect()
}

fn eh_position_table() -> Vec<u8> {
    (1_u8..=72)
        .map(|position| if position == 72 { 0 } else { position })
        .collect()
}

fn eh_data_mapping() -> (Vec<u8>, Vec<u8>, Vec<u8>) {
    let mut active = Vec::with_capacity(72);
    let mut bytes = Vec::with_capacity(72);
    let mut shifts = Vec::with_capacity(72);
    let mut data_bit = 0_u8;
    for position in 1_u8..=72 {
        let is_data = position <= 71 && !position.is_power_of_two();
        active.push(u8::from(is_data));
        bytes.push(if is_data { data_bit / 8 } else { 0 });
        shifts.push(if is_data { 7 - data_bit % 8 } else { 0 });
        if is_data {
            data_bit += 1;
        }
    }
    assert_eq!(data_bit, 64);
    (active, bytes, shifts)
}

fn eh_tables() -> Vec<EncodedTable> {
    let (data_active, data_bytes, data_shifts) = eh_data_mapping();
    vec![
        (TABLE_WIDEN, UINT, 16, 256, widen_table()),
        (TABLE_ZERO_BYTE, BYTES, 1, 1, vec![0]),
        (TABLE_BYTE_IDENTITY, UINT, 8, 256, byte_identity_table()),
        (TABLE_EH_CODE_BYTE, UINT, 8, 72, eh_code_byte_table()),
        (TABLE_EH_CODE_SHIFT, UINT, 8, 72, eh_code_shift_table()),
        (TABLE_EH_POSITION, UINT, 8, 72, eh_position_table()),
        (TABLE_EH_DATA_ACTIVE, UINT, 8, 72, data_active),
        (TABLE_EH_DATA_BYTE, UINT, 8, 72, data_bytes),
        (TABLE_EH_DATA_SHIFT, UINT, 8, 72, data_shifts),
        (TABLE_EH_FILL_LIMIT, UINT, 8, 4, vec![1, 2, 4, 8]),
        (TABLE_BITS_NOT_MASK, 2, 8, 1, vec![0xff]),
        (TABLE_D4_FLAGS, UINT, 8, 8, vec![0, 3, 6, 5, 4, 7, 2, 1]),
    ]
}

fn r3_gcd(mut left: u64, mut right: u64) -> u64 {
    while right != 0 {
        (left, right) = (right, left % right);
    }
    left
}

fn r3_toroidal_separation(delta: u64, side: u64) -> u64 {
    delta.min(side - delta)
}

fn r3_slot_multiplier_valid(candidate: u64, interior: u64) -> bool {
    let population = interior * interior;
    let slots = population / 1_728;
    if slots < 2 || r3_gcd(candidate, slots) != 1 {
        return false;
    }
    let window = 32.max(interior / 8);
    let cell_multiplier = 2 * interior - 1;
    for lane_delta in 1..=4_u64 {
        let wrapped = candidate * lane_delta % slots;
        for delta in [i128::from(wrapped), i128::from(wrapped) - i128::from(slots)] {
            let flat = (i128::from(cell_multiplier) * 1_728 * delta)
                .rem_euclid(i128::from(population)) as u64;
            let row = flat / interior;
            let column = flat % interior;
            let column_separation = r3_toroidal_separation(column, interior);
            let row_cases = if column == 0 {
                [row, row]
            } else {
                [row, (row + 1) % interior]
            };
            for row_delta in row_cases.into_iter().take(if column == 0 { 1 } else { 2 }) {
                if r3_toroidal_separation(row_delta, interior).max(column_separation) < window {
                    return false;
                }
            }
        }
    }
    true
}

/// Exact smallest-B table over the closed legal interior index domain.
/// Indices zero and 255 are reserved and deliberately zero.
pub fn r3_slot_multiplier_table() -> [u8; 256] {
    let mut table = [0_u8; 256];
    for (index, output) in table.iter_mut().enumerate().take(255).skip(1) {
        let interior = index as u64 * 8;
        let population = interior * interior;
        let slots = population / 1_728;
        if slots < 2 {
            continue;
        }
        if let Some(candidate) =
            (1..slots).find(|candidate| r3_slot_multiplier_valid(*candidate, interior))
        {
            *output = u8::try_from(candidate).expect("closed B table fits one byte");
        }
    }
    table
}

fn r3_eh_tables() -> Vec<EncodedTable> {
    let mut tables = eh_tables();
    tables.push((
        TABLE_R3_SLOT_MULTIPLIER,
        UINT,
        8,
        256,
        r3_slot_multiplier_table().to_vec(),
    ));
    tables.sort_by_key(|table| table.0);
    tables
}

type EncodedTable = (u16, u8, u32, u32, Vec<u8>);

fn rs_tables() -> Vec<EncodedTable> {
    vec![
        (TABLE_EXP, UINT, 8_u32, 1_025_u32, exp_table()),
        (TABLE_LOG, UINT, 16, 256, log_table()),
        (TABLE_WIDEN, UINT, 16, 256, widen_table()),
        (TABLE_ZERO_BYTE, BYTES, 1, 1, vec![0]),
        (TABLE_BYTE_IDENTITY, UINT, 8, 256, byte_identity_table()),
    ]
}

fn encode_package_with_tables(
    profile_version: u16,
    recipes: &[BuiltRecipe],
    tables: Vec<EncodedTable>,
) -> Vec<u8> {
    let table_bytes = tables
        .iter()
        .map(|(_, _, _, _, payload)| 16 + payload.len())
        .sum::<usize>();
    let encoded_recipes = recipes.iter().map(encode_recipe).collect::<Vec<_>>();
    let recipe_bytes = encoded_recipes.iter().map(Vec::len).sum::<usize>();
    let mut raw = vec![0; 64 + table_bytes + recipe_bytes];
    raw[..8].copy_from_slice(b"GBRECP0\0");
    put_u16(&mut raw, 12, profile_version);
    put_u16(&mut raw, 16, recipes.len() as u16);
    put_u16(&mut raw, 18, tables.len() as u16);
    put_u32(
        &mut raw,
        20,
        recipes
            .iter()
            .map(|recipe| recipe.builder.nodes.len() as u32)
            .sum(),
    );
    put_u32(
        &mut raw,
        24,
        recipes.iter().map(|recipe| recipe.edges as u32).sum(),
    );
    put_u32(
        &mut raw,
        28,
        tables
            .iter()
            .map(|(_, _, _, _, payload)| payload.len() as u32)
            .sum(),
    );
    let package_length = raw.len() as u32;
    put_u32(&mut raw, 32, package_length);
    put_u64(
        &mut raw,
        36,
        recipes.iter().map(|recipe| recipe.steps).max().unwrap(),
    );
    put_u32(
        &mut raw,
        44,
        recipes
            .iter()
            .map(|recipe| recipe.scratch as u32)
            .max()
            .unwrap(),
    );
    let mut cursor = 64;
    for (id, element_type, width, count, payload) in tables {
        put_u16(&mut raw, cursor, id);
        raw[cursor + 2] = element_type;
        put_u32(&mut raw, cursor + 4, width);
        put_u32(&mut raw, cursor + 8, count);
        put_u32(&mut raw, cursor + 12, payload.len() as u32);
        raw[cursor + 16..cursor + 16 + payload.len()].copy_from_slice(&payload);
        cursor += 16 + payload.len();
    }
    for recipe in encoded_recipes {
        raw[cursor..cursor + recipe.len()].copy_from_slice(&recipe);
        cursor += recipe.len();
    }
    raw
}

fn encode_package(profile_version: u16, recipes: &[BuiltRecipe]) -> Vec<u8> {
    encode_package_with_tables(profile_version, recipes, rs_tables())
}

fn gf_round() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_GF_ROUND);
    let state = 1;
    let left = recipe.read_fixed(state, GF_LEFT);
    let right = recipe.read_fixed(state, GF_RIGHT);
    let product = recipe.read_fixed(state, GF_PRODUCT);
    let one = recipe.constant(8, 1);
    let low = recipe.push(OP_MASK, Shape::uint(8), &[right], 0, 1);
    let low_is_one = recipe.equal(low, one);
    let zero = recipe.constant(8, 0);
    let selected_left = recipe.select(Shape::uint(8), low_is_one, left, zero);
    let product = recipe.binary(OP_XOR, Shape::uint(8), product, selected_left);
    let high_shift = recipe.constant(8, 7);
    let high = recipe.binary(OP_SHR, Shape::uint(8), left, high_shift);
    let high_is_one = recipe.equal(high, one);
    let masked = recipe.push(OP_MASK, Shape::uint(8), &[left], 0, 0x7f);
    let shift = recipe.constant(8, 1);
    let doubled = recipe.binary(OP_SHL, Shape::uint(8), masked, shift);
    let reduction = recipe.constant(8, 0x1d);
    let reduction = recipe.select(Shape::uint(8), high_is_one, reduction, zero);
    let left = recipe.binary(OP_XOR, Shape::uint(8), doubled, reduction);
    let right = recipe.binary(OP_SHR, Shape::uint(8), right, shift);
    let state = recipe.write_fixed(state, GF_LEFT, left);
    let state = recipe.write_fixed(state, GF_RIGHT, right);
    let state = recipe.write_fixed(state, GF_PRODUCT, product);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn inverse_round() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_INV_ROUND);
    let state = 1;
    let product = recipe.read_fixed(state, INV_PRODUCT);
    let base = recipe.read_fixed(state, INV_BASE);
    let exponent = recipe.read_fixed(state, INV_EXPONENT);
    let one = recipe.constant(8, 1);
    let bit = recipe.push(OP_MASK, Shape::uint(8), &[exponent], 0, 1);
    let bit = recipe.equal(bit, one);
    let (state, product_times_base) = recipe.gf_multiply(state, product, base);
    let product = recipe.select(Shape::uint(8), bit, product_times_base, product);
    let state = recipe.write_fixed(state, INV_PRODUCT, product);
    let (state, base) = recipe.gf_multiply(state, base, base);
    let state = recipe.write_fixed(state, INV_BASE, base);
    let shift = recipe.constant(8, 1);
    let exponent = recipe.binary(OP_SHR, Shape::uint(8), exponent, shift);
    let state = recipe.write_fixed(state, INV_EXPONENT, exponent);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn eh_scan() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_EH_SCAN);
    let state = 1;
    let byte_table = recipe.table(TABLE_EH_CODE_BYTE, 8);
    let byte_index = recipe.push(OP_LOOKUP, Shape::uint(8), &[byte_table, 2], 0, 0);
    let byte = recipe.read(state, byte_index);
    let shift_table = recipe.table(TABLE_EH_CODE_SHIFT, 8);
    let shift = recipe.push(OP_LOOKUP, Shape::uint(8), &[shift_table, 2], 0, 0);
    let shifted = recipe.binary(OP_SHR, Shape::uint(8), byte, shift);
    let bit = recipe.push(OP_MASK, Shape::uint(8), &[shifted], 0, 1);
    let position_table = recipe.table(TABLE_EH_POSITION, 8);
    let position = recipe.push(OP_LOOKUP, Shape::uint(8), &[position_table, 2], 0, 0);
    let zero = recipe.constant(8, 0);
    let one = recipe.constant(8, 1);
    let set = recipe.equal(bit, one);
    let contribution = recipe.select(Shape::uint(8), set, position, zero);
    let syndrome = recipe.read_fixed(state, EH_SYNDROME);
    let syndrome = recipe.binary(OP_XOR, Shape::uint(8), syndrome, contribution);
    let state = recipe.write_fixed(state, EH_SYNDROME, syndrome);
    let parity = recipe.read_fixed(state, EH_PARITY);
    let parity = recipe.binary(OP_XOR, Shape::uint(8), parity, bit);
    let state = recipe.write_fixed(state, EH_PARITY, parity);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn eh_validate() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_EH_VALIDATE);
    let state = 1;
    let index = recipe.iteration_byte();
    let count = recipe.read_fixed(state, EH_COUNT);
    let four = recipe.constant(8, 4);
    let count_valid = recipe.less(count, four);
    let active = recipe.less(index, count);
    let position = recipe.read_iteration(state, EH_POSITIONS);
    let zero = recipe.constant(8, 0);
    let seventy_three = recipe.constant(8, 73);
    let above_zero = recipe.less(zero, position);
    let below_limit = recipe.less(position, seventy_three);
    let in_range = recipe.bool_and(above_zero, below_limit);
    let padding = recipe.equal(position, zero);
    let position_valid = recipe.select(
        Shape {
            kind: BOOL,
            width: 1,
        },
        active,
        in_range,
        padding,
    );
    let index_zero = recipe.equal(index, zero);
    let one = recipe.constant(8, 1);
    let safe_index = recipe.select(Shape::uint(8), index_zero, one, index);
    let previous_index = recipe.binary(OP_SUB, Shape::uint(8), safe_index, one);
    let previous = recipe.read_offset(state, EH_POSITIONS, previous_index);
    let ordered = recipe.less(previous, position);
    let truth = recipe.boolean(true);
    let ordered = recipe.select(
        Shape {
            kind: BOOL,
            width: 1,
        },
        index_zero,
        truth,
        ordered,
    );
    let ordered = recipe.select(
        Shape {
            kind: BOOL,
            width: 1,
        },
        active,
        ordered,
        truth,
    );
    let valid = recipe.bool_and(count_valid, position_valid);
    let valid = recipe.bool_and(valid, ordered);
    let success = recipe.status(0);
    let failure = recipe.status(3);
    let status = recipe.select(Shape::status(), valid, success, failure);
    recipe.finish_body(status, state);
    recipe
}

fn eh_candidate() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_EH_CANDIDATE);
    let state = 1;
    let divisor = recipe.constant(64, 73);
    let fill_index = recipe.binary(OP_QUOT, Shape::uint(64), 2, divisor);
    let flip_index = recipe.binary(OP_REM, Shape::uint(64), 2, divisor);
    let identity = recipe.table(TABLE_BYTE_IDENTITY, 8);
    let fill = recipe.push(OP_LOOKUP, Shape::uint(8), &[identity, fill_index], 0, 0);
    let flip = recipe.push(OP_LOOKUP, Shape::uint(8), &[identity, flip_index], 0, 0);
    let count = recipe.read_fixed(state, EH_COUNT);
    let limit_table = recipe.table(TABLE_EH_FILL_LIMIT, 8);
    let fill_limit = recipe.push(OP_LOOKUP, Shape::uint(8), &[limit_table, count], 0, 0);
    let fill_valid = recipe.less(fill, fill_limit);
    let zero = recipe.constant(8, 0);
    let one = recipe.constant(8, 1);
    let two = recipe.constant(8, 2);
    let may_flip = recipe.less(count, two);
    let flip_zero = recipe.equal(flip, zero);
    let flip_valid = recipe.bool_or(may_flip, flip_zero);

    let mut syndrome = recipe.read_fixed(state, EH_SYNDROME);
    let mut parity = recipe.read_fixed(state, EH_PARITY);
    let mut flip_is_erasure = recipe.boolean(false);
    for ordinal in 0_u8..3 {
        let ordinal_value = recipe.constant(8, u64::from(ordinal));
        let active = recipe.less(ordinal_value, count);
        let position = recipe.read_fixed(state, EH_POSITIONS + u16::from(ordinal));
        let shifted = if ordinal == 0 {
            fill
        } else {
            let shift = recipe.constant(8, u64::from(ordinal));
            recipe.binary(OP_SHR, Shape::uint(8), fill, shift)
        };
        let bit = recipe.push(OP_MASK, Shape::uint(8), &[shifted], 0, 1);
        let safe_position = recipe.select(Shape::uint(8), active, position, one);
        let zero_based = recipe.binary(OP_SUB, Shape::uint(8), safe_position, one);
        let code_byte_table = recipe.table(TABLE_EH_CODE_BYTE, 8);
        let code_byte = recipe.push(
            OP_LOOKUP,
            Shape::uint(8),
            &[code_byte_table, zero_based],
            0,
            0,
        );
        let observed_byte = recipe.read(state, code_byte);
        let code_shift_table = recipe.table(TABLE_EH_CODE_SHIFT, 8);
        let code_shift = recipe.push(
            OP_LOOKUP,
            Shape::uint(8),
            &[code_shift_table, zero_based],
            0,
            0,
        );
        let observed = recipe.binary(OP_SHR, Shape::uint(8), observed_byte, code_shift);
        let observed = recipe.push(OP_MASK, Shape::uint(8), &[observed], 0, 1);
        let delta = recipe.binary(OP_XOR, Shape::uint(8), observed, bit);
        let delta_set = recipe.equal(delta, one);
        let contributes = recipe.bool_and(active, delta_set);
        let syndrome_position_table = recipe.table(TABLE_EH_POSITION, 8);
        let syndrome_position = recipe.push(
            OP_LOOKUP,
            Shape::uint(8),
            &[syndrome_position_table, zero_based],
            0,
            0,
        );
        let contribution = recipe.select(Shape::uint(8), contributes, syndrome_position, zero);
        syndrome = recipe.binary(OP_XOR, Shape::uint(8), syndrome, contribution);
        let parity_bit = recipe.select(Shape::uint(8), active, delta, zero);
        parity = recipe.binary(OP_XOR, Shape::uint(8), parity, parity_bit);
        let matches = recipe.equal(flip, position);
        let matches = recipe.bool_and(active, matches);
        flip_is_erasure = recipe.bool_or(flip_is_erasure, matches);
    }

    let flip_nonzero = recipe.bool_not(flip_zero);
    let seventy_two = recipe.constant(8, 72);
    let flip_overall = recipe.equal(flip, seventy_two);
    let not_overall = recipe.bool_not(flip_overall);
    let flip_has_syndrome = recipe.bool_and(flip_nonzero, not_overall);
    let flip_contribution = recipe.select(Shape::uint(8), flip_has_syndrome, flip, zero);
    syndrome = recipe.binary(OP_XOR, Shape::uint(8), syndrome, flip_contribution);
    let flip_parity = recipe.select(Shape::uint(8), flip_nonzero, one, zero);
    parity = recipe.binary(OP_XOR, Shape::uint(8), parity, flip_parity);

    let syndrome_zero = recipe.equal(syndrome, zero);
    let parity_zero = recipe.equal(parity, zero);
    let parity_valid = recipe.bool_and(syndrome_zero, parity_zero);
    let no_erasure_flip = recipe.bool_not(flip_is_erasure);
    let valid = recipe.bool_and(fill_valid, flip_valid);
    let valid = recipe.bool_and(valid, no_erasure_flip);
    let valid = recipe.bool_and(valid, parity_valid);
    let found = recipe.read_fixed(state, EH_FOUND_COUNT);
    let increment = recipe.select(Shape::uint(8), valid, one, zero);
    let found = recipe.binary(OP_ADD, Shape::uint(8), found, increment);
    let state = recipe.write_fixed(state, EH_FOUND_COUNT, found);
    let old_fill = recipe.read_fixed(state, EH_CHOSEN_FILL);
    let chosen_fill = recipe.select(Shape::uint(8), valid, fill, old_fill);
    let state = recipe.write_fixed(state, EH_CHOSEN_FILL, chosen_fill);
    let old_flip = recipe.read_fixed(state, EH_CHOSEN_FLIP);
    let chosen_flip = recipe.select(Shape::uint(8), valid, flip, old_flip);
    let state = recipe.write_fixed(state, EH_CHOSEN_FLIP, chosen_flip);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn eh_output() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_EH_OUTPUT);
    let state = 1;
    let position_table = recipe.table(TABLE_EH_POSITION, 8);
    let syndrome_position = recipe.push(OP_LOOKUP, Shape::uint(8), &[position_table, 2], 0, 0);
    let seventy_two = recipe.constant(8, 72);
    let zero = recipe.constant(8, 0);
    let is_overall = recipe.equal(syndrome_position, zero);
    let position = recipe.select(Shape::uint(8), is_overall, seventy_two, syndrome_position);
    let byte_table = recipe.table(TABLE_EH_CODE_BYTE, 8);
    let byte_index = recipe.push(OP_LOOKUP, Shape::uint(8), &[byte_table, 2], 0, 0);
    let byte = recipe.read(state, byte_index);
    let shift_table = recipe.table(TABLE_EH_CODE_SHIFT, 8);
    let shift = recipe.push(OP_LOOKUP, Shape::uint(8), &[shift_table, 2], 0, 0);
    let shifted = recipe.binary(OP_SHR, Shape::uint(8), byte, shift);
    let mut bit = recipe.push(OP_MASK, Shape::uint(8), &[shifted], 0, 1);
    let count = recipe.read_fixed(state, EH_COUNT);
    let fill = recipe.read_fixed(state, EH_CHOSEN_FILL);
    let one = recipe.constant(8, 1);
    for ordinal in 0_u8..3 {
        let ordinal_value = recipe.constant(8, u64::from(ordinal));
        let active = recipe.less(ordinal_value, count);
        let erased_position = recipe.read_fixed(state, EH_POSITIONS + u16::from(ordinal));
        let matches = recipe.equal(position, erased_position);
        let matches = recipe.bool_and(active, matches);
        let shifted_fill = if ordinal == 0 {
            fill
        } else {
            let ordinal_value = recipe.constant(8, u64::from(ordinal));
            recipe.binary(OP_SHR, Shape::uint(8), fill, ordinal_value)
        };
        let fill_bit = recipe.push(OP_MASK, Shape::uint(8), &[shifted_fill], 0, 1);
        bit = recipe.select(Shape::uint(8), matches, fill_bit, bit);
    }
    let flip = recipe.read_fixed(state, EH_CHOSEN_FLIP);
    let flip_here = recipe.equal(position, flip);
    let flipped = recipe.binary(OP_XOR, Shape::uint(8), bit, one);
    bit = recipe.select(Shape::uint(8), flip_here, flipped, bit);

    let active_table = recipe.table(TABLE_EH_DATA_ACTIVE, 8);
    let data_active = recipe.push(OP_LOOKUP, Shape::uint(8), &[active_table, 2], 0, 0);
    let data_active = recipe.equal(data_active, one);
    let data_byte_table = recipe.table(TABLE_EH_DATA_BYTE, 8);
    let data_byte = recipe.push(OP_LOOKUP, Shape::uint(8), &[data_byte_table, 2], 0, 0);
    let current = recipe.read_offset(state, EH_OUTPUT, data_byte);
    let data_shift_table = recipe.table(TABLE_EH_DATA_SHIFT, 8);
    let data_shift = recipe.push(OP_LOOKUP, Shape::uint(8), &[data_shift_table, 2], 0, 0);
    let placed = recipe.binary(OP_SHL, Shape::uint(8), bit, data_shift);
    let updated = recipe.binary(OP_XOR, Shape::uint(8), current, placed);
    let written = recipe.write_offset(state, EH_OUTPUT, data_byte, updated);
    let state = recipe.select(Shape::bytes(STATE_BYTES), data_active, written, state);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn eh_decode() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::custom(
        RECIPE_EH_DECODE,
        vec![Shape::bytes(9), Shape::bytes(1), Shape::bytes(3)],
        vec![Shape::status(), Shape::bytes(8)],
    );
    let observation = 1;
    let count_bytes = 2;
    let positions = 3;
    let prefix = recipe.push(OP_CONCAT, Shape::bytes(12), &[observation, positions], 0, 0);
    let zeros = recipe.zero_bytes(STATE_BYTES as u16 - 12);
    let mut state = recipe.push(OP_CONCAT, Shape::bytes(STATE_BYTES), &[prefix, zeros], 0, 0);
    let zero16 = recipe.constant(16, 0);
    let count = recipe.read(count_bytes, zero16);
    state = recipe.write_fixed(state, EH_COUNT, count);
    state = recipe.iterate(state, BODY_EH_VALIDATE, 3);
    state = recipe.iterate(state, BODY_EH_SCAN, 72);
    state = recipe.iterate(state, BODY_EH_CANDIDATE, 584);
    state = recipe.iterate(state, BODY_EH_OUTPUT, 72);
    let found = recipe.read_fixed(state, EH_FOUND_COUNT);
    let one = recipe.constant(8, 1);
    let unique = recipe.equal(found, one);
    let start = recipe.constant(16, u64::from(EH_OUTPUT));
    let length = recipe.constant(16, 8);
    let output = recipe.push(OP_SLICE, Shape::bytes(8), &[state, start, length], 0, 0);
    let success = recipe.status(0);
    let failure = recipe.status(5);
    let status = recipe.select(Shape::status(), unique, success, failure);
    recipe.finish_main(status, output);
    recipe
}

fn eh_encode_step() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_EH_ENCODE);
    let state = 1;
    let one = recipe.constant(8, 1);
    let active_table = recipe.table(TABLE_EH_DATA_ACTIVE, 8);
    let active = recipe.push(OP_LOOKUP, Shape::uint(8), &[active_table, 2], 0, 0);
    let active = recipe.equal(active, one);
    let data_byte_table = recipe.table(TABLE_EH_DATA_BYTE, 8);
    let data_byte = recipe.push(OP_LOOKUP, Shape::uint(8), &[data_byte_table, 2], 0, 0);
    let byte = recipe.read(state, data_byte);
    let data_shift_table = recipe.table(TABLE_EH_DATA_SHIFT, 8);
    let data_shift = recipe.push(OP_LOOKUP, Shape::uint(8), &[data_shift_table, 2], 0, 0);
    let shifted = recipe.binary(OP_SHR, Shape::uint(8), byte, data_shift);
    let bit = recipe.push(OP_MASK, Shape::uint(8), &[shifted], 0, 1);
    let code_byte_table = recipe.table(TABLE_EH_CODE_BYTE, 8);
    let code_byte = recipe.push(OP_LOOKUP, Shape::uint(8), &[code_byte_table, 2], 0, 0);
    let current = recipe.read_offset(state, EH_OUTPUT, code_byte);
    let code_shift_table = recipe.table(TABLE_EH_CODE_SHIFT, 8);
    let code_shift = recipe.push(OP_LOOKUP, Shape::uint(8), &[code_shift_table, 2], 0, 0);
    let placed = recipe.binary(OP_SHL, Shape::uint(8), bit, code_shift);
    let updated = recipe.binary(OP_XOR, Shape::uint(8), current, placed);
    let written = recipe.write_offset(state, EH_OUTPUT, code_byte, updated);
    let state = recipe.select(Shape::bytes(STATE_BYTES), active, written, state);
    let position_table = recipe.table(TABLE_EH_POSITION, 8);
    let position = recipe.push(OP_LOOKUP, Shape::uint(8), &[position_table, 2], 0, 0);
    let zero = recipe.constant(8, 0);
    let bit_set = recipe.equal(bit, one);
    let contributes = recipe.bool_and(active, bit_set);
    let contribution = recipe.select(Shape::uint(8), contributes, position, zero);
    let syndrome = recipe.read_fixed(state, EH_SYNDROME);
    let syndrome = recipe.binary(OP_XOR, Shape::uint(8), syndrome, contribution);
    let state = recipe.write_fixed(state, EH_SYNDROME, syndrome);
    let parity = recipe.read_fixed(state, EH_PARITY);
    let selected_bit = recipe.select(Shape::uint(8), active, bit, zero);
    let parity = recipe.binary(OP_XOR, Shape::uint(8), parity, selected_bit);
    let state = recipe.write_fixed(state, EH_PARITY, parity);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn eh_parity_step() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_EH_PARITY);
    let state = 1;
    let iteration = 2;
    let syndrome = recipe.read_fixed(state, EH_SYNDROME);
    let shifted = recipe.binary(OP_SHR, Shape::uint(8), syndrome, iteration);
    let bit = recipe.push(OP_MASK, Shape::uint(8), &[shifted], 0, 1);
    let one = recipe.constant(8, 1);
    let position = recipe.binary(OP_SHL, Shape::uint(8), one, iteration);
    let zero_based = recipe.binary(OP_SUB, Shape::uint(8), position, one);
    let byte_table = recipe.table(TABLE_EH_CODE_BYTE, 8);
    let code_byte = recipe.push(OP_LOOKUP, Shape::uint(8), &[byte_table, zero_based], 0, 0);
    let output_base = recipe.constant(8, u64::from(EH_OUTPUT));
    let byte_index = recipe.binary(OP_ADD, Shape::uint(8), output_base, code_byte);
    let current = recipe.read(state, byte_index);
    let shift_table = recipe.table(TABLE_EH_CODE_SHIFT, 8);
    let code_shift = recipe.push(OP_LOOKUP, Shape::uint(8), &[shift_table, zero_based], 0, 0);
    let placed = recipe.binary(OP_SHL, Shape::uint(8), bit, code_shift);
    let updated = recipe.binary(OP_XOR, Shape::uint(8), current, placed);
    let state = recipe.write(state, byte_index, updated);
    let parity_index = recipe.fixed_index(EH_PARITY);
    let parity = recipe.read(state, parity_index);
    let parity = recipe.binary(OP_XOR, Shape::uint(8), parity, bit);
    let state = recipe.write(state, parity_index, parity);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn eh_encode() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::custom(
        RECIPE_TRANSPORT_ENCODE,
        vec![Shape::bytes(8)],
        vec![Shape::status(), Shape::bytes(9)],
    );
    let input = 1;
    let zeros = recipe.zero_bytes(STATE_BYTES as u16 - 8);
    let mut state = recipe.push(OP_CONCAT, Shape::bytes(STATE_BYTES), &[input, zeros], 0, 0);
    state = recipe.iterate(state, BODY_EH_ENCODE, 72);
    state = recipe.iterate(state, BODY_EH_PARITY, 7);
    let parity = recipe.read_fixed(state, EH_PARITY);
    let overall_index = recipe.fixed_index(EH_OUTPUT + 8);
    let overall = recipe.read(state, overall_index);
    let overall = recipe.binary(OP_XOR, Shape::uint(8), overall, parity);
    state = recipe.write(state, overall_index, overall);
    let start = recipe.constant(16, u64::from(EH_OUTPUT));
    let length = recipe.constant(16, 9);
    let output = recipe.push(OP_SLICE, Shape::bytes(9), &[state, start, length], 0, 0);
    let status = recipe.status(0);
    recipe.finish_main(status, output);
    recipe
}

fn crc32c_bit() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_CRC32C_BIT);
    let state = 1;
    let crc = recipe.read_uint(state, CRC_VALUE, 4);
    let byte = recipe.read_fixed(state, CRC_BYTE);
    let iteration = recipe.iteration_byte();
    let shifted = recipe.binary(OP_SHR, Shape::uint(8), byte, iteration);
    let bit = recipe.push(OP_MASK, Shape::uint(8), &[shifted], 0, 1);
    let one8 = recipe.constant(8, 1);
    let bit_set = recipe.equal(bit, one8);
    let zero32 = recipe.constant(32, 0);
    let one32 = recipe.constant(32, 1);
    let bit = recipe.select(Shape::uint(32), bit_set, one32, zero32);
    let low = recipe.push(OP_MASK, Shape::uint(32), &[crc], 0, 1);
    let mix = recipe.binary(OP_XOR, Shape::uint(32), low, bit);
    let mix = recipe.equal(mix, one32);
    let shifted_crc = recipe.binary(OP_SHR, Shape::uint(32), crc, one32);
    let polynomial = recipe.constant(32, 0x82f6_3b78);
    let reduction = recipe.select(Shape::uint(32), mix, polynomial, zero32);
    let crc = recipe.binary(OP_XOR, Shape::uint(32), shifted_crc, reduction);
    let state = recipe.write_uint(state, CRC_VALUE, 4, crc);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn combined_crc_bit() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_CRC32C_BIT);
    let state = 1;
    let crc = recipe.read_uint(state, CRC_VALUE, 8);
    let byte = recipe.read_fixed(state, CRC_BYTE);
    let iteration = recipe.iteration_byte();
    let one8 = recipe.constant(8, 1);
    let zero64 = recipe.constant(64, 0);
    let one64 = recipe.constant(64, 1);

    let reflected = recipe.binary(OP_SHR, Shape::uint(8), byte, iteration);
    let reflected = recipe.push(OP_MASK, Shape::uint(8), &[reflected], 0, 1);
    let reflected_set = recipe.equal(reflected, one8);
    let reflected = recipe.select(Shape::uint(64), reflected_set, one64, zero64);
    let low = recipe.push(OP_MASK, Shape::uint(64), &[crc], 0, 1);
    let reflected_mix = recipe.binary(OP_XOR, Shape::uint(64), low, reflected);
    let reflected_mix = recipe.equal(reflected_mix, one64);
    let reflected_shift = recipe.binary(OP_SHR, Shape::uint(64), crc, one64);
    let crc32_polynomial = recipe.constant(64, 0x82f6_3b78);
    let crc32_reduction = recipe.select(Shape::uint(64), reflected_mix, crc32_polynomial, zero64);
    let crc32 = recipe.binary(OP_XOR, Shape::uint(64), reflected_shift, crc32_reduction);

    let seven = recipe.constant(8, 7);
    let bit_shift = recipe.binary(OP_SUB, Shape::uint(8), seven, iteration);
    let forward = recipe.binary(OP_SHR, Shape::uint(8), byte, bit_shift);
    let forward = recipe.push(OP_MASK, Shape::uint(8), &[forward], 0, 1);
    let forward_set = recipe.equal(forward, one8);
    let forward = recipe.select(Shape::uint(64), forward_set, one64, zero64);
    let top_shift = recipe.constant(64, 63);
    let top = recipe.binary(OP_SHR, Shape::uint(64), crc, top_shift);
    let forward_mix = recipe.binary(OP_XOR, Shape::uint(64), top, forward);
    let forward_mix = recipe.equal(forward_mix, one64);
    let masked = recipe.push(OP_MASK, Shape::uint(64), &[crc], 0, 0x7fff_ffff_ffff_ffff);
    let forward_shift = recipe.binary(OP_SHL, Shape::uint(64), masked, one64);
    let crc64_polynomial = recipe.constant(64, 0x42f0_e1eb_a9ea_3693);
    let crc64_reduction = recipe.select(Shape::uint(64), forward_mix, crc64_polynomial, zero64);
    let crc64 = recipe.binary(OP_XOR, Shape::uint(64), forward_shift, crc64_reduction);

    let mode = recipe.read_fixed(state, CRC_MODE);
    let crc64_mode = recipe.equal(mode, one8);
    let crc = recipe.select(Shape::uint(64), crc64_mode, crc64, crc32);
    let state = recipe.write_uint(state, CRC_VALUE, 8, crc);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn crc_byte(id: u16, bit_body: u16) -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(id);
    let state = 1;
    let byte = recipe.read(state, 2);
    let state = recipe.write_fixed(state, CRC_BYTE, byte);
    let state = recipe.iterate(state, bit_body, 8);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn crc_fact(id: u16, width: u32, body: u16, combined: bool) -> RecipeBuilder {
    let mut recipe = RecipeBuilder::custom(
        id,
        vec![Shape::bytes(9)],
        vec![Shape::status(), Shape::uint(width)],
    );
    let input = 1;
    let zeros = recipe.zero_bytes(STATE_BYTES as u16 - 9);
    let mut state = recipe.push(OP_CONCAT, Shape::bytes(STATE_BYTES), &[input, zeros], 0, 0);
    let bytes = if combined { 8 } else { (width / 8) as u16 };
    if width == 32 {
        let initial_byte = recipe.constant(8, 0xff);
        let initial_start = if combined { 4 } else { 0 };
        for index in initial_start..bytes {
            state = recipe.write_fixed(state, CRC_VALUE + index, initial_byte);
        }
    }
    if combined {
        let mode = recipe.constant(8, u64::from(width == 64));
        state = recipe.write_fixed(state, CRC_MODE, mode);
    }
    let byte_body = if body == BODY_CRC32C_BIT {
        BODY_CRC32C_BYTE
    } else {
        BODY_CRC64_BYTE
    };
    state = recipe.iterate(state, byte_body, 9);
    let result_offset = if combined && width == 32 {
        CRC_VALUE + 4
    } else {
        CRC_VALUE
    };
    let mut crc = recipe.read_uint(state, result_offset, (width / 8) as u16);
    if width == 32 {
        let xor_out = recipe.constant(32, 0xffff_ffff);
        crc = recipe.binary(OP_XOR, Shape::uint(32), crc, xor_out);
    }
    let status = recipe.status(0);
    recipe.finish_main(status, crc);
    recipe
}

fn r3_map_forward() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::custom(
        114,
        vec![
            Shape::uint(32),
            Shape::uint(16),
            Shape::uint(16),
            Shape::uint(16),
        ],
        vec![Shape::status(), Shape::uint(32)],
    );
    let physical_unit_id = 1;
    let encoded_bit = 2;
    let side = 3;
    let shell_width = 4;
    let zero16 = recipe.constant(16, 0);
    let eight16 = recipe.constant(16, 8);
    let side_min = recipe.constant(16, 63);
    let side_limit = recipe.constant(16, 2_049);
    let width_min = recipe.constant(16, 7);
    let width_limit = recipe.constant(16, 129);
    let side_above_min = recipe.less(side_min, side);
    let side_below_limit = recipe.less(side, side_limit);
    let width_above_min = recipe.less(width_min, shell_width);
    let width_below_limit = recipe.less(shell_width, width_limit);
    let side_remainder = recipe.binary(OP_REM, Shape::uint(16), side, eight16);
    let width_remainder = recipe.binary(OP_REM, Shape::uint(16), shell_width, eight16);
    let side_aligned = recipe.equal(side_remainder, zero16);
    let width_aligned = recipe.equal(width_remainder, zero16);
    let side_shape = recipe.bool_and(side_above_min, side_below_limit);
    let side_shape = recipe.bool_and(side_shape, side_aligned);
    let width_shape = recipe.bool_and(width_above_min, width_below_limit);
    let width_shape = recipe.bool_and(width_shape, width_aligned);
    let safe_side_default = recipe.constant(16, 64);
    let safe_width_default = recipe.constant(16, 8);
    let safe_side = recipe.select(Shape::uint(16), side_shape, side, safe_side_default);
    let safe_width = recipe.select(
        Shape::uint(16),
        width_shape,
        shell_width,
        safe_width_default,
    );
    let two16 = recipe.constant(16, 2);
    let double_width = recipe.binary(OP_MUL, Shape::uint(16), safe_width, two16);
    let minimum_side = recipe.binary(OP_ADD, Shape::uint(16), double_width, eight16);
    let shell_fits = recipe.less_or_equal(minimum_side, safe_side);
    let mut valid = recipe.bool_and(side_shape, width_shape);
    valid = recipe.bool_and(valid, shell_fits);
    let safe_side = recipe.select(Shape::uint(16), shell_fits, safe_side, safe_side_default);
    let safe_width = recipe.select(Shape::uint(16), shell_fits, safe_width, safe_width_default);
    let double_width = recipe.binary(OP_MUL, Shape::uint(16), safe_width, two16);
    let interior16 = recipe.binary(OP_SUB, Shape::uint(16), safe_side, double_width);
    let interior_index = recipe.binary(OP_QUOT, Shape::uint(16), interior16, eight16);
    let multiplier_table = recipe.table(TABLE_R3_SLOT_MULTIPLIER, 8);
    let slot_multiplier = recipe.push(
        OP_LOOKUP,
        Shape::uint(8),
        &[multiplier_table, interior_index],
        0,
        0,
    );
    let zero8 = recipe.constant(8, 0);
    let has_multiplier = recipe.less(zero8, slot_multiplier);
    valid = recipe.bool_and(valid, has_multiplier);
    let interior = recipe.push(OP_CONCAT, Shape::uint(32), &[zero16, interior16], 0, 0);
    let population = recipe.binary(OP_MUL, Shape::uint(32), interior, interior);
    let unit_bits = recipe.constant(32, 1_728);
    let slot_count = recipe.binary(OP_QUOT, Shape::uint(32), population, unit_bits);
    let zero32 = recipe.constant(32, 0);
    let one32 = recipe.constant(32, 1);
    let id_nonzero = recipe.less(zero32, physical_unit_id);
    let id_in_range = recipe.less_or_equal(physical_unit_id, slot_count);
    let bit_limit = recipe.constant(16, 1_728);
    let bit_in_range = recipe.less(encoded_bit, bit_limit);
    valid = recipe.bool_and(valid, id_nonzero);
    valid = recipe.bool_and(valid, id_in_range);
    valid = recipe.bool_and(valid, bit_in_range);
    let safe_id = recipe.select(Shape::uint(32), id_nonzero, physical_unit_id, one32);
    let ordinal = recipe.binary(OP_SUB, Shape::uint(32), safe_id, one32);
    let slot_multiplier16 =
        recipe.push(OP_CONCAT, Shape::uint(16), &[zero8, slot_multiplier], 0, 0);
    let slot_multiplier32 = recipe.push(
        OP_CONCAT,
        Shape::uint(32),
        &[zero16, slot_multiplier16],
        0,
        0,
    );
    let slot_product = recipe.binary(OP_MUL, Shape::uint(32), slot_multiplier32, ordinal);
    let safe_slot_count = recipe.select(Shape::uint(32), has_multiplier, slot_count, one32);
    let slot = recipe.binary(OP_REM, Shape::uint(32), slot_product, safe_slot_count);
    let slot_first = recipe.binary(OP_MUL, Shape::uint(32), slot, unit_bits);
    let bit32 = recipe.push(OP_CONCAT, Shape::uint(32), &[zero16, encoded_bit], 0, 0);
    let logical = recipe.binary(OP_ADD, Shape::uint(32), slot_first, bit32);

    // `(2I-1)*logical mod I^2`, expressed without overflowing UINT[32].
    let remainder = recipe.binary(OP_REM, Shape::uint(32), logical, interior);
    let scaled_once = recipe.binary(OP_MUL, Shape::uint(32), interior, remainder);
    let two32 = recipe.constant(32, 2);
    let scaled_twice = recipe.binary(OP_MUL, Shape::uint(32), scaled_once, two32);
    let scaled = recipe.binary(OP_REM, Shape::uint(32), scaled_twice, population);
    let shifted = recipe.binary(OP_ADD, Shape::uint(32), population, scaled);
    let difference = recipe.binary(OP_SUB, Shape::uint(32), shifted, logical);
    let multiplied = recipe.binary(OP_REM, Shape::uint(32), difference, population);
    let width32 = recipe.push(OP_CONCAT, Shape::uint(32), &[zero16, safe_width], 0, 0);
    let width_factor = recipe.constant(32, 257);
    let width_term = recipe.binary(OP_MUL, Shape::uint(32), width32, width_factor);
    let profile_term = recipe.constant(32, 40_503 * 7);
    let offset_sum = recipe.binary(OP_ADD, Shape::uint(32), width_term, profile_term);
    let offset = recipe.binary(OP_REM, Shape::uint(32), offset_sum, population);
    let added = recipe.binary(OP_ADD, Shape::uint(32), multiplied, offset);
    let output = recipe.binary(OP_REM, Shape::uint(32), added, population);
    let success = recipe.status(0);
    let failure = recipe.status(3);
    let status = recipe.select(Shape::status(), valid, success, failure);
    recipe.finish_main(status, output);
    recipe
}

fn r3_shape_stub(id: u16) -> RecipeBuilder {
    let (inputs, outputs) = match id {
        113 => (
            vec![
                Shape::uint(8),
                Shape { kind: 2, width: 5 },
                Shape { kind: 2, width: 5 },
            ],
            vec![
                Shape::status(),
                Shape {
                    kind: BOOL,
                    width: 1,
                },
                Shape {
                    kind: BOOL,
                    width: 1,
                },
            ],
        ),
        115 => (
            vec![Shape::uint(32), Shape::uint(16), Shape::uint(16)],
            vec![
                Shape::status(),
                Shape::uint(8),
                Shape::uint(32),
                Shape::uint(16),
            ],
        ),
        116 => (
            vec![Shape::bytes(20)],
            vec![
                Shape::status(),
                Shape::uint(8),
                Shape {
                    kind: BOOL,
                    width: 1,
                },
            ],
        ),
        117 => (
            vec![Shape::uint(32), Shape::uint(32), Shape::uint(8)],
            vec![Shape::status(), Shape::uint(8)],
        ),
        _ => unreachable!("closed R3 ABI size-probe ID"),
    };
    let mut recipe = RecipeBuilder::custom(id, inputs, outputs.clone());
    let status = recipe.status(0);
    let mut values = Vec::new();
    for shape in outputs.into_iter().skip(1) {
        values.push(if shape.kind == BOOL {
            recipe.boolean(false)
        } else {
            recipe.constant(shape.width, 0)
        });
    }
    recipe.finish_outputs(status, &values);
    recipe
}

fn r3_slot_only(trusted_inputs: bool) -> RecipeBuilder {
    let mut recipe = RecipeBuilder::custom(
        114,
        vec![Shape::uint(32), Shape::uint(32), Shape::uint(8)],
        vec![Shape::status(), Shape::uint(32)],
    );
    let physical_unit_id = 1;
    let slot_count = 2;
    let multiplier = 3;
    let zero8 = recipe.constant(8, 0);
    let zero16 = recipe.constant(16, 0);
    let one32 = recipe.constant(32, 1);
    let multiplier16 = recipe.push(OP_CONCAT, Shape::uint(16), &[zero8, multiplier], 0, 0);
    let multiplier32 = recipe.push(OP_CONCAT, Shape::uint(32), &[zero16, multiplier16], 0, 0);
    let (safe_id, safe_slot_count, valid) = if trusted_inputs {
        (physical_unit_id, slot_count, None)
    } else {
        let zero32 = recipe.constant(32, 0);
        let id_nonzero = recipe.less(zero32, physical_unit_id);
        let slots_nonzero = recipe.less(zero32, slot_count);
        let id_in_range = recipe.less_or_equal(physical_unit_id, slot_count);
        let multiplier_nonzero = recipe.less(zero8, multiplier);
        let valid = recipe.bool_and(id_nonzero, slots_nonzero);
        let valid = recipe.bool_and(valid, id_in_range);
        let valid = recipe.bool_and(valid, multiplier_nonzero);
        (
            recipe.select(Shape::uint(32), id_nonzero, physical_unit_id, one32),
            recipe.select(Shape::uint(32), slots_nonzero, slot_count, one32),
            Some(valid),
        )
    };
    let ordinal = recipe.binary(OP_SUB, Shape::uint(32), safe_id, one32);
    let product = recipe.binary(OP_MUL, Shape::uint(32), multiplier32, ordinal);
    let slot = recipe.binary(OP_REM, Shape::uint(32), product, safe_slot_count);
    let success = recipe.status(0);
    let status = if let Some(valid) = valid {
        let failure = recipe.status(3);
        recipe.select(Shape::status(), valid, success, failure)
    } else {
        success
    };
    recipe.finish_main(status, slot);
    recipe
}

fn r3_repetition_symbol_masks() -> RecipeBuilder {
    let bits5 = Shape { kind: 2, width: 5 };
    let bool1 = Shape {
        kind: BOOL,
        width: 1,
    };
    let mut recipe = RecipeBuilder::custom(
        113,
        vec![Shape::uint(8), bits5, bits5],
        vec![Shape::status(), bool1, bool1],
    );
    let factor = 1;
    let known_mask = 2;
    let one_mask = 3;
    let zero5 = recipe.constant(5, 0);
    let five5 = recipe.constant(5, 5);
    let known = recipe.push(OP_SLICE, Shape::uint(5), &[known_mask, zero5, five5], 0, 0);
    let ones = recipe.push(OP_SLICE, Shape::uint(5), &[one_mask, zero5, five5], 0, 0);
    let two8 = recipe.constant(8, 2);
    let five8 = recipe.constant(8, 5);
    let factor_two = recipe.equal(factor, two8);
    let factor_five = recipe.equal(factor, five8);
    let factor_valid = recipe.bool_or(factor_two, factor_five);
    let overlap = recipe.binary(OP_AND, Shape::uint(5), ones, known);
    let subset = recipe.equal(overlap, ones);
    let tail_mask = recipe.constant(5, 7);
    let known_tail = recipe.binary(OP_AND, Shape::uint(5), known, tail_mask);
    let ones_tail = recipe.binary(OP_AND, Shape::uint(5), ones, tail_mask);
    let known_tail_zero = recipe.equal(known_tail, zero5);
    let ones_tail_zero = recipe.equal(ones_tail, zero5);
    let factor_two_tail = recipe.bool_and(known_tail_zero, ones_tail_zero);
    let truth = recipe.boolean(true);
    let tail_valid = recipe.select(bool1, factor_two, factor_two_tail, truth);
    let valid = recipe.bool_and(factor_valid, subset);
    let valid = recipe.bool_and(valid, tail_valid);

    let popcount = recipe.table(TABLE_R3_POPCOUNT5, 8);
    let known_count = recipe.push(OP_LOOKUP, Shape::uint(8), &[popcount, known], 0, 0);
    let one_count = recipe.push(OP_LOOKUP, Shape::uint(8), &[popcount, ones], 0, 0);
    let zero8 = recipe.constant(8, 0);
    let safe_known_count = recipe.select(Shape::uint(8), valid, known_count, zero8);
    let safe_one_count = recipe.select(Shape::uint(8), valid, one_count, zero8);
    let zero_count = recipe.binary(OP_SUB, Shape::uint(8), safe_known_count, safe_one_count);
    let output_zero = recipe.less(safe_one_count, zero_count);
    let output_one = recipe.less(zero_count, safe_one_count);
    let output_known = recipe.bool_or(output_zero, output_one);
    let success = recipe.status(0);
    let failure = recipe.status(3);
    let status = recipe.select(Shape::status(), valid, success, failure);
    recipe.finish_outputs(status, &[output_known, output_one]);
    recipe
}

fn r3_repetition_symbol_counts() -> RecipeBuilder {
    let bool1 = Shape {
        kind: BOOL,
        width: 1,
    };
    let mut recipe = RecipeBuilder::custom(
        113,
        vec![Shape::uint(8), Shape::uint(8), Shape::uint(8)],
        vec![Shape::status(), bool1, bool1],
    );
    let factor = 1;
    let known_zero_count = 2;
    let known_one_count = 3;
    let two = recipe.constant(8, 2);
    let five = recipe.constant(8, 5);
    let factor_two = recipe.equal(factor, two);
    let factor_five = recipe.equal(factor, five);
    let factor_valid = recipe.bool_or(factor_two, factor_five);
    let zero8 = recipe.constant(8, 0);
    let factor16 = recipe.push(OP_CONCAT, Shape::uint(16), &[zero8, factor], 0, 0);
    let known_zero16 = recipe.push(OP_CONCAT, Shape::uint(16), &[zero8, known_zero_count], 0, 0);
    let known_one16 = recipe.push(OP_CONCAT, Shape::uint(16), &[zero8, known_one_count], 0, 0);
    let total = recipe.binary(OP_ADD, Shape::uint(16), known_zero16, known_one16);
    let total_valid = recipe.less_or_equal(total, factor16);
    let valid = recipe.bool_and(factor_valid, total_valid);
    let output_zero = recipe.less(known_one_count, known_zero_count);
    let output_one = recipe.less(known_zero_count, known_one_count);
    let output_known = recipe.bool_or(output_zero, output_one);
    let success = recipe.status(0);
    let failure = recipe.status(3);
    let status = recipe.select(Shape::status(), valid, success, failure);
    recipe.finish_outputs(status, &[output_known, output_one]);
    recipe
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct R3AbiSizeProbe {
    pub archived_package_bytes: u32,
    pub archived_map_recipe_bytes: u32,
    pub maximum_package_bytes: u32,
    pub optimistic_probe_bytes: u32,
    pub optimistic_probe_nodes: u32,
    pub exact_forward_recipe_bytes: u32,
    pub exact_forward_recipe_nodes: u32,
    pub trusted_slot_recipe_bytes: u32,
    pub trusted_slot_recipe_nodes: u32,
    pub checked_slot_recipe_bytes: u32,
    pub checked_slot_recipe_nodes: u32,
    pub slot_multiplier_table_record_bytes: u32,
    pub mask_repetition_recipe_bytes: u32,
    pub mask_repetition_recipe_nodes: u32,
    pub mask_repetition_table_record_bytes: u32,
    pub count_repetition_recipe_bytes: u32,
    pub count_repetition_recipe_nodes: u32,
}

/// Deterministic shell-feasibility probe. Recipes 113/115/116/117 are
/// deliberately output-only shape stubs. This is a concrete provisional
/// measurement, not a minimality proof and never a recipient package.
pub fn r3_compact_abi_size_probe() -> Result<R3AbiSizeProbe> {
    let mut recipes = Vec::new();
    let mut builders = vec![
        eh_scan(),
        eh_validate(),
        eh_candidate(),
        eh_output(),
        eh_decode(),
        crc32c_bit(),
        crc_byte(BODY_CRC32C_BYTE, BODY_CRC32C_BIT),
        eh_parity_step(),
        eh_encode_step(),
    ];
    for id in 101..=107 {
        builders.push(fact_recipe(id, 7));
    }
    builders.push(eh_encode());
    builders.push(fact_recipe(111, 7));
    builders.push(fact_recipe(112, 7));
    builders.push(r3_shape_stub(113));
    builders.push(r3_map_forward());
    builders.push(r3_shape_stub(115));
    builders.push(r3_shape_stub(116));
    builders.push(r3_shape_stub(117));
    for builder in builders {
        recipes.push(finalize(builder, &recipes));
    }
    let forward = recipes
        .iter()
        .find(|recipe| recipe.builder.id == 114)
        .expect("forward recipe");
    let forward_bytes = encode_recipe(forward).len();
    let trusted_slot = finalize(r3_slot_only(true), &[]);
    let checked_slot = finalize(r3_slot_only(false), &[]);
    let mask_repetition = finalize(r3_repetition_symbol_masks(), &[]);
    let count_repetition = finalize(r3_repetition_symbol_counts(), &[]);
    let raw = encode_package_with_tables(7, &recipes, r3_eh_tables());
    decode_recipe_package(&raw, 7)?;
    Ok(R3AbiSizeProbe {
        archived_package_bytes: 24_786,
        archived_map_recipe_bytes: 1_644,
        maximum_package_bytes: 26_373,
        optimistic_probe_bytes: u32::try_from(raw.len()).expect("package bound"),
        optimistic_probe_nodes: u32::from_be_bytes(raw[20..24].try_into().unwrap()),
        exact_forward_recipe_bytes: u32::try_from(forward_bytes).expect("recipe bound"),
        exact_forward_recipe_nodes: u32::try_from(forward.builder.nodes.len()).expect("node bound"),
        trusted_slot_recipe_bytes: u32::try_from(encode_recipe(&trusted_slot).len())
            .expect("recipe bound"),
        trusted_slot_recipe_nodes: u32::try_from(trusted_slot.builder.nodes.len())
            .expect("node bound"),
        checked_slot_recipe_bytes: u32::try_from(encode_recipe(&checked_slot).len())
            .expect("recipe bound"),
        checked_slot_recipe_nodes: u32::try_from(checked_slot.builder.nodes.len())
            .expect("node bound"),
        slot_multiplier_table_record_bytes: 16 + 256,
        mask_repetition_recipe_bytes: u32::try_from(encode_recipe(&mask_repetition).len())
            .expect("recipe bound"),
        mask_repetition_recipe_nodes: u32::try_from(mask_repetition.builder.nodes.len())
            .expect("node bound"),
        mask_repetition_table_record_bytes: 16 + 32,
        count_repetition_recipe_bytes: u32::try_from(encode_recipe(&count_repetition).len())
            .expect("recipe bound"),
        count_repetition_recipe_nodes: u32::try_from(count_repetition.builder.nodes.len())
            .expect("node bound"),
    })
}

fn fact_recipe(id: u16, profile_version: u16) -> RecipeBuilder {
    match id {
        101 => {
            let mut recipe = RecipeBuilder::custom(
                id,
                vec![Shape { kind: 2, width: 8 }],
                vec![Shape::status(), Shape { kind: 2, width: 8 }],
            );
            let table = recipe.table(TABLE_BITS_NOT_MASK, 8);
            let zero = recipe.constant(8, 0);
            let mask = recipe.push(OP_LOOKUP, Shape { kind: 2, width: 8 }, &[table, zero], 0, 0);
            let output = recipe.binary(OP_XOR, Shape { kind: 2, width: 8 }, 1, mask);
            let status = recipe.status(0);
            recipe.finish_main(status, output);
            recipe
        }
        102 => {
            let mut recipe = RecipeBuilder::custom(
                id,
                vec![
                    Shape::uint(3),
                    Shape {
                        kind: BOOL,
                        width: 1,
                    },
                    Shape::uint(16),
                    Shape::uint(16),
                    Shape::uint(16),
                    Shape {
                        kind: BOOL,
                        width: 1,
                    },
                ],
                vec![
                    Shape::status(),
                    Shape::uint(32),
                    Shape {
                        kind: BOOL,
                        width: 1,
                    },
                ],
            );
            let transform = 1;
            let polarity = 2;
            let row = 3;
            let column = 4;
            let side = 5;
            let observed = 6;
            let zero16 = recipe.constant(16, 0);
            let one16 = recipe.constant(16, 1);
            let side_nonzero = recipe.less(zero16, side);
            let safe_side = recipe.select(Shape::uint(16), side_nonzero, side, one16);
            let last = recipe.binary(OP_SUB, Shape::uint(16), safe_side, one16);
            let row_valid = recipe.less(row, safe_side);
            let column_valid = recipe.less(column, safe_side);
            let safe_row = recipe.select(Shape::uint(16), row_valid, row, zero16);
            let safe_column = recipe.select(Shape::uint(16), column_valid, column, zero16);
            let flags_table = recipe.table(TABLE_D4_FLAGS, 8);
            let flags = recipe.push(OP_LOOKUP, Shape::uint(8), &[flags_table, transform], 0, 0);
            let zero8 = recipe.constant(8, 0);
            let swap_mask = recipe.push(OP_MASK, Shape::uint(8), &[flags], 0, 1);
            let swap = recipe.less(zero8, swap_mask);
            let reverse_row_mask = recipe.push(OP_MASK, Shape::uint(8), &[flags], 0, 2);
            let reverse_row = recipe.less(zero8, reverse_row_mask);
            let reverse_column_mask = recipe.push(OP_MASK, Shape::uint(8), &[flags], 0, 4);
            let reverse_column = recipe.less(zero8, reverse_column_mask);
            let base_row = recipe.select(Shape::uint(16), swap, safe_column, safe_row);
            let base_column = recipe.select(Shape::uint(16), swap, safe_row, safe_column);
            let flipped_row = recipe.binary(OP_SUB, Shape::uint(16), last, base_row);
            let flipped_column = recipe.binary(OP_SUB, Shape::uint(16), last, base_column);
            let selected_row = recipe.select(Shape::uint(16), reverse_row, flipped_row, base_row);
            let selected_column =
                recipe.select(Shape::uint(16), reverse_column, flipped_column, base_column);
            let row32 = recipe.push(OP_CONCAT, Shape::uint(32), &[zero16, selected_row], 0, 0);
            let column32 =
                recipe.push(OP_CONCAT, Shape::uint(32), &[zero16, selected_column], 0, 0);
            let side32 = recipe.push(OP_CONCAT, Shape::uint(32), &[zero16, safe_side], 0, 0);
            let product = recipe.binary(OP_MUL, Shape::uint(32), row32, side32);
            let flat = recipe.binary(OP_ADD, Shape::uint(32), product, column32);
            let same = recipe.equal(polarity, observed);
            let false_value = recipe.boolean(false);
            let normalized = recipe.equal(same, false_value);
            let valid = recipe.select(
                Shape {
                    kind: BOOL,
                    width: 1,
                },
                side_nonzero,
                row_valid,
                false_value,
            );
            let valid = recipe.select(
                Shape {
                    kind: BOOL,
                    width: 1,
                },
                valid,
                column_valid,
                false_value,
            );
            let success = recipe.status(0);
            let failure = recipe.status(3);
            let status = recipe.select(Shape::status(), valid, success, failure);
            recipe.finish_outputs(status, &[flat, normalized]);
            recipe
        }
        103 => {
            let mut recipe = RecipeBuilder::custom(
                id,
                vec![Shape::uint(16), Shape::uint(16)],
                vec![
                    Shape::status(),
                    Shape {
                        kind: BOOL,
                        width: 1,
                    },
                ],
            );
            let output = recipe.less(1, 2);
            let status = recipe.status(0);
            recipe.finish_main(status, output);
            recipe
        }
        104 => {
            let mut recipe = RecipeBuilder::custom(
                id,
                vec![Shape::uint(16), Shape::uint(16), Shape::uint(16)],
                vec![Shape::status(), Shape::uint(32)],
            );
            let zero = recipe.constant(16, 0);
            let row = recipe.push(OP_CONCAT, Shape::uint(32), &[zero, 1], 0, 0);
            let column = recipe.push(OP_CONCAT, Shape::uint(32), &[zero, 2], 0, 0);
            let stride = recipe.push(OP_CONCAT, Shape::uint(32), &[zero, 3], 0, 0);
            let product = recipe.binary(OP_MUL, Shape::uint(32), row, stride);
            let output = recipe.binary(OP_ADD, Shape::uint(32), product, column);
            let status = recipe.status(0);
            recipe.finish_main(status, output);
            recipe
        }
        105 => {
            let mut recipe = RecipeBuilder::custom(
                id,
                vec![Shape::uint(32)],
                vec![Shape::status(), Shape::uint(32)],
            );
            let one = recipe.constant(32, 1);
            let output = recipe.binary(OP_ADD, Shape::uint(32), 1, one);
            let status = recipe.status(0);
            recipe.finish_main(status, output);
            recipe
        }
        106 => {
            let mut recipe = RecipeBuilder::custom(
                id,
                vec![Shape::uint(8)],
                vec![
                    Shape::status(),
                    Shape {
                        kind: BOOL,
                        width: 1,
                    },
                ],
            );
            let zero = recipe.constant(8, 0);
            let output = recipe.equal(1, zero);
            let status = recipe.status(0);
            recipe.finish_main(status, output);
            recipe
        }
        107 => crc_fact(id, 32, BODY_CRC32C_BIT, profile_version % 2 == 0),
        109 => {
            let mut recipe = RecipeBuilder::custom(
                id,
                vec![Shape::uint(32), Shape::uint(16), Shape::uint(16)],
                vec![Shape::status(), Shape::uint(32)],
            );
            let logical = 1;
            let side = 2;
            let shell_width = 3;
            let shell_below_side = recipe.less(shell_width, side);
            let side_limit = recipe.constant(16, 2_049);
            let side_in_range = recipe.less(side, side_limit);
            let preliminary = recipe.bool_and(shell_below_side, side_in_range);
            let safe_side = recipe.select(Shape::uint(16), preliminary, side, shell_width);
            let after_first_shell = recipe.binary(OP_SUB, Shape::uint(16), safe_side, shell_width);
            let second_shell_below_side = recipe.less(shell_width, after_first_shell);
            let valid = recipe.bool_and(preliminary, second_shell_below_side);
            let safe_after_first_shell =
                recipe.select(Shape::uint(16), valid, after_first_shell, shell_width);
            let interior16 =
                recipe.binary(OP_SUB, Shape::uint(16), safe_after_first_shell, shell_width);
            let zero16 = recipe.constant(16, 0);
            let interior = recipe.push(OP_CONCAT, Shape::uint(32), &[zero16, interior16], 0, 0);
            let population = recipe.binary(OP_MUL, Shape::uint(32), interior, interior);
            let zero32 = recipe.constant(32, 0);
            let one32 = recipe.constant(32, 1);
            let nonzero_population = recipe.less(zero32, population);
            let safe_population =
                recipe.select(Shape::uint(32), nonzero_population, population, one32);
            let safe_interior = recipe.select(Shape::uint(32), nonzero_population, interior, one32);
            let reduced = recipe.binary(OP_REM, Shape::uint(32), logical, safe_population);
            let remainder = recipe.binary(OP_REM, Shape::uint(32), reduced, safe_interior);
            let scaled_once = recipe.binary(OP_MUL, Shape::uint(32), safe_interior, remainder);
            let two32 = recipe.constant(32, 2);
            let scaled_twice = recipe.binary(OP_MUL, Shape::uint(32), scaled_once, two32);
            let scaled = recipe.binary(OP_REM, Shape::uint(32), scaled_twice, safe_population);
            let shifted = recipe.binary(OP_ADD, Shape::uint(32), safe_population, scaled);
            let difference = recipe.binary(OP_SUB, Shape::uint(32), shifted, reduced);
            let multiplied = recipe.binary(OP_REM, Shape::uint(32), difference, safe_population);

            let width32 = recipe.push(OP_CONCAT, Shape::uint(32), &[zero16, shell_width], 0, 0);
            let width_factor = recipe.constant(32, 257);
            let width_term = recipe.binary(OP_MUL, Shape::uint(32), width32, width_factor);
            let profile_term = recipe.constant(32, 40_503 * u64::from(profile_version));
            let offset_sum = recipe.binary(OP_ADD, Shape::uint(32), width_term, profile_term);
            let offset = recipe.binary(OP_REM, Shape::uint(32), offset_sum, safe_population);
            let added = recipe.binary(OP_ADD, Shape::uint(32), multiplied, offset);
            let output = recipe.binary(OP_REM, Shape::uint(32), added, safe_population);
            let valid = recipe.select(
                Shape {
                    kind: BOOL,
                    width: 1,
                },
                valid,
                nonzero_population,
                valid,
            );
            let success = recipe.status(0);
            let failure = recipe.status(3);
            let status = recipe.select(Shape::status(), valid, success, failure);
            recipe.finish_main(status, output);
            recipe
        }
        110 => {
            let mut recipe = RecipeBuilder::custom(
                id,
                vec![Shape::uint(32), Shape::uint(16)],
                vec![Shape::status(), Shape::uint(48)],
            );
            let output = recipe.push(OP_CONCAT, Shape::uint(48), &[1, 2], 0, 0);
            let status = recipe.status(0);
            recipe.finish_main(status, output);
            recipe
        }
        111 => crc_fact(
            id,
            if profile_version % 2 == 1 { 32 } else { 64 },
            if profile_version % 2 == 1 {
                BODY_CRC32C_BIT
            } else {
                BODY_CRC32C_BIT
            },
            profile_version % 2 == 0,
        ),
        112 => {
            let mut recipe = RecipeBuilder::custom(
                id,
                vec![
                    Shape::uint(16),
                    Shape::uint(16),
                    Shape {
                        kind: BOOL,
                        width: 1,
                    },
                ],
                vec![
                    Shape::status(),
                    Shape {
                        kind: BOOL,
                        width: 1,
                    },
                ],
            );
            let maximum = recipe.constant(16, 0xffff);
            let can_increment = recipe.less(2, maximum);
            let zero = recipe.constant(16, 0);
            let safe_value = recipe.select(Shape::uint(16), can_increment, 2, zero);
            let one = recipe.constant(16, 1);
            let next = recipe.binary(OP_ADD, Shape::uint(16), safe_value, one);
            let adjacent = recipe.equal(1, next);
            let false_value = recipe.boolean(false);
            let output = recipe.select(
                Shape {
                    kind: BOOL,
                    width: 1,
                },
                adjacent,
                3,
                false_value,
            );
            let output = recipe.select(
                Shape {
                    kind: BOOL,
                    width: 1,
                },
                can_increment,
                output,
                false_value,
            );
            let status = recipe.status(0);
            recipe.finish_main(status, output);
            recipe
        }
        _ => unreachable!("closed fact recipe ID"),
    }
}

fn validate_erasure() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_VALIDATE_ERASURE);
    let state = 1;
    let index = recipe.iteration_byte();
    let position = recipe.read_iteration(state, POSITIONS);
    let count = recipe.read_fixed(state, ERASURE_COUNT);
    let active = recipe.less(index, count);
    let zero = recipe.constant(8, 0);
    let one = recipe.constant(8, 1);
    let limit = recipe.constant(8, 255);
    let position_in_range = recipe.less(position, limit);
    let position_zero = recipe.equal(position, zero);
    let position_shape_ok = recipe.select(
        Shape {
            kind: BOOL,
            width: 1,
        },
        active,
        position_in_range,
        position_zero,
    );
    let index_zero = recipe.equal(index, zero);
    let safe_index = recipe.select(Shape::uint(8), index_zero, one, index);
    let previous_index = recipe.binary(OP_SUB, Shape::uint(8), safe_index, one);
    let previous_position = recipe.read_offset(state, POSITIONS, previous_index);
    let ordered = recipe.less(previous_position, position);
    let truth = recipe.boolean(true);
    let ordered = recipe.select(
        Shape {
            kind: BOOL,
            width: 1,
        },
        index_zero,
        truth,
        ordered,
    );
    let truth = recipe.boolean(true);
    let ordered = recipe.select(
        Shape {
            kind: BOOL,
            width: 1,
        },
        active,
        ordered,
        truth,
    );
    let valid = recipe.bool_and(position_shape_ok, ordered);
    let zeroed = recipe.write(state, position, zero);
    let state = recipe.select(Shape::bytes(STATE_BYTES), active, zeroed, state);
    let success = recipe.status(0);
    let failure = recipe.status(3);
    let status = recipe.select(Shape::status(), valid, success, failure);
    recipe.finish_body(status, state);
    recipe
}

fn erasure_boundary() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_ERASURE_BOUNDARY);
    let state = 1;
    let count = recipe.read_fixed(state, ERASURE_COUNT);
    let boundary = recipe.constant(8, 65);
    let valid = recipe.less(count, boundary);
    let success = recipe.status(0);
    let failure = recipe.status(4);
    let status = recipe.select(Shape::status(), valid, success, failure);
    recipe.finish_body(status, state);
    recipe
}

fn syndrome_byte() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_SYNDROME_BYTE);
    let state = 1;
    let coefficient = recipe.read(state, 2);
    let accumulator = recipe.read_fixed(state, ACCUMULATOR);
    let point = recipe.read_fixed(state, POINT);
    let (state, product) = recipe.gf_multiply(state, accumulator, point);
    let accumulator = recipe.binary(OP_XOR, Shape::uint(8), product, coefficient);
    let state = recipe.write_fixed(state, ACCUMULATOR, accumulator);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn syndrome() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_SYNDROME);
    let state = 1;
    let index = recipe.iteration_byte();
    let point = recipe.alpha(index);
    let zero = recipe.constant(8, 0);
    let state = recipe.write_fixed(state, POINT, point);
    let state = recipe.write_fixed(state, ACCUMULATOR, zero);
    let state = recipe.iterate(state, BODY_SYNDROME_BYTE, 255);
    let value = recipe.read_fixed(state, ACCUMULATOR);
    let state = recipe.write_iteration(state, SYNDROMES, value);
    let state = recipe.write_iteration(state, TRANSFORMED, value);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn gamma_update() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_GAMMA_UPDATE);
    let state = 1;
    let iteration = recipe.iteration_byte();
    let sixty_four = recipe.constant(8, 64);
    let one = recipe.constant(8, 1);
    let degree = recipe.binary(OP_SUB, Shape::uint(8), sixty_four, iteration);
    let previous_degree = recipe.binary(OP_SUB, Shape::uint(8), degree, one);
    let current = recipe.read_offset(state, GAMMA, degree);
    let previous = recipe.read_offset(state, GAMMA, previous_degree);
    let location = recipe.read_fixed(state, LOCATION);
    let (state, product) = recipe.gf_multiply(state, previous, location);
    let coefficient = recipe.binary(OP_XOR, Shape::uint(8), current, product);
    let state = recipe.write_offset(state, GAMMA, degree, coefficient);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn transform_shift() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_TRANSFORM_SHIFT);
    let state = 1;
    let index = recipe.iteration_byte();
    let one = recipe.constant(8, 1);
    let last_value = recipe.constant(8, 63);
    let last = recipe.equal(index, last_value);
    let next_index = recipe.binary(OP_ADD, Shape::uint(8), index, one);
    let safe_next = recipe.select(Shape::uint(8), last, index, next_index);
    let current = recipe.read_iteration(state, TRANSFORMED);
    let next_value = recipe.read_offset(state, TRANSFORMED, safe_next);
    let location = recipe.read_fixed(state, LOCATION);
    let (state, product) = recipe.gf_multiply(state, current, location);
    let transformed = recipe.binary(OP_XOR, Shape::uint(8), product, next_value);
    let zero = recipe.constant(8, 0);
    let value = recipe.select(Shape::uint(8), last, zero, transformed);
    let state = recipe.write_iteration(state, TRANSFORMED, value);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn erasure_locator() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_ERASURE_LOCATOR);
    let state = 1;
    let index = recipe.iteration_byte();
    let count = recipe.read_fixed(state, ERASURE_COUNT);
    let active = recipe.less(index, count);
    let position = recipe.read_iteration(state, POSITIONS);
    let maximum = recipe.constant(8, 254);
    let exponent = recipe.binary(OP_SUB, Shape::uint(8), maximum, position);
    let location = recipe.alpha(exponent);
    let prepared = recipe.write_fixed(state, LOCATION, location);
    let prepared = recipe.iterate(prepared, BODY_GAMMA_UPDATE, 64);
    let prepared = recipe.iterate(prepared, BODY_TRANSFORM_SHIFT, 64);
    let state = recipe.select(Shape::bytes(STATE_BYTES), active, prepared, state);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn bm_discrepancy() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_BM_DISCREPANCY);
    let state = 1;
    let iteration = recipe.iteration_byte();
    let one = recipe.constant(8, 1);
    let index = recipe.binary(OP_ADD, Shape::uint(8), iteration, one);
    let n = recipe.read_fixed(state, OUTER_INDEX);
    let degree = recipe.read_fixed(state, CONNECTION_DEGREE);
    let within_degree = recipe.less_or_equal(index, degree);
    let within_n = recipe.less_or_equal(index, n);
    let active = recipe.bool_and(within_degree, within_n);
    let safe_n = recipe.select(Shape::uint(8), within_n, n, index);
    let source_index = recipe.binary(OP_SUB, Shape::uint(8), safe_n, index);
    let connection = recipe.read_offset(state, CONNECTION, index);
    let syndrome = recipe.read_offset(state, TRANSFORMED, source_index);
    let (state, product) = recipe.gf_multiply(state, connection, syndrome);
    let zero = recipe.constant(8, 0);
    let product = recipe.select(Shape::uint(8), active, product, zero);
    let discrepancy = recipe.read_fixed(state, DISCREPANCY);
    let discrepancy = recipe.binary(OP_XOR, Shape::uint(8), discrepancy, product);
    let state = recipe.write_fixed(state, DISCREPANCY, discrepancy);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn bm_connection() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_BM_CONNECTION);
    let state = 1;
    let index = recipe.iteration_byte();
    let shift = recipe.read_fixed(state, BM_SHIFT);
    let shifted = recipe.less_or_equal(shift, index);
    let safe_index = recipe.select(Shape::uint(8), shifted, index, shift);
    let prior_index = recipe.binary(OP_SUB, Shape::uint(8), safe_index, shift);
    let prior = recipe.read_offset(state, PRIOR_CONNECTION, prior_index);
    let scale = recipe.read_fixed(state, SCALE);
    let (state, product) = recipe.gf_multiply(state, scale, prior);
    let zero = recipe.constant(8, 0);
    let product = recipe.select(Shape::uint(8), shifted, product, zero);
    let old = recipe.read_iteration(state, CONNECTION);
    let updated = recipe.binary(OP_XOR, Shape::uint(8), old, product);
    let state = recipe.write_iteration(state, CONNECTION, updated);
    let flag = recipe.read_fixed(state, CURRENT_IS_ERASURE);
    let one = recipe.constant(8, 1);
    let update = recipe.equal(flag, one);
    let prior = recipe.read_iteration(state, PRIOR_CONNECTION);
    let prior = recipe.select(Shape::uint(8), update, old, prior);
    let state = recipe.write_iteration(state, PRIOR_CONNECTION, prior);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn bm() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_BM);
    let original = 1;
    let n = recipe.iteration_byte();
    let erasures = recipe.read_fixed(original, ERASURE_COUNT);
    let sixty_four = recipe.constant(8, 64);
    let active_length = recipe.binary(OP_SUB, Shape::uint(8), sixty_four, erasures);
    let active = recipe.less(n, active_length);
    let discrepancy = recipe.read_offset(original, TRANSFORMED, n);
    let state = recipe.write_fixed(original, OUTER_INDEX, n);
    let state = recipe.write_fixed(state, DISCREPANCY, discrepancy);
    let one = recipe.constant(8, 1);
    let zero = recipe.constant(8, 0);
    let state = recipe.iterate(state, BODY_BM_DISCREPANCY, 32);
    let discrepancy = recipe.read_fixed(state, DISCREPANCY);
    let discrepancy_zero = recipe.equal(discrepancy, zero);
    let degree = recipe.read_fixed(state, CONNECTION_DEGREE);
    let two_degree = recipe.binary(OP_ADD, Shape::uint(8), degree, degree);
    let update_degree = recipe.less_or_equal(two_degree, n);
    let nonzero = recipe.bool_not(discrepancy_zero);
    let update = recipe.bool_and(nonzero, update_degree);
    let update_byte = recipe.select(Shape::uint(8), update, one, zero);
    let state = recipe.write_fixed(state, CURRENT_IS_ERASURE, update_byte);
    let prior_discrepancy = recipe.read_fixed(state, PRIOR_DISCREPANCY);
    let (state, inverse) = recipe.gf_inverse(state, prior_discrepancy);
    let (state, scale) = recipe.gf_multiply(state, discrepancy, inverse);
    let scale = recipe.select(Shape::uint(8), discrepancy_zero, zero, scale);
    let state = recipe.write_fixed(state, SCALE, scale);
    let state = recipe.iterate(state, BODY_BM_CONNECTION, 33);

    let n_plus_one = recipe.binary(OP_ADD, Shape::uint(8), n, one);
    let safe_n_plus_one = recipe.select(Shape::uint(8), update, n_plus_one, degree);
    let updated_degree = recipe.binary(OP_SUB, Shape::uint(8), safe_n_plus_one, degree);
    let new_degree = recipe.select(Shape::uint(8), update, updated_degree, degree);
    let old_shift = recipe.read_fixed(state, BM_SHIFT);
    let incremented_shift = recipe.binary(OP_ADD, Shape::uint(8), old_shift, one);
    let new_shift = recipe.select(Shape::uint(8), update, one, incremented_shift);
    let old_b = recipe.read_fixed(state, PRIOR_DISCREPANCY);
    let new_b = recipe.select(Shape::uint(8), update, discrepancy, old_b);
    let state = recipe.write_fixed(state, CONNECTION_DEGREE, new_degree);
    let state = recipe.write_fixed(state, BM_SHIFT, new_shift);
    let state = recipe.write_fixed(state, PRIOR_DISCREPANCY, new_b);

    let maximum_degree = recipe.constant(8, 32);
    let degree_ok = recipe.less_or_equal(new_degree, maximum_degree);
    let twice = recipe.binary(OP_ADD, Shape::uint(8), new_degree, new_degree);
    let mixed = recipe.binary(OP_ADD, Shape::uint(8), twice, erasures);
    let mixed_ok = recipe.less_or_equal(mixed, sixty_four);
    let boundary_ok = recipe.bool_and(degree_ok, mixed_ok);
    let truth = recipe.boolean(true);
    let iteration_ok = recipe.select(
        Shape {
            kind: BOOL,
            width: 1,
        },
        active,
        boundary_ok,
        truth,
    );
    let computed = recipe.select(Shape::bytes(STATE_BYTES), active, state, original);
    let success = recipe.status(0);
    let failure = recipe.status(4);
    let status = recipe.select(Shape::status(), iteration_ok, success, failure);
    recipe.finish_body(status, computed);
    recipe
}

fn connection_degree() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_CONNECTION_DEGREE);
    let state = 1;
    let index = recipe.iteration_byte();
    let coefficient = recipe.read_iteration(state, CONNECTION);
    let zero = recipe.constant(8, 0);
    let coefficient_zero = recipe.equal(coefficient, zero);
    let nonzero = recipe.bool_not(coefficient_zero);
    let degree = recipe.read_fixed(state, OBSERVED_DEGREE);
    let degree = recipe.select(Shape::uint(8), nonzero, index, degree);
    let state = recipe.write_fixed(state, OBSERVED_DEGREE, degree);
    let last_index = recipe.constant(8, 32);
    let last = recipe.equal(index, last_index);
    let expected = recipe.read_fixed(state, CONNECTION_DEGREE);
    let matches = recipe.equal(degree, expected);
    let truth = recipe.boolean(true);
    let valid = recipe.select(
        Shape {
            kind: BOOL,
            width: 1,
        },
        last,
        matches,
        truth,
    );
    let success = recipe.status(0);
    let failure = recipe.status(4);
    let status = recipe.select(Shape::status(), valid, success, failure);
    recipe.finish_body(status, state);
    recipe
}

fn locator_convolution() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_LOCATOR_CONVOLUTION);
    let state = 1;
    let index = recipe.iteration_byte();
    let outer = recipe.read_fixed(state, OUTER_INDEX);
    let active = recipe.less_or_equal(index, outer);
    let safe_outer = recipe.select(Shape::uint(8), active, outer, index);
    let gamma_index = recipe.binary(OP_SUB, Shape::uint(8), safe_outer, index);
    let gamma = recipe.read_offset(state, GAMMA, gamma_index);
    let connection = recipe.read_iteration(state, CONNECTION);
    let (state, product) = recipe.gf_multiply(state, gamma, connection);
    let zero = recipe.constant(8, 0);
    let product = recipe.select(Shape::uint(8), active, product, zero);
    let accumulator = recipe.read_fixed(state, ACCUMULATOR);
    let accumulator = recipe.binary(OP_XOR, Shape::uint(8), accumulator, product);
    let state = recipe.write_fixed(state, ACCUMULATOR, accumulator);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn locator() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_LOCATOR);
    let state = 1;
    let index = recipe.iteration_byte();
    let zero = recipe.constant(8, 0);
    let state = recipe.write_fixed(state, OUTER_INDEX, index);
    let state = recipe.write_fixed(state, ACCUMULATOR, zero);
    let state = recipe.iterate(state, BODY_LOCATOR_CONVOLUTION, 33);
    let coefficient = recipe.read_fixed(state, ACCUMULATOR);
    let state = recipe.write_iteration(state, LOCATOR, coefficient);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn locator_degree() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_LOCATOR_DEGREE);
    let state = 1;
    let index = recipe.iteration_byte();
    let coefficient = recipe.read_iteration(state, LOCATOR);
    let zero = recipe.constant(8, 0);
    let coefficient_zero = recipe.equal(coefficient, zero);
    let nonzero = recipe.bool_not(coefficient_zero);
    let degree = recipe.read_fixed(state, OBSERVED_DEGREE);
    let degree = recipe.select(Shape::uint(8), nonzero, index, degree);
    let state = recipe.write_fixed(state, OBSERVED_DEGREE, degree);
    let last_index = recipe.constant(8, 64);
    let last = recipe.equal(index, last_index);
    let erasures = recipe.read_fixed(state, ERASURE_COUNT);
    let unknown = recipe.read_fixed(state, CONNECTION_DEGREE);
    let expected = recipe.binary(OP_ADD, Shape::uint(8), erasures, unknown);
    let matches = recipe.equal(degree, expected);
    let truth = recipe.boolean(true);
    let valid = recipe.select(
        Shape {
            kind: BOOL,
            width: 1,
        },
        last,
        matches,
        truth,
    );
    let success = recipe.status(0);
    let failure = recipe.status(4);
    let status = recipe.select(Shape::status(), valid, success, failure);
    recipe.finish_body(status, state);
    recipe
}

fn chien_evaluate() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_CHIEN_EVALUATE);
    let state = 1;
    let iteration = recipe.iteration_byte();
    let maximum = recipe.constant(8, 64);
    let coefficient_index = recipe.binary(OP_SUB, Shape::uint(8), maximum, iteration);
    let coefficient = recipe.read_offset(state, LOCATOR, coefficient_index);
    let accumulator = recipe.read_fixed(state, ACCUMULATOR);
    let point = recipe.read_fixed(state, POINT);
    let (state, product) = recipe.gf_multiply(state, accumulator, point);
    let accumulator = recipe.binary(OP_XOR, Shape::uint(8), product, coefficient);
    let state = recipe.write_fixed(state, ACCUMULATOR, accumulator);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn chien() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_CHIEN);
    let state = 1;
    let position = recipe.iteration_byte();
    let widened = recipe.widen(position);
    let one16 = recipe.constant(16, 1);
    let exponent = recipe.binary(OP_ADD, Shape::uint(16), widened, one16);
    let point = recipe.alpha(exponent);
    let zero = recipe.constant(8, 0);
    let state = recipe.write_fixed(state, POINT, point);
    let state = recipe.write_fixed(state, ACCUMULATOR, zero);
    let state = recipe.iterate(state, BODY_CHIEN_EVALUATE, 65);
    let value = recipe.read_fixed(state, ACCUMULATOR);
    let root = recipe.equal(value, zero);
    let root_count = recipe.read_fixed(state, ROOT_COUNT);
    let capacity = recipe.constant(8, 64);
    let room = recipe.less(root_count, capacity);
    let safe_count = recipe.select(Shape::uint(8), room, root_count, zero);
    let written = recipe.write_offset(state, CORRECTION_POSITIONS, safe_count, position);
    let state = recipe.select(Shape::bytes(STATE_BYTES), root, written, state);
    let one = recipe.constant(8, 1);
    let increment = recipe.select(Shape::uint(8), root, one, zero);
    let root_count = recipe.binary(OP_ADD, Shape::uint(8), root_count, increment);
    let state = recipe.write_fixed(state, ROOT_COUNT, root_count);
    let no_room = recipe.bool_not(room);
    let root_and_full = recipe.bool_and(root, no_room);
    let room_valid = recipe.bool_not(root_and_full);
    let final_index = recipe.constant(8, 254);
    let final_position = recipe.equal(position, final_index);
    let erasures = recipe.read_fixed(state, ERASURE_COUNT);
    let unknown = recipe.read_fixed(state, CONNECTION_DEGREE);
    let expected = recipe.binary(OP_ADD, Shape::uint(8), erasures, unknown);
    let exact_count = recipe.equal(root_count, expected);
    let truth = recipe.boolean(true);
    let final_valid = recipe.select(
        Shape {
            kind: BOOL,
            width: 1,
        },
        final_position,
        exact_count,
        truth,
    );
    let valid = recipe.bool_and(room_valid, final_valid);
    let success = recipe.status(0);
    let failure = recipe.status(5);
    let status = recipe.select(Shape::status(), valid, success, failure);
    recipe.finish_body(status, state);
    recipe
}

fn erasure_root_search() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_ERASURE_ROOT_SEARCH);
    let state = 1;
    let index = recipe.iteration_byte();
    let root_count = recipe.read_fixed(state, ROOT_COUNT);
    let active = recipe.less(index, root_count);
    let position = recipe.read_iteration(state, CORRECTION_POSITIONS);
    let target = recipe.read_fixed(state, TARGET_POSITION);
    let matches = recipe.equal(position, target);
    let matches = recipe.bool_and(active, matches);
    let found = recipe.read_fixed(state, FOUND);
    let one = recipe.constant(8, 1);
    let zero = recipe.constant(8, 0);
    let found_bool = recipe.equal(found, one);
    let found_bool = recipe.bool_or(found_bool, matches);
    let found = recipe.select(Shape::uint(8), found_bool, one, zero);
    let state = recipe.write_fixed(state, FOUND, found);
    let marked = recipe.write_iteration(state, ROOT_IS_ERASURE, one);
    let state = recipe.select(Shape::bytes(STATE_BYTES), matches, marked, state);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn erasure_root() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_ERASURE_ROOT);
    let original = 1;
    let index = recipe.iteration_byte();
    let count = recipe.read_fixed(original, ERASURE_COUNT);
    let one = recipe.constant(8, 1);
    let active = recipe.less(index, count);
    let target = recipe.read_iteration(original, POSITIONS);
    let zero = recipe.constant(8, 0);
    let state = recipe.write_fixed(original, TARGET_POSITION, target);
    let state = recipe.write_fixed(state, FOUND, zero);
    let state = recipe.iterate(state, BODY_ERASURE_ROOT_SEARCH, 64);
    let found = recipe.read_fixed(state, FOUND);
    let found = recipe.equal(found, one);
    let truth = recipe.boolean(true);
    let required = recipe.select(
        Shape {
            kind: BOOL,
            width: 1,
        },
        active,
        found,
        truth,
    );
    let state = recipe.select(Shape::bytes(STATE_BYTES), active, state, original);
    let success = recipe.status(0);
    let failure = recipe.status(5);
    let status = recipe.select(Shape::status(), required, success, failure);
    recipe.finish_body(status, state);
    recipe
}

fn evaluator_convolution() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_EVALUATOR_CONVOLUTION);
    let state = 1;
    let index = recipe.iteration_byte();
    let outer = recipe.read_fixed(state, OUTER_INDEX);
    let active = recipe.less_or_equal(index, outer);
    let safe_outer = recipe.select(Shape::uint(8), active, outer, index);
    let syndrome_index = recipe.binary(OP_SUB, Shape::uint(8), safe_outer, index);
    let syndrome = recipe.read_offset(state, SYNDROMES, syndrome_index);
    let locator = recipe.read_iteration(state, LOCATOR);
    let (state, product) = recipe.gf_multiply(state, syndrome, locator);
    let zero = recipe.constant(8, 0);
    let product = recipe.select(Shape::uint(8), active, product, zero);
    let accumulator = recipe.read_fixed(state, ACCUMULATOR);
    let accumulator = recipe.binary(OP_XOR, Shape::uint(8), accumulator, product);
    let state = recipe.write_fixed(state, ACCUMULATOR, accumulator);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn evaluator() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_EVALUATOR);
    let state = 1;
    let index = recipe.iteration_byte();
    let zero = recipe.constant(8, 0);
    let state = recipe.write_fixed(state, OUTER_INDEX, index);
    let state = recipe.write_fixed(state, ACCUMULATOR, zero);
    let state = recipe.iterate(state, BODY_EVALUATOR_CONVOLUTION, 65);
    let coefficient = recipe.read_fixed(state, ACCUMULATOR);
    let state = recipe.write_iteration(state, EVALUATOR, coefficient);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn derivative() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_DERIVATIVE);
    let state = 1;
    let index = recipe.iteration_byte();
    let one = recipe.constant(8, 1);
    let source_index = recipe.binary(OP_ADD, Shape::uint(8), index, one);
    let coefficient = recipe.read_offset(state, LOCATOR, source_index);
    let parity = recipe.push(OP_MASK, Shape::uint(8), &[index], 0, 1);
    let zero = recipe.constant(8, 0);
    let even = recipe.equal(parity, zero);
    let coefficient = recipe.select(Shape::uint(8), even, coefficient, zero);
    let state = recipe.write_iteration(state, DERIVATIVE, coefficient);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn magnitude_evaluate() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_MAGNITUDE_EVALUATE);
    let state = 1;
    let iteration = recipe.iteration_byte();
    let maximum = recipe.constant(8, 63);
    let coefficient_index = recipe.binary(OP_SUB, Shape::uint(8), maximum, iteration);
    let evaluator = recipe.read_offset(state, EVALUATOR, coefficient_index);
    let derivative = recipe.read_offset(state, DERIVATIVE, coefficient_index);
    let point = recipe.read_fixed(state, POINT);
    let evaluator_accumulator = recipe.read_fixed(state, EVALUATOR_ACCUMULATOR);
    let derivative_accumulator = recipe.read_fixed(state, DERIVATIVE_ACCUMULATOR);
    let (state, evaluator_product) = recipe.gf_multiply(state, evaluator_accumulator, point);
    let evaluator_accumulator = recipe.binary(OP_XOR, Shape::uint(8), evaluator_product, evaluator);
    let state = recipe.write_fixed(state, EVALUATOR_ACCUMULATOR, evaluator_accumulator);
    let (state, derivative_product) = recipe.gf_multiply(state, derivative_accumulator, point);
    let derivative_accumulator =
        recipe.binary(OP_XOR, Shape::uint(8), derivative_product, derivative);
    let state = recipe.write_fixed(state, DERIVATIVE_ACCUMULATOR, derivative_accumulator);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn magnitude() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_MAGNITUDE);
    let original = 1;
    let index = recipe.iteration_byte();
    let root_count = recipe.read_fixed(original, ROOT_COUNT);
    let active = recipe.less(index, root_count);
    let position = recipe.read_iteration(original, CORRECTION_POSITIONS);
    let maximum = recipe.constant(8, 254);
    let exponent = recipe.binary(OP_SUB, Shape::uint(8), maximum, position);
    let location = recipe.alpha(exponent);
    let widened = recipe.widen(position);
    let one16 = recipe.constant(16, 1);
    let point_exponent = recipe.binary(OP_ADD, Shape::uint(16), widened, one16);
    let point = recipe.alpha(point_exponent);
    let zero = recipe.constant(8, 0);
    let one = recipe.constant(8, 1);
    let state = recipe.write_fixed(original, POINT, point);
    let state = recipe.write_fixed(state, EVALUATOR_ACCUMULATOR, zero);
    let state = recipe.write_fixed(state, DERIVATIVE_ACCUMULATOR, zero);
    let state = recipe.iterate(state, BODY_MAGNITUDE_EVALUATE, 64);
    let numerator = recipe.read_fixed(state, EVALUATOR_ACCUMULATOR);
    let denominator = recipe.read_fixed(state, DERIVATIVE_ACCUMULATOR);
    let denominator_zero = recipe.equal(denominator, zero);
    let denominator_nonzero = recipe.bool_not(denominator_zero);
    let safe_denominator = recipe.select(Shape::uint(8), denominator_nonzero, denominator, one);
    let (state, inverse) = recipe.gf_inverse(state, safe_denominator);
    let (state, quotient) = recipe.gf_multiply(state, numerator, inverse);
    let (state, magnitude) = recipe.gf_multiply(state, location, quotient);
    let is_erasure = recipe.read_iteration(state, ROOT_IS_ERASURE);
    let is_erasure = recipe.equal(is_erasure, one);
    let magnitude_zero = recipe.equal(magnitude, zero);
    let magnitude_nonzero = recipe.bool_not(magnitude_zero);
    let unknown_valid = recipe.bool_or(is_erasure, magnitude_nonzero);
    let valid_root = recipe.bool_and(denominator_nonzero, unknown_valid);
    let truth = recipe.boolean(true);
    let valid = recipe.select(
        Shape {
            kind: BOOL,
            width: 1,
        },
        active,
        valid_root,
        truth,
    );
    let written = recipe.write_iteration(state, CORRECTION_MAGNITUDES, magnitude);
    let written = recipe.write_iteration(written, EVALUATOR, magnitude);
    let written = recipe.write_iteration(written, DERIVATIVE, location);
    let state = recipe.select(Shape::bytes(STATE_BYTES), active, written, state);
    let unknown = recipe.bool_not(is_erasure);
    let count_error = recipe.bool_and(active, unknown);
    let count_error = recipe.bool_and(count_error, magnitude_nonzero);
    let error_count = recipe.read_fixed(state, ERROR_COUNT);
    let increment = recipe.select(Shape::uint(8), count_error, one, zero);
    let error_count = recipe.binary(OP_ADD, Shape::uint(8), error_count, increment);
    let state = recipe.write_fixed(state, ERROR_COUNT, error_count);
    let last_index = recipe.constant(8, 63);
    let last = recipe.equal(index, last_index);
    let degree = recipe.read_fixed(state, CONNECTION_DEGREE);
    let exact_errors = recipe.equal(error_count, degree);
    let erasures = recipe.read_fixed(state, ERASURE_COUNT);
    let twice = recipe.binary(OP_ADD, Shape::uint(8), error_count, error_count);
    let mixed = recipe.binary(OP_ADD, Shape::uint(8), twice, erasures);
    let maximum = recipe.constant(8, 64);
    let bound = recipe.less_or_equal(mixed, maximum);
    let final_ok = recipe.bool_and(exact_errors, bound);
    let truth = recipe.boolean(true);
    let final_ok = recipe.select(
        Shape {
            kind: BOOL,
            width: 1,
        },
        last,
        final_ok,
        truth,
    );
    let valid = recipe.bool_and(valid, final_ok);
    let success = recipe.status(0);
    let failure = recipe.status(5);
    let status = recipe.select(Shape::status(), valid, success, failure);
    recipe.finish_body(status, state);
    recipe
}

fn apply_correction() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_APPLY);
    let state = 1;
    let index = recipe.iteration_byte();
    let root_count = recipe.read_fixed(state, ROOT_COUNT);
    let active = recipe.less(index, root_count);
    let position = recipe.read_iteration(state, CORRECTION_POSITIONS);
    let magnitude = recipe.read_iteration(state, CORRECTION_MAGNITUDES);
    let observed = recipe.read(state, position);
    let corrected = recipe.binary(OP_XOR, Shape::uint(8), observed, magnitude);
    let written = recipe.write(state, position, corrected);
    let state = recipe.select(Shape::bytes(STATE_BYTES), active, written, state);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn correction_syndrome() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_CORRECTION_SYNDROME);
    let state = 1;
    let index = recipe.iteration_byte();
    let root_count = recipe.read_fixed(state, ROOT_COUNT);
    let active = recipe.less(index, root_count);
    let contribution = recipe.read_iteration(state, EVALUATOR);
    let zero = recipe.constant(8, 0);
    let selected = recipe.select(Shape::uint(8), active, contribution, zero);
    let accumulator = recipe.read_fixed(state, ACCUMULATOR);
    let accumulator = recipe.binary(OP_XOR, Shape::uint(8), accumulator, selected);
    let state = recipe.write_fixed(state, ACCUMULATOR, accumulator);
    let location = recipe.read_iteration(state, DERIVATIVE);
    let (state, next) = recipe.gf_multiply(state, contribution, location);
    let state = recipe.write_iteration(state, EVALUATOR, next);
    let status = recipe.status(0);
    recipe.finish_body(status, state);
    recipe
}

fn correction_syndromes() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::body(BODY_CORRECTION_SYNDROMES);
    let state = 1;
    let syndrome = recipe.read_iteration(state, SYNDROMES);
    let state = recipe.write_fixed(state, ACCUMULATOR, syndrome);
    let state = recipe.iterate(state, BODY_CORRECTION_SYNDROME, 64);
    let accumulator = recipe.read_fixed(state, ACCUMULATOR);
    let zero = recipe.constant(8, 0);
    let valid = recipe.equal(accumulator, zero);
    let success = recipe.status(0);
    let failure = recipe.status(5);
    let status = recipe.select(Shape::status(), valid, success, failure);
    recipe.finish_body(status, state);
    recipe
}

fn rs_decode() -> RecipeBuilder {
    let mut recipe = RecipeBuilder::main(RECIPE_RS_DECODE);
    let observation = 1;
    let count_bytes = 2;
    let positions = 3;
    let prefix = recipe.push(
        OP_CONCAT,
        Shape::bytes(319),
        &[observation, positions],
        0,
        0,
    );
    let zero_suffix = recipe.zero_bytes(1_217);
    let mut state = recipe.push(
        OP_CONCAT,
        Shape::bytes(STATE_BYTES),
        &[prefix, zero_suffix],
        0,
        0,
    );
    let zero = recipe.constant(8, 0);
    let one = recipe.constant(8, 1);
    let zero16 = recipe.constant(16, 0);
    let count = recipe.read(count_bytes, zero16);
    state = recipe.write_fixed(state, ERASURE_COUNT, count);
    state = recipe.iterate(state, BODY_ERASURE_BOUNDARY, 1);
    state = recipe.iterate(state, BODY_VALIDATE_ERASURE, 64);

    state = recipe.iterate(state, BODY_SYNDROME, 64);
    state = recipe.write_fixed(state, GAMMA, one);
    state = recipe.write_fixed(state, CONNECTION, one);
    state = recipe.write_fixed(state, PRIOR_CONNECTION, one);
    state = recipe.write_fixed(state, CONNECTION_DEGREE, zero);
    state = recipe.write_fixed(state, BM_SHIFT, one);
    state = recipe.write_fixed(state, PRIOR_DISCREPANCY, one);

    state = recipe.iterate(state, BODY_ERASURE_LOCATOR, 64);
    state = recipe.iterate(state, BODY_BM, 64);
    state = recipe.write_fixed(state, OBSERVED_DEGREE, zero);
    state = recipe.iterate(state, BODY_CONNECTION_DEGREE, 33);

    state = recipe.iterate(state, BODY_LOCATOR, 65);
    state = recipe.write_fixed(state, OBSERVED_DEGREE, zero);
    state = recipe.iterate(state, BODY_LOCATOR_DEGREE, 65);

    state = recipe.write_fixed(state, ROOT_COUNT, zero);
    state = recipe.iterate(state, BODY_CHIEN, 255);
    state = recipe.iterate(state, BODY_ERASURE_ROOT, 64);

    state = recipe.iterate(state, BODY_EVALUATOR, 64);
    state = recipe.iterate(state, BODY_DERIVATIVE, 64);
    state = recipe.write_fixed(state, ERROR_COUNT, zero);
    state = recipe.iterate(state, BODY_MAGNITUDE, 64);
    state = recipe.iterate(state, BODY_APPLY, 64);

    state = recipe.iterate(state, BODY_CORRECTION_SYNDROMES, 64);
    let length = recipe.constant(16, 191);
    let output = recipe.push(OP_SLICE, Shape::bytes(191), &[state, zero16, length], 0, 0);
    let status = recipe.status(0);
    recipe.finish_main(status, output);
    recipe
}

fn build_recipes() -> Vec<BuiltRecipe> {
    let mut recipes = Vec::new();
    for builder in [
        validate_erasure(),
        erasure_boundary(),
        syndrome_byte(),
        syndrome(),
        gamma_update(),
        transform_shift(),
        erasure_locator(),
        bm_discrepancy(),
        bm_connection(),
        bm(),
        connection_degree(),
        locator_convolution(),
        locator(),
        locator_degree(),
        chien_evaluate(),
        chien(),
        erasure_root_search(),
        erasure_root(),
        evaluator_convolution(),
        evaluator(),
        derivative(),
        magnitude_evaluate(),
        magnitude(),
        apply_correction(),
        correction_syndrome(),
        correction_syndromes(),
        rs_decode(),
    ] {
        let recipe = finalize(builder, &recipes);
        recipes.push(recipe);
    }
    recipes
}

/// Raw generic-VM package containing the exact field primitives used by the
/// full RS recipe.
pub fn build_rs_recipe_primitives(profile_version: u16) -> Result<Vec<u8>> {
    let first = finalize(gf_round(), &[]);
    let second = finalize(inverse_round(), std::slice::from_ref(&first));
    let tables = rs_tables()
        .into_iter()
        .filter(|(id, ..)| matches!(*id, TABLE_EXP | TABLE_LOG))
        .collect();
    let raw = encode_package_with_tables(profile_version, &[first, second], tables);
    decode_recipe_package(&raw, profile_version)?;
    Ok(raw)
}

/// Build and independently parse the hash-bound decoder30 recipe manifestation.
///
/// Admission still requires the separate closure audit; successful parsing is
/// not a claim that this particular DAG implements every frozen decoder case.
pub fn build_rs_decoder_recipe_package(profile_version: u16) -> Result<Vec<u8>> {
    if !(5..=6).contains(&profile_version) {
        return Err(BootstrapError {
            code: crate::RejectCode::Recipe,
            offset: None,
        });
    }
    let recipes = build_recipes();
    let raw = encode_package(profile_version, &recipes);
    decode_recipe_package(&raw, profile_version)?;
    Ok(raw)
}

/// Build the complete EH72 decoder/encoder package and admit it through the
/// frozen parser. Profiles 1 through 4 share the same transport procedures.
pub fn build_eh_recipe_package(profile_version: u16) -> Result<Vec<u8>> {
    if profile_version == 7 {
        return build_r3_recipe_package();
    }
    if !(1..=4).contains(&profile_version) && profile_version != 7 {
        return Err(BootstrapError {
            code: crate::RejectCode::Recipe,
            offset: None,
        });
    }
    let mut recipes = Vec::new();
    let mut builders = vec![
        eh_scan(),
        eh_validate(),
        eh_candidate(),
        eh_output(),
        eh_decode(),
    ];
    if profile_version % 2 == 0 {
        builders.push(combined_crc_bit());
    } else {
        builders.push(crc32c_bit());
    }
    builders.push(crc_byte(BODY_CRC32C_BYTE, BODY_CRC32C_BIT));
    builders.push(eh_parity_step());
    builders.push(eh_encode_step());
    for id in 101..=107 {
        builders.push(fact_recipe(id, profile_version));
    }
    builders.push(eh_encode());
    for id in 109..=112 {
        builders.push(fact_recipe(id, profile_version));
    }
    for builder in builders {
        let recipe = finalize(builder, &recipes);
        recipes.push(recipe);
    }
    let raw = encode_package_with_tables(profile_version, &recipes, eh_tables());
    decode_recipe_package(&raw, profile_version)?;
    Ok(raw)
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct R3RecipePackageMetrics {
    pub package_bytes: u32,
    pub package_sha256: String,
    pub node_count: u32,
    pub edge_count: u32,
    pub table_payload_bytes: u32,
    pub maximum_primitive_steps: u64,
    pub peak_scratch_bytes: u32,
    pub repetition_recipe_bytes: u32,
    pub repetition_recipe_nodes: u32,
    pub repetition_primitive_steps: u64,
    pub repetition_peak_scratch_bytes: u64,
    pub route_worked_held_primitive_steps_per_sector: u64,
    pub route_peak_scratch_bytes: u64,
    pub projected_route_prefix_bytes_per_sector: u32,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct R3RecipeResourceRow {
    pub recipe_id: u16,
    pub encoded_bytes: u32,
    pub node_count: u32,
    pub primitive_steps: u64,
    pub peak_scratch_bytes: u64,
}

fn r3_recipe_builders() -> Vec<RecipeBuilder> {
    let mut builders = vec![
        eh_scan(),
        eh_validate(),
        eh_candidate(),
        eh_output(),
        eh_decode(),
        crc32c_bit(),
        crc_byte(BODY_CRC32C_BYTE, BODY_CRC32C_BIT),
        eh_parity_step(),
        eh_encode_step(),
    ];
    for id in 101..=107 {
        builders.push(fact_recipe(id, 7));
    }
    builders.push(eh_encode());
    for id in 109..=112 {
        builders.push(fact_recipe(id, 7));
    }
    builders.push(r3_repetition_symbol_counts());
    builders
}

pub fn r3_recipe_resource_rows() -> Result<Vec<R3RecipeResourceRow>> {
    let mut recipes = Vec::new();
    for builder in r3_recipe_builders() {
        recipes.push(finalize(builder, &recipes));
    }
    let raw = encode_package_with_tables(7, &recipes, r3_eh_tables());
    let package = decode_recipe_package(&raw, 7)?;
    [30_u16, 109, 110, 113]
        .into_iter()
        .map(|recipe_id| {
            let recipe = recipes
                .iter()
                .find(|recipe| recipe.builder.id == recipe_id)
                .expect("frozen resource recipe");
            Ok(R3RecipeResourceRow {
                recipe_id,
                encoded_bytes: u32::try_from(encode_recipe(recipe).len())
                    .expect("recipe package bound"),
                node_count: u32::try_from(recipe.builder.nodes.len()).expect("recipe node bound"),
                primitive_steps: package
                    .recipe_primitive_steps(recipe_id)
                    .expect("recipe primitive steps"),
                peak_scratch_bytes: package
                    .recipe_peak_scratch_bytes(recipe_id)
                    .expect("recipe scratch"),
            })
        })
        .collect()
}

/// Build the compact v7 recipient package: legacy EH/common primitives and
/// map recipes remain unchanged, table 17 binds exact smallest-B values, and
/// recipe 113 decides one repetition symbol from validated zero/one counts.
pub fn build_r3_recipe_package() -> Result<Vec<u8>> {
    let mut recipes = Vec::new();
    for builder in r3_recipe_builders() {
        recipes.push(finalize(builder, &recipes));
    }
    let raw = encode_package_with_tables(7, &recipes, r3_eh_tables());
    decode_recipe_package(&raw, 7)?;
    Ok(raw)
}

pub fn r3_recipe_package_metrics() -> Result<R3RecipePackageMetrics> {
    let mut recipes = Vec::new();
    for builder in r3_recipe_builders() {
        recipes.push(finalize(builder, &recipes));
    }
    let repetition = recipes
        .iter()
        .find(|recipe| recipe.builder.id == 113)
        .expect("recipe 113");
    let repetition_recipe_bytes = encode_recipe(repetition).len() as u32;
    let raw = encode_package_with_tables(7, &recipes, r3_eh_tables());
    let package = decode_recipe_package(&raw, 7)?;
    // Archived prefix plus exact owner-projected deltas: package table and
    // recipe bytes are embedded once more, while examples/DEFINE shrink 47 B.
    let projected_route_prefix_bytes_per_sector = 27_714_u32
        .checked_add(272)
        .and_then(|value| value.checked_add(repetition_recipe_bytes))
        .and_then(|value| value.checked_add(280))
        .and_then(|value| value.checked_sub(47))
        .expect("closed route projection");
    let route_recipe_ids = [
        101_u16, 102, 103, 104, 105, 106, 107, 113, 109, 110, 111, 112,
    ];
    let route_worked_held_primitive_steps_per_sector = route_recipe_ids
        .iter()
        .try_fold(0_u64, |sum, recipe_id| {
            package
                .recipe_primitive_steps(*recipe_id)
                .and_then(|steps| steps.checked_mul(2))
                .and_then(|steps| sum.checked_add(steps))
        })
        .expect("closed route worked/held charge");
    let route_peak_scratch_bytes = route_recipe_ids
        .iter()
        .filter_map(|recipe_id| package.recipe_peak_scratch_bytes(*recipe_id))
        .max()
        .expect("route recipe scratch");
    Ok(R3RecipePackageMetrics {
        package_bytes: raw.len() as u32,
        package_sha256: format!("{:x}", Sha256::digest(&raw)),
        node_count: u32::from_be_bytes(raw[20..24].try_into().unwrap()),
        edge_count: u32::from_be_bytes(raw[24..28].try_into().unwrap()),
        table_payload_bytes: u32::from_be_bytes(raw[28..32].try_into().unwrap()),
        maximum_primitive_steps: u64::from_be_bytes(raw[36..44].try_into().unwrap()),
        peak_scratch_bytes: u32::from_be_bytes(raw[44..48].try_into().unwrap()),
        repetition_recipe_bytes,
        repetition_recipe_nodes: repetition.builder.nodes.len() as u32,
        repetition_primitive_steps: package
            .recipe_primitive_steps(113)
            .expect("recipe 113 steps"),
        repetition_peak_scratch_bytes: package
            .recipe_peak_scratch_bytes(113)
            .expect("recipe 113 scratch"),
        route_worked_held_primitive_steps_per_sector,
        route_peak_scratch_bytes,
        projected_route_prefix_bytes_per_sector,
    })
}

/// Execute the route-bound EH72 decoder30 ABI.
pub fn evaluate_eh_decoder_recipe(
    package: &RecipePackage,
    observation: &[u8],
    erasures: &[u8],
) -> std::result::Result<RecipeOutcome, BootstrapError> {
    let mut positions = vec![0_u8; 3];
    let count = if erasures.len() > 3 {
        4
    } else {
        positions[..erasures.len()].copy_from_slice(erasures);
        erasures.len() as u8
    };
    evaluate_recipe(
        package,
        RECIPE_EH_DECODE,
        &[
            RecipeValue::Bytes(observation.to_vec()),
            RecipeValue::Bytes(vec![count]),
            RecipeValue::Bytes(positions),
        ],
    )
}

/// Execute the route-bound transport encoder108 ABI.
pub fn evaluate_transport_encoder_recipe(
    package: &RecipePackage,
    source: &[u8],
) -> std::result::Result<RecipeOutcome, BootstrapError> {
    evaluate_recipe(
        package,
        RECIPE_TRANSPORT_ENCODE,
        &[RecipeValue::Bytes(source.to_vec())],
    )
}

/// Normalize the variable external erasure list into the recipe's fixed,
/// explicitly taught `(positions, prefix-active)` interface and execute it.
pub fn evaluate_rs_decoder_recipe(
    package: &RecipePackage,
    observation: &[u8],
    erasures: &[u16],
) -> std::result::Result<RecipeOutcome, BootstrapError> {
    let mut positions = vec![0_u8; 64];
    let count = if erasures.len() > 64 {
        positions[0] = 255;
        65
    } else {
        for (index, position) in erasures.iter().copied().enumerate() {
            positions[index] = u8::try_from(position).unwrap_or(255);
        }
        erasures.len() as u8
    };
    evaluate_recipe(
        package,
        RECIPE_RS_DECODE,
        &[
            RecipeValue::Bytes(observation.to_vec()),
            RecipeValue::Bytes(vec![count]),
            RecipeValue::Bytes(positions),
        ],
    )
}

/// Execute a body recipe for a direct primitive KAT.
pub fn evaluate_rs_recipe_body(
    package: &RecipePackage,
    recipe_id: u16,
    state: Vec<u8>,
) -> std::result::Result<RecipeOutcome, BootstrapError> {
    evaluate_recipe(
        package,
        recipe_id,
        &[
            RecipeValue::Bytes(state),
            RecipeValue::Uint {
                width: 64,
                value: 0,
            },
        ],
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::candidate::{decode_rs255_191, encode_rs255_191};

    fn run_body(
        package: &RecipePackage,
        recipe_id: u16,
        mut state: Vec<u8>,
        count: usize,
    ) -> Vec<u8> {
        for iteration in 0..count {
            let outcome = evaluate_recipe(
                package,
                recipe_id,
                &[
                    RecipeValue::Bytes(state),
                    RecipeValue::Uint {
                        width: 64,
                        value: iteration as u64,
                    },
                ],
            )
            .unwrap();
            assert_eq!(outcome.status, 0, "body {recipe_id}");
            let RecipeValue::Bytes(next) = outcome.outputs.into_iter().next().unwrap() else {
                panic!("state")
            };
            state = next;
        }
        state
    }

    #[test]
    fn every_rs_recipe_prefix_is_statically_valid() {
        let recipes = build_recipes();
        for count in 1..=recipes.len() {
            let raw = encode_package(5, &recipes[..count]);
            decode_recipe_package(&raw, 5)
                .unwrap_or_else(|error| {
                    let recipe = &recipes[count - 1];
                    panic!(
                        "recipe prefix {count} rejected: {error:?}; bytes={} nodes={} edges={} steps={} scratch={}",
                        raw.len(),
                        recipe.builder.nodes.len(),
                        recipe.edges,
                        recipe.steps,
                        recipe.scratch,
                    )
                });
        }
    }

    #[test]
    fn every_eh_recipe_prefix_is_statically_valid() {
        let mut builders = vec![
            eh_scan(),
            eh_validate(),
            eh_candidate(),
            eh_output(),
            eh_decode(),
            crc32c_bit(),
            crc_byte(BODY_CRC32C_BYTE, BODY_CRC32C_BIT),
            eh_parity_step(),
            eh_encode_step(),
        ];
        for id in 101..=107 {
            builders.push(fact_recipe(id, 1));
        }
        builders.push(eh_encode());
        for id in 109..=112 {
            builders.push(fact_recipe(id, 1));
        }
        let mut recipes = Vec::new();
        for builder in builders {
            let recipe = finalize(builder, &recipes);
            recipes.push(recipe);
            let raw = encode_package_with_tables(1, &recipes, eh_tables());
            decode_recipe_package(&raw, 1).unwrap_or_else(|error| {
                let last = recipes.last().unwrap();
                panic!(
                    "EH recipe {} rejected {error:?}: nodes={} steps={} bytes={}",
                    last.builder.id,
                    last.builder.nodes.len(),
                    last.steps,
                    raw.len()
                )
            });
        }
    }

    #[test]
    fn single_error_recipe_bm_matches_reference_trace() {
        let raw = build_rs_decoder_recipe_package(5).unwrap();
        let package = decode_recipe_package(&raw, 5).unwrap();
        let data = std::array::from_fn(|index| index as u8);
        let encoded = encode_rs255_191(&data);
        let mut changed = encoded;
        changed[0] ^= 0x53;
        let trace = decode_rs255_191(&changed, &[]).trace.unwrap();
        let mut state = vec![0; STATE_BYTES as usize];
        state[..255].copy_from_slice(&changed);
        state[GAMMA as usize] = 1;
        state[CONNECTION as usize] = 1;
        state[PRIOR_CONNECTION as usize] = 1;
        state[BM_SHIFT as usize] = 1;
        state[PRIOR_DISCREPANCY as usize] = 1;
        state = run_body(&package, BODY_SYNDROME, state, 64);
        assert_eq!(
            &state[SYNDROMES as usize..SYNDROMES as usize + 64],
            &trace.syndromes
        );
        state[LOOP_COUNTER_0 as usize] = 0;
        state = run_body(&package, BODY_BM, state, 64);
        assert_eq!(
            &state[CONNECTION as usize..CONNECTION as usize + trace.unknown_error_locator.len()],
            trace.unknown_error_locator.as_slice()
        );
        assert!(
            state
                [CONNECTION as usize + trace.unknown_error_locator.len()..CONNECTION as usize + 33]
                .iter()
                .all(|value| *value == 0)
        );
        assert_eq!(
            state[CONNECTION_DEGREE as usize] as usize,
            trace.unknown_error_locator.len() - 1
        );
        state[LOOP_COUNTER_0 as usize] = 0;
        state = run_body(&package, BODY_LOCATOR, state, 65);
        assert_eq!(
            &state[LOCATOR as usize..LOCATOR as usize + trace.full_locator.len()],
            trace.full_locator.as_slice()
        );
        state[LOOP_COUNTER_0 as usize] = 0;
        state[ROOT_COUNT as usize] = 0;
        state = run_body(&package, BODY_CHIEN, state, 255);
        assert_eq!(
            &state[CORRECTION_POSITIONS as usize
                ..CORRECTION_POSITIONS as usize + trace.correction_positions.len()],
            trace
                .correction_positions
                .iter()
                .map(|value| *value as u8)
                .collect::<Vec<_>>()
        );
        state[LOOP_COUNTER_0 as usize] = 0;
        state = run_body(&package, BODY_EVALUATOR, state, 64);
        assert_eq!(
            &state[EVALUATOR as usize..EVALUATOR as usize + 64],
            &trace.evaluator
        );
        state[LOOP_COUNTER_0 as usize] = 0;
        state = run_body(&package, BODY_DERIVATIVE, state, 64);
        state[LOOP_COUNTER_0 as usize] = 0;
        state = run_body(&package, BODY_MAGNITUDE, state, 64);
        assert_eq!(
            &state[CORRECTION_MAGNITUDES as usize
                ..CORRECTION_MAGNITUDES as usize + trace.correction_magnitudes.len()],
            trace.correction_magnitudes.as_slice()
        );
    }
}
