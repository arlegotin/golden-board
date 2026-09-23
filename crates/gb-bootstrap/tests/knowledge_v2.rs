use gb_bootstrap::knowledge_v2::{
    KnowledgeInputs, build_knowledge_use_v2, validate_knowledge_use_v2,
};
use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use std::collections::BTreeMap;
use std::sync::OnceLock;

struct Fixture {
    prefixes: [Vec<u8>; 4],
    required: Vec<u8>,
    all: Vec<u8>,
    bodies: BTreeMap<u32, Vec<u8>>,
}
impl Fixture {
    fn inputs(&self) -> KnowledgeInputs<'_> {
        KnowledgeInputs {
            prefixes: self.prefixes.each_ref().map(Vec::as_slice),
            side: 2048,
            width: 112,
            required_stream: &self.required,
            all_stream: &self.all,
            body_payloads: &self.bodies,
        }
    }
}
// Source constructors are test setup only. The production evidence API receives
// immutable observations and cannot infer whether the caller actually acquired them.
fn fixture() -> &'static Fixture {
    static VALUE: OnceLock<Fixture> = OnceLock::new();
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
        let all = slice.all_stream().to_vec();
        let mut frames = BTreeMap::new();
        let mut at = 4;
        while at < all.len() {
            let n = 8 + u32::from_be_bytes(all[at + 4..at + 8].try_into().unwrap()) as usize;
            let id = u16::from_be_bytes(all[at..at + 2].try_into().unwrap());
            frames.insert(id, &all[at..at + n]);
            at += n;
        }
        let bodies = slice
            .assignments()
            .iter()
            .filter(|a| matches!(a.section_id(), 100 | 200))
            .map(|a| {
                (
                    u32::from(a.section_id()),
                    a.record_ids()
                        .iter()
                        .flat_map(|id| frames[id].iter().copied())
                        .collect(),
                )
            })
            .collect();
        Fixture {
            prefixes: gb_bootstrap::route_v2::build_route_prefixes(&slice).unwrap(),
            required: slice.required_stream().to_vec(),
            all,
            bodies,
        }
    })
}
fn proof() -> &'static Vec<u8> {
    static RAW: OnceLock<Vec<u8>> = OnceLock::new();
    RAW.get_or_init(|| build_knowledge_use_v2(fixture().inputs()).unwrap())
}
fn object(value: &V) -> &BTreeMap<String, V> {
    match value {
        V::Object(v) => v,
        _ => panic!("object"),
    }
}
fn array(value: &V) -> &[V] {
    match value {
        V::Array(v) => v,
        _ => panic!("array"),
    }
}

#[test]
fn complete_proof_has_observed_spans_and_distinct_rejection_classes() {
    let raw = proof();
    let value = validate_canonical_manifest(raw).unwrap();
    let root = object(&value);
    assert_eq!(root.len(), 9);
    assert_eq!(
        root["scope"],
        V::String("carried-finite-use-and-ablation-development".into())
    );
    assert_eq!(
        root["topological_order"],
        V::Array((1..=12).map(V::U64).collect())
    );
    assert_eq!(array(&root["repair_coverage"]).len(), 11);
    let routes = array(&root["route_rows"]);
    assert_eq!(routes.len(), 4);
    for (sector, row) in routes.iter().enumerate() {
        let row = object(row);
        let frames = array(&row["record_rows"]);
        assert_eq!(frames.len(), 48);
        assert_eq!(array(&row["fact_rows"]).len(), 12);
        let examples = array(&row["example_rows"]);
        assert_eq!(examples.len(), 33);
        assert!(examples.iter().any(|v| object(v)["status"] != V::U64(0)));
        let mut end = 64;
        for frame in frames {
            let frame = object(frame);
            assert_eq!(frame["byte_offset"], V::U64(end));
            if let V::U64(n) = frame["bytes"] {
                end += n;
            } else {
                panic!("integer")
            }
        }
        assert_eq!(end as usize, fixture().prefixes[sector].len());
    }
    let ablations = array(&root["ablation_rows"]);
    assert_eq!(ablations.len(), 96);
    for (i, row) in ablations.iter().enumerate() {
        let row = object(row);
        assert_eq!(row["sector_id"], V::U64((i / 24) as u64));
        assert_eq!(row["fact_id"], V::U64(((i % 24) / 2 + 1) as u64));
        assert_eq!(
            row["classification"],
            V::String(
                if i % 2 == 0 {
                    "record-structure"
                } else {
                    "definition-relationship"
                }
                .into()
            )
        );
        assert_eq!(row["success"], V::Bool(false));
    }
    validate_knowledge_use_v2(raw, fixture().inputs()).unwrap();
}

