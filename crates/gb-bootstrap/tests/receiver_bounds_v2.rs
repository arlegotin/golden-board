use std::collections::BTreeMap;

use gb_bootstrap::receiver_bounds_v2::{
    ReceiverBoundSources, admit_resource_limits_v2, derive_receiver_bounds_v2,
};
use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use sha2::{Digest, Sha256};

fn object(v: &V) -> &BTreeMap<String, V> {
    match v {
        V::Object(v) => v,
        _ => panic!("object"),
    }
}
fn object_mut(v: &mut V) -> &mut BTreeMap<String, V> {
    match v {
        V::Object(v) => v,
        _ => panic!("object"),
    }
}
fn array(v: &V) -> &[V] {
    match v {
        V::Array(v) => v,
        _ => panic!("array"),
    }
}
fn array_mut(v: &mut V) -> &mut Vec<V> {
    match v {
        V::Array(v) => v,
        _ => panic!("array"),
    }
}
fn number(v: &V) -> u64 {
    match v {
        V::U64(v) => *v,
        _ => panic!("number"),
    }
}
fn document() -> V {
    validate_canonical_manifest(
        &derive_receiver_bounds_v2(ReceiverBoundSources::default()).unwrap(),
    )
    .unwrap()
}
fn measured() -> V {
    let bounds = document();
    let mut owners = object(&object(&bounds)["source_owners"]).clone();
    owners.remove("spec/receiver-bounds-v2.md");
    V::Object(BTreeMap::from([
        (
            "schema".into(),
            V::String("golden-board.m2-resource-limits/v2".into()),
        ),
        ("corpus_sha256".into(), V::String("1".repeat(64))),
        ("case_count".into(), V::U64(1)),
        ("case_resources_sha256".into(), V::String("2".repeat(64))),
        ("source_owners".into(), V::Object(owners)),
        (
            "maximum_resource".into(),
            object(&bounds)["maximum_resource"].clone(),
        ),
        (
            "adapter_maxima".into(),
            object(&bounds)["adapter_bounds"].clone(),
        ),
    ]))
}
fn admits(v: &V) -> bool {
    admit_resource_limits_v2(
        &serialize_manifest(v).unwrap(),
        ReceiverBoundSources::default(),
    )
    .is_ok()
}

#[test]
fn source_only_document_is_closed_canonical_and_binds_all_five_owners() {
    let sources = ReceiverBoundSources::default();
    let raw = derive_receiver_bounds_v2(sources).unwrap();
    let doc = validate_canonical_manifest(&raw).unwrap();
    assert_eq!(serialize_manifest(&doc).unwrap(), raw);
    let value = object(&doc);
    assert_eq!(value.len(), 6);
    assert_eq!(
        value["schema"],
        V::String("golden-board.m2-receiver-bounds/v2".into())
    );
    let owners = object(&value["source_owners"]);
    assert_eq!(owners.len(), 5);
    for (path, bytes) in [
        ("spec/profile-policy-v2.toml", sources.profile_policy),
        ("spec/profile-limits-v2.toml", sources.profile_limits),
        ("spec/damage-policy-v2.toml", sources.damage_policy),
        (
            "spec/resource-accounting-v2.md",
            sources.resource_accounting,
        ),
        ("spec/receiver-bounds-v2.md", sources.receiver_bounds),
    ] {
        assert_eq!(
            owners[path],
            V::String(format!("{:x}", Sha256::digest(bytes)))
        );
    }
    let terms = object(&value["derivation"]);
    assert_eq!(number(&terms["Q"]), 2427);
    assert_eq!(number(&terms["E"]), 32790);
    assert_eq!(number(&terms["Ea"]), 1048576);
    assert!(number(&terms["El"]) > u64::from(u32::MAX));
    assert_eq!(array(&value["adapter_bounds"]).len(), 22);
}

