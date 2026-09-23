//! Independent profile-8 route construction from the numeric development owners.
//! Successful construction proves the generated relationships and exact framing;
//! it does not promote a candidate or establish recipient acquisition.

use std::collections::{BTreeMap, BTreeSet};

use gb_foundation::{ManifestValue, validate_canonical_manifest};
use gb_slice::SliceCompilation;
use sha2::{Digest, Sha256};

use crate::carrier::{CarrierError, RouteImages, SectorImage, ShellOwner, ShellSpan};
use crate::recipe_wire_v1::{
    RecipePackageV1, decode_recipe_package_v1, evaluate_serialized_recipe_v1,
};
use crate::teaching_recipe_v2::{build_teaching_recipe_package, teaching_examples};

type Result<T> = std::result::Result<T, CarrierError>;
const STAGES: [u8; 12] = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5];
const MASKS: [u8; 4] = [0, 0x3c, 0xa5, 0xc9];

fn ensure(condition: bool) -> Result<()> {
    if condition {
        Ok(())
    } else {
        Err(CarrierError::OwnerIdentity)
    }
}

fn u16_at(raw: &[u8], at: usize) -> Result<u16> {
    Ok(u16::from_be_bytes(
        raw.get(at..at + 2)
            .ok_or(CarrierError::ManifestShape)?
            .try_into()
            .map_err(|_| CarrierError::ManifestShape)?,
    ))
}

fn u32_at(raw: &[u8], at: usize) -> Result<u32> {
    Ok(u32::from_be_bytes(
        raw.get(at..at + 4)
            .ok_or(CarrierError::ManifestShape)?
            .try_into()
            .map_err(|_| CarrierError::ManifestShape)?,
    ))
}

fn words16(raw: &mut Vec<u8>, values: &[u16]) {
    for value in values {
        raw.extend(value.to_be_bytes());
    }
}

fn words32(raw: &mut Vec<u8>, values: &[u32]) {
    for value in values {
        raw.extend(value.to_be_bytes());
    }
}

fn layout(raw: &mut Vec<u8>, rows: &[(u16, u16)]) {
    words16(raw, &[rows.len() as u16]);
    for &(offset, width) in rows {
        words16(raw, &[offset, width]);
    }
}

fn hex(text: &str) -> Result<Vec<u8>> {
    ensure(text.len() % 2 == 0 && text.len() <= 65536)?;
    text.as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let text = std::str::from_utf8(pair).map_err(|_| CarrierError::ManifestShape)?;
            u8::from_str_radix(text, 16).map_err(|_| CarrierError::ManifestShape)
        })
        .collect()
}

fn field<'a>(value: &'a ManifestValue, key: &str) -> Result<&'a ManifestValue> {
    let ManifestValue::Object(table) = value else {
        return Err(CarrierError::ManifestShape);
    };
    table.get(key).ok_or(CarrierError::ManifestShape)
}

fn number(value: &ManifestValue) -> Result<u64> {
    match value {
        ManifestValue::U64(value) => Ok(*value),
        _ => Err(CarrierError::ManifestShape),
    }
}

fn text(value: &ManifestValue) -> Result<&str> {
    match value {
        ManifestValue::String(value) => Ok(value),
        _ => Err(CarrierError::ManifestShape),
    }
}

fn array(value: &ManifestValue) -> Result<&[ManifestValue]> {
    match value {
        ManifestValue::Array(value) => Ok(value),
        _ => Err(CarrierError::ManifestShape),
    }
}

fn base_source() -> Result<ManifestValue> {
    validate_canonical_manifest(include_bytes!("../../../spec/route-data-v0.json"))
        .map_err(|_| CarrierError::ManifestShape)
}

fn record(stage: u8, kind: u8, id: u16, payload: &[u8]) -> Result<Vec<u8>> {
    let mut raw = vec![stage, kind];
    words16(&mut raw, &[id]);
    words32(
        &mut raw,
        &[u32::try_from(payload.len()).map_err(|_| CarrierError::Arithmetic)?],
    );
    raw.extend(payload);
    Ok(raw)
}

fn example_payload(
    fact: u16,
    recipe: u16,
    input: &[u8],
    expected: &[u8],
    package: &RecipePackageV1,
) -> Result<Vec<u8>> {
    let actual =
        evaluate_serialized_recipe_v1(package, recipe, input).map_err(|_| CarrierError::Recipe)?;
    ensure(
        actual == expected && actual.len() >= 2 && (actual[..2] == [0, 0] || actual.len() == 2),
    )?;
    let mut raw = Vec::new();
    words16(&mut raw, &[fact, recipe]);
    words32(&mut raw, &[input.len() as u32, expected.len() as u32]);
    raw.extend(input);
    raw.extend(expected);
    Ok(raw)
}

fn relation(recipe: u16, input: &[u8]) -> Result<Vec<u8>> {
    let mut output = vec![0, 0];
    match recipe {
        101 => output.push(input[0] ^ 255),
        102 => {
            let transform = input[0];
            let polarity = input[1];
            let row = u32::from(u16_at(input, 2)?);
            let column = u32::from(u16_at(input, 4)?);
            let side = u32::from(u16_at(input, 6)?);
            let last = side.checked_sub(1).ok_or(CarrierError::Geometry)?;
            ensure(transform < 8 && row < side && column < side)?;
            let (row, column) = match transform {
                0 => (row, column),
                1 => (last - column, row),
                2 => (last - row, last - column),
                3 => (column, last - row),
                4 => (row, last - column),
                5 => (last - column, last - row),
                6 => (last - row, column),
                _ => (column, row),
            };
            words32(&mut output, &[row * side + column]);
            output.push(polarity ^ input[8]);
        }
        103 => output.push(u8::from(u16_at(input, 0)? < u16_at(input, 2)?)),
        104 => words32(
            &mut output,
            &[u32::from(u16_at(input, 0)?) * u32::from(u16_at(input, 4)?)
                + u32::from(u16_at(input, 2)?)],
        ),
        105 => words32(
            &mut output,
            &[u32_at(input, 0)?
                .checked_add(1)
                .ok_or(CarrierError::Arithmetic)?],
        ),
        107 => words32(&mut output, &[crate::crc32c(input)]),
        109 => {
            let logical = u64::from(u32_at(input, 0)?);
            let side = u64::from(u16_at(input, 4)?);
            let width = u64::from(u16_at(input, 6)?);
            let interior = side.checked_sub(2 * width).ok_or(CarrierError::Geometry)?;
            let population = interior * interior;
            ensure(population > 0)?;
            let physical = ((2 * interior - 1) * (logical % population) + 8 * 40503 + width * 257)
                % population;
            words32(&mut output, &[physical as u32]);
        }
        112 => output.push(u8::from(
            u16_at(input, 2)?.checked_add(1) == Some(u16_at(input, 0)?) && input[4] == 1,
        )),
        113 => {
            let [factor, zeros, ones] = input else {
                return Err(CarrierError::ManifestShape);
            };
            let erased = factor
                .checked_sub(zeros + ones)
                .ok_or(CarrierError::ManifestShape)?;
            let zero = 2 * ones + erased < *factor;
            let one = 2 * zeros + erased < *factor;
            output.extend([u8::from(zero ^ one), u8::from(one && !zero)]);
        }
        _ => return Err(CarrierError::Recipe),
    }
    Ok(output)
}

fn primary(
    root: &ManifestValue,
    fact: u16,
    sector: usize,
    held: bool,
    package: &RecipePackageV1,
    definitions: &[Vec<u8>],
) -> Result<Vec<u8>> {
    if fact == 10 {
        let definition = &definitions[9];
        let start = 106 + 4 * if held { 1 } else { 8 };
        let descriptor = &definition[start..start + 4];
        let mut input = definitions[7][112..121].to_vec();
        input.extend(&definitions[7][328..337]);
        input.extend(descriptor);
        let mut word =
            input[usize::from(descriptor[0]) * 9..usize::from(descriptor[0]) * 9 + 9].to_vec();
        let mut mask = [0u8; 9];
        for bit in
            usize::from(descriptor[2])..usize::from(descriptor[2]) + usize::from(descriptor[3])
        {
            let flag = 1 << (7 - bit % 8);
            if descriptor[1] == 0 {
                word[bit / 8] ^= flag;
            } else {
                word[bit / 8] &= !flag;
                mask[bit / 8] |= flag;
            }
        }
        let mut expected = vec![0, 0];
        expected.extend(word);
        expected.extend(mask);
        return example_payload(fact, 111, &input, &expected, package);
    }
    if fact == 6 {
        let examples = teaching_examples().map_err(|_| CarrierError::Recipe)?;
        let example = &examples[usize::from(held)];
        return example_payload(
            fact,
            example.recipe,
            &example.input,
            &example.output,
            package,
        );
    }
    if fact == 8 {
        let worked = [[5, 3, 2], [2, 1, 0], [5, 1, 0], [2, 1, 1]];
        let held_rows = [[5, 2, 3], [2, 0, 1], [5, 0, 1], [5, 2, 2]];
        let input = if held {
            &held_rows[sector]
        } else {
            &worked[sector]
        };
        return example_payload(fact, 113, input, &relation(113, input)?, package);
    }
    let examples = field(root, "examples")?;
    let row = if fact == 9 {
        let selected = array(field(examples, "mapping")?)?
            .iter()
            .find(|row| field(row, "profile_version").and_then(number).ok() == Some(1))
            .ok_or(CarrierError::ManifestShape)?;
        field(selected, "value")?
    } else if fact == 11 {
        let selected = array(field(examples, "section_check")?)?
            .iter()
            .find(|row| field(row, "section_check_id").and_then(text).ok() == Some("crc32c-v0"))
            .ok_or(CarrierError::ManifestShape)?;
        field(selected, "value")?
    } else {
        array(field(examples, "common")?)?
            .iter()
            .find(|row| field(row, "fact_id").and_then(number).ok() == Some(u64::from(fact)))
            .ok_or(CarrierError::ManifestShape)?
    };
    let mut input = hex(text(field(
        row,
        if held {
            "held_input_hex"
        } else {
            "worked_input_hex"
        },
    )?)?)?;
    let slots: BTreeSet<_> = array(field(row, "mask_input_slots")?)?
        .iter()
        .map(number)
        .collect::<Result<_>>()?;
    let mut offset = 0;
    for (index, shape) in array(field(row, "inputs")?)?.iter().enumerate() {
        let kind = number(field(shape, "type")?)?;
        let width = number(field(shape, "width")?)?;
        let bytes = if kind == 3 { width } else { width.div_ceil(8) } as usize;
        let current = input
            .get_mut(offset..offset + bytes)
            .ok_or(CarrierError::ManifestShape)?;
        if slots.contains(&(index as u64 + 1)) {
            for byte in current.iter_mut() {
                *byte ^= MASKS[sector];
            }
            if kind != 3 && width % 8 != 0 {
                if kind == 2 {
                    *current.last_mut().ok_or(CarrierError::ManifestShape)? &=
                        255 << (8 - width % 8);
                } else {
                    *current.first_mut().ok_or(CarrierError::ManifestShape)? &=
                        (1 << (width % 8)) - 1;
                }
            }
        }
        offset += bytes;
    }
    ensure(offset == input.len())?;
    let recipe = if fact == 11 {
        107
    } else {
        number(field(row, "recipe_id")?)? as u16
    };
    example_payload(fact, recipe, &input, &relation(recipe, &input)?, package)
}

