//! Generate slice-v1 independently from logical source inputs, never another encoder's bytes.

use std::collections::BTreeMap;
use std::error::Error;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use gb_foundation::canonicalize_manifest;
use gb_slice::{Closure, SliceInputs, compile_slice_v1};
use serde_json::json;
use sha2::{Digest, Sha256};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

fn digest(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn read_source(root: &Path, relative: &str, maximum: usize) -> Result<Vec<u8>> {
    let mut path = root.to_owned();
    for component in Path::new(relative).components() {
        path.push(component);
        if fs::symlink_metadata(&path)?.file_type().is_symlink() {
            return Err("symlink in source input".into());
        }
    }
    let file = File::open(path)?;
    let metadata = file.metadata()?;
    if !metadata.is_file() || metadata.len() > maximum as u64 {
        return Err("invalid or oversized source input".into());
    }
    let mut raw = Vec::new();
    file.take(maximum as u64 + 1).read_to_end(&mut raw)?;
    if raw.len() > maximum {
        return Err("oversized source input".into());
    }
    Ok(raw)
}

fn closure_name(closure: Closure) -> &'static str {
    match closure {
        Closure::Required => "m2_required",
        Closure::AllOnly => "m2_all_only",
        Closure::All => "m2_all",
    }
}

fn frames(raw: &[u8]) -> BTreeMap<u16, &[u8]> {
    // This function consumes only the independently production-validated output.
    let mut result = BTreeMap::new();
    let mut cursor = 4;
    while cursor < raw.len() {
        let id = u16::from_be_bytes(raw[cursor..cursor + 2].try_into().unwrap());
        let size = u32::from_be_bytes(raw[cursor + 4..cursor + 8].try_into().unwrap()) as usize;
        result.insert(id, &raw[cursor..cursor + 8 + size]);
        cursor += 8 + size;
    }
    result
}

fn check_output(path: &Path) -> Result<()> {
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.is_dir()
        || metadata.file_type().is_symlink()
        || fs::read_dir(path)?.next().is_some()
    {
        return Err("output must be an existing empty private directory".into());
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if metadata.permissions().mode() & 0o077 != 0 {
            return Err("output directory must not be accessible to group or others".into());
        }
    }
    Ok(())
}

fn write_outputs(directory: &Path, outputs: &[(&str, Vec<u8>)]) -> Result<()> {
    check_output(directory)?;
    let mut created = Vec::new();
    let result = (|| -> Result<()> {
        for (name, raw) in outputs {
            let path = directory.join(name);
            let mut options = OpenOptions::new();
            options.write(true).create_new(true);
            #[cfg(unix)]
            {
                use std::os::unix::fs::OpenOptionsExt;
                options.mode(0o600);
            }
            let mut file = options.open(&path)?;
            created.push(path);
            file.write_all(raw)?;
            file.sync_all()?;
        }
        File::open(directory)?.sync_all()?;
        Ok(())
    })();
    if result.is_err() {
        for path in created {
            let _ = fs::remove_file(path);
        }
    }
    result
}

fn run() -> Result<()> {
    let arguments: Vec<_> = std::env::args_os().skip(1).collect();
    if arguments.len() != 2 {
        return Err("usage: slice_v1 REPOSITORY_ROOT PRIVATE_EMPTY_OUTPUT_DIRECTORY".into());
    }
    let root = PathBuf::from(&arguments[0]).canonicalize()?;
    let output = PathBuf::from(&arguments[1]);
    if !output.is_absolute() {
        return Err("output directory must be an explicit absolute path".into());
    }
    check_output(&output)?;
    let declaration = read_source(&root, "studies/m2/slice-v1.json", 1_048_576)?;
    let legacy = read_source(&root, "studies/m2/slice-v0.json", 32_768)?;
    let content = read_source(&root, "conformance/content-v0.json", 1_048_576)?;
    let chess = read_source(&root, "conformance/chess-v0.json", 1_048_576)?;
    let games = read_source(&root, "reports/game-set-v0.bin", 327_677)?;
    let spec = read_source(&root, "spec/content-v0.md", 262_144)?;
    let constants = read_source(&root, "spec/constants-v0.toml", 262_144)?;
    let curriculum = read_source(&root, "spec/curriculum-v0.toml", 262_144)?;
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
    let all_frames = frames(compiled.all_stream());
    let sections = compiled
        .assignments()
        .iter()
        .map(|assignment| {
            let payload: Vec<u8> = assignment
                .record_ids()
                .iter()
                .flat_map(|id| all_frames[id].iter().copied())
                .collect();
            json!({
                "section_id": assignment.section_id(),
                "closure": closure_name(assignment.closure()),
                "semantic_copy_id": assignment.semantic_copy_id(),
                "record_ids": assignment.record_ids(),
                "payload_bytes": payload.len(), "payload_sha256": digest(&payload),
            })
        })
        .collect::<Vec<_>>();
    let identity = json!({
        "schema":"golden-board.m2-slice-independent-compilation/v1",
        "declaration_sha256":digest(&declaration),
        "required":{
            "stream_bytes":compiled.required_stream().len(), "stream_sha256":digest(compiled.required_stream()),
            "record_count":compiled.required_projection().records().len(), "root_record_id":compiled.required_projection().root_record_id(),
        },
        "all":{
            "stream_bytes":compiled.all_stream().len(), "stream_sha256":digest(compiled.all_stream()),
            "record_count":compiled.all_projection().records().len(), "root_record_id":compiled.all_projection().root_record_id(),
        },
        "body_sections":sections,
        "tier_roots":compiled.tier_roots().iter().map(|root| json!({
            "section_id":root.section_id(), "closure":closure_name(root.closure()),
            "semantic_copy_id":root.semantic_copy_id(), "record_id":root.record_id(),
            "frame_bytes":root.frame().len(), "frame_sha256":digest(root.frame()),
        })).collect::<Vec<_>>(),
        "game_payload_sha256":compiled.game_payloads().iter().map(|raw|digest(raw)).collect::<Vec<_>>(),
        "fixture_payload_sha256":compiled.fixture_payloads().iter().map(|raw|digest(raw)).collect::<Vec<_>>(),
    });
    let identity_raw = canonicalize_manifest(&serde_json::to_vec(&identity)?)?;
    let outputs = [
        (
            "required.content-v0.bin",
            compiled.required_stream().to_vec(),
        ),
        ("all.content-v0.bin", compiled.all_stream().to_vec()),
        ("section-identities.json", identity_raw),
    ];
    write_outputs(&output, &outputs)?;
    println!(
        "required_bytes={} required_sha256={}",
        compiled.required_stream().len(),
        digest(compiled.required_stream())
    );
    println!(
        "all_bytes={} all_sha256={}",
        compiled.all_stream().len(),
        digest(compiled.all_stream())
    );
    println!(
        "body_sections={} game_payloads={}",
        compiled.assignments().len(),
        compiled.game_payloads().len()
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("slice-v1: {error}");
        std::process::exit(2);
    }
}
