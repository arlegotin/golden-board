"""Remove inert development metadata and unreferenced local glyph definitions."""
from .document import decode_document, encode_document

def clean_document(body, *, advanced=False, fingerprint=None):
    document = decode_document(body)
    records = document['records']
    removed_tables = []
    if advanced:
        table, trace = records[841], records[846]
        if (not isinstance(fingerprint,bytes) or len(fingerprint)!=32
                or table != {'kind':5, 'id':841, 'rows':1, 'cols':32,
                     'values':list(fingerprint)}
                or trace['kind'] != 3 or trace['data'] != [840,841,842,843,844]
                or [r['id'] for r in records.values()
                    if r['kind'] == 3 and 841 in r['data']] != [846]):
            raise ValueError('Extra fingerprint location/content changed; inspect before removal.')
        del records[841]
        trace['data'].remove(841)
        removed_tables.append(841)
    used = set()
    for record in records.values():
        if record['kind'] == 2:
            used.update(record['cells'])
        elif record['kind'] == 3:
            used.update(glyph for step in record['steps'] for _, glyph in step)
    unused = [ident for ident, record in records.items()
              if record['kind'] == 1 and ident not in used]
    for ident in unused:
        del records[ident]
    result = encode_document(document['entries'], list(records.values()))
    return result, {'unused_glyph_ids':unused, 'removed_sha_tables':removed_tables,
                    'saved_bytes':len(body)-len(result)}
