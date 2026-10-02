use std::collections::{BTreeMap, BTreeSet};

use gb_bootstrap::*;
use gb_foundation::{ManifestValue, validate_canonical_manifest};

fn decode_hex(text: &str) -> Vec<u8> {
    assert_eq!(text.len() % 2, 0);
    text.as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let digit = |byte: u8| match byte {
                b'0'..=b'9' => byte - b'0',
                b'a'..=b'f' => byte - b'a' + 10,
                _ => panic!("non-lowercase-hex fixture"),
            };
            digit(pair[0]) << 4 | digit(pair[1])
        })
        .collect()
}

fn error_code<T: std::fmt::Debug>(result: Result<T>) -> RejectCode {
    result.unwrap_err().code
}

fn manifest_object(value: &ManifestValue) -> &BTreeMap<String, ManifestValue> {
    let ManifestValue::Object(value) = value else {
        panic!("fixture object")
    };
    value
}

fn manifest_array(value: &ManifestValue) -> &[ManifestValue] {
    let ManifestValue::Array(value) = value else {
        panic!("fixture array")
    };
    value
}

fn manifest_text(value: &ManifestValue) -> &str {
    let ManifestValue::String(value) = value else {
        panic!("fixture string")
    };
    value
}

fn manifest_u64(value: &ManifestValue) -> u64 {
    let ManifestValue::U64(value) = value else {
        panic!("fixture unsigned integer")
    };
    *value
}

#[test]
fn shared_conformance_vectors_are_canonical_and_consumed() {
    let fixture =
        validate_canonical_manifest(include_bytes!("../../../conformance/bootstrap-v0.json"))
            .unwrap();
    let fields = manifest_object(&fixture);
    assert_eq!(
        fields.keys().map(String::as_str).collect::<Vec<_>>(),
        [
            "common_block_hex",
            "crc32c_kats",
            "crc64_ecma_kats",
            "inventory_entry_count",
            "inventory_hex",
            "schema",
            "section_crc32c_hex",
            "section_crc64_ecma_hex",
            "tier_frame_hex",
        ]
    );
    assert_eq!(
        manifest_text(&fields["schema"]),
        "golden-board.bootstrap-v0-fixtures/v0"
    );

    for row in manifest_array(&fields["crc32c_kats"]) {
        let row = manifest_object(row);
        assert_eq!(
            row.keys().map(String::as_str).collect::<Vec<_>>(),
            ["input_hex", "result_hex"]
        );
        assert_eq!(
            format!(
                "{:08x}",
                crc32c(&decode_hex(manifest_text(&row["input_hex"])))
            ),
            manifest_text(&row["result_hex"])
        );
    }
    for row in manifest_array(&fields["crc64_ecma_kats"]) {
        let row = manifest_object(row);
        assert_eq!(
            row.keys().map(String::as_str).collect::<Vec<_>>(),
            ["input_hex", "result_hex"]
        );
        assert_eq!(
            format!(
                "{:016x}",
                crc64_ecma(&decode_hex(manifest_text(&row["input_hex"])))
            ),
            manifest_text(&row["result_hex"])
        );
    }

    let common_raw = decode_hex(manifest_text(&fields["common_block_hex"]));
    let common = decode_common_block(&common_raw, 1).unwrap();
    assert_eq!(encode_common_block(&common).unwrap().as_slice(), common_raw);

    for key in ["section_crc32c_hex", "section_crc64_ecma_hex"] {
        let raw = decode_hex(manifest_text(&fields[key]));
        let section = decode_section(&raw).unwrap();
        assert_eq!(encode_section(&section).unwrap(), raw);
    }

    let inventory_raw = decode_hex(manifest_text(&fields["inventory_hex"]));
    let inventory = decode_inventory(&inventory_raw).unwrap();
    assert_eq!(
        inventory.entries.len() as u64,
        manifest_u64(&fields["inventory_entry_count"])
    );
    assert_eq!(encode_inventory(&inventory).unwrap(), inventory_raw);

    let tier_raw = decode_hex(manifest_text(&fields["tier_frame_hex"]));
    let tier = decode_tier_frame(&tier_raw, 2).unwrap();
    assert_eq!(encode_tier_frame(&tier).unwrap(), tier_raw);
}

