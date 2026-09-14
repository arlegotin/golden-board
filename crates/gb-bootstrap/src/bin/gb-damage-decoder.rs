//! Persistent bounded observation-only decoder bridge for the independent P7
//! corpus comparison.
//!
//! Request frame: `u8 channel_id || u32-be byte_length || exact bytes`, where
//! channel IDs 0/1/2 are OBS_BITS/OBS_MATRIX/OBS_UNITS. Channel 255 with an
//! empty payload requests the exact section-attempt boundary KAT result.
//! Response frame:
//! `u32-be byte_length || canonical decoder-result bytes`.  Each request calls
//! the stateless public decoder entry point afresh.  EOF between frames exits;
//! a truncated frame is a fatal framing error.

use std::io::{self, Read, Write};

use gb_bootstrap::damage::{
    ArtifactState, RecoveryResult, ResourceProjection, decode_observation, render_decoder_result,
    section_attempt_boundary_kat,
};

const MAX_FRAME_BYTES: usize = 4_194_306;

fn closed_resource_limit() -> RecoveryResult {
    RecoveryResult {
        profile_version: None,
        inventory_established: false,
        resource: ResourceProjection::default(),
        artifact_state: ArtifactState::ResourceLimit,
        sections: Vec::new(),
        fragments: Vec::new(),
        accepted_hypotheses: Vec::new(),
    }
}

fn channel(id: u8) -> Option<&'static str> {
    match id {
        0 => Some("OBS_BITS"),
        1 => Some("OBS_MATRIX"),
        2 => Some("OBS_UNITS"),
        _ => None,
    }
}

fn read_exact_or_framing(reader: &mut impl Read, bytes: &mut [u8]) -> io::Result<()> {
    reader.read_exact(bytes).map_err(|error| {
        io::Error::new(
            io::ErrorKind::UnexpectedEof,
            format!("truncated damage bridge frame: {error}"),
        )
    })
}

fn write_raw(writer: &mut impl Write, raw: &[u8]) -> io::Result<()> {
    let length = u32::try_from(raw.len())
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "bridge result too large"))?;
    writer.write_all(&length.to_be_bytes())?;
    writer.write_all(raw)?;
    writer.flush()
}

fn write_result(writer: &mut impl Write, channel: &str, result: &RecoveryResult) -> io::Result<()> {
    let (raw, _) = render_decoder_result(channel, result)
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "decoder result render failed"))?;
    write_raw(writer, &raw)
}

fn run(mut reader: impl Read, mut writer: impl Write) -> io::Result<()> {
    loop {
        let mut id = [0_u8; 1];
        match reader.read(&mut id)? {
            0 => return Ok(()),
            1 => {}
            _ => unreachable!(),
        }
        if id[0] == 255 {
            let mut length = [0_u8; 4];
            read_exact_or_framing(&mut reader, &mut length)?;
            if u32::from_be_bytes(length) != 0 {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "boundary KAT control payload must be empty",
                ));
            }
            let (raw, _) = section_attempt_boundary_kat().map_err(|_| {
                io::Error::new(io::ErrorKind::InvalidData, "boundary KAT execution failed")
            })?;
            write_raw(&mut writer, &raw)?;
            continue;
        }
        let channel = channel(id[0]).ok_or_else(|| {
            io::Error::new(io::ErrorKind::InvalidData, "unknown damage bridge channel")
        })?;
        let mut length = [0_u8; 4];
        read_exact_or_framing(&mut reader, &mut length)?;
        let length = usize::try_from(u32::from_be_bytes(length))
            .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "frame length overflow"))?;
        if length > MAX_FRAME_BYTES {
            let mut remaining = length;
            let mut discard = [0_u8; 8_192];
            while remaining != 0 {
                let take = remaining.min(discard.len());
                read_exact_or_framing(&mut reader, &mut discard[..take])?;
                remaining -= take;
            }
            write_result(&mut writer, channel, &closed_resource_limit())?;
            continue;
        }
        let mut raw = vec![0_u8; length];
        read_exact_or_framing(&mut reader, &mut raw)?;
        let result = decode_observation(channel, &raw);
        write_result(&mut writer, channel, &result)?;
    }
}

fn main() -> io::Result<()> {
    run(
        io::BufReader::new(io::stdin().lock()),
        io::BufWriter::new(io::stdout().lock()),
    )
}

#[cfg(test)]
mod tests {
    use std::io::Cursor;

    use gb_bootstrap::candidate_recipe::build_eh_recipe_package;
    use gb_bootstrap::carrier::{
        ManifestationCore, build_manifestation_core, render_semantic_envelope,
    };
    use gb_bootstrap::policy::load_profile_policy;
    use gb_foundation::{ManifestValue, validate_canonical_manifest};
    use gb_slice::{SliceInputs, compile_slice_v0};

    use super::*;

    fn request(channel: u8, raw: &[u8]) -> Vec<u8> {
        let mut frame = vec![channel];
        frame.extend_from_slice(&(raw.len() as u32).to_be_bytes());
        frame.extend_from_slice(raw);
        frame
    }

