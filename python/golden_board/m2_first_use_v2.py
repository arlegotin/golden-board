"""Finite observed first-use spans and literal prerequisites; no source fallback."""
from hashlib import sha256

from . import canonical_manifest
from .m2_decoder import DecoderError
from .m2_route_receiver_v2 import decode_observed_route_v2
from .recipe_wire_v2 import decode_recipe_package_v2, evaluate_recipe_v2

_LIMIT = 1_048_576
_DEPS = ((),(1,),(1,),(2,3),(3,4),(5,),(6,),(6,7),(6,8),(7,8,9),(10,),(11,))


class FirstUseError(ValueError):
    """Incomplete, ungrounded or mismatched finite coverage."""


def _need(ok, why):
    if not ok:
        raise FirstUseError(why)


def _number(raw, at, width):
    _need(0 <= at <= len(raw) and width <= len(raw)-at,'field-boundary')
    return int.from_bytes(raw[at:at+width],'big')


def _identity(raw):
    return dict(bytes=len(raw),sha256=sha256(raw).hexdigest())


def _uleb(raw, at, end, bits):
    """Read a bounded canonical field while preserving its actual wire span."""
    start=at;value=0
    for ordinal in range((bits+6)//7):
        _need(at<end<=len(raw),'integer-boundary')
        byte=raw[at];at+=1;value|=(byte&127)<<(7*ordinal)
        _need(value<1<<bits,'integer-overflow')
        if byte<128:
            _need(ordinal==0 or byte!=0,'integer-noncanonical')
            return value,at,at-start
    raise FirstUseError('integer-length')


def _opcode_order(dependencies):
    _need(all(set(ds)<=dependencies.keys() for ds in dependencies.values()),'undefined-opcode')
    done=[]
    while len(done)<len(dependencies):
        ready=[op for op,ds in dependencies.items() if op not in done and set(ds)<=set(done)]
        _need(bool(ready),'first-use-cycle')
        done.append(min(ready))
    return done


def _route_rows(prefixes,side,width):
    _need(type(prefixes) is tuple and len(prefixes)==4,'prefix-count')
    _need(type(side) is int and type(width) is int and 64<=side<=2048
          and 8<=width<=128 and side%8==width%8==0 and 2*width+8<=side,'geometry')
    rows=[]
    packages=[]
    definitions=[]
    for sector,raw in enumerate(prefixes):
        _need(type(raw) is bytes and 64<=len(raw)<=32768
              and len(raw)*8<=width*(side-width),'prefix-bound')
        try:
            admitted=decode_observed_route_v2(raw,side,width,sector)
        except DecoderError as error:
            raise FirstUseError('route') from error
        packages.append(admitted.package.encoded)
        definitions.append(admitted.definitions)
        at=64;frames=[];defs=[];examples=[];package_at=None
        while at<len(raw):
            _need(len(frames)<48,'frame-count')
            stage,kind=raw[at:at+2]
            rid=_number(raw,at+2,2);size=_number(raw,at+4,4)
            end=at+8+size
            _need(end<=len(raw),'frame-bound')
            frames.append([stage,kind,rid,at,8+size])
            p=at+8
            if kind==1:
                defs.append([_number(raw,p,2),p+14,size-14])
            elif kind in (2,3):
                ilen=_number(raw,p+4,4);olen=_number(raw,p+8,4)
                examples.append([_number(raw,p,2),_number(raw,p+2,2),rid,p+12,ilen,p+12+ilen,olen])
            elif kind==5:
                package_at=p
            at=end
        _need(len(frames)==48 and len(defs)==12 and len(examples)==33 and package_at is not None,'route-coverage')
        rows.append(dict(sector_id=sector,**_identity(raw),package_offset=package_at,
                         definition_spans=defs,frame_spans=frames,example_spans=examples))
    _need(all(p==packages[0] for p in packages) and all(d==definitions[0] for d in definitions),'route-agreement')
    return rows,packages[0],definitions[0]


def _scan(raw,definitions):
    layouts=[];at=0
    for lid,size in enumerate((32,8,64,16,32,12)):
        start=at;n=_number(definitions[4],at,2);at+=2;pairs=[];end=0
        _need(1<=n<=32,'layout-count')
        for _ in range(n):
            pos=_number(definitions[4],at,2);width=_number(definitions[4],at+2,2);at+=4
            _need(pos==end and width>0,'layout-partition');end+=width;pairs.append([pos,width])
        _need(end==size,'layout-size');layouts.append([lid,start,pairs])
    start=at;n=_number(definitions[4],at,2);at+=2;pairs=[]
    _need(n==2,'compact-descriptor-layout')
    for _ in range(n):
        pairs.append([_number(definitions[4],at,2),_number(definitions[4],at+2,2)]);at+=4
    _need(pairs==[[0,1],[1,0]],'compact-descriptor-layout')
    layouts.append([6,start,pairs])
    fields=[];tables=[];recipes=[];descriptors=[];nodes=[];calls=[];node_fields=[]
    def header(lid,owner,item,start):
        for index,(offset,width) in enumerate(layouts[lid][2]):
            fields.append([lid,owner,item,index,start+offset,width,layouts[lid][1]+2+4*index])
    header(2,0,0,0)
    table_map={};recipe_map={};node_map={};input_map={};output_map={}
    at=64
    nt=_number(raw,18,2);nr=_number(raw,16,2)
    _need(nt<=256 and nr<=256 and len(raw)<=32768 and raw[8:10]==b'\0\2','package-bound')
    for _ in range(nt):
        tid=_number(raw,at,2);size=_number(raw,at+12,4)
        row=[tid,at,16+size,at+16,size,raw[at+2],_number(raw,at+4,4),_number(raw,at+8,4)]
        header(3,tid,0,at);tables.append(row);table_map[tid]=row;at+=16+size
    for _ in range(nr):
        start=at;rid=_number(raw,at,2);ni=_number(raw,at+4,2);no=_number(raw,at+6,2)
        nn=_number(raw,at+8,4);size=_number(raw,at+28,4)
        recipe_end=start+size;_need(recipe_end<=len(raw),'recipe-boundary')
        _need(nn<=4096 and len(nodes)+nn<=4096,'node-bound')
        row=[rid,start,size,ni,no,nn];recipes.append(row);recipe_map[rid]=row
        header(4,rid,0,start);at+=32;values={};outputs={}
        for io,count in enumerate((ni,no)):
            _need(count<=4096,'descriptor-bound')
            for index in range(1,count+1):
                begin=at;_need(at<recipe_end,'descriptor-boundary');kind=raw[at]
                width,at,length=_uleb(raw,at+1,recipe_end,32)
                _need(kind in (0,1,2,3,5),'descriptor-type')
                d=[rid,io,index,index,begin,kind,width,1]
                descriptors.append(d)
                for field,offset,span in ((0,begin,1),(1,begin+1,length)):
                    fields.append([6,rid,index+io*65536,field,offset,span,layouts[6][1]+2+4*field])
                (values if io==0 else outputs)[index]=(begin,at-begin)
                (input_map if io==0 else output_map)[rid,index]=d
        for index in range(1,nn+1):
            start_node=at;_need(at<recipe_end,'node-boundary');op=raw[at]&31;ty=raw[at]>>5
            _need(1<=op<=25 and 0<=ty<=5,'node-convention')
            shape=definitions[5][(op-1)*6:op*6]
            arity,auxbytes,immbytes=shape[1],shape[3],shape[4]
            _need(arity<=3 and auxbytes in (0,3) and immbytes in (0,10),'node-shape')
            node_fields.append([rid,index,0,0,at,1]);at+=1
            field=at;width,at,length=_uleb(raw,at,recipe_end,32)
            node_fields.append([rid,index,1,0,field,length]);args=[]
            for ordinal in range(1,arity+1):
                field=at;value,at,length=_uleb(raw,at,recipe_end,16)
                _need(value in values,'late-argument')
                args.append([value,field,*values[value]])
                node_fields.append([rid,index,2,ordinal,field,length])
            aux=[];imm=[]
            if auxbytes:
                field=at;target,at,length=_uleb(raw,at,recipe_end,16)
                if op==2:
                    _need(target in table_map,'missing-table');t=table_map[target];span=(t[1],t[2])
                elif op==5:
                    _need(target in outputs,'missing-output');span=outputs[target]
                else:
                    _need(op==22 and target<rid and target in recipe_map,'late-callee')
                    t=recipe_map[target];span=(t[1],t[2]);calls.append([rid,index,target])
                aux=[target,field,*span];node_fields.append([rid,index,3,0,field,length])
            if immbytes:
                field=at;immediate,at,length=_uleb(raw,at,recipe_end,64)
                imm=[field,immediate];node_fields.append([rid,index,4,0,field,length])
            _need(at-start_node<=shape[5],'node-partition')
            node=[rid,index,ni+index,start_node,at-start_node,op,ty,width,args,aux,imm]
            nodes.append(node);node_map[rid,index]=node;values[ni+index]=(start_node,at-start_node)
        _need(at==start+size,'recipe-partition')
    _need(at==len(raw) and len(fields)<=65536,'package-partition')
    return dict(layout_rows=layouts,field_rows=fields,table_rows=tables,recipe_rows=recipes,
                descriptor_rows=descriptors,node_rows=nodes,node_field_rows=node_fields,call_rows=calls),node_map,input_map,output_map


def _grounding(value,node_map,inputs,outputs):
    teaching=[n for n in value['node_rows'] if n[0]==211]
    _need(bool(teaching),'teaching-absent')
    ni=next(r[3] for r in value['recipe_rows'] if r[0]==211)
    emits=[n for n in teaching if n[5]==5]
    def anchor(value_id):
        if value_id<=ni:
            _need((211,value_id) in inputs,'input-anchor');return [0,value_id]
        n=node_map.get((211,value_id-ni));_need(n is not None,'node-anchor')
        if n[5]==1:return [1,n[1]]
        if n[5]==2:return [2,n[9][0]]
        if n[5]==25:return [4,n[1]]
        slots=[]
        for e in emits:
            if e[8][0][0]==value_id and e[10][1]==0:
                slot=e[9][0];d=outputs[211,slot]
                if (d[5],d[6])==(n[6],n[7]):slots.append(slot)
        _need(bool(slots),'unobserved-intermediate')
        return [3,min(slots)]
    copies=[[n[1],n[8][0][0],n[9][0],n[10][1]] for n in emits if n[8][0][0]<=ni]
    _need(copies==[[70,1,33,0],[71,2,33,8],[72,4,34,0],[73,4,34,3]],'emit-literal-anchors')
    literal=[];deps={op:set() for op in range(1,26)};witness={op:[] for op in deps}
    for n in teaching:
        op=n[5];witness[op].append(n[1])
        if op==5:continue
        args=[anchor(a[0]) for a in n[8]];result=anchor(n[2])
        literal.append([n[1],op,args,result])
        if result[0]==3:deps[op].add(5)
        for kind,_ in args:
            if kind in (1,2,4):deps[op].add({1:1,2:2,4:25}[kind])
        if op==22:
            pending=[n[9][0]];seen=set()
            while pending:
                rid=pending.pop()
                if rid in seen:continue
                seen.add(rid)
                for child in value['node_rows']:
                    if child[0]!=rid:continue
                    deps[22].add(child[5])
                    if child[5]==22:pending.append(child[9][0])
    # The second explicit loop probe supplies a non-identity accumulator path.
    for n in value['node_rows']:
        if n[0]==213:deps[22].add(n[5])
    deps[25].update((1,5))
    _need(all(witness.values()),'opcode-coverage')
    order=_opcode_order(deps)
    return dict(literal_rows=literal,copy_rows=copies,
        opcode_rows=[[op,6*(op-1),sorted(deps[op]),witness[op]] for op in deps],
        opcode_order=order,type_rows=[[ty,150+10*ty,10] for ty in range(6)])


def _uses(value,routes,definitions):
    nodes=value['node_rows'];recipe_ids={r[0] for r in value['recipe_rows']};table_ids={t[0] for t in value['table_rows']}
    def closure(root):
        reached=set();tables=set();pending=[root]
        while pending:
            rid=pending.pop();_need(rid in recipe_ids,'undefined-recipe')
            if rid in reached:continue
            reached.add(rid)
            for n in nodes:
                if n[0]!=rid:continue
                if n[5]==2:tables.add(n[9][0])
                if n[5]==22:pending.append(n[9][0])
        return sorted(reached),sorted(tables)
    roots=[];conventions=[]
    for fact,parents in enumerate(_DEPS,1):
        examples=[e for e in routes[0]['example_spans'] if e[0]==fact]
        _need(examples and all(p<fact for p in parents),'fact-first-use')
        conventions.append([fact,list(parents),len(definitions[fact-1]),[e[2] for e in examples]])
        for e in examples:
            if (fact,e[1]) not in roots:roots.append((fact,e[1]))
        if fact==8:roots.append((8,108))
        if fact==10:roots.append((10,_number(definitions[9],8,2)))
    roots.extend((0,rid) for rid in (30,109,113,120,123,127,202))
    uses=[[fact,rid,*closure(rid)] for fact,rid in roots]
    reached=set(r for row in uses for r in row[2]);tables=set(t for row in uses for t in row[3])|{17}
    _need(reached==recipe_ids and tables==table_ids,'unused-definition')
    _need({n[6] for n in nodes}|{d[5] for d in value['descriptor_rows']}==set(range(6)),'unused-type')
    return dict(use_rows=uses,convention_rows=conventions)


def _adapter_rows(package,definitions):
    parsed=decode_recipe_package_v2(package,8)
    rows=[]
    for block,base in enumerate((134,325)):
        for lane in range(24):
            segments=([[7,base+8*lane,8]] if lane<23
                      else [[7,base+184,7],[8,15,1]])
            source=b''.join(definitions[f-1][at:at+n] for f,at,n in segments)
            output=[8,112+216*block+9*lane,9]
            expected=definitions[7][output[1]:output[1]+9]
            result=evaluate_recipe_v2(parsed,108,(source,))
            _need(result.status==0 and result.outputs==(expected,),'whole-unit-encoder-use')
            rows.append([8,108,block,lane,segments,output])
    return rows


def build_first_use_v2(prefixes, *, side, width):
    routes,package,definitions=_route_rows(prefixes,side,width)
    value,node_map,inputs,outputs=_scan(package,definitions)
    value.update(_grounding(value,node_map,inputs,outputs))
    value.update(_uses(value,routes,definitions))
    value['adapter_rows']=_adapter_rows(package,definitions)
    table=next(t for t in value['table_rows'] if t[0]==17)
    index=(side-2*width)//8
    _need(table[5:]==[0,8,256] and index<table[7],'mapping-table-use')
    value['mapping_use']=[9,17,index,table[3]+index,package[table[3]+index],0,464]
    value.update(schema='golden-board.m2-first-use/v2',scope='finite-carried-convention-coverage-development',
                 inputs=dict(side=side,shell_width=width,package=_identity(package)),route_rows=routes)
    _literal_constraints(prefixes[0],value)
    value['summary']=dict(result='pass',route_count=4,package_bytes=len(package),
        field_count=len(value['field_rows']),node_count=len(value['node_rows']),
        constant_count=sum(bool(n[10]) for n in value['node_rows']),table_count=len(value['table_rows']),
        recipe_count=len(value['recipe_rows']),opcode_count=len(value['opcode_rows']),
        literal_count=len(value['literal_rows']),copy_count=len(value['copy_rows']))
    raw=canonical_manifest.serialize_manifest(value)
    _need(len(raw)<=_LIMIT,'output-bound')
    return raw


def _literal_constraints(prefix,value):
    def chunks(recipe,io,start):
        values={}
        for d in value['descriptor_rows']:
            if d[0]!=recipe or d[1]!=io:continue
            size=d[6] if d[5]==3 else (d[6]+7)//8
            _need(start+size<=len(prefix),'literal-bound')
            values[d[2]]=(prefix[start:start+size],d[5]);start+=size
        return values
    for example in value['route_rows'][0]['example_spans']:
        if example[2] not in (602,603):continue
        ins=chunks(211,0,example[3]);outs=chunks(211,1,example[5])
        for _,source,destination,offset in value['copy_rows']:
            raw,kind=ins[source];target,_=outs[destination]
            _need(kind==3 or offset%8==0,'literal-copy-alignment')
            byte_at=offset if kind==3 else offset//8
            _need(target[byte_at:byte_at+len(raw)]==raw,'literal-copy')
        _need(outs[1][0]==b'\0\0','literal-success')
    failure=next((e for e in value['route_rows'][0]['example_spans'] if e[1]==212),None)
    program=[n for n in value['node_rows'] if n[0]==212]
    _need(failure is not None and failure[4]==0 and failure[6]==2
          and prefix[failure[5]:failure[5]+2]==b'\0\4','literal-failure')
    _need(len(program)==4 and [n[5] for n in program]==[1,5,25,5]
          and program[0][10][1]==7 and program[1][8][0][0]==1
          and program[1][9][0]==2 and program[1][10][1]==0
          and program[2][10][1]==4 and program[3][8][0][0]==3
          and program[3][9][0]==1 and program[3][10][1]==0,'literal-suppression-graph')


def validate_first_use_v2(raw,prefixes,*,side,width):
    _need(type(raw) is bytes and len(raw)<=_LIMIT,'evidence-bound')
    try:
        canonical_manifest.validate_canonical_manifest(raw)
    except canonical_manifest.ManifestError as error:
        raise FirstUseError('canonical-evidence') from error
    _need(raw==build_first_use_v2(prefixes,side=side,width=width),'coverage-mismatch')
