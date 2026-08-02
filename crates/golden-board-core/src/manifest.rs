use crate::constants::{MANIFEST, MANIFEST_DIAGNOSTICS};
use crate::{scalar_preimage, sha256_hex};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

const MAX_INPUT: usize = 1 << 24;
const MAX_DEPTH: usize = 64;
const MAX_COLLECTION: usize = 65_535;
const MAX_NODES: usize = 1_000_000;
const MAX_STRING_BYTES: usize = 1 << 24;
const MAX_U64_TEXT: &str = "18446744073709551615";

const LIMIT: &str = MANIFEST_DIAGNOSTICS[0];
const UTF8: &str = MANIFEST_DIAGNOSTICS[1];
const SYNTAX: &str = MANIFEST_DIAGNOSTICS[2];
const TRAILING_DATA: &str = MANIFEST_DIAGNOSTICS[3];
const DUPLICATE_KEY: &str = MANIFEST_DIAGNOSTICS[4];
const UNSUPPORTED_TYPE: &str = MANIFEST_DIAGNOSTICS[5];
const INTEGER_RANGE: &str = MANIFEST_DIAGNOSTICS[6];
const INVALID_KEY: &str = MANIFEST_DIAGNOSTICS[7];
const INVALID_UNICODE: &str = MANIFEST_DIAGNOSTICS[8];
const NONCANONICAL: &str = MANIFEST_DIAGNOSTICS[9];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ManifestError {
    code: &'static str,
}

impl ManifestError {
    const fn new(code: &'static str) -> Self {
        Self { code }
    }

    pub const fn code(&self) -> &'static str {
        self.code
    }
}

impl fmt::Display for ManifestError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.code)
    }
}

impl std::error::Error for ManifestError {}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ManifestValue {
    String(String),
    Bool(bool),
    Integer(u64),
    Array(Vec<ManifestValue>),
    Object(BTreeMap<String, ManifestValue>),
}

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
struct RawString(Vec<u32>);

