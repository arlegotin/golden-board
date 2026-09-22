use std::collections::BTreeMap;

use gb_bootstrap::body_recipe_v1::build_revision_recipe_package;
use gb_bootstrap::recipe::{RecipeValue, decode_recipe_package};
use gb_bootstrap::recipe_wire_v1::{
    decode_recipe_package_v1, evaluate_recipe_v1, evaluate_serialized_recipe_v1,
    expand_recipe_package_v1,
};
use gb_bootstrap::teaching_recipe_v2::{
    build_teaching_recipe_package, build_teaching_recipe_package_from_source,
};

const SOURCE: &[u8] = include_bytes!("../../../spec/recipe-teaching-v2.toml");

fn hex(value: &str) -> Vec<u8> {
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
}

fn u16_at(raw: &[u8], offset: usize) -> usize {
    u16::from_be_bytes(raw[offset..offset + 2].try_into().unwrap()) as usize
}

fn u32_at(raw: &[u8], offset: usize) -> usize {
    u32::from_be_bytes(raw[offset..offset + 4].try_into().unwrap()) as usize
}

fn records(raw: &[u8]) -> (BTreeMap<u16, &[u8]>, BTreeMap<u16, &[u8]>) {
    let mut cursor = 64;
    let mut tables = BTreeMap::new();
    for _ in 0..u16_at(raw, 18) {
        let end = cursor + 16 + u32_at(raw, cursor + 12);
        tables.insert(u16_at(raw, cursor) as u16, &raw[cursor..end]);
        cursor = end;
    }
    let mut recipes = BTreeMap::new();
    for _ in 0..u16_at(raw, 16) {
        let end = cursor + u32_at(raw, cursor + 28);
        recipes.insert(u16_at(raw, cursor) as u16, &raw[cursor..end]);
        cursor = end;
    }
    assert_eq!(cursor, raw.len());
    (tables, recipes)
}

#[test]
fn all_owner_examples_evaluate_with_exact_serialized_status_and_data() {
    let raw = build_teaching_recipe_package().unwrap();
    assert_eq!(
        raw,
        build_teaching_recipe_package_from_source(SOURCE).unwrap()
    );
    let package = decode_recipe_package_v1(&raw, 8).unwrap();
    let source: toml::Value = toml::from_str(std::str::from_utf8(SOURCE).unwrap()).unwrap();
    let examples = source["examples"].as_array().unwrap();
    assert_eq!(examples.len(), 8);
    for row in examples {
        let input: Vec<u8> = row["inputs"]
            .as_array()
            .unwrap()
            .iter()
            .flat_map(|value| hex(value.as_str().unwrap()))
            .collect();
        let actual = evaluate_serialized_recipe_v1(
            &package,
            row["recipe"].as_integer().unwrap() as u16,
            &input,
        )
        .unwrap();
        assert_eq!(actual, hex(row["output"].as_str().unwrap()));
    }
}

#[test]
fn additions_preserve_inherited_programs_except_removed106_and_replaced110() {
    let previous = expand_recipe_package_v1(&build_revision_recipe_package().unwrap(), 8).unwrap();
    let compact = build_teaching_recipe_package().unwrap();
    use sha2::{Digest, Sha256};
    println!(
        "active teaching package {} bytes sha256 {:x}",
        compact.len(),
        Sha256::digest(&compact)
    );
    assert!(decode_recipe_package(&compact, 8).is_err());
    assert!(decode_recipe_package_v1(&compact, 7).is_err());
    let expanded = expand_recipe_package_v1(&compact, 8).unwrap();
    let (old_tables, old_recipes) = records(&previous);
    let (new_tables, new_recipes) = records(&expanded);
    assert_eq!(new_tables.len(), old_tables.len() + 1);
    // Active recipe-teaching-v2 now owns an exact29-recipe set. The
    // historical/base package retains its original106 and110 bytes.
    assert_eq!(
        new_recipes.keys().copied().collect::<Vec<_>>(),
        vec![
            1, 2, 3, 4, 30, 90, 92, 99, 100, 101, 102, 103, 104, 105, 107, 108, 109, 110, 111, 112,
            113, 201, 202, 203, 210, 211, 212, 213, 214,
        ]
    );
    assert_eq!(old_recipes[&106].len(), 228);
    assert_ne!(new_recipes[&110], old_recipes[&110]);
    for (id, record) in old_tables {
        assert_eq!(new_tables[&id], record);
    }
    let expected_retained: BTreeMap<_, _> = old_recipes
        .into_iter()
        .filter(|(id, _)| ![106, 110].contains(id))
        .collect();
    let actual_retained: BTreeMap<_, _> = new_recipes
        .iter()
        .filter(|(id, _)| **id < 210 && **id != 110)
        .map(|(id, raw)| (*id, *raw))
        .collect();
    assert_eq!(actual_retained, expected_retained);
    assert_eq!(&new_tables[&21][16..], &[7, 8, 9]);
    assert_eq!(&new_tables[&5][16..], &(0..=255u8).collect::<Vec<_>>());
    let logical = decode_recipe_package_v1(&compact, 8).unwrap().logical;
    assert_eq!(logical.recipe_primitive_steps(213), Some(6));
    assert_eq!(logical.recipe_primitive_steps(214), Some(22));
    let mut altered = compact.clone();
    altered.fill(0);
    assert_eq!(build_teaching_recipe_package().unwrap(), compact);
}

