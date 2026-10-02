//! Bounded compact retention of complete, source-bound revised damage replays.
//! This projection does not assert that its caller freshly executed a receiver.
use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

use crate::damage_corpus_v2::DamageCorpusV2;
use crate::resources_v2::{ResourceLimitsAccumulatorV2, source_owners};
use crate::static_v2::StaticProjectionV2;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CompleteDamageError {
    Shape,
    Binding,
    Coverage,
    Bounds,
    Emit,
}
pub type Result<T> = std::result::Result<T, CompleteDamageError>;
const PROFILE: &str = "eh72-hier-r5-r2-r1-lzss-crc32c-v1";
const FAMILIES: [&str; 9] = ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "B0"];
const REQUIRED: [u64; 6] = [1, 2, 3, 16, 17, 18];
const ZERO: &str = "0000000000000000000000000000000000000000000000000000000000000000";
type Object = BTreeMap<String, V>;
fn object(v: &V) -> Result<&Object> {
    if let V::Object(v) = v {
        Ok(v)
    } else {
        Err(CompleteDamageError::Shape)
    }
}
fn array(v: &V) -> Result<&[V]> {
    if let V::Array(v) = v {
        Ok(v)
    } else {
        Err(CompleteDamageError::Shape)
    }
}
fn number(v: &V) -> Result<u64> {
    if let V::U64(v) = v {
        Ok(*v)
    } else {
        Err(CompleteDamageError::Shape)
    }
}
fn string(v: &V) -> Result<&str> {
    if let V::String(v) = v {
        Ok(v)
    } else {
        Err(CompleteDamageError::Shape)
    }
}
fn boolean(v: &V) -> Result<bool> {
    if let V::Bool(v) = v {
        Ok(*v)
    } else {
        Err(CompleteDamageError::Shape)
    }
}
fn closed<'a>(v: &'a V, names: &str) -> Result<&'a Object> {
    let v = object(v)?;
    if v.len() != names.split(',').count() || names.split(',').any(|k| !v.contains_key(k)) {
        return Err(CompleteDamageError::Shape);
    }
    Ok(v)
}
fn o(rows: impl IntoIterator<Item = (&'static str, V)>) -> V {
    V::Object(rows.into_iter().map(|(k, v)| (k.into(), v)).collect())
}
fn s(v: impl Into<String>) -> V {
    V::String(v.into())
}
fn a(values: impl IntoIterator<Item = V>) -> V {
    V::Array(values.into_iter().collect())
}
fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn sha(v: &V) -> Result<&str> {
    let v = string(v)?;
    if v.len() != 64
        || !v
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err(CompleteDamageError::Shape);
    }
    Ok(v)
}
fn encode(v: &V) -> Result<Vec<u8>> {
    serialize_manifest(v).map_err(|_| CompleteDamageError::Bounds)
}
fn parse(raw: &[u8]) -> Result<V> {
    validate_canonical_manifest(raw).map_err(|_| CompleteDamageError::Shape)
}
fn need(v: bool) -> Result<()> {
    if v {
        Ok(())
    } else {
        Err(CompleteDamageError::Binding)
    }
}
fn add(a: u64, b: u64) -> Result<u64> {
    a.checked_add(b).ok_or(CompleteDamageError::Bounds)
}
fn passing(v: &V) -> Result<bool> {
    match string(v)? {
        "pass" => Ok(true),
        "fail" => Ok(false),
        _ => Err(CompleteDamageError::Shape),
    }
}
fn outcome(v: bool) -> V {
    s(if v { "pass" } else { "fail" })
}
fn checked_state(v: &V) -> Result<&str> {
    let v = string(v)?;
    need(matches!(
        v,
        "verified" | "recovered" | "incomplete" | "corrupt" | "ambiguous" | "unknown"
    ))?;
    Ok(v)
}
fn good(v: &V) -> Result<bool> {
    Ok(matches!(checked_state(v)?, "verified" | "recovered"))
}

