//! Observation-only admission of development route-v2. No route/lesson/carrier
//! builder or saved prefix is an input. Numeric relationships are checked with
//! neutral primitives; recovered-context evidence remains separate from availability.
use crate::damage::{ObsMatrix, ResourceProjection};
use crate::mapping_v2::{self, Mapping};
use crate::recipe_wire_v1::{
    RecipePackageV1, decode_recipe_package_v1, evaluate_serialized_recipe_v1,
};
use crate::resources_v2::{self, Kernel, ReferenceLedger};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
const CALIBRATIONS: [[u8; 32]; 4] = [
    [
        0xf0, 0x0f, 0xcc, 0x33, 0xaa, 0x55, 0x96, 0x69, 0x81, 0x7e, 0x24, 0xdb, 0x18, 0xe7, 0x42,
        0xbd, 0x01, 0xfe, 0x02, 0xfd, 0x04, 0xfb, 0x08, 0xf7, 0x10, 0xef, 0x20, 0xdf, 0x40, 0xbf,
        0x80, 0x7f,
    ],
    [
        0xcc, 0x33, 0xaa, 0x55, 0x96, 0x69, 0xf0, 0x0f, 0x02, 0xfd, 0x18, 0xe7, 0x42, 0xbd, 0x81,
        0x7e, 0x04, 0xfb, 0x08, 0xf7, 0x10, 0xef, 0x20, 0xdf, 0x40, 0xbf, 0x80, 0x7f, 0x01, 0xfe,
        0x24, 0xdb,
    ],
    [
        0xaa, 0x55, 0x96, 0x69, 0xf0, 0x0f, 0xcc, 0x33, 0x04, 0xfb, 0x42, 0xbd, 0x81, 0x7e, 0x24,
        0xdb, 0x08, 0xf7, 0x10, 0xef, 0x20, 0xdf, 0x40, 0xbf, 0x80, 0x7f, 0x01, 0xfe, 0x02, 0xfd,
        0x18, 0xe7,
    ],
    [
        0x96, 0x69, 0xf0, 0x0f, 0xcc, 0x33, 0xaa, 0x55, 0x08, 0xf7, 0x81, 0x7e, 0x24, 0xdb, 0x18,
        0xe7, 0x10, 0xef, 0x20, 0xdf, 0x40, 0xbf, 0x80, 0x7f, 0x01, 0xfe, 0x02, 0xfd, 0x04, 0xfb,
        0x42, 0xbd,
    ],
];
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RouteError {
    ResourceLimit,
    Observation,
}
pub type Result<T> = std::result::Result<T, RouteError>;
const STAGES: [u8; 12] = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5];
const PRIMARY: [u16; 12] = [101, 102, 103, 104, 105, 211, 107, 113, 109, 110, 111, 112];
const RECIPE_IDS: [u16; 29] = [
    1, 2, 3, 4, 30, 90, 92, 99, 100, 101, 102, 103, 104, 105, 107, 108, 109, 110, 111, 112, 113,
    201, 202, 203, 210, 211, 212, 213, 214,
];
const TABLE_IDS: [u16; 14] = [3, 4, 5, 10, 11, 12, 13, 14, 15, 17, 18, 19, 20, 21];
fn u16_at(raw: &[u8], at: usize) -> Option<u16> {
    Some(u16::from_be_bytes(
        raw.get(at..at.checked_add(2)?)?.try_into().ok()?,
    ))
}
fn u32_at(raw: &[u8], at: usize) -> Option<u32> {
    Some(u32::from_be_bytes(
        raw.get(at..at.checked_add(4)?)?.try_into().ok()?,
    ))
}
pub(crate) fn charge(
    resource: &mut ResourceProjection,
    steps: u64,
    count: u64,
    scratch: u64,
) -> Result<()> {
    resource.primitive_steps = resource
        .primitive_steps
        .checked_add(steps.checked_mul(count).ok_or(RouteError::ResourceLimit)?)
        .ok_or(RouteError::ResourceLimit)?;
    resource.peak_scratch_bytes = resource.peak_scratch_bytes.max(scratch);
    Ok(())
}
fn charge_recipe(
    resource: &mut ResourceProjection,
    package: &RecipePackageV1,
    id: u16,
) -> Result<()> {
    charge(
        resource,
        package
            .logical
            .recipe_primitive_steps(id)
            .ok_or(RouteError::Observation)?,
        1,
        package
            .logical
            .recipe_peak_scratch_bytes(id)
            .ok_or(RouteError::Observation)?,
    )
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ObservedRoute {
    width: u16,
    sector: u8,
    mapping: Mapping,
    package: RecipePackageV1,
    definitions: Vec<Vec<u8>>,
    commitments: crate::route_semantics_v2::ContextCommitments,
}
impl ObservedRoute {
    pub fn mapping(&self) -> &Mapping {
        &self.mapping
    }
    pub fn package(&self) -> &RecipePackageV1 {
        &self.package
    }
    pub(crate) fn definitions(&self) -> &[Vec<u8>] {
        &self.definitions
    }
    pub fn commitments(&self) -> &crate::route_semantics_v2::ContextCommitments {
        &self.commitments
    }
    pub fn width(&self) -> u16 {
        self.width
    }
    pub fn sector(&self) -> u8 {
        self.sector
    }
    pub fn mapping_sha256(&self) -> Result<String> {
        use gb_foundation::ManifestValue as V;
        let map = &self.mapping;
        let mut fields = BTreeMap::new();
        fields.insert(
            "id".into(),
            V::String("affine-slot-then-interior-v2".into()),
        );
        for (key, value) in [
            ("interior_side", u64::from(map.interior_side())),
            ("population", map.population()),
            ("unit_population", map.unit_slot_count()),
            ("unit_multiplier", map.slot_multiplier()),
            ("unit_inverse_multiplier", map.inverse_slot_multiplier()),
            ("cell_multiplier", map.cell_multiplier()),
            ("offset", map.cell_offset()),
            ("cell_inverse_multiplier", map.inverse_cell_multiplier()),
        ] {
            fields.insert(key.into(), V::U64(value));
        }
        let bytes = gb_foundation::serialize_manifest(&V::Object(fields))
            .map_err(|_| RouteError::Observation)?;
        Ok(format!("{:x}", Sha256::digest(bytes)))
    }
}
fn tables(raw: &[u8]) -> Option<BTreeMap<u16, &[u8]>> {
    let count = usize::from(u16_at(raw, 18)?);
    if count > 4096 {
        return None;
    }
    let mut cursor = 64usize;
    let mut rows = BTreeMap::new();
    for _ in 0..count {
        let length = u32_at(raw, cursor + 12)? as usize;
        let end = cursor.checked_add(16)?.checked_add(length)?;
        let row = raw.get(cursor..end)?;
        if rows.insert(u16_at(row, 0)?, row).is_some() {
            return None;
        }
        cursor = end;
    }
    Some(rows)
}
fn definition_shape(fact: u16, payload: &[u8]) -> bool {
    let lengths = [16, 64, 96, 296, 226, 210, 636, 544, 464, 294, 314, 2421];
    if !(1..=12).contains(&fact)
        || payload.len() != 14 + lengths[usize::from(fact - 1)]
        || u16_at(payload, 0) != Some(fact)
        || u16_at(payload, 2) != Some(fact)
        || payload.get(4..6) != Some(&[3, 0])
        || u32_at(payload, 6) != Some((payload.len() - 14) as u32)
        || u32_at(payload, 10) != Some(1)
    {
        return false;
    }
    if fact == 12 {
        let value = &payload[14..];
        // The miniature is carried bytes, checked independently as content.
        if u16_at(value, 0) != Some(0)
            || u16_at(value, 6) != Some(1)
            || u16_at(value, 12) != Some(2)
            || u16_at(value, 14) != Some(29)
            || u16_at(value, 16) != Some(29)
            || u32_at(value, 206) != Some(575)
            || u32_at(value, 785) != Some(1056)
            || u16_at(value, 789) != Some(48)
            || u16_at(value, 2013) != Some(2)
        {
            return false;
        }
    }
    true
}
fn skeleton(sector: u8) -> Vec<(u8, u8, u16, Option<u16>)> {
    let base = u16::from(sector) * 10000;
    let mut out = Vec::with_capacity(47);
    for fact in 1..=12u16 {
        let stage = STAGES[usize::from(fact - 1)];
        for kind in 1..=3u8 {
            out.push((
                stage,
                kind,
                base + fact * 100 + u16::from(kind),
                (kind != 1).then_some(PRIMARY[usize::from(fact - 1)]),
            ));
        }
        if fact == 6 {
            for (index, recipe) in [105, 211, 211, 212, 214, 214].into_iter().enumerate() {
                out.push((
                    stage,
                    2 + (index % 2) as u8,
                    base + 610 + index as u16,
                    Some(recipe),
                ));
            }
        }
        if fact == 12 {
            out.push((stage, 2, base + 1210, Some(203)));
            out.push((stage, 3, base + 1211, Some(203)));
        }
    }
    out.extend([
        (5, 5, base + 6001, None),
        (5, 6, base + 7001, None),
        (5, 7, base + 7002, None),
    ]);
    out
}
/// Admit exact framing and execute every supplied example. Invalid routes are
/// `None`; a declared/global resource violation is an error, never a fallback.
pub fn admit_route_prefix(
    raw: &[u8],
    side: u16,
    width: u16,
    sector: u8,
    resource: &mut ResourceProjection,
) -> Result<Option<ObservedRoute>> {
    admit_route_prefix_mode(raw, side, width, sector, resource, None)
}
fn admit_route_prefix_mode(
    raw: &[u8],
    side: u16,
    width: u16,
    sector: u8,
    resource: &mut ResourceProjection,
    mut adapter: Option<&mut ReferenceLedger>,
) -> Result<Option<ObservedRoute>> {
    if sector > 3
        || raw.len() < 64
        || raw.len() > 30784
        || !(64..=2048).contains(&side)
        || side % 8 != 0
        || !(8..=128).contains(&width)
        || width % 8 != 0
        || u32::from(width) * 2 + 8 > u32::from(side)
    {
        return Ok(None);
    }
    let head = &raw[32..64];
    if raw[..32] != CALIBRATIONS[usize::from(sector)]
        || head[..8] != *b"GBROUTE\0"
        || u16_at(head, 8) != Some(2)
        || head[10] != sector
        || head[11] != sector
        || u16_at(head, 12) != Some(8)
        || u16_at(head, 14) != Some(47)
        || u32_at(head, 16) != Some((raw.len() - 64) as u32)
        || u32_at(head, 24) != Some((raw.len() * 8) as u32)
        || u16_at(head, 28) != Some(256)
        || u16_at(head, 30) != Some(0)
        || raw.len() * 8 > usize::from(width) * usize::from(side - width)
    {
        return Ok(None);
    }
    if let Some(m) = adapter.as_deref_mut() {
        m.event(Kernel::RouteFrame, raw.len() as u64, 8 * 47)
            .map_err(|_| RouteError::ResourceLimit)?;
    }
    let wanted = skeleton(sector);
    let mut cursor = 64usize;
    let mut rows = Vec::with_capacity(47);
    for (stage, kind, id, recipe) in wanted {
        let Some(header) = raw.get(cursor..cursor + 8) else {
            return Ok(None);
        };
        let end = cursor
            .checked_add(8)
            .and_then(|start| start.checked_add(u32_at(header, 4)? as usize))
            .ok_or(RouteError::ResourceLimit)?;
        let Some(payload) = raw.get(cursor + 8..end) else {
            return Ok(None);
        };
        if header[0] != stage || header[1] != kind || u16_at(header, 2) != Some(id) {
            return Ok(None);
        }
        if kind == 1 {
            let fact = (id - u16::from(sector) * 10000) / 100;
            if !definition_shape(fact, payload) {
                return Ok(None);
            }
        }
        if let Some(recipe) = recipe {
            let Some(input) = u32_at(payload, 4) else {
                return Ok(None);
            };
            let Some(output) = u32_at(payload, 8) else {
                return Ok(None);
            };
            let fact = if id % 10000 >= 1200 {
                12
            } else {
                (id % 10000) / 100
            };
            if payload.len() != 12 + input as usize + output as usize
                || u16_at(payload, 0) != Some(fact)
                || u16_at(payload, 2) != Some(recipe)
                || output < 2
            {
                return Ok(None);
            }
            let status = u16_at(payload, 12 + input as usize).unwrap();
            if status > 14 || (status != 0 && output != 2) {
                return Ok(None);
            }
        }
        rows.push((kind, recipe, payload));
        cursor = end;
    }
    if cursor != raw.len() || rows[45].2 != 1u32.to_be_bytes() || !rows[46].2.is_empty() {
        return Ok(None);
    }
    let package_raw = rows[44].2;
    if u32_at(head, 20) != Some(package_raw.len() as u32) {
        return Ok(None);
    }
    if package_raw.len() >= 64 && &package_raw[..8] == b"GBRECP0\0" {
        let steps = u64::from_be_bytes(package_raw[36..44].try_into().unwrap());
        let scratch = u32_at(package_raw, 44).unwrap();
        if steps > 268435456
            || scratch > 16777216
            || u32_at(package_raw, 20).unwrap() > 65535
            || u32_at(package_raw, 24).unwrap() > 262140
        {
            return Err(RouteError::ResourceLimit);
        }
    }
    if let Some(m) = adapter.as_deref_mut() {
        m.event(
            Kernel::RecipeParse,
            package_raw.len() as u64,
            resources_v2::program_workspace(package_raw)
                .map_err(|_| RouteError::ResourceLimit)?
                .parsing(),
        )
        .map_err(|_| RouteError::ResourceLimit)?;
    }
    let Ok(package) = decode_recipe_package_v1(package_raw, 8) else {
        return Ok(None);
    };
    if let Some(m) = adapter.as_deref_mut() {
        let w =
            resources_v2::program_workspace(package_raw).map_err(|_| RouteError::ResourceLimit)?;
        m.retain("route:program", w.immutable())
            .map_err(|_| RouteError::ResourceLimit)?;
        m.event(
            Kernel::ProgramRefinement,
            u64::from(u32_at(package_raw, 20).unwrap()),
            w.refinement(),
        )
        .map_err(|_| RouteError::ResourceLimit)?;
    }
    if package.logical.recipe_ids().ne(RECIPE_IDS)
        || !mapping_refines(&package)
        || !transport_refines_and_body_interface(&package)
    {
        return Ok(None);
    }
    let Some(tables) = tables(package_raw) else {
        return Ok(None);
    };
    if tables.keys().copied().ne(TABLE_IDS) {
        return Ok(None);
    }
    let definitions = rows
        .iter()
        .filter(|row| row.0 == 1)
        .map(|row| row.2[14..].to_vec())
        .collect::<Vec<_>>();
    for (_, recipe, payload) in &rows {
        if let Some(recipe) = recipe {
            let input = u32_at(payload, 4).unwrap() as usize;
            if let Some(m) = adapter.as_deref_mut() {
                resources_v2::example_event(m, &package.logical, *recipe, input)
                    .map_err(|_| RouteError::ResourceLimit)?;
            }
            charge_recipe(resource, &package, *recipe)?;
            if let Some(m) = adapter.as_deref_mut() {
                m.vm_workspace(package.logical.recipe_peak_scratch_bytes(*recipe).unwrap())
                    .map_err(|_| RouteError::ResourceLimit)?;
            }
            if evaluate_serialized_recipe_v1(&package, *recipe, &payload[12..12 + input])
                .ok()
                .as_deref()
                != Some(&payload[12 + input..])
            {
                return Ok(None);
            }
        }
    }
    if let Some(m) = adapter.as_deref_mut() {
        m.event(
            Kernel::MappingSearch,
            resources_v2::mapping_tests(side - 2 * width),
            64,
        )
        .map_err(|_| RouteError::ResourceLimit)?;
    }
    let Ok(mapping) = mapping_v2::derive(side, width) else {
        return Ok(None);
    };
    let table = tables[&17];
    let index = usize::from(mapping.interior_side() / 8);
    if table.len() != 272
        || table[2..4] != [0, 0]
        || u32_at(table, 4) != Some(8)
        || u32_at(table, 8) != Some(256)
        || u32_at(table, 12) != Some(256)
        || u64::from(table[16 + index]) != mapping.slot_multiplier()
    {
        return Ok(None);
    }
    for logical in [0, 1, mapping.population() - 1] {
        let mut input = (logical as u32).to_be_bytes().to_vec();
        input.extend(side.to_be_bytes());
        input.extend(width.to_be_bytes());
        if let Some(m) = adapter.as_deref_mut() {
            resources_v2::example_event(m, &package.logical, 109, input.len())
                .map_err(|_| RouteError::ResourceLimit)?;
        }
        charge_recipe(resource, &package, 109)?;
        if let Some(m) = adapter.as_deref_mut() {
            m.vm_workspace(package.logical.recipe_peak_scratch_bytes(109).unwrap())
                .map_err(|_| RouteError::ResourceLimit)?;
        }
        let expected = ((mapping.cell_multiplier() * logical + mapping.cell_offset())
            % mapping.population()) as u32;
        let mut output = vec![0, 0];
        output.extend(expected.to_be_bytes());
        if evaluate_serialized_recipe_v1(&package, 109, &input).ok() != Some(output) {
            return Ok(None);
        }
    }
    if let Some(m) = adapter.as_deref_mut() {
        let bytes = definitions.iter().map(|v| v.len() as u64).sum();
        let w = resources_v2::definition_workspace(
            bytes,
            resources_v2::program_workspace(package_raw).map_err(|_| RouteError::ResourceLimit)?,
        )
        .map_err(|_| RouteError::ResourceLimit)?;
        m.event(Kernel::DefinitionValidation, bytes, w)
            .map_err(|_| RouteError::ResourceLimit)?;
    }
    let Ok(commitments) = crate::route_semantics_v2::validate_definitions(
        &definitions.iter().map(Vec::as_slice).collect::<Vec<_>>(),
        &package,
    ) else {
        return Ok(None);
    };
    if let Some(m) = adapter.as_deref_mut() {
        resources_v2::retain_program(m, package_raw).map_err(|_| RouteError::ResourceLimit)?;
        let mut bytes = Vec::new();
        for value in &definitions {
            bytes.extend((value.len() as u32).to_be_bytes());
            bytes.extend(value);
        }
        m.retain(
            &resources_v2::retained_key("definitions:", &bytes),
            definitions.iter().map(|v| v.len() as u64 + 16).sum(),
        )
        .map_err(|_| RouteError::ResourceLimit)?;
    }
    Ok(Some(ObservedRoute {
        width,
        sector,
        mapping,
        package,
        definitions,
        commitments,
    }))
}
fn route_bytes(
    matrix: &ObsMatrix,
    width: usize,
    sector: u8,
    count: usize,
) -> Result<Option<Vec<u8>>> {
    if count > 30784 || count * 8 > width * (matrix.side - width) {
        return Ok(None);
    }
    let mut raw = vec![0; count];
    for bit in 0..count * 8 {
        let (row, col) = crate::sector_cell_at(matrix.side, width, sector, bit)
            .map_err(|_| RouteError::Observation)?;
        match matrix.values[row * matrix.side + col] {
            0 => {}
            1 => raw[bit / 8] |= 1 << (7 - bit % 8),
            2 => return Ok(None),
            _ => return Err(RouteError::Observation),
        }
    }
    Ok(Some(raw))
}
pub(crate) fn discover_route_at(
    matrix: &ObsMatrix,
    width: usize,
    sector: u8,
    resource: &mut ResourceProjection,
    adapter: &mut ReferenceLedger,
) -> Result<Option<ObservedRoute>> {
    let Some(head) = route_bytes(matrix, width, sector, 64)? else {
        return Ok(None);
    };
    if u16_at(&head, 40) != Some(2) {
        return Ok(None);
    }
    let Some(length) = u32_at(&head, 48) else {
        return Ok(None);
    };
    if length > 30720 || (64 + length as usize) * 8 > width * (matrix.side - width) {
        return Ok(None);
    }
    adapter
        .event(
            Kernel::ShellRead,
            8 * (64 + u64::from(length)),
            64 + u64::from(length),
        )
        .map_err(|_| RouteError::ResourceLimit)?;
    let Some(raw) = route_bytes(matrix, width, sector, 64 + length as usize)? else {
        return Ok(None);
    };
    adapter
        .retain("route:prefix", raw.len() as u64)
        .map_err(|_| RouteError::ResourceLimit)?;
    admit_route_prefix_mode(
        &raw,
        matrix.side as u16,
        width as u16,
        sector,
        resource,
        Some(adapter),
    )
}

fn expanded_frames(raw: &[u8]) -> Option<BTreeMap<(u8, u16), Vec<u8>>> {
    if raw.len() < 64 || raw.len() > 1048576 {
        return None;
    }
    let mut cursor = 64usize;
    let mut rows = BTreeMap::new();
    for _ in 0..u16_at(raw, 18)? {
        let end = cursor
            .checked_add(16)?
            .checked_add(u32_at(raw, cursor + 12)? as usize)?;
        let row = raw.get(cursor..end)?;
        rows.insert((0, u16_at(row, 0)?), row.to_vec());
        cursor = end;
    }
    for _ in 0..u16_at(raw, 16)? {
        let end = cursor.checked_add(u32_at(raw, cursor + 28)? as usize)?;
        let row = raw.get(cursor..end)?;
        rows.insert((1, u16_at(row, 0)?), row.to_vec());
        cursor = end;
    }
    (cursor == raw.len()).then_some(rows)
}
pub(crate) fn mapping_refines(package: &RecipePackageV1) -> bool {
    static EXPECTED: std::sync::OnceLock<Option<Vec<u8>>> = std::sync::OnceLock::new();
    let expected = EXPECTED.get_or_init(|| {
        let neutral = crate::body_recipe_v1::build_revision_recipe_package().ok()?;
        let expanded = crate::recipe_wire_v1::expand_recipe_package_v1(&neutral, 8).ok()?;
        expanded_frames(&expanded)?.remove(&(1, 109))
    });
    let Some(raw) = crate::recipe_wire_v1::expand_recipe_package_v1(&package.encoded, 8).ok()
    else {
        return false;
    };
    let Some(mut frames) = expanded_frames(&raw) else {
        return false;
    };
    expected.is_some() && frames.remove(&(1, 109)).as_ref() == expected.as_ref()
}
pub(crate) fn body_refines(package: &RecipePackageV1) -> bool {
    static EXPECTED: std::sync::OnceLock<Option<BTreeMap<(u8, u16), Vec<u8>>>> =
        std::sync::OnceLock::new();
    let expected = EXPECTED
        .get_or_init(|| expanded_frames(&crate::body_recipe_v1::build_body_recipe_package().ok()?));
    let Some(raw) = crate::recipe_wire_v1::expand_recipe_package_v1(&package.encoded, 8).ok()
    else {
        return false;
    };
    let Some(observed) = expanded_frames(&raw) else {
        return false;
    };
    let Some(expected) = expected else {
        return false;
    };
    [(0, 3), (0, 4), (0, 5), (1, 201), (1, 202)]
        .iter()
        .all(|key| observed.get(key).is_some() && observed.get(key) == expected.get(key))
}
/// Complete fixed-interface native projection used only for the refined body
/// closure. It mirrors STATUS16 and suppresses every output on rejection.
pub(crate) fn native_body_output(buffer: &[u8], length: u16) -> Vec<u8> {
    if buffer.len() != 16384 || usize::from(length) > buffer.len() {
        return vec![0, 3];
    }
    let Ok(body) = crate::body_codec_v1::decode_lzss(&buffer[..usize::from(length)]) else {
        return vec![0, 3];
    };
    let mut out = vec![0, 0];
    out.extend((body.len() as u16).to_be_bytes());
    out.extend(body);
    out.resize(16388, 0);
    out
}
/// Explicit finite support for the stated body program refinement. This runs
/// the generic VM, including the maximum decoded body; no native callback is
/// substituted into that VM. Construction evidence is not acquisition evidence.
pub fn verify_body_refinement() -> Result<()> {
    let compact = crate::body_recipe_v1::build_revision_recipe_package()
        .map_err(|_| RouteError::Observation)?;
    let package = decode_recipe_package_v1(&compact, 8).map_err(|_| RouteError::Observation)?;
    if !body_refines(&package) {
        return Err(RouteError::Observation);
    }
    let max = crate::body_codec_v1::encode_lzss(&vec![b'A'; 16384])
        .map_err(|_| RouteError::Observation)?;
    let mut vectors = vec![
        vec![3, 0, 8, 0, b'1', b'2', b'3', b'4', b'5', b'6', b'7', b'8'],
        vec![3, 0, 8, 0x40, b'A', 0, 4],
        vec![3, 0, 3, 0x80, 0],
        vec![3, 0, 3, 0x80, 0, 0],
        vec![3, 0, 1, 1, b'A'],
        vec![3, 0, 1, 0, b'A', 0],
        vec![2, 0, 0],
        vec![3, 64, 1],
        vec![3, 0, 0],
    ];
    vectors.push(max);
    for prefix in vectors {
        let length = prefix.len() as u16;
        let mut buffer = vec![0xa5; 16384];
        buffer[..prefix.len()].copy_from_slice(&prefix);
        let mut input = buffer.clone();
        input.extend(length.to_be_bytes());
        let observed = evaluate_serialized_recipe_v1(&package, 202, &input)
            .map_err(|_| RouteError::Observation)?;
        if observed != native_body_output(&buffer, length) {
            return Err(RouteError::Observation);
        }
    }
    for length in [2u16, 16385] {
        let buffer = vec![0; 16384];
        let mut input = buffer.clone();
        input.extend(length.to_be_bytes());
        let observed = evaluate_serialized_recipe_v1(&package, 202, &input)
            .map_err(|_| RouteError::Observation)?;
        if observed != native_body_output(&buffer, length) {
            return Err(RouteError::Observation);
        }
    }
    Ok(())
}

#[cfg(test)]
mod refinement_tests {
    use super::*;
    #[test]
    fn full_body_refinement_covers_literal_overlap_padding_failures_and_maximum() {
        verify_body_refinement().unwrap();
    }
    #[test]
    fn unrelated_programs_do_not_replace_exact_transitive_body_and_mapping_comparison() {
        let compact = crate::body_recipe_v1::build_revision_recipe_package().unwrap();
        let package = decode_recipe_package_v1(&compact, 8).unwrap();
        assert!(mapping_refines(&package));
        assert!(body_refines(&package));
        let mut forged = package.clone();
        forged.encoded[64 + 16] ^= 1;
        assert!(!body_refines(&forged));
        // Even a mutable diagnostic cache never changes the compared program.
        let mut forged = package;
        forged.logical.profile_version = 7;
        assert!(body_refines(&forged));
    }
}

fn closure(
    frames: &BTreeMap<(u8, u16), Vec<u8>>,
    roots: &[u16],
) -> Option<BTreeMap<(u8, u16), Vec<u8>>> {
    let mut result = BTreeMap::new();
    let mut pending = roots.to_vec();
    while let Some(id) = pending.pop() {
        if result.contains_key(&(1, id)) {
            continue;
        }
        if result.len() > 4352 {
            return None;
        }
        let frame = frames.get(&(1, id))?;
        let front = 32 + 12 * (usize::from(u16_at(frame, 4)?) + usize::from(u16_at(frame, 6)?));
        let nodes = frame.get(front..)?;
        if nodes.len() % 32 != 0 {
            return None;
        }
        for node in nodes.chunks_exact(32) {
            let auxiliary = u16_at(node, 18)?;
            match node[2] {
                2 => {
                    result.insert((0, auxiliary), frames.get(&(0, auxiliary))?.clone());
                }
                22 => {
                    if !result.contains_key(&(1, auxiliary)) {
                        pending.push(auxiliary);
                    }
                }
                _ => {}
            }
        }
        result.insert((1, id), frame.clone());
    }
    Some(result)
}
fn transport_refines_and_body_interface(package: &RecipePackageV1) -> bool {
    static EXPECTED: std::sync::OnceLock<Option<BTreeMap<(u8, u16), Vec<u8>>>> =
        std::sync::OnceLock::new();
    let expected = EXPECTED.get_or_init(|| {
        let raw = crate::candidate_recipe::build_r3_recipe_package().ok()?;
        closure(&expanded_frames(&raw)?, &[30, 113])
    });
    let Some(raw) = crate::recipe_wire_v1::expand_recipe_package_v1(&package.encoded, 8).ok()
    else {
        return false;
    };
    let Some(frames) = expanded_frames(&raw) else {
        return false;
    };
    if expected.is_none() || closure(&frames, &[30, 113]).as_ref() != expected.as_ref() {
        return false;
    }
    let Some(body) = frames.get(&(1, 202)) else {
        return false;
    };
    if u16_at(body, 4) != Some(2) || u16_at(body, 6) != Some(3) {
        return false;
    }
    for (index, (kind, width)) in [(3, 16384), (0, 16), (5, 16), (0, 16), (3, 16384)]
        .into_iter()
        .enumerate()
    {
        let at = 32 + 12 * index;
        if body.get(at + 2) != Some(&kind) || u32_at(body, at + 4) != Some(width) {
            return false;
        }
    }
    true
}

#[cfg(test)]
mod substituted_program_tests {
    use super::*;
    #[test]
    fn valid_replacement_transport_and_mapping_programs_reject_refinement() {
        let original = crate::body_recipe_v1::build_revision_recipe_package().unwrap();
        for id in [30, 113, 109] {
            let mut expanded =
                crate::recipe_wire_v1::expand_recipe_package_v1(&original, 8).unwrap();
            let mut cursor = 64usize;
            for _ in 0..u16_at(&expanded, 18).unwrap() {
                cursor += 16 + u32_at(&expanded, cursor + 12).unwrap() as usize;
            }
            while u16_at(&expanded, cursor) != Some(id) {
                cursor += u32_at(&expanded, cursor + 28).unwrap() as usize;
            }
            let front = cursor
                + 32
                + 12 * (usize::from(u16_at(&expanded, cursor + 4).unwrap())
                    + usize::from(u16_at(&expanded, cursor + 6).unwrap()));
            let end = cursor + u32_at(&expanded, cursor + 28).unwrap() as usize;
            let node = (front..end)
                .step_by(32)
                .find(|at| expanded[*at + 2] == 24)
                .unwrap();
            expanded[node + 2] = 25;
            expanded[node + 24..node + 32].copy_from_slice(&4u64.to_be_bytes());
            let compact = crate::recipe_wire_v1::encode_recipe_package_v1(&expanded, 8).unwrap();
            let changed = decode_recipe_package_v1(&compact, 8).unwrap();
            if id == 109 {
                assert!(!mapping_refines(&changed));
                assert!(transport_refines_and_body_interface(&changed));
            } else {
                assert!(!transport_refines_and_body_interface(&changed));
                assert!(mapping_refines(&changed));
            }
            assert!(
                body_refines(&changed),
                "unrelated program {id} must not alter body closure equality"
            );
        }
    }
}
