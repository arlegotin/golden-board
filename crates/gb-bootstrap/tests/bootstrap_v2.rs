use gb_bootstrap as legacy;
use gb_bootstrap::bootstrap_v2 as v2;
use gb_bootstrap::{
    CHECK_CRC32C, CHECK_CRC64_ECMA, CLOSURE_M2_ALL_ONLY, CLOSURE_M2_REQUIRED, Inventory,
    InventoryEntry, SECTION_CAPACITY_PROBE, SECTION_CONTENT_BODY, SECTION_INVENTORY,
    SECTION_LOAD_PROBE, SECTION_RESERVE_PROBE, SECTION_TIER_FRAME,
};
use std::collections::BTreeMap;

fn bodies() -> Vec<u32> {
    (16..=18).chain(100..=163).chain(200..=210).collect()
}

fn entry(id: u32, kind: u16, version: u16, required: bool) -> InventoryEntry {
    InventoryEntry {
        section_id: id,
        section_type: kind,
        section_version: version,
        closure_class: if required {
            CLOSURE_M2_REQUIRED
        } else {
            CLOSURE_M2_ALL_ONLY
        },
        check_id: CHECK_CRC32C,
        copy_count: 1,
        physical_replica_count: if required { 5 } else { 1 },
        dependencies: vec![],
        logical_payload_length: 1,
        game_ordinal: None,
    }
}

fn update_length(inventory: &mut Inventory) {
    let dependencies: usize = inventory
        .entries
        .iter()
        .map(|row| row.dependencies.len())
        .sum();
    inventory.entries[0].logical_payload_length =
        (8 + inventory.entries.len() * 20 + dependencies * 4) as u32;
}

fn fixture() -> Inventory {
    let mut entries = vec![
        entry(1, SECTION_INVENTORY, 2, true),
        entry(2, SECTION_TIER_FRAME, 0, true),
        entry(3, SECTION_TIER_FRAME, 0, true),
    ];
    entries[1].dependencies = vec![16, 17, 18];
    entries[1].logical_payload_length = 46;
    entries[2].dependencies = bodies();
    entries[2].logical_payload_length = 346;
    for id in bodies() {
        let mut row = entry(id, SECTION_CONTENT_BODY, u16::from(id % 2 == 0), id < 100);
        row.logical_payload_length = 100;
        if (100..=163).contains(&id) {
            row.game_ordinal = Some((id - 100) as u16);
        }
        entries.push(row);
    }
    let mut value = Inventory {
        inventory_version: 2,
        entries,
    };
    update_length(&mut value);
    value
}

fn row_mut(inventory: &mut Inventory, id: u32) -> &mut InventoryEntry {
    inventory
        .entries
        .iter_mut()
        .find(|row| row.section_id == id)
        .unwrap()
}

fn wire_offset(raw: &[u8], wanted: u32) -> usize {
    let count = u16::from_be_bytes([raw[2], raw[3]]);
    let mut cursor = 8;
    for _ in 0..count {
        let id = u32::from_be_bytes(raw[cursor..cursor + 4].try_into().unwrap());
        if id == wanted {
            return cursor;
        }
        let dependencies = u16::from_be_bytes([raw[cursor + 12], raw[cursor + 13]]);
        cursor += 20 + 4 * usize::from(dependencies);
    }
    panic!("missing fixture entry {wanted}");
}

#[test]
fn exact_81_entry_metadata_round_trip_and_legacy_rejection() {
    let inventory = fixture();
    assert_eq!(inventory.entries.len(), 81);
    assert_eq!(inventory.entries[0].logical_payload_length, 1952);
    let raw = v2::encode_inventory(&inventory).unwrap();
    assert_eq!(raw.len(), 1952);
    assert_eq!(&raw[..8], &[0, 2, 0, 81, 0, 0, 0, 64]);
    assert_eq!(
        &raw[8..28],
        &[
            0, 0, 0, 1, 0, 1, 0, 2, 128, 1, 1, 10, 0, 0, 0, 0, 7, 160, 255, 255,
        ]
    );
    assert_eq!(v2::decode_inventory(&raw).unwrap(), inventory);
    assert_eq!(v2::encode_inventory(&inventory).unwrap(), raw);
    assert!(legacy::encode_inventory(&inventory).is_err());
    assert!(legacy::decode_inventory(&raw).is_err());
    let game = wire_offset(&raw, 100);
    assert_eq!(raw[game + 11], 3);
    assert_eq!(&raw[game + 18..game + 20], &[0, 0]);
}