    fn responses(raw: &[u8]) -> Vec<Vec<u8>> {
        let mut offset = 0_usize;
        let mut rows = Vec::new();
        while offset < raw.len() {
            let length = usize::try_from(u32::from_be_bytes(
                raw[offset..offset + 4].try_into().unwrap(),
            ))
            .unwrap();
            offset += 4;
            rows.push(raw[offset..offset + length].to_vec());
            offset += length;
        }
        rows
    }

    fn core(profile_version: u16) -> ManifestationCore {
        let compiled = compile_slice_v0(SliceInputs {
            declaration: include_bytes!("../../../../studies/m2/slice-v0.json"),
            content_fixture: include_bytes!("../../../../conformance/content-v0.json"),
            chess_fixture: include_bytes!("../../../../conformance/chess-v0.json"),
            game_set: include_bytes!("../../../../reports/game-set-v0.bin"),
            content_spec: include_bytes!("../../../../spec/content-v0.md"),
            constants: include_bytes!("../../../../spec/constants-v0.toml"),
            curriculum: include_bytes!("../../../../spec/curriculum-v0.toml"),
        })
        .unwrap();
        let policy_raw = include_bytes!("../../../../spec/profile-policy-v0.toml");
        let policy = load_profile_policy(policy_raw).unwrap();
        let semantic = render_semantic_envelope(
            &policy,
            policy_raw,
            &compiled,
            include_bytes!("../../../../spec/curriculum-v0.toml"),
        )
        .unwrap();
        build_manifestation_core(
            profile_version,
            include_bytes!("../../../../spec/route-data-v0.json"),
            &build_eh_recipe_package(profile_version).unwrap(),
            &semantic,
            7_141,
            16_384,
        )
        .unwrap()
    }

    #[test]
    fn multiple_frames_are_fresh_and_canonical() {
        let bits = [0, 0, 0, 1, 0];
        let matrix = [0, 1, 0];
        let mut input = request(0, &bits);
        input.extend_from_slice(&request(1, &matrix));
        input.extend_from_slice(&request(0, &bits));
        let mut output = Vec::new();
        run(Cursor::new(input), &mut output).unwrap();
        let rows = responses(&output);
        assert_eq!(rows.len(), 3);
        assert_eq!(rows[0], rows[2]);
        assert_ne!(rows[0], rows[1]);
        for row in rows {
            validate_canonical_manifest(&row).unwrap();
        }
    }

    #[test]
    fn clean_profile_frames_return_exact_independent_results() {
        let p1 = core(1);
        let p3 = core(3);
        let mut input = request(0, &p1.carrier_bytes);
        input.extend_from_slice(&request(0, &p3.carrier_bytes));
        let mut output = Vec::new();
        run(Cursor::new(input), &mut output).unwrap();
        let rows = responses(&output);
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].len(), 18_125);
        assert_eq!(
            gb_bootstrap::damage::observation_sha256(&rows[0]),
            "bc2a853b5dd4be7bf6686807efbe65dc00e9af7f98f4a9dd2300ee1299640779"
        );
        assert_eq!(rows[1].len(), 17_879);
        assert_eq!(
            gb_bootstrap::damage::observation_sha256(&rows[1]),
            "d6aa54580c2bf7f12073147a6b910b8c7dbea9c67c22639916befbdf7d363a97"
        );
    }

    #[test]
    fn oversize_is_discarded_and_closed_as_resource_limit() {
        let raw = vec![0_u8; MAX_FRAME_BYTES + 1];
        let mut output = Vec::new();
        run(Cursor::new(request(1, &raw)), &mut output).unwrap();
        let rows = responses(&output);
        assert_eq!(rows.len(), 1);
        let ManifestValue::Object(result) = validate_canonical_manifest(&rows[0]).unwrap() else {
            panic!("object")
        };
        assert_eq!(
            result.get("artifact_state"),
            Some(&ManifestValue::String("resource-limit".to_owned()))
        );
    }

    #[test]
    fn unknown_channel_and_truncated_frame_are_fatal() {
        assert_eq!(
            run(Cursor::new(vec![3]), Vec::new()).unwrap_err().kind(),
            io::ErrorKind::InvalidData
        );
        assert_eq!(
            run(Cursor::new(vec![0, 0, 0]), Vec::new())
                .unwrap_err()
                .kind(),
            io::ErrorKind::UnexpectedEof
        );
        assert_eq!(
            run(Cursor::new(vec![0, 0, 0, 0, 2, 0]), Vec::new())
                .unwrap_err()
                .kind(),
            io::ErrorKind::UnexpectedEof
        );
    }

    #[test]
    fn boundary_kat_control_executes_and_returns_exact_bytes() {
        let mut output = Vec::new();
        run(Cursor::new(request(255, &[])), &mut output).unwrap();
        let rows = responses(&output);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].len(), 307);
        assert_eq!(
            gb_bootstrap::damage::observation_sha256(&rows[0]),
            "4ad1468cd6cac6774b95e997d37c6fb420ff94cc0aa82595aeaa7b356440a68b"
        );
        validate_canonical_manifest(&rows[0]).unwrap();
        assert_eq!(
            run(Cursor::new(request(255, &[0])), Vec::new())
                .unwrap_err()
                .kind(),
            io::ErrorKind::InvalidData
        );
    }
}
