from logging import basicConfig, DEBUG
from enum import Enum

import struct

from . import Opcode, ParamType, Register
from .vm import VM

ASM = """

arg:
    "Hello, World"

_start:
    call main
    exit

main:
    push 21
    push 21
    call foo
    mov acc a
    pop
    pop
    mov a acc
    ret

foo:
    add rbp[1] rbp[2]
    ret

"""

from dataclasses import dataclass


@dataclass
class pending:
    name: str
    # length: int


def assemble(asm: str) -> tuple[int, bytes]:
    ret = []
    locs = {}

    for line in asm.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.endswith(':'):
            name = line[:-1]
            locs[name] = len(ret)
            print(f'Added location {name}={len(ret)}')
            continue
        if line.startswith('"'):
            line = line[1:-1]
            string = struct.pack(f'>{len(line)+1}s', line.encode('ascii') + b'\0')
            for b in string:
                ret.append(b)
            continue
        parts = line.split()

        match parts[0]:
            case 'call':
                ret.append(Opcode.CALL)
                func = parts[1]
                if func in locs:
                    ret.append(locs[func])
                else:
                    ret.append(pending(func))
                    ret.append(...)
            case 'exit':
                ret.append(Opcode.EXIT)
            case 'push':
                ret.append(Opcode.PUSH_LITERAL)
                ret.append(ParamType.i8)
                val = int(parts[1])
                assert 0 <= val <= 256
                ret.append(val)
            case 'mov':
                ret.append(Opcode.MOV)
                f = None
                t = None
                match parts[1]:
                    case 'acc':
                        ret.append(ParamType.Register)
                        f = Register.Accumulator
                    case 'a':
                        ret.append(ParamType.Register)
                        f = Register.A
                    case _:
                        raise NotImplementedError(f'mov from {parts[1]} is not implemented!')
                match parts[2]:
                    case 'a':
                        ret.append(ParamType.Register)
                        t = Register.A
                    case 'acc':
                        ret.append(ParamType.Register)
                        t = Register.Accumulator
                    case _:
                        raise NotImplementedError(f'mov from {parts[2]} is not implemented!')
                ret.append(f)
                ret.append(t)
            case 'pop':
                ret.append(Opcode.POP)
            case 'ret':
                ret.append(Opcode.RETURN)
            case 'add':
                ret.append(Opcode.ADD)
                after = []
                if parts[1].startswith('rbp'):
                    ret.append(ParamType.NearBase)
                    after.append(int(parts[1][4:-1]))
                if parts[1].startswith('rbp'):
                    ret.append(ParamType.NearBase)
                    after.append(int(parts[1][4:-1]))
                for a in after:
                    ret.append(a)
            case _:
                print(ret)
                raise NotImplementedError(f"{parts[0]} is not implemented!")

    for i, v in enumerate(list(ret)):
        if isinstance(v, pending):
            assert v.name in locs
            replace = struct.pack('>H', locs[v.name])
            for y, x in enumerate(replace):
                ret.pop(i + y)
                ret.insert(i + y, x)

    return locs.get('_start', 0), bytes(op.value if isinstance(op, Enum) else op for op in ret)


OPCODES: list[Opcode | ParamType | int] = [
    # _start
    *(Opcode.CALL, 0x00, 0x04),  # 0 call main @4
    Opcode.EXIT,  # 3 exit

    # main: int(str[])
    *(Opcode.PUSH_LITERAL, ParamType.i8, 0x15),  # 4 push u8:21
    *(Opcode.PUSH_LITERAL, ParamType.i8, 0x15),  # 7 push u8:21
    *(Opcode.CALL, 0, 26),  # 10 call foo@26
    *(Opcode.MOV, ParamType.Register, ParamType.Register, Register.Accumulator, Register.A),  # 13 mov ACC, A
    Opcode.POP,  # 18
    Opcode.POP,  # 19
    *(Opcode.MOV, ParamType.Register, ParamType.Register, Register.A, Register.Accumulator),  # 20 mov A, ACC
    Opcode.RETURN,  # 25

    # foo: int(a: int, b: int)
    *(Opcode.ADD, ParamType.NearBase, ParamType.NearBase, 1, 2),  # 26
    Opcode.RETURN  # 31
]
PROGRAM_G = bytes(op.value if isinstance(op, Enum) else op for op in OPCODES)

ENTRYPOINT, PROGRAM = assemble(ASM)


def main():
    """Entrypoint."""
    print(PROGRAM_G)
    print(PROGRAM)
    print(ENTRYPOINT)
    basicConfig(level=DEBUG)

    vm = VM(PROGRAM)
    vm.ip = ENTRYPOINT
    vm.run()


if __name__ == '__main__':
    main()
