"""Compact inert v1 course authoring; no chess rules or runtime inference."""
from copy import deepcopy
from .authoring import glyphs
from .document import NONE,decode_document,encode_document


class CourseAuthor:
    """One non-glyph ID space, exact interning and explicit imported dependencies."""
    def __init__(self):
        self.records=deepcopy(glyphs())
        self._records={r['id']:r for r in self.records}
        self._next=256
        self._frames={}
        self._traces={}
        self._tables={}
        self.labels={}

    def _add(self,record):
        if self._next>=NONE:raise ValueError('Course record ID space exhausted.')
        ident=self._next;self._next+=1
        record={'id':ident,**record}
        self.records.append(record);self._records[ident]=record
        return ident

    def record(self,ident):
        return self._records[ident]

    def glyph(self,ident,rows,cols,mask):
        if type(ident) is not int or not 0<=ident<=255 or type(rows) is not int or type(cols) is not int or not 1<=rows<=255 or not 1<=cols<=255:
            raise ValueError('Glyph requires an octet identity and nonempty dimensions.')
        if len(mask)!=(rows*cols+7)//8 or any(type(v) is not int or not 0<=v<=255 for v in mask):
            raise ValueError('Incomplete glyph mask.')
        padding=(-rows*cols)%8
        if padding and mask[-1]&((1<<padding)-1):raise ValueError('Noncanonical glyph padding.')
        record={'kind':1,'id':ident,'rows':rows,'cols':cols,'mask':list(mask)}
        if ident in self._records:
            if self._records[ident]!=record:raise ValueError('Glyph identity would change meaning.')
        else:self.records.append(record);self._records[ident]=record
        return ident

    @staticmethod
    def _frame_key(record):
        return (record['rows'],record['cols'],tuple(record['cells']),tuple(map(tuple,record['regions'])))

    @staticmethod
    def _trace_key(record):
        return (record['initial'],tuple(record['data']),tuple(tuple(map(tuple,p)) for p in record['steps']))

    def frame(self,cells,rows=9,cols=8,regions=()):
        if type(rows) is not int or type(cols) is not int or not 1<=rows<=255 or not 1<=cols<=255 or len(cells)!=rows*cols:
            raise ValueError('Complete nonempty u8-dimension frame required.')
        if any(type(v) is not int or v not in self._records or self._records[v]['kind']!=1 for v in cells):
            raise ValueError('Frame contains an unknown glyph.')
        regions=[list(r) for r in regions]
        if any(len(r)!=2 or type(r[0]) is not int or not 0<=r[0]<NONE or type(r[1]) is not int or not 0<=r[1]<len(cells) for r in regions):
            raise ValueError('Frame region is outside its finite domain.')
        if [r[0] for r in regions]!=sorted({r[0] for r in regions}) or len({r[1] for r in regions})!=len(regions):
            raise ValueError('Regions require unique sorted IDs and distinct cells.')
        record={'kind':2,'rows':rows,'cols':cols,'cells':list(cells),'regions':regions}
        key=self._frame_key(record)
        if key not in self._frames:self._frames[key]=self._add(record)
        return self._frames[key]

    def trace(self,frames,rows=9,cols=8,regions=(),data=()):
        if not frames:raise ValueError('A trace needs an explicit initial state.')
        initial=self.frame(frames[0],rows,cols,regions)
        if any(len(f)!=rows*cols or any(type(v) is not int or v not in self._records or self._records[v]['kind']!=1 for v in f) for f in frames):
            raise ValueError('Trace states must have constant dimensions and known glyphs.')
        if any(v not in self._records or self._records[v]['kind']!=5 for v in data):
            raise ValueError('Trace data must reference actual tables.')
        steps=[[[i,v] for i,v in enumerate(after) if v!=before[i]] for before,after in zip(frames,frames[1:])]
        record={'kind':3,'initial':initial,'data':list(data),'steps':steps};key=self._trace_key(record)
        if key not in self._traces:self._traces[key]=self._add(record)
        return self._traces[key]

    def table(self,values,cols):
        if type(cols) is not int or not 1<=cols<=255 or not values or len(values)%cols or any(type(v) is not int or not 0<=v<65536 for v in values):
            raise ValueError('Complete nonempty u16 table required.')
        key=(cols,tuple(values))
        if key not in self._tables:self._tables[key]=self._add({'kind':5,'rows':len(values)//cols,'cols':cols,'values':list(values)})
        return self._tables[key]

    def page(self,label,display,trace=False,shape=0,choices=(),accepted=(),success=NONE,failure=NONE,passive=NONE,links=()):
        if label in self.labels:raise ValueError('Duplicate course page label.')
        ident=self._add({'kind':4,'display_kind':int(trace),'display':display,'shape':shape,
            'choices':list(choices),'accepted':[list(v) for v in accepted],
            'success':success,'failure':failure,'passive':passive,'links':list(links)})
        self.labels[label]=ident
        return ident

    def import_subgraph(self,data,entries):
        """Copy exact reachable records, including glyphs, and reserve all their IDs."""
        document=decode_document(data);records=document['records'];wanted=set();pending=list(entries)
        if any(v not in records or records[v]['kind'] not in (3,4) for v in entries):
            raise ValueError('Invalid imported course entry.')
        while pending:
            ident=pending.pop()
            if ident in wanted:continue
            wanted.add(ident);r=records[ident]
            if r['kind']==2:pending.extend(r['cells'])
            elif r['kind']==3:
                pending.extend([r['initial']]+r['data'])
                pending.extend(v for step in r['steps'] for _,v in step)
            elif r['kind']==4:
                pending.append(r['display']);pending.extend(r['links'])
                pending.extend(r[k] for k in ('success','failure','passive') if r[k]!=NONE)
        for ident in wanted:
            if ident in self._records and self._records[ident]!=records[ident]:
                raise ValueError('Imported ID conflicts with existing course data.')
        for ident,r in records.items():
            if ident not in wanted:continue
            if ident not in self._records:
                r=deepcopy(r);self.records.append(r);self._records[ident]=r
            if r['kind']==2:self._frames.setdefault(self._frame_key(r),ident)
            elif r['kind']==3:self._traces.setdefault(self._trace_key(r),ident)
            elif r['kind']==5:self._tables.setdefault((r['cols'],tuple(r['values'])),ident)
        self._next=max(self._next,max(wanted,default=255)+1)
        return tuple(ident for ident in records if ident in wanted)

    def encode(self,entries):
        return encode_document(entries,self.records)


def passive_reachable(data):
    """Reachability using only carried ordinary links, without response edges."""
    document=decode_document(data);seen=set();pending=list(document['entries'])
    while pending:
        ident=pending.pop()
        if ident in seen:continue
        seen.add(ident);r=document['records'][ident]
        if r['kind']==4:pending.extend(r['links'])
    return seen


def compile_group(author,group):
    """Compile explicit finite query frames; semantic truth is checked upstream."""
    queries=group['queries'];rows,cols=group['rows'],group['cols'];name=group['id']
    if not 1<=len(queries)<=8 or cols<8 or rows+1+len(queries)>255:
        raise ValueError('A group needs1–8indexed queries and an eight-column response strip.')
    if len({q['id'] for q in queries})!=len(queries):raise ValueError('Duplicate query ID.')
    choices=[];query_rows=[];next_region=1
    for q in queries:
        options=q['options']
        if not 2<=len(options)<=3 or len({tuple(f) for f in options})!=len(options):
            raise ValueError('Each query needs2–3distinct finite alternatives.')
        if type(q['correct']) is not int or not 0<=q['correct']<len(options):
            raise ValueError('Query must identify its exact correct alternative.')
        if not q['worked'] or not q['contrast'] or not q['strata']:
            raise ValueError('Every query needs worked/contrast and actual stratum bindings.')
        for frame in q['worked']+q['contrast']+options:
            if len(frame)!=rows*cols:raise ValueError('Group query frame dimension mismatch.')
        ids=list(range(next_region,next_region+len(options)));next_region+=len(options)
        query_rows.append(ids);choices.extend(ids)
    height=rows+1+len(queries)
    regions=[(ident,(rows+1+qi)*cols+3+oi) for qi,ids in enumerate(query_rows) for oi,ident in enumerate(ids)]

    def decorate(frame,qi,oi=None,feedback=0,selected=()):
        cells=list(frame)+[0]*cols
        for index,q in enumerate(queries):
            strip=[13+index,5 if index==qi else 0,13+oi if index==qi and oi is not None else 0]
            strip.extend(5 if query_rows[index][j] in selected else 13+j for j in range(len(q['options'])))
            strip.extend([0]*(cols-len(strip)))
            if index==qi:strip[6]=feedback
            cells.extend(strip)
        return cells

    lesson=[];practice=[];passive=[];bindings=[];selected=[]
    for qi,q in enumerate(queries):
        begin=len(lesson);lesson.extend(decorate(f,qi) for f in q['worked']);work_end=len(lesson)
        lesson.extend(decorate(f,qi) for f in q['contrast']);contrast_end=len(lesson)
        practice_start=len(practice);passive_start=len(passive)
        for oi,frame in enumerate(q['options']):
            practice.append(decorate(frame,qi,oi))
            passive.append(decorate(frame,qi,oi))
            passive.append(decorate(frame,qi,oi,6 if oi==q['correct'] else 7))
        correct=query_rows[qi][q['correct']];selected.append(correct)
        passive.append(decorate(q['options'][q['correct']],qi,q['correct'],6,selected))
        bindings.append({'id':q['id'],'strata':list(q['strata']),'option_ids':query_rows[qi],
            'correct_region':correct,'worked_steps':[begin,work_end-1],
            'contrast_steps':[work_end,contrast_end-1],
            'practice_steps':[practice_start,len(practice)-1],
            'passive_steps':[passive_start,len(passive)-1]})
    expected=sorted(selected)
    success=author.page(name+'_success',author.frame([6],1,1))
    failure=author.page(name+'_failure',author.frame([7],1,1))
    data=group.get('data',())
    passive_id=author.page(name+'_passive',author.trace(passive,height,cols,regions,data),trace=True)
    practice_id=author.page(name+'_practice',author.trace(practice,height,cols,regions,data),trace=True,
        shape=2,choices=choices,accepted=[expected],success=success,failure=failure,passive=passive_id)
    worked=author.page(name+'_worked',author.trace(lesson,height,cols,regions,data),trace=True)
    author.record(worked)['links']=[practice_id,passive_id]
    author.record(practice_id)['links']=[worked,passive_id]
    author.record(passive_id)['links']=[worked,practice_id,success,failure]
    for ident in (success,failure):author.record(ident)['links']=[practice_id,passive_id,worked]
    return {'id':name,'worked':worked,'contrast':worked,'practice':practice_id,
        'passive':passive_id,'success':success,'failure':failure,'expected':expected,
        'queries':bindings,'frames':{str(worked):lesson,str(practice_id):practice,
            str(passive_id):passive,str(success):[[6]],str(failure):[[7]]}}
