//! Independent compiler for the participant-revision logical slice declaration.

use super::{
    AtomicAssignment, Closure, SliceCompilation, SliceError, SliceInputs, TierRoot,
    assemble_frames, compile_slice_v0, error, hex_bytes, sha256_hex, stream_frames,
};
use gb_content::{
    ContentAuthoringProjection, FieldSpec, FieldValue, LessonCase, Record, RecordPayload, Region,
    encode_content_v0, projection_view, stream_validation,
};
use gb_foundation::validate_canonical_manifest;
use serde_json::{Map, Value};

const DECLARATION_MAX: usize = 1_048_576;
const LESSON_RECORDS_MAX: usize = 4096;
const SECTION_PAYLOAD_MAX: usize = 16_384;
const PATH: &str = "lesson_records.payload";

fn closed<'a>(value: &'a Value, keys: &[&str]) -> Result<&'a Map<String, Value>, SliceError> {
    let object = value.as_object().ok_or_else(|| error("bad_shape", PATH))?;
    if object.len() != keys.len() || keys.iter().any(|key| !object.contains_key(*key)) {
        return Err(error("closed_shape", PATH));
    }
    Ok(object)
}

fn unsigned(value: &Value, maximum: u64) -> Result<u64, SliceError> {
    let number = value.as_u64().ok_or_else(|| error("bad_type", PATH))?;
    if number > maximum {
        return Err(error("bad_value", PATH));
    }
    Ok(number)
}

fn u16_field(object: &Map<String, Value>, name: &str) -> Result<u16, SliceError> {
    Ok(unsigned(&object[name], u64::from(u16::MAX))? as u16)
}

fn u8_field(object: &Map<String, Value>, name: &str) -> Result<u8, SliceError> {
    Ok(unsigned(&object[name], u64::from(u8::MAX))? as u8)
}

fn array(value: &Value, maximum: usize) -> Result<&[Value], SliceError> {
    let values = value.as_array().ok_or_else(|| error("bad_type", PATH))?;
    if values.len() > maximum {
        return Err(error("limit_exceeded", PATH));
    }
    Ok(values)
}

fn atoms(value: &Value) -> Result<Vec<u32>, SliceError> {
    array(value, 65_535)?
        .iter()
        .map(|value| unsigned(value, u64::from(u32::MAX)).map(|number| number as u32))
        .collect()
}

fn region(value: &Value) -> Result<Region, SliceError> {
    let object = closed(
        value,
        &[
            "region_id",
            "label_ref",
            "row_start",
            "row_end",
            "column_start",
            "column_end",
            "flags",
        ],
    )?;
    Ok(Region {
        region_id: u16_field(object, "region_id")?,
        label_ref: u16_field(object, "label_ref")?,
        row_start: u16_field(object, "row_start")?,
        row_end: u16_field(object, "row_end")?,
        column_start: u16_field(object, "column_start")?,
        column_end: u16_field(object, "column_end")?,
        flags: u8_field(object, "flags")?,
    })
}

fn case(value: &Value) -> Result<LessonCase, SliceError> {
    let object = closed(
        value,
        &["case_class", "region_ids", "feedback_ref", "next_node_ref"],
    )?;
    Ok(LessonCase {
        case_class: u8_field(object, "case_class")?,
        region_ids: array(&object["region_ids"], 4096)?
            .iter()
            .map(|value| unsigned(value, u64::from(u16::MAX)).map(|number| number as u16))
            .collect::<Result<_, _>>()?,
        feedback_ref: u16_field(object, "feedback_ref")?,
        next_node_ref: u16_field(object, "next_node_ref")?,
    })
}

