//! Bounded Rust producer for the M2 Gate 8 cross-language receipt.
//!
//! The producer independently regenerates the promoted v7 Gates 1--7 facts,
//! compares them with its own private candidate root, and emits only the exact
//! canonical receipt named by the frozen Gate 8 owner. It never reads the live
//! retained candidate as a generated-value source.

use std::ffi::{OsStr, OsString};
use std::fs::{self, File, Metadata, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};

use gb_bootstrap::carrier::R3GateOneThroughFive;
use gb_bootstrap::gate8_v1::{
    GATE8_PRODUCER_IDS, Gate8GateSixSevenFactsV1, admit_gate8_producer_receipt,
    regenerate_current_r3_gate8_facts, render_r3_gate_six_seven_facts, render_rust_gate8_receipt,
};

const OWNER_RAW: &[u8] = include_bytes!("../../../../spec/gate8-policy-v0.toml");
const REFRESH_OWNER_RAW: &[u8] = include_bytes!("../../../../spec/gate8-verifier-refresh-v0.toml");
const MAX_FILE_BYTES: u64 = 1_048_576;
const MAX_TREE_BYTES: u64 = 83_886_080;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Mode {
    Generate,
    Check,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Arguments {
    mode: Mode,
    producer_id: &'static str,
    candidate_root: PathBuf,
    output_directory: PathBuf,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ExitClass {
    Invalid,
    Generation,
}

type CliResult<T> = std::result::Result<T, ExitClass>;

#[cfg(unix)]
fn exactly_one_link(metadata: &Metadata) -> bool {
    use std::os::unix::fs::MetadataExt;
    metadata.nlink() == 1
}

#[cfg(not(unix))]
fn exactly_one_link(_metadata: &Metadata) -> bool {
    false
}

#[cfg(unix)]
fn directory_is_private(metadata: &Metadata) -> bool {
    use std::os::unix::fs::MetadataExt;
    metadata.mode() & 0o777 == 0o700
}

#[cfg(not(unix))]
fn directory_is_private(_metadata: &Metadata) -> bool {
    false
}

fn parse_arguments(arguments: Vec<OsString>) -> CliResult<Arguments> {
    if arguments.len() != 9
        || arguments[0] != OsStr::new("producer")
        || arguments[1] != OsStr::new("--mode")
        || arguments[3] != OsStr::new("--producer-id")
        || arguments[5] != OsStr::new("--candidate-root")
        || arguments[7] != OsStr::new("--output-dir")
    {
        return Err(ExitClass::Invalid);
    }
    let mode = match arguments[2].to_str() {
        Some("generate") => Mode::Generate,
        Some("check") => Mode::Check,
        _ => return Err(ExitClass::Invalid),
    };
    let producer_id = match arguments[4].to_str() {
        Some("native-rust") => "native-rust",
        Some("linux-rust") => "linux-rust",
        _ => return Err(ExitClass::Invalid),
    };
    let candidate_root = PathBuf::from(&arguments[6]);
    let output_directory = PathBuf::from(&arguments[8]);
    if !absolute_normal_path(&candidate_root) || !absolute_normal_path(&output_directory) {
        return Err(ExitClass::Invalid);
    }
    Ok(Arguments {
        mode,
        producer_id,
        candidate_root,
        output_directory,
    })
}

fn absolute_normal_path(path: &Path) -> bool {
    path.is_absolute()
        && !path
            .components()
            .any(|part| matches!(part, Component::CurDir | Component::ParentDir))
}

fn reject_linked_directory_chain(path: &Path) -> CliResult<()> {
    if !absolute_normal_path(path) {
        return Err(ExitClass::Invalid);
    }
    let mut current = PathBuf::new();
    for component in path.components() {
        current.push(component.as_os_str());
        if matches!(component, Component::RootDir | Component::Prefix(_)) {
            continue;
        }
        let metadata = fs::symlink_metadata(&current).map_err(|_| ExitClass::Invalid)?;
        if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
            return Err(ExitClass::Invalid);
        }
    }
    Ok(())
}

fn read_regular(path: &Path, aggregate: &mut u64) -> CliResult<Vec<u8>> {
    let before = fs::symlink_metadata(path).map_err(|_| ExitClass::Invalid)?;
    if !before.file_type().is_file()
        || before.file_type().is_symlink()
        || !exactly_one_link(&before)
        || before.len() == 0
        || before.len() > MAX_FILE_BYTES
    {
        return Err(ExitClass::Invalid);
    }
    *aggregate = aggregate
        .checked_add(before.len())
        .filter(|value| *value <= MAX_TREE_BYTES)
        .ok_or(ExitClass::Invalid)?;
    let mut raw =
        Vec::with_capacity(usize::try_from(before.len()).map_err(|_| ExitClass::Invalid)?);
    File::open(path)
        .map_err(|_| ExitClass::Invalid)?
        .take(MAX_FILE_BYTES + 1)
        .read_to_end(&mut raw)
        .map_err(|_| ExitClass::Invalid)?;
    let after = fs::symlink_metadata(path).map_err(|_| ExitClass::Invalid)?;
    if raw.len() as u64 != before.len()
        || after.len() != before.len()
        || !after.file_type().is_file()
        || !exactly_one_link(&after)
    {
        return Err(ExitClass::Invalid);
    }
    Ok(raw)
}

fn validate_source_root() -> CliResult<PathBuf> {
    let current = std::env::current_dir().map_err(|_| ExitClass::Invalid)?;
    let canonical = fs::canonicalize(&current).map_err(|_| ExitClass::Invalid)?;
    if current != canonical {
        return Err(ExitClass::Invalid);
    }
    reject_linked_directory_chain(&canonical)?;
    let mut aggregate = 0;
    let owner = read_regular(&canonical.join("spec/gate8-policy-v0.toml"), &mut aggregate)?;
    let refresh_owner = read_regular(
        &canonical.join("spec/gate8-verifier-refresh-v0.toml"),
        &mut aggregate,
    )?;
    if owner != OWNER_RAW || refresh_owner != REFRESH_OWNER_RAW {
        return Err(ExitClass::Invalid);
    }
    Ok(canonical)
}

fn directory_names(directory: &Path) -> CliResult<Vec<String>> {
    let mut names = fs::read_dir(directory)
        .map_err(|_| ExitClass::Invalid)?
        .map(|entry| {
            entry
                .map_err(|_| ExitClass::Invalid)?
                .file_name()
                .into_string()
                .map_err(|_| ExitClass::Invalid)
        })
        .collect::<CliResult<Vec<_>>>()?;
    names.sort_by(|left, right| left.as_bytes().cmp(right.as_bytes()));
    if names.windows(2).any(|rows| rows[0] >= rows[1]) {
        return Err(ExitClass::Invalid);
    }
    Ok(names)
}

fn allowed_receipt_names(producer_id: &str) -> &'static [&'static str] {
    match producer_id {
        "native-rust" => &[
            "native-python.json",
            "native-rust.json",
            "linux-python.json",
            "linux-rust.json",
        ],
        "linux-rust" => &["linux-python.json", "linux-rust.json"],
        _ => &[],
    }
}