#[test]
fn malformed_pre_admission_shapes_are_covered_without_using_measured_maxima() {
    let doc = document();
    let rows = array(&object(&doc)["adapter_bounds"]);
    let row = |name: &str| -> &BTreeMap<String, V> {
        rows.iter()
            .map(object)
            .find(|r| r["kernel"] == V::String(name.into()))
            .unwrap()
    };
    // A short carried program can declare a large output before equality fails.
    assert!(number(&row("route-example")["peak_workspace_bytes"]) >= 64 * 1048576 + 8 * 128);
    // All62 active calls fit within the unchanged256-record policy ceiling.
    let routes = number(&object(&object(&doc)["derivation"])["A"]);
    assert_eq!(number(&row("route-example")["calls"]), routes * 259);
    assert!(number(&row("route-example")["calls"]) >= routes * 62);
    // Generic checked inventory payloads may exceed valid inventory limits.
    assert!(number(&row("inventory")["peak_workspace_bytes"]) >= 16 * 32768);
    // An incomplete common copy can advertise a full neutral envelope.
    assert!(number(&row("section-assembly")["peak_workspace_bytes"]) >= 1048576 + 24 * 2427);
    // Foreign entries retain u32 declared payloads before layout rejection.
    assert!(
        number(&row("group-layout")["peak_workspace_bytes"])
            >= 128 * 4096 * u64::from(u32::MAX).div_ceil(157)
    );
    let local = rows
        .iter()
        .map(|r| number(&object(r)["peak_workspace_bytes"]))
        .max()
        .unwrap();
    assert!(
        number(&object(&object(&doc)["maximum_resource"])["peak_scratch_bytes"]) > local + 16777216
    );
}

#[test]
fn source_changes_and_measured_shape_or_owner_drift_reject() {
    let source = ReceiverBoundSources::default();
    let mut changed = source.profile_limits.to_vec();
    changed.extend_from_slice(b"\n");
    assert!(
        derive_receiver_bounds_v2(ReceiverBoundSources {
            profile_limits: &changed,
            ..source
        })
        .is_err()
    );
    assert!(
        derive_receiver_bounds_v2(ReceiverBoundSources {
            receiver_bounds: b"",
            ..source
        })
        .is_err()
    );
    let good = measured();
    assert!(admits(&good));
    let mut bad = good.clone();
    object_mut(&mut bad).insert("self_hash".into(), V::String("0".repeat(64)));
    assert!(!admits(&bad));
    for count in [0, 65536] {
        let mut bad = good.clone();
        object_mut(&mut bad).insert("case_count".into(), V::U64(count));
        assert!(!admits(&bad));
    }
    let mut bad = good.clone();
    object_mut(&mut bad).insert("case_count".into(), V::Bool(true));
    assert!(!admits(&bad));
    let mut bad = good.clone();
    object_mut(object_mut(&mut bad).get_mut("source_owners").unwrap()).insert(
        "spec/profile-policy-v2.toml".into(),
        V::String("0".repeat(64)),
    );
    assert!(!admits(&bad));
    let mut bad = good.clone();
    array_mut(object_mut(&mut bad).get_mut("adapter_maxima").unwrap()).swap(0, 1);
    assert!(!admits(&bad));
    let mut raw = serialize_manifest(&good).unwrap();
    raw.pop();
    assert!(admit_resource_limits_v2(&raw, source).is_err());
}

#[test]
fn each_resource_and_adapter_component_has_an_independent_inclusive_bound() {
    let good = measured();
    for field in ["section_attempts", "primitive_steps", "peak_scratch_bytes"] {
        let mut bad = good.clone();
        let fields = object_mut(object_mut(&mut bad).get_mut("maximum_resource").unwrap());
        let value = number(&fields[field]);
        fields.insert(field.into(), V::U64(value.checked_add(1).unwrap()));
        assert!(!admits(&bad), "{field}");
        object_mut(object_mut(&mut bad).get_mut("maximum_resource").unwrap())
            .insert(field.into(), V::Bool(false));
        assert!(!admits(&bad));
    }
    for index in 0..22 {
        for field in ["calls", "reference_input_units", "peak_workspace_bytes"] {
            let mut bad = good.clone();
            let rows = array_mut(object_mut(&mut bad).get_mut("adapter_maxima").unwrap());
            let fields = object_mut(&mut rows[index]);
            let value = number(&fields[field]);
            fields.insert(field.into(), V::U64(value.checked_add(1).unwrap()));
            assert!(!admits(&bad), "row {index} {field}");
        }
    }
}
