use std::collections::BTreeMap;

use gb_bootstrap::candidate_recipe::{
    r3_compact_abi_size_probe, r3_recipe_package_metrics, r3_recipe_resource_rows,
    r3_slot_multiplier_table,
};
use gb_bootstrap::carrier::HierarchicalMap;
use sha2::{Digest, Sha256};

fn main() {
    let mut counts = BTreeMap::<u64, u64>::new();
    let mut fitting = 0_u64;
    let mut rejected = 0_u64;
    for side in (64_u16..=2_048).step_by(8) {
        let maximum = 128.min((side - 8) / 2);
        for shell_width in (8_u16..=maximum).step_by(8) {
            match HierarchicalMap::derive(side, shell_width) {
                Ok(map) => {
                    fitting += 1;
                    *counts.entry(map.slot_multiplier).or_default() += 1;
                }
                Err(_) => rejected += 1,
            }
        }
    }
    println!("fitting_geometries={fitting}");
    println!("rejected_geometries={rejected}");
    println!("distinct_slot_multipliers={}", counts.len());
    for (multiplier, count) in counts {
        println!("B={multiplier} count={count}");
    }
    let table = r3_slot_multiplier_table();
    println!("slot_multiplier_table_sha256={:x}", Sha256::digest(table));
    println!(
        "slot_multiplier_table_nonzero={}",
        table.iter().filter(|value| **value != 0).count()
    );
    let probe = r3_compact_abi_size_probe().unwrap();
    println!("abi_size_probe={probe:?}");
    println!("compact_package={:?}", r3_recipe_package_metrics().unwrap());
    println!(
        "recipe_resource_rows={:?}",
        r3_recipe_resource_rows().unwrap()
    );
}