fn producer_from_receipt_name(name: &str) -> Option<&'static str> {
    let id = name.strip_suffix(".json")?;
    GATE8_PRODUCER_IDS
        .iter()
        .copied()
        .find(|value| *value == id)
}

fn validate_output_directory(arguments: &Arguments) -> CliResult<Option<Vec<u8>>> {
    reject_linked_directory_chain(&arguments.output_directory)?;
    let metadata =
        fs::symlink_metadata(&arguments.output_directory).map_err(|_| ExitClass::Invalid)?;
    if !metadata.file_type().is_dir()
        || metadata.file_type().is_symlink()
        || !directory_is_private(&metadata)
    {
        return Err(ExitClass::Invalid);
    }
    let own_name = format!("{}.json", arguments.producer_id);
    let allowed = allowed_receipt_names(arguments.producer_id);
    let mut own = None;
    let mut aggregate = 0;
    for name in directory_names(&arguments.output_directory)? {
        if !allowed.contains(&name.as_str()) {
            return Err(ExitClass::Invalid);
        }
        let producer = producer_from_receipt_name(&name).ok_or(ExitClass::Invalid)?;
        let raw = read_regular(&arguments.output_directory.join(&name), &mut aggregate)?;
        admit_gate8_producer_receipt(&raw, producer).map_err(|_| ExitClass::Invalid)?;
        if name == own_name {
            own = Some(raw);
        }
    }
    match (arguments.mode, own) {
        (Mode::Generate, None) => Ok(None),
        (Mode::Check, Some(raw)) => Ok(Some(raw)),
        _ => Err(ExitClass::Invalid),
    }
}

