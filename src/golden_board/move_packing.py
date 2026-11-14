"""Fixed6/6/3 unsigned move fields; literal playback remains separate.

This is authoring-time data representation, not chess inference or a Player rule.
"""
from copy import deepcopy
from functools import lru_cache
from .document import decode_document,encode_document

SCHEMA=[16,1,6,6,3]

def pack_move(row):
    if not isinstance(row,(list,tuple)) or len(row)!=3 or any(type(v)is not int for v in row):raise ValueError('Three exact unsigned fields required.')
    origin,target,choice=row
    if not 0<=origin<64 or not 0<=target<64 or not 0<=choice<=4:raise ValueError('Move field outside6/6/3 declared domain.')
    return (origin<<9)|(target<<3)|choice

def unpack_move(value):
    if type(value)is not int or not 0<=value<32768 or (value&7)>4:raise ValueError('Invalid high padding bit or choice; no masking/repair.')
    return [value>>9,(value>>3)&63,value&7]

@lru_cache(maxsize=2)
def pack_anthology(original):
    d=deepcopy(decode_document(original));records=d['records'];processed=set()
    schema=max(records)+1
    if schema>=65535:raise ValueError('No schema record identity available.')
    records[schema]={'kind':5,'id':schema,'rows':1,'cols':5,'values':list(SCHEMA)}
    for entry in d['entries']:
        trace=records[entry]
        if trace['kind']!=3 or len(trace['data'])!=2:raise ValueError('Expected qualified two-table literal game trace.')
        ident=trace['data'][0]
        if ident not in processed:
            table=records[ident]
            if table['kind']!=5 or table['cols']!=3:raise ValueError('Expected unpacked three-column source moves.')
            values=table['values'];table['values']=[pack_move(values[i:i+3]) for i in range(0,len(values),3)];table['cols']=1
            processed.add(ident)
        trace['data'].append(schema)
    return encode_document(d['entries'],list(records.values()))
