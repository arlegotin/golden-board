use std::fs;
use std::path::{Path, PathBuf};

use gb_content::{
    ContentProjectionView, RecordPayload, RunState, advance_committed, new_run, projection_view,
    run_state_view, step, stream_validation,
};
use gb_foundation::canonicalize_manifest;
use gb_foundation::constants::{
    ACTION_COMMIT, ACTION_RESET, ACTION_SELECT, LESSON_ALLOW_REPEATED_SELECTIONS, PHASE_ACTIVE,
    PHASE_COMMITTED, REGION_SELECTABLE, RESPONSE_SEQUENCE,
};
use gb_slice::{Closure, SliceInputs, compile_slice_v0};
use sha2::{Digest, Sha256};

struct OwnedInputs {
    declaration: Vec<u8>,
    content_fixture: Vec<u8>,
    chess_fixture: Vec<u8>,
    game_set: Vec<u8>,
    content_spec: Vec<u8>,
    constants: Vec<u8>,
    curriculum: Vec<u8>,
}

impl OwnedInputs {
    fn view(&self) -> SliceInputs<'_> {
        SliceInputs {
            declaration: &self.declaration,
            content_fixture: &self.content_fixture,
            chess_fixture: &self.chess_fixture,
            game_set: &self.game_set,
            content_spec: &self.content_spec,
            constants: &self.constants,
            curriculum: &self.curriculum,
        }
    }
}

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

fn read(relative: &str, cap: usize) -> Vec<u8> {
    let path = root().join(relative);
    let metadata = path.symlink_metadata().unwrap();
    assert!(metadata.file_type().is_file() && !metadata.file_type().is_symlink());
    assert!(metadata.len() <= cap as u64);
    let bytes = fs::read(path).unwrap();
    assert!(bytes.len() <= cap);
    bytes
}

fn inputs() -> OwnedInputs {
    OwnedInputs {
        declaration: read("studies/m2/slice-v0.json", 32_768),
        content_fixture: read("conformance/content-v0.json", 1_048_576),
        chess_fixture: read("conformance/chess-v0.json", 1_048_576),
        game_set: read("reports/game-set-v0.bin", 327_677),
        content_spec: read("spec/content-v0.md", 262_144),
        constants: read("spec/constants-v0.toml", 262_144),
        curriculum: read("spec/curriculum-v0.toml", 262_144),
    }
}

fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn bytes_hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

#[test]
fn exact_two_tier_compilation_and_projection() {
    let compiled = compile_slice_v0(inputs().view()).unwrap();
    assert_eq!(compiled.required_stream().len(), 575);
    assert_eq!(
        sha256(compiled.required_stream()),
        "99c783060adb543ef1621b4e17f57772bd88c9d37cb249981aed5f9a4962d7dc"
    );
    assert_eq!(compiled.all_stream().len(), 13_644);
    assert_eq!(
        sha256(compiled.all_stream()),
        "de7e22f0aa4316d9f32d9435287dd19bd6c04519aae1dc9bd816613f26929671"
    );
    assert_eq!(compiled.required_projection().records().len(), 29);
    assert_eq!(compiled.required_projection().root_record_id(), 29);
    assert_eq!(compiled.all_projection().records().len(), 182);
    assert_eq!(compiled.all_projection().root_record_id(), 182);
    assert!(
        compiled
            .all_projection()
            .records()
            .iter()
            .map(|record| record.record_id())
            .eq(1_u16..=182)
    );
}

