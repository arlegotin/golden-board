"""Deterministic modern PNG previews of binary data; not a recipient decoder."""
import binascii
from pathlib import Path
import struct
import zlib


def _chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', binascii.crc32(kind + data) & 0xffffffff)


def write_binary_png(path: Path, width: int, height: int, black: bytes, scale=1):
    if width <= 0 or height <= 0 or len(black) != width * height or not 1 <= scale <= 8:
        raise ValueError('Invalid binary raster dimensions/scale.')
    if any(value not in (0, 1) for value in black):
        raise ValueError('A clean binary raster requires exact two-state values.')
    rows = []
    for row in range(height):
        pixels = [1 - value for value in black[row * width:(row + 1) * width] for _ in range(scale)]
        pixels.extend([1] * (-len(pixels) % 8))
        packed = bytes(sum(pixels[offset + bit] << (7 - bit) for bit in range(8))
                       for offset in range(0, len(pixels), 8))
        rows.extend([b'\0' + packed] * scale)
    header = struct.pack('>IIBBBBB', width * scale, height * scale, 1, 0, 0, 0, 0)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', header)
                     + _chunk(b'IDAT', zlib.compress(b''.join(rows), 9)) + _chunk(b'IEND', b''))


def write_frame_png(path: Path, packet: dict, cell=32):
    frame, glyphs = packet['frame'], packet['glyphs']
    width, height = frame['cols'] * cell, frame['rows'] * cell
    pixels = bytearray(width * height)
    selected = {index for ident, index in frame['regions'] if ident in packet['selection']}
    for index, token in enumerate(frame['cells']):
        left, top = index % frame['cols'] * cell, index // frame['cols'] * cell
        thick = 3 if index in selected else 1
        glyph = glyphs[str(token)] if str(token) in glyphs else glyphs[token]
        for dy in range(cell):
            for dx in range(cell):
                value = int(dx < thick or dy < thick or dx >= cell - thick or dy >= cell - thick)
                if 4 <= dx < cell - 4 and 4 <= dy < cell - 4:
                    gx = (dx - 4) * glyph['cols'] // (cell - 8)
                    gy = (dy - 4) * glyph['rows'] // (cell - 8)
                    bit = gy * glyph['cols'] + gx
                    value = int(bool(glyph['mask'][bit // 8] & (128 >> (bit % 8))))
                pixels[(top + dy) * width + left + dx] = value
    write_binary_png(path, width, height, bytes(pixels))
