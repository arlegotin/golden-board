"""Explicit authoring-time T0 examples; the delivered data has no interpreter."""
from copy import deepcopy
import hashlib,json
from .course_author import CourseAuthor,compile_group,passive_reachable

OPS={name:i for i,name in enumerate(('count','equal','less','row','col','at','roles','updates','record'),1)}
ROWS,COLS=18,16


def _matrix(value):
    if not isinstance(value,list) or not value or not isinstance(value[0],list) or not value[0] or any(len(row)!=len(value[0]) for row in value):
        raise ValueError('An explicit complete matrix is required.')
    if any(type(v) is not int or not 0<=v<=9 for row in value for v in row):raise ValueError('T0 numeric examples use0–9.')
    return value


def generic_result(spec):
    """Only the finite G2/G3 operations actually consumed by these examples."""
    op=spec['op']
    if op in ('count','row','col','at','roles','updates'):
        matrix=_matrix(spec['matrix']);rows,cols=len(matrix),len(matrix[0])
        if op in ('row','at','roles') and (type(spec['row']) is not int or not 0<=spec['row']<rows):raise ValueError('Row outside matrix.')
        if op in ('col','at','roles') and (type(spec['col']) is not int or not 0<=spec['col']<cols):raise ValueError('Column outside matrix.')
        if op=='count':return sum(v==spec['value'] for row in matrix for v in row)
        if op=='row':return list(matrix[spec['row']])
        if op=='col':return [row[spec['col']] for row in matrix]
        if op=='at':return matrix[spec['row']][spec['col']]
        if op=='roles':return [matrix[spec['row']][spec['col']],sum(v==spec['value'] for row in matrix for v in row),spec['row']*cols+spec['col']]
        result=deepcopy(matrix)
        for update in spec['updates']:
            if len(update)!=3:raise ValueError('One explicit row/column/value update per step required.')
            r,c,v=update
            if type(r) is not int or type(c) is not int or not 0<=r<rows or not 0<=c<cols or type(v) is not int or not 0<=v<=9:raise ValueError('Invalid sparse update.')
            result[r][c]=v
        return result
    if op=='equal':return int(spec['left']==spec['right'])
    if op=='less':
        if type(spec['left']) is not int or type(spec['right']) is not int:raise ValueError('Ordered integer operands required.')
        return int(spec['left']<spec['right'])
    if op=='record':
        records=spec['records'];ids=[r['id'] for r in records]
        if len(ids)!=len(set(ids)) or spec['reference'] not in ids:raise ValueError('Unique finite records and a resolved reference required.')
        for record in records:
            body=record['body']
            if type(record['id']) is not int or not 0<=record['id']<=9 or not 1<=len(body)<=3 or any(type(v) is not int or not 0<=v<=9 for v in body):raise ValueError('Invalid finite record body.')
        offset=0
        for record in records:
            body=record['body']
            if record['id']==spec['reference']:return [[offset,record['id'],len(body)],list(body)+[None]*(3-len(body))]
            offset+=2+len(body) # This explicitly scoped model has one ID and one length field.
    raise ValueError('Unknown finite lesson operation: '+str(op))


def add_numeric_glyphs(author):
    patterns={22:['010','101','010'],23:['00000','00000','11111','00000','00000'],24:['00100']*5,
        25:['00000','00000','00111','00100','00100'],26:['00000','00000','11100','00100','00100'],
        27:['00100','00100','00111','00000','00000'],28:['00100','00100','11100','00000','00000'],
        29:['00100','00010','11111','00010','00100']}
    for ident,rows in patterns.items():
        bits=''.join(rows);bits+='0'*(-len(bits)%8)
        author.glyph(ident,len(rows),len(rows[0]),[int(bits[i:i+8],2) for i in range(0,len(bits),8)])


def number_glyph(value):
    if value is None:return 0
    if type(value) is not int or not 0<=value<=9:raise ValueError('Displayed cardinal is outside0–9.')
    return 22 if value==0 else 12+value


def _result_matrix(value):
    if not isinstance(value,list):return [[value]]
    return value if value and isinstance(value[0],list) else [value]


