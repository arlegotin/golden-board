use gb_bootstrap::resources_v2::{
    Kernel, ReferenceLedger, content_workspace, definition_workspace, program_workspace,
};
#[test]
fn content_alias_and_phase_arenas_have_exact_owned_sizes() {
    assert_eq!(content_workspace(100, 10, 20).unwrap(), 8960);
    assert_eq!(content_workspace(100, 10, 21).unwrap(), 8968);
    assert_eq!(content_workspace(0, 0, 0).unwrap(), 256);
    assert!(content_workspace(u64::MAX, 10, 0).is_err());
    assert!(content_workspace(10, 65536, 0).is_err());
}
#[test]
fn complete_recipe_header_counts_are_clamped_before_workspace_arithmetic() {
    assert_eq!(program_workspace(&[0; 63]).unwrap().parsing(), 63);
    let mut raw = [0; 64];
    raw[8..10].copy_from_slice(&1u16.to_be_bytes());
    raw[16..18].copy_from_slice(&1u16.to_be_bytes());
    raw[18..20].copy_from_slice(&1u16.to_be_bytes());
    raw[20..24].copy_from_slice(&1u32.to_be_bytes());
    raw[24..28].copy_from_slice(&2u32.to_be_bytes());
    raw[28..32].copy_from_slice(&3u32.to_be_bytes());
    let w = program_workspace(&raw).unwrap();
    assert_eq!(w.immutable(), 614);
    assert_eq!(w.parsing(), 726);
    assert_eq!(w.refinement(), 56);
    assert_eq!(
        definition_workspace(5, w).unwrap(),
        40 + (614 + 4 * content_workspace(577, 29, 29 * (577 / 14)).unwrap()).max(726)
    );
    raw[16..32].fill(255);
    let w = program_workspace(&raw).unwrap();
    assert!(w.parsing() > w.immutable());
}
#[test]
fn checked_events_keep_completed_counts_and_overlapping_peak() {
    let mut ledger = ReferenceLedger::default();
    ledger.retain("square", 100).unwrap();
    ledger.event(Kernel::Observation, 12, 20).unwrap();
    ledger.event(Kernel::Observation, 5, 10).unwrap();
    assert_eq!(ledger.peak_scratch_bytes(), 120);
    let row = ledger.rows()[0];
    assert_eq!(
        (
            row.calls(),
            row.reference_input_units(),
            row.peak_workspace_bytes()
        ),
        (2, 17, 20)
    );
    ledger.retain("units", 200).unwrap();
    ledger.vm_workspace(40).unwrap();
    assert_eq!(ledger.peak_scratch_bytes(), 340);
    ledger.release("square");
    ledger.release("units");
    ledger.event(Kernel::ResultRender, 8, 10).unwrap();
    assert_eq!(ledger.peak_scratch_bytes(), 340);
    let before = ledger.clone();
    assert!(ledger.event(Kernel::Observation, u64::MAX, 1).is_err());
    assert_eq!(ledger, before);
    ledger.retain("ceiling", u64::MAX).unwrap();
    let before = ledger.clone();
    assert!(ledger.event(Kernel::LaneAdapter, 1, 1).is_err());
    assert_eq!(ledger, before);
}

