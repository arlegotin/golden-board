use std::collections::BTreeMap;
use std::path::Path;
use std::process::Command;

use gb_bootstrap::candidate::{
    CandidateProfile, CodecError, DecodeQuality, EhErasure, EhObservation, FragmentState,
    HierarchicalGroupState, HierarchicalLaneState, HierarchicalRepetitionState, PROFILES,
    RS_GENERATOR, RS_STATUS_ALGEBRA_BOUNDARY, RS_STATUS_PARAMETER, RS_STATUS_SUCCESS,
    TransportFamily, UnitRecovery, aggregate_repetition_observation, decode_clean_rs_unit,
    decode_eh_unit, decode_eh72, decode_rs_unit, decode_rs255_191, derive_rs_generator,
    diagnose_hierarchical_eh_group, encode_eh_unit, encode_eh72, encode_rs255_191, gf256_alpha_pow,
    gf256_mul, profile_by_id, profile_by_version, recover_eh_copies, recover_hierarchical_eh_group,
    rs_syndromes, verify_rs255_191,
};
use gb_bootstrap::candidate_recipe::{
    build_eh_recipe_package, build_r3_recipe_package, build_rs_decoder_recipe_package,
    build_rs_recipe_primitives, evaluate_eh_decoder_recipe, evaluate_rs_decoder_recipe,
    evaluate_rs_recipe_body, evaluate_transport_encoder_recipe, r3_recipe_package_metrics,
    r3_recipe_resource_rows, r3_slot_multiplier_table,
};
use gb_bootstrap::recipe::{RecipeValue, decode_recipe_package, evaluate_recipe};
use gb_bootstrap::{CommonBlock, SECTION_CONTENT_BODY, encode_common_block};
use gb_foundation::{ManifestValue, validate_canonical_manifest};
use sha2::{Digest, Sha256};

fn object(value: &ManifestValue) -> &BTreeMap<String, ManifestValue> {
    let ManifestValue::Object(value) = value else {
        panic!("object")
    };
    value
}

fn array(value: &ManifestValue) -> &[ManifestValue] {
    let ManifestValue::Array(value) = value else {
        panic!("array")
    };
    value
}

fn text(value: &ManifestValue) -> &str {
    let ManifestValue::String(value) = value else {
        panic!("string")
    };
    value
}

fn unsigned(value: &ManifestValue) -> u64 {
    let ManifestValue::U64(value) = value else {
        panic!("u64")
    };
    *value
}

fn hex(raw: &str) -> Vec<u8> {
    let compact = raw.split_ascii_whitespace().collect::<String>();
    compact
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            u8::from_str_radix(std::str::from_utf8(pair).expect("ASCII hex"), 16)
                .expect("literal hex")
        })
        .collect()
}

fn flip_position(raw: &mut [u8; 9], position: usize) {
    let index = position - 1;
    raw[index / 8] ^= 1 << (7 - index % 8);
}

fn common(profile_version: u16, payload_byte: u8) -> [u8; 191] {
    encode_common_block(&CommonBlock {
        profile_version,
        section_id: 9,
        semantic_copy_id: 0,
        section_type: SECTION_CONTENT_BODY,
        section_version: 0,
        fragment_index: 0,
        fragment_count: 1,
        section_envelope_length: 157,
        payload: vec![payload_byte; 157],
    })
    .unwrap()
}

#[test]
fn exactly_seven_profile_tuples_are_closed() {
    assert_eq!(PROFILES.len(), 7);
    assert_eq!(
        PROFILES.map(|profile| (
            profile.id,
            profile.version,
            profile.transport,
            profile.section_check_id,
            profile.required_copy_count,
        )),
        [
            (
                "eh72-r2-crc32c-v0",
                1,
                TransportFamily::Eh72Replicated,
                1,
                2
            ),
            (
                "eh72-r2-crc64-ecma-v0",
                2,
                TransportFamily::Eh72Replicated,
                2,
                2
            ),
            (
                "eh72-r3-crc32c-v0",
                3,
                TransportFamily::Eh72Replicated,
                1,
                3
            ),
            (
                "eh72-r3-crc64-ecma-v0",
                4,
                TransportFamily::Eh72Replicated,
                2,
                3
            ),
            ("rs255-191-crc32c-v0", 5, TransportFamily::Rs255_191, 1, 2),
            (
                "rs255-191-crc64-ecma-v0",
                6,
                TransportFamily::Rs255_191,
                2,
                2
            ),
            (
                "eh72-hier-r5-r2-r1-crc32c-v0",
                7,
                TransportFamily::Eh72HierarchicalRepetition,
                1,
                1
            ),
        ]
    );
    for profile in PROFILES {
        assert_eq!(profile_by_version(profile.version), Some(profile));
        assert_eq!(profile_by_id(profile.id), Some(profile));
    }
    assert_eq!(profile_by_version(0), None);
    assert_eq!(profile_by_version(7), Some(PROFILES[6]));
    assert_eq!(profile_by_version(8), None);
    assert_eq!(profile_by_id("rs255-223-v0"), None);
}

#[test]
fn four_literal_eh72_encodings_are_exact() {
    for (data, encoded) in [
        ("0000000000000000", "000000000000000000"),
        ("8000000000000000", "e00000000000000001"),
        ("0123456789abcdef", "11121a2a9e26af36de"),
        ("ffffffffffffffff", "ffffffffffffffffff"),
    ] {
        let data: [u8; 8] = hex(data).try_into().unwrap();
        let expected: [u8; 9] = hex(encoded).try_into().unwrap();
        assert_eq!(encode_eh72(&data), expected);
        let decoded = decode_eh72(&expected, &[]).unwrap();
        assert_eq!(decoded.data, data);
        assert_eq!(decoded.quality, DecodeQuality::Verified);
        assert_eq!(decoded.constructions, 73);
    }
}

#[test]
fn eh72_single_changes_erasures_and_mixed_boundary_are_bounded() {
    let data: [u8; 8] = hex("0123456789abcdef").try_into().unwrap();
    let encoded = encode_eh72(&data);
    for position in 1..=72 {
        let mut changed = encoded;
        flip_position(&mut changed, position);
        let decoded = decode_eh72(&changed, &[]).unwrap();
        assert_eq!(decoded.data, data, "changed position {position}");
        assert_eq!(decoded.quality, DecodeQuality::Recovered);
        assert_eq!(decoded.constructions, 73);

        let mut observed = encoded;
        flip_position(&mut observed, position);
        let decoded = decode_eh72(&observed, &[position as u8]).unwrap();
        assert_eq!(decoded.data, data, "erased position {position}");
        assert_eq!(decoded.quality, DecodeQuality::Recovered);
        assert_eq!(decoded.constructions, 144);
    }

    let mut mixed = encoded;
    flip_position(&mut mixed, 5);
    flip_position(&mut mixed, 72);
    assert_eq!(decode_eh72(&mixed, &[5]).unwrap().data, data);
    assert_eq!(decode_eh72(&mixed, &[5]).unwrap().constructions, 144);
    assert_eq!(decode_eh72(&encoded, &[1, 2]).unwrap().constructions, 4);
    assert_eq!(decode_eh72(&encoded, &[1, 2, 3]).unwrap().constructions, 8);

    let mut beyond = encoded;
    flip_position(&mut beyond, 5);
    flip_position(&mut beyond, 6);
    assert_eq!(decode_eh72(&beyond, &[]), Err(CodecError::Corrupt));
    assert_eq!(
        decode_eh72(&encoded, &[1, 2, 3, 4]),
        Err(CodecError::Erasure)
    );
    assert_eq!(decode_eh72(&encoded, &[1, 1]), Err(CodecError::Erasure));
    assert_eq!(decode_eh72(&encoded, &[0]), Err(CodecError::Erasure));
    assert_eq!(decode_eh72(&encoded, &[73]), Err(CodecError::Erasure));
}

