from abc import ABC, abstractmethod
from typing import Iterator, Generic, TypeVar, Sequence, ClassVar
from dataclasses import field, dataclass

from .. import BytecodeTypes

from ...compiler import SourceLocation


@dataclass(frozen=True, kw_only=True, slots=True)
class BytecodeBase(ABC):
    """Base class for all bytecode structures."""
    location: SourceLocation = field(kw_only=False)

    def encode(self) -> Iterator[BytecodeTypes]:
        for x in self._encode():
            if isinstance(x, BytecodeBase):
                yield from x.encode()
            else:
                yield x

    @abstractmethod
    def _encode(self) -> Iterator[BytecodeTypes | 'BytecodeBase']:
        ...


from typing import Generic, TypeVar

T = TypeVar('T', bound=BytecodeBase)


@dataclass(frozen=True, kw_only=True, slots=True)
class BytecodeContainer(Generic[T], BytecodeBase, ABC):
    """A simple bytecode type that just contains other types."""
    MAGIC: ClassVar[bytes]
    content: Sequence[T] = field(default_factory=list)

    def _encode(self) -> Iterator[T | BytecodeTypes]:
        yield self.MAGIC
        yield len(self.content)
        yield from self.content


from .code import *
from .types import *


@dataclass(frozen=True, kw_only=True, slots=True)
class BytecodeBinary(BytecodeBase):
    """A complete binary."""
    MAGIC: ClassVar[bytes] = b'foo-binary-v0.0.1'
    types: list[BytecodeType] = field(default_factory=list)

    def _encode(self) -> Iterator[BytecodeTypes | BytecodeBase]:
        yield BytecodeBinary.MAGIC
