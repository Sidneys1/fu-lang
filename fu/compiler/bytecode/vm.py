from . import Opcode, getLogger, ParamType, Register
from typing import TypeVar, Any

_LOG = getLogger(__name__)

T = TypeVar('T', bound=int)


class VM:
    """Fu virtual machine."""
    code: bytes
    ip = 0
    esp = 0
    ebp = 0

    _stack = [
        0  # Reference (index) to arg array in heap
    ]

    @property
    def accumulator(self):
        return self.registers[Register.Accumulator]

    @accumulator.setter
    def accumulator(self, value):
        self.registers[Register.Accumulator] = value

    heap = [[1], b'foobar']

    registers: dict[Register, Any] = {Register.Accumulator: None, Register.A: None}

    def push(self, val):
        self._stack.append(val)
        self.esp += 1

    def pop(self):
        self.esp -= 1
        return self._stack.pop()

    def __init__(self, code: bytes):
        self.code = code

    def run(self):
        while True:
            if 0 > self.ip or self.ip >= len(self.code):
                raise RuntimeError(f'Instruction pointer out of bounds!')
            self.step()

    def slice(self, start, end) -> int | bytes:
        if (end - start) == 1:
            return self.code[self.ip + start]
        return self.code[self.ip + start:self.ip + end]

    def decode_param(self, offset: int, type: ParamType):
        match type:
            case ParamType.NearBase:
                ebp_off = self.slice(offset, offset + len(type)) + 1
                # print(f'Decoding param near EBP: {ebp_off}')
                return self._stack[self.ebp - ebp_off]
            case _:
                return type.type(self.slice(offset, offset + len(type)))

    def decode_op(self) -> tuple[int, Opcode, list[Any]]:
        op = Opcode(self.code[self.ip])
        # print(f'decoding {op}')
        length = 1
        params = []
        for t in op.params:
            # print(f'param type is {t}')
            if len(t) == 1:
                val = t.type(self.code[self.ip + length])
            else:
                val = t.type(self.code[self.ip + length:self.ip + length + len(t)])
            length += len(t)
            params.append(val)
        return length, op, params

    def step(self):
        length, op, params = self.decode_op()
        _LOG.debug(f"{self.ip:#04x}-{self.ip+length-1:#04x} {op.name}({params})")
        match op:
            case Opcode.NOP:
                pass

            # Stack and Accumulator...
            case Opcode.STOR_LITERAL:
                self.accumulator = self.decode_param(length, params[0])
                length += len(params[0])
                _LOG.debug(f"\tStoring a literal {params[0].name}({self.accumulator}) into the accumulator.")
            case Opcode.PUSH_LITERAL:
                self.push(self.decode_param(length, params[0]))
                length += len(params[0])
                _LOG.debug(f"\tStoring a literal {params[0].name}({self._stack[-1]}) onto the stack: {self._stack}.")
            case Opcode.POP:
                self.accumulator = self.pop()
                _LOG.debug(f"\tPopping {self.accumulator} off of the stack: {self._stack}")

            # Control flow...
            case Opcode.CALL:
                self.push(self.ip + length)
                self.push(self.ebp)
                self.ebp = self.esp
                self.ip = params[0]
                length += len(op.params[0])
                _LOG.debug(f"\tCalling {params[0]:#04x}, stack is now {self._stack}, {self.esp=}, {self.ebp=}.")
                return
            case Opcode.RETURN:
                self.ebp = self.pop()
                self.ip = self.pop()
                _LOG.debug(f"\tReturning to {self.ip:#04x}, stack is now {self._stack}, {self.esp=}, {self.ebp=}.")
                return
            case Opcode.EXIT:
                _LOG.debug(f"\tExiting with {self.accumulator}")
                raise SystemExit(self.accumulator)

            # Arithmetic
            case Opcode.ADD:
                # TODO: validate types are addable...
                a = self.decode_param(length, params[0])
                length += len(params[0])
                b = self.decode_param(length, params[1])
                length += len(params[1])
                self.accumulator = a + b
                _LOG.debug(f"\tAdding {a}+{b}={self.accumulator}.")
            case Opcode.MOV:
                src = self.decode_param(length, params[0])
                length += len(params[0])
                if isinstance(src, Register):
                    src = self.registers[src]
                dest = self.decode_param(length, params[1])
                length += len(params[1])
                match dest:
                    case Register():
                        self.registers[dest] = src
                    case _:
                        raise NotImplementedError(f"Mov to a {type(dest).__name__} is not implemented.")
                _LOG.debug(f"\tMoved {src} to {dest}.")

            case _:
                raise NotImplementedError(f"Opcode {op.name} is not supported! At: {self.ip:#04x}.")

        self.ip += length


"""
push retaddr [retaddr]
push 1 [retaddr, 1]
push 2 [retaddr, 1, 2]
call foo
add i8 i8 [retaddr] (3)
return []
"""
