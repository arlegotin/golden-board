use gb_bootstrap::complete_damage_v2::CompleteDamageError;
use gb_bootstrap::independence_v2::{IndependenceV2Error, build_complete_independence_v2};
use gb_bootstrap::recovery_provenance_v2::RecoveryProvenanceInputs;
use std::sync::OnceLock;

struct Fixture {
    carrier: gb_bootstrap::carrier_v2::Carrier,
    projection: gb_bootstrap::static_v2::StaticProjectionV2,
    corpus: gb_bootstrap::damage_corpus_v2::DamageCorpusV2,
}
impl Fixture {
    fn inputs(&self) -> RecoveryProvenanceInputs<'_> {
        RecoveryProvenanceInputs {
            carrier: self.carrier.packed_bytes(),
            candidate_manifest: self.projection.document("candidate-manifest.json").unwrap(),
            capacity_ledger: self.projection.document("capacity-ledger.json").unwrap(),
            ownership_ledger: self.projection.document("ownership-ledger.json").unwrap(),
            semantic_envelope: self.projection.document("semantic-envelope.json").unwrap(),
            profile_policy: include_bytes!("../../../spec/profile-policy-v2.toml"),
            profile_limits: include_bytes!("../../../spec/profile-limits-v2.toml"),
            damage_policy: include_bytes!("../../../spec/damage-policy-v2.toml"),
        }
    }
}
fn fixture() -> &'static Fixture {
    static F: OnceLock<Fixture> = OnceLock::new();
    F.get_or_init(|| {
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
        let projection =
            gb_bootstrap::static_v2::build_static_projection_v2(&slice, &carrier).unwrap();
        let corpus = gb_bootstrap::damage_corpus_v2::DamageCorpusV2::new(
            &slice,
            &carrier,
            include_bytes!("../../../spec/route-data-v0.json"),
        )
        .unwrap();
        Fixture {
            carrier,
            projection,
            corpus,
        }
    })
}
#[test]
fn no_saved_premise_or_partial_damage_tree_can_construct_a_proof() {
    let f = fixture();
    let mut changed = f.inputs();
    changed.candidate_manifest = b"{}\n";
    let mut called = false;
    assert_eq!(
        build_complete_independence_v2(
            changed,
            &f.projection,
            &f.corpus,
            |_| {
                called = true;
                Err(CompleteDamageError::Binding)
            },
            &[]
        )
        .unwrap_err(),
        IndependenceV2Error::Binding
    );
    assert!(
        !called,
        "raw/static disagreement must reject before reading damage"
    );
    assert_eq!(
        build_complete_independence_v2(
            f.inputs(),
            &f.projection,
            &f.corpus,
            |_| Err(CompleteDamageError::Binding),
            &[]
        )
        .unwrap_err(),
        IndependenceV2Error::Damage
    );
}

/// This test requires a current complete independently generated damage tree.
/// It never synthesizes a passing tree, and retained admission is not fresh
/// damage execution. The actual wrapper regenerates physical/recovery premises.
#[test]
#[ignore = "requires GB_COMPLETE_DAMAGE_V2_TREE from a fresh complete producer"]
fn complete_tree_regenerates_physical_and_actual_recovery_premises() {
    let f = fixture();
    let root = std::path::PathBuf::from(
        std::env::var_os("GB_COMPLETE_DAMAGE_V2_TREE").expect("fresh tree path"),
    );
    let mut names = vec!["resource-limits.json".to_owned()];
    let mut queue = vec![root.join("damage")];
    let mut directories = 0;
    while let Some(path) = queue.pop() {
        directories += 1;
        assert!(directories <= 4096);
        for entry in std::fs::read_dir(path).unwrap() {
            let entry = entry.unwrap();
            let kind = entry.file_type().unwrap();
            assert!(!kind.is_symlink());
            if kind.is_dir() {
                queue.push(entry.path())
            } else {
                assert!(kind.is_file());
                names.push(
                    entry
                        .path()
                        .strip_prefix(&root)
                        .unwrap()
                        .to_str()
                        .unwrap()
                        .to_owned(),
                );
                assert!(names.len() <= 4096);
            }
        }
    }
    names.sort();
    let proof = build_complete_independence_v2(
        f.inputs(),
        &f.projection,
        &f.corpus,
        |name| {
            let path = root.join(name);
            let meta =
                std::fs::symlink_metadata(&path).map_err(|_| CompleteDamageError::Binding)?;
            if !meta.is_file() || meta.len() > 1_048_576 {
                return Err(CompleteDamageError::Bounds);
            }
            std::fs::read(path).map_err(|_| CompleteDamageError::Binding)
        },
        &names,
    )
    .unwrap();
    assert!(proof.passed());
    assert_eq!(proof.physical_evidence().rows().len(), 8);
    assert_eq!(proof.recovery_provenance().bodies().len(), 78);
    assert_eq!(proof.recovery_provenance().required_stream().len(), 42432);
    assert_eq!(proof.recovery_provenance().all_stream().len(), 55664);
    assert_eq!(proof.recovery_provenance().first_use().len(), 129784);
}
