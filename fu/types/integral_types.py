from dataclasses import dataclass, field
from typing import ClassVar, Self

from . import TypeBase


@dataclass(frozen=True, kw_only=True, slots=True)
class IntegralType(TypeBase):
    """Supertype for certain value types: integrals, floats, etc."""

    reference_type: ClassVar[bool] = False
    inherits: tuple[Self] | None = field(init=None, default=())
    indexable: ClassVar[None] = None
    callable: ClassVar[None] = None

    def could_hold_value(self, value: str) -> bool:
        return False


#
# ================  INT TYPES  ================
#


@dataclass(frozen=True, kw_only=True, slots=True)
class IntType(IntegralType):
    """Describes a type that is an integer number (ℤ)."""
    size: int
    signed: bool

    def range(self) -> tuple[int, int]:
        max = (2**(self.size * 8)) - 1
        min = 0
        if self.signed:
            max = max // 2
            min = -(max + 1)
        return min, max

    def could_hold_value(self, value: str | int) -> bool:
        try:
            if isinstance(value, str):
                value = int(value)
            min, max = self.range()
            return min <= value <= max
        except:
            return False

    @classmethod
    def best_for_value(cls, value: int, want_signed: bool = False):
        options = _SIGNED_TYPES if want_signed or value < 0 else _UNSIGNED_TYPES
        return min((x for x in options if x.could_hold_value(value)), key=lambda x: x.size)


I8_TYPE = IntType('i8', size=1, signed=True)
U8_TYPE = IntType('u8', size=1, signed=False)
I16_TYPE = IntType('i16', size=2, signed=True)
U16_TYPE = IntType('u16', size=2, signed=False)
I32_TYPE = IntType('i32', size=4, signed=True)
U32_TYPE = IntType('u32', size=4, signed=False)
I64_TYPE = IntType('i64', size=8, signed=True)
U64_TYPE = IntType('u64', size=8, signed=False)

SIZE_TYPE = IntType('size_t', size=8, signed=True)
USIZE_TYPE = IntType('usize_t', size=8, signed=False)

_SIGNED_TYPES = (I8_TYPE, I16_TYPE, I32_TYPE, I64_TYPE)
_UNSIGNED_TYPES = (U8_TYPE, U16_TYPE, U32_TYPE, U64_TYPE)

#
# ================  FLOAT TYPES  ================
#


@dataclass(frozen=True, kw_only=True, slots=True)
class FloatType(IntegralType):
    """Describes a IEEE floating point number."""
    size: int
    exp_bits: int

    def could_hold_value(self, value: str | float) -> bool:
        if isinstance(value, float):
            return True
        try:
            float(value)
            return True
        except:
            return False

    @classmethod
    def best_for_value(cls, value: float, want_signed: bool = False):
        return min((x for x in (F16_TYPE, F32_TYPE, F64_TYPE) if x.could_hold_value(value)), key=lambda x: x.size)


F16_TYPE = FloatType('f16', size=2, exp_bits=5)
F32_TYPE = FloatType('f32', size=4, exp_bits=8)
F64_TYPE = FloatType('f64', size=8, exp_bits=11)

#
# ================  ENUM TYPES  ================
#


@dataclass(frozen=True, kw_only=True, slots=True)
class EnumType(IntType):
    """Describes a type that is a set of scoped integral literals."""
    size: int = field(init=False)
    values: dict[str, int] = field(kw_only=False)
    inherits: tuple[IntType] = field(default=())

    def __post_init__(self):
        TypeBase.__post_init__(self)
        if self.inherits == ():
            min_val = min(self.values.values())
            max_val = max(self.values.values())
            options = _UNSIGNED_TYPES if min_val < 0 else _SIGNED_TYPES
            selection: IntType | None = None
            for option in options:
                t_min, t_max = option.range()
                if (t_min <= min_val <= t_max) and (t_max >= max_val >= min_val):
                    selection = option
                    break
            if selection is None:
                raise ValueError("No integer type exists that can satisfy an enumeration with inclusive range "
                                 f"{min_val}-{max_val}.")
            object.__setattr__(self, 'inherits', (selection, ))
        object.__setattr__(self, 'size', self.inherits[0].size)


BOOL_TYPE = EnumType('bool', {'false': 0, 'true': 1}, inherits=(U32_TYPE, ), signed=False)
"""A special Enumeration type that inherits from u32 instead of u8 (as would be expected)."""