fn record(value: &Value, ordinal: usize) -> Result<Record, SliceError> {
    let object = closed(value, &["record_id", "kind", "payload"])?;
    let id = u16_field(object, "record_id")?;
    if usize::from(id) != ordinal + 1 {
        return Err(error("record_order", "lesson_records"));
    }
    let payload = &object["payload"];
    let payload = match u16_field(object, "kind")? {
        2 => {
            let object = closed(
                payload,
                &["atom_class", "atom_width", "min_value", "max_value"],
            )?;
            if u8_field(object, "atom_class")? != 1
                || u8_field(object, "atom_width")? != 1
                || unsigned(&object["min_value"], u64::from(u32::MAX))? != 0
                || unsigned(&object["max_value"], u64::from(u32::MAX))? != 255
            {
                return Err(error("byte_schema", PATH));
            }
            RecordPayload::AtomSchema {
                atom_class: 1,
                atom_width: 1,
                entries: Vec::new(),
                min_value: Some(0),
                max_value: Some(255),
                allowed_mask: None,
            }
        }
        3 => {
            let object = closed(payload, &["atom_schema_ref", "atoms"])?;
            RecordPayload::AtomVector {
                atom_schema_ref: u16_field(object, "atom_schema_ref")?,
                atoms: atoms(&object["atoms"])?,
            }
        }
        4 => {
            let object = closed(payload, &["atom_schema_ref", "rows", "columns", "cells"])?;
            RecordPayload::Matrix {
                atom_schema_ref: u16_field(object, "atom_schema_ref")?,
                rows: u16_field(object, "rows")?,
                columns: u16_field(object, "columns")?,
                cells: atoms(&object["cells"])?,
            }
        }
        7 => {
            let object = closed(payload, &["surface_matrix_ref", "regions"])?;
            RecordPayload::RegionSet {
                surface_matrix_ref: u16_field(object, "surface_matrix_ref")?,
                regions: array(&object["regions"], 4096)?
                    .iter()
                    .map(region)
                    .collect::<Result<_, _>>()?,
            }
        }
        8 => {
            let object = closed(
                payload,
                &[
                    "binding_class",
                    "namespace_id",
                    "semantic_code",
                    "argument",
                    "auxiliary",
                ],
            )?;
            RecordPayload::SemanticBinding {
                binding_class: u8_field(object, "binding_class")?,
                namespace_id: u16_field(object, "namespace_id")?,
                semantic_code: u16_field(object, "semantic_code")?,
                argument: u16_field(object, "argument")?,
                auxiliary: u16_field(object, "auxiliary")?,
            }
        }
        9 => {
            let object = closed(payload, &["data_binding_ref", "data"])?;
            RecordPayload::OpaqueData {
                data_binding_ref: u16_field(object, "data_binding_ref")?,
                data: atoms(&object["data"])?,
            }
        }
        10 => {
            let object = closed(
                payload,
                &[
                    "predicate_binding_ref",
                    "subject_opaque_data_ref",
                    "result_atom_vector_ref",
                ],
            )?;
            RecordPayload::PredicateResult {
                predicate_binding_ref: u16_field(object, "predicate_binding_ref")?,
                subject_opaque_data_ref: u16_field(object, "subject_opaque_data_ref")?,
                result_atom_vector_ref: u16_field(object, "result_atom_vector_ref")?,
            }
        }
        11 => {
            let object = closed(
                payload,
                &["feedback_code", "display_ref", "predicate_result_ref"],
            )?;
            RecordPayload::Feedback {
                feedback_code: u16_field(object, "feedback_code")?,
                display_ref: u16_field(object, "display_ref")?,
                predicate_result_ref: u16_field(object, "predicate_result_ref")?,
            }
        }
        12 => {
            let object = closed(
                payload,
                &[
                    "presentation_ref",
                    "region_set_ref",
                    "resulting_presentation_ref",
                    "limitation_text_ref",
                    "actions",
                    "expected_outcome",
                    "expected_feedback_ref",
                    "expected_next_node_ref",
                ],
            )?;
            let actions = array(&object["actions"], 65_535)?
                .iter()
                .map(|value| {
                    let value = value.as_str().ok_or_else(|| error("bad_type", PATH))?;
                    if value.len() != 8 {
                        return Err(error("bad_hex", PATH));
                    }
                    let bytes = hex_bytes(value, PATH)?;
                    <[u8; 4]>::try_from(bytes.as_slice()).map_err(|_| error("bad_hex", PATH))
                })
                .collect::<Result<_, _>>()?;
            RecordPayload::PassiveTrace {
                presentation_ref: u16_field(object, "presentation_ref")?,
                region_set_ref: u16_field(object, "region_set_ref")?,
                resulting_presentation_ref: u16_field(object, "resulting_presentation_ref")?,
                limitation_text_ref: u16_field(object, "limitation_text_ref")?,
                actions,
                expected_outcome: u8_field(object, "expected_outcome")?,
                expected_feedback_ref: u16_field(object, "expected_feedback_ref")?,
                expected_next_node_ref: u16_field(object, "expected_next_node_ref")?,
            }
        }
        13 => {
            let object = closed(
                payload,
                &[
                    "role",
                    "response_shape",
                    "answer_mode",
                    "flags",
                    "presentation_ref",
                    "region_set_ref",
                    "predicate_result_ref",
                    "passive_trace_ref",
                    "max_selections",
                    "item_event_budget",
                    "cases",
                    "default_feedback_ref",
                    "default_next_node_ref",
                ],
            )?;
            RecordPayload::LessonNode {
                role: u8_field(object, "role")?,
                response_shape: u8_field(object, "response_shape")?,
                answer_mode: u8_field(object, "answer_mode")?,
                flags: u8_field(object, "flags")?,
                presentation_ref: u16_field(object, "presentation_ref")?,
                region_set_ref: u16_field(object, "region_set_ref")?,
                predicate_result_ref: u16_field(object, "predicate_result_ref")?,
                passive_trace_ref: u16_field(object, "passive_trace_ref")?,
                max_selections: u16_field(object, "max_selections")?,
                item_event_budget: u16_field(object, "item_event_budget")?,
                cases: array(&object["cases"], 4096)?
                    .iter()
                    .map(case)
                    .collect::<Result<_, _>>()?,
                default_feedback_ref: u16_field(object, "default_feedback_ref")?,
                default_next_node_ref: u16_field(object, "default_next_node_ref")?,
            }
        }
        14 => {
            let object = closed(payload, &["entry_node_ref", "global_event_budget"])?;
            RecordPayload::Root {
                entry_node_ref: u16_field(object, "entry_node_ref")?,
                global_event_budget: u16_field(object, "global_event_budget")?,
            }
        }
        _ => return Err(error("record_kind", "lesson_records")),
    };
    Ok(Record::authoring(id, payload))
}

