//! Complete revised damage and physical proof after caller-established native
//! preflight agreement. This library emits private bytes, never Gate8 receipts.
use crate::complete_damage_v2::{CompleteDamageProjectionV2, CompleteDamageV2};
use crate::independence_v2::IndependenceProofV2;
use crate::preflight_v2::PreflightV2;
use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::error::Error;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CompleteCandidateError {
    Preflight,
    Source,
    Replay,
    Damage,
    Bounds,
    Emit,
    Read,
    Independence,
}
impl std::fmt::Display for CompleteCandidateError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "complete-candidate-v2: {self:?}")
    }
}
impl Error for CompleteCandidateError {}
pub type Result<T> = std::result::Result<T, CompleteCandidateError>;
type ReplayResult<T> = std::result::Result<T, Box<dyn Error>>;
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CandidateFileV2 {
    path: String,
    bytes: u64,
    sha256: String,
}
impl CandidateFileV2 {
    pub fn path(&self) -> &str {
        &self.path
    }
    pub fn bytes(&self) -> u64 {
        self.bytes
    }
    pub fn sha256(&self) -> &str {
        &self.sha256
    }
}
pub struct CompleteCandidateV2 {
    files: Vec<CandidateFileV2>,
    damage: CompleteDamageProjectionV2,
    within_bounds: bool,
    gate6: bool,
    proof: Option<IndependenceProofV2>,
}
impl CompleteCandidateV2 {
    pub fn files(&self) -> &[CandidateFileV2] {
        &self.files
    }
    pub fn damage(&self) -> &CompleteDamageProjectionV2 {
        &self.damage
    }
    pub fn measured_resources_within_bounds(&self) -> bool {
        self.within_bounds
    }
    pub fn gate6_passed(&self) -> bool {
        self.gate6
    }
    pub fn independence_proof(&self) -> Option<&IndependenceProofV2> {
        self.proof.as_ref()
    }
    pub fn proof_not_evaluated(&self) -> bool {
        self.proof.is_none()
    }
    pub fn passed(&self) -> bool {
        self.gate6 && self.proof.as_ref().is_some_and(IndependenceProofV2::passed)
    }
}
fn object(v: &V) -> Result<&BTreeMap<String, V>> {
    if let V::Object(v) = v {
        Ok(v)
    } else {
        Err(CompleteCandidateError::Source)
    }
}
fn parse(raw: &[u8]) -> Result<V> {
    validate_canonical_manifest(raw).map_err(|_| CompleteCandidateError::Source)
}
fn doc<'a>(core: &'a PreflightV2, path: &str) -> Result<&'a [u8]> {
    core.document(path).ok_or(CompleteCandidateError::Source)
}
fn pass_summary(raw: &[u8]) -> Result<bool> {
    let v = parse(raw)?;
    let v = object(&v)?;
    let summary = object(v.get("summary").ok_or(CompleteCandidateError::Source)?)?;
    match summary.get("result") {
        Some(V::String(s)) if s == "pass" => Ok(true),
        Some(V::String(s)) if s == "fail" => Ok(false),
        _ => Err(CompleteCandidateError::Source),
    }
}
fn realism_pass(raw: &[u8]) -> Result<bool> {
    let v = parse(raw)?;
    let root = object(&v)?;
    let realism = object(root.get("realism").ok_or(CompleteCandidateError::Source)?)?;
    if realism.len() != 2 {
        return Err(CompleteCandidateError::Source);
    }
    let V::Array(failures) = realism
        .get("failures")
        .ok_or(CompleteCandidateError::Source)?
    else {
        return Err(CompleteCandidateError::Source);
    };
    if failures.iter().any(|v| !matches!(v, V::String(_))) {
        return Err(CompleteCandidateError::Source);
    }
    match realism.get("result") {
        Some(V::String(s)) if s == "pass" => Ok(failures.is_empty()),
        Some(V::String(s)) if s == "fail" => Ok(false),
        _ => Err(CompleteCandidateError::Source),
    }
}
fn enter(core: &PreflightV2, workers: usize) -> Result<()> {
    if !(1..=8).contains(&workers) {
        return Err(CompleteCandidateError::Bounds);
    }
    if !pass_summary(doc(core, "known-answer-manifest.json")?)?
        || !pass_summary(doc(core, "grammar-state-manifest.json")?)?
        || !realism_pass(doc(core, "static-limits.json")?)?
    {
        return Err(CompleteCandidateError::Preflight);
    }
    let sources = crate::receiver_bounds_v2::ReceiverBoundSources::default();
    let bounds = crate::receiver_bounds_v2::derive_receiver_bounds_v2(sources)
        .map_err(|_| CompleteCandidateError::Source)?;
    if doc(core, "receiver-bounds.json")? != bounds {
        return Err(CompleteCandidateError::Source);
    }
    crate::receiver_bounds_v2::admit_resource_limits_v2(
        doc(core, "preflight-resource-limits.json")?,
        sources,
    )
    .map_err(|_| CompleteCandidateError::Preflight)
}
/// Check the same source, resource and static Gates 1–5 prerequisites used at
/// full replay entry, without constructing any D0–D7 observation.
pub fn validate_preflight_entry_v2(core: &PreflightV2, workers: usize) -> Result<()> {
    enter(core, workers)
}
#[derive(Default)]
struct Files {
    rows: BTreeMap<String, CandidateFileV2>,
    total: u64,
}
impl Files {
    fn emit(
        &mut self,
        path: &str,
        raw: &[u8],
        emit: &mut impl FnMut(&str, &[u8]) -> Result<()>,
    ) -> Result<()> {
        let total = self
            .total
            .checked_add(raw.len() as u64)
            .ok_or(CompleteCandidateError::Bounds)?;
        if self.rows.len() >= 4119 || total > 570425344 || self.rows.contains_key(path) {
            return Err(CompleteCandidateError::Bounds);
        }
        emit(path, raw)?;
        self.total = total;
        self.rows.insert(
            path.into(),
            CandidateFileV2 {
                path: path.into(),
                bytes: raw.len() as u64,
                sha256: format!("{:x}", Sha256::digest(raw)),
            },
        );
        Ok(())
    }
}
fn gate6_pass(root: &[u8], within_bounds: bool) -> Result<bool> {
    let root = parse(root)?;
    let result = object(&root)?
        .get("result")
        .ok_or(CompleteCandidateError::Source)?;
    match result {
        V::String(s) if s == "pass" => Ok(within_bounds),
        V::String(s) if s == "fail" => Ok(false),
        _ => Err(CompleteCandidateError::Source),
    }
}
/// Call only after the coordinator has independently compared native preflight
/// outputs. `emit` and `read` must address private staging; a returned result is
/// not a publication permission, a source-freeze receipt, or a Gate8 result.
pub fn build_complete_candidate_v2(
    core: &PreflightV2,
    workers: usize,
    mut emit: impl FnMut(&str, &[u8]) -> Result<()>,
    mut read: impl FnMut(&str) -> Result<Vec<u8>>,
) -> Result<CompleteCandidateV2> {
    complete_with_replay(core, workers, &mut emit, &mut read, |consume| {
        let selected = crate::replay_backend_v2::ordered_cases(core.corpus(), true)?;
        crate::replay_backend_v2::replay_workers(core.corpus(), &selected, workers, true, consume)
    })
}
fn complete_with_replay(
    core: &PreflightV2,
    workers: usize,
    emit: &mut impl FnMut(&str, &[u8]) -> Result<()>,
    read: &mut impl FnMut(&str) -> Result<Vec<u8>>,
    replay: impl FnOnce(&mut dyn FnMut(usize, Vec<u8>, Vec<u8>) -> ReplayResult<()>) -> ReplayResult<()>,
) -> Result<CompleteCandidateV2> {
    enter(core, workers)?;
    let mut files = Files::default();
    for (path, raw) in core.documents() {
        files.emit(path, raw, emit)?;
    }
    let mut damage = CompleteDamageV2::new(
        core.static_projection(),
        core.corpus(),
        core.boundary_kats().clone(),
    )
    .map_err(|_| CompleteCandidateError::Source)?;
    let mut damage_names = Vec::new();
    let mut cursor = 0usize;
    let mut damage_emit = |path: &str, raw: &[u8]| -> crate::complete_damage_v2::Result<()> {
        files
            .emit(path, raw, emit)
            .map_err(|_| crate::complete_damage_v2::CompleteDamageError::Emit)?;
        damage_names.push(path.to_owned());
        Ok(())
    };
    replay(&mut |index, _, row| {
        if index != cursor {
            return Err(CompleteCandidateError::Replay.into());
        }
        damage
            .push(&row, &mut damage_emit)
            .map_err(|_| CompleteCandidateError::Damage)?;
        cursor += 1;
        Ok(())
    })
    .map_err(|_| CompleteCandidateError::Replay)?;
    let damage = damage
        .finish(&mut damage_emit)
        .map_err(|_| CompleteCandidateError::Damage)?;
    let sources = crate::receiver_bounds_v2::ReceiverBoundSources::default();
    let within_bounds = match crate::receiver_bounds_v2::admit_resource_limits_v2(
        damage.resource_limits_bytes(),
        sources,
    ) {
        Ok(()) => true,
        Err(crate::receiver_bounds_v2::ReceiverBoundsError::Exceeded) => false,
        Err(_) => return Err(CompleteCandidateError::Source),
    };
    let gate6 = gate6_pass(damage.root_bytes(), within_bounds)?;
    let proof = if gate6 {
        let proof = crate::independence_v2::build_complete_independence_v2(
            crate::recovery_provenance_v2::RecoveryProvenanceInputs {
                carrier: doc(core, "carrier.bin")?,
                candidate_manifest: doc(core, "candidate-manifest.json")?,
                capacity_ledger: doc(core, "capacity-ledger.json")?,
                ownership_ledger: doc(core, "ownership-ledger.json")?,
                semantic_envelope: doc(core, "semantic-envelope.json")?,
                profile_policy: sources.profile_policy,
                profile_limits: sources.profile_limits,
                damage_policy: sources.damage_policy,
            },
            core.static_projection(),
            core.corpus(),
            |p| read(p).map_err(|_| crate::complete_damage_v2::CompleteDamageError::Emit),
            &damage_names,
        )
        .map_err(|_| CompleteCandidateError::Independence)?;
        if proof.damage_manifest() != damage.root_bytes()
            || proof.recovery_provenance().canonical_bytes() != core.recovery().canonical_bytes()
        {
            return Err(CompleteCandidateError::Independence);
        }
        files.emit("independence-proof.json", proof.canonical_bytes(), emit)?;
        Some(proof)
    } else {
        None
    };
    Ok(CompleteCandidateV2 {
        files: files.rows.into_values().collect(),
        damage,
        within_bounds,
        gate6,
        proof,
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fresh_core_emit_and_partial_iterator_failures_never_reach_proof() {
        let core = crate::preflight_v2::build_preflight_v2(
            crate::preflight_v2::PreflightInputsV2::default(),
        )
        .unwrap();
        let mut called = false;
        let result = complete_with_replay(
            &core,
            1,
            &mut |_, _| Err(CompleteCandidateError::Emit),
            &mut |_| panic!("read before complete damage"),
            |_| {
                called = true;
                Ok(())
            },
        );
        assert!(matches!(result, Err(CompleteCandidateError::Emit)));
        assert!(!called);
        let mut emitted = Vec::new();
        let result = complete_with_replay(
            &core,
            1,
            &mut |p, _| {
                emitted.push(p.to_owned());
                Ok(())
            },
            &mut |_| panic!("read before complete damage"),
            |_| Ok(()),
        );
        assert!(matches!(result, Err(CompleteCandidateError::Damage)));
        assert_eq!(emitted, crate::preflight_v2::CORE_PATHS);
        assert!(
            !emitted
                .iter()
                .any(|p| p == "independence-proof.json" || p == "damage/manifest.json")
        );
        for index in [0, 1] {
            let result = complete_with_replay(
                &core,
                1,
                &mut |_, _| Ok(()),
                &mut |_| panic!("read after malformed row"),
                |consume| consume(index, vec![], b"{}\n".to_vec()),
            );
            assert!(matches!(result, Err(CompleteCandidateError::Replay)));
        }
        let result = complete_with_replay(
            &core,
            0,
            &mut |_, _| panic!("emission with invalid worker bound"),
            &mut |_| panic!("read with invalid worker bound"),
            |_| panic!("replay with invalid worker bound"),
        );
        assert!(matches!(result, Err(CompleteCandidateError::Bounds)));
    }
    fn raw(value: V) -> Vec<u8> {
        gb_foundation::serialize_manifest(&value).unwrap()
    }
    fn o(rows: impl IntoIterator<Item = (&'static str, V)>) -> V {
        V::Object(rows.into_iter().map(|(k, v)| (k.into(), v)).collect())
    }
    #[test]
    fn static_realism_failure_cannot_enter_damage() {
        for (result, failures, expected) in [
            ("pass", vec![], true),
            ("fail", vec![V::String("density".into())], false),
            ("pass", vec![V::String("density".into())], false),
        ] {
            let value = raw(o([(
                "realism",
                o([
                    ("result", V::String(result.into())),
                    ("failures", V::Array(failures)),
                ]),
            )]));
            assert_eq!(realism_pass(&value).unwrap(), expected);
        }
    }
    #[test]
    fn losing_damage_or_exceeded_bounds_do_not_reach_proof() {
        for result in ["pass", "fail"] {
            for bounds in [false, true] {
                let root = raw(o([("result", V::String(result.into()))]));
                assert_eq!(
                    gate6_pass(&root, bounds).unwrap(),
                    result == "pass" && bounds
                );
            }
        }
    }
    #[test]
    fn emit_failure_does_not_record_success_or_allow_later_duplicate() {
        let mut files = Files::default();
        assert!(
            files
                .emit("x", b"data", &mut |_, _| Err(CompleteCandidateError::Emit))
                .is_err()
        );
        assert!(files.rows.is_empty());
        files.emit("x", b"data", &mut |_, _| Ok(())).unwrap();
        assert!(
            files
                .emit("x", b"data", &mut |_, _| panic!("duplicate write"))
                .is_err()
        );
    }
}
