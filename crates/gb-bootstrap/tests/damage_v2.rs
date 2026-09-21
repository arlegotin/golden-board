use gb_bootstrap::damage::{ArtifactState, UnitEntry, serialize_obs_units};
use gb_bootstrap::damage_v2::{decode_observation_v2, render_decoder_result_v2};
#[test]
fn malformed_observations_always_project_v2_failure_without_inventing_streams() {
    for channel in ["OBS_BITS", "OBS_MATRIX", "OBS_UNITS"] {
        let result = decode_observation_v2(channel, &[]);
        assert_eq!(result.artifact_state(), ArtifactState::Failure);
        assert!(result.required_bytes().is_none());
        let (raw, _) = render_decoder_result_v2(channel, &result).unwrap();
        assert!(
            std::str::from_utf8(&raw)
                .unwrap()
                .contains("golden-board.m2-damage-decoder-result/v2")
        );
    }
}
#[test]
fn unit_count_is_global_but_sparse_nonzero_ids_are_diagnostic() {
    let sparse = serialize_obs_units(&[UnitEntry {
        physical_unit_id: u32::MAX,
        bytes: vec![0; 216],
    }])
    .unwrap();
    let result = decode_observation_v2("OBS_UNITS", &sparse);
    assert_eq!(result.artifact_state(), ArtifactState::Failure);
    assert!(
        result
            .fragments()
            .iter()
            .any(|row| row.input_id == u32::MAX)
    );
    let mut raw = 2390u32.to_be_bytes().to_vec();
    for id in 1..=2390u32 {
        raw.extend(id.to_be_bytes());
        raw.extend(0u16.to_be_bytes());
    }
    assert_eq!(
        decode_observation_v2("OBS_UNITS", &raw).artifact_state(),
        ArtifactState::ResourceLimit
    );
}

#[test]
fn both_hierarchical_registry_bootstraps_are_attempted_without_profile_short_circuit() {
    let observation = |id| {
        serialize_obs_units(&[UnitEntry {
            physical_unit_id: id,
            bytes: vec![0; 216],
        }])
        .unwrap()
    };
    let ordinary = decode_observation_v2("OBS_UNITS", &observation(100));
    let bootstrap = decode_observation_v2("OBS_UNITS", &observation(1));
    let repetition_charge = 1728 * 24 + 24 * 80435;
    assert_eq!(
        bootstrap.resource().primitive_steps - ordinary.resource().primitive_steps,
        2 * repetition_charge
    );
    assert!(!bootstrap.inventory_established());
}