#[derive(Debug)]
enum RawValue<'a> {
    String(RawString),
    Bool(bool),
    Number(&'a str),
    Array(Vec<RawValue<'a>>),
    Object(Vec<(RawString, RawValue<'a>)>),
    Null,
}

fn error(code: &'static str) -> ManifestError {
    ManifestError::new(code)
}

fn utf8_width(codepoint: u32) -> usize {
    match codepoint {
        0..=0x7f => 1,
        0x80..=0x7ff => 2,
        0x800..=0xffff => 3,
        _ => 4,
    }
}

fn is_json_whitespace(byte: u8) -> bool {
    matches!(byte, b' ' | b'\t' | b'\r' | b'\n')
}

fn hex_value(byte: u8) -> Option<u32> {
    match byte {
        b'0'..=b'9' => Some(u32::from(byte - b'0')),
        b'a'..=b'f' => Some(u32::from(byte - b'a') + 10),
        b'A'..=b'F' => Some(u32::from(byte - b'A') + 10),
        _ => None,
    }
}

fn hex_quad(raw: &[u8], start: usize) -> Option<u32> {
    let digits = raw.get(start..start.checked_add(4)?)?;
    let mut value = 0;
    for byte in digits {
        value = (value << 4) | hex_value(*byte)?;
    }
    Some(value)
}

fn checked_decoded_add(decoded: &mut usize, width: usize) -> Result<(), ManifestError> {
    *decoded = decoded.checked_add(width).ok_or_else(|| error(LIMIT))?;
    if *decoded > MAX_STRING_BYTES {
        return Err(error(LIMIT));
    }
    Ok(())
}

fn scan_string(raw: &[u8], start: usize) -> Result<usize, ManifestError> {
    let mut index = start + 1;
    let mut decoded = 0;
    while index < raw.len() {
        let byte = raw[index];
        index += 1;
        if byte == b'"' {
            return Ok(index);
        }

        let mut width = 1;
        if byte == b'\\' && index < raw.len() {
            let escape = raw[index];
            index += 1;
            if escape == b'u'
                && let Some(mut codepoint) = hex_quad(raw, index)
            {
                index += 4;
                if (0xd800..=0xdbff).contains(&codepoint)
                    && raw.get(index..index.saturating_add(2)) == Some(&b"\\u"[..])
                    && let Some(low) = hex_quad(raw, index + 2)
                    && (0xdc00..=0xdfff).contains(&low)
                {
                    codepoint = 0x10000 + ((codepoint - 0xd800) << 10) + low - 0xdc00;
                    index += 6;
                }
                width = utf8_width(codepoint);
            }
        }
        checked_decoded_add(&mut decoded, width)?;
    }
    Ok(index)
}

fn scan_structural_limits(raw: &[u8]) -> Result<(), ManifestError> {
    let mut commas = Vec::<usize>::new();
    let mut nodes = 0usize;
    let mut index = 0usize;

    while index < raw.len() {
        let byte = raw[index];
        if is_json_whitespace(byte) {
            index += 1;
            continue;
        }
        if byte == b'"' {
            let end = scan_string(raw, index)?;
            let mut following = end;
            while raw.get(following).copied().is_some_and(is_json_whitespace) {
                following += 1;
            }
            if raw.get(following) != Some(&b':') {
                bump_count(&mut nodes, MAX_NODES)?;
            }
            index = end;
            continue;
        }
        if matches!(byte, b'[' | b'{') {
            bump_count(&mut nodes, MAX_NODES)?;
            if commas.len() >= MAX_DEPTH {
                return Err(error(LIMIT));
            }
            commas.push(0);
            index += 1;
            continue;
        }
        if matches!(byte, b']' | b'}') {
            commas.pop();
            index += 1;
            continue;
        }
        if byte == b',' {
            if let Some(count) = commas.last_mut() {
                if *count >= MAX_COLLECTION - 1 {
                    return Err(error(LIMIT));
                }
                *count += 1;
            }
            index += 1;
            continue;
        }
        if byte == b':' {
            index += 1;
            continue;
        }

        bump_count(&mut nodes, MAX_NODES)?;
        index += 1;
        while index < raw.len()
            && !is_json_whitespace(raw[index])
            && !matches!(raw[index], b'[' | b']' | b'{' | b'}' | b':' | b',' | b'"')
        {
            index += 1;
        }
    }
    Ok(())
}

fn bump_count(count: &mut usize, maximum: usize) -> Result<(), ManifestError> {
    if *count >= maximum {
        return Err(error(LIMIT));
    }
    *count += 1;
    Ok(())
}

struct Parser<'a> {
    text: &'a str,
    index: usize,
    nodes: usize,
}

impl<'a> Parser<'a> {
    fn new(text: &'a str) -> Self {
        Self {
            text,
            index: 0,
            nodes: 0,
        }
    }

    fn parse(mut self) -> Result<RawValue<'a>, ManifestError> {
        self.skip_whitespace();
        let value = self.parse_value(0)?;
        let tail = &self.text.as_bytes()[self.index..];
        if tail.iter().copied().any(|byte| !is_json_whitespace(byte))
            || (tail.first() == Some(&b'\n') && tail != b"\n")
        {
            return Err(error(TRAILING_DATA));
        }
        Ok(value)
    }

    fn bytes(&self) -> &'a [u8] {
        self.text.as_bytes()
    }

    fn skip_whitespace(&mut self) {
        while self
            .bytes()
            .get(self.index)
            .copied()
            .is_some_and(is_json_whitespace)
        {
            self.index += 1;
        }
    }

    fn take(&mut self, expected: u8) -> bool {
        if self.bytes().get(self.index) == Some(&expected) {
            self.index += 1;
            true
        } else {
            false
        }
    }

    fn parse_value(&mut self, depth: usize) -> Result<RawValue<'a>, ManifestError> {
        self.skip_whitespace();
        let byte = self
            .bytes()
            .get(self.index)
            .copied()
            .ok_or_else(|| error(SYNTAX))?;
        bump_count(&mut self.nodes, MAX_NODES)?;
        match byte {
            b'"' => self.parse_string().map(RawValue::String),
            b'{' => self.parse_object(depth.checked_add(1).ok_or_else(|| error(LIMIT))?),
            b'[' => self.parse_array(depth.checked_add(1).ok_or_else(|| error(LIMIT))?),
            b't' => {
                self.consume_literal(b"true")?;
                Ok(RawValue::Bool(true))
            }
            b'f' => {
                self.consume_literal(b"false")?;
                Ok(RawValue::Bool(false))
            }
            b'n' => {
                self.consume_literal(b"null")?;
                Ok(RawValue::Null)
            }
            b'-' | b'0'..=b'9' => self.parse_number().map(RawValue::Number),
            _ => Err(error(SYNTAX)),
        }
    }

    fn consume_literal(&mut self, literal: &[u8]) -> Result<(), ManifestError> {
        if self.bytes().get(self.index..self.index + literal.len()) != Some(literal) {
            return Err(error(SYNTAX));
        }
        self.index += literal.len();
        Ok(())
    }

    fn parse_array(&mut self, depth: usize) -> Result<RawValue<'a>, ManifestError> {
        if depth > MAX_DEPTH {
            return Err(error(LIMIT));
        }
        self.index += 1;
        self.skip_whitespace();
        let mut items = Vec::new();
        if self.take(b']') {
            return Ok(RawValue::Array(items));
        }
        loop {
            if items.len() >= MAX_COLLECTION {
                return Err(error(LIMIT));
            }
            let item = self.parse_value(depth)?;
            items.push(item);
            self.skip_whitespace();
            if self.take(b']') {
                return Ok(RawValue::Array(items));
            }
            if !self.take(b',') {
                return Err(error(SYNTAX));
            }
        }
    }

    fn parse_object(&mut self, depth: usize) -> Result<RawValue<'a>, ManifestError> {
        if depth > MAX_DEPTH {
            return Err(error(LIMIT));
        }
        self.index += 1;
        self.skip_whitespace();
        let mut pairs = Vec::new();
        if self.take(b'}') {
            return Ok(RawValue::Object(pairs));
        }
        loop {
            if pairs.len() >= MAX_COLLECTION {
                return Err(error(LIMIT));
            }
            self.skip_whitespace();
            if self.bytes().get(self.index) != Some(&b'"') {
                return Err(error(SYNTAX));
            }
            let key = self.parse_string()?;
            self.skip_whitespace();
            if !self.take(b':') {
                return Err(error(SYNTAX));
            }
            let value = self.parse_value(depth)?;
            pairs.push((key, value));
            self.skip_whitespace();
            if self.take(b'}') {
                return Ok(RawValue::Object(pairs));
            }
            if !self.take(b',') {
                return Err(error(SYNTAX));
            }
        }
    }

    fn parse_string(&mut self) -> Result<RawString, ManifestError> {
        self.index += 1;
        let mut codepoints = Vec::new();
        let mut decoded = 0usize;
        while let Some(byte) = self.bytes().get(self.index).copied() {
            if byte == b'"' {
                self.index += 1;
                return Ok(RawString(codepoints));
            }
            if byte == b'\\' {
                self.index += 1;
                let escape = self
                    .bytes()
                    .get(self.index)
                    .copied()
                    .ok_or_else(|| error(SYNTAX))?;
                self.index += 1;
                let codepoint = match escape {
                    b'"' => u32::from(b'"'),
                    b'\\' => u32::from(b'\\'),
                    b'/' => u32::from(b'/'),
                    b'b' => 0x08,
                    b'f' => 0x0c,
                    b'n' => 0x0a,
                    b'r' => 0x0d,
                    b't' => 0x09,
                    b'u' => {
                        let first =
                            hex_quad(self.bytes(), self.index).ok_or_else(|| error(SYNTAX))?;
                        self.index += 4;
                        if (0xd800..=0xdbff).contains(&first)
                            && self.bytes().get(self.index..self.index + 2) == Some(&b"\\u"[..])
                        {
                            if let Some(low) = hex_quad(self.bytes(), self.index + 2) {
                                if (0xdc00..=0xdfff).contains(&low) {
                                    self.index += 6;
                                    0x10000 + ((first - 0xd800) << 10) + low - 0xdc00
                                } else {
                                    first
                                }
                            } else {
                                first
                            }
                        } else {
                            first
                        }
                    }
                    _ => return Err(error(SYNTAX)),
                };
                checked_decoded_add(&mut decoded, utf8_width(codepoint))?;
                codepoints.push(codepoint);
                continue;
            }
            if byte < 0x20 {
                return Err(error(SYNTAX));
            }
            if byte.is_ascii() {
                checked_decoded_add(&mut decoded, 1)?;
                codepoints.push(u32::from(byte));
                self.index += 1;
                continue;
            }
            let character = self.text[self.index..]
                .chars()
                .next()
                .ok_or_else(|| error(SYNTAX))?;
            checked_decoded_add(&mut decoded, character.len_utf8())?;
            codepoints.push(u32::from(character));
            self.index += character.len_utf8();
        }
        Err(error(SYNTAX))
    }

    fn parse_number(&mut self) -> Result<&'a str, ManifestError> {
        let start = self.index;
        if self.take(b'-') && self.index >= self.bytes().len() {
            return Err(error(SYNTAX));
        }
        match self.bytes().get(self.index).copied() {
            Some(b'0') => {
                self.index += 1;
                if self.bytes().get(self.index).is_some_and(u8::is_ascii_digit) {
                    return Err(error(SYNTAX));
                }
            }
            Some(b'1'..=b'9') => {
                while self.bytes().get(self.index).is_some_and(u8::is_ascii_digit) {
                    self.index += 1;
                }
            }
            _ => return Err(error(SYNTAX)),
        }
        if self.take(b'.') {
            let digit_start = self.index;
            while self.bytes().get(self.index).is_some_and(u8::is_ascii_digit) {
                self.index += 1;
            }
            if self.index == digit_start {
                return Err(error(SYNTAX));
            }
        }
        if matches!(self.bytes().get(self.index), Some(b'e' | b'E')) {
            self.index += 1;
            if matches!(self.bytes().get(self.index), Some(b'+' | b'-')) {
                self.index += 1;
            }
            let digit_start = self.index;
            while self.bytes().get(self.index).is_some_and(u8::is_ascii_digit) {
                self.index += 1;
            }
            if self.index == digit_start {
                return Err(error(SYNTAX));
            }
        }
        Ok(&self.text[start..self.index])
    }
}

