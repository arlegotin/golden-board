use std::env;
use std::fmt::Write as _;
use std::fs;
use std::path::PathBuf;

use gb_bootstrap::carrier::{build_r3_gate_one_through_five, generate_r3_route_owner};
use gb_slice::{SliceInputs, compile_slice_v0};
use sha2::{Digest, Sha256};

fn digest(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn main() {
    let output = env::args_os()
        .nth(1)
        .map(PathBuf::from)
        .expect("usage: cargo run -p gb-bootstrap --example r3_carrier -- NEW_OUTPUT_DIRECTORY");
    assert!(
        output.is_absolute() && (output.starts_with("/tmp") || output.starts_with("/private/tmp")),
        "the Rust bridge writes only to a new absolute temporary directory"
    );
    fs::create_dir(&output).expect("output directory must be new and its parent must exist");
    let curriculum = include_bytes!("../../../spec/curriculum-v0.toml");
    let compiled = compile_slice_v0(SliceInputs {
        declaration: include_bytes!("../../../studies/m2/slice-v0.json"),
        content_fixture: include_bytes!("../../../conformance/content-v0.json"),
        chess_fixture: include_bytes!("../../../conformance/chess-v0.json"),
        game_set: include_bytes!("../../../reports/game-set-v0.bin"),
        content_spec: include_bytes!("../../../spec/content-v0.md"),
        constants: include_bytes!("../../../spec/constants-v0.toml"),
        curriculum,
    })
    .expect("slice");
    let result = build_r3_gate_one_through_five(
        include_bytes!("../../../spec/bootstrap-v1.md"),
        include_bytes!("../../../spec/profile-policy-v1.toml"),
        include_bytes!("../../../spec/damage-policy-v1.toml"),
        include_bytes!("../../../spec/route-data-v1.json"),
        include_bytes!("../../../spec/profile-limits-v1.toml"),
        include_bytes!("../../../spec/m2-r3-owner-promotion-v1.toml"),
        include_bytes!("../../../conformance/m2-r3-owner-v1.json"),
        &compiled,
        curriculum,
    )
    .expect("strict promoted v7 gates 1--5");
    assert_eq!(result.gate_passes, [true; 5]);
    let route = generate_r3_route_owner().expect("route owner");

    let mut files = vec![
        (
            "semantic-envelope-v0.json".to_owned(),
            result.semantic.canonical_bytes().to_vec(),
        ),
        (
            "carrier-v7.obs-bits".to_owned(),
            result.core.carrier_bytes.clone(),
        ),
        (
            "candidate-manifest-v1.json".to_owned(),
            result.artifacts.candidate_manifest.clone(),
        ),
        (
            "ownership-ledger-v1.json".to_owned(),
            result.artifacts.ownership_ledger.clone(),
        ),
        (
            "capacity-ledger-v1.json".to_owned(),
            result.artifacts.capacity_ledger.clone(),
        ),
        (
            "density-ledger-v0.json".to_owned(),
            result.artifacts.density_ledger.clone(),
        ),
        (
            "recipient-package-v7.bin".to_owned(),
            route.draft.recipient_package.clone(),
        ),
    ];
    for (sector, raw) in route.draft.route_prefixes.iter().enumerate() {
        files.push((format!("route-prefix-v1-sector-{sector}.bin"), raw.clone()));
    }
    let mut cell_table = Vec::with_capacity(result.core.cell_owners.len() * 9);
    for owner in &result.core.cell_owners {
        cell_table.push(owner.kind);
        cell_table.extend_from_slice(&owner.owner_id.to_be_bytes());
        cell_table.extend_from_slice(&owner.bit_offset.to_be_bytes());
    }
    files.push(("cell-ownership-v1.bin".to_owned(), cell_table));
    files.sort_by(|left, right| left.0.cmp(&right.0));

    let mut hashes = String::new();
    for (name, raw) in &files {
        fs::write(output.join(name), raw).expect("write artifact");
        writeln!(hashes, "{}  {}  {}", digest(raw), raw.len(), name).unwrap();
    }
    fs::write(output.join("ARTIFACT-SHA256"), hashes).expect("write digest inventory");

    let mut metrics = String::new();
    writeln!(metrics, "profile_id={}", result.core.profile.id).unwrap();
    writeln!(metrics, "gates_1_through_5=pass,pass,pass,pass,pass").unwrap();
    writeln!(
        metrics,
        "bootstrap_spec_sha256={}",
        digest(include_bytes!("../../../spec/bootstrap-v1.md"))
    )
    .unwrap();
    writeln!(
        metrics,
        "profile_policy_sha256={}",
        digest(include_bytes!("../../../spec/profile-policy-v1.toml"))
    )
    .unwrap();
    writeln!(
        metrics,
        "damage_policy_sha256={}",
        digest(include_bytes!("../../../spec/damage-policy-v1.toml"))
    )
    .unwrap();
    writeln!(
        metrics,
        "route_data_sha256={}",
        digest(include_bytes!("../../../spec/route-data-v1.json"))
    )
    .unwrap();
    writeln!(
        metrics,
        "profile_limits_sha256={}",
        digest(include_bytes!("../../../spec/profile-limits-v1.toml"))
    )
    .unwrap();
    writeln!(
        metrics,
        "promotion_manifest_sha256={}",
        digest(include_bytes!(
            "../../../spec/m2-r3-owner-promotion-v1.toml"
        ))
    )
    .unwrap();
    writeln!(metrics, "side={}", result.core.side).unwrap();
    writeln!(metrics, "shell_width={}", result.core.shell_width).unwrap();
    writeln!(
        metrics,
        "interior_side={}",
        result.core.mapping.interior_side
    )
    .unwrap();
    writeln!(metrics, "population={}", result.core.mapping.population).unwrap();
    writeln!(metrics, "physical_units={}", result.core.units.len()).unwrap();
    writeln!(
        metrics,
        "mandatory_physical_units={}",
        result.mandatory_physical_units
    )
    .unwrap();
    writeln!(metrics, "lower_bound_cells={}", result.lower_bound_cells).unwrap();
    writeln!(metrics, "carrier_cells={}", result.core.carrier_bits.len()).unwrap();
    writeln!(
        metrics,
        "carrier_obs_bits_bytes={}",
        result.core.carrier_bytes.len()
    )
    .unwrap();
    writeln!(
        metrics,
        "fixed_pad_cells={}",
        result.core.mapping.fixed_pad_cells
    )
    .unwrap();
    writeln!(
        metrics,
        "slot_multiplier={}",
        result.core.mapping.slot_multiplier
    )
    .unwrap();
    writeln!(
        metrics,
        "slot_inverse_multiplier={}",
        result.core.mapping.inverse_slot_multiplier
    )
    .unwrap();
    writeln!(
        metrics,
        "cell_multiplier={}",
        result.core.mapping.cell_multiplier
    )
    .unwrap();
    writeln!(
        metrics,
        "cell_inverse_multiplier={}",
        result.core.mapping.inverse_cell_multiplier
    )
    .unwrap();
    writeln!(metrics, "cell_offset={}", result.core.mapping.cell_offset).unwrap();
    writeln!(
        metrics,
        "separation_window={}",
        result.core.mapping.window_side
    )
    .unwrap();
    writeln!(metrics, "section_count={}", result.core.sections.len()).unwrap();
    writeln!(
        metrics,
        "logical_group_count={}",
        route.draft.logical_group_count
    )
    .unwrap();
    writeln!(
        metrics,
        "factor_1_group_count={}",
        route.draft.factor_1_group_count
    )
    .unwrap();
    writeln!(
        metrics,
        "factor_2_group_count={}",
        route.draft.factor_2_group_count
    )
    .unwrap();
    writeln!(
        metrics,
        "factor_5_group_count={}",
        route.draft.factor_5_group_count
    )
    .unwrap();
    writeln!(
        metrics,
        "load_fragment_counts={:?}",
        route.draft.load_fragment_counts
    )
    .unwrap();
    writeln!(
        metrics,
        "load_payload_bytes={:?}",
        route.draft.load_payload_bytes
    )
    .unwrap();
    writeln!(
        metrics,
        "inventory_entry_count={}",
        route.draft.inventory_entry_count
    )
    .unwrap();
    writeln!(
        metrics,
        "inventory_dependency_count={}",
        route.draft.inventory_dependency_count
    )
    .unwrap();
    writeln!(
        metrics,
        "inventory_payload_bytes={}",
        route.draft.inventory_payload_bytes
    )
    .unwrap();
    writeln!(
        metrics,
        "inventory_fragment_count={}",
        route.draft.inventory_fragment_count
    )
    .unwrap();
    writeln!(
        metrics,
        "sector_capacity_bytes={}",
        route.draft.sector_capacity_bytes
    )
    .unwrap();
    writeln!(
        metrics,
        "route_prefix_cells_by_sector={:?}",
        route
            .draft
            .route_images
            .sectors
            .each_ref()
            .map(|sector| sector.route_prefix_cells)
    )
    .unwrap();
    writeln!(
        metrics,
        "route_headroom_cells_by_sector={:?}",
        route
            .draft
            .route_images
            .sectors
            .each_ref()
            .map(|sector| sector.headroom_cells)
    )
    .unwrap();
    writeln!(
        metrics,
        "examined_geometry_pairs={}",
        route.examined_pair_count
    )
    .unwrap();
    writeln!(metrics, "total_geometry_pairs={}", route.total_pair_count).unwrap();
    writeln!(metrics, "predecessor_side={}", route.predecessor_side).unwrap();
    writeln!(
        metrics,
        "predecessor_shell_width={}",
        route.predecessor_shell_width
    )
    .unwrap();
    writeln!(metrics, "predecessor_reason={}", route.predecessor_reason).unwrap();
    writeln!(
        metrics,
        "clean_eh_decoder_invocations={}",
        result.clean_path_eh_decoder_invocations
    )
    .unwrap();
    writeln!(
        metrics,
        "clean_repetition_candidate_groups={}",
        result.clean_path_repetition_candidate_groups
    )
    .unwrap();
    writeln!(
        metrics,
        "clean_repetition_symbol_invocations={}",
        result.clean_path_repetition_symbol_invocations
    )
    .unwrap();
    writeln!(
        metrics,
        "complete_interior_ones={}",
        result.artifacts.complete_interior_ones
    )
    .unwrap();
    writeln!(
        metrics,
        "complete_interior_cells={}",
        result.artifacts.complete_interior_cells
    )
    .unwrap();
    writeln!(metrics, "regularity={:?}", result.artifacts.regularity).unwrap();
    writeln!(metrics, "realism=pass").unwrap();
    writeln!(
        metrics,
        "candidate_manifest_identity={}",
        result.artifacts.candidate_manifest_identity
    )
    .unwrap();
    fs::write(output.join("METRICS"), metrics).expect("write metrics");
    println!("{}", output.display());
}
