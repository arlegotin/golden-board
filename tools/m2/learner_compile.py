"""Compile reviewed lesson pages using public content-v0 authoring values.

Owner answers are returned separately and never copied into held-out records.
The checked logical declaration is independently compiled by both languages.
"""
from dataclasses import asdict, fields, is_dataclass
import hashlib
import json
from golden_board import content as c, canonical_manifest, m2_runner


def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def _compose(page):
    panels = page['panels']
    if not 1 <= len(panels) <= 16:
        raise ValueError('panel count')
    for panel in panels:
        rows, cols, cells = panel['rows'], panel['columns'], panel['cells']
        if type(rows) is not int or type(cols) is not int or not 1 <= rows <= 128 or not 1 <= cols <= 256:
            raise ValueError('panel dimensions')
        if len(cells) != rows*cols or any(type(v) is not int or not 0 <= v <= 255 for v in cells):
            raise ValueError('panel cells')
    # Pack whole authored panels, never their cells. Wide comparisons get
    # another row rather than a mostly blank sixty-column surface. This is
    # source layout: both independent encoders receive the same final matrix.
    placements = []
    row_offset = column_offset = row_height = cols = 0
    for panel in panels:
        if column_offset and column_offset + panel['columns'] > 36:
            row_offset += row_height + 2
            column_offset = row_height = 0
        placements.append((row_offset, column_offset))
        cols = max(cols, column_offset + panel['columns'])
        row_height = max(row_height, panel['rows'])
        column_offset += panel['columns'] + 2
    rows = row_offset + row_height
    if rows*cols > 65535:
        raise ValueError('composed cell count')
    # Authored separators differ from actual empty cells; the viewer assigns
    # no special meaning to this numeric atom.
    cells = [255]*(rows*cols)
    for panel, (top, left) in zip(panels, placements, strict=True):
        for row in range(panel['rows']):
            start = (row+top)*cols+left
            cells[start:start+panel['columns']] = panel['cells'][row*panel['columns']:(row+1)*panel['columns']]
    last_top, last_left = placements[-1]
    seen = set()
    regions = []
    crops = {}
    for region in page['regions']:
        rid = region['id']
        r0,r1,c0,c1 = (region[k] for k in ('row_start','row_end','column_start','column_end'))
        if type(rid) is not int or not 1 <= rid <= 4096 or rid in seen:
            raise ValueError('region id')
        if any(type(v) is not int for v in (r0,r1,c0,c1)) or not 0 <= r0 < r1 <= panels[-1]['rows'] or not 0 <= c0 < c1 <= panels[-1]['columns']:
            raise ValueError('region bounds')
        seen.add(rid)
        regions.append(c.ContentRegion(rid,0,r0+last_top,r1+last_top,c0+last_left,c1+last_left,1))
        crop = tuple(panels[-1]['cells'][r*panels[-1]['columns']+col]
                     for r in range(r0,r1) for col in range(c0,c1))
        crops[rid] = (r1-r0,c1-c0,crop)
    regions.sort(key=lambda r:r.region_id)
    for i,a in enumerate(regions):
        for b in regions[i+1:]:
            if max(a.row_start,b.row_start)<min(a.row_end,b.row_end) and max(a.column_start,b.column_start)<min(a.column_end,b.column_end):
                raise ValueError('overlapping selectable regions')
    correct = tuple(page['correct'])
    if not correct or len(set(correct)) != len(correct) or any(rid not in seen for rid in correct):
        raise ValueError('correct region is absent')
    return rows,cols,tuple(cells),tuple(regions),crops

