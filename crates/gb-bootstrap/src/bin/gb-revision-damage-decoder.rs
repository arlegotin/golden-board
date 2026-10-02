//! Bounded observation-only process bridge owned by decoder-bridge-v2.
use gb_bootstrap::damage_v2::{
    decode_observation_v2, render_decoder_result_v2, render_resources_v2,
};
use std::io::{self, Read, Write};
fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = io::stdin().lock();
    let mut output = io::stdout().lock();
    loop {
        let mut tag = [0u8; 1];
        if input.read(&mut tag)? == 0 {
            return Ok(());
        }
        let channel = match tag[0] {
            1 => "OBS_BITS",
            2 => "OBS_MATRIX",
            3 => "OBS_UNITS",
            _ => return Err("unknown channel".into()),
        };
        let mut size = [0; 4];
        input.read_exact(&mut size)?;
        let size = u32::from_be_bytes(size) as usize;
        if size > 4194306 {
            return Err("observation frame exceeds bound".into());
        }
        let mut wire = vec![0; size];
        input.read_exact(&mut wire)?;
        let result = decode_observation_v2(channel, &wire);
        let result_bytes = render_decoder_result_v2(channel, &result)
            .map_err(|_| "result serialization")?
            .0;
        let sidecar =
            render_resources_v2(channel, &wire, &result).map_err(|_| "resource serialization")?;
        for value in [&result_bytes, &sidecar] {
            if value.is_empty() || value.len() > 1048576 {
                return Err("response frame exceeds bound".into());
            }
        }
        for value in [&result_bytes, &sidecar] {
            output.write_all(&(value.len() as u32).to_be_bytes())?;
            output.write_all(value)?;
        }
        output.flush()?;
    }
}
fn main() {
    if let Err(error) = run() {
        eprintln!("revision observation bridge: {error}");
        std::process::exit(2);
    }
}
