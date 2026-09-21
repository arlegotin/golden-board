#!/usr/bin/env python3
"""Private lossless-compaction probe; never creates a carrier or changes owners."""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import copy
import hashlib
import json
from pathlib import Path
import unittest

from golden_board import capacity, content
from tools.m2 import measure_slice_v1 as sizing

ROOT=Path(__file__).resolve().parents[2]
MAX_DECODED=65535
MAX_ENCODED=2*MAX_DECODED+3
ALGORITHMS=(1,2,3,4)
NAMES={0:'raw',1:'byte-rle',2:'lzss-256',3:'lzss-4096',4:'lzss-4096-long'}


def _need(value,message):
    if not value:raise ValueError(message)


def _decode(raw):
    _need(type(raw) is bytes and 3<=len(raw)<=MAX_ENCODED,'encoded length')
    codec=raw[0]
    expected=int.from_bytes(raw[1:3],'big')
    _need(codec in NAMES and expected<=MAX_DECODED,'codec or decoded bound')
    if codec==0:
        _need(len(raw)==3+expected,'raw length')
        return raw[3:]
    output=bytearray()
    cursor=3
    window={1:0,2:256,3:4096,4:4096}[codec]
    while codec==1 and len(output)<expected:
        _need(cursor<len(raw),'truncated token')
        tag=raw[cursor];cursor+=1
        length=tag+1 if tag<128 else tag-128+3
        _need(length<=expected-len(output),'decoded overrun')
        if tag<128:
            _need(length<=len(raw)-cursor,'truncated literal')
            output.extend(raw[cursor:cursor+length]);cursor+=length
        else:
            _need(cursor<len(raw),'truncated repetition')
            output.extend(bytes((raw[cursor],))*length);cursor+=1
    while codec in (2,3,4) and len(output)<expected:
        _need(cursor<len(raw),'truncated flags')
        flags=raw[cursor];cursor+=1
        for bit in range(7,-1,-1):
            if len(output)==expected:
                _need(flags&((1<<(bit+1))-1)==0,'unused flag bits')
                break
            if flags&(1<<bit):
                width=3 if codec==4 else 2
                _need(width<=len(raw)-cursor,'truncated copy')
                if codec==2:distance=raw[cursor]+1;length=raw[cursor+1]+3
                else:
                    packed=int.from_bytes(raw[cursor:cursor+width],'big')
                    shift=12 if codec==4 else 4
                    distance=(packed>>shift)+1;length=(packed&((1<<shift)-1))+3
                cursor+=width
                _need(length<=expected-len(output),'decoded overrun')
                _need(distance<=window and distance<=len(output),'backreference bounds')
                for _ in range(length):output.append(output[-distance])
            else:
                _need(cursor<len(raw),'truncated literal')
                output.append(raw[cursor]);cursor+=1
    _need(cursor==len(raw),'trailing encoded bytes')
    return bytes(output)


