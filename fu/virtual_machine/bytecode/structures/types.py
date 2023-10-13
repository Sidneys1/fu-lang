from dataclasses import dataclass
from typing import Iterator

from ...types import TypeBase

from . import BytecodeBase, BytecodeTypes


@dataclass(frozen=True, kw_only=True, slots=True)
class BytecodeMember(BytecodeBase):
    """A usertype definition."""

    def _encode(self) -> Iterator[BytecodeTypes | BytecodeBase]:
        raise NotImplementedError()
        yield


@dataclass(frozen=True, kw_only=True, slots=True)
class BytecodeType(BytecodeBase):
    """A usertype definition."""
    # content: list[BytecodeMember]

    @classmethod
    def from_static_type(cls, type_: TypeBase) -> 'BytecodeType':
        return None  # noqa


__all__ = ('BytecodeMember', 'BytecodeType')
