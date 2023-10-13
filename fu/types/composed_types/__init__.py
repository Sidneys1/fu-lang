from dataclasses import dataclass, field

from ...compiler.tokenizer import SpecialOperatorType

from .. import TypeBase


@dataclass(frozen=True, kw_only=True, slots=True)
class ComposedType(TypeBase):
    """Represents a type built of other types."""
    readonly: set[str] = field(default_factory=set)
    special_operators: dict[SpecialOperatorType, tuple[tuple[TypeBase, ...], TypeBase]] = field(default_factory=dict)


__all__ = ('ComposedType', )
