use std::collections::BTreeMap;

use gb_bootstrap::RejectCode;
use gb_bootstrap::recipe::{RecipeValue, decode_recipe_package, evaluate_recipe};
use gb_foundation::{ManifestValue, validate_canonical_manifest};

fn object(value: &ManifestValue) -> &BTreeMap<String, ManifestValue> {
    let ManifestValue::Object(value) = value else {
        panic!("object")
    };
    value
}

fn array(value: &ManifestValue) -> &[ManifestValue] {
    let ManifestValue::Array(value) = value else {
        panic!("array")
    };
    value
}

fn text(value: &ManifestValue) -> &str {
    let ManifestValue::String(value) = value else {
        panic!("string")
    };
    value
}

fn unsigned(value: &ManifestValue) -> u64 {
    let ManifestValue::U64(value) = value else {
        panic!("u64")
    };
    *value
}

fn hex(value: &str) -> Vec<u8> {
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let digit = |value| match value {
                b'0'..=b'9' => value - b'0',
                b'a'..=b'f' => value - b'a' + 10,
                _ => panic!("lowercase hex"),
            };
            digit(pair[0]) << 4 | digit(pair[1])
        })
        .collect()
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

fn descriptor(target: &mut [u8], offset: usize, id: u16, kind: u8, width: u32) {
    put_u16(target, offset, id);
    target[offset + 2] = kind;
    put_u32(target, offset + 4, width);
    put_u32(target, offset + 8, 1);
}

#[allow(clippy::too_many_arguments)]
fn node(
    target: &mut [u8],
    offset: usize,
    id: u16,
    opcode: u8,
    kind: u8,
    width: u32,
    arguments: &[u16],
    auxiliary: u16,
    immediate: u64,
) {
    put_u16(target, offset, id);
    target[offset + 2] = opcode;
    target[offset + 3] = kind;
    put_u32(target, offset + 4, width);
    put_u16(target, offset + 8, arguments.len() as u16);
    for (index, argument) in arguments.iter().copied().enumerate() {
        put_u16(target, offset + 10 + index * 2, argument);
    }
    put_u16(target, offset + 18, auxiliary);
    put_u64(target, offset + 24, immediate);
}

fn package() -> Vec<u8> {
    let recipe_bytes = 32 + 2 * 12 + 4 * 32;
    let mut raw = vec![0_u8; 64 + recipe_bytes];
    let package_bytes = raw.len() as u32;
    raw[..8].copy_from_slice(b"GBRECP0\0");
    put_u16(&mut raw, 12, 1);
    put_u16(&mut raw, 16, 1);
    put_u32(&mut raw, 20, 4);
    put_u32(&mut raw, 24, 2);
    put_u32(&mut raw, 32, package_bytes);
    put_u64(&mut raw, 36, 4);
    put_u32(&mut raw, 44, 4);

    let recipe = 64;
    put_u16(&mut raw, recipe, 1);
    put_u16(&mut raw, recipe + 6, 2);
    put_u32(&mut raw, recipe + 8, 4);
    put_u32(&mut raw, recipe + 12, 2);
    put_u64(&mut raw, recipe + 16, 4);
    put_u32(&mut raw, recipe + 24, 4);
    put_u32(&mut raw, recipe + 28, recipe_bytes as u32);
    descriptor(&mut raw, recipe + 32, 1, 5, 16);
    descriptor(&mut raw, recipe + 44, 2, 0, 8);
    let nodes = recipe + 56;
    node(&mut raw, nodes, 1, 1, 5, 16, &[], 0, 0);
    node(&mut raw, nodes + 32, 2, 5, 5, 16, &[1], 1, 0);
    node(&mut raw, nodes + 64, 3, 1, 0, 8, &[], 0, 42);
    node(&mut raw, nodes + 96, 4, 5, 5, 16, &[3], 2, 0);
    raw
}

fn duplicate_argument_package() -> Vec<u8> {
    let recipe_bytes = 32 + 2 * 12 + 5 * 32;
    let mut raw = vec![0_u8; 64 + recipe_bytes];
    let package_bytes = raw.len() as u32;
    raw[..8].copy_from_slice(b"GBRECP0\0");
    put_u16(&mut raw, 12, 1);
    put_u16(&mut raw, 16, 1);
    put_u32(&mut raw, 20, 5);
    put_u32(&mut raw, 24, 4);
    put_u32(&mut raw, 32, package_bytes);
    put_u64(&mut raw, 36, 5);
    put_u32(&mut raw, 44, 5);

    let recipe = 64;
    put_u16(&mut raw, recipe, 1);
    put_u16(&mut raw, recipe + 6, 2);
    put_u32(&mut raw, recipe + 8, 5);
    put_u32(&mut raw, recipe + 12, 4);
    put_u64(&mut raw, recipe + 16, 5);
    put_u32(&mut raw, recipe + 24, 5);
    put_u32(&mut raw, recipe + 28, recipe_bytes as u32);
    descriptor(&mut raw, recipe + 32, 1, 5, 16);
    descriptor(&mut raw, recipe + 44, 2, 0, 8);
    let nodes = recipe + 56;
    node(&mut raw, nodes, 1, 1, 0, 8, &[], 0, 0xaa);
    node(&mut raw, nodes + 32, 2, 13, 0, 8, &[1, 1], 0, 0);
    node(&mut raw, nodes + 64, 3, 24, 5, 16, &[], 0, 0);
    node(&mut raw, nodes + 96, 4, 5, 5, 16, &[3], 1, 0);
    node(&mut raw, nodes + 128, 5, 5, 5, 16, &[2], 2, 0);
    raw
}

