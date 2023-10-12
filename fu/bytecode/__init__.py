from enum import Enum, auto
from logging import getLogger
from typing import TypeAlias, Callable, Any
import struct
from functools import partial

MODULE_LOGGER = getLogger(__name__)


def decode_struct(pack: str, vals: bytes):
    return struct.unpack(pack, vals)[0]


def encode_struct(pack: str, vals):
    return struct.pack(pack, vals)


_u16: Callable[[bytes], int] = partial(decode_struct, '>H')
_u32: Callable[[bytes], int] = partial(decode_struct, '>I')
_u64: Callable[[bytes], int] = partial(decode_struct, '>L')

u16: Callable[[int], bytes] = partial(encode_struct, '>H')


class RegisterEnum(Enum):
    Accumulator = auto()
    A = auto()


from ..compiler.typing.integral_types import *


class NumericTypes(Enum):
    u8 = auto()
    u16 = auto()
    u32 = auto()
    u64 = auto()
    i8 = auto()
    i16 = auto()
    i32 = auto()
    i64 = auto()

    usize_t = auto()
    size_t = auto()

    f16 = auto()
    f32 = auto()
    f64 = auto()

    @staticmethod
    def from_int_type(rhs: IntType):
        return NumericTypes[rhs.name]

    def to_type(self) -> IntegralType:
        match self:
            case self.u8:
                return U8_TYPE
            case self.i32:
                return I32_TYPE
            case _:
                raise NotImplementedError()


class ParamType(Enum):

    def __new__(cls, *args, **kwds):
        obj = object.__new__(cls)
        obj._value_ = args[0]
        return obj

    def __init__(self, _: int, length: int, t: type):
        if t is Ellipsis:
            t = self.__class__
        self._length_ = length
        self._type_ = t

    def __len__(self) -> int:
        return self._length_

    @property
    def length(self):
        return self._length_

    @property
    def type(self):
        return self._type_

    # PushOrPop = auto(), 1, bool

    ParamType = auto(), 1, ...
    # NearBase = auto(), 1, int
    NumericType = auto(), 1, NumericTypes
    u8 = auto(), 1, int
    u16 = auto(), 2, _u16
    u32 = auto(), 4, _u32
    u64 = auto(), 8, _u64
    # Register = auto(), 1, Register


ParamList: TypeAlias = tuple[ParamType, ...]


class OpcodeEnum(Enum):
    """A Fu bytecode operation."""

    def __new__(cls, *args, **kwds):
        obj = object.__new__(cls)
        obj._value_ = args[0]
        return obj

    def __init__(self, _: int, params: ParamList | ParamType = ()):
        if isinstance(params, ParamType):
            params = (params, )
        self._params_ = params

    def __len__(self) -> int:
        return len(self._params_)

    @property
    def params(self) -> ParamList:
        return self._params_

    NOP = auto()

    # Arguments
    PUSH_ARG = auto(), ParamType.u16

    # Locals
    PUSH_LOCAL = auto(), ParamType.u16
    POP_LOCAL = auto(), ParamType.u16
    INIT_LOCAL = auto()

    # References
    PUSH_REF = auto(), ParamType.u16
    POP_REF = auto(), ParamType.u16

    # Conversions
    CHECKED_CONVERT = auto(), ParamType.NumericType
    UNCHECKED_CONVERT = auto(), ParamType.NumericType

    # Control flow
    RET = auto()

    # # Stack and accumulator
    # POP = auto()
    # PUSH_LITERAL = auto(), (ParamType.ParamType, )
    # STOR_LITERAL = auto(), (ParamType.ParamType, )

    # # Control flow
    # CALL = auto(), (ParamType.u16, )
    # EXIT = auto()
    # RETURN = auto()
    # HALT_AND_CATCH_FIRE = auto()

    # # Arithmetic
    # ADD = auto(), (ParamType.ParamType, ParamType.ParamType)
    # MOV = auto(), (ParamType.ParamType, ParamType.ParamType)
