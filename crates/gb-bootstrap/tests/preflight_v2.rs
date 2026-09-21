use gb_bootstrap::preflight_v2::{CORE_PATHS, PreflightInputsV2, build_preflight_v2};
use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
fn object(v: &V) -> &std::collections::BTreeMap<String, V> {
    let V::Object(v) = v else { panic!() };
    v
}
fn array(v: &V) -> &[V] {
    let V::Array(v) = v else { panic!() };
    v
}
#[test]
fn freshly_generated_preflight_binds_all22_files_examples_boundaries_and_resources() {
    let core = build_preflight_v2(PreflightInputsV2::default()).unwrap();
    assert_eq!(
        core.documents().map(|(p, _)| p).collect::<Vec<_>>(),
        CORE_PATHS
    );
    let known =
        validate_canonical_manifest(core.document("known-answer-manifest.json").unwrap()).unwrap();
    let known = object(&known);
    let examples = array(&known["example_rows"]);
    assert_eq!(examples.len(), 128);
    assert!(
        examples
            .iter()
            .all(|v| object(v)["success"] == V::Bool(true))
    );
    assert!(examples.iter().any(|v| object(v)["status"] == V::U64(4)));
    assert!(examples.iter().any(|v| object(v)["status"] == V::U64(11)));
    let grammar =
        validate_canonical_manifest(core.document("grammar-state-manifest.json").unwrap()).unwrap();
    let grammar = object(&grammar);
    assert_eq!(array(&grammar["boundary_rows"]).len(), 21);
    assert_eq!(array(&grammar["boundary_kats"]).len(), 4);
    assert_eq!(
        object(&grammar["summary"])["result"],
        V::String("pass".into())
    );
    let limits =
        validate_canonical_manifest(core.document("preflight-resource-limits.json").unwrap())
            .unwrap();
    assert_eq!(object(&limits)["case_count"], V::U64(22));
    assert_eq!(
        core.document("decoder-result.json").unwrap(),
        core.recovery().decoder_result()
    );
    assert_eq!(
        core.document("m2-required.content-v0.bin").unwrap(),
        core.recovery().required_stream()
    );
    assert_eq!(
        core.document("m2-all.content-v0.bin").unwrap(),
        core.recovery().all_stream()
    );
    assert!(core.document("damage/manifest.json").is_none());
    assert!(core.document("independence-proof.json").is_none());
    if let Some(path) = std::env::var_os("GB_PREFLIGHT_V2_TEST_EXPORT") {
        use std::os::unix::fs::{DirBuilderExt, PermissionsExt};
        let path = std::path::PathBuf::from(path);
        assert!(path.is_absolute());
        std::fs::DirBuilder::new()
            .mode(0o700)
            .create(&path)
            .unwrap();
        for (name, raw) in core.documents() {
            std::fs::write(path.join(name), raw).unwrap();
            std::fs::set_permissions(path.join(name), std::fs::Permissions::from_mode(0o644))
                .unwrap();
        }
    }
}
#[test]
fn source_bound_violation_rejects_before_carrier_or_receiver_work() {
    let inputs = PreflightInputsV2::default();
    let changed = PreflightInputsV2::new(inputs.sources().map(|(p, b)| {
        if p == "spec/receiver-bounds-v2.md" {
            (p, b"changed owner".as_slice())
        } else {
            (p, b)
        }
    }))
    .unwrap();
    assert!(build_preflight_v2(changed).is_err());
}