fn prefixes_with_spans(
    slice: &SliceCompilation,
) -> Result<[(Vec<u8>, Vec<(ShellOwner, usize)>); 4]> {
    let root = base_source()?;
    let package_raw = build_teaching_recipe_package().map_err(|_| CarrierError::Recipe)?;
    let package = decode_recipe_package_v1(&package_raw, 8).map_err(|_| CarrierError::Recipe)?;
    let definitions = definitions(slice, &package)?;
    let teaching = teaching_examples().map_err(|_| CarrierError::Recipe)?;
    let calibrations = array(field(&root, "calibration_hex")?)?;
    ensure(calibrations.len() == 4 && definitions.len() == 12)?;
    let mut result = Vec::new();
    for sector in 0..4 {
        let base = sector as u16 * 10000;
        let mut records = Vec::new();
        let mut owners = Vec::new();
        let mut count = 0;
        let mut append = |stage, kind, id, payload: &[u8]| -> Result<()> {
            let raw = record(stage, kind, base + id, payload)?;
            let owner = match kind {
                2 | 3 => ShellOwner::Example,
                5 => ShellOwner::Recipe,
                _ => ShellOwner::Instruction,
            };
            owners.push((owner, raw.len() * 8));
            records.extend(raw);
            count += 1;
            Ok(())
        };
        for fact in 1u16..=12 {
            let definition = &definitions[usize::from(fact - 1)];
            let stage = STAGES[usize::from(fact - 1)];
            let mut payload = Vec::new();
            words16(&mut payload, &[fact, fact]);
            payload.extend([3, 0]);
            words32(&mut payload, &[definition.len() as u32, 1]);
            payload.extend(definition);
            append(stage, 1, fact * 100 + 1, &payload)?;
            append(
                stage,
                2,
                fact * 100 + 2,
                &primary(&root, fact, sector, false, &package, &definitions)?,
            )?;
            append(
                stage,
                3,
                fact * 100 + 3,
                &primary(&root, fact, sector, true, &package, &definitions)?,
            )?;
            if fact == 6 {
                for (index, example) in teaching[2..].iter().enumerate() {
                    append(
                        stage,
                        2 + (index % 2) as u8,
                        610 + index as u16,
                        &example_payload(
                            fact,
                            example.recipe,
                            &example.input,
                            &example.output,
                            &package,
                        )?,
                    )?;
                }
            }
            if fact == 10 {
                let mut expected = vec![0, 0];
                expected.extend(&definitions[6][134..142]);
                append(
                    stage,
                    2,
                    1004,
                    &example_payload(fact, 30, &definition[373..386], &expected, &package)?,
                )?;
            }
            if fact == 12 {
                for (index, (input, expected)) in [
                    ("0031323334353637380009", "00003132333435363738"),
                    ("4041000400000000000004", "00004141414141414141"),
                ]
                .into_iter()
                .enumerate()
                {
                    append(
                        stage,
                        2 + index as u8,
                        1210 + index as u16,
                        &example_payload(fact, 203, &hex(input)?, &hex(expected)?, &package)?,
                    )?;
                }
            }
        }
        append(5, 5, 6001, &package_raw)?;
        append(5, 6, 7001, &1u32.to_be_bytes())?;
        append(5, 7, 7002, &[])?;
        ensure(count == 48)?;
        let prefix_cells = (64 + records.len()) * 8;
        let mut prefix = hex(text(&calibrations[sector])?)?;
        ensure(prefix.len() == 32)?;
        prefix.extend(b"GBROUTE\0");
        words16(&mut prefix, &[2]);
        prefix.extend([sector as u8, sector as u8]);
        words16(&mut prefix, &[8, count]);
        words32(
            &mut prefix,
            &[
                records.len() as u32,
                package_raw.len() as u32,
                prefix_cells as u32,
            ],
        );
        words16(&mut prefix, &[256, 0]);
        prefix.extend(records);
        let mut spans = vec![
            (ShellOwner::Instruction, 256),
            (ShellOwner::Instruction, 256),
        ];
        spans.extend(owners);
        ensure(
            prefix.len() * 8 == prefix_cells
                && spans.iter().map(|row| row.1).sum::<usize>() == prefix_cells,
        )?;
        result.push((prefix, spans));
    }
    result.try_into().map_err(|_| CarrierError::Arithmetic)
}

/// Construct all four complete prefixes from independently compiled content.
pub fn build_route_prefixes(slice: &SliceCompilation) -> Result<[Vec<u8>; 4]> {
    Ok(prefixes_with_spans(slice)?.map(|(prefix, _)| prefix))
}

fn bits(raw: &[u8]) -> Vec<u8> {
    raw.iter()
        .flat_map(|byte| (0..8).map(move |bit| (byte >> (7 - bit)) & 1))
        .collect()
}

fn packed(values: &[u8]) -> Vec<u8> {
    values
        .chunks_exact(8)
        .map(|row| row.iter().fold(0, |value, bit| value * 2 + bit))
        .collect()
}

fn recipe_record<'a>(package: &'a [u8], wanted: u16) -> Result<&'a [u8]> {
    let mut cursor = 64;
    for _ in 0..u16_at(package, 18)? {
        cursor += 16 + u32_at(package, cursor + 12)? as usize;
    }
    for _ in 0..u16_at(package, 16)? {
        let length = u32_at(package, cursor + 28)? as usize;
        let row = package
            .get(cursor..cursor + length)
            .ok_or(CarrierError::Recipe)?;
        if u16_at(row, 0)? == wanted {
            return Ok(row);
        }
        cursor += length;
    }
    Err(CarrierError::Recipe)
}

fn first_six(package: &RecipePackageV1) -> Result<Vec<Vec<u8>>> {
    let mut result = vec![hex("00ff807faa55f00fcc3301fe817e18e7")?];
    let source = crate::RawObservation::parse(&bits(&hex("80402010080403c1")?), 64)
        .map_err(|_| CarrierError::Geometry)?;
    let images = [
        "80402010080403c1",
        "81820408102040c0",
        "83c0201008040201",
        "0302040810204181",
        "010204081020c083",
        "c040201008048281",
        "c103040810204080",
        "8141201008040203",
    ];
    let mut value = Vec::new();
    let mut unique = BTreeSet::new();
    for transform in 0..8 {
        let mut cells = Vec::new();
        for row in 0..8 {
            for column in 0..8 {
                cells.push(
                    source
                        .normalized_bit(
                            crate::EntryHypothesis {
                                transform,
                                polarity: 0,
                            },
                            row,
                            column,
                        )
                        .map_err(|_| CarrierError::Geometry)?,
                );
            }
        }
        let encoded = packed(&cells);
        ensure(encoded == hex(images[usize::from(transform)])?)?;
        unique.insert(encoded.clone());
        unique.insert(encoded.iter().map(|byte| byte ^ 255).collect::<Vec<_>>());
        value.extend(encoded);
    }
    ensure(unique.len() == 16)?;
    result.push(value);
    let mut value = Vec::new();
    for n in [0u8, 1, 2, 3, 4, 5, 7, 8, 15, 16, 24, 31] {
        words32(&mut value, &[(1u32 << n) - 1]);
        value.extend([n, n ^ 255]);
        words16(&mut value, &[u16::from(n)]);
    }
    result.push(value);
    let mut value = Vec::new();
    words16(&mut value, &[32, 8, 24, 6]);
    for sector in 0u8..4 {
        for (u, v) in [(0, 0), (0, 23), (7, 0), (7, 23), (0, 1), (1, 0)] {
            let actual =
                crate::sector_cell(32, 8, sector, u, v).map_err(|_| CarrierError::Geometry)?;
            let expected = match sector {
                0 => (u, v),
                1 => (v, 31 - u),
                2 => (31 - u, 31 - v),
                _ => (31 - v, u),
            };
            ensure(actual == expected)?;
            words16(
                &mut value,
                &[
                    u16::from(sector),
                    u as u16,
                    v as u16,
                    actual.0 as u16,
                    actual.1 as u16,
                    (24 * u + v) as u16,
                ],
            );
        }
    }
    result.push(value);
    let mut value = Vec::new();
    for rows in [
        &[
            (0, 8),
            (8, 2),
            (10, 1),
            (11, 1),
            (12, 2),
            (14, 2),
            (16, 4),
            (20, 4),
            (24, 4),
            (28, 2),
            (30, 2),
        ][..],
        &[(0, 1), (1, 1), (2, 2), (4, 4)],
        &[
            (0, 8),
            (8, 2),
            (10, 2),
            (12, 2),
            (14, 2),
            (16, 2),
            (18, 2),
            (20, 4),
            (24, 4),
            (28, 4),
            (32, 4),
            (36, 8),
            (44, 4),
            (48, 16),
        ],
        &[(0, 2), (2, 1), (3, 1), (4, 4), (8, 4), (12, 4)],
        &[
            (0, 2),
            (2, 2),
            (4, 2),
            (6, 2),
            (8, 4),
            (12, 4),
            (16, 8),
            (24, 4),
            (28, 4),
        ],
        &[(0, 2), (2, 1), (3, 1), (4, 4), (8, 4)],
    ] {
        layout(&mut value, rows);
    }
    let recipe = recipe_record(&package.encoded, 109)?;
    let measured = [
        109,
        32,
        u16_at(recipe, 4)?,
        u16_at(recipe, 6)?,
        12,
        (u16_at(recipe, 4)? + u16_at(recipe, 6)?) * 12,
        u32_at(recipe, 8)? as u16,
        (recipe.len()
            - 32
            - (usize::from(u16_at(recipe, 4)?) + usize::from(u16_at(recipe, 6)?)) * 12)
            as u16,
        recipe.len() as u16,
    ];
    ensure(measured == [109, 32, 3, 2, 12, 60, 42, 484, 576])?;
    words16(&mut value, &measured);
    result.push(value);
    let mut value = Vec::new();
    for opcode in 1u8..=25 {
        let arity = match opcode {
            1 | 2 | 24 | 25 => 0,
            5 | 14 | 22 => 1,
            3 | 20 | 23 => 3,
            _ => 2,
        };
        let aux = if matches!(opcode, 2 | 5 | 22) { 2 } else { 0 };
        let imm = if matches!(opcode, 1 | 5 | 14 | 22 | 25) {
            8
        } else {
            0
        };
        value.extend([
            opcode,
            arity,
            2 * arity,
            aux,
            imm,
            6 + 2 * arity + aux + imm,
        ]);
    }
    for (kind, unit, min, max) in [
        (0, 0, 1, 64),
        (1, 0, 1, 1),
        (2, 0, 1, 1048576),
        (3, 1, 0, 1048576),
        (4, 2, 0, 1048576),
        (5, 0, 16, 16),
    ] {
        value.extend([kind, unit]);
        words32(&mut value, &[min, max]);
    }
    result.push(value);
    Ok(result)
}

fn example_common(value: u8) -> Result<[u8; 191]> {
    let payload = crate::encode_section(&crate::SectionEnvelope {
        section_id: 400,
        section_type: 4,
        section_version: 0,
        closure_class: 129,
        check_id: 1,
        dependencies: vec![],
        payload: vec![value],
    })
    .map_err(|_| CarrierError::Section)?;
    ensure(payload.len() == 23)?;
    crate::encode_common_block(&crate::CommonBlock {
        profile_version: 8,
        section_id: 400,
        semantic_copy_id: 0,
        section_type: 4,
        section_version: 0,
        fragment_index: 0,
        fragment_count: 1,
        section_envelope_length: 23,
        payload,
    })
    .map_err(|_| CarrierError::Section)
}

fn recheck_common(raw: &mut [u8; 191]) {
    let mut preimage = crate::LOCAL_CHECK_DOMAIN.to_vec();
    preimage.extend(&raw[..187]);
    raw[187..].copy_from_slice(&crate::crc32c(&preimage).to_be_bytes());
}

fn common_agreement(raw: &[u8; 191]) -> bool {
    let Ok(common) = crate::decode_common_block(raw, 8) else {
        return false;
    };
    let Ok(envelope) = crate::decode_section(&common.payload) else {
        return false;
    };
    common.section_id == envelope.section_id
        && common.section_type == envelope.section_type
        && common.section_version == envelope.section_version
        && common.section_envelope_length as usize == common.payload.len()
}

fn seventh(a: &[u8; 191], b: &[u8; 191]) -> Result<Vec<u8>> {
    let mut value = Vec::new();
    layout(
        &mut value,
        &[
            (0, 2),
            (2, 2),
            (4, 4),
            (8, 2),
            (10, 2),
            (12, 2),
            (14, 2),
            (16, 2),
            (18, 2),
            (20, 2),
            (22, 4),
            (26, 4),
            (30, 157),
            (187, 4),
        ],
    );
    layout(
        &mut value,
        &[
            (0, 2),
            (2, 4),
            (6, 2),
            (8, 2),
            (10, 1),
            (11, 1),
            (12, 2),
            (14, 4),
        ],
    );
    value.extend(crate::LOCAL_CHECK_DOMAIN);
    value.extend(crate::SECTION_CHECK_DOMAIN);
    for (raw, expected) in [
        (b"123456789".as_slice(), 0xe3069283),
        (&[0, 1, 2, 3, 4, 5, 6, 7, 8][..], 0x7144c5a8),
    ] {
        let crc = crate::crc32c(raw);
        ensure(crc == expected)?;
        value.extend(raw);
        words32(&mut value, &[crc]);
    }
    ensure(common_agreement(a) && common_agreement(b))?;
    value.extend(a);
    value.extend(b);
    let rows = [
        [2, 2, 1, 1, 0, 0],
        [14, 2, 1, 1, 0, 0],
        [26, 2, 1, 1, 0, 0],
        [18, 2, 0, 1, 0, 0],
        [16, 2, 1, 1, 0, 0],
        [4, 2, 1, 1, 1, 0],
        [22, 2, 1, 1, 0, 0],
        [48, 1, 1, 0, 0, 0],
        [187, 1, u16::from(a[187] ^ 1), 0, 0, 0],
        [53, 1, 1, 1, 0, 0],
    ];
    for row in rows {
        let [offset, width, replacement, recheck, local, agreement] = row;
        let mut changed = *a;
        changed[usize::from(offset)..usize::from(offset + width)]
            .copy_from_slice(&replacement.to_be_bytes()[2 - usize::from(width)..]);
        if recheck == 1 {
            recheck_common(&mut changed);
        }
        ensure(
            crate::decode_common_block(&changed, 8).is_ok() == (local == 1)
                && common_agreement(&changed) == (agreement == 1),
        )?;
        words16(&mut value, &row);
    }
    Ok(value)
}

