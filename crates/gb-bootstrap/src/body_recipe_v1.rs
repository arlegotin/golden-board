//! Independently constructed generic programs from `spec/body-recipe-v1.md`.
//!
//! These builders have no codec callback. Every decoded byte is produced by
//! the ordinary recipe VM. Construction is fresh, ordered, and unoptimized.

use std::cell::RefCell;

use crate::candidate_recipe::{
    EncodedTable, RecipeBuilder, Shape, encode_package_with_tables, fact_recipe, finalize,
    r3_eh_tables, r3_recipe_builders,
};
use crate::recipe::decode_recipe_package;
use crate::recipe_wire_v1::encode_recipe_package_v1;
use crate::{BootstrapError, RejectCode, Result};

const B: u16 = 16_384;
const S: u32 = 32_782;
const N: u16 = 32_768;
const L: u16 = 32_770;
const P: u16 = 32_772;
const O: u16 = 32_774;
const D: u16 = 32_776;
const R: u16 = 32_778;
const F: u16 = 32_779;
const K: u16 = 32_780;
const E: u16 = 32_781;
const BOOLEAN: Shape = Shape { kind: 1, width: 1 };

// Interior mutability lets nested expressions retain the specification's
// left-to-right argument evaluation. Each borrow starts after its arguments
// have been constructed; no borrow spans another helper invocation.
struct Builder(RefCell<RecipeBuilder>);

impl Builder {
    fn new(id: u16, inputs: Vec<Shape>, outputs: Vec<Shape>) -> Self {
        Self(RefCell::new(RecipeBuilder::custom(id, inputs, outputs)))
    }

    fn emit(&self, op: u8, shape: Shape, args: &[u16], aux: u16, imm: u64) -> u16 {
        self.0.borrow_mut().push(op, shape, args, aux, imm)
    }

    fn u(&self, width: u32, value: u64) -> u16 {
        self.0.borrow_mut().constant(width, value)
    }

    fn u8(&self, value: u8) -> u16 {
        self.u(8, u64::from(value))
    }

    fn u16(&self, value: u16) -> u16 {
        self.u(16, u64::from(value))
    }

    fn boolean(&self, value: bool) -> u16 {
        self.0.borrow_mut().boolean(value)
    }

    fn status(&self, value: u16) -> u16 {
        self.0.borrow_mut().status(value)
    }

    fn table(&self, id: u16, width: u32) -> u16 {
        self.0.borrow_mut().table(id, width)
    }

    fn arithmetic(&self, opcode: u8, width: u32, a: u16, b: u16) -> u16 {
        self.emit(opcode, Shape::uint(width), &[a, b], 0, 0)
    }

    fn add(&self, width: u32, a: u16, b: u16) -> u16 {
        self.arithmetic(6, width, a, b)
    }

    fn sub(&self, width: u32, a: u16, b: u16) -> u16 {
        self.arithmetic(7, width, a, b)
    }

    fn shl(&self, width: u32, a: u16, b: u16) -> u16 {
        self.arithmetic(15, width, a, b)
    }

    fn shr(&self, width: u32, a: u16, b: u16) -> u16 {
        self.arithmetic(16, width, a, b)
    }

    fn mask(&self, width: u32, value: u16, mask: u64) -> u16 {
        self.emit(14, Shape::uint(width), &[value], 0, mask)
    }

    fn eq(&self, a: u16, b: u16) -> u16 {
        self.emit(17, BOOLEAN, &[a, b], 0, 0)
    }

    fn lt(&self, a: u16, b: u16) -> u16 {
        self.emit(18, BOOLEAN, &[a, b], 0, 0)
    }

    fn select(&self, shape: Shape, condition: u16, yes: u16, no: u16) -> u16 {
        self.emit(23, shape, &[condition, yes, no], 0, 0)
    }

    fn cat(&self, shape: Shape, a: u16, b: u16) -> u16 {
        self.emit(4, shape, &[a, b], 0, 0)
    }

    fn read(&self, state: u16, index: u16) -> u16 {
        self.emit(19, Shape::uint(8), &[state, index], 0, 0)
    }

    fn write(&self, state: u16, index: u16, value: u16) -> u16 {
        self.emit(20, Shape::bytes(S), &[state, index, value], 0, 0)
    }

    fn look(&self, shape: Shape, table: u16, index: u16) -> u16 {
        self.emit(21, shape, &[table, index], 0, 0)
    }

