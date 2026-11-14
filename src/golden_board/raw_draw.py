"""Clean nonlinguistic raster primitives and inert calibration. No recovery.

Useful drawings extracted from pre-clean revision3fa53ef; no legacy runtime imports.
"""
from .checksum import MASK, byte_trace, crc32c
from .document import NONE


def _bits(value, width):
    return bytes((value >> shift) & 1 for shift in range(width - 1, -1, -1))

def _write(canvas, x, y, data, cols, row_gap=1):
    rows = (len(data) + cols - 1) // cols
    if x < 0 or x + cols > 64 or y < 0 or y + (rows - 1) * row_gap >= 64:
        raise ValueError('Raw diagram exceeds panel.')
    for index, value in enumerate(data):
        canvas[(y + index // cols * row_gap) * 64 + x + index % cols] = value

def _number(canvas, value, width, x, y):
    _write(canvas, x, y, _bits(value, width), width)

def _octets(canvas, data, x=0, y=16, cols=64):
    bits = b''.join(_bits(value, 8) for value in data)
    _write(canvas, x, y, bits, cols)

def _shape(canvas, cells, rows, cols, x, y, size=3):
    for index, value in enumerate(cells):
        px, py = x + index % cols * size, y + index // cols * size
        for dy in range(size - 1):
            for dx in range(size - 1):
                if px + dx < 64 and py + dy < 64:
                    canvas[(py + dy) * 64 + px + dx] = value

def _mini_frame(canvas, cells, x, y, size=6):
    for index, value in enumerate(cells):
        bits = [0, 0, 0, 0] if value == 0 else [1, 0, 0, 1] if value == 1 else [0, 1, 1, 0]
        _shape(canvas, bits, 2, 2, x + index % 3 * size, y + index // 3 * size, max(2, size // 2))

def _field(canvas, data, y, x=13):
    if not 1 <= len(data) <= 6:
        raise ValueError('Worked field band outside its explicit width.')
    _number(canvas, len(data), 4, x-10, y)
    _octets(canvas, data, x=x, y=y, cols=len(data) * 8)
    for offset in range(0, len(data) * 8, 8):
        canvas[(y + 1) * 64 + x + offset] = 1

def _box(canvas, x0, y0, x1, y1):
    for x in range(x0, x1 + 1):
        canvas[y0 * 64 + x] = canvas[y1 * 64 + x] = 1
    for y in range(y0, y1 + 1):
        canvas[y * 64 + x0] = canvas[y * 64 + x1] = 1

def _arrow(canvas, x, y, length, vertical=False):
    for offset in range(length):
        canvas[(y + offset if vertical else y) * 64 + (x if vertical else x + offset)] = 1
    for side in (-1, 1):
        if vertical:
            canvas[(y + length - 2) * 64 + x + side] = 1
        else:
            canvas[(y + side) * 64 + x + length - 2] = 1

def miniature_model():
    """Fixed non-chess calibration example, entirely visible in the raw route.

    This is conformance validation, not replacement of missing observed pixels.
    The independently authored literal wire vector is checked against it.
    """
    records = {ident: {'kind': 1, 'id': ident, 'rows': 2, 'cols': 2, 'mask': [mask]}
               for ident, mask in ((0, 0), (1, 0x90), (2, 0x60))}
    for ident, cells, regions in ((256, [0, 1, 1, 1, 0, 1], [[10, 0], [20, 5]]),
                                  (258, [1, 1, 1, 1, 0, 0], []),
                                  (259, [1] * 6, []), (260, [2] * 6, [])):
        records[ident] = {'kind': 2, 'id': ident, 'rows': 2, 'cols': 3, 'cells': cells, 'regions': regions}
    records[257] = {'kind': 3, 'id': 257, 'initial': 256, 'data': [400], 'steps': [[[0, 1]], [[5, 0]]]}
    records[400] = {'kind': 5, 'id': 400, 'rows': 2, 'cols': 3, 'values': list(range(6))}
    for ident, display_kind, display, links in ((512, 0, 256, [516]), (514, 0, 259, [512]),
            (515, 0, 260, [512]), (516, 1, 257, [517, 518]), (517, 0, 259, [512]), (518, 0, 258, [512])):
        practice = ident == 512
        records[ident] = {'kind': 4, 'id': ident, 'display_kind': display_kind, 'display': display,
                         'shape': 2 if practice else 0, 'choices': [10, 20] if practice else [],
                         'accepted': [[10]] if practice else [], 'success': 514 if practice else NONE,
                         'failure': 515 if practice else NONE, 'passive': 516 if practice else NONE, 'links': links}
    return {'version': 1, 'entries': [512, 257], 'records': records}

def arrange_panels(panels, *, columns):
    if (not panels or not 1 <= columns <= 32 or len(panels) % columns or
            any(len(p) != 4096 for p in panels)):
        raise ValueError('Invalid raw panel arrangement.')
    width, height = columns * 64, len(panels) // columns * 64
    route = bytearray(width * height)
    for ordinal, panel in enumerate(panels):
        left, top = ordinal % columns * 64, ordinal // columns * 64
        for row in range(64):
            route[(top + row) * width + left:(top + row) * width + left + 64] = panel[row * 64:(row + 1) * 64]
    return bytes(route)

def panel(route, ordinal, *, columns=8):
    width = columns * 64
    if type(ordinal) is not int or not 0 <= ordinal < len(route) // 4096:
        raise ValueError('Unknown raw panel.')
    x, y = ordinal % columns * 64, ordinal // columns * 64
    return b''.join(route[(y + row) * width + x:(y + row) * width + x + 64] for row in range(64))

def _read_number(p, x, y, width):
    bits = p[y * 64 + x:y * 64 + x + width]
    if any(value > 1 for value in bits):
        raise ValueError('Incomplete raw parameter.')
    value = 0
    for bit in bits:
        value = value * 2 + bit
    return value

def _coded_cell(canvas,value,x,y):
    if value not in (0,1):raise ValueError('Boolean calibration requires0or1.')
    patterns=([1,1,1,1,0,1,1,1,1],[1]*9)
    _write(canvas,x,y,bytes(patterns[value]),3)


def draw_calibration(ordinal,p,blocks):
    if ordinal in (0, 1):
        for value in range(16):
            y = 10 + value * 3
            _write(p, 2, y, b'\x01' * value + b'\x00' * (16 - value), 16)
            _number(p, value, 4 if ordinal == 0 else 8, 28, y)
    elif ordinal == 2:
        for bit in range(8):
            _number(p, 1 << bit, 8, 12, 12 + bit * 6)
            _number(p, bit + 1, 4, 32, 12 + bit * 6)
            _write(p, 44, 12 + bit * 6, b'\x01' * (bit + 1), bit + 1)
    elif ordinal == 3:
        cells = [0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 1, 1, 1, 0, 1]
        _shape(p, cells, 3, 5, 8, 12, 4)
        _shape(p, [1 - bit for bit in cells], 3, 5, 36, 12, 4)
        _number(p, 3, 8, 8, 38)
        _number(p, 5, 8, 8, 48)
    elif ordinal == 4:
        for index in range(6):
            _number(p, index + 1, 4, 14 + index % 3 * 16, 14 + index // 3 * 12)
            _number(p, index + 1, 4, 10 + index * 8, 48)
    elif ordinal == 6:
        for row, value in enumerate((1, 2, 17, 256, 258, 513)):
            _number(p, value, 16, 9, 14 + row * 7)
            _number(p, value >> 8, 8, 33, 14 + row * 7)
            _number(p, value & 255, 8, 47, 14 + row * 7)
    elif ordinal == 8:
        for value in range(4):
            a, b = (value >> 1, value & 1)
            for offset, result in ((0, a ^ b), (32, int(a == b))):
                for x, bit in zip((9, 13, 20), (a, b, result)):
                    _shape(p, [bit], 1, 1, x + offset, 16 + value * 10, 4)
    elif ordinal == 9:
        for row, value in enumerate((53, 2147483649, 2197175160)):
            _number(p, value, 32, 9, 12 + row * 20)
            _number(p, value >> 1, 32, 9, 14 + row * 20)
            _number(p, value & 1, 1, 53, 12 + row * 20)
    elif ordinal == 12:
        _number(p, MASK, 32, 16, 14)
        _number(p, 517762881, 32, 16, 32)
        _number(p, 4812730177, 33, 16, 50)
    elif ordinal == 13:
        _number(p, 4294967295, 32, 10, 14)
        _number(p, 53, 8, 34, 30)
        _number(p, 4294967295 ^ 53, 32, 10, 46)
    elif ordinal == 14:
        for row, state in enumerate(byte_trace(53)):
            _number(p, state, 32, 10, 16 + row * 4)
            _number(p, row, 4, 50, 16 + row * 4)
    elif ordinal == 15:
        _number(p, 4294967295, 32, 10, 12)
        _number(p, byte_trace(53)[-1], 32, 10, 26)
        _number(p, crc32c(b'5'), 32, 10, 40)
        for index, value in enumerate(crc32c(b'5').to_bytes(4, 'big')):
            _number(p, value, 8, 10 + index * 12, 54)
    elif ordinal == 16:
        for row, width in enumerate((2, 1, 2, 2, 2, 2, 241, 4)):
            _number(p, width, 16, 4, 10 + row * 6)
            _write(p, 32, 10 + row * 6, b'\x01' * (row + 1), row + 1)
        for top, block in zip((9, 33), blocks):
            _box(p, 42, top, 62, top + 18)
            _number(p, 0, 8, 44, top + 2)
            _number(p, 11, 8, 52, top + 2)
            _octets(p, block[:11], x=44, y=top + 4, cols=16)
            _number(p, 252, 8, 44, top + 11)
            _number(p, 4, 8, 52, top + 11)
            _octets(p, block[-4:], x=44, y=top + 13, cols=16)
            _number(p, 256, 16, 44, top + 16)
        _number(p, 327, 16, 43, 56)
    elif ordinal == 24:
        for row, value in enumerate(('d639', '0002', '000f', '0200', '0101')):
            _field(p, bytes.fromhex(value), 10 + row * 5)
        for row, value in enumerate(('01', '0001', '00000003', '02', '02', '90')):
            _field(p, bytes.fromhex(value), 37 + row * 4)
        for row, bits in enumerate(([0, 0, 0, 0], [1, 0, 0, 1], [0, 1, 1, 0])):
            _shape(p, bits, 2, 2, 53, 12 + row * 18, 4)
    elif ordinal == 25:
        fields = ('02', '0100', '00000012', '02', '03', '000101010001', '0002', '000a0000', '00140005')
        for row, value in enumerate(fields):
            _field(p, bytes.fromhex(value), 10 + row * 4)
        _mini_frame(p, [0, 1, 1, 1, 0, 1], 3, 48)
        for row in range(2):
            for col in range(3):
                value = row * 3 + col
                x, y = (29 + col * 11, 46 + row * 8)
                _box(p,x,y,x+9,y+6)
                _write(p, x + 2, y + 2, b'\x01' * value + b'\x00' * (6 - value), 6)
                _number(p, value, 3, x + 3, y + 4)
    elif ordinal == 26:
        fields = ('03', '0101', '00000013', '0100', '01', '0190', '00000002', '0001', '0000', '01', '0001', '0005', '00')
        for row, value in enumerate(fields):
            _field(p, bytes.fromhex(value), 10 + row * 4)
        for row, cells in enumerate(([0, 1, 1, 1, 0, 1], [1, 1, 1, 1, 0, 1], [1, 1, 1, 1, 0, 0])):
            _mini_frame(p, cells, 49, 10 + row * 20, size=4)
    elif ordinal == 27:
        fields = ('04', '0200', '0000001a', '00', '0100', '02', '0002', '000a0014', '0001', '0001', '000a', '0202', '0203', '0204', '0001', '0204')
        for row, value in enumerate(fields):
            _field(p, bytes.fromhex(value), 10 + row * 3, x=21)
    elif ordinal in (28, 29):
        _octets(p, blocks[ordinal - 28])
        if ordinal == 29:
            for y, value in ((8, '05'), (10, '0190'), (12, '00000011'), (50, '00000002'), (53, '03'), (56, '000000010002'), (59, '000300040005')):
                _field(p, bytes.fromhex(value), y)
    elif ordinal == 30:
        for row, values in enumerate(((1, 10, 512, 512), (3, 0, 512, 512), (2, 0, 512, 515))):
            _write(p, 3, 12 + row * 12, b''.join((_bits(value, 16) for value in values)), 32)
        _mini_frame(p, [2] * 6, 43, 42)
    elif ordinal == 31:
        for row, values in enumerate(((20, 515), (10, 514), (516, 518))):
            _write(p, 3, 12 + row * 10, b''.join((_bits(value, 16) for value in values)), 32)
        _mini_frame(p, [1] * 6, 43, 12)
        _mini_frame(p, [1, 1, 1, 1, 0, 0], 43, 42)
    else:raise ValueError("No retained calibration drawing.")


def _byte(p,value,x,y):
    _box(p,x-2,y-2,x+9,y+2)
    _number(p,value,8,x,y)

def _calibration(p):
    for top,value in ((6,53),(35,11)):
        _box(p,2,top,61,top+26)
        _byte(p,value,28,top+4)
        _arrow(p,31,top+7,5,vertical=True)
        for c,bit in enumerate(_bits(value,8)):
            x,y=8+6*c,top+13
            _box(p,x,y,x+5,y+5)
            _write(p,x+2,y+2,bytes([bit])*4,2)
        _byte(p,1,20,top+22);_byte(p,8,36,top+22)

def _matrices(p):
    for left,top,rows,cols,values in (
            (0,7,2,8,(53,11)),(33,7,3,5,(17,10,31)),
            (0,35,1,7,(89,)),(33,35,2,8,(53,0))):
        _box(p,left,top,left+30,top+25)
        _byte(p,rows,left+4,top+5);_byte(p,cols,left+19,top+5)
        # Bounds include every white tile and the completely zero second row.
        width,height=cols*3-1,rows*3-1
        bx,by=left+(31-(width+4))//2,top+11
        x,y=bx+2,by+2
        pixels=[bit for value in values for bit in _bits(value,cols)]
        _shape(p,pixels,rows,cols,x,y,size=3)
        _box(p,bx,by,bx+width+3,by+height+3)
        for c in range(cols):p[(top+9)*64+x+3*c]=1

def _references(p):
    for top,ident,refs in ((8,6,()),(21,7,()),(34,8,(6,7)),(47,9,(8,))):
        _box(p,1,top,62,top+12)
        _byte(p,ident,4,top+2);_byte(p,len(refs),18,top+2)
        _box(p,28,top,60,top+5)
        for j,ref in enumerate(refs):_byte(p,ref,32+12*j,top+2)
        _byte(p,len(refs),4,top+9)
        _box(p,16,top+7,27,top+11)
        _write(p,18,top+9,b'\1'*len(refs)+b'\0'*(8-len(refs)),8)
