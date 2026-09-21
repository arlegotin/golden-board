use gb_bootstrap::candidate_recipe::build_r3_recipe_package;
use gb_bootstrap::recipe::{RecipeValue, decode_recipe_package, evaluate_recipe};
use gb_bootstrap::recipe_wire_v1::{
    decode_recipe_package_v1, encode_recipe_package_v1, evaluate_recipe_v1,
    evaluate_serialized_recipe_v1, expand_recipe_package_v1,
};
use gb_foundation::{ManifestValue, validate_canonical_manifest};

fn hex(raw: &str) -> Vec<u8> {
    raw.as_bytes()
        .chunks_exact(2)
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
}

fn fixture() -> (Vec<u8>, u16, Vec<u8>, Vec<u8>) {
    let ManifestValue::Object(root) =
        validate_canonical_manifest(include_bytes!("../../../conformance/recipe-v0.json")).unwrap()
    else {
        panic!("object")
    };
    let text = |key: &str| match &root[key] {
        ManifestValue::String(s) => s.as_str(),
        _ => panic!("text"),
    };
    let ManifestValue::U64(id) = root["recipe_id"] else {
        panic!("number")
    };
    let list = |key: &str| match &root[key] {
        ManifestValue::Array(items) => items
            .iter()
            .flat_map(|item| match item {
                ManifestValue::String(s) => hex(s),
                _ => panic!("hex"),
            })
            .collect::<Vec<_>>(),
        _ => panic!("list"),
    };
    (
        hex(text("package_hex")),
        id as u16,
        list("inputs_hex"),
        list("expected_outputs_hex"),
    )
}

fn recipes(raw: &[u8]) -> Vec<(usize, usize, usize)> {
    let u16_at = |i| usize::from(u16::from_be_bytes(raw[i..i + 2].try_into().unwrap()));
    let u32_at = |i| u32::from_be_bytes(raw[i..i + 4].try_into().unwrap()) as usize;
    let mut cursor = 64;
    for _ in 0..u16_at(18) {
        cursor += 16 + u32_at(cursor + 12);
    }
    let mut rows = Vec::new();
    for _ in 0..u16_at(16) {
        let nodes = cursor + 32 + 12 * (u16_at(cursor + 4) + u16_at(cursor + 6));
        let count = u32_at(cursor + 8);
        rows.push((cursor, nodes, count));
        cursor += u32_at(cursor + 28);
    }
    assert_eq!(cursor, raw.len());
    rows
}

fn nodes(raw: &[u8], start: usize, count: usize) -> Vec<(usize, usize)> {
    let sizes = [
        0usize, 14, 8, 12, 10, 18, 10, 10, 10, 10, 10, 10, 10, 10, 16, 10, 10, 10, 10, 10, 12, 10,
        18, 12, 6, 14,
    ];
    let mut cursor = start;
    let mut rows = Vec::new();
    for _ in 0..count {
        let size = sizes[raw[cursor] as usize];
        rows.push((cursor, size));
        cursor += size;
    }
    rows
}

#[test]
fn independent_v7_package_round_trips_with_exact_opcode_node_saving() {
    let expanded = build_r3_recipe_package().unwrap();
    assert_eq!(expanded.len(), 25_930);
    let compact = encode_recipe_package_v1(&expanded, 7).unwrap();
    assert_eq!(compact.len(), 11_664);
    assert_eq!(&compact[8..12], &[0, 1, 0, 0]);
    assert_eq!(expand_recipe_package_v1(&compact, 7).unwrap(), expanded);
    let logical = decode_recipe_package(&expanded, 7).unwrap();
    let decoded = decode_recipe_package_v1(&compact, 7).unwrap();
    assert_eq!(decoded.logical, logical);
    assert!(decode_recipe_package(&compact, 7).is_err());
    assert!(decode_recipe_package_v1(&expanded, 7).is_err());
    assert_eq!(
        evaluate_serialized_recipe_v1(&decoded, 105, &[0, 0, 0, 1]).unwrap(),
        [0, 0, 0, 0, 0, 2]
    );
    assert_eq!(
        evaluate_serialized_recipe_v1(&decoded, 105, &[255; 4]).unwrap(),
        [0, 11]
    );
}