#[test]
fn sidecars_bind_complete_source_owners_and_aggregation_requires_exact_order() {
    use gb_bootstrap::damage::ResourceProjection;
    use gb_bootstrap::resources_v2::{build_resource_limits_v2, render_resource_sidecar};
    use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
    let mut ledger = ReferenceLedger::default();
    ledger.event(Kernel::Observation, 4, 0).unwrap();
    let first = render_resource_sidecar(
        "OBS_UNITS",
        &"1".repeat(64),
        &"2".repeat(64),
        ResourceProjection {
            section_attempts: 2,
            primitive_steps: 3,
            peak_scratch_bytes: 4,
        },
        &ledger,
    )
    .unwrap();
    ledger.event(Kernel::Observation, 8, 2).unwrap();
    let second = render_resource_sidecar(
        "OBS_UNITS",
        &"3".repeat(64),
        &"4".repeat(64),
        ResourceProjection {
            section_attempts: 1,
            primitive_steps: 5,
            peak_scratch_bytes: 2,
        },
        &ledger,
    )
    .unwrap();
    let pairs = [
        ("D0-000000", first.as_slice()),
        ("D0-000001", second.as_slice()),
    ];
    let raw =
        build_resource_limits_v2(&"a".repeat(64), &["D0-000000", "D0-000001"], pairs).unwrap();
    assert_eq!(
        raw,
        gb_bootstrap::resources_v2::build_resource_limits_v2_owned(
            &"a".repeat(64),
            &["D0-000000", "D0-000001"],
            pairs
                .into_iter()
                .map(|(id, raw)| (id.to_owned(), raw.to_vec()))
        )
        .unwrap()
    );
    let mut stream =
        gb_bootstrap::resources_v2::ResourceLimitsAccumulatorV2::new(&["D0-000000", "D0-000001"])
            .unwrap();
    stream.push("D0-000000", &first).unwrap();
    stream.push("D0-000001", &second).unwrap();
    assert_eq!(stream.finish(&"a".repeat(64)).unwrap(), raw);
    let mut partial =
        gb_bootstrap::resources_v2::ResourceLimitsAccumulatorV2::new(&["D0-000000", "D0-000001"])
            .unwrap();
    partial.push("D0-000000", &first).unwrap();
    assert!(partial.finish(&"a".repeat(64)).is_err());
    let V::Object(doc) = validate_canonical_manifest(&raw).unwrap() else {
        panic!()
    };
    assert_eq!(doc["case_count"], V::U64(2));
    let V::Object(max) = &doc["maximum_resource"] else {
        panic!()
    };
    assert_eq!(max["section_attempts"], V::U64(2));
    assert_eq!(max["primitive_steps"], V::U64(5));
    assert_eq!(max["peak_scratch_bytes"], V::U64(4));
    for rows in [
        vec![pairs[0]],
        vec![pairs[1], pairs[0]],
        vec![pairs[0], pairs[1], pairs[0]],
    ] {
        assert!(
            build_resource_limits_v2(&"a".repeat(64), &["D0-000000", "D0-000001"], rows).is_err()
        );
    }
    assert!(build_resource_limits_v2(&"a".repeat(64), &["D0-000000", "D0-000000"], pairs).is_err());
    assert!(
        build_resource_limits_v2(
            &"a".repeat(64),
            &["D0-000000"],
            [("D0-000000", b"{}".as_slice())]
        )
        .is_err()
    );
}

#[test]
fn observation_count_rejection_charges_one_logical_render_and_renderer_is_pure() {
    use gb_bootstrap::damage::ArtifactState;
    use gb_bootstrap::damage_v2::{
        decode_observation_v2, render_decoder_result_v2, render_resources_v2,
    };
    use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
    let wire = 2390u32.to_be_bytes();
    let result = decode_observation_v2("OBS_UNITS", &wire);
    assert_eq!(result.artifact_state(), ArtifactState::ResourceLimit);
    assert_eq!(result.resource().primitive_steps, 0);
    assert_eq!(result.resource().peak_scratch_bytes, 1048576 + 256);
    let first = render_decoder_result_v2("OBS_UNITS", &result).unwrap();
    let side = render_resources_v2("OBS_UNITS", &wire, &result).unwrap();
    assert_eq!(
        first,
        render_decoder_result_v2("OBS_UNITS", &result).unwrap()
    );
    assert_eq!(
        side,
        render_resources_v2("OBS_UNITS", &wire, &result).unwrap()
    );
    assert!(render_resources_v2("OBS_UNITS", b"changed", &result).is_err());
    let V::Object(doc) = validate_canonical_manifest(&side).unwrap() else {
        panic!()
    };
    let V::Array(rows) = &doc["adapter_rows"] else {
        panic!()
    };
    let V::Object(observation) = &rows[0] else {
        panic!()
    };
    assert_eq!(observation["calls"], V::U64(1));
    assert_eq!(observation["reference_input_units"], V::U64(4));
    let V::Object(render) = &rows[21] else {
        panic!()
    };
    assert_eq!(render["calls"], V::U64(1));
    assert_eq!(
        render["reference_input_units"],
        V::U64(first.0.len() as u64 + 12)
    );
}

