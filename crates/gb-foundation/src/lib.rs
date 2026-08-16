pub mod constants;

use std::collections::BTreeMap;
use std::fmt;

use serde::Deserializer;
use serde::de::{self, DeserializeSeed, MapAccess, SeqAccess, Visitor};
use sha2::{Digest, Sha256};

pub const MAX_MANIFEST_BYTES: usize = 1_048_576;
pub const MAX_MANIFEST_DEPTH: usize = 32;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FoundationError(&'static str);

impl fmt::Display for FoundationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.0)
    }
}

impl std::error::Error for FoundationError {}

type Result<T> = std::result::Result<T, FoundationError>;

pub fn u16_be(value: u64) -> Result<[u8; 2]> {
    let value = u16::try_from(value).map_err(|_| FoundationError("u16 out of range"))?;
    Ok(value.to_be_bytes())
}

pub fn u32_be(value: u64) -> Result<[u8; 4]> {
    let value = u32::try_from(value).map_err(|_| FoundationError("u32 out of range"))?;
    Ok(value.to_be_bytes())
}

fn valid_domain(domain: &[u8]) -> bool {
    domain.last() == Some(&0)
        && !domain[..domain.len().saturating_sub(1)].contains(&0)
        && domain[..domain.len().saturating_sub(1)].is_ascii()
}

pub fn frame_preimage(domain: &[u8], fields: &[&[u8]]) -> Result<Vec<u8>> {
    if !valid_domain(domain) {
        return Err(FoundationError("invalid identity domain"));
    }
    let count = u16_be(
        fields
            .len()
            .try_into()
            .map_err(|_| FoundationError("field count out of range"))?,
    )?;
    let mut total = domain
        .len()
        .checked_add(2)
        .ok_or(FoundationError("preimage length overflow"))?;
    for field in fields {
        u32_be(
            field
                .len()
                .try_into()
                .map_err(|_| FoundationError("field length out of range"))?,
        )?;
        total = total
            .checked_add(4)
            .and_then(|size| size.checked_add(field.len()))
            .ok_or(FoundationError("preimage length overflow"))?;
    }

    let mut output = Vec::with_capacity(total);
    output.extend_from_slice(domain);
    output.extend_from_slice(&count);
    for field in fields {
        output.extend_from_slice(&u32_be(field.len() as u64)?);
        output.extend_from_slice(field);
    }
    Ok(output)
}

pub fn identity_hex(domain: &[u8], fields: &[&[u8]]) -> Result<String> {
    Ok(format!(
        "{:x}",
        Sha256::digest(frame_preimage(domain, fields)?)
    ))
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ManifestValue {
    Object(BTreeMap<String, ManifestValue>),
    Array(Vec<ManifestValue>),
    String(String),
    Bool(bool),
    U64(u64),
}

fn valid_key(key: &str) -> bool {
    !key.is_empty() && key.bytes().all(|byte| (0x20..=0x7e).contains(&byte))
}

fn check_input_depth(text: &str) -> Result<()> {
    let mut depth = 0usize;
    let mut in_string = false;
    let mut escaped = false;
    for character in text.chars() {
        if in_string {
            if escaped {
                escaped = false;
            } else if character == '\\' {
                escaped = true;
            } else if character == '"' {
                in_string = false;
            }
        } else if character == '"' {
            in_string = true;
        } else if matches!(character, '[' | '{') {
            depth += 1;
            if depth > MAX_MANIFEST_DEPTH {
                return Err(FoundationError("manifest nesting exceeds 32"));
            }
        } else if matches!(character, ']' | '}') {
            depth = depth.saturating_sub(1);
        }
    }
    Ok(())
}

struct ValueSeed {
    depth: usize,
}

impl<'de> DeserializeSeed<'de> for ValueSeed {
    type Value = ManifestValue;

    fn deserialize<D>(self, deserializer: D) -> std::result::Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_any(ValueVisitor { depth: self.depth })
    }
}

struct ValueVisitor {
    depth: usize,
}

impl<'de> Visitor<'de> for ValueVisitor {
    type Value = ManifestValue;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a canonical-manifest v0 value")
    }

    fn visit_bool<E>(self, value: bool) -> std::result::Result<Self::Value, E> {
        Ok(ManifestValue::Bool(value))
    }

    fn visit_u64<E>(self, value: u64) -> std::result::Result<Self::Value, E> {
        Ok(ManifestValue::U64(value))
    }

    fn visit_i64<E>(self, _value: i64) -> std::result::Result<Self::Value, E>
    where
        E: de::Error,
    {
        Err(E::custom("signed integer is outside manifest-v0"))
    }

    fn visit_f64<E>(self, _value: f64) -> std::result::Result<Self::Value, E>
    where
        E: de::Error,
    {
        Err(E::custom("float is outside manifest-v0"))
    }

    fn visit_str<E>(self, value: &str) -> std::result::Result<Self::Value, E> {
        Ok(ManifestValue::String(value.to_owned()))
    }

    fn visit_string<E>(self, value: String) -> std::result::Result<Self::Value, E> {
        Ok(ManifestValue::String(value))
    }

    fn visit_seq<A>(self, mut sequence: A) -> std::result::Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        if self.depth > MAX_MANIFEST_DEPTH {
            return Err(de::Error::custom("manifest nesting exceeds 32"));
        }
        let mut values = Vec::new();
        while let Some(value) = sequence.next_element_seed(ValueSeed {
            depth: self.depth + 1,
        })? {
            values.push(value);
        }
        Ok(ManifestValue::Array(values))
    }

    fn visit_map<A>(self, mut map: A) -> std::result::Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        if self.depth > MAX_MANIFEST_DEPTH {
            return Err(de::Error::custom("manifest nesting exceeds 32"));
        }
        let mut values = BTreeMap::new();
        while let Some(key) = map.next_key::<String>()? {
            if !valid_key(&key) {
                return Err(de::Error::custom("invalid manifest object key"));
            }
            let value = map.next_value_seed(ValueSeed {
                depth: self.depth + 1,
            })?;
            if values.insert(key, value).is_some() {
                return Err(de::Error::custom("duplicate manifest object key"));
            }
        }
        Ok(ManifestValue::Object(values))
    }
}