fn validate_duplicates(value: &RawValue<'_>) -> Result<(), ManifestError> {
    match value {
        RawValue::Array(items) => {
            for item in items {
                validate_duplicates(item)?;
            }
        }
        RawValue::Object(pairs) => {
            let mut seen = BTreeSet::new();
            for (key, _) in pairs {
                if !seen.insert(key) {
                    return Err(error(DUPLICATE_KEY));
                }
            }
            for (_, item) in pairs {
                validate_duplicates(item)?;
            }
        }
        RawValue::String(_) | RawValue::Bool(_) | RawValue::Number(_) | RawValue::Null => {}
    }
    Ok(())
}

fn validate_supported(value: &RawValue<'_>) -> Result<(), ManifestError> {
    match value {
        RawValue::Null => return Err(error(UNSUPPORTED_TYPE)),
        RawValue::Number(lexeme)
            if lexeme
                .bytes()
                .any(|byte| matches!(byte, b'.' | b'e' | b'E')) =>
        {
            return Err(error(UNSUPPORTED_TYPE));
        }
        RawValue::Array(items) => {
            for item in items {
                validate_supported(item)?;
            }
        }
        RawValue::Object(pairs) => {
            for (_, item) in pairs {
                validate_supported(item)?;
            }
        }
        RawValue::String(_) | RawValue::Bool(_) | RawValue::Number(_) => {}
    }
    Ok(())
}