#[test]
fn incomplete_discovered_copy_has_no_constructed_envelope_workspace() {
    use gb_bootstrap::damage::{ArtifactState, UnitEntry, serialize_obs_units};
    use gb_bootstrap::damage_v2::{decode_observation_v2, render_resources_v2};
    use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
    let envelope = gb_bootstrap::encode_section(&gb_bootstrap::SectionEnvelope {
        section_id: 4005,
        section_type: 6,
        section_version: 0,
        closure_class: 129,
        check_id: 1,
        dependencies: vec![],
        payload: vec![7; 200],
    })
    .unwrap();
    let blocks = gb_bootstrap::fragment_envelope(8, 4005, 0, 6, 0, &envelope).unwrap();
    assert_eq!(blocks.len(), 2);
    let raw = serialize_obs_units(&[UnitEntry {
        physical_unit_id: 100,
        bytes: gb_bootstrap::candidate::encode_eh_unit(&blocks[0]).to_vec(),
    }])
    .unwrap();
    let result = decode_observation_v2("OBS_UNITS", &raw);
    assert_eq!(result.artifact_state(), ArtifactState::Failure);
    assert_eq!(result.resource().section_attempts, 0);
    let V::Object(doc) =
        validate_canonical_manifest(&render_resources_v2("OBS_UNITS", &raw, &result).unwrap())
            .unwrap()
    else {
        panic!()
    };
    let V::Array(rows) = &doc["adapter_rows"] else {
        panic!()
    };
    let row = rows
        .iter()
        .find_map(|row| match row {
            V::Object(r) if r["kernel"] == V::String("section-assembly".into()) => Some(r),
            _ => None,
        })
        .unwrap();
    assert_eq!(row["calls"], V::U64(2));
    assert_eq!(row["reference_input_units"], V::U64(2 * 191));
    assert_eq!(row["peak_workspace_bytes"], V::U64(24));
}

#[test]
fn invalid_unit_widths_reject_before_normalized_pool_or_lane_work() {
    use gb_bootstrap::damage::{ArtifactState, ObsUnits};
    use gb_bootstrap::damage_v2::{decode_observation_v2, render_resources_v2};
    use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
    for length in [0u16, 256, u16::MAX] {
        let mut raw = 1u32.to_be_bytes().to_vec();
        raw.extend(1u32.to_be_bytes());
        raw.extend(length.to_be_bytes());
        raw.resize(10 + usize::from(length), 0);
        assert!(
            ObsUnits::parse(&raw).is_ok(),
            "historical parser remains unchanged"
        );
        let result = decode_observation_v2("OBS_UNITS", &raw);
        assert_eq!(result.artifact_state(), ArtifactState::Failure);
        assert_eq!(result.resource().primitive_steps, 0, "length {length}");
        assert_eq!(result.resource().section_attempts, 0);
        assert_eq!(result.resource().peak_scratch_bytes, 1048576 + 256);
        assert!(result.fragments().is_empty());
        let V::Object(doc) =
            validate_canonical_manifest(&render_resources_v2("OBS_UNITS", &raw, &result).unwrap())
                .unwrap()
        else {
            panic!()
        };
        let V::Array(rows) = &doc["adapter_rows"] else {
            panic!()
        };
        for value in rows {
            let V::Object(row) = value else { panic!() };
            let V::String(kernel) = &row["kernel"] else {
                panic!()
            };
            if kernel == "observation" {
                assert_eq!(row["calls"], V::U64(1));
                assert_eq!(row["reference_input_units"], V::U64(raw.len() as u64));
                assert_eq!(row["peak_workspace_bytes"], V::U64(0));
            } else if kernel != "result-render" {
                assert_eq!(row["calls"], V::U64(0), "{kernel}");
            }
        }
    }
}