fn fixture() -> &'static (
    gb_slice::SliceCompilation,
    gb_bootstrap::carrier_v2::Carrier,
    Vec<UnitEntry>,
    std::collections::BTreeMap<u32, Vec<u32>>,
) {
    static VALUE: std::sync::OnceLock<(
        gb_slice::SliceCompilation,
        gb_bootstrap::carrier_v2::Carrier,
        Vec<UnitEntry>,
        std::collections::BTreeMap<u32, Vec<u32>>,
    )> = std::sync::OnceLock::new();
    VALUE.get_or_init(|| {
        let slice = gb_slice::compile_slice_v1(
            include_bytes!("../../../studies/m2/slice-v1.json"),
            gb_slice::SliceInputs {
                declaration: include_bytes!("../../../studies/m2/slice-v0.json"),
                content_fixture: include_bytes!("../../../conformance/content-v0.json"),
                chess_fixture: include_bytes!("../../../conformance/chess-v0.json"),
                game_set: include_bytes!("../../../reports/game-set-v0.bin"),
                content_spec: include_bytes!("../../../spec/content-v0.md"),
                constants: include_bytes!("../../../spec/constants-v0.toml"),
                curriculum: include_bytes!("../../../spec/curriculum-v0.toml"),
            },
        )
        .unwrap();
        let carrier = gb_bootstrap::carrier_v2::build_carrier(&slice).unwrap();
        let map = gb_bootstrap::mapping_v2::derive(carrier.side(), carrier.shell_width()).unwrap();
        let mut units = Vec::new();
        let mut ids = std::collections::BTreeMap::<u32, Vec<u32>>::new();
        for unit in 1..=map.unit_slot_count() {
            let mut bytes = vec![0u8; 216];
            for bit in 0..1728u16 {
                let physical = map.forward(unit, bit).unwrap() as usize;
                let inner = usize::from(map.interior_side());
                let width = usize::from(map.shell_width());
                let absolute =
                    (physical / inner + width) * usize::from(map.side()) + physical % inner + width;
                let value = (carrier.packed_bytes()[4 + absolute / 8] >> (7 - absolute % 8)) & 1;
                bytes[usize::from(bit) / 8] |= value << (7 - bit % 8);
            }
            let common = gb_bootstrap::candidate::decode_eh_unit(
                &gb_bootstrap::candidate::EhObservation {
                    encoded: bytes.as_slice().try_into().unwrap(),
                    erasures: vec![],
                },
                8,
            )
            .unwrap()
            .common;
            let block = gb_bootstrap::decode_common_block(&common, 8).unwrap();
            ids.entry(block.section_id).or_default().push(unit as u32);
            units.push(UnitEntry {
                physical_unit_id: unit as u32,
                bytes,
            });
        }
        (slice, carrier, units, ids)
    })
}
#[test]
fn foreign_inventory_splices_match_full_source_oracle_resources() {
    use gb_bootstrap::damage_corpus_v2::DamageCorpusV2;
    use gb_bootstrap::damage_oracle_v2::FullOracleV2;
    use gb_bootstrap::damage_v2::render_resources_v2;
    let export = std::env::var_os("GB_FOREIGN_INVENTORY_TEST_EXPORT").map(std::path::PathBuf::from);
    if let Some(path) = &export {
        assert!(path.is_absolute());
        let mut directory = std::fs::DirBuilder::new();
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            directory.mode(0o700);
        }
        directory.create(path).unwrap();
    }
    let (slice, carrier, _, _) = fixture();
    let corpus = DamageCorpusV2::new(
        slice,
        carrier,
        include_bytes!("../../../spec/route-data-v0.json"),
    )
    .unwrap();
    let oracle = FullOracleV2::new(&corpus).unwrap();
    for ordinal in [11, 12, 13, 14, 15, 414] {
        let case = corpus.case("D7", ordinal).unwrap();
        let expected = oracle.project("D7", ordinal, case.bytes()).unwrap();
        let result = decode_observation_v2(case.channel(), case.bytes());
        let (raw, _) = render_decoder_result_v2(case.channel(), &result).unwrap();
        let resources = render_resources_v2(case.channel(), case.bytes(), &result).unwrap();
        assert_eq!(expected.semantic().wrong_accepts(), 0);
        assert!(
            raw == expected.result_bytes(),
            "D7/{ordinal} result mismatch"
        );
        assert!(
            resources == expected.resource_bytes(),
            "D7/{ordinal} resource mismatch"
        );
        assert!(!result.inventory_established());
        assert!(result.required_bytes().is_none());
        assert!(result.all_bytes().is_none());
        if let Some(path) = &export {
            use std::io::Write;
            for (suffix, bytes) in [("result", &raw), ("resources", &resources)] {
                let mut options = std::fs::OpenOptions::new();
                options.write(true).create_new(true);
                #[cfg(unix)]
                {
                    use std::os::unix::fs::OpenOptionsExt;
                    options.mode(0o644);
                }
                options
                    .open(path.join(format!("D7-{ordinal:06}.{suffix}.json")))
                    .unwrap()
                    .write_all(bytes)
                    .unwrap();
            }
        }
    }
}
#[test]
fn clean_units_and_missing_inventory_required_all_only_or_probe_keep_availability_exact() {
    let (slice, _, units, ids) = fixture();
    for (missing, state, required, all) in [
        (None, ArtifactState::Exact, true, true),
        (Some(1), ArtifactState::Failure, false, false),
        (Some(16), ArtifactState::Failure, false, false),
        (Some(100), ArtifactState::Degraded, true, false),
        (Some(211), ArtifactState::Degraded, true, true),
    ] {
        let entries = units
            .iter()
            .filter(|unit| {
                missing.is_none_or(|section| !ids[&section].contains(&unit.physical_unit_id))
            })
            .cloned()
            .collect::<Vec<_>>();
        let raw = serialize_obs_units(&entries).unwrap();
        let result = decode_observation_v2("OBS_UNITS", &raw);
        assert_eq!(result.artifact_state(), state, "missing={missing:?}");
        assert_eq!(result.required_bytes().is_some(), required);
        assert_eq!(result.all_bytes().is_some(), all);
        if required {
            assert_eq!(result.required_bytes(), Some(slice.required_stream()));
        }
        if all {
            assert_eq!(result.all_bytes(), Some(slice.all_stream()));
        }
        assert!(result.resource().primitive_steps > 0);
        render_decoder_result_v2("OBS_UNITS", &result).unwrap();
    }
}
#[test]
fn clean_bits_and_matrix_recover_from_their_actual_observed_routes() {
    let (slice, carrier, _, _) = fixture();
    let cells = carrier.packed_bytes()[4..]
        .iter()
        .flat_map(|byte| (0..8).rev().map(move |bit| (byte >> bit) & 1))
        .collect::<Vec<_>>();
    let matrix =
        gb_bootstrap::damage::serialize_obs_matrix(usize::from(carrier.side()), &cells).unwrap();
    for (channel, raw) in [
        ("OBS_BITS", carrier.packed_bytes()),
        ("OBS_MATRIX", matrix.as_slice()),
    ] {
        let result = decode_observation_v2(channel, raw);
        assert_eq!(
            result.artifact_state(),
            ArtifactState::Exact,
            "channel={channel}"
        );
        assert_eq!(result.required_bytes(), Some(slice.required_stream()));
        assert_eq!(result.all_bytes(), Some(slice.all_stream()));
        assert_eq!(result.accepted_hypotheses().len(), 4);
        assert_eq!(result.context_witnesses().len(), 4);
        for witness in result.context_witnesses() {
            assert_eq!(
                witness.proof().required(),
                gb_bootstrap::route_semantics_v2::ContextState::Consistent
            );
            assert_eq!(
                witness.proof().all(),
                gb_bootstrap::route_semantics_v2::ContextState::Consistent
            );
            assert_eq!(witness.package_sha256().len(), 64);
            assert_eq!(witness.definitions_sha256().len(), 64);
        }
        assert_eq!(result.resource().section_attempts, 136);
        render_decoder_result_v2(channel, &result).unwrap();
    }
}