fn validate_candidate_structure(arguments: &Arguments, source_root: &Path) -> CliResult<()> {
    reject_linked_directory_chain(&arguments.candidate_root)?;
    let metadata =
        fs::symlink_metadata(&arguments.candidate_root).map_err(|_| ExitClass::Invalid)?;
    if !metadata.file_type().is_dir()
        || metadata.file_type().is_symlink()
        || !directory_is_private(&metadata)
        || arguments.candidate_root.starts_with(source_root)
        || arguments.output_directory.starts_with(source_root)
        || arguments
            .candidate_root
            .starts_with(&arguments.output_directory)
        || arguments
            .output_directory
            .starts_with(&arguments.candidate_root)
    {
        return Err(ExitClass::Invalid);
    }
    if !directory_names(&arguments.candidate_root)?.is_empty() {
        return Err(ExitClass::Invalid);
    }
    Ok(())
}

fn expected_damage_names() -> Vec<String> {
    let mut expected_damage = vec!["damage-manifest.json".to_owned()];
    expected_damage.extend((0..8).map(|family| format!("damage-D{family}.json")));
    for (family, count) in [1_usize, 1, 2, 3, 11, 1, 41, 3].into_iter().enumerate() {
        expected_damage
            .extend((0..count).map(|ordinal| format!("damage-D{family}-cases-{ordinal:04}.json")));
    }
    expected_damage.push("independence-proof.json".to_owned());
    expected_damage.sort_by(|left, right| left.as_bytes().cmp(right.as_bytes()));
    expected_damage
}

#[cfg(unix)]
fn set_private_file_permissions(file: &File) -> io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    file.set_permissions(fs::Permissions::from_mode(0o600))
}

#[cfg(not(unix))]
fn set_private_file_permissions(_file: &File) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "private Gate 8 files require Unix permissions",
    ))
}

#[cfg(unix)]
fn set_private_directory_permissions(path: &Path) -> io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))
}

#[cfg(not(unix))]
fn set_private_directory_permissions(_path: &Path) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "private Gate 8 directories require Unix permissions",
    ))
}

fn write_new_regular(path: &Path, raw: &[u8]) -> CliResult<()> {
    if raw.is_empty() || raw.len() as u64 > MAX_FILE_BYTES {
        return Err(ExitClass::Generation);
    }
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|_| ExitClass::Generation)?;
    set_private_file_permissions(&file).map_err(|_| ExitClass::Generation)?;
    file.write_all(raw).map_err(|_| ExitClass::Generation)?;
    file.sync_all().map_err(|_| ExitClass::Generation)?;
    Ok(())
}