fn eighth(a: &[u8; 191], b: &[u8; 191], package: &RecipePackageV1) -> Result<Vec<u8>> {
    let mut value = Vec::new();
    words16(&mut value, &[24, 9, 8, 216, 192, 191, 1, 0]);
    for i in 0..24 {
        words16(&mut value, &[9 * i, 8 * i]);
    }
    for common in [a, b] {
        let encoded = crate::candidate::encode_eh_unit(common);
        let observation = crate::candidate::EhObservation {
            encoded,
            erasures: vec![],
        };
        ensure(
            crate::candidate::decode_eh_unit(&observation, 8)
                .map_err(|_| CarrierError::Recipe)?
                .common
                == *common,
        )?;
        let mut plain = Vec::new();
        for word in encoded.chunks_exact(9) {
            let decoded = crate::candidate::decode_eh72(
                word.try_into().map_err(|_| CarrierError::Recipe)?,
                &[],
            )
            .map_err(|_| CarrierError::Recipe)?;
            let mut expected = vec![0, 0];
            expected.extend(decoded.data);
            let mut input = word.to_vec();
            input.extend([0; 4]);
            ensure(
                evaluate_serialized_recipe_v1(package, 30, &input)
                    .map_err(|_| CarrierError::Recipe)?
                    == expected,
            )?;
            let mut expected_code = vec![0, 0];
            expected_code.extend(word);
            ensure(
                evaluate_serialized_recipe_v1(package, 108, &decoded.data)
                    .map_err(|_| CarrierError::Recipe)?
                    == expected_code,
            )?;
            plain.extend(decoded.data);
        }
        ensure(plain.len() == 192 && plain[..191] == *common && plain[191] == 0)?;
        value.extend(encoded);
    }
    Ok(value)
}

fn ninth() -> Result<Vec<u8>> {
    let maps = [
        crate::mapping_v2::derive(2040, 128)?,
        crate::mapping_v2::derive(1952, 128)?,
    ];
    let table = crate::candidate_recipe::r3_slot_multiplier_table();
    let mut value = Vec::new();
    for map in maps {
        ensure(map.slot_multiplier() == u64::from(table[usize::from(map.interior_side() / 8)]))?;
        words32(
            &mut value,
            &[
                u32::from(map.side()),
                u32::from(map.shell_width()),
                u32::from(map.interior_side()),
                map.population() as u32,
                map.unit_slot_count() as u32,
                map.slot_multiplier() as u32,
                map.inverse_slot_multiplier() as u32,
                map.cell_multiplier() as u32,
                map.inverse_cell_multiplier() as u32,
                map.cell_offset() as u32,
            ],
        );
    }
    for map in maps {
        let q = map.unit_slot_count();
        let b = map.slot_multiplier();
        for (unit, bit) in [(1, 0), (1, 1727), (q, 0), (q, 1727), (q / b + 2, 0)] {
            let slot = b * (unit - 1) % q;
            let logical = 1728 * slot + u64::from(bit);
            let physical = (map.cell_multiplier() * logical + map.cell_offset()) % map.population();
            ensure(
                map.forward(unit, bit)? == physical && map.inverse(physical)? == (0, unit, bit),
            )?;
            words32(
                &mut value,
                &[
                    unit as u32,
                    u32::from(bit),
                    slot as u32,
                    logical as u32,
                    physical as u32,
                    0,
                ],
            );
        }
        for logical in [1728 * q - 1, 1728 * q, map.population() - 1] {
            let physical = (map.cell_multiplier() * logical + map.cell_offset()) % map.population();
            let (kind, unit, bit) = map.inverse(physical)?;
            let slot = if kind == 0 { logical / 1728 } else { 0 };
            if kind == 0 {
                ensure(map.forward(unit, bit)? == physical)?;
            } else {
                ensure((unit, bit) == (0, 0))?;
            }
            words32(
                &mut value,
                &[
                    unit as u32,
                    u32::from(bit),
                    slot as u32,
                    logical as u32,
                    physical as u32,
                    u32::from(kind),
                ],
            );
        }
    }
    Ok(value)
}

fn observation(common: &[u8; 191], flips: &[u16]) -> crate::candidate::EhObservation {
    let mut encoded = crate::candidate::encode_eh_unit(common);
    for bit in flips {
        encoded[usize::from(*bit) / 8] ^= 1 << (7 - *bit % 8);
    }
    crate::candidate::EhObservation {
        encoded,
        erasures: vec![],
    }
}

fn common_identity(raw: &[u8; 191]) -> [u8; 20] {
    let mut key = [0; 20];
    let mut at = 0;
    for (offset, width) in [
        (0, 2),
        (4, 4),
        (8, 2),
        (10, 2),
        (12, 2),
        (16, 2),
        (18, 2),
        (22, 4),
    ] {
        key[at..at + width].copy_from_slice(&raw[offset..offset + width]);
        at += width;
    }
    key
}

fn group_observation(
    lanes: &[Option<crate::candidate::EhObservation>],
    expected_key: &[u8; 20],
    a: &[u8; 191],
    b: &[u8; 191],
    package: &RecipePackageV1,
    verified_counts: &mut BTreeSet<[u8; 3]>,
) -> Result<([u8; 8], Vec<u8>, [u8; 12])> {
    ensure(matches!(lanes.len(), 1 | 2 | 5))?;
    let classify = |raw: &[u8; 191]| -> Result<u8> {
        if raw == a {
            Ok(1)
        } else if raw == b {
            Ok(2)
        } else {
            Err(CarrierError::OwnerIdentity)
        }
    };
    let mut trace = [0; 12];
    let mut states = Vec::new();
    let mut lane_blocks = BTreeSet::new();
    for (index, lane) in lanes.iter().enumerate() {
        match lane {
            None => states.push(0),
            Some(lane) => match crate::candidate::decode_eh_unit(lane, 8) {
                Ok(decoded) => {
                    trace[index] = classify(&decoded.common)?;
                    states.push(
                        if decoded.quality == crate::candidate::DecodeQuality::Verified {
                            2
                        } else {
                            3
                        },
                    );
                    lane_blocks.insert(decoded.common);
                }
                Err(_) => states.push(1),
            },
        }
    }
    let mut all = lane_blocks.clone();
    let mut rep_block = None;
    let mut rep_state = 0;
    if lanes.len() > 1 {
        let repetition = crate::candidate::aggregate_repetition_observation(lanes)
            .map_err(|_| CarrierError::Recipe)?;
        if let Some(rep) = repetition {
            for bit in 0..1728 {
                let mut zeros = 0;
                let mut ones = 0;
                for lane in lanes.iter().flatten() {
                    if lane.erasures.iter().any(|erasure| {
                        usize::from(erasure.codeword) == bit / 72
                            && usize::from(erasure.position) == bit % 72 + 1
                    }) {
                        continue;
                    }
                    if (lane.encoded[bit / 8] >> (7 - bit % 8)) & 1 == 0 {
                        zeros += 1;
                    } else {
                        ones += 1;
                    }
                }
                let counts = [lanes.len() as u8, zeros, ones];
                if verified_counts.insert(counts) {
                    ensure(
                        evaluate_serialized_recipe_v1(package, 113, &counts)
                            .map_err(|_| CarrierError::Recipe)?
                            == relation(113, &counts)?,
                    )?;
                }
                let consequence = relation(113, &counts)?;
                let erased = rep.erasures.iter().any(|erasure| {
                    usize::from(erasure.codeword) == bit / 72
                        && usize::from(erasure.position) == bit % 72 + 1
                });
                ensure(erased == (consequence[2] == 0))?;
                if !erased {
                    ensure((rep.encoded[bit / 8] >> (7 - bit % 8)) & 1 == consequence[3])?;
                }
            }
            match crate::candidate::decode_eh_unit(&rep, 8) {
                Ok(decoded) => {
                    trace[5] = classify(&decoded.common)?;
                    rep_state = 3;
                    all.insert(decoded.common);
                    rep_block = Some(decoded.common);
                }
                Err(_) => rep_state = 1,
            }
        }
    }
    let identities = !all.is_empty() && all.iter().all(|raw| common_identity(raw) == *expected_key);
    let accepted = identities && all.len() == 1;
    let conflict = all.len() > 1;
    let present = lanes.iter().filter(|lane| lane.is_some()).count() as u8;
    let row = [
        lanes.len() as u8,
        present,
        lane_blocks.len() as u8,
        u8::from(rep_block.is_some()),
        u8::from(rep_block.is_some_and(|block| lane_blocks.contains(&block))),
        u8::from(identities),
        u8::from(accepted),
        u8::from(conflict),
    ];
    let group = if conflict {
        4
    } else if all.len() == 1 {
        if states.contains(&2) { 2 } else { 3 }
    } else if present == 0 {
        0
    } else {
        1
    };
    let mut mask = 0;
    for raw in &all {
        if raw == a {
            mask |= 1;
        } else if raw == b {
            mask |= 2;
        } else {
            return Err(CarrierError::OwnerIdentity);
        }
    }
    states.extend([rep_state, all.len() as u8, group, mask]);
    trace[6..].copy_from_slice(&[
        u8::from(present != 0),
        u8::from(states[..lanes.len()].contains(&2)),
        u8::from(identities),
        mask,
        group,
        u8::from(accepted),
    ]);
    let mut expected = vec![0, 0];
    expected.extend(&trace[9..]);
    ensure(
        evaluate_serialized_recipe_v1(package, 110, &trace[..9])
            .map_err(|_| CarrierError::Recipe)?
            == expected,
    )?;
    Ok((row, states, trace))
}

