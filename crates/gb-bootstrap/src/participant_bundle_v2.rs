//! Revised participant preimages from fresh Rust recovery and owned observations.
//! No Python producer, saved answer, route builder or recipient source fallback.
use crate::damage_oracle_v2::FullOracleV2;
use crate::preflight_v2::PreflightV2;
use crate::recovery_provenance_v2::RecoveryProvenanceV2;
use gb_content::RecordPayload;
use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

const PROFILE: &str = "eh72-hier-r5-r2-r1-lzss-crc32c-v1";
const OWNER: &[u8] = include_bytes!("../../../spec/gate8-policy-v2.toml");
const JSON_MAX: usize = 1_048_576;
const FILE_MAX: usize = 4_194_306;
const TOTAL_MAX: usize = 67_108_864;
pub type BundleFilesV2 = BTreeMap<String, Vec<u8>>;
type Object = BTreeMap<String, V>;
type Result<T> = std::result::Result<T, BundleErrorV2>;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BundleErrorV2 {
    Input,
    Source,
    Bound,
    Content,
    Namespace,
    Chess,
    Convergence,
    Manifest,
}
impl std::fmt::Display for BundleErrorV2 {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "participant-bundle-v2: {self:?}")
    }
}
impl std::error::Error for BundleErrorV2 {}

fn need(ok: bool, error: BundleErrorV2) -> Result<()> {
    if ok { Ok(()) } else { Err(error) }
}
fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn hex(raw: &[u8]) -> String {
    raw.iter().map(|b| format!("{b:02x}")).collect()
}
fn s(v: &str) -> V {
    V::String(v.into())
}
fn n(v: usize) -> V {
    V::U64(v as u64)
}
fn obj(rows: impl IntoIterator<Item = (&'static str, V)>) -> V {
    V::Object(rows.into_iter().map(|(k, v)| (k.into(), v)).collect())
}
fn object(v: &V) -> Result<&Object> {
    match v {
        V::Object(x) => Ok(x),
        _ => Err(BundleErrorV2::Manifest),
    }
}
fn array(v: &V) -> Result<&[V]> {
    match v {
        V::Array(x) => Ok(x),
        _ => Err(BundleErrorV2::Manifest),
    }
}
fn string(v: &V) -> Result<&str> {
    match v {
        V::String(x) => Ok(x),
        _ => Err(BundleErrorV2::Manifest),
    }
}
fn field<'a>(v: &'a Object, k: &str) -> Result<&'a V> {
    v.get(k).ok_or(BundleErrorV2::Manifest)
}
fn parse(raw: &[u8]) -> Result<V> {
    need(
        !raw.is_empty() && raw.len() <= JSON_MAX,
        BundleErrorV2::Bound,
    )?;
    validate_canonical_manifest(raw).map_err(|_| BundleErrorV2::Manifest)
}
fn encode(v: &V) -> Result<Vec<u8>> {
    serialize_manifest(v).map_err(|_| BundleErrorV2::Manifest)
}
fn digest(v: &str) -> bool {
    v.len() == 64
        && v.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn path(v: &str) -> bool {
    !v.is_empty()
        && v.len() <= 255
        && v.bytes().all(|b| (32..=126).contains(&b))
        && !v.contains('\\')
        && v.split('/').all(|p| !matches!(p, "" | "." | ".."))
}
fn policy() -> Result<toml::Table> {
    need(OWNER.len() <= 65536, BundleErrorV2::Bound)?;
    let p: toml::Table = std::str::from_utf8(OWNER)
        .map_err(|_| BundleErrorV2::Source)?
        .parse()
        .map_err(|_| BundleErrorV2::Source)?;
    need(
        p.get("schema").and_then(toml::Value::as_str) == Some("golden-board.m2-gate8-policy/v2")
            && p.get("candidate_id").and_then(toml::Value::as_str) == Some(PROFILE),
        BundleErrorV2::Source,
    )?;
    Ok(p)
}
fn section<'a>(p: &'a toml::Table, name: &str) -> Result<&'a toml::Table> {
    p.get(name)
        .and_then(toml::Value::as_table)
        .ok_or(BundleErrorV2::Source)
}
fn strings<'a>(p: &'a toml::Table, name: &str) -> Result<Vec<&'a str>> {
    p.get(name)
        .and_then(toml::Value::as_array)
        .ok_or(BundleErrorV2::Source)?
        .iter()
        .map(|v| v.as_str().ok_or(BundleErrorV2::Source))
        .collect()
}
fn bundle_name(id: &str) -> Result<&'static str> {
    match id {
        "technical-v2" => Ok("technical_bundle"),
        "learner-v2" => Ok("learner_bundle"),
        _ => Err(BundleErrorV2::Input),
    }
}
fn role_paths(p: &toml::Table) -> Result<Vec<(String, String)>> {
    let mut out = Vec::new();
    for prefix in ["participant", "owner"] {
        let roles = strings(p, &format!("{prefix}_roles"))?;
        let paths = strings(p, &format!("{prefix}_paths"))?;
        need(roles.len() == paths.len(), BundleErrorV2::Source)?;
        for (role, name) in roles.into_iter().zip(paths) {
            need(
                path(name) && !out.iter().any(|(r, n)| r == role || n == name),
                BundleErrorV2::Source,
            )?;
            out.push((role.to_owned(), name.to_owned()));
        }
    }
    Ok(out)
}
fn files_bound(files: &BundleFilesV2, p: &toml::Table) -> Result<()> {
    let expected = role_paths(p)?;
    need(
        files.len() == expected.len() && files.len() <= 256,
        BundleErrorV2::Input,
    )?;
    let mut total = 0usize;
    for (_, path) in expected {
        let raw = files.get(&path).ok_or(BundleErrorV2::Input)?;
        need(
            !raw.is_empty() && raw.len() <= FILE_MAX,
            BundleErrorV2::Bound,
        )?;
        total = total.checked_add(raw.len()).ok_or(BundleErrorV2::Bound)?;
        need(total <= TOTAL_MAX, BundleErrorV2::Bound)?;
    }
    Ok(())
}