#[test]
fn shared_inventory_rejections_are_exact() {
    let fixture =
        validate_canonical_manifest(include_bytes!("../../../conformance/bootstrap-v0.json"))
            .unwrap();
    let original = decode_hex(manifest_text(&manifest_object(&fixture)["inventory_hex"]));
    let rejections = validate_canonical_manifest(include_bytes!(
        "../../../conformance/bootstrap-invalid-v0.json"
    ))
    .unwrap();
    let fields = manifest_object(&rejections);
    assert_eq!(
        fields.keys().map(String::as_str).collect::<Vec<_>>(),
        ["inventory_mutations", "schema"]
    );
    assert_eq!(
        manifest_text(&fields["schema"]),
        "golden-board.bootstrap-v0-rejections/v0"
    );
    for row in manifest_array(&fields["inventory_mutations"]) {
        let row = manifest_object(row);
        assert_eq!(
            row.keys().map(String::as_str).collect::<Vec<_>>(),
            ["offset", "replacement_hex", "result_code"]
        );
        assert_eq!(manifest_u64(&row["result_code"]), 13);
        let offset = usize::try_from(manifest_u64(&row["offset"])).unwrap();
        let replacement = decode_hex(manifest_text(&row["replacement_hex"]));
        let mut mutated = original.clone();
        mutated[offset..offset + replacement.len()].copy_from_slice(&replacement);
        assert_eq!(
            error_code(decode_inventory(&mutated)),
            RejectCode::Inventory
        );
    }
}

#[test]
fn raw_validation_and_entry_hypothesis_order_are_exact() {
    assert_eq!(ENTRY_HYPOTHESES.len(), 16);
    for (index, hypothesis) in ENTRY_HYPOTHESES.iter().enumerate() {
        assert_eq!(hypothesis.transform, (index / 2) as u8);
        assert_eq!(hypothesis.polarity, (index % 2) as u8);
    }

    let mut bits = vec![0; 16];
    let normalized = (1usize, 2usize);
    let expected_observed = [
        (1, 2),
        (1, 1),
        (2, 1),
        (2, 2),
        (1, 1),
        (1, 2),
        (2, 2),
        (2, 1),
    ];
    for (transform, (row, column)) in expected_observed.into_iter().enumerate() {
        bits.fill(0);
        bits[row * 4 + column] = 1;
        let observation = RawObservation::parse(&bits, 16).unwrap();
        assert_eq!(
            observation
                .normalized_bit(
                    EntryHypothesis {
                        transform: transform as u8,
                        polarity: 0,
                    },
                    normalized.0,
                    normalized.1,
                )
                .unwrap(),
            1
        );
        assert_eq!(
            observation
                .normalized_bit(
                    EntryHypothesis {
                        transform: transform as u8,
                        polarity: 1,
                    },
                    normalized.0,
                    normalized.1,
                )
                .unwrap(),
            0
        );
    }

    assert_eq!(
        error_code(RawObservation::parse(&[], 0)),
        RejectCode::RawLength
    );
    assert_eq!(
        error_code(RawObservation::parse(&[0; 3], 4)),
        RejectCode::RawLength
    );
    assert_eq!(
        error_code(RawObservation::parse(&[0, 0, 2, 0], 4)),
        RejectCode::RawValue
    );
    assert_eq!(
        error_code(RawObservation::parse(&[0; 15], 15)),
        RejectCode::RawGeometry
    );
}

#[test]
fn shell_sectors_are_disjoint_complete_and_clockwise() {
    let side = 32usize;
    let width = 8usize;
    let per_sector = width * (side - width);
    let mut owners = BTreeMap::new();
    for sector in 0..4 {
        for index in 0..per_sector {
            let cell = sector_cell_at(side, width, sector, index).unwrap();
            assert!(owners.insert(cell, sector).is_none());
            assert!(
                cell.0 < width
                    || cell.0 >= side - width
                    || cell.1 < width
                    || cell.1 >= side - width
            );
        }
    }
    let expected_shell = side * side - (side - 2 * width) * (side - 2 * width);
    assert_eq!(owners.len(), expected_shell);
    assert_eq!(owners[&(0, 0)], 0);
    assert_eq!(owners[&(0, side - 1)], 1);
    assert_eq!(owners[&(side - 1, side - 1)], 2);
    assert_eq!(owners[&(side - 1, 0)], 3);

    assert_eq!(
        error_code(sector_cell(23, 8, 0, 0, 0)),
        RejectCode::ShellGeometry
    );
    assert_eq!(
        error_code(sector_cell(32, 7, 0, 0, 0)),
        RejectCode::ShellGeometry
    );
    assert_eq!(
        error_code(sector_cell(32, 8, 4, 0, 0)),
        RejectCode::ShellGeometry
    );
    assert_eq!(
        error_code(sector_cell(MAX_SIDE + 1, 8, 0, 0, 0)),
        RejectCode::ShellGeometry
    );
    assert_eq!(route_headroom_cells(100, 1).unwrap(), 5);
    assert_eq!(route_headroom_cells(20, 4).unwrap(), 16);
    assert_eq!(
        error_code(route_headroom_cells(0, usize::MAX)),
        RejectCode::ResourceLimit
    );
}

