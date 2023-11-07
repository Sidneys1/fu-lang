from contextlib import contextmanager, AbstractContextManager
from contextvars import ContextVar, Token as ContextVarToken
from dataclasses import dataclass
from enum import Enum
from logging import getLogger
from typing import ContextManager, Generator, Iterable, Iterator, Optional, Any

from ..types import ARRAY_TYPE, STR_ARRAY_TYPE, VOID_TYPE, FloatType, GenericType, IntType, TypeBase
from ..types.integral_types import *
from ..virtual_machine.bytecode import (BytecodeTypes, NumericTypes, OpcodeEnum, _encode_f32, _encode_numeric,
                                        _encode_u8, int_u8, int_i16)
from ..virtual_machine.bytecode.builder import BytecodeBuilder
from ..virtual_machine.bytecode.structures import *
from . import CompilerNotice
from .analyzer.checks._check_conversion import _check_conversion
from .analyzer.scope import _CURRENT_ANALYZER_SCOPE, AnalyzerScope, StaticVariableDecl
from .analyzer.static_type import type_from_lex
from .lexer import (Declaration, Identifier, Identity, Lex, LexedLiteral, Operator, ParamList, ReturnStatement, Scope,
                    Statement, Expression, Atom, Operator, IfStatement)
from .tokenizer import Token, TokenType
from .util import is_sequence_of, collect_returning_generator

_LOG = getLogger(__package__)

REF_TYPE_T = GenericType.GenericParam('T')
REF_TYPE = GenericType('ref', size=4, reference_type=False, generic_params={'T': REF_TYPE_T})


def make_ref(t: TypeBase) -> GenericType:
    return REF_TYPE.resolve_generic_instance(T=t)  # type: ignore


FUNCTIONS: BytecodeFunction = []


# @dataclass(frozen=True, kw_only=True, slots=True)
class CompileScope(ContextManager):
    name: str
    parent: Optional['CompileScope']
    _reset_tok: ContextVarToken | None = None
    _reset_static_tok: ContextVarToken | None = None
    static_scope: AnalyzerScope

    def __init__(self, name: str, root=False):
        self.name = name
        self.parent = CompileScope.current() if not root else None
        if self.parent is None:
            self.static_scope = AnalyzerScope.current()
        else:
            static_scope = self.parent.static_scope.get_child(name)
            if static_scope is None:
                raise RuntimeError()
            self.static_scope = static_scope
            assert self.static_scope is not None

    def __enter__(self):
        self._reset_tok = _CURRENT_COMPILE_SCOPE.set(self)
        self._reset_static_tok = _CURRENT_ANALYZER_SCOPE.set(self.static_scope)
        return self

    def __exit__(self, *args) -> None:
        assert self._reset_tok is not None and self._reset_static_tok is not None
        _CURRENT_COMPILE_SCOPE.reset(self._reset_tok)
        _CURRENT_ANALYZER_SCOPE.reset(self._reset_static_tok)
        self._reset_static_tok = None
        self._reset_tok = None

    @staticmethod
    def current() -> 'CompileScope':
        return _CURRENT_COMPILE_SCOPE.get()

    @property
    def fqdn(self) -> str:
        names = [self.name]
        p = self.parent
        while p is not None and p.parent is not None:
            names.append(p.name)
            p = p.parent
        return '.'.join(reversed(names))


@contextmanager
def enter_global_scope(scope: CompileScope):
    tok = _CURRENT_COMPILE_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _CURRENT_COMPILE_SCOPE.reset(tok)


class FunctionScope(CompileScope):
    args: dict[str, TypeBase]
    locals: dict[str, TypeBase]
    decls: dict[str, TypeBase]
    returns: TypeBase

    def __init__(self,
                 name: str,
                 returns: TypeBase,
                 args: dict[str, TypeBase] | None = None,
                 decls: dict[str, TypeBase] | None = None) -> None:
        super().__init__(name)
        self.returns = returns
        self.args = args or {}
        self.decls = decls or {}
        self.locals = {}

    @staticmethod
    def current_fn() -> Optional['FunctionScope']:
        current: CompileScope | None = _CURRENT_COMPILE_SCOPE.get()
        while current is not None and current.parent is not None and not isinstance(current, FunctionScope):
            current = current.parent
        assert current is None or isinstance(current, FunctionScope)
        return current

    def __repr__(self) -> str:
        args = ', '.join(f"{k}: {v.name}" for k, v in self.args.items())
        return f"{self.fqdn}({args})"