#[test]
fn all_64_game_records_are_exact_atomic_payloads() {
    let compiled = compile_slice_v0(inputs().view()).unwrap();
    assert_eq!(compiled.game_payloads().len(), 64);
    assert_eq!(
        compiled.game_payloads().iter().map(Vec::len).sum::<usize>(),
        10_022
    );
    for (ordinal, game) in compiled.game_payloads().iter().enumerate() {
        assert!(ordinal == 0 || compiled.game_payloads()[ordinal - 1] < *game);
        let plies = usize::from(u16::from_be_bytes([game[0], game[1]]));
        assert_eq!(game.len(), 2 + plies * 2 + 1);
        assert!(game[game.len() - 1] <= 2);
        let binding_id = 30 + ordinal as u16 * 2;
        let binding = &compiled.all_projection().records()[usize::from(binding_id - 1)];
        assert_eq!(binding.record_id(), binding_id);
        assert_eq!(
            binding.payload(),
            &RecordPayload::SemanticBinding {
                binding_class: 1,
                namespace_id: 2,
                semantic_code: ordinal as u16 + 1,
                argument: 29,
                auxiliary: game.len() as u16,
            }
        );
        let opaque = &compiled.all_projection().records()[usize::from(binding_id)];
        assert_eq!(opaque.record_id(), binding_id + 1);
        assert_eq!(
            opaque.payload(),
            &RecordPayload::OpaqueData {
                data_binding_ref: binding_id,
                data: game.iter().copied().map(u32::from).collect(),
            }
        );
    }
}

#[test]
fn ten_chess_packets_are_binary_exact_and_bound() {
    let compiled = compile_slice_v0(inputs().view()).unwrap();
    assert_eq!(compiled.fixture_payloads().len(), 10);
    assert_eq!(
        compiled
            .fixture_payloads()
            .iter()
            .map(Vec::len)
            .sum::<usize>(),
        741
    );
    assert_eq!(
        compiled
            .fixture_payloads()
            .iter()
            .map(|payload| sha256(payload))
            .collect::<Vec<_>>(),
        [
            "38f1a45ac64d296ae1057dbaff3e71de5d25a52ccb5d147d16d5daa348bb8167",
            "bc3dbbca5121b4e6043b86eff535b1dd499413e3a290140bdbbdfdf95043a89d",
            "726f74f3cefe01590ba93fd3c0272e02c20c22ef65fc8f55e00c4ded85a4033c",
            "b7180039601455515e8251b3c06b7bcbded533ebfd2b9f6551cff165783fd76f",
            "11c74522c075473253134264d93bac170d74f7b266e725e3d6e26cb2fd2687b3",
            "b19f2b430789ef0735abe7244b3f50195339522e206d70bd16a8f512a3f79a3b",
            "608b5a5096e9ff0757afb9a28fd7c7cf7bad5b51e83156ea40030f772821be72",
            "4b6c26b3a77c8f04bdc85f08451cc4716eb060fb865f1e5fe8375492fc52aeb8",
            "25f57acfdbd8d0cc650c2d8479f1d6c8b7ae3b61144c378637140ad64d6bc5f9",
            "6d7429ded9625f2fb56230d2a5e8873e9e38e9e29390c5eb7409424ce11a0a55",
        ]
    );
    for (ordinal, payload) in compiled.fixture_payloads().iter().enumerate() {
        assert_eq!(payload[0], 0);
        assert_eq!(payload[1], ordinal as u8 + 1);
        assert!(!payload.windows(5).any(|window| window == b"chess"));
        let prior_len = usize::from(u16::from_be_bytes([payload[2], payload[3]]));
        assert_eq!(prior_len % 2, 0);
        let subject_offset = 4 + prior_len;
        let subject_len = usize::from(u16::from_be_bytes([
            payload[subject_offset],
            payload[subject_offset + 1],
        ]));
        assert_eq!(subject_len, if ordinal < 8 { 2 } else { 0 });
        let expected_offset = subject_offset + 2 + subject_len;
        let expected_len = usize::from(u16::from_be_bytes([
            payload[expected_offset],
            payload[expected_offset + 1],
        ]));
        assert_eq!(payload.len(), expected_offset + 2 + expected_len);
        assert_eq!(
            payload[expected_offset + 2],
            match ordinal {
                0 | 1 => 1,
                2 => 2,
                3..=6 => 3,
                7 => 4,
                8 | 9 => 5,
                _ => unreachable!(),
            }
        );
        let binding_id = 158 + ordinal as u16 * 2;
        let binding = &compiled.all_projection().records()[usize::from(binding_id - 1)];
        assert_eq!(
            binding.payload(),
            &RecordPayload::SemanticBinding {
                binding_class: 1,
                namespace_id: 3,
                semantic_code: ordinal as u16 + 1,
                argument: 29,
                auxiliary: payload.len() as u16,
            }
        );
        let opaque = &compiled.all_projection().records()[usize::from(binding_id)];
        assert_eq!(
            opaque.payload(),
            &RecordPayload::OpaqueData {
                data_binding_ref: binding_id,
                data: payload.iter().copied().map(u32::from).collect(),
            }
        );
    }
}