fn append(records: &mut Vec<Record>, payload: RecordPayload) -> Result<u16, SliceError> {
    let id = u16::try_from(records.len() + 1).map_err(|_| error("limit_exceeded", "records"))?;
    records.push(Record::authoring(id, payload));
    Ok(id)
}

/// Compile only from the reviewed logical declaration and independently checked M1 inputs.
pub fn compile_slice_v1(
    declaration: &[u8],
    legacy: SliceInputs<'_>,
) -> Result<SliceCompilation, SliceError> {
    if declaration.len() > DECLARATION_MAX {
        return Err(error("input_too_large", "declaration"));
    }
    validate_canonical_manifest(declaration).map_err(|_| error("noncanonical", "declaration"))?;
    let value: Value =
        serde_json::from_slice(declaration).map_err(|_| error("bad_json", "declaration"))?;
    let object = closed(
        &value,
        &["schema", "legacy_declaration_sha256", "lesson_records"],
    )?;
    if object["schema"].as_str() != Some("golden-board.m2-slice/v1") {
        return Err(error("schema", "declaration"));
    }
    if object["legacy_declaration_sha256"].as_str() != Some(sha256_hex(legacy.declaration).as_str())
    {
        return Err(error("input_digest", "legacy_declaration_sha256"));
    }
    let historical = compile_slice_v0(legacy)?;
    let rows = array(&object["lesson_records"], LESSON_RECORDS_MAX)?;
    if rows.is_empty() {
        return Err(error("record_count", "lesson_records"));
    }
    let required_records = rows
        .iter()
        .enumerate()
        .map(|(index, value)| record(value, index))
        .collect::<Result<Vec<_>, _>>()?;
    if required_records[0].kind() != 2 {
        return Err(error("byte_schema", "lesson_records"));
    }
    let (entry, budget) = match required_records.last().map(Record::payload) {
        Some(RecordPayload::Root {
            entry_node_ref,
            global_event_budget,
        }) => (*entry_node_ref, *global_event_budget),
        _ => return Err(error("root", "lesson_records")),
    };
    let all_budget = budget
        .checked_add(64)
        .ok_or_else(|| error("limit_exceeded", "global_event_budget"))?;
    let required_root_id = required_records.last().unwrap().record_id();
    let required_stream = encode_content_v0(&ContentAuthoringProjection::new(
        0,
        required_records.clone(),
    ))
    .map_err(|_| error("content_reject", "required"))?;
    let required_projection = projection_view(
        &stream_validation(&required_stream).map_err(|_| error("content_reject", "required"))?,
    );
    let region_set = match required_records
        .get(usize::from(entry).wrapping_sub(1))
        .map(Record::payload)
    {
        Some(RecordPayload::LessonNode {
            region_set_ref,
            predicate_result_ref,
            ..
        }) if *predicate_result_ref != 0 => *region_set_ref,
        _ => return Err(error("entry_node", "lesson_records")),
    };
    match required_records
        .get(usize::from(region_set).wrapping_sub(1))
        .map(Record::payload)
    {
        Some(RecordPayload::RegionSet { regions, .. })
            if [1, 2].iter().all(|id| {
                regions
                    .iter()
                    .any(|region| region.region_id == *id && region.flags & 1 != 0)
            }) =>
        {
            ()
        }
        _ => return Err(error("entry_regions", "lesson_records")),
    }
    let (required_count, required_frames) = stream_frames(&required_stream)?;
    let mut assignments = Vec::new();
    let mut section = AtomicAssignment {
        closure: Closure::Required,
        section_id: 16,
        semantic_copy_id: 0,
        record_ids: Vec::new(),
    };
    let mut section_bytes = 0;
    for id in 1..required_root_id {
        let length = required_frames
            .get(&id)
            .ok_or_else(|| error("section_record", "required"))?
            .len();
        if length > SECTION_PAYLOAD_MAX {
            return Err(error("section_payload", "required"));
        }
        if section_bytes + length > SECTION_PAYLOAD_MAX {
            let next = section.section_id + 1;
            assignments.push(section);
            if next > 31 {
                return Err(error("section_count", "required"));
            }
            section = AtomicAssignment {
                closure: Closure::Required,
                section_id: next,
                semantic_copy_id: 0,
                record_ids: Vec::new(),
            };
            section_bytes = 0;
        }
        section.record_ids.push(id);
        section_bytes += length;
    }
    if section.record_ids.is_empty() {
        return Err(error("section_payload", "required"));
    }
    assignments.push(section);
    let mut all_records = required_records[..required_records.len() - 1].to_vec();
    let mut opaque_refs = Vec::with_capacity(74);
    for (namespace, first_section, payloads) in [
        (2, 100, &historical.game_payloads),
        (3, 200, &historical.fixture_payloads),
    ] {
        for (ordinal, data) in payloads.iter().enumerate() {
            let binding = append(
                &mut all_records,
                RecordPayload::SemanticBinding {
                    binding_class: 1,
                    namespace_id: namespace,
                    semantic_code: ordinal as u16 + 1,
                    argument: 1,
                    auxiliary: u16::try_from(data.len())
                        .map_err(|_| error("payload_length", "library"))?,
                },
            )?;
            let opaque = append(
                &mut all_records,
                RecordPayload::OpaqueData {
                    data_binding_ref: binding,
                    data: data.iter().copied().map(u32::from).collect(),
                },
            )?;
            opaque_refs.push(opaque);
            assignments.push(AtomicAssignment {
                closure: Closure::AllOnly,
                section_id: first_section + ordinal as u16,
                semantic_copy_id: 0,
                record_ids: vec![binding, opaque],
            });
        }
    }
    let text = append(&mut all_records, RecordPayload::Text("0".to_owned()))?;
    let payload_text = append(&mut all_records, RecordPayload::Text("1".to_owned()))?;
    let limitation = append(
        &mut all_records,
        RecordPayload::Text(
            "Inspecting raw records alone does not establish their chess meaning.".to_owned(),
        ),
    )?;
    let presentation = append(
        &mut all_records,
        RecordPayload::Matrix {
            atom_schema_ref: 1,
            rows: 1,
            columns: 1,
            cells: vec![74],
        },
    )?;
    let region_set = append(
        &mut all_records,
        RecordPayload::RegionSet {
            surface_matrix_ref: presentation,
            regions: vec![Region {
                region_id: 1,
                label_ref: 0,
                row_start: 0,
                row_end: 1,
                column_start: 0,
                column_end: 1,
                flags: 1,
            }],
        },
    )?;
    let fields = append(
        &mut all_records,
        RecordPayload::FieldSchema {
            fields: vec![
                FieldSpec {
                    name_text_ref: text,
                    storage: 2,
                    type_code: 4,
                    count: 1,
                },
                FieldSpec {
                    name_text_ref: payload_text,
                    storage: 2,
                    type_code: 9,
                    count: 74,
                },
            ],
        },
    )?;
    let library = append(
        &mut all_records,
        RecordPayload::Tuple {
            field_schema_ref: fields,
            field_values: vec![
                FieldValue::RecordRefs(vec![presentation]),
                FieldValue::RecordRefs(opaque_refs),
            ],
        },
    )?;
    let feedback = append(
        &mut all_records,
        RecordPayload::Feedback {
            feedback_code: 5,
            display_ref: library,
            predicate_result_ref: 0,
        },
    )?;
    let trace = append(
        &mut all_records,
        RecordPayload::PassiveTrace {
            presentation_ref: presentation,
            region_set_ref: region_set,
            resulting_presentation_ref: library,
            limitation_text_ref: limitation,
            actions: vec![[1, 0, 0, 1], [3, 0, 0, 0]],
            expected_outcome: 3,
            expected_feedback_ref: feedback,
            expected_next_node_ref: entry,
        },
    )?;
    let node = append(
        &mut all_records,
        RecordPayload::LessonNode {
            role: 4,
            response_shape: 1,
            answer_mode: 3,
            flags: 0,
            presentation_ref: presentation,
            region_set_ref: region_set,
            predicate_result_ref: 0,
            passive_trace_ref: trace,
            max_selections: 1,
            item_event_budget: 16,
            cases: Vec::new(),
            default_feedback_ref: feedback,
            default_next_node_ref: entry,
        },
    )?;
    assignments.push(AtomicAssignment {
        closure: Closure::AllOnly,
        section_id: 210,
        semantic_copy_id: 0,
        record_ids: (text..=node).collect(),
    });
    let all_root_id = append(
        &mut all_records,
        RecordPayload::Root {
            entry_node_ref: node,
            global_event_budget: all_budget,
        },
    )?;
    let all_stream = encode_content_v0(&ContentAuthoringProjection::new(0, all_records))
        .map_err(|_| error("content_reject", "all"))?;
    let all_projection = projection_view(
        &stream_validation(&all_stream).map_err(|_| error("content_reject", "all"))?,
    );
    let (all_count, all_frames) = stream_frames(&all_stream)?;
    if (1..required_root_id).any(|id| required_frames.get(&id) != all_frames.get(&id)) {
        return Err(error("shared_frame", "sections"));
    }
    for assignment in &assignments {
        let mut length = 0_usize;
        for id in &assignment.record_ids {
            length += all_frames
                .get(id)
                .ok_or_else(|| error("section_record", "sections"))?
                .len();
        }
        if length > SECTION_PAYLOAD_MAX {
            return Err(error("section_payload", "sections"));
        }
    }
    let required_body_ids = assignments
        .iter()
        .filter(|row| row.closure == Closure::Required)
        .flat_map(|row| row.record_ids.iter().copied());
    let all_body_ids = assignments
        .iter()
        .flat_map(|row| row.record_ids.iter().copied());
    if assemble_frames(
        required_count,
        required_body_ids,
        required_root_id,
        &required_frames,
    )? != required_stream
        || assemble_frames(all_count, all_body_ids, all_root_id, &all_frames)? != all_stream
    {
        return Err(error("tier_reassembly", "sections"));
    }
    let tier_roots = vec![
        TierRoot {
            closure: Closure::Required,
            section_id: 2,
            semantic_copy_id: 0,
            record_id: required_root_id,
            frame: required_frames[&required_root_id].clone(),
        },
        TierRoot {
            closure: Closure::All,
            section_id: 3,
            semantic_copy_id: 0,
            record_id: all_root_id,
            frame: all_frames[&all_root_id].clone(),
        },
    ];
    Ok(SliceCompilation {
        required_stream,
        all_stream,
        required_projection,
        all_projection,
        game_payloads: historical.game_payloads,
        fixture_payloads: historical.fixture_payloads,
        assignments,
        tier_roots,
        capacity_prototypes: historical.capacity_prototypes,
    })
}