def _encode(data,codec):
    _need(type(data) is bytes and len(data)<=MAX_DECODED and type(codec) is int and codec in NAMES,'encode bounds')
    output=bytearray(bytes((codec,))+len(data).to_bytes(2,'big'))
    stats={'literal_tokens':0,'repeat_or_copy_tokens':0,'literal_bytes':0,
           'repeat_or_copy_bytes':0,'maximum_distance':0,'encoder_byte_comparisons':0,
           'flag_bytes':0,'decoder_output_writes':len(data),
           'decoder_history_window':{0:0,1:0,2:256,3:4096,4:4096}[codec]}
    if codec==0:
        output.extend(data)
        stats['literal_bytes']=len(data)
        return bytes(output),stats
    window=stats['decoder_history_window']
    history=defaultdict(deque)
    literal=bytearray()
    group=[]

    def token(is_copy,raw):
        group.append((is_copy,raw))
        if len(group)==8:flush_group()

    def flush_group():
        if group:
            output.append(sum(int(copy)<<(7-i) for i,(copy,_) in enumerate(group)))
            for _,raw in group:output.extend(raw)
            stats['flag_bytes']+=1;group.clear()

    def flush():
        if literal:
            output.append(len(literal)-1);output.extend(literal)
            stats['literal_tokens']+=1;stats['literal_bytes']+=len(literal)
            literal.clear()

    def register(index):
        if not window:return
        if index+3<=len(data):history[data[index:index+3]].append(index)
        expired=index-window
        if expired>=0 and expired+3<=len(data):
            key=data[expired:expired+3]
            entries=history[key]
            _need(entries and entries[0]==expired,'encoder index invariant')
            entries.popleft()
            if not entries:del history[key]

    cursor=0
    while cursor<len(data):
        maximum=min({1:130,2:258,3:18,4:4098}[codec],len(data)-cursor)
        length=0;distance=0
        if codec==1:
            run=1
            while run<maximum:
                stats['encoder_byte_comparisons']+=1
                if data[cursor+run]!=data[cursor]:break
                run+=1
            if run>=3:length=run
        elif maximum>=3:
            # At most window candidates, nearest first. Equal maximum matches
            # stop immediately; ties therefore choose the smallest distance.
            for candidate in reversed(history.get(data[cursor:cursor+3],())):
                size=3
                while size<maximum:
                    stats['encoder_byte_comparisons']+=1
                    if data[candidate+size]!=data[cursor+size]:break
                    size+=1
                if size>length:length=size;distance=cursor-candidate
                if length==maximum:break
        if length>=(4 if codec==4 else 3):
            if codec==1:
                flush();output.append(128+length-3);output.append(data[cursor])
            elif codec==2:token(True,bytes((distance-1,length-3)))
            elif codec==4:token(True,(((distance-1)<<12)|(length-3)).to_bytes(3,'big'))
            else:token(True,(((distance-1)<<4)|(length-3)).to_bytes(2,'big'))
            stats['repeat_or_copy_tokens']+=1;stats['repeat_or_copy_bytes']+=length
            stats['maximum_distance']=max(stats['maximum_distance'],distance)
            for index in range(cursor,cursor+length):register(index)
            cursor+=length
        else:
            if codec==1:
                literal.append(data[cursor])
                if len(literal)==128:flush()
            else:
                token(False,bytes((data[cursor],)))
                stats['literal_tokens']+=1;stats['literal_bytes']+=1
            register(cursor);cursor+=1
    flush()
    flush_group()
    _need(len(output)<=MAX_ENCODED,'encoder output bound')
    return bytes(output),stats


def _body_sections(compiled,inputs):
    frames=capacity._frames(compiled.content_bytes,'compaction-all')
    return [{'section_id':row.section_id,'closure':row.closure,'record_ids':list(row.record_ids),
             'plain':b''.join(frames[record_id] for record_id in row.record_ids)}
            for row in inputs.real_content_sections]


