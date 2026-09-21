//! Additional build-bound literal factory inputs for the revised producer.
//! The runtime still compares the complete ordinary-repository source snapshot.
use crate::replay_source::SourceRow;
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fs;
use std::io::Read;
use std::os::unix::fs::MetadataExt;
use std::path::{Component, Path};
fn trivia(mut source: &str) -> Result<&str, String> {
    loop {
        source = source.trim_start();
        if let Some(rest) = source.strip_prefix("//") {
            source = rest.split_once('\n').map_or("", |v| v.1);
            continue;
        }
        if let Some(rest) = source.strip_prefix("/*") {
            let mut depth = 1usize;
            let bytes = rest.as_bytes();
            let mut cursor = 0usize;
            while depth > 0 && cursor + 1 < bytes.len() {
                if &bytes[cursor..cursor + 2] == b"/*" {
                    depth += 1;
                    cursor += 2;
                } else if &bytes[cursor..cursor + 2] == b"*/" {
                    depth -= 1;
                    cursor += 2;
                } else {
                    cursor += 1;
                }
            }
            if depth != 0 {
                return Err("unterminated factory comment".into());
            }
            source = &rest[cursor..];
            continue;
        }
        return Ok(source);
    }
}
pub fn references(source: &str) -> Result<Vec<String>, String> {
    let mut found = Vec::new();
    for name in ["include_bytes", "include_str"] {
        let mut offset = 0;
        while let Some(relative) = source[offset..].find(name) {
            let start = offset + relative;
            offset = start + name.len();
            if start > 0 && source.as_bytes()[start - 1].is_ascii_alphanumeric() {
                continue;
            }
            let rest = trivia(&source[offset..])?;
            let Some(rest) = rest.strip_prefix('!') else {
                continue;
            };
            let rest = trivia(rest)?
                .strip_prefix('(')
                .ok_or("factory include syntax")?;
            let rest = trivia(rest)?;
            let rest = rest
                .strip_prefix('"')
                .ok_or("factory includes must use literal paths")?;
            let end = rest.find('"').ok_or("unterminated factory include")?;
            let path = &rest[..end];
            if path.is_empty()
                || path.len() > 255
                || !path.bytes().all(|b| (0x20..=0x7e).contains(&b))
                || path.contains('\\')
                || !trivia(&rest[end + 1..])?.starts_with(')')
            {
                return Err("unsupported factory include literal".into());
            }
            found.push((start, path.to_owned()));
        }
    }
    found.sort_by_key(|v| v.0);
    Ok(found.into_iter().map(|v| v.1).collect())
}
fn read(root: &Path, path: &Path) -> Result<Vec<u8>, String> {
    let mut current = root.to_path_buf();
    for component in path.components() {
        if !matches!(component, Component::Normal(_)) {
            return Err("factory source path".into());
        }
        current.push(component.as_os_str());
        let metadata = fs::symlink_metadata(&current).map_err(|e| e.to_string())?;
        if metadata.file_type().is_symlink() {
            return Err("factory source link".into());
        }
    }
    let before = fs::symlink_metadata(&current).map_err(|e| e.to_string())?;
    if !before.is_file() || before.nlink() != 1 || before.len() > 8_388_608 {
        return Err("factory source bound/type".into());
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
    let mut file = fs::File::open(&current).map_err(|e| e.to_string())?;
    let mut raw = Vec::new();
    file.by_ref()
        .take(8_388_609)
        .read_to_end(&mut raw)
        .map_err(|e| e.to_string())?;
    if raw.len() as u64 != before.len()
        || stamp(&before) != stamp(&file.metadata().map_err(|e| e.to_string())?)
        || stamp(&before) != stamp(&fs::symlink_metadata(&current).map_err(|e| e.to_string())?)
    {
        return Err("factory source changed".into());
    }
    Ok(raw)
}
pub fn snapshot(root: &Path, rust: &[SourceRow]) -> Result<Vec<SourceRow>, String> {
    let mut paths = BTreeSet::new();
    for row in rust
        .iter()
        .filter(|r| r.path.contains("/src/") && r.path.ends_with(".rs"))
    {
        let raw = read(root, Path::new(&row.path))?;
        for name in references(std::str::from_utf8(&raw).map_err(|_| "Rust source UTF-8")?)? {
            let mut target = Path::new(&row.path)
                .parent()
                .ok_or("source parent")?
                .to_path_buf();
            for component in Path::new(&name).components() {
                match component {
                    Component::Normal(name) => target.push(name),
                    Component::ParentDir => {
                        if !target.pop() {
                            return Err("factory include escapes repository".into());
                        }
                    }
                    Component::CurDir => {}
                    _ => return Err("factory include must be relative".into()),
                }
            }
            paths.insert(target);
            if paths.len() + rust.len() > 4096 {
                return Err("compiled source file count".into());
            }
        }
    }
    let mut total = rust.iter().try_fold(0u64, |a, r| {
        a.checked_add(r.bytes).ok_or("compiled source sum")
    })?;
    let mut rows = Vec::new();
    for path in paths {
        let raw = read(root, &path)?;
        total = total
            .checked_add(raw.len() as u64)
            .filter(|v| *v <= 134_217_728)
            .ok_or("compiled source aggregate bound")?;
        let path = path.to_str().ok_or("factory path encoding")?.to_owned();
        if path.len() > 255 || !path.bytes().all(|b| (0x20..=0x7e).contains(&b)) {
            return Err("factory path bound".into());
        }
        rows.push(SourceRow {
            path,
            bytes: raw.len() as u64,
            sha256: format!("{:x}", Sha256::digest(&raw)),
        });
    }
    Ok(rows)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn literal_factory_references_include_multiline_and_spaced_macro_invocations() {
        let source = "let a = include_bytes!(\"../../../data.bin\");\nlet b=include_str ! (\n\"../owner.md\"\n);";
        assert_eq!(
            references(source).unwrap(),
            ["../../../data.bin", "../owner.md"]
        );
        assert!(references("include_bytes!(concat!(\"a\",\"b\"))").is_err());
        assert!(references("include_str!(\"a\\\\b\")").is_err());
        assert_eq!(
            references("include_str /* owner */ ! ( /* input */ \"owner.md\" /* end */ )").unwrap(),
            ["owner.md"]
        );
    }
    #[test]
    fn embedded_owner_edits_links_and_out_of_tree_paths_cannot_hide_from_the_snapshot() {
        let root = std::env::temp_dir()
            .canonicalize()
            .unwrap()
            .join(format!("gb-producer-includes-{}", std::process::id()));
        fs::create_dir_all(root.join("crates/fixture/src")).unwrap();
        fs::create_dir(root.join("spec")).unwrap();
        let source = "const OWNER:&str=include_str!(\"../../../spec/owner.md\");";
        fs::write(root.join("crates/fixture/src/lib.rs"), source).unwrap();
        fs::write(root.join("spec/owner.md"), b"first").unwrap();
        let rows = [SourceRow {
            path: "crates/fixture/src/lib.rs".into(),
            bytes: source.len() as u64,
            sha256: String::new(),
        }];
        let first = snapshot(&root, &rows).unwrap();
        assert_eq!(first[0].path, "spec/owner.md");
        fs::write(root.join("spec/owner.md"), b"other").unwrap();
        assert_ne!(snapshot(&root, &rows).unwrap(), first);
        fs::rename(root.join("spec/owner.md"), root.join("spec/real.md")).unwrap();
        std::os::unix::fs::symlink("real.md", root.join("spec/owner.md")).unwrap();
        assert!(snapshot(&root, &rows).is_err());
        fs::remove_file(root.join("spec/owner.md")).unwrap();
        fs::write(
            root.join("crates/fixture/src/lib.rs"),
            "include_str!(\"../../../../escape\")",
        )
        .unwrap();
        assert!(snapshot(&root, &rows).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
