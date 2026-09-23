use gb_bootstrap::damage::ResourceProjection;
use gb_bootstrap::route_receiver_v2::admit_route_prefix;
fn slice() -> gb_slice::SliceCompilation {
    gb_slice::compile_slice_v1(
        include_bytes!("../../../studies/m2/slice-v1.json"),
        gb_slice::SliceInputs {
            declaration: include_bytes!("../../../studies/m2/slice-v0.json"),
            content_fixture: include_bytes!("../../../conformance/content-v0.json"),
            chess_fixture: include_bytes!("../../../conformance/chess-v0.json"),
            game_set: include_bytes!("../../../reports/game-set-v0.bin"),
            content_spec: include_bytes!("../../../spec/content-v0.md"),
            constants: include_bytes!("../../../spec/constants-v0.toml"),
            curriculum: include_bytes!("../../../spec/curriculum-v0.toml"),
        },
    )
    .unwrap()
}
#[test]
fn observed_complete_route_admits_only_after_every_example_and_mapping() {
    let prefixes = gb_bootstrap::route_v2::build_route_prefixes(&slice()).unwrap();
    for (sector, prefix) in prefixes.iter().enumerate() {
        let mut cost = ResourceProjection::default();
        let route = admit_route_prefix(prefix, 2048, 112, sector as u8, &mut cost)
            .unwrap()
            .unwrap();
        assert_eq!(route.mapping().unit_slot_count(), 1925);
        assert_eq!(route.package().encoded.len(), 18531);
        let logical = &route.package().logical;
        let mut expected_steps = 3 * logical.recipe_primitive_steps(109).unwrap()
            + 13 * logical.recipe_primitive_steps(111).unwrap()
            + 8 * logical.recipe_primitive_steps(110).unwrap()
            + logical.recipe_primitive_steps(30).unwrap()
            + 4 * logical.recipe_primitive_steps(113).unwrap();
        let mut at = 64;
        while at < prefix.len() {
            let length = u32::from_be_bytes(prefix[at + 4..at + 8].try_into().unwrap()) as usize;
            if [2, 3].contains(&prefix[at + 1]) {
                let recipe = u16::from_be_bytes(prefix[at + 10..at + 12].try_into().unwrap());
                expected_steps += logical.recipe_primitive_steps(recipe).unwrap();
            }
            at += 8 + length;
        }
        assert_eq!(cost.primitive_steps, expected_steps);
        assert_eq!(cost.section_attempts, 0);
    }
}
#[test]
fn structural_status_example_package_and_domain_mutants_fail_closed() {
    let prefixes = gb_bootstrap::route_v2::build_route_prefixes(&slice()).unwrap();
    let original = &prefixes[0];
    for (at, value) in [(41, 1u8), (47, 46), (63, 1)] {
        let mut changed = original.clone();
        changed[at] = value;
        assert!(
            admit_route_prefix(&changed, 2040, 112, 0, &mut ResourceProjection::default())
                .unwrap()
                .is_none()
        );
    }
    let mut changed = original.clone();
    let first_example = 64 + 8 + 14 + 16;
    let input = u32::from_be_bytes(
        changed[first_example + 12..first_example + 16]
            .try_into()
            .unwrap(),
    ) as usize;
    let output = first_example + 8 + 12 + input;
    changed[output + 1] ^= 1;
    assert!(
        admit_route_prefix(&changed, 2040, 112, 0, &mut ResourceProjection::default())
            .unwrap()
            .is_none()
    );
    assert!(
        admit_route_prefix(original, 2040, 111, 0, &mut ResourceProjection::default())
            .unwrap()
            .is_none()
    );
    assert!(
        admit_route_prefix(
            &original[..original.len() - 1],
            2040,
            112,
            0,
            &mut ResourceProjection::default()
        )
        .unwrap()
        .is_none()
    );
    let mut changed = original.clone();
    let output_length = u32::from_be_bytes(
        changed[first_example + 16..first_example + 20]
            .try_into()
            .unwrap(),
    ) as usize;
    changed[output + output_length - 1] ^= 1;
    let mut consumed = ResourceProjection::default();
    assert!(
        admit_route_prefix(&changed, 2040, 112, 0, &mut consumed)
            .unwrap()
            .is_none()
    );
    assert!(
        consumed.primitive_steps > 0,
        "a rejected executed example retains its cost"
    );
    let mut changed = original.clone();
    let mut package_record = 64;
    while changed[package_record + 1] != 5 {
        package_record += 8 + u32::from_be_bytes(
            changed[package_record + 4..package_record + 8]
                .try_into()
                .unwrap(),
        ) as usize;
    }
    changed[package_record + 8] ^= 1;
    changed[package_record + 8 + 36..package_record + 8 + 44]
        .copy_from_slice(&268435457u64.to_be_bytes());
    assert!(
        admit_route_prefix(&changed, 2040, 112, 0, &mut ResourceProjection::default())
            .unwrap()
            .is_none()
    );
}
#[test]
fn contradictory_numeric_definition_rejects_after_owned_example_schedule() {
    let mut prefix = gb_bootstrap::route_v2::build_route_prefixes(&slice()).unwrap()[0].clone();
    prefix[64 + 8 + 14 + 1] ^= 1;
    let mut cost = ResourceProjection::default();
    assert!(
        admit_route_prefix(&prefix, 2040, 112, 0, &mut cost)
            .unwrap()
            .is_none()
    );
    let clean = gb_bootstrap::route_v2::build_route_prefixes(&slice()).unwrap()[0].clone();
    let mut full = ResourceProjection::default();
    assert!(
        admit_route_prefix(&clean, 2040, 112, 0, &mut full)
            .unwrap()
            .is_some()
    );
    assert_eq!(cost, full);
}

