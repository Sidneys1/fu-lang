from io import BytesIO

from ...virtual_machine.bytecode import OpcodeEnum, _encode_numeric, int_u8

from .. import SourceLocation, CompilerNotice

from .storage import Storage, StorageDescriptor
from .util import write_to_buffer


def retrieve(from_: StorageDescriptor, buffer: BytesIO, loc: SourceLocation) -> StorageDescriptor:
    """Retrieve a SD from wherever it may be into the stack (if possible)."""
    from . import _LOG
    _LOG.debug(f"Retrieving {from_.storage}[{from_.slot}] onto the stack...")

    if from_.storage == Storage.Stack:
        # Already in the stack!
        return from_

    match from_:
        case StorageDescriptor(storage=Storage.Arguments) if from_.slot is not None:
            # The thing we're trying to retrieve is in the current method's args.
            write_to_buffer(buffer, OpcodeEnum.PUSH_ARG, _encode_numeric(from_.slot, int_u8))
            return StorageDescriptor(Storage.Stack, from_.type)
        case StorageDescriptor(storage=Storage.Locals) if from_.slot is not None:
            # The thing we're trying to retrieve is in the current method's locals.
            write_to_buffer(buffer, OpcodeEnum.PUSH_LOCAL, _encode_numeric(from_.slot, int_u8))
            return StorageDescriptor(Storage.Stack, from_.type)
    raise CompilerNotice('Critical', f"Don't know how to get {from_.type.name} out of {from_.storage.name}", loc)