/// Existing selectors, interpreted exclusively in the supplied checked stream.
pub struct TechnicalQueryV2 {
    pub request: Vec<u8>,
    pub expected: Vec<u8>,
    pub position: [u8; 67],
}
pub fn technical_content_query_v2(raw: &[u8]) -> Result<TechnicalQueryV2> {
    need(
        !raw.is_empty() && raw.len() <= JSON_MAX,
        BundleErrorV2::Bound,
    )?;
    let projection = gb_content::stream_validation(raw).map_err(|_| BundleErrorV2::Content)?;
    let mut cursor = 4usize;
    let mut record12 = None;
    for record in projection.records() {
        let header = raw.get(cursor..cursor + 8).ok_or(BundleErrorV2::Content)?;
        let size = u32::from_be_bytes(header[4..8].try_into().unwrap()) as usize;
        let end = cursor
            .checked_add(8)
            .and_then(|n| n.checked_add(size))
            .ok_or(BundleErrorV2::Bound)?;
        let frame = raw.get(cursor..end).ok_or(BundleErrorV2::Content)?;
        if record.record_id() == 12 {
            record12 = Some(frame);
        }
        cursor = end;
    }
    need(cursor == raw.len(), BundleErrorV2::Content)?;
    let bindings = projection
        .records()
        .iter()
        .filter_map(|r| match r.payload() {
            RecordPayload::SemanticBinding {
                binding_class: 1,
                namespace_id: 2,
                semantic_code: 1,
                ..
            } => Some(r.record_id()),
            _ => None,
        })
        .collect::<Vec<_>>();
    need(bindings.len() == 1, BundleErrorV2::Namespace)?;
    let games = projection
        .records()
        .iter()
        .filter_map(|r| match r.payload() {
            RecordPayload::OpaqueData {
                data_binding_ref,
                data,
            } if *data_binding_ref == bindings[0] => Some(data),
            _ => None,
        })
        .collect::<Vec<_>>();
    need(games.len() == 1, BundleErrorV2::Namespace)?;
    let game = games[0]
        .iter()
        .map(|v| u8::try_from(*v).map_err(|_| BundleErrorV2::Content))
        .collect::<Result<Vec<_>>>()?;
    need(game.len() >= 5, BundleErrorV2::Content)?;
    let count = usize::from(u16::from_be_bytes(game[..2].try_into().unwrap()));
    need(
        (1..=4096).contains(&count) && game.len() == 3 + 2 * count,
        BundleErrorV2::Content,
    )?;
    let moves = game[2..game.len() - 1]
        .chunks_exact(2)
        .map(|b| gb_chess::decode_move(b).map_err(|_| BundleErrorV2::Chess))
        .collect::<Result<Vec<_>>>()?;
    let score = gb_chess::Score::from_code(*game.last().unwrap()).ok_or(BundleErrorV2::Chess)?;
    gb_chess::validate_source_record(&moves, score).map_err(|_| BundleErrorV2::Chess)?;
    let position = gb_chess::encode_position(
        gb_chess::replay_from_start(&moves[..1])
            .map_err(|_| BundleErrorV2::Chess)?
            .position(),
    );
    let request = encode(&obj([
        ("schema", s("golden-board.m2-technical-content-query/v0")),
        ("generic_record", obj([("record_id", n(12))])),
        (
            "chess_transition",
            obj([("game_ordinal", n(0)), ("ply_ordinal", n(0))]),
        ),
    ]))?;
    let expected = encode(&obj([
        (
            "schema",
            s("golden-board.m2-technical-content-query-result/v0"),
        ),
        (
            "generic_record",
            obj([
                ("record_id", n(12)),
                (
                    "canonical_record_sha256",
                    s(&hash(record12.ok_or(BundleErrorV2::Namespace)?)),
                ),
            ]),
        ),
        (
            "chess_transition",
            obj([
                ("game_ordinal", n(0)),
                ("ply_ordinal", n(0)),
                ("move_hex", s(&hex(&game[2..4]))),
                (
                    "resulting_position_identity",
                    s(
                        &gb_foundation::identity_hex(b"golden-board:position:v0\0", &[&position])
                            .map_err(|_| BundleErrorV2::Chess)?,
                    ),
                ),
            ]),
        ),
    ]))?;
    Ok(TechnicalQueryV2 {
        request,
        expected,
        position,
    })
}