#[test]
fn contradictory_recovered_context_remains_separate_from_content_availability() {
    let (slice, carrier, _, _) = fixture();
    let prefixes = gb_bootstrap::route_v2::build_route_prefixes(slice).unwrap();
    let prefix = &prefixes[0];
    let mut at = 64;
    loop {
        if prefix[at + 1] == 1 && prefix[at + 8..at + 10] == 12u16.to_be_bytes() {
            break;
        }
        at += 8 + u32::from_be_bytes(prefix[at + 4..at + 8].try_into().unwrap()) as usize;
    }
    let byte = at + 8 + 14 + 3;
    let (row, col) = gb_bootstrap::sector_cell_at(
        usize::from(carrier.side()),
        usize::from(carrier.shell_width()),
        0,
        byte * 8 + 7,
    )
    .unwrap();
    let absolute = row * usize::from(carrier.side()) + col;
    let mut observed = carrier.packed_bytes().to_vec();
    observed[4 + absolute / 8] ^= 1 << (7 - absolute % 8);
    let result = decode_observation_v2("OBS_BITS", &observed);
    assert_eq!(result.artifact_state(), ArtifactState::Exact);
    assert_eq!(result.required_bytes(), Some(slice.required_stream()));
    assert_eq!(result.all_bytes(), Some(slice.all_stream()));
    assert_eq!(result.context_witnesses().len(), 4);
    assert_eq!(
        result
            .context_witnesses()
            .iter()
            .filter(|w| w.proof().required()
                == gb_bootstrap::route_semantics_v2::ContextState::Contradiction)
            .count(),
        1
    );
    assert!(
        result
            .context_witnesses()
            .iter()
            .all(|w| w.proof().all() == gb_bootstrap::route_semantics_v2::ContextState::Consistent)
    );
}
#[test]
fn complete_observed_foreign_route_is_diagnostic_and_never_establishes_profile8() {
    let (slice, carrier, _, _) = fixture();
    let package = gb_bootstrap::candidate_recipe::build_eh_recipe_package(3).unwrap();
    let donor = gb_bootstrap::carrier::build_route_images(
        include_bytes!("../../../spec/route-data-v0.json"),
        3,
        &package,
        carrier.side(),
        128,
    )
    .unwrap();
    let sector = &donor.sectors[0];
    assert_eq!(sector.route_prefix_cells, 27714 * 8);
    let mut raw = carrier.packed_bytes().to_vec();
    for bit in 0..sector.route_prefix_cells as usize {
        let (r, c) =
            gb_bootstrap::sector_cell_at(usize::from(carrier.side()), 128, 0, bit).unwrap();
        let absolute = r * usize::from(carrier.side()) + c;
        let mask = 1u8 << (7 - absolute % 8);
        raw[4 + absolute / 8] =
            (raw[4 + absolute / 8] & !mask) | (sector.bits[bit] << (7 - absolute % 8));
    }
    let result = decode_observation_v2("OBS_BITS", &raw);
    assert!(
        result
            .accepted_hypotheses()
            .iter()
            .any(|h| h.profile_version == 3)
    );
    assert!(result.profile_version().is_none_or(|v| v == 8));
    if let Some(required) = result.required_bytes() {
        assert_eq!(required, slice.required_stream());
    }
    if let Some(all) = result.all_bytes() {
        assert_eq!(all, slice.all_stream());
    }
}
#[test]
fn valid_foreign7_inventory_reaches_all_present_groups_without_establishing_profile8() {
    use gb_bootstrap::{Inventory, InventoryEntry, SectionEnvelope};
    let bodies: Vec<u32> = std::iter::once(16).chain(100..=163).collect();
    let mut entries = vec![];
    for id in [1, 2, 3]
        .into_iter()
        .chain(bodies.iter().copied())
        .chain([211])
    {
        let required = [1, 2, 3, 16].contains(&id);
        entries.push(InventoryEntry {
            section_id: id,
            section_type: match id {
                1 => 1,
                2 | 3 => 2,
                211 => 4,
                _ => 3,
            },
            section_version: if id == 1 { 1 } else { 0 },
            closure_class: if required { 128 } else { 129 },
            check_id: 1,
            copy_count: 1,
            physical_replica_count: if required {
                5
            } else if id == 211 {
                2
            } else {
                1
            },
            dependencies: match id {
                2 => vec![16],
                3 => bodies.clone(),
                _ => vec![],
            },
            logical_payload_length: 1,
            game_ordinal: if (100..=163).contains(&id) {
                Some((id - 100) as u16)
            } else {
                None
            },
        });
    }
    entries[0].logical_payload_length = (8 + entries
        .iter()
        .map(|e| 20 + e.dependencies.len() * 4)
        .sum::<usize>()) as u32;
    let inventory = Inventory {
        inventory_version: 1,
        entries,
    };
    let payload = gb_bootstrap::encode_inventory(&inventory).unwrap();
    let envelope = gb_bootstrap::encode_section(&SectionEnvelope {
        section_id: 1,
        section_type: 1,
        section_version: 1,
        closure_class: 128,
        check_id: 1,
        dependencies: vec![],
        payload,
    })
    .unwrap();
    let blocks = gb_bootstrap::fragment_envelope(7, 1, 0, 1, 1, &envelope).unwrap();
    let mut units = vec![];
    for (fragment, block) in blocks.iter().enumerate() {
        for lane in 0..5 {
            units.push(UnitEntry {
                physical_unit_id: (fragment * 5 + lane + 1) as u32,
                bytes: gb_bootstrap::candidate::encode_eh_unit(block).to_vec(),
            });
        }
    }
    let probe = gb_bootstrap::encode_section(&SectionEnvelope {
        section_id: 211,
        section_type: 4,
        section_version: 0,
        closure_class: 129,
        check_id: 1,
        dependencies: vec![],
        payload: vec![1],
    })
    .unwrap();
    let block = gb_bootstrap::fragment_envelope(7, 211, 0, 4, 0, &probe).unwrap()[0];
    let first = 1 + inventory
        .entries
        .iter()
        .filter(|e| e.section_id < 211)
        .map(|e| {
            (18 + 4 * e.dependencies.len() + e.logical_payload_length as usize + 4).div_ceil(157)
                * usize::from(e.physical_replica_count)
        })
        .sum::<usize>();
    for lane in 0..2 {
        units.push(UnitEntry {
            physical_unit_id: (first + lane) as u32,
            bytes: gb_bootstrap::candidate::encode_eh_unit(&block).to_vec(),
        });
    }
    let result = decode_observation_v2("OBS_UNITS", &serialize_obs_units(&units).unwrap());
    assert!(!result.inventory_established());
    assert_eq!(result.artifact_state(), ArtifactState::Failure);
    assert!(result.required_bytes().is_none());
    assert_eq!(
        result.resource().primitive_steps,
        units.len() as u64 * (5 * 24 * 80435 + 2 * 1698049)
            + (blocks.len() as u64 + 2) * (1728 * 24 + 24 * 80435)
    );
    assert_eq!(result.resource().section_attempts, 2);
}

