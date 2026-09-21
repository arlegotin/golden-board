"""Explicit revised required-stream admission; historical entry is unchanged."""
from hashlib import sha256

from .m2_runner import GenericRunner, RunnerError

CONTENT_BYTES = 42432
CONTENT_SHA256 = '141168a051b44f978667f7c562070300d79368ace3fee47f5d19082de7642c17'
CONTENT_ROOT_ID = 588


def m2_runner_v1(raw_content_bytes: bytes, *, label_suppressed: bool) -> GenericRunner:
    if type(raw_content_bytes) is not bytes:
        raise TypeError('runner input must be bytes')
    if (len(raw_content_bytes) != CONTENT_BYTES
            or sha256(raw_content_bytes).hexdigest() != CONTENT_SHA256):
        raise RunnerError('m2_required_v1_content_stream_identity')
    runner = GenericRunner(raw_content_bytes,label_suppressed=label_suppressed)
    if runner.projection_view.root_record_id != CONTENT_ROOT_ID:
        raise RunnerError('m2_required_v1_content_stream_identity')
    return runner