fn tenth(a: &[u8; 191], b: &[u8; 191], package: &RecipePackageV1) -> Result<Vec<u8>> {
    let roster = [
        [1u16, 0, 2, 5, 1, 5],
        [1, 1, 2, 5, 6, 10],
        [400, 0, 1, 5, 11, 15],
        [401, 0, 1, 2, 16, 17],
    ];
    let mut value = Vec::new();
    words16(&mut value, &[4, 6]);
    for row in roster {
        words16(&mut value, &row);
    }
    value.extend([0, 4, 8, 10, 12, 16, 18, 22, 2]);
    let mut keys = Vec::<[u8; 20]>::new();
    for section in [400, 401] {
        let mut key = Vec::new();
        words16(&mut key, &[8]);
        words32(&mut key, &[section]);
        words16(&mut key, &[0, 4, 0, 0, 1]);
        words32(&mut key, &[23]);
        keys.push(
            key.as_slice()
                .try_into()
                .map_err(|_| CarrierError::Recipe)?,
        );
        value.extend(key);
    }
    let templates = [
        [0u8, 0, 0, 0],
        [0, 0, 59, 5],
        [0, 0, 0, 1],
        [1, 0, 0, 2],
        [1, 0, 2, 2],
        [1, 0, 4, 2],
        [1, 0, 6, 2],
        [1, 0, 8, 2],
        [0, 1, 59, 5],
        [0, 1, 60, 5],
        [0, 1, 61, 5],
        [0, 1, 62, 5],
        [0, 1, 63, 5],
    ];
    words16(&mut value, &[111]);
    value.push(0);
    value.extend([13, 4]);
    let mut observations = Vec::new();
    let words = [
        observation(a, &[]).encoded[..9].to_vec(),
        observation(b, &[]).encoded[..9].to_vec(),
    ]
    .concat();
    for row @ [source, unknown, first, count] in templates {
        value.extend(row);
        let mut lane = observation(if source == 0 { a } else { b }, &[]);
        let mut unknown_mask = [0u8; 9];
        for bit in u16::from(first)..u16::from(first) + u16::from(count) {
            let mask = 1 << (7 - bit % 8);
            if unknown == 0 {
                lane.encoded[usize::from(bit) / 8] ^= mask;
            } else {
                lane.encoded[usize::from(bit) / 8] &= !mask;
                unknown_mask[usize::from(bit) / 8] |= mask;
                lane.erasures.push(crate::candidate::EhErasure {
                    codeword: (bit / 72) as u8,
                    position: (bit % 72 + 1) as u8,
                });
            }
        }
        let mut input = words.clone();
        input.extend(row);
        let mut expected = vec![0, 0];
        expected.extend(&lane.encoded[..9]);
        expected.extend(unknown_mask);
        ensure(
            evaluate_serialized_recipe_v1(package, 111, &input)
                .map_err(|_| CarrierError::Recipe)?
                == expected,
        )?;
        observations.push(lane);
    }
    words16(&mut value, &[110]);
    value.extend([8, 24]);
    let cases = [
        [11u8, 0, 0, 0, 0, 0],
        [11, 4, 0, 0, 0, 0],
        [11, 1, 0, 0, 0, 0],
        [11, 3, 0, 0, 0, 0],
        [11, 1, 4, 5, 6, 7],
        [11, 4, 5, 6, 7, 8],
        [11, 9, 10, 11, 12, 13],
        [16, 1, 1, 0, 0, 0],
    ];
    let mut counts = BTreeSet::new();
    let mut raw_groups = Vec::new();
    for row in cases {
        let owner = roster
            .iter()
            .find(|r| (r[4]..=r[5]).contains(&u16::from(row[0])))
            .ok_or(CarrierError::OwnerIdentity)?;
        let factor = usize::from(owner[3]);
        ensure(row[1 + factor..].iter().all(|id| *id == 0))?;
        let key = keys
            .iter()
            .find(|key| {
                u32_at(*key, 2).ok() == Some(u32::from(owner[0]))
                    && u16_at(*key, 12).ok() == Some(owner[1])
                    && u16_at(*key, 14).ok() == Some(owner[2])
            })
            .ok_or(CarrierError::OwnerIdentity)?;
        let lanes = row[1..1 + factor]
            .iter()
            .map(|id| {
                if *id == 0 {
                    None
                } else {
                    Some(observations[usize::from(*id - 1)].clone())
                }
            })
            .collect::<Vec<_>>();
        let (_, states, trace) = group_observation(&lanes, key, a, b, package, &mut counts)?;
        value.extend(row);
        value.extend(&states[..factor]);
        value.resize(value.len() + 5 - factor, 0);
        value.push(states[factor]);
        value.extend(trace);
        raw_groups.push(lanes);
    }
    ensure(value.len() == 354)?;
    value.extend([3, 4]);
    for bit in [0u16, 63, 72] {
        words16(&mut value, &[bit]);
        value.extend([(bit / 72) as u8, (bit % 72 + 1) as u8]);
    }
    value.extend([7, 0, 0]);
    words16(&mut value, &[30]);
    let rep = crate::candidate::aggregate_repetition_observation(&raw_groups[6])
        .map_err(|_| CarrierError::Recipe)?
        .ok_or(CarrierError::Recipe)?;
    let mut input = rep.encoded[..9].to_vec();
    let positions = rep
        .erasures
        .iter()
        .filter(|e| e.codeword == 0)
        .map(|e| e.position)
        .collect::<Vec<_>>();
    ensure(positions.len() <= 3)?;
    input.push(positions.len() as u8);
    input.extend(positions);
    input.resize(13, 0);
    let mut expected = vec![0, 0];
    expected.extend(&a[..8]);
    ensure(
        evaluate_serialized_recipe_v1(package, 30, &input).map_err(|_| CarrierError::Recipe)?
            == expected,
    )?;
    value.extend(input);
    words16(&mut value, &[113]);
    value.extend([4, 8]);
    for symbols in [
        [2u8, 0, 1, 2, 2, 2],
        [5, 0, 1, 1, 1, 1],
        [5, 1, 2, 2, 2, 2],
        [5, 2, 2, 2, 2, 2],
    ] {
        let active = &symbols[1..1 + usize::from(symbols[0])];
        let input = [
            symbols[0],
            active.iter().filter(|v| **v == 0).count() as u8,
            active.iter().filter(|v| **v == 1).count() as u8,
        ];
        let expected = relation(113, &input)?;
        ensure(
            evaluate_serialized_recipe_v1(package, 113, &input)
                .map_err(|_| CarrierError::Recipe)?
                == expected,
        )?;
        value.extend(symbols);
        value.extend(&expected[2..]);
    }
    value.push(5);
    for length in [22u16, 157, 158, 314, 315] {
        let fragments = length.div_ceil(157);
        let last = length - 157 * (fragments - 1);
        ensure(
            (0..fragments)
                .map(|i| if i + 1 == fragments { last } else { 157 })
                .sum::<u16>()
                == length,
        )?;
        words16(&mut value, &[length]);
        value.extend([fragments as u8, last as u8]);
    }
    ensure(value.len() == 443)?;
    Ok(value)
}

fn metadata_inventory() -> crate::Inventory {
    let bodies: Vec<_> = (16..=18).chain(100..=163).chain(200..=210).collect();
    let mut entries = Vec::new();
    for id in [1, 2, 3].into_iter().chain(bodies.iter().copied()) {
        let required = [1, 2, 3, 16, 17, 18].contains(&id);
        entries.push(crate::InventoryEntry {
            section_id: id,
            section_type: if id == 1 {
                1
            } else if id < 4 {
                2
            } else {
                3
            },
            section_version: if id == 1 { 2 } else { 0 },
            closure_class: if required { 128 } else { 129 },
            check_id: 1,
            copy_count: 1,
            physical_replica_count: if required { 5 } else { 1 },
            dependencies: if id == 2 {
                vec![16, 17, 18]
            } else if id == 3 {
                bodies.clone()
            } else {
                vec![]
            },
            logical_payload_length: 1,
            game_ordinal: if (100..=163).contains(&id) {
                Some((id - 100) as u16)
            } else {
                None
            },
        });
    }
    entries[0].logical_payload_length = 1952;
    crate::Inventory {
        inventory_version: 2,
        entries,
    }
}

fn eleventh(a: &[u8; 191]) -> Result<Vec<u8>> {
    let mut value = Vec::new();
    layout(&mut value, &[(0, 2), (2, 2), (4, 2), (6, 2)]);
    layout(
        &mut value,
        &[
            (0, 4),
            (4, 2),
            (6, 2),
            (8, 1),
            (9, 1),
            (10, 1),
            (11, 1),
            (12, 2),
            (14, 4),
            (18, 2),
        ],
    );
    for factor in [1, 2, 5] {
        for ordinal in [0, 1] {
            value.extend([factor, ordinal, 2 * factor + ordinal]);
        }
    }
    words16(&mut value, &[1, 2, 0, 5, 1, 2, 3, 4, 5]);
    for text in [
        "011111", "100000", "110000", "111011", "110100", "111101", "111100", "111110", "111111",
        "000000", "010101", "101111",
    ] {
        let inputs: Vec<_> = text.bytes().map(|byte| byte - b'0').collect();
        let required = inputs[0] & inputs[1] & inputs[3];
        let all = required & inputs[2] & inputs[4];
        let exact = all & inputs[5];
        value.extend(inputs);
        value.extend([required, all, exact]);
    }
    for profile in [8u16, 7] {
        let mut changed = *a;
        changed[..2].copy_from_slice(&profile.to_be_bytes());
        recheck_common(&mut changed);
        let accepted = crate::decode_common_block(&changed, 8).is_ok();
        ensure(accepted == (profile == 8))?;
        words16(&mut value, &[profile, 8, 1, u16::from(accepted)]);
    }
    words16(&mut value, &[3]);
    for row in [[4, 2, 4], [10, 6, 2], [12, 8, 2]] {
        value.extend(row);
    }
    words16(&mut value, &[7]);
    for row in [
        [2, 0, 4],
        [6, 4, 2],
        [8, 6, 2],
        [10, 8, 1],
        [11, 9, 1],
        [12, 12, 2],
        [14, 14, 4],
    ] {
        value.extend(row);
    }
    words16(&mut value, &[2, 16, 17, 18]);
    let ids = [2u32, 16, 17, 18];
    for (adjacency, selected, expected, valid) in [
        (0x7000u16, 8u8, 15u8, true),
        (0x4200, 8, 14, true),
        (0, 4, 4, true),
        (0x4800, 8, 0, false),
    ] {
        let mut inventory = metadata_inventory();
        inventory
            .entries
            .retain(|row| ids.contains(&row.section_id));
        for (index, row) in inventory.entries.iter_mut().enumerate() {
            row.dependencies = ids
                .iter()
                .enumerate()
                .filter(|(target, _)| adjacency & (1 << (15 - (index * 4 + target))) != 0)
                .map(|(_, id)| *id)
                .collect();
        }
        let admitted = crate::validate_dependency_graph(&inventory).is_ok();
        ensure(admitted == valid)?;
        let mut closure = selected;
        if admitted {
            for _ in 0..4 {
                let mut next = closure;
                for index in 0..4 {
                    if closure & (8 >> index) != 0 {
                        next |= ((adjacency >> (12 - index * 4)) & 15) as u8;
                    }
                }
                closure = next;
            }
        } else {
            closure = 0;
        }
        ensure(closure == expected)?;
        words16(&mut value, &[adjacency]);
        value.extend([selected, closure, u8::from(admitted)]);
    }
    for (id, ordinal, has, expected) in [
        (100u16, 0u16, 1u16, 1u16),
        (163, 63, 1, 1),
        (211, 65535, 0, 1),
        (101, 0, 1, 0),
    ] {
        let mut inventory = metadata_inventory();
        if id == 211 {
            inventory.entries.push(crate::InventoryEntry {
                section_id: 211,
                section_type: 4,
                section_version: 0,
                closure_class: 129,
                check_id: 1,
                copy_count: 1,
                physical_replica_count: 1,
                dependencies: vec![],
                logical_payload_length: 1,
                game_ordinal: None,
            });
            inventory.entries[0].logical_payload_length += 20;
        }
        let row = inventory
            .entries
            .iter_mut()
            .find(|row| row.section_id == u32::from(id))
            .ok_or(CarrierError::Section)?;
        row.game_ordinal = if has == 1 { Some(ordinal) } else { None };
        let admitted = crate::bootstrap_v2::encode_inventory(&inventory)
            .and_then(|raw| crate::bootstrap_v2::decode_inventory(&raw))
            .is_ok();
        ensure(admitted == (expected == 1))?;
        words16(&mut value, &[id, ordinal, has, u16::from(admitted)]);
    }
    Ok(value)
}

fn closed(row: &ManifestValue, names: &str) -> Result<()> {
    let ManifestValue::Object(fields) = row else {
        return Err(CarrierError::ManifestShape);
    };
    ensure(
        fields.keys().map(String::as_str).collect::<BTreeSet<_>>()
            == names.split_whitespace().collect(),
    )
}

fn n16(row: &ManifestValue, key: &str) -> Result<u16> {
    u16::try_from(number(field(row, key)?)?).map_err(|_| CarrierError::ManifestShape)
}
fn n8(row: &ManifestValue, key: &str) -> Result<u8> {
    u8::try_from(number(field(row, key)?)?).map_err(|_| CarrierError::ManifestShape)
}
fn n32(row: &ManifestValue, key: &str) -> Result<u32> {
    u32::try_from(number(field(row, key)?)?).map_err(|_| CarrierError::ManifestShape)
}
fn nums16(row: &ManifestValue, key: &str) -> Result<Vec<u16>> {
    array(field(row, key)?)?
        .iter()
        .map(|v| u16::try_from(number(v)?).map_err(|_| CarrierError::ManifestShape))
        .collect()
}
fn nums32(row: &ManifestValue, key: &str) -> Result<Vec<u32>> {
    array(field(row, key)?)?
        .iter()
        .map(|v| u32::try_from(number(v)?).map_err(|_| CarrierError::ManifestShape))
        .collect()
}