#[test]
fn assignments_roots_and_capacity_prototypes_are_exact() {
    let compiled = compile_slice_v0(inputs().view()).unwrap();
    assert_eq!(compiled.assignments().len(), 77);
    assert_eq!(compiled.assignments()[0].closure(), Closure::Required);
    assert_eq!(compiled.assignments()[0].section_id(), 16);
    assert_eq!(
        compiled.assignments()[0].record_ids(),
        (1_u16..=28).collect::<Vec<_>>()
    );
    let body = compiled
        .assignments()
        .iter()
        .flat_map(|assignment| assignment.record_ids().iter().copied())
        .collect::<Vec<_>>();
    assert!(body.into_iter().eq(1_u16..=181));
    assert!(
        compiled
            .assignments()
            .iter()
            .all(|assignment| assignment.semantic_copy_id() == 0)
    );
    assert_eq!(compiled.tier_roots().len(), 2);
    assert_eq!(
        (
            compiled.tier_roots()[0].section_id(),
            compiled.tier_roots()[0].record_id()
        ),
        (2, 29)
    );
    assert_eq!(
        (
            compiled.tier_roots()[1].section_id(),
            compiled.tier_roots()[1].record_id()
        ),
        (3, 182)
    );
    assert_eq!(compiled.tier_roots()[1].closure(), Closure::All);
    assert!(
        compiled
            .tier_roots()
            .iter()
            .all(|root| root.frame().len() == 12)
    );
    assert_eq!(
        compiled
            .capacity_prototypes()
            .iter()
            .map(|prototype| prototype.frame_length())
            .collect::<Vec<_>>(),
        [15, 14, 14, 20, 34, 19, 54, 18, 11, 14, 14, 28, 58, 12]
    );
    for (index, prototype) in compiled.capacity_prototypes().iter().enumerate() {
        assert_eq!(prototype.kind(), index as u16 + 1);
        assert_eq!(
            prototype.prototype_id(),
            format!("generic-base-kind-{:02}", index + 1)
        );
    }
}

#[test]
fn declaration_and_each_bound_input_fail_closed() {
    let mut source = inputs();
    source.declaration.push(b' ');
    assert_eq!(
        compile_slice_v0(source.view()).unwrap_err().reason(),
        "noncanonical"
    );

    let mutate = |field: usize| {
        let mut source = inputs();
        let bytes = match field {
            0 => &mut source.content_fixture,
            1 => &mut source.chess_fixture,
            2 => &mut source.game_set,
            3 => &mut source.content_spec,
            4 => &mut source.constants,
            5 => &mut source.curriculum,
            _ => unreachable!(),
        };
        let index = bytes.len() / 2;
        bytes[index] ^= 1;
        let rejected = compile_slice_v0(source.view()).unwrap_err();
        assert_eq!(rejected.reason(), "input_digest");
    };
    for field in 0..6 {
        mutate(field);
    }
}

#[test]
fn canonical_declaration_value_mutations_fail_closed() {
    let mut source = inputs();
    let mut declaration: serde_json::Value = serde_json::from_slice(&source.declaration).unwrap();
    declaration["schema"] = serde_json::json!("golden-board.m2-slice/v1");
    source.declaration =
        gb_foundation::canonicalize_manifest(&serde_json::to_vec(&declaration).unwrap()).unwrap();
    assert_eq!(
        compile_slice_v0(source.view()).unwrap_err().reason(),
        "declaration_mismatch"
    );

    let mut source = inputs();
    let mut declaration: serde_json::Value = serde_json::from_slice(&source.declaration).unwrap();
    declaration["unexpected"] = serde_json::json!(0);
    source.declaration =
        gb_foundation::canonicalize_manifest(&serde_json::to_vec(&declaration).unwrap()).unwrap();
    assert_eq!(
        compile_slice_v0(source.view()).unwrap_err().reason(),
        "declaration_mismatch"
    );
}

