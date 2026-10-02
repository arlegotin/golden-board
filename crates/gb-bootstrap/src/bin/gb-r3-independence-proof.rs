//! Bounded, read-only gate-7 proof projector for promoted M2 R3.
//!
//! Invocation:
//! `gb-r3-independence-proof CANDIDATE OWNERSHIP DAMAGE_DIRECTORY`
//!
//! The two files and the exact gate-6 directory are strictly admitted. The
//! canonical proof-v1 bytes are written to stdout; no file is created or
//! modified. Any framing, path, schema, binding, resource, or proof error is
//! fatal and produces no proof bytes.

use std::collections::BTreeMap;
use std::ffi::OsStr;
use std::fs::{self, File, Metadata};
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};

use gb_bootstrap::independence_v1::{
    admit_independence_proof_v1, build_independence_proof_from_bundle_v1,
};
use gb_foundation::{ManifestValue, validate_canonical_manifest};

const MAX_FILE_BYTES: u64 = 1_048_576;
const MAX_AGGREGATE_BYTES: u64 = 536_870_912;
const MAX_GATE6_FILES: usize = 10_047;

#[cfg(unix)]
fn exactly_one_link(metadata: &Metadata) -> bool {
    use std::os::unix::fs::MetadataExt;
    metadata.nlink() == 1
}

#[cfg(not(unix))]
fn exactly_one_link(_metadata: &Metadata) -> bool {
    false
}

fn read_regular(path: &Path, aggregate: &mut u64) -> io::Result<Vec<u8>> {
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.file_type().is_file()
        || metadata.file_type().is_symlink()
        || !exactly_one_link(&metadata)
        || metadata.len() == 0
        || metadata.len() > MAX_FILE_BYTES
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid R3 proof input file",
        ));
    }
    *aggregate = aggregate
        .checked_add(metadata.len())
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "R3 proof input overflow"))?;
    if *aggregate > MAX_AGGREGATE_BYTES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "R3 proof aggregate exceeds bound",
        ));
    }
    let capacity = usize::try_from(metadata.len())
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "R3 proof input too large"))?;
    let mut raw = Vec::with_capacity(capacity);
    File::open(path)?
        .take(MAX_FILE_BYTES + 1)
        .read_to_end(&mut raw)?;
    if raw.len() as u64 != metadata.len() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "R3 proof input changed while reading",
        ));
    }
    Ok(raw)
}

fn shard_key(name: &str) -> Option<(usize, u64)> {
    let tail = name.strip_prefix("damage-D")?;
    let family = tail.as_bytes().first()?.checked_sub(b'0')? as usize;
    if family > 7 || tail.as_bytes().get(1).copied()? != b'-' {
        return None;
    }
    let digits = tail
        .strip_prefix(&format!("{family}-cases-"))?
        .strip_suffix(".json")?;
    if digits.len() < 4 || !digits.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    let ordinal = digits.parse::<u64>().ok()?;
    if ordinal > 10_037 || digits != format!("{ordinal:04}") {
        return None;
    }
    Some((family, ordinal))
}

fn shard_manifest_key(raw: &[u8]) -> io::Result<(usize, u64)> {
    let ManifestValue::Object(value) = validate_canonical_manifest(raw).map_err(|_| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid R3 proof shard manifest",
        )
    })?
    else {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid R3 proof shard root",
        ));
    };
    let family = match value.get("family_id") {
        Some(ManifestValue::String(value)) if value.len() == 2 && value.starts_with('D') => value
            .as_bytes()
            .get(1)
            .and_then(|byte| byte.checked_sub(b'0'))
            .map(usize::from)
            .filter(|family| *family <= 7),
        _ => None,
    }
    .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "invalid R3 shard family"))?;
    let ordinal = match value.get("shard_ordinal") {
        Some(ManifestValue::U64(value)) if *value <= 10_037 => *value,
        _ => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "invalid R3 shard ordinal",
            ));
        }
    };
    Ok((family, ordinal))
}

fn reject_linked_directory_chain(target: &Path) -> io::Result<()> {
    if !target.is_absolute()
        || target
            .components()
            .any(|component| matches!(component, Component::CurDir | Component::ParentDir))
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "invalid R3 proof path",
        ));
    }
    let mut current = PathBuf::new();
    for component in target.components() {
        current.push(component.as_os_str());
        if matches!(component, Component::RootDir | Component::Prefix(_)) {
            continue;
        }
        let metadata = fs::symlink_metadata(&current)?;
        if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "linked R3 proof directory",
            ));
        }
    }
    Ok(())
}

