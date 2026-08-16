use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, OpenOptions};
use std::io::Read;
#[cfg(unix)]
use std::os::unix::fs::OpenOptionsExt;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use gb_foundation::{
    ManifestValue, canonicalize_manifest, frame_preimage, identity_hex, parse_manifest,
    serialize_manifest, u16_be, u32_be, validate_canonical_manifest,
};
use serde_json::Value;
use sha2::{Digest, Sha256};

const MAX_BYTES: usize = 1_048_576;
const M0_IDENTITY_VECTORS_SHA256: &str =
    "19b90c4ab863ca3853a1b8229b8ae84a886e4a8cf0c3bee496157e592bf000ae";
const M1_IDENTITY_VECTORS: [(&str, &str, &str, &str, &str); 4] = [
    (
        "initial-position",
        "676f6c64656e2d626f6172643a706f736974696f6e3a763000",
        "04020305060302040101010101010101000000000000000000000000000000000000000000000000000000000000000007070707070707070a08090b0c09080a000f00",
        "676f6c64656e2d626f6172643a706f736974696f6e3a76300000010000004304020305060302040101010101010101000000000000000000000000000000000000000000000000000000000000000007070707070707070a08090b0c09080a000f00",
        "7d578698cdb2095a1b818234f12b3e6d4f19bbadb414887f26e6a8d52417a186",
    ),
    (
        "initial-repetition-key",
        "676f6c64656e2d626f6172643a72657065746974696f6e2d6b65793a763000",
        "04020305060302040101010101010101000000000000000000000000000000000000000000000000000000000000000007070707070707070a08090b0c09080a000f00",
        "676f6c64656e2d626f6172643a72657065746974696f6e2d6b65793a76300000010000004304020305060302040101010101010101000000000000000000000000000000000000000000000000000000000000000007070707070707070a08090b0c09080a000f00",
        "b12da42c15cc340394688be5d771ad8936241e9dcb03592b2791e06b9dbe33e3",
    ),
    (
        "fools-mate-game",
        "676f6c64656e2d626f6172643a67616d653a763000",
        "00043550d24039e0edf001",
        "676f6c64656e2d626f6172643a67616d653a76300000010000000b00043550d24039e0edf001",
        "c49a921d652aa82b69a320073ca7ca0f5f3adf3d4ccc80d5aea162a52925b3bb",
    ),
    (
        "fools-mate-game-set",
        "676f6c64656e2d626f6172643a67616d652d7365743a763000",
        "000100043550d24039e0edf001",
        "676f6c64656e2d626f6172643a67616d652d7365743a76300000010000000d000100043550d24039e0edf001",
        "4070001b03556dcf41043adcf7a261c4b20aa7874a8033546520a48107fbc2f8",
    ),
];

#[cfg(any(target_os = "linux", target_os = "android"))]
const O_NOFOLLOW: i32 = 0x20_000;
#[cfg(any(target_os = "macos", target_os = "ios"))]
const O_NOFOLLOW: i32 = 0x100;

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn fixture(name: &str) -> Vec<u8> {
    fs::read(root().join("conformance").join(name)).unwrap()
}

fn hex_bytes(value: &str) -> Vec<u8> {
    assert!(value.len().is_multiple_of(2));
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let text = std::str::from_utf8(pair).unwrap();
            u8::from_str_radix(text, 16).unwrap()
        })
        .collect()
}

fn m1_identity_vector_is_closed(value: &Value) -> bool {
    value.as_object().is_some_and(|row| {
        row.len() == 5
            && [
                "domain_hex",
                "fields_hex",
                "identity",
                "name",
                "preimage_hex",
            ]
            .iter()
            .all(|key| row.contains_key(*key))
    })
}

