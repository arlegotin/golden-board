//! Emit source-only bounds; optionally check a measured aggregate's components.
use std::io::{Read, Write};

use gb_bootstrap::receiver_bounds_v2::{
    ReceiverBoundSources, admit_resource_limits_v2, derive_receiver_bounds_v2,
};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args_os().skip(1).collect::<Vec<_>>();
    let sources = ReceiverBoundSources::default();
    if !args.is_empty() {
        if args.len() != 2 || args[0] != "--admit" {
            return Err("usage: receiver_bounds_v2 [--admit MEASURED_RESOURCE_LIMITS_JSON]".into());
        }
        let mut raw = Vec::new();
        std::fs::File::open(&args[1])?
            .take(1_048_577)
            .read_to_end(&mut raw)?;
        admit_resource_limits_v2(&raw, sources)?;
        eprintln!(
            "measured counters fit source bounds; corpus coverage and gate status are separate"
        );
    }
    std::io::stdout()
        .lock()
        .write_all(&derive_receiver_bounds_v2(sources)?)?;
    Ok(())
}
