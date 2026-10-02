//! Frozen pre-result M2 transport candidates.
//!
//! This module is intentionally small and closed: exactly six profile tuples,
//! the specified extended-Hamming transport, and the specified RS field,
//! generator, systematic encoder, and syndrome verifier.  No candidate is
//! selected here.

use std::collections::BTreeMap;

use crate::{CHECK_CRC32C, CHECK_CRC64_ECMA, COMMON_BLOCK_BYTES, decode_common_block};

pub const EH_DATA_BYTES: usize = 8;
pub const EH_CODEWORD_BYTES: usize = 9;
pub const EH_CODEWORD_BITS: usize = 72;
pub const EH_CODEWORDS_PER_UNIT: usize = 24;
pub const EH_UNIT_BYTES: usize = 216;
pub const RS_DATA_BYTES: usize = 191;
pub const RS_PARITY_BYTES: usize = 64;
pub const RS_CODEWORD_BYTES: usize = 255;

pub const RS_GENERATOR: [u8; 65] = [
    0x01, 0xc1, 0x0a, 0xff, 0x3a, 0x80, 0xb7, 0x73, 0x8c, 0x99, 0x93, 0x5b, 0xc5, 0xdb, 0xdd, 0xdc,
    0x8e, 0x1c, 0x78, 0x15, 0xa4, 0x93, 0x06, 0xcc, 0x28, 0xe6, 0xb6, 0x0e, 0x79, 0x30, 0x8f, 0x4d,
    0xe4, 0x51, 0x55, 0x2b, 0xa2, 0x10, 0xc3, 0xa3, 0x23, 0x95, 0x9a, 0x23, 0x84, 0x64, 0x64, 0x33,
    0xb0, 0x0b, 0xa1, 0x86, 0xd0, 0x84, 0xf4, 0xb0, 0xc0, 0xdd, 0xe8, 0xab, 0x7d, 0x9b, 0xe4, 0xf2,
    0xf5,
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TransportFamily {
    Eh72Replicated,
    Eh72HierarchicalRepetition,
    Rs255_191,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct CandidateProfile {
    pub id: &'static str,
    pub version: u16,
    pub transport: TransportFamily,
    pub section_check_id: u8,
    pub required_copy_count: u8,
}

pub const PROFILES: [CandidateProfile; 7] = [
    CandidateProfile {
        id: "eh72-r2-crc32c-v0",
        version: 1,
        transport: TransportFamily::Eh72Replicated,
        section_check_id: CHECK_CRC32C,
        required_copy_count: 2,
    },
    CandidateProfile {
        id: "eh72-r2-crc64-ecma-v0",
        version: 2,
        transport: TransportFamily::Eh72Replicated,
        section_check_id: CHECK_CRC64_ECMA,
        required_copy_count: 2,
    },
    CandidateProfile {
        id: "eh72-r3-crc32c-v0",
        version: 3,
        transport: TransportFamily::Eh72Replicated,
        section_check_id: CHECK_CRC32C,
        required_copy_count: 3,
    },
    CandidateProfile {
        id: "eh72-r3-crc64-ecma-v0",
        version: 4,
        transport: TransportFamily::Eh72Replicated,
        section_check_id: CHECK_CRC64_ECMA,
        required_copy_count: 3,
    },
    CandidateProfile {
        id: "rs255-191-crc32c-v0",
        version: 5,
        transport: TransportFamily::Rs255_191,
        section_check_id: CHECK_CRC32C,
        required_copy_count: 2,
    },
    CandidateProfile {
        id: "rs255-191-crc64-ecma-v0",
        version: 6,
        transport: TransportFamily::Rs255_191,
        section_check_id: CHECK_CRC64_ECMA,
        required_copy_count: 2,
    },
    CandidateProfile {
        id: "eh72-hier-r5-r2-r1-crc32c-v0",
        version: 7,
        transport: TransportFamily::Eh72HierarchicalRepetition,
        section_check_id: CHECK_CRC32C,
        required_copy_count: 1,
    },
];

pub fn profile_by_version(version: u16) -> Option<CandidateProfile> {
    PROFILES
        .iter()
        .copied()
        .find(|profile| profile.version == version)
}

pub fn profile_by_id(id: &str) -> Option<CandidateProfile> {
    PROFILES.iter().copied().find(|profile| profile.id == id)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CodecError {
    Parameter,
    Erasure,
    Corrupt,
    Ambiguous,
    InternalInvariant,
    LocalCheck,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DecodeQuality {
    Verified,
    Recovered,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct EhCodeword {
    pub data: [u8; EH_DATA_BYTES],
    pub quality: DecodeQuality,
    pub constructions: u16,
}

fn eh_bit(codeword: &[u8; EH_CODEWORD_BYTES], position: usize) -> u8 {
    let index = position - 1;
    (codeword[index / 8] >> (7 - index % 8)) & 1
}

fn eh_set_bit(codeword: &mut [u8; EH_CODEWORD_BYTES], position: usize, value: u8) {
    let index = position - 1;
    let mask = 1 << (7 - index % 8);
    codeword[index / 8] = (codeword[index / 8] & !mask) | (value * mask);
}

fn eh_is_hamming_parity(position: usize) -> bool {
    matches!(position, 1 | 2 | 4 | 8 | 16 | 32 | 64)
}

fn eh_parity_valid(codeword: &[u8; EH_CODEWORD_BYTES]) -> bool {
    for parity in [1, 2, 4, 8, 16, 32, 64] {
        let mut value = 0;
        for position in 1..=71 {
            if position & parity != 0 {
                value ^= eh_bit(codeword, position);
            }
        }
        if value != 0 {
            return false;
        }
    }
    (1..=72).fold(0, |parity, position| parity ^ eh_bit(codeword, position)) == 0
}

pub fn encode_eh72(data: &[u8; EH_DATA_BYTES]) -> [u8; EH_CODEWORD_BYTES] {
    let mut encoded = [0_u8; EH_CODEWORD_BYTES];
    let mut data_bit = 0;
    for position in 1..=71 {
        if eh_is_hamming_parity(position) {
            continue;
        }
        let value = (data[data_bit / 8] >> (7 - data_bit % 8)) & 1;
        eh_set_bit(&mut encoded, position, value);
        data_bit += 1;
    }
    debug_assert_eq!(data_bit, 64);
    for parity in [1, 2, 4, 8, 16, 32, 64] {
        let value = (1..=71)
            .filter(|position| position & parity != 0)
            .fold(0, |value, position| value ^ eh_bit(&encoded, position));
        eh_set_bit(&mut encoded, parity, value);
    }
    let overall = (1..=71).fold(0, |value, position| value ^ eh_bit(&encoded, position));
    eh_set_bit(&mut encoded, 72, overall);
    encoded
}

fn eh_data(codeword: &[u8; EH_CODEWORD_BYTES]) -> [u8; EH_DATA_BYTES] {
    let mut data = [0_u8; EH_DATA_BYTES];
    let mut data_bit = 0;
    for position in 1..=71 {
        if eh_is_hamming_parity(position) {
            continue;
        }
        data[data_bit / 8] |= eh_bit(codeword, position) << (7 - data_bit % 8);
        data_bit += 1;
    }
    data
}

pub fn decode_eh72(
    observed: &[u8; EH_CODEWORD_BYTES],
    erased_positions: &[u8],
) -> Result<EhCodeword, CodecError> {
    if erased_positions.len() > 3 {
        return Err(CodecError::Erasure);
    }
    let mut erased = [false; EH_CODEWORD_BITS + 1];
    for position in erased_positions.iter().copied() {
        let index = usize::from(position);
        if !(1..=EH_CODEWORD_BITS).contains(&index) || erased[index] {
            return Err(CodecError::Erasure);
        }
        erased[index] = true;
    }
    let erased_order = (1..=EH_CODEWORD_BITS)
        .filter(|position| erased[*position])
        .collect::<Vec<_>>();
    let max_known_changes = (3 - erased_order.len()) / 2;
    let mut candidates = BTreeMap::<[u8; EH_CODEWORD_BYTES], bool>::new();
    let mut constructions = 0_u16;
    for fill in 0..(1_usize << erased_order.len()) {
        let mut base = *observed;
        for (ordinal, position) in erased_order.iter().copied().enumerate() {
            eh_set_bit(&mut base, position, ((fill >> ordinal) & 1) as u8);
        }
        constructions += 1;
        if eh_parity_valid(&base) {
            candidates
                .entry(base)
                .and_modify(|corrected| *corrected |= !erased_order.is_empty())
                .or_insert(!erased_order.is_empty());
        }
        if max_known_changes == 1 {
            for position in 1..=EH_CODEWORD_BITS {
                if erased[position] {
                    continue;
                }
                constructions += 1;
                let mut changed = base;
                let inverted = eh_bit(&changed, position) ^ 1;
                eh_set_bit(&mut changed, position, inverted);
                if eh_parity_valid(&changed) {
                    candidates
                        .entry(changed)
                        .and_modify(|corrected| *corrected = true)
                        .or_insert(true);
                }
            }
        }
    }
    if candidates.len() > 1 {
        return Err(CodecError::InternalInvariant);
    }
    let Some((codeword, corrected)) = candidates.into_iter().next() else {
        return Err(CodecError::Corrupt);
    };
    Ok(EhCodeword {
        data: eh_data(&codeword),
        quality: if corrected {
            DecodeQuality::Recovered
        } else {
            DecodeQuality::Verified
        },
        constructions,
    })
}

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct EhErasure {
    pub codeword: u8,
    /// One-based encoded bit position in `1..=72`.
    pub position: u8,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EhObservation {
    pub encoded: [u8; EH_UNIT_BYTES],
    pub erasures: Vec<EhErasure>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct DecodedUnit {
    pub common: [u8; COMMON_BLOCK_BYTES],
    pub quality: DecodeQuality,
}

pub fn encode_eh_unit(common: &[u8; COMMON_BLOCK_BYTES]) -> [u8; EH_UNIT_BYTES] {
    let mut plain = [0_u8; COMMON_BLOCK_BYTES + 1];
    plain[..COMMON_BLOCK_BYTES].copy_from_slice(common);
    let mut encoded = [0_u8; EH_UNIT_BYTES];
    for index in 0..EH_CODEWORDS_PER_UNIT {
        let data: [u8; EH_DATA_BYTES] = plain[index * EH_DATA_BYTES..(index + 1) * EH_DATA_BYTES]
            .try_into()
            .expect("exact eight-byte chunk");
        encoded[index * EH_CODEWORD_BYTES..(index + 1) * EH_CODEWORD_BYTES]
            .copy_from_slice(&encode_eh72(&data));
    }
    encoded
}

pub fn decode_eh_unit(
    observation: &EhObservation,
    expected_profile_version: u16,
) -> Result<DecodedUnit, CodecError> {
    let mut per_codeword = vec![Vec::<u8>::new(); EH_CODEWORDS_PER_UNIT];
    let mut previous = None;
    for erasure in observation.erasures.iter().copied() {
        if usize::from(erasure.codeword) >= EH_CODEWORDS_PER_UNIT
            || !(1..=72).contains(&erasure.position)
            || previous.is_some_and(|old| old >= erasure)
        {
            return Err(CodecError::Erasure);
        }
        previous = Some(erasure);
        per_codeword[usize::from(erasure.codeword)].push(erasure.position);
    }
    let mut plain = [0_u8; COMMON_BLOCK_BYTES + 1];
    let mut quality = DecodeQuality::Verified;
    for (index, erasures) in per_codeword.iter().enumerate() {
        let encoded: [u8; EH_CODEWORD_BYTES] = observation.encoded
            [index * EH_CODEWORD_BYTES..(index + 1) * EH_CODEWORD_BYTES]
            .try_into()
            .expect("exact nine-byte chunk");
        let decoded = decode_eh72(&encoded, erasures)?;
        if decoded.quality == DecodeQuality::Recovered {
            quality = DecodeQuality::Recovered;
        }
        plain[index * EH_DATA_BYTES..(index + 1) * EH_DATA_BYTES].copy_from_slice(&decoded.data);
    }
    if plain[COMMON_BLOCK_BYTES] != 0 {
        return Err(CodecError::Corrupt);
    }
    let common: [u8; COMMON_BLOCK_BYTES] = plain[..COMMON_BLOCK_BYTES]
        .try_into()
        .expect("exact common-block prefix");
    decode_common_block(&common, expected_profile_version).map_err(|_| CodecError::LocalCheck)?;
    Ok(DecodedUnit { common, quality })
}

/// Algebraically equivalent fast path for the overwhelmingly common
/// no-erasure, already-valid observation.  Invalid parity falls back to the
/// exhaustive bounded decoder so correction and rejection boundaries remain
/// exactly those of `decode_eh_unit`.
pub fn decode_eh_unit_fast(
    observation: &EhObservation,
    expected_profile_version: u16,
) -> Result<DecodedUnit, CodecError> {
    if !observation.erasures.is_empty() {
        return decode_eh_unit(observation, expected_profile_version);
    }
    let mut plain = [0_u8; COMMON_BLOCK_BYTES + 1];
    for index in 0..EH_CODEWORDS_PER_UNIT {
        let encoded: [u8; EH_CODEWORD_BYTES] = observation.encoded
            [index * EH_CODEWORD_BYTES..(index + 1) * EH_CODEWORD_BYTES]
            .try_into()
            .expect("exact nine-byte chunk");
        if !eh_parity_valid(&encoded) {
            return decode_eh_unit(observation, expected_profile_version);
        }
        plain[index * EH_DATA_BYTES..(index + 1) * EH_DATA_BYTES]
            .copy_from_slice(&eh_data(&encoded));
    }
    if plain[COMMON_BLOCK_BYTES] != 0 {
        return Err(CodecError::Corrupt);
    }
    let common: [u8; COMMON_BLOCK_BYTES] = plain[..COMMON_BLOCK_BYTES]
        .try_into()
        .expect("exact common-block prefix");
    decode_common_block(&common, expected_profile_version).map_err(|_| CodecError::LocalCheck)?;
    Ok(DecodedUnit {
        common,
        quality: DecodeQuality::Verified,
    })
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FragmentState {
    Verified,
    Recovered,
    Missing,
    Corrupt,
    Ambiguous,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct UnitRecovery {
    pub state: FragmentState,
    pub common: Option<[u8; COMMON_BLOCK_BYTES]>,
}

pub fn recover_eh_copies(
    profile: CandidateProfile,
    observations: &[Option<EhObservation>],
) -> Result<UnitRecovery, CodecError> {
    if !PROFILES.contains(&profile)
        || profile.transport != TransportFamily::Eh72Replicated
        || observations.len() != usize::from(profile.required_copy_count)
    {
        return Err(CodecError::Parameter);
    }
    let present = observations.iter().filter(|value| value.is_some()).count();
    let mut valid = BTreeMap::<[u8; COMMON_BLOCK_BYTES], bool>::new();
    for observation in observations.iter().flatten() {
        if let Ok(decoded) = decode_eh_unit(observation, profile.version) {
            valid
                .entry(decoded.common)
                .and_modify(|verified| {
                    *verified |= decoded.quality == DecodeQuality::Verified;
                })
                .or_insert(decoded.quality == DecodeQuality::Verified);
        }
    }
    Ok(match valid.len() {
        0 if present == 0 => UnitRecovery {
            state: FragmentState::Missing,
            common: None,
        },
        0 => UnitRecovery {
            state: FragmentState::Corrupt,
            common: None,
        },
        1 => {
            let (common, verified) = valid.into_iter().next().expect("one entry");
            UnitRecovery {
                state: if verified {
                    FragmentState::Verified
                } else {
                    FragmentState::Recovered
                },
                common: Some(common),
            }
        }
        _ => UnitRecovery {
            state: FragmentState::Ambiguous,
            common: None,
        },
    })
}

fn erasure_mask(
    observation: &EhObservation,
) -> Result<[bool; EH_CODEWORDS_PER_UNIT * 72], CodecError> {
    let mut mask = [false; EH_CODEWORDS_PER_UNIT * 72];
    let mut previous = None;
    for erasure in observation.erasures.iter().copied() {
        if usize::from(erasure.codeword) >= EH_CODEWORDS_PER_UNIT
            || !(1..=72).contains(&erasure.position)
            || previous.is_some_and(|old| old >= erasure)
        {
            return Err(CodecError::Erasure);
        }
        previous = Some(erasure);
        let bit = usize::from(erasure.codeword) * 72 + usize::from(erasure.position) - 1;
        mask[bit] = true;
    }
    Ok(mask)
}

fn encoded_bit(encoded: &[u8; EH_UNIT_BYTES], bit: usize) -> u8 {
    (encoded[bit / 8] >> (7 - bit % 8)) & 1
}

fn set_encoded_bit(encoded: &mut [u8; EH_UNIT_BYTES], bit: usize, value: u8) {
    let shift = 7 - bit % 8;
    let mask = 1 << shift;
    encoded[bit / 8] = (encoded[bit / 8] & !mask) | (value << shift);
}

/// Construct the exact v7 raw-repetition observation for one physical group.
///
/// A missing lane contributes one erasure to every encoded bit. A present lane
/// contributes either its known encoded bit or its declared erasure. Candidate
/// bit `b` is admitted exactly when `2e+s<R`; a symbol with no sole admissible
/// value is passed to EH72 as an erasure. The work and output are bounded by
/// five lanes and 1,728 encoded bits.
pub fn aggregate_repetition_observation(
    observations: &[Option<EhObservation>],
) -> Result<Option<EhObservation>, CodecError> {
    if !matches!(observations.len(), 2 | 5) {
        return Err(CodecError::Parameter);
    }
    if observations.iter().all(Option::is_none) {
        return Ok(None);
    }
    let masks = observations
        .iter()
        .map(|row| row.as_ref().map(erasure_mask).transpose())
        .collect::<Result<Vec<_>, _>>()?;
    let replica_count = observations.len();
    let mut encoded = [0_u8; EH_UNIT_BYTES];
    let mut erasures = Vec::new();
    for bit in 0..EH_UNIT_BYTES * 8 {
        let mut zeros = 0usize;
        let mut ones = 0usize;
        let mut erased = 0usize;
        for (observation, mask) in observations.iter().zip(&masks) {
            match (observation, mask) {
                (Some(row), Some(mask)) if !mask[bit] => {
                    if encoded_bit(&row.encoded, bit) == 0 {
                        zeros += 1;
                    } else {
                        ones += 1;
                    }
                }
                _ => erased += 1,
            }
        }
        let zero_admissible = 2 * ones + erased < replica_count;
        let one_admissible = 2 * zeros + erased < replica_count;
        match (zero_admissible, one_admissible) {
            (true, false) => set_encoded_bit(&mut encoded, bit, 0),
            (false, true) => set_encoded_bit(&mut encoded, bit, 1),
            _ => erasures.push(EhErasure {
                codeword: u8::try_from(bit / 72).expect("24 codewords"),
                position: u8::try_from(bit % 72 + 1).expect("one-based EH position"),
            }),
        }
    }
    Ok(Some(EhObservation { encoded, erasures }))
}

/// Recover one v7 factor-1/2/5 physical group without semantic voting.
///
/// Each lane is decoded independently. For REP2/REP5, the separately derived
/// repetition observation is also decoded. Locally valid common blocks are
/// byte-deduplicated; more than one distinct value is always ambiguous even
/// when one value has a physical majority.
pub fn recover_hierarchical_eh_group(
    profile: CandidateProfile,
    observations: &[Option<EhObservation>],
) -> Result<UnitRecovery, CodecError> {
    let diagnostic = diagnose_hierarchical_eh_group(profile, observations)?;
    Ok(UnitRecovery {
        state: match diagnostic.state {
            HierarchicalGroupState::Missing => FragmentState::Missing,
            HierarchicalGroupState::Corrupt => FragmentState::Corrupt,
            HierarchicalGroupState::Verified => FragmentState::Verified,
            HierarchicalGroupState::Recovered => FragmentState::Recovered,
            HierarchicalGroupState::Conflict => FragmentState::Ambiguous,
        },
        common: diagnostic.common,
    })
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum HierarchicalLaneState {
    Absent = 0,
    Corrupt = 1,
    Verified = 2,
    Recovered = 3,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum HierarchicalRepetitionState {
    NotConstructed = 0,
    Corrupt = 1,
    Recovered = 3,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum HierarchicalGroupState {
    Missing = 0,
    Corrupt = 1,
    Verified = 2,
    Recovered = 3,
    Conflict = 4,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct HierarchicalLaneDiagnostic {
    pub state: HierarchicalLaneState,
    pub common: Option<[u8; COMMON_BLOCK_BYTES]>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HierarchicalGroupDiagnostic {
    pub factor: u8,
    pub lanes: Vec<HierarchicalLaneDiagnostic>,
    pub repetition_state: HierarchicalRepetitionState,
    pub repetition_common: Option<[u8; COMMON_BLOCK_BYTES]>,
    pub state: HierarchicalGroupState,
    pub distinct_candidate_count: u8,
    pub common: Option<[u8; COMMON_BLOCK_BYTES]>,
    pub eh_codeword_invocations: u32,
    pub repetition_symbol_invocations: u32,
}

/// Full bounded v7 group adapter result, including the diagnostics and logical
/// recipe invocation charges that must remain independent of caching.
pub fn diagnose_hierarchical_eh_group(
    profile: CandidateProfile,
    observations: &[Option<EhObservation>],
) -> Result<HierarchicalGroupDiagnostic, CodecError> {
    if !PROFILES.contains(&profile)
        || profile.transport != TransportFamily::Eh72HierarchicalRepetition
        || profile.version != 7
        || !matches!(observations.len(), 1 | 2 | 5)
    {
        return Err(CodecError::Parameter);
    }
    let present = observations.iter().filter(|value| value.is_some()).count();
    let mut valid = BTreeMap::<[u8; COMMON_BLOCK_BYTES], bool>::new();
    let mut lanes = Vec::with_capacity(observations.len());
    for observation in observations {
        let Some(observation) = observation else {
            lanes.push(HierarchicalLaneDiagnostic {
                state: HierarchicalLaneState::Absent,
                common: None,
            });
            continue;
        };
        match decode_eh_unit(observation, profile.version) {
            Ok(decoded) => {
                let independently_verified =
                    decoded.quality == DecodeQuality::Verified && observation.erasures.is_empty();
                valid
                    .entry(decoded.common)
                    .and_modify(|verified| *verified |= independently_verified)
                    .or_insert(independently_verified);
                lanes.push(HierarchicalLaneDiagnostic {
                    state: if independently_verified {
                        HierarchicalLaneState::Verified
                    } else {
                        HierarchicalLaneState::Recovered
                    },
                    common: Some(decoded.common),
                });
            }
            Err(_) => lanes.push(HierarchicalLaneDiagnostic {
                state: HierarchicalLaneState::Corrupt,
                common: None,
            }),
        }
    }
    let repetition_constructed = observations.len() > 1 && present != 0;
    let mut repetition_state = HierarchicalRepetitionState::NotConstructed;
    let mut repetition_common = None;
    if repetition_constructed {
        if let Some(repetition) = aggregate_repetition_observation(observations)? {
            match decode_eh_unit(&repetition, profile.version) {
                Ok(decoded) => {
                    repetition_state = HierarchicalRepetitionState::Recovered;
                    repetition_common = Some(decoded.common);
                    // Aggregate bytes are always recovery evidence.
                    valid.entry(decoded.common).or_insert(false);
                }
                Err(_) => repetition_state = HierarchicalRepetitionState::Corrupt,
            }
        }
    }
    let distinct_candidate_count =
        u8::try_from(valid.len()).map_err(|_| CodecError::InternalInvariant)?;
    let (state, common) = match valid.len() {
        0 if present == 0 => (HierarchicalGroupState::Missing, None),
        0 => (HierarchicalGroupState::Corrupt, None),
        1 => {
            let (common, independently_verified) = valid.into_iter().next().expect("one entry");
            (
                if independently_verified {
                    HierarchicalGroupState::Verified
                } else {
                    HierarchicalGroupState::Recovered
                },
                Some(common),
            )
        }
        _ => (HierarchicalGroupState::Conflict, None),
    };
    Ok(HierarchicalGroupDiagnostic {
        factor: observations.len() as u8,
        lanes,
        repetition_state,
        repetition_common,
        state,
        distinct_candidate_count,
        common,
        eh_codeword_invocations: u32::try_from(
            EH_CODEWORDS_PER_UNIT * (present + usize::from(repetition_constructed)),
        )
        .map_err(|_| CodecError::InternalInvariant)?,
        repetition_symbol_invocations: if repetition_constructed {
            (EH_UNIT_BYTES * 8) as u32
        } else {
            0
        },
    })
}

/// Direct polynomial-basis GF(256) multiplication modulo `0x11d`.
pub const fn gf256_mul(mut left: u8, mut right: u8) -> u8 {
    let mut result = 0_u8;
    let mut round = 0;
    while round < 8 {
        if right & 1 != 0 {
            result ^= left;
        }
        right >>= 1;
        let carry = left & 0x80 != 0;
        left <<= 1;
        if carry {
            // The x^8 term is discarded by u8 arithmetic; 0x11d without
            // that term is 0x1d.
            left ^= 0x1d;
        }
        round += 1;
    }
    result
}

const fn rs_alpha_powers() -> [u8; 255] {
    let mut result = [0_u8; 255];
    result[0] = 1;
    let mut exponent = 1;
    while exponent < 255 {
        result[exponent] = gf256_mul(result[exponent - 1], 2);
        exponent += 1;
    }
    result
}

const RS_ALPHA_POWERS: [u8; 255] = rs_alpha_powers();

pub fn gf256_alpha_pow(exponent: usize) -> u8 {
    let mut value = 1_u8;
    for _ in 0..exponent % 255 {
        value = gf256_mul(value, 2);
    }
    value
}

pub fn derive_rs_generator() -> [u8; 65] {
    let mut polynomial = vec![1_u8];
    for exponent in 0..64 {
        let root = gf256_alpha_pow(exponent);
        let mut next = vec![0_u8; polynomial.len() + 1];
        for (index, coefficient) in polynomial.iter().copied().enumerate() {
            next[index] ^= coefficient;
            next[index + 1] ^= gf256_mul(coefficient, root);
        }
        polynomial = next;
    }
    polynomial.try_into().expect("degree-64 generator")
}

pub fn encode_rs255_191(data: &[u8; RS_DATA_BYTES]) -> [u8; RS_CODEWORD_BYTES] {
    let mut work = [0_u8; RS_CODEWORD_BYTES];
    work[..RS_DATA_BYTES].copy_from_slice(data);
    for index in 0..RS_DATA_BYTES {
        let coefficient = work[index];
        if coefficient == 0 {
            continue;
        }
        for generator_index in 1..=RS_PARITY_BYTES {
            work[index + generator_index] ^= gf256_mul(coefficient, RS_GENERATOR[generator_index]);
        }
    }
    let mut encoded = [0_u8; RS_CODEWORD_BYTES];
    encoded[..RS_DATA_BYTES].copy_from_slice(data);
    encoded[RS_DATA_BYTES..].copy_from_slice(&work[RS_DATA_BYTES..]);
    encoded
}

pub fn rs_syndromes(codeword: &[u8; RS_CODEWORD_BYTES]) -> [u8; RS_PARITY_BYTES] {
    let mut syndromes = [0_u8; RS_PARITY_BYTES];
    for (exponent, syndrome) in syndromes.iter_mut().enumerate() {
        let point = gf256_alpha_pow(exponent);
        let mut value = 0_u8;
        for coefficient in codeword.iter().copied() {
            value = gf256_mul(value, point) ^ coefficient;
        }
        *syndrome = value;
    }
    syndromes
}

pub fn verify_rs255_191(codeword: &[u8; RS_CODEWORD_BYTES]) -> bool {
    rs_syndromes(codeword).iter().all(|value| *value == 0)
}

pub const RS_STATUS_SUCCESS: u16 = 0;
pub const RS_STATUS_PARAMETER: u16 = 3;
pub const RS_STATUS_ALGEBRA_BOUNDARY: u16 = 4;
pub const RS_STATUS_NO_UNIQUE_CODEWORD: u16 = 5;
pub const RS_STATUS_LOCAL_CHECK: u16 = 6;
pub const RS_STATUS_RESOURCE_LIMIT: u16 = 11;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RsDecodeTrace {
    pub syndromes: [u8; 64],
    pub erasure_locator: Vec<u8>,
    pub transformed_syndromes: [u8; 64],
    pub bm_input: Vec<u8>,
    pub unknown_error_locator: Vec<u8>,
    pub full_locator: Vec<u8>,
    pub evaluator: [u8; 64],
    pub correction_positions: Vec<u16>,
    pub correction_magnitudes: Vec<u8>,
    pub field_multiplications: u32,
    pub field_inversions: u16,
    pub primitive_steps: u32,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RsDecodeOutcome {
    pub status: u16,
    pub quality: Option<DecodeQuality>,
    /// Present only on success; failures never expose a partial correction.
    pub codeword: Option<[u8; RS_CODEWORD_BYTES]>,
    /// Present only on success and intended for literal conformance evidence.
    pub trace: Option<RsDecodeTrace>,
}

impl RsDecodeOutcome {
    fn failure(status: u16) -> Self {
        Self {
            status,
            quality: None,
            codeword: None,
            trace: None,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct WorkLimit;

struct RsWork {
    multiplications: u32,
    inversions: u16,
    steps: u32,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct RsWorkAccounting {
    multiplications: u32,
    inversions: u16,
    steps: u32,
}

impl RsWork {
    fn new() -> Result<Self, WorkLimit> {
        Ok(Self {
            multiplications: 0,
            inversions: 0,
            steps: 0,
        })
    }

    fn accounting(&self) -> RsWorkAccounting {
        RsWorkAccounting {
            multiplications: self.multiplications,
            inversions: self.inversions,
            steps: self.steps,
        }
    }

    fn charge(&mut self, steps: u32) -> Result<(), WorkLimit> {
        self.steps = self.steps.checked_add(steps).ok_or(WorkLimit)?;
        if self.steps > 1_000_000 {
            return Err(WorkLimit);
        }
        Ok(())
    }

    fn multiply(&mut self, left: u8, right: u8) -> Result<u8, WorkLimit> {
        self.multiplications = self.multiplications.checked_add(1).ok_or(WorkLimit)?;
        if self.multiplications > 80_000 {
            return Err(WorkLimit);
        }
        self.charge(8)?;
        Ok(gf256_mul(left, right))
    }

    fn inverse(&mut self, value: u8) -> Result<u8, WorkLimit> {
        if value == 0 {
            return Err(WorkLimit);
        }
        self.inversions = self.inversions.checked_add(1).ok_or(WorkLimit)?;
        if self.inversions > 128 {
            return Err(WorkLimit);
        }
        self.charge(1)?;
        let mut product = 1;
        let mut base = value;
        let mut exponent = 254;
        while exponent != 0 {
            if exponent & 1 != 0 {
                product = self.multiply(product, base)?;
            }
            base = self.multiply(base, base)?;
            exponent >>= 1;
        }
        Ok(product)
    }

    fn alpha_pow(&self, exponent: usize) -> u8 {
        RS_ALPHA_POWERS[exponent % 255]
    }

    fn polynomial_multiply(&mut self, left: &[u8], right: &[u8]) -> Result<Vec<u8>, WorkLimit> {
        let length = left
            .len()
            .checked_add(right.len())
            .and_then(|value| value.checked_sub(1))
            .ok_or(WorkLimit)?;
        if length > 129 {
            return Err(WorkLimit);
        }
        let mut product = vec![0; length];
        for (left_index, left_value) in left.iter().copied().enumerate() {
            for (right_index, right_value) in right.iter().copied().enumerate() {
                product[left_index + right_index] ^= self.multiply(left_value, right_value)?;
            }
        }
        Ok(product)
    }

    fn polynomial_evaluate(&mut self, polynomial: &[u8], value: u8) -> Result<u8, WorkLimit> {
        let mut result = 0;
        for coefficient in polynomial.iter().copied().rev() {
            result = self.multiply(result, value)? ^ coefficient;
        }
        Ok(result)
    }

    fn syndromes(&mut self, word: &[u8; 255]) -> Result<[u8; 64], WorkLimit> {
        let mut syndromes = [0; 64];
        for (exponent, syndrome) in syndromes.iter_mut().enumerate() {
            let point = self.alpha_pow(exponent);
            let mut value = 0;
            for coefficient in word.iter().copied() {
                value = self.multiply(value, point)? ^ coefficient;
            }
            *syndrome = value;
        }
        Ok(syndromes)
    }
}

fn berlekamp_massey(sequence: &[u8], work: &mut RsWork) -> Result<(Vec<u8>, usize), WorkLimit> {
    let mut connection = vec![1];
    let mut prior_connection = vec![1];
    let mut degree = 0_usize;
    let mut shift = 1_usize;
    let mut prior_discrepancy = 1_u8;
    for (index, item) in sequence.iter().copied().enumerate() {
        let mut discrepancy = item;
        for subindex in 1..=degree {
            if subindex < connection.len() {
                discrepancy ^= work.multiply(connection[subindex], sequence[index - subindex])?;
            }
        }
        if discrepancy == 0 {
            shift = shift.checked_add(1).ok_or(WorkLimit)?;
            continue;
        }
        let old_connection = connection.clone();
        let prior_inverse = work.inverse(prior_discrepancy)?;
        let scale = work.multiply(discrepancy, prior_inverse)?;
        let required = prior_connection.len().checked_add(shift).ok_or(WorkLimit)?;
        if required > 65 {
            return Err(WorkLimit);
        }
        connection.resize(connection.len().max(required), 0);
        for (subindex, coefficient) in prior_connection.iter().copied().enumerate() {
            connection[subindex + shift] ^= work.multiply(scale, coefficient)?;
        }
        if 2 * degree <= index {
            degree = index + 1 - degree;
            prior_connection = old_connection;
            prior_discrepancy = discrepancy;
            shift = 1;
        } else {
            shift = shift.checked_add(1).ok_or(WorkLimit)?;
        }
    }
    while connection.len() > 1 && connection.last() == Some(&0) {
        connection.pop();
    }
    Ok((connection, degree))
}

/// Execute the exact Section-17 errors-and-erasures decoder.
pub fn decode_rs255_191(observation: &[u8], erasures: &[u16]) -> RsDecodeOutcome {
    decode_rs255_191_accounted(observation, erasures).0
}

fn decode_rs255_191_accounted(
    observation: &[u8],
    erasures: &[u16],
) -> (RsDecodeOutcome, Option<RsWorkAccounting>) {
    if observation.len() != RS_CODEWORD_BYTES
        || erasures
            .iter()
            .any(|position| usize::from(*position) >= RS_CODEWORD_BYTES)
        || erasures.windows(2).any(|pair| pair[0] >= pair[1])
    {
        return (RsDecodeOutcome::failure(RS_STATUS_PARAMETER), None);
    }
    if erasures.len() > 64 {
        return (RsDecodeOutcome::failure(RS_STATUS_ALGEBRA_BOUNDARY), None);
    }
    let mut working: [u8; 255] = observation.try_into().expect("checked exact length");
    for position in erasures.iter().copied() {
        working[usize::from(position)] = 0;
    }
    let mut work = match RsWork::new() {
        Ok(work) => work,
        Err(_) => return (RsDecodeOutcome::failure(RS_STATUS_RESOURCE_LIMIT), None),
    };
    let decoded = (|| -> Result<RsDecodeOutcome, WorkLimit> {
        let syndromes = work.syndromes(&working)?;
        if erasures.is_empty() && syndromes.iter().all(|value| *value == 0) {
            return Ok(RsDecodeOutcome {
                status: RS_STATUS_SUCCESS,
                quality: Some(DecodeQuality::Verified),
                codeword: Some(working),
                trace: Some(RsDecodeTrace {
                    syndromes,
                    erasure_locator: vec![1],
                    transformed_syndromes: syndromes,
                    bm_input: syndromes.to_vec(),
                    unknown_error_locator: vec![1],
                    full_locator: vec![1],
                    evaluator: [0; 64],
                    correction_positions: Vec::new(),
                    correction_magnitudes: Vec::new(),
                    field_multiplications: work.multiplications,
                    field_inversions: work.inversions,
                    primitive_steps: work.steps,
                }),
            });
        }
        let mut erasure_locator = vec![1];
        for position in erasures.iter().copied() {
            let location = work.alpha_pow(254 - usize::from(position));
            erasure_locator = work.polynomial_multiply(&erasure_locator, &[1, location])?;
            if erasure_locator.len() > 65 {
                return Ok(RsDecodeOutcome::failure(RS_STATUS_ALGEBRA_BOUNDARY));
            }
        }
        let mut transformed = [0; 64];
        for index in 0..64 {
            for subindex in 0..=index.min(erasures.len()) {
                transformed[index] ^=
                    work.multiply(erasure_locator[subindex], syndromes[index - subindex])?;
            }
        }
        let bm_input = transformed[erasures.len()..].to_vec();
        let (unknown_locator, unknown_degree) = berlekamp_massey(&bm_input, &mut work)?;
        if unknown_locator.len() != unknown_degree + 1
            || unknown_locator.len() > 33
            || 2 * unknown_degree + erasures.len() > 64
        {
            return Ok(RsDecodeOutcome::failure(RS_STATUS_ALGEBRA_BOUNDARY));
        }
        let full_locator = work.polynomial_multiply(&erasure_locator, &unknown_locator)?;
        if full_locator.len() > 65 || full_locator.len() - 1 != erasures.len() + unknown_degree {
            return Ok(RsDecodeOutcome::failure(RS_STATUS_ALGEBRA_BOUNDARY));
        }
        let mut roots = Vec::with_capacity(full_locator.len() - 1);
        for position in 0..255 {
            if work.polynomial_evaluate(&full_locator, work.alpha_pow(position + 1))? == 0 {
                roots.push(position as u16);
            }
        }
        if roots.len() != full_locator.len() - 1
            || erasures
                .iter()
                .any(|erasure| roots.binary_search(erasure).is_err())
            || roots
                .iter()
                .filter(|position| erasures.binary_search(position).is_err())
                .count()
                != unknown_degree
        {
            return Ok(RsDecodeOutcome::failure(RS_STATUS_NO_UNIQUE_CODEWORD));
        }
        let mut evaluator = [0; 64];
        for (syndrome_index, syndrome) in syndromes.iter().copied().enumerate() {
            for (locator_index, locator) in full_locator.iter().copied().enumerate() {
                let evaluator_index = syndrome_index + locator_index;
                if evaluator_index >= evaluator.len() {
                    break;
                }
                evaluator[evaluator_index] ^= work.multiply(syndrome, locator)?;
            }
        }
        let derivative = (1..full_locator.len())
            .map(|index| {
                if index % 2 == 1 {
                    full_locator[index]
                } else {
                    0
                }
            })
            .collect::<Vec<_>>();
        let mut correction_positions = Vec::with_capacity(roots.len());
        let mut correction_magnitudes = Vec::with_capacity(roots.len());
        for position in roots.iter().copied() {
            let position_index = usize::from(position);
            let location = work.alpha_pow(254 - position_index);
            let argument = work.alpha_pow(position_index + 1);
            let denominator = work.polynomial_evaluate(&derivative, argument)?;
            if denominator == 0 {
                return Ok(RsDecodeOutcome::failure(RS_STATUS_NO_UNIQUE_CODEWORD));
            }
            let numerator = work.polynomial_evaluate(&evaluator, argument)?;
            let inverse = work.inverse(denominator)?;
            let quotient = work.multiply(numerator, inverse)?;
            let magnitude = work.multiply(location, quotient)?;
            if magnitude == 0 && erasures.binary_search(&position).is_err() {
                return Ok(RsDecodeOutcome::failure(RS_STATUS_NO_UNIQUE_CODEWORD));
            }
            correction_positions.push(position);
            correction_magnitudes.push(magnitude);
        }
        let error_count = correction_positions
            .iter()
            .zip(&correction_magnitudes)
            .filter(|(position, magnitude)| {
                **magnitude != 0 && erasures.binary_search(position).is_err()
            })
            .count();
        if error_count != unknown_degree || 2 * error_count + erasures.len() > 64 {
            return Ok(RsDecodeOutcome::failure(RS_STATUS_NO_UNIQUE_CODEWORD));
        }
        for (position, magnitude) in correction_positions
            .iter()
            .copied()
            .zip(correction_magnitudes.iter().copied())
        {
            working[usize::from(position)] ^= magnitude;
        }
        if work.syndromes(&working)?.iter().any(|value| *value != 0) {
            return Ok(RsDecodeOutcome::failure(RS_STATUS_NO_UNIQUE_CODEWORD));
        }
        Ok(RsDecodeOutcome {
            status: RS_STATUS_SUCCESS,
            quality: Some(DecodeQuality::Recovered),
            codeword: Some(working),
            trace: Some(RsDecodeTrace {
                syndromes,
                erasure_locator,
                transformed_syndromes: transformed,
                bm_input,
                unknown_error_locator: unknown_locator,
                full_locator,
                evaluator,
                correction_positions,
                correction_magnitudes,
                field_multiplications: work.multiplications,
                field_inversions: work.inversions,
                primitive_steps: work.steps,
            }),
        })
    })();
    let outcome = decoded.unwrap_or_else(|_| RsDecodeOutcome::failure(RS_STATUS_RESOURCE_LIMIT));
    (outcome, Some(work.accounting()))
}

pub fn decode_rs_unit(
    observation: &[u8],
    erasures: &[u16],
    expected_profile_version: u16,
) -> Result<DecodedUnit, u16> {
    let Some(profile) = profile_by_version(expected_profile_version) else {
        return Err(RS_STATUS_PARAMETER);
    };
    if profile.transport != TransportFamily::Rs255_191 {
        return Err(RS_STATUS_PARAMETER);
    }
    let outcome = decode_rs255_191(observation, erasures);
    let Some(codeword) = outcome.codeword else {
        return Err(outcome.status);
    };
    let common: [u8; 191] = codeword[..191].try_into().expect("systematic prefix");
    decode_common_block(&common, expected_profile_version).map_err(|_| RS_STATUS_LOCAL_CHECK)?;
    Ok(DecodedUnit {
        common,
        quality: outcome.quality.expect("successful decode quality"),
    })
}

pub fn decode_clean_rs_unit(
    codeword: &[u8; RS_CODEWORD_BYTES],
    expected_profile_version: u16,
) -> Result<DecodedUnit, CodecError> {
    if !verify_rs255_191(codeword) {
        return Err(CodecError::Corrupt);
    }
    let common: [u8; COMMON_BLOCK_BYTES] = codeword[..RS_DATA_BYTES]
        .try_into()
        .expect("systematic data prefix");
    decode_common_block(&common, expected_profile_version).map_err(|_| CodecError::LocalCheck)?;
    Ok(DecodedUnit {
        common,
        quality: DecodeQuality::Verified,
    })
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use gb_foundation::{ManifestValue, validate_canonical_manifest};

    use super::*;

    fn object(value: &ManifestValue) -> &BTreeMap<String, ManifestValue> {
        let ManifestValue::Object(value) = value else {
            panic!("object")
        };
        value
    }

    fn array(value: &ManifestValue) -> &[ManifestValue] {
        let ManifestValue::Array(value) = value else {
            panic!("array")
        };
        value
    }

    fn text(value: &ManifestValue) -> &str {
        let ManifestValue::String(value) = value else {
            panic!("string")
        };
        value
    }

    fn unsigned(value: &ManifestValue) -> u64 {
        let ManifestValue::U64(value) = value else {
            panic!("unsigned")
        };
        *value
    }

    fn hex(value: &str) -> Vec<u8> {
        assert_eq!(value.len() % 2, 0);
        value
            .as_bytes()
            .chunks_exact(2)
            .map(|pair| {
                let pair = std::str::from_utf8(pair).unwrap();
                u8::from_str_radix(pair, 16).unwrap()
            })
            .collect()
    }

    #[test]
    fn fast_eh_unit_path_is_exhaustively_equal_at_the_single_bit_boundary() {
        let common = crate::encode_common_block(&crate::CommonBlock {
            profile_version: 1,
            section_id: 1,
            semantic_copy_id: 0,
            section_type: crate::SECTION_INVENTORY,
            section_version: 0,
            fragment_index: 0,
            fragment_count: 1,
            section_envelope_length: 1,
            payload: vec![0x42],
        })
        .unwrap();
        let clean = encode_eh_unit(&common);
        let clean_observation = EhObservation {
            encoded: clean,
            erasures: Vec::new(),
        };
        assert_eq!(
            decode_eh_unit_fast(&clean_observation, 1),
            decode_eh_unit(&clean_observation, 1)
        );
        for bit in 0..EH_CODEWORD_BITS {
            let mut encoded = clean;
            encoded[bit / 8] ^= 1 << (7 - bit % 8);
            let observation = EhObservation {
                encoded,
                erasures: Vec::new(),
            };
            assert_eq!(
                decode_eh_unit_fast(&observation, 1),
                decode_eh_unit(&observation, 1),
                "bit {bit}"
            );
        }
    }

    #[test]
    fn direct_rs_work_accounting_is_literal_and_excludes_static_alpha_derivation() {
        let clean_data = std::array::from_fn(|index| index as u8);
        let clean_word = encode_rs255_191(&clean_data);
        let (clean, clean_work) = decode_rs255_191_accounted(&clean_word, &[]);
        assert_eq!(clean.status, RS_STATUS_SUCCESS);
        let clean_work = clean_work.expect("valid invocation accounting");
        assert_eq!(
            clean_work,
            RsWorkAccounting {
                multiplications: 16_320,
                inversions: 0,
                steps: 130_560,
            }
        );
        assert_eq!(
            clean_work.steps,
            8 * clean_work.multiplications + u32::from(clean_work.inversions)
        );

        let expected = BTreeMap::from([
            ("single-data-first", (33_522, 3, 268_179)),
            ("e0-s64", (66_880, 64, 535_104)),
            ("e32-s0", (49_425, 96, 395_496)),
            ("e1-s63", (22_449, 1, 179_593)),
            ("e33-s0", (27_905, 64, 223_304)),
        ]);
        let manifest =
            validate_canonical_manifest(include_bytes!("../../../conformance/rs255-191-v0.json"))
                .unwrap();
        let root = object(&manifest);
        let mut seen = Vec::new();
        for value in array(&root["decode_kats"]) {
            let row = object(value);
            let case_id = text(&row["id"]);
            let Some(&(multiplications, inversions, steps)) = expected.get(case_id) else {
                continue;
            };
            let observation = hex(text(&row["observation_hex"]));
            let erasures = array(&row["erasure_positions"])
                .iter()
                .map(|value| u16::try_from(unsigned(value)).unwrap())
                .collect::<Vec<_>>();
            let expected_status = u16::try_from(unsigned(&row["expected_status"])).unwrap();
            let (outcome, accounting) = decode_rs255_191_accounted(&observation, &erasures);
            assert_eq!(outcome.status, expected_status, "{case_id}");
            let accounting = accounting.expect("bounded valid invocation accounting");
            assert_eq!(
                accounting,
                RsWorkAccounting {
                    multiplications,
                    inversions,
                    steps,
                },
                "{case_id}"
            );
            assert_eq!(
                accounting.steps,
                8 * accounting.multiplications + u32::from(accounting.inversions),
                "{case_id}"
            );
            if let Some(trace) = outcome.trace {
                assert_eq!(trace.field_multiplications, accounting.multiplications);
                assert_eq!(trace.field_inversions, accounting.inversions);
                assert_eq!(trace.primitive_steps, accounting.steps);
            }
            seen.push(case_id);
        }
        seen.sort_unstable();
        assert_eq!(seen, expected.keys().copied().collect::<Vec<_>>());
    }
}