fn validate_integer_range(value: &RawValue<'_>) -> Result<(), ManifestError> {
    match value {
        RawValue::Number(lexeme) => {
            let digits = lexeme.strip_prefix('-').unwrap_or(lexeme);
            if lexeme.starts_with('-')
                || digits.len() > MAX_U64_TEXT.len()
                || (digits.len() == MAX_U64_TEXT.len() && digits > MAX_U64_TEXT)
            {
                return Err(error(INTEGER_RANGE));
            }
        }
        RawValue::Array(items) => {
            for item in items {
                validate_integer_range(item)?;
            }
        }
        RawValue::Object(pairs) => {
            for (_, item) in pairs {
                validate_integer_range(item)?;
            }
        }
        RawValue::String(_) | RawValue::Bool(_) | RawValue::Null => {}
    }
    Ok(())
}

fn validate_keys(value: &RawValue<'_>) -> Result<(), ManifestError> {
    match value {
        RawValue::Array(items) => {
            for item in items {
                validate_keys(item)?;
            }
        }
        RawValue::Object(pairs) => {
            if pairs
                .iter()
                .any(|(key, _)| key.0.iter().any(|codepoint| *codepoint > 0x7f))
            {
                return Err(error(INVALID_KEY));
            }
            for (_, item) in pairs {
                validate_keys(item)?;
            }
        }
        RawValue::String(_) | RawValue::Bool(_) | RawValue::Number(_) | RawValue::Null => {}
    }
    Ok(())
}

fn has_surrogate(value: &RawString) -> bool {
    value
        .0
        .iter()
        .any(|codepoint| (0xd800..=0xdfff).contains(codepoint))
}

fn validate_unicode(value: &RawValue<'_>) -> Result<(), ManifestError> {
    match value {
        RawValue::String(text) if has_surrogate(text) => return Err(error(INVALID_UNICODE)),
        RawValue::Array(items) => {
            for item in items {
                validate_unicode(item)?;
            }
        }
        RawValue::Object(pairs) => {
            if pairs.iter().any(|(key, _)| has_surrogate(key)) {
                return Err(error(INVALID_UNICODE));
            }
            for (_, item) in pairs {
                validate_unicode(item)?;
            }
        }
        RawValue::String(_) | RawValue::Bool(_) | RawValue::Number(_) | RawValue::Null => {}
    }
    Ok(())
}

fn plain_string(value: RawString) -> Result<String, ManifestError> {
    let mut result = String::with_capacity(value.0.len());
    for codepoint in value.0 {
        let character = char::from_u32(codepoint).ok_or_else(|| error(INVALID_UNICODE))?;
        result.push(character);
    }
    Ok(result)
}

