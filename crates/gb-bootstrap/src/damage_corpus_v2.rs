//! Independent, lazy profile-8 damage observations; never decoder outcomes.
//! The inherited coordinate operators receive newly authored profile-8 units.
use crate::carrier::{CellOwner, HierarchicalManifestationCore, HierarchicalMap, ProtectedUnit};
use crate::carrier_v2::Carrier;
use crate::damage::{self, Coordinate, UnitEntry};
use crate::damage_v1 as old;
use crate::{CommonBlock, EntryHypothesis};
use gb_foundation::{ManifestValue as V, serialize_manifest};
use gb_slice::SliceCompilation;
use sha2::{Digest, Sha256};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CorpusError {
    Source,
    Construction,
    Case,
    Bounds,
}
pub type Result<T> = std::result::Result<T, CorpusError>;
fn need(ok: bool) -> Result<()> {
    if ok {
        Ok(())
    } else {
        Err(CorpusError::Construction)
    }
}
fn u16_at(raw: &[u8], at: usize) -> Result<u16> {
    Ok(u16::from_be_bytes(
        raw.get(at..at + 2)
            .ok_or(CorpusError::Bounds)?
            .try_into()
            .unwrap(),
    ))
}
fn u32_at(raw: &[u8], at: usize) -> Result<u32> {
    Ok(u32::from_be_bytes(
        raw.get(at..at + 4)
            .ok_or(CorpusError::Bounds)?
            .try_into()
            .unwrap(),
    ))
}
fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn d<T>(v: damage::Result<T>) -> Result<T> {
    v.map_err(|_| CorpusError::Construction)
}
fn object(rows: impl IntoIterator<Item = (&'static str, V)>) -> V {
    V::Object(rows.into_iter().map(|(k, v)| (k.to_owned(), v)).collect())
}
fn string(v: &str) -> V {
    V::String(v.to_owned())
}
fn array_u64(v: impl IntoIterator<Item = u64>) -> V {
    V::Array(v.into_iter().map(V::U64).collect())
}
fn parameter(id: &'static str, value_type: &'static str, value: V) -> V {
    object([
        ("id", string(id)),
        ("value_type", string(value_type)),
        ("value", value),
    ])
}
fn scalar(id: &'static str, value: u64) -> V {
    parameter(id, "u64", V::U64(value))
}
fn ids(id: &'static str, value: impl IntoIterator<Item = u64>) -> V {
    parameter(id, "u64-list", array_u64(value))
}
fn coords(id: &'static str, value: &[Coordinate]) -> V {
    parameter(
        id,
        "coordinate-list",
        V::Array(
            value
                .iter()
                .map(|p| array_u64([u64::from(p.row), u64::from(p.column)]))
                .collect(),
        ),
    )
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ObservationV2 {
    bytes: Vec<u8>,
    channel: &'static str,
    operator: &'static str,
    identity: Vec<u8>,
}
impl ObservationV2 {
    pub fn bytes(&self) -> &[u8] {
        &self.bytes
    }
    pub fn channel(&self) -> &'static str {
        self.channel
    }
    pub fn operator(&self) -> &'static str {
        self.operator
    }
    pub fn identity_bytes(&self) -> &[u8] {
        &self.identity
    }
}

