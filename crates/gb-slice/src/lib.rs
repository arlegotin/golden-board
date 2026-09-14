//! Independent, fail-closed compiler for the reviewed M2 semantic slice.

use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

use gb_content::{
    ContentAuthoringProjection, ContentProjectionView, FieldSpec, FieldValue, LessonCase, Record,
    RecordPayload, authoring_from_validated, encode_content_v0, projection_view, stream_validation,
};
use gb_foundation::constants::{
    ANSWER_EXTERNAL, ATOM_UNSIGNED, BINDING_DATA, CONTENT_KIND_ROOT, CONTENT_VERSION,
    FEEDBACK_NEUTRAL, FIELD_RECORD_REF, RESPONSE_SINGLE, ROLE_PRACTICE,
};
use gb_foundation::{identity_hex, validate_canonical_manifest};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

const DECLARATION_CAP: usize = 32_768;
const FIXTURE_CAP: usize = 1_048_576;
const TEXT_INPUT_CAP: usize = 262_144;
const GAME_SET_CAP: usize = 327_677;
const REQUIRED_STREAM_LENGTH: usize = 575;
const REQUIRED_STREAM_SHA256: &str =
    "99c783060adb543ef1621b4e17f57772bd88c9d37cb249981aed5f9a4962d7dc";
const ALL_STREAM_LENGTH: usize = 13_644;
const ALL_STREAM_SHA256: &str = "de7e22f0aa4316d9f32d9435287dd19bd6c04519aae1dc9bd816613f26929671";

const CONTENT_FIXTURE_SHA256: &str =
    "b3f4279e95854e77bd3ce25c05e8580b1298ffccc164ac40a6010e86091a038b";
const CHESS_FIXTURE_SHA256: &str =
    "9a63aa74a32761bf1f8919278e895f532e4d4f305a30f74ddd1d0c4acec6a639";
const GAME_SET_SHA256: &str = "e883055cd0417061cf04d596cbca75d039948a987180d26a80bd6d6888f4764e";
const GAME_SET_IDENTITY: &str = "ffe37ea482b590eb2b454041c0918d05a85161c8f0c604bbf58cc7b71de87db9";
const CONTENT_SPEC_SHA256: &str =
    "6d47bce1bfaa8430ea81dafcfa37f98aa9260b3a8c732e237fbca04b7601d476";
const CONSTANTS_SHA256: &str = "ceb2c0f66db88631aa036d886b018d9c93a6817ac566dcbda3104fc6dd9118b6";
const CURRICULUM_SHA256: &str = "601b61eb433e8128e39dd8c62baee6ed1f5461f3ac9a2d0182114861f2ddf263";

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SliceError {
    reason: &'static str,
    path: &'static str,
}

impl SliceError {
    pub fn reason(&self) -> &'static str {
        self.reason
    }

    pub fn path(&self) -> &'static str {
        self.path
    }
}

impl fmt::Display for SliceError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} at {}", self.reason, self.path)
    }
}

impl std::error::Error for SliceError {}

fn error(reason: &'static str, path: &'static str) -> SliceError {
    SliceError { reason, path }
}

