from io import SEEK_END, BytesIO
from typing import Mapping
from types import EllipsisType
from contextvars import ContextVar
from contextlib import contextmanager
from logging import getLogger

from ...compiler import SourceLocation
from ...types import VOID_TYPE, TypeBase

from . import _encode_numeric, _encode_u32, _to_bytecode_numeric, int_u16, int_u32
from .structures import BytecodeBinary, BytecodeFunction, BytecodeType

_BUILDER: ContextVar['BytecodeBuilder'] = ContextVar('_BUILDER')
_LOG = getLogger(__package__)


class BytecodeBuilder:
    """Used for building a bytecode binary."""
    __code_length: int

    __types: list[BytecodeType]
    __strings: dict[str, int_u32]
    __strings_buffer: BytesIO
    __functions: list[BytecodeFunction | EllipsisType]
    __code: list[bytes]
    __source_map: dict[tuple[int_u32, int_u32], SourceLocation]
    __function_map: dict[int_u32, int_u16]

    @property
    def function_map(self) -> Mapping[int_u32, int_u16]:
        """Mapping from fqdn stringid to function id."""
        return self.__function_map

    def __init__(self) -> None:
        current = _BUILDER.get(None)
        assert current is None

        self.__code_length = 0

        self.__types = []
        zero_pos = int_u32(0)
        self.__strings = {'': zero_pos}
        self.__strings_buffer = BytesIO(_encode_u32(zero_pos))
        self.__strings_buffer.seek(0, SEEK_END)
        self.__functions = []
        self.__function_map = {}
        self.__code = []
        self.__source_map = {}

    @staticmethod
    def current() -> 'BytecodeBuilder':
        ret = _BUILDER.get(None)
        assert ret is not None
        return ret

    @contextmanager
    @staticmethod
    def create():
        from ...compiler.util import set_contextvar
        with set_contextvar(_BUILDER, BytecodeBuilder()) as builder:
            yield builder

    def finalize(self, entrypoint: int_u32 | None) -> BytecodeBinary:
        assert all(isinstance(x, BytecodeFunction) for x in self.__functions)
        assert not any(x is Ellipsis for x in self.__functions)
        return BytecodeBinary(
            b''.join(self.__code),
            self.__strings_buffer.getvalue(),
            self.__types,
            self.__functions,  # type: ignore
            entrypoint,
            self.__source_map)

    def _add_type(self, type_: BytecodeType) -> int_u16:
        # TODO: recursively check...
        try:
            index = self.__types.index(type_)
            _LOG.debug(f'Adding existing type: {index}')
            return _to_bytecode_numeric(index, int_u16)
        except ValueError:
            self.__types.append(type_)
            _LOG.debug(f'Adding new type: {len(self.__types) - 1}')
            return _to_bytecode_numeric(len(self.__types) - 1, int_u16)

    def add_type_type(self, type_: TypeBase) -> int_u16:
        assert isinstance(type_, TypeBase)
        if type_ == VOID_TYPE:
            return self._add_type(BytecodeType(type_=BytecodeType.Type.VOID))
        return self._add_type(BytecodeType.from_type(self, type_))

    def add_string(self, string: str) -> int_u32:
        if string not in self.__strings:
            i = _to_bytecode_numeric(self.__strings_buffer.tell(), int_u32)
            self.__strings[string] = i
            encoded = string.encode('utf-8')
            self.__strings_buffer.write(_encode_numeric(len(encoded), int_u32))
            self.__strings_buffer.write(encoded)
            return i
        return self.__strings[string]

    def add_function(self, fn: BytecodeFunction, fqdn: int_u32) -> int_u16:
        if fqdn in self.__function_map:
            raise ValueError()
        self.__functions.append(fn)
        id_ = _to_bytecode_numeric(len(self.__functions) - 1, int_u16)
        self.__function_map[fqdn] = id_
        return id_

    def reserve_function(self, fqdn: int_u32) -> int_u16:
        if fqdn in self.__function_map:
            raise ValueError()
        self.__functions.append(...)
        id_ = _to_bytecode_numeric(len(self.__functions) - 1, int_u16)
        self.__function_map[fqdn] = id_
        return id_

    def fulfill_function_reservation(self, reservation: int_u16, fn: BytecodeFunction) -> None:
        self.__functions[reservation] = fn

    def add_code(self, code: bytes) -> int_u32:
        pos = self.__code_length
        self.__code_length += len(code)
        self.__code.append(code)
        return _to_bytecode_numeric(pos, int_u32)

    def add_source_map(self, location: SourceLocation, byte_range: tuple[int, int]):
        self.__source_map[(int_u32(byte_range[0]), int_u32(byte_range[1]))] = location

    # @property
    # def code_length(self) -> int:
    #     return self.__code_length
