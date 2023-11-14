from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO, IOBase
from typing import Generic, Iterator, NewType, Self, Sequence, TypeVar, Union

from .. import BytecodeTypes, _encode_f32, _encode_u8, int_u8, _encode_numeric, int_u32, float_f32


class BytecodeBase(ABC):  # type: ignore[misc]
    """Base class for all bytecode structures."""

    @classmethod
    def decode(cls, stream: IOBase) -> Self:
        raise NotImplementedError()

    def encode(self, stream: IOBase) -> None:
        for x in _to_bytes(self._encode()):
            stream.write(x)

    @abstractmethod
    def _encode(self) -> Iterator[Union[BytecodeTypes, 'BytecodeBase']]:
        ...


T = TypeVar('T', bound=BytecodeBase)


class BytecodeContainer(Generic[T], BytecodeBase, ABC):  # type: ignore[misc]
    """A simple bytecode type that just contains other types."""
    content: Sequence[T] = field(default_factory=list)

    def _encode(self) -> Iterator[T | BytecodeTypes]:
        print(f"encoding {type(self).__name__}: {len(self.content)}")
        yield _encode_numeric(len(self.content), int_u32)
        yield from self.content


from .binary import *
from .code import *
from .types import *


def _to_bytes(in_: Iterator[BytecodeTypes | BytecodeBase], silent=False) -> Iterator[bytes]:
    for x in in_:
        # if not silent:
        #     print(f"Bytecode Structure to-bytes: {x}")
        match x:
            case BytecodeBase():
                yield from _to_bytes(x._encode())
            case tuple():
                yield from _to_bytes((y for y in x), silent=True)
            case Enum():
                val = x.value
                assert isinstance(val, int) and \
                    max(type(x)._value2member_map_.keys()) < 255 and \
                    min(type(x)._value2member_map_.keys()) >= 0  # noqa
                yield _encode_numeric(val, int_u8)
            case int():
                yield _encode_numeric(x, int_u8)
            case float():
                yield _encode_numeric(x, float_f32)
            case bool():
                yield b'\x01' if x else b'\x00'
            case _:
                yield x
