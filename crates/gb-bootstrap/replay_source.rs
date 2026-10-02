//! Bounded compiled-Rust source preimages shared by build and replay only.
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};
use std::{fs, io::Read};
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SourceRow {
    pub path: String,
    pub bytes: u64,
    pub sha256: String,
}
pub fn snapshot(root: &Path) -> Result<Vec<SourceRow>, String> {
    for directory in [root.to_path_buf(), root.join("crates")] {
        let meta = fs::symlink_metadata(directory).map_err(|e| e.to_string())?;
        if !meta.is_dir() || meta.file_type().is_symlink() {
            return Err("real source root required".into());
        }
    }
    fn regular(path: &Path) -> Result<fs::Metadata, String> {
        let meta = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
        if !meta.is_file() || meta.file_type().is_symlink() {
            return Err("regular source required".into());
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt;
            if meta.nlink() != 1 {
                return Err("hardlinked source rejected".into());
            }
        }
        if meta.len() > 8 * 1024 * 1024 {
            return Err("source file bound".into());
        }
        Ok(meta)
    }
    fn walk(path: &Path, files: &mut Vec<PathBuf>, visited: &mut usize) -> Result<(), String> {
        let meta = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
        if !meta.is_dir() || meta.file_type().is_symlink() {
            return Err("real source directory required".into());
        }
        for entry in fs::read_dir(path).map_err(|e| e.to_string())? {
            let entry = entry.map_err(|e| e.to_string())?;
            *visited += 1;
            if *visited > 4096 {
                return Err("source entry bound".into());
            }
            let path = entry.path();
            let name = entry
                .file_name()
                .into_string()
                .map_err(|_| "source path encoding")?;
            if !name.is_ascii() {
                return Err("ASCII source paths required".into());
            }
            if name == "target" {
                continue;
            }
            let meta = fs::symlink_metadata(&path).map_err(|e| e.to_string())?;
            if meta.file_type().is_symlink() {
                return Err("source symlink rejected".into());
            }
            if meta.is_dir() {
                walk(&path, files, visited)?;
            } else if name == "Cargo.toml" || path.extension().is_some_and(|ext| ext == "rs") {
                files.push(path);
            }
        }
        Ok(())
    }
    let mut files = vec![root.join("Cargo.toml"), root.join("Cargo.lock")];
    let mut visited = 2;
    for name in [
        "gb-foundation",
        "gb-chess",
        "gb-content",
        "gb-bootstrap",
        "gb-slice",
    ] {
        let dir = root.join("crates").join(name);
        regular(&dir.join("Cargo.toml"))?;
        walk(&dir, &mut files, &mut visited)?;
    }
    files.sort();
    if files.len() > 4096 {
        return Err("source file count bound".into());
    }
    let mut total = 0u64;
    let mut rows = Vec::with_capacity(files.len());
    for path in files {
        let meta = regular(&path)?;
        total = total
            .checked_add(meta.len())
            .ok_or("source total overflow")?;
        if total > 128 * 1024 * 1024 {
            return Err("source total bound".into());
        }
        let mut file = fs::File::open(&path).map_err(|e| e.to_string())?;
        let mut hash = Sha256::new();
        let mut size = 0u64;
        let mut buffer = [0u8; 65536];
        loop {
            let read = file.read(&mut buffer).map_err(|e| e.to_string())?;
            if read == 0 {
                break;
            }
            size += read as u64;
            if size > meta.len() {
                return Err("source changed during read".into());
            }
            hash.update(&buffer[..read]);
        }
        if size != meta.len() || regular(&path)?.len() != size {
            return Err("source changed during read".into());
        }
        let path = path
            .strip_prefix(root)
            .map_err(|_| "source root")?
            .to_str()
            .ok_or("source ASCII")?
            .to_owned();
        if !path.is_ascii() {
            return Err("ASCII source paths required".into());
        }
        rows.push(SourceRow {
            path,
            bytes: size,
            sha256: format!("{:x}", hash.finalize()),
        });
    }
    Ok(rows)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::sync::atomic::{AtomicU64, Ordering};
    fn root() -> std::path::PathBuf {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let root = std::env::temp_dir().join(format!(
            "gb-rust-preimages-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        fs::write(root.join("Cargo.toml"), b"workspace").unwrap();
        fs::write(root.join("Cargo.lock"), b"locked").unwrap();
        for name in [
            "gb-foundation",
            "gb-chess",
            "gb-content",
            "gb-bootstrap",
            "gb-slice",
        ] {
            let dir = root.join("crates").join(name);
            fs::create_dir_all(dir.join("src")).unwrap();
            fs::write(dir.join("Cargo.toml"), b"manifest").unwrap();
            fs::write(dir.join("src/lib.rs"), b"source").unwrap();
        }
        root
    }
    #[test]
    fn source_binding_is_sorted_complete_and_changes_with_source() {
        let root = root();
        let first = snapshot(&root).unwrap();
        assert_eq!(first.len(), 12);
        assert!(first.windows(2).all(|rows| rows[0].path < rows[1].path));
        fs::write(root.join("crates/gb-bootstrap/src/lib.rs"), b"changed").unwrap();
        assert_ne!(snapshot(&root).unwrap(), first);
        fs::write(root.join("crates/gb-bootstrap/build.rs"), b"build source").unwrap();
        assert_eq!(snapshot(&root).unwrap().len(), 13);
        fs::remove_dir_all(root).unwrap();
    }
    #[cfg(unix)]
    #[test]
    fn links_and_oversized_files_cannot_enter_source_binding() {
        use std::os::unix::fs::symlink;
        let root = root();
        let file = root.join("crates/gb-bootstrap/src/lib.rs");
        let alias = root.join("crates/gb-bootstrap/src/alias.rs");
        symlink(&file, &alias).unwrap();
        assert!(snapshot(&root).is_err());
        fs::remove_file(&alias).unwrap();
        fs::hard_link(&file, &alias).unwrap();
        assert!(snapshot(&root).is_err());
        fs::remove_file(&alias).unwrap();
        fs::OpenOptions::new()
            .write(true)
            .open(&file)
            .unwrap()
            .set_len(8 * 1024 * 1024 + 1)
            .unwrap();
        assert!(snapshot(&root).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
