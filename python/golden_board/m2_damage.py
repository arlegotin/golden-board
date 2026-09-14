"""Frozen M2 damage generation and independent expected-state oracle.

The module consumes a complete P6 manifestation.  It never changes candidate
bytes or policy choices: observations are derived from the frozen D0--D7
owner and summarized as one closed canonical manifest.  A separate evaluator
must consume the serialized observation bytes before any gate result is set.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import multiprocessing
from multiprocessing.util import Finalize
import os
import select
import subprocess
from time import monotonic
import tomllib
from typing import Iterable, NoReturn, Sequence

from . import (
    bootstrap,
    canonical_manifest,
    identity,
    m2_carrier,
    m2_codec,
    m2_decoder,
    m2_policy,
    m2_route_data,
)


DAMAGE_SCHEMA = "golden-board.m2-damage-manifest/v0"
R3_DAMAGE_SCHEMA = "golden-board.m2-damage-manifest/v1"
R3_FAMILY_SCHEMA = "golden-board.m2-damage-family/v1"
R3_SHARD_SCHEMA = "golden-board.m2-damage-cases/v1"
R3_BOUNDARY_SCHEMA = "golden-board.m2-boundary-kat-result/v1"
R3_PROFILE_ID = "eh72-hier-r5-r2-r1-crc32c-v0"
R3_BOUNDARY_KAT_IDS = (
    "rep2-correction-boundary",
    "rep5-correction-boundary",
    "complete-section-conflict",
    "section-attempt-ceiling-plus-one",
)
R3_FAMILY_IDS = tuple(f"D{index}" for index in range(8))
R3_FAMILY_CASE_COUNTS = (16, 4, 256, 128, 1_841, 21, 7_364, 408)
R3_FAMILY_GUARANTEES = (
    "all_declared_m2_sections_exact",
    "all_declared_m2_sections_exact",
    "m2_required_closure",
    "m2_required_closure",
    "m2_required_closure",
    "all_declared_m2_sections_exact",
    "m2_required_closure",
    "correct_or_explicit_failure",
)
R3_BOUNDARY_KAT_SHA256 = (
    "452d38bd592174b0fb022cee41e4f261768957811893ae471934bf3e4e8e6622",
    "5158867ec6d4c740afec018f5695a51779ca54758113303d3b656c4b6ee1f01e",
    "9508a43cc54c7f6dc06fcee677a18db1ed57bfdb87e1c5f692d332642a3c5b56",
    "966307a69ded9f055704443e6c6c46b4d0226a4a4bced398e0573fe5afe03187",
)
R3_CANDIDATE_MANIFEST_SHA256 = (
    "38839aa28561ff2bec0997a80d8dc938e876526c25f40e23b6a78844f8fc1d86"
)
_SAMPLE_DOMAIN = bytes.fromhex("47422d44414d4147452d763000")
_WINDOW_DOMAIN = bytes.fromhex("47422d44414d4147452d57494e444f572d763000")
_MAX_DECODER_FRAME_BYTES = 4_194_306
_MAX_DECODER_RESULT_BYTES = 1_048_576


class DamageError(ValueError):
    __slots__ = ("reason",)

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class RustBatchDecoder:
    """Bounded client for the independent fresh-per-frame Rust decoder."""

    __slots__ = ("_process", "_timeout", "_closed")

    def __init__(
        self, command: Sequence[str], *, timeout_seconds: float = 60.0
    ) -> None:
        if (
            isinstance(command, (str, bytes, bytearray))
            or not 1 <= len(command) <= 16
            or any(
                type(item) is not str or not 1 <= len(item) <= 4_096
                for item in command
            )
            or type(timeout_seconds) not in (int, float)
            or not 1.0 <= timeout_seconds <= 600.0
        ):
            _fail("rust-decoder-command")
        try:
            self._process = subprocess.Popen(
                tuple(command),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        except (OSError, ValueError) as error:
            raise DamageError("rust-decoder-start") from error
        if self._process.stdin is None or self._process.stdout is None:
            self._process.kill()
            self._process.wait()
            _fail("rust-decoder-start")
        self._timeout = float(timeout_seconds)
        self._closed = False

    def __enter__(self) -> RustBatchDecoder:
        return self

    def _transfer(self, descriptor: int, data: bytes, write: bool) -> bytes:
        deadline = monotonic() + self._timeout
        cursor = 0
        output = bytearray()
        while cursor < len(data):
            remaining = deadline - monotonic()
            if remaining <= 0:
                _fail("rust-decoder-timeout")
            readable, writable, _ = select.select(
                () if write else (descriptor,),
                (descriptor,) if write else (),
                (),
                remaining,
            )
            if write:
                if not writable:
                    _fail("rust-decoder-timeout")
                try:
                    consumed = os.write(descriptor, data[cursor:])
                except OSError as error:
                    raise DamageError("rust-decoder-framing") from error
                if consumed <= 0:
                    _fail("rust-decoder-framing")
                cursor += consumed
            else:
                if not readable:
                    _fail("rust-decoder-timeout")
                try:
                    chunk = os.read(descriptor, len(data) - cursor)
                except OSError as error:
                    raise DamageError("rust-decoder-framing") from error
                if not chunk:
                    _fail("rust-decoder-short-read")
                output.extend(chunk)
                cursor += len(chunk)
        return bytes(output)

    def _exchange(self, channel_id: int, raw: bytes) -> bytes:
        if self._closed or self._process.poll() is not None:
            _fail("rust-decoder-exited")
        if (
            type(channel_id) is not int
            or not 0 <= channel_id <= 255
            or type(raw) is not bytes
            or len(raw) > _MAX_DECODER_FRAME_BYTES
        ):
            _fail("rust-decoder-frame")
        stdin = self._process.stdin
        stdout = self._process.stdout
        assert stdin is not None and stdout is not None
        frame = bytes((channel_id,)) + len(raw).to_bytes(4, "big") + raw
        self._transfer(stdin.fileno(), frame, True)
        length_raw = self._transfer(stdout.fileno(), bytes(4), False)
        length = int.from_bytes(length_raw, "big")
        if not 1 <= length <= _MAX_DECODER_RESULT_BYTES:
            _fail("rust-decoder-result-length")
        return self._transfer(stdout.fileno(), bytes(length), False)

    def decode(self, channel: str, raw: bytes) -> bytes:
        channel_id = {"OBS_BITS": 0, "OBS_MATRIX": 1, "OBS_UNITS": 2}.get(
            channel
        )
        if channel_id is None:
            _fail("rust-decoder-frame")
        return self._exchange(channel_id, raw)

    def boundary_kat(self, ordinal: int | None = None) -> bytes:
        if ordinal is None:
            payload = b""
        elif type(ordinal) is int and 0 <= ordinal <= 3:
            payload = bytes((ordinal,))
        else:
            _fail("boundary-kat")
        return self._exchange(255, payload)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        stdin = self._process.stdin
        stdout = self._process.stdout
        try:
            if stdin is not None:
                stdin.close()
            try:
                status = self._process.wait(timeout=self._timeout)
            except subprocess.TimeoutExpired as error:
                self._process.kill()
                self._process.wait()
                raise DamageError("rust-decoder-close-timeout") from error
            if status != 0:
                _fail("rust-decoder-exit")
        finally:
            if stdout is not None:
                stdout.close()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        try:
            self.close()
        except DamageError:
            if exc is None:
                raise


_WORKER_POLICY_RAW: bytes | None = None
_WORKER_LIMITS_RAW: bytes | None = None
_WORKER_DAMAGE_RAW: bytes | None = None
_WORKER_CLEAN_ENVELOPES: dict[int, bytes] | None = None
_WORKER_RUST_DECODER: RustBatchDecoder | None = None
_WORKER_FINALIZER: Finalize | None = None
_WORKER_RESULT_SCHEMA_VERSION: int | None = None


def _decoder_worker_finalize() -> None:
    global _WORKER_RUST_DECODER
    decoder = _WORKER_RUST_DECODER
    _WORKER_RUST_DECODER = None
    if decoder is not None:
        try:
            decoder.close()
        except DamageError:
            pass


def _decoder_worker_initialize(
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    damage_policy_raw: bytes,
    clean_envelopes: dict[int, bytes],
    rust_decoder_command: tuple[str, ...] | None,
) -> None:
    global _WORKER_POLICY_RAW
    global _WORKER_LIMITS_RAW
    global _WORKER_DAMAGE_RAW
    global _WORKER_CLEAN_ENVELOPES
    global _WORKER_RUST_DECODER
    global _WORKER_FINALIZER
    global _WORKER_RESULT_SCHEMA_VERSION
    _WORKER_POLICY_RAW = profile_policy_raw
    _WORKER_LIMITS_RAW = profile_limits_raw
    _WORKER_DAMAGE_RAW = damage_policy_raw
    _WORKER_CLEAN_ENVELOPES = clean_envelopes
    _WORKER_RESULT_SCHEMA_VERSION = m2_decoder.ObservationDecoder(
        profile_policy_raw, profile_limits_raw, damage_policy_raw
    ).result_schema_version
    _WORKER_RUST_DECODER = (
        None
        if rust_decoder_command is None
        else RustBatchDecoder(rust_decoder_command)
    )
    _WORKER_FINALIZER = Finalize(
        None, _decoder_worker_finalize, exitpriority=10
    )


def _decoder_worker_evaluate(
    task: tuple[str, str, bytes],
) -> tuple[
    str,
    bytes,
    bytes | None,
    str,
    tuple[tuple[int, str], ...],
    int,
]:
    case_id, channel, observation = task
    if (
        _WORKER_POLICY_RAW is None
        or _WORKER_LIMITS_RAW is None
        or _WORKER_DAMAGE_RAW is None
        or _WORKER_CLEAN_ENVELOPES is None
        or _WORKER_RESULT_SCHEMA_VERSION is None
    ):
        _fail("decoder-worker")
    decoder = m2_decoder.ObservationDecoder(
        _WORKER_POLICY_RAW, _WORKER_LIMITS_RAW, _WORKER_DAMAGE_RAW
    )
    if decoder.result_schema_version != _WORKER_RESULT_SCHEMA_VERSION:
        _fail("decoder-worker-owner")
    try:
        actual = decoder.decode(channel, observation)
    except m2_decoder.DecoderError as error:
        actual = m2_decoder.DecodeResult(
            "resource-limit" if error.reason == "resource-limit" else "failure",
            None,
            (),
            (),
            False,
        )
    actual_raw = decoder.render_result(channel, actual)
    rust_raw = (
        None
        if _WORKER_RUST_DECODER is None
        else _WORKER_RUST_DECODER.decode(channel, observation)
    )
    actual_by_id = {item.section_id: item for item in actual.section_results}
    states = tuple(
        (
            section_id,
            (
                actual_by_id[section_id].state
                if section_id in actual_by_id
                else "unknown"
            ),
        )
        for section_id in sorted(_WORKER_CLEAN_ENVELOPES)
    )
    wrong = sum(
        item.envelope is not None
        and _WORKER_CLEAN_ENVELOPES.get(item.section_id) != item.envelope
        for item in actual.section_results
    )
    return case_id, actual_raw, rust_raw, actual.artifact_state, states, wrong


def _decoder_worker_boundary_kat(ordinal: int | None) -> bytes:
    if _WORKER_RUST_DECODER is None:
        _fail("decoder-worker")
    return _WORKER_RUST_DECODER.boundary_kat(ordinal)


@dataclass(frozen=True, slots=True)
class DamageRun:
    profile_id: str
    manifest: bytes
    manifest_identity: str
    family_manifests: tuple[bytes, ...]
    case_shards: tuple[tuple[str, bytes], ...]
    case_count: int
    family_case_counts: tuple[tuple[str, int], ...]
    wrong_accept_count: int
    gate6_result: str
    gate7_result: str
    bundle_case_preimages: tuple[tuple[str, str, bytes, bytes], ...] = ()


@dataclass(frozen=True, slots=True)
class DamageBundleV1:
    """Strictly admitted gate-6 v1 root/family/shard projection."""

    root: dict[str, object]
    families: tuple[dict[str, object], ...]
    shards: tuple[tuple[str, dict[str, object]], ...]
    case_rows_by_family: tuple[tuple[dict[str, object], ...], ...]
    result: str


@dataclass(frozen=True, slots=True)
class _Result:
    artifact_state: str
    section_states: tuple[tuple[int, str], ...]
    wrong_accepts: int
    decoder_base: m2_decoder.DecodeResult


@dataclass(frozen=True, slots=True)
class _DamageCaseSpec:
    channel: str
    operator: str
    parameters: dict[str, tuple[str, object]]
    observation: bytes
    expected: _Result


def _fail(reason: str) -> NoReturn:
    raise DamageError(reason)


def _bits(raw: bytes, count: int | None = None) -> bytearray:
    values = bytearray((byte >> shift) & 1 for byte in raw for shift in range(7, -1, -1))
    return values if count is None else values[:count]


def _packed(values: Sequence[int]) -> bytes:
    result = bytearray((len(values) + 7) // 8)
    for index, value in enumerate(values):
        if value not in (0, 1):
            _fail("bit-value")
        result[index // 8] |= value << (7 - index % 8)
    return bytes(result)


def _obs_bits(values: Sequence[int]) -> bytes:
    return len(values).to_bytes(4, "big") + _packed(values)


def _obs_matrix(side: int, values: bytes | bytearray) -> bytes:
    if (
        len(values) != side * side
        or values.count(0) + values.count(1) + values.count(2) != len(values)
    ):
        _fail("matrix-value")
    return side.to_bytes(2, "big") + bytes(values)


def _obs_units(order: Sequence[int], encoded: dict[int, bytes]) -> bytes:
    result = bytearray(len(order).to_bytes(4, "big"))
    seen: set[int] = set()
    for unit_id in order:
        value = encoded[unit_id]
        if unit_id in seen or not 1 <= unit_id <= 0xFFFF_FFFF or len(value) > 0xFFFF:
            _fail("unit-observation")
        seen.add(unit_id)
        result.extend(unit_id.to_bytes(4, "big"))
        result.extend(len(value).to_bytes(2, "big"))
        result.extend(value)
    return bytes(result)


def _replace_sector_route_prefix(
    matrix: bytearray,
    side: int,
    width: int,
    sector: m2_route_data.SectorImage,
) -> None:
    """Replace exactly one route prefix, preserving headroom and fixed pad."""

    if (
        type(matrix) is not bytearray
        or len(matrix) != side * side
        or type(sector) is not m2_route_data.SectorImage
        or not 0 <= sector.sector_id <= 3
        or not 0 < sector.route_prefix_cells <= len(sector.data) * 8
    ):
        _fail("alternate-route-owner")
    alternate_bits = _bits(sector.data, sector.route_prefix_cells)
    for local, bit in enumerate(alternate_bits):
        row, column = bootstrap.sector_cell(
            side, width, sector.sector_id, local
        )
        matrix[row * side + column] = bit


def _obs_unit_ids(raw: bytes) -> tuple[int, ...]:
    if type(raw) is not bytes or len(raw) < 4:
        _fail("unit-observation")
    count = int.from_bytes(raw[:4], "big")
    cursor = 4
    result: list[int] = []
    for _ in range(count):
        if cursor + 6 > len(raw):
            _fail("unit-observation")
        unit_id = int.from_bytes(raw[cursor : cursor + 4], "big")
        length = int.from_bytes(raw[cursor + 4 : cursor + 6], "big")
        cursor += 6
        if cursor + length > len(raw):
            _fail("unit-observation")
        result.append(unit_id)
        cursor += length
    if cursor != len(raw) or len(set(result)) != len(result):
        _fail("unit-observation")
    return tuple(result)


def _transport_lane_invocations(profile: m2_codec.CandidateProfile) -> int:
    return (
        24
        if profile.transport_id
        in (m2_codec.EH_TRANSPORT, m2_codec.HIER_TRANSPORT)
        else 1
    )


def _transform_coordinate(side: int, transform: int, row: int, column: int) -> tuple[int, int]:
    last = side - 1
    return (
        (row, column),
        (last - column, row),
        (last - row, last - column),
        (column, last - row),
        (row, last - column),
        (last - column, last - row),
        (last - row, column),
        (column, row),
    )[transform]


def _transform_matrix(clean: Sequence[int], side: int, transform: int, polarity: int) -> bytearray:
    observed = bytearray(side * side)
    for at, value in enumerate(clean):
        row, column = divmod(at, side)
        out_row, out_column = _transform_coordinate(side, transform, row, column)
        observed[out_row * side + out_column] = value ^ polarity
    return observed


def _sample_indices(population: int, count: int, seed: int, domain: bytes = _SAMPLE_DOMAIN) -> tuple[int, ...]:
    if not 0 <= count <= population or population <= 0:
        _fail("sample-population")
    limit = ((1 << 64) // population) * population
    selected: set[int] = set()
    result: list[int] = []
    counter = 0
    retry_max = population * 64 + 1024
    while len(result) < count:
        if counter >= retry_max or counter > 0xFFFF_FFFF_FFFF_FFFF:
            _fail("sample-resource")
        digest = sha256(domain + seed.to_bytes(8, "big") + counter.to_bytes(8, "big")).digest()
        counter += 1
        for offset in range(0, 32, 8):
            word = int.from_bytes(digest[offset : offset + 8], "big")
            if word >= limit:
                continue
            index = word % population
            if index not in selected:
                selected.add(index)
                result.append(index)
                if len(result) == count:
                    break
    return tuple(result)


def _two_unbiased_indices(population: int, seed: int, domain: bytes) -> tuple[int, int]:
    if population <= 0:
        _fail("sample-population")
    limit = ((1 << 64) // population) * population
    result: list[int] = []
    counter = 0
    while len(result) < 2:
        if counter >= population * 64 + 1024:
            _fail("sample-resource")
        digest = sha256(
            domain + seed.to_bytes(8, "big") + counter.to_bytes(8, "big")
        ).digest()
        counter += 1
        for offset in range(0, 32, 8):
            word = int.from_bytes(digest[offset : offset + 8], "big")
            if word < limit:
                result.append(word % population)
                if len(result) == 2:
                    break
    return result[0], result[1]


def _fisher_yates(values: Sequence[int], seed: int) -> tuple[int, ...]:
    work = list(values)
    counter = 0
    words: list[int] = []

    def next_index(population: int) -> int:
        nonlocal counter, words
        limit = ((1 << 64) // population) * population
        while True:
            if not words:
                if counter >= population * 64 + 1024:
                    _fail("sample-resource")
                digest = sha256(
                    _SAMPLE_DOMAIN
                    + seed.to_bytes(8, "big")
                    + counter.to_bytes(8, "big")
                ).digest()
                counter += 1
                words = [
                    int.from_bytes(digest[offset : offset + 8], "big")
                    for offset in range(0, 32, 8)
                ]
            word = words.pop(0)
            if word < limit:
                return word % population

    for index in range(len(work) - 1, 0, -1):
        chosen = next_index(index + 1)
        work[index], work[chosen] = work[chosen], work[index]
    return tuple(work)


def _parameter_rows(values: dict[str, tuple[str, object]]) -> list[dict[str, object]]:
    rows = []
    for name in sorted(values):
        value_type, value = values[name]
        if value_type not in ("u64", "ascii", "u64-list", "coordinate-list"):
            _fail("parameter-shape")
        rows.append({"id": name, "value_type": value_type, "value": value})
    return rows


def _canonical_array_sha256(rows: Sequence[dict[str, object]]) -> str:
    """Hash an exact canonical bare array without an artifact-size cap."""

    digest = sha256()
    digest.update(b"[")
    for index, row in enumerate(rows):
        raw = canonical_manifest.serialize_manifest(row)
        if not raw.endswith(b"\n"):
            _fail("case-row-canonical")
        if index:
            digest.update(b",")
        digest.update(raw[:-1])
    digest.update(b"]")
    return digest.hexdigest()


_R3_ROOT_KEYS = frozenset(
    {
        "schema",
        "damage_policy_sha256",
        "profile_policy_sha256",
        "profile_limits_sha256",
        "bootstrap_spec_sha256",
        "route_data_sha256",
        "recipient_package_sha256",
        "profile_id",
        "candidate_manifest_sha256",
        "clean_observation_sha256",
        "family_rows",
        "boundary_kat_rows",
        "summary",
    }
)
_R3_FAMILY_ROW_KEYS = frozenset(
    {"family_id", "case_count", "wrong_accept_count", "result", "case_rows_sha256"}
)
_R3_BOUNDARY_ROW_KEYS = frozenset({"kat_id", "result_sha256", "result"})
_R3_ROOT_SUMMARY_KEYS = frozenset(
    {"family_case_counts", "wrong_accept_count", "manifest_identity"}
)
_R3_FAMILY_KEYS = frozenset(
    {
        "schema",
        "damage_manifest_identity",
        "profile_id",
        "family_id",
        "guarantee_id",
        "shard_rows",
        "summary",
    }
)
_R3_SHARD_REF_KEYS = frozenset(
    {"shard_ordinal", "case_first", "case_count", "manifest_sha256"}
)
_R3_FAMILY_SUMMARY_KEYS = frozenset(
    {"case_count", "wrong_accept_count", "result", "manifest_identity"}
)
_R3_SHARD_KEYS = frozenset(
    {
        "schema",
        "damage_manifest_identity",
        "profile_id",
        "family_id",
        "shard_ordinal",
        "case_first",
        "case_rows",
        "summary",
    }
)
_R3_SHARD_SUMMARY_KEYS = frozenset(
    {"case_count", "wrong_accept_count", "manifest_identity"}
)
_R3_CASE_KEYS = frozenset(
    {
        "case_id",
        "family_id",
        "channel",
        "operator",
        "parameter_projection",
        "observation_sha256",
        "decoder_result_sha256",
        "expected_artifact_state",
        "expected_section_states",
        "wrong_accept_count",
    }
)
_R3_PARAMETER_KEYS = frozenset({"id", "value_type", "value"})
_R3_SECTION_STATE_KEYS = frozenset({"section_id", "state"})
_R3_CANDIDATE_KEYS = frozenset(
    {
        "schema",
        "profile_policy_sha256",
        "profile_limits_sha256",
        "bootstrap_spec_sha256",
        "route_data_sha256",
        "recipient_package_sha256",
        "profile_id",
        "profile_version",
        "semantic_envelope_sha256",
        "side",
        "shell_width",
        "mapping",
        "shell_rows",
        "section_rows",
        "unit_rows",
        "ownership_sha256",
        "capacity_ledger_sha256",
        "density_ledger_sha256",
        "carrier_sha256",
        "ledger",
        "manifest_identity",
    }
)
_R3_HEX = frozenset("0123456789abcdef")
_R3_SECTION_STATES = frozenset(
    {"verified", "recovered", "incomplete", "corrupt", "ambiguous", "unknown"}
)
_R3_ARTIFACT_STATES = frozenset(
    {"exact", "degraded", "failure", "ambiguous", "resource-limit"}
)
_R3_FAMILY_COUNT_ROW_KEYS = frozenset({"family_id", "case_count"})
_R3_D7_CASE_BLOCKS = (
    ("mapping-mutants", "OBS_BITS", 3, (("mutant_ordinal", "u64"),)),
    (
        "check-mutants",
        "OBS_UNITS",
        2,
        (("case_ordinal", "u64"), ("target_unit_ids", "u64-list")),
    ),
    (
        "check-mutants",
        "OBS_UNITS",
        2,
        (("case_ordinal", "u64"), ("section_id", "u64")),
    ),
    (
        "code-mutants",
        "OBS_UNITS",
        3,
        (("case_ordinal", "u64"), ("target_unit_ids", "u64-list")),
    ),
    (
        "route-conflicts",
        "OBS_BITS",
        1,
        (("alternate_profile_version", "u64"),),
    ),
    (
        "cross-profile-splices",
        "OBS_UNITS",
        5,
        (("source_profile_version", "u64"), ("target_unit_ids", "u64-list")),
    ),
    (
        "valid-copy-conflicts",
        "OBS_UNITS",
        1,
        (("section_id", "u64"), ("target_unit_id", "u64")),
    ),
    (
        "d2-one-beyond",
        "OBS_MATRIX",
        256,
        (("d2_ordinal", "u64"), ("side", "u64")),
    ),
    ("d3-one-beyond", "OBS_MATRIX", 128, (("seed", "u64"),)),
    (
        "missing-unit-one-beyond",
        "OBS_UNITS",
        1,
        (("omitted_unit_ids", "u64-list"),),
    ),
    (
        "algebraic-one-beyond",
        "OBS_MATRIX",
        3,
        (("erasures", "u64"), ("errors", "u64"), ("target_unit_ids", "u64-list")),
    ),
    (
        "resource-route-one-beyond",
        "OBS_BITS",
        2,
        (("declared_value", "u64"),),
    ),
    ("geometry-one-beyond", "OBS_BITS", 1, (("side", "u64"),)),
)


def _r3_damage_manifest(raw: bytes, schema: str, reason: str) -> dict[str, object]:
    if type(raw) is not bytes or not 1 <= len(raw) <= 1_048_576:
        _fail(reason)
    try:
        value = canonical_manifest.validate_canonical_manifest(raw)
    except (TypeError, ValueError) as error:
        raise DamageError(reason) from error
    if type(value) is not dict or value.get("schema") != schema:
        _fail(reason)
    return value


def _r3_hex64(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in _R3_HEX for character in value)
    )


def _r3_u64(value: object) -> bool:
    return type(value) is int and 0 <= value <= 0xFFFF_FFFF_FFFF_FFFF


def _r3_nested_identity(value: dict[str, object]) -> str:
    summary = value.get("summary")
    if type(summary) is not dict or "manifest_identity" not in summary:
        _fail("r3-damage-identity")
    projected = dict(value)
    projected_summary = dict(summary)
    projected_summary.pop("manifest_identity")
    projected["summary"] = projected_summary
    return identity.identity_hex(
        b"golden-board:manifest:v0\0",
        (canonical_manifest.serialize_manifest(projected),),
    )


def _r3_case_shape(
    family: str, ordinal: int
) -> tuple[str, str, tuple[tuple[str, str], ...], int]:
    if family == "D0":
        return (
            "OBS_BITS",
            "clean-transform-polarity",
            (("polarity_id", "u64"), ("transform_id", "u64")),
            ordinal,
        )
    if family == "D1":
        return (
            "OBS_MATRIX",
            "erase-one-complete-shell-sector",
            (("sector_id", "u64"),),
            ordinal,
        )
    if family == "D2":
        return (
            "OBS_MATRIX",
            "erase-square-in-protected-interior",
            (("side", "u64"), ("top_left", "coordinate-list")),
            ordinal,
        )
    if family == "D3":
        return (
            "OBS_MATRIX",
            "fixed-weight-unknown-bit-substitution",
            (("coordinates", "coordinate-list"), ("seed", "u64"), ("stratum_id", "u64")),
            ordinal,
        )
    if family == "D4":
        return (
            "OBS_UNITS",
            "omit-one-physical-unit-observation",
            (("omitted_unit_id", "u64"),),
            ordinal,
        )
    if family == "D5":
        return (
            "OBS_UNITS",
            "permute-intact-physical-unit-observations",
            (("permutation_ordinal", "u64"),),
            ordinal,
        )
    if family == "D6":
        return (
            "OBS_MATRIX",
            "erase-shell-sector-union-one-physical-unit-cell-set",
            (("sector_id", "u64"), ("unit_id", "u64")),
            ordinal,
        )
    if family != "D7":
        _fail("r3-damage-case-family")
    cursor = 0
    for operator, channel, count, projection in _R3_D7_CASE_BLOCKS:
        if ordinal < cursor + count:
            subordinal = ordinal - cursor
            if operator == "check-mutants" and "section_id" in {
                item[0] for item in projection
            }:
                subordinal += 2
            return channel, operator, projection, subordinal
        cursor += count
    _fail("r3-damage-case-ordinal")


class _R3ParameterContext:
    """The bounded geometry projection used to bind case parameters."""

    __slots__ = (
        "side",
        "width",
        "interior",
        "population",
        "mapping",
        "section_rows",
        "unit_rows",
        "unit_bits",
        "d3_population_cache",
    )

    def __init__(self, candidate: dict[str, object]) -> None:
        try:
            self.side = int(candidate["side"])
            self.width = int(candidate["shell_width"])
            self.mapping = candidate["mapping"]
            self.section_rows = tuple(candidate["section_rows"])
            self.unit_rows = tuple(candidate["unit_rows"])
        except (KeyError, TypeError, ValueError) as error:
            raise DamageError("r3-damage-candidate") from error
        if type(self.mapping) is not dict:
            _fail("r3-damage-candidate")
        self.interior = self.side - 2 * self.width
        self.population = self.interior * self.interior
        self.unit_bits = 1_728
        self.d3_population_cache: dict[int, tuple[int, ...]] = {}

    def physical_cell(self, unit_id: int, bit_offset: int) -> int:
        try:
            return m2_carrier.map_unit_bit(
                self.mapping, unit_id, bit_offset
            )
        except m2_carrier.CarrierError as error:
            raise DamageError("r3-damage-mapping") from error


def _r3_validate_parameter_value(row: dict[str, object]) -> None:
    value_type = row.get("value_type")
    value = row.get("value")
    if value_type == "u64":
        if not _r3_u64(value):
            _fail("r3-damage-parameter")
    elif value_type == "ascii":
        if type(value) is not str:
            _fail("r3-damage-parameter")
        try:
            encoded = value.encode("ascii")
        except UnicodeError as error:
            raise DamageError("r3-damage-parameter") from error
        if len(encoded) > 128:
            _fail("r3-damage-parameter")
    elif value_type == "u64-list":
        if (
            type(value) is not list
            or len(value) > 4_194_304
            or any(not _r3_u64(item) for item in value)
        ):
            _fail("r3-damage-parameter")
    elif value_type == "coordinate-list":
        if (
            type(value) is not list
            or len(value) > 4_194_304
            or any(
                type(item) is not list
                or len(item) != 2
                or any(type(axis) is not int or not 0 <= axis <= 0xFFFF_FFFF for axis in item)
                for item in value
            )
        ):
            _fail("r3-damage-parameter")
    else:
        _fail("r3-damage-parameter")


def _r3_validate_case(
    row: object,
    family: str,
    ordinal: int,
    section_ids: tuple[int, ...],
    parameter_context: _R3ParameterContext,
) -> dict[str, object]:
    if type(row) is not dict or set(row) != _R3_CASE_KEYS:
        _fail("r3-damage-case")
    channel, operator, projection, subordinal = _r3_case_shape(family, ordinal)
    parameters = row.get("parameter_projection")
    states = row.get("expected_section_states")
    if (
        row.get("case_id") != f"{family}-{ordinal:06d}"
        or row.get("family_id") != family
        or row.get("channel") != channel
        or row.get("operator") != operator
        or type(parameters) is not list
        or tuple(
            (item.get("id"), item.get("value_type"))
            if type(item) is dict
            else (None, None)
            for item in parameters
        )
        != projection
        or any(type(item) is not dict or set(item) != _R3_PARAMETER_KEYS for item in parameters)
        or not _r3_hex64(row.get("observation_sha256"))
        or not _r3_hex64(row.get("decoder_result_sha256"))
        or row.get("expected_artifact_state") not in _R3_ARTIFACT_STATES
        or not _r3_u64(row.get("wrong_accept_count"))
        or type(states) is not list
        or tuple(
            item.get("section_id") if type(item) is dict else None
            for item in states
        )
        != section_ids
        or any(
            type(item) is not dict
            or set(item) != _R3_SECTION_STATE_KEYS
            or item.get("state") not in _R3_SECTION_STATES
            for item in states
        )
    ):
        _fail("r3-damage-case")
    for item in parameters:
        _r3_validate_parameter_value(item)
    parameter_values = {str(item["id"]): item["value"] for item in parameters}
    if "case_ordinal" in parameter_values and parameter_values["case_ordinal"] != subordinal:
        _fail("r3-damage-parameter-binding")
    if "target_unit_ids" in parameter_values and parameter_values["target_unit_ids"] != [1, 2, 3, 4, 5]:
        _fail("r3-damage-parameter-binding")
    if "omitted_unit_ids" in parameter_values and parameter_values["omitted_unit_ids"] != [1, 2, 3, 4, 5]:
        _fail("r3-damage-parameter-binding")
    if operator == "valid-copy-conflicts" and (
        parameter_values != {"section_id": 1, "target_unit_id": 1}
    ):
        _fail("r3-damage-parameter-binding")
    if operator == "route-conflicts" and parameter_values.get("alternate_profile_version") != 3:
        _fail("r3-damage-parameter-binding")
    if family == "D0" and parameter_values != {
        "polarity_id": ordinal % 2,
        "transform_id": ordinal // 2,
    }:
        _fail("r3-damage-parameter-binding")
    if family == "D1" and parameter_values.get("sector_id") != ordinal:
        _fail("r3-damage-parameter-binding")
    if family == "D4" and parameter_values.get("omitted_unit_id") != ordinal + 1:
        _fail("r3-damage-parameter-binding")
    if family == "D5" and parameter_values.get("permutation_ordinal") != ordinal:
        _fail("r3-damage-parameter-binding")
    if family == "D6" and parameter_values != {
        "sector_id": ordinal // 1_841,
        "unit_id": ordinal % 1_841 + 1,
    }:
        _fail("r3-damage-parameter-binding")
    if family == "D2":
        square = max(32, parameter_context.interior // 32)
        placements = _d2_placements(parameter_context, square)
        top, left = placements[ordinal]
        if parameter_values != {
            "side": square,
            "top_left": [[top, left]],
        }:
            _fail("r3-damage-parameter-binding")
    if family == "D3":
        coordinates = _d3_coordinates(parameter_context, ordinal)
        if parameter_values != {
            "coordinates": [list(item) for item in coordinates],
            "seed": 5_134_751_402_299_490_304 + ordinal,
            "stratum_id": ordinal // 32,
        }:
            _fail("r3-damage-parameter-binding")
    if family == "D7":
        if operator == "mapping-mutants" and parameter_values != {
            "mutant_ordinal": subordinal
        }:
            _fail("r3-damage-parameter-binding")
        if operator == "check-mutants":
            expected = (
                {"case_ordinal": subordinal, "target_unit_ids": [1, 2, 3, 4, 5]}
                if subordinal < 2
                else {"case_ordinal": subordinal, "section_id": 2}
            )
            if parameter_values != expected:
                _fail("r3-damage-parameter-binding")
        if operator == "code-mutants" and parameter_values != {
            "case_ordinal": subordinal,
            "target_unit_ids": [1, 2, 3, 4, 5],
        }:
            _fail("r3-damage-parameter-binding")
        if operator == "cross-profile-splices" and parameter_values != {
            "source_profile_version": (2, 3, 4, 5, 6)[subordinal],
            "target_unit_ids": [1, 2, 3, 4, 5],
        }:
            _fail("r3-damage-parameter-binding")
        if operator == "d2-one-beyond" and parameter_values != {
            "d2_ordinal": subordinal,
            "side": max(32, parameter_context.interior // 32) + 1,
        }:
            _fail("r3-damage-parameter-binding")
        if operator == "d3-one-beyond" and parameter_values != {
            "seed": 5_134_751_402_299_490_304 + subordinal
        }:
            _fail("r3-damage-parameter-binding")
        if operator == "algebraic-one-beyond":
            errors, erasures = ((2, 0), (1, 2), (0, 4))[subordinal]
            if parameter_values != {
                "erasures": erasures,
                "errors": errors,
                "target_unit_ids": [1, 2, 3, 4, 5],
            }:
                _fail("r3-damage-parameter-binding")
        if operator == "resource-route-one-beyond" and parameter_values != {
            "declared_value": (268_435_457, 16_777_217)[subordinal]
        }:
            _fail("r3-damage-parameter-binding")
        if operator == "resource-route-one-beyond" and (
            row["expected_artifact_state"] != "resource-limit"
            or any(item["state"] != "unknown" for item in states)
        ):
            _fail("r3-damage-result-binding")
        if operator == "geometry-one-beyond" and parameter_values != {
            "side": 2_056
        }:
            _fail("r3-damage-parameter-binding")
        if operator == "geometry-one-beyond" and (
            row["expected_artifact_state"] != "failure"
            or any(item["state"] != "unknown" for item in states)
        ):
            _fail("r3-damage-result-binding")
    return row


def _r3_checked_sum(values: Iterable[int], reason: str) -> int:
    total = 0
    for value in values:
        if not _r3_u64(value) or total > 0xFFFF_FFFF_FFFF_FFFF - value:
            _fail(reason)
        total += value
    return total


def _r3_render_shard_projection(
    template: dict[str, object], rows: Sequence[dict[str, object]]
) -> bytes:
    wrong = _r3_checked_sum(
        (int(row["wrong_accept_count"]) for row in rows),
        "r3-damage-shard-sum",
    )
    value = {
        "schema": R3_SHARD_SCHEMA,
        "damage_manifest_identity": template["damage_manifest_identity"],
        "profile_id": R3_PROFILE_ID,
        "family_id": template["family_id"],
        "shard_ordinal": template["shard_ordinal"],
        "case_first": template["case_first"],
        "case_rows": list(rows),
        "summary": {
            "case_count": len(rows),
            "wrong_accept_count": wrong,
        },
    }
    manifest_identity = identity.identity_hex(
        b"golden-board:manifest:v0\0",
        (canonical_manifest.serialize_manifest(value),),
    )
    value["summary"] = {
        "case_count": len(rows),
        "wrong_accept_count": wrong,
        "manifest_identity": manifest_identity,
    }
    return canonical_manifest.serialize_manifest(value)


def _r3_family_case_passes(
    family: str,
    row: dict[str, object],
    required_section_ids: frozenset[int],
) -> bool:
    if row["wrong_accept_count"] != 0:
        return False
    states = {
        int(item["section_id"]): str(item["state"])
        for item in row["expected_section_states"]
    }
    exact = {"verified", "recovered"}
    if family in {"D0", "D1", "D5"}:
        return all(state in exact for state in states.values())
    if family in {"D2", "D3", "D4", "D6"}:
        return all(states[section_id] in exact for section_id in required_section_ids)
    return family == "D7"


def validate_damage_bundle_v1(
    manifest_raw: bytes,
    family_manifests: Sequence[bytes],
    case_shards: Sequence[tuple[str, bytes]],
    damage_policy_raw: bytes,
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    bootstrap_spec_raw: bytes,
    route_data_raw: bytes,
    recipient_package_raw: bytes,
    candidate_manifest_raw: bytes,
    clean_observation_raw: bytes,
) -> DamageBundleV1:
    """Strictly admit one complete canonical R3 gate-6 artifact bundle.

    This validator is deliberately independent of gate 7.  It reconstructs
    every root/family/shard binding and never treats a proof as permission to
    accept incomplete or mismatched gate-6 evidence.
    """

    if (
        type(manifest_raw) is not bytes
        or type(family_manifests) not in (list, tuple)
        or type(case_shards) not in (list, tuple)
        or any(
            type(raw) is not bytes
            for raw in (
                damage_policy_raw,
                profile_policy_raw,
                profile_limits_raw,
                bootstrap_spec_raw,
                route_data_raw,
                recipient_package_raw,
                candidate_manifest_raw,
                clean_observation_raw,
            )
        )
        or len(family_manifests) != 8
        or any(type(raw) is not bytes for raw in family_manifests)
        or not 8 <= len(case_shards) <= 10_038
        or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not bytes
            for item in case_shards
        )
        or 9 + len(case_shards) > 10_047
    ):
        _fail("r3-damage-bundle")
    all_raws = (manifest_raw, *family_manifests) + tuple(
        raw for _, raw in case_shards
    )
    if (
        any(not 1 <= len(raw) <= 1_048_576 for raw in all_raws)
        or sum(len(raw) for raw in all_raws) > 536_870_912
    ):
        _fail("r3-damage-bundle-size")
    try:
        decoder_policy = m2_policy.load_r3_decoder_policy(
            profile_policy_raw, profile_limits_raw, damage_policy_raw
        )
    except m2_policy.PolicyError as error:
        raise DamageError("r3-damage-owner") from error
    if (
        decoder_policy.profile_policy_sha256
        != sha256(profile_policy_raw).hexdigest()
        or decoder_policy.profile_limits_sha256
        != sha256(profile_limits_raw).hexdigest()
        or decoder_policy.damage_policy_sha256
        != sha256(damage_policy_raw).hexdigest()
    ):
        _fail("r3-damage-owner")

    candidate = _r3_damage_manifest(
        candidate_manifest_raw,
        "golden-board.m2-candidate-manifest/v1",
        "r3-damage-candidate",
    )
    omitted_candidate = dict(candidate)
    candidate_identity = omitted_candidate.pop("manifest_identity", None)
    section_rows = candidate.get("section_rows")
    unit_rows = candidate.get("unit_rows")
    mapping = candidate.get("mapping")
    if (
        sha256(candidate_manifest_raw).hexdigest()
        != R3_CANDIDATE_MANIFEST_SHA256
        or set(candidate) != _R3_CANDIDATE_KEYS
        or candidate_identity
        != identity.identity_hex(
            b"golden-board:manifest:v0\0",
            (canonical_manifest.serialize_manifest(omitted_candidate),),
        )
        or candidate.get("profile_id") != R3_PROFILE_ID
        or candidate.get("profile_version") != 7
        or candidate.get("profile_policy_sha256")
        != sha256(profile_policy_raw).hexdigest()
        or candidate.get("profile_limits_sha256")
        != sha256(profile_limits_raw).hexdigest()
        or candidate.get("bootstrap_spec_sha256")
        != sha256(bootstrap_spec_raw).hexdigest()
        or candidate.get("route_data_sha256")
        != sha256(route_data_raw).hexdigest()
        or candidate.get("recipient_package_sha256")
        != sha256(recipient_package_raw).hexdigest()
        or candidate.get("carrier_sha256")
        != sha256(clean_observation_raw).hexdigest()
        or candidate.get("side") != 2_040
        or candidate.get("shell_width") != 128
        or type(mapping) is not dict
        or mapping.get("id") != "affine-slot-then-interior-v1"
        or type(section_rows) is not list
        or len(section_rows) != 138
        or type(unit_rows) is not list
        or len(unit_rows) != 1_841
    ):
        _fail("r3-damage-candidate")
    section_ids = tuple(
        row.get("section_id") if type(row) is dict else None
        for row in section_rows
    )
    unit_ids = tuple(
        row.get("physical_unit_id") if type(row) is dict else None
        for row in unit_rows
    )
    if (
        any(type(section_id) is not int or not 1 <= section_id <= 0xFFFF_FFFF for section_id in section_ids)
        or tuple(sorted(set(section_ids))) != section_ids
        or unit_ids != tuple(range(1, 1_842))
    ):
        _fail("r3-damage-candidate")
    required_section_ids = frozenset(
        int(row["section_id"])
        for row in section_rows
        if type(row) is dict and row.get("closure_class") == 128
    )
    if required_section_ids != frozenset({1, 2, 3, 16}):
        _fail("r3-damage-candidate")
    parameter_context = _R3ParameterContext(candidate)

    root = _r3_damage_manifest(
        manifest_raw, R3_DAMAGE_SCHEMA, "r3-damage-root"
    )
    root_summary = root.get("summary")
    root_family_rows = root.get("family_rows")
    boundary_rows = root.get("boundary_kat_rows")
    owner_bindings = {
        "damage_policy_sha256": sha256(damage_policy_raw).hexdigest(),
        "profile_policy_sha256": sha256(profile_policy_raw).hexdigest(),
        "profile_limits_sha256": sha256(profile_limits_raw).hexdigest(),
        "bootstrap_spec_sha256": sha256(bootstrap_spec_raw).hexdigest(),
        "route_data_sha256": sha256(route_data_raw).hexdigest(),
        "recipient_package_sha256": sha256(recipient_package_raw).hexdigest(),
        "candidate_manifest_sha256": sha256(candidate_manifest_raw).hexdigest(),
        "clean_observation_sha256": sha256(clean_observation_raw).hexdigest(),
    }
    if (
        set(root) != _R3_ROOT_KEYS
        or root.get("profile_id") != R3_PROFILE_ID
        or any(root.get(key) != value for key, value in owner_bindings.items())
        or type(root_summary) is not dict
        or set(root_summary) != _R3_ROOT_SUMMARY_KEYS
        or type(root_family_rows) is not list
        or len(root_family_rows) != 8
        or type(boundary_rows) is not list
        or len(boundary_rows) != 4
        or root_summary.get("manifest_identity") != _r3_nested_identity(root)
    ):
        _fail("r3-damage-root")
    if any(
        type(row) is not dict
        or set(row) != _R3_FAMILY_ROW_KEYS
        or row.get("family_id") != family
        or row.get("case_count") != count
        or not _r3_u64(row.get("wrong_accept_count"))
        or row.get("result") not in {"pass", "fail"}
        or not _r3_hex64(row.get("case_rows_sha256"))
        for row, family, count in zip(
            root_family_rows,
            R3_FAMILY_IDS,
            R3_FAMILY_CASE_COUNTS,
            strict=True,
        )
    ):
        _fail("r3-damage-root-family")
    family_count_rows = root_summary.get("family_case_counts")
    expected_count_rows = [
        {"family_id": family, "case_count": count}
        for family, count in zip(
            R3_FAMILY_IDS, R3_FAMILY_CASE_COUNTS, strict=True
        )
    ]
    if (
        type(family_count_rows) is not list
        or any(
            type(row) is not dict or set(row) != _R3_FAMILY_COUNT_ROW_KEYS
            for row in family_count_rows
        )
        or family_count_rows != expected_count_rows
        or _r3_checked_sum(R3_FAMILY_CASE_COUNTS, "r3-damage-case-count")
        != 10_038
    ):
        _fail("r3-damage-root-summary")
    boundary_pass = True
    for row, kat_id, kat_sha256 in zip(
        boundary_rows,
        R3_BOUNDARY_KAT_IDS,
        R3_BOUNDARY_KAT_SHA256,
        strict=True,
    ):
        if (
            type(row) is not dict
            or set(row) != _R3_BOUNDARY_ROW_KEYS
            or row.get("kat_id") != kat_id
            or row.get("result_sha256") != kat_sha256
            or row.get("result") not in {"pass", "fail"}
        ):
            _fail("r3-damage-boundary")
        boundary_pass = boundary_pass and row["result"] == "pass"

    family_values: list[dict[str, object]] = []
    shard_values: list[tuple[str, dict[str, object]]] = []
    cases_by_family: list[tuple[dict[str, object], ...]] = []
    shard_cursor = 0
    root_identity = str(root_summary["manifest_identity"])
    for family_index, (family, expected_count, family_raw) in enumerate(
        zip(
            R3_FAMILY_IDS,
            R3_FAMILY_CASE_COUNTS,
            family_manifests,
            strict=True,
        )
    ):
        family_value = _r3_damage_manifest(
            family_raw, R3_FAMILY_SCHEMA, "r3-damage-family"
        )
        family_summary = family_value.get("summary")
        shard_refs = family_value.get("shard_rows")
        if (
            set(family_value) != _R3_FAMILY_KEYS
            or family_value.get("damage_manifest_identity") != root_identity
            or family_value.get("profile_id") != R3_PROFILE_ID
            or family_value.get("family_id") != family
            or family_value.get("guarantee_id")
            != R3_FAMILY_GUARANTEES[family_index]
            or type(shard_refs) is not list
            or not shard_refs
            or type(family_summary) is not dict
            or set(family_summary) != _R3_FAMILY_SUMMARY_KEYS
            or family_summary.get("manifest_identity")
            != _r3_nested_identity(family_value)
        ):
            _fail("r3-damage-family")
        family_cases: list[dict[str, object]] = []
        parsed_shards: list[
            tuple[dict[str, object], bytes, tuple[dict[str, object], ...]]
        ] = []
        case_first = 0
        for shard_ordinal, shard_ref in enumerate(shard_refs):
            if shard_cursor >= len(case_shards):
                _fail("r3-damage-shard-count")
            name, shard_raw = case_shards[shard_cursor]
            shard_cursor += 1
            expected_name = f"damage-{family}-cases-{shard_ordinal:04d}.json"
            if (
                type(shard_ref) is not dict
                or set(shard_ref) != _R3_SHARD_REF_KEYS
                or shard_ref.get("shard_ordinal") != shard_ordinal
                or shard_ref.get("case_first") != case_first
                or not _r3_u64(shard_ref.get("case_count"))
                or not 1 <= int(shard_ref["case_count"]) <= 256
                or not _r3_hex64(shard_ref.get("manifest_sha256"))
                or name != expected_name
                or shard_ref.get("manifest_sha256")
                != sha256(shard_raw).hexdigest()
            ):
                _fail("r3-damage-shard-ref")
            shard_value = _r3_damage_manifest(
                shard_raw, R3_SHARD_SCHEMA, "r3-damage-shard"
            )
            shard_summary = shard_value.get("summary")
            shard_cases = shard_value.get("case_rows")
            if (
                set(shard_value) != _R3_SHARD_KEYS
                or shard_value.get("damage_manifest_identity") != root_identity
                or shard_value.get("profile_id") != R3_PROFILE_ID
                or shard_value.get("family_id") != family
                or shard_value.get("shard_ordinal") != shard_ordinal
                or shard_value.get("case_first") != case_first
                or type(shard_cases) is not list
                or len(shard_cases) != shard_ref["case_count"]
                or type(shard_summary) is not dict
                or set(shard_summary) != _R3_SHARD_SUMMARY_KEYS
                or shard_summary.get("case_count") != len(shard_cases)
                or shard_summary.get("manifest_identity")
                != _r3_nested_identity(shard_value)
            ):
                _fail("r3-damage-shard")
            validated_cases = tuple(
                _r3_validate_case(
                    row,
                    family,
                    case_first + local_ordinal,
                    section_ids,
                    parameter_context,
                )
                for local_ordinal, row in enumerate(shard_cases)
            )
            shard_wrong = _r3_checked_sum(
                (int(row["wrong_accept_count"]) for row in validated_cases),
                "r3-damage-shard-sum",
            )
            if shard_summary.get("wrong_accept_count") != shard_wrong:
                _fail("r3-damage-shard-summary")
            parsed_shards.append((shard_value, shard_raw, validated_cases))
            shard_values.append((name, shard_value))
            family_cases.extend(validated_cases)
            case_first += len(validated_cases)
        if case_first != expected_count:
            _fail("r3-damage-family-count")
        for index, (_, _, shard_cases) in enumerate(parsed_shards[:-1]):
            if len(shard_cases) == 256:
                continue
            next_cases = parsed_shards[index + 1][2]
            if not next_cases:
                _fail("r3-damage-shard-partition")
            try:
                _r3_render_shard_projection(
                    parsed_shards[index][0],
                    (*shard_cases, next_cases[0]),
                )
            except canonical_manifest.ManifestError:
                pass
            else:
                _fail("r3-damage-shard-partition")
        family_wrong = _r3_checked_sum(
            (int(row["wrong_accept_count"]) for row in family_cases),
            "r3-damage-family-sum",
        )
        family_pass = all(
            _r3_family_case_passes(family, row, required_section_ids)
            for row in family_cases
        )
        if family == "D7":
            family_pass = family_pass and boundary_pass
        expected_result = "pass" if family_pass else "fail"
        expected_root_row = {
            "family_id": family,
            "case_count": expected_count,
            "wrong_accept_count": family_wrong,
            "result": expected_result,
            "case_rows_sha256": _canonical_array_sha256(family_cases),
        }
        if (
            root_family_rows[family_index] != expected_root_row
            or family_summary
            != {
                "case_count": expected_count,
                "wrong_accept_count": family_wrong,
                "result": expected_result,
                "manifest_identity": family_summary["manifest_identity"],
            }
        ):
            _fail("r3-damage-family-binding")
        family_values.append(family_value)
        cases_by_family.append(tuple(family_cases))
    if shard_cursor != len(case_shards):
        _fail("r3-damage-shard-count")
    root_wrong = _r3_checked_sum(
        (int(row["wrong_accept_count"]) for row in root_family_rows),
        "r3-damage-root-sum",
    )
    if root_summary.get("wrong_accept_count") != root_wrong:
        _fail("r3-damage-root-summary")
    result = (
        "pass"
        if root_wrong == 0
        and all(row["result"] == "pass" for row in root_family_rows)
        else "fail"
    )
    return DamageBundleV1(
        root,
        tuple(family_values),
        tuple(shard_values),
        tuple(cases_by_family),
        result,
    )


def _oracle_mapping(
    side: int,
    width: int,
    profile_version: int,
    hierarchical: dict[str, object] | None = None,
) -> tuple[dict[str, object], str]:
    interior = side - 2 * width
    population = interior * interior
    if profile_version == 7:
        if (
            type(hierarchical) is not dict
            or set(hierarchical)
            != {
                "id",
                "interior_side",
                "population",
                "unit_population",
                "unit_multiplier",
                "unit_inverse_multiplier",
                "cell_multiplier",
                "offset",
                "cell_inverse_multiplier",
            }
            or hierarchical.get("id")
            != "affine-slot-then-interior-v1"
            or hierarchical.get("interior_side") != interior
            or hierarchical.get("population") != population
        ):
            _fail("oracle-mapping")
        mapping = dict(hierarchical)
    else:
        if hierarchical is not None:
            _fail("oracle-mapping")
        mapping = {
            "id": "affine-interior-v1",
            "interior_side": interior,
            "population": population,
            "multiplier": 2 * interior - 1,
            "offset": (profile_version * 40_503 + width * 257) % population,
            "inverse_multiplier": population - 2 * interior - 1,
        }
    return mapping, sha256(canonical_manifest.serialize_manifest(mapping)).hexdigest()


def _route_example_recipe_ids(prefix: bytes) -> tuple[int, ...]:
    """Return the exact worked/held recipe IDs charged by one route prefix."""

    if (
        type(prefix) is not bytes
        or len(prefix) < 64
        or prefix[32:40] != b"GBROUTE\0"
    ):
        _fail("route-resource")
    record_count = int.from_bytes(prefix[46:48], "big")
    record_bytes = int.from_bytes(prefix[48:52], "big")
    if record_count < 1 or len(prefix) != 64 + record_bytes:
        _fail("route-resource")
    cursor = 64
    previous_record_id = 0
    previous_stage = 0
    recipe_ids: list[int] = []
    for _ in range(record_count):
        if cursor + 8 > len(prefix):
            _fail("route-resource")
        stage = prefix[cursor]
        kind = prefix[cursor + 1]
        record_id = int.from_bytes(prefix[cursor + 2 : cursor + 4], "big")
        length = int.from_bytes(prefix[cursor + 4 : cursor + 8], "big")
        payload_first = cursor + 8
        record_end = payload_first + length
        if (
            stage > 5
            or not 1 <= kind <= 7
            or record_id <= previous_record_id
            or stage < previous_stage
            or record_end > len(prefix)
        ):
            _fail("route-resource")
        if kind in (2, 3):
            if length < 4:
                _fail("route-resource")
            recipe_id = int.from_bytes(
                prefix[payload_first + 2 : payload_first + 4], "big"
            )
            if recipe_id == 0:
                _fail("route-resource")
            recipe_ids.append(recipe_id)
        previous_record_id = record_id
        previous_stage = stage
        cursor = record_end
    if cursor != len(prefix) or not recipe_ids:
        _fail("route-resource")
    return tuple(recipe_ids)


class _Context:
    def __init__(self, manifestation: m2_carrier.Manifestation, profile: m2_codec.CandidateProfile) -> None:
        self.manifestation = manifestation
        self.profile = profile
        self.candidate = canonical_manifest.validate_canonical_manifest(manifestation.candidate_manifest)
        if (
            manifestation.profile_id != profile.profile_id
            or self.candidate.get("profile_id") != profile.profile_id
            or self.candidate.get("carrier_sha256") != sha256(manifestation.carrier).hexdigest()
            or profile.transport_id
            not in (m2_codec.EH_TRANSPORT, m2_codec.HIER_TRANSPORT)
        ):
            _fail("candidate-binding")
        self.is_r3 = profile.transport_id == m2_codec.HIER_TRANSPORT
        if self.is_r3 != (
            self.candidate.get("schema")
            == "golden-board.m2-candidate-manifest/v1"
        ):
            _fail("candidate-binding")
        self.side = int(self.candidate["side"])
        self.width = int(self.candidate["shell_width"])
        count = int.from_bytes(manifestation.carrier[:4], "big")
        if count != self.side * self.side:
            _fail("carrier-shape")
        self.clean = _bits(manifestation.carrier[4:], count)
        self.mapping = self.candidate["mapping"]
        self.interior = int(self.mapping["interior_side"])
        self.population = int(self.mapping["population"])
        self.multiplier = int(
            self.mapping[
                "cell_multiplier" if self.is_r3 else "multiplier"
            ]
        )
        self.offset = int(self.mapping["offset"])
        self.inverse = int(
            self.mapping[
                "cell_inverse_multiplier"
                if self.is_r3
                else "inverse_multiplier"
            ]
        )
        if self.interior != self.side - 2 * self.width or self.population != self.interior**2:
            _fail("mapping")
        self.unit_rows = tuple(self.candidate["unit_rows"])
        self.section_rows = tuple(self.candidate["section_rows"])
        self.row_by_unit = {
            int(row["physical_unit_id"]): row for row in self.unit_rows
        }
        self.unit_bits = profile.protected_unit_bytes * 8
        self.protected_bits = len(self.unit_rows) * self.unit_bits
        if self.is_r3:
            if (
                profile.profile_id != R3_PROFILE_ID
                or profile.profile_version != 7
                or self.unit_bits != 1_728
                or tuple(int(row["physical_unit_id"]) for row in self.unit_rows)
                != tuple(range(1, len(self.unit_rows) + 1))
                or int(self.mapping.get("unit_population", -1))
                != len(self.unit_rows)
                or any(int(row["semantic_copy_id"]) != 0 for row in self.unit_rows)
            ):
                _fail("r3-realization")
            groups: dict[tuple[int, int], list[dict[str, object]]] = {}
            for row in self.unit_rows:
                groups.setdefault(
                    (int(row["section_id"]), int(row["fragment_index"])),
                    [],
                ).append(row)
            for rows in groups.values():
                ordered = sorted(
                    rows, key=lambda item: int(item["physical_unit_id"])
                )
                factor = int(ordered[0]["physical_replica_count"])
                first_id = int(ordered[0]["physical_unit_id"])
                if (
                    factor not in (1, 2, 5)
                    or len(ordered) != factor
                    or tuple(int(row["replica_index"]) for row in ordered)
                    != tuple(range(factor))
                    or tuple(int(row["physical_replica_count"]) for row in ordered)
                    != (factor,) * factor
                    or tuple(int(row["physical_unit_id"]) for row in ordered)
                    != tuple(range(first_id, first_id + factor))
                ):
                    _fail("r3-realization")
        self.clean_encoded: dict[int, bytes] = {}
        for row in self.unit_rows:
            unit_id = int(row["physical_unit_id"])
            bits = bytearray(self.unit_bits)
            for bit_offset in range(self.unit_bits):
                physical = self.physical_cell(unit_id, bit_offset)
                local_row, local_column = divmod(physical, self.interior)
                bits[bit_offset] = self.clean[(local_row + self.width) * self.side + local_column + self.width]
            encoded = _packed(bits)
            if sha256(encoded).hexdigest() != row["encoded_sha256"]:
                _fail("unit-identity")
            self.clean_encoded[unit_id] = encoded
        self.clean_common: dict[int, bytes] = {}
        for row in self.unit_rows:
            unit_id = int(row["physical_unit_id"])
            recovery = m2_codec._eh72_decode_unit(self.clean_encoded[unit_id], (), profile.profile_version)
            if recovery.state != "verified" or recovery.decoded is None:
                _fail("clean-unit")
            self.clean_common[unit_id] = recovery.decoded
        self.rows_by_section: dict[int, list[dict[str, object]]] = {}
        for row in self.unit_rows:
            self.rows_by_section.setdefault(int(row["section_id"]), []).append(row)
        self.rows_by_group: dict[
            tuple[int, int], list[dict[str, object]]
        ] = {}
        for row in self.unit_rows:
            self.rows_by_group.setdefault(
                (int(row["section_id"]), int(row["fragment_index"])),
                [],
            ).append(row)
        self.clean_envelopes: dict[int, bytes] = {}
        self.d3_population_cache: dict[int, tuple[int, ...]] = {}
        for section in self.section_rows:
            section_id = int(section["section_id"])
            copies: dict[int, list[bytes]] = {}
            if self.is_r3:
                by_fragment: dict[int, list[dict[str, object]]] = {}
                for row in self.rows_by_section[section_id]:
                    by_fragment.setdefault(int(row["fragment_index"]), []).append(row)
                blocks: list[bytes] = []
                for fragment_index in sorted(by_fragment):
                    values = {
                        self.clean_common[int(row["physical_unit_id"])]
                        for row in by_fragment[fragment_index]
                    }
                    if len(values) != 1:
                        _fail("clean-group")
                    blocks.append(next(iter(values)))
                copies[0] = blocks
            else:
                for row in self.rows_by_section[section_id]:
                    copies.setdefault(int(row["semantic_copy_id"]), []).append(
                        self.clean_common[int(row["physical_unit_id"])]
                    )
            witnesses = []
            for copy_id in sorted(copies):
                _, envelope = bootstrap.assemble_semantic_copy(copies[copy_id], profile.profile_version)
                witnesses.append(bootstrap.SectionWitness(envelope, True))
            state, envelope = bootstrap.recover_logical_section(witnesses)
            if state != "verified":
                _fail("clean-section")
            self.clean_envelopes[section_id] = envelope
        inventory_section = bootstrap.decode_section_envelope(
            self.clean_envelopes[1]
        )
        self.inventory = bootstrap.decode_inventory(inventory_section.payload)
        clean_streams: list[bytes] = []
        for frame_id in (2, 3):
            frame_envelope = bootstrap.decode_section_envelope(
                self.clean_envelopes[frame_id]
            )
            frame = bootstrap.decode_tier_frame(frame_envelope.payload, frame_id)
            bootstrap.validate_tier_against_inventory(
                frame, frame_envelope, self.inventory
            )
            clean_streams.append(
                bootstrap.assemble_content_stream(
                    frame,
                    {
                        section_id: bootstrap.decode_section_envelope(
                            self.clean_envelopes[section_id]
                        ).payload
                        for section_id in frame.body_section_ids
                    },
                )
            )
        self.clean_required_stream, self.clean_all_stream = clean_streams
        shell_row = next(
            row for row in self.candidate["shell_rows"] if row["sector_id"] == 0
        )
        prefix_cells = int(shell_row["route_prefix_cells"])
        sector_bits = bytearray(
            self.clean[row * self.side + column]
            for bit_offset in range(prefix_cells)
            for row, column in (
                bootstrap.sector_cell(
                    self.side, self.width, 0, bit_offset
                ),
            )
        )
        prefix = _packed(sector_bits)
        example_recipe_ids = _route_example_recipe_ids(prefix)
        cursor = 64
        package_raws: list[bytes] = []
        while cursor < len(prefix):
            kind = prefix[cursor + 1]
            length = int.from_bytes(prefix[cursor + 4 : cursor + 8], "big")
            payload = prefix[cursor + 8 : cursor + 8 + length]
            if kind == 5:
                package_raws.append(payload)
            cursor += 8 + length
        if cursor != len(prefix) or not package_raws:
            _fail("route-resource")
        recipes = {
            recipe.recipe_id: recipe
            for raw in package_raws
            for recipe in bootstrap.decode_recipe_package(
                raw, self.profile.profile_version
            ).recipes
        }
        try:
            charged_recipes = [recipes[recipe_id] for recipe_id in example_recipe_ids]
            transport_recipe = recipes[30]
        except KeyError:
            _fail("route-resource")
        self.route_steps_per_sector = sum(
            recipe.primitive_steps for recipe in charged_recipes
        )
        self.route_example_recipe_ids = tuple(example_recipe_ids)
        self.route_peak_scratch = max(
            recipe.peak_live_scratch_bytes for recipe in charged_recipes
        )
        self.transport_steps = transport_recipe.primitive_steps
        self.transport_peak_scratch = transport_recipe.peak_live_scratch_bytes
        repetition_recipe = recipes.get(113)
        if self.is_r3:
            if repetition_recipe is None:
                _fail("route-resource")
            self.repetition_steps = repetition_recipe.primitive_steps
            self.repetition_peak_scratch = (
                repetition_recipe.peak_live_scratch_bytes
            )
        else:
            self.repetition_steps = 0
            self.repetition_peak_scratch = 0

    def physical_cell(self, unit_id: int, bit_offset: int) -> int:
        if self.is_r3:
            try:
                return m2_carrier.map_unit_bit(
                    self.mapping, unit_id, bit_offset
                )
            except m2_carrier.CarrierError as error:
                raise DamageError("mapping") from error
        return (
            self.multiplier * ((unit_id - 1) * self.unit_bits + bit_offset)
            + self.offset
        ) % self.population

    def coordinate_to_unit(self, row: int, column: int) -> tuple[int, int] | None:
        if not self.width <= row < self.side - self.width or not self.width <= column < self.side - self.width:
            return None
        physical = (row - self.width) * self.interior + column - self.width
        if self.is_r3:
            try:
                return m2_carrier.invert_interior_cell(
                    self.mapping, physical
                )
            except m2_carrier.CarrierError as error:
                raise DamageError("mapping") from error
        logical = (
            self.inverse * ((physical - self.offset) % self.population)
        ) % self.population
        if logical >= self.protected_bits:
            return None
        return logical // self.unit_bits + 1, logical % self.unit_bits

    def _decode_unit(self, unit_id: int, encoded: bytes, erasures: tuple[int, ...]) -> m2_codec.Recovery:
        clean_encoded = self.clean_encoded[unit_id]
        if encoded == clean_encoded and not erasures:
            return m2_codec.Recovery("verified", self.clean_common[unit_id], 0)
        erased_by_word: list[list[int]] = [[] for _ in range(24)]
        for bit in erasures:
            erased_by_word[bit // 72].append(bit % 72 + 1)
        if any(len(items) > 3 for items in erased_by_word):
            return m2_codec.Recovery("corrupt", None, 0)
        plain = self.clean_common[unit_id] + b"\0"
        recovered = bytearray()
        state = "verified"
        constructions = 0
        for word in range(24):
            encoded_word = encoded[word * 9 : word * 9 + 9]
            clean_word = clean_encoded[word * 9 : word * 9 + 9]
            if encoded_word == clean_word and not erased_by_word[word]:
                recovered.extend(plain[word * 8 : word * 8 + 8])
                continue
            try:
                result = m2_codec.eh72_decode(encoded_word, erased_by_word[word])
            except m2_codec.CodecError:
                return m2_codec.Recovery("corrupt", None, constructions)
            constructions += result.constructions
            if result.decoded is None:
                return m2_codec.Recovery("corrupt", None, constructions)
            recovered.extend(result.decoded)
            if result.state != "verified":
                state = "recovered"
        if recovered[-1] != 0:
            return m2_codec.Recovery("corrupt", None, constructions)
        common = bytes(recovered[:-1])
        try:
            bootstrap.decode_common_block(common, self.profile.profile_version)
        except bootstrap.BootstrapReject:
            return m2_codec.Recovery("corrupt", None, constructions)
        return m2_codec.Recovery(state, common, constructions)

    def _r3_group_result(
        self,
        rows: Sequence[dict[str, object]],
        replacements: dict[int, bytes],
        erasures: dict[int, tuple[int, ...]],
        omitted: set[int],
    ) -> m2_codec.ReplicaGroupResult:
        ordered = tuple(
            sorted(rows, key=lambda item: int(item["replica_index"]))
        )
        if not ordered:
            _fail("r3-group")
        factor = int(ordered[0]["physical_replica_count"])
        affected = any(
            int(row["physical_unit_id"])
            in set(replacements) | set(erasures) | omitted
            for row in ordered
        )
        if not affected:
            blocks = tuple(
                self.clean_common[int(row["physical_unit_id"])]
                for row in ordered
            )
            if len(set(blocks)) != 1:
                _fail("clean-group")
            return m2_codec.ReplicaGroupResult(
                0,
                2,
                1,
                blocks[0],
                (2,) * factor,
                blocks,
                3 if factor > 1 else 0,
                blocks[0] if factor > 1 else bytes(191),
                0,
            )
        observations: list[m2_codec.CopyObservation | None] = []
        invalid_indices: set[int] = set()
        for row in ordered:
            unit_id = int(row["physical_unit_id"])
            if unit_id in omitted:
                observations.append(None)
                continue
            erased = erasures.get(unit_id, ())
            encoded = replacements.get(unit_id, self.clean_encoded[unit_id])
            if len(encoded) != m2_codec.EH_UNIT_BYTES:
                invalid_indices.add(len(observations))
                observations.append(None)
                continue
            bits = _bits(encoded)
            for bit_offset in erased:
                if not 0 <= bit_offset < len(bits):
                    _fail("r3-erasure")
                bits[bit_offset] = 0
            observations.append(
                m2_codec.CopyObservation(_packed(bits), erased)
            )
        try:
            result = m2_codec.aggregate_replica_group(
                self.profile, tuple(observations)
            )
        except m2_codec.CodecError as error:
            raise DamageError("r3-group") from error
        if not invalid_indices:
            return result
        lane_states = list(result.lane_states)
        for index in invalid_indices:
            lane_states[index] = 1
        group_state = result.group_state
        if group_state == 0:
            group_state = 1
        return replace(
            result,
            group_state=group_state,
            lane_states=tuple(lane_states),
        )

    def _r3_identity_matches(
        self, block: bootstrap.CommonBlock, row: dict[str, object]
    ) -> bool:
        expected = bootstrap.decode_common_block(
            self.clean_common[int(row["physical_unit_id"])],
            self.profile.profile_version,
        )
        return (
            block.section_id,
            block.semantic_copy_id,
            block.fragment_index,
            block.fragment_count,
            block.section_type,
            block.section_version,
            block.section_envelope_length,
        ) == (
            int(row["section_id"]),
            int(row["semantic_copy_id"]),
            int(row["fragment_index"]),
            expected.fragment_count,
            expected.section_type,
            expected.section_version,
            expected.section_envelope_length,
        )

    def evaluate(
        self,
        replacements: dict[int, bytes] | None = None,
        erasures: dict[int, tuple[int, ...]] | None = None,
        omitted: set[int] | None = None,
        route_conflict: bool = False,
        forced_state: str | None = None,
    ) -> _Result:
        replacements = replacements or {}
        erasures = erasures or {}
        omitted = omitted or set()
        if self.is_r3:
            return self._evaluate_r3(
                replacements,
                erasures,
                omitted,
                route_conflict=route_conflict,
                forced_state=forced_state,
            )
        if forced_state is not None:
            rows = tuple((int(row["section_id"]), "unknown") for row in self.section_rows)
            return _Result(
                forced_state,
                rows,
                0,
                m2_decoder.DecodeResult(forced_state, None, (), (), False),
            )
        recoveries: dict[int, m2_codec.Recovery] = {}
        for unit_id in set(replacements) | set(erasures):
            try:
                recoveries[unit_id] = self._decode_unit(
                    unit_id,
                    replacements.get(unit_id, self.clean_encoded[unit_id]),
                    erasures.get(unit_id, ()),
                )
            except (m2_codec.CodecError, ValueError):
                recoveries[unit_id] = m2_codec.Recovery("corrupt", None, 0)
            recovery = recoveries[unit_id]
            if recovery.decoded is not None:
                try:
                    observed_block = bootstrap.decode_common_block(
                        recovery.decoded, self.profile.profile_version
                    )
                    expected_block = bootstrap.decode_common_block(
                        self.clean_common[unit_id], self.profile.profile_version
                    )
                except bootstrap.BootstrapReject:
                    recoveries[unit_id] = m2_codec.Recovery("corrupt", None, 0)
                else:
                    observed_identity = (
                        observed_block.profile_version,
                        observed_block.section_id,
                        observed_block.semantic_copy_id,
                        observed_block.section_type,
                        observed_block.section_version,
                        observed_block.fragment_index,
                        observed_block.fragment_count,
                        observed_block.section_envelope_length,
                    )
                    expected_identity = (
                        expected_block.profile_version,
                        expected_block.section_id,
                        expected_block.semantic_copy_id,
                        expected_block.section_type,
                        expected_block.section_version,
                        expected_block.fragment_index,
                        expected_block.fragment_count,
                        expected_block.section_envelope_length,
                    )
                    if observed_identity != expected_identity:
                        recoveries[unit_id] = m2_codec.Recovery(
                            "corrupt", None, 0
                        )
        section_states: list[tuple[int, str]] = []
        section_results: list[m2_decoder.SectionResult] = []
        section_attempts = 0
        wrong = 0
        ambiguous = route_conflict
        for section in self.section_rows:
            section_id = int(section["section_id"])
            if not any(
                int(row["physical_unit_id"]) in recoveries or int(row["physical_unit_id"]) in omitted
                for row in self.rows_by_section[section_id]
            ):
                section_states.append((section_id, "verified"))
                section_attempts += 1
                section_results.append(
                    m2_decoder.SectionResult(
                        section_id, "verified", self.clean_envelopes[section_id]
                    )
                )
                continue
            copy_rows: dict[int, list[dict[str, object]]] = {}
            for row in self.rows_by_section[section_id]:
                copy_rows.setdefault(int(row["semantic_copy_id"]), []).append(row)
            witnesses: list[bootstrap.SectionWitness] = []
            attempted_envelopes: set[bytes] = set()
            corrupt_seen = False
            missing_seen = False
            for copy_id in sorted(copy_rows):
                blocks: list[bytes] = []
                copy_verified = True
                complete = True
                for row in sorted(copy_rows[copy_id], key=lambda item: int(item["fragment_index"])):
                    unit_id = int(row["physical_unit_id"])
                    if unit_id in omitted:
                        missing_seen = True
                        complete = False
                        break
                    result = recoveries.get(unit_id)
                    if result is None:
                        blocks.append(self.clean_common[unit_id])
                    elif result.decoded is None:
                        corrupt_seen = True
                        complete = False
                        break
                    else:
                        blocks.append(result.decoded)
                        copy_verified = copy_verified and result.state == "verified"
                if complete:
                    try:
                        candidate_envelope = b"".join(
                            bootstrap.decode_common_block(
                                block, self.profile.profile_version
                            ).payload
                            for block in blocks
                        )
                    except bootstrap.BootstrapReject:
                        candidate_envelope = b""
                    expected_length = bootstrap.decode_common_block(
                        self.clean_common[
                            int(
                                sorted(
                                    copy_rows[copy_id],
                                    key=lambda item: int(item["fragment_index"]),
                                )[0]["physical_unit_id"]
                            )
                        ],
                        self.profile.profile_version,
                    ).section_envelope_length
                    if len(candidate_envelope) == expected_length:
                        attempted_envelopes.add(candidate_envelope)
                    try:
                        _, envelope = bootstrap.assemble_semantic_copy(blocks, self.profile.profile_version)
                        witnesses.append(bootstrap.SectionWitness(envelope, copy_verified))
                    except bootstrap.BootstrapReject:
                        corrupt_seen = True
            section_attempts += len(attempted_envelopes)
            if not witnesses:
                state = "corrupt" if corrupt_seen else "incomplete" if missing_seen else "unknown"
                recovered_envelope = None
            else:
                try:
                    state, recovered_envelope = bootstrap.recover_logical_section(witnesses)
                    if recovered_envelope != self.clean_envelopes[section_id]:
                        wrong += 1
                except bootstrap.BootstrapReject as error:
                    state = "ambiguous" if error.code == bootstrap.AMBIGUOUS else "corrupt"
                    recovered_envelope = None
            section_states.append((section_id, state))
            section_results.append(
                m2_decoder.SectionResult(
                    section_id, state, recovered_envelope
                )
            )
            if state == "ambiguous":
                ambiguous = True
        inventory_available = False
        observed_inventory = self.inventory
        inventory_result = next(
            item for item in section_results if item.section_id == 1
        )
        if inventory_result.envelope is not None:
            try:
                observed_inventory = bootstrap.decode_inventory(
                    bootstrap.decode_section_envelope(
                        inventory_result.envelope
                    ).payload
                )
            except bootstrap.BootstrapReject:
                pass
            else:
                inventory_available = True
        envelope_by_id = {
            item.section_id: item.envelope
            for item in section_results
            if item.envelope is not None
        }
        streams: list[bytes | None] = []
        if inventory_available:
            for frame_id in (2, 3):
                try:
                    frame_envelope = bootstrap.decode_section_envelope(
                        envelope_by_id[frame_id]
                    )
                    frame = bootstrap.decode_tier_frame(
                        frame_envelope.payload, frame_id
                    )
                    bootstrap.validate_tier_against_inventory(
                        frame, frame_envelope, observed_inventory
                    )
                    stream = bootstrap.assemble_content_stream(
                        frame,
                        {
                            section_id: bootstrap.decode_section_envelope(
                                envelope_by_id[section_id]
                            ).payload
                            for section_id in frame.body_section_ids
                        },
                    )
                except (KeyError, bootstrap.BootstrapReject):
                    stream = None
                streams.append(stream)
        else:
            streams = [None, None]
        required_stream, all_stream = streams
        artifact = (
            "ambiguous"
            if ambiguous
            else "exact"
            if all(
                state in ("verified", "recovered")
                for _, state in section_states
            )
            and required_stream is not None
            and all_stream is not None
            else "degraded"
            if required_stream is not None
            else "failure"
        )
        diagnostics: list[m2_decoder.FragmentDiagnostic] = []
        for row in self.unit_rows:
            unit_id = int(row["physical_unit_id"])
            if not inventory_available and unit_id in omitted:
                continue
            if unit_id in omitted:
                state, common = "missing", None
            else:
                recovery = recoveries.get(unit_id)
                if recovery is None:
                    state, common = "verified", self.clean_common[unit_id]
                else:
                    state, common = recovery.state, recovery.decoded
            if inventory_available:
                section_id = int(row["section_id"])
                copy_id = int(row["semantic_copy_id"])
                fragment_index = int(row["fragment_index"])
            elif common is not None:
                block = bootstrap.decode_common_block(
                    common, self.profile.profile_version
                )
                section_id = block.section_id
                copy_id = block.semantic_copy_id
                fragment_index = block.fragment_index
            else:
                section_id, copy_id, fragment_index = 0, 0xFFFF, 0xFFFF
            diagnostics.append(
                m2_decoder.FragmentDiagnostic(
                    unit_id,
                    (
                        self.profile.profile_id
                        if inventory_available or common is not None
                        else ""
                    ),
                    section_id,
                    copy_id,
                    fragment_index,
                    state,
                    common,
                )
            )
        visible_sections = (
            tuple(section_results)
            if inventory_available
            else tuple(
                item for item in section_results if item.envelope is not None
            )
        )
        decoder_base = m2_decoder.DecodeResult(
            artifact,
            self.profile.profile_id if inventory_available else None,
            visible_sections,
            (),
            inventory_available,
            tuple(diagnostics),
            required_stream,
            all_stream,
            m2_decoder.ResourceUsage(section_attempts, 0, 0),
        )
        return _Result(
            artifact, tuple(section_states), wrong, decoder_base
        )

    def _evaluate_r3(
        self,
        replacements: dict[int, bytes],
        erasures: dict[int, tuple[int, ...]],
        omitted: set[int],
        *,
        route_conflict: bool,
        forced_state: str | None,
    ) -> _Result:
        """Independent group-aware oracle projection for the frozen v7 lane."""

        if forced_state is not None:
            return _Result(
                forced_state,
                tuple(
                    (int(row["section_id"]), "unknown")
                    for row in self.section_rows
                ),
                0,
                m2_decoder.DecodeResult(
                    forced_state, None, (), (), False
                ),
            )
        known_ids = set(self.row_by_unit)
        if (
            not set(replacements) <= known_ids
            or not set(erasures) <= known_ids
            or not omitted <= known_ids
        ):
            _fail("r3-unit-id")
        group_results: dict[
            tuple[int, int], m2_codec.ReplicaGroupResult
        ] = {}
        group_identity: dict[tuple[int, int], bool] = {}
        for key, rows in self.rows_by_group.items():
            result = self._r3_group_result(
                rows, replacements, erasures, omitted
            )
            group_results[key] = result
            identity_valid = False
            if result.group_state in (2, 3):
                try:
                    block = bootstrap.decode_common_block(
                        result.chosen_block, self.profile.profile_version
                    )
                except bootstrap.BootstrapReject:
                    block = None
                identity_valid = (
                    block is not None
                    and self._r3_identity_matches(block, rows[0])
                )
            group_identity[key] = identity_valid

        section_results: list[m2_decoder.SectionResult] = []
        section_states: list[tuple[int, str]] = []
        section_attempts = 0
        wrong = 0
        for section in self.section_rows:
            section_id = int(section["section_id"])
            fragment_count = int(section["fragment_count"])
            concrete: list[tuple[int, bytes]] = []
            states: list[int] = []
            for fragment_index in range(fragment_count):
                key = (section_id, fragment_index)
                group = group_results[key]
                state = (
                    group.group_state
                    if group.group_state not in (2, 3)
                    or group_identity[key]
                    else 1
                )
                states.append(state)
                if state in (2, 3):
                    concrete.append((state, group.chosen_block))
            envelope_value: bytes | None = None
            if len(concrete) == fragment_count:
                blocks = tuple(block for _, block in concrete)
                try:
                    candidate_envelope = b"".join(
                        bootstrap.decode_common_block(
                            block, self.profile.profile_version
                        ).payload
                        for block in blocks
                    )
                except bootstrap.BootstrapReject:
                    candidate_envelope = b""
                if bootstrap.section_envelope_attempt_eligible(
                    candidate_envelope
                ):
                    section_attempts += 1
                try:
                    observed_copy, envelope = (
                        bootstrap.assemble_semantic_copy(
                            blocks, self.profile.profile_version
                        )
                    )
                    decoded_section = bootstrap.decode_section_envelope(
                        envelope
                    )
                    bootstrap.validate_envelope_against_inventory(
                        decoded_section, self.inventory
                    )
                except bootstrap.BootstrapReject:
                    state_name = "corrupt"
                else:
                    if observed_copy != 0:
                        state_name = "corrupt"
                    else:
                        envelope_value = envelope
                        state_name = (
                            "verified"
                            if all(state == 2 for state, _ in concrete)
                            else "recovered"
                        )
                        if envelope != self.clean_envelopes[section_id]:
                            wrong += 1
            else:
                state_name = (
                    "corrupt"
                    if any(state in (1, 4) for state in states)
                    else "incomplete"
                )
            section_results.append(
                m2_decoder.SectionResult(
                    section_id, state_name, envelope_value
                )
            )
            section_states.append((section_id, state_name))

        inventory_result = section_results[0]
        inventory_available = False
        if inventory_result.section_id != 1:
            _fail("inventory-order")
        if inventory_result.envelope is not None:
            try:
                observed_inventory = bootstrap.decode_inventory(
                    bootstrap.decode_section_envelope(
                        inventory_result.envelope
                    ).payload
                )
            except bootstrap.BootstrapReject:
                observed_inventory = None
            inventory_available = observed_inventory == self.inventory

        diagnostics: list[m2_decoder.FragmentDiagnostic] = []
        if inventory_available:
            for key in sorted(
                self.rows_by_group,
                key=lambda item: int(
                    self.rows_by_group[item][0]["physical_unit_id"]
                ),
            ):
                rows = tuple(
                    sorted(
                        self.rows_by_group[key],
                        key=lambda item: int(item["replica_index"]),
                    )
                )
                group = group_results[key]
                for row, lane_state, lane_block in zip(
                    rows,
                    group.lane_states,
                    group.lane_blocks,
                    strict=True,
                ):
                    diagnostics.append(
                        m2_decoder.FragmentDiagnostic(
                            int(row["physical_unit_id"]),
                            self.profile.profile_id,
                            int(row["section_id"]),
                            0,
                            int(row["fragment_index"]),
                            {
                                0: "missing",
                                1: "corrupt",
                                2: "verified",
                                3: "recovered",
                            }[lane_state],
                            lane_block if lane_state in (2, 3) else None,
                            int(row["replica_index"]),
                            int(row["physical_replica_count"]),
                        )
                    )
            visible_sections = tuple(section_results)
        else:
            registry = m2_codec.r3_registry_profiles(self.profile)
            initial_rows = self.rows_by_group[(1, 0)]
            initial = group_results[(1, 0)]
            initial_lane = {
                int(row["physical_unit_id"]): (
                    initial.lane_states[index],
                    initial.lane_blocks[index],
                )
                for index, row in enumerate(
                    sorted(
                        initial_rows,
                        key=lambda item: int(item["replica_index"]),
                    )
                )
            }
            for unit_id in sorted(known_ids - omitted):
                encoded = replacements.get(
                    unit_id, self.clean_encoded[unit_id]
                )
                erased_bits = erasures.get(unit_id, ())
                candidates: list[
                    tuple[
                        m2_codec.CandidateProfile,
                        m2_codec.Recovery,
                        bootstrap.CommonBlock,
                    ]
                ] = []
                for candidate_profile in registry:
                    if len(encoded) != candidate_profile.protected_unit_bytes:
                        continue
                    try:
                        if candidate_profile.transport_id in (
                            m2_codec.EH_TRANSPORT,
                            m2_codec.HIER_TRANSPORT,
                        ):
                            recovery = m2_codec._eh72_decode_unit(
                                encoded,
                                erased_bits,
                                candidate_profile.profile_version,
                            )
                        else:
                            rs = m2_codec.rs255_191_decode(
                                encoded,
                                tuple(sorted({bit // 8 for bit in erased_bits})),
                                None,
                            )
                            recovery = m2_codec.Recovery(
                                rs.state,
                                rs.decoded,
                                rs.primitive_steps,
                            )
                        block = (
                            bootstrap.decode_common_block(
                                recovery.decoded,
                                candidate_profile.profile_version,
                            )
                            if recovery.decoded is not None
                            else None
                        )
                    except (
                        m2_codec.CodecError,
                        bootstrap.BootstrapReject,
                    ):
                        block = None
                    if block is not None:
                        candidates.append(
                            (candidate_profile, recovery, block)
                        )
                replica_index = unit_id - 1 if unit_id <= 5 else 0xFFFF
                factor = 5 if unit_id <= 5 else 0xFFFF
                if len(candidates) == 1:
                    candidate_profile, recovery, block = candidates[0]
                    common = recovery.decoded
                    state_name = recovery.state
                    if candidate_profile.profile_version == 7 and unit_id <= 5:
                        lane_state, lane_block = initial_lane[unit_id]
                        state_name = {
                            0: "missing",
                            1: "corrupt",
                            2: "verified",
                            3: "recovered",
                        }[lane_state]
                        common = lane_block if lane_state in (2, 3) else None
                    diagnostics.append(
                        m2_decoder.FragmentDiagnostic(
                            unit_id,
                            candidate_profile.profile_id,
                            block.section_id,
                            block.semantic_copy_id,
                            block.fragment_index,
                            state_name,
                            common,
                            replica_index,
                            factor,
                        )
                    )
                else:
                    diagnostics.append(
                        m2_decoder.FragmentDiagnostic(
                            unit_id,
                            "",
                            0,
                            0xFFFF,
                            0xFFFF,
                            "ambiguous" if candidates else "corrupt",
                            None,
                            replica_index,
                            factor,
                        )
                    )
            for unit_id in range(1, 6):
                if unit_id in omitted:
                    diagnostics.append(
                        m2_decoder.FragmentDiagnostic(
                            unit_id,
                            self.profile.profile_id,
                            1,
                            0,
                            0,
                            "missing",
                            None,
                            unit_id - 1,
                            5,
                        )
                    )
            diagnostics.sort(key=lambda item: item.input_id)
            visible_sections = tuple(
                item
                for item in section_results
                if item.section_id == 1 or item.envelope is not None
            )

        envelope_by_id = {
            item.section_id: item.envelope
            for item in section_results
            if item.envelope is not None
        }
        streams: list[bytes | None] = []
        if inventory_available:
            for frame_id in (2, 3):
                try:
                    frame_envelope = bootstrap.decode_section_envelope(
                        envelope_by_id[frame_id]
                    )
                    frame = bootstrap.decode_tier_frame(
                        frame_envelope.payload, frame_id
                    )
                    bootstrap.validate_tier_against_inventory(
                        frame, frame_envelope, self.inventory
                    )
                    stream = bootstrap.assemble_content_stream(
                        frame,
                        {
                            section_id: bootstrap.decode_section_envelope(
                                envelope_by_id[section_id]
                            ).payload
                            for section_id in frame.body_section_ids
                        },
                    )
                except (KeyError, bootstrap.BootstrapReject):
                    stream = None
                streams.append(stream)
        else:
            streams = [None, None]
        required_stream, all_stream = streams
        if required_stream is None:
            all_stream = None
        artifact = (
            "ambiguous"
            if route_conflict
            or any(item.state == "ambiguous" for item in visible_sections)
            else "exact"
            if inventory_available
            and all(
                item.state in ("verified", "recovered")
                for item in section_results
            )
            and required_stream is not None
            and all_stream is not None
            else "degraded"
            if required_stream is not None
            else "failure"
        )
        projected_states = (
            tuple(section_states)
            if inventory_available
            else tuple(
                (
                    int(row["section_id"]),
                    next(
                        (
                            item.state
                            for item in visible_sections
                            if item.section_id == int(row["section_id"])
                        ),
                        "unknown",
                    ),
                )
                for row in self.section_rows
            )
        )
        return _Result(
            artifact,
            projected_states,
            wrong,
            m2_decoder.DecodeResult(
                artifact,
                self.profile.profile_id if inventory_available else None,
                visible_sections,
                (),
                inventory_available,
                tuple(diagnostics),
                required_stream,
                all_stream,
                m2_decoder.ResourceUsage(section_attempts, 0, 0),
            ),
        )

    def coordinate_damage(self, coordinates: Iterable[tuple[int, int]], erased: bool) -> tuple[dict[int, bytes], dict[int, tuple[int, ...]]]:
        changed: dict[int, list[int]] = {}
        for row, column in coordinates:
            target = self.coordinate_to_unit(row, column)
            if target is not None:
                unit_id, bit = target
                changed.setdefault(unit_id, []).append(bit)
        replacements: dict[int, bytes] = {}
        erasures: dict[int, tuple[int, ...]] = {}
        for unit_id, offsets in changed.items():
            distinct = tuple(sorted(set(offsets)))
            if erased:
                erasures[unit_id] = distinct
            else:
                bits = _bits(self.clean_encoded[unit_id])
                for bit in distinct:
                    bits[bit] ^= 1
                replacements[unit_id] = _packed(bits)
        return replacements, erasures


_ACTIVE_EVALUATORS: set[object] = set()


def _canonical_difference_keys(left: bytes, right: bytes) -> tuple[str, ...]:
    try:
        left_value = canonical_manifest.validate_canonical_manifest(left)
    except (TypeError, ValueError):
        return ("expected-invalid",)
    try:
        right_value = canonical_manifest.validate_canonical_manifest(right)
    except (TypeError, ValueError):
        return ("observed-invalid",)
    if type(left_value) is not dict or type(right_value) is not dict:
        return ("non-object",)
    keys = tuple(
        sorted(
            key
            for key in set(left_value) | set(right_value)
            if left_value.get(key) != right_value.get(key)
        )
    )
    return keys[:16] + (("more",) if len(keys) > 16 else ())


def _decoder_disagreement_reason(
    case_id: str,
    expected_raw: bytes,
    python_raw: bytes,
    rust_raw: bytes,
    expected_artifact_state: str,
    python_artifact_state: str,
    expected_section_states: tuple[tuple[int, str], ...],
    python_section_states: tuple[tuple[int, str], ...],
    expected_wrong: int,
    python_wrong: int,
) -> str:
    projection_deltas = tuple(
        name
        for name, differs in (
            ("artifact-state", expected_artifact_state != python_artifact_state),
            ("section-states", expected_section_states != python_section_states),
            ("wrong-accept", expected_wrong != python_wrong),
        )
        if differs
    )

    def joined(values: tuple[str, ...]) -> str:
        return ",".join(values) if values else "none"

    return "|".join(
        (
            "decoder-independent-disagreement",
            f"case={case_id}",
            f"expected_sha256={sha256(expected_raw).hexdigest()}",
            f"python_sha256={sha256(python_raw).hexdigest()}",
            f"rust_sha256={sha256(rust_raw).hexdigest()}",
            "expected_python_keys="
            + joined(_canonical_difference_keys(expected_raw, python_raw)),
            "python_rust_keys="
            + joined(_canonical_difference_keys(python_raw, rust_raw)),
            "projection_deltas=" + joined(projection_deltas),
        )
    )


class _DamageEvaluator:
    """Evaluator-side comparison around one fresh observation-only decoder."""

    def __init__(
        self,
        context: _Context,
        profile_policy_raw: bytes,
        profile_limits_raw: bytes,
        damage_policy_raw: bytes,
        alternate_recipient_package: bytes,
        rust_decoder_command: Sequence[str] | None,
        worker_count: int,
        *,
        alternate_route_manifest_raw: bytes | None = None,
        capture_mismatches: bool = False,
    ) -> None:
        self.context = context
        self.profile_policy_raw = profile_policy_raw
        self.profile_limits_raw = profile_limits_raw
        try:
            if context.is_r3:
                self.damage_policy = m2_policy.load_r3_decoder_policy(
                    profile_policy_raw,
                    profile_limits_raw,
                    damage_policy_raw,
                )
                self.result_schema_version = 1
            else:
                self.damage_policy = m2_policy.load_damage_policy(
                    damage_policy_raw
                )
                self.result_schema_version = 0
        except m2_policy.PolicyError as error:
            raise DamageError("damage-policy") from error
        maximum_workers = min(8, os.cpu_count() or 1)
        if (
            type(worker_count) is not int
            or not 1 <= worker_count <= maximum_workers
            or (
                rust_decoder_command is not None
                and (
                    isinstance(rust_decoder_command, (str, bytes, bytearray))
                    or not 1 <= len(rust_decoder_command) <= 16
                    or any(type(item) is not str for item in rust_decoder_command)
                )
            )
        ):
            _fail("decoder-workers")
        self.worker_count = worker_count
        self.compare_rust = rust_decoder_command is not None
        self._pool = multiprocessing.get_context("spawn").Pool(
            processes=worker_count,
            initializer=_decoder_worker_initialize,
            initargs=(
                profile_policy_raw,
                profile_limits_raw,
                damage_policy_raw,
                dict(context.clean_envelopes),
                (
                    None
                    if rust_decoder_command is None
                    else tuple(rust_decoder_command)
                ),
            ),
        )
        self._pending: list[
            tuple[
                str,
                object,
                bytes,
                str,
                tuple[tuple[int, str], ...],
                int,
            ]
        ] = []
        self._actual_wrong: dict[str, int] = {}
        self._closed = False
        _ACTIVE_EVALUATORS.add(self)
        self.profiles = (
            m2_codec.r3_registry_profiles(context.profile)
            if context.is_r3
            else m2_codec.load_candidate_profiles(
                profile_policy_raw, profile_limits_raw
            )
        )
        self.alternate_profile = (
            next(
                profile
                for profile in self.profiles
                if profile.profile_version == 3
            )
            if context.is_r3
            else next(
                profile
                for profile in self.profiles
                if profile.transport_id == context.profile.transport_id
                and profile.section_check_id
                == context.profile.section_check_id
                and profile.required_copy_count
                != context.profile.required_copy_count
            )
        )
        alternate_package = bootstrap.decode_recipe_package(
            alternate_recipient_package,
            self.alternate_profile.profile_version,
        )
        alternate_recipes = {
            recipe.recipe_id: recipe for recipe in alternate_package.recipes
        }
        if context.is_r3:
            if alternate_route_manifest_raw is None:
                alternate_example_recipe_ids = None
            elif type(alternate_route_manifest_raw) is not bytes:
                _fail("alternate-route-owner")
            else:
                try:
                    alternate_routes = m2_route_data.build_route_images(
                        alternate_route_manifest_raw,
                        m2_route_data.CandidateRouteData(
                            self.alternate_profile.profile_id,
                            self.alternate_profile.profile_version,
                            self.alternate_profile.transport_id,
                            self.alternate_profile.section_check_id,
                            (alternate_recipient_package,),
                        ),
                        context.side,
                        context.width,
                    )
                except m2_route_data.RouteDataError as error:
                    raise DamageError("alternate-route-owner") from error
                if (
                    len(alternate_routes.sectors) != 4
                    or alternate_routes.sectors[0].sector_id != 0
                    or alternate_routes.sectors[0].route_prefix_cells % 8
                ):
                    _fail("alternate-route-owner")
                prefix_bytes = (
                    alternate_routes.sectors[0].route_prefix_cells // 8
                )
                alternate_example_recipe_ids = _route_example_recipe_ids(
                    alternate_routes.sectors[0].data[:prefix_bytes]
                )
        else:
            alternate_example_recipe_ids = tuple(
                recipe_id
                for recipe_id in context.route_example_recipe_ids
                if recipe_id != 113
            )
        try:
            alternate_transport = alternate_recipes[30]
        except KeyError:
            _fail("alternate-route-resource")
        if alternate_example_recipe_ids is None:
            self.alternate_route_steps = None
            self.alternate_route_scratch = None
        else:
            try:
                charged = [
                    alternate_recipes[recipe_id]
                    for recipe_id in alternate_example_recipe_ids
                ]
            except KeyError:
                _fail("alternate-route-resource")
            self.alternate_route_steps = sum(
                recipe.primitive_steps for recipe in charged
            )
            self.alternate_route_scratch = max(
                recipe.peak_live_scratch_bytes for recipe in charged
            )
        self.alternate_transport_steps = alternate_transport.primitive_steps
        self.alternate_transport_scratch = (
            alternate_transport.peak_live_scratch_bytes
        )
        self.match_by_case: dict[str, bool] = {}
        self.capture_mismatches = capture_mismatches
        self.mismatch_raw_by_case: dict[
            str, tuple[bytes, bytes, bytes]
        ] = {}
        self.family_case_counts: dict[str, int] = {}
        self.bundle_case_preimages: dict[str, tuple[str, bytes, bytes]] = {}

    def _abort(self) -> None:
        if self._closed:
            _ACTIVE_EVALUATORS.discard(self)
            return
        self._closed = True
        self._pool.terminate()
        self._pool.join()
        _ACTIVE_EVALUATORS.discard(self)

    def _finish_next(self) -> None:
        if not self._pending:
            return
        (
            case_id,
            pending,
            expected_raw,
            expected_artifact_state,
            expected_section_states,
            expected_wrong,
        ) = self._pending.pop(0)
        try:
            (
                observed_case_id,
                actual_raw,
                rust_raw,
                artifact_state,
                actual_states,
                wrong,
            ) = pending.get(timeout=600.0)  # type: ignore[attr-defined]
        except (multiprocessing.TimeoutError, OSError, EOFError) as error:
            self._abort()
            raise DamageError("decoder-worker") from error
        except BaseException:
            self._abort()
            raise
        if observed_case_id != case_id:
            self._abort()
            _fail("decoder-worker-order")
        self._actual_wrong[case_id] = wrong
        matches = (
            actual_raw == expected_raw
            and (rust_raw is None or rust_raw == expected_raw)
            and artifact_state == expected_artifact_state
            and actual_states == expected_section_states
            and wrong == expected_wrong
        )
        self.match_by_case[case_id] = matches
        if (
            not matches
            and self.capture_mismatches
            and len(self.mismatch_raw_by_case) < 16
        ):
            self.mismatch_raw_by_case[case_id] = (
                expected_raw,
                actual_raw,
                actual_raw if rust_raw is None else rust_raw,
            )
        if not matches and self.context.is_r3 and not self.capture_mismatches:
            reason = _decoder_disagreement_reason(
                case_id,
                expected_raw,
                actual_raw,
                actual_raw if rust_raw is None else rust_raw,
                expected_artifact_state,
                artifact_state,
                expected_section_states,
                actual_states,
                expected_wrong,
                wrong,
            )
            self._abort()
            raise DamageError(reason)

    def finish(self, rows: list[dict[str, object]]) -> None:
        while self._pending:
            self._finish_next()
        case_ids = {str(row["case_id"]) for row in rows}
        if case_ids != set(self._actual_wrong):
            self._abort()
            _fail("decoder-worker-coverage")
        for row in rows:
            row["wrong_accept_count"] = self._actual_wrong[str(row["case_id"])]

    def boundary_kat(self, ordinal: int | None = None) -> bytes:
        if self._pending or self._closed:
            _fail("decoder-worker-state")
        if ordinal is not None and (
            type(ordinal) is not int or not 0 <= ordinal <= 3
        ):
            _fail("boundary-kat")
        if not self.compare_rust:
            return (
                m2_decoder.section_attempt_boundary_kat()
                if ordinal is None
                else m2_decoder.r3_boundary_kat(ordinal)
            )
        pending = self._pool.apply_async(
            _decoder_worker_boundary_kat, (ordinal,)
        )
        try:
            return pending.get(timeout=600.0)
        except (multiprocessing.TimeoutError, OSError, EOFError) as error:
            self._abort()
            raise DamageError("decoder-worker") from error

    def close(self) -> None:
        if self._closed:
            return
        if self._pending:
            self._abort()
            _fail("decoder-worker-pending")
        self._closed = True
        self._pool.close()
        self._pool.join()
        _ACTIVE_EVALUATORS.discard(self)

    def __del__(self) -> None:
        try:
            self._abort()
        except Exception:
            pass

    def evaluate(
        self,
        case_id: str,
        operator: str,
        parameters: dict[str, tuple[str, object]],
        channel: str,
        observation: bytes,
        expected: _Result,
    ) -> tuple[str, int]:
        values = {name: value for name, (_kind, value) in parameters.items()}
        base = expected.decoder_base
        accepted: list[m2_decoder.AcceptedHypothesis] = []
        section_attempts = base.resource.section_attempts
        primitive_steps = 0
        peak_scratch = 0
        if base.artifact_state == "resource-limit":
            # The first canonical route is statically rejected before any
            # recipe invocation; the owned no-partial projection retains the
            # exact zero counters and no accepted hypotheses.
            pass
        elif channel == "OBS_UNITS":
            observed_ids = _obs_unit_ids(observation)
            observed_count = len(observed_ids)
            for (
                profile_version,
                _profile_id,
                _package_sha,
                steps,
                scratch,
            ) in self.damage_policy.obs_units_resource_profiles:
                candidate_profile = next(
                    profile
                    for profile in self.profiles
                    if profile.profile_version == profile_version
                )
                primitive_steps += (
                    observed_count
                    * _transport_lane_invocations(candidate_profile)
                    * steps
                )
                peak_scratch = max(peak_scratch, scratch)
            if self.context.is_r3:
                if base.inventory_available:
                    present_ids = set(observed_ids)
                    repetition_groups = sum(
                        int(rows[0]["physical_replica_count"]) > 1
                        and any(
                            int(row["physical_unit_id"]) in present_ids
                            for row in rows
                        )
                        for rows in self.context.rows_by_group.values()
                    )
                else:
                    repetition_groups = int(
                        any(1 <= unit_id <= 5 for unit_id in observed_ids)
                    )
                primitive_steps += repetition_groups * (
                    1_728 * self.damage_policy.repetition_primitive_steps
                    + 24 * self.context.transport_steps
                )
                if repetition_groups:
                    peak_scratch = max(
                        peak_scratch,
                        self.damage_policy.repetition_peak_scratch_bytes,
                    )
        elif operator != "geometry-one-beyond":
            transform = 0
            polarity = 0
            if operator == "clean-transform-polarity":
                transform = int(values["transform_id"])
                polarity = int(values["polarity_id"])
            current_sectors = [0, 1, 2, 3]
            if operator in (
                "erase-one-complete-shell-sector",
                "erase-shell-sector-union-one-protected-unit-cell-set",
                "erase-shell-sector-union-one-physical-unit-cell-set",
            ):
                current_sectors.remove(int(values["sector_id"]))
            elif operator == "resource-route-one-beyond":
                current_sectors.remove(0)
            elif operator == "route-conflicts":
                current_sectors.remove(0)
            _, current_mapping_sha = _oracle_mapping(
                self.context.side,
                self.context.width,
                self.context.profile.profile_version,
                self.context.mapping if self.context.is_r3 else None,
            )
            accepted.extend(
                m2_decoder.AcceptedHypothesis(
                    transform,
                    polarity,
                    sector,
                    self.context.profile.profile_id,
                    current_mapping_sha,
                )
                for sector in current_sectors
            )
            primitive_steps += (
                len(current_sectors) * self.context.route_steps_per_sector
            )
            peak_scratch = max(
                peak_scratch, self.context.route_peak_scratch
            )
            if current_sectors:
                current_count = (
                    len(self.context.unit_rows)
                    if base.inventory_available
                    else min(
                        self.context.profile.protected_units,
                        self.context.population
                        // (self.context.profile.protected_unit_bytes * 8),
                    )
                )
                primitive_steps += (
                    len(current_sectors)
                    * current_count
                    * 24
                    * self.context.transport_steps
                )
                if self.context.is_r3:
                    repetition_group_count = (
                        sum(
                            int(rows[0]["physical_replica_count"]) > 1
                            for rows in self.context.rows_by_group.values()
                        )
                        if base.inventory_available
                        else 1
                    )
                    primitive_steps += len(current_sectors) * (
                        repetition_group_count
                        * (
                            1_728 * self.context.repetition_steps
                            + 24 * self.context.transport_steps
                        )
                    )
                peak_scratch = max(
                    peak_scratch,
                    self.context.transport_peak_scratch,
                    self.context.repetition_peak_scratch
                    if self.context.is_r3
                    else 0,
                )
            if operator == "route-conflicts":
                if (
                    self.alternate_route_steps is None
                    or self.alternate_route_scratch is None
                ):
                    _fail("alternate-route-resource")
                _, alternate_mapping_sha = _oracle_mapping(
                    self.context.side,
                    self.context.width,
                    self.alternate_profile.profile_version,
                )
                accepted.append(
                    m2_decoder.AcceptedHypothesis(
                        transform,
                        polarity,
                        0,
                        self.alternate_profile.profile_id,
                        alternate_mapping_sha,
                    )
                )
                primitive_steps += self.alternate_route_steps
                alternate_count = min(
                    self.alternate_profile.protected_units,
                    self.context.population
                    // (self.alternate_profile.protected_unit_bytes * 8),
                )
                primitive_steps += (
                    alternate_count
                    * 24
                    * self.alternate_transport_steps
                )
                peak_scratch = max(
                    peak_scratch,
                    self.alternate_route_scratch,
                    self.alternate_transport_scratch,
                )
        accepted.sort(
            key=lambda item: (
                item.transform_id,
                item.polarity_id,
                item.sector_id,
                next(
                    ordinal
                    for ordinal, profile in enumerate(self.profiles)
                    if profile.profile_id == item.profile_id
                ),
            )
        )
        expected_result = m2_decoder.DecodeResult(
            base.artifact_state,
            base.profile_id,
            base.section_results,
            tuple(
                profile.profile_id
                for profile in self.profiles
                if any(
                    item.profile_id == profile.profile_id
                    for item in accepted
                )
            ),
            base.inventory_available,
            base.fragment_diagnostics,
            base.m2_required_stream,
            base.m2_all_stream,
            m2_decoder.ResourceUsage(
                section_attempts, primitive_steps, peak_scratch
            ),
            tuple(accepted),
        )
        expected_raw = m2_decoder.render_decoder_result(
            channel,
            expected_result,
            schema_version=self.result_schema_version,
        )
        if case_id in {"D2-000000", "D3-000000", "D4-000000", "D7-000011"}:
            self.bundle_case_preimages[case_id] = (
                channel,
                observation,
                expected_raw,
            )
        pending = self._pool.apply_async(
            _decoder_worker_evaluate,
            ((case_id, channel, observation),),
        )
        self._pending.append(
            (
                case_id,
                pending,
                expected_raw,
                expected.artifact_state,
                expected.section_states,
                expected.wrong_accepts,
            )
        )
        if len(self._pending) >= 2 * self.worker_count:
            self._finish_next()
        return sha256(expected_raw).hexdigest(), expected.wrong_accepts


def _case_row(
    case_id: str,
    family: str,
    channel: str,
    operator: str,
    parameters: dict[str, tuple[str, object]],
    observation: bytes,
    result: _Result,
    evaluator: _DamageEvaluator,
) -> dict[str, object]:
    ordinal = evaluator.family_case_counts.get(family, 0)
    evaluator.family_case_counts[family] = ordinal + 1
    case_id = f"{family}-{ordinal:06d}"
    decoder_result_sha256, wrong_accepts = evaluator.evaluate(
        case_id, operator, parameters, channel, observation, result
    )
    return {
        "case_id": case_id,
        "family_id": family,
        "channel": channel,
        "operator": operator,
        "parameter_projection": _parameter_rows(parameters),
        "observation_sha256": sha256(observation).hexdigest(),
        "decoder_result_sha256": decoder_result_sha256,
        "expected_artifact_state": result.artifact_state,
        "expected_section_states": [
            {"section_id": section_id, "state": state}
            for section_id, state in result.section_states
        ],
        "wrong_accept_count": wrong_accepts,
    }


def _matrix_case(
    context: _Context,
    family: str,
    ordinal: int,
    operator: str,
    coordinates: Sequence[tuple[int, int]],
    erased: bool,
    parameters: dict[str, tuple[str, object]],
    base: bytearray | None = None,
    evaluator: _DamageEvaluator | None = None,
) -> dict[str, object]:
    if evaluator is None:
        _fail("decoder-evaluator")
    matrix = bytearray(context.clean if base is None else base)
    for row, column in coordinates:
        matrix[row * context.side + column] = 2 if erased else matrix[row * context.side + column] ^ 1
    replacements, erasures = context.coordinate_damage(coordinates, erased)
    result = context.evaluate(replacements, erasures)
    return _case_row(
        f"{family}-{ordinal:06d}", family, "OBS_MATRIX", operator,
        parameters, _obs_matrix(context.side, matrix), result, evaluator,
    )


def _d2_placements(context: _Context, side_length: int) -> tuple[tuple[int, int], ...]:
    domain = context.interior - side_length + 1
    choices = (0, domain // 2, domain - 1)
    anchors = tuple((row, column) for row in choices for column in choices)
    anchor_flats = sorted(row * domain + column for row, column in anchors)
    needed = 256 - len(anchors)
    selected = _sample_indices(domain * domain - len(anchor_flats), needed, 5134751402299490304)

    def unfilter(index: int) -> int:
        value = index
        for excluded in anchor_flats:
            if excluded <= value:
                value += 1
        return value

    sampled = tuple(divmod(unfilter(index), domain) for index in selected)
    return tuple((row + context.width, column + context.width) for row, column in anchors + sampled)


def _d3_population(context: _Context, stratum: int) -> tuple[int, ...]:
    cached = context.d3_population_cache.get(stratum)
    if cached is not None:
        return cached
    coordinates: set[int] = set()
    required = {
        int(row["section_id"])
        for row in context.section_rows if int(row["closure_class"]) == 128
    }
    for unit in context.unit_rows:
        unit_id = int(unit["physical_unit_id"])
        if stratum == 2 and int(unit["section_id"]) not in required:
            continue
        for bit in range(context.unit_bits):
            physical = context.physical_cell(unit_id, bit)
            row, column = divmod(physical, context.interior)
            if stratum == 2 or (
                bit < 16 or bit >= context.unit_bits - 16 or bit % 8 in (0, 7)
                or row % 16 in (0, 15) or column % 16 in (0, 15)
            ):
                coordinates.add(row * context.interior + column)
    result = tuple(sorted(coordinates))
    context.d3_population_cache[stratum] = result
    return result


def _d3_coordinates(context: _Context, ordinal: int, extra: int = 0) -> tuple[tuple[int, int], ...]:
    seed = 5134751402299490304 + ordinal
    stratum = ordinal // 32
    weight = max(64, (context.interior * context.interior + 1999) // 2000) + extra
    if stratum == 0:
        selected = _sample_indices(context.population, weight, seed)
        return tuple(
            (row + context.width, column + context.width)
            for row, column in (divmod(index, context.interior) for index in selected)
        )
    if stratum == 1:
        window = max(32, context.interior // 8)
        domain = context.interior - window + 1
        origin, column_origin = _two_unbiased_indices(
            domain, seed, _WINDOW_DOMAIN
        )
        selected = _sample_indices(window * window, weight, seed)
        return tuple(
            (context.width + origin + row, context.width + column_origin + column)
            for row, column in (divmod(index, window) for index in selected)
        )
    population = _d3_population(context, stratum)
    selected = _sample_indices(len(population), weight, seed)
    return tuple(
        (row + context.width, column + context.width)
        for row, column in (
            divmod(population[index], context.interior) for index in selected
        )
    )


def _reencode_unit(common: bytes) -> bytes:
    return m2_codec.eh72_encode_unit(common)


def _eh_mutant_unit(common: bytes, mutant: str) -> bytes:
    if type(common) is not bytes or len(common) != 191:
        _fail("eh-mutant-input")

    def source_bits(chunk: bytes, lsb_first: bool) -> list[int]:
        shifts = range(8) if lsb_first else range(7, -1, -1)
        return [(byte >> shift) & 1 for byte in chunk for shift in shifts]

    def pack(bits: Sequence[int], lsb_first: bool) -> bytes:
        output = bytearray(9)
        for index, bit in enumerate(bits):
            output[index // 8] |= bit << (
                index % 8 if lsb_first else 7 - index % 8
            )
        return bytes(output)

    output = bytearray()
    padded = common + b"\0"
    for offset in range(0, len(padded), 8):
        chunk = padded[offset : offset + 8]
        bits = [0] * 72
        if mutant == "eh-parity-position-off-by-one":
            reserved = {2, 3, 5, 9, 17, 33, 65}
            source = iter(source_bits(chunk, False))
            for position in range(1, 72):
                if position not in reserved:
                    bits[position - 1] = next(source)
            for mask in (1, 2, 4, 8, 16, 32, 64):
                position = mask + 1
                bits[position - 1] = sum(
                    bits[q - 1]
                    for q in range(1, 72)
                    if q != position and ((q - 1) & mask)
                ) & 1
            bits[71] = sum(bits[:71]) & 1
            output.extend(pack(bits, False))
        elif mutant == "eh-position-72-in-hamming-equations":
            parity_positions = {1, 2, 4, 8, 16, 32, 64}
            source = iter(source_bits(chunk, False))
            for position in range(1, 72):
                if position not in parity_positions:
                    bits[position - 1] = next(source)
            bits[71] = sum(bits[:71]) & 1
            for parity in sorted(parity_positions):
                bits[parity - 1] = (
                    sum(
                        bits[q - 1]
                        for q in range(1, 72)
                        if q != parity and q & parity
                    )
                    + bits[71]
                ) & 1
            output.extend(pack(bits, False))
        elif mutant == "eh-lsb-first":
            parity_positions = {1, 2, 4, 8, 16, 32, 64}
            source = iter(source_bits(chunk, True))
            for position in range(1, 72):
                if position not in parity_positions:
                    bits[position - 1] = next(source)
            for parity in sorted(parity_positions):
                bits[parity - 1] = sum(
                    bits[q - 1]
                    for q in range(1, 72)
                    if q != parity and q & parity
                ) & 1
            bits[71] = sum(bits[:71]) & 1
            output.extend(pack(bits, True))
        else:
            _fail("eh-mutant")
    if len(output) != 216:
        _fail("eh-mutant-output")
    return bytes(output)


def _fragment_unchecked_envelope(
    envelope: bytes,
    section: bootstrap.SectionEnvelope,
    profile_version: int,
    semantic_copy_id: int,
) -> tuple[bytes, ...]:
    """Frame a deliberately invalid section-check mutant with valid local checks."""

    count = (len(envelope) + 156) // 157
    return tuple(
        bootstrap.encode_common_block(
            bootstrap.CommonBlock(
                profile_version,
                section.section_id,
                semantic_copy_id,
                section.section_type,
                section.section_version,
                index,
                count,
                len(envelope),
                envelope[index * 157 : min((index + 1) * 157, len(envelope))],
            )
        )
        for index in range(count)
    )


def _resource_route_observation(
    context: _Context, field_offset: int, value: int, width: int
) -> bytes:
    """Mutate the exact sector-0 kind-5 package resource field."""

    if (field_offset, width) not in ((36, 8), (44, 4)):
        _fail("resource-route-field")
    shell_row = next(
        row for row in context.candidate["shell_rows"] if row["sector_id"] == 0
    )
    prefix_cells = int(shell_row["route_prefix_cells"])
    if prefix_cells % 8:
        _fail("resource-route-prefix")
    sector_cells = context.width * (context.side - context.width)
    local_bits = bytearray(
        context.clean[row * context.side + column]
        for offset in range(sector_cells)
        for row, column in (
            bootstrap.sector_cell(context.side, context.width, 0, offset),
        )
    )
    prefix = bytearray(_packed(local_bits[:prefix_cells]))
    if (
        len(prefix) < 64
        or prefix[:32] == bytes(32)
        or prefix[32:40] != b"GBROUTE\0"
        or int.from_bytes(prefix[48:52], "big") != len(prefix) - 64
    ):
        _fail("resource-route-envelope")
    cursor = 64
    package_offsets: list[int] = []
    while cursor < len(prefix):
        if cursor + 8 > len(prefix):
            _fail("resource-route-record")
        kind = prefix[cursor + 1]
        payload_length = int.from_bytes(prefix[cursor + 4 : cursor + 8], "big")
        payload = cursor + 8
        end = payload + payload_length
        if end > len(prefix):
            _fail("resource-route-record")
        if kind == 5:
            package_offsets.append(payload)
        cursor = end
    if cursor != len(prefix) or not package_offsets:
        _fail("resource-route-record")
    package = min(package_offsets)
    target = package + field_offset
    if prefix[package : package + 8] != b"GBRECP0\0" or target + width > len(prefix):
        _fail("resource-route-package")
    prefix[target : target + width] = value.to_bytes(width, "big")
    changed_bits = _bits(prefix, prefix_cells)
    matrix = bytearray(context.clean)
    for offset, bit in enumerate(changed_bits):
        row, column = bootstrap.sector_cell(
            context.side, context.width, 0, offset
        )
        matrix[row * context.side + column] = bit
    return _obs_bits(matrix)


def _r3_d7_case_spec(
    context: _Context,
    profile: m2_codec.CandidateProfile,
    alternate_recipient_package: bytes,
    alternate_route_manifest_raw: bytes,
    ordinal: int,
) -> _DamageCaseSpec:
    """Build one exact frozen D7 case without traversing any other family."""

    if (
        not context.is_r3
        or profile.profile_id != R3_PROFILE_ID
        or profile.profile_version != 7
        or type(alternate_recipient_package) is not bytes
        or type(alternate_route_manifest_raw) is not bytes
        or type(ordinal) is not int
        or not 0 <= ordinal < 408
    ):
        _fail("r3-d7-probe-input")
    all_ids = tuple(sorted(context.clean_encoded))
    first_common = context.clean_common[1]
    initial_target_ids = tuple(range(1, 6))
    target_section = 2
    target_envelope = context.clean_envelopes[target_section]
    section = bootstrap.decode_section_envelope(target_envelope)
    channel: str
    operator: str
    parameters: dict[str, tuple[str, object]]
    observation: bytes
    expected: _Result

    if ordinal < 3:
        multiplier, offset = (
            (1, 0),
            (context.multiplier, (context.offset + 1) % context.population),
            (2 * context.interior + 1, context.offset),
        )[ordinal]
        matrix = bytearray(context.clean)
        for unit_id in all_ids:
            logical_first = int(
                context.row_by_unit[unit_id]["logical_bit_first"]
            )
            for bit_offset, bit in enumerate(
                _bits(context.clean_encoded[unit_id])
            ):
                physical = (
                    multiplier * (logical_first + bit_offset) + offset
                ) % context.population
                row, column = divmod(physical, context.interior)
                matrix[
                    (row + context.width) * context.side
                    + column
                    + context.width
                ] = bit
        replacements: dict[int, bytes] = {}
        for unit_id in all_ids:
            extracted = bytearray(context.unit_bits)
            for bit_offset in range(context.unit_bits):
                physical = context.physical_cell(unit_id, bit_offset)
                row, column = divmod(physical, context.interior)
                extracted[bit_offset] = matrix[
                    (row + context.width) * context.side
                    + column
                    + context.width
                ]
            value = _packed(extracted)
            if value != context.clean_encoded[unit_id]:
                replacements[unit_id] = value
        channel = m2_decoder.OBS_BITS
        operator = "mapping-mutants"
        parameters = {"mutant_ordinal": ("u64", ordinal)}
        observation = _obs_bits(matrix)
        expected = context.evaluate(replacements)
    elif ordinal < 5:
        local_ordinal = ordinal - 3
        if local_ordinal == 0:
            value = _reencode_unit(
                first_common[:187] + first_common[187:][::-1]
            )
        else:
            register = 0xFFFF_FFFF
            for byte in bootstrap.LOCAL_DOMAIN + first_common[:187]:
                register ^= byte << 24
                for _ in range(8):
                    register = (
                        ((register << 1) ^ 0x1EDC6F41) & 0xFFFF_FFFF
                        if register & 0x8000_0000
                        else (register << 1) & 0xFFFF_FFFF
                    )
            reflected = (register ^ 0xFFFF_FFFF).to_bytes(4, "big")
            value = _reencode_unit(first_common[:187] + reflected)
        replacements = {unit_id: value for unit_id in initial_target_ids}
        encoded = dict(context.clean_encoded)
        encoded.update(replacements)
        channel = m2_decoder.OBS_UNITS
        operator = "check-mutants"
        parameters = {
            "case_ordinal": ("u64", local_ordinal),
            "target_unit_ids": ("u64-list", list(initial_target_ids)),
        }
        observation = _obs_units(all_ids, encoded)
        expected = context.evaluate(replacements)
    elif ordinal < 7:
        local_ordinal = ordinal - 5
        if local_ordinal == 0:
            envelope_value = bytearray(target_envelope)
            envelope_value[11] = 2 if section.check_id == 1 else 1
            envelope = bytes(envelope_value)
        else:
            check_width = 4 if section.check_id == 1 else 8
            envelope = (
                target_envelope[:-check_width]
                + target_envelope[-check_width:][::-1]
            )
        fragments = _fragment_unchecked_envelope(
            envelope, section, profile.profile_version, 0
        )
        replacements = {
            int(row["physical_unit_id"]): _reencode_unit(
                fragments[int(row["fragment_index"])]
            )
            for row in context.rows_by_section[target_section]
        }
        encoded = dict(context.clean_encoded)
        encoded.update(replacements)
        channel = m2_decoder.OBS_UNITS
        operator = "check-mutants"
        parameters = {
            "case_ordinal": ("u64", local_ordinal + 2),
            "section_id": ("u64", target_section),
        }
        observation = _obs_units(all_ids, encoded)
        expected = context.evaluate(replacements)
    elif ordinal < 10:
        local_ordinal = ordinal - 7
        mutant = (
            "eh-parity-position-off-by-one",
            "eh-position-72-in-hamming-equations",
            "eh-lsb-first",
        )[local_ordinal]
        value = _eh_mutant_unit(first_common, mutant)
        replacements = {unit_id: value for unit_id in initial_target_ids}
        encoded = dict(context.clean_encoded)
        encoded.update(replacements)
        channel = m2_decoder.OBS_UNITS
        operator = "code-mutants"
        parameters = {
            "case_ordinal": ("u64", local_ordinal),
            "target_unit_ids": ("u64-list", list(initial_target_ids)),
        }
        observation = _obs_units(all_ids, encoded)
        expected = context.evaluate(replacements)
    elif ordinal == 10:
        alternate_profile = next(
            item
            for item in m2_codec.r3_registry_profiles(profile)
            if item.profile_version == 3
        )
        alternate_routes = m2_route_data.build_route_images(
            alternate_route_manifest_raw,
            m2_route_data.CandidateRouteData(
                alternate_profile.profile_id,
                alternate_profile.profile_version,
                alternate_profile.transport_id,
                alternate_profile.section_check_id,
                (alternate_recipient_package,),
            ),
            context.side,
            context.width,
        )
        matrix = bytearray(context.clean)
        _replace_sector_route_prefix(
            matrix,
            context.side,
            context.width,
            alternate_routes.sectors[0],
        )
        channel = m2_decoder.OBS_BITS
        operator = "route-conflicts"
        parameters = {
            "alternate_profile_version": (
                "u64",
                alternate_profile.profile_version,
            )
        }
        observation = _obs_bits(matrix)
        expected = context.evaluate()
    elif ordinal < 16:
        local_ordinal = ordinal - 11
        other = tuple(
            item
            for item in m2_codec.r3_registry_profiles(profile)
            if item.profile_id != profile.profile_id
        )[local_ordinal]
        block = bootstrap.decode_common_block(
            first_common, profile.profile_version
        )
        other_common = bootstrap.encode_common_block(
            replace(block, profile_version=other.profile_version)
        )
        other_encoded = (
            m2_codec.eh72_encode_unit(other_common)
            if other.transport_id == m2_codec.EH_TRANSPORT
            else m2_codec.rs255_191_encode(other_common)
        )
        replacements = {
            unit_id: other_encoded for unit_id in initial_target_ids
        }
        encoded = dict(context.clean_encoded)
        encoded.update(replacements)
        channel = m2_decoder.OBS_UNITS
        operator = "cross-profile-splices"
        parameters = {
            "source_profile_version": ("u64", other.profile_version),
            "target_unit_ids": ("u64-list", list(initial_target_ids)),
        }
        observation = _obs_units(all_ids, encoded)
        expected = context.evaluate(replacements)
    elif ordinal == 16:
        block = bootstrap.decode_common_block(
            first_common, profile.profile_version
        )
        changed = replace(
            block,
            payload=bytes((block.payload[0] ^ 1,)) + block.payload[1:],
        )
        replacements = {
            1: _reencode_unit(bootstrap.encode_common_block(changed))
        }
        encoded = dict(context.clean_encoded)
        encoded.update(replacements)
        channel = m2_decoder.OBS_UNITS
        operator = "valid-copy-conflicts"
        parameters = {
            "section_id": ("u64", 1),
            "target_unit_id": ("u64", 1),
        }
        observation = _obs_units(all_ids, encoded)
        expected = context.evaluate(replacements)
    elif ordinal < 273:
        local_ordinal = ordinal - 17
        square = max(32, context.interior // 32)
        top, left = _d2_placements(context, square)[local_ordinal]
        expanded = square + 1
        top = min(top, context.side - context.width - expanded)
        left = min(left, context.side - context.width - expanded)
        coordinates = tuple(
            (top + row, left + column)
            for row in range(expanded)
            for column in range(expanded)
        )
        replacements, erasures = context.coordinate_damage(coordinates, True)
        matrix = bytearray(context.clean)
        for row, column in coordinates:
            matrix[row * context.side + column] = 2
        channel = m2_decoder.OBS_MATRIX
        operator = "d2-one-beyond"
        parameters = {
            "d2_ordinal": ("u64", local_ordinal),
            "side": ("u64", expanded),
        }
        observation = _obs_matrix(context.side, matrix)
        expected = context.evaluate(replacements, erasures)
    elif ordinal < 401:
        local_ordinal = ordinal - 273
        coordinates = _d3_coordinates(context, local_ordinal, 1)
        replacements, erasures = context.coordinate_damage(coordinates, False)
        matrix = bytearray(context.clean)
        for row, column in coordinates:
            matrix[row * context.side + column] ^= 1
        channel = m2_decoder.OBS_MATRIX
        operator = "d3-one-beyond"
        parameters = {
            "seed": ("u64", 5_134_751_402_299_490_304 + local_ordinal)
        }
        observation = _obs_matrix(context.side, matrix)
        expected = context.evaluate(replacements, erasures)
    elif ordinal == 401:
        omitted = set(initial_target_ids)
        channel = m2_decoder.OBS_UNITS
        operator = "missing-unit-one-beyond"
        parameters = {
            "omitted_unit_ids": ("u64-list", sorted(omitted))
        }
        observation = _obs_units(
            tuple(item for item in all_ids if item not in omitted),
            context.clean_encoded,
        )
        expected = context.evaluate(omitted=omitted)
    elif ordinal < 405:
        local_ordinal = ordinal - 402
        errors, erased_count = ((2, 0), (1, 2), (0, 4))[local_ordinal]
        matrix = bytearray(context.clean)
        erasures: dict[int, tuple[int, ...]] = {}
        replacements = {}
        erased_offsets = tuple(range(erased_count))
        for unit_id in initial_target_ids:
            bits = _bits(context.clean_encoded[unit_id])
            for bit in erased_offsets:
                physical = context.physical_cell(unit_id, bit)
                row, column = divmod(physical, context.interior)
                matrix[
                    (row + context.width) * context.side
                    + column
                    + context.width
                ] = 2
            for bit in range(erased_count, erased_count + errors):
                bits[bit] ^= 1
                physical = context.physical_cell(unit_id, bit)
                row, column = divmod(physical, context.interior)
                index = (
                    (row + context.width) * context.side
                    + column
                    + context.width
                )
                matrix[index] ^= 1
            if errors:
                replacements[unit_id] = _packed(bits)
            if erased_count:
                erasures[unit_id] = erased_offsets
        channel = m2_decoder.OBS_MATRIX
        operator = "algebraic-one-beyond"
        parameters = {
            "erasures": ("u64", erased_count),
            "errors": ("u64", errors),
            "target_unit_ids": ("u64-list", list(initial_target_ids)),
        }
        observation = _obs_matrix(context.side, matrix)
        expected = context.evaluate(replacements, erasures)
    elif ordinal < 407:
        local_ordinal = ordinal - 405
        field_offset, width, declared = (
            (36, 8, 268_435_457),
            (44, 4, 16_777_217),
        )[local_ordinal]
        channel = m2_decoder.OBS_BITS
        operator = "resource-route-one-beyond"
        parameters = {"declared_value": ("u64", declared)}
        observation = _resource_route_observation(
            context, field_offset, declared, width
        )
        expected = context.evaluate(forced_state="resource-limit")
    else:
        geometry_count = 2_056 * 2_056
        channel = m2_decoder.OBS_BITS
        operator = "geometry-one-beyond"
        parameters = {"side": ("u64", 2_056)}
        observation = geometry_count.to_bytes(4, "big") + bytes(
            (geometry_count + 7) // 8
        )
        expected = context.evaluate(forced_state="failure")

    expected_channel, expected_operator, projection, _ = _r3_case_shape(
        "D7", ordinal
    )
    parameter_shape = tuple(
        (str(row["id"]), str(row["value_type"]))
        for row in _parameter_rows(parameters)
    )
    if (
        channel != expected_channel
        or operator != expected_operator
        or parameter_shape != projection
    ):
        _fail("r3-d7-probe-shape")
    return _DamageCaseSpec(
        channel, operator, parameters, observation, expected
    )


def _run_damage(
    manifestation: m2_carrier.Manifestation,
    profile: m2_codec.CandidateProfile,
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    damage_policy_raw: bytes,
    route_manifest_raw: bytes,
    alternate_recipient_package: bytes,
    rust_decoder_command: Sequence[str] | None,
    worker_count: int,
    alternate_route_manifest_raw: bytes | None = None,
) -> DamageRun:
    """Run the exact frozen D0--D7 corpus for one gate-5 survivor."""

    is_r3 = profile.profile_version == 7
    if is_r3:
        try:
            decoder_policy = m2_policy.load_r3_decoder_policy(
                profile_policy_raw,
                profile_limits_raw,
                damage_policy_raw,
            )
        except m2_policy.PolicyError as error:
            raise DamageError("policy-binding") from error
        policy_sha256 = decoder_policy.profile_policy_sha256
        damage_sha256 = decoder_policy.damage_policy_sha256
    else:
        policy = m2_policy.load_profile_policy(profile_policy_raw)
        damage = m2_policy.load_damage_policy(damage_policy_raw)
        policy_sha256 = policy.sha256
        damage_sha256 = damage.sha256
    document = tomllib.loads(damage_policy_raw.decode("utf-8"))
    if (
        damage_sha256 != sha256(damage_policy_raw).hexdigest()
        or policy_sha256 != sha256(profile_policy_raw).hexdigest()
    ):
        _fail("policy-binding")
    if is_r3 and type(alternate_route_manifest_raw) is not bytes:
        _fail("alternate-route-owner")
    context = _Context(manifestation, profile)
    evaluator = _DamageEvaluator(
        context,
        profile_policy_raw,
        profile_limits_raw,
        damage_policy_raw,
        alternate_recipient_package,
        rust_decoder_command,
        worker_count,
        alternate_route_manifest_raw=alternate_route_manifest_raw,
    )
    candidate = context.candidate
    candidate_profiles = (
        m2_codec.r3_registry_profiles(profile)
        if is_r3
        else m2_codec.load_candidate_profiles(
            profile_policy_raw, profile_limits_raw
        )
    )
    if (
        candidate["profile_policy_sha256"] != policy_sha256
        or candidate["profile_limits_sha256"]
        != sha256(profile_limits_raw).hexdigest()
    ):
        _fail("candidate-policy-binding")
    clean_observation = _obs_bits(context.clean)
    rows: list[dict[str, object]] = []
    counts: list[tuple[str, int]] = []

    # D0: all physical orientation/polarity views normalize to the same carrier.
    start = len(rows)
    for transform in range(8):
        for polarity in range(2):
            observed = _transform_matrix(context.clean, context.side, transform, polarity)
            result = context.evaluate()
            rows.append(_case_row(
                f"D0-{transform:02d}-{polarity}", "D0", "OBS_BITS", "clean-transform-polarity",
                {"polarity_id": ("u64", polarity), "transform_id": ("u64", transform)},
                _obs_bits(observed), result, evaluator,
            ))
    counts.append(("D0", len(rows) - start))

    # D1: shell redundancy leaves the protected interior untouched.
    start = len(rows)
    sector_cells = context.width * (context.side - context.width)
    for sector in range(4):
        coordinates = tuple(bootstrap.sector_cell(context.side, context.width, sector, offset) for offset in range(sector_cells))
        rows.append(_matrix_case(
            context, "D1", sector, "erase-one-complete-shell-sector", coordinates, True,
            {"sector_id": ("u64", sector)}, evaluator=evaluator,
        ))
    counts.append(("D1", len(rows) - start))

    # D2: nine anchors followed by the exact rejection-sampled placements.
    start = len(rows)
    square = max(32, context.interior // 32)
    placements = _d2_placements(context, square)
    for ordinal, (top, left) in enumerate(placements):
        coordinates = tuple((top + row, left + column) for row in range(square) for column in range(square))
        rows.append(_matrix_case(
            context, "D2", ordinal, "erase-square-in-protected-interior", coordinates, True,
            {"side": ("u64", square), "top_left": ("coordinate-list", [[top, left]])},
            evaluator=evaluator,
        ))
    counts.append(("D2", len(rows) - start))

    # D3: exact 128 seeds and four frozen strata.
    start = len(rows)
    for ordinal in range(128):
        coordinates = _d3_coordinates(context, ordinal)
        rows.append(_matrix_case(
            context, "D3", ordinal, "fixed-weight-unknown-bit-substitution", coordinates, False,
            {"coordinates": ("coordinate-list", [list(item) for item in coordinates]),
             "seed": ("u64", 5134751402299490304 + ordinal),
             "stratum_id": ("u64", ordinal // 32)}, evaluator=evaluator,
        ))
    counts.append(("D3", len(rows) - start))

    # D4: every unit omission, with all other complete observations present.
    start = len(rows)
    all_ids = tuple(sorted(context.clean_encoded))
    for ordinal, unit_id in enumerate(all_ids):
        order = tuple(value for value in all_ids if value != unit_id)
        result = context.evaluate(omitted={unit_id})
        rows.append(_case_row(
            f"D4-{ordinal:06d}",
            "D4",
            "OBS_UNITS",
            (
                "omit-one-physical-unit-observation"
                if is_r3
                else "omit-one-protected-unit-observation"
            ),
            {"omitted_unit_id": ("u64", unit_id)}, _obs_units(order, context.clean_encoded), result, evaluator,
        ))
    counts.append(("D4", len(rows) - start))

    # D5: five literal permutations and sixteen deterministic Fisher-Yates rows.
    start = len(rows)
    permutations = [
        all_ids,
        tuple(reversed(all_ids)),
        all_ids[1:] + all_ids[:1],
        all_ids[::2] + all_ids[1::2],
        all_ids[1::2] + all_ids[::2],
    ]
    for seed in range(5134751402299490560, 5134751402299490576):
        permutations.append(_fisher_yates(all_ids, seed))
    for ordinal, order in enumerate(permutations):
        rows.append(_case_row(
            f"D5-{ordinal:06d}",
            "D5",
            "OBS_UNITS",
            (
                "permute-intact-physical-unit-observations"
                if is_r3
                else "permute-intact-protected-unit-observations"
            ),
            {"permutation_ordinal": ("u64", ordinal)}, _obs_units(order, context.clean_encoded), context.evaluate(), evaluator,
        ))
    counts.append(("D5", len(rows) - start))

    # D6: the exact Cartesian product.  Recovery is equivalent to omitting the
    # fully erased unit; the observation hash still covers every erased cell.
    start = len(rows)
    sector_bases: list[bytearray] = []
    sector_coordinates: list[tuple[tuple[int, int], ...]] = []
    for sector in range(4):
        coords = tuple(bootstrap.sector_cell(context.side, context.width, sector, offset) for offset in range(sector_cells))
        matrix = bytearray(context.clean)
        for row, column in coords:
            matrix[row * context.side + column] = 2
        sector_bases.append(matrix)
        sector_coordinates.append(coords)
    for sector in range(4):
        for unit_id in all_ids:
            matrix = bytearray(sector_bases[sector])
            for bit in range(context.unit_bits):
                physical = context.physical_cell(unit_id, bit)
                local_row, local_column = divmod(physical, context.interior)
                matrix[(local_row + context.width) * context.side + local_column + context.width] = 2
            result = context.evaluate(
                erasures={unit_id: tuple(range(context.unit_bits))}
            )
            rows.append(_case_row(
                f"D6-{sector:01d}-{unit_id:06d}", "D6", "OBS_MATRIX",
                (
                    "erase-shell-sector-union-one-physical-unit-cell-set"
                    if is_r3
                    else "erase-shell-sector-union-one-protected-unit-cell-set"
                ),
                {"sector_id": ("u64", sector), "unit_id": ("u64", unit_id)},
                _obs_matrix(context.side, matrix), result, evaluator,
            ))
    counts.append(("D6", len(rows) - start))

    # D7 starts with three genuinely malformed mappings.  They are decoded
    # under the frozen mapping and therefore may only recover exact bytes or
    # fail explicitly.
    start = len(rows)
    mapping_variants = (
        (1, 0),
        (context.multiplier, (context.offset + 1) % context.population),
        (2 * context.interior + 1, context.offset),
    )
    for ordinal, (multiplier, offset) in enumerate(mapping_variants):
        matrix = bytearray(context.clean)
        for unit_id in all_ids:
            bits = _bits(context.clean_encoded[unit_id])
            logical_first = (
                int(context.row_by_unit[unit_id]["logical_bit_first"])
                if is_r3
                else (unit_id - 1) * context.unit_bits
            )
            for bit_offset, bit in enumerate(bits):
                logical = logical_first + bit_offset
                physical = (multiplier * logical + offset) % context.population
                local_row, local_column = divmod(physical, context.interior)
                matrix[(local_row + context.width) * context.side + local_column + context.width] = bit
        replacements: dict[int, bytes] = {}
        for unit_id in all_ids:
            extracted = bytearray(context.unit_bits)
            for bit_offset in range(context.unit_bits):
                physical = context.physical_cell(unit_id, bit_offset)
                local_row, local_column = divmod(physical, context.interior)
                extracted[bit_offset] = matrix[(local_row + context.width) * context.side + local_column + context.width]
            value = _packed(extracted)
            if value != context.clean_encoded[unit_id]:
                replacements[unit_id] = value
        result = context.evaluate(replacements)
        rows.append(_case_row(
            "", "D7", "OBS_BITS", "mapping-mutants",
            {"mutant_ordinal": ("u64", ordinal)}, _obs_bits(matrix), result, evaluator,
        ))

    # Check mutants use the exact lowest numeric unit or lowest required
    # noninventory section named by the owner.
    first = all_ids[0]
    first_common = context.clean_common[first]
    initial_target_ids = tuple(range(1, 6)) if is_r3 else (first,)
    target_section = next(
        int(row["section_id"])
        for row in context.section_rows
        if int(row["closure_class"]) == 128
        and int(row["section_id"]) != 1
    )
    target_envelope = context.clean_envelopes[target_section]
    section = bootstrap.decode_section_envelope(target_envelope)
    local_mutants: list[tuple[str, bytes]] = [
        (
            "local-wrong-stored-byte-order",
            _reencode_unit(first_common[:187] + first_common[187:][::-1]),
        )
    ]
    reflected_register = 0xFFFF_FFFF
    for byte in bootstrap.LOCAL_DOMAIN + first_common[:187]:
        reflected_register ^= byte << 24
        for _ in range(8):
            reflected_register = (
                ((reflected_register << 1) ^ 0x1EDC6F41) & 0xFFFF_FFFF
                if reflected_register & 0x8000_0000
                else (reflected_register << 1) & 0xFFFF_FFFF
            )
    reflected = (reflected_register ^ 0xFFFF_FFFF).to_bytes(4, "big")
    local_mutants.append(
        ("local-wrong-reflection", _reencode_unit(first_common[:187] + reflected))
    )
    for ordinal, (_name, value) in enumerate(local_mutants):
        encoded = dict(context.clean_encoded)
        replacements = {
            unit_id: value for unit_id in initial_target_ids
        }
        encoded.update(replacements)
        local_parameters: dict[str, tuple[str, object]] = {
            "case_ordinal": ("u64", ordinal),
        }
        local_parameters[
            "target_unit_ids" if is_r3 else "target_unit_id"
        ] = (
            "u64-list" if is_r3 else "u64",
            list(initial_target_ids) if is_r3 else first,
        )
        rows.append(_case_row(
            "", "D7", "OBS_UNITS", "check-mutants",
            local_parameters,
            _obs_units(all_ids, encoded),
            context.evaluate(replacements),
            evaluator,
        ))

    # The remaining two check cases rebuild one complete locally valid copy
    # while leaving its section check deliberately invalid.
    section_variants: list[bytes] = []
    wrong_id = bytearray(target_envelope)
    wrong_id[11] = 2 if section.check_id == 1 else 1
    section_variants.append(bytes(wrong_id))
    check_width = 4 if section.check_id == 1 else 8
    section_variants.append(
        target_envelope[:-check_width] + target_envelope[-check_width:][::-1]
    )
    for ordinal, envelope in enumerate(section_variants):
        fragments = _fragment_unchecked_envelope(
            envelope, section, profile.profile_version, 0
        )
        target_rows = sorted(
            (row for row in context.rows_by_section[target_section] if int(row["semantic_copy_id"]) == 0),
            key=lambda row: int(row["fragment_index"]),
        )
        replacements = {
            int(row["physical_unit_id"]): _reencode_unit(
                fragments[int(row["fragment_index"])]
            )
            for row in target_rows
        }
        encoded = dict(context.clean_encoded)
        encoded.update(replacements)
        result = context.evaluate(replacements)
        rows.append(_case_row(
            "", "D7", "OBS_UNITS", "check-mutants",
            {
                "case_ordinal": ("u64", ordinal + 2),
                "section_id": ("u64", target_section),
            },
            _obs_units(all_ids, encoded), result, evaluator,
        ))

    # Each EH code mutant re-encodes all 24 chunks of the lowest numeric unit.
    for ordinal, name in enumerate(
        (
            "eh-parity-position-off-by-one",
            "eh-position-72-in-hamming-equations",
            "eh-lsb-first",
        )
    ):
        value = _eh_mutant_unit(first_common, name)
        encoded = dict(context.clean_encoded)
        replacements = {
            unit_id: value for unit_id in initial_target_ids
        }
        encoded.update(replacements)
        code_parameters: dict[str, tuple[str, object]] = {
            "case_ordinal": ("u64", ordinal),
        }
        code_parameters[
            "target_unit_ids" if is_r3 else "target_unit_id"
        ] = (
            "u64-list" if is_r3 else "u64",
            list(initial_target_ids) if is_r3 else first,
        )
        rows.append(_case_row(
            "", "D7", "OBS_UNITS", "code-mutants",
            code_parameters,
            _obs_units(all_ids, encoded),
            context.evaluate(replacements), evaluator,
        ))

    # One alternate route is locally complete, while the other three routes
    # still establish the one exact downstream artifact.
    alternate_profile = (
        next(
            item
            for item in candidate_profiles
            if item.profile_version == 3
        )
        if is_r3
        else next(
            item
            for item in candidate_profiles
            if item.transport_id == "eh72-replicated-v0"
            and item.section_check_id == profile.section_check_id
            and item.required_copy_count != profile.required_copy_count
        )
    )
    alternate_routes = m2_route_data.build_route_images(
        (
            alternate_route_manifest_raw
            if is_r3
            else route_manifest_raw
        ),
        m2_route_data.CandidateRouteData(
            alternate_profile.profile_id,
            alternate_profile.profile_version,
            alternate_profile.transport_id,
            alternate_profile.section_check_id,
            (alternate_recipient_package,),
        ),
        context.side,
        context.width,
    )
    route_conflict_matrix = bytearray(context.clean)
    _replace_sector_route_prefix(
        route_conflict_matrix,
        context.side,
        context.width,
        alternate_routes.sectors[0],
    )
    rows.append(_case_row(
        "", "D7", "OBS_BITS", "route-conflicts",
        {"alternate_profile_version": ("u64", alternate_profile.profile_version)},
        _obs_bits(route_conflict_matrix),
        # The alternate shell route is locally complete, but its different
        # profile/version must still validate the unchanged interior.  It does
        # not become semantic ambiguity merely by existing; the three current
        # routes retain the one exact downstream result.
        context.evaluate(), evaluator,
    ))

    # Cross-profile splice rows use the same current clean lowest common block,
    # changing only its profile version before rechecking and reencoding it.
    block = bootstrap.decode_common_block(first_common, profile.profile_version)
    cross_ordinal = 0
    for other in candidate_profiles:
        if other.profile_id == profile.profile_id:
            continue
        other_common = bootstrap.encode_common_block(
            replace(block, profile_version=other.profile_version)
        )
        other_encoded = (
            m2_codec.eh72_encode_unit(other_common)
            if other.transport_id == m2_codec.EH_TRANSPORT
            else m2_codec.rs255_191_encode(other_common)
        )
        encoded = dict(context.clean_encoded)
        splice_ids = initial_target_ids if is_r3 else (first,)
        replacements = {
            unit_id: other_encoded for unit_id in splice_ids
        }
        encoded.update(replacements)
        splice_parameters: dict[str, tuple[str, object]] = {
            "source_profile_version": ("u64", other.profile_version),
        }
        splice_parameters[
            "target_unit_ids" if is_r3 else "target_unit_id"
        ] = (
            "u64-list" if is_r3 else "u64",
            list(splice_ids) if is_r3 else first,
        )
        rows.append(_case_row(
            "", "D7", "OBS_UNITS", "cross-profile-splices",
            splice_parameters,
            _obs_units(all_ids, encoded),
            context.evaluate(replacements),
            evaluator,
        ))
        cross_ordinal += 1
    if cross_ordinal != len(candidate_profiles) - 1:
        _fail("cross-profile-count")

    # A distinct fully checked copy must be reported ambiguous, never voted.
    if is_r3:
        changed_block = replace(
            block,
            payload=bytes((block.payload[0] ^ 1,)) + block.payload[1:],
        )
        replacements = {
            1: _reencode_unit(
                bootstrap.encode_common_block(changed_block)
            )
        }
        conflict_parameters = {
            "section_id": ("u64", 1),
            "target_unit_id": ("u64", 1),
        }
    else:
        changed = replace(
            section,
            payload=bytes((section.payload[0] ^ 1,))
            + section.payload[1:],
        )
        changed_envelope = bootstrap.encode_section_envelope(changed)
        fragments = bootstrap.fragment_section(
            changed_envelope, profile.profile_version, 0
        )
        target_rows = sorted(
            (
                row
                for row in context.rows_by_section[target_section]
                if int(row["semantic_copy_id"]) == 0
            ),
            key=lambda row: int(row["fragment_index"]),
        )
        replacements = {
            int(row["physical_unit_id"]): _reencode_unit(fragment)
            for row, fragment in zip(target_rows, fragments, strict=True)
        }
        conflict_parameters = {
            "section_id": ("u64", target_section)
        }
    encoded = dict(context.clean_encoded)
    encoded.update(replacements)
    rows.append(_case_row(
        "", "D7", "OBS_UNITS", "valid-copy-conflicts",
        conflict_parameters,
        _obs_units(all_ids, encoded),
        context.evaluate(replacements),
        evaluator,
    ))

    # The D2 and D3 one-beyond rows restart the exact frozen generators.
    for ordinal, (top, left) in enumerate(placements):
        expanded = square + 1
        shifted_top = min(top, context.side - context.width - expanded)
        shifted_left = min(left, context.side - context.width - expanded)
        coordinates = tuple((shifted_top + row, shifted_left + column) for row in range(expanded) for column in range(expanded))
        rows.append(_matrix_case(
            context, "D7", len(rows) - start, "d2-one-beyond", coordinates, True,
            {"d2_ordinal": ("u64", ordinal), "side": ("u64", expanded)},
            evaluator=evaluator,
        ))
    for ordinal in range(128):
        coordinates = _d3_coordinates(context, ordinal, 1)
        rows.append(_matrix_case(
            context, "D7", len(rows) - start, "d3-one-beyond", coordinates, False,
            {"seed": ("u64", 5134751402299490304 + ordinal)},
            evaluator=evaluator,
        ))

    # Correlated omission crosses the exact owner boundary for this profile.
    if is_r3:
        omitted = set(range(1, 6))
    else:
        first_section_rows = context.rows_by_section[target_section]
        by_copy: dict[int, list[dict[str, object]]] = {}
        for row in first_section_rows:
            by_copy.setdefault(int(row["semantic_copy_id"]), []).append(row)
        omitted = {
            int(
                sorted(
                    by_copy[copy_id],
                    key=lambda row: int(row["fragment_index"]),
                )[0]["physical_unit_id"]
            )
            for copy_id in sorted(by_copy)[:2]
        }
    order = tuple(unit_id for unit_id in all_ids if unit_id not in omitted)
    rows.append(_case_row(
        "", "D7", "OBS_UNITS", "missing-unit-one-beyond",
        {"omitted_unit_ids": ("u64-list", sorted(omitted))}, _obs_units(order, context.clean_encoded), context.evaluate(omitted=omitted), evaluator,
    ))

    # EH algebraic one-beyond cases target the first codeword in every lane of
    # the first v7 REP5 group (one legacy unit in the historical path).
    for ordinal, (errors, erased_count) in enumerate(((2, 0), (1, 2), (0, 4))):
        matrix = bytearray(context.clean)
        coordinates: list[tuple[int, int]] = []
        erasure_map: dict[int, tuple[int, ...]] = {}
        replacement_map: dict[int, bytes] = {}
        erased_offsets = tuple(range(erased_count))
        algebra_ids = initial_target_ids if is_r3 else (first,)
        for unit_id in algebra_ids:
            bits = _bits(context.clean_encoded[unit_id])
            for bit in erased_offsets:
                physical = context.physical_cell(unit_id, bit)
                row, column = divmod(physical, context.interior)
                coordinate = (
                    row + context.width,
                    column + context.width,
                )
                matrix[coordinate[0] * context.side + coordinate[1]] = 2
                coordinates.append(coordinate)
            for bit in range(erased_count, erased_count + errors):
                bits[bit] ^= 1
                physical = context.physical_cell(unit_id, bit)
                row, column = divmod(physical, context.interior)
                coordinate = (
                    row + context.width,
                    column + context.width,
                )
                matrix[coordinate[0] * context.side + coordinate[1]] ^= 1
                coordinates.append(coordinate)
            if errors:
                replacement_map[unit_id] = _packed(bits)
            if erased_count:
                erasure_map[unit_id] = erased_offsets
        algebra_parameters: dict[str, tuple[str, object]] = {
            "erasures": ("u64", erased_count),
            "errors": ("u64", errors),
        }
        if is_r3:
            algebra_parameters["target_unit_ids"] = (
                "u64-list",
                list(algebra_ids),
            )
        rows.append(_case_row(
            "", "D7", "OBS_MATRIX", "algebraic-one-beyond",
            algebra_parameters,
            _obs_matrix(context.side, matrix), context.evaluate(replacement_map, erasure_map), evaluator,
        ))

    # Resource and geometry boundaries are rejected before candidate output.
    for ordinal, (name, field_offset, width, declared) in enumerate((
        ("recipe-step-ceiling-plus-one", 36, 8, 268_435_457),
        ("recipe-scratch-ceiling-plus-one", 44, 4, 16_777_217),
    )):
        observation = _resource_route_observation(
            context, field_offset, declared, width
        )
        rows.append(_case_row(
            "", "D7", "OBS_BITS", "resource-route-one-beyond",
            {"declared_value": ("u64", declared)},
            observation,
            context.evaluate(forced_state="resource-limit"),
            evaluator,
        ))
    geometry_count = 2056 * 2056
    rows.append(_case_row(
        "", "D7", "OBS_BITS", "geometry-one-beyond",
        {"side": ("u64", 2056)}, geometry_count.to_bytes(4, "big") + bytes((geometry_count + 7) // 8),
        context.evaluate(forced_state="failure"), evaluator,
    ))
    d7_count = (
        int(document["d7"]["case_count"])
        if is_r3
        else int(document["d7"]["case_count"]["eh_total"])
    )
    if len(rows) - start != d7_count:
        _fail("d7-case-count")
    counts.append(("D7", len(rows) - start))

    evaluator.finish(rows)
    wrong = sum(int(row["wrong_accept_count"]) for row in rows)
    damage_cap = next(
        item
        for item in tomllib.loads(profile_limits_raw.decode("utf-8"))["profile"]
        if item["profile_version"] == profile.profile_version
    )["damage_cases"]
    expected_total = (
        16
        + 4
        + 256
        + 128
        + len(all_ids)
        + 21
        + 4 * len(all_ids)
        + d7_count
    )
    if (
        len(rows) != expected_total
        or len(rows) > damage_cap
        or tuple(family for family, _ in counts) != tuple(f"D{i}" for i in range(8))
    ):
        _fail("case-count")
    required_ids = {
        int(row["section_id"])
        for row in context.section_rows
        if int(row["closure_class"]) == 128
    }
    exact_states = {"verified", "recovered"}
    family_passes: dict[str, bool] = {}
    for family, _ in counts:
        family_rows = [row for row in rows if row["family_id"] == family]
        passed = all(
            int(row["wrong_accept_count"]) == 0
            and evaluator.match_by_case.get(str(row["case_id"]), False)
            for row in family_rows
        )
        if family in ("D0", "D1", "D5"):
            passed = passed and all(
                all(
                    str(item["state"]) in exact_states
                    for item in row["expected_section_states"]
                )
                for row in family_rows
            )
        elif family in ("D2", "D3", "D4", "D6"):
            passed = passed and all(
                all(
                    next(
                        str(item["state"])
                        for item in row["expected_section_states"]
                        if int(item["section_id"]) == section_id
                    )
                    in exact_states
                    for section_id in required_ids
                )
                for row in family_rows
            )
        family_passes[family] = passed
    boundary_rows: list[dict[str, object]] = []
    boundary_pass = True
    if is_r3:
        for ordinal, kat_id in enumerate(R3_BOUNDARY_KAT_IDS):
            boundary_raw = m2_decoder.r3_boundary_kat(ordinal)
            rust_boundary_raw = evaluator.boundary_kat(ordinal)
            try:
                boundary_value = (
                    canonical_manifest.validate_canonical_manifest(
                        boundary_raw
                    )
                )
            except (TypeError, ValueError):
                boundary_value = {}
            passed = (
                rust_boundary_raw == boundary_raw
                and boundary_value
                == {
                    "schema": R3_BOUNDARY_SCHEMA,
                    "kat_id": kat_id,
                    "result": "pass",
                }
            )
            boundary_pass = boundary_pass and passed
            boundary_rows.append(
                {
                    "kat_id": kat_id,
                    "result_sha256": sha256(boundary_raw).hexdigest(),
                    "result": "pass" if passed else "fail",
                }
            )
    else:
        boundary_raw = m2_decoder.section_attempt_boundary_kat()
        rust_boundary_raw = evaluator.boundary_kat()
        boundary_sha256 = sha256(boundary_raw).hexdigest()
        boundary_pass = (
            len(boundary_raw) == 307
            and rust_boundary_raw == boundary_raw
            and boundary_sha256
            == "4ad1468cd6cac6774b95e997d37c6fb420ff94cc0aa82595aeaa7b356440a68b"
        )
        boundary_rows.append(
            {
                "kat_id": "section-attempt-ceiling-plus-one",
                "result_sha256": boundary_sha256,
                "result": "pass" if boundary_pass else "fail",
            }
        )
    evaluator.close()
    family_passes["D7"] = family_passes["D7"] and boundary_pass
    family_root_rows = [
        {
            "family_id": family,
            "case_count": count,
            "wrong_accept_count": sum(
                int(row["wrong_accept_count"])
                for row in rows
                if row["family_id"] == family
            ),
            "result": "pass" if family_passes[family] else "fail",
            "case_rows_sha256": _canonical_array_sha256(
                [row for row in rows if row["family_id"] == family]
            ),
        }
        for family, count in counts
    ]
    summary_without_identity: dict[str, object] = {
        "family_case_counts": [
            {"family_id": family, "case_count": count} for family, count in counts
        ],
        "wrong_accept_count": wrong,
    }
    value: dict[str, object] = {
        "schema": R3_DAMAGE_SCHEMA if is_r3 else DAMAGE_SCHEMA,
        "damage_policy_sha256": damage_sha256,
        "profile_policy_sha256": policy_sha256,
    }
    if is_r3:
        generated = document.get("generated")
        if type(generated) is not dict:
            _fail("damage-owner")
        value.update(
            {
                "profile_limits_sha256": sha256(
                    profile_limits_raw
                ).hexdigest(),
                "bootstrap_spec_sha256": candidate[
                    "bootstrap_spec_sha256"
                ],
                "route_data_sha256": sha256(
                    route_manifest_raw
                ).hexdigest(),
                "recipient_package_sha256": generated[
                    "recipient_package_sha256"
                ],
            }
        )
    value.update(
        {
            "profile_id": profile.profile_id,
            "candidate_manifest_sha256": sha256(
                manifestation.candidate_manifest
            ).hexdigest(),
            "clean_observation_sha256": sha256(
                clean_observation
            ).hexdigest(),
            "family_rows": family_root_rows,
            "boundary_kat_rows": boundary_rows,
            "summary": summary_without_identity,
        }
    )
    manifest_identity = identity.identity_hex(
        b"golden-board:manifest:v0\0", (canonical_manifest.serialize_manifest(value),)
    )
    value["summary"] = {**summary_without_identity, "manifest_identity": manifest_identity}
    raw = canonical_manifest.serialize_manifest(value)
    guarantees = (
        "all_declared_m2_sections_exact",
        "all_declared_m2_sections_exact",
        "m2_required_closure",
        "m2_required_closure",
        "m2_required_closure",
        "all_declared_m2_sections_exact",
        "m2_required_closure",
        "correct_or_explicit_failure",
    )
    family_manifests: list[bytes] = []
    case_shards: list[tuple[str, bytes]] = []
    for family_index, (family, count) in enumerate(counts):
        family_rows = [row for row in rows if row["family_id"] == family]
        shard_rows: list[dict[str, object]] = []
        first = 0
        shard_ordinal = 0
        while first < len(family_rows):
            maximum = min(256, len(family_rows) - first)

            def render_shard(take: int) -> bytes:
                selected = family_rows[first : first + take]
                shard_summary: dict[str, object] = {
                    "case_count": take,
                    "wrong_accept_count": sum(
                        int(row["wrong_accept_count"]) for row in selected
                    ),
                }
                shard_value: dict[str, object] = {
                    "schema": R3_SHARD_SCHEMA if is_r3 else "golden-board.m2-damage-cases/v0",
                    "damage_manifest_identity": manifest_identity,
                    "profile_id": profile.profile_id,
                    "family_id": family,
                    "shard_ordinal": shard_ordinal,
                    "case_first": first,
                    "case_rows": selected,
                    "summary": shard_summary,
                }
                shard_identity = identity.identity_hex(
                    b"golden-board:manifest:v0\0",
                    (canonical_manifest.serialize_manifest(shard_value),),
                )
                shard_value["summary"] = {
                    **shard_summary,
                    "manifest_identity": shard_identity,
                }
                return canonical_manifest.serialize_manifest(shard_value)

            low, high = 1, maximum
            chosen_raw: bytes | None = None
            chosen = 0
            while low <= high:
                middle = (low + high) // 2
                try:
                    candidate_raw = render_shard(middle)
                except canonical_manifest.ManifestError:
                    high = middle - 1
                else:
                    chosen = middle
                    chosen_raw = candidate_raw
                    low = middle + 1
            if chosen_raw is None:
                _fail("case-row-too-large")
            name = f"damage-{family}-cases-{shard_ordinal:04d}.json"
            case_shards.append((name, chosen_raw))
            shard_rows.append(
                {
                    "shard_ordinal": shard_ordinal,
                    "case_first": first,
                    "case_count": chosen,
                    "manifest_sha256": sha256(chosen_raw).hexdigest(),
                }
            )
            first += chosen
            shard_ordinal += 1
        family_summary: dict[str, object] = {
            "case_count": count,
            "wrong_accept_count": sum(
                int(row["wrong_accept_count"]) for row in family_rows
            ),
            "result": "pass" if family_passes[family] else "fail",
        }
        family_value: dict[str, object] = {
            "schema": R3_FAMILY_SCHEMA if is_r3 else "golden-board.m2-damage-family/v0",
            "damage_manifest_identity": manifest_identity,
            "profile_id": profile.profile_id,
            "family_id": family,
            "guarantee_id": guarantees[family_index],
            "shard_rows": shard_rows,
            "summary": family_summary,
        }
        family_identity = identity.identity_hex(
            b"golden-board:manifest:v0\0",
            (canonical_manifest.serialize_manifest(family_value),),
        )
        family_value["summary"] = {
            **family_summary,
            "manifest_identity": family_identity,
        }
        family_manifests.append(canonical_manifest.serialize_manifest(family_value))
    return DamageRun(
        profile.profile_id, raw, manifest_identity, tuple(family_manifests),
        tuple(case_shards),
        len(rows), tuple(counts), wrong,
        # Gate 6 is the byte-exact oracle/Python/Rust comparison above.  Gate 7
        # remains a separate ownership proof and is never inferred from it.
        (
            "pass"
            if wrong == 0 and all(family_passes.values())
            else "fail"
        ),
        "not_evaluated",
        tuple(
            (case_id, *evaluator.bundle_case_preimages[case_id])
            for case_id in (
                "D2-000000",
                "D3-000000",
                "D4-000000",
                "D7-000011",
            )
        )
        if is_r3
        else (),
    )


def run_damage(
    manifestation: m2_carrier.Manifestation,
    profile: m2_codec.CandidateProfile,
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    damage_policy_raw: bytes,
    route_manifest_raw: bytes,
    alternate_recipient_package: bytes,
    rust_decoder_command: Sequence[str],
    worker_count: int,
    alternate_route_manifest_raw: bytes | None = None,
) -> DamageRun:
    """Run P7 and deterministically reap every worker on all exit paths."""

    before = set(_ACTIVE_EVALUATORS)
    try:
        return _run_damage(
            manifestation,
            profile,
            profile_policy_raw,
            profile_limits_raw,
            damage_policy_raw,
            route_manifest_raw,
            alternate_recipient_package,
            rust_decoder_command,
            worker_count,
            alternate_route_manifest_raw,
        )
    finally:
        for evaluator in tuple(_ACTIVE_EVALUATORS - before):
            assert isinstance(evaluator, _DamageEvaluator)
            evaluator._abort()


def run_damage_python(
    manifestation: m2_carrier.Manifestation,
    profile: m2_codec.CandidateProfile,
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    damage_policy_raw: bytes,
    route_manifest_raw: bytes,
    alternate_recipient_package: bytes,
    worker_count: int,
    alternate_route_manifest_raw: bytes | None = None,
) -> DamageRun:
    """Independently render Gate 6 through only the Python oracle/decoder lane.

    This is the Gate-8 Python-producer path.  It deliberately neither starts
    nor reads the Rust decoder, so a Python/Rust disagreement remains visible
    as a receipt-column mismatch instead of suppressing one producer column.
    """

    before = set(_ACTIVE_EVALUATORS)
    try:
        return _run_damage(
            manifestation,
            profile,
            profile_policy_raw,
            profile_limits_raw,
            damage_policy_raw,
            route_manifest_raw,
            alternate_recipient_package,
            None,
            worker_count,
            alternate_route_manifest_raw,
        )
    finally:
        for evaluator in tuple(_ACTIVE_EVALUATORS - before):
            assert isinstance(evaluator, _DamageEvaluator)
            evaluator._abort()


def run_r3_d7_range_probe(
    manifestation: m2_carrier.Manifestation,
    profile: m2_codec.CandidateProfile,
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    damage_policy_raw: bytes,
    alternate_recipient_package: bytes,
    alternate_route_manifest_raw: bytes,
    rust_decoder_command: Sequence[str],
    worker_count: int,
    first_ordinal: int,
    stop_ordinal: int,
) -> tuple[tuple[str, str, int], ...]:
    """Cross-check one bounded D7 ordinal range without producing artifacts."""

    if (
        type(first_ordinal) is not int
        or type(stop_ordinal) is not int
        or not 0 <= first_ordinal < stop_ordinal <= 408
        or stop_ordinal - first_ordinal > 32
    ):
        _fail("r3-d7-probe-range")
    before = set(_ACTIVE_EVALUATORS)
    evaluator: _DamageEvaluator | None = None
    try:
        context = _Context(manifestation, profile)
        if not context.is_r3:
            _fail("r3-d7-probe-profile")
        evaluator = _DamageEvaluator(
            context,
            profile_policy_raw,
            profile_limits_raw,
            damage_policy_raw,
            alternate_recipient_package,
            rust_decoder_command,
            worker_count,
            alternate_route_manifest_raw=alternate_route_manifest_raw,
        )
        evaluator.family_case_counts["D7"] = first_ordinal
        rows: list[dict[str, object]] = []
        for ordinal in range(first_ordinal, stop_ordinal):
            spec = _r3_d7_case_spec(
                context,
                profile,
                alternate_recipient_package,
                alternate_route_manifest_raw,
                ordinal,
            )
            row = _case_row(
                "",
                "D7",
                spec.channel,
                spec.operator,
                spec.parameters,
                spec.observation,
                spec.expected,
                evaluator,
            )
            if row["case_id"] != f"D7-{ordinal:06d}":
                _fail("r3-d7-probe-order")
            rows.append(row)
        evaluator.finish(rows)
        if any(
            int(row["wrong_accept_count"]) != 0
            or not evaluator.match_by_case.get(str(row["case_id"]), False)
            for row in rows
        ):
            _fail("r3-d7-probe-result")
        result = tuple(
            (
                str(row["case_id"]),
                str(row["decoder_result_sha256"]),
                int(row["wrong_accept_count"]),
            )
            for row in rows
        )
        evaluator.close()
        return result
    finally:
        for active in tuple(_ACTIVE_EVALUATORS - before):
            assert isinstance(active, _DamageEvaluator)
            active._abort()


def run_r3_damage_preflight(
    manifestation: m2_carrier.Manifestation,
    profile: m2_codec.CandidateProfile,
    profile_policy_raw: bytes,
    profile_limits_raw: bytes,
    damage_policy_raw: bytes,
    alternate_recipient_package: bytes,
    rust_decoder_command: Sequence[str],
    worker_count: int,
) -> bytes:
    """Run five bounded cross-language cases without rendering gate-6 files."""

    before = set(_ACTIVE_EVALUATORS)
    evaluator: _DamageEvaluator | None = None
    try:
        context = _Context(manifestation, profile)
        if not context.is_r3:
            _fail("r3-preflight-profile")
        evaluator = _DamageEvaluator(
            context,
            profile_policy_raw,
            profile_limits_raw,
            damage_policy_raw,
            alternate_recipient_package,
            rust_decoder_command,
            worker_count,
            capture_mismatches=True,
        )
        rows: list[dict[str, object]] = []
        square = max(32, context.interior // 32)
        top, left = _d2_placements(context, square)[0]
        rows.append(
            _matrix_case(
                context,
                "D2",
                0,
                "erase-square-in-protected-interior",
                tuple(
                    (top + row, left + column)
                    for row in range(square)
                    for column in range(square)
                ),
                True,
                {
                    "side": ("u64", square),
                    "top_left": ("coordinate-list", [[top, left]]),
                },
                evaluator=evaluator,
            )
        )
        rows.append(
            _matrix_case(
                context,
                "D3",
                0,
                "fixed-weight-unknown-bit-substitution",
                _d3_coordinates(context, 0),
                False,
                {
                    "coordinates": (
                        "coordinate-list",
                        [list(item) for item in _d3_coordinates(context, 0)],
                    ),
                    "seed": ("u64", 5_134_751_402_299_490_304),
                    "stratum_id": ("u64", 0),
                },
                evaluator=evaluator,
            )
        )
        all_ids = tuple(sorted(context.clean_encoded))
        rows.append(
            _case_row(
                "",
                "D4",
                "OBS_UNITS",
                "omit-one-physical-unit-observation",
                {"omitted_unit_id": ("u64", 1)},
                _obs_units(all_ids[1:], context.clean_encoded),
                context.evaluate(omitted={1}),
                evaluator,
            )
        )
        matrix = bytearray(context.clean)
        sector_cells = context.width * (context.side - context.width)
        for offset in range(sector_cells):
            row, column = bootstrap.sector_cell(
                context.side, context.width, 0, offset
            )
            matrix[row * context.side + column] = 2
        for bit_offset in range(context.unit_bits):
            physical = context.physical_cell(1, bit_offset)
            local_row, local_column = divmod(physical, context.interior)
            matrix[
                (local_row + context.width) * context.side
                + local_column
                + context.width
            ] = 2
        rows.append(
            _case_row(
                "",
                "D6",
                "OBS_MATRIX",
                "erase-shell-sector-union-one-physical-unit-cell-set",
                {
                    "sector_id": ("u64", 0),
                    "unit_id": ("u64", 1),
                },
                _obs_matrix(context.side, matrix),
                context.evaluate(
                    erasures={1: tuple(range(context.unit_bits))}
                ),
                evaluator,
            )
        )
        block = bootstrap.decode_common_block(
            context.clean_common[1], profile.profile_version
        )
        changed = replace(
            block,
            payload=bytes((block.payload[0] ^ 1,)) + block.payload[1:],
        )
        replacement = _reencode_unit(bootstrap.encode_common_block(changed))
        encoded = dict(context.clean_encoded)
        encoded[1] = replacement
        evaluator.family_case_counts["D7"] = 16
        rows.append(
            _case_row(
                "",
                "D7",
                "OBS_UNITS",
                "valid-copy-conflicts",
                {
                    "section_id": ("u64", 1),
                    "target_unit_id": ("u64", 1),
                },
                _obs_units(all_ids, encoded),
                context.evaluate({1: replacement}),
                evaluator,
            )
        )
        evaluator.finish(rows)
        expected_ids = (
            "D2-000000",
            "D3-000000",
            "D4-000000",
            "D6-000000",
            "D7-000016",
        )
        if tuple(str(row["case_id"]) for row in rows) != expected_ids:
            _fail("r3-preflight-order")
        mismatches = tuple(
            str(row["case_id"])
            for row in rows
            if int(row["wrong_accept_count"]) != 0
            or not evaluator.match_by_case.get(str(row["case_id"]), False)
        )
        if mismatches:
            details: list[str] = []
            for case_id in mismatches:
                expected_raw, actual_raw, rust_raw = (
                    evaluator.mismatch_raw_by_case[case_id]
                )
                expected_value = canonical_manifest.validate_canonical_manifest(
                    expected_raw
                )
                actual_value = canonical_manifest.validate_canonical_manifest(
                    actual_raw
                )
                rust_value = canonical_manifest.validate_canonical_manifest(
                    rust_raw
                )
                oracle_python_keys = tuple(
                    sorted(
                        key
                        for key in set(expected_value) | set(actual_value)
                        if expected_value.get(key) != actual_value.get(key)
                    )
                )
                python_rust_keys = tuple(
                    sorted(
                        key
                        for key in set(actual_value) | set(rust_value)
                        if actual_value.get(key) != rust_value.get(key)
                    )
                )
                resource_projection = tuple(
                    ",".join(
                        str(value["resource"][name])
                        for name in (
                            "section_attempts",
                            "primitive_steps",
                            "peak_scratch_bytes",
                        )
                    )
                    for value in (
                        expected_value,
                        actual_value,
                        rust_value,
                    )
                )
                details.append(
                    "/".join(
                        (
                            case_id,
                            "python-rust-equal"
                            if actual_raw == rust_raw
                            else "python-rust-differ",
                            ",".join(oracle_python_keys),
                            ",".join(python_rust_keys),
                            "|".join(resource_projection),
                        )
                    )
                )
            _fail("r3-preflight-mismatch:" + ";".join(details))
        evaluator.close()
        return canonical_manifest.serialize_manifest(
            {
                "kind": "golden-board.m2-r3-damage-preflight",
                "profile_id": R3_PROFILE_ID,
                "case_rows": rows,
            }
        )
    finally:
        if evaluator is not None:
            evaluator._abort()
        for active in tuple(_ACTIVE_EVALUATORS - before):
            assert isinstance(active, _DamageEvaluator)
            active._abort()


__all__ = [
    "DAMAGE_SCHEMA",
    "R3_BOUNDARY_KAT_IDS",
    "R3_BOUNDARY_KAT_SHA256",
    "R3_CANDIDATE_MANIFEST_SHA256",
    "R3_DAMAGE_SCHEMA",
    "R3_FAMILY_CASE_COUNTS",
    "R3_FAMILY_IDS",
    "R3_FAMILY_SCHEMA",
    "R3_PROFILE_ID",
    "R3_SHARD_SCHEMA",
    "DamageBundleV1",
    "DamageError",
    "DamageRun",
    "RustBatchDecoder",
    "run_damage",
    "run_r3_d7_range_probe",
    "run_r3_damage_preflight",
    "validate_damage_bundle_v1",
]
