//! Fresh development bundle comparison. The source projection here deliberately
//! covers only the 22 shared bundle source inputs, not a production source freeze.
use gb_bootstrap::learner_bundle_v2::LearnerBundleSourcesV2;
use gb_bootstrap::participant_bundle_v2::{
    build_participant_bundles_v2, render_bundle_manifest_v2, technical_literal_sources_v2,
};
use gb_bootstrap::preflight_v2::{PreflightInputsV2, build_preflight_v2};
use gb_bootstrap::source_v2::{admit_source_projection_v2, roadmap_normative_sha256};
use gb_foundation::{ManifestValue as V, serialize_manifest};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::error::Error;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::Path;

fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn s(value: impl Into<String>) -> V {
    V::String(value.into())
}
fn n(value: usize) -> V {
    V::U64(value as u64)
}
fn object<const N: usize>(rows: [(&str, V); N]) -> V {
    V::Object(rows.into_iter().map(|(k, v)| (k.into(), v)).collect())
}
fn read(path: &Path) -> Result<Vec<u8>, Box<dyn Error>> {
    if !fs::symlink_metadata(path)?.is_file() {
        return Err("source is not a regular file".into());
    }
    let mut raw = Vec::new();
    File::open(path)?.take(8_388_609).read_to_end(&mut raw)?;
    if raw.len() > 8_388_608 {
        return Err("source file too large".into());
    }
    Ok(raw)
}
fn write(out: &Path, name: &str, raw: &[u8]) -> Result<(), Box<dyn Error>> {
    let path = out.join(name);
    fs::create_dir_all(path.parent().ok_or("no parent")?)?;
    let mut options = OpenOptions::new();
    options.create_new(true).write(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o644);
    }
    options.open(path)?.write_all(raw)?;
    Ok(())
}
fn first_difference(path: &str, a: &V, b: &V) -> String {
    match (a, b) {
        (V::Object(a), V::Object(b)) => {
            if a.keys().ne(b.keys()) {
                return format!("{path}: object keys differ");
            }
            for (key, value) in a {
                if value != &b[key] {
                    return first_difference(&format!("{path}.{key}"), value, &b[key]);
                }
            }
        }
        (V::Array(a), V::Array(b)) => {
            if a.len() != b.len() {
                return format!("{path}: length {} vs {}", a.len(), b.len());
            }
            for (index, (a, b)) in a.iter().zip(b).enumerate() {
                if a != b {
                    return first_difference(&format!("{path}[{index}]"), a, b);
                }
            }
        }
        _ => {
            return format!("{path}: {a:?} vs {b:?}")
                .chars()
                .take(320)
                .collect();
        }
    }
    format!("{path}: equal")
}
fn diagnostic_heldouts(
    corpus: &gb_bootstrap::damage_corpus_v2::DamageCorpusV2,
) -> Result<(), Box<dyn Error>> {
    use gb_bootstrap::damage_oracle_v2::FullOracleV2;
    use gb_bootstrap::damage_v2::{
        decode_observation_v2, render_decoder_result_v2, render_resources_v2,
    };
    use gb_foundation::validate_canonical_manifest;
    let oracle = FullOracleV2::new(corpus).map_err(|e| format!("oracle: {e:?}"))?;
    for (family, ordinal) in [("D3", 0), ("D2", 0), ("D4", 0), ("D7", 11)] {
        let case = corpus
            .case(family, ordinal)
            .map_err(|e| format!("case: {e:?}"))?;
        let expected = oracle
            .project(family, ordinal, case.bytes())
            .map_err(|e| format!("oracle: {e:?}"))?;
        let actual = decode_observation_v2(case.channel(), case.bytes());
        let (result, _) = render_decoder_result_v2(case.channel(), &actual)
            .map_err(|e| format!("result: {e:?}"))?;
        let resources = render_resources_v2(case.channel(), case.bytes(), &actual)
            .map_err(|e| format!("resources: {e:?}"))?;
        for (name, expected, actual) in [
            ("result", expected.result_bytes(), result.as_slice()),
            ("resource", expected.resource_bytes(), resources.as_slice()),
        ] {
            if expected != actual {
                let a = validate_canonical_manifest(expected)?;
                let b = validate_canonical_manifest(actual)?;
                return Err(format!(
                    "{family}/{ordinal} {name} source vs receiver: {}",
                    first_difference("$", &a, &b)
                )
                .into());
            }
        }
        println!("{family}/{ordinal}: exact result and resource agreement");
    }
    Ok(())
}
fn run() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 2 {
        return Err(
            "usage: participant_bundle_v2 REPOSITORY_ROOT ABSOLUTE_NEW_PRIVATE_DIRECTORY".into(),
        );
    }
    let root = Path::new(&args[0]);
    let out = Path::new(&args[1]);
    if !out.is_absolute() || out.file_name().is_none() || out.try_exists()? {
        return Err("output must be a new absolute directory".into());
    }
    let policy_raw = read(&root.join("spec/gate8-policy-v2.toml"))?;
    let policy: toml::Table = std::str::from_utf8(&policy_raw)?.parse()?;
    let mut paths = BTreeSet::from([
        "spec/gate8-policy-v2.toml".to_owned(),
        "spec/learner-assessment-v2.md".to_owned(),
        "studies/m2/learner-assessment-v2.toml".to_owned(),
    ]);
    for id in ["technical_bundle", "learner_bundle"] {
        for path in policy[id]["literal_sources"]
            .as_table()
            .ok_or("literal sources")?
            .values()
        {
            paths.insert(path.as_str().ok_or("literal path")?.to_owned());
        }
    }
    if paths.len() != 22 {
        return Err("diagnostic source closure changed".into());
    }
    let mut originals = BTreeMap::new();
    let mut rows = Vec::new();
    for path in paths {
        let raw = read(&root.join(&path))?;
        #[cfg(unix)]
        let executable = {
            use std::os::unix::fs::PermissionsExt;
            fs::metadata(root.join(&path))?.permissions().mode() & 0o111 != 0
        };
        #[cfg(not(unix))]
        let executable = false;
        rows.push(object([
            ("path", s(&path)),
            ("mode", s(if executable { "100755" } else { "100644" })),
            ("byte_length", n(raw.len())),
            ("sha256", s(hash(&raw))),
        ]));
        originals.insert(path, raw);
    }
    let roadmap = read(&root.join("docs/roadmap.md"))?;
    let source_raw = serialize_manifest(&object([
        ("schema", s("m2-evidence-source-v2")),
        (
            "roadmap_normative_sha256",
            s(roadmap_normative_sha256(&roadmap).map_err(|e| format!("roadmap: {e:?}"))?),
        ),
        ("entries", V::Array(rows)),
    ]))?;
    admit_source_projection_v2(&source_raw).map_err(|e| format!("source: {e:?}"))?;
    if std::env::var_os("GB_PARTICIPANT_BUNDLE_DIAGNOSTIC").is_some() {
        let inputs = PreflightInputsV2::default();
        let sources: BTreeMap<_, _> = inputs.sources().collect();
        let slice = gb_slice::compile_slice_v1(
            sources["studies/m2/slice-v1.json"],
            gb_slice::SliceInputs {
                declaration: sources["studies/m2/slice-v0.json"],
                content_fixture: sources["conformance/content-v0.json"],
                chess_fixture: sources["conformance/chess-v0.json"],
                game_set: sources["reports/game-set-v0.bin"],
                content_spec: sources["spec/content-v0.md"],
                constants: sources["spec/constants-v0.toml"],
                curriculum: sources["spec/curriculum-v0.toml"],
            },
        )?;
        let carrier = gb_bootstrap::carrier_v2::build_carrier(&slice)
            .map_err(|e| format!("carrier: {e:?}"))?;
        let corpus = gb_bootstrap::damage_corpus_v2::DamageCorpusV2::new(
            &slice,
            &carrier,
            sources["spec/route-data-v0.json"],
        )
        .map_err(|e| format!("corpus: {e:?}"))?;
        return diagnostic_heldouts(&corpus);
    }
    let core = build_preflight_v2(PreflightInputsV2::default())
        .map_err(|e| format!("preflight: {e:?}"))?;
    let bundles = build_participant_bundles_v2(
        &core,
        &technical_literal_sources_v2(),
        LearnerBundleSourcesV2::default(),
        &source_raw,
    )?;
    // Real, recovered bundle mutation checks. No fixtures stand in for recovery.
    let mut changed = bundles.technical_files().clone();
    changed
        .get_mut("recipient/01-clean/opening.md")
        .ok_or("opening absent")?
        .push(b' ');
    if render_bundle_manifest_v2("technical-v2", &changed, core.recovery(), &source_raw).is_ok() {
        return Err("changed literal unexpectedly admitted".into());
    }
    let mut changed = bundles.learner_files().clone();
    changed
        .get_mut("recipient/lesson.content-v0.bin")
        .ok_or("stream absent")?
        .push(0);
    if render_bundle_manifest_v2("learner-v2", &changed, core.recovery(), &source_raw).is_ok() {
        return Err("foreign content unexpectedly admitted".into());
    }
    for (path, raw) in originals {
        if read(&root.join(path))? != raw {
            return Err("diagnostic source changed during generation".into());
        }
    }
    if read(&root.join("docs/roadmap.md"))? != roadmap {
        return Err("roadmap changed during generation".into());
    }
    let mut dir = fs::DirBuilder::new();
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        dir.mode(0o700);
    }
    dir.create(out)?;
    for (id, files) in [
        ("technical-v2", bundles.technical_files()),
        ("learner-v2", bundles.learner_files()),
    ] {
        for (name, raw) in files {
            write(out, &format!("{id}/{name}"), raw)?;
        }
    }
    write(
        out,
        "technical-v2/bundle-manifest.json",
        &bundles.preimages().technical_manifest,
    )?;
    write(
        out,
        "learner-v2/bundle-manifest.json",
        &bundles.preimages().learner_manifest,
    )?;
    write(
        out,
        "bundle-preimages.json",
        &bundles.preimages().canonical_bytes,
    )?;
    write(out, "diagnostic-source-projection.json", &source_raw)?;
    write(out, "DEVELOPMENT.txt", b"Fresh local development bundle comparison only. The 22-row source projection is a diagnostic subset, not a complete source freeze. No fresh release, exposure, human result or Candidate-ready claim is implied.\n")?;
    for (name, raw) in [
        (
            "technical-manifest",
            &bundles.preimages().technical_manifest,
        ),
        ("learner-manifest", &bundles.preimages().learner_manifest),
        ("bundle-preimages", &bundles.preimages().canonical_bytes),
    ] {
        println!("{name} {} {}", raw.len(), hash(raw));
    }
    Ok(())
}
fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