fn record_payload(view: &ContentProjectionView, record_id: u16) -> &RecordPayload {
    view.records()
        .iter()
        .find(|record| record.record_id() == record_id)
        .unwrap()
        .payload()
}

fn predicate_value(view: &ContentProjectionView, predicate_result_ref: u16) -> serde_json::Value {
    if predicate_result_ref == 0 {
        return serde_json::json!({
            "argument": 0,
            "auxiliary": 0,
            "binding_class": 0,
            "namespace_id": 0,
            "predicate_binding_ref": 0,
            "predicate_result_ref": 0,
            "result_atom_vector_ref": 0,
            "semantic_code": 0,
            "subject_data_binding_ref": 0,
            "subject_opaque_data_ref": 0,
        });
    }
    let RecordPayload::PredicateResult {
        predicate_binding_ref,
        subject_opaque_data_ref,
        result_atom_vector_ref,
    } = record_payload(view, predicate_result_ref)
    else {
        panic!("predicate reference did not resolve through public view")
    };
    let RecordPayload::SemanticBinding {
        binding_class,
        namespace_id,
        semantic_code,
        argument,
        auxiliary,
    } = record_payload(view, *predicate_binding_ref)
    else {
        panic!("predicate binding did not resolve through public view")
    };
    let RecordPayload::OpaqueData {
        data_binding_ref, ..
    } = record_payload(view, *subject_opaque_data_ref)
    else {
        panic!("predicate subject did not resolve through public view")
    };
    assert!(matches!(
        record_payload(view, *result_atom_vector_ref),
        RecordPayload::AtomVector { .. }
    ));
    serde_json::json!({
        "argument": argument,
        "auxiliary": auxiliary,
        "binding_class": binding_class,
        "namespace_id": namespace_id,
        "predicate_binding_ref": predicate_binding_ref,
        "predicate_result_ref": predicate_result_ref,
        "result_atom_vector_ref": result_atom_vector_ref,
        "semantic_code": semantic_code,
        "subject_data_binding_ref": data_binding_ref,
        "subject_opaque_data_ref": subject_opaque_data_ref,
    })
}

fn available_actions(
    view: &ContentProjectionView,
    state: &gb_content::RunStateView,
) -> Vec<String> {
    if state.phase() != PHASE_ACTIVE {
        return Vec::new();
    }
    let RecordPayload::LessonNode {
        response_shape,
        flags,
        region_set_ref,
        max_selections,
        ..
    } = record_payload(view, state.current_node_id())
    else {
        panic!("current node did not resolve through public view")
    };
    let RecordPayload::RegionSet { regions, .. } = record_payload(view, *region_set_ref) else {
        panic!("region set did not resolve through public view")
    };
    let can_select = state.selection_buffer().len() < usize::from(*max_selections);
    let repeated =
        *response_shape == RESPONSE_SEQUENCE && *flags & LESSON_ALLOW_REPEATED_SELECTIONS != 0;
    let mut output = Vec::new();
    if can_select {
        for region in regions {
            if region.flags & REGION_SELECTABLE == 0
                || state.selection_buffer().contains(&region.region_id) && !repeated
            {
                continue;
            }
            output.push(format!("{ACTION_SELECT:02x}00{:04x}", region.region_id));
        }
    }
    output.push(format!("{ACTION_RESET:02x}000000"));
    output.push(format!("{ACTION_COMMIT:02x}000000"));
    output
}

