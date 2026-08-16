use std::collections::{BTreeMap, BTreeSet};
use std::fs::OpenOptions;
use std::io::Read;
#[cfg(unix)]
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use gb_chess::source::{
    GameRecord, SourceReject, compile_source, decode_game, decode_game_set, encode_game,
    encode_game_set, validate_anthology,
};
use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
use sha2::{Digest, Sha256};

const FIXTURE_BYTES: usize = 254_843;
const FIXTURE_SHA256: &str = "07c36421b2b27aa3b9ab4609f34b6f0d24d63bac9752e0c083747cb90e0f8b30";
const READ_CAP: usize = 1_048_577;
#[cfg(any(target_os = "linux", target_os = "android"))]
const O_NOFOLLOW: i32 = 0x20_000;
#[cfg(any(target_os = "macos", target_os = "ios"))]
const O_NOFOLLOW: i32 = 0x100;

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

#[cfg(unix)]
fn safe_read(relative: &str, cap: usize) -> Vec<u8> {
    assert!(!relative.is_empty());
    assert!(relative.split('/').all(|part| {
        !part.is_empty()
            && part != "."
            && part != ".."
            && part
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
    }));
    let mut path = root();
    let parts: Vec<_> = relative.split('/').collect();
    for part in &parts[..parts.len() - 1] {
        path.push(part);
        let metadata = path.symlink_metadata().unwrap();
        assert!(metadata.file_type().is_dir() && !metadata.file_type().is_symlink());
    }
    path.push(parts.last().unwrap());
    let before = path.symlink_metadata().unwrap();
    assert!(before.file_type().is_file() && !before.file_type().is_symlink());
    assert!(before.len() <= cap as u64);
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(O_NOFOLLOW)
        .open(&path)
        .unwrap();
    let after = file.metadata().unwrap();
    assert!(after.file_type().is_file());
    assert_eq!((before.dev(), before.ino()), (after.dev(), after.ino()));
    assert!(after.len() <= cap as u64);
    let mut bytes = Vec::with_capacity(after.len() as usize);
    file.take(cap as u64 + 1).read_to_end(&mut bytes).unwrap();
    assert!(bytes.len() <= cap);
    bytes
}

#[cfg(not(unix))]
fn safe_read(_relative: &str, _cap: usize) -> Vec<u8> {
    panic!("source fixture tests require no-follow file opens")
}

fn object<'a>(value: &'a V, keys: &[&str]) -> &'a BTreeMap<String, V> {
    let V::Object(fields) = value else {
        panic!("object")
    };
    assert_eq!(
        fields.keys().map(String::as_str).collect::<BTreeSet<_>>(),
        keys.iter().copied().collect::<BTreeSet<_>>()
    );
    fields
}

fn array(value: &V) -> &[V] {
    let V::Array(values) = value else {
        panic!("array")
    };
    values
}

fn text(value: &V) -> &str {
    let V::String(value) = value else {
        panic!("string")
    };
    value
}

fn number(value: &V) -> usize {
    let V::U64(value) = value else { panic!("u64") };
    usize::try_from(*value).unwrap()
}

fn field<'a>(fields: &'a BTreeMap<String, V>, key: &str) -> &'a V {
    fields.get(key).unwrap()
}

fn checked_hex(value: &V) -> Vec<u8> {
    let value = text(value);
    assert!(value.len().is_multiple_of(2));
    assert!(
        value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    );
    hex(value)
}

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn expected(value: &V, input_len: usize) -> Option<SourceReject> {
    let fields = object(
        value,
        if matches!(value, V::Object(x) if x.contains_key("accept")) {
            &["accept"]
        } else {
            &["rejection"]
        },
    );
    if let Some(accept) = fields.get("accept") {
        object(accept, &[]);
        return None;
    }
    let rejection = object(
        field(fields, "rejection"),
        &["code", "raw_end", "raw_start"],
    );
    let result = SourceReject {
        code: u16::try_from(number(field(rejection, "code"))).unwrap(),
        raw_start: u32::try_from(number(field(rejection, "raw_start"))).unwrap(),
        raw_end: u32::try_from(number(field(rejection, "raw_end"))).unwrap(),
    };
    assert!(result.raw_start <= result.raw_end && result.raw_end as usize <= input_len);
    Some(result)
}

