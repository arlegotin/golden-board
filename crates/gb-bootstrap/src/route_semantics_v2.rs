//! Validate observed finite teaching relationships and separate recovered claims.
//!
//! Runtime inputs are carried values, the observed package and recovered bytes.
//! No lesson, route, fixture or carrier constructor supplies expected decoder data.
use crate::candidate::{
    EhObservation, aggregate_repetition_observation, decode_eh_unit_fast, encode_eh_unit,
};
use crate::recipe_wire_v1::{RecipePackageV1, decode_recipe_package_v1};
use gb_content::{ContentProjection, Record, RecordPayload as P};
use std::collections::{BTreeMap, BTreeSet};
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ContextState {
    Unresolved,
    Consistent,
    Contradiction,
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ContextProof {
    required: ContextState,
    all: ContextState,
}
impl ContextProof {
    pub fn required(&self) -> ContextState {
        self.required
    }
    pub fn all(&self) -> ContextState {
        self.all
    }
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ContextCommitments {
    fact12: Vec<u8>,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SemanticError;
type Result<T> = std::result::Result<T, SemanticError>;
fn need(ok: bool) -> Result<()> {
    if ok { Ok(()) } else { Err(SemanticError) }
}
fn take(raw: &[u8], at: usize, n: usize) -> Result<&[u8]> {
    raw.get(at..at.checked_add(n).ok_or(SemanticError)?)
        .ok_or(SemanticError)
}
fn u16_at(raw: &[u8], at: usize) -> Result<u16> {
    Ok(u16::from_be_bytes(take(raw, at, 2)?.try_into().unwrap()))
}
fn u32_at(raw: &[u8], at: usize) -> Result<u32> {
    Ok(u32::from_be_bytes(take(raw, at, 4)?.try_into().unwrap()))
}
fn words(out: &mut Vec<u8>, values: &[u16]) {
    for v in values {
        out.extend(v.to_be_bytes());
    }
}
fn longs(out: &mut Vec<u8>, values: &[u32]) {
    for v in values {
        out.extend(v.to_be_bytes());
    }
}
fn layout(out: &mut Vec<u8>, fields: &[(u16, u16)]) {
    words(out, &[fields.len() as u16]);
    for &(a, b) in fields {
        words(out, &[a, b]);
    }
}
fn exact(raw: &[u8], expected: Vec<u8>) -> Result<()> {
    need(raw == expected)
}
fn common_recheck(raw: &mut [u8]) {
    let mut p = crate::LOCAL_CHECK_DOMAIN.to_vec();
    p.extend_from_slice(&raw[..187]);
    raw[187..191].copy_from_slice(&crate::crc32c(&p).to_be_bytes());
}
fn checked_common(raw: &[u8]) -> bool {
    crate::decode_common_block(raw, 8).is_ok()
}
fn agreement(raw: &[u8]) -> bool {
    crate::decode_common_block(raw, 8)
        .is_ok_and(|b| crate::validate_fragment_envelope_agreement(&b, &b.payload).is_ok())
}
fn common_example(value: u8) -> Result<[u8; 191]> {
    let envelope = crate::encode_section(&crate::SectionEnvelope {
        section_id: 400,
        section_type: 4,
        section_version: 0,
        closure_class: 129,
        check_id: 1,
        dependencies: vec![],
        payload: vec![value],
    })
    .map_err(|_| SemanticError)?;
    crate::encode_common_block(&crate::CommonBlock {
        profile_version: 8,
        section_id: 400,
        semantic_copy_id: 0,
        section_type: 4,
        section_version: 0,
        fragment_index: 0,
        fragment_count: 1,
        section_envelope_length: envelope.len() as u32,
        payload: envelope,
    })
    .map_err(|_| SemanticError)
}
fn wire_frames(raw: &[u8]) -> Result<(BTreeMap<u16, &[u8]>, BTreeMap<u16, &[u8]>)> {
    let mut at = 64;
    let mut tables = BTreeMap::new();
    let mut recipes = BTreeMap::new();
    for _ in 0..u16_at(raw, 18)? {
        let n = 16 + u32_at(raw, at + 12)? as usize;
        let row = take(raw, at, n)?;
        tables.insert(u16_at(row, 0)?, row);
        at += n;
    }
    for _ in 0..u16_at(raw, 16)? {
        let n = u32_at(raw, at + 28)? as usize;
        let row = take(raw, at, n)?;
        recipes.insert(u16_at(row, 0)?, row);
        at += n;
    }
    need(at == raw.len())?;
    Ok((tables, recipes))
}
fn first_six(v: &[&[u8]], package: &RecipePackageV1) -> Result<()> {
    let mut out = vec![];
    for b in [0u8, 128, 170, 240, 204, 1, 129, 24] {
        out.extend([b, !b]);
    }
    exact(v[0], out)?;
    let base = [0x80u8, 0x40, 0x20, 0x10, 8, 4, 3, 0xc1];
    let bits: Vec<_> = base
        .iter()
        .flat_map(|b| (0..8).map(move |i| (b >> (7 - i)) & 1))
        .collect();
    let observation = crate::RawObservation::parse(&bits, 64).map_err(|_| SemanticError)?;
    let mut out = vec![];
    let mut images = BTreeSet::new();
    for t in 0..8 {
        let mut image = vec![0u8; 8];
        for r in 0..8 {
            for c in 0..8 {
                image[r] |= observation
                    .normalized_bit(
                        crate::EntryHypothesis {
                            transform: t,
                            polarity: 0,
                        },
                        r,
                        c,
                    )
                    .map_err(|_| SemanticError)?
                    << (7 - c);
            }
        }
        need(images.insert(image.clone()))?;
        need(images.insert(image.iter().map(|x| !x).collect()))?;
        out.extend(image);
    }
    exact(v[1], out)?;
    let mut out = vec![];
    for n in [0u8, 1, 2, 3, 4, 5, 7, 8, 15, 16, 24, 31] {
        out.extend(((1u32 << n) - 1).to_be_bytes());
        out.extend([n, 255 ^ n]);
        words(&mut out, &[u16::from(n)]);
    }
    exact(v[2], out)?;
    let mut out = vec![];
    words(&mut out, &[32, 8, 24, 6]);
    for q in 0..4 {
        for (u, v) in [(0, 0), (0, 23), (7, 0), (7, 23), (0, 1), (1, 0)] {
            let (r, c) = crate::sector_cell(32, 8, q, u, v).map_err(|_| SemanticError)?;
            words(
                &mut out,
                &[
                    q as u16,
                    u as u16,
                    v as u16,
                    r as u16,
                    c as u16,
                    (24 * u + v) as u16,
                ],
            );
        }
    }
    exact(v[3], out)?;
    let mut out = vec![];
    for fields in [
        &[
            (0, 8),
            (8, 2),
            (10, 1),
            (11, 1),
            (12, 2),
            (14, 2),
            (16, 4),
            (20, 4),
            (24, 4),
            (28, 2),
            (30, 2),
        ][..],
        &[(0, 1), (1, 1), (2, 2), (4, 4)],
        &[
            (0, 8),
            (8, 2),
            (10, 2),
            (12, 2),
            (14, 2),
            (16, 2),
            (18, 2),
            (20, 4),
            (24, 4),
            (28, 4),
            (32, 4),
            (36, 8),
            (44, 4),
            (48, 16),
        ],
        &[(0, 2), (2, 1), (3, 1), (4, 4), (8, 4), (12, 4)],
        &[
            (0, 2),
            (2, 2),
            (4, 2),
            (6, 2),
            (8, 4),
            (12, 4),
            (16, 8),
            (24, 4),
            (28, 4),
        ],
        &[(0, 2), (2, 1), (3, 1), (4, 4), (8, 4)],
    ] {
        layout(&mut out, fields);
    }
    let (_, recipes) = wire_frames(&package.encoded)?;
    let r = recipes.get(&109).ok_or(SemanticError)?;
    let input = u16_at(r, 4)?;
    let output = u16_at(r, 6)?;
    let descriptors = (input + output) * 12;
    let nodes = u32_at(r, 8)?;
    let front = 32 + usize::from(descriptors);
    need(nodes <= u16::MAX as u32 && r.len() <= u16::MAX as usize)?;
    words(
        &mut out,
        &[
            109,
            32,
            input,
            output,
            12,
            descriptors,
            nodes as u16,
            (r.len() - front) as u16,
            r.len() as u16,
        ],
    );
    exact(v[4], out)?;
    let mut out = vec![];
    for op in 1..=25u8 {
        let a = match op {
            1 | 2 | 24 | 25 => 0,
            5 | 14 | 22 => 1,
            3 | 20 | 23 => 3,
            _ => 2,
        };
        let aux = if matches!(op, 2 | 5 | 22) { 2 } else { 0 };
        let imm = if matches!(op, 1 | 5 | 14 | 22 | 25) {
            8
        } else {
            0
        };
        out.extend([op, a, 2 * a, aux, imm, 6 + 2 * a + aux + imm]);
    }
    for (t, u, min, max) in [
        (0, 0, 1, 64),
        (1, 0, 1, 1),
        (2, 0, 1, 1048576),
        (3, 1, 0, 1048576),
        (4, 2, 0, 1048576),
        (5, 0, 16, 16),
    ] {
        out.extend([t, u]);
        longs(&mut out, &[min, max]);
    }
    exact(v[5], out)
}
fn seventh_eighth(v: &[&[u8]]) -> Result<([u8; 191], [u8; 191])> {
    let mut out = vec![];
    layout(
        &mut out,
        &[
            (0, 2),
            (2, 2),
            (4, 4),
            (8, 2),
            (10, 2),
            (12, 2),
            (14, 2),
            (16, 2),
            (18, 2),
            (20, 2),
            (22, 4),
            (26, 4),
            (30, 157),
            (187, 4),
        ],
    );
    layout(
        &mut out,
        &[
            (0, 2),
            (2, 4),
            (6, 2),
            (8, 2),
            (10, 1),
            (11, 1),
            (12, 2),
            (14, 4),
        ],
    );
    out.extend(crate::LOCAL_CHECK_DOMAIN);
    out.extend(crate::SECTION_CHECK_DOMAIN);
    for input in [*b"123456789", [0, 1, 2, 3, 4, 5, 6, 7, 8]] {
        out.extend(input);
        out.extend(crate::crc32c(&input).to_be_bytes());
    }
    let a = common_example(0)?;
    let b = common_example(1)?;
    out.extend(a);
    out.extend(b);
    for (at, width, value, recheck) in [
        (2, 2, 1, 1),
        (14, 2, 1, 1),
        (26, 2, 1, 1),
        (18, 2, 0, 1),
        (16, 2, 1, 1),
        (4, 2, 1, 1),
        (22, 2, 1, 1),
        (48, 1, 1, 0),
        (187, 1, u16::from(a[187] ^ 1), 0),
        (53, 1, 1, 1),
    ] {
        let mut changed = a;
        changed[at..at + width].copy_from_slice(&value.to_be_bytes()[2 - width..]);
        if recheck == 1 {
            common_recheck(&mut changed);
        }
        words(
            &mut out,
            &[
                at as u16,
                width as u16,
                value,
                recheck,
                u16::from(checked_common(&changed)),
                u16::from(agreement(&changed)),
            ],
        );
    }
    exact(v[6], out)?;
    let mut out = vec![];
    words(&mut out, &[24, 9, 8, 216, 192, 191, 1, 0]);
    for i in 0..24 {
        words(&mut out, &[9 * i, 8 * i]);
    }
    for block in [a, b] {
        let enc = encode_eh_unit(&block);
        let dec = decode_eh_unit_fast(
            &EhObservation {
                encoded: enc,
                erasures: vec![],
            },
            8,
        )
        .map_err(|_| SemanticError)?;
        need(dec.common == block)?;
        out.extend(enc);
    }
    exact(v[7], out)?;
    Ok((a, b))
}
fn ninth(raw: &[u8], package: &RecipePackageV1) -> Result<()> {
    let (tables, _) = wire_frames(&package.encoded)?;
    let table = tables.get(&17).ok_or(SemanticError)?;
    need(
        table.len() == 272 && table[2] == 0 && u32_at(table, 4)? == 8 && u32_at(table, 8)? == 256,
    )?;
    let maps = [
        crate::mapping_v2::derive(2040, 128),
        crate::mapping_v2::derive(1952, 128),
    ];
    let mut out = vec![];
    for map in &maps {
        let m = map.as_ref().map_err(|_| SemanticError)?;
        need(u64::from(table[16 + usize::from(m.interior_side() / 8)]) == m.slot_multiplier())?;
        longs(
            &mut out,
            &[
                u32::from(m.side()),
                u32::from(m.shell_width()),
                u32::from(m.interior_side()),
                m.population() as u32,
                m.unit_slot_count() as u32,
                m.slot_multiplier() as u32,
                m.inverse_slot_multiplier() as u32,
                m.cell_multiplier() as u32,
                m.inverse_cell_multiplier() as u32,
                m.cell_offset() as u32,
            ],
        );
    }
    for map in maps {
        let m = map.map_err(|_| SemanticError)?;
        let q = m.unit_slot_count();
        let b = m.slot_multiplier();
        let mut rows = vec![];
        for (unit, bit) in [(1, 0), (1, 1727), (q, 0), (q, 1727), (q / b + 2, 0)] {
            let slot = (unit - 1) * b % q;
            let logical = slot * 1728 + u64::from(bit);
            let physical = m.forward(unit, bit).map_err(|_| SemanticError)?;
            need(m.inverse(physical).map_err(|_| SemanticError)? == (0, unit, bit))?;
            rows.push([
                unit as u32,
                u32::from(bit),
                slot as u32,
                logical as u32,
                physical as u32,
                0,
            ]);
        }
        for logical in [1728 * q - 1, 1728 * q, m.population() - 1] {
            let physical = (m.cell_multiplier() * logical + m.cell_offset()) % m.population();
            let (kind, unit, bit) = m.inverse(physical).map_err(|_| SemanticError)?;
            let slot = if kind == 0 { logical / 1728 } else { 0 };
            rows.push([
                unit as u32,
                u32::from(bit),
                slot as u32,
                logical as u32,
                physical as u32,
                u32::from(kind),
            ]);
        }
        for row in rows {
            longs(&mut out, &row);
        }
    }
    exact(raw, out)
}
fn lane(block: [u8; 191], flips: &[usize]) -> EhObservation {
    let mut encoded = encode_eh_unit(&block);
    for bit in flips {
        encoded[bit / 8] ^= 1 << (7 - bit % 8);
    }
    EhObservation {
        encoded,
        erasures: vec![],
    }
}
fn group(
    lanes: &[Option<EhObservation>],
    section: u32,
    a: &[u8; 191],
    b: &[u8; 191],
) -> Result<([u8; 8], [u8; 9], [u8; 12])> {
    need(matches!(lanes.len(), 1 | 2 | 5))?;
    let classify = |raw: &[u8; 191]| -> Result<u8> {
        if raw == a {
            Ok(1)
        } else if raw == b {
            Ok(2)
        } else {
            Err(SemanticError)
        }
    };
    let matches_identity = |raw: &[u8; 191]| {
        crate::decode_common_block(raw, 8).is_ok_and(|c| {
            c.section_id == section
                && c.semantic_copy_id == 0
                && c.section_type == 4
                && c.section_version == 0
                && c.fragment_index == 0
                && c.fragment_count == 1
                && c.section_envelope_length == 23
        })
    };
    let mut trace = [0; 12];
    let mut distinct = BTreeSet::new();
    let mut states = vec![];
    let mut present = 0;
    let mut identity = true;
    for (index, l) in lanes.iter().enumerate() {
        match l {
            None => states.push(0),
            Some(l) => {
                present += 1;
                match decode_eh_unit_fast(l, 8) {
                    Err(_) => states.push(1),
                    Ok(d) => {
                        states.push(if d.quality == crate::candidate::DecodeQuality::Verified {
                            2
                        } else {
                            3
                        });
                        trace[index] = classify(&d.common)?;
                        identity &= matches_identity(&d.common);
                        distinct.insert(d.common);
                    }
                }
            }
        }
    }
    let lane_count = distinct.len();
    let repetition = if lanes.len() > 1 {
        aggregate_repetition_observation(lanes).map_err(|_| SemanticError)?
    } else {
        None
    };
    let rep = repetition
        .as_ref()
        .and_then(|x| decode_eh_unit_fast(x, 8).ok());
    let rep_valid = rep.is_some();
    let equals = rep.as_ref().is_some_and(|d| distinct.contains(&d.common));
    if let Some(d) = rep {
        trace[5] = classify(&d.common)?;
        identity &= matches_identity(&d.common);
        distinct.insert(d.common);
    }
    identity &= !distinct.is_empty();
    let conflict = distinct.len() > 1;
    let accepted = identity && distinct.len() == 1;
    let row = [
        lanes.len() as u8,
        present,
        lane_count as u8,
        rep_valid as u8,
        equals as u8,
        identity as u8,
        accepted as u8,
        conflict as u8,
    ];
    let mut summary = [0u8; 9];
    let verified = states.contains(&2);
    for (i, x) in states.into_iter().enumerate().take(5) {
        summary[i] = x;
    }
    summary[5] = if rep_valid {
        3
    } else if repetition.is_some() {
        1
    } else {
        0
    };
    summary[6] = distinct.len() as u8;
    summary[7] = if conflict {
        4
    } else if distinct.len() == 1 {
        if verified { 2 } else { 3 }
    } else if present == 0 {
        0
    } else {
        1
    };
    summary[8] = u8::from(distinct.contains(a)) | u8::from(distinct.contains(b)) << 1;
    trace[6..].copy_from_slice(&[
        u8::from(present != 0),
        u8::from(verified),
        u8::from(identity),
        summary[8],
        summary[7],
        u8::from(accepted),
    ]);
    Ok((row, summary, trace))
}
fn tenth(raw: &[u8], a: [u8; 191], b: [u8; 191]) -> Result<()> {
    let mut out = vec![];
    let mut next = 1;
    for (section, fragment, f, r) in [(1, 0, 2, 5), (1, 1, 2, 5), (400, 0, 1, 5), (401, 0, 1, 2)] {
        longs(&mut out, &[section, fragment, f, r, next, next + r - 1]);
        next += r;
    }
    out.extend([0, 4, 8, 10, 12, 16, 18, 22]);
    let conflict = vec![
        Some(lane(a, &[])),
        Some(lane(b, &[0, 1])),
        Some(lane(b, &[2, 3])),
        Some(lane(b, &[4, 5])),
        Some(lane(b, &[6, 7])),
    ];
    let rep: Vec<_> = (0..5).map(|i| Some(lane(b, &[2 * i, 2 * i + 1]))).collect();
    let cases = vec![
        vec![None; 5],
        vec![Some(lane(b, &[0, 1]))],
        vec![Some(lane(a, &[]))],
        vec![Some(lane(a, &[])); 5],
        conflict.clone(),
        rep.clone(),
        vec![Some(lane(a, &[])), None],
        vec![Some(lane(a, &[])), Some(lane(b, &[]))],
        vec![Some(lane(a, &[]))],
    ];
    let mut traces = Vec::new();
    for (i, lanes) in cases.iter().enumerate() {
        let (row, _, trace) = group(lanes, if i == 8 { 401 } else { 400 }, &a, &b)?;
        out.extend(row);
        traces.extend(trace);
    }
    for (which, lanes) in [conflict, rep].iter().enumerate() {
        for i in 0..5 {
            if which == 0 && i == 0 {
                out.extend([1, 0, 0, 0, 0, 0]);
            } else {
                let start = if which == 0 { 2 * (i - 1) } else { 2 * i };
                out.extend([2, 2]);
                words(&mut out, &[start as u16, (start + 1) as u16]);
            }
        }
        out.extend(group(lanes, 400, &a, &b)?.1);
    }
    for length in [22u16, 157, 158, 314, 315] {
        let fragments = length.div_ceil(157);
        words(
            &mut out,
            &[length, fragments, length - 157 * (fragments - 1), length],
        );
    }
    need(out.len() == 294 && traces.len() == 108)?;
    out.extend(traces);
    let mut unknown = Vec::new();
    for first in [59u8, 60, 61, 62, 63] {
        out.extend([first, 5]);
        let mut observation = lane(a, &[]);
        for bit in first..first + 5 {
            observation.encoded[usize::from(bit) / 8] &= !(1 << (7 - bit % 8));
        }
        observation.erasures = (first..first + 5)
            .map(|bit| crate::candidate::EhErasure {
                codeword: 0,
                position: bit + 1,
            })
            .collect();
        unknown.push(Some(observation));
    }
    let (_, states, trace) = group(&unknown, 400, &a, &b)?;
    out.extend(trace);
    out.extend(&states[..6]);
    exact(raw, out)
}
fn graph(adjacency: u16, selected: u8) -> Option<u8> {
    fn visit(i: usize, a: u16, active: &mut u8, done: &mut u8) -> bool {
        let bit = 8 >> i;
        if *active & bit != 0 {
            return false;
        }
        if *done & bit != 0 {
            return true;
        }
        *active |= bit;
        for j in 0..4 {
            if a & (0x8000 >> (i * 4 + j)) != 0 && !visit(j, a, active, done) {
                return false;
            }
        }
        *active &= !bit;
        *done |= bit;
        true
    }
    let mut closure = 0;
    for i in 0..4 {
        if selected & (8 >> i) != 0 && !visit(i, adjacency, &mut 0, &mut closure) {
            return None;
        }
    }
    Some(closure)
}
// A complete neutral metadata witness lets the production v2 validator check
// individual ordinal claims without admitting an incomplete illustrative roster.
fn ordinal_witness(id: u16, ordinal: u16, present: bool) -> bool {
    let body_ids: Vec<u32> = (16..=18).chain(100..=163).chain(200..=210).collect();
    let mut entries = vec![];
    for sid in [1, 2, 3]
        .into_iter()
        .chain(body_ids.iter().copied())
        .chain([211])
    {
        let required = [1, 2, 3, 16, 17, 18].contains(&sid);
        entries.push(crate::InventoryEntry {
            section_id: sid,
            section_type: match sid {
                1 => 1,
                2 | 3 => 2,
                211 => 4,
                _ => 3,
            },
            section_version: if sid == 1 { 2 } else { 0 },
            closure_class: if required { 128 } else { 129 },
            check_id: 1,
            copy_count: 1,
            physical_replica_count: if required { 5 } else { 1 },
            dependencies: match sid {
                2 => vec![16, 17, 18],
                3 => body_ids.clone(),
                _ => vec![],
            },
            logical_payload_length: 1,
            game_ordinal: if (100..=163).contains(&sid) {
                Some((sid - 100) as u16)
            } else {
                None
            },
        });
    }
    entries[0].logical_payload_length = (8 + entries
        .iter()
        .map(|e| 20 + 4 * e.dependencies.len())
        .sum::<usize>()) as u32;
    let Some(entry) = entries.iter_mut().find(|e| e.section_id == u32::from(id)) else {
        return false;
    };
    entry.game_ordinal = if present { Some(ordinal) } else { None };
    crate::bootstrap_v2::encode_inventory(&crate::Inventory {
        inventory_version: 2,
        entries,
    })
    .is_ok()
}
fn eleventh(raw: &[u8], a: [u8; 191]) -> Result<()> {
    let mut out = vec![];
    layout(&mut out, &[(0, 2), (2, 2), (4, 2), (6, 2)]);
    layout(
        &mut out,
        &[
            (0, 4),
            (4, 2),
            (6, 2),
            (8, 1),
            (9, 1),
            (10, 1),
            (11, 1),
            (12, 2),
            (14, 4),
            (18, 2),
        ],
    );
    for r in [1, 2, 5] {
        for ordinal in [0, 1] {
            out.extend([r, ordinal, 2 * r + ordinal]);
        }
    }
    words(&mut out, &[1, 2, 0, 5, 1, 2, 3, 4, 5]);
    for bits in [
        "011111", "100000", "110000", "111011", "110100", "111101", "111100", "111110", "111111",
        "000000", "010101", "101111",
    ] {
        let x: Vec<u8> = bits.bytes().map(|b| b - b'0').collect();
        let required = x[0] & x[1] & x[3];
        let all = required & x[2] & x[4];
        out.extend(&x);
        out.extend([required, all, all & x[5]]);
    }
    for profile in [8u16, 7] {
        let mut changed = a;
        changed[..2].copy_from_slice(&profile.to_be_bytes());
        common_recheck(&mut changed);
        words(
            &mut out,
            &[profile, 8, 1, u16::from(checked_common(&changed))],
        );
    }
    words(&mut out, &[3]);
    for row in [[4, 2, 4], [10, 6, 2], [12, 8, 2]] {
        out.extend(row);
    }
    words(&mut out, &[7]);
    for row in [
        [2, 0, 4],
        [6, 4, 2],
        [8, 6, 2],
        [10, 8, 1],
        [11, 9, 1],
        [12, 12, 2],
        [14, 14, 4],
    ] {
        out.extend(row);
    }
    words(&mut out, &[2, 16, 17, 18]);
    for (adj, mask) in [(0x7000, 8), (0x4200, 8), (0, 4), (0x4800, 8)] {
        let result = graph(adj, mask);
        words(&mut out, &[adj]);
        out.extend([mask, result.unwrap_or(0), u8::from(result.is_some())]);
    }
    for (id, ordinal, has) in [(100u16, 0, 1), (163, 63, 1), (211, 65535, 0), (101, 0, 1)] {
        let admitted = if (100..=163).contains(&id) {
            has == 1 && ordinal == id - 100
        } else {
            id >= 211 && has == 0 && ordinal == 65535
        };
        need(ordinal_witness(id, ordinal, has == 1) == admitted)?;
        words(&mut out, &[id, ordinal, has, u16::from(admitted)]);
    }
    exact(raw, out)
}
fn frames(raw: &[u8]) -> Result<BTreeMap<u16, &[u8]>> {
    let mut at = 4;
    let mut out = BTreeMap::new();
    for _ in 0..u16_at(raw, 2)? {
        let n = 8 + u32_at(raw, at + 4)? as usize;
        let frame = take(raw, at, n)?;
        need(out.insert(u16_at(frame, 0)?, frame).is_none())?;
        at += n;
    }
    need(at == raw.len())?;
    Ok(out)
}
fn record_refs(p: &P) -> Vec<u16> {
    let mut ids = vec![];
    match p {
        P::Text(_) => {}
        P::AtomSchema { entries, .. } => ids.extend(entries.iter().map(|e| e.label_text_ref)),
        P::AtomVector {
            atom_schema_ref, ..
        }
        | P::Matrix {
            atom_schema_ref, ..
        } => ids.push(*atom_schema_ref),
        P::FieldSchema { fields } => {
            for f in fields {
                ids.push(f.name_text_ref);
                if f.storage == 1 {
                    ids.push(f.type_code);
                }
            }
        }
        P::Tuple {
            field_schema_ref,
            field_values,
        } => {
            ids.push(*field_schema_ref);
            for v in field_values {
                if let gb_content::FieldValue::RecordRefs(r) = v {
                    ids.extend(r);
                }
            }
        }
        P::RegionSet {
            surface_matrix_ref,
            regions,
        } => {
            ids.push(*surface_matrix_ref);
            ids.extend(regions.iter().map(|r| r.label_ref));
        }
        P::SemanticBinding {
            binding_class,
            argument,
            auxiliary,
            ..
        } => {
            ids.push(*argument);
            if *binding_class == 2 {
                ids.push(*auxiliary);
            }
        }
        P::OpaqueData {
            data_binding_ref, ..
        } => ids.push(*data_binding_ref),
        P::PredicateResult {
            predicate_binding_ref,
            subject_opaque_data_ref,
            result_atom_vector_ref,
        } => ids.extend([
            *predicate_binding_ref,
            *subject_opaque_data_ref,
            *result_atom_vector_ref,
        ]),
        P::Feedback {
            display_ref,
            predicate_result_ref,
            ..
        } => ids.extend([*display_ref, *predicate_result_ref]),
        P::PassiveTrace {
            presentation_ref,
            region_set_ref,
            resulting_presentation_ref,
            limitation_text_ref,
            expected_feedback_ref,
            expected_next_node_ref,
            ..
        } => ids.extend([
            *presentation_ref,
            *region_set_ref,
            *resulting_presentation_ref,
            *limitation_text_ref,
            *expected_feedback_ref,
            *expected_next_node_ref,
        ]),
        P::LessonNode {
            presentation_ref,
            region_set_ref,
            predicate_result_ref,
            passive_trace_ref,
            cases,
            default_feedback_ref,
            default_next_node_ref,
            ..
        } => {
            ids.extend([
                *presentation_ref,
                *region_set_ref,
                *predicate_result_ref,
                *passive_trace_ref,
                *default_feedback_ref,
                *default_next_node_ref,
            ]);
            for c in cases {
                ids.extend([c.feedback_ref, c.next_node_ref]);
            }
        }
        P::Root { entry_node_ref, .. } => ids.push(*entry_node_ref),
    }
    ids.retain(|id| *id != 0);
    ids
}
fn encode_records(records: &[Record]) -> Result<Vec<u8>> {
    gb_content::encode_content_v0(&gb_content::ContentAuthoringProjection::new(
        0,
        records.to_vec(),
    ))
    .map_err(|_| SemanticError)
}
fn pruned(records: Vec<Record>, root: u16) -> Result<Vec<u8>> {
    let by_id: BTreeMap<_, _> = records.into_iter().map(|r| (r.record_id(), r)).collect();
    let mut seen = BTreeSet::new();
    let mut pending = vec![root];
    while let Some(id) = pending.pop() {
        if seen.insert(id) {
            pending.extend(record_refs(by_id.get(&id).ok_or(SemanticError)?.payload()));
        }
    }
    encode_records(
        &by_id
            .into_iter()
            .filter(|(id, _)| seen.contains(id))
            .map(|(_, r)| r)
            .collect::<Vec<_>>(),
    )
}
fn role_witness(
    projection: &ContentProjection,
    role: u8,
    mode: u8,
    predicate: bool,
    trace: bool,
) -> Result<bool> {
    let packed = role == 5 && mode == 1;
    let node_id = if packed { 26 } else { 28 };
    let feedback = if packed {
        22
    } else if role == 4 {
        24
    } else {
        20
    };
    let mut records = vec![];
    for record in projection.records() {
        let mut p = record.payload().clone();
        match &mut p {
            P::LessonNode {
                role: r,
                answer_mode,
                predicate_result_ref,
                passive_trace_ref,
                cases,
                default_feedback_ref,
                default_next_node_ref,
                flags,
                ..
            } if record.record_id() == node_id => {
                *r = role;
                *answer_mode = mode;
                *predicate_result_ref = if predicate { 19 } else { 0 };
                *passive_trace_ref = if trace { 25 } else { 0 };
                *default_feedback_ref = feedback;
                *default_next_node_ref = if packed { node_id } else { 0 };
                *flags = u8::from(role == 4);
                if packed {
                    for c in cases {
                        c.next_node_ref = if c.case_class == 1 { 0 } else { node_id };
                    }
                } else {
                    cases.clear();
                }
            }
            P::LessonNode { .. } => continue,
            P::PassiveTrace {
                expected_outcome,
                expected_feedback_ref,
                expected_next_node_ref,
                limitation_text_ref,
                ..
            } => {
                *expected_outcome = if packed { 1 } else { 3 };
                *expected_feedback_ref = if packed { 21 } else { feedback };
                *expected_next_node_ref = 0;
                *limitation_text_ref = if role == 4 { 5 } else { 0 };
            }
            P::Root {
                entry_node_ref,
                global_event_budget,
            } => {
                *entry_node_ref = node_id;
                *global_event_budget = 8;
            }
            _ => {}
        }
        records.push(Record::authoring(record.record_id(), p));
    }
    Ok(pruned(records, 29).is_ok())
}
fn miniature(raw: &[u8]) -> Result<()> {
    need(u32_at(raw, 0)? == 575 && u32_at(raw, 579)? == 1056 && raw.len() == 1639)?;
    let mini = take(raw, 4, 575)?;
    let projection = gb_content::stream_validation(mini).map_err(|_| SemanticError)?;
    need(projection.records().len() == 29 && projection.root_record_id() == 29)?;
    let s = &raw[583..];
    let mut at = 0;
    need(u16_at(s, at)? == 48)?;
    at += 2;
    for _ in 0..48 {
        let offset = u16_at(s, at)? as usize;
        let width = u16_at(s, at + 2)? as usize;
        let old = u32_at(s, at + 4)?;
        let new = u32_at(s, at + 8)?;
        let accepted = u16_at(s, at + 12)?;
        need(matches!(width, 1 | 2 | 4) && accepted <= 1)?;
        need(width == 4 || (old < 1 << (width * 8) && new < 1 << (width * 8)))?;
        need(take(mini, offset, width)? == &old.to_be_bytes()[4 - width..])?;
        let mut changed = mini.to_vec();
        changed[offset..offset + width].copy_from_slice(&new.to_be_bytes()[4 - width..]);
        need(u16::from(gb_content::stream_validation(&changed).is_ok()) == accepted)?;
        at += 14;
    }
    need(u16_at(s, at)? == 6)?;
    at += 2;
    let roles = [
        (1, 3, 1, 1, 0, 0, 0, 1, 1, 3),
        (2, 3, 1, 1, 0, 0, 0, 1, 1, 3),
        (3, 3, 1, 1, 0, 0, 1, 1, 1, 3),
        (4, 3, 0, 0, 0, 0, 0, 1, 5, 3),
        (5, 1, 1, 1, 1, 4096, 1, 1, 3, 2),
        (5, 2, 0, 0, 0, 0, 0, 0, 1, 3),
    ];
    for (role, mode, pmin, pmax, cmin, cmax, tmin, tmax, feedback, outcome) in roles {
        let mut expected = vec![role, mode, pmin, pmax];
        words(&mut expected, &[cmin, cmax]);
        expected.extend([tmin, tmax, feedback, outcome]);
        need(take(s, at, 12)? == expected)?;
        for trace in tmin..=tmax {
            need(role_witness(
                &projection,
                role,
                mode,
                pmin == 1,
                trace == 1,
            )?)?;
        }
        need(!role_witness(
            &projection,
            role,
            mode,
            pmin != 1,
            tmin == 1,
        )?)?;
        at += 12;
    }
    need(u16_at(s, at)? == 4)?;
    at += 2;
    for index in 0..4 {
        let row = take(s, at, 12)?;
        let expected = match index {
            0 => [6, 14, 12, 1, 1, 1],
            1 => [6, 14, 12, 2, 2, 0],
            2 => [4, 12, 12, 1, 1, 1],
            _ => [6, 14, 12, 0, 0, 0],
        };
        for (i, n) in expected.iter().enumerate() {
            need(u16_at(row, 2 * i)? == *n)?;
        }
        let mut records = vec![];
        for record in projection.records() {
            let mut p = record.payload().clone();
            match &mut p {
                P::FieldSchema { fields } if record.record_id() == 13 && matches!(index, 1 | 3) => {
                    if index == 1 {
                        fields.last_mut().ok_or(SemanticError)?.count = 2;
                    } else {
                        fields.pop();
                    }
                }
                P::Tuple { field_values, .. }
                    if record.record_id() == 14 && matches!(index, 1 | 3) =>
                {
                    if index == 1 {
                        *field_values.last_mut().ok_or(SemanticError)? =
                            gb_content::FieldValue::RecordRefs(vec![12, 12]);
                    } else {
                        field_values.pop();
                    }
                }
                P::LessonNode {
                    presentation_ref, ..
                } if record.record_id() == 28 && index == 2 => *presentation_ref = 12,
                _ => {}
            }
            records.push(Record::authoring(record.record_id(), p));
        }
        need(u16::from(encode_records(&records).is_ok()) == expected[5])?;
        at += 12;
    }
    need(u16_at(s, at)? == 8)?;
    at += 2;
    for _ in 0..8 {
        let row = take(s, at, 32)?;
        let node = u16_at(row, 0)?;
        let count = row[2] as usize;
        need(
            (26..=28).contains(&node)
                && count <= 3
                && row[18] <= 2
                && row[3 + count * 4..15].iter().all(|b| *b == 0),
        )?;
        let mut state = gb_content::new_run(&projection);
        for expected in 26..node {
            need(state.current_node_id() == expected)?;
            state = gb_content::step(&projection, state, &[3, 0, 0, 0]).0;
            state =
                gb_content::advance_committed(&projection, &state).map_err(|_| SemanticError)?;
        }
        let mut last = 0;
        for action in row[3..3 + count * 4].chunks_exact(4) {
            (state, last) = gb_content::step(&projection, state, action);
        }
        let view = gb_content::run_state_view(&state);
        let shape = match projection
            .records()
            .iter()
            .find(|r| r.record_id() == node)
            .ok_or(SemanticError)?
            .payload()
        {
            P::LessonNode { response_shape, .. } => *response_shape,
            _ => return Err(SemanticError),
        };
        let selections = if view.phase() == 2 {
            let response = view.committed_response();
            need(response.len() >= 3)?;
            let n = u16_at(response, 1)? as usize;
            need(response.len() == 3 + n * 2)?;
            (0..n)
                .map(|i| u16_at(response, 3 + i * 2))
                .collect::<Result<Vec<_>>>()?
        } else {
            view.selection_buffer().to_vec()
        };
        let mut expected = vec![];
        words(&mut expected, &[node]);
        expected.push(count as u8);
        expected.extend_from_slice(&row[3..15]);
        expected.extend([view.phase(), last, shape, selections.len() as u8]);
        for i in 0..2 {
            words(&mut expected, &[selections.get(i).copied().unwrap_or(0)]);
        }
        expected.push(view.outcome());
        words(
            &mut expected,
            &[
                view.feedback_ref(),
                view.next_node_ref(),
                view.global_remaining(),
                view.local_remaining(),
            ],
        );
        need(row == expected)?;
        at += 32;
    }
    need(at == s.len())
}
fn position_local(raw: &[u8]) -> Result<()> {
    need(raw.len() == 408 && u16_at(raw, 0)? == 2)?;
    let mut expected = vec![];
    layout(&mut expected, &[(0, 64), (64, 1), (65, 1), (66, 1)]);
    need(take(raw, 2, 18)? == expected)?;
    need(
        u16_at(raw, 20)? == 0
            && u16_at(raw, 22)? != 0
            && u16_at(raw, 24)? == 67
            && u16_at(raw, 26)? == 9,
    )?;
    let mut expected = vec![];
    for row in [
        [204, 0, 8],
        [177, 8, 8],
        [150, 16, 8],
        [123, 24, 8],
        [96, 32, 8],
        [69, 40, 8],
        [42, 48, 8],
        [15, 56, 8],
        [258, 64, 3],
    ] {
        words(&mut expected, &row);
    }
    need(take(raw, 28, 54)? == expected)?;
    for at in [82, 229] {
        let bytes = take(raw, at, 67)?;
        let p = gb_chess::decode_position(bytes).map_err(|_| SemanticError)?;
        need(gb_chess::encode_position(&p) == bytes)?;
        gb_chess::validate_local(&p).map_err(|_| SemanticError)?;
    }
    need(
        u16_at(raw, 149)? == 1
            && u16_at(raw, 151)? != 0
            && u16_at(raw, 153)? == 22
            && u16_at(raw, 155)? == 68
            && u16_at(raw, 157)? == 23
            && u16_at(raw, 159)? == 67
            && raw[161] == 1
            && raw[162..229] == raw[229..296],
    )?;
    let mut expected = vec![];
    layout(&mut expected, &[(10, 6), (4, 6), (1, 3), (0, 1)]);
    need(take(raw, 296, 18)? == expected && u16_at(raw, 314)? == 12)?;
    for index in 0..12 {
        let row = take(raw, 316 + index * 6, 6)?;
        let wire = u16_at(row, 0)?;
        let decoded = gb_chess::decode_move(&wire.to_be_bytes());
        need(
            row[2] == (wire >> 10) as u8
                && row[3] == ((wire >> 4) & 63) as u8
                && row[4] == ((wire >> 1) & 7) as u8
                && row[5] == u8::from(decoded.is_ok()),
        )?;
        if let Ok(m) = decoded {
            need(gb_chess::encode_move(m) == wire.to_be_bytes())?;
        }
        if index < 8 {
            need(wire == 0xc790 + 2 * index as u16)?;
        }
    }
    for (i, value) in [(8, 0x1950), (9, 0xe6a0), (10, 0x31c1), (11, 0x30c0)] {
        need(u16_at(raw, 316 + i * 6)? == value)?;
    }
    let first = gb_chess::decode_move(&0x31c0u16.to_be_bytes()).map_err(|_| SemanticError)?;
    let replay = gb_chess::replay_from_start(&[first]).map_err(|_| SemanticError)?;
    need(gb_chess::encode_position(replay.position()) == raw[82..149])?;
    need(u16_at(raw, 388)? == 1 && u16_at(raw, 390)? != 0 && u16_at(raw, 392)? == 69)?;
    let mut expected = vec![];
    layout(&mut expected, &[(0, 2), (2, 66), (68, 1)]);
    need(take(raw, 394, 14)? == expected)
}
fn twelfth(raw: &[u8]) -> Result<()> {
    for i in 0..3 {
        need(
            u16_at(raw, i * 6)? == i as u16
                && u16_at(raw, i * 6 + 2)? > 0
                && u16_at(raw, i * 6 + 4)? > 0,
        )?;
    }
    need(u16_at(raw, 14)? == 29 && u16_at(raw, 16)? == 29)?;
    let mut expected = vec![];
    for fields in [
        &[(0, 2), (2, 2)][..],
        &[(0, 2), (2, 2), (4, 4)],
        &[(0, 1), (1, 1), (2, 2), (4, 2), (6, 2), (8, 2)],
        &[(0, 2), (2, 2)],
        &[(0, 2)],
        &[
            (0, 2),
            (2, 1),
            (3, 1),
            (4, 2),
            (6, 2),
            (8, 4),
            (12, 2),
            (14, 4),
            (18, 4),
        ],
    ] {
        layout(&mut expected, fields);
    }
    for (i, (n, fixed)) in [
        (1, 0),
        (5, 0),
        (4, 0),
        (7, 0),
        (10, 0),
        (3, 0),
        (18, 0),
        (10, 1),
        (3, 0),
        (6, 1),
        (6, 1),
        (20, 0),
        (22, 0),
        (4, 1),
    ]
    .iter()
    .enumerate()
    {
        words(&mut expected, &[(i + 1) as u16, *n, *fixed]);
    }
    need(take(raw, 18, 188)? == expected)?;
    miniature(take(raw, 206, 1639)?)?;
    for i in 0..10 {
        let r = take(raw, 1845 + i * 8, 8)?;
        need(u16_at(r, 0)? > 0 && u16_at(r, 6)? <= 14)?;
    }
    let mut expected = vec![];
    for row in [[3, 5, 8], [3, 5, 7], [8, 1, 9], [8, 1, 8]] {
        words(&mut expected, &row);
    }
    need(take(raw, 1925, 24)? == expected)?;
    for i in 0..2 {
        let frame = take(raw, 1949 + i * 18, 18)?;
        need(
            u16_at(frame, 0)? > 0
                && u16_at(frame, 2)? == 8
                && u32_at(frame, 4)? == 10
                && frame[8] == 1
                && frame[9] == 0
                && u16_at(frame, 10)? == 2 + i as u16
                && u16_at(frame, 12)? == 1,
        )?;
        let reference = u16_at(raw, 1985 + i * 2)?;
        let row = take(raw, 1989 + i * 12, 12)?;
        need(u32_at(row, 0)? == if i == 0 { 100 } else { 200 })?;
        need(
            u16_at(row, 4)? == u16_at(frame, 0)?
                && reference == u16_at(frame, 0)?
                && u16_at(row, 6)? > reference
                && u16_at(row, 8)? == 2 + i as u16
                && u16_at(row, 10)? == 1,
        )?;
    }
    need(
        u16_at(raw, 2013 + 151)? == u16_at(raw, 1989 + 12 + 6)?
            && u16_at(raw, 2013 + 390)? == u16_at(raw, 1989 + 6)?,
    )?;
    position_local(take(raw, 2013, 408)?)
}
/// Reparse the immutable input bytes; cached logical package fields are not trusted.
pub fn validate_definitions(
    values: &[&[u8]],
    package: &RecipePackageV1,
) -> Result<ContextCommitments> {
    const WIDTHS: [usize; 12] = [16, 64, 96, 296, 226, 210, 636, 544, 464, 430, 314, 2421];
    need(values.len() == 12)?;
    for (value, width) in values.iter().zip(WIDTHS) {
        need(value.len() == width)?;
    }
    let package = decode_recipe_package_v1(&package.encoded, 8).map_err(|_| SemanticError)?;
    first_six(values, &package)?;
    let (a, b) = seventh_eighth(values)?;
    ninth(values[8], &package)?;
    tenth(values[9], a, b)?;
    eleventh(values[10], a)?;
    twelfth(values[11])?;
    Ok(ContextCommitments {
        fact12: values[11].to_vec(),
    })
}
fn check_context<'a>(
    raw: &'a [u8],
    context: usize,
    commitments: &[u8],
) -> Result<(ContentProjection, BTreeMap<u16, &'a [u8]>)> {
    let projection = gb_content::stream_validation(raw).map_err(|_| SemanticError)?;
    need(
        projection.records().len() == u16_at(commitments, context * 6 + 2)? as usize
            && projection.root_record_id() == u16_at(commitments, context * 6 + 4)?,
    )?;
    Ok((projection, frames(raw)?))
}
fn required_claims(raw: &[u8], c: &[u8]) -> Result<()> {
    let (projection, frames) = check_context(raw, 0, c)?;
    need(
        projection
            .records()
            .iter()
            .take(12)
            .map(Record::kind)
            .eq([2, 3, 4, 7, 8, 9, 8, 10, 4, 11, 12, 13]),
    )?;
    let root = projection.root_record_id();
    let last = frames
        .get(&12)
        .ok_or(SemanticError)?
        .len()
        .checked_sub(10)
        .ok_or(SemanticError)?;
    let sources = [
        (5, 6, false),
        (5, 8, true),
        (7, 6, false),
        (7, 8, false),
        (6, 0, false),
        (3, 0, false),
        (10, 2, false),
        (12, last, false),
        (root, 0, false),
        (root, 2, true),
    ];
    let mut expected = vec![];
    for (owner, offset, scalar) in sources {
        let frame = frames.get(&owner).ok_or(SemanticError)?;
        let value = u16_at(&frame[8..], offset)?;
        let kind = if scalar {
            0
        } else {
            u16_at(frames.get(&value).ok_or(SemanticError)?, 2)?
        };
        if !scalar {
            if owner == 12 {
                need(value > owner && kind == 13)?;
            } else {
                need(value < owner)?;
            }
        }
        words(&mut expected, &[owner, offset as u16, value, kind]);
    }
    need(take(c, 1845, 80)? == expected)?;
    let suffix = &c[2013..];
    let id = u16_at(suffix, 22)?;
    let p = projection
        .records()
        .iter()
        .find(|r| r.record_id() == id)
        .ok_or(SemanticError)?;
    let P::Matrix {
        rows,
        columns,
        cells,
        ..
    } = p.payload()
    else {
        return Err(SemanticError);
    };
    need(*rows == 20 && *columns == 27)?;
    let mut position = [0u8; 67];
    let mut covered = [false; 67];
    for i in 0..9 {
        let source = u16_at(suffix, 28 + i * 6)? as usize;
        let destination = u16_at(suffix, 30 + i * 6)? as usize;
        let count = u16_at(suffix, 32 + i * 6)? as usize;
        for j in 0..count {
            let value = *cells.get(source + j).ok_or(SemanticError)?;
            need(value <= 255 && destination + j < 67 && !covered[destination + j])?;
            position[destination + j] = value as u8;
            covered[destination + j] = true;
        }
    }
    need(covered.into_iter().all(|b| b) && position == suffix[82..149])
}
fn opaque(projection: &ContentProjection, id: u16) -> Result<Vec<u8>> {
    match projection
        .records()
        .iter()
        .find(|r| r.record_id() == id)
        .ok_or(SemanticError)?
        .payload()
    {
        P::OpaqueData { data, .. } => data
            .iter()
            .map(|v| u8::try_from(*v).map_err(|_| SemanticError))
            .collect(),
        _ => Err(SemanticError),
    }
}
fn moves(raw: &[u8]) -> Result<Vec<gb_chess::Move>> {
    need(raw.len() % 2 == 0 && raw.len() <= 16384)?;
    raw.chunks_exact(2)
        .map(|r| gb_chess::decode_move(r).map_err(|_| SemanticError))
        .collect()
}
fn all_claims(raw: &[u8], c: &[u8], bodies: &BTreeMap<u32, Vec<u8>>) -> Result<bool> {
    let (projection, frames) = check_context(raw, 1, c)?;
    let suffix = &c[2013..];
    let mut bodies_complete = true;
    for i in 0..2 {
        let carried = take(c, 1949 + i * 18, 18)?;
        let row = take(c, 1989 + i * 12, 12)?;
        let sid = u32_at(row, 0)?;
        let binding = u16_at(row, 4)?;
        let subject = u16_at(row, 6)?;
        need(*frames.get(&binding).ok_or(SemanticError)? == carried)?;
        let oframe = frames.get(&subject).ok_or(SemanticError)?;
        need(u16_at(oframe, 2)? == 9 && u16_at(oframe, 8)? == binding)?;
        if let Some(body) = bodies.get(&sid) {
            let mut exact = carried.to_vec();
            exact.extend_from_slice(oframe);
            need(body.len() <= 16384 && *body == exact)?;
        } else {
            bodies_complete = false;
        }
    }
    let game = opaque(&projection, u16_at(suffix, 390)?)?;
    need(
        game.len() == u16_at(suffix, 392)? as usize && game.len() == 69 && u16_at(&game, 0)? == 33,
    )?;
    let game_moves = moves(&game[2..68])?;
    let score = gb_chess::Score::from_code(game[68]).ok_or(SemanticError)?;
    gb_chess::validate_source_record(&game_moves, score).map_err(|_| SemanticError)?;
    need(
        gb_chess::encode_move(game_moves[0]) == 0x31c0u16.to_be_bytes()
            && gb_chess::encode_move(game_moves[2]) == u16_at(suffix, 316 + 8 * 6)?.to_be_bytes()
            && gb_chess::encode_move(game_moves[3]) == u16_at(suffix, 316 + 9 * 6)?.to_be_bytes(),
    )?;
    let replay = gb_chess::replay_from_start(&game_moves[..1]).map_err(|_| SemanticError)?;
    need(gb_chess::encode_position(replay.position()) == suffix[82..149])?;
    let fixture = opaque(&projection, u16_at(suffix, 151)?)?;
    need(fixture.len() == 90 && fixture[0] == 0 && fixture[1] == 1)?;
    let prior_len = u16_at(&fixture, 2)? as usize;
    need(prior_len == 12)?;
    let prior = moves(take(&fixture, 4, prior_len)?)?;
    let subject_at = 4 + prior_len;
    let subject_len = u16_at(&fixture, subject_at)? as usize;
    need(subject_len == 2)?;
    let subject = moves(take(&fixture, subject_at + 2, subject_len)?)?;
    let expected_at = subject_at + 2 + subject_len;
    let expected_len = u16_at(&fixture, expected_at)? as usize;
    need(expected_len == 68 && expected_at + 2 + expected_len == fixture.len())?;
    let pre = gb_chess::replay_from_start(&prior).map_err(|_| SemanticError)?;
    let post = gb_chess::apply_move(&pre, subject[0]).map_err(|_| SemanticError)?;
    need(gb_chess::encode_position(post.position()) == suffix[229..296])?;
    need(
        take(&fixture, u16_at(suffix, 153)? as usize, 68)? == &suffix[161..229]
            && take(&fixture, u16_at(suffix, 157)? as usize, 67)? == &suffix[229..296],
    )?;
    // Promotion field examples also bind to recovered namespace-3 subjects.
    for promotion in 1..=4u16 {
        let binding=projection.records().iter().find(|r|matches!(r.payload(),P::SemanticBinding{binding_class:1,namespace_id:3,semantic_code,..} if *semantic_code==promotion+3)).ok_or(SemanticError)?.record_id();
        let subject_id=projection.records().iter().find(|r|matches!(r.payload(),P::OpaqueData{data_binding_ref,..} if *data_binding_ref==binding)).ok_or(SemanticError)?.record_id();
        let payload = opaque(&projection, subject_id)?;
        need(
            payload.len() <= 16384
                && payload.len() >= 8
                && payload[0] == 0
                && payload[1] == (promotion + 3) as u8,
        )?;
        let n = u16_at(&payload, 2)? as usize;
        let prior = moves(take(&payload, 4, n)?)?;
        let at = 4 + n;
        need(u16_at(&payload, at)? == 2)?;
        let wire = u16_at(&payload, at + 2)?;
        need(wire == u16_at(suffix, 316 + usize::from(promotion) * 6)?)?;
        let result_at = at + 4;
        let result_len = u16_at(&payload, result_at)? as usize;
        need(result_len > 0 && result_at + 2 + result_len == payload.len())?;
        let pre = gb_chess::replay_from_start(&prior).map_err(|_| SemanticError)?;
        let mv = gb_chess::decode_move(&wire.to_be_bytes()).map_err(|_| SemanticError)?;
        gb_chess::apply_move(&pre, mv).map_err(|_| SemanticError)?;
        if promotion == 1 {
            let no_promotion = gb_chess::decode_move(&u16_at(suffix, 316)?.to_be_bytes())
                .map_err(|_| SemanticError)?;
            need(gb_chess::apply_move(&pre, no_promotion).is_err())?;
        }
    }
    Ok(bodies_complete)
}
impl ContextCommitments {
    /// Content availability is unchanged by this evidence-only comparison.
    pub fn prove_recovered(
        &self,
        required: Option<&[u8]>,
        all: Option<&[u8]>,
        bodies: &BTreeMap<u32, Vec<u8>>,
    ) -> ContextProof {
        let required = match required {
            None => ContextState::Unresolved,
            Some(raw) => {
                if required_claims(raw, &self.fact12).is_ok() {
                    ContextState::Consistent
                } else {
                    ContextState::Contradiction
                }
            }
        };
        let all = match all {
            None => ContextState::Unresolved,
            Some(raw) => match all_claims(raw, &self.fact12, bodies) {
                Ok(true) => ContextState::Consistent,
                Ok(false) => ContextState::Unresolved,
                Err(_) => ContextState::Contradiction,
            },
        };
        ContextProof { required, all }
    }
}
