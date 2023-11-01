from dataclasses import dataclass
from enum import Enum
from logging import getLogger
from typing import Iterator

from .. import _encode_u16, _encode_u32, int_u16, int_u32
from . import BytecodeBase, BytecodeTypes
from .binary import BytecodeBase, BytecodeTypes, Iterator

_LOG = getLogger(__package__)

# @dataclass(frozen=True, kw_only=True, slots=True)
# class BytecodeLine(BytecodeFromSource):
#     """A "line" (collection of sequential expressions, which are raw opcodes and their parameters)."""

#     @classmethod
#     def decode(cls, stream: bytes) -> tuple[Self, bytes]:
#         count = _from_u32(stream[:4])
#         b = stream[4:4 + count]
#         return BytecodeLine(None), stream[4 + count:]

#     def _encode(self) -> Iterator[BytecodeTypes]:
#         b = bytes(to_bytes(x for x in self.content))
#         print(f"encoding {type(self).__name__}: {len(b)} bytes")
#         yield _to_u32(len(b))
#         yield b

# @dataclass(frozen=True, kw_only=True, slots=True)
# class BytecodeBlock(BytecodeContainer[BytecodeLine]):
#     """A block (collection of sequential lines)."""

#     @classmethod
#     def decode(cls, stream: bytes) -> tuple[Self, bytes]:
#         count = _from_u32(stream[:4])
#         stream = stream[4:]
#         lines: list[BytecodeLine] = []
#         for _ in range(count):
#             line, stream = BytecodeLine.decode(stream)
#             lines.append(line)
#         return BytecodeBlock(None, content=lines), stream


@dataclass(frozen=True, slots=True)
class BytecodeFunction(BytecodeBase):
    """An exported function."""

    name: int_u32
    """Function name, as an index into the Strings table."""
    scope: int_u32
    """Function scope, as an index into the Strings table."""
    signature: int_u16
    """Function signature, as an index into the Types table."""

    address: int_u32
    """Function code, as an offset into Code table."""

    def _encode(self) -> Iterator[BytecodeTypes | BytecodeBase]:
        yield _encode_u32(self.name)
        yield _encode_u32(self.scope)
        yield _encode_u16(self.signature)
        yield _encode_u32(self.address)

    # @classmethod
    # def decode(cls, stream: bytes) -> tuple[Self, bytes]:
    #     count = _from_u32(stream[:4])
    #     stream = stream[4:]
    #     blocks: list[BytecodeBlock] = []
    #     for _ in range(count):
    #         block, stream = BytecodeBlock.decode(stream)
    #         blocks.append(block)
    #     return BytecodeFunction(None, content=blocks), stream


__all__ = ('BytecodeFunction', )
