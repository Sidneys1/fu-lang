"""Static types and the `Type` type."""

from dataclasses import dataclass, field, InitVar
from typing import Optional
from collections import OrderedDict
from functools import partial

from ...compiler.tokenizer import SpecialOperatorType
from .. import TypeBase
from . import ComposedType, CallSignature

# def _type_generics():
#     return {'T': StaticType.TYPE_T}

TYPE_TYPE = TypeBase('type', is_builtin=True)


@dataclass(frozen=True, kw_only=True, slots=True)
class StaticType(TypeBase):
    """Describes the static storage of a class (vs an instance of one)."""

    instance_type: ComposedType | None = field(init=False, default=None)
    name: str = field(init=False, default='static<???>')
    static_members: OrderedDict[str, TypeBase] = field(init=False, default_factory=OrderedDict)
    callable: CallSignature | None = field(init=False, default=None)
    _resolved: bool = field(init=False, default=False)
    is_builtin: bool = field(init=False, default=False)

    def resolve(self,
                resolved: Optional['ComposedType'],
                static_members: OrderedDict[str, TypeBase],
                name: str | None = None):
        if self._resolved:
            raise ValueError("Already resolved.")

        _set = partial(object.__setattr__, self)
        _set('_resolved', True)

        _set('static_members', static_members)

        if resolved is None:
            assert name is not None
            _set('name', f"static<{name}>")
            return

        _set('instance_type', resolved)
        assert self.instance_type is not None
        _set('name', f"static<{self.instance_type.name if self.instance_type is not None else self.name}>")

        if self.instance_type is not None:
            # get constructor
            _set('callable',
                 self.instance_type.special_operators.get(SpecialOperatorType.Constructor, ((), self.instance_type)))


# @dataclass(frozen=True, kw_only=True, slots=True)
# class StaticType(GenericType):  # type: ignore[misc]
#     """Describes the static storage of a class (not an instance of one)."""

#     TYPE_T: ClassVar[GenericType.GenericParam] = GenericType.GenericParam('T')  # pylint: disable=too-many-function-args

#     of: InitVar[ComposedType] = field(kw_only=False, default=TYPE_T)

#     name: str = field(init=False, default='Static')
#     underlying: ComposedType = field(init=False)
#     const: bool = field(default=False)
#     is_builtin: bool = field(init=False, default=False)
#     special_operators: dict[SpecialOperatorType, CallSignature] = field(default_factory=dict)

#     indexable: tuple[TypeBase, ...] | None = field(default=None)  # type: ignore

#     generic_params: dict[str, TypeBase] = field(init=False, default_factory=dict)

#     size: int | None = field(default=None)
#     instance_members: OrderedDict[str, TypeBase] = field(default_factory=OrderedDict)
#     static_members: OrderedDict[str, TypeBase] = field(default_factory=OrderedDict)
#     readonly: set[str] = field(default_factory=set)
#     inherited_members: set[str] = field(default_factory=set)
#     generic_inheritance: tuple[GenericType, ...] = field(default=())

#     reference_type: bool = field(init=False, default=True)

#     inherits: tuple[TypeBase] = field(default=())  # type: ignore[misc]

#     callable: CallSignature | None = field(init=False, default=None)

#     # pylint: disable=arguments-differ
#     def __post_init__(self, of: ComposedType | GenericType.GenericParam) -> None:  # type: ignore[override]
#         GenericType.__post_init__(self)

#         self.generic_params['T'] = of

#         if of is StaticType.TYPE_T:
#             return

#         # Make sure T is in fact a type...
#         assert isinstance(of, TypeBase), f"Underlying is unexpectedly a {type(self.underlying).__name__}!"

#         _set = partial(object.__setattr__, self)

#         # Set underlying property to match T
#         _set('underlying', of)

#         # self.generic_params.

#         # update callable
#         # TODO: static-only types?
#         if isinstance(self.underlying, ComposedType):
#             if SpecialOperatorType.Constructor in self.underlying.special_operators:
#                 params, ret = self.underlying.special_operators[SpecialOperatorType.Constructor]
#             else:
#                 params, ret = (), self.underlying.this_type

#             assert isinstance(ret, ThisType)
#             # assert ret.resolved is not None and ret.resolved is self.underlying, f"{ret.resolved=} for {self.underlying.name}"

#             _set('callable', (params, ret))

# TODO: update size

# @staticmethod
# def of(t: TypeBase) -> 'StaticType':
#     return StaticType().resolve_generic(T=t)

# StaticType()

# def _typetype_size(self: TypeType) -> int | None:
#     # TODO
#     return None

# def _typetype_callable(self: TypeType) -> CallSignature | None:
#     if isinstance(self.underlying,
#                   ComposedType) and SpecialOperatorType.Constructor in self.underlying.special_operators:
#         # input(self.underlying.special_operators)
#         params, ret = self.underlying.special_operators[SpecialOperatorType.Constructor]
#         from ... import ThisType
#         assert isinstance(ret, ThisType)
#         assert ret.resolved is not None
#         return params, ret.resolved
#     return None

# # def _typetype_indexable(self: TypeType) -> tuple[TypeBase, ...] | None:
# #     # Determined by whether we have a static `op[]` member.
# #     # TODO
# #     return None

# TypeType.size = property(_typetype_size)  # type: ignore[misc,assignment]
# TypeType.callable = property(_typetype_callable)  # type: ignore[misc,assignment]

# @TypeType.size.setter
# def _size_setter(self: TypeType, _):
#     raise RuntimeError()

# @TypeType.callable.setter
# def _callable_setter(self: TypeType, _):
#     raise RuntimeError()

# TypeType.indexable = property(_typetype_indexable)  # type: ignore[misc,assignment]

__all__ = ('TYPE_TYPE', )
