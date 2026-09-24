use gb_bootstrap::recipe_wire_v2::decode_recipe_package_v2;
use gb_bootstrap::route_semantics_v2::{ContextState, validate_definitions};
use std::collections::BTreeMap;
use std::sync::OnceLock;
fn input() -> &'static (
    gb_slice::SliceCompilation,
    Vec<Vec<u8>>,
    gb_bootstrap::recipe_wire_v1::RecipePackageV1,
) {
    static INPUT: OnceLock<(
        gb_slice::SliceCompilation,
        Vec<Vec<u8>>,
        gb_bootstrap::recipe_wire_v1::RecipePackageV1,
    )> = OnceLock::new();
    INPUT.get_or_init(|| {
        let slice = gb_slice::compile_slice_v1(
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
        .unwrap();
        let prefix = gb_bootstrap::route_v2::build_route_prefixes(&slice).unwrap()[0].clone();
        let mut at = 64;
        let mut values = vec![];
        let mut package = None;
        while at < prefix.len() {
            let n = u32::from_be_bytes(prefix[at + 4..at + 8].try_into().unwrap()) as usize;
            let p = &prefix[at + 8..at + 8 + n];
            if prefix[at + 1] == 1 {
                values.push(p[14..].to_vec());
            }
            if prefix[at + 1] == 5 {
                package = Some(decode_recipe_package_v2(p, 8).unwrap());
            }
            at += 8 + n;
        }
        (slice, values, package.unwrap())
    })
}
#[test]
fn validates_observed_relationships_and_retains_unresolved_contexts() {
    let (_, values, package) = input();
    let proof = validate_definitions(
        &values.iter().map(Vec::as_slice).collect::<Vec<_>>(),
        package,
    )
    .unwrap();
    let result = proof.prove_recovered(None, None, &BTreeMap::new());
    assert_eq!(result.required(), ContextState::Unresolved);
    assert_eq!(result.all(), ContextState::Unresolved);
}

#[test]
fn case_identity_cannot_be_replaced_by_another_valid_constructed_case() {
    let (_, values, package) = input();
    let mut changed = values.clone();
    let other = values[9][22 + 57 * 7..22 + 57 * 8].to_vec();
    changed[9][22 + 57 * 4..22 + 57 * 5].copy_from_slice(&other);
    assert!(
        validate_definitions(
            &changed.iter().map(Vec::as_slice).collect::<Vec<_>>(),
            package
        )
        .is_err()
    );
}
#[test]
fn selection_discriminants_cannot_be_forged_or_replaced_by_valid_rows() {
    let (_, values, package) = input();
    let start = 206 + 583 + 2 + 48 * 14 + 2 + 6 * 12 + 2 + 4 * 12 + 2;
    for index in [8, 9] {
        for mutation in 0..3 {
            let mut changed = values.clone();
            let at = start + 32 * index;
            match mutation {
                0 => changed[11][at..at + 32]
                    .copy_from_slice(&values[11][start + 32 * 6..start + 32 * 7]),
                1 => changed[11][at + 16] = 6,
                _ => changed[11][at + 20] = 2,
            }
            assert!(
                validate_definitions(
                    &changed.iter().map(Vec::as_slice).collect::<Vec<_>>(),
                    package
                )
                .is_err(),
                "row {index} mutation {mutation}"
            );
        }
    }
}

#[test]
fn contradictions_in_each_fact_and_miniature_consequence_reject() {
    let (_, values, package) = input();
    for (fact, at) in [
        (0, 1),
        (1, 8),
        (2, 7),
        (3, 20),
        (4, 10),
        (5, 5),
        (6, 144),
        (7, 112),
        (8, 39),
        (9, 110),
        (9, 162 + 7 * 24),
        (9, 61),
        (9, 63),
        (9, 67),
        (9, 69),
        (9, 71),
        (9, 73),
        (9, 75),
        (9, 77),
        (9, 101),
        (9, 103),
        (9, 106),
        (9, 158),
        (9, 369),
        (9, 362),
        (9, 383),
        (9, 392),
        (9, 420),
        (9, 174 + 3 * 24 + 7),
        (10, 73),
        (11, 210),
        (11, 206 + 1703 - 1),
        (11, 2077 + 146),
        (11, 2077 + 321),
    ] {
        let mut changed = values.clone();
        changed[fact][at] ^= 1;
        assert!(
            validate_definitions(
                &changed.iter().map(Vec::as_slice).collect::<Vec<_>>(),
                package
            )
            .is_err(),
            "fact {} byte {}",
            fact + 1,
            at
        );
    }
}
fn bodies(slice: &gb_slice::SliceCompilation) -> BTreeMap<u32, Vec<u8>> {
    let raw = slice.all_stream();
    let mut at = 4;
    let mut frames = BTreeMap::new();
    while at < raw.len() {
        let n = 8 + u32::from_be_bytes(raw[at + 4..at + 8].try_into().unwrap()) as usize;
        frames.insert(
            u16::from_be_bytes(raw[at..at + 2].try_into().unwrap()),
            raw[at..at + n].to_vec(),
        );
        at += n;
    }
    slice
        .assignments()
        .iter()
        .map(|a| {
            (
                u32::from(a.section_id()),
                a.record_ids()
                    .iter()
                    .flat_map(|id| frames[id].clone())
                    .collect(),
            )
        })
        .collect()
}
#[test]
fn recovered_proof_binds_context_namespace_subject_and_exact_section_membership() {
    let (slice, values, package) = input();
    let commitments = validate_definitions(
        &values.iter().map(Vec::as_slice).collect::<Vec<_>>(),
        package,
    )
    .unwrap();
    let body = bodies(slice);
    let proof = commitments.prove_recovered(
        Some(slice.required_stream()),
        Some(slice.all_stream()),
        &body,
    );
    assert_eq!(proof.required(), ContextState::Consistent);
    assert_eq!(proof.all(), ContextState::Consistent);
    assert_eq!(
        commitments
            .prove_recovered(
                Some(slice.required_stream()),
                Some(slice.all_stream()),
                &BTreeMap::new()
            )
            .all(),
        ContextState::Unresolved
    );
    let mut swapped = body.clone();
    swapped.insert(100, body[&200].clone());
    assert_eq!(
        commitments
            .prove_recovered(
                Some(slice.required_stream()),
                Some(slice.all_stream()),
                &swapped
            )
            .all(),
        ContextState::Contradiction
    );
    let mut changed = values.clone();
    changed[11][3] ^= 1;
    let altered = validate_definitions(
        &changed.iter().map(Vec::as_slice).collect::<Vec<_>>(),
        package,
    )
    .unwrap();
    assert_eq!(
        altered
            .prove_recovered(
                Some(slice.required_stream()),
                Some(slice.all_stream()),
                &body
            )
            .required(),
        ContextState::Contradiction
    );
    // A fully content-valid stream with another namespace still cannot discharge
    // the carried namespace claim, and does not change transport availability.
    let projection = gb_content::stream_validation(slice.all_stream()).unwrap();
    let records = projection
        .records()
        .iter()
        .map(|r| {
            let mut p = r.payload().clone();
            if r.record_id() == 588 {
                if let gb_content::RecordPayload::SemanticBinding { namespace_id, .. } = &mut p {
                    *namespace_id = 4;
                }
            }
            gb_content::Record::authoring(r.record_id(), p)
        })
        .collect();
    let changed =
        gb_content::encode_content_v0(&gb_content::ContentAuthoringProjection::new(0, records))
            .unwrap();
    assert_eq!(
        commitments
            .prove_recovered(Some(slice.required_stream()), Some(&changed), &body)
            .all(),
        ContextState::Contradiction
    );
}
#[test]
fn bounded_shapes_and_forged_cached_package_reject_without_partial_commitments() {
    let (_, values, package) = input();
    let refs = values.iter().map(Vec::as_slice).collect::<Vec<_>>();
    assert!(validate_definitions(&refs[..11], package).is_err());
    for n in [0, 1, 2419, 2420, 2422, 16384] {
        let mut changed = values.clone();
        changed[11].resize(n, 0);
        assert!(
            validate_definitions(
                &changed.iter().map(Vec::as_slice).collect::<Vec<_>>(),
                package
            )
            .is_err()
        );
    }
    let mut forged = package.clone();
    forged.encoded[0] ^= 1;
    assert!(validate_definitions(&refs, &forged).is_err());
}
