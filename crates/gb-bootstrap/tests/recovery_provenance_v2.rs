use gb_bootstrap::recovery_provenance_v2::{
    RecoveryProvenanceInputs, build_recovery_provenance_v2, validate_recovery_provenance_v2,
};
use gb_foundation::{
    ManifestValue as V, identity_hex, serialize_manifest, validate_canonical_manifest,
};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::sync::OnceLock;

fn fixture() -> &'static [Vec<u8>; 5] {
    static F: OnceLock<[Vec<u8>; 5]> = OnceLock::new();
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
            carrier.packed_bytes().to_vec(),
            p.document("candidate-manifest.json").unwrap().to_vec(),
            p.document("capacity-ledger.json").unwrap().to_vec(),
            p.document("ownership-ledger.json").unwrap().to_vec(),
            p.document("semantic-envelope.json").unwrap().to_vec(),
        ]
    })
}
fn input(d: &[Vec<u8>; 5]) -> RecoveryProvenanceInputs<'_> {
    RecoveryProvenanceInputs {
        carrier: &d[0],
        candidate_manifest: &d[1],
        capacity_ledger: &d[2],
        ownership_ledger: &d[3],
        semantic_envelope: &d[4],
        profile_policy: include_bytes!("../../../spec/profile-policy-v2.toml"),
        profile_limits: include_bytes!("../../../spec/profile-limits-v2.toml"),
        damage_policy: include_bytes!("../../../spec/damage-policy-v2.toml"),
    }
}
fn obj(v: &mut V) -> &mut BTreeMap<String, V> {
    if let V::Object(v) = v { v } else { panic!() }
}
fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn rebind(d: &mut [Vec<u8>; 5], candidate: &mut V) {
    let mut capacity = validate_canonical_manifest(&d[2]).unwrap();
    obj(&mut capacity).insert("semantic_envelope_sha256".into(), V::String(hash(&d[4])));
    obj(&mut capacity).insert("carrier_sha256".into(), V::String(hash(&d[0])));
    d[2] = serialize_manifest(&capacity).unwrap();
    let mut ownership = validate_canonical_manifest(&d[3]).unwrap();
    obj(&mut ownership).insert("capacity_ledger_sha256".into(), V::String(hash(&d[2])));
    obj(&mut ownership).insert("carrier_sha256".into(), V::String(hash(&d[0])));
    d[3] = serialize_manifest(&ownership).unwrap();
    if let V::Array(rows) = obj(candidate).get_mut("files").unwrap() {
        for row in rows {
            let row = obj(row);
            for (index, name) in [
                (0, "carrier.bin"),
                (2, "capacity-ledger.json"),
                (3, "ownership-ledger.json"),
                (4, "semantic-envelope.json"),
            ] {
                if row["path"] == V::String(name.into()) {
                    row.insert("bytes".into(), V::U64(d[index].len() as u64));
                    row.insert("sha256".into(), V::String(hash(&d[index])));
                }
            }
        }
    }
    obj(candidate).remove("manifest_identity");
    let id = identity_hex(
        b"golden-board:manifest:v0\0",
        &[&serialize_manifest(candidate).unwrap()],
    )
    .unwrap();
    obj(candidate).insert("manifest_identity".into(), V::String(id));
    d[1] = serialize_manifest(candidate).unwrap();
}

#[test]
fn rebound_stale_content_context_cannot_replace_actual_stream() {
    let mut d = fixture().clone();
    let mut candidate = validate_canonical_manifest(&d[1]).unwrap();
    let mut semantic = validate_canonical_manifest(&d[4]).unwrap();
    for v in [&mut candidate, &mut semantic] {
        obj(obj(v).get_mut("source_identities").unwrap())
            .insert("required_content_sha256".into(), V::String("0".repeat(64)));
    }
    d[4] = serialize_manifest(&semantic).unwrap();
    rebind(&mut d, &mut candidate);
    assert!(build_recovery_provenance_v2(input(&d)).is_err());
}

