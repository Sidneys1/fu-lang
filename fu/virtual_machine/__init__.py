from typing import TypeVar, Any
from dataclasses import dataclass, field

from ..types.integral_types import IntType, FloatType

from .bytecode import OpcodeEnum, getLogger, ParamType, NumericTypes

_LOG = getLogger(__name__)

T = TypeVar('T', bound=int)


@dataclass(slots=True)
class StackFrame:
    args: tuple[Any, ...]
    locals: list[Any] = field(init=False, default_factory=list)
    stack: list[Any] = field(init=False, default_factory=list)


class VM:
    """Fu virtual machine."""

    class VmTerminated(Exception):
        exit_code: int

        def __init__(self, exit_code: int) -> None:
            self.exit_code = exit_code

    code: bytes
    ip = 0

    _stack_frames: list[StackFrame] = []

    heap: list[tuple[Any, ...]] = []

    def __init__(self, code: bytes, args: list[str]):
        self.code = code

        arg_refs = []
        for arg in args:
            arg_refs.append(len(self.heap))
            self.heap.append((len(arg), *arg))
        self._stack_frames.append(StackFrame((len(self.heap), )))
        self.heap.append((len(arg_refs), *arg_refs))

        print(
            f"VM initialized with main(args: str[] = heap[{self._stack_frames[0].args[0]}]), heap: {self.heap}\n\tBytecode ({len(code):,} Bytes): {code!r}"
        )

    def run(self):
        input('Press enter to run...')
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
                return type.type_(self.slice(offset, offset + len(type)))

    def decode_op(self) -> tuple[int, OpcodeEnum, list[Any]]:
        op = OpcodeEnum(self.code[self.ip])
        # print(f'decoding {op}')
        length = 1
        params = []
        for t in op.params:
            # print(f'param type is {t}')
            if len(t) == 1:
                val = t.type_(self.code[self.ip + length])
            else:
                val = t.type_(self.code[self.ip + length:self.ip + length + len(t)])
            length += len(t)
            params.append(val)
        return length, op, params

    def step(self):
        length, op, params = self.decode_op()
        _LOG.debug(f"{self.ip:#04x}-{self.ip+length-1:#04x} {op.name}({params})")
        stack_frame = self._stack_frames[-1]

        _LOG.debug(f"\nStack: {stack_frame.stack} Locals: {stack_frame.locals}")

        match op:
            case OpcodeEnum.PUSH_ARG:
                """Push argument # onto the stack."""
                stack_frame.stack.append(stack_frame.args[params[0]])
                self.ip += length
            case OpcodeEnum.PUSH_REF:
                """Pop a heap ref off the stack, and push the value from the heap object's slot # onto the stack."""
                ref = stack_frame.stack.pop()
                stack_frame.stack.append(self.heap[ref][params[0]])
                self.ip += length
            case OpcodeEnum.PUSH_LOCAL:
                """Copy the value of a local onto the stack."""
                stack_frame.stack.append(stack_frame.locals[params[0]])
                self.ip += length
            case OpcodeEnum.CHECKED_CONVERT:
                """Pop a value off the heap and convert it to the target datatype, pushing the result on the heap."""
                to = params[0]
                assert isinstance(to, NumericTypes)
                to_type = to.to_type()
                match to_type:
                    case IntType():
                        min, max = to_type.range()
                        val = stack_frame.stack.pop()
                        if not isinstance(val, (int, float)) or min > val > max:
                            # todo: exceptions
                            raise RuntimeError(f"Checked numeric conversion from '{val!r}' to `{to.name}` failed")
                    case _:
                        raise NotImplementedError()
                stack_frame.stack.append(val)
                self.ip += length
            case OpcodeEnum.INIT_LOCAL:
                """Pop a value off the stack and append it to the locals."""
                stack_frame.locals.append(stack_frame.stack.pop())
                self.ip += length
            case OpcodeEnum.RET:
                """Copy the last stack value from this frame and push it onto the last frame, then delete this frame."""
                return_value = stack_frame.stack.pop() if stack_frame.stack else None
                self._stack_frames.pop()
                if not self._stack_frames:
                    assert return_value is None or isinstance(return_value, int)
                    raise VM.VmTerminated(return_value or 0)
                self._stack_frames[-1].stack.append(return_value)
            case _:
                raise NotImplementedError(f"Opcode {op.name} is not supported! At: {self.ip:#04x}.")


"""
push retaddr [retaddr]
push 1 [retaddr, 1]
push 2 [retaddr, 1, 2]
call foo
add i8 i8 [retaddr] (3)
return []
"""
