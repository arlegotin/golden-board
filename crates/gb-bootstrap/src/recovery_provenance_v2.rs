//! Actual OBS_BITS recovery, with no source construction or saved-result fallback.
use crate::damage::{ArtifactState, SectionState};
use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
const LIMIT: usize = 1_048_576;
const PROFILE: &str = "eh72-hier-r5-r2-r1-lzss-crc32c-v1";
type Object = BTreeMap<String, V>;
type Result<T> = std::result::Result<T, RecoveryProvenanceError>;
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RecoveryProvenanceError {
    Input,
    Binding,
    Recovery,
    Knowledge,
    Arithmetic,
}
impl std::fmt::Display for RecoveryProvenanceError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "recovery-provenance-v2: {self:?}")
    }
}
impl std::error::Error for RecoveryProvenanceError {}
#[derive(Clone, Copy)]
pub struct RecoveryProvenanceInputs<'a> {
    pub carrier: &'a [u8],
    pub candidate_manifest: &'a [u8],
    pub capacity_ledger: &'a [u8],
    pub ownership_ledger: &'a [u8],
    pub semantic_envelope: &'a [u8],
    pub profile_policy: &'a [u8],
    pub profile_limits: &'a [u8],
    pub damage_policy: &'a [u8],
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RecoveredBodyV2 {
    section_id: u32,
    section_version: u16,
    envelope: Vec<u8>,
    stored: Vec<u8>,
    decoded: Vec<u8>,
}
impl RecoveredBodyV2 {
    pub fn section_id(&self) -> u32 {
        self.section_id
    }
    pub fn section_version(&self) -> u16 {
        self.section_version
    }
    pub fn envelope(&self) -> &[u8] {
        &self.envelope
    }
    pub fn stored_payload(&self) -> &[u8] {
        &self.stored
    }
    pub fn decoded_payload(&self) -> &[u8] {
        &self.decoded
    }
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RecoveryProvenanceV2 {
    value: Vec<u8>,
    decoder_result: Vec<u8>,
    knowledge: Vec<u8>,
    first_use: Vec<u8>,
    prefixes: [Vec<u8>; 4],
    required: Vec<u8>,
    all: Vec<u8>,
    bodies: Vec<RecoveredBodyV2>,
}
impl RecoveryProvenanceV2 {
    pub fn canonical_bytes(&self) -> &[u8] {
        &self.value
    }
    pub fn decoder_result(&self) -> &[u8] {
        &self.decoder_result
    }
    pub fn knowledge_use(&self) -> &[u8] {
        &self.knowledge
    }
    pub fn first_use(&self) -> &[u8] {
        &self.first_use
    }
    pub fn prefixes(&self) -> [&[u8]; 4] {
        self.prefixes.each_ref().map(Vec::as_slice)
    }
    pub fn required_stream(&self) -> &[u8] {
        &self.required
    }
    pub fn all_stream(&self) -> &[u8] {
        &self.all
    }
    pub fn bodies(&self) -> &[RecoveredBodyV2] {
        &self.bodies
    }
}
fn need(ok: bool, error: RecoveryProvenanceError) -> Result<()> {
    if ok { Ok(()) } else { Err(error) }
}
fn input(ok: bool) -> Result<()> {
    need(ok, RecoveryProvenanceError::Input)
}
fn bind(ok: bool) -> Result<()> {
    need(ok, RecoveryProvenanceError::Binding)
}
fn recover(ok: bool) -> Result<()> {
    need(ok, RecoveryProvenanceError::Recovery)
}
fn obj(v: &V) -> Result<&Object> {
    if let V::Object(v) = v {
        Ok(v)
    } else {
        Err(RecoveryProvenanceError::Input)
    }
}
fn arr(v: &V) -> Result<&[V]> {
    if let V::Array(v) = v {
        Ok(v)
    } else {
        Err(RecoveryProvenanceError::Input)
    }
}
fn num(v: &V) -> Result<u64> {
    if let V::U64(v) = v {
        Ok(*v)
    } else {
        Err(RecoveryProvenanceError::Input)
    }
}
fn string(v: &V) -> Result<&str> {
    if let V::String(v) = v {
        Ok(v)
    } else {
        Err(RecoveryProvenanceError::Input)
    }
}
fn field<'a>(v: &'a Object, k: &str) -> Result<&'a V> {
    v.get(k).ok_or(RecoveryProvenanceError::Input)
}
fn nfield(v: &Object, k: &str) -> Result<u64> {
    num(field(v, k)?)
}
fn sfield<'a>(v: &'a Object, k: &str) -> Result<&'a str> {
    string(field(v, k)?)
}
fn hash(v: &[u8]) -> String {
    format!("{:x}", Sha256::digest(v))
}
fn s(v: &str) -> V {
    V::String(v.into())
}
fn n(v: usize) -> V {
    V::U64(v as u64)
}
fn object(rows: impl IntoIterator<Item = (&'static str, V)>) -> V {
    V::Object(rows.into_iter().map(|(k, v)| (k.into(), v)).collect())
}
fn identity(v: &[u8]) -> V {
    object([("bytes", n(v.len())), ("sha256", s(&hash(v)))])
}
fn parse(raw: &[u8]) -> Result<V> {
    input(!raw.is_empty() && raw.len() <= LIMIT)?;
    validate_canonical_manifest(raw).map_err(|_| RecoveryProvenanceError::Input)
}
fn serialize(v: &V) -> Result<Vec<u8>> {
    let b = serialize_manifest(v).map_err(|_| RecoveryProvenanceError::Input)?;
    input(b.len() <= LIMIT)?;
    Ok(b)
}
fn table(v: &Object, name: &str) -> Result<Vec<Object>> {
    let fs = arr(field(v, &format!("{name}_fields"))?)?;
    arr(field(v, &format!("{name}_rows"))?)?
        .iter()
        .map(|row| {
            let row = arr(row)?;
            input(fs.len() == row.len())?;
            fs.iter()
                .zip(row)
                .map(|(k, v)| Ok((string(k)?.to_owned(), v.clone())))
                .collect()
        })
        .collect()
}
fn size_hash(raw: &[u8], row: &Object) -> Result<()> {
    bind(raw.len() as u64 == nfield(row, "bytes")? && hash(raw) == sfield(row, "sha256")?)
}
fn extract(raw: &[u8], side: usize, width: usize, sector: u8, bytes: usize) -> Result<Vec<u8>> {
    input(bytes <= 32768)?;
    let mut out = vec![0; bytes];
    for at in 0..bytes
        .checked_mul(8)
        .ok_or(RecoveryProvenanceError::Arithmetic)?
    {
        let (r, c) = crate::sector_cell_at(side, width, sector, at)
            .map_err(|_| RecoveryProvenanceError::Input)?;
        let flat = r
            .checked_mul(side)
            .and_then(|v| v.checked_add(c))
            .ok_or(RecoveryProvenanceError::Arithmetic)?;
        let b = raw
            .get(4 + flat / 8)
            .ok_or(RecoveryProvenanceError::Input)?;
        out[at / 8] |= ((b >> (7 - flat % 8)) & 1) << (7 - at % 8);
    }
    Ok(out)
}
pub fn build_recovery_provenance_v2(
    i: RecoveryProvenanceInputs<'_>,
) -> Result<RecoveryProvenanceV2> {
    input((4..=524292).contains(&i.carrier.len()))?;
    for p in [i.profile_policy, i.profile_limits, i.damage_policy] {
        input(!p.is_empty() && p.len() <= LIMIT)?;
    }
    // The actual Rust receiver uses these exact compiled neutral owners.
    input(
        i.profile_policy == include_bytes!("../../../spec/profile-policy-v2.toml")
            && i.profile_limits == include_bytes!("../../../spec/profile-limits-v2.toml")
            && i.damage_policy == include_bytes!("../../../spec/damage-policy-v2.toml"),
    )?;
    crate::physical_v2::admit_physical_inputs_v2(
        i.candidate_manifest,
        i.capacity_ledger,
        i.ownership_ledger,
        i.semantic_envelope,
    )
    .map_err(|_| RecoveryProvenanceError::Input)?;
    let candidate = parse(i.candidate_manifest)?;
    let candidate = obj(&candidate)?;
    let capacity = parse(i.capacity_ledger)?;
    let capacity = obj(&capacity)?;
    let ownership = parse(i.ownership_ledger)?;
    let ownership = obj(&ownership)?;
    let source = obj(field(candidate, "source_identities")?)?;
    let files: BTreeMap<_, _> = arr(field(candidate, "files")?)?
        .iter()
        .map(|v| {
            let o = obj(v)?;
            Ok((sfield(o, "path")?, o))
        })
        .collect::<Result<_>>()?;
    size_hash(
        i.carrier,
        files
            .get("carrier.bin")
            .ok_or(RecoveryProvenanceError::Input)?,
    )?;
    for (p, k) in [
        (i.profile_policy, "profile_policy_sha256"),
        (i.profile_limits, "profile_limits_source_sha256"),
        (i.damage_policy, "damage_policy_sha256"),
    ] {
        bind(hash(p) == sfield(source, k)?)?;
    }
    let side = nfield(ownership, "side")?;
    let width = nfield(ownership, "shell_width")?;
    let cells = side
        .checked_mul(side)
        .ok_or(RecoveryProvenanceError::Arithmetic)?;
    bind(
        u64::from(u32::from_be_bytes(
            i.carrier[..4]
                .try_into()
                .map_err(|_| RecoveryProvenanceError::Input)?,
        )) == cells
            && i.carrier.len() as u64 == 4 + cells / 8,
    )?;
    let result = crate::damage_v2::decode_observation_v2("OBS_BITS", i.carrier);
    recover(
        result.profile_version() == Some(8)
            && result.inventory_established()
            && result.artifact_state() == ArtifactState::Exact,
    )?;
    let rows = table(capacity, "section")?;
    let expected: BTreeMap<_, _> = rows
        .iter()
        .map(|r| Ok((nfield(r, "section_id")?, r)))
        .collect::<Result<_>>()?;
    recover(
        result.sections().len() == expected.len()
            && result
                .sections()
                .iter()
                .map(|r| u64::from(r.section_id))
                .collect::<BTreeSet<_>>()
                == expected.keys().copied().collect(),
    )?;
    let mapping_hash = hash(&serialize(field(ownership, "mapping")?)?);
    let hypotheses = result.accepted_hypotheses();
    recover(
        hypotheses.len() == 4
            && hypotheses
                .iter()
                .map(|h| {
                    (
                        h.transform_id,
                        h.polarity_id,
                        h.sector_id,
                        h.profile_version,
                    )
                })
                .collect::<BTreeSet<_>>()
                == (0..4).map(|sector| (0, 0, sector, 8)).collect(),
    )?;
    bind(hypotheses.iter().all(|h| h.mapping_sha256 == mapping_hash))?;
    let shells = table(ownership, "shell")?;
    let mut prefixes: [Vec<u8>; 4] = std::array::from_fn(|_| Vec::new());
    for sector in 0..4 {
        let header = extract(i.carrier, side as usize, width as usize, sector as u8, 64)?;
        let count = u64::from(u32::from_be_bytes(
            header[56..60]
                .try_into()
                .map_err(|_| RecoveryProvenanceError::Input)?,
        ));
        input(
            (512..=32768 * 8).contains(&count)
                && count % 8 == 0
                && count
                    <= width
                        .checked_mul(side - width)
                        .ok_or(RecoveryProvenanceError::Arithmetic)?,
        )?;
        let prefix = extract(
            i.carrier,
            side as usize,
            width as usize,
            sector as u8,
            (count / 8) as usize,
        )?;
        size_hash(
            &prefix,
            files
                .get(format!("route-{sector}.bin").as_str())
                .ok_or(RecoveryProvenanceError::Input)?,
        )?;
        bind(nfield(&shells[sector], "route_prefix_cells")? == count)?;
        prefixes[sector] = prefix;
    }
    let mut bodies = Vec::new();
    let mut inventory = None;
    let mut sections: Vec<_> = result.sections().iter().collect();
    sections.sort_by_key(|r| r.section_id);
    for r in sections {
        recover(r.state == SectionState::Verified)?;
        let raw = r
            .envelope
            .as_deref()
            .ok_or(RecoveryProvenanceError::Recovery)?;
        let section = crate::decode_section(raw).map_err(|_| RecoveryProvenanceError::Recovery)?;
        let row = expected[&u64::from(r.section_id)];
        for (k, v) in [
            ("section_id", u64::from(section.section_id)),
            ("section_type", u64::from(section.section_type)),
            ("section_version", u64::from(section.section_version)),
            ("closure_class", u64::from(section.closure_class)),
            ("check_id", u64::from(section.check_id)),
        ] {
            bind(nfield(row, k)? == v)?;
        }
        bind(
            section
                .dependencies
                .iter()
                .map(|v| V::U64(u64::from(*v)))
                .collect::<Vec<_>>()
                == arr(field(row, "dependency_ids")?)?,
        )?;
        bind(
            raw.len() as u64 == nfield(row, "envelope_bytes")?
                && hash(raw) == sfield(row, "envelope_sha256")?
                && section.payload.len() as u64 == nfield(row, "stored_payload_bytes")?
                && hash(&section.payload) == sfield(row, "payload_sha256")?,
        )?;
        if section.section_id == 1 {
            inventory = Some(
                crate::bootstrap_v2::decode_inventory(&section.payload)
                    .map_err(|_| RecoveryProvenanceError::Recovery)?,
            );
        }
        if section.section_type == 3 {
            let decoded =
                crate::body_codec_v1::decode_body(section.section_version, &section.payload)
                    .map_err(|_| RecoveryProvenanceError::Recovery)?;
            bind(
                decoded.len() <= 16384
                    && decoded.len() as u64 == nfield(row, "decoded_payload_bytes")?,
            )?;
            bodies.push(RecoveredBodyV2 {
                section_id: section.section_id,
                section_version: section.section_version,
                envelope: raw.to_vec(),
                stored: section.payload,
                decoded,
            });
        }
    }
    bind(
        inventory
            .ok_or(RecoveryProvenanceError::Recovery)?
            .entries
            .iter()
            .map(|r| u64::from(r.section_id))
            .collect::<BTreeSet<_>>()
            == expected.keys().copied().collect(),
    )?;
    bind(
        bodies.iter().map(|b| b.section_id).collect::<Vec<_>>()
            == [16, 17, 18]
                .into_iter()
                .chain(100..164)
                .chain(200..211)
                .collect::<Vec<_>>(),
    )?;
    let aggregate = bodies.iter().try_fold(0u64, |n, b| {
        n.checked_add(b.decoded.len() as u64)
            .ok_or(RecoveryProvenanceError::Arithmetic)
    })?;
    input(aggregate <= LIMIT as u64)?;
    let required = result
        .required_bytes()
        .ok_or(RecoveryProvenanceError::Recovery)?
        .to_vec();
    let all = result
        .all_bytes()
        .ok_or(RecoveryProvenanceError::Recovery)?
        .to_vec();
    for (raw, key) in [
        (&required, "required_content_sha256"),
        (&all, "all_content_sha256"),
    ] {
        input((4..=LIMIT).contains(&raw.len()))?;
        bind(hash(raw) == sfield(source, key)?)?;
    }
    let body_payloads = bodies
        .iter()
        .map(|b| (b.section_id, b.decoded.clone()))
        .collect();
    let knowledge =
        crate::knowledge_v2::build_knowledge_use_v2(crate::knowledge_v2::KnowledgeInputs {
            prefixes: prefixes.each_ref().map(Vec::as_slice),
            side: side as u16,
            width: width as u16,
            required_stream: &required,
            all_stream: &all,
            body_payloads: &body_payloads,
        })
        .map_err(|_| RecoveryProvenanceError::Knowledge)?;
    let knowledge_doc = parse(&knowledge)?;
    for row in arr(field(obj(&knowledge_doc)?, "route_rows")?)? {
        bind(sfield(obj(row)?, "mapping_sha256")? == mapping_hash)?;
    }
    let first_use = crate::first_use_v2::build_first_use_v2(crate::first_use_v2::FirstUseInputs {
        prefixes: prefixes.each_ref().map(Vec::as_slice),
        side: side as u16,
        width: width as u16,
    })
    .map_err(|_| RecoveryProvenanceError::Knowledge)?;
    let (decoder_result, _) = crate::damage_v2::render_decoder_result_v2("OBS_BITS", &result)
        .map_err(|_| RecoveryProvenanceError::Recovery)?;
    input(
        [knowledge.len(), first_use.len(), decoder_result.len()]
            .iter()
            .all(|n| *n <= LIMIT),
    )?;
    let value = serialize(&object([
        ("schema", s("golden-board.m2-recovery-provenance/v2")),
        ("profile_id", s(PROFILE)),
        ("scope", s("actual-observation-to-carried-knowledge")),
        ("result", s("pass")),
        (
            "inputs",
            object([
                ("carrier", identity(i.carrier)),
                ("candidate_manifest", identity(i.candidate_manifest)),
                ("capacity_ledger", identity(i.capacity_ledger)),
                ("ownership_ledger", identity(i.ownership_ledger)),
                ("semantic_envelope", identity(i.semantic_envelope)),
            ]),
        ),
        (
            "policy_sha256",
            object([
                ("spec/profile-policy-v2.toml", s(&hash(i.profile_policy))),
                ("spec/profile-limits-v2.toml", s(&hash(i.profile_limits))),
                ("spec/damage-policy-v2.toml", s(&hash(i.damage_policy))),
            ]),
        ),
        (
            "geometry",
            object([("side", V::U64(side)), ("shell_width", V::U64(width))]),
        ),
        ("decoder_result", identity(&decoder_result)),
        (
            "prefix_rows",
            V::Array(
                prefixes
                    .iter()
                    .enumerate()
                    .map(|(sector, raw)| {
                        object([
                            ("sector_id", n(sector)),
                            ("bytes", n(raw.len())),
                            ("sha256", s(&hash(raw))),
                        ])
                    })
                    .collect(),
            ),
        ),
        (
            "stream_rows",
            V::Array(
                [(2, &required), (3, &all)]
                    .map(|(id, raw)| {
                        object([
                            ("section_id", n(id)),
                            ("bytes", n(raw.len())),
                            ("sha256", s(&hash(raw))),
                        ])
                    })
                    .to_vec(),
            ),
        ),
        (
            "body_rows",
            V::Array(
                bodies
                    .iter()
                    .map(|b| {
                        object([
                            ("section_id", V::U64(u64::from(b.section_id))),
                            ("section_version", V::U64(u64::from(b.section_version))),
                            ("envelope", identity(&b.envelope)),
                            ("stored", identity(&b.stored)),
                            ("decoded", identity(&b.decoded)),
                        ])
                    })
                    .collect(),
            ),
        ),
        ("knowledge_use", identity(&knowledge)),
        ("first_use", identity(&first_use)),
    ]))?;
    Ok(RecoveryProvenanceV2 {
        value,
        decoder_result,
        knowledge,
        first_use,
        prefixes,
        required,
        all,
        bodies,
    })
}
pub fn validate_recovery_provenance_v2(
    raw: &[u8],
    input: RecoveryProvenanceInputs<'_>,
) -> Result<()> {
    parse(raw)?;
    bind(build_recovery_provenance_v2(input)?.canonical_bytes() == raw)
}
