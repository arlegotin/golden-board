//! Explicit development profile8 observation decoder. Historical decoders are unchanged.
//! Runtime input is only the serialized observation and neutral source-owned code.
use crate::bootstrap_v2::decode_inventory;
use crate::candidate::{
    CandidateProfile, DecodeQuality, EH_UNIT_BYTES, EhErasure, EhObservation,
    HierarchicalGroupDiagnostic, HierarchicalGroupState, HierarchicalLaneDiagnostic,
    HierarchicalLaneState, HierarchicalRepetitionState, RS_CODEWORD_BYTES, TransportFamily,
    aggregate_repetition_observation, decode_eh_unit_fast as decode_eh_unit, decode_rs_unit,
};
use crate::damage::{
    AcceptedHypothesis, ArtifactState, FragmentState, ObsMatrix, ObsUnits, ResourceProjection,
    SectionResult, SectionState, observation_sha256,
};
use crate::recipe_wire_v1::{RecipePackageV1, evaluate_serialized_recipe_v1};
use crate::resources_v2::{Kernel, ReferenceLedger};
use crate::route_receiver_v2::{ObservedRoute, RouteError};
use crate::{
    CLOSURE_M2_REQUIRED, COMMON_PAYLOAD_BYTES, FragmentWitness, Inventory, InventoryEntry,
    MAX_BLOCKS_PER_COPY, MAX_ENVELOPE_BYTES, MAX_SECTION_CANDIDATES, RecoveryQuality,
    SECTION_INVENTORY, SectionEnvelope, SectionWitness, aggregate_section_witnesses,
    assemble_semantic_copy, decode_common_block, decode_section,
};
use gb_foundation::{ManifestValue, serialize_manifest};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
#[path = "boundary_kat_v2.rs"]
pub mod boundary_kat_v2;
const PROFILE_V8: u16 = 8;
const ABSENT_U16: u16 = u16::MAX;
const ZERO_SHA256: &str = "0000000000000000000000000000000000000000000000000000000000000000";
const MAX_PHYSICAL_UNITS: u32 = 2389;
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DamageV2Error {
    Channel,
    Owner,
    Observation,
    Profile,
    Reconstruction,
    ResourceLimit,
}
pub type Result<T> = std::result::Result<T, DamageV2Error>;
pub type FragmentDiagnosticV2 = crate::damage_v1::FragmentDiagnosticV1;
/// Evidence attached to one exact observed route, separate from availability.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ContextWitnessV2 {
    hypothesis: AcceptedHypothesis,
    package_sha256: String,
    definitions_sha256: String,
    proof: crate::route_semantics_v2::ContextProof,
}
impl ContextWitnessV2 {
    pub fn hypothesis(&self) -> &AcceptedHypothesis {
        &self.hypothesis
    }
    pub fn package_sha256(&self) -> &str {
        &self.package_sha256
    }
    pub fn definitions_sha256(&self) -> &str {
        &self.definitions_sha256
    }
    pub fn proof(&self) -> &crate::route_semantics_v2::ContextProof {
        &self.proof
    }
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RecoveryResultV2 {
    profile_version: Option<u16>,
    inventory_established: bool,
    resource: ResourceProjection,
    artifact_state: ArtifactState,
    sections: Vec<SectionResult>,
    fragments: Vec<FragmentDiagnosticV2>,
    accepted_hypotheses: Vec<AcceptedHypothesis>,
    required: Option<Vec<u8>>,
    all: Option<Vec<u8>>,
    context_proof: Option<crate::route_semantics_v2::ContextProof>,
    context_witnesses: Vec<ContextWitnessV2>,
    adapter: ReferenceLedger,
    observation_binding: Option<(String, String)>,
}
impl RecoveryResultV2 {
    pub fn profile_version(&self) -> Option<u16> {
        self.profile_version
    }
    pub fn context_witnesses(&self) -> &[ContextWitnessV2] {
        &self.context_witnesses
    }
    fn closed(state: ArtifactState, resource: ResourceProjection) -> Self {
        Self {
            profile_version: None,
            inventory_established: false,
            resource,
            artifact_state: state,
            sections: vec![],
            fragments: vec![],
            accepted_hypotheses: vec![],
            required: None,
            all: None,
            context_proof: None,
            context_witnesses: vec![],
            adapter: ReferenceLedger::default(),
            observation_binding: None,
        }
    }
    pub fn artifact_state(&self) -> ArtifactState {
        self.artifact_state
    }
    pub fn required_bytes(&self) -> Option<&[u8]> {
        self.required.as_deref()
    }
    pub fn all_bytes(&self) -> Option<&[u8]> {
        self.all.as_deref()
    }
    pub fn fragments(&self) -> &[FragmentDiagnosticV2] {
        &self.fragments
    }
    pub fn sections(&self) -> &[SectionResult] {
        &self.sections
    }
    pub fn resource(&self) -> ResourceProjection {
        self.resource
    }
    pub fn accepted_hypotheses(&self) -> &[AcceptedHypothesis] {
        &self.accepted_hypotheses
    }
    pub fn inventory_established(&self) -> bool {
        self.inventory_established
    }
}
fn profile_for_version(version: u16) -> Option<CandidateProfile> {
    if version == 8 {
        Some(CandidateProfile {
            id: "eh72-hier-r5-r2-r1-lzss-crc32c-v1",
            version: 8,
            transport: TransportFamily::Eh72HierarchicalRepetition,
            section_check_id: 1,
            required_copy_count: 2,
        })
    } else {
        crate::candidate::profile_by_version(version)
    }
}
fn checked_charge(resource: &mut Budget, steps: u64, count: u64, scratch: u64) -> Result<()> {
    let mut next = resource.value;
    crate::route_receiver_v2::charge(&mut next, steps, count, scratch)
        .map_err(|_| DamageV2Error::ResourceLimit)?;
    resource
        .adapter
        .vm_workspace(scratch)
        .map_err(|_| DamageV2Error::ResourceLimit)?;
    resource.value = next;
    Ok(())
}
fn charge_registry_lane(resource: &mut Budget, version: u16) -> Result<()> {
    let (steps, count, scratch) = match version {
        8 | 2 | 3 | 4 | 7 => (80435, 24, 4613),
        5 | 6 => (1698049, 1, 7688),
        _ => return Err(DamageV2Error::Profile),
    };
    checked_charge(resource, steps, count, scratch)
}
fn charge_repetition_group(resource: &mut Budget) -> Result<()> {
    checked_charge(resource, 24, 1728, 10)?;
    checked_charge(resource, 80435, 24, 4613)
}
#[derive(Default)]
struct Budget {
    value: ResourceProjection,
    adapter: ReferenceLedger,
    attempted: BTreeSet<Vec<u8>>,
    complete_paths: usize,
    charged_groups: BTreeSet<(usize, u16, Vec<Option<u32>>)>,
}
impl std::ops::Deref for Budget {
    type Target = ResourceProjection;
    fn deref(&self) -> &Self::Target {
        &self.value
    }
}
impl std::ops::DerefMut for Budget {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.value
    }
}
impl Budget {
    fn event(&mut self, kernel: Kernel, units: u64, workspace: u64) -> Result<()> {
        self.adapter
            .event(kernel, units, workspace)
            .map_err(|_| DamageV2Error::ResourceLimit)
    }
    fn retain(&mut self, key: &str, bytes: u64) -> Result<()> {
        self.adapter
            .retain(key, bytes)
            .map_err(|_| DamageV2Error::ResourceLimit)
    }
}
fn charge_group_once(
    resource: &mut Budget,
    profile: u16,
    ids: Vec<Option<u32>>,
    package: Option<&crate::recipe::RecipePackage>,
) -> Result<()> {
    if ids.len() == 1 || ids.iter().all(Option::is_none) {
        return Ok(());
    }
    let key = (resource.complete_paths, profile, ids);
    if resource.charged_groups.contains(&key) {
        return Ok(());
    }
    resource.event(
        Kernel::RepetitionAdapter,
        key.2.len() as u64 * 1728,
        216 + 2 * 1728,
    )?;
    if let Some(package) = package {
        charge_observed(resource, package, 113, 1728)?;
        charge_observed(resource, package, 30, 24)?;
    } else {
        charge_repetition_group(resource)?;
    }
    resource.event(Kernel::CommonFrame, 191, 191)?;
    resource.charged_groups.insert(key);
    Ok(())
}
fn charge_section_attempt(resource: &mut Budget, raw: &[u8]) -> Result<()> {
    if resource.attempted.contains(raw) {
        return Ok(());
    }
    if resource.section_attempts >= 4096 {
        return Err(DamageV2Error::ResourceLimit);
    };
    resource.retain(
        &format!("attempt:{}", resource.attempted.len()),
        raw.len() as u64 + 8,
    )?;
    resource.event(Kernel::SectionCheck, raw.len() as u64, raw.len() as u64)?;
    resource.attempted.insert(raw.to_vec());
    resource.section_attempts += 1;
    Ok(())
}

fn validate_envelope_against_inventory(
    envelope: &SectionEnvelope,
    inventory: &Inventory,
) -> Result<()> {
    let row = inventory
        .entries
        .iter()
        .find(|row| row.section_id == envelope.section_id)
        .ok_or(DamageV2Error::Reconstruction)?;
    if row.section_type != envelope.section_type
        || row.section_version != envelope.section_version
        || row.closure_class != envelope.closure_class
        || row.check_id != envelope.check_id
        || row.dependencies != envelope.dependencies
        || row.logical_payload_length as usize != envelope.payload.len()
    {
        Err(DamageV2Error::Reconstruction)
    } else {
        Ok(())
    }
}
fn diagnose_hierarchical(
    profile: CandidateProfile,
    observations: &[Option<EhObservation>],
) -> std::result::Result<HierarchicalGroupDiagnostic, crate::candidate::CodecError> {
    if profile.transport != TransportFamily::Eh72HierarchicalRepetition
        || !matches!(profile.version, 7 | 8)
        || !matches!(observations.len(), 1 | 2 | 5)
    {
        return Err(crate::candidate::CodecError::Parameter);
    }
    let present = observations.iter().filter(|value| value.is_some()).count();
    let mut valid = BTreeMap::<[u8; 191], bool>::new();
    let mut lanes = Vec::with_capacity(observations.len());
    for observation in observations {
        let Some(observation) = observation else {
            lanes.push(HierarchicalLaneDiagnostic {
                state: HierarchicalLaneState::Absent,
                common: None,
            });
            continue;
        };
        match decode_eh_unit(observation, profile.version) {
            Ok(decoded) => {
                let independently_verified =
                    decoded.quality == DecodeQuality::Verified && observation.erasures.is_empty();
                valid
                    .entry(decoded.common)
                    .and_modify(|verified| *verified |= independently_verified)
                    .or_insert(independently_verified);
                lanes.push(HierarchicalLaneDiagnostic {
                    state: if independently_verified {
                        HierarchicalLaneState::Verified
                    } else {
                        HierarchicalLaneState::Recovered
                    },
                    common: Some(decoded.common),
                });
            }
            Err(_) => lanes.push(HierarchicalLaneDiagnostic {
                state: HierarchicalLaneState::Corrupt,
                common: None,
            }),
        }
    }
    let repetition_constructed = observations.len() > 1 && present != 0;
    let mut repetition_state = HierarchicalRepetitionState::NotConstructed;
    let mut repetition_common = None;
    if repetition_constructed {
        if let Some(repetition) = aggregate_repetition_observation(observations)? {
            match decode_eh_unit(&repetition, profile.version) {
                Ok(decoded) => {
                    repetition_state = HierarchicalRepetitionState::Recovered;
                    repetition_common = Some(decoded.common);
                    // Aggregate bytes are always recovery evidence.
                    valid.entry(decoded.common).or_insert(false);
                }
                Err(_) => repetition_state = HierarchicalRepetitionState::Corrupt,
            }
        }
    }
    let distinct_candidate_count =
        u8::try_from(valid.len()).map_err(|_| crate::candidate::CodecError::InternalInvariant)?;
    let (state, common) = match valid.len() {
        0 if present == 0 => (HierarchicalGroupState::Missing, None),
        0 => (HierarchicalGroupState::Corrupt, None),
        1 => {
            let (common, independently_verified) = valid.into_iter().next().expect("one entry");
            (
                if independently_verified {
                    HierarchicalGroupState::Verified
                } else {
                    HierarchicalGroupState::Recovered
                },
                Some(common),
            )
        }
        _ => (HierarchicalGroupState::Conflict, None),
    };
    Ok(HierarchicalGroupDiagnostic {
        factor: observations.len() as u8,
        lanes,
        repetition_state,
        repetition_common,
        state,
        distinct_candidate_count,
        common,
        eh_codeword_invocations: u32::try_from(
            24 * (present + usize::from(repetition_constructed)),
        )
        .map_err(|_| crate::candidate::CodecError::InternalInvariant)?,
        repetition_symbol_invocations: if repetition_constructed {
            (EH_UNIT_BYTES * 8) as u32
        } else {
            0
        },
    })
}
#[derive(Clone, Debug)]
struct LocalCandidate {
    profile_version: u16,
    common: [u8; 191],
    quality: DecodeQuality,
}

