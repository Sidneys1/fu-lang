from logging import getLogger
from types import TracebackType
# from contextlib import COnte
from typing import ContextManager, Optional, Generator, TypeAlias, Iterator, Iterable
from contextvars import ContextVar, Token
from dataclasses import field, dataclass

from ..bytecode import OpcodeEnum, u16, NumericTypes

from . import CompilerNotice
from .util import is_sequence_of
from .analyzer import GLOBAL_SCOPE, StaticVariableDecl, _resolve_type, StaticScope
from .analyzer.static_type import type_from_lex
from .analyzer.static_scope import _SCOPE as _CURRENT_STATIC_SCOPE
from .typing import TypeBase
from .typing.composed_types.generic_types import GenericType
from .typing.integral_types import *
from .tokenizer import Token, TokenType
from .lexer import Lex, Declaration, Scope, ParamList, Identity, Statement, ReturnStatement, Operator, Atom, Identifier, Literal

_LOG = getLogger(__package__)

REF_TYPE_T = GenericType.GenericParam('T')
REF_TYPE = GenericType('ref', size=4, reference_type=False, generic_params={'T': REF_TYPE_T})


def make_ref(t: TypeBase) -> GenericType:
    return REF_TYPE.resolve_generic_instance(T=t, preserve_inheritance=True)  # type: ignore


BytecodeTypes: TypeAlias = OpcodeEnum | NumericTypes | int | bytes | tuple['BytecodeTypes', ...]


# @dataclass(frozen=True, kw_only=True, slots=True)
class CompileScope(ContextManager):
    name: str
    parent: Optional['CompileScope']
    _reset_tok: Token | None = None
    _reset_static_tok: Token | None = None
    static_scope: StaticScope

    def __init__(self, name: str, root=False):
        self.name = name
        self.parent = CompileScope.current() if not root else None
        if self.parent is None:
            self.static_scope = StaticScope.current()
        else:
            self.static_scope = self.parent.static_scope.get_child(name)
            assert self.static_scope is not None

    def __enter__(self):
        self._reset_tok = _CURRENT_COMPILE_SCOPE.set(self)
        self._reset_static_tok = _CURRENT_STATIC_SCOPE.set(self.static_scope)
        return self

    def __exit__(self, *args) -> None:
        assert self._reset_tok is not None
        _CURRENT_COMPILE_SCOPE.reset(self._reset_tok)
        _CURRENT_STATIC_SCOPE.reset(self._reset_static_tok)
        self._reset_static_tok = None
        self._reset_tok = None

    @staticmethod
    def current() -> 'CompileScope':
        return _CURRENT_COMPILE_SCOPE.get()

    @property
    def fqdn(self) -> str:
        names = [self.name]
        p = self.parent
        while p is not None and p is not GLOBAL_COMPILE_SCOPE:
            names.append(p.name)
            p = p.parent
        return '.'.join(reversed(names))


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
        while current is not None and current is not GLOBAL_COMPILE_SCOPE and not isinstance(current, FunctionScope):
            current = current.parent
        assert current is None or isinstance(current, FunctionScope)
        return current

    def __repr__(self) -> str:
        args = ', '.join(f"{k}: {v.name}" for k, v in self.args.items())
        return f"{self.fqdn}({args})"


GLOBAL_COMPILE_SCOPE = CompileScope('<GLOBAL SCOPE>', root=True)
_CURRENT_COMPILE_SCOPE: ContextVar[CompileScope] = ContextVar('_CURRENT_COMPILE_SCOPE', default=GLOBAL_COMPILE_SCOPE)


def to_bytes(input: Iterable[BytecodeTypes]) -> Iterator[int]:
    for x in input:
        match x:
            case tuple():
                yield from to_bytes(y for y in x)
            case Enum():
                val = x.value
                assert isinstance(val, int)
                yield val
            case bytes():
                yield from x
            case _:
                yield x


def compile() -> Generator[CompilerNotice, None, bytes | None]:
    _LOG.debug('\n\n\033#3STARTED COMPILING\n\033#4STARTED COMPILING\n\n')
    main = GLOBAL_SCOPE.members.get('main')
    assert isinstance(main, StaticVariableDecl), f"Main was a {type(main).__name__}"
    all: list[BytecodeTypes] = []
    try:
        for x in compile_func(main):
            if isinstance(x, CompilerNotice):
                yield x
            else:
                all.append(x)
    except CompilerNotice as ex:
        yield ex
        return None
    for x in all:
        if isinstance(x, tuple):
            _LOG.debug(', '.join(str(y) for y in x))
        else:
            _LOG.debug(x)
    return bytes(to_bytes(all))