#[test]
fn eh_units_require_all_codewords_zero_pad_and_local_check() {
    let common = common(1, 0x42);
    let encoded = encode_eh_unit(&common);
    let clean = EhObservation {
        encoded,
        erasures: Vec::new(),
    };
    assert_eq!(
        decode_eh_unit(&clean, 1).unwrap().quality,
        DecodeQuality::Verified
    );

    let mut changed = clean.clone();
    changed.encoded[0] ^= 0x80;
    assert_eq!(decode_eh_unit(&changed, 1).unwrap().common, common);
    assert_eq!(
        decode_eh_unit(&changed, 1).unwrap().quality,
        DecodeQuality::Recovered
    );

    let erased = EhObservation {
        encoded,
        erasures: vec![EhErasure {
            codeword: 0,
            position: 1,
        }],
    };
    assert_eq!(decode_eh_unit(&erased, 1).unwrap().common, common);

    let mut bad_pad_plain = [0_u8; 192];
    bad_pad_plain[..191].copy_from_slice(&common);
    bad_pad_plain[191] = 1;
    let mut bad_pad = encoded;
    bad_pad[23 * 9..].copy_from_slice(&encode_eh72(&bad_pad_plain[23 * 8..].try_into().unwrap()));
    assert_eq!(
        decode_eh_unit(
            &EhObservation {
                encoded: bad_pad,
                erasures: vec![],
            },
            1,
        ),
        Err(CodecError::Corrupt)
    );

    let mut bad_local = common;
    bad_local[40] ^= 1;
    assert_eq!(
        decode_eh_unit(
            &EhObservation {
                encoded: encode_eh_unit(&bad_local),
                erasures: vec![],
            },
            1,
        ),
        Err(CodecError::LocalCheck)
    );
}

#[test]
fn replicated_eh_copies_deduplicate_recover_and_never_vote() {
    let profile = profile_by_version(1).unwrap();
    let first = common(1, 0x11);
    let second = common(1, 0x22);
    let clean_first = EhObservation {
        encoded: encode_eh_unit(&first),
        erasures: vec![],
    };
    let clean_second = EhObservation {
        encoded: encode_eh_unit(&second),
        erasures: vec![],
    };
    let mut recovered_first = clean_first.clone();
    recovered_first.encoded[7] ^= 1;

    let mut corrupt_first = clean_first.clone();
    for position in [0, 9, 18, 27] {
        corrupt_first.encoded[position / 8] ^= 1 << (7 - position % 8);
    }
    let expected_valid = UnitRecovery {
        state: FragmentState::Verified,
        common: Some(first),
    };
    assert_eq!(
        recover_eh_copies(
            profile,
            &[Some(corrupt_first.clone()), Some(clean_first.clone())]
        )
        .unwrap(),
        expected_valid
    );
    assert_eq!(
        recover_eh_copies(profile, &[Some(clean_first.clone()), Some(corrupt_first)]).unwrap(),
        expected_valid
    );

    let recovered = recover_eh_copies(profile, &[Some(recovered_first), None]).unwrap();
    assert_eq!(recovered.state, FragmentState::Recovered);
    assert_eq!(recovered.common, Some(first));
    assert_eq!(
        recover_eh_copies(profile, &[Some(clean_first.clone()), None])
            .unwrap()
            .state,
        FragmentState::Verified
    );
    assert_eq!(
        recover_eh_copies(profile, &[None, None]).unwrap().state,
        FragmentState::Missing
    );
    assert_eq!(
        recover_eh_copies(profile, &[Some(clean_first), Some(clean_second)])
            .unwrap()
            .state,
        FragmentState::Ambiguous
    );
    assert_eq!(
        recover_eh_copies(profile, &[None]),
        Err(CodecError::Parameter)
    );
    let rs_profile = profile_by_version(5).unwrap();
    assert_eq!(
        recover_eh_copies(rs_profile, &[None, None]),
        Err(CodecError::Parameter)
    );
}

#[test]
fn hierarchical_repetition_boundaries_and_valid_conflicts_fail_closed() {
    let profile = profile_by_version(7).unwrap();
    let first = common(7, 0x11);
    let second = common(7, 0x22);
    let clean_first = EhObservation {
        encoded: encode_eh_unit(&first),
        erasures: vec![],
    };
    let clean_second = EhObservation {
        encoded: encode_eh_unit(&second),
        erasures: vec![],
    };

    for factor in [1_usize, 2, 5] {
        let observations = vec![Some(clean_first.clone()); factor];
        assert_eq!(
            recover_hierarchical_eh_group(profile, &observations).unwrap(),
            UnitRecovery {
                state: FragmentState::Verified,
                common: Some(first),
            }
        );
    }
    assert_eq!(
        recover_hierarchical_eh_group(profile, &[None, None, None, None, None]).unwrap(),
        UnitRecovery {
            state: FragmentState::Missing,
            common: None,
        }
    );
    assert_eq!(
        recover_hierarchical_eh_group(
            profile,
            &[Some(clean_first.clone()), None, None, None, None]
        )
        .unwrap(),
        UnitRecovery {
            state: FragmentState::Verified,
            common: Some(first),
        }
    );

    let diagnostic = diagnose_hierarchical_eh_group(
        profile,
        &[
            Some(clean_first.clone()),
            Some(clean_first.clone()),
            Some(clean_first.clone()),
            Some(clean_first.clone()),
            Some(clean_second.clone()),
        ],
    )
    .unwrap();
    assert_eq!(diagnostic.state, HierarchicalGroupState::Conflict);
    assert_eq!(diagnostic.distinct_candidate_count, 2);
    assert_eq!(diagnostic.eh_codeword_invocations, 144);
    assert_eq!(diagnostic.repetition_symbol_invocations, 1_728);
    assert!(diagnostic.common.is_none());
    assert_eq!(
        diagnostic.repetition_state,
        HierarchicalRepetitionState::Recovered
    );
    assert_eq!(
        diagnostic
            .lanes
            .iter()
            .map(|lane| lane.state)
            .collect::<Vec<_>>(),
        vec![HierarchicalLaneState::Verified; 5]
    );

    let mut recovered = clean_first.clone();
    recovered.encoded[0] ^= 0x80;
    assert_eq!(
        recover_hierarchical_eh_group(profile, &[Some(recovered), None, None, None, None]).unwrap(),
        UnitRecovery {
            state: FragmentState::Recovered,
            common: Some(first),
        }
    );

    // A valid minority is still a conflict; repetition is never a semantic vote.
    assert_eq!(
        recover_hierarchical_eh_group(
            profile,
            &[
                Some(clean_first.clone()),
                Some(clean_first.clone()),
                Some(clean_first.clone()),
                Some(clean_first.clone()),
                Some(clean_second.clone()),
            ]
        )
        .unwrap(),
        UnitRecovery {
            state: FragmentState::Ambiguous,
            common: None,
        }
    );

    let mut zero = EhObservation {
        encoded: [0; 216],
        erasures: vec![],
    };
    let mut one = zero.clone();
    one.encoded[0] = 0x80;
    let rep2_at_r_minus_one = aggregate_repetition_observation(&[Some(zero.clone()), None])
        .unwrap()
        .unwrap();
    assert_eq!(rep2_at_r_minus_one.encoded[0] & 0x80, 0);
    assert!(rep2_at_r_minus_one.erasures.is_empty());
    let rep2_at_r = aggregate_repetition_observation(&[Some(zero.clone()), Some(one.clone())])
        .unwrap()
        .unwrap();
    assert_eq!(
        rep2_at_r.erasures[0],
        EhErasure {
            codeword: 0,
            position: 1
        }
    );

    let at_r_minus_one = aggregate_repetition_observation(&[
        Some(zero.clone()),
        Some(zero.clone()),
        Some(zero),
        Some(one.clone()),
        Some(one.clone()),
    ])
    .unwrap()
    .unwrap();
    assert_eq!(at_r_minus_one.encoded[0] & 0x80, 0);
    assert!(at_r_minus_one.erasures.is_empty());

    zero = EhObservation {
        encoded: [0; 216],
        erasures: vec![],
    };
    let at_r = aggregate_repetition_observation(&[
        Some(zero.clone()),
        Some(zero),
        Some(one.clone()),
        Some(one),
        None,
    ])
    .unwrap()
    .unwrap();
    assert_eq!(
        at_r.erasures[0],
        EhErasure {
            codeword: 0,
            position: 1
        }
    );
}

