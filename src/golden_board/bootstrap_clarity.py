"""Final bootstrap authoring.

All message-specific examples use the existing inert grammar. Field bounds include every white zero cell, and
all worked quantities come from the carried inert grammar.
"""
from functools import lru_cache

from . import direct_bootstrap as carrier, raw_draw as d
from .checksum import byte_trace, crc32c
from .document import Reader, decode_document, encode_document

LAYOUT_REVISION = 'bootstrap-field-boundaries-1'
GROUPS = ((1, 2), (5, 6), (11, 12, 13), (19, 20, 21),
          (22, 23, 24), (25, 26, 27, 28), (29, 30, 31))
LOCAL = {ordinal: i for group in GROUPS for i, ordinal in enumerate(group, 1)}
BYTE_EXAMPLES = (0x0001, 0x0100, 0x0180, 0x8001, 0x1234, 0x3412, 0x00a5, 0xa500)


@lru_cache(maxsize=1)
def miniature():
    model = d.miniature_model()
    return encode_document(model['entries'], list(model['records'].values()))


@lru_cache(maxsize=1)
def _model():
    return decode_document(miniature())


def example():
    from .clean_carrier import encode_section, inventory_for
    body = miniature()
    section = encode_section(1, 1, body)
    inventory = inventory_for({1: body})
    return section, encode_section(0, 0, inventory), inventory


def record_fields(ident):
    """Actual encoded record split at the worked example's visible field bands."""
    item = _model()['records'][ident]
    kind = item['kind']
    if kind == 1:
        widths = [1, 1, len(item['mask'])]
    elif kind == 2:
        widths = [1, 1, len(item['cells']), 2] + [4]*len(item['regions'])
    elif kind == 3:
        widths = [2, 1, 2*len(item['data']), 4]
        for step in item['steps']:
            widths += [2] + [w for _ in step for w in (2, 1)]
    elif kind == 4:
        widths = [1, 2, 1, 2]
        if item['choices']:
            widths += [2*len(item['choices'])]
        widths += [2]
        for response in item['accepted']:
            widths += [2, 2*len(response)]
        widths += [2, 2, 2, 2]
        if item['links']:
            widths += [2*len(item['links'])]
    else:
        widths = [4, 1] + [min(6, 2*len(item['values'])-offset)
                            for offset in range(0, 2*len(item['values']), 6)]
    reader = Reader(miniature())
    reader.take(2)
    roots, count = reader.uint(2), reader.uint(2)
    reader.take(2*roots)
    for _ in range(count):
        tag, rid, length = reader.take(1), reader.take(2), reader.take(4)
        payload = reader.take(int.from_bytes(length, 'big'))
        if int.from_bytes(rid, 'big') == ident:
            values = Reader(payload)
            bands = [values.take(width) for width in widths]
            values.end()
            return [tag, rid, length, *bands]
    raise ValueError('Missing miniature record.')