fn miniature() -> Result<(Vec<u8>, Vec<gb_content::Record>)> {
    use gb_content::{
        AtomEntry, FieldSpec, FieldValue, LessonCase, Record, RecordPayload as P, Region,
    };
    let source = include_bytes!("../../../conformance/content-v0.json");
    ensure(
        source.len() <= 1048576
            && format!("{:x}", Sha256::digest(source))
                == "b3f4279e95854e77bd3ce25c05e8580b1298ffccc164ac40a6010e86091a038b",
    )?;
    let root = validate_canonical_manifest(source).map_err(|_| CarrierError::ManifestShape)?;
    let bases = array(field(&root, "bases")?)?
        .iter()
        .filter(|row| field(row, "name").and_then(text).ok() == Some("generic-base"))
        .collect::<Vec<_>>();
    ensure(bases.len() == 1)?;
    let base = bases[0];
    closed(
        base,
        "name projection stream_hex stream_length stream_sha256",
    )?;
    let projection = field(base, "projection")?;
    closed(projection, "records root_record_id version")?;
    ensure(n16(projection, "version")? == 0 && n16(projection, "root_record_id")? == 29)?;
    let rows = array(field(projection, "records")?)?;
    ensure(rows.len() == 29)?;
    let mut records = Vec::new();
    for (index, row) in rows.iter().enumerate() {
        let kind = text(field(row, "kind")?)?;
        let id = n16(row, "record_id")?;
        ensure(usize::from(id) == index + 1)?;
        let payload = match kind {
            "TEXT" => {
                closed(row, "kind record_id text")?;
                P::Text(text(field(row, "text")?)?.to_owned())
            }
            "ATOM_SCHEMA" => {
                let class = n8(row, "atom_class")?;
                closed(
                    row,
                    match class {
                        1 => "kind record_id atom_class atom_width entry_count min_value max_value",
                        2 => "kind record_id atom_class atom_width entry_count entries",
                        3 => {
                            "kind record_id atom_class atom_width entry_count entries allowed_mask"
                        }
                        _ => return Err(CarrierError::ManifestShape),
                    },
                )?;
                let mut entries = Vec::new();
                if class != 1 {
                    for entry in array(field(row, "entries")?)? {
                        let key = if class == 2 { "code" } else { "one_hot_bit" };
                        closed(
                            entry,
                            if class == 2 {
                                "code label_text_ref"
                            } else {
                                "one_hot_bit label_text_ref"
                            },
                        )?;
                        entries.push(AtomEntry {
                            code: n32(entry, key)?,
                            label_text_ref: n16(entry, "label_text_ref")?,
                        });
                    }
                }
                ensure(usize::from(n16(row, "entry_count")?) == entries.len())?;
                P::AtomSchema {
                    atom_class: class,
                    atom_width: n8(row, "atom_width")?,
                    entries,
                    min_value: if class == 1 {
                        Some(n32(row, "min_value")?)
                    } else {
                        None
                    },
                    max_value: if class == 1 {
                        Some(n32(row, "max_value")?)
                    } else {
                        None
                    },
                    allowed_mask: if class == 3 {
                        Some(n32(row, "allowed_mask")?)
                    } else {
                        None
                    },
                }
            }
            "ATOM_VECTOR" => {
                closed(row, "kind record_id atom_schema_ref atom_count atoms")?;
                let atoms = nums32(row, "atoms")?;
                ensure(atoms.len() == usize::from(n16(row, "atom_count")?))?;
                P::AtomVector {
                    atom_schema_ref: n16(row, "atom_schema_ref")?,
                    atoms,
                }
            }
            "MATRIX" => {
                closed(row, "kind record_id atom_schema_ref rows columns cells")?;
                let rows = n16(row, "rows")?;
                let columns = n16(row, "columns")?;
                let cells = nums32(row, "cells")?;
                ensure(cells.len() == usize::from(rows) * usize::from(columns))?;
                P::Matrix {
                    atom_schema_ref: n16(row, "atom_schema_ref")?,
                    rows,
                    columns,
                    cells,
                }
            }
            "FIELD_SCHEMA" => {
                closed(row, "kind record_id field_count fields")?;
                let mut fields = Vec::new();
                for item in array(field(row, "fields")?)? {
                    closed(item, "name_text_ref storage type count")?;
                    fields.push(FieldSpec {
                        name_text_ref: n16(item, "name_text_ref")?,
                        storage: n8(item, "storage")?,
                        type_code: n16(item, "type")?,
                        count: n16(item, "count")?,
                    });
                }
                ensure(fields.len() == usize::from(n16(row, "field_count")?))?;
                P::FieldSchema { fields }
            }
            "TUPLE" => {
                closed(row, "kind record_id field_schema_ref field_values")?;
                let mut field_values = Vec::new();
                for item in array(field(row, "field_values")?)? {
                    if field(item, "atoms").is_ok() {
                        closed(item, "atoms")?;
                        field_values.push(FieldValue::Atoms(nums32(item, "atoms")?));
                    } else {
                        closed(item, "record_refs")?;
                        field_values.push(FieldValue::RecordRefs(nums16(item, "record_refs")?));
                    }
                }
                P::Tuple {
                    field_schema_ref: n16(row, "field_schema_ref")?,
                    field_values,
                }
            }
            "REGION_SET" => {
                closed(
                    row,
                    "kind record_id surface_matrix_ref region_count regions",
                )?;
                let mut regions = Vec::new();
                for item in array(field(row, "regions")?)? {
                    closed(
                        item,
                        "region_id label_ref row_start row_end column_start column_end flags",
                    )?;
                    regions.push(Region {
                        region_id: n16(item, "region_id")?,
                        label_ref: n16(item, "label_ref")?,
                        row_start: n16(item, "row_start")?,
                        row_end: n16(item, "row_end")?,
                        column_start: n16(item, "column_start")?,
                        column_end: n16(item, "column_end")?,
                        flags: n8(item, "flags")?,
                    });
                }
                ensure(regions.len() == usize::from(n16(row, "region_count")?))?;
                P::RegionSet {
                    surface_matrix_ref: n16(row, "surface_matrix_ref")?,
                    regions,
                }
            }
            "SEMANTIC_BINDING" => {
                closed(
                    row,
                    "kind record_id binding_class namespace_id semantic_code argument auxiliary",
                )?;
                P::SemanticBinding {
                    binding_class: n8(row, "binding_class")?,
                    namespace_id: n16(row, "namespace_id")?,
                    semantic_code: n16(row, "semantic_code")?,
                    argument: n16(row, "argument")?,
                    auxiliary: n16(row, "auxiliary")?,
                }
            }
            "OPAQUE_DATA" => {
                closed(row, "kind record_id data_binding_ref data")?;
                P::OpaqueData {
                    data_binding_ref: n16(row, "data_binding_ref")?,
                    data: nums32(row, "data")?,
                }
            }
            "PREDICATE_RESULT" => {
                closed(
                    row,
                    "kind record_id predicate_binding_ref subject_opaque_data_ref result_atom_vector_ref",
                )?;
                P::PredicateResult {
                    predicate_binding_ref: n16(row, "predicate_binding_ref")?,
                    subject_opaque_data_ref: n16(row, "subject_opaque_data_ref")?,
                    result_atom_vector_ref: n16(row, "result_atom_vector_ref")?,
                }
            }
            "FEEDBACK" => {
                closed(
                    row,
                    "kind record_id feedback_code display_ref predicate_result_ref",
                )?;
                P::Feedback {
                    feedback_code: n16(row, "feedback_code")?,
                    display_ref: n16(row, "display_ref")?,
                    predicate_result_ref: n16(row, "predicate_result_ref")?,
                }
            }
            "PASSIVE_TRACE" => {
                closed(
                    row,
                    "kind record_id presentation_ref region_set_ref resulting_presentation_ref limitation_text_ref action_count actions expected_outcome expected_feedback_ref expected_next_node_ref",
                )?;
                let actions = array(field(row, "actions")?)?
                    .iter()
                    .map(|item| {
                        hex(text(item)?)
                            .and_then(|raw| raw.try_into().map_err(|_| CarrierError::ManifestShape))
                    })
                    .collect::<Result<Vec<[u8; 4]>>>()?;
                ensure(actions.len() == usize::from(n16(row, "action_count")?))?;
                P::PassiveTrace {
                    presentation_ref: n16(row, "presentation_ref")?,
                    region_set_ref: n16(row, "region_set_ref")?,
                    resulting_presentation_ref: n16(row, "resulting_presentation_ref")?,
                    limitation_text_ref: n16(row, "limitation_text_ref")?,
                    actions,
                    expected_outcome: n8(row, "expected_outcome")?,
                    expected_feedback_ref: n16(row, "expected_feedback_ref")?,
                    expected_next_node_ref: n16(row, "expected_next_node_ref")?,
                }
            }
            "LESSON_NODE" => {
                closed(
                    row,
                    "kind record_id role response_shape answer_mode flags presentation_ref region_set_ref predicate_result_ref passive_trace_ref max_selections item_event_budget case_count cases default_feedback_ref default_next_node_ref",
                )?;
                let mut cases = Vec::new();
                for item in array(field(row, "cases")?)? {
                    closed(
                        item,
                        "case_class selection_count region_ids feedback_ref next_node_ref",
                    )?;
                    let region_ids = nums16(item, "region_ids")?;
                    ensure(region_ids.len() == usize::from(n16(item, "selection_count")?))?;
                    cases.push(LessonCase {
                        case_class: n8(item, "case_class")?,
                        region_ids,
                        feedback_ref: n16(item, "feedback_ref")?,
                        next_node_ref: n16(item, "next_node_ref")?,
                    });
                }
                ensure(cases.len() == usize::from(n16(row, "case_count")?))?;
                P::LessonNode {
                    role: n8(row, "role")?,
                    response_shape: n8(row, "response_shape")?,
                    answer_mode: n8(row, "answer_mode")?,
                    flags: n8(row, "flags")?,
                    presentation_ref: n16(row, "presentation_ref")?,
                    region_set_ref: n16(row, "region_set_ref")?,
                    predicate_result_ref: n16(row, "predicate_result_ref")?,
                    passive_trace_ref: n16(row, "passive_trace_ref")?,
                    max_selections: n16(row, "max_selections")?,
                    item_event_budget: n16(row, "item_event_budget")?,
                    cases,
                    default_feedback_ref: n16(row, "default_feedback_ref")?,
                    default_next_node_ref: n16(row, "default_next_node_ref")?,
                }
            }
            "ROOT" => {
                closed(row, "kind record_id entry_node_ref global_event_budget")?;
                P::Root {
                    entry_node_ref: n16(row, "entry_node_ref")?,
                    global_event_budget: n16(row, "global_event_budget")?,
                }
            }
            _ => return Err(CarrierError::ManifestShape),
        };
        records.push(Record::authoring(id, payload));
    }
    let encoded = gb_content::encode_content_v0(&gb_content::ContentAuthoringProjection::new(
        0,
        records.clone(),
    ))
    .map_err(|_| CarrierError::Section)?;
    ensure(
        encoded.len() == 575
            && number(field(base, "stream_length")?)? == 575
            && format!("{:x}", Sha256::digest(&encoded)) == text(field(base, "stream_sha256")?)?
            && encoded == hex(text(field(base, "stream_hex")?)?)?,
    )?;
    Ok((encoded, records))
}

fn edited(
    records: &[gb_content::Record],
    id: u16,
    edit: impl FnOnce(&mut gb_content::RecordPayload),
) -> Vec<gb_content::Record> {
    let mut result = records.to_vec();
    let index = result
        .iter()
        .position(|row| row.record_id() == id)
        .expect("owned miniature record");
    let mut payload = result[index].payload().clone();
    edit(&mut payload);
    result[index] = gb_content::Record::authoring(id, payload);
    result
}

