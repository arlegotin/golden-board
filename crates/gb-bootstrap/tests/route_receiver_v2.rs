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
        assert_eq!(route.package().encoded.len(), 18661);
        let logical = &route.package().logical;
        let mut expected_steps = 3 * logical.recipe_primitive_steps(109).unwrap()
            + 10 * logical.recipe_primitive_steps(110).unwrap();
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
    while at < original.len() {
        let id = u16::from_be_bytes(original[at + 2..at + 4].try_into().unwrap());
        if id == 1001 {
            fact10 = at + 8 + 14;
        }
        if id == 1002 {
            primary = at + 8 + 12;
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
    for offset in [294 + 4 * 12 + 5, 294 + 8 * 12 + 10, 402, 412 + 5, 424] {
        let mut changed = original.clone();
        changed[fact10 + offset] ^= 1;
        assert!(
            admit_route_prefix(&changed, 2048, 112, 0, &mut ResourceProjection::default())
                .unwrap()
                .is_none()
        );
    }
    let mut changed = original.clone();
    let unrelated = &original[fact10 + 294 + 5 * 12..fact10 + 294 + 6 * 12];
    changed[primary..primary + 9].copy_from_slice(&unrelated[..9]);
    changed[primary + 11..primary + 14].copy_from_slice(&unrelated[9..]);
    let mut rejected_cost = ResourceProjection::default();
    assert!(
        admit_route_prefix(&changed, 2048, 112, 0, &mut rejected_cost)
            .unwrap()
            .is_none()
    );
    assert_eq!(rejected_cost, preceding_cost);
}

#[test]
fn embedded_traces_execute_observed110_even_when_both_framed_group_examples_pass() {
    use gb_bootstrap::recipe_wire_v1::{decode_recipe_package_v1, evaluate_serialized_recipe_v1};
    use gb_bootstrap::teaching_recipe_v2::build_teaching_recipe_package_from_source;
    let original = gb_bootstrap::route_v2::build_route_prefixes(&slice()).unwrap()[0].clone();
    let mut source: toml::Value =
        toml::from_str(include_str!("../../../spec/recipe-teaching-v2.toml")).unwrap();
    // The verified singleton state constant is unused by conflict and REP-only.
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
        if [2, 3].contains(&kind)
            && u16::from_be_bytes(changed[at + 8..at + 10].try_into().unwrap()) == 10
        {
            assert_eq!(
                evaluate_serialized_recipe_v1(&package, 110, &changed[at + 20..at + 29]).unwrap(),
                changed[at + 29..at + 34]
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
        rejected_cost.primitive_steps + 7 * package.logical.recipe_primitive_steps(110).unwrap(),
        clean_cost.primitive_steps
    );
}
