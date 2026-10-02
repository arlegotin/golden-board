use gb_bootstrap::boundary_kat_v2::boundary_kat_results_v2;
use gb_bootstrap::complete_damage_v2::{CompleteDamageV2, admit_complete_damage_v2};
use gb_bootstrap::damage_corpus_v2::DamageCorpusV2;
use gb_bootstrap::damage_oracle_v2::FullOracleV2;
use gb_bootstrap::static_v2::{StaticProjectionV2, build_static_projection_v2};
use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use std::sync::OnceLock;

struct Fixture {
    corpus: DamageCorpusV2,
    projection: StaticProjectionV2,
    kats: [Vec<u8>; 4],
    first: Vec<u8>,
}
fn fixture() -> &'static Fixture {
    static FIXTURE: OnceLock<Fixture> = OnceLock::new();
    FIXTURE.get_or_init(|| {
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
        let projection = build_static_projection_v2(&slice, &carrier).unwrap();
        let corpus = DamageCorpusV2::new(
            &slice,
            &carrier,
            include_bytes!("../../../spec/route-data-v0.json"),
        )
        .unwrap();
        let observed = corpus.case("D0", 0).unwrap();
        let first = FullOracleV2::new(&corpus)
            .unwrap()
            .replay("D0", 0, observed.bytes())
            .unwrap();
        let kats = boundary_kat_results_v2().unwrap().try_into().unwrap();
        Fixture {
            corpus,
            projection,
            kats,
            first,
        }
    })
}
fn modified(raw: &[u8], mutate: impl FnOnce(&mut V)) -> Vec<u8> {
    let mut value = validate_canonical_manifest(raw).unwrap();
    mutate(&mut value);
    serialize_manifest(&value).unwrap()
}
fn object(v: &mut V) -> &mut std::collections::BTreeMap<String, V> {
    let V::Object(v) = v else { panic!() };
    v
}
#[test]
fn actual_source_row_is_admitted_but_partial_or_duplicate_execution_cannot_finish() {
    let f = fixture();
    let mut writer = CompleteDamageV2::new(&f.projection, &f.corpus, f.kats.clone()).unwrap();
    let mut emitted = Vec::new();
    writer
        .push(&f.first, &mut |p, _| {
            emitted.push(p.to_owned());
            Ok(())
        })
        .unwrap();
    assert!(emitted.is_empty());
    assert!(writer.finish(&mut |_, _| Ok(())).is_err());
    let mut writer = CompleteDamageV2::new(&f.projection, &f.corpus, f.kats.clone()).unwrap();
    writer.push(&f.first, &mut |_, _| Ok(())).unwrap();
    assert!(writer.push(&f.first, &mut |_, _| Ok(())).is_err());
    assert!(writer.finish(&mut |_, _| Ok(())).is_err());
}
#[test]
fn full_rows_require_complete_catalog_exact_types_and_current_sidecar_bindings() {
    let f = fixture();
    let variants = [
        modified(&f.first, |v| {
            let V::Array(states) = object(v).get_mut("expected_section_states").unwrap() else {
                panic!()
            };
            states.pop();
        }),
        modified(&f.first, |v| {
            object(v).insert("wrong_accept_count".into(), V::Bool(false));
        }),
        modified(&f.first, |v| {
            object(v).insert("promise_result".into(), V::String("fail".into()));
        }),
        modified(&f.first, |v| {
            object(object(v).get_mut("resource_projection").unwrap())
                .insert("result_sha256".into(), V::String("0".repeat(64)));
        }),
        modified(&f.first, |v| {
            object(object(v).get_mut("observation").unwrap())
                .insert("case_ordinal".into(), V::U64(1));
        }),
    ];
    for raw in variants {
        let mut writer = CompleteDamageV2::new(&f.projection, &f.corpus, f.kats.clone()).unwrap();
        assert!(writer.push(&raw, &mut |_, _| Ok(())).is_err());
        assert!(writer.push(&f.first, &mut |_, _| Ok(())).is_err());
    }
}
#[test]
fn kat_receipts_are_closed_ordered_and_retained_admission_rejects_absent_roots() {
    let f = fixture();
    let mut bad = f.kats.clone();
    bad.swap(0, 1);
    assert!(CompleteDamageV2::new(&f.projection, &f.corpus, bad).is_err());
    let mut bad = f.kats.clone();
    bad[0] = modified(&bad[0], |v| {
        object(v).insert("saved_pass".into(), V::Bool(true));
    });
    assert!(CompleteDamageV2::new(&f.projection, &f.corpus, bad).is_err());
    assert!(
        admit_complete_damage_v2(
            &f.projection,
            &f.corpus,
            |_| panic!("an unlisted name must not be read"),
            &[]
        )
        .is_err()
    );
}