_CURRENT_COMPILE_SCOPE: ContextVar[CompileScope] = ContextVar('_CURRENT_COMPILE_SCOPE')


def write_to_buffer(buffer: BytesIO, *args: BytecodeTypes | Enum | 'Label', silent=False) -> None:
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


_BUILDER = BytecodeBuilder()


def compile() -> Generator[CompilerNotice, None, BytecodeBinary | None]:
    _LOG.debug('\n\n\033#3STARTED COMPILING\n\033#4STARTED COMPILING\n\n')
    global_scope = AnalyzerScope.current()
    main = global_scope.members.get('main')

    if main is None:
        # dll?
        yield CompilerNotice('Error', "No entrypoint (symbol named `main`) found in global scope.", None)
        # _LOG.critical(f"Nothing to compile (no `main` symbol). Exiting.")
        return

    assert isinstance(main, StaticVariableDecl), f"Main was a {type(main).__name__}"
    if main.type.callable is None:
        yield CompilerNotice('Error', "Main must be a method.", main.location)
        return None
    params, return_type = main.type.callable
    if return_type not in (VOID_TYPE, U8_TYPE, I8_TYPE, U16_TYPE, I16_TYPE, U32_TYPE, I32_TYPE, U64_TYPE, I64_TYPE):
        assert isinstance(main.lex, Declaration)
        yield CompilerNotice('Error', "Main does not return an `i8`/`u8`/`void`, "
                             f"instead: `{return_type.name}`", main.lex.identity.rhs.ident.location)
        return None
    if params != ():
        with global_scope.enter('main'):
            allowed = yield from _check_conversion(params[0], STR_ARRAY_TYPE, main.lex.identity.rhs.mods[-1].location)
        if not allowed:
            yield CompilerNotice('Error', "Main must take no arguments: `()`; or one argument: `(str[])`. "
                                 f"Got `({', '.join(x.name for x in params)})` instead.",
                                 main.lex.identity.rhs.mods[-1].location,
                                 extra=[ex])
            return None

    main_func: BytecodeFunction
    global_compile_scope = CompileScope('<ROOT>', True)
    with enter_global_scope(global_compile_scope):
        try:
            main_func = compile_func(main)
        except CompilerNotice as ex:
            yield ex
            return None
        # ret = b''.join(to_bytes(main_func.encode()))
        # func, x = BytecodeFunction.decode(ret)
        # for block in func.content:
        #     print("Block:")
        #     for line in block.content:
        #         print(f"\tLine: {line.content!r}")
        _BUILDER.add_function(main_func)
        ret = _BUILDER.finalize(entrypoint=main_func.address)

    return ret


class Storage(Enum):
    Arguments = 'args'
    Locals = 'locals'
    Heap = 'heap'
    Stack = 'stack'


@dataclass(slots=True)
class StorageDescriptor:

    storage: Storage
    type: TypeBase
    slot: int | None = None

    def __post_init__(self) -> None:
        assert isinstance(self.type, TypeBase)


@dataclass(slots=True)
class TempSourceMap:
    offset: int
    length: int
    location: SourceLocation


def _storage_type_of(name: str, loc: SourceLocation) -> StorageDescriptor:
    current_fn = FunctionScope.current_fn()
    if current_fn is None:
        raise NotImplementedError()
    for i, (k, v) in enumerate(current_fn.args.items()):
        if k == name:
            return StorageDescriptor(Storage.Arguments, v, slot=i)
    for i, (k, v) in enumerate(current_fn.locals.items()):
        if k == name:
            return StorageDescriptor(Storage.Locals, v, slot=i)
    for k, v in current_fn.decls.items():
        if k == name:
            return StorageDescriptor(Storage.Locals, v, slot=None)
    raise CompilerNotice('Error', f"Cannot find `{name}` in `{current_fn.fqdn}`.", loc)


def retrieve(from_: StorageDescriptor, buffer: BytesIO, loc: SourceLocation) -> StorageDescriptor:
    _LOG.debug(f"Retrieving {from_.storage}[{from_.slot}] onto the stack...")
    if from_.storage == Storage.Stack:
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