#[test]
fn crc_known_answers_match_the_normative_direct_algorithms() {
    let sequence: Vec<u8> = (0..=15).collect();
    for (bytes, expected) in [
        (&b""[..], 0x0000_0000),
        (&b"123456789"[..], 0xe306_9283),
        (&[0][..], 0x527d_5351),
        (&[0xff][..], 0xff00_0000),
        (&[0, 1, 2, 3][..], 0xd933_1aa3),
        (&sequence[..], 0xd9c9_08eb),
    ] {
        assert_eq!(crc32c(bytes), expected);
    }
    for (bytes, expected) in [
        (&b""[..], 0x0000_0000_0000_0000),
        (&b"123456789"[..], 0x6c40_df5f_0b49_7347),
        (&[0xff][..], 0x9afc_e626_ce85_b507),
        (&[0, 1, 2, 3][..], 0xf805_609e_ce1e_cbf3),
        (&sequence[..], 0xf9c4_2d91_abaf_3b55),
    ] {
        assert_eq!(crc64_ecma(bytes), expected);
    }
}

fn sample_block() -> CommonBlock {
    CommonBlock {
        profile_version: 1,
        section_id: 0x0102_0304,
        semantic_copy_id: 2,
        section_type: SECTION_CONTENT_BODY,
        section_version: 4,
        fragment_index: 0,
        fragment_count: 1,
        section_envelope_length: 3,
        payload: vec![0xaa, 0x55, 0x00],
    }
}

#[test]
fn common_block_has_one_literal_canonical_byte_vector() {
    let mut expected = vec![0; COMMON_BLOCK_BYTES];
    let prefix = decode_hex("000100000102030400020003000400000000000100030000000300000000aa5500");
    expected[..prefix.len()].copy_from_slice(&prefix);
    expected[187..].copy_from_slice(&decode_hex("5dbff7a6"));
    let encoded = encode_common_block(&sample_block()).unwrap();
    assert_eq!(encoded.as_slice(), expected);
    assert_eq!(decode_common_block(&encoded, 1).unwrap(), sample_block());

    let mut wrong_profile = encoded;
    wrong_profile[1] = 2;
    assert_eq!(
        error_code(decode_common_block(&wrong_profile, 1)),
        RejectCode::BlockFraming
    );
    let mut nonzero_pad = encoded;
    nonzero_pad[33] = 1;
    assert_eq!(
        error_code(decode_common_block(&nonzero_pad, 1)),
        RejectCode::FragmentShape
    );
    let mut wrong_check = encoded;
    wrong_check[190] ^= 1;
    assert_eq!(
        error_code(decode_common_block(&wrong_check, 1)),
        RejectCode::LocalCheck
    );
}

