use std::sync::OnceLock;

use gb_bootstrap::carrier_v2::{Carrier, build_carrier};
use gb_bootstrap::static_v2::{StaticProjectionV2, build_static_projection_v2};
use gb_foundation::{
    ManifestValue as V, identity_hex, serialize_manifest, validate_canonical_manifest,
};
use sha2::{Digest, Sha256};

fn fixture() -> &'static (Carrier, StaticProjectionV2) {
    static VALUE: OnceLock<(Carrier, StaticProjectionV2)> = OnceLock::new();
    VALUE.get_or_init(|| {
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
        let carrier = build_carrier(&slice).unwrap();
        let projection = build_static_projection_v2(&slice, &carrier).unwrap();
        (carrier, projection)
    })
}

fn object(v: &V) -> &std::collections::BTreeMap<String, V> {
    match v {
        V::Object(v) => v,
        _ => panic!("expected object"),
    }
}
fn array(v: &V) -> &[V] {
    match v {
        V::Array(v) => v,
        _ => panic!("expected array"),
    }
}
fn number(v: &V) -> u64 {
    match v {
        V::U64(v) => *v,
        _ => panic!("expected integer"),
    }
}
fn text(v: &V) -> &str {
    match v {
        V::String(v) => v,
        _ => panic!("expected text"),
    }
}
fn doc(name: &str) -> V {
    validate_canonical_manifest(fixture().1.document(name).unwrap()).unwrap()
}
fn digest(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

#[test]
fn all_seven_documents_are_canonical_and_hash_dag_closes_without_self_hash() {
    let (carrier, projection) = fixture();
    assert_eq!(projection.documents().count(), 7);
    for (_, raw) in projection.documents() {
        assert!(raw.len() <= 1_048_576);
        assert_eq!(
            serialize_manifest(&validate_canonical_manifest(raw).unwrap()).unwrap(),
            raw
        );
    }
    let candidate = doc("candidate-manifest.json");
    let candidate = object(&candidate);
    assert_eq!(text(&candidate["status"]), "static-projection-only");
    let mut omitted = candidate.clone();
    let identity = omitted.remove("manifest_identity").unwrap();
    assert_eq!(
        text(&identity),
        identity_hex(
            b"golden-board:manifest:v0\0",
            &[&serialize_manifest(&V::Object(omitted)).unwrap()]
        )
        .unwrap()
    );
    let files = array(&candidate["files"]);
    assert_eq!(files.len(), 11);
    for row in files {
        let row = object(row);
        let name = text(&row["path"]);
        assert_ne!(name, "candidate-manifest.json");
        if name == "carrier.bin" {
            assert_eq!(text(&row["sha256"]), digest(carrier.packed_bytes()));
            assert_eq!(number(&row["bytes"]), carrier.packed_bytes().len() as u64);
        } else if let Some(bytes) = projection.document(name) {
            assert_eq!(text(&row["sha256"]), digest(bytes));
            assert_eq!(number(&row["bytes"]), bytes.len() as u64);
        }
    }
}

#[test]
fn every_capacity_byte_and_owned_cell_is_charged() {
    let (carrier, _) = fixture();
    let capacity = doc("capacity-ledger.json");
    let ledger = object(&object(&capacity)["ledger"]);
    let transport = [
        "replicated_payload_bytes",
        "envelope_header_bytes",
        "section_check_bytes",
        "fragment_header_bytes",
        "fragment_zero_pad_bytes",
        "local_check_bytes",
        "transport_pad_bytes",
        "parity_bytes",
    ]
    .iter()
    .map(|k| number(&ledger[*k]))
    .sum::<u64>();
    assert_eq!(transport, 216 * carrier.unit_count());
    assert_eq!(number(&ledger["encoded_transport_bytes"]), transport);
    let cells = [
        "real_protected_cells",
        "capacity_probe_cells",
        "reserve_probe_cells",
        "load_probe_cells",
        "shell_instruction_cells",
        "shell_example_cells",
        "shell_recipe_cells",
        "shell_headroom_cells",
        "shell_fixed_pad_cells",
        "interior_fixed_pad_cells",
    ]
    .iter()
    .map(|k| number(&ledger[*k]))
    .sum::<u64>();
    assert_eq!(cells, u64::from(carrier.side()).pow(2));
    assert_eq!(number(&ledger["unused_cells"]), 0);
    let units = array(&object(&capacity)["unit_rows"]);
    assert_eq!(units.len() as u64, carrier.unit_count());
    for (index, row) in units.iter().enumerate() {
        assert_eq!(number(&array(row)[0]), index as u64 + 1);
        assert_eq!(number(&array(row)[2]), 0);
    }
    let ownership = doc("ownership-ledger.json");
    let pad = object(&object(&ownership)["interior_fixed_pad"]);
    assert_eq!(
        text(&pad["fill_order"]),
        "affine-images-of-ascending-logical-tail"
    );
    assert_eq!(
        number(&pad["logical_bit_first"]),
        1728 * carrier.unit_count()
    );
}

#[test]
fn search_and_declared_resources_keep_their_bounded_static_scope() {
    let (carrier, _) = fixture();
    let geometry = doc("geometry-search.json");
    let rows = array(&object(&geometry)["rows"]);
    assert_eq!(rows.len(), carrier.search_ledger().len());
    assert_eq!(text(&array(rows.last().unwrap())[2]), "fit");
    assert!(
        rows[..rows.len() - 1]
            .iter()
            .all(|r| text(&array(r)[2]) != "fit")
    );
    let limits = doc("static-limits.json");
    let limits = object(&limits);
    assert_eq!(text(&limits["scope"]), "static-construction-only");
    let declared = object(&limits["declared_transport"]);
    assert_eq!(
        text(&declared["scope"]),
        "one-pass-complete-inventory-groups"
    );
    let selected = object(&limits["selected_manifestation"]);
    let groups = array(&selected["factor_group_counts"]);
    let repeated = number(&groups[1]) + number(&groups[2]);
    assert_eq!(
        number(&declared["eh_decoder_calls"]),
        24 * (carrier.unit_count() + repeated)
    );
    assert_eq!(
        number(&declared["repetition_symbol_calls"]),
        1728 * repeated
    );
    assert_eq!(
        number(&selected["carrier_file_bytes"]),
        number(&selected["carrier_bytes"]) + 4
    );
    assert!(number(&selected["carrier_bytes"]) <= 524288);
    let semantic = object(&limits["semantic_capacity"]);
    assert_eq!(number(&semantic["authoring_payload_bytes"]), 105277);
    let before = number(&semantic["content_capacity_before_reserve_bytes"]);
    assert_eq!(
        number(&semantic["reserve_payload_bytes"]),
        382.max(before.div_ceil(19))
    );
    let semantic = doc("semantic-envelope.json");
    for row in array(&object(&semantic)["bucket_rows"]) {
        let row = array(row);
        assert_eq!(
            text(&row[2]),
            match text(&row[1]) {
                "core0" | "core1" | "core2" => "replicated-core0-2",
                "core3" | "core4" => "nonreplicated-core3-4",
                tier => panic!("unexpected neutral tier {tier}"),
            }
        );
    }
}
