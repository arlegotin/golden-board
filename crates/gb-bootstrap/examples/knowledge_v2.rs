//! Local development evidence from a fresh observation-only Rust recovery.
//! No carrier, route, lesson, or fixture authoring API is called by this example.
use gb_bootstrap::body_codec_v1::decode_body;
use gb_bootstrap::damage::{ArtifactState, ObsBits, ResourceProjection, SectionState};
use gb_bootstrap::damage_v2::{decode_bits_v2, render_decoder_result_v2};
use gb_bootstrap::knowledge_v2::{KnowledgeInputs, build_knowledge_use_v2};
use gb_bootstrap::route_receiver_v2::admit_route_prefix;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::error::Error;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::Path;

fn read_bits(path: &Path) -> Result<Vec<u8>, Box<dyn Error>> {
    if !fs::symlink_metadata(path)?.file_type().is_file() {
        return Err("observation must be a regular file".into());
    }
    let mut raw = Vec::new();
    File::open(path)?.take(524293).read_to_end(&mut raw)?;
    if raw.len() > 524292 {
        return Err("observation exceeds packed 512 KiB scope plus length header".into());
    }
    ObsBits::parse(&raw).map_err(|e| format!("observation: {e:?}"))?;
    Ok(raw)
}
fn shell_bytes(
    raw: &[u8],
    side: usize,
    width: usize,
    sector: u8,
    bytes: usize,
) -> Result<Vec<u8>, Box<dyn Error>> {
    if bytes > 32768 || bytes * 8 > width * (side - width) {
        return Err("bounded shell request".into());
    }
    let mut out = vec![0u8; bytes];
    for bit in 0..bytes * 8 {
        let (row, column) = gb_bootstrap::sector_cell_at(side, width, sector, bit)
            .map_err(|e| format!("shell coordinate: {e:?}"))?;
        let physical = row * side + column;
        let value = (raw[4 + physical / 8] >> (7 - physical % 8)) & 1;
        out[bit / 8] |= value << (7 - bit % 8);
    }
    Ok(out)
}
fn write_new(dir: &Path, name: &str, raw: &[u8]) -> Result<(), Box<dyn Error>> {
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    options.open(dir.join(name))?.write_all(raw)?;
    Ok(())
}
fn run() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 2 {
        return Err("usage: knowledge_v2 OBS_BITS_FILE ABSOLUTE_NEW_PRIVATE_DIRECTORY".into());
    }
    let out = Path::new(&args[1]);
    if !out.is_absolute() || out.file_name().is_none() || out.try_exists()? {
        return Err("output must be a new absolute directory".into());
    }
    let raw = read_bits(Path::new(&args[0]))?;
    let count = u32::from_be_bytes(raw[..4].try_into().unwrap()) as usize;
    let side = (64..=2048usize)
        .step_by(8)
        .find(|s| s * s == count)
        .ok_or("this local exporter requires an exact square observation")?;
    let recovered = decode_bits_v2(&raw).map_err(|e| format!("receiver: {e:?}"))?;
    if recovered.artifact_state() != ArtifactState::Exact
        || recovered.profile_version() != Some(8)
        || !recovered.inventory_established()
    {
        return Err("complete exact profile8 recovery required".into());
    }
    let required = recovered.required_bytes().ok_or("required stream absent")?;
    let all = recovered.all_bytes().ok_or("all stream absent")?;
    let mut candidates = Vec::new();
    for width in (8..=128usize).step_by(8).filter(|w| 2 * w + 8 <= side) {
        if width * (side - width) < 512 {
            continue;
        }
        let mut prefixes = Vec::with_capacity(4);
        for sector in 0..4u8 {
            let header = shell_bytes(&raw, side, width, sector, 64)?;
            if header[40..42] != 2u16.to_be_bytes() {
                break;
            }
            let body = u32::from_be_bytes(header[48..52].try_into().unwrap()) as usize;
            if body > 32704 || (64 + body) * 8 > width * (side - width) {
                break;
            }
            let prefix = shell_bytes(&raw, side, width, sector, 64 + body)?;
            let route = admit_route_prefix(
                &prefix,
                side as u16,
                width as u16,
                sector,
                &mut ResourceProjection::default(),
            )
            .map_err(|e| format!("prefix: {e:?}"))?;
            let Some(route) = route else {
                break;
            };
            let hash = route
                .mapping_sha256()
                .map_err(|e| format!("mapping: {e:?}"))?;
            if !recovered.accepted_hypotheses().iter().any(|h| {
                h.transform_id == 0
                    && h.polarity_id == 0
                    && h.sector_id == sector
                    && h.profile_version == 8
                    && h.mapping_sha256 == hash
            }) {
                return Err(
                    "observed prefix does not bind the receiver's accepted normal-view route"
                        .into(),
                );
            }
            prefixes.push(prefix);
        }
        if prefixes.len() == 4 {
            candidates.push((width as u16, prefixes));
        }
    }
    if candidates.len() != 1 {
        return Err("one complete four-route normal-view acquisition required".into());
    }
    let (width, prefixes) = candidates.pop().unwrap();
    let prefixes: [Vec<u8>; 4] = prefixes.try_into().map_err(|_| "four prefixes")?;
    let mut bodies = BTreeMap::new();
    for id in [100u32, 200] {
        let row = recovered
            .sections()
            .iter()
            .find(|s| s.section_id == id)
            .ok_or("checked body section absent")?;
        if !matches!(row.state, SectionState::Verified | SectionState::Recovered) {
            return Err("body section is not checked".into());
        }
        let envelope =
            gb_bootstrap::decode_section(row.envelope.as_deref().ok_or("body envelope absent")?)
                .map_err(|e| format!("section envelope: {e:?}"))?;
        if envelope.section_id != id || envelope.section_type != gb_bootstrap::SECTION_CONTENT_BODY
        {
            return Err("body envelope identity mismatch".into());
        }
        bodies.insert(
            id,
            decode_body(envelope.section_version, &envelope.payload)
                .map_err(|e| format!("body: {e:?}"))?,
        );
    }
    let proof = build_knowledge_use_v2(KnowledgeInputs {
        prefixes: prefixes.each_ref().map(Vec::as_slice),
        side: side as u16,
        width,
        required_stream: required,
        all_stream: all,
        body_payloads: &bodies,
    })?;
    let (result, _) =
        render_decoder_result_v2("OBS_BITS", &recovered).map_err(|e| format!("render: {e:?}"))?;
    let mut directory = fs::DirBuilder::new();
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        directory.mode(0o700);
    }
    directory.create(out)?;
    write_new(out, "observation.bin", &raw)?;
    write_new(out, "decoder-result.json", &result)?;
    write_new(out, "required.content-v0.bin", required)?;
    write_new(out, "all.content-v0.bin", all)?;
    for (sector, prefix) in prefixes.iter().enumerate() {
        write_new(out, &format!("route-{sector}.bin"), prefix)?;
    }
    for (id, body) in &bodies {
        write_new(out, &format!("body-{id}.bin"), body)?;
    }
    let note = format!(
        "Local development evidence only. No complete Gate5, fresh participant, resource/damage admission or promotion claim.\nInputs were extracted from this exact OBS_BITS observation through fresh Rust recipient recovery; no route/slice/carrier constructor supplies them.\nRust implements the written knowledge-use owner separately, but shares an author with Python; this is not fresh-author independence.\nobservation bytes={} sha256={:x}\nside={side} width={width}\nknowledge bytes={} sha256={:x}\n",
        raw.len(),
        Sha256::digest(&raw),
        proof.len(),
        Sha256::digest(&proof)
    );
    write_new(out, "README.txt", note.as_bytes())?;
    // Write the positive evidence last, after all provenance inputs were saved.
    write_new(out, "knowledge-use.json", &proof)?;
    print!("{note}");
    Ok(())
}
fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