#[test]
fn fragmentation_and_semantic_copy_assembly_are_atomic() {
    for length in [22usize, 157, 158, 314, 315] {
        let envelope = encode_section(&SectionEnvelope {
            section_id: 91,
            section_type: SECTION_CONTENT_BODY,
            section_version: 2,
            closure_class: CLOSURE_M2_REQUIRED,
            check_id: CHECK_CRC32C,
            dependencies: vec![],
            payload: (0..length - 22).map(|index| index as u8).collect(),
        })
        .unwrap();
        assert_eq!(envelope.len(), length);
        let raw_blocks = fragment_envelope(7, 91, 1, SECTION_CONTENT_BODY, 2, &envelope).unwrap();
        let expected_count = length.div_ceil(COMMON_PAYLOAD_BYTES);
        assert_eq!(raw_blocks.len(), expected_count);
        let witnesses: Vec<_> = raw_blocks
            .iter()
            .rev()
            .map(|raw_block| FragmentWitness {
                raw_block: *raw_block,
                quality: RecoveryQuality::Verified,
            })
            .collect();
        assert_eq!(
            assemble_semantic_copy(&witnesses, 7).unwrap(),
            SectionWitness {
                envelope,
                all_units_verified: true
            }
        );
    }

    let envelope = encode_section(&SectionEnvelope {
        section_id: 91,
        section_type: SECTION_CONTENT_BODY,
        section_version: 2,
        closure_class: CLOSURE_M2_REQUIRED,
        check_id: CHECK_CRC32C,
        dependencies: vec![],
        payload: vec![0x5a; 200],
    })
    .unwrap();
    let blocks = fragment_envelope(7, 91, 1, SECTION_CONTENT_BODY, 2, &envelope).unwrap();
    assert_eq!(
        error_code(assemble_semantic_copy(
            &[FragmentWitness {
                raw_block: blocks[0],
                quality: RecoveryQuality::Verified,
            }],
            7
        )),
        RejectCode::SectionIncomplete
    );
    let recovered = FragmentWitness {
        raw_block: blocks[0],
        quality: RecoveryQuality::Recovered,
    };
    let verified_duplicate = FragmentWitness {
        raw_block: blocks[0],
        quality: RecoveryQuality::Verified,
    };
    let second = FragmentWitness {
        raw_block: blocks[1],
        quality: RecoveryQuality::Verified,
    };
    assert!(
        assemble_semantic_copy(&[recovered, verified_duplicate, second], 7)
            .unwrap()
            .all_units_verified
    );
    let mut conflicting_block = decode_common_block(&blocks[0], 7).unwrap();
    conflicting_block.payload[0] ^= 1;
    let conflicting = encode_common_block(&conflicting_block).unwrap();
    assert_eq!(
        error_code(assemble_semantic_copy(
            &[
                FragmentWitness {
                    raw_block: blocks[0],
                    quality: RecoveryQuality::Verified,
                },
                FragmentWitness {
                    raw_block: conflicting,
                    quality: RecoveryQuality::Verified,
                },
            ],
            7
        )),
        RejectCode::FragmentConflict
    );
    let mut unchecked = blocks[0];
    unchecked[190] ^= 1;
    assert_eq!(
        error_code(assemble_semantic_copy(
            &[
                FragmentWitness {
                    raw_block: unchecked,
                    quality: RecoveryQuality::Verified,
                },
                FragmentWitness {
                    raw_block: blocks[1],
                    quality: RecoveryQuality::Verified,
                },
            ],
            7,
        )),
        RejectCode::LocalCheck
    );
    assert_eq!(
        error_code(fragment_envelope(
            7,
            92,
            1,
            SECTION_CONTENT_BODY,
            2,
            &envelope,
        )),
        RejectCode::SectionFraming
    );
}

fn sample_envelope(check_id: u8) -> SectionEnvelope {
    SectionEnvelope {
        section_id: 0x0102_0304,
        section_type: SECTION_CONTENT_BODY,
        section_version: 4,
        closure_class: CLOSURE_M2_REQUIRED,
        check_id,
        dependencies: vec![1, 2, 9],
        payload: vec![0xaa, 0x55, 0],
    }
}

#[test]
fn semantic_envelopes_match_literal_crc32c_and_crc64_vectors() {
    let crc32 =
        decode_hex("000001020304000300048001000300000003000000010000000200000009aa55004b9ccea9");
    let crc64 = decode_hex(
        "000001020304000300048002000300000003000000010000000200000009aa550088ff87a7641ab5ba",
    );
    assert_eq!(
        encode_section(&sample_envelope(CHECK_CRC32C)).unwrap(),
        crc32
    );
    assert_eq!(
        encode_section(&sample_envelope(CHECK_CRC64_ECMA)).unwrap(),
        crc64
    );
    assert_eq!(
        decode_section(&crc32).unwrap(),
        sample_envelope(CHECK_CRC32C)
    );
    assert_eq!(
        decode_section(&crc64).unwrap(),
        sample_envelope(CHECK_CRC64_ECMA)
    );

    let mut bad_check = crc32.clone();
    *bad_check.last_mut().unwrap() ^= 1;
    assert_eq!(
        error_code(decode_section(&bad_check)),
        RejectCode::SectionCheck
    );
    let mut trailing = crc32.clone();
    trailing.push(0);
    assert_eq!(
        error_code(decode_section(&trailing)),
        RejectCode::TrailingData
    );
    let mut duplicate_before_trailing = crc32.clone();
    duplicate_before_trailing[22..26].copy_from_slice(&1u32.to_be_bytes());
    duplicate_before_trailing.push(0);
    assert_eq!(
        error_code(decode_section(&duplicate_before_trailing)),
        RejectCode::SectionFraming
    );
    let mut self_dependency = sample_envelope(CHECK_CRC32C);
    self_dependency.dependencies = vec![self_dependency.section_id];
    assert_eq!(
        error_code(encode_section(&self_dependency)),
        RejectCode::SectionFraming
    );
}

