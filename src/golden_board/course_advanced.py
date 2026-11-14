"""Literal remaining-course teaching and actual serialized conformance.

All subject computation is author-time. Player consumes only v1 inert records.
"""
from copy import deepcopy
from collections import defaultdict
from functools import partial
import hashlib,tomllib
import chess
from .course_author import CourseAuthor,compile_group,passive_reachable
from .course_generic import add_numeric_glyphs,number_glyph
from .course_practical import (digits,bit,_grid,_panel,_history_page,_probe_page,_probe_frames,
    _decoded_frames,_binding,render as practical_render)
from .practical_cases import observe,move
from .practical_state import history,move_row,REASONS
from .advanced_cases import queries,evaluate,MODES,KINDS,signature,cell
from .anthology_input import load_anthology
from .document import decode_document
from .history_segments import HistorySegments

ROWS,COLS=23,26

def render(spec,result=None,*,verdict=None,target=None,root=None):
    f=[0]*(ROWS*COLS)
    known=evaluate(spec,root) if result is None else result
    _grid(f,known['before'],0)
    if result is not None and result['after'] is not None:_grid(f,result['after'],9)
    selected=spec.get('source',spec.get('pawn'))
    marks=result['marks'] if result is not None else [] if selected is None else [selected]
    _grid(f,[5 if i in marks else 0 for i in range(64)],18)
    f[8*COLS:8*COLS+2]=digits(MODES[spec['op']],2)
    f[8*COLS+3:8*COLS+5]=digits(KINDS.get(spec.get('kind'),0),2)
    if 'side' in spec:f[8*COLS+6]=3+spec['side']
    if selected is not None:f[8*COLS+8:8*COLS+10]=[number_glyph(selected//8),number_glyph(selected%8)]
    if 'file' in spec:f[8*COLS+11]=number_glyph(spec['file'])
    f[8*COLS+14:8*COLS+18]=digits(spec.get('history_id',0))
    f[8*COLS+20:8*COLS+24]=digits(spec.get('other_history_id',0))
    f[9*COLS:9*COLS+4]=digits(spec['context_id'])
    f[9*COLS+5]=bit('prefix' in spec)
    if target is not None:f[9*COLS+8:9*COLS+10]=digits(target+1,2)
    if spec['op'] in ('discovered','escape','effect','routine'):
        kind=spec.get('kind','move');f[9*COLS+12]=number_glyph(('move','claim','resign','agree').index(kind)+1)
        if kind=='move':f[9*COLS+14:9*COLS+19]=[number_glyph(n) for n in move_row(spec['move'])]
        elif kind in ('claim','resign'):
            actor=spec['actor'];f[9*COLS+14]=3+actor if type(actor) is int and actor in (0,1) else 7
            if kind=='claim':f[9*COLS+16]=number_glyph({'threefold':1,'fifty-move':2}.get(spec['reason'],3))
        else:
            consents=spec['consents'];f[9*COLS+14:9*COLS+14+len(consents)]=[3+n if type(n) is int and n in (0,1) else 7 for n in consents]
            f[9*COLS+18]=number_glyph(len(consents))
    if spec['op']=='anthology':
        f[9*COLS+12:9*COLS+14]=digits(spec['ordinal'],2)
        f[9*COLS+18:9*COLS+22]=digits(spec['ply'])
    if result is not None:
        if len(result['values'])>24:raise ValueError('Explicit result exceeds its visible finite field inventory.')
        for i,v in enumerate(result['values']):
            base=(10+i%12)*COLS+(13 if i>=12 else 0)
            f[base:base+2]=digits(i+1,2);f[base+3]=bit(v is not None)
            if v is not None:f[base+5:base+9]=digits(v)
    f[22*COLS:22*COLS+4]=[*digits(MODES[spec['op']],2),0,0 if verdict is None else 6 if verdict else 7]
    return f

def rival(result,target,op):
    r=deepcopy(result)
    if op=='proof':
        r['values'][0]=1-r['values'][0];r['values'][1]=1 if r['values'][0] else None
    else:
        value=r['values'][target];r['values'][target]=0 if value is None else None if target in (4,7,8,9) and value==0 else 1 if value==0 else 0
    return r

def groups(root):
    draw=partial(render,root=root);result=[]
    for family in ('T11','T12','T13','T14','T15','T16'):
        rows=[q for q in queries(root) if q['family']==family]
        for start in range(0,len(rows),8):
            qs=[]
            for source in rows[start:start+8]:
                q=deepcopy(source);s=q['worked_input'];work=evaluate(s,root);expected=evaluate(q['input'],root)
                wrong=rival(work,q['target'],s['op']);other=rival(expected,q['target'],q['input']['op'])
                options=[expected,other] if len(result)%2==0 else [other,expected]
                q.update(worked_expected=work,expected=expected,options_data=options,correct=options.index(expected))
                q['worked']=[draw(s,work,verdict=True,target=q['target'])]
                for v in q['worked_variants']:q['worked'].append(draw(v,evaluate(v,root),verdict=True))
                q['contrast']=[draw(s,wrong,verdict=False,target=q['target']),draw(s,work,verdict=True,target=q['target'])]
                q['options']=[draw(q['input'],r,target=q['target']) for r in options]
                if q['options'][0]==q['options'][1]:raise ValueError('Invisible advanced contrast: '+q['id'])
                qs.append(q)
            result.append({'id':family+'-'+str(start//8+1),'rows':ROWS,'cols':COLS,'queries':qs})
    return result

def _state_frame(state,history_id,context_id,ply,action=None):
    f=practical_render(observe(''));_grid(f,state['occupancy'],0);_panel(f,state,0)
    f[9*COLS+2:9*COLS+6]=digits(ply);f[9*COLS+18:9*COLS+22]=digits(context_id)
    f[8*COLS+14:8*COLS+18]=digits(history_id)
    if action and not action.startswith('claim:'):f[8*COLS+4:8*COLS+9]=[number_glyph(v) for v in move_row(action)]
    return f

def _move_values(text):
    row=move_row(text);return [row[0]*8+row[1],row[2]*8+row[3],row[4]]

def _details(author,spec,result,root):
    """Visible literal intermediate pages, plus explicit non-executable tables."""
    op=spec['op'];r=result['detail'];frames=[];tables=[]
    if op=='schedule':
        for i,state in enumerate(r['states']):frames.append(_state_frame(state,spec['history_id'],spec['context_id'],len(spec['prefix'].split())+i,None if not i else r['moves'][i-1]))
        if r['moves']:tables.append(author.table([v for m in r['moves'] for v in _move_values(m)],3))
        tables.append(author.table([spec['context_id'],spec['history_id'],len(spec['prefix'].split()),len(r['moves'])],4))
    elif op=='proof':
        nodes=[];arcs=[];domains=[]
        for node in r['nodes']:
            s=node['state'];parent=node['parent'];role=('attacker','defender','leaf').index(node['role'])
            nodes += [node['id'],0 if parent is None else parent+1,role,s['side'],int(s['closed']),REASONS.index(s['reason']),int(s['score'] is not None),0 if s['score'] is None else s['score'],len(s['legal']),*map(int,s['eligible']),len(node['children']),int(node['resignation_dominated']),0]
            for action in node['domain']:
                domains += [node['id'],2,0,0,0,1 if action=='claim:threefold' else 2] if action.startswith('claim:') else [node['id'],1,*_move_values(action),0]
            action=node['via']
            if parent is not None:
                arcs += [parent,node['id'],2,0,0,0,1 if action=='claim:threefold' else 2] if action.startswith('claim:') else [parent,node['id'],1,*_move_values(action),0]
            f=_state_frame(s,spec['history_id'],spec['context_id'],len(spec['prefix'].split())+_depth(r['nodes'],node),action)
            board=chess.Board(None);board.turn=s['side']==0
            for i,token in enumerate(s['occupancy']):
                if token:
                    board.set_piece_at(chess.square(i%8,7-i//8),chess.Piece((token-32)%6+1,token<38))
            controls=set().union(*(set(board.attacks(i)) for i,p in board.piece_map().items() if p.color!=board.turn))
            _grid(f,[5 if chess.square(i%8,7-i//8) in controls else 0 for i in range(64)],18)
            f[22*COLS:22*COLS+8]=[number_glyph(6),number_glyph(role),*digits(node['id'],3),*digits(0 if parent is None else parent+1,3)]
            frames.append(f)
        tables.append(author.table(nodes,14))
        if arcs:tables.append(author.table(arcs,7))
        if domains:tables.append(author.table(domains,6))
        tables.append(author.table([spec['context_id'],spec['history_id'],spec['winner'],int(r['available']),1,0],6))
    elif op=='anthology':
        indexes=spec['seeks'] or [0,spec['ply']]
        recovered=0
        for i in indexes:
            probe={**spec,'ply':i};event=evaluate(probe,root)
            if event['detail']['accepted']:recovered=i
            # A refused request has no new content. Its last recovered view is
            # still available; keep the literal event rather than skipping it.
            event['after']=r['positions'][recovered]
            frames.append(render(probe,event,verdict=True))
        tables.append(author.table([2,spec['ordinal'],r['entry'],r['trace'],r['plies'],r['score'],r['move_table'],r['score_table'],r['schema_table']],9))
        if spec['seeks']:tables.append(author.table(spec['seeks'],1))
    elif op=='facts' and spec['kind']=='development':
        rows=[]
        for origin,location in r['minor_locations'].items():
            departed=origin in r['departed'];rows += [origin,int(location is not None),0 if location is None else location,int(departed)]
            shown={**result,'values':[origin,int(location is not None),0 if location is None else location,int(departed)],'marks':[origin]}
            frames.append(render(spec,shown,verdict=True))
        tables.append(author.table(rows,4))
    elif op=='facts' and spec['kind']=='alternatives':
        for item in r['alternatives']:
            s={**move(spec['prefix'],item['move']),'history_id':spec['history_id']}
            frames += [practical_render(s),practical_render(s,item,verdict=True)]
        tables.append(author.table([v for m in spec['alternatives'] for v in _move_values(m)],3))
    elif op=='routine':
        stages=((0,),(1,),(2,),(3,4),(5,),(6,7,8),(9,10,11),(12,));visible=set();rows=[]
        for stage in r['ordered_stages']:
            highlighted=stages[stage-1];visible.update(highlighted)
            f=render(spec,result,verdict=True);f[22*COLS+5:22*COLS+7]=digits(stage,2)
            for i in range(len(result['values'])):
                base=(10+i%12)*COLS+(13 if i>=12 else 0)
                if i not in visible:f[base:base+12]=[0]*12
                elif i in highlighted:f[base+11]=5
            if stage<6:_grid(f,[0]*64,9)
            if stage==3:_grid(f,[5 if token==(37 if r['effect']['before']['side']==0 else 43) else 0 for token in result['before']],18)
            if stage==5:_grid(f,[5 if i in {cell(m[2:4]) for m in r['legal']} else 0 for i in range(64)],18)
            frames.append(f);rows += [v for field in highlighted for v in (stage,field+1)]
        tables.append(author.table(rows,2))
    if not frames:return None,None
    trace=author.trace(frames,ROWS,COLS,data=tables)
    return author.page('detail-'+str(spec['context_id']),trace,trace=True),frames

def _depth(nodes,node):
    n=0
    while node['parent'] is not None:
        if not node['via'].startswith('claim:'):n+=1
        node=nodes[node['parent']]
    return n

def _assemble(root):
    author=CourseAuthor();add_numeric_glyphs(author);gs=groups(root);cases=[];extras={};contexts={};details={};proofs={};probes={}
    probe_steps={};escape_frames=[];escape_rows=[];escape_contexts=[];king_rows=[]
    specs={s['context_id']:s for g in gs for q in g['queries'] for s in [q['worked_input'],q['input'],*q['worked_variants']]}
    king_contexts={s['context_id'] for g in gs for q in g['queries']
        if q['id']=='escape_square_safety_with_capture_occupancy'
        for s in [q['worked_input'],*q['worked_variants'],q['input']]}
    calibration_frames=[]
    # General move attempts are introduced in the linked first worked lesson,
    # where the request operands and complete result appear together. Other
    # operation/kind pairs retain a separate introductory calibration pair.
    seen={('effect','move')}
    for g in gs:
        for q in g['queries']:
            for s in [q['worked_input'],*q['worked_variants']]:
                key=(s['op'],s.get('kind'))
                if key in seen:continue
                seen.add(key);calibration_frames += [render(s,root=root),render(s,evaluate(s,root),verdict=True)]
    calibration=author.page('calibration',author.trace(calibration_frames,ROWS,COLS),trace=True);extras[calibration]=calibration_frames
    history_ids={s[k]:s['history_id' if k=='prefix' else 'other_history_id'] for s in specs.values() for k in ('prefix','other') if k in s}
    forest=HistorySegments(author,history_ids);extras.update(forest.node_frames())
    for prefix,ident in sorted(history_ids.items(),key=lambda row:row[1]):
        node,frames=forest.context(prefix);contexts[prefix]=node;extras[node]=frames
    for ident,spec in sorted(specs.items()):
        result=evaluate(spec,root);node,frames=_details(author,spec,result,root)
        if node is not None:
            details[str(ident)]=node;extras[node]=frames
            if spec['op']=='proof':proofs[str(ident)]=node
        if spec['op'] in ('discovered','escape','effect','routine') and spec.get('kind','move')=='move':
            normalized={**move(spec['prefix'],spec['move']),'history_id':spec['history_id']}
            if ident in king_contexts:
                frames,rows=_probe_frames(normalized)
                if len(frames)!=1:raise ValueError('One adjacent-king probe per king request required.')
                step=len(escape_frames);probe_steps[str(ident)]=step;escape_contexts.append(str(ident))
                escape_frames.extend(frames)
                escape_rows.extend([step,*row] for row in rows)
                probe=result['detail']['effect']['move_probe']
                king_rows.append([step,3,probe['king']])
            else:
                node,frames=_probe_page(author,normalized)
                if node is not None:
                    probes[str(ident)]=node;probe_steps[str(ident)]=0;extras[node]=frames
    if escape_frames:
        # Every step identifies its focal king, even with an empty attacker set.
        # Attacker rows extend that same three-value key; no fake safe attacker.
        data=[author.table([v for row in king_rows for v in row],3)]
        if escape_rows:data.append(author.table([v for row in escape_rows for v in row],4))
        trace=author.trace(escape_frames,ROWS,COLS,data=data)
        node=author.page('escape-probes',trace,trace=True);extras[node]=escape_frames
        probes.update({ident:node for ident in escape_contexts})
    for g in gs:
        case=compile_group(author,g);case['section']=5;cases.append(case)
        for q in g['queries']:
            for s in [q['worked_input'],q['input'],*q['worked_variants']]:
                nodes=[contexts[s[k]] for k in ('prefix','other') if k in s]
                nodes += [m[str(s['context_id'])] for m in (details,probes) if str(s['context_id']) in m]
                for node in nodes:
                    for role in ('worked','passive'):
                        if node not in author.record(case[role])['links']:author.record(case[role])['links'].append(node)
                    if case['worked'] not in author.record(node)['links']:author.record(node)['links'].append(case['worked'])
    truth,anthology=load_anthology(root);d=decode_document(anthology);inventory=[]
    for ordinal,entry in enumerate(d['entries'],1):
        trace=d['records'][entry];game=truth['games'][str(truth['canonical_games'][ordinal-1]['source_ordinal'])]
        inventory.append([2,ordinal,entry,entry,len(trace['steps']),game['score'],*trace['data']])
    tables=[author.table([n for row in inventory for n in row],9),author.table(list(hashlib.sha256(anthology).digest()),32)]
    history_table=forest.directory_rows(contexts)
    tables.append(author.table(history_table,6));tables.append(author.table(forest.segment_rows(),11))
    detail_table=[v for ident,node in sorted(details.items(),key=lambda r:int(r[0])) for v in (int(ident),node,author.record(node)['display'])]
    tables.append(author.table(detail_table,3))
    directory_frames=forest.locator_frames() or [calibration_frames[0]]
    directory=author.page('directory',author.trace(directory_frames,ROWS,COLS,data=tables),trace=True);extras[directory]=directory_frames
    author.record(directory)['links']=list(dict.fromkeys([calibration,*forest.node_frames(),*details.values(),*probes.values()]))
    author.record(calibration)['links']=[directory]
    for node in dict.fromkeys([*forest.node_frames(),*details.values(),*probes.values()]):author.record(node)['links'].append(directory)
    roots=[calibration]+[c['worked'] for c in cases]
    for a,b in zip(roots,roots[1:]):author.record(a)['links'].append(b);author.record(b)['links'].append(a)
    for node,frames in extras.items():cases[0]['frames'][str(node)]=frames
    body=author.encode(roots);forest.validate(decode_document(body),contexts,directory,forest.describe(),(2,3))
    digest=hashlib.sha256(body).hexdigest();bindings={}
    for c in cases:
        for q in c['queries']:
            for s in q['strata']:bindings.setdefault(s,[]).append(_binding(c,q,digest))
    return {'document':body,'groups':gs,'cases':cases,'bindings':bindings,'contexts':contexts,
        'history_ids':history_ids,'history_segments':forest.describe(),'details':details,'proofs':proofs,'probes':probes,'probe_steps':probe_steps,'roots':roots,
        'calibration':calibration,'directory':directory,'anthology_inventory':inventory,
        'scope':'48 authored finite T11–T16strata; not recipient evidence, full fit or release.'}

def build_advanced(root):
    product=_assemble(root);product['truth']=validate_advanced(product,root);return product

def validate_advanced(product,root):
    expected=_assemble(root)
    # A deterministic fresh assembly recomputes every native relation and actual
    # frame/table/reference. Hand-derived predicate tests and fresh material review
    # cover shared-author semantic risk; byte parity alone is not that evidence.
    for key in expected:
        if product.get(key)!=expected[key]:raise ValueError('Wrong carried advanced '+key)
    required={s for f in tomllib.loads((root/'content/coverage.toml').read_text())['family'][11:] for s in f['critical_strata']}
    if set(product['bindings'])!=required:raise ValueError('Missing or false advanced stratum binding.')
    document=decode_document(product['document']);reached=passive_reachable(product['document'])
    for case in product['cases']:
        for node,frames in case['frames'].items():
            if int(node) not in reached or _decoded_frames(document,int(node))!=frames:raise ValueError('Missing actual advanced literal/passive source.')
    return {'strata':len(required),'queries':len([q for g in product['groups'] for q in g['queries']]),
        'histories':len(product['contexts']),'proofs':len(product['proofs']),
        'anthology_entries':64,'anthology_states':6954,'passive_without_response':True,
        'scope':'Native literal authorship/conformance only; not recipient demonstration, full fit or release.'}
