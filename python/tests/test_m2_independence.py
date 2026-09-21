from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import unittest

from golden_board import canonical_manifest, identity, m2_independence, m2_physical_v2


ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = ROOT / "artifacts" / "candidates"
RETAINED_R3_CANDIDATE = (
    CANDIDATES
    / "eh72-hier-r5-r2-r1-crc32c-v0"
    / "candidate-manifest.json"
).is_file()


def _standalone_proof() -> bytes:
    predicate_ids = (
        "affine-map-bijection",
        "matrix-owner-total-partition",
        "shell-sector-total-partition",
        "protected-unit-total-partition",
        "owner-class-ledger-reconciliation",
        "semantic-copy-required-dependency-separation",
        "single-sector-route-survival",
        "d2-d4-d6-required-closure-survival",
        "damage-promise-binding",
    )
    floors = (1, 1, 1, 1, 1, 2, 3, 1, 1)
    value: dict[str, object] = {
        "schema": m2_independence.SCHEMA,
        "profile_id": "eh72-r3-crc32c-v0",
        "candidate_manifest_sha256": "1" * 64,
        "ownership_ledger_sha256": "2" * 64,
        "damage_manifest_sha256": "3" * 64,
        "predicate_rows": [
            {
                "predicate_id": predicate_id,
                "witness_count": floor,
                "minimum_surviving_count": floor,
                "violation_count": 1,
                "result": "fail",
            }
            for predicate_id, floor in zip(predicate_ids, floors, strict=True)
        ],
        "summary": {"predicate_count": 9, "result": "fail"},
    }
    manifest_identity = identity.identity_hex(
        b"golden-board:manifest:v0\0",
        (canonical_manifest.serialize_manifest(value),),
    )
    value["summary"] = {
        "predicate_count": 9,
        "result": "fail",
        "manifest_identity": manifest_identity,
    }
    return canonical_manifest.serialize_manifest(value)


def _standalone_proof_v1(*, failing_index: int | None = None) -> bytes:
    violations = [0] * 9
    if failing_index is not None:
        violations[failing_index] = 1
    return m2_independence._render_independence_proof_v1(
        "38839aa28561ff2bec0997a80d8dc938e876526c25f40e23b6a78844f8fc1d86",
        "f" * 64,
        "e" * 64,
        violations,
    ).raw


def _refresh_nested_identity(value: dict[str, object]) -> bytes:
    summary = dict(value["summary"])
    summary.pop("manifest_identity")
    omitted = dict(value)
    omitted["summary"] = summary
    summary["manifest_identity"] = identity.identity_hex(
        b"golden-board:manifest:v0\0",
        (canonical_manifest.serialize_manifest(omitted),),
    )
    value["summary"] = summary
    return canonical_manifest.serialize_manifest(value)