#[test]
fn rebound_carrier_with_all_route_calibrations_corrupt_has_no_source_fallback() {
    let mut d = fixture().clone();
    let mut candidate = validate_canonical_manifest(&d[1]).unwrap();
    let V::Object(ownership) = validate_canonical_manifest(&d[3]).unwrap() else {
        panic!("expected ownership object")
    };
    let (V::U64(side), V::U64(width)) = (&ownership["side"], &ownership["shell_width"]) else {
        panic!("expected owned geometry")
    };
    let (side, width) = (*side as usize, *width as usize);
    for sector in 0..4 {
        let (r, c) = gb_bootstrap::sector_cell_at(side, width, sector, 0).unwrap();
        let flat = r * side + c;
        d[0][4 + flat / 8] ^= 1 << (7 - flat % 8);
    }
    rebind(&mut d, &mut candidate);
    assert_eq!(
        build_recovery_provenance_v2(input(&d)).unwrap_err(),
        gb_bootstrap::recovery_provenance_v2::RecoveryProvenanceError::Recovery
    );
}
#[test]
fn actual_recovery_feeds_both_evidence_producers() {
    let d = fixture();
    gb_bootstrap::physical_v2::admit_physical_inputs_v2(&d[1], &d[2], &d[3], &d[4]).unwrap();
    assert!(
        gb_bootstrap::physical_v2::admit_physical_inputs_v2(b"{}", &d[2], &d[3], &d[4]).is_err()
    );
    let e = build_recovery_provenance_v2(input(d)).unwrap();
    let mut v = validate_canonical_manifest(e.canonical_bytes()).unwrap();
    assert_eq!(obj(&mut v).len(), 13);
    assert_eq!(e.bodies().len(), 78);
    assert_eq!(e.required_stream().len(), 42432);
    assert_eq!(e.all_stream().len(), 55664);
    assert!(e.prefixes().iter().all(|p| p.len() == 25424));
    assert_eq!(e.first_use().len(), 492857);
    obj(&mut v).insert("result".into(), V::String("failure".into()));
    assert!(validate_recovery_provenance_v2(&serialize_manifest(&v).unwrap(), input(d)).is_err());
    // Optional development comparison export; never consumed as a test input.
    if let Some(path) = std::env::var_os("GB_RECOVERY_V2_EXPORT") {
        let p = std::path::PathBuf::from(path);
        std::fs::create_dir(&p).unwrap();
        for (name, bytes) in [
            ("recovery-provenance.json", e.canonical_bytes()),
            ("decoder-result.json", e.decoder_result()),
            ("knowledge-use.json", e.knowledge_use()),
            ("first-use.json", e.first_use()),
        ] {
            std::fs::write(p.join(name), bytes).unwrap();
        }
    }
}
#[test]
fn stale_carrier_prefix_and_policy_bindings_reject() {
    let mut d = fixture().clone();
    *d[0].last_mut().unwrap() ^= 1;
    assert!(build_recovery_provenance_v2(input(&d)).is_err());
    let mut d = fixture().clone();
    let mut candidate = validate_canonical_manifest(&d[1]).unwrap();
    if let V::Array(rows) = obj(&mut candidate).get_mut("files").unwrap() {
        for row in rows {
            let row = obj(row);
            if row["path"] == V::String("route-0.bin".into()) {
                row.insert("sha256".into(), V::String("0".repeat(64)));
            }
        }
    }
    obj(&mut candidate).remove("manifest_identity");
    let id = identity_hex(
        b"golden-board:manifest:v0\0",
        &[&serialize_manifest(&candidate).unwrap()],
    )
    .unwrap();
    obj(&mut candidate).insert("manifest_identity".into(), V::String(id));
    d[1] = serialize_manifest(&candidate).unwrap();
    assert!(build_recovery_provenance_v2(input(&d)).is_err());
    let mut i = input(fixture());
    i.profile_policy = b"bad";
    assert!(build_recovery_provenance_v2(i).is_err());
}
