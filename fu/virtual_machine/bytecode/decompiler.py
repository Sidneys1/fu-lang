from io import SEEK_SET, BytesIO
from typing import Iterator

from ...color import RESET, COMMENT, NUM, FUNC_NAME, FAINT, KEYWORD, PARAM, TEMPLATE, CONSTANT, TYPE

from ...compiler import SourceLocation

from . import OpcodeEnum, _decode_u32, ParamType, int_u16, int_u32
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


def _get_function_id(fn_id: int_u16, binary: BytecodeBinary) -> str:
    scope, name = _get_fqdn(binary.functions[fn_id], binary.strings)
    if not scope:
        return name
    return scope + '.' + name


def decompile(bytecode: bytes, binary: BytecodeBinary | None = None, single_function: bool = False) -> Iterator[str]:
    if single_function and binary is None:
        raise ValueError("Cannot print single function if binary is not provided")

    functions: dict[int, tuple[str, str]] = {}
    longest_path = max(len(str(x))
                       for x in binary.source_map) if binary is not None and binary.source_map is not None else 0

    if binary:
        for func in binary.functions:
            fqdn, name = _get_fqdn(func, binary.strings)
            fqdn = (fqdn + '.' + name) if fqdn else name
            functions[func.address] = fqdn, f"{name}: {_get_signature(func, binary.strings, binary.types)}"
    with BytesIO(bytecode) as stream:
        pos = stream.tell()
        opcode: OpcodeEnum | None = OpcodeEnum.RET
        while True:
            last_opcode = opcode
            # last_pos = pos
            opcode, args, raw = OpcodeEnum.decode_op(stream)
            if opcode is None:
                break
            if binary is not None:
                args = tuple(
                    _get_function_id(a, binary) if p == ParamType.FunctionId else a
                    for p, a in zip(opcode.params, args))
            if last_opcode == OpcodeEnum.RET and pos in functions:
                if single_function:
                    return
                fqdn, sig = functions[pos]
                yield f"       {FAINT}│                               │ {RESET + FUNC_NAME}{fqdn + ':':<17}   {COMMENT}; {sig} = {{ /* ... */ }}{RESET}"

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
                op = f"{KEYWORD}{first}{RESET}.{PARAM}" + f'{RESET}.{PARAM}'.join(rest) + RESET
            else:
                op = KEYWORD + op + RESET

            asm = op
            if params:
                color = FUNC_NAME if opcode == OpcodeEnum.CALL_EXPORT else CONSTANT
                asm += ' ' + color + params + RESET
            asm += padding

            hex_bytes = ' '.join(f'{x:02x}' for x in raw)
            padding = ''
            if len(hex_bytes) < 29:
                padding = ' ' * (29 - len(hex_bytes))
            hb = hex_bytes.split(' ')
            hex_bytes = KEYWORD + hb[0] + RESET
            for i, b in enumerate(hb[1:]):
                if i < param_count:
                    hex_bytes += ' ' + PARAM + b
                elif opcode == OpcodeEnum.CALL_EXPORT:
                    hex_bytes += ' ' + FUNC_NAME + b
                else:
                    hex_bytes += ' ' + CONSTANT + b
            hex_bytes += RESET

            range_: str = ''
            end = stream.tell()
            if binary is not None and binary.source_map is not None:
                best: tuple[SourceLocation, tuple[int_u32, int_u32]] | None = None
                for (s, l), k in binary.source_map.items():
                    if s > pos or (s + l) < end:
                        continue
                    # print(f"{pos:#06x}-{end:#06x} is in {s:#06x}-{s+l:#06x}")
                    if best is None:
                        best = k, (s, l)
                        continue
                    bl = best[1][1]
                    if l < bl:
                        # print(f"{l:,} < {bl:,}")
                        best = k, (s, l)
                if best is not None:
                    range_ = f"{str(best[0]).ljust(longest_path)} │ "

            yield (f"{FAINT}{range_} {pos:#06x} │ {RESET + NUM}{hex_bytes + padding} "
                   f"{RESET + FAINT}│{RESET}   {asm} {COMMENT}; {explain}{RESET}")
            pos = end