struct FamilyWriter {
    family: &'static str,
    carrier: String,
    count: u64,
    wrong: u64,
    failed: u64,
    cases: Vec<V>,
    first: u64,
    hash: Sha256,
    shards: Vec<V>,
}
impl FamilyWriter {
    fn new(family: &'static str, carrier: &str) -> Self {
        Self {
            family,
            carrier: carrier.into(),
            count: 0,
            wrong: 0,
            failed: 0,
            cases: vec![],
            first: 0,
            hash: Sha256::new(),
            shards: vec![],
        }
    }
    fn shard(&self, cases: &[V]) -> V {
        o([
            ("schema", s("golden-board.m2-damage-shard/v2")),
            ("profile_id", s(PROFILE)),
            ("family_id", s(self.family)),
            ("first_ordinal", V::U64(self.first)),
            ("case_count", V::U64(cases.len() as u64)),
            ("cases", a(cases.iter().cloned())),
        ])
    }
    fn flush(&mut self, emit: &mut impl FnMut(&str, &[u8]) -> Result<()>) -> Result<()> {
        if self.cases.is_empty() {
            return Ok(());
        }
        let raw = encode(&self.shard(&self.cases))?;
        need(raw.len() <= 524288)?;
        let path = format!("damage/{}/{:06}.json", self.family, self.shards.len());
        emit(&path, &raw)?;
        self.shards.push(o([
            ("path", s(path)),
            ("bytes", V::U64(raw.len() as u64)),
            ("sha256", s(hash(&raw))),
            ("first_ordinal", V::U64(self.first)),
            ("case_count", V::U64(self.cases.len() as u64)),
        ]));
        self.first = add(self.first, self.cases.len() as u64)?;
        self.cases.clear();
        Ok(())
    }
    fn push(&mut self, case: V, emit: &mut impl FnMut(&str, &[u8]) -> Result<()>) -> Result<()> {
        let raw = encode(&case)?;
        if raw.len() > 262144 {
            return Err(CompleteDamageError::Bounds);
        }
        let v = object(&case)?;
        let wrong = number(&v["wrong_accept_count"])?;
        let failed = u64::from(!passing(&v["promise_result"])?);
        if self.cases.len() == 32 {
            self.flush(emit)?;
        }
        self.cases.push(case);
        if encode(&self.shard(&self.cases))?.len() > 524288 {
            let last = self.cases.pop().ok_or(CompleteDamageError::Shape)?;
            self.flush(emit)?;
            self.cases.push(last);
        }
        self.count = add(self.count, 1)?;
        self.wrong = add(self.wrong, wrong)?;
        self.failed = add(self.failed, failed)?;
        self.hash.update(&raw);
        Ok(())
    }
    fn finish(
        mut self,
        kats_pass: bool,
        emit: &mut impl FnMut(&str, &[u8]) -> Result<()>,
    ) -> Result<V> {
        need(self.count > 0)?;
        self.flush(emit)?;
        let passed = self.family == "B0"
            || (self.failed == 0 && self.wrong == 0 && (self.family != "D7" || kats_pass));
        let doc = o([
            ("schema", s("golden-board.m2-damage-family/v2")),
            ("profile_id", s(PROFILE)),
            ("carrier_sha256", s(self.carrier)),
            ("family_id", s(self.family)),
            ("case_count", V::U64(self.count)),
            ("wrong_accept_count", V::U64(self.wrong)),
            ("failed_promise_count", V::U64(self.failed)),
            ("result", outcome(passed)),
            ("cases_sha256", s(format!("{:x}", self.hash.finalize()))),
            ("shards", a(self.shards)),
        ]);
        let path = format!("damage/{}/manifest.json", self.family);
        let raw = encode(&doc)?;
        emit(&path, &raw)?;
        Ok(o([
            ("family_id", s(self.family)),
            ("case_count", V::U64(self.count)),
            ("wrong_accept_count", V::U64(self.wrong)),
            ("result", outcome(passed)),
            ("path", s(path)),
            ("bytes", V::U64(raw.len() as u64)),
            ("sha256", s(hash(&raw))),
        ]))
    }
}

struct Binding {
    candidate: String,
    carrier: String,
    q: u64,
    ids: Vec<u64>,
    section_hashes: BTreeMap<u64, String>,
    counts: [u64; 9],
}
impl Binding {
    fn new(projection: &StaticProjectionV2, corpus: &DamageCorpusV2) -> Result<Self> {
        let candidate_raw = projection
            .document("candidate-manifest.json")
            .ok_or(CompleteDamageError::Binding)?;
        let candidate = parse(candidate_raw)?;
        let candidate = object(&candidate)?;
        let capacity = parse(
            projection
                .document("capacity-ledger.json")
                .ok_or(CompleteDamageError::Binding)?,
        )?;
        let capacity = object(&capacity)?;
        let core = corpus.source_core();
        let carrier = hash(&core.carrier_bytes);
        let q = core.units.len() as u64;
        need(
            q > 0
                && q <= 2389
                && candidate["profile_id"] == s(PROFILE)
                && capacity["carrier_sha256"] == s(&carrier),
        )?;
        need(array(&capacity["unit_rows"])?.len() as u64 == q)?;
        let mut files = BTreeMap::new();
        for row in array(&candidate["files"])? {
            let row = closed(row, "path,bytes,sha256")?;
            need(files.insert(string(&row["path"])?, row).is_none())?;
        }
        let carrier_file = files
            .get("carrier.bin")
            .ok_or(CompleteDamageError::Binding)?;
        need(
            carrier_file["sha256"] == s(&carrier)
                && number(&carrier_file["bytes"])? == core.carrier_bytes.len() as u64,
        )?;
        for (path, raw) in projection
            .documents()
            .filter(|(p, _)| *p != "candidate-manifest.json")
        {
            let file = files.get(path).ok_or(CompleteDamageError::Binding)?;
            need(file["sha256"] == s(hash(raw)) && number(&file["bytes"])? == raw.len() as u64)?;
        }
        let sections = array(&capacity["section_rows"])?;
        need(sections.len() == core.sections.len())?;
        let mut ids = Vec::new();
        let mut required = Vec::new();
        let mut section_hashes = BTreeMap::new();
        for (row, section) in sections.iter().zip(&core.sections) {
            let row = array(row)?;
            need(row.len() == 17)?;
            let id = u64::from(section.section_id);
            need(row[0] == V::U64(id) && row[3] == V::U64(u64::from(section.closure_class)))?;
            let raw = section
                .envelope()
                .map_err(|_| CompleteDamageError::Binding)?;
            let digest = hash(&raw);
            need(row[12] == s(&digest) && row[13] == V::U64(raw.len() as u64))?;
            need(ids.last().is_none_or(|previous| *previous < id))?;
            ids.push(id);
            section_hashes.insert(id, digest);
            if section.closure_class == 128 {
                required.push(id);
            }
        }
        need(required == REQUIRED)?;
        let counts = [16, 4, 256, 128, q, 21, 4 * q, 415, 21];
        for (family, count) in FAMILIES.iter().zip(counts) {
            need(
                corpus
                    .case_count(family)
                    .map_err(|_| CompleteDamageError::Binding)?
                    == count,
            )?;
        }
        need(corpus.accidental_case_count() == 840 + 5 * q)?;
        Ok(Self {
            candidate: hash(candidate_raw),
            carrier,
            q,
            ids,
            section_hashes,
            counts,
        })
    }
    fn case_ids(&self) -> Vec<String> {
        FAMILIES
            .iter()
            .zip(self.counts)
            .flat_map(|(family, count)| {
                (0..count).map(move |ordinal| format!("{family}-{ordinal:06}"))
            })
            .collect()
    }
}

