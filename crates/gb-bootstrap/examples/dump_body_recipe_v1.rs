//! Generate independent compact development profile-8 recipe bytes.
use std::error::Error;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;

use gb_bootstrap::body_recipe_v1::build_revision_recipe_package;
use gb_bootstrap::recipe_wire_v1::{decode_recipe_package_v1, expand_recipe_package_v1};
use sha2::{Digest, Sha256};

fn run() -> Result<(), Box<dyn Error>> {
    let mut arguments = std::env::args_os().skip(1);
    let path = PathBuf::from(
        arguments
            .next()
            .ok_or("usage: dump_body_recipe_v1 ABSOLUTE_NEW_OUTPUT_FILE")?,
    );
    if arguments.next().is_some() || !path.is_absolute() {
        return Err("expected one absolute new output path".into());
    }
    let compact = build_revision_recipe_package().map_err(|_| "recipe construction failed")?;
    decode_recipe_package_v1(&compact, 8).map_err(|_| "compact validation failed")?;
    let expanded = expand_recipe_package_v1(&compact, 8).map_err(|_| "expansion failed")?;
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
        eprintln!("body-recipe-v1: {error}");
        std::process::exit(2);
    }
}
