use gb_bootstrap::candidate::encode_eh_unit;
use gb_bootstrap::recipe::RecipeValue;
use gb_bootstrap::recipe_wire_v2::{
    decode_recipe_package_v2, encode_recipe_package_v2, evaluate_serialized_recipe_v2,
    expand_recipe_package_v2,
};
use gb_bootstrap::recovery_recipe_v2::{
    admit_recovery_programs, build_recovery_recipe_package,
    build_recovery_recipe_package_from_source, evaluate_recovery_native,
    evaluate_serialized_recovery_native, recovery_program_refined,
};
use gb_bootstrap::{CommonBlock, encode_common_block};
use std::sync::OnceLock;

fn package() -> &'static gb_bootstrap::recipe_wire_v1::RecipePackageV1 {
    static PACKAGE: OnceLock<gb_bootstrap::recipe_wire_v1::RecipePackageV1> = OnceLock::new();
    PACKAGE.get_or_init(|| {
        decode_recipe_package_v2(&build_recovery_recipe_package().unwrap(), 8).unwrap()
    })
}

#[test]
fn source_closures_and_mapping_match_generic_execution() {
    let raw = build_recovery_recipe_package().unwrap();
    let package = decode_recipe_package_v2(&raw, 8).unwrap();
    for id in [119, 120, 122, 123, 124, 126, 127] {
        assert!(recovery_program_refined(&package, id));
    }
    for (side, width, unit, bit) in [
        (2048u16, 112u16, 1u32, 0u16),
        (2048, 128, 100, 1727),
        (512, 32, 90, 72),
        (0, 0, 1, 0),
        (64, 8, 1, 0),
        (u16::MAX, u16::MAX, 1, u16::MAX),
        (2048, 112, u32::MAX, 0),
        (2048, 112, 1, 1728),
    ] {
        let input = [
            side.to_be_bytes().as_slice(),
            width.to_be_bytes().as_slice(),
            unit.to_be_bytes().as_slice(),
            bit.to_be_bytes().as_slice(),
        ]
        .concat();
        assert_eq!(
            evaluate_serialized_recovery_native(&package, 124, &input).unwrap(),
            evaluate_serialized_recipe_v2(&raw, 8, 124, &input).unwrap()
        );
    }
}

fn common(byte: u8, copy: u16, version: u16) -> [u8; 191] {
    encode_common_block(&CommonBlock {
        profile_version: 8,
        section_id: 400,
        semantic_copy_id: copy,
        section_type: 3,
        section_version: version,
        fragment_index: 0,
        fragment_count: 1,
        section_envelope_length: 24,
        payload: vec![byte; 24],
    })
    .unwrap()
}
fn key(block: &[u8; 191]) -> Vec<u8> {
    [&block[..2], &block[4..14], &block[16..20], &block[22..26]].concat()
}
fn pair(block: &[u8; 191], flips: &[usize], unknown: &[usize]) -> Vec<u8> {
    let mut result = encode_eh_unit(block).to_vec();
    result.resize(432, 0);
    for bit in flips {
        result[bit / 8] ^= 128 >> (bit % 8);
    }
    for bit in unknown {
        let flag = 128 >> (bit % 8);
        result[bit / 8] &= !flag;
        result[216 + bit / 8] |= flag;
    }
    result
}
fn group_input(factor: u8, lanes: &[Option<Vec<u8>>], expected: &[u8]) -> Vec<u8> {
    let presence = lanes.iter().enumerate().fold(0u8, |mask, (i, lane)| {
        mask | if lane.is_some() { 1 << i } else { 0 }
    });
    let mut result = vec![factor, presence];
    result.extend(expected);
    for i in 0..5 {
        result.extend(
            lanes
                .get(i)
                .and_then(Option::as_ref)
                .cloned()
                .unwrap_or_else(|| vec![0; 432]),
        );
    }
    result
}
fn group_result(state: u8, accepted: bool, block: &[u8; 191]) -> Vec<u8> {
    let mut result = vec![0, 0, state, u8::from(accepted)];
    result.extend(block);
    result
}