/// Literal source files only. These are copied, never treated as instructions.
pub fn technical_literal_sources_v2() -> BundleFilesV2 {
    [
        (
            "clean-instructions-v2.txt",
            include_bytes!("../../../studies/m2/templates/technical/clean-instructions-v2.txt")
                .as_slice(),
        ),
        (
            "neutral-opening-prompt.md",
            include_bytes!("../../../studies/m2/templates/technical/neutral-opening-prompt.md")
                .as_slice(),
        ),
        (
            "allowed-tools.md",
            include_bytes!("../../../studies/m2/templates/technical/allowed-tools.md").as_slice(),
        ),
        (
            "storage-v2.txt",
            include_bytes!("../../../studies/m2/templates/technical/storage-v2.txt").as_slice(),
        ),
        (
            "adapter-instructions-v2.txt",
            include_bytes!("../../../studies/m2/templates/technical/adapter-instructions-v2.txt")
                .as_slice(),
        ),
        (
            "channel-formats.md",
            include_bytes!("../../../studies/m2/templates/technical/channel-formats.md").as_slice(),
        ),
        (
            "channel-mechanics-fixtures.json",
            include_bytes!(
                "../../../studies/m2/templates/technical/channel-mechanics-fixtures.json"
            )
            .as_slice(),
        ),
        (
            "heldout-instructions-v2.txt",
            include_bytes!("../../../studies/m2/templates/technical/heldout-instructions-v2.txt")
                .as_slice(),
        ),
        (
            "final-account-question.md",
            include_bytes!("../../../studies/m2/templates/technical/final-account-question.md")
                .as_slice(),
        ),
        (
            "export-format.md",
            include_bytes!("../../../studies/m2/templates/technical/export-format.md").as_slice(),
        ),
        (
            "owner-instructions-v2.txt",
            include_bytes!("../../../studies/m2/templates/technical/owner-instructions-v2.txt")
                .as_slice(),
        ),
    ]
    .into_iter()
    .map(|(name, raw)| {
        (
            format!("studies/m2/templates/technical/{name}"),
            raw.to_vec(),
        )
    })
    .collect()
}

