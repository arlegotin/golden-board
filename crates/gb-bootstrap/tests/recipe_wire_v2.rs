use gb_bootstrap::recipe::{RecipeValue, decode_recipe_package};
use gb_bootstrap::recipe_wire_v1::{decode_recipe_package_v1, encode_recipe_package_v1};
use gb_bootstrap::recipe_wire_v2::{
    decode_recipe_package_v2, encode_recipe_package_v2, evaluate_recipe_v2,
    evaluate_serialized_recipe_v2, expand_recipe_package_v2,
};
use gb_bootstrap::teaching_recipe_v2::build_teaching_recipe_package;
use sha2::{Digest, Sha256};

fn put16(raw: &mut [u8], at: usize, value: u16) {
    raw[at..at + 2].copy_from_slice(&value.to_be_bytes());
}

fn put32(raw: &mut [u8], at: usize, value: usize) {
    raw[at..at + 4].copy_from_slice(&(value as u32).to_be_bytes());
}

fn put64(raw: &mut [u8], at: usize, value: u64) {
    raw[at..at + 8].copy_from_slice(&value.to_be_bytes());
}

// Independent, hand-authored logical constant program: CONST, SUCCESS,
// EMIT(status), EMIT(value). Four steps, two edges, twelve live scratch bytes.
fn constant_program(value: u64) -> Vec<u8> {
    let mut raw = vec![0; 248];
    raw[..8].copy_from_slice(b"GBRECP0\0");
    put16(&mut raw, 12, 8);
    put16(&mut raw, 16, 1);
    put32(&mut raw, 20, 4);
    put32(&mut raw, 24, 2);
    put32(&mut raw, 32, 248);
    put64(&mut raw, 36, 4);
    put32(&mut raw, 44, 12);
    put16(&mut raw, 64, 1);
    put16(&mut raw, 70, 2);
    put32(&mut raw, 72, 4);
    put32(&mut raw, 76, 2);
    put64(&mut raw, 80, 4);
    put32(&mut raw, 88, 12);
    put32(&mut raw, 92, 184);
    for (offset, id, kind, width) in [(96, 1, 5, 16), (108, 2, 0, 64)] {
        put16(&mut raw, offset, id);
        raw[offset + 2] = kind;
        put32(&mut raw, offset + 4, width);
        put32(&mut raw, offset + 8, 1);
    }
    for (ordinal, op, kind, width, argument, auxiliary, immediate) in [
        (1, 1, 0, 64, 0, 0, value),
        (2, 24, 5, 16, 0, 0, 0),
        (3, 5, 5, 16, 2, 1, 0),
        (4, 5, 5, 16, 1, 2, 0),
    ] {
        let at = 120 + 32 * (ordinal - 1);
        put16(&mut raw, at, ordinal as u16);
        raw[at + 2] = op;
        raw[at + 3] = kind;
        put32(&mut raw, at + 4, width);
        put16(&mut raw, at + 8, u16::from(argument != 0));
        put16(&mut raw, at + 10, argument);
        put16(&mut raw, at + 18, auxiliary);
        put64(&mut raw, at + 24, immediate);
    }
    raw
}

fn replace_field(raw: &[u8], at: usize, length: usize, value: &[u8]) -> Vec<u8> {
    let mut changed = raw.to_vec();
    changed.splice(at..at + length, value.iter().copied());
    let size = changed.len();
    put32(&mut changed, 32, size);
    put32(&mut changed, 92, size - 64);
    changed
}

fn first_node_offset(raw: &[u8], recipe: usize) -> usize {
    // Independent fixture scan, deliberately not the production decoder.
    let count = usize::from(u16::from_be_bytes(
        raw[recipe + 4..recipe + 6].try_into().unwrap(),
    )) + usize::from(u16::from_be_bytes(
        raw[recipe + 6..recipe + 8].try_into().unwrap(),
    ));
    let mut cursor = recipe + 32;
    for _ in 0..count {
        cursor += 1;
        for index in 0..5 {
            let digit = raw[cursor];
            cursor += 1;
            if digit & 128 == 0 {
                break;
            }
            assert!(index < 4);
        }
    }
    cursor
}