#[test]
fn versions_checks_copy_counts_and_exact_spine_are_closed() {
    let good = fixture();
    for version in [0, 1, 3, u16::MAX] {
        let mut changed = good.clone();
        changed.inventory_version = version;
        assert!(v2::encode_inventory(&changed).is_err());
    }
    for id in [1, 2, 3, 16, 17, 18, 100, 163, 200, 210] {
        for factor in [0, 1, 2, 3, 5, 7] {
            let mut changed = good.clone();
            row_mut(&mut changed, id).physical_replica_count = factor;
            let expected = if id <= 18 { 5 } else { 1 };
            assert_eq!(
                v2::encode_inventory(&changed).is_ok(),
                factor == expected,
                "id={id}, factor={factor}"
            );
        }
        for check in [0, CHECK_CRC64_ECMA, 255] {
            let mut changed = good.clone();
            row_mut(&mut changed, id).check_id = check;
            assert!(v2::encode_inventory(&changed).is_err());
        }
        for copies in [0, 2, 3, 255] {
            let mut changed = good.clone();
            row_mut(&mut changed, id).copy_count = copies;
            assert!(v2::encode_inventory(&changed).is_err());
        }
        let mut changed = good.clone();
        row_mut(&mut changed, id).closure_class ^= 1;
        assert!(v2::encode_inventory(&changed).is_err());
    }
}

#[test]
fn bodies_dependencies_and_game_ordinals_are_exact_not_just_complete_counts() {
    let good = fixture();
    for id in bodies() {
        let mut missing = good.clone();
        missing.entries.retain(|row| row.section_id != id);
        update_length(&mut missing);
        assert!(v2::encode_inventory(&missing).is_err(), "missing body {id}");
    }
    for id in [1, 2, 3, 16, 100, 200] {
        let mut changed = good.clone();
        row_mut(&mut changed, id).dependencies = vec![100];
        update_length(&mut changed);
        assert!(v2::encode_inventory(&changed).is_err());
    }
    for tier in [2, 3] {
        let mut changed = good.clone();
        row_mut(&mut changed, tier).dependencies.pop();
        update_length(&mut changed);
        assert!(v2::encode_inventory(&changed).is_err());
        let mut changed = good.clone();
        row_mut(&mut changed, tier).dependencies.swap(0, 1);
        assert!(v2::encode_inventory(&changed).is_err());
    }
    for id in [16, 17, 18, 100, 163, 200, 210] {
        let mut changed = good.clone();
        row_mut(&mut changed, id).section_version = 2;
        assert!(v2::encode_inventory(&changed).is_err());
        let mut changed = good.clone();
        row_mut(&mut changed, id).section_type = SECTION_CAPACITY_PROBE;
        assert!(v2::encode_inventory(&changed).is_err());
        let mut changed = good.clone();
        row_mut(&mut changed, id).game_ordinal = Some(0);
        if id != 100 {
            assert!(v2::encode_inventory(&changed).is_err());
        }
    }
    let mut moved = good.clone();
    row_mut(&mut moved, 100).game_ordinal = Some(1);
    row_mut(&mut moved, 101).game_ordinal = Some(0);
    assert!(v2::encode_inventory(&moved).is_err());
    let mut unknown = good.clone();
    row_mut(&mut unknown, 200).section_id = 199;
    assert!(v2::encode_inventory(&unknown).is_err());
    let mut duplicate = good.clone();
    duplicate.entries[4].section_id = 16;
    assert!(v2::encode_inventory(&duplicate).is_err());
    let mut reordered = good;
    reordered.entries.swap(3, 4);
    assert!(v2::encode_inventory(&reordered).is_err());
}

