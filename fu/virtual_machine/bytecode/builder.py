from io import BytesIO, SEEK_END
from typing import TYPE_CHECKING

from ...compiler import SourceLocation
from ...types import TypeBase, VOID_TYPE

from . import _to_bytecode_numeric, _encode_numeric, _encode_u32, int_u16, int_u32
from .structures import BytecodeType, BuiltinTypes, BytecodeBinary, BytecodeFunction


class BytecodeBuilder:
    __code_length: int

    __types: list[BytecodeType]
    __strings: dict[str, int_u32]
    __strings_buffer: BytesIO
    __functions: list[BytecodeFunction]
    __code: list[bytes]
    __source_map: dict[SourceLocation, tuple[int_u32, int_u32]]

    def __init__(self) -> None:
        self.__code_length = 0

        self.__types = []
        zero_pos = int_u32(0)
        self.__strings = {'': zero_pos}
        self.__strings_buffer = BytesIO(_encode_u32(zero_pos))
        self.__strings_buffer.seek(0, SEEK_END)
        self.__functions = []
        self.__code = []
        self.__source_map = {}

    def finalize(self, entrypoint: int_u32 | None) -> BytecodeBinary:
        return BytecodeBinary(entrypoint, b''.join(self.__code), self.__types, self.__strings_buffer.getvalue(),
                              self.__functions, self.__source_map)

    def _add_type(self, type_: BytecodeType) -> int_u16:
        # TODO: recursively check...
        try:
            return _to_bytecode_numeric(self.__types.index(type_), int_u16)
        except ValueError:
            self.__types.append(type_)
            return _to_bytecode_numeric(len(self.__types) - 1, int_u16)

    def add_type_type(self, type_: TypeBase) -> int_u16:
        if type_ == VOID_TYPE:
            return self._add_type(BytecodeType(BuiltinTypes.void))
        return self._add_type(BytecodeType(builder=self, underlying=type_))

    def add_string(self, string: str) -> int_u32:
        if string not in self.__strings:
            i = _to_bytecode_numeric(self.__strings_buffer.tell(), int_u32)
            self.__strings[string] = i
            encoded = string.encode('utf-8')
            self.__strings_buffer.write(_encode_numeric(len(encoded), int_u32))
            self.__strings_buffer.write(encoded)
            return i
        return self.__strings[string]

    def add_function(self, fn: BytecodeFunction) -> int_u16:
        self.__functions.append(fn)
        return _to_bytecode_numeric(len(self.__functions) - 1, int_u16)

    def add_code(self, code: bytes) -> int_u32:
        pos = self.__code_length
        self.__code_length += len(code)
        self.__code.append(code)
        return _to_bytecode_numeric(pos, int_u32)

    def add_source_map(self, location: SourceLocation, byte_range: tuple[int, int]):
        self.__source_map[location] = (int_u32(byte_range[0]), int_u32(byte_range[1]))

    # @property
    # def code_length(self) -> int:
    #     return self.__code_length
