use gb_bootstrap::source_v2::{
    build_source_projection_v2, read_source_file_v2, validate_source_projection_v2,
};
use std::os::unix::fs::{PermissionsExt, symlink};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
};

static NEXT: AtomicU64 = AtomicU64::new(0);
struct Repo(PathBuf);
impl Repo {
    fn new() -> Self {
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "gb-source-v2-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        assert!(
            Command::new("git")
                .args(["init", "-q"])
                .arg(&root)
                .status()
                .unwrap()
                .success()
        );
        let repo = Self(root);
        repo.put(
            "spec/gate8-policy-v2.toml",
            include_bytes!("../../../spec/gate8-policy-v2.toml"),
        );
        repo.put("docs/roadmap.md",b"# Roadmap\n| Project state | pending |\n| Current milestone | M2 |\nfixed\n## 13. Project status\nmutable\n## 14. Adversarial stress matrix\nend\n");
        repo
    }
    fn put(&self, path: &str, raw: &[u8]) {
        let p = self.0.join(path);
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        fs::write(p, raw).unwrap();
    }
    fn root(&self) -> &Path {
        &self.0
    }
}
impl Drop for Repo {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn ordinary_repository_uses_complete_visible_files_and_exact_exclusions() {
    let repo = Repo::new();
    repo.put(".gitignore", b"ignored/\n");
    repo.put("tracked", b"old");
    assert!(
        Command::new("git")
            .arg("-C")
            .arg(repo.root())
            .args(["add", "tracked"])
            .status()
            .unwrap()
            .success()
    );
    fs::remove_file(repo.root().join("tracked")).unwrap();
    repo.put("untracked/new", b"new");
    repo.put("ignored/private", b"ignored");
    repo.put("docs/decisions.md", b"excluded");
    repo.put("docs/decisions.md.extra", b"included");
    repo.put("reports/m2-feasibility-v0.json", b"old");
    repo.put("reports/m2-feasibility-v2.json", b"new");
    repo.put("runner", b"run");
    fs::set_permissions(
        repo.root().join("runner"),
        fs::Permissions::from_mode(0o700),
    )
    .unwrap();
    let projection = build_source_projection_v2(repo.root()).unwrap();
    let paths = projection
        .entries()
        .iter()
        .map(|v| v.path())
        .collect::<Vec<_>>();
    assert_eq!(
        paths,
        [
            ".gitignore",
            "docs/decisions.md.extra",
            "runner",
            "spec/gate8-policy-v2.toml",
            "untracked/new"
        ]
    );
    assert_eq!(projection.entries()[2].mode(), "100755");
    assert_eq!(projection.entries()[4].byte_length(), 3);
    validate_source_projection_v2(projection.canonical_bytes(), repo.root()).unwrap();
    repo.put("untracked/new", b"newer");
    assert!(validate_source_projection_v2(projection.canonical_bytes(), repo.root()).is_err());
}

#[test]
fn linked_roots_gitfiles_and_linked_source_files_reject() {
    let repo = Repo::new();
    let alias = repo.root().with_extension("alias");
    symlink(repo.root(), &alias).unwrap();
    assert!(build_source_projection_v2(&alias).is_err());
    assert!(read_source_file_v2(&alias.join("spec"), "gate8-policy-v2.toml").is_err());
    fs::remove_file(&alias).unwrap();
    fs::rename(repo.root().join(".git"), repo.root().join("git-original")).unwrap();
    repo.put(".git", b"gitdir: git-original\n");
    assert!(build_source_projection_v2(repo.root()).is_err());
    fs::remove_file(repo.root().join(".git")).unwrap();
    fs::rename(repo.root().join("git-original"), repo.root().join(".git")).unwrap();
    repo.put("target", b"data");
    symlink("target", repo.root().join("link")).unwrap();
    assert!(build_source_projection_v2(repo.root()).is_err());
    fs::remove_file(repo.root().join("link")).unwrap();
    fs::hard_link(repo.root().join("target"), repo.root().join("second")).unwrap();
    assert!(build_source_projection_v2(repo.root()).is_err());
}

#[test]
fn missing_roadmap_and_oversized_visible_source_reject() {
    let repo = Repo::new();
    fs::remove_file(repo.root().join("docs/roadmap.md")).unwrap();
    assert!(build_source_projection_v2(repo.root()).is_err());
    repo.put("docs/roadmap.md", b"malformed\n");
    assert!(build_source_projection_v2(repo.root()).is_err());
    let repo = Repo::new();
    let file = fs::File::create(repo.root().join("oversized")).unwrap();
    file.set_len(8_388_609).unwrap();
    assert!(build_source_projection_v2(repo.root()).is_err());
    let repo = Repo::new();
    repo.put(".gitignore", b"docs/roadmap.md\n");
    assert!(build_source_projection_v2(repo.root()).is_err());
}

#[test]
fn external_git_environment_cannot_select_another_repository() {
    if let Some(root) = std::env::var_os("GB_SOURCE_TEST_REPOSITORY") {
        assert!(build_source_projection_v2(Path::new(&root)).is_ok());
        return;
    }
    let repo = Repo::new();
    let output = Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            "external_git_environment_cannot_select_another_repository",
        ])
        .env("GB_SOURCE_TEST_REPOSITORY", repo.root())
        .env("GIT_DIR", repo.root().join("absent-git"))
        .env("GIT_INDEX_FILE", repo.root().join("absent-index"))
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
}

#[test]
fn repository_fsmonitor_command_is_never_executed() {
    let repo = Repo::new();
    repo.put(".gitignore", b"private/\n");
    repo.put(
        "private/monitor",
        b"#!/bin/sh\nprintf unsafe > private/invoked\n",
    );
    fs::set_permissions(
        repo.root().join("private/monitor"),
        fs::Permissions::from_mode(0o700),
    )
    .unwrap();
    assert!(
        Command::new("git")
            .arg("-C")
            .arg(repo.root())
            .args(["config", "core.fsmonitor", "private/monitor"])
            .status()
            .unwrap()
            .success()
    );
    build_source_projection_v2(repo.root()).unwrap();
    assert!(!repo.root().join("private/invoked").exists());
}

#[test]
fn source_reads_reject_special_files_and_directory_aliases() {
    let repo = Repo::new();
    assert!(
        Command::new("mkfifo")
            .arg(repo.root().join("fifo"))
            .status()
            .unwrap()
            .success()
    );
    assert!(read_source_file_v2(repo.root(), "fifo").is_err());
    symlink("spec", repo.root().join("alias")).unwrap();
    assert!(read_source_file_v2(repo.root(), "alias/gate8-policy-v2.toml").is_err());
    assert!(read_source_file_v2(repo.root(), "spec").is_err());
    assert!(read_source_file_v2(repo.root(), "../escape").is_err());
}