#[test]
fn malformed_compact_tag_reaches_parser_and_foreign7_does_not_follow_inventory2() {
    use gb_bootstrap::damage_v2::render_resources_v2;
    use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
    let row = |raw: &[u8], kernel: &str| -> (u64, u64) {
        let V::Object(doc) = validate_canonical_manifest(raw).unwrap() else {
            panic!()
        };
        let V::Array(rows) = &doc["adapter_rows"] else {
            panic!()
        };
        let r = rows
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
        let V::U64(calls) = r["calls"] else { panic!() };
        let V::U64(units) = r["reference_input_units"] else {
            panic!()
        };
        (calls, units)
    };
    let (slice, carrier, units, ids) = fixture();
    let prefixes = gb_bootstrap::route_v2::build_route_prefixes(slice).unwrap();
    let mut wire = carrier.packed_bytes().to_vec();
    let mut total = 0;
    for (sector, prefix) in prefixes.iter().enumerate() {
        let mut at = 64;
        while prefix[at + 1] != 5 {
            at += 8 + u32::from_be_bytes(prefix[at + 4..at + 8].try_into().unwrap()) as usize;
        }
        total += u32::from_be_bytes(prefix[at + 4..at + 8].try_into().unwrap()) as u64;
        let changed_byte = at + 8 + 9;
        for bit in 0..8 {
            let (r, c) = gb_bootstrap::sector_cell_at(
                carrier.side() as usize,
                carrier.shell_width() as usize,
                sector as u8,
                changed_byte * 8 + bit,
            )
            .unwrap();
            let flat = r * carrier.side() as usize + c;
            let mask = 1 << (7 - flat % 8);
            wire[4 + flat / 8] =
                (wire[4 + flat / 8] & !mask) | (((2 >> (7 - bit)) & 1) << (7 - flat % 8));
        }
    }
    let result = decode_observation_v2("OBS_BITS", &wire);
    assert_eq!(result.artifact_state(), ArtifactState::Failure);
    assert_eq!(result.resource().primitive_steps, 0);
    assert_eq!(
        row(
            &render_resources_v2("OBS_BITS", &wire, &result).unwrap(),
            "recipe-parse"
        ),
        (4, total)
    );
    let changed = units
        .iter()
        .filter(|u| ids[&1].contains(&u.physical_unit_id))
        .map(|u| {
            let d = gb_bootstrap::candidate::decode_eh_unit(
                &gb_bootstrap::candidate::EhObservation {
                    encoded: u.bytes.as_slice().try_into().unwrap(),
                    erasures: vec![],
                },
                8,
            )
            .unwrap();
            let mut common = gb_bootstrap::decode_common_block(&d.common, 8).unwrap();
            common.profile_version = 7;
            let block = gb_bootstrap::encode_common_block(&common).unwrap();
            UnitEntry {
                physical_unit_id: u.physical_unit_id,
                bytes: gb_bootstrap::candidate::encode_eh_unit(&block).to_vec(),
            }
        })
        .collect::<Vec<_>>();
    let wire = serialize_obs_units(&changed).unwrap();
    let result = decode_observation_v2("OBS_UNITS", &wire);
    assert!(!result.inventory_established());
    let sidecar = render_resources_v2("OBS_UNITS", &wire, &result).unwrap();
    assert_eq!(row(&sidecar, "repetition-adapter").0, 2);
    assert_eq!(row(&sidecar, "inventory").0, 0);
    // Foreign section1 lanes retain per-input diagnostics, but cannot replace
    // the active route-fixed bootstrap representatives during fallback.
    assert_eq!(row(&sidecar, "section-assembly").0, 0);
    assert!(result.sections().iter().all(|s| s.envelope.is_none()));
}

