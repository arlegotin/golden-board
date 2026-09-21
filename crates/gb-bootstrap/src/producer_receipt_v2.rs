//! Pure receipt projections after fresh candidate and bundle construction.
//! Admission compares bindings; it never acquires an environment, executes a
//! producer, validates a filesystem freeze, or infers semantic pass from hashes.
use crate::complete_candidate_v2::CompleteCandidateV2;
use crate::participant_bundle_v2::ParticipantBundlesV2;
use crate::source_v2::{SourceProjectionV2, safe_path};
use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

const OWNER: &str = include_str!("../../../spec/gate8-policy-v2.toml");
const OLD_ENVIRONMENT_OWNER: &str = include_str!("../../../spec/gate8-policy-v0.toml");
const PROFILE: &str = "eh72-hier-r5-r2-r1-lzss-crc32c-v1";
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ReceiptErrorV2 {
    Manifest,
    Binding,
    Identity,
    Files,
    Bounds,
    Prerequisite,
    Owner,
}
impl std::fmt::Display for ReceiptErrorV2 {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "producer-receipt-v2: {self:?}")
    }
}
impl std::error::Error for ReceiptErrorV2 {}
pub type Result<T> = std::result::Result<T, ReceiptErrorV2>;
fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn digest(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn obj(pairs: impl IntoIterator<Item = (&'static str, V)>) -> V {
    V::Object(pairs.into_iter().map(|(k, v)| (k.into(), v)).collect())
}
fn s(v: &str) -> V {
    V::String(v.into())
}
fn parse(raw: &[u8]) -> Result<V> {
    if raw.len() > 1_048_576 {
        return Err(ReceiptErrorV2::Bounds);
    }
    validate_canonical_manifest(raw).map_err(|_| ReceiptErrorV2::Manifest)
}
fn object(v: &V) -> Result<&BTreeMap<String, V>> {
    if let V::Object(v) = v {
        Ok(v)
    } else {
        Err(ReceiptErrorV2::Manifest)
    }
}
fn closed<'a>(v: &'a V, keys: &str) -> Result<&'a BTreeMap<String, V>> {
    let v = object(v)?;
    if v.len() != keys.split(',').count() || keys.split(',').any(|k| !v.contains_key(k)) {
        return Err(ReceiptErrorV2::Manifest);
    }
    Ok(v)
}
fn string(v: &V) -> Result<&str> {
    if let V::String(v) = v {
        Ok(v)
    } else {
        Err(ReceiptErrorV2::Manifest)
    }
}
fn number(v: &V) -> Result<u64> {
    if let V::U64(v) = v {
        Ok(*v)
    } else {
        Err(ReceiptErrorV2::Manifest)
    }
}
fn encode(v: &V) -> Result<Vec<u8>> {
    let raw = serialize_manifest(v).map_err(|_| ReceiptErrorV2::Manifest)?;
    if raw.len() > 1_048_576 {
        return Err(ReceiptErrorV2::Bounds);
    }
    Ok(raw)
}
fn policy() -> Result<toml::Table> {
    if OWNER.len() > 65_536 {
        return Err(ReceiptErrorV2::Owner);
    }
    OWNER.parse().map_err(|_| ReceiptErrorV2::Owner)
}
fn fixed_paths() -> Result<Vec<String>> {
    policy()?
        .get("candidate_files")
        .and_then(toml::Value::as_table)
        .and_then(|v| v.get("fixed"))
        .and_then(toml::Value::as_array)
        .ok_or(ReceiptErrorV2::Owner)?
        .iter()
        .map(|v| v.as_str().map(str::to_owned).ok_or(ReceiptErrorV2::Owner))
        .collect()
}
fn linux_binding() -> Result<(String, String, String)> {
    let old: toml::Table = OLD_ENVIRONMENT_OWNER
        .parse()
        .map_err(|_| ReceiptErrorV2::Owner)?;
    let table = old
        .get("linux_acquisition_receipt")
        .and_then(toml::Value::as_table)
        .ok_or(ReceiptErrorV2::Owner)?;
    let get = |key| {
        table
            .get(key)
            .and_then(toml::Value::as_str)
            .ok_or(ReceiptErrorV2::Owner)
    };
    Ok((
        get("platform")?.into(),
        get("image_id")?.into(),
        get("sha256")?
            .strip_prefix("sha256:")
            .ok_or(ReceiptErrorV2::Owner)?
            .into(),
    ))
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ProducerIdentityV2 {
    producer_id: String,
    executable: V,
    environment: V,
}
impl ProducerIdentityV2 {
    /// Bind independently checked identities. These scalar arguments are not
    /// evidence that an executable ran or that a Linux image was acquired.
    pub fn from_bindings(
        producer_id: &str,
        executable_bytes: u64,
        executable_sha256: &str,
        platform: &str,
        image_id: &str,
        acquisition_sha256: &str,
    ) -> Result<Self> {
        let (kind, implementation) = producer_id
            .split_once('-')
            .ok_or(ReceiptErrorV2::Identity)?;
        if !matches!(kind, "native" | "linux")
            || !matches!(implementation, "python" | "rust")
            || executable_bytes == 0
            || executable_bytes > 536_870_912
            || !digest(executable_sha256)
            || platform.is_empty()
            || platform.len() > 64
            || !platform.bytes().all(|b| (0x20..=0x7e).contains(&b))
        {
            return Err(ReceiptErrorV2::Identity);
        }
        let expected = if kind == "native" {
            (platform.into(), "none".into(), "none".into())
        } else {
            linux_binding()?
        };
        if (platform, image_id, acquisition_sha256)
            != (
                expected.0.as_str(),
                expected.1.as_str(),
                expected.2.as_str(),
            )
        {
            return Err(ReceiptErrorV2::Identity);
        }
        Ok(Self {
            producer_id: producer_id.into(),
            executable: obj([
                ("implementation", s(implementation)),
                ("bytes", V::U64(executable_bytes)),
                ("sha256", s(executable_sha256)),
            ]),
            environment: obj([
                ("kind", s(kind)),
                ("platform", s(platform)),
                ("image_id", s(image_id)),
                ("acquisition_sha256", s(acquisition_sha256)),
            ]),
        })
    }
    pub fn producer_id(&self) -> &str {
        &self.producer_id
    }
    pub fn executable_identity(&self) -> &V {
        &self.executable
    }
    pub fn environment_identity(&self) -> &V {
        &self.environment
    }
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ProducerFileRowV2 {
    path: String,
    bytes: u64,
    sha256: String,
}
impl ProducerFileRowV2 {
    pub fn path(&self) -> &str {
        &self.path
    }
    pub fn byte_length(&self) -> u64 {
        self.bytes
    }
    pub fn sha256(&self) -> &str {
        &self.sha256
    }
    pub fn mode(&self) -> &str {
        "100644"
    }
    fn value(&self) -> V {
        obj([
            ("path", s(&self.path)),
            ("mode", s("100644")),
            ("bytes", V::U64(self.bytes)),
            ("sha256", s(&self.sha256)),
        ])
    }
}
/// Minted only from the completed candidate and immutable freshly generated
/// bundles. It does not replace lifecycle source/executable/filesystem checks.
pub struct ProducerFileTableV2 {
    source_sha256: String,
    rows: Vec<ProducerFileRowV2>,
}
impl ProducerFileTableV2 {
    pub fn rows(&self) -> &[ProducerFileRowV2] {
        &self.rows
    }
    pub fn source_projection_sha256(&self) -> &str {
        &self.source_sha256
    }
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ProducerReceiptV2 {
    raw: Vec<u8>,
    identity: ProducerIdentityV2,
    source_sha256: String,
    rows: Vec<ProducerFileRowV2>,
}
impl ProducerReceiptV2 {
    pub fn canonical_bytes(&self) -> &[u8] {
        &self.raw
    }
    pub fn identity(&self) -> &ProducerIdentityV2 {
        &self.identity
    }
    pub fn source_projection_sha256(&self) -> &str {
        &self.source_sha256
    }
    pub fn file_rows(&self) -> &[ProducerFileRowV2] {
        &self.rows
    }
}
pub fn build_producer_file_table_v2(
    candidate: &CompleteCandidateV2,
    bundles: &ParticipantBundlesV2,
    source: &SourceProjectionV2,
) -> Result<ProducerFileTableV2> {
    if !candidate.passed() {
        return Err(ReceiptErrorV2::Prerequisite);
    }
    let proof = candidate
        .independence_proof()
        .ok_or(ReceiptErrorV2::Prerequisite)?;
    let candidate_row = candidate
        .files()
        .iter()
        .find(|r| r.path() == "candidate-manifest.json")
        .ok_or(ReceiptErrorV2::Files)?;
    let source_sha256 = hash(source.canonical_bytes());
    let recovery_sha256 = hash(proof.recovery_provenance().canonical_bytes());
    let preimages = bundles.preimages();
    let projection = parse(&preimages.canonical_bytes)?;
    let projection = closed(
        &projection,
        "schema,profile_id,source_projection_sha256,bundle_rows",
    )?;
    if string(&projection["schema"])? != "golden-board.m2-bundle-preimages/v2"
        || string(&projection["profile_id"])? != PROFILE
        || string(&projection["source_projection_sha256"])? != source_sha256
    {
        return Err(ReceiptErrorV2::Binding);
    }
    for raw in [&preimages.technical_manifest, &preimages.learner_manifest] {
        let value = parse(raw)?;
        let manifest = object(&value)?;
        for (field, expected) in [
            ("source_projection_sha256", source_sha256.as_str()),
            ("candidate_manifest_sha256", candidate_row.sha256()),
            ("recovery_provenance_sha256", recovery_sha256.as_str()),
        ] {
            if manifest.get(field).and_then(|v| {
                if let V::String(s) = v {
                    Some(s.as_str())
                } else {
                    None
                }
            }) != Some(expected)
            {
                return Err(ReceiptErrorV2::Binding);
            }
        }
    }
    let mut rows = candidate
        .files()
        .iter()
        .map(|r| ProducerFileRowV2 {
            path: r.path().into(),
            bytes: r.bytes(),
            sha256: r.sha256().into(),
        })
        .collect::<Vec<_>>();
    rows.push(ProducerFileRowV2 {
        path: "bundle-preimages.json".into(),
        bytes: preimages.canonical_bytes.len() as u64,
        sha256: hash(&preimages.canonical_bytes),
    });
    rows.sort_by(|a, b| a.path.cmp(&b.path));
    validate_rows(&rows)?;
    Ok(ProducerFileTableV2 {
        source_sha256,
        rows,
    })
}
fn validate_rows(rows: &[ProducerFileRowV2]) -> Result<()> {
    let policy = policy()?;
    let bounds = policy
        .get("bounds")
        .and_then(toml::Value::as_table)
        .ok_or(ReceiptErrorV2::Owner)?;
    let bound = |key| {
        bounds
            .get(key)
            .and_then(toml::Value::as_integer)
            .and_then(|v| u64::try_from(v).ok())
            .ok_or(ReceiptErrorV2::Owner)
    };
    let count = usize::try_from(bound("candidate_files")?).map_err(|_| ReceiptErrorV2::Owner)?;
    let aggregate = bound("candidate_aggregate_bytes")?;
    if rows.is_empty() || rows.len() > count {
        return Err(ReceiptErrorV2::Bounds);
    }
    let fixed = fixed_paths()?.into_iter().collect::<BTreeSet<_>>();
    let mut required = fixed.clone();
    required.extend(
        [
            "resource-limits.json",
            "damage/manifest.json",
            "damage/boundary-kats.json",
        ]
        .map(str::to_owned),
    );
    for family in ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "B0"] {
        required.insert(format!("damage/{family}/manifest.json"));
        required.insert(format!("damage/{family}/000000.json"));
    }
    let mut prior = "";
    let mut total = 0u64;
    for row in rows {
        if !safe_path(&row.path) || row.path.as_str() <= prior || !digest(&row.sha256) {
            return Err(ReceiptErrorV2::Files);
        }
        let owned = if fixed.contains(&row.path)
            || matches!(
                row.path.as_str(),
                "resource-limits.json" | "damage/manifest.json" | "damage/boundary-kats.json"
            ) {
            true
        } else {
            let parts = row.path.split('/').collect::<Vec<_>>();
            parts.len() == 3
                && parts[0] == "damage"
                && matches!(
                    parts[1],
                    "D0" | "D1" | "D2" | "D3" | "D4" | "D5" | "D6" | "D7" | "B0"
                )
                && (parts[2] == "manifest.json"
                    || parts[2].strip_suffix(".json").is_some_and(|n| {
                        n.len() == 6
                            && n.bytes().all(|b| b.is_ascii_digit())
                            && n.parse::<u32>().is_ok_and(|n| n < 4096)
                    }))
        };
        if !owned {
            return Err(ReceiptErrorV2::Files);
        }
        required.remove(&row.path);
        total = total.checked_add(row.bytes).ok_or(ReceiptErrorV2::Bounds)?;
        if total > aggregate {
            return Err(ReceiptErrorV2::Bounds);
        }
        prior = &row.path;
    }
    if !required.is_empty() {
        return Err(ReceiptErrorV2::Files);
    }
    Ok(())
}
fn value(files: &ProducerFileTableV2, identity: &ProducerIdentityV2) -> V {
    obj([
        ("schema", s("golden-board.m2-gate8-producer-receipt/v2")),
        ("profile_id", s(PROFILE)),
        ("producer_id", s(&identity.producer_id)),
        ("source_projection_sha256", s(&files.source_sha256)),
        ("executable_identity", identity.executable.clone()),
        ("environment_identity", identity.environment.clone()),
        (
            "file_rows",
            V::Array(files.rows.iter().map(ProducerFileRowV2::value).collect()),
        ),
    ])
}
/// Rust production supports native-rust and linux-rust only. Filesystem/source
/// freeze and actual executable/environment checks remain outer lifecycle work.
pub fn build_producer_receipt_v2(
    files: &ProducerFileTableV2,
    identity: &ProducerIdentityV2,
) -> Result<ProducerReceiptV2> {
    if !matches!(identity.producer_id.as_str(), "native-rust" | "linux-rust") {
        return Err(ReceiptErrorV2::Identity);
    }
    validate_rows(&files.rows)?;
    Ok(ProducerReceiptV2 {
        raw: encode(&value(files, identity))?,
        identity: identity.clone(),
        source_sha256: files.source_sha256.clone(),
        rows: files.rows.clone(),
    })
}
/// Compare a complete receipt to independently established bindings. All four
/// producer labels may be admitted for comparison; admission executes none.
pub fn admit_producer_receipt_v2(
    raw: &[u8],
    source: &SourceProjectionV2,
    files: &ProducerFileTableV2,
    identity: &ProducerIdentityV2,
) -> Result<ProducerReceiptV2> {
    let v = parse(raw)?;
    let root = closed(
        &v,
        "schema,profile_id,producer_id,source_projection_sha256,executable_identity,environment_identity,file_rows",
    )?;
    if string(&root["schema"])? != "golden-board.m2-gate8-producer-receipt/v2"
        || string(&root["profile_id"])? != PROFILE
        || string(&root["source_projection_sha256"])? != hash(source.canonical_bytes())
        || files.source_sha256 != hash(source.canonical_bytes())
    {
        return Err(ReceiptErrorV2::Binding);
    }
    let exe = closed(&root["executable_identity"], "implementation,bytes,sha256")?;
    let env = closed(
        &root["environment_identity"],
        "kind,platform,image_id,acquisition_sha256",
    )?;
    let actual = ProducerIdentityV2::from_bindings(
        string(&root["producer_id"])?,
        number(&exe["bytes"])?,
        string(&exe["sha256"])?,
        string(&env["platform"])?,
        string(&env["image_id"])?,
        string(&env["acquisition_sha256"])?,
    )?;
    if &actual != identity
        || actual.executable != root["executable_identity"]
        || actual.environment != root["environment_identity"]
    {
        return Err(ReceiptErrorV2::Identity);
    }
    let V::Array(raw_rows) = &root["file_rows"] else {
        return Err(ReceiptErrorV2::Manifest);
    };
    if raw_rows.len() != files.rows.len() {
        return Err(ReceiptErrorV2::Files);
    }
    let mut rows = Vec::with_capacity(raw_rows.len());
    for row in raw_rows {
        let row = closed(row, "path,mode,bytes,sha256")?;
        if string(&row["mode"])? != "100644" {
            return Err(ReceiptErrorV2::Files);
        }
        rows.push(ProducerFileRowV2 {
            path: string(&row["path"])?.into(),
            bytes: number(&row["bytes"])?,
            sha256: string(&row["sha256"])?.into(),
        });
    }
    validate_rows(&rows)?;
    if rows != files.rows {
        return Err(ReceiptErrorV2::Binding);
    }
    Ok(ProducerReceiptV2 {
        raw: raw.to_vec(),
        identity: actual,
        source_sha256: files.source_sha256.clone(),
        rows,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::source_v2::admit_source_projection_v2;
    fn source() -> SourceProjectionV2 {
        admit_source_projection_v2(
            &encode(&obj([
                ("schema", s("m2-evidence-source-v2")),
                ("roadmap_normative_sha256", s(&"0".repeat(64))),
                (
                    "entries",
                    V::Array(vec![obj([
                        ("path", s("spec/gate8-policy-v2.toml")),
                        ("mode", s("100644")),
                        ("byte_length", V::U64(OWNER.len() as u64)),
                        ("sha256", s(&hash(OWNER.as_bytes()))),
                    ])]),
                ),
            ]))
            .unwrap(),
        )
        .unwrap()
    }
    // Grammar fixtures only: production callers cannot mint this private token.
    fn table(source: &SourceProjectionV2) -> ProducerFileTableV2 {
        let mut paths = fixed_paths().unwrap();
        paths.extend(
            [
                "resource-limits.json",
                "damage/manifest.json",
                "damage/boundary-kats.json",
            ]
            .map(str::to_owned),
        );
        for family in ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "B0"] {
            paths.push(format!("damage/{family}/manifest.json"));
            paths.push(format!("damage/{family}/000000.json"));
        }
        paths.sort();
        ProducerFileTableV2 {
            source_sha256: hash(source.canonical_bytes()),
            rows: paths
                .into_iter()
                .map(|path| ProducerFileRowV2 {
                    path,
                    bytes: 1,
                    sha256: hash(b"x"),
                })
                .collect(),
        }
    }
    fn identity() -> ProducerIdentityV2 {
        ProducerIdentityV2::from_bindings(
            "native-rust",
            3,
            &hash(b"bin"),
            "darwin/arm64",
            "none",
            "none",
        )
        .unwrap()
    }
    fn receipt(table: &ProducerFileTableV2, id: &ProducerIdentityV2) -> V {
        obj([
            ("schema", s("golden-board.m2-gate8-producer-receipt/v2")),
            ("profile_id", s(PROFILE)),
            ("producer_id", s(&id.producer_id)),
            ("source_projection_sha256", s(&table.source_sha256)),
            ("executable_identity", id.executable.clone()),
            ("environment_identity", id.environment.clone()),
            (
                "file_rows",
                V::Array(table.rows.iter().map(ProducerFileRowV2::value).collect()),
            ),
        ])
    }
    #[test]
    fn receipt_projection_exactly_binds_the_complete_ordered_table_and_identity() {
        let source = source();
        let table = table(&source);
        let identity = identity();
        let expected = encode(&receipt(&table, &identity)).unwrap();
        let built = build_producer_receipt_v2(&table, &identity).unwrap();
        assert_eq!(built.canonical_bytes(), expected);
        assert_eq!(
            admit_producer_receipt_v2(&expected, &source, &table, &identity).unwrap(),
            built
        );
        for mutate in 0..9 {
            let V::Object(mut value) = receipt(&table, &identity) else {
                unreachable!()
            };
            match mutate {
                0 => {
                    value.insert("source_projection_sha256".into(), s(&"0".repeat(64)));
                }
                1 => {
                    value.insert("producer_id".into(), s("native-python"));
                }
                2 => {
                    value.insert("extra".into(), V::Bool(true));
                }
                3..=7 => {
                    let V::Array(rows) = value.get_mut("file_rows").unwrap() else {
                        unreachable!()
                    };
                    match mutate {
                        3 => {
                            rows.remove(0);
                        }
                        4 => {
                            rows.swap(0, 1);
                        }
                        5 => {
                            rows.push(rows[0].clone());
                        }
                        _ => {
                            let V::Object(row) = &mut rows[0] else {
                                unreachable!()
                            };
                            if mutate == 6 {
                                row.insert("bytes".into(), V::Bool(true));
                            } else {
                                row.insert("mode".into(), s("100755"));
                            }
                        }
                    }
                }
                _ => {
                    let V::Object(env) = value.get_mut("environment_identity").unwrap() else {
                        unreachable!()
                    };
                    env.insert("image_id".into(), s("unexpected"));
                }
            }
            assert!(
                admit_producer_receipt_v2(
                    &encode(&V::Object(value)).unwrap(),
                    &source,
                    &table,
                    &identity
                )
                .is_err(),
                "mutation {mutate}"
            );
        }
    }
    #[test]
    fn native_and_linux_identity_rules_are_exact_and_do_not_acquire_anything() {
        assert!(
            ProducerIdentityV2::from_bindings(
                "native-rust",
                536_870_912,
                &"1".repeat(64),
                "darwin/arm64",
                "none",
                "none"
            )
            .is_ok()
        );
        assert!(
            ProducerIdentityV2::from_bindings(
                "native-rust",
                536_870_913,
                &"1".repeat(64),
                "darwin/arm64",
                "none",
                "none"
            )
            .is_err()
        );
        let (platform, image, acquisition) = linux_binding().unwrap();
        for implementation in ["rust", "python"] {
            assert!(
                ProducerIdentityV2::from_bindings(
                    &format!("linux-{implementation}"),
                    1,
                    &"1".repeat(64),
                    &platform,
                    &image,
                    &acquisition
                )
                .is_ok()
            );
        }
        for (producer, bytes, sha, platform, image, acquisition) in [
            ("native-rust", 0, "1".repeat(64), "darwin", "none", "none"),
            ("native-rust", 1, "A".repeat(64), "darwin", "none", "none"),
            ("native-rust", 1, "1".repeat(64), "", "none", "none"),
            (
                "native-rust",
                1,
                "1".repeat(64),
                "darwin",
                "changed",
                "none",
            ),
            (
                "linux-rust",
                1,
                "1".repeat(64),
                "linux/arm64",
                "none",
                "none",
            ),
            ("native-shell", 1, "1".repeat(64), "darwin", "none", "none"),
        ] {
            assert!(
                ProducerIdentityV2::from_bindings(
                    producer,
                    bytes,
                    &sha,
                    platform,
                    image,
                    acquisition
                )
                .is_err()
            );
        }
    }
    #[test]
    fn all_comparison_identities_require_exact_tables_but_rust_cannot_emit_python_receipts() {
        let source = source();
        let table = table(&source);
        let (linux_platform, image, acquisition) = linux_binding().unwrap();
        for producer in ["native-python", "native-rust", "linux-python", "linux-rust"] {
            let (platform, image, acquisition) = if producer.starts_with("native-") {
                ("darwin/arm64", "none", "none")
            } else {
                (
                    linux_platform.as_str(),
                    image.as_str(),
                    acquisition.as_str(),
                )
            };
            let id = ProducerIdentityV2::from_bindings(
                producer,
                3,
                &hash(b"bin"),
                platform,
                image,
                acquisition,
            )
            .unwrap();
            let raw = encode(&receipt(&table, &id)).unwrap();
            assert!(admit_producer_receipt_v2(&raw, &source, &table, &id).is_ok());
            assert_eq!(
                build_producer_receipt_v2(&table, &id).is_ok(),
                producer.ends_with("-rust")
            );
            let different = ProducerIdentityV2::from_bindings(
                producer,
                4,
                &hash(b"bin2"),
                platform,
                image,
                acquisition,
            )
            .unwrap();
            assert!(admit_producer_receipt_v2(&raw, &source, &table, &different).is_err());
        }
    }
    #[test]
    fn file_grammar_and_checked_aggregate_cannot_weaken_the_expected_table() {
        let source = source();
        let table = table(&source);
        for mutate in 0..7 {
            let mut rows = table.rows.clone();
            match mutate {
                0 => {
                    rows[0].path = "../escape".into();
                }
                1 => {
                    rows[0].path = "unowned.json".into();
                }
                2 => {
                    rows[0].sha256 = "A".repeat(64);
                }
                3 => {
                    rows[0].bytes = u64::MAX;
                }
                4 => {
                    rows.retain(|r| r.path != "damage/D7/manifest.json");
                }
                5 => {
                    rows.retain(|r| r.path != "bundle-preimages.json");
                }
                _ => {
                    rows.push(ProducerFileRowV2 {
                        path: "damage/D7/999999.json".into(),
                        bytes: 1,
                        sha256: hash(b"x"),
                    });
                    rows.sort_by(|a, b| a.path.cmp(&b.path));
                }
            }
            assert!(validate_rows(&rows).is_err(), "mutation {mutate}");
        }
    }
}