#[derive(Clone, Copy)]
pub struct SliceInputs<'a> {
    pub declaration: &'a [u8],
    pub content_fixture: &'a [u8],
    pub chess_fixture: &'a [u8],
    pub game_set: &'a [u8],
    pub content_spec: &'a [u8],
    pub constants: &'a [u8],
    pub curriculum: &'a [u8],
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Closure {
    Required,
    AllOnly,
    All,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AtomicAssignment {
    closure: Closure,
    section_id: u16,
    semantic_copy_id: u16,
    record_ids: Vec<u16>,
}

impl AtomicAssignment {
    pub fn closure(&self) -> Closure {
        self.closure
    }

    pub fn section_id(&self) -> u16 {
        self.section_id
    }

    pub fn semantic_copy_id(&self) -> u16 {
        self.semantic_copy_id
    }

    pub fn record_ids(&self) -> &[u16] {
        &self.record_ids
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TierRoot {
    closure: Closure,
    section_id: u16,
    semantic_copy_id: u16,
    record_id: u16,
    frame: Vec<u8>,
}

impl TierRoot {
    pub fn closure(&self) -> Closure {
        self.closure
    }

    pub fn section_id(&self) -> u16 {
        self.section_id
    }

    pub fn semantic_copy_id(&self) -> u16 {
        self.semantic_copy_id
    }

    pub fn record_id(&self) -> u16 {
        self.record_id
    }

    pub fn frame(&self) -> &[u8] {
        &self.frame
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CapacityPrototype {
    kind: u16,
    prototype_id: String,
    source_record_id: u16,
    frame_length: u16,
}

impl CapacityPrototype {
    pub fn kind(&self) -> u16 {
        self.kind
    }

    pub fn prototype_id(&self) -> &str {
        &self.prototype_id
    }

    pub fn source_record_id(&self) -> u16 {
        self.source_record_id
    }

    pub fn frame_length(&self) -> u16 {
        self.frame_length
    }
}

#[derive(Clone, Debug)]
pub struct SliceCompilation {
    required_stream: Vec<u8>,
    all_stream: Vec<u8>,
    required_projection: ContentProjectionView,
    all_projection: ContentProjectionView,
    game_payloads: Vec<Vec<u8>>,
    fixture_payloads: Vec<Vec<u8>>,
    assignments: Vec<AtomicAssignment>,
    tier_roots: Vec<TierRoot>,
    capacity_prototypes: Vec<CapacityPrototype>,
}

impl SliceCompilation {
    pub fn required_stream(&self) -> &[u8] {
        &self.required_stream
    }

    pub fn all_stream(&self) -> &[u8] {
        &self.all_stream
    }

    pub fn required_projection(&self) -> &ContentProjectionView {
        &self.required_projection
    }

    pub fn all_projection(&self) -> &ContentProjectionView {
        &self.all_projection
    }

    pub fn game_payloads(&self) -> &[Vec<u8>] {
        &self.game_payloads
    }

    pub fn fixture_payloads(&self) -> &[Vec<u8>] {
        &self.fixture_payloads
    }

    pub fn assignments(&self) -> &[AtomicAssignment] {
        &self.assignments
    }

    pub fn tier_roots(&self) -> &[TierRoot] {
        &self.tier_roots
    }

    pub fn capacity_prototypes(&self) -> &[CapacityPrototype] {
        &self.capacity_prototypes
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn checked_sha(
    bytes: &[u8],
    cap: usize,
    expected: &str,
    path: &'static str,
) -> Result<(), SliceError> {
    if bytes.len() > cap {
        return Err(error("input_too_large", path));
    }
    if sha256_hex(bytes) != expected {
        return Err(error("input_digest", path));
    }
    Ok(())
}

fn expected_declaration() -> Value {
    let capacity = [1_u16, 6, 9, 12, 13, 14, 15, 16, 17, 19, 20, 25, 26, 29]
        .into_iter()
        .enumerate()
        .map(|(index, source_record_id)| {
            json!({
                "kind": index + 1,
                "prototype_id": format!("generic-base-kind-{:02}", index + 1),
                "role": "nonsemantic-capacity-only",
                "source_record_id": source_record_id,
            })
        })
        .collect::<Vec<_>>();
    let games = (0_u16..64)
        .map(|ordinal| {
            json!({
                "binding_record_id": 30 + ordinal * 2,
                "closure": "m2_all_only",
                "game_ordinal": ordinal,
                "opaque_record_id": 31 + ordinal * 2,
                "section_id": 100 + ordinal,
                "semantic_copy_id": 0,
            })
        })
        .collect::<Vec<_>>();
    let case_names = [
        ("castling-positive-first-kingside", "castling-kingside"),
        ("castling-positive-first-queenside", "castling-queenside"),
        ("en-passant-legal-capture", "en-passant"),
        ("promotion-quiet-queen", "promotion-queen"),
        ("promotion-quiet-rook", "promotion-rook"),
        ("promotion-quiet-bishop", "promotion-bishop"),
        ("promotion-quiet-knight", "promotion-knight"),
        ("geometry-illegal-self-check", "self-check-rejection"),
        (
            "en-passant-nominal-without-capturer",
            "board-local-history-contrast",
        ),
        (
            "en-passant-effective-key-retained",
            "board-local-history-contrast",
        ),
    ];
    let fixtures = case_names
        .into_iter()
        .enumerate()
        .map(|(ordinal, (case_name, role))| {
            json!({
                "binding_record_id": 158 + ordinal * 2,
                "case_name": case_name,
                "closure": "m2_all_only",
                "fixture_ordinal": ordinal,
                "opaque_record_id": 159 + ordinal * 2,
                "role": role,
                "section_id": 200 + ordinal,
                "semantic_copy_id": 0,
            })
        })
        .collect::<Vec<_>>();
    let opaque_refs = (0_u16..64)
        .map(|ordinal| 31 + ordinal * 2)
        .chain((0_u16..10).map(|ordinal| 159 + ordinal * 2))
        .collect::<Vec<_>>();
    json!({
        "asymmetry_probe": {
            "cells": [0,1,2,3,4,5],
            "columns": 3,
            "committed_response_hex": "0100010002",
            "detects": ["transpose","reflection","polarity","row-column","bit-order"],
            "matrix_record_id": 12,
            "path_actions_hex": ["01000002","03000000"],
            "region_ids": [1,2,3],
            "region_set_record_id": 15,
            "rows": 2,
        },
        "capacity_prototypes": capacity,
        "chess_fixture_cases": {
            "assignments": fixtures,
            "binding_record": {
                "argument": 29,
                "auxiliary": "len(chess_fixture_binary[fixture_ordinal])",
                "binding_class": 1,
                "kind": "SEMANTIC_BINDING",
                "namespace_id": 3,
                "record_id": "binding_record_id",
                "semantic_code": "fixture_ordinal+1",
            },
            "opaque_record": {
                "data": "chess_fixture_binary[fixture_ordinal]",
                "data_binding_ref": "binding_record_id",
                "kind": "OPAQUE_DATA",
                "record_id": "opaque_record_id",
            },
            "payload_encoding": "slice-v0-chess-fixture-binary",
        },
        "content_base": {
            "fixture_name": "generic-base",
            "removed_root_record_id": 29,
            "retain_record_ids": (1_u16..=28).collect::<Vec<_>>(),
            "stream_length": 575,
            "stream_sha256": REQUIRED_STREAM_SHA256,
        },
        "game_record_plan": {
            "assignments": games,
            "binding_record": {
                "argument": 29,
                "auxiliary": "len(canonical_game_bytes[game_ordinal])",
                "binding_class": 1,
                "kind": "SEMANTIC_BINDING",
                "namespace_id": 2,
                "record_id": "binding_record_id",
                "semantic_code": "game_ordinal+1",
            },
            "opaque_record": {
                "data": "canonical_game_bytes[game_ordinal]",
                "data_binding_ref": "binding_record_id",
                "kind": "OPAQUE_DATA",
                "record_id": "opaque_record_id",
            },
        },
        "inputs": {
            "chess_fixture": {"path":"conformance/chess-v0.json","sha256":CHESS_FIXTURE_SHA256},
            "constants": {"path":"spec/constants-v0.toml","sha256":CONSTANTS_SHA256},
            "content_fixture": {"path":"conformance/content-v0.json","sha256":CONTENT_FIXTURE_SHA256},
            "content_spec": {"path":"spec/content-v0.md","sha256":CONTENT_SPEC_SHA256},
            "curriculum": {"path":"spec/curriculum-v0.toml","sha256":CURRICULUM_SHA256},
            "game_set": {"count":64,"identity":GAME_SET_IDENTITY,"path":"reports/game-set-v0.bin","sha256":GAME_SET_SHA256},
        },
        "records": [
            {"atom_class":1,"atom_width":1,"entries":[],"kind":"ATOM_SCHEMA","max_value":255,"min_value":0,"record_id":29},
            {"fields":[{"count":74,"name_text_ref":3,"storage":2,"type":9}],"kind":"FIELD_SCHEMA","record_id":178},
            {"field_schema_ref":178,"field_values":[{"record_refs":opaque_refs}],"kind":"TUPLE","record_id":179},
            {"display_ref":179,"feedback_code":1,"kind":"FEEDBACK","predicate_result_ref":0,"record_id":180},
            {"answer_mode":2,"case_count":0,"cases":[],"default_feedback_ref":180,"default_next_node_ref":26,"flags":0,"item_event_budget":2,"kind":"LESSON_NODE","max_selections":1,"passive_trace_ref":0,"predicate_result_ref":0,"presentation_ref":12,"record_id":181,"region_set_ref":15,"response_shape":1,"role":5},
            {"entry_node_ref":181,"global_event_budget":10,"kind":"ROOT","record_id":182},
        ],
        "schema": "golden-board.m2-slice/v0",
        "section_plan": {
            "support_assignments": [
                {"closure":"m2_required","record_ids":(1_u16..=28).collect::<Vec<_>>(),"section_id":16,"semantic_copy_id":0},
                {"closure":"m2_all_only","record_ids":[29],"section_id":17,"semantic_copy_id":0},
                {"closure":"m2_all_only","record_ids":[178,179,180,181],"section_id":210,"semantic_copy_id":0},
            ],
            "tier_roots": [
                {"closure":"m2_required","record_id":29,"section_id":2,"semantic_copy_id":0,"source":"content_base.removed_root_record"},
                {"closure":"m2_all","record_id":182,"section_id":3,"semantic_copy_id":0,"source":"records"},
            ],
        },
        "selected_curriculum_families": ["setup_turn","ordinary_move_capture","control_vs_legal","king_safety","castling","en_passant","promotion","position_history_draw","record_replay"],
    })
}

fn parse_declaration(bytes: &[u8]) -> Result<Value, SliceError> {
    if bytes.len() > DECLARATION_CAP {
        return Err(error("input_too_large", "declaration"));
    }
    validate_canonical_manifest(bytes).map_err(|_| error("noncanonical", "declaration"))?;
    let value: Value =
        serde_json::from_slice(bytes).map_err(|_| error("bad_json", "declaration"))?;
    if value != expected_declaration() {
        return Err(error("declaration_mismatch", "declaration"));
    }
    Ok(value)
}

fn hex_bytes(value: &str, path: &'static str) -> Result<Vec<u8>, SliceError> {
    if value.len() % 2 != 0 {
        return Err(error("bad_hex", path));
    }
    let mut output = Vec::with_capacity(value.len() / 2);
    for pair in value.as_bytes().chunks_exact(2) {
        let digit = |byte: u8| match byte {
            b'0'..=b'9' => Some(byte - b'0'),
            b'a'..=b'f' => Some(byte - b'a' + 10),
            _ => None,
        };
        let high = digit(pair[0]).ok_or_else(|| error("bad_hex", path))?;
        let low = digit(pair[1]).ok_or_else(|| error("bad_hex", path))?;
        output.push((high << 4) | low);
    }
    Ok(output)
}

fn object<'a>(
    value: &'a Value,
    path: &'static str,
) -> Result<&'a serde_json::Map<String, Value>, SliceError> {
    value.as_object().ok_or_else(|| error("bad_shape", path))
}

fn array<'a>(value: &'a Value, path: &'static str) -> Result<&'a [Value], SliceError> {
    value
        .as_array()
        .map(Vec::as_slice)
        .ok_or_else(|| error("bad_shape", path))
}

fn string<'a>(value: &'a Value, path: &'static str) -> Result<&'a str, SliceError> {
    value.as_str().ok_or_else(|| error("bad_shape", path))
}

fn number(value: &Value, path: &'static str) -> Result<u64, SliceError> {
    value.as_u64().ok_or_else(|| error("bad_shape", path))
}

fn member<'a>(value: &'a Value, key: &str, path: &'static str) -> Result<&'a Value, SliceError> {
    object(value, path)?
        .get(key)
        .ok_or_else(|| error("bad_shape", path))
}

fn validate_inputs(inputs: SliceInputs<'_>) -> Result<(), SliceError> {
    checked_sha(
        inputs.content_fixture,
        FIXTURE_CAP,
        CONTENT_FIXTURE_SHA256,
        "content_fixture",
    )?;
    checked_sha(
        inputs.chess_fixture,
        FIXTURE_CAP,
        CHESS_FIXTURE_SHA256,
        "chess_fixture",
    )?;
    checked_sha(inputs.game_set, GAME_SET_CAP, GAME_SET_SHA256, "game_set")?;
    checked_sha(
        inputs.content_spec,
        TEXT_INPUT_CAP,
        CONTENT_SPEC_SHA256,
        "content_spec",
    )?;
    checked_sha(
        inputs.constants,
        TEXT_INPUT_CAP,
        CONSTANTS_SHA256,
        "constants",
    )?;
    checked_sha(
        inputs.curriculum,
        TEXT_INPUT_CAP,
        CURRICULUM_SHA256,
        "curriculum",
    )?;
    validate_canonical_manifest(inputs.content_fixture)
        .map_err(|_| error("noncanonical", "content_fixture"))?;
    validate_canonical_manifest(inputs.chess_fixture)
        .map_err(|_| error("noncanonical", "chess_fixture"))?;
    let identity = identity_hex(b"golden-board:game-set:v0\0", &[inputs.game_set])
        .map_err(|_| error("identity", "game_set"))?;
    if identity != GAME_SET_IDENTITY {
        return Err(error("identity", "game_set"));
    }
    Ok(())
}

fn take_u16(bytes: &[u8], cursor: &mut usize) -> Result<u16, SliceError> {
    let end = cursor
        .checked_add(2)
        .ok_or_else(|| error("game_set_shape", "game_set"))?;
    let pair = bytes
        .get(*cursor..end)
        .ok_or_else(|| error("game_set_shape", "game_set"))?;
    *cursor = end;
    Ok(u16::from_be_bytes([pair[0], pair[1]]))
}

fn parse_games(bytes: &[u8]) -> Result<Vec<Vec<u8>>, SliceError> {
    let mut cursor = 0;
    if take_u16(bytes, &mut cursor)? != 64 {
        return Err(error("game_count", "game_set"));
    }
    let mut games: Vec<Vec<u8>> = Vec::with_capacity(64);
    let mut total_plies = 0_usize;
    for _ in 0..64 {
        let start = cursor;
        let plies = usize::from(take_u16(bytes, &mut cursor)?);
        if !(1..=4096).contains(&plies) {
            return Err(error("game_ply_count", "game_set"));
        }
        total_plies = total_plies
            .checked_add(plies)
            .ok_or_else(|| error("game_ply_count", "game_set"))?;
        if total_plies > 65_535 {
            return Err(error("game_ply_count", "game_set"));
        }
        let end = cursor
            .checked_add(plies * 2)
            .and_then(|value| value.checked_add(1))
            .ok_or_else(|| error("game_set_shape", "game_set"))?;
        let complete = bytes
            .get(start..end)
            .ok_or_else(|| error("game_set_shape", "game_set"))?;
        let score = complete[complete.len() - 1];
        if score > 2 {
            return Err(error("game_score", "game_set"));
        }
        if games
            .last()
            .is_some_and(|prior| prior.as_slice() >= complete)
        {
            return Err(error("game_order", "game_set"));
        }
        games.push(complete.to_vec());
        cursor = end;
    }
    if cursor != bytes.len() {
        return Err(error("game_set_trailing", "game_set"));
    }
    Ok(games)
}

fn parse_base(bytes: &[u8]) -> Result<(Vec<u8>, ContentProjectionView), SliceError> {
    let fixture: Value =
        serde_json::from_slice(bytes).map_err(|_| error("bad_json", "content_fixture"))?;
    if string(
        member(&fixture, "schema", "content_fixture")?,
        "content_fixture",
    )? != "golden-board.content-v0-fixtures/v0"
    {
        return Err(error("fixture_schema", "content_fixture"));
    }
    let bases = array(
        member(&fixture, "bases", "content_fixture")?,
        "content_fixture",
    )?;
    let selected = bases
        .iter()
        .filter(|base| {
            member(base, "name", "content_fixture")
                .and_then(|value| string(value, "content_fixture"))
                == Ok("generic-base")
        })
        .collect::<Vec<_>>();
    if selected.len() != 1 {
        return Err(error("fixture_name", "content_fixture"));
    }
    let selected = selected[0];
    let keys = object(selected, "content_fixture")?
        .keys()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    if keys
        != BTreeSet::from([
            "name",
            "projection",
            "stream_hex",
            "stream_length",
            "stream_sha256",
        ])
    {
        return Err(error("fixture_base_shape", "content_fixture"));
    }
    if number(
        member(selected, "stream_length", "content_fixture")?,
        "content_fixture",
    )? != REQUIRED_STREAM_LENGTH as u64
        || string(
            member(selected, "stream_sha256", "content_fixture")?,
            "content_fixture",
        )? != REQUIRED_STREAM_SHA256
    {
        return Err(error("fixture_base_binding", "content_fixture"));
    }
    let projection_json = member(selected, "projection", "content_fixture")?;
    let projection_keys = object(projection_json, "content_fixture")?
        .keys()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    if projection_keys != BTreeSet::from(["records", "root_record_id", "version"])
        || number(
            member(projection_json, "version", "content_fixture")?,
            "content_fixture",
        )? != 0
        || number(
            member(projection_json, "root_record_id", "content_fixture")?,
            "content_fixture",
        )? != 29
        || array(
            member(projection_json, "records", "content_fixture")?,
            "content_fixture",
        )?
        .len()
            != 29
    {
        return Err(error("fixture_projection", "content_fixture"));
    }
    let stream = hex_bytes(
        string(
            member(selected, "stream_hex", "content_fixture")?,
            "content_fixture",
        )?,
        "content_fixture",
    )?;
    if stream.len() != REQUIRED_STREAM_LENGTH || sha256_hex(&stream) != REQUIRED_STREAM_SHA256 {
        return Err(error("fixture_stream", "content_fixture"));
    }
    let projection =
        stream_validation(&stream).map_err(|_| error("content_reject", "content_fixture"))?;
    let view = projection_view(&projection);
    if view.version() != 0
        || view.root_record_id() != 29
        || view.records().len() != 29
        || view.records().iter().map(Record::record_id).ne(1_u16..=29)
    {
        return Err(error("fixture_projection", "content_fixture"));
    }
    Ok((stream, view))
}

fn fixture_case<'a>(fixture: &'a Value, name: &str) -> Result<&'a Value, SliceError> {
    let cases = array(member(fixture, "cases", "chess_fixture")?, "chess_fixture")?;
    let found = cases
        .iter()
        .filter(|case| {
            member(case, "name", "chess_fixture").and_then(|value| string(value, "chess_fixture"))
                == Ok(name)
        })
        .collect::<Vec<_>>();
    if found.len() != 1 {
        return Err(error("fixture_case", "chess_fixture"));
    }
    Ok(found[0])
}

fn bool_byte(value: &Value) -> Result<u8, SliceError> {
    value
        .as_bool()
        .map(u8::from)
        .ok_or_else(|| error("fixture_value", "chess_fixture"))
}

fn u16_value(value: &Value) -> Result<u16, SliceError> {
    u16::try_from(number(value, "chess_fixture")?)
        .map_err(|_| error("fixture_value", "chess_fixture"))
}

fn ep_value(value: &Value) -> Result<(u8, u8), SliceError> {
    let object = object(value, "chess_fixture")?;
    match string(
        object
            .get("kind")
            .ok_or_else(|| error("fixture_value", "chess_fixture"))?,
        "chess_fixture",
    )? {
        "none" if object.len() == 1 => Ok((0, 0xff)),
        "square" if object.len() == 2 => {
            let square = object
                .get("square")
                .ok_or_else(|| error("fixture_value", "chess_fixture"))?;
            let square = u8::try_from(number(square, "chess_fixture")?)
                .map_err(|_| error("fixture_value", "chess_fixture"))?;
            if square >= 64 {
                return Err(error("fixture_value", "chess_fixture"));
            }
            Ok((1, square))
        }
        _ => Err(error("fixture_value", "chess_fixture")),
    }
}

fn fixture_payload(case: &Value, ordinal: u8) -> Result<Vec<u8>, SliceError> {
    let operation = string(member(case, "operation", "chess_fixture")?, "chess_fixture")?;
    let (prior, subject) = if operation == "apply_move" {
        let input = member(case, "input", "chess_fixture")?;
        let keys = object(input, "chess_fixture")?
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>();
        if keys != BTreeSet::from(["move_hex", "moves_hex"]) {
            return Err(error("fixture_input", "chess_fixture"));
        }
        (
            hex_bytes(
                string(
                    member(input, "moves_hex", "chess_fixture")?,
                    "chess_fixture",
                )?,
                "chess_fixture",
            )?,
            hex_bytes(
                string(member(input, "move_hex", "chess_fixture")?, "chess_fixture")?,
                "chess_fixture",
            )?,
        )
    } else if operation == "evaluate_predicate" {
        let input = member(case, "input", "chess_fixture")?;
        if string(
            member(input, "predicate_id", "chess_fixture")?,
            "chess_fixture",
        )? != "chess.history_claim"
        {
            return Err(error("fixture_input", "chess_fixture"));
        }
        let nested = member(input, "input", "chess_fixture")?;
        if string(member(nested, "variant", "chess_fixture")?, "chess_fixture")? != "history-claim"
        {
            return Err(error("fixture_input", "chess_fixture"));
        }
        (
            hex_bytes(
                string(
                    member(nested, "moves_hex", "chess_fixture")?,
                    "chess_fixture",
                )?,
                "chess_fixture",
            )?,
            Vec::new(),
        )
    } else {
        return Err(error("fixture_operation", "chess_fixture"));
    };
    if prior.len() % 2 != 0 || (operation == "apply_move" && subject.len() != 2) {
        return Err(error("fixture_wire", "chess_fixture"));
    }

    let expected = member(case, "expected", "chess_fixture")?;
    let mut expected_bytes = Vec::new();
    match ordinal {
        0 | 1 => {
            let success = member(expected, "success", "chess_fixture")?;
            let position = hex_bytes(
                string(
                    member(success, "position_hex", "chess_fixture")?,
                    "chess_fixture",
                )?,
                "chess_fixture",
            )?;
            if position.len() != 67 || object(success, "chess_fixture")?.len() != 1 {
                return Err(error("fixture_expected", "chess_fixture"));
            }
            expected_bytes.push(1);
            expected_bytes.extend(position);
        }
        2 => {
            let success = member(expected, "success", "chess_fixture")?;
            let position = hex_bytes(
                string(
                    member(success, "position_hex", "chess_fixture")?,
                    "chess_fixture",
                )?,
                "chess_fixture",
            )?;
            if position.len() != 67 || object(success, "chess_fixture")?.len() != 2 {
                return Err(error("fixture_expected", "chess_fixture"));
            }
            expected_bytes.push(2);
            expected_bytes.extend(
                u16_value(member(success, "halfmove_clock", "chess_fixture")?)?.to_be_bytes(),
            );
            expected_bytes.extend(position);
        }
        3..=6 => {
            let success = member(expected, "success", "chess_fixture")?;
            let position = hex_bytes(
                string(
                    member(success, "position_hex", "chess_fixture")?,
                    "chess_fixture",
                )?,
                "chess_fixture",
            )?;
            if position.len() != 67 || object(success, "chess_fixture")?.len() != 3 {
                return Err(error("fixture_expected", "chess_fixture"));
            }
            let terminal = u8::try_from(number(
                member(success, "terminal", "chess_fixture")?,
                "chess_fixture",
            )?)
            .map_err(|_| error("fixture_expected", "chess_fixture"))?;
            expected_bytes.push(3);
            expected_bytes.extend(position);
            expected_bytes.push(bool_byte(member(
                success,
                "king_in_check",
                "chess_fixture",
            )?)?);
            expected_bytes.push(terminal);
        }
        7 => {
            if object(expected, "chess_fixture")?.len() != 1 {
                return Err(error("fixture_expected", "chess_fixture"));
            }
            expected_bytes.push(4);
            expected_bytes
                .extend(u16_value(member(expected, "rejection", "chess_fixture")?)?.to_be_bytes());
        }
        8 | 9 => {
            let success = member(expected, "success", "chess_fixture")?;
            let result = member(success, "result", "chess_fixture")?;
            let (nominal_kind, nominal_square) =
                ep_value(member(result, "nominal_ep", "chess_fixture")?)?;
            let (effective_kind, effective_square) =
                ep_value(member(result, "effective_ep", "chess_fixture")?)?;
            expected_bytes.push(5);
            expected_bytes
                .extend(u16_value(member(result, "played_plies", "chess_fixture")?)?.to_be_bytes());
            expected_bytes.extend(
                u16_value(member(result, "halfmove_clock", "chess_fixture")?)?.to_be_bytes(),
            );
            expected_bytes.extend(
                u16_value(member(result, "current_key_occurrences", "chess_fixture")?)?
                    .to_be_bytes(),
            );
            expected_bytes.extend([
                nominal_kind,
                nominal_square,
                effective_kind,
                effective_square,
            ]);
            expected_bytes.push(bool_byte(member(
                result,
                "fifty_move_available",
                "chess_fixture",
            )?)?);
            expected_bytes.push(bool_byte(member(
                result,
                "threefold_available",
                "chess_fixture",
            )?)?);
        }
        _ => return Err(error("fixture_ordinal", "chess_fixture")),
    }
    let prior_len =
        u16::try_from(prior.len()).map_err(|_| error("fixture_wire", "chess_fixture"))?;
    let subject_len =
        u16::try_from(subject.len()).map_err(|_| error("fixture_wire", "chess_fixture"))?;
    let expected_len =
        u16::try_from(expected_bytes.len()).map_err(|_| error("fixture_wire", "chess_fixture"))?;
    let mut payload = Vec::with_capacity(8 + prior.len() + subject.len() + expected_bytes.len());
    payload.extend([0, ordinal + 1]);
    payload.extend(prior_len.to_be_bytes());
    payload.extend(prior);
    payload.extend(subject_len.to_be_bytes());
    payload.extend(subject);
    payload.extend(expected_len.to_be_bytes());
    payload.extend(expected_bytes);
    Ok(payload)
}

fn parse_fixture_payloads(bytes: &[u8]) -> Result<Vec<Vec<u8>>, SliceError> {
    let fixture: Value =
        serde_json::from_slice(bytes).map_err(|_| error("bad_json", "chess_fixture"))?;
    if string(
        member(&fixture, "schema", "chess_fixture")?,
        "chess_fixture",
    )? != "golden-board.chess-v0-fixtures/v0"
    {
        return Err(error("fixture_schema", "chess_fixture"));
    }
    let names = [
        "castling-positive-first-kingside",
        "castling-positive-first-queenside",
        "en-passant-legal-capture",
        "promotion-quiet-queen",
        "promotion-quiet-rook",
        "promotion-quiet-bishop",
        "promotion-quiet-knight",
        "geometry-illegal-self-check",
        "en-passant-nominal-without-capturer",
        "en-passant-effective-key-retained",
    ];
    let payloads = names
        .iter()
        .enumerate()
        .map(|(ordinal, name)| fixture_payload(fixture_case(&fixture, name)?, ordinal as u8))
        .collect::<Result<Vec<_>, _>>()?;
    if payloads.iter().map(Vec::len).sum::<usize>() != 741 {
        return Err(error("fixture_payload_total", "chess_fixture"));
    }
    Ok(payloads)
}

fn validate_curriculum(bytes: &[u8]) -> Result<(), SliceError> {
    let text = std::str::from_utf8(bytes).map_err(|_| error("curriculum_utf8", "curriculum"))?;
    let value: toml::Value =
        toml::from_str(text).map_err(|_| error("curriculum_toml", "curriculum"))?;
    if value.get("schema").and_then(toml::Value::as_str) != Some("golden-board.curriculum/v0") {
        return Err(error("curriculum_schema", "curriculum"));
    }
    let concepts = value
        .get("concept")
        .and_then(toml::Value::as_array)
        .ok_or_else(|| error("curriculum_shape", "curriculum"))?;
    let mut family_ids = BTreeSet::new();
    for concept in concepts {
        let table = concept
            .as_table()
            .ok_or_else(|| error("curriculum_shape", "curriculum"))?;
        if table.get("family_concept").and_then(toml::Value::as_bool) == Some(true) {
            let id = table
                .get("id")
                .and_then(toml::Value::as_str)
                .ok_or_else(|| error("curriculum_shape", "curriculum"))?;
            if !family_ids.insert(id) {
                return Err(error("curriculum_duplicate", "curriculum"));
            }
        }
    }
    let selected = [
        "setup_turn",
        "ordinary_move_capture",
        "control_vs_legal",
        "king_safety",
        "castling",
        "en_passant",
        "promotion",
        "position_history_draw",
        "record_replay",
    ];
    if selected.iter().any(|id| !family_ids.contains(id)) {
        return Err(error("curriculum_family", "curriculum"));
    }
    Ok(())
}

fn validate_base_bindings(view: &ContentProjectionView) -> Result<(), SliceError> {
    let capacity_ids = [1_u16, 6, 9, 12, 13, 14, 15, 16, 17, 19, 20, 25, 26, 29];
    for (index, id) in capacity_ids.into_iter().enumerate() {
        let record = view
            .records()
            .iter()
            .find(|record| record.record_id() == id)
            .ok_or_else(|| error("capacity_record", "content_fixture"))?;
        if record.kind() != u16::try_from(index + 1).unwrap() {
            return Err(error("capacity_kind", "content_fixture"));
        }
    }
    let matrix = view
        .records()
        .iter()
        .find(|record| record.record_id() == 12)
        .ok_or_else(|| error("asymmetry_matrix", "content_fixture"))?;
    match matrix.payload() {
        RecordPayload::Matrix {
            atom_schema_ref,
            rows,
            columns,
            cells,
        } if *atom_schema_ref == 6
            && *rows == 2
            && *columns == 3
            && cells.as_slice() == [0, 1, 2, 3, 4, 5] => {}
        _ => return Err(error("asymmetry_matrix", "content_fixture")),
    }
    let schema = view
        .records()
        .iter()
        .find(|record| record.record_id() == 6)
        .ok_or_else(|| error("asymmetry_domain", "content_fixture"))?;
    match schema.payload() {
        RecordPayload::AtomSchema {
            atom_class,
            atom_width,
            entries,
            min_value,
            max_value,
            allowed_mask,
        } if *atom_class == ATOM_UNSIGNED
            && *atom_width == 1
            && entries.is_empty()
            && *min_value == Some(0)
            && *max_value == Some(5)
            && allowed_mask.is_none() => {}
        _ => return Err(error("asymmetry_domain", "content_fixture")),
    }
    let regions = view
        .records()
        .iter()
        .find(|record| record.record_id() == 15)
        .ok_or_else(|| error("asymmetry_regions", "content_fixture"))?;
    match regions.payload() {
        RecordPayload::RegionSet {
            surface_matrix_ref,
            regions,
        } if *surface_matrix_ref == 12
            && regions.iter().map(|region| region.region_id).eq(1_u16..=3) => {}
        _ => return Err(error("asymmetry_regions", "content_fixture")),
    }
    Ok(())
}

fn byte_data(bytes: &[u8]) -> Vec<u32> {
    bytes.iter().copied().map(u32::from).collect()
}

fn build_all_records(
    base: &ContentProjectionView,
    games: &[Vec<u8>],
    fixtures: &[Vec<u8>],
) -> Result<Vec<Record>, SliceError> {
    if games.len() != 64 || fixtures.len() != 10 {
        return Err(error("payload_count", "records"));
    }
    let mut records = base.records()[..28].to_vec();
    records.push(Record::authoring(
        29,
        RecordPayload::AtomSchema {
            atom_class: ATOM_UNSIGNED,
            atom_width: 1,
            entries: Vec::new(),
            min_value: Some(0),
            max_value: Some(255),
            allowed_mask: None,
        },
    ));
    for (ordinal, game) in games.iter().enumerate() {
        let ordinal = u16::try_from(ordinal).unwrap();
        let binding_id = 30 + ordinal * 2;
        let auxiliary =
            u16::try_from(game.len()).map_err(|_| error("game_payload_length", "records"))?;
        records.push(Record::authoring(
            binding_id,
            RecordPayload::SemanticBinding {
                binding_class: BINDING_DATA,
                namespace_id: 2,
                semantic_code: ordinal + 1,
                argument: 29,
                auxiliary,
            },
        ));
        records.push(Record::authoring(
            binding_id + 1,
            RecordPayload::OpaqueData {
                data_binding_ref: binding_id,
                data: byte_data(game),
            },
        ));
    }
    for (ordinal, payload) in fixtures.iter().enumerate() {
        let ordinal = u16::try_from(ordinal).unwrap();
        let binding_id = 158 + ordinal * 2;
        let auxiliary =
            u16::try_from(payload.len()).map_err(|_| error("fixture_payload_length", "records"))?;
        records.push(Record::authoring(
            binding_id,
            RecordPayload::SemanticBinding {
                binding_class: BINDING_DATA,
                namespace_id: 3,
                semantic_code: ordinal + 1,
                argument: 29,
                auxiliary,
            },
        ));
        records.push(Record::authoring(
            binding_id + 1,
            RecordPayload::OpaqueData {
                data_binding_ref: binding_id,
                data: byte_data(payload),
            },
        ));
    }
    let opaque_refs = (0_u16..64)
        .map(|ordinal| 31 + ordinal * 2)
        .chain((0_u16..10).map(|ordinal| 159 + ordinal * 2))
        .collect::<Vec<_>>();
    records.push(Record::authoring(
        178,
        RecordPayload::FieldSchema {
            fields: vec![FieldSpec {
                name_text_ref: 3,
                storage: FIELD_RECORD_REF,
                type_code: 9,
                count: 74,
            }],
        },
    ));
    records.push(Record::authoring(
        179,
        RecordPayload::Tuple {
            field_schema_ref: 178,
            field_values: vec![FieldValue::RecordRefs(opaque_refs)],
        },
    ));
    records.push(Record::authoring(
        180,
        RecordPayload::Feedback {
            feedback_code: FEEDBACK_NEUTRAL,
            display_ref: 179,
            predicate_result_ref: 0,
        },
    ));
    records.push(Record::authoring(
        181,
        RecordPayload::LessonNode {
            role: ROLE_PRACTICE,
            response_shape: RESPONSE_SINGLE,
            answer_mode: ANSWER_EXTERNAL,
            flags: 0,
            presentation_ref: 12,
            region_set_ref: 15,
            predicate_result_ref: 0,
            passive_trace_ref: 0,
            max_selections: 1,
            item_event_budget: 2,
            cases: Vec::<LessonCase>::new(),
            default_feedback_ref: 180,
            default_next_node_ref: 26,
        },
    ));
    records.push(Record::authoring(
        182,
        RecordPayload::Root {
            entry_node_ref: 181,
            global_event_budget: 10,
        },
    ));
    if records.len() != 182 || records.iter().map(Record::record_id).ne(1_u16..=182) {
        return Err(error("record_order", "records"));
    }
    Ok(records)
}

fn stream_frames(stream: &[u8]) -> Result<(u16, BTreeMap<u16, Vec<u8>>), SliceError> {
    if stream.len() < 4 {
        return Err(error("stream_shape", "stream"));
    }
    let version = u16::from_be_bytes([stream[0], stream[1]]);
    let count = u16::from_be_bytes([stream[2], stream[3]]);
    if version != CONTENT_VERSION as u16 {
        return Err(error("stream_version", "stream"));
    }
    let mut cursor = 4_usize;
    let mut frames = BTreeMap::new();
    for _ in 0..count {
        let header = stream
            .get(cursor..cursor + 8)
            .ok_or_else(|| error("stream_shape", "stream"))?;
        let id = u16::from_be_bytes([header[0], header[1]]);
        let payload_len = u32::from_be_bytes([header[4], header[5], header[6], header[7]]) as usize;
        let end = cursor
            .checked_add(8)
            .and_then(|value| value.checked_add(payload_len))
            .ok_or_else(|| error("stream_shape", "stream"))?;
        let frame = stream
            .get(cursor..end)
            .ok_or_else(|| error("stream_shape", "stream"))?;
        if frames.insert(id, frame.to_vec()).is_some() {
            return Err(error("stream_duplicate", "stream"));
        }
        cursor = end;
    }
    if cursor != stream.len() || frames.len() != usize::from(count) {
        return Err(error("stream_trailing", "stream"));
    }
    Ok((count, frames))
}

fn assemble_frames(
    count: u16,
    body_ids: impl IntoIterator<Item = u16>,
    root_id: u16,
    frames: &BTreeMap<u16, Vec<u8>>,
) -> Result<Vec<u8>, SliceError> {
    let mut output = Vec::new();
    output.extend((CONTENT_VERSION as u16).to_be_bytes());
    output.extend(count.to_be_bytes());
    for id in body_ids.into_iter().chain(std::iter::once(root_id)) {
        output.extend(
            frames
                .get(&id)
                .ok_or_else(|| error("section_record", "sections"))?,
        );
    }
    Ok(output)
}

fn assignments() -> Vec<AtomicAssignment> {
    let mut result = vec![AtomicAssignment {
        closure: Closure::Required,
        section_id: 16,
        semantic_copy_id: 0,
        record_ids: (1_u16..=28).collect(),
    }];
    result.push(AtomicAssignment {
        closure: Closure::AllOnly,
        section_id: 17,
        semantic_copy_id: 0,
        record_ids: vec![29],
    });
    result.extend((0_u16..64).map(|ordinal| AtomicAssignment {
        closure: Closure::AllOnly,
        section_id: 100 + ordinal,
        semantic_copy_id: 0,
        record_ids: vec![30 + ordinal * 2, 31 + ordinal * 2],
    }));
    result.extend((0_u16..10).map(|ordinal| AtomicAssignment {
        closure: Closure::AllOnly,
        section_id: 200 + ordinal,
        semantic_copy_id: 0,
        record_ids: vec![158 + ordinal * 2, 159 + ordinal * 2],
    }));
    result.push(AtomicAssignment {
        closure: Closure::AllOnly,
        section_id: 210,
        semantic_copy_id: 0,
        record_ids: vec![178, 179, 180, 181],
    });
    result
}

fn validate_assignment_coverage(assignments: &[AtomicAssignment]) -> Result<(), SliceError> {
    if assignments.len() != 77
        || assignments
            .iter()
            .any(|assignment| assignment.semantic_copy_id != 0)
        || assignments
            .windows(2)
            .any(|pair| pair[0].section_id >= pair[1].section_id)
    {
        return Err(error("assignment_order", "sections"));
    }
    let ids = assignments
        .iter()
        .flat_map(|assignment| assignment.record_ids.iter().copied())
        .collect::<Vec<_>>();
    if ids.into_iter().ne(1_u16..=181) {
        return Err(error("assignment_coverage", "sections"));
    }
    Ok(())
}

/// Compile and validate the two reviewed M2 semantic tiers from seven explicit inputs.
pub fn compile_slice_v0(inputs: SliceInputs<'_>) -> Result<SliceCompilation, SliceError> {
    parse_declaration(inputs.declaration)?;
    validate_inputs(inputs)?;
    validate_curriculum(inputs.curriculum)?;
    let games = parse_games(inputs.game_set)?;
    let fixtures = parse_fixture_payloads(inputs.chess_fixture)?;
    let (required_stream, base) = parse_base(inputs.content_fixture)?;
    validate_base_bindings(&base)?;

    let required_authoring =
        authoring_from_validated(&base).map_err(|_| error("authoring", "required"))?;
    let required_encoded =
        encode_content_v0(&required_authoring).map_err(|_| error("content_reject", "required"))?;
    if required_encoded != required_stream
        || required_stream.len() != REQUIRED_STREAM_LENGTH
        || sha256_hex(&required_stream) != REQUIRED_STREAM_SHA256
    {
        return Err(error("tier_bytes", "required"));
    }

    let all_records = build_all_records(&base, &games, &fixtures)?;
    let all_authoring = ContentAuthoringProjection::new(CONTENT_VERSION as u16, all_records);
    let all_stream =
        encode_content_v0(&all_authoring).map_err(|_| error("content_reject", "all"))?;
    if all_stream.len() != ALL_STREAM_LENGTH || sha256_hex(&all_stream) != ALL_STREAM_SHA256 {
        return Err(error("tier_bytes", "all"));
    }
    let all_projection =
        stream_validation(&all_stream).map_err(|_| error("content_reject", "all"))?;
    let all_view = projection_view(&all_projection);
    if all_view.records().len() != 182
        || all_view.root_record_id() != 182
        || all_view
            .records()
            .iter()
            .map(Record::record_id)
            .ne(1_u16..=182)
    {
        return Err(error("tier_projection", "all"));
    }

    let assignments = assignments();
    validate_assignment_coverage(&assignments)?;
    let (required_count, required_frames) = stream_frames(&required_stream)?;
    let required_reassembled = assemble_frames(required_count, 1_u16..=28, 29, &required_frames)?;
    if required_count != 29 || required_reassembled != required_stream {
        return Err(error("tier_reassembly", "required"));
    }
    stream_validation(&required_reassembled).map_err(|_| error("content_reject", "required"))?;
    let capacity_ids = [1_u16, 6, 9, 12, 13, 14, 15, 16, 17, 19, 20, 25, 26, 29];
    let expected_lengths = [15_u16, 14, 14, 20, 34, 19, 54, 18, 11, 14, 14, 28, 58, 12];
    let capacity_prototypes = capacity_ids
        .into_iter()
        .enumerate()
        .map(|(index, source_record_id)| {
            let frame_length = required_frames
                .get(&source_record_id)
                .and_then(|frame| u16::try_from(frame.len()).ok())
                .ok_or_else(|| error("capacity_frame", "required"))?;
            if frame_length != expected_lengths[index] {
                return Err(error("capacity_frame", "required"));
            }
            Ok(CapacityPrototype {
                kind: u16::try_from(index + 1).unwrap(),
                prototype_id: format!("generic-base-kind-{:02}", index + 1),
                source_record_id,
                frame_length,
            })
        })
        .collect::<Result<Vec<_>, SliceError>>()?;

    let (all_count, all_frames) = stream_frames(&all_stream)?;
    let all_body_ids = assignments
        .iter()
        .flat_map(|assignment| assignment.record_ids.iter().copied());
    let all_reassembled = assemble_frames(all_count, all_body_ids, 182, &all_frames)?;
    if all_count != 182 || all_reassembled != all_stream {
        return Err(error("tier_reassembly", "all"));
    }
    stream_validation(&all_reassembled).map_err(|_| error("content_reject", "all"))?;

    let required_root = required_frames
        .get(&29)
        .ok_or_else(|| error("tier_root", "required"))?
        .clone();
    let all_root = all_frames
        .get(&182)
        .ok_or_else(|| error("tier_root", "all"))?
        .clone();
    if required_root.len() != 12
        || all_root.len() != 12
        || u16::from_be_bytes([required_root[2], required_root[3]]) != CONTENT_KIND_ROOT
        || u16::from_be_bytes([all_root[2], all_root[3]]) != CONTENT_KIND_ROOT
    {
        return Err(error("tier_root", "sections"));
    }
    let tier_roots = vec![
        TierRoot {
            closure: Closure::Required,
            section_id: 2,
            semantic_copy_id: 0,
            record_id: 29,
            frame: required_root,
        },
        TierRoot {
            closure: Closure::All,
            section_id: 3,
            semantic_copy_id: 0,
            record_id: 182,
            frame: all_root,
        },
    ];
    Ok(SliceCompilation {
        required_projection: base,
        all_projection: all_view,
        required_stream,
        all_stream,
        game_payloads: games,
        fixture_payloads: fixtures,
        assignments,
        tier_roots,
        capacity_prototypes,
    })
}