#[test]
fn checked_root_controls_reach_full_content_validation_and_undercoverage_keeps_diagnostics() {
    use gb_bootstrap::damage_corpus_v2::DamageCorpusV2;
    use gb_bootstrap::damage_v2::render_resources_v2;
    use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
    let (slice, carrier, _, _) = fixture();
    let corpus = DamageCorpusV2::new(
        slice,
        carrier,
        include_bytes!("../../../spec/route-data-v0.json"),
    )
    .unwrap();
    for (ordinal, bodies, validations, state) in [
        (14, 3, 1, ArtifactState::Failure),
        (17, 78, 2, ArtifactState::Degraded),
    ] {
        let case = corpus.case("B0", ordinal).unwrap();
        let result = decode_observation_v2("OBS_UNITS", case.bytes());
        assert!(result.inventory_established());
        assert_eq!(result.artifact_state(), state);
        assert_eq!(result.required_bytes().is_some(), ordinal == 17);
        assert!(result.all_bytes().is_none());
        let V::Object(doc) = validate_canonical_manifest(
            &render_resources_v2("OBS_UNITS", case.bytes(), &result).unwrap(),
        )
        .unwrap() else {
            panic!()
        };
        let V::Array(rows) = &doc["adapter_rows"] else {
            panic!()
        };
        for (kernel, calls) in [
            ("body-adapter", bodies),
            ("content-validation", validations),
        ] {
            let row = rows
                .iter()
                .find_map(|row| match row {
                    V::Object(row) if row["kernel"] == V::String(kernel.into()) => Some(row),
                    _ => None,
                })
                .unwrap();
            assert_eq!(row["calls"], V::U64(calls), "B0-{ordinal}: {kernel}");
        }
    }
    let case = corpus.case("B0", 20).unwrap();
    let result = decode_observation_v2("OBS_BITS", case.bytes());
    assert_eq!(result.artifact_state(), ArtifactState::Failure);
    assert!(!result.inventory_established());
    assert!(result.required_bytes().is_none());
    assert!(result.all_bytes().is_none());
    assert_eq!(result.accepted_hypotheses().len(), 4);
    assert!(!result.sections().is_empty());
    assert!(!result.fragments().is_empty());
    assert_eq!(
        result.resource().section_attempts as usize,
        result.sections().len()
    );
}
