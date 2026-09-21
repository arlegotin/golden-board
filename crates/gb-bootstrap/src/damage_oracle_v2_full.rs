//! Full source-side composition, independently scheduled from observed bytes.
use super::resources::{self, Attempt, Kernel, Ledger, Reservation};
use super::routes::{
    DiscoveryScanner, Hypothesis, Matrix, Program, RoutePath, ScanContext, ScanError,
};
use super::{FragmentDiagnostic, Group, Input, Lane, SemanticProjection};
use crate::damage::{ArtifactState, FragmentState, SectionResult, SectionState};
use crate::damage_corpus_v2::DamageCorpusV2;
use crate::{CommonBlock, Inventory};
use gb_foundation::{ManifestValue as V, serialize_manifest};
use sha2::{Digest, Sha256};
use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

type Result<T> = std::result::Result<T, ScanError>;
const REGISTRY: [u16; 7] = [8, 2, 3, 4, 5, 6, 7];
const ZERO: &str = "0000000000000000000000000000000000000000000000000000000000000000";
fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn add(a: u64, b: u64) -> Result<u64> {
    a.checked_add(b).ok_or(ScanError::Resource)
}
fn mul(a: u64, b: u64) -> Result<u64> {
    a.checked_mul(b).ok_or(ScanError::Resource)
}
fn object(rows: impl IntoIterator<Item = (&'static str, V)>) -> V {
    V::Object(rows.into_iter().map(|(k, v)| (k.to_owned(), v)).collect())
}
fn string(s: &str) -> V {
    V::String(s.to_owned())
}
fn profile_name(p: u16) -> Result<&'static str> {
    if p == 8 {
        Ok("eh72-hier-r5-r2-r1-lzss-crc32c-v1")
    } else {
        crate::candidate::profile_by_version(p)
            .map(|p| p.id)
            .ok_or(ScanError::Source)
    }
}
fn section_state(s: SectionState) -> &'static str {
    match s {
        SectionState::Verified => "verified",
        SectionState::Recovered => "recovered",
        SectionState::Incomplete => "incomplete",
        SectionState::Corrupt => "corrupt",
        SectionState::Ambiguous => "ambiguous",
        SectionState::Unknown => "unknown",
    }
}
fn fragment_state(s: FragmentState) -> &'static str {
    match s {
        FragmentState::Verified => "verified",
        FragmentState::Recovered => "recovered",
        FragmentState::Missing => "missing",
        FragmentState::Corrupt => "corrupt",
        FragmentState::Ambiguous => "ambiguous",
        FragmentState::Unknown => "unknown",
    }
}
fn artifact_state(s: ArtifactState) -> &'static str {
    match s {
        ArtifactState::Exact => "exact",
        ArtifactState::Degraded => "degraded",
        ArtifactState::Failure => "failure",
        ArtifactState::Ambiguous => "ambiguous",
        ArtifactState::ResourceLimit => "resource-limit",
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct PathResult {
    established: bool,
    state: ArtifactState,
    sections: Vec<SectionResult>,
    fragments: Vec<FragmentDiagnostic>,
    required: Option<Vec<u8>>,
    all: Option<Vec<u8>>,
}
impl PathResult {
    fn closed(state: ArtifactState) -> Self {
        Self {
            established: false,
            state,
            sections: vec![],
            fragments: vec![],
            required: None,
            all: None,
        }
    }
    fn footprint(&self) -> Result<u64> {
        let mut n = add(
            mul(self.sections.len() as u64, 48)?,
            mul(self.fragments.len() as u64, 40)?,
        )?;
        for s in &self.sections {
            n = add(n, s.envelope.as_ref().map_or(0, |v| v.len() as u64))?;
        }
        for f in &self.fragments {
            if f.common_block_sha256 != ZERO {
                n = add(n, 191)?;
            }
        }
        n = add(n, self.required.as_ref().map_or(0, |v| v.len() as u64))?;
        add(n, self.all.as_ref().map_or(0, |v| v.len() as u64))
    }
}

pub struct CompleteProjection {
    result: Vec<u8>,
    sidecar: Vec<u8>,
    semantic: SemanticProjection,
}
impl CompleteProjection {
    pub fn result_bytes(&self) -> &[u8] {
        &self.result
    }
    pub fn resource_bytes(&self) -> &[u8] {
        &self.sidecar
    }
    pub fn semantic(&self) -> &SemanticProjection {
        &self.semantic
    }
}
pub struct FullOracleV2<'a> {
    scanner: DiscoveryScanner<'a>,
    programs: BTreeMap<u16, Arc<Program>>,
    lanes: RefCell<BTreeMap<(Vec<u8>, Vec<(u8, u8)>), Option<Lane>>>,
}
impl<'a> FullOracleV2<'a> {
    pub fn new(source: &'a DamageCorpusV2) -> Result<Self> {
        let scanner = DiscoveryScanner::new(source)?;
        let mut programs = BTreeMap::from([(8, scanner.active_program())]);
        for profile in [2, 3, 4, 5, 6, 7] {
            let raw = match profile {
                5 | 6 => crate::candidate_recipe::build_rs_decoder_recipe_package(profile),
                7 => crate::candidate_recipe::build_r3_recipe_package(),
                _ => crate::candidate_recipe::build_eh_recipe_package(profile),
            }
            .map_err(|_| ScanError::Source)?;
            programs.insert(profile, Arc::new(Program::parse(&raw, profile)?));
        }
        Ok(Self {
            scanner,
            programs,
            lanes: RefCell::new(BTreeMap::new()),
        })
    }

    /// Exact owned observations only. Construction binding authorizes the
    /// independently proved clean-definition optimization, never receiver data.
    pub fn project(&self, family: &str, ordinal: u64, raw: &[u8]) -> Result<CompleteProjection> {
        let owned = self
            .scanner
            .source
            .case(family, ordinal)
            .map_err(|_| ScanError::Source)?;
        if owned.bytes() != raw {
            return Err(ScanError::Source);
        }
        let channel = owned.channel();
        let mut ledger = Ledger::new();
        ledger.adapter(Kernel::Observation, raw.len() as u64, 0)?;
        let mut context = ScanContext::default();
        let mut candidates = Vec::new();
        let outcome = if channel == "OBS_UNITS" {
            self.units(raw, &mut candidates, &mut ledger)
        } else {
            self.square(channel, raw, &mut context, &mut candidates, &mut ledger)
        };
        let mut selected = match outcome {
            Ok(()) => select(&candidates),
            Err(ScanError::Unavailable) => PathResult::closed(ArtifactState::Failure),
            Err(ScanError::Resource) => {
                context.hypotheses.clear();
                PathResult::closed(ArtifactState::ResourceLimit)
            }
            Err(error) => return Err(error),
        };
        ledger.release_transients()?;
        let result = render(channel, &mut selected, &mut context.hypotheses, &mut ledger)?;
        let sidecar = resource_sidecar(channel, raw, &result, &ledger)?;
        let semantic = super::SemanticOracleV2::new(self.scanner.source)
            .finish(
                selected.state,
                selected.sections,
                selected.fragments,
                selected.required,
                selected.all,
                family == "B0",
            )
            .map_err(|_| ScanError::Source)?;
        Ok(CompleteProjection {
            result,
            sidecar,
            semantic,
        })
    }

    /// One bounded development replay row, generated from source and this
    /// observation alone. Independent receiver convergence is checked outside
    /// this producer; a row never awards a gate.
    pub fn replay(&self, family: &str, ordinal: u64, raw: &[u8]) -> Result<Vec<u8>> {
        let projection = self.project(family, ordinal, raw)?;
        let observation = self
            .scanner
            .source
            .case(family, ordinal)
            .map_err(|_| ScanError::Source)?;
        let required = self
            .scanner
            .source
            .source_core()
            .sections
            .iter()
            .filter(|s| s.closure_class == 128)
            .map(|s| s.section_id)
            .collect::<BTreeSet<_>>();
        replay_row(observation.identity_bytes(), &projection, &required)
    }

