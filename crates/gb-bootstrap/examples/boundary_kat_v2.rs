//! Separate four-receipt export, never the observation-only decoder IPC.
use std::io::{self, Write};
fn main() {
    if std::env::args_os().len() != 1 {
        eprintln!("boundary_kat_v2 accepts no arguments");
        std::process::exit(2);
    }
    let rows = gb_bootstrap::boundary_kat_v2::boundary_kat_results_v2()
        .expect("source-owned boundary fixtures");
    let mut output = io::stdout().lock();
    for raw in rows {
        output.write_all(&raw).expect("receipt output");
    }
}
