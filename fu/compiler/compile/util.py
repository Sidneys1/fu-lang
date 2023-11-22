# type: ignore
from io import BytesIO
from enum import Enum
from typing import TYPE_CHECKING, Iterator

from ...virtual_machine.bytecode import BytecodeTypes, _encode_f32, _encode_numeric, _encode_u8, int_u8

if TYPE_CHECKING:
    from .label import Label


def write_to_buffer(buffer: BytesIO, *args: BytecodeTypes | Enum | 'Label', silent=False) -> None:
    from .label import Label
    for x in args:
        # if not silent:
        #     print(repr(x))
        match x:
            case Label():
                buffer.write(x.relative())
            case tuple():
                for y in x:
                    write_to_buffer(buffer, y, silent=True)
            case Enum():
                val = x.value
                # pylint: disable=protected-access
                assert (isinstance(val, int) and max(type(x)._value2member_map_.keys()) < 255  # noqa
                        and min(type(x)._value2member_map_.keys()) >= 0)  # noqa
                buffer.write(_encode_numeric(val, int_u8))
            case int():
                buffer.write(_encode_numeric(x, int_u8))
            case float():
                buffer.write(_encode_f32(x))
            case bytes():
                buffer.write(x)
            case _:
                raise NotImplementedError(f"Oopsie, don't know how to do {type(x).__name__} {x!r}")


def stream_to_bytes(in_: Iterator[BytecodeTypes], silent=False) -> Iterator[bytes]:
    for x in in_:
        # if not silent:
        #     print(x)
        match x:
            case tuple():
                yield from stream_to_bytes((y for y in x), silent=True)
            case Enum():
                val = x.value
                # pylint: disable=protected-access
                assert isinstance(val, int) and max(type(x)._value2member_map_.keys()) < 255 and min(
                    type(x)._value2member_map_.keys()) >= 0
                yield _encode_u8(val)
            case int():
                yield _encode_u8(x)
            case float():
                yield _encode_f32(x)
            case bool():
                yield b'\x01' if x else b'\x00'
            case _:
                yield x