#[test]
fn all_opcodes_emit_offsets_and_failure_suppression_preserve_semantics() {
    let (expanded, id, input, expected) = fixture();
    let compact = encode_recipe_package_v1(&expanded, 1).unwrap();
    let parsed = decode_recipe_package_v1(&compact, 1).unwrap();
    assert_eq!(
        parsed
            .logical
            .opcode_ids()
            .collect::<std::collections::BTreeSet<_>>(),
        (1..=25).collect()
    );
    let mut success = vec![0, 0];
    success.extend(expected);
    assert_eq!(
        evaluate_serialized_recipe_v1(&parsed, id, &input).unwrap(),
        success
    );
    let mut bad = input.clone();
    bad[1] = 0;
    assert_eq!(
        evaluate_serialized_recipe_v1(&parsed, id, &bad).unwrap(),
        [0, 11]
    );
    assert_eq!(
        evaluate_serialized_recipe_v1(&parsed, 3, &[]).unwrap(),
        [0, 4]
    );
    let mut saw_offset = false;
    for (_, start, count) in recipes(&compact) {
        for (at, size) in nodes(&compact, start, count) {
            let node = &compact[at..at + size];
            if node[0] == 5 && node[10..18].iter().any(|x| *x != 0) {
                saw_offset = true;
            }
        }
    }
    assert!(
        saw_offset,
        "fixture must discriminate nonzero EMIT offset preservation"
    );
    assert_eq!(expand_recipe_package_v1(&compact, 1).unwrap(), expanded);
}

#[test]
fn profile8_is_explicit_and_v1_evaluation_revalidates_wire() {
    let mut expanded = build_r3_recipe_package().unwrap();
    expanded[12..14].copy_from_slice(&8u16.to_be_bytes());
    assert!(decode_recipe_package(&expanded, 8).is_err());
    let compact = encode_recipe_package_v1(&expanded, 8).unwrap();
    let mut parsed = decode_recipe_package_v1(&compact, 8).unwrap();
    assert_eq!(parsed.logical.profile_version, 8);
    assert!(
        evaluate_recipe(
            &parsed.logical,
            105,
            &[RecipeValue::Uint {
                width: 32,
                value: 1
            }]
        )
        .is_err()
    );
    assert_eq!(
        evaluate_recipe_v1(
            &parsed,
            105,
            &[RecipeValue::Uint {
                width: 32,
                value: 1
            }]
        )
        .unwrap()
        .status,
        0
    );
    parsed.logical.maximum_primitive_steps = 0;
    assert_eq!(
        evaluate_serialized_recipe_v1(&parsed, 105, &[255; 4]).unwrap(),
        [0, 11]
    );
    parsed.encoded[48] = 1;
    assert!(
        evaluate_recipe_v1(
            &parsed,
            105,
            &[RecipeValue::Uint {
                width: 32,
                value: 1
            }]
        )
        .is_err()
    );
    assert!(evaluate_serialized_recipe_v1(&parsed, 105, &[0; 4]).is_err());
    assert!(decode_recipe_package_v1(&compact, 7).is_err());
    assert!(decode_recipe_package_v1(&compact, 9).is_err());
}

