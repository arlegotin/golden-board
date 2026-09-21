use gb_bootstrap::physical_v2::build_physical_evidence_v2;
use gb_foundation::{
    ManifestValue as V, identity_hex, serialize_manifest, validate_canonical_manifest,
};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::sync::OnceLock;
fn digest(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn fixture() -> &'static [Vec<u8>; 4] {
    static F: OnceLock<[Vec<u8>; 4]> = OnceLock::new();
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
        let p = gb_bootstrap::static_v2::build_static_projection_v2(&slice, &carrier).unwrap();
        [
            "candidate-manifest.json",
            "capacity-ledger.json",
            "ownership-ledger.json",
            "semantic-envelope.json",
        ]
        .map(|n| p.document(n).unwrap().to_vec())
    })
}
fn obj(v: &V) -> &BTreeMap<String, V> {
    if let V::Object(v) = v { v } else { panic!() }
}
fn objm(v: &mut V) -> &mut BTreeMap<String, V> {
    if let V::Object(v) = v { v } else { panic!() }
}
fn arr(v: &V) -> &[V] {
    if let V::Array(v) = v { v } else { panic!() }
}
fn arrm(v: &mut V) -> &mut Vec<V> {
    if let V::Array(v) = v { v } else { panic!() }
}
fn num(v: &V) -> u64 {
    if let V::U64(v) = v { *v } else { panic!() }
}
fn run(d: &[Vec<u8>; 4]) -> gb_bootstrap::physical_v2::PhysicalEvidenceV2 {
    build_physical_evidence_v2(&d[0], &d[1], &d[2], &d[3]).unwrap()
}
fn edit(index: usize, f: impl FnOnce(&mut V)) -> [Vec<u8>; 4] {
    let mut d = fixture().clone();
    let mut v = validate_canonical_manifest(&d[index]).unwrap();
    f(&mut v);
    d[index] = serialize_manifest(&v).unwrap();
    // Rebind the exact input DAG, never forge the expected result.
    let mut cap = validate_canonical_manifest(&d[1]).unwrap();
    objm(&mut cap).insert("semantic_envelope_sha256".into(), V::String(digest(&d[3])));
    d[1] = serialize_manifest(&cap).unwrap();
    let mut own = validate_canonical_manifest(&d[2]).unwrap();
    objm(&mut own).insert("capacity_ledger_sha256".into(), V::String(digest(&d[1])));
    d[2] = serialize_manifest(&own).unwrap();
    let mut candidate = validate_canonical_manifest(&d[0]).unwrap();
    for row in arrm(objm(&mut candidate).get_mut("files").unwrap()) {
        let r = objm(row);
        for (i, path) in [
            (1, "capacity-ledger.json"),
            (2, "ownership-ledger.json"),
            (3, "semantic-envelope.json"),
        ] {
            if r["path"] == V::String(path.into()) {
                r.insert("bytes".into(), V::U64(d[i].len() as u64));
                r.insert("sha256".into(), V::String(digest(&d[i])));
            }
        }
    }
    objm(&mut candidate).remove("manifest_identity");
    let id = identity_hex(
        b"golden-board:manifest:v0\0",
        &[&serialize_manifest(&candidate).unwrap()],
    )
    .unwrap();
    objm(&mut candidate).insert("manifest_identity".into(), V::String(id));
    d[0] = serialize_manifest(&candidate).unwrap();
    d
}
#[test]
fn source_built_inputs_produce_only_eight_complete_derived_predicates() {
    let d = fixture();
    let e = run(d);
    let v = validate_canonical_manifest(e.canonical_bytes()).unwrap();
    let o = obj(&v);
    assert_eq!(o.len(), 5);
    assert_eq!(o["scope"], V::String("physical-predicates-only".into()));
    assert!(!o.contains_key("result"));
    let rows = arr(&o["predicate_rows"]);
    assert_eq!(rows.len(), 8);
    let capacity = validate_canonical_manifest(&d[1]).unwrap();
    let ledger = obj(&obj(&capacity)["ledger"]);
    let ownership = validate_canonical_manifest(&d[2]).unwrap();
    let own = obj(&ownership);
    let s = num(&own["side"]);
    let w = num(&own["shell_width"]);
    let p = (s - 2 * w).pow(2);
    let q = p / 1728;
    let g1 = num(&ledger["factor_1_group_count"]);
    let g2 = num(&ledger["factor_2_group_count"]);
    let g5 = num(&ledger["factor_5_group_count"]);
    let deps: u64 = arr(&obj(&capacity)["section_rows"])
        .iter()
        .map(|r| arr(&arr(r)[8]).len() as u64)
        .sum();
    let expected = [
        p,
        s * s,
        s * s - p,
        1728 * q,
        s * s,
        1728 * (g2 + 10 * g5),
        6 * (256 + 5 * q),
        g1 + g2 + g5 + deps + 5,
    ];
    for (r, n) in rows.iter().zip(expected) {
        let r = obj(r);
        assert_eq!(num(&r["witness_count"]), n);
        assert_eq!(num(&r["minimum_surviving_count"]), 1);
        assert_eq!(num(&r["violation_count"]), 0, "{r:?}");
        assert_eq!(r["result"], V::String("pass".into()));
    }
    assert_eq!(e.canonical_bytes(), serialize_manifest(&v).unwrap());
}
#[test]
fn malformed_inputs_and_unbound_changes_reject() {
    let d = fixture();
    for bad in [b"{}".as_slice(), b"[]", b"true", b"{\"schema\":true}"] {
        assert!(build_physical_evidence_v2(bad, &d[1], &d[2], &d[3]).is_err());
    }
    let changed = edit(2, |v| {
        objm(v).insert("side".into(), V::Bool(true));
    });
    assert!(
        build_physical_evidence_v2(&changed[0], &changed[1], &changed[2], &changed[3]).is_err()
    );
    let changed = edit(1, |v| {
        objm(v).insert("extra".into(), V::U64(0));
    });
    assert!(
        build_physical_evidence_v2(&changed[0], &changed[1], &changed[2], &changed[3]).is_err()
    );
    let changed = edit(2, |v| {
        objm(v).insert("cell_table_sha256".into(), V::String("0".repeat(64)));
    });
    assert!(build_physical_evidence_v2(&d[0], &d[1], &changed[2], &d[3]).is_err());
}
#[test]
fn hash_row_factor_and_byte_contradictions_count_instead_of_disappearing() {
    let base = run(fixture());
    for (index, kind) in [(2, 0), (2, 1), (1, 2), (1, 3)] {
        let changed = edit(index, |v| match kind {
            0 => {
                objm(v).insert("cell_table_sha256".into(), V::String("0".repeat(64)));
            }
            1 => {
                let rows = arrm(objm(v).get_mut("unit_rows").unwrap());
                arrm(&mut rows[0])[1] = V::String("0".repeat(64));
            }
            2 => {
                let rows = arrm(objm(v).get_mut("section_rows").unwrap());
                arrm(&mut rows[0])[7] = V::String("load:0".into());
            }
            _ => {
                let l = objm(objm(v).get_mut("ledger").unwrap());
                let n = num(&l["replicated_payload_bytes"]);
                l.insert("replicated_payload_bytes".into(), V::U64(n + 1));
            }
        });
        let result = run(&changed);
        assert_eq!(
            result.rows()[6].violation_count(),
            0,
            "metadata-only mutation {kind}"
        );
        assert_eq!(result.rows().len(), 8);
        assert_eq!(
            result
                .rows()
                .iter()
                .map(|r| r.witness_count())
                .collect::<Vec<_>>(),
            base.rows()
                .iter()
                .map(|r| r.witness_count())
                .collect::<Vec<_>>()
        );
        let expected_row = match kind {
            0 => 1,
            1 | 2 => 3,
            _ => 7,
        };
        assert!(
            result.rows()[expected_row].violation_count() > 0,
            "kind {kind}"
        );
    }
}