#[test]
fn probe_metadata_has_exact_local_rules_without_ledger_eligibility_claim() {
    for (kind, factors) in [
        (SECTION_CAPACITY_PROBE, vec![1, 2]),
        (SECTION_RESERVE_PROBE, vec![2]),
        (SECTION_LOAD_PROBE, vec![1]),
    ] {
        for factor in [1, 2, 5] {
            let mut value = fixture();
            let mut probe = entry(211, kind, 0, false);
            probe.physical_replica_count = factor;
            probe.logical_payload_length = 1;
            value.entries.push(probe);
            update_length(&mut value);
            assert_eq!(
                v2::encode_inventory(&value).is_ok(),
                factors.contains(&factor)
            );
            if factors.contains(&factor) {
                let raw = v2::encode_inventory(&value).unwrap();
                assert_eq!(v2::decode_inventory(&raw).unwrap(), value);
                let mut high = value.clone();
                high.entries.last_mut().unwrap().section_id = u32::MAX;
                assert_eq!(
                    v2::decode_inventory(&v2::encode_inventory(&high).unwrap()).unwrap(),
                    high
                );
                for mutation in 0..7 {
                    let mut changed = value.clone();
                    let row = changed.entries.last_mut().unwrap();
                    match mutation {
                        0 => row.section_version = 1,
                        1 => row.dependencies = vec![16],
                        2 => row.game_ordinal = Some(0),
                        3 => row.closure_class = CLOSURE_M2_REQUIRED,
                        4 => row.section_id = 19,
                        5 => row.logical_payload_length = 0,
                        _ => row.logical_payload_length = 16385,
                    }
                    changed.entries.sort_by_key(|row| row.section_id);
                    update_length(&mut changed);
                    assert!(v2::encode_inventory(&changed).is_err());
                }
            }
        }
    }
}

#[test]
fn stored_lengths_inventory_self_length_and_maximum_entry_population_are_bounded() {
    let good = fixture();
    for id in [2, 3, 16, 100, 210] {
        for length in [0, 16384, 16385, u32::MAX] {
            let mut value = good.clone();
            row_mut(&mut value, id).logical_payload_length = length;
            assert_eq!(v2::encode_inventory(&value).is_ok(), length == 16384);
        }
    }
    let mut wrong_self = good.clone();
    wrong_self.entries[0].logical_payload_length += 1;
    assert!(v2::encode_inventory(&wrong_self).is_err());
    let mut at_limit = good;
    for id in 211..932 {
        at_limit
            .entries
            .push(entry(id, SECTION_CAPACITY_PROBE, 0, false));
    }
    update_length(&mut at_limit);
    assert_eq!(at_limit.entries.len(), 802);
    let raw = v2::encode_inventory(&at_limit).unwrap();
    assert_eq!(raw.len(), 16372);
    assert_eq!(v2::decode_inventory(&raw).unwrap(), at_limit);
    at_limit
        .entries
        .push(entry(932, SECTION_CAPACITY_PROBE, 0, false));
    update_length(&mut at_limit);
    assert!(v2::encode_inventory(&at_limit).is_err());
    assert!(v2::decode_inventory(&vec![0; 16385]).is_err());
}

#[test]
fn malformed_wire_is_atomic_and_has_no_version_or_flags_fallback() {
    let good = v2::encode_inventory(&fixture()).unwrap();
    for (offset, width, value) in [
        (0, 2, 0u32),
        (0, 2, 1),
        (0, 2, 3),
        (2, 2, 0),
        (2, 2, 4097),
        (4, 2, 1),
        (6, 2, 63),
        (18, 1, 2),
        (19, 1, 0),
        (19, 1, 6),
        (19, 1, 138),
        (20, 2, 4096),
        (22, 4, 1951),
        (26, 2, 0),
    ] {
        let mut raw = good.clone();
        raw[offset..offset + width].copy_from_slice(&value.to_be_bytes()[4 - width..]);
        assert!(
            v2::decode_inventory(&raw).is_err(),
            "offset={offset} value={value}"
        );
    }
    let game = wire_offset(&good, 100);
    for flags in [0, 2, 4, 6, 10, 0x83] {
        let mut raw = good.clone();
        raw[game + 11] = flags;
        assert!(v2::decode_inventory(&raw).is_err());
    }
    for boundary in [0, 1, 7, 8, 27, 28, 30, 40, good.len() - 1] {
        assert!(v2::decode_inventory(&good[..boundary]).is_err());
    }
    let mut trailing = good;
    trailing.push(0);
    assert!(v2::decode_inventory(&trailing).is_err());
}