# def compile_expression(expression, target_type, target_value):
#     _LOG.debug(f'Compiling expression: {str(expression).strip()}, result in {target_type!r} {target_value!r}')
#     scope = CompileScope.current()
#     match expression:
#         case Literal(type=TokenType.Number):
#             yield ParamType.u16
#             yield target_type
#             yield expression.to_value()
#             yield target_value
#         case Operator(oper=Token(type=TokenType.Dot)):
#             # assume lhs is identifier
#             if not isinstance(expression.lhs, Identifier):
#                 raise NotImplementedError()
#             name = expression.lhs.value
#             assert name in scope.args or name in scope.stack
#             haystack = scope.args if name in scope.args else scope.stack
#             if expression.lhs.value in haystack:
#                 index = -1
#                 for i, (k, v) in enumerate(haystack.items()):
#                     if k == expression.lhs.value:
#                         index = i
#                         lhs_type = v
#                         break
#                 lhs = ParamType.NearBase if not v.reference_type else 'deref', -(index +
#                                                                                  1) if name in scope.args else index

#             if not isinstance(expression.rhs, Identifier):
#                 raise NotImplementedError()
#             name = expression.rhs.value
#             index = -1
#             for i, (k, v) in enumerate(lhs_type.members.items()):
#                 if k == name:
#                     index = i
#                     lhs_type = v
#                     break
#             # rhs_type = lhs_type.members[name]
#             yield f"{lhs}[{index}] # {expression}"
#             # yield from lhs
#             # yield name
#         case Identifier():
#             name = expression.value
#             haystack = scope.args if name in scope.args else scope.stack
#             if name in haystack:
#                 index = -1
#                 for i, (k, v) in enumerate(haystack.items()):
#                     if k == name:
#                         index = i
#                         lhs_type = v
#                         break
#                 lhs = (ParamType.NearBase, index) if not v.reference_type else ('deref', -(index + 1))
#             yield f"{OpcodeEnum.MOV} {lhs[0]} {target_type} {lhs[1]} {target_value} --{expression}"
#         case _:
#             raise RuntimeError(f"Don't know how to compile {type(expression).__name__}!")

from enum import Enum


class Storage(Enum):
    Arguments = 'args'
    Locals = 'locals'
    Heap = 'heap'
    Stack = 'stack'


@dataclass(frozen=True, slots=True)
class StorageDescriptor:

    storage: Storage
    type: TypeBase
    slot: int | None = None


def _storage_type_of(name: str) -> StorageDescriptor:
    current_fn = FunctionScope.current_fn()
    if current_fn is None:
        raise NotImplementedError()
    for i, (k, v) in enumerate(current_fn.args.items()):
        if k == name:
            return StorageDescriptor(Storage.Arguments, v, slot=i)
    for i, (k, v) in enumerate(current_fn.locals.items()):
        if k == name:
            return StorageDescriptor(Storage.Locals, v, slot=i)
    for i, (k, v) in enumerate(current_fn.decls.items()):
        if k == name:
            return StorageDescriptor(Storage.Locals, v, slot=None)
    raise CompilerNotice('Error', f"Cannot find `{name}` in `{current_fn.fqdn}`.", None)


def retrieve(from_: StorageDescriptor) -> Generator[CompilerNotice | BytecodeTypes, None, StorageDescriptor]:
    match from_:
        case StorageDescriptor(storage=Storage.Arguments) if from_.slot is not None:
            """The thing we're trying to retrieve is in the current method's args, and it's a ref-type."""
            yield OpcodeEnum.PUSH_ARG, u16(from_.slot)
            return StorageDescriptor(Storage.Stack, from_.type)
        case _:
            raise CompilerNotice('Critical', f"Don't know how to get {from_.type.name} out of {from_.storage.name}",
                                 None)
    raise NotImplementedError()


def compile_expression(expression: Lex) -> Generator[CompilerNotice | BytecodeTypes, None, StorageDescriptor]:
    _LOG.debug(f'Compiling expression: {str(expression).strip()}')
    scope = CompileScope.current()
    match expression:
        case Operator(oper=Token(type=TokenType.Equals), lhs=Identifier(), rhs=Lex()):
            assert isinstance(expression.lhs, Identifier)
            assert expression.rhs is not None
            rhs_storage = yield from compile_expression(expression.rhs)
            lhs_storage = _storage_type_of(expression.lhs.value)
            yield from convert_to_stack(rhs_storage, lhs_storage.type)
            match lhs_storage.storage:
                case Storage.Locals:
                    if lhs_storage.slot is None:
                        fn_scope = FunctionScope.current_fn()
                        assert fn_scope is not None
                        yield OpcodeEnum.INIT_LOCAL
                        slot = len(fn_scope.locals)
                        fn_scope.locals[expression.lhs.value] = lhs_storage.type
                        return StorageDescriptor(Storage.Locals, lhs_storage.type, slot)
                    else:
                        yield OpcodeEnum.POP_LOCAL, u16(lhs_storage.slot)
                        return lhs_storage
                case _:
                    raise NotImplementedError()
        case Operator(oper=Token(type=TokenType.Dot), lhs=Identifier(), rhs=Identifier()):
            # what is lhs?
            assert isinstance(expression.lhs, Identifier) and isinstance(expression.rhs, Identifier)
            lhs_storage = _storage_type_of(expression.lhs.value)
            if lhs_storage is None:
                raise CompilerNotice('Error', f"Couldn't resolve `{expression.lhs.value}` in {scope.fqdn}.",
                                     expression.location)
            # Get left side somewhere we can access it
            new_storage = yield from retrieve(lhs_storage)
            if isinstance(new_storage.type, REF_TYPE):  # type: ignore
                assert isinstance(new_storage.type, GenericType)
                lhs_deref = new_storage.type.generic_params['T']
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
                    raise CompilerNotice('Error',
                                         f"Couldn't find member `{expression.rhs.value}` in type `{lhs_deref.name}`.",
                                         expression.location)
                yield OpcodeEnum.PUSH_REF, u16(slot_num)
                return StorageDescriptor(Storage.Stack, make_ref(slot_type) if slot_type.reference_type else slot_type)

            raise NotImplementedError()
        case Identifier():
            name = expression.value
            storage_type = _storage_type_of(name)
            assert storage_type is not None
            return storage_type
        case Operator():
            raise CompilerNotice(
                'Error',
                f"Don't know how to compile `{type(expression.lhs).__name__} {expression.oper.value!r} {type(expression.rhs).__name__}`!",
                expression.location)
        case _:
            raise CompilerNotice('Error', f"Don't know how to compile `{type(expression).__name__}`!",
                                 expression.location)
    raise NotImplementedError()


