from io import IOBase
from logging import getLogger
from typing import Iterator, Self

from .. import _encode_u16, _encode_u32, int_u16, int_u32, _decode_u16, _decode_u32
from . import BytecodeBase, BytecodeTypes

_LOG = getLogger(__package__)


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

    def __init__(self, name: int_u32, scope: int_u32, signature: int_u16, address: int_u32) -> None:
        self.name = name
        self.scope = scope
        self.signature = signature
        self.address = address

    def _encode(self) -> Iterator[BytecodeTypes | BytecodeBase]:
        _LOG.debug(f"\t\tName: string #{self.name}")
        yield _encode_u32(self.name)
        _LOG.debug(f"\t\tScope: string #{self.scope}" if self.scope else "\t\tScope: <global>")
        yield _encode_u32(self.scope)
        _LOG.debug(f"\t\tType: type #{self.signature}")
        yield _encode_u16(self.signature)
        _LOG.debug(f"\t\tCode: {self.name:#06x}")
        yield _encode_u32(self.address)

    @classmethod
    def decode(cls, stream: IOBase) -> Self:
        name = _decode_u32(stream.read(4))
        scope = _decode_u32(stream.read(4))
        signature = _decode_u16(stream.read(2))
        address = _decode_u32(stream.read(4))
        return cls(name, scope, signature, address)


__all__ = ('BytecodeFunction', )