#[test]
fn failures_suppress_prior_output_and_iteration_uses_each_index() {
    let raw = build_teaching_recipe_package().unwrap();
    let package = decode_recipe_package_v1(&raw, 8).unwrap();
    let failed = evaluate_recipe_v1(&package, 212, &[]).unwrap();
    assert_eq!(failed.status, 4);
    assert!(failed.outputs.is_empty());
    for (input, expected) in [
        (0u8, &[0, 0, 3][..]),
        (7, &[0, 0, 10][..]),
        (254, &[0, 11][..]),
    ] {
        assert_eq!(
            evaluate_serialized_recipe_v1(&package, 214, &[input]).unwrap(),
            expected
        );
    }
    let out = evaluate_recipe_v1(
        &package,
        213,
        &[
            RecipeValue::Uint { width: 8, value: 7 },
            RecipeValue::Uint {
                width: 64,
                value: 2,
            },
        ],
    )
    .unwrap();
    assert_eq!(out.outputs, vec![RecipeValue::Uint { width: 8, value: 9 }]);
    let bad_index = evaluate_recipe_v1(
        &package,
        213,
        &[
            RecipeValue::Uint { width: 8, value: 0 },
            RecipeValue::Uint {
                width: 64,
                value: 256,
            },
        ],
    )
    .unwrap();
    assert_eq!(bad_index.status, 11);
    assert!(bad_index.outputs.is_empty());
    for input in [
        vec![6, 0, 0xb6, b'a', b'b', b'c', 1],
        vec![128, 1, 0xb6, b'a', b'b', b'c', 1],
        vec![255, 1, 0xb6, b'a', b'b', b'c', 1],
    ] {
        assert_eq!(
            evaluate_serialized_recipe_v1(&package, 211, &input).unwrap(),
            [0, 11]
        );
    }
}

#[test]
fn bounded_source_rejects_shape_reference_type_and_example_mutations_atomically() {
    assert!(build_teaching_recipe_package_from_source(&vec![b' '; 65_537]).is_err());
    assert!(build_teaching_recipe_package_from_source(&[0xff]).is_err());
    let original: toml::Value = toml::from_str(std::str::from_utf8(SOURCE).unwrap()).unwrap();
    for mutation in 0..17 {
        let mut value = original.clone();
        match mutation {
            0 => {
                value
                    .as_table_mut()
                    .unwrap()
                    .insert("extra".into(), 1.into());
            }
            1 => value["version"] = 2.into(),
            2 => value["version"] = true.into(),
            3 => value["tables"][0]["payload"] = "07080900".into(),
            4 => value["tables"][0]["type"] = 3.into(),
            5 => value["recipes"][0]["id"] = 211.into(),
            6 => {
                value["recipes"][1]["nodes"][0]
                    .as_array_mut()
                    .unwrap()
                    .push(0.into());
            }
            7 => value["recipes"][1]["nodes"][0][0] = 26.into(),
            8 => value["recipes"][1]["nodes"][0][3] = 1.into(),
            9 => value["recipes"][1]["nodes"][0][4] = 1.into(),
            10 => value["recipes"][1]["nodes"][1][4] = 65535.into(),
            11 => value["recipes"][5]["nodes"][0][7] = 214.into(),
            12 => value["recipes"][5]["nodes"][0][8] = i64::MAX.into(),
            13 => value["recipes"][0]["inputs"][0][1] = 0.into(),
            14 => value["examples"][0]["output"] = "0001".into(),
            15 => value["examples"][0]["inputs"][0] = "0600".into(),
            _ => {
                value["examples"].as_array_mut().unwrap().pop();
            }
        }
        let changed = toml::to_string(&value).unwrap();
        assert!(
            build_teaching_recipe_package_from_source(changed.as_bytes()).is_err(),
            "mutation {mutation}"
        );
    }
}

#[test]
fn group_decision_keeps_all_six_sources_and_separates_identity_from_local_state() {
    let package = decode_recipe_package_v1(&build_teaching_recipe_package().unwrap(), 8).unwrap();
    for (input, output) in [
        ([0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0]),
        ([0, 0, 0, 0, 0, 0, 1, 0, 0], [0, 0, 0, 1, 0]),
        ([1, 0, 0, 0, 0, 2, 1, 1, 1], [0, 0, 3, 4, 0]),
        ([0, 0, 0, 0, 0, 2, 1, 0, 1], [0, 0, 2, 3, 1]),
        ([1, 1, 1, 1, 1, 1, 1, 1, 1], [0, 0, 1, 2, 1]),
        ([1, 0, 0, 0, 0, 0, 1, 1, 0], [0, 0, 1, 2, 0]),
    ] {
        assert_eq!(
            evaluate_serialized_recipe_v1(&package, 110, &input).unwrap(),
            output
        );
    }
    for slot in 0..6 {
        for mask in 1..=3 {
            let mut input = [0; 9];
            input[slot] = mask;
            input[6] = 1;
            input[8] = 1;
            let output = if mask == 3 {
                [0, 0, 3, 4, 0]
            } else {
                [0, 0, mask, 3, 1]
            };
            assert_eq!(
                evaluate_serialized_recipe_v1(&package, 110, &input).unwrap(),
                output
            );
        }
    }
}