fn materialize_private_candidate(
    candidate_root: &Path,
    gates: &R3GateOneThroughFive,
    gate_six_seven: &Gate8GateSixSevenFactsV1,
) -> CliResult<()> {
    write_new_regular(
        &candidate_root.join("candidate-manifest.json"),
        &gates.artifacts.candidate_manifest,
    )?;
    write_new_regular(
        &candidate_root.join("capacity-ledger.json"),
        &gates.artifacts.capacity_ledger,
    )?;
    write_new_regular(
        &candidate_root.join("carrier.obs-bits"),
        &gates.core.carrier_bytes,
    )?;
    write_new_regular(
        &candidate_root.join("density-ledger.json"),
        &gates.artifacts.density_ledger,
    )?;
    write_new_regular(
        &candidate_root.join("ownership-ledger.json"),
        &gates.artifacts.ownership_ledger,
    )?;
    write_new_regular(
        &candidate_root.join("semantic-envelope.json"),
        gates.semantic.canonical_bytes(),
    )?;
    let damage = candidate_root.join("damage");
    fs::create_dir(&damage).map_err(|_| ExitClass::Generation)?;
    set_private_directory_permissions(&damage).map_err(|_| ExitClass::Generation)?;
    write_new_regular(
        &damage.join("damage-manifest.json"),
        &gate_six_seven.damage_bundle.damage_manifest,
    )?;
    for (family, raw) in gate_six_seven
        .damage_bundle
        .family_manifests
        .iter()
        .enumerate()
    {
        write_new_regular(&damage.join(format!("damage-D{family}.json")), raw)?;
    }
    for (name, raw) in &gate_six_seven.damage_bundle.case_shards {
        write_new_regular(&damage.join(name), raw)?;
    }
    write_new_regular(
        &damage.join("independence-proof.json"),
        &gate_six_seven.independence_proof.canonical_bytes,
    )?;
    File::open(&damage)
        .and_then(|file| file.sync_all())
        .and_then(|_| File::open(candidate_root))
        .and_then(|file| file.sync_all())
        .map_err(|_| ExitClass::Generation)?;
    Ok(())
}

fn compare_file(path: &Path, expected: &[u8], aggregate: &mut u64) -> CliResult<()> {
    if read_regular(path, aggregate)? != expected {
        return Err(ExitClass::Invalid);
    }
    Ok(())
}

fn validate_private_candidate_bytes(
    candidate_root: &Path,
    gates: &R3GateOneThroughFive,
    gate_six_seven: &Gate8GateSixSevenFactsV1,
) -> CliResult<()> {
    let expected_root = [
        "candidate-manifest.json",
        "capacity-ledger.json",
        "carrier.obs-bits",
        "damage",
        "density-ledger.json",
        "ownership-ledger.json",
        "semantic-envelope.json",
    ];
    if directory_names(candidate_root)? != expected_root {
        return Err(ExitClass::Invalid);
    }
    let damage = candidate_root.join("damage");
    reject_linked_directory_chain(&damage)?;
    if directory_names(&damage)? != expected_damage_names() {
        return Err(ExitClass::Invalid);
    }
    let mut aggregate = 0_u64;
    compare_file(
        &candidate_root.join("candidate-manifest.json"),
        &gates.artifacts.candidate_manifest,
        &mut aggregate,
    )?;
    compare_file(
        &candidate_root.join("capacity-ledger.json"),
        &gates.artifacts.capacity_ledger,
        &mut aggregate,
    )?;
    compare_file(
        &candidate_root.join("carrier.obs-bits"),
        &gates.core.carrier_bytes,
        &mut aggregate,
    )?;
    compare_file(
        &candidate_root.join("density-ledger.json"),
        &gates.artifacts.density_ledger,
        &mut aggregate,
    )?;
    compare_file(
        &candidate_root.join("ownership-ledger.json"),
        &gates.artifacts.ownership_ledger,
        &mut aggregate,
    )?;
    compare_file(
        &candidate_root.join("semantic-envelope.json"),
        gates.semantic.canonical_bytes(),
        &mut aggregate,
    )?;
    compare_file(
        &damage.join("damage-manifest.json"),
        &gate_six_seven.damage_bundle.damage_manifest,
        &mut aggregate,
    )?;
    for (family, raw) in gate_six_seven
        .damage_bundle
        .family_manifests
        .iter()
        .enumerate()
    {
        compare_file(
            &damage.join(format!("damage-D{family}.json")),
            raw,
            &mut aggregate,
        )?;
    }
    for (name, raw) in &gate_six_seven.damage_bundle.case_shards {
        compare_file(&damage.join(name), raw, &mut aggregate)?;
    }
    compare_file(
        &damage.join("independence-proof.json"),
        &gate_six_seven.independence_proof.canonical_bytes,
        &mut aggregate,
    )?;
    Ok(())
}