def _variant(compiled,base,sections,codec,whole,optional):
    source=copy.deepcopy(sections)
    if whole:
        required=[row for row in source if row['closure']=='m2_required']
        combined={'section_id':16,'closure':'m2_required',
                  'record_ids':[rid for row in required for rid in row['record_ids']],
                  'plain':b''.join(row['plain'] for row in required)}
        source=[combined]+[row for row in source if row['closure']!='m2_required']
    wire=[]
    metadata=[]
    for row in source:
        plain=row['plain']
        wrapped=row['closure']=='m2_required' or optional
        if wrapped:
            encoded,stats=_encode(plain,codec)
            raw,raw_stats=_encode(plain,0)
            if len(raw)<=len(encoded):encoded,stats=raw,raw_stats
            restored=_decode(encoded)
            chosen=encoded[0]
        else:
            encoded=plain;restored=plain;stats=None;chosen=None
        _need(restored==plain,'exact section roundtrip')
        wire.append((row,encoded,restored))
        metadata.append({'section_id':row['section_id'],'closure':row['closure'],
                         'decoded_bytes':len(plain),'payload_bytes':len(encoded),
                         'wrapped':wrapped,'chosen_codec':chosen,'stats':stats,
                         'plain_sha256':hashlib.sha256(plain).hexdigest(),
                         'encoded_sha256':hashlib.sha256(encoded).hexdigest()})
    required_body=b''.join(restored for row,_,restored in wire if row['closure']=='m2_required')
    all_body=b''.join(restored for _,_,restored in wire)
    required_frames=capacity._frames(compiled.required_content_bytes,'compaction-required')
    all_frames=capacity._frames(compiled.content_bytes,'compaction-all')
    required=compiled.required_content_bytes[:4]+required_body+list(required_frames.values())[-1]
    all_stream=compiled.content_bytes[:4]+all_body+list(all_frames.values())[-1]
    _need(required==compiled.required_content_bytes and all_stream==compiled.content_bytes,'stream roundtrip')
    content.stream_validation(required);content.stream_validation(all_stream)
    result={'codec':NAMES[codec],'layout':'whole-required-body' if whole else 'original-whole-record-sections',
            'optional_bodies_wrapped':optional,'sections':metadata,
            'maximum_decoded_section_bytes':max(row['decoded_bytes'] for row in metadata),
            'decoded_section_bound_change_required':any(row['decoded_bytes']>16384 for row in metadata),
            'required_wire_payload_bytes':sum(row['payload_bytes'] for row in metadata if row['closure']=='m2_required'),
            'all_wire_body_payload_bytes':sum(row['payload_bytes'] for row in metadata),
            'roundtrip_required_sha256':hashlib.sha256(required).hexdigest(),
            'roundtrip_all_sha256':hashlib.sha256(all_stream).hexdigest()}
    oversized=[row['section_id'] for row in metadata if row['payload_bytes']>sizing.MAX_SECTION]
    if oversized:
        result.update(admissible_single_section_payloads=False,oversized_section_ids=oversized)
        return result,None,wire
    model=copy.deepcopy(base)
    real=[]
    for (row,encoded,_),meta in zip(wire,metadata,strict=True):
        factor=5 if row['closure']=='m2_required' else 1
        fragments=sizing._fragments(len(encoded))
        real.append({'section_id':row['section_id'],'closure':row['closure'],
                     'payload_bytes':len(encoded),'decoded_bytes':len(row['plain']),
                     'record_ids':row['record_ids'],'factor':factor,'fragments':fragments,
                     'physical_units':factor*fragments})
    model['real_sections']=real
    required_ids=[row['section_id'] for row in real if row['closure']=='m2_required']
    all_ids=[row['section_id'] for row in real]
    for tier in model['tier_frames']:
        bodies=required_ids if tier['section_id']==2 else all_ids
        tier['body_section_ids']=bodies
        tier['payload_bytes']=22+4*len(bodies)+tier['root_frame_bytes']
        tier['fragments']=sizing._fragments(tier['payload_bytes'],len(bodies))
        tier['physical_units']=5*tier['fragments']
    # Compression never spends the semantic authoring/reserve promise. Keep
    # all 105277 allowance bytes and the full 9353 uncompressed reserve bytes.
    groups={factor:sum(row['fragments'] for row in model['real_sections']+model['tier_frames']+
                      model['capacity_sections']+model['reserve_sections'] if row['factor']==factor)
            for factor in (1,2,5)}
    model['noninventory_logical_groups']=groups
    model['noninventory_physical_units']=sum(factor*count for factor,count in groups.items())
    model['base_entry_count']=1+len(real)+len(model['tier_frames'])+len(model['capacity_sections'])+len(model['reserve_sections'])
    model['dependency_count']=sum(len(row['body_section_ids']) for row in model['tier_frames'])
    result.update(admissible_single_section_payloads=True,
                  authoring_payload_bytes=model['authoring_payload_bytes'],reserve_payload_bytes=model['reserve_payload_bytes'],
                  minimum_mandatory_units=sizing._inventory(model,0)['mandatory_units'])
    return result,model,wire


