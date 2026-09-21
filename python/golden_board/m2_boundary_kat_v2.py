"""Fresh bounded fixtures, separate from observation-only decoder inputs.

The explicit source-owner inputs are the three pinned policy documents accepted
by ObservationDecoderV2. Saved receipts and corpus expectations are not inputs.
"""
from . import bootstrap, canonical_manifest, m2_codec, m2_damage, m2_decoder
from .m2_decoder_v2 import ObservationDecoderV2

KAT_IDS = (
    "rep2-correction-boundary", "rep5-correction-boundary",
    "complete-section-conflict", "section-attempt-ceiling-plus-one",
)


def _envelope(section_id, payload):
    return bootstrap.encode_section_envelope(bootstrap.SectionEnvelope(
        section_id, 6, 0, 129, 1, (), payload))


def _repetition(decoder, factor):
    counts = ((1, 0), (1, 1)) if factor == 2 else ((2, 1), (2, 2))
    if tuple(m2_codec.repetition_symbol_counts(factor, *row) for row in counts) != (
            (True, 0), (False, 0)):
        return False
    common = bootstrap.fragment_section(_envelope(4000 + factor, b"boundary"), 8, 0)[0]
    encoded = m2_codec.eh72_encode_unit(common)
    profile = decoder.profile_by_version[8]
    good = decoder._aggregate_v7_group(profile, (
        m2_decoder._ObservedUnit(1, encoded, ()),) + (None,) * (factor - 1))
    masks = bytes(0xAA if index % 2 == 0 else 0x55 for index in range(len(encoded)))
    bad = decoder._aggregate_v7_group(profile, (
        m2_decoder._ObservedUnit(10, bytes(a ^ b for a, b in zip(encoded, masks)), ()),
        m2_decoder._ObservedUnit(11, bytes(a ^ b ^ 0xFF for a, b in zip(encoded, masks)), ()),
    ) + (None,) * (factor - 2))
    return (good.group_state in (2, 3) and good.chosen_block == common
            and bad.group_state not in (2, 3) and bad.chosen_block == bytes(191)
            and decoder._meter.usage.primitive_steps > 0)


def _conflict(decoder):
    envelopes = tuple(_envelope(4003, value) for value in (b"first", b"other"))
    # Each hierarchical profile owns semantic copy zero. Distinct admitted
    # profiles preserve two complete candidates without inventing a copy ID.
    lanes = {100 + copy: m2_codec.eh72_encode_unit(
        bootstrap.fragment_section(raw, 8 - copy, 0)[0]) for copy, raw in enumerate(envelopes)}
    for order in ((100, 101), (101, 100)):
        result = decoder.decode(m2_decoder.OBS_UNITS, m2_damage._obs_units(order, lanes))
        if (result.artifact_state != "ambiguous" or result.profile_id is not None
                or result.inventory_available or result.m2_required_stream is not None
                or result.m2_all_stream is not None or result.accepted_hypotheses
                or result.resource.section_attempts != 2
                or result.section_results != (m2_decoder.SectionResult(1, "incomplete", None),
                                              m2_decoder.SectionResult(4003, "ambiguous", None))):
            return False
    return True


def _attempt_ceiling(decoder):
    candidates = sorted({_envelope(4004, n.to_bytes(4, "big")) for n in range(4097)})
    if len(candidates) != 4097:
        return False
    meter = decoder._meter
    meter.invoke(53, 7)
    compared = 0
    for ordinal, raw in enumerate(candidates):
        if not bootstrap.section_envelope_attempt_eligible(raw):
            return False
        try:
            meter.section(raw)
        except m2_decoder.DecoderError as error:
            if error.reason != "resource-limit" or ordinal != 4096:
                return False
            break
        # Actual stored-check comparison, after the production meter admits it.
        if bootstrap.decode_section_envelope(raw).section_id != 4004:
            return False
        compared += 1
        before = (meter.usage, meter.adapter_rows)
        meter.section(raw)
        if before != (meter.usage, meter.adapter_rows):
            return False
    else:
        return False
    closed = decoder._closed("resource-limit")
    checks = next((row for row in meter.adapter_rows if row[0] == "section-check"), None)
    return (compared == 4096 and closed.resource.section_attempts == 4096
            and closed.resource.primitive_steps == 53 and closed.resource.peak_scratch_bytes >= 7
            and checks == ("section-check", 4096, sum(map(len, candidates[:4096])), len(candidates[0]))
            and closed.artifact_state == "resource-limit" and closed.profile_id is None
            and not closed.inventory_available and not closed.section_results
            and not closed.fragment_diagnostics and not closed.route_profile_ids
            and not closed.accepted_hypotheses and closed.m2_required_stream is None
            and closed.m2_all_stream is None)


def boundary_kat_result_v2(ordinal, profile_policy_raw, profile_limits_raw, damage_policy_raw):
    if type(ordinal) is not int or not 0 <= ordinal < len(KAT_IDS):
        raise ValueError("boundary-kat-ordinal")
    decoder = ObservationDecoderV2(profile_policy_raw, profile_limits_raw, damage_policy_raw)
    try:
        passed = (_repetition(decoder, (2, 5)[ordinal]) if ordinal < 2 else
                  _conflict(decoder) if ordinal == 2 else _attempt_ceiling(decoder))
    except (ValueError, m2_decoder.DecoderError):
        passed = False
    return canonical_manifest.serialize_manifest(dict(
        schema="golden-board.m2-boundary-kat-result/v2", kat_id=KAT_IDS[ordinal],
        result="pass" if passed else "fail"))


def boundary_kat_results_v2(profile_policy_raw, profile_limits_raw, damage_policy_raw):
    return tuple(boundary_kat_result_v2(i, profile_policy_raw, profile_limits_raw,
                                      damage_policy_raw) for i in range(len(KAT_IDS)))


def _main():
    """Separate bounded export; this is never an observation IPC channel."""
    import argparse
    from pathlib import Path
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec_directory", type=Path)
    args = parser.parse_args()
    owners = []
    for name in ("profile-policy-v2.toml", "profile-limits-v2.toml", "damage-policy-v2.toml"):
        with args.spec_directory.joinpath(name).open("rb") as stream:
            owners.append(stream.read(65537))
    for raw in boundary_kat_results_v2(*owners):
        sys.stdout.buffer.write(raw)


if __name__ == "__main__":
    _main()
