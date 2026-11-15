"""Clean binary drawing primitives and the current inert miniature. No recovery."""
from .checksum import byte_trace
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
    records = {ident: {'kind': 1, 'id': ident, 'rows': 2, 'cols': 3, 'mask': [mask]}
               for ident, mask in ((0, 0), (1, 0xd4), (2, 0x28))}
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

def draw_calibration(ordinal, p):
    """The current pattern, row-order and CRC-state examples."""
    if ordinal == 3:
        cells = [0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 1, 1, 1, 0, 1]
        _shape(p, cells, 3, 5, 8, 12, 4)
        _shape(p, [1 - bit for bit in cells], 3, 5, 36, 12, 4)
        _number(p, 3, 8, 19, 38)
        _number(p, 5, 8, 19, 48)
    elif ordinal == 4:
        for index in range(6):
            _number(p, index + 1, 4, 14 + index % 3 * 16, 14 + index // 3 * 12)
            _number(p, index + 1, 4, 10 + index * 8, 48)
    elif ordinal == 12:
        for row, state in enumerate(byte_trace(53)):
            _number(p, state, 32, 10, 16 + row * 4)
            _number(p, row, 4, 50, 16 + row * 4)
    else:
        raise ValueError("Unknown calibration panel.")


def _byte(p,value,x,y):
    _box(p,x-2,y-2,x+9,y+2)
    _number(p,value,8,x,y)


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
