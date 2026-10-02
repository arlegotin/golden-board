use std::path::PathBuf;

use gb_bootstrap::carrier::generate_r3_route_owner;
use gb_bootstrap::policy::{project_r3_policy_owners, render_r3_profile_limits};
use gb_slice::{SliceInputs, compile_slice_v0};

fn main() {
    let route = generate_r3_route_owner().expect("deterministic R3 route owner");
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
    let projected = project_r3_policy_owners(&route).expect("project final policy owners");
    let limits = render_r3_profile_limits(
        &route,
        &compiled,
        include_bytes!("../../../spec/curriculum-v0.toml"),
    )
    .expect("derive exact R3 limits");
    let output_directory = std::env::args_os()
        .nth(1)
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let files = [
        (
            "golden-board-profile-policy-v1.rust-projected.toml",
            projected.profile_policy.as_slice(),
        ),
        (
            "golden-board-damage-policy-v1.rust-projected.toml",
            projected.damage_policy.as_slice(),
        ),
        (
            "golden-board-profile-limits-v1.rust.toml",
            limits.canonical_bytes.as_slice(),
        ),
        (
            "golden-board-profile-limits-v1.python-reproduction.json",
            limits.python_reproduction_receipt.as_slice(),
        ),
        (
            "golden-board-profile-limits-v1.rust-reproduction.json",
            limits.rust_reproduction_receipt.as_slice(),
        ),
    ];
    for (name, raw) in files {
        std::fs::write(output_directory.join(name), raw).expect("write temporary owner output");
    }
    println!("bootstrap_spec_sha256={}", projected.bootstrap_spec_sha256);
    println!("profile_policy_bytes={}", projected.profile_policy.len());
    println!("profile_policy_sha256={}", projected.profile_policy_sha256);
    println!("damage_policy_bytes={}", projected.damage_policy.len());
    println!("damage_policy_sha256={}", projected.damage_policy_sha256);
    println!("profile_limits_bytes={}", limits.canonical_bytes.len());
    println!("profile_limits_sha256={}", limits.sha256);
    println!(
        "python_limits_receipt_bytes={}",
        limits.python_reproduction_receipt.len()
    );
    println!(
        "python_limits_receipt_sha256={}",
        limits.python_reproduction_sha256
    );
    println!(
        "rust_limits_receipt_bytes={}",
        limits.rust_reproduction_receipt.len()
    );
    println!(
        "rust_limits_receipt_sha256={}",
        limits.rust_reproduction_sha256
    );
}
