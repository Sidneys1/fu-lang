import struct
from enum import Enum, auto
from functools import partial
from io import BytesIO
from logging import getLogger
from typing import Any, Callable, Iterator, NewType, Optional, TypeAlias, TypeVar

from ...types.integral_types import *

MODULE_LOGGER = getLogger(__name__)


def _decode_struct(pack: str, vals: bytes):
    return struct.unpack(pack, vals)[0]


def _encode_struct(pack: str, vals):
    return struct.pack(pack, vals)


int_u8 = NewType('int_u8', int)
int_u16 = NewType('int_u16', int)
int_u32 = NewType('int_u32', int)
int_u64 = NewType('int_u64', int)

T = TypeVar('T', int_u8, int_u16, int_u32, int_u64)


def _to_bytecode_numeric(i: int, to: type[T]) -> T:
    if to is int_u8 and 0 > i > 255:
        raise ValueError()
    return to(i)


def _encode_numeric(i: int, to: type[T]) -> bytes:
    if to is not None:
        i = _to_bytecode_numeric(i, to)
    return _get_numeric_coders(to)[0](i)


def _decode_numeric(b: bytes, to: type[T]) -> T:
    return _get_numeric_coders(to)[1](b)


_decode_u8: Callable[[bytes], int_u8] = partial(_decode_struct, '>B')
_decode_u16: Callable[[bytes], int_u16] = partial(_decode_struct, '>H')
_decode_u32: Callable[[bytes], int_u32] = partial(_decode_struct, '>I')
_decode_u64: Callable[[bytes], int_u64] = partial(_decode_struct, '>L')

_encode_u8: Callable[[int_u8], bytes] = partial(_encode_struct, '>B')
_encode_u16: Callable[[int_u16], bytes] = partial(_encode_struct, '>H')
_encode_u32: Callable[[int_u32], bytes] = partial(_encode_struct, '>I')
_encode_u64: Callable[[int_u64], bytes] = partial(_encode_struct, '>L')

float_f16 = NewType('float_f16', float)
float_f32 = NewType('float_f32', float)
float_f64 = NewType('float_f64', float)

_encode_f16: Callable[[float_f16], bytes] = partial(_encode_struct, '>e')
_encode_f32: Callable[[float_f32], bytes] = partial(_encode_struct, '>f')
_encode_f64: Callable[[float_f64], bytes] = partial(_encode_struct, '>d')

_NUMERIC_CODERS = {
    int_u8: (_encode_u8, _decode_u8),
    int_u16: (_encode_u16, _decode_u16),
    int_u32: (_encode_u32, _decode_u32),
    int_u64: (_encode_u64, _decode_u64),
}


def _get_numeric_coders(t: type[T]) -> tuple[Callable[[T], bytes], Callable[[bytes], T]]:
    return _NUMERIC_CODERS[t]  # type: ignore


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
        self._type = t

    def __len__(self) -> int:
        return self._length_

    @property
    def length(self):
        return self._length_

    @property
    def type_(self) -> type:
        return self._type

    # PushOrPop = auto(), 1, bool

    ParamType = auto(), 1, ...
    # NearBase = auto(), 1, int
    NumericType = auto(), 1, NumericTypes
    u8 = auto(), 1, int
    u16 = auto(), 2, _decode_u16
    u32 = auto(), 4, _decode_u32
    u64 = auto(), 8, _decode_u64
    # Register = auto(), 1, Register


ParamList: TypeAlias = tuple[ParamType, ...]


class OpcodeEnum(Enum):
    """A Fu bytecode operation."""

    def __new__(cls, *args, **kwds):
        obj = object.__new__(cls)
        obj._value_ = args[0]
        return obj

    def __init__(self, _: int, fmt: str = '', explain: str = '', params: ParamList | ParamType = ()):
        self._format_ = fmt
        self._explainer_ = explain
        if isinstance(params, ParamType):
            params = (params, )
        self._params_ = params

    def __len__(self) -> int:
        return len(self._params_)

    @property
    def params(self) -> ParamList:
        return self._params_

    @property
    def fmt(self) -> str:
        return self._format_

    @property
    def explainer(self) -> str:
        return self._explainer_

    @staticmethod
    def decode_op(stream: BytesIO) -> tuple[Optional['OpcodeEnum'], tuple[Any, ...], bytes]:
        raw = stream.read(1)
        if len(raw) == 0:
            return None, (None, ), b''
        op = OpcodeEnum(raw[0])
        params = []
        for p in op.params:
            value = stream.read(len(p))
            params.append(p.type_(value[0]) if len(p) == 1 else p.type_(value))
            raw += value
        return op, tuple(params), raw

    def as_asm(self, *params: Any) -> tuple[str, str]:
        return self._format_.format(*params), self._explainer_.format(*params)

    NOP = auto()

    PUSH_LITERAL_u8 = auto(), 'push.u8 {}', 'push literal u8({}) onto stack', ParamType.u8

    # Arguments
    PUSH_ARG = auto(), 'pusharg {}', 'push argument #{}', ParamType.u8

    # Locals
    PUSH_LOCAL = auto(), 'pushlocal {}', 'push local #{}', ParamType.u8
    POP_LOCAL = auto(), 'poplocal {}', 'pop into local #{}', ParamType.u8
    INIT_LOCAL = auto(), 'initlocal', 'pop into a new local'

    # References
    PUSH_REF = auto(), 'pushref {}', 'pop a ref, push ref[{}]', ParamType.u8
    # POP_REF = auto(), 'setref {}', 'pop a ref, then pop again into ref[{}]', ParamType.u8
    PUSH_ARRAY = auto(), 'pusharray', 'pop an index, pop a ref, push ref[index]'

    # Conversions
    CHECKED_CONVERT = auto(), 'cconv.{0.name}', 'pop, convert to `{0.name}` (checked), push', ParamType.NumericType
    UNCHECKED_CONVERT = auto(), 'uconv.{0.name}', 'pop, convert to `{0.name}` (unchecked), push', ParamType.NumericType

    # Control flow
    RET = auto(), 'ret', 'return'

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


_FRIENDLY_OPCODE_NAMES: dict[OpcodeEnum, str] = {}

BytecodeTypes: TypeAlias = Enum | int_u8 | bytes | tuple['BytecodeTypes', ...] | bool


def to_bytes(in_: Iterator[BytecodeTypes]) -> Iterator[int]:
    for x in in_:
        print(x)
        match x:
            case tuple():
                yield from to_bytes(y for y in x)
            case Enum():
                val = x.value
                assert isinstance(val, int)
                yield val
            case bytes():
                yield from x
            case bool():
                yield 1 if x else 0
            case _:
                yield x
