use std::collections::{BTreeMap, BTreeSet};

pub mod candidate;
pub mod candidate_recipe;
pub mod carrier;
pub mod damage;
pub mod damage_v1;
pub mod gate8_v1;
pub mod independence_v1;
pub mod policy;
pub mod recipe;

pub const MAX_RAW_BITS: usize = 4_194_304;
pub const MAX_SIDE: usize = 2_048;
pub const MAX_BLOCKS_PER_COPY: usize = 65_535;
pub const MAX_ENVELOPE_BYTES: usize = 1_048_576;
pub const MAX_DEPENDENCIES: usize = 4_095;
pub const MAX_INVENTORY_ENTRIES: usize = 4_096;
pub const MAX_TIER_BODY_IDS: usize = 4_094;
pub const MAX_SECTION_CANDIDATES: usize = 4_096;

pub const COMMON_BLOCK_BYTES: usize = 191;
pub const COMMON_PAYLOAD_BYTES: usize = 157;
pub const LOCAL_CHECK_DOMAIN: [u8; 8] = [0xd3, 0x91, 0x6a, 0xc4, 0x72, 0x08, 0xbe, 0x5f];
pub const SECTION_CHECK_DOMAIN: [u8; 8] = [0x4b, 0xe2, 0x19, 0x77, 0xa0, 0x3c, 0x65, 0xd8];

pub const SECTION_INVENTORY: u16 = 1;
pub const SECTION_TIER_FRAME: u16 = 2;
pub const SECTION_CONTENT_BODY: u16 = 3;
pub const SECTION_CAPACITY_PROBE: u16 = 4;
pub const SECTION_RESERVE_PROBE: u16 = 5;
pub const SECTION_LOAD_PROBE: u16 = 6;

pub const CLOSURE_M2_REQUIRED: u8 = 128;
pub const CLOSURE_M2_ALL_ONLY: u8 = 129;
pub const CHECK_CRC32C: u8 = 1;
pub const CHECK_CRC64_ECMA: u8 = 2;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum RejectCode {
    RawLength = 1,
    RawValue = 2,
    RawGeometry = 3,
    ShellGeometry = 4,
    ResourceLimit = 5,
    BlockFraming = 6,
    FragmentShape = 7,
    LocalCheck = 8,
    FragmentConflict = 9,
    SectionIncomplete = 10,
    SectionFraming = 11,
    SectionCheck = 12,
    Inventory = 13,
    TierFrame = 14,
    Dependency = 15,
    ContentStream = 16,
    Ambiguous = 17,
    Recipe = 18,
    TrailingData = 19,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct BootstrapError {
    pub code: RejectCode,
    pub offset: Option<usize>,
}

impl BootstrapError {
    const fn new(code: RejectCode) -> Self {
        Self { code, offset: None }
    }

    const fn at(code: RejectCode, offset: usize) -> Self {
        Self {
            code,
            offset: Some(offset),
        }
    }
}

pub type Result<T> = std::result::Result<T, BootstrapError>;

fn checked_add(left: usize, right: usize) -> Result<usize> {
    left.checked_add(right)
        .ok_or(BootstrapError::new(RejectCode::ResourceLimit))
}

fn checked_mul(left: usize, right: usize) -> Result<usize> {
    left.checked_mul(right)
        .ok_or(BootstrapError::new(RejectCode::ResourceLimit))
}

fn read_u16(raw: &[u8], offset: usize, code: RejectCode) -> Result<u16> {
    let end = offset
        .checked_add(2)
        .ok_or(BootstrapError::new(RejectCode::ResourceLimit))?;
    let bytes = raw
        .get(offset..end)
        .ok_or(BootstrapError::at(code, offset))?;
    Ok(u16::from_be_bytes([bytes[0], bytes[1]]))
}

fn read_u32(raw: &[u8], offset: usize, code: RejectCode) -> Result<u32> {
    let end = offset
        .checked_add(4)
        .ok_or(BootstrapError::new(RejectCode::ResourceLimit))?;
    let bytes = raw
        .get(offset..end)
        .ok_or(BootstrapError::at(code, offset))?;
    Ok(u32::from_be_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]))
}

fn known_section_type(value: u16) -> bool {
    (SECTION_INVENTORY..=SECTION_LOAD_PROBE).contains(&value)
}

fn known_closure(value: u8) -> bool {
    matches!(value, CLOSURE_M2_REQUIRED | CLOSURE_M2_ALL_ONLY)
}

fn known_check(value: u8) -> bool {
    matches!(value, CHECK_CRC32C | CHECK_CRC64_ECMA)
}

