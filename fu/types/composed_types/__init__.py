"""
Composed (class) types.
"""

from dataclasses import dataclass, field
from typing import TypeAlias, Literal, Optional
from collections import OrderedDict
from functools import partial

from ...compiler.tokenizer import SpecialOperatorType
from .. import TypeBase

CallSignature: TypeAlias = tuple[tuple['TypeBase', ...], 'TypeBase']
"""A tuple representing the argument list (`[0]`) and return type (`[1]`) of a callable."""


@dataclass(frozen=True, kw_only=True, slots=True, eq=False)
class ThisType(TypeBase):  # type: ignore[misc]
    """Represents the temporary value of `this` while still defining a type."""
    name: str = field(init=False, default='this')
    size: None = field(init=False, default=None)
    const: Literal[False] = field(init=False, default=False)
    is_builtin: Literal[False] = field(init=False, default=False)

    resolved: Optional['ComposedType'] = field(init=False, default=None)

    def resolve(self, resolved: 'ComposedType'):
        _set = partial(object.__setattr__, self)
        _set('resolved', resolved)
        _set('name', f"this<{resolved.name}>")

    def __eq__(self, __value: object) -> bool:
        return isinstance(__value, ThisType)


@dataclass(frozen=True, kw_only=True, slots=True)
class ComposedType(TypeBase):  # type: ignore[misc]
    """Represents a type built of other types."""

    reference_type: bool = field(default=True)
    """Whether or not instances of this type is passed by ref (True) or value (False)."""

    inherits: tuple['TypeBase', ...] | None = None
    """Inheritance chain."""

    indexable: CallSignature | None = None
    """`None` if this type doesn't accept the indexing operator (`[]`), otherwise defines the signature."""

    callable: CallSignature | None = None
    """`None` if this type doesn't accept the call operator (`()`), otherwise defines the signature."""

    instance_members: OrderedDict[str, 'TypeBase'] = field(default_factory=OrderedDict)
    """Members stored in instances of this class (ordered)."""

    static_members: OrderedDict[str, 'TypeBase'] = field(default_factory=OrderedDict)
    """Members stored in the static type of this class (ordered)."""

    readonly: set[str] = field(default_factory=set)
    """Members of this class (`instance_members` and `static_members` both) that are readonly \
       (not assignable after construction)."""

    special_operators: dict[SpecialOperatorType, CallSignature] = field(default_factory=dict)
    """Call signatures for any special operators stored on the type."""

    inherited_members: set[str] = field(default_factory=set)
    """Members that have come from parent classes."""

    this_type: ThisType = field(init=False, default_factory=ThisType)


__all__ = ('ComposedType', 'ThisType')