#[test]
fn missing_context_bad_geometry_and_unbounded_inputs_reject() {
    let f = fixture();
    for side in [0, 63, 2041, 2056] {
        assert!(build_knowledge_use_v2(KnowledgeInputs { side, ..f.inputs() }).is_err());
    }
    for width in [0, 7, 111, 136] {
        assert!(
            build_knowledge_use_v2(KnowledgeInputs {
                width,
                ..f.inputs()
            })
            .is_err()
        );
    }
    assert!(
        build_knowledge_use_v2(KnowledgeInputs {
            required_stream: &[],
            ..f.inputs()
        })
        .is_err()
    );
    let mut bodies = f.bodies.clone();
    bodies.remove(&200);
    assert!(
        build_knowledge_use_v2(KnowledgeInputs {
            body_payloads: &bodies,
            ..f.inputs()
        })
        .is_err()
    );
    bodies.insert(200, vec![0; 16385]);
    assert!(
        build_knowledge_use_v2(KnowledgeInputs {
            body_payloads: &bodies,
            ..f.inputs()
        })
        .is_err()
    );
    let too_long = vec![0; 32769];
    let mut inputs = f.inputs();
    inputs.prefixes[0] = &too_long;
    assert!(build_knowledge_use_v2(inputs).is_err());
}

#[test]
fn content_membership_and_exact_prefix_boundaries_are_not_optional() {
    let f = fixture();
    let mut bodies = f.bodies.clone();
    let body = bodies.get_mut(&100).unwrap();
    *body.last_mut().unwrap() ^= 1;
    assert!(
        build_knowledge_use_v2(KnowledgeInputs {
            body_payloads: &bodies,
            ..f.inputs()
        })
        .is_err()
    );
    let mut extra = f.prefixes[0].clone();
    extra.push(0);
    let mut inputs = f.inputs();
    inputs.prefixes[0] = &extra;
    assert!(build_knowledge_use_v2(inputs).is_err());
    let mut wrong_sector = f.inputs();
    wrong_sector.prefixes.swap(0, 1);
    assert!(build_knowledge_use_v2(wrong_sector).is_err());
}

#[test]
fn forged_missing_noncanonical_or_oversized_evidence_rejects() {
    let f = fixture();
    assert!(validate_knowledge_use_v2(b"{}\n", f.inputs()).is_err());
    assert!(validate_knowledge_use_v2(&vec![b' '; 1048577], f.inputs()).is_err());
    let mut noncanonical = proof().clone();
    noncanonical.pop();
    assert!(validate_knowledge_use_v2(&noncanonical, f.inputs()).is_err());
    let V::Object(mut value) = validate_canonical_manifest(proof()).unwrap() else {
        panic!("object")
    };
    let V::Array(rows) = value.get_mut("ablation_rows").unwrap() else {
        panic!("array")
    };
    let V::Object(row) = &mut rows[1] else {
        panic!("object")
    };
    row.insert(
        "classification".into(),
        V::String("record-structure".into()),
    );
    let changed = serialize_manifest(&V::Object(value)).unwrap();
    assert!(validate_knowledge_use_v2(&changed, f.inputs()).is_err());
}