fn check_strict_ids(ids: &[u32], owner: RejectCode, self_id: Option<u32>) -> Result<()> {
    if ids.len() > MAX_DEPENDENCIES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    let mut previous = 0u32;
    for (index, id) in ids.iter().copied().enumerate() {
        if id == 0 || index != 0 && id <= previous || Some(id) == self_id {
            return Err(BootstrapError::new(owner));
        }
        previous = id;
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct EntryHypothesis {
    pub transform: u8,
    pub polarity: u8,
}

pub const ENTRY_HYPOTHESES: [EntryHypothesis; 16] = [
    EntryHypothesis {
        transform: 0,
        polarity: 0,
    },
    EntryHypothesis {
        transform: 0,
        polarity: 1,
    },
    EntryHypothesis {
        transform: 1,
        polarity: 0,
    },
    EntryHypothesis {
        transform: 1,
        polarity: 1,
    },
    EntryHypothesis {
        transform: 2,
        polarity: 0,
    },
    EntryHypothesis {
        transform: 2,
        polarity: 1,
    },
    EntryHypothesis {
        transform: 3,
        polarity: 0,
    },
    EntryHypothesis {
        transform: 3,
        polarity: 1,
    },
    EntryHypothesis {
        transform: 4,
        polarity: 0,
    },
    EntryHypothesis {
        transform: 4,
        polarity: 1,
    },
    EntryHypothesis {
        transform: 5,
        polarity: 0,
    },
    EntryHypothesis {
        transform: 5,
        polarity: 1,
    },
    EntryHypothesis {
        transform: 6,
        polarity: 0,
    },
    EntryHypothesis {
        transform: 6,
        polarity: 1,
    },
    EntryHypothesis {
        transform: 7,
        polarity: 0,
    },
    EntryHypothesis {
        transform: 7,
        polarity: 1,
    },
];

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RawObservation {
    side: usize,
    bits: Vec<u8>,
}

impl RawObservation {
    pub fn parse(values: &[u8], declared_count: usize) -> Result<Self> {
        if declared_count == 0 || declared_count > MAX_RAW_BITS || values.len() != declared_count {
            return Err(BootstrapError::new(RejectCode::RawLength));
        }
        for (offset, value) in values.iter().copied().enumerate() {
            if value > 1 {
                return Err(BootstrapError::at(RejectCode::RawValue, offset));
            }
        }
        let side = declared_count.isqrt();
        if side > MAX_SIDE || side.checked_mul(side) != Some(declared_count) {
            return Err(BootstrapError::new(RejectCode::RawGeometry));
        }
        Ok(Self {
            side,
            bits: values.to_vec(),
        })
    }

    pub fn side(&self) -> usize {
        self.side
    }

    pub fn normalized_bit(
        &self,
        hypothesis: EntryHypothesis,
        row: usize,
        column: usize,
    ) -> Result<u8> {
        if row >= self.side
            || column >= self.side
            || hypothesis.transform > 7
            || hypothesis.polarity > 1
        {
            return Err(BootstrapError::new(RejectCode::RawGeometry));
        }
        let last = self.side - 1;
        let (observed_row, observed_column) = match hypothesis.transform {
            0 => (row, column),
            1 => (last - column, row),
            2 => (last - row, last - column),
            3 => (column, last - row),
            4 => (row, last - column),
            5 => (last - column, last - row),
            6 => (last - row, column),
            7 => (column, row),
            _ => unreachable!(),
        };
        Ok(self.bits[observed_row * self.side + observed_column] ^ hypothesis.polarity)
    }
}

fn validate_shell(side: usize, width: usize) -> Result<usize> {
    if side > MAX_SIDE {
        return Err(BootstrapError::new(RejectCode::ShellGeometry));
    }
    let maximum = side
        .checked_sub(8)
        .map(|value| (value / 2).min(128))
        .ok_or(BootstrapError::new(RejectCode::ShellGeometry))?;
    if width < 8 || width % 8 != 0 || width > maximum {
        return Err(BootstrapError::new(RejectCode::ShellGeometry));
    }
    side.checked_sub(width)
        .ok_or(BootstrapError::new(RejectCode::ShellGeometry))
}

pub fn sector_cell(
    side: usize,
    width: usize,
    sector: u8,
    local_row: usize,
    local_column: usize,
) -> Result<(usize, usize)> {
    let span = validate_shell(side, width)?;
    if sector > 3 || local_row >= width || local_column >= span {
        return Err(BootstrapError::new(RejectCode::ShellGeometry));
    }
    let last = side - 1;
    Ok(match sector {
        0 => (local_row, local_column),
        1 => (local_column, last - local_row),
        2 => (last - local_row, last - local_column),
        3 => (last - local_column, local_row),
        _ => unreachable!(),
    })
}

pub fn sector_cell_at(
    side: usize,
    width: usize,
    sector: u8,
    index: usize,
) -> Result<(usize, usize)> {
    let span = validate_shell(side, width)?;
    let count = checked_mul(width, span)?;
    if index >= count {
        return Err(BootstrapError::new(RejectCode::ShellGeometry));
    }
    sector_cell(side, width, sector, index / span, index % span)
}

pub fn route_headroom_cells(instruction_cells: usize, discriminator_cells: usize) -> Result<usize> {
    let five_percent = instruction_cells
        .checked_add(19)
        .ok_or(BootstrapError::new(RejectCode::ResourceLimit))?
        / 20;
    let four_discriminators = checked_mul(4, discriminator_cells)?;
    Ok(five_percent.max(four_discriminators))
}

pub fn crc32c(bytes: &[u8]) -> u32 {
    let mut register = 0xffff_ffffu32;
    for byte in bytes {
        register ^= u32::from(*byte);
        for _ in 0..8 {
            register = if register & 1 == 1 {
                (register >> 1) ^ 0x82f6_3b78
            } else {
                register >> 1
            };
        }
    }
    register ^ 0xffff_ffff
}

pub fn crc64_ecma(bytes: &[u8]) -> u64 {
    let mut register = 0u64;
    for byte in bytes {
        register ^= u64::from(*byte) << 56;
        for _ in 0..8 {
            register = if register & (1u64 << 63) != 0 {
                (register << 1) ^ 0x42f0_e1eb_a9ea_3693
            } else {
                register << 1
            };
        }
    }
    register
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CommonBlock {
    pub profile_version: u16,
    pub section_id: u32,
    pub semantic_copy_id: u16,
    pub section_type: u16,
    pub section_version: u16,
    pub fragment_index: u16,
    pub fragment_count: u16,
    pub section_envelope_length: u32,
    pub payload: Vec<u8>,
}

fn validate_common_fields(block: &CommonBlock) -> Result<()> {
    if block.section_id == 0 || !known_section_type(block.section_type) {
        return Err(BootstrapError::new(RejectCode::BlockFraming));
    }
    let envelope_length = usize::try_from(block.section_envelope_length)
        .map_err(|_| BootstrapError::new(RejectCode::ResourceLimit))?;
    if envelope_length == 0 || envelope_length > MAX_ENVELOPE_BYTES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    let count = envelope_length
        .checked_add(COMMON_PAYLOAD_BYTES - 1)
        .ok_or(BootstrapError::new(RejectCode::ResourceLimit))?
        / COMMON_PAYLOAD_BYTES;
    if count == 0 || count > MAX_BLOCKS_PER_COPY || usize::from(block.fragment_count) != count {
        return Err(BootstrapError::new(RejectCode::FragmentShape));
    }
    let index = usize::from(block.fragment_index);
    if index >= count {
        return Err(BootstrapError::new(RejectCode::FragmentShape));
    }
    let expected_length = if index + 1 == count {
        envelope_length - COMMON_PAYLOAD_BYTES * (count - 1)
    } else {
        COMMON_PAYLOAD_BYTES
    };
    if block.payload.len() != expected_length {
        return Err(BootstrapError::new(RejectCode::FragmentShape));
    }
    Ok(())
}

pub fn encode_common_block(block: &CommonBlock) -> Result<[u8; COMMON_BLOCK_BYTES]> {
    validate_common_fields(block)?;
    let mut raw = [0u8; COMMON_BLOCK_BYTES];
    raw[0..2].copy_from_slice(&block.profile_version.to_be_bytes());
    raw[2..4].copy_from_slice(&0u16.to_be_bytes());
    raw[4..8].copy_from_slice(&block.section_id.to_be_bytes());
    raw[8..10].copy_from_slice(&block.semantic_copy_id.to_be_bytes());
    raw[10..12].copy_from_slice(&block.section_type.to_be_bytes());
    raw[12..14].copy_from_slice(&block.section_version.to_be_bytes());
    raw[14..16].copy_from_slice(&0u16.to_be_bytes());
    raw[16..18].copy_from_slice(&block.fragment_index.to_be_bytes());
    raw[18..20].copy_from_slice(&block.fragment_count.to_be_bytes());
    raw[20..22].copy_from_slice(&(block.payload.len() as u16).to_be_bytes());
    raw[22..26].copy_from_slice(&block.section_envelope_length.to_be_bytes());
    raw[26..30].copy_from_slice(&0u32.to_be_bytes());
    raw[30..30 + block.payload.len()].copy_from_slice(&block.payload);
    let mut preimage = Vec::with_capacity(LOCAL_CHECK_DOMAIN.len() + 187);
    preimage.extend_from_slice(&LOCAL_CHECK_DOMAIN);
    preimage.extend_from_slice(&raw[..187]);
    raw[187..].copy_from_slice(&crc32c(&preimage).to_be_bytes());
    Ok(raw)
}

pub fn decode_common_block(raw: &[u8], expected_profile_version: u16) -> Result<CommonBlock> {
    if raw.len() != COMMON_BLOCK_BYTES {
        return Err(BootstrapError::new(RejectCode::BlockFraming));
    }
    let profile_version = read_u16(raw, 0, RejectCode::BlockFraming)?;
    let grammar_version = read_u16(raw, 2, RejectCode::BlockFraming)?;
    let section_id = read_u32(raw, 4, RejectCode::BlockFraming)?;
    let semantic_copy_id = read_u16(raw, 8, RejectCode::BlockFraming)?;
    let section_type = read_u16(raw, 10, RejectCode::BlockFraming)?;
    let section_version = read_u16(raw, 12, RejectCode::BlockFraming)?;
    let flags = read_u16(raw, 14, RejectCode::BlockFraming)?;
    let fragment_index = read_u16(raw, 16, RejectCode::FragmentShape)?;
    let fragment_count = read_u16(raw, 18, RejectCode::FragmentShape)?;
    let valid_payload_length = read_u16(raw, 20, RejectCode::FragmentShape)?;
    let section_envelope_length = read_u32(raw, 22, RejectCode::FragmentShape)?;
    let reserved = read_u32(raw, 26, RejectCode::BlockFraming)?;
    if profile_version != expected_profile_version
        || grammar_version != 0
        || section_id == 0
        || !known_section_type(section_type)
        || flags != 0
        || reserved != 0
    {
        return Err(BootstrapError::new(RejectCode::BlockFraming));
    }
    let payload_length = usize::from(valid_payload_length);
    if payload_length == 0 || payload_length > COMMON_PAYLOAD_BYTES {
        return Err(BootstrapError::new(RejectCode::FragmentShape));
    }
    let block = CommonBlock {
        profile_version,
        section_id,
        semantic_copy_id,
        section_type,
        section_version,
        fragment_index,
        fragment_count,
        section_envelope_length,
        payload: raw[30..30 + payload_length].to_vec(),
    };
    validate_common_fields(&block)?;
    if raw[30 + payload_length..187].iter().any(|byte| *byte != 0) {
        return Err(BootstrapError::new(RejectCode::FragmentShape));
    }
    let mut preimage = Vec::with_capacity(LOCAL_CHECK_DOMAIN.len() + 187);
    preimage.extend_from_slice(&LOCAL_CHECK_DOMAIN);
    preimage.extend_from_slice(&raw[..187]);
    let stored = read_u32(raw, 187, RejectCode::LocalCheck)?;
    if crc32c(&preimage) != stored {
        return Err(BootstrapError::new(RejectCode::LocalCheck));
    }
    Ok(block)
}

pub fn fragment_envelope(
    profile_version: u16,
    section_id: u32,
    semantic_copy_id: u16,
    section_type: u16,
    section_version: u16,
    envelope: &[u8],
) -> Result<Vec<[u8; COMMON_BLOCK_BYTES]>> {
    if envelope.is_empty() || envelope.len() > MAX_ENVELOPE_BYTES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    let decoded = decode_section(envelope)?;
    if decoded.section_id != section_id
        || decoded.section_type != section_type
        || decoded.section_version != section_version
    {
        return Err(BootstrapError::new(RejectCode::SectionFraming));
    }
    let count = envelope
        .len()
        .checked_add(COMMON_PAYLOAD_BYTES - 1)
        .ok_or(BootstrapError::new(RejectCode::ResourceLimit))?
        / COMMON_PAYLOAD_BYTES;
    if count > MAX_BLOCKS_PER_COPY {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    let count_u16 =
        u16::try_from(count).map_err(|_| BootstrapError::new(RejectCode::ResourceLimit))?;
    let envelope_length = u32::try_from(envelope.len())
        .map_err(|_| BootstrapError::new(RejectCode::ResourceLimit))?;
    let mut blocks = Vec::with_capacity(count);
    for index in 0..count {
        let start = index * COMMON_PAYLOAD_BYTES;
        let end = envelope.len().min(start + COMMON_PAYLOAD_BYTES);
        blocks.push(encode_common_block(&CommonBlock {
            profile_version,
            section_id,
            semantic_copy_id,
            section_type,
            section_version,
            fragment_index: index as u16,
            fragment_count: count_u16,
            section_envelope_length: envelope_length,
            payload: envelope[start..end].to_vec(),
        })?);
    }
    Ok(blocks)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RecoveryQuality {
    Verified,
    Recovered,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FragmentWitness {
    pub raw_block: [u8; COMMON_BLOCK_BYTES],
    pub quality: RecoveryQuality,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SectionWitness {
    pub envelope: Vec<u8>,
    pub all_units_verified: bool,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CanonicalSection {
    pub envelope: Vec<u8>,
    pub quality: RecoveryQuality,
}

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
struct CopyIdentity {
    profile_version: u16,
    section_id: u32,
    semantic_copy_id: u16,
    section_type: u16,
    section_version: u16,
    fragment_count: u16,
    section_envelope_length: u32,
}

fn copy_identity(block: &CommonBlock) -> CopyIdentity {
    CopyIdentity {
        profile_version: block.profile_version,
        section_id: block.section_id,
        semantic_copy_id: block.semantic_copy_id,
        section_type: block.section_type,
        section_version: block.section_version,
        fragment_count: block.fragment_count,
        section_envelope_length: block.section_envelope_length,
    }
}

pub fn assemble_semantic_copy(
    witnesses: &[FragmentWitness],
    expected_profile_version: u16,
) -> Result<SectionWitness> {
    if witnesses.len() > MAX_BLOCKS_PER_COPY {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    let first = witnesses
        .first()
        .ok_or(BootstrapError::new(RejectCode::SectionIncomplete))?;
    let first_block = decode_common_block(&first.raw_block, expected_profile_version)?;
    let identity = copy_identity(&first_block);
    let count = usize::from(identity.fragment_count);
    if count == 0 || count > MAX_BLOCKS_PER_COPY {
        return Err(BootstrapError::new(RejectCode::FragmentShape));
    }
    let mut selected: BTreeMap<u16, (CommonBlock, bool)> = BTreeMap::new();
    for witness in witnesses {
        let block = decode_common_block(&witness.raw_block, expected_profile_version)?;
        if copy_identity(&block) != identity {
            return Err(BootstrapError::new(RejectCode::FragmentConflict));
        }
        let verified = witness.quality == RecoveryQuality::Verified;
        match selected.get_mut(&block.fragment_index) {
            Some((prior, any_verified)) => {
                if *prior != block {
                    return Err(BootstrapError::new(RejectCode::FragmentConflict));
                }
                *any_verified |= verified;
            }
            None => {
                selected.insert(block.fragment_index, (block, verified));
            }
        }
    }
    if selected.len() != count || selected.keys().copied().ne(0..identity.fragment_count) {
        return Err(BootstrapError::new(RejectCode::SectionIncomplete));
    }
    let envelope_length = usize::try_from(identity.section_envelope_length)
        .map_err(|_| BootstrapError::new(RejectCode::ResourceLimit))?;
    let mut envelope = Vec::with_capacity(envelope_length);
    let mut all_units_verified = true;
    for (_, (block, verified)) in selected {
        envelope.extend_from_slice(&block.payload);
        all_units_verified &= verified;
    }
    if envelope.len() != envelope_length {
        return Err(BootstrapError::new(RejectCode::FragmentShape));
    }
    let decoded = decode_section(&envelope)?;
    if decoded.section_id != identity.section_id
        || decoded.section_type != identity.section_type
        || decoded.section_version != identity.section_version
    {
        return Err(BootstrapError::new(RejectCode::SectionFraming));
    }
    Ok(SectionWitness {
        envelope,
        all_units_verified,
    })
}

pub fn aggregate_section_witnesses(witnesses: &[SectionWitness]) -> Result<CanonicalSection> {
    if witnesses.len() > MAX_SECTION_CANDIDATES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    let first = witnesses
        .first()
        .ok_or(BootstrapError::new(RejectCode::SectionIncomplete))?;
    decode_section(&first.envelope)?;
    let mut any_verified = first.all_units_verified;
    for witness in &witnesses[1..] {
        decode_section(&witness.envelope)?;
        if witness.envelope != first.envelope {
            return Err(BootstrapError::new(RejectCode::Ambiguous));
        }
        any_verified |= witness.all_units_verified;
    }
    Ok(CanonicalSection {
        envelope: first.envelope.clone(),
        quality: if any_verified {
            RecoveryQuality::Verified
        } else {
            RecoveryQuality::Recovered
        },
    })
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SectionEnvelope {
    pub section_id: u32,
    pub section_type: u16,
    pub section_version: u16,
    pub closure_class: u8,
    pub check_id: u8,
    pub dependencies: Vec<u32>,
    pub payload: Vec<u8>,
}

fn validate_envelope_fields(envelope: &SectionEnvelope) -> Result<()> {
    if envelope.section_id == 0
        || !known_section_type(envelope.section_type)
        || !known_closure(envelope.closure_class)
        || !known_check(envelope.check_id)
    {
        return Err(BootstrapError::new(RejectCode::SectionFraming));
    }
    check_strict_ids(
        &envelope.dependencies,
        RejectCode::SectionFraming,
        Some(envelope.section_id),
    )?;
    Ok(())
}

fn check_width(check_id: u8) -> Result<usize> {
    match check_id {
        CHECK_CRC32C => Ok(4),
        CHECK_CRC64_ECMA => Ok(8),
        _ => Err(BootstrapError::new(RejectCode::SectionFraming)),
    }
}

pub fn encode_section(envelope: &SectionEnvelope) -> Result<Vec<u8>> {
    validate_envelope_fields(envelope)?;
    let dependency_bytes = checked_mul(envelope.dependencies.len(), 4)?;
    let check_bytes = check_width(envelope.check_id)?;
    let total = checked_add(
        checked_add(checked_add(18, dependency_bytes)?, envelope.payload.len())?,
        check_bytes,
    )?;
    if total > MAX_ENVELOPE_BYTES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    let dependency_count = u16::try_from(envelope.dependencies.len())
        .map_err(|_| BootstrapError::new(RejectCode::ResourceLimit))?;
    let payload_length = u32::try_from(envelope.payload.len())
        .map_err(|_| BootstrapError::new(RejectCode::ResourceLimit))?;
    let mut raw = Vec::with_capacity(total);
    raw.extend_from_slice(&0u16.to_be_bytes());
    raw.extend_from_slice(&envelope.section_id.to_be_bytes());
    raw.extend_from_slice(&envelope.section_type.to_be_bytes());
    raw.extend_from_slice(&envelope.section_version.to_be_bytes());
    raw.push(envelope.closure_class);
    raw.push(envelope.check_id);
    raw.extend_from_slice(&dependency_count.to_be_bytes());
    raw.extend_from_slice(&payload_length.to_be_bytes());
    for dependency in &envelope.dependencies {
        raw.extend_from_slice(&dependency.to_be_bytes());
    }
    raw.extend_from_slice(&envelope.payload);
    let mut preimage = Vec::with_capacity(SECTION_CHECK_DOMAIN.len() + raw.len());
    preimage.extend_from_slice(&SECTION_CHECK_DOMAIN);
    preimage.extend_from_slice(&raw);
    match envelope.check_id {
        CHECK_CRC32C => raw.extend_from_slice(&crc32c(&preimage).to_be_bytes()),
        CHECK_CRC64_ECMA => raw.extend_from_slice(&crc64_ecma(&preimage).to_be_bytes()),
        _ => unreachable!(),
    }
    Ok(raw)
}

pub fn decode_section(raw: &[u8]) -> Result<SectionEnvelope> {
    if raw.len() > MAX_ENVELOPE_BYTES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    if raw.len() < 22 {
        return Err(BootstrapError::new(RejectCode::SectionFraming));
    }
    let envelope_version = read_u16(raw, 0, RejectCode::SectionFraming)?;
    let section_id = read_u32(raw, 2, RejectCode::SectionFraming)?;
    let section_type = read_u16(raw, 6, RejectCode::SectionFraming)?;
    let section_version = read_u16(raw, 8, RejectCode::SectionFraming)?;
    let closure_class = raw[10];
    let check_id = raw[11];
    if envelope_version != 0
        || section_id == 0
        || !known_section_type(section_type)
        || !known_closure(closure_class)
        || !known_check(check_id)
    {
        return Err(BootstrapError::new(RejectCode::SectionFraming));
    }
    let dependency_count = usize::from(read_u16(raw, 12, RejectCode::SectionFraming)?);
    if dependency_count > MAX_DEPENDENCIES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    let payload_length = usize::try_from(read_u32(raw, 14, RejectCode::SectionFraming)?)
        .map_err(|_| BootstrapError::new(RejectCode::ResourceLimit))?;
    let dependency_bytes = checked_mul(dependency_count, 4)?;
    let dependencies_end = checked_add(18, dependency_bytes)?;
    let mut dependencies = Vec::with_capacity(dependency_count);
    for index in 0..dependency_count {
        dependencies.push(read_u32(raw, 18 + index * 4, RejectCode::SectionFraming)?);
    }
    check_strict_ids(&dependencies, RejectCode::SectionFraming, Some(section_id))?;
    let payload_end = checked_add(dependencies_end, payload_length)?;
    let expected = checked_add(payload_end, check_width(check_id)?)?;
    if expected != raw.len() {
        return Err(BootstrapError::new(if expected < raw.len() {
            RejectCode::TrailingData
        } else {
            RejectCode::SectionFraming
        }));
    }
    let mut preimage = Vec::with_capacity(SECTION_CHECK_DOMAIN.len() + payload_end);
    preimage.extend_from_slice(&SECTION_CHECK_DOMAIN);
    preimage.extend_from_slice(&raw[..payload_end]);
    let check_matches = match check_id {
        CHECK_CRC32C => read_u32(raw, payload_end, RejectCode::SectionCheck)? == crc32c(&preimage),
        CHECK_CRC64_ECMA => {
            let bytes = raw
                .get(payload_end..payload_end + 8)
                .ok_or(BootstrapError::new(RejectCode::SectionFraming))?;
            u64::from_be_bytes(bytes.try_into().expect("eight-byte checked slice"))
                == crc64_ecma(&preimage)
        }
        _ => unreachable!(),
    };
    if !check_matches {
        return Err(BootstrapError::new(RejectCode::SectionCheck));
    }
    Ok(SectionEnvelope {
        section_id,
        section_type,
        section_version,
        closure_class,
        check_id,
        dependencies,
        payload: raw[dependencies_end..payload_end].to_vec(),
    })
}

pub fn validate_fragment_envelope_agreement(
    block: &CommonBlock,
    raw_envelope: &[u8],
) -> Result<SectionEnvelope> {
    let envelope = decode_section(raw_envelope)?;
    if block.section_id != envelope.section_id
        || block.section_type != envelope.section_type
        || block.section_version != envelope.section_version
        || usize::try_from(block.section_envelope_length).ok() != Some(raw_envelope.len())
    {
        return Err(BootstrapError::new(RejectCode::SectionFraming));
    }
    Ok(envelope)
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct InventoryEntry {
    pub section_id: u32,
    pub section_type: u16,
    pub section_version: u16,
    pub closure_class: u8,
    pub check_id: u8,
    pub copy_count: u8,
    /// Physical lane factor. Inventory v0 has no physical-lane field on wire
    /// and is represented canonically as one; v1 carries exactly 1, 2, or 5.
    pub physical_replica_count: u8,
    pub dependencies: Vec<u32>,
    pub logical_payload_length: u32,
    pub game_ordinal: Option<u16>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Inventory {
    pub inventory_version: u16,
    pub entries: Vec<InventoryEntry>,
}

fn validate_inventory(inventory: &Inventory, encoded_length: Option<usize>) -> Result<()> {
    if !matches!(inventory.inventory_version, 0 | 1) {
        return Err(BootstrapError::new(RejectCode::Inventory));
    }
    if !(3..=MAX_INVENTORY_ENTRIES).contains(&inventory.entries.len()) {
        return Err(BootstrapError::new(
            if inventory.entries.len() > MAX_INVENTORY_ENTRIES {
                RejectCode::ResourceLimit
            } else {
                RejectCode::Inventory
            },
        ));
    }
    let mut ids = BTreeSet::new();
    let mut ordinals = BTreeSet::new();
    let mut previous = 0u32;
    for entry in &inventory.entries {
        if entry.section_id == 0 || entry.section_id <= previous || !ids.insert(entry.section_id) {
            return Err(BootstrapError::new(RejectCode::Inventory));
        }
        previous = entry.section_id;
        let protection_valid = match inventory.inventory_version {
            0 => (1..=3).contains(&entry.copy_count) && entry.physical_replica_count == 1,
            1 => {
                entry.copy_count == 1
                    && matches!(entry.physical_replica_count, 1 | 2 | 5)
                    && entry.check_id == CHECK_CRC32C
            }
            _ => false,
        };
        if !known_section_type(entry.section_type)
            || !known_closure(entry.closure_class)
            || !known_check(entry.check_id)
            || !protection_valid
        {
            return Err(BootstrapError::new(RejectCode::Inventory));
        }
        check_strict_ids(
            &entry.dependencies,
            RejectCode::Inventory,
            Some(entry.section_id),
        )?;
        match entry.game_ordinal {
            Some(ordinal) => {
                if ordinal > 63
                    || entry.section_type != SECTION_CONTENT_BODY
                    || !ordinals.insert(ordinal)
                {
                    return Err(BootstrapError::new(RejectCode::Inventory));
                }
            }
            None => {}
        }
    }
    if ordinals.len() != 64 || ordinals.iter().copied().ne(0..64) {
        return Err(BootstrapError::new(RejectCode::Inventory));
    }
    let dependency_total = inventory.entries.iter().try_fold(0usize, |sum, entry| {
        checked_add(sum, entry.dependencies.len())
    })?;
    let derived_length = checked_add(
        8,
        checked_add(
            checked_mul(inventory.entries.len(), 20)?,
            checked_mul(dependency_total, 4)?,
        )?,
    )?;
    if derived_length > MAX_ENVELOPE_BYTES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    let entry_one = inventory.entries.first().expect("length checked");
    let first_shape_valid = entry_one.section_id == 1
        && entry_one.section_type == SECTION_INVENTORY
        && entry_one.closure_class == CLOSURE_M2_REQUIRED
        && entry_one.dependencies.is_empty()
        && entry_one.game_ordinal.is_none()
        && entry_one.logical_payload_length as usize == derived_length
        && encoded_length.is_none_or(|length| length == derived_length);
    if !first_shape_valid {
        return Err(BootstrapError::new(RejectCode::Inventory));
    }
    if inventory.inventory_version == 0
        && (entry_one.section_version != 0
            || entry_one.copy_count != 2
            || entry_one.physical_replica_count != 1)
    {
        return Err(BootstrapError::new(RejectCode::Inventory));
    }
    if inventory.inventory_version == 1
        && (entry_one.section_version != 1
            || entry_one.copy_count != 1
            || entry_one.physical_replica_count != 5)
    {
        return Err(BootstrapError::new(RejectCode::Inventory));
    }
    for (expected_id, entry) in [(2u32, &inventory.entries[1]), (3u32, &inventory.entries[2])] {
        if entry.section_id != expected_id
            || entry.section_type != SECTION_TIER_FRAME
            || entry.section_version != 0
            || entry.closure_class != CLOSURE_M2_REQUIRED
            || entry.game_ordinal.is_some()
            || (inventory.inventory_version == 0 && entry.copy_count < 2)
            || (inventory.inventory_version == 1
                && (entry.copy_count != 1 || entry.physical_replica_count != 5))
        {
            return Err(BootstrapError::new(RejectCode::Inventory));
        }
    }
    if inventory.inventory_version == 1 {
        const SPINE: [u32; 4] = [1, 2, 3, 16];
        for entry in &inventory.entries {
            let is_spine = SPINE.contains(&entry.section_id);
            if is_spine != (entry.closure_class == CLOSURE_M2_REQUIRED)
                || is_spine != (entry.physical_replica_count == 5)
            {
                return Err(BootstrapError::new(RejectCode::Inventory));
            }
        }
        let entry_sixteen = inventory
            .entries
            .binary_search_by_key(&16, |entry| entry.section_id)
            .ok()
            .map(|index| &inventory.entries[index]);
        if !entry_sixteen.is_some_and(|entry| {
            entry.section_type == SECTION_CONTENT_BODY
                && entry.section_version == 0
                && entry.copy_count == 1
                && entry.physical_replica_count == 5
        }) {
            return Err(BootstrapError::new(RejectCode::Inventory));
        }
    }
    for entry in &inventory.entries {
        if matches!(
            entry.section_type,
            SECTION_INVENTORY | SECTION_TIER_FRAME | SECTION_CONTENT_BODY
        ) && entry.logical_payload_length == 0
        {
            return Err(BootstrapError::new(RejectCode::Inventory));
        }
        if entry
            .dependencies
            .iter()
            .any(|dependency| !ids.contains(dependency))
        {
            return Err(BootstrapError::new(RejectCode::Inventory));
        }
    }
    validate_dependency_graph(inventory)?;
    Ok(())
}

fn validate_dependency_graph(inventory: &Inventory) -> Result<()> {
    let by_id: BTreeMap<u32, &InventoryEntry> = inventory
        .entries
        .iter()
        .map(|entry| (entry.section_id, entry))
        .collect();
    let mut colors = BTreeMap::<u32, u8>::new();
    for root in by_id.keys().copied() {
        if colors.get(&root) == Some(&2) {
            continue;
        }
        colors.insert(root, 1);
        let mut stack = vec![(root, 0usize)];
        while let Some((id, next_dependency)) = stack.last_mut() {
            let entry = by_id
                .get(id)
                .ok_or(BootstrapError::new(RejectCode::Inventory))?;
            if *next_dependency == entry.dependencies.len() {
                colors.insert(*id, 2);
                stack.pop();
                continue;
            }
            let dependency = entry.dependencies[*next_dependency];
            *next_dependency += 1;
            match colors.get(&dependency).copied().unwrap_or(0) {
                1 => return Err(BootstrapError::new(RejectCode::Dependency)),
                2 => {}
                _ => {
                    colors.insert(dependency, 1);
                    stack.push((dependency, 0));
                }
            }
        }
    }
    Ok(())
}

pub fn encode_inventory(inventory: &Inventory) -> Result<Vec<u8>> {
    validate_inventory(inventory, None)?;
    let dependencies: usize = inventory.entries.iter().try_fold(0usize, |sum, entry| {
        checked_add(sum, entry.dependencies.len())
    })?;
    let total = checked_add(
        8,
        checked_add(
            checked_mul(inventory.entries.len(), 20)?,
            checked_mul(dependencies, 4)?,
        )?,
    )?;
    if total > MAX_ENVELOPE_BYTES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    if inventory.entries[0].logical_payload_length as usize != total {
        return Err(BootstrapError::new(RejectCode::Inventory));
    }
    let mut raw = Vec::with_capacity(total);
    raw.extend_from_slice(&inventory.inventory_version.to_be_bytes());
    raw.extend_from_slice(&(inventory.entries.len() as u16).to_be_bytes());
    raw.extend_from_slice(&0u16.to_be_bytes());
    raw.extend_from_slice(&64u16.to_be_bytes());
    for entry in &inventory.entries {
        raw.extend_from_slice(&entry.section_id.to_be_bytes());
        raw.extend_from_slice(&entry.section_type.to_be_bytes());
        raw.extend_from_slice(&entry.section_version.to_be_bytes());
        raw.push(entry.closure_class);
        raw.push(entry.check_id);
        raw.push(entry.copy_count);
        let has_game_ordinal = u8::from(entry.game_ordinal.is_some());
        raw.push(if inventory.inventory_version == 0 {
            has_game_ordinal
        } else {
            (entry.physical_replica_count << 1) | has_game_ordinal
        });
        raw.extend_from_slice(&(entry.dependencies.len() as u16).to_be_bytes());
        raw.extend_from_slice(&entry.logical_payload_length.to_be_bytes());
        raw.extend_from_slice(&entry.game_ordinal.unwrap_or(0xffff).to_be_bytes());
        for dependency in &entry.dependencies {
            raw.extend_from_slice(&dependency.to_be_bytes());
        }
    }
    Ok(raw)
}

pub fn decode_inventory(raw: &[u8]) -> Result<Inventory> {
    if raw.len() < 8 {
        return Err(BootstrapError::new(RejectCode::Inventory));
    }
    if raw.len() > MAX_ENVELOPE_BYTES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    let inventory_version = read_u16(raw, 0, RejectCode::Inventory)?;
    if !matches!(inventory_version, 0 | 1)
        || read_u16(raw, 4, RejectCode::Inventory)? != 0
        || read_u16(raw, 6, RejectCode::Inventory)? != 64
    {
        return Err(BootstrapError::new(RejectCode::Inventory));
    }
    let count = usize::from(read_u16(raw, 2, RejectCode::Inventory)?);
    if count > MAX_INVENTORY_ENTRIES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    if count < 3 {
        return Err(BootstrapError::new(RejectCode::Inventory));
    }
    let minimum = checked_add(8, checked_mul(count, 20)?)?;
    if minimum > raw.len() {
        return Err(BootstrapError::new(RejectCode::Inventory));
    }
    let mut offset = 8usize;
    let mut entries = Vec::with_capacity(count);
    for _ in 0..count {
        let fixed_end = checked_add(offset, 20)?;
        if fixed_end > raw.len() {
            return Err(BootstrapError::new(RejectCode::Inventory));
        }
        let section_id = read_u32(raw, offset, RejectCode::Inventory)?;
        let section_type = read_u16(raw, offset + 4, RejectCode::Inventory)?;
        let section_version = read_u16(raw, offset + 6, RejectCode::Inventory)?;
        let closure_class = raw[offset + 8];
        let check_id = raw[offset + 9];
        let copy_count = raw[offset + 10];
        let flags = raw[offset + 11];
        let physical_replica_count = if inventory_version == 0 {
            if flags & !1 != 0 {
                return Err(BootstrapError::new(RejectCode::Inventory));
            }
            1
        } else {
            if flags & 0xf0 != 0 || !matches!(flags >> 1, 1 | 2 | 5) {
                return Err(BootstrapError::new(RejectCode::Inventory));
            }
            flags >> 1
        };
        let dependency_count = usize::from(read_u16(raw, offset + 12, RejectCode::Inventory)?);
        if dependency_count > MAX_DEPENDENCIES {
            return Err(BootstrapError::new(RejectCode::ResourceLimit));
        }
        let logical_payload_length = read_u32(raw, offset + 14, RejectCode::Inventory)?;
        let encoded_ordinal = read_u16(raw, offset + 18, RejectCode::Inventory)?;
        offset = fixed_end;
        let dependency_end = checked_add(offset, checked_mul(dependency_count, 4)?)?;
        if dependency_end > raw.len() {
            return Err(BootstrapError::new(RejectCode::Inventory));
        }
        let mut dependencies = Vec::with_capacity(dependency_count);
        for index in 0..dependency_count {
            dependencies.push(read_u32(raw, offset + index * 4, RejectCode::Inventory)?);
        }
        offset = dependency_end;
        let game_ordinal = if flags & 1 == 1 {
            if encoded_ordinal > 63 {
                return Err(BootstrapError::new(RejectCode::Inventory));
            }
            Some(encoded_ordinal)
        } else {
            if encoded_ordinal != 0xffff {
                return Err(BootstrapError::new(RejectCode::Inventory));
            }
            None
        };
        entries.push(InventoryEntry {
            section_id,
            section_type,
            section_version,
            closure_class,
            check_id,
            copy_count,
            physical_replica_count,
            dependencies,
            logical_payload_length,
            game_ordinal,
        });
    }
    if offset != raw.len() {
        return Err(BootstrapError::new(RejectCode::TrailingData));
    }
    let inventory = Inventory {
        inventory_version,
        entries,
    };
    validate_inventory(&inventory, Some(raw.len()))?;
    Ok(inventory)
}

pub fn dependency_closure(
    inventory: &Inventory,
    roots: &[u32],
    available: &BTreeSet<u32>,
) -> Result<Vec<u32>> {
    validate_inventory(inventory, None)?;
    check_strict_ids(roots, RejectCode::Dependency, None)?;
    let by_id: BTreeMap<u32, &InventoryEntry> = inventory
        .entries
        .iter()
        .map(|entry| (entry.section_id, entry))
        .collect();
    let mut closure = BTreeSet::new();
    let mut stack: Vec<u32> = roots.iter().rev().copied().collect();
    while let Some(id) = stack.pop() {
        let entry = by_id
            .get(&id)
            .ok_or(BootstrapError::new(RejectCode::Dependency))?;
        if !available.contains(&id) {
            return Err(BootstrapError::new(RejectCode::Dependency));
        }
        if closure.insert(id) {
            for dependency in entry.dependencies.iter().rev() {
                stack.push(*dependency);
            }
        }
    }
    Ok(closure.into_iter().collect())
}

pub fn validate_envelope_against_inventory(
    envelope: &SectionEnvelope,
    inventory: &Inventory,
) -> Result<()> {
    validate_inventory(inventory, None)?;
    let entry = inventory
        .entries
        .binary_search_by_key(&envelope.section_id, |entry| entry.section_id)
        .ok()
        .map(|index| &inventory.entries[index])
        .ok_or(BootstrapError::new(RejectCode::Inventory))?;
    if envelope.section_type != entry.section_type
        || envelope.section_version != entry.section_version
        || envelope.closure_class != entry.closure_class
        || envelope.check_id != entry.check_id
        || envelope.dependencies != entry.dependencies
        || envelope.payload.len() != entry.logical_payload_length as usize
    {
        return Err(BootstrapError::new(RejectCode::Inventory));
    }
    Ok(())
}

pub fn validate_common_against_inventory(block: &CommonBlock, inventory: &Inventory) -> Result<()> {
    validate_common_fields(block)?;
    validate_inventory(inventory, None)?;
    let entry = inventory
        .entries
        .binary_search_by_key(&block.section_id, |entry| entry.section_id)
        .ok()
        .map(|index| &inventory.entries[index])
        .ok_or(BootstrapError::new(RejectCode::Inventory))?;
    if block.section_type != entry.section_type
        || block.section_version != entry.section_version
        || block.semantic_copy_id >= u16::from(entry.copy_count)
    {
        return Err(BootstrapError::new(RejectCode::Inventory));
    }
    Ok(())
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TierFrame {
    pub tier_id: u8,
    pub body_section_ids: Vec<u32>,
    pub assembled_stream_byte_length: u32,
    pub assembled_record_count: u16,
    pub root_record_bytes: Vec<u8>,
}

fn validate_tier_fields(tier: &TierFrame) -> Result<()> {
    if tier.assembled_stream_byte_length as usize > MAX_ENVELOPE_BYTES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    if tier.tier_id > 1
        || tier.body_section_ids.is_empty()
        || tier.body_section_ids.len() > MAX_TIER_BODY_IDS
        || tier.assembled_stream_byte_length == 0
        || tier.assembled_record_count < 2
        || tier.root_record_bytes.is_empty()
    {
        return Err(BootstrapError::new(RejectCode::TierFrame));
    }
    check_strict_ids(&tier.body_section_ids, RejectCode::TierFrame, None)?;
    validate_root_frame(&tier.root_record_bytes).map(|_| ())
}

fn validate_root_frame(raw: &[u8]) -> Result<u16> {
    if raw.len() != 12 {
        return Err(BootstrapError::new(RejectCode::TierFrame));
    }
    let record_id = read_u16(raw, 0, RejectCode::TierFrame)?;
    let record_kind = read_u16(raw, 2, RejectCode::TierFrame)?;
    let payload_length = read_u32(raw, 4, RejectCode::TierFrame)?;
    let entry_node = read_u16(raw, 8, RejectCode::TierFrame)?;
    let global_budget = read_u16(raw, 10, RejectCode::TierFrame)?;
    if record_id == 0
        || record_kind != 14
        || payload_length != 4
        || entry_node == 0
        || global_budget == 0
    {
        return Err(BootstrapError::new(RejectCode::TierFrame));
    }
    Ok(record_id)
}

fn validate_body_frames(raw: &[u8], previous_record_id: &mut u16) -> Result<usize> {
    if raw.is_empty() {
        return Err(BootstrapError::new(RejectCode::TierFrame));
    }
    let mut offset = 0usize;
    let mut count = 0usize;
    while offset < raw.len() {
        let header_end = checked_add(offset, 8)?;
        if header_end > raw.len() {
            return Err(BootstrapError::new(RejectCode::TierFrame));
        }
        let record_id = read_u16(raw, offset, RejectCode::TierFrame)?;
        let record_kind = read_u16(raw, offset + 2, RejectCode::TierFrame)?;
        let payload_length = usize::try_from(read_u32(raw, offset + 4, RejectCode::TierFrame)?)
            .map_err(|_| BootstrapError::new(RejectCode::ResourceLimit))?;
        let end = checked_add(header_end, payload_length)?;
        if end > raw.len()
            || record_id == 0
            || record_id <= *previous_record_id
            || !(1..14).contains(&record_kind)
        {
            return Err(BootstrapError::new(RejectCode::TierFrame));
        }
        *previous_record_id = record_id;
        count = checked_add(count, 1)?;
        offset = end;
    }
    Ok(count)
}

pub fn encode_tier_frame(tier: &TierFrame) -> Result<Vec<u8>> {
    validate_tier_fields(tier)?;
    let total = checked_add(
        checked_add(22, checked_mul(tier.body_section_ids.len(), 4)?)?,
        tier.root_record_bytes.len(),
    )?;
    if total > MAX_ENVELOPE_BYTES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    let root_length = u32::try_from(tier.root_record_bytes.len())
        .map_err(|_| BootstrapError::new(RejectCode::ResourceLimit))?;
    let mut raw = Vec::with_capacity(total);
    raw.extend_from_slice(&0u16.to_be_bytes());
    raw.push(tier.tier_id);
    raw.push(0);
    raw.extend_from_slice(&(tier.body_section_ids.len() as u16).to_be_bytes());
    raw.extend_from_slice(&0u16.to_be_bytes());
    raw.extend_from_slice(&tier.assembled_stream_byte_length.to_be_bytes());
    raw.extend_from_slice(&tier.assembled_record_count.to_be_bytes());
    raw.extend_from_slice(&root_length.to_be_bytes());
    raw.extend_from_slice(&0u16.to_be_bytes());
    raw.extend_from_slice(&tier.assembled_record_count.to_be_bytes());
    for section_id in &tier.body_section_ids {
        raw.extend_from_slice(&section_id.to_be_bytes());
    }
    raw.extend_from_slice(&tier.root_record_bytes);
    Ok(raw)
}

pub fn decode_tier_frame(raw: &[u8], expected_section_id: u32) -> Result<TierFrame> {
    if raw.len() < 27 {
        return Err(BootstrapError::new(RejectCode::TierFrame));
    }
    if raw.len() > MAX_ENVELOPE_BYTES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    let tier_id = raw[2];
    if read_u16(raw, 0, RejectCode::TierFrame)? != 0
        || raw[3] != 0
        || read_u16(raw, 6, RejectCode::TierFrame)? != 0
        || !matches!((expected_section_id, tier_id), (2, 0) | (3, 1))
    {
        return Err(BootstrapError::new(RejectCode::TierFrame));
    }
    let count = usize::from(read_u16(raw, 4, RejectCode::TierFrame)?);
    if count == 0 || count > MAX_TIER_BODY_IDS {
        return Err(BootstrapError::new(if count > MAX_TIER_BODY_IDS {
            RejectCode::ResourceLimit
        } else {
            RejectCode::TierFrame
        }));
    }
    let assembled_stream_byte_length = read_u32(raw, 8, RejectCode::TierFrame)?;
    if assembled_stream_byte_length as usize > MAX_ENVELOPE_BYTES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    let assembled_record_count = read_u16(raw, 12, RejectCode::TierFrame)?;
    let root_length = usize::try_from(read_u32(raw, 14, RejectCode::TierFrame)?)
        .map_err(|_| BootstrapError::new(RejectCode::ResourceLimit))?;
    if read_u16(raw, 18, RejectCode::TierFrame)? != 0
        || read_u16(raw, 20, RejectCode::TierFrame)? != assembled_record_count
        || assembled_stream_byte_length == 0
        || assembled_record_count == 0
        || root_length == 0
    {
        return Err(BootstrapError::new(RejectCode::TierFrame));
    }
    let ids_end = checked_add(22, checked_mul(count, 4)?)?;
    let expected = checked_add(ids_end, root_length)?;
    if expected != raw.len() {
        return Err(BootstrapError::new(if expected < raw.len() {
            RejectCode::TrailingData
        } else {
            RejectCode::TierFrame
        }));
    }
    let mut body_section_ids = Vec::with_capacity(count);
    for index in 0..count {
        body_section_ids.push(read_u32(raw, 22 + index * 4, RejectCode::TierFrame)?);
    }
    let tier = TierFrame {
        tier_id,
        body_section_ids,
        assembled_stream_byte_length,
        assembled_record_count,
        root_record_bytes: raw[ids_end..].to_vec(),
    };
    validate_tier_fields(&tier)?;
    Ok(tier)
}

pub fn validate_tier_against_inventory(
    tier: &TierFrame,
    envelope: &SectionEnvelope,
    inventory: &Inventory,
) -> Result<()> {
    if decode_tier_frame(&envelope.payload, envelope.section_id)? != *tier {
        return Err(BootstrapError::new(RejectCode::TierFrame));
    }
    let expected_section_id = u32::from(tier.tier_id) + 2;
    if envelope.section_id != expected_section_id
        || envelope.section_type != SECTION_TIER_FRAME
        || envelope.section_version != 0
        || envelope.closure_class != CLOSURE_M2_REQUIRED
        || envelope.dependencies != tier.body_section_ids
    {
        return Err(BootstrapError::new(RejectCode::TierFrame));
    }
    validate_envelope_against_inventory(envelope, inventory)?;
    let expected: Vec<u32> = inventory
        .entries
        .iter()
        .filter(|entry| {
            entry.section_type == SECTION_CONTENT_BODY
                && (tier.tier_id == 1 || entry.closure_class == CLOSURE_M2_REQUIRED)
        })
        .map(|entry| entry.section_id)
        .collect();
    if tier.body_section_ids != expected {
        return Err(BootstrapError::new(RejectCode::TierFrame));
    }
    Ok(())
}

pub fn assemble_tier_bytes(
    tier: &TierFrame,
    body_payloads: &BTreeMap<u32, Vec<u8>>,
) -> Result<Vec<u8>> {
    validate_tier_fields(tier)?;
    if body_payloads
        .keys()
        .copied()
        .ne(tier.body_section_ids.iter().copied())
    {
        return Err(BootstrapError::new(RejectCode::Dependency));
    }
    let mut derived_length = 4usize;
    let mut derived_record_count = 0usize;
    let mut previous_record_id = 0u16;
    for section_id in &tier.body_section_ids {
        let body = &body_payloads[section_id];
        derived_length = checked_add(derived_length, body.len())?;
        derived_record_count = checked_add(
            derived_record_count,
            validate_body_frames(body, &mut previous_record_id)?,
        )?;
    }
    let root_record_id = validate_root_frame(&tier.root_record_bytes)?;
    if root_record_id <= previous_record_id {
        return Err(BootstrapError::new(RejectCode::TierFrame));
    }
    derived_record_count = checked_add(derived_record_count, 1)?;
    derived_length = checked_add(derived_length, tier.root_record_bytes.len())?;
    let assembled_length = usize::try_from(tier.assembled_stream_byte_length)
        .map_err(|_| BootstrapError::new(RejectCode::ResourceLimit))?;
    if assembled_length > MAX_ENVELOPE_BYTES || derived_length > MAX_ENVELOPE_BYTES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    if derived_length != assembled_length
        || derived_record_count != usize::from(tier.assembled_record_count)
    {
        return Err(BootstrapError::new(RejectCode::TierFrame));
    }
    let mut raw = Vec::with_capacity(assembled_length);
    raw.extend_from_slice(&0u16.to_be_bytes());
    raw.extend_from_slice(&tier.assembled_record_count.to_be_bytes());
    for section_id in &tier.body_section_ids {
        raw.extend_from_slice(&body_payloads[section_id]);
    }
    raw.extend_from_slice(&tier.root_record_bytes);
    debug_assert_eq!(raw.len(), assembled_length);
    Ok(raw)
}

pub fn assemble_content_stream(
    tier: &TierFrame,
    body_payloads: &BTreeMap<u32, Vec<u8>>,
) -> Result<Vec<u8>> {
    let raw = assemble_tier_bytes(tier, body_payloads)?;
    gb_content::stream_validation(&raw)
        .map_err(|_| BootstrapError::new(RejectCode::ContentStream))?;
    Ok(raw)
}
