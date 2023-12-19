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
    is_builtin: bool = field(default=False)

    def get_size(self) -> int | None:
        raise NotImplementedError()

    def intrinsic_size(self) -> int | None:
        return None

    def __post_init__(self) -> None:
        pass

    # def __instancecheck__(self, __instance: Any) -> bool:
    #     return isinstance(__instance, TypeBase) and __instance.inherits is not None and self in __instance.inherits

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


VOID_TYPE = TypeBase('void', is_builtin=True)

from .integral_types import *
from .composed_types import *

from .composed_types.generic_types import *
from .composed_types.generic_types.array import ARRAY_TYPE
from .composed_types.static_type import *


@dataclass(frozen=True, slots=True)
class RefType(TypeBase):
    name: str = field(init=False)
    is_builtin: bool = field(init=False, default=False)
    to: TypeBase

    def __post_init__(self) -> None:
        object.__setattr__(self, 'name', f"ref<{self.to.name}>")

    @classmethod
    def get_size(cls) -> int:
        from ..compiler.target import TARGET
        if (target := TARGET.get(None)) is None:
            raise NotImplementedError("Target platform is not set. Size of ref unknown.")
        return target.architecture.platform_size(cls)


def make_ref(to: TypeBase) -> RefType:
    return RefType(to)


BUILTINS: dict[str, TypeBase] = {
    'type': TYPE_TYPE,
    'void': VOID_TYPE,

    # Integer Types
    'int': INT_TYPE,
    'uint': UINT_TYPE,
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
