use gb_bootstrap::damage::{ArtifactState, SectionState};
use gb_bootstrap::damage_corpus_v2::DamageCorpusV2;
use gb_bootstrap::damage_oracle_v2::SemanticOracleV2;
use std::sync::OnceLock;
fn fixture() -> &'static DamageCorpusV2 {
    static CORPUS: OnceLock<DamageCorpusV2> = OnceLock::new();
    CORPUS.get_or_init(|| {
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
        let carrier = gb_bootstrap::carrier_v2::build_carrier(&slice).unwrap();
        DamageCorpusV2::new(
            &slice,
            &carrier,
            include_bytes!("../../../spec/route-data-v0.json"),
        )
        .unwrap()
    })
}

#[test]
fn complete_source_oracle_owns_selection_render_and_resource_rows() {
    use gb_bootstrap::damage_oracle_v2::FullOracleV2;
    let corpus = fixture();
    let full = FullOracleV2::new(corpus).unwrap();
    let semantic = SemanticOracleV2::new(corpus);
    for (family, ordinal) in [("D5", 0), ("D0", 0), ("D7", 405), ("B0", 0), ("B0", 20)] {
        let case = corpus.case(family, ordinal).unwrap();
        let value = full.project(family, ordinal, case.bytes()).unwrap();
        let expected = semantic.project(family, ordinal, case.bytes()).unwrap();
        assert_eq!(
            value.semantic().artifact_state(),
            expected.artifact_state(),
            "{family}/{ordinal}"
        );
        assert!(
            value.semantic() == &expected,
            "semantic projection differs {family}/{ordinal}"
        );
        let result = std::str::from_utf8(value.result_bytes()).unwrap();
        let resources = std::str::from_utf8(value.resource_bytes()).unwrap();
        assert!(result.contains("golden-board.m2-damage-decoder-result/v2"));
        assert!(resources.contains("golden-board.m2-observation-resources/v2"));
        assert!(resources.contains("\"kernel\":\"result-render\""));
        assert!(value.result_bytes().ends_with(b"\n"));
        assert!(value.resource_bytes().ends_with(b"\n"));
        let warm = full.project(family, ordinal, case.bytes()).unwrap();
        assert_eq!(warm.result_bytes(), value.result_bytes());
        assert_eq!(warm.resource_bytes(), value.resource_bytes());
        if family == "D7" {
            let row = full.replay(family, ordinal, case.bytes()).unwrap();
            let gb_foundation::ManifestValue::Object(row) =
                gb_foundation::validate_canonical_manifest(&row).unwrap()
            else {
                panic!("replay object");
            };
            assert_eq!(
                row["promise_result"],
                gb_foundation::ManifestValue::String("pass".into())
            );
            assert_eq!(
                row["reauthored_boundary"],
                gb_foundation::ManifestValue::Bool(false)
            );
            let gb_foundation::ManifestValue::Array(states) = &row["expected_section_states"]
            else {
                panic!("states");
            };
            assert_eq!(states.len(), expected.section_states().len());
            let mut wrong = case.bytes().to_vec();
            wrong[0] ^= 1;
            assert!(full.replay(family, ordinal, &wrong).is_err());
            assert!(full.replay(family, ordinal + 1, case.bytes()).is_err());
        }
    }
}

