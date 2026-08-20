use std::collections::{BTreeMap, BTreeSet};

use gb_foundation::constants::*;
use gb_foundation::{
    MAX_MANIFEST_BYTES, ManifestValue, identity_hex, parse_manifest, serialize_manifest,
};
use sha2::{Digest, Sha256};

use crate::{
    BoardTerminal, LocallyAdmissiblePosition, Move, Score, Side, apply_move, board_terminal,
    decode_move, destination, encode_move, encode_position, file, king_in_check, legal_moves,
    origin, piece_kind, promotion, rank, replay_from_start, validate_source_record,
};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SourceReject {
    pub code: u16,
    pub raw_start: u32,
    pub raw_end: u32,
}

type Result<T> = std::result::Result<T, SourceReject>;

fn reject(code: u16, raw_start: usize, raw_end: usize) -> SourceReject {
    SourceReject {
        code,
        raw_start: raw_start as u32,
        raw_end: raw_end as u32,
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct GameRecord {
    moves: Vec<Move>,
    score: Score,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SourceCandidate {
    compiled: Vec<CompiledGame>,
    game_set: Vec<u8>,
}

#[derive(Clone, Copy, Debug)]
pub struct EvidenceInputs<'a> {
    pub source: &'a [u8],
    pub chess_v0: &'a [u8],
    pub source_v0: &'a [u8],
    pub identity_v0: &'a [u8],
    pub constants_v0: &'a [u8],
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ValidatedCandidate {
    candidate_bytes: Vec<u8>,
    game_set_bytes: Vec<u8>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RetainedEvidence {
    report_bytes: Vec<u8>,
    game_set_bytes: Vec<u8>,
}

impl RetainedEvidence {
    pub fn report_bytes(&self) -> &[u8] {
        &self.report_bytes
    }

    pub fn game_set_bytes(&self) -> &[u8] {
        &self.game_set_bytes
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Span {
    start: usize,
    end: usize,
}

#[derive(Clone, Copy, Debug)]
struct Line {
    span: Span,
    next: usize,
}

#[derive(Clone, Copy, Debug)]
struct Block {
    opener: Span,
    content: Span,
}

#[derive(Clone, Copy, Debug)]
struct ParsedBlock {
    block: Block,
    separator: Option<Line>,
    result: Score,
}

#[derive(Clone, Copy, Debug)]
struct Token {
    span: Span,
}

#[derive(Clone, Debug)]
struct FramedBlock {
    block: Block,
    result: Score,
    tokens: Vec<Token>,
    movetext_end: usize,
}

#[derive(Clone, Debug)]
struct StructuredBlock {
    block: Block,
    result: Score,
    semantic: Vec<SemanticToken>,
    marker: Span,
}

#[derive(Clone, Copy, Debug)]
struct SemanticToken {
    token: Token,
    san: bool,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct TraceRow {
    raw_span: Span,
    move_bytes: [u8; 2],
    post_position_bytes: [u8; 67],
    suffix_truth_code: u8,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct CompiledGame {
    source_ordinal: usize,
    opener_span: Span,
    rows: Vec<TraceRow>,
    record: GameRecord,
}

impl SourceCandidate {
    pub fn game_count(&self) -> usize {
        self.compiled.len()
    }

    pub fn ply_count(&self) -> usize {
        self.compiled.iter().map(|game| game.rows.len()).sum()
    }

    pub fn game_set_bytes(&self) -> &[u8] {
        &self.game_set
    }
}

pub fn compile_source(raw: &[u8]) -> Result<SourceCandidate> {
    if raw.len() > SOURCE_MAX_INPUT_BYTES as usize {
        let start = SOURCE_MAX_INPUT_BYTES as usize;
        return Err(reject(SOURCE_INPUT_TOO_LARGE, start, start + 1));
    }
    validate_byte_profile(raw)?;
    let lines = physical_lines(raw);
    let blocks = scan_fences(raw, &lines)?;
    let parsed = scan_tags(raw, &lines, &blocks)?;
    let framed = frame_blocks(raw, &lines, &parsed)?;
    let structured = structure_blocks(raw, &framed)?;
    compile_games(raw, &structured)
}

fn choose(best: &mut Option<SourceReject>, candidate: SourceReject) {
    if best.is_none_or(|current| {
        (candidate.raw_start, candidate.code) < (current.raw_start, current.code)
    }) {
        *best = Some(candidate);
    }
}

fn utf8_reject(raw: &[u8]) -> Option<SourceReject> {
    let mut at = 0usize;
    while at < raw.len() {
        let byte = raw[at];
        let (width, second_min, second_max) = match byte {
            0x00..=0x7f => {
                at += 1;
                continue;
            }
            0xc2..=0xdf => (2, 0x80, 0xbf),
            0xe0 => (3, 0xa0, 0xbf),
            0xe1..=0xec | 0xee..=0xef => (3, 0x80, 0xbf),
            0xed => (3, 0x80, 0x9f),
            0xf0 => (4, 0x90, 0xbf),
            0xf1..=0xf3 => (4, 0x80, 0xbf),
            0xf4 => (4, 0x80, 0x8f),
            _ => return Some(reject(SOURCE_UTF8_INVALID, at, at + 1)),
        };
        if raw.len() - at < width {
            return Some(reject(SOURCE_UTF8_INVALID, at, raw.len()));
        }
        if !(second_min..=second_max).contains(&raw[at + 1])
            || raw[at + 2..at + width]
                .iter()
                .any(|byte| !(0x80..=0xbf).contains(byte))
        {
            return Some(reject(SOURCE_UTF8_INVALID, at, at + 1));
        }
        at += width;
    }
    None
}

fn validate_byte_profile(raw: &[u8]) -> Result<()> {
    let mut best = None;
    if raw.starts_with(&[0xef, 0xbb, 0xbf]) {
        choose(&mut best, reject(SOURCE_UTF8_BOM, 0, 3));
    }
    if let Some(error) = utf8_reject(raw) {
        choose(&mut best, error);
    }
    for (at, &byte) in raw.iter().enumerate() {
        if (byte < 0x20 && !matches!(byte, b'\t' | b'\n' | b'\r')) || byte == 0x7f {
            choose(&mut best, reject(SOURCE_CONTROL, at, at + 1));
        }
    }

    let mut newline_kind = None;
    let mut at = 0usize;
    while at < raw.len() {
        match raw[at] {
            b'\r' if raw.get(at + 1) == Some(&b'\n') => {
                if newline_kind == Some(false) {
                    choose(&mut best, reject(SOURCE_NEWLINE_MIXED, at, at + 2));
                }
                newline_kind.get_or_insert(true);
                at += 2;
            }
            b'\r' => {
                choose(&mut best, reject(SOURCE_NEWLINE_BARE_CR, at, at + 1));
                at += 1;
            }
            b'\n' => {
                if newline_kind == Some(true) {
                    choose(&mut best, reject(SOURCE_NEWLINE_MIXED, at, at + 1));
                }
                newline_kind.get_or_insert(false);
                at += 1;
            }
            _ => at += 1,
        }
    }
    if raw.last() != Some(&b'\n') {
        choose(
            &mut best,
            reject(SOURCE_NEWLINE_FINAL_MISSING, raw.len(), raw.len()),
        );
    }
    if let Some(error) = best {
        return Err(error);
    }
    Ok(())
}

fn physical_lines(raw: &[u8]) -> Vec<Line> {
    let mut lines = Vec::new();
    let mut start = 0usize;
    while start < raw.len() {
        let lf = raw[start..]
            .iter()
            .position(|&byte| byte == b'\n')
            .map(|offset| start + offset)
            .expect("the byte profile requires a final newline");
        let end = if lf > start && raw[lf - 1] == b'\r' {
            lf - 1
        } else {
            lf
        };
        lines.push(Line {
            span: Span { start, end },
            next: lf + 1,
        });
        start = lf + 1;
    }
    lines
}

fn hws(bytes: &[u8]) -> bool {
    bytes.iter().all(|byte| matches!(byte, b' ' | b'\t'))
}

fn scan_fences(raw: &[u8], lines: &[Line]) -> Result<Vec<Block>> {
    let mut best = None;
    let mut open: Option<Line> = None;
    let mut blocks = Vec::new();
    let mut pair_count = 0usize;
    for &line in lines {
        let bytes = &raw[line.span.start..line.span.end];
        let opener = bytes.starts_with(b"```pgn") && hws(&bytes[6..]);
        let closer = bytes.starts_with(b"```") && hws(&bytes[3..]);
        let leading = bytes
            .iter()
            .take_while(|&&byte| matches!(byte, b' ' | b'\t'))
            .count();
        let bad_shape = (bytes.starts_with(b"```") && !opener && !closer)
            || (leading > 0 && bytes[leading..].starts_with(b"```"));
        if bad_shape {
            choose(
                &mut best,
                reject(SOURCE_FENCE_SHAPE, line.span.start, line.span.end),
            );
            continue;
        }
        match (open, opener, closer) {
            (None, true, _) => open = Some(line),
            (None, _, true) => choose(
                &mut best,
                reject(SOURCE_FENCE_ORPHAN_CLOSE, line.span.start, line.span.end),
            ),
            (Some(_), true, _) => choose(
                &mut best,
                reject(SOURCE_FENCE_NESTED_OPEN, line.span.start, line.span.end),
            ),
            (Some(opener_line), _, true) => {
                pair_count += 1;
                if line.next - opener_line.span.start > SOURCE_MAX_FENCE_BYTES as usize {
                    let start = opener_line.span.start + SOURCE_MAX_FENCE_BYTES as usize;
                    choose(
                        &mut best,
                        reject(SOURCE_FENCE_BLOCK_BYTES, start, start + 1),
                    );
                }
                if pair_count <= SOURCE_ANTHOLOGY_GAME_COUNT as usize {
                    blocks.push(Block {
                        opener: opener_line.span,
                        content: Span {
                            start: opener_line.next,
                            end: line.span.start,
                        },
                    });
                } else if pair_count == SOURCE_ANTHOLOGY_GAME_COUNT as usize + 1 {
                    choose(
                        &mut best,
                        reject(
                            SOURCE_FENCE_COUNT,
                            opener_line.span.start,
                            opener_line.span.end,
                        ),
                    );
                }
                open = None;
            }
            _ => {}
        }
    }
    if let Some(opener) = open {
        if raw.len() - opener.span.start > SOURCE_MAX_FENCE_BYTES as usize {
            let start = opener.span.start + SOURCE_MAX_FENCE_BYTES as usize;
            choose(
                &mut best,
                reject(SOURCE_FENCE_BLOCK_BYTES, start, start + 1),
            );
        } else {
            choose(
                &mut best,
                reject(SOURCE_FENCE_UNCLOSED, raw.len(), raw.len()),
            );
        }
    }
    if pair_count < SOURCE_ANTHOLOGY_GAME_COUNT as usize {
        choose(&mut best, reject(SOURCE_FENCE_COUNT, raw.len(), raw.len()));
    }
    if let Some(error) = best {
        return Err(error);
    }
    Ok(blocks)
}

struct Tag<'a> {
    name: &'a [u8],
    name_span: Span,
    value: Vec<u8>,
    value_span: Span,
}

fn parse_tag<'a>(raw: &'a [u8], line: Line) -> std::result::Result<Tag<'a>, SourceReject> {
    let bytes = &raw[line.span.start..line.span.end];
    let syntax = || reject(SOURCE_TAG_SYNTAX, line.span.start, line.span.end);
    if bytes.first() != Some(&b'[') {
        return Err(syntax());
    }
    let mut at = 1usize;
    if !bytes.get(at).is_some_and(|byte| byte.is_ascii_alphabetic()) {
        return Err(syntax());
    }
    let name_start = at;
    at += 1;
    while bytes
        .get(at)
        .is_some_and(|byte| byte.is_ascii_alphanumeric() || *byte == b'_')
    {
        at += 1;
    }
    let name_end = at;
    if name_end - name_start > SOURCE_MAX_TAG_NAME_BYTES as usize {
        let start = line.span.start + name_start + SOURCE_MAX_TAG_NAME_BYTES as usize;
        return Err(reject(SOURCE_TAG_NAME_LENGTH, start, start + 1));
    }
    if bytes.get(at..at + 2) != Some(&b" \""[..]) {
        return Err(syntax());
    }
    at += 2;
    let value_start = at;
    if !bytes.ends_with(b"\"]") {
        return Err(syntax());
    }
    let value_end = bytes.len() - 2;
    if value_end - value_start > SOURCE_MAX_TAG_VALUE_BYTES as usize {
        let start = line.span.start + value_start + SOURCE_MAX_TAG_VALUE_BYTES as usize;
        return Err(reject(SOURCE_TAG_VALUE_LENGTH, start, start + 1));
    }
    let mut value = Vec::new();
    while at < value_end {
        match bytes[at] {
            b'"' => return Err(syntax()),
            b'\\' => {
                let escape_start = at;
                at += 1;
                let Some(&escaped) = bytes.get(at).filter(|_| at < value_end) else {
                    return Err(reject(
                        SOURCE_TAG_ESCAPE,
                        line.span.start + escape_start,
                        line.span.start + escape_start + 1,
                    ));
                };
                if !matches!(escaped, b'"' | b'\\') {
                    return Err(reject(
                        SOURCE_TAG_ESCAPE,
                        line.span.start + escape_start,
                        line.span.start + at + 1,
                    ));
                }
                value.push(escaped);
                at += 1;
            }
            byte => {
                value.push(byte);
                at += 1;
            }
        }
    }
    Ok(Tag {
        name: &bytes[name_start..name_end],
        name_span: Span {
            start: line.span.start + name_start,
            end: line.span.start + name_end,
        },
        value,
        value_span: Span {
            start: line.span.start + value_start,
            end: line.span.start + value_end,
        },
    })
}

fn scan_tags(raw: &[u8], lines: &[Line], blocks: &[Block]) -> Result<Vec<ParsedBlock>> {
    let mut best = None;
    let mut parsed = Vec::with_capacity(blocks.len());
    for &block in blocks {
        let content: Vec<Line> = lines
            .iter()
            .copied()
            .filter(|line| {
                line.span.start >= block.content.start && line.span.start < block.content.end
            })
            .collect();
        if content.is_empty() {
            choose(
                &mut best,
                reject(SOURCE_TAG_SYNTAX, block.content.start, block.content.start),
            );
            continue;
        }
        if raw[content[0].span.start..content[0].span.end].first() != Some(&b'[') {
            let span = if content[0].span.start == content[0].span.end {
                Span {
                    start: block.content.start,
                    end: block.content.start,
                }
            } else {
                content[0].span
            };
            choose(&mut best, reject(SOURCE_TAG_SYNTAX, span.start, span.end));
            continue;
        }

        let mut names = BTreeSet::new();
        let mut result = None;
        let mut separator = None;
        let mut failed = false;
        for (index, &line) in content.iter().enumerate() {
            let bytes = &raw[line.span.start..line.span.end];
            if bytes.first() != Some(&b'[') {
                separator = Some(line);
                break;
            }
            if index >= SOURCE_MAX_TAG_LINES as usize {
                choose(
                    &mut best,
                    reject(SOURCE_TAG_COUNT, line.span.start, line.span.end),
                );
                failed = true;
                break;
            }
            let tag = match parse_tag(raw, line) {
                Ok(tag) => tag,
                Err(error) => {
                    choose(&mut best, error);
                    failed = true;
                    break;
                }
            };
            if !names.insert(tag.name.to_vec()) {
                choose(
                    &mut best,
                    reject(SOURCE_TAG_DUPLICATE, tag.name_span.start, tag.name_span.end),
                );
                failed = true;
                break;
            }
            if matches!(tag.name, b"SetUp" | b"FEN" | b"Variant") {
                choose(
                    &mut best,
                    reject(SOURCE_TAG_FORBIDDEN, tag.name_span.start, tag.name_span.end),
                );
                failed = true;
                break;
            }
            if tag.name == b"Result" {
                result = match tag.value.as_slice() {
                    b"1-0" => Some(Score::FirstWin),
                    b"0-1" => Some(Score::SecondWin),
                    b"1/2-1/2" => Some(Score::Draw),
                    _ => {
                        choose(
                            &mut best,
                            reject(
                                SOURCE_TAG_RESULT_VALUE,
                                tag.value_span.start,
                                tag.value_span.end,
                            ),
                        );
                        failed = true;
                        break;
                    }
                };
            }
        }
        if failed {
            continue;
        }
        let required_at = separator.map_or(block.content.end, |line| line.span.start);
        let Some(result) = result else {
            choose(
                &mut best,
                reject(SOURCE_TAG_RESULT_MISSING, required_at, required_at),
            );
            continue;
        };
        parsed.push(ParsedBlock {
            block,
            separator,
            result,
        });
    }
    if let Some(error) = best {
        return Err(error);
    }
    Ok(parsed)
}

fn move_number_shape(token: &[u8]) -> bool {
    token.len() >= 2
        && token.last() == Some(&b'.')
        && token[..token.len() - 1].iter().all(u8::is_ascii_digit)
}

fn result_score(token: &[u8]) -> Option<Score> {
    match token {
        b"1-0" => Some(Score::FirstWin),
        b"0-1" => Some(Score::SecondWin),
        b"1/2-1/2" => Some(Score::Draw),
        _ => None,
    }
}

fn frame_blocks(raw: &[u8], lines: &[Line], blocks: &[ParsedBlock]) -> Result<Vec<FramedBlock>> {
    let mut best = None;
    let mut total_plies = 0usize;
    let mut framed = Vec::with_capacity(blocks.len());
    for &block in blocks {
        let Some(separator) = block.separator else {
            choose(
                &mut best,
                reject(
                    SOURCE_SEPARATOR_MISSING,
                    block.block.content.end,
                    block.block.content.end,
                ),
            );
            continue;
        };
        if separator.span.start != separator.span.end {
            choose(
                &mut best,
                reject(
                    SOURCE_SEPARATOR_MISSING,
                    separator.span.start,
                    separator.span.start,
                ),
            );
            continue;
        }
        let movetext: Vec<Line> = lines
            .iter()
            .copied()
            .filter(|line| {
                line.span.start >= separator.next && line.span.start < block.block.content.end
            })
            .collect();
        let Some(first) = movetext.first() else {
            choose(
                &mut best,
                reject(
                    SOURCE_MOVETEXT_MISSING,
                    block.block.content.end,
                    block.block.content.end,
                ),
            );
            continue;
        };
        if first.span.start == first.span.end {
            choose(
                &mut best,
                reject(SOURCE_SEPARATOR_EXTRA, first.span.start, first.span.end),
            );
            continue;
        }

        let mut tokens = Vec::new();
        let mut potential_plies = 0usize;
        let mut failed = false;
        for line in &movetext {
            let bytes = &raw[line.span.start..line.span.end];
            let error = if bytes.is_empty() {
                Some(SOURCE_MOVETEXT_EMPTY_LINE)
            } else if bytes.first() == Some(&b'[') {
                Some(SOURCE_MOVETEXT_TAG_LINE)
            } else if bytes
                .first()
                .is_some_and(|byte| matches!(byte, b' ' | b'\t'))
            {
                Some(SOURCE_MOVETEXT_LEADING_HWS)
            } else if bytes
                .last()
                .is_some_and(|byte| matches!(byte, b' ' | b'\t'))
            {
                Some(SOURCE_MOVETEXT_TRAILING_HWS)
            } else {
                None
            };
            if let Some(code) = error {
                choose(&mut best, reject(code, line.span.start, line.span.end));
                failed = true;
                break;
            }

            let mut at = line.span.start;
            while at < line.span.end {
                while at < line.span.end && matches!(raw[at], b' ' | b'\t') {
                    at += 1;
                }
                let start = at;
                while at < line.span.end && !matches!(raw[at], b' ' | b'\t') {
                    at += 1;
                }
                if start == at {
                    continue;
                }
                let token = Token {
                    span: Span { start, end: at },
                };
                if tokens.len() == SOURCE_MAX_TOKENS_PER_BLOCK as usize {
                    choose(&mut best, reject(SOURCE_RESOURCE_TOKEN_COUNT, start, at));
                    failed = true;
                    break;
                }
                let bytes = &raw[start..at];
                if !move_number_shape(bytes) && result_score(bytes).is_none() {
                    potential_plies += 1;
                    total_plies += 1;
                    if potential_plies > SOURCE_MAX_PLIES_PER_BLOCK as usize {
                        choose(&mut best, reject(SOURCE_RESOURCE_RECORD_PLIES, start, at));
                        failed = true;
                        break;
                    }
                    if total_plies > SOURCE_MAX_TOTAL_PLIES as usize {
                        choose(&mut best, reject(SOURCE_RESOURCE_TOTAL_PLIES, start, at));
                        failed = true;
                        break;
                    }
                }
                tokens.push(token);
            }
            if failed {
                break;
            }
        }
        if failed {
            continue;
        }
        framed.push(FramedBlock {
            block: block.block,
            result: block.result,
            tokens,
            movetext_end: movetext.last().unwrap().span.end,
        });
    }
    if let Some(error) = best {
        return Err(error);
    }
    Ok(framed)
}

enum StructureState {
    Number { expected: u32, has_san: bool },
    FirstSan { expected: u32 },
    SecondSan { next: u32 },
    Closed,
}

fn structure_blocks(raw: &[u8], blocks: &[FramedBlock]) -> Result<Vec<StructuredBlock>> {
    let mut best = None;
    let mut structured = Vec::with_capacity(blocks.len());
    for block in blocks {
        let mut state = StructureState::Number {
            expected: 1,
            has_san: false,
        };
        let mut semantic = Vec::new();
        let mut marker = None;
        let mut failed = false;
        for &token in &block.tokens {
            let bytes = &raw[token.span.start..token.span.end];
            if bytes == b"*" {
                choose(
                    &mut best,
                    reject(SOURCE_RESULT_TOKEN, token.span.start, token.span.end),
                );
                failed = true;
                break;
            }
            let result = result_score(bytes);
            match state {
                StructureState::Number { expected, has_san } => {
                    if let Some(score) = result {
                        if !has_san {
                            choose(
                                &mut best,
                                reject(SOURCE_RESULT_TOO_EARLY, token.span.start, token.span.end),
                            );
                            failed = true;
                            break;
                        }
                        if score != block.result {
                            choose(
                                &mut best,
                                reject(SOURCE_RESULT_MISMATCH, token.span.start, token.span.end),
                            );
                            failed = true;
                            break;
                        }
                        marker = Some(token.span);
                        state = StructureState::Closed;
                    } else if !move_number_shape(bytes) {
                        choose(
                            &mut best,
                            reject(SOURCE_MOVE_NUMBER_SHAPE, token.span.start, token.span.end),
                        );
                        failed = true;
                        break;
                    } else {
                        let digits = &bytes[..bytes.len() - 1];
                        let value = if digits.first() == Some(&b'0') {
                            None
                        } else {
                            std::str::from_utf8(digits)
                                .ok()
                                .and_then(|value| value.parse::<u32>().ok())
                        };
                        if value != Some(expected) {
                            choose(
                                &mut best,
                                reject(SOURCE_MOVE_NUMBER_VALUE, token.span.start, token.span.end),
                            );
                            failed = true;
                            break;
                        }
                        semantic.push(SemanticToken { token, san: false });
                        state = StructureState::FirstSan { expected };
                    }
                }
                StructureState::FirstSan { expected } => {
                    if result.is_some() {
                        choose(
                            &mut best,
                            reject(SOURCE_RESULT_TOO_EARLY, token.span.start, token.span.end),
                        );
                        failed = true;
                        break;
                    }
                    if move_number_shape(bytes) {
                        choose(
                            &mut best,
                            reject(
                                SOURCE_MOVE_NUMBER_POSITION,
                                token.span.start,
                                token.span.end,
                            ),
                        );
                        failed = true;
                        break;
                    }
                    semantic.push(SemanticToken { token, san: true });
                    state = StructureState::SecondSan { next: expected + 1 };
                }
                StructureState::SecondSan { next } => {
                    if let Some(score) = result {
                        if score != block.result {
                            choose(
                                &mut best,
                                reject(SOURCE_RESULT_MISMATCH, token.span.start, token.span.end),
                            );
                            failed = true;
                            break;
                        }
                        marker = Some(token.span);
                        state = StructureState::Closed;
                    } else if move_number_shape(bytes) {
                        choose(
                            &mut best,
                            reject(
                                SOURCE_MOVE_NUMBER_POSITION,
                                token.span.start,
                                token.span.end,
                            ),
                        );
                        failed = true;
                        break;
                    } else {
                        semantic.push(SemanticToken { token, san: true });
                        state = StructureState::Number {
                            expected: next,
                            has_san: true,
                        };
                    }
                }
                StructureState::Closed => {
                    choose(
                        &mut best,
                        reject(SOURCE_TOKEN_AFTER_RESULT, token.span.start, token.span.end),
                    );
                    failed = true;
                    break;
                }
            }
        }
        if failed {
            continue;
        }
        let Some(marker) = marker else {
            choose(
                &mut best,
                reject(
                    SOURCE_RESULT_MISSING,
                    block.movetext_end,
                    block.movetext_end,
                ),
            );
            continue;
        };
        structured.push(StructuredBlock {
            block: block.block,
            result: block.result,
            semantic,
            marker,
        });
    }
    if let Some(error) = best {
        return Err(error);
    }
    Ok(structured)
}

#[derive(Clone, Copy)]
struct ParsedSan {
    piece: u8,
    castle: Option<bool>,
    from_file: Option<i8>,
    from_rank: Option<i8>,
    capture: bool,
    destination: u8,
    promotion: u8,
    stem_end: usize,
    suffix: Option<u8>,
}

fn san_square(bytes: &[u8]) -> Option<u8> {
    if bytes.len() != 2 || !(b'a'..=b'h').contains(&bytes[0]) || !(b'1'..=b'8').contains(&bytes[1])
    {
        return None;
    }
    Some((bytes[1] - b'1') * 8 + (bytes[0] - b'a'))
}

fn parse_san(token: &[u8]) -> Option<ParsedSan> {
    let (stem, suffix) = match token.last().copied() {
        Some(b'+' | b'#') => (&token[..token.len() - 1], token.last().copied()),
        _ => (token, None),
    };
    if stem.is_empty() || stem.last().is_some_and(|byte| matches!(byte, b'+' | b'#')) {
        return None;
    }
    if matches!(stem, b"O-O" | b"O-O-O") {
        return Some(ParsedSan {
            piece: 6,
            castle: Some(stem == b"O-O"),
            from_file: None,
            from_rank: None,
            capture: false,
            destination: if stem == b"O-O" { 6 } else { 2 },
            promotion: 0,
            stem_end: stem.len(),
            suffix,
        });
    }

    let (without_promotion, promotion_code) = if stem.len() >= 2 && stem[stem.len() - 2] == b'=' {
        let code = match stem[stem.len() - 1] {
            b'Q' => 1,
            b'R' => 2,
            b'B' => 3,
            b'N' => 4,
            _ => return None,
        };
        (&stem[..stem.len() - 2], code)
    } else {
        (stem, 0)
    };
    if without_promotion.len() < 2 {
        return None;
    }
    let destination = san_square(&without_promotion[without_promotion.len() - 2..])?;
    let destination_rank = rank(destination);
    let mut prefix = &without_promotion[..without_promotion.len() - 2];
    let piece = match prefix.first().copied() {
        Some(b'N') => 2,
        Some(b'B') => 3,
        Some(b'R') => 4,
        Some(b'Q') => 5,
        Some(b'K') => 6,
        _ => 1,
    };
    if piece != 1 {
        prefix = &prefix[1..];
    }
    let capture = prefix.last() == Some(&b'x');
    if capture {
        prefix = &prefix[..prefix.len() - 1];
    }
    let (from_file, from_rank) = match (piece, prefix) {
        (1, []) if !capture => (None, None),
        (1, [file @ b'a'..=b'h']) if capture => (Some((file - b'a') as i8), None),
        (1, _) => return None,
        (_, []) => (None, None),
        (6, _) => return None,
        (_, [file @ b'a'..=b'h']) => (Some((file - b'a') as i8), None),
        (_, [rank @ b'1'..=b'8']) => (None, Some((rank - b'1') as i8)),
        (_, [file @ b'a'..=b'h', rank @ b'1'..=b'8']) => {
            (Some((file - b'a') as i8), Some((rank - b'1') as i8))
        }
        _ => return None,
    };
    if piece == 1 {
        if matches!(destination_rank, 0 | 7) != (promotion_code != 0) {
            return None;
        }
    } else if promotion_code != 0 {
        return None;
    }
    Some(ParsedSan {
        piece,
        castle: None,
        from_file,
        from_rank,
        capture,
        destination,
        promotion: promotion_code,
        stem_end: stem.len(),
        suffix,
    })
}

fn square_text(square: u8, output: &mut Vec<u8>) {
    output.push(b'a' + file(square) as u8);
    output.push(b'1' + rank(square) as u8);
}

fn canonical_stem(state: &crate::ReplayState, legal: &[Move], mv: Move) -> Vec<u8> {
    let from = origin(mv);
    let to = destination(mv);
    let piece = piece_kind(state.position.bytes[from as usize]);
    if piece == 6 && (file(from) - file(to)).abs() == 2 {
        return if file(to) > file(from) {
            b"O-O".to_vec()
        } else {
            b"O-O-O".to_vec()
        };
    }
    let capture = state.position.bytes[to as usize] != 0 || (piece == 1 && file(from) != file(to));
    let mut output = Vec::with_capacity(8);
    if piece == 1 {
        if capture {
            output.push(b'a' + file(from) as u8);
        }
    } else {
        output.push(match piece {
            2 => b'N',
            3 => b'B',
            4 => b'R',
            5 => b'Q',
            6 => b'K',
            _ => unreachable!(),
        });
        if piece != 6 {
            let contenders: Vec<u8> = legal
                .iter()
                .copied()
                .filter(|candidate| {
                    destination(*candidate) == to
                        && piece_kind(state.position.bytes[origin(*candidate) as usize]) == piece
                })
                .map(origin)
                .collect();
            if contenders.len() > 1 {
                if contenders
                    .iter()
                    .filter(|&&other| file(other) == file(from))
                    .count()
                    == 1
                {
                    output.push(b'a' + file(from) as u8);
                } else if contenders
                    .iter()
                    .filter(|&&other| rank(other) == rank(from))
                    .count()
                    == 1
                {
                    output.push(b'1' + rank(from) as u8);
                } else {
                    square_text(from, &mut output);
                }
            }
        }
    }
    if capture {
        output.push(b'x');
    }
    square_text(to, &mut output);
    if promotion(mv) != 0 {
        output.push(b'=');
        output.push(match promotion(mv) {
            1 => b'Q',
            2 => b'R',
            3 => b'B',
            4 => b'N',
            _ => unreachable!(),
        });
    }
    output
}

fn suffix_truth(state: &crate::ReplayState) -> Option<u8> {
    let local = LocallyAdmissiblePosition {
        wire: state.position.clone(),
    };
    if !king_in_check(&local, Side(state.position.bytes[64])) {
        None
    } else if matches!(board_terminal(state), BoardTerminal::Checkmate(_)) {
        Some(b'#')
    } else {
        Some(b'+')
    }
}

fn compile_games(raw: &[u8], blocks: &[StructuredBlock]) -> Result<SourceCandidate> {
    let mut terminal_error = None;
    let mut stem_error = None;
    let mut suffix_error = None;
    let mut score_error = None;
    let mut compiled = Vec::with_capacity(blocks.len());

    for (source_ordinal, block) in blocks.iter().enumerate() {
        let mut state = replay_from_start(&[]).expect("the standard initial state is valid");
        let mut moves = Vec::with_capacity(block.semantic.len());
        let mut rows = Vec::with_capacity(block.semantic.len());
        let mut resolvable = true;
        for &semantic in &block.semantic {
            let token = semantic.token;
            if board_terminal(&state) != BoardTerminal::None {
                choose(
                    &mut terminal_error,
                    reject(SOURCE_GAME_AFTER_TERMINAL, token.span.start, token.span.end),
                );
                resolvable = false;
                break;
            }
            if !semantic.san {
                continue;
            }
            let bytes = &raw[token.span.start..token.span.end];
            let Some(parsed) = parse_san(bytes) else {
                choose(
                    &mut stem_error,
                    reject(SOURCE_SAN_SHAPE, token.span.start, token.span.end),
                );
                resolvable = false;
                break;
            };
            let legal = legal_moves(&state);
            let wanted_destination = parsed.castle.map_or(parsed.destination, |kingside| {
                state.position.bytes[64] * 56 + if kingside { 6 } else { 2 }
            });
            let matches: Vec<Move> = legal
                .iter()
                .copied()
                .filter(|mv| {
                    let from = origin(*mv);
                    piece_kind(state.position.bytes[from as usize]) == parsed.piece
                        && destination(*mv) == wanted_destination
                        && promotion(*mv) == parsed.promotion
                        && parsed.from_file.is_none_or(|wanted| file(from) == wanted)
                        && parsed.from_rank.is_none_or(|wanted| rank(from) == wanted)
                })
                .collect();
            let [mv] = matches.as_slice() else {
                choose(
                    &mut stem_error,
                    reject(
                        if matches.is_empty() {
                            SOURCE_SAN_NO_MATCH
                        } else {
                            SOURCE_SAN_AMBIGUOUS
                        },
                        token.span.start,
                        token.span.end,
                    ),
                );
                resolvable = false;
                break;
            };
            let mv = *mv;
            let canonical = canonical_stem(&state, &legal, mv);
            let supplied = &bytes[..parsed.stem_end];
            let stem_valid = canonical == supplied && parsed.capture == canonical.contains(&b'x');
            if !stem_valid {
                choose(
                    &mut stem_error,
                    reject(SOURCE_SAN_NONCANONICAL, token.span.start, token.span.end),
                );
            }
            let next = apply_move(&state, mv).expect("a selected legal move applies");
            let truth = suffix_truth(&next);
            let suffix_valid = parsed.suffix == truth;
            if !suffix_valid {
                let (start, end) = if parsed.suffix.is_some() {
                    (token.span.end - 1, token.span.end)
                } else {
                    (token.span.end, token.span.end)
                };
                choose(&mut suffix_error, reject(SOURCE_SAN_SUFFIX, start, end));
            }
            if stem_valid && suffix_valid {
                rows.push(TraceRow {
                    raw_span: token.span,
                    move_bytes: encode_move(mv),
                    post_position_bytes: encode_position(next.position()),
                    suffix_truth_code: match truth {
                        None => SUFFIX_NONE,
                        Some(b'+') => SUFFIX_CHECK,
                        Some(b'#') => SUFFIX_MATE,
                        _ => unreachable!(),
                    },
                });
            }
            moves.push(mv);
            state = next;
        }
        if !resolvable {
            continue;
        }
        if validate_source_record(&moves, block.result).is_err() {
            choose(
                &mut score_error,
                reject(SOURCE_TERMINAL_SCORE, block.marker.start, block.marker.end),
            );
        }
        compiled.push(CompiledGame {
            source_ordinal,
            opener_span: block.block.opener,
            rows,
            record: GameRecord {
                moves,
                score: block.result,
            },
        });
    }

    for error in [terminal_error, stem_error, suffix_error, score_error] {
        if let Some(error) = error {
            return Err(error);
        }
    }
    let mut seen = BTreeSet::new();
    for game in &compiled {
        if !seen.insert(move_stream(&game.record)) {
            return Err(reject(
                SOURCE_DUPLICATE_MOVE_STREAM,
                game.opener_span.start,
                game.opener_span.end,
            ));
        }
    }
    for (source_ordinal, game) in compiled.iter().enumerate() {
        assert_eq!(game.source_ordinal, source_ordinal);
        assert_eq!(game.rows.len(), game.record.moves.len());
    }
    assert_eq!(
        compiled.iter().map(|game| game.rows.len()).sum::<usize>(),
        compiled
            .iter()
            .map(|game| game.record.moves.len())
            .sum::<usize>()
    );
    let games: Vec<GameRecord> = compiled.iter().map(|game| game.record.clone()).collect();
    let game_set = encode_game_set(&games)?;
    Ok(SourceCandidate { compiled, game_set })
}

pub fn encode_game(game: &GameRecord) -> Vec<u8> {
    let mut output = Vec::with_capacity(3 + game.moves.len() * 2);
    output.extend_from_slice(&(game.moves.len() as u16).to_be_bytes());
    for &mv in &game.moves {
        output.extend_from_slice(&encode_move(mv));
    }
    output.push(game.score.code());
    output
}

pub fn decode_game(raw: &[u8]) -> Result<GameRecord> {
    if raw.len() < 2 {
        return Err(reject(SOURCE_GAME_TRUNCATED, raw.len(), raw.len()));
    }
    let count = u16::from_be_bytes([raw[0], raw[1]]) as usize;
    if count == 0 || count > SOURCE_MAX_GAME_PLIES as usize {
        return Err(reject(SOURCE_GAME_COUNT, 0, 2));
    }
    let expected = count
        .checked_mul(2)
        .and_then(|size| size.checked_add(3))
        .ok_or_else(|| reject(SOURCE_GAME_COUNT, 0, 2))?;
    if raw.len() < expected {
        return Err(reject(SOURCE_GAME_TRUNCATED, raw.len(), raw.len()));
    }

    let mut moves = Vec::with_capacity(count);
    for index in 0..count {
        let start = 2 + index * 2;
        let mv = decode_move(&raw[start..start + 2])
            .map_err(|_| reject(SOURCE_GAME_MOVE, start, start + 2))?;
        moves.push(mv);
    }
    let score_at = 2 + count * 2;
    let score = Score::from_code(raw[score_at])
        .ok_or_else(|| reject(SOURCE_GAME_SCORE, score_at, score_at + 1))?;
    if raw.len() > expected {
        return Err(reject(SOURCE_GAME_TRAILING, expected, expected + 1));
    }

    let mut state = replay_from_start(&[]).expect("the standard initial state is valid");
    for (index, &mv) in moves.iter().enumerate() {
        state = apply_move(&state, mv)
            .map_err(|_| reject(SOURCE_GAME_SEMANTIC, 2 + index * 2, 4 + index * 2))?;
    }
    validate_source_record(&moves, score)
        .map_err(|_| reject(SOURCE_GAME_SEMANTIC, score_at, score_at + 1))?;
    Ok(GameRecord { moves, score })
}

fn move_stream(game: &GameRecord) -> Vec<u8> {
    game.moves.iter().flat_map(|&mv| encode_move(mv)).collect()
}

pub fn validate_anthology(games: &[GameRecord]) -> Result<Vec<GameRecord>> {
    if games.len() != SOURCE_ANTHOLOGY_GAME_COUNT as usize {
        return Err(reject(SOURCE_ANTHOLOGY_COUNT, 0, 0));
    }
    let mut seen = BTreeSet::new();
    for game in games {
        if !seen.insert(move_stream(game)) {
            return Err(reject(SOURCE_ANTHOLOGY_DUPLICATE_STREAM, 0, 0));
        }
    }
    Ok(games.to_vec())
}

pub fn encode_game_set(games: &[GameRecord]) -> Result<Vec<u8>> {
    if games.is_empty() || games.len() > SOURCE_MAX_GAME_SET_GAMES as usize {
        return Err(reject(SOURCE_GAME_SET_COUNT, 0, 0));
    }
    let mut total_plies = 0usize;
    for game in games {
        total_plies = total_plies
            .checked_add(game.moves.len())
            .ok_or_else(|| reject(SOURCE_GAME_SET_TOTAL_PLIES, 0, 0))?;
        if total_plies > SOURCE_MAX_GAME_SET_PLIES as usize {
            return Err(reject(SOURCE_GAME_SET_TOTAL_PLIES, 0, 0));
        }
    }

    let mut encoded: Vec<Vec<u8>> = games.iter().map(encode_game).collect();
    encoded.sort();
    if encoded.windows(2).any(|pair| pair[0] == pair[1]) {
        return Err(reject(SOURCE_GAME_SET_DUPLICATE, 0, 0));
    }
    let output_len = encoded
        .iter()
        .try_fold(2usize, |size, game| size.checked_add(game.len()))
        .ok_or_else(|| reject(SOURCE_GAME_SET_TOTAL_PLIES, 0, 0))?;
    let mut output = Vec::with_capacity(output_len);
    output.extend_from_slice(&(games.len() as u16).to_be_bytes());
    for game in encoded {
        output.extend_from_slice(&game);
    }
    Ok(output)
}

pub fn decode_game_set(raw: &[u8]) -> Result<Vec<GameRecord>> {
    if raw.len() > SOURCE_MAX_GAME_SET_BYTES as usize {
        let start = SOURCE_MAX_GAME_SET_BYTES as usize;
        return Err(reject(SOURCE_GAME_SET_SIZE, start, start + 1));
    }
    if raw.len() < 2 {
        return Err(reject(SOURCE_GAME_SET_TRUNCATED, raw.len(), raw.len()));
    }
    let count = u16::from_be_bytes([raw[0], raw[1]]) as usize;
    if count == 0 || count > SOURCE_MAX_GAME_SET_GAMES as usize {
        return Err(reject(SOURCE_GAME_SET_COUNT, 0, 2));
    }

    let mut at = 2usize;
    let mut total_plies = 0usize;
    let mut spans = Vec::with_capacity(count.min(raw.len() / 3));
    for _ in 0..count {
        if raw.len().saturating_sub(at) < 2 {
            return Err(reject(SOURCE_GAME_SET_TRUNCATED, raw.len(), raw.len()));
        }
        let header = at;
        let plies = u16::from_be_bytes([raw[at], raw[at + 1]]) as usize;
        if plies == 0 || plies > SOURCE_MAX_GAME_PLIES as usize {
            return Err(reject(SOURCE_GAME_COUNT, at, at + 2));
        }
        total_plies = total_plies
            .checked_add(plies)
            .ok_or_else(|| reject(SOURCE_GAME_SET_TOTAL_PLIES, at, at + 2))?;
        if total_plies > SOURCE_MAX_GAME_SET_PLIES as usize {
            return Err(reject(SOURCE_GAME_SET_TOTAL_PLIES, at, at + 2));
        }
        let length = plies
            .checked_mul(2)
            .and_then(|size| size.checked_add(3))
            .ok_or_else(|| reject(SOURCE_GAME_COUNT, at, at + 2))?;
        let end = at
            .checked_add(length)
            .ok_or_else(|| reject(SOURCE_GAME_SET_TRUNCATED, raw.len(), raw.len()))?;
        if end > raw.len() {
            return Err(reject(SOURCE_GAME_SET_TRUNCATED, raw.len(), raw.len()));
        }
        spans.push((header, end));
        at = end;
    }

    let mut games = Vec::with_capacity(count);
    for &(start, end) in &spans {
        let bytes = &raw[start..end];
        let game = decode_game(bytes).map_err(|error| {
            reject(
                error.code,
                start + error.raw_start as usize,
                start + error.raw_end as usize,
            )
        })?;
        games.push(game);
    }
    for pair in spans.windows(2) {
        let prior = &raw[pair[0].0..pair[0].1];
        let (start, end) = pair[1];
        let bytes = &raw[start..end];
        if bytes < prior {
            return Err(reject(SOURCE_GAME_SET_ORDER, start, end));
        }
        if bytes == prior {
            return Err(reject(SOURCE_GAME_SET_DUPLICATE, start, end));
        }
    }
    if at < raw.len() {
        return Err(reject(SOURCE_GAME_SET_TRAILING, at, at + 1));
    }
    Ok(games)
}

const CANDIDATE_KEYS: &[&str] = &[
    "constants_sha256",
    "game_count",
    "game_set_identity",
    "games",
    "initial_position_bytes",
    "initial_position_identity",
    "ir_bytes",
    "ply_count",
    "schema",
    "score_counts",
    "source_sha256",
    "spec_sha256",
];
const GAME_KEYS: &[&str] = &["game_identity", "rows", "score", "source_ordinal"];
const SPEC_KEYS: &[&str] = &["chess_v0", "identity_v0", "source_v0"];

fn mv_object(entries: impl IntoIterator<Item = (&'static str, ManifestValue)>) -> ManifestValue {
    ManifestValue::Object(
        entries
            .into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn checked_evidence(evidence: &EvidenceInputs<'_>) -> Result<()> {
    if [
        evidence.source,
        evidence.chess_v0,
        evidence.source_v0,
        evidence.identity_v0,
        evidence.constants_v0,
    ]
    .iter()
    .any(|value| value.len() > MAX_MANIFEST_BYTES)
    {
        return Err(reject(SOURCE_EVIDENCE_SHAPE, 0, 0));
    }
    Ok(())
}

fn candidate_value(candidate: &SourceCandidate, evidence: &EvidenceInputs<'_>) -> ManifestValue {
    let initial = replay_from_start(&[]).expect("initial replay");
    let initial_bytes = encode_position(initial.position());
    let mut scores = [0u64; 3];
    let mut ir_bytes = 0u64;
    let mut ply_count = 0u64;
    let games = candidate
        .compiled
        .iter()
        .map(|compiled| {
            let game_bytes = encode_game(&compiled.record);
            scores[compiled.record.score.code() as usize] += 1;
            ir_bytes += game_bytes.len() as u64;
            ply_count += compiled.rows.len() as u64;
            let rows = compiled
                .rows
                .iter()
                .map(|row| {
                    ManifestValue::Array(vec![
                        ManifestValue::U64(row.raw_span.start as u64),
                        ManifestValue::U64(row.raw_span.end as u64),
                        ManifestValue::String(format!(
                            "{:02x}{:02x}",
                            row.move_bytes[0], row.move_bytes[1]
                        )),
                        ManifestValue::String(
                            row.post_position_bytes
                                .iter()
                                .map(|byte| format!("{byte:02x}"))
                                .collect(),
                        ),
                        ManifestValue::U64(row.suffix_truth_code as u64),
                    ])
                })
                .collect();
            mv_object([
                (
                    "game_identity",
                    ManifestValue::String(
                        identity_hex(b"golden-board:game:v0\0", &[&game_bytes]).unwrap(),
                    ),
                ),
                ("rows", ManifestValue::Array(rows)),
                (
                    "score",
                    ManifestValue::U64(compiled.record.score.code() as u64),
                ),
                (
                    "source_ordinal",
                    ManifestValue::U64(compiled.source_ordinal as u64),
                ),
            ])
        })
        .collect();
    mv_object([
        (
            "constants_sha256",
            ManifestValue::String(digest(evidence.constants_v0)),
        ),
        (
            "game_count",
            ManifestValue::U64(candidate.compiled.len() as u64),
        ),
        (
            "game_set_identity",
            ManifestValue::String(
                identity_hex(b"golden-board:game-set:v0\0", &[&candidate.game_set]).unwrap(),
            ),
        ),
        ("games", ManifestValue::Array(games)),
        (
            "initial_position_bytes",
            ManifestValue::String(
                initial_bytes
                    .iter()
                    .map(|byte| format!("{byte:02x}"))
                    .collect(),
            ),
        ),
        (
            "initial_position_identity",
            ManifestValue::String(
                identity_hex(b"golden-board:position:v0\0", &[&initial_bytes]).unwrap(),
            ),
        ),
        ("ir_bytes", ManifestValue::U64(ir_bytes)),
        ("ply_count", ManifestValue::U64(ply_count)),
        (
            "schema",
            ManifestValue::String("golden-board-source-candidate-v0".to_owned()),
        ),
        (
            "score_counts",
            ManifestValue::Array(scores.into_iter().map(ManifestValue::U64).collect()),
        ),
        (
            "source_sha256",
            ManifestValue::String(digest(evidence.source)),
        ),
        (
            "spec_sha256",
            mv_object([
                ("chess_v0", ManifestValue::String(digest(evidence.chess_v0))),
                (
                    "identity_v0",
                    ManifestValue::String(digest(evidence.identity_v0)),
                ),
                (
                    "source_v0",
                    ManifestValue::String(digest(evidence.source_v0)),
                ),
            ]),
        ),
    ])
}

pub fn encode_candidate_trace(
    candidate: &SourceCandidate,
    evidence: &EvidenceInputs<'_>,
) -> Result<Vec<u8>> {
    checked_evidence(evidence)?;
    if candidate != &compile_source(evidence.source)? {
        return Err(reject(SOURCE_EVIDENCE_CROSS_FIELD, 0, 0));
    }
    serialize_manifest(&candidate_value(candidate, evidence))
        .map_err(|_| reject(SOURCE_EVIDENCE_SIZE, 0, 0))
}

fn exact_keys(fields: &BTreeMap<String, ManifestValue>, keys: &[&str]) -> bool {
    fields.len() == keys.len() && keys.iter().all(|key| fields.contains_key(*key))
}

fn hex_string(value: Option<&ManifestValue>, length: usize) -> bool {
    matches!(value, Some(ManifestValue::String(text)) if text.len() == length && text.bytes().all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)))
}

fn bounded_u64(value: Option<&ManifestValue>, maximum: u64) -> bool {
    matches!(value, Some(ManifestValue::U64(number)) if *number <= maximum)
}

fn candidate_shape(value: &ManifestValue) -> bool {
    let ManifestValue::Object(fields) = value else {
        return false;
    };
    let Some(ManifestValue::Object(specs)) = fields.get("spec_sha256") else {
        return false;
    };
    let Some(ManifestValue::Array(scores)) = fields.get("score_counts") else {
        return false;
    };
    let Some(ManifestValue::Array(games)) = fields.get("games") else {
        return false;
    };
    if !exact_keys(fields, CANDIDATE_KEYS)
        || !exact_keys(specs, SPEC_KEYS)
        || !matches!(fields.get("schema"), Some(ManifestValue::String(value)) if value == "golden-board-source-candidate-v0")
        || !["constants_sha256", "game_set_identity", "initial_position_identity", "source_sha256"]
            .iter()
            .all(|key| hex_string(fields.get(*key), 64))
        || !SPEC_KEYS.iter().all(|key| hex_string(specs.get(*key), 64))
        || !hex_string(fields.get("initial_position_bytes"), 134)
        || !bounded_u64(
            fields.get("game_count"),
            SOURCE_ANTHOLOGY_GAME_COUNT as u64,
        )
        || !bounded_u64(fields.get("ply_count"), SOURCE_MAX_TOTAL_PLIES as u64)
        || !bounded_u64(fields.get("ir_bytes"), SOURCE_MAX_GAME_SET_BYTES as u64)
        || scores.len() != 3
        || !scores.iter().all(|score| {
            matches!(score, ManifestValue::U64(value) if *value <= SOURCE_ANTHOLOGY_GAME_COUNT as u64)
        })
        || games.len() > SOURCE_ANTHOLOGY_GAME_COUNT as usize
    {
        return false;
    }
    games.iter().all(|game| {
        let ManifestValue::Object(game) = game else {
            return false;
        };
        let Some(ManifestValue::Array(rows)) = game.get("rows") else {
            return false;
        };
        exact_keys(game, GAME_KEYS)
            && hex_string(game.get("game_identity"), 64)
            && bounded_u64(
                game.get("source_ordinal"),
                SOURCE_ANTHOLOGY_GAME_COUNT as u64 - 1,
            )
            && matches!(game.get("score"), Some(ManifestValue::U64(value)) if *value <= SCORE_DRAW as u64)
            && rows.len() <= SOURCE_MAX_GAME_PLIES as usize
            && rows.iter().all(|row| {
                let ManifestValue::Array(row) = row else {
                    return false;
                };
                row.len() == 5
                    && matches!((&row[0], &row[1]), (ManifestValue::U64(start), ManifestValue::U64(end)) if start <= end && *end <= SOURCE_MAX_INPUT_BYTES as u64)
                    && hex_string(row.get(2), 4)
                    && hex_string(row.get(3), 134)
                    && matches!(&row[4], ManifestValue::U64(value) if *value <= SUFFIX_MATE as u64)
            })
    })
}

fn parsed_candidate(candidate_bytes: &[u8]) -> Result<ManifestValue> {
    if candidate_bytes.len() > MAX_MANIFEST_BYTES {
        return Err(reject(
            SOURCE_EVIDENCE_SIZE,
            MAX_MANIFEST_BYTES,
            MAX_MANIFEST_BYTES + 1,
        ));
    }
    let value = parse_manifest(candidate_bytes).map_err(|_| reject(SOURCE_EVIDENCE_SHAPE, 0, 0))?;
    if !candidate_shape(&value) {
        return Err(reject(SOURCE_EVIDENCE_SHAPE, 0, 0));
    }
    if serialize_manifest(&value).map_err(|_| reject(SOURCE_EVIDENCE_SHAPE, 0, 0))?
        != candidate_bytes
    {
        return Err(reject(SOURCE_EVIDENCE_NONCANONICAL, 0, 0));
    }
    Ok(value)
}

fn string_field<'a>(fields: &'a BTreeMap<String, ManifestValue>, key: &str) -> &'a str {
    let ManifestValue::String(value) = &fields[key] else {
        unreachable!("shape-checked string")
    };
    value
}

pub fn validate_candidate_trace(
    candidate_bytes: &[u8],
    game_set_bytes: &[u8],
    evidence: &EvidenceInputs<'_>,
) -> Result<ValidatedCandidate> {
    checked_evidence(evidence)?;
    let value = parsed_candidate(candidate_bytes)?;
    let ManifestValue::Object(fields) = &value else {
        unreachable!()
    };
    let ManifestValue::Object(specs) = &fields["spec_sha256"] else {
        unreachable!()
    };
    if string_field(fields, "constants_sha256") != digest(evidence.constants_v0)
        || string_field(fields, "source_sha256") != digest(evidence.source)
        || string_field(specs, "chess_v0") != digest(evidence.chess_v0)
        || string_field(specs, "identity_v0") != digest(evidence.identity_v0)
        || string_field(specs, "source_v0") != digest(evidence.source_v0)
    {
        return Err(reject(SOURCE_EVIDENCE_HASH, 0, 0));
    }
    let expected = compile_source(evidence.source)?;
    let expected_bytes = serialize_manifest(&candidate_value(&expected, evidence))
        .map_err(|_| reject(SOURCE_EVIDENCE_SIZE, 0, 0))?;
    if candidate_bytes != expected_bytes || game_set_bytes != expected.game_set {
        return Err(reject(SOURCE_EVIDENCE_CROSS_FIELD, 0, 0));
    }
    Ok(ValidatedCandidate {
        candidate_bytes: candidate_bytes.to_vec(),
        game_set_bytes: game_set_bytes.to_vec(),
    })
}

pub fn coordinate_candidates(
    first: &ValidatedCandidate,
    second: &ValidatedCandidate,
) -> Result<RetainedEvidence> {
    if first != second {
        return Err(reject(SOURCE_CANDIDATE_MISMATCH, 0, 0));
    }
    let ManifestValue::Object(mut value) =
        parse_manifest(&first.candidate_bytes).map_err(|_| reject(SOURCE_EVIDENCE_SHAPE, 0, 0))?
    else {
        return Err(reject(SOURCE_EVIDENCE_SHAPE, 0, 0));
    };
    value.insert(
        "schema".to_owned(),
        ManifestValue::String("golden-board-source-compilation-v0".to_owned()),
    );
    value.insert(
        "producer_labels".to_owned(),
        ManifestValue::Array(vec![
            ManifestValue::String("python".to_owned()),
            ManifestValue::String("rust".to_owned()),
        ]),
    );
    let report_bytes = serialize_manifest(&ManifestValue::Object(value))
        .map_err(|_| reject(SOURCE_EVIDENCE_SIZE, 0, 0))?;
    Ok(RetainedEvidence {
        report_bytes,
        game_set_bytes: first.game_set_bytes.clone(),
    })
}

pub fn validate_retained_evidence(
    report_bytes: &[u8],
    game_set_bytes: &[u8],
    evidence: &EvidenceInputs<'_>,
) -> Result<RetainedEvidence> {
    if report_bytes.len() > MAX_MANIFEST_BYTES {
        return Err(reject(
            SOURCE_EVIDENCE_SIZE,
            MAX_MANIFEST_BYTES,
            MAX_MANIFEST_BYTES + 1,
        ));
    }
    let ManifestValue::Object(mut value) =
        parse_manifest(report_bytes).map_err(|_| reject(SOURCE_EVIDENCE_SHAPE, 0, 0))?
    else {
        return Err(reject(SOURCE_EVIDENCE_SHAPE, 0, 0));
    };
    let labels = value.remove("producer_labels");
    let schema = value.insert(
        "schema".to_owned(),
        ManifestValue::String("golden-board-source-candidate-v0".to_owned()),
    );
    if value.len() != CANDIDATE_KEYS.len()
        || !matches!(schema, Some(ManifestValue::String(value)) if value == "golden-board-source-compilation-v0")
        || labels
            != Some(ManifestValue::Array(vec![
                ManifestValue::String("python".to_owned()),
                ManifestValue::String("rust".to_owned()),
            ]))
        || !candidate_shape(&ManifestValue::Object(value.clone()))
    {
        return Err(reject(SOURCE_EVIDENCE_SHAPE, 0, 0));
    }
    let mut report_value = value.clone();
    report_value.insert(
        "schema".to_owned(),
        ManifestValue::String("golden-board-source-compilation-v0".to_owned()),
    );
    report_value.insert(
        "producer_labels".to_owned(),
        ManifestValue::Array(vec![
            ManifestValue::String("python".to_owned()),
            ManifestValue::String("rust".to_owned()),
        ]),
    );
    if serialize_manifest(&ManifestValue::Object(report_value))
        .map_err(|_| reject(SOURCE_EVIDENCE_SHAPE, 0, 0))?
        != report_bytes
    {
        return Err(reject(SOURCE_EVIDENCE_NONCANONICAL, 0, 0));
    }
    let candidate_bytes = serialize_manifest(&ManifestValue::Object(value))
        .map_err(|_| reject(SOURCE_EVIDENCE_SHAPE, 0, 0))?;
    let validated = validate_candidate_trace(&candidate_bytes, game_set_bytes, evidence)?;
    Ok(RetainedEvidence {
        report_bytes: report_bytes.to_vec(),
        game_set_bytes: validated.game_set_bytes,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{encode_position, replay_from_start};

    #[test]
    fn source_candidate_retains_complete_private_trace_rows() {
        let raw = b"f3 e5 g4 Qh4# 0-1";
        let spans = [(0, 2), (3, 5), (6, 8), (9, 13)];
        let block = StructuredBlock {
            block: Block {
                opener: Span { start: 0, end: 0 },
                content: Span {
                    start: 0,
                    end: raw.len(),
                },
            },
            result: Score::SecondWin,
            semantic: spans
                .iter()
                .map(|&(start, end)| SemanticToken {
                    token: Token {
                        span: Span { start, end },
                    },
                    san: true,
                })
                .collect(),
            marker: Span { start: 14, end: 17 },
        };

        let candidate = compile_games(raw, &[block]).unwrap();
        assert_eq!(candidate.compiled.len(), 1);
        let compiled = &candidate.compiled[0];
        assert_eq!(compiled.source_ordinal, 0);
        assert_eq!(compiled.opener_span, Span { start: 0, end: 0 });
        assert_eq!(compiled.rows.len(), compiled.record.moves.len());
        assert_eq!(compiled.rows.len(), 4);
        assert_eq!(compiled.record.score, Score::SecondWin);

        let expected_moves = [[0x35, 0x50], [0xd2, 0x40], [0x39, 0xe0], [0xed, 0xf0]];
        let expected_suffixes = [SUFFIX_NONE, SUFFIX_NONE, SUFFIX_NONE, SUFFIX_MATE];
        let mut state = replay_from_start(&[]).unwrap();
        for (index, row) in compiled.rows.iter().enumerate() {
            assert_eq!(
                row.raw_span,
                Span {
                    start: spans[index].0,
                    end: spans[index].1
                }
            );
            assert_eq!(row.move_bytes, expected_moves[index]);
            state = apply_move(&state, compiled.record.moves[index]).unwrap();
            assert_eq!(row.post_position_bytes, encode_position(state.position()));
            assert_eq!(row.suffix_truth_code, expected_suffixes[index]);
        }
        assert_eq!((candidate.game_count(), candidate.ply_count()), (1, 4));
    }
}
