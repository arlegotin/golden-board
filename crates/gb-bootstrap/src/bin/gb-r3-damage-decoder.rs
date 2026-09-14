//! Persistent bounded observation-only decoder bridge for promoted M2 R3.
//!
//! Request frame: `u8 channel_id || u32-be byte_length || exact bytes`, where
//! channel IDs 0/1/2 are OBS_BITS/OBS_MATRIX/OBS_UNITS.  Response frame:
//! `u32-be byte_length || canonical decoder-result/v1 bytes`.  Each request is
//! decoded from only its serialized observation and tracked candidate-neutral
//! owner/profile/recipe code. EOF between frames exits; a truncated frame is
//! a fatal framing error.

use std::io::{self, Read, Write};

use gb_bootstrap::damage_v1::{
    RecoveryResultV1, boundary_kat_result_v1, decode_observation_v1, render_decoder_result_v1,
};

const MAX_FRAME_BYTES: usize = 4_194_306;

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
            format!("truncated R3 damage bridge frame: {error}"),
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

fn write_result(
    writer: &mut impl Write,
    channel: &str,
    result: &RecoveryResultV1,
) -> io::Result<()> {
    let (raw, _) = render_decoder_result_v1(channel, result).map_err(|_| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "R3 decoder result render failed",
        )
    })?;
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
        let channel = if id[0] == 255 {
            None
        } else {
            Some(channel(id[0]).ok_or_else(|| {
                io::Error::new(
                    io::ErrorKind::InvalidData,
                    "unknown R3 damage bridge channel",
                )
            })?)
        };
        let mut length = [0_u8; 4];
        read_exact_or_framing(&mut reader, &mut length)?;
        let length = usize::try_from(u32::from_be_bytes(length))
            .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "frame length overflow"))?;
        if length > MAX_FRAME_BYTES {
            // A caller-controlled u32 length may be nearly 4 GiB.  Draining
            // it would make the bridge's supposedly bounded framing path
            // attacker-controlled work, so an oversized frame is fatal and
            // the session cannot be resynchronized.
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "R3 damage bridge frame exceeds bounded maximum",
            ));
        }
        let mut raw = vec![0_u8; length];
        read_exact_or_framing(&mut reader, &mut raw)?;
        if let Some(channel) = channel {
            let result = decode_observation_v1(channel, &raw);
            write_result(&mut writer, channel, &result)?;
        } else {
            let ordinal = *raw.first().filter(|_| raw.len() == 1).ok_or_else(|| {
                io::Error::new(
                    io::ErrorKind::InvalidData,
                    "R3 boundary KAT request must contain one ordinal byte",
                )
            })?;
            let result = boundary_kat_result_v1(ordinal).map_err(|_| {
                io::Error::new(io::ErrorKind::InvalidData, "R3 boundary KAT failed")
            })?;
            write_raw(&mut writer, &result.canonical_bytes)?;
        }
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

    use gb_foundation::{ManifestValue, validate_canonical_manifest};

    use super::*;

    fn request(channel: u8, raw: &[u8]) -> Vec<u8> {
        let mut frame = vec![channel];
        frame.extend_from_slice(&(raw.len() as u32).to_be_bytes());
        frame.extend_from_slice(raw);
        frame
    }

    #[test]
    fn bridge_is_persistent_framed_and_result_v1_only() {
        let mut input = request(2, &0_u32.to_be_bytes());
        input.extend(request(0, &0_u32.to_be_bytes()));
        let mut output = Vec::new();
        run(Cursor::new(input), &mut output).unwrap();
        let mut offset = 0_usize;
        for _ in 0..2 {
            let length = usize::try_from(u32::from_be_bytes(
                output[offset..offset + 4].try_into().unwrap(),
            ))
            .unwrap();
            offset += 4;
            let raw = &output[offset..offset + length];
            offset += length;
            let ManifestValue::Object(value) = validate_canonical_manifest(raw).unwrap() else {
                panic!("result must be object");
            };
            assert_eq!(
                value.get("schema").and_then(ManifestValueExt::as_string),
                Some("golden-board.m2-damage-decoder-result/v1")
            );
        }
        assert_eq!(offset, output.len());
    }

    #[test]
    fn bridge_rejects_oversized_truncated_and_unknown_frames_without_draining() {
        let mut oversized = vec![2];
        oversized.extend_from_slice(&u32::MAX.to_be_bytes());
        assert_eq!(
            run(Cursor::new(oversized), Vec::new()).unwrap_err().kind(),
            io::ErrorKind::InvalidData
        );

        let truncated = request(2, &[0, 0, 0]);
        let mut declared_longer = truncated;
        declared_longer[1..5].copy_from_slice(&4_u32.to_be_bytes());
        assert_eq!(
            run(Cursor::new(declared_longer), Vec::new())
                .unwrap_err()
                .kind(),
            io::ErrorKind::UnexpectedEof
        );

        assert_eq!(
            run(Cursor::new(request(255, &[])), Vec::new())
                .unwrap_err()
                .kind(),
            io::ErrorKind::InvalidData
        );
        assert_eq!(
            run(Cursor::new(request(255, &[4])), Vec::new())
                .unwrap_err()
                .kind(),
            io::ErrorKind::InvalidData
        );
        assert_eq!(
            run(Cursor::new(request(254, &[])), Vec::new())
                .unwrap_err()
                .kind(),
            io::ErrorKind::InvalidData
        );
    }

    #[test]
    fn bridge_boundary_channel_is_persistent_exact_v1_and_ordered() {
        let mut input = Vec::new();
        for ordinal in 0_u8..4 {
            input.extend(request(255, &[ordinal]));
        }
        let mut output = Vec::new();
        run(Cursor::new(input), &mut output).unwrap();
        let mut offset = 0_usize;
        for kat_id in gb_bootstrap::damage_v1::BOUNDARY_KAT_IDS_V1 {
            let length = usize::try_from(u32::from_be_bytes(
                output[offset..offset + 4].try_into().unwrap(),
            ))
            .unwrap();
            offset += 4;
            let raw = &output[offset..offset + length];
            offset += length;
            let ManifestValue::Object(value) = validate_canonical_manifest(raw).unwrap() else {
                panic!("boundary result must be object");
            };
            assert_eq!(
                value.get("schema").and_then(ManifestValueExt::as_string),
                Some("golden-board.m2-boundary-kat-result/v1")
            );
            assert_eq!(
                value.get("kat_id").and_then(ManifestValueExt::as_string),
                Some(kat_id)
            );
            assert_eq!(
                value.get("result").and_then(ManifestValueExt::as_string),
                Some("pass")
            );
        }
        assert_eq!(offset, output.len());
    }

    trait ManifestValueExt {
        fn as_string(&self) -> Option<&str>;
    }

    impl ManifestValueExt for ManifestValue {
        fn as_string(&self) -> Option<&str> {
            match self {
                ManifestValue::String(value) => Some(value),
                _ => None,
            }
        }
    }
}