def _source_matrix(spec):
    op=spec['op']
    if 'matrix' in spec:return spec['matrix']
    if op in ('equal','less'):
        return [spec['left'],spec['right']] if isinstance(spec['left'],list) else [[spec['left']],[spec['right']]]
    if op=='record':return [[r['id'],len(r['body'])]+r['body']+[None]*(3-len(r['body'])) for r in spec['records']]
    raise ValueError('Unrendered lesson input.')


def _box(cells,matrix,y,x):
    rows,cols=len(matrix),len(matrix[0])
    if not rows or not cols or any(len(r)!=cols for r in matrix) or y+rows+2>ROWS or x+cols+2>COLS:raise ValueError('Displayed matrix exceeds its complete frame.')
    put=lambda r,c,v:cells.__setitem__(r*COLS+c,v)
    for col in range(cols):put(y,x+1+col,number_glyph(col));put(y+rows+1,x+1+col,23)
    for row in range(rows):
        put(y+1+row,x,number_glyph(row));put(y+1+row,x+cols+1,24)
        for col,value in enumerate(matrix[row]):put(y+1+row,x+1+col,number_glyph(value))
    for r,c,v in ((y,x,25),(y,x+cols+1,26),(y+rows+1,x,27),(y+rows+1,x+cols+1,28)):put(r,c,v)


def render_generic(spec,result,*,verdict=None,applied=None):
    """Draw every relevant input; zero-valued cells differ from absent padding."""
    source=_source_matrix(spec);target=_result_matrix(result);cells=[0]*(ROWS*COLS)
    mode=OPS[spec['op']]
    cells[:4]=[1 if mode&(1<<bit) else 2 for bit in range(3,-1,-1)]
    args=[spec[k] for k in ('row','col','value','reference') if k in spec]
    cells[5:5+len(args)]=[number_glyph(v) for v in args]
    cells[COLS:COLS+2]=[number_glyph(len(source)),number_glyph(len(source[0]))]
    start=COLS-len(target[0])-2
    cells[COLS+start:COLS+start+2]=[number_glyph(len(target)),number_glyph(len(target[0]))]
    _box(cells,source,3,0);_box(cells,target,3,start)
    cells[5*COLS+len(source[0])+3]=29
    if spec['op']=='updates':
        _box(cells,spec['updates'],10,0)
        if applied is not None:
            cells[9*COLS+8]=number_glyph(applied)
            if applied:cells[(10+applied)*COLS+6]=5
    if spec['op']=='record':
        flat=[v for r in spec['records'] for v in [r['id'],len(r['body']),*r['body']]]
        padded=flat+[None]*(-len(flat)%8)
        _box(cells,[padded[i:i+8] for i in range(0,len(padded),8)],10,0)
        cells[9*COLS]=number_glyph(len(flat))
    if verdict is not None:cells[COLS-1]=6 if verdict else 7
    return cells


def _blank(value):
    matrix=_result_matrix(value)
    return [[None]*len(matrix[0]) for _ in matrix]


def _query_frames(query):
    work=query['worked_input'];answer=generic_result(work)
    if work['op']=='updates':
        worked=[render_generic(work,generic_result({**work,'updates':work['updates'][:i]}),applied=i)
                for i in range(len(work['updates'])+1)]
    else:worked=[render_generic(work,_blank(answer)),render_generic(work,answer,verdict=True)]
    for variant in query.get('worked_variants',[]):
        result=generic_result(variant)
        worked.extend([render_generic(variant,_blank(result)),render_generic(variant,result,verdict=True)])
    contrast=[render_generic(work,query['worked_rival'],verdict=False),render_generic(work,answer,verdict=True)]
    options=[render_generic(query['input'],value) for value in query['options_data']]
    return worked,contrast,options


def _query(ident,strata,work,practice,worked_rival,options,*,varied_values=(),variants=()):
    expected=generic_result(practice);worked_expected=generic_result(work)
    if worked_rival==worked_expected or options.count(expected)!=1:raise ValueError('Lesson needs a discriminating rival and one exact finite answer.')
    query={'id':ident,'strata':list(strata),'worked_input':work,'input':practice,
        'worked_expected':worked_expected,'worked_rival':worked_rival,'expected':expected,
        'options_data':options,'correct':options.index(expected),
        'worked_variants':[{**deepcopy(work),'value':value} for value in varied_values]+[deepcopy(v) for v in variants]}
    query['worked'],query['contrast'],query['options']=_query_frames(query)
    return query


