from enum import IntFlag
from io import BytesIO, IOBase, SEEK_CUR
from logging import getLogger
from typing import TYPE_CHECKING, ClassVar, Iterator, Self, TypeAlias
from humanize.filesize import naturalsize
from pathlib import Path

from ....compiler import SourceLocation
from . import BytecodeBase, BytecodeTypes

if TYPE_CHECKING:
    from .code import BytecodeFunction
    from .types import BytecodeType

from .. import _encode_numeric, _encode_u32, int_u16, int_u32, int_u8, _decode_u8, _decode_u32, _decode_u16

_LOG = getLogger(__package__)

SourceMap: TypeAlias = dict[tuple[int_u32, int_u32], SourceLocation]


class BytecodeBinary(BytecodeBase):
    """A complete binary."""
    MAGIC: ClassVar[bytes] = b'foo-binary-v0.0.1'

    class Flags(IntFlag):
        NONE = 0
        IS_LIBRARY = 1

    flags: Flags
    entrypoint: int_u32 | None
    bytecode: bytes

    strings: bytes
    types: list['BytecodeType']
    functions: list['BytecodeFunction']
    source_map: SourceMap | None = None

    _strings_count: int | None = None

    @property
    def strings_count(self) -> int:
        if self._strings_count is not None:
            return self._strings_count
        i = 0
        with BytesIO(self.strings) as stream:
            val = stream.read(4)
            while val != b'':
                string_len = _decode_u32(val)
                stream.seek(string_len, SEEK_CUR)
                i += 1
                val = stream.read(4)
        self._strings_count = i
        return i

    def __init__(self,
                 bytecode: bytes,
                 strings: bytes,
                 types: list['BytecodeType'],
                 functions: list['BytecodeFunction'],
                 entrypoint: int_u32 | None = None,
                 source_map: SourceMap | None = None) -> None:
        self.flags = BytecodeBinary.Flags.NONE
        if entrypoint is None:
            self.flags |= BytecodeBinary.Flags.IS_LIBRARY

        self.bytecode = bytecode
        self.strings = strings
        self.types = types
        self.functions = functions
        self.entrypoint = entrypoint
        self.source_map = source_map

    @classmethod
    def decode(cls, stream: IOBase, load_source_map=True) -> Self:
        assert stream.read(len(cls.MAGIC)) == cls.MAGIC

        flags = BytecodeBinary.Flags(_decode_u8(stream.read(1)))

        entrypoint: int_u32 | None = None
        if BytecodeBinary.Flags.IS_LIBRARY not in flags:
            # Read entrypoint
            entrypoint = _decode_u32(stream.read(4))

        strings = stream.read(_decode_u32(stream.read(4)))

        types: list['BytecodeType'] = []
        from .types import BytecodeType
        for _ in range(_decode_u16(stream.read(2))):
            types.append(BytecodeType.decode(stream))

        funcs: list['BytecodeFunction'] = []
        from .code import BytecodeFunction
        for _ in range(_decode_u16(stream.read(2))):
            funcs.append(BytecodeFunction.decode(stream))

        bytecode = stream.read(_decode_u32(stream.read(4)))

        source_map: SourceMap | None = None
        if load_source_map:
            source_map = {}
            for _ in range(_decode_u16(stream.read(2))):
                file_name = stream.read(_decode_u16(stream.read(2))).decode('utf-8')
                seek = (_decode_u32(stream.read(4)), _decode_u32(stream.read(4)))
                lines = (_decode_u16(stream.read(2)), _decode_u16(stream.read(2)))
                columns = (_decode_u16(stream.read(2)), _decode_u16(stream.read(2)))
                op_range = (_decode_u32(stream.read(4)), _decode_u32(stream.read(4)))
                source_map[op_range] = SourceLocation(seek, lines, columns, file_name)

        return cls(bytecode, strings, types, funcs, entrypoint, source_map)

    def _encode(self) -> Iterator[BytecodeTypes | BytecodeBase]:
        _LOG.debug(f"Magic ({BytecodeBinary.MAGIC!r})")
        yield BytecodeBinary.MAGIC

        _LOG.debug(f'Flags ({_encode_numeric(self.flags.value, int_u8)!r})')
        yield self.flags

        if self.entrypoint is not None:
            _LOG.debug(f'Entrypoint ({self.entrypoint:#06x})')
            yield _encode_u32(self.entrypoint)

        # yield self.strings
        _LOG.debug(f"Strings length ({naturalsize(len(self.strings), True, format='%.02f')}), strings blob")
        yield _encode_numeric(len(self.strings), int_u32), self.strings

        # with BytesIO() as buffer:
        _LOG.debug(f"Types count ({len(self.types):,})")
        yield _encode_numeric(len(self.types), int_u16)
        for i, t in enumerate(self.types):
            _LOG.debug(f"\tType #{i}")
            with BytesIO() as buffer:
                t.encode(buffer)
                yield buffer.getvalue()

        # yield self.functions
        _LOG.debug(f"Functions count ({len(self.functions):,})")
        yield _encode_numeric(len(self.functions), int_u16)
        for i, f in enumerate(self.functions):
            with BytesIO() as buffer:
                f.encode(buffer)
                _LOG.debug(f"\tFunction #{i}")
                yield buffer.getvalue()

        # yield self.bytecode
        _LOG.debug(f"Bytecode length ({naturalsize(len(self.bytecode), True, format='%.02f')}), bytecode blob")
        yield _encode_numeric(len(self.bytecode), int_u32), self.bytecode

        yield _encode_numeric(len(self.source_map) if self.source_map is not None else 0, int_u16)

        if self.source_map is None:
            return

        _LOG.debug(f"Sourcemap count ({len(self.source_map):,})")
        for i, (k, v) in enumerate(sorted(self.source_map.items(), key=lambda e: e[0][0])):
            with BytesIO() as buffer:
                _LOG.debug(f"\tSource Map #{i}: {k}: {v}")
                fname = v.file.encode('utf-8')
                buffer.write(_encode_numeric(len(fname), int_u16))
                buffer.write(fname)
                buffer.write(_encode_numeric(v.seek[0], int_u32))
                buffer.write(_encode_numeric(v.seek[1], int_u32))
                buffer.write(_encode_numeric(v.lines[0], int_u16))
                buffer.write(_encode_numeric(v.lines[1], int_u16))
                buffer.write(_encode_numeric(v.columns[0], int_u16))
                buffer.write(_encode_numeric(v.columns[1], int_u16))
                buffer.write(_encode_u32(k[0]))
                buffer.write(_encode_u32(k[1]))
                yield buffer.getvalue()
