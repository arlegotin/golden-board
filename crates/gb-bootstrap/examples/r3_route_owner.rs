use std::path::PathBuf;

use gb_bootstrap::carrier::generate_r3_route_owner;

fn main() {
    let generated = generate_r3_route_owner().expect("deterministic R3 route owner");
    let output_directory = std::env::args_os()
        .nth(1)
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let files = [
        (
            "golden-board-route-data-v1.rust.json",
            generated.route_data.as_slice(),
        ),
        (
            "golden-board-route-v1.rust-projection.json",
            generated.reproduction_projection.as_slice(),
        ),
        (
            "golden-board-route-v1.python-reproduction.json",
            generated.python_reproduction_receipt.as_slice(),
        ),
        (
            "golden-board-route-v1.rust-reproduction.json",
            generated.rust_reproduction_receipt.as_slice(),
        ),
        (
            "golden-board-route-v1.rust-malformed-corpus.json",
            generated.malformed_corpus.as_slice(),
        ),
    ];
    for (name, raw) in files {
        std::fs::write(output_directory.join(name), raw).expect("write temporary owner output");
    }
    for row in &generated.malformed_cases {
        std::fs::write(
            output_directory.join(format!("golden-board-route-v1-mutant-{}.bin", row.case_id)),
            &row.mutant,
        )
        .expect("write temporary malformed prefix");
    }
    println!("route_data_bytes={}", generated.route_data.len());
    println!("route_data_sha256={}", generated.route_data_sha256);
    println!(
        "reproduction_projection_bytes={}",
        generated.reproduction_projection.len()
    );
    println!(
        "reproduction_projection_sha256={}",
        generated.reproduction_projection_sha256
    );
    println!(
        "python_reproduction_bytes={}",
        generated.python_reproduction_receipt.len()
    );
    println!(
        "python_reproduction_sha256={}",
        generated.python_reproduction_sha256
    );
    println!(
        "rust_reproduction_bytes={}",
        generated.rust_reproduction_receipt.len()
    );
    println!(
        "rust_reproduction_sha256={}",
        generated.rust_reproduction_sha256
    );
    println!(
        "malformed_corpus_bytes={}",
        generated.malformed_corpus.len()
    );
    println!(
        "malformed_corpus_sha256={}",
        generated.malformed_corpus_sha256
    );
    println!("examined_pair_count={}", generated.examined_pair_count);
    println!("total_pair_count={}", generated.total_pair_count);
    println!(
        "predecessor={}/{}/{}",
        generated.predecessor_side, generated.predecessor_shell_width, generated.predecessor_reason
    );
    for row in &generated.malformed_cases {
        println!("mutant={} {}", row.case_id, row.mutant_sha256);
    }
}