#[test]
fn original_lanes_repetition_identity_and_canonicality_have_exact_outputs() {
    let p = package();
    let a = common(b'A', 0, 0);
    let b = common(b'B', 0, 0);
    let foreign = common(b'A', 1, 9);
    let cases = [
        (
            group_input(5, &[None, None, None, None, None], &key(&a)),
            group_result(0, false, &[0; 191]),
        ),
        (
            group_input(1, &[Some(pair(&a, &[0], &[]))], &key(&a)),
            group_result(3, true, &a),
        ),
        (
            group_input(1, &[Some(pair(&a, &[], &[0, 1, 2]))], &key(&a)),
            group_result(3, true, &a),
        ),
        (
            group_input(1, &[Some(pair(&a, &[], &[0, 1, 2, 3]))], &key(&a)),
            group_result(1, false, &[0; 191]),
        ),
        (
            group_input(
                5,
                &(0..5)
                    .map(|i| Some(pair(&b, &[2 * i, 2 * i + 1], &[])))
                    .collect::<Vec<_>>(),
                &key(&b),
            ),
            group_result(3, true, &b),
        ),
        (
            group_input(
                5,
                &[
                    Some(pair(&a, &[], &[])),
                    Some(pair(&b, &[], &[])),
                    None,
                    None,
                    None,
                ],
                &key(&a),
            ),
            group_result(4, false, &[0; 191]),
        ),
        (
            group_input(2, &[Some(pair(&a, &[], &[])), None], &key(&a)),
            group_result(2, true, &a),
        ),
        (
            group_input(1, &[Some(pair(&foreign, &[], &[]))], &key(&a)),
            group_result(2, false, &foreign),
        ),
    ];
    for (input, expected) in cases {
        assert_eq!(
            evaluate_serialized_recovery_native(p, 120, &input).unwrap(),
            expected
        );
    }
    let valid = group_input(1, &[Some(pair(&a, &[], &[]))], &key(&a));
    for (at, bad) in [(0, 3), (1, 128), (1, 0), (22 + 432, 1)] {
        let mut input = valid.clone();
        input[at] = bad;
        assert_eq!(
            evaluate_serialized_recovery_native(p, 120, &input).unwrap(),
            [0, 3]
        );
    }
    let mut hidden = group_input(1, &[Some(pair(&a, &[], &[0]))], &key(&a));
    hidden[22] |= 128;
    assert_eq!(
        evaluate_serialized_recovery_native(p, 120, &hidden).unwrap(),
        [0, 3]
    );
    let mut state = group_input(1, &[Some(pair(&foreign, &[], &[]))], &key(&a));
    state.resize(4096, 255);
    state.extend([255; 8]);
    let mut expected = vec![0; 4098];
    expected[2808..2999].copy_from_slice(&foreign);
    expected[3012] = 2;
    assert_eq!(
        evaluate_serialized_recovery_native(p, 119, &state).unwrap(),
        expected
    );
}

#[test]
fn complete_group_generic_matches_native_when_valid_lane_conflicts_with_raw_rep() {
    let p = package();
    let a = common(b'A', 0, 0);
    let b = common(b'B', 0, 0);
    let mut lanes = vec![Some(pair(&a, &[], &[]))];
    lanes.extend((1..5).map(|i| Some(pair(&b, &[2 * i, 2 * i + 1], &[]))));
    let input = group_input(5, &lanes, &key(&a));
    let native = evaluate_serialized_recovery_native(p, 120, &input).unwrap();
    assert_eq!(native, group_result(4, false, &[0; 191]));
    assert_eq!(
        evaluate_serialized_recipe_v2(&p.encoded, 8, 120, &input).unwrap(),
        native
    );
}

