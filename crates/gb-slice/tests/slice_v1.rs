use std::collections::BTreeMap;

use gb_content::{
    RecordPayload, new_run, projection_view, run_state_view, step, stream_validation,
};
use gb_foundation::canonicalize_manifest;
use gb_slice::{Closure, SliceInputs, compile_slice_v0, compile_slice_v1};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

fn legacy() -> SliceInputs<'static> {
    SliceInputs {
        declaration: include_bytes!("../../../studies/m2/slice-v0.json"),
        content_fixture: include_bytes!("../../../conformance/content-v0.json"),
        chess_fixture: include_bytes!("../../../conformance/chess-v0.json"),
        game_set: include_bytes!("../../../reports/game-set-v0.bin"),
        content_spec: include_bytes!("../../../spec/content-v0.md"),
        constants: include_bytes!("../../../spec/constants-v0.toml"),
        curriculum: include_bytes!("../../../spec/curriculum-v0.toml"),
    }
}

fn declaration() -> Value {
    let payloads = vec![
        (
            2,
            json!({"atom_class":1,"atom_width":1,"min_value":0,"max_value":255}),
        ),
        (
            4,
            json!({"atom_schema_ref":1,"rows":2,"columns":3,"cells":[0,1,2,3,4,5]}),
        ),
        (
            7,
            json!({"surface_matrix_ref":2,"regions":[
                {"region_id":1,"label_ref":0,"row_start":0,"row_end":1,"column_start":0,"column_end":1,"flags":1},
                {"region_id":2,"label_ref":0,"row_start":1,"row_end":2,"column_start":2,"column_end":3,"flags":1}
            ]}),
        ),
        (3, json!({"atom_schema_ref":1,"atoms":[1]})),
        (
            8,
            json!({"binding_class":1,"namespace_id":40000,"semantic_code":1,"argument":1,"auxiliary":1}),
        ),
        (9, json!({"data_binding_ref":5,"data":[1]})),
        (
            8,
            json!({"binding_class":2,"namespace_id":40000,"semantic_code":1,"argument":5,"auxiliary":1}),
        ),
        (
            10,
            json!({"predicate_binding_ref":7,"subject_opaque_data_ref":6,"result_atom_vector_ref":4}),
        ),
        (
            11,
            json!({"feedback_code":2,"display_ref":2,"predicate_result_ref":8}),
        ),
        (
            11,
            json!({"feedback_code":3,"display_ref":2,"predicate_result_ref":8}),
        ),
        (
            12,
            json!({"presentation_ref":2,"region_set_ref":3,"resulting_presentation_ref":2,"limitation_text_ref":0,"actions":["01000001","03000000"],"expected_outcome":1,"expected_feedback_ref":9,"expected_next_node_ref":0}),
        ),
        (
            13,
            json!({"role":5,"response_shape":1,"answer_mode":1,"flags":0,"presentation_ref":2,"region_set_ref":3,"predicate_result_ref":8,"passive_trace_ref":11,"max_selections":1,"item_event_budget":16,"cases":[{"case_class":1,"region_ids":[1],"feedback_ref":9,"next_node_ref":0}],"default_feedback_ref":10,"default_next_node_ref":12}),
        ),
        (14, json!({"entry_node_ref":12,"global_event_budget":128})),
    ];
    json!({
        "schema":"golden-board.m2-slice/v1",
        "legacy_declaration_sha256": format!("{:x}",Sha256::digest(legacy().declaration)),
        "lesson_records":payloads.into_iter().enumerate().map(|(i,(kind,payload))|
            json!({"record_id":i+1,"kind":kind,"payload":payload})).collect::<Vec<_>>()
    })
}

fn raw(value: &Value) -> Vec<u8> {
    canonicalize_manifest(&serde_json::to_vec(value).unwrap()).unwrap()
}

fn frames(raw: &[u8]) -> BTreeMap<u16, &[u8]> {
    let mut result = BTreeMap::new();
    let mut at = 4;
    while at < raw.len() {
        let id = u16::from_be_bytes(raw[at..at + 2].try_into().unwrap());
        let length = u32::from_be_bytes(raw[at + 4..at + 8].try_into().unwrap()) as usize;
        result.insert(id, &raw[at..at + 8 + length]);
        at += 8 + length;
    }
    result
}

