from dataclasses import InitVar, dataclass, field
from enum import Enum, auto
from functools import partial
from io import BytesIO
from logging import getLogger
from typing import TYPE_CHECKING, Iterator, Optional

from ....types import TypeBase
from .. import _decode_u32, _encode_numeric, _encode_u16, _encode_u32, int_u16, int_u32
from . import BytecodeBase, BytecodeTypes
from fu.virtual_machine.bytecode.structures.binary import BytesIO

if TYPE_CHECKING:
    from ..builder import BytecodeBuilder

_LOG = getLogger(__package__)

# @dataclass(frozen=True, kw_only=True, slots=True)
# class BytecodeMember(BytecodeBase):
#     """A usertype definition."""

#     def _encode(self) -> Iterator[BytecodeTypes | BytecodeBase]:
#         raise NotImplementedError()
#         yield


@dataclass(frozen=True, slots=True)
class BytecodeTypeMod(BytecodeBase):
    ...


class BuiltinTypes(Enum):
    NOT_A_BUILTIN = 0
    void = auto()


@dataclass(frozen=True, slots=True)
class BytecodeType(BytecodeBase):
    """A usertype definition."""
    builtin: BuiltinTypes = BuiltinTypes.NOT_A_BUILTIN
    builder: InitVar[Optional['BytecodeBuilder']] = None
    underlying: InitVar[TypeBase | None] = None

    name: int_u32 | None = field(init=False, default=None)
    callable: tuple[tuple[int_u16, ...], int_u16] | None = field(init=False, default=None)

    def __post_init__(self, builder: Optional['BytecodeBuilder'] = None, underlying: TypeBase | None = None) -> None:
        if underlying is None:
            assert self.builtin != BuiltinTypes.NOT_A_BUILTIN
            return
        assert builder is not None

        _set = partial(object.__setattr__, self)

        _set('name', builder.add_string(underlying.name))

        if underlying.callable is not None:
            args, ret = underlying.callable
            ret_index = builder.add_type_type(ret)
            args_indexes = tuple(builder.add_type_type(t) for t in args)
            _set('callable', (args_indexes, ret_index))

    def _encode(self) -> Iterator[BytecodeTypes | BytecodeBase]:
        _LOG.debug("Builtin")
        yield self.builtin
        if self.builtin != BuiltinTypes.NOT_A_BUILTIN:
            return

        assert self.name is not None
        _LOG.debug("Name")
        yield _encode_u32(self.name)

        _LOG.debug("Callable?")
        yield self.callable is not None
        if self.callable is not None:
            yield _encode_u16(self.callable[1])
            yield _encode_numeric(len(self.callable[0]), int_u16)
            yield from (_encode_u16(y) for y in self.callable[0])

    # @classmethod
    # def decode(cls, stream: BytesIO) -> tuple['BytecodeType', bytes]:
    #     _LOG.debug("Builtin")
    #     builtin = BuiltinTypes(stream.read(1)[0])
    #     if builtin != BuiltinTypes.NOT_A_BUILTIN:
    #         return BytecodeType(builtin)

    #     _LOG.debug("Name")
    #     name = _decode_u32(stream.read(4))
    #     input(name)

    #     # _LOG.debug("Callable?")
    #     # yield self.callable is not None
    #     # if self.callable is not None:
    #     #     yield _encode_u16(self.callable[1])
    #     #     yield _encode_numeric(len(self.callable[0]), int_u16)
    #     #     yield from (_encode_u16(y) for y in self.callable[0])
    #     raise NotImplementedError()


__all__ = ('BytecodeType', 'BuiltinTypes')