pub struct DamageCorpusV2 {
    core: HierarchicalManifestationCore,
    commons: Vec<[u8; 191]>,
    donor_prefix: Vec<u8>,
    placements: Vec<Coordinate>,
    permutations: Vec<Vec<usize>>,
}
impl DamageCorpusV2 {
    pub(crate) fn source_core(&self) -> &HierarchicalManifestationCore {
        &self.core
    }
    pub(crate) fn source_commons(&self) -> &[[u8; 191]] {
        &self.commons
    }
    pub(crate) fn source_donor_prefix(&self) -> &[u8] {
        &self.donor_prefix
    }
    pub fn new(
        slice: &SliceCompilation,
        carrier: &Carrier,
        donor_route_owner: &[u8],
    ) -> Result<Self> {
        // Reject a substituted source before any expensive construction.
        if donor_route_owner.len() > 1_048_576
            || hash(donor_route_owner)
                != "965a3e35ceb4b5a92a7715b3fcde20cc3019f8c9d9efa533abd93b051bb86641"
        {
            return Err(CorpusError::Source);
        }
        let side = carrier.side();
        let width = carrier.shell_width();
        let mapping8 =
            crate::mapping_v2::derive(side, width).map_err(|_| CorpusError::Construction)?;
        let mut mapping =
            HierarchicalMap::derive(side, width).map_err(|_| CorpusError::Construction)?;
        mapping.cell_offset = mapping8.cell_offset();
        need(
            mapping.population == mapping8.population()
                && carrier.unit_count() == mapping.unit_slot_count,
        )?;
        let count = usize::from(side)
            .checked_mul(usize::from(side))
            .ok_or(CorpusError::Bounds)?;
        let raw = carrier.packed_bytes();
        need(
            count <= 2048 * 2048 && raw.len() == 4 + count / 8 && u32_at(raw, 0)? as usize == count,
        )?;
        let bits: Vec<u8> = raw[4..]
            .iter()
            .flat_map(|b| (0..8).rev().map(move |n| (b >> n) & 1))
            .collect();
        let mut owners = vec![
            CellOwner {
                kind: 0,
                owner_id: 0,
                bit_offset: 0
            };
            count
        ];
        let mut units = Vec::new();
        let mut commons = Vec::new();
        for section in carrier.sections() {
            let envelope = section.envelope().map_err(|_| CorpusError::Construction)?;
            let blocks = crate::fragment_envelope(
                8,
                section.section_id,
                0,
                section.section_type,
                section.section_version,
                &envelope,
            )
            .map_err(|_| CorpusError::Construction)?;
            for (fragment_index, block) in blocks.into_iter().enumerate() {
                let encoded = crate::candidate::encode_eh_unit(&block);
                for replica_index in 0..section.copy_count {
                    let ordinal = units.len() as u64;
                    need(ordinal < mapping.unit_slot_count)?;
                    for bit in 0..1728u16 {
                        let physical = mapping
                            .forward_unit_bit(ordinal, bit)
                            .map_err(|_| CorpusError::Construction)?;
                        need(
                            physical
                                == mapping8
                                    .forward(ordinal + 1, bit)
                                    .map_err(|_| CorpusError::Construction)?,
                        )?;
                        let (row, col) = mapping
                            .matrix_cell(physical)
                            .map_err(|_| CorpusError::Construction)?;
                        let flat = usize::from(row) * usize::from(side) + usize::from(col);
                        need(
                            owners[flat].kind == 0
                                && bits[flat]
                                    == ((encoded[usize::from(bit) / 8] >> (7 - bit % 8)) & 1),
                        )?;
                        owners[flat] = CellOwner {
                            kind: 4,
                            owner_id: (ordinal + 1) as u32,
                            bit_offset: u32::from(bit),
                        };
                    }
                    let slot = mapping
                        .slot(ordinal)
                        .map_err(|_| CorpusError::Construction)?;
                    units.push(ProtectedUnit {
                        physical_unit_id: (ordinal + 1) as u32,
                        section_id: section.section_id,
                        semantic_copy_id: 0,
                        fragment_index: fragment_index as u16,
                        replica_index,
                        physical_replica_count: section.copy_count,
                        encoded,
                        slot,
                        logical_bit_first: slot * 1728,
                    });
                    commons.push(block);
                }
            }
        }
        need(units.len() as u64 == carrier.unit_count() && units.len() >= 5)?;
        need(
            units[..5].iter().all(|u| {
                u.section_id == 1 && u.fragment_index == 0 && u.physical_replica_count == 5
            }),
        )?;
        let routes = crate::route_v2::build_route_images(slice, side, width)
            .map_err(|_| CorpusError::Construction)?;
        for route in &routes.sectors {
            for (bit, value) in route.bits.iter().enumerate() {
                let (row, col) = crate::sector_cell_at(
                    usize::from(side),
                    usize::from(width),
                    route.sector_id,
                    bit,
                )
                .map_err(|_| CorpusError::Construction)?;
                let flat = row * usize::from(side) + col;
                need(owners[flat].kind == 0 && bits[flat] == *value)?;
            }
        }
        let package = crate::candidate_recipe::build_eh_recipe_package(3)
            .map_err(|_| CorpusError::Construction)?;
        let donor = crate::carrier::build_route_images(donor_route_owner, 3, &package, side, 128)
            .map_err(|_| CorpusError::Construction)?;
        let donor_prefix = prefix(&donor.sectors[0])?;
        need(donor_prefix.len() * 8 <= 128 * (usize::from(side) - 128))?;
        let core = HierarchicalManifestationCore {
            profile: crate::candidate::CandidateProfile {
                id: "eh72-hier-r5-r2-r1-lzss-crc32c-v1",
                version: 8,
                transport: crate::candidate::TransportFamily::Eh72HierarchicalRepetition,
                section_check_id: 1,
                required_copy_count: 2,
            },
            semantic_envelope_sha256: String::new(),
            side,
            shell_width: width,
            mapping,
            routes,
            sections: carrier.sections().to_vec(),
            units,
            carrier_bits: bits,
            carrier_bytes: raw.to_vec(),
            cell_owners: owners,
            interior_fixed_pad_bits: Vec::new(),
        };
        let placements = d2_placements_v2(usize::from(core.mapping.interior_side))?;
        let permutations = d(damage::d5_permutations(core.units.len()))?;
        Ok(Self {
            core,
            commons,
            donor_prefix,
            placements,
            permutations,
        })
    }
    pub fn case_count(&self, family: &str) -> Result<u64> {
        Ok(match family {
            "D0" => 16,
            "D1" => 4,
            "D2" => 256,
            "D3" => 128,
            "D4" => self.core.units.len() as u64,
            "D5" => 21,
            "D6" => 4 * self.core.units.len() as u64,
            "D7" => 415,
            "B0" => 21,
            _ => return Err(CorpusError::Case),
        })
    }
    pub fn accidental_case_count(&self) -> u64 {
        840 + 5 * self.core.units.len() as u64
    }
    pub fn case(&self, family: &str, ordinal: u64) -> Result<ObservationV2> {
        if ordinal >= self.case_count(family)? {
            return Err(CorpusError::Case);
        }
        let (channel, operator, mut parameters, bytes) = self.generate(family, ordinal as usize)?;
        parameters.sort_by_key(|p| {
            if let V::Object(p) = p {
                if let V::String(s) = &p["id"] {
                    s.clone()
                } else {
                    unreachable!()
                }
            } else {
                unreachable!()
            }
        });
        let identity = serialize_manifest(&object([
            ("schema", string("golden-board.damage-observation/v2")),
            ("case_id", string(&format!("{family}-{ordinal:06}"))),
            ("family_id", string(family)),
            ("case_ordinal", V::U64(ordinal)),
            ("channel", string(channel)),
            ("operator", string(operator)),
            ("parameter_projection", V::Array(parameters)),
            ("observation_bytes", V::U64(bytes.len() as u64)),
            ("observation_sha256", string(&hash(&bytes))),
        ]))
        .map_err(|_| CorpusError::Construction)?;
        Ok(ObservationV2 {
            bytes,
            channel,
            operator,
            identity,
        })
    }
    fn generate(&self, family: &str, n: usize) -> Result<Generated> {
        let c = &self.core;
        let result = match family {
            "D0" => (
                "OBS_BITS",
                "clean-transform-polarity",
                vec![
                    scalar("polarity_id", (n % 2) as u64),
                    scalar("transform_id", (n / 2) as u64),
                ],
                d(damage::serialize_obs_bits(&d(
                    damage::transformed_clean_bits(
                        &c.carrier_bits,
                        usize::from(c.side),
                        EntryHypothesis {
                            transform: (n / 2) as u8,
                            polarity: (n % 2) as u8,
                        },
                    ),
                )?))?,
            ),
            "D1" => (
                "OBS_MATRIX",
                "erase-one-complete-shell-sector",
                vec![scalar("sector_id", n as u64)],
                d(old::erase_shell_sector_v1(c, n as u8, None))?,
            ),
            "D2" => {
                let p = self.placements[n];
                let side = damage::d2_square_side(usize::from(c.mapping.interior_side));
                (
                    "OBS_MATRIX",
                    "erase-square-in-protected-interior",
                    vec![
                        scalar("side", side as u64),
                        coords(
                            "top_left",
                            &[Coordinate {
                                row: p.row + u32::from(c.shell_width),
                                column: p.column + u32::from(c.shell_width),
                            }],
                        ),
                    ],
                    d(old::erase_square_v1(c, p, side))?,
                )
            }
            "D3" => {
                let seed = SEED + n as u64;
                let points = d(old::d3_coordinates_v1(c, seed, 0))?;
                (
                    "OBS_MATRIX",
                    "fixed-weight-unknown-bit-substitution",
                    vec![
                        coords("coordinates", &points),
                        scalar("seed", seed),
                        scalar("stratum_id", (n / 32) as u64),
                    ],
                    d(old::substitute_coordinates_v1(c, &points))?,
                )
            }
            "D4" => (
                "OBS_UNITS",
                "omit-one-physical-unit-observation",
                vec![scalar("omitted_unit_id", n as u64 + 1)],
                d(old::omitted_unit_observation_v1(c, &[n as u32 + 1]))?,
            ),
            "D5" => (
                "OBS_UNITS",
                "permute-intact-physical-unit-observations",
                vec![scalar("permutation_ordinal", n as u64)],
                d(old::permuted_unit_observation_v1(c, &self.permutations[n]))?,
            ),
            "D6" => {
                let sector = n / c.units.len();
                let unit = n % c.units.len() + 1;
                (
                    "OBS_MATRIX",
                    "erase-shell-sector-union-one-physical-unit-cell-set",
                    vec![
                        scalar("sector_id", sector as u64),
                        scalar("unit_id", unit as u64),
                    ],
                    d(old::erase_shell_sector_v1(
                        c,
                        sector as u8,
                        Some(unit as u32),
                    ))?,
                )
            }
            "D7" => return self.d7(n),
            "B0" => return self.boundary(n),
            _ => return Err(CorpusError::Case),
        };
        Ok(result)
    }
    fn entries(&self) -> Vec<UnitEntry> {
        old::clean_unit_entries_v1(&self.core)
    }
    fn replace_first(&self, bytes: Vec<u8>, count: usize) -> Result<Vec<u8>> {
        let mut entries = self.entries();
        for entry in &mut entries[..count] {
            entry.bytes = bytes.clone();
        }
        d(damage::serialize_obs_units(&entries))
    }
    fn d7(&self, n: usize) -> Result<Generated> {
        let c = &self.core;
        let first_ids = || ids("target_unit_ids", 1..=5);
        Ok(match n {
            0..=2 => (
                "OBS_BITS",
                "mapping-mutants",
                vec![scalar("mutant_ordinal", n as u64)],
                d(old::mapping_mutant_v1(c, n as u8))?,
            ),
            3..=4 => {
                let mut common = self.commons[0];
                if n == 3 {
                    common[187..].reverse()
                } else {
                    let mut reg = 0xffff_ffffu32;
                    let mut pre = crate::LOCAL_CHECK_DOMAIN.to_vec();
                    pre.extend_from_slice(&common[..187]);
                    for b in pre {
                        reg ^= u32::from(b) << 24;
                        for _ in 0..8 {
                            reg = if reg & 0x8000_0000 != 0 {
                                (reg << 1) ^ 0x1edc_6f41
                            } else {
                                reg << 1
                            };
                        }
                    }
                    common[187..].copy_from_slice(&(reg ^ 0xffff_ffff).to_be_bytes());
                }
                (
                    "OBS_UNITS",
                    "check-mutants",
                    vec![scalar("case_ordinal", (n - 3) as u64), first_ids()],
                    self.replace_first(crate::candidate::encode_eh_unit(&common).to_vec(), 5)?,
                )
            }
            5..=6 => {
                let s = self.section(2)?;
                let mut env = s.envelope().map_err(|_| CorpusError::Construction)?;
                if n == 5 {
                    env[11] = 2
                } else {
                    let len = env.len();
                    env[len - 4..].reverse()
                };
                (
                    "OBS_UNITS",
                    "check-mutants",
                    vec![
                        scalar("case_ordinal", (n - 3) as u64),
                        scalar("section_id", 2),
                    ],
                    d(damage::serialize_obs_units(
                        &self.replace_envelope(2, &env)?,
                    ))?,
                )
            }
            7..=9 => {
                let mut plain = [0u8; 192];
                plain[..191].copy_from_slice(&self.commons[0]);
                let mut encoded = Vec::with_capacity(216);
                for chunk in plain.chunks_exact(8) {
                    encoded.extend_from_slice(&damage::encode_eh_mutant_chunk(
                        chunk.try_into().unwrap(),
                        (n - 7) as u8,
                    ));
                }
                (
                    "OBS_UNITS",
                    "code-mutants",
                    vec![scalar("case_ordinal", (n - 7) as u64), first_ids()],
                    self.replace_first(encoded, 5)?,
                )
            }
            10 => {
                let mut bits = c.carrier_bits.clone();
                patch_prefix(&mut bits, c.side, 128, 0, &self.donor_prefix)?;
                (
                    "OBS_BITS",
                    "route-conflicts",
                    vec![scalar("alternate_profile_version", 3)],
                    d(damage::serialize_obs_bits(&bits))?,
                )
            }
            11..=15 => {
                let profile = (n - 9) as u16;
                let mut common = self.commons[0];
                common[..2].copy_from_slice(&profile.to_be_bytes());
                local_check(&mut common);
                let p = crate::candidate::profile_by_version(profile)
                    .ok_or(CorpusError::Construction)?;
                let encoded = match p.transport {
                    crate::candidate::TransportFamily::Rs255_191 => {
                        crate::candidate::encode_rs255_191(&common).to_vec()
                    }
                    _ => crate::candidate::encode_eh_unit(&common).to_vec(),
                };
                (
                    "OBS_UNITS",
                    "cross-profile-splices",
                    vec![
                        scalar("source_profile_version", u64::from(profile)),
                        first_ids(),
                    ],
                    self.replace_first(encoded, 5)?,
                )
            }
            16 => {
                let mut common = self.commons[0];
                common[30] ^= 1;
                local_check(&mut common);
                (
                    "OBS_UNITS",
                    "valid-copy-conflicts",
                    vec![scalar("section_id", 1), scalar("target_unit_id", 1)],
                    self.replace_first(crate::candidate::encode_eh_unit(&common).to_vec(), 1)?,
                )
            }
            17..=272 => (
                "OBS_MATRIX",
                "d2-one-beyond",
                vec![
                    scalar("d2_ordinal", (n - 17) as u64),
                    scalar(
                        "side",
                        damage::d2_square_side(usize::from(c.mapping.interior_side)) as u64 + 1,
                    ),
                ],
                d(old::d2_one_beyond_v1(c, self.placements[n - 17]))?,
            ),
            273..=400 => {
                let seed = SEED + (n - 273) as u64;
                let points = d(old::d3_coordinates_v1(c, seed, 1))?;
                (
                    "OBS_MATRIX",
                    "d3-one-beyond",
                    vec![scalar("seed", seed)],
                    d(old::substitute_coordinates_v1(c, &points))?,
                )
            }
            401 => (
                "OBS_UNITS",
                "missing-unit-one-beyond",
                vec![ids("omitted_unit_ids", 1..=5)],
                d(old::omitted_unit_observation_v1(c, &[1, 2, 3, 4, 5]))?,
            ),
            402..=404 => {
                let (errors, erasures) = [(2, 0), (1, 2), (0, 4)][n - 402];
                (
                    "OBS_MATRIX",
                    "algebraic-one-beyond",
                    vec![
                        scalar("erasures", erasures as u64),
                        scalar("errors", errors as u64),
                        first_ids(),
                    ],
                    d(old::algebraic_one_beyond_v1(c, errors, erasures))?,
                )
            }
            405..=406 => (
                "OBS_BITS",
                "resource-route-one-beyond",
                vec![scalar(
                    "declared_value",
                    if n == 405 { 268_435_457 } else { 16_777_217 },
                )],
                d(old::resource_route_one_beyond_v1(c, n == 406))?,
            ),
            407 => (
                "OBS_BITS",
                "geometry-one-beyond",
                vec![scalar("side", 2056)],
                old::geometry_one_beyond_v1(),
            ),
            408..=413 => (
                "OBS_BITS",
                "compact-wire-mutants",
                vec![scalar("case_ordinal", (n - 408) as u64)],
                self.compact(n - 408)?,
            ),
            414 => {
                let mut common = self.commons[0];
                common[..2].copy_from_slice(&7u16.to_be_bytes());
                local_check(&mut common);
                (
                    "OBS_UNITS",
                    "foreign-profile7-bootstrap",
                    vec![scalar("source_profile_version", 7), first_ids()],
                    self.replace_first(crate::candidate::encode_eh_unit(&common).to_vec(), 5)?,
                )
            }
            _ => return Err(CorpusError::Case),
        })
    }
    fn section(&self, id: u32) -> Result<&crate::carrier::LogicalSection> {
        self.core
            .sections
            .iter()
            .find(|s| s.section_id == id)
            .ok_or(CorpusError::Construction)
    }
    fn replace_envelope(&self, id: u32, envelope: &[u8]) -> Result<Vec<UnitEntry>> {
        let s = self.section(id)?;
        need(envelope.len() == s.envelope().map_err(|_| CorpusError::Construction)?.len())?;
        let count = envelope.len().div_ceil(157);
        let mut blocks = Vec::with_capacity(count);
        // Local blocks can intentionally carry a malformed section check, so
        // use the neutral block author rather than a section-admitting parser.
        for (index, payload) in envelope.chunks(157).enumerate() {
            blocks.push(
                crate::encode_common_block(&CommonBlock {
                    profile_version: 8,
                    section_id: id,
                    semantic_copy_id: 0,
                    section_type: s.section_type,
                    section_version: s.section_version,
                    fragment_index: index as u16,
                    fragment_count: count as u16,
                    section_envelope_length: envelope.len() as u32,
                    payload: payload.to_vec(),
                })
                .map_err(|_| CorpusError::Construction)?,
            );
        }
        let mut entries = self.entries();
        let mut replaced = 0;
        for unit in self.core.units.iter().filter(|u| u.section_id == id) {
            let block = blocks
                .get(usize::from(unit.fragment_index))
                .ok_or(CorpusError::Construction)?;
            entries[unit.physical_unit_id as usize - 1].bytes =
                crate::candidate::encode_eh_unit(block).to_vec();
            replaced += 1;
        }
        need(replaced == count * usize::from(s.copy_count))?;
        Ok(entries)
    }
    fn replace_payload(&self, id: u32, payload: Vec<u8>) -> Result<Vec<UnitEntry>> {
        let mut s = self.section(id)?.clone();
        need(s.payload.len() == payload.len())?;
        s.payload = payload;
        self.replace_envelope(id, &s.envelope().map_err(|_| CorpusError::Construction)?)
    }
    fn boundary(&self, n: usize) -> Result<Generated> {
        if n < 14 {
            let closure = if n < 7 { 128 } else { 129 };
            let s = self
                .core
                .sections
                .iter()
                .find(|s| {
                    s.section_type == crate::SECTION_CONTENT_BODY
                        && s.section_version == 1
                        && s.closure_class == closure
                })
                .ok_or(CorpusError::Construction)?;
            let k = n % 7;
            let mut payload = s.payload.clone();
            need(payload.len() >= 6)?;
            match k {
                0 => payload[0] = 2,
                1 => payload[1..3].copy_from_slice(&16385u16.to_be_bytes()),
                _ => {
                    payload.fill(0);
                    let start: &[u8] = match k {
                        2 => &[3, 0, 0],
                        3 => &[3, 0, 3, 128, 0, 0],
                        4 => &[3, 0, 1, 1, 0],
                        5 => &[3, 0, 1, 0, 0],
                        6 => &[3, 0, 1, 128, 0, 15],
                        _ => unreachable!(),
                    };
                    payload[..start.len()].copy_from_slice(start);
                }
            }
            return Ok((
                "OBS_UNITS",
                "compressed-body-mutants",
                vec![
                    scalar("case_ordinal", k as u64),
                    scalar("section_id", u64::from(s.section_id)),
                ],
                d(damage::serialize_obs_units(
                    &self.replace_payload(s.section_id, payload)?,
                ))?,
            ));
        }
        if n < 20 {
            let id = 2 + (n - 14) / 3;
            let k = (n - 14) % 3;
            let mut payload = self.section(id as u32)?.payload.clone();
            need(
                payload.len() >= 12
                    && u16_at(&payload, payload.len() - 10)? == 14
                    && u32_at(&payload, payload.len() - 8)? == 4,
            )?;
            let len = payload.len();
            match k {
                0 => payload[len - 4..len - 2].fill(0),
                1 => payload[len - 2..].fill(0),
                2 => {
                    let v = u32_at(&payload, 8)?
                        .checked_add(1)
                        .ok_or(CorpusError::Bounds)?;
                    payload[8..12].copy_from_slice(&v.to_be_bytes());
                }
                _ => unreachable!(),
            }
            return Ok((
                "OBS_UNITS",
                "checked-tier-control-mutants",
                vec![
                    scalar("case_ordinal", k as u64),
                    scalar("section_id", id as u64),
                ],
                d(damage::serialize_obs_units(
                    &self.replace_payload(id as u32, payload)?,
                ))?,
            ));
        }
        let load = self
            .core
            .sections
            .iter()
            .find(|s| s.section_type == crate::SECTION_LOAD_PROBE)
            .ok_or(CorpusError::Construction)?;
        let mut inventory = crate::bootstrap_v2::decode_inventory(&self.section(1)?.payload)
            .map_err(|_| CorpusError::Construction)?;
        let entry = inventory
            .entries
            .iter_mut()
            .find(|e| e.section_id == load.section_id)
            .ok_or(CorpusError::Construction)?;
        entry.logical_payload_length = entry
            .logical_payload_length
            .checked_sub(157)
            .ok_or(CorpusError::Bounds)?;
        let payload = crate::bootstrap_v2::encode_inventory(&inventory)
            .map_err(|_| CorpusError::Construction)?;
        let entries = self.replace_payload(1, payload)?;
        let mut bits = self.core.carrier_bits.clone();
        for (unit, entry) in self
            .core
            .units
            .iter()
            .zip(entries)
            .filter(|(u, _)| u.section_id == 1)
        {
            for bit in 0..1728u16 {
                let physical = self
                    .core
                    .mapping
                    .forward_unit_bit(u64::from(unit.physical_unit_id - 1), bit)
                    .map_err(|_| CorpusError::Construction)?;
                let (row, col) = self
                    .core
                    .mapping
                    .matrix_cell(physical)
                    .map_err(|_| CorpusError::Construction)?;
                bits[usize::from(row) * usize::from(self.core.side) + usize::from(col)] =
                    (entry.bytes[usize::from(bit) / 8] >> (7 - bit % 8)) & 1;
            }
        }
        Ok((
            "OBS_BITS",
            "square-inventory-undercoverage",
            vec![
                scalar("removed_payload_bytes", 157),
                scalar("section_id", u64::from(load.section_id)),
            ],
            d(damage::serialize_obs_bits(&bits))?,
        ))
    }
    fn compact(&self, n: usize) -> Result<Vec<u8>> {
        let mut bits = self.core.carrier_bits.clone();
        for route in &self.core.routes.sectors {
            let mut raw = prefix(route)?;
            let package = package_offset(&raw)?;
            let first = first_recipe(&raw[package..])? + package;
            match n {
                0 => raw[package + 8..package + 10].fill(0),
                1 => raw[package + 48] = 1,
                2 => {
                    let len = u32_at(&raw, package + 32)?
                        .checked_sub(1)
                        .ok_or(CorpusError::Bounds)?;
                    raw[package + 32..package + 36].copy_from_slice(&len.to_be_bytes());
                }
                3 | 4 => {
                    let node = first_compact_node(&raw, first)?;
                    let tag = raw.get_mut(node).ok_or(CorpusError::Bounds)?;
                    need(*tag & 31 != 0 && *tag >> 5 != 0)?;
                    *tag &= if n == 3 { 0xe0 } else { 0x1f };
                }
                5 => {
                    let at = first + 16;
                    let old = u64::from_be_bytes(
                        raw.get(at..at + 8)
                            .ok_or(CorpusError::Bounds)?
                            .try_into()
                            .unwrap(),
                    );
                    let v = old.checked_add(1).ok_or(CorpusError::Bounds)?;
                    raw[at..at + 8].copy_from_slice(&v.to_be_bytes());
                }
                _ => return Err(CorpusError::Case),
            }
            patch_prefix(
                &mut bits,
                self.core.side,
                self.core.shell_width,
                route.sector_id,
                &raw,
            )?;
        }
        d(damage::serialize_obs_bits(&bits))
    }
}
type Generated = (&'static str, &'static str, Vec<V>, Vec<u8>);
const SEED: u64 = 5_134_751_402_299_490_304;
fn local_check(common: &mut [u8; 191]) {
    let mut raw = crate::LOCAL_CHECK_DOMAIN.to_vec();
    raw.extend_from_slice(&common[..187]);
    common[187..].copy_from_slice(&crate::crc32c(&raw).to_be_bytes());
}
fn prefix(route: &crate::carrier::SectorImage) -> Result<Vec<u8>> {
    let count = usize::try_from(route.route_prefix_cells).map_err(|_| CorpusError::Bounds)?;
    need(count % 8 == 0 && count <= route.bits.len())?;
    let mut raw = vec![0; count / 8];
    for bit in 0..count {
        raw[bit / 8] |= route.bits[bit] << (7 - bit % 8);
    }
    Ok(raw)
}
fn patch_prefix(bits: &mut [u8], side: u16, width: u16, sector: u8, raw: &[u8]) -> Result<()> {
    need(raw.len() * 8 <= usize::from(width) * (usize::from(side) - usize::from(width)))?;
    for bit in 0..raw.len() * 8 {
        let (row, col) = crate::sector_cell_at(usize::from(side), usize::from(width), sector, bit)
            .map_err(|_| CorpusError::Bounds)?;
        bits[row * usize::from(side) + col] = (raw[bit / 8] >> (7 - bit % 8)) & 1;
    }
    Ok(())
}
fn package_offset(raw: &[u8]) -> Result<usize> {
    let mut at = 64;
    let mut found = None;
    while at < raw.len() {
        let header = raw.get(at..at + 8).ok_or(CorpusError::Bounds)?;
        let len = u32_at(header, 4)? as usize;
        let end = at
            .checked_add(8)
            .and_then(|v| v.checked_add(len))
            .ok_or(CorpusError::Bounds)?;
        need(end <= raw.len())?;
        if header[1] == 5 {
            need(found.is_none())?;
            found = Some(at + 8);
        }
        at = end;
    }
    need(at == raw.len())?;
    found.ok_or(CorpusError::Construction)
}
fn first_recipe(raw: &[u8]) -> Result<usize> {
    let mut at = 64;
    for _ in 0..u16_at(raw, 18)? {
        let len = u32_at(raw, at + 12)? as usize;
        at = at
            .checked_add(16)
            .and_then(|v| v.checked_add(len))
            .ok_or(CorpusError::Bounds)?;
        need(at <= raw.len())?;
    }
    need(at + 32 <= raw.len())?;
    Ok(at)
}

