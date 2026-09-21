//! Strict revised source projections. Parsing a projection checks its grammar;
//! only reconstruction against an ordinary repository proves its visible set.
use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::CString;
use std::fs::{File, Metadata};
use std::io::{self, Read};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::MetadataExt;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::time::{Duration, Instant};

pub const EXCLUDED_PATHS: [&str; 4] = [
    "docs/decisions.md",
    "docs/roadmap.md",
    "reports/m2-feasibility-v0.json",
    "reports/m2-feasibility-v2.json",
];
const OWNER: &[u8] = include_bytes!("../../../spec/gate8-policy-v2.toml");
const FILE_MAX: u64 = 8_388_608;
const TOTAL_MAX: u64 = 134_217_728;
const COUNT_MAX: usize = 4096;
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SourceError {
    Manifest,
    Path,
    Bounds,
    Owner,
    Roadmap,
    Repository,
    Git,
    Io,
    Race,
}
impl std::fmt::Display for SourceError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "source-v2: {self:?}")
    }
}
impl std::error::Error for SourceError {}
pub type Result<T> = std::result::Result<T, SourceError>;
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SourceEntryV2 {
    path: String,
    mode: String,
    byte_length: u64,
    sha256: String,
}
impl SourceEntryV2 {
    pub fn path(&self) -> &str {
        &self.path
    }
    pub fn mode(&self) -> &str {
        &self.mode
    }
    pub fn byte_length(&self) -> u64 {
        self.byte_length
    }
    pub fn sha256(&self) -> &str {
        &self.sha256
    }
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SourceProjectionV2 {
    raw: Vec<u8>,
    roadmap: String,
    entries: Vec<SourceEntryV2>,
}
impl SourceProjectionV2 {
    pub fn canonical_bytes(&self) -> &[u8] {
        &self.raw
    }
    pub fn roadmap_normative_sha256(&self) -> &str {
        &self.roadmap
    }
    pub fn entries(&self) -> &[SourceEntryV2] {
        &self.entries
    }
}
fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn object(v: &V) -> Result<&BTreeMap<String, V>> {
    if let V::Object(v) = v {
        Ok(v)
    } else {
        Err(SourceError::Manifest)
    }
}
fn string(v: &V) -> Result<&str> {
    if let V::String(v) = v {
        Ok(v)
    } else {
        Err(SourceError::Manifest)
    }
}
fn number(v: &V) -> Result<u64> {
    if let V::U64(v) = v {
        Ok(*v)
    } else {
        Err(SourceError::Manifest)
    }
}
fn closed<'a>(v: &'a V, keys: &str) -> Result<&'a BTreeMap<String, V>> {
    let v = object(v)?;
    if v.len() != keys.split(',').count() || keys.split(',').any(|k| !v.contains_key(k)) {
        return Err(SourceError::Manifest);
    }
    Ok(v)
}
pub(crate) fn safe_path(path: &str) -> bool {
    !path.is_empty()
        && path.len() <= 255
        && path.bytes().all(|b| (0x20..=0x7e).contains(&b))
        && !path.contains('\\')
        && path.split('/').all(|p| !matches!(p, "" | "." | ".."))
}
fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
/// Preserve the exact inherited roadmap-normative-v0 byte algorithm.
pub fn roadmap_normative_sha256(raw: &[u8]) -> Result<String> {
    if raw.len() as u64 > FILE_MAX || raw.contains(&b'\r') || !raw.ends_with(b"\n") {
        return Err(SourceError::Roadmap);
    }
    let locate = |heading: &[u8]| -> Result<usize> {
        let positions = raw
            .windows(heading.len())
            .enumerate()
            .filter_map(|(i, v)| (v == heading).then_some(i))
            .collect::<Vec<_>>();
        if positions.len() != 1 {
            return Err(SourceError::Roadmap);
        }
        Ok(positions[0])
    };
    let status = locate(b"## 13. Project status")?;
    let stress = locate(b"## 14. Adversarial stress matrix")?;
    if status >= stress {
        return Err(SourceError::Roadmap);
    }
    let lines = raw[..status]
        .split_inclusive(|b| *b == b'\n')
        .collect::<Vec<_>>();
    let mut remove = Vec::new();
    for prefix in [
        b"| Project state | ".as_slice(),
        b"| Current milestone | ".as_slice(),
    ] {
        let matched = lines
            .iter()
            .enumerate()
            .filter(|(_, line)| line.starts_with(prefix))
            .map(|(i, _)| i)
            .collect::<Vec<_>>();
        if matched.len() != 1 {
            return Err(SourceError::Roadmap);
        }
        let index = matched[0];
        let value = &lines[index][prefix.len()..];
        if !value.ends_with(b" |\n") || value[..value.len() - 3].contains(&b'|') {
            return Err(SourceError::Roadmap);
        }
        remove.push(index);
    }
    let length = lines
        .iter()
        .enumerate()
        .filter(|(i, _)| !remove.contains(i))
        .map(|(_, v)| v.len() as u64)
        .sum::<u64>();
    let mut hash = Sha256::new();
    hash.update(b"golden-board:roadmap-normative:v0\0");
    hash.update(length.to_be_bytes());
    for (i, line) in lines.iter().enumerate() {
        if !remove.contains(&i) {
            hash.update(line);
        }
    }
    hash.update(((raw.len() - stress) as u64).to_be_bytes());
    hash.update(&raw[stress..]);
    Ok(format!("{:x}", hash.finalize()))
}
/// Closed grammar, resource bounds and exact compiled Gate8 owner admission.
/// This alone does not establish that a repository's visible set is complete.
pub fn admit_source_projection_v2(raw: &[u8]) -> Result<SourceProjectionV2> {
    if raw.len() > 1_048_576 {
        return Err(SourceError::Bounds);
    }
    let value = validate_canonical_manifest(raw).map_err(|_| SourceError::Manifest)?;
    let root = closed(&value, "schema,roadmap_normative_sha256,entries")?;
    if string(&root["schema"])? != "m2-evidence-source-v2"
        || !digest(string(&root["roadmap_normative_sha256"])?)
    {
        return Err(SourceError::Manifest);
    }
    let V::Array(rows) = &root["entries"] else {
        return Err(SourceError::Manifest);
    };
    if rows.is_empty() || rows.len() > COUNT_MAX {
        return Err(SourceError::Bounds);
    }
    let mut entries = Vec::with_capacity(rows.len());
    let mut previous = "";
    let mut total = 0u64;
    for row in rows {
        let row = closed(row, "path,mode,byte_length,sha256")?;
        let path = string(&row["path"])?;
        let mode = string(&row["mode"])?;
        let byte_length = number(&row["byte_length"])?;
        let sha = string(&row["sha256"])?;
        if !safe_path(path)
            || path <= previous
            || EXCLUDED_PATHS.contains(&path)
            || !matches!(mode, "100644" | "100755")
            || !digest(sha)
        {
            return Err(SourceError::Path);
        }
        total = total.checked_add(byte_length).ok_or(SourceError::Bounds)?;
        if byte_length > FILE_MAX || total > TOTAL_MAX {
            return Err(SourceError::Bounds);
        }
        entries.push(SourceEntryV2 {
            path: path.into(),
            mode: mode.into(),
            byte_length,
            sha256: sha.into(),
        });
        previous = path;
    }
    let owner = entries
        .iter()
        .find(|r| r.path == "spec/gate8-policy-v2.toml")
        .ok_or(SourceError::Owner)?;
    if owner.byte_length != OWNER.len() as u64 || owner.sha256 != hash(OWNER) {
        return Err(SourceError::Owner);
    }
    Ok(SourceProjectionV2 {
        raw: raw.to_vec(),
        roadmap: string(&root["roadmap_normative_sha256"])?.into(),
        entries,
    })
}
// Linux's ARM ABI assigns these two flags differently from x86/generic Linux.
#[cfg(all(target_os = "linux", any(target_arch = "aarch64", target_arch = "arm")))]
const OPEN_FLAGS: (i32, i32, i32, i32) = (0x8000, 0x4000, 0x80000, 0x800);
#[cfg(all(
    target_os = "linux",
    not(any(target_arch = "aarch64", target_arch = "arm"))
))]
const OPEN_FLAGS: (i32, i32, i32, i32) = (0x20000, 0x10000, 0x80000, 0x800);
#[cfg(target_os = "macos")]
const OPEN_FLAGS: (i32, i32, i32, i32) = (0x100, 0x100000, 0x1000000, 0x4);
unsafe extern "C" {
    fn openat(directory: i32, path: *const std::ffi::c_char, flags: i32, ...) -> i32;
}
fn open_child(directory: &File, name: &str, is_directory: bool) -> io::Result<File> {
    let name = CString::new(name).map_err(|_| io::ErrorKind::InvalidInput)?;
    let (nofollow, directory_flag, cloexec, nonblock) = OPEN_FLAGS;
    let flags = nofollow | cloexec | nonblock | if is_directory { directory_flag } else { 0 };
    // The directory descriptor is live; the terminated name remains alive for
    // this call. No creation flags are used, so openat consumes no mode argument.
    let fd = unsafe { openat(directory.as_raw_fd(), name.as_ptr(), flags) };
    if fd < 0 {
        Err(io::Error::last_os_error())
    } else {
        // A successful openat transfers exactly one new owned descriptor.
        Ok(unsafe { File::from_raw_fd(fd) })
    }
}
#[derive(Clone, Debug, Eq, PartialEq)]
struct Stamp {
    device: u64,
    inode: u64,
    mode: u32,
    links: u64,
    length: u64,
    modified: (i64, i64),
    changed: (i64, i64),
}
impl Stamp {
    fn of(m: &Metadata) -> Self {
        Self {
            device: m.dev(),
            inode: m.ino(),
            mode: m.mode(),
            links: m.nlink(),
            length: m.len(),
            modified: (m.mtime(), m.mtime_nsec()),
            changed: (m.ctime(), m.ctime_nsec()),
        }
    }
    fn directory_identity(&self, other: &Self) -> bool {
        self.device == other.device && self.inode == other.inode && self.mode == other.mode
    }
}
struct Directory {
    file: File,
    components: Vec<String>,
    stamps: Vec<Stamp>,
    absolute: PathBuf,
}
fn directory(root: &Path) -> Result<Directory> {
    let absolute = if root.is_absolute() {
        root.to_owned()
    } else {
        std::env::current_dir()
            .map_err(|_| SourceError::Io)?
            .join(root)
    };
    let mut file = File::open("/").map_err(|_| SourceError::Io)?;
    let mut components = Vec::new();
    let mut stamps = Vec::new();
    for c in absolute.components() {
        match c {
            Component::RootDir => {}
            Component::CurDir => {}
            Component::Normal(name) => {
                let name = name.to_str().ok_or(SourceError::Path)?;
                file = open_child(&file, name, true).map_err(|_| SourceError::Repository)?;
                let metadata = file.metadata().map_err(|_| SourceError::Io)?;
                if !metadata.is_dir() {
                    return Err(SourceError::Repository);
                }
                components.push(name.into());
                stamps.push(Stamp::of(&metadata));
            }
            _ => return Err(SourceError::Path),
        }
    }
    let absolute = Path::new("/").join(components.iter().collect::<PathBuf>());
    Ok(Directory {
        file,
        components,
        stamps,
        absolute,
    })
}
impl Directory {
    fn unchanged(&self) -> Result<()> {
        let mut file = File::open("/").map_err(|_| SourceError::Io)?;
        for (name, before) in self.components.iter().zip(&self.stamps) {
            file = open_child(&file, name, true).map_err(|_| SourceError::Race)?;
            if !before
                .directory_identity(&Stamp::of(&file.metadata().map_err(|_| SourceError::Io)?))
            {
                return Err(SourceError::Race);
            }
        }
        Ok(())
    }
}
fn open_relative(root: &Directory, path: &str) -> Result<Option<File>> {
    if !safe_path(path) {
        return Err(SourceError::Path);
    }
    let parts = path.split('/').collect::<Vec<_>>();
    let mut parent = root.file.try_clone().map_err(|_| SourceError::Io)?;
    for (i, name) in parts.iter().enumerate() {
        match open_child(&parent, name, i + 1 < parts.len()) {
            Ok(next) => parent = next,
            Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(None),
            Err(_) => return Err(SourceError::Path),
        }
    }
    let meta = parent.metadata().map_err(|_| SourceError::Io)?;
    if !meta.is_file() || meta.nlink() != 1 {
        return Err(SourceError::Path);
    }
    Ok(Some(parent))
}
fn read_regular(root: &Directory, path: &str) -> Result<Option<(Vec<u8>, Stamp)>> {
    let Some(mut file) = open_relative(root, path)? else {
        return Ok(None);
    };
    let before = Stamp::of(&file.metadata().map_err(|_| SourceError::Io)?);
    if before.length > FILE_MAX {
        return Err(SourceError::Bounds);
    }
    let mut raw = Vec::with_capacity(before.length as usize);
    file.by_ref()
        .take(FILE_MAX + 1)
        .read_to_end(&mut raw)
        .map_err(|_| SourceError::Io)?;
    if raw.len() as u64 > FILE_MAX {
        return Err(SourceError::Bounds);
    }
    let after = Stamp::of(&file.metadata().map_err(|_| SourceError::Io)?);
    if before != after || raw.len() as u64 != before.length {
        return Err(SourceError::Race);
    }
    current_stamp_matches(root, path, &before)?;
    root.unchanged()?;
    Ok(Some((raw, before)))
}
fn current_stamp_matches(root: &Directory, path: &str, before: &Stamp) -> Result<()> {
    let current = open_relative(root, path)?.ok_or(SourceError::Race)?;
    if before != &Stamp::of(&current.metadata().map_err(|_| SourceError::Io)?) {
        return Err(SourceError::Race);
    }
    Ok(())
}
/// Read one bounded regular source through no-follow directory descriptors.
/// This does not by itself establish repository visibility or completeness.
pub fn read_source_file_v2(root: &Path, path: &str) -> Result<Vec<u8>> {
    read_regular(&directory(root)?, path)?
        .map(|v| v.0)
        .ok_or(SourceError::Path)
}
/// Anchor filesystem operations after opening every ancestor without following
/// links. Callers must still check role-specific modes and later path identity.
pub fn open_real_directory_v2(root: &Path) -> Result<File> {
    let directory = directory(root)?;
    directory.unchanged()?;
    Ok(directory.file)
}
fn bounded_read(mut input: impl Read, limit: usize) -> Result<Vec<u8>> {
    let mut raw = Vec::new();
    input
        .by_ref()
        .take(limit as u64 + 1)
        .read_to_end(&mut raw)
        .map_err(|_| SourceError::Git)?;
    if raw.len() > limit {
        Err(SourceError::Bounds)
    } else {
        Ok(raw)
    }
}
fn visible_paths(root: &Path) -> Result<Vec<String>> {
    let mut command = Command::new("git");
    for (name, _) in std::env::vars_os() {
        if name.to_string_lossy().starts_with("GIT_") {
            command.env_remove(name);
        }
    }
    command
        .env("GIT_CONFIG_GLOBAL", "/dev/null")
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .env("GIT_OPTIONAL_LOCKS", "0")
        .args([
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.excludesFile=/dev/null",
            "-C",
        ])
        .arg(root)
        .args([
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = command.spawn().map_err(|_| SourceError::Git)?;
    let stdout = child.stdout.take().ok_or(SourceError::Git)?;
    let stderr = child.stderr.take().ok_or(SourceError::Git)?;
    let (tx, rx) = mpsc::channel();
    let tx2 = tx.clone();
    let a = std::thread::spawn(move || {
        let _ = tx.send((0, bounded_read(stdout, 1_048_576)));
    });
    let b = std::thread::spawn(move || {
        let _ = tx2.send((1, bounded_read(stderr, 65_536)));
    });
    let deadline = Instant::now() + Duration::from_secs(30);
    let mut outputs = [None, None];
    let mut status = None;
    let mut error = None;
    loop {
        while let Ok((index, value)) = rx.try_recv() {
            match value {
                Ok(raw) => outputs[index] = Some(raw),
                Err(e) => error = Some(e),
            }
        }
        if error.is_some() {
            break;
        }
        if status.is_none() {
            match child.try_wait() {
                Ok(v) => status = v,
                Err(_) => {
                    error = Some(SourceError::Git);
                    break;
                }
            }
        }
        if status.is_some() && outputs.iter().all(Option::is_some) {
            break;
        }
        if Instant::now() >= deadline {
            error = Some(SourceError::Git);
            break;
        }
        std::thread::sleep(Duration::from_millis(5));
    }
    if error.is_some() {
        let _ = child.kill();
    }
    let final_status = child.wait().map_err(|_| SourceError::Git);
    let joined = a.join().is_ok() & b.join().is_ok();
    if let Some(e) = error {
        return Err(e);
    }
    if !joined || !final_status?.success() {
        return Err(SourceError::Git);
    }
    let raw = outputs[0].take().ok_or(SourceError::Git)?;
    if !raw.is_empty() && !raw.ends_with(&[0]) {
        return Err(SourceError::Git);
    }
    let mut paths = BTreeSet::new();
    for path in raw.split(|b| *b == 0).filter(|p| !p.is_empty()) {
        let path = std::str::from_utf8(path).map_err(|_| SourceError::Path)?;
        if !safe_path(path) {
            return Err(SourceError::Path);
        }
        if !paths.insert(path.to_owned()) {
            return Err(SourceError::Git);
        }
        if paths.len() > COUNT_MAX {
            return Err(SourceError::Bounds);
        }
    }
    Ok(paths.into_iter().collect())
}
pub fn build_source_projection_v2(root: &Path) -> Result<SourceProjectionV2> {
    let root = directory(root)?;
    let git = open_child(&root.file, ".git", true).map_err(|_| SourceError::Repository)?;
    let git_stamp = Stamp::of(&git.metadata().map_err(|_| SourceError::Io)?);
    let paths = visible_paths(&root.absolute)?;
    if !paths.iter().any(|p| p == "docs/roadmap.md") {
        return Err(SourceError::Roadmap);
    }
    let mut rows = Vec::new();
    let mut stamps = Vec::new();
    let mut missing = Vec::new();
    let mut total = 0u64;
    for path in &paths {
        if EXCLUDED_PATHS.contains(&path.as_str()) {
            continue;
        }
        let Some((raw, stamp)) = read_regular(&root, path)? else {
            missing.push(path);
            continue;
        };
        total = total
            .checked_add(raw.len() as u64)
            .ok_or(SourceError::Bounds)?;
        if total > TOTAL_MAX {
            return Err(SourceError::Bounds);
        }
        rows.push(V::Object(BTreeMap::from([
            ("path".into(), V::String(path.clone())),
            (
                "mode".into(),
                V::String(
                    if stamp.mode & 0o111 == 0 {
                        "100644"
                    } else {
                        "100755"
                    }
                    .into(),
                ),
            ),
            ("byte_length".into(), V::U64(raw.len() as u64)),
            ("sha256".into(), V::String(hash(&raw))),
        ])));
        stamps.push((path.clone(), stamp));
    }
    let (roadmap, stamp) = read_regular(&root, "docs/roadmap.md")?.ok_or(SourceError::Roadmap)?;
    let roadmap = roadmap_normative_sha256(&roadmap)?;
    stamps.push(("docs/roadmap.md".into(), stamp));
    if paths != visible_paths(&root.absolute)? {
        return Err(SourceError::Race);
    }
    for (path, before) in stamps {
        current_stamp_matches(&root, &path, &before)?;
    }
    for path in missing {
        if open_relative(&root, path)?.is_some() {
            return Err(SourceError::Race);
        }
    }
    root.unchanged()?;
    let current_git = open_child(&root.file, ".git", true).map_err(|_| SourceError::Race)?;
    if !git_stamp.directory_identity(&Stamp::of(
        &current_git.metadata().map_err(|_| SourceError::Io)?,
    )) {
        return Err(SourceError::Race);
    }
    let value = V::Object(BTreeMap::from([
        ("schema".into(), V::String("m2-evidence-source-v2".into())),
        ("roadmap_normative_sha256".into(), V::String(roadmap)),
        ("entries".into(), V::Array(rows)),
    ]));
    admit_source_projection_v2(&serialize_manifest(&value).map_err(|_| SourceError::Manifest)?)
}
pub fn validate_source_projection_v2(raw: &[u8], root: &Path) -> Result<SourceProjectionV2> {
    let admitted = admit_source_projection_v2(raw)?;
    if build_source_projection_v2(root)?.canonical_bytes() != raw {
        return Err(SourceError::Race);
    }
    Ok(admitted)
}
#[cfg(test)]
mod tests {
    use super::*;
    const ROADMAP:&[u8]=b"# Roadmap\n| Project state | pending |\n| Current milestone | M2 |\nfixed\n## 13. Project status\nmutable\n## 14. Adversarial stress matrix\nend\n";
    #[test]
    fn roadmap_exact_preimage_preserves_only_the_owned_mutable_regions() {
        let prefix = b"# Roadmap\nfixed\n";
        let suffix = b"## 14. Adversarial stress matrix\nend\n";
        let mut expected = Sha256::new();
        expected.update(b"golden-board:roadmap-normative:v0\0");
        expected.update((prefix.len() as u64).to_be_bytes());
        expected.update(prefix);
        expected.update((suffix.len() as u64).to_be_bytes());
        expected.update(suffix);
        let original = roadmap_normative_sha256(ROADMAP).unwrap();
        assert_eq!(original, format!("{:x}", expected.finalize()));
        let text = String::from_utf8(ROADMAP.to_vec()).unwrap();
        let changed = text
            .replace("pending", "done")
            .replace("| M2 |", "| M3 |")
            .replace("mutable\n", "different status\n");
        assert_eq!(
            roadmap_normative_sha256(changed.as_bytes()).unwrap(),
            original
        );
        assert_ne!(
            roadmap_normative_sha256(text.replace("fixed", "changed").as_bytes()).unwrap(),
            original
        );
        for changed in [
            text.replace("| pending |", "| pending | extra |"),
            text.replace("## 14. Adversarial stress matrix", "missing"),
            text.replace("| Project state | pending |\n", ""),
            text.replace("fixed\n", "fixed\r\n"),
        ] {
            assert!(roadmap_normative_sha256(changed.as_bytes()).is_err());
        }
    }
    fn projection() -> V {
        V::Object(BTreeMap::from([
            ("schema".into(), V::String("m2-evidence-source-v2".into())),
            ("roadmap_normative_sha256".into(), V::String("0".repeat(64))),
            (
                "entries".into(),
                V::Array(vec![V::Object(BTreeMap::from([
                    ("path".into(), V::String("spec/gate8-policy-v2.toml".into())),
                    ("mode".into(), V::String("100644".into())),
                    ("byte_length".into(), V::U64(OWNER.len() as u64)),
                    ("sha256".into(), V::String(hash(OWNER))),
                ]))]),
            ),
        ]))
    }
    #[test]
    fn source_rows_are_closed_exactly_typed_bounded_and_owner_bound() {
        let raw = serialize_manifest(&projection()).unwrap();
        assert!(admit_source_projection_v2(&raw).is_ok());
        for (key, value) in [
            ("byte_length", V::Bool(true)),
            ("byte_length", V::U64(FILE_MAX + 1)),
            ("mode", V::String("120000".into())),
            ("path", V::String("../escape".into())),
            ("sha256", V::String("0".repeat(64))),
        ] {
            let V::Object(mut root) = projection() else {
                unreachable!()
            };
            let V::Array(rows) = root.get_mut("entries").unwrap() else {
                unreachable!()
            };
            let V::Object(row) = &mut rows[0] else {
                unreachable!()
            };
            row.insert(key.into(), value);
            assert!(
                admit_source_projection_v2(&serialize_manifest(&V::Object(root)).unwrap()).is_err()
            );
        }
        assert_eq!(
            admit_source_projection_v2(&vec![b' '; 1_048_577]),
            Err(SourceError::Bounds)
        );
        let V::Object(mut root) = projection() else {
            unreachable!()
        };
        let V::Array(rows) = root.get_mut("entries").unwrap() else {
            unreachable!()
        };
        let owner = rows.pop().unwrap();
        for i in 0..17 {
            rows.push(V::Object(BTreeMap::from([
                ("path".into(), V::String(format!("file-{i:02}"))),
                ("mode".into(), V::String("100644".into())),
                ("byte_length".into(), V::U64(FILE_MAX)),
                ("sha256".into(), V::String("0".repeat(64))),
            ])));
        }
        rows.push(owner);
        assert_eq!(
            admit_source_projection_v2(&serialize_manifest(&V::Object(root)).unwrap()),
            Err(SourceError::Bounds)
        );
    }
    #[test]
    fn retained_file_identity_detects_replacement_and_content_metadata_changes() {
        let path = std::env::temp_dir()
            .canonicalize()
            .unwrap()
            .join(format!("gb-source-v2-stamp-{}", std::process::id()));
        std::fs::create_dir(&path).unwrap();
        std::fs::write(path.join("file"), b"first").unwrap();
        let root = directory(&path).unwrap();
        let (_, stamp) = read_regular(&root, "file").unwrap().unwrap();
        std::fs::write(path.join("replacement"), b"first").unwrap();
        std::fs::rename(path.join("replacement"), path.join("file")).unwrap();
        assert_eq!(
            current_stamp_matches(&root, "file", &stamp),
            Err(SourceError::Race)
        );
        let (_, stamp) = read_regular(&root, "file").unwrap().unwrap();
        std::fs::write(path.join("file"), b"different").unwrap();
        assert_eq!(
            current_stamp_matches(&root, "file", &stamp),
            Err(SourceError::Race)
        );
        std::fs::remove_dir_all(&path).unwrap();
    }
}