pub fn parse_manifest(data: &[u8]) -> Result<ManifestValue> {
    if data.len() > MAX_MANIFEST_BYTES {
        return Err(FoundationError("manifest input exceeds byte limit"));
    }
    let text = std::str::from_utf8(data).map_err(|_| FoundationError("manifest is not UTF-8"))?;
    check_input_depth(text)?;
    let mut deserializer = serde_json::Deserializer::from_str(text);
    let value = ValueSeed { depth: 1 }
        .deserialize(&mut deserializer)
        .map_err(|_| FoundationError("invalid manifest JSON or value"))?;
    deserializer
        .end()
        .map_err(|_| FoundationError("trailing manifest data"))?;
    if !matches!(value, ManifestValue::Object(_)) {
        return Err(FoundationError("manifest top level must be an object"));
    }
    Ok(value)
}

struct Writer {
    bytes: Vec<u8>,
}

impl Writer {
    fn add(&mut self, bytes: &[u8]) -> Result<()> {
        if self.bytes.len().saturating_add(bytes.len()) > MAX_MANIFEST_BYTES {
            return Err(FoundationError("manifest output exceeds byte limit"));
        }
        self.bytes.extend_from_slice(bytes);
        Ok(())
    }
}

fn write_string(writer: &mut Writer, value: &str) -> Result<()> {
    writer.add(b"\"")?;
    const HEX: &[u8; 16] = b"0123456789abcdef";
    for character in value.chars() {
        match character {
            '"' => writer.add(b"\\\"")?,
            '\\' => writer.add(b"\\\\")?,
            '\u{08}' => writer.add(b"\\b")?,
            '\t' => writer.add(b"\\t")?,
            '\n' => writer.add(b"\\n")?,
            '\u{0c}' => writer.add(b"\\f")?,
            '\r' => writer.add(b"\\r")?,
            control if control <= '\u{1f}' => {
                let code = control as usize;
                writer.add(&[b'\\', b'u', b'0', b'0', HEX[code >> 4], HEX[code & 0x0f]])?;
            }
            scalar => {
                let mut buffer = [0; 4];
                writer.add(scalar.encode_utf8(&mut buffer).as_bytes())?;
            }
        }
    }
    writer.add(b"\"")
}

fn write_value(writer: &mut Writer, value: &ManifestValue, depth: usize) -> Result<()> {
    match value {
        ManifestValue::Object(values) => {
            if depth > MAX_MANIFEST_DEPTH {
                return Err(FoundationError("manifest nesting exceeds 32"));
            }
            writer.add(b"{")?;
            for (index, (key, value)) in values.iter().enumerate() {
                if !valid_key(key) {
                    return Err(FoundationError("invalid manifest object key"));
                }
                if index != 0 {
                    writer.add(b",")?;
                }
                write_string(writer, key)?;
                writer.add(b":")?;
                write_value(writer, value, depth + 1)?;
            }
            writer.add(b"}")
        }
        ManifestValue::Array(values) => {
            if depth > MAX_MANIFEST_DEPTH {
                return Err(FoundationError("manifest nesting exceeds 32"));
            }
            writer.add(b"[")?;
            for (index, value) in values.iter().enumerate() {
                if index != 0 {
                    writer.add(b",")?;
                }
                write_value(writer, value, depth + 1)?;
            }
            writer.add(b"]")
        }
        ManifestValue::String(value) => write_string(writer, value),
        ManifestValue::Bool(value) => writer.add(if *value { b"true" } else { b"false" }),
        ManifestValue::U64(value) => writer.add(value.to_string().as_bytes()),
    }
}

pub fn serialize_manifest(value: &ManifestValue) -> Result<Vec<u8>> {
    if !matches!(value, ManifestValue::Object(_)) {
        return Err(FoundationError("manifest top level must be an object"));
    }
    let mut writer = Writer { bytes: Vec::new() };
    write_value(&mut writer, value, 1)?;
    writer.add(b"\n")?;
    Ok(writer.bytes)
}

pub fn canonicalize_manifest(data: &[u8]) -> Result<Vec<u8>> {
    serialize_manifest(&parse_manifest(data)?)
}

pub fn validate_canonical_manifest(data: &[u8]) -> Result<ManifestValue> {
    let value = parse_manifest(data)?;
    if serialize_manifest(&value)? != data {
        return Err(FoundationError("manifest is not canonical"));
    }
    Ok(value)
}
