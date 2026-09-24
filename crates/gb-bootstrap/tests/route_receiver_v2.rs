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
        assert_eq!(route.package().encoded.len(), 17719);
        let logical = &route.package().logical;
        let mut expected_steps = 3 * logical.recipe_primitive_steps(109).unwrap()
            + 8 * logical.recipe_primitive_steps(126).unwrap();
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
        assert_eq!(cost.primitive_steps, 152936421);
        assert_eq!(cost.peak_scratch_bytes, 98398);
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

fn frames(prefix: &[u8]) -> std::collections::BTreeMap<u16, (usize, usize)> {
    let mut rows = std::collections::BTreeMap::new();
    let mut at = 64;
    while at < prefix.len() {
        let n = u32::from_be_bytes(prefix[at + 4..at + 8].try_into().unwrap()) as usize;
        let id = u16::from_be_bytes(prefix[at + 2..at + 4].try_into().unwrap());
        rows.insert(id, (at + 8, n));
        at += 8 + n;
    }
    rows
}
#[test]
fn valid_but_unrelated_primary_case_cannot_replace_its_bound_case() {
    let original = gb_bootstrap::route_v2::build_route_prefixes(&slice()).unwrap()[0].clone();
    let rows = frames(&original);
    let definition = rows[&1001].0 + 14;
    let primary = rows[&1002].0;
    let mut changed = original.clone();
    changed[primary + 12..primary + 12 + 57]
        .copy_from_slice(&original[definition + 22 + 57 * 5..definition + 22 + 57 * 6]);
    assert!(
        admit_route_prefix(&changed, 2048, 112, 0, &mut ResourceProjection::default())
            .unwrap()
            .is_none()
    );
}
#[test]
fn embedded_complete_group_failure_retains_exact_invoked_cost() {
    let original = gb_bootstrap::route_v2::build_route_prefixes(&slice()).unwrap()[0].clone();
    let rows = frames(&original);
    let p = rows[&6001];
    let package =
        gb_bootstrap::recipe_wire_v2::decode_recipe_package_v2(&original[p.0..p.0 + p.1], 8)
            .unwrap();
    let mut complete = ResourceProjection::default();
    assert!(
        admit_route_prefix(&original, 2048, 112, 0, &mut complete)
            .unwrap()
            .is_some()
    );
    let step = package.logical.recipe_primitive_steps(126).unwrap();
    let definition = rows[&1001].0 + 14;
    for case in [0usize, 1, 2, 3, 5] {
        let mut changed = original.clone();
        changed[definition + 22 + 57 * case + 5 + 28] ^= 1;
        let mut charged = ResourceProjection::default();
        assert!(
            admit_route_prefix(&changed, 2048, 112, 0, &mut charged)
                .unwrap()
                .is_none()
        );
        assert_eq!(
            charged.primitive_steps + (7 - case as u64) * step,
            complete.primitive_steps,
            "case {case}"
        );
    }
    for at in [0usize, 8, 10, 20, 21] {
        let mut changed = original.clone();
        changed[definition + at] ^= 1;
        let mut charged = ResourceProjection::default();
        assert!(
            admit_route_prefix(&changed, 2048, 112, 0, &mut charged)
                .unwrap()
                .is_none()
        );
        assert_eq!(
            charged.primitive_steps + 8 * step,
            complete.primitive_steps,
            "header {at}"
        );
    }
}
#[test]
fn changed_bootstrap_closure_rejects_before_any_example_execution() {
    let original = gb_bootstrap::route_v2::build_route_prefixes(&slice()).unwrap()[0].clone();
    let rows = frames(&original);
    let (at, len) = rows[&6001];
    let mut logical =
        gb_bootstrap::recipe_wire_v2::expand_recipe_package_v2(&original[at..at + len], 8).unwrap();
    let mut cursor = 64;
    let nt = u16::from_be_bytes(logical[18..20].try_into().unwrap());
    for _ in 0..nt {
        cursor +=
            16 + u32::from_be_bytes(logical[cursor + 12..cursor + 16].try_into().unwrap()) as usize;
    }
    while u16::from_be_bytes(logical[cursor..cursor + 2].try_into().unwrap()) != 127 {
        cursor +=
            u32::from_be_bytes(logical[cursor + 28..cursor + 32].try_into().unwrap()) as usize;
    }
    let end =
        cursor + u32::from_be_bytes(logical[cursor + 28..cursor + 32].try_into().unwrap()) as usize;
    let n = u16::from_be_bytes(logical[cursor + 4..cursor + 6].try_into().unwrap())
        + u16::from_be_bytes(logical[cursor + 6..cursor + 8].try_into().unwrap());
    let start = cursor + 32 + 12 * usize::from(n);
    let node = (start..end)
        .step_by(32)
        .find(|p| logical[*p + 2] == 1 && logical[*p + 24..*p + 32] == 16406u64.to_be_bytes())
        .unwrap();
    logical[node + 24..node + 32].copy_from_slice(&16407u64.to_be_bytes());
    let package = gb_bootstrap::recipe_wire_v2::encode_recipe_package_v2(&logical, 8).unwrap();
    assert_eq!(package.len(), len);
    let mut changed = original;
    changed[at..at + len].copy_from_slice(&package);
    let mut charged = ResourceProjection::default();
    assert!(
        admit_route_prefix(&changed, 2048, 112, 0, &mut charged)
            .unwrap()
            .is_none()
    );
    assert_eq!(charged.primitive_steps, 0);
}