def convert_to_stack(from_: StorageDescriptor,
                     to_: TypeBase,
                     checked=True) -> Generator[CompilerNotice | BytecodeTypes, None, None]:
    _LOG.debug(f"Converting from `{from_.type.name}` to `{to_.name}`.")
    if from_.type == to_:
        match from_.storage:
            case Storage.Stack:
                return
            case Storage.Locals:
                # get slot
                fn_scope = FunctionScope.current_fn()
                assert fn_scope is not None and from_.slot is not None
                yield OpcodeEnum.PUSH_LOCAL, u16(from_.slot)
                return
            case _:
                raise NotImplementedError()
    match from_.type, to_:
        case (IntType(), IntType()) | (FloatType(), IntType()):
            assert isinstance(to_, IntType)
            yield OpcodeEnum.CHECKED_CONVERT, NumericTypes.from_int_type(to_)
        case _:
            raise CompilerNotice('Error', f"Not sure how to convert from `{from_.type.name}` to `{to_.name}`.", None)


def compile_statement(
        statement: Statement | Declaration | ReturnStatement) -> Generator[CompilerNotice | BytecodeTypes, None, None]:
    scope = CompileScope.current()
    fn_scope = FunctionScope.current_fn()
    _LOG.debug(f'Compiling statement: {str(statement).strip()}')
    match statement:
        case Declaration() if statement.initial is not None:
            """Initialize local."""
            name = statement.identity.lhs.value
            assert fn_scope is not None
            local_type = fn_scope.decls[name]

            value_storage = yield from compile_expression(statement.initial)
            yield from convert_to_stack(value_storage, local_type)
            yield OpcodeEnum.INIT_LOCAL
            fn_scope.locals[name] = local_type
        case Declaration():
            """Declaration without initialization - nop"""
            pass
        case Statement():
            yield from compile_expression(statement.value)
        case ReturnStatement():
            if statement.value is not None:
                return_storage = yield from compile_expression(statement.value)
                current_fn = FunctionScope.current_fn()
                assert current_fn is not None
                fn_ret = current_fn.returns
                yield from convert_to_stack(return_storage, fn_ret)
            yield OpcodeEnum.RET
        case _:
            raise CompilerNotice('Error', f"Don't know how to compile statement of type `{type(statement).__name__}`!",
                                 statement.location)


def compile_func(func: StaticVariableDecl) -> Generator[CompilerNotice | BytecodeTypes, None, None]:
    outer_scope = CompileScope.current()

    _LOG.debug(f'Compiling function {func.name}')
    assert isinstance(func.type, TypeBase)
    assert func.type.callable is not None
    element = func.lex
    assert isinstance(element, Declaration)
    assert isinstance(element.initial, Scope)

    decls: dict[str, TypeBase] = {}

    content = list(element.initial.content)
    i = 0
    while i < len(content):
        x = content[i]
        if not isinstance(x, Declaration):
            i += 1
            continue

        decl_type = type_from_lex(x.identity.rhs, outer_scope.static_scope)
        if isinstance(decl_type, StaticScope):
            i += 1
            continue
        if isinstance(decl_type, StaticVariableDecl):
            decl_type = decl_type.type
        decls[x.identity.lhs.value] = decl_type
        # static = yield from _prep_stack_slot(x, decl_type)
        # if static:
        #     _LOG.debug(f"Initialization of `{x.identity.lhs.value}` was static.")
        #     # content.remove(x)
        #     continue
        i += 1

    mods = element.identity.rhs.mods
    assert mods
    last_mod = mods[-1]
    assert isinstance(last_mod, ParamList)
    params = last_mod.params
    assert is_sequence_of(params, Identity)
    args = {params[i].lhs.value: (make_ref(v) if v.reference_type else v) for i, v in enumerate(func.type.callable[0])}

    with FunctionScope(element.identity.lhs.value, func.type.callable[1], args=args, decls=decls) as scope:
        # TODO split in to branch-delimited blocks of code
        for x in element.initial.content:
            yield from compile_statement(x)
    if False:
        yield
    #     for x in content:
    #         yield from compile_block(x)