fn remove_owned_regular(path: &Path) -> CliResult<()> {
    match fs::symlink_metadata(path) {
        Ok(metadata)
            if metadata.file_type().is_file()
                && !metadata.file_type().is_symlink()
                && exactly_one_link(&metadata) =>
        {
            fs::remove_file(path).map_err(|_| ExitClass::Generation)
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        _ => Err(ExitClass::Generation),
    }
}

fn cleanup_candidate_root(candidate_root: &Path) -> CliResult<()> {
    let mut failed = false;
    let damage = candidate_root.join("damage");
    if let Ok(metadata) = fs::symlink_metadata(&damage) {
        if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
            failed = true;
        } else {
            for name in expected_damage_names() {
                if remove_owned_regular(&damage.join(name)).is_err() {
                    failed = true;
                }
            }
            match directory_names(&damage) {
                Ok(names) if names.is_empty() => {
                    if fs::remove_dir(&damage).is_err() {
                        failed = true;
                    }
                }
                _ => failed = true,
            }
        }
    }
    for name in [
        "candidate-manifest.json",
        "capacity-ledger.json",
        "carrier.obs-bits",
        "density-ledger.json",
        "ownership-ledger.json",
        "semantic-envelope.json",
    ] {
        if remove_owned_regular(&candidate_root.join(name)).is_err() {
            failed = true;
        }
    }
    match directory_names(candidate_root) {
        Ok(names) if names.is_empty() => {}
        _ => failed = true,
    }
    if File::open(candidate_root)
        .and_then(|file| file.sync_all())
        .is_err()
    {
        failed = true;
    }
    if failed {
        Err(ExitClass::Generation)
    } else {
        Ok(())
    }
}

fn generate_receipt(arguments: &Arguments) -> CliResult<Vec<u8>> {
    let facts = regenerate_current_r3_gate8_facts().map_err(|_| ExitClass::Generation)?;
    let gate_six_seven =
        render_r3_gate_six_seven_facts(&facts.gates_one_through_five, &facts.case_facts)
            .map_err(|_| ExitClass::Generation)?;
    if let Err(error) = materialize_private_candidate(
        &arguments.candidate_root,
        &facts.gates_one_through_five,
        &gate_six_seven,
    ) {
        let _ = cleanup_candidate_root(&arguments.candidate_root);
        return Err(error);
    }
    let result = (|| {
        validate_private_candidate_bytes(
            &arguments.candidate_root,
            &facts.gates_one_through_five,
            &gate_six_seven,
        )
        .map_err(|_| ExitClass::Generation)?;
        render_rust_gate8_receipt(
            &facts.gates_one_through_five,
            &gate_six_seven,
            arguments.producer_id,
        )
        .map(|receipt| receipt.canonical_bytes)
        .map_err(|_| ExitClass::Generation)
    })();
    let cleanup = cleanup_candidate_root(&arguments.candidate_root);
    match (result, cleanup) {
        (Ok(raw), Ok(())) => Ok(raw),
        (Err(error), _) => Err(error),
        (_, Err(error)) => Err(error),
    }
}

fn atomically_create_receipt(directory: &Path, name: &str, raw: &[u8]) -> CliResult<()> {
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| ExitClass::Generation)?
        .as_nanos();
    let stage = directory.join(format!(
        ".gb-m2-gate8-{}-{}-{nonce}.tmp",
        std::process::id(),
        name.trim_end_matches(".json")
    ));
    let destination = directory.join(name);
    let result = (|| -> io::Result<()> {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&stage)?;
        file.write_all(raw)?;
        file.sync_all()?;
        fs::hard_link(&stage, &destination)?;
        fs::remove_file(&stage)?;
        File::open(directory)?.sync_all()?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&stage);
        return Err(ExitClass::Generation);
    }
    let mut aggregate = 0;
    if read_regular(&destination, &mut aggregate)? != raw {
        return Err(ExitClass::Generation);
    }
    Ok(())
}

