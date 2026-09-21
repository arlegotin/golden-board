//! Independently compile, encode and recover every source-owned v1 body.
use std::collections::BTreeMap;
use std::error::Error;
use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::path::Path;

use gb_bootstrap::body_codec_v1::{decode_body, encode_body};
use gb_slice::{SliceInputs, compile_slice_v1};
use sha2::{Digest, Sha256};

fn bounded_read(root: &Path, relative: &str) -> Result<Vec<u8>, Box<dyn Error>> {
    let file = File::open(root.join(relative))?;
    if !file.metadata()?.is_file() || file.metadata()?.len() > 1_048_576 {
        return Err("invalid source file".into());
    }
    let mut raw = Vec::new();
    file.take(1_048_577).read_to_end(&mut raw)?;
    if raw.len() > 1_048_576 {
        return Err("source too large".into());
    }
    Ok(raw)
}

fn run() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 2 {
        return Err("usage: body_codec_v1 SOURCE_ROOT NEW_PACKED_OUTPUT".into());
    }
    let root = Path::new(&args[0]);
    let declaration = bounded_read(root, "studies/m2/slice-v1.json")?;
    let legacy = bounded_read(root, "studies/m2/slice-v0.json")?;
    let content = bounded_read(root, "conformance/content-v0.json")?;
    let chess = bounded_read(root, "conformance/chess-v0.json")?;
    let games = bounded_read(root, "reports/game-set-v0.bin")?;
    let spec = bounded_read(root, "spec/content-v0.md")?;
    let constants = bounded_read(root, "spec/constants-v0.toml")?;
    let curriculum = bounded_read(root, "spec/curriculum-v0.toml")?;
    let compiled = compile_slice_v1(
        &declaration,
        SliceInputs {
            declaration: &legacy,
            content_fixture: &content,
            chess_fixture: &chess,
            game_set: &games,
            content_spec: &spec,
            constants: &constants,
            curriculum: &curriculum,
        },
    )?;
    let mut frames = BTreeMap::new();
    let raw = compiled.all_stream();
    let mut cursor = 4;
    while cursor < raw.len() {
        let id = u16::from_be_bytes(raw[cursor..cursor + 2].try_into()?);
        let size = u32::from_be_bytes(raw[cursor + 4..cursor + 8].try_into()?) as usize;
        frames.insert(id, &raw[cursor..cursor + 8 + size]);
        cursor += 8 + size;
    }
    let mut packed = Vec::new();
    packed.extend_from_slice(&(compiled.assignments().len() as u16).to_be_bytes());
    for row in compiled.assignments() {
        let body: Vec<u8> = row
            .record_ids()
            .iter()
            .flat_map(|id| frames[id].iter().copied())
            .collect();
        let (version, encoded) = encode_body(&body).map_err(|e| format!("{e:?}"))?;
        let recovered = decode_body(version, &encoded).map_err(|e| format!("{e:?}"))?;
        if recovered != body {
            return Err("codec mismatch".into());
        }
        packed.extend_from_slice(&row.section_id().to_be_bytes());
        packed.extend_from_slice(&version.to_be_bytes());
        packed.extend_from_slice(&(encoded.len() as u32).to_be_bytes());
        packed.extend_from_slice(&encoded);
        println!(
            "{} {} {} {} {:x}",
            row.section_id(),
            version,
            body.len(),
            encoded.len(),
            Sha256::digest(&encoded)
        );
    }
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&args[1])?;
    file.write_all(&packed)?;
    println!("packed {} {:x}", packed.len(), Sha256::digest(&packed));
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("body-codec-v1: {error}");
        std::process::exit(2);
    }
}
