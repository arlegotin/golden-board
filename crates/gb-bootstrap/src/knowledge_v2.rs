//! Finite carried-use development evidence from observed prefixes and recovered bytes.
//!
//! The pure API reads no files and accepts no retained proof or authoring product.
//! Its input identities do not establish acquisition provenance or a complete Gate5.
use crate::damage::ResourceProjection;
use crate::route_receiver_v2::{RouteError, admit_route_prefix};
use crate::route_semantics_v2::{ContextState, validate_definitions};
use gb_foundation::{ManifestValue as V, serialize_manifest, validate_canonical_manifest};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

const MAX_BYTES: usize = 1_048_576;
const STAGES: [u8; 12] = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5];
const DEPENDENCIES: [&[u16]; 12] = [
    &[],
    &[1],
    &[1],
    &[2, 3],
    &[3, 4],
    &[5],
    &[6],
    &[6, 7],
    &[6, 8],
    &[7, 8, 9],
    &[10],
    &[11],
];

/// The array type makes the exact four-sector requirement explicit. BTreeMap
/// admits unique section IDs and gives the canonical ascending body order.
#[derive(Clone, Copy)]
pub struct KnowledgeInputs<'a> {
    pub prefixes: [&'a [u8]; 4],
    pub side: u16,
    pub width: u16,
    pub required_stream: &'a [u8],
    pub all_stream: &'a [u8],
    pub body_payloads: &'a BTreeMap<u32, Vec<u8>>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum KnowledgeError {
    Input,
    Route,
    Context,
    Probe,
    ResourceLimit,
    Canonical,
    EvidenceMismatch,
}
impl std::fmt::Display for KnowledgeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "knowledge-use-v2: {self:?}")
    }
}
impl std::error::Error for KnowledgeError {}
pub type Result<T> = std::result::Result<T, KnowledgeError>;

fn need(ok: bool, error: KnowledgeError) -> Result<()> {
    if ok { Ok(()) } else { Err(error) }
}
fn object<const N: usize>(fields: [(&str, V); N]) -> V {
    V::Object(fields.into_iter().map(|(k, v)| (k.into(), v)).collect())
}
fn string(s: &str) -> V {
    V::String(s.into())
}
fn number(n: usize) -> V {
    V::U64(n as u64)
}
fn ids(values: &[u16]) -> V {
    V::Array(values.iter().map(|v| V::U64(u64::from(*v))).collect())
}
fn digest(raw: &[u8]) -> V {
    string(&format!("{:x}", Sha256::digest(raw)))
}
fn identity(raw: &[u8]) -> V {
    object([("bytes", number(raw.len())), ("sha256", digest(raw))])
}
fn u16_at(raw: &[u8], at: usize) -> Result<u16> {
    Ok(u16::from_be_bytes(
        raw.get(at..at.checked_add(2).ok_or(KnowledgeError::Input)?)
            .ok_or(KnowledgeError::Input)?
            .try_into()
            .unwrap(),
    ))
}
fn u32_at(raw: &[u8], at: usize) -> Result<u32> {
    Ok(u32::from_be_bytes(
        raw.get(at..at.checked_add(4).ok_or(KnowledgeError::Input)?)
            .ok_or(KnowledgeError::Input)?
            .try_into()
            .unwrap(),
    ))
}
fn route_error(error: RouteError) -> KnowledgeError {
    match error {
        RouteError::ResourceLimit => KnowledgeError::ResourceLimit,
        RouteError::Observation => KnowledgeError::Route,
    }
}
fn input_bounds(input: KnowledgeInputs<'_>) -> Result<()> {
    need(
        (64..=2048).contains(&input.side)
            && input.side % 8 == 0
            && (8..=128).contains(&input.width)
            && input.width % 8 == 0
            && 2 * u32::from(input.width) + 8 <= u32::from(input.side),
        KnowledgeError::Input,
    )?;
    for prefix in input.prefixes {
        need(
            (64..=32768).contains(&prefix.len())
                && prefix.len() * 8
                    <= usize::from(input.width) * usize::from(input.side - input.width)
                && u32_at(prefix, 48)? as usize == prefix.len() - 64
                && u32_at(prefix, 56)? as usize == prefix.len() * 8,
            KnowledgeError::Input,
        )?;
    }
    need(
        [input.required_stream, input.all_stream]
            .iter()
            .all(|s| (4..=MAX_BYTES).contains(&s.len())),
        KnowledgeError::Input,
    )?;
    need(
        (1..=4096).contains(&input.body_payloads.len())
            && input.body_payloads.contains_key(&100)
            && input.body_payloads.contains_key(&200),
        KnowledgeError::Input,
    )?;
    let mut total = 0usize;
    for (&id, body) in input.body_payloads {
        need(
            id != 0 && (1..=16384).contains(&body.len()),
            KnowledgeError::Input,
        )?;
        total = total
            .checked_add(body.len())
            .ok_or(KnowledgeError::ResourceLimit)?;
        need(total <= MAX_BYTES, KnowledgeError::Input)?;
    }
    Ok(())
}