def compile_expression(expression: Lex,
                       buffer: BytesIO,
                       want: TypeBase | None = None) -> Generator[TempSourceMap, None, StorageDescriptor]:
    _LOG.debug(f'Compiling expression: {str(expression).strip()} (want: `{want.name if want is not None else want}`)')
    scope = CompileScope.current()
    start = buffer.tell()
    match expression:
        case LexedLiteral():
            value = expression.to_value()
            match value, want:
                case bool(), BOOL_TYPE:
                    write_to_buffer(buffer, OpcodeEnum.PUSH_LITERAL, NumericTypes.bool, b'\x01' if value else b'\x00')
                    return StorageDescriptor(Storage.Stack, BOOL_TYPE)
                case float(), None:
                    # TODO: best float type for literal
                    pass
                case float(), _ if want == F32_TYPE:
                    write_to_buffer(buffer, OpcodeEnum.PUSH_LITERAL, NumericTypes.f32,
                                    _encode_numeric(value, float_f32))
                    return StorageDescriptor(Storage.Stack, F32_TYPE)
                case int(), None:
                    # TODO: best int type for literal
                    pass
                case int(), _ if want == U8_TYPE:
                    #input(f"{want.name} -> {U8_TYPE.name}")
                    write_to_buffer(buffer, OpcodeEnum.PUSH_LITERAL, NumericTypes.u8, _encode_numeric(value, int_u8))
                    return StorageDescriptor(Storage.Stack, U8_TYPE)
                case int(), _ if want == U32_TYPE:
                    #input(f"{want.name} -> {U8_TYPE.name}")
                    write_to_buffer(buffer, OpcodeEnum.PUSH_LITERAL, NumericTypes.u32, _encode_numeric(value, int_u32))
                    return StorageDescriptor(Storage.Stack, U32_TYPE)
                case int(), IntType():
                    raise NotImplementedError(f"Unknown inttype `{want.name}`.")
            raise NotImplementedError(
                f"Don't know how to handle {type(value).__name__} literals (want={want.name if want is not None else None})."
            )
        case Operator(oper=Token(type=TokenType.Equals), lhs=Identifier(), rhs=Lex()):
            assert isinstance(expression.lhs, Identifier)
            assert expression.rhs is not None
            rhs_storage = yield from compile_expression(expression.rhs, buffer)
            lhs_storage = _storage_type_of(expression.lhs.value)
            convert_to_stack(rhs_storage, lhs_storage.type, buffer, expression.rhs.location)
            match lhs_storage.storage:
                case Storage.Locals:
                    if lhs_storage.slot is None:
                        fn_scope = FunctionScope.current_fn()
                        assert fn_scope is not None
                        write_to_buffer(buffer, OpcodeEnum.INIT_LOCAL)
                        slot = len(fn_scope.locals)
                        fn_scope.locals[expression.lhs.value] = lhs_storage.type
                        yield TempSourceMap(start, buffer.tell() - start, expression.location)
                        return StorageDescriptor(Storage.Locals, lhs_storage.type, slot)
                    else:
                        write_to_buffer(buffer, OpcodeEnum.POP_LOCAL, _encode_numeric(lhs_storage.slot, int_u8))
                        yield TempSourceMap(start, buffer.tell() - start, expression.location)
                        return lhs_storage
                case _:
                    raise NotImplementedError()
        case Operator(oper=Token(type=TokenType.Dot), rhs=Identifier()):
            _LOG.debug("...dot operator")
            # what is lhs?
            assert expression.lhs is not None and isinstance(expression.rhs, Identifier)
            lhs_storage = yield from compile_expression(expression.lhs, buffer)
            # assert isinstance(expression.lhs, Identifier) and isinstance(expression.rhs, Identifier)
            # lhs_storage = _storage_type_of(expression.lhs.value, expression.lhs.location)
            if lhs_storage is None:
                # _LOG.debug("...error")
                raise CompilerNotice('Error', f"Couldn't resolve `{expression.lhs.value}` in {scope.fqdn}.",
                                     expression.location)
            # Get left side somewhere we can access it
            lhs_storage = retrieve(lhs_storage, buffer, expression.lhs.location)
            # input(f'Ran retrieve, lhs storage is now {lhs_storage}')
            _LOG.debug(f"...new storage is {lhs_storage.type.name}")
            if isinstance(lhs_storage.type, GenericType) and REF_TYPE in lhs_storage.type.generic_inheritance:  # type: ignore # noqa: W1116  # pylint:disable=isinstance-second-argument-not-valid-type
                assert isinstance(lhs_storage.type, GenericType)
                lhs_deref = lhs_storage.type.generic_params['T']
                assert not isinstance(lhs_deref, GenericType.GenericParam)
                # TODO: actually determine slot of rhs
                # assume for now that it's in declaration order?
                slot_num = -1
                slot_type: TypeBase
                for i, (k, v) in enumerate(lhs_deref.members.items()):
                    if k == expression.rhs.value:
                        slot_num = i
                        slot_type = v
                        break
                if slot_num == -1:
                    # GFCS?
                    _LOG.error("...gfcs")
                    raise CompilerNotice('Error',
                                         f"Couldn't find member `{expression.rhs.value}` in type `{lhs_deref.name}`.",
                                         expression.location)
                write_to_buffer(buffer, OpcodeEnum.PUSH_REF.value, _encode_numeric(slot_num, int_u8))
                yield TempSourceMap(start, buffer.tell() - start, expression.location)
                return StorageDescriptor(Storage.Stack, make_ref(slot_type) if slot_type.reference_type else slot_type)

            raise NotImplementedError()
        case Operator(oper=Token(type=TokenType.LBracket)):
            assert expression.rhs is not None
            lhs_storage = yield from compile_expression(expression.lhs, buffer)
            lhs_storage = retrieve(lhs_storage, buffer, expression.lhs.location)
            if isinstance(lhs_storage.type, REF_TYPE):  # noqa
                assert isinstance(lhs_storage.type, GenericType)
                lhs_deref = lhs_storage.type.generic_params['T']  # noqa
                # input(lhs_deref)
                assert not isinstance(lhs_deref, GenericType.GenericParam)
                if lhs_deref.inherits is not None and ARRAY_TYPE in lhs_deref.inherits:
                    rhs_storage = yield from compile_expression(expression.rhs, buffer, want=USIZE_TYPE)
                    rhs_storage = retrieve(rhs_storage, buffer, expression.rhs.location)
                    write_to_buffer(buffer, OpcodeEnum.PUSH_ARRAY)
                    ret_type = lhs_deref.indexable[1]
                    if ret_type.reference_type:
                        ret_type = make_ref(ret_type)
                    return StorageDescriptor(Storage.Stack, ret_type)
                # # TODO: actually determine slot of rhs
                # # assume for now that it's in declaration order?
                # slot_num = -1
                # slot_type: TypeBase
                # for i, (k, v) in enumerate(lhs_deref.members.items()):
                #     if k == expression.rhs.value:
                #         slot_num = i
                #         slot_type = v
                #         break
                # if slot_num == -1:
                #     # GFCS?
                #     _LOG.error("...gfcs")
                #     raise CompilerNotice('Error',
                #                          f"Couldn't find member `{expression.rhs.value}` in type `{lhs_deref.name}`.",
                #                          expression.location)
                # write_to_buffer(buffer, OpcodeEnum.PUSH_REF.value, _encode_numeric(slot_num, int_u8))
                # yield TempSourceMap(start, buffer.tell() - start, expression.location)
                # return StorageDescriptor(Storage.Stack, make_ref(slot_type) if slot_type.reference_type else slot_type)
            raise NotImplementedError()
        case Operator(oper=Token(type=TokenType.Operator), lhs=Lex(), rhs=Lex()):
            # Misc infix operator
            if expression.oper.value in ('+', '-', '*', '/'):
                # Awesome, addition! Let's see what types lhs and rhs are
                lhs_storage = yield from compile_expression(expression.lhs, buffer)
                lhs_storage = retrieve(lhs_storage, buffer, expression.lhs.location)

                rhs_storage = yield from compile_expression(expression.rhs, buffer)
                rhs_storage = retrieve(rhs_storage, buffer, expression.rhs.location)
                # Let's check types...
                match lhs_storage.type, rhs_storage.type:
                    case _, EnumType() | EnumType(), _:
                        raise NotImplementedError("Don't know how to add enums!")
                    case IntegralType(), FloatType() | FloatType(), IntegralType():
                        raise NotImplementedError("Result will be a float...")
                    case FloatType(), FloatType():
                        bittness = max(lhs_storage.type.size, rhs_storage.type.size)
                        match bittness:
                            case 2:
                                r_type, t_type = NumericTypes.f16, F16_TYPE
                            case 4:
                                r_type, t_type = NumericTypes.f32, F32_TYPE
                            case 8:
                                r_type, t_type = NumericTypes.f64, F64_TYPE
                            case _:
                                raise NotImplementedError()
                        write_to_buffer(
                            buffer, {
                                '+': OpcodeEnum.CHECKED_ADD,
                                '-': OpcodeEnum.CHECKED_SUB,
                                '*': OpcodeEnum.CHECKED_MUL,
                                '/': OpcodeEnum.CHECKED_FDIV,
                            }[expression.oper.value], r_type)
                        _LOG.debug(
                            f"Adding two floats... `{lhs_storage.type.name} + {rhs_storage.type.name} = {t_type.name}`")
                        return StorageDescriptor(Storage.Stack, t_type)
                    case IntType(), IntType():
                        bittness = max(lhs_storage.type.size, rhs_storage.type.size)
                        signedness = lhs_storage.type.signed or rhs_storage.type.signed
                        match bittness, signedness:
                            case 8, False:
                                r_type, t_type = NumericTypes.u64, U64_TYPE
                            case 8, True:
                                r_type, t_type = NumericTypes.i64, I64_TYPE
                            case 4, False:
                                r_type, t_type = NumericTypes.u32, U32_TYPE
                            case 4, True:
                                r_type, t_type = NumericTypes.i32, I32_TYPE
                            case 2, False:
                                r_type, t_type = NumericTypes.u16, U16_TYPE
                            case 2, True:
                                r_type, t_type = NumericTypes.i16, I16_TYPE
                            case 1, False:
                                r_type, t_type = NumericTypes.u8, U8_TYPE
                            case 1, True:
                                r_type, t_type = NumericTypes.i8, I8_TYPE
                            case _:
                                raise NotImplementedError()

                        write_to_buffer(
                            buffer, {
                                '+': OpcodeEnum.CHECKED_ADD,
                                '-': OpcodeEnum.CHECKED_SUB,
                                '*': OpcodeEnum.CHECKED_MUL,
                                '/': OpcodeEnum.CHECKED_IDIV,
                            }[expression.oper.value], r_type)
                        _LOG.debug(
                            f"Adding two ints... `{lhs_storage.type.name} + {rhs_storage.type.name} = {t_type.name}`")
                        return StorageDescriptor(Storage.Stack, t_type)
                        # raise NotImplementedError(
                        #     f"Result will be an int... -> {want.name if want is not None else None}")
                    case _, _:
                        raise NotImplementedError(
                            f"Don't know how to add {lhs_storage.type.name} and {rhs_storage.type.name}")
            else:
                raise NotImplementedError(f"Don't support infix Operator {expression.oper.value!r}")
        case Identifier():
            name = expression.value
            storage_type = _storage_type_of(name, expression.location)
            assert storage_type is not None
            return storage_type
        case Operator():
            raise CompilerNotice(
                'Error',
                f"Don't know how to compile `{type(expression.lhs).__name__} {expression.oper.value!r} {type(expression.rhs).__name__}`!",
                expression.location)
        case _:
            raise CompilerNotice('Error', f"Don't know how to compile expression `{type(expression).__name__}`!",
                                 expression.location)