fn inventory() -> Vec<u8> {
    let mut raw = vec![0, 2, 0, 3, 0, 0, 0, 64];
    for (id, kind, factor, length) in [(1u32, 1u16, 5u8, 68u32), (2, 2, 2, 157), (3, 3, 1, 1)] {
        raw.extend(id.to_be_bytes());
        raw.extend(kind.to_be_bytes());
        raw.extend([0, 2, 0, 1, 1, 2 * factor, 0, 0]);
        raw.extend(length.to_be_bytes());
        raw.extend([0, 0]);
    }
    raw
}
#[test]
fn roster_whole_state_and_invalid_late_entry_match_generic() {
    let p = package();
    let raw = inventory();
    let mut state = raw.clone();
    state.resize(16384, 0);
    state.extend([0xff; 47]);
    state[16384..16386].copy_from_slice(&(raw.len() as u16).to_be_bytes());
    state[16396..16400].copy_from_slice(&9u32.to_be_bytes());
    let mut input = state;
    input.extend([255; 8]);
    let native = evaluate_serialized_recovery_native(p, 122, &input).unwrap();
    assert_eq!(
        evaluate_serialized_recipe_v2(&p.encoded, 8, 122, &input).unwrap(),
        native
    );
    assert_eq!(&native[2..16386], &input[..16384]);
    for (at, bad) in [(0, 1u8), (28, 0), (42, 255)] {
        let mut input = raw.clone();
        input[at] = bad;
        input.resize(16384, 0);
        input.extend((raw.len() as u16).to_be_bytes());
        input.extend(1u32.to_be_bytes());
        if at == 28 {
            input[28..32].fill(0);
        }
        assert_eq!(
            evaluate_serialized_recovery_native(p, 123, &input).unwrap(),
            [0, 3]
        );
        assert_eq!(
            evaluate_serialized_recipe_v2(&p.encoded, 8, 123, &input).unwrap(),
            [0, 3]
        );
    }
    for target in [0u32, 1, 5, 6, 9, 10, 11, u32::MAX] {
        let mut input = raw.clone();
        input.resize(16384, 0);
        input.extend((raw.len() as u16).to_be_bytes());
        input.extend(target.to_be_bytes());
        assert_eq!(
            evaluate_serialized_recovery_native(p, 123, &input).unwrap(),
            evaluate_serialized_recipe_v2(&p.encoded, 8, 123, &input).unwrap()
        );
    }
}

#[test]
fn first_inventory_anchor_has_exact_bounds_and_zeroes_rejected_blocks() {
    let p = package();
    let block = encode_common_block(&CommonBlock {
        profile_version: 8,
        section_id: 1,
        semantic_copy_id: 0,
        section_type: 1,
        section_version: 2,
        fragment_index: 0,
        fragment_count: 1,
        section_envelope_length: 90,
        payload: vec![0; 90],
    })
    .unwrap();
    for (limit, chosen, accepted, status) in [
        (5u32, block, true, 0u8),
        (4, block, false, 3),
        (2390, block, false, 3),
        (1908, common(b'A', 0, 0), false, 0),
    ] {
        let mut input = limit.to_be_bytes().to_vec();
        input.push(1);
        input.extend(pair(&chosen, &[], &[]));
        input.resize(2165, 0);
        let actual = evaluate_serialized_recovery_native(p, 127, &input).unwrap();
        if status != 0 {
            assert_eq!(actual, [0, status]);
        } else {
            assert_eq!(
                actual,
                group_result(2, accepted, if accepted { &chosen } else { &[0; 191] })
            );
        }
    }
    let mut input = 1908u32.to_be_bytes().to_vec();
    input.resize(2165, 0);
    assert_eq!(
        evaluate_serialized_recipe_v2(&p.encoded, 8, 127, &input).unwrap(),
        evaluate_serialized_recovery_native(p, 127, &input).unwrap()
    );
}

