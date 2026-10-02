#!/usr/bin/env python3
"""Run one bounded, non-persisting R3 D7 cross-language range probe."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile

from golden_board import m2_damage
from tools.m2 import generate_damage


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    maximum_workers = min(8, os.cpu_count() or 1)
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", required=True, type=int)
    parser.add_argument("--stop", required=True, type=int)
    parser.add_argument(
        "--workers", type=int, default=maximum_workers, choices=range(1, maximum_workers + 1)
    )
    arguments = parser.parse_args(argv)
    if (
        not 0 <= arguments.first < arguments.stop <= 408
        or arguments.stop - arguments.first > 32
    ):
        parser.error("require 0 <= first < stop <= 408 and at most 32 ordinals")
    return arguments


def main(argv: list[str] | None = None) -> int:
    arguments = _arguments(argv)
    inputs = generate_damage._owner_inputs()
    rust_decoder = generate_damage._build_rust_binary(
        "gb-r3-damage-decoder"
    )
    with tempfile.TemporaryDirectory(
        prefix="golden-board-r3-d7-probe-", dir="/tmp"
    ) as directory:
        alternate_package = generate_damage.generate_candidates._emit_package(
            3, Path(directory)
        )
        rows = m2_damage.run_r3_d7_range_probe(
            inputs.manifestation,
            inputs.profile,
            inputs.profile_policy_raw,
            inputs.profile_limits_raw,
            inputs.damage_policy_raw,
            alternate_package,
            inputs.alternate_route_data_raw,
            (str(rust_decoder),),
            arguments.workers,
            arguments.first,
            arguments.stop,
        )
    for case_id, digest, wrong_accept_count in rows:
        print(f"{case_id} {digest} wrong_accept={wrong_accept_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