fn to_public(value: RawValue<'_>) -> Result<ManifestValue, ManifestError> {
    match value {
        RawValue::String(text) => plain_string(text).map(ManifestValue::String),
        RawValue::Bool(value) => Ok(ManifestValue::Bool(value)),
        RawValue::Number(lexeme) => lexeme
            .parse::<u64>()
            .map(ManifestValue::Integer)
            .map_err(|_| error(INTEGER_RANGE)),
        RawValue::Array(items) => {
            let mut result = Vec::with_capacity(items.len());
            for item in items {
                result.push(to_public(item)?);
            }
            Ok(ManifestValue::Array(result))
        }
        RawValue::Object(pairs) => {
            let mut result = BTreeMap::new();
            for (key, item) in pairs {
                result.insert(plain_string(key)?, to_public(item)?);
            }
            Ok(ManifestValue::Object(result))
        }
        RawValue::Null => Err(error(UNSUPPORTED_TYPE)),
    }
}

struct PublicLimitPreflight {
    nodes: usize,
    output_bytes: usize,
}

impl PublicLimitPreflight {
    fn new() -> Self {
        Self {
            nodes: 0,
            output_bytes: 0,
        }
    }

    fn add_output(&mut self, count: usize) -> Result<(), ManifestError> {
        if count > MAX_INPUT.saturating_sub(self.output_bytes) {
            return Err(error(LIMIT));
        }
        self.output_bytes += count;
        Ok(())
    }

    fn check_string(&mut self, text: &str) -> Result<(), ManifestError> {
        if text.len() > MAX_STRING_BYTES {
            return Err(error(LIMIT));
        }
        self.add_output(1)?;
        for character in text.chars() {
            let width = match character {
                '"' | '\\' | '\u{08}' | '\t' | '\n' | '\u{0c}' | '\r' => 2,
                '\u{00}'..='\u{1f}' => 6,
                _ => character.len_utf8(),
            };
            self.add_output(width)?;
        }
        self.add_output(1)
    }

    fn check_value(&mut self, value: &ManifestValue, depth: usize) -> Result<(), ManifestError> {
        bump_count(&mut self.nodes, MAX_NODES)?;
        match value {
            ManifestValue::String(text) => self.check_string(text),
            ManifestValue::Bool(true) => self.add_output(4),
            ManifestValue::Bool(false) => self.add_output(5),
            ManifestValue::Integer(number) => self.add_output(number.to_string().len()),
            ManifestValue::Array(items) => {
                let next_depth = depth.checked_add(1).ok_or_else(|| error(LIMIT))?;
                if next_depth > MAX_DEPTH || items.len() > MAX_COLLECTION {
                    return Err(error(LIMIT));
                }
                self.add_output(1)?;
                for (index, item) in items.iter().enumerate() {
                    if index != 0 {
                        self.add_output(1)?;
                    }
                    self.check_value(item, next_depth)?;
                }
                self.add_output(1)
            }
            ManifestValue::Object(items) => {
                let next_depth = depth.checked_add(1).ok_or_else(|| error(LIMIT))?;
                if next_depth > MAX_DEPTH || items.len() > MAX_COLLECTION {
                    return Err(error(LIMIT));
                }
                self.add_output(1)?;
                for (index, (key, item)) in items.iter().enumerate() {
                    if index != 0 {
                        self.add_output(1)?;
                    }
                    self.check_string(key)?;
                    self.add_output(1)?;
                    self.check_value(item, next_depth)?;
                }
                self.add_output(1)
            }
        }
    }
}

fn validate_public_keys(value: &ManifestValue) -> Result<(), ManifestError> {
    match value {
        ManifestValue::Array(items) => {
            for item in items {
                validate_public_keys(item)?;
            }
        }
        ManifestValue::Object(items) => {
            if items.keys().any(|key| !key.is_ascii()) {
                return Err(error(INVALID_KEY));
            }
            for item in items.values() {
                validate_public_keys(item)?;
            }
        }
        ManifestValue::String(_) | ManifestValue::Bool(_) | ManifestValue::Integer(_) => {}
    }
    Ok(())
}

struct Encoder {
    data: Vec<u8>,
    nodes: usize,
}

impl Encoder {
    fn new(capacity: usize) -> Self {
        Self {
            data: Vec::with_capacity(capacity),
            nodes: 0,
        }
    }

    fn encode(mut self, value: &ManifestValue) -> Result<Vec<u8>, ManifestError> {
        self.write_value(value, 0)?;
        self.add(b"\n")?;
        Ok(self.data)
    }

    fn add(&mut self, bytes: &[u8]) -> Result<(), ManifestError> {
        if bytes.len() > MAX_INPUT.saturating_sub(self.data.len()) {
            return Err(error(LIMIT));
        }
        self.data.extend_from_slice(bytes);
        Ok(())
    }

