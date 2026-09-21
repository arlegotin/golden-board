//! Development section codec. A decoded body still needs all content checks.
use std::collections::{BTreeMap, VecDeque};

pub const MAX_BODY_BYTES: usize = 16_384;
pub const MAX_ENCODER_BYTES: usize = 18_435;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BodyCodecError {
    Size,
    Version,
    Framing,
    BackReference,
}

pub type Result<T> = std::result::Result<T, BodyCodecError>;

/// Decode atomically. Version is explicit, not inferred from payload bytes.
pub fn decode_body(version: u16, payload: &[u8]) -> Result<Vec<u8>> {
    if payload.len() > MAX_BODY_BYTES {
        return Err(BodyCodecError::Size);
    }
    match version {
        0 => Ok(payload.to_vec()),
        1 => decode_lzss(payload),
        _ => Err(BodyCodecError::Version),
    }
}

/// Decode every admitted tokenization, without imposing encoder tie rules.
pub fn decode_lzss(payload: &[u8]) -> Result<Vec<u8>> {
    if !(3..=MAX_BODY_BYTES).contains(&payload.len()) {
        return Err(BodyCodecError::Size);
    }
    if payload[0] != 3 {
        return Err(BodyCodecError::Version);
    }
    let expected = usize::from(u16::from_be_bytes([payload[1], payload[2]]));
    if expected > MAX_BODY_BYTES {
        return Err(BodyCodecError::Size);
    }
    let mut output = Vec::with_capacity(expected);
    let mut cursor = 3;
    while output.len() < expected {
        let flags = *payload.get(cursor).ok_or(BodyCodecError::Framing)?;
        cursor += 1;
        for bit in (0..8).rev() {
            if output.len() == expected {
                if u16::from(flags) & ((1u16 << (bit + 1)) - 1) != 0 {
                    return Err(BodyCodecError::Framing);
                }
                break;
            }
            if flags & (1 << bit) == 0 {
                let value = *payload.get(cursor).ok_or(BodyCodecError::Framing)?;
                cursor += 1;
                output.push(value);
            } else {
                let token = payload
                    .get(cursor..cursor + 2)
                    .ok_or(BodyCodecError::Framing)?;
                cursor += 2;
                let packed = u16::from_be_bytes([token[0], token[1]]);
                let distance = usize::from(packed >> 4) + 1;
                let count = usize::from(packed & 15) + 3;
                if distance > output.len() {
                    return Err(BodyCodecError::BackReference);
                }
                if count > expected - output.len() {
                    return Err(BodyCodecError::Size);
                }
                for _ in 0..count {
                    output.push(output[output.len() - distance]);
                }
            }
        }
    }
    if cursor != payload.len() {
        return Err(BodyCodecError::Framing);
    }
    Ok(output)
}

/// Select compression only for strictly smaller complete payloads.
pub fn encode_body(raw: &[u8]) -> Result<(u16, Vec<u8>)> {
    let compressed = encode_lzss(raw)?;
    if compressed.len() < raw.len() {
        Ok((1, compressed))
    } else {
        Ok((0, raw.to_vec()))
    }
}

/// Candidate encoding can exceed the section bound; encode_body selects raw.
pub fn encode_lzss(raw: &[u8]) -> Result<Vec<u8>> {
    if raw.len() > MAX_BODY_BYTES {
        return Err(BodyCodecError::Size);
    }
    let mut output = Vec::with_capacity(3 + raw.len() + raw.len().div_ceil(8));
    output.push(3);
    output.extend_from_slice(&(raw.len() as u16).to_be_bytes());
    let mut history: BTreeMap<[u8; 3], VecDeque<usize>> = BTreeMap::new();
    let mut cursor = 0;
    while cursor < raw.len() {
        let flag_index = output.len();
        output.push(0);
        for bit in (0..8).rev() {
            if cursor == raw.len() {
                break;
            }
            let maximum = 18.min(raw.len() - cursor);
            let mut length = 0;
            let mut distance = 0;
            if maximum >= 3 {
                let key: [u8; 3] = raw[cursor..cursor + 3].try_into().unwrap();
                if let Some(candidates) = history.get(&key) {
                    for &candidate in candidates.iter().rev() {
                        let mut matched = 3;
                        while matched < maximum && raw[candidate + matched] == raw[cursor + matched]
                        {
                            matched += 1;
                        }
                        if matched > length {
                            length = matched;
                            distance = cursor - candidate;
                        }
                        if matched == maximum {
                            break;
                        }
                    }
                }
            }
            if length >= 3 {
                output[flag_index] |= 1 << bit;
                let packed = (((distance - 1) << 4) | (length - 3)) as u16;
                output.extend_from_slice(&packed.to_be_bytes());
            } else {
                length = 1;
                output.push(raw[cursor]);
            }
            for index in cursor..cursor + length {
                if index + 3 <= raw.len() {
                    let key = raw[index..index + 3].try_into().unwrap();
                    history.entry(key).or_default().push_back(index);
                }
                if index >= 4096 {
                    let expired = index - 4096;
                    let key: [u8; 3] = raw[expired..expired + 3].try_into().unwrap();
                    if let Some(entries) = history.get_mut(&key) {
                        entries.pop_front();
                        if entries.is_empty() {
                            history.remove(&key);
                        }
                    }
                }
            }
            cursor += length;
        }
    }
    debug_assert!(output.len() <= MAX_ENCODER_BYTES);
    Ok(output)
}
