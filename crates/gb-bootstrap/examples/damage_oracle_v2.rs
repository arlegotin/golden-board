//! Independent source-oracle development comparison; no gate or promotion claim.
use gb_bootstrap::damage::{ArtifactState, FragmentState, SectionState};
#[cfg(test)]
use gb_bootstrap::replay_backend_v2::checked_receiver_row;
use gb_bootstrap::replay_backend_v2::{ordered_cases, replay_workers};
use gb_foundation::{ManifestValue as V, serialize_manifest};
use sha2::{Digest, Sha256};
use std::error::Error;
use std::fs::{self, OpenOptions};
use std::io::{BufWriter, Read, Write};
use std::path::Path;
fn string(s: &str) -> V {
    V::String(s.into())
}
fn hash(raw: Option<&[u8]>) -> V {
    string(
        &raw.map(|raw| format!("{:x}", Sha256::digest(raw)))
            .unwrap_or_else(|| "0".repeat(64)),
    )
}
fn artifact(s: ArtifactState) -> &'static str {
    match s {
        ArtifactState::Exact => "exact",
        ArtifactState::Degraded => "degraded",
        ArtifactState::Failure => "failure",
        ArtifactState::Ambiguous => "ambiguous",
        ArtifactState::ResourceLimit => "resource-limit",
    }
}
fn section(s: SectionState) -> &'static str {
    match s {
        SectionState::Verified => "verified",
        SectionState::Recovered => "recovered",
        SectionState::Incomplete => "incomplete",
        SectionState::Corrupt => "corrupt",
        SectionState::Ambiguous => "ambiguous",
        SectionState::Unknown => "unknown",
    }
}
fn fragment(s: FragmentState) -> &'static str {
    match s {
        FragmentState::Verified => "verified",
        FragmentState::Recovered => "recovered",
        FragmentState::Missing => "missing",
        FragmentState::Corrupt => "corrupt",
        FragmentState::Ambiguous => "ambiguous",
        FragmentState::Unknown => "unknown",
    }
}
fn profile(v: Option<u16>) -> String {
    match v {
        None => String::new(),
        Some(8) => "eh72-hier-r5-r2-r1-lzss-crc32c-v1".into(),
        Some(v) => gb_bootstrap::candidate::profile_by_version(v)
            .unwrap()
            .id
            .into(),
    }
}
fn source_corpus() -> Result<gb_bootstrap::damage_corpus_v2::DamageCorpusV2, Box<dyn Error>> {
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
    let carrier =
        gb_bootstrap::carrier_v2::build_carrier(&slice).map_err(|e| format!("carrier: {e:?}"))?;
    let corpus = gb_bootstrap::damage_corpus_v2::DamageCorpusV2::new(
        &slice,
        &carrier,
        include_bytes!("../../../spec/route-data-v0.json"),
    )
    .map_err(|e| format!("corpus: {e:?}"))?;
    Ok(corpus)
}

