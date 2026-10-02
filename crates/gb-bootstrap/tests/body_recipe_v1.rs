use std::collections::BTreeMap;

use gb_bootstrap::body_codec_v1::{decode_lzss, encode_lzss};
use gb_bootstrap::body_recipe_v1::{build_body_recipe_package, build_revision_recipe_package};
use gb_bootstrap::candidate_recipe::build_r3_recipe_package;
use gb_bootstrap::recipe::{RecipeValue, decode_recipe_package};
use gb_bootstrap::recipe_wire_v1::{
    decode_recipe_package_v1, encode_recipe_package_v1, evaluate_recipe_v1,
    evaluate_serialized_recipe_v1, expand_recipe_package_v1,
};
use sha2::{Digest, Sha256};

fn u16_at(raw: &[u8], offset: usize) -> usize {
    u16::from_be_bytes(raw[offset..offset + 2].try_into().unwrap()) as usize
}

fn u32_at(raw: &[u8], offset: usize) -> usize {
    u32::from_be_bytes(raw[offset..offset + 4].try_into().unwrap()) as usize
}

fn records(raw: &[u8]) -> BTreeMap<u16, &[u8]> {
    let mut cursor = 64;
    for _ in 0..u16_at(raw, 18) {
        cursor += 16 + u32_at(raw, cursor + 12);
    }
    let mut result = BTreeMap::new();
    for _ in 0..u16_at(raw, 16) {
        let end = cursor + u32_at(raw, cursor + 28);
        result.insert(u16_at(raw, cursor) as u16, &raw[cursor..end]);
        cursor = end;
    }
    assert_eq!(cursor, raw.len());
    result
}

fn small_input(body: &[u8], length: u16) -> Vec<u8> {
    assert!(body.len() <= 9);
    let mut input = vec![0; 9];
    input[..body.len()].copy_from_slice(body);
    input.extend_from_slice(&length.to_be_bytes());
    input
}

#[test]
fn independent_program_sizes_resources_and_historical_bytes_are_preserved() {
    let standalone = build_body_recipe_package().unwrap();
    assert_eq!(standalone.len(), 13_101);
    let compact = encode_recipe_package_v1(&standalone, 7).unwrap();
    assert_eq!(compact.len(), 5_457);
    let logical = decode_recipe_package(&standalone, 7).unwrap();
    let frames = records(&standalone);
    let compact_frames = records(&compact);
    for (id, nodes, expanded_bytes, compact_bytes, steps, scratch) in [
        (201, 145, 4720, 1774, 145, 65604),
        (202, 96, 3164, 1218, 2375776, 98394),
        (203, 133, 4336, 1584, 1293, 98398),
    ] {
        assert_eq!(u32_at(frames[&id], 8), nodes);
        assert_eq!(frames[&id].len(), expanded_bytes);
        assert_eq!(compact_frames[&id].len(), compact_bytes);
        assert_eq!(logical.recipe_primitive_steps(id), Some(steps));
        assert_eq!(logical.recipe_peak_scratch_bytes(id), Some(scratch));
    }
    let old = build_r3_recipe_package().unwrap();
    assert_eq!(
        format!("{:x}", Sha256::digest(&old)),
        "4bd8e0d485ae6e6a65f4edc4ef2aaac9585a2bcd8c4623e44d69f1dad3b0ec8e"
    );
    let combined = build_revision_recipe_package().unwrap();
    assert_eq!(combined.len(), 16_240);
    assert_eq!(u16_at(&combined, 12), 8);
    assert_eq!(u32_at(&combined, 20), 1073);
    assert_eq!(u32_at(&combined, 24), 1714);
    assert_eq!(
        u64::from_be_bytes(combined[36..44].try_into().unwrap()),
        2375776
    );
    assert_eq!(u32_at(&combined, 44), 98398);
    assert!(decode_recipe_package(&combined, 8).is_err());
    assert!(decode_recipe_package_v1(&combined, 7).is_err());
    let expanded = expand_recipe_package_v1(&combined, 8).unwrap();
    assert!(decode_recipe_package(&expanded, 8).is_err());
    let combined_frames = records(&expanded);
    for (id, old_frame) in records(&old) {
        if id == 109 {
            let mut expected = old_frame.to_vec();
            let start = 32 + 12 * (u16_at(&expected, 4) + u16_at(&expected, 6));
            let mut replacements = 0;
            for node in expected[start..].chunks_exact_mut(32) {
                if node[2] == 1
                    && u32_at(node, 4) == 32
                    && u64::from_be_bytes(node[24..32].try_into().unwrap()) == 7 * 40503
                {
                    node[24..32].copy_from_slice(&(8u64 * 40503).to_be_bytes());
                    replacements += 1;
                }
            }
            assert_eq!(replacements, 1);
            assert_eq!(combined_frames[&id], expected);
        } else {
            assert_eq!(combined_frames[&id], old_frame, "retained recipe {id}");
        }
    }
    let mut changed = combined.clone();
    changed.fill(0);
    assert_eq!(build_revision_recipe_package().unwrap(), combined);
}

