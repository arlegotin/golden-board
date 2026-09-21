//! Bind compiled workspace Rust sources; generated constants remain in OUT_DIR.
mod producer_source;
mod replay_source;
use std::{env, fs, path::PathBuf};
fn main() {
    let crate_root = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").expect("manifest root"));
    let root = crate_root
        .parent()
        .and_then(std::path::Path::parent)
        .expect("workspace root");
    let rows = replay_source::snapshot(root).expect("bounded Rust source projection");
    let mut output = String::from("const COMPILED_RUST_SOURCES: &[(&str,u64,&str)] = &[\n");
    let embedded = producer_source::snapshot(root, &rows).expect("bounded compiled factory inputs");
    for row in rows {
        println!("cargo:rerun-if-changed={}", root.join(&row.path).display());
        output.push_str(&format!(
            "({:?},{},{:?}),\n",
            row.path, row.bytes, row.sha256
        ));
    }
    for name in [
        "gb-foundation",
        "gb-chess",
        "gb-content",
        "gb-bootstrap",
        "gb-slice",
    ] {
        println!(
            "cargo:rerun-if-changed={}",
            root.join("crates").join(name).display()
        );
    }
    output.push_str("];\n");
    fs::write(
        PathBuf::from(env::var_os("OUT_DIR").expect("build output"))
            .join("replay-source-preimages.rs"),
        output,
    )
    .expect("compiled source projection");
    let mut output = String::from("const COMPILED_FACTORY_INPUTS: &[(&str,u64,&str)] = &[\n");
    for row in embedded {
        println!("cargo:rerun-if-changed={}", root.join(&row.path).display());
        output.push_str(&format!(
            "({:?},{},{:?}),\n",
            row.path, row.bytes, row.sha256
        ));
    }
    output.push_str("];\n");
    fs::write(
        PathBuf::from(env::var_os("OUT_DIR").expect("build output"))
            .join("producer-source-preimages.rs"),
        output,
    )
    .expect("compiled factory input projection");
}