#[test]
fn rs_field_generator_and_two_full_parity_kats_are_exact() {
    assert_eq!(gf256_mul(0x53, gf256_alpha_pow(254)), 0xa7);
    assert_eq!(derive_rs_generator(), RS_GENERATOR);

    let mut final_one = [0_u8; 191];
    final_one[190] = 1;
    let encoded = encode_rs255_191(&final_one);
    assert_eq!(
        encoded[191..],
        hex("c1 0a ff 3a 80 b7 73 8c 99 93 5b c5 db dd dc 8e
             1c 78 15 a4 93 06 cc 28 e6 b6 0e 79 30 8f 4d e4
             51 55 2b a2 10 c3 a3 23 95 9a 23 84 64 64 33 b0
             0b a1 86 d0 84 f4 b0 c0 dd e8 ab 7d 9b e4 f2 f5")
    );
    assert!(verify_rs255_191(&encoded));

    let sequence = std::array::from_fn(|index| index as u8);
    let encoded = encode_rs255_191(&sequence);
    assert_eq!(
        encoded[191..],
        hex("8c 1b e6 94 d0 57 75 7c 84 ad 11 47 37 f1 17 51
             d3 d4 33 c6 e3 3e 53 6f f7 bb c6 d1 36 ae 4b d0
             15 62 6f bc 94 c5 2c c5 ab eb e5 3f dc f0 a2 4e
             22 fa 23 87 d8 74 49 c7 be d4 ce eb 9c 94 c6 f9")
    );
    assert!(verify_rs255_191(&encoded));

    let zero = encode_rs255_191(&[0_u8; 191]);
    assert_eq!(zero, [0_u8; 255]);
}

#[test]
fn rs_syndrome_order_detects_boundary_errors_and_clean_units() {
    let sequence = std::array::from_fn(|index| index as u8);
    let encoded = encode_rs255_191(&sequence);
    let mut first = encoded;
    first[0] ^= 0x53;
    let syndromes = rs_syndromes(&first);
    assert_eq!((syndromes[0], syndromes[1]), (0x53, 0xa7));
    let mut last = encoded;
    last[254] ^= 0x53;
    assert_eq!(rs_syndromes(&last), [0x53; 64]);

    let expected_common = common(5, 0x5a);
    let encoded = encode_rs255_191(&expected_common);
    assert_eq!(
        decode_clean_rs_unit(&encoded, 5).unwrap().common,
        expected_common
    );
    assert_eq!(
        decode_clean_rs_unit(&encoded, 5).unwrap().quality,
        DecodeQuality::Verified
    );
    assert_eq!(
        decode_clean_rs_unit(&encoded, 6),
        Err(CodecError::LocalCheck)
    );
    let mut damaged = encoded;
    damaged[254] ^= 1;
    assert_eq!(decode_clean_rs_unit(&damaged, 5), Err(CodecError::Corrupt));
}

#[test]
fn named_rs_convention_mutants_do_not_match_frozen_parity() {
    fn mutant_mul(mut left: u8, mut right: u8) -> u8 {
        let mut result = 0;
        for _ in 0..8 {
            if right & 1 != 0 {
                result ^= left;
            }
            right >>= 1;
            let carry = left & 0x80 != 0;
            left <<= 1;
            if carry {
                left ^= 0x1b; // AES 0x11b mutant.
            }
        }
        result
    }

    let mut wrong_modulus = [0_u8; 65];
    wrong_modulus[0] = 1;
    let mut length = 1;
    let mut root = 1;
    for _ in 0..64 {
        let old = wrong_modulus;
        wrong_modulus = [0; 65];
        for index in 0..length {
            wrong_modulus[index] ^= old[index];
            wrong_modulus[index + 1] ^= mutant_mul(old[index], root);
        }
        root = mutant_mul(root, 2);
        length += 1;
    }
    assert_ne!(wrong_modulus, RS_GENERATOR, "modulus-0x11b mutant");

    let mut roots_from_one = vec![1_u8];
    for exponent in 1..=64 {
        let root = gf256_alpha_pow(exponent);
        let mut next = vec![0; roots_from_one.len() + 1];
        for (index, coefficient) in roots_from_one.iter().copied().enumerate() {
            next[index] ^= coefficient;
            next[index + 1] ^= gf256_mul(coefficient, root);
        }
        roots_from_one = next;
    }
    assert_ne!(
        roots_from_one.as_slice(),
        RS_GENERATOR,
        "first-root-one mutant"
    );

    let data = std::array::from_fn(|index| index as u8);
    let encoded = encode_rs255_191(&data);
    let mut reversed = data;
    reversed.reverse();
    assert_ne!(encode_rs255_191(&reversed)[191..], encoded[191..]);
}

#[test]
fn profile_struct_cannot_smuggle_a_seventh_tuple_into_copy_recovery() {
    let fake = CandidateProfile {
        id: "eh72-r4-crc32c-v0",
        version: 7,
        transport: TransportFamily::Eh72Replicated,
        section_check_id: 1,
        required_copy_count: 4,
    };
    assert_eq!(
        recover_eh_copies(fake, &[None, None, None, None]),
        Err(CodecError::Parameter)
    );
}

#[test]
fn shared_rs_corpus_matches_exact_decoder_intermediates_and_failures() {
    let manifest =
        validate_canonical_manifest(include_bytes!("../../../conformance/rs255-191-v0.json"))
            .unwrap();
    let root = object(&manifest);
    assert_eq!(
        root.keys().map(String::as_str).collect::<Vec<_>>(),
        [
            "decode_kats",
            "encode_kats",
            "field_inverse_kats",
            "field_multiplication_kats",
            "generator_coefficients_hex",
            "generator_sha256",
            "intermediate_kat",
            "mutant_ids",
            "profile_id",
            "schema",
        ]
    );
    assert_eq!(
        text(&root["schema"]),
        "golden-board.rs255-191-v0-fixtures/v0"
    );
    assert_eq!(text(&root["profile_id"]), "rs255-191-v0");
    assert_eq!(hex(text(&root["generator_coefficients_hex"])), RS_GENERATOR);

    let mut codewords = BTreeMap::<String, [u8; 255]>::new();
    for value in array(&root["encode_kats"]) {
        let row = object(value);
        let data: [u8; 191] = hex(text(&row["data_hex"])).try_into().unwrap();
        let expected: [u8; 255] = hex(text(&row["codeword_hex"])).try_into().unwrap();
        assert_eq!(encode_rs255_191(&data), expected, "{}", text(&row["id"]));
        codewords.insert(text(&row["id"]).to_owned(), expected);
    }

    for value in array(&root["decode_kats"]) {
        let row = object(value);
        let observation = hex(text(&row["observation_hex"]));
        let erasures = array(&row["erasure_positions"])
            .iter()
            .map(|value| u16::try_from(unsigned(value)).unwrap())
            .collect::<Vec<_>>();
        let expected_status = u16::try_from(unsigned(&row["expected_status"])).unwrap();
        let outcome = decode_rs255_191(&observation, &erasures);
        assert_eq!(outcome.status, expected_status, "{}", text(&row["id"]));
        if expected_status == RS_STATUS_SUCCESS {
            assert_eq!(
                outcome.codeword,
                Some(codewords[text(&row["expected_codeword_id"])]),
                "{}",
                text(&row["id"])
            );
            let trace = outcome.trace.expect("successful trace");
            assert_eq!(
                trace.correction_positions,
                array(&row["expected_correction_positions"])
                    .iter()
                    .map(|value| u16::try_from(unsigned(value)).unwrap())
                    .collect::<Vec<_>>(),
                "{}",
                text(&row["id"])
            );
            assert_eq!(
                trace.correction_magnitudes,
                array(&row["expected_correction_magnitudes"])
                    .iter()
                    .map(|value| u8::try_from(unsigned(value)).unwrap())
                    .collect::<Vec<_>>(),
                "{}",
                text(&row["id"])
            );
            assert!(trace.field_multiplications <= 80_000);
            assert!(trace.field_inversions <= 128);
            assert!(trace.primitive_steps <= 1_000_000);
        } else {
            assert_eq!(outcome.codeword, None, "{}", text(&row["id"]));
            assert_eq!(outcome.trace, None, "{}", text(&row["id"]));
            assert_eq!(outcome.quality, None, "{}", text(&row["id"]));
        }
    }

    let row = object(&root["intermediate_kat"]);
    let observation = hex(text(&row["observation_hex"]));
    let erasures = array(&row["erasure_positions"])
        .iter()
        .map(|value| u16::try_from(unsigned(value)).unwrap())
        .collect::<Vec<_>>();
    let outcome = decode_rs255_191(&observation, &erasures);
    assert_eq!(outcome.status, RS_STATUS_SUCCESS);
    assert_eq!(outcome.codeword, Some(codewords[text(&row["codeword_id"])]));
    let trace = outcome.trace.unwrap();
    assert_eq!(trace.syndromes.as_slice(), hex(text(&row["syndromes_hex"])));
    assert_eq!(
        trace.erasure_locator,
        hex(text(&row["erasure_locator_ascending_hex"]))
    );
    assert_eq!(
        trace.transformed_syndromes.as_slice(),
        hex(text(&row["transformed_syndromes_hex"]))
    );
    assert_eq!(trace.bm_input, hex(text(&row["bm_input_hex"])));
    assert_eq!(
        trace.unknown_error_locator,
        hex(text(&row["unknown_error_locator_ascending_hex"]))
    );
    assert_eq!(
        trace.full_locator,
        hex(text(&row["full_locator_ascending_hex"]))
    );
    assert_eq!(
        trace.evaluator.as_slice(),
        hex(text(&row["evaluator_ascending_padded_hex"]))
    );
    assert_eq!(
        trace.correction_positions,
        array(&row["correction_positions"])
            .iter()
            .map(|value| u16::try_from(unsigned(value)).unwrap())
            .collect::<Vec<_>>()
    );
    assert_eq!(
        trace.correction_magnitudes,
        array(&row["correction_magnitudes"])
            .iter()
            .map(|value| u8::try_from(unsigned(value)).unwrap())
            .collect::<Vec<_>>()
    );

    let clean = codewords["ascending-00-through-be"];
    for (observation, erasures, status) in [
        (&clean[..254], &[][..], RS_STATUS_PARAMETER),
        (&clean[..], &[1, 1][..], RS_STATUS_PARAMETER),
        (&clean[..], &[2, 1][..], RS_STATUS_PARAMETER),
        (&clean[..], &[255][..], RS_STATUS_PARAMETER),
        (
            &clean[..],
            &(0_u16..65).collect::<Vec<_>>()[..],
            RS_STATUS_ALGEBRA_BOUNDARY,
        ),
    ] {
        let outcome = decode_rs255_191(observation, erasures);
        assert_eq!(outcome.status, status);
        assert_eq!(outcome.codeword, None);
        assert_eq!(outcome.trace, None);
    }
}

#[test]
fn rs_unit_correction_is_profile_closed_and_local_check_is_last() {
    let expected_common = common(5, 0x5a);
    let encoded = encode_rs255_191(&expected_common);
    assert_eq!(
        decode_rs_unit(&encoded, &[], 5).unwrap(),
        gb_bootstrap::candidate::DecodedUnit {
            common: expected_common,
            quality: DecodeQuality::Verified,
        }
    );
    let mut changed = encoded;
    changed[0] ^= 0x53;
    assert_eq!(
        decode_rs_unit(&changed, &[], 5).unwrap(),
        gb_bootstrap::candidate::DecodedUnit {
            common: expected_common,
            quality: DecodeQuality::Recovered,
        }
    );
    let mut erased = encoded;
    erased[190] = 0xa5;
    assert_eq!(
        decode_rs_unit(&erased, &[190], 5).unwrap().common,
        expected_common
    );
    assert_eq!(decode_rs_unit(&encoded, &[], 1), Err(RS_STATUS_PARAMETER));
    assert_eq!(decode_rs_unit(&encoded, &[], 7), Err(RS_STATUS_PARAMETER));

    let bad_local_common = common(5, 0x33);
    let mut bad_local = encode_rs255_191(&bad_local_common);
    bad_local[40] ^= 1;
    bad_local = encode_rs255_191(&bad_local[..191].try_into().unwrap());
    assert_eq!(
        decode_rs_unit(&bad_local, &[], 5),
        Err(gb_bootstrap::candidate::RS_STATUS_LOCAL_CHECK)
    );
}

#[test]
fn generic_recipe_field_primitives_are_closed_and_exact() {
    let raw = build_rs_recipe_primitives(5).unwrap();
    let package = decode_recipe_package(&raw, 5).unwrap();
    assert_eq!(package.recipe_ids().collect::<Vec<_>>(), [1, 2]);
    assert!(raw.len() < 4_096);

    let mut state = vec![0_u8; 1_536];
    state[1_463] = 0x53;
    state[1_464] = 0xca;
    let state = (0..8).fold(state, |state, _| {
        let outcome = evaluate_rs_recipe_body(&package, 1, state).unwrap();
        assert_eq!(outcome.status, 0);
        let RecipeValue::Bytes(state) = &outcome.outputs[0] else {
            panic!("state output")
        };
        state.clone()
    });
    assert_eq!(state[1_465], gf256_mul(0x53, 0xca));

    let mut state = vec![0_u8; 1_536];
    state[1_466] = 1;
    state[1_467] = 0x53;
    state[1_468] = 254;
    let state = (0..8).fold(state, |state, _| {
        let outcome = evaluate_rs_recipe_body(&package, 2, state).unwrap();
        let RecipeValue::Bytes(state) = &outcome.outputs[0] else {
            panic!("state output")
        };
        state.clone()
    });
    assert_eq!(gf256_mul(0x53, state[1_466]), 1);
}

#[test]
fn generic_eh_recipe_encoder_and_decoder_are_closed_and_exact() {
    let raw = build_eh_recipe_package(1).unwrap();
    let package = decode_recipe_package(&raw, 1).unwrap();
    assert_eq!(
        package.recipe_ids().collect::<Vec<_>>(),
        [
            1, 2, 3, 4, 30, 90, 92, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111,
            112,
        ]
    );
    assert_eq!(raw.len(), 24_786);
    assert_eq!(u32::from_be_bytes(raw[20..24].try_into().unwrap()), 675);
    assert_eq!(package.maximum_primitive_steps, 80_435);
    assert_eq!(package.peak_scratch_bytes, 6_163);
    assert_eq!(
        format!("{:x}", Sha256::digest(&raw)),
        "f030732cd966fd9570149f6fd2d1befb5eed66319eb248b609693e868f977941"
    );

    let check = |recipe_id, inputs: Vec<RecipeValue>, outputs: Vec<RecipeValue>| {
        let outcome = evaluate_recipe(&package, recipe_id, &inputs).unwrap();
        assert_eq!(outcome.status, 0, "recipe {recipe_id}");
        assert_eq!(outcome.outputs, outputs, "recipe {recipe_id}");
    };
    check(
        101,
        vec![RecipeValue::Bits {
            width: 8,
            packed: vec![0x0f],
        }],
        vec![RecipeValue::Bits {
            width: 8,
            packed: vec![0xf0],
        }],
    );
    check(
        102,
        vec![
            RecipeValue::Uint { width: 3, value: 3 },
            RecipeValue::Bool(true),
            RecipeValue::Uint {
                width: 16,
                value: 2,
            },
            RecipeValue::Uint {
                width: 16,
                value: 5,
            },
            RecipeValue::Uint {
                width: 16,
                value: 8,
            },
            RecipeValue::Bool(false),
        ],
        vec![
            RecipeValue::Uint {
                width: 32,
                value: 45,
            },
            RecipeValue::Bool(true),
        ],
    );
    check(
        102,
        vec![
            RecipeValue::Uint { width: 3, value: 5 },
            RecipeValue::Bool(false),
            RecipeValue::Uint {
                width: 16,
                value: 1,
            },
            RecipeValue::Uint {
                width: 16,
                value: 6,
            },
            RecipeValue::Uint {
                width: 16,
                value: 8,
            },
            RecipeValue::Bool(true),
        ],
        vec![
            RecipeValue::Uint {
                width: 32,
                value: 14,
            },
            RecipeValue::Bool(true),
        ],
    );
    check(
        103,
        vec![
            RecipeValue::Uint {
                width: 16,
                value: 1,
            },
            RecipeValue::Uint {
                width: 16,
                value: 2,
            },
        ],
        vec![RecipeValue::Bool(true)],
    );
    check(
        104,
        vec![
            RecipeValue::Uint {
                width: 16,
                value: 2,
            },
            RecipeValue::Uint {
                width: 16,
                value: 3,
            },
            RecipeValue::Uint {
                width: 16,
                value: 8,
            },
        ],
        vec![RecipeValue::Uint {
            width: 32,
            value: 19,
        }],
    );
    check(
        105,
        vec![RecipeValue::Uint {
            width: 32,
            value: 8,
        }],
        vec![RecipeValue::Uint {
            width: 32,
            value: 9,
        }],
    );
    check(
        106,
        vec![RecipeValue::Uint { width: 8, value: 0 }],
        vec![RecipeValue::Bool(true)],
    );
    check(
        107,
        vec![RecipeValue::Bytes(b"123456789".to_vec())],
        vec![RecipeValue::Uint {
            width: 32,
            value: 0xe306_9283,
        }],
    );
    check(
        109,
        vec![
            RecipeValue::Uint {
                width: 32,
                value: 0,
            },
            RecipeValue::Uint {
                width: 16,
                value: 2_048,
            },
            RecipeValue::Uint {
                width: 16,
                value: 128,
            },
        ],
        vec![RecipeValue::Uint {
            width: 32,
            value: 0x0001_1eb7,
        }],
    );
    check(
        110,
        vec![
            RecipeValue::Uint {
                width: 32,
                value: 1,
            },
            RecipeValue::Uint {
                width: 16,
                value: 0,
            },
        ],
        vec![RecipeValue::Uint {
            width: 48,
            value: 0x0000_0001_0000,
        }],
    );
    check(
        111,
        vec![RecipeValue::Bytes(b"123456789".to_vec())],
        vec![RecipeValue::Uint {
            width: 32,
            value: 0xe306_9283,
        }],
    );
    check(
        112,
        vec![
            RecipeValue::Uint {
                width: 16,
                value: 64,
            },
            RecipeValue::Uint {
                width: 16,
                value: 63,
            },
            RecipeValue::Bool(true),
        ],
        vec![RecipeValue::Bool(true)],
    );

    let source = 0x0123_4567_89ab_cdef_u64.to_be_bytes();
    let encoded = encode_eh72(&source);
    let outcome = evaluate_transport_encoder_recipe(&package, &source).unwrap();
    assert_eq!(outcome.status, 0);
    assert_eq!(outcome.outputs, vec![RecipeValue::Bytes(encoded.to_vec())]);

    let outcome = evaluate_eh_decoder_recipe(&package, &encoded, &[]).unwrap();
    assert_eq!(outcome.status, 0);
    assert_eq!(outcome.outputs, vec![RecipeValue::Bytes(source.to_vec())]);

    let mut changed = encoded;
    changed[0] ^= 0x80;
    let outcome = evaluate_eh_decoder_recipe(&package, &changed, &[]).unwrap();
    assert_eq!(outcome.status, 0);
    assert_eq!(outcome.outputs, vec![RecipeValue::Bytes(source.to_vec())]);

    let mut erased = encoded;
    erased[1] ^= 0x20;
    let outcome = evaluate_eh_decoder_recipe(&package, &erased, &[11]).unwrap();
    assert_eq!(outcome.status, 0);
    assert_eq!(outcome.outputs, vec![RecipeValue::Bytes(source.to_vec())]);

    // EH erasure bytes are the one-based positions frozen by m2-spec §9.2;
    // serialized damage bit indices remain zero-based.  This cyclic pairing
    // covers every erased position and every distinct known-error position,
    // with the erased bit itself flipped rather than treated as already zero.
    for erased_position in 1..=72 {
        let error_position = erased_position % 72 + 1;
        let mut mixed = encoded;
        flip_position(&mut mixed, erased_position);
        flip_position(&mut mixed, error_position);
        let outcome =
            evaluate_eh_decoder_recipe(&package, &mixed, &[erased_position as u8]).unwrap();
        assert_eq!(outcome.status, 0, "erasure {erased_position}");
        assert_eq!(
            outcome.outputs,
            vec![RecipeValue::Bytes(source.to_vec())],
            "erasure {erased_position}, error {error_position}"
        );
    }

    for erasures in [&[1_u8, 1][..], &[1_u8, 2, 3, 4][..]] {
        let outcome = evaluate_eh_decoder_recipe(&package, &encoded, erasures).unwrap();
        assert_eq!(outcome.status, 3);
        assert!(outcome.outputs.is_empty());
    }
}

#[test]
fn compact_r3_recipient_package_and_repetition_count_abi_are_exact() {
    let raw = build_r3_recipe_package().unwrap();
    assert_eq!(raw, build_eh_recipe_package(7).unwrap());
    let package = decode_recipe_package(&raw, 7).unwrap();
    assert_eq!(package.recipe_ids().last(), Some(113));
    let metrics = r3_recipe_package_metrics().unwrap();
    assert_eq!(metrics.package_bytes, 25_930);
    assert_eq!(
        metrics.package_sha256,
        "4bd8e0d485ae6e6a65f4edc4ef2aaac9585a2bcd8c4623e44d69f1dad3b0ec8e"
    );
    assert_eq!(metrics.node_count, 699);
    assert_eq!(metrics.edge_count, 1_087);
    assert_eq!(metrics.table_payload_bytes, 1_470);
    assert_eq!(metrics.maximum_primitive_steps, 80_435);
    assert_eq!(metrics.peak_scratch_bytes, 6_163);
    assert_eq!(metrics.repetition_recipe_bytes, 872);
    assert_eq!(metrics.repetition_recipe_nodes, 24);
    assert_eq!(metrics.repetition_primitive_steps, 24);
    assert_eq!(metrics.repetition_peak_scratch_bytes, 10);
    assert_eq!(metrics.route_worked_held_primitive_steps_per_sector, 15_134);
    assert_eq!(metrics.route_peak_scratch_bytes, 6_163);
    assert_eq!(metrics.projected_route_prefix_bytes_per_sector, 29_091);
    assert!(metrics.projected_route_prefix_bytes_per_sector <= 29_257);
    assert_eq!(
        format!("{:x}", Sha256::digest(r3_slot_multiplier_table())),
        "835717bf400c597a3a9e1b59747f23d93047b6cfab462756fa07d96c5f3eba3f"
    );
    assert_eq!(
        r3_recipe_resource_rows()
            .unwrap()
            .into_iter()
            .map(|row| (
                row.recipe_id,
                row.encoded_bytes,
                row.node_count,
                row.primitive_steps,
                row.peak_scratch_bytes,
            ))
            .collect::<Vec<_>>(),
        [
            (30, 1_404, 41, 80_435, 4_613),
            (109, 1_436, 42, 42, 24),
            (110, 208, 4, 4, 10),
            (113, 872, 24, 24, 10),
        ]
    );

    let evaluate = |factor, zeros, ones| {
        evaluate_recipe(
            &package,
            113,
            &[
                RecipeValue::Uint {
                    width: 8,
                    value: factor,
                },
                RecipeValue::Uint {
                    width: 8,
                    value: zeros,
                },
                RecipeValue::Uint {
                    width: 8,
                    value: ones,
                },
            ],
        )
        .unwrap()
    };
    for (factor, zeros, ones, known, bit) in [
        (2, 0, 0, false, false),
        (2, 1, 0, true, false),
        (2, 0, 1, true, true),
        (2, 1, 1, false, false),
        (5, 3, 2, true, false),
        (5, 2, 3, true, true),
        (5, 2, 2, false, false),
        (5, 0, 0, false, false),
    ] {
        let outcome = evaluate(factor, zeros, ones);
        assert_eq!(outcome.status, 0);
        assert_eq!(
            outcome.outputs,
            [RecipeValue::Bool(known), RecipeValue::Bool(bit)]
        );
    }
    for (factor, zeros, ones) in [(1, 1, 0), (2, 2, 1), (5, 255, 255)] {
        let outcome = evaluate(factor, zeros, ones);
        assert_eq!(outcome.status, 3);
        assert!(outcome.outputs.is_empty());
    }
}

#[test]
fn generic_eh_crc64_export_is_closed_and_exact() {
    let raw = build_eh_recipe_package(2).unwrap();
    let package = decode_recipe_package(&raw, 2).unwrap();
    assert_eq!(raw.len(), 26_738);
    assert_eq!(u32::from_be_bytes(raw[20..24].try_into().unwrap()), 736);
    assert_eq!(package.maximum_primitive_steps, 80_435);
    assert_eq!(package.peak_scratch_bytes, 6_175);
    assert_eq!(
        format!("{:x}", Sha256::digest(&raw)),
        "cce1758613d7f10278533409e07103ae15162972fcf30030e17c233e39664011"
    );
    let outcome =
        evaluate_recipe(&package, 111, &[RecipeValue::Bytes(b"123456789".to_vec())]).unwrap();
    assert_eq!(outcome.status, 0);
    assert_eq!(
        outcome.outputs,
        vec![RecipeValue::Uint {
            width: 64,
            value: 0x6c40_df5f_0b49_7347,
        }]
    );
}

#[test]
fn generic_eh_packages_are_deterministic_for_all_four_profiles() {
    assert!(build_eh_recipe_package(0).is_err());
    assert!(build_eh_recipe_package(5).is_err());
    let expected = [
        (
            1,
            24_786,
            "f030732cd966fd9570149f6fd2d1befb5eed66319eb248b609693e868f977941",
        ),
        (
            2,
            26_738,
            "cce1758613d7f10278533409e07103ae15162972fcf30030e17c233e39664011",
        ),
        (
            3,
            24_786,
            "8c91ba74f9bbed97aed89191e8d8d30a9a0c4d32bd5ac98b63a4c19ed71fb0e7",
        ),
        (
            4,
            26_738,
            "de237fcd9d53581710404bd8b00152cb68f50adef48e715fdd4572e786bae4b8",
        ),
    ];
    for (profile_version, expected_bytes, expected_hash) in expected {
        let first = build_eh_recipe_package(profile_version).unwrap();
        let second = build_eh_recipe_package(profile_version).unwrap();
        assert_eq!(first, second);
        assert_eq!(first.len(), expected_bytes);
        assert_eq!(format!("{:x}", Sha256::digest(&first)), expected_hash);
    }
}

#[test]
fn generic_common_exports_cover_their_full_dynamic_domains() {
    let package = decode_recipe_package(&build_eh_recipe_package(1).unwrap(), 1).unwrap();
    let evaluate = |recipe_id, inputs: Vec<RecipeValue>| {
        evaluate_recipe(&package, recipe_id, &inputs).unwrap()
    };

    let side = 11_u64;
    let row = 2_u64;
    let column = 7_u64;
    let last = side - 1;
    let coordinates = [
        (row, column),
        (last - column, row),
        (last - row, last - column),
        (column, last - row),
        (row, last - column),
        (last - column, last - row),
        (last - row, column),
        (column, row),
    ];
    for (transform, (mapped_row, mapped_column)) in coordinates.into_iter().enumerate() {
        for polarity in [false, true] {
            for observed in [false, true] {
                let outcome = evaluate(
                    102,
                    vec![
                        RecipeValue::Uint {
                            width: 3,
                            value: transform as u64,
                        },
                        RecipeValue::Bool(polarity),
                        RecipeValue::Uint {
                            width: 16,
                            value: row,
                        },
                        RecipeValue::Uint {
                            width: 16,
                            value: column,
                        },
                        RecipeValue::Uint {
                            width: 16,
                            value: side,
                        },
                        RecipeValue::Bool(observed),
                    ],
                );
                assert_eq!(outcome.status, 0, "transform {transform}");
                assert_eq!(
                    outcome.outputs,
                    vec![
                        RecipeValue::Uint {
                            width: 32,
                            value: mapped_row * side + mapped_column,
                        },
                        RecipeValue::Bool(polarity ^ observed),
                    ],
                    "transform {transform}, polarity {polarity}, observed {observed}"
                );
            }
        }
    }
    for (invalid_side, invalid_row, invalid_column) in [(0, 0, 0), (11, 11, 0), (11, 0, 11)] {
        let outcome = evaluate(
            102,
            vec![
                RecipeValue::Uint { width: 3, value: 0 },
                RecipeValue::Bool(false),
                RecipeValue::Uint {
                    width: 16,
                    value: invalid_row,
                },
                RecipeValue::Uint {
                    width: 16,
                    value: invalid_column,
                },
                RecipeValue::Uint {
                    width: 16,
                    value: invalid_side,
                },
                RecipeValue::Bool(false),
            ],
        );
        assert_eq!(outcome.status, 3);
        assert!(outcome.outputs.is_empty());
    }

    for value in [0, 1, 10, 11, 255] {
        let outcome = evaluate(106, vec![RecipeValue::Uint { width: 8, value }]);
        assert_eq!(outcome.status, 0);
        assert_eq!(outcome.outputs, vec![RecipeValue::Bool(value == 0)]);
    }

    for profile_version in 1..=4 {
        let package = decode_recipe_package(
            &build_eh_recipe_package(profile_version).unwrap(),
            profile_version,
        )
        .unwrap();
        for (logical, side, shell_width) in
            [(987_654_321_u64, 100_u64, 10_u64), (0xf234_5678, 17, 3)]
        {
            let interior = side - 2 * shell_width;
            let population = interior * interior;
            let reduced = logical % population;
            let scaled = (population + 2 * (reduced % interior) * interior - reduced) % population;
            let offset = (40_503 * u64::from(profile_version) + shell_width * 257) % population;
            let expected = (scaled + offset) % population;
            let outcome = evaluate_recipe(
                &package,
                109,
                &[
                    RecipeValue::Uint {
                        width: 32,
                        value: logical,
                    },
                    RecipeValue::Uint {
                        width: 16,
                        value: side,
                    },
                    RecipeValue::Uint {
                        width: 16,
                        value: shell_width,
                    },
                ],
            )
            .unwrap();
            assert_eq!(outcome.status, 0);
            assert_eq!(
                outcome.outputs,
                vec![RecipeValue::Uint {
                    width: 32,
                    value: expected,
                }]
            );
        }
        for (side, shell_width) in [(0, 0), (17, 17), (17, 18), (2_049, 1)] {
            let outcome = evaluate_recipe(
                &package,
                109,
                &[
                    RecipeValue::Uint {
                        width: 32,
                        value: 1,
                    },
                    RecipeValue::Uint {
                        width: 16,
                        value: side,
                    },
                    RecipeValue::Uint {
                        width: 16,
                        value: shell_width,
                    },
                ],
            )
            .unwrap();
            assert_eq!(outcome.status, 3);
            assert!(outcome.outputs.is_empty());
        }
    }

    for (expected_count, available_count, valid, expected) in [
        (1, 0, true, true),
        (u16::MAX, u16::MAX - 1, true, true),
        (0, u16::MAX, true, false),
        (2, 1, false, false),
    ] {
        let outcome = evaluate(
            112,
            vec![
                RecipeValue::Uint {
                    width: 16,
                    value: u64::from(expected_count),
                },
                RecipeValue::Uint {
                    width: 16,
                    value: u64::from(available_count),
                },
                RecipeValue::Bool(valid),
            ],
        );
        assert_eq!(outcome.status, 0);
        assert_eq!(outcome.outputs, vec![RecipeValue::Bool(expected)]);
    }
}

#[test]
fn generic_eh_packages_fit_the_exact_python_route_owner() {
    let workspace = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .expect("workspace root");
    let temporary = std::env::temp_dir().join(format!(
        "golden-board-eh-route-projection-{}",
        std::process::id()
    ));
    std::fs::create_dir(&temporary).expect("exclusive route projection directory");
    let mut paths = Vec::new();
    for profile_version in 1..=4 {
        let path = temporary.join(format!("profile-{profile_version}.bin"));
        std::fs::write(&path, build_eh_recipe_package(profile_version).unwrap())
            .expect("write exact generated package");
        paths.push(path);
    }

    let script = r#"
from pathlib import Path
import sys
from golden_board import m2_recipe, m2_route_data as route

root = Path(sys.argv[1])
manifest = (root / "spec/route-data-v0.json").read_bytes()
rows = (
    ("eh72-r2-crc32c-v0", 1, "eh72-replicated-v0", "crc32c-v0"),
    ("eh72-r2-crc64-ecma-v0", 2, "eh72-replicated-v0", "crc64-ecma-v0"),
    ("eh72-r3-crc32c-v0", 3, "eh72-replicated-v0", "crc32c-v0"),
    ("eh72-r3-crc64-ecma-v0", 4, "eh72-replicated-v0", "crc64-ecma-v0"),
)
expected_prefix_bytes = (27_714, 29_674, 27_714, 29_674)
for row, package_path, prefix in zip(
    rows, sys.argv[2:], expected_prefix_bytes, strict=True
):
    package = Path(package_path).read_bytes()
    m2_recipe.admit_eh72_transport_recipe(row[1], package)
    candidate = route.CandidateRouteData(*row, (package,))
    if row[1] in (1, 3):
        image = route.build_route_images(manifest, candidate, 2048, 128)
        assert image.instruction_cells == 886_848
        assert image.headroom_cells == 44_343
        assert tuple(sector.route_prefix_cells // 8 for sector in image.sectors) == (prefix,) * 4
        assert all(len(sector.data) == route.SECTOR_CAPACITY_BYTES for sector in image.sectors)
        assert all(
            sector.route_prefix_cells + sector.headroom_cells <= route.SECTOR_CAPACITY_CELLS
            for sector in image.sectors
        )
    else:
        try:
            route.build_route_images(manifest, candidate, 2048, 128)
        except route.RouteDataError as error:
            assert str(error) == "sector-fit"
        else:
            raise AssertionError("CRC64 candidate unexpectedly passed sector-fit")
"#;
    let python = std::env::var_os("GB_PYTHON")
        .unwrap_or_else(|| workspace.join(".venv/bin/python").into_os_string());
    let mut command = Command::new(&python);
    command
        .arg("-c")
        .arg(script)
        .arg(workspace)
        .args(&paths)
        .env("PYTHONPATH", workspace.join("python"));
    let output = command.output().unwrap_or_else(|error| {
        panic!(
            "run Python route owner with {}: {error}",
            Path::new(&python).display()
        )
    });
    if let Err(error) = std::fs::remove_dir_all(&temporary) {
        panic!("clean route projection directory: {error}");
    }
    assert!(
        output.status.success(),
        "Python route owner rejected generated packages:\n{}",
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn generic_rs_decoder_recipe_parses_and_matches_clean_and_single_error() {
    assert!(build_rs_decoder_recipe_package(4).is_err());
    assert!(build_rs_decoder_recipe_package(7).is_err());
    let raw = build_rs_decoder_recipe_package(5).unwrap();
    let package = decode_recipe_package(&raw, 5).unwrap();
    assert_eq!(package.recipe_ids().last(), Some(30));
    assert_eq!(raw.len(), 32_302);
    assert_eq!(u32::from_be_bytes(raw[20..24].try_into().unwrap()), 865);
    assert_eq!(u32::from_be_bytes(raw[28..32].try_into().unwrap()), 2_306);
    assert_eq!(package.maximum_primitive_steps, 1_698_049);
    assert_eq!(package.peak_scratch_bytes, 7_688);
    assert_eq!(
        format!("{:x}", Sha256::digest(&raw)),
        "2dd94f23f63bd4fbeb8d56565a9cc9a7e0a2054d3483e364cfb60e7751058e91"
    );
    let profile_six = build_rs_decoder_recipe_package(6).unwrap();
    assert_eq!(profile_six.len(), 32_302);
    assert_eq!(
        format!("{:x}", Sha256::digest(&profile_six)),
        "1c05a1f57394d292487f46561492619358fe2d12e42e3a20194d5917f351e555"
    );

    // These are resource diagnostics for the hash-bound recipe manifestation.
    // Its earlier, decisive gate-2 result is recipe-closure failure; no claim
    // about other possible recipe DAGs follows from these measurements.
    let sector_capacity_cells = 128_usize * (2_048 - 128);
    let absolute_prefix_bytes = (0..=sector_capacity_cells / 8)
        .rev()
        .find(|bytes| {
            let prefix_cells = bytes * 8;
            let total_instructions = 4 * prefix_cells;
            let headroom = ((total_instructions + 19) / 20).max(4 * 256);
            let worst_sector_headroom = 256 + (headroom - 4 * 256).div_ceil(4);
            prefix_cells + worst_sector_headroom <= sector_capacity_cells
        })
        .unwrap();
    assert_eq!(absolute_prefix_bytes, 29_257);
    assert_eq!(raw.len() - absolute_prefix_bytes, 3_045);

    let data = std::array::from_fn(|index| index as u8);
    let encoded = encode_rs255_191(&data);
    let clean = evaluate_rs_decoder_recipe(&package, &encoded, &[]).unwrap();
    assert_eq!(clean.status, 0);
    assert_eq!(clean.outputs, vec![RecipeValue::Bytes(data.to_vec())]);

    let mut changed = encoded;
    changed[0] ^= 0x53;
    let recovered = evaluate_rs_decoder_recipe(&package, &changed, &[]).unwrap();
    assert_eq!(recovered.status, 0);
    assert_eq!(recovered.outputs, vec![RecipeValue::Bytes(data.to_vec())]);

    let mut erased = encoded;
    erased[190] = 0xa5;
    let recovered = evaluate_rs_decoder_recipe(&package, &erased, &[190]).unwrap();
    assert_eq!(recovered.status, 0);
    assert_eq!(recovered.outputs, vec![RecipeValue::Bytes(data.to_vec())]);

    erased[0] ^= 0x53;
    let recovered = evaluate_rs_decoder_recipe(&package, &erased, &[190]).unwrap();
    assert_eq!(recovered.status, 0);
    assert_eq!(recovered.outputs, vec![RecipeValue::Bytes(data.to_vec())]);
}

#[test]
fn exact_rs_recipe_manifestations_fail_closure_before_resource_gates_in_python() {
    let workspace = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .expect("workspace root");
    let temporary = std::env::temp_dir().join(format!(
        "golden-board-rs-manifestation-audit-{}",
        std::process::id()
    ));
    std::fs::create_dir(&temporary).expect("exclusive RS audit directory");
    let mut paths = Vec::new();
    for profile_version in 5..=6 {
        let path = temporary.join(format!("profile-{profile_version}.bin"));
        std::fs::write(
            &path,
            build_rs_decoder_recipe_package(profile_version).unwrap(),
        )
        .expect("write exact RS manifestation");
        paths.push(path);
    }

    let script = r#"
from pathlib import Path
import sys
from golden_board import m2_recipe

root = Path(sys.argv[1])
corpus = (root / "conformance/rs255-191-v0.json").read_bytes()
expected = {
    5: "2dd94f23f63bd4fbeb8d56565a9cc9a7e0a2054d3483e364cfb60e7751058e91",
    6: "1c05a1f57394d292487f46561492619358fe2d12e42e3a20194d5917f351e555",
}
for profile_version, package_path in zip((5, 6), sys.argv[2:], strict=True):
    result = m2_recipe.audit_rs_decoder_manifestation(
        profile_version, Path(package_path).read_bytes(), corpus
    )
    assert result.package_sha256 == expected[profile_version]
    assert len(result.checked_case_ids) == 18
    assert result.mismatched_case_ids == (
        "invalid-common-local-check",
        "e0-s64",
        "e1-s62",
        "e16-s32",
        "e31-s2",
        "e32-s0",
    )
    assert not result.recipe_closure_pass
    assert result.failure_reason == "incomplete_rs_recovery_recipe"
    assert not result.later_resource_gates_evaluated
"#;
    let python = std::env::var_os("GB_PYTHON")
        .unwrap_or_else(|| workspace.join(".venv/bin/python").into_os_string());
    let mut command = Command::new(&python);
    command
        .arg("-c")
        .arg(script)
        .arg(workspace)
        .args(&paths)
        .env("PYTHONPATH", workspace.join("python"));
    let output = command.output().unwrap_or_else(|error| {
        panic!(
            "run Python RS manifestation audit with {}: {error}",
            Path::new(&python).display()
        )
    });
    if let Err(error) = std::fs::remove_dir_all(&temporary) {
        panic!("clean RS audit directory: {error}");
    }
    assert!(
        output.status.success(),
        "Python rejected exact RS manifestations:\n{}",
        String::from_utf8_lossy(&output.stderr)
    );
}
