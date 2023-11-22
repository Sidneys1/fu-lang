"""
Type information for Fu static analysis.
"""

from dataclasses import dataclass, field, replace
from typing import Self, Literal, Optional

BUILTIN_NAMES = {
    'type',
    'void',

    # Integer Types
    'size_t',
    'usize_t',
    'i8',
    'u8',
    'i16',
    'u16',
    'i32',
    'u32',
    'i64',
    'u64',

    # Float Types
    'f16',
    'f32',
    'f64',

    # Enum Types
    'bool',

    # Generic types
    'Array',
}


@dataclass(frozen=True, kw_only=True, slots=True)
class TypeBase:  # type: ignore[misc]
    """Base class for all typing (runtime or static)."""
    name: str = field(kw_only=False)
    size: int | None = field(kw_only=False)
    const: bool = field(compare=False, default=False)
    is_builtin: bool = field(default=False)

    def __post_init__(self) -> None:
        pass

    # def __instancecheck__(self, __instance: Any) -> bool:
    #     return isinstance(__instance, TypeBase) and __instance.inherits is not None and self in __instance.inherits

    def as_const(self) -> Self:
        return replace(self, name=getattr(self, 'real_name', self.name), const=True)

    # def __eq__(self, __value: object) -> bool:
    #     if type(__value) != TypeBase:
    #         return False
    #     return (
    #         self.size,
    #         self.const,
    #         self.is_builtin,
    #     ) == (
    #         __value.size,
    #         __value.const,
    #         __value.is_builtin,
    #     )


VOID_TYPE = TypeBase('void', size=0, is_builtin=True)

from .integral_types import *
from .composed_types import *

from .composed_types.generic_types import *
from .composed_types.generic_types.array import ARRAY_TYPE
# from .composed_types.generic_types.interface import *
from .composed_types.generic_types.type_ import *

REF_TYPE_T = GenericType.GenericParam('T')
REF_TYPE = GenericType('ref', size=4, reference_type=False, generic_params={'T': REF_TYPE_T})


def make_ref(t: TypeBase) -> GenericType:
    return REF_TYPE.resolve_generic(T=t)


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
    'Array': ARRAY_TYPE,
}

# AOT defining some commonly used (but not builtin) types.
U8_ARRAY_TYPE = ARRAY_TYPE.resolve_generic(T=U8_TYPE)
STR_TYPE = U8_ARRAY_TYPE
STR_ARRAY_TYPE = ARRAY_TYPE.resolve_generic(T=STR_TYPE)