fn assert_outcome<T>(actual: Result<T, SourceReject>, wanted: Option<SourceReject>, label: &str) {
    match (actual, wanted) {
        (Ok(_), None) => {}
        (Err(actual), Some(wanted)) => assert_eq!(actual, wanted, "{label}"),
        (Ok(_), Some(wanted)) => panic!("{label}: accepted, expected {wanted:?}"),
        (Err(actual), None) => panic!("{label}: rejected {actual:?}"),
    }
}

fn registered_fixture() -> V {
    let registry_bytes = safe_read("conformance/registry.toml", 16_384);
    let registry: toml::Value =
        toml::from_str(std::str::from_utf8(&registry_bytes).unwrap()).unwrap();
    let table = registry.as_table().unwrap();
    assert_eq!(table.len(), 2);
    assert_eq!(
        table["schema"].as_str(),
        Some("golden-board.conformance-registry/v0")
    );
    let rows = table["suite"].as_array().unwrap();
    let source: Vec<_> = rows
        .iter()
        .filter(|row| row.get("id").and_then(toml::Value::as_str) == Some("source-v0"))
        .collect();
    assert_eq!(source.len(), 1);
    let source = source[0].as_table().unwrap();
    assert_eq!(
        source.keys().map(String::as_str).collect::<BTreeSet<_>>(),
        [
            "consumers",
            "id",
            "path",
            "provenance",
            "sha256",
            "specification",
            "version",
        ]
        .into_iter()
        .collect()
    );
    assert_eq!(source["path"].as_str(), Some("conformance/source-v0.json"));
    assert_eq!(source["specification"].as_str(), Some("source-v0"));
    assert_eq!(source["version"].as_str(), Some("v0"));
    assert_eq!(source["provenance"].as_str(), Some("hand-authored"));
    assert_eq!(
        source["consumers"].as_array().unwrap(),
        &[
            toml::Value::String("python".into()),
            toml::Value::String("rust".into())
        ]
    );
    assert_eq!(source["sha256"].as_str(), Some(FIXTURE_SHA256));
    let bytes = safe_read("conformance/source-v0.json", FIXTURE_BYTES);
    assert_eq!(bytes.len(), FIXTURE_BYTES);
    assert_eq!(digest(&bytes), FIXTURE_SHA256);
    validate_canonical_manifest(&bytes).unwrap()
}

fn locked_anthology() -> Vec<u8> {
    let lock_bytes = safe_read("inputs/source-lock.toml", 16_384);
    let lock: toml::Value = toml::from_str(std::str::from_utf8(&lock_bytes).unwrap()).unwrap();
    assert_eq!(
        lock.as_table()
            .unwrap()
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>(),
        ["reference", "schema", "source"].into_iter().collect()
    );
    assert_eq!(lock["schema"].as_str(), Some("golden-board.source-lock/v0"));
    let rows: Vec<_> = lock["source"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|row| row.get("id").and_then(toml::Value::as_str) == Some("anthology"))
        .collect();
    assert_eq!(rows.len(), 1);
    let row = rows[0].as_table().unwrap();
    assert_eq!(
        row.keys().map(String::as_str).collect::<BTreeSet<_>>(),
        [
            "bytes", "encoding", "id", "newline", "path", "role", "sha256"
        ]
        .into_iter()
        .collect()
    );
    assert_eq!(row["role"].as_str(), Some("authoritative_input"));
    assert_eq!(row["path"].as_str(), Some("docs/64_games.md"));
    assert_eq!(row["bytes"].as_integer(), Some(165_145));
    assert_eq!(
        row["sha256"].as_str(),
        Some("33d44f7167ab190cc793e3fdfd8190d89ed13c1dc507c20854cf64751c7be7da")
    );
    assert_eq!(row["encoding"].as_str(), Some("utf-8"));
    assert_eq!(row["newline"].as_str(), Some("lf"));
    let bytes = safe_read("docs/64_games.md", 165_145);
    assert_eq!(bytes.len(), 165_145);
    assert_eq!(digest(&bytes), text_sha(row["sha256"].as_str().unwrap()));
    bytes
}

fn text_sha(value: &str) -> String {
    assert_eq!(value.len(), 64);
    assert!(
        value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    );
    value.to_owned()
}

