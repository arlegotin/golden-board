"""Explicit profile-8 admission for the unchanged physical group composition."""

from . import m2_codec


def aggregate_replica_group(observations):
    # Bound the product before materializing input. Historical public admission
    # still accepts only its own profiles; profile8 is explicit at this boundary.
    if type(observations) not in (tuple, list) or len(observations) not in (1, 2, 5):
        raise m2_codec.CodecError('replicas-type-or-count')
    for lane in observations:
        if lane is None:
            continue
        if (type(lane) is not m2_codec.CopyObservation
                or type(lane.encoded) is not bytes or len(lane.encoded) != 216
                or type(lane.erasures) is not tuple or len(lane.erasures) > 1728):
            raise m2_codec.CodecError('replica-observation')
    return m2_codec._aggregate_replica_group(8, (1, 2, 5), observations)