def compile_pages(pages):
    if not 1 <= len(pages) <= 96 or len({p['id'] for p in pages}) != len(pages):
        raise ValueError('page count or duplicate id')
    records = []
    def add(value):
        rid = len(records)+1
        records.append(c.ContentRecordView(rid,value))
        return rid
    def put(rid,value):
        records[rid-1] = c.ContentRecordView(rid,value)
    byte_schema = add(c.ContentAtomSchema(1,1,min_value=0,max_value=255))
    truth_vector = add(c.ContentAtomVector(byte_schema,(1,))) if any(p['phase'] != 'heldout' for p in pages) else 0
    built = []
    local_budget = 16
    for ordinal,page in enumerate(pages):
        phase = page['phase']
        if phase not in ('teach','practice','heldout'):
            raise ValueError('phase')
        rows,cols,cells,regions,crops = _compose(page)
        matrix = add(c.ContentMatrix(byte_schema,rows,cols,cells))
        region_set = add(c.ContentRegionSet(matrix,regions))
        predicate = 0
        if phase != 'heldout':
            # This opaque assertion identifies the author-verified case. Its
            # chess meaning belongs to learner_content.py and owner evidence.
            identity = hashlib.sha256(json.dumps(page,sort_keys=True,separators=(',',':')).encode()).digest()
            data_binding = add(c.ContentSemanticBinding(1,40000,ordinal+1,byte_schema,len(identity)))
            data = add(c.ContentOpaqueData(data_binding,tuple(identity)))
            predicate_binding = add(c.ContentSemanticBinding(2,40000,ordinal+1,data_binding,byte_schema))
            predicate = add(c.ContentPredicateResult(predicate_binding,data,truth_vector))
        feedbacks = {}
        if phase != 'heldout':
            for rid in (page['correct'] if phase == 'practice' else page['correct'][:1]):
                height,width,crop = crops[rid]
                picture = add(c.ContentMatrix(byte_schema,height,width,crop))
                feedbacks[rid] = add(c.ContentFeedback(2 if phase == 'practice' else 1,picture,predicate if phase == 'practice' else 0))
        default_feedback = add(c.ContentFeedback(3 if phase == 'practice' else 1,matrix,predicate if phase == 'practice' else 0)) if phase != 'teach' else feedbacks[page['correct'][0]]
        trace_id = add(None) if phase != 'heldout' else 0
        node_id = add(None)
        built.append({'page': page, 'node_id': node_id, 'matrix': matrix, 'regions': region_set,
                      'predicate': predicate, 'feedbacks': feedbacks, 'default_feedback': default_feedback,
                      'trace_id': trace_id})
    owner_pages = []
    for index,item in enumerate(built):
        page = item['page'];phase = page['phase'];node = item['node_id']
        next_node = built[index+1]['node_id'] if index+1<len(built) else 0
        cases = ()
        if phase == 'practice':
            cases = tuple(c.ContentLessonCase(1,(rid,),item['feedbacks'][rid],next_node) for rid in sorted(page['correct']))
        if item['trace_id']:
            selected = page['correct'][0]
            actions = tuple(bytes.fromhex(action) for action in page['passive_actions']) if 'passive_actions' in page else (bytes((1,0,*selected.to_bytes(2,'big'))), bytes.fromhex('03000000'))
            put(item['trace_id'],c.ContentPassiveTrace(item['matrix'],item['regions'],item['matrix'],0,
                actions,1 if phase=='practice' else 3,item['feedbacks'][selected],next_node))
        put(node,c.ContentLessonNode(3 if phase=='teach' else 5,1,
            {'teach':3,'practice':1,'heldout':2}[phase],0,item['matrix'],item['regions'],
            item['predicate'],item['trace_id'],1,local_budget,cases,item['default_feedback'],node if phase=='practice' else next_node))
        owner_pages.append({'id':page['id'],'family':page['family'],'phase':phase,'node_id':node,
                            'surface_matrix_id':item['matrix'],'region_set_id':item['regions'],
                            'correct':list(page['correct']),'evidence':page['evidence']})
    root_id = add(c.ContentRoot(built[0]['node_id'],len(pages)*local_budget*4))
    raw = c.encode_content_v0(c.ContentAuthoringProjection(0,tuple(records)))
    c.stream_validation(raw)
    return raw,{'schema':'golden-board.m2-lesson-owner/v1','content_sha256':sha(raw),
                'content_bytes':len(raw),'root_id':root_id,'pages':owner_pages,
                'local_budget':local_budget,'global_budget':len(pages)*local_budget*4}


def slice_declaration(raw, legacy_declaration):
    """Emit logical authoring data, not encoded content as a Rust preimage."""
    view = c.projection_view(c.stream_validation(raw))
    records = []
    for record in view.records:
        payload = asdict(record.payload)
        if record.kind == 2:
            for key in ('entries', 'allowed_mask'):
                payload.pop(key)
        if record.kind == 12:
            payload['actions'] = [action.hex() for action in payload['actions']]
        records.append({'record_id':record.record_id, 'kind':record.kind,
                        'payload':payload})
    # The manifest serializer deliberately rejects tuples and null values.
    value = json.loads(json.dumps({'schema':'golden-board.m2-slice/v1',
        'legacy_declaration_sha256':sha(legacy_declaration),
        'lesson_records':records}))
    return canonical_manifest.serialize_manifest(value)


def _wire(value):
    if isinstance(value, bytes):
        return value.hex()
    if is_dataclass(value):
        rename = {'committed_response':'committed_response_hex',
                  'available_actions':'available_actions_hex',
                  'actions':'actions_hex', 'action':'action_hex',
                  'action_bytes':'action_hex'}
        return {rename.get(field.name, field.name):_wire(getattr(value, field.name))
                for field in fields(value)}
    if isinstance(value, (tuple, list)):
        return [_wire(item) for item in value]
    return value


def reference_transcript(raw, owner):
    """Replay every page through the generic public Python interpreter."""
    runner = m2_runner.GenericRunner(raw, label_suppressed=True)
    commands = []
    frames = [_wire(runner.frame())]
    for page in owner['pages']:
        if runner.frame().current_node_id != page['node_id']:
            raise ValueError('owner path differs from actual content path')
        for action in (bytes.fromhex(f"0100{page['correct'][0]:04x}"), bytes.fromhex('03000000')):
            runner.perform(action)
            commands.append({'action_hex':action.hex()})
            frames.append(_wire(runner.frame()))
        if runner.frame().can_advance:
            runner.advance()
            commands.append({'advance':True})
            frames.append(_wire(runner.frame()))
    return {'commands':commands, 'frames':frames}