fn cycle_records(input: &BTreeMap<String, V>) -> Vec<GameRecord> {
    let cycle = checked_hex(field(input, "cycle_moves_hex"));
    assert_eq!(cycle.len(), 8);
    let score = u8::try_from(number(field(input, "score"))).unwrap();
    assert!(score <= 2);
    let counts = array(field(input, "ply_counts"));
    let total = counts
        .iter()
        .try_fold(0usize, |total, count| total.checked_add(number(count)))
        .unwrap();
    assert!(total <= 65_536);
    counts
        .iter()
        .map(|count| {
            let count = number(count);
            assert!((1..=4096).contains(&count));
            let mut raw = Vec::with_capacity(3 + count * 2);
            raw.extend_from_slice(&(count as u16).to_be_bytes());
            for ply in 0..count {
                raw.extend_from_slice(&cycle[(ply % 4) * 2..(ply % 4 + 1) * 2]);
            }
            raw.push(score);
            decode_game(&raw).unwrap()
        })
        .collect()
}

fn expand_recipe(row: &BTreeMap<String, V>, locked: &[u8]) -> Vec<u8> {
    let kind = text(field(row, "recipe"));
    let expected_keys = if kind == "locked-base-patch" {
        &[
            "expected",
            "input",
            "input_bytes",
            "input_sha256",
            "name",
            "operation",
            "patch_cap",
            "recipe",
        ][..]
    } else {
        &[
            "count_cap",
            "expected",
            "input",
            "input_bytes",
            "input_sha256",
            "name",
            "operation",
            "recipe",
        ][..]
    };
    assert_eq!(
        row.keys().map(String::as_str).collect::<BTreeSet<_>>(),
        expected_keys.iter().copied().collect()
    );
    let input = match field(row, "input") {
        V::Object(input) => input,
        _ => panic!("recipe input object"),
    };
    if kind != "locked-base-patch" {
        let cap = number(field(row, "count_cap"));
        let ceiling = match kind {
            "literal-repeat" => READ_CAP,
            "knight-cycle-corpus" => 64,
            "typed-game-set-games" => 65_536,
            "typed-game-set-total-plies" => 16,
            "typed-anthology" => 65,
            _ => panic!("unknown source recipe {kind}"),
        };
        assert!(cap <= ceiling, "{kind} count cap {cap} exceeds {ceiling}");
    }
    let raw = match kind {
        "literal-repeat" => {
            object(
                field(row, "input"),
                &["prefix_hex", "repeat_count", "repeat_hex", "suffix_hex"],
            );
            let prefix = checked_hex(field(input, "prefix_hex"));
            let repeated = checked_hex(field(input, "repeat_hex"));
            let suffix = checked_hex(field(input, "suffix_hex"));
            let count = number(field(input, "repeat_count"));
            assert!(count <= number(field(row, "count_cap")));
            let length = prefix
                .len()
                .checked_add(repeated.len().checked_mul(count).unwrap())
                .unwrap()
                .checked_add(suffix.len())
                .unwrap();
            assert!(length <= READ_CAP);
            let mut raw = Vec::with_capacity(length);
            raw.extend_from_slice(&prefix);
            for _ in 0..count {
                raw.extend_from_slice(&repeated);
            }
            raw.extend_from_slice(&suffix);
            raw
        }
        "locked-base-patch" => {
            object(field(row, "input"), &["base", "patches"]);
            assert_eq!(text(field(input, "base")), "locked-anthology");
            let patches = array(field(input, "patches"));
            assert!(patches.len() <= number(field(row, "patch_cap")));
            assert_eq!(number(field(row, "patch_cap")), 4);
            let mut raw = locked.to_vec();
            let mut prior = locked.len() + 1;
            for patch in patches {
                let patch = object(patch, &["old_hex", "replacement_hex", "start"]);
                let start = number(field(patch, "start"));
                let old = checked_hex(field(patch, "old_hex"));
                let replacement = checked_hex(field(patch, "replacement_hex"));
                let end = start.checked_add(old.len()).unwrap();
                assert!(start < prior && end <= prior && end <= locked.len());
                assert_eq!(&locked[start..end], old);
                assert_eq!(&raw[start..end], old);
                let length = raw.len() - old.len() + replacement.len();
                assert!(length <= READ_CAP);
                raw.splice(start..end, replacement);
                prior = start;
            }
            raw
        }
        "knight-cycle-corpus" => {
            let input_keys = input.keys().map(String::as_str).collect::<BTreeSet<_>>();
            assert!(
                input_keys == ["cycle", "ply_counts", "result"].into_iter().collect()
                    || input_keys
                        == ["cycle", "newline_hex", "ply_counts", "result"]
                            .into_iter()
                            .collect()
            );
            let cycle: Vec<_> = array(field(input, "cycle")).iter().map(text).collect();
            assert_eq!(cycle, ["Nf3", "Nf6", "Ng1", "Ng8"]);
            assert_eq!(text(field(input, "result")), "1/2-1/2");
            let newline = input
                .get("newline_hex")
                .map_or_else(|| b"\n".to_vec(), checked_hex);
            assert!(newline == b"\n" || newline == b"\r\n");
            let counts = array(field(input, "ply_counts"));
            assert!(counts.len() <= number(field(row, "count_cap")));
            let mut total = 0usize;
            let mut raw = Vec::new();
            for count in counts {
                let count = number(count);
                assert!((1..=4096).contains(&count));
                total = total.checked_add(count).unwrap();
                assert!(total <= 65_536);
                let mut tokens = Vec::with_capacity(count + (count + 1) / 2 + 1);
                for ply in 0..count {
                    if ply % 2 == 0 {
                        tokens.push(format!("{}.", ply / 2 + 1));
                    }
                    tokens.push(cycle[ply % 4].to_owned());
                }
                tokens.push("1/2-1/2".to_owned());
                for (index, line) in [
                    "```pgn".to_owned(),
                    "[Result \"1/2-1/2\"]".to_owned(),
                    String::new(),
                    tokens.join(" "),
                    "```".to_owned(),
                    String::new(),
                ]
                .into_iter()
                .enumerate()
                {
                    if index != 0 {
                        raw.extend_from_slice(&newline);
                    }
                    raw.extend_from_slice(line.as_bytes());
                }
                assert!(raw.len() <= READ_CAP);
            }
            raw
        }
        "typed-game-set-games" => {
            object(field(row, "input"), &["count", "unit_hex"]);
            let unit = checked_hex(field(input, "unit_hex"));
            let count = number(field(input, "count"));
            assert!(count <= number(field(row, "count_cap")));
            let length = unit.len().checked_mul(count).unwrap();
            assert!(length <= READ_CAP);
            unit.repeat(count)
        }
        "typed-game-set-total-plies" | "typed-anthology" => {
            object(
                field(row, "input"),
                &["cycle_moves_hex", "ply_counts", "score"],
            );
            let counts = array(field(input, "ply_counts"));
            assert!(counts.len() <= number(field(row, "count_cap")));
            let records = cycle_records(input);
            let total: usize = records.iter().map(|record| encode_game(record).len()).sum();
            assert!(total <= READ_CAP);
            records.iter().flat_map(encode_game).collect()
        }
        _ => panic!("unknown source recipe {kind}"),
    };
    assert_eq!(raw.len(), number(field(row, "input_bytes")));
    let sha = text(field(row, "input_sha256"));
    assert_eq!(text_sha(sha), digest(&raw));
    raw
}

