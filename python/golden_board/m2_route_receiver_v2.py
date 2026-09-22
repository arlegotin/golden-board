"""Bounded observation-only route2 framing and executable relationships.

This parser has no authoring/source/clean-content inputs. Numeric DEFINE values
are exposed for subsequent knowledge-use validation; their framing alone is
not semantic acquisition proof or promoted candidate admission.
"""
from dataclasses import dataclass
from math import gcd

from . import bootstrap, recipe_wire_v1
from .m2_decoder import DecoderError, _CALIBRATIONS, _route_records
from .m2_program_refinement_v2 import mapping_program_refined, transport_programs_refined
from .m2_route_semantics_v2 import validate_local_definitions
from .m2_resources_v2 import recipe_storage, recipe_workspace, definition_workspace

_STAGES = (0,0,1,1,2,2,3,3,4,4,5,5)
_WIDTHS = (16,64,96,296,226,210,636,544,464,430,314,2421)
_PRIMARY = (101,102,103,104,105,211,107,113,109,110,111,112)
_RECIPES = (1,2,3,4,30,90,92,99,*range(100,106),*range(107,114),201,202,203,210,211,212,213,214)
_TABLES = (3,4,5,10,11,12,13,14,15,17,18,19,20,21)


@dataclass(frozen=True, slots=True)
class ObservedRouteV2:
    sector: int
    prefix_bytes: int
    package: recipe_wire_v1.RecipePackageV1
    definitions: tuple[bytes, ...]
    commitments: object
    example_count: int
    inventory_section_id: int
    mapping_values: tuple[int, ...]
    primitive_steps: int
    peak_scratch_bytes: int


    @property
    def mapping(self):
        keys = ('interior_side','population','unit_population','unit_multiplier',
                'unit_inverse_multiplier','cell_multiplier','offset','cell_inverse_multiplier')
        return dict(id='affine-slot-then-interior-v2', **dict(zip(keys,self.mapping_values,strict=True)))


def _require(condition, reason):
    if not condition:
        raise DecoderError('route-v2.'+reason)


def _skeleton():
    rows = []
    for fact, stage in enumerate(_STAGES,1):
        rows.extend((stage,kind,100*fact+kind,fact,None if kind == 1 else _PRIMARY[fact-1])
                    for kind in (1,2,3))
        if fact == 6:
            rows.extend((stage,2+i%2,610+i,6,recipe)
                        for i,recipe in enumerate((105,211,211,212,214,214)))
        if fact == 12:
            rows.extend(((5,2,1210,12,203),(5,3,1211,12,203)))
    rows.extend(((5,5,6001,0,None),(5,6,7001,0,None),(5,7,7002,0,None)))
    return tuple(rows)