fn record_refs(payload: &gb_content::RecordPayload) -> Vec<u16> {
    use gb_content::{FieldValue, RecordPayload as P};
    match payload {
        P::Text(_) => vec![],
        P::AtomSchema { entries, .. } => entries.iter().map(|entry| entry.label_text_ref).collect(),
        P::AtomVector {
            atom_schema_ref, ..
        }
        | P::Matrix {
            atom_schema_ref, ..
        } => vec![*atom_schema_ref],
        P::FieldSchema { fields } => fields
            .iter()
            .flat_map(|field| {
                [
                    field.name_text_ref,
                    if field.storage == 1 {
                        field.type_code
                    } else {
                        0
                    },
                ]
            })
            .collect(),
        P::Tuple {
            field_schema_ref,
            field_values,
        } => std::iter::once(*field_schema_ref)
            .chain(field_values.iter().flat_map(|value| match value {
                FieldValue::RecordRefs(ids) => ids.clone(),
                _ => vec![],
            }))
            .collect(),
        P::RegionSet {
            surface_matrix_ref,
            regions,
        } => std::iter::once(*surface_matrix_ref)
            .chain(regions.iter().map(|region| region.label_ref))
            .collect(),
        P::SemanticBinding {
            binding_class,
            argument,
            auxiliary,
            ..
        } => {
            if *binding_class == 1 {
                vec![*argument]
            } else {
                vec![*argument, *auxiliary]
            }
        }
        P::OpaqueData {
            data_binding_ref, ..
        } => vec![*data_binding_ref],
        P::PredicateResult {
            predicate_binding_ref,
            subject_opaque_data_ref,
            result_atom_vector_ref,
        } => vec![
            *predicate_binding_ref,
            *subject_opaque_data_ref,
            *result_atom_vector_ref,
        ],
        P::Feedback {
            display_ref,
            predicate_result_ref,
            ..
        } => vec![*display_ref, *predicate_result_ref],
        P::PassiveTrace {
            presentation_ref,
            region_set_ref,
            resulting_presentation_ref,
            limitation_text_ref,
            expected_feedback_ref,
            ..
        } => vec![
            *presentation_ref,
            *region_set_ref,
            *resulting_presentation_ref,
            *limitation_text_ref,
            *expected_feedback_ref,
        ],
        P::LessonNode {
            presentation_ref,
            region_set_ref,
            predicate_result_ref,
            passive_trace_ref,
            cases,
            default_feedback_ref,
            default_next_node_ref,
            ..
        } => [
            *presentation_ref,
            *region_set_ref,
            *predicate_result_ref,
            *passive_trace_ref,
            *default_feedback_ref,
            *default_next_node_ref,
        ]
        .into_iter()
        .chain(
            cases
                .iter()
                .flat_map(|case| [case.feedback_ref, case.next_node_ref]),
        )
        .collect(),
        P::Root { entry_node_ref, .. } => vec![*entry_node_ref],
    }
}

fn role_example(records: &[gb_content::Record], role: u8, mode: u8) -> Result<Vec<u8>> {
    use gb_content::{LessonCase, RecordPayload as P};
    let packed = mode == 1;
    let trace = role == 3 || packed;
    let predicate = role <= 3 || packed;
    let feedback = if packed {
        22
    } else if role == 4 {
        24
    } else {
        20
    };
    let records = edited(records, 28, |payload| {
        *payload = P::LessonNode {
            role,
            response_shape: 1,
            answer_mode: mode,
            flags: 0,
            presentation_ref: 14,
            region_set_ref: 15,
            predicate_result_ref: if predicate { 19 } else { 0 },
            passive_trace_ref: if trace { 25 } else { 0 },
            max_selections: 1,
            item_event_budget: 2,
            cases: if packed {
                vec![LessonCase {
                    case_class: 1,
                    region_ids: vec![],
                    feedback_ref: 21,
                    next_node_ref: 0,
                }]
            } else {
                vec![]
            },
            default_feedback_ref: feedback,
            default_next_node_ref: if packed { 28 } else { 0 },
        };
    });
    let records = edited(&records, 25, |payload| {
        *payload = P::PassiveTrace {
            presentation_ref: 14,
            region_set_ref: 15,
            resulting_presentation_ref: 0,
            limitation_text_ref: if role == 4 { 5 } else { 0 },
            actions: vec![[3, 0, 0, 0]],
            expected_outcome: if packed { 1 } else { 3 },
            expected_feedback_ref: if packed { 21 } else { feedback },
            expected_next_node_ref: 0,
        };
    });
    let records = edited(&records, 29, |payload| {
        *payload = P::Root {
            entry_node_ref: 28,
            global_event_budget: 2,
        };
    });
    let by_id: BTreeMap<_, _> = records.iter().map(|row| (row.record_id(), row)).collect();
    let mut reached = BTreeSet::new();
    let mut stack = vec![29];
    while let Some(id) = stack.pop() {
        if id != 0 && reached.insert(id) {
            stack.extend(record_refs(
                by_id.get(&id).ok_or(CarrierError::Section)?.payload(),
            ));
        }
    }
    let retained = records
        .into_iter()
        .filter(|row| reached.contains(&row.record_id()))
        .collect();
    gb_content::encode_content_v0(&gb_content::ContentAuthoringProjection::new(0, retained))
        .map_err(|_| CarrierError::Section)
}

fn content_teaching() -> Result<Vec<u8>> {
    use gb_content::RecordPayload as P;
    let (mini, records) = miniature()?;
    let mut supplement = Vec::new();
    let mutations: [[u32; 5]; 48] = [
        [0, 2, 0, 1, 0],
        [2, 2, 29, 28, 0],
        [4, 2, 1, 0, 0],
        [19, 2, 2, 1, 0],
        [563, 2, 29, 65535, 1],
        [571, 2, 26, 0, 0],
        [571, 2, 26, 27, 0],
        [573, 2, 8, 7, 0],
        [573, 2, 8, 9, 1],
        [573, 2, 8, 65535, 1],
        [555, 2, 3, 2, 0],
        [555, 2, 3, 4, 0],
        [6, 2, 1, 0, 0],
        [167, 2, 6, 0, 0],
        [167, 2, 6, 12, 0],
        [167, 2, 6, 1, 0],
        [169, 2, 2, 0, 0],
        [178, 1, 5, 6, 0],
        [129, 2, 2, 1, 0],
        [145, 1, 1, 0, 0],
        [158, 1, 1, 0, 1],
        [158, 1, 1, 2, 0],
        [193, 2, 6, 3, 0],
        [223, 1, 2, 3, 1],
        [223, 1, 2, 6, 0],
        [191, 1, 1, 0, 0],
        [224, 2, 9, 1, 0],
        [302, 2, 1, 0, 0],
        [314, 1, 3, 6, 0],
        [329, 2, 16, 6, 0],
        [343, 2, 17, 1, 0],
        [345, 2, 10, 9, 0],
        [359, 2, 0, 19, 0],
        [373, 2, 19, 0, 0],
        [493, 2, 2, 1, 0],
        [456, 1, 0, 1, 0],
        [514, 1, 0, 1, 0],
        [544, 1, 1, 0, 1],
        [439, 1, 1, 2, 0],
        [443, 2, 27, 26, 0],
        [435, 4, 50331648, 16777217, 0],
        [561, 2, 0, 27, 0],
        [413, 2, 5, 1, 0],
        [192, 1, 0, 1, 0],
        [250, 2, 1, 3, 0],
        [258, 2, 2, 1, 0],
        [545, 2, 14, 12, 1],
        [12, 1, 83, 255, 0],
    ];
    words16(&mut supplement, &[48]);
    for [offset, width, old, new, expected] in mutations {
        let offset = offset as usize;
        let width = width as usize;
        let mut changed = mini.clone();
        ensure(changed[offset..offset + width] == old.to_be_bytes()[4 - width..])?;
        changed[offset..offset + width].copy_from_slice(&new.to_be_bytes()[4 - width..]);
        let accepted = gb_content::stream_validation(&changed).is_ok();
        ensure(accepted == (expected == 1))?;
        words16(&mut supplement, &[offset as u16, width as u16]);
        words32(&mut supplement, &[old, new]);
        words16(&mut supplement, &[u16::from(accepted)]);
    }
    let roles: [[u16; 10]; 6] = [
        [1, 3, 1, 1, 0, 0, 0, 1, 1, 3],
        [2, 3, 1, 1, 0, 0, 0, 1, 1, 3],
        [3, 3, 1, 1, 0, 0, 1, 1, 1, 3],
        [4, 3, 0, 0, 0, 0, 0, 1, 5, 3],
        [5, 1, 1, 1, 1, 4096, 1, 1, 3, 2],
        [5, 2, 0, 0, 0, 0, 0, 0, 1, 3],
    ];
    words16(&mut supplement, &[6]);
    for row in roles {
        let raw = role_example(&records, row[0] as u8, row[1] as u8)?;
        let projection = gb_content::stream_validation(&raw).map_err(|_| CarrierError::Section)?;
        let mut run = gb_content::new_run(&projection);
        if row[1] == 1 {
            run = gb_content::step(&projection, run, &[1, 0, 0, 3]).0;
        }
        let (run, _) = gb_content::step(&projection, run, &[3, 0, 0, 0]);
        let state = gb_content::run_state_view(&run);
        let feedback = projection
            .records()
            .iter()
            .find(|record| record.record_id() == state.feedback_ref())
            .ok_or(CarrierError::Section)?;
        let P::Feedback { feedback_code, .. } = feedback.payload() else {
            return Err(CarrierError::Section);
        };
        ensure(*feedback_code == row[8] && u16::from(state.outcome()) == row[9])?;
        supplement.extend(row[..4].iter().map(|value| *value as u8));
        words16(&mut supplement, &row[4..6]);
        supplement.extend(row[6..].iter().map(|value| *value as u8));
    }
    words16(&mut supplement, &[4]);
    for row in [
        [6u16, 14, 12, 1, 1, 1],
        [6, 14, 12, 2, 2, 0],
        [4, 12, 12, 1, 1, 1],
        [6, 14, 12, 0, 0, 0],
    ] {
        let changed = if row[0] == 4 {
            edited(&records, 28, |payload| {
                if let P::LessonNode {
                    presentation_ref, ..
                } = payload
                {
                    *presentation_ref = 12;
                }
            })
        } else if row[3] != 1 {
            let with_schema = edited(&records, 13, |payload| {
                if let P::FieldSchema { fields } = payload {
                    if row[3] == 2 {
                        fields.last_mut().expect("miniature matrix field").count = 2;
                    } else {
                        fields.pop();
                    }
                }
            });
            edited(&with_schema, 14, |payload| {
                if let P::Tuple { field_values, .. } = payload {
                    if row[3] == 2 {
                        *field_values.last_mut().expect("miniature matrix field") =
                            gb_content::FieldValue::RecordRefs(vec![12, 12]);
                    } else {
                        field_values.pop();
                    }
                }
            })
        } else {
            records.clone()
        };
        let accepted =
            gb_content::encode_content_v0(&gb_content::ContentAuthoringProjection::new(0, changed))
                .is_ok();
        ensure(accepted == (row[5] == 1))?;
        words16(&mut supplement, &row);
    }
    let action_rows: [(u16, &[[u8; 4]], u8, u8, u8, &[u16], u8, u16, u16, u16, u16); 8] = [
        (26, &[[3, 0, 0, 0]], 2, 3, 1, &[], 1, 21, 27, 7, 1),
        (
            26,
            &[[1, 0, 0, 2], [3, 0, 0, 0]],
            2,
            3,
            1,
            &[2],
            2,
            23,
            26,
            6,
            0,
        ),
        (
            26,
            &[[1, 0, 0, 3], [3, 0, 0, 0]],
            2,
            3,
            1,
            &[3],
            2,
            22,
            26,
            6,
            0,
        ),
        (
            27,
            &[[1, 0, 0, 2], [1, 0, 0, 1], [3, 0, 0, 0]],
            2,
            3,
            2,
            &[1, 2],
            3,
            20,
            28,
            4,
            0,
        ),
        (
            28,
            &[[1, 0, 0, 1], [1, 0, 0, 1], [3, 0, 0, 0]],
            2,
            3,
            3,
            &[1, 1],
            3,
            24,
            0,
            3,
            0,
        ),
        (
            28,
            &[[1, 0, 0, 2], [1, 0, 0, 1], [3, 0, 0, 0]],
            2,
            3,
            3,
            &[2, 1],
            3,
            24,
            0,
            3,
            0,
        ),
        (
            26,
            &[[1, 0, 0, 1], [1, 0, 0, 1]],
            3,
            6,
            1,
            &[1],
            0,
            0,
            0,
            6,
            0,
        ),
        (
            26,
            &[[2, 0, 0, 0], [3, 0, 0, 0]],
            2,
            3,
            1,
            &[],
            1,
            21,
            27,
            6,
            0,
        ),
    ];
    words16(&mut supplement, &[8]);
    let projection = gb_content::stream_validation(&mini).map_err(|_| CarrierError::Section)?;
    for (node, actions, phase, result, shape, ids, outcome, feedback, next, global, local) in
        action_rows
    {
        let mut run = gb_content::new_run(&projection);
        for _ in 26..node {
            run = gb_content::step(&projection, run, &[3, 0, 0, 0]).0;
            run = gb_content::advance_committed(&projection, &run)
                .map_err(|_| CarrierError::Section)?;
        }
        let mut last = 0;
        for action in actions {
            (run, last) = gb_content::step(&projection, run, action);
        }
        let view = gb_content::run_state_view(&run);
        let actual_ids = if view.phase() == 2 {
            let response = view.committed_response();
            ensure(
                response[0] == shape && response.len() == 3 + 2 * usize::from(u16_at(response, 1)?),
            )?;
            response[3..]
                .chunks_exact(2)
                .map(|pair| u16::from_be_bytes([pair[0], pair[1]]))
                .collect::<Vec<_>>()
        } else {
            view.selection_buffer().to_vec()
        };
        ensure(
            view.current_node_id() == node
                && view.phase() == phase
                && last == result
                && actual_ids == ids
                && view.outcome() == outcome
                && view.feedback_ref() == feedback
                && view.next_node_ref() == next
                && view.global_remaining() == global
                && view.local_remaining() == local,
        )?;
        words16(&mut supplement, &[node]);
        supplement.push(actions.len() as u8);
        for index in 0..3 {
            supplement.extend(actions.get(index).copied().unwrap_or([0; 4]));
        }
        supplement.extend([phase, last, shape, ids.len() as u8]);
        for index in 0..2 {
            words16(&mut supplement, &[ids.get(index).copied().unwrap_or(0)]);
        }
        supplement.push(outcome);
        words16(&mut supplement, &[feedback, next, global, local]);
    }
    ensure(supplement.len() == 1056)?;
    let mut value = Vec::new();
    words32(&mut value, &[mini.len() as u32]);
    value.extend(mini);
    words32(&mut value, &[supplement.len() as u32]);
    value.extend(supplement);
    ensure(value.len() == 1639)?;
    Ok(value)
}