class M2IndependenceProof(unittest.TestCase):
    def test_standalone_schema_order_floors_and_identity_are_exact(self) -> None:
        raw = _standalone_proof()
        proof = m2_independence.parse_independence_proof(raw)
        self.assertEqual(proof.raw, raw)
        self.assertEqual(proof.result, "fail")
        self.assertEqual(len(proof.predicate_rows), 9)
        self.assertEqual(
            proof.manifest_identity,
            canonical_manifest.validate_canonical_manifest(raw)["summary"][
                "manifest_identity"
            ],
        )

    def test_standalone_proof_rejects_unknown_key_floor_and_identity_tampering(self) -> None:
        original = canonical_manifest.validate_canonical_manifest(_standalone_proof())
        mutants = []

        unknown = deepcopy(original)
        unknown["extra"] = 0
        mutants.append(unknown)

        floor = deepcopy(original)
        floor["predicate_rows"][5]["minimum_surviving_count"] = 1
        mutants.append(floor)

        result = deepcopy(original)
        result["predicate_rows"][0]["result"] = "pass"
        mutants.append(result)

        identity_mutant = deepcopy(original)
        identity_mutant["summary"]["manifest_identity"] = "0" * 64
        mutants.append(identity_mutant)

        for mutant in mutants:
            with self.subTest(mutant=mutants.index(mutant)), self.assertRaises(
                m2_independence.IndependenceError
            ):
                m2_independence.parse_independence_proof(
                    canonical_manifest.serialize_manifest(mutant)
                )

    def test_v1_standalone_exact_counts_literal_floors_and_failure_are_retained(self) -> None:
        passing = m2_independence.parse_independence_proof(_standalone_proof_v1())
        self.assertEqual(passing.result, "pass")
        self.assertEqual(
            tuple(row["witness_count"] for row in passing.predicate_rows),
            (3_182_656, 4_161_600, 978_944, 3_181_248, 4_161_600,
             1_282_176, 37_844, 1_362, 10_038),
        )
        self.assertEqual(
            tuple(row["minimum_surviving_count"] for row in passing.predicate_rows),
            (1,) * 9,
        )
        failing_raw = _standalone_proof_v1(failing_index=5)
        failing = m2_independence.parse_independence_proof_v1(failing_raw)
        self.assertEqual(failing.result, "fail")
        self.assertEqual(failing.predicate_rows[5]["violation_count"], 1)
        self.assertEqual(failing.raw, failing_raw)

        mutant = canonical_manifest.validate_canonical_manifest(failing_raw)
        mutant["predicate_rows"][0]["witness_count"] += 1
        with self.assertRaisesRegex(
            m2_independence.IndependenceError, "r3-proof-predicate"
        ):
            m2_independence.parse_independence_proof_v1(
                _refresh_nested_identity(mutant)
            )

        mutant = canonical_manifest.validate_canonical_manifest(failing_raw)
        mutant["predicate_rows"][1]["minimum_surviving_count"] = 2
        with self.assertRaisesRegex(
            m2_independence.IndependenceError, "r3-proof-predicate"
        ):
            m2_independence.parse_independence_proof_v1(
                _refresh_nested_identity(mutant)
            )

    def test_current_candidate_ownership_is_a_total_exact_partition(self) -> None:
        bases = sorted(
            path
            for path in CANDIDATES.glob("*")
            if (path / "candidate-manifest.json").is_file()
            and (path / "ownership-ledger.json").is_file()
        )
        if not bases:
            self.skipTest("ignored P6 candidate fixtures are not present")
        expected_hashes = {
            "eh72-r2-crc32c-v0": (
                "75d8b6a518315a707d6c1964001b4482c3913be8c3ba79bb43781e33816e6bbb",
                "bb1b1def3afa01adc47b612fae3b31d9620aa0f70484ae3e69ce75e7fed7f3bc",
            ),
            "eh72-r3-crc32c-v0": (
                "1e1bd5551ee357f3f4b809afba480b379c41b7365b971493db8f3bc2e415168b",
                "d72137c290c35d2fa0da6d09848fdb511ab7f3fe2db1a325a85d16292084b872",
            ),
            "eh72-hier-r5-r2-r1-crc32c-v0": (
                "38839aa28561ff2bec0997a80d8dc938e876526c25f40e23b6a78844f8fc1d86",
                "fe82dc8119d77a855e7227dea95a673e3fb2ffb5a9c513cf31a169ea53ee5d12",
            ),
        }
        for base in bases:
            with self.subTest(profile=base.name):
                candidate_raw = (base / "candidate-manifest.json").read_bytes()
                ownership_raw = (base / "ownership-ledger.json").read_bytes()
                if base.name in expected_hashes:
                    self.assertEqual(
                        (sha256(candidate_raw).hexdigest(), sha256(ownership_raw).hexdigest()),
                        expected_hashes[base.name],
                    )
                schema = canonical_manifest.validate_canonical_manifest(
                    candidate_raw
                )["schema"]
                if schema == "golden-board.m2-candidate-manifest/v2":
                    physical = canonical_manifest.validate_canonical_manifest(
                        m2_physical_v2.build_physical_evidence_v2(
                            candidate_raw,
                            (base / "capacity-ledger.json").read_bytes(),
                            ownership_raw,
                            (base / "semantic-envelope.json").read_bytes(),
                        )
                    )
                    self.assertEqual(
                        tuple(row["witness_count"] for row in physical["predicate_rows"]),
                        (3_297_856, 4_161_600, 863_744, 3_297_024,
                         4_161_600, 2_688_768, 58_776, 1_098),
                    )
                    for row in physical["predicate_rows"]:
                        with self.subTest(predicate=row["predicate_id"]):
                            self.assertEqual(row["violation_count"], 0)
                            self.assertEqual(row["result"], "pass")
                    continue
                if schema == "golden-board.m2-candidate-manifest/v1":
                    candidate = m2_independence._validate_candidate_v1(
                        candidate_raw, ownership_raw
                    )
                    m2_independence._validate_ownership_v1(
                        ownership_raw, candidate
                    )
                    self.assertEqual(
                        tuple(
                            sum(len(group) == factor for group in candidate.groups)
                            for factor in (1, 2, 5)
                        ),
                        (807, 442, 30),
                    )
                    self.assertEqual(len(candidate.groups), 1_279)
                    self.assertTrue(
                        m2_independence._r3_lane_pair_separated(
                            candidate, 1, 2, 0
                        )
                    )
                    self.assertTrue(
                        m2_independence._r3_lane_pair_separated(
                            candidate, 1, 5, 1_727
                        )
                    )
                    continue
                self.assertEqual(schema, "golden-board.m2-candidate-manifest/v0")
                candidate = m2_independence._validate_candidate(
                    candidate_raw, ownership_raw
                )
                ownership = m2_independence._validate_ownership(
                    ownership_raw, candidate
                )
                affine, table, shell, protected, classes = (
                    m2_independence._cell_evidence(candidate, ownership)
                )
                self.assertEqual((affine, table, shell, protected), (0, 0, 0, 0))
                self.assertEqual(sum(classes.values()), candidate.side * candidate.side)
                witnesses, violations = m2_independence._predicate_six(candidate)
                self.assertGreaterEqual(witnesses, 2)
                self.assertEqual(violations, 0)

    @unittest.skipUnless(
        RETAINED_R3_CANDIDATE,
        "retained ignored Gate 1-5 candidate is absent in a clean execution snapshot",
    )
    def test_v1_owner_is_hash_closed_and_d7_descriptor_is_complete(self) -> None:
        base = CANDIDATES / "eh72-hier-r5-r2-r1-crc32c-v0"
        candidate_raw = (base / "candidate-manifest.json").read_bytes()
        ownership_raw = (base / "ownership-ledger.json").read_bytes()
        candidate = m2_independence._validate_candidate_v1(
            candidate_raw, ownership_raw
        )
        self.assertEqual(candidate.protected_bits, 3_181_248)
        descriptors = m2_independence._r3_expected_d7()
        self.assertEqual(len(descriptors), 408)
        self.assertEqual(
            descriptors[0],
            ("OBS_BITS", "mapping-mutants", {"mutant_ordinal": ("u64", 0)}),
        )
        self.assertEqual(
            descriptors[-1],
            ("OBS_BITS", "geometry-one-beyond", {"side": ("u64", 2_056)}),
        )

        mutant = canonical_manifest.validate_canonical_manifest(candidate_raw)
        mutant["carrier_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            m2_independence.IndependenceError, "r3-candidate-sha256"
        ):
            m2_independence._validate_candidate_v1(
                canonical_manifest.serialize_manifest(mutant), ownership_raw
            )

    @unittest.skipUnless(
        RETAINED_R3_CANDIDATE,
        "retained ignored Gate 1-5 candidate is absent in a clean execution snapshot",
    )
    def test_v1_required_closure_micro_projection_is_physical_group_aware(self) -> None:
        base = CANDIDATES / "eh72-hier-r5-r2-r1-crc32c-v0"
        candidate_raw = (base / "candidate-manifest.json").read_bytes()
        ownership_raw = (base / "ownership-ledger.json").read_bytes()
        candidate = m2_independence._validate_candidate_v1(
            candidate_raw, ownership_raw
        )
        top, left = m2_independence._d2_placements(candidate, 55)[0]

        def parameters(rows: list[tuple[str, str, object]]) -> dict[str, object]:
            return {
                "parameter_projection": [
                    {"id": name, "value_type": value_type, "value": value}
                    for name, value_type, value in rows
                ]
            }

        cases = {f"D{index}": () for index in range(8)}
        cases["D2"] = (
            parameters(
                [
                    ("side", "u64", 55),
                    ("top_left", "coordinate-list", [[top, left]]),
                ]
            ),
        )
        cases["D4"] = (
            parameters([("omitted_unit_id", "u64", 1)]),
        )
        cases["D6"] = (
            parameters([("sector_id", "u64", 0), ("unit_id", "u64", 1_841)]),
        )
        damage = m2_independence._DamageV1(
            b"", {}, cases, {f"D{index}": "pass" for index in range(8)}, True
        )
        self.assertEqual(
            m2_independence._r3_closure_evidence(candidate, damage),
            (12, 0),
        )

    @unittest.skip(
        "superseded unbounded retained-v0 proof walk; bounded compatibility remains"
    )
    def test_full_retained_evidence_recomputes_byte_exact_when_available(self) -> None:
        damage_bases = sorted(
            path / "damage"
            for path in CANDIDATES.glob("*")
            if (path / "damage" / "damage-manifest.json").is_file()
        )
        if not damage_bases:
            self.skipTest("ignored P7 damage fixtures are not present")
        for damage in damage_bases:
            base = damage.parent
            family_raws = tuple(
                (damage / f"damage-D{index}.json").read_bytes()
                for index in range(8)
            )
            shard_raws = tuple(
                path.read_bytes()
                for path in sorted(damage.glob("damage-D*-cases-*.json"))
            )
            candidate_raw = (base / "candidate-manifest.json").read_bytes()
            ownership_raw = (base / "ownership-ledger.json").read_bytes()
            damage_raw = (damage / "damage-manifest.json").read_bytes()
            with self.subTest(profile=base.name):
                proof = m2_independence.build_independence_proof(
                    candidate_raw,
                    ownership_raw,
                    damage_raw,
                    family_raws,
                    shard_raws,
                )
                self.assertEqual(
                    m2_independence.validate_independence_proof(
                        proof.raw,
                        candidate_raw,
                        ownership_raw,
                        damage_raw,
                        family_raws,
                        shard_raws,
                    ),
                    proof,
                )
                tampered = canonical_manifest.validate_canonical_manifest(proof.raw)
                tampered["ownership_ledger_sha256"] = "0" * 64
                with self.assertRaises(m2_independence.IndependenceError):
                    m2_independence.validate_independence_proof(
                        canonical_manifest.serialize_manifest(tampered),
                        candidate_raw,
                        ownership_raw,
                        damage_raw,
                        family_raws,
                        shard_raws,
                    )

    def test_candidate_and_ownership_bindings_fail_closed(self) -> None:
        base = CANDIDATES / "eh72-r3-crc32c-v0"
        if not (base / "candidate-manifest.json").is_file():
            self.skipTest("ignored P6 candidate fixture is not present")
        candidate_raw = (base / "candidate-manifest.json").read_bytes()
        ownership_raw = (base / "ownership-ledger.json").read_bytes()

        candidate = canonical_manifest.validate_canonical_manifest(candidate_raw)
        candidate["carrier_sha256"] = "0" * 64
        with self.assertRaises(m2_independence.IndependenceError):
            m2_independence._validate_candidate(
                canonical_manifest.serialize_manifest(candidate), ownership_raw
            )

        ownership = canonical_manifest.validate_canonical_manifest(ownership_raw)
        ownership["cell_table_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            m2_independence.IndependenceError, "candidate-ownership-binding"
        ):
            m2_independence._validate_candidate(
                candidate_raw, canonical_manifest.serialize_manifest(ownership)
            )


if __name__ == "__main__":
    unittest.main()
