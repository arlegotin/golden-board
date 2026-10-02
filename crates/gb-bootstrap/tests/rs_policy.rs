use std::collections::BTreeMap;

use gb_foundation::{ManifestValue as V, validate_canonical_manifest};
use sha2::{Digest, Sha256};

fn object(value: &V) -> &BTreeMap<String, V> {
    match value {
        V::Object(v) => v,
        _ => panic!("object"),
    }
}
fn array(value: &V) -> &[V] {
    match value {
        V::Array(v) => v,
        _ => panic!("array"),
    }
}
fn text(value: &V) -> &str {
    match value {
        V::String(v) => v,
        _ => panic!("string"),
    }
}
fn uint(value: &V) -> u64 {
    match value {
        V::U64(v) => *v,
        _ => panic!("unsigned"),
    }
}
fn hex(value: &str) -> Vec<u8> {
    assert_eq!(value.len() % 2, 0);
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
}
fn sha(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn mul(mut a: u8, mut b: u8) -> u8 {
    let mut product = 0;
    for _ in 0..8 {
        if b & 1 != 0 {
            product ^= a;
        }
        let high = a & 0x80 != 0;
        a <<= 1;
        if high {
            a ^= 0x1d;
        }
        b >>= 1;
    }
    product
}
fn pow(mut a: u8, mut n: usize) -> u8 {
    let mut out = 1;
    while n != 0 {
        if n & 1 != 0 {
            out = mul(out, a);
        }
        a = mul(a, a);
        n >>= 1;
    }
    out
}
fn alpha(n: usize) -> u8 {
    pow(2, n % 255)
}
fn inv(a: u8) -> u8 {
    assert_ne!(a, 0);
    pow(a, 254)
}
fn eval(poly: &[u8], z: u8) -> u8 {
    poly.iter()
        .rev()
        .fold(0, |value, coefficient| mul(value, z) ^ coefficient)
}
fn convolution(a: &[u8], b: &[u8]) -> Vec<u8> {
    let mut out = vec![0; a.len() + b.len() - 1];
    for (i, x) in a.iter().enumerate() {
        for (j, y) in b.iter().enumerate() {
            out[i + j] ^= mul(*x, *y);
        }
    }
    out
}
fn generator() -> Vec<u8> {
    let mut ascending = vec![1];
    for root in 0..64 {
        ascending = convolution(&ascending, &[alpha(root), 1]);
    }
    ascending.into_iter().rev().collect()
}
fn encode(data: &[u8]) -> Vec<u8> {
    assert_eq!(data.len(), 191);
    let generator = generator();
    let mut work = data.to_vec();
    work.extend_from_slice(&[0; 64]);
    for i in 0..191 {
        let q = work[i];
        if q != 0 {
            for j in 0..=64 {
                work[i + j] ^= mul(q, generator[j]);
            }
        }
    }
    let mut out = data.to_vec();
    out.extend_from_slice(&work[191..]);
    out
}
fn syndromes(word: &[u8]) -> Vec<u8> {
    (0..64)
        .map(|j| word.iter().fold(0, |v, byte| mul(v, alpha(j)) ^ byte))
        .collect()
}

#[derive(Debug)]
struct Trace {
    status: u8,
    corrected: Vec<u8>,
    syndromes: Vec<u8>,
    gamma: Vec<u8>,
    transformed: Vec<u8>,
    bm_input: Vec<u8>,
    unknown: Vec<u8>,
    locator: Vec<u8>,
    evaluator: Vec<u8>,
    positions: Vec<usize>,
    magnitudes: Vec<u8>,
}

fn failure(status: u8) -> Trace {
    Trace {
        status,
        corrected: vec![],
        syndromes: vec![],
        gamma: vec![],
        transformed: vec![],
        bm_input: vec![],
        unknown: vec![],
        locator: vec![],
        evaluator: vec![],
        positions: vec![],
        magnitudes: vec![],
    }
}

fn decode(observed: &[u8], erasures: &[usize]) -> Trace {
    if observed.len() != 255
        || erasures.windows(2).any(|p| p[0] >= p[1])
        || erasures.iter().any(|p| *p >= 255)
    {
        return failure(3);
    }
    if erasures.len() > 64 {
        return failure(4);
    }
    let s = erasures.len();
    let mut word = observed.to_vec();
    for p in erasures {
        word[*p] = 0;
    }
    let syn = syndromes(&word);
    if s == 0 && syn.iter().all(|x| *x == 0) {
        return Trace {
            status: 0,
            corrected: word,
            syndromes: syn,
            gamma: vec![1],
            transformed: vec![0; 64],
            bm_input: vec![0; 64],
            unknown: vec![1],
            locator: vec![1],
            evaluator: vec![0; 64],
            positions: vec![],
            magnitudes: vec![],
        };
    }
    let mut gamma = vec![1];
    for p in erasures {
        gamma = convolution(&gamma, &[1, alpha(254 - p)]);
    }
    let mut transformed = vec![0; 64];
    for k in 0..64 {
        for i in 0..=k.min(s) {
            transformed[k] ^= mul(gamma[i], syn[k - i]);
        }
    }
    let u = transformed[s..].to_vec();
    let mut c = vec![1_u8];
    let mut b = vec![1_u8];
    let mut l = 0_usize;
    let mut m = 1_usize;
    let mut previous_d = 1_u8;
    for n in 0..u.len() {
        let mut d = u[n];
        for i in 1..=l {
            d ^= mul(*c.get(i).unwrap_or(&0), u[n - i]);
        }
        if d == 0 {
            m += 1;
            continue;
        }
        let old = c.clone();
        let q = mul(d, inv(previous_d));
        c.resize(c.len().max(b.len() + m), 0);
        for i in 0..b.len() {
            c[i + m] ^= mul(q, b[i]);
        }
        if 2 * l <= n {
            l = n + 1 - l;
            b = old;
            previous_d = d;
            m = 1;
        } else {
            m += 1;
        }
    }
    while c.len() > 1 && c.last() == Some(&0) {
        c.pop();
    }
    if c.len() != l + 1 || c.len() > 33 || 2 * l + s > 64 {
        return failure(4);
    }
    let locator = convolution(&gamma, &c);
    if locator.len() > 65 || locator.len() != s + l + 1 {
        return failure(4);
    }
    let positions: Vec<_> = (0..255)
        .filter(|p| eval(&locator, alpha(p + 1)) == 0)
        .collect();
    if positions.len() != locator.len() - 1
        || erasures.iter().any(|p| !positions.contains(p))
        || positions.iter().filter(|p| !erasures.contains(p)).count() != l
    {
        return failure(5);
    }
    let mut omega = vec![0; 64];
    for i in 0..syn.len() {
        for j in 0..locator.len() {
            if i + j < 64 {
                omega[i + j] ^= mul(syn[i], locator[j]);
            }
        }
    }
    let mut derivative = vec![0; locator.len().saturating_sub(1)];
    for i in (1..locator.len()).step_by(2) {
        derivative[i - 1] = locator[i];
    }
    let mut magnitudes = Vec::with_capacity(positions.len());
    let mut unknown_nonzero = 0;
    for p in &positions {
        let z = alpha(p + 1);
        let denominator = eval(&derivative, z);
        if denominator == 0 {
            return failure(5);
        }
        let magnitude = mul(mul(alpha(254 - p), eval(&omega, z)), inv(denominator));
        if !erasures.contains(p) {
            if magnitude == 0 {
                return failure(5);
            }
            unknown_nonzero += 1;
        }
        magnitudes.push(magnitude);
    }
    if unknown_nonzero != l || 2 * unknown_nonzero + s > 64 {
        return failure(5);
    }
    for (p, magnitude) in positions.iter().zip(&magnitudes) {
        word[*p] ^= magnitude;
    }
    if syndromes(&word).iter().any(|x| *x != 0) {
        return failure(5);
    }
    Trace {
        status: 0,
        corrected: word,
        syndromes: syn,
        gamma,
        transformed,
        bm_input: u,
        unknown: c,
        locator,
        evaluator: omega,
        positions,
        magnitudes,
    }
}

#[test]
fn shared_rs_owner_corpus_is_rederived_independently() {
    let raw = include_bytes!("../../../conformance/rs255-191-v0.json");
    assert_eq!(
        sha(raw),
        "d4dcc0cc441f42c66dc19d6db636733fc577751baf073dc7f951cd3c3dd23f72"
    );
    let manifest = validate_canonical_manifest(raw).unwrap();
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
            "schema"
        ]
    );
    assert_eq!(
        text(&root["schema"]),
        "golden-board.rs255-191-v0-fixtures/v0"
    );
    assert_eq!(text(&root["profile_id"]), "rs255-191-v0");
    for row in array(&root["field_multiplication_kats"]) {
        let row = object(row);
        assert_eq!(
            mul(uint(&row["a"]) as u8, uint(&row["b"]) as u8),
            uint(&row["product"]) as u8
        );
    }
    for row in array(&root["field_inverse_kats"]) {
        let row = object(row);
        assert_eq!(inv(uint(&row["a"]) as u8), uint(&row["inverse"]) as u8);
    }
    let generated = generator();
    assert_eq!(generated.len(), 65);
    assert_eq!(generated, hex(text(&root["generator_coefficients_hex"])));
    assert_eq!(sha(&generated), text(&root["generator_sha256"]));
    let mut codewords = BTreeMap::new();
    for row in array(&root["encode_kats"]) {
        let row = object(row);
        let codeword = encode(&hex(text(&row["data_hex"])));
        assert_eq!(codeword, hex(text(&row["codeword_hex"])));
        assert_eq!(sha(&codeword), text(&row["codeword_sha256"]));
        codewords.insert(text(&row["id"]).to_owned(), codeword);
    }
    for row in array(&root["decode_kats"]) {
        let row = object(row);
        let observation = hex(text(&row["observation_hex"]));
        assert_eq!(sha(&observation), text(&row["observation_sha256"]));
        let erasures: Vec<_> = array(&row["erasure_positions"])
            .iter()
            .map(|v| uint(v) as usize)
            .collect();
        let decoded = decode(&observation, &erasures);
        assert_eq!(
            decoded.status as u64,
            uint(&row["expected_status"]),
            "{}",
            text(&row["id"])
        );
        if decoded.status == 0 {
            assert_eq!(
                decoded.corrected,
                codewords[text(&row["expected_codeword_id"])]
            );
            let expected_positions: Vec<_> = array(&row["expected_correction_positions"])
                .iter()
                .map(|v| uint(v) as usize)
                .collect();
            let expected_magnitudes: Vec<_> = array(&row["expected_correction_magnitudes"])
                .iter()
                .map(|v| uint(v) as u8)
                .collect();
            assert_eq!(decoded.positions, expected_positions);
            assert_eq!(decoded.magnitudes, expected_magnitudes);
        }
    }
    let row = object(&root["intermediate_kat"]);
    let erasures: Vec<_> = array(&row["erasure_positions"])
        .iter()
        .map(|v| uint(v) as usize)
        .collect();
    let trace = decode(&hex(text(&row["observation_hex"])), &erasures);
    assert_eq!(trace.status, 0);
    assert_eq!(trace.syndromes, hex(text(&row["syndromes_hex"])));
    assert_eq!(
        trace.gamma,
        hex(text(&row["erasure_locator_ascending_hex"]))
    );
    assert_eq!(
        trace.transformed,
        hex(text(&row["transformed_syndromes_hex"]))
    );
    assert_eq!(trace.bm_input, hex(text(&row["bm_input_hex"])));
    assert_eq!(
        trace.unknown,
        hex(text(&row["unknown_error_locator_ascending_hex"]))
    );
    assert_eq!(trace.locator, hex(text(&row["full_locator_ascending_hex"])));
    assert_eq!(
        trace.evaluator,
        hex(text(&row["evaluator_ascending_padded_hex"]))
    );
    assert_eq!(
        trace.positions,
        array(&row["correction_positions"])
            .iter()
            .map(|v| uint(v) as usize)
            .collect::<Vec<_>>()
    );
    assert_eq!(
        trace.magnitudes,
        array(&row["correction_magnitudes"])
            .iter()
            .map(|v| uint(v) as u8)
            .collect::<Vec<_>>()
    );
    assert_eq!(array(&root["mutant_ids"]).len(), 15);
}
