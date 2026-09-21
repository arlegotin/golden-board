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
        let route = admit_route_prefix(prefix, 2040, 112, sector as u8, &mut cost)
            .unwrap()
            .unwrap();
        assert_eq!(route.mapping().unit_slot_count(), 1908);
        assert_eq!(route.package().encoded.len(), 18273);
        assert!(cost.primitive_steps > 0);
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
    assert_eq!(cost.primitive_steps, full.primitive_steps);
}
