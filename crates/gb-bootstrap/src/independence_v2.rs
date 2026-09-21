//! Complete nine-row wrapper over fresh physical and actual-recovery premises.
//! Retained damage admission is not a fresh damage execution or a gate receipt.
use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum IndependenceV2Error {
    Input,
    Binding,
    Arithmetic,
    Damage,
    Physical,
    Recovery,
}
pub type Result<T> = std::result::Result<T, IndependenceV2Error>;
impl std::fmt::Display for IndependenceV2Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "independence-v2: {self:?}")
    }
}
impl std::error::Error for IndependenceV2Error {}

/// Retains the freshly computed premises for a later producer to publish.
/// Construction is private; no saved premise can manufacture this value.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct IndependenceProofV2 {
    raw: Vec<u8>,
    passed: bool,
    physical: crate::physical_v2::PhysicalEvidenceV2,
    recovery: crate::recovery_provenance_v2::RecoveryProvenanceV2,
    damage_manifest: Vec<u8>,
}
impl IndependenceProofV2 {
    pub fn canonical_bytes(&self) -> &[u8] {
        &self.raw
    }
    pub fn passed(&self) -> bool {
        self.passed
    }
    pub fn physical_evidence(&self) -> &crate::physical_v2::PhysicalEvidenceV2 {
        &self.physical
    }
    pub fn recovery_provenance(&self) -> &crate::recovery_provenance_v2::RecoveryProvenanceV2 {
        &self.recovery
    }
    pub fn damage_manifest(&self) -> &[u8] {
        &self.damage_manifest
    }
}

/// Strictly admit the complete damage tree, then freshly enumerate physical
/// predicates and recover the actual carrier. The producer remains responsible
/// for fresh full damage execution and the surrounding gate order.
pub fn build_complete_independence_v2(
    input: crate::recovery_provenance_v2::RecoveryProvenanceInputs<'_>,
    static_projection: &crate::static_v2::StaticProjectionV2,
    corpus: &crate::damage_corpus_v2::DamageCorpusV2,
    read: impl FnMut(&str) -> crate::complete_damage_v2::Result<Vec<u8>>,
    names: &[String],
) -> Result<IndependenceProofV2> {
    for (name, raw) in [
        ("candidate-manifest.json", input.candidate_manifest),
        ("capacity-ledger.json", input.capacity_ledger),
        ("ownership-ledger.json", input.ownership_ledger),
        ("semantic-envelope.json", input.semantic_envelope),
    ] {
        need(static_projection.document(name) == Some(raw))?;
    }
    let damage =
        crate::complete_damage_v2::admit_complete_damage_v2(static_projection, corpus, read, names)
            .map_err(|_| IndependenceV2Error::Damage)?;
    let physical = crate::physical_v2::build_physical_evidence_v2(
        input.candidate_manifest,
        input.capacity_ledger,
        input.ownership_ledger,
        input.semantic_envelope,
    )
    .map_err(|_| IndependenceV2Error::Physical)?;
    let recovery = crate::recovery_provenance_v2::build_recovery_provenance_v2(input)
        .map_err(|_| IndependenceV2Error::Recovery)?;
    let mut counts = [0u64; 8];
    for (i, count) in counts.iter_mut().enumerate() {
        *count = corpus
            .case_count(&format!("D{i}"))
            .map_err(|_| IndependenceV2Error::Damage)?;
    }
    finish(physical, recovery, damage.root_bytes().to_vec(), &counts)
}

