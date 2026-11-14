"""Identity-checked conversion and original historical qualification sources."""
import hashlib
import json
from .document import decode_document

PINNED = {
    'foundation': 'a8c4da928c2ff570d69897c148a7c9c95c7537dcd4fedee222f714e58ecf8bcd',
    'anthology': 'c677a9e407854f2388831573ad2fd2296f2523a160f509e938dfbf409a3ba737',
}
HISTORICAL_CODECS = ('src/golden_board/document.py', 'viewer/player.mjs')


def current_document(data, identity):
    if identity not in PINNED or hashlib.sha256(data).hexdigest() != PINNED[identity]:
        raise ValueError('Qualified historical input identity changed.')
    if data[:3] != b'\xd6\x39\x01':
        raise ValueError('Qualified historical input header changed.')
    converted = data[:2] + data[3:]
    decode_document(converted)
    return converted


def presentation_source(root, relative):
    """Resolve immutable historical receipt keys, never substitute current code."""
    manifest = json.loads((root/'inputs/qualified/manifest.json').read_bytes())
    row = manifest['files'].get(relative)
    if row is None:
        return root/relative
    path = root/'inputs/qualified'/row['path']
    if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
        raise ValueError('Frozen presentation source changed: ' + relative)
    return path