fn kat_document(receipts: &[Vec<u8>; 4]) -> Result<(V, bool)> {
    let mut rows = Vec::new();
    let mut all = true;
    for (raw, id) in receipts.iter().zip(crate::boundary_kat_v2::KAT_IDS) {
        let value = parse(raw)?;
        let row = closed(&value, "schema,kat_id,result")?;
        need(
            row["schema"] == s("golden-board.m2-boundary-kat-result/v2") && row["kat_id"] == s(id),
        )?;
        all &= passing(&row["result"])?;
        rows.push(o([
            ("kat_id", s(id)),
            ("result", row["result"].clone()),
            ("bytes", V::U64(raw.len() as u64)),
            ("sha256", s(hash(raw))),
        ]));
    }
    Ok((
        o([
            ("schema", s("golden-board.m2-boundary-kats/v2")),
            ("profile_id", s(PROFILE)),
            ("rows", a(rows)),
        ]),
        all,
    ))
}
fn retained_kats(raw: &[u8]) -> Result<[Vec<u8>; 4]> {
    let value = parse(raw)?;
    let value = closed(&value, "schema,profile_id,rows")?;
    need(
        value["schema"] == s("golden-board.m2-boundary-kats/v2")
            && value["profile_id"] == s(PROFILE),
    )?;
    let rows = array(&value["rows"])?;
    need(rows.len() == 4)?;
    let mut receipts = Vec::new();
    for (row, id) in rows.iter().zip(crate::boundary_kat_v2::KAT_IDS) {
        let row = closed(row, "kat_id,result,bytes,sha256")?;
        need(row["kat_id"] == s(id))?;
        passing(&row["result"])?;
        let raw = encode(&o([
            ("schema", s("golden-board.m2-boundary-kat-result/v2")),
            ("kat_id", s(id)),
            ("result", row["result"].clone()),
        ]))?;
        need(number(&row["bytes"])? == raw.len() as u64 && sha(&row["sha256"])? == hash(&raw))?;
        receipts.push(raw);
    }
    receipts.try_into().map_err(|_| CompleteDamageError::Shape)
}
fn promise(family: &str, states: &[(u64, &V)], wrong: u64) -> Result<bool> {
    let selected: Vec<_> = match family {
        "D0" | "D1" | "D5" => states.iter().collect(),
        "D2" | "D3" | "D4" | "D6" => states
            .iter()
            .filter(|(id, _)| REQUIRED.contains(id))
            .collect(),
        "D7" | "B0" => vec![],
        _ => return Err(CompleteDamageError::Shape),
    };
    let mut all = true;
    for (_, state) in selected {
        all &= good(state)?;
    }
    Ok(all && (family == "B0" || wrong == 0))
}
fn validate_streams(state: &V, rows: &V) -> Result<()> {
    need(matches!(
        string(state)?,
        "exact" | "degraded" | "failure" | "ambiguous" | "resource-limit"
    ))?;
    let rows = array(rows)?;
    need(rows.len() == 2)?;
    let mut available = [false; 2];
    for (i, row) in rows.iter().enumerate() {
        let row = array(row)?;
        need(row.len() == 3 && row[0] == V::U64(i as u64 + 2))?;
        available[i] = boolean(&row[1])?;
        let digest = sha(&row[2])?;
        need(available[i] == (digest != ZERO))?;
    }
    need(!available[1] || available[0])?;
    match string(state)? {
        "exact" => need(available == [true, true]),
        "degraded" => need(available[0]),
        _ => need(available == [false, false]),
    }
}
fn sidecar(case: &Object) -> Result<Vec<u8>> {
    let obs = object(&case["observation"])?;
    encode(&o([
        ("schema", s("golden-board.m2-observation-resources/v2")),
        ("channel", obs["channel"].clone()),
        ("observation_sha256", obs["observation_sha256"].clone()),
        ("result_sha256", case["decoder_result_sha256"].clone()),
        ("source_owners", source_owners()),
        ("resource", case["resource"].clone()),
        ("adapter_rows", case["adapter_rows"].clone()),
    ]))
}
fn compact_full(raw: &[u8], binding: &Binding, identity: &V) -> Result<V> {
    let value = parse(raw)?;
    let v = closed(
        &value,
        "schema,observation,decoder_result,resource_projection,expected_section_states,wrong_accept_count,reauthored_boundary,promise_result",
    )?;
    need(
        v["schema"] == s("golden-board.m2-damage-replay-case/v2") && v["observation"] == *identity,
    )?;
    let obs = object(identity)?;
    let family = string(&obs["family_id"])?;
    need(boolean(&v["reauthored_boundary"])? == (family == "B0"))?;
    let result = closed(
        &v["decoder_result"],
        "schema,channel,artifact_state,established_profile_id,section_rows,fragment_diagnostics_sha256,m2_required_available,m2_all_available,m2_required_stream_sha256,m2_all_stream_sha256,resource,accepted_hypothesis_rows",
    )?;
    need(
        result["schema"] == s("golden-board.m2-damage-decoder-result/v2")
            && result["channel"] == obs["channel"],
    )?;
    sha(&result["fragment_diagnostics_sha256"])?;
    let established = string(&result["established_profile_id"])?;
    need(established.is_empty() || established == PROFILE)?;
    let states = array(&v["expected_section_states"])?;
    need(states.len() == binding.ids.len())?;
    let mut compact_states = Vec::new();
    let mut allstates = BTreeMap::new();
    for (row, id) in states.iter().zip(&binding.ids) {
        let row = closed(row, "section_id,state")?;
        need(row["section_id"] == V::U64(*id))?;
        checked_state(&row["state"])?;
        allstates.insert(*id, &row["state"]);
        compact_states.push(a([V::U64(*id), row["state"].clone()]));
    }
    let mut visible = BTreeSet::new();
    let mut previous = 0;
    let mut wrong = 0u64;
    for row in array(&result["section_rows"])? {
        let row = closed(row, "section_id,state,semantic_sha256")?;
        let id = number(&row["section_id"])?;
        need(id > previous && id <= u32::MAX as u64)?;
        previous = id;
        visible.insert(id);
        need(checked_state(&row["state"])? != "unknown")?;
        let expected = allstates.get(&id).ok_or(CompleteDamageError::Binding)?;
        need(**expected == row["state"])?;
        let digest = sha(&row["semantic_sha256"])?;
        if good(&row["state"])? {
            need(digest != ZERO)?;
            if binding
                .section_hashes
                .get(&id)
                .is_none_or(|expected| expected != digest)
            {
                wrong = add(wrong, 1)?;
            }
        } else {
            need(digest == ZERO)?;
        }
    }
    for (id, state) in &allstates {
        if !visible.contains(id) {
            need(checked_state(state)? == "unknown")?;
        }
    }
    need(number(&v["wrong_accept_count"])? == wrong)?;
    let hypotheses = array(&result["accepted_hypothesis_rows"])?;
    need(hypotheses.len() <= 64 && (obs["channel"] != s("OBS_UNITS") || hypotheses.is_empty()))?;
    let mut last = None;
    for row in hypotheses {
        let row = closed(
            row,
            "transform_id,polarity_id,sector_id,profile_id,mapping_sha256",
        )?;
        let t = number(&row["transform_id"])?;
        let p = number(&row["polarity_id"])?;
        let sector = number(&row["sector_id"])?;
        need(t < 8 && p < 2 && sector < 4)?;
        let profile = string(&row["profile_id"])?;
        let order = if profile == PROFILE {
            0
        } else {
            (2..=7)
                .find(|v| crate::candidate::profile_by_version(*v).is_some_and(|x| x.id == profile))
                .ok_or(CompleteDamageError::Binding)?
                - 1
        };
        let key = (t, p, sector, order, sha(&row["mapping_sha256"])?.to_owned());
        need(last.as_ref().is_none_or(|v| v < &key))?;
        last = Some(key);
    }
    let streams = a([
        a([
            V::U64(2),
            result["m2_required_available"].clone(),
            result["m2_required_stream_sha256"].clone(),
        ]),
        a([
            V::U64(3),
            result["m2_all_available"].clone(),
            result["m2_all_stream_sha256"].clone(),
        ]),
    ]);
    validate_streams(&result["artifact_state"], &streams)?;
    if boolean(&result["m2_required_available"])? {
        need(established == PROFILE)?;
    }
    if result["artifact_state"] == s("exact") {
        need(
            array(&result["section_rows"])?
                .iter()
                .all(|row| good(&object(row).unwrap()["state"]).unwrap_or(false)),
        )?;
    }
    if result["artifact_state"] == s("resource-limit") {
        need(
            established.is_empty()
                && visible.is_empty()
                && hypotheses.is_empty()
                && result["fragment_diagnostics_sha256"] == s(hash(b"[]")),
        )?;
    }
    let resource = closed(
        &v["resource_projection"],
        "schema,channel,observation_sha256,result_sha256,source_owners,resource,adapter_rows",
    )?;
    let result_sha = hash(&encode(&v["decoder_result"])?);
    need(
        resource["schema"] == s("golden-board.m2-observation-resources/v2")
            && resource["channel"] == obs["channel"]
            && resource["observation_sha256"] == obs["observation_sha256"]
            && resource["result_sha256"] == s(&result_sha)
            && resource["source_owners"] == source_owners()
            && resource["resource"] == result["resource"],
    )?;
    Ok(o([
        ("observation", identity.clone()),
        ("decoder_result_sha256", s(result_sha)),
        ("artifact_state", result["artifact_state"].clone()),
        ("stream_rows", streams),
        ("section_states", a(compact_states)),
        ("wrong_accept_count", v["wrong_accept_count"].clone()),
        ("promise_result", v["promise_result"].clone()),
        (
            "resource_projection_sha256",
            s(hash(&encode(&v["resource_projection"])?)),
        ),
        ("resource", resource["resource"].clone()),
        ("adapter_rows", resource["adapter_rows"].clone()),
    ]))
}
fn validate_compact(case: &V, binding: &Binding, identity: &V) -> Result<Vec<u8>> {
    let v = closed(
        case,
        "observation,decoder_result_sha256,artifact_state,stream_rows,section_states,wrong_accept_count,promise_result,resource_projection_sha256,resource,adapter_rows",
    )?;
    need(v["observation"] == *identity)?;
    sha(&v["decoder_result_sha256"])?;
    sha(&v["resource_projection_sha256"])?;
    let raw = encode(case)?;
    if raw.len() > 262144 {
        return Err(CompleteDamageError::Bounds);
    }
    validate_streams(&v["artifact_state"], &v["stream_rows"])?;
    let states = array(&v["section_states"])?;
    need(states.len() == binding.ids.len())?;
    let mut state_refs = Vec::new();
    for (row, id) in states.iter().zip(&binding.ids) {
        let row = array(row)?;
        need(row.len() == 2 && row[0] == V::U64(*id))?;
        checked_state(&row[1])?;
        state_refs.push((*id, &row[1]));
    }
    if v["artifact_state"] == s("exact") {
        for (_, state) in &state_refs {
            need(good(state)?)?;
        }
    }
    if v["artifact_state"] == s("resource-limit") {
        for (_, state) in &state_refs {
            need(checked_state(state)? == "unknown")?;
        }
    }
    let wrong = number(&v["wrong_accept_count"])?;
    let counters = closed(
        &v["resource"],
        "section_attempts,primitive_steps,peak_scratch_bytes",
    )?;
    need(number(&counters["section_attempts"])? <= 4096)?;
    number(&counters["primitive_steps"])?;
    number(&counters["peak_scratch_bytes"])?;
    let family = string(&object(identity)?["family_id"])?;
    need(passing(&v["promise_result"])? == promise(family, &state_refs, wrong)?)?;
    let raw = sidecar(v)?;
    need(sha(&v["resource_projection_sha256"])? == hash(&raw))?;
    Ok(raw)
}
#[derive(Default)]
struct Emissions {
    names: BTreeSet<String>,
    bytes: u64,
}
impl Emissions {
    fn write(
        &mut self,
        path: &str,
        raw: &[u8],
        emit: &mut impl FnMut(&str, &[u8]) -> Result<()>,
    ) -> Result<()> {
        let bytes = add(self.bytes, raw.len() as u64)?;
        if self.names.len() >= 4096 || bytes > 536870912 || !self.names.insert(path.to_owned()) {
            return Err(CompleteDamageError::Bounds);
        }
        emit(path, raw)?;
        self.bytes = bytes;
        Ok(())
    }
}
/// Canonical admitted output. It records retention, not fresh execution.
#[derive(Clone, Debug)]
pub struct CompleteDamageProjectionV2 {
    root: Vec<u8>,
    limits: Vec<u8>,
}
impl CompleteDamageProjectionV2 {
    pub fn root_bytes(&self) -> &[u8] {
        &self.root
    }
    pub fn resource_limits_bytes(&self) -> &[u8] {
        &self.limits
    }
}
/// Append-only streaming projection; any failed push poisons the unfinished writer.
/// `emit` must write only to private staging until `finish` succeeds.
pub struct CompleteDamageV2<'a> {
    corpus: &'a DamageCorpusV2,
    binding: Binding,
    family: usize,
    ordinal: u64,
    writer: Option<FamilyWriter>,
    families: Vec<V>,
    emissions: Emissions,
    corpus_hash: Sha256,
    replay_hash: Sha256,
    resources: ResourceLimitsAccumulatorV2,
    kats: V,
    kats_pass: bool,
    poisoned: bool,
}
impl<'a> CompleteDamageV2<'a> {
    pub fn new(
        projection: &StaticProjectionV2,
        corpus: &'a DamageCorpusV2,
        receipts: [Vec<u8>; 4],
    ) -> Result<Self> {
        let binding = Binding::new(projection, corpus)?;
        let (kats, kats_pass) = kat_document(&receipts)?;
        let ids = binding.case_ids();
        let refs = ids.iter().map(String::as_str).collect::<Vec<_>>();
        let resources =
            ResourceLimitsAccumulatorV2::new(&refs).map_err(|_| CompleteDamageError::Binding)?;
        Ok(Self {
            corpus,
            writer: Some(FamilyWriter::new("D0", &binding.carrier)),
            binding,
            family: 0,
            ordinal: 0,
            families: vec![],
            emissions: Emissions::default(),
            corpus_hash: Sha256::new(),
            replay_hash: Sha256::new(),
            resources,
            kats,
            kats_pass,
            poisoned: false,
        })
    }
    fn identity(&self) -> Result<Vec<u8>> {
        if self.family >= 9 {
            return Err(CompleteDamageError::Coverage);
        }
        Ok(self
            .corpus
            .case(FAMILIES[self.family], self.ordinal)
            .map_err(|_| CompleteDamageError::Binding)?
            .identity_bytes()
            .to_vec())
    }
    pub fn push(
        &mut self,
        raw: &[u8],
        emit: &mut impl FnMut(&str, &[u8]) -> Result<()>,
    ) -> Result<()> {
        if self.poisoned {
            return Err(CompleteDamageError::Coverage);
        }
        self.poisoned = true;
        let identity_raw = self.identity()?;
        let identity = parse(&identity_raw)?;
        let compact = compact_full(raw, &self.binding, &identity)?;
        self.accept(compact, &identity_raw, &identity, emit)?;
        self.replay_hash.update(raw);
        self.poisoned = false;
        Ok(())
    }
    fn push_retained(
        &mut self,
        compact: V,
        emit: &mut impl FnMut(&str, &[u8]) -> Result<()>,
    ) -> Result<()> {
        let identity_raw = self.identity()?;
        let identity = parse(&identity_raw)?;
        self.accept(compact, &identity_raw, &identity, emit)
    }
    fn accept(
        &mut self,
        compact: V,
        identity_raw: &[u8],
        identity: &V,
        emit: &mut impl FnMut(&str, &[u8]) -> Result<()>,
    ) -> Result<()> {
        let sidecar = validate_compact(&compact, &self.binding, identity)?;
        let case_id = string(&object(identity)?["case_id"])?;
        self.resources
            .push(case_id, &sidecar)
            .map_err(|_| CompleteDamageError::Binding)?;
        let emissions = &mut self.emissions;
        let mut limited = |p: &str, b: &[u8]| emissions.write(p, b, emit);
        self.writer
            .as_mut()
            .ok_or(CompleteDamageError::Coverage)?
            .push(compact, &mut limited)?;
        self.corpus_hash.update(identity_raw);
        self.ordinal += 1;
        if self.ordinal == self.binding.counts[self.family] {
            self.families.push(
                self.writer
                    .take()
                    .ok_or(CompleteDamageError::Coverage)?
                    .finish(self.kats_pass, &mut limited)?,
            );
            self.family += 1;
            self.ordinal = 0;
            if self.family < 9 {
                self.writer = Some(FamilyWriter::new(
                    FAMILIES[self.family],
                    &self.binding.carrier,
                ));
            }
        }
        Ok(())
    }
    pub fn finish(
        self,
        emit: &mut impl FnMut(&str, &[u8]) -> Result<()>,
    ) -> Result<CompleteDamageProjectionV2> {
        self.finish_internal(None, emit).map(|v| v.0)
    }
    fn finish_internal(
        mut self,
        retained_replay: Option<String>,
        emit: &mut impl FnMut(&str, &[u8]) -> Result<()>,
    ) -> Result<(CompleteDamageProjectionV2, BTreeSet<String>)> {
        if self.poisoned || self.family != 9 || self.ordinal != 0 || self.writer.is_some() {
            return Err(CompleteDamageError::Coverage);
        }
        let corpus_sha = format!("{:x}", self.corpus_hash.finalize());
        let replay_sha =
            retained_replay.unwrap_or_else(|| format!("{:x}", self.replay_hash.finalize()));
        let limits = self
            .resources
            .finish(&corpus_sha)
            .map_err(|_| CompleteDamageError::Coverage)?;
        self.emissions
            .write("resource-limits.json", &limits, emit)?;
        let kats = encode(&self.kats)?;
        self.emissions
            .write("damage/boundary-kats.json", &kats, emit)?;
        let mut wrong = 0;
        let mut passed = true;
        for (i, row) in self.families.iter().enumerate() {
            let row = object(row)?;
            passed &= passing(&row["result"])?;
            if i < 8 {
                wrong = add(wrong, number(&row["wrong_accept_count"])?)?;
            }
        }
        let root = encode(&o([
            ("schema", s("golden-board.m2-damage-manifest/v2")),
            ("profile_id", s(PROFILE)),
            ("candidate_manifest_sha256", s(self.binding.candidate)),
            ("carrier_sha256", s(self.binding.carrier)),
            ("source_owners", source_owners()),
            ("required_section_ids", a(REQUIRED.map(V::U64))),
            ("section_ids", a(self.binding.ids.into_iter().map(V::U64))),
            ("physical_units", V::U64(self.binding.q)),
            ("accidental_case_count", V::U64(840 + 5 * self.binding.q)),
            ("boundary_case_count", V::U64(21)),
            ("wrong_accept_count", V::U64(wrong)),
            ("result", outcome(passed)),
            ("corpus_sha256", s(corpus_sha)),
            ("complete_replay_sha256", s(replay_sha)),
            ("resource_limits_sha256", s(hash(&limits))),
            ("family_rows", a(self.families[..8].iter().cloned())),
            ("reauthored_boundary", self.families[8].clone()),
            (
                "boundary_kats",
                o([
                    ("path", s("damage/boundary-kats.json")),
                    ("bytes", V::U64(kats.len() as u64)),
                    ("sha256", s(hash(&kats))),
                ]),
            ),
        ]))?;
        self.emissions.write("damage/manifest.json", &root, emit)?;
        Ok((
            CompleteDamageProjectionV2 { root, limits },
            self.emissions.names,
        ))
    }
}

