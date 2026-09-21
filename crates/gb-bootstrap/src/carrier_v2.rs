//! Independent bounded construction of the unpromoted profile-8 carrier.
//! Historical carrier admission and the 512-KiB physical ceiling are unchanged.
use crate::carrier::{CarrierError, LogicalSection};
use crate::mapping_v2::{self, Mapping};
use crate::{
    CHECK_CRC32C, CLOSURE_M2_ALL_ONLY, CLOSURE_M2_REQUIRED, SECTION_CAPACITY_PROBE,
    SECTION_CONTENT_BODY, SECTION_INVENTORY, SECTION_LOAD_PROBE, SECTION_RESERVE_PROBE,
    SECTION_TIER_FRAME,
};
use crate::{FragmentWitness, Inventory, InventoryEntry, RecoveryQuality, TierFrame};
use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
use gb_slice::{Closure, SliceCompilation};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
type Result<T> = std::result::Result<T, CarrierError>;
const MAX_PAYLOAD: usize = 16384;
const MAX_CELLS: usize = 2048 * 2048;
fn require(ok: bool) -> Result<()> {
    if ok {
        Ok(())
    } else {
        Err(CarrierError::OwnerIdentity)
    }
}
fn u16_at(raw: &[u8], at: usize) -> Result<u16> {
    Ok(u16::from_be_bytes(
        raw.get(at..at + 2)
            .ok_or(CarrierError::Section)?
            .try_into()
            .map_err(|_| CarrierError::Section)?,
    ))
}
fn u32_at(raw: &[u8], at: usize) -> Result<u32> {
    Ok(u32::from_be_bytes(
        raw.get(at..at + 4)
            .ok_or(CarrierError::Section)?
            .try_into()
            .map_err(|_| CarrierError::Section)?,
    ))
}
fn object(v: &V) -> Result<&BTreeMap<String, V>> {
    if let V::Object(v) = v {
        Ok(v)
    } else {
        Err(CarrierError::ManifestShape)
    }
}
fn array(v: &V) -> Result<&[V]> {
    if let V::Array(v) = v {
        Ok(v)
    } else {
        Err(CarrierError::ManifestShape)
    }
}
fn number(v: &V) -> Result<u64> {
    if let V::U64(v) = v {
        Ok(*v)
    } else {
        Err(CarrierError::ManifestShape)
    }
}
fn text(v: &V) -> Result<&str> {
    if let V::String(v) = v {
        Ok(v)
    } else {
        Err(CarrierError::ManifestShape)
    }
}
fn field<'a>(v: &'a BTreeMap<String, V>, key: &str) -> Result<&'a V> {
    v.get(key).ok_or(CarrierError::ManifestShape)
}
fn names(v: &V, wanted: &[&str]) -> Result<()> {
    let actual = array(v)?;
    require(actual.len() == wanted.len())?;
    for (a, b) in actual.iter().zip(wanted) {
        require(text(a)? == *b)?;
    }
    Ok(())
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Capacity {
    sections: Vec<LogicalSection>,
    uncompressed_body_bytes: u64,
    stored_body_bytes: u64,
    future_authoring_bytes: u64,
    reserve_bytes: u64,
    capacity_probe_count: usize,
}
impl Capacity {
    pub fn future_authoring_bytes(&self) -> u64 {
        self.future_authoring_bytes
    }
    pub fn reserve_bytes(&self) -> u64 {
        self.reserve_bytes
    }
    pub fn body_count(&self) -> usize {
        self.sections
            .iter()
            .filter(|s| s.section_type == SECTION_CONTENT_BODY)
            .count()
    }
    pub fn capacity_probe_count(&self) -> usize {
        self.capacity_probe_count
    }
    pub fn uncompressed_body_bytes(&self) -> u64 {
        self.uncompressed_body_bytes
    }
    pub fn stored_body_bytes(&self) -> u64 {
        self.stored_body_bytes
    }
}

fn neutral_manifest() -> Result<Vec<u8>> {
    let historical = gb_slice::compile_slice_v0(gb_slice::SliceInputs {
        declaration: include_bytes!("../../../studies/m2/slice-v0.json"),
        content_fixture: include_bytes!("../../../conformance/content-v0.json"),
        chess_fixture: include_bytes!("../../../conformance/chess-v0.json"),
        game_set: include_bytes!("../../../reports/game-set-v0.bin"),
        content_spec: include_bytes!("../../../spec/content-v0.md"),
        constants: include_bytes!("../../../spec/constants-v0.toml"),
        curriculum: include_bytes!("../../../spec/curriculum-v0.toml"),
    })
    .map_err(|_| CarrierError::OwnerIdentity)?;
    let raw = include_bytes!("../../../spec/profile-policy-v0.toml");
    let policy =
        crate::policy::load_profile_policy(raw).map_err(|_| CarrierError::OwnerIdentity)?;
    Ok(crate::carrier::render_semantic_envelope(
        &policy,
        raw,
        &historical,
        include_bytes!("../../../spec/curriculum-v0.toml"),
    )?
    .canonical_bytes()
    .to_vec())
}

fn capacity_rows(raw: &[u8]) -> Result<Vec<(u64, u8)>> {
    require(raw.len() <= 1048576)?;
    let value = validate_canonical_manifest(raw).map_err(|_| CarrierError::ManifestShape)?;
    let root = object(&value)?;
    let keys = [
        "schema",
        "slice_semantic_sha256",
        "prototype_row_fields",
        "prototype_rows",
        "real_section_row_fields",
        "real_section_rows",
        "tier_frame_row_fields",
        "tier_frame_rows",
        "bucket_row_fields",
        "bucket_rows",
        "capacity_section_row_fields",
        "capacity_section_rows",
        "slot_row_fields",
        "slot_rows",
        "totals",
    ];
    require(root.len() == keys.len() && keys.iter().all(|key| root.contains_key(*key)))?;
    require(text(field(root, "schema")?)? == "golden-board.m2-semantic-envelope/v0")?;
    names(
        field(root, "bucket_row_fields")?,
        &[
            "bucket_id",
            "tier",
            "copy_class",
            "logical_payload_bytes",
            "slot_count",
            "section_count",
        ],
    )?;
    names(
        field(root, "capacity_section_row_fields")?,
        &[
            "section_id",
            "bucket_id",
            "section_ordinal",
            "tier",
            "copy_class",
            "first_slot_ordinal",
            "slot_count",
            "logical_payload_bytes",
        ],
    )?;
    let buckets = array(field(root, "bucket_rows")?)?;
    let rows = array(field(root, "capacity_section_rows")?)?;
    require(!buckets.is_empty() && buckets.len() <= 4096 && rows.len() <= 4096)?;
    let mut result = Vec::new();
    let mut index = 0;
    let mut total = 0;
    let mut slots = 0;
    let mut ids = BTreeSet::new();
    for bucket in buckets {
        let b = array(bucket)?;
        require(b.len() == 6)?;
        let id = text(&b[0])?;
        let tier = text(&b[1])?;
        let class = text(&b[2])?;
        require(ids.insert(id) && id.len() <= 256)?;
        let factor = match tier {
            "core0" | "core1" | "core2" => {
                require(class == "replicated-m2")?;
                2
            }
            "core3" | "core4" => {
                require(class == "nonreplicated-m2")?;
                1
            }
            _ => return Err(CarrierError::ManifestShape),
        };
        let count = number(&b[5])?;
        require(count <= 4096 && number(&b[3])? <= 1048576 && number(&b[4])? <= 65536)?;
        let mut size = 0;
        let mut first_slot = 0;
        for ordinal in 0..count {
            let row = array(rows.get(index).ok_or(CarrierError::ManifestShape)?)?;
            require(row.len() == 8)?;
            require(
                number(&row[0])? == 211 + index as u64
                    && text(&row[1])? == id
                    && number(&row[2])? == ordinal
                    && text(&row[3])? == tier
                    && text(&row[4])? == class
                    && number(&row[5])? == first_slot,
            )?;
            let slot_count = number(&row[6])?;
            let length = number(&row[7])?;
            require(slot_count <= 65536 && length <= MAX_PAYLOAD as u64)?;
            first_slot += slot_count;
            size += length;
            if length != 0 {
                result.push((length, factor));
            }
            index += 1;
        }
        require(size == number(&b[3])? && first_slot == number(&b[4])?)?;
        total += size;
        slots += first_slot;
    }
    require(index == rows.len())?;
    let totals = object(field(root, "totals")?)?;
    let total_keys = [
        "prototype_count",
        "real_section_count",
        "tier_frame_count",
        "bucket_count",
        "capacity_section_count",
        "slot_count",
        "authoring_payload_bytes",
    ];
    require(
        totals.len() == total_keys.len() && total_keys.iter().all(|key| totals.contains_key(*key)),
    )?;
    for key in total_keys {
        number(field(totals, key)?)?;
    }
    require(
        number(field(totals, "bucket_count")?)? == buckets.len() as u64
            && number(field(totals, "capacity_section_count")?)? == rows.len() as u64
            && number(field(totals, "slot_count")?)? == slots
            && number(field(totals, "authoring_payload_bytes")?)? == total
            && total == 105277,
    )?;
    Ok(result)
}

fn frames(stream: &[u8]) -> Result<BTreeMap<u16, Vec<u8>>> {
    require(stream.len() <= 1048576)?; // Bound the stream before frame indexing.
    gb_content::stream_validation(stream).map_err(|_| CarrierError::Section)?;
    let count = usize::from(u16_at(stream, 2)?);
    let mut cursor = 4;
    let mut result = BTreeMap::new();
    for _ in 0..count {
        let length = u32_at(stream, cursor + 4)? as usize;
        let end = cursor
            .checked_add(8 + length)
            .ok_or(CarrierError::Arithmetic)?;
        let raw = stream.get(cursor..end).ok_or(CarrierError::Section)?;
        let id = u16_at(raw, 0)?;
        require(result.insert(id, raw.to_vec()).is_none())?;
        cursor = end;
    }
    require(cursor == stream.len())?;
    Ok(result)
}
fn section(
    id: u32,
    kind: u16,
    version: u16,
    factor: u8,
    deps: Vec<u32>,
    payload: Vec<u8>,
) -> Result<LogicalSection> {
    require((1..=MAX_PAYLOAD).contains(&payload.len()) && deps.len() <= 4096)?;
    Ok(LogicalSection {
        section_id: id,
        section_type: kind,
        section_version: version,
        closure_class: if [1, 2, 3, 16, 17, 18].contains(&id) {
            CLOSURE_M2_REQUIRED
        } else {
            CLOSURE_M2_ALL_ONLY
        },
        check_id: CHECK_CRC32C,
        copy_count: factor,
        dependencies: deps,
        game_ordinal: if (100..=163).contains(&id) {
            Some((id - 100) as u8)
        } else {
            None
        },
        payload,
    })
}

pub fn derive_capacity(slice: &SliceCompilation) -> Result<Capacity> {
    require(slice.assignments().len() == 78 && slice.tier_roots().len() == 2)?;
    for (stream, projection) in [
        (slice.required_stream(), slice.required_projection()),
        (slice.all_stream(), slice.all_projection()),
    ] {
        require(stream.len() <= 1048576)?;
        let authored =
            gb_content::authoring_from_validated(projection).map_err(|_| CarrierError::Section)?;
        require(
            gb_content::encode_content_v0(&authored).map_err(|_| CarrierError::Section)? == stream,
        )?;
    }
    let all_frames = frames(slice.all_stream())?;
    let mut sections = Vec::new();
    let mut raw_sum = 0;
    let mut stored_sum = 0;
    let expected: Vec<u32> = (16..=18).chain(100..=163).chain(200..=210).collect();
    require(
        slice
            .assignments()
            .iter()
            .map(|a| u32::from(a.section_id()))
            .collect::<Vec<_>>()
            == expected,
    )?;
    for assignment in slice.assignments() {
        let mut body = Vec::new();
        require(
            !assignment.record_ids().is_empty()
                && assignment.record_ids().len() <= 65535
                && assignment.semantic_copy_id() == 0,
        )?;
        for id in assignment.record_ids() {
            let frame = all_frames.get(id).ok_or(CarrierError::Section)?;
            require(body.len() + frame.len() <= MAX_PAYLOAD)?;
            body.extend(frame);
        }
        let id = u32::from(assignment.section_id());
        let required = [16, 17, 18].contains(&id);
        require((assignment.closure() == Closure::Required) == required)?;
        raw_sum += body.len() as u64;
        let (version, stored) =
            crate::body_codec_v1::encode_body(&body).map_err(|_| CarrierError::Section)?;
        stored_sum += stored.len() as u64;
        sections.push(section(
            id,
            SECTION_CONTENT_BODY,
            version,
            if required { 5 } else { 1 },
            vec![],
            stored,
        )?);
    }
    let mut tier_sum = 0;
    for (index, root) in slice.tier_roots().iter().enumerate() {
        let required = index == 0;
        let id = if required { 2 } else { 3 };
        require(
            u32::from(root.section_id()) == id
                && root.semantic_copy_id() == 0
                && (root.closure() == Closure::Required) == required,
        )?;
        let stream = if required {
            slice.required_stream()
        } else {
            slice.all_stream()
        };
        let deps = if required {
            vec![16, 17, 18]
        } else {
            expected.clone()
        };
        let payload = crate::encode_tier_frame(&TierFrame {
            tier_id: index as u8,
            body_section_ids: deps.clone(),
            assembled_stream_byte_length: stream.len() as u32,
            assembled_record_count: u16_at(stream, 2)?,
            root_record_bytes: root.frame().to_vec(),
        })
        .map_err(|_| CarrierError::Section)?;
        tier_sum += payload.len() as u64;
        sections.push(section(id, SECTION_TIER_FRAME, 0, 5, deps, payload)?);
    }
    let needs = capacity_rows(&neutral_manifest()?)?;
    let future = needs.iter().map(|row| row.0).sum::<u64>();
    let capacity_probe_count = needs.len();
    let mut next = 211;
    for (length, factor) in needs {
        sections.push(section(
            next,
            SECTION_CAPACITY_PROBE,
            0,
            factor,
            vec![],
            vec![0; length as usize],
        )?);
        next += 1;
    }
    let reserve = (raw_sum + tier_sum + 16384 + future).div_ceil(19).max(382);
    let mut remaining = reserve;
    while remaining > 0 {
        let length = remaining.min(MAX_PAYLOAD as u64);
        sections.push(section(
            next,
            SECTION_RESERVE_PROBE,
            0,
            2,
            vec![],
            vec![0; length as usize],
        )?);
        remaining -= length;
        next += 1;
    }
    sections.sort_by_key(|s| s.section_id);
    require(
        sections
            .windows(2)
            .all(|p| p[0].section_id < p[1].section_id),
    )?;
    Ok(Capacity {
        sections,
        uncompressed_body_bytes: raw_sum,
        stored_body_bytes: stored_sum,
        future_authoring_bytes: future,
        reserve_bytes: reserve,
        capacity_probe_count,
    })
}

fn fragment_count(s: &LogicalSection) -> u64 {
    (22 + 4 * s.dependencies.len() as u64 + s.payload.len() as u64).div_ceil(157)
}
fn inventory_length(sections: &[LogicalSection], loads: usize) -> Result<usize> {
    let count = 1 + sections.len() + loads;
    let deps = sections.iter().map(|s| s.dependencies.len()).sum::<usize>();
    let length = 8 + 20 * count + 4 * deps;
    require(count <= 4096 && length <= MAX_PAYLOAD)?;
    Ok(length)
}
fn add_inventory(mut sections: Vec<LogicalSection>) -> Result<Vec<LogicalSection>> {
    sections.sort_by_key(|s| s.section_id);
    let length = inventory_length(&sections, 0)?;
    sections.insert(
        0,
        section(1, SECTION_INVENTORY, 2, 5, vec![], vec![0; length])?,
    );
    let entries = sections
        .iter()
        .map(|s| InventoryEntry {
            section_id: s.section_id,
            section_type: s.section_type,
            section_version: s.section_version,
            closure_class: s.closure_class,
            check_id: s.check_id,
            copy_count: 1,
            physical_replica_count: s.copy_count,
            dependencies: s.dependencies.clone(),
            logical_payload_length: s.payload.len() as u32,
            game_ordinal: s.game_ordinal.map(u16::from),
        })
        .collect();
    let raw = crate::bootstrap_v2::encode_inventory(&Inventory {
        inventory_version: 2,
        entries,
    })
    .map_err(|_| CarrierError::Section)?;
    require(raw.len() == length)?;
    sections[0].payload = raw;
    Ok(sections)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SearchFailure {
    RouteFit,
    Mapping,
    LoadFit,
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SearchRow {
    pub side: u16,
    pub shell_width: u16,
    pub accepted: bool,
    pub failure: Option<SearchFailure>,
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Carrier {
    side: u16,
    width: u16,
    units: u64,
    packed: Vec<u8>,
    ledger: Vec<SearchRow>,
    sections: Vec<LogicalSection>,
}
impl Carrier {
    pub fn side(&self) -> u16 {
        self.side
    }
    pub fn shell_width(&self) -> u16 {
        self.width
    }
    pub fn unit_count(&self) -> u64 {
        self.units
    }
    pub fn packed_bytes(&self) -> &[u8] {
        &self.packed
    }
    pub fn search_ledger(&self) -> &[SearchRow] {
        &self.ledger
    }
    pub fn sections(&self) -> &[LogicalSection] {
        &self.sections
    }
}
fn load_allocation(base: &[LogicalSection], q: u64) -> Result<Option<Vec<usize>>> {
    let mandatory = base
        .iter()
        .map(|s| fragment_count(s) * u64::from(s.copy_count))
        .sum::<u64>();
    for count in 0..=4096usize.saturating_sub(base.len() + 1) {
        let length = match inventory_length(base, count) {
            Ok(v) => v,
            Err(_) => break,
        };
        let fixed = mandatory + 5 * ((22 + length as u64).div_ceil(157));
        if fixed > q {
            continue;
        }
        let residual = q - fixed;
        if count == 0 {
            if residual == 0 {
                return Ok(Some(vec![]));
            }
            continue;
        }
        if residual < count as u64 || residual > 105 * count as u64 {
            continue;
        }
        let mut left = residual;
        let mut lengths = Vec::new();
        for index in 0..count {
            let remaining = count - index - 1;
            let fragments = 105.min(left - remaining as u64);
            let payload = 16384.min(157 * fragments - 22) as usize;
            require((22 + payload as u64).div_ceil(157) == fragments && payload > 0)?;
            lengths.push(payload);
            left -= fragments;
        }
        require(left == 0)?;
        return Ok(Some(lengths));
    }
    Ok(None)
}
fn choose_geometry(
    capacity: &Capacity,
    prefixes: &[Vec<u8>; 4],
) -> Result<(Mapping, Vec<usize>, Vec<SearchRow>)> {
    let total = prefixes.iter().map(|p| p.len() as u64 * 8).sum::<u64>();
    let extra = total.div_ceil(20).max(1024) - 1024;
    let mut ledger = Vec::new();
    for side in (64..=2048u16).step_by(8) {
        for width in (8..=128.min((side - 8) / 2)).step_by(8) {
            let cells = u64::from(width) * u64::from(side - width);
            if prefixes.iter().enumerate().any(|(sector, p)| {
                p.len() as u64 * 8 + 256 + extra / 4 + u64::from((sector as u64) < extra % 4)
                    > cells
            }) {
                ledger.push(SearchRow {
                    side,
                    shell_width: width,
                    accepted: false,
                    failure: Some(SearchFailure::RouteFit),
                });
                continue;
            }
            let mapping = match mapping_v2::derive(side, width) {
                Ok(v) => v,
                Err(_) => {
                    ledger.push(SearchRow {
                        side,
                        shell_width: width,
                        accepted: false,
                        failure: Some(SearchFailure::Mapping),
                    });
                    continue;
                }
            };
            if let Some(loads) = load_allocation(&capacity.sections, mapping.unit_slot_count())? {
                ledger.push(SearchRow {
                    side,
                    shell_width: width,
                    accepted: true,
                    failure: None,
                });
                return Ok((mapping, loads, ledger));
            }
            ledger.push(SearchRow {
                side,
                shell_width: width,
                accepted: false,
                failure: Some(SearchFailure::LoadFit),
            });
        }
    }
    Err(CarrierError::Geometry)
}
fn fill_sections(sections: &mut [LogicalSection], seed: &[u8; 32], pad: usize) -> Result<Vec<u8>> {
    let bytes = sections
        .iter()
        .filter(|s| s.section_type >= SECTION_CAPACITY_PROBE)
        .map(|s| s.payload.len())
        .sum::<usize>();
    let bits = crate::carrier::fill_bits(seed, bytes * 8 + pad)?;
    let mut cursor = 0;
    for s in sections
        .iter_mut()
        .filter(|s| s.section_type >= SECTION_CAPACITY_PROBE)
    {
        for byte in &mut s.payload {
            *byte = 0;
            for _ in 0..8 {
                *byte = (*byte << 1) | bits[cursor];
                cursor += 1;
            }
        }
    }
    Ok(bits[cursor..].to_vec())
}
fn absolute(mapping: &Mapping, physical: u64) -> usize {
    let i = u64::from(mapping.interior_side());
    let w = u64::from(mapping.shell_width());
    ((physical / i + w) * u64::from(mapping.side()) + physical % i + w) as usize
}
fn put(cells: &mut [u8], index: usize, bit: u8) -> Result<()> {
    let cell = cells.get_mut(index).ok_or(CarrierError::Ownership)?;
    require(*cell == 2 && bit <= 1)?;
    *cell = bit;
    Ok(())
}
fn pack(cells: &[u8]) -> Result<Vec<u8>> {
    require(cells.len() <= MAX_CELLS && cells.len() % 8 == 0 && cells.iter().all(|v| *v <= 1))?;
    let mut raw = Vec::with_capacity(4 + cells.len() / 8);
    raw.extend((cells.len() as u32).to_be_bytes());
    for byte in cells.chunks_exact(8) {
        raw.push(byte.iter().fold(0, |value, bit| (value << 1) | bit));
    }
    Ok(raw)
}

pub fn build_carrier(slice: &SliceCompilation) -> Result<Carrier> {
    let capacity = derive_capacity(slice)?;
    let prefixes = crate::route_v2::build_route_prefixes(slice)?;
    let (mapping, loads, ledger) = choose_geometry(&capacity, &prefixes)?;
    let mut sections = capacity.sections;
    let mut next = sections.last().ok_or(CarrierError::Section)?.section_id + 1;
    for length in loads {
        sections.push(section(
            next,
            SECTION_LOAD_PROBE,
            0,
            1,
            vec![],
            vec![0; length],
        )?);
        next += 1;
    }
    let seed: [u8; 32] = Sha256::digest(slice.all_stream()).into();
    let pad = fill_sections(&mut sections, &seed, mapping.fixed_pad_cells() as usize)?;
    let sections = add_inventory(sections)?;
    let mut cells = vec![2; usize::from(mapping.side()).pow(2)];
    let mut unit = 0;
    for s in &sections {
        let envelope = s.envelope()?;
        let fragments = crate::fragment_envelope(
            8,
            s.section_id,
            0,
            s.section_type,
            s.section_version,
            &envelope,
        )
        .map_err(|_| CarrierError::Section)?;
        for common in fragments {
            let encoded = crate::candidate::encode_eh_unit(&common);
            for _ in 0..s.copy_count {
                unit += 1;
                for bit in 0..1728u16 {
                    let physical = mapping.forward(unit, bit)?;
                    let value = (encoded[usize::from(bit) / 8] >> (7 - bit % 8)) & 1;
                    put(&mut cells, absolute(&mapping, physical), value)?;
                }
            }
        }
    }
    require(unit == mapping.unit_slot_count())?;
    for (index, bit) in pad.into_iter().enumerate() {
        let logical = unit * 1728 + index as u64;
        let physical =
            (mapping.cell_multiplier() * logical + mapping.cell_offset()) % mapping.population();
        require(mapping.inverse(physical)? == (1, 0, 0))?;
        put(&mut cells, absolute(&mapping, physical), bit)?;
    }
    let routes = crate::route_v2::build_route_images(slice, mapping.side(), mapping.shell_width())?;
    for sector in &routes.sectors {
        for (index, bit) in sector.bits.iter().enumerate() {
            let (row, col) = crate::sector_cell_at(
                usize::from(mapping.side()),
                usize::from(mapping.shell_width()),
                sector.sector_id,
                index,
            )
            .map_err(|_| CarrierError::Geometry)?;
            put(
                &mut cells,
                usize::from(row) * usize::from(mapping.side()) + usize::from(col),
                *bit,
            )?;
        }
    }
    require(cells.iter().all(|cell| *cell <= 1))?;
    Ok(Carrier {
        side: mapping.side(),
        width: mapping.shell_width(),
        units: unit,
        packed: pack(&cells)?,
        ledger,
        sections,
    })
}

fn unpack(raw: &[u8], width: u16) -> Result<(Mapping, Vec<u8>)> {
    require(raw.len() >= 4 && raw.len() <= 4 + MAX_CELLS / 8)?;
    let count = u32_at(raw, 0)? as usize;
    require(
        count >= 64 * 64 && count <= MAX_CELLS && count % 8 == 0 && raw.len() == 4 + count / 8,
    )?;
    let side = (64..=2048u16)
        .step_by(8)
        .find(|side| usize::from(*side).pow(2) == count)
        .ok_or(CarrierError::Geometry)?;
    let mapping = mapping_v2::derive(side, width)?;
    let cells = raw[4..]
        .iter()
        .flat_map(|byte| (0..8).rev().map(move |bit| (byte >> bit) & 1))
        .collect();
    Ok((mapping, cells))
}
/// Strict clean extraction from actual cells. Every EH unit, physical replica,
/// common identity, envelope and inventory is checked afresh. This is not a
/// damaged-carrier classifier and cannot substitute for damage evidence.
pub fn recover_clean_matrix(
    raw: &[u8],
    width: u16,
) -> Result<crate::bootstrap_v2::ContentRecovery> {
    let (mapping, cells) = unpack(raw, width)?;
    let mut groups: BTreeMap<u32, Vec<FragmentWitness>> = BTreeMap::new();
    let mut observed = Vec::new();
    for unit in 1..=mapping.unit_slot_count() {
        let mut encoded = [0u8; 216];
        for bit in 0..1728u16 {
            let value = cells[absolute(&mapping, mapping.forward(unit, bit)?)];
            encoded[usize::from(bit) / 8] |= value << (7 - bit % 8);
        }
        let decoded = crate::candidate::decode_eh_unit(
            &crate::candidate::EhObservation {
                encoded,
                erasures: vec![],
            },
            8,
        )
        .map_err(|_| CarrierError::Reconstruction)?;
        require(crate::candidate::encode_eh_unit(&decoded.common) == encoded)?;
        let common = crate::decode_common_block(&decoded.common, 8)
            .map_err(|_| CarrierError::Reconstruction)?;
        require(common.semantic_copy_id == 0)?;
        observed.push((common.section_id, common.fragment_index, decoded.common));
        groups
            .entry(common.section_id)
            .or_default()
            .push(FragmentWitness {
                raw_block: decoded.common,
                quality: RecoveryQuality::Verified,
            });
    }
    let mut envelopes = BTreeMap::new();
    for (id, witnesses) in groups {
        let mut unique = BTreeMap::new();
        for witness in witnesses {
            let common = crate::decode_common_block(&witness.raw_block, 8)
                .map_err(|_| CarrierError::Reconstruction)?;
            if let Some(old) = unique.insert(common.fragment_index, witness.clone()) {
                require(old.raw_block == witness.raw_block)?;
            }
        }
        let section = crate::assemble_semantic_copy(&unique.into_values().collect::<Vec<_>>(), 8)
            .map_err(|_| CarrierError::Reconstruction)?;
        envelopes.insert(id, section.envelope);
    }
    let inventory_envelope =
        crate::decode_section(envelopes.get(&1).ok_or(CarrierError::Reconstruction)?)
            .map_err(|_| CarrierError::Reconstruction)?;
    let inventory = crate::bootstrap_v2::decode_inventory(&inventory_envelope.payload)
        .map_err(|_| CarrierError::Reconstruction)?;
    require(inventory.entries.len() == envelopes.len())?;
    let recovery = crate::bootstrap_v2::recover_content(&envelopes)
        .map_err(|_| CarrierError::Reconstruction)?;
    require(
        recovery.rejected_section_ids.is_empty()
            && recovery.checked_section_ids.len() == inventory.entries.len()
            && recovery.required_bytes.is_some()
            && recovery.all_bytes.is_some(),
    )?;
    let mut expected = Vec::new();
    let mut probe_bytes = Vec::new();
    for entry in &inventory.entries {
        let envelope = envelopes
            .get(&entry.section_id)
            .ok_or(CarrierError::Reconstruction)?;
        let decoded = crate::decode_section(envelope).map_err(|_| CarrierError::Reconstruction)?;
        if entry.section_type >= SECTION_CAPACITY_PROBE {
            probe_bytes.extend(decoded.payload);
        }
        let fragments = crate::fragment_envelope(
            8,
            entry.section_id,
            0,
            entry.section_type,
            entry.section_version,
            envelope,
        )
        .map_err(|_| CarrierError::Reconstruction)?;
        require(
            expected.len() + fragments.len() * usize::from(entry.physical_replica_count)
                <= mapping.unit_slot_count() as usize,
        )?;
        for (index, common) in fragments.into_iter().enumerate() {
            for _ in 0..entry.physical_replica_count {
                expected.push((entry.section_id, index as u16, common));
            }
        }
    }
    require(expected == observed)?;
    let seed: [u8; 32] = Sha256::digest(
        recovery
            .all_bytes
            .as_ref()
            .ok_or(CarrierError::Reconstruction)?,
    )
    .into();
    let fill = crate::carrier::fill_bits(
        &seed,
        probe_bytes.len() * 8 + mapping.fixed_pad_cells() as usize,
    )?;
    for (index, byte) in probe_bytes.iter().enumerate() {
        for bit in 0..8 {
            require(((byte >> (7 - bit)) & 1) == fill[index * 8 + bit])?;
        }
    }
    for index in 0..mapping.fixed_pad_cells() {
        let logical = mapping.unit_slot_count() * 1728 + index;
        let physical =
            (mapping.cell_multiplier() * logical + mapping.cell_offset()) % mapping.population();
        require(
            cells[absolute(&mapping, physical)] == fill[probe_bytes.len() * 8 + index as usize],
        )?;
    }
    Ok(recovery)
}

/// Source conformance supplements matrix recovery with exact complete shell
/// bits and decoded source identity. No saved section dictionary feeds recovery.
pub fn verify_clean_carrier(slice: &SliceCompilation, raw: &[u8], width: u16) -> Result<()> {
    let recovery = recover_clean_matrix(raw, width)?;
    require(
        recovery.required_bytes.as_deref() == Some(slice.required_stream())
            && recovery.all_bytes.as_deref() == Some(slice.all_stream()),
    )?;
    let (mapping, cells) = unpack(raw, width)?;
    let routes = crate::route_v2::build_route_images(slice, mapping.side(), width)?;
    for sector in &routes.sectors {
        for (index, bit) in sector.bits.iter().enumerate() {
            let (row, col) = crate::sector_cell_at(
                usize::from(mapping.side()),
                usize::from(width),
                sector.sector_id,
                index,
            )
            .map_err(|_| CarrierError::Geometry)?;
            require(
                cells[usize::from(row) * usize::from(mapping.side()) + usize::from(col)] == *bit,
            )?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn capacity_projection_rejects_unknown_keys_wrong_types_order_and_totals() {
        let raw = neutral_manifest().unwrap();
        let value = validate_canonical_manifest(&raw).unwrap();
        assert_eq!(capacity_rows(&raw).unwrap().len(), 53);
        for case in 0..5 {
            let mut changed = value.clone();
            let V::Object(ref mut root) = changed else {
                panic!()
            };
            match case {
                0 => {
                    root.insert("unexpected".into(), V::U64(1));
                }
                1 | 2 | 3 => {
                    let V::Array(rows) = root.get_mut("capacity_section_rows").unwrap() else {
                        panic!()
                    };
                    let V::Array(row) = &mut rows[0] else {
                        panic!()
                    };
                    row[match case {
                        1 => 0,
                        2 => 7,
                        _ => 6,
                    }] = match case {
                        1 => V::U64(212),
                        2 => V::String("1024".into()),
                        _ => V::U64(65537),
                    };
                }
                _ => {
                    let V::Object(totals) = root.get_mut("totals").unwrap() else {
                        panic!()
                    };
                    totals.insert("authoring_payload_bytes".into(), V::U64(105276));
                }
            }
            let encoded = gb_foundation::serialize_manifest(&changed).unwrap();
            assert!(capacity_rows(&encoded).is_err(), "case={case}");
        }
        assert!(capacity_rows(&vec![b' '; 1048577]).is_err());
    }
    #[test]
    fn load_solver_handles_zero_need_inventory_fragment_growth_and_max_payload() {
        let base = vec![section(16, SECTION_CONTENT_BODY, 0, 5, vec![], vec![0; 1]).unwrap()];
        assert_eq!(load_allocation(&base, 10).unwrap(), Some(vec![]));
        assert_eq!(load_allocation(&base, 9).unwrap(), None);
        assert_eq!(load_allocation(&base, 11).unwrap(), Some(vec![135]));
        assert_eq!(load_allocation(&base, 115).unwrap(), Some(vec![16384]));
        assert_eq!(load_allocation(&base, 116).unwrap(), Some(vec![16384, 135]));
        assert_eq!(load_allocation(&base, 430).unwrap(), Some(vec![16384; 4]));
        assert_eq!(
            load_allocation(&base, 431).unwrap(),
            Some(vec![16384, 16384, 16384, 15678, 135])
        );
        assert!(inventory_length(&base, 4096).is_err());
    }
}
