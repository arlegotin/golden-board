use std::path::PathBuf;

use gb_bootstrap::carrier::generate_r3_route_draft;

fn main() {
    let generated = generate_r3_route_draft().expect("deterministic R3 route draft");
    let output_directory = std::env::args_os()
        .nth(1)
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let template_path = output_directory.join("golden-board-route-data-v1.rust-template.json");
    let receipt_path = output_directory.join("golden-board-route-v1.rust-receipt.json");
    std::fs::write(&template_path, &generated.route_data_template)
        .expect("write temporary route-data template");
    std::fs::write(&receipt_path, &generated.receipt).expect("write temporary route receipt");
    let package_path = output_directory.join("golden-board-recipient-package-v7.rust.bin");
    std::fs::write(&package_path, &generated.recipient_package)
        .expect("write temporary recipient package");
    let prefix_paths = generated.route_prefixes.each_ref().map(|_| PathBuf::new());
    let mut prefix_paths = prefix_paths;
    for (sector, prefix) in generated.route_prefixes.iter().enumerate() {
        let path = output_directory.join(format!(
            "golden-board-route-v1-sector-{sector}.rust-prefix.bin"
        ));
        std::fs::write(&path, prefix).expect("write temporary route prefix");
        prefix_paths[sector] = path;
    }
    let route_path = output_directory.join("golden-board-route-v1.rust-prefixes.bin");
    std::fs::write(&route_path, generated.route_prefixes.concat())
        .expect("write temporary concatenated route prefixes");
    println!("route_data_template={}", template_path.display());
    println!(
        "route_data_template_sha256={}",
        generated.route_data_template_sha256
    );
    println!("receipt={}", receipt_path.display());
    println!("receipt_sha256={}", generated.receipt_sha256);
    println!("recipient_package={}", package_path.display());
    println!("route_prefixes={prefix_paths:?}");
    println!("route_prefix_concat={}", route_path.display());
    println!(
        "recipient_package_bytes={}",
        generated.recipient_package.len()
    );
    println!(
        "recipient_package_sha256={}",
        generated.recipient_package_sha256
    );
    println!("route_sha256={}", generated.route_sha256);
    println!(
        "route_prefix_sha256_by_sector={:?}",
        generated.route_prefix_sha256_by_sector
    );
    println!("side={}", generated.side);
    println!("shell_width={}", generated.shell_width);
    println!("sector_capacity_bytes={}", generated.sector_capacity_bytes);
    println!(
        "route_prefix_cells_by_sector={:?}",
        generated
            .route_images
            .sectors
            .each_ref()
            .map(|sector| sector.route_prefix_cells)
    );
    println!(
        "route_headroom_cells_by_sector={:?}",
        generated
            .route_images
            .sectors
            .each_ref()
            .map(|sector| sector.headroom_cells)
    );
    println!(
        "worked_record_bytes_by_sector={:?}",
        generated.worked_record_bytes_by_sector
    );
    println!(
        "held_out_record_bytes_by_sector={:?}",
        generated.held_out_record_bytes_by_sector
    );
    println!("mapping={:?}", generated.mapping);
    println!("logical_group_count={}", generated.logical_group_count);
    println!("factor_1_group_count={}", generated.factor_1_group_count);
    println!("factor_2_group_count={}", generated.factor_2_group_count);
    println!("factor_5_group_count={}", generated.factor_5_group_count);
    println!("load_fragment_counts={:?}", generated.load_fragment_counts);
    println!("load_payload_bytes={:?}", generated.load_payload_bytes);
    println!("inventory_entry_count={}", generated.inventory_entry_count);
    println!(
        "inventory_dependency_count={}",
        generated.inventory_dependency_count
    );
    println!(
        "inventory_payload_bytes={}",
        generated.inventory_payload_bytes
    );
    println!(
        "inventory_fragment_count={}",
        generated.inventory_fragment_count
    );
}
