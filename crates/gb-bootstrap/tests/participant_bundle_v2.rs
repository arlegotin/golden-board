use gb_bootstrap::participant_bundle_v2::technical_content_query_v2;
use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
use std::sync::OnceLock;

fn compiled() -> &'static gb_slice::SliceCompilation {
    static VALUE: OnceLock<gb_slice::SliceCompilation> = OnceLock::new();
    VALUE.get_or_init(|| {
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
    })
}

#[test]
fn query_uses_checked_current_all_namespace_and_produces_a_real_position() {
    let query = technical_content_query_v2(compiled().all_stream()).unwrap();
    assert_eq!(query.position.len(), 67);
    gb_chess::validate_local(&gb_chess::decode_position(&query.position).unwrap()).unwrap();
    let V::Object(request) = validate_canonical_manifest(&query.request).unwrap() else {
        panic!("request");
    };
    assert_eq!(
        request["schema"],
        V::String("golden-board.m2-technical-content-query/v0".into())
    );
    let V::Object(expected) = validate_canonical_manifest(&query.expected).unwrap() else {
        panic!("expected");
    };
    assert_eq!(expected.len(), 3);
    let V::Object(transition) = &expected["chess_transition"] else {
        panic!("transition");
    };
    assert_eq!(transition["game_ordinal"], V::U64(0));
    assert_eq!(transition["ply_ordinal"], V::U64(0));
    assert_eq!(
        transition["resulting_position_identity"],
        V::String(
            gb_foundation::identity_hex(b"golden-board:position:v0\0", &[&query.position]).unwrap()
        )
    );
}

#[test]
fn query_rejects_missing_game_namespace_truncation_and_excess_before_lookup() {
    assert!(technical_content_query_v2(compiled().required_stream()).is_err());
    for raw in [vec![], vec![0; 3], vec![0; 1_048_577]] {
        assert!(technical_content_query_v2(&raw).is_err());
    }
    let raw = compiled().all_stream();
    assert!(technical_content_query_v2(&raw[..raw.len() - 1]).is_err());
}

#[test]
fn typed_opaque_atoms_cannot_supply_an_illegal_chess_transition() {
    use gb_content::{ContentAuthoringProjection, Record, RecordPayload as P};
    let projection = gb_content::stream_validation(compiled().all_stream()).unwrap();
    let game_binding = projection
        .records()
        .iter()
        .find_map(|r| match r.payload() {
            P::SemanticBinding {
                binding_class: 1,
                namespace_id: 2,
                semantic_code: 1,
                ..
            } => Some(r.record_id()),
            _ => None,
        })
        .unwrap();
    let records = projection
        .records()
        .iter()
        .map(|record| {
            let mut payload = record.payload().clone();
            if let P::OpaqueData {
                data_binding_ref,
                data,
            } = &mut payload
            {
                if *data_binding_ref == game_binding {
                    data[2] = 0;
                    data[3] = 0;
                }
            }
            Record::authoring(record.record_id(), payload)
        })
        .collect();
    let changed =
        gb_content::encode_content_v0(&ContentAuthoringProjection::new(0, records)).unwrap();
    gb_content::stream_validation(&changed).unwrap();
    assert!(matches!(
        technical_content_query_v2(&changed),
        Err(gb_bootstrap::participant_bundle_v2::BundleErrorV2::Chess)
    ));
}
