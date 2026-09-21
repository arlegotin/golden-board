//! Bounded ordered source-oracle replay, with an explicit observation-only receiver mode.
//! Source/executable freeze and private publication remain the caller's responsibility.
use gb_foundation::{ManifestValue as V, serialize_manifest};
use sha2::{Digest, Sha256};
use std::error::Error;
fn string(s: &str) -> V {
    V::String(s.into())
}
fn hash(raw: Option<&[u8]>) -> V {
    string(
        &raw.map(|b| format!("{:x}", Sha256::digest(b)))
            .unwrap_or_else(|| "0".repeat(64)),
    )
}
pub fn ordered_cases(
    corpus: &crate::damage_corpus_v2::DamageCorpusV2,
    all: bool,
) -> Result<Vec<(&'static str, u64)>, Box<dyn Error>> {
    if all {
        let mut rows = vec![];
        for family in ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "B0"] {
            let count = corpus
                .case_count(family)
                .map_err(|e| format!("count: {e:?}"))?;
            for ordinal in 0..count {
                rows.push((family, ordinal));
            }
        }
        if rows.len() as u64 != corpus.accidental_case_count() + 21 {
            return Err("incomplete source case count".into());
        }
        Ok(rows)
    } else {
        Ok([
            ("D0", vec![0, 7]),
            ("D1", vec![0]),
            ("D2", vec![0]),
            ("D3", vec![0, 96]),
            ("D4", vec![0]),
            ("D6", vec![0]),
            ("D7", vec![0, 10, 16, 401, 402, 405, 408, 413, 414]),
            ("B0", (0..21).collect()),
        ]
        .into_iter()
        .flat_map(|(family, ids)| ids.into_iter().map(move |id| (family, id)))
        .collect())
    }
}
pub fn replay_workers(
    corpus: &crate::damage_corpus_v2::DamageCorpusV2,
    selected: &[(&str, u64)],
    workers: usize,
    receiver: bool,
    mut emit: impl FnMut(usize, Vec<u8>, Vec<u8>) -> Result<(), Box<dyn Error>>,
) -> Result<(), Box<dyn Error>> {
    use std::collections::BTreeMap;
    use std::sync::{Arc, Mutex, mpsc};
    if !(1..=8).contains(&workers) {
        return Err("worker bound".into());
    }
    std::thread::scope(|scope| {
        let (tasks, queue) = mpsc::sync_channel::<usize>(workers * 2);
        let queue = Arc::new(Mutex::new(queue));
        type Work = Result<(Vec<u8>, Vec<u8>), String>;
        let (results, completed) = mpsc::channel::<(usize, Work)>();
        let mut handles = vec![];
        for _ in 0..workers {
            let queue = Arc::clone(&queue);
            let results = results.clone();
            handles.push(scope.spawn(move || {
                let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(
                    || -> Result<(), String> {
                        let oracle = crate::damage_oracle_v2::FullOracleV2::new(corpus)
                            .map_err(|e| format!("oracle: {e:?}"))?;
                        loop {
                            let next = queue.lock().map_err(|_| "task mutex")?.recv();
                            let Ok(index) = next else {
                                return Ok(());
                            };
                            let (family, ordinal) = selected[index];
                            let work = (|| {
                                let case = corpus
                                    .case(family, ordinal)
                                    .map_err(|e| format!("case: {e:?}"))?;
                                let row = oracle
                                    .replay(family, ordinal, case.bytes())
                                    .map_err(|e| format!("replay {family}-{ordinal:06}: {e:?}"))?;
                                let row = if receiver {
                                    compare_receiver(&row, case.channel(), case.bytes())?
                                } else {
                                    row
                                };
                                if index == 0 {
                                    let again = oracle
                                        .replay(family, ordinal, case.bytes())
                                        .map_err(|e| format!("warm: {e:?}"))?;
                                    let again = if receiver {
                                        compare_receiver(&again, case.channel(), case.bytes())?
                                    } else {
                                        again
                                    };
                                    if again != row {
                                        return Err("warm replay differs".to_owned());
                                    }
                                }
                                Ok((case.identity_bytes().to_vec(), row))
                            })();
                            if results.send((index, work)).is_err() {
                                return Ok(());
                            }
                        }
                    },
                ));
                match outcome {
                    Ok(Ok(())) => {}
                    Ok(Err(error)) => {
                        let _ = results.send((usize::MAX, Err(error)));
                    }
                    Err(_) => {
                        let _ = results.send((usize::MAX, Err("oracle worker panicked".into())));
                    }
                }
            }));
        }
        drop(results);
        let outcome = (|| -> Result<(), Box<dyn Error>> {
            let mut issued = selected.len().min(workers * 2);
            for index in 0..issued {
                tasks.send(index)?;
            }
            let mut expected = 0;
            let mut pending = BTreeMap::new();
            while expected < selected.len() {
                let (index, result) = completed.recv()?;
                let data = result.map_err(|e| -> Box<dyn Error> { e.into() })?;
                if index < expected || index >= issued || pending.insert(index, data).is_some() {
                    return Err("duplicate/unissued replay result".into());
                }
                if pending.len() > workers * 2 {
                    return Err("pending replay bound".into());
                }
                while let Some((identity, row)) = pending.remove(&expected) {
                    emit(expected, identity, row)?;
                    expected += 1;
                    if issued < selected.len() {
                        tasks.send(issued)?;
                        issued += 1;
                    }
                }
                if issued - expected > workers * 2 {
                    return Err("issued replay bound".into());
                }
            }
            Ok(())
        })();
        drop(tasks);
        drop(completed);
        let mut joined = true;
        for handle in handles {
            joined &= handle.join().is_ok();
        }
        outcome?;
        if !joined {
            return Err("oracle worker join failed".into());
        }
        Ok(())
    })
}