struct FixtureRow {
    operation: String,
    name: String,
    raw: Vec<u8>,
    wanted: Option<SourceReject>,
    source: V,
}

static FIXTURE_ROWS: OnceLock<(Vec<FixtureRow>, usize)> = OnceLock::new();

fn fixture_rows() -> &'static (Vec<FixtureRow>, usize) {
    FIXTURE_ROWS.get_or_init(|| {
        let fixture = registered_fixture();
        let top = object(&fixture, &["bases", "cases", "recipes", "schema"]);
        assert_eq!(
            text(field(top, "schema")),
            "golden-board.source-v0-fixtures/v0"
        );
        let bases = array(field(top, "bases"));
        assert_eq!(bases.len(), 1);
        let base = object(&bases[0], &["id", "source_lock_id"]);
        assert_eq!(text(field(base, "id")), "locked-anthology");
        assert_eq!(text(field(base, "source_lock_id")), "anthology");
        let locked = locked_anthology();
        let cases = array(field(top, "cases"));
        let recipes = array(field(top, "recipes"));
        assert_eq!((cases.len(), recipes.len()), (71, 115));

        let mut names = BTreeSet::new();
        let mut rows = Vec::with_capacity(186);
        for source in cases {
            let row = object(source, &["expected", "input_hex", "name", "operation"]);
            let raw = checked_hex(field(row, "input_hex"));
            let name = text(field(row, "name")).to_owned();
            assert!(!name.is_empty() && names.insert(name.clone()));
            rows.push(FixtureRow {
                operation: text(field(row, "operation")).to_owned(),
                name,
                wanted: expected(field(row, "expected"), raw.len()),
                raw,
                source: source.clone(),
            });
        }
        for source in recipes {
            let V::Object(row) = source else {
                panic!("recipe row")
            };
            let raw = expand_recipe(row, &locked);
            let name = text(field(row, "name")).to_owned();
            assert!(!name.is_empty() && names.insert(name.clone()));
            rows.push(FixtureRow {
                operation: text(field(row, "operation")).to_owned(),
                name,
                wanted: expected(field(row, "expected"), raw.len()),
                raw,
                source: source.clone(),
            });
        }

        let mut counts = BTreeMap::new();
        for row in &rows {
            *counts.entry(row.operation.as_str()).or_insert(0usize) += 1;
        }
        assert_eq!(
            counts,
            BTreeMap::from([
                ("compile_source", 151),
                ("decode_game", 12),
                ("decode_game_set", 9),
                ("encode_game_set", 4),
                ("validate_anthology", 4),
                ("validate_candidate_trace", 6),
            ])
        );
        assert_eq!(rows.len(), 186);
        (rows, 6)
    })
}

