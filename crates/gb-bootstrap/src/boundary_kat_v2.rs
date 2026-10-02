//! Fresh bounded receiver fixtures, never observation IPC inputs.
//!
//! Separate Python and Rust implementations share an author. Each constructs
//! its own inputs and calls the current receiver boundaries; no receipt is an input.
use super::*;

pub const KAT_IDS: [&str; 4] = [
    "rep2-correction-boundary",
    "rep5-correction-boundary",
    "complete-section-conflict",
    "section-attempt-ceiling-plus-one",
];

fn envelope(id: u32, payload: Vec<u8>) -> Result<Vec<u8>> {
    crate::encode_section(&SectionEnvelope {
        section_id: id,
        section_type: 6,
        section_version: 0,
        closure_class: 129,
        check_id: 1,
        dependencies: vec![],
        payload,
    })
    .map_err(|_| DamageV2Error::Reconstruction)
}
fn common(id: u32, profile: u16, payload: &[u8]) -> Result<[u8; 191]> {
    let raw = envelope(id, payload.to_vec())?;
    let blocks = crate::fragment_envelope(profile, id, 0, 6, 0, &raw)
        .map_err(|_| DamageV2Error::Reconstruction)?;
    if blocks.len() != 1 {
        return Err(DamageV2Error::Reconstruction);
    }
    Ok(blocks[0])
}
fn lane(encoded: [u8; 216]) -> LaneInput {
    LaneInput {
        present: true,
        observation: Some(EhObservation {
            encoded,
            erasures: vec![],
        }),
    }
}
fn repetition(factor: u8) -> Result<bool> {
    // The direct symbol uses the ordinary carried VM, independently built
    // from the neutral program owner rather than a duplicated inequality.
    let raw = crate::body_recipe_v1::build_revision_recipe_package()
        .map_err(|_| DamageV2Error::Reconstruction)?;
    let package = crate::recipe_wire_v1::decode_recipe_package_v1(&raw, 8)
        .map_err(|_| DamageV2Error::Reconstruction)?;
    let counts = if factor == 2 {
        [(1, 0), (1, 1)]
    } else {
        [(2, 1), (2, 2)]
    };
    for ((zeros, ones), known) in counts.into_iter().zip([1, 0]) {
        let value = evaluate_serialized_recipe_v1(&package, 113, &[factor, zeros, ones])
            .map_err(|_| DamageV2Error::Reconstruction)?;
        if value != [0, 0, known, 0] {
            return Ok(false);
        }
    }
    let block = common(4000 + u32::from(factor), 8, b"boundary")?;
    let identity = GroupIdentity::from_common(&block)?;
    let encoded = crate::candidate::encode_eh_unit(&block);
    let mut budget = Budget::default();
    let good = recover_group(
        &BTreeMap::from([(1, lane(encoded))]),
        1,
        factor,
        identity,
        &mut budget,
        None,
    )?;
    let mut left = encoded;
    let mut right = encoded;
    for index in 0..encoded.len() {
        let mask = if index % 2 == 0 { 0xaa } else { 0x55 };
        left[index] ^= mask;
        right[index] ^= mask ^ 0xff;
    }
    let bad = recover_group(
        &BTreeMap::from([(10, lane(left)), (11, lane(right))]),
        10,
        factor,
        identity,
        &mut budget,
        None,
    )?;
    Ok(matches!(
        good.state,
        FragmentState::Verified | FragmentState::Recovered
    ) && good.common == Some(block)
        && bad.common.is_none()
        && !matches!(
            bad.state,
            FragmentState::Verified | FragmentState::Recovered
        )
        && budget.value.primitive_steps > 0)
}
fn complete_conflict() -> Result<bool> {
    let mut entries = vec![];
    // Both hierarchical profiles use their actual semantic-copy-zero domain.
    for (profile, payload) in [(8, b"first".as_slice()), (7, b"other".as_slice())] {
        entries.push(crate::damage::UnitEntry {
            physical_unit_id: 100 + entries.len() as u32,
            bytes: crate::candidate::encode_eh_unit(&common(4003, profile, payload)?).to_vec(),
        });
    }
    for _ in 0..2 {
        let wire = crate::damage::serialize_obs_units(&entries)
            .map_err(|_| DamageV2Error::Reconstruction)?;
        let result = decode_observation_v2("OBS_UNITS", &wire);
        if result.artifact_state != ArtifactState::Ambiguous
            || result.profile_version.is_some()
            || result.inventory_established
            || result.required.is_some()
            || result.all.is_some()
            || !result.accepted_hypotheses.is_empty()
            || result.resource.section_attempts != 2
            || result.sections.len() != 2
            || !result.sections.iter().any(|s| {
                s.section_id == 4003 && s.state == SectionState::Ambiguous && s.envelope.is_none()
            })
            || result.sections.iter().any(|s| s.envelope.is_some())
        {
            return Ok(false);
        }
        entries.reverse();
    }
    Ok(true)
}

