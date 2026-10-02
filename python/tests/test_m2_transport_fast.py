from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from golden_board import m2_codec, m2_recipe, m2_route_data


ROOT = Path(__file__).resolve().parents[2]


def _emit(example: str, profile_version: int) -> bytes:
    environment = dict(os.environ)
    if "RUSTC" not in environment:
        environment["RUSTC"] = subprocess.run(
            ["rustup", "which", "--toolchain", "1.97.1", "rustc"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="golden-board-fast-") as directory:
        output = Path(directory) / "package.bin"
        subprocess.run(
            [
                "rustup",
                "run",
                "1.97.1",
                "cargo",
                "run",
                "-q",
                "--locked",
                "--offline",
                "-p",
                "gb-bootstrap",
                "--example",
                example,
                "--",
                str(profile_version),
                str(output),
            ],
            cwd=ROOT,
            env=environment,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return output.read_bytes()


class M2TransportFast(unittest.TestCase):
    def test_literal_direct_eh_and_rs_kats(self) -> None:
        source = bytes.fromhex("0123456789abcdef")
        eh = m2_codec.eh72_encode(source)
        self.assertEqual(eh.hex(), "11121a2a9e26af36de")
        changed = bytearray(eh)
        changed[0] ^= 0x04
        self.assertEqual(m2_codec.eh72_decode(bytes(changed), (6,)).decoded, source)

        rs_source = bytes(range(191))
        rs = m2_codec.rs255_191_encode(rs_source)
        self.assertEqual(
            sha256(rs).hexdigest(),
            "28a63541dcec4e03805a3a66c05fc5bc8efa595a4f339290ccedb7067a60be10",
        )
        changed = bytearray(rs)
        changed[0] ^= 0x53
        decoded = m2_codec.rs255_191_decode(bytes(changed))
        self.assertEqual((decoded.status, decoded.decoded), (0, rs_source))

    def test_canonical_package_identity_parser_and_admission_smoke(self) -> None:
        eh = _emit("dump_eh_package", 1)
        self.assertEqual(
            m2_recipe.smoke_eh72_transport_recipe(1, eh),
            "f030732cd966fd9570149f6fd2d1befb5eed66319eb248b609693e868f977941",
        )

        rs = _emit("dump_rs_decoder_package", 5)
        admission = m2_recipe.smoke_rs_decoder_manifestation(5, rs)
        self.assertEqual(
            admission.package_sha256,
            "2dd94f23f63bd4fbeb8d56565a9cc9a7e0a2054d3483e364cfb60e7751058e91",
        )
        self.assertFalse(admission.recipe_closure_pass)
        self.assertEqual(
            admission.failure_reason, "incomplete_rs_recovery_recipe"
        )
        self.assertFalse(admission.later_resource_gates_evaluated)

        rs_six = _emit("dump_rs_decoder_package", 6)
        admission_six = m2_recipe.smoke_rs_decoder_manifestation(6, rs_six)
        self.assertEqual(
            admission_six.package_sha256,
            "1c05a1f57394d292487f46561492619358fe2d12e42e3a20194d5917f351e555",
        )
        self.assertFalse(admission_six.recipe_closure_pass)
        self.assertEqual(
            admission_six.failure_reason, "incomplete_rs_recovery_recipe"
        )
        self.assertFalse(admission_six.later_resource_gates_evaluated)

    def test_nonzero_mask_route_oracle_smoke(self) -> None:
        manifest = (ROOT / "spec/route-data-v0.json").read_bytes()
        fact = m2_route_data.load_route_data_manifest(manifest)[0][0]
        worked = m2_route_data._mask_input(
            fact.worked_source, fact.source_inputs, fact.mask_input_slots, 0x3C
        )
        held = m2_route_data._mask_input(
            fact.held_source, fact.source_inputs, fact.mask_input_slots, 0x3C
        )
        self.assertEqual(worked, b"\x33")
        self.assertEqual(held, b"\xaa")
        self.assertEqual(
            m2_route_data._expected_nontransport_output(1, fact, worked),
            b"\0\0\xcc",
        )
        self.assertEqual(
            m2_route_data._expected_nontransport_output(1, fact, held),
            b"\0\0\x55",
        )


if __name__ == "__main__":
    unittest.main()