#[cfg(unix)]
fn direct_file_bytes(path: &Path) -> Result<Vec<u8>, String> {
    let metadata = fs::symlink_metadata(path).map_err(|error| error.to_string())?;
    if metadata.file_type().is_symlink()
        || !metadata.file_type().is_file()
        || metadata.len() > MAX_BYTES as u64
    {
        return Err("unsafe conformance file".into());
    }
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(O_NOFOLLOW)
        .open(path)
        .map_err(|error| error.to_string())?;
    let metadata = file.metadata().map_err(|error| error.to_string())?;
    if !metadata.file_type().is_file() || metadata.len() > MAX_BYTES as u64 {
        return Err("unsafe conformance file".into());
    }
    let mut bytes = Vec::with_capacity(metadata.len() as usize);
    file.take(MAX_BYTES as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| error.to_string())?;
    if bytes.len() > MAX_BYTES {
        return Err("unsafe conformance file".into());
    }
    Ok(bytes)
}

#[cfg(not(unix))]
fn direct_file_bytes(_path: &Path) -> Result<Vec<u8>, String> {
    Err("no no-follow file open available".into())
}

fn registry_identifier(value: &str) -> bool {
    !value.is_empty()
        && value.split('-').all(|part| {
            !part.is_empty()
                && part
                    .bytes()
                    .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit())
        })
}

fn validate_conformance_registry(repository: &Path) -> Result<(), String> {
    let conformance = repository.join("conformance");
    let directory_metadata =
        fs::symlink_metadata(&conformance).map_err(|error| error.to_string())?;
    if directory_metadata.file_type().is_symlink() || !directory_metadata.is_dir() {
        return Err("unsafe conformance directory".into());
    }
    let registry_bytes = direct_file_bytes(&conformance.join("registry.toml"))?;
    let registry: toml::Value =
        toml::from_str(std::str::from_utf8(&registry_bytes).map_err(|error| error.to_string())?)
            .map_err(|error| error.to_string())?;
    let table = registry
        .as_table()
        .ok_or_else(|| "invalid conformance registry".to_owned())?;
    if table.len() != 2
        || table.get("schema").and_then(toml::Value::as_str)
            != Some("golden-board.conformance-registry/v0")
        || !table.contains_key("suite")
    {
        return Err("invalid conformance registry".into());
    }
    let suites = table["suite"]
        .as_array()
        .ok_or_else(|| "invalid conformance registry".to_owned())?;
    let row_keys = [
        "id",
        "path",
        "specification",
        "version",
        "sha256",
        "consumers",
        "provenance",
    ];
    let mut identifiers = BTreeSet::new();
    let mut paths = BTreeSet::new();
    for suite in suites {
        let row = suite
            .as_table()
            .ok_or_else(|| "invalid conformance registry".to_owned())?;
        if row.len() != row_keys.len() || !row_keys.iter().all(|key| row.contains_key(*key)) {
            return Err("invalid conformance registry".into());
        }
        let identifier = row["id"]
            .as_str()
            .ok_or_else(|| "invalid conformance registry".to_owned())?;
        let specification = row["specification"]
            .as_str()
            .ok_or_else(|| "invalid conformance registry".to_owned())?;
        let path = row["path"]
            .as_str()
            .ok_or_else(|| "invalid conformance registry".to_owned())?;
        let digest = row["sha256"]
            .as_str()
            .ok_or_else(|| "invalid conformance registry".to_owned())?;
        let consumers = row["consumers"]
            .as_array()
            .ok_or_else(|| "invalid conformance registry".to_owned())?;
        if !registry_identifier(identifier)
            || !registry_identifier(specification)
            || path != format!("conformance/{identifier}.json")
            || !identifiers.insert(identifier)
            || !paths.insert(path.to_owned())
            || row["version"].as_str() != Some("v0")
            || digest.len() != 64
            || !digest
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            || consumers.as_slice()
                != [
                    toml::Value::String("python".into()),
                    toml::Value::String("rust".into()),
                ]
            || row["provenance"].as_str() != Some("hand-authored")
        {
            return Err("invalid conformance registry".into());
        }
        let payload = direct_file_bytes(&repository.join(path))?;
        if format!("{:x}", Sha256::digest(payload)) != digest {
            return Err("invalid conformance registry".into());
        }
    }

    let mut inventory = BTreeSet::new();
    for entry in fs::read_dir(conformance).map_err(|error| error.to_string())? {
        let entry = entry.map_err(|error| error.to_string())?;
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| "invalid conformance filename".to_owned())?;
        if name == "registry.toml" {
            continue;
        }
        let metadata = fs::symlink_metadata(entry.path()).map_err(|error| error.to_string())?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err("unsafe conformance inventory".into());
        }
        inventory.insert(format!("conformance/{name}"));
        if inventory.len() > paths.len() {
            return Err("invalid conformance inventory".into());
        }
    }
    if inventory != paths {
        return Err("invalid conformance inventory".into());
    }
    Ok(())
}

