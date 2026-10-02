//! Independently generate the diagnostic compact encoding of the retained v7 program.
use std::error::Error;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;

use gb_bootstrap::candidate_recipe::build_r3_recipe_package;
use gb_bootstrap::recipe_wire_v1::{encode_recipe_package_v1, expand_recipe_package_v1};
use sha2::{Digest, Sha256};

fn run() -> Result<(), Box<dyn Error>> {
    let mut arguments = std::env::args_os().skip(1);
    let path = PathBuf::from(
        arguments
            .next()
            .ok_or("usage: dump_recipe_wire_v1 ABSOLUTE_NEW_OUTPUT_FILE")?,
    );
    if arguments.next().is_some() || !path.is_absolute() {
        return Err("expected one absolute new output path".into());
    }
    let expanded = build_r3_recipe_package().map_err(|_| "logical recipe build failed")?;
    let compact = encode_recipe_package_v1(&expanded, 7).map_err(|_| "compact encoding failed")?;
    if expand_recipe_package_v1(&compact, 7).map_err(|_| "compact validation failed")? != expanded {
        return Err("logical round trip failed".into());
    }
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(path)?;
    file.write_all(&compact)?;
    file.sync_all()?;
    println!(
        "expanded_bytes={} expanded_sha256={:x}",
        expanded.len(),
        Sha256::digest(&expanded)
    );
    println!(
        "compact_bytes={} compact_sha256={:x}",
        compact.len(),
        Sha256::digest(&compact)
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("recipe-wire-v1: {error}");
        std::process::exit(2);
    }
}
