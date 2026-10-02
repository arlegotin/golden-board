use gb_bootstrap::body_codec_v1::{decode_body, decode_lzss, encode_body, encode_lzss};

#[test]
fn independently_written_small_vectors_and_overlap() {
    for (plain, wire) in [
        (b"".as_slice(), vec![3, 0, 0]),
        (b"a".as_slice(), vec![3, 0, 1, 0, b'a']),
        (b"aaaa".as_slice(), vec![3, 0, 4, 0x40, b'a', 0, 0]),
        (
            b"abcabcabc".as_slice(),
            vec![3, 0, 9, 0x10, b'a', b'b', b'c', 0, 0x23],
        ),
    ] {
        assert_eq!(encode_lzss(plain).unwrap(), wire);
        assert_eq!(decode_lzss(&wire).unwrap(), plain);
    }
    assert_eq!(encode_body(b"aaaa").unwrap(), (0, b"aaaa".to_vec()));
    let (version, wire) = encode_body(&[0; 256]).unwrap();
    assert_eq!(version, 1);
    assert_eq!(decode_body(version, &wire).unwrap(), [0; 256]);
}

#[test]
fn malformed_frames_reject_atomically() {
    let valid = encode_lzss(b"abcabcabc").unwrap();
    for end in 0..valid.len() {
        assert!(decode_lzss(&valid[..end]).is_err(), "truncated at {end}");
    }
    for bad in [
        vec![2, 0, 0],                      // Unknown codec.
        vec![3, 0, 0, 0],                   // Empty with trailing group.
        vec![3, 0, 1, 1, b'a'],             // Unused flag bit.
        vec![3, 0, 3, 0x80, 0, 0],          // No history.
        vec![3, 0, 4, 0x40, b'a', 0, 0x10], // Distance two after one byte.
        vec![3, 0, 3, 0x40, b'a', 0, 0],    // Copy overruns expected output.
        vec![3, 0x40, 1],                   // Decoded limit plus one.
    ] {
        assert!(decode_lzss(&bad).is_err(), "{bad:?}");
    }
    let mut trailing = valid;
    trailing.push(0);
    assert!(decode_lzss(&trailing).is_err());
    assert!(decode_body(2, b"abc").is_err());
    assert_eq!(decode_body(0, &[3, 0, 0]).unwrap(), [3, 0, 0]);
}

#[test]
fn maximum_output_and_window_are_exact() {
    let plain = vec![0x5a; 16_384];
    let wire = encode_lzss(&plain).unwrap();
    assert_eq!(decode_lzss(&wire).unwrap(), plain);
    assert!(encode_lzss(&[0; 16_385]).is_err());
    assert!(decode_lzss(&[0; 16_385]).is_err());
    assert!(decode_body(0, &[0; 16_385]).is_err());
    let mut window = vec![3, 0x10, 3]; // 4099 decoded bytes.
    for group in 0..512 {
        window.push(0);
        for offset in 0..8 {
            window.push(((group * 8 + offset) % 251) as u8);
        }
    }
    window.extend_from_slice(&[0x80, 0xff, 0xf0]); // 4096 back, length3.
    let decoded = decode_lzss(&window).unwrap();
    assert_eq!(decoded.len(), 4099);
    assert_eq!(&decoded[4096..], &[0, 1, 2]);
}

#[test]
fn generated_patterns_preserve_bytes_and_use_raw_when_larger() {
    let mut state = 0x8c02_9403u32;
    let mut random = Vec::new();
    for _ in 0..16_384 {
        state ^= state << 13;
        state ^= state >> 17;
        state ^= state << 5;
        random.push(state as u8);
    }
    assert!(encode_lzss(&random).unwrap().len() > 16_384);
    assert_eq!(encode_body(&random).unwrap(), (0, random.clone()));
    for length in [
        0, 1, 2, 3, 7, 8, 9, 17, 18, 19, 255, 4095, 4096, 4097, 16_384,
    ] {
        for modulus in [1, 3, 251] {
            let source: Vec<u8> = (0..length).map(|i| (i % modulus) as u8).collect();
            let (version, wire) = encode_body(&source).unwrap();
            assert_eq!(decode_body(version, &wire).unwrap(), source);
            assert_eq!(encode_body(&source).unwrap(), (version, wire));
        }
    }
}