fn run() -> Result<(), Box<dyn Error>> {
    let mut args: Vec<_> = std::env::args_os().skip(1).collect();
    let receiver = args.first().is_some_and(|arg| arg == "--receiver");
    if receiver {
        args.remove(0);
    }
    let complete = args.len() == 2 && args[0] == "--complete";
    let replay = matches!(args.len(), 4 | 6)
        && args[0] == "--replay"
        && args[1] == "--selection"
        && (args[2] == "preflight" || args[2] == "all")
        && (args.len() == 4 || args[3] == "--workers");
    if (args.len() != 1 && !complete && !replay) || (receiver && !replay) {
        return Err("usage: damage_oracle_v2 [--receiver] [--complete | --replay --selection preflight|all [--workers 1..8]] ABSOLUTE_NEW_PRIVATE_PATH".into());
    }
    let workers = if replay && args.len() == 6 {
        let value = args[4].to_str().ok_or("worker count ASCII")?;
        if value.len() != 1 || !(b'1'..=b'8').contains(&value.as_bytes()[0]) {
            return Err("workers must be1..8".into());
        }
        usize::from(value.as_bytes()[0] - b'0')
    } else {
        1
    };
    let path = Path::new(
        &args[if replay {
            args.len() - 1
        } else {
            usize::from(complete)
        }],
    );
    if !path.is_absolute() || path.file_name().is_none() {
        return Err("absolute new private path required".into());
    }
    if replay {
        check_preimages()?;
        if receiver {
            check_compiled_sources()?;
        }
    }
    for ancestor in path.parent().ok_or("parent")?.ancestors() {
        let meta = fs::symlink_metadata(ancestor)?;
        if !meta.is_dir() || meta.file_type().is_symlink() {
            return Err("real directory ancestors required".into());
        }
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if fs::metadata(path.parent().ok_or("parent")?)?
            .permissions()
            .mode()
            & 0o077
            != 0
        {
            return Err("private output parent required".into());
        }
    }
    let executable = if receiver {
        let path = std::env::current_exe()?;
        check_private_executable(&path)?;
        let hash = file_hash(&path)?;
        Some((path, hash))
    } else {
        None
    };
    let corpus = source_corpus()?;
    if replay {
        return run_replay(
            &corpus,
            path,
            args[2] == "all",
            workers,
            receiver,
            executable,
        );
    }
    let oracle = gb_bootstrap::damage_oracle_v2::SemanticOracleV2::new(&corpus);
    let full = if complete {
        Some(
            gb_bootstrap::damage_oracle_v2::FullOracleV2::new(&corpus)
                .map_err(|e| format!("full oracle: {e:?}"))?,
        )
    } else {
        None
    };
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    if complete {
        let mut builder = fs::DirBuilder::new();
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            builder.mode(0o700);
        }
        builder.create(path)?;
    }
    let semantic_path = if complete {
        path.join("semantic.jsonl")
    } else {
        path.to_path_buf()
    };
    let mut out = BufWriter::new(options.open(semantic_path)?);
    let mut count = 0;
    for (family, ordinals) in [
        ("D0", vec![0, 7]),
        ("D1", vec![0]),
        ("D2", vec![0]),
        ("D3", vec![0, 96]),
        ("D4", vec![0]),
        ("D6", vec![0]),
        ("D7", vec![0, 10, 16, 401, 402, 405, 408, 413, 414]),
        ("B0", (0..21).collect()),
    ] {
        for ordinal in ordinals {
            let case = corpus
                .case(family, ordinal)
                .map_err(|e| format!("case: {e:?}"))?;
            let value = oracle
                .project(family, ordinal, case.bytes())
                .map_err(|e| format!("oracle {family}-{ordinal}: {e:?}"))?;
            if let Some(full) = &full {
                let projected = full
                    .project(family, ordinal, case.bytes())
                    .map_err(|e| format!("full {family}-{ordinal}: {e:?}"))?;
                if projected.semantic() != &value {
                    return Err(
                        format!("full/partial semantic disagreement {family}-{ordinal}").into(),
                    );
                }
                for (suffix, bytes) in [
                    ("result", projected.result_bytes()),
                    ("resources", projected.resource_bytes()),
                ] {
                    let mut file =
                        options.open(path.join(format!("{family}-{ordinal:06}-{suffix}.json")))?;
                    file.write_all(bytes)?;
                    file.sync_all()?;
                }
            }
            let row = V::Object(
                [
                    ("case_id", string(&format!("{family}-{ordinal:06}"))),
                    ("artifact_state", string(artifact(value.artifact_state()))),
                    (
                        "section_states",
                        V::Array(
                            value
                                .section_states()
                                .iter()
                                .map(|(id, state)| {
                                    V::Array(vec![V::U64(u64::from(*id)), string(section(*state))])
                                })
                                .collect(),
                        ),
                    ),
                    ("wrong_accepts", V::U64(value.wrong_accepts())),
                    ("reauthored_boundary", V::Bool(value.reauthored_boundary())),
                    ("required_sha256", hash(value.required_stream())),
                    ("all_sha256", hash(value.all_stream())),
                    (
                        "sections",
                        V::Array(
                            value
                                .sections()
                                .iter()
                                .map(|s| {
                                    V::Array(vec![
                                        V::U64(u64::from(s.section_id)),
                                        string(section(s.state)),
                                        hash(s.envelope.as_deref()),
                                    ])
                                })
                                .collect(),
                        ),
                    ),
                    (
                        "fragments",
                        V::Array(
                            value
                                .fragments()
                                .iter()
                                .map(|f| {
                                    V::Array(vec![
                                        V::U64(u64::from(f.input_id)),
                                        string(&profile(f.profile_version)),
                                        V::U64(u64::from(f.section_id)),
                                        V::U64(u64::from(f.semantic_copy_id)),
                                        V::U64(u64::from(f.fragment_index)),
                                        V::U64(u64::from(f.replica_index)),
                                        V::U64(u64::from(f.physical_replica_count)),
                                        string(fragment(f.state)),
                                        string(&f.common_block_sha256),
                                    ])
                                })
                                .collect(),
                        ),
                    ),
                ]
                .into_iter()
                .map(|(k, v)| (k.to_owned(), v))
                .collect(),
            );
            out.write_all(&serialize_manifest(&row)?)?;
            count += 1;
            eprintln!(
                "{family}-{ordinal:06}: {}",
                artifact(value.artifact_state())
            );
        }
    }
    out.flush()?;
    out.get_ref().sync_all()?;
    if count != 38 {
        return Err("incomplete comparison".into());
    }
    eprintln!(
        "38 source-derived rows; complete={complete}; no production receiver input or gate receipt"
    );
    Ok(())
}

