//! Private revised producer. The coordinator, never this executable, compares
//! independent preflight cores and releases entry to complete damage replay.
use gb_bootstrap::preflight_v2::{CORE_PATHS, PreflightInputsV2, SOURCE_PATHS};
use gb_bootstrap::source_v2::{
    SourceProjectionV2, build_source_projection_v2, open_real_directory_v2, read_source_file_v2,
};
use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::{OsStr, OsString};
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};
use std::time::{Duration, Instant};
#[path = "../../producer_source.rs"]
mod producer_source;
include!(concat!(env!("OUT_DIR"), "/replay-source-preimages.rs"));
include!(concat!(env!("OUT_DIR"), "/producer-source-preimages.rs"));
const EXECUTION_OWNER: &[u8] = include_bytes!("../../../../spec/gate8-execution-v2.md");
#[path = "../../replay_source.rs"]
mod replay_source;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Failure {
    Arguments,
    Filesystem,
    Bounds,
    Source,
    Executable,
    Environment,
    Preflight,
    Release,
    Eof,
    Timeout,
    Generation,
    Receipt,
    Io,
}
type Result<T> = std::result::Result<T, Failure>;
#[derive(Debug, Eq, PartialEq)]
struct Arguments {
    producer_id: String,
    workers: usize,
    work_root: PathBuf,
}
fn parse_arguments(args: &[OsString]) -> Result<Arguments> {
    if args.len() != 7
        || args[0] != OsStr::new("producer")
        || args[1] != OsStr::new("--producer-id")
        || args[3] != OsStr::new("--workers")
        || args[5] != OsStr::new("--work-root")
    {
        return Err(Failure::Arguments);
    }
    let producer = args[2].to_str().ok_or(Failure::Arguments)?;
    let workers = args[4].to_str().ok_or(Failure::Arguments)?;
    let work_root = PathBuf::from(&args[6]);
    if !matches!(producer, "native-rust" | "linux-rust")
        || workers.len() != 1
        || !matches!(workers.as_bytes()[0], b'1'..=b'8')
        || !absolute_normal(&work_root)
    {
        return Err(Failure::Arguments);
    }
    Ok(Arguments {
        producer_id: producer.into(),
        workers: (workers.as_bytes()[0] - b'0') as usize,
        work_root,
    })
}
fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn obj(pairs: impl IntoIterator<Item = (&'static str, V)>) -> V {
    V::Object(pairs.into_iter().map(|(k, v)| (k.into(), v)).collect())
}
fn s(v: &str) -> V {
    V::String(v.into())
}
fn encode(v: &V) -> Result<Vec<u8>> {
    serialize_manifest(v).map_err(|_| Failure::Source)
}
#[derive(Clone, Debug, Eq, PartialEq)]
struct Row {
    path: String,
    bytes: u64,
    sha256: String,
}
impl Row {
    fn value(&self) -> V {
        obj([
            ("path", s(&self.path)),
            ("mode", s("100644")),
            ("bytes", V::U64(self.bytes)),
            ("sha256", s(&self.sha256)),
        ])
    }
}
struct Ready {
    raw: Vec<u8>,
    source_sha256: String,
    core_rows_sha256: String,
    rows: Vec<Row>,
}
fn readiness(producer: &str, source: &[u8], core: &BTreeMap<String, Vec<u8>>) -> Result<Ready> {
    if !matches!(producer, "native-rust" | "linux-rust")
        || core.len() != CORE_PATHS.len()
        || core.keys().map(String::as_str).ne(CORE_PATHS)
    {
        return Err(Failure::Preflight);
    }
    let rows = core
        .iter()
        .map(|(path, raw)| Row {
            path: path.clone(),
            bytes: raw.len() as u64,
            sha256: hash(raw),
        })
        .collect::<Vec<_>>();
    if rows.iter().any(|r| r.bytes == 0 || r.bytes > 1_048_576) {
        return Err(Failure::Bounds);
    }
    let row_value = V::Array(rows.iter().map(Row::value).collect());
    let core_rows_sha256 = hash(&encode(&obj([
        ("schema", s("golden-board.m2-preflight-files/v2")),
        ("rows", row_value.clone()),
    ]))?);
    let source_sha256 = hash(source);
    let raw = encode(&obj([
        ("schema", s("golden-board.m2-preflight-ready/v2")),
        ("producer_id", s(producer)),
        ("source_projection_sha256", s(&source_sha256)),
        ("core_rows", row_value),
    ]))?;
    if raw.len() > 16_384 {
        return Err(Failure::Bounds);
    }
    Ok(Ready {
        raw,
        source_sha256,
        core_rows_sha256,
        rows,
    })
}
fn admit_release(raw: &[u8], ready: &Ready) -> Result<()> {
    if raw.is_empty() || raw.len() > 4096 {
        return Err(Failure::Release);
    }
    let actual = validate_canonical_manifest(raw).map_err(|_| Failure::Release)?;
    if actual
        != obj([
            ("schema", s("golden-board.m2-preflight-release/v2")),
            ("source_projection_sha256", s(&ready.source_sha256)),
            ("core_rows_sha256", s(&ready.core_rows_sha256)),
        ])
    {
        return Err(Failure::Release);
    }
    Ok(())
}
#[repr(C)]
struct PollFd {
    fd: i32,
    events: i16,
    revents: i16,
}
#[cfg(target_os = "macos")]
type PollCount = u32;
#[cfg(target_os = "linux")]
type PollCount = usize;
#[cfg(target_os = "macos")]
type FileMode = u16;
#[cfg(target_os = "linux")]
type FileMode = u32;
unsafe extern "C" {
    fn poll(fds: *mut PollFd, count: PollCount, timeout: i32) -> i32;
    fn openat(fd: i32, name: *const std::ffi::c_char, flags: i32, ...) -> i32;
    fn mkdirat(fd: i32, name: *const std::ffi::c_char, mode: FileMode) -> i32;
    fn linkat(
        oldfd: i32,
        old: *const std::ffi::c_char,
        newfd: i32,
        new: *const std::ffi::c_char,
        flags: i32,
    ) -> i32;
    fn unlinkat(fd: i32, name: *const std::ffi::c_char, flags: i32) -> i32;
}
fn read_release(input: &mut (impl Read + AsRawFd), timeout: Duration) -> Result<Vec<u8>> {
    let deadline = Instant::now().checked_add(timeout).ok_or(Failure::Bounds)?;
    let mut raw = Vec::new();
    loop {
        let remaining = deadline
            .checked_duration_since(Instant::now())
            .ok_or(Failure::Timeout)?;
        let millis = remaining
            .as_millis()
            .saturating_add(1)
            .min(i32::MAX as u128) as i32;
        let mut descriptor = PollFd {
            fd: input.as_raw_fd(),
            events: 1,
            revents: 0,
        };
        // The live descriptor and one writable pollfd remain valid for the call.
        let ready = unsafe { poll(&mut descriptor, 1, millis) };
        if ready < 0 {
            if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(Failure::Io);
        }
        if ready == 0 {
            return Err(Failure::Timeout);
        }
        let mut buffer = [0u8; 4097];
        let amount = input
            .read(&mut buffer[..4097 - raw.len()])
            .map_err(|_| Failure::Io)?;
        if amount == 0 {
            return if raw.is_empty() {
                Err(Failure::Eof)
            } else {
                Ok(raw)
            };
        }
        raw.extend_from_slice(&buffer[..amount]);
        if raw.len() > 4096 {
            return Err(Failure::Bounds);
        }
    }
}
fn absolute_normal(path: &Path) -> bool {
    path.is_absolute()
        && !path
            .components()
            .any(|c| matches!(c, Component::CurDir | Component::ParentDir))
}
fn safe_path(path: &str) -> bool {
    !path.is_empty()
        && path.len() <= 255
        && path.bytes().all(|b| (0x20..=0x7e).contains(&b))
        && !path.contains('\\')
        && path.split('/').all(|v| !matches!(v, "" | "." | ".."))
}
fn private_dir(path: &Path) -> Result<File> {
    if !absolute_normal(path) {
        return Err(Failure::Filesystem);
    }
    let file = open_real_directory_v2(path).map_err(|_| Failure::Filesystem)?;
    if file.metadata().map_err(|_| Failure::Io)?.mode() & 0o7777 != 0o700 {
        return Err(Failure::Filesystem);
    }
    Ok(file)
}
fn check_work_root(root: &Path, source: &Path, executable: &Path) -> Result<()> {
    let work = private_dir(root)?
        .metadata()
        .map_err(|_| Failure::Filesystem)?;
    let source_id = open_real_directory_v2(source)
        .map_err(|_| Failure::Filesystem)?
        .metadata()
        .map_err(|_| Failure::Filesystem)?;
    if root.starts_with(source)
        || source.starts_with(root)
        || executable.starts_with(root)
        || fs::read_dir(root)
            .map_err(|_| Failure::Filesystem)?
            .next()
            .is_some()
    {
        return Err(Failure::Filesystem);
    }
    // Compare directory identities as well as lexical paths, including on
    // case-insensitive hosts where different spellings can name one directory.
    let contains = |child: &Path, target: &fs::Metadata| -> Result<bool> {
        for ancestor in child.ancestors() {
            let meta = open_real_directory_v2(ancestor)
                .map_err(|_| Failure::Filesystem)?
                .metadata()
                .map_err(|_| Failure::Filesystem)?;
            if (meta.dev(), meta.ino()) == (target.dev(), target.ino()) {
                return Ok(true);
            }
        }
        Ok(false)
    };
    if contains(root, &source_id)?
        || contains(source, &work)?
        || contains(executable.parent().ok_or(Failure::Filesystem)?, &work)?
    {
        return Err(Failure::Filesystem);
    }
    Ok(())
}
#[cfg(target_os = "macos")]
const FLAGS: (i32, i32, i32, i32) = (0x100, 0x100000, 0x1000000, 0x4);
#[cfg(all(target_os = "linux", any(target_arch = "aarch64", target_arch = "arm")))]
const FLAGS: (i32, i32, i32, i32) = (0x8000, 0x4000, 0x80000, 0x800);
#[cfg(all(
    target_os = "linux",
    not(any(target_arch = "aarch64", target_arch = "arm"))
))]
const FLAGS: (i32, i32, i32, i32) = (0x20000, 0x10000, 0x80000, 0x800);
#[cfg(target_os = "macos")]
const CREATE_EXCLUSIVE: i32 = 0x200 | 0x800;
#[cfg(target_os = "linux")]
const CREATE_EXCLUSIVE: i32 = 0x40 | 0x80;
fn c_name(name: &str) -> Result<std::ffi::CString> {
    std::ffi::CString::new(name).map_err(|_| Failure::Filesystem)
}
fn open_child(parent: &File, name: &str, directory: bool, create: bool) -> Result<File> {
    let name = c_name(name)?;
    let (nofollow, dir, cloexec, nonblock) = FLAGS;
    let flags = nofollow
        | cloexec
        | nonblock
        | if directory { dir } else { 0 }
        | if create { CREATE_EXCLUSIVE | 1 } else { 0 };
    // All paths are single components, descriptors live, and O_CREAT is paired
    // with O_EXCL and a mode argument. No final or ancestor link is followed.
    let fd = unsafe { openat(parent.as_raw_fd(), name.as_ptr(), flags, 0o644u32) };
    if fd < 0 {
        return Err(Failure::Filesystem);
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn ensure_directory(parent: &File, name: &str) -> Result<File> {
    let cname = c_name(name)?;
    let status = unsafe { mkdirat(parent.as_raw_fd(), cname.as_ptr(), 0o700) };
    if status < 0 && io::Error::last_os_error().kind() != io::ErrorKind::AlreadyExists {
        return Err(Failure::Filesystem);
    }
    let file = open_child(parent, name, true, false)?;
    if status == 0 {
        file.set_permissions(fs::Permissions::from_mode(0o700))
            .map_err(|_| Failure::Io)?;
        parent.sync_all().map_err(|_| Failure::Io)?;
    }
    if !file.metadata().map_err(|_| Failure::Io)?.is_dir()
        || file.metadata().map_err(|_| Failure::Io)?.mode() & 0o7777 != 0o700
    {
        return Err(Failure::Filesystem);
    }
    Ok(file)
}
fn write_new(root: &Path, path: &str, raw: &[u8]) -> Result<()> {
    if !safe_path(path) || raw.len() > 4_194_306 {
        return Err(Failure::Bounds);
    }
    let mut parent = private_dir(root)?;
    let parts = path.split('/').collect::<Vec<_>>();
    for name in &parts[..parts.len() - 1] {
        parent = ensure_directory(&parent, name)?;
    }
    let mut file = open_child(&parent, parts[parts.len() - 1], false, true)?;
    file.set_permissions(fs::Permissions::from_mode(0o644))
        .map_err(|_| Failure::Io)?;
    file.write_all(raw).map_err(|_| Failure::Io)?;
    file.sync_all().map_err(|_| Failure::Io)?;
    let meta = file.metadata().map_err(|_| Failure::Io)?;
    if !meta.is_file()
        || meta.nlink() != 1
        || meta.mode() & 0o7777 != 0o644
        || meta.len() != raw.len() as u64
    {
        return Err(Failure::Filesystem);
    }
    parent.sync_all().map_err(|_| Failure::Io)?;
    if read_source_file_v2(root, path).map_err(|_| Failure::Filesystem)? != raw {
        return Err(Failure::Filesystem);
    }
    let current = fs::symlink_metadata(root.join(path)).map_err(|_| Failure::Filesystem)?;
    if !same_metadata(&meta, &current) {
        return Err(Failure::Filesystem);
    }
    Ok(())
}
fn same_metadata(a: &fs::Metadata, b: &fs::Metadata) -> bool {
    a.dev() == b.dev()
        && a.ino() == b.ino()
        && a.mode() == b.mode()
        && a.nlink() == b.nlink()
        && a.len() == b.len()
        && a.mtime() == b.mtime()
        && a.mtime_nsec() == b.mtime_nsec()
        && a.ctime() == b.ctime()
        && a.ctime_nsec() == b.ctime_nsec()
}
fn verify_tree(root: &Path, expected: &[Row]) -> Result<()> {
    private_dir(root)?;
    // Sum the separate candidate, preflight/source and two bundle ceilings.
    if expected.len() > 4120 + 23 + 2 * (256 + 1) {
        return Err(Failure::Bounds);
    }
    let mut directories = BTreeSet::new();
    let mut rows = BTreeMap::new();
    let mut total = 0u64;
    for row in expected {
        if !safe_path(&row.path) || rows.insert(row.path.clone(), row).is_some() {
            return Err(Failure::Filesystem);
        }
        total = total
            .checked_add(row.bytes)
            .filter(|v| *v <= 570_425_344 + 23 * 1_048_576 + 2 * (67_108_864 + 1_048_576))
            .ok_or(Failure::Bounds)?;
        let mut parent = Path::new(&row.path).parent();
        while let Some(path) = parent {
            if path.as_os_str().is_empty() {
                break;
            }
            directories.insert(path.to_str().ok_or(Failure::Filesystem)?.to_owned());
            parent = path.parent();
        }
    }
    fn visit(
        root: &Path,
        current: &str,
        directories: &BTreeSet<String>,
        rows: &mut BTreeMap<String, &Row>,
    ) -> Result<()> {
        private_dir(&root.join(current))?;
        for entry in fs::read_dir(root.join(current)).map_err(|_| Failure::Filesystem)? {
            let entry = entry.map_err(|_| Failure::Filesystem)?;
            let name = entry
                .file_name()
                .into_string()
                .map_err(|_| Failure::Filesystem)?;
            let path = if current.is_empty() {
                name
            } else {
                format!("{current}/{name}")
            };
            if !safe_path(&path) {
                return Err(Failure::Filesystem);
            }
            let meta = fs::symlink_metadata(entry.path()).map_err(|_| Failure::Filesystem)?;
            if meta.is_dir() {
                if !directories.contains(&path) {
                    return Err(Failure::Filesystem);
                }
                visit(root, &path, directories, rows)?;
            } else {
                let expected = rows.remove(&path).ok_or(Failure::Filesystem)?;
                if !meta.is_file()
                    || meta.nlink() != 1
                    || meta.mode() & 0o7777 != 0o644
                    || meta.len() != expected.bytes
                {
                    return Err(Failure::Filesystem);
                }
                let raw = read_source_file_v2(root, &path).map_err(|_| Failure::Filesystem)?;
                if raw.len() as u64 != expected.bytes || hash(&raw) != expected.sha256 {
                    return Err(Failure::Filesystem);
                }
                if !same_metadata(
                    &meta,
                    &fs::symlink_metadata(entry.path()).map_err(|_| Failure::Filesystem)?,
                ) {
                    return Err(Failure::Filesystem);
                }
            }
        }
        Ok(())
    }
    visit(root, "", &directories, &mut rows)?;
    if !rows.is_empty() {
        return Err(Failure::Filesystem);
    }
    Ok(())
}
struct InstalledReceipt {
    directory: File,
    identity: (u64, u64),
}
fn receipt_last(root: &Path, raw: &[u8]) -> Result<InstalledReceipt> {
    if raw.len() > 1_048_576 {
        return Err(Failure::Bounds);
    }
    let directory = private_dir(root)?;
    let temporary = ".receipt-private";
    write_new(root, temporary, raw)?;
    let file = open_child(&directory, temporary, false, false)?;
    let identity = file.metadata().map_err(|_| Failure::Io)?;
    let old = c_name(temporary)?;
    let new = c_name("receipt.json")?;
    let mut installed = false;
    let result = (|| {
        if unsafe {
            linkat(
                directory.as_raw_fd(),
                old.as_ptr(),
                directory.as_raw_fd(),
                new.as_ptr(),
                0,
            )
        } != 0
        {
            return Err(Failure::Filesystem);
        }
        installed = true;
        if unsafe { unlinkat(directory.as_raw_fd(), old.as_ptr(), 0) } != 0 {
            return Err(Failure::Filesystem);
        }
        directory.sync_all().map_err(|_| Failure::Io)?;
        let meta = open_child(&directory, "receipt.json", false, false)?
            .metadata()
            .map_err(|_| Failure::Io)?;
        if meta.dev() != identity.dev()
            || meta.ino() != identity.ino()
            || meta.nlink() != 1
            || read_source_file_v2(root, "receipt.json").map_err(|_| Failure::Filesystem)? != raw
        {
            return Err(Failure::Filesystem);
        }
        Ok((identity.dev(), identity.ino()))
    })();
    if result.is_err() {
        if installed {
            if let Ok(file) = open_child(&directory, "receipt.json", false, false) {
                if let Ok(meta) = file.metadata() {
                    if meta.dev() == identity.dev() && meta.ino() == identity.ino() {
                        unsafe { unlinkat(directory.as_raw_fd(), new.as_ptr(), 0) };
                    }
                }
            }
        }
        if let Ok(file) = open_child(&directory, temporary, false, false) {
            if let Ok(meta) = file.metadata() {
                if meta.dev() == identity.dev() && meta.ino() == identity.ino() {
                    unsafe { unlinkat(directory.as_raw_fd(), old.as_ptr(), 0) };
                }
            }
        }
        let _ = directory.sync_all();
    }
    result.map(|identity| InstalledReceipt {
        directory,
        identity,
    })
}
#[derive(Clone, Debug, Eq, PartialEq)]
struct Executable {
    bytes: u64,
    sha256: String,
    device: u64,
    inode: u64,
    mode: u32,
    modified: (i64, i64),
    changed: (i64, i64),
}
fn executable_identity(path: &Path) -> Result<Executable> {
    if !absolute_normal(path) {
        return Err(Failure::Executable);
    }
    let directory = private_dir(path.parent().ok_or(Failure::Executable)?)?;
    let directory_identity = directory.metadata().map_err(|_| Failure::Executable)?;
    let name = path
        .file_name()
        .and_then(OsStr::to_str)
        .ok_or(Failure::Executable)?;
    let mut file = open_child(&directory, name, false, false)?;
    let before = file.metadata().map_err(|_| Failure::Executable)?;
    if !before.is_file()
        || before.nlink() != 1
        || before.mode() & 0o7777 != 0o500
        || before.len() == 0
        || before.len() > 536_870_912
    {
        return Err(Failure::Executable);
    }
    let stamp = |m: &fs::Metadata| {
        (
            m.dev(),
            m.ino(),
            m.mode(),
            m.nlink(),
            m.len(),
            m.mtime(),
            m.mtime_nsec(),
            m.ctime(),
            m.ctime_nsec(),
        )
    };
    let mut digest = Sha256::new();
    let mut count = 0u64;
    let mut buffer = [0u8; 65_536];
    loop {
        let n = file.read(&mut buffer).map_err(|_| Failure::Io)?;
        if n == 0 {
            break;
        }
        count = count
            .checked_add(n as u64)
            .filter(|v| *v <= 536_870_912 && *v <= before.len())
            .ok_or(Failure::Bounds)?;
        digest.update(&buffer[..n]);
    }
    let current_directory = private_dir(path.parent().ok_or(Failure::Executable)?)?;
    let current_directory_identity = current_directory
        .metadata()
        .map_err(|_| Failure::Executable)?;
    if (
        directory_identity.dev(),
        directory_identity.ino(),
        directory_identity.mode(),
    ) != (
        current_directory_identity.dev(),
        current_directory_identity.ino(),
        current_directory_identity.mode(),
    ) {
        return Err(Failure::Executable);
    }
    let current = open_child(&current_directory, name, false, false)?
        .metadata()
        .map_err(|_| Failure::Io)?;
    if count != before.len()
        || stamp(&before) != stamp(&file.metadata().map_err(|_| Failure::Io)?)
        || stamp(&before) != stamp(&current)
    {
        return Err(Failure::Executable);
    }
    private_dir(path.parent().ok_or(Failure::Executable)?)?;
    Ok(Executable {
        bytes: count,
        sha256: format!("{:x}", digest.finalize()),
        device: before.dev(),
        inode: before.ino(),
        mode: before.mode(),
        modified: (before.mtime(), before.mtime_nsec()),
        changed: (before.ctime(), before.ctime_nsec()),
    })
}
fn compiled_sources(root: &Path, source: &SourceProjectionV2) -> Result<()> {
    let rust = replay_source::snapshot(root).map_err(|_| Failure::Source)?;
    let factory = producer_source::snapshot(root, &rust).map_err(|_| Failure::Source)?;
    for (rows, compiled) in [
        (&rust, COMPILED_RUST_SOURCES),
        (&factory, COMPILED_FACTORY_INPUTS),
    ] {
        if rows.len() != compiled.len()
            || rows
                .iter()
                .zip(compiled)
                .any(|(r, (p, n, h))| r.path != *p || r.bytes != *n || r.sha256 != *h)
        {
            return Err(Failure::Source);
        }
        for row in rows {
            if !source.entries().iter().any(|r| {
                r.path() == row.path && r.byte_length() == row.bytes && r.sha256() == row.sha256
            }) {
                return Err(Failure::Source);
            }
        }
    }
    Ok(())
}
struct Freeze {
    root: PathBuf,
    source: SourceProjectionV2,
    executable_path: PathBuf,
    executable: Executable,
    work_root: PathBuf,
    work_identity: (u64, u64),
}
impl Freeze {
    fn establish(args: &Arguments) -> Result<Self> {
        let root = std::env::current_dir().map_err(|_| Failure::Source)?;
        let executable_path = std::env::current_exe().map_err(|_| Failure::Executable)?;
        check_work_root(&args.work_root, &root, &executable_path)?;
        let work = private_dir(&args.work_root)?
            .metadata()
            .map_err(|_| Failure::Io)?;
        let executable = executable_identity(&executable_path)?;
        let source = build_source_projection_v2(&root).map_err(|_| Failure::Source)?;
        if read_source_file_v2(&root, "spec/gate8-execution-v2.md").map_err(|_| Failure::Source)?
            != EXECUTION_OWNER
        {
            return Err(Failure::Source);
        }
        compiled_sources(&root, &source)?;
        let freeze = Self {
            root,
            source,
            executable_path,
            executable,
            work_root: args.work_root.clone(),
            work_identity: (work.dev(), work.ino()),
        };
        freeze.check()?;
        Ok(freeze)
    }
    fn check(&self) -> Result<()> {
        let current = build_source_projection_v2(&self.root).map_err(|_| Failure::Source)?;
        if current != self.source {
            return Err(Failure::Source);
        }
        compiled_sources(&self.root, &current)?;
        if executable_identity(&self.executable_path)? != self.executable {
            return Err(Failure::Executable);
        }
        let work = private_dir(&self.work_root)?
            .metadata()
            .map_err(|_| Failure::Filesystem)?;
        if (work.dev(), work.ino()) != self.work_identity {
            return Err(Failure::Filesystem);
        }
        Ok(())
    }
}
fn producer_identity(
    id: &str,
    freeze: &Freeze,
) -> Result<gb_bootstrap::producer_receipt_v2::ProducerIdentityV2> {
    let (platform, image, acquisition) = if id == "linux-rust" {
        if !cfg!(all(target_os = "linux", target_arch = "aarch64")) {
            return Err(Failure::Environment);
        }
        let owner = read_source_file_v2(&freeze.root, "spec/gate8-policy-v0.toml")
            .map_err(|_| Failure::Environment)?;
        let owner: toml::Table = std::str::from_utf8(&owner)
            .map_err(|_| Failure::Environment)?
            .parse()
            .map_err(|_| Failure::Environment)?;
        let t = owner
            .get("linux_acquisition_receipt")
            .and_then(toml::Value::as_table)
            .ok_or(Failure::Environment)?;
        let get = |key| {
            t.get(key)
                .and_then(toml::Value::as_str)
                .ok_or(Failure::Environment)
        };
        let raw =
            read_source_file_v2(&freeze.root, get("path")?).map_err(|_| Failure::Environment)?;
        let expected_hash = get("sha256")?
            .strip_prefix("sha256:")
            .ok_or(Failure::Environment)?;
        if raw.len() as i64
            != t.get("byte_length")
                .and_then(toml::Value::as_integer)
                .ok_or(Failure::Environment)?
            || hash(&raw) != expected_hash
        {
            return Err(Failure::Environment);
        }
        let keys = t
            .get("key_order")
            .and_then(toml::Value::as_array)
            .ok_or(Failure::Environment)?;
        let mut expected = String::new();
        for key in keys {
            let key = key.as_str().ok_or(Failure::Environment)?;
            let value = get(key)?;
            let value = if key == "dockerfile_sha256" {
                value.strip_prefix("sha256:").ok_or(Failure::Environment)?
            } else {
                value
            };
            expected.push_str(&format!("{key}={value}\n"));
        }
        if raw != expected.as_bytes() {
            return Err(Failure::Environment);
        }
        (
            get("platform")?.to_owned(),
            get("image_id")?.to_owned(),
            expected_hash.to_owned(),
        )
    } else {
        let os = if std::env::consts::OS == "macos" {
            "darwin"
        } else {
            std::env::consts::OS
        };
        let arch = if std::env::consts::ARCH == "aarch64" {
            "arm64"
        } else {
            std::env::consts::ARCH
        };
        (format!("{os}/{arch}"), "none".into(), "none".into())
    };
    gb_bootstrap::producer_receipt_v2::ProducerIdentityV2::from_bindings(
        id,
        freeze.executable.bytes,
        &freeze.executable.sha256,
        &platform,
        &image,
        &acquisition,
    )
    .map_err(|_| Failure::Environment)
}
fn generated_bundles(
    core: &gb_bootstrap::preflight_v2::PreflightV2,
    freeze: &Freeze,
) -> Result<gb_bootstrap::participant_bundle_v2::ParticipantBundlesV2> {
    let technical = gb_bootstrap::participant_bundle_v2::technical_literal_sources_v2()
        .into_keys()
        .map(|p| {
            read_source_file_v2(&freeze.root, &p)
                .map(|raw| (p, raw))
                .map_err(|_| Failure::Source)
        })
        .collect::<Result<BTreeMap<_, _>>>()?;
    let learner_paths = [
        "studies/m2/templates/learner/instructions-v1.txt",
        "tools/m2/learner_web/index.html",
        "tools/m2/learner_web/layout.js",
        "tools/m2/learner_web/ui.js",
        "tools/m2/learner_web/viewer.js",
        "tools/m2/learner_runner.py",
        "tools/m2/learner_runner_v1.py",
        "studies/m2/templates/learner/owner-instructions-v2.txt",
    ];
    let literals = learner_paths
        .into_iter()
        .map(|p| read_source_file_v2(&freeze.root, p).map_err(|_| Failure::Source))
        .collect::<Result<Vec<_>>>()?;
    let intent = read_source_file_v2(&freeze.root, "studies/m2/learner-assessment-v2.toml")
        .map_err(|_| Failure::Source)?;
    let chess = read_source_file_v2(&freeze.root, "conformance/chess-v0.json")
        .map_err(|_| Failure::Source)?;
    let game = read_source_file_v2(&freeze.root, "reports/game-set-v0.bin")
        .map_err(|_| Failure::Source)?;
    gb_bootstrap::participant_bundle_v2::build_participant_bundles_v2(
        core,
        &technical,
        gb_bootstrap::learner_bundle_v2::LearnerBundleSourcesV2 {
            intent: &intent,
            chess_fixture: &chess,
            game_set: &game,
            literals: std::array::from_fn(|i| literals[i].as_slice()),
        },
        freeze.source.canonical_bytes(),
    )
    .map_err(|_| Failure::Generation)
}
fn remove_owned_receipt(installed: InstalledReceipt) {
    let InstalledReceipt {
        directory,
        identity,
    } = installed;
    if let Ok(file) = open_child(&directory, "receipt.json", false, false) {
        if let Ok(meta) = file.metadata() {
            if (meta.dev(), meta.ino()) == identity {
                if let Ok(name) = c_name("receipt.json") {
                    unsafe { unlinkat(directory.as_raw_fd(), name.as_ptr(), 0) };
                    let _ = directory.sync_all();
                }
            }
        }
    }
}
fn run() -> Result<()> {
    let args = parse_arguments(&std::env::args_os().skip(1).collect::<Vec<_>>())?;
    let freeze = Freeze::establish(&args)?;
    let identity = producer_identity(&args.producer_id, &freeze)?;
    let inputs = SOURCE_PATHS
        .into_iter()
        .map(|p| {
            read_source_file_v2(&freeze.root, p)
                .map(|raw| (p, raw))
                .map_err(|_| Failure::Source)
        })
        .collect::<Result<BTreeMap<_, _>>>()?;
    let input = PreflightInputsV2::new(inputs.iter().map(|(p, raw)| (*p, raw.as_slice())))
        .map_err(|_| Failure::Source)?;
    let core =
        gb_bootstrap::preflight_v2::build_preflight_v2(input).map_err(|_| Failure::Preflight)?;
    gb_bootstrap::complete_candidate_v2::validate_preflight_entry_v2(&core, args.workers)
        .map_err(|_| Failure::Preflight)?;
    freeze.check()?;
    write_new(
        &args.work_root,
        "source.json",
        freeze.source.canonical_bytes(),
    )?;
    let documents = core
        .documents()
        .map(|(p, raw)| (p.to_owned(), raw.to_vec()))
        .collect::<BTreeMap<_, _>>();
    let ready = readiness(
        &args.producer_id,
        freeze.source.canonical_bytes(),
        &documents,
    )?;
    for (path, raw) in &documents {
        write_new(&args.work_root, &format!("preflight/{path}"), raw)?;
    }
    verify_tree(&args.work_root.join("preflight"), &ready.rows)?;
    freeze.check()?;
    io::stdout()
        .lock()
        .write_all(&ready.raw)
        .map_err(|_| Failure::Io)?;
    io::stdout().flush().map_err(|_| Failure::Io)?;
    let raw = read_release(&mut io::stdin().lock(), Duration::from_secs(3600))?;
    admit_release(&raw, &ready)?;
    freeze.check()?;
    verify_tree(&args.work_root.join("preflight"), &ready.rows)?;
    let candidate_root = args.work_root.join("candidate");
    ensure_directory(&private_dir(&args.work_root)?, "candidate")?;
    let candidate = gb_bootstrap::complete_candidate_v2::build_complete_candidate_v2(
        &core,
        args.workers,
        |p, raw| {
            write_new(&candidate_root, p, raw)
                .map_err(|_| gb_bootstrap::complete_candidate_v2::CompleteCandidateError::Emit)
        },
        |p| {
            read_source_file_v2(&candidate_root, p)
                .map_err(|_| gb_bootstrap::complete_candidate_v2::CompleteCandidateError::Read)
        },
    )
    .map_err(|_| Failure::Generation)?;
    freeze.check()?;
    if !candidate.passed() {
        return Err(Failure::Generation);
    }
    let bundles = generated_bundles(&core, &freeze)?;
    freeze.check()?;
    let mut work_rows = vec![Row {
        path: "source.json".into(),
        bytes: freeze.source.canonical_bytes().len() as u64,
        sha256: hash(freeze.source.canonical_bytes()),
    }];
    work_rows.extend(ready.rows.iter().map(|r| Row {
        path: format!("preflight/{}", r.path),
        bytes: r.bytes,
        sha256: r.sha256.clone(),
    }));
    for (id, files, manifest) in [
        (
            "technical-v2",
            bundles.technical_files(),
            &bundles.preimages().technical_manifest,
        ),
        (
            "learner-v2",
            bundles.learner_files(),
            &bundles.preimages().learner_manifest,
        ),
    ] {
        let mut rows = Vec::new();
        for (p, raw) in files {
            write_new(&args.work_root, &format!("bundles/{id}/{p}"), raw)?;
            rows.push(Row {
                path: p.clone(),
                bytes: raw.len() as u64,
                sha256: hash(raw),
            });
        }
        write_new(
            &args.work_root,
            &format!("bundles/{id}/bundle-manifest.json"),
            manifest,
        )?;
        rows.push(Row {
            path: "bundle-manifest.json".into(),
            bytes: manifest.len() as u64,
            sha256: hash(manifest),
        });
        verify_tree(&args.work_root.join("bundles").join(id), &rows)?;
        work_rows.extend(rows.into_iter().map(|r| Row {
            path: format!("bundles/{id}/{}", r.path),
            bytes: r.bytes,
            sha256: r.sha256,
        }));
    }
    write_new(
        &candidate_root,
        "bundle-preimages.json",
        &bundles.preimages().canonical_bytes,
    )?;
    let table = gb_bootstrap::producer_receipt_v2::build_producer_file_table_v2(
        &candidate,
        &bundles,
        &freeze.source,
    )
    .map_err(|_| Failure::Receipt)?;
    let rows = table
        .rows()
        .iter()
        .map(|r| Row {
            path: r.path().into(),
            bytes: r.byte_length(),
            sha256: r.sha256().into(),
        })
        .collect::<Vec<_>>();
    verify_tree(&candidate_root, &rows)?;
    work_rows.extend(rows.into_iter().map(|r| Row {
        path: format!("candidate/{}", r.path),
        bytes: r.bytes,
        sha256: r.sha256,
    }));
    verify_tree(&args.work_root, &work_rows)?;
    verify_tree(&args.work_root.join("preflight"), &ready.rows)?;
    if read_source_file_v2(&args.work_root, "source.json").map_err(|_| Failure::Source)?
        != freeze.source.canonical_bytes()
    {
        return Err(Failure::Source);
    }
    freeze.check()?;
    let receipt = gb_bootstrap::producer_receipt_v2::build_producer_receipt_v2(&table, &identity)
        .map_err(|_| Failure::Receipt)?;
    gb_bootstrap::producer_receipt_v2::admit_producer_receipt_v2(
        receipt.canonical_bytes(),
        &freeze.source,
        &table,
        &identity,
    )
    .map_err(|_| Failure::Receipt)?;
    if producer_identity(&args.producer_id, &freeze)? != identity {
        return Err(Failure::Environment);
    }
    let installed = receipt_last(&args.work_root, receipt.canonical_bytes())?;
    let final_check = freeze.check().and_then(|()| {
        if producer_identity(&args.producer_id, &freeze)? == identity {
            Ok(())
        } else {
            Err(Failure::Environment)
        }
    });
    if let Err(error) = final_check {
        remove_owned_receipt(installed);
        return Err(error);
    }
    Ok(())
}
fn main() {
    std::panic::set_hook(Box::new(|_| {}));
    if let Err(error) = std::panic::catch_unwind(run).unwrap_or(Err(Failure::Generation)) {
        eprintln!("gb-m2-gate8-v2: {error:?}");
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::DirBuilderExt;
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT: AtomicU64 = AtomicU64::new(0);
    struct Temp(PathBuf);
    impl Temp {
        fn new() -> Self {
            let path = std::env::temp_dir().canonicalize().unwrap().join(format!(
                "gb-gate8-producer-v2-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            fs::DirBuilder::new().mode(0o700).create(&path).unwrap();
            fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
            Self(path)
        }
    }
    impl Drop for Temp {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    fn args(work: &Path) -> Vec<OsString> {
        [
            OsString::from("producer"),
            "--producer-id".into(),
            "native-rust".into(),
            "--workers".into(),
            "2".into(),
            "--work-root".into(),
            work.as_os_str().into(),
        ]
        .into()
    }
    fn ready() -> Ready {
        let core = CORE_PATHS
            .into_iter()
            .map(|p| (p.into(), b"source-built fixture".to_vec()))
            .collect();
        readiness("native-rust", b"source projection", &core).unwrap()
    }
    fn release(ready: &Ready) -> Vec<u8> {
        encode(&obj([
            ("schema", s("golden-board.m2-preflight-release/v2")),
            ("source_projection_sha256", s(&ready.source_sha256)),
            ("core_rows_sha256", s(&ready.core_rows_sha256)),
        ]))
        .unwrap()
    }
    #[test]
    fn arguments_are_exact_ordered_native_or_linux_rust_only() {
        let work = Temp::new();
        assert_eq!(parse_arguments(&args(&work.0)).unwrap().workers, 2);
        for bad in ["0", "01", "+1", "9", " 1"] {
            let mut a = args(&work.0);
            a[4] = bad.into();
            assert!(parse_arguments(&a).is_err());
        }
        let mut a = args(&work.0);
        a[2] = "native-python".into();
        assert!(parse_arguments(&a).is_err());
        let mut a = args(&work.0);
        a.swap(1, 3);
        assert!(parse_arguments(&a).is_err());
        let mut a = args(&work.0);
        a.push("extra".into());
        assert!(parse_arguments(&a).is_err());
    }
    #[test]
    fn readiness_and_release_bind_every_core_row_and_reject_partial_or_noncanonical_input() {
        let ready = ready();
        assert_eq!(ready.rows.len(), 22);
        assert!(ready.raw.len() <= 16384);
        let raw = release(&ready);
        admit_release(&raw, &ready).unwrap();
        assert!(admit_release(&raw[..raw.len() - 1], &ready).is_err());
        let mut v = validate_canonical_manifest(&raw).unwrap();
        let V::Object(ref mut fields) = v else {
            unreachable!()
        };
        fields.insert("core_rows_sha256".into(), s(&"0".repeat(64)));
        assert!(admit_release(&encode(&v).unwrap(), &ready).is_err());
        let mut extra = raw.clone();
        extra.extend_from_slice(b"{}\n");
        assert!(admit_release(&extra, &ready).is_err());
        let mut core = CORE_PATHS
            .into_iter()
            .map(|p| (p.into(), vec![0]))
            .collect::<BTreeMap<_, _>>();
        core.insert(CORE_PATHS[0].into(), vec![]);
        assert!(readiness("native-rust", b"source", &core).is_err());
        core.remove(CORE_PATHS[0]);
        assert!(readiness("native-rust", b"source", &core).is_err());
    }
    #[test]
    fn work_root_and_staged_tree_are_private_exact_and_never_overwrite() {
        let work = Temp::new();
        let source = Temp::new();
        let binary = Temp::new();
        let exe = binary.0.join("producer");
        fs::write(&exe, b"exe").unwrap();
        check_work_root(&work.0, &source.0, &exe).unwrap();
        assert!(check_work_root(&source.0, &source.0, &exe).is_err());
        write_new(&work.0, "candidate/nested/a.json", b"data").unwrap();
        assert!(write_new(&work.0, "candidate/nested/a.json", b"replace").is_err());
        assert!(check_work_root(&work.0, &source.0, &exe).is_err());
        let rows = vec![Row {
            path: "nested/a.json".into(),
            bytes: 4,
            sha256: hash(b"data"),
        }];
        verify_tree(&work.0.join("candidate"), &rows).unwrap();
        fs::write(work.0.join("candidate/extra"), b"extra").unwrap();
        assert!(verify_tree(&work.0.join("candidate"), &rows).is_err());
        assert!(!work.0.join("receipt.json").exists());
    }
    #[test]
    fn final_receipt_is_atomic_no_replace_and_nonhardlinked() {
        let work = Temp::new();
        receipt_last(&work.0, b"first\n").unwrap();
        assert_eq!(fs::read(work.0.join("receipt.json")).unwrap(), b"first\n");
        assert_eq!(
            fs::metadata(work.0.join("receipt.json")).unwrap().nlink(),
            1
        );
        assert!(receipt_last(&work.0, b"second\n").is_err());
        assert_eq!(fs::read(work.0.join("receipt.json")).unwrap(), b"first\n");
    }
    unsafe extern "C" {
        fn pipe(descriptors: *mut i32) -> i32;
    }
    fn stream() -> (File, File) {
        let mut descriptors = [-1; 2];
        assert_eq!(unsafe { pipe(descriptors.as_mut_ptr()) }, 0);
        unsafe {
            (
                File::from_raw_fd(descriptors[0]),
                File::from_raw_fd(descriptors[1]),
            )
        }
    }
    #[test]
    fn release_requires_eof_and_rejects_empty_partial_oversized_and_delayed_extra_data() {
        let ready = ready();
        for input in [vec![], b"{\n".to_vec(), vec![b'x'; 4097]] {
            let (mut reader, mut writer) = stream();
            writer.write_all(&input).unwrap();
            drop(writer);
            assert!(
                read_release(&mut reader, Duration::from_secs(1))
                    .and_then(|raw| admit_release(&raw, &ready))
                    .is_err()
            );
        }
        let (mut reader, mut writer) = stream();
        writer.write_all(&release(&ready)).unwrap();
        drop(writer);
        admit_release(
            &read_release(&mut reader, Duration::from_secs(1)).unwrap(),
            &ready,
        )
        .unwrap();
        let (mut reader, mut writer) = stream();
        writer.write_all(&release(&ready)).unwrap();
        let sender = std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(5));
            writer.write_all(b"{}\n").unwrap();
        });
        let raw = read_release(&mut reader, Duration::from_secs(1)).unwrap();
        sender.join().unwrap();
        assert!(admit_release(&raw, &ready).is_err());
        let (mut reader, writer) = stream();
        assert_eq!(
            read_release(&mut reader, Duration::from_millis(10)),
            Err(Failure::Timeout)
        );
        drop(writer);
    }
    #[test]
    fn rejected_release_leaves_only_private_preflight_and_no_candidate_or_receipt() {
        let work = Temp::new();
        let ready = ready();
        write_new(&work.0, "preflight/core.json", b"private diagnostic").unwrap();
        let (mut reader, writer) = stream();
        drop(writer);
        assert_eq!(
            read_release(&mut reader, Duration::from_secs(1)),
            Err(Failure::Eof)
        );
        assert!(!work.0.join("candidate").exists());
        assert!(!work.0.join("receipt.json").exists());
        assert!(work.0.join("preflight/core.json").is_file());
        let mut changed = release(&ready);
        let index = changed.iter().position(|b| *b == b'0').unwrap_or(40);
        changed[index] = b'!';
        assert!(admit_release(&changed, &ready).is_err());
    }
    #[test]
    fn executable_identity_is_private_exact_mode_unlinked_and_content_bound() {
        let work = Temp::new();
        let path = work.0.join("producer");
        fs::write(&path, b"immutable executable").unwrap();
        assert!(executable_identity(&path).is_err());
        fs::set_permissions(&path, fs::Permissions::from_mode(0o500)).unwrap();
        let before = executable_identity(&path).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
        fs::write(&path, b"changed executable").unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o500)).unwrap();
        assert_ne!(executable_identity(&path).unwrap(), before);
        let alias = work.0.join("alias");
        fs::hard_link(&path, &alias).unwrap();
        assert!(executable_identity(&path).is_err());
        fs::remove_file(alias).unwrap();
        fs::set_permissions(&work.0, fs::Permissions::from_mode(0o755)).unwrap();
        assert!(executable_identity(&path).is_err());
        fs::set_permissions(&work.0, fs::Permissions::from_mode(0o700)).unwrap();
    }
    #[test]
    fn rollback_removes_only_the_owned_receipt_inode() {
        let work = Temp::new();
        let identity = receipt_last(&work.0, b"first\n").unwrap();
        remove_owned_receipt(identity);
        assert!(!work.0.join("receipt.json").exists());
        let identity = receipt_last(&work.0, b"second\n").unwrap();
        fs::write(work.0.join("foreign"), b"foreign").unwrap();
        fs::rename(work.0.join("foreign"), work.0.join("receipt.json")).unwrap();
        remove_owned_receipt(identity);
        assert_eq!(fs::read(work.0.join("receipt.json")).unwrap(), b"foreign");
    }
}
