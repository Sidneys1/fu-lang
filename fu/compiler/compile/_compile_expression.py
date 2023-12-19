from io import BytesIO
from typing import Generator

from ...types import (TypeBase, IntegralType, IntType, FloatType, EnumType, GenericType, BOOL_TYPE, F16_TYPE, F32_TYPE,
                      F64_TYPE, I16_TYPE, I32_TYPE, I64_TYPE, I8_TYPE, U16_TYPE, U32_TYPE, U64_TYPE, U8_TYPE,
                      USIZE_TYPE, ARRAY_TYPE, RefType, make_ref, ComposedType, StaticType)
from ...virtual_machine.bytecode import (NumericTypes, OpcodeEnum, _encode_numeric, int_u64, int_u8, float_f32, int_u32,
                                         int_u16)
from ...virtual_machine.bytecode.builder import BytecodeBuilder

from .. import CompilerNotice
from ..analyzer.scope import AnalyzerScope, StaticVariableDecl
from ..lexer import ExpList, Identifier, Lex, LexedLiteral, Operator
from ..tokenizer import Token, TokenType

from ._storage_type_of import storage_type_of
from ._temp_source_map import TempSourceMap
from .dependencies import DependantFunction
from .scope import CompileScope, FunctionScope
from .storage import Storage, StorageDescriptor
from .util import write_to_buffer
from ._retrieve import retrieve
from ._convert_to_stack import convert_to_stack