#[derive(Clone, Debug)]
struct LaneInput {
    present: bool,
    observation: Option<EhObservation>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct GroupIdentity {
    section_id: u32,
    section_type: u16,
    section_version: u16,
    fragment_index: u16,
    fragment_count: u16,
    section_envelope_length: u32,
}

impl GroupIdentity {
    fn from_common(common: &[u8; 191]) -> Result<Self> {
        let block =
            decode_common_block(common, PROFILE_V8).map_err(|_| DamageV2Error::Reconstruction)?;
        if block.semantic_copy_id != 0 {
            return Err(DamageV2Error::Reconstruction);
        }
        Ok(Self {
            section_id: block.section_id,
            section_type: block.section_type,
            section_version: block.section_version,
            fragment_index: block.fragment_index,
            fragment_count: block.fragment_count,
            section_envelope_length: block.section_envelope_length,
        })
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ExpectedLane {
    identity: GroupIdentity,
    replica_index: u16,
    physical_replica_count: u16,
}

#[derive(Clone, Debug)]
struct GroupRecovery {
    identity: GroupIdentity,
    first_id: u32,
    factor: u8,
    state: FragmentState,
    common: Option<[u8; 191]>,
    lane_states: Vec<FragmentState>,
}

fn section_envelope_length(entry: &InventoryEntry) -> Result<usize> {
    let check = match entry.check_id {
        1 => 4_usize,
        2 => 8_usize,
        _ => return Err(DamageV2Error::Reconstruction),
    };
    18_usize
        .checked_add(
            entry
                .dependencies
                .len()
                .checked_mul(4)
                .ok_or(DamageV2Error::ResourceLimit)?,
        )
        .and_then(|value| value.checked_add(entry.logical_payload_length as usize))
        .and_then(|value| value.checked_add(check))
        .filter(|value| *value <= MAX_ENVELOPE_BYTES)
        .ok_or(DamageV2Error::ResourceLimit)
}

fn inventory_layout(inventory: &Inventory) -> Result<BTreeMap<u32, ExpectedLane>> {
    if inventory.inventory_version != 2 {
        return Err(DamageV2Error::Reconstruction);
    }
    let mut id = 1_u32;
    let mut output = BTreeMap::new();
    for entry in &inventory.entries {
        let envelope_length = section_envelope_length(entry)?;
        let fragment_count = envelope_length.div_ceil(COMMON_PAYLOAD_BYTES);
        let fragment_count_u16 =
            u16::try_from(fragment_count).map_err(|_| DamageV2Error::ResourceLimit)?;
        let factor = u16::from(entry.physical_replica_count);
        for fragment_index in 0..fragment_count_u16 {
            let identity = GroupIdentity {
                section_id: entry.section_id,
                section_type: entry.section_type,
                section_version: entry.section_version,
                fragment_index,
                fragment_count: fragment_count_u16,
                section_envelope_length: envelope_length as u32,
            };
            for replica_index in 0..factor {
                if id > MAX_PHYSICAL_UNITS {
                    return Err(DamageV2Error::ResourceLimit);
                }
                output.insert(
                    id,
                    ExpectedLane {
                        identity,
                        replica_index,
                        physical_replica_count: factor,
                    },
                );
                id = id.checked_add(1).ok_or(DamageV2Error::ResourceLimit)?;
            }
        }
    }
    Ok(output)
}

fn decode_local_candidates(
    units: &ObsUnits,
    resource: &mut Budget,
) -> Result<BTreeMap<u32, Vec<LocalCandidate>>> {
    let mut output = BTreeMap::<u32, Vec<LocalCandidate>>::new();
    let mut entries = units.entries.iter().collect::<Vec<_>>();
    entries.sort_by_key(|entry| entry.physical_unit_id);
    // This loop order is normative: input ID first, then active v8 followed by
    // archived registry fixtures v2 through v7, without short-circuiting.
    for entry in entries {
        for version in [8_u16, 2, 3, 4, 5, 6, 7] {
            resource.event(
                Kernel::LaneAdapter,
                entry.bytes.len() as u64,
                entry.bytes.len() as u64 + 191,
            )?;
            charge_registry_lane(resource, version)?;
            if entry.bytes.len() == if matches!(version, 5 | 6) { 255 } else { 216 } {
                resource.event(Kernel::CommonFrame, 191, 191)?;
            }
            let profile = profile_for_version(version).ok_or(DamageV2Error::Profile)?;
            let decoded = match profile.transport {
                TransportFamily::Eh72Replicated | TransportFamily::Eh72HierarchicalRepetition
                    if entry.bytes.len() == EH_UNIT_BYTES =>
                {
                    let encoded: [u8; EH_UNIT_BYTES] = entry.bytes.as_slice().try_into().unwrap();
                    decode_eh_unit(
                        &EhObservation {
                            encoded,
                            erasures: Vec::new(),
                        },
                        version,
                    )
                    .ok()
                }
                TransportFamily::Rs255_191 if entry.bytes.len() == RS_CODEWORD_BYTES => {
                    decode_rs_unit(&entry.bytes, &[], version).ok()
                }
                _ => None,
            };
            if let Some(decoded) = decoded {
                output
                    .entry(entry.physical_unit_id)
                    .or_default()
                    .push(LocalCandidate {
                        profile_version: version,
                        common: decoded.common,
                        quality: decoded.quality,
                    });
            }
        }
    }
    Ok(output)
}

fn recover_group(
    entries: &BTreeMap<u32, LaneInput>,
    first_id: u32,
    factor: u8,
    expected: GroupIdentity,
    resource: &mut Budget,
) -> Result<GroupRecovery> {
    if !matches!(factor, 1 | 2 | 5) {
        return Err(DamageV2Error::Reconstruction);
    }
    let mut observations = Vec::with_capacity(usize::from(factor));
    let mut present_without_eh = Vec::with_capacity(usize::from(factor));
    for lane in 0..u32::from(factor) {
        let id = first_id
            .checked_add(lane)
            .ok_or(DamageV2Error::ResourceLimit)?;
        let row = entries.get(&id);
        observations.push(row.and_then(|row| row.observation.clone()));
        present_without_eh.push(row.is_some_and(|row| row.present && row.observation.is_none()));
    }
    if factor > 1
        && (0..u32::from(factor)).any(|lane| {
            entries
                .get(&(first_id + lane))
                .is_some_and(|row| row.present)
        })
    {
        charge_group_once(
            resource,
            8,
            (0..u32::from(factor))
                .map(|lane| {
                    let id = first_id + lane;
                    entries.get(&id).filter(|r| r.present).map(|_| id)
                })
                .collect(),
            None,
        )?;
    }
    let profile = profile_for_version(PROFILE_V8).ok_or(DamageV2Error::Profile)?;
    let diagnostic =
        diagnose_hierarchical(profile, &observations).map_err(|_| DamageV2Error::Reconstruction)?;
    let mut lane_states = Vec::with_capacity(diagnostic.lanes.len());
    for (lane_index, lane) in diagnostic.lanes.into_iter().enumerate() {
        let agrees = lane
            .common
            .and_then(|common| GroupIdentity::from_common(&common).ok())
            == Some(expected);
        lane_states.push(if present_without_eh[lane_index] {
            FragmentState::Corrupt
        } else {
            match lane.state {
                HierarchicalLaneState::Absent => FragmentState::Missing,
                HierarchicalLaneState::Corrupt => FragmentState::Corrupt,
                HierarchicalLaneState::Verified if agrees => FragmentState::Verified,
                HierarchicalLaneState::Recovered if agrees => FragmentState::Recovered,
                HierarchicalLaneState::Verified | HierarchicalLaneState::Recovered => {
                    FragmentState::Corrupt
                }
            }
        });
    }
    let common_agrees = diagnostic
        .common
        .and_then(|common| GroupIdentity::from_common(&common).ok())
        == Some(expected);
    let state = match diagnostic.state {
        HierarchicalGroupState::Missing if present_without_eh.iter().any(|value| *value) => {
            FragmentState::Corrupt
        }
        HierarchicalGroupState::Missing => FragmentState::Missing,
        HierarchicalGroupState::Corrupt => FragmentState::Corrupt,
        HierarchicalGroupState::Conflict => FragmentState::Ambiguous,
        HierarchicalGroupState::Verified if common_agrees => FragmentState::Verified,
        HierarchicalGroupState::Recovered if common_agrees => FragmentState::Recovered,
        HierarchicalGroupState::Verified | HierarchicalGroupState::Recovered => {
            FragmentState::Corrupt
        }
    };
    Ok(GroupRecovery {
        identity: expected,
        first_id,
        factor,
        state,
        common: common_agrees.then_some(diagnostic.common).flatten(),
        lane_states,
    })
}

fn assemble_raw_fragment_bytes(groups: &[GroupRecovery]) -> Option<Vec<u8>> {
    let first = groups.first()?;
    let count = usize::from(first.identity.fragment_count);
    if groups.len() != count
        || groups.iter().enumerate().any(|(index, group)| {
            group.identity.fragment_index as usize != index
                || group.identity.section_id != first.identity.section_id
                || group.identity.section_type != first.identity.section_type
                || group.identity.section_version != first.identity.section_version
                || group.identity.fragment_count != first.identity.fragment_count
                || group.identity.section_envelope_length != first.identity.section_envelope_length
                || group.common.is_none()
        })
    {
        return None;
    }
    let envelope_length = usize::try_from(first.identity.section_envelope_length).ok()?;
    let mut raw = Vec::with_capacity(envelope_length);
    for group in groups {
        let block = decode_common_block(group.common.as_ref()?, PROFILE_V8).ok()?;
        raw.extend_from_slice(&block.payload);
    }
    (raw.len() == envelope_length).then_some(raw)
}

fn structurally_attemptable(raw: &[u8]) -> bool {
    if raw.len() < 22
        || raw.len() > 32790
        || raw[..2] != [0, 0]
        || u32::from_be_bytes(raw[2..6].try_into().unwrap()) == 0
        || !(1..=6).contains(&u16::from_be_bytes(raw[6..8].try_into().unwrap()))
        || !matches!(raw[10], 128 | 129)
    {
        return false;
    }
    let check_bytes = match raw[11] {
        1 => 4_usize,
        2 => 8_usize,
        _ => return false,
    };
    let dependencies = usize::from(u16::from_be_bytes([raw[12], raw[13]]));
    if dependencies > 4095 || 18 + dependencies * 4 > raw.len() {
        return false;
    }
    let section_id = u32::from_be_bytes(raw[2..6].try_into().unwrap());
    let mut prior = 0;
    for bytes in raw[18..18 + dependencies * 4].chunks_exact(4) {
        let id = u32::from_be_bytes(bytes.try_into().unwrap());
        if id <= prior || id == section_id {
            return false;
        }
        prior = id;
    }
    let payload = usize::try_from(u32::from_be_bytes(raw[14..18].try_into().unwrap())).ok();
    18_usize
        .checked_add(dependencies.checked_mul(4).unwrap_or(usize::MAX))
        .and_then(|value| value.checked_add(payload?))
        .and_then(|value| value.checked_add(check_bytes))
        == Some(raw.len())
}

fn checked_section_from_groups(
    groups: &[GroupRecovery],
    inventory: Option<&Inventory>,
    resource: &mut Budget,
) -> Result<Option<SectionResult>> {
    if groups.iter().any(|group| group.common.is_none()) {
        return Ok(None);
    }
    let common_count = groups.iter().filter(|g| g.common.is_some()).count() as u64;
    let envelope_len = groups
        .first()
        .map_or(0, |g| u64::from(g.identity.section_envelope_length));
    if common_count != 0 {
        resource.event(
            Kernel::SectionAssembly,
            191 * common_count,
            envelope_len + 24 * common_count,
        )?;
    }
    checked_section_after_assembly(groups, inventory, resource)
}

// The bootstrap caller has already entered the raw assembly adapter. Catalog
// recovery enters it again only after the inventory and geometry are admitted.
fn checked_section_after_assembly(
    groups: &[GroupRecovery],
    inventory: Option<&Inventory>,
    resource: &mut Budget,
) -> Result<Option<SectionResult>> {
    let Some(raw) = assemble_raw_fragment_bytes(groups) else {
        return Ok(None);
    };
    if !structurally_attemptable(&raw) {
        return Ok(None);
    }
    charge_section_attempt(resource, &raw)?;
    let Ok(envelope) = decode_section(&raw) else {
        return Ok(None);
    };
    if inventory
        .is_some_and(|inventory| validate_envelope_against_inventory(&envelope, inventory).is_err())
    {
        return Ok(None);
    }
    let recovered = groups
        .iter()
        .any(|group| group.state == FragmentState::Recovered);
    Ok(Some(SectionResult {
        section_id: envelope.section_id,
        state: if recovered {
            SectionState::Recovered
        } else {
            SectionState::Verified
        },
        envelope: Some(raw),
    }))
}

fn bootstrap_inventory_groups(
    entries: &BTreeMap<u32, LaneInput>,
    resource: &mut Budget,
) -> Result<Vec<GroupRecovery>> {
    let initial = GroupIdentity {
        section_id: 1,
        section_type: SECTION_INVENTORY,
        section_version: 2,
        fragment_index: 0,
        fragment_count: 1,
        section_envelope_length: 1,
    };
    // The first group establishes the two variable shape fields.  Identity
    // fields fixed by the route are checked before those fields are trusted.
    let mut observations = Vec::with_capacity(5);
    let mut present_without_eh = Vec::with_capacity(5);
    for id in 1_u32..=5 {
        let row = entries.get(&id);
        observations.push(row.and_then(|row| row.observation.clone()));
        present_without_eh.push(row.is_some_and(|row| row.present && row.observation.is_none()));
    }
    if (1_u32..=5).any(|id| entries.get(&id).is_some_and(|row| row.present)) {
        charge_group_once(
            resource,
            8,
            (1..=5)
                .map(|id| entries.get(&id).filter(|r| r.present).map(|_| id))
                .collect(),
            None,
        )?;
    }
    let profile = profile_for_version(PROFILE_V8).ok_or(DamageV2Error::Profile)?;
    let diagnostic =
        diagnose_hierarchical(profile, &observations).map_err(|_| DamageV2Error::Reconstruction)?;
    let Some(common) = diagnostic.common else {
        let state = match diagnostic.state {
            HierarchicalGroupState::Missing if present_without_eh.iter().any(|value| *value) => {
                FragmentState::Corrupt
            }
            HierarchicalGroupState::Missing => FragmentState::Missing,
            HierarchicalGroupState::Conflict => FragmentState::Ambiguous,
            _ => FragmentState::Corrupt,
        };
        return Ok(vec![GroupRecovery {
            identity: initial,
            first_id: 1,
            factor: 5,
            state,
            common: None,
            lane_states: diagnostic
                .lanes
                .iter()
                .enumerate()
                .map(|(lane_index, lane)| {
                    if present_without_eh[lane_index] {
                        return FragmentState::Corrupt;
                    }
                    match lane.state {
                        HierarchicalLaneState::Absent => FragmentState::Missing,
                        HierarchicalLaneState::Corrupt => FragmentState::Corrupt,
                        HierarchicalLaneState::Verified => FragmentState::Verified,
                        HierarchicalLaneState::Recovered => FragmentState::Recovered,
                    }
                })
                .collect(),
        }]);
    };
    let identity = GroupIdentity::from_common(&common)?;
    if identity.section_id != 1
        || identity.section_type != SECTION_INVENTORY
        || identity.section_version != 2
        || identity.fragment_index != 0
        || identity.fragment_count == 0
        || usize::from(identity.fragment_count) > MAX_BLOCKS_PER_COPY
        || identity.section_envelope_length as usize > 16_406
        || u32::from(identity.fragment_count) * 5 > MAX_PHYSICAL_UNITS
    {
        return Ok(vec![GroupRecovery {
            identity,
            first_id: 1,
            factor: 5,
            state: FragmentState::Corrupt,
            common: None,
            lane_states: vec![FragmentState::Corrupt; 5],
        }]);
    }
    let mut output = Vec::with_capacity(usize::from(identity.fragment_count));
    let lane_states = diagnostic
        .lanes
        .iter()
        .map(|lane| {
            let agrees = lane
                .common
                .and_then(|common| GroupIdentity::from_common(&common).ok())
                == Some(identity);
            match lane.state {
                HierarchicalLaneState::Absent => FragmentState::Missing,
                HierarchicalLaneState::Corrupt => FragmentState::Corrupt,
                HierarchicalLaneState::Verified if agrees => FragmentState::Verified,
                HierarchicalLaneState::Recovered if agrees => FragmentState::Recovered,
                HierarchicalLaneState::Verified | HierarchicalLaneState::Recovered => {
                    FragmentState::Corrupt
                }
            }
        })
        .collect();
    output.push(GroupRecovery {
        identity,
        first_id: 1,
        factor: 5,
        state: match diagnostic.state {
            HierarchicalGroupState::Verified => FragmentState::Verified,
            HierarchicalGroupState::Recovered => FragmentState::Recovered,
            HierarchicalGroupState::Conflict => FragmentState::Ambiguous,
            HierarchicalGroupState::Missing => FragmentState::Missing,
            HierarchicalGroupState::Corrupt => FragmentState::Corrupt,
        },
        common: Some(common),
        lane_states,
    });
    for fragment_index in 1..identity.fragment_count {
        let expected = GroupIdentity {
            fragment_index,
            ..identity
        };
        output.push(recover_group(
            entries,
            1_u32
                .checked_add(u32::from(fragment_index) * 5)
                .ok_or(DamageV2Error::ResourceLimit)?,
            5,
            expected,
            resource,
        )?);
    }
    Ok(output)
}

fn groups_from_layout(
    entries: &BTreeMap<u32, LaneInput>,
    layout: &BTreeMap<u32, ExpectedLane>,
    resource: &mut Budget,
) -> Result<Vec<GroupRecovery>> {
    let mut groups = Vec::new();
    for (&id, lane) in layout {
        if lane.replica_index != 0 || lane.identity.section_id == 1 {
            continue;
        }
        groups.push(recover_group(
            entries,
            id,
            u8::try_from(lane.physical_replica_count).map_err(|_| DamageV2Error::Reconstruction)?,
            lane.identity,
            resource,
        )?);
    }
    Ok(groups)
}

fn foreign_or_local_candidate<'a>(
    candidates: &'a BTreeMap<u32, Vec<LocalCandidate>>,
    id: u32,
) -> Option<&'a LocalCandidate> {
    let rows = candidates.get(&id)?;
    (rows.len() == 1).then(|| &rows[0])
}

fn candidate_matches_expected(
    candidate: &LocalCandidate,
    block: &crate::CommonBlock,
    expected: ExpectedLane,
) -> bool {
    candidate.profile_version == PROFILE_V8
        && block.profile_version == PROFILE_V8
        && block.semantic_copy_id == 0
        && block.section_id == expected.identity.section_id
        && block.section_type == expected.identity.section_type
        && block.section_version == expected.identity.section_version
        && block.fragment_index == expected.identity.fragment_index
        && block.fragment_count == expected.identity.fragment_count
        && block.section_envelope_length == expected.identity.section_envelope_length
}

fn diagnostic_hash(
    state: FragmentState,
    source: Option<&(&LocalCandidate, crate::CommonBlock)>,
) -> String {
    if matches!(state, FragmentState::Verified | FragmentState::Recovered) {
        source.map_or_else(
            || ZERO_SHA256.to_owned(),
            |(candidate, _)| format!("{:x}", Sha256::digest(candidate.common)),
        )
    } else {
        ZERO_SHA256.to_owned()
    }
}

fn diagnostics_with_layout(
    entries: &BTreeMap<u32, LaneInput>,
    local: &BTreeMap<u32, Vec<LocalCandidate>>,
    layout: &BTreeMap<u32, ExpectedLane>,
    groups: &[GroupRecovery],
) -> Vec<FragmentDiagnosticV2> {
    let group_by_id = groups
        .iter()
        .flat_map(|group| {
            (0..u32::from(group.factor)).map(move |lane| (group.first_id + lane, (group, lane)))
        })
        .collect::<BTreeMap<_, _>>();
    let ids = layout
        .keys()
        .chain(entries.keys())
        .copied()
        .collect::<BTreeSet<_>>();
    ids.into_iter()
        .map(|id| {
            let expected = layout.get(&id).copied();
            let group_lane = group_by_id.get(&id).copied();
            let local_candidate = foreign_or_local_candidate(local, id);
            let source = local_candidate.and_then(|candidate| {
                decode_common_block(&candidate.common, candidate.profile_version)
                    .ok()
                    .map(|block| (candidate, block))
            });
            // A group-level conflict is a logical aggregation result.  It
            // must not erase the independently checked state/hash of any
            // physical lane that supplied one of the conflicting values.
            let profile8_lane_state = group_lane.map_or(FragmentState::Unknown, |(group, lane)| {
                group.lane_states[lane as usize]
            });
            let source_matches_expected = expected.is_some_and(|expected| {
                source.as_ref().is_some_and(|(candidate, block)| {
                    candidate_matches_expected(candidate, block, expected)
                })
            });
            let state = match (expected, entries.contains_key(&id)) {
                (Some(_), false) => FragmentState::Missing,
                (Some(_), true) if source.is_some() && !source_matches_expected => {
                    FragmentState::Corrupt
                }
                (Some(_), true) => profile8_lane_state,
                (None, true) => source
                    .as_ref()
                    .map_or(FragmentState::Corrupt, |(candidate, _)| {
                        match candidate.quality {
                            DecodeQuality::Verified => FragmentState::Verified,
                            DecodeQuality::Recovered => FragmentState::Recovered,
                        }
                    }),
                (None, false) => FragmentState::Unknown,
            };
            let (section_id, semantic_copy_id, fragment_index) = expected
                .map(|row| (row.identity.section_id, 0, row.identity.fragment_index))
                .or_else(|| {
                    source.as_ref().map(|(_, block)| {
                        (
                            block.section_id,
                            block.semantic_copy_id,
                            block.fragment_index,
                        )
                    })
                })
                .unwrap_or((0, ABSENT_U16, ABSENT_U16));
            FragmentDiagnosticV2 {
                input_id: id,
                profile_version: expected.map_or_else(
                    || {
                        source
                            .as_ref()
                            .map(|(candidate, _)| candidate.profile_version)
                    },
                    |_| Some(PROFILE_V8),
                ),
                section_id,
                semantic_copy_id,
                fragment_index,
                replica_index: expected.map_or(ABSENT_U16, |row| row.replica_index),
                physical_replica_count: expected
                    .map_or(ABSENT_U16, |row| row.physical_replica_count),
                state,
                common_block_sha256: diagnostic_hash(state, source.as_ref()),
            }
        })
        .collect()
}

fn diagnostics_without_inventory(
    entries: &BTreeMap<u32, LaneInput>,
    local: &BTreeMap<u32, Vec<LocalCandidate>>,
    bootstrap_groups: &[GroupRecovery],
) -> Vec<FragmentDiagnosticV2> {
    let ids = entries
        .keys()
        .copied()
        .chain(1_u32..=5)
        .collect::<BTreeSet<_>>();
    ids.into_iter()
        .map(|id| {
            let source = foreign_or_local_candidate(local, id).and_then(|candidate| {
                decode_common_block(&candidate.common, candidate.profile_version)
                    .ok()
                    .map(|block| (candidate, block))
            });
            let route_lane = (1..=5).contains(&id);
            let route_lane_missing = route_lane && !entries.contains_key(&id);
            let lane = usize::try_from(id.saturating_sub(1)).ok();
            let state = if !entries.contains_key(&id) {
                FragmentState::Missing
            } else if local.get(&id).is_some_and(|rows| rows.len() > 1) {
                FragmentState::Ambiguous
            } else if route_lane
                && source
                    .as_ref()
                    .is_some_and(|(candidate, _)| candidate.profile_version != PROFILE_V8)
            {
                match source.as_ref().unwrap().0.quality {
                    DecodeQuality::Verified => FragmentState::Verified,
                    DecodeQuality::Recovered => FragmentState::Recovered,
                }
            } else if route_lane {
                bootstrap_groups
                    .first()
                    .and_then(|group| lane.and_then(|lane| group.lane_states.get(lane).copied()))
                    .unwrap_or(FragmentState::Corrupt)
            } else if let Some((candidate, _)) = source.as_ref() {
                match candidate.quality {
                    DecodeQuality::Verified => FragmentState::Verified,
                    DecodeQuality::Recovered => FragmentState::Recovered,
                }
            } else {
                FragmentState::Corrupt
            };
            let (profile_version, section_id, semantic_copy_id, fragment_index) = source
                .as_ref()
                .map(|(candidate, block)| {
                    (
                        Some(candidate.profile_version),
                        block.section_id,
                        block.semantic_copy_id,
                        block.fragment_index,
                    )
                })
                .unwrap_or_else(|| {
                    if route_lane_missing {
                        // Even without an inventory, the profile8 route fixes IDs
                        // 1..=5 as the five physical lanes of section 1,
                        // fragment 0.  Missing inputs therefore retain this
                        // known identity; corrupt present bytes do not acquire
                        // an identity that was never locally checked.
                        (Some(PROFILE_V8), 1, 0, 0)
                    } else {
                        (None, 0, ABSENT_U16, ABSENT_U16)
                    }
                });
            FragmentDiagnosticV2 {
                input_id: id,
                profile_version,
                section_id,
                semantic_copy_id,
                fragment_index,
                replica_index: if route_lane {
                    u16::try_from(id - 1).unwrap()
                } else {
                    ABSENT_U16
                },
                physical_replica_count: if route_lane { 5 } else { ABSENT_U16 },
                state,
                common_block_sha256: diagnostic_hash(state, source.as_ref()),
            }
        })
        .collect()
}

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
struct DiscoveredCopyKey {
    profile_version: u16,
    section_id: u32,
    semantic_copy_id: u16,
}

fn quality_witness(quality: DecodeQuality, common: [u8; 191]) -> FragmentWitness {
    FragmentWitness {
        raw_block: common,
        quality: match quality {
            DecodeQuality::Verified => RecoveryQuality::Verified,
            DecodeQuality::Recovered => RecoveryQuality::Recovered,
        },
    }
}

/// Reconstruct the exact candidate bytes before comparing the stored section
/// check.  This deliberately duplicates only the bounded structural half of
/// `assemble_semantic_copy`: it lets the resource ledger charge a complete,
/// width-consistent candidate immediately before the stored-check comparison.
fn structurally_complete_discovered_envelope(
    witnesses: &[FragmentWitness],
    profile_version: u16,
) -> Option<Vec<u8>> {
    if witnesses.is_empty() || witnesses.len() > MAX_BLOCKS_PER_COPY {
        return None;
    }
    let mut identity: Option<(u32, u16, u16, u16, u16, u32)> = None;
    let mut blocks = BTreeMap::<u16, crate::CommonBlock>::new();
    for witness in witnesses {
        let block = decode_common_block(&witness.raw_block, profile_version).ok()?;
        let current = (
            block.section_id,
            block.semantic_copy_id,
            block.section_type,
            block.section_version,
            block.fragment_count,
            block.section_envelope_length,
        );
        if identity.is_some_and(|value| value != current) {
            return None;
        }
        identity = Some(current);
        match blocks.get(&block.fragment_index) {
            Some(previous) if previous != &block => return None,
            Some(_) => {}
            None => {
                blocks.insert(block.fragment_index, block);
            }
        }
    }
    let (_, _, _, _, fragment_count, envelope_length) = identity?;
    if fragment_count == 0
        || usize::from(fragment_count) > MAX_BLOCKS_PER_COPY
        || blocks.len() != usize::from(fragment_count)
        || blocks.keys().copied().ne(0..fragment_count)
    {
        return None;
    }
    let envelope_length = usize::try_from(envelope_length).ok()?;
    let mut raw = Vec::with_capacity(envelope_length);
    for (_, block) in blocks {
        raw.extend_from_slice(&block.payload);
    }
    (raw.len() == envelope_length).then_some(raw)
}

fn discovered_sections_without_inventory(
    local: &BTreeMap<u32, Vec<LocalCandidate>>,
    bootstrap_groups: &[GroupRecovery],
    attempted_envelopes: &mut BTreeSet<Vec<u8>>,
    resource: &mut Budget,
) -> Result<Vec<SectionResult>> {
    let mut copies = BTreeMap::<DiscoveredCopyKey, Vec<FragmentWitness>>::new();
    for candidates in local.values() {
        let [candidate] = candidates.as_slice() else {
            continue;
        };
        let Ok(block) = decode_common_block(&candidate.common, candidate.profile_version) else {
            continue;
        };
        // Hierarchical section 1 needs its accepted REP5 representatives.
        // Legacy profiles still enter diagnostic assembly from their raw
        // section 1 lanes, even when the resulting copy is incomplete.
        if block.section_id == 1 && matches!(candidate.profile_version, 7 | 8) {
            continue;
        }
        copies
            .entry(DiscoveredCopyKey {
                profile_version: candidate.profile_version,
                section_id: block.section_id,
                semantic_copy_id: block.semantic_copy_id,
            })
            .or_default()
            .push(quality_witness(candidate.quality, candidate.common));
    }
    for group in bootstrap_groups {
        let Some(common) = group.common else {
            continue;
        };
        if !matches!(
            group.state,
            FragmentState::Verified | FragmentState::Recovered
        ) {
            continue;
        }
        copies
            .entry(DiscoveredCopyKey {
                profile_version: PROFILE_V8,
                section_id: 1,
                semantic_copy_id: 0,
            })
            .or_default()
            .push(quality_witness(
                if group.state == FragmentState::Verified {
                    DecodeQuality::Verified
                } else {
                    DecodeQuality::Recovered
                },
                common,
            ));
    }

    let mut by_section = BTreeMap::<u32, Vec<SectionWitness>>::new();
    for (key, witnesses) in copies {
        charge_witness_assembly(&witnesses, key.profile_version, resource)?;
        let Some(raw) = structurally_complete_discovered_envelope(&witnesses, key.profile_version)
        else {
            continue;
        };
        if !structurally_attemptable(&raw) {
            continue;
        }
        if attempted_envelopes.insert(raw.clone()) {
            charge_section_attempt(resource, &raw)?;
        }
        let Ok(witness) = assemble_semantic_copy(&witnesses, key.profile_version) else {
            continue;
        };
        if by_section.values().map(Vec::len).sum::<usize>() >= MAX_SECTION_CANDIDATES {
            return Err(DamageV2Error::ResourceLimit);
        }
        by_section.entry(key.section_id).or_default().push(witness);
    }

    let mut sections = Vec::with_capacity(by_section.len());
    for (section_id, witnesses) in by_section {
        match aggregate_section_witnesses(&witnesses) {
            Ok(section) => sections.push(SectionResult {
                section_id,
                state: if section.quality == RecoveryQuality::Verified {
                    SectionState::Verified
                } else {
                    SectionState::Recovered
                },
                envelope: Some(section.envelope),
            }),
            Err(error) if error.code == crate::RejectCode::Ambiguous => {
                sections.push(SectionResult {
                    section_id,
                    state: SectionState::Ambiguous,
                    envelope: None,
                });
            }
            Err(error) if error.code == crate::RejectCode::ResourceLimit => {
                return Err(DamageV2Error::ResourceLimit);
            }
            Err(_) => return Err(DamageV2Error::Reconstruction),
        }
    }
    Ok(sections)
}

fn recover_all_sections(
    inventory: &Inventory,
    groups: &[GroupRecovery],
    inventory_result: &SectionResult,
    resource: &mut Budget,
) -> Result<Vec<SectionResult>> {
    let mut by_section = BTreeMap::<u32, Vec<GroupRecovery>>::new();
    for group in groups {
        by_section
            .entry(group.identity.section_id)
            .or_default()
            .push(group.clone());
    }
    let mut sections = Vec::with_capacity(inventory.entries.len());
    for entry in &inventory.entries {
        if entry.section_id == 1 {
            sections.push(inventory_result.clone());
            continue;
        }
        let groups = by_section.remove(&entry.section_id).unwrap_or_default();
        if groups
            .iter()
            .any(|group| group.state == FragmentState::Ambiguous)
        {
            sections.push(SectionResult {
                section_id: entry.section_id,
                state: SectionState::Corrupt,
                envelope: None,
            });
            continue;
        }
        if let Some(result) = checked_section_from_groups(&groups, Some(inventory), resource)? {
            sections.push(result);
            continue;
        }
        let state = if groups
            .iter()
            .any(|group| group.state == FragmentState::Corrupt)
        {
            SectionState::Corrupt
        } else if groups.len()
            != usize::try_from(section_envelope_length(entry)?.div_ceil(COMMON_PAYLOAD_BYTES))
                .map_err(|_| DamageV2Error::ResourceLimit)?
            || groups
                .iter()
                .any(|group| group.state == FragmentState::Missing)
        {
            SectionState::Incomplete
        } else {
            SectionState::Corrupt
        };
        sections.push(SectionResult {
            section_id: entry.section_id,
            state,
            envelope: None,
        });
    }
    Ok(sections)
}

fn artifact_state(sections: &[SectionResult], inventory: &Inventory) -> ArtifactState {
    if sections
        .iter()
        .any(|section| section.state == SectionState::Ambiguous)
    {
        return ArtifactState::Ambiguous;
    }
    let states = sections
        .iter()
        .map(|row| (row.section_id, row.state))
        .collect::<BTreeMap<_, _>>();
    let required_unavailable = inventory.entries.iter().any(|entry| {
        entry.closure_class == CLOSURE_M2_REQUIRED
            && !states.get(&entry.section_id).is_some_and(|state| {
                matches!(state, SectionState::Verified | SectionState::Recovered)
            })
    });
    if required_unavailable {
        ArtifactState::Failure
    } else if inventory.entries.iter().any(|entry| {
        !states
            .get(&entry.section_id)
            .is_some_and(|state| matches!(state, SectionState::Verified | SectionState::Recovered))
    }) {
        ArtifactState::Degraded
    } else {
        ArtifactState::Exact
    }
}

fn recover_v8_inputs(
    entries: &BTreeMap<u32, LaneInput>,
    local: &BTreeMap<u32, Vec<LocalCandidate>>,
    resource: &mut Budget,
    package: Option<&RecipePackageV1>,
    expected_units: Option<usize>,
    accepted_hypotheses: Vec<AcceptedHypothesis>,
    context: Option<&crate::route_semantics_v2::ContextCommitments>,
) -> Result<RecoveryResultV2> {
    let bootstrap_groups = bootstrap_inventory_groups(&entries, resource)?;
    let bootstrap_count = bootstrap_groups
        .iter()
        .filter(|g| g.common.is_some())
        .count() as u64;
    let bootstrap_len = bootstrap_groups
        .first()
        .map_or(0, |g| u64::from(g.identity.section_envelope_length));
    if bootstrap_count != 0 && bootstrap_groups.iter().all(|g| g.common.is_some()) {
        resource.event(
            Kernel::SectionAssembly,
            191 * bootstrap_count,
            bootstrap_len + 24 * bootstrap_count,
        )?;
    }
    let bootstrap_attempt =
        assemble_raw_fragment_bytes(&bootstrap_groups).filter(|raw| structurally_attemptable(raw));
    let inventory_section = checked_section_after_assembly(&bootstrap_groups, None, resource)?;
    let inventory = if let Some(section) = inventory_section
        .as_ref()
        .and_then(|s| s.envelope.as_ref())
        .and_then(|raw| decode_section(raw).ok())
    {
        resource.event(
            Kernel::Inventory,
            section.payload.len() as u64,
            16 * section.payload.len() as u64,
        )?;
        let parsed = decode_inventory(&section.payload).ok();
        resource.retain("path:inventory", 16 * section.payload.len() as u64)?;
        parsed
    } else {
        None
    };
    let inventory = inventory.filter(|inventory| {
        inventory_layout(inventory).is_ok_and(|layout| {
            layout.len() <= 2389 && expected_units.is_none_or(|count| count == layout.len())
        })
    });
    let Some(inventory) = inventory else {
        let active_local: BTreeMap<_, _> = local
            .iter()
            .filter_map(|(id, rows)| {
                let rows = rows
                    .iter()
                    .filter(|r| r.profile_version == 8)
                    .cloned()
                    .collect::<Vec<_>>();
                (!rows.is_empty()).then_some((*id, rows))
            })
            .collect();
        let mut attempted_envelopes = bootstrap_attempt.into_iter().collect::<BTreeSet<_>>();
        let mut sections = discovered_sections_without_inventory(
            &active_local,
            &bootstrap_groups,
            &mut attempted_envelopes,
            resource,
        )?;
        if !sections.iter().any(|section| section.section_id == 1) {
            let state = if bootstrap_groups.iter().any(|group| {
                matches!(
                    group.state,
                    FragmentState::Corrupt | FragmentState::Ambiguous
                )
            }) {
                SectionState::Corrupt
            } else if bootstrap_groups
                .iter()
                .any(|group| group.state == FragmentState::Missing)
            {
                SectionState::Incomplete
            } else {
                // Every fragment was locally recoverable, so failure to
                // establish a checked inventory is a semantic/check failure.
                SectionState::Corrupt
            };
            sections.push(SectionResult {
                section_id: 1,
                state,
                envelope: None,
            });
        }
        sections.sort_by_key(|section| section.section_id);
        let artifact_state = if sections
            .iter()
            .any(|section| section.state == SectionState::Ambiguous)
        {
            ArtifactState::Ambiguous
        } else {
            ArtifactState::Failure
        };
        return Ok(RecoveryResultV2 {
            profile_version: None,
            inventory_established: false,
            resource: resource.value,
            artifact_state,
            sections,
            fragments: diagnostics_without_inventory(&entries, &local, &bootstrap_groups),
            accepted_hypotheses,
            required: None,
            all: None,
            context_proof: None,
            context_witnesses: vec![],
            adapter: ReferenceLedger::default(),
            observation_binding: None,
        });
    };
    let inventory_result = checked_section_from_groups(&bootstrap_groups, None, resource)?
        .ok_or(DamageV2Error::Reconstruction)?;
    let layout = inventory_layout(&inventory)?;
    if layout.len() > 2_389 || layout.keys().next_back().copied().unwrap_or(0) > 2_389 {
        return Err(DamageV2Error::Reconstruction);
    }
    if expected_units.is_some_and(|count| count != layout.len()) {
        return Err(DamageV2Error::Reconstruction);
    }
    charge_layout(&inventory, layout.len() as u64, resource)?;
    let mut groups = bootstrap_groups;
    groups.extend(groups_from_layout(&entries, &layout, resource)?);
    let sections = recover_all_sections(&inventory, &groups, &inventory_result, resource)?;
    let mut result = RecoveryResultV2 {
        profile_version: Some(PROFILE_V8),
        inventory_established: true,
        resource: resource.value,
        artifact_state: artifact_state(&sections, &inventory),
        sections,
        fragments: diagnostics_with_layout(&entries, &local, &layout, &groups),
        accepted_hypotheses,
        required: None,
        all: None,
        context_proof: None,
        context_witnesses: vec![],
        adapter: ReferenceLedger::default(),
        observation_binding: None,
    };
    hydrate_streams(&mut result, package, resource, context)?;
    result.resource = resource.value;
    if result.required.is_none() {
        result.artifact_state = ArtifactState::Failure;
    } else if result.all.is_none() && result.artifact_state == ArtifactState::Exact {
        result.artifact_state = ArtifactState::Degraded;
    }
    Ok(result)
}

fn decoded_body(
    package: Option<&RecipePackageV1>,
    version: u16,
    payload: &[u8],
    budget: &mut Budget,
) -> Result<Option<Vec<u8>>> {
    if payload.len() > 16384 {
        return Ok(None);
    };
    budget.event(
        Kernel::BodyAdapter,
        payload.len() as u64,
        payload.len() as u64 + 32768,
    )?;
    if version == 0 {
        return Ok(Some(payload.to_vec()));
    }
    if version != 1 {
        return Ok(None);
    };
    if let Some(package) = package {
        let w = crate::resources_v2::program_workspace(&package.encoded)
            .map_err(|_| DamageV2Error::ResourceLimit)?;
        let nodes = u32::from_be_bytes(package.encoded[20..24].try_into().unwrap()) as u64;
        budget.event(Kernel::ProgramRefinement, nodes, w.refinement())?;
    }
    let (steps, scratch) = if let Some(package) = package {
        (
            package
                .logical
                .recipe_primitive_steps(202)
                .ok_or(DamageV2Error::Reconstruction)?,
            package
                .logical
                .recipe_peak_scratch_bytes(202)
                .ok_or(DamageV2Error::Reconstruction)?,
        )
    } else {
        (2375776, 98394)
    };
    checked_charge(budget, steps, 1, scratch.max(49152))?;
    let mut buffer = vec![0; 16384];
    buffer[..payload.len()].copy_from_slice(payload);
    let output = if package.is_none_or(crate::route_receiver_v2::body_refines) {
        crate::route_receiver_v2::native_body_output(&buffer, payload.len() as u16)
    } else {
        buffer.extend((payload.len() as u16).to_be_bytes());
        match evaluate_serialized_recipe_v1(package.unwrap(), 202, &buffer) {
            Ok(value) => value,
            Err(_) => return Ok(None),
        }
    };
    if output.len() != 16388 || output[..2] != [0, 0] {
        return Ok(None);
    };
    let length = usize::from(u16::from_be_bytes([output[2], output[3]]));
    if length > 16384 || output[4 + length..].iter().any(|v| *v != 0) {
        return Ok(None);
    };
    Ok(Some(output[4..4 + length].to_vec()))
}
// Transport framing defers ROOT chess/content controls to the full content validator.
// Historical decode_tier_frame remains strict and unchanged.
fn tier_transport_frame(raw: &[u8], id: u32) -> Option<crate::TierFrame> {
    if raw.len() < 27 || raw.len() > MAX_ENVELOPE_BYTES {
        return None;
    }
    let r16 = |at| u16::from_be_bytes(raw[at..at + 2].try_into().unwrap());
    let r32 = |at| u32::from_be_bytes(raw[at..at + 4].try_into().unwrap());
    let count = usize::from(r16(4));
    let bytes = r32(8);
    let records = r16(12);
    let root = r32(14) as usize;
    if r16(0) != 0
        || raw[3] != 0
        || r16(6) != 0
        || !matches!((id, raw[2]), (2, 0) | (3, 1))
        || count == 0
        || count > crate::MAX_TIER_BODY_IDS
        || bytes == 0
        || bytes as usize > MAX_ENVELOPE_BYTES
        || records < 2
        || root != 12
        || r16(18) != 0
        || r16(20) != records
    {
        return None;
    }
    let end = 22 + 4 * count;
    if end.checked_add(root) != Some(raw.len()) {
        return None;
    }
    let ids = raw[22..end]
        .chunks_exact(4)
        .map(|b| u32::from_be_bytes(b.try_into().unwrap()))
        .collect::<Vec<_>>();
    if ids.first() == Some(&0) || ids.windows(2).any(|p| p[0] >= p[1]) {
        return None;
    }
    let root = &raw[end..];
    if root[..2] == [0, 0] || root[2..4] != [0, 14] || root[4..8] != [0, 0, 0, 4] {
        return None;
    }
    Some(crate::TierFrame {
        tier_id: raw[2],
        body_section_ids: ids,
        assembled_stream_byte_length: bytes,
        assembled_record_count: records,
        root_record_bytes: root.to_vec(),
    })
}
fn assemble_for_content_validation(
    tier: &crate::TierFrame,
    bodies: &BTreeMap<u32, Vec<u8>>,
) -> Option<Vec<u8>> {
    let mut length = 4usize;
    let mut count = 1usize;
    let mut prior = 0u16;
    for id in &tier.body_section_ids {
        let body = bodies.get(id)?;
        if body.is_empty() {
            return None;
        }
        length = length.checked_add(body.len())?;
        if length > MAX_ENVELOPE_BYTES {
            return None;
        }
        let mut at = 0usize;
        while at < body.len() {
            let frame = body.get(at..at + 8)?;
            let id = u16::from_be_bytes([frame[0], frame[1]]);
            if id <= prior {
                return None;
            }
            prior = id;
            let len = u32::from_be_bytes(frame[4..8].try_into().unwrap()) as usize;
            at = at.checked_add(8)?.checked_add(len)?;
            if at > body.len() {
                return None;
            }
            count += 1;
            if count > 65535 {
                return None;
            }
        }
    }
    length = length.checked_add(tier.root_record_bytes.len())?;
    let rootid = u16::from_be_bytes(tier.root_record_bytes[..2].try_into().ok()?);
    if length > MAX_ENVELOPE_BYTES
        || length != tier.assembled_stream_byte_length as usize
        || count != usize::from(tier.assembled_record_count)
        || rootid <= prior
    {
        return None;
    }
    let mut raw = Vec::with_capacity(length);
    raw.extend(0u16.to_be_bytes());
    raw.extend(tier.assembled_record_count.to_be_bytes());
    for id in &tier.body_section_ids {
        raw.extend(&bodies[id]);
    }
    raw.extend(&tier.root_record_bytes);
    Some(raw)
}
fn assemble_tier(
    id: u32,
    checked: &BTreeMap<u32, SectionEnvelope>,
    decoded: &mut BTreeMap<u32, Vec<u8>>,
    package: Option<&RecipePackageV1>,
    budget: &mut Budget,
) -> Result<Option<Vec<u8>>> {
    let Some(envelope) = checked.get(&id) else {
        return Ok(None);
    };
    let Some(tier) = tier_transport_frame(&envelope.payload, id) else {
        return Ok(None);
    };
    if tier.body_section_ids != envelope.dependencies {
        return Ok(None);
    };
    let mut bodies = BTreeMap::new();
    for id in &tier.body_section_ids {
        let Some(body) = checked.get(id) else {
            return Ok(None);
        };
        if !decoded.contains_key(id) {
            let Some(raw) = decoded_body(package, body.section_version, &body.payload, budget)?
            else {
                return Ok(None);
            };
            budget.retain(&format!("path:body:{id}"), raw.len() as u64 + 8)?;
            decoded.insert(*id, raw);
        }
        bodies.insert(*id, decoded[id].clone());
    }
    let b = u64::from(tier.assembled_stream_byte_length);
    let r = u64::from(tier.assembled_record_count);
    let initial = crate::resources_v2::content_workspace(b, r, 0)
        .map_err(|_| DamageV2Error::ResourceLimit)?;
    budget.event(Kernel::ContentValidation, b, initial)?;
    let Some(raw) = assemble_for_content_validation(&tier, &bodies) else {
        return Ok(None);
    };
    let full = crate::resources_v2::content_workspace(b, r, content_aliases(&raw))
        .map_err(|_| DamageV2Error::ResourceLimit)?;
    budget
        .adapter
        .raise_workspace(Kernel::ContentValidation, full)
        .map_err(|_| DamageV2Error::ResourceLimit)?;
    if gb_content::stream_validation(&raw).is_err() {
        budget.adapter.release(&format!("path:stream:{id}"));
        return Ok(None);
    }
    budget.retain(&format!("path:stream:{id}"), raw.len() as u64)?;
    Ok(Some(raw))
}
fn hydrate_streams(
    result: &mut RecoveryResultV2,
    package: Option<&RecipePackageV1>,
    budget: &mut Budget,
    context: Option<&crate::route_semantics_v2::ContextCommitments>,
) -> Result<()> {
    if !result.inventory_established {
        return Ok(());
    };
    let checked = result
        .sections
        .iter()
        .filter_map(|row| row.envelope.as_ref())
        .filter_map(|raw| decode_section(raw).ok())
        .map(|row| (row.section_id, row))
        .collect::<BTreeMap<_, _>>();
    let mut decoded = BTreeMap::new();
    result.required = assemble_tier(2, &checked, &mut decoded, package, budget)?;
    if result.required.is_some() {
        result.all = assemble_tier(3, &checked, &mut decoded, package, budget)?;
    }
    result.context_proof = context
        .map(|c| c.prove_recovered(result.required.as_deref(), result.all.as_deref(), &decoded));
    Ok(())
}
fn verify_owners() -> Result<()> {
    static VERIFIED: std::sync::OnceLock<Result<()>> = std::sync::OnceLock::new();
    *VERIFIED.get_or_init(|| {
        for (raw, expected) in [
            (
                &include_bytes!("../../../spec/profile-policy-v2.toml")[..],
                "a8b05a0fea0149d39feb219f7aca9f1ba661b3e1c5f78283f0fa38f8bc0398f5",
            ),
            (
                &include_bytes!("../../../spec/damage-policy-v2.toml")[..],
                "e898f1b80f998e2d3b9830c2fe0a0899f101c761d645760585740b19dc7301fb",
            ),
            (
                &include_bytes!("../../../spec/profile-limits-v2.toml")[..],
                "c7a7a6fa0a5094796135603174e56809e30e03484b9384b6a0877e83f33833a7",
            ),
        ] {
            if raw.len() > 65536 || format!("{:x}", Sha256::digest(raw)) != expected {
                return Err(DamageV2Error::Owner);
            }
        }
        fn doc(raw: &[u8], schema: &str) -> Result<toml::Value> {
            if raw.len() > 65536 {
                return Err(DamageV2Error::Owner);
            }
            let text = std::str::from_utf8(raw).map_err(|_| DamageV2Error::Owner)?;
            let value: toml::Value = toml::from_str(text).map_err(|_| DamageV2Error::Owner)?;
            if value.get("schema").and_then(toml::Value::as_str) != Some(schema)
                || value
                    .get("policy_version")
                    .and_then(toml::Value::as_integer)
                    != Some(2)
                || value.get("status").and_then(toml::Value::as_str) != Some("development")
            {
                return Err(DamageV2Error::Owner);
            }
            Ok(value)
        }
        let profile = doc(
            include_bytes!("../../../spec/profile-policy-v2.toml"),
            "golden-board.profile-policy/v2",
        )?;
        let damage = doc(
            include_bytes!("../../../spec/damage-policy-v2.toml"),
            "golden-board.damage-policy/v2",
        )?;
        let limits = doc(
            include_bytes!("../../../spec/profile-limits-v2.toml"),
            "golden-board.profile-limits/v2",
        )?;
        let number = |value: &toml::Value, table: &str, key: &str| {
            value
                .get(table)
                .and_then(|v| v.get(key))
                .and_then(toml::Value::as_integer)
        };
        for (table, key, wanted) in [
            ("candidate", "profile_version", 8),
            ("candidate", "inventory_version", 2),
            ("candidate", "route_version", 2),
            ("candidate", "protected_unit_bytes", 216),
            ("geometry", "raw_bits_max", 4194304),
            ("storage", "stored_payload_bytes_max", 16384),
            ("storage", "dependency_count_max", 4095),
        ] {
            if number(&profile, table, key) != Some(wanted) {
                return Err(DamageV2Error::Owner);
            }
        }
        for (key, wanted) in [
            ("physical_units", 2389),
            ("dependency_count_per_section", 4095),
            ("raw_bits", 4194304),
            ("side", 2048),
            ("section_attempts", 4096),
            ("recipe_package_bytes", 1048576),
            ("recipe_primitive_steps", 268435456),
            ("recipe_scratch_bytes", 16777216),
            ("output_bytes", 1048576),
            ("counter_bits", 64),
        ] {
            if number(&limits, "policy_ceiling", key) != Some(wanted) {
                return Err(DamageV2Error::Owner);
            }
        }
        if limits
            .get("pending")
            .and_then(|v| v.get("production_admission"))
            .and_then(toml::Value::as_bool)
            != Some(false)
        {
            return Err(DamageV2Error::Owner);
        }
        let order = damage
            .get("decoder")
            .and_then(|v| v.get("registry_profile_order"))
            .and_then(toml::Value::as_array)
            .ok_or(DamageV2Error::Owner)?;
        if order
            .iter()
            .map(toml::Value::as_integer)
            .ne([8, 2, 3, 4, 5, 6, 7].into_iter().map(Some))
        {
            return Err(DamageV2Error::Owner);
        }
        let rows = damage
            .get("program_resource")
            .and_then(toml::Value::as_array)
            .ok_or(DamageV2Error::Owner)?;
        if rows.len() != 10 {
            return Err(DamageV2Error::Owner);
        }
        let mut ids = BTreeSet::new();
        for row in rows {
            let id = row
                .get("recipe_id")
                .and_then(toml::Value::as_integer)
                .ok_or(DamageV2Error::Owner)?;
            let profile = row
                .get("profile_version")
                .and_then(toml::Value::as_integer)
                .ok_or(DamageV2Error::Owner)?;
            let expected = match (profile, id) {
                (8 | 2 | 3 | 4 | 7, 30) => (80435, 4613),
                (5 | 6, 30) => (1698049, 7688),
                (8 | 7, 113) => (24, 10),
                (8, 202) => (2375776, 98394),
                _ => return Err(DamageV2Error::Owner),
            };
            if !ids.insert((profile, id))
                || row.get("primitive_steps").and_then(toml::Value::as_integer) != Some(expected.0)
                || row
                    .get("peak_scratch_bytes")
                    .and_then(toml::Value::as_integer)
                    != Some(expected.1)
            {
                return Err(DamageV2Error::Owner);
            }
        }
        Ok(())
    })
}
fn units_core(raw: &[u8], budget: &mut Budget) -> Result<RecoveryResultV2> {
    if raw.len() > 4194306 {
        return Err(DamageV2Error::ResourceLimit);
    }
    if raw.len() >= 4 && u32::from_be_bytes(raw[..4].try_into().unwrap()) > 2389 {
        return Err(DamageV2Error::ResourceLimit);
    }
    let units = ObsUnits::parse(raw).map_err(|_| DamageV2Error::Observation)?;
    if units
        .entries
        .iter()
        .any(|entry| !(1..=255).contains(&entry.bytes.len()))
    {
        return Err(DamageV2Error::Observation);
    }
    let pool = units
        .entries
        .iter()
        .map(|e| 8 + 2 * e.bytes.len() as u64 + 7 * 199)
        .sum();
    budget.retain("observation:units", pool)?;
    let local = decode_local_candidates(&units, budget)?;
    let entries: BTreeMap<u32, LaneInput> = units
        .entries
        .iter()
        .map(|entry| {
            (
                entry.physical_unit_id,
                LaneInput {
                    present: true,
                    observation: (entry.bytes.len() == 216).then(|| EhObservation {
                        encoded: entry.bytes.as_slice().try_into().unwrap(),
                        erasures: vec![],
                    }),
                },
            )
        })
        .collect();
    let mut result = recover_v8_inputs(&entries, &local, budget, None, None, vec![], None)?;
    if result.inventory_established {
        select_result(&result, 0, budget)?;
    }
    budget.adapter.release_prefix("path:");
    for version in 2..=6 {
        let commons = local
            .values()
            .flatten()
            .filter(|r| r.profile_version == version)
            .map(|r| r.common)
            .collect::<Vec<_>>();
        foreign_legacy_checks(&commons, version, budget)?;
        budget.adapter.release_prefix("path:");
    }
    let foreign_inputs = entries
        .iter()
        .map(|(id, row)| (*id, row.observation.clone()))
        .collect();
    let commons = local
        .values()
        .flatten()
        .filter(|r| r.profile_version == 7)
        .map(|r| r.common)
        .collect();
    foreign_hierarchical_checks(&foreign_inputs, commons, None, budget)?;
    budget.adapter.release_prefix("path:");
    if !result.inventory_established {
        let groups = bootstrap_inventory_groups(&entries, budget)?;
        let mut sections =
            discovered_sections_without_inventory(&local, &groups, &mut BTreeSet::new(), budget)?;
        if !sections.iter().any(|r| r.section_id == 1) {
            if let Some(inventory) = result.sections.iter().find(|r| r.section_id == 1) {
                sections.push(inventory.clone());
            }
        }
        sections.sort_by_key(|r| r.section_id);
        result.sections = sections;
        result.fragments = diagnostics_without_inventory(&entries, &local, &groups);
        result.artifact_state = if result
            .sections
            .iter()
            .any(|r| r.state == SectionState::Ambiguous)
        {
            ArtifactState::Ambiguous
        } else {
            ArtifactState::Failure
        };
    }
    if !result.inventory_established {
        select_result(&result, 0, budget)?;
    }
    budget.adapter.release_prefix("path:");
    result.resource = budget.value;
    Ok(result)
}
fn route_error(error: RouteError) -> DamageV2Error {
    match error {
        RouteError::ResourceLimit => DamageV2Error::ResourceLimit,
        RouteError::Observation => DamageV2Error::Observation,
    }
}
fn transformed(matrix: &ObsMatrix, transform: u8, polarity: u8) -> ObsMatrix {
    let side = matrix.side;
    let last = side - 1;
    let mut values = Vec::with_capacity(matrix.values.len());
    for row in 0..side {
        for col in 0..side {
            let (r, c) = match transform {
                0 => (row, col),
                1 => (last - col, row),
                2 => (last - row, last - col),
                3 => (col, last - row),
                4 => (row, last - col),
                5 => (last - col, last - row),
                6 => (last - row, col),
                _ => (col, row),
            };
            let bit = matrix.values[r * side + c];
            values.push(if bit < 2 { bit ^ polarity } else { 2 });
        }
    }
    ObsMatrix { side, values }
}
fn extract_inputs(
    matrix: &ObsMatrix,
    route: &ObservedRoute,
    budget: &mut Budget,
) -> Result<(BTreeMap<u32, LaneInput>, BTreeMap<u32, Vec<LocalCandidate>>)> {
    let map = route.mapping();
    let inner = usize::from(map.interior_side());
    let width = usize::from(map.shell_width());
    let mut entries = BTreeMap::new();
    let mut local = BTreeMap::new();
    let q = map.unit_slot_count();
    budget.event(Kernel::UnitExtraction, q * 1728, q * (8 + 2 * 216))?;
    budget.retain("path:units", q * (8 + 2 * 216 + 199))?;
    for unit in 1..=q {
        budget.event(Kernel::LaneAdapter, 216, 216 + 191)?;
        charge_registry_lane(budget, 8)?;
        budget.event(Kernel::CommonFrame, 191, 191)?;
        let mut encoded = [0u8; 216];
        let mut erasures = Vec::new();
        for bit in 0..1728u16 {
            let flat = map
                .forward(unit, bit)
                .map_err(|_| DamageV2Error::Reconstruction)? as usize;
            let value = matrix.values[(flat / inner + width) * matrix.side + flat % inner + width];
            if value == 2 {
                erasures.push(EhErasure {
                    codeword: (bit / 72) as u8,
                    position: (bit % 72 + 1) as u8,
                });
            } else {
                encoded[usize::from(bit) / 8] |= value << (7 - bit % 8);
            }
        }
        let observation = EhObservation { encoded, erasures };
        if let Ok(decoded) = decode_eh_unit(&observation, 8) {
            local.insert(
                unit as u32,
                vec![LocalCandidate {
                    profile_version: 8,
                    common: decoded.common,
                    quality: decoded.quality,
                }],
            );
        }
        entries.insert(
            unit as u32,
            LaneInput {
                present: true,
                observation: Some(observation),
            },
        );
    }
    Ok((entries, local))
}
enum ObservedPath {
    Active(ObservedRoute),
    Legacy(crate::damage::ParsedRoute),
    Hierarchical(crate::damage_v1::ParsedRouteV1),
}
impl ObservedPath {
    fn order(&self) -> (u16, u16, u8) {
        match self {
            Self::Active(r) => (0, r.width(), r.sector()),
            Self::Legacy(r) => (r.profile_version, r.width, r.sector),
            Self::Hierarchical(r) => (7, r.width, r.sector),
        }
    }
}
fn discover_paths(matrix: &ObsMatrix, budget: &mut Budget) -> Result<Vec<ObservedPath>> {
    let mut paths = vec![];
    let maximum = 128.min(matrix.side.saturating_sub(8) / 2);
    for width in (8..=maximum).step_by(8) {
        for sector in 0..4 {
            budget.event(Kernel::ShellRead, 512, 64)?;
            budget.retain("route:header", 64)?;
            if let Some(r) = crate::route_receiver_v2::discover_route_at(
                matrix,
                width,
                sector,
                &mut budget.value,
                &mut budget.adapter,
            )
            .map_err(route_error)?
            {
                paths.push(ObservedPath::Active(r));
            }
            match crate::damage::parse_sector_route_v2(
                matrix,
                width,
                sector,
                &mut budget.value,
                &mut budget.adapter,
            ) {
                Ok(Some(r)) => paths.push(ObservedPath::Legacy(r)),
                Err(crate::damage::DamageError::ResourceLimit) => {
                    return Err(DamageV2Error::ResourceLimit);
                }
                _ => {}
            }
            match crate::damage_v1::parse_sector_route_v2(
                matrix,
                width,
                sector,
                &mut budget.value,
                &mut budget.adapter,
            ) {
                Ok(Some(r)) => paths.push(ObservedPath::Hierarchical(r)),
                Err(crate::damage_v1::DamageV1Error::ResourceLimit) => {
                    return Err(DamageV2Error::ResourceLimit);
                }
                _ => {}
            }
            budget.adapter.release_prefix("route:");
            budget.retain("view:routes", 128 * paths.len() as u64)?;
        }
    }
    paths.sort_by_key(ObservedPath::order);
    Ok(paths)
}
fn charge_observed(
    budget: &mut Budget,
    package: &crate::recipe::RecipePackage,
    id: u16,
    count: u64,
) -> Result<()> {
    checked_charge(
        budget,
        package
            .recipe_primitive_steps(id)
            .ok_or(DamageV2Error::Reconstruction)?,
        count,
        package
            .recipe_peak_scratch_bytes(id)
            .ok_or(DamageV2Error::Reconstruction)?,
    )
}
fn charge_witness_assembly(
    witnesses: &[FragmentWitness],
    profile: u16,
    budget: &mut Budget,
) -> Result<()> {
    let length = structurally_complete_discovered_envelope(witnesses, profile)
        .map_or(0, |raw| raw.len() as u64);
    budget.event(
        Kernel::SectionAssembly,
        191 * witnesses.len() as u64,
        length + 24 * witnesses.len() as u64,
    )
}
fn charge_layout(inventory: &Inventory, q: u64, budget: &mut Budget) -> Result<()> {
    let i = inventory.entries.len() as u64;
    let edges = inventory
        .entries
        .iter()
        .map(|e| e.dependencies.len() as u64)
        .sum::<u64>();
    let layout = 128 * q + 64 * i;
    budget.event(Kernel::GroupLayout, q, layout)?;
    budget.retain("path:layout", layout + 8 * edges)?;
    budget.event(Kernel::DependencyClosure, edges, 24 * i + 8 * edges)
}
fn result_footprint(result: &RecoveryResultV2) -> u64 {
    48 * result.sections.len() as u64
        + 40 * result.fragments.len() as u64
        + 48 * result.accepted_hypotheses.len() as u64
        + result
            .sections
            .iter()
            .filter_map(|s| s.envelope.as_ref())
            .map(|v| v.len() as u64)
            .sum::<u64>()
        + 191
            * result
                .fragments
                .iter()
                .filter(|r| r.common_block_sha256 != ZERO_SHA256)
                .count() as u64
        + result.required.as_ref().map_or(0, |v| v.len() as u64)
        + result.all.as_ref().map_or(0, |v| v.len() as u64)
}
fn select_result(result: &RecoveryResultV2, prior: usize, budget: &mut Budget) -> Result<()> {
    let bytes = result_footprint(result);
    budget.event(
        Kernel::ResultSelection,
        bytes
            .checked_mul(prior.max(1) as u64)
            .ok_or(DamageV2Error::ResourceLimit)?,
        bytes,
    )?;
    // The stream spans transfer to the immutable result rather than duplicate.
    budget.adapter.release_prefix("path:stream:");
    budget.retain(&format!("result:{prior}"), bytes)
}
fn content_aliases(raw: &[u8]) -> u64 {
    use gb_foundation::constants::{CONTENT_KIND_LESSON_NODE, CONTENT_KIND_REGION_SET};
    if raw.len() < 4 {
        return 0;
    }
    let count = u16::from_be_bytes([raw[2], raw[3]]) as usize;
    let mut cursor = 4usize;
    let mut sets = BTreeMap::new();
    let mut lessons = Vec::new();
    for _ in 0..count {
        let Some(frame) = raw.get(cursor..cursor + 8) else {
            return 0;
        };
        let id = u16::from_be_bytes([frame[0], frame[1]]);
        let kind = u16::from_be_bytes([frame[2], frame[3]]);
        let len = u32::from_be_bytes(frame[4..8].try_into().unwrap()) as usize;
        let Some(end) = cursor.checked_add(8).and_then(|v| v.checked_add(len)) else {
            return 0;
        };
        let Some(payload) = raw.get(cursor + 8..end) else {
            return 0;
        };
        if kind == CONTENT_KIND_REGION_SET && payload.len() >= 4 {
            sets.insert(
                id,
                u16::from_be_bytes([payload[2], payload[3]]).min(4096) as u64,
            );
        }
        if kind == CONTENT_KIND_LESSON_NODE && payload.len() >= 8 && lessons.len() < 4096 {
            lessons.push(u16::from_be_bytes([payload[6], payload[7]]));
        }
        cursor = end;
    }
    if cursor != raw.len() {
        return 0;
    }
    lessons
        .iter()
        .map(|id| sets.get(id).copied().unwrap_or(0))
        .sum()
}
fn foreign_legacy_checks(common: &[[u8; 191]], version: u16, budget: &mut Budget) -> Result<()> {
    let mut copies = BTreeMap::<(u32, u16), Vec<FragmentWitness>>::new();
    for bytes in common {
        if let Ok(block) = decode_common_block(bytes, version) {
            copies
                .entry((block.section_id, block.semantic_copy_id))
                .or_default()
                .push(quality_witness(DecodeQuality::Recovered, *bytes));
        }
    }
    let mut inventories = BTreeSet::new();
    for ((id, _), witnesses) in &copies {
        if *id != 1 {
            continue;
        }
        charge_witness_assembly(witnesses, version, budget)?;
        if let Some(raw) = structurally_complete_discovered_envelope(witnesses, version) {
            if structurally_attemptable(&raw) {
                charge_section_attempt(budget, &raw)?;
                if decode_section(&raw).is_ok() {
                    inventories.insert(raw);
                }
            }
        }
    }
    let inventory = if inventories.len() == 1 {
        let section = decode_section(inventories.first().unwrap())
            .map_err(|_| DamageV2Error::Reconstruction)?;
        budget.event(
            Kernel::Inventory,
            section.payload.len() as u64,
            16 * section.payload.len() as u64,
        )?;
        let value = crate::decode_inventory(&section.payload)
            .ok()
            .filter(|i| i.inventory_version == 0);
        budget.retain("path:inventory", 16 * section.payload.len() as u64)?;
        value
    } else {
        None
    };
    if let Some(inventory) = inventory {
        let q = inventory
            .entries
            .iter()
            .map(|e| {
                section_envelope_length(e).map(|n| n.div_ceil(157) as u64 * u64::from(e.copy_count))
            })
            .collect::<Result<Vec<_>>>()?
            .iter()
            .sum();
        charge_layout(&inventory, q, budget)?;
        for entry in &inventory.entries {
            for copy in 0..u16::from(entry.copy_count) {
                if let Some(witnesses) = copies.get(&(entry.section_id, copy)) {
                    charge_witness_assembly(witnesses, version, budget)?;
                    if let Some(raw) = structurally_complete_discovered_envelope(witnesses, version)
                    {
                        if structurally_attemptable(&raw) {
                            charge_section_attempt(budget, &raw)?;
                            let _ = decode_section(&raw);
                        }
                    }
                }
            }
        }
    } else {
        foreign_sections(common, version, budget)?;
    }
    Ok(())
}
fn foreign_sections(
    common: &[[u8; 191]],
    version: u16,
    budget: &mut Budget,
) -> Result<BTreeMap<u32, Vec<u8>>> {
    let mut copies = BTreeMap::<(u32, u16), Vec<FragmentWitness>>::new();
    for common in common {
        if let Ok(block) = decode_common_block(common, version) {
            copies
                .entry((block.section_id, block.semantic_copy_id))
                .or_default()
                .push(quality_witness(DecodeQuality::Recovered, *common));
        }
    }
    let mut checked = BTreeMap::new();
    for ((id, _), witnesses) in copies {
        charge_witness_assembly(&witnesses, version, budget)?;
        if let Some(raw) = structurally_complete_discovered_envelope(&witnesses, version) {
            if structurally_attemptable(&raw) {
                charge_section_attempt(budget, &raw)?;
                if assemble_semantic_copy(&witnesses, version).is_ok() {
                    checked.insert(id, raw);
                }
            }
        }
    }
    Ok(checked)
}
fn foreign_group(
    inputs: &BTreeMap<u32, Option<EhObservation>>,
    first: u32,
    factor: u8,
    package: Option<&crate::recipe::RecipePackage>,
    budget: &mut Budget,
    cache: &mut BTreeMap<(u32, u8), Option<[u8; 191]>>,
) -> Result<Option<[u8; 191]>> {
    if let Some(value) = cache.get(&(first, factor)) {
        return Ok(*value);
    }
    let observations = (0..u32::from(factor))
        .map(|i| inputs.get(&(first + i)).cloned().flatten())
        .collect::<Vec<_>>();
    charge_group_once(
        budget,
        7,
        (0..u32::from(factor))
            .map(|i| inputs.contains_key(&(first + i)).then_some(first + i))
            .collect(),
        package,
    )?;
    let value = diagnose_hierarchical(
        crate::candidate::profile_by_version(7).unwrap(),
        &observations,
    )
    .map_err(|_| DamageV2Error::Reconstruction)?
    .common;
    cache.insert((first, factor), value);
    Ok(value)
}
fn foreign_hierarchical_checks(
    inputs: &BTreeMap<u32, Option<EhObservation>>,
    mut commons: Vec<[u8; 191]>,
    package: Option<&crate::recipe::RecipePackage>,
    budget: &mut Budget,
) -> Result<()> {
    let mut cache = BTreeMap::new();
    let mut bootstrap = vec![];
    if let Some(first) = foreign_group(&inputs, 1, 5, package, budget, &mut cache)? {
        if let Ok(block) = decode_common_block(&first, 7) {
            if block.section_id == 1
                && block.section_type == 1
                && block.section_version == 1
                && block.fragment_index == 0
                && block.semantic_copy_id == 0
                && usize::from(block.fragment_count) * 5 <= 2389
            {
                bootstrap.push(first);
                for f in 1..u32::from(block.fragment_count) {
                    if let Some(common) =
                        foreign_group(&inputs, 1 + 5 * f, 5, package, budget, &mut cache)?
                    {
                        bootstrap.push(common);
                    }
                }
            }
        }
    }
    let checked = foreign_sections(&bootstrap, 7, budget)?;
    let inventory = if let Some(section) = checked.get(&1).and_then(|raw| decode_section(raw).ok())
    {
        budget.event(
            Kernel::Inventory,
            section.payload.len() as u64,
            16 * section.payload.len() as u64,
        )?;
        let parsed = crate::decode_inventory(&section.payload)
            .ok()
            .filter(|i| i.inventory_version == 1);
        budget.retain("path:inventory", 16 * section.payload.len() as u64)?;
        parsed
    } else {
        None
    };
    if let Some(inventory) = inventory {
        let q = inventory
            .entries
            .iter()
            .map(|e| {
                section_envelope_length(e)
                    .map(|n| n.div_ceil(157) as u64 * u64::from(e.physical_replica_count))
            })
            .collect::<Result<Vec<_>>>()?
            .iter()
            .sum();
        charge_layout(&inventory, q, budget)?;
        let mut first = 1u32;
        let mut grouped = vec![];
        for entry in &inventory.entries {
            let length = section_envelope_length(entry)?;
            let fragments = length.div_ceil(157);
            let factor = entry.physical_replica_count;
            for fragment in 0..fragments {
                if first > 2389 {
                    break;
                }
                if let Some(common) =
                    foreign_group(&inputs, first, factor, package, budget, &mut cache)?
                {
                    if decode_common_block(&common, 7).is_ok_and(|b| {
                        b.section_id == entry.section_id
                            && b.semantic_copy_id == 0
                            && b.section_type == entry.section_type
                            && b.section_version == entry.section_version
                            && usize::from(b.fragment_index) == fragment
                            && usize::from(b.fragment_count) == fragments
                            && b.section_envelope_length as usize == length
                    }) {
                        grouped.push(common);
                    }
                }
                first = first
                    .checked_add(u32::from(factor))
                    .ok_or(DamageV2Error::ResourceLimit)?;
            }
        }
        foreign_sections(&grouped, 7, budget)?;
    } else {
        commons.retain(|c| decode_common_block(c, 7).is_ok_and(|b| b.section_id != 1));
        foreign_sections(&commons, 7, budget)?;
    }
    Ok(())
}
fn foreign_transport(
    matrix: &ObsMatrix,
    path: &ObservedPath,
    budget: &mut Budget,
) -> Result<AcceptedHypothesis> {
    let (version, sector, package, unit_bytes, population) = match path {
        ObservedPath::Legacy(r) => (
            r.profile_version,
            r.sector,
            &r.package,
            if matches!(r.profile_version, 5 | 6) {
                255
            } else {
                216
            },
            r.map.population,
        ),
        ObservedPath::Hierarchical(r) => (7, r.sector, &r.package, 216, r.map.population),
        _ => return Err(DamageV2Error::Reconstruction),
    };
    let unit_count = population / (8 * unit_bytes as u64);
    if unit_count > 2389 {
        return Err(DamageV2Error::ResourceLimit);
    }
    budget.event(
        Kernel::UnitExtraction,
        unit_count * 8 * unit_bytes as u64,
        unit_count * (8 + 2 * unit_bytes as u64),
    )?;
    budget.retain("path:units", unit_count * (8 + 2 * unit_bytes as u64 + 199))?;
    let mut inputs = BTreeMap::new();
    let mut commons = vec![];
    for ordinal in 0..unit_count {
        budget.event(
            Kernel::LaneAdapter,
            unit_bytes as u64,
            unit_bytes as u64 + 191,
        )?;
        charge_observed(budget, package, 30, if unit_bytes == 216 { 24 } else { 1 })?;
        budget.event(Kernel::CommonFrame, 191, 191)?;
        let mut encoded = vec![0u8; unit_bytes];
        let mut erased = BTreeSet::new();
        let mut eh_erased = vec![];
        for bit in 0..unit_bytes * 8 {
            let (row, col) = match path {
                ObservedPath::Legacy(r) => {
                    let physical = r
                        .map
                        .forward(ordinal * unit_bytes as u64 * 8 + bit as u64)
                        .map_err(|_| DamageV2Error::Reconstruction)?;
                    r.map.matrix_cell(physical)
                }
                ObservedPath::Hierarchical(r) => {
                    let physical = r
                        .map
                        .forward_unit_bit(ordinal, bit as u16)
                        .map_err(|_| DamageV2Error::Reconstruction)?;
                    r.map.matrix_cell(physical)
                }
                _ => unreachable!(),
            }
            .map_err(|_| DamageV2Error::Reconstruction)?;
            let value = matrix.values[usize::from(row) * matrix.side + usize::from(col)];
            if value == 2 {
                if unit_bytes == 216 {
                    eh_erased.push(EhErasure {
                        codeword: (bit / 72) as u8,
                        position: (bit % 72 + 1) as u8,
                    });
                } else {
                    erased.insert((bit / 8) as u16);
                }
            } else {
                encoded[bit / 8] |= value << (7 - bit % 8);
            }
        }
        if unit_bytes == 216 {
            let observation = EhObservation {
                encoded: encoded.as_slice().try_into().unwrap(),
                erasures: eh_erased,
            };
            if let Ok(d) = decode_eh_unit(&observation, version) {
                commons.push(d.common);
            }
            if version == 7 {
                inputs.insert((ordinal + 1) as u32, Some(observation));
            }
        } else if let Ok(d) =
            decode_rs_unit(&encoded, &erased.into_iter().collect::<Vec<_>>(), version)
        {
            commons.push(d.common);
        }
    }
    if version == 7 {
        foreign_hierarchical_checks(&inputs, commons, Some(package), budget)?;
    } else {
        foreign_legacy_checks(&commons, version, budget)?;
    }
    let mapping_sha256 = match path {
        ObservedPath::Legacy(r) => {
            crate::damage::mapping_sha256(r.map).map_err(|_| DamageV2Error::Reconstruction)?
        }
        ObservedPath::Hierarchical(r) => {
            crate::damage_v1::mapping_sha256_v1(r.map).map_err(|_| DamageV2Error::Reconstruction)?
        }
        _ => unreachable!(),
    };
    Ok(AcceptedHypothesis {
        transform_id: 0,
        polarity_id: 0,
        sector_id: sector,
        profile_version: version,
        mapping_sha256,
    })
}
fn same_downstream(a: &RecoveryResultV2, b: &RecoveryResultV2) -> bool {
    a.profile_version == b.profile_version
        && a.inventory_established == b.inventory_established
        && a.artifact_state == b.artifact_state
        && a.sections == b.sections
        && a.fragments == b.fragments
        && a.required == b.required
        && a.all == b.all
}
fn matrix_core(matrix: ObsMatrix, budget: &mut Budget) -> Result<RecoveryResultV2> {
    if !(64..=2048).contains(&matrix.side) || matrix.side % 8 != 0 {
        return Err(DamageV2Error::Observation);
    }
    budget.retain("observation:square", (matrix.side * matrix.side) as u64)?;
    let mut results = Vec::new();
    let mut hypotheses = Vec::new();
    let mut context_witnesses = Vec::new();
    for transform in 0..8 {
        for polarity in 0..2 {
            budget.event(Kernel::SquareView, (matrix.side * matrix.side) as u64, 0)?;
            let view = transformed(&matrix, transform, polarity);
            let routes = discover_paths(&view, budget)?;
            for path in routes {
                if budget.complete_paths == 64 {
                    return Err(DamageV2Error::ResourceLimit);
                }
                budget.complete_paths += 1;
                let ObservedPath::Active(route) = path else {
                    budget.retain("accepted", 48 * (hypotheses.len() as u64 + 1))?;
                    let mut hypothesis = foreign_transport(&view, &path, budget)?;
                    hypothesis.transform_id = transform;
                    hypothesis.polarity_id = polarity;
                    hypotheses.push(hypothesis);
                    budget.retain("accepted", 48 * hypotheses.len() as u64)?;
                    budget.adapter.release_prefix("path:");
                    continue;
                };
                hypotheses.push(AcceptedHypothesis {
                    transform_id: transform,
                    polarity_id: polarity,
                    sector_id: route.sector(),
                    profile_version: 8,
                    mapping_sha256: route.mapping_sha256().map_err(route_error)?,
                });
                budget.retain("accepted", 48 * hypotheses.len() as u64)?;
                let (entries, local) = extract_inputs(&view, &route, budget)?;
                let result = recover_v8_inputs(
                    &entries,
                    &local,
                    budget,
                    Some(route.package()),
                    Some(route.mapping().unit_slot_count() as usize),
                    vec![],
                    Some(route.commitments()),
                )?;
                // Each path owns its exact package and numeric definitions. All paths
                // execute and charge independently before downstream equality.
                let mut definition_bytes = Vec::new();
                for (i, value) in route.definitions().iter().enumerate() {
                    definition_bytes.extend(((i + 1) as u16).to_be_bytes());
                    definition_bytes.extend((value.len() as u32).to_be_bytes());
                    definition_bytes.extend(value);
                }
                let proof = result.context_proof.clone().unwrap_or_else(|| {
                    route
                        .commitments()
                        .prove_recovered(None, None, &BTreeMap::new())
                });
                context_witnesses.push(ContextWitnessV2 {
                    hypothesis: hypotheses.last().unwrap().clone(),
                    package_sha256: format!("{:x}", Sha256::digest(&route.package().encoded)),
                    definitions_sha256: format!("{:x}", Sha256::digest(&definition_bytes)),
                    proof,
                });
                let footprint = result_footprint(&result);
                budget.event(
                    Kernel::ResultSelection,
                    footprint
                        .checked_mul(results.len().max(1) as u64)
                        .ok_or(DamageV2Error::ResourceLimit)?,
                    footprint,
                )?;
                budget.adapter.release_prefix("path:stream:");
                if !results.iter().any(|old| same_downstream(old, &result)) {
                    budget.retain(&format!("result:{}", results.len()), footprint)?;
                    results.push(result);
                }
                budget.adapter.release_prefix("path:");
            }
            budget.adapter.release("view:routes");
        }
    }
    hypotheses.sort();
    hypotheses.dedup();
    let complete = results
        .iter()
        .filter(|result| result.inventory_established)
        .collect::<Vec<_>>();
    let mut result = if complete.len() > 1 {
        RecoveryResultV2::closed(ArtifactState::Ambiguous, budget.value)
    } else if complete.len() == 1 {
        complete[0].clone()
    } else if results.len() == 1 {
        results.remove(0)
    } else {
        RecoveryResultV2::closed(ArtifactState::Failure, budget.value)
    };
    result.resource = budget.value;
    result.accepted_hypotheses = hypotheses;
    result.context_witnesses = context_witnesses;
    Ok(result)
}
fn bits_matrix(raw: &[u8]) -> Result<ObsMatrix> {
    if raw.len() < 5 || raw.len() > 524292 {
        return Err(DamageV2Error::Observation);
    };
    let count = u32::from_be_bytes(raw[..4].try_into().unwrap()) as usize;
    if count == 0
        || count > 4194304
        || raw.len() != 4 + count.div_ceil(8)
        || (count % 8 != 0 && raw.last().unwrap() & ((1 << (8 - count % 8)) - 1) != 0)
    {
        return Err(DamageV2Error::Observation);
    }
    let side = (64..=2048usize)
        .step_by(8)
        .find(|side| side * side == count)
        .ok_or(DamageV2Error::Observation)?;
    let values = raw[4..]
        .iter()
        .flat_map(|byte| (0..8).rev().map(move |bit| (byte >> bit) & 1))
        .take(count)
        .collect();
    Ok(ObsMatrix { side, values })
}
fn finish_render(
    channel: &str,
    raw: &[u8],
    mut result: RecoveryResultV2,
    budget: &mut Budget,
) -> Result<RecoveryResultV2> {
    const WRITER: u64 = 1048576 + 256;
    for attempt in 0..2 {
        budget
            .adapter
            .vm_workspace(WRITER)
            .map_err(|_| DamageV2Error::ResourceLimit)?;
        result.resource = budget.value;
        result.resource.peak_scratch_bytes = result
            .resource
            .peak_scratch_bytes
            .max(budget.adapter.peak_scratch_bytes());
        let wrapper = serialize_manifest(&object([(
            "rows",
            ManifestValue::Array(fragment_values(&result)),
        )]));
        let mut bytes = wrapper.as_ref().map_or(1048577, |v| v.len() as u64);
        let rendered = if wrapper.is_ok() {
            let rendered = render_decoder_result_v2(channel, &result);
            bytes = bytes
                .checked_add(rendered.as_ref().map_or(1048577, |r| r.0.len() as u64))
                .ok_or(DamageV2Error::ResourceLimit)?;
            rendered.is_ok()
        } else {
            false
        };
        budget.event(Kernel::ResultRender, bytes, WRITER)?;
        if rendered {
            result.resource.peak_scratch_bytes = result
                .resource
                .peak_scratch_bytes
                .max(budget.adapter.peak_scratch_bytes());
            result.adapter = budget.adapter.clone();
            result.observation_binding = Some((channel.to_owned(), observation_sha256(raw)));
            return Ok(result);
        }
        if attempt == 1 {
            return Err(DamageV2Error::ResourceLimit);
        }
        result = RecoveryResultV2::closed(ArtifactState::ResourceLimit, budget.value);
    }
    unreachable!()
}
fn run(channel: &str, raw: &[u8]) -> Result<RecoveryResultV2> {
    verify_owners()?;
    let mut budget = Budget::default();
    if !matches!(channel, "OBS_UNITS" | "OBS_BITS" | "OBS_MATRIX") {
        return Err(DamageV2Error::Channel);
    }
    budget.event(Kernel::Observation, raw.len() as u64, 0)?;
    let decoded = match channel {
        "OBS_UNITS" => units_core(raw, &mut budget),
        "OBS_BITS" => bits_matrix(raw).and_then(|matrix| matrix_core(matrix, &mut budget)),
        "OBS_MATRIX" => ObsMatrix::parse(raw)
            .map_err(|_| DamageV2Error::Observation)
            .and_then(|matrix| matrix_core(matrix, &mut budget)),
        _ => unreachable!(),
    };
    let result = match decoded {
        Ok(mut result) => {
            result.resource = budget.value;
            result
        }
        Err(error) => RecoveryResultV2::closed(
            if error == DamageV2Error::ResourceLimit {
                ArtifactState::ResourceLimit
            } else {
                ArtifactState::Failure
            },
            budget.value,
        ),
    };
    budget.adapter.release_prefix("observation:");
    budget.adapter.release_prefix("route:");
    budget.adapter.release_prefix("path:");
    budget.adapter.release_prefix("view:");
    finish_render(channel, raw, result, &mut budget)
}
pub fn decode_units_v2(raw: &[u8]) -> Result<RecoveryResultV2> {
    run("OBS_UNITS", raw)
}
pub fn decode_matrix_v2(raw: &[u8]) -> Result<RecoveryResultV2> {
    run("OBS_MATRIX", raw)
}
pub fn decode_bits_v2(raw: &[u8]) -> Result<RecoveryResultV2> {
    run("OBS_BITS", raw)
}
pub fn decode_observation_v2(channel: &str, raw: &[u8]) -> RecoveryResultV2 {
    run(channel, raw).unwrap_or_else(|_| {
        RecoveryResultV2::closed(ArtifactState::Failure, ResourceProjection::default())
    })
}

fn state_name(state: SectionState) -> &'static str {
    match state {
        SectionState::Verified => "verified",
        SectionState::Recovered => "recovered",
        SectionState::Incomplete => "incomplete",
        SectionState::Corrupt => "corrupt",
        SectionState::Ambiguous => "ambiguous",
        SectionState::Unknown => "unknown",
    }
}

