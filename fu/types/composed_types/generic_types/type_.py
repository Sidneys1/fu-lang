"""Static types and the `Type` type."""

from dataclasses import dataclass, field, InitVar
from typing import ClassVar
from collections import OrderedDict
from functools import partial

from ....compiler.tokenizer import SpecialOperatorType
from ... import TypeBase
from . import ComposedType, ThisType, GenericType, CallSignature


def _type_generics():
    return {'T': StaticType.TYPE_T}


TYPE_TYPE = TypeBase('type', size=None, is_builtin=True)


@dataclass(frozen=True, kw_only=True, slots=True)
class StaticType(GenericType):  # type: ignore[misc]
    """Describes the static storage of a class (not an instance of one)."""

    TYPE_T: ClassVar[GenericType.GenericParam] = GenericType.GenericParam('T')  # pylint: disable=too-many-function-args

    of: InitVar[ComposedType] = field(kw_only=False, default=TYPE_T)

    name: str = field(init=False, default='Static')
    underlying: ComposedType = field(init=False)
    const: bool = field(init=False, default=False)
    is_builtin: bool = field(init=False, default=False)
    special_operators: dict[SpecialOperatorType, CallSignature] = field(init=False, default_factory=dict)

    indexable: tuple[TypeBase, ...] | None = field(init=False, default=None)  # type: ignore

    generic_params: dict[str, TypeBase] = field(init=False, default_factory=dict)

    size: int | None = field(init=False, default=None)
    instance_members: OrderedDict[str, TypeBase] = field(init=False, default_factory=OrderedDict)
    static_members: OrderedDict[str, TypeBase] = field(init=False, default_factory=OrderedDict)
    readonly: set[str] = field(init=False, default_factory=set)
    inherited_members: set[str] = field(init=False, default_factory=set)
    generic_inheritance: tuple[GenericType, ...] = field(init=False, default=())

    reference_type: bool = field(init=False, default=True)

    inherits: tuple[TypeBase] = field(init=False)  # type: ignore[misc]

    callable: CallSignature | None = field(init=False, default=None)

    # pylint: disable=arguments-differ
    def __post_init__(self, of: ComposedType | GenericType.GenericParam) -> None:  # type: ignore[override]
        GenericType.__post_init__(self)

        self.generic_params['T'] = of

        if of is StaticType.TYPE_T:
            return

        # Make sure T is in fact a type...
        assert isinstance(of, TypeBase), f"Underlying is unexpectedly a {type(self.underlying).__name__}!"

        _set = partial(object.__setattr__, self)

        # Set underlying property to match T
        _set('underlying', of)

        # update callable
        # TODO: static-only types?
        if isinstance(self.underlying, ComposedType):
            if SpecialOperatorType.Constructor in self.underlying.special_operators:
                params, ret = self.underlying.special_operators[SpecialOperatorType.Constructor]
            else:
                params, ret = (), self.underlying.this_type

            assert isinstance(ret, ThisType)
            # assert ret.resolved is not None and ret.resolved is self.underlying, f"{ret.resolved=} for {self.underlying.name}"

            _set('callable', (params, ret))

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

__all__ = ('StaticType', 'TYPE_TYPE')
