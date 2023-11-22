from enum import Enum
from io import IOBase
from logging import getLogger
from typing import TYPE_CHECKING, Iterator, Self

from ....types import TypeBase
from .. import _encode_numeric, _encode_u16, _encode_u32, int_u16, int_u32, _decode_u8, _decode_u32, _decode_u16, _decode_bool, _encode_bool
from . import BytecodeBase, BytecodeTypes

if TYPE_CHECKING:
    from ..builder import BytecodeBuilder
    from .binary import BytecodeBinary

_LOG = getLogger(__package__)


class BytecodeType(BytecodeBase):
    """A usertype definition."""

    class Type(Enum):
        TYPE_DEFINITION = 0
        IMPORTED_TYPE = 1
        VOID = 1

    type_: Type = Type.TYPE_DEFINITION
    _underlying: TypeBase | None

    name: int_u32 | None
    callable: tuple[tuple[int_u16, ...], int_u16] | None

    @classmethod
    def from_type(cls, builder: 'BytecodeBuilder', underlying: TypeBase) -> 'BytecodeType':
        name = builder.add_string(underlying.name)
        callable_: None | tuple[tuple[int_u16, ...], int_u16] = None
        if (underlying_callable := getattr(underlying, 'callable', None)) is not None:
            args, ret = underlying_callable
            ret_index = builder.add_type_type(ret)
            args_indexes = tuple(builder.add_type_type(t) for t in args)
            callable_ = args_indexes, ret_index
        # TODO: other type bits
        return cls(underlying=underlying, name=name, callable_=callable_)

    def __init__(self,
                 *,
                 underlying: TypeBase | None = None,
                 type_: Type = Type.TYPE_DEFINITION,
                 name: int_u32 | None = None,
                 callable_: tuple[tuple[int_u16, ...], int_u16] | None = None) -> None:
        self._underlying = underlying
        self.type_ = type_
        self.name = name
        self.callable = callable_
        if self.type_ == BytecodeType.Type.TYPE_DEFINITION:
            assert name is not None

    def _encode(self) -> Iterator[BytecodeTypes | BytecodeBase]:
        _LOG.debug(f"\t\tBuiltin: {self.type_}")
        yield self.type_
        if self.type_ not in (BytecodeType.Type.TYPE_DEFINITION, BytecodeType.Type.IMPORTED_TYPE):
            return
        assert self._underlying is not None
        assert self.name is not None
        _LOG.debug(f"\t\tName: {self._underlying.name} (string #{self.name})")
        yield _encode_u32(self.name)

        _LOG.debug(f"\t\tCallable: {self.callable is not None}")
        yield _encode_bool(self.callable is not None)
        if self.callable is not None:
            params = ', '.join(f"type #{x}" for x in self.callable[0])
            _LOG.debug(f"\t\t\tReturn: type #{self.callable[1]}; Params: ({params})")
            yield _encode_u16(self.callable[1])
            yield _encode_numeric(len(self.callable[0]), int_u16)
            yield from (_encode_u16(y) for y in self.callable[0])

    @classmethod
    def decode(cls, stream: IOBase) -> Self:
        type_ = BytecodeType.Type(_decode_u8(stream.read(1)))
        _LOG.debug('BytecodeType.type_ = %r', type_)
        if type_ not in (BytecodeType.Type.TYPE_DEFINITION, BytecodeType.Type.IMPORTED_TYPE):
            return cls(type_=type_)
        name = _decode_u32(stream.read(4))
        _LOG.debug('BytecodeType.name = %r', name)
        is_callable = _decode_bool(stream.read(1))
        _LOG.debug('BytecodeType.is_callable = %r', is_callable)
        callable_: None | tuple[tuple[int_u16, ...], int_u16] = None
        if is_callable:
            return_type = _decode_u16(stream.read(2))
            param_count = _decode_u16(stream.read(2))
            callable_ = tuple(_decode_u16(stream.read(2)) for _ in range(param_count)), return_type
        return cls(name=name, callable_=callable_)


__all__ = ('BytecodeType', )