def convert_to_stack(from_: StorageDescriptor,
                     to_: TypeBase,
                     buffer: BytesIO,
                     loc: SourceLocation,
                     checked=True) -> None:
    _LOG.debug(f"Converting from `{from_.type.name}` to `{to_.name}`.")
    if from_.type == to_:
        match from_.storage:
            case Storage.Stack:
                return
            case Storage.Locals:
                # get slot
                fn_scope = FunctionScope.current_fn()
                assert fn_scope is not None and from_.slot is not None
                write_to_buffer(buffer, OpcodeEnum.PUSH_LOCAL, _encode_numeric(from_.slot, int_u8))
                return
            case _:
                raise NotImplementedError()
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


@dataclass(slots=True)
class Label(AbstractContextManager):
    on: BytesIO
    patch_locations: list[int] = field(default_factory=list)
    _location: int | None = field(init=False, default=None)

    def append(self, *patch_locations: int) -> None:
        if self._location is not None:
            pos = self.on.tell()
            for x in self.patch_locations:
                self._patch(x)
            self.on.seek(pos)
            return
        self.patch_locations.extend(patch_locations)

    def relative(self) -> bytes:
        pos = self.on.tell()
        if self._location is not None:
            return _encode_numeric((self._location - pos) - 2, int_i16)
        self.patch_locations.append(pos)
        return b'\xde\xad'

    def _patch(self, patch_location: int) -> None:
        self.on.seek(patch_location)
        write_to_buffer(self.on, _encode_numeric((self._location - patch_location) - 2, int_i16))

    def link(self) -> None:
        """
        Link this Label to a location.

        Any existing patch_locations will be patched.

        Any future patch locations will be patched immediately.
        """
        if self._location is not None:
            raise ValueError()

        self._location = self.on.tell()
        while self.patch_locations:
            self._patch(self.patch_locations.pop())
        self.on.seek(self._location)

    def __exit__(self, __exc_type: type[BaseException] | None, _, __) -> bool | None:
        if __exc_type is None:
            self.link()
        return None