fn evidence_path(name: &str) -> bool {
    if name.len() > 128 || !name.is_ascii() {
        return false;
    }
    if matches!(
        name,
        "resource-limits.json" | "damage/manifest.json" | "damage/boundary-kats.json"
    ) {
        return true;
    }
    let Some((family, file)) = name.strip_prefix("damage/").and_then(|s| s.split_once('/')) else {
        return false;
    };
    if !FAMILIES.contains(&family) {
        return false;
    }
    if file == "manifest.json" {
        return true;
    }
    file.strip_suffix(".json").is_some_and(|index| {
        index.len() == 6
            && index.bytes().all(|b| b.is_ascii_digit())
            && index.parse::<u32>().is_ok_and(|i| i < 4096)
    })
}

/// Admit compact retention by regenerating every observation identity and exact
/// greedy shard. The complete replay digest is retained as a syntactically valid
/// commitment; compact data cannot reconstruct or prove that original execution.
pub fn admit_complete_damage_v2(
    projection: &StaticProjectionV2,
    corpus: &DamageCorpusV2,
    mut read: impl FnMut(&str) -> Result<Vec<u8>>,
    names: &[String],
) -> Result<CompleteDamageProjectionV2> {
    if names.len() > 4096 || names.iter().any(|name| !evidence_path(name)) {
        return Err(CompleteDamageError::Bounds);
    }
    let names_set = names.iter().cloned().collect::<BTreeSet<_>>();
    need(names_set.len() == names.len())?;
    let mut read_bounded = |path: &str| -> Result<Vec<u8>> {
        need(names_set.contains(path))?;
        let raw = read(path)?;
        if raw.len() > 1_048_576 {
            return Err(CompleteDamageError::Bounds);
        }
        Ok(raw)
    };
    let root_raw = read_bounded("damage/manifest.json")?;
    let root = parse(&root_raw)?;
    let root = closed(
        &root,
        "schema,profile_id,candidate_manifest_sha256,carrier_sha256,source_owners,required_section_ids,section_ids,physical_units,accidental_case_count,boundary_case_count,wrong_accept_count,result,corpus_sha256,complete_replay_sha256,resource_limits_sha256,family_rows,reauthored_boundary,boundary_kats",
    )?;
    let replay_sha = sha(&root["complete_replay_sha256"])?.to_owned();
    let receipts = retained_kats(&read_bounded("damage/boundary-kats.json")?)?;
    let mut writer = CompleteDamageV2::new(projection, corpus, receipts)?;
    // Fail static contradictions before generating the first potentially large observation.
    need(
        root["schema"] == s("golden-board.m2-damage-manifest/v2")
            && root["profile_id"] == s(PROFILE)
            && root["candidate_manifest_sha256"] == s(&writer.binding.candidate)
            && root["carrier_sha256"] == s(&writer.binding.carrier)
            && root["source_owners"] == source_owners()
            && root["physical_units"] == V::U64(writer.binding.q)
            && root["required_section_ids"] == a(REQUIRED.map(V::U64))
            && root["section_ids"] == a(writer.binding.ids.iter().copied().map(V::U64)),
    )?;
    let families = array(&root["family_rows"])?;
    need(families.len() == 8)?;
    for (index, family) in FAMILIES.iter().enumerate() {
        let family_path = format!("damage/{family}/manifest.json");
        let family_raw = read_bounded(&family_path)?;
        let doc = parse(&family_raw)?;
        let doc = closed(
            &doc,
            "schema,profile_id,carrier_sha256,family_id,case_count,wrong_accept_count,failed_promise_count,result,cases_sha256,shards",
        )?;
        need(number(&doc["case_count"])? == writer.binding.counts[index])?;
        let shards = array(&doc["shards"])?;
        if shards.is_empty() || shards.len() > 4096 {
            return Err(CompleteDamageError::Bounds);
        }
        for (shard_index, row) in shards.iter().enumerate() {
            let row = closed(row, "path,bytes,sha256,first_ordinal,case_count")?;
            let path = format!("damage/{family}/{shard_index:06}.json");
            need(row["path"] == s(&path))?;
            let raw = read_bounded(&path)?;
            need(
                raw.len() <= 524288
                    && number(&row["bytes"])? == raw.len() as u64
                    && sha(&row["sha256"])? == hash(&raw),
            )?;
            let shard = parse(&raw)?;
            let shard = closed(
                &shard,
                "schema,profile_id,family_id,first_ordinal,case_count,cases",
            )?;
            let cases = array(&shard["cases"])?;
            need(!cases.is_empty() && cases.len() <= 32)?;
            for case in cases {
                need(writer.family == index)?;
                writer.push_retained(case.clone(), &mut |p, b| need(read_bounded(p)? == b))?;
            }
        }
        need(writer.family == index + 1)?;
    }
    let (result, emitted) =
        writer.finish_internal(Some(replay_sha), &mut |p, b| need(read_bounded(p)? == b))?;
    need(emitted == names_set && result.root == root_raw)?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn retained_name_grammar_is_closed_before_any_file_read() {
        for path in [
            "damage/manifest.json",
            "resource-limits.json",
            "damage/boundary-kats.json",
            "damage/D0/manifest.json",
            "damage/B0/000020.json",
        ] {
            assert!(evidence_path(path));
        }
        for path in [
            "../damage/manifest.json",
            "damage/D8/000000.json",
            "damage/D0/0.json",
            "damage/D0/004096.json",
            "/damage/manifest.json",
            "damage/D0/manifest.json/extra",
            "extra.json",
        ] {
            assert!(!evidence_path(path), "{path}");
        }
    }
    #[test]
    fn retained_attempt_count_cannot_claim_the_unperformed_4097th_comparison() {
        let mut value = grammar_compact("resource-limit", "unknown");
        let V::Object(ref mut v) = value else {
            unreachable!()
        };
        let V::Object(resource) = v.get_mut("resource").unwrap() else {
            unreachable!()
        };
        resource.insert("section_attempts".into(), V::U64(4097));
        let digest = hash(&sidecar(v).unwrap());
        v.insert("resource_projection_sha256".into(), s(digest));
        let identity = v["observation"].clone();
        assert!(validate_compact(&value, &grammar_binding(), &identity).is_err());
    }
    fn grammar_binding() -> Binding {
        Binding {
            candidate: ZERO.into(),
            carrier: ZERO.into(),
            q: 1,
            ids: vec![1],
            section_hashes: BTreeMap::from([(1, "1".repeat(64))]),
            counts: [1; 9],
        }
    }
    fn grammar_compact(state: &str, section_state: &str) -> V {
        let available = state == "exact";
        let mut value = o([
            (
                "observation",
                o([
                    ("channel", s("OBS_UNITS")),
                    ("observation_sha256", s(ZERO)),
                    ("family_id", s("D7")),
                ]),
            ),
            ("decoder_result_sha256", s(ZERO)),
            ("artifact_state", s(state)),
            (
                "stream_rows",
                a((2..=3).map(|id| {
                    a([
                        V::U64(id),
                        V::Bool(available),
                        s(if available {
                            "1".repeat(64)
                        } else {
                            ZERO.into()
                        }),
                    ])
                })),
            ),
            ("section_states", a([a([V::U64(1), s(section_state)])])),
            ("wrong_accept_count", V::U64(0)),
            ("promise_result", s("pass")),
            ("resource_projection_sha256", s(ZERO)),
            (
                "resource",
                o([
                    ("section_attempts", V::U64(0)),
                    ("primitive_steps", V::U64(0)),
                    ("peak_scratch_bytes", V::U64(0)),
                ]),
            ),
            (
                "adapter_rows",
                a(crate::resources_v2::Kernel::ALL.map(|kernel| {
                    o([
                        ("kernel", s(kernel.id())),
                        ("calls", V::U64(0)),
                        ("reference_input_units", V::U64(0)),
                        ("peak_workspace_bytes", V::U64(0)),
                    ])
                })),
            ),
        ]);
        let digest = hash(&sidecar(object(&value).unwrap()).unwrap());
        let V::Object(ref mut v) = value else {
            unreachable!()
        };
        v.insert("resource_projection_sha256".into(), s(digest));
        value
    }
    #[test]
    fn retained_global_states_cannot_contradict_the_complete_catalog() {
        for (state, section, valid) in [
            ("exact", "verified", true),
            ("resource-limit", "unknown", true),
            ("exact", "unknown", false),
            ("resource-limit", "corrupt", false),
        ] {
            let value = grammar_compact(state, section);
            let identity = object(&value).unwrap()["observation"].clone();
            assert_eq!(
                validate_compact(&value, &grammar_binding(), &identity).is_ok(),
                valid,
                "{state}/{section}"
            );
        }
    }
    #[test]
    fn full_rows_cannot_add_a_visible_section_outside_the_source_catalog() {
        let compact = grammar_compact("exact", "verified");
        let v = object(&compact).unwrap();
        let identity = v["observation"].clone();
        let sections = a([1, 2].map(|id| {
            o([
                ("section_id", V::U64(id)),
                ("state", s("verified")),
                ("semantic_sha256", s("1".repeat(64))),
            ])
        }));
        let result = o([
            ("schema", s("golden-board.m2-damage-decoder-result/v2")),
            ("channel", s("OBS_UNITS")),
            ("artifact_state", s("exact")),
            ("established_profile_id", s(PROFILE)),
            ("section_rows", sections),
            ("fragment_diagnostics_sha256", s(hash(b"[]"))),
            ("m2_required_available", V::Bool(true)),
            ("m2_all_available", V::Bool(true)),
            ("m2_required_stream_sha256", s("1".repeat(64))),
            ("m2_all_stream_sha256", s("1".repeat(64))),
            ("resource", v["resource"].clone()),
            ("accepted_hypothesis_rows", a([])),
        ]);
        let mut compact = v.clone();
        compact.insert(
            "decoder_result_sha256".into(),
            s(hash(&encode(&result).unwrap())),
        );
        let resource = parse(&sidecar(&compact).unwrap()).unwrap();
        let row = o([
            ("schema", s("golden-board.m2-damage-replay-case/v2")),
            ("observation", identity.clone()),
            ("decoder_result", result),
            ("resource_projection", resource),
            (
                "expected_section_states",
                a([o([("section_id", V::U64(1)), ("state", s("verified"))])]),
            ),
            ("wrong_accept_count", V::U64(1)),
            ("reauthored_boundary", V::Bool(false)),
            ("promise_result", s("fail")),
        ]);
        assert!(compact_full(&encode(&row).unwrap(), &grammar_binding(), &identity).is_err());
    }
    #[test]
    fn retained_kat_hashes_bind_the_exact_closed_receipt() {
        let receipts = crate::boundary_kat_v2::KAT_IDS.map(|id| {
            encode(&o([
                ("schema", s("golden-board.m2-boundary-kat-result/v2")),
                ("kat_id", s(id)),
                ("result", s("pass")),
            ]))
            .unwrap()
        });
        let (document, passed) = kat_document(&receipts).unwrap();
        assert!(passed);
        assert_eq!(
            retained_kats(&encode(&document).unwrap()).unwrap(),
            receipts
        );
        let V::Object(mut changed) = document else {
            unreachable!()
        };
        let V::Array(rows) = changed.get_mut("rows").unwrap() else {
            unreachable!()
        };
        let V::Object(first) = &mut rows[0] else {
            unreachable!()
        };
        first.insert("result".into(), s("fail"));
        assert!(retained_kats(&encode(&V::Object(changed)).unwrap()).is_err());
    }
    #[test]
    fn oversized_cases_and_emission_overflow_fail_before_writing() {
        let mut writer = FamilyWriter::new("D0", ZERO);
        assert!(
            writer
                .push(case(262144), &mut |_, _| panic!("oversized case emitted"))
                .is_err()
        );
        let mut budget = Emissions {
            names: BTreeSet::new(),
            bytes: 536870912,
        };
        assert!(
            budget
                .write("damage/manifest.json", b"x", &mut |_, _| panic!(
                    "overflow emitted"
                ))
                .is_err()
        );
        let mut budget = Emissions::default();
        budget
            .write("resource-limits.json", b"x", &mut |_, _| Ok(()))
            .unwrap();
        assert!(
            budget
                .write("resource-limits.json", b"x", &mut |_, _| panic!(
                    "duplicate emitted"
                ))
                .is_err()
        );
    }
    #[test]
    fn degraded_can_retain_both_streams_but_available_hash_cannot_be_absent() {
        let digest = s("1".repeat(64));
        let both = a([
            a([V::U64(2), V::Bool(true), digest.clone()]),
            a([V::U64(3), V::Bool(true), digest]),
        ]);
        assert!(validate_streams(&s("degraded"), &both).is_ok());
        let absent = a([
            a([V::U64(2), V::Bool(true), s(ZERO)]),
            a([V::U64(3), V::Bool(true), s(ZERO)]),
        ]);
        assert!(validate_streams(&s("exact"), &absent).is_err());
    }
    fn case(padding: usize) -> V {
        o([
            ("wrong_accept_count", V::U64(0)),
            ("promise_result", s("pass")),
            ("padding", s("x".repeat(padding))),
        ])
    }
    #[test]
    fn shards_are_greedy_by_both_bounds_and_family_summary_hashes_actual_cases() {
        let mut files = BTreeMap::new();
        let mut emit = |p: &str, b: &[u8]| {
            files.insert(p.to_owned(), b.to_vec());
            Ok(())
        };
        let mut writer = FamilyWriter::new("D0", ZERO);
        let mut expected = Sha256::new();
        for _ in 0..65 {
            let row = case(0);
            expected.update(encode(&row).unwrap());
            writer.push(row, &mut emit).unwrap();
        }
        let summary = writer.finish(true, &mut emit).unwrap();
        let doc = parse(&files["damage/D0/manifest.json"]).unwrap();
        let d = object(&doc).unwrap();
        assert_eq!(d["cases_sha256"], s(format!("{:x}", expected.finalize())));
        assert_eq!(d["case_count"], V::U64(65));
        assert_eq!(array(&d["shards"]).unwrap().len(), 3);
        assert_eq!(object(&summary).unwrap()["result"], s("pass"));
        let mut writer = FamilyWriter::new("D7", ZERO);
        let mut files = BTreeMap::new();
        let mut emit = |p: &str, b: &[u8]| {
            files.insert(p.to_owned(), b.to_vec());
            Ok(())
        };
        for _ in 0..3 {
            writer.push(case(200_000), &mut emit).unwrap();
        }
        assert_eq!(
            object(&writer.finish(false, &mut emit).unwrap()).unwrap()["result"],
            s("fail")
        );
        let doc = parse(&files["damage/D7/manifest.json"]).unwrap();
        assert_eq!(array(&object(&doc).unwrap()["shards"]).unwrap().len(), 2);
    }
    #[test]
    fn failed_promises_remain_failed_and_b0_wrong_is_diagnostic() {
        for family in ["D0", "B0"] {
            let mut writer = FamilyWriter::new(family, ZERO);
            let mut row = case(0);
            let V::Object(ref mut v) = row else {
                unreachable!()
            };
            v.insert("wrong_accept_count".into(), V::U64(3));
            v.insert("promise_result".into(), s("fail"));
            writer.push(row, &mut |_, _| Ok(())).unwrap();
            let result = writer.finish(true, &mut |_, _| Ok(())).unwrap();
            assert_eq!(object(&result).unwrap()["result"], outcome(family == "B0"));
        }
    }
}
