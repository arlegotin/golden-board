use gb_bootstrap::learner_bundle_v2::{
    LearnerBundleSourcesV2, build_learner_assessment_v2, build_learner_bundle_v2,
    validate_learner_assessment_v2,
};
use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
use std::sync::OnceLock;

fn required() -> &'static [u8] {
    static RAW: OnceLock<Vec<u8>> = OnceLock::new();
    RAW.get_or_init(|| {
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
        .required_stream()
        .to_vec()
    })
}

#[test]
fn native_chess_derives_all_twelve_finals_from_recovered_pictures() {
    let sources = LearnerBundleSourcesV2::default();
    let raw = build_learner_assessment_v2(
        required(),
        sources.intent,
        sources.chess_fixture,
        sources.game_set,
    )
    .unwrap();
    let V::Object(root) = validate_canonical_manifest(&raw).unwrap() else {
        panic!()
    };
    let V::Array(pages) = &root["pages"] else {
        panic!()
    };
    assert_eq!(pages.len(), 12);
    for (page, correct) in pages.iter().zip([1, 2, 1, 2, 1, 2, 2, 1, 2, 1, 2, 2]) {
        let V::Object(page) = page else { panic!() };
        assert_eq!(page["correct"], V::Array(vec![V::U64(correct)]));
    }
    validate_learner_assessment_v2(
        &raw,
        required(),
        sources.intent,
        sources.chess_fixture,
        sources.game_set,
    )
    .unwrap();
}

#[test]
fn stale_result_malformed_types_and_changed_question_fail_closed() {
    let sources = LearnerBundleSourcesV2::default();
    let source = std::str::from_utf8(sources.intent).unwrap();
    for modified in [
        source.replacen("\"b1c3\", \"b8c6\"", "\"b1a3\", \"b8c6\"", 1),
        source.replacen("page_ordinal = 53", "page_ordinal = true", 1),
        source.replacen("reverse = true", "reverse = 1", 1),
    ] {
        assert_ne!(modified.as_bytes(), sources.intent);
        assert!(
            build_learner_assessment_v2(
                required(),
                modified.as_bytes(),
                sources.chess_fixture,
                sources.game_set
            )
            .is_err()
        );
    }
    let mut bad = required().to_vec();
    bad[100] ^= 1;
    assert!(
        build_learner_assessment_v2(
            &bad,
            sources.intent,
            sources.chess_fixture,
            sources.game_set
        )
        .is_err()
    );
    assert!(
        validate_learner_assessment_v2(
            b"{}\n",
            required(),
            sources.intent,
            sources.chess_fixture,
            sources.game_set
        )
        .is_err()
    );
}

#[test]
fn fresh_actual_recovery_packages_nine_recipient_files_and_rejects_stale_templates() {
    let compiled = gb_slice::compile_slice_v1(
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
    let carrier = gb_bootstrap::carrier_v2::build_carrier(&compiled).unwrap();
    let projection =
        gb_bootstrap::static_v2::build_static_projection_v2(&compiled, &carrier).unwrap();
    let recovered = gb_bootstrap::recovery_provenance_v2::build_recovery_provenance_v2(
        gb_bootstrap::recovery_provenance_v2::RecoveryProvenanceInputs {
            carrier: carrier.packed_bytes(),
            candidate_manifest: projection.document("candidate-manifest.json").unwrap(),
            capacity_ledger: projection.document("capacity-ledger.json").unwrap(),
            ownership_ledger: projection.document("ownership-ledger.json").unwrap(),
            semantic_envelope: projection.document("semantic-envelope.json").unwrap(),
            profile_policy: include_bytes!("../../../spec/profile-policy-v2.toml"),
            profile_limits: include_bytes!("../../../spec/profile-limits-v2.toml"),
            damage_policy: include_bytes!("../../../spec/damage-policy-v2.toml"),
        },
    )
    .unwrap();
    let sources = LearnerBundleSourcesV2::default();
    let files = build_learner_bundle_v2(&recovered, sources).unwrap();
    assert_eq!(files.len(), 11);
    assert_eq!(
        files.keys().filter(|p| p.starts_with("recipient/")).count(),
        9
    );
    assert_eq!(
        files["recipient/lesson.content-v0.bin"],
        recovered.required_stream()
    );
    assert_eq!(
        files["owner/semantic-evaluation.json"],
        build_learner_assessment_v2(
            recovered.required_stream(),
            sources.intent,
            sources.chess_fixture,
            sources.game_set
        )
        .unwrap()
    );
    assert_eq!(files["recipient/READ-ME.txt"], sources.literals[0]);
    assert!(files["recipient/lesson-data.js"].starts_with(b"globalThis.LESSON_DATA = {"));
    assert!(files["recipient/lesson-data.js"].ends_with(b"};\n"));
    let mut forged = sources;
    forged.literals[4] = b"stale viewer source\n";
    assert!(build_learner_bundle_v2(&recovered, forged).is_err());
    assert_eq!(files, build_learner_bundle_v2(&recovered, sources).unwrap());
}