    fn write_value(&mut self, value: &ManifestValue, depth: usize) -> Result<(), ManifestError> {
        bump_count(&mut self.nodes, MAX_NODES)?;
        match value {
            ManifestValue::String(text) => self.write_string(text),
            ManifestValue::Bool(true) => self.add(b"true"),
            ManifestValue::Bool(false) => self.add(b"false"),
            ManifestValue::Integer(number) => self.add(number.to_string().as_bytes()),
            ManifestValue::Array(items) => {
                let next_depth = depth.checked_add(1).ok_or_else(|| error(LIMIT))?;
                if next_depth > MAX_DEPTH || items.len() > MAX_COLLECTION {
                    return Err(error(LIMIT));
                }
                self.add(b"[")?;
                for (index, item) in items.iter().enumerate() {
                    if index != 0 {
                        self.add(b",")?;
                    }
                    self.write_value(item, next_depth)?;
                }
                self.add(b"]")
            }
            ManifestValue::Object(items) => {
                let next_depth = depth.checked_add(1).ok_or_else(|| error(LIMIT))?;
                if next_depth > MAX_DEPTH || items.len() > MAX_COLLECTION {
                    return Err(error(LIMIT));
                }
                for key in items.keys() {
                    if key.len() > MAX_STRING_BYTES {
                        return Err(error(LIMIT));
                    }
                    if !key.is_ascii() {
                        return Err(error(INVALID_KEY));
                    }
                }
                self.add(b"{")?;
                for (index, (key, item)) in items.iter().enumerate() {
                    if index != 0 {
                        self.add(b",")?;
                    }
                    self.write_string(key)?;
                    self.add(b":")?;
                    self.write_value(item, next_depth)?;
                }
                self.add(b"}")
            }
        }
    }

    fn write_string(&mut self, text: &str) -> Result<(), ManifestError> {
        if text.len() > MAX_STRING_BYTES {
            return Err(error(LIMIT));
        }
        self.add(b"\"")?;
        const HEX: &[u8; 16] = b"0123456789abcdef";
        for character in text.chars() {
            match character {
                '"' => self.add(b"\\\"")?,
                '\\' => self.add(b"\\\\")?,
                '\u{08}' => self.add(b"\\b")?,
                '\t' => self.add(b"\\t")?,
                '\n' => self.add(b"\\n")?,
                '\u{0c}' => self.add(b"\\f")?,
                '\r' => self.add(b"\\r")?,
                '\u{00}'..='\u{1f}' => {
                    let codepoint = character as usize;
                    let escaped = [
                        b'\\',
                        b'u',
                        b'0',
                        b'0',
                        HEX[codepoint >> 4],
                        HEX[codepoint & 0x0f],
                    ];
                    self.add(&escaped)?;
                }
                _ => {
                    let mut encoded = [0; 4];
                    self.add(character.encode_utf8(&mut encoded).as_bytes())?;
                }
            }
        }
        self.add(b"\"")
    }
}

pub fn decode_canonical_manifest(raw: &[u8]) -> Result<ManifestValue, ManifestError> {
    if raw.len() > MAX_INPUT {
        return Err(error(LIMIT));
    }
    scan_structural_limits(raw)?;
    let text = std::str::from_utf8(raw).map_err(|_| error(UTF8))?;
    if raw.starts_with(b"\xef\xbb\xbf") {
        return Err(error(UTF8));
    }
    let parsed = Parser::new(text).parse()?;
    validate_duplicates(&parsed)?;
    validate_supported(&parsed)?;
    validate_integer_range(&parsed)?;
    validate_keys(&parsed)?;
    validate_unicode(&parsed)?;
    let value = to_public(parsed)?;
    if encode_canonical_value(&value)? != raw {
        return Err(error(NONCANONICAL));
    }
    Ok(value)
}

pub fn encode_canonical_value(value: &ManifestValue) -> Result<Vec<u8>, ManifestError> {
    let mut preflight = PublicLimitPreflight::new();
    preflight.check_value(value, 0)?;
    preflight.add_output(1)?;
    validate_public_keys(value)?;
    Encoder::new(preflight.output_bytes).encode(value)
}

pub fn canonical_manifest_hash(raw: &[u8]) -> Result<String, ManifestError> {
    decode_canonical_manifest(raw)?;
    let preimage = scalar_preimage(MANIFEST, raw).map_err(|_| error(LIMIT))?;
    Ok(sha256_hex(&preimage))
}

#[cfg(test)]
mod tests {
    use super::{
        ManifestError, ManifestValue, canonical_manifest_hash, decode_canonical_manifest,
        encode_canonical_value,
    };
    use std::collections::BTreeMap;

    const MAX_INPUT: usize = 1 << 24;
    const MAX_DEPTH: usize = 64;
    const MAX_COLLECTION: usize = 65_535;
    const MAX_NODES: usize = 1_000_000;