#[test]
fn complete_section_aggregation_is_order_independent_and_quality_uses_any_verified_witness() {
    let envelope = encode_section(&sample_envelope(CHECK_CRC32C)).unwrap();
    let a = SectionWitness {
        envelope: envelope.clone(),
        all_units_verified: false,
    };
    let b = SectionWitness {
        envelope: envelope.clone(),
        all_units_verified: true,
    };
    assert_eq!(
        aggregate_section_witnesses(&[a.clone(), b.clone()]).unwrap(),
        CanonicalSection {
            envelope,
            quality: RecoveryQuality::Verified,
        }
    );
    assert_eq!(
        aggregate_section_witnesses(&[b, a]).unwrap().quality,
        RecoveryQuality::Verified
    );
    assert_eq!(
        error_code(aggregate_section_witnesses(&[
            SectionWitness {
                envelope: encode_section(&sample_envelope(CHECK_CRC32C)).unwrap(),
                all_units_verified: true,
            },
            SectionWitness {
                envelope: encode_section(&SectionEnvelope {
                    section_id: 10,
                    ..sample_envelope(CHECK_CRC32C)
                })
                .unwrap(),
                all_units_verified: true,
            },
        ])),
        RejectCode::Ambiguous
    );
    assert_eq!(
        error_code(aggregate_section_witnesses(&[SectionWitness {
            envelope: vec![1, 2, 3],
            all_units_verified: true,
        }])),
        RejectCode::SectionFraming
    );
}

fn sample_inventory(split_closures: bool) -> Inventory {
    let required: Vec<u32> = (4..36).collect();
    let all: Vec<u32> = (4..68).collect();
    let mut entries = vec![
        InventoryEntry {
            section_id: 1,
            section_type: SECTION_INVENTORY,
            section_version: 0,
            closure_class: CLOSURE_M2_REQUIRED,
            check_id: CHECK_CRC32C,
            copy_count: 2,
            physical_replica_count: 1,
            dependencies: vec![],
            logical_payload_length: 0,
            game_ordinal: None,
        },
        InventoryEntry {
            section_id: 2,
            section_type: SECTION_TIER_FRAME,
            section_version: 0,
            closure_class: CLOSURE_M2_REQUIRED,
            check_id: CHECK_CRC32C,
            copy_count: 2,
            physical_replica_count: 1,
            dependencies: if split_closures {
                required
            } else {
                all.clone()
            },
            logical_payload_length: 1,
            game_ordinal: None,
        },
        InventoryEntry {
            section_id: 3,
            section_type: SECTION_TIER_FRAME,
            section_version: 0,
            closure_class: CLOSURE_M2_REQUIRED,
            check_id: CHECK_CRC64_ECMA,
            copy_count: 2,
            physical_replica_count: 1,
            dependencies: all,
            logical_payload_length: 1,
            game_ordinal: None,
        },
    ];
    for ordinal in 0..64u16 {
        entries.push(InventoryEntry {
            section_id: u32::from(ordinal) + 4,
            section_type: SECTION_CONTENT_BODY,
            section_version: 0,
            closure_class: if split_closures && ordinal >= 32 {
                CLOSURE_M2_ALL_ONLY
            } else {
                CLOSURE_M2_REQUIRED
            },
            check_id: CHECK_CRC32C,
            copy_count: 1,
            physical_replica_count: 1,
            dependencies: vec![],
            logical_payload_length: 1,
            game_ordinal: Some(ordinal),
        });
    }
    let dependency_count: usize = entries.iter().map(|entry| entry.dependencies.len()).sum();
    entries[0].logical_payload_length = (8 + 20 * entries.len() + 4 * dependency_count) as u32;
    Inventory {
        inventory_version: 0,
        entries,
    }
}