#[test]
fn typed_mapping_and_dependency_contradictions_remain_counted_evidence() {
    for key in ["unit_multiplier", "unit_inverse_multiplier", "offset"] {
        let changed = edit(2, |v| {
            let mapping = objm(objm(v).get_mut("mapping").unwrap());
            let value = if key == "offset" {
                num(&mapping[key]) + 1
            } else {
                1
            };
            mapping.insert(key.into(), V::U64(value));
        });
        let evidence = run(&changed);
        assert_eq!(evidence.rows().len(), 8);
        assert!(evidence.rows()[0].violation_count() > 0, "{key}");
    }
    let changed = edit(1, |v| {
        let rows = arrm(objm(v).get_mut("section_rows").unwrap());
        let row = rows.iter_mut().find(|r| num(&arr(r)[0]) == 2).unwrap();
        arrm(&mut arrm(row)[8])[0] = V::U64(4_000_000_000);
    });
    let evidence = run(&changed);
    assert!(evidence.rows()[7].violation_count() > 0);
    assert_eq!(evidence.rows()[3].violation_count(), 0);
}

#[test]
fn missing_group_members_cannot_shrink_witness_populations() {
    let base = run(fixture());
    for column in [1usize, 3, 5] {
        let changed = edit(1, |v| {
            let rows = arrm(objm(v).get_mut("unit_rows").unwrap());
            let first = arrm(&mut rows[0]);
            first[column] = V::U64(match column {
                1 => 4_000_000_000,
                3 => 60000,
                _ => 1,
            });
        });
        let bad = run(&changed);
        assert_eq!(
            base.rows()
                .iter()
                .map(|r| r.witness_count())
                .collect::<Vec<_>>(),
            bad.rows()
                .iter()
                .map(|r| r.witness_count())
                .collect::<Vec<_>>()
        );
        assert!(bad.rows()[3].violation_count() > 0);
        assert!(bad.rows()[7].violation_count() > 0);
    }
}

