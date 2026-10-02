//! Stream independent identities or one observation; never decoder results.
use std::error::Error;
use std::fs::{self, OpenOptions};
use std::io::{BufWriter, Write};
use std::path::Path;

fn run() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 1 && args.len() != 4 {
        return Err(
            "usage: damage_corpus_v2 ABSOLUTE_NEW_PRIVATE_OUTPUT [--observation FAMILY ORDINAL]"
                .into(),
        );
    }
    let selection = if args.len() == 4 {
        if args[1] != "--observation" {
            return Err("unknown mode".into());
        }
        let family = args[2].to_str().ok_or("ASCII family required")?;
        if !["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "B0"].contains(&family) {
            return Err("unknown family".into());
        }
        let ordinal = args[3].to_str().ok_or("decimal ordinal required")?;
        if ordinal.is_empty() || ordinal.len() > 6 || !ordinal.bytes().all(|v| v.is_ascii_digit()) {
            return Err("bounded decimal ordinal required".into());
        }
        Some((family, ordinal.parse::<u64>()?))
    } else {
        None
    };
    let path = Path::new(&args[0]);
    if !path.is_absolute() || path.file_name().is_none() {
        return Err("absolute new output path required".into());
    }
    for ancestor in path.parent().ok_or("parent")?.ancestors() {
        let metadata = fs::symlink_metadata(ancestor)?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
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
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut output = BufWriter::new(options.open(path)?);
    if let Some((family, ordinal)) = selection {
        let case = corpus
            .case(family, ordinal)
            .map_err(|e| format!("{family}-{ordinal}: {e:?}"))?;
        output.write_all(case.bytes())?;
        output.flush()?;
        output.get_ref().sync_all()?;
        eprintln!("{}", std::str::from_utf8(case.identity_bytes())?);
        return Ok(());
    }
    let mut count = 0;
    for family in ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "B0"] {
        let length = corpus
            .case_count(family)
            .map_err(|e| format!("count: {e:?}"))?;
        for ordinal in 0..length {
            let case = corpus
                .case(family, ordinal)
                .map_err(|e| format!("{family}-{ordinal}: {e:?}"))?;
            let bytes = case.identity_bytes();
            if bytes.last() != Some(&b'\n') {
                return Err("canonical identity lacks newline".into());
            }
            output.write_all(bytes)?;
            count += 1;
            if ordinal > 0 && ordinal % 1000 == 0 {
                eprintln!("{family}: {ordinal}/{length}");
            }
        }
        eprintln!("{family}: {length} identities");
    }
    output.flush()?;
    output.get_ref().sync_all()?;
    if count != corpus.accidental_case_count() + 21 {
        return Err("incomplete operator inventory".into());
    }
    eprintln!("{count} identities written; no decoder invoked");
    Ok(())
}
fn main() {
    if let Err(error) = run() {
        eprintln!("damage-corpus-v2: {error}");
        std::process::exit(2)
    }
}
