//! Source-only construction of the revised Gates 1–5 preflight core.
//! No accidental damage family is executed and no promotion receipt is issued.
use crate::damage_corpus_v2::DamageCorpusV2;
use crate::recovery_provenance_v2::RecoveryProvenanceV2;
use crate::static_v2::StaticProjectionV2;
use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PreflightError {
    Inputs,
    Bounds,
    Source,
    Recovery,
    Convergence,
    Manifest,
    Resources,
}
pub type Result<T> = std::result::Result<T, PreflightError>;
pub const SOURCE_PATHS: [&str; 15] = [
    "conformance/chess-v0.json",
    "conformance/content-v0.json",
    "reports/game-set-v0.bin",
    "spec/constants-v0.toml",
    "spec/content-v0.md",
    "spec/curriculum-v0.toml",
    "spec/damage-policy-v2.toml",
    "spec/profile-limits-v2.toml",
    "spec/profile-policy-v0.toml",
    "spec/profile-policy-v2.toml",
    "spec/receiver-bounds-v2.md",
    "spec/resource-accounting-v2.md",
    "spec/route-data-v0.json",
    "studies/m2/slice-v0.json",
    "studies/m2/slice-v1.json",
];
pub const CORE_PATHS: [&str; 22] = [
    "candidate-manifest.json",
    "capacity-ledger.json",
    "carrier.bin",
    "decoder-result.json",
    "density-ledger.json",
    "first-use.json",
    "geometry-search.json",
    "grammar-state-manifest.json",
    "knowledge-use.json",
    "known-answer-manifest.json",
    "m2-all.content-v0.bin",
    "m2-required.content-v0.bin",
    "ownership-ledger.json",
    "preflight-resource-limits.json",
    "receiver-bounds.json",
    "recovery-provenance.json",
    "route-0.bin",
    "route-1.bin",
    "route-2.bin",
    "route-3.bin",
    "semantic-envelope.json",
    "static-limits.json",
];
const PROFILE: &str = "eh72-hier-r5-r2-r1-lzss-crc32c-v1";
#[derive(Clone)]
pub struct PreflightInputsV2<'a> {
    files: BTreeMap<&'a str, &'a [u8]>,
}
impl<'a> PreflightInputsV2<'a> {
    pub fn new(rows: impl IntoIterator<Item = (&'a str, &'a [u8])>) -> Result<Self> {
        let mut files = BTreeMap::new();
        let mut total = 0usize;
        for (path, raw) in rows {
            if files.len() >= 15
                || !SOURCE_PATHS.contains(&path)
                || raw.is_empty()
                || raw.len() > 8_388_608
                || files.insert(path, raw).is_some()
            {
                return Err(PreflightError::Inputs);
            }
            total = total.checked_add(raw.len()).ok_or(PreflightError::Bounds)?;
            if total > 134_217_728 {
                return Err(PreflightError::Bounds);
            }
        }
        if files.len() != 15 {
            return Err(PreflightError::Inputs);
        }
        Ok(Self { files })
    }
    fn raw(&self, path: &str) -> &'a [u8] {
        self.files[path]
    }
    pub fn sources(&self) -> impl Iterator<Item = (&'a str, &'a [u8])> + '_ {
        self.files.iter().map(|(p, b)| (*p, *b))
    }
}
impl Default for PreflightInputsV2<'static> {
    fn default() -> Self {
        Self {
            files: BTreeMap::from([
                (
                    SOURCE_PATHS[0],
                    include_bytes!("../../../conformance/chess-v0.json").as_slice(),
                ),
                (
                    SOURCE_PATHS[1],
                    include_bytes!("../../../conformance/content-v0.json").as_slice(),
                ),
                (
                    SOURCE_PATHS[2],
                    include_bytes!("../../../reports/game-set-v0.bin").as_slice(),
                ),
                (
                    SOURCE_PATHS[3],
                    include_bytes!("../../../spec/constants-v0.toml").as_slice(),
                ),
                (
                    SOURCE_PATHS[4],
                    include_bytes!("../../../spec/content-v0.md").as_slice(),
                ),
                (
                    SOURCE_PATHS[5],
                    include_bytes!("../../../spec/curriculum-v0.toml").as_slice(),
                ),
                (
                    SOURCE_PATHS[6],
                    include_bytes!("../../../spec/damage-policy-v2.toml").as_slice(),
                ),
                (
                    SOURCE_PATHS[7],
                    include_bytes!("../../../spec/profile-limits-v2.toml").as_slice(),
                ),
                (
                    SOURCE_PATHS[8],
                    include_bytes!("../../../spec/profile-policy-v0.toml").as_slice(),
                ),
                (
                    SOURCE_PATHS[9],
                    include_bytes!("../../../spec/profile-policy-v2.toml").as_slice(),
                ),
                (
                    SOURCE_PATHS[10],
                    include_bytes!("../../../spec/receiver-bounds-v2.md").as_slice(),
                ),
                (
                    SOURCE_PATHS[11],
                    include_bytes!("../../../spec/resource-accounting-v2.md").as_slice(),
                ),
                (
                    SOURCE_PATHS[12],
                    include_bytes!("../../../spec/route-data-v0.json").as_slice(),
                ),
                (
                    SOURCE_PATHS[13],
                    include_bytes!("../../../studies/m2/slice-v0.json").as_slice(),
                ),
                (
                    SOURCE_PATHS[14],
                    include_bytes!("../../../studies/m2/slice-v1.json").as_slice(),
                ),
            ]),
        }
    }
}
/// Immutable fresh core and the source context needed by the later full replay.
pub struct PreflightV2 {
    files: BTreeMap<String, Vec<u8>>,
    projection: StaticProjectionV2,
    corpus: DamageCorpusV2,
    recovery: RecoveryProvenanceV2,
    kats: [Vec<u8>; 4],
}
impl PreflightV2 {
    pub fn document(&self, path: &str) -> Option<&[u8]> {
        self.files.get(path).map(Vec::as_slice)
    }
    pub fn documents(&self) -> impl Iterator<Item = (&str, &[u8])> {
        self.files.iter().map(|(p, b)| (p.as_str(), b.as_slice()))
    }
    pub fn static_projection(&self) -> &StaticProjectionV2 {
        &self.projection
    }
    pub fn corpus(&self) -> &DamageCorpusV2 {
        &self.corpus
    }
    pub fn recovery(&self) -> &RecoveryProvenanceV2 {
        &self.recovery
    }
    pub fn boundary_kats(&self) -> &[Vec<u8>; 4] {
        &self.kats
    }
}

