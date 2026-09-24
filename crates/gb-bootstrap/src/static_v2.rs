//! Independent source-built static projections. These are not promoted results.

use std::collections::{BTreeMap, BTreeSet};

use gb_foundation::{
    ManifestValue as V, identity_hex, serialize_manifest, validate_canonical_manifest,
};
use gb_slice::SliceCompilation;
use sha2::{Digest, Sha256};

use crate::carrier::{CarrierError, CellOwner, ShellOwner};
use crate::carrier_v2::{Carrier, SearchFailure, build_carrier, derive_capacity};
use crate::mapping_v2::{Mapping, derive};
use crate::recipe_wire_v2::{decode_recipe_package_v2, expand_recipe_package_v2};

type Result<T> = std::result::Result<T, CarrierError>;
type Object = BTreeMap<String, V>;
const PROFILE: &str = "eh72-hier-r5-r2-r1-lzss-crc32c-v1";
const MAX_CELLS: usize = 2048 * 2048;

/// Exact neutral/source owners, injectable for malformed-source checks.
#[derive(Clone, Copy)]
pub struct StaticSources<'a> {
    pub inherited_profile_policy: &'a [u8],
    pub profile_policy: &'a [u8],
    pub profile_limits: &'a [u8],
    pub damage_policy: &'a [u8],
    pub curriculum: &'a [u8],
}
impl Default for StaticSources<'static> {
    fn default() -> Self {
        Self {
            inherited_profile_policy: include_bytes!("../../../spec/profile-policy-v0.toml"),
            profile_policy: include_bytes!("../../../spec/profile-policy-v2.toml"),
            profile_limits: include_bytes!("../../../spec/profile-limits-v2.toml"),
            damage_policy: include_bytes!("../../../spec/damage-policy-v2.toml"),
            curriculum: include_bytes!("../../../spec/curriculum-v0.toml"),
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct StaticProjectionV2 {
    documents: BTreeMap<&'static str, Vec<u8>>,
}
impl StaticProjectionV2 {
    pub fn document(&self, name: &str) -> Option<&[u8]> {
        self.documents.get(name).map(Vec::as_slice)
    }
    pub fn documents(&self) -> impl Iterator<Item = (&'static str, &[u8])> {
        self.documents
            .iter()
            .map(|(name, raw)| (*name, raw.as_slice()))
    }
}

fn require(ok: bool) -> Result<()> {
    if ok {
        Ok(())
    } else {
        Err(CarrierError::ManifestShape)
    }
}
fn add(a: u64, b: u64) -> Result<u64> {
    a.checked_add(b).ok_or(CarrierError::Arithmetic)
}
fn mul(a: u64, b: u64) -> Result<u64> {
    a.checked_mul(b).ok_or(CarrierError::Arithmetic)
}
fn sub(a: u64, b: u64) -> Result<u64> {
    a.checked_sub(b).ok_or(CarrierError::Arithmetic)
}
fn sum(values: impl IntoIterator<Item = u64>) -> Result<u64> {
    values.into_iter().try_fold(0, add)
}
fn n(value: impl Into<u64>) -> V {
    V::U64(value.into())
}
fn s(value: impl Into<String>) -> V {
    V::String(value.into())
}
fn a(values: impl IntoIterator<Item = V>) -> V {
    V::Array(values.into_iter().collect())
}
fn o<const N: usize>(rows: [(&str, V); N]) -> V {
    V::Object(
        rows.into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}
fn object(value: &V) -> Result<&Object> {
    if let V::Object(v) = value {
        Ok(v)
    } else {
        Err(CarrierError::ManifestShape)
    }
}
fn array(value: &V) -> Result<&[V]> {
    if let V::Array(v) = value {
        Ok(v)
    } else {
        Err(CarrierError::ManifestShape)
    }
}
fn number(value: &V) -> Result<u64> {
    if let V::U64(v) = value {
        Ok(*v)
    } else {
        Err(CarrierError::ManifestShape)
    }
}
fn text(value: &V) -> Result<&str> {
    if let V::String(v) = value {
        Ok(v)
    } else {
        Err(CarrierError::ManifestShape)
    }
}
fn field<'a>(value: &'a V, name: &str) -> Result<&'a V> {
    object(value)?.get(name).ok_or(CarrierError::ManifestShape)
}
fn digest(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn bytes<const N: usize>(raw: &[u8], at: usize) -> Result<[u8; N]> {
    raw.get(at..at.checked_add(N).ok_or(CarrierError::Arithmetic)?)
        .ok_or(CarrierError::ManifestShape)?
        .try_into()
        .map_err(|_| CarrierError::ManifestShape)
}
fn u16_at(raw: &[u8], at: usize) -> Result<u16> {
    Ok(u16::from_be_bytes(bytes(raw, at)?))
}
fn u32_at(raw: &[u8], at: usize) -> Result<u32> {
    Ok(u32::from_be_bytes(bytes(raw, at)?))
}
fn u64_at(raw: &[u8], at: usize) -> Result<u64> {
    Ok(u64::from_be_bytes(bytes(raw, at)?))
}
fn table(target: &mut Object, name: &str, fields: &str, rows: Vec<V>) {
    target.insert(format!("{name}_fields"), a(fields.split(',').map(s)));
    target.insert(format!("{name}_rows"), V::Array(rows));
}
fn base(schema: &str) -> Object {
    BTreeMap::from([
        ("schema".into(), s(schema)),
        ("profile_id".into(), s(PROFILE)),
    ])
}
fn serialize(value: V) -> Result<Vec<u8>> {
    serialize_manifest(&value).map_err(|_| CarrierError::ManifestShape)
}
fn pack(bits: &[u8]) -> Result<Vec<u8>> {
    require(bits.len() % 8 == 0 && bits.iter().all(|b| *b <= 1))?;
    Ok(bits
        .chunks_exact(8)
        .map(|chunk| chunk.iter().fold(0, |b, bit| b * 2 + bit))
        .collect())
}

fn admit_sources(sources: StaticSources<'_>) -> Result<()> {
    let expected = StaticSources::default();
    for (raw, admitted) in [
        (
            sources.inherited_profile_policy,
            expected.inherited_profile_policy,
        ),
        (sources.profile_policy, expected.profile_policy),
        (sources.profile_limits, expected.profile_limits),
        (sources.damage_policy, expected.damage_policy),
        (sources.curriculum, expected.curriculum),
    ] {
        require(!raw.is_empty() && raw.len() <= 1_048_576 && raw == admitted)?;
        let value: toml::Value =
            toml::from_str(std::str::from_utf8(raw).map_err(|_| CarrierError::OwnerIdentity)?)
                .map_err(|_| CarrierError::OwnerIdentity)?;
        require(value.is_table())?;
    }
    let policy: toml::Value = toml::from_str(
        std::str::from_utf8(sources.profile_policy).map_err(|_| CarrierError::OwnerIdentity)?,
    )
    .map_err(|_| CarrierError::OwnerIdentity)?;
    require(
        policy["candidate"]["id"].as_str() == Some(PROFILE)
            && policy["candidate"]["profile_version"].as_integer() == Some(8)
            && policy["geometry"]["carrier_bytes_max"].as_integer() == Some(524288),
    )
}

fn provenance(slice: &SliceCompilation, source: StaticSources<'_>) -> V {
    o([
        (
            "inherited_profile_policy_sha256",
            s(digest(source.inherited_profile_policy)),
        ),
        ("profile_policy_sha256", s(digest(source.profile_policy))),
        (
            "profile_limits_source_sha256",
            s(digest(source.profile_limits)),
        ),
        ("damage_policy_sha256", s(digest(source.damage_policy))),
        (
            "required_content_sha256",
            s(digest(slice.required_stream())),
        ),
        ("all_content_sha256", s(digest(slice.all_stream()))),
    ])
}

fn neutral(source: StaticSources<'_>) -> Result<V> {
    let prototype = gb_slice::compile_slice_v0(gb_slice::SliceInputs {
        declaration: include_bytes!("../../../studies/m2/slice-v0.json"),
        content_fixture: include_bytes!("../../../conformance/content-v0.json"),
        chess_fixture: include_bytes!("../../../conformance/chess-v0.json"),
        game_set: include_bytes!("../../../reports/game-set-v0.bin"),
        content_spec: include_bytes!("../../../spec/content-v0.md"),
        constants: include_bytes!("../../../spec/constants-v0.toml"),
        curriculum: source.curriculum,
    })
    .map_err(|_| CarrierError::OwnerIdentity)?;
    let policy = crate::policy::load_profile_policy(source.inherited_profile_policy)
        .map_err(|_| CarrierError::OwnerIdentity)?;
    let manifest = crate::carrier::render_semantic_envelope(
        &policy,
        source.inherited_profile_policy,
        &prototype,
        source.curriculum,
    )?;
    validate_canonical_manifest(manifest.canonical_bytes()).map_err(|_| CarrierError::ManifestShape)
}

fn protection_class(tier: &V, inherited: &V) -> Result<V> {
    let (prior, current) = match text(tier)? {
        "core0" | "core1" | "core2" => ("replicated-m2", "replicated-core0-2"),
        "core3" | "core4" => ("nonreplicated-m2", "nonreplicated-core3-4"),
        _ => return Err(CarrierError::ManifestShape),
    };
    require(text(inherited)? == prior)?;
    Ok(s(current))
}

fn semantic(
    slice: &SliceCompilation,
    carrier: &Carrier,
    source: StaticSources<'_>,
    ids: &V,
) -> Result<(V, BTreeMap<u32, String>, BTreeMap<u32, u64>)> {
    let neutral = neutral(source)?;
    let capacity = derive_capacity(slice)?;
    let sections: BTreeMap<_, _> = carrier
        .sections()
        .iter()
        .map(|s| (s.section_id, s))
        .collect();
    let mut result = base("golden-board.m2-semantic-envelope/v2");
    result.insert("source_identities".into(), ids.clone());
    table(
        &mut result,
        "prototype",
        "kind,prototype_id,source_record_id,frame_bytes",
        array(field(&neutral, "prototype_rows")?)?.to_vec(),
    );
    table(
        &mut result,
        "bucket",
        "bucket_id,tier,protection_class,payload_bytes,slot_count,section_count",
        array(field(&neutral, "bucket_rows")?)?
            .iter()
            .map(|row| {
                let mut row = array(row)?.to_vec();
                require(row.len() == 6)?;
                row[2] = protection_class(&row[1], &row[2])?;
                Ok(V::Array(row))
            })
            .collect::<Result<Vec<_>>>()?,
    );
    table(
        &mut result,
        "slot",
        "bucket_id,slot_ordinal,role_ordinal,role_id,kind,prototype_id,frame_bytes",
        array(field(&neutral, "slot_rows")?)?.to_vec(),
    );
    let mut capacity_rows = Vec::new();
    let mut owners = BTreeMap::new();
    for row in array(field(&neutral, "capacity_section_rows")?)? {
        let row = array(row)?;
        require(row.len() == 8)?;
        if number(&row[7])? == 0 {
            continue;
        }
        let id = 211 + u32::try_from(capacity_rows.len()).map_err(|_| CarrierError::Arithmetic)?;
        let mut row = row.to_vec();
        row[0] = n(id);
        row[4] = protection_class(&row[3], &row[4])?;
        owners.insert(
            id,
            format!("capacity:{}:{}", text(&row[1])?, number(&row[2])?),
        );
        capacity_rows.push(V::Array(row));
    }
    table(
        &mut result,
        "capacity_section",
        "section_id,bucket_id,section_ordinal,tier,protection_class,first_slot_ordinal,slot_count,payload_bytes",
        capacity_rows,
    );
    let mut decoded = BTreeMap::new();
    let mut body_rows = Vec::new();
    let mut stored_sum = 0;
    for assignment in slice.assignments() {
        let id = u32::from(assignment.section_id());
        let section = sections.get(&id).ok_or(CarrierError::Section)?;
        let raw = crate::body_codec_v1::decode_body(section.section_version, &section.payload)
            .map_err(|_| CarrierError::Section)?;
        let (version, encoded) =
            crate::body_codec_v1::encode_body(&raw).map_err(|_| CarrierError::Section)?;
        require(version == section.section_version && encoded == section.payload)?;
        decoded.insert(id, raw.len() as u64);
        stored_sum = add(stored_sum, section.payload.len() as u64)?;
        body_rows.push(a([
            n(id),
            n(section.closure_class),
            n(section.copy_count),
            n(raw.len() as u64),
            n(section.payload.len() as u64),
            n(version),
            a(assignment.record_ids().iter().copied().map(n)),
            n(if (100..=163).contains(&id) {
                id - 100
            } else {
                65535
            }),
            n(if (200..=209).contains(&id) {
                id - 200
            } else {
                65535
            }),
        ]));
        owners.insert(id, format!("body:{id}"));
    }
    table(
        &mut result,
        "real_section",
        "section_id,closure_class,physical_replica_count,decoded_payload_bytes,stored_payload_bytes,section_version,record_ids,game_ordinal,fixture_ordinal",
        body_rows,
    );
    let mut tier_sum = 0;
    let mut tiers = Vec::new();
    for id in [2, 3] {
        let section = sections.get(&id).ok_or(CarrierError::Section)?;
        let tier =
            crate::decode_tier_frame(&section.payload, id).map_err(|_| CarrierError::Section)?;
        tier_sum = add(tier_sum, section.payload.len() as u64)?;
        owners.insert(id, format!("tier:{id}"));
        tiers.push(a([
            n(id),
            n(section.copy_count),
            n(section.payload.len() as u64),
            a(section.dependencies.iter().copied().map(n)),
            n(tier.assembled_stream_byte_length),
            n(tier.assembled_record_count),
            n(tier.root_record_bytes.len() as u64),
        ]));
    }
    table(
        &mut result,
        "tier_frame",
        "section_id,physical_replica_count,payload_bytes,dependency_ids,assembled_stream_bytes,assembled_record_count,root_record_bytes",
        tiers,
    );
    owners.insert(1, "inventory".into());
    for (kind, label) in [(5, "reserve"), (6, "load")] {
        for (ordinal, section) in carrier
            .sections()
            .iter()
            .filter(|s| s.section_type == kind)
            .enumerate()
        {
            owners.insert(section.section_id, format!("{label}:{ordinal}"));
        }
    }
    require(owners.len() == carrier.sections().len())?;
    let raw_sum = sum(decoded.values().copied())?;
    let before = sum([raw_sum, tier_sum, 16384, capacity.future_authoring_bytes()])?;
    let reserve = before.div_ceil(19).max(382);
    require(
        reserve == capacity.reserve_bytes()
            && raw_sum == capacity.uncompressed_body_bytes()
            && stored_sum == capacity.stored_body_bytes(),
    )?;
    let totals = o([
        (
            "prototype_count",
            n(array(field(&neutral, "prototype_rows")?)?.len() as u64),
        ),
        ("real_section_count", n(decoded.len() as u64)),
        ("tier_frame_count", n(2u64)),
        (
            "bucket_count",
            n(array(field(&neutral, "bucket_rows")?)?.len() as u64),
        ),
        (
            "capacity_section_count",
            n(capacity.capacity_probe_count() as u64),
        ),
        (
            "slot_count",
            n(array(field(&neutral, "slot_rows")?)?.len() as u64),
        ),
        (
            "authoring_payload_bytes",
            n(capacity.future_authoring_bytes()),
        ),
        ("real_decoded_body_payload_bytes", n(raw_sum)),
        ("real_stored_body_payload_bytes", n(stored_sum)),
        ("tier_payload_bytes", n(tier_sum)),
        ("content_capacity_before_reserve_bytes", n(before)),
        ("reserve_payload_bytes", n(reserve)),
        ("protected_logical_capacity_bytes", n(add(before, reserve)?)),
    ]);
    result.insert("totals".into(), totals);
    Ok((V::Object(result), owners, decoded))
}

fn mapping_value(mapping: Mapping) -> V {
    o([
        ("id", s("affine-slot-then-interior-v2")),
        ("interior_side", n(mapping.interior_side())),
        ("population", n(mapping.population())),
        ("unit_population", n(mapping.unit_slot_count())),
        ("unit_multiplier", n(mapping.slot_multiplier())),
        (
            "unit_inverse_multiplier",
            n(mapping.inverse_slot_multiplier()),
        ),
        ("cell_multiplier", n(mapping.cell_multiplier())),
        ("offset", n(mapping.cell_offset())),
        (
            "cell_inverse_multiplier",
            n(mapping.inverse_cell_multiplier()),
        ),
    ])
}

fn class(owner: ShellOwner) -> (&'static str, &'static str) {
    match owner {
        ShellOwner::Instruction => ("instruction", "shell_instruction_cells"),
        ShellOwner::Example => ("example", "shell_example_cells"),
        ShellOwner::Recipe => ("recipe", "shell_recipe_cells"),
        ShellOwner::Headroom => ("headroom", "shell_headroom_cells"),
        ShellOwner::FixedPad => ("fixed-pad", "shell_fixed_pad_cells"),
    }
}

fn bump(ledger: &mut BTreeMap<&'static str, u64>, key: &'static str, value: u64) -> Result<()> {
    let prior = *ledger.get(key).ok_or(CarrierError::ManifestShape)?;
    ledger.insert(key, add(prior, value)?);
    Ok(())
}

fn assign(
    owners: &mut [CellOwner],
    bits: &[u8],
    flat: usize,
    owner: CellOwner,
    expected: u8,
) -> Result<()> {
    let cell = owners.get_mut(flat).ok_or(CarrierError::Ownership)?;
    require(cell.kind == 0 && bits.get(flat) == Some(&expected) && expected <= 1)?;
    *cell = owner;
    Ok(())
}

fn physical_flat(mapping: Mapping, physical: u64) -> Result<usize> {
    require(physical < mapping.population())?;
    let i = u64::from(mapping.interior_side());
    let w = u64::from(mapping.shell_width());
    usize::try_from(add(
        mul(add(physical / i, w)?, u64::from(mapping.side()))?,
        add(physical % i, w)?,
    )?)
    .map_err(|_| CarrierError::Arithmetic)
}

fn shell_inverse(side: usize, width: usize, row: usize, column: usize) -> Option<(u8, usize)> {
    let span = side - width;
    if row < width && column < span {
        Some((0, row * span + column))
    } else if column >= span && row < span {
        Some((1, (side - 1 - column) * span + row))
    } else if row >= span && column >= width {
        Some((2, (side - 1 - row) * span + side - 1 - column))
    } else if column < width && row >= width {
        Some((3, column * span + side - 1 - row))
    } else {
        None
    }
}

struct Physical {
    capacity: V,
    ownership: V,
    density: V,
    realism: V,
    selected: V,
    groups: [u64; 3],
    compressed: u64,
}

fn physical(
    slice: &SliceCompilation,
    carrier: &Carrier,
    mapping: Mapping,
    semantic_sha: &str,
    names: &BTreeMap<u32, String>,
    decoded: &BTreeMap<u32, u64>,
    hash: &str,
    routes: &crate::carrier::RouteImages,
    prefixes: &[Vec<u8>; 4],
) -> Result<Physical> {
    let side = usize::from(carrier.side());
    let count = side.checked_mul(side).ok_or(CarrierError::Arithmetic)?;
    let raw = carrier.packed_bytes();
    require(
        count <= MAX_CELLS
            && count % 8 == 0
            && raw.len() == 4 + count / 8
            && u32_at(raw, 0)? as usize == count
            && carrier.unit_count() == mapping.unit_slot_count(),
    )?;
    let bits: Vec<u8> = raw[4..]
        .iter()
        .flat_map(|b| (0..8).rev().map(move |k| (b >> k) & 1))
        .collect();
    let mut owners = vec![
        CellOwner {
            kind: 0,
            owner_id: 0,
            bit_offset: 0
        };
        count
    ];
    let keys = [
        "stored_payload_bytes",
        "decoded_body_payload_bytes",
        "replicated_payload_bytes",
        "envelope_header_bytes",
        "section_check_bytes",
        "fragment_header_bytes",
        "fragment_zero_pad_bytes",
        "local_check_bytes",
        "transport_pad_bytes",
        "parity_bytes",
        "encoded_transport_bytes",
        "logical_group_count",
        "factor_1_group_count",
        "factor_2_group_count",
        "factor_5_group_count",
        "physical_unit_count",
        "codeword_count",
        "real_protected_cells",
        "capacity_probe_cells",
        "reserve_probe_cells",
        "load_probe_cells",
        "shell_instruction_cells",
        "shell_example_cells",
        "shell_recipe_cells",
        "shell_headroom_cells",
        "shell_fixed_pad_cells",
        "interior_fixed_pad_cells",
        "unused_cells",
        "total_cells",
    ];
    let mut ledger: BTreeMap<_, _> = keys.into_iter().map(|key| (key, 0)).collect();
    let mut shells = Vec::new();
    for sector in &routes.sectors {
        let mut coalesced: Vec<(u64, u64, &'static str)> = Vec::new();
        let mut cursor = 0;
        for span in &sector.spans {
            require(span.first_cell == cursor)?;
            let (name, key) = class(span.owner);
            bump(&mut ledger, key, span.cell_count)?;
            if span.cell_count != 0 {
                if let Some(prior) = coalesced.last_mut().filter(|p| p.2 == name) {
                    prior.1 = add(prior.1, span.cell_count)?;
                } else {
                    coalesced.push((cursor, span.cell_count, name));
                }
            }
            cursor = add(cursor, span.cell_count)?;
        }
        require(cursor == sector.bits.len() as u64)?;
        let prefix = sector.route_prefix_cells;
        let end_headroom = add(prefix, sector.headroom_cells)?;
        for (index, bit) in sector.bits.iter().copied().enumerate() {
            let (row, column) = crate::sector_cell_at(
                side,
                usize::from(carrier.shell_width()),
                sector.sector_id,
                index,
            )
            .map_err(|_| CarrierError::Geometry)?;
            let index = index as u64;
            let (kind, offset) = if index < prefix {
                (1, index)
            } else if index < end_headroom {
                (2, index - prefix)
            } else {
                (3, index - end_headroom)
            };
            assign(
                &mut owners,
                &bits,
                row * side + column,
                CellOwner {
                    kind,
                    owner_id: u32::from(sector.sector_id),
                    bit_offset: u32::try_from(offset).map_err(|_| CarrierError::Arithmetic)?,
                },
                bit,
            )?;
        }
        shells.push(a([
            n(sector.sector_id),
            n(prefix),
            n(sector.headroom_cells),
            n(sub(cursor, end_headroom)?),
            s(digest(&pack(&sector.bits)?)),
            a(coalesced
                .into_iter()
                .map(|(first, count, name)| a([n(first), n(count), s(name)]))),
        ]));
    }
    let mut section_rows = Vec::new();
    let mut unit_rows = Vec::new();
    let mut mapped_rows = Vec::new();
    let mut unit_types = vec![0u16];
    let mut groups = [0u64; 3];
    let mut unit_id = 0u64;
    let mut dependency_sum = 0;
    let mut maximum_deps = 0;
    let mut maximum_payload = 0;
    let mut maximum_envelope = 0;
    let mut maximum_fragments = 0;
    let mut compressed = 0;
    let mut load_bytes = Vec::new();
    let mut load_fragments = Vec::new();
    let mut mandatory = 0;
    for section in carrier.sections() {
        require(section.payload.len() <= 16384 && section.dependencies.len() <= 4095)?;
        let factor = u64::from(section.copy_count);
        let factor_index = match factor {
            1 => 0,
            2 => 1,
            5 => 2,
            _ => return Err(CarrierError::Section),
        };
        let envelope = section.envelope()?;
        let commons = crate::fragment_envelope(
            8,
            section.section_id,
            0,
            section.section_type,
            section.section_version,
            &envelope,
        )
        .map_err(|_| CarrierError::Section)?;
        let fragments = commons.len() as u64;
        groups[factor_index] = add(groups[factor_index], fragments)?;
        let physical = mul(factor, fragments)?;
        dependency_sum = add(dependency_sum, section.dependencies.len() as u64)?;
        maximum_deps = maximum_deps.max(section.dependencies.len() as u64);
        maximum_payload = maximum_payload.max(section.payload.len() as u64);
        maximum_envelope = maximum_envelope.max(envelope.len() as u64);
        maximum_fragments = maximum_fragments.max(fragments);
        let decoded_length = decoded
            .get(&section.section_id)
            .copied()
            .unwrap_or(section.payload.len() as u64);
        let first = add(unit_id, 1)?;
        for (fragment, common) in commons.iter().enumerate() {
            let encoded = crate::candidate::encode_eh_unit(common);
            for replica in 0..section.copy_count {
                unit_id = add(unit_id, 1)?;
                require(unit_id <= mapping.unit_slot_count())?;
                let slot = mul(mapping.slot_multiplier(), unit_id - 1)? % mapping.unit_slot_count();
                let mut mapped_hash = Sha256::new();
                for bit in 0..1728u16 {
                    let physical = mapping.forward(unit_id, bit)?;
                    require(mapping.inverse(physical)? == (0, unit_id, bit))?;
                    mapped_hash.update(
                        u32::try_from(physical)
                            .map_err(|_| CarrierError::Arithmetic)?
                            .to_be_bytes(),
                    );
                    assign(
                        &mut owners,
                        &bits,
                        physical_flat(mapping, physical)?,
                        CellOwner {
                            kind: 4,
                            owner_id: u32::try_from(unit_id)
                                .map_err(|_| CarrierError::Arithmetic)?,
                            bit_offset: u32::from(bit),
                        },
                        (encoded[usize::from(bit) / 8] >> (7 - bit % 8)) & 1,
                    )?;
                }
                mapped_rows.push(a([n(unit_id), s(format!("{:x}", mapped_hash.finalize()))]));
                unit_rows.push(a([
                    n(unit_id),
                    n(section.section_id),
                    n(0u64),
                    n(fragment as u64),
                    n(replica),
                    n(section.copy_count),
                    n(encoded.len() as u64),
                    s(digest(&encoded)),
                    n(slot),
                    n(mul(slot, 1728)?),
                    n(1728u64),
                ]));
                unit_types.push(section.section_type);
            }
        }
        section_rows.push(a([
            n(section.section_id),
            n(section.section_type),
            n(section.section_version),
            n(section.closure_class),
            n(section.check_id),
            n(1u64),
            n(section.copy_count),
            s(names
                .get(&section.section_id)
                .ok_or(CarrierError::Section)?
                .clone()),
            a(section.dependencies.iter().copied().map(n)),
            n(section.payload.len() as u64),
            n(decoded_length),
            s(digest(&section.payload)),
            s(digest(&envelope)),
            n(envelope.len() as u64),
            n(fragments),
            n(first),
            n(unit_id),
        ]));
        bump(
            &mut ledger,
            "stored_payload_bytes",
            section.payload.len() as u64,
        )?;
        bump(
            &mut ledger,
            "replicated_payload_bytes",
            mul(factor, section.payload.len() as u64)?,
        )?;
        bump(
            &mut ledger,
            "envelope_header_bytes",
            mul(factor, add(18, mul(4, section.dependencies.len() as u64)?)?)?,
        )?;
        bump(&mut ledger, "section_check_bytes", mul(factor, 4)?)?;
        bump(
            &mut ledger,
            "fragment_zero_pad_bytes",
            sub(mul(157, physical)?, mul(factor, envelope.len() as u64)?)?,
        )?;
        if section.section_type == 3 {
            bump(&mut ledger, "decoded_body_payload_bytes", decoded_length)?;
            compressed = add(compressed, u64::from(section.section_version == 1))?;
        }
        let key = match section.section_type {
            1..=3 => "real_protected_cells",
            4 => "capacity_probe_cells",
            5 => "reserve_probe_cells",
            6 => "load_probe_cells",
            _ => return Err(CarrierError::Section),
        };
        bump(&mut ledger, key, mul(1728, physical)?)?;
        if section.section_type == 6 {
            load_bytes.push(n(section.payload.len() as u64));
            load_fragments.push(n(fragments));
        } else {
            mandatory = add(mandatory, physical)?;
        }
    }
    require(unit_id == mapping.unit_slot_count())?;
    for (key, per_unit) in [
        ("fragment_header_bytes", 30),
        ("local_check_bytes", 4),
        ("transport_pad_bytes", 1),
        ("parity_bytes", 24),
        ("encoded_transport_bytes", 216),
        ("physical_unit_count", 1),
        ("codeword_count", 24),
    ] {
        bump(&mut ledger, key, mul(unit_id, per_unit)?)?;
    }
    for (key, value) in [
        ("factor_1_group_count", groups[0]),
        ("factor_2_group_count", groups[1]),
        ("factor_5_group_count", groups[2]),
        ("logical_group_count", sum(groups)?),
        ("interior_fixed_pad_cells", mapping.fixed_pad_cells()),
        ("total_cells", count as u64),
    ] {
        bump(&mut ledger, key, value)?;
    }
    require(sum([groups[0], mul(2, groups[1])?, mul(5, groups[2])?])? == unit_id)?;
    let fill_bytes = sum(carrier
        .sections()
        .iter()
        .filter(|s| s.section_type >= 4)
        .map(|s| s.payload.len() as u64))?;
    let fill_length = add(mul(fill_bytes, 8)?, mapping.fixed_pad_cells())?;
    let seed: [u8; 32] = Sha256::digest(slice.all_stream()).into();
    let fill = crate::carrier::fill_bits(
        &seed,
        usize::try_from(fill_length).map_err(|_| CarrierError::Arithmetic)?,
    )?;
    let mut fill_cursor = 0usize;
    for section in carrier.sections().iter().filter(|s| s.section_type >= 4) {
        let end = fill_cursor
            .checked_add(section.payload.len() * 8)
            .ok_or(CarrierError::Arithmetic)?;
        require(pack(&fill[fill_cursor..end])? == section.payload)?;
        fill_cursor = end;
    }
    let protected = mul(unit_id, 1728)?;
    for (offset, bit) in fill[fill_cursor..].iter().copied().enumerate() {
        let logical = add(protected, offset as u64)?;
        let physical = add(
            mul(mapping.cell_multiplier(), logical)?,
            mapping.cell_offset(),
        )? % mapping.population();
        require(mapping.inverse(physical)? == (1, 0, 0))?;
        assign(
            &mut owners,
            &bits,
            physical_flat(mapping, physical)?,
            CellOwner {
                kind: 5,
                owner_id: 0,
                bit_offset: offset as u32,
            },
            bit,
        )?;
    }
    require(owners.iter().all(|owner| (1..=5).contains(&owner.kind)))?;
    // Independently invert every actual matrix coordinate in row-major order.
    // The assignment bitmap already rejects overlap; this checks the inverse
    // geometry and the pad's logical offset rather than its physical rank.
    let width = usize::from(carrier.shell_width());
    for (flat, owner) in owners.iter().enumerate() {
        let (row, column) = (flat / side, flat % side);
        if let Some((sector, local)) = shell_inverse(side, width, row, column) {
            let image = &routes.sectors[usize::from(sector)];
            let local = local as u64;
            let (kind, offset) = if local < image.route_prefix_cells {
                (1, local)
            } else if local < add(image.route_prefix_cells, image.headroom_cells)? {
                (2, local - image.route_prefix_cells)
            } else {
                (3, local - image.route_prefix_cells - image.headroom_cells)
            };
            require(
                owner.kind == kind
                    && owner.owner_id == u32::from(sector)
                    && u64::from(owner.bit_offset) == offset,
            )?;
            let inverse = crate::sector_cell_at(side, width, sector, local as usize)
                .map_err(|_| CarrierError::Geometry)?;
            require(inverse == (row, column))?;
        } else {
            require(
                row >= width && column >= width && row < side - width && column < side - width,
            )?;
            let interior_flat = add(
                mul((row - width) as u64, u64::from(mapping.interior_side()))?,
                (column - width) as u64,
            )?;
            match mapping.inverse(interior_flat)? {
                (0, unit, bit) => require(
                    owner.kind == 4
                        && u64::from(owner.owner_id) == unit
                        && owner.bit_offset == u32::from(bit),
                )?,
                (1, 0, 0) => {
                    let shifted = add(interior_flat, mapping.population())? - mapping.cell_offset();
                    let logical =
                        mul(mapping.inverse_cell_multiplier(), shifted)? % mapping.population();
                    require(
                        owner.kind == 5
                            && owner.owner_id == 0
                            && u64::from(owner.bit_offset) == sub(logical, protected)?,
                    )?;
                }
                _ => return Err(CarrierError::Ownership),
            }
        }
    }
    let transport_sum = sum([
        "replicated_payload_bytes",
        "envelope_header_bytes",
        "section_check_bytes",
        "fragment_header_bytes",
        "fragment_zero_pad_bytes",
        "local_check_bytes",
        "transport_pad_bytes",
        "parity_bytes",
    ]
    .map(|k| ledger[k]))?;
    require(transport_sum == ledger["encoded_transport_bytes"])?;
    require(
        sum([
            "real_protected_cells",
            "capacity_probe_cells",
            "reserve_probe_cells",
            "load_probe_cells",
            "shell_instruction_cells",
            "shell_example_cells",
            "shell_recipe_cells",
            "shell_headroom_cells",
            "shell_fixed_pad_cells",
            "interior_fixed_pad_cells",
        ]
        .map(|k| ledger[k]))?
            == count as u64,
    )?;
    let mut capacity = base("golden-board.m2-capacity-ledger/v2");
    capacity.insert("carrier_sha256".into(), s(hash));
    capacity.insert("semantic_envelope_sha256".into(), s(semantic_sha));
    table(
        &mut capacity,
        "section",
        "section_id,section_type,section_version,closure_class,check_id,semantic_copy_count,physical_replica_count,owner_id,dependency_ids,stored_payload_bytes,decoded_payload_bytes,payload_sha256,envelope_sha256,envelope_bytes,fragment_count,first_physical_unit,last_physical_unit",
        section_rows,
    );
    table(
        &mut capacity,
        "unit",
        "physical_unit_id,section_id,semantic_copy_id,fragment_index,replica_index,physical_replica_count,encoded_bytes,encoded_sha256,slot,logical_bit_first,logical_bit_count",
        unit_rows,
    );
    capacity.insert(
        "ledger".into(),
        V::Object(ledger.into_iter().map(|(k, v)| (k.into(), n(v))).collect()),
    );
    let capacity = V::Object(capacity);
    let capacity_sha = digest(&serialize(capacity.clone())?);
    let mut ownership = base("golden-board.m2-ownership-ledger/v2");
    ownership.insert("carrier_sha256".into(), s(hash));
    ownership.insert("capacity_ledger_sha256".into(), s(capacity_sha));
    ownership.insert("side".into(), n(carrier.side()));
    ownership.insert("shell_width".into(), n(carrier.shell_width()));
    ownership.insert("mapping".into(), mapping_value(mapping));
    table(
        &mut ownership,
        "shell",
        "sector_id,route_prefix_cells,headroom_cells,fixed_pad_cells,image_sha256,spans",
        shells,
    );
    table(
        &mut ownership,
        "unit",
        "physical_unit_id,mapped_cell_sha256",
        mapped_rows,
    );
    ownership.insert(
        "interior_fixed_pad".into(),
        o([
            ("logical_bit_first", n(protected)),
            ("logical_bit_count", n(mapping.fixed_pad_cells())),
            ("fill_order", s("affine-images-of-ascending-logical-tail")),
        ]),
    );
    ownership.insert("cell_table".into(), o([("row_bytes", n(9u64)), ("row_count", n(count as u64)), ("row_order", s("canonical-matrix-row-major")),
        ("owner_kind_ids", a(["1-shell-route", "2-shell-headroom", "3-shell-fixed-pad", "4-protected-unit", "5-interior-fixed-pad"].map(s))),
        ("owner_id_rule", s("sector-id-for-shell-kinds-physical-unit-id-for-protected-unit-zero-for-interior-fixed-pad")),
        ("owner_bit_offset_rule", s("zero-based-offset-within-named-owner"))]));
    let mut cell_hash = Sha256::new();
    for owner in &owners {
        cell_hash.update([owner.kind]);
        cell_hash.update(owner.owner_id.to_be_bytes());
        cell_hash.update(owner.bit_offset.to_be_bytes());
    }
    ownership.insert(
        "cell_table_sha256".into(),
        s(format!("{:x}", cell_hash.finalize())),
    );
    let (density, realism) = density(
        &bits,
        &owners,
        &unit_types,
        side,
        usize::from(carrier.shell_width()),
        hash,
    )?;
    let inventory = carrier.sections().first().ok_or(CarrierError::Section)?;
    let selected = o([
        ("side", n(carrier.side())),
        ("shell_width", n(carrier.shell_width())),
        ("cells", n(count as u64)),
        ("carrier_bytes", n(count as u64 / 8)),
        ("carrier_file_bytes", n(raw.len() as u64)),
        ("interior_side", n(mapping.interior_side())),
        ("population", n(mapping.population())),
        ("physical_units", n(unit_id)),
        ("protected_cells", n(protected)),
        ("fixed_pad_cells", n(mapping.fixed_pad_cells())),
        ("inventory_entries", n(carrier.sections().len() as u64)),
        ("inventory_payload_bytes", n(inventory.payload.len() as u64)),
        ("inventory_dependency_count", n(dependency_sum)),
        ("maximum_dependency_count", n(maximum_deps)),
        ("maximum_section_payload_bytes", n(maximum_payload)),
        (
            "maximum_decoded_body_bytes",
            n(decoded
                .values()
                .copied()
                .max()
                .ok_or(CarrierError::Section)?),
        ),
        ("maximum_section_envelope_bytes", n(maximum_envelope)),
        ("maximum_fragments_per_section", n(maximum_fragments)),
        ("logical_groups", n(sum(groups)?)),
        ("factor_group_counts", a(groups.map(n))),
        ("load_payload_bytes", V::Array(load_bytes)),
        ("load_fragment_counts", V::Array(load_fragments)),
        ("mandatory_physical_units", n(mandatory)),
        (
            "route_prefix_bytes",
            a(prefixes.iter().map(|p| n(p.len() as u64))),
        ),
        (
            "route_headroom_cells",
            a(routes.sectors.iter().map(|s| n(s.headroom_cells))),
        ),
    ]);
    Ok(Physical {
        capacity,
        ownership: V::Object(ownership),
        density,
        realism,
        selected,
        groups,
        compressed,
    })
}

fn density(
    bits: &[u8],
    owners: &[CellOwner],
    unit_types: &[u16],
    side: usize,
    width: usize,
    hash: &str,
) -> Result<(V, V)> {
    require(
        side <= 2048 && width * 2 < side && bits.len() == side * side && owners.len() == bits.len(),
    )?;
    let ids = [
        "shell",
        "real-protected",
        "capacity-probe",
        "reserve-probe",
        "load-probe",
        "fixed-pad",
        "complete-interior",
    ];
    let mut cells = [0u64; 7];
    let mut ones = [0u64; 7];
    for (flat, (&bit, owner)) in bits.iter().zip(owners).enumerate() {
        require(bit <= 1)?;
        let mut indices = [false; 7];
        match owner.kind {
            1..=3 => indices[0] = true,
            4 => {
                indices[match unit_types.get(owner.owner_id as usize) {
                    Some(1..=3) => 1,
                    Some(4) => 2,
                    Some(5) => 3,
                    Some(6) => 4,
                    _ => return Err(CarrierError::Ownership),
                }] = true
            }
            5 => (),
            _ => return Err(CarrierError::Ownership),
        }
        indices[5] = matches!(owner.kind, 3 | 5);
        let row = flat / side;
        let column = flat % side;
        indices[6] = row >= width && row < side - width && column >= width && column < side - width;
        for i in 0..7 {
            if indices[i] {
                cells[i] = add(cells[i], 1)?;
                ones[i] = add(ones[i], u64::from(bit))?;
            }
        }
    }
    let interior = side - 2 * width;
    let at = |r: usize, c: usize| bits[(r + width) * side + c + width];
    let mut regularity = [0u64; 6];
    for axis in 0..2 {
        let mut seen = BTreeSet::new();
        for line in 0..interior {
            let pattern: Vec<u8> = (0..interior)
                .map(|k| if axis == 0 { at(line, k) } else { at(k, line) })
                .collect();
            let mut run = 0;
            let mut prior = 2;
            for &bit in &pattern {
                run = if bit == prior { add(run, 1)? } else { 1 };
                regularity[axis] = regularity[axis].max(run);
                prior = bit;
            }
            if !seen.insert(pattern) {
                regularity[4 + axis] = add(regularity[4 + axis], 1)?;
            }
        }
    }
    regularity[2] = u64::MAX;
    for r in 0..interior / 32 {
        for c in 0..interior / 32 {
            let count = sum((0..32)
                .flat_map(|dr| (0..32).map(move |dc| u64::from(at(r * 32 + dr, c * 32 + dc)))))?;
            regularity[2] = regularity[2].min(count);
            regularity[3] = regularity[3].max(count);
        }
    }
    require(cells[6] > 0 && regularity[2] != u64::MAX)?;
    let run_limit = 128.max((interior as u64).div_ceil(4));
    let repeat_limit = 2.max(interior as u64 / 32);
    let conditions = [
        (
            mul(ones[6], 4)? < cells[6],
            "global-one-fraction-below-minimum",
        ),
        (
            mul(ones[6], 4)? > mul(cells[6], 3)?,
            "global-one-fraction-above-maximum",
        ),
        (regularity[2] < 128, "tile-one-count-below-minimum"),
        (regularity[3] > 896, "tile-one-count-above-maximum"),
        (
            regularity[0] > run_limit,
            "horizontal-equal-run-above-maximum",
        ),
        (
            regularity[1] > run_limit,
            "vertical-equal-run-above-maximum",
        ),
        (
            regularity[4] > repeat_limit,
            "repeated-row-count-above-maximum",
        ),
        (
            regularity[5] > repeat_limit,
            "repeated-column-count-above-maximum",
        ),
    ];
    let failures: Vec<_> = conditions
        .into_iter()
        .filter(|(failed, _)| *failed)
        .map(|(_, label)| s(label))
        .collect();
    let realism = o([
        (
            "result",
            s(if failures.is_empty() { "pass" } else { "fail" }),
        ),
        ("failures", V::Array(failures)),
    ]);
    let density = o([
        ("schema", s("golden-board.m2-density-ledger/v0")),
        ("profile_id", s(PROFILE)),
        ("carrier_sha256", s(hash)),
        (
            "scope_rows",
            a((0..7)
                .map(|i| {
                    Ok(o([
                        ("scope_id", s(ids[i])),
                        ("cell_count", n(cells[i])),
                        ("zero_count", n(sub(cells[i], ones[i])?)),
                        ("one_count", n(ones[i])),
                        (
                            "one_density_ppm",
                            n(if cells[i] == 0 {
                                0
                            } else {
                                mul(ones[i], 1_000_000)? / cells[i]
                            }),
                        ),
                    ]))
                })
                .collect::<Result<Vec<_>>>()?),
        ),
        (
            "interior_regularity",
            o([
                ("longest_horizontal_equal_run", n(regularity[0])),
                ("longest_vertical_equal_run", n(regularity[1])),
                ("tile_one_count_min", n(regularity[2])),
                ("tile_one_count_max", n(regularity[3])),
                ("repeated_row_count", n(regularity[4])),
                ("repeated_column_count", n(regularity[5])),
            ]),
        ),
    ]);
    Ok((density, realism))
}

fn package(prefixes: &[Vec<u8>; 4], q: u64, groups: [u64; 3], compressed: u64) -> Result<(V, V)> {
    let mut packages = Vec::new();
    let mut counts = Vec::new();
    for prefix in prefixes {
        require(
            prefix.len() <= 1_048_576
                && prefix.len() >= 64
                && u16_at(prefix, 40)? == 2
                && u16_at(prefix, 44)? == 8,
        )?;
        let count = u16_at(prefix, 46)?;
        counts.push(n(count));
        let mut cursor = 64usize;
        let mut found = None;
        for _ in 0..count {
            let kind = *prefix.get(cursor + 1).ok_or(CarrierError::Recipe)?;
            let length = u32_at(prefix, cursor + 4)? as usize;
            let end = cursor
                .checked_add(8)
                .and_then(|n| n.checked_add(length))
                .ok_or(CarrierError::Arithmetic)?;
            let payload = prefix.get(cursor + 8..end).ok_or(CarrierError::Recipe)?;
            if kind == 5 {
                require(found.is_none())?;
                found = Some(payload.to_vec());
            }
            cursor = end;
        }
        require(cursor == prefix.len())?;
        packages.push(found.ok_or(CarrierError::Recipe)?);
    }
    require(packages.windows(2).all(|p| p[0] == p[1]))?;
    let raw = &packages[0];
    let parsed = decode_recipe_package_v2(raw, 8).map_err(|_| CarrierError::Recipe)?;
    let expanded = expand_recipe_package_v2(raw, 8).map_err(|_| CarrierError::Recipe)?;
    let mut cursor = 64usize;
    for _ in 0..u16_at(&expanded, 18)? {
        cursor = cursor
            .checked_add(16)
            .and_then(|n| n.checked_add(u32_at(&expanded, cursor + 12).ok()? as usize))
            .ok_or(CarrierError::Recipe)?;
    }
    let mut recipe_rows = Vec::new();
    for _ in 0..u16_at(&expanded, 16)? {
        let id = u16_at(&expanded, cursor)?;
        let steps = u64_at(&expanded, cursor + 16)?;
        let scratch = u32_at(&expanded, cursor + 24)?;
        require(
            parsed.logical.recipe_primitive_steps(id) == Some(steps)
                && parsed.logical.recipe_peak_scratch_bytes(id) == Some(u64::from(scratch)),
        )?;
        recipe_rows.push(a([
            n(id),
            n(u32_at(&expanded, cursor + 8)?),
            n(u32_at(&expanded, cursor + 12)?),
            n(steps),
            n(scratch),
        ]));
        cursor = cursor
            .checked_add(u32_at(&expanded, cursor + 28)? as usize)
            .ok_or(CarrierError::Arithmetic)?;
    }
    require(cursor == expanded.len())?;
    let value = o([
        ("sha256", s(digest(raw))),
        ("encoded_bytes", n(raw.len() as u64)),
        ("expanded_bytes", n(expanded.len() as u64)),
        ("recipe_count", n(u16_at(raw, 16)?)),
        ("table_count", n(u16_at(raw, 18)?)),
        ("table_payload_bytes", n(u32_at(raw, 28)?)),
        ("node_count", n(u32_at(raw, 20)?)),
        ("edge_count", n(u32_at(raw, 24)?)),
        (
            "maximum_declared_primitive_steps",
            n(parsed.logical.maximum_primitive_steps),
        ),
        (
            "maximum_declared_scratch_bytes",
            n(parsed.logical.peak_scratch_bytes),
        ),
        (
            "recipe_fields",
            a([
                "recipe_id",
                "node_count",
                "edge_count",
                "primitive_steps",
                "scratch_bytes",
            ]
            .map(s)),
        ),
        ("recipe_rows", V::Array(recipe_rows)),
        ("records_per_sector", V::Array(counts)),
        ("prefix_sha256", a(prefixes.iter().map(|p| s(digest(p))))),
    ]);
    let repeated = add(groups[1], groups[2])?;
    let eh_calls = mul(24, q)?;
    let symbol_calls = mul(1728, repeated)?;
    let group_calls = add(groups[0], repeated)?;
    let mut steps = 0;
    let mut scratch = 0;
    // One catalog pass after inventory admission. Repetition-symbol work is
    // included in complete120; acquisition/bootstrap127 belong to full sidecars.
    for (id, calls) in [
        (30, eh_calls),
        (120, group_calls),
        (123, group_calls),
        (202, compressed),
    ] {
        steps = add(
            steps,
            mul(
                calls,
                parsed
                    .logical
                    .recipe_primitive_steps(id)
                    .ok_or(CarrierError::Recipe)?,
            )?,
        )?;
        if calls > 0 {
            scratch = scratch.max(
                parsed
                    .logical
                    .recipe_peak_scratch_bytes(id)
                    .ok_or(CarrierError::Recipe)?,
            );
        }
    }
    let declared = o([
        ("scope", s("one-pass-complete-inventory-groups")),
        ("eh_codewords_per_unit", n(24u64)),
        ("eh_decoder_calls", n(eh_calls)),
        ("repetition_groups", n(repeated)),
        ("repetition_symbol_calls", n(symbol_calls)),
        ("complete_group_calls", n(group_calls)),
        ("roster_calls", n(group_calls)),
        ("body_decoder_calls", n(compressed)),
        ("primitive_steps", n(steps)),
        ("peak_recipe_scratch_bytes", n(scratch)),
    ]);
    Ok((value, declared))
}

pub fn build_static_projection_v2(
    slice: &SliceCompilation,
    carrier: &Carrier,
) -> Result<StaticProjectionV2> {
    build_static_projection_v2_with_sources(slice, carrier, StaticSources::default())
}

pub fn build_static_projection_v2_with_sources(
    slice: &SliceCompilation,
    carrier: &Carrier,
    source: StaticSources<'_>,
) -> Result<StaticProjectionV2> {
    admit_sources(source)?;
    // Carrier has private fields, but may belong to another admitted slice.
    // Rebuild and compare every section/probe byte and every searched geometry.
    require(&build_carrier(slice)? == carrier)?;
    for (raw, view) in [
        (slice.required_stream(), slice.required_projection()),
        (slice.all_stream(), slice.all_projection()),
    ] {
        require(raw.len() <= 1_048_576)?;
        let authored =
            gb_content::authoring_from_validated(view).map_err(|_| CarrierError::Section)?;
        require(
            gb_content::encode_content_v0(&authored).map_err(|_| CarrierError::Section)? == raw,
        )?;
    }
    let mapping = derive(carrier.side(), carrier.shell_width())?;
    let prefixes = crate::route_v2::build_route_prefixes(slice)?;
    let routes = crate::route_v2::build_route_images(slice, carrier.side(), carrier.shell_width())?;
    let ids = provenance(slice, source);
    let hash = digest(carrier.packed_bytes());
    let (semantic, names, decoded) = semantic(slice, carrier, source, &ids)?;
    let semantic_raw = serialize(semantic.clone())?;
    let physical = physical(
        slice,
        carrier,
        mapping,
        &digest(&semantic_raw),
        &names,
        &decoded,
        &hash,
        &routes,
        &prefixes,
    )?;
    let geometry = o([
        ("schema", s("golden-board.m2-geometry-search/v2")),
        ("profile_id", s(PROFILE)),
        (
            "prefix_bytes",
            a(prefixes.iter().map(|p| n(p.len() as u64))),
        ),
        (
            "headroom_cells",
            a(routes.sectors.iter().map(|r| n(r.headroom_cells))),
        ),
        ("selected_side", n(carrier.side())),
        ("selected_shell_width", n(carrier.shell_width())),
        ("row_fields", a(["side", "shell_width", "result"].map(s))),
        (
            "rows",
            a(carrier.search_ledger().iter().map(|r| {
                a([
                    n(r.side),
                    n(r.shell_width),
                    s(match r.failure {
                        Some(SearchFailure::RouteFit) => "route-headroom",
                        Some(SearchFailure::Mapping) => "mapping-table",
                        Some(SearchFailure::LoadFit) => "inventory-load-fixed-point",
                        None => "fit",
                    }),
                ])
            })),
        ),
    ]);
    let mut documents = BTreeMap::new();
    documents.insert("semantic-envelope.json", semantic_raw);
    documents.insert("capacity-ledger.json", serialize(physical.capacity)?);
    documents.insert("ownership-ledger.json", serialize(physical.ownership)?);
    documents.insert("density-ledger.json", serialize(physical.density)?);
    documents.insert("geometry-search.json", serialize(geometry)?);
    let (package, declared) = package(
        &prefixes,
        carrier.unit_count(),
        physical.groups,
        physical.compressed,
    )?;
    let projection_hashes: Object = [
        ("semantic_envelope", "semantic-envelope.json"),
        ("capacity_ledger", "capacity-ledger.json"),
        ("ownership_ledger", "ownership-ledger.json"),
        ("density_ledger", "density-ledger.json"),
        ("geometry_search", "geometry-search.json"),
    ]
    .into_iter()
    .map(|(key, name)| (key.to_owned(), s(digest(&documents[name]))))
    .collect();
    let limits = o([
        ("schema", s("golden-board.m2-static-limits/v2")),
        ("profile_id", s(PROFILE)),
        ("scope", s("static-construction-only")),
        ("source_identities", ids.clone()),
        ("carrier_sha256", s(&hash)),
        ("projection_sha256", V::Object(projection_hashes)),
        ("semantic_capacity", field(&semantic, "totals")?.clone()),
        ("selected_manifestation", physical.selected),
        ("route_package", package),
        ("declared_transport", declared),
        ("realism", physical.realism),
    ]);
    documents.insert("static-limits.json", serialize(limits)?);
    let mut files: BTreeMap<String, (u64, String)> = documents
        .iter()
        .map(|(name, bytes)| ((*name).to_owned(), (bytes.len() as u64, digest(bytes))))
        .collect();
    files.insert(
        "carrier.bin".into(),
        (carrier.packed_bytes().len() as u64, hash),
    );
    for (sector, prefix) in prefixes.iter().enumerate() {
        files.insert(
            format!("route-{sector}.bin"),
            (prefix.len() as u64, digest(prefix)),
        );
    }
    let mut candidate = base("golden-board.m2-candidate-manifest/v2");
    candidate.insert("profile_version".into(), n(8u64));
    candidate.insert("status".into(), s("static-projection-only"));
    candidate.insert("source_identities".into(), ids);
    candidate.insert(
        "files".into(),
        a(files.into_iter().map(|(path, (bytes, sha))| {
            o([("path", s(path)), ("bytes", n(bytes)), ("sha256", s(sha))])
        })),
    );
    let omitted = serialize(V::Object(candidate.clone()))?;
    let identity = identity_hex(b"golden-board:manifest:v0\0", &[&omitted])
        .map_err(|_| CarrierError::ManifestShape)?;
    candidate.insert("manifest_identity".into(), s(identity));
    documents.insert("candidate-manifest.json", serialize(V::Object(candidate))?);
    Ok(StaticProjectionV2 { documents })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn malformed_owner_source_rejects_without_building_a_carrier() {
        let mut sources = StaticSources::default();
        sources.profile_policy = b"profile_version = true\n";
        assert!(admit_sources(sources).is_err());
        let mut changed = StaticSources::default().profile_limits.to_vec();
        changed.extend_from_slice(b"\n[unexpected]\nvalue=0\n");
        sources = StaticSources::default();
        sources.profile_limits = &changed;
        assert!(admit_sources(sources).is_err());
    }

    #[test]
    fn uniform_interior_returns_measured_failures_in_owned_order() {
        let side = 64;
        let owners = vec![
            CellOwner {
                kind: 5,
                owner_id: 0,
                bit_offset: 0
            };
            side * side
        ];
        let (_, realism) = density(&vec![0; side * side], &owners, &[0], side, 8, "test").unwrap();
        assert_eq!(text(field(&realism, "result").unwrap()).unwrap(), "fail");
        let failures = array(field(&realism, "failures").unwrap()).unwrap();
        assert_eq!(
            failures,
            [
                s("global-one-fraction-below-minimum"),
                s("tile-one-count-below-minimum"),
                s("repeated-row-count-above-maximum"),
                s("repeated-column-count-above-maximum")
            ]
        );
    }
}