pub fn build_technical_files_v2(
    core: &PreflightV2,
    literals: &BundleFilesV2,
) -> Result<BundleFilesV2> {
    let policy = policy()?;
    let table = section(&policy, "technical_bundle")?;
    let literal_paths = section(table, "literal_sources")?;
    need(literals.len() == literal_paths.len(), BundleErrorV2::Source)?;
    let roles = role_paths(table)?.into_iter().collect::<BTreeMap<_, _>>();
    let mut files = BTreeMap::new();
    for (role, source) in literal_paths {
        let source = source.as_str().ok_or(BundleErrorV2::Source)?;
        let raw = literals.get(source).ok_or(BundleErrorV2::Source)?;
        need(
            !raw.is_empty() && raw.len() <= JSON_MAX,
            BundleErrorV2::Bound,
        )?;
        files.insert(
            roles.get(role).ok_or(BundleErrorV2::Source)?.clone(),
            raw.clone(),
        );
    }
    let carrier = core.document("carrier.bin").ok_or(BundleErrorV2::Input)?;
    need(carrier.len() <= 524292, BundleErrorV2::Bound)?;
    files.insert(roles["artifact"].clone(), carrier.to_vec());
    let clean = core
        .document("decoder-result.json")
        .ok_or(BundleErrorV2::Input)?;
    need(
        clean == core.recovery().decoder_result(),
        BundleErrorV2::Convergence,
    )?;
    files.insert(roles["clean-expected"].clone(), clean.to_vec());
    let oracle = FullOracleV2::new(core.corpus()).map_err(|_| BundleErrorV2::Source)?;
    let mut channels = Vec::new();
    for (letter, family, ordinal) in [
        ('a', "D3", 0),
        ('b', "D2", 0),
        ('c', "D4", 0),
        ('d', "D7", 11),
    ] {
        let case = core
            .corpus()
            .case(family, ordinal)
            .map_err(|_| BundleErrorV2::Source)?;
        let expected = oracle
            .project(family, ordinal, case.bytes())
            .map_err(|_| BundleErrorV2::Source)?;
        let actual = crate::damage_v2::decode_observation_v2(case.channel(), case.bytes());
        let (result, _) = crate::damage_v2::render_decoder_result_v2(case.channel(), &actual)
            .map_err(|_| BundleErrorV2::Convergence)?;
        let resources =
            crate::damage_v2::render_resources_v2(case.channel(), case.bytes(), &actual)
                .map_err(|_| BundleErrorV2::Convergence)?;
        need(
            result == expected.result_bytes()
                && resources == expected.resource_bytes()
                && expected.semantic().wrong_accepts() == 0,
            BundleErrorV2::Convergence,
        )?;
        files.insert(
            roles[&format!("observation-{letter}")].clone(),
            case.bytes().to_vec(),
        );
        files.insert(roles[&format!("{letter}-expected")].clone(), result);
        channels.push(obj([
            ("file", s(&format!("observation-{letter}.bin"))),
            ("channel", s(case.channel())),
        ]));
    }
    files.insert(
        roles["channel-map"].clone(),
        encode(&obj([("observations", V::Array(channels))]))?,
    );
    let query = technical_content_query_v2(core.recovery().all_stream())?;
    files.insert(roles["content-query"].clone(), query.request);
    files.insert(roles["query-expected"].clone(), query.expected);
    files.insert(roles["query-position"].clone(), query.position.to_vec());
    files_bound(&files, table)?;
    Ok(files)
}