macro_rules! input {
    ($name:literal) => {
        ($name, &include_bytes!(concat!("../../../", $name))[..])
    };
}
fn preimages() -> Vec<(&'static str, &'static [u8])> {
    vec![
        input!("studies/m2/slice-v0.json"),
        input!("studies/m2/slice-v1.json"),
        input!("conformance/content-v0.json"),
        input!("conformance/chess-v0.json"),
        input!("reports/game-set-v0.bin"),
        input!("spec/content-v0.md"),
        input!("spec/constants-v0.toml"),
        input!("spec/curriculum-v0.toml"),
        input!("spec/route-data-v0.json"),
        input!("spec/profile-policy-v0.toml"),
        input!("spec/recipe-teaching-v2.toml"),
        input!("spec/profile-policy-v2.toml"),
        input!("spec/profile-limits-v2.toml"),
        input!("spec/damage-policy-v2.toml"),
        input!("spec/resource-accounting-v2.md"),
        input!("spec/damage-replay-v2.md"),
    ]
}
fn check_preimages() -> Result<(), Box<dyn Error>> {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .ok_or("source root")?;
    for (path, expected) in preimages() {
        let path = root.join(path);
        let metadata = fs::symlink_metadata(&path)?;
        if !metadata.is_file()
            || metadata.file_type().is_symlink()
            || metadata.len() != expected.len() as u64
        {
            return Err(format!("compiled source preimage changed: {}", path.display()).into());
        }
        let mut actual = Vec::with_capacity(expected.len());
        fs::File::open(&path)?
            .take(expected.len() as u64 + 1)
            .read_to_end(&mut actual)?;
        if actual != expected {
            return Err(format!("compiled source preimage changed: {}", path.display()).into());
        }
    }
    Ok(())
}
fn file_hash(path: &Path) -> Result<String, Box<dyn Error>> {
    let mut file = fs::File::open(path)?;
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 65536];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        hash.update(&buffer[..count]);
    }
    Ok(format!("{:x}", hash.finalize()))
}
fn run_replay(
    corpus: &gb_bootstrap::damage_corpus_v2::DamageCorpusV2,
    path: &Path,
    all: bool,
    workers: usize,
    receiver: bool,
    executable: Option<(std::path::PathBuf, String)>,
) -> Result<(), Box<dyn Error>> {
    check_preimages()?;
    let compiled_sources = if receiver {
        Some(check_compiled_sources()?)
    } else {
        None
    };
    let (binary, binary_hash) = if let Some(identity) = executable {
        identity
    } else if receiver {
        return Err("missing pre-generation executable identity".into());
    } else {
        let binary = std::env::current_exe()?;
        let hash = file_hash(&binary)?;
        (binary, hash)
    };
    let selected = ordered_cases(corpus, all)?;
    let staged = if receiver {
        Some(ReplayOutput::new(path)?)
    } else {
        None
    };
    let output_path = staged.as_ref().map_or(path, |value| value.path.as_path());
    let mut builder = fs::DirBuilder::new();
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        builder.mode(0o700);
    }
    if !receiver {
        builder.create(path)?;
    }
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut rows = BufWriter::new(options.open(output_path.join("cases.jsonl"))?);
    let mut identities = BufWriter::new(options.open(output_path.join("identities.jsonl"))?);
    let (mut row_hash, mut identity_hash) = (Sha256::new(), Sha256::new());
    let (mut row_bytes, mut identity_bytes, mut failures) = (0u64, 0u64, 0u64);
    let start = std::time::Instant::now();
    replay_workers(
        corpus,
        &selected,
        workers,
        receiver,
        |index, identity, row| {
            let (family, ordinal) = selected[index];
            if row.len() > 1_048_576 || !row.ends_with(b"\n") {
                return Err("invalid bounded replay row".into());
            }
            let V::Object(value) = gb_foundation::validate_canonical_manifest(&row)? else {
                return Err("row object".into());
            };
            if value.get("promise_result") == Some(&string("fail")) {
                failures += 1;
            }
            rows.write_all(&row)?;
            identities.write_all(&identity)?;
            row_hash.update(&row);
            identity_hash.update(&identity);
            row_bytes = row_bytes
                .checked_add(row.len() as u64)
                .ok_or("row byte overflow")?;
            identity_bytes = identity_bytes
                .checked_add(identity.len() as u64)
                .ok_or("identity byte overflow")?;
            if !all || index % 64 == 0 {
                eprintln!(
                    "replay {}/{} {family}-{ordinal:06}, {}s",
                    index + 1,
                    selected.len(),
                    start.elapsed().as_secs()
                );
            }
            Ok(())
        },
    )?;
    rows.flush()?;
    identities.flush()?;
    rows.get_ref().sync_all()?;
    identities.get_ref().sync_all()?;
    let corpus_sha = format!("{:x}", identity_hash.finalize());
    let resource_limits = if receiver {
        Some(aggregate_streamed_resources(
            &output_path.join("cases.jsonl"),
            &selected,
            &corpus_sha,
        )?)
    } else {
        None
    };
    if let Some(raw) = &resource_limits {
        let mut file = options.open(output_path.join("resource-limits.json"))?;
        file.write_all(raw)?;
        file.sync_all()?;
    }
    check_preimages()?;
    if receiver && compiled_sources.as_ref() != Some(&check_compiled_sources()?) {
        return Err("compiled source changed during replay".into());
    }
    if file_hash(&binary)? != binary_hash {
        return Err("producer executable changed during replay".into());
    }
    if receiver {
        check_private_executable(&binary)?;
    }
    let owners = V::Object(
        preimages()
            .into_iter()
            .map(|(name, raw)| (name.to_owned(), hash(Some(raw))))
            .collect(),
    );
    let value = V::Object(
        [
            ("selection", string(if all { "all" } else { "preflight" })),
            ("case_count", V::U64(selected.len() as u64)),
            (
                "case_ids",
                V::Array(
                    selected
                        .iter()
                        .map(|(f, n)| string(&format!("{f}-{n:06}")))
                        .collect(),
                ),
            ),
            ("row_bytes", V::U64(row_bytes)),
            ("row_sha256", string(&format!("{:x}", row_hash.finalize()))),
            ("identity_bytes", V::U64(identity_bytes)),
            ("identity_sha256", string(&corpus_sha)),
            ("promise_failures", V::U64(failures)),
            ("source_preimages", owners),
            ("executable_sha256", string(&binary_hash)),
            ("workers", V::U64(workers as u64)),
            (
                "evidence_scope",
                string(if receiver {
                    "same-language-rust-source-oracle-and-observation-receiver-no-gate"
                } else {
                    "development-source-oracle-no-gate"
                }),
            ),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_owned(), v))
        .collect(),
    );
    let mut value = value;
    if let V::Object(fields) = &mut value {
        if let Some(source) = compiled_sources {
            fields.insert("compiled_rust_sources".into(), source);
        }
        if let Some(raw) = &resource_limits {
            fields.insert("resource_limits_sha256".into(), hash(Some(raw)));
        }
    }
    let mut summary = options.open(output_path.join("summary.json"))?;
    summary.write_all(&serialize_manifest(&value)?)?;
    summary.sync_all()?;
    drop(summary);
    drop(rows);
    drop(identities);
    if let Some(stage) = staged {
        stage.publish()?;
    }
    eprintln!(
        "complete {}-case development source replay; promise failures={failures}; no gate awarded",
        selected.len()
    );
    Ok(())
}
fn main() {
    if let Err(error) = run() {
        eprintln!("damage-oracle-v2: {error}");
        std::process::exit(2)
    }
}

