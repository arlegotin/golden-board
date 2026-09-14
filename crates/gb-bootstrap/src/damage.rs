//! Bounded M2 damage observations, generators, and recovery evaluator.
//!
//! The decoder side of this module accepts only a serialized named channel and
//! candidate-neutral bootstrap owners.  Damage coordinates and the clean
//! carrier are kept on the generator/oracle side and are never decoder input.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::OnceLock;

use gb_foundation::{ManifestValue, serialize_manifest};
use sha2::{Digest, Sha256};

use crate::candidate::{
    DecodeQuality, DecodedUnit, EH_CODEWORD_BITS, EH_UNIT_BYTES, EhErasure, EhObservation,
    RS_CODEWORD_BYTES, TransportFamily, decode_eh_unit, decode_eh_unit_fast, decode_rs_unit,
    encode_eh_unit, encode_rs255_191, profile_by_version,
};
use crate::candidate_recipe::{build_eh_recipe_package, build_rs_decoder_recipe_package};
use crate::carrier::{AffineMap, ManifestationCore};
use crate::policy::load_damage_policy;
use crate::recipe::{decode_recipe_package, evaluate_serialized_recipe};
use crate::{
    CHECK_CRC32C, CLOSURE_M2_REQUIRED, COMMON_PAYLOAD_BYTES, EntryHypothesis, FragmentWitness,
    Inventory, LOCAL_CHECK_DOMAIN, MAX_RAW_BITS, MAX_SIDE, RecoveryQuality, SECTION_INVENTORY,
    SectionEnvelope, SectionWitness, aggregate_section_witnesses, assemble_content_stream,
    assemble_semantic_copy, crc32c, decode_common_block, decode_inventory, decode_section,
    decode_tier_frame, encode_common_block, encode_section, fragment_envelope, sector_cell_at,
    validate_envelope_against_inventory, validate_tier_against_inventory,
};

const DAMAGE_DOMAIN: &[u8] = b"GB-DAMAGE-v0\0";
pub(crate) const WINDOW_DOMAIN: &[u8] = b"GB-DAMAGE-WINDOW-v0\0";
const MAX_UNITS: usize = 16_384;
const UNIT_BITS: usize = EH_UNIT_BYTES * 8;
const ROUTE_MAGIC: &[u8; 8] = b"GBROUTE\0";
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
const FACT_STAGES: [u8; 12] = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DamageError {
    Channel,
    Length,
    Value,
    Coordinate,
    Duplicate,
    Operator,
    SamplePopulation,
    SampleResource,
    Route,
    Profile,
    Reconstruction,
    Ambiguous,
    ResourceLimit,
}

pub type Result<T> = std::result::Result<T, DamageError>;

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct ResourceProjection {
    pub section_attempts: u64,
    pub primitive_steps: u64,
    pub peak_scratch_bytes: u64,
}

fn merge_resource(target: &mut ResourceProjection, source: ResourceProjection) -> Result<()> {
    target.section_attempts = target
        .section_attempts
        .checked_add(source.section_attempts)
        .ok_or(DamageError::ResourceLimit)?;
    target.primitive_steps = target
        .primitive_steps
        .checked_add(source.primitive_steps)
        .ok_or(DamageError::ResourceLimit)?;
    target.peak_scratch_bytes = target.peak_scratch_bytes.max(source.peak_scratch_bytes);
    Ok(())
}

fn charge_recipe(
    resource: &mut ResourceProjection,
    package: &crate::recipe::RecipePackage,
    recipe_id: u16,
    invocations: u64,
) -> Result<()> {
    let steps = package
        .recipe_primitive_steps(recipe_id)
        .and_then(|value| value.checked_mul(invocations))
        .ok_or(DamageError::ResourceLimit)?;
    resource.primitive_steps = resource
        .primitive_steps
        .checked_add(steps)
        .ok_or(DamageError::ResourceLimit)?;
    resource.peak_scratch_bytes = resource.peak_scratch_bytes.max(
        package
            .recipe_peak_scratch_bytes(recipe_id)
            .ok_or(DamageError::Reconstruction)?,
    );
    Ok(())
}

fn charge_section_attempts(resource: &mut ResourceProjection, count: usize) -> Result<()> {
    let count = u64::try_from(count).map_err(|_| DamageError::ResourceLimit)?;
    let total = resource
        .section_attempts
        .checked_add(count)
        .ok_or(DamageError::ResourceLimit)?;
    if total > 4_096 {
        return Err(DamageError::ResourceLimit);
    }
    resource.section_attempts = total;
    Ok(())
}

fn neutral_package(profile_version: u16) -> Result<&'static crate::recipe::RecipePackage> {
    static PACKAGES: OnceLock<std::result::Result<Vec<crate::recipe::RecipePackage>, DamageError>> =
        OnceLock::new();
    let packages = PACKAGES.get_or_init(|| {
        (1..=6)
            .map(|version| {
                let profile = profile_by_version(version).ok_or(DamageError::Profile)?;
                let raw = match profile.transport {
                    TransportFamily::Eh72Replicated
                    | TransportFamily::Eh72HierarchicalRepetition => {
                        build_eh_recipe_package(version)
                    }
                    TransportFamily::Rs255_191 => build_rs_decoder_recipe_package(version),
                }
                .map_err(|_| DamageError::Reconstruction)?;
                let row = units_resource_row(version)?;
                if observation_sha256(&raw) != row.package_sha256 {
                    return Err(DamageError::Reconstruction);
                }
                let package = decode_recipe_package(&raw, version)
                    .map_err(|_| DamageError::Reconstruction)?;
                if package.recipe_primitive_steps(30) != Some(row.primitive_steps)
                    || package.recipe_peak_scratch_bytes(30) != Some(row.peak_scratch_bytes)
                {
                    return Err(DamageError::Reconstruction);
                }
                Ok(package)
            })
            .collect()
    });
    packages
        .as_ref()
        .map_err(|error| *error)?
        .get(usize::from(profile_version.saturating_sub(1)))
        .ok_or(DamageError::Profile)
}

#[derive(Clone, Copy)]
struct UnitsResourceRow {
    package_sha256: &'static str,
    primitive_steps: u64,
    peak_scratch_bytes: u64,
    invocations_per_unit: u64,
}

fn units_resource_row(profile_version: u16) -> Result<UnitsResourceRow> {
    let (package_sha256, primitive_steps, peak_scratch_bytes, invocations_per_unit) =
        match profile_version {
            1 => (
                "f030732cd966fd9570149f6fd2d1befb5eed66319eb248b609693e868f977941",
                80_435,
                4_613,
                24,
            ),
            2 => (
                "cce1758613d7f10278533409e07103ae15162972fcf30030e17c233e39664011",
                80_435,
                4_613,
                24,
            ),
            3 => (
                "8c91ba74f9bbed97aed89191e8d8d30a9a0c4d32bd5ac98b63a4c19ed71fb0e7",
                80_435,
                4_613,
                24,
            ),
            4 => (
                "de237fcd9d53581710404bd8b00152cb68f50adef48e715fdd4572e786bae4b8",
                80_435,
                4_613,
                24,
            ),
            5 => (
                "2dd94f23f63bd4fbeb8d56565a9cc9a7e0a2054d3483e364cfb60e7751058e91",
                1_698_049,
                7_688,
                1,
            ),
            6 => (
                "1c05a1f57394d292487f46561492619358fe2d12e42e3a20194d5917f351e555",
                1_698_049,
                7_688,
                1,
            ),
            _ => return Err(DamageError::Profile),
        };
    Ok(UnitsResourceRow {
        package_sha256,
        primitive_steps,
        peak_scratch_bytes,
        invocations_per_unit,
    })
}

fn verify_damage_owner() -> Result<()> {
    static VERIFIED: OnceLock<std::result::Result<(), DamageError>> = OnceLock::new();
    *VERIFIED.get_or_init(|| {
        let raw = include_bytes!("../../../spec/damage-policy-v0.toml");
        let policy = load_damage_policy(raw).map_err(|_| DamageError::Reconstruction)?;
        let rows = &policy.obs_units_resource_profiles;
        if rows.len() != 6 {
            return Err(DamageError::Reconstruction);
        }
        for (ordinal, observed) in rows.iter().enumerate() {
            let version = u16::try_from(ordinal + 1).unwrap();
            let expected = units_resource_row(version)?;
            let profile = profile_by_version(version).ok_or(DamageError::Profile)?;
            if observed.0 != version
                || observed.1 != profile.id
                || observed.2 != expected.package_sha256
                || observed.3 != expected.primitive_steps
                || observed.4 != expected.peak_scratch_bytes
            {
                return Err(DamageError::Reconstruction);
            }
        }
        Ok(())
    })
}

fn charge_units_profile(
    resource: &mut ResourceProjection,
    row: UnitsResourceRow,
    unit_count: usize,
) -> Result<()> {
    let steps = row
        .primitive_steps
        .checked_mul(row.invocations_per_unit)
        .and_then(|value| value.checked_mul(unit_count as u64))
        .ok_or(DamageError::ResourceLimit)?;
    resource.primitive_steps = resource
        .primitive_steps
        .checked_add(steps)
        .ok_or(DamageError::ResourceLimit)?;
    resource.peak_scratch_bytes = resource.peak_scratch_bytes.max(row.peak_scratch_bytes);
    Ok(())
}