fn recipe_input(row: &FixtureRow) -> &BTreeMap<String, V> {
    let V::Object(fields) = &row.source else {
        panic!()
    };
    let V::Object(input) = field(fields, "input") else {
        panic!()
    };
    input
}

#[test]
fn registered_fixture_inventory_is_closed_before_dispatch() {
    let (rows, deferred) = fixture_rows();
    assert_eq!(rows.len() - deferred, 180);
    assert_eq!(*deferred, 6);
}

#[test]
fn registered_binary_rows_dispatch_by_operation() {
    let (rows, _) = fixture_rows();
    let mut consumed = 0usize;
    for row in rows {
        match row.operation.as_str() {
            "decode_game" => {
                assert_outcome(decode_game(&row.raw), row.wanted, &row.name);
                consumed += 1;
            }
            "decode_game_set" => {
                assert_outcome(decode_game_set(&row.raw), row.wanted, &row.name);
                consumed += 1;
            }
            "encode_game_set" => {
                let recipe = text(field(
                    match &row.source {
                        V::Object(fields) => fields,
                        _ => panic!(),
                    },
                    "recipe",
                ));
                let records = if recipe == "typed-game-set-games" {
                    let input = recipe_input(&row);
                    let unit = decode_game(&checked_hex(field(input, "unit_hex"))).unwrap();
                    vec![unit; number(field(input, "count"))]
                } else {
                    cycle_records(recipe_input(&row))
                };
                assert_outcome(encode_game_set(&records), row.wanted, &row.name);
                consumed += 1;
            }
            "validate_anthology" => {
                assert_outcome(
                    validate_anthology(&cycle_records(recipe_input(&row))),
                    row.wanted,
                    &row.name,
                );
                consumed += 1;
            }
            "compile_source" | "validate_candidate_trace" => {}
            operation => panic!("unknown operation {operation}"),
        }
    }
    assert_eq!(consumed, 29);
}

#[test]
fn registered_compile_stage_one_through_six_rejections() {
    let (rows, _) = fixture_rows();
    let mut consumed = 0usize;
    for row in rows {
        if row.operation == "compile_source" && row.wanted.is_some_and(|wanted| wanted.code <= 40) {
            assert_outcome(compile_source(&row.raw), row.wanted, &row.name);
            consumed += 1;
        }
    }
    assert_eq!(consumed, 98);
}