#[path = "../replay_source.rs"]
mod replay_source;
include!(concat!(env!("OUT_DIR"), "/replay-source-preimages.rs"));
fn check_compiled_sources() -> Result<V, Box<dyn Error>> {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .ok_or("source root")?;
    let rows = replay_source::snapshot(root).map_err(|e| format!("source projection: {e}"))?;
    if rows.len() != COMPILED_RUST_SOURCES.len()
        || rows
            .iter()
            .zip(COMPILED_RUST_SOURCES)
            .any(|(row, (path, len, hash))| {
                row.path != *path || row.bytes != *len || row.sha256 != *hash
            })
    {
        return Err("compiled Rust source changed".into());
    }
    Ok(V::Array(
        rows.into_iter()
            .map(|row| {
                V::Object(
                    [
                        ("path".into(), string(&row.path)),
                        ("bytes".into(), V::U64(row.bytes)),
                        ("sha256".into(), string(&row.sha256)),
                    ]
                    .into_iter()
                    .collect(),
                )
            })
            .collect(),
    ))
}
#[cfg(test)]
mod replay_tests {
    use super::*;
    #[test]
    fn receiver_convergence_rejects_mismatched_result_and_resource_before_emit() {
        let row = serialize_manifest(&V::Object(
            [
                (
                    "schema".into(),
                    string("golden-board.m2-damage-replay-case/v2"),
                ),
                ("decoder_result".into(), V::Object(Default::default())),
                ("resource_projection".into(), V::Object(Default::default())),
            ]
            .into_iter()
            .collect(),
        ))
        .unwrap();
        assert!(checked_receiver_row(&row, "OBS_UNITS", &[], b"{}\n", b"{}\n").is_err());
    }
}

