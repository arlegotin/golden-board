"""Ostensive6/6/3 field mapping, independent of move legality or chess inference."""
from .move_packing import pack_move,unpack_move
from .course_generic import number_glyph

ROWS,COLS=17,26
_MISSING=object()

def _digits(value,width):return [number_glyph(int(v)) for v in str(value).zfill(width)]
def _bits(value,width):return [1 if (value>>i)&1 else 2 for i in range(width-1,-1,-1)]

def solve(spec):
    _bridge(spec)
    try:return pack_move(spec['row']) if spec['op']=='pack' else unpack_move(spec['value'])
    except ValueError:return None

def _bridge(spec):
    if 'prefix' not in spec:return None
    from .practical_cases import move
    from .practical_state import evaluate,move_row
    effect=evaluate(move(spec['prefix'],spec['move']));r=move_row(spec['move'])
    fields=[r[0]*8+r[1],r[2]*8+r[3],r[4]]
    actual=spec['row'] if spec['op']=='pack' else unpack_move(spec['value'])
    if not effect['accepted'] or actual!=fields:raise ValueError('False packed-field/actual-move teaching binding.')
    return effect

def _render_fields(spec,result=_MISSING,*,complete=None,verdict=None):
    done=result is not _MISSING if complete is None else complete
    value=result if done else None;f=[0]*(9*COLS)
    row=spec['row'] if spec['op']=='pack' else value
    code=spec['value'] if spec['op']=='unpack' else value
    for i,x in enumerate((0,8,16)):f[x]=number_glyph(i+1)
    f[22:24]=_digits(6,2);f[7*COLS]=number_glyph(1 if spec['op']=='pack' else 2)
    if row is not None:
        for v,x,width,bits in zip(row,(0,8,16),(2,2,1),(6,6,3)):
            f[COLS+x:COLS+x+width]=_digits(v,width);f[2*COLS+x:2*COLS+x+bits]=_bits(v,bits)
    if code is not None:
        f[3*COLS:3*COLS+16]=_bits(code,16);f[5*COLS+2:5*COLS+7]=_digits(code,5)
    for x,v in ((0,1),(1,6),(7,6),(13,3)):f[4*COLS+x]=number_glyph(v)
    f[6*COLS]=0 if not done else 1 if value is not None else 2
    f[8*COLS]=0 if verdict is None else 6 if verdict else 7
    if 'history_id' in spec:f[7*COLS+20:7*COLS+24]=_digits(spec['history_id'],4)
    return f

def render(spec,result=_MISSING,*,complete=None,verdict=None):
    top=[0]*(8*COLS);effect=_bridge(spec)
    if effect:
        for y in range(8):
            top[y*COLS:y*COLS+8]=effect['before']['occupancy'][y*8:y*8+8]
            top[y*COLS+9:y*COLS+17]=effect['after']['occupancy'][y*8:y*8+8]
    return top+_render_fields(spec,result,complete=complete,verdict=verdict)

def packing_groups(root):
    from .practical_cases import practical_queries,PROMO,SHORT
    from .practical_state import move_row
    qs=practical_queries(root)
    ids={s[k]:s['history_id' if k=='prefix' else 'other_history_id'] for q in qs for s in [q['worked_input'],q['input'],*q['worked_variants']] for k in ('prefix','other') if k in s}
    def actual(op,prefix,text):
        r=move_row(text);row=[r[0]*8+r[1],r[2]*8+r[3],r[4]];prefix=' '.join(prefix.split())
        return {'op':op,'prefix':prefix,'move':text,'history_id':ids[prefix],**({'row':row} if op=='pack' else {'value':pack_move(row)})}
    rows=[]
    examples=[{'op':'pack','row':[0,0,0]},{'op':'pack','row':[63,63,4]},
        *[{'op':'pack','row':[1,8,p]} for p in range(5)],
        {'op':'unpack','value':32768},{'op':'unpack','value':5},
        *[actual('pack',PROMO,'b7a8'+suffix) for suffix in 'qrbn']]
    inputs=[('field_concatenation',actual('pack','','e2e4'),actual('pack','e2e4','e7e5')),
            ('field_separation',actual('unpack',SHORT,'e1g1'),{'op':'unpack','value':pack_move([56,0,4])})]
    for ident,work,practice in inputs:
        expected=solve(practice);worked=solve(work)
        if practice['op']=='pack':wrong=pack_move([practice['row'][1],practice['row'][0],practice['row'][2]]);workwrong=pack_move([work['row'][1],work['row'][0],work['row'][2]])
        else:wrong=[expected[0],expected[1],3];workwrong=[worked[0],worked[1],4]
        variants=examples if practice['op']=='pack' else []
        q={'id':ident,'family':'T10','strata':['origin_destination_and_explicit_promotion'],
            'worked_input':work,'input':practice,'worked_expected':worked,'expected':expected,
            'worked_variants':variants,'rival_kind':'fixed_fields','options_data':[wrong,expected],'correct':1,
            'worked':[render(work),render(work,worked,verdict=True)],
            'contrast':[render(work,workwrong,verdict=False),render(work,worked,verdict=True)],
            'options':[render(practice,wrong),render(practice,expected)]}
        q['worked'] += [render(s,solve(s),verdict=True) for s in variants]
        rows.append(q)
    return [{'id':'T10-packed-fields','rows':ROWS,'cols':COLS,'queries':rows}]
