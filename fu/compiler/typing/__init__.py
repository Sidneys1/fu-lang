from typing import Self, Literal

from dataclasses import dataclass, field, replace


@dataclass(frozen=True, kw_only=True, slots=True)
class TypeBase:
    """Base class for all typing (runtime or static)."""
    name: str = field(kw_only=False)
    size: int | None
    reference_type: bool = False
    inherits: tuple['TypeBase', ...] | None = None
    indexable: tuple[tuple['TypeBase', ...], 'TypeBase'] | None = None
    callable: tuple[tuple['TypeBase', ...], 'TypeBase'] | None = None
    members: dict[str, 'TypeBase'] = field(default_factory=dict)
    const: bool = field(compare=False, default=False)

    def as_const(self) -> Self:
        return replace(self, const=True)


VOID_TYPE = TypeBase('void', size=0)

from .integral_types import *

from .composed_types import *


@dataclass(frozen=True, slots=True, kw_only=True)
class ThisType(TypeBase):
    """Represents the temporary value of `this` while still defining a type."""
    name: ClassVar[str] = 'this'
    size: ClassVar[None] = None
    reference_type: ClassVar[Literal[True]] = True
    inherits: ClassVar[None] = None
    indexable: ClassVar[None] = None
    callable: ClassVar[None] = None

    resolved: ComposedType | None = field(init=False, default=None)

    def resolve(self, resolved: ComposedType):
        object.__setattr__(self, 'resolved', resolved)


# from .composed_types.type import TYPE_TYPE
from .composed_types.generic_types import *
from .composed_types.generic_types.type_ import *
from .composed_types.generic_types.array import ARRAY_TYPE

U8_ARRAY_TYPE = ARRAY_TYPE.resolve_generic_instance({'T': U8_TYPE})
STR_TYPE = U8_ARRAY_TYPE

BUILTINS: dict[str, TypeBase] = {
    'type': TYPE_TYPE,
    'void': VOID_TYPE,

    # Integer Types
    'size_t': SIZE_TYPE,
    'usize_t': USIZE_TYPE,
    'i8': I8_TYPE,
    'u8': U8_TYPE,
    'i16': I16_TYPE,
    'u16': U16_TYPE,
    'i32': I32_TYPE,
    'u32': U32_TYPE,
    'i64': I64_TYPE,
    'u64': U64_TYPE,

    # Float Types
    'f16': F16_TYPE,
    'f32': F32_TYPE,
    'f64': F64_TYPE,

    # Enum Types
    'bool': BOOL_TYPE,
}