#[test]
fn registry_hashes_and_paths_match() {
    validate_conformance_registry(&root()).unwrap();
}

static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

struct TestRepo {
    path: PathBuf,
}

impl TestRepo {
    fn new(payload: &[u8]) -> Self {
        let parent = std::env::temp_dir();
        let path = (0..100)
            .find_map(|_| {
                let serial = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
                let candidate = parent.join(format!(
                    "golden-board-registry-{}-{serial}",
                    std::process::id()
                ));
                match fs::create_dir(&candidate) {
                    Ok(()) => Some(candidate),
                    Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => None,
                    Err(error) => panic!("temporary repository creation failed: {error}"),
                }
            })
            .expect("could not create a unique bounded temporary repository");
        fs::create_dir(path.join("conformance")).unwrap();
        let repository = Self { path };
        repository.write_valid(payload);
        repository
    }

    fn payload_path(&self) -> PathBuf {
        self.path.join("conformance/identity-v0.json")
    }

    fn write_valid(&self, payload: &[u8]) {
        fs::write(self.payload_path(), payload).unwrap();
        fs::write(
            self.path.join("conformance/registry.toml"),
            test_registry(payload),
        )
        .unwrap();
    }
}

impl Drop for TestRepo {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.path).unwrap();
    }
}

fn test_registry(payload: &[u8]) -> Vec<u8> {
    format!(
        concat!(
            "schema = \"golden-board.conformance-registry/v0\"\n\n",
            "[[suite]]\n",
            "id = \"identity-v0\"\n",
            "path = \"conformance/identity-v0.json\"\n",
            "specification = \"identity-v0\"\n",
            "version = \"v0\"\n",
            "sha256 = \"{:x}\"\n",
            "consumers = [\"python\", \"rust\"]\n",
            "provenance = \"hand-authored\"\n",
        ),
        Sha256::digest(payload)
    )
    .into_bytes()
}

fn replace_once(source: &[u8], from: &str, to: &str) -> Vec<u8> {
    std::str::from_utf8(source)
        .unwrap()
        .replacen(from, to, 1)
        .into_bytes()
}