#[test]
fn registered_compile_semantic_rejections() {
    let (rows, _) = fixture_rows();
    let mut consumed = 0usize;
    for row in rows {
        if row.operation == "compile_source"
            && row
                .wanted
                .is_some_and(|wanted| (41..=48).contains(&wanted.code))
        {
            let actual = compile_source(&row.raw);
            if let (Err(actual), Some(wanted)) = (&actual, row.wanted) {
                if *actual != wanted {
                    let start = actual.raw_start as usize;
                    let end = actual.raw_end as usize;
                    panic!(
                        "{}: actual {actual:?} token {:?}, wanted {wanted:?}",
                        row.name,
                        String::from_utf8_lossy(&row.raw[start..end])
                    );
                }
            }
            assert_outcome(actual, row.wanted, &row.name);
            consumed += 1;
        }
    }
    assert_eq!(consumed, 30);
}

#[test]
fn registered_compile_rows_dispatch_by_operation() {
    let (rows, _) = fixture_rows();
    let mut consumed = 0usize;
    for row in rows {
        match row.operation.as_str() {
            "compile_source" => {
                assert_outcome(compile_source(&row.raw), row.wanted, &row.name);
                consumed += 1;
            }
            "decode_game"
            | "decode_game_set"
            | "encode_game_set"
            | "validate_anthology"
            | "validate_candidate_trace" => {}
            operation => panic!("unknown operation {operation}"),
        }
    }
    assert_eq!(consumed, 151);
}

#[test]
fn locked_anthology_compiles_atomically_and_deterministically() {
    let raw = locked_anthology();
    let first = compile_source(&raw).unwrap();
    let second = compile_source(&raw).unwrap();
    assert_eq!((first.game_count(), first.ply_count()), (64, 4_915));
    assert_eq!(first.game_set_bytes(), second.game_set_bytes());

    let games = decode_game_set(first.game_set_bytes()).unwrap();
    assert_eq!(games.len(), 64);
    let encoded: Vec<Vec<u8>> = games.iter().map(encode_game).collect();
    assert_eq!(
        encoded
            .iter()
            .map(|game| u16::from_be_bytes([game[0], game[1]]) as usize)
            .sum::<usize>(),
        4_915
    );
    assert!(encoded.windows(2).all(|pair| pair[0] < pair[1]));
    for game in encoded {
        assert_eq!(encode_game(&decode_game(&game).unwrap()), game);
    }
}

fn replace_once(raw: &[u8], old: &[u8], replacement: &[u8]) -> Vec<u8> {
    let at = raw
        .windows(old.len())
        .position(|window| window == old)
        .unwrap();
    let mut output = Vec::with_capacity(raw.len() - old.len() + replacement.len());
    output.extend_from_slice(&raw[..at]);
    output.extend_from_slice(replacement);
    output.extend_from_slice(&raw[at + old.len()..]);
    output
}

fn complete_blocks(raw: &[u8]) -> Vec<Vec<u8>> {
    let mut blocks = Vec::new();
    let mut at = 0usize;
    while let Some(offset) = raw[at..].windows(6).position(|window| window == b"```pgn") {
        let start = at + offset;
        let content = raw[start..]
            .windows(4)
            .position(|window| window == b"```\n")
            .unwrap();
        let end = start + content + 4;
        blocks.push(raw[start..end].to_vec());
        at = end;
    }
    assert_eq!(blocks.len(), 64);
    blocks
}

#[test]
fn source_compilation_is_invariant_only_under_owned_grammar_changes() {
    let raw = locked_anthology();
    let baseline = compile_source(&raw).unwrap().game_set_bytes().to_vec();

    let mut crlf =
        Vec::with_capacity(raw.len() + raw.iter().filter(|&&byte| byte == b'\n').count());
    for &byte in &raw {
        if byte == b'\n' {
            crlf.push(b'\r');
        }
        crlf.push(byte);
    }
    assert_eq!(compile_source(&crlf).unwrap().game_set_bytes(), baseline);

    let opaque = replace_once(&raw, b"```pgn\n", b"```pgn\n[Opaque \"untrusted data\"]\n");
    assert_eq!(compile_source(&opaque).unwrap().game_set_bytes(), baseline);

    let prose = [
        b"outer heading  \n".as_slice(),
        raw.as_slice(),
        b"outer tail\t\n".as_slice(),
    ]
    .concat();
    assert_eq!(compile_source(&prose).unwrap().game_set_bytes(), baseline);

    let hws = replace_once(&raw, b"1. e4 c5 2. Nf3", b"1.\te4  c5\n2. Nf3");
    assert_eq!(compile_source(&hws).unwrap().game_set_bytes(), baseline);

    let mut blocks = complete_blocks(&raw);
    blocks.reverse();
    let permuted: Vec<u8> = blocks.into_iter().flatten().collect();
    assert_eq!(
        compile_source(&permuted).unwrap().game_set_bytes(),
        baseline
    );
}