def _emit_if_head(term: Expression, buffer: BytesIO, next_case: Label) -> Iterator[TempSourceMap]:
    start = buffer.tell()
    storage = yield from compile_expression(term, buffer, BOOL_TYPE)
    convert_to_stack(storage, BOOL_TYPE, buffer, term.location)
    write_to_buffer(buffer, OpcodeEnum.JZ, next_case)
    yield TempSourceMap(start, buffer.tell() - start, term.location)


def _emit_if_body(content: Scope | Statement | ReturnStatement,
                  buffer: BytesIO,
                  *,
                  end_label: Label | None = None) -> Iterator[TempSourceMap]:
    if isinstance(content, Scope):
        yield from compile_blocks(content.content, buffer)
    else:
        yield from compile_statement(content, buffer)

    if end_label is not None:
        write_to_buffer(buffer, OpcodeEnum.JMP, end_label)


def compile_if_statement(statement: IfStatement, buffer: BytesIO) -> Iterator[TempSourceMap]:
    assert statement.term is not None
    next_case_label = Label(buffer)
    yield from _emit_if_head(statement.term, buffer, next_case_label)

    other_cases: list[IfStatement] = list(statement.content[1:])  # type: ignore

    has_else_block = other_cases and isinstance(last := statement.content[-1], IfStatement) and last.term is None
    else_block: IfStatement | None = None
    if has_else_block:
        last_block = other_cases.pop()
        assert isinstance(last_block, IfStatement)
        else_block = last_block

    end_label = Label(buffer)

    # jumps_to_end = []
    assert isinstance(
        statement.content[0],
        (Scope, Statement, ReturnStatement)), f"Body was unexpectedly a `{type(statement.content[0]).__name__}`!"
    yield from _emit_if_body(statement.content[0], buffer, end_label=end_label if bool(other_cases) else None)

    for case in other_cases:
        assert isinstance(case, IfStatement) and case.term is not None
        next_case_label.link()

        # Emit head
        next_case_label = Label(buffer)
        yield from _emit_if_head(case.term, buffer, next_case_label)

        # Emit body
        assert not isinstance(case.content[0], IfStatement)
        yield from _emit_if_body(case.content[0], buffer, end_label=end_label)

    next_case_label.link()

    if else_block is not None:
        # Emit body
        assert len(else_block.content) == 1
        assert not isinstance(else_block.content[0], IfStatement)
        yield from _emit_if_body(else_block.content[0], buffer)

    # Rewrite the jumps to the end...
    end_label.link()