#[test]
fn canonical_scalar_boundaries_match_hand_authored_wire_and_execute() {
    for (value, scalar) in [
        (0, vec![0]),
        (1, vec![1]),
        (127, vec![127]),
        (128, vec![128, 1]),
        (255, vec![255, 1]),
        (256, vec![128, 2]),
        (16383, vec![255, 127]),
        (16384, vec![128, 128, 1]),
        (65535, vec![255, 255, 3]),
        (
            u64::MAX,
            vec![255, 255, 255, 255, 255, 255, 255, 255, 255, 1],
        ),
    ] {
        let expanded = constant_program(value);
        let encoded = encode_recipe_package_v2(&expanded, 8).unwrap();
        let mut expected = vec![5, 16, 0, 64, 1, 64];
        expected.extend(scalar);
        expected.extend([184, 16, 165, 16, 2, 1, 0, 165, 16, 1, 2, 0]);
        assert_eq!(&encoded[8..10], &[0, 2]);
        assert_eq!(&encoded[96..], expected);
        assert_eq!(expand_recipe_package_v2(&encoded, 8).unwrap(), expanded);
        let mut answer = vec![0, 0];
        answer.extend(value.to_be_bytes());
        assert_eq!(
            evaluate_serialized_recipe_v2(&encoded, 8, 1, &[]).unwrap(),
            answer
        );
    }
}

#[test]
fn profile8_package_round_trip_preserves_complete_logical_resources() {
    let active = build_teaching_recipe_package().unwrap();
    let expanded = expand_recipe_package_v2(&active, 8).unwrap();
    let previous = encode_recipe_package_v1(&expanded, 8).unwrap();
    let encoded = encode_recipe_package_v2(&expanded, 8).unwrap();
    let parsed = decode_recipe_package_v2(&encoded, 8).unwrap();
    assert_eq!(
        parsed.logical,
        decode_recipe_package_v1(&previous, 8).unwrap().logical
    );
    assert_eq!(expand_recipe_package_v2(&encoded, 8).unwrap(), expanded);
    assert!(encoded.len() < previous.len());
    assert!(decode_recipe_package_v1(&encoded, 8).is_err());
    assert!(decode_recipe_package(&encoded, 8).is_err());
    assert!(decode_recipe_package_v2(&previous, 8).is_err());
    println!(
        "wire1={} wire2={} expanded={} sha256={:x}",
        previous.len(),
        encoded.len(),
        expanded.len(),
        Sha256::digest(&encoded)
    );
}

#[test]
fn historical_profiles_and_invalid_logical_programs_are_not_reencoded() {
    let expanded = constant_program(0);
    let encoded = encode_recipe_package_v2(&expanded, 8).unwrap();
    for profile in [0, 1, 7, 9, u16::MAX] {
        let mut changed = expanded.clone();
        put16(&mut changed, 12, profile);
        assert!(encode_recipe_package_v2(&changed, profile).is_err());
        let mut changed = encoded.clone();
        put16(&mut changed, 12, profile);
        assert!(decode_recipe_package_v2(&changed, profile).is_err());
        assert!(decode_recipe_package_v2(&encoded, profile).is_err());
    }
    for at in [120 + 20, 36, 44, 120 + 10] {
        let mut changed = expanded.clone();
        changed[at] ^= 1;
        assert!(encode_recipe_package_v2(&changed, 8).is_err());
    }
}

#[test]
fn overlong_overflow_and_truncated_fields_reject_without_resynchronizing() {
    let encoded = encode_recipe_package_v2(&constant_program(0), 8).unwrap();
    let first = first_node_offset(&encoded, 64);
    // Node-one width/immediate and node-three argument/auxiliary/immediate.
    // Every mutation keeps outer lengths exact.
    for (offset, value) in [
        (1, vec![192, 0]),
        (1, vec![128, 128, 128, 128, 16]),
        (1, vec![128, 128, 128, 128, 128, 0]),
        (2, vec![128, 0]),
        (2, vec![128, 128, 128, 128, 128, 128, 128, 128, 128, 2]),
        (2, vec![128; 10]),
        (7, vec![130, 0]),
        (7, vec![128, 128, 4]),
        (7, vec![128, 128, 128, 0]),
        (8, vec![129, 0]),
        (8, vec![128, 128, 4]),
        (9, vec![128, 0]),
    ] {
        let at = first + offset;
        let changed = replace_field(&encoded, at, 1, &value);
        assert!(
            decode_recipe_package_v2(&changed, 8).is_err(),
            "field {at}: {value:?}"
        );
        assert!(expand_recipe_package_v2(&changed, 8).is_err());
    }
    for length in 0..encoded.len() {
        assert!(decode_recipe_package_v2(&encoded[..length], 8).is_err());
    }
    let mut changed = encoded.clone();
    changed.push(0);
    assert!(decode_recipe_package_v2(&changed, 8).is_err());
    assert!(decode_recipe_package_v2(&replace_field(&encoded, encoded.len(), 0, &[0]), 8).is_err());
    let last = encoded.len() - 1;
    assert!(decode_recipe_package_v2(&replace_field(&encoded, last, 1, &[128]), 8).is_err());
}

