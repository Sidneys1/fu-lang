from abc import ABC, abstractmethod
from typing import Iterator, Generic, TypeVar, Sequence, Union, Self, NewType
from dataclasses import field, dataclass
from io import BytesIO
from enum import Enum

from .. import _encode_u32, BytecodeTypes, _encode_f32, _encode_u8


@dataclass(frozen=True, kw_only=True, slots=True)
class BytecodeBase(ABC):
    """Base class for all bytecode structures."""

    @classmethod
    def decode(cls, stream: BytesIO) -> tuple[Self, bytes]:
        raise NotImplementedError()

    def encode(self) -> Iterator[bytes]:
        yield from _to_bytes(self._encode())

    @abstractmethod
    def _encode(self) -> Iterator[Union[BytecodeTypes, 'BytecodeBase']]:
        ...


T = TypeVar('T', bound=BytecodeBase)


@dataclass(frozen=True, kw_only=True, slots=True)
class BytecodeContainer(Generic[T], BytecodeBase, ABC):
    """A simple bytecode type that just contains other types."""
    content: Sequence[T] = field(default_factory=list)

    def _encode(self) -> Iterator[T | BytecodeTypes]:
        print(f"encoding {type(self).__name__}: {len(self.content)}")
        yield _encode_u32(len(self.content))
        yield from self.content


from .code import *
from .types import *
from .binary import *


def _to_bytes(in_: Iterator[BytecodeTypes | BytecodeBase], silent=False) -> Iterator[bytes]:
    for x in in_:
        if not silent:
            print(f"Bytecode Structure to-bytes: {x}")
        match x:
            case BytecodeBase():
                yield from x.encode()
            case tuple():
                yield from _to_bytes((y for y in x), silent=True)
            case Enum():
                val = x.value
                assert isinstance(val, int) and \
                    max(type(x)._value2member_map_.keys()) < 255 and \
                    min(type(x)._value2member_map_.keys()) >= 0  # noqa
                yield _encode_u8(val)
            case int():
                yield _encode_u8(x)
            case float():
                yield _encode_f32(x)
            case bool():
                yield b'\x01' if x else b'\x00'
            case _:
                yield x