#[test]
fn compact_shape_resource_unused_fields_and_emission_mutations_reject() {
    let (expanded, _, _, _) = fixture();
    let compact = encode_recipe_package_v1(&expanded, 1).unwrap();
    let mut changes = Vec::new();
    for (offset, bytes) in [
        (8, vec![0, 0]),
        (10, vec![0, 1]),
        (14, vec![0, 1]),
        (16, vec![1, 1]),
        (18, vec![16, 1]),
        (20, vec![255; 4]),
        (24, vec![255; 4]),
        (32, vec![0; 4]),
        (36, vec![255; 8]),
        (44, vec![255; 4]),
        (48, vec![1]),
    ] {
        let mut changed = compact.clone();
        changed[offset..offset + bytes.len()].copy_from_slice(&bytes);
        changes.push(changed);
    }
    let rows = recipes(&compact);
    let (first, node, _) = rows[0];
    for (offset, bytes) in [
        (first + 8, vec![255; 4]),
        (first + 28, vec![0; 4]),
        (node, vec![26]),
        (node + 2, vec![255; 4]),
    ] {
        let mut changed = compact.clone();
        changed[offset..offset + bytes.len()].copy_from_slice(&bytes);
        changes.push(changed);
    }
    let mut changed = compact.clone();
    changed.push(0);
    changes.push(changed);
    changes.push(compact[..compact.len() - 1].to_vec());
    changes.push(vec![0; 1_048_577]);
    for (recipe, start, count) in rows {
        for (at, _) in nodes(&compact, start, count) {
            if compact[at] == 24 {
                // An omitted field cannot be smuggled in as extra zero bytes.
                let mut changed = compact.clone();
                changed.splice(at + 6..at + 6, [0, 0]);
                let package_length = changed.len() as u32;
                changed[32..36].copy_from_slice(&package_length.to_be_bytes());
                let length =
                    u32::from_be_bytes(compact[recipe + 28..recipe + 32].try_into().unwrap()) + 2;
                changed[recipe + 28..recipe + 32].copy_from_slice(&length.to_be_bytes());
                changes.push(changed);
            }
            if compact[at] == 5 && compact[at + 10..at + 18].iter().any(|x| *x != 0) {
                let mut changed = compact.clone();
                changed[at + 10..at + 18].fill(0);
                changes.push(changed);
            }
        }
    }
    for changed in changes {
        assert!(decode_recipe_package_v1(&changed, 1).is_err());
        assert!(expand_recipe_package_v1(&changed, 1).is_err());
    }
    let mut invalid_expanded = expanded.clone();
    let (_, start, _) = recipes(&invalid_expanded)[0];
    invalid_expanded[start + 20] = 1;
    assert!(encode_recipe_package_v1(&invalid_expanded, 1).is_err());
}

fn zero_chain(count: usize) -> Vec<u8> {
    // Hand-authored reachable UINT64 zero chain, with exact logical resources.
    let mut raw = vec![0u8; 120];
    let push = |raw: &mut Vec<u8>,
                op: u8,
                kind: u8,
                width: u32,
                args: &[u16],
                aux: Option<u16>,
                imm: Option<u64>| {
        raw.extend([op, kind]);
        raw.extend(width.to_be_bytes());
        for arg in args {
            raw.extend(arg.to_be_bytes());
        }
        if let Some(aux) = aux {
            raw.extend(aux.to_be_bytes());
        }
        if let Some(imm) = imm {
            raw.extend(imm.to_be_bytes());
        }
    };
    push(&mut raw, 1, 0, 64, &[], None, Some(0));
    for index in 1..count - 3 {
        push(&mut raw, 6, 0, 64, &[1, index as u16], None, None);
    }
    push(&mut raw, 24, 5, 16, &[], None, None);
    push(&mut raw, 5, 5, 16, &[(count - 2) as u16], Some(1), Some(0));
    push(&mut raw, 5, 5, 16, &[(count - 3) as u16], Some(2), Some(0));
    let size = raw.len();
    let put16 = |raw: &mut [u8], at: usize, value: u16| {
        raw[at..at + 2].copy_from_slice(&value.to_be_bytes())
    };
    let put32 = |raw: &mut [u8], at: usize, value: u32| {
        raw[at..at + 4].copy_from_slice(&value.to_be_bytes())
    };
    let put64 = |raw: &mut [u8], at: usize, value: u64| {
        raw[at..at + 8].copy_from_slice(&value.to_be_bytes())
    };
    raw[..8].copy_from_slice(b"GBRECP0\0");
    put16(&mut raw, 8, 1);
    put16(&mut raw, 12, 8);
    put16(&mut raw, 16, 1);
    put32(&mut raw, 20, count as u32);
    put32(&mut raw, 24, (2 * count - 6) as u32);
    put32(&mut raw, 32, size as u32);
    put64(&mut raw, 36, count as u64);
    put32(&mut raw, 44, 24);
    put16(&mut raw, 64, 1);
    put16(&mut raw, 70, 2);
    put32(&mut raw, 72, count as u32);
    put32(&mut raw, 76, (2 * count - 6) as u32);
    put64(&mut raw, 80, count as u64);
    put32(&mut raw, 88, 24);
    put32(&mut raw, 92, (size - 64) as u32);
    put16(&mut raw, 96, 1);
    raw[98] = 5;
    put32(&mut raw, 100, 16);
    put32(&mut raw, 104, 1);
    put16(&mut raw, 108, 2);
    put32(&mut raw, 112, 64);
    put32(&mut raw, 116, 1);
    raw
}

