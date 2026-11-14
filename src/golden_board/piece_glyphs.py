"""Final piece presentation; identities and rules stay fixed."""
import hashlib
from .document import decode_document, encode_document

REVISION = 'inverted-5x5-v1'

# Internal piece order is pawn, knight, bishop, rook, queen, king.
WHITE_ROWS = (
    ('00000', '00100', '00100', '00100', '00000'),
    ('00000', '00110', '00100', '01100', '00000'),
    ('00000', '00100', '00100', '01110', '00000'),
    ('00000', '01010', '01010', '01110', '00000'),
    ('00000', '01010', '00100', '01110', '00000'),
    ('00000', '00100', '01010', '01110', '00000'),
)


# Hash the twelve public 32-bit masks, including canonical zero padding.
PALETTE_SHA256 = hashlib.sha256(b''.join(
    ((int(''.join(rows), 2) ^ (side * ((1 << 25) - 1))) << 7).to_bytes(4, 'big')
    for side in range(2) for rows in WHITE_ROWS
)).hexdigest()


def apply_piece_glyphs(data: bytes) -> bytes:
    """Replace twelve validated masks; preserve all other inert document data."""
    document = decode_document(data)
    for side in range(2):
        for kind, rows in enumerate(WHITE_ROWS):
            ident = 32 + kind + side * 6
            record = document['records'].get(ident)
            if (record is None or record['kind'] != 1
                    or (record['rows'], record['cols']) != (5, 5)):
                raise ValueError(f'Expected a complete 5x5 piece glyph at {ident}.')
            value = int(''.join(rows), 2)
            if side:
                value ^= (1 << 25) - 1
            # Invert only the meaningful cells, never the seven unused low bits.
            record['mask'] = list((value << 7).to_bytes(4, 'big'))
    return encode_document(document['entries'], list(document['records'].values()))
