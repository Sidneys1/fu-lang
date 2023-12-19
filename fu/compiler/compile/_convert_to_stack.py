from ...types import FloatType, IntType, TypeBase
from ...types.integral_types import FloatType, IntType, TypeBase
from ...virtual_machine.bytecode import NumericTypes, OpcodeEnum, _encode_numeric, int_u8
from ...virtual_machine.bytecode.structures import BytesIO, SourceLocation, int_u8

from .. import CompilerNotice

from .storage import Storage, StorageDescriptor
from .util import write_to_buffer


def convert_to_stack(from_: StorageDescriptor,
                     to_: TypeBase,
                     buffer: BytesIO,
                     loc: SourceLocation,
                     checked=True) -> None:
    from . import _LOG
    _LOG.debug(f"Converting from `{from_.type.name}` to `{to_.name}`.")
    if from_.type == to_:
        match from_.storage:
            case Storage.Stack:
                return
            case Storage.Locals:
                assert from_.slot is not None
                write_to_buffer(buffer, OpcodeEnum.PUSH_LOCAL, _encode_numeric(from_.slot, int_u8))
                return
            case Storage.Arguments:
                assert from_.slot is not None
                write_to_buffer(buffer, OpcodeEnum.PUSH_ARG, _encode_numeric(from_.slot, int_u8))
                return
            case Storage.Static:
                assert from_.slot is not None
                # TODO: write PUSH_STATIC opcode
                return
            case _:
                raise NotImplementedError(f"Don't know how to move a {from_.storage} onto the stack.")
    match from_.type, to_:
        case IntType(), IntType():
            write_to_buffer(buffer, OpcodeEnum.CHECKED_CONVERT if checked else OpcodeEnum.UNCHECKED_CONVERT,
                            NumericTypes.from_int_type(to_).value)
            return
        case FloatType(), IntType():
            write_to_buffer(buffer, OpcodeEnum.CHECKED_CONVERT if checked else OpcodeEnum.UNCHECKED_CONVERT,
                            NumericTypes.from_int_type(to_).value)
            return
        case _:
            raise CompilerNotice(
                'Error',
                f"Not sure how to convert from `{from_.type.name}` ({type(from_.type).__name__}) on the {from_.storage.name} to `{to_.name}`.",
                loc)