#[test]
fn independently_compiles_shared_teaching_and_atomic_canonical_games() {
    let compiled = compile_slice_v1(&raw(&declaration()), legacy()).unwrap();
    let historical = compile_slice_v0(legacy()).unwrap();
    assert_eq!(compiled.required_projection().records().len(), 13);
    assert_eq!(compiled.all_projection().records().len(), 171);
    assert_eq!(compiled.game_payloads(), historical.game_payloads());
    assert_eq!(compiled.fixture_payloads(), historical.fixture_payloads());
    assert_eq!(
        compiled.capacity_prototypes(),
        historical.capacity_prototypes()
    );
    let required = frames(compiled.required_stream());
    let all = frames(compiled.all_stream());
    for id in 1..13 {
        assert_eq!(required[&id], all[&id]);
    }
    assert_eq!(compiled.assignments().len(), 76);
    assert_eq!(compiled.assignments()[0].closure(), Closure::Required);
    assert_eq!(compiled.assignments()[0].section_id(), 16);
    assert_eq!(
        compiled.assignments()[0].record_ids(),
        &(1..13).collect::<Vec<_>>()
    );
    for (ordinal, payload) in historical.game_payloads().iter().enumerate() {
        let assignment = &compiled.assignments()[ordinal + 1];
        assert_eq!(assignment.section_id(), 100 + ordinal as u16);
        assert_eq!(assignment.closure(), Closure::AllOnly);
        assert_eq!(
            assignment.record_ids(),
            &[13 + 2 * ordinal as u16, 14 + 2 * ordinal as u16]
        );
        let record = &compiled.all_projection().records()[13 + 2 * ordinal];
        match record.payload() {
            RecordPayload::OpaqueData { data, .. } => assert_eq!(
                data,
                &payload.iter().copied().map(u32::from).collect::<Vec<_>>()
            ),
            _ => panic!("game must remain complete opaque data"),
        }
    }
    let support = compiled.assignments().last().unwrap();
    assert_eq!(support.section_id(), 210);
    assert_eq!(support.record_ids().len(), 10);
    for root in compiled.tier_roots() {
        let stream = if root.closure() == Closure::Required {
            compiled.required_stream()
        } else {
            compiled.all_stream()
        };
        let mut rebuilt = stream[..4].to_vec();
        for assignment in compiled
            .assignments()
            .iter()
            .filter(|a| root.closure() != Closure::Required || a.closure() == Closure::Required)
        {
            for id in assignment.record_ids() {
                rebuilt.extend_from_slice(all[id]);
            }
        }
        rebuilt.extend_from_slice(root.frame());
        assert_eq!(rebuilt, stream);
    }
}

#[test]
fn library_payload_is_reachable_by_neutral_inspection_without_scoring_a_match() {
    let compiled = compile_slice_v1(&raw(&declaration()), legacy()).unwrap();
    let accepted = stream_validation(compiled.all_stream()).unwrap();
    let mut state = new_run(&accepted);
    let projection = projection_view(&accepted);
    let intro = &projection.records()[usize::from(run_state_view(&state).current_node_id() - 1)];
    match intro.payload() {
        RecordPayload::LessonNode {
            role,
            answer_mode,
            predicate_result_ref,
            cases,
            region_set_ref,
            ..
        } => {
            assert_eq!((*role, *answer_mode, *predicate_result_ref), (4, 3, 0));
            assert!(cases.is_empty());
            match projection.records()[usize::from(*region_set_ref - 1)].payload() {
                RecordPayload::RegionSet { regions, .. } => {
                    assert_eq!(regions.len(), 1);
                    assert_eq!(regions[0].region_id, 1);
                }
                _ => panic!("inspection must select only its dedicated surface"),
            }
        }
        _ => panic!("library entry must be a generic lesson node"),
    }
    state = step(&accepted, state, &[1, 0, 0, 1]).0;
    state = step(&accepted, state, &[3, 0, 0, 0]).0;
    let view = run_state_view(&state);
    assert_eq!(view.outcome(), 3);
    assert_eq!(view.next_node_ref(), 12);
    let feedback = &projection.records()[usize::from(view.feedback_ref() - 1)];
    let display = match feedback.payload() {
        RecordPayload::Feedback { display_ref, .. } => *display_ref,
        _ => panic!("selection must produce generic feedback"),
    };
    match projection.records()[usize::from(display - 1)].payload() {
        RecordPayload::Tuple { field_values, .. } => {
            assert_eq!(field_values.len(), 2);
            match &field_values[1] {
                gb_content::FieldValue::RecordRefs(references) => assert_eq!(references.len(), 74),
                _ => panic!("library tuple must reference payloads"),
            }
        }
        _ => panic!("library must be an artifact-carried tuple"),
    }
}