    fn assert_code(expected: &str, raw: &[u8]) {
        let actual = decode_canonical_manifest(raw).unwrap_err();
        assert_eq!(expected, actual.code());
    }

    fn assert_round_trip(raw: &[u8]) {
        let value = decode_canonical_manifest(raw).unwrap();
        assert_eq!(raw, encode_canonical_value(&value).unwrap());
    }

    fn node_document(extra: usize, first: &[u8]) -> Vec<u8> {
        let mut raw = Vec::new();
        raw.push(b'{');
        for group in 0..27 {
            if group != 0 {
                raw.push(b',');
            }
            raw.extend_from_slice(format!("\"g{group:02}\":[").as_bytes());
            let width = 37_036 + usize::from(group == 26) * extra;
            for index in 0..width {
                if index != 0 {
                    raw.push(b',');
                }
                raw.extend_from_slice(if group == 0 && index == 0 {
                    first
                } else {
                    b"0"
                });
            }
            raw.push(b']');
        }
        raw.extend_from_slice(b"}\n");
        raw
    }

    #[test]
    fn canonical_documents_round_trip() {
        for raw in [
            &b"{}\n"[..],
            &b"{\"a\":2,\"b\":1}\n"[..],
            &b"{\"a\":\"\\n\",\"u\":\"\xc3\xa9\"}\n"[..],
            &b"{\"x\":[true,false,0,18446744073709551615]}\n"[..],
            &b"{\"a\":\"\\b\\t\\n\\f\\r\\u0000\\\"\\\\/\"}\n"[..],
            &b"{\"\\u0000\":true,\"A\":false}\n"[..],
            &b"\"\xf0\x9f\x98\x80\"\n"[..],
        ] {
            assert_round_trip(raw);
        }
    }

    #[test]
    fn public_values_encode_without_a_second_data_model() {
        let value = ManifestValue::Object(BTreeMap::from([
            (
                "z".to_owned(),
                ManifestValue::Array(vec![
                    ManifestValue::Bool(true),
                    ManifestValue::Integer(u64::MAX),
                ]),
            ),
            ("a".to_owned(), ManifestValue::String("é".to_owned())),
        ]));
        assert_eq!(
            b"{\"a\":\"\xc3\xa9\",\"z\":[true,18446744073709551615]}\n",
            encode_canonical_value(&value).unwrap().as_slice(),
        );

        let invalid_key = ManifestValue::Object(BTreeMap::from([(
            "é".to_owned(),
            ManifestValue::Bool(false),
        )]));
        assert_eq!(
            "manifest.invalid_key",
            encode_canonical_value(&invalid_key).unwrap_err().code(),
        );

        let limit_before_key = ManifestValue::Object(BTreeMap::from([(
            "é".to_owned(),
            ManifestValue::String("a".repeat(MAX_INPUT)),
        )]));
        assert_eq!(
            "manifest.limit",
            encode_canonical_value(&limit_before_key)
                .unwrap_err()
                .code(),
        );
    }

    #[test]
    fn noncanonical_and_trailing_forms_are_distinct() {
        for raw in [
            &b"{\"b\":1,\"a\":2}\n"[..],
            &b"{ \"a\":1}\n"[..],
            &b"{\"a\":\"\\u0061\"}\n"[..],
            &b"{\"a\":\"\\/\"}\n"[..],
            &b"{\"a\":\"\\u000A\"}\n"[..],
            &b"{}"[..],
            &b"\n{}\n"[..],
            &b"{} \n"[..],
            &b"{\"u\":\"\\ud83d\\ude00\"}\n"[..],
        ] {
            assert_code("manifest.noncanonical", raw);
        }
        for raw in [&b"{}\n\n"[..], &b"{}\nX"[..], &b"{\"a\":0,\"a\":1}\nX"[..]] {
            assert_code("manifest.trailing_data", raw);
        }
    }