def generic_groups():
    """Explicit worked/novel-practice inputs, not a runtime question language."""
    count='count_equality_order';matrix='matrix_rows_columns_addresses'
    q=[]
    q.append(_query('count',[count],{'op':'count','matrix':[[1,0,1],[2,0,1]],'value':1},
        {'op':'count','matrix':[[0,2,1],[1,1,2]],'value':0},6,[4,1,3],varied_values=(0,2)))
    q.append(_query('equal',[count],{'op':'equal','left':[1,0,2],'right':[1,0,2]},
        {'op':'equal','left':[0,2,1],'right':[0,1,2]},0,[1,0]))
    q.append(_query('order',[count],{'op':'less','left':3,'right':1},
        {'op':'less','left':1,'right':2},1,[1,0],
        variants=({'op':'less','left':0,'right':0},{'op':'less','left':2,'right':2})))
    a=[[0,1,2],[2,0,1]]
    q.append(_query('row',[matrix],{'op':'row','matrix':a,'row':1},
        {'op':'row','matrix':[[1,0],[0,2],[2,1]],'row':1},[1,0,2],[[2,0],[0,2],[1,0]]))
    q.append(_query('column',[matrix],{'op':'col','matrix':a,'col':1},
        {'op':'col','matrix':[[1,0],[0,2],[2,1]],'col':0},[0,1],[[1,0,2],[0,1,2],[1,2,0]]))
    q.append(_query('address',[matrix],{'op':'at','matrix':a,'row':1,'col':1},
        {'op':'at','matrix':[[2,1],[0,2],[1,0]],'row':0,'col':1},1,[2,0,1]))
    q.append(_query('roles',['value_count_address_role_separation'],
        {'op':'roles','matrix':[[0,2,1,2],[1,1,0,2]],'row':1,'col':2,'value':1},
        {'op':'roles','matrix':[[1,0],[2,2],[0,1]],'row':2,'col':1,'value':0},
        [0,3,2],[[1,2,1],[1,2,5],[1,5,2]],varied_values=(0,),
        variants=({'op':'roles','matrix':[[2,2,0],[1,0,2]],'row':0,'col':1,'value':2},)))
    q.append(_query('updates',['before_after_and_partial_update'],
        {'op':'updates','matrix':[[1,2,0],[1,0,2]],'updates':[[0,1,0],[1,2,1]]},
        {'op':'updates','matrix':[[0,1,2],[2,1,0]],'updates':[[1,0,0],[0,2,1]]},
        [[0,0,0],[0,0,1]],[[[0,0,1],[0,0,0]],[[0,1,1],[0,1,0]],[[0,1,1],[2,1,0]]]))
    q.append(_query('records',['record_length_boundary_and_reference'],
        {'op':'record','records':[{'id':2,'body':[1,0,2]},{'id':7,'body':[2,1]}],'reference':7},
        {'op':'record','records':[{'id':2,'body':[0,2]},{'id':7,'body':[1,1,0]}],'reference':2},
        [[0,2,3],[1,0,2]],[[[4,7,3],[1,1,0]],[[4,2,2],[0,2,None]],[[0,2,2],[0,2,None]]]))
    return [{'id':'finite-data','rows':ROWS,'cols':COLS,'queries':q[:7]},
            {'id':'updates-records','rows':ROWS,'cols':COLS,'queries':q[7:]}]