fn envelope(row: &InventoryEntry, payload: Vec<u8>) -> Vec<u8> {
    legacy::encode_section(&legacy::SectionEnvelope {
        section_id: row.section_id,
        section_type: row.section_type,
        section_version: row.section_version,
        closure_class: row.closure_class,
        check_id: row.check_id,
        dependencies: row.dependencies.clone(),
        payload,
    })
    .unwrap()
}

fn content_fixture() -> (BTreeMap<u32, Vec<u8>>, Vec<u8>, Vec<u8>) {
    let compiled = gb_slice::compile_slice_v1(
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
    let mut frames = BTreeMap::new();
    let all = compiled.all_stream();
    let mut cursor = 4;
    while cursor < all.len() {
        let id = u16::from_be_bytes(all[cursor..cursor + 2].try_into().unwrap());
        let length = u32::from_be_bytes(all[cursor + 4..cursor + 8].try_into().unwrap()) as usize;
        frames.insert(id, &all[cursor..cursor + 8 + length]);
        cursor += 8 + length;
    }
    let mut inventory = fixture();
    let mut sections = BTreeMap::new();
    for assignment in compiled.assignments() {
        let body: Vec<u8> = assignment
            .record_ids()
            .iter()
            .flat_map(|id| frames[id].iter().copied())
            .collect();
        let (version, payload) = legacy::body_codec_v1::encode_body(&body).unwrap();
        let row = row_mut(&mut inventory, u32::from(assignment.section_id()));
        row.section_version = version;
        row.logical_payload_length = payload.len() as u32;
        sections.insert(row.section_id, envelope(row, payload));
    }
    for root in compiled.tier_roots() {
        let row = row_mut(&mut inventory, u32::from(root.section_id()));
        let stream = if row.section_id == 2 {
            compiled.required_stream()
        } else {
            compiled.all_stream()
        };
        let payload = legacy::encode_tier_frame(&legacy::TierFrame {
            tier_id: (row.section_id - 2) as u8,
            body_section_ids: row.dependencies.clone(),
            assembled_stream_byte_length: stream.len() as u32,
            assembled_record_count: u16::from_be_bytes(stream[2..4].try_into().unwrap()),
            root_record_bytes: root.frame().to_vec(),
        })
        .unwrap();
        row.logical_payload_length = payload.len() as u32;
        sections.insert(row.section_id, envelope(row, payload));
    }
    let raw_inventory = v2::encode_inventory(&inventory).unwrap();
    sections.insert(1, envelope(&inventory.entries[0], raw_inventory));
    (
        sections,
        compiled.required_stream().to_vec(),
        compiled.all_stream().to_vec(),
    )
}

#[test]
fn recovered_streams_use_checked_envelopes_and_full_typed_source_compilation() {
    let (sections, required, all) = content_fixture();
    let result = v2::recover_content(&sections).unwrap();
    assert_eq!(result.required_bytes, Some(required.clone()));
    assert_eq!(result.all_bytes, Some(all));
    assert_eq!(
        result.checked_section_ids,
        sections.keys().copied().collect::<Vec<_>>()
    );
    assert!(result.rejected_section_ids.is_empty());
    let mut missing = sections.clone();
    missing.remove(&100);
    let result = v2::recover_content(&missing).unwrap();
    assert_eq!(result.required_bytes, Some(required));
    assert_eq!(result.all_bytes, None);
    assert!(!result.checked_section_ids.contains(&100));
    assert!(result.rejected_section_ids.is_empty());
    let mut no_required = sections;
    no_required.remove(&17);
    let result = v2::recover_content(&no_required).unwrap();
    assert_eq!((result.required_bytes, result.all_bytes), (None, None));
}

#[test]
fn checked_root_and_codec_failures_never_become_content_success() {
    let (sections, required, _) = content_fixture();
    for tier_id in [2, 3] {
        for invalid_entry in [0u16, 1] {
            let mut changed = sections.clone();
            let mut value = legacy::decode_section(&changed[&tier_id]).unwrap();
            let count = u16::from_be_bytes(value.payload[4..6].try_into().unwrap()) as usize;
            let entry = 22 + 4 * count + 8;
            value.payload[entry..entry + 2].copy_from_slice(&invalid_entry.to_be_bytes());
            changed.insert(tier_id, legacy::encode_section(&value).unwrap());
            let result = v2::recover_content(&changed).unwrap();
            assert_eq!(
                result.required_bytes,
                if tier_id == 2 {
                    None
                } else {
                    Some(required.clone())
                }
            );
            assert_eq!(result.all_bytes, None);
            assert!(result.checked_section_ids.contains(&tier_id));
            assert!(result.rejected_section_ids.is_empty());
        }
    }
    let mut changed = sections;
    let mut value = legacy::decode_section(&changed[&16]).unwrap();
    assert_eq!(value.section_version, 1);
    value.payload[0] = 255;
    changed.insert(16, legacy::encode_section(&value).unwrap());
    let result = v2::recover_content(&changed).unwrap();
    assert_eq!((result.required_bytes, result.all_bytes), (None, None));
    assert!(result.checked_section_ids.contains(&16));
    assert!(result.rejected_section_ids.is_empty());
}

#[test]
fn missing_inventory_unowned_ids_and_malformed_envelopes_fail_closed() {
    let (sections, required, _) = content_fixture();
    let single = BTreeMap::from([(100, sections[&100].clone())]);
    assert!(v2::recover_content(&single).is_err());
    assert!(v2::recover_content(&BTreeMap::new()).is_err());
    let mut unknown = sections.clone();
    unknown.insert(211, sections[&100].clone());
    assert!(v2::recover_content(&unknown).is_err());
    let mut bad_inventory = sections.clone();
    *bad_inventory.get_mut(&1).unwrap().last_mut().unwrap() ^= 1;
    assert!(v2::recover_content(&bad_inventory).is_err());
    for wrong in 0..3 {
        let mut changed = sections.clone();
        let value = if wrong == 0 {
            let mut raw = changed[&100].clone();
            *raw.last_mut().unwrap() ^= 1;
            raw
        } else if wrong == 1 {
            changed[&101].clone()
        } else {
            let mut value = legacy::decode_section(&changed[&100]).unwrap();
            value.section_version ^= 1;
            legacy::encode_section(&value).unwrap()
        };
        changed.insert(100, value);
        let result = v2::recover_content(&changed).unwrap();
        assert_eq!(result.required_bytes, Some(required.clone()));
        assert_eq!(result.all_bytes, None);
        assert_eq!(result.rejected_section_ids, vec![100]);
        assert!(!result.checked_section_ids.contains(&100));
    }
}

#[test]
fn record_boundaries_are_checked_even_if_concatenated_content_would_be_identical() {
    let (mut sections, _, _) = content_fixture();
    let mut inventory_envelope = legacy::decode_section(&sections[&1]).unwrap();
    let mut inventory = v2::decode_inventory(&inventory_envelope.payload).unwrap();
    let first = legacy::decode_section(&sections[&16]).unwrap();
    let second = legacy::decode_section(&sections[&17]).unwrap();
    let mut a = legacy::body_codec_v1::decode_body(first.section_version, &first.payload).unwrap();
    let mut b =
        legacy::body_codec_v1::decode_body(second.section_version, &second.payload).unwrap();
    let joined = [a.as_slice(), b.as_slice()].concat();
    b.insert(0, a.pop().unwrap());
    assert_eq!([a.as_slice(), b.as_slice()].concat(), joined);
    for (id, raw) in [(16, a), (17, b)] {
        let (version, payload) = legacy::body_codec_v1::encode_body(&raw).unwrap();
        let row = row_mut(&mut inventory, id);
        row.section_version = version;
        row.logical_payload_length = payload.len() as u32;
        sections.insert(id, envelope(row, payload));
    }
    inventory_envelope.payload = v2::encode_inventory(&inventory).unwrap();
    sections.insert(1, legacy::encode_section(&inventory_envelope).unwrap());
    let result = v2::recover_content(&sections).unwrap();
    assert_eq!((result.required_bytes, result.all_bytes), (None, None));
    assert_eq!(result.checked_section_ids.len(), 81);
    assert!(result.rejected_section_ids.is_empty());
}