#[test]
fn construction_wrapper_and_typed_input_errors_are_preserved() {
    let p = package();
    for case in 0..8 {
        let input = [0, 0, 0, 6, case];
        let result = evaluate_serialized_recovery_native(p, 126, &input).unwrap();
        assert_eq!(&result[..2], &[0, 0]);
        assert_eq!(result.len(), 52);
    }
    for input in [[0, 0, 0, 0, 4], [0, 0, 0, 6, 8], [255, 255, 255, 255, 0]] {
        assert_eq!(
            evaluate_serialized_recovery_native(p, 126, &input).unwrap(),
            [0, 3]
        );
    }
    assert!(evaluate_serialized_recovery_native(p, 120, &[]).is_err());
    assert!(evaluate_serialized_recovery_native(p, 124, &[0; 9]).is_err());
    assert!(
        evaluate_recovery_native(
            p,
            124,
            &[RecipeValue::Uint {
                width: 32,
                value: 2048
            }]
        )
        .is_err()
    );
    let values = [
        RecipeValue::Uint {
            width: 16,
            value: 2048,
        },
        RecipeValue::Uint {
            width: 16,
            value: 112,
        },
        RecipeValue::Uint {
            width: 32,
            value: 1,
        },
        RecipeValue::Uint {
            width: 16,
            value: 0,
        },
    ];
    assert_eq!(evaluate_recovery_native(p, 124, &values).unwrap().status, 0);
}

#[test]
fn carried_construction_positive_and_negative_cases_match_generic_execution() {
    let p = package();
    for case in [4, 6, 7] {
        let input = [0, 0, 0, 6, case];
        let native = evaluate_serialized_recovery_native(p, 126, &input).unwrap();
        assert_eq!(
            evaluate_serialized_recipe_v2(&p.encoded, 8, 126, &input).unwrap(),
            native,
            "case {case}"
        );
    }
}

fn recipe_offset(raw: &[u8], id: u16) -> usize {
    let read16 = |at| u16::from_be_bytes(raw[at..at + 2].try_into().unwrap());
    let read32 = |at| u32::from_be_bytes(raw[at..at + 4].try_into().unwrap()) as usize;
    let mut cursor = 64;
    for _ in 0..read16(18) {
        cursor += 16 + read32(cursor + 12);
    }
    for _ in 0..read16(16) {
        if read16(cursor) == id {
            return cursor;
        }
        cursor += read32(cursor + 28);
    }
    panic!("missing recipe {id}")
}
#[test]
fn closure_rejects_transitive_source_mutations_and_keeps_unrelated_programs_independent() {
    let p = package();
    let original = expand_recipe_package_v2(&p.encoded, 8).unwrap();
    for id in [1, 3, 4, 90, 92, 114, 115, 116, 117, 118, 119, 120, 203] {
        let mut raw = original.clone();
        let at = recipe_offset(&raw, id);
        let inputs = u16::from_be_bytes(raw[at + 4..at + 6].try_into().unwrap()) as usize;
        let outputs = u16::from_be_bytes(raw[at + 6..at + 8].try_into().unwrap()) as usize;
        let count = u32::from_be_bytes(raw[at + 8..at + 12].try_into().unwrap()) as usize;
        let first = at + 32 + 12 * (inputs + outputs);
        let node = (0..count)
            .map(|i| first + 32 * i)
            .find(|n| raw[*n + 2] == 1 && raw[*n + 3] == 0)
            .unwrap();
        raw[node + 31] ^= 1;
        let encoded = encode_recipe_package_v2(&raw, 8).unwrap();
        let changed = decode_recipe_package_v2(&encoded, 8).unwrap();
        assert_eq!(
            recovery_program_refined(&changed, 120),
            id == 203,
            "recipe {id}"
        );
        if id != 203 {
            assert!(evaluate_serialized_recovery_native(&changed, 120, &[]).is_err());
        }
    }
    for at in [36usize, 44] {
        let mut changed = p.clone();
        changed.encoded[at] ^= 1;
        assert!(!recovery_program_refined(&changed, 120));
    }
}