fn content_frames(raw: &[u8]) -> Result<Vec<&[u8]>> {
    gb_content::stream_validation(raw).map_err(|_| CarrierError::Section)?;
    let mut cursor = 4;
    let mut frames = Vec::new();
    while cursor < raw.len() {
        let end = cursor + 8 + u32_at(raw, cursor + 4)? as usize;
        frames.push(raw.get(cursor..end).ok_or(CarrierError::Section)?);
        cursor = end;
    }
    ensure(frames.len() == usize::from(u16_at(raw, 2)?))?;
    Ok(frames)
}

/// Carried canonical chess relationships, constructed and checked from source.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PositionTeachingV2 {
    value: Vec<u8>,
}

impl PositionTeachingV2 {
    pub fn value(&self) -> &[u8] {
        &self.value
    }
}

fn fixture_parts(raw: &[u8], kind: u8) -> Result<(&[u8], &[u8], &[u8])> {
    ensure(raw.len() <= 16384 && raw.get(..2) == Some(&[0, kind]))?;
    let mut cursor = 2;
    let mut parts = Vec::new();
    for _ in 0..3 {
        let length = usize::from(u16_at(raw, cursor)?);
        cursor += 2;
        let end = cursor.checked_add(length).ok_or(CarrierError::Arithmetic)?;
        parts.push(raw.get(cursor..end).ok_or(CarrierError::Section)?);
        cursor = end;
    }
    ensure(cursor == raw.len() && parts[0].len() % 2 == 0 && parts[1].len() == 2)?;
    Ok((parts[0], parts[1], parts[2]))
}

fn chess_moves(raw: &[u8]) -> Result<Vec<gb_chess::Move>> {
    ensure(raw.len() % 2 == 0 && raw.len() <= 8192)?;
    raw.chunks_exact(2)
        .map(|wire| gb_chess::decode_move(wire).map_err(|_| CarrierError::Section))
        .collect()
}

fn opaque_subject(
    slice: &SliceCompilation,
    section: u16,
    namespace: u16,
    binding: u16,
    opaque: u16,
    expected: &[u8],
) -> Result<Vec<u8>> {
    use gb_content::RecordPayload as P;
    let assignment = slice
        .assignments()
        .iter()
        .find(|assignment| assignment.section_id() == section)
        .ok_or(CarrierError::Section)?;
    ensure(assignment.record_ids() == [binding, opaque])?;
    let records = slice.all_projection().records();
    let binding_row = records
        .iter()
        .find(|row| row.record_id() == binding)
        .ok_or(CarrierError::Section)?;
    ensure(
        matches!(binding_row.payload(),P::SemanticBinding {binding_class:1,namespace_id,semantic_code:1,..} if *namespace_id==namespace),
    )?;
    let opaque_row = records
        .iter()
        .find(|row| row.record_id() == opaque)
        .ok_or(CarrierError::Section)?;
    let P::OpaqueData {
        data_binding_ref,
        data,
    } = opaque_row.payload()
    else {
        return Err(CarrierError::Section);
    };
    let bytes = data
        .iter()
        .map(|value| u8::try_from(*value).map_err(|_| CarrierError::Section))
        .collect::<Result<Vec<_>>>()?;
    ensure(*data_binding_ref == binding && bytes == expected)?;
    Ok(bytes)
}

/// Tie pure Position67, tagged fixture results, Move16 and game framing to
/// actual decoded subjects and public chess replay. Wire-valid need not be legal.
pub fn build_position_teaching_v2(slice: &SliceCompilation) -> Result<PositionTeachingV2> {
    ensure(
        slice.game_payloads().len() == 64
            && slice.fixture_payloads().len() == 10
            && slice.assignments().len() == 78,
    )?;
    for (stream, projection) in [
        (slice.required_stream(), slice.required_projection()),
        (slice.all_stream(), slice.all_projection()),
    ] {
        ensure(stream.len() <= 1048576)?;
        gb_content::stream_validation(stream).map_err(|_| CarrierError::Section)?;
        let authored =
            gb_content::authoring_from_validated(projection).map_err(|_| CarrierError::Section)?;
        ensure(
            gb_content::encode_content_v0(&authored).map_err(|_| CarrierError::Section)? == stream,
        )?;
    }
    let game = opaque_subject(slice, 100, 2, 588, 589, &slice.game_payloads()[0])?;
    ensure(game.len() == 69 && u16_at(&game, 0)? == 33 && game[68] == 0)?;
    let source_game = gb_chess::source::decode_game(&game).map_err(|_| CarrierError::Section)?;
    ensure(gb_chess::source::encode_game(&source_game) == game)?;
    let moves = chess_moves(&game[2..68])?;
    ensure(gb_chess::encode_move(moves[0]) == [0x31, 0xc0])?;
    let matrix = slice
        .required_projection()
        .records()
        .iter()
        .find(|record| record.record_id() == 43)
        .ok_or(CarrierError::Section)?;
    let gb_content::RecordPayload::Matrix {
        rows,
        columns,
        cells,
        ..
    } = matrix.payload()
    else {
        return Err(CarrierError::Section);
    };
    ensure(*rows == 20 && *columns == 27 && cells.len() == 540)?;
    let extraction = [
        [204u16, 0, 8],
        [177, 8, 8],
        [150, 16, 8],
        [123, 24, 8],
        [96, 32, 8],
        [69, 40, 8],
        [42, 48, 8],
        [15, 56, 8],
        [258, 64, 3],
    ];
    let mut first = vec![0u8; 67];
    for [cell, offset, count] in extraction {
        for index in 0..usize::from(count) {
            first[usize::from(offset) + index] = u8::try_from(cells[usize::from(cell) + index])
                .map_err(|_| CarrierError::Section)?;
        }
    }
    let first_state =
        gb_chess::replay_from_start(&moves[..1]).map_err(|_| CarrierError::Section)?;
    ensure(
        gb_chess::encode_position(first_state.position()).as_slice() == first
            && first
                == hex(concat!(
                    "0402030506030204010101010001010100000000000000000000000001000000",
                    "0000000000000000000000000000000007070707070707070a08090b0c09080a",
                    "010f15"
                ))?,
    )?;
    let fixture = opaque_subject(slice, 200, 3, 716, 717, &slice.fixture_payloads()[0])?;
    let (prior, subject, expected) = fixture_parts(&fixture, 1)?;
    ensure(
        fixture.len() == 90
            && prior.len() == 12
            && subject == [0x10, 0x60]
            && expected.len() == 68
            && expected[0] == 1
            && expected == &fixture[22..90],
    )?;
    let before =
        gb_chess::replay_from_start(&chess_moves(prior)?).map_err(|_| CarrierError::Section)?;
    let after = gb_chess::apply_move(
        &before,
        gb_chess::decode_move(subject).map_err(|_| CarrierError::Section)?,
    )
    .map_err(|_| CarrierError::Section)?;
    let second = &expected[1..];
    ensure(gb_chess::encode_position(after.position()).as_slice() == second)?;
    for raw in [&first[..], second] {
        let position = gb_chess::decode_position(raw).map_err(|_| CarrierError::Section)?;
        ensure(gb_chess::encode_position(&position).as_slice() == raw)?;
    }
    let (promotion_prior, promotion_subject, _) = fixture_parts(&slice.fixture_payloads()[3], 4)?;
    ensure(promotion_subject == [0xc7, 0x92])?;
    let promotion = u16::from_be_bytes(
        promotion_subject
            .try_into()
            .map_err(|_| CarrierError::Section)?,
    );
    for index in 0..4 {
        let (_, subject, _) = fixture_parts(&slice.fixture_payloads()[3 + index], 4 + index as u8)?;
        ensure(u16_at(subject, 0)? == ((promotion & !14) | ((index as u16 + 1) << 1)))?;
    }
    let pre_promotion = gb_chess::replay_from_start(&chess_moves(promotion_prior)?)
        .map_err(|_| CarrierError::Section)?;
    let missing = gb_chess::decode_move(&(promotion & !14).to_be_bytes())
        .map_err(|_| CarrierError::Section)?;
    ensure(
        gb_chess::apply_move(&pre_promotion, missing).is_err()
            && gb_chess::apply_move(
                &pre_promotion,
                gb_chess::decode_move(promotion_subject).map_err(|_| CarrierError::Section)?,
            )
            .is_ok(),
    )?;
    let first_move = u16::from_be_bytes(gb_chess::encode_move(moves[0]));
    let origin = first_move >> 10;
    let mut wires = (0..8)
        .map(|code| (promotion & !14) | (code << 1))
        .collect::<Vec<u16>>();
    wires.extend([
        u16::from_be_bytes(gb_chess::encode_move(moves[2])),
        u16::from_be_bytes(gb_chess::encode_move(moves[3])),
        first_move | 1,
        (first_move & !0x3f0) | (origin << 4),
    ]);
    ensure(
        wires
            == [
                0xc790, 0xc792, 0xc794, 0xc796, 0xc798, 0xc79a, 0xc79c, 0xc79e, 0x1950, 0xe6a0,
                0x31c1, 0x30c0,
            ],
    )?;
    let mut value = Vec::new();
    words16(&mut value, &[2]);
    layout(&mut value, &[(0, 64), (64, 1), (65, 1), (66, 1)]);
    words16(&mut value, &[0, 43, 67, 9]);
    for row in extraction {
        words16(&mut value, &row);
    }
    value.extend(first);
    words16(&mut value, &[1, 717, 22, 68, 23, 67]);
    value.extend(expected);
    value.extend(second);
    layout(&mut value, &[(10, 6), (4, 6), (1, 3), (0, 1)]);
    words16(&mut value, &[12]);
    for (index, wire) in wires.into_iter().enumerate() {
        let admitted = gb_chess::decode_move(&wire.to_be_bytes());
        ensure(admitted.is_ok() == matches!(index, 0..=4 | 8 | 9))?;
        if let Ok(mv) = admitted {
            ensure(gb_chess::encode_move(mv) == wire.to_be_bytes())?;
        }
        words16(&mut value, &[wire]);
        value.extend([
            (wire >> 10) as u8,
            ((wire >> 4) & 63) as u8,
            ((wire >> 1) & 7) as u8,
            u8::from(admitted.is_ok()),
        ]);
    }
    words16(&mut value, &[1, 589, game.len() as u16]);
    layout(&mut value, &[(0, 2), (2, 66), (68, 1)]);
    ensure(value.len() == 408)?;
    Ok(PositionTeachingV2 { value })
}