def compile_statement(statement: Statement | IfStatement | Declaration | ReturnStatement,
                      buffer: BytesIO) -> Iterator[TempSourceMap]:
    # scope = CompileScope.current()
    fn_scope = FunctionScope.current_fn()
    _LOG.debug(f'Compiling statement: {str(statement).strip()}')
    # input()
    start = buffer.tell()
    match statement:
        case Declaration() if statement.initial is not None:
            # Initialize local.
            name = statement.identity.lhs.value
            assert fn_scope is not None
            local_type = fn_scope.decls[name]

            value_storage = yield from compile_expression(statement.initial, buffer, local_type)
            convert_to_stack(value_storage, local_type, buffer, statement.initial.location)
            write_to_buffer(buffer, OpcodeEnum.INIT_LOCAL)
            fn_scope.locals[name] = local_type
            yield TempSourceMap(start, buffer.tell() - start, statement.location)
        case Declaration():
            pass
        case Statement():
            yield from compile_expression(statement.value, buffer)
            yield TempSourceMap(start, buffer.tell() - start, statement.location)
        case ReturnStatement():
            if statement.value is not None:
                assert fn_scope is not None
                fn_ret = fn_scope.returns
                return_storage = yield from compile_expression(statement.value, buffer, want=fn_ret)
                _LOG.debug(f"...return_storage is {return_storage}")
                convert_to_stack(return_storage, fn_ret, buffer, statement.value.location)
            write_to_buffer(buffer, OpcodeEnum.RET)
            yield TempSourceMap(start, buffer.tell() - start, statement.location)
        case IfStatement():
            # evaluate thingy
            yield from compile_if_statement(statement, buffer)
            yield TempSourceMap(start, buffer.tell() - start, statement.location)
        case _:
            raise CompilerNotice('Error', f"Don't know how to compile statement of type `{type(statement).__name__}`!",
                                 statement.location)
    return None