fn source_rows(raw: &[u8]) -> Result<BTreeMap<String, (usize, String)>> {
    need(
        !raw.is_empty() && raw.len() <= JSON_MAX,
        BundleErrorV2::Bound,
    )?;
    let admitted =
        crate::source_v2::admit_source_projection_v2(raw).map_err(|_| BundleErrorV2::Source)?;
    let mut out = BTreeMap::new();
    for row in admitted.entries() {
        let length = usize::try_from(row.byte_length()).map_err(|_| BundleErrorV2::Bound)?;
        out.insert(row.path().to_owned(), (length, row.sha256().to_owned()));
    }
    for (name, raw) in [
        ("spec/gate8-policy-v2.toml", OWNER),
        (
            "spec/learner-assessment-v2.md",
            include_bytes!("../../../spec/learner-assessment-v2.md").as_slice(),
        ),
        (
            "studies/m2/learner-assessment-v2.toml",
            include_bytes!("../../../studies/m2/learner-assessment-v2.toml").as_slice(),
        ),
    ] {
        need(
            out.get(name) == Some(&(raw.len(), hash(raw))),
            BundleErrorV2::Source,
        )?;
    }
    Ok(out)
}
fn file_row(role: &str, path: &str, raw: &[u8]) -> V {
    obj([
        ("role_id", s(role)),
        ("path", s(path)),
        ("mode", s("100644")),
        ("bytes", n(raw.len())),
        ("sha256", s(&hash(raw))),
    ])
}

/// Hash actual caller-generated preimages. Fresh semantic generation is owned
/// by build_technical_files_v2 / learner_bundle_v2, not inferred from this hash.
pub fn render_bundle_manifest_v2(
    id: &str,
    files: &BundleFilesV2,
    recovery: &RecoveryProvenanceV2,
    source_projection: &[u8],
) -> Result<Vec<u8>> {
    let policy = policy()?;
    let table = section(&policy, bundle_name(id)?)?;
    files_bound(files, table)?;
    let sources = source_rows(source_projection)?;
    let roles = role_paths(table)?;
    let literal_paths = section(table, "literal_sources")?;
    for (role, source) in literal_paths {
        let source = source.as_str().ok_or(BundleErrorV2::Source)?;
        let path = roles
            .iter()
            .find(|(r, _)| r == role)
            .ok_or(BundleErrorV2::Source)?
            .1
            .as_str();
        let raw = &files[path];
        need(
            sources.get(source) == Some(&(raw.len(), hash(raw))),
            BundleErrorV2::Source,
        )?;
    }
    let stream = if id == "technical-v2" {
        recovery.all_stream()
    } else {
        recovery.required_stream()
    };
    if id == "learner-v2" {
        let path = roles
            .iter()
            .find(|(r, _)| r == "content-stream")
            .ok_or(BundleErrorV2::Source)?
            .1
            .as_str();
        need(files[path] == stream, BundleErrorV2::Content)?;
    }
    let provenance = parse(recovery.canonical_bytes())?;
    let input = object(field(object(&provenance)?, "inputs")?)?;
    if id == "technical-v2" {
        let path_for = |role: &str| {
            roles
                .iter()
                .find(|(r, _)| r == role)
                .map(|(_, p)| p.as_str())
                .ok_or(BundleErrorV2::Source)
        };
        let carrier = &files[path_for("artifact")?];
        let identity = object(field(input, "carrier")?)?;
        need(
            field(identity, "bytes")? == &n(carrier.len())
                && field(identity, "sha256")? == &s(&hash(carrier))
                && files[path_for("clean-expected")?] == recovery.decoder_result(),
            BundleErrorV2::Content,
        )?;
    }
    let candidate = object(field(input, "candidate_manifest")?)?;
    let candidate_sha = string(field(candidate, "sha256")?)?;
    need(digest(candidate_sha), BundleErrorV2::Manifest)?;
    let participant_count = strings(table, "participant_roles")?.len();
    let all_rows = roles
        .iter()
        .map(|(role, path)| file_row(role, path, &files[path]))
        .collect::<Vec<_>>();
    let release_ids = strings(table, "release_ids")?;
    let release_counts = table
        .get("release_counts")
        .and_then(toml::Value::as_array)
        .ok_or(BundleErrorV2::Source)?;
    need(
        release_counts.len() == release_ids.len(),
        BundleErrorV2::Source,
    )?;
    let mut cursor = 0usize;
    let mut releases = Vec::new();
    for (ordinal, (release, count)) in release_ids.iter().zip(release_counts).enumerate() {
        let count = usize::try_from(count.as_integer().ok_or(BundleErrorV2::Source)?)
            .map_err(|_| BundleErrorV2::Bound)?;
        let end = cursor.checked_add(count).ok_or(BundleErrorV2::Bound)?;
        need(count > 0 && end <= participant_count, BundleErrorV2::Source)?;
        releases.push(obj([
            ("ordinal", n(ordinal)),
            ("release_id", s(release)),
            (
                "participant_role_ids",
                V::Array(roles[cursor..end].iter().map(|(r, _)| s(r)).collect()),
            ),
        ]));
        cursor = end;
    }
    need(cursor == participant_count, BundleErrorV2::Source)?;
    encode(&obj([
        ("schema", s("golden-board.m2-participant-bundle/v2")),
        ("bundle_id", s(id)),
        ("profile_id", s(PROFILE)),
        ("source_projection_sha256", s(&hash(source_projection))),
        ("candidate_manifest_sha256", s(candidate_sha)),
        (
            "recovery_provenance_sha256",
            s(&hash(recovery.canonical_bytes())),
        ),
        ("content_stream_sha256", s(&hash(stream))),
        (
            "participant_files",
            V::Array(all_rows[..participant_count].to_vec()),
        ),
        (
            "owner_files",
            V::Array(all_rows[participant_count..].to_vec()),
        ),
        ("release_rows", V::Array(releases)),
    ]))
}

