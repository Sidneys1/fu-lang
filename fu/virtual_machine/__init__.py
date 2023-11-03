from enum import Enum
from dataclasses import dataclass, field
from typing import Any, TypeVar
from inspect import isclass
from time import perf_counter
from operator import add, sub, mul, floordiv

from ..types.integral_types import FloatType, IntType
from .bytecode import NumericTypes, OpcodeEnum, ParamType, getLogger
from .bytecode.structures import BytecodeBinary

_LOG = getLogger(__name__)

T = TypeVar('T', bound=int)


@dataclass(slots=True)
class StackFrame:
    args: tuple[Any, ...]
    locals: list[Any] = field(init=False, default_factory=list)
    stack: list[Any] = field(init=False, default_factory=list)


@dataclass(slots=True, repr=False)
class Ref:
    value: int

    def __repr__(self) -> str:
        return f"@{self.value:x}"


@dataclass(slots=True, repr=False)
class Array:
    length: int
    _underlying: list[Any]

    def __getitem__(self, index: int) -> Any:
        if index == 0:
            return self.length
        return self._underlying[index - 1]

    def __repr__(self) -> str:
        return f"Array[{self.length}]<{','.join(repr(x) for x in self._underlying)}>"


class VM:
    """Fu virtual machine."""

    class VmTerminated(Exception):
        exit_code: int

        def __init__(self, exit_code: int) -> None:
            self.exit_code = exit_code

    code: bytes
    ip = 0

    _stack_frames: list[StackFrame] = []

    heap: list[Any] = []

    def _heap_repr(self) -> str:
        return '{' + ', '.join(f"@{i}: {v!r}" for i, v in enumerate(self.heap)) + '}'

    def __init__(self, binary: BytecodeBinary, args: list[str]):
        self.code = binary.bytecode

        assert binary.entrypoint is not None
        self.ip = binary.entrypoint

        arg_refs = []
        for arg in args:
            arg_refs.append(Ref(len(self.heap)))
            self.heap.append(arg)
        self._stack_frames.append(StackFrame((Ref(len(self.heap)), )))
        self.heap.append(Array(len(arg_refs), arg_refs))

        print(
            f"% VM initialized with main(args: str[] = {self._stack_frames[0].args[0]}), heap: {self._heap_repr()}\n% Bytecode ({len(self.code):,} Bytes):"
        )
        from .bytecode.decompiler import decompile
        for line in decompile(self.code, binary=binary):
            print('%     ', line, sep='')

    def run(self):
        input('% Press enter to run...')
        start = perf_counter()
        extra = ''
        try:
            while True:
                if 0 > self.ip or self.ip >= len(self.code):
                    raise RuntimeError(f'Instruction pointer out of bounds!')
                self.step()
        except VM.VmTerminated as ex:
            extra = f' with exit code {ex.exit_code}'
            raise
        finally:
            end = perf_counter()
            print(f"% vm terminated after {(end - start) * 1000:0.4f}ms{extra}.")

    def decode_op(self) -> tuple[int, OpcodeEnum, list[Any]]:
        op = OpcodeEnum(self.code[self.ip])
        # print(f'decoding {op}')
        length = 1
        params = []
        last: ParamType | NumericTypes | None = None
        for t in op.params:
            if t is Ellipsis:
                if isclass(last.type_) and issubclass(last.type_, Enum):
                    val = last.type_(self.code[self.ip + length])
                else:
                    val = last.type_(self.code[self.ip + length:self.ip + length + len(last)])
                length += len(last)
            else:
                if isclass(t.type_) and issubclass(t.type_, Enum):
                    val = t.type_(self.code[self.ip + length])
                else:
                    val = t.type_(self.code[self.ip + length:self.ip + length + len(t)])
                length += len(t)
            params.append(val)
            last = val
        return length, op, params

    def _get_slot_of(self, thing: Any, slot: int) -> Any:
        match thing:
            case str():
                if slot == 0:
                    return len(thing)
                return thing[slot + 1]
            case tuple() | Array():
                return thing[slot]
            case _:
                raise NotImplementedError(f"Don't know how to access slot {slot} of a {type(thing).__name__}")

    def step(self):
        length, op, params = self.decode_op()
        _LOG.debug(f"{self.ip:#04x}-{self.ip+length-1:#04x} {op.name}({params})")
        stack_frame = self._stack_frames[-1]

        if op == OpcodeEnum.PUSH_ARG:
            # Push argument # onto the stack.
            stack_frame.stack.append(stack_frame.args[params[0]])
            self.ip += length
        elif op == OpcodeEnum.PUSH_REF:
            # Pop a heap ref off the stack, and push the value from the heap object's slot # onto the stack.
            ref = stack_frame.stack.pop()
            assert isinstance(ref, Ref)
            value = self._get_slot_of(self.heap[ref.value], params[0])
            stack_frame.stack.append(value)
            self.ip += length
        elif op == OpcodeEnum.PUSH_LOCAL:
            # Copy the value of a local onto the stack.
            stack_frame.stack.append(stack_frame.locals[params[0]])
            self.ip += length
        elif op == OpcodeEnum.CHECKED_CONVERT:
            # Pop a value off the heap and convert it to the target datatype, pushing the result on the heap.
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
        elif op == OpcodeEnum.INIT_LOCAL:
            # Pop a value off the stack and append it to the locals.
            stack_frame.locals.append(stack_frame.stack.pop())
            self.ip += length
        elif op == OpcodeEnum.RET:
            # Copy the last stack value from this frame and push it onto the last frame, then delete this frame.
            return_value = stack_frame.stack.pop() if stack_frame.stack else None
            self._stack_frames.pop()
            if not self._stack_frames:
                assert return_value is None or isinstance(return_value, int), f"{return_value!r}"
                raise VM.VmTerminated(return_value or 0)
            self._stack_frames[-1].stack.append(return_value)
        elif op == OpcodeEnum.PUSH_LITERAL:
            # Push a literal onto the stack
            stack_frame.stack.append(params[1])
            self.ip += length
            # print(f'incrementing ip by {length}')
        elif op == OpcodeEnum.PUSH_ARRAY:
            # Pop an index
            index = stack_frame.stack.pop()
            # pop a ref
            ref = stack_frame.stack.pop()
            assert isinstance(ref, Ref)
            value = self._get_slot_of(self.heap[ref.value], index + 1)
            stack_frame.stack.append(value)
            self.ip += length
        elif op in (OpcodeEnum.CHECKED_ADD, OpcodeEnum.CHECKED_SUB, OpcodeEnum.CHECKED_MUL, OpcodeEnum.CHECKED_IDIV):
            rhs = stack_frame.stack.pop()
            lhs = stack_frame.stack.pop()
            type_ = params[0]
            assert isinstance(type_, NumericTypes)
            n_type = NumericTypes.to_type(type_)

            val = {
                OpcodeEnum.CHECKED_ADD: add,
                OpcodeEnum.CHECKED_SUB: sub,
                OpcodeEnum.CHECKED_MUL: mul,
                OpcodeEnum.CHECKED_IDIV: floordiv
            }[op](lhs, rhs)
            assert isinstance(n_type, IntType)
            min_, max_ = n_type.range()
            if min_ > val > max_:
                # TODO: checked exception
                pass
            stack_frame.stack.append(val)
            self.ip += length
        else:
            raise NotImplementedError(f"Opcode {op.name} is not supported! At: {self.ip:#04x}.")

        _LOG.debug(f"\tAfter: Stack {stack_frame.stack}; Locals {stack_frame.locals}")


"""
push retaddr [retaddr]
push 1 [retaddr, 1]
push 2 [retaddr, 1, 2]
call foo
add i8 i8 [retaddr] (3)
return []
"""
