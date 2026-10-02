"""Structural admission of source-owned neutral program refinements.

No route, lesson, carrier or expected result is generated/read here. The two
small source program constructors encode known generic transform semantics.
"""
from functools import lru_cache

from . import bootstrap, m2_recipe, recipe_wire_v1
from .m2_body_recipe_v1 import body_recipe_programs_v1


def _program_key(recipe):
    return (tuple((d.value_type,d.width) for d in recipe.inputs),
            tuple((d.value_type,d.width) for d in recipe.outputs),
            tuple((n.opcode,n.output_type,n.output_width,n.arguments,n.auxiliary_u16,n.auxiliary_u32,n.immediate_u64)
                  for n in recipe.nodes))


def _source_key(body):
    return (tuple(body.inputs),tuple(body.outputs),
            tuple((op,kind,width,args,aux,0,imm) for op,kind,width,args,aux,imm in body.nodes))


def _closure(logical, roots):
    programs = {r.recipe_id:r for r in logical.recipes}
    tables = {t.table_id:t for t in logical.tables}
    used_programs,used_tables = set(),set()
    pending = list(roots)
    while pending:
        rid = pending.pop()
        if rid in used_programs:
            continue
        if rid not in programs:
            return None
        used_programs.add(rid)
        for node in programs[rid].nodes:
            if node.opcode == 2:
                used_tables.add(node.auxiliary_u16)
            elif node.opcode == 22:
                pending.append(node.auxiliary_u16)
    if not used_tables <= tables.keys():
        return None
    return (tuple((rid,_program_key(programs[rid])) for rid in sorted(used_programs)),
            tuple((tid,tables[tid].element_type,tables[tid].element_width,
                   tables[tid].element_count,tables[tid].payload) for tid in sorted(used_tables)))


@lru_cache(maxsize=1)
def _expected():
    mapping = _source_key(m2_recipe._r3_fact(109,8))
    body = tuple((p.recipe_id,_source_key(p)) for p in body_recipe_programs_v1() if p.recipe_id in (201,202))
    tables = ((3,bootstrap.UINT,16,256,b''.join(i.to_bytes(2,'big') for i in range(256))),
              (4,bootstrap.BYTES,1,1,b'\0'),(5,bootstrap.UINT,8,256,bytes(range(256))))
    neutral = bootstrap.decode_recipe_package(m2_recipe.build_r3_recipe_package(),7)
    return mapping,body,tables,_closure(neutral,(30,113))


def mapping_program_refined(package):
    if type(package) is not recipe_wire_v1.RecipePackageV1 or package.profile_version != 8:
        return False
    observed = tuple(r for r in package.logical.recipes if r.recipe_id == 109)
    return len(observed) == 1 and _program_key(observed[0]) == _expected()[0]


def body_program_refined(package):
    if type(package) is not recipe_wire_v1.RecipePackageV1 or package.profile_version != 8:
        return False
    programs = tuple((r.recipe_id,_program_key(r)) for r in package.logical.recipes if r.recipe_id in (201,202))
    tables = tuple((t.table_id,t.element_type,t.element_width,t.element_count,t.payload)
                   for t in package.logical.tables if t.table_id in (3,4,5))
    _,expected_programs,expected_tables,_ = _expected()
    return programs == expected_programs and tables == expected_tables


def transport_programs_refined(package):
    if type(package) is not recipe_wire_v1.RecipePackageV1 or package.profile_version != 8:
        return False
    return _closure(package.logical,(30,113)) == _expected()[3]