    fn units(
        &self,
        raw: &[u8],
        candidates: &mut Vec<PathResult>,
        ledger: &mut Ledger,
    ) -> Result<()> {
        let count = raw.get(..4).ok_or(ScanError::Unavailable)?;
        if u32::from_be_bytes(count.try_into().unwrap()) > 2389 {
            return Err(ScanError::Resource);
        }
        let frame = crate::damage::ObsUnits::parse(raw).map_err(|_| ScanError::Unavailable)?;
        let inputs = frame
            .entries
            .into_iter()
            .map(|e| {
                (
                    e.physical_unit_id,
                    Input {
                        bytes: e.bytes,
                        erased: vec![],
                    },
                )
            })
            .collect::<BTreeMap<_, _>>();
        let pool = inputs.values().try_fold(0u64, |n, i| {
            add(n, add(8 + 7 * 199, mul(i.bytes.len() as u64, 2)?)?)
        })?;
        let _pool = ledger.retain(pool)?;
        let lanes = self.decode_lanes(&inputs, &REGISTRY, None, ledger)?;
        let mut path = PathState::default();
        let mut active = None;
        for profile in REGISTRY {
            if matches!(profile, 8 | 7) {
                let result = self.hierarchical(
                    profile,
                    &inputs,
                    &lanes,
                    None,
                    &self.programs[&profile],
                    &mut path,
                    ledger,
                )?;
                if profile == 8 {
                    if result.established {
                        consider(result.clone(), candidates, ledger)?;
                    }
                    active = Some(result);
                }
            } else {
                self.legacy(profile, &lanes, &mut path, ledger)?;
            }
            // Group charge keys survive the shared registry path. Other arenas
            // belong to the current profile and end before the next profile.
            path.close(ledger)?;
        }
        if candidates.is_empty() {
            let mut active = active.ok_or(ScanError::Source)?;
            let mut sections = BTreeMap::new();
            for profile in REGISTRY {
                let mut selected = lanes
                    .iter()
                    .filter(|(_, l)| !matches!(profile, 8 | 7) || l.block.section_id != 1)
                    .map(|(id, l)| (*id, l.clone()))
                    .collect::<BTreeMap<_, _>>();
                if let Some(bootstrap) = path.bootstrap.get(&profile) {
                    selected.extend(bootstrap.clone());
                }
                for (id, row) in diagnostic_assemblies(&selected, profile, ledger)? {
                    if let Some(old) = sections.get_mut(&id) {
                        let old: &mut SectionResult = old;
                        if old.envelope != row.envelope {
                            old.state = SectionState::Ambiguous;
                            old.envelope = None;
                        }
                    } else {
                        sections.insert(id, row);
                    }
                }
            }
            if let Some(inventory) = active.sections.iter().find(|s| s.section_id == 1) {
                sections.insert(1, inventory.clone());
            }
            active.sections = sections.into_values().collect();
            // All registry lanes supply their own semantic identity. Fixed
            // bootstrap replica metadata is independent of local validity.
            let mut ids = inputs.keys().copied().collect::<BTreeSet<_>>();
            ids.extend(1..=5);
            active.fragments = ids
                .into_iter()
                .map(|id| {
                    super::diagnostic(id, inputs.contains_key(&id), lanes.get(&id), None, id <= 5)
                })
                .collect();
            consider(active, candidates, ledger)?;
        }
        Ok(())
    }

    fn square(
        &self,
        channel: &str,
        raw: &[u8],
        context: &mut ScanContext,
        candidates: &mut Vec<PathResult>,
        ledger: &mut Ledger,
    ) -> Result<()> {
        let matrix = Matrix::parse(channel, raw)?;
        let _pool = ledger.retain(matrix.cells.len() as u64)?;
        for transform in 0..8 {
            for polarity in 0..2 {
                let routes = self
                    .scanner
                    .scan_view(&matrix, transform, polarity, context, ledger)?;
                context.complete_paths = context
                    .complete_paths
                    .checked_add(routes.len())
                    .ok_or(ScanError::Resource)?;
                if context.complete_paths > 64 {
                    return Err(ScanError::Resource);
                }
                for route in &routes {
                    context.admit_hypothesis(route, ledger)?;
                    let inputs = extract(&matrix, route, ledger)?;
                    let pool_bytes = mul(
                        route.mapping.units,
                        8 + 2 * u64::from(route.mapping.unit_bytes) + 199,
                    )?;
                    let pool = ledger.retain(pool_bytes)?;
                    let lanes =
                        self.decode_lanes(&inputs, &[route.profile], Some(&route.program), ledger)?;
                    let mut path = PathState::default();
                    if matches!(route.profile, 8 | 7) {
                        let value = self.hierarchical(
                            route.profile,
                            &inputs,
                            &lanes,
                            Some(route.mapping.units as usize),
                            &route.program,
                            &mut path,
                            ledger,
                        )?;
                        if route.profile == 8 {
                            consider(value, candidates, ledger)?;
                        }
                    } else {
                        self.legacy(route.profile, &lanes, &mut path, ledger)?;
                    }
                    path.close(ledger)?;
                    ledger.release(pool)?;
                }
                for route in routes {
                    ledger.release(route.descriptor)?;
                }
            }
        }
        Ok(())
    }

    fn lane(&self, id: u32, input: &Input) -> Option<Lane> {
        if input.erased.is_empty() {
            if let Some(source) = self
                .scanner
                .source
                .source_core()
                .units
                .get((id as usize).wrapping_sub(1))
            {
                if source.encoded.as_slice() == input.bytes {
                    let raw = self.scanner.source.source_commons()[id as usize - 1];
                    return Some(Lane {
                        raw,
                        block: crate::decode_common_block(&raw, 8).ok()?,
                        verified: true,
                    });
                }
            }
        }
        let key = (
            input.bytes.clone(),
            input
                .erased
                .iter()
                .map(|e| (e.codeword, e.position))
                .collect(),
        );
        if let Some(value) = self.lanes.borrow().get(&key) {
            return value.clone();
        }
        let value = super::decode_lane(input);
        if self.lanes.borrow().len() < 1_000_000 {
            self.lanes.borrow_mut().insert(key, value.clone());
        }
        value
    }

    fn decode_lanes(
        &self,
        inputs: &BTreeMap<u32, Input>,
        profiles: &[u16],
        program: Option<&Program>,
        ledger: &mut Ledger,
    ) -> Result<BTreeMap<u32, Lane>> {
        let mut lanes = BTreeMap::new();
        for (&id, input) in inputs {
            let actual = self.lane(id, input);
            for &profile in profiles {
                let program = program.unwrap_or(&self.programs[&profile]);
                let shape = program.shapes.get(&30).ok_or(ScanError::Source)?;
                let local = add(input.bytes.len() as u64, 191)?;
                ledger.adapter(Kernel::LaneAdapter, input.bytes.len() as u64, local)?;
                let lease = ledger.retain(local)?;
                let count = if matches!(profile, 5 | 6) { 1 } else { 24 };
                ledger.vm_repeated(shape.steps, shape.scratch, count)?;
                if input.bytes.len() == if matches!(profile, 5 | 6) { 255 } else { 216 } {
                    ledger.adapter(Kernel::CommonFrame, 191, 191)?;
                }
                ledger.release(lease)?;
                if let Some(value) = actual
                    .as_ref()
                    .filter(|v| v.block.profile_version == profile)
                {
                    lanes.insert(id, value.clone());
                }
            }
        }
        Ok(lanes)
    }
}

#[derive(Default)]
struct PathState {
    reservations: Vec<Reservation>,
    groups: BTreeSet<(u16, Vec<Option<u32>>)>,
    bodies: BTreeMap<u32, Option<Vec<u8>>>,
    bootstrap: BTreeMap<u16, BTreeMap<u32, Lane>>,
}
impl PathState {
    fn hold(&mut self, ledger: &mut Ledger, bytes: u64) -> Result<()> {
        self.reservations.push(ledger.retain(bytes)?);
        Ok(())
    }
    fn close(&mut self, ledger: &mut Ledger) -> Result<()> {
        for lease in self.reservations.drain(..).rev() {
            ledger.release(lease)?;
        }
        Ok(())
    }
}