#[test]
fn evaluation_reparses_bytes_and_keeps_failure_output_suppression() {
    let active = build_teaching_recipe_package().unwrap();
    let expanded = expand_recipe_package_v2(&active, 8).unwrap();
    let encoded = encode_recipe_package_v2(&expanded, 8).unwrap();
    assert_eq!(
        evaluate_serialized_recipe_v2(&encoded, 8, 105, &[255; 4]).unwrap(),
        [0, 11]
    );
    assert_eq!(
        evaluate_serialized_recipe_v2(&encoded, 8, 212, &[]).unwrap(),
        [0, 4]
    );
    let mut parsed = decode_recipe_package_v2(&encoded, 8).unwrap();
    parsed.logical.maximum_primitive_steps = 0;
    parsed.logical.profile_version = 0;
    let outcome = evaluate_recipe_v2(
        &parsed,
        105,
        &[RecipeValue::Uint {
            width: 32,
            value: 1,
        }],
    )
    .unwrap();
    assert_eq!(outcome.status, 0);
    parsed.encoded[48] = 1;
    assert!(
        evaluate_recipe_v2(
            &parsed,
            105,
            &[RecipeValue::Uint {
                width: 32,
                value: 1
            }]
        )
        .is_err()
    );
}

#[test]
fn compact_inputs_still_require_full_logical_and_resource_admission() {
    let encoded = encode_recipe_package_v2(&constant_program(0), 8).unwrap();
    let first = first_node_offset(&encoded, 64);
    for (at, bytes) in [
        (10, vec![0, 1]),
        (14, vec![0, 1]),
        (16, vec![1, 1]),
        (18, vec![16, 1]),
        (20, vec![255; 4]),
        (24, vec![255; 4]),
        (28, vec![0, 0, 0, 1]),
        (36, vec![255; 8]),
        (43, vec![3]),
        (44, vec![255; 4]),
        (47, vec![11]),
        (48, vec![1]),
        (68, vec![0, 65]),
        (70, vec![0, 65]),
        (80, vec![255; 8]),
        (88, vec![255; 4]),
        (99, vec![1]),
        (first, vec![26]),
        (first, vec![193]),
        (first + 7, vec![3]),
        (first + 8, vec![2]),
    ] {
        let mut changed = encoded.clone();
        changed[at..at + bytes.len()].copy_from_slice(&bytes);
        assert!(
            decode_recipe_package_v2(&changed, 8).is_err(),
            "mutation at {at}"
        );
    }
    assert!(decode_recipe_package_v2(&vec![0; 1_048_577], 8).is_err());
}

#[test]
fn invalid_packed_tags_and_the_old_two_byte_grammar_reject() {
    let encoded = encode_recipe_package_v2(&constant_program(0), 8).unwrap();
    let first = first_node_offset(&encoded, 64);
    for tag in 0u8..=255 {
        if tag & 31 == 0 || tag & 31 > 25 || tag >> 5 > 5 {
            let mut changed = encoded.clone();
            changed[first] = tag;
            assert!(decode_recipe_package_v2(&changed, 8).is_err(), "tag {tag}");
        }
    }
    let old_nodes = [1, 0, 64, 0, 24, 5, 16, 5, 5, 16, 2, 1, 0, 5, 5, 16, 1, 2, 0];
    let old_grammar = replace_field(&encoded, first, encoded.len() - first, &old_nodes);
    assert!(decode_recipe_package_v2(&old_grammar, 8).is_err());
}

#[test]
fn malformed_compact_descriptors_reject_before_logical_execution() {
    let encoded = encode_recipe_package_v2(&constant_program(0), 8).unwrap();
    assert_eq!(first_node_offset(&encoded, 64), 100);
    for kind in [4, 6, 7, 255] {
        for at in [96, 98] {
            let mut changed = encoded.clone();
            changed[at] = kind;
            assert!(decode_recipe_package_v2(&changed, 8).is_err());
        }
    }
    for (at, value) in [
        (97, vec![144, 0]),
        (97, vec![128, 128, 128, 128, 16]),
        (97, vec![128, 128, 128, 128, 128, 0]),
        (97, vec![0]),
        (97, vec![8]),
        (99, vec![193, 0]),
        (99, vec![65]),
    ] {
        let changed = replace_field(&encoded, at, 1, &value);
        assert!(decode_recipe_package_v2(&changed, 8).is_err());
    }
    // Repair lengths after truncating within each descriptor.
    for end in 96..100 {
        let changed = replace_field(&encoded, end, encoded.len() - end, &[]);
        assert!(decode_recipe_package_v2(&changed, 8).is_err());
    }
    // The previous development grammar's fixed-width descriptor is not accepted.
    let expanded = constant_program(0);
    let changed = replace_field(&encoded, 96, 4, &expanded[96..120]);
    assert!(decode_recipe_package_v2(&changed, 8).is_err());
}