    fn not(&self, value: u16) -> u16 {
        self.eq(value, self.boolean(false))
    }

    fn and(&self, a: u16, b: u16) -> u16 {
        self.select(BOOLEAN, a, b, self.boolean(false))
    }

    fn or(&self, a: u16, b: u16) -> u16 {
        self.select(BOOLEAN, a, self.boolean(true), b)
    }

    fn le(&self, a: u16, b: u16) -> u16 {
        self.not(self.lt(b, a))
    }

    fn all(&self, values: &[u16]) -> u16 {
        let mut result = values[0];
        for &value in &values[1..] {
            result = self.and(result, value);
        }
        result
    }

    fn read_fixed(&self, state: u16, offset: u16) -> u16 {
        self.read(state, self.u16(offset))
    }

    fn write_fixed(&self, state: u16, offset: u16, value: u16) -> u16 {
        self.write(state, self.u16(offset), value)
    }

    fn read_uint(&self, state: u16, offset: u16, count: u16) -> u16 {
        let mut value = self.read_fixed(state, offset);
        let mut width = 8;
        for i in 1..count {
            let following = self.read_fixed(state, offset + i);
            width += 8;
            value = self.cat(Shape::uint(width), value, following);
        }
        value
    }

    fn write_uint(&self, mut state: u16, offset: u16, count: u16, value: u16) -> u16 {
        let width = 8 * u32::from(count);
        let identity = self.table(5, 8);
        for i in 0..count {
            let shift = 8 * u32::from(count - i - 1);
            let shifted = if shift == 0 {
                value
            } else {
                self.shr(width, value, self.u(width, u64::from(shift)))
            };
            let masked = self.mask(width, shifted, 255);
            let byte = self.look(Shape::uint(8), identity, masked);
            state = self.write_fixed(state, offset + i, byte);
        }
        state
    }

    fn widen(&self, value: u16) -> u16 {
        self.look(Shape::uint(16), self.table(3, 16), value)
    }

    fn safe_input(&self, index: u16) -> u16 {
        let safe = self.select(
            Shape::uint(16),
            self.lt(index, self.u16(B)),
            index,
            self.u16(0),
        );
        self.read(1, safe)
    }

    fn iterate(&self, state: u16, count: u64) -> u16 {
        self.emit(22, Shape::bytes(S), &[state], 201, count)
    }

    fn finish(&self, status: u16, values: &[u16]) {
        self.emit(5, Shape::status(), &[status], 1, 0);
        for (index, value) in values.iter().copied().enumerate() {
            self.emit(5, Shape::status(), &[value], (index + 2) as u16, 0);
        }
    }

    fn zero_bytes(&self, length: u16) -> u16 {
        let table = self.table(4, 1);
        let zero = self.u8(0);
        let first = self.look(Shape::bytes(1), table, zero);
        let mut powers = vec![(1u16, first)];
        while powers.last().expect("initial power").0 <= length / 2 {
            let (width, value) = *powers.last().expect("initial power");
            powers.push((
                2 * width,
                self.cat(Shape::bytes(2 * u32::from(width)), value, value),
            ));
        }
        let mut remaining = length;
        let mut output = None;
        for (width, value) in powers.into_iter().rev() {
            if width <= remaining {
                output = Some(match output {
                    None => value,
                    Some(prefix) => self.cat(
                        Shape::bytes(u32::from(length - remaining + width)),
                        prefix,
                        value,
                    ),
                });
                remaining -= width;
            }
        }
        assert_eq!(remaining, 0);
        output.expect("positive fixed construction length")
    }

    fn initialize(&self, encoded: u16, encoded_length: u16, extra: Option<u16>) -> (u16, u16) {
        let target = self.read_uint(encoded, 1, 2);
        let mut good = self.all(&[
            self.le(self.u16(3), encoded_length),
            self.le(encoded_length, self.u16(B)),
            self.le(target, self.u16(B)),
            self.eq(self.read_fixed(encoded, 0), self.u8(3)),
        ]);
        if let Some(extra) = extra {
            good = self.and(good, extra);
        }
        let mut state = self.cat(Shape::bytes(S), encoded, self.zero_bytes(B + 14));
        state = self.write_uint(state, N, 2, encoded_length);
        state = self.write_uint(state, L, 2, target);
        state = self.write_fixed(state, P + 1, self.u8(3));
        state = self.write_fixed(
            state,
            E,
            self.select(Shape::uint(8), good, self.u8(1), self.u8(0)),
        );
        (state, target)
    }

