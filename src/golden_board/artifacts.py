"""Verify the published artifact views; this is a developer aid, not blind discovery."""
import binascii
import hashlib
import json
from pathlib import Path
import struct
import zlib

from .clean_carrier import decode_serial


def sha(data):
    return hashlib.sha256(data).hexdigest()


def png_packed(data: bytes) -> bytes:
    """Read the retained 2048-square, one-bit, filter-zero PNG exactly.

    This deliberately supports the project's renderer, not arbitrary PNG images.
    PNG white bits are inverted to the message's black=1 packed convention.
    """
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Invalid canonical PNG signature.')
    cursor, chunks = 8, []
    while cursor < len(data):
        if cursor + 12 > len(data):
            raise ValueError('Truncated PNG chunk.')
        length = int.from_bytes(data[cursor:cursor+4], 'big')
        end = cursor + 12 + length
        if end > len(data):
            raise ValueError('Truncated PNG body.')
        kind = data[cursor+4:cursor+8]
        body = data[cursor+8:end-4]
        check = int.from_bytes(data[end-4:end], 'big')
        if binascii.crc32(kind + body) & 0xffffffff != check:
            raise ValueError('PNG chunk CRC mismatch.')
        chunks.append((kind, body))
        cursor = end
    if [kind for kind, _ in chunks] != [b'IHDR', b'IDAT', b'IEND']:
        raise ValueError('Unexpected canonical PNG chunks.')
    if chunks[0][1] != struct.pack('>IIBBBBB', 2048, 2048, 1, 0, 0, 0, 0) or chunks[2][1]:
        raise ValueError('Unexpected canonical PNG geometry/format.')
    expected = 2048 * 257
    decoder = zlib.decompressobj()
    try:
        rows = decoder.decompress(chunks[1][1], expected + 1)
    except zlib.error as error:
        raise ValueError('Invalid PNG compressed data.') from error
    if len(rows) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError('PNG scanline length or compressed boundary mismatch.')
    if any(rows[i*257] != 0 for i in range(2048)):
        raise ValueError('Unexpected PNG scanline filter.')
    return bytes(value ^ 255 for i in range(2048) for value in rows[i*257+1:(i+1)*257])


def verify_artifacts(root: Path, transforms: bool = False) -> dict:
    """Check frozen hashes, every symbol/pixel, and the complete checked payload."""
    directory = Path(root) / 'artifacts'
    manifest = json.loads((directory/'manifest.json').read_bytes())
    forms = {}
    for suffix in ('bin', 'txt', 'png'):
        name = 'GOLDEN-BOARD.' + suffix
        identity = manifest['forms'][suffix]
        data = (directory/name).read_bytes()
        if len(data) != identity['bytes'] or sha(data) != identity['sha256']:
            raise ValueError('Frozen artifact identity mismatch: ' + name)
        forms[suffix] = data
    text = forms['txt']
    if len(text) != 4194305 or text[-1:] != b'\n' or set(text[:-1]) != {48, 49}:
        raise ValueError('Canonical TXT requires exactly 2^22 symbols and final LF.')
    # Independent literal grouping, separate from the carrier's pack_bits helper.
    packed = bytes(int(text[i:i+8], 2) for i in range(0, len(text)-1, 8))
    if packed != forms['bin'] or png_packed(forms['png']) != packed:
        raise ValueError('PNG/TXT/BIN cells disagree.')
    decoded = decode_serial(text)
    documents = {str(i): {'bytes': len(body), 'sha256': sha(body)}
                 for i, body in decoded['documents'].items()}
    if documents != manifest['documents']:
        raise ValueError('Recovered document identities differ from the reference baseline.')
    count = 1
    if transforms:
        from .clean_carrier import decode_symbols, transform, unpack_bits
        symbols = unpack_bits(packed)
        count = 0
        for turn in range(4):
            for mirror in (False, True):
                for inverse in (False, True):
                    observed = transform(symbols, turn, mirror, inverse)
                    if decode_symbols(observed)['documents'] != decoded['documents']:
                        raise ValueError('Clean transformed content mismatch.')
                    count += 1
    return {'exact': True, 'cells': 4194304, 'side': 2048,
            'forms': {suffix: {'bytes': len(data), 'sha256': sha(data)} for suffix, data in forms.items()},
            'documents': documents, 'clean_presentations_checked': count,
            'scope': 'Frozen artifact identity and native conformance; no new recipient trial.'}
