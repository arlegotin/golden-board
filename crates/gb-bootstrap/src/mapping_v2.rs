//! Profile-8 physical mapping with complete domain validation.
//!
//! Recipe 109 is only the modular affine primitive. This adapter additionally
//! owns legal geometry, the smallest table-17 multiplier, one-based unit IDs,
//! encoded-bit limits, and inverse fixed-pad classification.

use crate::carrier::{CarrierError, HierarchicalInverse, HierarchicalMap};

type Result<T> = std::result::Result<T, CarrierError>;

/// A derived map whose validated state cannot be replaced through public fields.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Mapping {
    map: HierarchicalMap,
}

/// Derive the exact inherited geometry and smallest-B proof, then bind the
/// profile-8 affine offset. A zero table entry has no admissible map.
pub fn derive(side: u16, shell_width: u16) -> Result<Mapping> {
    let mut map = HierarchicalMap::derive(side, shell_width)?;
    let width_term = u64::from(shell_width)
        .checked_mul(257)
        .ok_or(CarrierError::Arithmetic)?;
    map.cell_offset = 8_u64
        .checked_mul(40_503)
        .and_then(|value| value.checked_add(width_term))
        .ok_or(CarrierError::Arithmetic)?
        % map.population;
    Ok(Mapping { map })
}

impl Mapping {
    /// Map unit IDs 1..=Q and encoded bits 0..1728 to interior physical cells.
    pub fn forward(&self, unit_id: u64, encoded_bit: u16) -> Result<u64> {
        if unit_id == 0 || unit_id > self.map.unit_slot_count {
            return Err(CarrierError::Geometry);
        }
        self.map.forward_unit_bit(unit_id - 1, encoded_bit)
    }

    /// Return `(0, one_based_unit_id, encoded_bit)` for protected cells or
    /// exactly `(1, 0, 0)` for fixed pad. Out-of-range physical cells reject.
    pub fn inverse(&self, physical: u64) -> Result<(u8, u64, u16)> {
        match self.map.inverse(physical)? {
            HierarchicalInverse::Unit {
                physical_ordinal,
                replica_bit,
                ..
            } => Ok((
                0,
                physical_ordinal
                    .checked_add(1)
                    .ok_or(CarrierError::Arithmetic)?,
                replica_bit,
            )),
            HierarchicalInverse::FixedPad { .. } => Ok((1, 0, 0)),
        }
    }

    pub fn side(&self) -> u16 {
        self.map.side
    }

    pub fn shell_width(&self) -> u16 {
        self.map.shell_width
    }

    pub fn interior_side(&self) -> u16 {
        self.map.interior_side
    }

    pub fn population(&self) -> u64 {
        self.map.population
    }

    pub fn unit_slot_count(&self) -> u64 {
        self.map.unit_slot_count
    }

    pub fn window_side(&self) -> u16 {
        self.map.window_side
    }

    pub fn slot_multiplier(&self) -> u64 {
        self.map.slot_multiplier
    }

    pub fn inverse_slot_multiplier(&self) -> u64 {
        self.map.inverse_slot_multiplier
    }

    pub fn cell_multiplier(&self) -> u64 {
        self.map.cell_multiplier
    }

    pub fn cell_offset(&self) -> u64 {
        self.map.cell_offset
    }

    pub fn inverse_cell_multiplier(&self) -> u64 {
        self.map.inverse_cell_multiplier
    }

    pub fn fixed_pad_cells(&self) -> u64 {
        self.map.fixed_pad_cells
    }
}
