//! Input-only finite coverage exporter. Acquisition provenance is external.
use gb_bootstrap::first_use_v2::{FirstUseInputs, build_first_use_v2};
use sha2::{Digest, Sha256};
use std::error::Error;
use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::path::Path;

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() != 4 {
        return Err(
            "usage: first_use_v2 SIDE WIDTH OBSERVED_PREFIX_DIRECTORY NEW_OUTPUT_FILE".into(),
        );
    }
    let side = args[0].parse()?;
    let width = args[1].parse()?;
    let mut prefixes = Vec::new();
    for sector in 0..4 {
        let path = Path::new(&args[2]).join(format!("route-{sector}.bin"));
        if !std::fs::symlink_metadata(&path)?.file_type().is_file() {
            return Err("prefix must be regular".into());
        }
        let mut raw = vec![];
        File::open(path)?.take(32769).read_to_end(&mut raw)?;
        if raw.len() > 32768 {
            return Err("prefix exceeds bound".into());
        }
        prefixes.push(raw);
    }
    let raw = build_first_use_v2(FirstUseInputs {
        prefixes: [&prefixes[0], &prefixes[1], &prefixes[2], &prefixes[3]],
        side,
        width,
    })?;
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    options.open(&args[3])?.write_all(&raw)?;
    println!("{} bytes sha256 {:x}", raw.len(), Sha256::digest(&raw));
    Ok(())
}