#[test]
fn registry_toml_mutations_fail_closed() {
    let payload = b"fixture\n";
    let registry = test_registry(payload);
    let row = std::str::from_utf8(&registry)
        .unwrap()
        .split_once("[[suite]]\n")
        .unwrap()
        .1;
    let path = "path = \"conformance/identity-v0.json\"";
    let replacements = [
        (
            "missing_top_key",
            "schema = \"golden-board.conformance-registry/v0\"\n\n",
            "",
        ),
        (
            "extra_top_key",
            "\n\n[[suite]]",
            "\nextra = true\n\n[[suite]]",
        ),
        ("bad_schema", "registry/v0", "registry/v1"),
        ("missing_row_key", "version = \"v0\"\n", ""),
        ("bad_id_empty", "id = \"identity-v0\"", "id = \"\""),
        ("bad_id_uppercase", "identity-v0", "Identity-v0"),
        ("bad_id_hyphens", "identity-v0", "identity--v0"),
        (
            "bad_specification",
            "specification = \"identity-v0\"",
            "specification = \"identity_v0\"",
        ),
        ("empty_path", path, "path = \"\""),
        ("parent_path", path, "path = \"../identity-v0.json\""),
        ("absolute_path", path, "path = \"/identity-v0.json\""),
        (
            "nested_path",
            path,
            "path = \"conformance/nested/identity-v0.json\"",
        ),
        (
            "backslash_alias",
            path,
            "path = 'conformance\\identity-v0.json'",
        ),
        (
            "nul_path",
            path,
            "path = \"conformance/identity-v0\\u0000.json\"",
        ),
        ("dot_path", path, "path = \".\""),
        ("dot_dot_path", path, "path = \"..\""),
        (
            "alternate_path",
            path,
            "path = \"conformance/./identity-v0.json\"",
        ),
        (
            "registry_self_path",
            path,
            "path = \"conformance/registry.toml\"",
        ),
        ("bad_version", "version = \"v0\"", "version = \"v1\""),
        (
            "bad_consumers",
            "[\"python\", \"rust\"]",
            "[\"rust\", \"python\"]",
        ),
        ("bad_provenance", "hand-authored", "generated"),
    ];
    let mut mutations: Vec<_> = replacements
        .into_iter()
        .map(|(name, from, to)| (name, replace_once(&registry, from, to)))
        .collect();
    let duplicate_path_row = row.replacen("id = \"identity-v0\"", "id = \"manifest-v0\"", 1);
    let mut oversized = registry.clone();
    oversized.resize(MAX_BYTES + 1, b' ');
    mutations.extend([
        (
            "missing_suite",
            b"schema = \"golden-board.conformance-registry/v0\"\n".to_vec(),
        ),
        (
            "extra_row_key",
            [registry.as_slice(), b"extra = \"x\"\n"].concat(),
        ),
        (
            "bad_hash",
            replace_once(
                &registry,
                &format!("{:x}", Sha256::digest(payload)),
                &"A".repeat(64),
            ),
        ),
        (
            "duplicate_id",
            [registry.as_slice(), b"[[suite]]\n", row.as_bytes()].concat(),
        ),
        (
            "duplicate_path",
            [
                registry.as_slice(),
                b"[[suite]]\n",
                duplicate_path_row.as_bytes(),
            ]
            .concat(),
        ),
        ("oversized_registry", oversized),
    ]);
    for (name, mutation) in mutations {
        let repository = TestRepo::new(payload);
        fs::write(repository.path.join("conformance/registry.toml"), mutation).unwrap();
        assert!(
            validate_conformance_registry(&repository.path).is_err(),
            "{name}"
        );
    }
}

#[test]
fn registry_tree_mutations_fail_closed() {
    for name in [
        "missing_target",
        "unregistered_payload",
        "direct_symlink",
        "non_regular_target",
        "hash_mismatch",
        "inventory_mismatch",
        "unexpected_symlink",
        "registry_symlink",
        "registry_non_regular",
    ] {
        let repository = TestRepo::new(b"fixture\n");
        let payload = repository.payload_path();
        match name {
            "missing_target" => fs::remove_file(payload).unwrap(),
            "unregistered_payload" => {
                fs::write(
                    repository.path.join("conformance/manifest-v0.json"),
                    b"extra\n",
                )
                .unwrap();
            }
            "direct_symlink" => {
                fs::remove_file(&payload).unwrap();
                let target = repository.path.join("target.json");
                fs::write(&target, b"fixture\n").unwrap();
                std::os::unix::fs::symlink(target, payload).unwrap();
            }
            "non_regular_target" => {
                fs::remove_file(&payload).unwrap();
                fs::create_dir(payload).unwrap();
            }
            "hash_mismatch" => fs::write(payload, b"changed\n").unwrap(),
            "inventory_mismatch" => {
                fs::remove_file(payload).unwrap();
                fs::write(
                    repository.path.join("conformance/manifest-v0.json"),
                    b"fixture\n",
                )
                .unwrap();
            }
            "unexpected_symlink" => {
                let target = repository.path.join("target.json");
                fs::write(&target, b"extra\n").unwrap();
                std::os::unix::fs::symlink(target, repository.path.join("conformance/extra.json"))
                    .unwrap();
            }
            "registry_symlink" => {
                let registry = repository.path.join("conformance/registry.toml");
                let bytes = fs::read(&registry).unwrap();
                fs::remove_file(&registry).unwrap();
                let target = repository.path.join("registry.toml");
                fs::write(&target, bytes).unwrap();
                std::os::unix::fs::symlink(target, registry).unwrap();
            }
            "registry_non_regular" => {
                let registry = repository.path.join("conformance/registry.toml");
                fs::remove_file(&registry).unwrap();
                fs::create_dir(registry).unwrap();
            }
            _ => unreachable!(),
        }
        assert!(
            validate_conformance_registry(&repository.path).is_err(),
            "{name}"
        );
    }
}

