//! Source-side observed shell discovery. No production route receiver calls.

use super::resources::{self, AccountingError, Kernel, Ledger, ProgramWorkspace, Reservation};
use crate::damage_corpus_v2::DamageCorpusV2;
use crate::recipe::RecipePackage;
use gb_foundation::{ManifestValue as V, serialize_manifest};
use sha2::{Digest, Sha256};
use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ScanError {
    Unavailable,
    Resource,
    Unsupported,
    Source,
}
type Result<T> = std::result::Result<T, ScanError>;
impl From<AccountingError> for ScanError {
    fn from(error: AccountingError) -> Self {
        match error {
            AccountingError::Overflow | AccountingError::AttemptLimit => Self::Resource,
            AccountingError::Reservation => Self::Source,
        }
    }
}
fn need(value: bool) -> Result<()> {
    if value {
        Ok(())
    } else {
        Err(ScanError::Unavailable)
    }
}
fn take(raw: &[u8], offset: usize, length: usize) -> Result<&[u8]> {
    raw.get(offset..offset.checked_add(length).ok_or(ScanError::Unavailable)?)
        .ok_or(ScanError::Unavailable)
}
fn n16(raw: &[u8], offset: usize) -> Result<u16> {
    Ok(u16::from_be_bytes(
        take(raw, offset, 2)?.try_into().unwrap(),
    ))
}
fn n32(raw: &[u8], offset: usize) -> Result<u32> {
    Ok(u32::from_be_bytes(
        take(raw, offset, 4)?.try_into().unwrap(),
    ))
}
fn n64(raw: &[u8], offset: usize) -> Result<u64> {
    Ok(u64::from_be_bytes(
        take(raw, offset, 8)?.try_into().unwrap(),
    ))
}
fn digest(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn add(a: u64, b: u64) -> Result<u64> {
    a.checked_add(b).ok_or(ScanError::Resource)
}
fn mul(a: u64, b: u64) -> Result<u64> {
    a.checked_mul(b).ok_or(ScanError::Resource)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ScanState {
    Closed,
    ResourceLimit,
}

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct Hypothesis {
    pub transform: u8,
    pub polarity: u8,
    pub sector: u8,
    pub registry_ordinal: u8,
    pub profile: u16,
    pub mapping_sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ObservedMap {
    pub side: u16,
    pub width: u16,
    pub interior: u16,
    pub population: u64,
    pub units: u64,
    pub unit_bytes: u16,
    pub slot_multiplier: u64,
    pub slot_inverse: u64,
    pub multiplier: u64,
    pub offset: u64,
    pub inverse: u64,
    pub hierarchical: bool,
}
impl ObservedMap {
    pub fn physical(&self, one_based_id: u64, bit: u16) -> Result<u64> {
        need(
            (1..=self.units).contains(&one_based_id)
                && u64::from(bit) < u64::from(self.unit_bytes) * 8,
        )?;
        let ordinal = one_based_id - 1;
        let slot = if self.hierarchical {
            self.slot_multiplier * ordinal % self.units
        } else {
            ordinal
        };
        let logical = u64::from(self.unit_bytes) * 8 * slot + u64::from(bit);
        Ok((self.multiplier * logical + self.offset) % self.population)
    }
    fn commitment(&self, route_version: u16) -> Result<String> {
        let mut rows = BTreeMap::from([
            (
                "id".to_owned(),
                V::String(
                    match route_version {
                        0 => "affine-interior-v1",
                        1 => "affine-slot-then-interior-v1",
                        2 => "affine-slot-then-interior-v2",
                        _ => return Err(ScanError::Unavailable),
                    }
                    .to_owned(),
                ),
            ),
            ("interior_side".to_owned(), V::U64(u64::from(self.interior))),
            ("population".to_owned(), V::U64(self.population)),
            ("offset".to_owned(), V::U64(self.offset)),
        ]);
        if self.hierarchical {
            rows.extend([
                ("unit_population".to_owned(), V::U64(self.units)),
                ("unit_multiplier".to_owned(), V::U64(self.slot_multiplier)),
                (
                    "unit_inverse_multiplier".to_owned(),
                    V::U64(self.slot_inverse),
                ),
                ("cell_multiplier".to_owned(), V::U64(self.multiplier)),
                ("cell_inverse_multiplier".to_owned(), V::U64(self.inverse)),
            ]);
        } else {
            rows.extend([
                ("multiplier".to_owned(), V::U64(self.multiplier)),
                ("inverse_multiplier".to_owned(), V::U64(self.inverse)),
            ]);
        }
        Ok(digest(
            &serialize_manifest(&V::Object(rows)).map_err(|_| ScanError::Source)?,
        ))
    }
}

#[derive(Clone)]
pub struct RoutePath {
    pub transform: u8,
    pub polarity: u8,
    pub width: u16,
    pub sector: u8,
    pub profile: u16,
    pub mapping: ObservedMap,
    pub hypothesis: Hypothesis,
    pub(crate) program: Arc<Program>,
    pub(crate) descriptor: Reservation,
}
pub struct DiscoveryAudit {
    pub state: ScanState,
    pub paths: Vec<RoutePath>,
    pub ledger: Ledger,
}

#[derive(Clone)]
struct Record {
    stage: u8,
    kind: u8,
    id: u16,
    payload: Vec<u8>,
}
fn records(raw: &[u8]) -> Result<Vec<Record>> {
    let count = usize::from(n16(raw, 46)?);
    need((37..=256).contains(&count))?;
    let mut cursor = 64;
    let mut output = Vec::with_capacity(count);
    let (mut prior, mut stage) = (0, 0);
    for _ in 0..count {
        let header = take(raw, cursor, 8)?;
        let length = n32(header, 4)? as usize;
        let id = n16(header, 2)?;
        need(header[0] <= 5 && header[0] >= stage && (1..=7).contains(&header[1]) && id > prior)?;
        prior = id;
        stage = header[0];
        let payload = take(raw, cursor + 8, length)?.to_vec();
        cursor += 8 + length;
        output.push(Record {
            stage,
            kind: header[1],
            id,
            payload,
        });
    }
    need(cursor == raw.len())?;
    Ok(output)
}

#[derive(Clone, Copy)]
pub(crate) struct RecipeShape {
    pub input_bytes: u64,
    pub output_bytes: u64,
    pub descriptors: u64,
    pub steps: u64,
    pub scratch: u64,
}
pub(crate) struct Program {
    pub raw: Vec<u8>,
    pub logical: RecipePackage,
    pub storage: ProgramWorkspace,
    pub shapes: BTreeMap<u16, RecipeShape>,
    tables: BTreeMap<u16, Vec<u8>>,
    recipe_records: BTreeMap<u16, Vec<u8>>,
}
impl Program {
    pub(crate) fn parse(raw: &[u8], profile: u16) -> Result<Self> {
        let (expanded, logical) = if profile == 8 {
            let parsed = crate::recipe_wire_v1::decode_recipe_package_v1(raw, 8)
                .map_err(|_| ScanError::Unavailable)?;
            let expanded = crate::recipe_wire_v1::expand_recipe_package_v1(raw, 8)
                .map_err(|_| ScanError::Unavailable)?;
            (expanded, parsed.logical)
        } else {
            (
                raw.to_vec(),
                crate::recipe::decode_recipe_package(raw, profile)
                    .map_err(|_| ScanError::Unavailable)?,
            )
        };
        let mut cursor = 64;
        let mut tables = BTreeMap::new();
        for _ in 0..n16(&expanded, 18)? {
            let length = 16 + n32(&expanded, cursor + 12)? as usize;
            tables.insert(
                n16(&expanded, cursor)?,
                take(&expanded, cursor, length)?.to_vec(),
            );
            cursor += length;
        }
        let mut shapes = BTreeMap::new();
        let mut recipe_records = BTreeMap::new();
        for _ in 0..n16(&expanded, 16)? {
            let length = n32(&expanded, cursor + 28)? as usize;
            let row = take(&expanded, cursor, length)?;
            let (id, inputs, outputs) = (n16(row, 0)?, n16(row, 4)?, n16(row, 6)?);
            let mut shape = RecipeShape {
                input_bytes: 0,
                output_bytes: 0,
                descriptors: u64::from(inputs + outputs),
                steps: n64(row, 16)?,
                scratch: u64::from(n32(row, 24)?),
            };
            for i in 0..usize::from(inputs + outputs) {
                let offset = 32 + i * 12;
                let width = u64::from(n32(row, offset + 4)?);
                let bytes = if row[offset + 2] == 3 {
                    width
                } else {
                    width.div_ceil(8)
                };
                if i < usize::from(inputs) {
                    shape.input_bytes = add(shape.input_bytes, bytes)?;
                } else {
                    shape.output_bytes = add(shape.output_bytes, bytes)?;
                }
            }
            shapes.insert(id, shape);
            recipe_records.insert(id, row.to_vec());
            cursor += length;
        }
        need(cursor == expanded.len())?;
        Ok(Self {
            raw: raw.to_vec(),
            logical,
            storage: resources::program_workspace_from_header(raw)?,
            shapes,
            tables,
            recipe_records,
        })
    }
    pub(crate) fn closure(
        &self,
        roots: &[u16],
    ) -> Result<(BTreeMap<u16, Vec<u8>>, BTreeMap<u16, Vec<u8>>)> {
        let mut recipes = BTreeMap::new();
        let mut tables = BTreeMap::new();
        let mut pending = roots.to_vec();
        while let Some(id) = pending.pop() {
            if recipes.contains_key(&id) {
                continue;
            }
            let raw = self.recipe_records.get(&id).ok_or(ScanError::Unavailable)?;
            let first = 32 + usize::from(n16(raw, 4)? + n16(raw, 6)?) * 12;
            for node in raw[first..].chunks_exact(32) {
                let auxiliary = n16(node, 18)?;
                if node[2] == 22 {
                    pending.push(auxiliary);
                }
                if node[2] == 2 {
                    tables.insert(
                        auxiliary,
                        self.tables
                            .get(&auxiliary)
                            .ok_or(ScanError::Unavailable)?
                            .clone(),
                    );
                }
            }
            recipes.insert(id, raw.clone());
        }
        Ok((recipes, tables))
    }
}

struct Reference {
    records: Vec<Record>,
    program: Arc<Program>,
}
pub struct DiscoveryScanner<'a> {
    pub(crate) source: &'a DamageCorpusV2,
    references: BTreeMap<(u16, u8), Reference>,
    examples: RefCell<BTreeMap<(Vec<u8>, u16, Vec<u8>), Vec<u8>>>,
}
#[derive(Default)]
pub(crate) struct ScanContext {
    programs: BTreeMap<Vec<u8>, Reservation>,
    definitions: BTreeMap<Vec<Vec<u8>>, Reservation>,
    pub hypotheses: BTreeSet<Hypothesis>,
    pub complete_paths: usize,
}
impl ScanContext {
    pub(crate) fn admit_hypothesis(&mut self, path: &RoutePath, ledger: &mut Ledger) -> Result<()> {
        if self.hypotheses.insert(path.hypothesis.clone()) {
            let lease = ledger.retain(48)?;
            ledger.persist(lease)?;
        }
        Ok(())
    }
}
impl<'a> DiscoveryScanner<'a> {
    pub(crate) fn active_program(&self) -> Arc<Program> {
        Arc::clone(&self.references[&(8, 0)].program)
    }
    pub fn new(source: &'a DamageCorpusV2) -> Result<Self> {
        let mut references = BTreeMap::new();
        for sector in &source.source_core().routes.sectors {
            let raw = sector.bits[..sector.route_prefix_cells as usize]
                .chunks_exact(8)
                .map(|v| v.iter().fold(0u8, |a, b| a * 2 + *b))
                .collect::<Vec<_>>();
            let rows = records(&raw).map_err(|_| ScanError::Source)?;
            let package = rows.iter().find(|r| r.kind == 5).ok_or(ScanError::Source)?;
            references.insert(
                (8, sector.sector_id),
                Reference {
                    program: Arc::new(Program::parse(&package.payload, 8)?),
                    records: rows,
                },
            );
        }
        let rows = records(source.source_donor_prefix()).map_err(|_| ScanError::Source)?;
        let package = rows.iter().find(|r| r.kind == 5).ok_or(ScanError::Source)?;
        references.insert(
            (3, 0),
            Reference {
                program: Arc::new(Program::parse(&package.payload, 3)?),
                records: rows,
            },
        );
        Ok(Self {
            source,
            references,
            examples: RefCell::new(BTreeMap::new()),
        })
    }
    pub fn scan_owned(&self, family: &str, ordinal: u64, raw: &[u8]) -> Result<DiscoveryAudit> {
        let owned = self
            .source
            .case(family, ordinal)
            .map_err(|_| ScanError::Source)?;
        if owned.bytes() != raw {
            return Err(ScanError::Source);
        }
        let mut ledger = Ledger::new();
        ledger.adapter(Kernel::Observation, raw.len() as u64, 0)?;
        let matrix = Matrix::parse(owned.channel(), raw)?;
        let _observation = ledger.retain(matrix.cells.len() as u64)?;
        let mut context = ScanContext::default();
        let mut paths = Vec::new();
        for transform in 0..8 {
            for polarity in 0..2 {
                match self.scan_view(&matrix, transform, polarity, &mut context, &mut ledger) {
                    Ok(mut view) => {
                        if context.complete_paths + view.len() > 64 {
                            return Ok(DiscoveryAudit {
                                state: ScanState::ResourceLimit,
                                paths: vec![],
                                ledger,
                            });
                        }
                        context.complete_paths += view.len();
                        for path in &view {
                            context.admit_hypothesis(path, &mut ledger)?;
                            ledger.release(path.descriptor)?;
                        }
                        paths.append(&mut view);
                    }
                    Err(ScanError::Resource) => {
                        return Ok(DiscoveryAudit {
                            state: ScanState::ResourceLimit,
                            paths: vec![],
                            ledger,
                        });
                    }
                    Err(error) => return Err(error),
                }
            }
        }
        Ok(DiscoveryAudit {
            state: ScanState::Closed,
            paths,
            ledger,
        })
    }

    pub(crate) fn scan_view(
        &self,
        matrix: &Matrix,
        transform: u8,
        polarity: u8,
        context: &mut ScanContext,
        ledger: &mut Ledger,
    ) -> Result<Vec<RoutePath>> {
        ledger.adapter(Kernel::SquareView, matrix.cells.len() as u64, 0)?;
        let mut paths = Vec::new();
        let upper = 128.min(matrix.side.saturating_sub(8) / 2);
        for width in (8..=upper).step_by(8) {
            for sector in 0..4 {
                match self.scan_sector(matrix, transform, polarity, width, sector, context, ledger)
                {
                    Ok(path) => paths.push(path),
                    Err(ScanError::Unavailable) => {}
                    Err(error) => return Err(error),
                }
            }
        }
        paths.sort_by_key(|p| (registry(p.profile), p.width, p.sector));
        Ok(paths)
    }

    fn scan_sector(
        &self,
        matrix: &Matrix,
        transform: u8,
        polarity: u8,
        width: u16,
        sector: u8,
        context: &mut ScanContext,
        ledger: &mut Ledger,
    ) -> Result<RoutePath> {
        let header = matrix.shell(transform, polarity, width, sector, 64, ledger)?;
        let header_lease = ledger.retain(64)?;
        let result = (|| {
            let version = n16(&header, 40)?;
            let profile = n16(&header, 44)?;
            let record_bytes = n32(&header, 48)? as usize;
            let length = 64_usize
                .checked_add(record_bytes)
                .ok_or(ScanError::Unavailable)?;
            let extent = usize::from(width) * usize::from(matrix.side - width);
            need(length <= 30_720 && length.checked_mul(8).is_some_and(|n| n <= extent))?;
            if version != 2 {
                validate_header(&header, sector, length)?;
            }
            let raw = matrix.shell(transform, polarity, width, sector, length, ledger)?;
            let prefix_lease = ledger.retain(length as u64)?;
            let parsed = (|| {
                validate_header(&header, sector, length)?;
                ledger.adapter(
                    Kernel::RouteFrame,
                    length as u64,
                    u64::from(n16(&header, 46)?) * 8,
                )?;
                let rows = records(&raw)?;
                self.validate_records(
                    &header,
                    rows,
                    matrix.side,
                    width,
                    transform,
                    polarity,
                    sector,
                    profile,
                    version,
                    context,
                    ledger,
                )
            })();
            ledger.release(prefix_lease)?;
            parsed
        })();
        ledger.release(header_lease)?;
        result
    }

    #[allow(clippy::too_many_arguments)]
    fn validate_records(
        &self,
        header: &[u8],
        rows: Vec<Record>,
        side: u16,
        width: u16,
        transform: u8,
        polarity: u8,
        sector: u8,
        profile: u16,
        version: u16,
        context: &mut ScanContext,
        ledger: &mut Ledger,
    ) -> Result<RoutePath> {
        let reference = self
            .references
            .get(&(profile, sector))
            .ok_or(ScanError::Unsupported)?;
        need(rows.len() == reference.records.len())?;
        for (actual, expected) in rows.iter().zip(&reference.records) {
            need(
                (actual.stage, actual.kind, actual.id)
                    == (expected.stage, expected.kind, expected.id),
            )?;
        }
        let package_row = rows
            .iter()
            .find(|r| r.kind == 5)
            .ok_or(ScanError::Unavailable)?;
        let wire = &package_row.payload;
        need(wire.len() == n32(header, 52)? as usize)?;
        if version == 2
            && wire.len() >= 64
            && &wire[..8] == b"GBRECP0\0"
            && (n64(wire, 36)? > 268_435_456 || n32(wire, 44)? > 16_777_216)
        {
            return Err(ScanError::Resource);
        }
        let storage = resources::program_workspace_from_header(wire)?;
        ledger.adapter(
            Kernel::RecipeParse,
            wire.len() as u64,
            storage.parse_workspace()?,
        )?;
        let program = if *wire == reference.program.raw {
            Arc::clone(&reference.program)
        } else {
            Arc::new(Program::parse(wire, profile)?)
        };
        let program_lease = ledger.retain(storage.immutable_bytes)?;
        let mut promoted = false;
        if version < 2 {
            if !context.programs.contains_key(wire) {
                context.programs.insert(wire.clone(), program_lease);
                ledger.persist(program_lease)?;
                promoted = true;
            }
        }
        let outcome = (|| {
            if version == 2 {
                ledger.adapter(
                    Kernel::ProgramRefinement,
                    storage.logical_nodes,
                    storage.refinement_extra_bytes,
                )?;
                need(
                    program.closure(&[109, 30, 113])?
                        == reference.program.closure(&[109, 30, 113])?,
                )?;
                // The body interface is admitted independently of optional native refinement.
                let shape = program.shapes.get(&202).ok_or(ScanError::Unavailable)?;
                need(
                    shape.input_bytes == 16_386
                        && shape.output_bytes == 16_388
                        && shape.descriptors == 5,
                )?;
            }
            for row in rows.iter().filter(|r| r.kind == 4) {
                let id = n16(&row.payload, 0)?;
                need(program.tables.get(&id) == Some(&row.payload))?;
            }
            let mut examples = BTreeMap::<u16, Vec<Vec<u8>>>::new();
            let mut definitions = Vec::new();
            for (row, expected) in rows.iter().zip(&reference.records) {
                if row.kind == 1 {
                    let fact = n16(&row.payload, 0)?;
                    need(fact == (definitions.len() + 1) as u16 && n16(&row.payload, 2)? == fact)?;
                    if version == 2 {
                        need(
                            row.payload.get(4..6) == Some(&[3, 0])
                                && n32(&row.payload, 10)? == 1
                                && row.payload.len() == 14 + n32(&row.payload, 6)? as usize,
                        )?;
                    }
                    definitions.push(row.payload[14..].to_vec());
                } else if matches!(row.kind, 2 | 3) {
                    need(row.payload.len() >= 14)?;
                    let fact = n16(&row.payload, 0)?;
                    let recipe = n16(&row.payload, 2)?;
                    need(
                        fact == n16(&expected.payload, 0)? && recipe == n16(&expected.payload, 2)?,
                    )?;
                    let input_length = n32(&row.payload, 4)? as usize;
                    let output_length = n32(&row.payload, 8)? as usize;
                    need(
                        12usize
                            .checked_add(input_length)
                            .and_then(|n| n.checked_add(output_length))
                            == Some(row.payload.len()),
                    )?;
                    let input = take(&row.payload, 12, input_length)?;
                    let expected_output = take(&row.payload, 12 + input_length, output_length)?;
                    let inputs = examples.entry(fact).or_default();
                    need(!inputs.iter().any(|old| old.as_slice() == input))?;
                    inputs.push(input.to_vec());
                    let output = self.call(&program, recipe, input, ledger)?;
                    need(output == expected_output)?;
                } else if row.kind == 6 {
                    need(row.payload == 1u32.to_be_bytes())?;
                } else if row.kind == 7 {
                    need(row.payload.is_empty())?;
                }
            }
            let mapping = derive_map(side, width, profile, version, &program, ledger)?;
            for logical in [0, 1, mapping.population - 1] {
                let mut input = (logical as u32).to_be_bytes().to_vec();
                input.extend(side.to_be_bytes());
                input.extend(width.to_be_bytes());
                let actual = self.call(&program, 109, &input, ledger)?;
                let physical = (mapping.multiplier * logical + mapping.offset) % mapping.population;
                let mut expected = vec![0, 0];
                expected.extend((physical as u32).to_be_bytes());
                need(actual == expected)?;
            }
            if version == 2 {
                let total = definitions.iter().map(|v| v.len() as u64).sum::<u64>();
                ledger.adapter(
                    Kernel::DefinitionValidation,
                    total,
                    resources::definition_workspace(total, storage)?,
                )?;
            }
            // Source construction has proved these exact finite relationships. A
            // different locally meaningful value needs a new proof, not rejection.
            for (row, expected) in rows
                .iter()
                .zip(&reference.records)
                .filter(|(r, _)| r.kind == 1)
            {
                if row.payload != expected.payload {
                    return Err(ScanError::Unsupported);
                }
            }
            if version == 2 && !context.definitions.contains_key(&definitions) {
                let bytes = definitions.iter().map(|v| v.len() as u64 + 16).sum();
                let lease = ledger.retain(bytes)?;
                ledger.persist(lease)?;
                context.definitions.insert(definitions.clone(), lease);
            }
            let hypothesis = Hypothesis {
                transform,
                polarity,
                sector,
                registry_ordinal: registry(profile),
                profile,
                mapping_sha256: mapping.commitment(version)?,
            };
            Ok(RoutePath {
                transform,
                polarity,
                width,
                sector,
                profile,
                mapping,
                hypothesis,
                program: Arc::clone(&program),
                descriptor: ledger.retain(128)?,
            })
        })();
        if outcome.is_ok() && !context.programs.contains_key(wire) {
            context.programs.insert(wire.clone(), program_lease);
            ledger.persist(program_lease)?;
            promoted = true;
        }
        if !promoted {
            ledger.release(program_lease)?;
        }
        outcome
    }

    pub(crate) fn call(
        &self,
        program: &Program,
        id: u16,
        input: &[u8],
        ledger: &mut Ledger,
    ) -> Result<Vec<u8>> {
        let shape = program.shapes.get(&id).ok_or(ScanError::Unavailable)?;
        let workspace = add(
            add(input.len() as u64, shape.output_bytes)?,
            mul(8, shape.descriptors)?,
        )?;
        ledger.adapter(Kernel::RouteExample, input.len() as u64, workspace)?;
        let lease = ledger.retain(workspace)?;
        let result = (|| {
            ledger.vm(shape.steps, shape.scratch)?;
            let key = (program.raw.clone(), id, input.to_vec());
            if let Some(output) = self.examples.borrow().get(&key) {
                return Ok(output.clone());
            }
            let output =
                crate::recipe::evaluate_serialized_validated_recipe(&program.logical, id, input)
                    .map_err(|_| ScanError::Unavailable)?;
            if self.examples.borrow().len() < 4096 {
                self.examples.borrow_mut().insert(key, output.clone());
            }
            Ok(output)
        })();
        ledger.release(lease)?;
        result
    }
}

fn registry(profile: u16) -> u8 {
    [8, 2, 3, 4, 5, 6, 7]
        .iter()
        .position(|p| *p == profile)
        .map_or(255, |n| n as u8)
}
fn validate_header(raw: &[u8], sector: u8, length: usize) -> Result<()> {
    const CALIBRATIONS: [&str; 4] = [
        "f00fcc33aa559669817e24db18e742bd01fe02fd04fb08f710ef20df40bf807f",
        "cc33aa559669f00f02fd18e742bd817e04fb08f710ef20df40bf807f01fe24db",
        "aa559669f00fcc3304fb42bd817e24db08f710ef20df40bf807f01fe02fd18e7",
        "9669f00fcc33aa5508f7817e24db18e710ef20df40bf807f01fe02fd04fb42bd",
    ];
    let calibration = CALIBRATIONS[usize::from(sector)]
        .as_bytes()
        .chunks_exact(2)
        .map(|v| u8::from_str_radix(std::str::from_utf8(v).unwrap(), 16).unwrap())
        .collect::<Vec<_>>();
    need(
        raw[..32] == calibration
            && &raw[32..40] == b"GBROUTE\0"
            && raw[42] == sector
            && raw[43] == sector,
    )?;
    let (version, profile) = (n16(raw, 40)?, n16(raw, 44)?);
    need(matches!((version, profile), (0, 2..=6) | (1, 7) | (2, 8)))?;
    need(n16(raw, 60)? == 256 && n16(raw, 62)? == 0 && n32(raw, 56)? as usize == length * 8)?;
    let count = n16(raw, 46)?;
    need(if version == 2 {
        count == 47
    } else {
        (37..=256).contains(&count)
    })
}

fn gcd(mut a: u64, mut b: u64) -> u64 {
    while b != 0 {
        (a, b) = (b, a % b);
    }
    a
}
fn smallest_multiplier(interior: u64) -> (Option<u64>, u64) {
    let population = interior * interior;
    let units = population / 1728;
    if units < 2 {
        return (None, 0);
    }
    let multiplier = 2 * interior - 1;
    let window = 32.max(interior / 8);
    let mut tests = 0;
    for b in 1..units {
        if gcd(b, units) != 1 {
            continue;
        }
        let mut valid = true;
        for distance in 1..=4 {
            tests += 1;
            let wrapped = b * distance % units;
            for delta in [i128::from(wrapped), i128::from(wrapped) - i128::from(units)] {
                let flat = (i128::from(multiplier) * 1728 * delta)
                    .rem_euclid(i128::from(population)) as u64;
                let (row, column) = (flat / interior, flat % interior);
                let rows = if column == 0 {
                    vec![row]
                } else {
                    vec![row, (row + 1) % interior]
                };
                for r in rows {
                    if r.min(interior - r).max(column.min(interior - column)) < window {
                        valid = false;
                        break;
                    }
                }
                if !valid {
                    break;
                }
            }
            if !valid {
                break;
            }
        }
        if valid {
            return (Some(b), tests);
        }
    }
    (None, tests)
}
fn derive_map(
    side: u16,
    width: u16,
    profile: u16,
    version: u16,
    program: &Program,
    ledger: &mut Ledger,
) -> Result<ObservedMap> {
    need(
        (64..=2048).contains(&side)
            && side % 8 == 0
            && width % 8 == 0
            && (8..=128).contains(&width)
            && u32::from(width) * 2 + 8 <= u32::from(side),
    )?;
    let interior = side - 2 * width;
    let i = u64::from(interior);
    let population = i * i;
    let unit_bytes = if matches!(profile, 5 | 6) { 255 } else { 216 };
    let units = population / (u64::from(unit_bytes) * 8);
    let (slot_multiplier, slot_inverse) = if version > 0 {
        let table = program.tables.get(&17).ok_or(ScanError::Unavailable)?;
        need(
            table.len() == 272
                && table[2..4] == [0, 0]
                && n32(table, 4)? == 8
                && n32(table, 8)? == 256
                && n32(table, 12)? == 256,
        )?;
        let (found, tests) = smallest_multiplier(i);
        ledger.adapter(Kernel::MappingSearch, tests, 64)?;
        let b = found.ok_or(ScanError::Unavailable)?;
        need(u64::from(table[16 + usize::from(interior / 8)]) == b)?;
        let inverse = (1..units)
            .find(|n| b * n % units == 1)
            .ok_or(ScanError::Unavailable)?;
        (b, inverse)
    } else {
        (1, 1)
    };
    Ok(ObservedMap {
        side,
        width,
        interior,
        population,
        units,
        unit_bytes,
        slot_multiplier,
        slot_inverse,
        multiplier: 2 * i - 1,
        offset: (u64::from(profile) * 40503 + u64::from(width) * 257) % population,
        inverse: population - 2 * i - 1,
        hierarchical: version > 0,
    })
}

pub(crate) struct Matrix {
    pub side: u16,
    pub cells: Vec<u8>,
}
impl Matrix {
    pub fn parse(channel: &str, raw: &[u8]) -> Result<Self> {
        let (side, cells) = match channel {
            "OBS_MATRIX" => {
                let side = usize::from(n16(raw, 0)?);
                need(side <= 2048 && side > 0 && raw.len() == 2 + side * side)?;
                need(raw[2..].iter().all(|v| *v <= 2))?;
                (side, raw[2..].to_vec())
            }
            "OBS_BITS" => {
                let count = n32(raw, 0)? as usize;
                need(count > 0 && count <= 4_194_304 && raw.len() == 4 + count.div_ceil(8))?;
                if count % 8 != 0 {
                    need(raw.last().unwrap() & ((1 << (8 - count % 8)) - 1) == 0)?;
                }
                let side = count.isqrt();
                need(side * side == count && side <= 2048)?;
                let values = (0..count)
                    .map(|b| (raw[4 + b / 8] >> (7 - b % 8)) & 1)
                    .collect();
                (side, values)
            }
            _ => return Err(ScanError::Unavailable),
        };
        Ok(Self {
            side: side as u16,
            cells,
        })
    }
    pub fn value(&self, t: u8, p: u8, r: usize, c: usize) -> u8 {
        let last = usize::from(self.side) - 1;
        let (r, c) = match t {
            0 => (r, c),
            1 => (last - c, r),
            2 => (last - r, last - c),
            3 => (c, last - r),
            4 => (r, last - c),
            5 => (last - c, last - r),
            6 => (last - r, c),
            _ => (c, r),
        };
        let value = self.cells[r * usize::from(self.side) + c];
        if value == 2 { 2 } else { value ^ p }
    }
    fn shell(
        &self,
        t: u8,
        p: u8,
        width: u16,
        sector: u8,
        bytes: usize,
        ledger: &mut Ledger,
    ) -> Result<Vec<u8>> {
        ledger.adapter(Kernel::ShellRead, mul(bytes as u64, 8)?, bytes as u64)?;
        let side = usize::from(self.side);
        let width = usize::from(width);
        need(bytes * 8 <= width * (side - width))?;
        let mut out = vec![0; bytes];
        for bit in 0..bytes * 8 {
            let (u, v) = (bit / (side - width), bit % (side - width));
            let (r, c) = match sector {
                0 => (u, v),
                1 => (v, side - 1 - u),
                2 => (side - 1 - u, side - 1 - v),
                _ => (side - 1 - v, u),
            };
            let value = self.value(t, p, r, c);
            need(value != 2)?;
            out[bit / 8] |= value << (7 - bit % 8);
        }
        Ok(out)
    }
}
