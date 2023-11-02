from io import SEEK_SET, BytesIO
from typing import Iterator

from . import OpcodeEnum, _decode_u32
from .structures import BytecodeBinary, BytecodeFunction, BytecodeType


def _get_string(index: int, stream: BytesIO) -> str:
    stream.seek(index, SEEK_SET)
    length = _decode_u32(stream.read(4))
    return '' if length == 0 else stream.read(length).decode('utf-8')


def _get_fqdn(func: BytecodeFunction, strings: bytes) -> tuple[str, str]:
    with BytesIO(strings) as stream:
        scope = _get_string(func.scope, stream)
        name = _get_string(func.name, stream)
    return scope, name


def _get_signature(func: BytecodeFunction, strings: bytes, types: list[BytecodeType]) -> str:
    t = types[func.signature]
    assert t.name is not None
    with BytesIO(strings) as stream:
        return _get_string(t.name, stream)


def decompile(bytecode: bytes, binary: BytecodeBinary | None = None) -> Iterator[str]:
    with BytesIO(bytecode) as stream:
        pos = stream.tell()
        opcode: OpcodeEnum | None = OpcodeEnum.RET
        while True:
            last_opcode = opcode
            last_pos = pos
            opcode, args, raw = OpcodeEnum.decode_op(stream)
            if opcode is None:
                break
            if last_opcode == OpcodeEnum.RET:
                if binary is None:
                    yield '       |          | <unknown>:'
                elif binary is not None:
                    func = next((x for x in binary.functions if x.address == last_pos), None)
                    if func is not None:
                        fqdn, name = _get_fqdn(func, binary.strings)
                        fqdn = (fqdn + '.' + name) if fqdn else name
                        sig = _get_signature(func, binary.strings, binary.types)
                        yield f"       |          | {fqdn + ':':<14} ; {name}: {sig} = {{ /* ... */ }}"

            pos = stream.tell()
            asm, explain = opcode.as_asm(*args)
            hex_bytes = ' '.join(f'{x:02x}' for x in raw)
            yield f"{pos:#06x} | {hex_bytes:<8} |   {asm:<12} ;   {explain}"