fn twelfth(slice: &SliceCompilation) -> Result<Vec<u8>> {
    let required = content_frames(slice.required_stream())?;
    let all = content_frames(slice.all_stream())?;
    let first = required.get(..12).ok_or(CarrierError::Section)?;
    ensure(
        first
            .iter()
            .map(|frame| u16_at(frame, 2))
            .collect::<Result<Vec<_>>>()?
            == [2, 3, 4, 7, 8, 9, 8, 10, 4, 11, 12, 13],
    )?;
    for (stream, projection) in [
        (slice.required_stream(), slice.required_projection()),
        (slice.all_stream(), slice.all_projection()),
    ] {
        let authored =
            gb_content::authoring_from_validated(projection).map_err(|_| CarrierError::Section)?;
        ensure(
            gb_content::encode_content_v0(&authored).map_err(|_| CarrierError::Section)? == stream,
        )?;
    }
    let mut value = Vec::new();
    words16(
        &mut value,
        &[
            0,
            required.len() as u16,
            slice.required_projection().root_record_id(),
            1,
            all.len() as u16,
            slice.all_projection().root_record_id(),
            2,
            29,
            29,
        ],
    );
    for rows in [
        &[(0, 2), (2, 2)][..],
        &[(0, 2), (2, 2), (4, 4)],
        &[(0, 1), (1, 1), (2, 2), (4, 2), (6, 2), (8, 2)],
        &[(0, 2), (2, 2)],
        &[(0, 2)],
        &[
            (0, 2),
            (2, 1),
            (3, 1),
            (4, 2),
            (6, 2),
            (8, 4),
            (12, 2),
            (14, 4),
            (18, 4),
        ],
    ] {
        layout(&mut value, rows);
    }
    for row in [
        [1, 1, 0],
        [2, 5, 0],
        [3, 4, 0],
        [4, 7, 0],
        [5, 10, 0],
        [6, 3, 0],
        [7, 18, 0],
        [8, 10, 1],
        [9, 3, 0],
        [10, 6, 1],
        [11, 6, 1],
        [12, 20, 0],
        [13, 22, 0],
        [14, 4, 1],
    ] {
        words16(&mut value, &row);
    }
    value.extend(content_teaching()?);
    let by_id: BTreeMap<_, _> = required
        .iter()
        .map(|frame| Ok((u16_at(frame, 0)?, *frame)))
        .collect::<Result<_>>()?;
    let root = required.last().ok_or(CarrierError::Section)?;
    ensure(u16_at(root, 2)? == 14)?;
    let refs = [
        (first[4], 6, false),
        (first[4], 8, true),
        (first[6], 6, false),
        (first[6], 8, false),
        (first[5], 0, false),
        (first[2], 0, false),
        (first[9], 2, false),
        (first[11], first[11].len() - 10, false),
        (*root, 0, false),
        (*root, 2, true),
    ];
    for (index, (frame, offset, scalar)) in refs.into_iter().enumerate() {
        let owner = u16_at(frame, 0)?;
        let target = u16_at(frame, 8 + offset)?;
        let kind = if scalar {
            0
        } else {
            u16_at(by_id.get(&target).ok_or(CarrierError::Section)?, 2)?
        };
        if index == 7 {
            ensure(target > owner && kind == 13)?;
        } else if !scalar {
            ensure(target < owner)?;
        }
        words16(&mut value, &[owner, offset as u16, target, kind]);
    }
    for row in [[3, 5, 8], [3, 5, 7], [8, 1, 9], [8, 1, 8]] {
        words16(&mut value, &row);
    }
    let all_by_id: BTreeMap<_, _> = all
        .iter()
        .map(|frame| Ok((u16_at(frame, 0)?, *frame)))
        .collect::<Result<_>>()?;
    let mut bridges = Vec::new();
    for (section, namespace, expected) in [
        (100u16, 2u16, slice.game_payloads().first()),
        (200, 3, slice.fixture_payloads().first()),
    ] {
        let assignment = slice
            .assignments()
            .iter()
            .find(|assignment| assignment.section_id() == section)
            .ok_or(CarrierError::Section)?;
        let ids = assignment.record_ids();
        ensure(ids.len() == 2)?;
        let binding = *all_by_id.get(&ids[0]).ok_or(CarrierError::Section)?;
        let opaque = *all_by_id.get(&ids[1]).ok_or(CarrierError::Section)?;
        ensure(
            u16_at(binding, 2)? == 8
                && u16_at(opaque, 2)? == 9
                && binding[8] == 1
                && u16_at(binding, 10)? == namespace
                && u16_at(binding, 12)? == 1
                && u16_at(opaque, 8)? == ids[0]
                && opaque.get(10..) == expected.map(Vec::as_slice),
        )?;
        bridges.push((section, namespace, binding, opaque));
    }
    for (_, _, binding, _) in &bridges {
        value.extend(*binding);
    }
    for (_, _, _, opaque) in &bridges {
        value.extend(&opaque[8..10]);
    }
    for (section, namespace, binding, opaque) in bridges {
        words32(&mut value, &[u32::from(section)]);
        words16(
            &mut value,
            &[u16_at(binding, 0)?, u16_at(opaque, 0)?, namespace, 1],
        );
    }
    ensure(value.len() == 2013)?;
    value.extend(build_position_teaching_v2(slice)?.value());
    Ok(value)
}

fn definitions(slice: &SliceCompilation, package: &RecipePackageV1) -> Result<Vec<Vec<u8>>> {
    let mut values = first_six(package)?;
    let a = example_common(0)?;
    let b = example_common(1)?;
    values.push(seventh(&a, &b)?);
    values.push(eighth(&a, &b, package)?);
    values.push(ninth()?);
    values.push(tenth(&a, &b, package)?);
    values.push(eleventh(&a)?);
    values.push(twelfth(slice)?);
    ensure(
        values.iter().map(Vec::len).collect::<Vec<_>>()
            == [16, 64, 96, 296, 226, 210, 636, 544, 464, 443, 314, 2421],
    )?;
    Ok(values)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn full_physical_identity_rejects_each_changed_key_byte_without_losing_candidate() {
        let a = example_common(0).unwrap();
        let b = example_common(1).unwrap();
        let package =
            decode_recipe_package_v1(&build_teaching_recipe_package().unwrap(), 8).unwrap();
        let lanes = [Some(observation(&a, &[])), Some(observation(&a, &[]))];
        let key = common_identity(&a);
        let mut counts = BTreeSet::new();
        let (_, _, valid) = group_observation(&lanes, &key, &a, &b, &package, &mut counts).unwrap();
        assert_eq!(valid, [1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 2, 1]);
        for byte in 0..20 {
            let mut wrong_key = key;
            wrong_key[byte] ^= 1;
            let (_, states, trace) =
                group_observation(&lanes, &wrong_key, &a, &b, &package, &mut counts).unwrap();
            assert_eq!(states, [2, 2, 3, 1, 2, 1]);
            assert_eq!(
                trace,
                [1, 1, 0, 0, 0, 1, 1, 1, 0, 1, 2, 0],
                "key byte {byte}"
            );
        }
    }

    #[test]
    fn unknown_symbol_trace_keeps_failed_lanes_and_combines_only_known_symbols() {
        let a = example_common(0).unwrap();
        let b = example_common(1).unwrap();
        let package =
            decode_recipe_package_v1(&build_teaching_recipe_package().unwrap(), 8).unwrap();
        let mut lanes = Vec::new();
        for first in [59u8, 60, 61, 62, 63] {
            let mut lane = observation(&a, &[]);
            for bit in first..first + 5 {
                lane.encoded[usize::from(bit) / 8] &= !(1 << (7 - bit % 8));
                lane.erasures.push(crate::candidate::EhErasure {
                    codeword: 0,
                    position: bit + 1,
                });
            }
            assert!(crate::candidate::decode_eh_unit(&lane, 8).is_err());
            lanes.push(Some(lane));
        }
        let repetition = crate::candidate::aggregate_repetition_observation(&lanes)
            .unwrap()
            .unwrap();
        assert_eq!(
            repetition.erasures,
            [crate::candidate::EhErasure {
                codeword: 0,
                position: 64
            }]
        );
        let mut expected_encoded = crate::candidate::encode_eh_unit(&a);
        expected_encoded[7] &= !1;
        assert_eq!(repetition.encoded, expected_encoded);
        assert_eq!(
            crate::candidate::decode_eh_unit(&repetition, 8)
                .unwrap()
                .common,
            a
        );
        let (row, states, trace) = group_observation(
            &lanes,
            &common_identity(&a),
            &a,
            &b,
            &package,
            &mut BTreeSet::new(),
        )
        .unwrap();
        assert_eq!(row, [5, 5, 0, 1, 0, 1, 1, 0]);
        assert_eq!(states, [1, 1, 1, 1, 1, 3, 1, 3, 1]);
        assert_eq!(trace, [0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 3, 1]);
        for lane in lanes.iter_mut().flatten() {
            lane.erasures.clear();
        }
        let guessed = crate::candidate::aggregate_repetition_observation(&lanes)
            .unwrap()
            .unwrap();
        assert!(crate::candidate::decode_eh_unit(&guessed, 8).is_err());
        let (_, guessed_states, guessed_trace) = group_observation(
            &lanes,
            &common_identity(&a),
            &a,
            &b,
            &package,
            &mut BTreeSet::new(),
        )
        .unwrap();
        assert_eq!(guessed_states, [1, 1, 1, 1, 1, 1, 0, 1, 0]);
        assert_eq!(guessed_trace, [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0]);
    }

    #[test]
    fn semantic_miniature_and_every_typed_role_witness_are_admitted() {
        let (raw, records) = miniature().expect("semantic miniature source");
        assert_eq!(raw.len(), 575);
        for (role, mode) in [(1, 3), (2, 3), (3, 3), (4, 3), (5, 1), (5, 2)] {
            role_example(&records, role, mode)
                .unwrap_or_else(|error| panic!("role={role}, mode={mode}: {error:?}"));
        }
        assert_eq!(
            content_teaching().expect("all content consequences").len(),
            1639
        );
    }
}

/// Fill every actual sector, retaining exact shared headroom and fixed padding.
/// Mapping admissibility and complete carrier selection are separate checks.
pub fn build_route_images(slice: &SliceCompilation, side: u16, width: u16) -> Result<RouteImages> {
    if !(64..=2048).contains(&side)
        || side % 8 != 0
        || !(8..=128).contains(&width)
        || width % 8 != 0
        || 2 * u32::from(width) + 8 > u32::from(side)
    {
        return Err(CarrierError::Geometry);
    }
    let capacity = usize::from(width) * usize::from(side - width);
    let prefixes = prefixes_with_spans(slice)?;
    let instruction_cells: usize = prefixes.iter().map(|row| row.0.len() * 8).sum();
    let headroom = instruction_cells.div_ceil(20).max(1024);
    let extra = headroom - 1024;
    let mut sectors = Vec::new();
    for (sector, (prefix, mut owners)) in prefixes.into_iter().enumerate() {
        let prefix_cells = prefix.len() * 8;
        let assigned = 256 + extra / 4 + usize::from(sector < extra % 4);
        if prefix_cells + assigned > capacity {
            return Err(CarrierError::RouteFit);
        }
        let mut cells = bits(&prefix);
        cells.extend(bits(&prefix[..32]));
        let mut counter = 0u64;
        while cells.len() < capacity {
            let mut hash = Sha256::new();
            hash.update(b"GB-M2-SHELL-PAD-v0\0");
            hash.update(8u16.to_be_bytes());
            hash.update([sector as u8]);
            hash.update(counter.to_be_bytes());
            cells.extend(bits(&hash.finalize()));
            counter += 1;
        }
        cells.truncate(capacity);
        owners.push((ShellOwner::Headroom, assigned));
        owners.push((ShellOwner::FixedPad, capacity - prefix_cells - assigned));
        let mut first = 0u64;
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
            .collect();
        ensure(first == capacity as u64)?;
        sectors.push(SectorImage {
            sector_id: sector as u8,
            bits: cells,
            route_prefix_cells: prefix_cells as u64,
            headroom_cells: assigned as u64,
            spans,
        });
    }
    Ok(RouteImages {
        instruction_cells: instruction_cells as u64,
        headroom_cells: headroom as u64,
        sectors: sectors.try_into().map_err(|_| CarrierError::Arithmetic)?,
    })
}
