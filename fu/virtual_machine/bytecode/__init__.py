import struct
from enum import Enum, auto
from functools import partial
from io import BytesIO
from logging import getLogger
from typing import Any, Callable, Iterator, NewType, Optional, TypeAlias, TypeVar
from inspect import isclass

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
int_i8 = NewType('int_i8', int)
int_i16 = NewType('int_i16', int)
int_i32 = NewType('int_i32', int)
int_i64 = NewType('int_i64', int)

T = TypeVar('T', int_u8, int_u16, int_u32, int_u64, int_i8, int_i16, int_i32, int_i64)


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
_decode_u64: Callable[[bytes], int_u64] = partial(_decode_struct, '>Q')
_decode_i8: Callable[[bytes], int_i8] = partial(_decode_struct, '>b')
_decode_i16: Callable[[bytes], int_i16] = partial(_decode_struct, '>h')
_decode_i32: Callable[[bytes], int_i32] = partial(_decode_struct, '>i')
_decode_i64: Callable[[bytes], int_i64] = partial(_decode_struct, '>q')

_encode_u8: Callable[[int_u8], bytes] = partial(_encode_struct, '>B')
_encode_u16: Callable[[int_u16], bytes] = partial(_encode_struct, '>H')
_encode_u32: Callable[[int_u32], bytes] = partial(_encode_struct, '>I')
_encode_u64: Callable[[int_u64], bytes] = partial(_encode_struct, '>Q')
_encode_i8: Callable[[int_i8], bytes] = partial(_encode_struct, '>b')
_encode_i16: Callable[[int_i16], bytes] = partial(_encode_struct, '>h')
_encode_i32: Callable[[int_i32], bytes] = partial(_encode_struct, '>i')
_encode_i64: Callable[[int_i64], bytes] = partial(_encode_struct, '>q')

float_f16 = NewType('float_f16', float)
float_f32 = NewType('float_f32', float)
float_f64 = NewType('float_f64', float)

_decode_f16: Callable[[bytes], float_f16] = partial(_decode_struct, '>e')
_decode_f32: Callable[[bytes], float_f32] = partial(_decode_struct, '>f')
_decode_f64: Callable[[bytes], float_f64] = partial(_decode_struct, '>d')
_encode_f16: Callable[[float_f16], bytes] = partial(_encode_struct, '>e')
_encode_f32: Callable[[float_f32], bytes] = partial(_encode_struct, '>f')
_encode_f64: Callable[[float_f64], bytes] = partial(_encode_struct, '>d')

_NUMERIC_CODERS = {
    int_u8: (_encode_u8, _decode_u8),
    int_u16: (_encode_u16, _decode_u16),
    int_u32: (_encode_u32, _decode_u32),
    int_u64: (_encode_u64, _decode_u64),
    int_i8: (_encode_i8, _decode_i8),
    int_i16: (_encode_i16, _decode_i16),
    int_i32: (_encode_i32, _decode_i32),
    int_i64: (_encode_i64, _decode_i64),
    float_f16: (_encode_f16, _decode_f16),
    float_f32: (_encode_f32, _decode_f32),
    float_f64: (_encode_f64, _decode_f64),
}


def _get_numeric_coders(t: type[T]) -> tuple[Callable[[T], bytes], Callable[[bytes], T]]:
    return _NUMERIC_CODERS[t]  # type: ignore


class NumericTypes(Enum):

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

    u8 = 0, 1, _decode_u8
    u16 = auto(), 2, _decode_u16
    u32 = auto(), 4, _decode_u32
    u64 = auto(), 8, _decode_u64
    i8 = auto(), 1, _decode_i8
    i16 = auto(), 2, _decode_i16
    i32 = auto(), 4, _decode_i32
    i64 = auto(), 8, _decode_i64

    usize_t = auto(), 8, _decode_u64
    size_t = auto(), 8, _decode_i64

    f16 = auto(), 2, _decode_f16
    f32 = auto(), 4, _decode_f32
    f64 = auto(), 8, _decode_f64

    @staticmethod
    def from_int_type(rhs: IntType):
        return NumericTypes[rhs.name]

    def to_type(self) -> IntegralType:
        match self:
            case self.u8:
                return U8_TYPE
            case self.i32:
                return I32_TYPE
            case self.u32:
                return U32_TYPE
            case self.f32:
                return F32_TYPE
            case self.u64:
                return U64_TYPE
            case _:
                raise NotImplementedError(f"{self.name}")


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
    # u8 = auto(), 1, int
    # u16 = auto(), 2, _decode_u16
    # u32 = auto(), 4, _decode_u32
    # u64 = auto(), 8, _decode_u64
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
        if not isinstance(params, tuple):
            params = (params, )
        self._params_ = params

    def __len__(self) -> int:
        return sum(len(p) for p in self._params_)

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
        last: ParamType | NumericTypes | None = None
        # input(f"{op}: {op.params}")
        for p in op.params:
            if p is Ellipsis:
                assert last is not None
                value = stream.read(len(last))
                val = last.type_(value)
            else:
                value = stream.read(len(p))
                if isclass(p.type_) and issubclass(p.type_, Enum):
                    val = p.type_(value[0])
                else:
                    val = p.type_(value)
            params.append(val)
            raw += value
            last = val
        return op, tuple(params), raw

    def as_asm(self, *params: Any) -> tuple[str, str]:
        return self._format_.format(*params), self._explainer_.format(*params)

    NOP = 0

    PUSH_LITERAL = auto(), 'push.{0.name} {1}', 'push literal `{0.name}` ({1}) onto stack', (ParamType.NumericType, ...)

    # Arguments
    PUSH_ARG = auto(), 'pusharg {}', 'push argument #{}', NumericTypes.u8

    # Locals
    PUSH_LOCAL = auto(), 'pushlocal {}', 'push local #{}', NumericTypes.u8
    POP_LOCAL = auto(), 'poplocal {}', 'pop into local #{}', NumericTypes.u8
    INIT_LOCAL = auto(), 'initlocal', 'pop into a new local'

    # References
    PUSH_REF = auto(), 'pushref {}', 'pop a ref, push ref[{}]', NumericTypes.u8
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
    # HALT_AND_CATCH_FIRE = auto()

    # # Arithmetic
    CHECKED_ADD = auto(), 'add.{0.name}', 'pop two, add into `{0.name}` (checked), push', ParamType.NumericType
    CHECKED_SUB = auto(), 'sub.{0.name}', 'pop two, subtract into `{0.name}` (checked), push', ParamType.NumericType
    CHECKED_MUL = auto(), 'mul.{0.name}', 'pop two, multiply into `{0.name}` (checked), push', ParamType.NumericType
    CHECKED_IDIV = auto(
    ), 'idiv.{0.name}', 'pop two, integer divide into `{0.name}` (checked), push', ParamType.NumericType
    CHECKED_FDIV = auto(
    ), 'fdiv.{0.name}', 'pop two, float divide into `{0.name}` (checked), push', ParamType.NumericType


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
