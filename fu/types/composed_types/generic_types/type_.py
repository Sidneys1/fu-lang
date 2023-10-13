from dataclasses import dataclass, field
from typing import Self, ClassVar

from ....compiler.tokenizer import SpecialOperatorType

from ... import ThisType, TypeBase

from . import GenericType, ComposedType


def _type_generics():
    return {'T': TypeType.TYPE_T}


TYPE_TYPE = TypeBase('type', size=None)


@dataclass(frozen=True, kw_only=True, slots=True)
class TypeType(GenericType):
    """Describes a type (not an instance of one)."""

    TYPE_T = GenericType.GenericParam('T')

    name: str = field(init=False, default='Type')
    underlying: TypeBase = field(init=False)

    indexable: tuple[Self, ...] | None = field(init=False)

    generic_params: dict[str, TypeBase] = field(default_factory=_type_generics)

    size: int | None = field(init=False)
    members: dict[str, TypeBase] = field(default_factory=dict)
    readonly: set[str] = field(default_factory=set)
    reference_type: bool = True
    inherits: ClassVar[tuple[TypeBase]] = (TYPE_TYPE, )

    callable: tuple[tuple[TypeBase, ...], TypeBase] | None = field(init=False)

    def __post_init__(self):
        assert isinstance(self.generic_params['T'],
                          TypeBase), f"Underlying is unexpectedly a {type(self.underlying).__name__}!"
        names = ','.join(k if v is None else v.name for k, v in self.generic_params.items())
        object.__setattr__(self, '_name', self.name)
        object.__setattr__(self, 'name', f"{self.name}<{names}>")
        object.__setattr__(self, 'underlying', self.generic_params['T'])

    @classmethod
    def of(cls, t: TypeBase) -> 'ComposedType':
        return cls().resolve_generic_instance(preserve_inheritance=True, T=t)


def _typetype_size(self: TypeType) -> int | None:
    # TODO
    return None


def _typetype_callable(self: TypeType) -> tuple[tuple[TypeBase, ...], TypeBase] | None:
    if isinstance(self.underlying,
                  ComposedType) and SpecialOperatorType.Constructor in self.underlying.special_operators:
        params, ret = self.underlying.special_operators[SpecialOperatorType.Constructor]
        assert isinstance(ret, ThisType)
        return params, ret.resolved
    return None


def _typetype_indexable(self: TypeType) -> tuple[Self, ...] | None:
    # Determined by whether we have a static `op[]` member.
    # TODO
    return None


TypeType.size = property(_typetype_size)
TypeType.callable = property(_typetype_callable)
TypeType.indexable = property(_typetype_indexable)

__all__ = ('TypeType', 'TYPE_TYPE')