pub struct BundlePreimagesV2 {
    pub canonical_bytes: Vec<u8>,
    pub technical_manifest: Vec<u8>,
    pub learner_manifest: Vec<u8>,
}

/// Complete private producer preimages. No receipt or publication is implied.
pub struct ParticipantBundlesV2 {
    technical_files: BundleFilesV2,
    learner_files: BundleFilesV2,
    preimages: BundlePreimagesV2,
}
impl ParticipantBundlesV2 {
    pub fn technical_files(&self) -> &BundleFilesV2 {
        &self.technical_files
    }
    pub fn learner_files(&self) -> &BundleFilesV2 {
        &self.learner_files
    }
    pub fn preimages(&self) -> &BundlePreimagesV2 {
        &self.preimages
    }
}

pub fn build_participant_bundles_v2(
    core: &PreflightV2,
    technical_sources: &BundleFilesV2,
    learner_sources: crate::learner_bundle_v2::LearnerBundleSourcesV2<'_>,
    source_projection: &[u8],
) -> Result<ParticipantBundlesV2> {
    source_rows(source_projection)?;
    let technical_files = build_technical_files_v2(core, technical_sources)?;
    let learner_files =
        crate::learner_bundle_v2::build_learner_bundle_v2(core.recovery(), learner_sources)
            .map_err(|_| BundleErrorV2::Content)?;
    let preimages = build_bundle_preimages_v2(
        core.recovery(),
        source_projection,
        &technical_files,
        &learner_files,
    )?;
    Ok(ParticipantBundlesV2 {
        technical_files,
        learner_files,
        preimages,
    })
}