def _legend_frames():
    frames=[]
    for n in range(10):
        frame=[0]*(ROWS*COLS)
        # Framed concrete particles, paired with a cardinal glyph and binary row.
        _box(frame,[[None]*3 for _ in range(3)],3,0)
        for i in range(n):frame[(4+i//3)*COLS+1+i%3]=13
        _box(frame,[[n]],3,13)
        for i,bit in enumerate(range(3,-1,-1)):frame[8*COLS+11+i]=1 if n&(1<<bit) else 2
        frames.append(frame)
    return frames


def _buffer_frame(shape,target,before,action_code,operand,after,accepted,ok=True):
    cells=[0]*(ROWS*COLS)
    cells[:3]=[number_glyph(shape),number_glyph(action_code),number_glyph(operand)]
    cells[COLS-1]=6 if ok else 7
    for values,y,x in ((before,3,0),(after,3,11),(target,10,0)):
        _box(cells,[list(values)+[None]*(3-len(values))],y,x)
        cells[(y-1)*COLS+x]=number_glyph(len(values))
    response=before if action_code==2 else []
    _box(cells,[list(response)+[None]*(3-len(response))],10,11)
    cells[9*COLS+11]=number_glyph(len(response))
    cells[4*COLS+8]=29
    cells[9*COLS+8]=number_glyph(int(accepted is not None))
    cells[13*COLS+8]=0 if accepted is None else 6 if accepted else 7
    cells[16*COLS+8]=number_glyph(0 if accepted is None else 1 if accepted else 2)
    cells[17*COLS+3:17*COLS+6]=[13,14,15]
    return cells


def _action_case(author,name,shape,expected,plans,strata):
    plans=[list(plan)+([('retry',None,[],None,True)] if i+1<len(plans) else []) for i,plan in enumerate(plans)]
    prompt=_buffer_frame(shape,expected,[],0,None,[],None)
    regions=[(i+1,17*COLS+3+i) for i in range(3)]
    success=author.page(name+'_success',author.frame([6],1,1))
    failure=author.page(name+'_failure',author.frame([7],1,1))
    work=[];scripts=[]
    for plan in plans:
        before=[];steps=[]
        for operation,value,after,accepted,ok in plan:
            code={'idle':0,'select':1,'commit':2,'reset':3,'retry':4}[operation]
            work.append(_buffer_frame(shape,expected,before,code,value,after,accepted,ok))
            action=None if operation=='idle' else {'link':None} if operation=='retry' else {operation:value if operation=='select' else True}
            steps.append({'action':action,'operation':operation,'selection':list(after),'accepted':accepted,'ok':ok})
            before=list(after)
        scripts.append(steps)
    passive=author.page(name+'_passive',author.trace([prompt]+work,ROWS,COLS,regions),trace=True)
    practice=author.page(name+'_practice',author.frame(prompt,ROWS,COLS,regions),shape=shape,
        choices=[1,2,3],accepted=[expected],success=success,failure=failure,passive=passive)
    worked=author.page(name+'_worked',author.trace(work,ROWS,COLS,regions),trace=True)
    for script in scripts:
        for step in script:
            if step['operation']=='retry':step['action']={'link':practice}
    author.record(worked)['links']=[practice,passive]
    author.record(practice)['links']=[worked,passive]
    author.record(passive)['links']=[worked,practice,success,failure]
    for ident in (success,failure):author.record(ident)['links']=[worked,practice,passive]
    return {'id':name,'section':1,'worked':worked,'contrast':worked,'practice':practice,
        'passive':passive,'success':success,'failure':failure,'expected':list(expected),
        'strata':list(strata),'scripts':scripts,'plans':plans,'queries':[],
        'display_contract':{'number_glyphs':{str(i):number_glyph(i) for i in range(10)},
            'padding_glyph':0,'before_cells':[4*COLS+1+i for i in range(3)],
            'after_cells':[4*COLS+12+i for i in range(3)],
            'response_cells':[11*COLS+12+i for i in range(3)],
            'commit_flag_cell':9*COLS+8,'feedback_cell':13*COLS+8},
        'frames':{str(worked):work,str(practice):[prompt],str(passive):[prompt]+work,
            str(success):[[6]],str(failure):[[7]]}}


def _action_cases(author):
    common='select_commit_reset_retry';ordered='ordered_sequence_vs_set'
    single=[('idle',None,[],None,True),('select',1,[1],None,True),('select',2,[2],None,True),
        ('reset',None,[],None,True),('select',2,[2],None,True),('commit',None,[],True,True),
        ('retry',None,[],None,True),('select',1,[1],None,True),('commit',None,[],False,True)]
    sets=[('select',3,[3],None,True),('select',1,[1,3],None,True),('select',3,[1],None,True),
        ('select',3,[1,3],None,True),('reset',None,[],None,True),('select',1,[1],None,True),
        ('select',3,[1,3],None,True),('commit',None,[],True,True),('retry',None,[],None,True),
        ('select',2,[2],None,True),('commit',None,[],False,True)]
    sequence=[('select',2,[2],None,True),('select',1,[2,1],None,True),('select',2,[2,1,2],None,True),
        ('select',3,[2,1,2],None,False),('commit',None,[],True,True)]
    reordered=[('select',1,[1],None,True),('select',2,[1,2],None,True),
        ('select',2,[1,2,2],None,True),('commit',None,[],False,True)]
    lost_repeat=[('select',1,[1],None,True),('select',2,[1,2],None,True),('commit',None,[],False,True)]
    empty=[('idle',None,[],None,True),('commit',None,[],True,True),('retry',None,[],None,True),
        ('select',1,[1],None,True),('commit',None,[],False,True),('retry',None,[],None,True),
        ('select',1,[1],None,True),('reset',None,[],None,True),('commit',None,[],True,True)]
    return [_action_case(author,'single-replace',1,[2],[single],[common]),
        _action_case(author,'set-toggle',2,[1,3],[sets],[common,ordered]),
        _action_case(author,'ordered-repeat',3,[2,1,2],[sequence,reordered,lost_repeat],[common,ordered]),
        _action_case(author,'empty-commit',2,[],[empty],[common,'empty_commit_vs_no_submission'])]


def _calibrate_group(author,case):
    """A complete two-query aggregate, with actual region IDs and action states."""
    expected=case['expected']
    if expected!=[2,5]:raise ValueError('Recheck literal grouped calibration plans after changing operands.')
    plans=[
        [('select',2,[2],None,True),('commit',None,[],False,True)],
        [('select',5,[5],None,True),('select',2,[2,5],None,True),('idle',None,[2,5],None,True),('commit',None,[],True,True)],
        [('select',2,[2],None,True),('select',4,[2,4],None,True),('commit',None,[],False,True)],
        [('select',2,[2],None,True),('select',5,[2,5],None,True),('select',4,[2,4,5],None,True),('commit',None,[],False,True)],
        [('select',2,[2],None,True),('reset',None,[],None,True),('select',5,[5],None,True),('select',2,[2,5],None,True),('commit',None,[],True,True)],
    ]
    plans=[list(plan)+([('retry',None,[],None,True)] if i+1<len(plans) else []) for i,plan in enumerate(plans)]
    page=author.record(case['practice']);trace=author.record(page['display']);initial=author.record(trace['initial'])
    upper=initial['rows']*COLS;frames=[];scripts=[]
    options=case['frames'][str(case['practice'])]
    for plan in plans:
        before=[];script=[];current=0
        for operation,value,after,accepted,ok in plan:
            if operation=='select':current=page['choices'].index(value)
            frame=list(options[current])
            for qi,q in enumerate(case['queries']):
                for oi,ident in enumerate(q['option_ids']):
                    frame[(ROWS+1+qi)*COLS+3+oi]=5 if ident in after else 13+oi
            code={'idle':0,'select':1,'commit':2,'reset':3,'retry':4}[operation]
            panel=_buffer_frame(2,expected,before,code,value,after,accepted,ok)
            panel[17*COLS+3:17*COLS+8]=[number_glyph(v) for v in page['choices']]
            frames.append(frame+panel)
            action=None if operation=='idle' else {'link':case['practice']} if operation=='retry' else {operation:value if operation=='select' else True}
            script.append({'action':action,'operation':operation,'selection':list(after),'accepted':accepted,'ok':ok})
            before=list(after)
        scripts.append(script)
    tutorial=author.page('grouped-calibration-actions',author.trace(frames,initial['rows']+ROWS,COLS,initial['regions']),trace=True,
        links=[case['worked'],case['practice'],case['passive']])
    author.record(case['worked'])['links'].insert(0,tutorial)
    author.record(case['passive'])['links'].insert(0,tutorial)
    case.update(scripts=scripts,script_display=tutorial,plans=plans)
    case['frames'][str(tutorial)]=frames
    case['display_contract']={'number_glyphs':{str(i):number_glyph(i) for i in range(10)},'padding_glyph':0,
        'before_cells':[upper+4*COLS+1+i for i in range(3)],
        'after_cells':[upper+4*COLS+12+i for i in range(3)],
        'response_cells':[upper+11*COLS+12+i for i in range(3)],
        'commit_flag_cell':upper+9*COLS+8,'feedback_cell':upper+13*COLS+8,
        'selected_cells':[{'id':ident,'cell':(ROWS+1+qi)*COLS+3+oi,'unselected':13+oi}
            for qi,q in enumerate(case['queries']) for oi,ident in enumerate(q['option_ids'])]}


def validate_generic(product):
    """Recompute every declared query and check its displayed operands/consequences."""
    checked=[]
    for group in product['groups']:
        for q in group['queries']:
            if generic_result(q['input'])!=q['expected'] or generic_result(q['worked_input'])!=q['worked_expected']:
                raise ValueError('Wrong declared finite truth: '+q['id'])
            if q['worked_rival']==q['worked_expected'] or q['options_data'].count(q['expected'])!=1 or q['options_data'][q['correct']]!=q['expected']:
                raise ValueError('Incomplete/wrong finite alternatives: '+q['id'])
            work,contrast,options=_query_frames(q)
            if (q['worked'],q['contrast'],q['options'])!=(work,contrast,options):raise ValueError('Displayed operands or intermediate differ from recomputed truth.')
            checked.append({'query':q['id'],'strata':q['strata'],'input_sha256':hashlib.sha256(json.dumps(q['input'],sort_keys=True).encode()).hexdigest(),'expected':q['expected'],'rival':q['worked_rival'],
                'worked_variants':[{'input':v,'expected':generic_result(v)} for v in q.get('worked_variants',[])]})
    reached=passive_reachable(product['document'])
    if any(c[k] not in reached for c in product['cases'] for k in ('worked','practice','passive','success','failure')):
        raise ValueError('Course instruction or feedback needs a response to be reached.')
    if any(not rows for rows in product['bindings'].values()):raise ValueError('Unbound generic stratum.')
    return {'strata':len(product['bindings']),'queries':checked,'passive_without_response':True,
        'scope':'Authored finite truth/data, not recipient understanding or final candidate qualification'}


def build_generic():
    author=CourseAuthor();add_numeric_glyphs(author)
    legend_frames=_legend_frames();legend=author.page('cardinal-binary-legend',author.trace(legend_frames,ROWS,COLS),trace=True)
    cases=_action_cases(author);groups=generic_groups()
    calibration={'id':'grouped-calibration','rows':ROWS,'cols':COLS,'queries':deepcopy(groups[0]['queries'][:2])}
    groups.insert(0,calibration)
    for group in groups:
        group['data']=[]
        c=compile_group(author,group);c['section']=1
        if group['id']=='grouped-calibration':_calibrate_group(author,c)
        cases.append(c)
    roots=[legend]+[c['worked'] for c in cases]
    for before,after in zip(roots,roots[1:]):
        author.record(before)['links'].append(after);author.record(after)['links'].append(before)
    cases[0]['frames'][str(legend)]=legend_frames
    body=author.encode(roots);digest=hashlib.sha256(body).hexdigest();bindings={}
    for c in cases:
        for q in c['queries'] or [{'strata':c['strata'],'id':c['id']}]:
            for stratum in q['strata']:
                bindings.setdefault(stratum,[]).append({'case':c['id'],'query':q['id'],
                    'worked':c['worked'],'prediction':c['practice'],'contrast':c['contrast'],
                    'practice':c['practice'],'passive':c['passive'],'success':c['success'],
                    'failure':c['failure'],'document_sha256':digest,'state':'authored'})
    product={'document':body,'groups':groups,'cases':cases,'bindings':bindings,'roots':roots,
        'scope':'Actual T0logical course data; no carried-candidate/recipient demonstration claim'}
    product['truth']=validate_generic(product)
    return product
