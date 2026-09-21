"""Complete bounded profile8 placement, distinct from modular recipe109."""
from dataclasses import dataclass
from functools import lru_cache

from .m2_carrier import unit_multiplier_table


@dataclass(frozen=True, slots=True)
class MappingParameters:
    interior: int
    population: int
    units: int
    slot_multiplier: int
    slot_inverse: int
    cell_multiplier: int
    cell_inverse: int
    offset: int


@lru_cache(maxsize=3815)
def _parameters(side, width):
    interior = side - 2 * width
    population = interior * interior
    units = population // 1728
    multiplier = unit_multiplier_table()[interior // 8]
    if units < 2 or multiplier == 0:
        raise ValueError('mapping_v2.no_fit')
    affine = 2 * interior - 1
    return MappingParameters(interior, population, units, multiplier,
        pow(multiplier, -1, units), affine, pow(affine, -1, population),
        (8 * 40503 + width * 257) % population)


def mapping_parameters(side, width):
    # Validate before the cache: Python floats/bools can share integer keys.
    if (type(side) is not int or type(width) is not int or not 64 <= side <= 2048
            or not 8 <= width <= 128 or side % 8 or width % 8 or 2 * width + 8 > side):
        raise ValueError('mapping_v2.geometry')
    return _parameters(side, width)


def map_unit_bit(side, width, unit_id, encoded_bit):
    row = mapping_parameters(side, width)
    if (type(unit_id) is not int or type(encoded_bit) is not int
            or not 1 <= unit_id <= row.units or not 0 <= encoded_bit < 1728):
        raise ValueError('mapping_v2.unit_bit')
    slot = row.slot_multiplier * (unit_id - 1) % row.units
    logical = 1728 * slot + encoded_bit
    # Admitted geometry bounds every intermediate below 2**64.
    return (row.cell_multiplier * logical + row.offset) % row.population


def invert_interior_cell(side, width, physical):
    row = mapping_parameters(side, width)
    if type(physical) is not int or not 0 <= physical < row.population:
        raise ValueError('mapping_v2.physical')
    logical = row.cell_inverse * ((physical - row.offset) % row.population) % row.population
    if logical >= 1728 * row.units:
        return 1, 0, 0
    slot, bit = divmod(logical, 1728)
    unit_id = row.slot_inverse * slot % row.units + 1
    return 0, unit_id, bit
