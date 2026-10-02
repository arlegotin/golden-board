"""Source-built profile8 recipes; no route or carrier promotion is implied."""
from functools import lru_cache

from . import m2_recipe, recipe_wire_v1
from .m2_body_recipe_v1 import body_recipe_programs_v1


@lru_cache(maxsize=1)
def build_revision_recipe_package() -> bytes:
    # Profile-number parity selected checks in historical candidates. Profile8
    # is expressly CRC32C: retain those programs and replace only the affine
    # recipe's profile-derived offset, then append the full bounded decoder.
    bodies = tuple(m2_recipe._r3_fact(109, 8) if body.recipe_id == 109 else body
                   for body in m2_recipe._r3_recipe_bodies()) + body_recipe_programs_v1()
    tables = m2_recipe._r3_eh_tables()
    return _encode_profile8_package(bodies, tables)


def _encode_profile8_package(bodies, tables) -> bytes:
    """Serialize source programs with complete independently derived resources."""
    records = []
    resources = {}
    total_nodes = total_edges = 0
    for body in bodies:
        raw, edges, steps, scratch = m2_recipe._recipe_record(
            body.recipe_id, body.inputs, body.outputs, body.nodes, resources)
        records.append(raw)
        resources[body.recipe_id] = steps, scratch
        total_nodes += len(body.nodes)
        total_edges += edges
    be = int.to_bytes
    package_size = 64 + sum(map(len, tables)) + sum(map(len, records))
    table_payload = sum(int.from_bytes(table[12:16], 'big') for table in tables)
    header = b''.join((
        b'GBRECP0\0', bytes(4), be(8, 2, 'big'), bytes(2),
        be(len(records), 2, 'big'), be(len(tables), 2, 'big'),
        be(total_nodes, 4, 'big'), be(total_edges, 4, 'big'),
        be(table_payload, 4, 'big'), be(package_size, 4, 'big'),
        be(max(row[0] for row in resources.values()), 8, 'big'),
        be(max(row[1] for row in resources.values()), 4, 'big'), bytes(16),
    ))
    expanded = header + b''.join(tables) + b''.join(records)
    # The explicit new codec performs complete logical validation under the
    # new profile admission, then writes its one prescribed compact grammar.
    return recipe_wire_v1.encode_recipe_package_v1(expanded, 8)