#[test]
fn registry_payload_byte_boundaries() {
    for (size, accepted) in [(MAX_BYTES, true), (MAX_BYTES + 1, false)] {
        let repository = TestRepo::new(&vec![b'x'; size]);
        assert_eq!(
            validate_conformance_registry(&repository.path).is_ok(),
            accepted,
            "payload size {size}"
        );
    }
}

#[test]
fn identity_fixture_and_boundaries() {
    let original = fixture("identity-v0.json");
    let data: Value = serde_json::from_slice(&original).unwrap();
    let vectors = data["vectors"].as_array().unwrap();
    assert_eq!(vectors.len(), 12);
    assert_eq!(
        format!(
            "{:x}",
            Sha256::digest(serde_json::to_vec(&vectors[..8]).unwrap())
        ),
        M0_IDENTITY_VECTORS_SHA256
    );
    for (case, (name, domain, field, preimage, digest)) in
        vectors[8..].iter().zip(M1_IDENTITY_VECTORS)
    {
        assert!(m1_identity_vector_is_closed(case));
        assert_eq!(case["name"], name);
        assert_eq!(case["domain_hex"], domain);
        assert_eq!(case["fields_hex"], serde_json::json!([field]));
        assert_eq!(case["preimage_hex"], preimage);
        assert_eq!(case["identity"], digest);
    }
    let mut extra_key = vectors[8].clone();
    extra_key
        .as_object_mut()
        .unwrap()
        .insert("extra".into(), Value::Null);
    assert!(!m1_identity_vector_is_closed(&extra_key));
    for case in vectors {
        let domain = hex_bytes(case["domain_hex"].as_str().unwrap());
        let fields: Vec<Vec<u8>> = case["fields_hex"]
            .as_array()
            .unwrap()
            .iter()
            .map(|value| hex_bytes(value.as_str().unwrap()))
            .collect();
        let fields: Vec<&[u8]> = fields.iter().map(Vec::as_slice).collect();
        assert_eq!(
            frame_preimage(&domain, &fields).unwrap(),
            hex_bytes(case["preimage_hex"].as_str().unwrap())
        );
        assert_eq!(
            identity_hex(&domain, &fields).unwrap(),
            case["identity"].as_str().unwrap()
        );
    }
    for case in data["sha256"].as_array().unwrap() {
        assert_eq!(
            format!(
                "{:x}",
                Sha256::digest(hex_bytes(case["message_hex"].as_str().unwrap()))
            ),
            case["digest"].as_str().unwrap()
        );
    }
    assert_eq!(u16_be(0).unwrap(), [0, 0]);
    assert_eq!(u16_be(65_535).unwrap(), [0xff, 0xff]);
    assert!(u16_be(65_536).is_err());
    assert_eq!(u32_be(4_294_967_295).unwrap(), [0xff; 4]);
    assert!(u32_be(4_294_967_296).is_err());
    assert!(frame_preimage(b"bad", &[]).is_err());
    assert!(frame_preimage(b"bad\0domain\0", &[]).is_err());
    assert!(frame_preimage(b"bad\xff\0", &[]).is_err());
    let too_many = vec![&b""[..]; 65_536];
    assert!(frame_preimage(b"test:a\0", &too_many).is_err());
    assert_eq!(fixture("identity-v0.json"), original);
}