#[test]
fn inventory_round_trip_enforces_games_graph_and_complete_closure() {
    let inventory = sample_inventory(false);
    let raw = encode_inventory(&inventory).unwrap();
    assert_eq!(
        raw.len(),
        inventory.entries[0].logical_payload_length as usize
    );
    assert_eq!(decode_inventory(&raw).unwrap(), inventory);

    let block = CommonBlock {
        profile_version: 1,
        section_id: 4,
        semantic_copy_id: 0,
        section_type: SECTION_CONTENT_BODY,
        section_version: 0,
        fragment_index: 0,
        fragment_count: 1,
        section_envelope_length: 1,
        payload: vec![0],
    };
    validate_common_against_inventory(&block, &inventory).unwrap();
    let mut out_of_range_copy = block;
    out_of_range_copy.semantic_copy_id = 1;
    assert_eq!(
        error_code(validate_common_against_inventory(
            &out_of_range_copy,
            &inventory,
        )),
        RejectCode::Inventory
    );

    let available: BTreeSet<u32> = inventory
        .entries
        .iter()
        .map(|entry| entry.section_id)
        .collect();
    let closure = dependency_closure(&inventory, &[2], &available).unwrap();
    assert_eq!(closure.first(), Some(&2));
    assert_eq!(closure.last(), Some(&67));
    let mut missing = available.clone();
    missing.remove(&40);
    assert_eq!(
        error_code(dependency_closure(&inventory, &[2], &missing)),
        RejectCode::Dependency
    );

    let mut duplicate_game = inventory.clone();
    duplicate_game.entries[4].game_ordinal = Some(0);
    assert_eq!(
        error_code(encode_inventory(&duplicate_game)),
        RejectCode::Inventory
    );
    let mut wrong_self_length = inventory.clone();
    wrong_self_length.entries[0].logical_payload_length += 1;
    assert_eq!(
        error_code(encode_inventory(&wrong_self_length)),
        RejectCode::Inventory
    );
    let mut cyclic = inventory.clone();
    cyclic.entries[3].dependencies = vec![5];
    cyclic.entries[4].dependencies = vec![4];
    cyclic.entries[0].logical_payload_length += 8;
    assert_eq!(
        error_code(encode_inventory(&cyclic)),
        RejectCode::Dependency
    );
    let mut trailing = raw;
    trailing.push(0);
    assert_eq!(
        error_code(decode_inventory(&trailing)),
        RejectCode::TrailingData
    );
}

fn sample_inventory_v1() -> Inventory {
    let body_ids = (4_u32..68).collect::<Vec<_>>();
    let mut entries = vec![
        InventoryEntry {
            section_id: 1,
            section_type: SECTION_INVENTORY,
            section_version: 1,
            closure_class: CLOSURE_M2_REQUIRED,
            check_id: CHECK_CRC32C,
            copy_count: 1,
            physical_replica_count: 5,
            dependencies: vec![],
            logical_payload_length: 0,
            game_ordinal: None,
        },
        InventoryEntry {
            section_id: 2,
            section_type: SECTION_TIER_FRAME,
            section_version: 0,
            closure_class: CLOSURE_M2_REQUIRED,
            check_id: CHECK_CRC32C,
            copy_count: 1,
            physical_replica_count: 5,
            dependencies: vec![16],
            logical_payload_length: 1,
            game_ordinal: None,
        },
        InventoryEntry {
            section_id: 3,
            section_type: SECTION_TIER_FRAME,
            section_version: 0,
            closure_class: CLOSURE_M2_REQUIRED,
            check_id: CHECK_CRC32C,
            copy_count: 1,
            physical_replica_count: 5,
            dependencies: body_ids,
            logical_payload_length: 1,
            game_ordinal: None,
        },
    ];
    for ordinal in 0..64_u16 {
        let section_id = u32::from(ordinal) + 4;
        let is_spine = section_id == 16;
        entries.push(InventoryEntry {
            section_id,
            section_type: SECTION_CONTENT_BODY,
            section_version: 0,
            closure_class: if is_spine {
                CLOSURE_M2_REQUIRED
            } else {
                CLOSURE_M2_ALL_ONLY
            },
            check_id: CHECK_CRC32C,
            copy_count: 1,
            physical_replica_count: if is_spine {
                5
            } else if section_id % 2 == 0 {
                2
            } else {
                1
            },
            dependencies: vec![],
            logical_payload_length: 1,
            game_ordinal: Some(ordinal),
        });
    }
    let dependency_count: usize = entries.iter().map(|entry| entry.dependencies.len()).sum();
    entries[0].logical_payload_length = (8 + 20 * entries.len() + 4 * dependency_count) as u32;
    Inventory {
        inventory_version: 1,
        entries,
    }
}

