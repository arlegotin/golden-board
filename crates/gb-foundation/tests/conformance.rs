use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use gb_foundation::{
    ManifestValue, canonicalize_manifest, frame_preimage, identity_hex, parse_manifest,
    serialize_manifest, u16_be, u32_be, validate_canonical_manifest,
};
use serde_json::Value;
use sha2::{Digest, Sha256};

const MAX_BYTES: usize = 1_048_576;

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

#[test]
fn registry_hashes_and_paths_match() {
    let registry: toml::Value =
        toml::from_str(&fs::read_to_string(root().join("conformance/registry.toml")).unwrap())
            .unwrap();
    for suite in registry["suite"].as_array().unwrap() {
        let path = root().join(suite["path"].as_str().unwrap());
        assert!(path.is_file());
        assert_eq!(
            format!("{:x}", Sha256::digest(fs::read(path).unwrap())),
            suite["sha256"].as_str().unwrap()
        );
        assert_eq!(
            suite["consumers"].as_array().unwrap(),
            &[
                toml::Value::String("python".into()),
                toml::Value::String("rust".into())
            ]
        );
    }
}

#[test]
fn identity_fixture_and_boundaries() {
    let original = fixture("identity-v0.json");
    let data: Value = serde_json::from_slice(&original).unwrap();
    for case in data["vectors"].as_array().unwrap() {
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
    validate_canonical_manifest(&original).unwrap();
    assert_eq!(fixture("manifest-v0.json"), original);
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
