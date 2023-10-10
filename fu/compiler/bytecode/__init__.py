from enum import Enum, auto
from logging import getLogger
from typing import TypeAlias, Callable
import struct
from functools import partial

MODULE_LOGGER = getLogger(__name__)


def decode_struct(pack: str, vals: bytes):
    return struct.unpack(pack, vals)[0]


_u16: Callable[[bytes], int] = partial(decode_struct, '>H')


class Register(Enum):
    Accumulator = auto()
    A = auto()


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

    ParamType = auto(), 1, ...
    NearBase = auto(), 1, int
    i8 = auto(), 1, int
    u16 = auto(), 2, _u16
    Register = auto(), 1, Register


ParamList: TypeAlias = tuple[type, ...]


class Opcode(Enum):
    """A Fu bytecode operation."""

    def __new__(cls, *args, **kwds):
        obj = object.__new__(cls)
        obj._value_ = args[0]
        return obj

    def __init__(self, _: int, params: ParamList = ()):
        self._params_ = params

    def __len__(self) -> int:
        return len(self._params_)

    @property
    def params(self) -> ParamList:
        return self._params_

    NOP = auto()

    # Stack and accumulator
    POP = auto()
    PUSH_LITERAL = auto(), (ParamType.ParamType, )
    STOR_LITERAL = auto(), (ParamType.ParamType, )

    # Control flow
    CALL = auto(), (ParamType.u16, )
    EXIT = auto()
    RETURN = auto()
    HALT_AND_CATCH_FIRE = auto()

    # Arithmetic
    ADD = auto(), (ParamType.ParamType, ParamType.ParamType)
    MOV = auto(), (ParamType.ParamType, ParamType.ParamType)