fn block_matches(block: &CommonBlock, profile: u16, expected: Option<&super::Expected>) -> bool {
    if block.profile_version != profile {
        return false;
    }
    match expected {
        None => block.section_id == 1 && block.semantic_copy_id == 0 && block.fragment_index == 0,
        Some(e) => {
            block.section_id == e.id
                && block.semantic_copy_id == 0
                && block.section_type == e.kind
                && block.section_version == e.version
                && block.fragment_index == e.index
                && block.fragment_count == e.count
                && block.section_envelope_length == e.length
        }
    }
}
fn choose_group(
    inputs: &BTreeMap<u32, Input>,
    lanes: &BTreeMap<u32, Lane>,
    ids: &[u32],
    profile: u16,
    expected: Option<&super::Expected>,
    program: &Program,
    state: &mut PathState,
    ledger: &mut Ledger,
) -> Result<Group> {
    let present = ids.iter().any(|id| inputs.contains_key(id));
    let key = (
        profile,
        ids.iter()
            .map(|id| inputs.contains_key(id).then_some(*id))
            .collect(),
    );
    if matches!(ids.len(), 2 | 5) && present && state.groups.insert(key) {
        let workspace = 216 + 2 * 1728;
        ledger.adapter(
            Kernel::RepetitionAdapter,
            ids.len() as u64 * 1728,
            workspace,
        )?;
        let lease = ledger.retain(workspace)?;
        let rep = program.shapes.get(&113).ok_or(ScanError::Source)?;
        let decode = program.shapes.get(&30).ok_or(ScanError::Source)?;
        ledger.vm_repeated(rep.steps, rep.scratch, 1728)?;
        ledger.vm_repeated(decode.steps, decode.scratch, 24)?;
        ledger.adapter(Kernel::CommonFrame, 191, 191)?;
        ledger.release(lease)?;
    }
    if profile == 8 {
        return Ok(super::group(inputs, lanes, ids, expected));
    }
    let mut candidates = BTreeMap::<[u8; 191], Lane>::new();
    for id in ids {
        if let Some(lane) = lanes
            .get(id)
            .filter(|l| block_matches(&l.block, profile, expected))
        {
            candidates
                .entry(lane.raw)
                .and_modify(|v| v.verified |= lane.verified)
                .or_insert(lane.clone());
        }
    }
    if matches!(ids.len(), 2 | 5) && present {
        let mut combined = Input {
            bytes: vec![0; 216],
            erased: vec![],
        };
        let masks = ids
            .iter()
            .map(|id| {
                inputs.get(id).map(|p| {
                    p.erased
                        .iter()
                        .map(|e| usize::from(e.codeword) * 72 + usize::from(e.position) - 1)
                        .collect::<BTreeSet<_>>()
                })
            })
            .collect::<Vec<_>>();
        for bit in 0..1728 {
            let (mut zeros, mut ones) = (0, 0);
            for (id, mask) in ids.iter().zip(&masks) {
                if let (Some(input), Some(mask)) = (inputs.get(id), mask) {
                    if input.bytes.len() == 216 && !mask.contains(&bit) {
                        if input.bytes[bit / 8] & (1 << (7 - bit % 8)) == 0 {
                            zeros += 1;
                        } else {
                            ones += 1;
                        }
                    }
                }
            }
            let erased = ids.len() - zeros - ones;
            if 2 * ones + erased < ids.len() {
            } else if 2 * zeros + erased < ids.len() {
                combined.bytes[bit / 8] |= 1 << (7 - bit % 8);
            } else {
                combined.erased.push(crate::candidate::EhErasure {
                    codeword: (bit / 72) as u8,
                    position: (bit % 72 + 1) as u8,
                });
            }
        }
        if let Some(mut lane) =
            super::decode_lane(&combined).filter(|l| block_matches(&l.block, profile, expected))
        {
            lane.verified = false;
            candidates.entry(lane.raw).or_insert(lane);
        }
    }
    Ok(match candidates.len() {
        0 => Group {
            state: if present {
                FragmentState::Corrupt
            } else {
                FragmentState::Missing
            },
            lane: None,
        },
        1 => {
            let lane = candidates.into_values().next().unwrap();
            Group {
                state: if lane.verified {
                    FragmentState::Verified
                } else {
                    FragmentState::Recovered
                },
                lane: Some(lane),
            }
        }
        _ => Group {
            state: FragmentState::Ambiguous,
            lane: None,
        },
    })
}

fn assemble(lanes: &[Lane], profile: u16, ledger: &mut Ledger) -> Result<Option<Vec<u8>>> {
    if lanes.is_empty() {
        return Ok(None);
    }
    let candidate = copy_bytes(lanes, profile);
    let length = candidate.as_ref().map_or(0, |raw| raw.len() as u64);
    let workspace = add(length, mul(lanes.len() as u64, 24)?)?;
    ledger.adapter(
        Kernel::SectionAssembly,
        mul(lanes.len() as u64, 191)?,
        workspace,
    )?;
    let lease = ledger.retain(workspace)?;
    let result = if let Some(raw) = candidate {
        assemble_inner(lanes, profile, &raw, ledger)
    } else {
        Ok(None)
    };
    ledger.release(lease)?;
    result
}

// Only common-fragment identity and complete ordered coverage construct bytes.
// An advertised capacity is not a constructed candidate. Envelope admission is
// later, so a complete malformed envelope still reserves its actual byte count.
fn copy_bytes(lanes: &[Lane], profile: u16) -> Option<Vec<u8>> {
    let b = &lanes.first()?.block;
    let mut by_index = BTreeMap::<u16, &Lane>::new();
    for lane in lanes {
        let c = &lane.block;
        if c.profile_version != profile
            || c.section_id != b.section_id
            || c.semantic_copy_id != b.semantic_copy_id
            || c.section_type != b.section_type
            || c.section_version != b.section_version
            || c.fragment_count != b.fragment_count
            || c.section_envelope_length != b.section_envelope_length
        {
            return None;
        }
        if by_index
            .get(&c.fragment_index)
            .is_some_and(|old| old.raw != lane.raw)
        {
            return None;
        }
        by_index.insert(c.fragment_index, lane);
    }
    if by_index.keys().copied().ne(0..b.fragment_count) {
        return None;
    }
    let raw = by_index
        .values()
        .flat_map(|l| l.block.payload.iter().copied())
        .collect::<Vec<_>>();
    (raw.len() == b.section_envelope_length as usize).then_some(raw)
}

fn assemble_inner(
    lanes: &[Lane],
    profile: u16,
    raw: &[u8],
    ledger: &mut Ledger,
) -> Result<Option<Vec<u8>>> {
    let b = &lanes.first().ok_or(ScanError::Source)?.block;
    if raw.len() < 10 {
        return Ok(None);
    }
    if u32::from_be_bytes(raw[2..6].try_into().unwrap()) != b.section_id
        || u16::from_be_bytes(raw[6..8].try_into().unwrap()) != b.section_type
        || u16::from_be_bytes(raw[8..10].try_into().unwrap()) != b.section_version
    {
        return Ok(None);
    }
    if ledger.section_check(raw)? == Attempt::Ineligible {
        return Ok(None);
    }
    let witnesses = lanes
        .iter()
        .map(|l| crate::FragmentWitness {
            raw_block: l.raw,
            quality: if l.verified {
                crate::RecoveryQuality::Verified
            } else {
                crate::RecoveryQuality::Recovered
            },
        })
        .collect::<Vec<_>>();
    Ok(crate::assemble_semantic_copy(&witnesses, profile)
        .ok()
        .map(|v| v.envelope))
}

fn parse_inventory(
    raw: &[u8],
    profile: u16,
    path: &mut PathState,
    ledger: &mut Ledger,
) -> Result<Option<Inventory>> {
    let Ok(envelope) = crate::decode_section(raw) else {
        return Ok(None);
    };
    let bytes = envelope.payload.len() as u64;
    ledger.adapter(Kernel::Inventory, bytes, mul(16, bytes)?)?;
    path.hold(ledger, mul(16, bytes)?)?;
    let parsed = if profile == 8 {
        crate::bootstrap_v2::decode_inventory(&envelope.payload)
    } else {
        crate::decode_inventory(&envelope.payload)
    };
    Ok(parsed
        .ok()
        .filter(|v| {
            v.inventory_version
                == if profile == 8 {
                    2
                } else if profile == 7 {
                    1
                } else {
                    0
                }
        })
        .filter(|v| {
            v.entries
                .first()
                .is_some_and(|e| super::envelope_agrees(&envelope, e))
        }))
}