#[test]
fn manifest_fixture() {
    validate_canonical_manifest(&fixture("source-v0.json")).unwrap();
    let original = fixture("manifest-v0.json");
    let data: Value = serde_json::from_slice(&original).unwrap();
    for case in data["cases"].as_array().unwrap() {
        let source = hex_bytes(case["source_hex"].as_str().unwrap());
        let expected = hex_bytes(case["canonical_hex"].as_str().unwrap());
        match case["outcome"].as_str().unwrap() {
            "reject" => assert!(canonicalize_manifest(&source).is_err(), "{}", case["name"]),
            "canonical" => {
                assert_eq!(canonicalize_manifest(&source).unwrap(), expected);
                validate_canonical_manifest(&source).unwrap();
            }
            "noncanonical" => {
                assert_eq!(canonicalize_manifest(&source).unwrap(), expected);
                assert!(validate_canonical_manifest(&source).is_err());
            }
            outcome => panic!("unknown outcome {outcome}"),
        }
    }
    validate_canonical_manifest(&fixture("identity-v0.json")).unwrap();
    validate_canonical_manifest(&fixture("chess-v0.json")).unwrap();
    validate_canonical_manifest(&original).unwrap();
    assert_eq!(fixture("manifest-v0.json"), original);
}

#[test]
fn source_report_is_canonical() {
    validate_canonical_manifest(&fs::read(root().join("reports/source-doctor.json")).unwrap())
        .unwrap();
}

#[test]
fn manifest_generated_boundaries_and_ordering() {
    let depth_32 = format!("{}{}{}\n", "{\"a\":".repeat(31), "{}", "}".repeat(31));
    let depth_33 = format!("{}{}{}\n", "{\"a\":".repeat(32), "{}", "}".repeat(32));
    validate_canonical_manifest(depth_32.as_bytes()).unwrap();
    assert!(canonicalize_manifest(depth_33.as_bytes()).is_err());

    let content = "a".repeat(MAX_BYTES - 9);
    let exact = format!("{{\"s\":\"{content}\"}}\n").into_bytes();
    assert_eq!(exact.len(), MAX_BYTES);
    validate_canonical_manifest(&exact).unwrap();
    let mut oversized = exact.clone();
    oversized.push(b'\n');
    assert!(canonicalize_manifest(&oversized).is_err());

    let mut first = BTreeMap::new();
    first.insert("b".into(), ManifestValue::U64(1));
    first.insert("a".into(), ManifestValue::U64(2));
    assert_eq!(
        serialize_manifest(&ManifestValue::Object(first)).unwrap(),
        b"{\"a\":2,\"b\":1}\n"
    );
    let value = parse_manifest(b"{\"a\":[true,0,\"x\"],\"b\":{}}\n").unwrap();
    assert_eq!(
        serialize_manifest(&value).unwrap(),
        b"{\"a\":[true,0,\"x\"],\"b\":{}}\n"
    );

    let at_limit = ManifestValue::Object(BTreeMap::from([(
        "s".into(),
        ManifestValue::String(content),
    )]));
    assert_eq!(serialize_manifest(&at_limit).unwrap().len(), MAX_BYTES);
    let over_limit = ManifestValue::Object(BTreeMap::from([(
        "s".into(),
        ManifestValue::String("a".repeat(MAX_BYTES - 8)),
    )]));
    assert!(serialize_manifest(&over_limit).is_err());
}