#[test]
fn malformed_group_traces_and_valid_but_unrelated_primary_examples_reject() {
    let original = gb_bootstrap::route_v2::build_route_prefixes(&slice()).unwrap()[0].clone();
    let package = gb_bootstrap::recipe_wire_v1::decode_recipe_package_v1(
        &gb_bootstrap::teaching_recipe_v2::build_teaching_recipe_package().unwrap(),
        8,
    )
    .unwrap();
    let mut preceding_cost = ResourceProjection::default();
    let mut at = 64;
    let mut fact10 = 0;
    let mut primary = 0;
    let mut held_out = 0;
    let mut framed_erasure = 0;
    while at < original.len() {
        let id = u16::from_be_bytes(original[at + 2..at + 4].try_into().unwrap());
        if id == 1001 {
            fact10 = at + 8 + 14;
        }
        if id == 1002 {
            primary = at + 8 + 12;
        }
        if id == 1003 {
            held_out = at + 8 + 12;
        }
        if id == 1004 {
            framed_erasure = at + 8 + 12;
        }
        if primary == 0 && [2, 3].contains(&original[at + 1]) {
            let recipe = u16::from_be_bytes(original[at + 10..at + 12].try_into().unwrap());
            preceding_cost.primitive_steps +=
                package.logical.recipe_primitive_steps(recipe).unwrap();
            preceding_cost.peak_scratch_bytes = preceding_cost
                .peak_scratch_bytes
                .max(package.logical.recipe_peak_scratch_bytes(recipe).unwrap());
        }
        at += 8 + u32::from_be_bytes(original[at + 4..at + 8].try_into().unwrap()) as usize;
    }
    for offset in [
        162 + 7 * 24,
        61,
        63,
        67,
        69,
        71,
        73,
        75,
        77,
        106,
        354 + 9,
        368,
        369,
        370,
        373 + 10,
        390 + 2,
        174 + 3 * 24 + 7,
    ] {
        let mut changed = original.clone();
        changed[fact10 + offset] ^= 1;
        assert!(
            admit_route_prefix(&changed, 2048, 112, 0, &mut ResourceProjection::default())
                .unwrap()
                .is_none()
        );
    }
    let mut changed = original.clone();
    changed[primary..primary + 42].copy_from_slice(&original[held_out..held_out + 42]);
    let mut rejected_cost = ResourceProjection::default();
    assert!(
        admit_route_prefix(&changed, 2048, 112, 0, &mut rejected_cost)
            .unwrap()
            .is_none()
    );
    assert_eq!(rejected_cost, preceding_cost);

    let mut complete = ResourceProjection::default();
    assert!(
        admit_route_prefix(&original, 2048, 112, 0, &mut complete)
            .unwrap()
            .is_some()
    );
    let erasure_steps = package.logical.recipe_primitive_steps(30).unwrap();
    let repetition_steps = package.logical.recipe_primitive_steps(113).unwrap();
    let constructor_steps = package.logical.recipe_primitive_steps(111).unwrap();
    let decision_steps = package.logical.recipe_primitive_steps(110).unwrap();
    let after_constructors = 8 * decision_steps + erasure_steps + 4 * repetition_steps;
    for (offset, replacement, unexecuted) in [
        (102, 110, 13 * constructor_steps + after_constructors),
        (103, 1, 13 * constructor_steps + after_constructors),
        // Template3's invalid range rejects before its constructor call.
        (116, 72, 11 * constructor_steps + after_constructors),
        (159, 111, after_constructors),
        (369, 2, erasure_steps + 4 * repetition_steps),
        (387, 112, 4 * repetition_steps),
        (391, 3, 4 * repetition_steps),
        (399, 3, 3 * repetition_steps),
        (407, 3, 2 * repetition_steps),
        (415, 3, repetition_steps),
        // Two observed zeroes produce known=1, contradicting the carried tie.
        // This rejects at the first113 call only if counts come from symbols.
        (392, 0, 3 * repetition_steps),
        // Position65 still decodes A, but differs from the observed erasure64.
        // Independent semantics rejects it after the entire VM schedule.
        (383, 65, 0),
        // The final byte is metadata and must retain the complete VM cost.
        (442, 0, 0),
    ] {
        let mut changed = original.clone();
        changed[fact10 + offset] = replacement;
        if offset == 383 {
            changed[framed_erasure + 10] = replacement;
        }
        let mut retained = ResourceProjection::default();
        assert!(
            admit_route_prefix(&changed, 2048, 112, 0, &mut retained)
                .unwrap()
                .is_none(),
            "offset {offset}"
        );
        assert_eq!(
            retained.primitive_steps + unexecuted,
            complete.primitive_steps,
            "offset {offset}"
        );
    }
}