#[test]
fn source_loader_rejects_unowned_shapes_lengths_and_table_changes() {
    let source =
        std::str::from_utf8(include_bytes!("../../../spec/recovery-program-v2.toml")).unwrap();
    for changed in [
        source.replacen("version = 1", "version = true", 1),
        source.replacen("id = 114", "id = 113", 1),
        source.replacen("d3916ac47208be5f", "d3916ac47208be5e", 1),
        format!("{source}\n[unowned]\nvalue=1\n"),
        " ".repeat(262145),
    ] {
        assert!(build_recovery_recipe_package_from_source(changed.as_bytes()).is_err());
    }
}

#[test]
fn every_transitive_table_is_compared_before_native_execution() {
    let p = package();
    let original = expand_recipe_package_v2(&p.encoded, 8).unwrap();
    for (table_id, root) in [
        (3u16, 120),
        (4, 120),
        (5, 120),
        (10, 120),
        (11, 120),
        (12, 120),
        (13, 120),
        (14, 120),
        (15, 120),
        (18, 120),
        (23, 120),
        (17, 124),
        (24, 126),
        (25, 126),
        (26, 126),
        (27, 126),
    ] {
        let mut cursor = 64;
        let count = u16::from_be_bytes(original[18..20].try_into().unwrap());
        let mut payload = None;
        for _ in 0..count {
            let id = u16::from_be_bytes(original[cursor..cursor + 2].try_into().unwrap());
            if id == table_id {
                payload = Some(cursor + 16);
                break;
            }
            cursor += 16
                + u32::from_be_bytes(original[cursor + 12..cursor + 16].try_into().unwrap())
                    as usize;
        }
        let at = payload.unwrap();
        let mut admitted = None;
        for bit in 0..8 {
            let mut raw = original.clone();
            raw[at] ^= 1 << bit;
            if let Ok(encoded) = encode_recipe_package_v2(&raw, 8) {
                admitted = Some(encoded);
                break;
            }
        }
        let changed =
            decode_recipe_package_v2(&admitted.expect("valid typed table mutation"), 8).unwrap();
        assert!(
            !recovery_program_refined(&changed, root),
            "table {table_id}, root {root}"
        );
    }
}

#[test]
fn scoped_admission_reuses_only_explicit_immutable_source_closures() {
    let p = package();
    let admitted = admit_recovery_programs(p, &[120, 123, 127]).unwrap();
    let a = common(b'A', 0, 0);
    let input = group_input(1, &[Some(pair(&a, &[], &[]))], &key(&a));
    for _ in 0..3 {
        assert_eq!(
            admitted.evaluate_serialized(120, &input).unwrap(),
            group_result(2, true, &a)
        );
    }
    assert!(admitted.evaluate_serialized(124, &[0; 10]).is_err());
    assert!(admit_recovery_programs(p, &[]).is_err());
    assert!(admit_recovery_programs(p, &[120, 120]).is_err());
    assert!(admit_recovery_programs(p, &[118]).is_err());
    let expanded = expand_recipe_package_v2(&p.encoded, 8).unwrap();
    let historical = gb_bootstrap::recipe_wire_v1::encode_recipe_package_v1(&expanded, 8).unwrap();
    let historical =
        gb_bootstrap::recipe_wire_v1::decode_recipe_package_v1(&historical, 8).unwrap();
    assert!(admit_recovery_programs(&historical, &[120]).is_err());
    let mut changed = p.clone();
    {
        let handle = admit_recovery_programs(&changed, &[120]).unwrap();
        assert_eq!(handle.evaluate_serialized(120, &input).unwrap()[2], 2);
    }
    changed.encoded[48] = 1;
    assert!(admit_recovery_programs(&changed, &[120]).is_err());
}