#[test]
fn unit_adapter_counts_include_wrong_width_and_failed_bootstrap() {
    use gb_bootstrap::damage::{UnitEntry, serialize_obs_units};
    use gb_bootstrap::damage_v2::{decode_observation_v2, render_resources_v2};
    use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
    let raw = serialize_obs_units(&[UnitEntry {
        physical_unit_id: 1,
        bytes: vec![0; 216],
    }])
    .unwrap();
    let result = decode_observation_v2("OBS_UNITS", &raw);
    let V::Object(doc) =
        validate_canonical_manifest(&render_resources_v2("OBS_UNITS", &raw, &result).unwrap())
            .unwrap()
    else {
        panic!()
    };
    let V::Array(rows) = &doc["adapter_rows"] else {
        panic!()
    };
    for (kernel, calls, units, workspace) in [
        ("lane-adapter", 7, 7 * 216, 407),
        ("common-frame", 7, 7 * 191, 191),
        ("repetition-adapter", 2, 2 * 5 * 1728, 3672),
        ("result-selection", 1, 248, 248),
    ] {
        let row = rows
            .iter()
            .find_map(|v| {
                if let V::Object(r) = v {
                    if r["kernel"] == V::String(kernel.into()) {
                        Some(r)
                    } else {
                        None
                    }
                } else {
                    None
                }
            })
            .unwrap();
        assert_eq!(row["calls"], V::U64(calls), "{kernel}");
        assert_eq!(row["reference_input_units"], V::U64(units), "{kernel}");
        assert_eq!(row["peak_workspace_bytes"], V::U64(workspace), "{kernel}");
    }
}

#[test]
fn revision_process_bridge_is_repeatable_and_rejects_only_invalid_host_frames() {
    use std::io::{Read, Write};
    use std::process::{Command, Stdio};
    let executable = env!("CARGO_BIN_EXE_gb-revision-damage-decoder");
    let mut process = Command::new(executable)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let mut input = process.stdin.take().unwrap();
    let mut output = process.stdout.take().unwrap();
    let mut responses = Vec::new();
    for _ in 0..2 {
        input.write_all(&[3, 0, 0, 0, 0]).unwrap();
        input.flush().unwrap();
        let mut pair = Vec::new();
        for _ in 0..2 {
            let mut n = [0; 4];
            output.read_exact(&mut n).unwrap();
            let n = u32::from_be_bytes(n) as usize;
            assert!((1..=1048576).contains(&n));
            let mut raw = vec![0; n];
            output.read_exact(&mut raw).unwrap();
            gb_foundation::validate_canonical_manifest(&raw).unwrap();
            pair.push(raw);
        }
        responses.push(pair);
    }
    assert_eq!(responses[0], responses[1]);
    drop(input);
    assert!(process.wait().unwrap().success());
    for raw in [
        vec![0],
        vec![3, 0],
        vec![3, 0, 0, 0, 1],
        vec![3, 0, 64, 0, 3],
    ] {
        let mut child = Command::new(executable)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        child.stdin.take().unwrap().write_all(&raw).unwrap();
        let result = child.wait_with_output().unwrap();
        assert!(!result.status.success());
        assert!(result.stdout.is_empty());
    }
}

