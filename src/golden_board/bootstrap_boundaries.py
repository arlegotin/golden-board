"""Explicit field-boundary candidate; the frozen default remains reproducible.

Only drawing changes live here. Examples, miniature bytes, unchanged panels and
the carrier grammar come from the existing construction pipeline.
"""
from . import bootstrap_clarity as frozen, raw_draw as d
from .checksum import byte_trace, crc32c
from .direct_bootstrap import (SIDE, START, WIDTH, HEIGHT, COLUMNS, VERSION,
                               CAPACITY_BYTES, extract)

LAYOUT_REVISION = 'bootstrap-field-boundaries-1'
CHANGED_PANELS = (2,6,7,9,10,11,13,14,18,19,32)


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


def _draw(p, ordinal, used, section):
    if ordinal == 2:
        for index in range(8):
            _bounded(p,1 << index,8,20,12+index*6)
            _bounded(p,index+1,4,40,12+index*6)
    elif ordinal == 6:
        for y, value in zip(range(12,60,6),frozen.BYTE_EXAMPLES):
            _bounded(p,value,16,9,y)
            _bounded(p,value >> 8,8,33,y)
            _bounded(p,value & 255,8,47,y)
    elif ordinal == 7:
        for y, value, width in ((12,2048,16),(24,64,16),(36,8,16),(48,used,32)):
            _bounded(p,value,width,48-width,y)
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
    elif ordinal in (11,13):
        _calculation(p,final=ordinal == 13)
    elif ordinal == 14:
        for y, value, stored in ((12,53,53),(30,52,53),(48,11,11)):
            d._box(p,2,y-4,61,y+11)
            _bounded(p,value,8,6,y)
            _bounded(p,crc32c(bytes([value])),32,19,y)
            _bounded(p,crc32c(bytes([stored])),32,19,y+7)
            _bounded(p,int(value == stored),1,56,y+4)
    elif ordinal == 18:
        for top, ident, refs in ((7,6,()),(21,7,()),(35,8,(6,)),(49,9,(7,8))):
            _bounded(p,ident,8,5,top+4)
            _bounded(p,len(refs),8,19,top+4)
            d._box(p,32,top,60,top+8)
            for x, ref in zip((36,49),refs):
                _bounded(p,ref,8,x,top+4)
    elif ordinal == 19:
        frozen._scope(p,section)
        for y in (33,56):
            d._box(p,6,y-2,57,y+2)
        _bounded(p,crc32c(section[:-4]),32,16,45)
    elif ordinal == 32:
        for row, value in enumerate((0,used,CAPACITY_BYTES,CAPACITY_BYTES-used)):
            _bounded(p,value,32,9,10+row*10)
            d._write(p,51,10+row*10,b'\1'*(row+1),row+1)
        d._box(p,12,45,51,61)
        _bounded(p,0,32,16,49)
        _bounded(p,32,8,28,57)


def make_route(used, mini_section, inventory_section, inventory_payload):
    canonical = frozen.make_route(used,mini_section,inventory_section,inventory_payload)
    panels = []
    for ordinal in range(1,33):
        if ordinal in CHANGED_PANELS:
            p = bytearray(4096)
            _draw(p,ordinal,used,mini_section)
            frozen._header(p,ordinal)
            panels.append(bytes(p))
        else:
            panels.append(d.panel(canonical,ordinal-1,columns=32))
    return d.arrange_panels(panels,columns=32)


def parameters(route):
    p = d.panel(route,6,columns=32)
    values = [d._read_number(p,48-width,12+row*12,width)
              for row, width in enumerate((16,16,16,32))]
    if values[:3] != [2048,64,8] or not 1 <= values[3] <= CAPACITY_BYTES:
        raise ValueError('Invalid carried candidate parameters.')
    return values[3]