    fn finalize(
        &self,
        state: u16,
        encoded_length: u16,
        target: u16,
        output_length: u16,
        include_length: bool,
    ) {
        let good = self.all(&[
            self.eq(self.read_uint(state, P, 2), encoded_length),
            self.eq(self.read_uint(state, O, 2), target),
            self.eq(self.read_fixed(state, R), self.u8(0)),
            self.eq(self.read_fixed(state, F), self.u8(0)),
        ]);
        let status = self.select(Shape::status(), good, self.status(0), self.status(3));
        let decoded = self.emit(
            3,
            Shape::bytes(u32::from(output_length)),
            &[state, self.u16(B), self.u16(output_length)],
            0,
            0,
        );
        if include_length {
            self.finish(status, &[target, decoded]);
        } else {
            self.finish(status, &[decoded]);
        }
    }
}

fn step() -> RecipeBuilder {
    let b = Builder::new(
        201,
        vec![Shape::bytes(S), Shape::uint(64)],
        vec![Shape::status(), Shape::bytes(S)],
    );
    let n = b.read_uint(1, N, 2);
    let target = b.read_uint(1, L, 2);
    let cursor = b.read_uint(1, P, 2);
    let produced = b.read_uint(1, O, 2);
    let distance = b.read_uint(1, D, 2);
    let remaining = b.read_fixed(1, R);
    let flags = b.read_fixed(1, F);
    let tokens = b.read_fixed(1, K);
    let admitted = b.read_fixed(1, E);
    let active = b.lt(produced, target);
    let new_token = b.eq(remaining, b.u8(0));
    let new_group = b.eq(tokens, b.u8(0));
    let next_flags = b.select(Shape::uint(8), new_group, b.safe_input(cursor), flags);
    let token_cursor = b.add(
        16,
        cursor,
        b.select(Shape::uint(16), new_group, b.u16(1), b.u16(0)),
    );
    let first = b.safe_input(token_cursor);
    let second = b.safe_input(b.add(16, token_cursor, b.u16(1)));
    let word = b.cat(Shape::uint(16), first, second);
    let high_bit = b.mask(8, next_flags, 128);
    let copy = b.eq(high_bit, b.u8(128));
    let new_distance = b.add(16, b.shr(16, word, b.u16(4)), b.u16(1));
    let copy_length = b.add(8, b.mask(8, second, 15), b.u8(3));
    let token_length = b.select(Shape::uint(8), copy, copy_length, b.u8(1));
    let token_end = b.add(
        16,
        token_cursor,
        b.select(Shape::uint(16), copy, b.u16(2), b.u16(1)),
    );
    let end_output = b.add(16, produced, b.widen(token_length));
    let good_token = b.all(&[
        b.le(token_end, n),
        b.le(end_output, target),
        b.or(b.not(copy), b.le(new_distance, produced)),
    ]);
    let good = b.all(&[
        b.eq(admitted, b.u8(1)),
        b.or(b.not(active), b.or(b.not(new_token), good_token)),
    ]);
    let status = b.select(Shape::status(), good, b.status(0), b.status(3));
    let distance_used = b.select(Shape::uint(16), new_token, new_distance, distance);
    let safe_produced = b.select(
        Shape::uint(16),
        b.lt(produced, distance_used),
        distance_used,
        produced,
    );
    let source = b.add(16, b.u16(B), b.sub(16, safe_produced, distance_used));
    let copy_byte = b.read(1, source);
    let output_byte = b.select(
        Shape::uint(8),
        b.or(b.not(new_token), copy),
        copy_byte,
        first,
    );
    let mut updated = b.write(1, b.add(16, b.u16(B), produced), output_byte);
    let selected_cursor = b.select(Shape::uint(16), new_token, token_end, cursor);
    updated = b.write_uint(updated, P, 2, selected_cursor);
    updated = b.write_uint(updated, O, 2, b.add(16, produced, b.u16(1)));
    updated = b.write_uint(updated, D, 2, distance_used);
    let old_remaining_safe = b.select(Shape::uint(8), new_token, b.u8(1), remaining);
    let old_remaining_next = b.sub(8, old_remaining_safe, b.u8(1));
    let new_remaining = b.sub(8, token_length, b.u8(1));
    updated = b.write_fixed(
        updated,
        R,
        b.select(Shape::uint(8), new_token, new_remaining, old_remaining_next),
    );
    let shifted = b.shl(8, b.mask(8, next_flags, 127), b.u8(1));
    updated = b.write_fixed(
        updated,
        F,
        b.select(Shape::uint(8), new_token, shifted, flags),
    );
    let available = b.select(Shape::uint(8), new_group, b.u8(8), tokens);
    let next_tokens = b.sub(8, available, b.u8(1));
    updated = b.write_fixed(
        updated,
        K,
        b.select(Shape::uint(8), new_token, next_tokens, tokens),
    );
    updated = b.select(Shape::bytes(S), active, updated, 1);
    b.finish(status, &[updated]);
    b.0.into_inner()
}

