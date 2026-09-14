use std::collections::BTreeMap;
use std::path::PathBuf;

use gb_bootstrap::policy::render_r3_promoted_owner_bundle;
use gb_foundation::{ManifestValue, serialize_manifest};
use gb_slice::{SliceInputs, compile_slice_v0};
use sha2::{Digest, Sha256};

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn main() {
    let compiled = compile_slice_v0(SliceInputs {
        declaration: include_bytes!("../../../studies/m2/slice-v0.json"),
        content_fixture: include_bytes!("../../../conformance/content-v0.json"),
        chess_fixture: include_bytes!("../../../conformance/chess-v0.json"),
        game_set: include_bytes!("../../../reports/game-set-v0.bin"),
        content_spec: include_bytes!("../../../spec/content-v0.md"),
        constants: include_bytes!("../../../spec/constants-v0.toml"),
        curriculum: include_bytes!("../../../spec/curriculum-v0.toml"),
    })
    .expect("independent semantic slice");
    let bundle = render_r3_promoted_owner_bundle(
        &compiled,
        include_bytes!("../../../spec/curriculum-v0.toml"),
    )
    .expect("derive exact promoted owner bundle");
    let route = &bundle.route;
    let projected = &bundle.projected_policies;
    let limits = &bundle.limits;
    let directory = std::env::args_os()
        .nth(1)
        .map(PathBuf::from)
        .unwrap_or_else(|| std::env::temp_dir().join("golden-board-r3-rust-stage"));
    std::fs::create_dir_all(&directory).expect("create bounded stage directory");
    let mut files = vec![
        (
            "recipient-package-v7.bin".to_owned(),
            route.draft.recipient_package.clone(),
        ),
        (
            "route-data-v1.template.json".to_owned(),
            route.draft.route_data_template.clone(),
        ),
        ("route-data-v1.json".to_owned(), route.route_data.clone()),
        (
            "route-reproduction-projection.json".to_owned(),
            route.reproduction_projection.clone(),
        ),
        (
            "route-malformed-corpus.json".to_owned(),
            route.malformed_corpus.clone(),
        ),
        (
            "route-rust-reproduction.json".to_owned(),
            route.rust_reproduction_receipt.clone(),
        ),
        (
            "profile-policy-v1.projected.toml".to_owned(),
            projected.profile_policy.clone(),
        ),
        (
            "damage-policy-v1.projected.toml".to_owned(),
            projected.damage_policy.clone(),
        ),
        (
            "profile-limits-v1.toml".to_owned(),
            limits.canonical_bytes.clone(),
        ),
        (
            "limits-rust-reproduction.json".to_owned(),
            limits.rust_reproduction_receipt.clone(),
        ),
        (
            "m2-r3-owner-promotion-v1.projected.toml".to_owned(),
            bundle.promotion_manifest.clone(),
        ),
        (
            "route-prefixes.bin".to_owned(),
            route.draft.route_prefixes.concat(),
        ),
    ];
    for (sector, raw) in route.draft.route_prefixes.iter().enumerate() {
        files.push((format!("route-prefix-sector-{sector}.bin"), raw.clone()));
    }
    files.sort_by(|left, right| left.0.cmp(&right.0));
    let mut rows = Vec::with_capacity(files.len());
    for (name, raw) in &files {
        std::fs::write(directory.join(name), raw).expect("write staged owner input");
        rows.push(ManifestValue::Object(BTreeMap::from([
            ("bytes".to_owned(), ManifestValue::U64(raw.len() as u64)),
            ("path".to_owned(), ManifestValue::String(name.clone())),
            ("sha256".to_owned(), ManifestValue::String(sha256(raw))),
        ])));
    }
    let manifest = serialize_manifest(&ManifestValue::Object(BTreeMap::from([
        ("files".to_owned(), ManifestValue::Array(rows)),
        (
            "schema".to_owned(),
            ManifestValue::String("golden-board.m2-r3-rust-stage/v1".to_owned()),
        ),
    ])))
    .expect("canonical stage manifest");
    std::fs::write(directory.join("manifest.json"), &manifest).expect("write stage manifest");
    println!("stage={}", directory.display());
    println!("manifest_bytes={}", manifest.len());
    println!("manifest_sha256={}", sha256(&manifest));
}