fn retain_layout(
    inventory: &Inventory,
    units: usize,
    path: &mut PathState,
    ledger: &mut Ledger,
) -> Result<()> {
    let entries = inventory.entries.len() as u64;
    let edges = inventory
        .entries
        .iter()
        .map(|e| e.dependencies.len() as u64)
        .sum::<u64>();
    let workspace = add(mul(128, units as u64)?, mul(64, entries)?)?;
    ledger.adapter(Kernel::GroupLayout, units as u64, workspace)?;
    path.hold(ledger, add(workspace, mul(8, edges)?)?)?;
    ledger.adapter(
        Kernel::DependencyClosure,
        edges,
        add(mul(24, entries)?, mul(8, edges)?)?,
    )?;
    Ok(())
}

type CopyKey = (u16, u32, u16);
fn diagnostic_assemblies(
    lanes: &BTreeMap<u32, Lane>,
    profile: u16,
    ledger: &mut Ledger,
) -> Result<BTreeMap<u32, SectionResult>> {
    let mut copies = BTreeMap::<CopyKey, Vec<Lane>>::new();
    for lane in lanes
        .values()
        .filter(|l| l.block.profile_version == profile)
    {
        let b = &lane.block;
        copies
            .entry((profile, b.section_id, b.semantic_copy_id))
            .or_default()
            .push(lane.clone());
    }
    let mut values = BTreeMap::<u32, BTreeMap<Vec<u8>, bool>>::new();
    for ((_, id, _), rows) in copies {
        if let Some(raw) = assemble(&rows, profile, ledger)? {
            let mut verified = BTreeMap::new();
            for row in &rows {
                verified
                    .entry(row.block.fragment_index)
                    .and_modify(|v| *v |= row.verified)
                    .or_insert(row.verified);
            }
            let complete_verified = verified.values().all(|v| *v);
            values
                .entry(id)
                .or_default()
                .entry(raw)
                .and_modify(|v| *v |= complete_verified)
                .or_insert(complete_verified);
        }
    }
    Ok(values
        .into_iter()
        .map(|(id, mut values)| {
            let (state, envelope) = if values.len() == 1 {
                let (raw, verified) = values.pop_first().unwrap();
                (
                    if verified {
                        SectionState::Verified
                    } else {
                        SectionState::Recovered
                    },
                    Some(raw),
                )
            } else {
                (SectionState::Ambiguous, None)
            };
            (
                id,
                SectionResult {
                    section_id: id,
                    state,
                    envelope,
                },
            )
        })
        .collect())
}

fn envelope_state(envelope: &Option<Vec<u8>>, states: &[FragmentState]) -> SectionState {
    if envelope.is_some() {
        if states.iter().all(|s| *s == FragmentState::Verified) {
            SectionState::Verified
        } else {
            SectionState::Recovered
        }
    } else if states
        .iter()
        .any(|s| matches!(s, FragmentState::Corrupt | FragmentState::Ambiguous))
    {
        SectionState::Corrupt
    } else if states.contains(&FragmentState::Missing) {
        SectionState::Incomplete
    } else {
        SectionState::Corrupt
    }
}