fn complete() -> RecipeBuilder {
    let b = Builder::new(
        202,
        vec![Shape::bytes(u32::from(B)), Shape::uint(16)],
        vec![Shape::status(), Shape::uint(16), Shape::bytes(u32::from(B))],
    );
    let (state, target) = b.initialize(1, 2, None);
    let state = b.iterate(state, u64::from(B));
    b.finalize(state, 2, target, B, true);
    b.0.into_inner()
}

fn construction_example() -> RecipeBuilder {
    let b = Builder::new(
        203,
        vec![Shape::bytes(9), Shape::uint(16)],
        vec![Shape::status(), Shape::bytes(8)],
    );
    let mut header = b.zero_bytes(3);
    header = b.emit(20, Shape::bytes(3), &[header, b.u16(0), b.u8(3)], 0, 0);
    header = b.emit(20, Shape::bytes(3), &[header, b.u16(2), b.u8(8)], 0, 0);
    let prefix = b.cat(Shape::bytes(12), header, 1);
    let encoded = b.cat(Shape::bytes(u32::from(B)), prefix, b.zero_bytes(B - 12));
    let length_good = b.le(2, b.u16(9));
    let safe_length = b.select(Shape::uint(16), length_good, 2, b.u16(0));
    let encoded_length = b.add(16, safe_length, b.u16(3));
    let (state, target) = b.initialize(encoded, encoded_length, Some(length_good));
    let state = b.iterate(state, 8);
    b.finalize(state, encoded_length, target, 8, false);
    b.0.into_inner()
}

fn builders() -> [RecipeBuilder; 3] {
    [step(), complete(), construction_example()]
}

fn tables() -> Vec<EncodedTable> {
    vec![
        (
            3,
            0,
            16,
            256,
            (0..256u16).flat_map(u16::to_be_bytes).collect(),
        ),
        (4, 3, 1, 1, vec![0]),
        (5, 0, 8, 256, (0..=255u8).collect()),
    ]
}

/// Standalone expanded diagnostic profile 7, admitted by the unchanged v0 VM.
pub fn build_body_recipe_package() -> Result<Vec<u8>> {
    let mut recipes = Vec::new();
    for builder in builders() {
        recipes.push(finalize(builder, &recipes));
    }
    let raw = encode_package_with_tables(7, &recipes, tables());
    decode_recipe_package(&raw, 7)?;
    Ok(raw)
}

/// Fresh logical source for separately owned additions to development profile 8.
pub(crate) fn revision_recipe_builders() -> Vec<RecipeBuilder> {
    let mut source: Vec<_> = r3_recipe_builders()
        .into_iter()
        .map(|builder| {
            // Keep the CRC32C R3 source; only the affine profile constant changes.
            if builder.id == 109 {
                fact_recipe(109, 8)
            } else {
                builder
            }
        })
        .collect();
    source.extend(builders());
    source
}

/// Compact development profile 8; historical public parsers still reject it.
pub fn build_revision_recipe_package() -> Result<Vec<u8>> {
    let shared_tables = r3_eh_tables();
    for required in tables() {
        if !shared_tables.iter().any(|table| table == &required) {
            return Err(BootstrapError {
                code: RejectCode::Recipe,
                offset: None,
            });
        }
    }
    let mut recipes = Vec::new();
    for builder in revision_recipe_builders() {
        recipes.push(finalize(builder, &recipes));
    }
    let expanded = encode_package_with_tables(8, &recipes, shared_tables);
    // This adapter performs the new explicit max-profile-8 semantic admission.
    encode_recipe_package_v1(&expanded, 8)
}
