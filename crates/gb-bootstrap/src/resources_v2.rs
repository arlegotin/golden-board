//! Checked reference adapter work and canonical workspace reservations for v2.
use std::collections::BTreeMap;
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ResourceError {
    Arithmetic,
    Bounds,
    Manifest,
    Binding,
}
type Result<T> = std::result::Result<T, ResourceError>;
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
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
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct AdapterRow {
    calls: u64,
    units: u64,
    workspace: u64,
}
impl AdapterRow {
    pub fn calls(self) -> u64 {
        self.calls
    }
    pub fn reference_input_units(self) -> u64 {
        self.units
    }
    pub fn peak_workspace_bytes(self) -> u64 {
        self.workspace
    }
}
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct ReferenceLedger {
    rows: [AdapterRow; 22],
    retained: BTreeMap<String, u64>,
    peak: u64,
}
impl ReferenceLedger {
    pub fn rows(&self) -> &[AdapterRow; 22] {
        &self.rows
    }
    pub fn peak_scratch_bytes(&self) -> u64 {
        self.peak
    }
    pub fn live_bytes(&self) -> Result<u64> {
        self.retained.values().copied().try_fold(0, add)
    }
    pub fn retain(&mut self, key: &str, bytes: u64) -> Result<()> {
        let prior = self.retained.get(key).copied().unwrap_or(0);
        let live = add(
            self.live_bytes()?
                .checked_sub(prior)
                .ok_or(ResourceError::Arithmetic)?,
            bytes,
        )?;
        self.retained.insert(key.into(), bytes);
        self.peak = self.peak.max(live);
        Ok(())
    }
    pub(crate) fn release_prefix(&mut self, prefix: &str) {
        self.retained.retain(|key, _| !key.starts_with(prefix));
    }
    pub fn release(&mut self, key: &str) {
        self.retained.remove(key);
    }
    pub fn event(&mut self, kernel: Kernel, units: u64, workspace: u64) -> Result<()> {
        let previous = self.rows[kernel as usize];
        let calls = add(previous.calls, 1)?;
        let units = add(previous.units, units)?;
        let peak = add(self.live_bytes()?, workspace)?;
        self.rows[kernel as usize] = AdapterRow {
            calls,
            units,
            workspace: previous.workspace.max(workspace),
        };
        self.peak = self.peak.max(peak);
        Ok(())
    }
    pub(crate) fn raise_workspace(&mut self, kernel: Kernel, bytes: u64) -> Result<()> {
        let peak = add(self.live_bytes()?, bytes)?;
        self.rows[kernel as usize].workspace = self.rows[kernel as usize].workspace.max(bytes);
        self.peak = self.peak.max(peak);
        Ok(())
    }
    pub fn vm_workspace(&mut self, bytes: u64) -> Result<()> {
        let peak = add(self.live_bytes()?, bytes)?;
        self.peak = self.peak.max(peak);
        Ok(())
    }
}
fn add(a: u64, b: u64) -> Result<u64> {
    a.checked_add(b).ok_or(ResourceError::Arithmetic)
}
fn mul(a: u64, b: u64) -> Result<u64> {
    a.checked_mul(b).ok_or(ResourceError::Arithmetic)
}
fn sum(v: impl IntoIterator<Item = u64>) -> Result<u64> {
    v.into_iter().try_fold(0, add)
}
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct ProgramWorkspace {
    immutable: u64,
    parsing: u64,
    refinement: u64,
}
impl ProgramWorkspace {
    pub fn immutable(self) -> u64 {
        self.immutable
    }
    pub fn parsing(self) -> u64 {
        self.parsing
    }
    pub fn refinement(self) -> u64 {
        self.refinement
    }
}
pub fn content_workspace(bytes: u64, records: u64, aliases: u64) -> Result<u64> {
    if bytes > 1048576 || records > 65535 || aliases > 4096 * 4096 {
        return Err(ResourceError::Bounds);
    }
    let actions = 65535.min(bytes / 4);
    let selections = 4096.min(actions);
    let lessons = 4096.min(records);
    let edges = 16384.min(bytes / 2);
    let persistent = sum([mul(32, bytes)?, mul(128, records)?, mul(8, aliases)?])?;
    let dependency = add(mul(4, bytes)?, mul(24, records)?)?;
    let passive = sum([
        mul(64, actions)?,
        mul(32, selections)?,
        mul(24, lessons)?,
        256,
    ])?;
    let graph = add(mul(48, edges)?, mul(192, lessons)?)?;
    add(persistent, dependency.max(passive).max(graph))
}
pub fn program_workspace(raw: &[u8]) -> Result<ProgramWorkspace> {
    let v = raw.len() as u64;
    if v > 1048576 {
        return Err(ResourceError::Bounds);
    }
    if raw.len() < 64 {
        return Ok(ProgramWorkspace {
            immutable: v,
            parsing: v,
            refinement: 0,
        });
    }
    let p = u64::from(u16::from_be_bytes([raw[16], raw[17]])).min(256);
    let t = u64::from(u16::from_be_bytes([raw[18], raw[19]])).min(4096);
    let n = u64::from(u32::from_be_bytes(
        raw[20..24].try_into().map_err(|_| ResourceError::Bounds)?,
    ))
    .min(65535);
    let e = u64::from(u32::from_be_bytes(
        raw[24..28].try_into().map_err(|_| ResourceError::Bounds)?,
    ))
    .min(262140);
    let d = u64::from(u32::from_be_bytes(
        raw[28..32].try_into().map_err(|_| ResourceError::Bounds)?,
    ))
    .min(1048576);
    let x = if u16::from_be_bytes([raw[8], raw[9]]) == 1 {
        add(v, mul(26, n)?)?.min(1048576)
    } else {
        v
    };
    let immutable = sum([
        v,
        mul(3, x)?,
        mul(64, n)?,
        mul(64, t)?,
        mul(128, p)?,
        mul(8, d)?,
    ])?;
    let parsing = sum([immutable, mul(48, n)?, mul(8, e)?, mul(16, t)?, mul(32, p)?])?;
    let refinement = sum([mul(32, n)?, mul(8, e)?, mul(8, t)?])?;
    Ok(ProgramWorkspace {
        immutable,
        parsing,
        refinement,
    })
}
pub fn definition_workspace(bytes: u64, program: ProgramWorkspace) -> Result<u64> {
    let mini = content_workspace(577, 29, 29 * (577 / 14))?;
    add(
        mul(8, bytes)?,
        program.parsing.max(add(program.immutable, mul(4, mini)?)?),
    )
}

