//! Independent owned-observation oracles: a partial semantic projection and a
//! complete route/resource composition. Neither calls a production receiver or
//! consumes saved receiver results; neither awards a gate.
use crate::candidate::{self, DecodeQuality, EhErasure};
use crate::damage::{
    ArtifactState, FragmentState, ObsMatrix, ObsUnits, SectionResult, SectionState,
};
use crate::damage_corpus_v2::DamageCorpusV2;
use crate::{CommonBlock, Inventory, InventoryEntry};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
#[path = "damage_oracle_v2_full.rs"]
mod full;
#[path = "damage_oracle_v2_resources.rs"]
pub mod resources;
#[path = "damage_oracle_v2_routes.rs"]
pub mod routes;
pub use full::{CompleteProjection, FullOracleV2};
const ZERO: &str = "0000000000000000000000000000000000000000000000000000000000000000";
const ABSENT: u16 = u16::MAX;
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum OracleError {
    OwnedObservation,
    Bounds,
    Source,
}
pub type Result<T> = std::result::Result<T, OracleError>;
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FragmentDiagnostic {
    pub input_id: u32,
    pub profile_version: Option<u16>,
    pub section_id: u32,
    pub semantic_copy_id: u16,
    pub fragment_index: u16,
    pub replica_index: u16,
    pub physical_replica_count: u16,
    pub state: FragmentState,
    pub common_block_sha256: String,
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticProjection {
    state: ArtifactState,
    states: Vec<(u32, SectionState)>,
    sections: Vec<SectionResult>,
    fragments: Vec<FragmentDiagnostic>,
    wrong: u64,
    required: Option<Vec<u8>>,
    all: Option<Vec<u8>>,
    boundary: bool,
}
impl SemanticProjection {
    pub fn artifact_state(&self) -> ArtifactState {
        self.state
    }
    pub fn section_states(&self) -> &[(u32, SectionState)] {
        &self.states
    }
    pub fn sections(&self) -> &[SectionResult] {
        &self.sections
    }
    pub fn fragments(&self) -> &[FragmentDiagnostic] {
        &self.fragments
    }
    pub fn wrong_accepts(&self) -> u64 {
        self.wrong
    }
    pub fn required_stream(&self) -> Option<&[u8]> {
        self.required.as_deref()
    }
    pub fn all_stream(&self) -> Option<&[u8]> {
        self.all.as_deref()
    }
    pub fn reauthored_boundary(&self) -> bool {
        self.boundary
    }
}
#[derive(Clone)]
struct Input {
    bytes: Vec<u8>,
    erased: Vec<EhErasure>,
}
#[derive(Clone)]
struct Lane {
    raw: [u8; 191],
    block: CommonBlock,
    verified: bool,
}
#[derive(Clone, Debug)]
struct Expected {
    id: u32,
    kind: u16,
    version: u16,
    index: u16,
    count: u16,
    length: u32,
    replica: u16,
    factor: u16,
}
impl Expected {
    fn agrees(&self, b: &CommonBlock) -> bool {
        b.profile_version == 8
            && b.section_id == self.id
            && b.semantic_copy_id == 0
            && b.section_type == self.kind
            && b.section_version == self.version
            && b.fragment_index == self.index
            && b.fragment_count == self.count
            && b.section_envelope_length == self.length
    }
}
struct Group {
    state: FragmentState,
    lane: Option<Lane>,
}
pub struct SemanticOracleV2<'a> {
    source: &'a DamageCorpusV2,
}
impl<'a> SemanticOracleV2<'a> {
    pub fn new(source: &'a DamageCorpusV2) -> Self {
        Self { source }
    }
    fn finish(
        &self,
        state: ArtifactState,
        mut sections: Vec<SectionResult>,
        fragments: Vec<FragmentDiagnostic>,
        required: Option<Vec<u8>>,
        all: Option<Vec<u8>>,
        boundary: bool,
    ) -> Result<SemanticProjection> {
        sections.sort_by_key(|s| s.section_id);
        let visible: BTreeMap<_, _> = sections.iter().map(|s| (s.section_id, s.state)).collect();
        let core = self.source.source_core();
        let states = core
            .sections
            .iter()
            .map(|s| {
                (
                    s.section_id,
                    *visible.get(&s.section_id).unwrap_or(&SectionState::Unknown),
                )
            })
            .collect();
        let clean: BTreeMap<_, _> = core
            .sections
            .iter()
            .map(|s| {
                s.envelope()
                    .map(|v| (s.section_id, v))
                    .map_err(|_| OracleError::Source)
            })
            .collect::<Result<_>>()?;
        let wrong = sections
            .iter()
            .filter(|s| {
                s.envelope
                    .as_ref()
                    .is_some_and(|bytes| clean.get(&s.section_id) != Some(bytes))
            })
            .count() as u64;
        Ok(SemanticProjection {
            state,
            states,
            sections,
            fragments,
            wrong,
            required,
            all,
            boundary,
        })
    }
    pub fn project(&self, family: &str, ordinal: u64, raw: &[u8]) -> Result<SemanticProjection> {
        // This partial oracle is defined for exact owned corpus observations.
        // Case metadata proves the explicitly owned framing/resource exceptions;
        // all recovered data below is extracted from the supplied bytes.
        let owned = self
            .source
            .case(family, ordinal)
            .map_err(|_| OracleError::OwnedObservation)?;
        if owned.bytes() != raw {
            return Err(OracleError::OwnedObservation);
        }
        let boundary = family == "B0";
        if family == "D7" && (405..=413).contains(&ordinal) {
            return self.finish(
                if ordinal <= 406 {
                    ArtifactState::ResourceLimit
                } else {
                    ArtifactState::Failure
                },
                vec![],
                vec![],
                None,
                None,
                boundary,
            );
        }
        let square = owned.channel() != "OBS_UNITS";
        let inputs = self.extract(owned.channel(), family, ordinal, raw)?;
        let mut lanes = BTreeMap::new();
        for (id, input) in &inputs {
            let known = self
                .source
                .source_core()
                .units
                .get((*id as usize).wrapping_sub(1));
            let lane = if input.erased.is_empty()
                && known.is_some_and(|unit| input.bytes == unit.encoded)
            {
                let common = self.source.source_commons()[*id as usize - 1];
                Some(Lane {
                    raw: common,
                    block: crate::decode_common_block(&common, 8)
                        .map_err(|_| OracleError::Source)?,
                    verified: true,
                })
            } else {
                decode_lane(input)
            };
            if let Some(lane) = lane {
                lanes.insert(*id, lane);
            }
        }
        let bootstrap = group(&inputs, &lanes, &[1, 2, 3, 4, 5], None);
        let mut inventory_section = None;
        let mut inventory_state = if bootstrap.state == FragmentState::Missing {
            SectionState::Incomplete
        } else {
            SectionState::Corrupt
        };
        if let Some(first) = &bootstrap.lane {
            let b = &first.block;
            if b.section_id == 1
                && b.semantic_copy_id == 0
                && b.fragment_index == 0
                && b.section_type == crate::SECTION_INVENTORY
                && b.section_version == 2
                && usize::from(b.fragment_count) * 5 <= 2389
            {
                let mut recovered = Vec::new();
                let mut all_verified = true;
                for index in 0..b.fragment_count {
                    let expected = Expected {
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
                    let row = group(&inputs, &lanes, &ids, Some(&expected));
                    all_verified &= row.state == FragmentState::Verified;
                    if let Some(lane) = row.lane {
                        recovered.push(lane)
                    } else {
                        recovered.clear();
                        break;
                    }
                }
                if let Some(raw) = assemble_unique(&recovered) {
                    inventory_state = if all_verified {
                        SectionState::Verified
                    } else {
                        SectionState::Recovered
                    };
                    inventory_section = Some(raw);
                }
            }
        }
        let inventory = inventory_section
            .as_ref()
            .and_then(|raw| crate::decode_section(raw).ok())
            .and_then(|s| {
                crate::bootstrap_v2::decode_inventory(&s.payload)
                    .ok()
                    .filter(|inventory| envelope_agrees(&s, &inventory.entries[0]))
            })
            .filter(|inventory| {
                let Ok(layout) = layout(inventory) else {
                    return false;
                };
                (!square || layout.len() == self.source.source_core().units.len())
                    && layout.len() <= 2389
            });
        if let Some(inventory) = inventory {
            let layout = layout(&inventory)?;
            let mut sections = Vec::new();
            let mut cursor = 1u32;
            for entry in &inventory.entries {
                let count = fragment_count(entry)?;
                let mut recovered = Vec::new();
                let mut states = Vec::new();
                for index in 0..count {
                    let shape = &layout[&cursor];
                    let factor = u32::from(shape.factor);
                    let ids = (cursor..cursor + factor).collect::<Vec<_>>();
                    let value = group(&inputs, &lanes, &ids, Some(shape));
                    states.push(value.state);
                    if let Some(lane) = value.lane {
                        recovered.push(lane)
                    }
                    cursor = cursor.checked_add(factor).ok_or(OracleError::Bounds)?;
                    if index + 1 == count {
                        break;
                    }
                }
                let envelope = if recovered.len() == usize::from(count) {
                    assemble_unique(&recovered).filter(|raw| {
                        crate::decode_section(raw)
                            .ok()
                            .is_some_and(|s| envelope_agrees(&s, entry))
                    })
                } else {
                    None
                };
                let state = if envelope.is_some() {
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
                };
                sections.push(SectionResult {
                    section_id: entry.section_id,
                    state,
                    envelope,
                });
            }
            let ids = layout
                .keys()
                .chain(inputs.keys())
                .copied()
                .collect::<BTreeSet<_>>();
            let fragments = ids
                .into_iter()
                .map(|id| {
                    diagnostic(
                        id,
                        inputs.contains_key(&id),
                        lanes.get(&id),
                        layout.get(&id),
                        false,
                    )
                })
                .collect();
            let checked = sections
                .iter()
                .filter_map(|s| s.envelope.as_ref().map(|raw| (s.section_id, raw.clone())))
                .collect::<BTreeMap<_, _>>();
            let availability = crate::bootstrap_v2::recover_content(&checked).ok();
            let required = availability.as_ref().and_then(|a| a.required_bytes.clone());
            let all = availability.and_then(|a| a.all_bytes);
            let state = if required.is_none() {
                ArtifactState::Failure
            } else if all.is_some() && sections.iter().all(|s| s.envelope.is_some()) {
                ArtifactState::Exact
            } else {
                ArtifactState::Degraded
            };
            return self.finish(state, sections, fragments, required, all, boundary);
        }
        // No catalog: only actual individually checked headers can supply
        // diagnostic sections. Source ownership cannot invent other groups.
        let mut checked = diagnostic_sections(
            lanes
                .iter()
                .filter(|(_, lane)| lane.block.section_id != 1)
                .map(|(_, lane)| lane),
        )?;
        checked.insert(
            1,
            SectionResult {
                section_id: 1,
                state: inventory_state,
                envelope: inventory_section,
            },
        );
        let mut ids = inputs.keys().copied().collect::<BTreeSet<_>>();
        // Every remaining owned case has an admitted bootstrap procedure:
        // framed OBS_UNITS or a complete square route. Its five fixed physical
        // positions do not depend on local or inventory recovery.
        ids.extend(1..=5);
        let fragments = ids
            .into_iter()
            .map(|id| diagnostic(id, inputs.contains_key(&id), lanes.get(&id), None, id <= 5))
            .collect();
        self.finish(
            ArtifactState::Failure,
            checked.into_values().collect(),
            fragments,
            None,
            None,
            boundary,
        )
    }
    fn extract(
        &self,
        channel: &str,
        family: &str,
        ordinal: u64,
        raw: &[u8],
    ) -> Result<BTreeMap<u32, Input>> {
        if channel == "OBS_UNITS" {
            let entries = ObsUnits::parse(raw)
                .map_err(|_| OracleError::Bounds)?
                .entries;
            if entries.len() > 2389 {
                return Err(OracleError::Bounds);
            }
            return Ok(entries
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
                .collect());
        }
        let core = self.source.source_core();
        let side = usize::from(core.side);
        let mut values = if channel == "OBS_MATRIX" {
            let frame = ObsMatrix::parse(raw).map_err(|_| OracleError::Bounds)?;
            if frame.side != side {
                return Err(OracleError::Bounds);
            }
            frame.values
        } else {
            let frame = crate::damage::ObsBits::parse(raw).map_err(|_| OracleError::Bounds)?;
            if frame.count != side * side {
                return Err(OracleError::Bounds);
            }
            raw[4..]
                .iter()
                .flat_map(|b| (0..8).rev().map(move |n| (b >> n) & 1))
                .collect::<Vec<_>>()
        };
        if family == "D0" {
            let mut canonical = vec![0; values.len()];
            let last = side - 1;
            let transform = ordinal / 2;
            let polarity = (ordinal % 2) as u8;
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
                        7 => (col, row),
                        _ => return Err(OracleError::Bounds),
                    };
                    canonical[row * side + col] = values[r * side + c] ^ polarity;
                }
            }
            values = canonical;
        }
        let mut inputs = BTreeMap::new();
        for unit in &core.units {
            let mut bytes = vec![0; 216];
            let mut erased = Vec::new();
            for bit in 0..1728u16 {
                let physical = core
                    .mapping
                    .forward_unit_bit(u64::from(unit.physical_unit_id - 1), bit)
                    .map_err(|_| OracleError::Source)?;
                let (r, c) = core
                    .mapping
                    .matrix_cell(physical)
                    .map_err(|_| OracleError::Source)?;
                let value = values[usize::from(r) * side + usize::from(c)];
                if value == 2 {
                    erased.push(EhErasure {
                        codeword: (bit / 72) as u8,
                        position: (bit % 72 + 1) as u8,
                    })
                } else {
                    bytes[usize::from(bit) / 8] |= value << (7 - bit % 8);
                }
            }
            inputs.insert(unit.physical_unit_id, Input { bytes, erased });
        }
        Ok(inputs)
    }
}
fn decode_lane(input: &Input) -> Option<Lane> {
    let (raw, verified) = if input.bytes.len() == 216 {
        let mut plain = [0u8; 192];
        let mut verified = true;
        for index in 0..24 {
            let erased = input
                .erased
                .iter()
                .filter(|p| usize::from(p.codeword) == index)
                .map(|p| p.position)
                .collect::<Vec<_>>();
            let word = candidate::decode_eh72(
                input.bytes[index * 9..index * 9 + 9].try_into().ok()?,
                &erased,
            )
            .ok()?;
            plain[index * 8..index * 8 + 8].copy_from_slice(&word.data);
            verified &= word.quality == DecodeQuality::Verified;
        }
        if plain[191] != 0 {
            return None;
        }
        let raw: [u8; 191] = plain[..191].try_into().ok()?;
        let profile = u16::from_be_bytes(raw[..2].try_into().ok()?);
        if ![8, 2, 3, 4, 7].contains(&profile) {
            return None;
        }
        (raw, verified)
    } else if input.bytes.len() == 255 && input.erased.is_empty() {
        let out = candidate::decode_rs255_191(&input.bytes, &[]);
        let bytes = out.codeword?;
        let raw: [u8; 191] = bytes[..191].try_into().ok()?;
        let profile = u16::from_be_bytes(raw[..2].try_into().ok()?);
        if ![5, 6].contains(&profile) {
            return None;
        }
        (raw, out.quality? == DecodeQuality::Verified)
    } else {
        return None;
    };
    let profile = u16::from_be_bytes(raw[..2].try_into().ok()?);
    let block = crate::decode_common_block(&raw, profile).ok()?;
    Some(Lane {
        raw,
        block,
        verified,
    })
}
fn group(
    inputs: &BTreeMap<u32, Input>,
    lanes: &BTreeMap<u32, Lane>,
    ids: &[u32],
    expected: Option<&Expected>,
) -> Group {
    let identity_agrees = |l: &Lane| {
        expected.map_or(
            l.block.profile_version == 8
                && l.block.section_id == 1
                && l.block.semantic_copy_id == 0
                && l.block.fragment_index == 0,
            |e| e.agrees(&l.block),
        )
    };
    let mut candidates = BTreeMap::<[u8; 191], Lane>::new();
    let present = ids.iter().any(|id| inputs.contains_key(id));
    for id in ids {
        // Physical ownership cannot remove a locally valid profile8 packet
        // from the union: it may conflict with another original or raw REP.
        if let Some(lane) = lanes.get(id).filter(|l| l.block.profile_version == 8) {
            candidates
                .entry(lane.raw)
                .and_modify(|old| old.verified |= lane.verified)
                .or_insert_with(|| lane.clone());
        }
    }
    if matches!(ids.len(), 2 | 5) && present {
        let masks = ids
            .iter()
            .map(|id| {
                inputs.get(id).filter(|p| p.bytes.len() == 216).map(|p| {
                    p.erased
                        .iter()
                        .map(|e| usize::from(e.codeword) * 72 + usize::from(e.position) - 1)
                        .collect::<BTreeSet<_>>()
                })
            })
            .collect::<Vec<_>>();
        let mut repetition = Input {
            bytes: vec![0; 216],
            erased: vec![],
        };
        for bit in 0..1728 {
            let mut zeros = 0;
            let mut ones = 0;
            let mut erased = 0;
            for (id, mask) in ids.iter().zip(&masks) {
                match (inputs.get(id), mask) {
                    (Some(input), Some(mask)) if !mask.contains(&bit) => {
                        if (input.bytes[bit / 8] >> (7 - bit % 8)) & 1 == 0 {
                            zeros += 1
                        } else {
                            ones += 1
                        }
                    }
                    _ => erased += 1,
                }
            }
            match (
                2 * ones + erased < ids.len(),
                2 * zeros + erased < ids.len(),
            ) {
                (true, false) => {}
                (false, true) => repetition.bytes[bit / 8] |= 1 << (7 - bit % 8),
                _ => repetition.erased.push(EhErasure {
                    codeword: (bit / 72) as u8,
                    position: (bit % 72 + 1) as u8,
                }),
            }
        }
        if let Some(mut lane) = decode_lane(&repetition).filter(|l| l.block.profile_version == 8) {
            lane.verified = false;
            candidates.entry(lane.raw).or_insert(lane);
        }
    }
    match candidates.len() {
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
            if !identity_agrees(&lane) {
                return Group {
                    state: FragmentState::Corrupt,
                    lane: None,
                };
            }
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
    }
}
fn assemble_unique(lanes: &[Lane]) -> Option<Vec<u8>> {
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
    crate::assemble_semantic_copy(&witnesses, 8)
        .ok()
        .map(|s| s.envelope)
}
fn fragment_count(entry: &InventoryEntry) -> Result<u16> {
    let len = 22usize
        .checked_add(
            entry
                .dependencies
                .len()
                .checked_mul(4)
                .ok_or(OracleError::Bounds)?,
        )
        .and_then(|x| x.checked_add(entry.logical_payload_length as usize))
        .ok_or(OracleError::Bounds)?;
    u16::try_from(len.div_ceil(157)).map_err(|_| OracleError::Bounds)
}
fn layout(inventory: &Inventory) -> Result<BTreeMap<u32, Expected>> {
    let mut rows = BTreeMap::new();
    let mut id = 1u32;
    for e in &inventory.entries {
        let count = fragment_count(e)?;
        let length = 22 + 4 * e.dependencies.len() + e.logical_payload_length as usize;
        for index in 0..count {
            for replica in 0..u16::from(e.physical_replica_count) {
                if id > 2389 {
                    return Err(OracleError::Bounds);
                }
                rows.insert(
                    id,
                    Expected {
                        id: e.section_id,
                        kind: e.section_type,
                        version: e.section_version,
                        index,
                        count,
                        length: length as u32,
                        replica,
                        factor: u16::from(e.physical_replica_count),
                    },
                );
                id = id.checked_add(1).ok_or(OracleError::Bounds)?;
            }
        }
    }
    Ok(rows)
}
fn envelope_agrees(s: &crate::SectionEnvelope, e: &InventoryEntry) -> bool {
    s.section_id == e.section_id
        && s.section_type == e.section_type
        && s.section_version == e.section_version
        && s.closure_class == e.closure_class
        && s.check_id == e.check_id
        && s.dependencies == e.dependencies
        && s.payload.len() == e.logical_payload_length as usize
}
fn diagnostic(
    id: u32,
    present: bool,
    lane: Option<&Lane>,
    expected: Option<&Expected>,
    initial: bool,
) -> FragmentDiagnostic {
    let mut row = FragmentDiagnostic {
        input_id: id,
        profile_version: None,
        section_id: 0,
        semantic_copy_id: ABSENT,
        fragment_index: ABSENT,
        replica_index: ABSENT,
        physical_replica_count: ABSENT,
        state: if present {
            FragmentState::Corrupt
        } else {
            FragmentState::Missing
        },
        common_block_sha256: ZERO.into(),
    };
    if let Some(e) = expected {
        row.profile_version = Some(8);
        row.section_id = e.id;
        row.semantic_copy_id = 0;
        row.fragment_index = e.index;
        row.replica_index = e.replica;
        row.physical_replica_count = e.factor;
    } else if initial {
        row.replica_index = (id - 1) as u16;
        row.physical_replica_count = 5;
        if !present {
            row.profile_version = Some(8);
            row.section_id = 1;
            row.semantic_copy_id = 0;
            row.fragment_index = 0;
        }
    }
    if let Some(lane) = lane {
        if expected.is_some() && lane.block.profile_version != 8 {
            return row;
        }
        // An admitted catalog names the physical row, while its local check
        // supplies the state/hash even if that packet names another owner.
        // Without a catalog only the observed local identity is available.
        if expected.is_none() {
            row.profile_version = Some(lane.block.profile_version);
            row.section_id = lane.block.section_id;
            row.semantic_copy_id = lane.block.semantic_copy_id;
            row.fragment_index = lane.block.fragment_index;
        }
        row.state = if lane.verified {
            FragmentState::Verified
        } else {
            FragmentState::Recovered
        };
        row.common_block_sha256 = format!("{:x}", Sha256::digest(lane.raw));
    }
    row
}
fn diagnostic_sections<'a>(
    lanes: impl Iterator<Item = &'a Lane>,
) -> Result<BTreeMap<u32, SectionResult>> {
    type Key = (u16, u32, u16, u16, u16, u16, u32);
    let mut copies = BTreeMap::<Key, BTreeMap<u16, BTreeMap<[u8; 191], Lane>>>::new();
    for lane in lanes {
        let b = &lane.block;
        copies
            .entry((
                b.profile_version,
                b.section_id,
                b.semantic_copy_id,
                b.section_type,
                b.section_version,
                b.fragment_count,
                b.section_envelope_length,
            ))
            .or_default()
            .entry(b.fragment_index)
            .or_default()
            .entry(lane.raw)
            .and_modify(|v| v.verified |= lane.verified)
            .or_insert_with(|| lane.clone());
    }
    let mut checked = BTreeMap::<u32, BTreeMap<Vec<u8>, bool>>::new();
    let mut candidates = 0usize;
    for ((profile, id, _, _, _, count, _), fragments) in copies {
        if fragments.len() != usize::from(count) || fragments.keys().copied().ne(0..count) {
            continue;
        }
        let combinations = fragments.values().try_fold(1usize, |n, v| {
            n.checked_mul(v.len()).ok_or(OracleError::Bounds)
        })?;
        if combinations > 4096
            || candidates
                .checked_add(combinations)
                .ok_or(OracleError::Bounds)?
                > 4096
        {
            return Err(OracleError::Bounds);
        }
        candidates += combinations;
        let mut variants = vec![Vec::<crate::FragmentWitness>::new()];
        for values in fragments.into_values() {
            let mut next = Vec::new();
            for prior in &variants {
                for lane in values.values() {
                    let mut v = prior.clone();
                    v.push(crate::FragmentWitness {
                        raw_block: lane.raw,
                        quality: if lane.verified {
                            crate::RecoveryQuality::Verified
                        } else {
                            crate::RecoveryQuality::Recovered
                        },
                    });
                    next.push(v)
                }
            }
            variants = next;
        }
        for variant in variants {
            if let Ok(section) = crate::assemble_semantic_copy(&variant, profile) {
                checked
                    .entry(id)
                    .or_default()
                    .entry(section.envelope)
                    .and_modify(|v| *v |= section.all_units_verified)
                    .or_insert(section.all_units_verified);
            }
        }
    }
    Ok(checked
        .into_iter()
        .map(|(id, values)| {
            let (state, envelope) = if values.len() == 1 {
                let (raw, verified) = values.into_iter().next().unwrap();
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

#[cfg(test)]
mod tests {
    use super::*;

    fn packet(section: u32, copy: u16, profile: u16) -> Input {
        let raw = crate::encode_common_block(&CommonBlock {
            profile_version: profile,
            section_id: section,
            semantic_copy_id: copy,
            section_type: 1,
            section_version: 2,
            fragment_index: 0,
            fragment_count: 1,
            section_envelope_length: 24,
            payload: vec![0x5a; 24],
        })
        .unwrap();
        Input {
            bytes: candidate::encode_eh_unit(&raw).to_vec(),
            erased: vec![],
        }
    }

    fn expected() -> Expected {
        Expected {
            id: 400,
            kind: 1,
            version: 2,
            index: 0,
            count: 1,
            length: 24,
            replica: 0,
            factor: 5,
        }
    }

    fn local_lanes(inputs: &BTreeMap<u32, Input>) -> BTreeMap<u32, Lane> {
        inputs
            .iter()
            .filter_map(|(id, input)| decode_lane(input).map(|lane| (*id, lane)))
            .collect()
    }

    #[test]
    fn oracle_group_conflict_precedes_expected_identity() {
        for (section, copy) in [(401, 0), (400, 1)] {
            let inputs = BTreeMap::from([(6, packet(400, 0, 8)), (7, packet(section, copy, 8))]);
            let lanes = local_lanes(&inputs);
            assert_eq!(lanes.len(), 2);
            let result = group(&inputs, &lanes, &[6, 7, 8, 9, 10], Some(&expected()));
            assert_eq!(result.state, FragmentState::Ambiguous);
            assert!(result.lane.is_none());
        }
    }

    #[test]
    fn oracle_group_original_and_raw_repetition_conflict_in_both_identity_directions() {
        for (original, repeated) in [(400, 401), (401, 400)] {
            let mut inputs = BTreeMap::from([(6, packet(original, 0, 8))]);
            for index in 0..4 {
                let mut damaged = packet(repeated, 0, 8);
                // Each lane has an uncorrectable double error in word zero;
                // disjoint error positions leave a three-vote raw majority.
                for bit in [index * 2, index * 2 + 1] {
                    damaged.bytes[bit / 8] ^= 128 >> (bit % 8);
                }
                assert!(decode_lane(&damaged).is_none());
                inputs.insert(7 + index as u32, damaged);
            }
            let lanes = local_lanes(&inputs);
            assert_eq!(lanes.len(), 1);
            let result = group(&inputs, &lanes, &[6, 7, 8, 9, 10], Some(&expected()));
            assert_eq!(result.state, FragmentState::Ambiguous);
            assert!(result.lane.is_none());
        }
    }

    #[test]
    fn oracle_bootstrap_conflict_keeps_all_local_candidates() {
        let inputs = BTreeMap::from([(1, packet(1, 0, 8)), (2, packet(401, 0, 8))]);
        let result = group(&inputs, &local_lanes(&inputs), &[1, 2, 3, 4, 5], None);
        assert_eq!(result.state, FragmentState::Ambiguous);
        assert!(result.lane.is_none());
    }

    #[test]
    fn oracle_wrong_owner_rejects_group_but_preserves_local_diagnostic() {
        let inputs = BTreeMap::from([(6, packet(401, 1, 8))]);
        let lanes = local_lanes(&inputs);
        let wanted = expected();
        let result = group(&inputs, &lanes, &[6, 7, 8, 9, 10], Some(&wanted));
        assert_eq!(result.state, FragmentState::Corrupt);
        assert!(result.lane.is_none());
        let lane = &lanes[&6];
        let row = diagnostic(6, true, Some(lane), Some(&wanted), false);
        assert_eq!(row.state, FragmentState::Verified);
        assert_eq!(
            (
                row.profile_version,
                row.section_id,
                row.semantic_copy_id,
                row.fragment_index
            ),
            (Some(8), 400, 0, 0)
        );
        assert_eq!((row.replica_index, row.physical_replica_count), (0, 5));
        assert_eq!(
            row.common_block_sha256,
            format!("{:x}", Sha256::digest(lane.raw))
        );
        let fallback = diagnostic(6, true, Some(lane), None, false);
        assert_eq!((fallback.section_id, fallback.semantic_copy_id), (401, 1));
        assert_eq!(fallback.common_block_sha256, row.common_block_sha256);
    }

    #[test]
    fn oracle_foreign_profiles_are_only_diagnostics() {
        let inputs = BTreeMap::from([(6, packet(400, 0, 8)), (7, packet(400, 0, 7))]);
        let lanes = local_lanes(&inputs);
        assert_eq!(lanes.len(), 2);
        let result = group(&inputs, &lanes, &[6, 7, 8, 9, 10], Some(&expected()));
        assert_eq!(result.state, FragmentState::Verified);
        assert_eq!(result.lane.unwrap().raw, lanes[&6].raw);
        let row = diagnostic(7, true, Some(&lanes[&7]), Some(&expected()), false);
        assert_eq!(row.state, FragmentState::Corrupt);
        assert_eq!(row.common_block_sha256, ZERO);
        let fallback = diagnostic(2, true, Some(&lanes[&7]), None, true);
        assert_eq!(
            (fallback.profile_version, fallback.state),
            (Some(7), FragmentState::Verified)
        );
        assert_eq!(
            (fallback.replica_index, fallback.physical_replica_count),
            (1, 5)
        );
    }
}