    #[test]
    fn every_stable_diagnostic_is_observable() {
        let cases: [(&str, &[u8]); 18] = [
            ("manifest.utf8", b"\xff"),
            ("manifest.utf8", b"\xef\xbb\xbf{}\n"),
            ("manifest.syntax", b"{]\n"),
            ("manifest.syntax", b"[1,]\n"),
            ("manifest.syntax", b"{\"a\":\"\\uZZZZ\"}\n"),
            ("manifest.duplicate_key", b"{\"a\":0,\"a\":1}\n"),
            ("manifest.duplicate_key", b"{\"a\":0,\"\\u0061\":1}\n"),
            ("manifest.unsupported_type", b"null\n"),
            ("manifest.unsupported_type", b"1.0\n"),
            ("manifest.unsupported_type", b"1e0\n"),
            ("manifest.integer_range", b"-0\n"),
            ("manifest.integer_range", b"-1\n"),
            ("manifest.integer_range", b"18446744073709551616\n"),
            ("manifest.invalid_key", b"{\"\xc3\xa9\":0}\n"),
            ("manifest.invalid_key", b"{\"\\u00e9\":0}\n"),
            ("manifest.invalid_key", b"{\"\\ud800\":0}\n"),
            ("manifest.invalid_unicode", b"{\"a\":\"\\ud800\"}\n"),
            ("manifest.invalid_unicode", b"{\"a\":\"\\udc00\"}\n"),
        ];
        for (expected, raw) in cases {
            assert_code(expected, raw);
        }
        assert_code("manifest.syntax", b"\x0b{}\n");
        assert_code("manifest.syntax", b"[\x0c0]\n");
        assert_code("manifest.trailing_data", b"{}\x0c\n");
    }

    #[test]
    fn diagnostic_precedence_is_global() {
        let mut over_input = vec![b' '; MAX_INPUT + 1];
        over_input[0] = 0xff;
        assert_code("manifest.limit", &over_input);
        assert_code(
            "manifest.limit",
            format!("{{]{}", "[".repeat(MAX_DEPTH + 1)).as_bytes(),
        );
        let over_collection = format!("[{}null]\n", ",".repeat(MAX_COLLECTION));
        assert_code("manifest.limit", over_collection.as_bytes());
        assert_code("manifest.limit", &node_document(1, b"null"));
        assert_code("manifest.trailing_data", b"{\"a\":null,\"a\":1}\nX");
        assert_code(
            "manifest.duplicate_key",
            b"{\"a\":null,\"a\":18446744073709551616}\n",
        );
        assert_code(
            "manifest.unsupported_type",
            b"[null,18446744073709551616]\n",
        );
        assert_code("manifest.trailing_data", b"{\"a\":\"\\ud800\"}\nX");
        assert_code("manifest.duplicate_key", b"{\"a\":\"\\ud800\",\"a\":0}\n");
        assert_code("manifest.unsupported_type", b"[\"\\ud800\",null]\n");
        assert_code(
            "manifest.integer_range",
            b"[\"\\ud800\",18446744073709551616]\n",
        );
        assert_code("manifest.invalid_key", b"{\"\xc3\xa9\":\"\\ud800\"}\n");
        assert_code(
            "manifest.integer_range",
            format!("{}\n", "9".repeat(5000)).as_bytes(),
        );
        assert_code("manifest.syntax", "[1١]\n".as_bytes());
    }

    #[test]
    fn structural_limits_honor_boundary_and_ignore_string_punctuation() {
        assert_round_trip(b"{\"brackets\":\"[[[,,,{{{\"}\n");
        let at_depth = format!("{}0{}\n", "[".repeat(MAX_DEPTH), "]".repeat(MAX_DEPTH));
        assert_round_trip(at_depth.as_bytes());
        let over_depth = format!(
            "{}0{}\n",
            "[".repeat(MAX_DEPTH + 1),
            "]".repeat(MAX_DEPTH + 1)
        );
        assert_code("manifest.limit", over_depth.as_bytes());

        let at_collection = format!("[{}]\n", vec!["0"; MAX_COLLECTION].join(","));
        assert_round_trip(at_collection.as_bytes());
        let over_collection = format!("[{}]\n", vec!["0"; MAX_COLLECTION + 1].join(","));
        assert_code("manifest.limit", over_collection.as_bytes());

        let at_nodes = node_document(0, b"0");
        assert_eq!(MAX_NODES, 1 + 27 + 27 * 37_036);
        assert_round_trip(&at_nodes);
        assert_code("manifest.limit", &node_document(1, b"0"));
    }

    #[test]
    fn input_boundary_and_hash_are_exact() {
        let mut at = Vec::with_capacity(MAX_INPUT);
        at.push(b'"');
        at.extend(std::iter::repeat_n(b'a', MAX_INPUT - 3));
        at.extend_from_slice(b"\"\n");
        assert_eq!(MAX_INPUT, at.len());
        assert_round_trip(&at);

        let mut over = at.clone();
        over.insert(over.len() - 2, b'a');
        assert_code("manifest.limit", &over);
        assert_eq!(
            "836b1e2073681781d86862b6135f26e66db2c15cc73080d01815930aefbc4a4a",
            canonical_manifest_hash(b"{}\n").unwrap(),
        );
    }

    #[test]
    fn errors_are_stable_values() {
        let error: ManifestError = decode_canonical_manifest(b"null\n").unwrap_err();
        assert_eq!("manifest.unsupported_type", error.code());
        assert_eq!(error.code(), error.to_string());
    }
}