fn checkpoint(view: &ContentProjectionView, state: &RunState) -> serde_json::Value {
    let public = run_state_view(state);
    let RecordPayload::LessonNode {
        predicate_result_ref,
        ..
    } = record_payload(view, public.current_node_id())
    else {
        panic!("current node did not resolve through public view")
    };
    serde_json::json!({
        "available_actions_hex": available_actions(view, &public),
        "can_advance": public.phase() == PHASE_COMMITTED && public.next_node_ref() != 0,
        "committed_response_hex": bytes_hex(public.committed_response()),
        "current_node_id": public.current_node_id(),
        "evaluator_predicate": predicate_value(view, *predicate_result_ref),
        "feedback_ref": public.feedback_ref(),
        "global_remaining": public.global_remaining(),
        "local_remaining": public.local_remaining(),
        "next_node_ref": public.next_node_ref(),
        "outcome": public.outcome(),
        "phase": public.phase(),
        "selection_buffer": public.selection_buffer(),
    })
}

fn commitment(view: &ContentProjectionView, state: &RunState) -> serde_json::Value {
    let public = run_state_view(state);
    assert_eq!(public.phase(), PHASE_COMMITTED);
    let RecordPayload::LessonNode {
        predicate_result_ref,
        ..
    } = record_payload(view, public.current_node_id())
    else {
        panic!("current node did not resolve through public view")
    };
    let RecordPayload::Feedback {
        predicate_result_ref: feedback_predicate_ref,
        ..
    } = record_payload(view, public.feedback_ref())
    else {
        panic!("feedback did not resolve through public view")
    };
    serde_json::json!({
        "committed_response_hex": bytes_hex(public.committed_response()),
        "feedback_predicate": predicate_value(view, *feedback_predicate_ref),
        "feedback_ref": public.feedback_ref(),
        "next_node_ref": public.next_node_ref(),
        "node_id": public.current_node_id(),
        "node_predicate": predicate_value(view, *predicate_result_ref),
        "outcome": public.outcome(),
    })
}

#[test]
fn public_views_reconstruct_exact_language_neutral_runner_evidence() {
    let compiled = compile_slice_v0(inputs().view()).unwrap();
    let projection = stream_validation(compiled.all_stream()).unwrap();
    let public_projection = projection_view(&projection);
    let action_groups: [&[[u8; 4]]; 4] = [
        &[[1, 0, 0, 2], [3, 0, 0, 0]],
        &[[1, 0, 0, 1], [3, 0, 0, 0]],
        &[[1, 0, 0, 3], [1, 0, 0, 1], [3, 0, 0, 0]],
        &[[1, 0, 0, 3], [1, 0, 0, 1], [3, 0, 0, 0]],
    ];
    let mut state = new_run(&projection);
    let mut checkpoints = vec![checkpoint(&public_projection, &state)];
    let mut commitments = Vec::new();
    for (group_index, actions) in action_groups.iter().enumerate() {
        if group_index != 0 {
            state = advance_committed(&projection, &state).unwrap();
            checkpoints.push(checkpoint(&public_projection, &state));
        }
        for action in *actions {
            let available = available_actions(&public_projection, &run_state_view(&state));
            assert!(available.contains(&bytes_hex(action)));
            let (next, _) = step(&projection, state, action);
            state = next;
            checkpoints.push(checkpoint(&public_projection, &state));
        }
        commitments.push(commitment(&public_projection, &state));
    }
    let public = run_state_view(&state);
    let events = public
        .events()
        .iter()
        .map(|event| {
            serde_json::json!({
                "action_hex": bytes_hex(event.action()),
                "node_id": event.node_id(),
                "result": event.result(),
            })
        })
        .collect::<Vec<_>>();
    let evidence = serde_json::json!({
        "checkpoints": checkpoints,
        "commitments": commitments,
        "content_stream_sha256": sha256(compiled.all_stream()),
        "events": events,
        "schema": "golden-board.runner-semantic-path/v0",
    });
    let canonical = canonicalize_manifest(&serde_json::to_vec(&evidence).unwrap()).unwrap();
    assert_eq!(canonical.len(), 9_883);
    assert_eq!(
        sha256(&canonical),
        "966e510af60a9a95afc60badee2d985da95add187f7d132bc2009369db33cbd3"
    );
    assert_eq!(public.committed_response(), &[3, 0, 2, 0, 3, 0, 1]);
    assert_eq!(public.events().len(), 10);
}