def _route_budget(model):
    best=None
    table=sizing._table(256)
    for side,width in sizing._pairs(2048):
        interior=side-2*width
        if not table[interior//8]:continue
        layout=sizing._layout(model,side,width)
        if layout is None:continue
        maximum=5*width*(side-width)//42
        if best is None or maximum>best['maximum_route_prefix_bytes_per_sector']:
            best=dict(layout,maximum_route_prefix_bytes_per_sector=maximum,
                      existing_route_growth_budget_per_sector=maximum-sizing.ROUTE_PREFIX_BYTES,
                      fixed24_route_growth_budget_per_sector=maximum-23499,
                      fixed24_and_table_dedup_growth_budget_per_sector=maximum-21717)
    return best


def _probe(root,output):
    inputs=sizing._inputs(root)
    compiled=inputs['revised']
    base=sizing._model(inputs['revised_inputs'],inputs['policy'])
    sections=_body_sections(compiled,inputs['revised_inputs'])
    _need((len(compiled.required_content_bytes),len(compiled.content_bytes))==(42432,55664),
          'review changed source stream before probing')
    streams={'required':{'bytes':len(compiled.required_content_bytes),'sha256':compiled.required_content_sha256},
             'all':{'bytes':len(compiled.content_bytes),'sha256':compiled.content_sha256}}
    diagnostics=[]
    artifacts={}
    for codec in ALGORITHMS:
        for name,raw in (('required',compiled.required_content_bytes),('all',compiled.content_bytes)):
            encoded,stats=_encode(raw,codec)
            _need(_decode(encoded)==raw,'full stream diagnostic roundtrip')
            diagnostics.append({'codec':NAMES[codec],'stream':name,'decoded_bytes':len(raw),
                                'encoded_bytes':len(encoded),'stats':stats})
    variants=[]
    for codec in ALGORITHMS:
        for whole in (False,True):
            for optional in (False,True):
                row,model,wire=_variant(compiled,base,sections,codec,whole,optional)
                if not optional:
                    required=[(item,encoded) for item,encoded,_ in wire if item['closure']=='m2_required']
                    # This owner-only inspection container is not a carrier or
                    # transport envelope. Its six-byte row wrapper is not part
                    # of the measured, individually protected payloads.
                    bundle=len(required).to_bytes(2,'big')+b''.join(
                        item['section_id'].to_bytes(2,'big')+len(encoded).to_bytes(4,'big')+encoded
                        for item,encoded in required)
                    artifacts[f"compaction-{NAMES[codec]}-{'whole' if whole else 'sections'}.bin"]=bundle
                if model is not None:
                    row['existing_2048_128_fixed_point']=sizing._layout(model,2048,128)
                    row['maximum_bootstrap_route_budget']=_route_budget(model)
                    row['route_sensitivity']=[]
                    for route_name,prefix in (('existing',29091),('fixed24-node-assumption',23499),
                                              ('fixed24-and-table-dedup-assumption',21717)):
                        search=sizing._search(model,2048,prefix-29091)
                        row['route_sensitivity'].append({'name':route_name,
                            'codec_decoder_and_teaching_bytes_counted':0,
                            **{key:value for key,value in search.items() if key not in ('rows','mapping_table')}})
                variants.append(row)
    audit_path='artifacts/work/participant-revision/bounded-redesign.md'
    audit=sizing._read(root,audit_path)
    probe_source=sizing._read(root,'tools/m2/probe_slice_compaction.py')
    report={'schema':'golden-board.private-slice-compaction/v1',
            'status':'feasibility-only-unchanged-512KiB-cap-no-carrier-or-pass',
            'streams':streams,'lesson_pages':sum(isinstance(r.payload,content.ContentLessonNode)
                                               for r in compiled.required_projection.records),
            'input_identities':inputs['input_identities']+[
                {'path':audit_path,'bytes':len(audit),'sha256':hashlib.sha256(audit).hexdigest()},
                {'path':'tools/m2/probe_slice_compaction.py','bytes':len(probe_source),
                 'sha256':hashlib.sha256(probe_source).hexdigest()}],
            'authoring_payload_bytes':105277,'reserve_payload_bytes':9353,'inventory_allowance_bytes':16384,
            'codec_header_bytes':3,'codec_max_decoded_bytes':MAX_DECODED,'codec_max_encoded_bytes':MAX_ENCODED,
            'required_section_representation':'conditional new section-version payload wrapper; no sniffing or reinterpretation of old section bytes',
            'full_stream_size_diagnostics':diagnostics,'variants':variants,
            'old_2048_128_shell':{'prefix_bytes_per_sector':29091,
                'maximum_equal_prefix_bytes_per_sector':5*128*(2048-128)//42,
                'remaining_bytes_per_sector':5*128*(2048-128)//42-29091},
            'grammar':{
                'header':'u8 codec (0 raw, 1 byte-RLE, 2 LZSS-256, 3 LZSS-4096, 4 LZSS-4096-long) || u16_be decoded length',
                'raw':'exactly decoded_length literal bytes',
                'rle':'tag<128: next tag+1 bytes literal; tag>=128: next byte repeated tag-128+3 times',
                'lz_flags':'one flags byte for up to eight tokens, MSB first: 0 literal(next byte); 1 copy(next two bytes for codecs 2/3, three bytes for codec 4)',
                'lz256_copy':'u8 distance_minus_one || u8 length_minus_three; distance 1..256, length 3..258',
                'lz4096_copy':'u16_be ((distance_minus_one<<4)|length_minus_three); distance 1..4096, length 3..18',
                'lz4096_long_copy':'u24_be ((distance_minus_one<<12)|length_minus_three); distance 1..4096, length 3..4098; encoder minimum match 4',
                'rejection':'check input/output bounds before each token; copy distance must not exceed produced bytes; unused final flag bits zero; exact declared output and exact input EOF',
                'overlap':'copy byte by byte from current output[-distance]; overlapping repetitions are allowed',
                'encoder':'greedy longest match, nearest-distance tie; bounded sliding 3-byte index; raw wrapper if no smaller compressed encoding',
            }}
    main_rows=[r for r in variants if not r['optional_bodies_wrapped']]
    table=[]
    for row in main_rows:
        minimum=row.get('minimum_mandatory_units','oversize')
        budget=row.get('maximum_bootstrap_route_budget')
        route='none' if budget is None else str(budget['maximum_route_prefix_bytes_per_sector'])
        table.append(f"| {row['codec']} | {'whole required body' if 'whole-required' in row['layout'] else 'original sections'} | {row['required_wire_payload_bytes']} | {minimum} | {route} |")
    selected=next(r for r in main_rows if r['codec']=='lzss-4096' and r['layout']=='original-whole-record-sections')
    best=selected['maximum_bootstrap_route_budget']
    _need(best is not None,'selected diagnostic missing route budget')
    summary=f'''# Lossless compaction within the unchanged 512 KiB scope

All 65 pages and all anthology data are preserved byte for byte. The required
stream remains 42,432 bytes (`{compiled.required_content_sha256}`); the all stream
remains 55,664 bytes (`{compiled.content_sha256}`). No source stream, teaching
content, production owner or ceiling was changed. The 2560 calculation remains
an earlier conditional sensitivity, not a promoted answer to this constraint.

The useful case is **LZSS with a 4096-byte window applied separately to the three
original required sections**: 16,273 / 15,067 / 11,076 decoded bytes become
**4,968 / 4,849 / 2,987 bytes**, including each three-byte codec header. This
preserves the existing decoded-section size bound and all record boundaries.
Required transport payload falls from 42,416 to 12,804 bytes without changing
the typed content stream. Optional game/fixture/library bodies remain plain.

Compression alone still does not fit the existing bootstrap route. The exact
fixed-point minimum is **1,893 physical units**, against **1,858** available at
2048/128. The old route occupies 29,091 bytes per sector; that geometry allows
at most 29,257 with five-percent headroom, leaving only **166 new route bytes**.
The codec decoder, its examples and its resource contract are not yet encoded.

## Exact measured alternatives

All sizes include explicit codec framing. Capacity retains the full 105,277-byte
authoring allowance, full 16,384-byte logical inventory allowance and full
9,353-byte uncompressed reserve. Required bodies, inventory and both tier
frames keep factor 5; replicated capacity/reserve keep factor 2; all-only
material keeps factor 1. CRC, section headers, fragment rounding, inventory
growth, load-section fixed point and tail padding remain charged.

These payloads would require explicit new section-version dispatch. The probe
does not sniff existing payload bytes or reinterpret a current version. It
assumes the existing fixed-width version field can select the new payload
grammar; the three-byte codec header is additionally charged inside that
payload. No production version number or receiver acceptance is assigned here.

| Codec | Required grouping | Encoded required payload | Minimum mandatory units | Largest affordable route prefix per sector within 2048 |
|---|---|---:|---:|---:|
{chr(10).join(table)}

RLE and 256-window LZSS do not offer enough savings. Their whole-body forms also
exceed the existing 16,384-byte encoded-section cap. The whole-body 4096 case
is diagnostic only: 42,416 decoded bytes become 12,458, but decoding one body
that large would change the decoded-section bound and section grouping. Its
extra savings do not justify treating that bound as already authorized.
Separately wrapping all optional bodies produced no physical saving: raw
fallback headers increased total body charges by two units in the measured
cases. The favorable layout therefore leaves those bodies unchanged.

The requested three-byte-copy alternative (twelve distance bits, twelve length
bits, maximum copy length 4098, greedy minimum match 4) is also measured. Its
original sections total 14,295 bytes (5,394 / 5,536 / 3,365), requiring 1,938
mandatory units. Its whole-body encoding is 13,855 bytes. The longer tokens
outweigh the longer matches on this exact content; neither improves the
short-copy 4096-window result. No optimal-parser search was assumed.

## Remaining bootstrap budget

The per-section 4096 case has a complete inventory/load fixed point at
**{best['side']}/{best['width']}**, interior {best['interior_side']}, with
{best['unit_population']} total units, {best['mandatory_units']} mandatory units,
{best['load_units']} load units, {best['load_payload_total']} load payload bytes,
inventory {best['inventory_payload_bytes']} bytes/{best['inventory_fragment_count']} fragments,
and {best['fixed_pad_cells']} pad cells. That geometry admits at most
**{best['maximum_route_prefix_bytes_per_sector']} route bytes per sector** while
preserving the exact five-percent headroom formula.

The parallel [bounded redesign audit](bounded-redesign.md) derives a lossless
fixed-24-byte recipe-node representation saving 5,592 bytes per sector, reducing
the old prefix to 23,499. Under that unencoded format proposal, the remaining
codec/teaching budget is **{best['fixed24_route_growth_budget_per_sector']} bytes per sector**.
Its additional TABLE deduplication proposal reduces the prefix to 21,717 and
would leave **{best['fixed24_and_table_dedup_growth_budget_per_sector']} bytes per sector**.
These are conditional budgets, not measured decoder costs or a bootstrap pass.
The JSON includes exhaustive 2048-cap searches for each stated prefix, with
the codec's added route charge explicitly zero. They are lower-cost sensitivity
calculations until the decoder and every worked/held-out example are encoded.

Thus this probe finds a plausible lossless path within 512 KiB: keep the three
original decoded sections, compact their bytes, and compact the recipe route.
It does not establish that the receiver explanation and implementation fit.
Large fixed-width VM state, full-state copies and worked/held-out example sizes
must be charged in the next concrete design. Existing damage and independence
passes cannot be reused for different bytes or physical populations.

## Closed experimental token grammar

Each encoded body begins with `codec:u8 || decoded_length:u16_be`. Codec 0 is
raw data of that exact length. Codec 1 uses a one-byte tag: 0..127 means the
next tag+1 literal bytes; 128..255 means repeat the following byte tag-125 times
(3..130). Codecs 2, 3 and 4 use one flag byte for up to eight tokens, high bit
first: 0 means one following literal byte, 1 means a copy. Copies are two bytes
in codecs 2/3 and three bytes in codec 4.

- Codec 2: `distance_minus_1:u8 || length_minus_3:u8`; window 256,
  lengths 3..258.
- Codec 3: `((distance_minus_1)<<4)|(length_minus_3):u16_be`; window 4096,
  lengths 3..18.
- Codec 4: `((distance_minus_1)<<12)|(length_minus_3):u24_be`; window 4096,
  lengths 3..4098. The greedy encoder emits matches only at length 4 or more.

These codec IDs compare private experiments. A production proposal need only
teach its one selected codec, not every alternative in this probe.

The decoder rejects truncated headers, tokens or distances; backward distance
beyond produced output; output beyond its declared length; nonzero unused
final flag bits; and trailing input. Copies may overlap and are performed
byte by byte. The encoder is deterministic greedy longest-match with nearest
distance as tie-breaker. It uses a bounded sliding three-byte index and no
external dependencies, engine or unbounded search.

The probe's general codec bound is 65,535 decoded and 131,073 encoded bytes.
The preferred per-section proposal can enforce the existing 16,384 decoded
limit instead; measured maxima are 16,273 decoded and 4,968 encoded. A normal
streaming decoder needs a 4096-byte history window plus bounded counters and
input/output storage. Every successful token produces at least one byte, so
there are at most decoded_length tokens and exactly decoded_length output
writes; copies read at most that many history bytes. These are byte-operation
bounds, not recipe-VM work/scratch receipts. VM realization may cost much more.

## Verification and artifacts

```sh
PYTHONPATH=python:. .venv/bin/python tools/m2/probe_slice_compaction.py --self-test
PYTHONPATH=python:. .venv/bin/python tools/m2/probe_slice_compaction.py --output-dir artifacts/work/participant-revision
```

Roundtrips reconstruct both original streams exactly and pass public content
validation. The tests cover empty/full-bound payloads, overlap, every truncated
prefix of representative encodings, invalid distances, unused flags, output
overrun and exact EOF. Original inputs and parallel assumptions are hash-bound
in `compaction-measurement.json`. Each `.bin` is an owner-only inspection
container: u16 section count, then u16 section ID / u32 encoded length / encoded
body. That container is not a carrier or an uncharged transport format.
'''
    artifacts['compaction-measurement.json']=sizing._encoded(report)
    summary+='\nArtifact digests:\n\n'+''.join(
        f'- `{name}`: {len(raw):,} bytes, SHA-256 `{hashlib.sha256(raw).hexdigest()}`.\n'
        for name,raw in sorted(artifacts.items()))
    artifacts['compaction-summary.md']=summary.encode()
    output.mkdir(parents=True,exist_ok=True)
    for name,raw in artifacts.items():
        _need(name.startswith('compaction-'),'probe output ownership')
        (output/name).write_bytes(raw)
    print(json.dumps({'status':report['status'],'preferred_required_payload_bytes':12804,
                      'mandatory_units':selected['minimum_mandatory_units'],'old_2048_128_fit':False,
                      'conditional_bootstrap_budget':best},sort_keys=True))


class _CodecTests(unittest.TestCase):
    def test_exact_roundtrip_and_determinism(self):
        cases=(b'',b'a',bytes(range(256)),b'a'*65535,(b'abcd'*1024)+bytes(range(256)),
               bytes((i*73+i//11)%256 for i in range(4096)))
        for data in cases:
            for codec in ALGORITHMS:
                with self.subTest(codec=codec,length=len(data)):
                    encoded,stats=_encode(data,codec)
                    self.assertEqual(_decode(encoded),data)
                    self.assertEqual(_encode(data,codec),(encoded,stats))
                    self.assertLessEqual(stats['decoder_output_writes'],len(data))

    def test_all_proper_prefixes_are_rejected(self):
        for codec in ALGORITHMS:
            encoded,_=_encode(b'abcabcabcxyz'*12,codec)
            for length in range(len(encoded)):
                with self.subTest(codec=codec,length=length):
                    with self.assertRaises(ValueError):_decode(encoded[:length])
            with self.assertRaises(ValueError):_decode(encoded+b'\0')

    def test_malformed_backreferences_and_output_bounds(self):
        cases=(b'\x02\0\3\x80\0\0',b'\x03\0\3\x80\0\0',
               b'\x03\0\4\x40a\xff\xf0',b'\x02\0\4\x40a\1\0',
               b'\x02\0\2\x40a\0\0',b'\x01\0\2\x80a',
               b'\x01\0\3\2ab',b'\5\0\0',b'\0\0\1',
               b'\0\0\0x',b'\x02\0\1\x40a',b'\4\0\3\x80\0\0\0',
               b'\4\0\4\x40a\0\0',b'\4\0\2\x40a\0\x0f\xff')
        for raw in cases:
            with self.subTest(raw=raw.hex()):
                with self.assertRaises(ValueError):_decode(raw)
        self.assertEqual(_decode(b'\x02\0\4\x40a\0\0'),b'aaaa')
        self.assertEqual(_decode(b'\x03\0\4\x40a\0\0'),b'aaaa')
        with self.assertRaises(ValueError):_encode(b'x'*(MAX_DECODED+1),2)
        with self.assertRaises(ValueError):_decode(b'\0'*(MAX_ENCODED+1))

    def test_maximum_window_distances(self):
        for codec,window in ((2,256),(3,4096),(4,4096)):
            prefix=bytes(index%251 for index in range(window))
            copy={2:bytes((255,0)),3:b'\xff\xf0',4:b'\xff\xf0\0'}[codec]
            raw=bytes((codec,))+(window+3).to_bytes(2,'big')+b''.join(
                b'\0'+prefix[i:i+8] for i in range(0,window,8))+b'\x80'+copy
            self.assertEqual(_decode(raw),prefix+prefix[:3])

    def test_exact_original_sections_and_conservative_capacity(self):
        inputs=sizing._inputs(ROOT)
        original=inputs['revised']
        base=sizing._model(inputs['revised_inputs'],inputs['policy'])
        row,model,_=_variant(original,base,_body_sections(original,inputs['revised_inputs']),3,False,False)
        self.assertEqual([r['payload_bytes'] for r in row['sections'] if r['closure']=='m2_required'],[4968,4849,2987])
        self.assertFalse(row['decoded_section_bound_change_required'])
        self.assertEqual(row['roundtrip_required_sha256'],original.required_content_sha256)
        self.assertEqual(row['roundtrip_all_sha256'],original.content_sha256)
        self.assertEqual((model['authoring_payload_bytes'],model['reserve_payload_bytes']),(105277,9353))
        self.assertEqual(row['minimum_mandatory_units'],1893)
        self.assertIsNone(sizing._layout(model,2048,128))
        best=_route_budget(model)
        self.assertEqual((best['side'],best['width'],best['maximum_route_prefix_bytes_per_sector']),(2048,112,25813))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args()
    if args.self_test:
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(_CodecTests))
        if not result.wasSuccessful():raise SystemExit(1)
        return
    if args.output_dir is None:parser.error('--output-dir is required unless --self-test')
    _probe(ROOT,args.output_dir)


if __name__=='__main__':main()