def compile_expression(expression: Lex,
                       buffer: BytesIO,
                       want: TypeBase | None = None) -> Generator[TempSourceMap, None, StorageDescriptor]:
    """Compile a single expression."""
    from . import _LOG
    _LOG.debug(f'Compiling expression: {str(expression).strip()} (want: `{want.name if want is not None else want}`)')
    scope = CompileScope.current()
    start = buffer.tell()
    match expression:
        case LexedLiteral():
            value = expression.to_value()
            match value, want:
                case bool(), _ if want == BOOL_TYPE:
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
                    rtype, *bits = NumericTypes.best_value(value)
                    write_to_buffer(buffer, OpcodeEnum.PUSH_LITERAL, *bits)
                    return StorageDescriptor(Storage.Stack, rtype)
                case int(), _ if want == U8_TYPE:
                    #input(f"{want.name} -> {U8_TYPE.name}")
                    write_to_buffer(buffer, OpcodeEnum.PUSH_LITERAL, NumericTypes.u8, _encode_numeric(value, int_u8))
                    return StorageDescriptor(Storage.Stack, U8_TYPE)
                case int(), _ if want == U32_TYPE:
                    #input(f"{want.name} -> {U8_TYPE.name}")
                    write_to_buffer(buffer, OpcodeEnum.PUSH_LITERAL, NumericTypes.u32, _encode_numeric(value, int_u32))
                    return StorageDescriptor(Storage.Stack, U32_TYPE)
                case int(), _ if want == U64_TYPE:
                    #input(f"{want.name} -> {U8_TYPE.name}")
                    write_to_buffer(buffer, OpcodeEnum.PUSH_LITERAL, NumericTypes.u64, _encode_numeric(value, int_u64))
                    return StorageDescriptor(Storage.Stack, U64_TYPE)
                case int(), IntType():
                    raise NotImplementedError(f"Unknown inttype `{want.name}`.")
            raise NotImplementedError(
                f"Don't know how to handle {type(value).__name__} literals (want={want.name if want is not None else None})."
            )
        case Operator(oper=Token(type=TokenType.Equals), lhs=Identifier(), rhs=Lex()):
            assert isinstance(expression.lhs, Identifier)
            assert expression.rhs is not None
            rhs_storage = yield from compile_expression(expression.rhs, buffer)
            lhs_storage = storage_type_of(expression.lhs.value, expression.lhs.location)
            assert isinstance(lhs_storage.type, TypeBase)
            # assert isinstance(lhs_storage.decl,
            #                   StaticVariableDecl), f"lhs_storage is unexpectedly a `{type(lhs_storage).__name__}`"
            lhs_type = lhs_storage.type
            if isinstance(lhs_type, ComposedType):
                lhs_type = make_ref(lhs_type)
            convert_to_stack(rhs_storage, lhs_type, buffer, expression.rhs.location)
            match lhs_storage.storage:
                case Storage.Locals:
                    if lhs_storage.slot is None:
                        fn_scope = FunctionScope.current_fn()
                        assert fn_scope is not None
                        write_to_buffer(buffer, OpcodeEnum.INIT_LOCAL)
                        slot = len(fn_scope.locals)
                        fn_scope.locals[expression.lhs.value] = lhs_type
                        yield TempSourceMap(start, buffer.tell() - start, expression.location)
                        return StorageDescriptor(Storage.Locals, lhs_type, slot=slot)
                    else:
                        write_to_buffer(buffer, OpcodeEnum.POP_LOCAL, _encode_numeric(lhs_storage.slot, int_u8))
                        yield TempSourceMap(start, buffer.tell() - start, expression.location)
                        return lhs_storage
                case _:
                    raise NotImplementedError()
        case Operator(oper=Token(type=TokenType.Equality)):
            assert expression.lhs is not None
            assert expression.rhs is not None
            lhs_storage = yield from compile_expression(expression.lhs, buffer)
            assert isinstance(lhs_storage.type, TypeBase)
            convert_to_stack(lhs_storage, lhs_storage.type, buffer, expression.lhs.location)
            rhs_storage = yield from compile_expression(expression.rhs, buffer)
            assert isinstance(rhs_storage.type, TypeBase)
            convert_to_stack(rhs_storage, rhs_storage.type, buffer, expression.rhs.location)
            write_to_buffer(buffer, OpcodeEnum.CMP)
            return StorageDescriptor(Storage.Stack, BOOL_TYPE)
        case Operator(oper=Token(type=TokenType.LessThan)):
            assert expression.lhs is not None
            assert expression.rhs is not None
            lhs_storage = yield from compile_expression(expression.lhs, buffer)
            assert isinstance(lhs_storage.type, TypeBase)
            convert_to_stack(lhs_storage, lhs_storage.type, buffer, expression.lhs.location)
            rhs_storage = yield from compile_expression(expression.rhs, buffer)
            assert isinstance(rhs_storage.type, TypeBase)
            convert_to_stack(rhs_storage, rhs_storage.type, buffer, expression.rhs.location)
            write_to_buffer(buffer, OpcodeEnum.LESS)
            return StorageDescriptor(Storage.Stack, BOOL_TYPE)
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
            if lhs_storage.storage == Storage.Static:
                if isinstance(lhs_storage.type, AnalyzerScope):
                    member = lhs_storage.type.members[expression.rhs.value]
                    if isinstance(member, AnalyzerScope):
                        return StorageDescriptor(Storage.Static, member)
                    return StorageDescriptor(Storage.Static, member.type, decl=member)
                if isinstance(lhs_storage.type, StaticType):
                    member_type = lhs_storage.type.static_members[expression.rhs.value]
                    assert lhs_storage.decl is not None
                    member = lhs_storage.decl.member_decls[expression.rhs.value]
                    slot = -1
                    for s, name in enumerate(lhs_storage.type.static_members):
                        if name == expression.rhs.value:
                            slot = s
                            break
                    if slot == -1:
                        raise NotImplementedError()
                    return StorageDescriptor(Storage.Static, member_type, decl=member, slot=slot)
                raise NotImplementedError(f"lhs_storage.type is unexpectedly a `{type(lhs_storage.type).__name__}`")

            # Get left side somewhere we can access it
            lhs_storage = retrieve(lhs_storage, buffer, expression.lhs.location)
            next_part_start = buffer.tell()
            if next_part_start != start:
                yield TempSourceMap(start, buffer.tell() - start, expression.lhs.location)

            # input(f'Ran retrieve, lhs storage is now {lhs_storage}')
            _LOG.debug(f"...new storage is {lhs_storage.type.name}")
            if isinstance(lhs_storage.type, RefType):  # type: ignore # noqa: W1116  # pylint:disable=isinstance-second-argument-not-valid-type
                assert isinstance(lhs_storage.type, RefType)
                lhs_deref = lhs_storage.type.to
                assert isinstance(lhs_deref, ComposedType)
                # TODO: actually determine slot of rhs
                # assume for now that it's in declaration order?
                slot_num = -1
                slot_type: TypeBase
                for i, (k, v) in enumerate(lhs_deref.instance_members.items()):
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
                # input(f"{next_part_start:#06x}-{buffer.tell():#06x}")
                yield TempSourceMap(next_part_start, buffer.tell() - next_part_start, expression.rhs.location)
                # from traceback import format_stack
                # input(f"Generating TSM {start:#06x}-{buffer.tell()-start:#06x} @ {expression.location}\n\t" +
                #       '\t'.join(format_stack()))
                yield TempSourceMap(start, buffer.tell() - start, expression.location)
                return StorageDescriptor(
                    Storage.Stack,
                    make_ref(slot_type) if getattr(slot_type, 'reference_type', False) else slot_type)

            raise NotImplementedError()
        case Operator(oper=Token(type=TokenType.LBracket)):
            assert expression.rhs is not None
            lhs_storage = yield from compile_expression(expression.lhs, buffer)
            lhs_storage = retrieve(lhs_storage, buffer, expression.lhs.location)
            if isinstance(lhs_storage.type, RefType):  # noqa
                assert isinstance(lhs_storage.type, RefType)
                lhs_deref = lhs_storage.type.to
                # input(lhs_deref)
                assert isinstance(lhs_deref, ComposedType)
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
                        bittness = max(lhs_storage.type.get_size(), rhs_storage.type.get_size())
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
                        bittness = max(lhs_storage.type.get_size(), rhs_storage.type.get_size())
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
            print(f'compile_expression({expression=})')
            name = expression.value
            storage_type = storage_type_of(name, expression.location)
            # input(
            #     f'\tstorage_type_of({name=}) = StorageType({storage_type.storage}, {storage_type.type.name}, slot={storage_type.slot})'
            # )
            assert storage_type is not None
            return storage_type
        case Operator(oper=Token(type=TokenType.LParen)):
            assert expression.lhs is not None
            # resolve lhs type
            lhs = yield from compile_expression(expression.lhs, buffer)
            if lhs.storage == Storage.Static:
                # foo
                if lhs.decl is None:
                    raise NotImplementedError("???")
                func_decl = lhs.decl
                assert func_decl.type.callable is not None
                if isinstance(func_decl.type, StaticType):
                    # ctor
                    # input('ctor')
                    # TODO: emit new_object bytecode
                    # TODO: get type id
                    builder = BytecodeBuilder.current()
                    assert func_decl.type.instance_type is not None
                    type_id = builder.add_type_type(func_decl.type.instance_type)
                    write_to_buffer(buffer, OpcodeEnum.NEW, _encode_numeric(type_id, int_u16))
                    # TODO: dependant on ctor function (if it exists)
                    return StorageDescriptor(Storage.Stack, make_ref(func_decl.type.instance_type))
                # Some other static function/callable
                params, ret_type = func_decl.type.callable
                func = DependantFunction(buffer, func_decl)
                # TODO: push params
                if params != ():
                    assert isinstance(expression.rhs, ExpList)
                    assert len(expression.rhs.values) == len(params)
                    for param_type, expr in zip(params, expression.rhs.values):
                        ex_storage = yield from compile_expression(expr, buffer, want=param_type)
                        convert_to_stack(ex_storage, param_type, buffer, expr.location)
                    write_to_buffer(buffer, OpcodeEnum.INIT_ARGS, _encode_numeric(len(params), int_u8))
                write_to_buffer(buffer, OpcodeEnum.CALL_EXPORT, func.id())
                return StorageDescriptor(Storage.Stack, ret_type)
            if lhs.decl is not None:
                raise NotImplementedError("non-static svd?")
            raise NotImplementedError("Literally don't even know how we got here.")
        case Operator():
            raise CompilerNotice(
                'Error',
                f"Don't know how to compile `{type(expression.lhs).__name__} {expression.oper.value!r} {type(expression.rhs).__name__}`!",
                expression.location)
        case _:
            raise CompilerNotice('Error', f"Don't know how to compile expression `{type(expression).__name__}`!",
                                 expression.location)
    raise NotImplementedError()