fn run_with(arguments: Vec<OsString>) -> CliResult<()> {
    let arguments = parse_arguments(arguments)?;
    let source_root = validate_source_root()?;
    validate_output_directory(&arguments)?;
    validate_candidate_structure(&arguments, &source_root)?;
    let generated = generate_receipt(&arguments)?;
    let existing = validate_output_directory(&arguments)?;
    match arguments.mode {
        Mode::Generate => atomically_create_receipt(
            &arguments.output_directory,
            &format!("{}.json", arguments.producer_id),
            &generated,
        ),
        Mode::Check => {
            if existing.as_deref() != Some(generated.as_slice()) {
                return Err(ExitClass::Generation);
            }
            Ok(())
        }
    }
}

fn main() {
    let arguments = std::env::args_os().skip(1).collect::<Vec<_>>();
    match run_with(arguments) {
        Ok(()) => {}
        Err(ExitClass::Invalid) => {
            eprintln!("Gate 8 producer rejected invalid input");
            std::process::exit(2);
        }
        Err(ExitClass::Generation) => {
            eprintln!("Gate 8 producer generation or check failed");
            std::process::exit(3);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use sha2::{Digest, Sha256};

    fn temporary_directory(label: &str) -> PathBuf {
        let path = std::env::temp_dir().join(format!(
            "golden-board-gate8-{label}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir(&path).unwrap();
        set_private_directory_permissions(&path).unwrap();
        fs::canonicalize(path).unwrap()
    }

    fn receipt(producer_id: &str) -> Vec<u8> {
        let rows = [
            "semantic-content-projection",
            "candidate-manifest",
            "carrier",
            "ownership-ledger",
            "capacity-ledger",
            "density-ledger",
            "damage-bundle-inventory",
            "independence-proof",
        ]
        .into_iter()
        .enumerate()
        .map(|(ordinal, artifact_id)| {
            format!("{{\"artifact_id\":\"{artifact_id}\",\"sha256\":\"{ordinal:064x}\"}}")
        })
        .collect::<Vec<_>>()
        .join(",");
        format!(
            "{{\"artifact_rows\":[{rows}],\"candidate_id\":\"eh72-hier-r5-r2-r1-crc32c-v0\",\"producer_id\":\"{producer_id}\",\"schema\":\"golden-board.m2-gate8-producer-receipt/v0\"}}\n"
        )
        .into_bytes()
    }

    fn arguments(mode: &str, producer: &str, candidate: &Path, output: &Path) -> Vec<OsString> {
        [
            OsString::from("producer"),
            OsString::from("--mode"),
            OsString::from(mode),
            OsString::from("--producer-id"),
            OsString::from(producer),
            OsString::from("--candidate-root"),
            candidate.as_os_str().to_owned(),
            OsString::from("--output-dir"),
            output.as_os_str().to_owned(),
        ]
        .into()
    }

    #[test]
    fn embedded_gate8_owner_is_the_final_preimage() {
        assert_eq!(OWNER_RAW.len(), 87_506);
        assert_eq!(
            format!("{:x}", Sha256::digest(OWNER_RAW)),
            "fd53145eeb5d0d5578b8cb1aff980039c999839516528b309a626dd62e52794e"
        );
        assert_eq!(REFRESH_OWNER_RAW.len(), 36_105);
        assert_eq!(
            format!("{:x}", Sha256::digest(REFRESH_OWNER_RAW)),
            "8b01c255d948f46ea4fb30b16160af00c416cb087dddc9c62ac768a989772116"
        );
    }

    #[test]
    fn argv_is_exact_and_rejects_unknown_producers_or_order() {
        let candidate = Path::new("/private/tmp/candidate");
        let output = Path::new("/private/tmp/output");
        assert_eq!(
            parse_arguments(arguments("generate", "native-rust", candidate, output))
                .unwrap()
                .producer_id,
            "native-rust"
        );
        assert_eq!(
            parse_arguments(arguments("check", "linux-rust", candidate, output))
                .unwrap()
                .mode,
            Mode::Check
        );
        assert!(parse_arguments(arguments("run", "native-rust", candidate, output)).is_err());
        assert!(
            parse_arguments(arguments("generate", "native-python", candidate, output)).is_err()
        );
        let mut reordered = arguments("generate", "native-rust", candidate, output);
        reordered.swap(1, 3);
        assert!(parse_arguments(reordered).is_err());
        let mut extra = arguments("generate", "native-rust", candidate, output);
        extra.push(OsString::from("extra"));
        assert!(parse_arguments(extra).is_err());
    }

    #[test]
    fn environment_receipt_name_sets_are_exact() {
        assert_eq!(
            allowed_receipt_names("native-rust"),
            [
                "native-python.json",
                "native-rust.json",
                "linux-python.json",
                "linux-rust.json"
            ]
        );
        assert_eq!(
            allowed_receipt_names("linux-rust"),
            ["linux-python.json", "linux-rust.json"]
        );
        assert!(allowed_receipt_names("native-python").is_empty());
    }

    #[test]
    fn shared_receipt_directory_enforces_phase_environment_and_atomic_no_overwrite() {
        let candidate = temporary_directory("receipt-candidate");
        let output = temporary_directory("receipt-output");
        let native =
            parse_arguments(arguments("generate", "native-rust", &candidate, &output)).unwrap();
        assert_eq!(validate_output_directory(&native).unwrap(), None);
        write_new_regular(
            &output.join("native-python.json"),
            &receipt("native-python"),
        )
        .unwrap();
        assert_eq!(validate_output_directory(&native).unwrap(), None);

        let own = receipt("native-rust");
        atomically_create_receipt(&output, "native-rust.json", &own).unwrap();
        let check = Arguments {
            mode: Mode::Check,
            ..native.clone()
        };
        assert_eq!(
            validate_output_directory(&check).unwrap(),
            Some(own.clone())
        );
        assert_eq!(
            atomically_create_receipt(&output, "native-rust.json", b"replacement\n"),
            Err(ExitClass::Generation)
        );
        assert_eq!(fs::read(output.join("native-rust.json")).unwrap(), own);
        assert_eq!(directory_names(&output).unwrap().len(), 2);

        let linux = Arguments {
            producer_id: "linux-rust",
            mode: Mode::Generate,
            candidate_root: candidate.clone(),
            output_directory: output.clone(),
        };
        assert_eq!(validate_output_directory(&linux), Err(ExitClass::Invalid));
        fs::remove_file(output.join("native-python.json")).unwrap();
        fs::remove_file(output.join("native-rust.json")).unwrap();
        fs::remove_dir(output).unwrap();
        fs::remove_dir(candidate).unwrap();
    }

    #[test]
    fn private_work_root_must_be_empty_and_cleanup_never_follows_extras() {
        let candidate = temporary_directory("work-root");
        let output = temporary_directory("work-output");
        let parsed =
            parse_arguments(arguments("generate", "native-rust", &candidate, &output)).unwrap();
        let source = fs::canonicalize(std::env::current_dir().unwrap()).unwrap();
        validate_candidate_structure(&parsed, &source).unwrap();
        write_new_regular(&candidate.join("candidate-manifest.json"), b"{}\n").unwrap();
        assert_eq!(
            validate_candidate_structure(&parsed, &source),
            Err(ExitClass::Invalid)
        );
        fs::create_dir(candidate.join("damage")).unwrap();
        set_private_directory_permissions(&candidate.join("damage")).unwrap();
        write_new_regular(&candidate.join("damage/damage-manifest.json"), b"{}\n").unwrap();
        cleanup_candidate_root(&candidate).unwrap();
        assert!(directory_names(&candidate).unwrap().is_empty());

        write_new_regular(&candidate.join("unexpected"), b"x").unwrap();
        assert_eq!(
            cleanup_candidate_root(&candidate),
            Err(ExitClass::Generation)
        );
        assert!(candidate.join("unexpected").is_file());
        fs::remove_file(candidate.join("unexpected")).unwrap();
        fs::remove_dir(output).unwrap();
        fs::remove_dir(candidate).unwrap();
    }
}
