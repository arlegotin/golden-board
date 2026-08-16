use std::collections::{BTreeMap, BTreeSet};
use std::rc::Rc;

use gb_foundation::constants::*;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ContentReject {
    pub code: u16,
    pub raw_start: u32,
    pub raw_end: u32,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct InvalidHostState;

type Result<T> = std::result::Result<T, ContentReject>;

fn reject(code: u16, start: usize, end: usize) -> ContentReject {
    ContentReject {
        code,
        raw_start: start as u32,
        raw_end: end as u32,
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AtomEntry {
    pub code: u32,
    pub label_text_ref: u16,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FieldSpec {
    pub name_text_ref: u16,
    pub storage: u8,
    pub type_code: u16,
    pub count: u16,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum FieldValue {
    Atoms(Vec<u32>),
    RecordRefs(Vec<u16>),
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Region {
    pub region_id: u16,
    pub label_ref: u16,
    pub row_start: u16,
    pub row_end: u16,
    pub column_start: u16,
    pub column_end: u16,
    pub flags: u8,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LessonCase {
    pub case_class: u8,
    pub region_ids: Vec<u16>,
    pub feedback_ref: u16,
    pub next_node_ref: u16,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RecordPayload {
    Text(String),
    AtomSchema {
        atom_class: u8,
        atom_width: u8,
        entries: Vec<AtomEntry>,
        min_value: Option<u32>,
        max_value: Option<u32>,
        allowed_mask: Option<u32>,
    },
    AtomVector {
        atom_schema_ref: u16,
        atoms: Vec<u32>,
    },
    Matrix {
        atom_schema_ref: u16,
        rows: u16,
        columns: u16,
        cells: Vec<u32>,
    },
    FieldSchema {
        fields: Vec<FieldSpec>,
    },
    Tuple {
        field_schema_ref: u16,
        field_values: Vec<FieldValue>,
    },
    RegionSet {
        surface_matrix_ref: u16,
        regions: Vec<Region>,
    },
    SemanticBinding {
        binding_class: u8,
        namespace_id: u16,
        semantic_code: u16,
        argument: u16,
        auxiliary: u16,
    },
    OpaqueData {
        data_binding_ref: u16,
        data: Vec<u32>,
    },
    PredicateResult {
        predicate_binding_ref: u16,
        subject_opaque_data_ref: u16,
        result_atom_vector_ref: u16,
    },
    Feedback {
        feedback_code: u16,
        display_ref: u16,
        predicate_result_ref: u16,
    },
    PassiveTrace {
        presentation_ref: u16,
        region_set_ref: u16,
        resulting_presentation_ref: u16,
        limitation_text_ref: u16,
        actions: Vec<[u8; 4]>,
        expected_outcome: u8,
        expected_feedback_ref: u16,
        expected_next_node_ref: u16,
    },
    LessonNode {
        role: u8,
        response_shape: u8,
        answer_mode: u8,
        flags: u8,
        presentation_ref: u16,
        region_set_ref: u16,
        predicate_result_ref: u16,
        passive_trace_ref: u16,
        max_selections: u16,
        item_event_budget: u16,
        cases: Vec<LessonCase>,
        default_feedback_ref: u16,
        default_next_node_ref: u16,
    },
    Root {
        entry_node_ref: u16,
        global_event_budget: u16,
    },
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Record {
    record_id: u16,
    payload: RecordPayload,
}

impl Record {
    pub fn record_id(&self) -> u16 {
        self.record_id
    }

    pub fn kind(&self) -> u16 {
        payload_kind(&self.payload)
    }

    pub fn payload(&self) -> &RecordPayload {
        &self.payload
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ContentProjection {
    version: u16,
    root_record_id: u16,
    records: Vec<Record>,
}

impl ContentProjection {
    pub fn version(&self) -> u16 {
        self.version
    }

    pub fn root_record_id(&self) -> u16 {
        self.root_record_id
    }

    pub fn records(&self) -> &[Record] {
        &self.records
    }
}

fn payload_kind(payload: &RecordPayload) -> u16 {
    match payload {
        RecordPayload::Text(_) => CONTENT_KIND_TEXT,
        RecordPayload::AtomSchema { .. } => CONTENT_KIND_ATOM_SCHEMA,
        RecordPayload::AtomVector { .. } => CONTENT_KIND_ATOM_VECTOR,
        RecordPayload::Matrix { .. } => CONTENT_KIND_MATRIX,
        RecordPayload::FieldSchema { .. } => CONTENT_KIND_FIELD_SCHEMA,
        RecordPayload::Tuple { .. } => CONTENT_KIND_TUPLE,
        RecordPayload::RegionSet { .. } => CONTENT_KIND_REGION_SET,
        RecordPayload::SemanticBinding { .. } => CONTENT_KIND_SEMANTIC_BINDING,
        RecordPayload::OpaqueData { .. } => CONTENT_KIND_OPAQUE_DATA,
        RecordPayload::PredicateResult { .. } => CONTENT_KIND_PREDICATE_RESULT,
        RecordPayload::Feedback { .. } => CONTENT_KIND_FEEDBACK,
        RecordPayload::PassiveTrace { .. } => CONTENT_KIND_PASSIVE_TRACE,
        RecordPayload::LessonNode { .. } => CONTENT_KIND_LESSON_NODE,
        RecordPayload::Root { .. } => CONTENT_KIND_ROOT,
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Span {
    start: usize,
    end: usize,
}

#[derive(Clone, Copy, Debug)]
struct RawRecord {
    id: u16,
    kind: u16,
    header_start: usize,
    length_span: Span,
    payload: Span,
}

#[derive(Clone, Copy, Debug)]
enum Wanted {
    Kind(u16),
    Display,
    Presentation,
    BindingData,
    BindingPredicate,
}

#[derive(Clone, Copy, Debug)]
struct RefField {
    value: u16,
    span: Span,
    wanted: Wanted,
    optional: bool,
}

#[derive(Clone, Copy, Debug)]
struct ControlField {
    value: u16,
    span: Span,
}

#[derive(Clone, Debug, Default)]
struct Meta {
    refs: Vec<RefField>,
    controls: Vec<ControlField>,
    detail: Detail,
}

#[derive(Clone, Debug, Default)]
enum Detail {
    #[default]
    None,
    AtomVector {
        count: u16,
        data_start: usize,
    },
    Matrix {
        data_start: usize,
    },
    FieldSchema {
        fields: Vec<FieldMeta>,
    },
    Tuple {
        data_start: usize,
    },
    RegionSet {
        regions: Vec<RegionMeta>,
    },
    OpaqueData {
        data_start: usize,
    },
    PredicateResult {
        result_span: Span,
    },
    Feedback {
        predicate_span: Span,
    },
    PassiveTrace {
        limitation_span: Span,
        action_count_span: Span,
        actions_start: usize,
        outcome_span: Span,
        feedback_span: Span,
        next_span: Span,
    },
    LessonNode(LessonMeta),
    Root {
        budget_span: Span,
    },
}

#[derive(Clone, Copy, Debug)]
struct FieldMeta {
    name_span: Span,
}

#[derive(Clone, Copy, Debug)]
struct RegionMeta {
    id_span: Span,
    row_end_span: Span,
    column_end_span: Span,
}

#[derive(Clone, Debug)]
struct LessonMeta {
    mode_span: Span,
    flags_span: Span,
    predicate_span: Span,
    trace_span: Span,
    max_span: Span,
    budget_span: Span,
    case_count_span: Span,
    cases: Vec<CaseMeta>,
    default_feedback_span: Span,
}

#[derive(Clone, Debug)]
struct CaseMeta {
    count_span: Span,
    region_spans: Vec<Span>,
    feedback_span: Span,
    next_span: Span,
}

#[derive(Clone, Debug)]
struct DecodedRecord {
    record: Record,
    raw: RawRecord,
    meta: Meta,
}

struct Cursor<'a> {
    raw: &'a [u8],
    at: usize,
    end: usize,
}

impl<'a> Cursor<'a> {
    fn new(raw: &'a [u8], span: Span) -> Self {
        Self {
            raw,
            at: span.start,
            end: span.end,
        }
    }

    fn remaining(&self) -> usize {
        self.end - self.at
    }

    fn span(&mut self, width: usize) -> Option<Span> {
        let end = self.at.checked_add(width)?;
        if end > self.end {
            return None;
        }
        let span = Span {
            start: self.at,
            end,
        };
        self.at = end;
        Some(span)
    }

    fn u8(&mut self) -> Option<(u8, Span)> {
        let span = self.span(1)?;
        Some((self.raw[span.start], span))
    }

    fn u16(&mut self) -> Option<(u16, Span)> {
        let span = self.span(2)?;
        Some((
            u16::from_be_bytes([self.raw[span.start], self.raw[span.start + 1]]),
            span,
        ))
    }
}

fn known_kind(kind: u16) -> bool {
    (CONTENT_KIND_TEXT..=CONTENT_KIND_ROOT).contains(&kind)
}

fn stage3_shape(kind: u16, length: usize) -> bool {
    match kind {
        CONTENT_KIND_TEXT => length >= 1,
        CONTENT_KIND_ATOM_SCHEMA => length >= 5,
        CONTENT_KIND_ATOM_VECTOR => length >= 4,
        CONTENT_KIND_MATRIX => length >= 7,
        CONTENT_KIND_FIELD_SCHEMA => length >= 10,
        CONTENT_KIND_TUPLE => length >= 3,
        CONTENT_KIND_REGION_SET => length >= 18,
        CONTENT_KIND_SEMANTIC_BINDING => length == 10,
        CONTENT_KIND_OPAQUE_DATA => length >= 3,
        CONTENT_KIND_PREDICATE_RESULT | CONTENT_KIND_FEEDBACK => length == 6,
        CONTENT_KIND_PASSIVE_TRACE => length >= 20,
        CONTENT_KIND_LESSON_NODE => length >= 22,
        CONTENT_KIND_ROOT => length == 4,
        _ => false,
    }
}

fn frame(raw: &[u8]) -> Result<Vec<RawRecord>> {
    if raw.len() > CONTENT_MAX_STREAM_BYTES as usize {
        let start = CONTENT_MAX_STREAM_BYTES as usize;
        return Err(reject(CONTENT_LIMIT_EXCEEDED, start, start + 1));
    }
    if raw.len() < 4 {
        return Err(reject(CONTENT_TRUNCATED, raw.len(), raw.len()));
    }
    let version = u16::from_be_bytes([raw[0], raw[1]]);
    let count = u16::from_be_bytes([raw[2], raw[3]]) as usize;
    if version != CONTENT_VERSION as u16 {
        return Err(reject(CONTENT_BAD_VERSION, 0, 2));
    }
    if !(CONTENT_MIN_RECORDS as usize..=CONTENT_MAX_RECORDS as usize).contains(&count) {
        return Err(reject(CONTENT_BAD_RECORD_COUNT, 2, 4));
    }

    let mut at = 4usize;
    let mut previous = 0u16;
    let mut per_kind = [0usize; 15];
    let mut records = Vec::with_capacity(count.min(raw.len() / 8));
    for _ in 0..count {
        if raw.len().saturating_sub(at) < 8 {
            return Err(reject(CONTENT_TRUNCATED, raw.len(), raw.len()));
        }
        let id = u16::from_be_bytes([raw[at], raw[at + 1]]);
        let kind = u16::from_be_bytes([raw[at + 2], raw[at + 3]]);
        let length =
            u32::from_be_bytes([raw[at + 4], raw[at + 5], raw[at + 6], raw[at + 7]]) as usize;
        if id == 0 {
            return Err(reject(CONTENT_BAD_RECORD_ID, at, at + 2));
        }
        if id <= previous {
            return Err(reject(CONTENT_RECORD_ORDER, at, at + 2));
        }
        if !known_kind(kind) {
            return Err(reject(CONTENT_BAD_RECORD_KIND, at + 2, at + 4));
        }
        if length > CONTENT_MAX_PAYLOAD_BYTES as usize
            || (kind == CONTENT_KIND_TEXT && length > CONTENT_MAX_TEXT_BYTES as usize)
        {
            return Err(reject(CONTENT_LIMIT_EXCEEDED, at + 4, at + 8));
        }
        if kind != CONTENT_KIND_ROOT {
            per_kind[kind as usize] += 1;
            if per_kind[kind as usize] > CONTENT_MAX_RECORDS_PER_NON_ROOT_KIND as usize {
                return Err(reject(CONTENT_LIMIT_EXCEEDED, at + 2, at + 4));
            }
        }
        let payload_start = at + 8;
        let Some(payload_end) = payload_start.checked_add(length) else {
            return Err(reject(CONTENT_LIMIT_EXCEEDED, at + 4, at + 8));
        };
        if payload_end > raw.len() {
            return Err(reject(CONTENT_TRUNCATED, raw.len(), raw.len()));
        }
        if !stage3_shape(kind, length) {
            return Err(reject(CONTENT_BAD_PAYLOAD_LENGTH, at + 4, at + 8));
        }
        records.push(RawRecord {
            id,
            kind,
            header_start: at,
            length_span: Span {
                start: at + 4,
                end: at + 8,
            },
            payload: Span {
                start: payload_start,
                end: payload_end,
            },
        });
        previous = id;
        at = payload_end;
    }
    if at < raw.len() {
        return Err(reject(CONTENT_TRAILING_DATA, at, at + 1));
    }
    Ok(records)
}

fn read_atom(raw: &[u8], span: Span, _width: u8) -> u32 {
    raw[span.start..span.end]
        .iter()
        .fold(0u32, |value, byte| (value << 8) | *byte as u32)
}

fn exact_length(record: RawRecord, expected: usize) -> Result<()> {
    if record.payload.end - record.payload.start != expected {
        Err(reject(
            CONTENT_BAD_PAYLOAD_LENGTH,
            record.length_span.start,
            record.length_span.end,
        ))
    } else {
        Ok(())
    }
}

fn decode_text(raw: &[u8], record: RawRecord) -> Result<(RecordPayload, Meta)> {
    let bytes = &raw[record.payload.start..record.payload.end];
    let text = match std::str::from_utf8(bytes) {
        Ok(text) => text,
        Err(error) => {
            let start = record.payload.start + error.valid_up_to();
            let end = error
                .error_len()
                .map_or(record.payload.end, |length| start + length.min(1));
            return Err(reject(CONTENT_BAD_UTF8, start, end));
        }
    };
    for (offset, character) in text.char_indices() {
        if (character <= '\u{1f}' && character != '\n')
            || character == '\r'
            || character == '\u{7f}'
            || ('\u{80}'..='\u{9f}').contains(&character)
            || (offset == 0 && character == '\u{feff}')
        {
            let start = record.payload.start + offset;
            return Err(reject(
                CONTENT_BAD_VALUE,
                start,
                start + character.len_utf8(),
            ));
        }
    }
    Ok((RecordPayload::Text(text.to_owned()), Meta::default()))
}

fn decode_atom_schema(raw: &[u8], record: RawRecord) -> Result<(RecordPayload, Meta)> {
    let mut cursor = Cursor::new(raw, record.payload);
    let (class, class_span) = cursor.u8().unwrap();
    let (width, width_span) = cursor.u8().unwrap();
    let (count, count_span) = cursor.u16().unwrap();
    if !matches!(class, ATOM_UNSIGNED | ATOM_ENUM | ATOM_MASK) {
        return Err(reject(CONTENT_BAD_TAG, class_span.start, class_span.end));
    }
    if !matches!(width, 1 | 2 | 4) {
        return Err(reject(CONTENT_BAD_TAG, width_span.start, width_span.end));
    }
    if class == ATOM_UNSIGNED && count != 0 {
        return Err(reject(CONTENT_BAD_COUNT, count_span.start, count_span.end));
    }
    if class == ATOM_ENUM && count == 0 {
        return Err(reject(CONTENT_BAD_COUNT, count_span.start, count_span.end));
    }
    if count as usize > CONTENT_MAX_ENUM_ENTRIES as usize {
        return Err(reject(
            CONTENT_LIMIT_EXCEEDED,
            count_span.start,
            count_span.end,
        ));
    }
    let expected = match class {
        ATOM_UNSIGNED => 4 + 2 * width as usize,
        ATOM_ENUM => 4 + count as usize * (width as usize + 2),
        ATOM_MASK => 4 + width as usize + count as usize * (width as usize + 2),
        _ => unreachable!(),
    };
    exact_length(record, expected)?;

    if class == ATOM_UNSIGNED {
        let min_span = cursor.span(width as usize).unwrap();
        let max_span = cursor.span(width as usize).unwrap();
        let min_value = read_atom(raw, min_span, width);
        let max_value = read_atom(raw, max_span, width);
        if min_value > max_value {
            return Err(reject(CONTENT_BAD_VALUE, max_span.start, max_span.end));
        }
        return Ok((
            RecordPayload::AtomSchema {
                atom_class: class,
                atom_width: width,
                entries: Vec::new(),
                min_value: Some(min_value),
                max_value: Some(max_value),
                allowed_mask: None,
            },
            Meta::default(),
        ));
    }

    let first_value = if class == ATOM_MASK {
        let first = cursor.span(width as usize).unwrap();
        read_atom(raw, first, width)
    } else {
        0
    };
    if class == ATOM_MASK && first_value.count_ones() != count as u32 {
        return Err(reject(CONTENT_BAD_COUNT, count_span.start, count_span.end));
    }
    let mut entries = Vec::with_capacity(count as usize);
    let mut entry_spans = Vec::with_capacity(count as usize);
    let mut previous = None;
    for _ in 0..count {
        let code_span = cursor.span(width as usize).unwrap();
        let code = read_atom(raw, code_span, width);
        let (label, label_span) = cursor.u16().unwrap();
        if let Some(prior) = previous {
            if code < prior {
                return Err(reject(
                    CONTENT_NONCANONICAL_ORDER,
                    code_span.start,
                    code_span.end,
                ));
            }
            if code == prior {
                return Err(reject(CONTENT_DUPLICATE, code_span.start, code_span.end));
            }
        }
        if class == ATOM_MASK && (code == 0 || !code.is_power_of_two() || code & !first_value != 0)
        {
            return Err(reject(CONTENT_BAD_VALUE, code_span.start, code_span.end));
        }
        previous = Some(code);
        entries.push(AtomEntry {
            code,
            label_text_ref: label,
        });
        entry_spans.push((code_span, label_span));
    }
    let refs = entry_spans
        .iter()
        .map(|(_, span)| RefField {
            value: u16::from_be_bytes([raw[span.start], raw[span.start + 1]]),
            span: *span,
            wanted: Wanted::Kind(CONTENT_KIND_TEXT),
            optional: false,
        })
        .collect();
    Ok((
        RecordPayload::AtomSchema {
            atom_class: class,
            atom_width: width,
            entries,
            min_value: None,
            max_value: None,
            allowed_mask: (class == ATOM_MASK).then_some(first_value),
        },
        Meta {
            refs,
            detail: Detail::None,
            ..Meta::default()
        },
    ))
}

fn decode_local(raw: &[u8], record: RawRecord) -> Result<(RecordPayload, Meta)> {
    if record.kind == CONTENT_KIND_TEXT {
        return decode_text(raw, record);
    }
    if record.kind == CONTENT_KIND_ATOM_SCHEMA {
        return decode_atom_schema(raw, record);
    }
    let mut cursor = Cursor::new(raw, record.payload);
    match record.kind {
        CONTENT_KIND_ATOM_VECTOR => {
            let (schema, schema_span) = cursor.u16().unwrap();
            let (count, count_span) = cursor.u16().unwrap();
            if count as usize > CONTENT_MAX_VECTOR_ATOMS as usize {
                return Err(reject(
                    CONTENT_LIMIT_EXCEEDED,
                    count_span.start,
                    count_span.end,
                ));
            }
            Ok((
                RecordPayload::AtomVector {
                    atom_schema_ref: schema,
                    atoms: Vec::new(),
                },
                Meta {
                    refs: vec![RefField {
                        value: schema,
                        span: schema_span,
                        wanted: Wanted::Kind(CONTENT_KIND_ATOM_SCHEMA),
                        optional: false,
                    }],
                    detail: Detail::AtomVector {
                        count,
                        data_start: cursor.at,
                    },
                    ..Meta::default()
                },
            ))
        }
        CONTENT_KIND_MATRIX => {
            let (schema, schema_span) = cursor.u16().unwrap();
            let (rows, rows_span) = cursor.u16().unwrap();
            let (columns, columns_span) = cursor.u16().unwrap();
            if rows == 0 {
                return Err(reject(CONTENT_BAD_COUNT, rows_span.start, rows_span.end));
            }
            if columns == 0 {
                return Err(reject(
                    CONTENT_BAD_COUNT,
                    columns_span.start,
                    columns_span.end,
                ));
            }
            if rows as usize * columns as usize > CONTENT_MAX_MATRIX_CELLS as usize {
                return Err(reject(
                    CONTENT_LIMIT_EXCEEDED,
                    columns_span.start,
                    columns_span.end,
                ));
            }
            Ok((
                RecordPayload::Matrix {
                    atom_schema_ref: schema,
                    rows,
                    columns,
                    cells: Vec::new(),
                },
                Meta {
                    refs: vec![RefField {
                        value: schema,
                        span: schema_span,
                        wanted: Wanted::Kind(CONTENT_KIND_ATOM_SCHEMA),
                        optional: false,
                    }],
                    detail: Detail::Matrix {
                        data_start: cursor.at,
                    },
                    ..Meta::default()
                },
            ))
        }
        CONTENT_KIND_FIELD_SCHEMA => decode_field_schema(raw, record, cursor),
        CONTENT_KIND_TUPLE => {
            let (schema, span) = cursor.u16().unwrap();
            Ok((
                RecordPayload::Tuple {
                    field_schema_ref: schema,
                    field_values: Vec::new(),
                },
                Meta {
                    refs: vec![RefField {
                        value: schema,
                        span,
                        wanted: Wanted::Kind(CONTENT_KIND_FIELD_SCHEMA),
                        optional: false,
                    }],
                    detail: Detail::Tuple {
                        data_start: cursor.at,
                    },
                    ..Meta::default()
                },
            ))
        }
        CONTENT_KIND_REGION_SET => decode_region_set(raw, record, cursor),
        CONTENT_KIND_SEMANTIC_BINDING => decode_binding(raw, record, cursor),
        CONTENT_KIND_OPAQUE_DATA => {
            let (binding, span) = cursor.u16().unwrap();
            Ok((
                RecordPayload::OpaqueData {
                    data_binding_ref: binding,
                    data: Vec::new(),
                },
                Meta {
                    refs: vec![RefField {
                        value: binding,
                        span,
                        wanted: Wanted::BindingData,
                        optional: false,
                    }],
                    detail: Detail::OpaqueData {
                        data_start: cursor.at,
                    },
                    ..Meta::default()
                },
            ))
        }
        CONTENT_KIND_PREDICATE_RESULT => decode_predicate(record, cursor),
        CONTENT_KIND_FEEDBACK => decode_feedback(record, cursor),
        CONTENT_KIND_PASSIVE_TRACE => decode_passive(raw, record, cursor),
        CONTENT_KIND_LESSON_NODE => decode_lesson(raw, record, cursor),
        CONTENT_KIND_ROOT => {
            let (entry, entry_span) = cursor.u16().unwrap();
            let (budget, budget_span) = cursor.u16().unwrap();
            Ok((
                RecordPayload::Root {
                    entry_node_ref: entry,
                    global_event_budget: budget,
                },
                Meta {
                    refs: vec![RefField {
                        value: entry,
                        span: entry_span,
                        wanted: Wanted::Kind(CONTENT_KIND_LESSON_NODE),
                        optional: false,
                    }],
                    detail: Detail::Root { budget_span },
                    ..Meta::default()
                },
            ))
        }
        _ => unreachable!(),
    }
}

fn decode_field_schema(
    _raw: &[u8],
    record: RawRecord,
    mut cursor: Cursor<'_>,
) -> Result<(RecordPayload, Meta)> {
    let (count, count_span) = cursor.u16().unwrap();
    if count == 0 {
        return Err(reject(CONTENT_BAD_COUNT, count_span.start, count_span.end));
    }
    if count as usize > CONTENT_MAX_FIELD_SCHEMA_FIELDS as usize {
        return Err(reject(
            CONTENT_LIMIT_EXCEEDED,
            count_span.start,
            count_span.end,
        ));
    }
    exact_length(record, 2 + count as usize * 8)?;
    let mut fields = Vec::with_capacity(count as usize);
    let mut field_meta = Vec::with_capacity(count as usize);
    let mut refs = Vec::with_capacity(count as usize * 2);
    let mut slots = 0usize;
    for _ in 0..count {
        let (name, name_span) = cursor.u16().unwrap();
        let (storage, storage_span) = cursor.u8().unwrap();
        let (reserved, reserved_span) = cursor.u8().unwrap();
        let (type_code, type_span) = cursor.u16().unwrap();
        let (field_count, field_count_span) = cursor.u16().unwrap();
        if !matches!(storage, FIELD_INLINE_ATOM | FIELD_RECORD_REF) {
            return Err(reject(
                CONTENT_BAD_TAG,
                storage_span.start,
                storage_span.end,
            ));
        }
        if reserved != 0 {
            return Err(reject(
                CONTENT_RESERVED_NONZERO,
                reserved_span.start,
                reserved_span.end,
            ));
        }
        if storage == FIELD_RECORD_REF
            && !matches!(
                type_code,
                CONTENT_KIND_TEXT
                    | CONTENT_KIND_ATOM_VECTOR
                    | CONTENT_KIND_MATRIX
                    | CONTENT_KIND_TUPLE
                    | CONTENT_KIND_OPAQUE_DATA
            )
        {
            return Err(reject(CONTENT_BAD_TAG, type_span.start, type_span.end));
        }
        if field_count == 0 {
            return Err(reject(
                CONTENT_BAD_COUNT,
                field_count_span.start,
                field_count_span.end,
            ));
        }
        slots += field_count as usize;
        if slots > CONTENT_MAX_TUPLE_SLOTS as usize {
            return Err(reject(
                CONTENT_LIMIT_EXCEEDED,
                field_count_span.start,
                field_count_span.end,
            ));
        }
        refs.push(RefField {
            value: name,
            span: name_span,
            wanted: Wanted::Kind(CONTENT_KIND_TEXT),
            optional: false,
        });
        if storage == FIELD_INLINE_ATOM {
            refs.push(RefField {
                value: type_code,
                span: type_span,
                wanted: Wanted::Kind(CONTENT_KIND_ATOM_SCHEMA),
                optional: false,
            });
        }
        fields.push(FieldSpec {
            name_text_ref: name,
            storage,
            type_code,
            count: field_count,
        });
        field_meta.push(FieldMeta { name_span });
    }
    Ok((
        RecordPayload::FieldSchema { fields },
        Meta {
            refs,
            detail: Detail::FieldSchema { fields: field_meta },
            ..Meta::default()
        },
    ))
}

fn decode_region_set(
    _raw: &[u8],
    record: RawRecord,
    mut cursor: Cursor<'_>,
) -> Result<(RecordPayload, Meta)> {
    let (surface, surface_span) = cursor.u16().unwrap();
    let (count, count_span) = cursor.u16().unwrap();
    if count == 0 {
        return Err(reject(CONTENT_BAD_COUNT, count_span.start, count_span.end));
    }
    if count as usize > CONTENT_MAX_REGIONS as usize {
        return Err(reject(
            CONTENT_LIMIT_EXCEEDED,
            count_span.start,
            count_span.end,
        ));
    }
    exact_length(record, 4 + count as usize * 14)?;
    let mut refs = vec![RefField {
        value: surface,
        span: surface_span,
        wanted: Wanted::Kind(CONTENT_KIND_MATRIX),
        optional: false,
    }];
    let mut regions = Vec::with_capacity(count as usize);
    let mut metas = Vec::with_capacity(count as usize);
    let mut previous = None;
    for _ in 0..count {
        let (id, id_span) = cursor.u16().unwrap();
        let (label, label_span) = cursor.u16().unwrap();
        let (row_start, _) = cursor.u16().unwrap();
        let (row_end, row_end_span) = cursor.u16().unwrap();
        let (column_start, _) = cursor.u16().unwrap();
        let (column_end, column_end_span) = cursor.u16().unwrap();
        let (flags, flags_span) = cursor.u8().unwrap();
        let (reserved, reserved_span) = cursor.u8().unwrap();
        if id == 0 {
            return Err(reject(CONTENT_BAD_VALUE, id_span.start, id_span.end));
        }
        if let Some(prior) = previous {
            if id < prior {
                return Err(reject(
                    CONTENT_NONCANONICAL_ORDER,
                    id_span.start,
                    id_span.end,
                ));
            }
            if id == prior {
                return Err(reject(CONTENT_DUPLICATE, id_span.start, id_span.end));
            }
        }
        if flags & !(REGION_SELECTABLE | REGION_HIGHLIGHTED) != 0 {
            return Err(reject(
                CONTENT_RESERVED_NONZERO,
                flags_span.start,
                flags_span.end,
            ));
        }
        if reserved != 0 {
            return Err(reject(
                CONTENT_RESERVED_NONZERO,
                reserved_span.start,
                reserved_span.end,
            ));
        }
        if row_start >= row_end {
            return Err(reject(
                CONTENT_BAD_VALUE,
                row_end_span.start,
                row_end_span.end,
            ));
        }
        if column_start >= column_end {
            return Err(reject(
                CONTENT_BAD_VALUE,
                column_end_span.start,
                column_end_span.end,
            ));
        }
        if label != 0 {
            refs.push(RefField {
                value: label,
                span: label_span,
                wanted: Wanted::Display,
                optional: true,
            });
        }
        previous = Some(id);
        regions.push(Region {
            region_id: id,
            label_ref: label,
            row_start,
            row_end,
            column_start,
            column_end,
            flags,
        });
        metas.push(RegionMeta {
            id_span,
            row_end_span,
            column_end_span,
        });
    }
    Ok((
        RecordPayload::RegionSet {
            surface_matrix_ref: surface,
            regions,
        },
        Meta {
            refs,
            detail: Detail::RegionSet { regions: metas },
            ..Meta::default()
        },
    ))
}

fn decode_binding(
    _raw: &[u8],
    _record: RawRecord,
    mut cursor: Cursor<'_>,
) -> Result<(RecordPayload, Meta)> {
    let (class, class_span) = cursor.u8().unwrap();
    let (reserved, reserved_span) = cursor.u8().unwrap();
    let (namespace_id, namespace_span) = cursor.u16().unwrap();
    let (semantic_code, semantic_span) = cursor.u16().unwrap();
    let (argument, argument_span) = cursor.u16().unwrap();
    let (auxiliary, auxiliary_span) = cursor.u16().unwrap();
    if !matches!(class, BINDING_DATA | BINDING_PREDICATE) {
        return Err(reject(CONTENT_BAD_TAG, class_span.start, class_span.end));
    }
    if reserved != 0 {
        return Err(reject(
            CONTENT_RESERVED_NONZERO,
            reserved_span.start,
            reserved_span.end,
        ));
    }
    if namespace_id == 0 {
        return Err(reject(
            CONTENT_BAD_VALUE,
            namespace_span.start,
            namespace_span.end,
        ));
    }
    if semantic_code == 0 {
        return Err(reject(
            CONTENT_BAD_VALUE,
            semantic_span.start,
            semantic_span.end,
        ));
    }
    if class == BINDING_DATA && auxiliary == 0 {
        return Err(reject(
            CONTENT_BAD_COUNT,
            auxiliary_span.start,
            auxiliary_span.end,
        ));
    }
    if class == BINDING_DATA && auxiliary as usize > CONTENT_MAX_OPAQUE_ATOMS as usize {
        return Err(reject(
            CONTENT_LIMIT_EXCEEDED,
            auxiliary_span.start,
            auxiliary_span.end,
        ));
    }
    Ok((
        RecordPayload::SemanticBinding {
            binding_class: class,
            namespace_id,
            semantic_code,
            argument,
            auxiliary,
        },
        Meta {
            refs: vec![
                RefField {
                    value: argument,
                    span: argument_span,
                    wanted: if class == BINDING_DATA {
                        Wanted::Kind(CONTENT_KIND_ATOM_SCHEMA)
                    } else {
                        Wanted::BindingData
                    },
                    optional: false,
                },
                RefField {
                    value: auxiliary,
                    span: auxiliary_span,
                    wanted: Wanted::Kind(CONTENT_KIND_ATOM_SCHEMA),
                    optional: class == BINDING_DATA,
                },
            ]
            .into_iter()
            .filter(|field| !(class == BINDING_DATA && field.span == auxiliary_span))
            .collect(),
            ..Meta::default()
        },
    ))
}

fn decode_predicate(record: RawRecord, mut cursor: Cursor<'_>) -> Result<(RecordPayload, Meta)> {
    let (predicate, predicate_span) = cursor.u16().unwrap();
    let (subject, subject_span) = cursor.u16().unwrap();
    let (result, result_span) = cursor.u16().unwrap();
    exact_length(record, 6)?;
    Ok((
        RecordPayload::PredicateResult {
            predicate_binding_ref: predicate,
            subject_opaque_data_ref: subject,
            result_atom_vector_ref: result,
        },
        Meta {
            refs: vec![
                RefField {
                    value: predicate,
                    span: predicate_span,
                    wanted: Wanted::BindingPredicate,
                    optional: false,
                },
                RefField {
                    value: subject,
                    span: subject_span,
                    wanted: Wanted::Kind(CONTENT_KIND_OPAQUE_DATA),
                    optional: false,
                },
                RefField {
                    value: result,
                    span: result_span,
                    wanted: Wanted::Kind(CONTENT_KIND_ATOM_VECTOR),
                    optional: false,
                },
            ],
            detail: Detail::PredicateResult { result_span },
            ..Meta::default()
        },
    ))
}

fn decode_feedback(record: RawRecord, mut cursor: Cursor<'_>) -> Result<(RecordPayload, Meta)> {
    let (code, code_span) = cursor.u16().unwrap();
    let (display, display_span) = cursor.u16().unwrap();
    let (predicate, predicate_span) = cursor.u16().unwrap();
    exact_length(record, 6)?;
    if !(FEEDBACK_NEUTRAL..=FEEDBACK_LIMITATION).contains(&code) {
        return Err(reject(CONTENT_BAD_TAG, code_span.start, code_span.end));
    }
    Ok((
        RecordPayload::Feedback {
            feedback_code: code,
            display_ref: display,
            predicate_result_ref: predicate,
        },
        Meta {
            refs: vec![
                RefField {
                    value: display,
                    span: display_span,
                    wanted: Wanted::Display,
                    optional: false,
                },
                RefField {
                    value: predicate,
                    span: predicate_span,
                    wanted: Wanted::Kind(CONTENT_KIND_PREDICATE_RESULT),
                    optional: true,
                },
            ],
            detail: Detail::Feedback { predicate_span },
            ..Meta::default()
        },
    ))
}

fn decode_passive(
    raw: &[u8],
    record: RawRecord,
    mut cursor: Cursor<'_>,
) -> Result<(RecordPayload, Meta)> {
    let (presentation, presentation_span) = cursor.u16().unwrap();
    let (region_set, region_span) = cursor.u16().unwrap();
    let (resulting, resulting_span) = cursor.u16().unwrap();
    let (limitation, limitation_span) = cursor.u16().unwrap();
    let (count, count_span) = cursor.u16().unwrap();
    if count == 0 {
        return Err(reject(CONTENT_BAD_COUNT, count_span.start, count_span.end));
    }
    exact_length(record, 16 + count as usize * 4)?;
    let actions_start = cursor.at;
    let mut actions = Vec::with_capacity(count as usize);
    for _ in 0..count {
        let span = cursor.span(4).unwrap();
        let action = [
            raw[span.start],
            raw[span.start + 1],
            raw[span.start + 2],
            raw[span.start + 3],
        ];
        if !matches!(action[0], ACTION_SELECT | ACTION_RESET | ACTION_COMMIT) {
            return Err(reject(CONTENT_BAD_TAG, span.start, span.start + 1));
        }
        if action[1] != 0 {
            return Err(reject(
                CONTENT_RESERVED_NONZERO,
                span.start + 1,
                span.start + 2,
            ));
        }
        if action[0] != ACTION_SELECT && action[2..] != [0, 0] {
            return Err(reject(CONTENT_BAD_VALUE, span.start + 2, span.end));
        }
        actions.push(action);
    }
    let (outcome, outcome_span) = cursor.u8().unwrap();
    let (reserved, reserved_span) = cursor.u8().unwrap();
    let (feedback, feedback_span) = cursor.u16().unwrap();
    let (next, next_span) = cursor.u16().unwrap();
    if !matches!(
        outcome,
        OUTCOME_ACCEPTED | OUTCOME_REJECTED | OUTCOME_NEUTRAL
    ) {
        return Err(reject(
            CONTENT_BAD_TAG,
            outcome_span.start,
            outcome_span.end,
        ));
    }
    if reserved != 0 {
        return Err(reject(
            CONTENT_RESERVED_NONZERO,
            reserved_span.start,
            reserved_span.end,
        ));
    }
    Ok((
        RecordPayload::PassiveTrace {
            presentation_ref: presentation,
            region_set_ref: region_set,
            resulting_presentation_ref: resulting,
            limitation_text_ref: limitation,
            actions,
            expected_outcome: outcome,
            expected_feedback_ref: feedback,
            expected_next_node_ref: next,
        },
        Meta {
            refs: vec![
                RefField {
                    value: presentation,
                    span: presentation_span,
                    wanted: Wanted::Presentation,
                    optional: false,
                },
                RefField {
                    value: region_set,
                    span: region_span,
                    wanted: Wanted::Kind(CONTENT_KIND_REGION_SET),
                    optional: false,
                },
                RefField {
                    value: resulting,
                    span: resulting_span,
                    wanted: Wanted::Presentation,
                    optional: true,
                },
                RefField {
                    value: limitation,
                    span: limitation_span,
                    wanted: Wanted::Kind(CONTENT_KIND_TEXT),
                    optional: true,
                },
                RefField {
                    value: feedback,
                    span: feedback_span,
                    wanted: Wanted::Kind(CONTENT_KIND_FEEDBACK),
                    optional: false,
                },
            ],
            controls: vec![ControlField {
                value: next,
                span: next_span,
            }],
            detail: Detail::PassiveTrace {
                limitation_span,
                action_count_span: count_span,
                actions_start,
                outcome_span,
                feedback_span,
                next_span,
            },
        },
    ))
}

fn decode_lesson(
    _raw: &[u8],
    record: RawRecord,
    mut cursor: Cursor<'_>,
) -> Result<(RecordPayload, Meta)> {
    let (role, role_span) = cursor.u8().unwrap();
    let (shape, shape_span) = cursor.u8().unwrap();
    let (mode, mode_span) = cursor.u8().unwrap();
    let (flags, flags_span) = cursor.u8().unwrap();
    let (presentation, presentation_span) = cursor.u16().unwrap();
    let (region_set, region_span) = cursor.u16().unwrap();
    let (predicate, predicate_span) = cursor.u16().unwrap();
    let (trace, trace_span) = cursor.u16().unwrap();
    let (max_selections, max_span) = cursor.u16().unwrap();
    let (item_event_budget, budget_span) = cursor.u16().unwrap();
    let (case_count, case_count_span) = cursor.u16().unwrap();
    if !(ROLE_EXACT_RULE..=ROLE_PRACTICE).contains(&role) {
        return Err(reject(CONTENT_BAD_TAG, role_span.start, role_span.end));
    }
    if !matches!(shape, RESPONSE_SINGLE | RESPONSE_SET | RESPONSE_SEQUENCE) {
        return Err(reject(CONTENT_BAD_TAG, shape_span.start, shape_span.end));
    }
    if !matches!(
        mode,
        ANSWER_PACKED_PRACTICE | ANSWER_EXTERNAL | ANSWER_UNSCORED
    ) {
        return Err(reject(CONTENT_BAD_TAG, mode_span.start, mode_span.end));
    }
    if flags & !LESSON_ALLOW_REPEATED_SELECTIONS != 0 {
        return Err(reject(
            CONTENT_RESERVED_NONZERO,
            flags_span.start,
            flags_span.end,
        ));
    }
    if case_count as usize > CONTENT_MAX_CASES_PER_NODE as usize {
        return Err(reject(
            CONTENT_LIMIT_EXCEEDED,
            case_count_span.start,
            case_count_span.end,
        ));
    }
    let mut cases = Vec::with_capacity(case_count as usize);
    let mut metas = Vec::with_capacity(case_count as usize);
    let mut controls = Vec::with_capacity(case_count as usize + 1);
    let mut refs = vec![
        RefField {
            value: presentation,
            span: presentation_span,
            wanted: Wanted::Presentation,
            optional: false,
        },
        RefField {
            value: region_set,
            span: region_span,
            wanted: Wanted::Kind(CONTENT_KIND_REGION_SET),
            optional: false,
        },
        RefField {
            value: predicate,
            span: predicate_span,
            wanted: Wanted::Kind(CONTENT_KIND_PREDICATE_RESULT),
            optional: true,
        },
        RefField {
            value: trace,
            span: trace_span,
            wanted: Wanted::Kind(CONTENT_KIND_PASSIVE_TRACE),
            optional: true,
        },
    ];
    let mut prior_response: Option<Vec<u8>> = None;
    for _ in 0..case_count {
        if cursor.remaining() < 8 {
            return Err(reject(
                CONTENT_BAD_PAYLOAD_LENGTH,
                record.length_span.start,
                record.length_span.end,
            ));
        }
        let (class, class_span) = cursor.u8().unwrap();
        let (reserved, reserved_span) = cursor.u8().unwrap();
        let (selection_count, count_span) = cursor.u16().unwrap();
        if !matches!(class, CASE_ACCEPTED | CASE_REJECTED_SPECIAL) {
            return Err(reject(CONTENT_BAD_TAG, class_span.start, class_span.end));
        }
        if reserved != 0 {
            return Err(reject(
                CONTENT_RESERVED_NONZERO,
                reserved_span.start,
                reserved_span.end,
            ));
        }
        let Some(ids_bytes) = (selection_count as usize).checked_mul(2) else {
            return Err(reject(
                CONTENT_LIMIT_EXCEEDED,
                count_span.start,
                count_span.end,
            ));
        };
        if cursor.remaining() < ids_bytes + 4 {
            return Err(reject(
                CONTENT_BAD_PAYLOAD_LENGTH,
                record.length_span.start,
                record.length_span.end,
            ));
        }
        let mut ids = Vec::with_capacity(selection_count as usize);
        let mut region_spans = Vec::with_capacity(selection_count as usize);
        let mut previous = None;
        for _ in 0..selection_count {
            let (id, span) = cursor.u16().unwrap();
            if shape == RESPONSE_SET {
                if let Some(prior) = previous {
                    if id < prior {
                        return Err(reject(CONTENT_NONCANONICAL_ORDER, span.start, span.end));
                    }
                    if id == prior {
                        return Err(reject(CONTENT_DUPLICATE, span.start, span.end));
                    }
                }
                previous = Some(id);
            }
            ids.push(id);
            region_spans.push(span);
        }
        let (feedback, feedback_span) = cursor.u16().unwrap();
        let (next, next_span) = cursor.u16().unwrap();
        let response_bytes = response_bytes(shape, &ids);
        if let Some(prior) = &prior_response {
            if response_bytes < *prior {
                return Err(reject(
                    CONTENT_NONCANONICAL_ORDER,
                    count_span.start,
                    count_span.end,
                ));
            }
            if response_bytes == *prior {
                return Err(reject(CONTENT_DUPLICATE, count_span.start, count_span.end));
            }
        }
        prior_response = Some(response_bytes.clone());
        refs.push(RefField {
            value: feedback,
            span: feedback_span,
            wanted: Wanted::Kind(CONTENT_KIND_FEEDBACK),
            optional: false,
        });
        controls.push(ControlField {
            value: next,
            span: next_span,
        });
        cases.push(LessonCase {
            case_class: class,
            region_ids: ids,
            feedback_ref: feedback,
            next_node_ref: next,
        });
        metas.push(CaseMeta {
            count_span,
            region_spans,
            feedback_span,
            next_span,
        });
    }
    if cursor.remaining() != 4 {
        return Err(reject(
            CONTENT_BAD_PAYLOAD_LENGTH,
            record.length_span.start,
            record.length_span.end,
        ));
    }
    let (default_feedback, default_feedback_span) = cursor.u16().unwrap();
    let (default_next, default_next_span) = cursor.u16().unwrap();
    refs.push(RefField {
        value: default_feedback,
        span: default_feedback_span,
        wanted: Wanted::Kind(CONTENT_KIND_FEEDBACK),
        optional: false,
    });
    controls.push(ControlField {
        value: default_next,
        span: default_next_span,
    });
    Ok((
        RecordPayload::LessonNode {
            role,
            response_shape: shape,
            answer_mode: mode,
            flags,
            presentation_ref: presentation,
            region_set_ref: region_set,
            predicate_result_ref: predicate,
            passive_trace_ref: trace,
            max_selections,
            item_event_budget,
            cases,
            default_feedback_ref: default_feedback,
            default_next_node_ref: default_next,
        },
        Meta {
            refs,
            controls,
            detail: Detail::LessonNode(LessonMeta {
                mode_span,
                flags_span,
                predicate_span,
                trace_span,
                max_span,
                budget_span,
                case_count_span,
                cases: metas,
                default_feedback_span,
            }),
        },
    ))
}

fn response_bytes(shape: u8, ids: &[u16]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(3 + ids.len() * 2);
    bytes.push(shape);
    bytes.extend_from_slice(&(ids.len() as u16).to_be_bytes());
    for id in ids {
        bytes.extend_from_slice(&id.to_be_bytes());
    }
    bytes
}

fn find_record(records: &[DecodedRecord], id: u16) -> Option<usize> {
    records
        .binary_search_by_key(&id, |record| record.record.record_id)
        .ok()
}

fn binding_class(record: &DecodedRecord) -> Option<u8> {
    match record.record.payload {
        RecordPayload::SemanticBinding { binding_class, .. } => Some(binding_class),
        _ => None,
    }
}

fn wanted_matches(record: &DecodedRecord, wanted: Wanted) -> bool {
    match wanted {
        Wanted::Kind(kind) => record.record.kind() == kind,
        Wanted::Display => matches!(
            record.record.kind(),
            CONTENT_KIND_TEXT
                | CONTENT_KIND_ATOM_VECTOR
                | CONTENT_KIND_MATRIX
                | CONTENT_KIND_TUPLE
                | CONTENT_KIND_OPAQUE_DATA
        ),
        Wanted::Presentation => matches!(
            record.record.kind(),
            CONTENT_KIND_MATRIX | CONTENT_KIND_TUPLE
        ),
        Wanted::BindingData => binding_class(record) == Some(BINDING_DATA),
        Wanted::BindingPredicate => binding_class(record) == Some(BINDING_PREDICATE),
    }
}

fn validate_ref(records: &[DecodedRecord], owner: u16, field: RefField) -> Result<()> {
    if field.value == 0 {
        return if field.optional {
            Ok(())
        } else {
            Err(reject(
                CONTENT_ZERO_REFERENCE,
                field.span.start,
                field.span.end,
            ))
        };
    }
    if field.value >= owner {
        return Err(reject(
            CONTENT_FORWARD_REFERENCE,
            field.span.start,
            field.span.end,
        ));
    }
    let Some(index) = find_record(records, field.value) else {
        return Err(reject(
            CONTENT_MISSING_REFERENCE,
            field.span.start,
            field.span.end,
        ));
    };
    if !wanted_matches(&records[index], field.wanted) {
        return Err(reject(
            CONTENT_WRONG_REFERENCE_KIND,
            field.span.start,
            field.span.end,
        ));
    }
    Ok(())
}

fn schema<'a>(
    records: &'a [DecodedRecord],
    id: u16,
) -> (
    u8,
    u8,
    &'a [AtomEntry],
    Option<u32>,
    Option<u32>,
    Option<u32>,
) {
    let record = &records[find_record(records, id).unwrap()].record;
    let RecordPayload::AtomSchema {
        atom_class,
        atom_width,
        entries,
        min_value,
        max_value,
        allowed_mask,
    } = &record.payload
    else {
        unreachable!()
    };
    (
        *atom_class,
        *atom_width,
        entries,
        *min_value,
        *max_value,
        *allowed_mask,
    )
}

fn atom_valid(records: &[DecodedRecord], schema_id: u16, value: u32) -> bool {
    let (class, _, entries, min, max, mask) = schema(records, schema_id);
    match class {
        ATOM_UNSIGNED => (min.unwrap()..=max.unwrap()).contains(&value),
        ATOM_ENUM => entries
            .binary_search_by_key(&value, |entry| entry.code)
            .is_ok(),
        ATOM_MASK => value & !mask.unwrap() == 0,
        _ => false,
    }
}

fn retain_earliest(best: &mut Option<ContentReject>, candidate: ContentReject) {
    if best.as_ref().is_none_or(|current| {
        (candidate.raw_start, candidate.code) < (current.raw_start, current.code)
    }) {
        *best = Some(candidate);
    }
}

fn decode_atoms(raw: &[u8], start: usize, count: usize, width: u8) -> Vec<u32> {
    (0..count)
        .map(|index| {
            let start = start + index * width as usize;
            read_atom(
                raw,
                Span {
                    start,
                    end: start + width as usize,
                },
                width,
            )
        })
        .collect()
}

fn validate_lengths_and_tuple_refs(raw: &[u8], records: &mut [DecodedRecord]) -> Result<()> {
    for index in 0..records.len() {
        let raw_record = records[index].raw;
        match (&records[index].record.payload, &records[index].meta.detail) {
            (
                RecordPayload::AtomVector {
                    atom_schema_ref, ..
                },
                Detail::AtomVector { count, .. },
            ) => {
                let width = schema(records, *atom_schema_ref).1 as usize;
                exact_length(raw_record, 4 + *count as usize * width)?;
            }
            (
                RecordPayload::Matrix {
                    atom_schema_ref,
                    rows,
                    columns,
                    ..
                },
                Detail::Matrix { .. },
            ) => {
                let width = schema(records, *atom_schema_ref).1 as usize;
                exact_length(raw_record, 6 + *rows as usize * *columns as usize * width)?;
            }
            (
                RecordPayload::Tuple {
                    field_schema_ref, ..
                },
                Detail::Tuple { .. },
            ) => {
                let schema_record =
                    &records[find_record(records, *field_schema_ref).unwrap()].record;
                let RecordPayload::FieldSchema { fields } = &schema_record.payload else {
                    unreachable!()
                };
                let mut width = 2usize;
                for field in fields {
                    let item = if field.storage == FIELD_INLINE_ATOM {
                        schema(records, field.type_code).1 as usize
                    } else {
                        2
                    };
                    width = width.checked_add(item * field.count as usize).unwrap();
                }
                exact_length(raw_record, width)?;
            }
            (
                RecordPayload::OpaqueData {
                    data_binding_ref, ..
                },
                Detail::OpaqueData { .. },
            ) => {
                let binding = &records[find_record(records, *data_binding_ref).unwrap()].record;
                let RecordPayload::SemanticBinding {
                    argument,
                    auxiliary,
                    ..
                } = binding.payload
                else {
                    unreachable!()
                };
                let width = schema(records, argument).1 as usize;
                exact_length(raw_record, 2 + width * auxiliary as usize)?;
            }
            _ => {}
        }
    }

    for index in 0..records.len() {
        let (schema_id, mut at) =
            match (&records[index].record.payload, &records[index].meta.detail) {
                (
                    RecordPayload::Tuple {
                        field_schema_ref, ..
                    },
                    Detail::Tuple { data_start },
                ) => (*field_schema_ref, *data_start),
                _ => continue,
            };
        let schema_record = &records[find_record(records, schema_id).unwrap()].record;
        let RecordPayload::FieldSchema { fields } = &schema_record.payload else {
            unreachable!()
        };
        let fields = fields.clone();
        let owner = records[index].record.record_id;
        let mut values = Vec::with_capacity(fields.len());
        for field in &fields {
            if field.storage == FIELD_INLINE_ATOM {
                let width = schema(records, field.type_code).1;
                let atoms = decode_atoms(raw, at, field.count as usize, width);
                at += width as usize * field.count as usize;
                values.push(FieldValue::Atoms(atoms));
            } else {
                let mut refs = Vec::with_capacity(field.count as usize);
                for _ in 0..field.count {
                    let value = u16::from_be_bytes([raw[at], raw[at + 1]]);
                    let span = Span {
                        start: at,
                        end: at + 2,
                    };
                    validate_ref(
                        records,
                        owner,
                        RefField {
                            value,
                            span,
                            wanted: Wanted::Kind(field.type_code),
                            optional: false,
                        },
                    )?;
                    refs.push(value);
                    at += 2;
                }
                values.push(FieldValue::RecordRefs(refs));
            }
        }
        let RecordPayload::Tuple { field_values, .. } = &mut records[index].record.payload else {
            unreachable!()
        };
        *field_values = values;
    }
    Ok(())
}

fn presentation_summary(
    records: &[DecodedRecord],
    summaries: &BTreeMap<u16, (u8, u16)>,
    id: u16,
) -> (u8, u16) {
    let record = &records[find_record(records, id).unwrap()].record;
    match &record.payload {
        RecordPayload::Matrix { .. } => (1, id),
        RecordPayload::Tuple { .. } => summaries[&id],
        _ => (0, 0),
    }
}

fn validate_derived(raw: &[u8], records: &mut [DecodedRecord]) -> Result<()> {
    for record in records.iter() {
        for &field in &record.meta.refs {
            validate_ref(records, record.record.record_id, field)?;
        }
    }
    validate_lengths_and_tuple_refs(raw, records)?;

    let mut stage_five = None;
    for index in 0..records.len() {
        let payload = records[index].record.payload.clone();
        match (payload, records[index].meta.detail.clone()) {
            (
                RecordPayload::AtomVector {
                    atom_schema_ref, ..
                },
                Detail::AtomVector { count, data_start },
            ) => {
                let width = schema(records, atom_schema_ref).1;
                let atoms = decode_atoms(raw, data_start, count as usize, width);
                for (at, value) in atoms.iter().enumerate() {
                    if !atom_valid(records, atom_schema_ref, *value) {
                        let start = data_start + at * width as usize;
                        retain_earliest(
                            &mut stage_five,
                            reject(CONTENT_BAD_VALUE, start, start + width as usize),
                        );
                    }
                }
                let RecordPayload::AtomVector { atoms: target, .. } =
                    &mut records[index].record.payload
                else {
                    unreachable!()
                };
                *target = atoms;
            }
            (
                RecordPayload::Matrix {
                    atom_schema_ref,
                    rows,
                    columns,
                    ..
                },
                Detail::Matrix { data_start, .. },
            ) => {
                let width = schema(records, atom_schema_ref).1;
                let cells = decode_atoms(raw, data_start, rows as usize * columns as usize, width);
                for (at, value) in cells.iter().enumerate() {
                    if !atom_valid(records, atom_schema_ref, *value) {
                        let start = data_start + at * width as usize;
                        retain_earliest(
                            &mut stage_five,
                            reject(CONTENT_BAD_VALUE, start, start + width as usize),
                        );
                    }
                }
                let RecordPayload::Matrix { cells: target, .. } =
                    &mut records[index].record.payload
                else {
                    unreachable!()
                };
                *target = cells;
            }
            (
                RecordPayload::Tuple {
                    field_schema_ref,
                    field_values,
                },
                _,
            ) => {
                let schema_record =
                    &records[find_record(records, field_schema_ref).unwrap()].record;
                let RecordPayload::FieldSchema { fields } = &schema_record.payload else {
                    unreachable!()
                };
                let Detail::Tuple { data_start } = records[index].meta.detail else {
                    unreachable!()
                };
                let mut at = data_start;
                for (field, value) in fields.iter().zip(field_values) {
                    if let FieldValue::Atoms(atoms) = value {
                        let width = schema(records, field.type_code).1 as usize;
                        for atom in atoms {
                            if !atom_valid(records, field.type_code, atom) {
                                retain_earliest(
                                    &mut stage_five,
                                    reject(CONTENT_BAD_VALUE, at, at + width),
                                );
                            }
                            at += width;
                        }
                    } else {
                        at += 2 * field.count as usize;
                    }
                }
            }
            (
                RecordPayload::OpaqueData {
                    data_binding_ref, ..
                },
                Detail::OpaqueData { data_start },
            ) => {
                let binding = &records[find_record(records, data_binding_ref).unwrap()].record;
                let RecordPayload::SemanticBinding {
                    argument,
                    auxiliary,
                    ..
                } = binding.payload
                else {
                    unreachable!()
                };
                let width = schema(records, argument).1;
                let data = decode_atoms(raw, data_start, auxiliary as usize, width);
                for (at, atom) in data.iter().enumerate() {
                    if !atom_valid(records, argument, *atom) {
                        let start = data_start + at * width as usize;
                        retain_earliest(
                            &mut stage_five,
                            reject(CONTENT_BAD_VALUE, start, start + width as usize),
                        );
                    }
                }
                let RecordPayload::OpaqueData { data: target, .. } =
                    &mut records[index].record.payload
                else {
                    unreachable!()
                };
                *target = data;
            }
            _ => {}
        }
    }

    for index in 0..records.len() {
        if let (RecordPayload::FieldSchema { fields }, Detail::FieldSchema { fields: metas }) =
            (&records[index].record.payload, &records[index].meta.detail)
        {
            let mut names = BTreeSet::new();
            for (field, meta) in fields.iter().zip(metas) {
                let name = &records[find_record(records, field.name_text_ref).unwrap()].record;
                let RecordPayload::Text(text) = &name.payload else {
                    unreachable!()
                };
                if text.contains('\n') {
                    retain_earliest(
                        &mut stage_five,
                        reject(
                            CONTENT_SCHEMA_MISMATCH,
                            meta.name_span.start,
                            meta.name_span.end,
                        ),
                    );
                }
                if !names.insert(text.as_bytes()) {
                    retain_earliest(
                        &mut stage_five,
                        reject(CONTENT_DUPLICATE, meta.name_span.start, meta.name_span.end),
                    );
                }
            }
        }
    }

    for index in 0..records.len() {
        if let RecordPayload::PredicateResult {
            predicate_binding_ref,
            subject_opaque_data_ref,
            result_atom_vector_ref,
        } = records[index].record.payload
        {
            let binding = &records[find_record(records, predicate_binding_ref).unwrap()].record;
            let RecordPayload::SemanticBinding {
                argument,
                auxiliary,
                ..
            } = binding.payload
            else {
                unreachable!()
            };
            let subject = &records[find_record(records, subject_opaque_data_ref).unwrap()].record;
            let RecordPayload::OpaqueData {
                data_binding_ref, ..
            } = subject.payload
            else {
                unreachable!()
            };
            let result = &records[find_record(records, result_atom_vector_ref).unwrap()].record;
            let RecordPayload::AtomVector {
                atom_schema_ref,
                ref atoms,
            } = result.payload
            else {
                unreachable!()
            };
            let Detail::PredicateResult { result_span, .. } = records[index].meta.detail else {
                unreachable!()
            };
            if data_binding_ref != argument || atom_schema_ref != auxiliary || atoms.len() != 1 {
                retain_earliest(
                    &mut stage_five,
                    reject(CONTENT_SCHEMA_MISMATCH, result_span.start, result_span.end),
                );
            }
        }
    }

    for index in 0..records.len() {
        if let (
            RecordPayload::RegionSet {
                surface_matrix_ref,
                regions,
            },
            Detail::RegionSet { regions: metas },
        ) = (&records[index].record.payload, &records[index].meta.detail)
        {
            let surface = &records[find_record(records, *surface_matrix_ref).unwrap()].record;
            let RecordPayload::Matrix { rows, columns, .. } = surface.payload else {
                unreachable!()
            };
            for (region, meta) in regions.iter().zip(metas) {
                if region.row_end > rows {
                    retain_earliest(
                        &mut stage_five,
                        reject(
                            CONTENT_BAD_VALUE,
                            meta.row_end_span.start,
                            meta.row_end_span.end,
                        ),
                    );
                }
                if region.column_end > columns {
                    retain_earliest(
                        &mut stage_five,
                        reject(
                            CONTENT_BAD_VALUE,
                            meta.column_end_span.start,
                            meta.column_end_span.end,
                        ),
                    );
                }
            }
            for later in 1..regions.len() {
                if regions[later].flags & REGION_SELECTABLE == 0 {
                    continue;
                }
                for earlier in &regions[..later] {
                    if earlier.flags & REGION_SELECTABLE != 0
                        && earlier.row_start < regions[later].row_end
                        && regions[later].row_start < earlier.row_end
                        && earlier.column_start < regions[later].column_end
                        && regions[later].column_start < earlier.column_end
                    {
                        retain_earliest(
                            &mut stage_five,
                            reject(
                                CONTENT_BAD_VALUE,
                                metas[later].id_span.start,
                                metas[later].id_span.end,
                            ),
                        );
                    }
                }
            }
        }
    }

    let mut summaries = BTreeMap::new();
    for record in records.iter() {
        if let RecordPayload::Tuple { field_values, .. } = &record.record.payload {
            let mut count = 0u8;
            let mut matrix = 0u16;
            for value in field_values {
                if let FieldValue::RecordRefs(refs) = value {
                    for id in refs {
                        let (add, found) = presentation_summary(records, &summaries, *id);
                        let total = count.saturating_add(add).min(2);
                        matrix = if count == 0 && add == 1 {
                            found
                        } else if add == 0 {
                            matrix
                        } else {
                            0
                        };
                        count = total;
                    }
                }
            }
            summaries.insert(
                record.record.record_id,
                (count, if count == 1 { matrix } else { 0 }),
            );
        }
    }
    for record in records.iter() {
        let (presentation, region_set, span, resulting) =
            match (&record.record.payload, &record.meta.detail) {
                (
                    RecordPayload::PassiveTrace {
                        presentation_ref,
                        region_set_ref,
                        resulting_presentation_ref,
                        ..
                    },
                    _,
                ) => (
                    *presentation_ref,
                    *region_set_ref,
                    record.meta.refs[0].span,
                    Some((*resulting_presentation_ref, record.meta.refs[2].span)),
                ),
                (
                    RecordPayload::LessonNode {
                        presentation_ref,
                        region_set_ref,
                        ..
                    },
                    Detail::LessonNode(_),
                ) => (
                    *presentation_ref,
                    *region_set_ref,
                    record.meta.refs[0].span,
                    None,
                ),
                _ => continue,
            };
        let region = &records[find_record(records, region_set).unwrap()].record;
        let RecordPayload::RegionSet {
            surface_matrix_ref, ..
        } = region.payload
        else {
            unreachable!()
        };
        if presentation_summary(records, &summaries, presentation) != (1, surface_matrix_ref) {
            retain_earliest(
                &mut stage_five,
                reject(CONTENT_SCHEMA_MISMATCH, span.start, span.end),
            );
        }
        if let Some((resulting, resulting_span)) = resulting
            && resulting != 0
            && presentation_summary(records, &summaries, resulting) != (1, surface_matrix_ref)
        {
            retain_earliest(
                &mut stage_five,
                reject(
                    CONTENT_SCHEMA_MISMATCH,
                    resulting_span.start,
                    resulting_span.end,
                ),
            );
        }
    }
    stage_five.map_or(Ok(()), Err)
}

fn feedback(records: &[DecodedRecord], id: u16) -> (u16, u16) {
    let record = &records[find_record(records, id).unwrap()].record;
    let RecordPayload::Feedback {
        feedback_code,
        predicate_result_ref,
        ..
    } = record.payload
    else {
        unreachable!()
    };
    (feedback_code, predicate_result_ref)
}

fn selectable_regions(records: &[DecodedRecord], region_set: u16) -> BTreeSet<u16> {
    let record = &records[find_record(records, region_set).unwrap()].record;
    let RecordPayload::RegionSet { ref regions, .. } = record.payload else {
        unreachable!()
    };
    regions
        .iter()
        .filter(|region| region.flags & REGION_SELECTABLE != 0)
        .map(|region| region.region_id)
        .collect()
}

fn validate_graph(records: &[DecodedRecord]) -> Result<u16> {
    let roots: Vec<usize> = records
        .iter()
        .enumerate()
        .filter(|(_, record)| record.record.kind() == CONTENT_KIND_ROOT)
        .map(|(index, _)| index)
        .collect();
    if roots.is_empty() {
        return Err(reject(
            CONTENT_ROOT_COUNT,
            records.last().map_or(0, |r| r.raw.payload.end),
            records.last().map_or(0, |r| r.raw.payload.end),
        ));
    }
    if roots.len() > 1 {
        let record = &records[roots[1]].raw;
        return Err(reject(
            CONTENT_ROOT_COUNT,
            record.header_start + 2,
            record.header_start + 4,
        ));
    }
    let root_index = roots[0];
    if root_index + 1 != records.len() {
        let record = &records[root_index].raw;
        return Err(reject(
            CONTENT_ROOT_NOT_FINAL,
            record.header_start + 2,
            record.header_start + 4,
        ));
    }

    let mut edge_count = 0usize;
    for record in records {
        for control in &record.meta.controls {
            if control.value == 0 {
                continue;
            }
            let Some(target) = find_record(records, control.value) else {
                return Err(reject(
                    CONTENT_BAD_CONTROL_EDGE,
                    control.span.start,
                    control.span.end,
                ));
            };
            if records[target].record.kind() != CONTENT_KIND_LESSON_NODE {
                return Err(reject(
                    CONTENT_BAD_CONTROL_EDGE,
                    control.span.start,
                    control.span.end,
                ));
            }
            if record.record.kind() == CONTENT_KIND_LESSON_NODE {
                edge_count += 1;
                if edge_count > CONTENT_MAX_CONTROL_EDGES as usize {
                    return Err(reject(
                        CONTENT_LIMIT_EXCEEDED,
                        control.span.start,
                        control.span.end,
                    ));
                }
            }
        }
    }

    let root_id = records[root_index].record.record_id;
    let mut reached = BTreeSet::new();
    let mut stack = vec![root_id];
    while let Some(id) = stack.pop() {
        if !reached.insert(id) {
            continue;
        }
        let record = &records[find_record(records, id).unwrap()];
        for field in &record.meta.refs {
            if field.value != 0 {
                stack.push(field.value);
            }
        }
        if record.record.kind() == CONTENT_KIND_LESSON_NODE {
            for control in &record.meta.controls {
                if control.value != 0 {
                    stack.push(control.value);
                }
            }
        }
        if let RecordPayload::Tuple {
            ref field_values, ..
        } = record.record.payload
        {
            for value in field_values {
                if let FieldValue::RecordRefs(refs) = value {
                    stack.extend(refs);
                }
            }
        }
    }
    if let Some(orphan) = records
        .iter()
        .find(|record| !reached.contains(&record.record.record_id))
    {
        return Err(reject(
            CONTENT_ORPHAN_RECORD,
            orphan.raw.header_start,
            orphan.raw.header_start + 2,
        ));
    }

    let mut trace_owner = BTreeMap::new();
    for record in records {
        if let RecordPayload::LessonNode {
            passive_trace_ref, ..
        } = record.record.payload
        {
            if passive_trace_ref != 0 {
                let Detail::LessonNode(ref meta) = record.meta.detail else {
                    unreachable!()
                };
                if trace_owner
                    .insert(passive_trace_ref, record.record.record_id)
                    .is_some()
                {
                    return Err(reject(
                        CONTENT_BAD_PASSIVE_TRACE,
                        meta.trace_span.start,
                        meta.trace_span.end,
                    ));
                }
            }
        }
    }
    Ok(root_id)
}

fn validate_lessons(records: &[DecodedRecord]) -> Result<()> {
    for record in records {
        let RecordPayload::LessonNode {
            role,
            response_shape,
            answer_mode,
            flags,
            region_set_ref,
            predicate_result_ref,
            passive_trace_ref,
            max_selections,
            ref cases,
            ..
        } = record.record.payload
        else {
            continue;
        };
        let Detail::LessonNode(ref meta) = record.meta.detail else {
            unreachable!()
        };
        if response_shape == RESPONSE_SINGLE && max_selections != 1 {
            return Err(reject(
                CONTENT_BAD_RESPONSE_SCHEMA,
                meta.max_span.start,
                meta.max_span.end,
            ));
        }
        if response_shape != RESPONSE_SINGLE
            && max_selections as usize > CONTENT_MAX_SELECTIONS as usize
        {
            return Err(reject(
                CONTENT_BAD_RESPONSE_SCHEMA,
                meta.max_span.start,
                meta.max_span.end,
            ));
        }
        if flags & LESSON_ALLOW_REPEATED_SELECTIONS != 0 && response_shape != RESPONSE_SEQUENCE {
            return Err(reject(
                CONTENT_BAD_RESPONSE_SCHEMA,
                meta.flags_span.start,
                meta.flags_span.end,
            ));
        }
        let selectable = selectable_regions(records, region_set_ref);
        for (case, case_meta) in cases.iter().zip(&meta.cases) {
            if response_shape == RESPONSE_SINGLE && case.region_ids.len() > 1 {
                return Err(reject(
                    CONTENT_BAD_RESPONSE_SCHEMA,
                    case_meta.count_span.start,
                    case_meta.count_span.end,
                ));
            }
            if case.region_ids.len() > max_selections as usize {
                return Err(reject(
                    CONTENT_BAD_RESPONSE_SCHEMA,
                    case_meta.count_span.start,
                    case_meta.count_span.end,
                ));
            }
            let mut seen = BTreeSet::new();
            for (id, span) in case.region_ids.iter().zip(&case_meta.region_spans) {
                if *id == 0 || !selectable.contains(id) {
                    return Err(reject(CONTENT_BAD_RESPONSE_SCHEMA, span.start, span.end));
                }
                if response_shape == RESPONSE_SEQUENCE
                    && flags & LESSON_ALLOW_REPEATED_SELECTIONS == 0
                    && !seen.insert(*id)
                {
                    return Err(reject(CONTENT_BAD_RESPONSE_SCHEMA, span.start, span.end));
                }
            }
        }

        let allowed = matches!(
            (role, answer_mode),
            (
                ROLE_EXACT_RULE | ROLE_OBSERVABLE_RELATION | ROLE_WORKED_EXAMPLE | ROLE_HEURISTIC,
                ANSWER_UNSCORED
            ) | (ROLE_PRACTICE, ANSWER_PACKED_PRACTICE | ANSWER_EXTERNAL)
        );
        if !allowed {
            return Err(reject(
                CONTENT_FORBIDDEN_ANSWER_DATA,
                meta.mode_span.start,
                meta.mode_span.end,
            ));
        }
        let requirements = match (role, answer_mode) {
            (ROLE_EXACT_RULE | ROLE_OBSERVABLE_RELATION, ANSWER_UNSCORED) => (true, None, false),
            (ROLE_WORKED_EXAMPLE, ANSWER_UNSCORED) => (true, Some(true), false),
            (ROLE_HEURISTIC, ANSWER_UNSCORED) => (false, None, false),
            (ROLE_PRACTICE, ANSWER_PACKED_PRACTICE) => (true, Some(true), true),
            (ROLE_PRACTICE, ANSWER_EXTERNAL) => (false, Some(false), false),
            _ => unreachable!(),
        };
        let bad_span = if (predicate_result_ref != 0) != requirements.0 {
            Some(meta.predicate_span)
        } else if requirements
            .1
            .is_some_and(|required| (passive_trace_ref != 0) != required)
        {
            Some(meta.trace_span)
        } else if !requirements.2 && !cases.is_empty() {
            Some(meta.case_count_span)
        } else {
            None
        };
        if let Some(span) = bad_span {
            return Err(reject(CONTENT_FORBIDDEN_ANSWER_DATA, span.start, span.end));
        }
        if answer_mode == ANSWER_PACKED_PRACTICE
            && !cases.iter().any(|case| case.case_class == CASE_ACCEPTED)
        {
            return Err(reject(
                CONTENT_BAD_RESPONSE_SCHEMA,
                meta.case_count_span.start,
                meta.case_count_span.end,
            ));
        }
    }

    for record in records {
        if let RecordPayload::Feedback {
            feedback_code,
            predicate_result_ref,
            ..
        } = record.record.payload
        {
            let Detail::Feedback { predicate_span } = record.meta.detail else {
                unreachable!()
            };
            let valid = match feedback_code {
                FEEDBACK_NEUTRAL | FEEDBACK_LIMITATION => predicate_result_ref == 0,
                FEEDBACK_MATCH | FEEDBACK_NO_MATCH | FEEDBACK_ALTERNATIVE => {
                    predicate_result_ref != 0
                }
                _ => false,
            };
            if !valid {
                return Err(reject(
                    CONTENT_BAD_FEEDBACK,
                    predicate_span.start,
                    predicate_span.end,
                ));
            }
        }
    }
    for record in records {
        let RecordPayload::LessonNode {
            role,
            answer_mode,
            predicate_result_ref,
            ref cases,
            default_feedback_ref,
            ..
        } = record.record.payload
        else {
            continue;
        };
        let Detail::LessonNode(ref meta) = record.meta.detail else {
            unreachable!()
        };
        for (case, case_meta) in cases.iter().zip(&meta.cases) {
            let (code, predicate) = feedback(records, case.feedback_ref);
            let valid = if case.case_class == CASE_ACCEPTED {
                code == FEEDBACK_MATCH && predicate == predicate_result_ref
            } else {
                code == FEEDBACK_ALTERNATIVE && predicate != 0
            };
            if !valid {
                return Err(reject(
                    CONTENT_BAD_FEEDBACK,
                    case_meta.feedback_span.start,
                    case_meta.feedback_span.end,
                ));
            }
        }
        let (code, predicate) = feedback(records, default_feedback_ref);
        let valid = match (role, answer_mode) {
            (ROLE_PRACTICE, ANSWER_PACKED_PRACTICE) => {
                code == FEEDBACK_NO_MATCH && predicate == predicate_result_ref
            }
            (ROLE_HEURISTIC, ANSWER_UNSCORED) => code == FEEDBACK_LIMITATION && predicate == 0,
            _ => code == FEEDBACK_NEUTRAL && predicate == 0,
        };
        if !valid {
            return Err(reject(
                CONTENT_BAD_FEEDBACK,
                meta.default_feedback_span.start,
                meta.default_feedback_span.end,
            ));
        }
    }
    Ok(())
}

fn success_edges(record: &DecodedRecord) -> Vec<(u16, Span)> {
    let RecordPayload::LessonNode {
        answer_mode,
        ref cases,
        default_next_node_ref,
        ..
    } = record.record.payload
    else {
        return Vec::new();
    };
    let Detail::LessonNode(ref meta) = record.meta.detail else {
        unreachable!()
    };
    if answer_mode == ANSWER_PACKED_PRACTICE {
        cases
            .iter()
            .zip(&meta.cases)
            .filter(|(case, _)| case.case_class == CASE_ACCEPTED)
            .map(|(case, data)| (case.next_node_ref, data.next_span))
            .collect()
    } else {
        vec![(
            default_next_node_ref,
            record.meta.controls.last().unwrap().span,
        )]
    }
}

fn validate_budgets(records: &[DecodedRecord], root_id: u16) -> Result<()> {
    let lessons: Vec<u16> = records
        .iter()
        .filter(|record| record.record.kind() == CONTENT_KIND_LESSON_NODE)
        .map(|record| record.record.record_id)
        .collect();
    let mut adjacency = BTreeMap::<u16, Vec<(u16, Span)>>::new();
    let mut reverse = BTreeMap::<u16, Vec<u16>>::new();
    for id in &lessons {
        let record = &records[find_record(records, *id).unwrap()];
        let edges = success_edges(record);
        for (target, _) in &edges {
            if *target != 0 {
                reverse.entry(*target).or_default().push(*id);
            }
        }
        adjacency.insert(*id, edges);
    }
    let mut visited = BTreeSet::new();
    let mut order = Vec::new();
    for &start in &lessons {
        if visited.contains(&start) {
            continue;
        }
        let mut stack = vec![(start, false)];
        while let Some((node, done)) = stack.pop() {
            if done {
                order.push(node);
                continue;
            }
            if !visited.insert(node) {
                continue;
            }
            stack.push((node, true));
            for (target, _) in &adjacency[&node] {
                if *target != 0 && !visited.contains(target) {
                    stack.push((*target, false));
                }
            }
        }
    }
    let mut component = BTreeMap::new();
    let mut component_id = 0usize;
    for &start in order.iter().rev() {
        if component.contains_key(&start) {
            continue;
        }
        component_id += 1;
        let mut stack = vec![start];
        while let Some(node) = stack.pop() {
            if component.contains_key(&node) {
                continue;
            }
            component.insert(node, component_id);
            stack.extend(reverse.get(&node).into_iter().flatten().copied());
        }
    }
    let mut sizes = BTreeMap::new();
    for id in component.values() {
        *sizes.entry(*id).or_insert(0usize) += 1;
    }
    let mut cycle: Option<Span> = None;
    for (&source, edges) in &adjacency {
        for (target, span) in edges {
            if *target != 0
                && component[&source] == component[target]
                && (source == *target || sizes[&component[&source]] > 1)
            {
                if cycle.is_none_or(|current| span.start < current.start) {
                    cycle = Some(*span);
                }
            }
        }
    }
    if let Some(span) = cycle {
        return Err(reject(CONTENT_BAD_CONTROL_EDGE, span.start, span.end));
    }

    for record in records {
        if let RecordPayload::LessonNode {
            max_selections,
            item_event_budget,
            ..
        } = record.record.payload
        {
            let Detail::LessonNode(ref meta) = record.meta.detail else {
                unreachable!()
            };
            if item_event_budget == 0 || (item_event_budget as usize) < max_selections as usize + 1
            {
                return Err(reject(
                    CONTENT_BUDGET_PROOF,
                    meta.budget_span.start,
                    meta.budget_span.end,
                ));
            }
        }
    }
    let root = &records[find_record(records, root_id).unwrap()];
    let RecordPayload::Root {
        entry_node_ref,
        global_event_budget,
    } = root.record.payload
    else {
        unreachable!()
    };
    let Detail::Root { budget_span } = root.meta.detail else {
        unreachable!()
    };
    if global_event_budget == 0 {
        return Err(reject(
            CONTENT_BUDGET_PROOF,
            budget_span.start,
            budget_span.end,
        ));
    }
    let mut cost = BTreeMap::<u16, usize>::new();
    for node in order {
        let record = &records[find_record(records, node).unwrap()];
        let RecordPayload::LessonNode {
            item_event_budget, ..
        } = record.record.payload
        else {
            unreachable!()
        };
        let tail = adjacency[&node]
            .iter()
            .map(|(target, _)| if *target == 0 { 0 } else { cost[target] })
            .max()
            .unwrap_or(0);
        cost.insert(
            node,
            (item_event_budget as usize + tail).min(global_event_budget as usize + 1),
        );
    }
    if cost[&entry_node_ref] > global_event_budget as usize {
        return Err(reject(
            CONTENT_BUDGET_PROOF,
            budget_span.start,
            budget_span.end,
        ));
    }
    Ok(())
}

pub fn stream_validation(raw: &[u8]) -> Result<ContentProjection> {
    let framed = frame(raw)?;
    let mut records = Vec::with_capacity(framed.len());
    let mut binding_keys = BTreeSet::new();
    for record in framed {
        if record.kind == CONTENT_KIND_SEMANTIC_BINDING {
            let start = record.payload.start;
            let class = raw[start];
            if matches!(class, BINDING_DATA | BINDING_PREDICATE) {
                let namespace = u16::from_be_bytes([raw[start + 2], raw[start + 3]]);
                let semantic = u16::from_be_bytes([raw[start + 4], raw[start + 5]]);
                if !binding_keys.insert((class, namespace, semantic)) {
                    return Err(reject(CONTENT_DUPLICATE, start, start + 1));
                }
            }
        }
        let (payload, meta) = decode_local(raw, record)?;
        records.push(DecodedRecord {
            record: Record {
                record_id: record.id,
                payload,
            },
            raw: record,
            meta,
        });
    }
    validate_derived(raw, &mut records)?;
    let root_id = validate_graph(&records)?;
    validate_lessons(&records)?;
    validate_passive_traces(&records)?;
    validate_budgets(&records, root_id)?;
    Ok(ContentProjection {
        version: CONTENT_VERSION as u16,
        root_record_id: root_id,
        records: records.into_iter().map(|record| record.record).collect(),
    })
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Event {
    node_id: u16,
    action: [u8; 4],
    result: u8,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RunState {
    root_record_id: u16,
    current_node_id: u16,
    global_remaining: u16,
    local_remaining: u16,
    phase: u8,
    outcome: u8,
    buffer: Vec<u16>,
    committed_response: Vec<u8>,
    feedback_ref: u16,
    next_node_ref: u16,
    events: Rc<Vec<Event>>,
}

impl RunState {
    pub fn current_node_id(&self) -> u16 {
        self.current_node_id
    }
    pub fn global_remaining(&self) -> u16 {
        self.global_remaining
    }
    pub fn local_remaining(&self) -> u16 {
        self.local_remaining
    }
    pub fn phase(&self) -> u8 {
        self.phase
    }
    pub fn outcome(&self) -> u8 {
        self.outcome
    }
    pub fn feedback_ref(&self) -> u16 {
        self.feedback_ref
    }
    pub fn next_node_ref(&self) -> u16 {
        self.next_node_ref
    }
    pub fn buffer(&self) -> &[u16] {
        &self.buffer
    }
}

fn projection_record(projection: &ContentProjection, id: u16) -> &Record {
    &projection.records[projection
        .records
        .binary_search_by_key(&id, |record| record.record_id)
        .unwrap()]
}

fn lesson(projection: &ContentProjection, id: u16) -> &RecordPayload {
    let payload = &projection_record(projection, id).payload;
    assert!(matches!(payload, RecordPayload::LessonNode { .. }));
    payload
}

fn root_payload(projection: &ContentProjection) -> (u16, u16) {
    let RecordPayload::Root {
        entry_node_ref,
        global_event_budget,
    } = projection_record(projection, projection.root_record_id).payload
    else {
        unreachable!()
    };
    (entry_node_ref, global_event_budget)
}

pub fn new_run(projection: &ContentProjection) -> RunState {
    let (entry, global) = root_payload(projection);
    let RecordPayload::LessonNode {
        item_event_budget, ..
    } = lesson(projection, entry)
    else {
        unreachable!()
    };
    RunState {
        root_record_id: projection.root_record_id,
        current_node_id: entry,
        global_remaining: global,
        local_remaining: *item_event_budget,
        phase: PHASE_ACTIVE,
        outcome: OUTCOME_NONE,
        buffer: Vec::new(),
        committed_response: Vec::new(),
        feedback_ref: 0,
        next_node_ref: 0,
        events: Rc::new(Vec::new()),
    }
}

fn normalize_action(raw: &[u8]) -> ([u8; 4], bool) {
    if raw.len() != CONTENT_ACTION_BYTES as usize {
        return ([0; 4], false);
    }
    let action = [raw[0], raw[1], raw[2], raw[3]];
    if !matches!(action[0], ACTION_SELECT | ACTION_RESET | ACTION_COMMIT)
        || action[1] != 0
        || (action[0] != ACTION_SELECT && action[2..] != [0, 0])
    {
        ([0; 4], false)
    } else {
        (action, true)
    }
}

fn transition(
    projection: &ContentProjection,
    state: &mut RunState,
    raw_action: &[u8],
    log: bool,
) -> u8 {
    if state.phase == PHASE_COMMITTED {
        return INTERACTION_ALREADY_COMMITTED;
    }
    if state.phase == PHASE_EXHAUSTED {
        return INTERACTION_BUDGET_EXHAUSTED;
    }
    let (action, valid) = normalize_action(raw_action);
    state.global_remaining -= 1;
    state.local_remaining -= 1;
    let RecordPayload::LessonNode {
        response_shape,
        flags,
        region_set_ref,
        max_selections,
        cases,
        default_feedback_ref,
        default_next_node_ref,
        answer_mode,
        ..
    } = lesson(projection, state.current_node_id)
    else {
        unreachable!()
    };
    let result = if !valid {
        INTERACTION_INVALID_ACTION
    } else if action[0] == ACTION_SELECT {
        let id = u16::from_be_bytes([action[2], action[3]]);
        let region_record = projection_record(projection, *region_set_ref);
        let RecordPayload::RegionSet { regions, .. } = &region_record.payload else {
            unreachable!()
        };
        if !regions
            .iter()
            .any(|region| region.region_id == id && region.flags & REGION_SELECTABLE != 0)
        {
            INTERACTION_INVALID_REGION
        } else if (*response_shape != RESPONSE_SEQUENCE
            || *flags & LESSON_ALLOW_REPEATED_SELECTIONS == 0)
            && state.buffer.contains(&id)
        {
            INTERACTION_DUPLICATE
        } else if state.buffer.len() >= *max_selections as usize {
            INTERACTION_OVER_LIMIT
        } else {
            if *response_shape == RESPONSE_SET {
                let at = state.buffer.binary_search(&id).unwrap_err();
                state.buffer.insert(at, id);
            } else {
                state.buffer.push(id);
            }
            INTERACTION_SELECTED
        }
    } else if action[0] == ACTION_RESET {
        state.buffer.clear();
        INTERACTION_RESET
    } else {
        let response = response_bytes(*response_shape, &state.buffer);
        let chosen = cases.iter().find(|case| case.region_ids == state.buffer);
        let (class, feedback, next) = chosen
            .map_or((0, *default_feedback_ref, *default_next_node_ref), |case| {
                (case.case_class, case.feedback_ref, case.next_node_ref)
            });
        state.outcome = if *answer_mode == ANSWER_PACKED_PRACTICE {
            if class == CASE_ACCEPTED {
                OUTCOME_ACCEPTED
            } else {
                OUTCOME_REJECTED
            }
        } else {
            OUTCOME_NEUTRAL
        };
        state.feedback_ref = feedback;
        state.next_node_ref = next;
        state.buffer.clear();
        state.committed_response = response;
        state.phase = PHASE_COMMITTED;
        INTERACTION_COMMITTED
    };
    if log {
        Rc::make_mut(&mut state.events).push(Event {
            node_id: state.current_node_id,
            action,
            result,
        });
    }
    if result != INTERACTION_COMMITTED
        && (state.global_remaining == 0 || state.local_remaining == 0)
    {
        state.phase = PHASE_EXHAUSTED;
    }
    result
}

pub fn step(
    projection: &ContentProjection,
    mut state: RunState,
    raw_action: &[u8],
) -> (RunState, u8) {
    let result = transition(projection, &mut state, raw_action, true);
    (state, result)
}

pub fn advance_committed(
    projection: &ContentProjection,
    state: &RunState,
) -> std::result::Result<RunState, InvalidHostState> {
    if state.phase != PHASE_COMMITTED || state.next_node_ref == 0 {
        return Err(InvalidHostState);
    }
    let mut next = state.clone();
    next.current_node_id = state.next_node_ref;
    next.outcome = OUTCOME_NONE;
    next.committed_response.clear();
    next.feedback_ref = 0;
    next.next_node_ref = 0;
    next.buffer.clear();
    if next.global_remaining == 0 {
        next.phase = PHASE_EXHAUSTED;
        next.local_remaining = 0;
    } else {
        let RecordPayload::LessonNode {
            item_event_budget, ..
        } = lesson(projection, next.current_node_id)
        else {
            unreachable!()
        };
        next.phase = PHASE_ACTIVE;
        next.local_remaining = (*item_event_budget).min(next.global_remaining);
    }
    Ok(next)
}

pub fn encode_run_state(state: &RunState) -> Vec<u8> {
    let response = if state.phase == PHASE_COMMITTED {
        &state.committed_response[..]
    } else {
        &[][..]
    };
    let mut output =
        Vec::with_capacity(18 + state.buffer.len() * 2 + response.len() + state.events.len() * 7);
    output.extend_from_slice(&(CONTENT_VERSION as u16).to_be_bytes());
    output.extend_from_slice(&state.root_record_id.to_be_bytes());
    output.extend_from_slice(&state.current_node_id.to_be_bytes());
    output.extend_from_slice(&state.global_remaining.to_be_bytes());
    output.extend_from_slice(&state.local_remaining.to_be_bytes());
    output.push(state.phase);
    output.push(state.outcome);
    output.extend_from_slice(&(state.buffer.len() as u16).to_be_bytes());
    for id in &state.buffer {
        output.extend_from_slice(&id.to_be_bytes());
    }
    output.extend_from_slice(&(response.len() as u16).to_be_bytes());
    output.extend_from_slice(response);
    output.extend_from_slice(&(state.events.len() as u16).to_be_bytes());
    for event in state.events.iter() {
        output.extend_from_slice(&event.node_id.to_be_bytes());
        output.extend_from_slice(&event.action);
        output.push(event.result);
    }
    output
}

fn bad_state(start: usize, end: usize) -> ContentReject {
    reject(CONTENT_BAD_RUN_STATE, start, end)
}

fn state_u16(raw: &[u8], at: &mut usize) -> Result<(u16, Span)> {
    if raw.len().saturating_sub(*at) < 2 {
        return Err(bad_state(raw.len(), raw.len()));
    }
    let span = Span {
        start: *at,
        end: *at + 2,
    };
    *at += 2;
    Ok((
        u16::from_be_bytes([raw[span.start], raw[span.start + 1]]),
        span,
    ))
}

fn validate_selection(
    shape: u8,
    flags: u8,
    maximum: u16,
    selectable: &BTreeSet<u16>,
    ids: &[u16],
    count_span: Span,
    spans: &[Span],
) -> Result<()> {
    if (shape == RESPONSE_SINGLE && ids.len() > 1) || ids.len() > maximum as usize {
        return Err(bad_state(count_span.start, count_span.end));
    }
    let mut seen = BTreeSet::new();
    for (index, id) in ids.iter().enumerate() {
        let span = spans[index];
        if *id == 0 || !selectable.contains(id) {
            return Err(bad_state(span.start, span.end));
        }
        if shape == RESPONSE_SET && index > 0 && ids[index - 1] >= *id {
            return Err(bad_state(span.start, span.end));
        }
        if (shape != RESPONSE_SEQUENCE || flags & LESSON_ALLOW_REPEATED_SELECTIONS == 0)
            && !seen.insert(*id)
        {
            return Err(bad_state(span.start, span.end));
        }
    }
    Ok(())
}

fn retain_candidates(
    candidates: &mut Vec<RunState>,
    span: Span,
    matches: impl Fn(&RunState) -> bool,
) -> Result<()> {
    candidates.retain(matches);
    if candidates.is_empty() {
        Err(bad_state(span.start, span.end))
    } else {
        Ok(())
    }
}

pub fn validate_run_state(projection: &ContentProjection, raw: &[u8]) -> Result<RunState> {
    if raw.len() > CONTENT_MAX_RUN_STATE_BYTES as usize {
        return Err(reject(
            CONTENT_LIMIT_EXCEEDED,
            CONTENT_MAX_RUN_STATE_BYTES as usize,
            CONTENT_MAX_RUN_STATE_BYTES as usize + 1,
        ));
    }
    if raw.len() < 11 {
        return Err(bad_state(raw.len(), raw.len()));
    }
    let phase = raw[10];
    if !matches!(phase, PHASE_ACTIVE | PHASE_COMMITTED | PHASE_EXHAUSTED) {
        return Err(bad_state(10, 11));
    }
    if phase == PHASE_EXHAUSTED && raw.len() > CONTENT_MAX_EXHAUSTED_RUN_STATE_BYTES as usize {
        return Err(reject(
            CONTENT_LIMIT_EXCEEDED,
            CONTENT_MAX_EXHAUSTED_RUN_STATE_BYTES as usize,
            CONTENT_MAX_EXHAUSTED_RUN_STATE_BYTES as usize + 1,
        ));
    }

    let mut at = 0usize;
    let (version, version_span) = state_u16(raw, &mut at)?;
    let (root_id, root_span) = state_u16(raw, &mut at)?;
    let (current_id, current_span) = state_u16(raw, &mut at)?;
    let (global, global_span) = state_u16(raw, &mut at)?;
    let (local, local_span) = state_u16(raw, &mut at)?;
    at += 1;
    let outcome_span = Span {
        start: at,
        end: at + 1,
    };
    let outcome = raw[at];
    at += 1;
    let (buffer_count, buffer_count_span) = state_u16(raw, &mut at)?;
    if buffer_count as usize > CONTENT_MAX_SELECTIONS as usize {
        return Err(bad_state(buffer_count_span.start, buffer_count_span.end));
    }
    let buffer_start = at;
    let buffer_bytes = (buffer_count as usize)
        .checked_mul(2)
        .ok_or_else(|| bad_state(buffer_count_span.start, buffer_count_span.end))?;
    if raw.len().saturating_sub(at) < buffer_bytes {
        return Err(bad_state(raw.len(), raw.len()));
    }
    at += buffer_bytes;
    let (response_length, response_length_span) = state_u16(raw, &mut at)?;
    if response_length > 8195 {
        return Err(bad_state(
            response_length_span.start,
            response_length_span.end,
        ));
    }
    if raw.len().saturating_sub(at) < response_length as usize {
        return Err(bad_state(raw.len(), raw.len()));
    }
    let response_span = Span {
        start: at,
        end: at + response_length as usize,
    };
    at = response_span.end;
    let (event_count, event_count_span) = state_u16(raw, &mut at)?;
    let events_start = at;
    let event_bytes = (event_count as usize)
        .checked_mul(CONTENT_EVENT_BYTES as usize)
        .ok_or_else(|| bad_state(event_count_span.start, event_count_span.end))?;
    if raw.len().saturating_sub(at) < event_bytes {
        return Err(bad_state(raw.len(), raw.len()));
    }
    at += event_bytes;
    if at != raw.len() {
        return Err(bad_state(at, at + 1));
    }

    let mut buffer = Vec::with_capacity(buffer_count as usize);
    let mut buffer_spans = Vec::with_capacity(buffer_count as usize);
    for start in (buffer_start..buffer_start + buffer_bytes).step_by(2) {
        buffer.push(u16::from_be_bytes([raw[start], raw[start + 1]]));
        buffer_spans.push(Span {
            start,
            end: start + 2,
        });
    }
    let response = raw[response_span.start..response_span.end].to_vec();
    let mut events = Vec::with_capacity(event_count as usize);
    let mut event_spans = Vec::with_capacity(event_count as usize);
    for start in (events_start..events_start + event_bytes).step_by(CONTENT_EVENT_BYTES as usize) {
        let node_id = u16::from_be_bytes([raw[start], raw[start + 1]]);
        let action = [
            raw[start + 2],
            raw[start + 3],
            raw[start + 4],
            raw[start + 5],
        ];
        let result = raw[start + 6];
        events.push(Event {
            node_id,
            action,
            result,
        });
        event_spans.push(start);
    }

    if version != CONTENT_VERSION as u16 {
        return Err(bad_state(version_span.start, version_span.end));
    }
    if root_id != projection.root_record_id {
        return Err(bad_state(root_span.start, root_span.end));
    }
    let Ok(current_index) = projection
        .records
        .binary_search_by_key(&current_id, |record| record.record_id)
    else {
        return Err(bad_state(current_span.start, current_span.end));
    };
    if !matches!(
        projection.records[current_index].payload,
        RecordPayload::LessonNode { .. }
    ) {
        return Err(bad_state(current_span.start, current_span.end));
    }
    let (_, root_budget) = root_payload(projection);
    if global > root_budget {
        return Err(bad_state(global_span.start, global_span.end));
    }
    let RecordPayload::LessonNode {
        item_event_budget,
        response_shape,
        flags,
        region_set_ref,
        max_selections,
        cases,
        default_feedback_ref,
        default_next_node_ref,
        answer_mode,
        ..
    } = lesson(projection, current_id)
    else {
        unreachable!()
    };
    if local > *item_event_budget || local > global {
        return Err(bad_state(local_span.start, local_span.end));
    }
    let mut rule_four = None;
    if (phase == PHASE_ACTIVE && (global == 0 || local == 0))
        || (phase == PHASE_EXHAUSTED && global != 0 && local != 0)
    {
        retain_earliest(&mut rule_four, bad_state(10, 11));
    }
    if phase != PHASE_COMMITTED {
        if outcome != OUTCOME_NONE {
            retain_earliest(
                &mut rule_four,
                bad_state(outcome_span.start, outcome_span.end),
            );
        }
        if response_length != 0 {
            retain_earliest(
                &mut rule_four,
                bad_state(response_length_span.start, response_length_span.end),
            );
        }
    } else if !matches!(
        outcome,
        OUTCOME_ACCEPTED | OUTCOME_REJECTED | OUTCOME_NEUTRAL
    ) {
        retain_earliest(
            &mut rule_four,
            bad_state(outcome_span.start, outcome_span.end),
        );
    }
    if phase == PHASE_COMMITTED && buffer_count != 0 {
        retain_earliest(
            &mut rule_four,
            bad_state(buffer_count_span.start, buffer_count_span.end),
        );
    }
    if buffer.len() > *max_selections as usize {
        retain_earliest(
            &mut rule_four,
            bad_state(buffer_count_span.start, buffer_count_span.end),
        );
    }
    let selectable = selectable_regions(
        &projection
            .records
            .iter()
            .map(|record| DecodedRecord {
                record: record.clone(),
                raw: RawRecord {
                    id: record.record_id,
                    kind: record.kind(),
                    header_start: 0,
                    length_span: Span { start: 0, end: 0 },
                    payload: Span { start: 0, end: 0 },
                },
                meta: Meta::default(),
            })
            .collect::<Vec<_>>(),
        *region_set_ref,
    );
    if let Err(candidate) = validate_selection(
        *response_shape,
        *flags,
        *max_selections,
        &selectable,
        &buffer,
        buffer_count_span,
        &buffer_spans,
    ) {
        retain_earliest(&mut rule_four, candidate);
    }

    let (feedback_ref, next_node_ref) = if phase == PHASE_COMMITTED {
        if response.first() != Some(response_shape) {
            retain_earliest(
                &mut rule_four,
                bad_state(response_span.start, response_span.start + 1),
            );
            (0, 0)
        } else if let Some(decoded) = decode_response(*response_shape, &response) {
            let response_count_span = Span {
                start: response_span.start + 1,
                end: response_span.start + 3,
            };
            let response_spans = (0..decoded.len())
                .map(|index| Span {
                    start: response_span.start + 3 + index * 2,
                    end: response_span.start + 5 + index * 2,
                })
                .collect::<Vec<_>>();
            if let Err(candidate) = validate_selection(
                *response_shape,
                *flags,
                *max_selections,
                &selectable,
                &decoded,
                response_count_span,
                &response_spans,
            ) {
                retain_earliest(&mut rule_four, candidate);
            }
            let chosen = cases.iter().find(|case| case.region_ids == decoded);
            let (class, feedback, next) = chosen
                .map_or((0, *default_feedback_ref, *default_next_node_ref), |case| {
                    (case.case_class, case.feedback_ref, case.next_node_ref)
                });
            let wanted_outcome = if *answer_mode == ANSWER_PACKED_PRACTICE {
                if class == CASE_ACCEPTED {
                    OUTCOME_ACCEPTED
                } else {
                    OUTCOME_REJECTED
                }
            } else {
                OUTCOME_NEUTRAL
            };
            if outcome != wanted_outcome {
                retain_earliest(
                    &mut rule_four,
                    bad_state(outcome_span.start, outcome_span.end),
                );
            }
            (feedback, next)
        } else {
            retain_earliest(
                &mut rule_four,
                bad_state(response_span.start, response_span.end),
            );
            (0, 0)
        }
    } else {
        (0, 0)
    };
    if event_count > root_budget {
        retain_earliest(
            &mut rule_four,
            bad_state(event_count_span.start, event_count_span.end),
        );
    }
    if let Some(candidate) = rule_four {
        return Err(candidate);
    }

    let mut replay = new_run(projection);
    for (event, start) in events.iter().zip(event_spans.iter().copied()) {
        if replay.phase == PHASE_COMMITTED && replay.next_node_ref != 0 {
            replay = advance_committed(projection, &replay).unwrap();
        }
        if replay.current_node_id != event.node_id || replay.phase != PHASE_ACTIVE {
            return Err(bad_state(start, start + 2));
        }
        let (normalized, callable) = normalize_action(&event.action);
        if normalized != event.action && event.action != [0; 4] {
            let bad = if !matches!(
                event.action[0],
                ACTION_SELECT | ACTION_RESET | ACTION_COMMIT
            ) {
                start + 2
            } else if event.action[1] != 0 {
                start + 3
            } else {
                start + 4
            };
            return Err(bad_state(
                bad,
                if bad == start + 4 { bad + 2 } else { bad + 1 },
            ));
        }
        let action: &[u8] = if callable { &event.action } else { &[] };
        let (next, actual) = step(projection, replay, action);
        replay = next;
        if actual != event.result {
            return Err(bad_state(start + 6, start + 7));
        }
    }
    let mut candidates = vec![replay.clone()];
    if replay.phase == PHASE_COMMITTED && replay.next_node_ref != 0 {
        candidates.push(advance_committed(projection, &replay).unwrap());
    }
    retain_candidates(&mut candidates, current_span, |candidate| {
        candidate.current_node_id == current_id
    })?;
    retain_candidates(&mut candidates, global_span, |candidate| {
        candidate.global_remaining == global
    })?;
    retain_candidates(&mut candidates, local_span, |candidate| {
        candidate.local_remaining == local
    })?;
    retain_candidates(&mut candidates, Span { start: 10, end: 11 }, |candidate| {
        candidate.phase == phase
    })?;
    retain_candidates(&mut candidates, outcome_span, |candidate| {
        candidate.outcome == outcome
    })?;
    retain_candidates(&mut candidates, buffer_count_span, |candidate| {
        candidate.buffer.len() == buffer.len()
    })?;
    for (index, span) in buffer_spans.iter().copied().enumerate() {
        retain_candidates(&mut candidates, span, |candidate| {
            candidate.buffer[index] == buffer[index]
        })?;
    }
    retain_candidates(&mut candidates, response_length_span, |candidate| {
        candidate.committed_response.len() == response.len()
    })?;
    for (index, (actual, span)) in response
        .iter()
        .zip(response_span.start..response_span.end)
        .enumerate()
    {
        retain_candidates(
            &mut candidates,
            Span {
                start: span,
                end: span + 1,
            },
            |candidate| candidate.committed_response[index] == *actual,
        )?;
    }
    let mut state = candidates.remove(0);
    state.feedback_ref = feedback_ref;
    state.next_node_ref = next_node_ref;
    Ok(state)
}

fn decode_response(shape: u8, raw: &[u8]) -> Option<Vec<u16>> {
    if raw.len() < 3 || raw[0] != shape {
        return None;
    }
    let count = u16::from_be_bytes([raw[1], raw[2]]) as usize;
    if raw.len() != 3 + count * 2 {
        return None;
    }
    Some(
        raw[3..]
            .chunks_exact(2)
            .map(|pair| u16::from_be_bytes([pair[0], pair[1]]))
            .collect(),
    )
}

fn validate_passive_traces(records: &[DecodedRecord]) -> Result<()> {
    let projection = ContentProjection {
        version: CONTENT_VERSION as u16,
        root_record_id: records.last().unwrap().record.record_id,
        records: records.iter().map(|record| record.record.clone()).collect(),
    };
    for owner in records {
        let RecordPayload::LessonNode {
            role,
            presentation_ref,
            region_set_ref,
            passive_trace_ref,
            item_event_budget,
            ..
        } = owner.record.payload
        else {
            continue;
        };
        if passive_trace_ref == 0 {
            continue;
        }
        let trace_record = &records[find_record(records, passive_trace_ref).unwrap()];
        let RecordPayload::PassiveTrace {
            presentation_ref: trace_presentation,
            region_set_ref: trace_regions,
            resulting_presentation_ref: _,
            limitation_text_ref,
            ref actions,
            expected_outcome,
            expected_feedback_ref,
            expected_next_node_ref,
        } = trace_record.record.payload
        else {
            unreachable!()
        };
        let Detail::LessonNode(ref owner_meta) = owner.meta.detail else {
            unreachable!()
        };
        let Detail::PassiveTrace {
            limitation_span,
            action_count_span,
            actions_start,
            outcome_span,
            feedback_span,
            next_span,
        } = trace_record.meta.detail
        else {
            unreachable!()
        };
        if trace_presentation != presentation_ref || trace_regions != region_set_ref {
            return Err(reject(
                CONTENT_BAD_PASSIVE_TRACE,
                owner_meta.trace_span.start,
                owner_meta.trace_span.end,
            ));
        }
        if (role == ROLE_HEURISTIC) != (limitation_text_ref != 0) {
            return Err(reject(
                CONTENT_BAD_PASSIVE_TRACE,
                limitation_span.start,
                limitation_span.end,
            ));
        }
        if actions.len() > item_event_budget as usize {
            return Err(reject(
                CONTENT_BAD_PASSIVE_TRACE,
                action_count_span.start,
                action_count_span.end,
            ));
        }
        let mut state = RunState {
            root_record_id: projection.root_record_id,
            current_node_id: owner.record.record_id,
            global_remaining: item_event_budget,
            local_remaining: item_event_budget,
            phase: PHASE_ACTIVE,
            outcome: OUTCOME_NONE,
            buffer: Vec::new(),
            committed_response: Vec::new(),
            feedback_ref: 0,
            next_node_ref: 0,
            events: Rc::new(Vec::new()),
        };
        for (index, action) in actions.iter().enumerate() {
            let result = transition(&projection, &mut state, action, false);
            let final_action = index + 1 == actions.len();
            let wanted = if final_action {
                INTERACTION_COMMITTED
            } else if action[0] == ACTION_SELECT {
                INTERACTION_SELECTED
            } else {
                INTERACTION_RESET
            };
            if result != wanted || final_action != (action[0] == ACTION_COMMIT) {
                let start = actions_start + index * 4;
                return Err(reject(CONTENT_BAD_PASSIVE_TRACE, start, start + 4));
            }
        }
        if state.outcome != expected_outcome {
            return Err(reject(
                CONTENT_BAD_PASSIVE_TRACE,
                outcome_span.start,
                outcome_span.end,
            ));
        }
        if state.feedback_ref != expected_feedback_ref {
            return Err(reject(
                CONTENT_BAD_PASSIVE_TRACE,
                feedback_span.start,
                feedback_span.end,
            ));
        }
        if state.next_node_ref != expected_next_node_ref {
            return Err(reject(
                CONTENT_BAD_PASSIVE_TRACE,
                next_span.start,
                next_span.end,
            ));
        }
    }
    Ok(())
}
