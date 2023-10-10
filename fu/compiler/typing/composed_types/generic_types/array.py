from typing import ClassVar, Self
from dataclasses import dataclass, field

from ...integral_types import USIZE_TYPE, SIZE_TYPE

from . import GenericType, TypeBase

# def _array_generics():
#     return {'T': ArrayType.ARRAY_T}

# @dataclass(frozen=True, kw_only=True, slots=True)
# class ArrayType(GenericType):
#     """Describes an array of elements."""
#     ARRAY_T = GenericType.GenericParam('T')

#     name: str = field(init=False, default='Array')
#     of_type: TypeBase = field(init=False)
#     indexable: tuple[Self, ...] = field(init=False)

#     generic_params: dict[str, TypeBase] = field(default_factory=_array_generics)

#     size: ClassVar[None] = None
#     members: ClassVar[dict[str, TypeBase]] = {'length': USIZE_TYPE}
#     readonly: ClassVar[set[str]] = {'length'}
#     reference_type: ClassVar[bool] = True
#     inherits: ClassVar[None] = None
#     callable: ClassVar[None] = None

#     def __post_init__(self):
#         names = ','.join(k if v is None else v.name for k, v in self.generic_params.items())
#         object.__setattr__(self, '_name', self.name)
#         object.__setattr__(self, 'name', f"{self.name}<{names}>")
#         indexable: tuple[Self, ...] = (SIZE_TYPE, ), self.generic_params['T']
#         object.__setattr__(self, 'of_type', self.generic_params['T'])
#         object.__setattr__(self, 'indexable', indexable)

#     def of(self, t: TypeBase) -> 'ArrayType':
#         return self.resolve_generic({'T': t})

ARRAY_GENERIC_PARAM = GenericType.GenericParam('T')
ARRAY_TYPE = GenericType('Array',
                         size=None,
                         reference_type=True,
                         indexable=((SIZE_TYPE, ), ARRAY_GENERIC_PARAM),
                         members={'length': USIZE_TYPE},
                         readonly={'length'},
                         generic_params={'T': ARRAY_GENERIC_PARAM})
