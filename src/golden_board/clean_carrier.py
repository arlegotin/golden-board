"""Current single-copy grammar: one direct checked-section stream, atomic clean-input acceptance.

No fragments, row packets, recovery copies, repair or subject inference.
"""
from functools import lru_cache
import struct
from .checksum import crc32c
from .document import Reader,decode_document
from . import direct_bootstrap as raw

SIDE=2048
VERSION=raw.VERSION
START=raw.START
CAPACITY_BYTES=raw.CAPACITY_BYTES
SECTION_HEADER_BYTES=6
SECTION_FRAMING_BYTES=10
BYTE_BITS=tuple(bytes((v>>b)&1 for b in range(7,-1,-1)) for v in range(256))
INVERSE=bytes([1,0]+list(range(2,256)))

def unpack_bits(data):return b''.join(BYTE_BITS[v] for v in data)

def pack_bits(symbols):
    if len(symbols)%8 or any(v>1 for v in symbols):raise ValueError('Binary aligned symbols required.')
    return bytes(sum(symbols[i+j]<<(7-j) for j in range(8)) for i in range(0,len(symbols),8))

def transform(symbols,rotation=0,mirror=False,inverse=False):
    if len(symbols)!=SIDE*SIDE:raise ValueError('Clean square requires4194304symbols.')
    result=symbols
    for _ in range(rotation%4):result=b''.join(result[c::SIDE][::-1] for c in range(SIDE))
    if mirror:result=b''.join(result[r:r+SIDE][::-1] for r in range(0,len(result),SIDE))
    return result.translate(INVERSE) if inverse else result

def payload_cell(byte,bit):
    if type(byte)is not int or not 0<=byte<CAPACITY_BYTES or type(bit)is not int or not 0<=bit<8:raise ValueError('Direct byte/bit outside square.')
    return START*SIDE+byte*8+bit

def encode_section(ident,kind,payload):
    if type(ident)is not int or not 0<=ident<65535 or kind!=(0 if ident==0 else 1):raise ValueError('Invalid section identity/kind.')
    covered=struct.pack('>HI',ident,len(payload))+payload
    return covered+crc32c(covered).to_bytes(4,'big')

def decode_section(data):
    if len(data)<10 or len(data)>CAPACITY_BYTES:raise ValueError('Invalid section length.')
    ident,length=struct.unpack('>HI',data[:6]);kind=0 if ident==0 else 1
    if length!=len(data)-10 or length>CAPACITY_BYTES-10:raise ValueError('Invalid declared section length.')
    if ident==65535:raise ValueError('Section identity mismatch.')
    check=int.from_bytes(data[-4:],'big')
    if crc32c(data[:-4])!=check:raise ValueError('Section integrity mismatch.')
    return {'id':ident,'kind':kind,'payload':data[6:-4],'crc':check}

def inventory_for(documents):
    if not isinstance(documents,dict) or not documents or len(documents)>=65535:raise ValueError('Nonempty document inventory required.')
    parts=[len(documents).to_bytes(2,'big')]
    for ident,data in sorted(documents.items()):
        document=decode_document(data);section=encode_section(ident,1,data);entries=document['entries']
        parts.append(struct.pack('>HIIH',ident,len(data),int.from_bytes(section[-4:],'big'),len(entries)))
        parts.extend(e.to_bytes(2,'big') for e in entries)
    return b''.join(parts)

def decode_inventory(payload):
    reader=Reader(payload)
    count=reader.uint(2)
    if not 1<=count<=(len(payload)-2)//14:raise ValueError('Inventory count exceeds received data.')
    items={};previous=0
    for _ in range(count):
        ident,length,check,n=reader.uint(2),reader.uint(4),reader.uint(4),reader.uint(2)
        entries=reader.integers(n)
        if not previous<ident<65535 or not length or not entries or len(set(entries))!=len(entries):raise ValueError('Invalid inventory identity/length/roots.')
        previous=ident;items[ident]={'length':length,'crc':check,'entries':entries}
    reader.end();return items

@lru_cache(maxsize=1)
def _mini():
    data=raw.miniature();section=encode_section(1,1,data);inventory=inventory_for({1:data})
    return section,encode_section(0,0,inventory),inventory