use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use sha2::{Digest, Sha256};
impl Kernel {
    pub const ALL: [Kernel; 22] = [
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
    pub fn id(self) -> &'static str {
        [
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
        ][self as usize]
    }
}
fn object(v: &V) -> Result<&BTreeMap<String, V>> {
    if let V::Object(v) = v {
        Ok(v)
    } else {
        Err(ResourceError::Manifest)
    }
}
fn array(v: &V) -> Result<&[V]> {
    if let V::Array(v) = v {
        Ok(v)
    } else {
        Err(ResourceError::Manifest)
    }
}
fn string(v: &V) -> Result<&str> {
    if let V::String(v) = v {
        Ok(v)
    } else {
        Err(ResourceError::Manifest)
    }
}
fn number(v: &V) -> Result<u64> {
    if let V::U64(v) = v {
        Ok(*v)
    } else {
        Err(ResourceError::Manifest)
    }
}
fn keys(v: &BTreeMap<String, V>, expected: &str) -> Result<()> {
    let names = expected.split(',').collect::<Vec<_>>();
    if v.len() == names.len() && names.into_iter().all(|k| v.contains_key(k)) {
        Ok(())
    } else {
        Err(ResourceError::Manifest)
    }
}
fn sha(v: &str) -> Result<()> {
    if v.len() == 64
        && v.bytes()
            .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
    {
        Ok(())
    } else {
        Err(ResourceError::Manifest)
    }
}
fn o(rows: impl IntoIterator<Item = (&'static str, V)>) -> V {
    V::Object(rows.into_iter().map(|(k, v)| (k.into(), v)).collect())
}
fn s(v: impl Into<String>) -> V {
    V::String(v.into())
}
fn digest(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
pub(crate) fn source_owners() -> V {
    o([
        (
            "spec/profile-policy-v2.toml",
            s(digest(include_bytes!(
                "../../../spec/profile-policy-v2.toml"
            ))),
        ),
        (
            "spec/profile-limits-v2.toml",
            s(digest(include_bytes!(
                "../../../spec/profile-limits-v2.toml"
            ))),
        ),
        (
            "spec/damage-policy-v2.toml",
            s(digest(include_bytes!(
                "../../../spec/damage-policy-v2.toml"
            ))),
        ),
        (
            "spec/resource-accounting-v2.md",
            s(digest(include_bytes!(
                "../../../spec/resource-accounting-v2.md"
            ))),
        ),
    ])
}
fn resource_value(r: crate::damage::ResourceProjection) -> V {
    o([
        ("section_attempts", V::U64(r.section_attempts)),
        ("primitive_steps", V::U64(r.primitive_steps)),
        ("peak_scratch_bytes", V::U64(r.peak_scratch_bytes)),
    ])
}
fn row_values(rows: &[AdapterRow; 22]) -> V {
    V::Array(
        Kernel::ALL
            .into_iter()
            .zip(rows)
            .map(|(kernel, row)| {
                o([
                    ("kernel", s(kernel.id())),
                    ("calls", V::U64(row.calls)),
                    ("reference_input_units", V::U64(row.units)),
                    ("peak_workspace_bytes", V::U64(row.workspace)),
                ])
            })
            .collect(),
    )
}
fn serialize(value: V) -> Result<Vec<u8>> {
    serialize_manifest(&value).map_err(|_| ResourceError::Manifest)
}
/// Pure projection. The caller must bind these digests to the returned result.
pub fn render_resource_sidecar(
    channel: &str,
    observation_sha256: &str,
    result_sha256: &str,
    resource: crate::damage::ResourceProjection,
    ledger: &ReferenceLedger,
) -> Result<Vec<u8>> {
    if !matches!(channel, "OBS_BITS" | "OBS_MATRIX" | "OBS_UNITS") {
        return Err(ResourceError::Manifest);
    }
    sha(observation_sha256)?;
    sha(result_sha256)?;
    serialize(o([
        ("schema", s("golden-board.m2-observation-resources/v2")),
        ("channel", s(channel)),
        ("observation_sha256", s(observation_sha256)),
        ("result_sha256", s(result_sha256)),
        ("source_owners", source_owners()),
        ("resource", resource_value(resource)),
        ("adapter_rows", row_values(&ledger.rows)),
    ]))
}
fn read_sidecar(raw: &[u8]) -> Result<(crate::damage::ResourceProjection, [AdapterRow; 22])> {
    let value = validate_canonical_manifest(raw).map_err(|_| ResourceError::Manifest)?;
    let v = object(&value)?;
    keys(
        v,
        "schema,channel,observation_sha256,result_sha256,source_owners,resource,adapter_rows",
    )?;
    if string(&v["schema"])? != "golden-board.m2-observation-resources/v2"
        || !matches!(
            string(&v["channel"])?,
            "OBS_BITS" | "OBS_MATRIX" | "OBS_UNITS"
        )
        || v["source_owners"] != source_owners()
    {
        return Err(ResourceError::Binding);
    }
    sha(string(&v["observation_sha256"])?)?;
    sha(string(&v["result_sha256"])?)?;
    let resource = object(&v["resource"])?;
    keys(
        resource,
        "section_attempts,primitive_steps,peak_scratch_bytes",
    )?;
    let r = crate::damage::ResourceProjection {
        section_attempts: number(&resource["section_attempts"])?,
        primitive_steps: number(&resource["primitive_steps"])?,
        peak_scratch_bytes: number(&resource["peak_scratch_bytes"])?,
    };
    let values = array(&v["adapter_rows"])?;
    if values.len() != 22 {
        return Err(ResourceError::Manifest);
    }
    let mut rows = [AdapterRow::default(); 22];
    for (i, (kernel, value)) in Kernel::ALL.into_iter().zip(values).enumerate() {
        let row = object(value)?;
        keys(
            row,
            "kernel,calls,reference_input_units,peak_workspace_bytes",
        )?;
        if string(&row["kernel"])? != kernel.id() {
            return Err(ResourceError::Manifest);
        }
        let row = AdapterRow {
            calls: number(&row["calls"])?,
            units: number(&row["reference_input_units"])?,
            workspace: number(&row["peak_workspace_bytes"])?,
        };
        if row.calls == 0 && (row.units != 0 || row.workspace != 0) {
            return Err(ResourceError::Manifest);
        }
        rows[i] = row;
    }
    Ok((r, rows))
}
/// Exact ordered coverage only; this is measured aggregation, never promotion.
pub struct ResourceLimitsAccumulatorV2 {
    expected: Vec<String>,
    cursor: usize,
    case_hash: Sha256,
    maximum: crate::damage::ResourceProjection,
    maxima: [AdapterRow; 22],
}
impl ResourceLimitsAccumulatorV2 {
    pub fn new(expected: &[&str]) -> Result<Self> {
        if expected.is_empty() || expected.len() > 65535 {
            return Err(ResourceError::Bounds);
        }
        let mut unique = std::collections::BTreeSet::new();
        for id in expected {
            if id.is_empty() || id.len() > 128 || !id.is_ascii() || !unique.insert(*id) {
                return Err(ResourceError::Manifest);
            }
        }
        let mut case_hash = Sha256::new();
        case_hash.update(b"GBRESV2\0");
        case_hash.update((expected.len() as u32).to_be_bytes());
        Ok(Self {
            expected: expected.iter().map(|s| (*s).to_owned()).collect(),
            cursor: 0,
            case_hash,
            maximum: crate::damage::ResourceProjection::default(),
            maxima: [AdapterRow::default(); 22],
        })
    }
    pub fn push(&mut self, id: &str, raw: &[u8]) -> Result<()> {
        if self.expected.get(self.cursor).map(String::as_str) != Some(id) {
            return Err(ResourceError::Binding);
        }
        let (resource, adapter) = read_sidecar(raw)?;
        self.maximum.section_attempts =
            self.maximum.section_attempts.max(resource.section_attempts);
        self.maximum.primitive_steps = self.maximum.primitive_steps.max(resource.primitive_steps);
        self.maximum.peak_scratch_bytes = self
            .maximum
            .peak_scratch_bytes
            .max(resource.peak_scratch_bytes);
        for (max, row) in self.maxima.iter_mut().zip(adapter) {
            max.calls = max.calls.max(row.calls);
            max.units = max.units.max(row.units);
            max.workspace = max.workspace.max(row.workspace);
        }
        self.case_hash.update((id.len() as u16).to_be_bytes());
        self.case_hash.update(id.as_bytes());
        self.case_hash.update(Sha256::digest(raw));
        self.cursor += 1;
        Ok(())
    }
    pub fn finish(self, corpus_sha256: &str) -> Result<Vec<u8>> {
        sha(corpus_sha256)?;
        if self.cursor != self.expected.len() {
            return Err(ResourceError::Binding);
        }
        serialize(o([
            ("schema", s("golden-board.m2-resource-limits/v2")),
            ("corpus_sha256", s(corpus_sha256)),
            ("case_count", V::U64(self.cursor as u64)),
            (
                "case_resources_sha256",
                s(format!("{:x}", self.case_hash.finalize())),
            ),
            ("source_owners", source_owners()),
            ("maximum_resource", resource_value(self.maximum)),
            ("adapter_maxima", row_values(&self.maxima)),
        ]))
    }
}

/// Exact ordered coverage only; this is measured aggregation, never promotion.
pub fn build_resource_limits_v2_owned(
    corpus_sha256: &str,
    expected_case_ids: &[&str],
    rows: impl IntoIterator<Item = (String, Vec<u8>)>,
) -> Result<Vec<u8>> {
    aggregate_resource_limits(corpus_sha256, expected_case_ids, rows)
}

/// Exact ordered coverage only; this is measured aggregation, never promotion.
pub fn build_resource_limits_v2<'a>(
    corpus_sha256: &str,
    expected_case_ids: &[&str],
    rows: impl IntoIterator<Item = (&'a str, &'a [u8])>,
) -> Result<Vec<u8>> {
    aggregate_resource_limits(corpus_sha256, expected_case_ids, rows)
}
fn aggregate_resource_limits<S: AsRef<str>, B: AsRef<[u8]>>(
    corpus_sha256: &str,
    expected_case_ids: &[&str],
    rows: impl IntoIterator<Item = (S, B)>,
) -> Result<Vec<u8>> {
    sha(corpus_sha256)?;
    let mut accumulator = ResourceLimitsAccumulatorV2::new(expected_case_ids)?;
    for (id, raw) in rows {
        accumulator.push(id.as_ref(), raw.as_ref())?;
    }
    accumulator.finish(corpus_sha256)
}

// These helpers consume already checked package metadata and exact observed wire.
pub(crate) fn retained_key(prefix: &str, raw: &[u8]) -> String {
    let mut key = String::with_capacity(prefix.len() + 2 * raw.len());
    key.push_str(prefix);
    use std::fmt::Write;
    for byte in raw {
        write!(&mut key, "{byte:02x}").unwrap();
    }
    key
}
pub(crate) fn retain_program(ledger: &mut ReferenceLedger, raw: &[u8]) -> Result<()> {
    ledger.release("route:program");
    ledger.retain(
        &retained_key("program:", raw),
        program_workspace(raw)?.immutable(),
    )
}
pub(crate) fn example_event(
    ledger: &mut ReferenceLedger,
    package: &crate::recipe::RecipePackage,
    id: u16,
    inputs: usize,
) -> Result<()> {
    let (outputs, descriptors) = package.adapter_shape(id).ok_or(ResourceError::Bounds)?;
    ledger.event(
        Kernel::RouteExample,
        inputs as u64,
        sum([inputs as u64, outputs, mul(8, descriptors)?])?,
    )
}
pub(crate) fn mapping_tests(inner: u16) -> u64 {
    let i = u64::from(inner);
    let p = i * i;
    let q = p / 1728;
    let a = 2 * i - 1;
    let window = 32.max(i / 8);
    let mut tests = 0;
    fn gcd(mut a: u64, mut b: u64) -> u64 {
        while b != 0 {
            (a, b) = (b, a % b)
        }
        a
    }
    for candidate in 1..q {
        if gcd(candidate, q) != 1 {
            continue;
        }
        let mut separates = true;
        for distance in 1..=4 {
            tests += 1;
            let wrapped = candidate * distance % q;
            for delta in [wrapped as i128, wrapped as i128 - q as i128] {
                let flat = (a as i128 * 1728 * delta).rem_euclid(p as i128) as u64;
                let row = flat / i;
                let col = flat % i;
                let dc = col.min(i - col);
                for dr in [row, if col == 0 { row } else { (row + 1) % i }] {
                    if dr.min(i - dr).max(dc) < window {
                        separates = false;
                        break;
                    }
                }
                if !separates {
                    break;
                }
            }
            if !separates {
                break;
            }
        }
        if separates {
            break;
        }
    }
    tests
}

/// V2's explicit legacy validation schedule. Historical parsers do not call this.
pub(crate) fn legacy_rows(
    rows: &[(u8, u8, u16, &[u8])],
    profile: u16,
    sector: u8,
    package_bytes: usize,
    resource: &mut crate::damage::ResourceProjection,
    ledger: &mut ReferenceLedger,
) -> Result<Option<(crate::recipe::RecipePackage, Vec<u8>)>> {
    use crate::recipe::{decode_recipe_package, evaluate_serialized_recipe};
    let read16 = |v: &[u8], at: usize| {
        v.get(at..at + 2)
            .map(|p| u16::from_be_bytes(p.try_into().unwrap()))
    };
    let read32 = |v: &[u8], at: usize| {
        v.get(at..at + 4)
            .map(|p| u32::from_be_bytes(p.try_into().unwrap()) as usize)
    };
    let packages = rows.iter().filter(|r| r.1 == 5).collect::<Vec<_>>();
    if packages.is_empty() || packages.iter().map(|r| r.3.len()).sum::<usize>() != package_bytes {
        return Ok(None);
    }
    let mut parsed = Vec::new();
    let mut recipe_owners = BTreeMap::new();
    let mut tables = BTreeMap::new();
    for row in &packages {
        let wire = row.3;
        if profile == 7 && wire.len() >= 64 && &wire[..8] == b"GBRECP0\0" {
            if u64::from_be_bytes(wire[36..44].try_into().unwrap()) > 268435456
                || read32(wire, 44).unwrap() > 16777216
            {
                return Err(ResourceError::Bounds);
            }
        }
        ledger.event(
            Kernel::RecipeParse,
            wire.len() as u64,
            program_workspace(wire)?.parsing(),
        )?;
        let Ok(package) = decode_recipe_package(wire, profile) else {
            return Ok(None);
        };
        retain_program(ledger, wire)?;
        let owner = parsed.len();
        for id in package.recipe_ids() {
            if recipe_owners.insert(id, owner).is_some() {
                return Ok(None);
            }
        }
        let mut at = 64;
        for _ in 0..read16(wire, 18).unwrap() {
            let end = at + 16 + read32(wire, at + 12).unwrap();
            if tables
                .insert(read16(wire, at).unwrap(), wire[at..end].to_vec())
                .is_some()
            {
                return Ok(None);
            }
            at = end;
        }
        parsed.push(package);
    }
    let base = u16::from(sector) * 10000;
    const STAGES: [u8; 12] = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5];
    const RECIPES: [u16; 12] = [101, 102, 103, 104, 105, 106, 107, 113, 109, 110, 111, 112];
    let mut facts = BTreeMap::new();
    let mut examples = BTreeMap::<(u16, u8), Vec<u8>>::new();
    for &(stage, kind, id, payload) in rows {
        if !(1..=3).contains(&kind) {
            continue;
        }
        let Some(fact) = read16(payload, 0).filter(|v| (1..=12).contains(v)) else {
            return Ok(None);
        };
        if stage != STAGES[usize::from(fact - 1)] || id != base + fact * 100 + u16::from(kind) {
            return Ok(None);
        }
        if kind == 1 {
            if read16(payload, 2) != Some(fact) || facts.insert(fact, ()).is_some() {
                return Ok(None);
            }
            if profile == 7 && !crate::damage_v1::legacy_definition_fields(fact, payload) {
                return Ok(None);
            }
            continue;
        }
        let Some(recipe) = read16(payload, 2) else {
            return Ok(None);
        };
        if profile == 7 && recipe != RECIPES[usize::from(fact - 1)] {
            return Ok(None);
        }
        let (Some(inputs), Some(outputs)) = (read32(payload, 4), read32(payload, 8)) else {
            return Ok(None);
        };
        if 12usize
            .checked_add(inputs)
            .and_then(|n| n.checked_add(outputs))
            != Some(payload.len())
        {
            return Ok(None);
        }
        let Some(owner) = recipe_owners.get(&recipe) else {
            return Ok(None);
        };
        let package = &parsed[*owner];
        example_event(ledger, package, recipe, inputs)?;
        let steps = package
            .recipe_primitive_steps(recipe)
            .ok_or(ResourceError::Bounds)?;
        let scratch = package
            .recipe_peak_scratch_bytes(recipe)
            .ok_or(ResourceError::Bounds)?;
        let next = resource
            .primitive_steps
            .checked_add(steps)
            .ok_or(ResourceError::Arithmetic)?;
        ledger.vm_workspace(scratch)?;
        resource.primitive_steps = next;
        resource.peak_scratch_bytes = resource.peak_scratch_bytes.max(scratch);
        if evaluate_serialized_recipe(package, recipe, &payload[12..12 + inputs])
            .ok()
            .as_deref()
            != Some(&payload[12 + inputs..])
        {
            return Ok(None);
        }
        if examples
            .insert((fact, kind), payload[12..12 + inputs].to_vec())
            .is_some()
        {
            return Ok(None);
        }
    }
    if facts.len() != 12
        || examples.len() != 24
        || (1..=12).any(|fact| examples.get(&(fact, 2)) == examples.get(&(fact, 3)))
    {
        return Ok(None);
    }
    let standalone = rows.iter().filter(|r| r.1 == 4).collect::<Vec<_>>();
    if standalone.len() != tables.len() {
        return Ok(None);
    }
    for (index, (row, (_, wire))) in standalone.iter().zip(&tables).enumerate() {
        if row.0 != 5 || row.2 != base + 5001 + index as u16 || row.3 != wire {
            return Ok(None);
        }
    }
    if packages.len() != 1 || packages[0].0 != 5 || packages[0].2 != base + 6001 {
        return Ok(None);
    }
    let wanted = (1..=12u16)
        .flat_map(|_| [1u8, 2, 3])
        .chain(std::iter::repeat_n(4, tables.len()))
        .chain([5, 6, 7]);
    if rows.iter().map(|r| r.1).ne(wanted) {
        return Ok(None);
    }
    let endpoint = &rows[rows.len() - 2];
    let end = &rows[rows.len() - 1];
    if endpoint.0 != 5
        || endpoint.2 != base + 7001
        || endpoint.3 != 1u32.to_be_bytes()
        || end.0 != 5
        || end.2 != base + 7002
        || !end.3.is_empty()
    {
        return Ok(None);
    }
    Ok(Some((parsed.remove(0), packages[0].3.to_vec())))
}
