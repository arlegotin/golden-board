"""Shared literal prefixes with complete boundaries and explicit parent references.

Player never inherits/computes state: each segment has a full initial snapshot.
The actual finite parent path supplies every standard-start move and state.
"""
from .practical_state import history,move_row
from .practical_cases import observe
from .course_generic import number_glyph
from .document import NONE

ROWS,COLS=23,9

def _extends(longer,shorter):return not shorter or longer==shorter or longer.startswith(shorter+' ')

def _moves(text):
    row=move_row(text);return [row[0]*8+row[1],row[2]*8+row[3],row[4]]

def _frame(state,ply,action=None):
    from .course_practical import render,_grid,_panel,digits
    wide=render(observe(''));_grid(wide,state['occupancy'],0);_panel(wide,state,0)
    cells=[v for row in range(ROWS) for v in wide[row*26:row*26+COLS]]
    cells[8*COLS:9*COLS]=[number_glyph(1),5,*([0]*7)]
    if action:cells[8*COLS+2:8*COLS+7]=[number_glyph(v) for v in move_row(action)]
    # Identity is the explicit page/trace/parent scope. Omitting a redundant ID
    # allows identical boundary snapshots to share one inert frame record.
    cells[9*COLS:10*COLS]=[*digits(ply),*([0]*5)]
    return cells