def make_carrier(documents):
    inventory=inventory_for(documents);sections={0:encode_section(0,0,inventory)}
    sections.update({i:encode_section(i,1,data) for i,data in sorted(documents.items())})
    stream=b''.join(sections.values());used=len(stream)
    if used>CAPACITY_BYTES:raise ValueError(f'Measured clean fit failure: {used}bytes > {CAPACITY_BYTES}.')
    route=raw.make_route(used,*_mini());symbols=bytearray(SIDE*SIDE)
    for y in range(raw.HEIGHT):symbols[y*SIDE:y*SIDE+raw.WIDTH]=route[y*raw.WIDTH:(y+1)*raw.WIDTH]
    symbols[START*SIDE:START*SIDE+used*8]=unpack_bits(stream)
    cursor=0;ledger={}
    for ident,section in sections.items():
        ledger[str(ident)]={'byte_offset':cursor,'absolute_byte_offset':START*SIDE//8+cursor,
            'section_bytes':len(section),'body_bytes':len(section)-10,'framing_bytes':10}
        cursor+=len(section)
    cells={'discovery_calibration':raw.WIDTH*raw.HEIGHT,'top_band_reserve':(SIDE-raw.WIDTH)*START,
        'document_payload':sum(map(len,documents.values()))*8,'inventory_payload':len(inventory)*8,
        'integrity_framing':len(sections)*10*8,'alignment_padding':0,'trailing_reserve':(CAPACITY_BYTES-used)*8}
    assert sum(cells.values())==SIDE*SIDE and cursor==used
    return bytes(symbols),{'wire_version':VERSION,'bootstrap_layout':raw.LAYOUT_REVISION,'side':SIDE,'payload_capacity_bytes':CAPACITY_BYTES,
        'used_payload_bytes':used,'reserve_bytes':CAPACITY_BYTES-used,'logical_sections':len(sections),
        'stored_sections':len(sections),'discovery_routes':1,'sections':ledger,'cell_ledger':cells,'recovery':'unsupported'}

def _decode_normalized(symbols):
    route=raw.extract(symbols);used=raw.parameters(route)
    if route!=raw.make_route(used,*_mini()):raise ValueError('Observed direct discovery route does not validate.')
    if any(symbols[START*SIDE+used*8:]):raise ValueError('Nonzero final reserve.')
    stream=pack_bits(symbols[START*SIDE:START*SIDE+used*8]);reader=Reader(stream);sections={};previous=-1
    while reader.offset<used:
        start=reader.offset;remaining=used-start
        if remaining<10:raise ValueError('Truncated section length/header/check.')
        header=reader.take(6);length=int.from_bytes(header[2:6],'big')
        if length>remaining-10 or length>CAPACITY_BYTES-10:raise ValueError('Invalid declared section length.')
        # Bound before taking/slicing; never allocate from an untrusted u32.
        reader.take(length+4);section=decode_section(stream[start:reader.offset]);ident=section['id']
        if ident<=previous or previous==-1 and ident!=0:raise ValueError('Section order/identity mismatch.')
        sections[ident]=section;previous=ident
    reader.end()
    if 0 not in sections:raise ValueError('Missing inventory section.')
    inventory=decode_inventory(sections[0]['payload'])
    if list(sections)!=[0,*inventory]:raise ValueError('Inventory section set/order/count mismatch.')
    documents={}
    for ident,item in inventory.items():
        section=sections[ident];payload=section['payload'];document=decode_document(payload)
        if len(payload)!=item['length'] or section['crc']!=item['crc'] or document['entries']!=item['entries']:raise ValueError('Inventory length/check/root mismatch.')
        documents[ident]=payload
    return {'documents':documents,'inventory':inventory,'used_payload_bytes':used,
        'stored_sections':len(sections),'state':'checked_complete','wire_version':VERSION}

@lru_cache(maxsize=1)
def _signature():
    route=raw.make_route(1,*_mini())
    return tuple((r,c,route[r*raw.WIDTH+c]) for r in range(64) for c in range(64))

def _coordinate(r,c,turn,mirror):
    if mirror:c=SIDE-1-c
    return ((r,c),(SIDE-1-c,r),(SIDE-1-r,SIDE-1-c),(c,SIDE-1-r))[turn]

def decode_symbols(symbols):
    if len(symbols)!=SIDE*SIDE or any(v>1 for v in symbols):raise ValueError('Require complete clean2048square binary observation.')
    accepted=[];diagnostics=[]
    for turn in range(4):
        for mirror in (False,True):
            for inverse in (False,True):
                if any((symbols[(p:=_coordinate(r,c,turn,mirror))[0]*SIDE+p[1]]^inverse)!=v for r,c,v in _signature()):continue
                normalized=transform(symbols,turn,mirror,inverse)
                try:result=_decode_normalized(normalized)
                except ValueError as error:diagnostics.append(str(error));continue
                result['normalization']={'rotation':turn,'mirror':mirror,'inverse':inverse};accepted.append(result)
    if len(accepted)!=1:raise ValueError(f'Clean extraction needs one valid orientation; found{len(accepted)}. '+('; '.join(diagnostics) or 'Discovery calibration mismatch.'))
    accepted[0]['valid_orientations']=1;return accepted[0]

def decode_serial(data):
    if data.endswith(b'\n'):data=data[:-1]
    if len(data)!=SIDE*SIDE or any(v not in (48,49) for v in data):raise ValueError('Require exact delimited clean0/1symbols with optional finalLF.')
    return decode_symbols(data.translate(bytes.maketrans(b'01',b'\0\1')))
