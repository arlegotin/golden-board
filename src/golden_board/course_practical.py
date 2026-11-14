"""Literal practical teaching, author-time truth and actual-byte binding validation."""
from copy import deepcopy
import hashlib
import tomllib
import chess

from .course_author import CourseAuthor,compile_group,passive_reachable
from .course_generic import add_numeric_glyphs,number_glyph
from .practical_state import evaluate,history,move_row,REASONS
from .practical_cases import practical_queries,move,observe,claim,CYCLE,PROMO,EP,RIGHTS_OK,KING_BACK
from .document import decode_document
from .history_segments import HistorySegments
from .course_move_packing import packing_groups
from .source_game import cell_index

ROWS,COLS=23,26
MODES={'observe':1,'attempt':2,'compare':3,'material':4,'record':5}
KINDS={'move':1,'claim':2,'resign':3,'agree':4}

def digits(value,width=4):
    if type(value) is not int or not 0<=value<10**width:raise ValueError('Finite example exceeds its declared display width.')
    return [number_glyph(int(c)) for c in str(value).zfill(width)]

def bit(value):return 1 if value else 2
def _grid(frame,values,x):
    for y in range(8):frame[y*COLS+x:y*COLS+x+8]=values[y*8:y*8+8]

def _ep(value):return [bit(value is not None),number_glyph(0 if value is None else value//8),number_glyph(0 if value is None else value%8)]

def _panel(frame,state,x,missing=()):
    if state is None:return
    values=[[3+state['side']],[bit(v) for v in state['rights']],_ep(state['ep']),_ep(state['key_ep']),
        digits(state['clock']),digits(state['repeat']),[bit(state['check'])],digits(len(state['legal'])),
        [bit(v) for v in state['eligible']],[bit(state['closed'])],[number_glyph(REASONS.index(state['reason']))],
        [bit(state['score'] is not None),0 if state['score'] is None else 10+state['score']]]
    for i,vs in enumerate(values):
        base=(10+i)*COLS+x;frame[base:base+2]=digits(i+1,2)
        if i+1 not in missing:frame[base+3:base+3+len(vs)]=vs

def render(spec,result=None,*,verdict=None):
    """Fixed output extent independent of truth; labels are inert numeric fields."""
    frame=[0]*(ROWS*COLS);op=spec['op'];frame[8*COLS]=number_glyph(MODES[op]);frame[8*COLS+1]=5
    frame[22*COLS]=number_glyph(MODES[op]);frame[22*COLS+1]=0 if verdict is None else 6 if verdict else 7
    if op=='material':
        known=evaluate(spec);_grid(frame,known['occupancy'],0)
        if result:
            available=result['classification']=='common-dead'
            frame[9*COLS:9*COLS+2]=[bit(available),bit(True) if available else 0]
        return frame
    missing=(6,7,8,9,10,11,12) if op=='observe' else (4,6,7,8,9,10,11,12) if op=='compare' else ()
    before=history(spec.get('prefix',''))[0 if op=='record' else -1];_grid(frame,before['occupancy'],0);_panel(frame,before,0,missing)
    if op=='compare':
        other=history(spec['other'])[-1];_grid(frame,other['occupancy'],9);_panel(frame,other,9,missing)
    if op=='attempt':
        kind=spec['kind'];frame[8*COLS+2]=number_glyph(KINDS[kind])
        if kind=='move':
            try:row=move_row(spec['move'])
            except ValueError:
                # Invalid promotion suffix: preserve coordinate fields and a
                # distinct out-of-domain choice, without repairing the request.
                row=move_row(spec['move'][:4])+[5];row=row[:4]+[5]
            frame[8*COLS+4:8*COLS+9]=[number_glyph(n) for n in row]
        elif kind in ('claim','resign'):
            actor=spec['actor'];frame[8*COLS+4]=3+actor if type(actor) is int and actor in (0,1) else 7
            if kind=='claim':frame[8*COLS+6]=number_glyph({'threefold':1,'fifty-move':2}.get(spec['reason'],3))
        else:
            consents=spec['consents'];frame[8*COLS+4:8*COLS+4+len(consents)]=[3+n if type(n) is int and n in (0,1) else 7 for n in consents]
            frame[8*COLS+8]=number_glyph(len(consents))
    if op=='record':
        frame[8*COLS+3:8*COLS+7]=digits(spec['length']);frame[8*COLS+8:8*COLS+12]=digits(spec['ply'])
        frame[8*COLS+13]=10+spec['score']
        frame[8*COLS+18:8*COLS+22]=digits(spec.get('record_id',0))
    frame[8*COLS+14:8*COLS+18]=digits(spec.get('history_id',0))
    if op=='compare':frame[8*COLS+20:8*COLS+24]=digits(spec.get('other_history_id',0))
    if result is None:return frame
    frame[9*COLS]=bit(result['accepted']);after=result['after']
    if after is not None and op!='compare':_grid(frame,after['occupancy'],9);_panel(frame,after,9)
    if op=='compare':
        frame[9*COLS+2]=bit(result['equal_key'])
        frame[9*COLS+4:9*COLS+7]=_ep(result['before']['key_ep'])
        frame[9*COLS+9:9*COLS+12]=_ep(result['after']['key_ep'])
    if op=='record':
        frame[9*COLS+2]=bit(result['complete'])
        known=result['record_cause']!='unspecified'
        frame[9*COLS+4:9*COLS+6]=[bit(known),number_glyph(1) if known else 0]
        frame[9*COLS+6:9*COLS+10]=digits(result['available'])
    if result.get('accepted') and result.get('move_probe'):
        _grid(frame,[5 if i in result['move_probe']['new_piece_control'] else 0 for i in range(64)],18)
    return frame

def rival(spec,result,kind):
    r=deepcopy(result)
    if kind=='material':r['classification']='outside-profile' if r['classification']=='common-dead' else 'common-dead'
    elif kind=='equal_key':r['equal_key']=not r['equal_key']
    elif kind=='complete':r.update(complete=True,accepted=True,after=history(spec['prefix'])[-1])
    elif kind=='record_cause':r['record_cause']='checkmate'
    elif kind=='promotion':
        if spec['op']=='record':
            m=move_row(spec['prefix'].split()[-1]);target=m[2]*8+m[3]
            r['after']['occupancy'][target]=32 if r['after']['occupancy'][target]<38 else 38
        else:
            alternative={**spec,'move':spec['move'][:4]+('n' if spec['move'][4:]!='n' else 'q')}
            r=evaluate(alternative)
    elif kind=='rook':
        text=spec['move'];white=text.startswith('e1');short=text[2]=='g'
        origin=(63 if short else 56) if white else (7 if short else 0)
        target=(61 if short else 59) if white else (5 if short else 3)
        r['after']['occupancy'][origin]=35 if white else 41;r['after']['occupancy'][target]=0
    elif kind=='ep':
        row=move_row(spec['move']);captured=(row[0]*8+row[3]);r['after']['occupancy'][captured]=r['before']['occupancy'][captured]
    elif kind=='rights':r['after']['rights']=[True]*4
    elif kind=='reason':r['after']['reason']='stalemate' if r['after']['reason']=='checkmate' else 'checkmate'
    elif kind=='closed':r['after']['closed']=not r['after']['closed']
    elif kind=='repeat':r['after']['repeat']+=1
    elif kind=='clock':r['after']['clock']=r['before']['clock']+1
    elif kind=='score':r['after']['score']=1-r['after']['score']
    elif kind=='side':r['after']['side']=1-r['after']['side']
    elif kind=='accepted':
        r['accepted']=not r['accepted']
        if not r['accepted']:r['after']=deepcopy(r['before'])
        elif spec['kind']=='move' and r.get('castle_probes'):
            r['after']['occupancy']=r['castle_probes'][-1]['occupancy'];r['after']['side']=1-r['before']['side']
        elif spec['kind'] in ('claim','agree','resign'):
            reason='agreement' if spec['kind']=='agree' else 'resignation' if spec['kind']=='resign' else 'threefold'
            r['after'].update(closed=True,reason=reason,score=2 if spec['kind']!='resign' else 0,legal=[],eligible=[False,False])
    else:raise ValueError('Undeclared rival kind.')
    if render(spec,r)==render(spec,result):raise ValueError('Invisible rival: '+kind)
    return r

def groups(root):
    queries=practical_queries(root);result=[]
    for family in ('T4','T5','T6','T7','T8','T9','T10'):
        family_queries=[q for q in queries if q['family']==family]
        for start in range(0,len(family_queries),6):
            qs=[]
            for source in family_queries[start:start+6]:
                q=deepcopy(source);work=evaluate(q['worked_input']);expected=evaluate(q['input'])
                wrong=rival(q['worked_input'],work,q['rival_kind']);other=rival(q['input'],expected,q['rival_kind'])
                options=[expected,other] if len(result)%2==0 else [other,expected]
                q.update(worked_expected=work,expected=expected,worked_rival=wrong,options_data=options,correct=options.index(expected))
                q['worked']=[render(q['worked_input'],work,verdict=True)]
                for v in q['worked_variants']:q['worked'].append(render(v,evaluate(v),verdict=True))
                q['contrast']=[render(q['worked_input'],wrong,verdict=False),render(q['worked_input'],work,verdict=True)]
                q['options']=[render(q['input'],v) for v in options];qs.append(q)
            result.append({'id':family+'-'+str(start//6+1),'rows':ROWS,'cols':COLS,'queries':qs})
    return result+packing_groups(root)

def _history_page(author,prefix,ident,full_keys=False):
    states=history(prefix);frames=[];moves=prefix.split()
    for i,state in enumerate(states):
        frame=render(observe(''),None);_grid(frame,state['occupancy'],0);_panel(frame,state,0)
        frame[9*COLS+2:9*COLS+6]=digits(i)
        # The common initial state is stored once. The directory identifies its
        # carrying trace; subsequent frames display the same input history ID.
        if i:frame[9*COLS+18:9*COLS+22]=digits(ident)
        if i:frame[8*COLS+4:8*COLS+9]=[number_glyph(v) for v in move_row(moves[i-1])]
        frames.append(frame)
    initial=author.frame(frames[0],ROWS,COLS)
    key_rows=[]
    for i in (range(len(states)) if full_keys else (len(states)-1,)):
        state=states[i]
        ep=state['key_ep'];key_rows += [i,initial,i,state['side'],*map(int,state['rights']),int(ep is not None),0 if ep is None else ep//8,0 if ep is None else ep%8,state['repeat']]
    data=[author.table(key_rows,12),author.table([n for i in states[-1]['occurrences'] for n in (len(states)-1,i)],2)]
    if moves:data.append(author.table([v for text in moves for v in move_row(text)],5))
    legal=states[-1]['legal']
    # The explicit count0 in the panel is the complete empty domain; v1 tables
    # are nonempty, so an empty reply table would misrepresent the grammar.
    if legal:data.append(author.table([v for text in legal for v in move_row(text)],5))
    trace=author.trace(frames,ROWS,COLS,data=data);label='history-'+str(trace)
    node=author.labels[label] if label in author.labels else author.page(label,trace,trace=True)
    return node,frames

def _probe_frames(spec):
    """Complete literal probe diagrams and attacker rows, without allocating records."""
    result=evaluate(spec);frames=[];data=[]
    for probe in result.get('castle_probes',[]):
        f=render(spec);_grid(f,probe['occupancy'],9)
        _grid(f,[5 if i in probe['enemy_control'] else 0 for i in range(64)],18)
        f[22*COLS:22*COLS+4]=[number_glyph(6),number_glyph(probe['stage']),bit(bool(probe['attackers'])),number_glyph(probe['king']%8)]
        frames.append(f)
        data += [[probe['stage'],probe['king'],s] for s in probe['attackers']]
    if result.get('move_probe'):
        probe=result['move_probe'];f=render(spec);_grid(f,probe['occupancy'],9)
        _grid(f,[5 if i in probe['attackers'] else 0 for i in range(64)],18)
        f[22*COLS:22*COLS+3]=[number_glyph(7),number_glyph(0),bit(probe['king_attacked'])];frames.append(f)
        data += [[3,probe['king'],s] for s in probe['attackers']]
    return frames,data

def _probe_page(author,spec):
    frames,data=_probe_frames(spec)
    if not frames:return None,None
    refs=[author.table([v for row in data for v in row],3)] if data else []
    trace=author.trace(frames,ROWS,COLS,data=refs);label='probe-'+str(trace)
    return author.labels[label] if label in author.labels else author.page(label,trace,trace=True),frames

def _calibration_specs(root):
    qs=practical_queries(root);ids={s['prefix']:s['history_id'] for q in qs for s in [q['worked_input'],q['input'],*q['worked_variants']] if 'prefix' in s}
    result=[move('','e2e4'),move('e2e4','e7e5'),*[move(PROMO,'b7a8'+s) for s in 'qrbn'],
        *[move(PROMO+' b7a8q','g2h1'+s) for s in 'qrbn'],
        observe(RIGHTS_OK),observe(KING_BACK),observe(EP),observe(EP+' '+CYCLE),
        observe(CYCLE),observe(CYCLE*2),claim(CYCLE*2,0),
        next(q['worked_input'] for q in qs if q['id']=='recorded_score_unspecified_cause')]
    schemas={(s['op'],s.get('kind')) for s in result};extra=[]
    for q in qs:
        s=q['worked_input'];key=(s['op'],s.get('kind'))
        if key not in schemas:extra.append(dict(s));schemas.add(key)
    result=result[:-1]+extra+result[-1:]
    for s in result:
        if 'prefix' in s:s['prefix']=' '.join(s['prefix'].split());s['history_id']=ids[s['prefix']]
    return result

def _record_page(author,spec):
    """Same three-column move and one-cell score tables as the anthology.

    The visible ordinal and carried directory associate a query with these exact
    records. Literal full playback remains separate from move data.
    """
    states=history(spec['prefix']);moves=spec['prefix'].split();frames=[];values=[]
    for text in moves:
        r=move_row(text);values += [r[0]*8+r[1],r[2]*8+r[3],r[4]]
    refs=[author.table(values,3),author.table([spec['score']],1)]
    if spec['length']!=len(moves):refs.append(author.table([spec['length']],1))
    for i,state in enumerate(states):
        f=render(spec);_grid(f,state['occupancy'],0);_panel(f,state,0)
        f[8*COLS+8:8*COLS+12]=digits(i)
        f[9*COLS:9*COLS+2]=[bit(spec['length']==len(moves)),bit(i==len(moves))]
        if i:
            row=move_row(moves[i-1]);f[22*COLS+4:22*COLS+9]=[number_glyph(v) for v in row]
            f[9*COLS+12:9*COLS+15]=digits(row[0]*8+row[1],3)
            f[9*COLS+16:9*COLS+19]=digits(row[2]*8+row[3],3)
            f[9*COLS+20]=number_glyph(row[4])
        frames.append(f)
    trace=author.trace(frames,ROWS,COLS,data=refs)
    return author.page('record-'+str(spec['record_id']),trace,trace=True),frames,refs

def _reply_frames(prefix,history_id):
    frames=[]
    for text in history(prefix)[-1]['legal']:
        request={**move(prefix,text),'history_id':history_id}
        frames += [render(request),render(request,evaluate(request),verdict=True)]
    return frames

def _decoded_frames(document,node):
    page=document['records'][node];r=document['records'][page['display']]
    if page['display_kind']==0:return [r['cells']]
    f=list(document['records'][r['initial']]['cells']);out=[f[:]]
    for step in r['steps']:
        for i,v in step:f[i]=v
        out.append(f[:])
    return out

def _table_signature(record):return (record['rows'],record['cols'],record['values'])

def _binding(case,q,digest):
    return {'case':case['id'],'query':q['id'],'document_sha256':digest,'state':'authored',
        **{role:case[role] for role in ('worked','contrast','practice','passive','success','failure')},
        **{role+'_steps':q[role+'_steps'] for role in ('worked','contrast','practice','passive')},'prediction':case['practice']}

def build_practical(root):
    author=CourseAuthor();add_numeric_glyphs(author);gs=groups(root);cases=[];contexts={};extra_frames={};probes={};records={};directory=[];replies={}
    calibration_frames=[]
    for s in _calibration_specs(root):calibration_frames += [render(s),render(s,evaluate(s),verdict=True)]
    calibration=author.page('calibration',author.trace(calibration_frames,ROWS,COLS),trace=True)
    history_ids={s[k]:s['history_id' if k=='prefix' else 'other_history_id'] for g in gs for q in g['queries'] for s in [q['worked_input'],q['input'],*q['worked_variants']] for k in ('prefix','other') if k in s}
    key_prefixes={s[k] for g in gs for q in g['queries'] if q['family']=='T8' for s in [q['worked_input'],q['input'],*q['worked_variants']] for k in ('prefix','other') if k in s}
    forest=HistorySegments(author,history_ids,key_prefixes);extra_frames.update(forest.node_frames())
    record_specs={s['record_id']:s for g in gs for q in g['queries'] for s in [q['worked_input'],q['input'],*q['worked_variants']] if s['op']=='record'}
    for ident,spec in sorted(record_specs.items()):
        node,frames,refs=_record_page(author,spec);records[str(ident)]=node;extra_frames[node]=frames
        directory += [ident,node,refs[0],refs[1],spec['length'],len(spec['prefix'].split()),spec['score']]
    directory_table=author.table(directory,7)
    directory_node=author.page('record-directory',author.trace([render(_calibration_specs(root)[-1])],ROWS,COLS,data=[directory_table]),trace=True)
    extra_frames[directory_node]=[render(_calibration_specs(root)[-1])]
    author.record(calibration)['links'].extend([directory_node,*records.values()]);author.record(directory_node)['links']=[calibration,*records.values()]
    for node in records.values():author.record(node)['links']=[directory_node,calibration]
    for group in gs:
        case=compile_group(author,group);case['section']=4;cases.append(case)
        for q in group['queries']:
            for spec in [q['worked_input'],q['input'],*q['worked_variants']]:
                if spec['op']=='record':
                    node=records[str(spec['record_id'])]
                    for role in ('worked','passive'):
                        if node not in author.record(case[role])['links']:author.record(case[role])['links'].append(node)
                    if case['worked'] not in author.record(node)['links']:author.record(node)['links'].append(case['worked'])
                for prefix in [spec[k] for k in ('prefix','other') if k in spec]:
                    if prefix not in contexts:
                        node,frames=forest.context(prefix);contexts[prefix]=node;extra_frames[node]=frames
                    node=contexts[prefix]
                    for role in ('worked','passive'):
                        if node not in author.record(case[role])['links']:author.record(case[role])['links'].append(node)
                    if case['worked'] not in author.record(node)['links']:author.record(node)['links'].append(case['worked'])
                if spec['op']=='attempt' and spec['kind']=='move':
                    key=(spec['prefix'],spec['move'])
                    if key not in probes:
                        node,frames=_probe_page(author,spec)
                        if node is not None:probes[key]=node;extra_frames[node]=frames
                    if key in probes:
                        node=probes[key]
                        for role in ('worked','passive'):
                            if node not in author.record(case[role])['links']:author.record(case[role])['links'].append(node)
                        if case['worked'] not in author.record(node)['links']:author.record(node)['links'].append(case['worked'])
            if q['family']=='T4':
                # Show every legal reply's entire literal effect, not only count.
                for spec in [q['worked_input'],q['input'],*q['worked_variants']]:
                    if 'prefix' not in spec:continue
                    reply_frames=_reply_frames(spec['prefix'],history_ids[spec['prefix']])
                    if reply_frames:
                        trace=author.trace(reply_frames,ROWS,COLS);label='all-replies-'+str(trace)
                        node=author.labels[label] if label in author.labels else author.page(label,trace,trace=True);extra_frames[node]=reply_frames
                        replies[spec['prefix']]=node
                        author.record(case['worked'])['links'].append(node);author.record(case['passive'])['links'].append(node);author.record(node)['links']=[case['worked'],case['passive']]
    history_directory=forest.directory_rows(contexts)
    locator_frames=forest.locator_frames() or [calibration_frames[0]]
    history_directory_node=author.page('history-directory',author.trace(locator_frames,ROWS,COLS,data=[author.table(history_directory,6),author.table(forest.segment_rows(),11)]),trace=True)
    author.record(calibration)['links'].append(history_directory_node)
    author.record(history_directory_node)['links']=[calibration,*forest.node_frames()]
    for node in forest.node_frames():author.record(node)['links'].append(history_directory_node)
    extra_frames[history_directory_node]=locator_frames
    roots=[calibration]+[c['worked'] for c in cases]
    for a,b in zip(roots,roots[1:]):author.record(a)['links'].append(b);author.record(b)['links'].append(a)
    cases[0]['frames'][str(calibration)]=calibration_frames
    for node,frames in extra_frames.items():
        c=next((c for c in cases if node in author.record(c['worked'])['links']),cases[0]);c['frames'][str(node)]=frames
    body=author.encode(roots);digest=hashlib.sha256(body).hexdigest();bindings={}
    for c in cases:
        for q in c['queries']:
            for s in q['strata']:bindings.setdefault(s,[]).append(_binding(c,q,digest))
    p={'document':body,'groups':gs,'cases':cases,'bindings':bindings,'contexts':contexts,'roots':roots,'calibration':calibration,
        'records':records,'record_directory':directory_node,'replies':replies,
        'history_ids':history_ids,'history_directory':history_directory_node,'history_segments':forest.describe(),
        'probes':[{'prefix':p,'move':m,'node':n} for (p,m),n in probes.items()],
        'scope':'66 authored practical strata; finite teaching, not recipient confirmation or full course'}
    p['truth']=validate_practical(p,root);return p

def validate_practical(product,root):
    """Recompute semantics and compare the actual serialized packet/relation data."""
    expected_groups=groups(root);d=decode_document(product['document']);reached=passive_reachable(product['document'])
    if product['groups']!=expected_groups:raise ValueError('Practical semantic result/teaching/input differs.')
    if len(product['cases'])!=len(expected_groups):raise ValueError('Missing practical group.')
    expected_bindings={};digest=hashlib.sha256(product['document']).hexdigest();checked=[]
    for group,case in zip(expected_groups,product['cases']):
        a=CourseAuthor();add_numeric_glyphs(a);reference=compile_group(a,group)
        if case['id']!=group['id'] or case['queries']!=reference['queries'] or case['expected']!=reference['expected']:raise ValueError('Wrong practical query binding.')
        for role in ('worked','practice','passive','success','failure'):
            node=case[role]
            if node not in reached or _decoded_frames(d,node)!=reference['frames'][str(reference[role])]:raise ValueError('Wrong actual practical '+role+' frames.')
            page=d['records'][node];ref=a.record(reference[role])
            if any(page[k]!=ref[k] for k in ('shape','choices','accepted')):raise ValueError('Wrong actual practical accepted relation.')
            for key in ('success','failure','passive'):
                expected=case[key] if ref[key]!=65535 else 65535
                if page[key]!=expected:raise ValueError('Wrong actual practical feedback target.')
        for q,b in zip(group['queries'],case['queries']):
            for s in q['strata']:expected_bindings.setdefault(s,[]).append(_binding(case,b,digest))
            checked.append({k:q[k] for k in ('id','strata','worked_input','input','worked_expected','expected','worked_variants','rival_kind')})
    families=tomllib.loads((root/'content/coverage.toml').read_text())['family'][4:11]
    required={s for f in families for s in f['critical_strata']}
    if set(expected_bindings)!=required or product['bindings']!=expected_bindings:raise ValueError('Missing/false practical stratum binding.')
    for c in product['cases']:
        for node,frames in c['frames'].items():
            if int(node) not in reached or _decoded_frames(d,int(node))!=frames:raise ValueError('Wrong carried practical intermediate.')
    required_prefixes={s[k] for g in expected_groups for q in g['queries'] for s in [q['worked_input'],q['input'],*q['worked_variants']] for k in ('prefix','other') if k in s}
    if set(product['contexts'])!=required_prefixes:raise ValueError('Missing coherent practical history.')
    history_ids={s[k]:s['history_id' if k=='prefix' else 'other_history_id'] for g in expected_groups for q in g['queries'] for s in [q['worked_input'],q['input'],*q['worked_variants']] for k in ('prefix','other') if k in s}
    key_prefixes={s[k] for g in expected_groups for q in g['queries'] if q['family']=='T8' for s in [q['worked_input'],q['input'],*q['worked_variants']] for k in ('prefix','other') if k in s}
    if product['history_ids']!=history_ids:raise ValueError('Wrong history operand identity.')
    a=CourseAuthor();add_numeric_glyphs(a)
    forest=HistorySegments(a,history_ids,key_prefixes)
    forest.validate(d,product['contexts'],product['history_directory'],product['history_segments'])
    record_specs={s['record_id']:s for g in expected_groups for q in g['queries'] for s in [q['worked_input'],q['input'],*q['worked_variants']] if s['op']=='record'}
    if set(product['records'])!={str(i) for i in record_specs}:raise ValueError('Missing record operand.')
    expected_directory=[]
    for ident,spec in sorted(record_specs.items()):
        a=CourseAuthor();add_numeric_glyphs(a);_,frames,refs=_record_page(a,spec)
        node=product['records'][str(ident)];actual=d['records'][d['records'][node]['display']]
        if _decoded_frames(d,node)!=frames or [_table_signature(d['records'][r]) for r in actual['data']]!=[_table_signature(a.record(r)) for r in refs]:raise ValueError('Wrong record move/score/length/playback data.')
        expected_directory += [ident,node,actual['data'][0],actual['data'][1],spec['length'],len(spec['prefix'].split()),spec['score']]
    directory=d['records'][d['records'][product['record_directory']]['display']]
    if len(directory['data'])!=1 or _table_signature(d['records'][directory['data'][0]])!=(len(record_specs),7,expected_directory):raise ValueError('Wrong record operand reference directory.')
    expected_probes={}
    for g in expected_groups:
        for q in g['queries']:
            for s in [q['worked_input'],q['input'],*q['worked_variants']]:
                if s['op']=='attempt' and s['kind']=='move':
                    a=CourseAuthor();add_numeric_glyphs(a);node,frames=_probe_page(a,s)
                    if node is not None:expected_probes[(s['prefix'],s['move'])]=(frames,[_table_signature(a.record(i)) for i in a.record(a.record(node)['display'])['data']])
    actual_probes={(p['prefix'],p['move']):p['node'] for p in product['probes']}
    if set(actual_probes)!=set(expected_probes):raise ValueError('Missing explicit move/castling probe.')
    for key,(frames,tables) in expected_probes.items():
        node=actual_probes[key];trace=d['records'][d['records'][node]['display']]
        if _decoded_frames(d,node)!=frames or [_table_signature(d['records'][i]) for i in trace['data']]!=tables:raise ValueError('Wrong carried trial occupancy/attack sources.')
    expected_replies={s['prefix'] for g in expected_groups for q in g['queries'] if q['family']=='T4' for s in [q['worked_input'],q['input'],*q['worked_variants']] if history(s['prefix'])[-1]['legal']}
    if set(product['replies'])!=expected_replies:raise ValueError('Missing complete T4reply effects.')
    for prefix,node in product['replies'].items():
        if _decoded_frames(d,node)!=_reply_frames(prefix,history_ids[prefix]):raise ValueError('Wrong complete reply effects.')
    calibration=[]
    for s in _calibration_specs(root):calibration += [render(s),render(s,evaluate(s),verdict=True)]
    if product['roots'][0]!=product['calibration'] or _decoded_frames(d,product['calibration'])!=calibration:raise ValueError('Missing practical calibration.')
    return {'strata':len(required),'queries':checked,'histories':len(required_prefixes),'passive_without_response':True,
        'scope':'Finite authored T4–T10 truth, not recipient discovery/understanding or complete-product qualification'}