fn first_compact_node(raw: &[u8], recipe: usize) -> Result<usize> {
    let descriptors = usize::from(u16_at(raw, recipe + 4)?) + usize::from(u16_at(raw, recipe + 6)?);
    need(descriptors <= 128)?;
    let end = recipe
        .checked_add(u32_at(raw, recipe + 28)? as usize)
        .ok_or(CorpusError::Bounds)?;
    need(end <= raw.len())?;
    let mut cursor = recipe + 32;
    for _ in 0..descriptors {
        need(cursor < end && raw[cursor] <= 5)?;
        cursor += 1;
        let mut terminated = false;
        for index in 0..5 {
            need(cursor < end)?;
            let byte = raw[cursor];
            cursor += 1;
            need(index != 4 || byte & 127 <= 15)?;
            if byte & 128 == 0 {
                need(index == 0 || byte != 0)?;
                terminated = true;
                break;
            }
        }
        need(terminated)?;
    }
    need(cursor < end)?;
    Ok(cursor)
}

// The inherited owner samples the population with anchor flats removed,
// then lifts each rank back into the complete row-major coordinate domain.
// The historical public helper samples a different population and is left
// unchanged for its existing callers.
fn d2_placements_v2(interior: usize) -> Result<Vec<Coordinate>> {
    if !(32..=2048).contains(&interior) {
        return Err(CorpusError::Bounds);
    }
    let square = damage::d2_square_side(interior);
    let last = interior.checked_sub(square).ok_or(CorpusError::Bounds)?;
    let width = last.checked_add(1).ok_or(CorpusError::Bounds)?;
    let total = width.checked_mul(width).ok_or(CorpusError::Bounds)?;
    let mut anchors = std::collections::BTreeSet::new();
    let mut output = Vec::with_capacity(256);
    for row in [0, last / 2, last] {
        for column in [0, last / 2, last] {
            if anchors.insert(row * width + column) {
                output.push(Coordinate {
                    row: row as u32,
                    column: column as u32,
                });
            }
        }
    }
    let population = total
        .checked_sub(anchors.len())
        .ok_or(CorpusError::Bounds)?;
    let count = 256usize
        .checked_sub(output.len())
        .ok_or(CorpusError::Bounds)?;
    for rank in d(damage::sample_without_replacement(population, count, SEED))? {
        let mut flat = rank;
        for excluded in &anchors {
            if *excluded <= flat {
                flat = flat.checked_add(1).ok_or(CorpusError::Bounds)?;
            }
        }
        need(flat < total && !anchors.contains(&flat))?;
        output.push(Coordinate {
            row: (flat / width) as u32,
            column: (flat % width) as u32,
        });
    }
    need(output.len() == 256)?;
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn sampled_placements_draw_from_anchor_excluded_population() {
        let placements = d2_placements_v2(64).unwrap();
        assert_eq!(placements.len(), 256);
        assert_eq!(
            placements[9],
            Coordinate {
                row: 26,
                column: 31
            }
        );
        let unique: std::collections::BTreeSet<_> = placements.iter().collect();
        assert_eq!(unique.len(), 256);
        assert!(
            placements
                .iter()
                .all(|point| point.row <= 32 && point.column <= 32)
        );
        assert!(d2_placements_v2(32).is_err());
        assert!(d2_placements_v2(2049).is_err());
    }
}