pub fn checked_receiver_row(
    oracle_row: &[u8],
    channel: &str,
    observation: &[u8],
    result: &[u8],
    resources: &[u8],
) -> Result<Vec<u8>, Box<dyn Error>> {
    use gb_foundation::validate_canonical_manifest as parse;
    if oracle_row.len() > 1_048_576 || result.len() > 1_048_576 || resources.len() > 1_048_576 {
        return Err("replay projection bound".into());
    }
    let V::Object(mut row) = parse(oracle_row)? else {
        return Err("replay row object".into());
    };
    let expected = [
        "schema",
        "observation",
        "decoder_result",
        "resource_projection",
        "expected_section_states",
        "wrong_accept_count",
        "reauthored_boundary",
        "promise_result",
    ];
    if row.len() != expected.len()
        || expected.iter().any(|key| !row.contains_key(*key))
        || row["schema"] != string("golden-board.m2-damage-replay-case/v2")
    {
        return Err("closed replay row".into());
    }
    let V::Object(identity) = &row["observation"] else {
        return Err("observation object".into());
    };
    if identity.get("channel") != Some(&string(channel))
        || identity.get("observation_bytes") != Some(&V::U64(observation.len() as u64))
        || identity.get("observation_sha256") != Some(&hash(Some(observation)))
    {
        return Err("actual observation binding".into());
    }
    if serialize_manifest(&row["decoder_result"])? != result {
        return Err("independent oracle/receiver result differs".into());
    }
    if serialize_manifest(&row["resource_projection"])? != resources {
        return Err("independent oracle/receiver resources differ".into());
    }
    row.insert("decoder_result".into(), parse(result)?);
    row.insert("resource_projection".into(), parse(resources)?);
    let actual = serialize_manifest(&V::Object(row))?;
    if actual != oracle_row {
        return Err("complete replay row differs".into());
    }
    Ok(actual)
}
fn compare_receiver(row: &[u8], channel: &str, raw: &[u8]) -> Result<Vec<u8>, String> {
    use crate::damage_v2::{decode_observation_v2, render_decoder_result_v2, render_resources_v2};
    // This call is the entire production receiver interface. The source
    // oracle, case ID and expected result are not runtime receiver inputs.
    let result = decode_observation_v2(channel, raw);
    let rendered = render_decoder_result_v2(channel, &result)
        .map_err(|e| format!("receiver result: {e:?}"))?
        .0;
    let resources = render_resources_v2(channel, raw, &result)
        .map_err(|e| format!("receiver resources: {e:?}"))?;
    checked_receiver_row(row, channel, raw, &rendered, &resources).map_err(|e| e.to_string())
}