impl FullOracleV2<'_> {
    fn hierarchical(
        &self,
        profile: u16,
        inputs: &BTreeMap<u32, Input>,
        lanes: &BTreeMap<u32, Lane>,
        geometry: Option<usize>,
        program: &Program,
        path: &mut PathState,
        ledger: &mut Ledger,
    ) -> Result<PathResult> {
        let first = choose_group(
            inputs,
            lanes,
            &[1, 2, 3, 4, 5],
            profile,
            None,
            program,
            path,
            ledger,
        )?;
        let mut inventory_state = if first.state == FragmentState::Missing {
            SectionState::Incomplete
        } else {
            SectionState::Corrupt
        };
        let mut inventory_raw = None;
        let mut bootstrap_lanes = BTreeMap::new();
        let mut bootstrap_identity = None;
        if let Some(first) = first.lane {
            let b = &first.block;
            if b.section_id == 1
                && b.semantic_copy_id == 0
                && b.fragment_index == 0
                && b.section_type == 1
                && b.section_version == if profile == 8 { 2 } else { 1 }
                && usize::from(b.fragment_count) * 5 <= 2389
            {
                bootstrap_identity = Some(b.clone());
                let mut selected = Vec::new();
                let mut states = Vec::new();
                for index in 0..b.fragment_count {
                    let expected = super::Expected {
                        id: 1,
                        kind: b.section_type,
                        version: b.section_version,
                        index,
                        count: b.fragment_count,
                        length: b.section_envelope_length,
                        replica: 0,
                        factor: 5,
                    };
                    let ids =
                        (u32::from(index) * 5 + 1..=u32::from(index) * 5 + 5).collect::<Vec<_>>();
                    let result = choose_group(
                        inputs,
                        lanes,
                        &ids,
                        profile,
                        Some(&expected),
                        program,
                        path,
                        ledger,
                    )?;
                    states.push(result.state);
                    if let Some(lane) = result.lane {
                        bootstrap_lanes.insert(u32::from(index) * 5 + 1, lane.clone());
                        selected.push(lane);
                    } else {
                        break;
                    }
                }
                if selected.len() == usize::from(b.fragment_count) {
                    inventory_raw = assemble(&selected, profile, ledger)?;
                }
                inventory_state = envelope_state(&inventory_raw, &states);
            }
        }
        let inventory = if let Some(raw) = &inventory_raw {
            parse_inventory(raw, profile, path, ledger)?
        } else {
            None
        };
        let inventory = inventory.filter(|inv| {
            super::layout(inv).ok().is_some_and(|layout| {
                layout.len() <= 2389 && geometry.is_none_or(|q| q == layout.len())
            })
        });
        if let Some(inventory) = inventory {
            let layout = super::layout(&inventory).map_err(|_| ScanError::Source)?;
            retain_layout(&inventory, layout.len(), path, ledger)?;
            let mut cursor = 1u32;
            let mut sections = Vec::new();
            for entry in &inventory.entries {
                let count = super::fragment_count(entry).map_err(|_| ScanError::Source)?;
                let mut selected = Vec::new();
                let mut states = Vec::new();
                for _ in 0..count {
                    let expected = &layout[&cursor];
                    let factor = u32::from(expected.factor);
                    let ids = (cursor..cursor + factor).collect::<Vec<_>>();
                    let result = choose_group(
                        inputs,
                        lanes,
                        &ids,
                        profile,
                        Some(expected),
                        program,
                        path,
                        ledger,
                    )?;
                    states.push(result.state);
                    if let Some(lane) = result.lane {
                        selected.push(lane);
                    }
                    cursor += factor;
                }
                let envelope = if selected.len() == usize::from(count) {
                    assemble(&selected, profile, ledger)?.filter(|raw| {
                        crate::decode_section(raw)
                            .ok()
                            .is_some_and(|e| super::envelope_agrees(&e, entry))
                    })
                } else {
                    None
                };
                let state = envelope_state(&envelope, &states);
                sections.push(SectionResult {
                    section_id: entry.section_id,
                    state,
                    envelope,
                });
            }
            let mut fragments = Vec::new();
            for id in layout
                .keys()
                .chain(inputs.keys())
                .copied()
                .collect::<BTreeSet<_>>()
            {
                let mut row = super::diagnostic(
                    id,
                    inputs.contains_key(&id),
                    lanes.get(&id),
                    layout.get(&id),
                    false,
                );
                if profile != 8 && layout.contains_key(&id) {
                    row.profile_version = Some(profile);
                }
                fragments.push(row);
            }
            let (required, all) = if profile == 8 {
                self.content(&sections, geometry.is_some(), program, path, ledger)?
            } else {
                (None, None)
            };
            let state = if required.is_none() {
                ArtifactState::Failure
            } else if all.is_some() && sections.iter().all(|s| s.envelope.is_some()) {
                ArtifactState::Exact
            } else {
                ArtifactState::Degraded
            };
            return Ok(PathResult {
                established: true,
                state,
                sections,
                fragments,
                required,
                all,
            });
        }
        // Discovery stops at the first failed inventory group. The separate
        // diagnostic procedure visits every declared group and preserves each
        // unique representative; logical group charges remain shared.
        if let Some(b) = bootstrap_identity {
            for index in 0..b.fragment_count {
                let expected = super::Expected {
                    id: 1,
                    kind: b.section_type,
                    version: b.section_version,
                    index,
                    count: b.fragment_count,
                    length: b.section_envelope_length,
                    replica: 0,
                    factor: 5,
                };
                let ids = (u32::from(index) * 5 + 1..=u32::from(index) * 5 + 5).collect::<Vec<_>>();
                let result = choose_group(
                    inputs,
                    lanes,
                    &ids,
                    profile,
                    Some(&expected),
                    program,
                    path,
                    ledger,
                )?;
                if let Some(lane) = result.lane {
                    bootstrap_lanes.insert(ids[0], lane);
                }
            }
        }
        let mut diagnostic_lanes = lanes
            .iter()
            .filter(|(_, l)| l.block.section_id != 1)
            .map(|(id, l)| (*id, l.clone()))
            .collect::<BTreeMap<_, _>>();
        diagnostic_lanes.extend(bootstrap_lanes.clone());
        let mut sections = diagnostic_assemblies(&diagnostic_lanes, profile, ledger)?;
        path.bootstrap.insert(profile, bootstrap_lanes);
        sections.insert(
            1,
            SectionResult {
                section_id: 1,
                state: inventory_state,
                envelope: inventory_raw,
            },
        );
        let mut ids = inputs.keys().copied().collect::<BTreeSet<_>>();
        ids.extend(1..=5);
        let fragments = ids
            .into_iter()
            .map(|id| {
                super::diagnostic(id, inputs.contains_key(&id), lanes.get(&id), None, id <= 5)
            })
            .collect();
        Ok(PathResult {
            established: false,
            state: ArtifactState::Failure,
            sections: sections.into_values().collect(),
            fragments,
            required: None,
            all: None,
        })
    }

    fn legacy(
        &self,
        profile: u16,
        lanes: &BTreeMap<u32, Lane>,
        path: &mut PathState,
        ledger: &mut Ledger,
    ) -> Result<()> {
        let inventory_lanes = lanes
            .iter()
            .filter(|(_, l)| l.block.section_id == 1)
            .map(|(id, l)| (*id, l.clone()))
            .collect();
        let inventory_sections = diagnostic_assemblies(&inventory_lanes, profile, ledger)?;
        let inventory =
            if let Some(raw) = inventory_sections.get(&1).and_then(|s| s.envelope.as_ref()) {
                parse_inventory(raw, profile, path, ledger)?
            } else {
                None
            };
        if let Some(inv) = inventory {
            let mut units = 0usize;
            for entry in &inv.entries {
                let check = if entry.check_id == 1 { 4 } else { 8 };
                let len = 18
                    + entry.dependencies.len() * 4
                    + entry.logical_payload_length as usize
                    + check;
                units = units
                    .checked_add(len.div_ceil(157) * usize::from(entry.copy_count))
                    .ok_or(ScanError::Resource)?;
            }
            retain_layout(&inv, units, path, ledger)?;
        }
        let _ = diagnostic_assemblies(lanes, profile, ledger)?;
        Ok(())
    }

    fn content(
        &self,
        sections: &[SectionResult],
        square: bool,
        program: &Program,
        path: &mut PathState,
        ledger: &mut Ledger,
    ) -> Result<(Option<Vec<u8>>, Option<Vec<u8>>)> {
        let checked = sections
            .iter()
            .filter_map(|s| {
                s.envelope
                    .as_ref()
                    .and_then(|raw| crate::decode_section(raw).ok())
                    .map(|envelope| (s.section_id, envelope))
            })
            .collect::<BTreeMap<_, _>>();
        let required = self.tier(2, &checked, square, program, path, ledger)?;
        let all = if required.is_some() {
            self.tier(3, &checked, square, program, path, ledger)?
        } else {
            None
        };
        Ok((required, all))
    }

    fn tier(
        &self,
        id: u32,
        checked: &BTreeMap<u32, crate::SectionEnvelope>,
        square: bool,
        program: &Program,
        path: &mut PathState,
        ledger: &mut Ledger,
    ) -> Result<Option<Vec<u8>>> {
        let Some(envelope) = checked.get(&id) else {
            return Ok(None);
        };
        let Some(tier) = tier_wire(&envelope.payload, id) else {
            return Ok(None);
        };
        if tier.body_section_ids != envelope.dependencies {
            return Ok(None);
        }
        for body_id in &tier.body_section_ids {
            if !path.bodies.contains_key(body_id) {
                let Some(body) = checked.get(body_id) else {
                    return Ok(None);
                };
                let workspace = add(body.payload.len() as u64, 32768)?;
                ledger.adapter(Kernel::BodyAdapter, body.payload.len() as u64, workspace)?;
                let adapter = ledger.retain(workspace)?;
                let decoded = if body.section_version == 1 {
                    if square {
                        ledger.adapter(
                            Kernel::ProgramRefinement,
                            program.storage.logical_nodes,
                            program.storage.refinement_extra_bytes,
                        )?;
                    }
                    let shape = program.shapes.get(&202).ok_or(ScanError::Source)?;
                    ledger.vm(shape.steps, shape.scratch)?;
                    let baseline = &self.programs[&8];
                    if !square || program.closure(&[202])? == baseline.closure(&[202])? {
                        crate::body_codec_v1::decode_body(1, &body.payload).ok()
                    } else {
                        let mut input = body.payload.clone();
                        input.resize(16384, 0);
                        input.extend((body.payload.len() as u16).to_be_bytes());
                        let output = crate::recipe::evaluate_serialized_validated_recipe(
                            &program.logical,
                            202,
                            &input,
                        )
                        .map_err(|_| ScanError::Unsupported)?;
                        if output.len() == 16388 && output[..2] == [0, 0] {
                            let count =
                                usize::from(u16::from_be_bytes(output[2..4].try_into().unwrap()));
                            if count <= 16384 && output[4 + count..].iter().all(|v| *v == 0) {
                                Some(output[4..4 + count].to_vec())
                            } else {
                                None
                            }
                        } else {
                            None
                        }
                    }
                } else {
                    crate::body_codec_v1::decode_body(body.section_version, &body.payload).ok()
                };
                ledger.release(adapter)?;
                if let Some(raw) = &decoded {
                    path.hold(ledger, add(raw.len() as u64, 8)?)?;
                }
                path.bodies.insert(*body_id, decoded);
            }
            if path.bodies[body_id].is_none() {
                return Ok(None);
            }
        }
        let bytes = u64::from(tier.assembled_stream_byte_length);
        let records = u64::from(tier.assembled_record_count);
        let initial = resources::content_workspace(bytes, records, 0)?;
        ledger.adapter(Kernel::ContentValidation, bytes, initial)?;
        let mut adapter = ledger.retain(initial)?;
        let mut raw = vec![0, 0];
        raw.extend(tier.assembled_record_count.to_be_bytes());
        for body in &tier.body_section_ids {
            raw.extend(path.bodies[body].as_ref().unwrap());
        }
        raw.extend(&tier.root_record_bytes);
        if raw.len() as u64 != bytes {
            ledger.release(adapter)?;
            return Ok(None);
        }
        let aliases = content_aliases(&raw);
        let complete = resources::content_workspace(bytes, records, aliases)?;
        ledger.release(adapter)?;
        ledger.adapter_peak(Kernel::ContentValidation, complete)?;
        adapter = ledger.retain(complete)?;
        let valid = gb_content::stream_validation(&raw).is_ok();
        ledger.release(adapter)?;
        if valid {
            path.hold(ledger, raw.len() as u64)?;
            Ok(Some(raw))
        } else {
            Ok(None)
        }
    }
}

// Only the bounded tier envelope is decoded here. ROOT and complete content
// semantics are checked at the reached content-validation boundary, after
// selected body decoding, even when those semantics will fail.
fn tier_wire(raw: &[u8], section: u32) -> Option<crate::TierFrame> {
    if !(27..=crate::MAX_ENVELOPE_BYTES).contains(&raw.len()) {
        return None;
    }
    let n16 = |at| u16::from_be_bytes([raw[at], raw[at + 1]]);
    let n32 = |at| u32::from_be_bytes(raw[at..at + 4].try_into().unwrap());
    let count = usize::from(n16(4));
    let bytes = n32(8);
    let records = n16(12);
    let root = n32(14) as usize;
    if n16(0) != 0
        || raw[3] != 0
        || n16(6) != 0
        || n16(18) != 0
        || n16(20) != records
        || !matches!((section, raw[2]), (2, 0) | (3, 1))
        || count == 0
        || count > crate::MAX_TIER_BODY_IDS
        || bytes == 0
        || bytes as usize > crate::MAX_ENVELOPE_BYTES
        || records < 2
        || root == 0
    {
        return None;
    }
    let end = 22usize.checked_add(count.checked_mul(4)?)?;
    if end.checked_add(root)? != raw.len() {
        return None;
    }
    let mut ids = Vec::with_capacity(count);
    let mut prior = 0;
    for index in 0..count {
        let id = n32(22 + index * 4);
        if id <= prior {
            return None;
        }
        ids.push(id);
        prior = id;
    }
    Some(crate::TierFrame {
        tier_id: raw[2],
        body_section_ids: ids,
        assembled_stream_byte_length: bytes,
        assembled_record_count: records,
        root_record_bytes: raw[end..].to_vec(),
    })
}

