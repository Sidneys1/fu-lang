# from dataclasses import dataclass, field
# from typing import Self, ClassVar

# from ....compiler.tokenizer import SpecialOperatorType

# from ... import ThisType, TypeBase

# from . import GenericType, ComposedType

# def _interface_generics():
#     return {'T': InterfaceType.TYPE_T}

# INTERFACE_TYPE = TypeBase('interface', size=None)

# @dataclass(frozen=True, kw_only=True, slots=True)
# class InterfaceType(GenericType):
#     """Describes a interface (not an instance of one)."""

#     TYPE_T = GenericType.GenericParam('T')

#     name: str = field(init=False, default='Interface')
#     underlying: TypeBase = field(init=False)

#     indexable: tuple[Self, ...] | None = field(init=False)

#     generic_params: dict[str, TypeBase] = field(default_factory=_interface_generics)

#     size: int | None = field(init=False)
#     members: dict[str, TypeBase] = field(default_factory=dict)
#     readonly: set[str] = field(default_factory=set)
#     reference_type: bool = True
#     inherits: ClassVar[tuple[TypeBase]] = (INTERFACE_TYPE, )

#     callable: tuple[tuple[TypeBase, ...], TypeBase] | None = field(init=False)

#     def __post_init__(self):
#         GenericType.__post_init__(self)
#         assert isinstance(self.generic_params['T'],
#                           TypeBase), f"Underlying is unexpectedly a {type(self.underlying).__name__}!"
#         object.__setattr__(self, 'underlying', self.generic_params['T'])

# def _interfacetype_size(self: InterfaceType) -> int | None:
#     # TODO
#     return None

# def _interfacetype_callable(self: InterfaceType) -> tuple[tuple[TypeBase, ...], TypeBase] | None:
#     if isinstance(self.underlying,
#                   ComposedType) and SpecialOperatorType.Constructor in self.underlying.special_operators:
#         # input(self.underlying.special_operators)
#         params, ret = self.underlying.special_operators[SpecialOperatorType.Constructor]
#         assert isinstance(ret, ThisType)
#         return params, ret.resolved
#     return None

# def _interfacetype_indexable(self: InterfaceType) -> tuple[Self, ...] | None:
#     # Determined by whether we have a static `op[]` member.
#     # TODO
#     return None

# InterfaceType.size = property(_interfacetype_size)
# InterfaceType.callable = property(_interfacetype_callable)
# InterfaceType.indexable = property(_interfacetype_indexable)

# __all__ = ('InterfaceType', 'INTERFACE_TYPE')