#[test]
fn rejects_noncanonical_shapes_bools_bad_actions_and_source_substitution() {
    let good = declaration();
    let mut mutants = Vec::new();
    let mut value = good.clone();
    value["extra"] = json!(0);
    mutants.push(value);
    let mut value = good.clone();
    value["lesson_records"][0]["payload"]["min_value"] = json!(false);
    mutants.push(value);
    let mut value = good.clone();
    value["lesson_records"][0]["payload"]["entries"] = json!([]);
    mutants.push(value);
    let mut value = good.clone();
    value["lesson_records"][10]["payload"]["actions"][0] = json!("0100000A");
    mutants.push(value);
    let mut value = good.clone();
    value["lesson_records"][1]["record_id"] = json!(3);
    mutants.push(value);
    let mut value = good.clone();
    value["legacy_declaration_sha256"] = json!("0".repeat(64));
    mutants.push(value);
    let mut value = good.clone();
    value["lesson_records"][12]["payload"]["global_event_budget"] = json!(65535);
    mutants.push(value);
    let mut value = good.clone();
    value["lesson_records"][2]["payload"]["regions"][1]["region_id"] = json!(3);
    mutants.push(value);
    let mut value = good.clone();
    value["lesson_records"][2]["payload"]["regions"][0]["unexpected"] = json!(0);
    mutants.push(value);
    let mut value = good.clone();
    value["lesson_records"][11]["payload"]["cases"][0]["unexpected"] = json!(0);
    mutants.push(value);
    let mut value = good.clone();
    value["lesson_records"][11]["payload"]["item_event_budget"] = json!(true);
    mutants.push(value);
    for value in mutants {
        assert!(compile_slice_v1(&raw(&value), legacy()).is_err());
    }
    let canonical = raw(&good);
    let mut trailing = canonical.clone();
    trailing.push(b' ');
    assert!(compile_slice_v1(&trailing, legacy()).is_err());
    assert!(compile_slice_v1(&vec![b' '; 1_048_577], legacy()).is_err());
    let mut changed = legacy();
    changed.game_set = b"substituted";
    assert!(compile_slice_v1(&canonical, changed).is_err());
}

fn wide_declaration(columns: usize) -> Value {
    let mut value = declaration();
    value["lesson_records"][1]["payload"]["rows"] = json!(1);
    value["lesson_records"][1]["payload"]["columns"] = json!(columns);
    value["lesson_records"][1]["payload"]["cells"] = json!(vec![0; columns]);
    let second = &mut value["lesson_records"][2]["payload"]["regions"][1];
    second["row_start"] = json!(0);
    second["row_end"] = json!(1);
    second["column_start"] = json!(columns - 1);
    second["column_end"] = json!(columns);
    value
}

#[test]
fn partitions_only_between_whole_frames_and_rejects_one_oversized_frame() {
    // The MATRIX frame has an 8-byte frame header and 6-byte matrix header.
    let compiled = compile_slice_v1(&raw(&wide_declaration(16_370)), legacy()).unwrap();
    let required: Vec<_> = compiled
        .assignments()
        .iter()
        .filter(|row| row.closure() == Closure::Required)
        .collect();
    assert_eq!(required.len(), 3);
    assert_eq!(required[0].record_ids(), &[1]);
    assert_eq!(required[1].record_ids(), &[2]);
    assert_eq!(required[2].record_ids(), &(3..13).collect::<Vec<_>>());
    assert_eq!(frames(compiled.required_stream())[&2].len(), 16_384);
    let rejected = compile_slice_v1(&raw(&wide_declaration(16_371)), legacy()).unwrap_err();
    assert_eq!(rejected.reason(), "section_payload");
}

#[test]
fn rejects_more_than_sixteen_required_sections() {
    let mut value = wide_declaration(16_370);
    let rows = value["lesson_records"].as_array_mut().unwrap();
    let mut root = rows.pop().unwrap();
    let node_payload = rows[11]["payload"].clone();
    let trace_payload = rows[10]["payload"].clone();
    rows[11]["payload"]["default_next_node_ref"] = json!(16);
    for ordinal in 0..14 {
        let matrix_id = rows.len() + 1;
        rows.push(json!({"record_id":matrix_id,"kind":4,
            "payload":{"atom_schema_ref":1,"rows":1,"columns":16370,"cells":vec![0;16370]}}));
        rows.push(json!({"record_id":matrix_id+1,"kind":11,
            "payload":{"feedback_code":3,"display_ref":matrix_id,"predicate_result_ref":8}}));
        rows.push(json!({"record_id":matrix_id+2,"kind":12,"payload":trace_payload.clone()}));
        let mut node = node_payload.clone();
        node["passive_trace_ref"] = json!(matrix_id + 2);
        node["default_feedback_ref"] = json!(matrix_id + 1);
        node["default_next_node_ref"] = json!(if ordinal == 13 { 12 } else { matrix_id + 7 });
        rows.push(json!({"record_id":matrix_id+3,"kind":13,"payload":node}));
    }
    root["record_id"] = json!(rows.len() + 1);
    rows.push(root);
    let rejected = compile_slice_v1(&raw(&value), legacy()).unwrap_err();
    assert_eq!(rejected.reason(), "section_count");
}
