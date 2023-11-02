from dataclasses import dataclass, field, replace
from typing import Any, Literal, Self, ClassVar, Optional

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
    size: int | None
    reference_type: bool = False
    inherits: tuple['TypeBase', ...] | None = None
    indexable: tuple[tuple['TypeBase', ...], 'TypeBase'] | None = None
    callable: tuple[tuple['TypeBase', ...], 'TypeBase'] | None = None
    members: dict[str, 'TypeBase'] = field(default_factory=dict)
    const: bool = field(compare=False, default=False)
    is_builtin: bool = field(default=False)

    def __post_init__(self) -> None:
        # from ..compiler.analyzer.scope import _CURRENT_ANALYZER_SCOPE, _PARSING_BUILTINS
        # object.__setattr__(self, 'is_builtin', (_CURRENT_ANALYZER_SCOPE.get(None) is None or _PARSING_BUILTINS.get())
        #                    and (self.name in BUILTIN_NAMES or getattr(self, '_name', '!') in BUILTIN_NAMES))
        pass

    def __instancecheck__(self, __instance: Any) -> bool:
        return isinstance(__instance, TypeBase) and __instance.inherits is not None and self in __instance.inherits

    def as_const(self) -> Self:
        return replace(self, name=getattr(self, '_name', self.name), const=True)

    def __eq__(self, __value: object) -> bool:
        if type(__value) != TypeBase:
            return False
        return (
            self.size,
            self.reference_type,
            self.inherits,
            self.indexable,
            self.callable,
            self.members,
            self.const,
            self.is_builtin,
        ) == (
            __value.size,
            __value.reference_type,
            __value.inherits,
            __value.indexable,
            __value.callable,
            __value.members,
            __value.const,
            __value.is_builtin,
        )


VOID_TYPE = TypeBase('void', size=0, is_builtin=True)


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class ThisType(TypeBase):  # type: ignore[misc]
    """Represents the temporary value of `this` while still defining a type."""
    name: str = field(init=False, default='this')
    size: ClassVar[None] = None  # type: ignore[misc]
    reference_type: ClassVar[Literal[True]] = True  # type: ignore[misc]
    inherits: ClassVar[None] = None  # type: ignore[misc]
    indexable: ClassVar[None] = None  # type: ignore[misc]
    callable: ClassVar[None] = None  # type: ignore[misc]

    resolved: Optional['ComposedType'] = field(init=False, default=None)

    def resolve(self, resolved: 'ComposedType'):
        object.__setattr__(self, 'resolved', resolved)
        object.__setattr__(self, 'name', f"this<{resolved.name}>")

    def __eq__(self, __value: object) -> bool:
        return isinstance(__value, ThisType)  # and (self.resolved is None or __value.resolved is None
        #      or self.resolved == __value.resolved)


from .composed_types import *
from .integral_types import *

from .composed_types.generic_types import *
from .composed_types.generic_types.array import ARRAY_TYPE
from .composed_types.generic_types.interface import *
from .composed_types.generic_types.type_ import *

U8_ARRAY_TYPE = ARRAY_TYPE.resolve_generic_instance(T=U8_TYPE)
STR_TYPE = U8_ARRAY_TYPE
STR_ARRAY_TYPE = ARRAY_TYPE.resolve_generic_instance(T=STR_TYPE)

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