def compile_blocks(statements: Iterable[Statement | Declaration | ReturnStatement | IfStatement],
                   buffer: BytesIO) -> Iterator[TempSourceMap]:
    for statement in statements:
        yield from compile_statement(statement, buffer)


def compile_func(func: StaticVariableDecl) -> BytecodeFunction:
    outer_scope = CompileScope.current()

    _LOG.debug(f'Compiling function {func.name}')
    assert isinstance(func.type, TypeBase)
    assert func.type.callable is not None
    element = func.lex
    assert isinstance(element, Declaration)

    # Determine args
    mods = element.identity.rhs.mods
    assert mods
    last_mod = mods[-1]
    assert isinstance(last_mod, ParamList)
    params = last_mod.params
    assert is_sequence_of(params, Identity)

    args = {params[i].lhs.value: (make_ref(v) if v.reference_type else v) for i, v in enumerate(func.type.callable[0])}
    decls: dict[str, TypeBase] = {}
    code: bytes
    source_locs: list[TempSourceMap] = []

    if element.is_fat_arrow:
        assert isinstance(element.initial, (Expression, Atom, Operator, Identifier, LexedLiteral))
        with FunctionScope(element.identity.lhs.value, func.type.callable[1], args=args,
                           decls=decls) as scope, BytesIO() as buffer:
            # TODO split in to branch-delimited blocks of code
            return_storage, source_maps = collect_returning_generator(compile_expression(element.initial, buffer))
            start = buffer.tell()
            convert_to_stack(return_storage, func.type.callable[1], buffer, element.initial.location)
            write_to_buffer(buffer, OpcodeEnum.RET)
            for source_loc in source_maps:
                source_locs.append(source_loc)
            source_locs.append(TempSourceMap(start, buffer.tell() - start, element.initial.location))
            code = buffer.getvalue()
    else:
        assert isinstance(element.initial, Scope)
        # Generate decls
        i = 0
        while i < len(element.initial.content):
            x = element.initial.content[i]
            if not isinstance(x, Declaration):
                i += 1
                continue
            decl_type = type_from_lex(x.identity.rhs, outer_scope.static_scope)
            if isinstance(decl_type, AnalyzerScope):
                i += 1
                continue
            if isinstance(decl_type, StaticVariableDecl):
                decl_type = decl_type.type
            decls[x.identity.lhs.value] = decl_type
            i += 1

        with FunctionScope(element.identity.lhs.value, func.type.callable[1], args=args,
                           decls=decls) as scope, BytesIO() as buffer:
            # TODO split in to branch-delimited blocks of code
            for source_loc in compile_blocks(element.initial.content, buffer):
                source_locs.append(source_loc)
            if OpcodeEnum(buffer.getbuffer()[-1]) != OpcodeEnum.RET:
                write_to_buffer(buffer, OpcodeEnum.RET)
            code = buffer.getvalue()

    assert isinstance(func.lex, Declaration)
    name = _BUILDER.add_string(func.lex.identity.lhs.value)
    scope = _BUILDER.add_string('' if outer_scope.parent is None else outer_scope.fqdn)
    signature = _BUILDER.add_type_type(func.type)
    address = _BUILDER.add_code(code)

    # for loc in source_locs:
    #     _BUILDER.add_source_map(loc.location, (loc.offset + address, loc.length))

    # _BUILDER.add_source_map(func.location, (address, len(code)))

    return BytecodeFunction(name, scope, signature, address)