type Object = BTreeMap<String, V>;
fn object(v: &V) -> Result<&Object> {
    if let V::Object(v) = v {
        Ok(v)
    } else {
        Err(PreflightError::Manifest)
    }
}
fn array(v: &V) -> Result<&[V]> {
    if let V::Array(v) = v {
        Ok(v)
    } else {
        Err(PreflightError::Manifest)
    }
}
fn number(v: &V) -> Result<u64> {
    if let V::U64(v) = v {
        Ok(*v)
    } else {
        Err(PreflightError::Manifest)
    }
}
fn string(v: &V) -> Result<&str> {
    if let V::String(v) = v {
        Ok(v)
    } else {
        Err(PreflightError::Manifest)
    }
}
fn closed<'a>(v: &'a V, keys: &str) -> Result<&'a Object> {
    let v = object(v)?;
    if v.len() != keys.split(',').count() || keys.split(',').any(|k| !v.contains_key(k)) {
        return Err(PreflightError::Manifest);
    }
    Ok(v)
}
fn o(rows: impl IntoIterator<Item = (&'static str, V)>) -> V {
    V::Object(rows.into_iter().map(|(k, v)| (k.into(), v)).collect())
}
fn s(v: impl Into<String>) -> V {
    V::String(v.into())
}
fn a(v: impl IntoIterator<Item = V>) -> V {
    V::Array(v.into_iter().collect())
}
fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn encode(v: &V) -> Result<Vec<u8>> {
    serialize_manifest(v).map_err(|_| PreflightError::Manifest)
}
fn parse(raw: &[u8]) -> Result<V> {
    validate_canonical_manifest(raw).map_err(|_| PreflightError::Manifest)
}
fn need(ok: bool) -> Result<()> {
    if ok {
        Ok(())
    } else {
        Err(PreflightError::Manifest)
    }
}
fn known_answer(profile: &[u8], recovery: &RecoveryProvenanceV2) -> Result<Vec<u8>> {
    let knowledge = parse(recovery.knowledge_use())?;
    let knowledge = object(&knowledge)?;
    let routes = array(&knowledge["route_rows"])?;
    need(routes.len() == 4)?;
    let mut rows = Vec::new();
    let mut package = None;
    for (sector, route) in routes.iter().enumerate() {
        let route = object(route)?;
        need(route["sector_id"] == V::U64(sector as u64))?;
        if let Some(expected) = &package {
            need(expected == &route["package_sha256"])?;
        } else {
            package = Some(route["package_sha256"].clone());
        }
        let mut records = BTreeMap::new();
        for row in array(&route["record_rows"])? {
            let row = object(row)?;
            let id = number(&row["record_id"])?;
            need(records.insert(id, row).is_none())?;
        }
        let examples = array(&route["example_rows"])?;
        need(examples.len() == 32)?;
        let mut previous = 0;
        for example in examples {
            let ex = closed(
                example,
                "record_id,fact_id,recipe_id,kind,input_bytes,output_bytes,status,success",
            )?;
            let id = number(&ex["record_id"])?;
            need(id > previous)?;
            previous = id;
            let record = records.get(&id).ok_or(PreflightError::Manifest)?;
            let offset = usize::try_from(number(&record["byte_offset"])?)
                .map_err(|_| PreflightError::Bounds)?;
            let length =
                usize::try_from(number(&record["bytes"])?).map_err(|_| PreflightError::Bounds)?;
            let end = offset.checked_add(length).ok_or(PreflightError::Bounds)?;
            let prefixes = recovery.prefixes();
            let frame = prefixes[sector]
                .get(offset..end)
                .ok_or(PreflightError::Bounds)?;
            need(record["sha256"] == s(hash(frame)) && ex["success"] == V::Bool(true))?;
            let mut row = ex.clone();
            row.insert("sector_id".into(), V::U64(sector as u64));
            row.insert("record_sha256".into(), s(hash(frame)));
            rows.push(V::Object(row));
        }
    }
    need(rows.len() == 128)?;
    encode(&o([
        ("schema", s("golden-board.m2-known-answer/v2")),
        ("profile_id", s(PROFILE)),
        (
            "input_sha256",
            o([
                ("profile_policy", s(hash(profile))),
                ("knowledge_use", s(hash(recovery.knowledge_use()))),
                ("first_use", s(hash(recovery.first_use()))),
                ("recovery_provenance", s(hash(recovery.canonical_bytes()))),
            ]),
        ),
        ("package_sha256", package.ok_or(PreflightError::Manifest)?),
        ("example_rows", a(rows)),
        (
            "summary",
            o([
                ("route_count", V::U64(4)),
                ("example_count", V::U64(128)),
                ("result", s("pass")),
            ]),
        ),
    ]))
}
fn receiver(channel: &str, raw: &[u8]) -> Result<(Vec<u8>, Vec<u8>)> {
    let result = crate::damage_v2::decode_observation_v2(channel, raw);
    let result_bytes = crate::damage_v2::render_decoder_result_v2(channel, &result)
        .map_err(|_| PreflightError::Recovery)?
        .0;
    let sidecar = crate::damage_v2::render_resources_v2(channel, raw, &result)
        .map_err(|_| PreflightError::Resources)?;
    Ok((result_bytes, sidecar))
}
fn checked_replay(raw: &[u8], identity: &[u8], result: &[u8], sidecar: &[u8]) -> Result<V> {
    let value = parse(raw)?;
    let row = closed(
        &value,
        "schema,observation,decoder_result,resource_projection,expected_section_states,wrong_accept_count,reauthored_boundary,promise_result",
    )?;
    if row["schema"] != s("golden-board.m2-damage-replay-case/v2")
        || row["observation"] != parse(identity)?
        || encode(&row["decoder_result"])? != result
        || encode(&row["resource_projection"])? != sidecar
    {
        return Err(PreflightError::Convergence);
    }
    // Comparing complete canonical result and sidecar preserves every scalar,
    // hash, diagnostic and kernel row, rather than only a semantic summary.
    Ok(value)
}
fn grammar(
    candidate: &[u8],
    recovery: &RecoveryProvenanceV2,
    kats: &[Vec<u8>; 4],
    boundaries: Vec<V>,
) -> Result<Vec<u8>> {
    let clean = parse(recovery.decoder_result())?;
    let clean = object(&clean)?;
    need(
        clean["artifact_state"] == s("exact")
            && clean["established_profile_id"] == s(PROFILE)
            && clean["m2_required_available"] == V::Bool(true)
            && clean["m2_all_available"] == V::Bool(true),
    )?;
    need(boundaries.len() == 21)?;
    let mut kat_rows = Vec::new();
    let mut pass = true;
    for (raw, id) in kats.iter().zip(crate::boundary_kat_v2::KAT_IDS) {
        let value = parse(raw)?;
        let row = closed(&value, "schema,kat_id,result")?;
        need(
            row["schema"] == s("golden-board.m2-boundary-kat-result/v2") && row["kat_id"] == s(id),
        )?;
        let result = string(&row["result"])?;
        need(matches!(result, "pass" | "fail"))?;
        pass &= result == "pass";
        kat_rows.push(o([
            ("kat_id", s(id)),
            ("result", row["result"].clone()),
            ("bytes", V::U64(raw.len() as u64)),
            ("sha256", s(hash(raw))),
        ]));
    }
    encode(&o([
        ("schema", s("golden-board.m2-grammar-state/v2")),
        ("profile_id", s(PROFILE)),
        (
            "input_sha256",
            o([
                ("candidate_manifest", s(hash(candidate))),
                ("recovery_provenance", s(hash(recovery.canonical_bytes()))),
                ("decoder_result", s(hash(recovery.decoder_result()))),
            ]),
        ),
        (
            "clean_result",
            o([
                ("artifact_state", clean["artifact_state"].clone()),
                (
                    "established_profile_id",
                    clean["established_profile_id"].clone(),
                ),
                (
                    "section_count",
                    V::U64(array(&clean["section_rows"])?.len() as u64),
                ),
                (
                    "required_stream_sha256",
                    clean["m2_required_stream_sha256"].clone(),
                ),
                ("all_stream_sha256", clean["m2_all_stream_sha256"].clone()),
            ]),
        ),
        ("boundary_kats", a(kat_rows)),
        ("boundary_rows", a(boundaries)),
        (
            "summary",
            o([
                ("boundary_case_count", V::U64(21)),
                ("boundary_kat_count", V::U64(4)),
                ("result", s(if pass { "pass" } else { "fail" })),
            ]),
        ),
    ]))
}
/// Build only the closed preflight core. All runtime receiver inputs are channel
/// and observation bytes; the independent source oracle alone sees the corpus.
pub fn build_preflight_v2(inputs: PreflightInputsV2<'_>) -> Result<PreflightV2> {
    // Bounds and their exact source identities are admitted before construction
    // or observation work. Full measured damage maxima are a later postcondition.
    let bound_sources = crate::receiver_bounds_v2::ReceiverBoundSources {
        profile_policy: inputs.raw("spec/profile-policy-v2.toml"),
        profile_limits: inputs.raw("spec/profile-limits-v2.toml"),
        damage_policy: inputs.raw("spec/damage-policy-v2.toml"),
        resource_accounting: inputs.raw("spec/resource-accounting-v2.md"),
        receiver_bounds: inputs.raw("spec/receiver-bounds-v2.md"),
    };
    let bounds = crate::receiver_bounds_v2::derive_receiver_bounds_v2(bound_sources)
        .map_err(|_| PreflightError::Source)?;
    let slice = gb_slice::compile_slice_v1(
        inputs.raw("studies/m2/slice-v1.json"),
        gb_slice::SliceInputs {
            declaration: inputs.raw("studies/m2/slice-v0.json"),
            content_fixture: inputs.raw("conformance/content-v0.json"),
            chess_fixture: inputs.raw("conformance/chess-v0.json"),
            game_set: inputs.raw("reports/game-set-v0.bin"),
            content_spec: inputs.raw("spec/content-v0.md"),
            constants: inputs.raw("spec/constants-v0.toml"),
            curriculum: inputs.raw("spec/curriculum-v0.toml"),
        },
    )
    .map_err(|_| PreflightError::Source)?;
    let carrier = crate::carrier_v2::build_carrier(&slice).map_err(|_| PreflightError::Source)?;
    let projection = crate::static_v2::build_static_projection_v2_with_sources(
        &slice,
        &carrier,
        crate::static_v2::StaticSources {
            inherited_profile_policy: inputs.raw("spec/profile-policy-v0.toml"),
            profile_policy: bound_sources.profile_policy,
            profile_limits: bound_sources.profile_limits,
            damage_policy: bound_sources.damage_policy,
            curriculum: inputs.raw("spec/curriculum-v0.toml"),
        },
    )
    .map_err(|_| PreflightError::Source)?;
    let candidate = projection
        .document("candidate-manifest.json")
        .ok_or(PreflightError::Source)?;
    let recovery = crate::recovery_provenance_v2::build_recovery_provenance_v2(
        crate::recovery_provenance_v2::RecoveryProvenanceInputs {
            carrier: carrier.packed_bytes(),
            candidate_manifest: candidate,
            capacity_ledger: projection
                .document("capacity-ledger.json")
                .ok_or(PreflightError::Source)?,
            ownership_ledger: projection
                .document("ownership-ledger.json")
                .ok_or(PreflightError::Source)?,
            semantic_envelope: projection
                .document("semantic-envelope.json")
                .ok_or(PreflightError::Source)?,
            profile_policy: bound_sources.profile_policy,
            profile_limits: bound_sources.profile_limits,
            damage_policy: bound_sources.damage_policy,
        },
    )
    .map_err(|_| PreflightError::Recovery)?;
    let known = known_answer(bound_sources.profile_policy, &recovery)?;
    let kats: [Vec<u8>; 4] = crate::boundary_kat_v2::boundary_kat_results_v2()
        .map_err(|_| PreflightError::Recovery)?
        .try_into()
        .map_err(|_| PreflightError::Manifest)?;
    let corpus = DamageCorpusV2::new(&slice, &carrier, inputs.raw("spec/route-data-v0.json"))
        .map_err(|_| PreflightError::Source)?;
    let oracle =
        crate::damage_oracle_v2::FullOracleV2::new(&corpus).map_err(|_| PreflightError::Source)?;
    let ids = std::iter::once("clean-observation".to_owned())
        .chain((0..21).map(|i| format!("B0-{i:06}")))
        .collect::<Vec<_>>();
    let refs = ids.iter().map(String::as_str).collect::<Vec<_>>();
    let mut resources = crate::resources_v2::ResourceLimitsAccumulatorV2::new(&refs)
        .map_err(|_| PreflightError::Resources)?;
    let mut identity_hash = Sha256::new();
    let clean_identity = encode(&o([
        ("case_id", s("clean-observation")),
        ("channel", s("OBS_BITS")),
        (
            "observation_bytes",
            V::U64(carrier.packed_bytes().len() as u64),
        ),
        ("observation_sha256", s(hash(carrier.packed_bytes()))),
    ]))?;
    let (clean_result, clean_sidecar) = receiver("OBS_BITS", carrier.packed_bytes())?;
    if clean_result != recovery.decoder_result() {
        return Err(PreflightError::Convergence);
    }
    identity_hash.update(&clean_identity);
    resources
        .push("clean-observation", &clean_sidecar)
        .map_err(|_| PreflightError::Resources)?;
    let mut boundary_rows = Vec::new();
    for ordinal in 0..21 {
        let case = corpus
            .case("B0", ordinal)
            .map_err(|_| PreflightError::Source)?;
        let expected = oracle
            .replay("B0", ordinal, case.bytes())
            .map_err(|_| PreflightError::Convergence)?;
        let (actual, sidecar) = receiver(case.channel(), case.bytes())?;
        let row = checked_replay(&expected, case.identity_bytes(), &actual, &sidecar)?;
        let row = object(&row)?;
        let result = object(&row["decoder_result"])?;
        let identity = parse(case.identity_bytes())?;
        let identity = object(&identity)?;
        let id = format!("B0-{ordinal:06}");
        resources
            .push(&id, &sidecar)
            .map_err(|_| PreflightError::Resources)?;
        identity_hash.update(case.identity_bytes());
        boundary_rows.push(o([
            ("case_id", s(id)),
            ("observation_sha256", identity["observation_sha256"].clone()),
            ("replay_bytes", V::U64(expected.len() as u64)),
            ("replay_sha256", s(hash(&expected))),
            ("decoder_result_sha256", s(hash(&actual))),
            ("resource_projection_sha256", s(hash(&sidecar))),
            ("artifact_state", result["artifact_state"].clone()),
            ("resource", result["resource"].clone()),
            ("convergence", s("pass")),
        ]));
    }
    let limits = resources
        .finish(&format!("{:x}", identity_hash.finalize()))
        .map_err(|_| PreflightError::Resources)?;
    crate::receiver_bounds_v2::admit_resource_limits_v2(&limits, bound_sources)
        .map_err(|_| PreflightError::Resources)?;
    let grammar = grammar(candidate, &recovery, &kats, boundary_rows)?;
    let mut files: BTreeMap<String, Vec<u8>> = projection
        .documents()
        .map(|(p, b)| (p.into(), b.to_vec()))
        .collect();
    files.insert("carrier.bin".into(), carrier.packed_bytes().to_vec());
    for (sector, prefix) in recovery.prefixes().into_iter().enumerate() {
        files.insert(format!("route-{sector}.bin"), prefix.to_vec());
    }
    for (path, raw) in [
        ("recovery-provenance.json", recovery.canonical_bytes()),
        ("knowledge-use.json", recovery.knowledge_use()),
        ("first-use.json", recovery.first_use()),
        ("decoder-result.json", recovery.decoder_result()),
        ("m2-required.content-v0.bin", recovery.required_stream()),
        ("m2-all.content-v0.bin", recovery.all_stream()),
    ] {
        files.insert(path.into(), raw.to_vec());
    }
    for (path, raw) in [
        ("receiver-bounds.json", bounds),
        ("known-answer-manifest.json", known),
        ("grammar-state-manifest.json", grammar),
        ("preflight-resource-limits.json", limits),
    ] {
        files.insert(path.into(), raw);
    }
    need(files.keys().map(String::as_str).collect::<Vec<_>>() == CORE_PATHS)?;
    Ok(PreflightV2 {
        files,
        projection,
        corpus,
        recovery,
        kats,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn convergence_compares_complete_resources_and_diagnostics_not_only_state() {
        let identity = o([("case_id", s("B0-000000"))]);
        let result = o([
            ("artifact_state", s("failure")),
            ("fragment_diagnostics_sha256", s("1".repeat(64))),
        ]);
        let sidecar = o([("primitive_steps", V::U64(12))]);
        let row = o([
            ("schema", s("golden-board.m2-damage-replay-case/v2")),
            ("observation", identity.clone()),
            ("decoder_result", result.clone()),
            ("resource_projection", sidecar.clone()),
            ("expected_section_states", a([])),
            ("wrong_accept_count", V::U64(0)),
            ("reauthored_boundary", V::Bool(true)),
            ("promise_result", s("pass")),
        ]);
        let raw = encode(&row).unwrap();
        let id = encode(&identity).unwrap();
        let result_raw = encode(&result).unwrap();
        let sidecar_raw = encode(&sidecar).unwrap();
        assert!(checked_replay(&raw, &id, &result_raw, &sidecar_raw).is_ok());
        let changed_result = encode(&o([
            ("artifact_state", s("failure")),
            ("fragment_diagnostics_sha256", s("2".repeat(64))),
        ]))
        .unwrap();
        assert_eq!(
            checked_replay(&raw, &id, &changed_result, &sidecar_raw),
            Err(PreflightError::Convergence)
        );
        let changed_resource = encode(&o([("primitive_steps", V::U64(13))])).unwrap();
        assert_eq!(
            checked_replay(&raw, &id, &result_raw, &changed_resource),
            Err(PreflightError::Convergence)
        );
    }
    #[test]
    fn input_domain_is_exact_bounded_and_duplicate_free() {
        let source = PreflightInputsV2::default();
        let rows = source
            .files
            .iter()
            .map(|(p, b)| (*p, *b))
            .collect::<Vec<_>>();
        assert!(PreflightInputsV2::new(rows.clone()).is_ok());
        assert!(PreflightInputsV2::new(rows[..14].iter().copied()).is_err());
        let mut duplicate = rows.clone();
        duplicate.push(rows[0]);
        assert!(PreflightInputsV2::new(duplicate).is_err());
        let mut unknown = rows.clone();
        unknown[0] = ("saved-evidence.json", b"{}");
        assert!(PreflightInputsV2::new(unknown).is_err());
        let empty = rows.into_iter().map(|(p, b)| {
            if p == SOURCE_PATHS[0] {
                (p, b"".as_slice())
            } else {
                (p, b)
            }
        });
        assert!(PreflightInputsV2::new(empty).is_err());
    }
}