#[test]
fn source_oracle_scans_actual_routes_and_closes_rejection_events() {
    use gb_bootstrap::damage_oracle_v2::resources::Kernel;
    use gb_bootstrap::damage_oracle_v2::routes::{DiscoveryScanner, ScanState};
    let corpus = fixture();
    let scanner = DiscoveryScanner::new(corpus).unwrap();
    for (family, ordinal, count, state) in [
        ("D0", 0, 4, ScanState::Closed),
        ("D0", 7, 4, ScanState::Closed),
        ("D1", 0, 3, ScanState::Closed),
        ("D7", 408, 0, ScanState::Closed),
        ("D7", 413, 0, ScanState::Closed),
        ("D7", 405, 0, ScanState::ResourceLimit),
    ] {
        let observation = corpus.case(family, ordinal).unwrap();
        let audit = scanner
            .scan_owned(family, ordinal, observation.bytes())
            .unwrap();
        assert_eq!(audit.state, state, "{family}/{ordinal}");
        assert_eq!(audit.paths.len(), count, "{family}/{ordinal}");
        if state == ScanState::ResourceLimit {
            assert_eq!(audit.ledger.resource().primitive_steps, 0);
            assert_eq!(audit.ledger.row(Kernel::RecipeParse).calls, 0);
            assert!(audit.ledger.row(Kernel::ShellRead).calls > 0);
        } else if count > 0 {
            assert!(audit.ledger.resource().primitive_steps > 0);
            assert!(audit.paths.iter().all(|p| p.profile == 8 && p.width == 112));
        } else {
            assert_eq!(audit.ledger.row(Kernel::RecipeParse).calls, 4);
            assert_eq!(audit.ledger.resource().primitive_steps, 0);
        }
    }
    let donor = corpus.case("D7", 10).unwrap();
    let audit = scanner.scan_owned("D7", 10, donor.bytes()).unwrap();
    // W128 donor rows112..115 intersect the left W112 prefix as well as
    // replacing the top route; the two unaffected right/bottom routes remain.
    assert_eq!(
        audit
            .paths
            .iter()
            .filter(|p| p.profile == 8)
            .map(|p| p.sector)
            .collect::<Vec<_>>(),
        vec![1, 2]
    );
    let foreign = audit
        .paths
        .iter()
        .filter(|p| p.profile == 3)
        .collect::<Vec<_>>();
    assert_eq!(foreign.len(), 1);
    assert_eq!(foreign[0].width, 128);
    assert_eq!(
        foreign[0].hypothesis.mapping_sha256,
        "7f2f3f2a9bd9238668b3fefc78f31ae2ac4a0fa58acaab2793b24ca4d3c2369c"
    );
}
#[test]
fn clean_and_permuted_observations_establish_both_typed_streams() {
    let corpus = fixture();
    let oracle = SemanticOracleV2::new(corpus);
    let clean = corpus.case("D5", 0).unwrap();
    let value = oracle.project("D5", 0, clean.bytes()).unwrap();
    assert_eq!(value.artifact_state(), ArtifactState::Exact);
    assert_eq!(value.wrong_accepts(), 0);
    assert_eq!(value.required_stream().unwrap().len(), 42432);
    assert_eq!(value.all_stream().unwrap().len(), 55664);
    assert!(
        value
            .section_states()
            .iter()
            .all(|(_, state)| *state == SectionState::Verified)
    );
    let permuted = corpus.case("D5", 1).unwrap();
    assert_eq!(oracle.project("D5", 1, permuted.bytes()).unwrap(), value);
}
#[test]
fn checked_malformed_content_has_transport_diagnostics_but_no_invalid_stream() {
    let corpus = fixture();
    let oracle = SemanticOracleV2::new(corpus);
    for ordinal in [0, 7, 14, 17, 20] {
        let case = corpus.case("B0", ordinal).unwrap();
        let value = oracle.project("B0", ordinal, case.bytes()).unwrap();
        assert!(value.reauthored_boundary());
        assert_eq!(value.wrong_accepts(), 1);
        assert!(value.all_stream().is_none());
        assert_eq!(value.required_stream().is_some(), matches!(ordinal, 7 | 17));
        assert_eq!(
            value.artifact_state(),
            if matches!(ordinal, 7 | 17) {
                ArtifactState::Degraded
            } else {
                ArtifactState::Failure
            }
        );
    }
}
#[test]
fn group_conflict_does_not_rewrite_individually_checked_lane_diagnostics() {
    let corpus = fixture();
    let oracle = SemanticOracleV2::new(corpus);
    let case = corpus.case("D7", 16).unwrap();
    let value = oracle.project("D7", 16, case.bytes()).unwrap();
    assert_eq!(value.artifact_state(), ArtifactState::Failure);
    assert_eq!(value.section_states()[0], (1, SectionState::Corrupt));
    assert!(
        value.fragments()[..5]
            .iter()
            .all(|row| row.common_block_sha256 != "0".repeat(64))
    );
    assert_ne!(
        value.fragments()[0].common_block_sha256,
        value.fragments()[1].common_block_sha256
    );
}
#[test]
fn owned_resource_and_framing_failures_have_no_partial_semantic_availability() {
    let corpus = fixture();
    let oracle = SemanticOracleV2::new(corpus);
    for n in [405, 406, 407, 408, 413] {
        let case = corpus.case("D7", n).unwrap();
        let value = oracle.project("D7", n, case.bytes()).unwrap();
        assert_eq!(
            value.artifact_state(),
            if n < 407 {
                ArtifactState::ResourceLimit
            } else {
                ArtifactState::Failure
            }
        );
        assert!(value.sections().is_empty());
        assert!(value.fragments().is_empty());
        assert!(value.required_stream().is_none());
        assert!(value.all_stream().is_none());
    }
    let case = corpus.case("D5", 0).unwrap();
    let mut wrong = case.bytes().to_vec();
    wrong[10] ^= 1;
    assert!(oracle.project("D5", 0, &wrong).is_err());
}