fn validate_layout(
    candidate_path: &Path,
    ownership_path: &Path,
    damage_directory: &Path,
) -> io::Result<()> {
    if !candidate_path.is_absolute()
        || !ownership_path.is_absolute()
        || !damage_directory.is_absolute()
        || candidate_path.file_name() != Some(OsStr::new("candidate-manifest.json"))
        || ownership_path.file_name() != Some(OsStr::new("ownership-ledger.json"))
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "unexpected R3 proof bound-input path",
        ));
    }
    let candidate_root = candidate_path
        .parent()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "missing R3 candidate root"))?;
    if ownership_path.parent() != Some(candidate_root)
        || damage_directory != candidate_root.join("damage")
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "unbound R3 proof directory layout",
        ));
    }
    reject_linked_directory_chain(candidate_root)?;
    reject_linked_directory_chain(damage_directory)?;
    Ok(())
}

fn project_paths_at(
    candidate_path: &Path,
    ownership_path: &Path,
    damage_directory: &Path,
) -> io::Result<Vec<u8>> {
    validate_layout(candidate_path, ownership_path, damage_directory)?;
    let directory_metadata = fs::symlink_metadata(damage_directory)?;
    if !directory_metadata.file_type().is_dir() || directory_metadata.file_type().is_symlink() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid R3 proof damage directory",
        ));
    }

    let mut bound_input_bytes = 0_u64;
    let candidate = read_regular(candidate_path, &mut bound_input_bytes)?;
    let ownership = read_regular(ownership_path, &mut bound_input_bytes)?;
    let mut aggregate = 0_u64;
    let mut files = BTreeMap::<String, Vec<u8>>::new();
    let entries = fs::read_dir(&damage_directory)?.collect::<io::Result<Vec<_>>>()?;
    if entries.len() > MAX_GATE6_FILES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "too many R3 proof damage files",
        ));
    }
    for entry in entries {
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "non-ASCII damage filename"))?;
        let allowed = name == "damage-manifest.json"
            || (0..8).any(|family| name == format!("damage-D{family}.json"))
            || shard_key(&name).is_some();
        if !allowed || files.contains_key(&name) {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "unexpected R3 proof damage file",
            ));
        }
        let raw = read_regular(&entry.path(), &mut aggregate)?;
        if let Some(expected) = shard_key(&name) {
            if shard_manifest_key(&raw)? != expected {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "R3 shard filename/content mismatch",
                ));
            }
        }
        files.insert(name, raw);
    }
    if files.len() < 17 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "incomplete R3 proof damage bundle",
        ));
    }
    let root = files
        .get("damage-manifest.json")
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "missing damage root"))?;
    let family = (0..8)
        .map(|ordinal| {
            files
                .get(&format!("damage-D{ordinal}.json"))
                .map(Vec::as_slice)
                .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "missing damage family"))
        })
        .collect::<io::Result<Vec<_>>>()?;
    let shards = files
        .iter()
        .filter_map(|(name, raw)| shard_key(name).map(|key| (key, raw.as_slice())))
        .collect::<BTreeMap<_, _>>();
    let shards = shards.values().copied().collect::<Vec<_>>();
    let proof =
        build_independence_proof_from_bundle_v1(&candidate, &ownership, root, &family, &shards)
            .map_err(|_| {
                io::Error::new(io::ErrorKind::InvalidData, "R3 proof projection rejected")
            })?;
    admit_independence_proof_v1(
        &proof.canonical_bytes,
        &candidate,
        &ownership,
        root,
        &proof.predicate_rows,
    )
    .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "R3 proof self-admission failed"))?;
    Ok(proof.canonical_bytes)
}

fn project_paths(
    candidate_path: &Path,
    ownership_path: &Path,
    damage_directory: &Path,
) -> io::Result<Vec<u8>> {
    project_paths_at(candidate_path, ownership_path, damage_directory)
}

fn run() -> io::Result<Vec<u8>> {
    let arguments = std::env::args_os().skip(1).collect::<Vec<_>>();
    if arguments.len() != 3 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "expected candidate, ownership, and damage-directory paths",
        ));
    }
    project_paths(
        &PathBuf::from(&arguments[0]),
        &PathBuf::from(&arguments[1]),
        &PathBuf::from(&arguments[2]),
    )
}