#[test]
fn capacity_factor_claim_cannot_remove_semantically_owned_lane_pairs() {
    let base = run(fixture());
    let changed = edit(1, |v| {
        let first = &mut arrm(objm(v).get_mut("section_rows").unwrap())[0];
        arrm(first)[6] = V::U64(1);
    });
    let evidence = run(&changed);
    assert_eq!(
        base.rows()
            .iter()
            .map(|r| r.witness_count())
            .collect::<Vec<_>>(),
        evidence
            .rows()
            .iter()
            .map(|r| r.witness_count())
            .collect::<Vec<_>>()
    );
    assert!(evidence.rows()[3].violation_count() > 0);
    assert!(evidence.rows()[7].violation_count() > 0);
}

#[test]
fn nonunique_replica_member_keeps_all_pairs_and_marks_every_affected_bit() {
    let changed = edit(1, |v| {
        let rows = arrm(objm(v).get_mut("unit_rows").unwrap());
        arrm(&mut rows[1])[4] = V::U64(0);
    });
    let evidence = run(&changed);
    // Replica 0 now has two members and replica 1 none: seven of C(5,2)
    // pairs have an absent/nonunique endpoint, for all1728 corresponding bits.
    assert_eq!(evidence.rows()[5].violation_count(), 7 * 1728);
}

#[test]
fn shell_class_ranges_and_individual_class_totals_are_counted() {
    let crossed = edit(2, |v| {
        let sectors = arrm(objm(v).get_mut("shell_rows").unwrap());
        let spans = arrm(&mut arrm(&mut sectors[0])[5]);
        let index = spans
            .iter()
            .position(|r| arr(r)[2] == V::String("headroom".into()))
            .unwrap();
        let moved = spans.remove(index);
        spans.insert(0, moved);
        let mut offset = 0;
        for row in spans {
            let r = arrm(row);
            r[0] = V::U64(offset);
            offset += num(&r[1]);
        }
    });
    assert_eq!(run(&crossed).rows()[2].violation_count(), 1);
    let mismatch = edit(1, |v| {
        let ledger = objm(objm(v).get_mut("ledger").unwrap());
        let first = num(&ledger["shell_instruction_cells"]);
        let second = num(&ledger["shell_example_cells"]);
        ledger.insert("shell_instruction_cells".into(), V::U64(first + 1));
        ledger.insert("shell_example_cells".into(), V::U64(second - 1));
    });
    assert_eq!(run(&mismatch).rows()[4].violation_count(), 2);
}
#[test]
fn dependency_deletion_cannot_remove_expected_edge_witnesses() {
    let baseline = run(fixture());
    let changed = edit(1, |v| {
        let rows = arrm(objm(v).get_mut("section_rows").unwrap());
        let row = rows.iter_mut().find(|r| num(&arr(r)[0]) == 2).unwrap();
        arrm(&mut arrm(row)[8]).pop();
    });
    let result = run(&changed);
    assert_eq!(
        result.rows()[7].witness_count(),
        baseline.rows()[7].witness_count()
    );
    assert_eq!(result.rows()[7].violation_count(), 2);
    assert_eq!(result.rows()[3].violation_count(), 0);
}

#[test]
fn wrong_existing_tier_targets_count_three_expected_edges_and_one_global_violation() {
    let baseline = run(fixture());
    let changed = edit(1, |v| {
        let rows = arrm(objm(v).get_mut("section_rows").unwrap());
        let row = rows.iter_mut().find(|r| num(&arr(r)[0]) == 2).unwrap();
        arrm(row)[8] = V::Array([100, 101, 102].into_iter().map(V::U64).collect());
    });
    let result = run(&changed);
    assert_eq!(
        result.rows()[7].witness_count(),
        baseline.rows()[7].witness_count()
    );
    assert_eq!(result.rows()[7].violation_count(), 4);
    assert_eq!(result.rows()[3].violation_count(), 0);
}