class HistorySegments:
    def __init__(self,author,history_ids,full_keys=()):
        if not history_ids or len(set(history_ids.values()))!=len(history_ids) or any(type(i)is not int or not 1<=i<=9999 for i in history_ids.values()):
            raise ValueError('History request IDs must be unique positive four-digit identities.')
        if any(p!=' '.join(p.split()) for p in history_ids):raise ValueError('Canonical move-prefix spacing required.')
        self.author=author;self.history_ids=dict(history_ids);children={'':set()}
        for prefix in history_ids:
            parent=''
            for move in prefix.split():
                child=(parent+' '+move).strip();children.setdefault(parent,set()).add(child);children.setdefault(child,set());parent=child
        important=set(history_ids)|{p for p,c in children.items() if len(c)>1}|{''}
        ordered=sorted(important,key=lambda p:(len(p.split()),p));self.segment_for={p:i+1 for i,p in enumerate(ordered)}
        self.carriers={};self.parents={}
        for prefix in ordered:
            parent=None if not prefix else max((p for p in important if p!=prefix and _extends(prefix,p)),key=lambda p:len(p.split()))
            self.parents[prefix]=parent;states=history(prefix);moves=prefix.split();start=0 if parent is None else len(parent.split());end=len(moves)
            frames=[_frame(states[i],i,None if not i else moves[i-1]) for i in range(start,end+1)]
            initial=author.frame(frames[0],ROWS,COLS);keys=[]
            indexes=range(start,end+1) if any(_extends(p,prefix) for p in full_keys) else (end,)
            for i in indexes:
                s=states[i];ep=s['key_ep']
                keys += [i,initial,i-start,s['side'],*map(int,s['rights']),int(ep is not None),0 if ep is None else ep//8,0 if ep is None else ep%8,s['repeat']]
            roles={'keys':author.table(keys,12),'occurrences':author.table([v for i in states[-1]['occurrences'] for v in (end,i)],2)}
            if end>start:roles['moves']=author.table([v for m in moves[start:] for v in _moves(m)],3)
            if states[-1]['legal']:roles['legal']=author.table([v for m in states[-1]['legal'] for v in _moves(m)],3)
            trace=author.trace(frames,ROWS,COLS,data=list(roles.values()));ident=self.segment_for[prefix]
            page=author.page('segment-'+str(ident),trace,trace=True)
            self.carriers[prefix]={'page':page,'trace':trace,'frames':frames,'tables':roles,'start':start,'end':end,'id':ident}
        for prefix,c in self.carriers.items():
            parent=self.parents[prefix]
            if parent is not None:
                p=self.carriers[parent];author.record(c['page'])['links'].append(p['page']);author.record(p['page'])['links'].append(c['page'])

    def context(self,prefix):
        c=self.carriers[prefix];return c['page'],c['frames']

    def describe(self):return {p:c['page'] for p,c in self.carriers.items()}
    def node_frames(self):return {c['page']:c['frames'] for c in self.carriers.values()}

    def directory_rows(self,contexts,document=None):
        rows=[]
        for prefix,ident in sorted(self.history_ids.items(),key=lambda r:r[1]):
            node=contexts[prefix];c=self.carriers[prefix]
            trace=self.author.record(node)['display'] if document is None else document['records'][node]['display']
            rows += [ident,node,trace,c['end']-c['start'],c['end'],c['id']]
        return rows

    def segment_rows(self,segments=None,document=None):
        segments=self.describe() if segments is None else segments;rows=[]
        for prefix,c in self.carriers.items():
            parent=self.parents[prefix];node=segments[prefix]
            if document is None:trace=c['trace'];roles=c['tables']
            else:
                trace=document['records'][node]['display'];data=document['records'][trace]['data'];roles=dict(zip(c['tables'],data))
            rows += [c['id'],node,trace,NONE if parent is None else self.segment_for[parent],c['start'],c['end'],
                roles['keys'],roles['occurrences'],roles.get('moves',NONE),roles.get('legal',NONE),c['end']-c['start']]
        return rows

    def locator_frames(self):
        from .course_practical import render,digits,_grid,_panel
        from .practical_state import evaluate
        frames=[];pairs=[];endstates={p:history(p)[-1] for p in self.history_ids}
        for a in self.history_ids:
            for b in self.history_ids:
                if len(a.split())>=len(b.split()):continue
                sa,sb=endstates[a],endstates[b]
                if sa['occupancy']==sb['occupancy'] and sa['repeat']!=sb['repeat']:pairs.append((a,b))
        if pairs:
            for prefix in min(pairs,key=lambda row:(sum(len(p.split()) for p in row),row)):
                c=self.carriers[prefix];s={**observe(prefix),'history_id':self.history_ids[prefix]}
                before=render(s);after=render(s,evaluate(s),verdict=True)
                for f in (before,after):
                    f[8*26+20:8*26+24]=digits(c['id']);f[9*26+12:9*26+16]=digits(c['page'])
                    f[9*26+18:9*26+22]=digits(c['end']-c['start']);f[22*26+8:22*26+12]=digits(c['end'])
                frames += [before,after]
        branches=[p for p in self.carriers if sum(parent==p for parent in self.parents.values())>=2]
        if branches:
            parent=min(branches,key=lambda p:(not bool(p),self.history_ids.get(p)==self.segment_for[p],len(p.split()),p));p=self.carriers[parent];state=history(parent)[-1]
            for child in [c for c in self.carriers if self.parents[c]==parent][:2]:
                c=self.carriers[child];f=render(observe(''));_grid(f,state['occupancy'],0);_panel(f,state,0)
                _grid(f,state['occupancy'],9);_panel(f,state,9)
                # A reference/branch diagram has its own mode. Its segment IDs
                # must not masquerade as observe-mode request history IDs.
                f[8*26]=number_glyph(7)
                f[8*26+14:8*26+18]=digits(p['id']);f[8*26+20:8*26+24]=digits(c['id'])
                f[9*26+12:9*26+16]=digits(p['page']);f[9*26+18:9*26+22]=digits(c['page'])
                f[22*26:22*26+2]=[number_glyph(7),5];f[22*26+8:22*26+12]=digits(c['start']);frames.append(f)
                state_after=history(child)[-1];g=list(f);_grid(g,state_after['occupancy'],9);_panel(g,state_after,9)
                g[22*26+8:22*26+12]=digits(c['end']);frames.append(g)
        return frames

    def validate(self,document,contexts,directory=None,segments=None,directory_positions=(0,1)):
        from .course_practical import _decoded_frames,_table_signature
        segments=self.describe() if segments is None else segments
        if set(contexts)!=set(self.history_ids) or set(segments)!=set(self.carriers):raise ValueError('Missing history endpoint or literal segment.')
        if len(set(segments.values()))!=len(segments):raise ValueError('Distinct history segments alias one page.')
        for prefix,c in self.carriers.items():
            node=segments[prefix]
            if prefix in contexts and contexts[prefix]!=node:raise ValueError('Endpoint names the wrong segment.')
            if node not in document['records'] or _decoded_frames(document,node)!=c['frames']:raise ValueError('Wrong literal history segment/boundary.')
            actual=document['records'][document['records'][node]['display']]
            tables=[document['records'][i] for i in actual['data']];expected=[self.author.record(i) for i in c['tables'].values()]
            if len(tables)!=len(expected):raise ValueError('Missing key/occurrence/move/domain role.')
            for i,(a,b) in enumerate(zip(tables,expected)):
                values=list(b['values'])
                if i==0:
                    for pos in range(1,len(values),12):values[pos]=actual['initial']
                if _table_signature(a)!=(b['rows'],b['cols'],values):raise ValueError('Wrong scoped history table.')
            parent=self.parents[prefix]
            if parent is not None and _decoded_frames(document,segments[parent])[-1]!=_decoded_frames(document,node)[0]:raise ValueError('Broken literal parent boundary.')
        if directory is not None:
            trace=document['records'][document['records'][directory]['display']]
            endpoint=self.directory_rows(contexts,document);segment=self.segment_rows(segments,document)
            a,b=directory_positions
            if len(trace['data'])<=max(a,b) or _table_signature(document['records'][trace['data'][a]])!=(len(self.history_ids),6,endpoint):raise ValueError('Wrong history endpoint directory.')
            if _table_signature(document['records'][trace['data'][b]])!=(len(self.carriers),11,segment):raise ValueError('Wrong parent/trace/role directory.')
