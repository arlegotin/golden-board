//! Export independently source-built development artifacts to a private directory.
use std::error::Error;
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::Path;

use gb_bootstrap::carrier_v2::build_carrier;
use gb_bootstrap::route_v2::build_route_prefixes;
use gb_bootstrap::static_v2::build_static_projection_v2;
use sha2::{Digest, Sha256};

fn private_empty(path: &Path) -> Result<(), Box<dyn Error>> {
    if !path.is_absolute() {
        return Err("output must be an absolute private directory".into());
    }
    for ancestor in path.ancestors() {
        let meta = fs::symlink_metadata(ancestor)?;
        if !meta.is_dir() || meta.file_type().is_symlink() {
            return Err("output directory or ancestor is not a real directory".into());
        }
    }
    if fs::read_dir(path)?.next().is_some() {
        return Err("output directory must be empty".into());
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if fs::metadata(path)?.permissions().mode() & 0o077 != 0 {
            return Err("output directory must be private".into());
        }
    }
    Ok(())
}

fn write(directory: &Path, name: &str, raw: &[u8]) -> Result<(), Box<dyn Error>> {
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(directory.join(name))?;
    file.write_all(raw)?;
    file.sync_all()?;
    println!("{name} {} {:x}", raw.len(), Sha256::digest(raw));
    Ok(())
}

fn run() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 1 {
        return Err("usage: static_v2 PRIVATE_EMPTY_OUTPUT_DIRECTORY".into());
    }
    let output = Path::new(&args[0]);
    private_empty(output)?;
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
    )?;
    let carrier = build_carrier(&slice).map_err(|e| format!("carrier: {e:?}"))?;
    let prefixes = build_route_prefixes(&slice).map_err(|e| format!("routes: {e:?}"))?;
    let projections = build_static_projection_v2(&slice, &carrier)
        .map_err(|e| format!("static projection: {e:?}"))?;
    // All computation and strict source validation finish before output writes.
    private_empty(output)?;
    write(output, "carrier.bin", carrier.packed_bytes())?;
    for (sector, prefix) in prefixes.iter().enumerate() {
        write(output, &format!("route-{sector}.bin"), prefix)?;
    }
    for (name, bytes) in projections.documents() {
        write(output, name, bytes)?;
    }
    File::open(output)?.sync_all()?;
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("static-v2: {error}");
        std::process::exit(2);
    }
}