#[derive(Clone, Copy)]
struct Frame<'a> {
    id: u16,
    stage: u8,
    kind: u8,
    start: usize,
    end: usize,
    payload: &'a [u8],
}
fn frames(raw: &[u8]) -> Result<Vec<Frame<'_>>> {
    let count = u16_at(raw, 46)? as usize;
    need(count == 48, KnowledgeError::Route)?;
    let mut at = 64usize;
    let mut rows = Vec::with_capacity(count);
    for _ in 0..count {
        let n = u32_at(raw, at + 4)? as usize;
        let end = at
            .checked_add(8)
            .and_then(|n0| n0.checked_add(n))
            .ok_or(KnowledgeError::ResourceLimit)?;
        let payload = raw.get(at + 8..end).ok_or(KnowledgeError::Route)?;
        rows.push(Frame {
            id: u16_at(raw, at + 2)?,
            stage: raw[at],
            kind: raw[at + 1],
            start: at,
            end,
            payload,
        });
        at = end;
    }
    need(at == raw.len(), KnowledgeError::Route)?;
    Ok(rows)
}
fn topological_order() -> Result<Vec<u16>> {
    let mut done = BTreeSet::new();
    let mut order = Vec::new();
    while done.len() < 12 {
        let next = (1..=12u16)
            .find(|id| {
                !done.contains(id)
                    && DEPENDENCIES[usize::from(*id - 1)]
                        .iter()
                        .all(|d| done.contains(d))
            })
            .ok_or(KnowledgeError::Route)?;
        done.insert(next);
        order.push(next);
    }
    let mut ancestors = BTreeSet::new();
    let mut stack = vec![12u16];
    while let Some(id) = stack.pop() {
        if ancestors.insert(id) {
            stack.extend_from_slice(DEPENDENCIES[usize::from(id - 1)]);
        }
    }
    need(ancestors == done, KnowledgeError::Route)?;
    Ok(order)
}
fn record_rows(raw: &[u8], frames: &[Frame<'_>]) -> V {
    V::Array(
        frames
            .iter()
            .map(|f| {
                object([
                    ("record_id", number(usize::from(f.id))),
                    ("stage", number(usize::from(f.stage))),
                    ("kind", number(usize::from(f.kind))),
                    ("byte_offset", number(f.start)),
                    ("bytes", number(f.end - f.start)),
                    ("payload_bytes", number(f.payload.len())),
                    ("sha256", digest(&raw[f.start..f.end])),
                ])
            })
            .collect(),
    )
}
fn facts_and_examples<'a>(frames: &[Frame<'a>]) -> Result<(V, V, Vec<Frame<'a>>)> {
    let definitions: Vec<_> = frames.iter().filter(|f| f.kind == 1).copied().collect();
    need(definitions.len() == 12, KnowledgeError::Route)?;
    let mut seen = BTreeSet::new();
    let mut facts = Vec::with_capacity(12);
    for f in &definitions {
        let fact = u16_at(f.payload, 0)?;
        need((1..=12).contains(&fact), KnowledgeError::Route)?;
        let index = usize::from(fact - 1);
        need(
            f.stage == STAGES[index]
                && !seen.contains(&fact)
                && DEPENDENCIES[index].iter().all(|d| seen.contains(d)),
            KnowledgeError::Route,
        )?;
        seen.insert(fact);
        let mut worked = Vec::new();
        let mut held = Vec::new();
        for example in frames.iter().filter(|x| matches!(x.kind, 2 | 3)) {
            if u16_at(example.payload, 0)? == fact {
                if example.kind == 2 {
                    worked.push(example.id);
                } else {
                    held.push(example.id);
                }
            }
        }
        let value = f.payload.get(14..).ok_or(KnowledgeError::Route)?;
        need(
            !value.is_empty() && !worked.is_empty() && !held.is_empty(),
            KnowledgeError::Route,
        )?;
        facts.push(object([
            ("fact_id", number(usize::from(fact))),
            ("stage", number(usize::from(f.stage))),
            ("consumes", ids(DEPENDENCIES[index])),
            ("definition_record_id", number(usize::from(f.id))),
            ("value_byte_offset", number(f.start + 8 + 14)),
            ("value_bytes", number(value.len())),
            ("value_sha256", digest(value)),
            ("worked_record_ids", ids(&worked)),
            ("held_out_record_ids", ids(&held)),
        ]));
    }
    let mut examples = Vec::with_capacity(33);
    for f in frames.iter().filter(|f| matches!(f.kind, 2 | 3)) {
        let input = u32_at(f.payload, 4)? as usize;
        let output = u32_at(f.payload, 8)? as usize;
        let fact = u16_at(f.payload, 0)?;
        need(
            seen.contains(&fact) && 12 + input + output == f.payload.len(),
            KnowledgeError::Route,
        )?;
        examples.push(object([
            ("record_id", number(usize::from(f.id))),
            ("fact_id", number(usize::from(fact))),
            ("recipe_id", number(usize::from(u16_at(f.payload, 2)?))),
            (
                "kind",
                string(if f.kind == 2 { "worked" } else { "held-out" }),
            ),
            ("input_bytes", number(input)),
            ("output_bytes", number(output)),
            (
                "status",
                number(usize::from(u16_at(f.payload, 12 + input)?)),
            ),
            ("success", V::Bool(true)),
        ]));
    }
    need(examples.len() == 33, KnowledgeError::Route)?;
    Ok((V::Array(facts), V::Array(examples), definitions))
}
fn coverage() -> V {
    const FACTS: [&[u16]; 11] = [
        &[1, 2, 3, 4, 5, 6],
        &[5, 6],
        &[7, 8, 9],
        &[9],
        &[8, 10, 11],
        &[7, 10, 11],
        &[11, 12],
        &[7, 8, 10, 11, 12],
        &[12],
        &[12],
        &[7, 9],
    ];
    V::Array(
        FACTS
            .iter()
            .enumerate()
            .map(|(i, facts)| {
                let contexts: &[&str] = match i {
                    6 | 7 | 9 => &["required", "all"],
                    8 => &["required", "all", "section-membership"],
                    _ => &[],
                };
                object([
                    ("repair_id", string(&format!("C{:02}", i + 1))),
                    ("fact_ids", ids(facts)),
                    (
                        "context_claims",
                        V::Array(contexts.iter().map(|s| string(s)).collect()),
                    ),
                ])
            })
            .collect(),
    )
}