pub fn validate_complete_independence_v2(
    raw: &[u8],
    input: crate::recovery_provenance_v2::RecoveryProvenanceInputs<'_>,
    static_projection: &crate::static_v2::StaticProjectionV2,
    corpus: &crate::damage_corpus_v2::DamageCorpusV2,
    read: impl FnMut(&str) -> crate::complete_damage_v2::Result<Vec<u8>>,
    names: &[String],
) -> Result<()> {
    parse(raw)?;
    need(
        build_complete_independence_v2(input, static_projection, corpus, read, names)?
            .canonical_bytes()
            == raw,
    )
}
fn identity(raw: &[u8]) -> V {
    o([
        ("bytes", V::U64(raw.len() as u64)),
        ("sha256", s(&format!("{:x}", Sha256::digest(raw)))),
    ])
}
fn parse(raw: &[u8]) -> Result<V> {
    need(!raw.is_empty() && raw.len() <= 1_048_576)?;
    validate_canonical_manifest(raw).map_err(|_| IndependenceV2Error::Input)
}
fn finish(
    physical: crate::physical_v2::PhysicalEvidenceV2,
    recovery: crate::recovery_provenance_v2::RecoveryProvenanceV2,
    damage_manifest: Vec<u8>,
    counts: &[u64; 8],
) -> Result<IndependenceProofV2> {
    let p = parse(physical.canonical_bytes())?;
    let p = object(&p)?;
    let damage = parse(&damage_manifest)?;
    let mut rows = array(field(p, "predicate_rows")?)?.to_vec();
    need(rows.len() == 8)?;
    rows.push(damage_row(counts, &damage)?);
    let outcomes = rows
        .iter()
        .map(|r| passed(field(object(r)?, "result")?))
        .collect::<Result<Vec<_>>>()?;
    let passed = outcomes.into_iter().all(|v| v);
    let value = o([
        ("schema", s("golden-board.m2-independence-proof/v2")),
        ("profile_id", s("eh72-hier-r5-r2-r1-lzss-crc32c-v1")),
        ("input_sha256", field(p, "input_sha256")?.clone()),
        ("physical_evidence", identity(physical.canonical_bytes())),
        ("recovery_provenance", identity(recovery.canonical_bytes())),
        ("knowledge_use", identity(recovery.knowledge_use())),
        ("first_use", identity(recovery.first_use())),
        ("damage_manifest", identity(&damage_manifest)),
        ("predicate_rows", V::Array(rows)),
        ("result", s(if passed { "pass" } else { "fail" })),
    ]);
    let raw = serialize_manifest(&value).map_err(|_| IndependenceV2Error::Input)?;
    Ok(IndependenceProofV2 {
        raw,
        passed,
        physical,
        recovery,
        damage_manifest,
    })
}
fn object(v: &V) -> Result<&BTreeMap<String, V>> {
    if let V::Object(v) = v {
        Ok(v)
    } else {
        Err(IndependenceV2Error::Input)
    }
}
fn array(v: &V) -> Result<&[V]> {
    if let V::Array(v) = v {
        Ok(v)
    } else {
        Err(IndependenceV2Error::Input)
    }
}
fn field<'a>(v: &'a BTreeMap<String, V>, k: &str) -> Result<&'a V> {
    v.get(k).ok_or(IndependenceV2Error::Input)
}
fn integer(v: &V) -> Result<u64> {
    if let V::U64(v) = v {
        Ok(*v)
    } else {
        Err(IndependenceV2Error::Input)
    }
}
fn string(v: &V) -> Result<&str> {
    if let V::String(v) = v {
        Ok(v)
    } else {
        Err(IndependenceV2Error::Input)
    }
}
fn passed(v: &V) -> Result<bool> {
    match string(v)? {
        "pass" => Ok(true),
        "fail" => Ok(false),
        _ => Err(IndependenceV2Error::Input),
    }
}
fn need(ok: bool) -> Result<()> {
    if ok {
        Ok(())
    } else {
        Err(IndependenceV2Error::Binding)
    }
}
fn o(rows: impl IntoIterator<Item = (&'static str, V)>) -> V {
    V::Object(rows.into_iter().map(|(k, v)| (k.into(), v)).collect())
}
fn s(v: &str) -> V {
    V::String(v.into())
}
fn damage_row(counts: &[u64; 8], root: &V) -> Result<V> {
    let rows = array(field(object(root)?, "family_rows")?)?;
    need(rows.len() == 8 && counts.iter().all(|n| *n > 0))?;
    let mut total = 0u64;
    let mut violations = 0u64;
    for (i, (raw, expected)) in rows.iter().zip(counts).enumerate() {
        let row = object(raw)?;
        need(
            row.len() == 7
                && [
                    "family_id",
                    "case_count",
                    "wrong_accept_count",
                    "result",
                    "path",
                    "bytes",
                    "sha256",
                ]
                .iter()
                .all(|k| row.contains_key(*k)),
        )?;
        need(
            string(field(row, "family_id")?)? == format!("D{i}")
                && integer(field(row, "case_count")?)? == *expected,
        )?;
        total = total
            .checked_add(*expected)
            .ok_or(IndependenceV2Error::Arithmetic)?;
        if !passed(field(row, "result")?)? {
            violations = violations
                .checked_add(*expected)
                .ok_or(IndependenceV2Error::Arithmetic)?;
        }
    }
    Ok(o([
        ("predicate_id", s("damage-promise-binding")),
        ("witness_count", V::U64(total)),
        ("minimum_surviving_count", V::U64(1)),
        ("violation_count", V::U64(violations)),
        (
            "result",
            s(if total > 0 && violations == 0 {
                "pass"
            } else {
                "fail"
            }),
        ),
    ]))
}

#[cfg(test)]
mod tests {
    use super::*;
    const COUNTS: [u64; 8] = [16, 4, 256, 128, 1908, 21, 7632, 415];
    fn fixture(failed: &[usize]) -> V {
        // Local arithmetic fixture, never a retained-tree admission or producer.
        let rows = COUNTS
            .iter()
            .enumerate()
            .map(|(i, n)| {
                V::Object(BTreeMap::from([
                    ("family_id".into(), V::String(format!("D{i}"))),
                    ("case_count".into(), V::U64(*n)),
                    ("wrong_accept_count".into(), V::U64(0)),
                    (
                        "result".into(),
                        V::String(if failed.contains(&i) { "fail" } else { "pass" }.into()),
                    ),
                    (
                        "path".into(),
                        V::String(format!("damage/D{i}/manifest.json")),
                    ),
                    ("bytes".into(), V::U64(1)),
                    ("sha256".into(), V::String("0".repeat(64))),
                ]))
            })
            .collect();
        V::Object(BTreeMap::from([
            ("family_rows".into(), V::Array(rows)),
            // These classes cannot add a ninth-row witness or dilute violations.
            ("reauthored_boundary".into(), V::U64(u64::MAX)),
            ("boundary_kats".into(), V::U64(u64::MAX)),
        ]))
    }
    fn number(row: &V, key: &str) -> u64 {
        if let V::Object(r) = row {
            if let V::U64(n) = r[key] {
                return n;
            }
        }
        panic!()
    }
    #[test]
    fn ninth_row_counts_only_accidental_cases() {
        let row = damage_row(&COUNTS, &fixture(&[])).unwrap();
        assert_eq!(number(&row, "witness_count"), 10380);
        assert_eq!(number(&row, "violation_count"), 0);
        assert_eq!(number(&row, "minimum_surviving_count"), 1);
        let V::Object(row) = row else { panic!() };
        assert_eq!(row.len(), 5);
        assert_eq!(row["result"], V::String("pass".into()));
    }
    #[test]
    fn failed_family_counts_all_witnesses_including_d7_kat_failure() {
        assert_eq!(
            number(
                &damage_row(&COUNTS, &fixture(&[7])).unwrap(),
                "violation_count"
            ),
            415
        );
        let row = damage_row(&COUNTS, &fixture(&[4, 7])).unwrap();
        assert_eq!(number(&row, "violation_count"), 2323);
        let V::Object(row) = row else { panic!() };
        assert_eq!(row["result"], V::String("fail".into()));
        assert_eq!(
            number(
                &damage_row(&COUNTS, &fixture(&(0..8).collect::<Vec<_>>())).unwrap(),
                "violation_count"
            ),
            10380
        );
    }
    #[test]
    fn malformed_family_domain_cannot_change_witnesses() {
        for bad in [V::U64(414), V::Bool(true), V::U64(u64::MAX)] {
            let mut root = fixture(&[]);
            let V::Object(ref mut root) = root else {
                panic!()
            };
            let V::Array(rows) = root.get_mut("family_rows").unwrap() else {
                panic!()
            };
            let V::Object(row) = &mut rows[7] else {
                panic!()
            };
            row.insert("case_count".into(), bad);
            assert!(damage_row(&COUNTS, &V::Object(root.clone())).is_err());
        }
        let mut root = fixture(&[]);
        let V::Object(ref mut o) = root else { panic!() };
        let V::Array(rows) = o.get_mut("family_rows").unwrap() else {
            panic!()
        };
        rows.swap(0, 1);
        assert!(damage_row(&COUNTS, &root).is_err());
        assert!(damage_row(&[0; 8], &fixture(&[])).is_err());
    }
}
