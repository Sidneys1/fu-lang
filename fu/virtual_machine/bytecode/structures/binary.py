from dataclasses import dataclass, field
from enum import IntFlag, auto
from io import BytesIO
from logging import getLogger
from typing import TYPE_CHECKING, ClassVar, Iterator

from ....compiler import SourceLocation
from . import BytecodeBase, BytecodeTypes

if TYPE_CHECKING:
    from .code import BytecodeFunction
    from .types import BytecodeType

from .. import _encode_numeric, _encode_u32, int_u16, int_u32

_LOG = getLogger(__package__)


class BinaryFlags(IntFlag):
    NONE = 0
    IsLibrary = auto()
    HasSourceMap = auto()


@dataclass(frozen=True, slots=True)
class BytecodeBinary(BytecodeBase):
    """A complete binary."""
    MAGIC: ClassVar[bytes] = b'foo-binary-v0.0.1'

    entrypoint: int_u32 | None
    bytecode: bytes = field(repr=False)

    types: list['BytecodeType'] = field(default_factory=list)
    strings: bytes = field(default=b'', repr=False)
    functions: list['BytecodeFunction'] = field(default_factory=list)
    source_map: dict[SourceLocation, tuple[int_u32, int_u32]] | None = None

    # @classmethod
    # def decode(cls, stream: bytes) -> Iterator[BytecodeBase]:
    #     from itertools import islice
    #     magic = stream[:len(cls.MAGIC)]
    #     assert magic == cls.MAGIC
    #     print('Magic in the air')
    #     if False:
    #         yield

    def _encode(self) -> Iterator[BytecodeTypes | BytecodeBase]:
        _LOG.debug("Magic")
        yield BytecodeBinary.MAGIC
        # _LOG.debug("Metadata")
        # yield self.metadata

        flags = BinaryFlags.NONE
        if self.source_map:
            flags |= BinaryFlags.HasSourceMap
        if self.entrypoint is None:
            flags |= BinaryFlags.IsLibrary

        _LOG.debug('Flags')
        yield flags

        if self.entrypoint is not None:
            yield _encode_u32(self.entrypoint)

        # with BytesIO() as buffer:
        _LOG.debug("Types count")
        yield _encode_numeric(len(self.types), int_u16)
        for i, t in enumerate(self.types):
            t_buf = b''.join(t.encode())
            _LOG.debug(f"\tType #{i}")
            yield _encode_numeric(len(t_buf), int_u16), t_buf

        # yield self.strings
        _LOG.debug("Strings length, strings blob")
        yield _encode_numeric(len(self.strings), int_u32), self.strings

        # yield self.functions
        _LOG.debug("Functions count")
        yield _encode_numeric(len(self.functions), int_u16)
        for i, f in enumerate(self.functions):
            t_buf = b''.join(f.encode())
            _LOG.debug(f"\tFunction #{i}")
            yield _encode_numeric(len(t_buf), int_u16), t_buf

        # yield self.bytecode
        _LOG.debug("Bytecode length, bytecode blob")
        yield _encode_numeric(len(self.bytecode), int_u32), self.bytecode

        if self.source_map is not None:
            _LOG.debug("Sourcemap count")
            yield _encode_numeric(len(self.source_map), int_u16)
            for i, (k, v) in enumerate(self.source_map.items()):
                with BytesIO() as buffer:
                    fname = k.file.encode('utf-8')
                    buffer.write(_encode_numeric(len(fname), int_u16))
                    buffer.write(fname)
                    buffer.write(_encode_numeric(k.seek[0], int_u32))
                    buffer.write(_encode_numeric(k.seek[1], int_u32))
                    buffer.write(_encode_numeric(k.lines[0], int_u16))
                    buffer.write(_encode_numeric(k.lines[1], int_u16))
                    buffer.write(_encode_numeric(k.columns[0], int_u16))
                    buffer.write(_encode_numeric(k.columns[1], int_u16))
                    buffer.write(_encode_u32(v[0]))
                    buffer.write(_encode_u32(v[1]))
                    _LOG.debug(f"\tSource Map #{i}: {k}: {v}")
                    yield _encode_numeric(buffer.tell(), int_u16), buffer.getvalue()