fn fragment_state_name(state: FragmentState) -> &'static str {
    match state {
        FragmentState::Verified => "verified",
        FragmentState::Recovered => "recovered",
        FragmentState::Missing => "missing",
        FragmentState::Corrupt => "corrupt",
        FragmentState::Ambiguous => "ambiguous",
        FragmentState::Unknown => "unknown",
    }
}

fn artifact_state_name(state: ArtifactState) -> &'static str {
    match state {
        ArtifactState::Exact => "exact",
        ArtifactState::Degraded => "degraded",
        ArtifactState::Failure => "failure",
        ArtifactState::Ambiguous => "ambiguous",
        ArtifactState::ResourceLimit => "resource-limit",
    }
}

fn string(value: &str) -> ManifestValue {
    ManifestValue::String(value.to_owned())
}

fn object(rows: impl IntoIterator<Item = (&'static str, ManifestValue)>) -> ManifestValue {
    ManifestValue::Object(
        rows.into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}

fn canonical_array(rows: Vec<ManifestValue>) -> Result<Vec<u8>> {
    let wrapped = serialize_manifest(&object([("rows", ManifestValue::Array(rows))]))
        .map_err(|_| DamageV2Error::Reconstruction)?;
    const PREFIX: &[u8] = b"{\"rows\":";
    const SUFFIX: &[u8] = b"}\n";
    if !wrapped.starts_with(PREFIX) || !wrapped.ends_with(SUFFIX) {
        return Err(DamageV2Error::Reconstruction);
    }
    Ok(wrapped[PREFIX.len()..wrapped.len() - SUFFIX.len()].to_vec())
}

fn fragment_values(result: &RecoveryResultV2) -> Vec<ManifestValue> {
    result
        .fragments
        .iter()
        .map(|row| {
            object([
                ("input_id", ManifestValue::U64(u64::from(row.input_id))),
                (
                    "profile_id",
                    string(
                        row.profile_version
                            .and_then(profile_for_version)
                            .map_or("", |profile| profile.id),
                    ),
                ),
                ("section_id", ManifestValue::U64(u64::from(row.section_id))),
                (
                    "semantic_copy_id",
                    ManifestValue::U64(u64::from(row.semantic_copy_id)),
                ),
                (
                    "fragment_index",
                    ManifestValue::U64(u64::from(row.fragment_index)),
                ),
                (
                    "replica_index",
                    ManifestValue::U64(u64::from(row.replica_index)),
                ),
                (
                    "physical_replica_count",
                    ManifestValue::U64(u64::from(row.physical_replica_count)),
                ),
                ("state", string(fragment_state_name(row.state))),
                ("common_block_sha256", string(&row.common_block_sha256)),
            ])
        })
        .collect()
}

pub fn render_decoder_result_v2(
    channel: &str,
    result: &RecoveryResultV2,
) -> Result<(Vec<u8>, String)> {
    if !matches!(channel, "OBS_BITS" | "OBS_MATRIX" | "OBS_UNITS") {
        return Err(DamageV2Error::Channel);
    }
    if channel == "OBS_UNITS" && !result.accepted_hypotheses.is_empty() {
        return Err(DamageV2Error::Reconstruction);
    }

    let profile_id = result
        .profile_version
        .and_then(profile_for_version)
        .map_or("", |profile| profile.id);
    let section_rows = result.sections.iter().map(|row| {
        object([
            ("section_id", ManifestValue::U64(u64::from(row.section_id))),
            ("state", string(state_name(row.state))),
            (
                "semantic_sha256",
                string(
                    &row.envelope
                        .as_ref()
                        .map_or_else(|| ZERO_SHA256.to_owned(), |raw| observation_sha256(raw)),
                ),
            ),
        ])
    });
    let fragment_bytes = canonical_array(fragment_values(result))?;

    let required = result.required.clone();
    let all = result.all.clone();
    if all.is_some() && required.is_none() {
        return Err(DamageV2Error::Reconstruction);
    }
    let accepted = result.accepted_hypotheses.iter().map(|row| {
        object([
            (
                "transform_id",
                ManifestValue::U64(u64::from(row.transform_id)),
            ),
            (
                "polarity_id",
                ManifestValue::U64(u64::from(row.polarity_id)),
            ),
            ("sector_id", ManifestValue::U64(u64::from(row.sector_id))),
            (
                "profile_id",
                string(profile_for_version(row.profile_version).map_or("", |profile| profile.id)),
            ),
            ("mapping_sha256", string(&row.mapping_sha256)),
        ])
    });
    let value = object([
        ("schema", string("golden-board.m2-damage-decoder-result/v2")),
        ("channel", string(channel)),
        (
            "artifact_state",
            string(artifact_state_name(result.artifact_state)),
        ),
        ("established_profile_id", string(profile_id)),
        ("section_rows", ManifestValue::Array(section_rows.collect())),
        (
            "fragment_diagnostics_sha256",
            string(&observation_sha256(&fragment_bytes)),
        ),
        (
            "m2_required_available",
            ManifestValue::Bool(required.is_some()),
        ),
        ("m2_all_available", ManifestValue::Bool(all.is_some())),
        (
            "m2_required_stream_sha256",
            string(
                &required
                    .as_ref()
                    .map_or_else(|| ZERO_SHA256.to_owned(), |raw| observation_sha256(raw)),
            ),
        ),
        (
            "m2_all_stream_sha256",
            string(
                &all.as_ref()
                    .map_or_else(|| ZERO_SHA256.to_owned(), |raw| observation_sha256(raw)),
            ),
        ),
        (
            "resource",
            object([
                (
                    "section_attempts",
                    ManifestValue::U64(result.resource.section_attempts),
                ),
                (
                    "primitive_steps",
                    ManifestValue::U64(result.resource.primitive_steps),
                ),
                (
                    "peak_scratch_bytes",
                    ManifestValue::U64(result.resource.peak_scratch_bytes),
                ),
            ]),
        ),
        (
            "accepted_hypothesis_rows",
            ManifestValue::Array(accepted.collect()),
        ),
    ]);
    let raw = serialize_manifest(&value).map_err(|_| DamageV2Error::Reconstruction)?;
    if raw.len() > 1_048_576 {
        return Err(DamageV2Error::ResourceLimit);
    }
    let sha256 = observation_sha256(&raw);
    Ok((raw, sha256))
}

#[cfg(test)]
mod body_path_tests {
    use super::*;
    #[test]
    fn legacy_inventory_fragments_reach_registry_fallback_assembly() {
        let envelope = crate::encode_section(&SectionEnvelope {
            section_id: 1,
            section_type: 1,
            section_version: 2,
            closure_class: 128,
            check_id: 1,
            dependencies: vec![],
            payload: vec![1; 200],
        })
        .unwrap();
        for profile_version in 2..=8 {
            let blocks = crate::fragment_envelope(profile_version, 1, 0, 1, 2, &envelope).unwrap();
            assert_eq!(blocks.len(), 2);
            let lanes = (1..=5)
                .map(|id| {
                    (
                        id,
                        vec![LocalCandidate {
                            profile_version,
                            quality: DecodeQuality::Verified,
                            common: blocks[0],
                        }],
                    )
                })
                .collect();
            let mut budget = Budget::default();
            let sections = discovered_sections_without_inventory(
                &lanes,
                &[],
                &mut BTreeSet::new(),
                &mut budget,
            )
            .unwrap();
            assert!(sections.is_empty());
            let row = &budget.adapter.rows()[Kernel::SectionAssembly as usize];
            let expected = u64::from(profile_version <= 6);
            assert_eq!(row.calls(), expected, "profile{profile_version}");
            assert_eq!(row.reference_input_units(), 955 * expected);
            assert_eq!(row.peak_workspace_bytes(), 120 * expected);
            assert_eq!(budget.section_attempts, 0);
        }
    }
    #[test]
    fn unavailable_hierarchical_group_stops_before_selected_block_assembly() {
        let raw = crate::encode_section(&SectionEnvelope {
            section_id: 400,
            section_type: 4,
            section_version: 0,
            closure_class: 129,
            check_id: 1,
            dependencies: vec![],
            payload: vec![1; 200],
        })
        .unwrap();
        let blocks = crate::fragment_envelope(8, 400, 0, 4, 0, &raw).unwrap();
        let groups = blocks
            .iter()
            .enumerate()
            .map(|(i, block)| GroupRecovery {
                identity: GroupIdentity::from_common(block).unwrap(),
                first_id: i as u32 + 1,
                factor: 1,
                state: if i == 0 {
                    FragmentState::Verified
                } else {
                    FragmentState::Missing
                },
                common: (i == 0).then_some(*block),
                lane_states: vec![],
            })
            .collect::<Vec<_>>();
        let mut budget = Budget::default();
        assert!(
            checked_section_from_groups(&groups, None, &mut budget)
                .unwrap()
                .is_none()
        );
        assert_eq!(
            budget.adapter.rows()[Kernel::SectionAssembly as usize].calls(),
            0
        );
        // An actual selected, but incomplete, generic witness list still enters its adapter.
        charge_witness_assembly(
            &[quality_witness(DecodeQuality::Verified, blocks[0])],
            8,
            &mut budget,
        )
        .unwrap();
        assert_eq!(
            budget.adapter.rows()[Kernel::SectionAssembly as usize].calls(),
            1
        );
        assert_eq!(
            budget.adapter.rows()[Kernel::SectionAssembly as usize].reference_input_units(),
            191
        );
        assert_eq!(budget.section_attempts, 0);
    }
    #[test]
    fn section_attempt_eligibility_checks_header_dependencies_and_exact_bound_before_crc() {
        let envelope = crate::SectionEnvelope {
            section_id: 400,
            section_type: 4,
            section_version: 65535,
            closure_class: 129,
            check_id: 1,
            dependencies: vec![2, 3],
            payload: vec![7],
        };
        let raw = crate::encode_section(&envelope).unwrap();
        assert!(structurally_attemptable(&raw));
        for (at, bytes) in [
            (2, vec![0, 0, 0, 0]),
            (6, vec![0, 0]),
            (10, vec![0]),
            (18, vec![0, 0, 0, 0]),
            (22, vec![0, 0, 0, 2]),
            (22, 400u32.to_be_bytes().to_vec()),
        ] {
            let mut changed = raw.clone();
            changed[at..at + bytes.len()].copy_from_slice(&bytes);
            assert!(!structurally_attemptable(&changed), "offset{at}");
        }
        let mut changed = raw.clone();
        *changed.last_mut().unwrap() ^= 1;
        assert!(structurally_attemptable(&changed));
        changed = raw.clone();
        changed[11] = 2;
        assert!(!structurally_attemptable(&changed));
        let mut large = envelope;
        large.dependencies.clear();
        large.payload = vec![0; 32768];
        assert!(structurally_attemptable(
            &crate::encode_section(&large).unwrap()
        ));
        large.payload.push(0);
        assert!(!structurally_attemptable(
            &crate::encode_section(&large).unwrap()
        ));
    }
    #[test]
    fn altered_valid_body_program_executes_generic_vm_and_keeps_failure_atomic() {
        let compact = crate::body_recipe_v1::build_revision_recipe_package().unwrap();
        let mut expanded = crate::recipe_wire_v1::expand_recipe_package_v1(&compact, 8).unwrap();
        let u16_at =
            |raw: &[u8], at: usize| u16::from_be_bytes(raw[at..at + 2].try_into().unwrap());
        let u32_at = |raw: &[u8], at: usize| {
            u32::from_be_bytes(raw[at..at + 4].try_into().unwrap()) as usize
        };
        let mut offset = 64;
        for _ in 0..u16_at(&expanded, 18) {
            offset += 16 + u32_at(&expanded, offset + 12);
        }
        while u16_at(&expanded, offset) != 202 {
            offset += u32_at(&expanded, offset + 28);
        }
        let start = offset
            + 32
            + 12 * (usize::from(u16_at(&expanded, offset + 4))
                + usize::from(u16_at(&expanded, offset + 6)));
        let end = offset + u32_at(&expanded, offset + 28);
        let node = (start..end)
            .step_by(32)
            .find(|at| expanded[*at + 2] == 24)
            .unwrap();
        expanded[node + 2] = 25;
        expanded[node + 24..node + 32].copy_from_slice(&4u64.to_be_bytes());
        let changed = crate::recipe_wire_v1::encode_recipe_package_v1(&expanded, 8).unwrap();
        let package = crate::recipe_wire_v1::decode_recipe_package_v1(&changed, 8).unwrap();
        assert!(!crate::route_receiver_v2::body_refines(&package));
        let mut budget = Budget::default();
        let output =
            decoded_body(Some(&package), 1, &[3, 0, 8, 0x40, b'A', 0, 4], &mut budget).unwrap();
        assert!(output.is_none());
        assert_eq!(
            budget.primitive_steps,
            package.logical.recipe_primitive_steps(202).unwrap()
        );
        assert_eq!(budget.section_attempts, 0);
    }
}

pub fn render_resources_v2(
    channel: &str,
    wire: &[u8],
    result: &RecoveryResultV2,
) -> Result<Vec<u8>> {
    if result.observation_binding.as_ref() != Some(&(channel.to_owned(), observation_sha256(wire)))
    {
        return Err(DamageV2Error::Reconstruction);
    }
    let (_, result_sha256) = render_decoder_result_v2(channel, result)?;
    crate::resources_v2::render_resource_sidecar(
        channel,
        &observation_sha256(wire),
        &result_sha256,
        result.resource,
        &result.adapter,
    )
    .map_err(|_| DamageV2Error::Reconstruction)
}