#[test]
fn descriptor_width_boundaries_and_separate_input_output_ordinals_round_trip() {
    for (width, scalar) in [
        (1, vec![1]),
        (127, vec![127]),
        (128, vec![128, 1]),
        (16383, vec![255, 127]),
        (16384, vec![128, 128, 1]),
        (1_048_576, vec![128, 128, 64]),
    ] {
        // Independent logical identity program. Input and output-one both
        // start at descriptor ID 1. Input storage is outside live-node scratch.
        let mut expanded = constant_program(0)[..96].to_vec();
        expanded.resize(228, 0);
        put16(&mut expanded, 68, 1);
        for at in [20, 72] {
            put32(&mut expanded, at, 3);
        }
        for at in [36, 80] {
            put64(&mut expanded, at, 3);
        }
        for at in [44, 88] {
            put32(&mut expanded, at, 4);
        }
        put32(&mut expanded, 32, 228);
        put32(&mut expanded, 92, 164);
        for (at, id, kind, value_width) in [(96, 1, 3, width), (108, 1, 5, 16), (120, 2, 3, width)]
        {
            put16(&mut expanded, at, id);
            expanded[at + 2] = kind;
            put32(&mut expanded, at + 4, value_width);
            put32(&mut expanded, at + 8, 1);
        }
        for (ordinal, op, argument, slot) in [(1, 24, 0, 0), (2, 5, 2, 1), (3, 5, 1, 2)] {
            let at = 132 + 32 * (ordinal - 1);
            put16(&mut expanded, at, ordinal as u16);
            expanded[at + 2] = op;
            expanded[at + 3] = 5;
            put32(&mut expanded, at + 4, 16);
            put16(&mut expanded, at + 8, u16::from(argument != 0));
            put16(&mut expanded, at + 10, argument);
            put16(&mut expanded, at + 18, slot);
        }
        let encoded = encode_recipe_package_v2(&expanded, 8).unwrap();
        let mut expected = vec![3];
        expected.extend(&scalar);
        expected.extend([5, 16, 3]);
        expected.extend(&scalar);
        assert_eq!(&encoded[96..first_node_offset(&encoded, 64)], expected);
        assert_eq!(expand_recipe_package_v2(&encoded, 8).unwrap(), expanded);
        if width <= 128 {
            let input = vec![7; width];
            let mut expected = vec![0, 0];
            expected.extend(&input);
            assert_eq!(
                evaluate_serialized_recipe_v2(&encoded, 8, 1, &input).unwrap(),
                expected
            );
        }
    }
}

#[test]
fn a_varint_cannot_borrow_its_terminal_byte_from_the_next_recipe() {
    let one = encode_recipe_package_v2(&constant_program(0), 8).unwrap();
    let mut pair = one.clone();
    let boundary = pair.len();
    pair.extend_from_slice(&one[64..]);
    put16(&mut pair, boundary, 256);
    put16(&mut pair, 16, 2);
    put32(&mut pair, 20, 8);
    put32(&mut pair, 24, 4);
    let size = pair.len();
    put32(&mut pair, 32, size);
    assert!(decode_recipe_package_v2(&pair, 8).is_ok());
    // The next recipe starts with01, a valid canonical terminator for80.
    pair[boundary - 1] = 128;
    assert_eq!(pair[boundary], 1);
    assert!(decode_recipe_package_v2(&pair, 8).is_err());
}

fn push_reference(raw: &mut Vec<u8>, value: usize) {
    // Fixture construction only: every reference fits its specified u16.
    assert!(value <= u16::MAX as usize);
    if value < 128 {
        raw.push(value as u8);
    } else if value < 16384 {
        raw.extend([(value as u8 & 127) | 128, (value >> 7) as u8]);
    } else {
        raw.extend([
            (value as u8 & 127) | 128,
            ((value >> 7) as u8 & 127) | 128,
            (value >> 14) as u8,
        ]);
    }
}

