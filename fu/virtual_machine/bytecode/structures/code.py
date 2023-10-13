from dataclasses import dataclass
from typing import Sequence

from . import BytecodeContainer, BytecodeTypes


@dataclass(frozen=True, kw_only=True, slots=True)
class BytecodeLine(BytecodeContainer):
    """A "line" (collection of sequential expressions, which are raw opcodes and their parameters)."""
    content: Sequence[BytecodeTypes]


@dataclass(frozen=True, kw_only=True, slots=True)
class BytecodeBlock(BytecodeContainer[BytecodeLine]):
    """A block (collection of sequential lines)."""


@dataclass(frozen=True, kw_only=True, slots=True)
class BytecodeFunction(BytecodeContainer[BytecodeBlock]):
    """A function (collection of blocks + a callable type)."""


__all__ = ('BytecodeLine', 'BytecodeBlock', 'BytecodeFunction')