#[test]
fn observed_transforms_erasures_and_noise_preserve_source_required_bytes() {
    let corpus = fixture();
    let oracle = SemanticOracleV2::new(corpus);
    let case = corpus.case("D5", 0).unwrap();
    let clean = oracle.project("D5", 0, case.bytes()).unwrap();
    for (family, ordinal) in [
        ("D0", 7),
        ("D0", 15),
        ("D2", 9),
        ("D3", 0),
        ("D3", 96),
        ("D6", 0),
    ] {
        let case = corpus.case(family, ordinal).unwrap();
        let actual = oracle.project(family, ordinal, case.bytes()).unwrap();
        assert_eq!(
            actual.required_stream(),
            clean.required_stream(),
            "{family}-{ordinal}"
        );
        assert_eq!(actual.wrong_accepts(), 0, "{family}-{ordinal}");
        if family == "D0" {
            assert_eq!(actual, clean)
        }
    }
}

#[test]
fn missing_bootstrap_and_foreign7_do_not_invent_content_from_source_catalog() {
    let corpus = fixture();
    let oracle = SemanticOracleV2::new(corpus);
    for n in [401, 402, 414] {
        let case = corpus.case("D7", n).unwrap();
        let value = oracle.project("D7", n, case.bytes()).unwrap();
        assert_eq!(value.artifact_state(), ArtifactState::Failure);
        assert!(value.required_stream().is_none());
        assert!(value.all_stream().is_none());
        assert_eq!(value.wrong_accepts(), 0);
        assert_eq!(
            value.section_states()[0].1,
            if n == 401 {
                SectionState::Incomplete
            } else {
                SectionState::Corrupt
            }
        );
        if n == 414 {
            assert!(
                value.fragments()[..5]
                    .iter()
                    .all(|f| f.profile_version == Some(7))
            );
        }
    }
}

#[test]
fn admitted_bootstrap_context_retains_five_physical_positions_before_inventory() {
    let corpus = fixture();
    let oracle = SemanticOracleV2::new(corpus);
    for ordinal in [0, 11, 16, 401, 402, 414] {
        let case = corpus.case("D7", ordinal).unwrap();
        let value = oracle.project("D7", ordinal, case.bytes()).unwrap();
        assert_eq!(value.fragments().len(), 1908, "D7-{ordinal}");
        for (index, row) in value.fragments()[..5].iter().enumerate() {
            assert_eq!(row.input_id, index as u32 + 1);
            assert_eq!(
                (row.replica_index, row.physical_replica_count),
                (index as u16, 5),
                "D7-{ordinal}"
            );
            if ordinal == 401 {
                assert_eq!(
                    (
                        row.profile_version,
                        row.section_id,
                        row.semantic_copy_id,
                        row.fragment_index
                    ),
                    (Some(8), 1, 0, 0)
                );
                assert_eq!(row.state, gb_bootstrap::damage::FragmentState::Missing);
                assert_eq!(row.common_block_sha256, "0".repeat(64));
            }
        }
    }
}