pub fn build_bundle_preimages_v2(
    recovery: &RecoveryProvenanceV2,
    source_projection: &[u8],
    technical: &BundleFilesV2,
    learner: &BundleFilesV2,
) -> Result<BundlePreimagesV2> {
    let technical_manifest =
        render_bundle_manifest_v2("technical-v2", technical, recovery, source_projection)?;
    let learner_manifest =
        render_bundle_manifest_v2("learner-v2", learner, recovery, source_projection)?;
    let mut rows = Vec::new();
    for (id, raw) in [
        ("technical-v2", &technical_manifest),
        ("learner-v2", &learner_manifest),
    ] {
        let manifest = parse(raw)?;
        let manifest = object(&manifest)?;
        let files = array(field(manifest, "participant_files")?)?
            .iter()
            .chain(array(field(manifest, "owner_files")?)?)
            .cloned()
            .collect();
        rows.push(obj([
            ("bundle_id", s(id)),
            ("manifest_bytes", n(raw.len())),
            ("manifest_sha256", s(&hash(raw))),
            ("file_rows", V::Array(files)),
        ]));
    }
    let canonical_bytes = encode(&obj([
        ("schema", s("golden-board.m2-bundle-preimages/v2")),
        ("profile_id", s(PROFILE)),
        ("source_projection_sha256", s(&hash(source_projection))),
        ("bundle_rows", V::Array(rows)),
    ]))?;
    Ok(BundlePreimagesV2 {
        canonical_bytes,
        technical_manifest,
        learner_manifest,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn source_value() -> V {
        let inputs = [
            ("spec/gate8-policy-v2.toml", OWNER),
            (
                "spec/learner-assessment-v2.md",
                include_bytes!("../../../spec/learner-assessment-v2.md").as_slice(),
            ),
            (
                "studies/m2/learner-assessment-v2.toml",
                include_bytes!("../../../studies/m2/learner-assessment-v2.toml").as_slice(),
            ),
        ];
        obj([
            ("schema", s("m2-evidence-source-v2")),
            ("roadmap_normative_sha256", s(&"0".repeat(64))),
            (
                "entries",
                V::Array(
                    inputs
                        .into_iter()
                        .map(|(path, raw)| {
                            obj([
                                ("path", s(path)),
                                ("mode", s("100644")),
                                ("byte_length", n(raw.len())),
                                ("sha256", s(&hash(raw))),
                            ])
                        })
                        .collect(),
                ),
            ),
        ])
    }

    #[test]
    fn source_projection_requires_typed_closed_rows_and_owned_policy_preimage() {
        let good = source_value();
        assert_eq!(source_rows(&encode(&good).unwrap()).unwrap().len(), 3);
        assert!(source_rows(b"source").is_err());
        for (key, value) in [
            ("byte_length", V::Bool(true)),
            ("byte_length", n(OWNER.len() + 1)),
            ("sha256", s(&"0".repeat(64))),
            ("mode", s("100600")),
            ("path", s("../spec/gate8-policy-v2.toml")),
            ("extra", n(1)),
        ] {
            let mut changed = good.clone();
            let V::Object(root) = &mut changed else {
                unreachable!()
            };
            let V::Array(rows) = root.get_mut("entries").unwrap() else {
                unreachable!()
            };
            let V::Object(row) = &mut rows[0] else {
                unreachable!()
            };
            row.insert(key.into(), value);
            assert!(source_rows(&encode(&changed).unwrap()).is_err(), "{key}");
        }
        let mut duplicate = good.clone();
        let V::Object(root) = &mut duplicate else {
            unreachable!()
        };
        let V::Array(rows) = root.get_mut("entries").unwrap() else {
            unreachable!()
        };
        rows.push(rows[0].clone());
        assert!(source_rows(&encode(&duplicate).unwrap()).is_err());
        assert!(source_rows(&vec![b' '; JSON_MAX + 1]).is_err());
    }

    #[test]
    fn assessment_owner_and_intent_preimages_are_required() {
        for index in [1, 2] {
            let mut changed = source_value();
            let V::Object(root) = &mut changed else {
                unreachable!()
            };
            let V::Array(rows) = root.get_mut("entries").unwrap() else {
                unreachable!()
            };
            rows.remove(index);
            assert!(source_rows(&encode(&changed).unwrap()).is_err());
        }
    }

    #[test]
    fn raw_bundle_inventory_is_exact_and_individually_bounded() {
        let owner = policy().unwrap();
        for bundle in ["technical_bundle", "learner_bundle"] {
            let table = section(&owner, bundle).unwrap();
            let mut files = role_paths(table)
                .unwrap()
                .into_iter()
                .map(|(_, path)| (path, vec![1]))
                .collect::<BundleFilesV2>();
            files_bound(&files, table).unwrap();
            let first = files.keys().next().unwrap().clone();
            files.remove(&first);
            assert!(files_bound(&files, table).is_err());
            files.insert("owner/unowned.json".into(), vec![1]);
            assert!(files_bound(&files, table).is_err());
            files.remove("owner/unowned.json");
            files.insert(first.clone(), vec![]);
            assert!(files_bound(&files, table).is_err());
            files.insert(first, vec![0; FILE_MAX + 1]);
            assert!(files_bound(&files, table).is_err());
        }
        assert!(bundle_name("technical-v0").is_err());
    }
}