pub fn clean_resource_projection(core: &ManifestationCore) -> Result<ResourceProjection> {
    let package_raw =
        build_eh_recipe_package(core.profile.version).map_err(|_| DamageError::Reconstruction)?;
    let package = decode_recipe_package(&package_raw, core.profile.version)
        .map_err(|_| DamageError::Reconstruction)?;
    let route_recipe_ids = [
        101_u16, 102, 103, 104, 105, 106, 107, 30, 109, 110, 111, 112,
    ];
    let one_route = route_recipe_ids
        .iter()
        .try_fold(0_u64, |sum, id| {
            package
                .recipe_primitive_steps(*id)
                .and_then(|steps| sum.checked_add(steps.checked_mul(2)?))
        })
        .ok_or(DamageError::ResourceLimit)?;
    let transport = package
        .recipe_primitive_steps(30)
        .and_then(|steps| steps.checked_mul(24))
        .and_then(|steps| steps.checked_mul(core.units.len() as u64))
        .and_then(|steps| steps.checked_mul(4))
        .ok_or(DamageError::ResourceLimit)?;
    let primitive_steps = one_route
        .checked_mul(4)
        .and_then(|value| value.checked_add(transport))
        .ok_or(DamageError::ResourceLimit)?;
    let peak_scratch_bytes = route_recipe_ids
        .iter()
        .filter_map(|id| package.recipe_peak_scratch_bytes(*id))
        .max()
        .ok_or(DamageError::Reconstruction)?;
    Ok(ResourceProjection {
        section_attempts: core.sections.len() as u64,
        primitive_steps,
        peak_scratch_bytes,
    })
}

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct Coordinate {
    pub row: u32,
    pub column: u32,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ObsBits {
    pub count: usize,
    packed: Vec<u8>,
}

impl ObsBits {
    pub fn parse(raw: &[u8]) -> Result<Self> {
        if raw.len() < 5 {
            return Err(DamageError::Length);
        }
        let count = usize::try_from(u32::from_be_bytes(
            raw[..4].try_into().expect("four-byte prefix"),
        ))
        .map_err(|_| DamageError::Length)?;
        if count == 0 || count > MAX_RAW_BITS || raw.len() != 4 + count.div_ceil(8) {
            return Err(DamageError::Length);
        }
        let packed = raw[4..].to_vec();
        let used = count % 8;
        if used != 0
            && packed
                .last()
                .is_some_and(|byte| byte & ((1 << (8 - used)) - 1) != 0)
        {
            return Err(DamageError::Value);
        }
        Ok(Self { count, packed })
    }

    fn bit(&self, flat: usize) -> Result<u8> {
        if flat >= self.count {
            return Err(DamageError::Coordinate);
        }
        Ok((self.packed[flat / 8] >> (7 - flat % 8)) & 1)
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ObsMatrix {
    pub side: usize,
    pub values: Vec<u8>,
}

impl ObsMatrix {
    pub fn parse(raw: &[u8]) -> Result<Self> {
        if raw.len() < 3 {
            return Err(DamageError::Length);
        }
        let side = usize::from(u16::from_be_bytes([raw[0], raw[1]]));
        let count = side.checked_mul(side).ok_or(DamageError::ResourceLimit)?;
        if side == 0 || side > MAX_SIDE || count > MAX_RAW_BITS || raw.len() != 2 + count {
            return Err(DamageError::Length);
        }
        if raw[2..].iter().any(|value| *value > 2) {
            return Err(DamageError::Value);
        }
        Ok(Self {
            side,
            values: raw[2..].to_vec(),
        })
    }

    fn value(&self, row: usize, column: usize) -> Result<u8> {
        if row >= self.side || column >= self.side {
            return Err(DamageError::Coordinate);
        }
        Ok(self.values[row * self.side + column])
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UnitEntry {
    pub physical_unit_id: u32,
    pub bytes: Vec<u8>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ObsUnits {
    pub entries: Vec<UnitEntry>,
}

impl ObsUnits {
    pub fn parse(raw: &[u8]) -> Result<Self> {
        if raw.len() < 4 {
            return Err(DamageError::Length);
        }
        let count = usize::try_from(u32::from_be_bytes(
            raw[..4].try_into().expect("four-byte prefix"),
        ))
        .map_err(|_| DamageError::Length)?;
        if count > MAX_UNITS {
            return Err(DamageError::ResourceLimit);
        }
        let mut offset = 4_usize;
        let mut ids = BTreeSet::new();
        let mut entries = Vec::with_capacity(count);
        for _ in 0..count {
            let header_end = offset.checked_add(6).ok_or(DamageError::ResourceLimit)?;
            let header = raw.get(offset..header_end).ok_or(DamageError::Length)?;
            let physical_unit_id = u32::from_be_bytes(header[..4].try_into().unwrap());
            let length = usize::from(u16::from_be_bytes(header[4..].try_into().unwrap()));
            if physical_unit_id == 0 || !ids.insert(physical_unit_id) {
                return Err(DamageError::Duplicate);
            }
            let end = header_end
                .checked_add(length)
                .ok_or(DamageError::ResourceLimit)?;
            let bytes = raw
                .get(header_end..end)
                .ok_or(DamageError::Length)?
                .to_vec();
            entries.push(UnitEntry {
                physical_unit_id,
                bytes,
            });
            offset = end;
        }
        if offset != raw.len() {
            return Err(DamageError::Length);
        }
        Ok(Self { entries })
    }
}

pub fn serialize_obs_bits(bits: &[u8]) -> Result<Vec<u8>> {
    if bits.is_empty() || bits.len() > MAX_RAW_BITS || bits.iter().any(|bit| *bit > 1) {
        return Err(DamageError::Value);
    }
    let mut raw = u32::try_from(bits.len())
        .map_err(|_| DamageError::ResourceLimit)?
        .to_be_bytes()
        .to_vec();
    raw.resize(4 + bits.len().div_ceil(8), 0);
    for (index, bit) in bits.iter().copied().enumerate() {
        raw[4 + index / 8] |= bit << (7 - index % 8);
    }
    Ok(raw)
}

pub fn serialize_obs_matrix(side: usize, values: &[u8]) -> Result<Vec<u8>> {
    let count = side.checked_mul(side).ok_or(DamageError::ResourceLimit)?;
    if side == 0 || side > MAX_SIDE || count != values.len() || values.iter().any(|v| *v > 2) {
        return Err(DamageError::Value);
    }
    let mut raw = u16::try_from(side)
        .map_err(|_| DamageError::ResourceLimit)?
        .to_be_bytes()
        .to_vec();
    raw.extend_from_slice(values);
    Ok(raw)
}

pub fn serialize_obs_units(entries: &[UnitEntry]) -> Result<Vec<u8>> {
    if entries.len() > MAX_UNITS {
        return Err(DamageError::ResourceLimit);
    }
    let mut ids = BTreeSet::new();
    let mut raw = u32::try_from(entries.len())
        .map_err(|_| DamageError::ResourceLimit)?
        .to_be_bytes()
        .to_vec();
    for entry in entries {
        if entry.physical_unit_id == 0 || !ids.insert(entry.physical_unit_id) {
            return Err(DamageError::Duplicate);
        }
        raw.extend_from_slice(&entry.physical_unit_id.to_be_bytes());
        raw.extend_from_slice(
            &u16::try_from(entry.bytes.len())
                .map_err(|_| DamageError::ResourceLimit)?
                .to_be_bytes(),
        );
        raw.extend_from_slice(&entry.bytes);
    }
    Ok(raw)
}

pub fn observation_sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

pub fn section_attempt_boundary_kat() -> Result<(Vec<u8>, String)> {
    // Feed 4,097 independently valid and byte-distinct checked envelopes to
    // the real section aggregation entry point.  The owning global attempt
    // counter admits exactly the first 4,096 and rejects ordinal 4,096 before
    // allowing any partial output from the over-limit invocation.
    let mut resource = ResourceProjection::default();
    let mut checked = 0_u64;
    let mut rejected = None;
    for ordinal in 0_u32..4_097 {
        let envelope = encode_section(&SectionEnvelope {
            section_id: 1,
            section_type: SECTION_INVENTORY,
            section_version: 0,
            closure_class: CLOSURE_M2_REQUIRED,
            check_id: CHECK_CRC32C,
            dependencies: Vec::new(),
            payload: ordinal.to_be_bytes().to_vec(),
        })
        .map_err(|_| DamageError::Reconstruction)?;
        let witness = SectionWitness {
            envelope,
            all_units_verified: true,
        };
        if let Err(error) = charge_section_attempts(&mut resource, 1) {
            if error != DamageError::ResourceLimit {
                return Err(error);
            }
            rejected = Some(u64::from(ordinal));
            break;
        }
        aggregate_section_witnesses(std::slice::from_ref(&witness))
            .map_err(|_| DamageError::Reconstruction)?;
        checked += 1;
    }
    if checked != 4_096 || rejected != Some(4_096) || resource.section_attempts != checked {
        return Err(DamageError::Reconstruction);
    }
    let value = ManifestValue::Object(BTreeMap::from([
        (
            "schema".to_owned(),
            ManifestValue::String("golden-board.m2-boundary-kat-result/v0".to_owned()),
        ),
        (
            "kat_id".to_owned(),
            ManifestValue::String("section-attempt-ceiling-plus-one".to_owned()),
        ),
        (
            "artifact_state".to_owned(),
            ManifestValue::String("resource-limit".to_owned()),
        ),
        ("candidates_present".to_owned(), ManifestValue::U64(4_097)),
        ("candidates_checked".to_owned(), ManifestValue::U64(checked)),
        (
            "rejected_candidate_ordinal".to_owned(),
            ManifestValue::U64(rejected.unwrap()),
        ),
        (
            "section_output_sha256".to_owned(),
            ManifestValue::String("0".repeat(64)),
        ),
    ]));
    let raw = serialize_manifest(&value).map_err(|_| DamageError::Reconstruction)?;
    let sha256 = observation_sha256(&raw);
    Ok((raw, sha256))
}

fn observed_coordinate(
    side: usize,
    transform: u8,
    row: usize,
    column: usize,
) -> Result<(usize, usize)> {
    if side == 0 || row >= side || column >= side || transform > 7 {
        return Err(DamageError::Coordinate);
    }
    let last = side - 1;
    Ok(match transform {
        0 => (row, column),
        1 => (last - column, row),
        2 => (last - row, last - column),
        3 => (column, last - row),
        4 => (row, last - column),
        5 => (last - column, last - row),
        6 => (last - row, column),
        7 => (column, row),
        _ => unreachable!(),
    })
}

pub fn transformed_clean_bits(
    canonical: &[u8],
    side: usize,
    hypothesis: EntryHypothesis,
) -> Result<Vec<u8>> {
    if canonical.len() != side.checked_mul(side).ok_or(DamageError::ResourceLimit)?
        || canonical.iter().any(|bit| *bit > 1)
        || hypothesis.polarity > 1
    {
        return Err(DamageError::Value);
    }
    let mut observed = vec![0; canonical.len()];
    for row in 0..side {
        for column in 0..side {
            let (observed_row, observed_column) =
                observed_coordinate(side, hypothesis.transform, row, column)?;
            observed[observed_row * side + observed_column] =
                canonical[row * side + column] ^ hypothesis.polarity;
        }
    }
    Ok(observed)
}

pub(crate) struct CounterWords {
    domain: &'static [u8],
    seed: u64,
    counter: u64,
    words: [u64; 4],
    next: usize,
    attempts: u64,
    retry_max: u64,
}

impl CounterWords {
    pub(crate) fn new(domain: &'static [u8], seed: u64, population: usize) -> Result<Self> {
        if population == 0 || population > MAX_RAW_BITS {
            return Err(DamageError::SamplePopulation);
        }
        let retry_max = u64::try_from(population)
            .map_err(|_| DamageError::SampleResource)?
            .checked_mul(64)
            .and_then(|value| value.checked_add(1024))
            .ok_or(DamageError::SampleResource)?;
        Ok(Self {
            domain,
            seed,
            counter: 0,
            words: [0; 4],
            next: 4,
            attempts: 0,
            retry_max,
        })
    }

    fn word(&mut self) -> Result<u64> {
        if self.attempts >= self.retry_max {
            return Err(DamageError::SampleResource);
        }
        if self.next == 4 {
            let mut hash = Sha256::new();
            hash.update(self.domain);
            hash.update(self.seed.to_be_bytes());
            hash.update(self.counter.to_be_bytes());
            let digest = hash.finalize();
            for index in 0..4 {
                self.words[index] =
                    u64::from_be_bytes(digest[index * 8..(index + 1) * 8].try_into().unwrap());
            }
            self.counter = self
                .counter
                .checked_add(1)
                .ok_or(DamageError::SampleResource)?;
            self.next = 0;
        }
        let word = self.words[self.next];
        self.next += 1;
        self.attempts += 1;
        Ok(word)
    }

    pub(crate) fn unbiased(&mut self, population: usize) -> Result<usize> {
        if population == 0 {
            return Err(DamageError::SamplePopulation);
        }
        let population = population as u64;
        let remainder = ((u128::from(u64::MAX) + 1) % u128::from(population)) as u64;
        let limit = (u128::from(u64::MAX) + 1) - u128::from(remainder);
        loop {
            let word = self.word()?;
            if u128::from(word) < limit {
                return usize::try_from(word % population).map_err(|_| DamageError::SampleResource);
            }
        }
    }
}

pub fn sample_without_replacement(
    population: usize,
    count: usize,
    seed: u64,
) -> Result<Vec<usize>> {
    if count > population || population > MAX_RAW_BITS {
        return Err(DamageError::SamplePopulation);
    }
    if count == 0 {
        return Ok(Vec::new());
    }
    let mut stream = CounterWords::new(DAMAGE_DOMAIN, seed, population)?;
    let mut selected = BTreeSet::new();
    let mut output = Vec::with_capacity(count);
    while output.len() < count {
        let index = stream.unbiased(population)?;
        if selected.insert(index) {
            output.push(index);
        }
    }
    Ok(output)
}

pub fn d2_square_side(interior_side: usize) -> usize {
    32.max(interior_side / 32)
}

pub fn d2_placements(interior_side: usize) -> Result<Vec<Coordinate>> {
    let square = d2_square_side(interior_side);
    if square > interior_side {
        return Err(DamageError::SamplePopulation);
    }
    let last = interior_side - square;
    let axes = [0_usize, last / 2, last];
    let mut placements = Vec::with_capacity(256);
    let mut seen = BTreeSet::new();
    for row in axes {
        for column in axes {
            let coordinate = Coordinate {
                row: row as u32,
                column: column as u32,
            };
            if seen.insert(coordinate) {
                placements.push(coordinate);
            }
        }
    }
    let width = last + 1;
    let population = width
        .checked_mul(width)
        .ok_or(DamageError::SampleResource)?;
    let mut stream = CounterWords::new(DAMAGE_DOMAIN, 5_134_751_402_299_490_304, population)?;
    while placements.len() < 256 {
        let flat = stream.unbiased(population)?;
        let coordinate = Coordinate {
            row: (flat / width) as u32,
            column: (flat % width) as u32,
        };
        if seen.insert(coordinate) {
            placements.push(coordinate);
        }
    }
    if placements.len() != 256 {
        return Err(DamageError::SamplePopulation);
    }
    Ok(placements)
}

pub fn d3_weight(interior_cells: usize) -> usize {
    64.max(interior_cells.div_ceil(2000))
}

fn interior_coordinate(core: &ManifestationCore, flat: usize) -> Result<Coordinate> {
    let interior = usize::from(core.mapping.interior_side);
    if flat >= interior * interior {
        return Err(DamageError::Coordinate);
    }
    Ok(Coordinate {
        row: u32::try_from(flat / interior + usize::from(core.shell_width))
            .map_err(|_| DamageError::Coordinate)?,
        column: u32::try_from(flat % interior + usize::from(core.shell_width))
            .map_err(|_| DamageError::Coordinate)?,
    })
}

fn d3_population(core: &ManifestationCore, stratum: usize, seed: u64) -> Result<Vec<Coordinate>> {
    let interior = usize::from(core.mapping.interior_side);
    match stratum {
        0 => (0..interior * interior)
            .map(|flat| interior_coordinate(core, flat))
            .collect(),
        1 => {
            let window = 32.max(interior / 8);
            let origins = interior
                .checked_sub(window)
                .and_then(|value| value.checked_add(1))
                .ok_or(DamageError::SamplePopulation)?;
            let mut stream = CounterWords::new(WINDOW_DOMAIN, seed, origins)?;
            let row = stream.unbiased(origins)?;
            let column = stream.unbiased(origins)?;
            let mut population = Vec::with_capacity(window * window);
            for local_row in 0..window {
                for local_column in 0..window {
                    population.push(Coordinate {
                        row: (row + local_row + usize::from(core.shell_width)) as u32,
                        column: (column + local_column + usize::from(core.shell_width)) as u32,
                    });
                }
            }
            Ok(population)
        }
        2 => {
            let required = core
                .sections
                .iter()
                .filter(|section| section.closure_class == CLOSURE_M2_REQUIRED)
                .map(|section| section.section_id)
                .collect::<BTreeSet<_>>();
            let required_units = core
                .units
                .iter()
                .filter(|unit| required.contains(&unit.section_id))
                .map(|unit| unit.physical_unit_id)
                .collect::<BTreeSet<_>>();
            let mut result = BTreeSet::new();
            let side = usize::from(core.side);
            for (flat, owner) in core.cell_owners.iter().enumerate() {
                if owner.kind == 4 && required_units.contains(&owner.owner_id) {
                    result.insert(Coordinate {
                        row: (flat / side) as u32,
                        column: (flat % side) as u32,
                    });
                }
            }
            Ok(result.into_iter().collect())
        }
        3 => {
            let side = usize::from(core.side);
            let width = usize::from(core.shell_width);
            let mut result = BTreeSet::new();
            for (flat, owner) in core.cell_owners.iter().enumerate() {
                if owner.kind != 4 {
                    continue;
                }
                let row = flat / side;
                let column = flat % side;
                let offset = owner.bit_offset as usize;
                let local_row = row - width;
                let local_column = column - width;
                if offset < 16
                    || offset + 16 >= UNIT_BITS
                    || offset % 8 == 0
                    || offset % 8 == 7
                    || matches!(local_row % 16, 0 | 15)
                    || matches!(local_column % 16, 0 | 15)
                {
                    result.insert(Coordinate {
                        row: row as u32,
                        column: column as u32,
                    });
                }
            }
            Ok(result.into_iter().collect())
        }
        _ => Err(DamageError::Operator),
    }
}

pub fn d3_coordinates(
    core: &ManifestationCore,
    seed: u64,
    extra: usize,
) -> Result<Vec<Coordinate>> {
    let ordinal = seed
        .checked_sub(5_134_751_402_299_490_304)
        .ok_or(DamageError::Operator)?;
    if ordinal >= 128 {
        return Err(DamageError::Operator);
    }
    let population = d3_population(core, (ordinal / 32) as usize, seed)?;
    let count = d3_weight(
        usize::try_from(core.mapping.population).map_err(|_| DamageError::ResourceLimit)?,
    )
    .checked_add(extra)
    .ok_or(DamageError::ResourceLimit)?;
    if population.len() < count {
        return Err(DamageError::SamplePopulation);
    }
    sample_without_replacement(population.len(), count, seed)?
        .into_iter()
        .map(|index| {
            population
                .get(index)
                .copied()
                .ok_or(DamageError::Coordinate)
        })
        .collect()
}

pub fn clean_unit_entries(core: &ManifestationCore) -> Vec<UnitEntry> {
    core.units
        .iter()
        .map(|unit| UnitEntry {
            physical_unit_id: unit.physical_unit_id,
            bytes: unit.encoded.to_vec(),
        })
        .collect()
}

pub fn d5_permutations(unit_count: usize) -> Result<Vec<Vec<usize>>> {
    if unit_count == 0 || unit_count > MAX_UNITS {
        return Err(DamageError::Operator);
    }
    let ascending = (0..unit_count).collect::<Vec<_>>();
    let mut descending = ascending.clone();
    descending.reverse();
    let mut rotate_left = ascending.clone();
    rotate_left.rotate_left(1);
    let even_then_odd = (0..unit_count)
        .filter(|index| index % 2 == 0)
        .chain((0..unit_count).filter(|index| index % 2 == 1))
        .collect();
    let odd_then_even = (0..unit_count)
        .filter(|index| index % 2 == 1)
        .chain((0..unit_count).filter(|index| index % 2 == 0))
        .collect();
    let mut output = vec![
        ascending,
        descending,
        rotate_left,
        even_then_odd,
        odd_then_even,
    ];
    for ordinal in 0..16_u64 {
        let seed = 5_134_751_402_299_490_560_u64
            .checked_add(ordinal)
            .ok_or(DamageError::SampleResource)?;
        let mut stream = CounterWords::new(DAMAGE_DOMAIN, seed, unit_count)?;
        let mut permutation = (0..unit_count).collect::<Vec<_>>();
        // Exact zero-based Durstenfeld: descending i and uniform j in 0..=i.
        for index in (1..unit_count).rev() {
            let selected = stream.unbiased(index + 1)?;
            permutation.swap(index, selected);
        }
        output.push(permutation);
    }
    Ok(output)
}

pub fn permuted_unit_observation(
    core: &ManifestationCore,
    permutation: &[usize],
) -> Result<Vec<u8>> {
    if permutation.len() != core.units.len()
        || permutation.iter().copied().collect::<BTreeSet<_>>().len() != core.units.len()
        || permutation.iter().any(|index| *index >= core.units.len())
    {
        return Err(DamageError::Operator);
    }
    let clean = clean_unit_entries(core);
    let entries = permutation
        .iter()
        .map(|index| clean[*index].clone())
        .collect::<Vec<_>>();
    serialize_obs_units(&entries)
}

pub fn omitted_unit_observation(core: &ManifestationCore, omitted: &[u32]) -> Result<Vec<u8>> {
    if omitted.is_empty()
        || omitted.len() > core.units.len()
        || omitted
            .iter()
            .any(|id| *id == 0 || *id as usize > core.units.len())
        || omitted.iter().copied().collect::<BTreeSet<_>>().len() != omitted.len()
    {
        return Err(DamageError::Operator);
    }
    let omitted = omitted.iter().copied().collect::<BTreeSet<_>>();
    serialize_obs_units(
        &clean_unit_entries(core)
            .into_iter()
            .filter(|entry| !omitted.contains(&entry.physical_unit_id))
            .collect::<Vec<_>>(),
    )
}

fn clean_common(core: &ManifestationCore, unit_id: u32) -> Result<[u8; 191]> {
    let unit = core
        .units
        .get(usize::try_from(unit_id).map_err(|_| DamageError::Operator)? - 1)
        .ok_or(DamageError::Operator)?;
    decode_eh_unit(
        &EhObservation {
            encoded: unit.encoded,
            erasures: Vec::new(),
        },
        core.profile.version,
    )
    .map(|decoded| decoded.common)
    .map_err(|_| DamageError::Reconstruction)
}

fn recompute_common_local_check(common: &mut [u8; 191]) {
    let mut preimage = Vec::with_capacity(LOCAL_CHECK_DOMAIN.len() + 187);
    preimage.extend_from_slice(&LOCAL_CHECK_DOMAIN);
    preimage.extend_from_slice(&common[..187]);
    common[187..].copy_from_slice(&crc32c(&preimage).to_be_bytes());
}

pub fn cross_profile_splice(
    core: &ManifestationCore,
    source_profile_version: u16,
) -> Result<Vec<u8>> {
    if source_profile_version == core.profile.version
        || profile_by_version(source_profile_version).is_none()
    {
        return Err(DamageError::Operator);
    }
    let mut common = clean_common(core, 1)?;
    common[..2].copy_from_slice(&source_profile_version.to_be_bytes());
    recompute_common_local_check(&mut common);
    let source_profile = profile_by_version(source_profile_version).unwrap();
    let bytes = match source_profile.transport {
        TransportFamily::Eh72Replicated | TransportFamily::Eh72HierarchicalRepetition => {
            encode_eh_unit(&common).to_vec()
        }
        TransportFamily::Rs255_191 => encode_rs255_191(&common).to_vec(),
    };
    let mut entries = clean_unit_entries(core);
    entries[0].bytes = bytes;
    serialize_obs_units(&entries)
}

pub fn local_check_mutant(core: &ManifestationCore, normal_reflection: bool) -> Result<Vec<u8>> {
    let mut common = clean_common(core, 1)?;
    if normal_reflection {
        let mut register = 0xffff_ffff_u32;
        let mut preimage = Vec::with_capacity(LOCAL_CHECK_DOMAIN.len() + 187);
        preimage.extend_from_slice(&LOCAL_CHECK_DOMAIN);
        preimage.extend_from_slice(&common[..187]);
        for byte in preimage {
            register ^= u32::from(byte) << 24;
            for _ in 0..8 {
                register = if register & 0x8000_0000 != 0 {
                    (register << 1) ^ 0x1edc_6f41
                } else {
                    register << 1
                };
            }
        }
        common[187..].copy_from_slice(&(register ^ 0xffff_ffff).to_be_bytes());
    } else {
        common[187..].reverse();
    }
    let mut entries = clean_unit_entries(core);
    entries[0].bytes = encode_eh_unit(&common).to_vec();
    serialize_obs_units(&entries)
}

fn mutant_set_bit(word: &mut [u8; 9], position: usize, value: u8, lsb_packing: bool) {
    let index = position - 1;
    let shift = if lsb_packing {
        index % 8
    } else {
        7 - index % 8
    };
    let mask = 1 << shift;
    word[index / 8] = (word[index / 8] & !mask) | (value << shift);
}

fn mutant_bit(word: &[u8; 9], position: usize, lsb_packing: bool) -> u8 {
    let index = position - 1;
    let shift = if lsb_packing {
        index % 8
    } else {
        7 - index % 8
    };
    (word[index / 8] >> shift) & 1
}

pub(crate) fn encode_eh_mutant_chunk(data: &[u8; 8], ordinal: u8) -> [u8; 9] {
    let (reserved, lsb_input, lsb_output) = match ordinal {
        0 => (&[2_usize, 3, 5, 9, 17, 33, 65][..], false, false),
        1 => (&[1_usize, 2, 4, 8, 16, 32, 64][..], false, false),
        2 => (&[1_usize, 2, 4, 8, 16, 32, 64][..], true, true),
        _ => unreachable!(),
    };
    let mut word = [0_u8; 9];
    let mut data_bit = 0_usize;
    for position in 1..=71 {
        if reserved.contains(&position) {
            continue;
        }
        let value = if lsb_input {
            (data[data_bit / 8] >> (data_bit % 8)) & 1
        } else {
            (data[data_bit / 8] >> (7 - data_bit % 8)) & 1
        };
        mutant_set_bit(&mut word, position, value, lsb_output);
        data_bit += 1;
    }
    debug_assert_eq!(data_bit, 64);
    if ordinal == 1 {
        let overall = (1..=71).fold(0, |value, position| {
            value ^ mutant_bit(&word, position, false)
        });
        mutant_set_bit(&mut word, 72, overall, false);
        for mask in [1_usize, 2, 4, 8, 16, 32, 64] {
            let value = (1..=71)
                .filter(|position| *position != mask && *position & mask != 0)
                .fold(mutant_bit(&word, 72, false), |value, position| {
                    value ^ mutant_bit(&word, position, false)
                });
            mutant_set_bit(&mut word, mask, value, false);
        }
    } else {
        for mask in [1_usize, 2, 4, 8, 16, 32, 64] {
            let reserved_position = if ordinal == 0 { mask + 1 } else { mask };
            let value = (1..=71)
                .filter(|position| {
                    *position != reserved_position
                        && if ordinal == 0 {
                            (*position - 1) & mask != 0
                        } else {
                            *position & mask != 0
                        }
                })
                .fold(0, |value, position| {
                    value ^ mutant_bit(&word, position, lsb_output)
                });
            mutant_set_bit(&mut word, reserved_position, value, lsb_output);
        }
        let overall = (1..=71).fold(0, |value, position| {
            value ^ mutant_bit(&word, position, lsb_output)
        });
        mutant_set_bit(&mut word, 72, overall, lsb_output);
    }
    word
}

pub fn code_mutant(core: &ManifestationCore, ordinal: u8) -> Result<Vec<u8>> {
    if ordinal > 2 {
        return Err(DamageError::Operator);
    }
    let common = clean_common(core, 1)?;
    let mut plain = [0_u8; 192];
    plain[..191].copy_from_slice(&common);
    let mut encoded = [0_u8; EH_UNIT_BYTES];
    for chunk in 0..24 {
        let data: [u8; 8] = plain[chunk * 8..(chunk + 1) * 8].try_into().unwrap();
        encoded[chunk * 9..(chunk + 1) * 9]
            .copy_from_slice(&encode_eh_mutant_chunk(&data, ordinal));
    }
    let mut entries = clean_unit_entries(core);
    entries[0].bytes = encoded.to_vec();
    serialize_obs_units(&entries)
}

fn replace_section_copy(
    core: &ManifestationCore,
    section_id: u32,
    semantic_copy_id: u16,
    envelope: &[u8],
    structurally_valid: bool,
) -> Result<Vec<u8>> {
    let section = core
        .sections
        .iter()
        .find(|section| section.section_id == section_id)
        .ok_or(DamageError::Operator)?;
    let blocks = if structurally_valid {
        fragment_envelope(
            core.profile.version,
            section.section_id,
            semantic_copy_id,
            section.section_type,
            section.section_version,
            envelope,
        )
        .map_err(|_| DamageError::Operator)?
    } else {
        let count = envelope.len().div_ceil(COMMON_PAYLOAD_BYTES);
        (0..count)
            .map(|fragment| {
                let start = fragment * COMMON_PAYLOAD_BYTES;
                let end = envelope.len().min(start + COMMON_PAYLOAD_BYTES);
                encode_common_block(&crate::CommonBlock {
                    profile_version: core.profile.version,
                    section_id,
                    semantic_copy_id,
                    section_type: section.section_type,
                    section_version: section.section_version,
                    fragment_index: fragment as u16,
                    fragment_count: count as u16,
                    section_envelope_length: envelope.len() as u32,
                    payload: envelope[start..end].to_vec(),
                })
                .map_err(|_| DamageError::Operator)
            })
            .collect::<Result<Vec<_>>>()?
    };
    let mut entries = clean_unit_entries(core);
    let matching = core
        .units
        .iter()
        .filter(|unit| unit.section_id == section_id && unit.semantic_copy_id == semantic_copy_id)
        .collect::<Vec<_>>();
    if matching.len() != blocks.len() {
        return Err(DamageError::Reconstruction);
    }
    for (unit, block) in matching.into_iter().zip(blocks) {
        entries[unit.physical_unit_id as usize - 1].bytes = encode_eh_unit(&block).to_vec();
    }
    serialize_obs_units(&entries)
}

pub fn section_check_mutant(core: &ManifestationCore, wrong_check_id: bool) -> Result<Vec<u8>> {
    let section = core
        .sections
        .iter()
        .find(|section| section.section_id != 1 && section.closure_class == CLOSURE_M2_REQUIRED)
        .ok_or(DamageError::Operator)?;
    let mut envelope = section
        .envelope()
        .map_err(|_| DamageError::Reconstruction)?;
    if wrong_check_id {
        envelope[11] = if envelope[11] == 1 { 2 } else { 1 };
    } else {
        let width = if envelope[11] == 1 { 4 } else { 8 };
        let length = envelope.len();
        envelope[length - width..].reverse();
    }
    replace_section_copy(core, section.section_id, 0, &envelope, false)
}

pub fn valid_copy_conflict(core: &ManifestationCore) -> Result<Vec<u8>> {
    let section = core
        .sections
        .iter()
        .find(|section| section.section_id != 1 && section.closure_class == CLOSURE_M2_REQUIRED)
        .ok_or(DamageError::Operator)?;
    if section.payload.is_empty() {
        return Err(DamageError::Operator);
    }
    let mut mutated = section.clone();
    mutated.payload[0] ^= 1;
    let envelope = mutated.envelope().map_err(|_| DamageError::Operator)?;
    replace_section_copy(core, section.section_id, 0, &envelope, true)
}

pub fn mapping_mutant(core: &ManifestationCore, ordinal: u8) -> Result<Vec<u8>> {
    if ordinal > 2 {
        return Err(DamageError::Operator);
    }
    let mut bits = core.carrier_bits.clone();
    let population = core.mapping.population;
    let interior = u64::from(core.mapping.interior_side);
    for unit in &core.units {
        for bit_offset in 0..UNIT_BITS {
            let logical = unit.logical_bit_first + bit_offset as u64;
            let physical = match ordinal {
                0 => logical,
                1 => {
                    (core.mapping.multiplier * logical + (core.mapping.offset + 1) % population)
                        % population
                }
                2 => ((2 * interior + 1) * logical + core.mapping.offset) % population,
                _ => unreachable!(),
            };
            let (row, column) = core
                .mapping
                .matrix_cell(physical)
                .map_err(|_| DamageError::Coordinate)?;
            let value = (unit.encoded[bit_offset / 8] >> (7 - bit_offset % 8)) & 1;
            bits[usize::from(row) * usize::from(core.side) + usize::from(column)] = value;
        }
    }
    serialize_obs_bits(&bits)
}

pub fn route_conflict(core: &ManifestationCore, alternate: &ManifestationCore) -> Result<Vec<u8>> {
    if core.profile.version == alternate.profile.version
        || core.profile.transport != alternate.profile.transport
        || core.profile.section_check_id != alternate.profile.section_check_id
        || core.profile.required_copy_count == alternate.profile.required_copy_count
    {
        return Err(DamageError::Operator);
    }
    let source = &alternate.routes.sectors[0];
    let prefix =
        usize::try_from(source.route_prefix_cells).map_err(|_| DamageError::ResourceLimit)?;
    let target_prefix = usize::try_from(core.routes.sectors[0].route_prefix_cells)
        .map_err(|_| DamageError::ResourceLimit)?;
    if prefix != target_prefix {
        return Err(DamageError::Operator);
    }
    let mut bits = core.carrier_bits.clone();
    for bit in 0..prefix {
        let (row, column) = sector_cell_at(
            usize::from(core.side),
            usize::from(core.shell_width),
            0,
            bit,
        )
        .map_err(|_| DamageError::Coordinate)?;
        bits[row * usize::from(core.side) + column] = source.bits[bit];
    }
    serialize_obs_bits(&bits)
}

pub fn missing_unit_one_beyond(core: &ManifestationCore) -> Result<(Vec<u32>, Vec<u8>)> {
    let section_id = core
        .sections
        .iter()
        .find(|section| section.section_id != 1 && section.closure_class == CLOSURE_M2_REQUIRED)
        .map(|section| section.section_id)
        .ok_or(DamageError::Operator)?;
    let omitted = core
        .units
        .iter()
        .filter(|unit| unit.section_id == section_id && unit.fragment_index == 0)
        .map(|unit| unit.physical_unit_id)
        .take(2)
        .collect::<Vec<_>>();
    if omitted.len() != 2 {
        return Err(DamageError::Operator);
    }
    let raw = omitted_unit_observation(core, &omitted)?;
    Ok((omitted, raw))
}

pub fn d2_one_beyond(core: &ManifestationCore, placement: Coordinate) -> Result<Vec<u8>> {
    let side = d2_square_side(usize::from(core.mapping.interior_side)) + 1;
    let maximum = usize::from(core.mapping.interior_side) - side;
    erase_square(
        core,
        Coordinate {
            row: placement.row.min(maximum as u32),
            column: placement.column.min(maximum as u32),
        },
        side,
    )
}

pub fn algebraic_one_beyond(
    core: &ManifestationCore,
    errors: usize,
    erasures: usize,
) -> Result<Vec<u8>> {
    if 2 * errors + erasures != 4 || errors + erasures > EH_CODEWORD_BITS {
        return Err(DamageError::Operator);
    }
    let mut values = core.carrier_bits.clone();
    let unit = core.units.first().ok_or(DamageError::Operator)?;
    for position in 0..erasures + errors {
        let physical = core
            .mapping
            .forward(unit.logical_bit_first + position as u64)
            .map_err(|_| DamageError::Coordinate)?;
        let (row, column) = core
            .mapping
            .matrix_cell(physical)
            .map_err(|_| DamageError::Coordinate)?;
        let flat = usize::from(row) * usize::from(core.side) + usize::from(column);
        if position < erasures {
            values[flat] = 2;
        } else {
            values[flat] ^= 1;
        }
    }
    serialize_obs_matrix(usize::from(core.side), &values)
}

pub fn resource_route_one_beyond(core: &ManifestationCore, scratch: bool) -> Result<Vec<u8>> {
    let route = &core.routes.sectors[0];
    let prefix_bytes =
        usize::try_from(route.route_prefix_cells).map_err(|_| DamageError::ResourceLimit)? / 8;
    let mut raw = vec![0_u8; prefix_bytes];
    for bit in 0..prefix_bytes * 8 {
        raw[bit / 8] |= route.bits[bit] << (7 - bit % 8);
    }
    let mut offset = 64_usize;
    let mut package_offset = None;
    while offset < raw.len() {
        let header = raw
            .get(offset..offset + 8)
            .ok_or(DamageError::Reconstruction)?;
        let length = usize::try_from(u32::from_be_bytes(header[4..8].try_into().unwrap()))
            .map_err(|_| DamageError::ResourceLimit)?;
        if header[1] == 5 {
            package_offset = Some(offset + 8);
            break;
        }
        offset = offset
            .checked_add(8 + length)
            .ok_or(DamageError::ResourceLimit)?;
    }
    let package = package_offset.ok_or(DamageError::Reconstruction)?;
    if scratch {
        raw[package + 44..package + 48].copy_from_slice(&16_777_217_u32.to_be_bytes());
    } else {
        raw[package + 36..package + 44].copy_from_slice(&268_435_457_u64.to_be_bytes());
    }
    let mut bits = core.carrier_bits.clone();
    for bit in 0..raw.len() * 8 {
        let (row, column) = sector_cell_at(
            usize::from(core.side),
            usize::from(core.shell_width),
            0,
            bit,
        )
        .map_err(|_| DamageError::Coordinate)?;
        bits[row * usize::from(core.side) + column] = (raw[bit / 8] >> (7 - bit % 8)) & 1;
    }
    serialize_obs_bits(&bits)
}

pub fn geometry_one_beyond() -> Vec<u8> {
    let count = 2_056_u32 * 2_056;
    let mut raw = count.to_be_bytes().to_vec();
    raw.resize(4 + count as usize / 8, 0);
    raw
}

pub fn erase_square(
    core: &ManifestationCore,
    top_left: Coordinate,
    square: usize,
) -> Result<Vec<u8>> {
    let mut values = core.carrier_bits.clone();
    let row = usize::try_from(top_left.row).map_err(|_| DamageError::Coordinate)?;
    let column = usize::try_from(top_left.column).map_err(|_| DamageError::Coordinate)?;
    let width = usize::from(core.shell_width);
    let interior = usize::from(core.mapping.interior_side);
    if row > interior.saturating_sub(square) || column > interior.saturating_sub(square) {
        return Err(DamageError::Coordinate);
    }
    for local_row in row..row + square {
        for local_column in column..column + square {
            let matrix_row = local_row + width;
            let matrix_column = local_column + width;
            values[matrix_row * usize::from(core.side) + matrix_column] = 2;
        }
    }
    serialize_obs_matrix(usize::from(core.side), &values)
}

pub fn substitute_coordinates(
    core: &ManifestationCore,
    coordinates: &[Coordinate],
) -> Result<Vec<u8>> {
    if coordinates.len() > MAX_RAW_BITS {
        return Err(DamageError::ResourceLimit);
    }
    let mut values = core.carrier_bits.clone();
    let mut seen = BTreeSet::new();
    let side = usize::from(core.side);
    for coordinate in coordinates {
        if !seen.insert(*coordinate) {
            return Err(DamageError::Duplicate);
        }
        let row = usize::try_from(coordinate.row).map_err(|_| DamageError::Coordinate)?;
        let column = usize::try_from(coordinate.column).map_err(|_| DamageError::Coordinate)?;
        if row >= side || column >= side {
            return Err(DamageError::Coordinate);
        }
        values[row * side + column] ^= 1;
    }
    serialize_obs_matrix(side, &values)
}

pub fn erase_shell_sector(
    core: &ManifestationCore,
    sector: u8,
    unit_id: Option<u32>,
) -> Result<Vec<u8>> {
    if sector > 3 || unit_id.is_some_and(|id| id == 0 || id as usize > core.units.len()) {
        return Err(DamageError::Operator);
    }
    let side = usize::from(core.side);
    let width = usize::from(core.shell_width);
    let mut values = core.carrier_bits.clone();
    let sector_cells = width
        .checked_mul(side - width)
        .ok_or(DamageError::ResourceLimit)?;
    for index in 0..sector_cells {
        let (row, column) =
            sector_cell_at(side, width, sector, index).map_err(|_| DamageError::Coordinate)?;
        values[row * side + column] = 2;
    }
    if let Some(unit_id) = unit_id {
        for (flat, owner) in core.cell_owners.iter().enumerate() {
            if owner.kind == 4 && owner.owner_id == unit_id {
                values[flat] = 2;
            }
        }
    }
    serialize_obs_matrix(side, &values)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FragmentState {
    Verified,
    Recovered,
    Missing,
    Corrupt,
    Ambiguous,
    Unknown,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SectionState {
    Verified,
    Recovered,
    Incomplete,
    Corrupt,
    Ambiguous,
    Unknown,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ArtifactState {
    Exact,
    Degraded,
    Failure,
    Ambiguous,
    ResourceLimit,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SectionResult {
    pub section_id: u32,
    pub state: SectionState,
    pub envelope: Option<Vec<u8>>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RecoveryResult {
    pub profile_version: Option<u16>,
    pub inventory_established: bool,
    pub resource: ResourceProjection,
    pub artifact_state: ArtifactState,
    pub sections: Vec<SectionResult>,
    pub fragments: Vec<FragmentDiagnostic>,
    pub accepted_hypotheses: Vec<AcceptedHypothesis>,
}

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct AcceptedHypothesis {
    pub transform_id: u8,
    pub polarity_id: u8,
    pub sector_id: u8,
    pub profile_version: u16,
    pub mapping_sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FragmentDiagnostic {
    pub input_id: u32,
    pub profile_version: Option<u16>,
    pub section_id: u32,
    pub semantic_copy_id: u16,
    pub fragment_index: u16,
    pub state: FragmentState,
    pub common_block_sha256: String,
}

#[derive(Clone, Debug)]
struct PhysicalObservation {
    id: u32,
    present: bool,
    common: Option<[u8; 191]>,
    quality: Option<RecoveryQuality>,
}

#[derive(Clone)]
struct CachedEhUnit {
    encoded: [u8; EH_UNIT_BYTES],
    erasures: Vec<EhErasure>,
    decoded: Option<DecodedUnit>,
}

/// Stateful only for pure decode memoization.  Every result remains a function
/// of the serialized observation; cache entries are used only after exact byte
/// and erasure equality for the same discovered profile and physical unit ID.
#[derive(Default)]
pub struct DamageDecoder {
    eh_cache: BTreeMap<(u16, u32), CachedEhUnit>,
    matrix_cache: BTreeMap<(usize, u16, u16), MatrixCache>,
}

#[derive(Clone)]
struct MatrixCache {
    values: Vec<u8>,
    observations: Vec<PhysicalObservation>,
}

impl DamageDecoder {
    pub fn new() -> Self {
        Self::default()
    }

    fn decode_eh(
        &mut self,
        profile_version: u16,
        id: u32,
        encoded: [u8; EH_UNIT_BYTES],
        erasures: Vec<EhErasure>,
    ) -> Option<DecodedUnit> {
        let key = (profile_version, id);
        if let Some(cached) = self.eh_cache.get(&key) {
            if cached.encoded == encoded && cached.erasures == erasures {
                return cached.decoded;
            }
        }
        let decoded = decode_eh_unit_fast(
            &EhObservation {
                encoded,
                erasures: erasures.clone(),
            },
            profile_version,
        )
        .ok();
        self.eh_cache.entry(key).or_insert(CachedEhUnit {
            encoded,
            erasures,
            decoded,
        });
        decoded
    }
}

fn route_bytes(
    matrix: &ObsMatrix,
    width: usize,
    sector: u8,
    byte_count: usize,
) -> Result<Option<Vec<u8>>> {
    let bit_count = byte_count
        .checked_mul(8)
        .ok_or(DamageError::ResourceLimit)?;
    let sector_cells = width
        .checked_mul(
            matrix
                .side
                .checked_sub(width)
                .ok_or(DamageError::Coordinate)?,
        )
        .ok_or(DamageError::ResourceLimit)?;
    if bit_count > sector_cells {
        return Ok(None);
    }
    let mut raw = vec![0_u8; byte_count];
    for bit in 0..bit_count {
        let (row, column) =
            sector_cell_at(matrix.side, width, sector, bit).map_err(|_| DamageError::Coordinate)?;
        match matrix.value(row, column)? {
            0 => {}
            1 => raw[bit / 8] |= 1 << (7 - bit % 8),
            2 => return Ok(None),
            _ => unreachable!(),
        }
    }
    Ok(Some(raw))
}

fn read_u16(raw: &[u8], offset: usize) -> Option<u16> {
    raw.get(offset..offset + 2)
        .map(|bytes| u16::from_be_bytes(bytes.try_into().unwrap()))
}

fn read_u32(raw: &[u8], offset: usize) -> Option<u32> {
    raw.get(offset..offset + 4)
        .map(|bytes| u32::from_be_bytes(bytes.try_into().unwrap()))
}

fn package_table_bytes(raw: &[u8]) -> Option<Vec<&[u8]>> {
    if raw.len() < 64 {
        return None;
    }
    let count = usize::from(read_u16(raw, 18)?);
    let mut offset = 64_usize;
    let mut rows = Vec::with_capacity(count);
    for _ in 0..count {
        let header = raw.get(offset..offset.checked_add(16)?)?;
        let payload = usize::try_from(read_u32(header, 12)?).ok()?;
        let end = offset.checked_add(16)?.checked_add(payload)?;
        rows.push(raw.get(offset..end)?);
        offset = end;
    }
    Some(rows)
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct ParsedRoute {
    pub(crate) profile_version: u16,
    pub(crate) width: u16,
    pub(crate) sector: u8,
    pub(crate) map: AffineMap,
    pub(crate) package: crate::recipe::RecipePackage,
}

fn recipe_u32(package: &crate::recipe::RecipePackage, recipe_id: u16, input: &[u8]) -> Result<u64> {
    let raw =
        evaluate_serialized_recipe(package, recipe_id, input).map_err(|_| DamageError::Route)?;
    if raw.len() != 6 || raw[..2] != [0, 0] {
        return Err(DamageError::Route);
    }
    Ok(u64::from(u32::from_be_bytes(raw[2..].try_into().unwrap())))
}

fn modular_inverse(value: u64, modulus: u64) -> Result<u64> {
    let (mut old_r, mut r) = (modulus as i128, value as i128);
    let (mut old_t, mut t) = (0_i128, 1_i128);
    while r != 0 {
        let quotient = old_r / r;
        (old_r, r) = (r, old_r - quotient * r);
        (old_t, t) = (t, old_t - quotient * t);
    }
    if old_r != 1 {
        return Err(DamageError::Route);
    }
    Ok(old_t.rem_euclid(modulus as i128) as u64)
}

/// Recover the affine map from the route-embedded promoted recipe rather than
/// from a candidate-side map constructor or a clean manifestation.
fn observed_map(
    package: &crate::recipe::RecipePackage,
    side: u16,
    width: u16,
) -> Result<AffineMap> {
    if !(64..=2_048).contains(&side)
        || side % 8 != 0
        || !(8..=128).contains(&width)
        || width % 8 != 0
        || u32::from(width) * 2 + 8 > u32::from(side)
    {
        return Err(DamageError::Coordinate);
    }
    let interior_side = side - 2 * width;
    let population = u64::from(interior_side) * u64::from(interior_side);
    let input = |logical: u32| {
        let mut raw = logical.to_be_bytes().to_vec();
        raw.extend_from_slice(&side.to_be_bytes());
        raw.extend_from_slice(&width.to_be_bytes());
        raw
    };
    let offset = recipe_u32(package, 109, &input(0))?;
    let next = recipe_u32(package, 109, &input(1))?;
    if offset >= population || next >= population {
        return Err(DamageError::Route);
    }
    let multiplier = (next + population - offset) % population;
    let inverse_multiplier = modular_inverse(multiplier, population)?;
    let map = AffineMap {
        side,
        shell_width: width,
        interior_side,
        population,
        multiplier,
        offset,
        inverse_multiplier,
    };
    for logical in [0_u64, 1, population / 2, population - 1] {
        let expected = recipe_u32(package, 109, &input(logical as u32))?;
        if map.forward(logical).map_err(|_| DamageError::Coordinate)? != expected
            || map.inverse(expected).map_err(|_| DamageError::Coordinate)? != logical
        {
            return Err(DamageError::Route);
        }
    }
    Ok(map)
}

/// Parse one complete route directly from observed sector cells.  This checks
/// the frozen calibration, envelope, closed record graph, package structure,
/// endpoint, and terminal record; it never compares against a generated route.
fn parse_sector_route(
    matrix: &ObsMatrix,
    width: usize,
    sector: u8,
    resource: &mut ResourceProjection,
) -> Result<Option<ParsedRoute>> {
    let Some(head) = route_bytes(matrix, width, sector, 64)? else {
        return Ok(None);
    };
    if head[..32] != CALIBRATIONS[usize::from(sector)] || &head[32..40] != ROUTE_MAGIC {
        return Ok(None);
    }
    let envelope = &head[32..64];
    let Some(route_version) = read_u16(envelope, 8) else {
        return Ok(None);
    };
    let profile_version = read_u16(envelope, 12).unwrap();
    let record_count = usize::from(read_u16(envelope, 14).unwrap());
    let record_bytes =
        usize::try_from(read_u32(envelope, 16).unwrap()).map_err(|_| DamageError::ResourceLimit)?;
    let package_bytes =
        usize::try_from(read_u32(envelope, 20).unwrap()).map_err(|_| DamageError::ResourceLimit)?;
    let prefix_cells =
        usize::try_from(read_u32(envelope, 24).unwrap()).map_err(|_| DamageError::ResourceLimit)?;
    if route_version != 0
        || envelope[10] != sector
        || envelope[11] != sector
        || profile_by_version(profile_version).is_none()
        || !(37..=256).contains(&record_count)
        || record_bytes > 30_720
        || package_bytes > 1_048_576
        || prefix_cells
            != (64_usize
                .checked_add(record_bytes)
                .ok_or(DamageError::ResourceLimit)?)
                * 8
        || read_u16(envelope, 28) != Some(256)
        || read_u16(envelope, 30) != Some(0)
    {
        return Ok(None);
    }
    let Some(route) = route_bytes(matrix, width, sector, 64 + record_bytes)? else {
        return Ok(None);
    };
    let records = &route[64..];
    let base = u16::from(sector) * 10_000;
    let mut offset = 0_usize;
    let mut rows = Vec::<(u8, u8, u16, &[u8])>::with_capacity(record_count);
    let mut prior_id = 0_u16;
    let mut prior_stage = 0_u8;
    for ordinal in 0..record_count {
        let Some(header) = records.get(offset..offset + 8) else {
            return Ok(None);
        };
        let stage = header[0];
        let kind = header[1];
        let record_id = u16::from_be_bytes(header[2..4].try_into().unwrap());
        let payload_bytes = usize::try_from(u32::from_be_bytes(header[4..8].try_into().unwrap()))
            .map_err(|_| DamageError::ResourceLimit)?;
        let end = offset
            .checked_add(8)
            .and_then(|value| value.checked_add(payload_bytes))
            .ok_or(DamageError::ResourceLimit)?;
        let Some(payload) = records.get(offset + 8..end) else {
            return Ok(None);
        };
        if stage > 5
            || kind == 0
            || kind > 7
            || ordinal != 0 && (record_id <= prior_id || stage < prior_stage)
        {
            return Ok(None);
        }
        rows.push((stage, kind, record_id, payload));
        prior_id = record_id;
        prior_stage = stage;
        offset = end;
    }
    if offset != records.len() || record_count < 39 {
        return Ok(None);
    }
    for fact in 1_u16..=12 {
        let stage = FACT_STAGES[usize::from(fact - 1)];
        let start = usize::from(fact - 1) * 3;
        for (local, kind) in [1_u8, 2, 3].into_iter().enumerate() {
            let (actual_stage, actual_kind, id, payload) = rows[start + local];
            if actual_stage != stage
                || actual_kind != kind
                || id != base + fact * 100 + 1 + local as u16
                || payload.len() < if kind == 1 { 2 } else { 12 }
                || read_u16(payload, 0) != Some(fact)
            {
                return Ok(None);
            }
            if kind == 1 && read_u16(payload, 2) != Some(fact) {
                return Ok(None);
            }
            if kind != 1 {
                let input = usize::try_from(read_u32(payload, 4).unwrap())
                    .map_err(|_| DamageError::ResourceLimit)?;
                let output = usize::try_from(read_u32(payload, 8).unwrap())
                    .map_err(|_| DamageError::ResourceLimit)?;
                if 12_usize
                    .checked_add(input)
                    .and_then(|value| value.checked_add(output))
                    != Some(payload.len())
                {
                    return Ok(None);
                }
            }
        }
    }
    let table_count = record_count - 39;
    for (index, row) in rows[36..36 + table_count].iter().enumerate() {
        if row.0 != 5 || row.1 != 4 || row.2 != base + 5_001 + index as u16 {
            return Ok(None);
        }
    }
    let package = rows[36 + table_count];
    let parsed_package = decode_recipe_package(package.3, profile_version).ok();
    if package.0 != 5
        || package.1 != 5
        || package.2 != base + 6_001
        || package.3.len() != package_bytes
        || parsed_package.is_none()
    {
        return Ok(None);
    }
    let parsed_package = parsed_package.unwrap();
    let Some(package_tables) = package_table_bytes(package.3) else {
        return Ok(None);
    };
    if package_tables.len() != table_count
        || rows[36..36 + table_count]
            .iter()
            .zip(package_tables)
            .any(|(route_table, package_table)| route_table.3 != package_table)
    {
        return Ok(None);
    }
    for fact in 0..12 {
        let worked = rows[fact * 3 + 1].3;
        let held = rows[fact * 3 + 2].3;
        if worked.len() < 12 || held.len() < 12 {
            return Ok(None);
        }
        let worked_input = usize::try_from(read_u32(worked, 4).unwrap())
            .map_err(|_| DamageError::ResourceLimit)?;
        let held_input =
            usize::try_from(read_u32(held, 4).unwrap()).map_err(|_| DamageError::ResourceLimit)?;
        if worked.get(12..12 + worked_input).is_none()
            || held.get(12..12 + held_input).is_none()
            || worked[12..12 + worked_input] == held[12..12 + held_input]
        {
            return Ok(None);
        }
        for example in [worked, held] {
            let recipe_id = read_u16(example, 2).unwrap();
            let input_bytes = usize::try_from(read_u32(example, 4).unwrap())
                .map_err(|_| DamageError::ResourceLimit)?;
            let output_bytes = usize::try_from(read_u32(example, 8).unwrap())
                .map_err(|_| DamageError::ResourceLimit)?;
            let input_end = 12_usize
                .checked_add(input_bytes)
                .ok_or(DamageError::ResourceLimit)?;
            let output_end = input_end
                .checked_add(output_bytes)
                .ok_or(DamageError::ResourceLimit)?;
            if output_end != example.len() {
                return Ok(None);
            }
            charge_recipe(resource, &parsed_package, recipe_id, 1)?;
            if evaluate_serialized_recipe(&parsed_package, recipe_id, &example[12..input_end])
                .ok()
                .as_deref()
                != Some(&example[input_end..])
            {
                return Ok(None);
            }
        }
    }
    let endpoint = rows[37 + table_count];
    let end = rows[38 + table_count];
    if endpoint.0 != 5
        || endpoint.1 != 6
        || endpoint.2 != base + 7_001
        || endpoint.3 != 1_u32.to_be_bytes()
        || end.0 != 5
        || end.1 != 7
        || end.2 != base + 7_002
        || !end.3.is_empty()
    {
        return Ok(None);
    }
    let width = u16::try_from(width).map_err(|_| DamageError::Coordinate)?;
    let map = observed_map(&parsed_package, matrix.side as u16, width)?;
    Ok(Some(ParsedRoute {
        profile_version,
        width,
        sector,
        map,
        package: parsed_package,
    }))
}

fn mapping_sha256(map: AffineMap) -> Result<String> {
    let value = ManifestValue::Object(BTreeMap::from([
        (
            "id".to_owned(),
            ManifestValue::String("affine-interior-v1".to_owned()),
        ),
        (
            "interior_side".to_owned(),
            ManifestValue::U64(u64::from(map.interior_side)),
        ),
        ("population".to_owned(), ManifestValue::U64(map.population)),
        ("multiplier".to_owned(), ManifestValue::U64(map.multiplier)),
        ("offset".to_owned(), ManifestValue::U64(map.offset)),
        (
            "inverse_multiplier".to_owned(),
            ManifestValue::U64(map.inverse_multiplier),
        ),
    ]));
    let raw = serialize_manifest(&value).map_err(|_| DamageError::Reconstruction)?;
    Ok(observation_sha256(&raw))
}

pub(crate) fn discover_routes(
    matrix: &ObsMatrix,
    resource: &mut ResourceProjection,
) -> Result<Vec<ParsedRoute>> {
    let maximum = 128.min(matrix.side.saturating_sub(8) / 2);
    let mut claims = Vec::new();
    for width in (8..=maximum).step_by(8) {
        for sector in 0..4 {
            if let Some(route) = parse_sector_route(matrix, width, sector, resource)? {
                claims.push(route);
            }
        }
    }
    Ok(claims)
}

fn calibration_bit(sector: u8, bit: usize) -> u8 {
    (CALIBRATIONS[usize::from(sector)][bit / 8] >> (7 - bit % 8)) & 1
}

fn matrix_view_may_have_route(observed: &ObsMatrix, transform: u8, polarity: u8) -> Result<bool> {
    let maximum = 128.min(observed.side.saturating_sub(8) / 2);
    for width in (8..=maximum).step_by(8) {
        for sector in 0..4 {
            let mut matches = true;
            for bit in 0..256 {
                let (row, column) = sector_cell_at(observed.side, width, sector, bit)
                    .map_err(|_| DamageError::Coordinate)?;
                let (observed_row, observed_column) =
                    observed_coordinate(observed.side, transform, row, column)?;
                let value = observed.value(observed_row, observed_column)?;
                if value == 2 || value ^ polarity != calibration_bit(sector, bit) {
                    matches = false;
                    break;
                }
            }
            if matches {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

fn bits_view_may_have_route(
    observed: &ObsBits,
    side: usize,
    transform: u8,
    polarity: u8,
) -> Result<bool> {
    let maximum = 128.min(side.saturating_sub(8) / 2);
    for width in (8..=maximum).step_by(8) {
        for sector in 0..4 {
            let mut matches = true;
            for bit in 0..256 {
                let (row, column) = sector_cell_at(side, width, sector, bit)
                    .map_err(|_| DamageError::Coordinate)?;
                let (observed_row, observed_column) =
                    observed_coordinate(side, transform, row, column)?;
                if observed.bit(observed_row * side + observed_column)? ^ polarity
                    != calibration_bit(sector, bit)
                {
                    matches = false;
                    break;
                }
            }
            if matches {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

fn extract_matrix_unit_at(
    decoder: &mut DamageDecoder,
    matrix: &ObsMatrix,
    map: AffineMap,
    profile_version: u16,
    ordinal: usize,
) -> Result<PhysicalObservation> {
    let mut encoded = [0_u8; EH_UNIT_BYTES];
    let mut erasures = Vec::new();
    for bit_offset in 0..UNIT_BITS {
        let logical = ordinal
            .checked_mul(UNIT_BITS)
            .and_then(|value| value.checked_add(bit_offset))
            .ok_or(DamageError::ResourceLimit)?;
        let physical = map
            .forward(logical as u64)
            .map_err(|_| DamageError::Coordinate)?;
        let (row, column) = map
            .matrix_cell(physical)
            .map_err(|_| DamageError::Coordinate)?;
        match matrix.value(usize::from(row), usize::from(column))? {
            0 => {}
            1 => encoded[bit_offset / 8] |= 1 << (7 - bit_offset % 8),
            2 => erasures.push(EhErasure {
                codeword: u8::try_from(bit_offset / EH_CODEWORD_BITS).unwrap(),
                position: u8::try_from(bit_offset % EH_CODEWORD_BITS + 1).unwrap(),
            }),
            _ => unreachable!(),
        }
    }
    let id = u32::try_from(ordinal + 1).map_err(|_| DamageError::ResourceLimit)?;
    let decoded = decoder.decode_eh(profile_version, id, encoded, erasures);
    Ok(PhysicalObservation {
        id,
        present: true,
        common: decoded.map(|value| value.common),
        quality: decoded.map(|value| match value.quality {
            DecodeQuality::Verified => RecoveryQuality::Verified,
            DecodeQuality::Recovered => RecoveryQuality::Recovered,
        }),
    })
}

fn extract_matrix_units(
    decoder: &mut DamageDecoder,
    matrix: &ObsMatrix,
    map: AffineMap,
    profile_version: u16,
) -> Result<Vec<PhysicalObservation>> {
    let unit_count =
        usize::try_from(map.population).map_err(|_| DamageError::ResourceLimit)? / UNIT_BITS;
    if unit_count > MAX_UNITS {
        return Err(DamageError::ResourceLimit);
    }
    let key = (matrix.side, map.shell_width, profile_version);
    if let Some(cached) = decoder.matrix_cache.get(&key).cloned() {
        if cached.observations.len() != unit_count || cached.values.len() != matrix.values.len() {
            return Err(DamageError::Reconstruction);
        }
        let width = usize::from(map.shell_width);
        let interior = usize::from(map.interior_side);
        let mut changed = BTreeSet::new();
        for row in 0..interior {
            let matrix_row = row + width;
            for column in 0..interior {
                let matrix_column = column + width;
                let flat = matrix_row * matrix.side + matrix_column;
                if matrix.values[flat] != cached.values[flat] {
                    let physical = row * interior + column;
                    let logical = map
                        .inverse(physical as u64)
                        .map_err(|_| DamageError::Coordinate)?;
                    let ordinal = usize::try_from(logical)
                        .map_err(|_| DamageError::ResourceLimit)?
                        / UNIT_BITS;
                    if ordinal < unit_count {
                        changed.insert(ordinal);
                    }
                }
            }
        }
        let mut observations = cached.observations;
        for ordinal in changed {
            observations[ordinal] =
                extract_matrix_unit_at(decoder, matrix, map, profile_version, ordinal)?;
        }
        decoder.matrix_cache.insert(
            key,
            MatrixCache {
                values: matrix.values.clone(),
                observations: observations.clone(),
            },
        );
        return Ok(observations);
    }
    let mut observations = Vec::with_capacity(unit_count);
    for ordinal in 0..unit_count {
        observations.push(extract_matrix_unit_at(
            decoder,
            matrix,
            map,
            profile_version,
            ordinal,
        )?);
    }
    decoder.matrix_cache.insert(
        key,
        MatrixCache {
            values: matrix.values.clone(),
            observations: observations.clone(),
        },
    );
    Ok(observations)
}

fn inventory_from_observations(
    observations: &[PhysicalObservation],
    profile_version: u16,
    resource: &mut ResourceProjection,
) -> Result<(Inventory, Vec<u8>, RecoveryQuality)> {
    let mut copies = BTreeMap::<u16, Vec<FragmentWitness>>::new();
    for observation in observations {
        let (Some(common), Some(quality)) = (observation.common, observation.quality) else {
            continue;
        };
        let Ok(block) = decode_common_block(&common, profile_version) else {
            continue;
        };
        if block.section_id == 1 && block.section_type == SECTION_INVENTORY {
            copies
                .entry(block.semantic_copy_id)
                .or_default()
                .push(FragmentWitness {
                    raw_block: common,
                    quality,
                });
        }
    }
    let mut witnesses = Vec::new();
    for fragments in copies.values() {
        if let Ok(witness) = assemble_semantic_copy(fragments, profile_version) {
            witnesses.push(witness);
        }
    }
    let witnesses = deduplicate_section_witnesses(witnesses);
    charge_section_attempts(resource, witnesses.len())?;
    let canonical = aggregate_section_witnesses(&witnesses).map_err(|error| match error.code {
        crate::RejectCode::Ambiguous => DamageError::Ambiguous,
        _ => DamageError::Reconstruction,
    })?;
    let envelope = decode_section(&canonical.envelope).map_err(|_| DamageError::Reconstruction)?;
    let inventory = decode_inventory(&envelope.payload).map_err(|_| DamageError::Reconstruction)?;
    Ok((inventory, canonical.envelope, canonical.quality))
}

fn deduplicate_section_witnesses(witnesses: Vec<SectionWitness>) -> Vec<SectionWitness> {
    let mut unique = BTreeMap::<Vec<u8>, bool>::new();
    for witness in witnesses {
        unique
            .entry(witness.envelope)
            .and_modify(|verified| *verified |= witness.all_units_verified)
            .or_insert(witness.all_units_verified);
    }
    unique
        .into_iter()
        .map(|(envelope, all_units_verified)| SectionWitness {
            envelope,
            all_units_verified,
        })
        .collect()
}

fn expected_layout(inventory: &Inventory) -> Result<BTreeMap<u32, (u32, u16, u16)>> {
    let maximum_copy = inventory
        .entries
        .iter()
        .map(|entry| entry.copy_count)
        .max()
        .unwrap_or(0);
    let mut id = 1_u32;
    let mut layout = BTreeMap::new();
    for copy in 0..maximum_copy {
        for entry in inventory
            .entries
            .iter()
            .filter(|entry| copy < entry.copy_count)
        {
            let check = match entry.check_id {
                1 => 4_usize,
                2 => 8_usize,
                _ => return Err(DamageError::Reconstruction),
            };
            let envelope = 18_usize
                .checked_add(entry.dependencies.len() * 4)
                .and_then(|value| value.checked_add(entry.logical_payload_length as usize))
                .and_then(|value| value.checked_add(check))
                .ok_or(DamageError::ResourceLimit)?;
            let fragments = envelope.div_ceil(COMMON_PAYLOAD_BYTES);
            for fragment in 0..fragments {
                layout.insert(
                    id,
                    (
                        entry.section_id,
                        u16::from(copy),
                        u16::try_from(fragment).map_err(|_| DamageError::ResourceLimit)?,
                    ),
                );
                id = id.checked_add(1).ok_or(DamageError::ResourceLimit)?;
            }
        }
    }
    Ok(layout)
}

fn recover_sections(
    observations: &[PhysicalObservation],
    profile_version: u16,
    resource: &mut ResourceProjection,
) -> Result<RecoveryResult> {
    let (inventory, inventory_envelope, inventory_quality) =
        match inventory_from_observations(observations, profile_version, resource) {
            Ok(value) => value,
            Err(DamageError::Ambiguous) => {
                let sections =
                    discovered_sections_without_inventory(observations, profile_version, resource)?;
                return Ok(RecoveryResult {
                    profile_version: Some(profile_version),
                    inventory_established: false,
                    artifact_state: ArtifactState::Ambiguous,
                    resource: *resource,
                    sections,
                    fragments: diagnostics_without_inventory(observations, profile_version),
                    accepted_hypotheses: Vec::new(),
                });
            }
            Err(_) => {
                let sections =
                    discovered_sections_without_inventory(observations, profile_version, resource)?;
                return Ok(RecoveryResult {
                    profile_version: Some(profile_version),
                    inventory_established: false,
                    artifact_state: ArtifactState::Failure,
                    resource: *resource,
                    sections,
                    fragments: diagnostics_without_inventory(observations, profile_version),
                    accepted_hypotheses: Vec::new(),
                });
            }
        };
    let layout = expected_layout(&inventory)?;
    if observations
        .iter()
        .any(|row| row.id as usize > layout.len())
    {
        return Err(DamageError::Reconstruction);
    }
    let by_id = observations
        .iter()
        .map(|row| (row.id, row))
        .collect::<BTreeMap<_, _>>();
    let mut valid = BTreeMap::<(u32, u16), Vec<FragmentWitness>>::new();
    for observation in observations {
        let (Some(common), Some(quality)) = (observation.common, observation.quality) else {
            continue;
        };
        if let Ok(block) = decode_common_block(&common, profile_version) {
            valid
                .entry((block.section_id, block.semantic_copy_id))
                .or_default()
                .push(FragmentWitness {
                    raw_block: common,
                    quality,
                });
        }
    }
    let mut section_results = Vec::with_capacity(inventory.entries.len());
    let mut any_optional_unavailable = false;
    let mut required_unavailable = false;
    for entry in &inventory.entries {
        if entry.section_id == 1 {
            let state = SectionState::Verified;
            section_results.push(SectionResult {
                section_id: 1,
                state: match inventory_quality {
                    RecoveryQuality::Verified => state,
                    RecoveryQuality::Recovered => SectionState::Recovered,
                },
                envelope: Some(inventory_envelope.clone()),
            });
            continue;
        }
        let mut witnesses = Vec::<SectionWitness>::new();
        let mut corrupt = false;
        let mut missing = false;
        for copy in 0..entry.copy_count {
            if let Some(fragments) = valid.get(&(entry.section_id, u16::from(copy))) {
                if let Ok(witness) = assemble_semantic_copy(fragments, profile_version) {
                    if decode_section(&witness.envelope)
                        .and_then(|envelope| {
                            validate_envelope_against_inventory(&envelope, &inventory)
                        })
                        .is_ok()
                    {
                        witnesses.push(witness);
                    } else {
                        corrupt = true;
                    }
                }
            }
            for (id, expected) in layout.iter().filter(|(_, expected)| {
                expected.0 == entry.section_id && expected.1 == u16::from(copy)
            }) {
                match by_id.get(id) {
                    None => missing = true,
                    Some(row) if !row.present || row.common.is_none() => corrupt = true,
                    Some(row) => {
                        let actual = row
                            .common
                            .and_then(|common| decode_common_block(&common, profile_version).ok());
                        if actual.as_ref().is_none_or(|block| {
                            (
                                block.section_id,
                                block.semantic_copy_id,
                                block.fragment_index,
                            ) != *expected
                        }) {
                            corrupt = true;
                        }
                    }
                }
            }
        }
        let witnesses = deduplicate_section_witnesses(witnesses);
        charge_section_attempts(resource, witnesses.len())?;
        let (state, envelope) = if witnesses.is_empty() {
            (
                if corrupt {
                    SectionState::Corrupt
                } else if missing {
                    SectionState::Incomplete
                } else {
                    SectionState::Unknown
                },
                None,
            )
        } else {
            match aggregate_section_witnesses(&witnesses) {
                Ok(canonical) => (
                    match canonical.quality {
                        RecoveryQuality::Verified => SectionState::Verified,
                        RecoveryQuality::Recovered => SectionState::Recovered,
                    },
                    Some(canonical.envelope),
                ),
                Err(error) if error.code == crate::RejectCode::Ambiguous => {
                    (SectionState::Ambiguous, None)
                }
                Err(_) => (SectionState::Corrupt, None),
            }
        };
        if !matches!(state, SectionState::Verified | SectionState::Recovered) {
            if entry.closure_class == CLOSURE_M2_REQUIRED {
                required_unavailable = true;
            } else {
                any_optional_unavailable = true;
            }
        }
        section_results.push(SectionResult {
            section_id: entry.section_id,
            state,
            envelope,
        });
    }
    let closure_view = RecoveryResult {
        profile_version: Some(profile_version),
        inventory_established: true,
        resource: *resource,
        artifact_state: ArtifactState::Failure,
        sections: section_results.clone(),
        fragments: Vec::new(),
        accepted_hypotheses: Vec::new(),
    };
    if recovered_stream(&closure_view, 2).is_none() {
        required_unavailable = true;
    }
    if recovered_stream(&closure_view, 3).is_none() {
        any_optional_unavailable = true;
    }
    let artifact_state = if section_results
        .iter()
        .any(|row| row.state == SectionState::Ambiguous)
    {
        ArtifactState::Ambiguous
    } else if required_unavailable {
        ArtifactState::Failure
    } else if any_optional_unavailable {
        ArtifactState::Degraded
    } else {
        ArtifactState::Exact
    };
    Ok(RecoveryResult {
        profile_version: Some(profile_version),
        inventory_established: true,
        resource: *resource,
        artifact_state,
        sections: section_results,
        fragments: diagnostics_with_inventory(observations, profile_version, &layout),
        accepted_hypotheses: Vec::new(),
    })
}

fn common_hash(common: &[u8; 191]) -> String {
    format!("{:x}", Sha256::digest(common))
}

fn diagnostics_without_inventory(
    observations: &[PhysicalObservation],
    profile_version: u16,
) -> Vec<FragmentDiagnostic> {
    observations
        .iter()
        .map(|row| {
            let block = row
                .common
                .and_then(|common| decode_common_block(&common, profile_version).ok());
            FragmentDiagnostic {
                input_id: row.id,
                profile_version: block.as_ref().map(|_| profile_version),
                section_id: block.as_ref().map_or(0, |block| block.section_id),
                semantic_copy_id: block
                    .as_ref()
                    .map_or(u16::MAX, |block| block.semantic_copy_id),
                fragment_index: block
                    .as_ref()
                    .map_or(u16::MAX, |block| block.fragment_index),
                state: if block.is_some() {
                    match row.quality {
                        Some(RecoveryQuality::Verified) => FragmentState::Verified,
                        Some(RecoveryQuality::Recovered) => FragmentState::Recovered,
                        None => FragmentState::Unknown,
                    }
                } else {
                    FragmentState::Unknown
                },
                common_block_sha256: row
                    .common
                    .as_ref()
                    .filter(|_| block.is_some())
                    .map_or_else(|| "0".repeat(64), common_hash),
            }
        })
        .collect()
}

fn discovered_sections_without_inventory(
    observations: &[PhysicalObservation],
    profile_version: u16,
    resource: &mut ResourceProjection,
) -> Result<Vec<SectionResult>> {
    let mut fragments = BTreeMap::<(u32, u16), Vec<FragmentWitness>>::new();
    for observation in observations {
        let (Some(common), Some(quality)) = (observation.common, observation.quality) else {
            continue;
        };
        let Ok(block) = decode_common_block(&common, profile_version) else {
            continue;
        };
        fragments
            .entry((block.section_id, block.semantic_copy_id))
            .or_default()
            .push(FragmentWitness {
                raw_block: common,
                quality,
            });
    }
    let mut by_section = BTreeMap::<u32, Vec<SectionWitness>>::new();
    for ((section_id, _), rows) in fragments {
        if let Ok(witness) = assemble_semantic_copy(&rows, profile_version) {
            by_section.entry(section_id).or_default().push(witness);
        }
    }
    by_section
        .into_iter()
        .map(|(section_id, witnesses)| {
            let witnesses = deduplicate_section_witnesses(witnesses);
            charge_section_attempts(resource, witnesses.len())?;
            Ok(match aggregate_section_witnesses(&witnesses) {
                Ok(canonical) => SectionResult {
                    section_id,
                    state: match canonical.quality {
                        RecoveryQuality::Verified => SectionState::Verified,
                        RecoveryQuality::Recovered => SectionState::Recovered,
                    },
                    envelope: Some(canonical.envelope),
                },
                Err(error) if error.code == crate::RejectCode::Ambiguous => SectionResult {
                    section_id,
                    state: SectionState::Ambiguous,
                    envelope: None,
                },
                Err(_) => SectionResult {
                    section_id,
                    state: SectionState::Corrupt,
                    envelope: None,
                },
            })
        })
        .collect()
}

fn diagnostics_with_inventory(
    observations: &[PhysicalObservation],
    profile_version: u16,
    layout: &BTreeMap<u32, (u32, u16, u16)>,
) -> Vec<FragmentDiagnostic> {
    let observed = observations
        .iter()
        .map(|row| (row.id, row))
        .collect::<BTreeMap<_, _>>();
    let ids = layout
        .keys()
        .chain(observed.keys())
        .copied()
        .collect::<BTreeSet<_>>();
    ids.into_iter()
        .map(|id| {
            let expected = layout.get(&id).copied();
            let observation = observed.get(&id).copied();
            let decoded = observation
                .and_then(|row| row.common)
                .and_then(|common| decode_common_block(&common, profile_version).ok());
            let agrees = expected.is_some_and(|identity| {
                decoded.as_ref().is_some_and(|block| {
                    (
                        block.section_id,
                        block.semantic_copy_id,
                        block.fragment_index,
                    ) == identity
                })
            });
            let (section_id, semantic_copy_id, fragment_index) = expected
                .or_else(|| {
                    decoded.as_ref().map(|block| {
                        (
                            block.section_id,
                            block.semantic_copy_id,
                            block.fragment_index,
                        )
                    })
                })
                .unwrap_or((0, u16::MAX, u16::MAX));
            let state = match (expected, observation, decoded.as_ref(), agrees) {
                (Some(_), None, _, _) => FragmentState::Missing,
                (Some(_), Some(_), _, false) => FragmentState::Corrupt,
                (_, Some(row), Some(_), true) | (None, Some(row), Some(_), false) => {
                    match row.quality {
                        Some(RecoveryQuality::Verified) => FragmentState::Verified,
                        Some(RecoveryQuality::Recovered) => FragmentState::Recovered,
                        None => FragmentState::Unknown,
                    }
                }
                (None, Some(_), None, _) => FragmentState::Unknown,
                _ => FragmentState::Unknown,
            };
            let valid = matches!(state, FragmentState::Verified | FragmentState::Recovered);
            FragmentDiagnostic {
                input_id: id,
                profile_version: expected
                    .map(|_| profile_version)
                    .or_else(|| decoded.as_ref().filter(|_| valid).map(|_| profile_version)),
                section_id,
                semantic_copy_id,
                fragment_index,
                state,
                common_block_sha256: observation
                    .and_then(|row| row.common.as_ref())
                    .filter(|_| valid)
                    .map_or_else(|| "0".repeat(64), common_hash),
            }
        })
        .collect()
}

fn merge_view_results(mut results: Vec<RecoveryResult>) -> Result<RecoveryResult> {
    if results.is_empty() {
        return Err(DamageError::Route);
    }
    let mut resource = ResourceProjection::default();
    let mut accepted = BTreeSet::new();
    for result in &results {
        merge_resource(&mut resource, result.resource)?;
        accepted.extend(result.accepted_hypotheses.iter().cloned());
    }
    let accepted_hypotheses = accepted.into_iter().collect::<Vec<_>>();
    let mut complete = results
        .iter_mut()
        .filter(|result| result.inventory_established)
        .map(|result| {
            result.resource = ResourceProjection::default();
            result.accepted_hypotheses.clear();
            result.clone()
        })
        .collect::<Vec<_>>();
    complete.dedup();
    match complete.len() {
        0 => {
            let mut result = results.remove(0);
            result.profile_version = None;
            result.inventory_established = false;
            result.artifact_state = ArtifactState::Failure;
            result.resource = resource;
            result.accepted_hypotheses = accepted_hypotheses;
            Ok(result)
        }
        1 => {
            let mut result = complete.pop().unwrap();
            result.resource = resource;
            result.accepted_hypotheses = accepted_hypotheses;
            Ok(result)
        }
        _ => Ok(RecoveryResult {
            profile_version: None,
            inventory_established: false,
            resource,
            artifact_state: ArtifactState::Ambiguous,
            sections: Vec::new(),
            fragments: Vec::new(),
            accepted_hypotheses,
        }),
    }
}

/// Decode a canonical-orientation matrix after at least one complete shell
/// route has independently established the candidate profile and map.
impl DamageDecoder {
    fn decode_canonical_matrix(
        &mut self,
        matrix: &ObsMatrix,
        transform_id: u8,
        polarity_id: u8,
    ) -> Result<RecoveryResult> {
        let mut resource = ResourceProjection::default();
        let route_rows = discover_routes(matrix, &mut resource)?;
        if route_rows.is_empty() {
            return Err(DamageError::Route);
        }
        for route in &route_rows {
            let unit_count = route.map.population / UNIT_BITS as u64;
            charge_recipe(&mut resource, &route.package, 30, unit_count * 24)?;
        }
        let mut claims = Vec::<ParsedRoute>::new();
        for route in &route_rows {
            if !claims.iter().any(|prior| {
                prior.profile_version == route.profile_version
                    && prior.width == route.width
                    && prior.map == route.map
                    && prior.package == route.package
            }) {
                claims.push(route.clone());
            }
        }
        let mut accepted_hypotheses = route_rows
            .iter()
            .map(|route| {
                Ok(AcceptedHypothesis {
                    transform_id,
                    polarity_id,
                    sector_id: route.sector,
                    profile_version: route.profile_version,
                    mapping_sha256: mapping_sha256(route.map)?,
                })
            })
            .collect::<Result<Vec<_>>>()?;
        accepted_hypotheses.sort();
        accepted_hypotheses.dedup();
        // A locally valid route is an accepted hypothesis even when its claimed
        // map/profile cannot reconstruct a complete downstream result.  This is
        // deliberately distinct from ambiguity: only two nonidentical complete
        // checked results are ambiguous.
        let mut complete = Vec::<RecoveryResult>::new();
        for route in claims {
            let profile_version = route.profile_version;
            let Some(profile) = profile_by_version(profile_version) else {
                continue;
            };
            if profile.transport != TransportFamily::Eh72Replicated {
                continue;
            }
            let result = recover_sections(
                &extract_matrix_units(self, &matrix, route.map, profile_version)?,
                profile_version,
                &mut resource,
            )?;
            if result.inventory_established && !complete.contains(&result) {
                complete.push(result);
            }
        }
        match complete.len() {
            0 => Ok(RecoveryResult {
                profile_version: None,
                inventory_established: false,
                resource,
                artifact_state: ArtifactState::Failure,
                sections: Vec::new(),
                fragments: Vec::new(),
                accepted_hypotheses,
            }),
            1 => {
                let mut result = complete.pop().unwrap();
                result.resource = resource;
                result.accepted_hypotheses = accepted_hypotheses;
                Ok(result)
            }
            _ => Ok(RecoveryResult {
                profile_version: None,
                inventory_established: false,
                resource,
                artifact_state: ArtifactState::Ambiguous,
                sections: Vec::new(),
                fragments: Vec::new(),
                accepted_hypotheses,
            }),
        }
    }

    pub fn decode_matrix(&mut self, raw: &[u8]) -> Result<RecoveryResult> {
        verify_damage_owner()?;
        let observed = ObsMatrix::parse(raw)?;
        let mut results = Vec::new();
        for transform in 0..8 {
            for polarity in 0..2 {
                if !matrix_view_may_have_route(&observed, transform, polarity)? {
                    continue;
                }
                let mut canonical = vec![0; observed.values.len()];
                for row in 0..observed.side {
                    for column in 0..observed.side {
                        let (observed_row, observed_column) =
                            observed_coordinate(observed.side, transform, row, column)?;
                        let value = observed.value(observed_row, observed_column)?;
                        canonical[row * observed.side + column] =
                            if value == 2 { 2 } else { value ^ polarity };
                    }
                }
                let matrix = ObsMatrix {
                    side: observed.side,
                    values: canonical,
                };
                if let Ok(result) = self.decode_canonical_matrix(&matrix, transform, polarity) {
                    results.push(result);
                }
            }
        }
        merge_view_results(results)
    }

    /// Decode raw transformed bits by trying the frozen sixteen entry hypotheses.
    pub fn decode_bits(&mut self, raw: &[u8]) -> Result<RecoveryResult> {
        verify_damage_owner()?;
        let bits = ObsBits::parse(raw)?;
        let side = bits.count.isqrt();
        if side == 0 || side > MAX_SIDE || side * side != bits.count {
            return Err(DamageError::Length);
        }
        let mut results = Vec::new();
        for transform in 0..8 {
            for polarity in 0..2 {
                if !bits_view_may_have_route(&bits, side, transform, polarity)? {
                    continue;
                }
                let mut canonical = vec![0; bits.count];
                for row in 0..side {
                    for column in 0..side {
                        let (observed_row, observed_column) =
                            observed_coordinate(side, transform, row, column)?;
                        canonical[row * side + column] =
                            bits.bit(observed_row * side + observed_column)? ^ polarity;
                    }
                }
                let matrix = ObsMatrix {
                    side,
                    values: canonical,
                };
                if let Ok(result) = self.decode_canonical_matrix(&matrix, transform, polarity) {
                    results.push(result);
                }
            }
        }
        merge_view_results(results)
    }

    /// Decode artifact-derived unit IDs/bytes without candidate or operator input.
    /// Every frozen profile is tried; only a uniquely valid inventory establishes
    /// the profile.
    pub fn decode_units(&mut self, raw: &[u8]) -> Result<RecoveryResult> {
        verify_damage_owner()?;
        let units = ObsUnits::parse(raw)?;
        let mut results = Vec::new();
        let mut resource = ResourceProjection::default();
        for profile_version in 1..=6 {
            let Some(profile) = profile_by_version(profile_version) else {
                continue;
            };
            let _package = neutral_package(profile_version)?;
            charge_units_profile(
                &mut resource,
                units_resource_row(profile_version)?,
                units.entries.len(),
            )?;
            let observations = units
                .entries
                .iter()
                .map(|entry| {
                    let decoded = match profile.transport {
                        TransportFamily::Eh72Replicated if entry.bytes.len() == EH_UNIT_BYTES => {
                            let encoded: [u8; EH_UNIT_BYTES] =
                                entry.bytes.as_slice().try_into().unwrap();
                            self.decode_eh(
                                profile_version,
                                entry.physical_unit_id,
                                encoded,
                                Vec::new(),
                            )
                        }
                        TransportFamily::Rs255_191 if entry.bytes.len() == RS_CODEWORD_BYTES => {
                            decode_rs_unit(&entry.bytes, &[], profile_version).ok()
                        }
                        _ => None,
                    };
                    PhysicalObservation {
                        id: entry.physical_unit_id,
                        present: true,
                        common: decoded.map(|value| value.common),
                        quality: decoded.map(|value| match value.quality {
                            DecodeQuality::Verified => RecoveryQuality::Verified,
                            DecodeQuality::Recovered => RecoveryQuality::Recovered,
                        }),
                    }
                })
                .collect::<Vec<_>>();
            if let Ok(result) = recover_sections(&observations, profile_version, &mut resource) {
                if !result.sections.is_empty() {
                    results.push(result);
                }
            }
        }
        let mut complete = results
            .iter()
            .filter(|result| result.inventory_established)
            .cloned()
            .collect::<Vec<_>>();
        if complete.len() != 1 {
            let discovered = if complete.is_empty() && results.len() == 1 {
                Some(results.remove(0))
            } else {
                None
            };
            let mut result = discovered.unwrap_or(RecoveryResult {
                profile_version: None,
                inventory_established: false,
                resource,
                artifact_state: if results.len() > 1 {
                    ArtifactState::Ambiguous
                } else {
                    ArtifactState::Failure
                },
                sections: Vec::new(),
                fragments: Vec::new(),
                accepted_hypotheses: Vec::new(),
            });
            result.profile_version = None;
            result.inventory_established = false;
            result.resource = resource;
            return Ok(result);
        }
        let mut result = complete.pop().unwrap();
        result.resource = resource;
        Ok(result)
    }
}

pub fn decode_matrix(raw: &[u8]) -> Result<RecoveryResult> {
    DamageDecoder::new().decode_matrix(raw)
}

pub fn decode_bits(raw: &[u8]) -> Result<RecoveryResult> {
    DamageDecoder::new().decode_bits(raw)
}

pub fn decode_units(raw: &[u8]) -> Result<RecoveryResult> {
    DamageDecoder::new().decode_units(raw)
}

/// Evaluate one serialized named channel with fresh decoder state and close
/// parser/decoder rejection into the frozen canonical artifact-state space.
pub fn decode_observation(channel: &str, raw: &[u8]) -> RecoveryResult {
    let decoded = match channel {
        "OBS_BITS" => decode_bits(raw),
        "OBS_MATRIX" => decode_matrix(raw),
        "OBS_UNITS" => decode_units(raw),
        _ => Err(DamageError::Channel),
    };
    decoded.unwrap_or_else(|error| RecoveryResult {
        profile_version: None,
        inventory_established: false,
        resource: ResourceProjection::default(),
        artifact_state: if error == DamageError::ResourceLimit {
            ArtifactState::ResourceLimit
        } else {
            ArtifactState::Failure
        },
        sections: Vec::new(),
        fragments: Vec::new(),
        accepted_hypotheses: Vec::new(),
    })
}

pub fn wrong_accept_count(result: &RecoveryResult, clean: &ManifestationCore) -> u64 {
    let expected = clean
        .sections
        .iter()
        .filter_map(|section| section.envelope().ok().map(|raw| (section.section_id, raw)))
        .collect::<BTreeMap<_, _>>();
    result
        .sections
        .iter()
        .filter(|row| {
            row.envelope.as_ref().is_some_and(|actual| {
                expected
                    .get(&row.section_id)
                    .is_none_or(|clean| clean != actual)
            })
        })
        .count() as u64
}

pub fn required_closure_exact(result: &RecoveryResult, clean: &ManifestationCore) -> bool {
    let by_id = result
        .sections
        .iter()
        .map(|row| (row.section_id, row))
        .collect::<BTreeMap<_, _>>();
    clean
        .sections
        .iter()
        .filter(|section| section.closure_class == CLOSURE_M2_REQUIRED)
        .all(|section| {
            by_id.get(&section.section_id).is_some_and(|row| {
                matches!(row.state, SectionState::Verified | SectionState::Recovered)
                    && row.envelope.as_ref() == section.envelope().ok().as_ref()
            })
        })
}

pub fn all_sections_exact(result: &RecoveryResult, clean: &ManifestationCore) -> bool {
    if result.sections.len() != clean.sections.len() {
        return false;
    }
    let by_id = result
        .sections
        .iter()
        .map(|row| (row.section_id, row))
        .collect::<BTreeMap<_, _>>();
    clean.sections.iter().all(|section| {
        by_id.get(&section.section_id).is_some_and(|row| {
            matches!(row.state, SectionState::Verified | SectionState::Recovered)
                && row.envelope.as_ref() == section.envelope().ok().as_ref()
        })
    })
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum OracleUnitState {
    Verified,
    Recovered,
    Missing,
    Corrupt,
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct DamageEffect {
    pub erased_coordinates: Vec<Coordinate>,
    pub substituted_coordinates: Vec<Coordinate>,
    pub omitted_unit_ids: Vec<u32>,
}

/// Independent ownership oracle.  It uses only the frozen cell-owner table and
/// EH correction radius, never transport decoder output.
pub fn oracle_section_states(
    core: &ManifestationCore,
    effect: &DamageEffect,
) -> Result<Vec<(u32, SectionState)>> {
    let side = usize::from(core.side);
    let mut erased = BTreeMap::<u32, [u16; 24]>::new();
    let mut changed = BTreeMap::<u32, [u16; 24]>::new();
    let mut seen_erased = BTreeSet::new();
    let mut seen_changed = BTreeSet::new();
    for (coordinates, seen, counts) in [
        (&effect.erased_coordinates, &mut seen_erased, &mut erased),
        (
            &effect.substituted_coordinates,
            &mut seen_changed,
            &mut changed,
        ),
    ] {
        for coordinate in coordinates {
            if !seen.insert(*coordinate) {
                return Err(DamageError::Duplicate);
            }
            let row = usize::try_from(coordinate.row).map_err(|_| DamageError::Coordinate)?;
            let column = usize::try_from(coordinate.column).map_err(|_| DamageError::Coordinate)?;
            if row >= side || column >= side {
                return Err(DamageError::Coordinate);
            }
            let owner = core
                .cell_owners
                .get(row * side + column)
                .ok_or(DamageError::Coordinate)?;
            if owner.kind == 4 {
                counts.entry(owner.owner_id).or_insert([0; 24])
                    [owner.bit_offset as usize / EH_CODEWORD_BITS] += 1;
            }
        }
    }
    let omitted = effect
        .omitted_unit_ids
        .iter()
        .copied()
        .collect::<BTreeSet<_>>();
    if omitted.len() != effect.omitted_unit_ids.len() {
        return Err(DamageError::Duplicate);
    }
    let mut units = BTreeMap::new();
    for unit in &core.units {
        let state = if omitted.contains(&unit.physical_unit_id) {
            OracleUnitState::Missing
        } else {
            let erased_counts = erased
                .get(&unit.physical_unit_id)
                .copied()
                .unwrap_or([0; 24]);
            let changed_counts = changed
                .get(&unit.physical_unit_id)
                .copied()
                .unwrap_or([0; 24]);
            if erased_counts.iter().any(|count| *count > 3)
                || changed_counts.iter().any(|count| *count > 1)
            {
                OracleUnitState::Corrupt
            } else if erased_counts.iter().any(|count| *count != 0)
                || changed_counts.iter().any(|count| *count != 0)
            {
                OracleUnitState::Recovered
            } else {
                OracleUnitState::Verified
            }
        };
        units.insert(unit.physical_unit_id, state);
    }
    let mut output = Vec::with_capacity(core.sections.len());
    for section in &core.sections {
        let mut copies = Vec::new();
        for copy in 0..section.copy_count {
            let states = core
                .units
                .iter()
                .filter(|unit| {
                    unit.section_id == section.section_id
                        && unit.semantic_copy_id == u16::from(copy)
                })
                .map(|unit| units[&unit.physical_unit_id])
                .collect::<Vec<_>>();
            if states.is_empty() {
                return Err(DamageError::Reconstruction);
            }
            copies.push(states);
        }
        let state = if copies
            .iter()
            .any(|copy| copy.iter().all(|state| *state == OracleUnitState::Verified))
        {
            SectionState::Verified
        } else if copies.iter().any(|copy| {
            copy.iter().all(|state| {
                matches!(
                    state,
                    OracleUnitState::Verified | OracleUnitState::Recovered
                )
            })
        }) {
            SectionState::Recovered
        } else if copies
            .iter()
            .flatten()
            .any(|state| *state == OracleUnitState::Corrupt)
        {
            SectionState::Corrupt
        } else if copies
            .iter()
            .flatten()
            .any(|state| *state == OracleUnitState::Missing)
        {
            SectionState::Incomplete
        } else {
            SectionState::Unknown
        };
        output.push((section.section_id, state));
    }
    Ok(output)
}

pub fn evaluator_states(
    result: &RecoveryResult,
    clean: &ManifestationCore,
) -> Vec<(u32, SectionState)> {
    let rows = result
        .sections
        .iter()
        .map(|row| (row.section_id, row.state))
        .collect::<BTreeMap<_, _>>();
    clean
        .sections
        .iter()
        .map(|section| {
            (
                section.section_id,
                rows.get(&section.section_id)
                    .copied()
                    .unwrap_or(SectionState::Unknown),
            )
        })
        .collect()
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

/// Serialize a bare compact canonical JSON array.  Manifest-v0 only permits an
/// object at top level, so serialize a one-key object with the same canonical
/// writer and remove that fixed framing.  A bare array has no trailing LF.
fn canonical_array(rows: Vec<ManifestValue>) -> Result<Vec<u8>> {
    let wrapped = serialize_manifest(&object([("rows", ManifestValue::Array(rows))]))
        .map_err(|_| DamageError::Reconstruction)?;
    const PREFIX: &[u8] = b"{\"rows\":";
    const SUFFIX: &[u8] = b"}\n";
    if !wrapped.starts_with(PREFIX) || !wrapped.ends_with(SUFFIX) {
        return Err(DamageError::Reconstruction);
    }
    Ok(wrapped[PREFIX.len()..wrapped.len() - SUFFIX.len()].to_vec())
}

fn recovered_stream(result: &RecoveryResult, tier_id: u32) -> Option<Vec<u8>> {
    let sections = result
        .sections
        .iter()
        .filter_map(|row| row.envelope.as_ref())
        .filter_map(|raw| decode_section(raw).ok())
        .map(|row| (row.section_id, row))
        .collect::<BTreeMap<_, _>>();
    let inventory = sections
        .get(&1)
        .and_then(|section| decode_inventory(&section.payload).ok())?;
    let tier_section = sections.get(&tier_id)?;
    let tier = decode_tier_frame(&tier_section.payload, tier_id).ok()?;
    validate_tier_against_inventory(&tier, tier_section, &inventory).ok()?;
    let bodies = tier
        .body_section_ids
        .iter()
        .map(|id| {
            sections
                .get(id)
                .map(|section| (*id, section.payload.clone()))
        })
        .collect::<Option<BTreeMap<_, _>>>()?;
    assemble_content_stream(&tier, &bodies).ok()
}

/// Render the exact frozen decoder-result schema from decoder-owned state,
/// including its observation-derived logical resource projection.
pub fn render_decoder_result(channel: &str, result: &RecoveryResult) -> Result<(Vec<u8>, String)> {
    if !matches!(channel, "OBS_BITS" | "OBS_MATRIX" | "OBS_UNITS") {
        return Err(DamageError::Channel);
    }
    let profile_id = result
        .profile_version
        .and_then(profile_by_version)
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
                        .map_or_else(|| "0".repeat(64), |raw| observation_sha256(raw)),
                ),
            ),
        ])
    });
    let fragment_rows = result.fragments.iter().map(|row| {
        object([
            ("input_id", ManifestValue::U64(u64::from(row.input_id))),
            (
                "profile_id",
                string(
                    row.profile_version
                        .and_then(profile_by_version)
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
            ("state", string(fragment_state_name(row.state))),
            ("common_block_sha256", string(&row.common_block_sha256)),
        ])
    });
    let fragment_bytes = canonical_array(fragment_rows.collect())?;
    let required = recovered_stream(result, 2);
    let all = recovered_stream(result, 3);
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
                string(profile_by_version(row.profile_version).unwrap().id),
            ),
            ("mapping_sha256", string(&row.mapping_sha256)),
        ])
    });
    let value = object([
        ("schema", string("golden-board.m2-damage-decoder-result/v0")),
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
                    .map_or_else(|| "0".repeat(64), |raw| observation_sha256(raw)),
            ),
        ),
        (
            "m2_all_stream_sha256",
            string(
                &all.as_ref()
                    .map_or_else(|| "0".repeat(64), |raw| observation_sha256(raw)),
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
    let raw = serialize_manifest(&value).map_err(|_| DamageError::Reconstruction)?;
    let sha256 = observation_sha256(&raw);
    Ok((raw, sha256))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::candidate_recipe::build_eh_recipe_package;
    use crate::carrier::{build_manifestation_core, render_semantic_envelope};
    use crate::policy::load_profile_policy;
    use gb_slice::{SliceInputs, compile_slice_v0};

    fn core(profile_version: u16) -> ManifestationCore {
        let compiled = compile_slice_v0(SliceInputs {
            declaration: include_bytes!("../../../studies/m2/slice-v0.json"),
            content_fixture: include_bytes!("../../../conformance/content-v0.json"),
            chess_fixture: include_bytes!("../../../conformance/chess-v0.json"),
            game_set: include_bytes!("../../../reports/game-set-v0.bin"),
            content_spec: include_bytes!("../../../spec/content-v0.md"),
            constants: include_bytes!("../../../spec/constants-v0.toml"),
            curriculum: include_bytes!("../../../spec/curriculum-v0.toml"),
        })
        .unwrap();
        let policy_raw = include_bytes!("../../../spec/profile-policy-v0.toml");
        let policy = load_profile_policy(policy_raw).unwrap();
        let semantic = render_semantic_envelope(
            &policy,
            policy_raw,
            &compiled,
            include_bytes!("../../../spec/curriculum-v0.toml"),
        )
        .unwrap();
        build_manifestation_core(
            profile_version,
            include_bytes!("../../../spec/route-data-v0.json"),
            &build_eh_recipe_package(profile_version).unwrap(),
            &semantic,
            7_141,
            16_384,
        )
        .unwrap()
    }

    #[test]
    fn channels_reject_noncanonical_shapes() {
        assert_eq!(ObsBits::parse(&[0, 0, 0, 1, 0x81]), Err(DamageError::Value));
        assert_eq!(ObsMatrix::parse(&[0, 1, 3]), Err(DamageError::Value));
        assert_eq!(ObsUnits::parse(&[0, 0, 0, 1]), Err(DamageError::Length));
        let (boundary, sha256) = section_attempt_boundary_kat().unwrap();
        assert_eq!(boundary.len(), 307);
        assert_eq!(
            sha256,
            "4ad1468cd6cac6774b95e997d37c6fb420ff94cc0aa82595aeaa7b356440a68b"
        );
    }

    #[test]
    fn sampling_is_bounded_and_without_replacement() {
        assert_eq!(
            sample_without_replacement(0, 0, 0).unwrap(),
            Vec::<usize>::new()
        );
        assert_eq!(
            sample_without_replacement(3, 4, 0),
            Err(DamageError::SamplePopulation)
        );
        let sample = sample_without_replacement(10_000, 512, 5_134_751_402_299_490_304).unwrap();
        assert_eq!(sample.len(), 512);
        assert_eq!(sample.iter().copied().collect::<BTreeSet<_>>().len(), 512);
    }

    #[test]
    fn d2_has_exact_anchor_prefix_and_case_count() {
        let placements = d2_placements(1696).unwrap();
        assert_eq!(placements.len(), 256);
        assert_eq!(placements[0], Coordinate { row: 0, column: 0 });
        assert_eq!(
            placements[1],
            Coordinate {
                row: 0,
                column: 821
            }
        );
        assert_eq!(
            placements[2],
            Coordinate {
                row: 0,
                column: 1643
            }
        );
        assert_eq!(
            placements[8],
            Coordinate {
                row: 1643,
                column: 1643
            }
        );
    }

    #[test]
    fn decoder_consumes_serialized_channels_and_recovers_without_clean_input() {
        let core = core(1);
        let d0 = decode_bits(&core.carrier_bytes).unwrap();
        assert_eq!(d0.profile_version, Some(1));
        assert_eq!(d0.artifact_state, ArtifactState::Exact);
        assert_eq!(wrong_accept_count(&d0, &core), 0);
        assert!(required_closure_exact(&d0, &core));

        let d1_raw = erase_shell_sector(&core, 0, None).unwrap();
        let d1 = decode_matrix(&d1_raw).unwrap();
        assert_eq!(d1.profile_version, Some(1));
        assert_eq!(d1.artifact_state, ArtifactState::Exact);
        assert_eq!(wrong_accept_count(&d1, &core), 0);

        let mut entries = clean_unit_entries(&core);
        entries.remove(0);
        let d4_raw = serialize_obs_units(&entries).unwrap();
        let d4 = decode_units(&d4_raw).unwrap();
        assert_eq!(d4.profile_version, Some(1));
        assert!(required_closure_exact(&d4, &core));
        assert_eq!(wrong_accept_count(&d4, &core), 0);
    }

    #[test]
    fn ownership_oracle_matches_decoder_for_real_d2_and_d3_cases() {
        let core = core(1);
        let top_left = d2_placements(usize::from(core.mapping.interior_side)).unwrap()[0];
        let square = d2_square_side(usize::from(core.mapping.interior_side));
        let raw = erase_square(&core, top_left, square).unwrap();
        let decoded = decode_matrix(&raw).unwrap();
        let erased_coordinates = (0..square)
            .flat_map(|row| {
                (0..square).map(move |column| Coordinate {
                    row: top_left.row + core.shell_width as u32 + row as u32,
                    column: top_left.column + core.shell_width as u32 + column as u32,
                })
            })
            .collect();
        let expected = oracle_section_states(
            &core,
            &DamageEffect {
                erased_coordinates,
                ..DamageEffect::default()
            },
        )
        .unwrap();
        assert_eq!(evaluator_states(&decoded, &core), expected);
        assert!(required_closure_exact(&decoded, &core));
        assert_eq!(wrong_accept_count(&decoded, &core), 0);

        let coordinates = d3_coordinates(&core, 5_134_751_402_299_490_304, 0).unwrap();
        let raw = substitute_coordinates(&core, &coordinates).unwrap();
        let decoded = decode_matrix(&raw).unwrap();
        let expected = oracle_section_states(
            &core,
            &DamageEffect {
                substituted_coordinates: coordinates,
                ..DamageEffect::default()
            },
        )
        .unwrap();
        assert_eq!(evaluator_states(&decoded, &core), expected);
        assert!(required_closure_exact(&decoded, &core));
        assert_eq!(wrong_accept_count(&decoded, &core), 0);
    }

    #[test]
    fn clean_resource_projection_is_independently_charged() {
        verify_damage_owner().unwrap();
        assert_eq!(
            (1..=6)
                .map(|version| {
                    let package = neutral_package(version).unwrap();
                    (
                        package.recipe_primitive_steps(30).unwrap(),
                        package.recipe_peak_scratch_bytes(30).unwrap(),
                    )
                })
                .collect::<Vec<_>>(),
            vec![
                (80_435, 4_613),
                (80_435, 4_613),
                (80_435, 4_613),
                (80_435, 4_613),
                (1_698_049, 7_688),
                (1_698_049, 7_688),
            ]
        );
        let p1_core = core(1);
        let p3_core = core(3);
        let p1 = clean_resource_projection(&p1_core).unwrap();
        let p3 = clean_resource_projection(&p3_core).unwrap();
        assert_eq!(
            p1,
            ResourceProjection {
                section_attempts: 137,
                primitive_steps: 12_849_712_464,
                peak_scratch_bytes: 6_163,
            }
        );
        assert_eq!(
            p3,
            ResourceProjection {
                section_attempts: 135,
                primitive_steps: 14_092_915_824,
                peak_scratch_bytes: 6_163,
            }
        );

        let p1_result = decode_bits(&p1_core.carrier_bytes).unwrap();
        let p3_result = decode_bits(&p3_core.carrier_bytes).unwrap();
        assert_eq!(p1_result.resource, p1);
        assert_eq!(p3_result.resource, p3);
        assert!(recovered_stream(&p1_result, 2).is_some());
        assert!(recovered_stream(&p1_result, 3).is_some());
        assert!(recovered_stream(&p3_result, 2).is_some());
        assert!(recovered_stream(&p3_result, 3).is_some());
        let (p1_raw, p1_sha256) = render_decoder_result("OBS_BITS", &p1_result).unwrap();
        let (p3_raw, p3_sha256) = render_decoder_result("OBS_BITS", &p3_result).unwrap();
        gb_foundation::validate_canonical_manifest(&p1_raw).unwrap();
        gb_foundation::validate_canonical_manifest(&p3_raw).unwrap();
        assert_eq!(p1_raw.len(), 18_125);
        assert_eq!(
            p1_sha256,
            "bc2a853b5dd4be7bf6686807efbe65dc00e9af7f98f4a9dd2300ee1299640779"
        );
        assert_eq!(p3_raw.len(), 17_879);
        assert_eq!(
            p3_sha256,
            "d6aa54580c2bf7f12073147a6b910b8c7dbea9c67c22639916befbdf7d363a97"
        );

        let p3_omit_last =
            omitted_unit_observation(&p3_core, &[u32::try_from(p3_core.units.len()).unwrap()])
                .unwrap();
        let p3_omit_result = decode_observation("OBS_UNITS", &p3_omit_last);
        assert_eq!(
            p3_omit_result.resource,
            ResourceProjection {
                section_attempts: 135,
                primitive_steps: 20_278_972_992,
                peak_scratch_bytes: 7_688,
            }
        );
        let (_, p3_omit_sha256) = render_decoder_result("OBS_UNITS", &p3_omit_result).unwrap();
        assert_eq!(
            p3_omit_sha256,
            "afe47e50d3d5464e150aa5b9ee67c666eaadde3e87fd2d7c66133dbe93cdd597"
        );
    }

    #[test]
    fn d7_mutants_are_observation_only_and_never_wrong_accept() {
        let p1 = core(1);
        let p3 = core(3);
        for ordinal in 0..3 {
            let decoded = decode_bits(&mapping_mutant(&p1, ordinal).unwrap());
            if let Ok(decoded) = decoded {
                assert_eq!(wrong_accept_count(&decoded, &p1), 0);
            }
        }
        for (case, raw) in [
            local_check_mutant(&p1, false).unwrap(),
            local_check_mutant(&p1, true).unwrap(),
            section_check_mutant(&p1, true).unwrap(),
            section_check_mutant(&p1, false).unwrap(),
            code_mutant(&p1, 0).unwrap(),
            code_mutant(&p1, 1).unwrap(),
            code_mutant(&p1, 2).unwrap(),
            cross_profile_splice(&p1, 2).unwrap(),
            cross_profile_splice(&p1, 3).unwrap(),
            cross_profile_splice(&p1, 4).unwrap(),
            cross_profile_splice(&p1, 5).unwrap(),
            cross_profile_splice(&p1, 6).unwrap(),
            valid_copy_conflict(&p1).unwrap(),
            missing_unit_one_beyond(&p1).unwrap().1,
        ]
        .into_iter()
        .enumerate()
        {
            let decoded =
                decode_units(&raw).unwrap_or_else(|error| panic!("unit mutant {case}: {error:?}"));
            assert_eq!(wrong_accept_count(&decoded, &p1), 0);
        }
        let conflict = decode_bits(&route_conflict(&p1, &p3).unwrap()).unwrap();
        assert_eq!(conflict.artifact_state, ArtifactState::Exact);
        assert_eq!(conflict.profile_version, Some(1));
        assert!(
            conflict
                .accepted_hypotheses
                .iter()
                .any(|row| row.profile_version == 3)
        );
        assert_eq!(wrong_accept_count(&conflict, &p1), 0);
        for (errors, erasures) in [(2, 0), (1, 2), (0, 4)] {
            let decoded = decode_matrix(&algebraic_one_beyond(&p1, errors, erasures).unwrap());
            if let Ok(decoded) = decoded {
                assert_eq!(wrong_accept_count(&decoded, &p1), 0);
            }
        }
        for scratch in [false, true] {
            let decoded = decode_bits(&resource_route_one_beyond(&p1, scratch).unwrap()).unwrap();
            assert!(all_sections_exact(&decoded, &p1));
            assert_eq!(wrong_accept_count(&decoded, &p1), 0);
        }
        assert_eq!(
            decode_bits(&geometry_one_beyond()),
            Err(DamageError::Length)
        );
    }
}