#[test]
fn exact_bounded_package_executes_atomically() {
    let raw = package();
    let package = decode_recipe_package(&raw, 1).unwrap();
    assert_eq!(package.recipe_ids().collect::<Vec<_>>(), [1]);
    assert_eq!(package.maximum_primitive_steps, 4);
    assert_eq!(package.peak_scratch_bytes, 4);
    assert_eq!(
        evaluate_recipe(&package, 1, &[]).unwrap(),
        gb_bootstrap::recipe::RecipeOutcome {
            status: 0,
            outputs: vec![RecipeValue::Uint {
                width: 8,
                value: 42
            }],
        }
    );
}

#[test]
fn duplicate_argument_releases_one_live_value_once() {
    let package = decode_recipe_package(&duplicate_argument_package(), 1).unwrap();
    assert_eq!(package.peak_scratch_bytes, 5);
    assert_eq!(
        evaluate_recipe(&package, 1, &[]).unwrap(),
        gb_bootstrap::recipe::RecipeOutcome {
            status: 0,
            outputs: vec![RecipeValue::Uint { width: 8, value: 0 }],
        }
    );
}

#[test]
fn static_shape_resource_and_trailing_mutations_fail_before_evaluation() {
    for mutation in ["opcode", "scratch", "edge", "trailing"] {
        let mut raw = package();
        match mutation {
            "opcode" => raw[64 + 56 + 2] = 26,
            "scratch" => put_u32(&mut raw, 44, 5),
            "edge" => put_u32(&mut raw, 24, 3),
            "trailing" => {
                raw.push(0);
                let length = raw.len() as u32;
                put_u32(&mut raw, 32, length);
            }
            _ => unreachable!(),
        }
        let error = decode_recipe_package(&raw, 1).unwrap_err();
        assert_eq!(error.code, RejectCode::Recipe, "{mutation}");
    }
}

#[test]
fn shared_kitchen_sink_bytes_cover_all_opcodes_and_match_outputs() {
    let manifest =
        validate_canonical_manifest(include_bytes!("../../../conformance/recipe-v0.json")).unwrap();
    let fields = object(&manifest);
    assert_eq!(
        fields.keys().map(String::as_str).collect::<Vec<_>>(),
        [
            "expected_outputs_hex",
            "inputs_hex",
            "package_hex",
            "profile_version",
            "recipe_id",
            "schema",
            "status",
        ]
    );
    assert_eq!(
        text(&fields["schema"]),
        "golden-board.recipe-v0-fixtures/v0"
    );
    let raw = hex(text(&fields["package_hex"]));
    let profile = u16::try_from(unsigned(&fields["profile_version"])).unwrap();
    let package = decode_recipe_package(&raw, profile).unwrap();
    assert_eq!(
        package
            .opcode_ids()
            .collect::<std::collections::BTreeSet<_>>(),
        (1_u8..=25).collect()
    );
    let inputs = [
        RecipeValue::Uint { width: 8, value: 6 },
        RecipeValue::Uint { width: 8, value: 2 },
        RecipeValue::Bits {
            width: 8,
            packed: vec![0xb6],
        },
        RecipeValue::Bytes(b"abc".to_vec()),
        RecipeValue::Bool(true),
    ];
    assert_eq!(
        array(&fields["inputs_hex"])
            .iter()
            .map(|value| text(value))
            .collect::<Vec<_>>(),
        ["06", "02", "b6", "616263", "01"]
    );
    let recipe_id = u16::try_from(unsigned(&fields["recipe_id"])).unwrap();
    let outcome = evaluate_recipe(&package, recipe_id, &inputs).unwrap();
    assert_eq!(outcome.status, unsigned(&fields["status"]) as u16);
    let observed = outcome
        .outputs
        .iter()
        .map(|value| match value {
            RecipeValue::Uint { width, value } => {
                value.to_be_bytes()[8 - (*width as usize).div_ceil(8)..].to_vec()
            }
            RecipeValue::Bool(value) => vec![u8::from(*value)],
            RecipeValue::Bits { packed, .. } | RecipeValue::Bytes(packed) => packed.clone(),
            RecipeValue::Status(value) => value.to_be_bytes().to_vec(),
            RecipeValue::Table { .. } => panic!("table output forbidden"),
        })
        .collect::<Vec<_>>();
    let expected = array(&fields["expected_outputs_hex"])
        .iter()
        .map(|value| hex(text(value)))
        .collect::<Vec<_>>();
    assert_eq!(observed, expected);

    let runtime_limit_inputs = [
        RecipeValue::Uint { width: 8, value: 6 },
        RecipeValue::Uint { width: 8, value: 0 },
        RecipeValue::Bits {
            width: 8,
            packed: vec![0xb6],
        },
        RecipeValue::Bytes(b"abc".to_vec()),
        RecipeValue::Bool(true),
    ];
    assert_eq!(
        evaluate_recipe(&package, recipe_id, &runtime_limit_inputs).unwrap(),
        gb_bootstrap::recipe::RecipeOutcome {
            status: 11,
            outputs: vec![],
        }
    );
    assert_eq!(
        evaluate_recipe(&package, 3, &[]).unwrap(),
        gb_bootstrap::recipe::RecipeOutcome {
            status: 4,
            outputs: vec![],
        }
    );
}