#[test]
fn foreign_inventory_parsing_is_reached_and_repeated_assemblies_do_not_repeat_crc() {
    use gb_bootstrap::damage::{
        ArtifactState, FragmentState, ResourceProjection, SectionResult, SectionState, UnitEntry,
        serialize_obs_units,
    };
    use gb_bootstrap::damage_v2::{
        FragmentDiagnosticV2, decode_observation_v2, render_resources_v2,
    };
    use gb_bootstrap::{Inventory, InventoryEntry, SectionEnvelope};
    use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
    use sha2::{Digest, Sha256};
    let mut entries = Vec::new();
    for id in [1u32, 2, 3].into_iter().chain(100..164) {
        entries.push(InventoryEntry {
            section_id: id,
            section_type: if id == 1 {
                1
            } else if id <= 3 {
                2
            } else {
                3
            },
            section_version: 0,
            closure_class: if id <= 3 { 128 } else { 129 },
            check_id: 1,
            copy_count: if id <= 3 { 2 } else { 1 },
            physical_replica_count: 1,
            dependencies: vec![],
            logical_payload_length: 1,
            game_ordinal: if id >= 100 {
                Some((id - 100) as u16)
            } else {
                None
            },
        });
    }
    let inventory_entries = entries.len() as u64;
    entries[0].logical_payload_length = (8 + 20 * entries.len()) as u32;
    let payload = gb_bootstrap::encode_inventory(&Inventory {
        inventory_version: 0,
        entries,
    })
    .unwrap();
    let env = gb_bootstrap::encode_section(&SectionEnvelope {
        section_id: 1,
        section_type: 1,
        section_version: 0,
        closure_class: 128,
        check_id: 1,
        dependencies: vec![],
        payload: payload.clone(),
    })
    .unwrap();
    let blocks = gb_bootstrap::fragment_envelope(3, 1, 0, 1, 0, &env).unwrap();
    let units = blocks
        .iter()
        .enumerate()
        .map(|(i, b)| UnitEntry {
            physical_unit_id: i as u32 + 1,
            bytes: gb_bootstrap::candidate::encode_eh_unit(b).to_vec(),
        })
        .collect::<Vec<_>>();
    let wire = serialize_obs_units(&units).unwrap();
    let result = decode_observation_v2("OBS_UNITS", &wire);
    assert_eq!(result.artifact_state(), ArtifactState::Failure);
    assert_eq!(result.profile_version(), None);
    assert!(!result.inventory_established());
    assert!(result.required_bytes().is_none());
    assert!(result.all_bytes().is_none());
    assert!(result.accepted_hypotheses().is_empty());
    assert_eq!(
        result.sections(),
        &[SectionResult {
            section_id: 1,
            state: SectionState::Verified,
            envelope: Some(env.clone()),
        }]
    );
    let fragments = blocks
        .iter()
        .enumerate()
        .map(|(i, block)| FragmentDiagnosticV2 {
            input_id: i as u32 + 1,
            profile_version: Some(3),
            section_id: 1,
            semantic_copy_id: 0,
            fragment_index: i as u16,
            replica_index: if i < 5 { i as u16 } else { u16::MAX },
            physical_replica_count: if i < 5 { 5 } else { u16::MAX },
            state: FragmentState::Verified,
            common_block_sha256: format!("{:x}", Sha256::digest(block)),
        })
        .collect::<Vec<_>>();
    assert_eq!(result.fragments(), fragments);
    let block_count = blocks.len() as u64;
    let envelope_bytes = env.len() as u64;
    let expected_units = 2 * block_count + 4 + 64;
    let result_bytes = 48 + envelope_bytes + block_count * (40 + 191);
    // Every input visits five EH and two RS registry procedures. The active8
    // and foreign7 bootstrap each attempt one REP group. At render time only
    // the deduplicated checked envelope and final diagnostic result remain.
    assert_eq!(
        result.resource(),
        ResourceProjection {
            section_attempts: 1,
            primitive_steps: block_count * (5 * 24 * 80435 + 2 * 1698049)
                + 2 * (1728 * 24 + 24 * 80435),
            peak_scratch_bytes: 1048576 + 256 + envelope_bytes + 8 + result_bytes,
        }
    );
    let V::Object(doc) =
        validate_canonical_manifest(&render_resources_v2("OBS_UNITS", &wire, &result).unwrap())
            .unwrap()
    else {
        panic!()
    };
    let V::Array(rows) = &doc["adapter_rows"] else {
        panic!()
    };
    for (kernel, calls, work, workspace) in [
        (
            "inventory",
            1,
            payload.len() as u64,
            16 * payload.len() as u64,
        ),
        (
            "group-layout",
            1,
            expected_units,
            128 * expected_units + 64 * inventory_entries,
        ),
        ("dependency-closure", 1, 0, 24 * inventory_entries),
        // The foreign path assembles inventory discovery and its admitted
        // catalog copy. Final registry-wide fallback assembles the same legacy
        // raw section1 once more; only hierarchical7/8 require REP bootstrap
        // representatives. All three reach the same globally deduplicated CRC.
        (
            "section-assembly",
            3,
            3 * 191 * block_count,
            envelope_bytes + 24 * block_count,
        ),
        ("section-check", 1, envelope_bytes, envelope_bytes),
        ("result-selection", 1, result_bytes, result_bytes),
        ("body-adapter", 0, 0, 0),
        ("content-validation", 0, 0, 0),
    ] {
        let row = rows
            .iter()
            .find_map(|v| {
                if let V::Object(r) = v {
                    if r["kernel"] == V::String(kernel.into()) {
                        Some(r)
                    } else {
                        None
                    }
                } else {
                    None
                }
            })
            .unwrap();
        assert_eq!(row["calls"], V::U64(calls), "{kernel}");
        assert_eq!(row["reference_input_units"], V::U64(work), "{kernel}");
        assert_eq!(row["peak_workspace_bytes"], V::U64(workspace), "{kernel}");
    }
}