#[test]
fn constructor_range_validation_preserves_pre_call_and_final_semantic_charges() {
    let original = gb_bootstrap::route_v2::build_route_prefixes(&slice()).unwrap()[0].clone();
    let package = gb_bootstrap::recipe_wire_v1::decode_recipe_package_v1(
        &gb_bootstrap::teaching_recipe_v2::build_teaching_recipe_package().unwrap(),
        8,
    )
    .unwrap();
    let mut base_steps = 3 * package.logical.recipe_primitive_steps(109).unwrap();
    let mut at = 64;
    let mut fact10 = 0;
    let mut framed_calls = 0;
    while at < original.len() {
        let length = u32::from_be_bytes(original[at + 4..at + 8].try_into().unwrap()) as usize;
        let id = u16::from_be_bytes(original[at + 2..at + 4].try_into().unwrap());
        if id == 1001 {
            fact10 = at + 8 + 14;
        }
        if [2, 3].contains(&original[at + 1]) {
            let recipe = u16::from_be_bytes(original[at + 10..at + 12].try_into().unwrap());
            base_steps += package.logical.recipe_primitive_steps(recipe).unwrap();
            framed_calls += 1;
        }
        at += 8 + length;
    }
    assert_eq!(framed_calls, 33);
    let full_steps = base_steps
        + 13 * package.logical.recipe_primitive_steps(111).unwrap()
        + 8 * package.logical.recipe_primitive_steps(110).unwrap()
        + package.logical.recipe_primitive_steps(30).unwrap()
        + 4 * package.logical.recipe_primitive_steps(113).unwrap();
    // Template1 has count0. First73 is outside the constructor's domain;
    // first1/72 are valid no-ops but violate the later canonical descriptor rule.
    for (first, expected_steps) in [(73, base_steps), (1, full_steps), (72, full_steps)] {
        let mut changed = original.clone();
        changed[fact10 + 108] = first;
        let mut cost = ResourceProjection::default();
        assert!(
            admit_route_prefix(&changed, 2048, 112, 0, &mut cost)
                .unwrap()
                .is_none()
        );
        assert_eq!(cost.primitive_steps, expected_steps, "first {first}");
    }
}

