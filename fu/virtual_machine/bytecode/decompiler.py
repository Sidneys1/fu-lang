from io import SEEK_SET, BytesIO
from typing import Iterator

from ...color import RESET, COMMENT, NUM, FUNC_NAME, FAINT, KEYWORD, PARAM, TEMPLATE, CONSTANT, TYPE

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
                    yield f'       {FAINT}│                        │ {RESET + FUNC_NAME}<unknown>:{RESET}'
                elif binary is not None:
                    func = next((x for x in binary.functions if x.address == last_pos), None)
                    if func is not None:
                        fqdn, name = _get_fqdn(func, binary.strings)
                        fqdn = (fqdn + '.' + name) if fqdn else name
                        sig = _get_signature(func, binary.strings, binary.types)
                        yield f"       {FAINT}│                   │ {RESET + FUNC_NAME}{fqdn + ':':<17}   {COMMENT}; {name}: {sig} = {{ /* ... */ }}{RESET}"

            asm, explain = opcode.as_asm(*args)
            padding = ''
            if len(asm) < 17:
                padding = ' ' * (17 - len(asm))
            op = asm
            params = ''
            if ' ' in asm:
                op, params = asm.split(' ', maxsplit=1)
            # input(f"{asm!r} -> {op!r} - {params!r}")

            param_count = 0
            if '.' in op:
                first, *rest = op.split('.')
                param_count = len(rest)
                op = f"{KEYWORD}{first}{RESET}.{TYPE}" + f'{RESET}.{TYPE}'.join(rest) + RESET
            else:
                op = KEYWORD + op + RESET

            asm = op
            if params:
                asm += ' ' + CONSTANT + params + RESET
            asm += padding

            hex_bytes = ' '.join(f'{x:02x}' for x in raw)
            padding = ''
            if len(hex_bytes) < 17:
                padding = ' ' * (17 - len(hex_bytes))
            hb = hex_bytes.split(' ')
            hex_bytes = KEYWORD + hb[0] + RESET
            for i, b in enumerate(hb[1:]):
                if i < param_count:
                    hex_bytes += ' ' + TYPE + b
                else:
                    hex_bytes += ' ' + CONSTANT + b
            hex_bytes += RESET

            yield (f"{FAINT}{pos:#06x} │ {RESET + NUM}{hex_bytes + padding} "
                   f"{RESET + FAINT}│{RESET}   {asm} {COMMENT}; {explain}{RESET}")
            pos = stream.tell()