def glyph_bits(ident):
    glyph = _model()['records'][ident]
    rows, cols = glyph['rows'], glyph['cols']
    bits = bytes((glyph['mask'][i//8] >> (7-i%8)) & 1 for i in range(rows*cols))
    return rows, cols, bits


def frame_raster(cells):
    """Six tile IDs expanded from carried rectangular glyphs, with one-cell gaps."""
    if len(cells) != 6:
        raise ValueError('Miniature frame needs six cells.')
    rows, cols, _ = glyph_bits(cells[0])
    width, height = 3*(cols+1)-1, 2*(rows+1)-1
    pixels = bytearray(width*height)
    for index, ident in enumerate(cells):
        gr, gc, bits = glyph_bits(ident)
        if (gr, gc) != (rows, cols):
            raise ValueError('Miniature glyph dimensions disagree.')
        for y in range(rows):
            start = (index//3*(rows+1)+y)*width+index%3*(cols+1)
            pixels[start:start+cols] = bits[y*cols:(y+1)*cols]
    return width, height, bytes(pixels)


def _scaled(p, pixels, width, height, x, y, scale=1):
    if x < 0 or y < 0 or x+width*scale > 64 or y+height*scale > 63:
        raise ValueError('Miniature picture exceeds panel.')
    for row in range(height):
        band = bytes(v for v in pixels[row*width:(row+1)*width] for _ in range(scale))
        for dy in range(scale):
            d._write(p, x, y+row*scale+dy, band, width*scale)


def draw_frame(p, cells, x, y, scale=1):
    width, height, pixels = frame_raster(cells)
    _scaled(p, pixels, width, height, x, y, scale)


def _glyph(p, ident, x, y, scale=2):
    rows, cols, bits = glyph_bits(ident)
    _scaled(p, bits, cols, rows, x, y, scale)
    d._box(p, x-2, y-2, x+cols*scale+1, y+rows*scale+1)


def _fields(p, fields, start=8, gap=4, x=13):
    for index, value in enumerate(fields):
        d._field(p, value, start+gap*index, x)


def _header(p, ordinal):
    p[:3] = b'\1'*3
    p[64:66] = b'\1'*2
    d._write(p, 4, 0, b'\1'*ordinal, ordinal)
    d._number(p, ordinal, 8, 56, 0)
    if local := LOCAL.get(ordinal):
        d._write(p, 4, 2, b'\1'*local, local)
        d._number(p, local, 8, 56, 2)
    p[63*64:] = b'\1'*64


def _bounded(p, value, width, x, y):
    """Use the same two-cell inset as the existing bounded byte examples."""
    if (not 1 <= width <= 48 or not 0 <= value < 1 << width or
            x < 2 or x+width+1 >= 64 or y < 6 or y+2 >= 63):
        raise ValueError('Bounded field exceeds its bits or panel.')
    d._box(p,x-2,y-2,x+width+1,y+2)
    d._number(p,value,width,x,y)

def _word(p, value, y):
    """Four eight-bit bands; the all-ones operand exposes every band boundary."""
    d._box(p,8,y-2,55,y+2)
    for x, byte in zip((10,22,34,46),value.to_bytes(4,'big')):
        d._number(p,byte,8,x,y)

def _calculation(p, *, final):
    # The same operand grouping and result arrow in both XOR examples.
    d._box(p,5,5,58,25)
    _word(p,0xffffffff,10)
    if final:
        _word(p,byte_trace(53)[-1],20)
        result = crc32c(b'5')
    else:
        _bounded(p,53,8,46,20)
        result = 0xffffffff ^ 53
    d._arrow(p,31,27,5,vertical=True)
    _word(p,result,36)
    if final:
        d._arrow(p,31,41,8,vertical=True)
        for x, byte in zip((10,22,34,46),result.to_bytes(4,'big')):
            _bounded(p,byte,8,x,54)


def _byte_expansion(p):
    for top, value in ((6, 53), (35, 11)):
        d._box(p, 2, top, 61, top+26)
        d._byte(p, value, 28, top+4)
        d._arrow(p, 31, top+8, 5, vertical=True)
        for col, bit in enumerate(d._bits(value, 8)):
            x, y = 8+6*col, top+14
            d._box(p, x, y, x+4, y+4)
            d._number(p, bit, 1, x+2, y+2)
        d._byte(p, 1, 20, top+22)
        d._byte(p, 8, 36, top+22)


def _references(p):
    for top, ident, refs in ((7,6,()), (21,7,()), (35,8,(6,)), (49,9,(7,8))):
        d._byte(p, ident, 5, top+4)
        d._byte(p, len(refs), 19, top+4)
        d._box(p, 32, top, 60, top+8)
        for x, ref in zip((36,49), refs):
            d._byte(p, ref, x, top+4)


def _scope(p, section):
    _fields(p, [section[:2], section[2:6], section[-4:]], start=8, gap=7, x=21)
    # Identical column roles in both rows: start, length, exclusive end.
    for y, values in ((33, (0,len(section)-4,len(section)-4)),
                      (56, (len(section)-4,4,len(section)))):
        d._write(p, 8, y, b''.join(d._bits(v,16) for v in values), 48)
        d._box(p,6,y-2,57,y+2)
    d._arrow(p, 31, 37, 5, vertical=True)
    _bounded(p,crc32c(section[:-4]),32,16,45)


def _inventory(p, payload):
    # Count, item ID/length/check, root count, and the bounded list of two roots.
    windows = ((0,2), (2,4), (4,8), (8,12), (12,14), (14,16), (16,18))
    for y, (a,b) in zip((8,18,24,30,40,48,54), windows):
        d._field(p, payload[a:b], y, x=21)
    d._box(p, 8, 44, 55, 59)


def _glyph_record(p):
    data = miniature()
    _fields(p, [data[:2],data[2:4],data[4:6],data[6:8],data[8:10]], start=6, gap=3)
    for ident, top in ((0,24),(1,45)):
        _fields(p, record_fields(ident), start=top, gap=3)
        _glyph(p, ident, 52, top+6, scale=2)


def _frame_record(p):
    _fields(p, record_fields(256), start=8, gap=4)
    d._box(p, 2, 46, 27, 59)
    draw_frame(p, _model()['records'][256]['cells'], 4, 48, scale=2)
    for index in range(6):
        x, y = 33+index%3*10, 46+index//3*9
        d._box(p, x, y, x+8, y+4)
        d._number(p, index, 3, x+3, y+2)


def _trace(p):
    _fields(p, record_fields(257), start=8, gap=4)
    trace = _model()['records'][257]
    cells = list(_model()['records'][trace['initial']]['cells'])
    states = [cells[:]]
    for step in trace['steps']:
        for index, glyph in step:
            cells[index] = glyph
        states.append(cells[:])
    for y, cells in zip((12,32,52), states):
        d._box(p, 48, y-1, 60, y+5)
        draw_frame(p, cells, 49, y)


def _page(p):
    ys = (5,8,11,17,20,26,29,32,37,40,43,48,51,54,57,60)
    for y, field in zip(ys, record_fields(512)):
        d._field(p, field, y, x=21)


def _outcome(p):
    _fields(p, record_fields(2), start=6, gap=3)
    _glyph(p, 2, 52, 12, scale=2)
    practice = _model()['records'][512]
    for top, response in ((27,10), (46,20)):
        page_id = practice['success'] if [response] in practice['accepted'] else practice['failure']
        page = _model()['records'][page_id]
        d._number(p, response, 16, 3, top+6)
        d._arrow(p, 23, top+6, 7)
        d._box(p, 33, top, 62, top+15)
        d._number(p, page['kind'], 8, 35, top+2)
        d._number(p, page_id, 16, 45, top+2)
        d._number(p, page['display_kind'], 8, 35, top+6)
        d._number(p, page['display'], 16, 45, top+6)
        draw_frame(p, _model()['records'][page['display']]['cells'], 42, top+9)


def _actions(p):
    for row, values in enumerate(((1,10,512,512),(3,0,512,512),(2,0,512,515))):
        d._write(p, 3, 12+row*12, b''.join(d._bits(v,16) for v in values), 32)
    draw_frame(p, _model()['records'][260]['cells'], 43, 48)


def _feedback(p):
    for row, values in enumerate(((20,515),(10,514),(516,518))):
        d._write(p, 3, 12+row*10, b''.join(d._bits(v,16) for v in values), 32)
    draw_frame(p, _model()['records'][259]['cells'], 43, 12)
    draw_frame(p, _model()['records'][258]['cells'], 43, 46)


def make_route(used, mini_section, inventory_section, inventory_payload):
    if type(used) is not int or not 1 <= used <= carrier.CAPACITY_BYTES:
        raise ValueError('Direct used-byte count outside square.')
    panels = []
    unchanged = (3,4,12)
    for ordinal in range(1,33):
        p = bytearray(4096)
        if ordinal == 1:
            carrier._counting(p)
        elif ordinal in unchanged:
            d.draw_calibration(ordinal, p)
        elif ordinal == 2:
            for index in range(8):
                _bounded(p,1 << index,8,20,12+index*6)
                _bounded(p,index+1,4,40,12+index*6)
        elif ordinal == 5:
            _byte_expansion(p)
        elif ordinal == 6:
            for y, value in zip(range(12,60,6),BYTE_EXAMPLES):
                _bounded(p,value,16,9,y)
                _bounded(p,value >> 8,8,33,y)
                _bounded(p,value & 255,8,47,y)
        elif ordinal == 7:
            for y, value, width in ((12,2048,16),(24,64,16),(36,8,16),(48,used,32)):
                _bounded(p,value,width,48-width,y)
        elif ordinal == 8:
            for row,(a,b) in enumerate(((0,0),(0,1),(1,0),(1,1))):
                for offset,result in ((0,a^b),(32,int(a==b))):
                    # Bounded fields expose zero-valued entries at normal bit scale.
                    for x,value in ((7,a),(13,b),(23,result)):
                        d._box(p,x+offset,10+row*12,x+offset+4,14+row*12)
                        d._number(p,value,1,x+offset+2,12+row*12)
        elif ordinal == 9:
            for y, value in ((10,53),(28,2147483649),(46,2197175160)):
                _bounded(p,value,32,9,y)
                _bounded(p,value >> 1,32,9,y+7)
                d._arrow(p,44,y,6)
                _bounded(p,value & 1,1,53,y)
        elif ordinal == 10:
            for y, value, width in ((14,0xffffffff,32),(32,0x1edc6f41,32),
                                    (50,0x11edc6f41,33)):
                _bounded(p,value,width,48-width,y)
        elif ordinal in (11, 13):
            _calculation(p,final=ordinal == 13)
        elif ordinal == 14:
            for y, value, stored in ((12,53,53),(30,52,53),(48,11,11)):
                d._box(p,2,y-4,61,y+11)
                _bounded(p,value,8,6,y)
                _bounded(p,crc32c(bytes([value])),32,19,y)
                _bounded(p,crc32c(bytes([stored])),32,19,y+7)
                _bounded(p,int(value == stored),1,56,y+4)
        elif ordinal == 15:
            end=len(mini_section)
            for y,values in zip((12,24,36,48),
                                ((0,2,2),(2,4,6),(6,end-10,end-4),(end-4,4,end))):
                d._box(p,5,y-3,58,y+3)
                d._write(p,8,y,b''.join(d._bits(value,16) for value in values),48)
        elif ordinal == 16:
            carrier._mapping(p,used)
        elif ordinal == 17:
            d._matrices(p)
        elif ordinal == 18:
            _references(p)
        elif ordinal == 19:
            _scope(p,mini_section)
        elif ordinal in (20, 29):
            data = inventory_section if ordinal==20 else mini_section
            d._octets(p,data,y=4+(59-(len(data)*8+63)//64)//2)
        elif ordinal == 21:
            _inventory(p,inventory_payload)
        elif ordinal == 22:
            _glyph_record(p)
        elif ordinal == 23:
            _frame_record(p)
        elif ordinal == 24:
            _trace(p)
        elif ordinal == 25:
            _page(p)
        elif ordinal == 26:
            _outcome(p)
        elif ordinal == 27:
            _actions(p)
        elif ordinal == 28:
            _feedback(p)
        elif ordinal == 30:
            _fields(p,record_fields(400),start=11,gap=7)
        elif ordinal == 31:
            a,b=len(inventory_section),len(mini_section);total=a+b
            for y,values in ((12,(0,0,a,a)),(24,(1,a,total,b))):
                d._write(p,0,y,b''.join(d._bits(v,16) for v in values),64)
            d._write(p,8,36,b''.join(d._bits(v,16) for v in (0,1,2)),48)
            d._arrow(p,31,28,5,vertical=True)
            d._number(p,total-1,16,12,52);d._number(p,total,16,36,52)
        else:
            for row, value in enumerate((0,used,carrier.CAPACITY_BYTES,carrier.CAPACITY_BYTES-used)):
                _bounded(p,value,32,9,10+row*10)
                d._write(p,51,10+row*10,b'\1'*(row+1),row+1)
            d._box(p,12,45,51,61)
            _bounded(p,0,32,16,49)
            _bounded(p,32,8,28,57)
        _header(p,ordinal)
        panels.append(bytes(p))
    return d.arrange_panels(panels,columns=32)

def parameters(route):
    """Read the carried right-aligned parameters at their bounded widths."""
    p = d.panel(route,6,columns=32)
    values = [d._read_number(p,48-width,12+row*12,width)
              for row,width in enumerate((16,16,16,32))]
    if values[:3] != [2048,64,8] or not 1 <= values[3] <= carrier.CAPACITY_BYTES:
        raise ValueError('Invalid carried direct-stream parameters.')
    return values[3]
