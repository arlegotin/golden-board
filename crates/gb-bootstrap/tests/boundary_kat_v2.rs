use gb_bootstrap::boundary_kat_v2::{KAT_IDS, boundary_kat_result_v2, boundary_kat_results_v2};
use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
#[test]
fn four_current_receiver_boundaries_emit_exact_ordered_receipts() {
    let rows = boundary_kat_results_v2().unwrap();
    assert_eq!(rows.len(), 4);
    for (ordinal, raw) in rows.iter().enumerate() {
        let V::Object(value) = validate_canonical_manifest(raw).unwrap() else {
            panic!()
        };
        assert_eq!(value.len(), 3);
        assert_eq!(
            value["schema"],
            V::String("golden-board.m2-boundary-kat-result/v2".into())
        );
        assert_eq!(value["kat_id"], V::String(KAT_IDS[ordinal].into()));
        assert_eq!(value["result"], V::String("pass".into()));
        assert_eq!(*raw, boundary_kat_result_v2(ordinal).unwrap());
    }
}
#[test]
fn unknown_ordinals_never_choose_default_fixture() {
    for ordinal in [4, 255, usize::MAX] {
        assert!(boundary_kat_result_v2(ordinal).is_err());
    }
}
