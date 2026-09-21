//! Explicit development inventory-v2 admission for profile 8.
//!
//! The wire prefix and entries reuse inventory-v1 framing. The exact content
//! membership, required closure and protection are owned by bootstrap-v2.md.
//! This metadata check does not derive probe classes or establish carrier fit.

use std::collections::BTreeMap;

use super::{
    BootstrapError, CHECK_CRC32C, CLOSURE_M2_ALL_ONLY, CLOSURE_M2_REQUIRED, Inventory,
    MAX_DEPENDENCIES, MAX_INVENTORY_ENTRIES, RejectCode, Result, SECTION_CAPACITY_PROBE,
    SECTION_CONTENT_BODY, SECTION_INVENTORY, SECTION_LOAD_PROBE, SECTION_RESERVE_PROBE,
    SECTION_TIER_FRAME, check_strict_ids, checked_add, checked_mul,
};

pub const MAX_STORED_PAYLOAD_BYTES: usize = 16_384;
pub const REQUIRED_SECTION_IDS: [u32; 6] = [1, 2, 3, 16, 17, 18];

fn body_ids() -> Vec<u32> {
    (16..=18).chain(100..=163).chain(200..=210).collect()
}

fn invalid() -> BootstrapError {
    BootstrapError::new(RejectCode::Inventory)
}

fn validate_inventory(inventory: &Inventory, encoded_length: Option<usize>) -> Result<()> {
    if inventory.entries.len() > MAX_INVENTORY_ENTRIES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    if inventory.inventory_version != 2 || inventory.entries.len() < 81 {
        return Err(invalid());
    }
    if inventory.entries[..3]
        .iter()
        .map(|entry| entry.section_id)
        .ne([1, 2, 3])
    {
        return Err(invalid());
    }
    let all_bodies = body_ids();
    let mut observed_bodies = Vec::with_capacity(all_bodies.len());
    let mut previous_id = 0;
    let mut derived_length = 8;
    for entry in &inventory.entries {
        if entry.dependencies.len() > MAX_DEPENDENCIES {
            return Err(BootstrapError::new(RejectCode::ResourceLimit));
        }
        derived_length = checked_add(
            derived_length,
            checked_add(20, checked_mul(entry.dependencies.len(), 4)?)?,
        )?;
        if derived_length > MAX_STORED_PAYLOAD_BYTES {
            return Err(BootstrapError::new(RejectCode::ResourceLimit));
        }
        if entry.section_id == 0
            || entry.section_id <= previous_id
            || entry.check_id != CHECK_CRC32C
            || entry.copy_count != 1
            || !(1..=MAX_STORED_PAYLOAD_BYTES as u32).contains(&entry.logical_payload_length)
        {
            return Err(invalid());
        }
        previous_id = entry.section_id;
        check_strict_ids(
            &entry.dependencies,
            RejectCode::Inventory,
            Some(entry.section_id),
        )?;
        let required = REQUIRED_SECTION_IDS.contains(&entry.section_id);
        if entry.closure_class
            != if required {
                CLOSURE_M2_REQUIRED
            } else {
                CLOSURE_M2_ALL_ONLY
            }
            || (entry.physical_replica_count == 5) != required
        {
            return Err(invalid());
        }
        let ordinal = if (100..=163).contains(&entry.section_id) {
            Some((entry.section_id - 100) as u16)
        } else {
            None
        };
        if entry.game_ordinal != ordinal {
            return Err(invalid());
        }
        let valid = match entry.section_id {
            1 => {
                entry.section_type == SECTION_INVENTORY
                    && entry.section_version == 2
                    && entry.dependencies.is_empty()
            }
            2 | 3 => {
                let dependencies: &[u32] = if entry.section_id == 2 {
                    &[16, 17, 18]
                } else {
                    &all_bodies
                };
                entry.section_type == SECTION_TIER_FRAME
                    && entry.section_version == 0
                    && entry.dependencies == dependencies
            }
            id if all_bodies.binary_search(&id).is_ok() => {
                observed_bodies.push(id);
                entry.section_type == SECTION_CONTENT_BODY
                    && matches!(entry.section_version, 0 | 1)
                    && entry.dependencies.is_empty()
                    && entry.physical_replica_count == if required { 5 } else { 1 }
            }
            211.. => {
                let factor = match entry.section_type {
                    SECTION_CAPACITY_PROBE => matches!(entry.physical_replica_count, 1 | 2),
                    SECTION_RESERVE_PROBE => entry.physical_replica_count == 2,
                    SECTION_LOAD_PROBE => entry.physical_replica_count == 1,
                    _ => false,
                };
                entry.section_version == 0 && entry.dependencies.is_empty() && factor
            }
            _ => false,
        };
        if !valid {
            return Err(invalid());
        }
    }
    if observed_bodies != all_bodies
        || inventory.entries[0].logical_payload_length as usize != derived_length
        || encoded_length.is_some_and(|length| length != derived_length)
    {
        return Err(invalid());
    }
    Ok(())
}