#[test]
fn rejection_is_atomic_and_named_source_mutants_are_killed() {
    let raw = locked_anthology();
    let accepted = compile_source(&raw).unwrap();
    let accepted_before = accepted.game_set_bytes().to_vec();
    let mut bad = raw.clone();
    bad[0] = 0;
    let bad_before = bad.clone();
    assert_eq!(compile_source(&bad).unwrap_err().code, 4);
    assert_eq!(bad, bad_before);
    assert_eq!(accepted.game_set_bytes(), accepted_before);

    let (rows, _) = fixture_rows();
    let names = [
        "san-suffix-extra-check",
        "san-suffix-missing-check",
        "san-suffix-wrong-mate",
        "san-suffix-missing-mate",
        "accept-san-pinned-pseudo-mover-excluded",
        "san-noncanonical-redundant-file",
        "terminal-after-checkmate",
        "terminal-after-stalemate",
        "terminal-after-common-dead",
    ];
    for name in names {
        let row = rows.iter().find(|row| row.name == name).unwrap();
        assert_eq!(row.operation, "compile_source");
        assert_outcome(compile_source(&row.raw), row.wanted, name);
    }
}

#[test]
fn empty_source_rejects_at_the_final_newline_boundary() {
    let error = compile_source(b"").unwrap_err();
    assert_eq!((error.code, error.raw_start, error.raw_end), (7, 0, 0));
}

#[test]
fn game_and_set_bytes_round_trip_the_identity_anchor() {
    let game_bytes = hex("00043550d24039e0edf001");
    let game = decode_game(&game_bytes).unwrap();
    assert_eq!(encode_game(&game), game_bytes);

    let set_bytes = hex("000100043550d24039e0edf001");
    let games = decode_game_set(&set_bytes).unwrap();
    assert_eq!(games.len(), 1);
    assert_eq!(encode_game_set(&games).unwrap(), set_bytes);

    let error = decode_game(&[0, 0, 0]).unwrap_err();
    assert_eq!((error.code, error.raw_start, error.raw_end), (49, 0, 2));
}

#[test]
fn raw_profile_and_fence_count_follow_owner_stage_order() {
    let error = compile_source(b"\xef\xbb\xbf\n").unwrap_err();
    assert_eq!((error.code, error.raw_start, error.raw_end), (2, 0, 3));

    let block = b"```pgn\n[Result \"1-0\"]\n\n1. e4 1-0\n```\n";
    let raw = block.repeat(63);
    let error = compile_source(&raw).unwrap_err();
    assert_eq!(
        (error.code, error.raw_start, error.raw_end),
        (13, raw.len() as u32, raw.len() as u32)
    );
}

#[test]
fn result_tag_value_is_rejected_before_movetext_structure() {
    let bad = b"```pgn\n[Result \"*\"]\n\n1. ??? *\n```\n";
    let valid = b"```pgn\n[Result \"1-0\"]\n\n1. e4 1-0\n```\n";
    let mut raw = bad.to_vec();
    raw.extend_from_slice(&valid.repeat(63));
    let at = raw.iter().position(|&byte| byte == b'*').unwrap() as u32;
    let error = compile_source(&raw).unwrap_err();
    assert_eq!(
        (error.code, error.raw_start, error.raw_end),
        (22, at, at + 1)
    );
}

fn hex(value: &str) -> Vec<u8> {
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let digit = |byte| match byte {
                b'0'..=b'9' => byte - b'0',
                b'a'..=b'f' => byte - b'a' + 10,
                _ => panic!("lowercase hex"),
            };
            digit(pair[0]) << 4 | digit(pair[1])
        })
        .collect()
}