#[test]
fn embedded_traces_execute_observed110_even_when_all_framed_examples_pass() {
    use gb_bootstrap::recipe_wire_v1::{decode_recipe_package_v1, evaluate_serialized_recipe_v1};
    use gb_bootstrap::teaching_recipe_v2::build_teaching_recipe_package_from_source;
    let original = gb_bootstrap::route_v2::build_route_prefixes(&slice()).unwrap()[0].clone();
    let mut source: toml::Value =
        toml::from_str(include_str!("../../../spec/recipe-teaching-v2.toml")).unwrap();
    // No framed example invokes110, but its verified state still must execute.
    source["recipes"][0]["nodes"][9][8] = 1.into();
    let changed_package =
        build_teaching_recipe_package_from_source(toml::to_string(&source).unwrap().as_bytes())
            .unwrap();
    let package = decode_recipe_package_v1(&changed_package, 8).unwrap();
    let mut changed = original.clone();
    let mut at = 64;
    while at < changed.len() {
        let length = u32::from_be_bytes(changed[at + 4..at + 8].try_into().unwrap()) as usize;
        let kind = changed[at + 1];
        if [2, 3].contains(&kind) {
            let recipe = u16::from_be_bytes(changed[at + 10..at + 12].try_into().unwrap());
            let input = u32::from_be_bytes(changed[at + 12..at + 16].try_into().unwrap()) as usize;
            assert_eq!(
                evaluate_serialized_recipe_v1(&package, recipe, &changed[at + 20..at + 20 + input])
                    .unwrap(),
                changed[at + 20 + input..at + 8 + length]
            );
        }
        if kind == 5 {
            assert_eq!(length, changed_package.len());
            changed[at + 8..at + 8 + length].copy_from_slice(&changed_package);
        }
        at += 8 + length;
    }
    let mut clean_cost = ResourceProjection::default();
    assert!(
        admit_route_prefix(&original, 2048, 112, 0, &mut clean_cost)
            .unwrap()
            .is_some()
    );
    let mut rejected_cost = ResourceProjection::default();
    assert!(
        admit_route_prefix(&changed, 2048, 112, 0, &mut rejected_cost)
            .unwrap()
            .is_none()
    );
    // The third embedded trace rejects and retains its VM charge.
    assert_eq!(
        rejected_cost.primitive_steps
            + 5 * package.logical.recipe_primitive_steps(110).unwrap()
            + package.logical.recipe_primitive_steps(30).unwrap()
            + 4 * package.logical.recipe_primitive_steps(113).unwrap(),
        clean_cost.primitive_steps
    );
}

#[test]
fn embedded_constructors_reject_changed_range_table_after_framed_examples_pass() {
    use gb_bootstrap::recipe_wire_v1::{decode_recipe_package_v1, evaluate_serialized_recipe_v1};
    let original = gb_bootstrap::route_v2::build_route_prefixes(&slice()).unwrap()[0].clone();
    let mut changed_package =
        gb_bootstrap::teaching_recipe_v2::build_teaching_recipe_package().unwrap();
    let mut cursor = 64;
    let table_count = u16::from_be_bytes(changed_package[18..20].try_into().unwrap());
    let mut changed_table = false;
    for _ in 0..table_count {
        let id = u16::from_be_bytes(changed_package[cursor..cursor + 2].try_into().unwrap());
        let length = u32::from_be_bytes(
            changed_package[cursor + 12..cursor + 16]
                .try_into()
                .unwrap(),
        ) as usize;
        if id == 22 {
            // Bit100 is outside both ordinary range slices. Its all-ones
            // mask position contains a source zero, so ordinary erasure still
            // passes; template3's bit0 flip reveals the damaged range mask.
            changed_package[cursor + 16 + 12] ^= 8;
            changed_table = true;
        }
        cursor += 16 + length;
    }
    assert!(changed_table);
    let package = decode_recipe_package_v1(&changed_package, 8).unwrap();
    let mut changed = original.clone();
    let mut at = 64;
    let mut framed = 0;
    while at < changed.len() {
        let length = u32::from_be_bytes(changed[at + 4..at + 8].try_into().unwrap()) as usize;
        match changed[at + 1] {
            2 | 3 => {
                let recipe = u16::from_be_bytes(changed[at + 10..at + 12].try_into().unwrap());
                let input =
                    u32::from_be_bytes(changed[at + 12..at + 16].try_into().unwrap()) as usize;
                assert_eq!(
                    evaluate_serialized_recipe_v1(
                        &package,
                        recipe,
                        &changed[at + 20..at + 20 + input]
                    )
                    .unwrap(),
                    changed[at + 20 + input..at + 8 + length],
                );
                framed += 1;
            }
            5 => {
                assert_eq!(length, changed_package.len());
                changed[at + 8..at + 8 + length].copy_from_slice(&changed_package);
            }
            _ => {}
        }
        at += 8 + length;
    }
    assert_eq!(framed, 33);
    let mut clean_cost = ResourceProjection::default();
    assert!(
        admit_route_prefix(&original, 2048, 112, 0, &mut clean_cost)
            .unwrap()
            .is_some()
    );
    let mut rejected_cost = ResourceProjection::default();
    assert!(
        admit_route_prefix(&changed, 2048, 112, 0, &mut rejected_cost)
            .unwrap()
            .is_none()
    );
    assert_eq!(
        rejected_cost.primitive_steps
            + 10 * package.logical.recipe_primitive_steps(111).unwrap()
            + 8 * package.logical.recipe_primitive_steps(110).unwrap()
            + package.logical.recipe_primitive_steps(30).unwrap()
            + 4 * package.logical.recipe_primitive_steps(113).unwrap(),
        clean_cost.primitive_steps,
    );
}