/// Revalidate each route, its recovered context and every owned rejection probe.
/// Builders and host expected outputs are never substituted for supplied bytes.
pub fn build_knowledge_use_v2(input: KnowledgeInputs<'_>) -> Result<Vec<u8>> {
    input_bounds(input)?;
    let order = topological_order()?;
    let mut route_rows = Vec::with_capacity(4);
    let mut ablation_rows = Vec::with_capacity(96);
    let mut shared_package = None;
    let mut shared_definitions = None;
    for (sector, raw) in input.prefixes.into_iter().enumerate() {
        let mut cost = ResourceProjection::default();
        let route = admit_route_prefix(raw, input.side, input.width, sector as u8, &mut cost)
            .map_err(route_error)?
            .ok_or(KnowledgeError::Route)?;
        if let Some(package) = &shared_package {
            need(package == &route.package().encoded, KnowledgeError::Route)?;
        } else {
            shared_package = Some(route.package().encoded.clone());
        }
        if let Some(values) = &shared_definitions {
            need(values == route.definitions(), KnowledgeError::Route)?;
        } else {
            shared_definitions = Some(route.definitions().to_vec());
        }
        let context = route.commitments().prove_recovered(
            Some(input.required_stream),
            Some(input.all_stream),
            input.body_payloads,
        );
        // The Rust all-context proof is Consistent only when both carried body
        // membership checks are complete; omitted bodies yield Unresolved.
        need(
            context.required() == ContextState::Consistent
                && context.all() == ContextState::Consistent,
            KnowledgeError::Context,
        )?;
        let frames = frames(raw)?;
        let (facts, examples, definitions) = facts_and_examples(&frames)?;
        route_rows.push(object([
            ("sector_id", number(sector)),
            ("package_sha256", digest(&route.package().encoded)),
            (
                "mapping_sha256",
                string(&route.mapping_sha256().map_err(route_error)?),
            ),
            ("record_rows", record_rows(raw, &frames)),
            ("fact_rows", facts),
            ("example_rows", examples),
            (
                "context",
                object([
                    ("required", string("checked")),
                    ("all", string("checked")),
                    ("section-membership", string("checked")),
                ]),
            ),
        ]));
        for (index, frame) in definitions.iter().enumerate() {
            let fact = u16_at(frame.payload, 0)?;
            need(fact as usize == index + 1, KnowledgeError::Route)?;
            for contradict in [false, true] {
                let mut mutant = raw.to_vec();
                if contradict {
                    mutant[frame.end - 1] ^= 1;
                    let mut values = route.definitions().to_vec();
                    let last = values[index].last_mut().ok_or(KnowledgeError::Probe)?;
                    *last ^= 1;
                    need(
                        validate_definitions(
                            &values.iter().map(Vec::as_slice).collect::<Vec<_>>(),
                            route.package(),
                        )
                        .is_err(),
                        KnowledgeError::Probe,
                    )?;
                } else {
                    mutant.drain(frame.start..frame.end);
                    let body_length = (mutant.len() - 64) as u32;
                    let prefix_cells = (mutant.len() * 8) as u32;
                    mutant[46..48].copy_from_slice(&(u16_at(raw, 46)? - 1).to_be_bytes());
                    mutant[48..52].copy_from_slice(&body_length.to_be_bytes());
                    mutant[56..60].copy_from_slice(&prefix_cells.to_be_bytes());
                }
                let mut mutant_cost = ResourceProjection::default();
                let rejected = admit_route_prefix(
                    &mutant,
                    input.side,
                    input.width,
                    sector as u8,
                    &mut mutant_cost,
                )
                .map_err(route_error)?;
                need(rejected.is_none(), KnowledgeError::Probe)?;
                // Contradictions reach the same complete VM schedule and fail
                // the separately checked numeric relation. Removal fails the
                // closed header/skeleton before any carried VM execution.
                need(
                    mutant_cost
                        == if contradict {
                            cost
                        } else {
                            ResourceProjection::default()
                        },
                    KnowledgeError::Probe,
                )?;
                ablation_rows.push(object([
                    ("sector_id", number(sector)),
                    ("fact_id", number(usize::from(fact))),
                    (
                        "operator",
                        string(if contradict { "contradict" } else { "remove" }),
                    ),
                    ("bytes", number(mutant.len())),
                    ("sha256", digest(&mutant)),
                    (
                        "classification",
                        string(if contradict {
                            "definition-relationship"
                        } else {
                            "record-structure"
                        }),
                    ),
                    ("success", V::Bool(false)),
                ]));
            }
        }
    }
    let value = object([
        ("schema", string("golden-board.m2-knowledge-use/v2")),
        ("profile_id", string("eh72-hier-r5-r2-r1-lzss-crc32c-v1")),
        (
            "scope",
            string("carried-finite-use-and-ablation-development"),
        ),
        (
            "inputs",
            object([
                ("side", number(usize::from(input.side))),
                ("shell_width", number(usize::from(input.width))),
                (
                    "prefixes",
                    V::Array(
                        input
                            .prefixes
                            .iter()
                            .enumerate()
                            .map(|(sector, raw)| {
                                object([
                                    ("sector_id", number(sector)),
                                    ("bytes", number(raw.len())),
                                    ("sha256", digest(raw)),
                                ])
                            })
                            .collect(),
                    ),
                ),
                ("required_stream", identity(input.required_stream)),
                ("all_stream", identity(input.all_stream)),
                (
                    "decoded_bodies",
                    V::Array(
                        input
                            .body_payloads
                            .iter()
                            .map(|(&id, raw)| {
                                object([
                                    ("section_id", V::U64(u64::from(id))),
                                    ("bytes", number(raw.len())),
                                    ("sha256", digest(raw)),
                                ])
                            })
                            .collect(),
                    ),
                ),
            ]),
        ),
        ("topological_order", ids(&order)),
        ("route_rows", V::Array(route_rows)),
        ("repair_coverage", coverage()),
        ("ablation_rows", V::Array(ablation_rows)),
        (
            "summary",
            object([
                ("route_count", number(4)),
                ("definition_count", number(48)),
                ("example_count", number(132)),
                ("structural_presence_rejections", number(48)),
                ("relationship_contradiction_rejections", number(48)),
                ("recovered_context_count", number(4)),
                ("result", string("pass")),
            ]),
        ),
    ]);
    let bytes = serialize_manifest(&value).map_err(|_| KnowledgeError::Canonical)?;
    need(bytes.len() <= MAX_BYTES, KnowledgeError::ResourceLimit)?;
    Ok(bytes)
}

/// Canonical closed equality is against a fresh complete regeneration; no proof
/// summary, hash, cached result, or caller-selected subset can waive a check.
pub fn validate_knowledge_use_v2(raw: &[u8], input: KnowledgeInputs<'_>) -> Result<()> {
    need(
        !raw.is_empty() && raw.len() <= MAX_BYTES,
        KnowledgeError::Canonical,
    )?;
    validate_canonical_manifest(raw).map_err(|_| KnowledgeError::Canonical)?;
    need(
        raw == build_knowledge_use_v2(input)?,
        KnowledgeError::EvidenceMismatch,
    )
}
