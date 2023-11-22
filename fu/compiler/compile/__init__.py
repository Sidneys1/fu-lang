from logging import getLogger
from typing import Generator, Iterable, Iterator
from io import SEEK_CUR

from ...types import (STR_ARRAY_TYPE, VOID_TYPE, TypeBase, ComposedType, make_ref)
from ...types.integral_types import *
from ...virtual_machine.bytecode import (OpcodeEnum, _encode_u16)
from ...virtual_machine.bytecode.builder import BytecodeBuilder
from ...virtual_machine.bytecode.structures import *
from .. import CompilerNotice
from ..analyzer.checks._check_conversion import _check_conversion
from ..analyzer.scope import AnalyzerScope, StaticVariableDecl
from ..analyzer.static_type import type_from_lex
from ..lexer import (Declaration, Identifier, Identity, LexedLiteral, Operator, ParamList, ReturnStatement, Scope,
                     Statement, Expression, Atom, IfStatement)
from ..util import is_sequence_of, collect_returning_generator

from .util import write_to_buffer
from .scope import CompileScope, FunctionScope
from .dependencies import DependantFunction
from ._compile_if_statement import compile_if_statement
from ._temp_source_map import TempSourceMap
from ._compile_expression import compile_expression
from ._convert_to_stack import convert_to_stack

_LOG = getLogger(__package__)


def compile_binary() -> Generator[CompilerNotice, None, BytecodeBinary | None]:
    _LOG.debug('\n\n\033#3STARTED COMPILING\n\033#4STARTED COMPILING\n\n')
    global_scope = AnalyzerScope.current()
    main = global_scope.members.get('main')

    if main is None:
        # dll?
        yield CompilerNotice('Error', "No entrypoint (symbol named `main`) found in global scope.", None)
        # _LOG.critical(f"Nothing to compile (no `main` symbol). Exiting.")
        return None

    assert isinstance(main, StaticVariableDecl), f"Main was a {type(main).__name__}"
    assert isinstance(main.type, ComposedType)
    assert isinstance(main.lex, Declaration)

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
            yield CompilerNotice(
                'Error', "Main must take no arguments: `()`; or one argument: `(str[])`. "
                f"Got `({', '.join(x.name for x in params)})` instead.", main.lex.identity.rhs.mods[-1].location)
            return None

    main_func: BytecodeFunction

    with BytecodeBuilder.create() as builder, CompileScope.create_root() as global_compile_scope:
        main_func_id = builder.reserve_function(builder.add_string('main'))
        try:
            main_func = compile_func(main_func_id, main)
            builder.fulfill_function_reservation(main_func_id, main_func)
        except CompilerNotice as ex:
            yield ex
            return None

        while global_compile_scope.deps:
            x = global_compile_scope.deps.pop()
            match x:
                case DependantFunction():
                    try:
                        assert x.decl.fqdn is not None
                        with global_compile_scope.enter_recursive(*x.decl.fqdn.split('.')[:-1]):
                            builder.fulfill_function_reservation(x.id_, compile_func(x.id_, x.decl))
                    except CompilerNotice as ex:
                        yield ex
                        return None

                case _:
                    raise NotImplementedError()

        assert isinstance(main_func.address, int), f"main_func.address is an `{type(main_func.address).__name__}`"
        ret = builder.finalize(entrypoint=main_func.address)

    return ret


def compile_statement(statement: Statement | IfStatement | Declaration | ReturnStatement,
                      buffer: BytesIO) -> Iterator[TempSourceMap]:
    # scope = CompileScope.current()
    fn_scope = FunctionScope.current_fn()
    assert fn_scope is not None
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
            assert fn_scope.func_id is not None
            if buffer.tell() >= 3 and buffer.seek(
                    -3, SEEK_CUR) and (last := buffer.read(3)) and last[0] == OpcodeEnum.CALL_EXPORT.value:
                buffer.seek(-3, SEEK_CUR)
                write_to_buffer(buffer, OpcodeEnum.TAIL_EXPORT, last[1:])
            else:
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
        start = buffer.tell()
        write_to_buffer(buffer, OpcodeEnum.NOP)
        yield from compile_statement(statement, buffer)
        write_to_buffer(buffer, OpcodeEnum.NOP)
        yield TempSourceMap(start, buffer.tell() - start, statement.location)


def compile_func(func_id: int_u16, func: StaticVariableDecl) -> BytecodeFunction:
    """Compile a function from a definition."""

    outer_scope = CompileScope.current()

    _LOG.debug(f'Compiling function {func.name}')
    assert isinstance(func.type, ComposedType) and func.type.callable is not None
    element = func.lex
    assert isinstance(element, Declaration)

    # Determine args
    mods = element.identity.rhs.mods
    assert mods
    last_mod = mods[-1]
    assert isinstance(last_mod, ParamList)
    params = last_mod.params
    assert is_sequence_of(params, Identity)

    args = {
        params[i].lhs.value: (make_ref(v) if getattr(v, 'reference_type', False) else v)
        for i, v in enumerate(func.type.callable[0])
    }
    decls: dict[str, TypeBase] = {}
    code: bytes
    source_locs: list[TempSourceMap] = []

    if element.is_fat_arrow:
        assert isinstance(element.initial, (Expression, Atom, Operator, Identifier, LexedLiteral))
        with FunctionScope(element.identity.lhs.value, func_id, func.type.callable[1], args=args,
                           decls=decls) as scope, BytesIO() as buffer:
            # TODO split in to branch-delimited blocks of code
            return_storage, source_maps = collect_returning_generator(
                compile_expression(element.initial, buffer, func.type.callable[1]))
            start = buffer.tell()
            convert_to_stack(return_storage, func.type.callable[1], buffer, element.initial.location)
            next_part_start = buffer.tell()
            if next_part_start != start:
                source_locs.append(TempSourceMap(start, next_part_start - start, element.raw[1].location))
            if buffer.tell() >= 3 and buffer.seek(
                    -3, SEEK_CUR) and (last := buffer.read(3)) and last[0] == OpcodeEnum.CALL_EXPORT.value:
                buffer.seek(-3, SEEK_CUR)
                write_to_buffer(buffer, OpcodeEnum.TAIL_EXPORT, last[1:])
            else:
                write_to_buffer(buffer, OpcodeEnum.RET)
            source_locs.extend(source_maps)
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

        with FunctionScope(element.identity.lhs.value, func_id, func.type.callable[1], args=args,
                           decls=decls) as scope, BytesIO() as buffer:
            # TODO split in to branch-delimited blocks of code
            for source_loc in compile_blocks(element.initial.content, buffer):
                source_locs.append(source_loc)
            if OpcodeEnum(buffer.getbuffer()[-1]) != OpcodeEnum.RET:
                write_to_buffer(buffer, OpcodeEnum.RET)
            code = buffer.getvalue()

    builder = BytecodeBuilder.current()
    assert isinstance(func.lex, Declaration) and builder is not None
    name = builder.add_string(func.lex.identity.lhs.value)
    scope = builder.add_string('' if outer_scope.parent is None else outer_scope.fqdn)
    signature = builder.add_type_type(func.type)
    address = builder.add_code(code)

    for loc in source_locs:
        print(f"Adding source map {loc.offset+address:#06x}[{loc.length}] - {loc.location}")
        builder.add_source_map(loc.location, (loc.offset + address, loc.length))

    builder.add_source_map(func.lex.location, (address, len(code)))

    return BytecodeFunction(name, scope, signature, address)