fn content_aliases(raw: &[u8]) -> u64 {
    if raw.len() < 4 {
        return 0;
    }
    let count = usize::from(u16::from_be_bytes([raw[2], raw[3]]));
    let mut regions = BTreeMap::new();
    let mut lessons = Vec::new();
    let mut cursor = 4usize;
    for _ in 0..count {
        let Some(header) = raw.get(cursor..cursor + 8) else {
            return 0;
        };
        let id = u16::from_be_bytes([header[0], header[1]]);
        let kind = u16::from_be_bytes([header[2], header[3]]);
        let length = u32::from_be_bytes(header[4..8].try_into().unwrap()) as usize;
        let Some(end) = cursor.checked_add(8).and_then(|v| v.checked_add(length)) else {
            return 0;
        };
        let Some(payload) = raw.get(cursor + 8..end) else {
            return 0;
        };
        if kind == 7 && payload.len() >= 4 {
            regions.insert(id, u16::from_be_bytes([payload[2], payload[3]]).min(4096));
        }
        if kind == 13 && payload.len() >= 8 && lessons.len() < 4096 {
            lessons.push(u16::from_be_bytes([payload[6], payload[7]]));
        }
        cursor = end;
    }
    lessons
        .iter()
        .map(|id| u64::from(*regions.get(id).unwrap_or(&0)))
        .sum()
}

fn extract(
    matrix: &Matrix,
    route: &RoutePath,
    ledger: &mut Ledger,
) -> Result<BTreeMap<u32, Input>> {
    let map = &route.mapping;
    ledger.adapter(
        Kernel::UnitExtraction,
        mul(map.units, u64::from(map.unit_bytes) * 8)?,
        mul(map.units, 8 + 2 * u64::from(map.unit_bytes))?,
    )?;
    let mut inputs = BTreeMap::new();
    for id in 1..=map.units {
        let mut input = Input {
            bytes: vec![0; usize::from(map.unit_bytes)],
            erased: vec![],
        };
        for bit in 0..map.unit_bytes * 8 {
            let flat = map.physical(id, bit)?;
            let r = usize::from(map.width) + (flat / u64::from(map.interior)) as usize;
            let c = usize::from(map.width) + (flat % u64::from(map.interior)) as usize;
            let value = matrix.value(route.transform, route.polarity, r, c);
            if value == 2 {
                if matches!(route.profile, 5 | 6) {
                    return Err(ScanError::Unsupported);
                }
                input.erased.push(crate::candidate::EhErasure {
                    codeword: (bit / 72) as u8,
                    position: (bit % 72 + 1) as u8,
                });
            } else {
                input.bytes[usize::from(bit / 8)] |= value << (7 - bit % 8);
            }
        }
        inputs.insert(id as u32, input);
    }
    Ok(inputs)
}

fn consider(value: PathResult, prior: &mut Vec<PathResult>, ledger: &mut Ledger) -> Result<()> {
    let size = value.footprint()?;
    ledger.adapter(
        Kernel::ResultSelection,
        mul(size, prior.len().max(1) as u64)?,
        size,
    )?;
    if !prior.contains(&value) {
        let lease = ledger.retain(size)?;
        ledger.persist(lease)?;
        prior.push(value);
    }
    Ok(())
}
fn select(candidates: &[PathResult]) -> PathResult {
    let established = candidates
        .iter()
        .filter(|v| v.established)
        .collect::<Vec<_>>();
    match established.len() {
        0 if candidates.len() == 1 => candidates[0].clone(),
        0 => PathResult::closed(ArtifactState::Failure),
        1 => established[0].clone(),
        _ => PathResult::closed(ArtifactState::Ambiguous),
    }
}
fn resource_value(ledger: &Ledger) -> V {
    let r = ledger.resource();
    object([
        ("section_attempts", V::U64(r.section_attempts)),
        ("primitive_steps", V::U64(r.primitive_steps)),
        ("peak_scratch_bytes", V::U64(r.peak_scratch_bytes)),
    ])
}
fn fragment_value(f: &FragmentDiagnostic) -> Result<V> {
    Ok(object([
        ("input_id", V::U64(u64::from(f.input_id))),
        (
            "profile_id",
            string(match f.profile_version {
                Some(p) => profile_name(p)?,
                None => "",
            }),
        ),
        ("section_id", V::U64(u64::from(f.section_id))),
        ("semantic_copy_id", V::U64(u64::from(f.semantic_copy_id))),
        ("fragment_index", V::U64(u64::from(f.fragment_index))),
        ("replica_index", V::U64(u64::from(f.replica_index))),
        (
            "physical_replica_count",
            V::U64(u64::from(f.physical_replica_count)),
        ),
        ("state", string(fragment_state(f.state))),
        ("common_block_sha256", string(&f.common_block_sha256)),
    ]))
}
fn render(
    channel: &str,
    value: &mut PathResult,
    hypotheses: &mut BTreeSet<Hypothesis>,
    ledger: &mut Ledger,
) -> Result<Vec<u8>> {
    loop {
        ledger.adapter(Kernel::ResultRender, 0, 1_048_576 + 256)?;
        let fragments = value
            .fragments
            .iter()
            .map(fragment_value)
            .collect::<Result<Vec<_>>>()?;
        let wrapper = serialize_manifest(&object([("rows", V::Array(fragments))]));
        let wrapper = match wrapper {
            Ok(raw) if raw.len() <= 1_048_576 => raw,
            _ => {
                ledger.adapter_work(Kernel::ResultRender, 1_048_577)?;
                *value = PathResult::closed(ArtifactState::ResourceLimit);
                hypotheses.clear();
                continue;
            }
        };
        ledger.adapter_work(Kernel::ResultRender, wrapper.len() as u64)?;
        // canonical wrapper is exactly {"rows":ARRAY}\n; hash only ARRAY.
        if !wrapper.starts_with(b"{\"rows\":") || !wrapper.ends_with(b"}\n") {
            return Err(ScanError::Source);
        }
        let fragment_hash = hash(&wrapper[8..wrapper.len() - 2]);
        let accepted = hypotheses
            .iter()
            .map(|h| {
                Ok(object([
                    ("transform_id", V::U64(u64::from(h.transform))),
                    ("polarity_id", V::U64(u64::from(h.polarity))),
                    ("sector_id", V::U64(u64::from(h.sector))),
                    ("profile_id", string(profile_name(h.profile)?)),
                    ("mapping_sha256", string(&h.mapping_sha256)),
                ]))
            })
            .collect::<Result<Vec<_>>>()?;
        let sections = value
            .sections
            .iter()
            .map(|s| {
                object([
                    ("section_id", V::U64(u64::from(s.section_id))),
                    ("state", string(section_state(s.state))),
                    (
                        "semantic_sha256",
                        string(
                            &s.envelope
                                .as_ref()
                                .map_or_else(|| ZERO.to_owned(), |v| hash(v)),
                        ),
                    ),
                ])
            })
            .collect();
        let object = object([
            ("schema", string("golden-board.m2-damage-decoder-result/v2")),
            ("channel", string(channel)),
            ("artifact_state", string(artifact_state(value.state))),
            (
                "established_profile_id",
                string(if value.established {
                    profile_name(8)?
                } else {
                    ""
                }),
            ),
            ("section_rows", V::Array(sections)),
            ("fragment_diagnostics_sha256", string(&fragment_hash)),
            ("m2_required_available", V::Bool(value.required.is_some())),
            ("m2_all_available", V::Bool(value.all.is_some())),
            (
                "m2_required_stream_sha256",
                string(
                    &value
                        .required
                        .as_ref()
                        .map_or_else(|| ZERO.to_owned(), |v| hash(v)),
                ),
            ),
            (
                "m2_all_stream_sha256",
                string(
                    &value
                        .all
                        .as_ref()
                        .map_or_else(|| ZERO.to_owned(), |v| hash(v)),
                ),
            ),
            ("resource", resource_value(ledger)),
            ("accepted_hypothesis_rows", V::Array(accepted)),
        ]);
        match serialize_manifest(&object) {
            Ok(raw) if raw.len() <= 1_048_576 => {
                ledger.adapter_work(Kernel::ResultRender, raw.len() as u64)?;
                return Ok(raw);
            }
            _ => {
                ledger.adapter_work(Kernel::ResultRender, 1_048_577)?;
                *value = PathResult::closed(ArtifactState::ResourceLimit);
                hypotheses.clear();
            }
        }
    }
}
fn resource_sidecar(channel: &str, raw: &[u8], result: &[u8], ledger: &Ledger) -> Result<Vec<u8>> {
    let owners = source_owners();
    let rows = Kernel::ALL
        .iter()
        .map(|k| {
            let r = ledger.row(*k);
            object([
                ("kernel", string(k.name())),
                ("calls", V::U64(r.calls)),
                ("reference_input_units", V::U64(r.reference_input_units)),
                ("peak_workspace_bytes", V::U64(r.peak_workspace_bytes)),
            ])
        })
        .collect();
    serialize_manifest(&object([
        ("schema", string("golden-board.m2-observation-resources/v2")),
        ("channel", string(channel)),
        ("observation_sha256", string(&hash(raw))),
        ("result_sha256", string(&hash(result))),
        ("source_owners", owners),
        ("resource", resource_value(ledger)),
        ("adapter_rows", V::Array(rows)),
    ]))
    .map_err(|_| ScanError::Source)
}