struct ReplayOutput {
    path: std::path::PathBuf,
    destination: std::path::PathBuf,
    published: bool,
}
impl ReplayOutput {
    fn new(destination: &Path) -> Result<Self, Box<dyn Error>> {
        use std::sync::atomic::{AtomicU64, Ordering};
        static NEXT: AtomicU64 = AtomicU64::new(0);
        if destination.try_exists()? {
            return Err("replay destination already exists".into());
        }
        let parent = destination.parent().ok_or("output parent")?;
        let name = destination
            .file_name()
            .ok_or("output name")?
            .to_str()
            .ok_or("output name UTF8")?;
        let path = parent.join(format!(
            ".{name}.pending-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        let mut builder = fs::DirBuilder::new();
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            builder.mode(0o700);
        }
        builder.create(&path)?;
        Ok(Self {
            path,
            destination: destination.to_path_buf(),
            published: false,
        })
    }
    fn publish(mut self) -> Result<(), Box<dyn Error>> {
        if self.destination.try_exists()? {
            return Err("replay destination appeared".into());
        }
        fs::rename(&self.path, &self.destination)?;
        self.published = true;
        Ok(())
    }
}
impl Drop for ReplayOutput {
    fn drop(&mut self) {
        if !self.published {
            let _ = fs::remove_dir_all(&self.path);
        }
    }
}
fn check_private_executable(path: &Path) -> Result<(), Box<dyn Error>> {
    let meta = fs::symlink_metadata(path)?;
    if !meta.is_file() || meta.file_type().is_symlink() {
        return Err("regular executable required".into());
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::{MetadataExt, PermissionsExt};
        if meta.nlink() != 1
            || meta.permissions().mode() & 0o222 != 0
            || fs::metadata(path.parent().ok_or("executable parent")?)?
                .permissions()
                .mode()
                & 0o077
                != 0
        {
            return Err(
                "receiver replay requires read-only executable in private directory".into(),
            );
        }
    }
    Ok(())
}
fn aggregate_streamed_resources(
    path: &Path,
    selected: &[(&str, u64)],
    corpus: &str,
) -> Result<Vec<u8>, Box<dyn Error>> {
    use std::io::{BufRead, BufReader};
    let mut input = BufReader::new(fs::File::open(path)?);
    let ids = selected
        .iter()
        .map(|(family, id)| format!("{family}-{id:06}"))
        .collect::<Vec<_>>();
    let borrowed = ids.iter().map(String::as_str).collect::<Vec<_>>();
    let mut failure = None;
    let rows = std::iter::from_fn(|| {
        let read = (|| -> Result<Option<(String, Vec<u8>)>, Box<dyn Error>> {
            let mut line = vec![];
            input
                .by_ref()
                .take(1_048_577)
                .read_until(b'\n', &mut line)?;
            if line.is_empty() {
                return Ok(None);
            }
            if line.len() > 1_048_576 || !line.ends_with(b"\n") {
                return Err("replay row bound".into());
            }
            let V::Object(row) = gb_foundation::validate_canonical_manifest(&line)? else {
                return Err("row object".into());
            };
            let Some(V::Object(identity)) = row.get("observation") else {
                return Err("identity object".into());
            };
            let Some(V::String(id)) = identity.get("case_id") else {
                return Err("case identity".into());
            };
            let sidecar = serialize_manifest(
                row.get("resource_projection")
                    .ok_or("resource projection")?,
            )?;
            Ok(Some((id.clone(), sidecar)))
        })();
        match read {
            Ok(value) => value,
            Err(error) => {
                failure = Some(error.to_string());
                None
            }
        }
    });
    let result =
        gb_bootstrap::resources_v2::build_resource_limits_v2_owned(corpus, &borrowed, rows);
    if let Some(error) = failure {
        return Err(error.into());
    }
    result.map_err(|e| format!("resource aggregation: {e:?}").into())
}

#[cfg(test)]
mod publication_tests {
    use super::*;
    #[cfg(unix)]
    #[test]
    fn receiver_producer_requires_a_private_read_only_unlinked_executable() {
        use std::os::unix::fs::PermissionsExt;
        let parent = std::env::temp_dir().join(format!("gb-replay-binary-{}", std::process::id()));
        fs::create_dir(&parent).unwrap();
        fs::set_permissions(&parent, fs::Permissions::from_mode(0o700)).unwrap();
        let path = parent.join("producer");
        fs::write(&path, b"bounded executable identity").unwrap();
        assert!(check_private_executable(&path).is_err());
        fs::set_permissions(&path, fs::Permissions::from_mode(0o500)).unwrap();
        assert!(check_private_executable(&path).is_ok());
        fs::hard_link(&path, parent.join("alias")).unwrap();
        assert!(check_private_executable(&path).is_err());
        fs::remove_file(parent.join("alias")).unwrap();
        fs::set_permissions(&parent, fs::Permissions::from_mode(0o755)).unwrap();
        assert!(check_private_executable(&path).is_err());
        fs::remove_dir_all(parent).unwrap();
    }
    #[test]
    fn failed_work_never_publishes_and_success_is_one_final_directory() {
        let parent =
            std::env::temp_dir().join(format!("gb-replay-publication-{}", std::process::id()));
        fs::create_dir(&parent).unwrap();
        let destination = parent.join("result");
        let stage = ReplayOutput::new(&destination).unwrap();
        let temporary = stage.path.clone();
        assert!(!destination.exists());
        fs::write(stage.path.join("cases.jsonl"), b"work").unwrap();
        drop(stage);
        assert!(!destination.exists());
        assert!(!temporary.exists());
        let stage = ReplayOutput::new(&destination).unwrap();
        fs::write(stage.path.join("cases.jsonl"), b"finished").unwrap();
        stage.publish().unwrap();
        assert_eq!(
            fs::read(destination.join("cases.jsonl")).unwrap(),
            b"finished"
        );
        assert!(ReplayOutput::new(&destination).is_err());
        assert_eq!(
            fs::read(destination.join("cases.jsonl")).unwrap(),
            b"finished"
        );
        fs::remove_dir_all(parent).unwrap();
    }
}

#[cfg(test)]
mod actual_replay_tests {
    use super::*;
    use std::sync::OnceLock;
    fn corpus() -> &'static gb_bootstrap::damage_corpus_v2::DamageCorpusV2 {
        static CORPUS: OnceLock<gb_bootstrap::damage_corpus_v2::DamageCorpusV2> = OnceLock::new();
        CORPUS.get_or_init(|| source_corpus().unwrap())
    }
    #[test]
    fn exact_owned_selections_have_no_missing_duplicate_or_extra_cases() {
        let corpus = corpus();
        let small = ordered_cases(corpus, false).unwrap();
        assert_eq!(small.len(), 38);
        assert_eq!(small.first(), Some(&("D0", 0)));
        assert_eq!(small.last(), Some(&("B0", 20)));
        let all = ordered_cases(corpus, true).unwrap();
        assert_eq!(
            all.len() as u64,
            corpus.accidental_case_count() + corpus.case_count("B0").unwrap()
        );
        let unique = all
            .iter()
            .copied()
            .collect::<std::collections::BTreeSet<_>>();
        assert_eq!(unique.len(), all.len());
        assert!(small.iter().all(|case| unique.contains(case)));
    }
    #[test]
    fn source_oracle_and_receiver_match_warm_and_worker_order_with_bounded_streaming_limits() {
        let corpus = corpus();
        let selected = [("D7", 401), ("B0", 20)];
        let mut outputs = vec![];
        for workers in [1, 2] {
            let mut rows = vec![];
            replay_workers(corpus, &selected, workers, true, |index, identity, row| {
                assert_eq!(index, rows.len());
                rows.push((identity, row));
                Ok(())
            })
            .unwrap();
            outputs.push(rows);
        }
        assert_eq!(outputs[0], outputs[1]);
        let (identity, row) = &outputs[0][0];
        let V::Object(value) = gb_foundation::validate_canonical_manifest(row).unwrap() else {
            panic!()
        };
        let case = corpus.case(selected[0].0, selected[0].1).unwrap();
        assert_eq!(case.identity_bytes(), identity);
        let result = serialize_manifest(&value["decoder_result"]).unwrap();
        let side = serialize_manifest(&value["resource_projection"]).unwrap();
        assert_eq!(
            checked_receiver_row(row, case.channel(), case.bytes(), &result, &side).unwrap(),
            *row
        );
        assert!(checked_receiver_row(row, case.channel(), case.bytes(), b"{}\n", &side).is_err());
        assert!(checked_receiver_row(row, case.channel(), case.bytes(), &result, b"{}\n").is_err());
        assert!(checked_receiver_row(row, case.channel(), b"changed", &result, &side).is_err());
        let parent = std::env::temp_dir().join(format!("gb-replay-stream-{}", std::process::id()));
        fs::create_dir(&parent).unwrap();
        let path = parent.join("cases.jsonl");
        let mut bytes = vec![];
        let mut hash = Sha256::new();
        let mut sidecars = vec![];
        for (identity, row) in &outputs[0] {
            bytes.extend(row);
            hash.update(identity);
            let V::Object(value) = gb_foundation::validate_canonical_manifest(row).unwrap() else {
                panic!()
            };
            sidecars.push(serialize_manifest(&value["resource_projection"]).unwrap());
        }
        fs::write(&path, &bytes).unwrap();
        let corpus_hash = format!("{:x}", hash.finalize());
        let actual = aggregate_streamed_resources(&path, &selected, &corpus_hash).unwrap();
        let expected = gb_bootstrap::resources_v2::build_resource_limits_v2(
            &corpus_hash,
            &["D7-000401", "B0-000020"],
            [
                ("D7-000401", sidecars[0].as_slice()),
                ("B0-000020", sidecars[1].as_slice()),
            ],
        )
        .unwrap();
        assert_eq!(actual, expected);
        assert!(aggregate_streamed_resources(&path, &selected[..1], &corpus_hash).is_err());
        bytes.pop();
        fs::write(&path, &bytes).unwrap();
        assert!(aggregate_streamed_resources(&path, &selected, &corpus_hash).is_err());
        fs::write(&path, vec![b'x'; 1_048_577]).unwrap();
        assert!(aggregate_streamed_resources(&path, &selected, &corpus_hash).is_err());
        for workers in [0, 9] {
            assert!(replay_workers(corpus, &selected, workers, true, |_, _, _| Ok(())).is_err());
        }
        fs::remove_dir_all(parent).unwrap();
    }
}
