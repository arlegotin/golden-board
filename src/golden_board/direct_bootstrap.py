"""Final clean bootstrap facade.

Lazy entrypoints permit the authoring module to reuse these calibration helpers.
No older drawing route is needed by the current runtime.
"""
from . import raw_draw as d

SIDE=2048
VERSION=8 # External layout engineering revision, never carried in the message.
START=64
WIDTH,HEIGHT,COLUMNS=2048,64,32
CAPACITY_BYTES=(SIDE-START)*SIDE//8
LAYOUT_REVISION='bootstrap-field-boundaries-1'
PARAMETER_PANEL=6

def _counting(p):
    # Two full-size fields, one above the other. Keep both carry boundaries and
    # the four-bit maximum; the next panel still teaches every bit's significance.
    values=(0,1,2,3,4,7,8,15)
    for top,width in ((9,4),(37,8)):
        for row,value in enumerate(values):
            y=top+3*row
            d._write(p,15,y,b'\1'*value+b'\0'*(16-value),16)
            d._number(p,value,width,41,y)

def _mapping(p,used):
    examples=((0,0),(0,7),(1,0),(255,7),(256,0),(used-1,7),(CAPACITY_BYTES-1,7),(used,0))
    for i,(byte,bit) in enumerate(examples):
        y=7+i*7;d._box(p,6,y-2,57,y+5)
        d._number(p,byte,32,9,y);d._number(p,bit,3,52,y)
        d._number(p,START+byte//256,16,9,y+3);d._number(p,(byte%256)*8+bit,16,39,y+3)

def miniature():
    from .bootstrap_clarity import miniature as current
    return current()


def make_route(used,mini_section,inventory_section,inventory_payload):
    from .bootstrap_clarity import make_route as current
    return current(used,mini_section,inventory_section,inventory_payload)


def parameters(route):
    from .bootstrap_clarity import parameters as current
    return current(route)


def extract(symbols):
    return b''.join(symbols[y*SIDE:y*SIDE+WIDTH] for y in range(HEIGHT))
