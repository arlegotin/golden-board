//! Enumerate manifest-only physical evidence. No carrier or proof is read.
fn main() {
    let args = std::env::args_os().skip(1).collect::<Vec<_>>();
    if args.len() != 2 {
        eprintln!("usage: physical_v2 INPUT_MANIFEST_DIRECTORY NEW_OUTPUT_FILE");
        std::process::exit(2);
    }
    let root = std::path::Path::new(&args[0]);
    let names = [
        "candidate-manifest.json",
        "capacity-ledger.json",
        "ownership-ledger.json",
        "semantic-envelope.json",
    ];
    let raw = names.map(|name| {
        let p = root.join(name);
        let metadata = std::fs::metadata(&p).expect("input metadata");
        assert!(metadata.len() <= 1048576);
        std::fs::read(p).expect("input manifest")
    });
    let evidence =
        gb_bootstrap::physical_v2::build_physical_evidence_v2(&raw[0], &raw[1], &raw[2], &raw[3])
            .expect("physical input");
    use std::io::Write;
    let mut f = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&args[1])
        .expect("new output");
    f.write_all(evidence.canonical_bytes())
        .expect("write output");
    for r in evidence.rows() {
        println!(
            "{} witnesses={} violations={}",
            r.predicate_id(),
            r.witness_count(),
            r.violation_count()
        );
    }
}