fn main() {
    match run() {
        Ok(raw) => {
            if io::stdout().lock().write_all(&raw).is_err() {
                std::process::exit(2);
            }
        }
        Err(_) => {
            eprintln!("R3 independence proof rejected");
            std::process::exit(2);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temporary_directory(label: &str) -> PathBuf {
        let path = std::env::temp_dir().join(format!(
            "golden-board-{label}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir(&path).unwrap();
        path
    }

    #[test]
    fn shard_names_are_exact_and_bounded() {
        assert_eq!(shard_key("damage-D0-cases-0000.json"), Some((0, 0)));
        assert_eq!(shard_key("damage-D7-cases-9999.json"), Some((7, 9_999)));
        assert_eq!(shard_key("damage-D7-cases-10000.json"), Some((7, 10_000)));
        for invalid in [
            "damage-D8-cases-0000.json",
            "damage-D0-cases-000.json",
            "damage-D0-cases-00000.json",
            "damage-D0-cases-+000.json",
            "damage-D0-cases-0000.JSON",
            "damage-D7-cases-10038.json",
        ] {
            assert_eq!(shard_key(invalid), None);
        }
        let wrong_content = b"{\"family_id\":\"D1\",\"shard_ordinal\":0}\n";
        assert_eq!(shard_manifest_key(wrong_content).unwrap(), (1, 0));
        assert_ne!(
            shard_key("damage-D0-cases-0000.json").unwrap(),
            shard_manifest_key(wrong_content).unwrap()
        );
    }

    #[test]
    fn cli_paths_reject_partial_unknown_and_linked_inputs_before_projection() {
        let workspace = fs::canonicalize(temporary_directory("r3-proof-cli")).unwrap();
        let directory = workspace.join("stage");
        fs::create_dir_all(&directory).unwrap();
        let candidate = directory.join("candidate-manifest.json");
        let ownership = directory.join("ownership-ledger.json");
        let damage = directory.join("damage");
        let gates = gb_bootstrap::gate8_v1::regenerate_current_r3_gates_one_through_five().unwrap();
        fs::write(&candidate, &gates.artifacts.candidate_manifest).unwrap();
        fs::write(&ownership, &gates.artifacts.ownership_ledger).unwrap();
        fs::create_dir(&damage).unwrap();
        assert_eq!(
            project_paths_at(&candidate, &ownership, &damage)
                .unwrap_err()
                .kind(),
            io::ErrorKind::InvalidData
        );
        fs::write(damage.join("unknown.json"), b"{}\n").unwrap();
        assert_eq!(
            project_paths_at(&candidate, &ownership, &damage)
                .unwrap_err()
                .kind(),
            io::ErrorKind::InvalidData
        );

        #[cfg(unix)]
        {
            use std::os::unix::fs::symlink;
            let linked_workspace =
                fs::canonicalize(temporary_directory("r3-proof-cli-link")).unwrap();
            let real = linked_workspace.join("real");
            fs::create_dir(&real).unwrap();
            let linked = linked_workspace.join("artifacts");
            symlink(&real, &linked).unwrap();
            let linked_root = linked.join("stage");
            fs::create_dir_all(real.join("stage").join("damage")).unwrap();
            assert_eq!(
                validate_layout(
                    &linked_root.join("candidate-manifest.json"),
                    &linked_root.join("ownership-ledger.json"),
                    &linked_root.join("damage"),
                )
                .unwrap_err()
                .kind(),
                io::ErrorKind::InvalidData
            );
            fs::remove_dir_all(linked_workspace).unwrap();
        }
        fs::remove_dir_all(workspace).unwrap();
    }

    #[test]
    fn cli_layout_rejects_unrelated_parent_and_renamed_damage() {
        let workspace = fs::canonicalize(temporary_directory("r3-proof-layout")).unwrap();
        let candidate_root = workspace.join("stage");
        let unrelated = workspace.join("unrelated");
        fs::create_dir_all(candidate_root.join("damage")).unwrap();
        fs::create_dir(&unrelated).unwrap();
        let candidate = candidate_root.join("candidate-manifest.json");
        let ownership = candidate_root.join("ownership-ledger.json");
        assert!(
            validate_layout(
                &candidate,
                &unrelated.join("ownership-ledger.json"),
                &candidate_root.join("damage"),
            )
            .is_err()
        );
        assert!(
            validate_layout(
                &candidate,
                &ownership,
                &candidate_root.join("damage-renamed"),
            )
            .is_err()
        );
        fs::remove_dir_all(workspace).unwrap();
    }
}