/// Encode only the closed v2 inventory. Capacity factors still need the owner
/// ledger's independently derived class; successful encoding does not supply it.
pub fn encode_inventory(inventory: &Inventory) -> Result<Vec<u8>> {
    validate_inventory(inventory, None)?;
    super::encode_inventory_fields(inventory)
}

/// Decode only version 2, with the 16384-byte cap applied before allocation.
pub fn decode_inventory(raw: &[u8]) -> Result<Inventory> {
    let inventory = super::decode_inventory_fields(raw, &[2], MAX_STORED_PAYLOAD_BYTES)?;
    validate_inventory(&inventory, Some(raw.len()))?;
    Ok(inventory)
}

/// Content availability established from independently checked envelopes.
/// This does not classify the artifact or establish physical replica evidence.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ContentRecovery {
    pub required_bytes: Option<Vec<u8>>,
    pub all_bytes: Option<Vec<u8>>,
    pub checked_section_ids: Vec<u32>,
    pub rejected_section_ids: Vec<u32>,
}

fn envelope_agrees(envelope: &super::SectionEnvelope, entry: &super::InventoryEntry) -> bool {
    envelope.section_id == entry.section_id
        && envelope.section_type == entry.section_type
        && envelope.section_version == entry.section_version
        && envelope.closure_class == entry.closure_class
        && envelope.check_id == entry.check_id
        && envelope.dependencies == entry.dependencies
        && envelope.payload.len() == entry.logical_payload_length as usize
}

fn checked_envelope(raw: &[u8], entry: &super::InventoryEntry) -> Result<super::SectionEnvelope> {
    let length = checked_add(
        checked_add(22, checked_mul(entry.dependencies.len(), 4)?)?,
        entry.logical_payload_length as usize,
    )?;
    if raw.len() != length {
        return Err(invalid());
    }
    let envelope = super::decode_section(raw)?;
    if !envelope_agrees(&envelope, entry) {
        return Err(invalid());
    }
    Ok(envelope)
}

fn assemble_checked_tier(
    section_id: u32,
    checked: &BTreeMap<u32, super::SectionEnvelope>,
) -> Result<Vec<u8>> {
    let fail = || BootstrapError::new(RejectCode::ContentStream);
    let envelope = checked.get(&section_id).ok_or_else(fail)?;
    let tier = super::decode_tier_frame(&envelope.payload, section_id)?;
    if tier.body_section_ids != envelope.dependencies {
        return Err(fail());
    }
    let mut bodies = BTreeMap::new();
    for id in &tier.body_section_ids {
        let body = checked.get(id).ok_or_else(fail)?;
        let decoded = super::body_codec_v1::decode_body(body.section_version, &body.payload)
            .map_err(|_| fail())?;
        bodies.insert(*id, decoded);
    }
    super::assemble_content_stream(&tier, &bodies)
}

/// Recover required and all content under explicit inventory-v2 admission.
/// An invalid inventory or an unowned supplied ID rejects the request. Other
/// invalid envelopes remain diagnostics; checked but invalid content cannot
/// establish stream availability. The all stream requires a valid required one.
pub fn recover_content(section_envelopes: &BTreeMap<u32, Vec<u8>>) -> Result<ContentRecovery> {
    if section_envelopes.len() > MAX_INVENTORY_ENTRIES {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    let raw_inventory = section_envelopes.get(&1).ok_or_else(invalid)?;
    if raw_inventory.len() > MAX_STORED_PAYLOAD_BYTES + 22 {
        return Err(BootstrapError::new(RejectCode::ResourceLimit));
    }
    let inventory_envelope = super::decode_section(raw_inventory)?;
    let inventory = decode_inventory(&inventory_envelope.payload)?;
    if !envelope_agrees(&inventory_envelope, &inventory.entries[0]) {
        return Err(invalid());
    }
    let entries: BTreeMap<_, _> = inventory
        .entries
        .iter()
        .map(|entry| (entry.section_id, entry))
        .collect();
    if section_envelopes.keys().any(|id| !entries.contains_key(id)) {
        return Err(invalid());
    }
    let mut checked = BTreeMap::from([(1, inventory_envelope)]);
    let mut rejected_section_ids = Vec::new();
    for (id, raw) in section_envelopes {
        if *id == 1 {
            continue;
        }
        match checked_envelope(raw, entries[id]) {
            Ok(envelope) => {
                checked.insert(*id, envelope);
            }
            Err(_) => rejected_section_ids.push(*id),
        }
    }
    let required_bytes = assemble_checked_tier(2, &checked).ok();
    let all_bytes = if required_bytes.is_some() {
        assemble_checked_tier(3, &checked).ok()
    } else {
        None
    };
    Ok(ContentRecovery {
        required_bytes,
        all_bytes,
        checked_section_ids: checked.keys().copied().collect(),
        rejected_section_ids,
    })
}
