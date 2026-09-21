//! Independently derived reference arithmetic for the source-side oracle.
//! These helpers do not discover routes or claim a complete result ledger.

use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AccountingError {
    Overflow,
    Reservation,
    AttemptLimit,
}
type Result<T> = std::result::Result<T, AccountingError>;

fn add(a: u64, b: u64) -> Result<u64> {
    a.checked_add(b).ok_or(AccountingError::Overflow)
}
fn mul(a: u64, b: u64) -> Result<u64> {
    a.checked_mul(b).ok_or(AccountingError::Overflow)
}
fn sum(values: &[u64]) -> Result<u64> {
    values.iter().try_fold(0, |a, b| add(a, *b))
}

/// Fixed reference capacities, independent of a host allocator or CPU count.
pub fn content_workspace(bytes: u64, records: u64, aliases: u64) -> Result<u64> {
    let actions = 65_535.min(bytes / 4);
    let selections = 4_096.min(actions);
    let lessons = 4_096.min(records);
    let edges = 16_384.min(bytes / 2);
    let persistent = sum(&[mul(32, bytes)?, mul(128, records)?, mul(8, aliases)?])?;
    let dependency = add(mul(4, bytes)?, mul(24, records)?)?;
    let passive = sum(&[
        mul(64, actions)?,
        mul(32, selections)?,
        mul(24, lessons)?,
        256,
    ])?;
    let graph = add(mul(48, edges)?, mul(192, lessons)?)?;
    add(persistent, dependency.max(passive).max(graph))
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WireEncoding {
    Expanded,
    Compact,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ProgramWorkspace {
    pub immutable_bytes: u64,
    pub parse_extra_bytes: u64,
    pub refinement_extra_bytes: u64,
    pub logical_nodes: u64,
}
impl ProgramWorkspace {
    pub fn parse_workspace(self) -> Result<u64> {
        add(self.immutable_bytes, self.parse_extra_bytes)
    }
}

/// A short header has no dependent arena; its supplied wire remains reserved.
pub fn short_program_workspace(wire_bytes: u64) -> ProgramWorkspace {
    ProgramWorkspace {
        immutable_bytes: wire_bytes,
        parse_extra_bytes: 0,
        refinement_extra_bytes: 0,
        logical_nodes: 0,
    }
}

/// Account the actual header, without turning accounting clamps into parsing.
/// Unknown encoding tags use the noncompact reservation and remain invalid.
pub fn program_workspace_from_header(raw: &[u8]) -> Result<ProgramWorkspace> {
    let length = u64::try_from(raw.len()).map_err(|_| AccountingError::Overflow)?;
    if raw.len() < 64 {
        return Ok(short_program_workspace(length));
    }
    let u16_at = |at| u64::from(u16::from_be_bytes([raw[at], raw[at + 1]]));
    let u32_at = |at| {
        u64::from(u32::from_be_bytes([
            raw[at],
            raw[at + 1],
            raw[at + 2],
            raw[at + 3],
        ]))
    };
    program_workspace(
        length,
        if u16_at(8) == 1 {
            WireEncoding::Compact
        } else {
            WireEncoding::Expanded
        },
        u16_at(16),
        u16_at(18),
        u32_at(20),
        u32_at(24),
        u32_at(28),
    )
}

/// Clamps describe malformed-input accounting, never semantic admission.
pub fn program_workspace(
    wire_bytes: u64,
    encoding: WireEncoding,
    recipes: u64,
    tables: u64,
    nodes: u64,
    edges: u64,
    table_payload: u64,
) -> Result<ProgramWorkspace> {
    let p = recipes.min(256);
    let t = tables.min(4_096);
    let n = nodes.min(65_535);
    let e = edges.min(262_140);
    let d = table_payload.min(1_048_576);
    let expanded = match encoding {
        WireEncoding::Expanded => wire_bytes,
        WireEncoding::Compact => add(wire_bytes, mul(26, n)?)?.min(1_048_576),
    };
    Ok(ProgramWorkspace {
        immutable_bytes: sum(&[
            wire_bytes,
            mul(3, expanded)?,
            mul(64, n)?,
            mul(64, t)?,
            mul(128, p)?,
            mul(8, d)?,
        ])?,
        parse_extra_bytes: sum(&[mul(48, n)?, mul(8, e)?, mul(16, t)?, mul(32, p)?])?,
        refinement_extra_bytes: sum(&[mul(32, n)?, mul(8, e)?, mul(8, t)?])?,
        logical_nodes: n,
    })
}

/// The owner reserves all four simultaneous miniature views explicitly.
pub fn definition_workspace(define_bytes: u64, program: ProgramWorkspace) -> Result<u64> {
    let miniature = content_workspace(577, 29, mul(29, 577 / 14)?)?;
    let content = add(program.immutable_bytes, mul(4, miniature)?)?;
    add(
        mul(8, define_bytes)?,
        program.parse_workspace()?.max(content),
    )
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(usize)]
pub enum Kernel {
    Observation,
    SquareView,
    ShellRead,
    RouteFrame,
    RecipeParse,
    ProgramRefinement,
    RouteExample,
    DefinitionValidation,
    MappingSearch,
    UnitExtraction,
    LaneAdapter,
    RepetitionAdapter,
    CommonFrame,
    SectionAssembly,
    SectionCheck,
    Inventory,
    GroupLayout,
    DependencyClosure,
    BodyAdapter,
    ContentValidation,
    ResultSelection,
    ResultRender,
}
impl Kernel {
    pub const ALL: [Self; 22] = [
        Self::Observation,
        Self::SquareView,
        Self::ShellRead,
        Self::RouteFrame,
        Self::RecipeParse,
        Self::ProgramRefinement,
        Self::RouteExample,
        Self::DefinitionValidation,
        Self::MappingSearch,
        Self::UnitExtraction,
        Self::LaneAdapter,
        Self::RepetitionAdapter,
        Self::CommonFrame,
        Self::SectionAssembly,
        Self::SectionCheck,
        Self::Inventory,
        Self::GroupLayout,
        Self::DependencyClosure,
        Self::BodyAdapter,
        Self::ContentValidation,
        Self::ResultSelection,
        Self::ResultRender,
    ];
    pub fn name(self) -> &'static str {
        const NAMES: [&str; 22] = [
            "observation",
            "square-view",
            "shell-read",
            "route-frame",
            "recipe-parse",
            "program-refinement",
            "route-example",
            "definition-validation",
            "mapping-search",
            "unit-extraction",
            "lane-adapter",
            "repetition-adapter",
            "common-frame",
            "section-assembly",
            "section-check",
            "inventory",
            "group-layout",
            "dependency-closure",
            "body-adapter",
            "content-validation",
            "result-selection",
            "result-render",
        ];
        NAMES[self as usize]
    }
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct AdapterRow {
    pub calls: u64,
    pub reference_input_units: u64,
    pub peak_workspace_bytes: u64,
}
impl AdapterRow {
    fn next(self, units: u64, workspace: u64) -> Result<Self> {
        Ok(Self {
            calls: add(self.calls, 1)?,
            reference_input_units: add(self.reference_input_units, units)?,
            peak_workspace_bytes: self.peak_workspace_bytes.max(workspace),
        })
    }
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct ResourceCounters {
    pub section_attempts: u64,
    pub primitive_steps: u64,
    pub peak_scratch_bytes: u64,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Reservation(u64);
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Attempt {
    Ineligible,
    Duplicate,
    Charged,
}

/// Explicit retained lifetimes and atomic charge events. No shared cache.
#[derive(Default)]
pub struct Ledger {
    counters: ResourceCounters,
    rows: [AdapterRow; 22],
    live: u64,
    next_reservation: u64,
    reservations: BTreeMap<u64, u64>,
    persistent: BTreeSet<u64>,
    attempted: BTreeSet<Vec<u8>>,
}
impl Ledger {
    pub fn new() -> Self {
        Self::default()
    }
    pub fn resource(&self) -> ResourceCounters {
        self.counters
    }
    pub fn row(&self, kernel: Kernel) -> AdapterRow {
        self.rows[kernel as usize]
    }
    pub fn live_bytes(&self) -> u64 {
        self.live
    }

    pub fn retain(&mut self, bytes: u64) -> Result<Reservation> {
        let live = add(self.live, bytes)?;
        let next = add(self.next_reservation, 1)?;
        let token = Reservation(self.next_reservation);
        self.reservations.insert(token.0, bytes);
        self.next_reservation = next;
        self.live = live;
        self.counters.peak_scratch_bytes = self.counters.peak_scratch_bytes.max(live);
        Ok(token)
    }

    pub fn release(&mut self, token: Reservation) -> Result<()> {
        let bytes = self
            .reservations
            .get(&token.0)
            .ok_or(AccountingError::Reservation)?;
        let live = self
            .live
            .checked_sub(*bytes)
            .ok_or(AccountingError::Reservation)?;
        self.reservations.remove(&token.0);
        self.persistent.remove(&token.0);
        self.live = live;
        Ok(())
    }

    /// Promote an admitted observation-wide value; attempted envelopes already
    /// have this lifetime through their separate exact-byte set.
    pub fn persist(&mut self, token: Reservation) -> Result<()> {
        if !self.reservations.contains_key(&token.0) {
            return Err(AccountingError::Reservation);
        }
        self.persistent.insert(token.0);
        Ok(())
    }

    /// End observation/path/view temporaries, also on an early global failure.
    pub fn release_transients(&mut self) -> Result<()> {
        let tokens = self
            .reservations
            .keys()
            .filter(|k| !self.persistent.contains(k))
            .copied()
            .map(Reservation)
            .collect::<Vec<_>>();
        for token in tokens {
            self.release(token)?;
        }
        Ok(())
    }

    pub fn adapter(&mut self, kernel: Kernel, units: u64, workspace: u64) -> Result<()> {
        let row = self.rows[kernel as usize].next(units, workspace)?;
        let peak = add(self.live, workspace)?;
        self.rows[kernel as usize] = row;
        self.counters.peak_scratch_bytes = self.counters.peak_scratch_bytes.max(peak);
        Ok(())
    }

    /// Grow a reached phase's reservation without inventing another invocation.
    pub fn adapter_peak(&mut self, kernel: Kernel, workspace: u64) -> Result<()> {
        let peak = add(self.live, workspace)?;
        self.rows[kernel as usize].peak_workspace_bytes = self.rows[kernel as usize]
            .peak_workspace_bytes
            .max(workspace);
        self.counters.peak_scratch_bytes = self.counters.peak_scratch_bytes.max(peak);
        Ok(())
    }

    /// Rendering learns its exact byte work after freezing result counters.
    pub fn adapter_work(&mut self, kernel: Kernel, units: u64) -> Result<()> {
        let total = add(self.rows[kernel as usize].reference_input_units, units)?;
        self.rows[kernel as usize].reference_input_units = total;
        Ok(())
    }

    /// One actual logical invocation; repeated invocations are separate events.
    pub fn vm(&mut self, steps: u64, scratch: u64) -> Result<()> {
        let steps = add(self.counters.primitive_steps, steps)?;
        let peak = add(self.live, scratch)?;
        self.counters.primitive_steps = steps;
        self.counters.peak_scratch_bytes = self.counters.peak_scratch_bytes.max(peak);
        Ok(())
    }

    /// Fold identical invocations while retaining the exact completed prefix if
    /// a later addition would overflow. This is not one larger atomic event.
    pub fn vm_repeated(&mut self, steps: u64, scratch: u64, count: u64) -> Result<()> {
        if count == 0 {
            return Ok(());
        }
        let peak = add(self.live, scratch)?;
        let completed = if steps == 0 {
            count
        } else {
            count.min((u64::MAX - self.counters.primitive_steps) / steps)
        };
        if completed != 0 {
            self.counters.primitive_steps =
                add(self.counters.primitive_steps, mul(steps, completed)?)?;
            self.counters.peak_scratch_bytes = self.counters.peak_scratch_bytes.max(peak);
        }
        if completed != count {
            return Err(AccountingError::Overflow);
        }
        Ok(())
    }

    /// Called immediately before comparison; stored check bytes are not read.
    pub fn section_check(&mut self, envelope: &[u8]) -> Result<Attempt> {
        if !section_eligible(envelope) {
            return Ok(Attempt::Ineligible);
        }
        if self.attempted.contains(envelope) {
            return Ok(Attempt::Duplicate);
        }
        if self.counters.section_attempts == 4096 {
            return Err(AccountingError::AttemptLimit);
        }
        let length = envelope.len() as u64;
        let live = add(self.live, add(length, 8)?)?;
        let peak = add(live, length)?;
        let attempts = add(self.counters.section_attempts, 1)?;
        let row = self.row(Kernel::SectionCheck).next(length, length)?;
        self.attempted.insert(envelope.to_vec());
        self.live = live;
        self.rows[Kernel::SectionCheck as usize] = row;
        self.counters.section_attempts = attempts;
        self.counters.peak_scratch_bytes = self.counters.peak_scratch_bytes.max(peak);
        Ok(Attempt::Charged)
    }
}

/// Exact pre-check grammar. This deliberately does not admit typed sections.
pub fn section_eligible(raw: &[u8]) -> bool {
    if !(22..=32790).contains(&raw.len()) {
        return false;
    }
    let u16_at = |at| u16::from_be_bytes([raw[at], raw[at + 1]]);
    let u32_at = |at| u32::from_be_bytes([raw[at], raw[at + 1], raw[at + 2], raw[at + 3]]);
    let id = u32_at(2);
    if u16_at(0) != 0
        || id == 0
        || !(1..=6).contains(&u16_at(6))
        || !matches!(raw[10], 128 | 129)
        || !matches!(raw[11], 1 | 2)
    {
        return false;
    }
    let count = usize::from(u16_at(12));
    if count > 4095 {
        return false;
    }
    let Some(payload_end) = 18_usize
        .checked_add(count * 4)
        .and_then(|n| n.checked_add(u32_at(14) as usize))
    else {
        return false;
    };
    let check = if raw[11] == 1 { 4 } else { 8 };
    if payload_end.checked_add(check) != Some(raw.len()) {
        return false;
    }
    let mut prior = 0;
    for ordinal in 0..count {
        let dependency = u32_at(18 + ordinal * 4);
        if dependency <= prior || dependency == id {
            return false;
        }
        prior = dependency;
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    fn envelope() -> Vec<u8> {
        crate::encode_section(&crate::SectionEnvelope {
            section_id: 1,
            section_type: 3,
            section_version: 0,
            closure_class: 128,
            check_id: 1,
            dependencies: vec![],
            payload: vec![42],
        })
        .unwrap()
    }

    #[test]
    fn closed_kernel_order_and_manual_workspace_values() {
        assert_eq!(Kernel::ALL.len(), 22);
        assert_eq!(Kernel::Observation.name(), "observation");
        assert_eq!(Kernel::ResultRender.name(), "result-render");
        assert_eq!(content_workspace(577, 29, 1189), Ok(51_080));
        assert_eq!(content_workspace(0, 0, 0), Ok(256));
        assert_eq!(
            content_workspace(u64::MAX, 1, 1),
            Err(AccountingError::Overflow)
        );
        let compact = program_workspace(100, WireEncoding::Compact, 1, 1, 2, 3, 4).unwrap();
        assert_eq!(compact.immutable_bytes, 908);
        assert_eq!(compact.parse_extra_bytes, 168);
        assert_eq!(compact.refinement_extra_bytes, 96);
        assert_eq!(compact.parse_workspace().unwrap(), 1076);
        let expanded = program_workspace(100, WireEncoding::Expanded, 1, 1, 2, 3, 4).unwrap();
        assert_eq!(expanded.immutable_bytes, 752);
        assert_eq!(definition_workspace(10, compact).unwrap(), 205_308);
        assert_eq!(short_program_workspace(17).parse_workspace(), Ok(17));
    }

    #[test]
    fn malformed_header_reservations_are_bounded_without_admitting_a_program() {
        let mut raw = [0xff; 64];
        raw[8..10].copy_from_slice(&1_u16.to_be_bytes());
        let compact = program_workspace_from_header(&raw).unwrap();
        let clamped =
            program_workspace(64, WireEncoding::Compact, 256, 4096, 65535, 262140, 1048576)
                .unwrap();
        assert_eq!(compact, clamped);
        assert_eq!(compact.logical_nodes, 65535);
        raw[8..10].copy_from_slice(&99_u16.to_be_bytes());
        assert_eq!(
            program_workspace_from_header(&raw).unwrap(),
            program_workspace(
                64,
                WireEncoding::Expanded,
                256,
                4096,
                65535,
                262140,
                1048576
            )
            .unwrap()
        );
        assert_eq!(
            program_workspace_from_header(&raw[..63]).unwrap(),
            short_program_workspace(63)
        );
    }

    #[test]
    fn logical_events_are_atomic_and_local_peaks_exclude_retained_bytes() {
        let mut ledger = Ledger::new();
        let retained = ledger.retain(100).unwrap();
        ledger.adapter(Kernel::LaneAdapter, 216, 407).unwrap();
        ledger.vm(80_435, 4_613).unwrap();
        assert_eq!(ledger.resource().primitive_steps, 80_435);
        assert_eq!(ledger.resource().peak_scratch_bytes, 4_713);
        assert_eq!(ledger.row(Kernel::LaneAdapter).peak_workspace_bytes, 407);
        ledger.release(retained).unwrap();
        ledger.adapter(Kernel::LaneAdapter, 216, 407).unwrap();
        assert_eq!(ledger.row(Kernel::LaneAdapter).calls, 2);
        assert_eq!(ledger.row(Kernel::LaneAdapter).reference_input_units, 432);
        assert_eq!(ledger.release(retained), Err(AccountingError::Reservation));

        let mut overflow = Ledger::new();
        overflow.adapter(Kernel::Observation, u64::MAX, 0).unwrap();
        let before = overflow.row(Kernel::Observation);
        assert_eq!(
            overflow.adapter(Kernel::Observation, 1, 7),
            Err(AccountingError::Overflow)
        );
        assert_eq!(overflow.row(Kernel::Observation), before);
        assert_eq!(overflow.resource().peak_scratch_bytes, 0);
        overflow.vm(u64::MAX, 2).unwrap();
        let before = overflow.resource();
        assert_eq!(overflow.vm(1, 8), Err(AccountingError::Overflow));
        assert_eq!(overflow.resource(), before);

        let retained = overflow.retain(u64::MAX).unwrap();
        let before = overflow.resource();
        let row = overflow.row(Kernel::LaneAdapter);
        assert_eq!(
            overflow.adapter(Kernel::LaneAdapter, 1, 1),
            Err(AccountingError::Overflow)
        );
        assert_eq!(overflow.resource(), before);
        assert_eq!(overflow.row(Kernel::LaneAdapter), row);
        assert_eq!(overflow.retain(1), Err(AccountingError::Overflow));
        overflow.release(retained).unwrap();
    }

    #[test]
    fn eligibility_is_structural_and_attempts_deduplicate_complete_bytes() {
        let raw = envelope();
        assert!(section_eligible(&raw));
        let mut ledger = Ledger::new();
        assert_eq!(ledger.section_check(&raw), Ok(Attempt::Charged));
        assert_eq!(ledger.section_check(&raw), Ok(Attempt::Duplicate));
        let mut wrong_check = raw.clone();
        *wrong_check.last_mut().unwrap() ^= 1;
        assert_eq!(ledger.section_check(&wrong_check), Ok(Attempt::Charged));
        assert_eq!(ledger.resource().section_attempts, 2);
        assert_eq!(ledger.row(Kernel::SectionCheck).reference_input_units, 46);
        assert_eq!(ledger.live_bytes(), 62);
        assert_eq!(ledger.resource().peak_scratch_bytes, 85);
        let mut wrong_width = raw.clone();
        wrong_width[11] = 2;
        assert_eq!(ledger.section_check(&wrong_width), Ok(Attempt::Ineligible));
        assert_eq!(ledger.resource().section_attempts, 2);
        let mut unrestricted_version = raw;
        unrestricted_version[8..10].copy_from_slice(&u16::MAX.to_be_bytes());
        assert!(section_eligible(&unrestricted_version));
    }

    #[test]
    fn eligibility_handles_dependency_edges_and_payload_above_content_limit() {
        let mut raw = envelope();
        raw.splice(18..18, [0, 0, 0, 2]);
        raw[13] = 1;
        assert!(section_eligible(&raw));
        raw[21] = 1;
        assert!(!section_eligible(&raw));
        raw[21] = 0;
        assert!(!section_eligible(&raw));
        let mut large = envelope();
        large[14..18].copy_from_slice(&16_385_u32.to_be_bytes());
        large.resize(18 + 16_385 + 4, 0);
        assert!(section_eligible(&large));
        for length in 0..23 {
            assert!(!section_eligible(&envelope()[..length]));
        }
        let mut dependencies = envelope();
        dependencies.splice(18..18, [0, 0, 0, 2, 0, 0, 0, 3]);
        dependencies[13] = 2;
        assert!(section_eligible(&dependencies));
        dependencies[25] = 2;
        assert!(!section_eligible(&dependencies));
        dependencies[21] = 3;
        assert!(!section_eligible(&dependencies));
        for (offset, value) in [(0, 1), (5, 0), (7, 7), (10, 0), (11, 0)] {
            let mut changed = envelope();
            changed[offset] = value;
            assert!(!section_eligible(&changed));
        }
        let mut trailing = envelope();
        trailing.push(0);
        assert!(!section_eligible(&trailing));
    }

    #[test]
    fn attempt_limit_keeps_prior_completed_events() {
        let mut ledger = Ledger::new();
        for id in 1..=4096_u32 {
            let mut raw = envelope();
            raw[2..6].copy_from_slice(&id.to_be_bytes());
            assert_eq!(ledger.section_check(&raw), Ok(Attempt::Charged));
        }
        let before = ledger.resource();
        let row = ledger.row(Kernel::SectionCheck);
        let mut raw = envelope();
        raw[2..6].copy_from_slice(&4097_u32.to_be_bytes());
        assert_eq!(
            ledger.section_check(&raw),
            Err(AccountingError::AttemptLimit)
        );
        assert_eq!(ledger.resource(), before);
        assert_eq!(ledger.row(Kernel::SectionCheck), row);
    }

    #[test]
    fn folded_vm_calls_keep_exact_completed_prefix_before_overflow() {
        let mut ledger = Ledger::new();
        ledger.vm(u64::MAX - 5, 1).unwrap();
        assert_eq!(ledger.vm_repeated(3, 7, 3), Err(AccountingError::Overflow));
        assert_eq!(ledger.resource().primitive_steps, u64::MAX - 2);
        assert_eq!(ledger.resource().peak_scratch_bytes, 7);
        let before = ledger.resource();
        assert_eq!(ledger.vm_repeated(3, 9, 1), Err(AccountingError::Overflow));
        assert_eq!(ledger.resource(), before);
        ledger.vm_repeated(u64::MAX, u64::MAX, 0).unwrap();
        assert_eq!(ledger.resource(), before);
    }
}