fn zero_chain(count: usize) -> Vec<u8> {
    let mut raw = constant_program(0)[..96].to_vec();
    raw.extend([5, 16, 0, 64]);
    put16(&mut raw, 8, 2);
    for at in [20, 72] {
        put32(&mut raw, at, count);
    }
    for at in [24, 76] {
        put32(&mut raw, at, 2 * count - 6);
    }
    for at in [36, 80] {
        put64(&mut raw, at, count as u64);
    }
    for at in [44, 88] {
        put32(&mut raw, at, 24);
    }
    raw.extend([1, 64, 0]);
    for reference in 1..count - 3 {
        raw.extend([6, 64, 1]);
        push_reference(&mut raw, reference);
    }
    raw.extend([184, 16, 165, 16]);
    push_reference(&mut raw, count - 2);
    raw.extend([1, 0, 165, 16]);
    push_reference(&mut raw, count - 3);
    raw.extend([2, 0]);
    let size = raw.len();
    put32(&mut raw, 32, size);
    put32(&mut raw, 92, size - 64);
    raw
}

#[test]
fn expanded_size_is_bounded_even_when_the_wire_package_fits() {
    let count = (1_048_576 - 120) / 32;
    let fitting = zero_chain(count);
    let expanded = expand_recipe_package_v2(&fitting, 8).unwrap();
    assert_eq!(expanded.len(), 1_048_568);
    assert_eq!(encode_recipe_package_v2(&expanded, 8).unwrap(), fitting);
    let too_large = zero_chain(count + 1);
    assert!(too_large.len() < 1_048_576);
    assert!(decode_recipe_package_v2(&too_large, 8).is_err());
    assert!(expand_recipe_package_v2(&too_large, 8).is_err());
}

#[test]
fn all_source_teaching_examples_preserve_exact_status_and_output_bytes() {
    let active = build_teaching_recipe_package().unwrap();
    let expanded = expand_recipe_package_v2(&active, 8).unwrap();
    let encoded = encode_recipe_package_v2(&expanded, 8).unwrap();
    let source: toml::Value =
        toml::from_str(include_str!("../../../spec/recipe-teaching-v2.toml")).unwrap();
    let hex = |value: &str| {
        value
            .as_bytes()
            .chunks_exact(2)
            .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
            .collect::<Vec<_>>()
    };
    for example in source["examples"].as_array().unwrap() {
        let id = example["recipe"].as_integer().unwrap() as u16;
        let input: Vec<u8> = example["inputs"]
            .as_array()
            .unwrap()
            .iter()
            .flat_map(|value| hex(value.as_str().unwrap()))
            .collect();
        let expected = hex(example["output"].as_str().unwrap());
        assert_eq!(
            evaluate_serialized_recipe_v2(&encoded, 8, id, &input).unwrap(),
            expected
        );
    }
}

#[test]
fn select_cannot_hide_failure_in_its_unselected_computation() {
    let mut expanded = constant_program(0)[..120].to_vec();
    expanded.resize(376, 0);
    for at in [20, 72] {
        put32(&mut expanded, at, 8);
    }
    for at in [24, 76] {
        put32(&mut expanded, at, 7);
    }
    for at in [36, 80] {
        put64(&mut expanded, at, 8);
    }
    for at in [44, 88] {
        put32(&mut expanded, at, 5);
    }
    put32(&mut expanded, 32, 376);
    put32(&mut expanded, 92, 312);
    put32(&mut expanded, 112, 8);
    for (ordinal, (op, kind, width, args, auxiliary, immediate)) in [
        (1, 1, 1, vec![], 0, 1),
        (1, 0, 8, vec![], 0, 1),
        (1, 0, 8, vec![], 0, 0),
        (9, 0, 8, vec![2, 3], 0, 0),
        (23, 0, 8, vec![1, 2, 4], 0, 0),
        (24, 5, 16, vec![], 0, 0),
        (5, 5, 16, vec![6], 1, 0),
        (5, 5, 16, vec![5], 2, 0),
    ]
    .into_iter()
    .enumerate()
    {
        let at = 120 + 32 * ordinal;
        put16(&mut expanded, at, (ordinal + 1) as u16);
        expanded[at + 2] = op;
        expanded[at + 3] = kind;
        put32(&mut expanded, at + 4, width);
        put16(&mut expanded, at + 8, args.len() as u16);
        for (index, argument) in args.into_iter().enumerate() {
            put16(&mut expanded, at + 10 + 2 * index, argument);
        }
        put16(&mut expanded, at + 18, auxiliary);
        put64(&mut expanded, at + 24, immediate);
    }
    let encoded = encode_recipe_package_v2(&expanded, 8).unwrap();
    assert_eq!(
        evaluate_serialized_recipe_v2(&encoded, 8, 1, &[]).unwrap(),
        [0, 11]
    );
}