#[derive(Debug)]
struct AttemptAudit {
    passed: bool,
    compared: usize,
}
fn attempt_ceiling() -> Result<AttemptAudit> {
    let candidates = (0..4097u32)
        .map(|n| envelope(4004, n.to_be_bytes().to_vec()))
        .collect::<Result<BTreeSet<_>>>()?;
    if candidates.len() != 4097 {
        return Err(DamageV2Error::Reconstruction);
    }
    let mut budget = Budget::default();
    checked_charge(&mut budget, 53, 1, 7)?;
    let mut compared = 0;
    let mut exhausted = false;
    for (ordinal, raw) in candidates.iter().enumerate() {
        if !structurally_attemptable(raw) {
            return Err(DamageV2Error::Reconstruction);
        }
        match charge_section_attempt(&mut budget, raw) {
            Err(DamageV2Error::ResourceLimit) if ordinal == 4096 => {
                exhausted = true;
                break;
            }
            Err(error) => return Err(error),
            Ok(()) => (),
        }
        // Count an actual successful stored-check comparison, never the
        // number predicted from the thrown resource-limit exception.
        let decoded = decode_section(raw).map_err(|_| DamageV2Error::Reconstruction)?;
        compared += 1;
        if decoded.section_id != 4004 {
            return Err(DamageV2Error::Reconstruction);
        }
        let before = (budget.value, budget.adapter.clone());
        charge_section_attempt(&mut budget, raw)?;
        if before != (budget.value, budget.adapter.clone()) {
            return Err(DamageV2Error::Reconstruction);
        }
    }
    // Preserve both VM and adapter peaks, as the ordinary final renderer does.
    let mut usage = budget.value;
    usage.peak_scratch_bytes = usage
        .peak_scratch_bytes
        .max(budget.adapter.peak_scratch_bytes());
    let closed = RecoveryResultV2::closed(ArtifactState::ResourceLimit, usage);
    let checks = budget.adapter.rows()[Kernel::SectionCheck as usize];
    Ok(AttemptAudit {
        compared,
        passed: exhausted
            && compared == 4096
            && closed.resource.section_attempts == 4096
            && closed.resource.primitive_steps == 53
            && closed.resource.peak_scratch_bytes == budget.adapter.peak_scratch_bytes()
            && closed.resource.peak_scratch_bytes >= 7
            && checks.calls() == 4096
            && checks.reference_input_units()
                == candidates
                    .iter()
                    .take(4096)
                    .map(|r| r.len() as u64)
                    .sum::<u64>()
            && checks.peak_workspace_bytes() == candidates.first().unwrap().len() as u64
            && closed.artifact_state == ArtifactState::ResourceLimit
            && closed.profile_version.is_none()
            && !closed.inventory_established
            && closed.sections.is_empty()
            && closed.fragments.is_empty()
            && closed.accepted_hypotheses.is_empty()
            && closed.required.is_none()
            && closed.all.is_none(),
    })
}

/// Execute one owned ordinal from fresh fixtures and emit exactly one receipt.
pub fn boundary_kat_result_v2(ordinal: usize) -> Result<Vec<u8>> {
    let id = KAT_IDS.get(ordinal).ok_or(DamageV2Error::Observation)?;
    verify_owners()?;
    let passed = match ordinal {
        0 => repetition(2),
        1 => repetition(5),
        2 => complete_conflict(),
        3 => attempt_ceiling().map(|audit| audit.passed && audit.compared == 4096),
        _ => unreachable!(),
    }
    .unwrap_or(false);
    serialize_manifest(&object([
        ("schema", string("golden-board.m2-boundary-kat-result/v2")),
        ("kat_id", string(id)),
        ("result", string(if passed { "pass" } else { "fail" })),
    ]))
    .map_err(|_| DamageV2Error::Reconstruction)
}
pub fn boundary_kat_results_v2() -> Result<Vec<Vec<u8>>> {
    (0..KAT_IDS.len()).map(boundary_kat_result_v2).collect()
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn attempt_ceiling_counts_actual_stored_check_calls() {
        let audit = attempt_ceiling().unwrap();
        assert!(audit.passed);
        assert_eq!(audit.compared, 4096);
    }
}