#[test]
fn compact_expansion_enforces_nearest_valid_and_boundary_plus_one_sizes() {
    let limit_count = (1_048_576 - 120) / 32;
    let valid = zero_chain(limit_count);
    let expanded = expand_recipe_package_v1(&valid, 8).unwrap();
    assert_eq!(expanded.len(), 1_048_568);
    assert_eq!(encode_recipe_package_v1(&expanded, 8).unwrap(), valid);
    let too_large = zero_chain(limit_count + 1);
    assert!(too_large.len() < 1_048_576);
    assert!(expand_recipe_package_v1(&too_large, 8).is_err());
}

#[test]
fn variable_node_ranges_reject_truncation_extra_fields_and_fixed24_experiment() {
    let expanded = build_r3_recipe_package().unwrap();
    let compact = encode_recipe_package_v1(&expanded, 7).unwrap();
    for (recipe, start, count) in recipes(&compact) {
        let record_bytes =
            u32::from_be_bytes(compact[recipe + 28..recipe + 32].try_into().unwrap()) as usize;
        let offsets = nodes(&compact, start, count);
        let (last, width) = offsets[count - 1];
        assert_eq!(last + width, recipe + record_bytes);
        let mut changed = compact.clone();
        changed.remove(last + width - 1);
        let length = changed.len() as u32;
        changed[32..36].copy_from_slice(&length.to_be_bytes());
        changed[recipe + 28..recipe + 32]
            .copy_from_slice(&((record_bytes - 1) as u32).to_be_bytes());
        assert!(decode_recipe_package_v1(&changed, 7).is_err());
        let mut changed = compact.clone();
        changed[recipe + 8..recipe + 12].copy_from_slice(&((count - 1) as u32).to_be_bytes());
        let total = u32::from_be_bytes(changed[20..24].try_into().unwrap()) - 1;
        changed[20..24].copy_from_slice(&total.to_be_bytes());
        assert!(decode_recipe_package_v1(&changed, 7).is_err());
    }
    // Preserve a diagnostic rendering of the abandoned fixed24 shape only as
    // an invalid-input fixture; the production codec has no fallback branch.
    let rows = recipes(&expanded);
    let mut old = expanded[..rows[0].0].to_vec();
    old[8..10].copy_from_slice(&1u16.to_be_bytes());
    for (recipe, start, count) in rows {
        let first = old.len();
        old.extend_from_slice(&expanded[recipe..start]);
        for node in expanded[start..start + count * 32].chunks_exact(32) {
            old.extend_from_slice(&node[2..8]);
            old.extend_from_slice(&node[10..20]);
            old.extend_from_slice(&node[24..32]);
        }
        let length = (old.len() - first) as u32;
        old[first + 28..first + 32].copy_from_slice(&length.to_be_bytes());
    }
    let length = old.len() as u32;
    old[32..36].copy_from_slice(&length.to_be_bytes());
    assert_eq!(old.len(), 20_338);
    assert!(decode_recipe_package_v1(&old, 7).is_err());
}
