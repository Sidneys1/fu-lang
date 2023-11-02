from dataclasses import dataclass, field
from typing import ClassVar, Self

from ....compiler.tokenizer import SpecialOperatorType
from ... import TypeBase
from . import ComposedType, GenericType


def _type_generics():
    return {'T': TypeType.TYPE_T}


TYPE_TYPE = TypeBase('type', size=None, is_builtin=True)


@dataclass(frozen=True, kw_only=True, slots=True)
class TypeType(GenericType):
    """Describes a type (not an instance of one)."""

    TYPE_T = GenericType.GenericParam('T')

    name: str = field(init=False, default='Type')
    underlying: TypeBase = field(init=False)

    indexable: tuple[TypeBase, ...] | None = field(init=False)  # type: ignore

    generic_params: dict[str, TypeBase] = field(default_factory=_type_generics)

    size: int | None = field(init=False)
    members: dict[str, TypeBase] = field(default_factory=dict)
    readonly: set[str] = field(default_factory=set)
    reference_type: bool = True
    inherits: ClassVar[tuple[TypeBase]] = (TYPE_TYPE, )  # type: ignore[misc]

    callable: tuple[tuple[TypeBase, ...], TypeBase] | None = field(init=False)

    def __post_init__(self):
        GenericType.__post_init__(self)
        assert isinstance(self.generic_params['T'],
                          TypeBase), f"Underlying is unexpectedly a {type(self.underlying).__name__}!"
        object.__setattr__(self, 'underlying', self.generic_params['T'])


def _typetype_size(self: TypeType) -> int | None:
    # TODO
    return None


def _typetype_callable(self: TypeType) -> tuple[tuple[TypeBase, ...], TypeBase] | None:
    if isinstance(self.underlying,
                  ComposedType) and SpecialOperatorType.Constructor in self.underlying.special_operators:
        # input(self.underlying.special_operators)
        params, ret = self.underlying.special_operators[SpecialOperatorType.Constructor]
        from ... import ThisType
        assert isinstance(ret, ThisType)
        assert ret.resolved is not None
        return params, ret.resolved
    return None


def _typetype_indexable(self: TypeType) -> tuple[TypeBase, ...] | None:
    # Determined by whether we have a static `op[]` member.
    # TODO
    return None


TypeType.size = property(_typetype_size)  # type: ignore[misc,assignment]
TypeType.callable = property(_typetype_callable)  # type: ignore[misc,assignment]
TypeType.indexable = property(_typetype_indexable)  # type: ignore[misc,assignment]

__all__ = ('TypeType', 'TYPE_TYPE')