#[test]
fn inventory_v1_round_trip_binds_semantic_copy_and_physical_factor() {
    let inventory = sample_inventory_v1();
    let raw = encode_inventory(&inventory).unwrap();
    assert_eq!(&raw[..2], &1_u16.to_be_bytes());
    assert_eq!(raw[8 + 10], 1);
    assert_eq!(raw[8 + 11], 5 << 1);
    assert_eq!(decode_inventory(&raw).unwrap(), inventory);

    let mut bad_copy = raw.clone();
    bad_copy[8 + 10] = 2;
    assert_eq!(
        error_code(decode_inventory(&bad_copy)),
        RejectCode::Inventory
    );

    let mut bad_factor = raw.clone();
    bad_factor[8 + 11] = 3 << 1;
    assert_eq!(
        error_code(decode_inventory(&bad_factor)),
        RejectCode::Inventory
    );

    let mut reserved = raw.clone();
    reserved[8 + 11] |= 0x80;
    assert_eq!(
        error_code(decode_inventory(&reserved)),
        RejectCode::Inventory
    );

    let section_sixteen = inventory
        .entries
        .binary_search_by_key(&16, |entry| entry.section_id)
        .unwrap();
    let mut missing_spine = inventory.clone();
    missing_spine.entries[section_sixteen].physical_replica_count = 2;
    assert_eq!(
        error_code(encode_inventory(&missing_spine)),
        RejectCode::Inventory
    );
}

#[test]
fn tier_frame_inventory_membership_and_singular_assembly_are_exact() {
    let inventory = sample_inventory(true);
    let body_ids: Vec<u32> = (4..36).collect();
    let bodies: BTreeMap<u32, Vec<u8>> = body_ids
        .iter()
        .copied()
        .map(|id| {
            let record_id = (id - 3) as u16;
            let mut frame = Vec::new();
            frame.extend_from_slice(&record_id.to_be_bytes());
            frame.extend_from_slice(&1u16.to_be_bytes());
            frame.extend_from_slice(&1u32.to_be_bytes());
            frame.push(id as u8);
            (id, frame)
        })
        .collect();
    let root = vec![0, 68, 0, 14, 0, 0, 0, 4, 0, 4, 0, 1];
    let length = 4 + bodies.values().map(Vec::len).sum::<usize>() + root.len();
    let tier = TierFrame {
        tier_id: 0,
        body_section_ids: body_ids.clone(),
        assembled_stream_byte_length: length as u32,
        assembled_record_count: 33,
        root_record_bytes: root.clone(),
    };
    let raw_tier = encode_tier_frame(&tier).unwrap();
    assert_eq!(decode_tier_frame(&raw_tier, 2).unwrap(), tier);
    let envelope = SectionEnvelope {
        section_id: 2,
        section_type: SECTION_TIER_FRAME,
        section_version: 0,
        closure_class: CLOSURE_M2_REQUIRED,
        check_id: CHECK_CRC32C,
        dependencies: body_ids,
        payload: raw_tier.clone(),
    };
    let mut matching_inventory = inventory.clone();
    matching_inventory.entries[1].logical_payload_length = raw_tier.len() as u32;
    validate_tier_against_inventory(&tier, &envelope, &matching_inventory).unwrap();

    let assembled = assemble_tier_bytes(&tier, &bodies).unwrap();
    assert_eq!(&assembled[..4], &[0, 0, 0, 33]);
    assert_eq!(&assembled[assembled.len() - root.len()..], root);
    assert_eq!(
        error_code(assemble_content_stream(&tier, &bodies)),
        RejectCode::ContentStream
    );

    let mut missing = bodies;
    missing.remove(&10);
    assert_eq!(
        error_code(assemble_tier_bytes(&tier, &missing)),
        RejectCode::Dependency
    );
    let mut trailing = raw_tier;
    trailing.push(0);
    assert_eq!(
        error_code(decode_tier_frame(&trailing, 2)),
        RejectCode::TrailingData
    );

    let mut over_limit = tier;
    over_limit.assembled_stream_byte_length = MAX_ENVELOPE_BYTES as u32 + 1;
    assert_eq!(
        error_code(encode_tier_frame(&over_limit)),
        RejectCode::ResourceLimit
    );
}