def _smallest_slot_multiplier(interior, units, adapter):
    population = interior**2
    affine = 2*interior-1
    window = max(32,interior//8)
    tests = 0
    try:
        for candidate in range(1,units):
            if gcd(candidate,units) != 1:
                continue
            valid = True
            for distance in range(1,5):
                tests += 1
                residue = candidate*distance % units
                for delta in (residue,residue-units):
                    row,column = divmod(affine*1728*delta % population,interior)
                    rows = (row,) if column == 0 else (row,(row+1)%interior)
                    if any(max(min(r,interior-r),min(column,interior-column)) < window for r in rows):
                        valid = False
                        break
                if not valid:
                    break
            if valid:
                return candidate
        raise DecoderError('route-v2.slot-multiplier')
    finally:
        adapter('mapping-search',tests,64)


def _decode_observed_route_v2(data, side, width, sector, usage, charge, adapter, retain):
    """Check observed frames/examples and derive the carried placement recipe.

    Only the declared prefix is parsed. Deliberately does not regenerate an
    expected route or read any source/spec/artifact file.
    """
    _require(type(data) is bytes and 64 <= len(data) <= 32768,'input')
    _require(type(side) is int and type(width) is int and type(sector) is int
             and 64 <= side <= 2048 and side % 8 == 0 and 8 <= width <= 128
             and width % 8 == 0 and 2*width+8 <= side and 0 <= sector < 4,'geometry')
    _require(data[:32] == _CALIBRATIONS[sector] and data[32:40] == b'GBROUTE\0'
             and data[40:46] == b'\0\2'+bytes((sector,sector))+b'\0\x08'
             and data[60:64] == b'\x01\0\0\0','envelope')
    count = int.from_bytes(data[46:48],'big')
    end = 64+int.from_bytes(data[48:52],'big')
    package_bytes = int.from_bytes(data[52:56],'big')
    _require(count == 47 and 64 <= end <= len(data) and end*8 <= width*(side-width)
             and int.from_bytes(data[56:60],'big') == end*8
             and 64 <= package_bytes <= end-64,'length')
    adapter('route-frame',end,8*count)
    records, packages = _route_records(data[64:end], count, package_bytes)
    _require(len(packages) == 1,'package-count')
    _require(all((stage,kind,rid) == (a,b,sector*10000+c)
                 for (stage,kind,rid,_),(a,b,c,_,_) in zip(records,_skeleton(),strict=True)),
             'record-order')
    raw_package = packages[0]
    if (len(raw_package) >= 64 and raw_package[:8] == b'GBRECP0\0'
            and (int.from_bytes(raw_package[36:44],'big') > bootstrap.RECIPE_STEP_MAX
                 or int.from_bytes(raw_package[44:48],'big') > bootstrap.RECIPE_SCRATCH_MAX)):
        raise DecoderError('resource-limit')
    adapter('recipe-parse',len(raw_package),recipe_workspace(raw_package))
    try:
        package = recipe_wire_v1.decode_recipe_package_v1(packages[0],8)
    except bootstrap.BootstrapReject as error:
        raise DecoderError('route-v2.package') from error
    logical = package.logical
    retain('active-route-package',recipe_storage(raw_package))
    _require(tuple(r.recipe_id for r in logical.recipes) == _RECIPES
             and tuple(t.table_id for t in logical.tables) == _TABLES,'program-set')
    adapter('program-refinement',logical.total_node_count,
            32*logical.total_node_count+8*logical.total_edge_count+8*len(logical.tables))
    _require(mapping_program_refined(package),'mapping-program')
    _require(transport_programs_refined(package),'transport-program')
    recipes = {r.recipe_id:r for r in logical.recipes}
    group_program = recipes[110]
    _require(tuple((d.value_type,d.width) for d in group_program.inputs) ==
             ((bootstrap.UINT,2),)*6+((bootstrap.BOOL,1),)*3
             and tuple((d.value_type,d.width) for d in group_program.outputs) ==
             ((bootstrap.STATUS,16),(bootstrap.UINT,2),(bootstrap.UINT,8),(bootstrap.BOOL,1)),
             'group-interface')
    body_program = recipes[202]
    _require(tuple((d.value_type,d.width) for d in body_program.inputs) ==
             ((bootstrap.BYTES,16384),(bootstrap.UINT,16))
             and tuple((d.value_type,d.width) for d in body_program.outputs) ==
             ((bootstrap.STATUS,16),(bootstrap.UINT,16),(bootstrap.BYTES,16384)),
             'body-interface')
    definitions = []
    example_count = steps = scratch = 0

    def evaluate(recipe_id, values):
        nonlocal steps, scratch
        recipe = recipes[recipe_id]
        charge(recipe.primitive_steps,recipe.peak_live_scratch_bytes)
        input_bytes = sum(map(len,values))
        output_bytes = sum(d.width if d.value_type == bootstrap.BYTES else (d.width+7)//8 for d in recipe.outputs)
        adapter('route-example',input_bytes,input_bytes+output_bytes+8*(len(recipe.inputs)+len(recipe.outputs)))
        steps += recipe.primitive_steps
        scratch = max(scratch,recipe.peak_live_scratch_bytes)
        usage[:] = (steps,scratch)
        _require(steps <= 0xffffffffffffffff,'resource-overflow')
        try:
            return recipe_wire_v1.evaluate_recipe_v1(package,recipe_id,values)
        except bootstrap.BootstrapReject as error:
            raise DecoderError('route-v2.example') from error

    for (stage,kind,rid,payload),(want_stage,want_kind,want_id,fact,recipe_id) in zip(records,_skeleton(),strict=True):
        _require((stage,kind,rid) == (want_stage,want_kind,sector*10000+want_id),'record-order')
        if kind == 1:
            expected_width = _WIDTHS[fact-1]
            _require(len(payload) == 14+expected_width
                     and payload[:4] == fact.to_bytes(2,'big')*2
                     and payload[4:6] == bytes((bootstrap.BYTES,0))
                     and int.from_bytes(payload[6:10],'big') == expected_width
                     and payload[10:14] == b'\0\0\0\1','definition')
            definitions.append(payload[14:])
        elif kind in (2,3):
            _require(len(payload) >= 14 and int.from_bytes(payload[:2],'big') == fact
                     and int.from_bytes(payload[2:4],'big') == recipe_id,'example-header')
            ilen,olen = int.from_bytes(payload[4:8],'big'),int.from_bytes(payload[8:12],'big')
            _require(olen >= 2 and len(payload) == 12+ilen+olen,'example-length')
            if fact == 10:
                start = 294+12*(4+(kind == 3))
                trace = definitions[9][start:start+12]
                _require(payload[12:] == trace[:9]+b'\0\0'+trace[9:],'group-primary')
            widths = tuple(d.width if d.value_type == bootstrap.BYTES else (d.width+7)//8
                           for d in recipes[recipe_id].inputs)
            _require(sum(widths) == ilen,'example-interface')
            cursor,values = 12,[]
            for size in widths:
                values.append(payload[cursor:cursor+size])
                cursor += size
            result = evaluate(recipe_id,tuple(values))
            _require(result.status.to_bytes(2,'big')+b''.join(result.outputs) == payload[cursor:]
                     and (not result.status or not result.outputs),'example-result')
            example_count += 1
        elif kind == 5:
            _require(payload == packages[0],'package-record')
        elif kind == 6:
            _require(payload == b'\0\0\0\1','endpoint')
        else:
            _require(payload == b'','end')

    # The complete table is carried; this lookup is selected by observed
    # geometry. Its current element is independently checked against the
    # bounded separation rule rather than accepted from a host lookup table.
    table = next(t for t in logical.tables if t.table_id == 17)
    _require((table.element_type,table.element_width,table.element_count) ==
             (bootstrap.UINT,8,256),'mapping-table')
    interior = side-2*width
    population,units = interior**2,interior**2//1728
    _require(units >= 2,'mapping-population')
    slot = table.payload[interior//8]
    _require(slot == _smallest_slot_multiplier(interior,units,adapter),'mapping-slot')
    recipe = recipes[109]
    _require(tuple((d.value_type,d.width) for d in recipe.inputs) ==
             ((bootstrap.UINT,32),(bootstrap.UINT,16),(bootstrap.UINT,16))
             and tuple((d.value_type,d.width) for d in recipe.outputs[1:]) ==
             ((bootstrap.UINT,32),),'mapping-interface')
    values = []
    for index in (0,1,population-1):
        result = evaluate(109,(index.to_bytes(4,'big'),side.to_bytes(2,'big'),width.to_bytes(2,'big')))
        _require(result.status == 0 and len(result.outputs) == 1,'mapping-result')
        values.append(int.from_bytes(result.outputs[0],'big'))
    affine = (values[1]-values[0]) % population
    offset = values[0]
    _require(affine == 2*interior-1 and offset == (8*40503+width*257) % population
             and (affine*(population-1)+offset) % population == values[2],'mapping-rule')
    mapping = dict(id='affine-slot-then-interior-v2',interior_side=interior,population=population,
                   unit_population=units,unit_multiplier=slot,unit_inverse_multiplier=pow(slot,-1,units),
                   cell_multiplier=affine,offset=offset,cell_inverse_multiplier=pow(affine,-1,population))
    for start in (*range(294,402,12),412):
        trace = definitions[9][start:start+12]
        result = evaluate(110,tuple(bytes((v,)) for v in trace[:9]))
        _require(result.status == 0 and b''.join(result.outputs) == trace[9:],'group-decision-trace')
    adapter('definition-validation',sum(map(len,definitions)),definition_workspace(definitions,raw_package))
    commitments = validate_local_definitions(tuple(definitions),package,side=side,width=width,sector=sector)
    return ObservedRouteV2(sector,end,package,tuple(definitions),commitments,example_count,1,
                           tuple(value for key,value in mapping.items() if key != 'id'),steps,scratch)


class RouteRejectionV2(DecoderError):
    __slots__ = ('primitive_steps','peak_scratch_bytes')

    def __init__(self, reason, steps, scratch):
        super().__init__(reason)
        self.primitive_steps = steps
        self.peak_scratch_bytes = scratch


def decode_observed_route_v2(data, side, width, sector, *, charge=None, adapter=None, retain=None):
    """Return observed facts or rejection with exact invoked VM charge."""
    usage = [0,0]
    retain = retain or (lambda key,size: None)
    try:
        return _decode_observed_route_v2(data,side,width,sector,usage,
            charge or (lambda steps,scratch: None),adapter or (lambda kernel,work,workspace: None),retain)
    except DecoderError as error:
        raise RouteRejectionV2(error.reason,*usage) from error
    finally:
        retain('active-route-package',0)