fn source_owners() -> V {
    object([
        (
            "spec/profile-policy-v2.toml",
            string(&hash(include_bytes!(
                "../../../spec/profile-policy-v2.toml"
            ))),
        ),
        (
            "spec/profile-limits-v2.toml",
            string(&hash(include_bytes!(
                "../../../spec/profile-limits-v2.toml"
            ))),
        ),
        (
            "spec/damage-policy-v2.toml",
            string(&hash(include_bytes!("../../../spec/damage-policy-v2.toml"))),
        ),
        (
            "spec/resource-accounting-v2.md",
            string(&hash(include_bytes!(
                "../../../spec/resource-accounting-v2.md"
            ))),
        ),
    ])
}

fn closed_object<'a>(value: &'a V, keys: &[&str]) -> Result<&'a BTreeMap<String, V>> {
    let V::Object(rows) = value else {
        return Err(ScanError::Source);
    };
    if rows.len() != keys.len() || keys.iter().any(|k| !rows.contains_key(*k)) {
        return Err(ScanError::Source);
    }
    Ok(rows)
}
fn replay_row(
    identity: &[u8],
    projection: &CompleteProjection,
    required: &BTreeSet<u32>,
) -> Result<Vec<u8>> {
    let observation =
        gb_foundation::validate_canonical_manifest(identity).map_err(|_| ScanError::Source)?;
    let obs = closed_object(
        &observation,
        &[
            "schema",
            "case_id",
            "family_id",
            "case_ordinal",
            "channel",
            "operator",
            "parameter_projection",
            "observation_bytes",
            "observation_sha256",
        ],
    )?;
    if obs["schema"] != string("golden-board.damage-observation/v2") {
        return Err(ScanError::Source);
    }
    let V::String(family) = &obs["family_id"] else {
        return Err(ScanError::Source);
    };
    let V::U64(ordinal) = obs["case_ordinal"] else {
        return Err(ScanError::Source);
    };
    if obs["case_id"] != string(&format!("{family}-{ordinal:06}"))
        || projection.semantic.boundary != (family == "B0")
    {
        return Err(ScanError::Source);
    }
    let result = gb_foundation::validate_canonical_manifest(&projection.result)
        .map_err(|_| ScanError::Source)?;
    let result_fields = closed_object(
        &result,
        &[
            "schema",
            "channel",
            "artifact_state",
            "established_profile_id",
            "section_rows",
            "fragment_diagnostics_sha256",
            "m2_required_available",
            "m2_all_available",
            "m2_required_stream_sha256",
            "m2_all_stream_sha256",
            "resource",
            "accepted_hypothesis_rows",
        ],
    )?;
    let resources = gb_foundation::validate_canonical_manifest(&projection.sidecar)
        .map_err(|_| ScanError::Source)?;
    let fields = closed_object(
        &resources,
        &[
            "schema",
            "channel",
            "observation_sha256",
            "result_sha256",
            "source_owners",
            "resource",
            "adapter_rows",
        ],
    )?;
    if result_fields["schema"] != string("golden-board.m2-damage-decoder-result/v2")
        || fields["schema"] != string("golden-board.m2-observation-resources/v2")
        || result_fields["channel"] != obs["channel"]
        || fields["channel"] != obs["channel"]
        || fields["observation_sha256"] != obs["observation_sha256"]
        || fields["result_sha256"] != string(&hash(&projection.result))
        || fields["resource"] != result_fields["resource"]
        || fields["source_owners"] != source_owners()
        || result_fields["artifact_state"] != string(artifact_state(projection.semantic.state))
    {
        return Err(ScanError::Source);
    }
    let counters = closed_object(
        &fields["resource"],
        &["section_attempts", "primitive_steps", "peak_scratch_bytes"],
    )?;
    if counters.values().any(|v| !matches!(v, V::U64(_))) {
        return Err(ScanError::Source);
    }
    let V::Array(adapters) = &fields["adapter_rows"] else {
        return Err(ScanError::Source);
    };
    if adapters.len() != Kernel::ALL.len() {
        return Err(ScanError::Source);
    }
    for (row, kernel) in adapters.iter().zip(Kernel::ALL) {
        let row = closed_object(
            row,
            &[
                "kernel",
                "calls",
                "reference_input_units",
                "peak_workspace_bytes",
            ],
        )?;
        if row["kernel"] != string(kernel.name())
            || ["calls", "reference_input_units", "peak_workspace_bytes"]
                .iter()
                .any(|k| !matches!(row[*k], V::U64(_)))
        {
            return Err(ScanError::Source);
        }
    }
    let states = projection
        .semantic
        .states
        .iter()
        .copied()
        .collect::<BTreeMap<_, _>>();
    if states.len() != projection.semantic.states.len()
        || !required.iter().all(|id| states.contains_key(id))
    {
        return Err(ScanError::Source);
    }
    let V::Array(visible) = &result_fields["section_rows"] else {
        return Err(ScanError::Source);
    };
    if visible.len() != projection.semantic.sections.len() {
        return Err(ScanError::Source);
    }
    for (value, section) in visible.iter().zip(&projection.semantic.sections) {
        let value = closed_object(value, &["section_id", "state", "semantic_sha256"])?;
        if value["section_id"] != V::U64(u64::from(section.section_id))
            || value["state"] != string(section_state(section.state))
            || states.get(&section.section_id) != Some(&section.state)
            || section.state == SectionState::Unknown
            || value["semantic_sha256"]
                != string(
                    &section
                        .envelope
                        .as_ref()
                        .map_or_else(|| ZERO.to_owned(), |v| hash(v)),
                )
        {
            return Err(ScanError::Source);
        }
    }
    let good = |s: &SectionState| matches!(s, SectionState::Verified | SectionState::Recovered);
    let fulfilled = match family.as_str() {
        "D0" | "D1" | "D5" => states.values().all(good),
        "D2" | "D3" | "D4" | "D6" => required.iter().all(|id| good(&states[id])),
        "D7" | "B0" => true,
        _ => return Err(ScanError::Source),
    } && (family == "B0" || projection.semantic.wrong == 0);
    let expected = projection
        .semantic
        .states
        .iter()
        .map(|(id, state)| {
            object([
                ("section_id", V::U64(u64::from(*id))),
                ("state", string(section_state(*state))),
            ])
        })
        .collect();
    serialize_manifest(&object([
        ("schema", string("golden-board.m2-damage-replay-case/v2")),
        ("observation", observation),
        ("decoder_result", result),
        ("resource_projection", resources),
        ("expected_section_states", V::Array(expected)),
        ("wrong_accept_count", V::U64(projection.semantic.wrong)),
        ("reauthored_boundary", V::Bool(projection.semantic.boundary)),
        (
            "promise_result",
            string(if fulfilled { "pass" } else { "fail" }),
        ),
    ]))
    .map_err(|_| ScanError::Source)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn incomplete_copy_charges_only_constructed_bytes_before_check() {
        let envelope = crate::encode_section(&crate::SectionEnvelope {
            section_id: 4005,
            section_type: 6,
            section_version: 0,
            closure_class: 129,
            check_id: 1,
            dependencies: vec![],
            payload: vec![42; 200],
        })
        .unwrap();
        assert_eq!(envelope.len(), 222);
        let lanes = envelope
            .chunks(157)
            .enumerate()
            .map(|(index, payload)| {
                let block = CommonBlock {
                    profile_version: 8,
                    section_id: 4005,
                    semantic_copy_id: 0,
                    section_type: 6,
                    section_version: 0,
                    fragment_index: index as u16,
                    fragment_count: 2,
                    section_envelope_length: envelope.len() as u32,
                    payload: payload.to_vec(),
                };
                Lane {
                    raw: crate::encode_common_block(&block).unwrap(),
                    block,
                    verified: true,
                }
            })
            .collect::<Vec<_>>();
        let mut ledger = Ledger::new();
        for _ in 0..2 {
            assert!(assemble(&lanes[..1], 8, &mut ledger).unwrap().is_none());
        }
        assert_eq!(ledger.row(Kernel::SectionAssembly).calls, 2);
        assert_eq!(
            ledger.row(Kernel::SectionAssembly).reference_input_units,
            382
        );
        assert_eq!(ledger.row(Kernel::SectionAssembly).peak_workspace_bytes, 24);
        assert_eq!(ledger.resource().section_attempts, 0);
        let mut ledger = Ledger::new();
        assert_eq!(assemble(&lanes, 8, &mut ledger).unwrap(), Some(envelope));
        assert_eq!(
            ledger.row(Kernel::SectionAssembly).peak_workspace_bytes,
            270
        );
        assert_eq!(ledger.resource().section_attempts, 1);
        let mut malformed = lanes;
        malformed[0].block.payload[2..6].copy_from_slice(&4006u32.to_be_bytes());
        malformed[0].raw = crate::encode_common_block(&malformed[0].block).unwrap();
        let mut ledger = Ledger::new();
        assert!(assemble(&malformed, 8, &mut ledger).unwrap().is_none());
        assert_eq!(
            ledger.row(Kernel::SectionAssembly).peak_workspace_bytes,
            270
        );
        assert_eq!(ledger.resource().section_attempts, 0);
    }

    #[test]
    fn raw_copy_preserves_duplicate_work_and_rejects_identity_conflicts_before_check() {
        let envelope = crate::encode_section(&crate::SectionEnvelope {
            section_id: 16,
            section_type: 3,
            section_version: 0,
            closure_class: 128,
            check_id: 1,
            dependencies: vec![],
            payload: vec![42],
        })
        .unwrap();
        let block = CommonBlock {
            profile_version: 8,
            section_id: 16,
            semantic_copy_id: 0,
            section_type: 3,
            section_version: 0,
            fragment_index: 0,
            fragment_count: 1,
            section_envelope_length: envelope.len() as u32,
            payload: envelope,
        };
        let lane = Lane {
            raw: crate::encode_common_block(&block).unwrap(),
            block,
            verified: true,
        };
        let mut recovered = lane.clone();
        recovered.verified = false;
        let mut ledger = Ledger::new();
        let rows = diagnostic_assemblies(
            &BTreeMap::from([(1, lane.clone()), (2, recovered)]),
            8,
            &mut ledger,
        )
        .unwrap();
        assert_eq!(rows[&16].state, SectionState::Verified);
        assert_eq!(
            ledger.row(Kernel::SectionAssembly).reference_input_units,
            382
        );
        assert_eq!(ledger.resource().section_attempts, 1);
        let mut changed = lane.clone();
        changed.block.section_version = 1;
        changed.raw = crate::encode_common_block(&changed.block).unwrap();
        let mut ledger = Ledger::new();
        assert!(
            diagnostic_assemblies(&BTreeMap::from([(1, lane), (2, changed)]), 8, &mut ledger)
                .unwrap()
                .is_empty()
        );
        assert_eq!(ledger.row(Kernel::SectionAssembly).calls, 1);
        assert_eq!(
            ledger.row(Kernel::SectionAssembly).reference_input_units,
            382
        );
        assert_eq!(ledger.resource().section_attempts, 0);
    }

    #[test]
    fn tier_wire_defers_root_semantics_without_relaxing_framing() {
        let tier = crate::TierFrame {
            tier_id: 0,
            body_section_ids: vec![16],
            assembled_stream_byte_length: 25,
            assembled_record_count: 2,
            root_record_bytes: vec![0, 2, 0, 14, 0, 0, 0, 4, 0, 1, 0, 1],
        };
        let mut raw = crate::encode_tier_frame(&tier).unwrap();
        assert_eq!(tier_wire(&raw, 2), Some(tier.clone()));
        let n = raw.len();
        raw[n - 2..].fill(0);
        assert!(crate::decode_tier_frame(&raw, 2).is_err());
        assert!(tier_wire(&raw, 2).is_some());
        raw[13] = 3;
        assert!(tier_wire(&raw, 2).is_none());
        let raw = crate::encode_tier_frame(&tier).unwrap();
        assert!(tier_wire(&raw[..raw.len() - 1], 2).is_none());
        assert!(tier_wire(&raw, 3).is_none());
    }

    #[test]
    fn selection_compares_before_dedup_and_keeps_established_failure() {
        let mut failed = PathResult::closed(ArtifactState::Failure);
        failed.sections.push(SectionResult {
            section_id: 1,
            state: SectionState::Corrupt,
            envelope: None,
        });
        let mut established = failed.clone();
        established.established = true;
        established.sections[0].state = SectionState::Verified;
        established.sections[0].envelope = Some(vec![1, 2, 3]);
        let mut ledger = Ledger::new();
        let mut rows = vec![];
        consider(failed.clone(), &mut rows, &mut ledger).unwrap();
        consider(failed.clone(), &mut rows, &mut ledger).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(ledger.row(Kernel::ResultSelection).calls, 2);
        assert_eq!(
            ledger.row(Kernel::ResultSelection).reference_input_units,
            96
        );
        consider(established.clone(), &mut rows, &mut ledger).unwrap();
        assert_eq!(select(&rows), established);
        let mut changed = established.clone();
        changed.sections[0].envelope = Some(vec![4, 5, 6]);
        consider(changed, &mut rows, &mut ledger).unwrap();
        assert_eq!(select(&rows).state, ArtifactState::Ambiguous);
        assert_eq!(
            ledger.row(Kernel::ResultSelection).reference_input_units,
            96 + 51 + 102
        );
        let different = PathResult::closed(ArtifactState::Failure);
        assert!(select(&[failed, different]).sections.is_empty());
    }

    #[test]
    fn one_render_event_counts_wrapper_and_final_after_counter_freeze() {
        let mut ledger = Ledger::new();
        let retained = ledger.retain(48).unwrap();
        ledger.persist(retained).unwrap();
        ledger.retain(9999).unwrap();
        ledger.release_transients().unwrap();
        let mut value = PathResult::closed(ArtifactState::Failure);
        let raw = render("OBS_UNITS", &mut value, &mut BTreeSet::new(), &mut ledger).unwrap();
        assert_eq!(ledger.row(Kernel::ResultRender).calls, 1);
        assert_eq!(
            ledger.row(Kernel::ResultRender).reference_input_units,
            12 + raw.len() as u64
        );
        assert_eq!(
            ledger.row(Kernel::ResultRender).peak_workspace_bytes,
            1_048_832
        );
        assert_eq!(ledger.resource().peak_scratch_bytes, 48 + 1_048_832);
        let parsed = gb_foundation::validate_canonical_manifest(&raw).unwrap();
        let V::Object(object) = parsed else {
            panic!("object");
        };
        assert_eq!(object["fragment_diagnostics_sha256"], string(&hash(b"[]")));
        assert_eq!(object["resource"], resource_value(&ledger));
        assert_eq!(object["established_profile_id"], string(""));
    }
}
