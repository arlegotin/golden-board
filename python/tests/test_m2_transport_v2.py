from dataclasses import replace
import unittest

from golden_board import bootstrap, m2_codec
from golden_board.m2_transport_v2 import aggregate_replica_group


def common(value):
    envelope = bootstrap.encode_section_envelope(bootstrap.SectionEnvelope(
        400, 4, 0, 129, 1, (), bytes([value])))
    return bootstrap.fragment_section(envelope, 8, 0)[0]


def lane(block, flips=()):
    raw = bytearray(m2_codec.eh72_encode_unit(block))
    for bit in flips:
        raw[bit//8] ^= 1 << (7-bit%8)
    return m2_codec.CopyObservation(bytes(raw), ())


class RevisedPhysicalGroups(unittest.TestCase):
    def test_valid_lane_never_short_circuits_distinct_valid_raw_repetition(self):
        a, b = common(0), common(1)
        rows = (lane(a), *(lane(b, (2*i, 2*i+1)) for i in range(4)))
        result = aggregate_replica_group(rows)
        self.assertEqual(result.lane_states, (2, 1, 1, 1, 1))
        self.assertEqual(result.repetition_state, 3)
        self.assertEqual(result.repetition_block, b)
        self.assertEqual(result.distinct_candidate_count, 2)
        self.assertEqual(result.group_state, 4)
        self.assertEqual(result.chosen_block, bytes(191))

    def test_repetition_alone_recovers_and_foreign_profile_does_not(self):
        b = common(1)
        result = aggregate_replica_group(tuple(lane(b, (2*i, 2*i+1)) for i in range(5)))
        self.assertEqual(result.lane_states, (1,)*5)
        self.assertEqual((result.group_state, result.chosen_block), (3, b))
        old = bootstrap.encode_common_block(replace(bootstrap.decode_common_block(b, 8), profile_version=7))
        wrong = aggregate_replica_group((lane(old),)*5)
        self.assertEqual((wrong.group_state, wrong.distinct_candidate_count), (1, 0))
        self.assertEqual(aggregate_replica_group((None,)*5).group_state, 0)

    def test_erased_value_shape_and_factor_fail_before_recovery(self):
        raw = bytearray(lane(common(0)).encoded)
        raw[0] |= 0x80
        for observations in ((None,)*3, [None]*6, iter([None]*5),
                             (m2_codec.CopyObservation(bytes(raw), (0,)),)):
            with self.assertRaises(m2_codec.CodecError):
                aggregate_replica_group(observations)

    def test_erasure_iterators_cannot_be_consumed_into_a_false_verified_state(self):
        raw = lane(common(0)).encoded
        zero_bit = next(i for i in range(1728) if not raw[i//8] & (1 << (7-i%8)))
        erased = m2_codec.CopyObservation(raw, (zero_bit,))
        self.assertEqual(aggregate_replica_group((erased,)).lane_states, (3,))
        for malformed in (
            m2_codec.CopyObservation(raw, iter((zero_bit,))),
            m2_codec.CopyObservation(raw, (zero_bit,)*1729),
            m2_codec.CopyObservation(bytearray(raw), ()),
            m2_codec.CopyObservation(memoryview(raw), ()),
        ):
            with self.assertRaises(m2_codec.CodecError):
                aggregate_replica_group((malformed,))


if __name__ == '__main__':
    unittest.main()