#[test]
fn small_carried_constructions_use_the_generic_vm_and_ignore_unused_padding() {
    let bytes = build_revision_recipe_package().unwrap();
    let package = decode_recipe_package_v1(&bytes, 8).unwrap();
    for (body, length, expected) in [
        (&b"\x0012345678"[..], 9, &b"12345678"[..]),
        (&b"\x40A\x00\x04"[..], 4, &b"AAAAAAAA"[..]),
        (
            &b"\x40A\x00\x04\xff\x81\x03\xab\xc7"[..],
            4,
            &b"AAAAAAAA"[..],
        ),
    ] {
        let output =
            evaluate_serialized_recipe_v1(&package, 203, &small_input(body, length)).unwrap();
        assert_eq!(&output[..2], &[0, 0]);
        assert_eq!(&output[2..], expected);
    }
    assert_eq!(
        evaluate_serialized_recipe_v1(&package, 107, b"123456789").unwrap(),
        [0, 0, 0xe3, 0x06, 0x92, 0x83]
    );
    assert_eq!(
        evaluate_serialized_recipe_v1(&package, 111, b"123456789").unwrap(),
        [0, 0, 0xe3, 0x06, 0x92, 0x83]
    );
}

#[test]
fn malformed_tokens_fail_atomically_and_interfaces_do_not_coerce_types() {
    let raw = build_revision_recipe_package().unwrap();
    let package = decode_recipe_package_v1(&raw, 8).unwrap();
    for (body, length) in [
        (&b"\x41A\x00\x04"[..], 4), // unused flags
        (&b"\x40A\x00\x04"[..], 5), // trailing input
        (&b"\x80\x00\x05"[..], 3),  // copy before output
        (&b"\x40A\x00\x05"[..], 4), // copy runs past declared output
        (&b"\x40A\x00\x04"[..], 3), // truncated copy
        (&b"\x00"[..], 1),          // truncated literal
        (&b""[..], 0),
        (&b"\x0012345678"[..], 10),
        (&b"\x0012345678"[..], 65535),
    ] {
        assert_eq!(
            evaluate_serialized_recipe_v1(&package, 203, &small_input(body, length)).unwrap(),
            [0, 3]
        );
    }
    for input in [vec![0; 10], vec![0; 12]] {
        assert!(evaluate_serialized_recipe_v1(&package, 203, &input).is_err());
    }
    assert!(
        evaluate_recipe_v1(
            &package,
            203,
            &[
                RecipeValue::Bytes(vec![0; 9]),
                RecipeValue::Uint { width: 8, value: 4 },
            ]
        )
        .is_err()
    );
    assert!(
        evaluate_recipe_v1(
            &package,
            203,
            &[
                RecipeValue::Bits {
                    width: 72,
                    packed: vec![0; 9]
                },
                RecipeValue::Uint {
                    width: 16,
                    value: 4
                },
            ]
        )
        .is_err()
    );
}

#[test]
fn full_entry_ignores_input_padding_and_zero_fills_output() {
    let package = decode_recipe_package_v1(&build_revision_recipe_package().unwrap(), 8).unwrap();
    let encoded = [3, 0, 8, 0x40, b'A', 0, 4];
    let mut input = vec![0xa5; 16_384];
    input[..encoded.len()].copy_from_slice(&encoded);
    input.extend_from_slice(&(encoded.len() as u16).to_be_bytes());
    let output = evaluate_serialized_recipe_v1(&package, 202, &input).unwrap();
    assert_eq!(&output[..4], &[0, 0, 0, 8]);
    assert_eq!(&output[4..12], b"AAAAAAAA");
    assert_eq!(output.len(), 16_388);
    assert!(output[12..].iter().all(|byte| *byte == 0));
    for (header, length) in [
        ([2, 0, 8], 7u16),
        ([3, 64, 1], 7),
        ([3, 0, 8], 2),
        ([3, 0, 8], 16385),
    ] {
        input[..3].copy_from_slice(&header);
        input[16384..].copy_from_slice(&length.to_be_bytes());
        assert_eq!(
            evaluate_serialized_recipe_v1(&package, 202, &input).unwrap(),
            [0, 3]
        );
    }
}

#[test]
#[ignore = "opt-in full 16 KiB generic-VM state-copy stress"]
fn full_size_generic_decoder_matches_the_independent_host_codec() {
    let package = decode_recipe_package_v1(&build_revision_recipe_package().unwrap(), 8).unwrap();
    let raw: Vec<u8> = (0..16_384)
        .map(|i| ((i * 73 + i / 257) & 255) as u8)
        .collect();
    let encoded = encode_lzss(&raw).unwrap();
    assert!(encoded.len() <= 16384);
    assert_eq!(decode_lzss(&encoded).unwrap(), raw);
    let mut input = vec![0; 16384];
    input[..encoded.len()].copy_from_slice(&encoded);
    input.extend_from_slice(&(encoded.len() as u16).to_be_bytes());
    let output = evaluate_serialized_recipe_v1(&package, 202, &input).unwrap();
    assert_eq!(&output[..4], &[0, 0, 64, 0]);
    assert_eq!(&output[4..], raw);
}
